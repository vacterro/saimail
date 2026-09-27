"""B-019 real-project bounded generation pilot: registration identity, exact input
gate, redacting dispatch, role-swapped replicates, dry-run proofs, metadata only.

The pilot rebuilds the exact B-018 BuiltProjectCorpus through the unchanged
B-018/B-017 path, refuses on any input-drift before a model call, and runs two
role-swapped replicates through the unchanged B-016 orchestration. These tests
drive the whole pipeline with deterministic in-process scripts and fake
transports: no network call exists anywhere in this module's test surface.
"""

import inspect
import json
import pathlib
import re
import socket
import urllib.request

import pytest

from lab import ally_generation_scenarios as sc
from lab import project_corpus_generation_pilot as pilot
from lab import project_corpus_pilot as pcp
from lab import saifren_population as pop
from lab import saifren_run as live
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag
from saimail import project_corpus as pc

ROOT = pathlib.Path(__file__).resolve().parent.parent
B018_REGISTRATION = ROOT / "lab" / pcp.REGISTRATION_FILE
LIVE_REGISTRATION = ROOT / "lab" / pilot.REGISTRATION_FILE

ALIAS_MODEL = "alias/model-a"
EXTERNAL_MODEL = "ext/model-b"

FORBIDDEN_REPORT_TOKENS = ("score", "winner", "leaderboard", "best_advisor",
                           "weighted", "ranking")


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def ok(output: str, model: str) -> dict:
    return {"output": output, "reported_model": model, "provider": None,
            "provider_basis": "NOT_EXPOSED", "finish_reason": "stop",
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            "latency_s": 0.01, "http_status": 200}


def transport_error() -> dict:
    return {"error_class": "HTTPError", "error": "HTTP 500 upstream", "http_status": 500,
            "latency_s": 0.01}


class ScriptedTransport:
    """Prompt-matched fake gateway; records every dispatch for one-call proofs."""

    def __init__(self, handler):
        self.handler = handler
        self.sends = []

    def send(self, prompt, model=None):
        self.sends.append({"prompt": prompt, "model": model})
        return self.handler(prompt, model)


def make_dispatch(send, log=None, cap=pilot.MAX_LIVE_CALLS):
    log = log if log is not None else pilot.MetadataLog()
    runner = live.Runner(send, live.CallBudget(cap), alias=live.COMBO)
    return pilot.RedactingDispatch(runner, log), log, runner


def fake_population(reported=(ALIAS_MODEL, EXTERNAL_MODEL)):
    population = pop.Population(
        combo=live.COMBO, observed_at=live._now(),
        membership_source=pop.COMBO_ALIAS_SAMPLE, roster_status=pop.ROSTER_NOT_EXPOSED)
    population.participants = (
        pop.Participant(role="A", requested=live.COMBO, reported_model=reported[0],
                        member_status=pop.OBSERVED_COMBO_MEMBER, source="COMBO_ALIAS"),
        pop.Participant(role="B", requested="vendor/comparator",
                        reported_model=reported[1],
                        member_status=pop.NOT_PROVEN_COMBO_MEMBER,
                        source="CATALOG_ELIGIBLE"),
    )
    return population


@pytest.fixture(scope="module")
def real_built():
    registration = pcp.load_registration(B018_REGISTRATION)
    return pcp.build_pilot_corpus(registration, ROOT).built


@pytest.fixture
def frozen(tmp_path):
    path = tmp_path / pilot.REGISTRATION_FILE
    pilot.register(path)
    return path


class BoomReviewer:
    """A reviewer that must never be called on a NO_ADVICE path."""

    def __init__(self):
        self.calls = 0

    def review(self, evidence_resolved_advice, corpus):
        self.calls += 1
        raise AssertionError("the reviewer must not be invoked")


def review_handler(corpus, candidate, *, overrides=None, rationale=None,
                   reported=None):
    reference = pilot.wire_review_text(candidate, corpus, overrides=overrides,
                                       rationale=rationale)

    def handler(prompt, model):
        model_reported = (reported(model) if reported is not None
                          else (ALIAS_MODEL if model in (live.COMBO, None)
                                else EXTERNAL_MODEL))
        if "bounded ALLY_ADVICE generator" in prompt:
            return ok(pilot.wire_candidate_text(candidate), model_reported)
        if ag.ally_candidate_id(candidate) in prompt:
            return ok(reference, model_reported)
        raise AssertionError("the handler matched no registered prompt")

    return handler


