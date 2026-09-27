"""LAB live adapters: strict parsing, one call per logical call, recorded stages."""

import hashlib
import json
from pathlib import Path

import pytest

from lab import ally_generation_live as l
from lab import ally_generation_scenarios as sc
from lab import saifren_population as pop
from lab import saifren_run as live
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag

ALIAS_MODEL = "alias-model"
EXTERNAL_MODEL = "ext/comp-model"


def wire_candidate(advice: aa.AllyAdvice) -> str:
    return json.dumps({
        "result": "CANDIDATE",
        "WORK_CONTEXT": advice.work_context,
        "OBSERVED_SCOPE": advice.observed_scope,
        "OBSERVED": [{"STATEMENT": o.statement, "EVIDENCE_REFS": list(o.evidence_refs)}
                     for o in advice.observed],
        "INFERRED": advice.inferred,
        "GUIDANCE_MODE": advice.guidance_mode,
        "SUGGESTED": advice.suggested,
        "COUNTEREVIDENCE": [{"STATEMENT": c.statement, "EVIDENCE_REFS": list(c.evidence_refs)}
                            for c in advice.counterevidence],
        "UNCERTAINTY": advice.uncertainty,
    })


def wire_review(candidate: aa.AllyAdvice, corpus: ag.ReflectionCorpus,
                overrides=None) -> str:
    overrides = overrides or {}
    fallback = sc.candidate_refs(candidate)[:1] or (corpus.items[0].evidence_ref,)
    dimensions = []
    for dimension in ag.DIMENSIONS:
        verdict = overrides.get(dimension, ag.PASS)
        refs = list(fallback) if (dimension in ag.EVIDENCE_REQUIRED_DIMENSIONS
                                  and verdict == ag.PASS) else []
        dimensions.append({"dimension": dimension, "verdict": verdict,
                           "rationale": f"{dimension} test rationale.",
                           "evidence_refs": refs})
    return json.dumps({
        "candidate_id": ag.ally_candidate_id(candidate),
        "corpus_id": corpus.corpus_id,
        "rubric_version": ag.RUBRIC_VERSION,
        "dimensions": dimensions,
    })


def ok(output: str, model: str) -> dict:
    return {"output": output, "reported_model": model, "provider": None,
            "provider_basis": "NOT_EXPOSED", "finish_reason": "stop",
            "usage": {"prompt_tokens": 12, "completion_tokens": 7, "total_tokens": 19},
            "latency_s": 0.01, "http_status": 200}


def transport_error() -> dict:
    return {"error_class": "HTTPError", "error": "HTTP 500 upstream", "http_status": 500,
            "latency_s": 0.01}


def runner_with(send, cap=sc.MAX_CALLS):
    return live.Runner(send, live.CallBudget(cap), alias=live.COMBO)


def make_dispatch(send, log=None, cap=sc.MAX_CALLS):
    log = log or l.CallLog()
    return l.Dispatch(runner_with(send, cap), log), log


def fake_population(reported=(ALIAS_MODEL, EXTERNAL_MODEL)):
    population = pop.Population(
        combo=live.COMBO, observed_at=live._now(),
        membership_source=pop.COMBO_ALIAS_SAMPLE, roster_status=pop.ROSTER_NOT_EXPOSED)
    population.participants = (
        pop.Participant(role="A", requested=live.COMBO, reported_model=reported[0],
                        member_status=pop.OBSERVED_COMBO_MEMBER, source="COMBO_ALIAS"),
        pop.Participant(role="B", requested="vendor/comparator", reported_model=reported[1],
                        member_status=pop.NOT_PROVEN_COMBO_MEMBER,
                        source="CATALOG_ELIGIBLE"),
    )
    return population


class ScriptedTransport:
    """Prompt-matched fake gateway; records every dispatch for one-call proofs."""

    def __init__(self, handler):
        self.handler = handler
        self.sends = []

    def send(self, prompt, model=None):
        self.sends.append({"prompt": prompt, "model": model})
        return self.handler(prompt, model)


