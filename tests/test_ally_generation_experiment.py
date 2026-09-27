"""Registered experiment plan: freeze identity, dry-run proofs, no durable paths."""

import hashlib
import json
import re
from pathlib import Path

import pytest

from lab import ally_generation_live as l
from lab import ally_generation_scenarios as sc
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag

REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

#: The frozen T-63 registration is historical evidence; the plan in code has
#: since gained EVENT_REF, so the old bytes both must stay untouched and must
#: refuse if presented as the new subject.
HISTORICAL_REGISTRATION_SHA256 = (
    "935fdd3f74675126e70a88641d3c976939cb9ad6f3aa2d631b86ccb3764c879f"
)

PRIVATE_PATH_TOKENS = (
    "reviewed_ally_to_human_private",
    "seal_human_private(",
    "HumanPrivateStore(",
    "admit_receiver_candidate",
)


def registered(tmp_path: Path) -> Path:
    path = tmp_path / sc.REGISTRATION_FILE
    l.register(path, sc.expected_registered_under())
    return path


def test_registration_digest_is_deterministic():
    first = json.dumps(sc.registration(), sort_keys=True)
    second = json.dumps(sc.registration(), sort_keys=True)
    assert first == second
    assert sc.digest(sc.registration()).startswith("sha256:")


def test_registration_file_roundtrip_and_expected_identity(tmp_path):
    path = registered(tmp_path)
    checked = l.check_registration(path)
    assert checked["digest"] == sc.digest(sc.registration())
    assert checked["registered_under"] == sc.expected_registered_under()
    with pytest.raises(l.RegistrationMismatch):
        l.check_registration(path, expected_registration_id="sha256:" + "0" * 64)


def test_registration_mutation_after_freeze_refuses(tmp_path):
    path = registered(tmp_path)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["registration"]["budget"]["max_calls"] = 99
    path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    with pytest.raises(l.RegistrationMismatch):
        l.check_registration(path)


def test_registration_missing_refuses(tmp_path):
    with pytest.raises(l.RegistrationMismatch):
        l.check_registration(tmp_path / "absent.json")


def test_planned_budget_is_the_declared_ceiling():
    planned = sc.DISCOVERY_RESERVE + sc.GENERATION_CALLS_MAX + sc.CONTROL_CALLS_MAX
    assert planned == sc.MAX_CALLS == 30
    registration = sc.registration()
    assert registration["budget"]["max_calls"] == sc.MAX_CALLS
    assert registration["budget"]["discovery_reserve"] == sc.DISCOVERY_RESERVE
    assert len(registration["scenarios"]) == 4
    assert len(registration["review_controls"]) == 3


def test_all_scenarios_build_valid_corpora():
    for code in sc.SCENARIO_CODES:
        corpus = sc.corpus_for(code)
        assert isinstance(corpus, ag.ReflectionCorpus)
        assert 3 <= len(corpus.items) <= ag.MAX_ITEMS
        for entry in corpus.items:
            assert REF_RE.fullmatch(entry.evidence_ref)
            assert entry.source_domain == ag.PROJECT_OPERATIONAL
            assert entry.observed_scope == sc.SCOPE
    assert all(entry.observed_scope == sc.SCOPE
               for entry in sc.corpus_for(sc.G4).items)


def test_registered_scenario_refs_are_in_the_corpora():
    g1 = sc.corpus_for(sc.G1)
    assert g1.item_for(sc.G1_COUNTEREXAMPLE_REF) is not None
    g2 = sc.corpus_for(sc.G2)
    assert all(g2.item_for(ref) is not None for ref in sc.G2_INCIDENT_REFS)
    assert len(set(sc.G2_INCIDENT_REFS)) == 3
    g3 = sc.corpus_for(sc.G3)
    assert all(g3.item_for(ref) is not None for ref in sc.G3_WEAKENING_REFS)
    assert len(set(sc.G3_WEAKENING_REFS)) == 3
    assert sc.PERMITTED_SCOPE == sc.SCOPE


