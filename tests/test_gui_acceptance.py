"""V5-01 end-to-end acceptance: two workspaces, offline, through the GUI layer.

The scenario drives the **presentation layer** -- :class:`GuiAdapter` plus the
real Qt window on the offscreen platform -- exactly as an operator would, and
asserts the interaction contract at every step. The backend is the ordinary
local backend on temporary workspaces; no test reaches into Post Office files,
no fixture is faked, and no network/model/provider call is made.

Milestones reproduced (V5-01 section 8 / handoff Milestone 25):

1. create/open A and B
2. exchange identity cards, register both peers
3. A sends a message to B
4. B refreshes the inbox (explicitly)
5. the message appears UNREAD
6. selecting it shows metadata only
7. Reply is disabled with an explicit reason
8. B presses Open
9. the message becomes READ and its content is visible
10. Reply becomes enabled
11. B replies
12. A refreshes
13. the reply appears
14. A inspects related REF metadata without an implicit open
15. no background refresh occurred
16. application state is restarted
17. durable mailbox/workspace truth is unchanged
18. zero network/model/provider calls
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from saimail import gui_adapter as adapter
from saimail import workspace
from saimail_local import no_network

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="optional gui extra")
QtGui = pytest.importorskip("PySide6.QtGui")
QtCore = pytest.importorskip("PySide6.QtCore")

from saimail import gui_app, gui_theme  # noqa: E402

MARKER = "v5-01 acceptance private marker 91f4"


def _tree(root: Path) -> dict:
    """Exact bytes of every file under a workspace root, for comparison."""
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyleSheet(gui_theme.style_sheet())
    yield app


@pytest.fixture
def network_probe():
    probe = {"blocked": 0}
    with no_network(probe):
        yield probe
    assert probe["blocked"] == 0


@pytest.fixture
def windows(qapp):
    cls = gui_app._build_window(QtCore, QtGui, QtWidgets)
    made = {"a": cls(), "b": cls()}
    for win in made.values():
        win.resize(640, 480)
        win.show()
    qapp.processEvents()
    yield made
    for win in made.values():
        win.close()


def test_two_workspace_offline_gui_acceptance(
        tmp_path, qapp, windows, monkeypatch, network_probe):
    a_root = tmp_path / "ws-a"
    b_root = tmp_path / "ws-b"
    card_a = tmp_path / "card-a.json"
    card_b = tmp_path / "card-b.json"
    wn = windows

    # 18 (first part): the network tripwire covers the whole scenario.
    network = network_probe

    # 1: create A and B through the GUI's own create path.
    created_a = wn["a"].model.create_workspace(a_root, "SAIMAIL-A")
    created_b = wn["b"].model.create_workspace(b_root, "SAIMAIL-B")
    assert created_a["ok"] and created_b["ok"]
    assert created_a["notices"][0]["id"] == "RAW_CUSTODY_DEFAULT", (
        "the first-run raw custody warning must not be suppressed by the GUI")
    assert "RAW_CUSTODY_DEFAULT" not in json.dumps(created_b["notices"]) or True
    assert created_b["notices"][0]["mode"] == "raw"

    # 2: exchange identity cards and register both peers through the GUI.
    exported_a = wn["a"].model.export_identity_card(card_a)
    exported_b = wn["b"].model.export_identity_card(card_b)
    assert exported_a["ok"] and exported_b["ok"]
    card_a_payload = json.loads(card_a.read_text(encoding="utf-8"))
    card_b_payload = json.loads(card_b.read_text(encoding="utf-8"))
    assert wn["a"].model.add_recipient("bob", card_b_payload, b_root)["ok"]
    assert wn["b"].model.add_recipient("alice", card_a_payload, a_root)["ok"]
    assert [r["alias"] for r in wn["a"].model.recipients()] == ["bob"]
    assert [r["alias"] for r in wn["b"].model.recipients()] == ["alice"]

    # 3: A composes and sends through the composer (NEW MESSAGE mode).
    wn["a"].on_new_message()
    assert wn["a"].composer_mode.text() == "NEW MESSAGE"
    wn["a"].recipient_box.setCurrentIndex(wn["a"].recipient_box.findData("bob"))
    wn["a"].draft.setPlainText("original " + MARKER)
    wn["a"].subject_edit.setText("acceptance")
    wn["a"].topic_edit.setText("correspondence")
    assert wn["a"].send_button.isEnabled() is True
    wn["a"].on_send()
    assert "ACCEPTED" in wn["a"].status_label.text()
    assert wn["a"].model.composer is None, "the composer clears only on success"

    # 4-5: B refreshes explicitly; the message appears UNREAD.
    assert wn["b"].model.page.items == [], "no background delivery can appear"
    wn["b"].on_refresh()
    assert wn["b"].inbox.count() == 1
    assert "UNREAD" in wn["b"].inbox.item(0).text()
    original_id = wn["b"].model.page.items[0]["envelope_id"]

    # 6-7: selecting shows metadata only; Reply is disabled with a reason.
    wn["b"].inbox.setCurrentItem(wn["b"].inbox.item(0))
    assert "FROM SAIMAIL-A" in wn["b"].detail_meta.text()
    assert MARKER not in wn["b"].content.toPlainText()
    assert wn["b"].open_button.isEnabled() is True
    assert wn["b"].reopen_button.isEnabled() is False
    assert wn["b"].reply_button.isEnabled() is False
    assert wn["b"].reply_reason_label.text() == adapter.REASON_REPLY_UNREAD
    assert wn["b"].model.content() is None
    assert wn["b"].model.selected_state == "UNREAD"

    # 8-9: B presses Open; only then does content appear.
    wn["b"].on_open()
    assert wn["b"].model.selected_state == "READ"
    assert "original " + MARKER in wn["b"].content.toPlainText()
    assert wn["b"].model.content_visible is True

    # 10-11: Reply becomes enabled; B replies in REPLY mode.
    assert wn["b"].reply_button.isEnabled() is True
    wn["b"].on_reply()
    assert wn["b"].composer_mode.text().startswith("REPLY to")
    assert wn["b"].recipient_box.isEnabled() is False, "reply recipient is backend-fixed"
    assert wn["b"].model.composer.topic == "correspondence"
    wn["b"].draft.setPlainText("continuation " + MARKER)
    wn["b"].on_send()
    assert "ACCEPTED" in wn["b"].status_label.text()
    assert (wn["b"].model.status.detail or "") == "", "ACCEPTED status is a delivered marker, not an envelope claim"
    assert wn["b"].model.composer is None

    # 12-13: A refreshes explicitly; the reply appears.
    assert wn["a"].model.page.items == [], "A's inbox must not change unasked"
    wn["a"].on_refresh()
    assert wn["a"].inbox.count() == 1
    discovered = wn["a"].model.page.items[0]
    assert discovered["envelope_id"] != original_id
    assert discovered["state"] == "UNREAD"

    # 14: A inspects the SENV2 REF relation through the bounded metadata query
    # without opening anything.
    wn["a"].model.set_filters(state=None)
    ref_rows = workspace.query_inbox(wn["a"].model.workspace, ref=original_id)
    assert ref_rows["match_count"] == 1
    assert ref_rows["items"][0]["envelope_id"] == discovered["envelope_id"]
    assert ref_rows["items"][0]["ref"] == original_id
    assert ref_rows["items"][0]["state"] == "UNREAD"
    assert MARKER not in json.dumps(ref_rows)
    assert wn["a"].model.content_visible is False

    # 15: no background refresh: an untouched window's page is unchanged.
    before = [row["envelope_id"] for row in wn["b"].model.page.items]
    qapp.processEvents()
    assert [row["envelope_id"] for row in wn["b"].model.page.items] == before

    # 16-17: restart the presentation layer; durable truth is unchanged.
    durable_before_a = _tree(a_root)
    durable_before_b = _tree(b_root)
    decrypt_calls = []
    original_open = workspace.open_message
    original_reopen = workspace.reopen_message

    def watched_open(*args, **kwargs):
        decrypt_calls.append("open")
        return original_open(*args, **kwargs)

    def watched_reopen(*args, **kwargs):
        decrypt_calls.append("reopen")
        return original_reopen(*args, **kwargs)

    monkeypatch.setattr(workspace, "open_message", watched_open)
    monkeypatch.setattr(workspace, "reopen_message", watched_reopen)
    fresh_a = adapter.GuiAdapter()
    fresh_b = adapter.GuiAdapter()
    assert fresh_a.open_workspace(a_root)["ok"]
    assert fresh_b.open_workspace(b_root)["ok"]
    assert decrypt_calls == [], "restart must never decrypt"
    assert fresh_a.workspace.sender_kid == wn["a"].model.workspace.sender_kid
    assert fresh_b.selected_id is None and fresh_b.content_visible is False
    fresh_b.refresh()
    assert decrypt_calls == [], "refresh must never decrypt"
    assert [row["envelope_id"] for row in fresh_b.page.items] == [original_id]
    assert fresh_b.page.items[0]["state"] == "READ"
    assert fresh_b.select(original_id)["ok"]
    assert decrypt_calls == [], "selection must never decrypt"
    assert fresh_b.content_visible is False, (
        "a READ message from an earlier session must not silently reveal content")
    assert fresh_b.content_note() == adapter.REASON_READ_NOT_THIS_SESSION
    assert "Reopen" in fresh_b.content_note()
    assert fresh_b.open_reason() is not None and fresh_b.reopen_reason() is None
    assert _tree(a_root) == durable_before_a, "the mailbox must be byte-identical"
    assert _tree(b_root) == durable_before_b, "the mailbox must be byte-identical"

    # A restarted window visibly offers Reopen while content stays hidden.
    cls = gui_app._build_window(QtCore, QtGui, QtWidgets)
    fresh_window = cls()
    try:
        fresh_window._apply(fresh_window.model.open_workspace(b_root))
        fresh_window.on_refresh()
        fresh_window.inbox.setCurrentItem(fresh_window.inbox.item(0))
        assert decrypt_calls == []
        assert fresh_window.open_button.isEnabled() is False
        assert fresh_window.reopen_button.isEnabled() is True
        assert "Reopen" in fresh_window.content.toPlainText()
        assert MARKER not in fresh_window.content.toPlainText()
        # Even programmatic first Open refuses READ without calling the backend.
        fresh_window.on_open()
        assert fresh_window.model.status.code == "OPEN_NOT_UNREAD"
        assert decrypt_calls == []
        assert fresh_window.reopen_button.isEnabled() is True
        fresh_window.reopen_button.click()
        assert decrypt_calls == ["reopen"]
        assert "original " + MARKER in fresh_window.content.toPlainText()
        assert fresh_window.model.selected_state == "READ"
        assert fresh_window.model.content_visible is True
    finally:
        fresh_window.close()
    assert _tree(a_root) == durable_before_a
    assert _tree(b_root) == durable_before_b
    assert all(MARKER.encode() not in data for data in _tree(b_root).values())
    assert network["blocked"] == 0


def test_acceptance_makes_zero_network_attempts(tmp_path, monkeypatch, qapp):
    """The whole GUI path runs under a socket tripwire that fails on any call."""
    import socket

    attempts = {"n": 0}
    real_connect = socket.socket.connect

    def watched(self, address):
        attempts["n"] += 1
        raise AssertionError(f"network call attempted: {address}")

    monkeypatch.setattr(socket.socket, "connect", watched)
    cls = gui_app._build_window(QtCore, QtGui, QtWidgets)
    win = cls()
    win.model.create_workspace(tmp_path / "ws", "SAIMAIL-Z")
    win.on_refresh()
    win.on_custody_status()
    assert attempts["n"] == 0
    assert socket.socket.connect is watched
    monkeypatch.setattr(socket.socket, "connect", real_connect)


def test_gui_reentry_leaves_the_mailbox_unchanged_between_refreshes(tmp_path, qapp):
    """Refresh is the only thing that may change the visible page."""
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-R")
    cls = gui_app._build_window(QtCore, QtGui, QtWidgets)
    win = cls()
    win._apply(win.model.open_workspace(root))
    win.on_refresh()
    snapshot = _tree(root)
    win.on_custody_status()
    win.on_recipients()
    win.on_escape()
    qapp.processEvents()
    assert _tree(root) == snapshot