def drifted_built():
    artifact = pc.ProjectArtifact(
        project_scope=pilot.B018_PROJECT_SCOPE, source_kind=pc.RUNTIME_OBSERVATION,
        source_ref="drift:one", observed_at="2026-09-19T20:00:00Z",
        content="One drifted synthetic capture.")
    declaration = pc.ProjectEventDeclaration(
        project_scope=pilot.B018_PROJECT_SCOPE,
        member_evidence_refs=(pc.project_evidence_ref(artifact),))
    request = pc.ProjectCorpusRequest(
        project_scope=pilot.B018_PROJECT_SCOPE,
        window_start="2026-09-19T19:30:00Z", window_end="2026-09-19T21:20:00Z",
        selection_basis=pc.SELECTION_BASIS, artifacts=(artifact,),
        event_declarations=(declaration,))
    return pc.build_project_corpus(request)


def fake_live_run(tmp_path, real_built, registration_path, handler=None,
                  population=None):
    corpus = real_built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)
    transport = ScriptedTransport(handler or review_handler(corpus, candidate))
    result = pilot.run(
        tmp_path / "out", built=real_built, transport=transport,
        population=population if population is not None else fake_population(),
        registration_path=registration_path, update_latest=False)
    return result, transport


# ------------------------------------------------------ registration (8..12)


def test_frozen_live_registration_file_exists_and_matches():
    raw = LIVE_REGISTRATION.read_bytes()
    assert pilot.canonical_registration_bytes(
        json.loads(raw.decode("utf-8"))) == raw
    record = pilot.check_registration(LIVE_REGISTRATION)
    assert record["id"] == pilot.registration_id_for(raw)


def test_registration_is_canonical_and_identity_is_stable(frozen):
    raw = frozen.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    assert pilot.canonical_registration_bytes(document) == raw
    record = pilot.check_registration(frozen)
    assert record["id"] == pilot.registration_id_for(raw)
    assert record["id"] == pilot.check_registration(frozen)["id"]
    pilot.register(frozen)
    assert frozen.read_bytes() == raw


def test_registration_requires_the_declared_plan(frozen, tmp_path):
    missing = tmp_path / "missing.json"
    assert error(pilot.check_registration, missing).code == pilot.REGISTRATION_MISSING
    raw = frozen.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    document["budget"]["max_live_calls"] = 13
    mutated = tmp_path / "mutated.json"
    mutated.write_bytes(pilot.canonical_registration_bytes(document))
    assert error(pilot.check_registration, mutated).code == pilot.REGISTRATION_MISMATCH
    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_bytes(raw + b" ")
    assert error(pilot.check_registration, noncanonical).code == (
        pilot.REGISTRATION_UNREADABLE)
    assert error(pilot.check_registration, frozen, "sha256:" + "0" * 64).code == (
        pilot.REGISTRATION_MISMATCH)
    conflicting = tmp_path / "conflicting.json"
    conflicting.write_bytes(b"not the registration")
    assert error(pilot.register, conflicting).code == pilot.REGISTRATION_EXISTS


def test_registration_mutation_changes_identity(frozen, tmp_path):
    document = json.loads(frozen.read_bytes().decode("utf-8"))
    original = pilot.registration_id_for(frozen.read_bytes())
    document["roles"]["replicate_2"] = {"generator": "A", "reviewer": "B"}
    mutated = tmp_path / "mutated.json"
    mutated.write_bytes(pilot.canonical_registration_bytes(document))
    assert pilot.registration_id_for(mutated.read_bytes()) != original
    assert error(pilot.check_registration, mutated).code == pilot.REGISTRATION_MISMATCH


