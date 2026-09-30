"""SAIMAIL desktop client (V5-01) -- the GUI presentation surface.

Qt is an **optional** dependency: this module is imported lazily by the
``saimail-gui`` entrypoint only. Importing :mod:`saimail` or running the
``saimail-local`` CLI never touches it, and a core install without the ``gui``
extra gets one bounded actionable error instead of a traceback.

The window is pure presentation. Every action is forwarded to
:class:`saimail.gui_adapter.GuiAdapter`, which in turn calls only the existing
tested public API. Nothing here parses a Post Office file, decrypts an
envelope, resolves an identity, deduplicates, mutates lifecycle state or reaches
the network.

Visual values come from :mod:`saimail.gui_theme`, the single transcription of
the canonical ``<saipen_home>/saipen/UI.md`` Golden Default palette.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from saimail import gui_adapter as adapter
from saimail import gui_theme as theme

MISSING_QT_MESSAGE = (
    "SAIMAIL GUI needs the optional GUI dependency.\n"
    "Install it with:  pip install \"saimail[gui]\"\n"
    "The command-line client (saimail-local) works without it."
)


def _require_qt():
    """Import PySide6 or exit cleanly with one actionable line, no traceback."""
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        print(MISSING_QT_MESSAGE, file=sys.stderr)
        return None
    return QtCore, QtGui, QtWidgets


def _build_window(QtCore, QtGui, QtWidgets, page_size: int = adapter.DEFAULT_PAGE_SIZE):
    """Construct the main window class against the imported Qt modules."""

    def _panel(title: str):
        box = QtWidgets.QGroupBox(title)
        box.setObjectName("Panel")
        return box

    def _label(text: str, name: str = "MetadataLabel"):
        widget = QtWidgets.QLabel(text)
        widget.setObjectName(name)
        widget.setWordWrap(True)
        return widget

    class InboxList(QtWidgets.QListWidget):
        """The inbox list. Enter is the documented keyboard route for Open.

        Double-click is deliberately NOT wired to Open: Qt would also fire
        ``itemActivated`` on a double-click, and silently decrypting on a
        double-click is exactly what the interaction contract forbids. So the
        list emits its own signal on Return/Enter only, and ``itemActivated``
        stays unconnected.
        """

        open_requested = QtCore.Signal()

        def keyPressEvent(self, event):
            if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                self.open_requested.emit()
                return
            super().keyPressEvent(event)

    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__()
            self.model = adapter.GuiAdapter(page_size=page_size)
            self.setWindowTitle("SAIMAIL — LOCAL ONLY")
            self.setMinimumSize(*theme.MIN_VIEWPORT)
            self.resize(*theme.CANONICAL_VIEWPORT)
            self._build()
            self._sync()

        # -- construction --------------------------------------------------

        def _build(self):
            root = QtWidgets.QWidget()
            self.setCentralWidget(root)
            outer = QtWidgets.QVBoxLayout(root)
            outer.setContentsMargins(12, 8, 12, 8)
            outer.setSpacing(8)

            outer.addWidget(self._title_region())
            outer.addWidget(self._mail_region(), 1)
            outer.addWidget(self._composer_region())
            outer.addWidget(self._rare_region())
            outer.addWidget(self._status_region())
            self._shortcuts()
            self._tab_order(root)

        def _title_region(self):
            bar = QtWidgets.QWidget()
            bar.setObjectName("TitleBar")
            row = QtWidgets.QHBoxLayout(bar)
            row.setContentsMargins(4, 4, 4, 4)
            row.setSpacing(8)
            self.title_label = _label("SAIMAIL", "TitleLabel")
            self.local_only_label = _label("LOCAL ONLY", "LocalOnlyLabel")
            self.seat_label = _label("no workspace", "MetadataLabel")
            self.custody_label = _label("custody —", "MetadataLabel")
            row.addWidget(self.title_label)
            row.addWidget(self.local_only_label)
            row.addWidget(self.seat_label)
            row.addWidget(self.custody_label)
            row.addStretch(1)
            self.refresh_button = QtWidgets.QPushButton("Refresh")
            self.refresh_button.setObjectName("Primary")
            self.refresh_button.clicked.connect(self.on_refresh)
            row.addWidget(self.refresh_button)
            return bar

        def _mail_region(self):
            split = QtWidgets.QSplitter()
            split.addWidget(self._inbox_region())
            split.addWidget(self._detail_region())
            split.setSizes([340, 280])
            return split

        def _inbox_region(self):
            box = _panel("Inbox")
            column = QtWidgets.QVBoxLayout(box)
            column.setContentsMargins(4, 4, 4, 4)
            column.setSpacing(4)

            filter_row = QtWidgets.QHBoxLayout()
            filter_row.setSpacing(4)
            self.filter_sender = QtWidgets.QLineEdit()
            self.filter_sender.setPlaceholderText("sender seat")
            self.filter_topic = QtWidgets.QLineEdit()
            self.filter_topic.setPlaceholderText("topic")
            self.filter_kind = QtWidgets.QComboBox()
            self.filter_kind.addItem("any kind", None)
            for kind in _KINDS:
                self.filter_kind.addItem(kind, kind)
            self.filter_state = QtWidgets.QComboBox()
            self.filter_state.addItem("any state", None)
            for state in ("UNREAD", "READ", "EXPIRED"):
                self.filter_state.addItem(state, state)
            filter_row.addWidget(_label("Sender", "MetadataLabel"))
            filter_row.addWidget(self.filter_sender)
            filter_row.addWidget(_label("Topic", "MetadataLabel"))
            filter_row.addWidget(self.filter_topic)
            filter_row.addWidget(_label("Kind", "MetadataLabel"))
            filter_row.addWidget(self.filter_kind)
            filter_row.addWidget(_label("State", "MetadataLabel"))
            filter_row.addWidget(self.filter_state)
            column.addLayout(filter_row)

            filter_buttons = QtWidgets.QHBoxLayout()
            filter_buttons.setSpacing(4)
            self.apply_filters_button = QtWidgets.QPushButton("Apply Filters")
            self.apply_filters_button.clicked.connect(self.on_apply_filters)
            self.reset_filters_button = QtWidgets.QPushButton("Reset Filters")
            self.reset_filters_button.clicked.connect(self.on_reset_filters)
            self.filters_label = _label(adapter.REASON_NO_FILTERS)
            filter_buttons.addWidget(self.apply_filters_button)
            filter_buttons.addWidget(self.reset_filters_button)
            filter_buttons.addWidget(self.filters_label, 1)
            column.addLayout(filter_buttons)

            self.inbox = InboxList()
            self.inbox.setObjectName("inbox")
            self.inbox.setUniformItemSizes(True)
            self.inbox.currentItemChanged.connect(self.on_select)
            self.inbox.open_requested.connect(self.on_open)
            column.addWidget(self.inbox, 1)

            self.load_more_button = QtWidgets.QPushButton("Load More")
            self.load_more_button.clicked.connect(self.on_load_more)
            column.addWidget(self.load_more_button)
            self.inbox_summary = _label("")
            column.addWidget(self.inbox_summary)
            return box

        def _detail_region(self):
            box = _panel("Message")
            column = QtWidgets.QVBoxLayout(box)
            column.setContentsMargins(4, 4, 4, 4)
            column.setSpacing(4)
            self.detail_meta = _label("Select a message. Metadata only — nothing is opened "
                                      "or decrypted until you press Open.")
            column.addWidget(self.detail_meta)

            actions = QtWidgets.QHBoxLayout()
            actions.setSpacing(4)
            self.open_button = QtWidgets.QPushButton("Open")
            self.open_button.setObjectName("Primary")
            self.open_button.clicked.connect(self.on_open)
            self.reply_button = QtWidgets.QPushButton("Reply")
            self.reply_button.clicked.connect(self.on_reply)
            actions.addWidget(self.open_button)
            actions.addWidget(self.reply_button)
            column.addLayout(actions)

            self.open_reason_label = _label("", "DisabledReason")
            self.reply_reason_label = _label("", "DisabledReason")
            column.addWidget(self.open_reason_label)
            column.addWidget(self.reply_reason_label)

            self.content = QtWidgets.QPlainTextEdit()
            self.content.setObjectName("content")
            self.content.setReadOnly(True)
            self.content.setPlainText("No content loaded.")
            column.addWidget(self.content, 1)
            self.content_label = _label("")
            column.addWidget(self.content_label)
            return box

        def _composer_region(self):
            box = _panel("Composer")
            column = QtWidgets.QVBoxLayout(box)
            column.setContentsMargins(4, 4, 4, 4)
            column.setSpacing(4)
            head = QtWidgets.QHBoxLayout()
            head.setSpacing(4)
            self.composer_mode = _label("no composer open", "SectionLabel")
            self.new_button = QtWidgets.QPushButton("New Message")
            self.new_button.clicked.connect(self.on_new_message)
            self.close_composer_button = QtWidgets.QPushButton("Close Composer")
            self.close_composer_button.clicked.connect(self.on_close_composer)
            head.addWidget(self.composer_mode)
            head.addStretch(1)
            head.addWidget(self.new_button)
            head.addWidget(self.close_composer_button)
            column.addLayout(head)

            fields = QtWidgets.QHBoxLayout()
            fields.setSpacing(4)
            self.recipient_box = QtWidgets.QComboBox()
            self.recipient_box.setObjectName("recipient")
            fields.addWidget(_label("Recipient", "MetadataLabel"))
            fields.addWidget(self.recipient_box)
            fields.addWidget(_label("Subject", "MetadataLabel"))
            self.subject_edit = QtWidgets.QLineEdit("local-message")
            fields.addWidget(self.subject_edit)
            fields.addWidget(_label("Topic", "MetadataLabel"))
            self.topic_edit = QtWidgets.QLineEdit("")
            self.topic_edit.setPlaceholderText("local-message")
            fields.addWidget(self.topic_edit)
            column.addLayout(fields)

            self.draft = QtWidgets.QPlainTextEdit()
            self.draft.setObjectName("draft")
            self.draft.setPlaceholderText("one line of operator text")
            column.addWidget(self.draft, 1)

            send_row = QtWidgets.QHBoxLayout()
            send_row.setSpacing(4)
            self.send_button = QtWidgets.QPushButton("Send")
            self.send_button.setObjectName("Primary")
            self.send_button.clicked.connect(self.on_send)
            self.send_reason_label = _label("", "DisabledReason")
            send_row.addWidget(self.send_button)
            send_row.addWidget(self.send_reason_label, 1)
            column.addLayout(send_row)
            return box

        def _rare_region(self):
            box = _panel("Workspace, Recipients, Identity, Custody")
            row = QtWidgets.QHBoxLayout(box)
            row.setContentsMargins(4, 4, 4, 4)
            row.setSpacing(4)
            self.open_workspace_button = QtWidgets.QPushButton("Open Workspace")
            self.open_workspace_button.clicked.connect(self.on_open_workspace)
            self.create_workspace_button = QtWidgets.QPushButton("Create Workspace")
            self.create_workspace_button.clicked.connect(self.on_create_workspace)
            self.recipients_button = QtWidgets.QPushButton("Recipients")
            self.recipients_button.clicked.connect(self.on_recipients)
            self.identity_button = QtWidgets.QPushButton("Export Identity Card")
            self.identity_button.clicked.connect(self.on_export_identity)
            self.custody_button = QtWidgets.QPushButton("Custody Status")
            self.custody_button.clicked.connect(self.on_custody_status)
            self.migrate_button = QtWidgets.QPushButton("Migrate Custody")
            self.migrate_button.clicked.connect(self.on_migrate_custody)
            for widget in (self.open_workspace_button, self.create_workspace_button,
                           self.recipients_button, self.identity_button,
                           self.custody_button, self.migrate_button):
                row.addWidget(widget)
            row.addStretch(1)
            return box

        def _status_region(self):
            strip = QtWidgets.QWidget()
            strip.setObjectName("StatusStrip")
            row = QtWidgets.QVBoxLayout(strip)
            row.setContentsMargins(4, 2, 4, 2)
            row.setSpacing(2)
            self.status_label = QtWidgets.QLabel(adapter.Status().text)
            self.status_label.setObjectName("StatusText")
            self.status_detail = _label("", "MetadataLabel")
            row.addWidget(self.status_label)
            row.addWidget(self.status_detail)
            return strip

        def _shortcuts(self):
            bindings = (
                ("Ctrl+O", self.on_open_workspace),
                ("Ctrl+R", self.on_refresh),
                ("Ctrl+N", self.on_new_message),
                ("Ctrl+Shift+R", self.on_reply),
                ("Ctrl+Return", self.on_send),
                ("Ctrl+M", self.on_load_more),
                ("Ctrl+Shift+F", self.on_reset_filters),
                ("Esc", self.on_close_composer),
            )
            for sequence, handler in bindings:
                shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self)
                shortcut.activated.connect(handler)

        def _tab_order(self, root):
            """One explicit focus chain: daily actions before rare ones."""
            chain = [
                self.refresh_button, self.filter_sender, self.filter_topic,
                self.filter_kind, self.filter_state, self.apply_filters_button,
                self.reset_filters_button, self.inbox, self.load_more_button,
                self.open_button, self.reply_button, self.content,
                self.recipient_box, self.subject_edit, self.topic_edit, self.draft,
                self.send_button, self.new_button, self.close_composer_button,
                self.open_workspace_button, self.create_workspace_button,
                self.recipients_button, self.identity_button, self.custody_button,
                self.migrate_button,
            ]
            for previous, following in zip(chain, chain[1:]):
                QtWidgets.QWidget.setTabOrder(previous, following)

        # -- rendering -----------------------------------------------------

        def _sync(self):
            """Draw presentation state from the adapter. No hidden mutation."""
            model = self.model
            loaded = model.workspace is not None
            self.seat_label.setText(
                f"seat {model.workspace.seat}" if loaded else "no workspace")
            self.custody_label.setText(
                f"custody {model.workspace.custody}" if loaded else "custody —")
            self.refresh_button.setEnabled(loaded)
            for widget in (self.recipient_box, self.subject_edit, self.topic_edit,
                           self.draft, self.send_button):
                widget.setEnabled(loaded)
            self._draw_inbox()
            self._draw_detail()
            self._draw_composer()
            self._draw_status()

        def _draw_inbox(self):
            self.inbox.blockSignals(True)
            self.inbox.clear()
            for item in self.model.page.items:
                row = QtWidgets.QListWidgetItem(
                    f"{item['state']:<7} {item['from']}  {item['topic']}  "
                    f"{item['received_at']}")
                row.setData(QtCore.Qt.ItemDataRole.UserRole, item["envelope_id"])
                self.inbox.addItem(row)
                if item["envelope_id"] == self.model.selected_id:
                    self.inbox.setCurrentItem(row)
            self.inbox.blockSignals(False)
            self.load_more_button.setVisible(self.model.page.has_more)
            active = self.model.active_filters()
            self.filters_label.setText(
                "filters active: " + ", ".join(active) if active
                else adapter.REASON_NO_FILTERS)
            self.inbox_summary.setText(
                f"{len(self.model.page.items)} row(s) shown, "
                f"{self.model.page.rows_examined} examined")

        def _draw_detail(self):
            row = self.model.selected_row
            if row is None:
                self.detail_meta.setText(
                    "Select a message. Metadata only — nothing is opened or decrypted "
                    "until you press Open.")
            else:
                self.detail_meta.setText(
                    f"FROM {row['from']}   KIND {row['kind']}   TOPIC {row['topic']}\n"
                    f"STATE {row['state']}   CREATED {row['created']}   "
                    f"RECEIVED {row['received_at']}\n"
                    + (f"REF {row['ref']}" if row.get("ref") else "REF —"))
            self.open_reason_label.setText(self.model.open_reason() or "")
            self.reply_reason_label.setText(self.model.reply_reason() or "")
            self.open_button.setEnabled(self.model.open_reason() is None)
            self.reply_button.setEnabled(self.model.reply_reason() is None)
            content = self.model.content()
            if content is None:
                note = self.model.content_note()
                self.content.setPlainText(note or "No content loaded.")
                self.content_label.setText("")
            else:
                self.content.setPlainText(
                    f"SUBJECT  {content.get('subject') or '—'}\n"
                    f"CLAIM    {content.get('claim') or '—'}\n"
                    f"FROM     {content.get('from')}\n"
                    f"KIND     {content.get('kind')}   TOPIC {content.get('topic')}\n"
                    f"RECEIVED {content.get('received_at')}\n"
                    f"STATUS   {content.get('status')}   "
                    f"EVIDENCE {content.get('evidence_state')}\n"
                    f"CONTENT_ID {content.get('content_id')}")
                self.content_label.setText(f"content_id {content.get('content_id')}")

        def _draw_composer(self):
            composer = self.model.composer
            if composer is None:
                self.composer_mode.setText("no composer open")
                self.recipient_box.setCurrentIndex(0 if self.recipient_box.count() else -1)
                self.recipient_box.setEnabled(False)
                self.subject_edit.setText("local-message")
                self.topic_edit.setText("")
                self.draft.setPlainText("")
            else:
                label = ("NEW MESSAGE" if composer.mode == adapter.COMPOSING_NEW
                         else f"REPLY to {composer.reply_target}")
                self.composer_mode.setText(label)
                self.recipient_box.setEnabled(not composer.recipient_locked)
                if composer.mode == adapter.COMPOSING_REPLY:
                    self.subject_edit.setText(composer.subject)
                    self.topic_edit.setText(composer.topic or "")
                elif composer.alias:
                    index = self.recipient_box.findData(composer.alias)
                    if index >= 0:
                        self.recipient_box.setCurrentIndex(index)
                self.draft.setPlainText(composer.draft)
            reason = self.model.send_reason()
            self.send_reason_label.setText(reason or "")
            self.send_button.setEnabled(reason is None)

        def _draw_status(self):
            status = self.model.status
            names = {adapter.OK: "StatusSuccess",
                     adapter.WARNING: "StatusWarning",
                     adapter.ERROR_LEVEL: "StatusDanger"}
            self.status_label.setObjectName(names.get(status.level, "StatusText"))
            self.status_label.setText(f"{status.level.upper()}  {status.code}  {status.text}")
            self.status_detail.setText(status.detail or "")
            style = self.status_label.style()
            style.unpolish(self.status_label)
            style.polish(self.status_label)

        # -- handlers ------------------------------------------------------

        def on_refresh(self):
            self._apply(self.model.refresh())
            self._reload_recipients()

        def on_load_more(self):
            self._apply(self.model.load_more())

        def on_select(self, current, _previous=None):
            if current is None:
                return
            envelope_id = current.data(QtCore.Qt.ItemDataRole.UserRole)
            self._apply(self.model.select(envelope_id))

        def on_open(self):
            self._apply(self.model.open_selected())

        def on_apply_filters(self):
            self._apply(self.model.set_filters(
                sender=self.filter_sender.text().strip() or None,
                topic=self.filter_topic.text().strip() or None,
                kind=self.filter_kind.currentData(),
                state=self.filter_state.currentData()))
            self._apply(self.model.refresh())

        def on_reset_filters(self):
            self.filter_sender.clear()
            self.filter_topic.clear()
            self.filter_kind.setCurrentIndex(0)
            self.filter_state.setCurrentIndex(0)
            self._apply(self.model.reset_filters())
            self._apply(self.model.refresh())

        def on_new_message(self):
            self._reload_recipients()
            result = self.model.start_new_message()
            self._apply(result)
            if result["ok"]:
                self.draft.setFocus()

        def on_reply(self):
            self._apply(self.model.start_reply())
            if self.model.composer is not None:
                self.draft.setFocus()

        def on_close_composer(self):
            self._apply(self.model.close_composer())

        def on_send(self):
            self.model.set_draft(self.draft.toPlainText())
            result = self.model.send()
            self._apply(result)
            if result["ok"]:
                self._reload_recipients()

        def on_open_workspace(self):
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Open Workspace")
            if not path:
                return
            self._apply(self.model.open_workspace(path))

        def on_create_workspace(self):
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Create Workspace In")
            if not path:
                return
            seat, ok = QtWidgets.QInputDialog.getText(self, "Create Workspace", "Seat")
            if not ok or not seat.strip():
                return
            custody, ok = QtWidgets.QInputDialog.getItem(
                self, "Create Workspace", "Custody",
                ["raw", "os-store"], 0, False)
            if not ok:
                return
            self._apply(self.model.create_workspace(path, seat.strip(), custody))

        def on_recipients(self):
            if self.model.workspace is None:
                self._apply(self.model.recipients() or {"ok": False})
                return
            self._reload_recipients()
            rows = self.model.recipients()
            detail = ", ".join(f"{r['alias']}@{r['seat']}" for r in rows) or "(none)"
            self._apply({"ok": True, "command": "recipient-list", "code": "OK",
                         "text": f"{len(rows)} recipient(s): {detail}"})
            self._add_recipient_dialog()

        def _add_recipient_dialog(self):
            card = QtWidgets.QFileDialog.getOpenFileName(
                self, "Recipient identity card", "", "JSON (*.json)")[0]
            if not card:
                return
            peer = QtWidgets.QFileDialog.getExistingDirectory(
                self, "Recipient workspace root")
            if not peer:
                return
            alias, ok = QtWidgets.QInputDialog.getText(self, "Add Recipient", "Alias")
            if not ok or not alias.strip():
                return
            try:
                payload = json.loads(Path(card).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                self._apply({"ok": False, "command": "recipient-add",
                             "code": "RECIPIENT_MALFORMED",
                             "text": f"identity card is unreadable: {exc}"})
                return
            self._apply(self.model.add_recipient(alias.strip(), payload, peer))

        def on_export_identity(self):
            dest = QtWidgets.QFileDialog.getSaveFileName(
                self, "Export public identity card", "identity-card.json",
                "JSON (*.json)")[0]
            if not dest:
                return
            self._apply(self.model.export_identity_card(dest))

        def on_custody_status(self):
            self._apply(self.model.custody_status())

        def on_migrate_custody(self):
            confirm = QtWidgets.QMessageBox.question(
                self, "Migrate Custody",
                "Move this workspace's private identity keys into the OS credential "
                "store? The workspace stops carrying them on disk. This does not "
                "protect against malware running as the same OS user.")
            if confirm != QtWidgets.QMessageBox.StandardButton.Yes:
                return
            self._apply(self.model.migrate_custody())

        # -- plumbing ------------------------------------------------------

        def _reload_recipients(self):
            current = self.recipient_box.currentData()
            self.recipient_box.clear()
            self.recipient_box.addItem("choose a recipient", None)
            for record in self.model.recipients():
                self.recipient_box.addItem(f"{record['alias']} ({record['seat']})",
                                           record["alias"])
            if current is not None:
                index = self.recipient_box.findData(current)
                if index >= 0:
                    self.recipient_box.setCurrentIndex(index)

        def _apply(self, result: Optional[dict] = None):
            if result is None:
                self._sync()
                return
            composer = self.model.composer
            if composer is not None and composer.mode == adapter.COMPOSING_NEW:
                composer.alias = self.recipient_box.currentData()
            self._sync()

    return MainWindow


_KINDS = ("DISCOVERY", "EXPERIENCE", "WARNING", "QUESTION", "HYPOTHESIS",
          "MEMORY_FRAGMENT", "PERSONAL_MESSAGE", "PROTOCOL_PROPOSAL")


def main(argv=None) -> int:
    """``saimail-gui`` entrypoint. Exits cleanly when the GUI extra is absent."""
    modules = _require_qt()
    if modules is None:
        return 2
    QtCore, QtGui, QtWidgets = modules
    from saimail import gui_theme

    gui_theme.assert_canonical()
    app = QtWidgets.QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("saimail-gui")
    app.setStyleSheet(gui_theme.style_sheet())
    window = _build_window(QtCore, QtGui, QtWidgets)()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
