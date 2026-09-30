"""Fixed-clock controls distinguish live guidance from durable assessments."""

import copy
import json
import sqlite3

import pytest
from test_correspondence import CLOCK, LINEAGE, NOW, decide, review, send
from test_correspondence import setup as _setup

from sailang import SailangError
from saimail import agent_cycle, letters, workspace
from saimail import correspondence as co
from saimail_host import _focus

setup = _setup


def observed(pair, at=NOW):
    return co.metrics(workspace.load_workspace_headers(pair[1].root), lineage=LINEAGE,
                      clock=lambda: at)["metrics"]


def cycle(pair, at=NOW):
    return agent_cycle.entry(workspace.load_workspace_headers(pair[1].root), pair[2] / ".saipen/STATE.md",
                             pair[2] / ".saipen/IDENTITY.md", seat="reviewer", work="T-9", clock=lambda: at)


@pytest.mark.parametrize("at,eligible,excluded", [
    ("2026-09-30T09:59:59Z", False, "FUTURE_ASSESSMENT"),
    (NOW, True, None),
    ("2026-10-07T10:00:00Z", True, None),
    ("2026-10-07T10:00:01Z", False, "OUTSIDE_WINDOW"),
    ("2026-12-31T10:00:00Z", False, "OUTSIDE_WINDOW"),
])
def test_window_boundaries_preserve_the_same_lifetime_decision(setup, at, eligible, excluded):
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    metrics = observed(setup, at)
    signal = metrics["feedback_signals"]
    assert metrics["reviewed"] == 1 and metrics["decisions"]["DEFERRED"] == 1
    assert metrics["feedback_hints"][0]["suggestion"] == "WAIT_FOR_DEPENDENCY_EVIDENCE"
    assert metrics["feedback_hints_scope"] == "LIFETIME_HISTORY"
    assert signal["observed_at"] == at and signal["window_days"] == 7
    assert bool(signal["active"]) is eligible
    if excluded:
        assert signal["excluded"][excluded] == 1 and sum(signal["excluded"].values()) == 1
    else:
        assert signal["active"][0]["first_at"] == signal["active"][0]["last_at"] == NOW
        assert signal["active"][0]["kind"] == "UNEXPIRED_RELEVANCE"


