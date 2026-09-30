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
import os
import sys
from itertools import pairwise
from pathlib import Path

from saimail import gui_adapter as adapter
from saimail import gui_theme as theme
from saimail.envelope import KINDS as _KINDS

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

    def _scroll_page(page):
        page.layout().setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        scroll.setWidget(page)
        return scroll

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
            if theme.FONT_FAMILY not in QtGui.QFontDatabase.families() and sys.platform == "win32":
                # Windows' offscreen Qt platform has no system font database.
                # Load the existing OS font, never fetch or bundle font files.
                font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "verdana.ttf"
                if font_path.is_file():
                    QtGui.QFontDatabase.addApplicationFont(str(font_path))
            font = QtGui.QFont(theme.FONT_FAMILY)
            font.setPixelSize(theme.SIZE_BODY)
            font.setStyleStrategy(QtGui.QFont.StyleStrategy.NoAntialias)
            self.setFont(font)
            self.model = adapter.GuiAdapter(page_size=page_size)
            self._key_job = None
            self._agent_page = None
            self._shortcut_handles = []
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
            self.tabs = QtWidgets.QTabWidget()
            mail_page = QtWidgets.QWidget()
            mail_layout = QtWidgets.QVBoxLayout(mail_page)
            mail_layout.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
            mail_layout.setContentsMargins(0, 0, 0, 0)
            mail_layout.addWidget(self._mail_region(), 1)
            mail_layout.addWidget(self._composer_region())
            mail_layout.addWidget(self._rare_region())
            self.tabs.addTab(_scroll_page(mail_page), "Mail")
            self.tabs.addTab(_scroll_page(self._agents_region()), "Agents && continuity")
            self.tabs.addTab(_scroll_page(self._keys_region()), "Keys && backup")
            outer.addWidget(self.tabs, 1)
            outer.addWidget(self._status_region())
            self._shortcuts()
            self._tab_order(root)

        def _keys_region(self):
            page = QtWidgets.QWidget()
            form = QtWidgets.QFormLayout(page)
            form.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            intro = _label("Your letters stay sealed. Unlock only to read or send.\n"
                           "Choose a long master password; recovery uses a separate backup and recovery key.")
            intro.setWordWrap(True)
            form.addRow(intro)
            self.key_folder = QtWidgets.QLineEdit()
            form.addRow("Mailbox folder", self.key_folder)
            self.key_seat = QtWidgets.QLineEdit("operator")
            form.addRow("Your local name", self.key_seat)
            self.key_password = QtWidgets.QLineEdit()
            self.key_password.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            form.addRow("Master password", self.key_password)
            self.key_confirm = QtWidgets.QLineEdit()
            self.key_confirm.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            form.addRow("Repeat new password", self.key_confirm)
            row = QtWidgets.QWidget()
            buttons = QtWidgets.QGridLayout(row)
            buttons.setSizeConstraint(QtWidgets.QLayout.SizeConstraint.SetMinimumSize)
            actions = (("Create encrypted mailbox", self.on_create_encrypted),
                       ("Unlock", self.on_unlock), ("Lock", self.on_lock),
                       ("Set / change master password", self.on_protect),
                       ("Create recovery backup", self.on_backup), ("Restore identity", self.on_restore))
            for i, (label, callback) in enumerate(actions):
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(callback)
                buttons.addWidget(button, i // 3, i % 3)
            form.addRow(row)
            self.key_backup_path = QtWidgets.QLineEdit()
            form.addRow("Recovery backup file", self.key_backup_path)
            self.key_recovery = QtWidgets.QLineEdit()
            self.key_recovery.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
            form.addRow("Recovery key (for restore)", self.key_recovery)
            self.key_result = QtWidgets.QPlainTextEdit()
            self.key_result.setReadOnly(True)
            self.key_result.setPlainText("Recovery backups contain identity keys only. Back up the sealed mailbox folder too.\n"
                                         "Keep the backup and recovery key separately.\n"
                                         "Hardware FIDO2/PRF unlock is not configured on this device.")
            form.addRow(self.key_result)
            return page

        def _agents_region(self):
            page = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(page)
            description = _label("Useful letters connect work across agents and generations.\n"
                                 "Discover headers, review evidence, record a decision, then preserve a proven result.")
            description.setWordWrap(True)
            layout.addWidget(description)
            form = QtWidgets.QFormLayout()
            self.agent_project = QtWidgets.QLineEdit()
            form.addRow("SAIPEN project folder", self.agent_project)
            self.agent_work = QtWidgets.QLineEdit()
            form.addRow("Work (empty = current)", self.agent_work)
            self.agent_scope = QtWidgets.QLineEdit()
            form.addRow("File in your current work", self.agent_scope)
            self.agent_result = QtWidgets.QLineEdit()
            form.addRow("Result evidence file", self.agent_result)
            layout.addLayout(form)
            actions = QtWidgets.QGridLayout()
            for i, (label, action) in enumerate((
                    ("Discover", "desk"), ("Review", "review"), ("Accept", "ACCEPTED"),
                    ("Defer", "DEFERRED"), ("Decline", "DECLINED"), ("Resolve with evidence", "RESOLVED"),
                    ("Keep for successors", "retain"), ("Report decision to sender", "report"), ("Outcomes", "metrics"))):
                button = QtWidgets.QPushButton(label)
                button.clicked.connect(lambda checked=False, a=action: self.on_agent_action(a))
                actions.addWidget(button, i // 3, i % 3)
            layout.addLayout(actions)
            self.agent_more = QtWidgets.QPushButton("Next discovery page")
            self.agent_more.setEnabled(False)
            self.agent_more.clicked.connect(lambda: self.on_agent_action("desk-next"))
            layout.addWidget(self.agent_more)
            self.agent_letters = QtWidgets.QListWidget()
            layout.addWidget(self.agent_letters, 1)
            self.agent_body = QtWidgets.QPlainTextEdit()
            self.agent_body.setReadOnly(True)
            layout.addWidget(self.agent_body, 2)
            return page

        def _run_key_job(self, action, *, reveal_backup=False):
            if self._key_job is not None:
                return

            class KeyJob(QtCore.QThread):
                completed = QtCore.Signal(object)

                def run(job):
                    try:
                        result = action()
                    except OSError:
                        result = self.model._fail_code("keys", "KEY_STORAGE_UNAVAILABLE",
                            "Could not access the mailbox folder or backup file. Check its location and permissions.")
                    except Exception:  # noqa: BLE001 - user-facing key boundary, never include exception data or secrets
                        result = self.model._fail_code("keys", "KEY_OPERATION_FAILED",
                            "Could not complete the key operation. Reopen the mailbox and check the selected backup file.")
                    job.completed.emit(result)

            self.status_label.setText("Working with encrypted identity…")
            self.centralWidget().setEnabled(False)
            for shortcut in self._shortcut_handles:
                shortcut.setEnabled(False)
            self._key_job = KeyJob(self)

            def completed(result):
                self.centralWidget().setEnabled(True)
                for shortcut in self._shortcut_handles:
                    shortcut.setEnabled(True)
                if reveal_backup and result.get("ok"):
                    backup = result["backup"]
                    self.key_result.setPlainText(
                        "BACKUP SAVED: " + backup["path"] + "\n\nRECOVERY KEY — KEEP SEPARATELY:\n"
                        + backup["recovery_key"] + "\n\nIdentity keys only; back up sealed mail separately. "
                        "Lock clears this display. The recovery key is not saved by the application.")
                else:
                    self.key_result.setPlainText(result.get("text") or result.get("detail") or result.get("code", "Done"))
                self._apply(result)

            self._key_job.completed.connect(completed)
            self._key_job.finished.connect(self._key_job.deleteLater)
            self._key_job.finished.connect(lambda: setattr(self, "_key_job", None))
            self._key_job.start()

        def _new_password(self):
            password = self.key_password.text()
            if password != self.key_confirm.text():
                self.key_result.setPlainText("Passwords differ. Repeat the same new password.")
                return None
            self.key_password.clear()
            self.key_confirm.clear()
            return password

        def on_create_encrypted(self):
            password = self._new_password()
            folder, seat = self.key_folder.text().strip(), self.key_seat.text().strip()
            if password is None or not folder or not seat:
                return
            self._run_key_job(lambda: self.model.create_workspace(folder, seat, "master-key", password=password))

        def on_unlock(self):
            password = self.key_password.text()
            self.key_password.clear()
            if self.model.workspace is None:
                folder = self.key_folder.text().strip()
                if not folder:
                    self.key_result.setPlainText("Choose the mailbox folder first.")
                    return
                self._run_key_job(lambda: self.model.open_workspace(folder, password=password))
            else:
                self._run_key_job(lambda: self.model.unlock_workspace(password))

        def on_lock(self):
            self.key_result.clear()
            self.key_password.clear()
            self.key_confirm.clear()
            self.key_recovery.clear()
            self.agent_body.clear()
            self.agent_letters.clear()
            self._agent_page = None
            self.agent_more.setEnabled(False)
            self._apply(self.model.lock_workspace())

        def on_protect(self):
            password = self._new_password()
            if password is not None:
                self._run_key_job(lambda: self.model.protect_keys(password))

        def on_backup(self):
            path = self.key_backup_path.text().strip()
            if not path:
                path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save encrypted recovery backup", "saimail-recovery.json")
            if path:
                self.key_backup_path.setText(path)
                self._run_key_job(lambda: self.model.recovery_backup(path), reveal_backup=True)

        def on_restore(self):
            password = self._new_password()
            if password is None:
                return
            backup, folder = self.key_backup_path.text().strip(), self.key_folder.text().strip()
            recovery_key = self.key_recovery.text().strip()
            self.key_recovery.clear()
            if not backup or not folder or not recovery_key:
                self.key_result.setPlainText("Fill the backup file, empty destination folder, recovery key and new password.")
                return
            self._run_key_job(lambda: self.model.restore_backup(backup, folder, recovery_key, password))

        def on_agent_action(self, action):
            selected = self.agent_letters.currentItem()
            envelope_id = selected.data(QtCore.Qt.ItemDataRole.UserRole) if selected else None
            kwargs = {"work": self.agent_work.text().strip() or None,
                      "scope": [self.agent_scope.text().strip()] if self.agent_scope.text().strip() else []}
            context = (str(self.model.workspace.root) if self.model.workspace else None,
                       self.agent_project.text().strip(), kwargs["work"], tuple(kwargs["scope"]))
            continued = action == "desk-next"
            if continued:
                if self._agent_page is None or context != self._agent_page["context"]:
                    self.agent_body.setPlainText("Discovery context changed. Press Discover to start again.")
                    self.agent_more.setEnabled(False)
                    return
                kwargs.update(continuation=self._agent_page["continuation"])
                action = "desk"
            if action in {"ACCEPTED", "DEFERRED", "DECLINED", "RESOLVED"}:
                reasons = {"ACCEPTED": "ACTION_PLANNED", "DEFERRED": "WAITING_DEPENDENCY",
                           "DECLINED": "NOT_ACTIONABLE", "RESOLVED": "ACTION_TAKEN"}
                kwargs.update(decision=action, reason=reasons[action], result_path=self.agent_result.text().strip() or None)
                action = "decide"
            if action not in {"desk", "metrics"} and not envelope_id:
                self.agent_body.setPlainText("Select a discovered letter first.")
                return
            result = self.model.correspondence_action(self.agent_project.text().strip(), action,
                                                      envelope_id=envelope_id, **kwargs)
            if action == "desk" and result.get("ok"):
                if not continued:
                    self.agent_letters.clear()
                self._agent_page = {"context": context, "continuation": result.get("continuation")}
                self.agent_more.setEnabled(not result.get("complete", False))
                seen = {self.agent_letters.item(i).data(QtCore.Qt.ItemDataRole.UserRole)
                        for i in range(self.agent_letters.count())}
                for item in (result.get("items") or []) + (result.get("cases") or []):
                    if item["envelope_id"] in seen:
                        continue
                    seen.add(item["envelope_id"])
                    row = QtWidgets.QListWidgetItem(
                        f"{item.get('match', 'NEW')}  {item.get('from', item.get('sender'))}  "
                        f"{item.get('decision', item.get('state'))}")
                    row.setData(QtCore.Qt.ItemDataRole.UserRole, item["envelope_id"])
                    self.agent_letters.addItem(row)
            from saimail.workspace import render_command

            self.agent_body.setPlainText(render_command(result))
            self._apply(result)

        def closeEvent(self, event):
            if self._key_job is not None and self._key_job.isRunning():
                self.status_label.setText("Finish the requested key operation before closing.")
                event.ignore()
                return
            self.model.close_workspace()
            self.agent_body.clear()
            self.key_result.clear()
            event.accept()

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

            filter_row = QtWidgets.QGridLayout()
            filter_row.setSpacing(4)
            self.filter_sender = QtWidgets.QLineEdit()
            self.filter_sender.setPlaceholderText("sender seat")
            self.filter_topic = QtWidgets.QLineEdit()
            self.filter_topic.setPlaceholderText("topic")
            self.filter_kind = QtWidgets.QComboBox()
            self.filter_kind.addItem("any kind", None)
            for kind in sorted(_KINDS):
                self.filter_kind.addItem(kind, kind)
            self.filter_state = QtWidgets.QComboBox()
            self.filter_state.addItem("any state", None)
            for state in ("UNREAD", "READ", "EXPIRED"):
                self.filter_state.addItem(state, state)
            for i, (label, control) in enumerate((("Sender", self.filter_sender), ("Topic", self.filter_topic),
                                                  ("Kind", self.filter_kind), ("State", self.filter_state))):
                filter_row.addWidget(_label(label, "MetadataLabel"), i // 2, (i % 2) * 2)
                filter_row.addWidget(control, i // 2, (i % 2) * 2 + 1)
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
            self.reopen_button = QtWidgets.QPushButton("Reopen")
            self.reopen_button.clicked.connect(self.on_reopen)
            self.reply_button = QtWidgets.QPushButton("Reply")
            self.reply_button.clicked.connect(self.on_reply)
            actions.addWidget(self.open_button)
            actions.addWidget(self.reopen_button)
            actions.addWidget(self.reply_button)
            column.addLayout(actions)

            self.open_reason_label = _label("", "DisabledReason")
            self.reopen_reason_label = _label("", "DisabledReason")
            self.reply_reason_label = _label("", "DisabledReason")
            column.addWidget(self.open_reason_label)
            column.addWidget(self.reopen_reason_label)
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
            head.addWidget(self.composer_mode)
            head.addStretch(1)
            head.addWidget(self.new_button)
            column.addLayout(head)

            self.composer_inputs = QtWidgets.QWidget()
            column.addWidget(self.composer_inputs)
            column = QtWidgets.QVBoxLayout(self.composer_inputs)
            column.setContentsMargins(0, 0, 0, 0)
            column.setSpacing(4)

            fields = QtWidgets.QGridLayout()
            fields.setSpacing(4)
            self.recipient_box = QtWidgets.QComboBox()
            self.recipient_box.setObjectName("recipient")
            self.recipient_box.currentIndexChanged.connect(self.on_recipient_changed)
            fields.addWidget(_label("Recipient", "MetadataLabel"), 0, 0)
            fields.addWidget(self.recipient_box, 0, 1)
            self.subject_edit = QtWidgets.QLineEdit("local-message")
            fields.addWidget(_label("Subject", "MetadataLabel"), 0, 2)
            fields.addWidget(self.subject_edit, 0, 3)
            fields.addWidget(_label("Topic", "MetadataLabel"), 1, 0)
            self.topic_edit = QtWidgets.QLineEdit("")
            self.topic_edit.setPlaceholderText("local-message")
            fields.addWidget(self.topic_edit, 1, 1, 1, 3)
            column.addLayout(fields)

            self.draft = QtWidgets.QPlainTextEdit()
            self.draft.setObjectName("draft")
            self.draft.setPlaceholderText("one line of operator text")
            self.draft.textChanged.connect(self.on_draft_changed)
            column.addWidget(self.draft, 1)

            send_row = QtWidgets.QHBoxLayout()
            send_row.setSpacing(4)
            self.send_button = QtWidgets.QPushButton("Send")
            self.send_button.setObjectName("Primary")
            self.send_button.clicked.connect(self.on_send)
            self.cancel_button = QtWidgets.QPushButton("Cancel Composer")
            self.cancel_button.clicked.connect(self.on_close_composer)
            self.send_reason_label = _label("", "DisabledReason")
            send_row.addWidget(self.send_button)
            send_row.addWidget(self.cancel_button)
            send_row.addWidget(self.send_reason_label, 1)
            column.addLayout(send_row)
            return box

        def _rare_region(self):
            box = _panel("Workspace, Recipients, Identity, Custody")
            row = QtWidgets.QGridLayout(box)
            row.setContentsMargins(4, 4, 4, 4)
            row.setSpacing(4)
            self.open_workspace_button = QtWidgets.QPushButton("Open Workspace")
            self.open_workspace_button.clicked.connect(self.on_open_workspace)
            self.create_workspace_button = QtWidgets.QPushButton("Create Workspace")
            self.create_workspace_button.clicked.connect(self.on_create_workspace)
            self.recipients_button = QtWidgets.QPushButton("Recipients")
            self.recipients_button.clicked.connect(self.on_recipients)
            self.add_recipient_button = QtWidgets.QPushButton("Add Recipient")
            self.add_recipient_button.clicked.connect(self.on_add_recipient)
            self.identity_button = QtWidgets.QPushButton("Export Identity Card")
            self.identity_button.clicked.connect(self.on_export_identity)
            self.custody_button = QtWidgets.QPushButton("Custody Status")
            self.custody_button.clicked.connect(self.on_custody_status)
            self.migrate_button = QtWidgets.QPushButton("Migrate Custody")
            self.migrate_button.clicked.connect(self.on_migrate_custody)
            for i, widget in enumerate((self.open_workspace_button, self.create_workspace_button,
                           self.recipients_button, self.add_recipient_button,
                           self.identity_button, self.custody_button,
                           self.migrate_button)):
                row.addWidget(widget, i // 4, i % 4)
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
                ("Esc", self.on_escape),
            )
            for sequence, handler in bindings:
                shortcut = QtGui.QShortcut(QtGui.QKeySequence(sequence), self)
                shortcut.activated.connect(handler)
                self._shortcut_handles.append(shortcut)

        def _tab_order(self, root):
            """One explicit focus chain: daily actions before rare ones."""
            chain = [
                self.refresh_button, self.filter_sender, self.filter_topic,
                self.filter_kind, self.filter_state, self.apply_filters_button,
                self.reset_filters_button, self.inbox, self.load_more_button,
                self.open_button, self.reply_button, self.content,
                self.recipient_box, self.subject_edit, self.topic_edit, self.draft,
                self.send_button, self.cancel_button, self.new_button,
                self.open_workspace_button, self.create_workspace_button,
                self.recipients_button, self.add_recipient_button,
                self.identity_button, self.custody_button, self.migrate_button,
            ]
            for previous, following in pairwise(chain):
                QtWidgets.QWidget.setTabOrder(previous, following)

        # -- rendering -----------------------------------------------------

        def _sync(self):
            """Draw presentation state from the adapter. No hidden mutation."""
            model = self.model
            loaded = model.workspace is not None
            self.seat_label.setText(
                f"seat {model.workspace.seat}" if loaded else "no workspace")
            self.custody_label.setText(
                f"{model.workspace.custody} · {'locked' if model.locked else 'unlocked'}" if loaded else "custody —")
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
            self.reopen_reason_label.setText(self.model.reopen_reason() or "")
            self.reply_reason_label.setText(self.model.reply_reason() or "")
            self.open_button.setEnabled(self.model.open_reason() is None)
            self.reopen_button.setEnabled(self.model.reopen_reason() is None)
            self.reply_button.setEnabled(self.model.reply_reason() is None)
            content = self.model.content()
            if content is None:
                note = self.model.content_note()
                self.content.setPlainText(note or "No content loaded.")
                self.content_label.setText("")
            else:
                text = (
                    f"SUBJECT  {content.get('subject') or '—'}\n"
                    f"CLAIM    {content.get('claim') or '—'}\n"
                    f"FROM     {content.get('from')}\n"
                    f"KIND     {content.get('kind')}   TOPIC {content.get('topic')}\n"
                    f"RECEIVED {content.get('received_at')}\n"
                    f"STATUS   {content.get('status')}   "
                    f"EVIDENCE {content.get('evidence_state')}\n"
                    f"CONTENT_ID {content.get('content_id')}")
                from sailang import SailangError
                from saimail import letters

                try:
                    letter = letters.parse(content.get("claim") or "")
                    text = "\n\n".join((
                        "OBSERVATION\n" + letter["observation"], "WHY IT MATTERS\n" + letter["impact"],
                        "REQUEST\n" + letter["request"], "COMPLETE WHEN\n" + letter["done_when"],
                        "UNCERTAINTY\n" + (letter["uncertainty"] or "See the evidence pointers."),
                        "EVIDENCE\n" + "\n".join(ref["path"] + " · " + ref["sha256"] for ref in letter["evidence"])))
                except SailangError:
                    pass
                self.content.setPlainText(text)
                self.content_label.setText(f"content_id {content.get('content_id')}")

        def _draw_composer(self):
            composer = self.model.composer
            self.composer_inputs.setVisible(composer is not None)
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

        def on_reopen(self):
            self._apply(self.model.reopen_selected())

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
            # The composer's own fields are the only presentation inputs; the
            # kind stays the documented daily default (PERSONAL_MESSAGE) because
            # V5-01 exposes no kind control on the daily surface.
            result = self.model.send(
                subject=self.subject_edit.text().strip() or None,
                topic=self.topic_edit.text().strip() or None)
            self._apply(result)
            if result["ok"]:
                self._reload_recipients()

        def on_open_workspace(self):
            path = QtWidgets.QFileDialog.getExistingDirectory(self, "Open Workspace")
            if not path:
                return
            self._apply(self.model.open_workspace(path))

        def on_create_workspace(self):
            self.tabs.setCurrentIndex(2)
            self.key_folder.setFocus()

        def on_recipients(self):
            """List registered recipients (metadata only). Never discovers peers."""
            self._reload_recipients()
            rows = self.model.recipients()
            if not rows:
                note = (adapter.REASON_NO_WORKSPACE if self.model.workspace is None
                        else "no recipients are registered")
                self._apply(self.model.list_recipients_note(note))
                return
            self._apply(self.model.list_recipients_note(
                f"{len(rows)} recipient(s), metadata only"))

        def on_add_recipient(self):
            """Register one recipient from an identity card plus a peer root."""
            if self.model.workspace is None:
                self._apply(self.model.list_recipients_note(adapter.REASON_NO_WORKSPACE))
                return
            self._add_recipient_dialog()

        def on_draft_changed(self):
            """Keep the draft in the adapter so Send's enabled state is truthful.

            This is pure presentation bookkeeping: the text stays ephemeral, and
            only an explicit Send forwards it to the backend.
            """
            if self.model.composer is not None:
                self.model.set_draft(self.draft.toPlainText())
                reason = self.model.send_reason()
                self.send_reason_label.setText(reason or "")
                self.send_button.setEnabled(reason is None)

        def on_recipient_changed(self, _index=None):
            if (self.model.composer is not None
                    and self.model.composer.mode == adapter.COMPOSING_NEW):
                self.model.composer.alias = self.recipient_box.currentData()
                reason = self.model.send_reason()
                self.send_reason_label.setText(reason or "")
                self.send_button.setEnabled(reason is None)

        def on_escape(self):
            """Esc closes the composer; otherwise it clears the error banner."""
            if self.model.composer is not None:
                self._apply(self.model.close_composer())
            else:
                self.model.clear_error()
                self._sync()

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

        def _apply(self, result: dict | None = None):
            if result is None:
                self._sync()
                return
            composer = self.model.composer
            if composer is not None and composer.mode == adapter.COMPOSING_NEW:
                composer.alias = self.recipient_box.currentData()
            self._sync()

    return MainWindow


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