def test_declared_policy_is_frozen():
    declared = pilot.declared_registration()
    assert declared["registration_version"] == pilot.PILOT_VERSION
    assert declared["b018_input"]["registration_id"] == pilot.B018_REGISTRATION_ID
    assert declared["b018_input"]["build_id"] == pilot.B018_BUILD_ID
    assert declared["b018_input"]["corpus_id"] == pilot.B018_CORPUS_ID
    assert declared["b018_input"]["artifact_count"] == 8
    assert declared["b018_input"]["event_count"] == 5
    assert declared["b018_input"]["input_identity_gate"] == pilot.NO_GO_INPUT_DRIFT
    assert declared["budget"]["max_live_calls"] == 12
    assert declared["budget"]["discovery_max"] == 8
    assert declared["budget"]["real_generation_max"] == 2
    assert declared["budget"]["real_review_max"] == 2
    roles = declared["roles"]
    assert roles["replicate_1"] == {"generator": "A", "reviewer": "B"}
    assert roles["replicate_2"] == {"generator": "B", "reviewer": "A"}
    assert roles["third_replicate"] is False
    privacy = declared["privacy"]
    assert privacy["local_raw_generator_output_persistence"] is False
    assert privacy["local_reviewer_rationale_persistence"] is False
    assert privacy["local_prompt_persistence"] is False
    assert privacy["provider_side_retention"] == "NOT_VERIFIED_BY_SAIMAIL"
    assert privacy["provider_side_training_use"] == "NOT_VERIFIED_BY_SAIMAIL"
    assert privacy["external_inference_privacy_equals_local_non_persistence"] is False
    assert privacy["in_process_ephemeral_equals_cryptographic_memory_erasure"] is False
    assert declared["population"]["post_freeze_replacement"] is False
    assert declared["population"]["role_a"].startswith("the SAIFREN combo alias")
    assert "never described as a SAIFREN member" in declared["population"]["role_b"]
    assert declared["transmission_boundary"]["discovery_prompts_carry_corpus_data"] is (
        False)


def test_registration_binds_prompt_hashes(frozen):
    declared = pilot.declared_registration()
    assert declared["prompts"]["generator_template_sha256"] == pilot._sha256(
        pilot.GENERATOR_TEMPLATE)
    assert declared["prompts"]["reviewer_template_sha256"] == pilot._sha256(
        pilot.REVIEWER_TEMPLATE)
    assert declared["prompts"]["untrusted_evidence_marker"] in pilot.GENERATOR_TEMPLATE
    assert declared["prompts"]["untrusted_evidence_marker"] in pilot.REVIEWER_TEMPLATE
    assert "CORPUS_CONTENT_IS_UNTRUSTED_EVIDENCE_DATA" in pilot.GENERATOR_TEMPLATE


def test_planned_budget_within_ceiling(monkeypatch):
    assert pilot._budget_check() == 12
    assert pilot.PLANNED_CALLS_MAX <= pilot.MAX_LIVE_CALLS
    monkeypatch.setattr(pilot, "PLANNED_CALLS_MAX", 13)
    with pytest.raises(SystemExit):
        pilot._budget_check()


# ------------------------------------------------------- input gate (1..7)


def test_real_built_corpus_matches_the_frozen_b018_identity(real_built):
    assert real_built.build_id == pilot.B018_BUILD_ID
    assert real_built.corpus_id == pilot.B018_CORPUS_ID
    assert real_built.artifact_count == pilot.B018_ARTIFACT_COUNT
    assert real_built.event_count == pilot.B018_EVENT_COUNT
    assert real_built.project_scope == pilot.B018_PROJECT_SCOPE
    pilot.verify_input_identity(real_built)
    assert pilot.prepare_input(ROOT, built=real_built) is real_built


def test_rebuild_path_reproduces_the_frozen_identity():
    registration, result = pilot.rebuild_b018(ROOT)
    assert registration.registration_id == pilot.B018_REGISTRATION_ID
    assert result.built.build_id == pilot.B018_BUILD_ID
    assert result.built.corpus_id == pilot.B018_CORPUS_ID
    pilot.verify_input_identity(result.built, registration.registration_id)