def default_handler(prompt: str, model: str):
    reported = ALIAS_MODEL if model == live.COMBO else EXTERNAL_MODEL
    if "bounded ALLY_ADVICE generator" in prompt:
        markers = {"G1": sc.fixture_ref("G1.p1"), "G2": sc.fixture_ref("G2.a1"),
                   "G3": sc.fixture_ref("G3.s1"), "G4": sc.fixture_ref("G4.q1")}
        code = next(c for c, marker in markers.items() if marker in prompt)
        payload = sc.fixture_candidate(code)
        return ok(json.dumps({"result": "NO_ADVICE"}) if payload is None
                  else wire_candidate(payload), reported)
    overrides = {}
    if sc.fixture_ref("G3.s1") in prompt:
        overrides[ag.COUNTEREVIDENCE_ADEQUACY] = ag.FAIL
    if sc.fixture_ref("G4.q1") in prompt:
        overrides[ag.SCOPE_DISCIPLINE] = ag.FAIL
    catalog = {
        ag.ally_candidate_id(sc.fixture_candidate(sc.G1)): (sc.fixture_candidate(sc.G1),
                                                            sc.corpus_for(sc.G1)),
        ag.ally_candidate_id(sc.fixture_candidate(sc.G3)): (sc.fixture_candidate(sc.G3),
                                                            sc.corpus_for(sc.G3)),
        ag.ally_candidate_id(sc.fixture_candidate(sc.G4)): (sc.fixture_candidate(sc.G4),
                                                            sc.corpus_for(sc.G4)),
    }
    for code in sc.CONTROL_CODES:
        candidate, dimension = sc.control_candidate(code)
        catalog[ag.ally_candidate_id(candidate)] = (candidate, sc.control_corpus(),
                                                    {dimension: ag.FAIL})
    for candidate_id, entry in catalog.items():
        candidate, corpus = entry[0], entry[1]
        if candidate_id in prompt:
            extra = entry[2] if len(entry) > 2 else {}
            return ok(wire_review(candidate, corpus, {**overrides, **extra}), reported)
    raise AssertionError("reviewer prompt matched no registered candidate")


# ------------------------------------------------------------------- parsing


def test_parse_generator_no_advice_and_candidate():
    assert l.parse_generator_output('{"result":"NO_ADVICE"}').kind == ag.NO_ADVICE
    advice = sc.fixture_candidate(sc.G1)
    result = l.parse_generator_output(wire_candidate(advice))
    assert result.kind == ag.CANDIDATE
    assert result.candidate.render() == advice.render()


@pytest.mark.parametrize("text", [
    '{"result":"NO_ADVICE","extra":1}',
    '{"result":"NO_ADVICE","result":"NO_ADVICE"}',
    '{"result":"MAYBE"}',
    '{"result":',
    'prose {"result":"NO_ADVICE"}',
    '[]',
    "{}",
])
def test_parse_generator_refusals(text):
    with pytest.raises(SailangError):
        l.parse_generator_output(text)


def test_parse_generator_refuses_noncanonical_ref_order():
    ordered = sorted([sc.fixture_ref("G1.p1"), sc.fixture_ref("G1.p3")])
    bad = json.dumps({
        "result": "CANDIDATE", "WORK_CONTEXT": "w", "OBSERVED_SCOPE": sc.SCOPE,
        "OBSERVED": [
            {"STATEMENT": "a", "EVIDENCE_REFS": list(reversed(ordered))},
            {"STATEMENT": "b", "EVIDENCE_REFS": [sc.fixture_ref("G1.p2")]},
        ],
        "INFERRED": "i", "GUIDANCE_MODE": "CONSIDER_CHANGE", "SUGGESTED": "s",
        "COUNTEREVIDENCE": [{"STATEMENT": "c",
                             "EVIDENCE_REFS": [sc.fixture_ref("G1.c1")]}],
        "UNCERTAINTY": "u",
    })
    with pytest.raises(SailangError):
        l.parse_generator_output(bad)


def test_parse_generator_refuses_bad_guidance_mode():
    advice = sc.fixture_candidate(sc.G1)
    payload = json.loads(wire_candidate(advice))
    payload["GUIDANCE_MODE"] = "REQUIRED"
    with pytest.raises(SailangError):
        l.parse_generator_output(json.dumps(payload))


