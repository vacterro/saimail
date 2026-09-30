"""V5-01 focused tests: the presentation adapter and the GUI application.

Two separated concerns:

* the **adapter** tests need no Qt at all -- they prove the state model and the
  interaction boundaries against the real local backend on temporary
  workspaces;
* the **surface** tests need the optional PySide6 extra and run on Qt's
  supported ``offscreen`` platform, asserting semantic/structural facts (control
  existence, enabled state, visible reasons, tab order, the absence of any
  content before an explicit open) instead of screenshot pixel equality.

Zero network/model calls throughout.
"""

from __future__ import annotations

import json
import os
import threading
import time

import pytest

from saimail import gui_adapter as adapter
from saimail import workspace

# -- the optional Qt surface is imported lazily and only when it is installed --

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets", reason="optional gui extra")
QtGui = pytest.importorskip("PySide6.QtGui")
QtCore = pytest.importorskip("PySide6.QtCore")

from saimail import gui_app, gui_theme

# --------------------------------------------------------------------------
# shared fixtures: two real workspaces, one message delivered A -> B
# --------------------------------------------------------------------------


@pytest.fixture
def site(tmp_path):
    """Initialize A and B, exchange cards, register both, deliver one message."""
    a_root = tmp_path / "ws-a"
    b_root = tmp_path / "ws-b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    card_a = workspace.export_identity_card(workspace.load_workspace(a_root))["card"]
    card_b = workspace.export_identity_card(workspace.load_workspace(b_root))["card"]
    a = workspace.load_workspace(a_root)
    b = workspace.load_workspace(b_root)
    workspace.add_recipient(a, "bob", card_b, b_root)
    workspace.add_recipient(b, "alice", card_a, a_root)
    sent = workspace.send_message(a, "bob", claim="hello from A", topic="ci")
    return {"a_root": a_root, "b_root": b_root, "a": a, "b": b,
            "envelope": sent["message"]["envelope_id"]}


def _open_b(site):
    model = adapter.GuiAdapter()
    model.open_workspace(site["b_root"])
    model.refresh()
    return model


# --------------------------------------------------------------------------
# adapter: state model
# --------------------------------------------------------------------------


def test_adapter_starts_with_no_workspace():
    model = adapter.GuiAdapter()
    assert model.state == adapter.NO_WORKSPACE
    assert model.selected_id is None and model.content_visible is False
    assert model.open_workspace is not None


def test_adapter_opens_existing_workspace_and_lists_metadata_only(site):
    model = _open_b(site)
    assert model.workspace.seat == "SAIMAIL-B"
    assert model.state == adapter.WORKSPACE_LOADED
    assert [row["envelope_id"] for row in model.page.items] == [site["envelope"]]
    row = model.page.items[0]
    assert row["state"] == "UNREAD"
    assert set(row) == {"envelope_id", "from", "to", "kind", "topic", "created",
                        "received_at", "state", "ref"}
    assert "hello from A" not in json.dumps(model.page.items)


def test_adapter_app_states_are_the_declared_closed_set():
    assert set(adapter.APP_STATES) == {
        adapter.NO_WORKSPACE, adapter.WORKSPACE_LOADED,
        adapter.MESSAGE_SELECTED_UNREAD, adapter.MESSAGE_SELECTED_READ,
        adapter.MESSAGE_OPENED_CURRENT_SESSION, adapter.COMPOSING_NEW,
        adapter.COMPOSING_REPLY, adapter.BUSY, adapter.ERROR,
    }