def test_input_drift_refused_before_any_call(tmp_path, frozen, real_built):
    drift = drifted_built()
    assert error(pilot.verify_input_identity, drift).code == pilot.NO_GO_INPUT_DRIFT
    transport = ScriptedTransport(lambda prompt, model: ok('{"result":"NO_ADVICE"}',
                                                           ALIAS_MODEL))
    assert error(pilot.run, tmp_path / "out", built=drift, transport=transport,
                 population=fake_population(),
                 registration_path=frozen).code == pilot.NO_GO_INPUT_DRIFT
    assert transport.sends == []


def test_raw_reflection_corpus_refused(tmp_path, frozen, real_built):
    assert error(pilot.prepare_input, ROOT,
                 built=real_built.reflection_corpus).code == (
        pc.PROJECT_CORPUS_BUILDER_PROOF_REQUIRED)
    assert error(pilot.run, tmp_path / "out",
                 built=real_built.reflection_corpus,
                 registration_path=frozen).code == (
        pc.PROJECT_CORPUS_BUILDER_PROOF_REQUIRED)


# ------------------------------------------------------------ dry run (B13)


def test_dry_run_proves_the_registered_plan(tmp_path, frozen):
    result = pilot.run(tmp_path / "out", dry_run=True, registration_path=frozen,
                       update_latest=False)
    assert result["status"] == pilot.STATUS_DRY_RUN
    assert result["planned_calls_max"] == 12
    assert result["b018_input"]["build_id"] == pilot.B018_BUILD_ID
    assert result["b018_input"]["corpus_id"] == pilot.B018_CORPUS_ID
    assert result["call_budget"]["spent_total"] == 0
    replicates = {row["unit_id"]: row for row in result["replicates"]}
    assert replicates["R1"]["generator"]["role"] == "A"
    assert replicates["R1"]["reviewer"]["role"] == "B"
    assert replicates["R2"]["generator"]["role"] == "B"
    assert replicates["R2"]["reviewer"]["role"] == "A"
    assert replicates["R1"]["outcome"]["status"] == ag.APPROVED
    assert replicates["R1"]["reviewer_calls"] == 1
    assert replicates["R2"]["outcome"]["status"] == ag.NO_ADVICE
    assert replicates["R2"]["reviewer_calls"] == 0
    assert replicates["R2"]["stages"]["SEMANTIC_REVIEW"] == sc.STAGE_SKIPPED
    proofs = {row["unit_id"]: row for row in result["dry_run_proofs"]}
    assert proofs["PROOF.ONE_EVENT"]["outcome"]["status"] == ag.REJECTED
    assert proofs["PROOF.ONE_EVENT"]["outcome"]["code"] == (
        ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS)
    assert proofs["PROOF.ONE_EVENT"]["reviewer_calls"] == 0
    assert proofs["PROOF.ONE_EVENT"]["reviewed_state"] is False
    assert proofs["PROOF.REVIEW_FAIL"]["outcome"]["status"] == ag.REJECTED
    assert proofs["PROOF.REVIEW_FAIL"]["reviewed_state"] is False
    assert proofs["PROOF.REVIEW_UNKNOWN"]["outcome"]["status"] == ag.REJECTED
    assert proofs["PROOF.REVIEW_UNKNOWN"]["reviewed_state"] is False
    assert proofs["PROOF.MALFORMED_JSON"]["outcome"]["status"] == ag.ERROR
    assert proofs["PROOF.MALFORMED_JSON"]["generator_calls"] == 1
    assert proofs["PROOF.MALFORMED_JSON"]["reviewer_calls"] == 0
    document = json.loads(pathlib.Path(result["artifact"]).read_text(encoding="utf-8"))
    serialized = json.dumps(document, ensure_ascii=False)
    for forbidden in ("You are the bounded ALLY_ADVICE generator",
                      "You are the independent semantic reviewer",
                      '"result": "CANDIDATE"', '"result":"CANDIDATE"',
                      "Dry-run observed item", "Dry-run inference",
                      "dry-run verdict."):
        assert forbidden not in serialized


