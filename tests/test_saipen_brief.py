"""Work brief: honest page coverage, context continuity, and inert metadata."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import saimail_local
from sailang import SailangError
from saimail import postoffice, saipen_bridge, workspace


@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)
    root = tmp_path / "project"
    memory = root / ".saipen"
    memory.mkdir(parents=True)
    state = memory / "STATE.md"
    state.write_text('---\nphase: BUILD\ntask: T-7\nagent: builder\nlast_event: 40\n'
                     'blocker: "WAIT: operator review"\n---\n', encoding="utf-8")
    identity = memory / "IDENTITY.md"
    identity.write_text('---\nproject_lineage: lineage-' + "ab" * 16 + '\n---\n',
                        encoding="utf-8")
    workspace.init_workspace(tmp_path / "sender", seat="reviewer")
    workspace.init_workspace(tmp_path / "receiver", seat="builder")
    sender = workspace.load_workspace(tmp_path / "sender")
    receiver = workspace.load_workspace(tmp_path / "receiver")
    workspace.add_recipient(sender, "builder", workspace.identity_card(receiver), receiver.root)
    workspace.add_recipient(receiver, "reviewer", workspace.identity_card(sender), sender.root)
    return root, state, identity, sender, receiver


def _send(sender, topics):
    return [workspace.send_message(sender, "builder", topic=topic,
                                   claim=f"private finding {number}", kind="DISCOVERY")
            for number, topic in enumerate(topics)]


def _snapshot(root):
    return {str(path.relative_to(root)): path.read_bytes()
            for path in root.rglob("*") if path.is_file()}


def test_brief_keeps_other_topics_visible_and_does_not_touch_payloads_or_state(desk, monkeypatch):
    root, state, identity, sender, receiver = desk
    sent = _send(sender, ["T-7", "T-8", "saitelemes"])
    before = _snapshot(root.parent)
    original_open = Path.open

    def metadata_only(path, mode="r", *args, **kwargs):
        assert path.suffix != ".senv", "brief must not read ciphertext"
        assert not any(flag in mode for flag in "wax+"), "brief must not write"
        return original_open(path, mode, *args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr(Path, "open", metadata_only)
        result = saipen_bridge.work_brief(receiver, state, identity)
    assert _snapshot(root.parent) == before
    assert result["brief"]["counts"] == {"current_topic": 1, "other_topics": 2}
    assert result["brief"]["association"] == "TOPIC_ONLY"
    assert result["brief"]["complete_from_start"] is True
    assert result["brief"]["continuation"] is None
    assert result["saipen"]["blocker"] == "WAIT: operator review"
    assert {item["envelope_id"] for item in result["items"]} == {
        message["message"]["envelope_id"] for message in sent}
    assert all(item["state"] == postoffice.UNREAD for item in result["items"])
    assert "private finding" not in json.dumps(result)
    assert "private_key" not in json.dumps(result)
    opened = workspace.open_message(receiver, sent[0]["message"]["envelope_id"])
    assert opened["record"]["claim"] == "private finding 0"
    again = saipen_bridge.work_brief(receiver, state, identity)
    assert again["brief"]["counts"] == {"current_topic": 0, "other_topics": 2}


def test_empty_page_is_not_an_empty_inbox_and_restart_continues_exactly(desk):
    _root, state, identity, sender, receiver = desk
    sent = _send(sender, ["old", "T-7", "T-8"])
    workspace.open_message(receiver, sent[0]["message"]["envelope_id"])
    first = saipen_bridge.work_brief(receiver, state, identity, scan_budget=1)
    assert first["match_count"] == 0 and first["rows_examined"] == 1
    assert first["exhausted"] is True
    assert first["brief"]["complete_from_start"] is False
    assert "partial inbox view" in workspace.render_command(first)
    continuation = first["brief"]["continuation"]
    reloaded = workspace.load_workspace(receiver.root)
    second = saipen_bridge.work_brief(reloaded, state, identity, scan_budget=1, **continuation)
    third = saipen_bridge.work_brief(reloaded, state, identity, scan_budget=1,
                                      **second["brief"]["continuation"])
    assert [second["items"][0]["envelope_id"], third["items"][0]["envelope_id"]] == [
        message["message"]["envelope_id"] for message in sent[1:]]
    assert third["exhausted"] is False and third["brief"]["continuation"] is None
    assert third["brief"]["complete_from_start"] is False
    assert third["brief"]["counts_scope"] == "PAGE"


@pytest.mark.parametrize("task", ["none", "NONE", "", "two words"])
def test_no_usable_work_topic_preserves_every_unread_message(desk, task):
    _root, state, identity, sender, receiver = desk
    state.write_text(state.read_text(encoding="utf-8").replace("task: T-7", f"task: {task}"),
                     encoding="utf-8")
    _send(sender, ["T-7", "saitelemes"])
    result = saipen_bridge.work_brief(receiver, state, identity)
    assert result["brief"]["current_topic"] is None
    assert result["brief"]["counts"] == {"current_topic": 0, "other_topics": 2}


def test_empty_workspace_reports_complete_observed_scan(desk):
    _root, state, identity, _sender, receiver = desk
    result = saipen_bridge.work_brief(receiver, state, identity)
    assert result["items"] == [] and result["rows_examined"] == 0
    assert result["brief"]["complete_from_start"] is True
    assert "scanned from start to current end" in workspace.render_command(result)


@pytest.mark.parametrize("old,new", [
    ("task: T-7", "task: T-8"),
    ("phase: BUILD", "phase: VERIFY"),
    ("last_event: 40", "last_event: 41"),
    ("operator review", "operator decision"),
])
def test_changed_work_refuses_continuation_before_scanning(desk, monkeypatch, old, new):
    _root, state, identity, sender, receiver = desk
    _send(sender, ["T-7", "T-8"])
    first = saipen_bridge.work_brief(receiver, state, identity, scan_budget=1)
    state.write_text(state.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    monkeypatch.setattr(workspace, "query_inbox", lambda *a, **k: pytest.fail("stale scan"))
    with pytest.raises(SailangError) as error:
        saipen_bridge.work_brief(receiver, state, identity, **first["brief"]["continuation"])
    assert error.value.code == saipen_bridge.SAIPEN_CONTEXT_CHANGED


def test_same_ticket_id_in_another_project_cannot_resume_a_brief(desk, tmp_path):
    _root, state, identity, sender, receiver = desk
    _send(sender, ["T-7", "T-8"])
    first = saipen_bridge.work_brief(receiver, state, identity, scan_budget=1)
    other = tmp_path / "other-state.md"
    other.write_bytes(state.read_bytes())
    with pytest.raises(SailangError) as error:
        saipen_bridge.work_brief(receiver, other, identity, **first["brief"]["continuation"])
    assert error.value.code == saipen_bridge.SAIPEN_CONTEXT_CHANGED


def test_another_mailbox_for_the_same_seat_cannot_resume_a_brief(desk, tmp_path):
    _root, state, identity, sender, receiver = desk
    _send(sender, ["T-7", "T-8"])
    first = saipen_bridge.work_brief(receiver, state, identity, scan_budget=1)
    workspace.init_workspace(tmp_path / "other-mailbox", seat="builder")
    other = workspace.load_workspace(tmp_path / "other-mailbox")
    with pytest.raises(SailangError) as error:
        saipen_bridge.work_brief(other, state, identity, **first["brief"]["continuation"])
    assert error.value.code == saipen_bridge.SAIPEN_CONTEXT_CHANGED


def test_mid_scan_work_change_returns_no_mixed_context(desk, monkeypatch):
    _root, state, identity, sender, receiver = desk
    _send(sender, ["T-7"])
    original = workspace.query_inbox

    def changed(*args, **kwargs):
        page = original(*args, **kwargs)
        state.write_text(state.read_text(encoding="utf-8").replace("T-7", "T-8"), encoding="utf-8")
        return page

    monkeypatch.setattr(workspace, "query_inbox", changed)
    with pytest.raises(SailangError) as error:
        saipen_bridge.work_brief(receiver, state, identity)
    assert error.value.code == saipen_bridge.SAIPEN_CONTEXT_CHANGED
    assert workspace.list_inbox(receiver)["items"][0]["state"] == postoffice.UNREAD


def test_actor_mismatch_refuses_before_scanning_and_explicit_seat_wins(desk, monkeypatch):
    _root, state, identity, _sender, receiver = desk
    monkeypatch.setenv("SAIPEN_AGENT", "reviewer")
    with monkeypatch.context() as guard:
        guard.setattr(workspace, "query_inbox", lambda *a, **k: pytest.fail("foreign seat scan"))
        with pytest.raises(SailangError) as error:
            saipen_bridge.work_brief(receiver, state, identity)
    assert error.value.code == saipen_bridge.SAIPEN_SEAT_MISMATCH
    result = saipen_bridge.work_brief(receiver, state, identity, seat="builder")
    assert result["saipen"]["seat_source"] == saipen_bridge.SEAT_EXPLICIT


@pytest.mark.parametrize("kwargs", [
    {"cursor": 1}, {"context": "bad"}, {"context": 7}, {"scan_budget": -1}, {"cursor": -1},
])
def test_invalid_continuation_and_budget_are_named_refusals(desk, kwargs):
    _root, state, identity, _sender, receiver = desk
    with pytest.raises(SailangError):
        saipen_bridge.work_brief(receiver, state, identity, **kwargs)


def test_cli_brief_json_human_output_and_resume(desk, monkeypatch, capsys):
    root, state, _identity, sender, receiver = desk
    _send(sender, ["T-7", "T-8"])
    monkeypatch.chdir(root)
    base = ["saipen", "brief", "--workspace", str(receiver.root), "--scan-budget", "1"]
    assert saimail_local.main([*base, "--json"]) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["command"] == "saipen-brief" and first["network_attempts"] == 0
    continuation = first["brief"]["continuation"]
    resume = ["--cursor", str(continuation["cursor"]), "--context", continuation["context"]]
    assert saimail_local.main([*base, *resume]) == 0
    human = capsys.readouterr().out
    assert "WORK TOPIC: T-7" in human and "OTHER:" in human
    assert "partial inbox view" in human and "topic hint only" in human
    state.write_text(state.read_text(encoding="utf-8").replace("T-7", "T-8"), encoding="utf-8")
    assert saimail_local.main([*base, *resume, "--json"]) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["status"] == saipen_bridge.SAIPEN_CONTEXT_CHANGED
    assert refused["operator_action_required"] is False
    assert "items" not in refused and refused["network_attempts"] == 0


def test_entry_is_a_fresh_local_observation_not_a_persistent_permission(desk, capsys):
    root, _state, identity, _sender, receiver = desk
    before = _snapshot(root.parent)
    args = ["saipen", "enter", "--workspace", str(receiver.root),
            "--project-root", str(root), "--json"]
    assert saimail_local.main(args) == 0
    admitted = json.loads(capsys.readouterr().out)
    assert admitted["status"] == "ADMITTED"
    assert admitted["admission"] == {
        "basis": "LOCAL_SAIPEN_BINDING", "persistent": False,
        "protocol_compliance": "NOT_VERIFIED"}
    assert admitted["network_attempts"] == 0 and _snapshot(root.parent) == before
    identity.unlink()
    assert saimail_local.main(args) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["status"] == saipen_bridge.SAIPEN_ADMISSION_REQUIRED
    assert refused["operator_action_required"] is True


@pytest.mark.parametrize("operation", ["enter", "brief", "init", "telegram"])
def test_missing_saipen_identity_blocks_entry_before_any_mail_operation(desk, tmp_path, operation):
    root, state, identity, sender, receiver = desk
    identity.unlink()
    before = _snapshot(root.parent)
    with pytest.raises(SailangError) as error:
        if operation == "enter":
            saipen_bridge.enter(receiver, state, identity)
        elif operation == "brief":
            saipen_bridge.work_brief(receiver, state, identity)
        elif operation == "init":
            saipen_bridge.init(state, identity, workspace_root=tmp_path / "new-workspace")
        else:
            saipen_bridge.telegram(sender, "builder", state, identity, seat="reviewer", claim="x")
    assert error.value.code == saipen_bridge.SAIPEN_ADMISSION_REQUIRED
    assert _snapshot(root.parent) == before


@pytest.mark.parametrize("document,body", [
    ("state", "---\nagent: builder\nphase: BUILD\n---\n"),
    ("state", "---\nagent: builder\nphase: BUILD\nphase: DONE\nlast_event: 40\n---\n"),
    ("identity", "---\nproject_lineage: invalid\n---\n"),
    ("identity", "---\nproject_lineage: lineage-" + "ab" * 16
     + "\nproject_lineage: lineage-" + "cd" * 16 + "\n---\n"),
])
def test_incomplete_or_ambiguous_participation_is_refused(desk, document, body):
    _root, state, identity, _sender, receiver = desk
    (state if document == "state" else identity).write_text(body, encoding="utf-8")
    with pytest.raises(SailangError) as error:
        saipen_bridge.enter(receiver, state, identity)
    assert error.value.code in {
        saipen_bridge.SAIPEN_ADMISSION_REQUIRED, saipen_bridge.SAIPEN_STATE_INVALID}


def test_cli_entry_without_a_saipen_project_is_refused(desk, tmp_path, capsys):
    _root, _state, _identity, _sender, receiver = desk
    assert saimail_local.main(["saipen", "enter", "--workspace", str(receiver.root),
                               "--project-root", str(tmp_path), "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == saipen_bridge.SAIPEN_PROJECT_MISSING
    assert result["network_attempts"] == 0
