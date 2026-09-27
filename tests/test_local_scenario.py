"""FG-05 acceptance: the existing pieces compose into one local workflow.

The scenario under test is ``lab/local_scenario.py``. These tests do not
re-prove any module's unit contract; they prove the *joints* — that source,
envelope, delivery, dedup, header scan, explicit open, promotion, restart,
TTL/tombstone, LEGACY succession, HUMAN_PRIVATE and attention compose through
public APIs into one finite machine-verifiable result with no model, network or
hardware involvement.

Proof areas: A happy path, B restart, C duplicate, D TTL, E tombstone,
F LEGACY, G HUMAN_PRIVATE, H no-advice/unverified, I durable failure injection,
J side-effect counts, K zero model/network, L one-command run.
"""

from __future__ import annotations

import contextlib
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from lab import local_scenario as ls
from sailang.errors import SailangError

ROOT = Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def no_network(probe: dict):
    """The test-owned network tripwire; the LAB engine must not import socket."""
    original_connect = socket.socket.connect
    original_create = socket.create_connection

    def blocked(*_args, **_kwargs):
        probe["blocked"] = probe.get("blocked", 0) + 1
        raise AssertionError("FG-05 core scenario attempted a network connection")

    socket.socket.connect = blocked
    socket.create_connection = blocked
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    base = tmp_path_factory.mktemp("fg05-scenario")
    probe = {"blocked": 0}
    with no_network(probe):
        return ls.run_scenario(base, probe=probe)


# ---------------------------------------------------------------- contract


def test_result_contract_is_machine_readable(result):
    assert result["schema"] == ls.RESULT_SCHEMA
    assert result["scenario"] == ls.SCENARIO
    assert result["version"] == ls.SCENARIO_VERSION
    assert result["status"] == "PASS"
    assert result["checks"] and all(entry["ok"] for entry in result["checks"])


def test_result_contains_no_private_plaintext(result):
    assert ls.PRIVATE_MARKER not in json.dumps(result)
    assert ls.PRIVATE_MARKER not in json.dumps(result["checks"])


def test_every_proof_area_is_checked(result):
    ids = {entry["id"] for entry in result["checks"]}
    for needed in (
        # A happy path / C+D+E probes
        "packaging_identity", "delivery_accepted", "scan_budget_exact",
        "scan_continuation", "open_explicit_plaintext", "open_claim_preserved",
        "open_evidence_preserved", "open_uncertainty_preserved",
        "promotion_binds_envelope", "promotion_is_not_a_writer",
        "dedup_status_duplicate", "dedup_original_received_at",
        # B restart
        "restart_index_survives", "restart_states_survive",
        "restart_identity_deterministic", "restart_dedup_main",
        # D/E TTL + tombstone
        "ttl_sweep_expire_exactly_one", "ttl_tombstone_published",
        "ttl_no_resurrection",
        # F LEGACY
        "legacy_adopted", "legacy_provenance_preserved",
        "legacy_successor_uncertainty", "legacy_no_authority_gain",
        # G HUMAN_PRIVATE
        "private_delivered", "private_open_explicit",
        "private_marker_absent_before_open", "private_marker_absent_after_open",
        "attention_admitted", "attention_reserved", "attention_acked",
        # H no-advice / unverified
        "no_advice_outcome", "unverified_resolution_refused",
        "unverified_conversion_refused", "advice_paths_no_delivery",
        "advice_paths_no_attention",
        # I durable failure injection
        "fault_bundle_write_retry_safe", "fault_commit_recovered",
        "fault_read_transition_reconciled", "fault_ack_retry_acks",
        "fault_legacy_repaired", "fault_tombstone_finished",
        # K zero network
        "zero_network_model_calls",
    ):
        assert needed in ids, f"missing proof check: {needed}"


# ---------------------------------------------------------- A. happy path


def test_happy_path_uses_public_apis_in_order(result):
    happy = result["happy_path"]
    assert happy["open"] == "EXPLICIT"
    assert happy["claim_preserved"] and happy["evidence_preserved"]
    assert happy["uncertainty_preserved"]
    assert happy["promotion"] == "SEPARATE_ACTION"
    assert happy["index_rows"] == 6
    assert result["envelopes"]["main"].startswith("sha256:")


# --------------------------------------------------------- B. restart


def test_restart_reconstructs_from_durable_roots(result):
    restart = result["restart_proof"]
    assert restart["object_identity_released"] is True
    assert restart["index_rows"] == 6
    assert restart["continued_open"] == "PASS"
    assert restart["states"]["main"] == "READ"
    assert restart["states"]["ttl"] == "EXPIRED"


# ------------------------------------------------- C. duplicate delivery


def test_duplicate_delivery_is_suppressed_across_lifecycle(result):
    assert result["dedup_proof"] == {"mail_duplicates": 4, "private_duplicates": 1}


# ----------------------------------------------------- D/E. TTL tombstone


def test_ttl_and_tombstone_prevent_resurrection(result):
    proof = result["ttl_tombstone_proof"]
    assert proof == {"expired": True, "tombstone": True,
                     "redelivery": "DUPLICATE", "resurrection": False}


# -------------------------------------------------------- F. LEGACY


def test_legacy_succession_preserves_provenance(result):
    proof = result["legacy_proof"]
    assert proof["adopted"] and proof["recovery_repaired"]
    assert proof["entry_id"].startswith("sha256:")
    assert proof["provenance_source_envelope"].startswith("sha256:")


