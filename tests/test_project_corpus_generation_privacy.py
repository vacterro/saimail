"""B-019 privacy RED/GREEN proof: no raw prompt, generator output, candidate prose,
reviewer rationale or provider error body reaches any durable artifact.

The full fake run keeps unique canary strings inside the fake raw generator
output and the fake reviewer rationale; after the run every durable output --
artifact, report, interpretation, runner retained records, metadata call records
and the console projection -- is inspected recursively for canary plaintext.
The corpus-content retention proof additionally asserts that no real B-018
corpus content appears in the B-019 outputs.

The population section of the artifact is the second, independently proven
boundary: the generic ``Population.as_record()`` keeps raw discovery/selection
error text by design, so the durable artifact may only use the explicit privacy
projection. Canaries inside ``discovery.alias_transport_errors[*].error``,
``rejected_candidates[*].error`` and one unlisted nested path must not survive,
while the error class, requested route and rejection reason must.
"""

import hashlib
import json
import pathlib

import pytest

from lab import project_corpus_generation_pilot as pilot
from lab import project_corpus_pilot as pcp
from lab import saifren_population as pop
from lab import saifren_run as live
from saimail import ally_advice as aa
from saimail import ally_generation as ag
from saimail import project_corpus as pc

ROOT = pathlib.Path(__file__).resolve().parent.parent

GENERATOR_CANARY = "PRIVATE_GENERATOR_CANARY_7B42"
REVIEWER_CANARY = "PRIVATE_REVIEWER_CANARY_91AC"
CORPUS_CANARY = "PRIVATE_CORPUS_CANARY_5E1D"
ERROR_CANARY = "PRIVATE_ERROR_BODY_CANARY_0F77"
POPULATION_CANARY_A = "PRIVATE_POPULATION_ERROR_CANARY_A"
POPULATION_CANARY_B = "PRIVATE_POPULATION_ERROR_CANARY_B"
POPULATION_CANARY_C = "PRIVATE_POPULATION_ERROR_CANARY_C"

POPULATION_CANARIES = (POPULATION_CANARY_A, POPULATION_CANARY_B, POPULATION_CANARY_C)

ALIAS_MODEL = "alias/model-a"
EXTERNAL_MODEL = "ext/model-b"

#: The T-69 outputs this correction must leave byte-identical (matrix 21..23).
HISTORICAL_ARTIFACT = (ROOT / "lab" / "out"
                       / "project_corpus_generation_live_20260919T220641Z.json")
HISTORICAL_REPORT = (ROOT / "lab" / "out"
                     / "PROJECT_CORPUS_GENERATION_REPORT_20260919T220641Z.md")
HISTORICAL_INTERPRETATION = (ROOT / "lab" / "analysis"
                             / "project_corpus_generation_20260919T220641Z.md")
HISTORICAL_ARTIFACT_SHA256 = (
    "e9745fcbb84f12f29f8e54c7f891e0b9a61949710e40d48224e9352889caa5d7")
HISTORICAL_REPORT_SHA256 = (
    "f442512fc28d7e31d54b0ae01510c9ee78985dc46024d56873c31b42e4f860b5")
HISTORICAL_INTERPRETATION_SHA256 = (
    "f4f2d92c60fbab134ef5b404968a6dc853f3ca2914fe83ae269376b791157617")

PRIVACY_CORRECTION_NOTE = (ROOT / "lab" / "analysis"
                           / "project_corpus_generation_20260919T220641Z_privacy_correction.md")


def ok(output: str, model: str) -> dict:
    return {"output": output, "reported_model": model, "provider": None,
            "provider_basis": "NOT_EXPOSED", "finish_reason": "stop",
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            "latency_s": 0.01, "http_status": 200}


class ScriptedTransport:
    def __init__(self, handler):
        self.handler = handler
        self.sends = []
        self.results = []

    def send(self, prompt, model=None):
        self.sends.append({"prompt": prompt, "model": model})
        result = self.handler(prompt, model)
        self.results.append(result)
        return result


def make_dispatch(send, log=None, cap=pilot.MAX_LIVE_CALLS):
    log = log if log is not None else pilot.MetadataLog()
    runner = live.Runner(send, live.CallBudget(cap), alias=live.COMBO)
    return pilot.RedactingDispatch(runner, log), log, runner