def test_parse_reviewer_roundtrip_and_refusals():
    candidate = sc.fixture_candidate(sc.G1)
    corpus = sc.corpus_for(sc.G1)
    report = l.parse_reviewer_output(wire_review(candidate, corpus), candidate, corpus)
    assert report.verdict_for(ag.OBSERVATION_SUPPORT) == ag.PASS
    wrong_candidate = sc.fixture_candidate(sc.G3)
    with pytest.raises(SailangError):
        l.parse_reviewer_output(wire_review(candidate, corpus), wrong_candidate, corpus)
    payload = json.loads(wire_review(candidate, corpus))
    payload["dimensions"] = payload["dimensions"][:-1]
    with pytest.raises(SailangError):
        l.parse_reviewer_output(json.dumps(payload), candidate, corpus)
    payload = json.loads(wire_review(candidate, corpus))
    payload["dimensions"][0]["verdict"] = "OK"
    with pytest.raises(SailangError):
        l.parse_reviewer_output(json.dumps(payload), candidate, corpus)
    with pytest.raises(SailangError):
        l.parse_reviewer_output("not json", candidate, corpus)


def test_reviewer_pass_without_refs_refuses():
    candidate = sc.fixture_candidate(sc.G1)
    corpus = sc.corpus_for(sc.G1)
    payload = json.loads(wire_review(candidate, corpus))
    payload["dimensions"][0]["evidence_refs"] = []
    with pytest.raises(SailangError):
        l.parse_reviewer_output(json.dumps(payload), candidate, corpus)


# ------------------------------------------------------------------ adapters


def counting_reviewer(report_factory):
    class Counting:
        calls = 0

        def review(self, evidence_resolved_advice, corpus):
            self.calls += 1
            return report_factory(evidence_resolved_advice, corpus)
    return Counting()


def passing_report_factory(evidence_resolved_advice, corpus):
    return l.parse_reviewer_output(
        wire_review(evidence_resolved_advice.advice, corpus),
        evidence_resolved_advice.advice, corpus)


def test_generator_transport_error_single_call_and_no_retry():
    calls = {"n": 0}

    def send(prompt, model=None):
        calls["n"] += 1
        return transport_error()

    dispatch, log = make_dispatch(send)
    generator = l.LabGenerator(dispatch, unit_id="G1.r1", replicate=1, role="A",
                               requested=live.COMBO)
    with pytest.raises(SailangError) as excinfo:
        generator.generate(sc.corpus_for(sc.G1))
    assert excinfo.value.code == l.ALLY_LAB_GENERATOR_TRANSPORT
    assert calls["n"] == 1
    assert generator.transport_status == sc.STAGE_ERROR
    assert len(log.records) == 1


def test_generator_schema_error_records_and_does_not_retry():
    calls = {"n": 0}

    def send(prompt, model=None):
        calls["n"] += 1
        return ok("{bad json", ALIAS_MODEL)

    dispatch, _ = make_dispatch(send)
    generator = l.LabGenerator(dispatch, unit_id="G1.r1", replicate=1, role="A",
                               requested=live.COMBO)
    with pytest.raises(SailangError):
        generator.generate(sc.corpus_for(sc.G1))
    assert generator.parse_status == sc.STAGE_SCHEMA_ERROR
    assert calls["n"] == 1


def test_no_advice_spends_zero_reviewer_calls():
    corpus = sc.corpus_for(sc.G2)

    def send(prompt, model=None):
        return ok('{"result":"NO_ADVICE"}', ALIAS_MODEL)

    dispatch, log = make_dispatch(send)
    generator = l.LabGenerator(dispatch, unit_id="G2.r1", replicate=1, role="A",
                               requested=live.COMBO)
    reviewer = counting_reviewer(passing_report_factory)
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
    assert outcome.status == ag.NO_ADVICE
    assert reviewer.calls == 0
    assert len(log.records) == 1


