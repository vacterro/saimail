"""FG-06 acceptance: TOTAL_FRICTION utility benchmark against a fair baseline.

Focused areas A-F, L, M. The benchmark is deterministic and offline; these
tests assert the declared comparison boundary, fixture immutability, metric
internal consistency and the preserved separation of unlike harms.
"""

from __future__ import annotations

import contextlib
import json
import socket

import pytest

from lab import local_scenario as ls
from lab import utility_friction as uf


@contextlib.contextmanager
def no_network(probe: dict):
    original_connect = socket.socket.connect
    original_create = socket.create_connection

    def blocked(*_args, **_kwargs):
        probe["blocked"] = probe.get("blocked", 0) + 1
        raise AssertionError("FG-06 utility benchmark attempted a network connection")

    socket.socket.connect = blocked
    socket.create_connection = blocked
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    base = tmp_path_factory.mktemp("fg06-utility")
    probe = {"blocked": 0, "python": "test", "platform": "test"}
    with no_network(probe):
        return uf.run_utility(base, probe=probe)


# ------------------------------------------------------ A. baseline fairness


def test_baseline_is_information_equivalent_on_shared_terms(result):
    for entry in result["workloads"]:
        protocol = entry["protocol_friction_components"]
        baseline = entry["baseline_friction_components"]
        # Shared work is identical on both sides; the differing terms are the
        # cost of lacking a selector, not extra semantics.
        assert protocol["durable_write"] == baseline["durable_write"]
        assert protocol["promotion_decision"] == baseline["promotion_decision"]
        assert protocol["attention_reservation"] == baseline["attention_reservation"]
        assert protocol["attention_acknowledgement"] == baseline["attention_acknowledgement"]
        assert baseline["header_scan"] == 0
        assert baseline["full_read"] == entry["messages_discovered"]
        assert protocol["header_scan"] == entry["messages_discovered"]
        assert protocol["full_read"] == entry["messages_opened"]


# --------------------------------------------------- B. fixture immutability


def test_workload_fixtures_are_frozen_and_identified(result):
    first = uf.frozen_workloads()
    second = uf.frozen_workloads()
    assert [w.identity() for w in first] == [w.identity() for w in second]
    by_id = {w.workload_id: w for w in first}
    for entry in result["workloads"]:
        assert entry["fixture_identity"] == by_id[entry["workload_id"]].identity()
    # The recovery workload reuses FG-05 and is reported separately.
    assert result["recovery"]["workload_id"] == "E_ERROR_RECOVERY_INTEGRATION"


# ------------------------------------------------------ C. metric accounting


def test_friction_and_metric_accounting_is_internally_consistent(result):
    for entry in result["workloads"]:
        protocol = _friction(entry["protocol_friction_components"])
        baseline = _friction(entry["baseline_friction_components"])
        assert entry["friction_protocol"] == protocol
        assert entry["friction_baseline"] == baseline
        assert entry["friction_ratio"] == round(protocol / baseline, 6)
        assert entry["messages_scanned"] == entry["messages_discovered"]
        assert entry["messages_opened"] == (
            entry["messages_relevant"] + entry["messages_unknown_atoms"]
            - entry["missed_mandatory_opens"])
        assert entry["open_rate"] == round(
            entry["messages_opened"] / entry["messages_discovered"], 6)
        assert entry["manual_decisions"] == entry["messages_relevant"]


def _friction(components: dict) -> float:
    return round(sum(uf.FRICTION_WEIGHTS[name] * value
                    for name, value in components.items()), 4)


# --------------------------------------------------- D. attention accounting


def test_attention_harms_remain_separate(result):
    for entry in result["workloads"]:
        assert entry["false_ignores"] == 0
        assert entry["missed_mandatory_opens"] == 0
        assert entry["unnecessary_opens"] == entry["false_opens"]
        assert entry["attention_reservations"] == entry["attention_acknowledgements"]
        assert entry["attention_saved_by_ignore"] == (
            entry["messages_discovered"] - entry["messages_opened"])
    fallback = next(e for e in result["workloads"] if e["workload_id"] == "D_FALLBACK_HEAVY")
    assert fallback["false_opens"] > 0
    assert fallback["attention_consumed_by_fallback"] > 0
    assert fallback["messages_unknown_atoms"] == fallback["messages_discovered"] // 2


# ----------------------------------------------------------- E. recovery


def test_recovery_accounting_reuses_fg05():
    recovery = None
    # A dedicated run keeps this focused; the module fixture covers the rest.
    import tempfile
    from pathlib import Path

    probe = {"blocked": 0, "python": "test", "platform": "test"}
    with no_network(probe):
        recovery = uf.run_utility(Path(tempfile.mkdtemp()), probe=probe)["recovery"]
    assert recovery["scenario_status"] == "PASS"
    assert recovery["injected_failures"] == 6
    assert recovery["recovery_actions"] == recovery["injected_failures"] + 1
    assert recovery["manual_recovery_interventions"] == 0
    assert recovery["authority_lost"] is False
    assert recovery["duplicate_side_effects"] is False


# --------------------------------------------------- F. TOTAL_FRICTION model


def test_total_friction_model_is_explicit_and_raw_survives(result):
    model = result["friction_model"]
    assert model["is_model_not_truth"] is True
    assert model["declared"] == "before_measurement"
    assert set(model["weights"]) == set(uf.FRICTION_WEIGHTS)
    assert "1000" in model["token_normalization"]
    for entry in result["workloads"]:
        assert entry["protocol_friction_components"]["token_kunit"] >= 0
        assert entry["token_model"]["measured_here"] is False
        assert entry["token_model"]["source"].startswith("T-9B")


# ---------------------------------------------------------------- L. privacy


def test_utility_result_carries_no_private_plaintext(result):
    assert ls.PRIVATE_MARKER not in json.dumps(result)


# ------------------------------------------------------- M. zero network


def test_utility_benchmark_is_offline(result):
    assert result["zero_network_model"]["network_attempts"] == 0
    assert result["zero_network_model"]["provider_calls"] == 0
    assert result["zero_network_model"]["generation_calls"] == 0
    assert result["zero_network_model"]["review_calls"] == 0


# ------------------------------------------------------------- outcome


def test_outcome_is_workload_specific(result):
    assert result["outcome_category"] in (
        "UTILITY_POSITIVE", "UTILITY_CONDITIONAL", "UTILITY_NEUTRAL", "UTILITY_NEGATIVE")
    by_id = result["outcome_by_workload"]
    assert by_id["A_LOW_OPEN_RATE"] == "UTILITY_POSITIVE"
    assert result["friction_ratio_min"] <= result["friction_ratio_max"]
    assert result["grading"].startswith("raw metrics")