# --------------------------------------------------- G. HUMAN_PRIVATE


def test_human_private_branch_and_attention(result):
    proof = result["human_private_proof"]
    assert proof["opened"] and proof["plaintext_persisted"] is False
    assert proof["mode"] == "STRICT"
    assert result["attention_accounting"]["reservations"] == 2
    assert result["attention_accounting"]["acknowledgements"] == 2
    assert result["attention_accounting"]["consumed"] == 2


# ------------------------------------------- H. no advice / unverified


def test_no_advice_and_unverified_advice_consume_nothing(result):
    proof = result["no_advice_proof"]
    assert proof["status"] == "NO_ADVICE"
    assert proof["delivery"] is False
    assert proof["attention_consumed"] is False
    assert proof["unverified_conversion"] == "ALLY_EVIDENCE_RESOLUTION_REQUIRED"


# ---------------------------------------------- I. durable failure injection


def test_every_injected_boundary_has_a_named_outcome(result):
    injection = result["failure_injection"]
    assert injection["count"] == 6
    assert set(injection["boundaries"]) == {
        "bundle_write", "index_commit", "read_transition",
        "attention_ack", "legacy_write", "tombstone_expiry",
    }
    ids = {entry["id"] for entry in result["checks"] if not entry["ok"]}
    assert not ids


# --------------------------------------------------- J. side-effect counts


EXPECTED_SIDE_EFFECTS = {
    "mail_accepts": 5, "mail_duplicates": 4, "durable_message_creations": 6,
    "explicit_opens": 2, "promotions": 1, "attention_reservations": 2,
    "attention_acknowledgements": 2, "tombstones": 1, "legacy_adoptions": 1,
    "legacy_recoveries": 1, "private_accepts": 1, "private_duplicates": 1,
    "injected_failures": 6,
}


def test_side_effect_counts_are_exact(result):
    assert result["side_effects"] == EXPECTED_SIDE_EFFECTS


# ------------------------------------------------- K. zero model / network


def test_core_scenario_is_offline(result):
    assert result["zero_network_model"]["network_attempts"] == 0
    assert result["zero_network_model"]["provider_calls"] == 0


# ------------------------------------------------- L. one-command run


def test_one_command_run_from_clean_state(tmp_path):
    completed = subprocess.run(
        [sys.executable, "tools/fg05_local_scenario.py", "--out", str(tmp_path)],
        cwd=ROOT, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    parsed = json.loads((tmp_path / "local_scenario_result.json").read_text(encoding="utf-8"))
    assert parsed["status"] == "PASS"
    assert parsed["zero_network_model"]["network_attempts"] == 0
    assert (tmp_path / "local_scenario_summary.md").is_file()


def test_runner_returns_non_zero_on_violated_invariants(monkeypatch):
    import importlib

    runner = importlib.import_module("tools.fg05_local_scenario")
    fake = {
        "status": "FAIL", "schema": ls.RESULT_SCHEMA, "version": 1,
        "participants": {"A": {"seat": "A"}, "B": {"seat": "B"}},
        "side_effects": {}, "failure_injection": {"count": 0},
        "zero_network_model": {"network_attempts": 0, "provider_calls": 0},
        "checks": [{"id": "x", "ok": False, "detail": "injected"}],
    }
    monkeypatch.setattr(ls, "run_scenario", lambda base, probe=None: fake)
    assert runner.main([]) == 1


# ------------------------------------------------------- focused controls


def test_identity_keys_are_deterministic_software_keys():
    first = ls.identity("alice", ls.SEAT_A)
    second = ls.identity("alice", ls.SEAT_A)
    other = ls.identity("bob", ls.SEAT_B)
    assert first.sender_kid == second.sender_kid
    assert first.recipient_kid == second.recipient_kid
    assert first.human_id == second.human_id
    assert first.sender_kid != other.sender_kid
    assert first.human_id != other.human_id


def test_fail_once_restores_the_original_attribute():
    class Target:
        def operation(self):
            return "original"

    target = Target()
    with ls.fail_once(target, "operation"), pytest.raises(SailangError) as caught:
        target.operation()
    assert caught.value.code == ls.INJECTED_FAILURE
    assert target.operation() == "original"


def test_no_network_guard_blocks_every_connection():
    probe = {"blocked": 0}
    with pytest.raises(AssertionError), no_network(probe):
        socket.create_connection(("127.0.0.1", 9))
    assert probe["blocked"] == 1


def test_evidence_gate_can_go_red():
    """Instrument control: the acceptance gate recognizes a known-bad check."""
    evidence = ls.Evidence()
    evidence.check("known_good", True)
    assert evidence.ok
    evidence.check("known_bad", False, "planted failure")
    assert not evidence.ok
    assert [entry["id"] for entry in evidence.checks if not entry["ok"]] == ["known_bad"]


def test_privacy_marker_scan_has_positive_and_negative_controls(tmp_path):
    """Instrument control: the plaintext-absence check detects a planted marker."""
    assert not ls.contains_marker(tmp_path, "fg05-needle")
    (tmp_path / "planted.bin").write_bytes(b"prefix fg05-needle suffix")
    assert ls.contains_marker(tmp_path, "fg05-needle")