def fake_population():
    population = pop.Population(
        combo=live.COMBO, observed_at=live._now(),
        membership_source=pop.COMBO_ALIAS_SAMPLE, roster_status=pop.ROSTER_NOT_EXPOSED)
    population.participants = (
        pop.Participant(role="A", requested=live.COMBO, reported_model=ALIAS_MODEL,
                        member_status=pop.OBSERVED_COMBO_MEMBER, source="COMBO_ALIAS"),
        pop.Participant(role="B", requested="vendor/comparator",
                        reported_model=EXTERNAL_MODEL,
                        member_status=pop.NOT_PROVEN_COMBO_MEMBER,
                        source="CATALOG_ELIGIBLE"),
    )
    return population


def canary_population():
    """A fake population whose raw diagnostic text carries unique canaries.

    Canary A sits on the alias transport path, canary B on a rejected candidate,
    canary C on an unlisted nested path so the projection is proven to audit more
    than the two paths observed in the historical live artifact.
    """
    population = pop.Population(
        combo=live.COMBO, observed_at="2026-09-19T22:00:00Z",
        membership_source=pop.COMBO_ALIAS_SAMPLE, roster_status=pop.ROSTER_NOT_EXPOSED,
        observed_members=(ALIAS_MODEL,), catalog_size=3,
        catalog_digest="sha256:" + "1" * 64,
        membership_digest="sha256:" + "2" * 64, probes_used=2)
    population.participants = (
        pop.Participant(role="A", requested=live.COMBO, reported_model=ALIAS_MODEL,
                        member_status=pop.OBSERVED_COMBO_MEMBER, source="COMBO_ALIAS"),
        pop.Participant(role="B", requested="vendor/comparator",
                        reported_model=EXTERNAL_MODEL,
                        member_status=pop.NOT_PROVEN_COMBO_MEMBER,
                        source="CATALOG_ELIGIBLE"),
    )
    population.rejected_candidates = (
        {"requested": "vendor/reject", "namespace": "vendor", "reason": "TRANSPORT",
         "error_class": "HTTPError", "error": f"HTTP 500 {POPULATION_CANARY_B}"},
        {"requested": "vendor/same", "namespace": "vendor",
         "reason": "SAME_REPORTED_MODEL_AS_ROLE_A", "reported_model": ALIAS_MODEL},
    )
    population.selection_probes_used = 4
    population.discovery = {
        "surface": pop.DISCOVERY_PATH,
        "combos_listed": [live.COMBO],
        "roster_field_present": False,
        "alias_transport_errors": [
            {"requested": live.COMBO, "error_class": "EmptyOutput",
             "error": f"no content; {POPULATION_CANARY_A}"}],
        "future_probe": {"error": POPULATION_CANARY_C,
                         "meta": [{"body": POPULATION_CANARY_C + "_NESTED"}]},
    }
    return population


def nested_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from nested_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from nested_strings(item)


def serialized_text(value) -> str:
    return "\n".join(nested_strings(value))


def file_sha256(path) -> str:
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def real_built():
    registration = pcp.load_registration(ROOT / "lab" / pcp.REGISTRATION_FILE)
    return pcp.build_pilot_corpus(registration, ROOT).built


@pytest.fixture
def frozen(tmp_path):
    path = tmp_path / pilot.REGISTRATION_FILE
    pilot.register(path)
    return path


