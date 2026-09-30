"""One recurring host observation stays keyless, bounded and context-bound."""

import json
import sys

import pytest

import saimail_local
from sailang import SailangError
from saimail import agent_cycle, correspondence, letters, saipen_bridge, workspace
from saimail_host import HostClient
from test_correspondence import CLOCK, LINEAGE, decide, review, send, setup


def entry(pair, **kwargs):
    _, receiver, root, _ = pair
    return agent_cycle.entry(workspace.load_workspace_headers(receiver.root), root / ".saipen/STATE.md",
                             root / ".saipen/IDENTITY.md", seat="reviewer", clock=CLOCK,
                             work=kwargs.pop("work", "T-9"), **kwargs)


def test_empty_cycle_does_not_create_decision_state_and_does_not_invent_work(setup):
    _, receiver, root, _ = setup
    result = entry(setup)
    assert result["cycle"]["next_action"]["action"] == "CONTINUE_WORK"
    assert result["cycle"]["complete_from_start"]
    assert not result["cycle"]["automatic_execution"]
    assert not (receiver.root / correspondence.DB_NAME).exists()
    state = root / ".saipen/STATE.md"
    state.write_text(state.read_text(encoding="utf-8").replace("T-7", "none"), encoding="utf-8")
    unbound = entry(setup, work=None)
    assert unbound["cycle"]["next_action"]["action"] == "CHOOSE_WORK"
    assert unbound["desk"] is None and not unbound["cycle"]["complete"]


def test_current_mail_returns_one_explicit_reading_action_without_opening(setup, monkeypatch):
    _, receiver, root, letter = setup
    eid = send(setup)["intent"]["envelope_id"]
    before = {p.name: p.read_bytes() for p in (root / ".saipen").iterdir()}
    monkeypatch.setattr(workspace, "open_message", lambda *a, **k: pytest.fail("unexpected open"))
    monkeypatch.setattr(workspace, "reopen_message", lambda *a, **k: pytest.fail("unexpected reopen"))
    monkeypatch.setattr(letters, "_file_hash", lambda *a, **k: pytest.fail("unexpected evidence read"))
    result = entry(setup)
    action = result["cycle"]["next_action"]
    assert action["action"] == "REVIEW" and action["envelope_id"] == eid
    assert action["command"] == ["saipen", "letter", "review"]
    assert action["arguments"] == ["--envelope", eid]
    assert action["authority"] == "INFORMATION_ONLY"
    assert letter["observation"] not in json.dumps(result)
    assert result["metrics"]["reviewed"] == 0
    assert {p.name: p.read_bytes() for p in (root / ".saipen").iterdir()} == before
    assert workspace.query_inbox(receiver)["items"][0]["state"] == "UNREAD"