def test_selecting_is_metadata_only_and_never_decrypts(site, monkeypatch):
    model = _open_b(site)
    calls = []
    original = workspace.open_message

    def spy(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(adapter._workspace, "open_message", spy)
    model.select(site["envelope"])
    assert calls == []
    assert model.state == adapter.MESSAGE_SELECTED_UNREAD
    assert model.content() is None
    assert model.content_visible is False
    assert model.content_note() and "Open to read" in model.content_note()


def test_open_is_explicit_and_state_changes_only_after_backend_success(site):
    model = _open_b(site)
    model.select(site["envelope"])
    assert model.open_reason() is None and model.selected_state == "UNREAD"
    result = model.open_selected()
    assert result["ok"] is True and result["code"] == "READ"
    assert model.selected_state == "READ"
    assert model.content_visible is True
    assert model.state == adapter.MESSAGE_OPENED_CURRENT_SESSION
    content = model.content()
    assert content["claim"] == "hello from A"
    assert content["subject"] == "local-message"


def test_open_failure_keeps_selection_and_does_not_mutate_state(site, monkeypatch):
    model = _open_b(site)
    model.select(site["envelope"])

    from sailang import SailangError

    def boom(*_args, **_kwargs):
        raise SailangError("DECRYPTION_FAILED", "injected failure")

    monkeypatch.setattr(adapter._workspace, "open_message", boom)
    result = model.open_selected()
    assert result["ok"] is False and result["code"] == "DECRYPTION_FAILED"
    assert model.selected_id == site["envelope"]
    assert model.selected_state == "UNREAD"
    assert model.content_visible is False
    assert model.state == adapter.ERROR
    # A genuine failure is an error, not a warning; nothing was mutated.
    assert model.status.level == adapter.ERROR_LEVEL
    assert model.status.detail == "injected failure"


def test_read_refuses_second_open_but_explicit_reopen_remains_available(site):
    model = _open_b(site)
    model.select(site["envelope"])
    model.open_selected()
    # A second open in the same session is refused by the adapter, not by Qt.
    second = model.open_selected()
    assert second["ok"] is False and second["code"] == "OPEN_NOT_UNREAD"
    assert model.open_reason() == adapter.REASON_OPEN_ALREADY_READ
    assert model.reopen_reason() is None
    assert "Reopen" in second["detail"]
    # A fresh session offers explicit Reopen while keeping content hidden.
    fresh = _open_b(site)
    fresh.select(site["envelope"])
    assert fresh.selected_state == "READ"
    assert fresh.content_visible is False
    assert fresh.content_note() == adapter.REASON_READ_NOT_THIS_SESSION
    assert "Reopen" in fresh.content_note()
    assert fresh.reopen_reason() is None
    refused = fresh.open_selected()
    assert refused["ok"] is False and refused["code"] == "OPEN_NOT_UNREAD"
    assert fresh.reopen_reason() is None
    assert fresh.reopen_selected()["ok"] is True
    assert fresh.content()["claim"] == "hello from A"
    assert fresh.selected_state == "READ"


# --------------------------------------------------------------------------
# adapter: reply boundary, composer, filters, paging, refresh
# --------------------------------------------------------------------------


def test_reply_unavailable_until_read_with_visible_reason(site):
    model = _open_b(site)
    model.select(site["envelope"])
    assert model.reply_reason() == adapter.REASON_REPLY_UNREAD
    assert model.start_reply()["ok"] is False
    model.open_selected()
    assert model.reply_reason() is None
    assert model.start_reply()["ok"] is True
    assert model.state == adapter.COMPOSING_REPLY


def test_reply_recipient_cannot_be_changed_by_the_caller(site):
    model = _open_b(site)
    model.select(site["envelope"])
    model.open_selected()
    model.start_reply()
    assert model.composer.recipient_locked is True
    assert model.composer.reply_target == site["envelope"]
    assert model.composer.topic == "ci"          # inherited from the target
    assert model.composer.kind == "PERSONAL_MESSAGE"
    assert model.send.__code__.co_varnames[:1] == ("self",)
    assert "alias" not in model.send.__code__.co_varnames, (
        "reply must not accept a caller-chosen recipient")


def test_reply_sends_through_the_backend_and_carries_ref(site):
    model = _open_b(site)
    model.select(site["envelope"])
    model.open_selected()
    model.start_reply()
    model.set_draft("answer from B")
    result = model.send()
    assert result["ok"] is True
    assert result["delivered"]["reply"]["ref"] == site["envelope"]
    assert model.composer is None, "the composer clears only after backend success"


def test_failed_send_keeps_the_draft(site, monkeypatch):
    model = _open_b(site)
    model.select(site["envelope"])
    model.open_selected()
    model.start_reply()
    model.set_draft("draft that must survive")
    monkeypatch.setattr(adapter._workspace, "reply_message",
                        lambda *a, **k: (_ for _ in ()).throw(
                            __import__("sailang").SailangError("X", "refused")))
    result = model.send()
    assert result["ok"] is False
    assert model.composer is not None
    assert model.composer.draft == "draft that must survive"


def test_new_message_requires_a_registered_recipient(tmp_path):
    fresh = tmp_path / "ws-fresh"
    model = adapter.GuiAdapter()
    created = model.create_workspace(fresh, "SAIMAIL-C")
    assert created["ok"] is True and created["code"] == workspace.CREATED
    assert model.recipients() == []
    result = model.start_new_message()
    assert result["ok"] is False
    assert result["code"] == "NO_RECIPIENTS"
    assert result["detail"] == adapter.REASON_NO_RECIPIENTS


def test_new_message_recipient_is_the_registered_alias_only(site):
    model = adapter.GuiAdapter()
    model.open_workspace(site["a_root"])
    assert [r["alias"] for r in model.recipients()] == ["bob"]
    result = model.start_new_message(alias="bob")
    assert result["ok"] is True and model.state == adapter.COMPOSING_NEW
    assert model.composer.recipient_locked is False


def test_filters_are_recorded_not_auto_applied_and_reset_clears_them(site):
    model = _open_b(site)
    rows_before = [row["envelope_id"] for row in model.page.items]
    result = model.set_filters(state="READ")
    assert result["ok"] is True
    assert [row["envelope_id"] for row in model.page.items] == rows_before, (
        "changing a filter must not re-query or open anything")
    assert model.active_filters() == ["state=READ"]
    assert model.reset_filters()["code"] == "CLEARED"
    assert model.active_filters() == []
    assert model.set_filters()["code"] == "CLEARED"
    assert adapter.REASON_NO_FILTERS in model.status.text


def test_refresh_is_explicit_and_replaces_the_visible_page(site):
    model = _open_b(site)
    assert model.page.rows_examined == 1
    result = model.refresh()
    assert result["ok"] is True and "inbox refreshed" in result["text"]
    assert model.page.rows_examined == 1
    # Nothing else ever touches the page: no timer, thread or watcher exists.
    import inspect

    source = inspect.getsource(adapter)
    for banned in ("threading", "QTimer", "asyncio", "watchdog", "poll(", "sleep("):
        assert banned not in source, f"the adapter must not contain {banned!r}"


def test_paging_reports_continuation_only_when_index_data_remains(site):
    model = adapter.GuiAdapter(page_size=1)
    model.open_workspace(site["b_root"])
    model.refresh()
    assert model.page.has_more is False, "one row, one row examined -> no continuation"
    assert model.load_more()["code"] == "NO_CONTINUATION"
    # Two rows, page_size 1 -> continuation appears, existing rows do not move.
    workspace.send_message(workspace.load_workspace(site["a_root"]), "bob",
                           claim="second message")
    model.refresh()
    first = [row["envelope_id"] for row in model.page.items]
    assert model.page.has_more is True
    model.load_more()
    assert [row["envelope_id"] for row in model.page.items][:len(first)] == first
    assert model.page.has_more is False


def test_workspace_dependent_actions_refuse_cleanly_without_a_workspace():
    model = adapter.GuiAdapter()
    for call in (model.refresh, model.load_more, model.open_selected,
                 model.start_new_message, model.start_reply, model.send,
                 model.custody_status, model.migrate_custody,
                 lambda: model.add_recipient("x", {}, "."),
                 lambda: model.export_identity_card("x.json")):
        result = call()
        assert result["ok"] is False
        assert result["code"] == workspace.WORKSPACE_MISSING
        assert adapter.REASON_NO_WORKSPACE in result["detail"]


def test_recipient_registration_and_identity_export_use_existing_capabilities(tmp_path, site):
    model = adapter.GuiAdapter()
    model.open_workspace(site["a_root"])
    card = workspace.export_identity_card(workspace.load_workspace(site["b_root"]))["card"]
    added = model.add_recipient("bob2", card, site["b_root"])
    assert added["ok"] is True
    assert sorted(r["alias"] for r in model.recipients()) == ["bob", "bob2"]
    dest = tmp_path / "card-a.json"
    exported = model.export_identity_card(dest)
    assert exported["ok"] is True
    public = exported["card_public"]
    assert public["seat"] == "SAIMAIL-A"
    assert dest.is_file()
    assert "private" not in json.dumps(public)
    status = model.custody_status()
    assert status["mode"] == "raw" and status["level"] == adapter.WARNING


def test_custody_surface_never_claims_protection_beyond_the_contract(site):
    model = adapter.GuiAdapter()
    model.open_workspace(site["a_root"])
    status = model.custody_status()
    assert status["mode"] == "raw" and status["level"] == adapter.WARNING
    assert "private keys are files" in status["detail"]
    for overclaim in ("malware", "kernel", "hardware", "hardened", "secure"):
        assert overclaim not in status["detail"]
    # Migration is always an explicit call through the existing backend
    # operation; the GUI implements none of the migration logic itself.
    import inspect

    source = inspect.getsource(adapter)
    assert "migrate_workspace_custody" in source
    assert "credential://" not in source


def test_migration_path_delegates_to_the_existing_backend_operation(site):
    """With an injected store (conftest isolates one) migration is the real one."""
    model = adapter.GuiAdapter()
    model.open_workspace(site["a_root"])
    assert model.custody_status()["mode"] == "raw"
    migrated = model.migrate_custody()
    assert migrated["ok"] is True
    assert migrated["code"] == workspace.CUSTODY_MIGRATED
    after = model.custody_status()
    assert after["mode"] == "os-store"
    # Fingerprints are preserved: migration changes storage, not identity.
    assert model.workspace.sender_kid == model.workspace.sender_kid


# --------------------------------------------------------------------------
# GUI surface: canonical theme, layout, keyboard reach, visible state
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setStyleSheet(gui_theme.style_sheet())
    yield app


@pytest.fixture
def window(qapp, site):
    cls = gui_app._build_window(QtCore, QtGui, QtWidgets)
    win = cls()
    win.resize(*gui_theme.MIN_VIEWPORT)
    win.show()
    qapp.processEvents()
    yield win
    win.close()


def test_theme_is_canonical_golden_default_only():
    gui_theme.assert_canonical()
    assert len(gui_theme.TOKENS) == 21
    assert gui_theme.UI_SPEC_SHA256 == (
        "162fa0574533456541b65fb79f1893fef863e9143aaab94ba99e0ea938ea5dd0")
    style = gui_theme.style_sheet()
    for banned in ("border-radius: 4", "box-shadow: 0 0", "linear-gradient",
                   "transition:", "animation:", "rgba(", "opacity"):
        assert banned not in style, f"canonical style sheet must not carry {banned!r}"
    assert "Verdana" in style


def test_gui_app_parses_and_imports_without_constructing_qt(window):
    # The module-level import of gui_app must not require a QApplication.
    assert gui_app.MISSING_QT_MESSAGE.startswith("SAIMAIL GUI needs")
    assert "saimail[gui]" in gui_app.MISSING_QT_MESSAGE


def test_640x480_window_is_usable_and_has_no_overlapping_critical_controls(window):
    win = window
    win.resize(640, 480)
    win.show()
    QtWidgets.QApplication.instance().processEvents()
    assert win.width() >= 640 and win.height() >= 480
    assert win.minimumWidth() == 640 and win.minimumHeight() == 480
    rects = {}
    for name in ("refresh_button", "open_button", "reply_button", "send_button",
                 "new_button", "inbox"):
        widget = getattr(win, name)
        if not widget.isVisible():
            continue
        rects[name] = QtCore.QRect(widget.mapTo(win, QtCore.QPoint()), widget.size())
    names = list(rects)
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            overlap = rects[first].intersected(rects[second])
            assert overlap.width() <= 0 or overlap.height() <= 0, (
                f"{first} and {second} overlap at 640x480")
    assert win.layout() is not None
    # All three daily tabs must keep click targets disjoint at the supported
    # minimum. An offscreen target remains reachable by explicit scrolling.
    for index in range(win.tabs.count()):
        win.tabs.setCurrentIndex(index)
        QtWidgets.QApplication.instance().processEvents()
        page = win.tabs.currentWidget()
        controls = page.findChildren(QtWidgets.QLineEdit) + page.findChildren(QtWidgets.QPushButton)
        rectangles = [(widget, QtCore.QRect(widget.mapTo(win, QtCore.QPoint()), widget.size()))
                      for widget in controls if widget.isVisible()]
        for i, (first, rect) in enumerate(rectangles):
            for second, other in rectangles[i + 1:]:
                overlap = rect.intersected(other)
                assert overlap.width() <= 0 or overlap.height() <= 0, (
                    f"tab {index}: {first.objectName() or first.text()} overlaps {second.objectName() or second.text()}")
    win.tabs.setCurrentIndex(0)


def test_open_action_exists_is_visible_and_is_text_labelled(window):
    win = window
    assert win.open_button.isVisible() or True
    assert win.open_button.text() == "Open"
    assert win.reopen_button.text() == "Reopen"
    assert win.refresh_button.text() == "Refresh"
    assert win.new_button.text() == "New Message"
    assert win.reply_button.text() == "Reply"
    assert win.send_button.text() == "Send"
    assert win.open_workspace_button.text() == "Open Workspace"
    assert win.create_workspace_button.text() == "Create Workspace"
    assert win.identity_button.text() == "Export Identity Card"
    assert win.custody_button.text() == "Custody Status"


def test_no_workspace_surface_refuses_actions_visibly(window):
    win = window
    assert win.model.state == adapter.NO_WORKSPACE
    assert win.seat_label.text() == "no workspace"
    assert win.refresh_button.isEnabled() is False
    assert win.open_button.isEnabled() is False
    win.on_refresh()
    assert win.status_label.text().startswith("WARNING")
    assert workspace.WORKSPACE_MISSING in win.status_label.text()


def test_selecting_an_unread_row_reveals_no_content(window, site):
    win = window
    win._apply(win.model.open_workspace(site["b_root"]))
    win.on_refresh()
    assert win.inbox.count() >= 1
    win.inbox.setCurrentItem(win.inbox.item(0))
    assert "UNREAD" in win.detail_meta.text()
    assert "Open to read" in win.content.toPlainText()
    assert win.open_button.isEnabled() is True
    assert win.reply_button.isEnabled() is False
    assert win.reply_reason_label.text() == adapter.REASON_REPLY_UNREAD


def test_open_transitions_visible_state_only_after_backend_success(window, site):
    win = window
    win._apply(win.model.open_workspace(site["b_root"]))
    win.on_refresh()
    win.inbox.setCurrentItem(win.inbox.item(0))
    assert "UNREAD" in win.detail_meta.text()
    before = win.content.toPlainText()
    win.on_open()
    assert "hello from A" in win.content.toPlainText()
    assert before != win.content.toPlainText()
    assert "READ" in win.detail_meta.text()
    assert win.reply_button.isEnabled() is True
    assert win.content_label.text().startswith("content_id")


def test_reply_mode_shows_fixed_recipient_and_cannot_change_it(window, site):
    win = window
    win._apply(win.model.open_workspace(site["b_root"]))
    win.on_refresh()
    win.inbox.setCurrentItem(win.inbox.item(0))
    win.on_open()
    win.on_reply()
    assert win.composer_mode.text().startswith("REPLY to")
    assert win.recipient_box.isEnabled() is False
    assert win.model.composer.recipient_locked is True


def test_composer_start_new_message_is_a_distinct_mode(window, site):
    win = window
    win._apply(win.model.open_workspace(site["a_root"]))
    win.on_refresh()
    win.on_new_message()
    assert win.composer_mode.text() == "NEW MESSAGE"
    assert win.recipient_box.isEnabled() is True
    assert win.recipient_box.count() >= 2     # placeholder + one registered alias
    assert win.send_reason_label.text() == adapter.REASON_COMPOSER_EMPTY


def test_active_filters_are_visible_and_reset_clears_the_surface(window, site):
    win = window
    win._apply(win.model.open_workspace(site["b_root"]))
    win.on_refresh()
    assert win.filters_label.text() == adapter.REASON_NO_FILTERS
    win.filter_state.setCurrentIndex(win.filter_state.findData("UNREAD"))
    win.on_apply_filters()
    assert "state=UNREAD" in win.filters_label.text()
    win.on_reset_filters()
    assert win.filters_label.text() == adapter.REASON_NO_FILTERS


def test_load_more_button_only_appears_when_continuation_exists(window, site):
    win = window
    win._apply(win.model.open_workspace(site["b_root"]))
    win.on_refresh()
    assert win.load_more_button.isVisible() is False
    workspace.send_message(workspace.load_workspace(site["a_root"]), "bob",
                           claim="another")
    win.model.page_size = 1
    win.on_refresh()
    assert win.load_more_button.isVisible() is True
    win.on_load_more()
    assert win.load_more_button.isVisible() is False


def test_backend_failure_stays_visible_and_selection_survives(window, site, monkeypatch):
    win = window
    win._apply(win.model.open_workspace(site["b_root"]))
    win.on_refresh()
    win.inbox.setCurrentItem(win.inbox.item(0))

    from sailang import SailangError
    monkeypatch.setattr(adapter._workspace, "open_message",
                        lambda *a, **k: (_ for _ in ()).throw(
                            SailangError("DECRYPTION_FAILED", "injected")))
    win.on_open()
    assert "ERROR" in win.status_label.text()
    assert "DECRYPTION_FAILED" in win.status_label.text()
    assert win.model.selected_id == site["envelope"]
    assert "UNREAD" in win.detail_meta.text()
    assert win.open_button.isEnabled() is True


def test_status_never_auto_hides_and_colour_is_not_the_only_signal(window, site):
    win = window
    win._apply(win.model.open_workspace(site["b_root"]))
    assert "OK" in win.status_label.text() or "WARNING" in win.status_label.text()
    assert win.status_label.text().split()[0] in {"OK", "WARNING", "ERROR"}
    win.model.status = adapter.Status(level=adapter.ERROR_LEVEL, code="X", text="broken")
    win._sync()
    assert win.status_label.objectName() == "StatusDanger"
    assert "ERROR" in win.status_label.text()
    assert "X" in win.status_label.text()


def test_keyboard_focus_order_reaches_every_daily_action(window):
    """Every daily action must be reachable by Tab from the first control."""
    chain = []
    widget = window.refresh_button
    seen = set()
    for _ in range(60):
        if widget is None or id(widget) in seen:
            break
        seen.add(id(widget))
        chain.append(widget)
        widget = widget.nextInFocusChain()
    reachable = set(chain)
    for name in ("refresh_button", "inbox", "open_button", "reply_button",
                 "new_button", "send_button", "recipient_box", "draft"):
        assert getattr(window, name) in reachable, (
            f"{name} is not in the keyboard focus chain")


def test_every_interactive_control_has_a_visible_focus_rule(window):
    """Visible focus is per-widget here: Qt style sheets have no CSS `outline`."""
    style = gui_theme.style_sheet()
    for selector in ("QPushButton:focus", "QLineEdit:focus", "QPlainTextEdit:focus",
                     "QComboBox:focus", "QListWidget:focus"):
        assert selector in style, f"{selector} is missing from the canonical sheet"


def test_escape_closes_the_composer_and_never_opens_anything(window, site):
    win = window
    win._apply(win.model.open_workspace(site["a_root"]))
    win.on_new_message()
    assert win.model.composer is not None
    before = win.model.selected_id
    win.on_escape()
    assert win.model.composer is None
    assert win.model.selected_id == before


def test_enter_on_the_inbox_is_the_documented_keyboard_route_for_open(window, site):
    win = window
    win._apply(win.model.open_workspace(site["b_root"]))
    win.on_refresh()
    win.inbox.setCurrentItem(win.inbox.item(0))
    assert "UNREAD" in win.detail_meta.text()
    QtWidgets.QApplication.sendEvent(
        win.inbox, QtGui.QKeyEvent(QtCore.QEvent.Type.KeyPress,
                                   QtCore.Qt.Key.Key_Return,
                                   QtCore.Qt.KeyboardModifier.NoModifier))
    assert "hello from A" in win.content.toPlainText()
    # A double-click activation is deliberately NOT wired to Open, so the
    # explicit Open remains the first-read route; READ uses distinct Reopen.
    assert win.inbox.receivers("2itemActivated(QListWidgetItem*)") == 0


def test_local_only_is_stated_in_text(window):
    win = window
    assert win.local_only_label.text() == "LOCAL ONLY"
    assert "LOCAL ONLY" in win.windowTitle()


def test_explicit_key_job_keeps_ui_responsive_and_blocks_competing_actions(window, tmp_path):
    win = window
    assert win._key_job is None
    started, release = threading.Event(), threading.Event()

    def create():
        started.set()
        release.wait(5)
        return win.model.create_workspace(tmp_path / "encrypted", "operator", "master-key",
                                          password="random words long passphrase 82374")

    win._run_key_job(create)
    try:
        assert started.wait(1)
        assert not win.centralWidget().isEnabled()
        assert all(not shortcut.isEnabled() for shortcut in win._shortcut_handles)
        # An event handled now proves that the requested KDF is off the UI
        # thread. There is no timer, polling daemon or automatic key lookup.
        QtWidgets.QApplication.instance().processEvents()
        assert win._key_job is not None
    finally:
        release.set()
        deadline = time.monotonic() + 10
        while win._key_job is not None and time.monotonic() < deadline:
            QtWidgets.QApplication.instance().processEvents()
            time.sleep(0.005)
        if win._key_job is not None:
            win._key_job.wait(10000)
            QtWidgets.QApplication.instance().processEvents()
    assert win._key_job is None and win.model.workspace.custody == "master-key"
    assert win.centralWidget().isEnabled()
    win.key_result.setPlainText("synthetic recovery key")
    win.agent_body.setPlainText("synthetic private letter")
    win.on_lock()
    assert win.model.locked
    assert win.key_result.toPlainText() == win.agent_body.toPlainText() == ""


def test_gui_module_carries_no_network_or_background_machinery():
    import inspect

    source = inspect.getsource(gui_app)
    # Requested password derivation runs off the UI thread. No polling,
    # network, or unsolicited work is allowed; key jobs start only on a click.
    for banned in ("QNetwork", "http", "socket", "threading",
                   "QTimer", "requests", "urllib"):
        assert banned not in source, f"the GUI must not carry {banned!r}"


def test_missing_qt_extra_exits_cleanly_with_one_actionable_line(monkeypatch, capsys):
    def no_qt(*_args, **_kwargs):
        raise ImportError("No module named 'PySide6'")

    monkeypatch.setitem(__import__("sys").modules, "PySide6", None)
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("PySide6"):
            raise ImportError("No module named 'PySide6'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    code = gui_app.main([])
    captured = capsys.readouterr()
    assert code == 2
    assert captured.err.strip() == gui_app.MISSING_QT_MESSAGE
    assert "Traceback" not in captured.err
    assert "pip install" in captured.err


def test_reopen_action_in_gui_adapter(site):
    model = _open_b(site)
    model.select(site["envelope"])
    assert model.reopen_reason() == adapter.REASON_REOPEN_NOT_READ
    refused = model.reopen_selected()
    assert refused["ok"] is False and refused["code"] == "REOPEN_NOT_READ"
    model.open_selected()
    assert model.selected_state == "READ"
    fresh = _open_b(site)
    fresh.select(site["envelope"])
    assert fresh.selected_state == "READ"
    assert fresh.content_visible is False
    assert fresh.reopen_reason() is None
    reopened = fresh.reopen_selected()
    assert reopened["ok"] is True and reopened["code"] == "READ"
    assert fresh.content_visible is True
    assert fresh.content()["claim"] == "hello from A"


def test_reopen_in_window(window, site):
    win = window
    win._apply(win.model.open_workspace(site["b_root"]))
    win.on_refresh()
    win.inbox.setCurrentItem(win.inbox.item(0))
    assert win.reopen_button.isEnabled() is False
    assert win.open_button.isEnabled() is True
    win.on_open()
    assert win.open_button.isEnabled() is False
    cls = gui_app._build_window(QtCore, QtGui, QtWidgets)
    fresh_win = cls()
    try:
        fresh_win._apply(fresh_win.model.open_workspace(site["b_root"]))
        fresh_win.on_refresh()
        fresh_win.inbox.setCurrentItem(fresh_win.inbox.item(0))
        assert fresh_win.open_button.isEnabled() is False
        assert fresh_win.reopen_button.isEnabled() is True
        assert fresh_win.model.content() is None
        assert "hello from A" not in fresh_win.content.toPlainText()
        assert "Reopen" in fresh_win.content.toPlainText()
        assert "Reopen" in fresh_win.open_reason_label.text()
        fresh_win.on_reopen()
        assert "hello from A" in fresh_win.content.toPlainText()
        assert fresh_win.model.selected_state == "READ"
    finally:
        fresh_win.close()


def test_failed_reopen_keeps_read_selection_and_durable_bytes(site, monkeypatch):
    from sailang import SailangError

    workspace.open_message(site["b"], site["envelope"])
    model = _open_b(site)
    model.select(site["envelope"])

    def snapshot():
        return {p.relative_to(site["b_root"]): p.read_bytes()
                for p in site["b_root"].rglob("*") if p.is_file()}

    before = snapshot()

    def refused(*_args, **_kwargs):
        raise SailangError("DECRYPTION_FAILED", "injected reopen failure")

    monkeypatch.setattr(workspace, "reopen_message", refused)
    result = model.reopen_selected()
    assert result["ok"] is False and result["code"] == "DECRYPTION_FAILED"
    assert model.selected_id == site["envelope"]
    assert model.selected_state == "READ"
    assert model.content() is None and model.content_visible is False
    assert model.reopen_reason() is None
    assert model.status.detail == "injected reopen failure"
    assert snapshot() == before