def combined_canary_run(tmp_path, frozen, real_built, population=None):
    """One full fake run whose raw generator output and reviewer rationale carry canaries."""
    corpus = real_built.reflection_corpus
    refs = sorted({item.evidence_ref for item in corpus.items})
    candidate = aa.AllyAdvice(
        created="2026-09-19T00:00:00Z",
        work_context="Canary fixture context.",
        observed_scope=pilot.B018_PROJECT_SCOPE,
        observed=(
            aa.AdviceObservation(f"{GENERATOR_CANARY} observed item one.",
                                 (refs[0], refs[1])),
            aa.AdviceObservation("Canary fixture observed item two.", (refs[2], refs[3])),
        ),
        inferred="Canary fixture inference.",
        guidance_mode=aa.CONSIDER_CHANGE,
        suggested="Canary fixture suggestion.",
        counterevidence=(
            aa.AdviceCounterevidence("Canary fixture counterevidence.", (refs[0],)),
        ),
        uncertainty="Canary fixture uncertainty.",
    )

    def handler(prompt, model):
        reported = ALIAS_MODEL if model in (live.COMBO, None) else EXTERNAL_MODEL
        if "bounded ALLY_ADVICE generator" in prompt:
            return ok(pilot.wire_candidate_text(candidate), reported)
        if ag.ally_candidate_id(candidate) in prompt:
            return ok(pilot.wire_review_text(
                candidate, corpus, rationale=f"{REVIEWER_CANARY} rationale."), reported)
        raise AssertionError("the handler matched no registered prompt")

    transport = ScriptedTransport(handler)
    result = pilot.run(
        tmp_path / "out", built=real_built, transport=transport,
        population=population if population is not None else fake_population(),
        registration_path=frozen, update_latest=False)
    return result, transport, candidate


def strip_and_read(path) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


# ------------------------------------------------ canary absence (13..19)


def test_full_fake_run_persists_no_raw_prose_canary(tmp_path, frozen, real_built):
    result, transport, candidate = combined_canary_run(tmp_path, frozen, real_built)
    assert result["replicates"][0]["outcome"]["status"] == ag.APPROVED
    # Non-vacuous: the canaries really were in the raw traffic this run handled.
    assert GENERATOR_CANARY in pilot.wire_candidate_text(candidate)
    assert GENERATOR_CANARY in transport.results[0]["output"]
    assert REVIEWER_CANARY in transport.results[1]["output"]
    # The parsed candidate (with its canary statement) reached the reviewer prompt.
    assert GENERATOR_CANARY in transport.sends[1]["prompt"]
    for path in (result["artifact"], result["report"], result["interpretation"]):
        text = strip_and_read(path)
        assert GENERATOR_CANARY not in text
        assert REVIEWER_CANARY not in text
        assert CORPUS_CANARY not in text
        assert "Canary fixture" not in text


def test_artifact_call_records_carry_no_raw_fields(tmp_path, frozen, real_built):
    result, _transport, _candidate = combined_canary_run(tmp_path, frozen, real_built)
    document = json.loads(strip_and_read(result["artifact"]))
    assert document["calls"]
    for call in document["calls"]:
        assert set(call) & {"prompt", "output", "error", "provider_error"} == set()
        assert isinstance(call["prompt_sha256"], str)
        assert isinstance(call["visible_output_sha256"], str)
        assert isinstance(call["visible_output_bytes"], int)
        assert call["visible_output_bytes"] > 0
    serialized = json.dumps(document, ensure_ascii=False)
    assert GENERATOR_CANARY not in serialized
    assert REVIEWER_CANARY not in serialized
    assert "Canary fixture" not in serialized


def test_durable_outputs_contain_no_real_corpus_content(tmp_path, frozen, real_built):
    result, _transport, _candidate = combined_canary_run(tmp_path, frozen, real_built)
    snippets = [item.content[:80] for item in real_built.reflection_corpus.items]
    for path in (result["artifact"], result["report"], result["interpretation"]):
        text = strip_and_read(path)
        for snippet in snippets:
            assert snippet not in text, snippet[:40]
    assert "BEGIN_CORPUS_CONTENT" not in strip_and_read(result["artifact"])


def test_console_projection_contains_no_canary(tmp_path, frozen, real_built, capsys):
    result, _transport, _candidate = combined_canary_run(tmp_path, frozen, real_built)
    print(json.dumps(pilot.console_summary(result), ensure_ascii=False, indent=2))
    captured = capsys.readouterr()
    assert GENERATOR_CANARY not in captured.out
    assert REVIEWER_CANARY not in captured.out
    assert "Canary fixture" not in captured.out
    assert captured.err == ""


# ------------------------------------ retained records / prompts (20..22)


