"""U1 / T-94: preregistered drift-safe watched-coverage experiment harness.

Offline only: deterministic fixtures, temp roots, no provider and no network.
The point of these tests is that the mechanism must be raise-only, so the harness
must not be able to quietly turn a sender-controlled attention inflation into a
coverage win.

Covered here: preregistration identity, the historical/current separation of the
manifest, preflight refusal on input or implementation drift, exactly one changed
receiver variable, byte-identical paired frames, truth-blind selector, the
R0-WATCHED-before-R4-NOISE ordering, relation-spam and noise-overlap cost
accounting, mandatory-floor preservation, unchanged unknown/opaque fallback,
zero network/model/provider calls, bounded schema and rerun determinism.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields
from pathlib import Path

import pytest

from lab import experiment_manifest as em
from lab import watched_coverage as wc
from sailang.errors import SailangError
from sailang.frame import Batch, Profile, decode, project_batch
from saimail.acceptance import ProfileRegistry
from saimail.selector import DEFER, IGNORE, OPEN_R2, OPEN_R3, depth, select
from saimail_local import no_network
from sailang import Record

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_SHA = "ab11da7a9f51d4d9716d4f94c27b374412977d5c675deaf17f47053bf447cd9f"
REGISTRATION_SHA = "42ed1767da2eb198787d995704821176b3dd4574ca080a81b39321e2de5ab512"
HISTORY = ROOT / "lab" / "history" / "u1-watched-coverage"
TOP_LEVEL_KEYS = {
    "schema", "version", "status", "outcome", "admission", "watched_target",
    "other_target", "treatment_variable", "directions", "workload_ids",
    "fixture_sha256", "registration_sha256", "pairs", "aggregate", "r1_control",
    "setup_and_maintenance", "runtime", "latency", "subjective_pleasantness",
    "production_promotion", "publication", "no_production_default_change",
    "interpretation",
}
PAIR_KEYS = {"workload", "direction", "paired_frames_identical", "baseline",
             "treatment", "comparison"}
COMPARISON_KEYS = {
    "relevant_attention_upgrades", "irrelevant_attention_upgrades",
    "total_attention_upgrades", "relevant_drift_rescued", "relevant_drift_not_rescued",
    "unnecessary_extra_opens", "relation_spam_extra_opens", "noise_overlap_extra_opens",
    "downward_attention_changes", "new_false_ignores", "new_missed_relevant",
    "baseline_required_open_downgrades", "safety_invariant_violation",
    "upgraded_message_ids", "rescued_message_ids", "relevant_not_rescued_message_ids",
    "extra_open_message_ids", "baseline_total_open", "treatment_total_open",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Network:
    """A tripwire: any use is a failure, so every assertion is exactly zero."""

    def __init__(self):
        self.calls = 0

    def send(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("U1 harness attempted a network call")


@pytest.fixture(scope="module")
def experiment(tmp_path_factory):
    base = tmp_path_factory.mktemp("u1")
    probe = {"blocked": 0}
    with no_network(probe):
        result = wc.run_experiment(base, probe=probe)
    return {"result": result, "probe": probe}


def rows_for(result, workload, direction, treatment=False):
    pair = next(pair for pair in result["pairs"]
                if pair["workload"] == workload and pair["direction"] == direction)
    arm = pair["treatment"] if treatment else pair["baseline"]
    return arm["rows"]


def temp_checkout(tmp_path) -> Path:
    root = tmp_path / "checkout"
    document = em.load(ROOT / wc.MANIFEST)
    rels = {component["PATH"] for component in document["implementation"]}
    rels.add(wc.MANIFEST)
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
    registration = json.loads((ROOT / wc.REGISTRATION).read_text(encoding="utf-8"))
    assert registration["schema"] == "WATCHED_RELATION_COVERAGE_REGISTRATION_1"
    assert registration["fixture_sha256"] == sha(ROOT / wc.FIXTURES) == FIXTURE_SHA
    assert registration["treatment_variable"] == "Interest.watched"
    assert registration["single_changed_field"] == "watched"
    assert registration["baseline_watched"] == []
    assert registration["treatment_watched"] == [registration["watched_target"]]
    for field in ("atoms", "subjects", "noise"):
        assert registration["baseline_interest"][field] == registration["treatment_interest"][field]
    assert registration["directions"] == ["A_TO_B", "B_TO_A"]
    assert registration["result_schema"] == wc.RESULT_SCHEMA
    assert registration["production_promotion"] == "NONE"
    assert registration["zero_call_budget"] == {"network": 0, "model": 0, "provider": 0}
    assert registration["truth_visible_to_selector"] is False
    assert registration["safety_invariants"]["DOWNWARD_ATTENTION_CHANGES"] == 0
    assert registration["safety_invariants"]["NEW_FALSE_IGNORES"] == 0
    assert registration["safety_invariants"]["NEW_MISSED_RELEVANT"] == 0
    assert registration["safety_invariants"]["BASELINE_REQUIRED_OPEN_DOWNGRADES"] == 0
    assert "SAFETY_INVARIANT_VIOLATION" in registration["terminal_outcomes"]
    assert "COVERAGE_GAIN_WITH_EXTRA_OPENS" in registration["terminal_outcomes"]


def test_historical_input_copies_are_byte_identical_and_immutable():
    assert sha(HISTORY / "watched_coverage_fixtures.json") == FIXTURE_SHA
    assert sha(HISTORY / "watched_coverage_registration.json") == REGISTRATION_SHA
    assert (HISTORY / "watched_coverage_fixtures.json").read_bytes() == \
        (ROOT / wc.FIXTURES).read_bytes()
    assert (HISTORY / "watched_coverage_registration.json").read_bytes() == \
        (ROOT / wc.REGISTRATION).read_bytes()


# ---------------------------------------------------------------------------
# MANIFEST: THREE SEPARATED AUTHORITIES
# ---------------------------------------------------------------------------


def test_manifest_identity_is_stable_and_not_self_referential():
    document = em.load(ROOT / wc.MANIFEST)
    identity = em.manifest_identity(document)
    assert len(identity) == 64
    assert identity.encode() not in em.canonical_bytes(document)
    assert document["authority"] == "HISTORICAL_ONLY"
    assert document["experiment_id"] == "U1-WATCHED-COVERAGE"


def test_historical_and_current_verify_independently():
    document = em.load(ROOT / wc.MANIFEST)
    historical = em.verify_historical(document, fixture_root=ROOT)
    current = em.verify_current(document, root=ROOT)
    assert historical["verdict"] == em.HISTORICAL_VERIFIED
    assert current["verdict"] == em.CURRENT_MATCH
    assert historical["current_source_read"] is False


def test_no_live_authority_is_granted():
    network = Network()
    document = em.load(ROOT / wc.MANIFEST)
    with pytest.raises(SailangError, match="HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY"):
        em.admit_live(document, root=ROOT, network=network)
    assert network.calls == 0


# ---------------------------------------------------------------------------
# PREFLIGHT REFUSALS
# ---------------------------------------------------------------------------


def test_preflight_refuses_current_implementation_drift(tmp_path):
    root = temp_checkout(tmp_path)
    (root / "lab" / "watched_coverage.py").write_bytes(b"# drifted implementation\n")
    assert em.verify_current(em.load(root / wc.MANIFEST), root=root)["verdict"] \
        == em.CURRENT_IMPLEMENTATION_DRIFT
    with pytest.raises(SailangError, match="U1_INPUT_DRIFT"):
        wc.preflight(root)


def test_preflight_refuses_current_input_drift(tmp_path):
    root = temp_checkout(tmp_path)
    fixture = root / "lab" / "watched_coverage_fixtures.json"
    fixture.write_bytes(fixture.read_bytes() + b"\n")
    assert em.verify_current(em.load(root / wc.MANIFEST), root=root)["verdict"] \
        == em.CURRENT_INPUT_DRIFT
    with pytest.raises(SailangError, match="U1_INPUT_DRIFT"):
        wc.preflight(root)


def test_preflight_refuses_historical_fixture_mismatch(tmp_path):
    root = temp_checkout(tmp_path)
    archived = root / "lab/history/u1-watched-coverage/watched_coverage_fixtures.json"
    archived.write_bytes(archived.read_bytes() + b"\n")
    document = em.load(root / wc.MANIFEST)
    assert em.verify_current(document, root=root)["verdict"] == em.CURRENT_MATCH
    assert em.verify_historical(document, fixture_root=root)["verdict"] \
        == em.HISTORICAL_MISMATCH
    with pytest.raises(SailangError, match="U1_HISTORY_MISMATCH"):
        wc.preflight(root)


def test_output_directory_must_be_new_and_empty(tmp_path):
    occupied = tmp_path / "evidence"
    occupied.mkdir()
    (occupied / "result.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="U1_NONEMPTY_WORKSPACE"):
        wc.run_experiment(occupied, root=ROOT)


# ---------------------------------------------------------------------------
# ONE VARIABLE, RECEIVER-OWNED, RAISE-ONLY
# ---------------------------------------------------------------------------


def test_exactly_one_receiver_variable_changes():
    registration = wc.load_registration(ROOT)
    baseline = wc.baseline_interest(registration)
    treatment = wc.treatment_interest(registration)
    for field in fields(baseline):
        left, right = getattr(baseline, field.name), getattr(treatment, field.name)
        if field.name == "watched":
            assert left == frozenset() and right == frozenset({registration["watched_target"]})
        else:
            assert left == right, field.name


def test_watched_target_is_receiver_owned_and_sender_cannot_alter_it():
    registration = wc.load_registration(ROOT)
    fixture = wc.load_fixture(ROOT)
    text = json.dumps(fixture)
    assert registration["watched_target"] not in text
    assert registration["other_target"] not in text
    treatment = wc.treatment_interest(registration)
    baseline = wc.baseline_interest(registration)
    profile = Profile.load("1")
    records = [Record.create(KIND="F", SRC="AGENT:U1A", SUBJ="db",
                             CLAIM="DATABASE>METADATA", TYPE="OBS",
                             EV="0", STATUS="U1", CREATED=wc.CREATED,
                             REFUTES=registration["other_target"])]
    frame = Batch.parse(project_batch(records, profile).render(),
                        ProfileRegistry.with_profiles(profile).resolve(profile.id)).frames[0]
    view = decode(frame)
    assert view.relation_targets == (("R", registration["other_target"]),)
    assert select(view, baseline).rule != wc.WATCHED_RULE
    assert select(view, treatment).rule != wc.WATCHED_RULE
    records[0] = Record.create(KIND="F", SRC="AGENT:U1A", SUBJ="db",
                               CLAIM="DATABASE>METADATA", TYPE="OBS",
                               EV="0", STATUS="U1", CREATED=wc.CREATED,
                               REFUTES=registration["watched_target"])
    frame = Batch.parse(project_batch(records, profile).render(),
                        ProfileRegistry.with_profiles(profile).resolve(profile.id)).frames[0]
    assert select(decode(frame), baseline).verdict != OPEN_R3
    assert select(decode(frame), treatment).verdict == OPEN_R3


def test_truth_is_not_visible_to_the_selector(experiment):
    for pair in experiment["result"]["pairs"]:
        assert pair["paired_frames_identical"] is True
        for row in pair["baseline"]["rows"]:
            assert "relevant" not in row["frame_sha256"]
    fixture = wc.load_fixture(ROOT)
    assert "relevant" in json.dumps(fixture)


def test_paired_records_and_frames_are_identical(experiment):
    for pair in experiment["result"]["pairs"]:
        assert [(row["message_id"], row["frame_sha256"]) for row in pair["baseline"]["rows"]] \
            == [(row["message_id"], row["frame_sha256"]) for row in pair["treatment"]["rows"]]


def test_treatment_can_only_preserve_or_raise_depth(experiment):
    result = experiment["result"]
    assert result["aggregate"]["downward_attention_changes"] == 0
    for pair in result["pairs"]:
        for left, right in zip(pair["baseline"]["rows"], pair["treatment"]["rows"], strict=True):
            assert depth(right["verdict"]) >= depth(left["verdict"]), left["message_id"]


def test_no_ignore_authority_is_created(experiment):
    result = experiment["result"]
    assert result["aggregate"]["new_false_ignores"] == 0
    assert result["aggregate"]["new_missed_relevant"] == 0
    for pair in result["pairs"]:
        for left, right in zip(pair["baseline"]["rows"], pair["treatment"]["rows"], strict=True):
            if right["verdict"] == IGNORE:
                assert left["verdict"] == IGNORE, left["message_id"]


# ---------------------------------------------------------------------------
# RULE ORDERING AND BOUNDED SCOPE
# ---------------------------------------------------------------------------


def test_r0_watched_wins_over_r4_noise(experiment):
    result = experiment["result"]
    baseline = rows_for(result, "NOISE_OVERLAP", "A_TO_B", treatment=False)
    treatment = rows_for(result, "NOISE_OVERLAP", "A_TO_B", treatment=True)
    assert baseline and all(row["verdict"] == IGNORE and row["rule"] == "R4-NOISE"
                            for row in baseline)
    assert all(row["verdict"] == OPEN_R3 and row["rule"] == wc.WATCHED_RULE
               for row in treatment)


def test_relation_to_other_target_does_not_trigger(experiment):
    result = experiment["result"]
    baseline = rows_for(result, "OTHER_TARGET", "A_TO_B", treatment=False)
    treatment = rows_for(result, "OTHER_TARGET", "A_TO_B", treatment=True)
    assert baseline and treatment
    for left, right in zip(baseline, treatment, strict=True):
        assert left["verdict"] == right["verdict"] == DEFER
        assert right["rule"] != wc.WATCHED_RULE


def test_no_relation_does_not_trigger(experiment):
    result = experiment["result"]
    baseline = rows_for(result, "NO_RELATION_RELEVANT", "A_TO_B", treatment=False)
    treatment = rows_for(result, "NO_RELATION_RELEVANT", "A_TO_B", treatment=True)
    assert baseline and treatment
    for left, right in zip(baseline, treatment, strict=True):
        assert left["verdict"] == right["verdict"] == DEFER
        assert right["rule"] != wc.WATCHED_RULE
    assert wc.load_fixture(ROOT)["workloads"][2]["id"] == "NO_RELATION_RELEVANT"


def test_relation_spam_and_noise_overlap_are_counted(experiment):
    aggregate = experiment["result"]["aggregate"]
    assert aggregate["relevant_attention_upgrades"] == 18
    assert aggregate["irrelevant_attention_upgrades"] == 24
    assert aggregate["relation_spam_extra_opens"] == 14
    assert aggregate["noise_overlap_extra_opens"] == 10
    assert aggregate["unnecessary_extra_opens"] == 0
    assert aggregate["relevant_drift_rescued"] == 14
    assert aggregate["relevant_drift_not_rescued"] == 6
    assert aggregate["safety_invariant_violation"] is False
    assert aggregate["outcome"] == "COVERAGE_GAIN_WITH_EXTRA_OPENS"


def test_mandatory_open_floors_are_not_downgraded(experiment):
    result = experiment["result"]
    baseline = rows_for(result, "MANDATORY_OPEN_CONTROL", "A_TO_B", treatment=False)
    required = [row for row in baseline if row["verdict"] in (OPEN_R2, OPEN_R3)]
    assert len(required) == 11
    for pair in result["pairs"]:
        for left, right in zip(pair["baseline"]["rows"], pair["treatment"]["rows"], strict=True):
            if left["verdict"] in (OPEN_R2, OPEN_R3):
                assert depth(right["verdict"]) >= depth(left["verdict"]), left["message_id"]
    assert result["aggregate"]["baseline_required_open_downgrades"] == 0


def test_unknown_and_opaque_fallback_unchanged(experiment):
    result = experiment["result"]
    baseline = rows_for(result, "UNKNOWN_OPAQUE_CONTROL", "A_TO_B", treatment=False)
    treatment = rows_for(result, "UNKNOWN_OPAQUE_CONTROL", "A_TO_B", treatment=True)
    assert {row["rule"] for row in baseline} == {"R2-UNKNOWN", "R3-OPEN-RECORD"}
    for left, right in zip(baseline, treatment, strict=True):
        assert left["verdict"] == right["verdict"] == OPEN_R2
        assert left["rule"] == right["rule"]


def test_r1_stress_control_is_separate_and_unchanged(experiment):
    control = experiment["result"]["r1_control"]
    assert control["changed_by_treatment"] is False
    assert control["false_ignores"] == 0
    assert control["watched_relation_cases"] == 4
    assert control["unknown_atom_fallbacks"] == 7
    assert control["opaque_claim_fallbacks"] == 8
    assert "not the U1" in control["scope"]


# ---------------------------------------------------------------------------
# SCHEMA, OFFLINE AND DETERMINISM
# ---------------------------------------------------------------------------


def test_result_schema_is_bounded(experiment):
    result = experiment["result"]
    assert set(result) == TOP_LEVEL_KEYS
    assert result["schema"] == wc.RESULT_SCHEMA and result["version"] == 1
    assert result["status"] == "PASS"
    assert result["production_promotion"] == "NONE"
    assert result["publication"] == "NONE"
    assert result["no_production_default_change"] is True
    assert result["outcome"] in wc._TERMINAL
    assert result["aggregate"]["outcome"] == result["outcome"]
    for pair in result["pairs"]:
        assert set(pair) == PAIR_KEYS
        assert set(pair["comparison"]) == COMPARISON_KEYS
        assert pair["baseline"]["messages"] == pair["treatment"]["messages"]


def test_both_directions_execute_for_every_workload(experiment):
    fixture = wc.load_fixture(ROOT)
    expected = {(workload["id"], direction)
                for workload in fixture["workloads"] for direction in fixture["directions"]}
    observed = {(pair["workload"], pair["direction"])
                for pair in experiment["result"]["pairs"]}
    assert observed == expected


def test_experiment_is_offline(experiment):
    result = experiment["result"]
    assert result["runtime"]["network_attempts"] == 0
    assert result["runtime"]["model_calls"] == 0
    assert result["runtime"]["provider_calls"] == 0
    assert experiment["probe"]["blocked"] == 0


def test_rerun_from_frozen_inputs_is_deterministic(experiment, tmp_path_factory):
    base = tmp_path_factory.mktemp("u1-repeat")
    probe = {"blocked": 0}
    with no_network(probe):
        second = wc.run_experiment(base, probe=probe)
    assert second == experiment["result"]


def test_harness_is_lab_only_and_offline():
    source = (ROOT / "lab" / "watched_coverage.py").read_text(encoding="utf-8")
    for token in ("import socket", "import urllib", "import requests", "http.client"):
        assert token not in source, token
    for module in (ROOT / "saimail").glob("*.py"):
        assert "watched_coverage" not in module.read_text(encoding="utf-8"), module
    selector = (ROOT / "saimail" / "selector.py").read_text(encoding="utf-8")
    assert "R0-WATCHED" in selector and "R4-NOISE" in selector