def test_dry_run_makes_zero_network_calls(tmp_path, frozen, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the dry run must make no network call")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    result = pilot.run(tmp_path / "out", dry_run=True, registration_path=frozen,
                       update_latest=False)
    assert result["status"] == pilot.STATUS_DRY_RUN
    assert result["b018_input"]["artifact_count"] == 8


# ------------------------------------------- generator/reviewer (23..40)


def test_no_advice_spends_zero_reviewer_calls(real_built):
    corpus = real_built.reflection_corpus
    dispatch, log, _ = make_dispatch(
        lambda prompt, model=None: ok('{"result":"NO_ADVICE"}', ALIAS_MODEL))
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    reviewer = BoomReviewer()
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
    assert outcome.status == ag.NO_ADVICE
    assert reviewer.calls == 0
    assert generator.calls == 1
    assert len(log.records) == 1


def test_malformed_json_is_error_with_single_call(real_built):
    corpus = real_built.reflection_corpus
    calls = {"n": 0}

    def send(prompt, model=None):
        calls["n"] += 1
        return ok('{"result":"CANDIDATE", this is not JSON', ALIAS_MODEL)

    dispatch, _log, _runner = make_dispatch(send)
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    reviewer = BoomReviewer()
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
    assert outcome.status == ag.ERROR
    assert calls["n"] == 1
    assert reviewer.calls == 0
    assert generator.parse_status == sc.STAGE_SCHEMA_ERROR


def test_generator_transport_error_single_call_no_retry(real_built):
    corpus = real_built.reflection_corpus
    calls = {"n": 0}

    def send(prompt, model=None):
        calls["n"] += 1
        return transport_error()

    dispatch, _log, _runner = make_dispatch(send)
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    with pytest.raises(SailangError) as caught:
        generator.generate(corpus)
    assert caught.value.code == pilot.PILOT_GENERATOR_TRANSPORT
    assert calls["n"] == 1
    assert generator.transport_status == sc.STAGE_ERROR


def test_outside_corpus_ref_reaches_zero_reviewer_calls(real_built):
    corpus = real_built.reflection_corpus
    dispatch, _log, _runner = make_dispatch(
        lambda prompt, model=None: ok(
            pilot.wire_candidate_text(pilot.outside_ref_candidate(corpus)),
            ALIAS_MODEL))
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    reviewer = BoomReviewer()
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert reviewer.calls == 0
    assert generator.ref_gate == sc.STAGE_FAIL


def test_one_event_candidate_reaches_zero_reviewer_calls():
    fixture = pilot.one_event_fixture()
    dispatch, _log, _runner = make_dispatch(
        lambda prompt, model=None: ok(
            pilot.wire_candidate_text(pilot.one_event_candidate(fixture)),
            ALIAS_MODEL))
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    reviewer = BoomReviewer()
    outcome = ag.generate_reviewed_ally_advice(fixture, generator, reviewer)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS
    assert reviewer.calls == 0


def test_two_event_candidate_reaches_existing_review_and_approves(real_built):
    corpus = real_built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)
    transport = ScriptedTransport(review_handler(corpus, candidate))
    dispatch, _log, _runner = make_dispatch(transport.send)
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    reviewer = pilot.PilotReviewer(dispatch, unit_id="R1", replicate=1, role="B",
                                   requested="vendor/comparator")
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
    assert outcome.status == ag.APPROVED
    assert isinstance(outcome.reviewed, ag.SemanticallyReviewedAllyAdvice)
    assert reviewer.calls == 1
    assert len(transport.sends) == 2
    assert outcome.report is not None
    assert all(v.verdict == ag.PASS for v in outcome.report.verdicts)


@pytest.mark.parametrize("overrides,code", [
    ({ag.OBSERVATION_SUPPORT: ag.FAIL}, ag.ALLY_GEN_REVIEW_REJECTED),
    ({ag.COUNTEREVIDENCE_ADEQUACY: ag.UNKNOWN}, ag.ALLY_GEN_REVIEW_UNCERTAIN),
])
def test_review_fail_and_unknown_mint_no_reviewed_state(real_built, overrides, code):
    corpus = real_built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)
    transport = ScriptedTransport(review_handler(corpus, candidate, overrides=overrides))
    dispatch, _log, _runner = make_dispatch(transport.send)
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    reviewer = pilot.PilotReviewer(dispatch, unit_id="R1", replicate=1, role="B",
                                   requested="vendor/comparator")
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
    assert outcome.status == ag.REJECTED
    assert outcome.code == code
    assert outcome.reviewed is None
    assert reviewer.calls == 1