def test_runner_retained_records_are_scrubbed_after_processing(real_built):
    corpus = real_built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)

    def send(prompt, model=None):
        return ok(pilot.wire_candidate_text(candidate), ALIAS_MODEL)

    dispatch, log, runner = make_dispatch(send)
    ephemeral = dispatch(pilot.generator_prompt(corpus), live.COMBO, unit_id="R1",
                         replicate=1, role="A", function="GENERATOR")
    assert ephemeral["output"] is not None
    assert ephemeral["status"] == "OK"
    assert GENERATOR_CANARY not in json.dumps(log.records)
    for record in runner.calls:
        assert record["prompt"] is None
        assert record["output"] is None
        assert record.get("error") is None


def test_prompt_plaintext_never_reaches_metadata_records():
    artifact = pc.ProjectArtifact(
        project_scope=pilot.B018_PROJECT_SCOPE, source_kind=pc.RUNTIME_OBSERVATION,
        source_ref="canary:source", observed_at="2026-09-19T20:00:00Z",
        content=f"{CORPUS_CANARY}: one bounded private corpus line.")
    declaration = pc.ProjectEventDeclaration(
        project_scope=pilot.B018_PROJECT_SCOPE,
        member_evidence_refs=(pc.project_evidence_ref(artifact),))
    request = pc.ProjectCorpusRequest(
        project_scope=pilot.B018_PROJECT_SCOPE,
        window_start="2026-09-19T19:30:00Z", window_end="2026-09-19T21:20:00Z",
        selection_basis=pc.SELECTION_BASIS, artifacts=(artifact,),
        event_declarations=(declaration,))
    corpus = pc.build_project_corpus(request).reflection_corpus
    transport = ScriptedTransport(
        lambda prompt, model=None: ok('{"result":"NO_ADVICE"}', ALIAS_MODEL))
    dispatch, log, runner = make_dispatch(transport.send)
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, BoomReviewer())
    assert outcome.status == ag.NO_ADVICE
    # Non-vacuous: the corpus content was inside the transmitted prompt.
    assert CORPUS_CANARY in transport.sends[0]["prompt"]
    assert CORPUS_CANARY not in json.dumps(log.records)
    assert CORPUS_CANARY not in json.dumps(runner.calls)
    assert "prompt" not in log.records[0]
    assert "output" not in log.records[0]
    assert log.records[0]["visible_output_sha256"] is not None


class BoomReviewer:
    def __init__(self):
        self.calls = 0

    def review(self, evidence_resolved_advice, corpus):
        self.calls += 1
        raise AssertionError("the reviewer must not be invoked")


def test_provider_error_body_is_never_persisted(real_built):
    corpus = real_built.reflection_corpus

    def send(prompt, model=None):
        return {"error_class": "HTTPError",
                "error": f"HTTP 500 {ERROR_CANARY}",
                "http_status": 500, "latency_s": 0.01}

    dispatch, log, runner = make_dispatch(send)
    generator = pilot.PilotGenerator(dispatch, unit_id="R1", replicate=1, role="A",
                                     requested=live.COMBO)
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, BoomReviewer())
    assert outcome.status == ag.ERROR
    record = log.records[0]
    assert record["error_class"] == "HTTPError"
    assert record["http_status"] == 500
    assert "error" not in record
    assert ERROR_CANARY not in json.dumps(record, ensure_ascii=False)
    assert ERROR_CANARY not in json.dumps(runner.calls, ensure_ascii=False)
    assert runner.calls[0]["error"] is None


def test_discovery_probe_output_and_error_text_are_sanitized():
    record = {
        "call_id": "abc", "unit_id": "DISCOVERY.probe", "replicate": 0,
        "role": "DISCOVERY", "function": "DISCOVERY", "requested_model": "m",
        "reported_model": "m", "provider": None, "provider_basis": "NOT_EXPOSED",
        "timestamp": "2026-09-19T20:00:00Z", "prompt_sha256": "a" * 64,
        "visible_output": f"OK {ERROR_CANARY}", "visible_output_sha256": None,
        "status": "OK", "error_class": None, "http_status": 200, "latency_s": 0.01,
        "usage": {}, "local_estimated_input_tokens": 3,
        "gateway_reported_prompt_tokens": 4, "prompt_token_delta": 1,
    }
    sanitized = pilot.sanitize_discovery_record(record)
    text = json.dumps(sanitized, ensure_ascii=False)
    assert ERROR_CANARY not in text
    assert "visible_output" not in sanitized
    assert sanitized["visible_output_sha256"] == pilot._sha256(
        f"OK {ERROR_CANARY}")
    assert sanitized["visible_output_bytes"] == len(
        f"OK {ERROR_CANARY}".encode("utf-8"))