def test_controls_are_valid_b012_objects_and_registered():
    registered_controls = {row["code"]: row for row in sc.control_registration()}
    for code in sc.CONTROL_CODES:
        candidate, dimension = sc.control_candidate(code)
        assert isinstance(candidate, aa.AllyAdvice)
        assert aa.AllyAdvice.parse(candidate.render()).render() == candidate.render()
        assert ag.ally_candidate_id(candidate) == registered_controls[code]["candidate_id"]
        assert dimension == registered_controls[code]["expected_dimension"]
    assert registered_controls["R1"]["expected_dimension"] == ag.NO_MOTIVE_INFERENCE
    assert registered_controls["R2"]["expected_dimension"] == ag.NO_FLATTERY
    assert registered_controls["R3"]["expected_dimension"] == ag.NO_COMPLIANCE_PRESSURE


def test_dry_run_is_network_free_and_provable(tmp_path, monkeypatch):
    def explode(**kwargs):
        raise AssertionError("a dry run must not resolve a credential")

    monkeypatch.setattr(l, "resolve", explode)
    path = registered(tmp_path)
    out = tmp_path / "out"
    result = l.run(out, True, registration_path=path, update_latest=False)
    assert result["status"] == "DRY_RUN"
    assert result["live_calls"] == 0
    assert result["calls"] == []
    assert result["experiment_class"]["experiment_class"] == "NOT_MEASURED"
    assert sorted(p.name for p in out.iterdir()) == ["ally_generation_dry_run.json"]
    units = {unit["unit_id"]: unit for unit in result["units"]}
    assert units["G2.r1"]["reviewer_calls"] == 0
    assert units["G2.r2"]["reviewer_calls"] == 0
    assert units["G3.r1"]["reviewer_calls"] == 1
    assert units["G3.r1"]["measurement"]["final_gate_outcome"] == ag.REJECTED
    assert units["G1.r1"]["generator"]["role"] == "A"
    assert units["G1.r2"]["generator"]["role"] == "B"
    assert len(result["review_controls"]) == 6
    assert all(row["outcome"] == sc.CONTROL_DETECTED for row in result["review_controls"])
    artifact = json.loads(Path(result["artifact"]).read_text(encoding="utf-8"))
    assert artifact["dry_run"] is True


def test_dry_run_report_renders_without_forbidden_fields(tmp_path):
    path = registered(tmp_path)
    result = l.run(tmp_path / "out", True, registration_path=path, update_latest=False)
    report = l.render(result)
    assert "REGISTRATION" in report
    assert "WHAT THIS RUN DOES NOT SHOW" in report
    for token in sc.REPORT_FORBIDDEN_KEYS:
        assert token not in report.lower()


def test_live_runner_has_no_durable_private_path():
    source = Path(l.__file__).read_text(encoding="utf-8")
    for token in PRIVATE_PATH_TOKENS:
        assert token not in source


def test_latest_index_update_is_additive(tmp_path):
    path = registered(tmp_path)
    result = l.run(tmp_path / "out", True, registration_path=path, update_latest=False)
    index = tmp_path / "LATEST.md"
    l.update_latest_index(index, result, "ally_generation_live_x.json", "stamp1")
    l.update_latest_index(index, result, "ally_generation_live_y.json", "stamp2")
    text = index.read_text(encoding="utf-8")
    assert text.count("## ALLY_ADVICE live generation experiment (T-63)") == 2
    assert "ally_generation_live_x.json" in text
    assert "ally_generation_live_y.json" in text