def test_reviewer_receives_exact_parsed_candidate_and_full_corpus(real_built):
    corpus = real_built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)
    transport = ScriptedTransport(review_handler(corpus, candidate))
    dispatch, _log, _runner = make_dispatch(transport.send)
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    reviewer = pilot.PilotReviewer(dispatch, unit_id="R1", replicate=1, role="B",
                                   requested="vendor/comparator")
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
    assert outcome.status == ag.APPROVED
    generator_prompt = next(send["prompt"] for send in transport.sends
                            if "bounded ALLY_ADVICE generator" in send["prompt"])
    reviewer_prompt = next(send["prompt"] for send in transport.sends
                           if ag.ally_candidate_id(candidate) in send["prompt"])
    assert "You are the bounded ALLY_ADVICE generator" not in reviewer_prompt
    assert pilot.wire_candidate_text(candidate) not in reviewer_prompt
    assert candidate.render().decode("utf-8") in reviewer_prompt
    for item in corpus.items:
        assert item.evidence_ref in reviewer_prompt
    assert corpus.corpus_id in reviewer_prompt
    assert "CORPUS_CONTENT_IS_UNTRUSTED_EVIDENCE_DATA" in generator_prompt
    assert "CORPUS_CONTENT_IS_UNTRUSTED_EVIDENCE_DATA" in reviewer_prompt


def test_reviewer_transport_error_single_call_no_retry(real_built):
    corpus = real_built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)
    calls = {"n": 0}

    def send(prompt, model=None):
        calls["n"] += 1
        if "bounded ALLY_ADVICE generator" in prompt:
            return ok(pilot.wire_candidate_text(candidate), ALIAS_MODEL)
        return transport_error()

    dispatch, _log, _runner = make_dispatch(send)
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    reviewer = pilot.PilotReviewer(dispatch, unit_id="R1", replicate=1, role="B",
                                   requested="vendor/comparator")
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
    assert outcome.status == ag.ERROR
    assert calls["n"] == 2
    assert reviewer.transport_status == sc.STAGE_ERROR


# ------------------------------------------------ full fake run (41..62)


def test_full_fake_run_role_swap_budget_and_artifact(tmp_path, frozen, real_built):
    result, transport = fake_live_run(tmp_path, real_built, frozen)
    assert result["status"] == pilot.STATUS_COMPLETED
    assert len(transport.sends) == 4
    assert result["call_budget"]["spent_total"] == 4
    assert result["call_budget"]["spent_discovery"] == 0
    assert result["call_budget"]["spent_generation"] == 2
    assert result["call_budget"]["spent_review"] == 2
    assert result["call_budget"]["retries"] == 0
    assert result["call_budget"]["repair_calls"] == 0
    assert result["role_assignment"] == {"R1": {"generator": "A", "reviewer": "B"},
                                         "R2": {"generator": "B", "reviewer": "A"}}
    assert len(result["replicates"]) == 2
    r1, r2 = result["replicates"]
    assert r1["unit_id"] == "R1" and r2["unit_id"] == "R2"
    assert r1["generator"]["role"] == "A" and r1["reviewer"]["role"] == "B"
    assert r2["generator"]["role"] == "B" and r2["reviewer"]["role"] == "A"
    assert r1["outcome"]["status"] == ag.APPROVED
    assert r2["outcome"]["status"] == ag.APPROVED
    assert r1["candidate"] is not None
    assert r1["candidate"]["candidate_id"].startswith("sha256:")
    assert r1["refs_confined_to_corpus"] is True
    assert r1["observed_scope_exact"] is True
    assert r1["outside_corpus_refs"] == []
    assert len(r1["review"]["verdicts"]) == 8
    assert {v["dimension"] for v in r1["review"]["verdicts"]} == set(ag.DIMENSIONS)
    assert result["side_effects"] == {
        "reviewed_ally_to_human_private_calls": 0, "hlet1_created": 0,
        "henv1_created": 0, "human_private_store_writes": 0,
        "attention_admissions": 0, "operator_presentation_of_generated_advice": 0}
    document = json.loads(
        pathlib.Path(result["artifact"]).read_text(encoding="utf-8"))
    assert document["live_registration"]["id"] == pilot.check_registration(frozen)["id"]
    assert document["b018_input"]["build_id"] == pilot.B018_BUILD_ID
    assert document["ephemeral_scrub"]["prompt_fields_nulled"] is True
    assert document["ephemeral_scrub"]["output_fields_nulled"] is True
    assert document["ephemeral_scrub"]["error_fields_nulled"] is True
    assert document["plaintext_retention"]["prompt"] is False
    for call in document["calls"]:
        assert "prompt" not in call
        assert "output" not in call
        assert "error" not in call
        assert call["function"] in ("GENERATOR", "REVIEWER", "DISCOVERY")
    report = pathlib.Path(result["report"]).read_text(encoding="utf-8")
    assert "EXTERNAL DATA HANDLING LIMIT" in report
    assert "WHAT THIS RUN DOES NOT SHOW" in report
    assert pilot.B018_BUILD_ID in report
    assert pilot.B018_CORPUS_ID in report
    for token in FORBIDDEN_REPORT_TOKENS:
        assert token not in report.lower()
    interpretation = pathlib.Path(result["interpretation"]).read_text(encoding="utf-8")
    assert "What cannot be concluded" in interpretation