def test_artifact_registration_and_report_are_self_describing(tmp_path, frozen,
                                                              real_built):
    result, _transport, _candidate = combined_canary_run(tmp_path, frozen, real_built)
    document = json.loads(strip_and_read(result["artifact"]))
    assert document["privacy"]["provider_side_retention"] == "NOT_VERIFIED_BY_SAIMAIL"
    assert document["privacy"]["local_raw_generator_output_persistence"] is False
    assert document["plaintext_retention"]["generator_output"] is False
    assert document["plaintext_retention"]["reviewer_rationale"] is False
    report = strip_and_read(result["report"])
    assert "EXTERNAL DATA HANDLING LIMIT" in report
    assert "Provider-side retention/use was not established by this experiment." in report


# ------------------------------------ population projection (T-70, 1..16)


def test_pre_fix_generic_population_record_carries_raw_error_text():
    """RED control: the pre-fix artifact serialized exactly this generic record."""
    raw = json.dumps(canary_population().as_record(), ensure_ascii=False)
    assert POPULATION_CANARY_A in raw
    assert POPULATION_CANARY_B in raw


def test_population_projection_drops_rejected_candidate_error_text():
    record = pilot.sanitize_population_record_for_private_pilot(canary_population())
    text = serialized_text(record)
    for canary in POPULATION_CANARIES:
        assert canary not in text
    assert set(record["rejected_candidates"][0]) & {"error"} == set()


def test_population_projection_drops_alias_transport_error_text():
    record = pilot.sanitize_population_record_for_private_pilot(canary_population())
    alias = record["discovery"]["alias_transport_errors"][0]
    assert POPULATION_CANARY_A not in serialized_text(alias)
    assert "error" not in alias


def test_population_projection_keeps_diagnostic_topology():
    """RED-3 / B5: privacy correction must not erase the experiment topology."""
    record = pilot.sanitize_population_record_for_private_pilot(canary_population())
    alias = record["discovery"]["alias_transport_errors"][0]
    assert alias["requested"] == live.COMBO
    assert alias["error_class"] == "EmptyOutput"
    assert alias["error_sha256"] == pilot._sha256(
        f"no content; {POPULATION_CANARY_A}")
    assert alias["error_bytes"] == len(
        f"no content; {POPULATION_CANARY_A}".encode("utf-8"))

    transport, same = record["rejected_candidates"]
    assert transport["requested"] == "vendor/reject"
    assert transport["namespace"] == "vendor"
    assert transport["reason"] == "TRANSPORT"
    assert transport["error_class"] == "HTTPError"
    assert transport["error_sha256"] == pilot._sha256(
        f"HTTP 500 {POPULATION_CANARY_B}")
    assert transport["error_bytes"] == len(
        f"HTTP 500 {POPULATION_CANARY_B}".encode("utf-8"))
    assert same["requested"] == "vendor/same"
    assert same["reason"] == "SAME_REPORTED_MODEL_AS_ROLE_A"
    assert same["reported_model"] == ALIAS_MODEL
    assert "error_sha256" not in same

    assert record["selection_probes_used"] == 4
    assert record["membership_probes_used"] == 2
    assert [p["role"] for p in record["participants"]] == ["A", "B"]
    assert [p["requested"] for p in record["participants"]] == [
        live.COMBO, "vendor/comparator"]
    assert record["observed_members"] == [ALIAS_MODEL]
    assert record["catalog_digest"] == "sha256:" + "1" * 64
    assert record["selection_rule"] == pop.SELECTION_RULE
    assert record["replacement_policy"] == pop.REPLACEMENT_POLICY


