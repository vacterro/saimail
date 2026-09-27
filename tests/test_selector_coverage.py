"""V2-02 / T-88: preregistered selector-coverage experiment harness.

Offline only: deterministic fixtures, temp roots, no provider and no network.
The point of these tests is that a *negative* result is admissible evidence, so
the harness must not be able to quietly turn a safety failure into a saving.

Covered here: preregistration identity, the historical/current separation of the
manifest, preflight refusal on input or implementation drift, byte-identical
paired arms, truth-blind policy, the non-downgradable machine floor, independent
false-ignore/missed-relevant accounting, friction inadmissibility on an unsafe
arm, zero network/model/provider calls, bounded schema and rerun determinism.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from lab import experiment_manifest as em
from lab import selector_coverage as sc
from lab import utility_friction as uf
from sailang.errors import SailangError
from saimail.postoffice import HeaderInterest, HeaderView
from saimail_local import no_network

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SHA = "a8fa4095ea4bbd1361a40c4c0d6be8968584e562a3cde3f47183a3cfccf9631e"
REGISTRATION_SHA = "9be09310122a3638155745b3955f769a8aad20a618a8c795a37eb78b1f6324fa"
HISTORY = ROOT / "lab" / "history" / "v202-selector-coverage"
TOP_LEVEL_KEYS = {
    "schema", "version", "status", "outcome", "admission", "fixture_sha256",
    "registration_sha256", "pairs", "r1_control", "friction_model",
    "setup_and_maintenance", "runtime", "latency", "subjective_pleasantness",
    "production_promotion", "publication", "interpretation",
}
ARM_KEYS = {
    "messages_delivered", "messages_scanned", "messages_opened", "fallback_opens",
    "false_ignores", "missed_relevant", "unnecessary_opens", "friction_components",
    "modeled_total_friction", "modeled_attention_events_not_executed",
    "sender_seals", "sender_extra_treatment_work", "rows",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Network:
    """A tripwire: any use is a failure, so every assertion is exactly zero."""

    def __init__(self):
        self.calls = 0

    def send(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("V2-02 harness attempted a network call")


def view(*, topic="ci-ok", kind="DISCOVERY") -> HeaderView:
    return HeaderView(envelope_id="sha256:" + "0" * 64, sender="V202A",
                      recipient="V202B", kind=kind, topic=topic,
                      created=sc.ls.SCENARIO_TIME, received_at=sc.ls.SCENARIO_TIME,
                      age_seconds=0.0)


@pytest.fixture(scope="module")
def experiment(tmp_path_factory):
    """Run the frozen experiment once, recording the container lists handed to
    each paired arm so byte-identity can be asserted rather than assumed."""
    base = tmp_path_factory.mktemp("v202")
    probe = {"blocked": 0}
    records = []
    original = sc._arm

    def recording(messages, containers, sender, receiver, root, treatment):
        records.append({"treatment": treatment, "messages": list(messages),
                        "containers": list(containers)})
        return original(messages, containers, sender, receiver, root, treatment)

    sc._arm = recording
    try:
        with no_network(probe):
            result = sc.run_experiment(base, probe=probe)
    finally:
        sc._arm = original
    return {"result": result, "records": records, "probe": probe}


def temp_checkout(tmp_path) -> Path:
    """A throwaway checkout that can be mutated without touching the repo."""
    root = tmp_path / "checkout"
    document = em.load(ROOT / sc.MANIFEST)
    rels = {component["PATH"] for component in document["implementation"]}
    rels.add(sc.MANIFEST)
    for record in document["inputs"]:
        rels.add(record["ARCHIVED_FIXTURE"])
        if "SOURCE_PATH" in record:
            rels.add(record["SOURCE_PATH"])
    for rel in rels:
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / rel).read_bytes())
    return root


# ---------------------------------------------------------------------------
# PREREGISTRATION
# ---------------------------------------------------------------------------


def test_registration_is_frozen_and_pins_one_variable():
    registration = json.loads((ROOT / sc.REGISTRATION).read_text(encoding="utf-8"))
    assert registration["schema"] == "SELECTOR_COVERAGE_REGISTRATION_1"
    assert registration["fixture_sha256"] == sha(ROOT / sc.FIXTURES) == FIXTURE_SHA
    assert registration["treatment_variable"] == "ignore_topics"
    assert registration["single_changed_field"] == "ignore_topics"
    assert registration["changed_value_added"] == "ci-ok"
    baseline = registration["baseline_policy"]["ignore_topics"]
    treatment = registration["treatment_policy"]["ignore_topics"]
    assert baseline == ["noise"]
    assert treatment == ["noise", "ci-ok"]
    for field in ("open_r3_topics", "open_r3_kinds"):
        assert registration["baseline_policy"][field] == registration["treatment_policy"][field]
    assert registration["directions"] == ["A_TO_B", "B_TO_A"]
    assert registration["result_schema"] == sc.RESULT_SCHEMA
    assert registration["production_promotion"] == "NONE"
    assert registration["zero_call_budget"] == {"network": 0, "model": 0, "provider": 0}
    assert registration["friction_model_identity"] == uf.FRICTION_MODEL_ID
    assert registration["friction_weights"] == uf.FRICTION_WEIGHTS
    assert registration["truth_visible_to_policy"] is False
    assert registration["success_criteria"]["aggregate_fallback_opens"] == "decrease"
    assert registration["rejection_criteria"]["safety_failure_overrides_friction_savings"] is True


def test_historical_input_copies_are_byte_identical_and_immutable():
    assert sha(HISTORY / "selector_coverage_fixtures.json") == FIXTURE_SHA
    assert sha(HISTORY / "selector_coverage_registration.json") == REGISTRATION_SHA
    assert (HISTORY / "selector_coverage_fixtures.json").read_bytes() == \
        (ROOT / sc.FIXTURES).read_bytes()
    assert (HISTORY / "selector_coverage_registration.json").read_bytes() == \
        (ROOT / sc.REGISTRATION).read_bytes()


# ---------------------------------------------------------------------------
# MANIFEST: THREE SEPARATED AUTHORITIES
# ---------------------------------------------------------------------------


def test_manifest_identity_is_stable_and_not_self_referential():
    document = em.load(ROOT / sc.MANIFEST)
    identity = em.manifest_identity(document)
    assert len(identity) == 64
    assert identity.encode() not in em.canonical_bytes(document)
    assert identity not in json.dumps(document)
    assert document["authority"] == "HISTORICAL_ONLY"
    assert document["experiment_id"] == "V202-SELECTOR-COVERAGE"


def test_historical_and_current_verify_independently():
    document = em.load(ROOT / sc.MANIFEST)
    historical = em.verify_historical(document, fixture_root=ROOT)
    current = em.verify_current(document, root=ROOT)
    assert historical["verdict"] == em.HISTORICAL_VERIFIED
    assert current["verdict"] == em.CURRENT_MATCH
    assert historical["current_source_read"] is False
    assert all(row["status"] == em.CURRENT_MATCH for row in current["inputs"])


def test_no_live_authority_is_granted():
    network = Network()
    document = em.load(ROOT / sc.MANIFEST)
    with pytest.raises(SailangError, match="HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY"):
        em.admit_live(document, root=ROOT, network=network)
    assert network.calls == 0


# ---------------------------------------------------------------------------
# PREFLIGHT REFUSALS
# ---------------------------------------------------------------------------


def test_preflight_refuses_current_implementation_drift(tmp_path):
    root = temp_checkout(tmp_path)
    (root / "lab" / "selector_coverage.py").write_bytes(b"# drifted implementation\n")
    current = em.verify_current(em.load(root / sc.MANIFEST), root=root)
    assert current["verdict"] == em.CURRENT_IMPLEMENTATION_DRIFT
    with pytest.raises(SailangError, match="V202_INPUT_DRIFT"):
        sc.preflight(root)


def test_preflight_refuses_current_input_drift(tmp_path):
    root = temp_checkout(tmp_path)
    fixture = root / "lab" / "selector_coverage_fixtures.json"
    fixture.write_bytes(fixture.read_bytes() + b"\n")
    current = em.verify_current(em.load(root / sc.MANIFEST), root=root)
    assert current["verdict"] == em.CURRENT_INPUT_DRIFT
    with pytest.raises(SailangError, match="V202_INPUT_DRIFT"):
        sc.preflight(root)


def test_preflight_refuses_historical_fixture_mismatch(tmp_path):
    root = temp_checkout(tmp_path)
    archived = root / "lab/history/v202-selector-coverage/selector_coverage_fixtures.json"
    archived.write_bytes(archived.read_bytes() + b"\n")
    document = em.load(root / sc.MANIFEST)
    assert em.verify_current(document, root=root)["verdict"] == em.CURRENT_MATCH
    historical = em.verify_historical(document, fixture_root=root)
    assert historical["verdict"] == em.HISTORICAL_MISMATCH
    with pytest.raises(SailangError, match="V202_HISTORY_MISMATCH"):
        sc.preflight(root)


def test_output_directory_must_be_new_and_empty(tmp_path):
    occupied = tmp_path / "evidence"
    occupied.mkdir()
    (occupied / "result.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="V202_NONEMPTY_WORKSPACE"):
        sc.run_experiment(occupied, root=ROOT)


# ---------------------------------------------------------------------------
# PAIRED ARMS
# ---------------------------------------------------------------------------


def test_both_directions_execute_for_every_workload(experiment):
    pairs = experiment["result"]["pairs"]
    observed = {(pair["workload"], pair["direction"]) for pair in pairs}
    fixture = json.loads((ROOT / sc.FIXTURES).read_text(encoding="utf-8"))
    expected = {(workload["id"], direction)
                for workload in fixture["workloads"] for direction in fixture["directions"]}
    assert observed == expected
    assert len(pairs) == len(expected)


def test_baseline_and_treatment_receive_byte_identical_inputs(experiment):
    records = experiment["records"]
    assert len(records) % 2 == 0
    for index in range(0, len(records), 2):
        baseline, treatment = records[index], records[index + 1]
        assert baseline["treatment"] is False and treatment["treatment"] is True
        assert baseline["containers"] == treatment["containers"]
        assert baseline["messages"] == treatment["messages"]
    for pair in experiment["result"]["pairs"]:
        assert pair["paired_transport_bytes_identical"] is True
        assert [(row["message_id"], row["payload_sha256"]) for row in pair["baseline"]["rows"]] \
            == [(row["message_id"], row["payload_sha256"]) for row in pair["treatment"]["rows"]]


def test_relevance_truth_is_not_visible_to_the_header_policy():
    assert "relevant" not in HeaderView.__dataclass_fields__
    policy = sc.policy(True)
    first = policy.decide(view(topic="ci-ok", kind="DISCOVERY"))
    second = policy.decide(view(topic="ci-ok", kind="DISCOVERY"))
    assert (first.verdict, first.rule) == (second.verdict, second.rule) == ("IGNORE", "HEADER-IGNORE-TOPIC")


def test_overlapping_open_beats_ignore():
    policy = HeaderInterest.of(open_r3_topics={"action"}, open_r3_kinds={"WARNING"},
                               ignore_topics={"noise", "ci-ok"})
    overlapping = policy.decide(view(topic="ci-ok", kind="WARNING"))
    assert overlapping.verdict == "OPEN_R3"
    assert policy.decide(view(topic="ci-ok", kind="DISCOVERY")).verdict == "IGNORE"


# ---------------------------------------------------------------------------
# SAFETY ACCOUNTING
# ---------------------------------------------------------------------------


def _row(message_id, *, machine, final, relevant, opened):
    return {"message_id": message_id, "payload_sha256": message_id, "relevant": relevant,
            "machine_verdict": machine, "final_verdict": final, "rule": "SYNTHETIC",
            "opened": opened}


def _arm(rows, *, fallback, unnecessary, friction):
    return {"rows": rows, "fallback_opens": fallback, "unnecessary_opens": unnecessary,
            "modeled_total_friction": friction}


def test_machine_required_floor_cannot_be_downgraded():
    baseline = _arm([_row("m1", machine="OPEN_R3", final="OPEN_R3", relevant=True, opened=True)],
                    fallback=0, unnecessary=0, friction=100.0)
    treatment = _arm([_row("m1", machine="OPEN_R3", final="DEFER", relevant=True, opened=True)],
                     fallback=0, unnecessary=0, friction=8.0)
    comparison = sc.grade_pair(baseline, treatment)
    assert comparison["baseline_required_open_downgrades"] == ["m1"]
    assert comparison["safe_on_fixture"] is False
    assert comparison["modeled_utility_comparison_admissible"] is False


def test_false_ignore_and_unnecessary_open_are_separate_harms():
    baseline = _arm([
        _row("relevant", machine="DEFER", final="DEFER", relevant=True, opened=True),
        _row("noise", machine="DEFER", final="DEFER", relevant=False, opened=True),
    ], fallback=2, unnecessary=1, friction=20.0)
    treatment = _arm([
        _row("relevant", machine="IGNORE", final="IGNORE", relevant=True, opened=False),
        _row("noise", machine="IGNORE", final="IGNORE", relevant=False, opened=False),
    ], fallback=0, unnecessary=0, friction=0.0)
    comparison = sc.grade_pair(baseline, treatment)
    assert comparison["new_false_ignores"] == ["relevant"]
    assert comparison["new_missed_relevant"] == ["relevant"]
    assert comparison["unnecessary_opens_reduced_by"] == 1
    assert comparison["fallback_opens_reduced_by"] == 2
    assert comparison["safe_on_fixture"] is False


def test_friction_saving_is_inadmissible_when_the_arm_is_unsafe(experiment):
    drift = [pair for pair in experiment["result"]["pairs"]
             if pair["workload"] == "TOPIC_DRIFT"]
    assert drift, "the frozen fixtures must contain the topic-drift workload"
    for pair in drift:
        comparison = pair["comparison"]
        assert comparison["safe_on_fixture"] is False
        assert comparison["modeled_utility_comparison_admissible"] is False
        assert comparison["friction_delta_treatment_minus_baseline"] < 0
        assert comparison["new_false_ignores"] == comparison["new_missed_relevant"]
        assert all(message_id.startswith("TOPIC_DRIFT-")
                   for message_id in comparison["new_false_ignores"])
    assert experiment["result"]["outcome"] == "CANDIDATE_REJECTED_SAFETY"


def test_safe_workloads_still_reduce_fallback_opens(experiment):
    safe = [pair for pair in experiment["result"]["pairs"]
            if pair["comparison"]["safe_on_fixture"]]
    assert safe
    for pair in safe:
        assert pair["comparison"]["new_false_ignores"] == []
        assert pair["comparison"]["new_missed_relevant"] == []
        assert pair["comparison"]["baseline_required_open_downgrades"] == []
        assert pair["treatment"]["fallback_opens"] <= pair["baseline"]["fallback_opens"]


# ---------------------------------------------------------------------------
# R1 CONTROL AND SCHEMA
# ---------------------------------------------------------------------------


def test_r1_control_is_separate_and_unchanged(experiment):
    control = experiment["result"]["r1_control"]
    assert control["changed_by_treatment"] is False
    assert control["false_ignores"] == 0
    assert "not the transport-header experiment" in control["scope"]
    assert uf.FRICTION_MODEL_ID == experiment["result"]["friction_model"]["identity"]


def test_result_schema_is_bounded(experiment):
    result = experiment["result"]
    assert set(result) == TOP_LEVEL_KEYS
    assert result["schema"] == sc.RESULT_SCHEMA and result["version"] == 1
    assert result["status"] == "PASS"
    assert result["production_promotion"] == "NONE"
    assert result["publication"] == "NONE"
    assert result["latency"] == "NOT_MEASURED"
    assert result["subjective_pleasantness"] == "NOT_MEASURED"
    assert result["outcome"] in {"CANDIDATE_SUPPORTED_ON_FIXTURES",
                                 "CANDIDATE_REJECTED_SAFETY", "NO_REDUCTION"}
    for pair in result["pairs"]:
        assert set(pair) == {"workload", "direction", "paired_transport_bytes_identical",
                             "baseline", "treatment", "comparison"}
        assert set(pair["baseline"]) == ARM_KEYS
        assert set(pair["treatment"]) == ARM_KEYS


def test_experiment_is_offline(experiment):
    result = experiment["result"]
    assert result["runtime"]["network_attempts"] == 0
    assert result["runtime"]["model_calls"] == 0
    assert result["runtime"]["provider_calls"] == 0
    assert experiment["probe"]["blocked"] == 0


def test_rerun_from_frozen_inputs_is_deterministic(experiment, tmp_path_factory):
    base = tmp_path_factory.mktemp("v202-repeat")
    probe = {"blocked": 0}
    with no_network(probe):
        second = sc.run_experiment(base, probe=probe)
    assert second == experiment["result"]


def test_harness_is_lab_only_and_offline():
    source = (ROOT / "lab" / "selector_coverage.py").read_text(encoding="utf-8")
    for token in ("import socket", "import urllib", "import requests", "http.client"):
        assert token not in source, token
    for module in (ROOT / "saimail").glob("*.py"):
        assert "selector_coverage" not in module.read_text(encoding="utf-8"), module