def test_no_advice_replicate_costs_one_generator_call(tmp_path, frozen, real_built):
    corpus = real_built.reflection_corpus

    def handler(prompt, model):
        assert "bounded ALLY_ADVICE generator" in prompt
        return ok('{"result":"NO_ADVICE"}', ALIAS_MODEL)

    result, transport = fake_live_run(tmp_path, real_built, frozen, handler=handler)
    assert len(transport.sends) == 2
    assert all(row["outcome"]["status"] == ag.NO_ADVICE for row in result["replicates"])
    assert all(row["reviewer_calls"] == 0 for row in result["replicates"])
    assert result["call_budget"]["spent_review"] == 0


def test_same_reported_model_pair_is_recorded_not_called_cross_model(
        tmp_path, frozen, real_built):
    corpus = real_built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)
    transport = ScriptedTransport(review_handler(
        corpus, candidate, reported=lambda model: ALIAS_MODEL))
    result = pilot.run(
        tmp_path / "out", built=real_built, transport=transport,
        population=fake_population(reported=(ALIAS_MODEL, ALIAS_MODEL)),
        registration_path=frozen, update_latest=False)
    for row in result["replicates"]:
        assert row["same_reported_model_pair"] is True
        assert row["same_reported_model_label"] == pilot.SAME_REPORTED_MODEL_PAIR
    report = pathlib.Path(result["report"]).read_text(encoding="utf-8")
    assert "cross-model" not in report.lower()


def test_no_go_population_starts_no_content_call(tmp_path, frozen, real_built):
    population = fake_population()
    population.participants = population.participants[:1]
    transport = ScriptedTransport(
        lambda prompt, model: (_ for _ in ()).throw(AssertionError("no call")))
    result = pilot.run(tmp_path / "out", built=real_built, transport=transport,
                       population=population, registration_path=frozen,
                       update_latest=False)
    assert result["status"] == pilot.NO_GO_POPULATION
    assert transport.sends == []
    assert result["call_budget"]["spent_total"] == 0
    assert result["replicates"] == []
    assert pathlib.Path(result["artifact"]).exists()
    assert pathlib.Path(result["report"]).exists()


def test_credential_unavailable_is_declared(tmp_path, frozen, real_built, monkeypatch):
    def refuse(**kwargs):
        raise pilot.CredentialNotProvisioned("no credential provisioned")

    monkeypatch.setattr(pilot, "resolve", refuse)
    result = pilot.run(tmp_path / "out", built=real_built,
                       registration_path=frozen, update_latest=False)
    assert result["status"] == pilot.LIVE_NOT_RUN_CREDENTIAL_UNAVAILABLE
    assert result["call_budget"]["spent_total"] == 0
    assert result["replicates"] == []
    assert pathlib.Path(result["artifact"]).exists()