def test_outside_corpus_ref_reaches_zero_reviewer_calls():
    corpus = sc.corpus_for(sc.G1)

    def send(prompt, model=None):
        return ok(wire_candidate(sc.fixture_candidate(sc.G3)), ALIAS_MODEL)

    dispatch, _log = make_dispatch(send)
    generator = l.LabGenerator(dispatch, unit_id="G1.r1", replicate=1, role="A",
                               requested=live.COMBO)
    reviewer = counting_reviewer(passing_report_factory)
    outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert reviewer.calls == 0
    assert generator.ref_gate == sc.STAGE_FAIL


def test_reviewer_invalid_json_no_retry():
    calls = {"n": 0}

    def send(prompt, model=None):
        calls["n"] += 1
        return ok("{nope", EXTERNAL_MODEL)

    dispatch, _ = make_dispatch(send)
    reviewer = l.LabReviewer(dispatch, unit_id="G1.r1", replicate=1, role="B",
                             requested="vendor/comparator")
    corpus = sc.corpus_for(sc.G1)
    resolved = aa.resolve_ally_evidence(sc.fixture_candidate(sc.G1),
                                        ag.CorpusEvidenceResolver(corpus))
    with pytest.raises(SailangError):
        ag.run_semantic_review(resolved, corpus, reviewer)
    assert reviewer.parse_status == sc.STAGE_SCHEMA_ERROR
    assert calls["n"] == 1


# ----------------------------------------------------------------- full runs


def live_run(tmp_path, handler=default_handler, population=None, **kwargs):
    transport = ScriptedTransport(handler)
    result = l.run(tmp_path / "out", False, transport=transport,
                   population=population or fake_population(), update_latest=False,
                   registration_path=kwargs.pop("registration_path", register_in(tmp_path)),
                   **kwargs)
    return result, transport


def register_in(tmp_path: Path) -> Path:
    path = tmp_path / "ally_generation_registration.json"
    if not path.exists():
        l.register(path, {"ticket": "T-63", "source_receipt": "SRC-047"})
    return path


def test_full_fake_run_artifact_counts_and_calls(tmp_path):
    result, transport = live_run(tmp_path)
    assert len(transport.sends) == result["live_calls"] == 20
    assert result["status"] == l.STATUS_COMPLETED
    counts = result["counts"]
    assert counts["generator_attempts"] == 8
    assert counts["no_advice"] == 2
    assert counts["candidates"] == 6
    assert counts["final_outcomes"] == {"NO_ADVICE": 2, "APPROVED": 2, "REJECTED": 4,
                                        "ERROR": 0}
    assert counts["false_pattern_candidates"] == 0
    assert counts["scope_widening"] == 2
    assert counts["missed_registered_counterevidence"] == 2
    assert counts["review_controls"]["R1"][sc.CONTROL_DETECTED] == 2
    assert result["registration"]["digest"] == sc.digest(sc.registration())
    assert result["artifact"].endswith(".json")
    assert result["report"]
    functions = {}
    for call in result["calls"]:
        functions[call["function"]] = functions.get(call["function"], 0) + 1
    assert functions["GENERATOR"] == 8
    assert functions["REVIEWER"] == 2 + 4 + 6
    assert result["live_calls"] == 20
    assert all(call["prompt_sha256"] for call in result["calls"])
    assert all("prompt" not in call for call in result["calls"])
    Path(result["artifact"]).read_text(encoding="utf-8")


def test_full_fake_run_keeps_credential_out(tmp_path):
    result, _ = live_run(tmp_path)
    text = Path(result["artifact"]).read_text(encoding="utf-8")
    assert "Bearer" not in text
    assert "authorization" not in text.lower()
    assert result["credential"]["backend"] is None


def test_raw_output_is_bounded(tmp_path):
    long_no_advice = json.dumps({"result": "NO_ADVICE"}) + " " * 6000

    def handler(prompt, model):
        reported = ALIAS_MODEL if model == live.COMBO else EXTERNAL_MODEL
        if "bounded ALLY_ADVICE generator" in prompt:
            return ok(long_no_advice, reported)
        return default_handler(prompt, model)

    result, _ = live_run(tmp_path, handler=handler)
    generators = [call for call in result["calls"] if call["function"] == "GENERATOR"]
    assert len(generators) == 8
    assert all(len(call["visible_output"]) == 4000 for call in generators)
    assert result["counts"]["no_advice"] == 8


