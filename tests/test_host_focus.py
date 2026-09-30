"""Less agent context retains discovery, feedback and all refusal boundaries."""

import copy
import json
import sys

import pytest
from test_correspondence import CLOCK, decide, review, send
from test_correspondence import setup as _setup

from saimail import agent_cycle, correspondence, letters, workspace
from saimail_host import HostClient

setup = _setup  # pytest fixture registration, shared without changing its oracle


def host(pair):
    _, receiver, project, _ = pair
    return HostClient([sys.executable, "-m", "saimail_local"], workspace=receiver.root,
                      project_root=project, seat="reviewer")


def full(pair, **kwargs):
    _, receiver, project, _ = pair
    return agent_cycle.entry(workspace.load_workspace_headers(receiver.root), project / ".saipen/STATE.md",
                             project / ".saipen/IDENTITY.md", seat="reviewer", work="T-9", clock=CLOCK, **kwargs)


def test_real_focus_reduces_context_without_opening_or_following_a_reading_action(setup):
    eid = send(setup)["intent"]["envelope_id"]
    _, receiver, project, letter = setup
    before = {p.name: p.read_bytes() for p in (project / ".saipen").iterdir()}
    original = host(setup).request("cycle", ["--work", "T-9"])["data"]
    focused = host(setup).focus(["--work", "T-9"])
    assert focused["state"] == "OK" and focused["schema"] == "SAIMAIL_HOST_FOCUS_1"
    assert focused["reading"] == [{"envelope_id": eid, "reason": "CURRENT_MAIL"}]
    assert focused["next_action"] == {"action": "REVIEW", "operation": "review", "arguments": ["--envelope", eid]}
    assert focused["coverage"]["complete_from_start"]
    assert focused["reviewed"] == 0 and not focused["automatic_execution"]
    assert len(json.dumps(focused)) < len(json.dumps(original))
    assert letter["observation"] not in json.dumps(focused)
    assert workspace.query_inbox(receiver)["items"][0]["state"] == "UNREAD"
    assert not (receiver.root / correspondence.DB_NAME).exists()
    assert {p.name: p.read_bytes() for p in (project / ".saipen").iterdir()} == before


def test_focus_retains_negative_feedback_and_does_not_double_count_revisions(setup):
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    first = host(setup).focus(["--work", "T-9"])
    assert first["feedback"] == [{"decision": "DEFERRED", "reason": "WAITING_DEPENDENCY", "count": 1,
                                    "suggestion": "WAIT_FOR_DEPENDENCY_EVIDENCE"}]
    decide(setup, eid, decision="DECLINED", reason="NOT_ACTIONABLE")
    last = host(setup).focus(["--work", "T-9"])
    assert last["reviewed"] == 1 and last["decisions"]["DEFERRED"] == 0
    assert last["feedback"] == [{"decision": "DECLINED", "reason": "NOT_ACTIONABLE", "count": 1,
                                   "suggestion": "ADD_REPRODUCTION_OR_DECISION_CRITERION"}]
    assert last["feedback_basis"] == "LATEST_RECEIVER_ASSESSMENT"
    assert not last["model_improvement_proven"]


@pytest.mark.parametrize("decision,reason", [
    (decision, reason) for decision, reasons in correspondence.REASONS.items() for reason in sorted(reasons)
])
def test_independent_focus_consumer_preserves_every_producer_reason(setup, decision, reason):
    eid = send(setup)["intent"]["envelope_id"]
    proof = [letters.evidence_ref(setup[2], "result.txt")] if decision == "RESOLVED" else []
    decide(setup, eid, decision=decision, reason=reason, evidence=proof)
    focused = host(setup).focus(["--work", "T-9"])
    assert focused["state"] == "OK"
    expected = {"decision": decision, "reason": reason, "count": 1}
    if reason in correspondence.FEEDBACK_HINTS:
        expected["suggestion"] = correspondence.FEEDBACK_HINTS[reason]
    assert focused["feedback"] == [expected]


def test_focus_preserves_every_pending_and_successor_reading_reference(setup):
    pending = send(setup, issue="pending")["intent"]["envelope_id"]
    review(setup, pending)
    reserved = send(setup, issue="retained")["intent"]["envelope_id"]
    decide(setup, reserved, evidence=[letters.evidence_ref(setup[2], "result.txt")])
    correspondence.retain(setup[1], reserved, lineage=setup[3]["lineage"], project_root=setup[2], clock=CLOCK)
    ordinary = host(setup).focus(["--work", "T-9"])
    assert ordinary["reading"][0] == {"envelope_id": pending, "reason": "CURRENT_WORK"}
    successor = host(setup).focus(["--work", "T-12", "--scope", setup[3]["scope"][0]])
    assert successor["reading"] == [{"envelope_id": reserved, "reason": "SUCCESSOR_RESERVE"}]
    assert successor["retained"] == 1 and successor["next_action"]["operation"] == "review"