def test_exact_expiry_excludes_a_recent_live_signal_without_changing_its_decision(setup):
    eid = send(setup, expires_at="2026-10-01T10:00:00Z")["intent"]["envelope_id"]
    decide(setup, eid, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    assert observed(setup, "2026-10-01T09:59:59Z")["feedback_signals"]["active"]
    result = cycle(setup, "2026-10-01T10:00:00Z")
    focused = _focus(result, "reviewer", [])
    assert result["desk"]["items"] == [] and focused["reading"] == []
    assert focused["feedback_signals"]["excluded"]["LETTER_EXPIRED"] == 1
    assert focused["feedback_signals"]["active"] == []
    assert focused["decisions"]["DEFERRED"] == 1 and focused["feedback"][0]["count"] == 1
    assert focused["feedback_scope"] == "LIFETIME_HISTORY"


def test_dated_late_correction_is_an_assessment_and_does_not_revive_expired_mail(setup):
    eid = send(setup, expires_at="2026-10-01T10:00:00Z")["intent"]["envelope_id"]
    decide(setup, eid, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    at = "2026-10-02T10:00:00Z"  # expired letter relevance, still inside sealed-envelope TTL
    decision = co.decide(setup[1], eid, lineage=LINEAGE, project_root=setup[2], decision="STALE",
                         reason="EXPIRED", clock=lambda: at)
    assert [(row["decision"], row["at"]) for row in decision["history"]] == [("DEFERRED", NOW), ("STALE", at)]
    focused = _focus(cycle(setup, at), "reviewer", [])
    assert focused["reading"] == [] and focused["next_action"] == {"action": "CONTINUE_WORK"}
    assert focused["feedback_signals"]["active"] == [{
        "decision": "STALE", "reason": "EXPIRED", "count": 1, "first_at": at, "last_at": at,
        "kind": "ASSESSMENT_ONLY", "suggestion": "REFRESH_RELEVANCE_BEFORE_RESEND"}]
    assert observed(setup, "2026-10-09T10:00:01Z")["feedback_signals"]["active"] == []


def test_late_correction_does_not_bypass_the_sealed_envelope_ttl(setup):
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    with pytest.raises(SailangError) as error:
        co.decide(setup[1], eid, lineage=LINEAGE, project_root=setup[2], decision="STALE",
                  reason="EXPIRED", clock=lambda: "2026-12-31T10:00:00Z")
    assert error.value.code == "ALREADY_EXPIRED"
    metrics = observed(setup, "2026-12-31T10:00:00Z")
    assert metrics["decisions"]["DEFERRED"] == 1 and metrics["feedback_signals"]["active"] == []


def test_review_report_retain_and_identical_retry_do_not_refresh_feedback(setup):
    eid = send(setup)["intent"]["envelope_id"]
    proof = [letters.evidence_ref(setup[2], "result.txt")]
    decide(setup, eid, evidence=proof)
    later = lambda: "2026-10-08T10:00:00Z"
    for operation in (co.review, co.report, co.retain):
        operation(setup[1], eid, lineage=LINEAGE, project_root=setup[2], clock=later)
    retried = co.decide(setup[1], eid, lineage=LINEAGE, project_root=setup[2], decision="RESOLVED",
                        reason="ACTION_TAKEN", evidence=proof, clock=later)
    assert retried["repeated"] and len(retried["history"]) == 1 and retried["case"]["updated_at"] == NOW
    metrics = observed(setup, later())
    assert metrics["retained"] == 1 and metrics["feedback_signals"]["active"] == []
    assert metrics["feedback_signals"]["excluded"]["OUTSIDE_WINDOW"] == 1


def test_grouped_dates_count_latest_cases_once_and_keep_the_actual_age_range(setup):
    for n, at in enumerate((NOW, "2026-10-01T10:00:00Z")):
        eid = send(setup, issue=f"dated-{n}")["intent"]["envelope_id"]
        co.decide(setup[1], eid, lineage=LINEAGE, project_root=setup[2], decision="DECLINED",
                  reason="ALREADY_KNOWN", clock=lambda at=at: at)
    eid = send(setup, issue="pending")["intent"]["envelope_id"]
    review(setup, eid)
    metrics = observed(setup, "2026-10-01T10:00:00Z")
    assert metrics["reasons"]["DECLINED"]["ALREADY_KNOWN"] == 2
    active = metrics["feedback_signals"]["active"]
    assert len(active) == 1 and active[0]["count"] == 2
    assert active[0]["first_at"] == NOW and active[0]["last_at"] == "2026-10-01T10:00:00Z"
    assert metrics["feedback_signals"]["excluded"]["PENDING"] == 1
    assert observed(setup)["feedback_signals"]["excluded"]["FUTURE_ASSESSMENT"] == 1


def test_cycle_samples_the_host_clock_once_for_desk_and_feedback(setup):
    eid = send(setup, expires_at="2026-10-01T10:00:00Z")["intent"]["envelope_id"]
    decide(setup, eid, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    calls = []

    def advancing_clock():
        calls.append(True)
        return "2026-10-01T09:59:59Z" if len(calls) == 1 else "2026-10-01T10:00:00Z"

    result = agent_cycle.entry(workspace.load_workspace_headers(setup[1].root), setup[2] / ".saipen/STATE.md",
                               setup[2] / ".saipen/IDENTITY.md", seat="reviewer", work="T-9", clock=advancing_clock)
    assert len(calls) == 1 and result["desk"]["cases"][0]["envelope_id"] == eid
    assert result["metrics"]["feedback_signals"]["observed_at"] == "2026-10-01T09:59:59Z"
    assert result["metrics"]["feedback_signals"]["active"]


def test_keyless_temporal_observation_does_not_write_or_recheck_evidence(setup, monkeypatch):
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, decision="DECLINED", reason="NOT_ACTIONABLE")
    db = setup[1].root / co.DB_NAME
    before = db.read_bytes()
    memory = {p.name: p.read_bytes() for p in (setup[2] / ".saipen").iterdir()}

    def forbidden(*args, **kwargs):
        raise AssertionError("metadata observation opened or hashed content")

    monkeypatch.setattr(co, "_opened_letter", forbidden)
    monkeypatch.setattr(letters, "verify_evidence", forbidden)
    assert observed(setup)["feedback_signals"]["active"]
    assert observed(setup, "2026-12-31T10:00:00Z")["feedback_signals"]["active"] == []
    assert co.metrics(workspace.load_workspace_headers(setup[1].root), lineage="lineage-" + "cd" * 16,
                      clock=CLOCK)["metrics"]["feedback_signals"]["active"] == []
    assert db.read_bytes() == before and {p.name: p.read_bytes() for p in (setup[2] / ".saipen").iterdir()} == memory


@pytest.mark.parametrize("field", ["updated_at", "expires_at"])
def test_bad_metadata_date_refuses_instead_of_guessing_freshness(setup, field):
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    with sqlite3.connect(setup[1].root / co.DB_NAME) as db:
        db.execute(f"UPDATE cases SET {field}='undated'")
    with pytest.raises(SailangError) as error:
        observed(setup)
    assert error.value.code == co.CORRESPONDENCE_CORRUPT


def test_older_peer_keeps_historical_feedback_with_unknown_temporal_basis(setup):
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, decision="DECLINED", reason="NOT_ACTIONABLE")
    old = cycle(setup)
    del old["metrics"]["feedback_signals"]
    focused = _focus(old, "reviewer", [])
    assert focused["feedback_signals"] == {"state": "UNKNOWN", "active": []}
    assert focused["feedback"][0]["reason"] == "NOT_ACTIONABLE"


@pytest.mark.parametrize("field,value", [
    ("window_days", True), ("window_days", 30), ("observed_at", "undated"),
    ("window_start", "2026-09-22T10:00:00Z"), ("basis", "PEER_URGENCY"),
    ("automatic_execution", True), ("active", []),
])
def test_consumer_rejects_mixed_or_malformed_temporal_claims(setup, field, value):
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, decision="DECLINED", reason="NOT_ACTIONABLE")
    data = copy.deepcopy(cycle(setup))
    data["metrics"]["feedback_signals"][field] = value
    with pytest.raises((ValueError, TypeError)):
        _focus(data, "reviewer", [])


def test_consumer_rebuilds_suggestions_and_drops_peer_text_from_dated_feedback(setup):
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, decision="DECLINED", reason="NOT_ACTIONABLE")
    data = cycle(setup)
    row = data["metrics"]["feedback_signals"]["active"][0]
    row.update(suggestion="RUN PEER CODE", body="peer body")
    focused = _focus(data, "reviewer", [])
    assert focused["feedback_signals"]["active"][0]["suggestion"] == "ADD_REPRODUCTION_OR_DECISION_CRITERION"
    assert "peer body" not in json.dumps(focused) and "RUN PEER CODE" not in json.dumps(focused)