def test_report_has_no_winner_or_score_field(tmp_path):
    result, _ = live_run(tmp_path)
    report = Path(result["report"]).read_text(encoding="utf-8")
    assert "WHAT THIS RUN DOES NOT SHOW" in report
    for token in sc.REPORT_FORBIDDEN_KEYS:
        assert token not in report.lower()


def test_transport_error_recorded_without_retry(tmp_path):
    state = {"g1_generator_calls": 0}

    def handler(prompt, model):
        if "bounded ALLY_ADVICE generator" in prompt and sc.fixture_ref("G1.p1") in prompt:
            state["g1_generator_calls"] += 1
            if state["g1_generator_calls"] == 1:
                return transport_error()
        return default_handler(prompt, model)

    result, _ = live_run(tmp_path, handler=handler)
    unit = next(u for u in result["units"] if u["unit_id"] == "G1.r1")
    assert unit["stages"]["GENERATOR_TRANSPORT"] == sc.STAGE_ERROR
    assert unit["outcome"]["code"] == ag.ALLY_GEN_PROVIDER_ERROR
    assert state["g1_generator_calls"] == 2


# ------------------------------------------------------------ T-64 TARGET A

HISTORICAL_RUN_ID = "20260919T201826Z_2a73d98de110453a"
HISTORICAL_ARTIFACT_SHA256 = (
    "29dbb415f0fd3c5aa86e450db59b1afea0ea2acb3847747e032d35136c920ca2"
)
HISTORICAL_REPORT_SHA256 = (
    "d56267a875899e09f0836b21d24a914b097aac13971bd8e99755bd2f5883c9ab"
)


def test_discovery_probe_success_without_status_key_records_ok():
    record = l._discovery_probe_record("model-X", ok("OK", "model-X"))
    assert record["status"] == "OK"
    assert record["error_class"] is None
    assert record["http_status"] == 200
    assert record["reported_model"] == "model-X"
    assert record["visible_output"] == "OK"


def test_discovery_probe_transport_error_records_error():
    record = l._discovery_probe_record("model-X", transport_error())
    assert record["status"] == "ERROR"
    assert record["error_class"] == "HTTPError"
    marked = l._discovery_probe_record(
        "model-X", {"output": None, "status": "ERROR", "error_class": None,
                    "http_status": None})
    assert marked["status"] == "ERROR"


def test_discovery_probe_non_success_http_cannot_record_ok():
    result = {"output": "OK", "reported_model": "model-X", "error_class": None,
              "http_status": 500, "latency_s": 0.01}
    record = l._discovery_probe_record("model-X", result)
    assert record["status"] == "ERROR"


def test_historical_t63_artifact_and_report_are_untouched():
    out = Path(__file__).resolve().parent.parent / "lab" / "out"
    artifact = out / f"ally_generation_live_{HISTORICAL_RUN_ID}.json"
    report = out / f"ALLY_GENERATION_REPORT_{HISTORICAL_RUN_ID}.md"
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == HISTORICAL_ARTIFACT_SHA256
    assert hashlib.sha256(report.read_bytes()).hexdigest() == HISTORICAL_REPORT_SHA256


def test_review_fail_does_not_trigger_second_generation(tmp_path):
    state = {"g3_gen": 0}

    def handler(prompt, model):
        if "bounded ALLY_ADVICE generator" in prompt and sc.fixture_ref("G3.s1") in prompt:
            state["g3_gen"] += 1
        return default_handler(prompt, model)

    result, _ = live_run(tmp_path, handler=handler)
    rejected = [u for u in result["units"]
                if u["unit_id"].startswith("G3")
                and u["measurement"]["final_gate_outcome"] == ag.REJECTED]
    assert len(rejected) == 2
    assert state["g3_gen"] == 2
    for unit in rejected:
        assert unit["measurement"]["reviewer_verdicts"][ag.COUNTEREVIDENCE_ADEQUACY] \
            == ag.FAIL
    assert result["counts"]["no_advice"] == 2