def test_population_projection_audits_unlisted_nested_error_paths():
    """A3: an added diagnostic path cannot silently persist raw text."""
    record = pilot.sanitize_population_record_for_private_pilot(canary_population())
    future = record["discovery"]["future_probe"]
    assert future["error_sha256"] == pilot._sha256(POPULATION_CANARY_C)
    assert future["error_bytes"] == len(POPULATION_CANARY_C.encode("utf-8"))
    assert future["meta"][0]["body_sha256"] == pilot._sha256(
        POPULATION_CANARY_C + "_NESTED")
    assert future["meta"][0]["body_bytes"] == len(
        (POPULATION_CANARY_C + "_NESTED").encode("utf-8"))
    joined = serialized_text(record)
    assert POPULATION_CANARY_C not in joined
    assert POPULATION_CANARY_C + "_NESTED" not in joined


def population_canary_run(tmp_path, frozen, real_built, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(pilot, "sanitize_population_record_for_private_pilot",
                            lambda population: population.as_record())
    return combined_canary_run(tmp_path, frozen, real_built,
                               population=canary_population())


def test_artifact_population_section_is_the_sanitized_projection(
        tmp_path, frozen, real_built):
    result, _transport, _candidate = population_canary_run(tmp_path, frozen, real_built)
    document = json.loads(strip_and_read(result["artifact"]))
    assert document["population_projection"] == pilot.POPULATION_PROJECTION_VERSION
    population = document["population"]
    for canary in POPULATION_CANARIES:
        assert canary not in serialized_text(population)
    assert population["discovery"]["alias_transport_errors"][0]["error_class"] == (
        "EmptyOutput")
    assert population["rejected_candidates"][0]["reason"] == "TRANSPORT"
    assert population["rejected_candidates"][1]["reason"] == (
        "SAME_REPORTED_MODEL_AS_ROLE_A")


def test_artifact_report_and_interpretation_hold_no_population_canary(
        tmp_path, frozen, real_built):
    result, _transport, _candidate = population_canary_run(tmp_path, frozen, real_built)
    document = json.loads(strip_and_read(result["artifact"]))
    assert all(canary not in serialized_text(document)
               for canary in POPULATION_CANARIES)
    for path in (result["report"], result["interpretation"]):
        text = strip_and_read(path)
        for canary in POPULATION_CANARIES:
            assert canary not in text


def test_privacy_claim_is_coupled_to_structural_reality(tmp_path, frozen, real_built):
    """B6: the declared boolean is proven by a scan, not trusted by itself."""
    result, _transport, _candidate = population_canary_run(tmp_path, frozen, real_built)
    document = json.loads(strip_and_read(result["artifact"]))
    assert document["plaintext_retention"]["provider_error_bodies"] is False
    assert document["plaintext_retention"]["only_hashes_lengths_and_metadata"] is True
    assert not any(canary in serialized_text(document)
                   for canary in POPULATION_CANARIES)


def test_broken_projection_control_makes_the_claim_false(
        tmp_path, frozen, real_built, monkeypatch):
    """Instrument control: with the boundary removed, the coupling test goes red."""
    result, _transport, _candidate = population_canary_run(
        tmp_path, frozen, real_built, monkeypatch=monkeypatch)
    text = strip_and_read(result["artifact"])
    document = json.loads(text)
    assert document["plaintext_retention"]["provider_error_bodies"] is False
    assert POPULATION_CANARY_A in text
    assert POPULATION_CANARY_B in text


def test_historical_t69_files_are_byte_identical():
    """RED-4 / matrix 21..23: the historical correction rewrites nothing."""
    assert file_sha256(HISTORICAL_ARTIFACT) == HISTORICAL_ARTIFACT_SHA256
    assert file_sha256(HISTORICAL_REPORT) == HISTORICAL_REPORT_SHA256
    assert file_sha256(HISTORICAL_INTERPRETATION) == HISTORICAL_INTERPRETATION_SHA256


def test_privacy_correction_note_is_additive_and_states_the_contract():
    assert PRIVACY_CORRECTION_NOTE.is_file()
    text = PRIVACY_CORRECTION_NOTE.read_text(encoding="utf-8")
    lowered = text.lower()
    for statement in ("t-69", "provider_error_bodies = false", "too broad",
                      "b-018 corpus content", "discovery happened before",
                      "sanitized population projection", "unchanged"):
        assert statement in lowered, statement
    for raw in ("Individual quota reached", "access_denied", "Deposit required",
                "empty response content"):
        assert raw not in text, raw
