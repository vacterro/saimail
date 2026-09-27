"""SAIMAIL GUI presentation adapter (V5-01, spec/25).

The GUI is a presentation layer, never a second protocol implementation. This
module is the whole of its domain-facing surface: one small object that holds
ephemeral presentation state and forwards every real action to the existing
tested public API in :mod:`saimail.workspace` (and, for filters, the same
bounded metadata query the CLI already uses).

Three boundaries are deliberate and load-bearing:

* **Selecting is not opening.** :meth:`GuiAdapter.select` reads one row's
  metadata from the page already in memory. It never touches the mailbox.
  Explicit :meth:`GuiAdapter.open_selected` and :meth:`GuiAdapter.reopen_selected`
  call ``workspace.open_message`` and ``workspace.reopen_message`` respectively;
  content becomes visible only after the requested action succeeds.
* **Refresh is explicit.** There is no watcher, timer, thread, poll or
  background mutation anywhere in this module. :meth:`GuiAdapter.refresh`
  replaces the visible page because the operator asked; nothing else ever
  changes the row list.
* **No invented semantics.** No persistence rule, delivery rule, recipient
  discovery, deduplication, lifecycle transition, thread model, custody policy
  or protocol relation lives here. Backend refusal codes pass through
  unchanged; the adapter never relabels a protocol verdict.

Open and Reopen are distinct receiver actions (T-113). Open performs the first
UNREAD-to-READ transition and refuses READ messages. Reopen explicitly
re-authenticates and decrypts a durable READ message, including in a later
session. The backend budgets and verifies each Reopen without changing durable
READ state or persisting plaintext. Content is held only in this session's
ephemeral presentation state (:attr:`GuiAdapter.content_visible`); workspace
entry, selection and refresh never decrypt it automatically.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from sailang import SailangError
from saimail import workspace as _workspace

#: The closed application state set (V5-01 Milestone 6).
NO_WORKSPACE = "NO_WORKSPACE"
WORKSPACE_LOADED = "WORKSPACE_LOADED"
MESSAGE_SELECTED_UNREAD = "MESSAGE_SELECTED_UNREAD"
MESSAGE_SELECTED_READ = "MESSAGE_SELECTED_READ"
MESSAGE_OPENED_CURRENT_SESSION = "MESSAGE_OPENED_CURRENT_SESSION"
COMPOSING_NEW = "COMPOSING_NEW"
COMPOSING_REPLY = "COMPOSING_REPLY"
BUSY = "BUSY"
ERROR = "ERROR"

APP_STATES = (
    NO_WORKSPACE, WORKSPACE_LOADED, MESSAGE_SELECTED_UNREAD,
    MESSAGE_SELECTED_READ, MESSAGE_OPENED_CURRENT_SESSION,
    COMPOSING_NEW, COMPOSING_REPLY, BUSY, ERROR,
)

#: Status levels for the persistent status strip. `warning` means the operator
#: has to decide something; `error` means an action was refused or failed.
OK = "ok"
WARNING = "warning"
ERROR_LEVEL = "error"

#: Page bound for one visible refresh. Small on purpose: it is the same bounded
#: metadata query the CLI uses, never a whole-mailbox load.
DEFAULT_PAGE_SIZE = 50

#: Why a control is unavailable. These strings are shown to the operator, so
#: they are plain sentences and never a bare code.
REASON_NO_WORKSPACE = "Open a workspace first."
REASON_NO_RECIPIENTS = "Register a recipient to compose a message."
REASON_EMPTY_INBOX = "The inbox is empty."
REASON_OPEN_ALREADY_READ = (
    "Already READ. Open is for the first read only. Use Reopen to read again.")
REASON_REPLY_UNREAD = "Open the message first to reply."
REASON_REPLY_NONE = "Select a READ message to reply."
REASON_READ_NOT_THIS_SESSION = (
    "READ — content is not loaded in this session. Use Reopen to read again.")
REASON_REOPEN_NOT_READ = "Message is UNREAD; open it explicitly first."
REASON_REOPEN_NONE = "Select a READ message to reopen."
REASON_COMPOSER_EMPTY = "Type a message to send."
REASON_NO_FILTERS = "No active filters."

@dataclass
class Status:
    """One persistent piece of visible evidence. Never auto-hides."""

    level: str = OK
    code: str = "READY"
    text: str = "ready"
    detail: str = ""

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "text": self.text,
                "detail": self.detail}


@dataclass
class Composer:
    """One composer mode. NEW selects a recipient; REPLY cannot."""

    mode: str
    alias: Optional[str] = None
    reply_target: Optional[str] = None
    subject: str = _workspace.DEFAULT_SUBJECT
    topic: Optional[str] = None
    kind: str = _workspace.DEFAULT_REPLY_KIND
    draft: str = ""

    @property
    def recipient_locked(self) -> bool:
        """Reply recipients are fixed by the backend, never by the operator."""
        return self.mode == COMPOSING_REPLY


@dataclass
class Page:
    """One bounded page of metadata rows plus its continuation state."""

    items: List[dict] = field(default_factory=list)
    rows_examined: int = 0
    exhausted: bool = False
    cursor: Optional[int] = None

    @property
    def has_more(self) -> bool:
        return self.exhausted and self.cursor is not None


class GuiAdapter:
    """Ephemeral presentation state over the unchanged local backend.

    Nothing here is durable: the workspace on disk is the only authority, and
    every accessor re-reads what it needs through the public API.
    """

    def __init__(self, page_size: int = DEFAULT_PAGE_SIZE):
        self.page_size = int(page_size)
        self.workspace: Optional[_workspace.Workspace] = None
        self.page = Page()
        self.filters: Dict[str, Optional[str]] = {}
        self.selected_id: Optional[str] = None
        self._opened: Dict[str, dict] = {}
        self.composer: Optional[Composer] = None
        self.status = Status()
        self.error_active = False
        self.busy = False

    # -- lifecycle ---------------------------------------------------------

    def open_workspace(self, root) -> dict:
        """Open an existing workspace. Read-only; nothing is created."""
        self.busy = True
        try:
            loaded = _workspace.load_workspace(Path(root))
        except SailangError as exc:
            return self._fail("workspace-open", exc)
        finally:
            self.busy = False
        self.workspace = loaded
        self._reset_view()
        return self._ok("workspace-open", "WORKSPACE_LOADED",
                        f"workspace opened for seat {loaded.seat}")

    def create_workspace(self, root, seat: str, custody: str = "raw") -> dict:
        """Create a workspace through the existing init path (raw by default)."""
        self.busy = True
        try:
            result = _workspace.init_workspace(Path(root), seat=seat, custody=custody)
        except SailangError as exc:
            return self._fail("workspace-create", exc)
        finally:
            self.busy = False
        if result.get("status") == _workspace.CREATED:
            self.workspace = _workspace.load_workspace(Path(root))
            self._reset_view()
        elif result.get("status") == _workspace.ALREADY_EXISTS:
            self.workspace = _workspace.load_workspace(Path(root))
            self._reset_view()
        notices = result.get("notices") or []
        return self._ok("workspace-create", result.get("status", "OK"),
                        result.get("detail") or "workspace created",
                        notices=notices, raw=result)

    def close_workspace(self) -> None:
        """Drop every ephemeral view. Durable state is untouched."""
        self.workspace = None
        self._reset_view()

    def _reset_view(self) -> None:
        self.page = Page()
        self.filters = {}
        self.selected_id = None
        self._opened = {}
        self.composer = None
        self.error_active = False

    # -- state -------------------------------------------------------------

    @property
    def state(self) -> str:
        """One composed application state, highest-precedence first.

        ERROR ranks below NO_WORKSPACE (with no workspace loaded, that is the
        truthful mode) and above the selection states, because a refused action
        is the newest fact on screen. Selection and content stay readable
        through their own accessors and their own regions regardless, so no
        information is hidden by this precedence.
        """
        if self.busy:
            return BUSY
        if self.composer is not None:
            return self.composer.mode
        if self.workspace is None:
            return NO_WORKSPACE
        if self.error_active:
            return ERROR
        if self.selected_id is not None and self.content_visible:
            return MESSAGE_OPENED_CURRENT_SESSION
        if self.selected_id is not None:
            # The presentation state is the closed ``MESSAGE_SELECTED_*``
            # vocabulary; the durable mailbox state stays its own string and is
            # still readable through ``selected_state`` / ``selected_row``.
            return (MESSAGE_SELECTED_READ if self.selected_state == "READ"
                    else MESSAGE_SELECTED_UNREAD)
        return WORKSPACE_LOADED

    @property
    def selected_row(self) -> Optional[dict]:
        for item in self.page.items:
            if item["envelope_id"] == self.selected_id:
                return item
        return None

    @property
    def selected_state(self) -> Optional[str]:
        row = self.selected_row
        return None if row is None else row["state"]

    @property
    def content_visible(self) -> bool:
        """True only after this session's explicit Open or Reopen succeeded."""
        return self.selected_id in self._opened

    def content(self) -> Optional[dict]:
        """Canonical record fields returned by explicit Open or Reopen, if any."""
        return self._opened.get(self.selected_id) if self.selected_id else None

    # -- mailbox view ------------------------------------------------------

    def refresh(self) -> dict:
        """Explicit refresh: bounded metadata query, page 1, cursor reset."""
        if self.workspace is None:
            return self._refuse_no_workspace("refresh")
        self.busy = True
        try:
            result = _workspace.query_inbox(
                self.workspace, sender=self.filters.get("sender"),
                topic=self.filters.get("topic"), kind=self.filters.get("kind"),
                state=self.filters.get("state"), scan_budget=self.page_size)
        except SailangError as exc:
            return self._fail("refresh", exc)
        finally:
            self.busy = False
        self.page = Page(items=list(result.get("items") or []),
                         rows_examined=result.get("rows_examined", 0),
                         exhausted=bool(result.get("exhausted")),
                         cursor=result.get("cursor"))
        if self.selected_row is None:
            self.selected_id = None
        return self._ok("refresh", "OK",
                        f"inbox refreshed ({self.page.rows_examined} row(s) examined, "
                        f"{len(self.page.items)} shown)")

    def load_more(self) -> dict:
        """Explicit continuation. Visible rows are appended, never reordered."""
        if self.workspace is None:
            return self._refuse_no_workspace("load-more")
        if not self.page.has_more:
            return self._ok("load-more", "NO_CONTINUATION", "no further index data")
        self.busy = True
        try:
            result = _workspace.query_inbox(
                self.workspace, sender=self.filters.get("sender"),
                topic=self.filters.get("topic"), kind=self.filters.get("kind"),
                state=self.filters.get("state"), scan_budget=self.page_size,
                cursor=self.page.cursor)
        except SailangError as exc:
            return self._fail("load-more", exc)
        finally:
            self.busy = False
        self.page.items.extend(result.get("items") or [])
        self.page.rows_examined += result.get("rows_examined", 0)
        self.page.exhausted = bool(result.get("exhausted"))
        self.page.cursor = result.get("cursor")
        return self._ok("load-more", "OK",
                        f"{len(result.get('items') or [])} more row(s) loaded",
                        has_more=self.page.has_more)

    def set_filters(self, *, sender=None, topic=None, kind=None, state=None) -> dict:
        """Record filters. Nothing is queried until the operator refreshes."""
        self.filters = {"sender": sender, "topic": topic, "kind": kind, "state": state}
        active = self.active_filters()
        if not active:
            return self._ok("filters", "CLEARED", REASON_NO_FILTERS)
        return self._ok("filters", "SET", "filters active: " + ", ".join(active))

    def reset_filters(self) -> dict:
        """Clear every filter. The visible page is not silently re-queried."""
        self.filters = {}
        return self._ok("filters", "CLEARED", "filters cleared")

    def active_filters(self) -> List[str]:
        return [f"{key}={value}" for key, value in sorted(self.filters.items())
                if value is not None]

    # -- selection and explicit open ---------------------------------------

    def select(self, envelope_id) -> dict:
        """Select one row: metadata only, no mailbox read, no decryption."""
        row = None
        for item in self.page.items:
            if item["envelope_id"] == envelope_id:
                row = item
                break
        if row is None:
            return self._fail_code("select", _workspace.BAD_INPUT,
                                  "that envelope id is not on the visible page")
        self.selected_id = envelope_id
        self.error_active = False
        return self._ok("select", row["state"],
                        f"{row['state']} selected: {row['from']} / {row['topic']}")

    def open_selected(self) -> dict:
        """Explicit first Open of UNREAD. Backend success gates the transition."""
        if self.workspace is None:
            return self._refuse_no_workspace("open")
        row = self.selected_row
        if row is None:
            return self._fail_code("open", _workspace.BAD_INPUT, "no message is selected")
        if row["state"] != "UNREAD":
            return self._fail_code("open", "OPEN_NOT_UNREAD",
                                   REASON_OPEN_ALREADY_READ
                                   if row["state"] == "READ" else
                                   f"state {row['state']} cannot be opened")
        self.busy = True
        try:
            result = _workspace.open_message(self.workspace, row["envelope_id"])
        except SailangError as exc:
            return self._fail("open", exc)
        finally:
            self.busy = False
        record = dict(result.get("record") or {})
        record["envelope_id"] = row["envelope_id"]
        record["from"] = row["from"]
        record["kind"] = row.get("kind")
        record["topic"] = row.get("topic")
        record["received_at"] = row.get("received_at")
        self._opened[row["envelope_id"]] = record
        for item in self.page.items:
            if item["envelope_id"] == row["envelope_id"]:
                item["state"] = "READ"
                break
        self.error_active = False
        return self._ok("open", "READ", f"opened {row['envelope_id']} explicitly",
                        record=record)

    def open_reason(self) -> Optional[str]:
        """Visible reason when Open is unavailable; None when it is available."""
        row = self.selected_row
        if row is None:
            return "Select a message to open."
        if row["state"] == "UNREAD":
            return None
        if row["state"] == "READ":
            return REASON_OPEN_ALREADY_READ
        return f"State {row['state']} cannot be opened."

    def reopen_selected(self) -> dict:
        """The explicit re-read action for an already-READ message."""
        if self.workspace is None:
            return self._refuse_no_workspace("reopen")
        row = self.selected_row
        if row is None:
            return self._fail_code("reopen", _workspace.BAD_INPUT, "no message is selected")
        if row["state"] != "READ":
            return self._fail_code("reopen", "REOPEN_NOT_READ",
                                   REASON_REOPEN_NOT_READ if row["state"] == "UNREAD" else
                                   f"state {row['state']} cannot be reopened")
        self.busy = True
        try:
            result = _workspace.reopen_message(self.workspace, row["envelope_id"])
        except SailangError as exc:
            return self._fail("reopen", exc)
        finally:
            self.busy = False
        record = dict(result.get("record") or {})
        record["envelope_id"] = row["envelope_id"]
        record["from"] = row["from"]
        record["kind"] = row.get("kind")
        record["topic"] = row.get("topic")
        record["received_at"] = row.get("received_at")
        self._opened[row["envelope_id"]] = record
        self.error_active = False
        return self._ok("reopen", "READ", f"reopened {row['envelope_id']} explicitly",
                        record=record)

    def reopen_reason(self) -> Optional[str]:
        """Visible reason when Reopen is unavailable; None when it is available."""
        if self.workspace is None:
            return REASON_NO_WORKSPACE
        row = self.selected_row
        if row is None:
            return REASON_REOPEN_NONE
        if row["state"] == "UNREAD":
            return REASON_REOPEN_NOT_READ
        if row["state"] != "READ":
            return f"State {row['state']} cannot be reopened."
        return None

    def content_note(self) -> Optional[str]:
        """Why no content is shown for the current selection, if none is."""
        row = self.selected_row
        if row is None or self.content_visible:
            return None
        if row["state"] == "UNREAD":
            return f"{row['state']} — content not loaded. Open to read."
        return REASON_READ_NOT_THIS_SESSION

    # -- composer ----------------------------------------------------------

    def start_new_message(self, alias=None) -> dict:
        if self.workspace is None:
            return self._refuse_no_workspace("compose-new")
        recipients = self.recipients()
        if not recipients:
            return self._fail_code("compose-new", "NO_RECIPIENTS", REASON_NO_RECIPIENTS)
        self.composer = Composer(mode=COMPOSING_NEW, alias=alias)
        self.error_active = False
        return self._ok("compose-new", COMPOSING_NEW, "composing a new message")

    def start_reply(self) -> dict:
        """Reply mode only for a selected READ message; recipient is backend-fixed."""
        if self.workspace is None:
            return self._refuse_no_workspace("compose-reply")
        row = self.selected_row
        if row is None or row["state"] != "READ":
            return self._fail_code("compose-reply", _workspace.REPLY_TARGET_UNREAD,
                                   REASON_REPLY_UNREAD)
        self.composer = Composer(mode=COMPOSING_REPLY,
                                 reply_target=row["envelope_id"],
                                 topic=row.get("topic"))
        self.error_active = False
        return self._ok("compose-reply", COMPOSING_REPLY,
                        f"replying to {row['envelope_id']}")

    def close_composer(self) -> dict:
        if self.composer is None:
            return self._ok("compose-close", "NO_COMPOSER", "no composer is open")
        self.composer = None
        return self._ok("compose-close", "CLOSED", "composer closed; draft discarded")

    def set_draft(self, text: str) -> None:
        if self.composer is not None:
            self.composer.draft = text

    def reply_reason(self) -> Optional[str]:
        """Visible reason when Reply is unavailable; None when it is available."""
        if self.workspace is None:
            return REASON_NO_WORKSPACE
        row = self.selected_row
        if row is None:
            return REASON_REPLY_NONE
        if row["state"] == "UNREAD":
            return REASON_REPLY_UNREAD
        if row["state"] != "READ":
            return f"State {row['state']} cannot be replied to."
        return None

    def send_reason(self) -> Optional[str]:
        """Visible reason when Send is unavailable; None when it is available."""
        if self.workspace is None:
            return REASON_NO_WORKSPACE
        if self.composer is None:
            return "Open the composer to send."
        if not self.composer.draft.strip():
            return REASON_COMPOSER_EMPTY
        if self.composer.mode == COMPOSING_NEW and not self.composer.alias:
            return "Choose a registered recipient."
        return None

    def send(self, *, subject=None, topic=None, kind=None) -> dict:
        """Send the current composer through the existing send/reply path.

        In REPLY mode the recipient is whatever the backend resolves from the
        target envelope: this call takes no alias and cannot change it.
        """
        if self.workspace is None:
            return self._refuse_no_workspace("send")
        composer = self.composer
        if composer is None:
            return self._fail_code("send", _workspace.BAD_INPUT, "no composer is open")
        if not composer.draft.strip():
            return self._fail_code("send", _workspace.BAD_INPUT, REASON_COMPOSER_EMPTY)
        command = "send" if composer.mode == COMPOSING_NEW else "reply"
        self.busy = True
        try:
            if composer.mode == COMPOSING_NEW:
                result = _workspace.send_message(
                    self.workspace, composer.alias, claim=composer.draft.strip(),
                    subject=subject or composer.subject,
                    topic=topic or composer.topic or _workspace.DEFAULT_TOPIC,
                    kind=kind or composer.kind)
            else:
                result = _workspace.reply_message(
                    self.workspace, composer.reply_target, claim=composer.draft.strip(),
                    subject=subject or composer.subject, topic=topic,
                    kind=kind or composer.kind)
        except SailangError as exc:
            return self._fail(command, exc)
        finally:
            self.busy = False
        accepted = result.get("status") in ("ACCEPTED", "DUPLICATE")
        if accepted:
            self.composer = None
        return self._ok(command, result.get("status", "OK"),
                        result.get("detail") or "sent",
                        delivered=result, clear_draft=accepted)

    # -- recipients, identity, custody ------------------------------------

    def recipients(self) -> List[dict]:
        if self.workspace is None:
            return []
        return list(_workspace.list_recipients(self.workspace).get("recipients") or [])

    def list_recipients_note(self, text: str) -> dict:
        """Record a recipient-list observation as visible evidence.

        Read-only: it never queries the backend itself, so it can never be the
        thing that discovers a peer or invents a recipient.
        """
        return self._ok("recipient-list", "OK", text)

    def add_recipient(self, alias: str, card: dict, peer_workspace) -> dict:
        if self.workspace is None:
            return self._refuse_no_workspace("recipient-add")
        self.busy = True
        try:
            result = _workspace.add_recipient(self.workspace, alias, card,
                                              Path(peer_workspace))
        except SailangError as exc:
            return self._fail("recipient-add", exc)
        finally:
            self.busy = False
        return self._ok("recipient-add", result.get("status", "OK"),
                        result.get("detail") or "recipient registered",
                        recipient=result.get("recipient"))

    def export_identity_card(self, dest) -> dict:
        if self.workspace is None:
            return self._refuse_no_workspace("identity-export")
        self.busy = True
        try:
            result = _workspace.export_identity_card(self.workspace, Path(dest))
        except SailangError as exc:
            return self._fail("identity-export", exc)
        finally:
            self.busy = False
        card = result.get("card") or {}
        return self._ok("identity-export", result.get("status", "OK"),
                        f"public identity card exported to {result.get('card_path')}",
                        card_public={"seat": card.get("seat"),
                                     "sender_kid": card.get("sender_kid"),
                                     "recipient_kid": card.get("recipient_kid"),
                                     "card_path": result.get("card_path")})

    def custody_status(self) -> dict:
        if self.workspace is None:
            return self._refuse_no_workspace("custody-status")
        try:
            result = _workspace.custody_status(self.workspace.root)
        except SailangError as exc:
            return self._fail("custody-status", exc)
        custody = result.get("custody") or {}
        mode = custody.get("mode")
        level = WARNING if mode == "raw" else OK
        self.status = Status(level=level, code="CUSTODY_STATUS",
                             text=f"custody: {mode} (backend {custody.get('backend_state')})",
                             detail=result.get("detail") or "")
        return {"ok": True, "code": "CUSTODY_STATUS", "mode": mode,
                "backend_state": custody.get("backend_state"),
                "loadable": custody.get("loadable"),
                "detail": result.get("detail"), "level": level}

    def migrate_custody(self) -> dict:
        if self.workspace is None:
            return self._refuse_no_workspace("custody-migrate")
        self.busy = True
        try:
            result = _workspace.migrate_workspace_custody(self.workspace.root)
        except SailangError as exc:
            return self._fail("custody-migrate", exc)
        finally:
            self.busy = False
        self.workspace = _workspace.load_workspace(self.workspace.root)
        return self._ok("custody-migrate", result.get("status", "OK"),
                        result.get("detail") or "custody migrated")

    # -- status plumbing ---------------------------------------------------

    def _ok(self, command: str, code: str, text: str, **extra) -> dict:
        self.status = Status(level=OK, code=code, text=text)
        self.error_active = False
        out = {"ok": True, "command": command, "code": code, "text": text}
        out.update(extra)
        return out

    def _fail(self, command: str, exc: SailangError) -> dict:
        level = WARNING if exc.code in _workspace.OPERATOR_ACTION_CODES else ERROR_LEVEL
        self.status = Status(level=level, code=exc.code, text=f"{command} refused: {exc.code}",
                             detail=getattr(exc, "detail", str(exc)))
        self.error_active = True
        return {"ok": False, "command": command, "code": exc.code,
                "text": self.status.text, "detail": self.status.detail,
                "level": level, "operator_action_required":
                    exc.code in _workspace.OPERATOR_ACTION_CODES}

    def _fail_code(self, command: str, code: str, detail: str) -> dict:
        self.status = Status(level=WARNING, code=code, text=f"{command}: {code}",
                             detail=detail)
        self.error_active = True
        return {"ok": False, "command": command, "code": code,
                "text": self.status.text, "detail": detail, "level": WARNING,
                "operator_action_required": True}

    def _refuse_no_workspace(self, command: str) -> dict:
        return self._fail_code(command, _workspace.WORKSPACE_MISSING, REASON_NO_WORKSPACE)

    def clear_error(self) -> None:
        self.error_active = False


__all__ = [
    "APP_STATES",
    "BUSY",
    "COMPOSING_NEW",
    "COMPOSING_REPLY",
    "Composer",
    "DEFAULT_PAGE_SIZE",
    "ERROR",
    "ERROR_LEVEL",
    "GuiAdapter",
    "MESSAGE_OPENED_CURRENT_SESSION",
    "MESSAGE_SELECTED_READ",
    "MESSAGE_SELECTED_UNREAD",
    "NO_WORKSPACE",
    "OK",
    "Page",
    "REASON_COMPOSER_EMPTY",
    "REASON_EMPTY_INBOX",
    "REASON_NO_FILTERS",
    "REASON_NO_RECIPIENTS",
    "REASON_NO_WORKSPACE",
    "REASON_OPEN_ALREADY_READ",
    "REASON_READ_NOT_THIS_SESSION",
    "REASON_REOPEN_NONE",
    "REASON_REOPEN_NOT_READ",
    "REASON_REPLY_NONE",
    "REASON_REPLY_UNREAD",
    "Status",
    "WARNING",
    "WORKSPACE_LOADED",
]