def test_full_fake_run_touches_no_human_corridor(tmp_path, frozen, real_built,
                                                 monkeypatch):
    from saimail.human_attention import AttentionQueue
    from saimail.sailetter import HumanPrivateStore

    def boom(*args, **kwargs):
        raise AssertionError("the pilot must not touch the human-private corridor")

    monkeypatch.setattr(aa, "ally_to_human_private", boom)
    monkeypatch.setattr(ag, "reviewed_ally_to_human_private", boom)
    monkeypatch.setattr("saimail.sailetter.seal_human_private", boom)
    monkeypatch.setattr(HumanPrivateStore, "deliver", boom)
    monkeypatch.setattr(AttentionQueue, "admit_receiver_candidate", boom)
    result, _transport = fake_live_run(tmp_path, real_built, frozen)
    assert result["replicates"][0]["outcome"]["status"] == ag.APPROVED
    names = sorted(entry.name for entry in (tmp_path / "out").iterdir())
    assert len(names) == 2
    assert (tmp_path / "analysis").is_dir()
    assert pathlib.Path(result["interpretation"]).exists()


def test_artifact_and_report_are_metadata_only(tmp_path, frozen, real_built):
    result, _transport = fake_live_run(tmp_path, real_built, frozen)
    artifact_text = pathlib.Path(result["artifact"]).read_text(encoding="utf-8")
    report_text = pathlib.Path(result["report"]).read_text(encoding="utf-8")
    interpretation = pathlib.Path(result["interpretation"]).read_text(encoding="utf-8")
    for text in (artifact_text, report_text, interpretation):
        for forbidden in ("Dry-run observed item", "Dry-run inference",
                          "Dry-run suggestion", "Dry-run counterevidence",
                          "Dry-run uncertainty", "You are the bounded ALLY_ADVICE",
                          "BEGIN_CORPUS_CONTENT", '"FORMAT": "ALLY1"'):
            assert forbidden not in text, forbidden
    assert "Dry-run observed item" not in artifact_text


def test_module_has_no_human_private_corridor_import():
    source = inspect.getsource(pilot)
    imports = re.findall(r"^\s*(?:import|from)\s+([A-Za-z0-9_.]+)", source,
                         flags=re.MULTILINE)
    for forbidden in ("saimail.sailetter", "saimail.human_attention",
                      "saimail.postoffice", "saimail.hardware_piv",
                      "saimail.envelope"):
        assert forbidden not in imports, forbidden
    for forbidden in ("HumanPrivateStore", "AttentionQueue", "seal_human_private",
                      "reviewed_ally_to_human_private("):
        assert forbidden not in source, forbidden


def test_console_summary_carries_no_raw_text(tmp_path, frozen, real_built):
    result, _transport = fake_live_run(tmp_path, real_built, frozen)
    printed = json.dumps(pilot.console_summary(result), ensure_ascii=False)
    assert "You are the bounded ALLY_ADVICE" not in printed
    assert "Dry-run observed item" not in printed
    assert json.loads(printed)["artifact"] == result["artifact"]


def test_redacting_dispatch_scrubs_runner_records(real_built):
    corpus = real_built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)
    transport = ScriptedTransport(review_handler(corpus, candidate))
    dispatch, log, runner = make_dispatch(transport.send)
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    generator.generate(corpus)
    assert len(runner.calls) == 1
    retained = runner.calls[0]
    assert retained["prompt"] is None
    assert retained["output"] is None
    assert retained.get("error") is None
    assert "prompt_sha256" in retained
    assert len(log.records) == 1
    raw_output = pilot.wire_candidate_text(candidate)
    record = log.records[0]
    assert record["visible_output_sha256"] == pilot._sha256(raw_output)
    assert record["visible_output_bytes"] == len(raw_output.encode("utf-8"))
    assert record["prompt_sha256"] == pilot._sha256(transport.sends[0]["prompt"])