def test_mechanical_measurements_do_not_call_a_grader():
    candidate = sc.fixture_candidate(sc.G1)
    measured = sc.measure(sc.G1, candidate, {ag.OBSERVATION_SUPPORT: ag.PASS}, ag.APPROVED)
    assert measured["counterexample_ref_cited"] is True
    assert measured["permitted_scope_retained"] is True
    widened = sc.measure(sc.G4, sc.fixture_candidate(sc.G4), {}, ag.REJECTED)
    assert widened["scope_widened"] is True
    missed = sc.measure(sc.G3, sc.fixture_candidate(sc.G3), {}, ag.REJECTED)
    assert missed["missed_registered_counterevidence"] is True


def test_prompt_templates_registered_by_digest():
    registration = sc.registration()
    assert registration["prompts"]["generator_template_sha256"] == l._sha256(
        sc.GENERATOR_TEMPLATE)
    assert registration["prompts"]["reviewer_template_sha256"] == l._sha256(
        sc.REVIEWER_TEMPLATE)
    prompt = sc.generator_prompt(sc.corpus_for(sc.G1))
    assert "NO_ADVICE is a valid" in prompt
    assert "Do not output reasoning" in prompt
    assert sc.G1_COUNTEREXAMPLE_REF in prompt


def test_control_candidate_parse_refuses_after_mutation():
    candidate, _ = sc.control_candidate("R3")
    with pytest.raises(SailangError):
        aa.AllyAdvice(
            created=candidate.created, work_context=candidate.work_context,
            observed_scope=candidate.observed_scope, observed=candidate.observed,
            inferred=candidate.inferred, guidance_mode=candidate.guidance_mode,
            suggested=candidate.suggested, counterevidence=candidate.counterevidence,
            uncertainty=candidate.uncertainty, guidance_status="REQUIRED")


def test_every_fixture_item_declares_a_canonical_event_ref():
    corpora = [sc.corpus_for(code) for code in sc.SCENARIO_CODES] + [sc.control_corpus()]
    for corpus in corpora:
        for entry in corpus.items:
            assert REF_RE.fullmatch(entry.event_ref), entry.evidence_ref
    # The historical G2 topology is ONE incident's three artifacts: one event.
    assert len(sc.corpus_for(sc.G2).event_refs_for(sc.G2_INCIDENT_REFS)) == 1
    # Repeated-pattern fixtures intentionally span more than one declared event.
    for code, refs in (
        (sc.G1, (sc.fixture_ref("G1.p1"), sc.fixture_ref("G1.p2"),
                 sc.fixture_ref("G1.p3"))),
        (sc.G3, (sc.fixture_ref("G3.s1"), sc.fixture_ref("G3.s2"),
                 sc.fixture_ref("G3.s3"))),
    ):
        assert len(sc.corpus_for(code).event_refs_for(refs)) >= 2, code


def test_prompts_expose_event_grouping():
    corpus = sc.corpus_for(sc.G1)
    generator = sc.generator_prompt(corpus)
    assert "at least two distinct" in generator
    assert "Artifact count is not event count" in generator
    assert all(entry.event_ref in generator for entry in corpus.items)
    reviewer = sc.reviewer_prompt(sc.fixture_candidate(sc.G1), corpus)
    assert "count as ONE underlying declared event" in reviewer
    assert "never claim this review proves" in reviewer
    assert all(entry.event_ref in reviewer for entry in corpus.items)
    assert "score" not in sc.REVIEWER_TEMPLATE.lower()


def test_registration_schema_includes_event_ref_capability():
    registration = sc.registration()
    assert registration["registration_version"] == sc.REGISTRATION_VERSION == 2
    for row in registration["scenarios"]:
        assert row["items"], row["code"]
        assert all("event_ref" in entry for entry in row["items"]), row["code"]
    assert "EVENT_REF" in registration["prompts"]["corpus_render"]
    assert "ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS" in (
        registration["grading"]["distinct_event_floor_rule"])


def test_historical_registration_is_frozen_and_refuses_as_the_new_subject():
    path = Path(l.__file__).resolve().parent / sc.REGISTRATION_FILE
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == HISTORICAL_REGISTRATION_SHA256
    with pytest.raises(l.RegistrationMismatch):
        l.check_registration(path)