def test_focus_cursor_walk_retains_both_axes_and_completion_limits(setup):
    ids = [send(setup, issue=f"walk-{n}")["intent"]["envelope_id"] for n in range(4)]
    for eid in ids[:2]:
        review(setup, eid)
    query, seen = ["--work", "T-9", "--budget", "1"], []
    focused = host(setup).focus(query)
    token = focused["continuation"]
    for _ in range(10):
        assert focused["state"] == "OK"
        assert focused["coverage"]["rows_examined"] <= 1 and focused["coverage"]["cases_examined"] <= 1
        seen.extend(row["envelope_id"] for row in focused["reading"])
        if focused["continuation"] is None:
            break
        focused = host(setup).focus([*query, "--continuation", focused["continuation"]])
    assert set(seen) == set(ids) and len(seen) == len(set(seen))
    assert focused["coverage"]["complete"] and not focused["coverage"]["complete_from_start"]
    state = setup[2] / ".saipen/STATE.md"
    state.write_text(state.read_text().replace("last_event: 40", "last_event: 41"), encoding="utf-8")
    refused = host(setup).focus([*query, "--continuation", token])
    assert refused["state"] == "DEGRADED" and refused["code"] == "SAIPEN_CONTEXT_CHANGED"


def test_empty_partial_focus_provides_a_host_owned_resume_with_identical_query(setup):
    for n in range(2):
        eid = send(setup, issue=f"closed-{n}")["intent"]["envelope_id"]
        decide(setup, eid, decision="DECLINED", reason="ALREADY_KNOWN")
    query = ["--work", "T-9", "--scope", "src/file.py", "--budget=1"]
    first = host(setup).focus(query)
    assert not first["coverage"]["complete"] and first["reading"] == []
    action = first["next_action"]
    assert action == {"action": "CONTINUE_DISCOVERY", "operation": "cycle",
                      "arguments": ["--work", "T-9", "--scope", "src/file.py", "--budget", "1",
                                    "--continuation", first["continuation"]]}
    last = host(setup).focus(action["arguments"])
    assert last["state"] == "OK" and last["coverage"]["complete"]
    assert not last["coverage"]["complete_from_start"]


def test_focus_without_work_keeps_unknown_coverage_and_choose_work(setup):
    state = setup[2] / ".saipen/STATE.md"
    state.write_text(state.read_text().replace("task: T-7", "task: none"), encoding="utf-8")
    focus = host(setup).focus()
    assert focus["state"] == "OK" and focus["work"] is None
    assert focus["next_action"] == {"action": "CHOOSE_WORK"}
    assert not focus["coverage"]["complete"] and not focus["coverage"]["complete_from_start"]


def test_projection_ignores_peer_command_hints_and_reconstructs_all_references(setup, monkeypatch):
    eid = send(setup)["intent"]["envelope_id"]
    data = full(setup)
    data["cycle"]["actions"] = []
    data["cycle"]["next_action"] = {"action": "EXECUTE", "command": ["peer-instruction"]}
    data["desk"]["items"][0]["body"] = "secret peer body must not enter agent context"
    client = host(setup)
    monkeypatch.setattr(client, "request", lambda *a: {"state": "OK", "data": data})
    focused = client.focus()
    assert focused["next_action"]["arguments"] == ["--envelope", eid]
    assert focused["reading"] == [{"envelope_id": eid, "reason": "CURRENT_MAIL"}]
    assert "peer-instruction" not in json.dumps(focused) and "secret peer body" not in json.dumps(focused)


@pytest.mark.parametrize("path,value", [
    (("cycle", "schema"), "SAIMAIL_AGENT_CYCLE_2"), (("cycle", "complete"), 1),
    (("cycle", "complete_from_start"), True), (("cycle", "automatic_execution"), True),
    (("cycle", "continuation"), "x" * 2049), (("cycle", "scope"), ["../other"]),
    (("cycle", "context"), "unbound"), (("cycle", "work"), "command"),
    (("desk", "rows_examined"), True), (("desk", "complete"), 0),
    (("saipen", "seat"), "another-seat"), (("metrics", "reviewed"), 2),
    (("metrics", "model_improvement_proven"), True),
])
def test_missing_or_mixed_projection_never_becomes_continue_work(setup, monkeypatch, path, value):
    send(setup)
    data = copy.deepcopy(full(setup))
    # This control has a partial page, so a claimed full coverage is a lie.
    if path == ("cycle", "complete_from_start"):
        data["cycle"].update(complete=False, complete_from_start=False, continuation="valid-opaque-token")
        data["desk"].update(complete=False, complete_from_start=False)
    data[path[0]][path[1]] = value
    client = host(setup)
    monkeypatch.setattr(client, "request", lambda *a: {"state": "OK", "data": data})
    result = client.focus()
    assert result["state"] == "DEGRADED" and result["reason"] == "INVALID_CYCLE"
    assert "next_action" not in result


def test_focus_preserves_named_degradation_without_more_invocations(setup, monkeypatch):
    calls = []
    client = host(setup)
    refusal = {"state": "DEGRADED", "reason": "MISSING_FEATURE", "authority": "INFORMATION_ONLY"}

    def absent(action, arguments):
        calls.append(action)
        return refusal

    monkeypatch.setattr(client, "request", absent)
    assert client.focus() == refusal and calls == ["cycle"]