def test_false_pattern_candidate_is_labelled(tmp_path):
    fabricated = fake_repeated_incident()
    fabricated_id = ag.ally_candidate_id(fabricated)

    def handler(prompt, model):
        reported = ALIAS_MODEL if model == live.COMBO else EXTERNAL_MODEL
        if "bounded ALLY_ADVICE generator" in prompt and sc.fixture_ref("G2.a1") in prompt:
            return ok(wire_candidate(fabricated), reported)
        if fabricated_id in prompt:
            return ok(wire_review(fabricated, sc.corpus_for(sc.G2)), reported)
        return default_handler(prompt, model)

    result, _ = live_run(tmp_path, handler=handler)
    g2 = [u for u in result["units"] if u["scenario"] == sc.G2]
    assert all(u["measurement"]["false_pattern_candidate"] for u in g2)
    assert result["counts"]["false_pattern_candidates"] == 2
    # Post-correction: the one-incident candidate is refused by the structural
    # distinct-event floor before any reviewer invocation (RED-B).
    assert all(u["outcome"]["code"] == ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS
               for u in g2)
    assert all(u["stages"]["EVENT_FLOOR_GATE"] == sc.STAGE_FAIL for u in g2)
    assert all(u["stages"]["REVIEWER_TRANSPORT"] == sc.STAGE_NOT_REACHED for u in g2)
    assert all(u["stages"]["SEMANTIC_REVIEW"] == sc.STAGE_SKIPPED for u in g2)
    assert all(u["measurement"]["final_gate_outcome"] == ag.REJECTED for u in g2)
    assert not [call for call in result["calls"]
                if call["unit_id"].startswith("G2.") and call["function"] == "REVIEWER"]


def fake_repeated_incident() -> aa.AllyAdvice:
    refs = (sc.fixture_ref("G2.a1"), sc.fixture_ref("G2.a2"), sc.fixture_ref("G2.a3"))
    return aa.AllyAdvice(
        created=sc.CREATED, work_context="Synthetic false-pattern probe.",
        observed_scope=sc.SCOPE,
        observed=(
            aa.AdviceObservation("The stall was repeated in three artifacts.",
                                 (refs[0],)),
            aa.AdviceObservation("The same stall appears again in another artifact.",
                                 (refs[1],)),
            aa.AdviceObservation("A third artifact shows the same stall once more.",
                                 (refs[2],)),
        ),
        inferred="The three artifacts may describe a recurring stall.",
        guidance_mode=aa.CONSIDER_CHANGE,
        suggested="Consider one stall review.",
        counterevidence=(aa.AdviceCounterevidence("The artifacts share one incident.",
                                                  (refs[2],)),),
        uncertainty="Three artifacts of one incident; the sample is bounded.")


def test_no_go_population_starts_no_scenario_call(tmp_path):
    population = fake_population()
    population.participants = population.participants[:1]
    result, transport = live_run(tmp_path, population=population)
    assert result["status"] == sc.NO_GO_POPULATION
    assert transport.sends == []
    assert result["counts"]["generator_attempts"] == 0


def test_credential_unavailable_is_declared(tmp_path, monkeypatch):
    def refuse(**kwargs):
        raise l.CredentialNotProvisioned("no credential provisioned")

    monkeypatch.setattr(l, "resolve", refuse)
    result = l.run(tmp_path / "out", False, registration_path=register_in(tmp_path),
                   update_latest=False)
    assert result["status"] == sc.LIVE_NOT_RUN_CREDENTIAL_UNAVAILABLE
    assert result["live_calls"] == 0
    Path(result["artifact"]).read_text(encoding="utf-8")


def test_planned_budget_over_ceiling_refuses(tmp_path, monkeypatch):
    register_in(tmp_path)
    monkeypatch.setattr(sc, "MAX_CALLS", 29)
    with pytest.raises(SystemExit):
        l._budget_check()