def test_unfinished_decisions_and_predecessor_results_are_reading_suggestions(setup):
    _, receiver, root, letter = setup
    pending = send(setup, issue="pending")["intent"]["envelope_id"]
    decide(setup, pending, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    reserved = send(setup, issue="reserved")["intent"]["envelope_id"]
    decide(setup, reserved, evidence=[letters.evidence_ref(root, "result.txt")])
    correspondence.retain(receiver, reserved, lineage=LINEAGE, project_root=root, clock=CLOCK)
    current = entry(setup)
    assert current["cycle"]["next_action"]["envelope_id"] == pending
    assert current["metrics"]["feedback_hints"][0]["suggestion"] == "WAIT_FOR_DEPENDENCY_EVIDENCE"
    successor = entry(setup, work="T-12", scope=letter["scope"])
    assert successor["cycle"]["next_action"]["envelope_id"] == reserved
    assert successor["cycle"]["next_action"]["reason"] == "SUCCESSOR_RESERVE"


def test_dual_pagination_preserves_every_axis_and_rejects_changed_host_context(setup):
    _, _, root, _ = setup
    ids = [send(setup, issue=f"cycle-{n}")["intent"]["envelope_id"] for n in range(4)]
    for eid in ids[:2]:
        review(setup, eid)
    page = entry(setup, budget=1)
    first = page["cycle"]["continuation"]
    seen = []
    for _ in range(12):
        assert page["desk"]["rows_examined"] <= 1 and page["desk"]["cases_examined"] <= 1
        assert len(page["cycle"]["actions"]) <= 2
        seen.extend(action["envelope_id"] for action in page["cycle"]["actions"])
        if page["cycle"]["continuation"] is None:
            break
        page = entry(setup, budget=1, continuation=page["cycle"]["continuation"])
    assert page["cycle"]["complete"] and not page["cycle"]["complete_from_start"]
    assert len(seen) == len(set(seen)) == 4 and set(seen) == set(ids)
    state = root / ".saipen/STATE.md"
    state.write_text(state.read_text(encoding="utf-8").replace("last_event: 40", "last_event: 41"), encoding="utf-8")
    with pytest.raises(SailangError, match=saipen_bridge.SAIPEN_CONTEXT_CHANGED):
        entry(setup, budget=1, continuation=first)


def test_empty_partial_page_recommends_continuation_not_an_empty_mailbox(setup):
    ids = [send(setup, issue=f"read-{n}")["intent"]["envelope_id"] for n in range(2)]
    for eid in ids:
        review(setup, eid)
        decide(setup, eid, decision="DECLINED", reason="ALREADY_KNOWN")
    page = entry(setup, budget=1)
    action = page["cycle"]["next_action"]
    assert action["action"] == "CONTINUE_DISCOVERY"
    assert action["arguments"][-1] == page["cycle"]["continuation"]
    assert not page["cycle"]["complete"]


@pytest.mark.parametrize("kwargs", [
    {"budget": True}, {"budget": 0}, {"budget": 101}, {"work": "none"},
    {"scope": ["../outside"]}, {"continuation": "invalid"}, {"continuation": "x" * 2049},
])
def test_bad_cycle_inputs_have_named_refusals(setup, kwargs):
    with pytest.raises(SailangError):
        entry(setup, **kwargs)


def test_context_change_mid_observation_returns_no_mixed_cycle(setup, monkeypatch):
    _, _, root, _ = setup
    original = correspondence.desk

    def changed(*args, **kwargs):
        page = original(*args, **kwargs)
        state = root / ".saipen/STATE.md"
        state.write_text(state.read_text(encoding="utf-8").replace("BUILD", "VERIFY"), encoding="utf-8")
        return page

    monkeypatch.setattr(correspondence, "desk", changed)
    with pytest.raises(SailangError, match=saipen_bridge.SAIPEN_CONTEXT_CHANGED):
        entry(setup)


def test_real_independent_host_can_observe_the_cycle_without_lifecycle_writes(setup):
    _, receiver, root, _ = setup
    eid = send(setup)["intent"]["envelope_id"]
    before = {p.name: p.read_bytes() for p in (root / ".saipen").iterdir()}
    host = HostClient([sys.executable, "-m", "saimail_local"], workspace=receiver.root,
                      project_root=root, seat="reviewer")
    result = host.request("cycle", ["--work", "T-9", "--budget", "1"])
    assert result["state"] == "OK"
    assert result["data"]["cycle"]["schema"] == agent_cycle.SCHEMA
    assert result["data"]["cycle"]["next_action"]["envelope_id"] == eid
    assert {p.name: p.read_bytes() for p in (root / ".saipen").iterdir()} == before


def test_cli_uses_one_admission_and_refuses_a_change_after_that_observation(setup, monkeypatch, capsys):
    _, receiver, root, _ = setup
    original, calls = saipen_bridge.enter, []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result["saipen"]["last_event"])
        if len(calls) == 1:
            state = root / ".saipen/STATE.md"
            state.write_text(state.read_text(encoding="utf-8").replace("last_event: 40", "last_event: 41"), encoding="utf-8")
        return result

    monkeypatch.setattr(saipen_bridge, "enter", changed)
    code = saimail_local.main(["--json", "saipen", "letter", "cycle", "--work", "T-9",
                              "--workspace", str(receiver.root), "--project-root", str(root),
                              "--seat", "reviewer"])
    result = json.loads(capsys.readouterr().out)
    assert code == 1 and result["status"] == saipen_bridge.SAIPEN_CONTEXT_CHANGED
    assert calls == ["40"]
