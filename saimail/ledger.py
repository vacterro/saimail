"""Append-only delivery ledger with reconstructable state (FUTURE GATE Wave 2).

Defect class this module eliminates: a mutable projection that is the only
truth. Today the outbox intents and the Post Office index ARE the state: a
question like "was this message ever delivered, and did we lose the receipt or
never send it?" has no answer if the file that would have said so is gone, and a
file that parses as empty is indistinguishable from one that was never written.

The ledger is the answer, and it is deliberately dull: one hash-chained JSON
line per fact, appended and fsynced, never rewritten. The transitions that used
to be implied by whichever file happened to survive become explicit records:

    CREATED -> SEALED -> OUTBOX_COMMITTED -> DELIVERY_ATTEMPTED -> DELIVERED
            -> RECEIPT_OBSERVED -> OPENED -> REPLIED
    and at any point: FAILED (re-armable), QUARANTINED, SUPERSEDED

Three properties are load-bearing:

* **Missing is not unreadable.** No ledger file means "this workspace predates
  the ledger" -- an honest empty, reported as ``ABSENT``. A ledger file that
  cannot be parsed, or whose hash chain does not verify, is ``UNKNOWN``: it is
  never folded into "0 pending" or "nothing happened". That distinction is the
  whole point of the module.
* **Folding is pure.** :func:`fold` takes events and returns current state plus
  the transitions it rejected, so state after a crash is computed from the
  record rather than trusted from a file that may have been half-written.
* **The projection is rebuildable.** The outbox intent and the Post Office index
  row are both derived, and those are the two :func:`reconcile` repairs. (The
  Future Letter registry row is derived too, but nothing rebuilds it from here,
  so ``reconcile`` returns it as empty rather than claiming a repair it does not
  perform.) :func:`reconcile` compares them against the fold and repairs from
  the CANONICAL source -- the sealed container or the authenticated index --
  never by inventing mail.

Appends are best-effort by design and say so: mail that has already been
delivered must not be reported as undelivered because a bookkeeping append hit a
full disk. :func:`health` reports a ledger that exists but cannot be extended,
so the loss of the record is visible even though the send succeeded.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path, PurePath

from sailang import SailangError
from saimail import envelope
from saimail import _journal_cache
from saimail import postoffice
from saimail import workspace as _workspace

LEDGER_SCHEMA = "SAIMAIL_LEDGER_1"
LEDGER_VERSION = 1
LEDGER_DIR = "ledger"
LEDGER_NAME = "events.jsonl"
LOCK_NAME = "ledger.lock"

CREATED = "CREATED"
SEALED = "SEALED"
OUTBOX_COMMITTED = "OUTBOX_COMMITTED"
DELIVERY_ATTEMPTED = "DELIVERY_ATTEMPTED"
DELIVERED = "DELIVERED"
RECEIPT_OBSERVED = "RECEIPT_OBSERVED"
OPENED = "OPENED"
REPLIED = "REPLIED"
FAILED = "FAILED"
QUARANTINED = "QUARANTINED"
SUPERSEDED = "SUPERSEDED"

EVENTS = (CREATED, SEALED, OUTBOX_COMMITTED, DELIVERY_ATTEMPTED, DELIVERED,
          RECEIPT_OBSERVED, OPENED, REPLIED, FAILED, QUARANTINED, SUPERSEDED)

#: The legal transitions. A record outside this table is not folded silently:
#: it is collected as invalid so a caller can see that history disagreed with
#: itself instead of receiving a confident wrong answer.
TRANSITIONS = {
    # Sender side. A logical message is keyed by its outbox idempotency key and
    # moves PENDING -> SEALED -> COMMITTED -> ATTEMPTED -> one terminal state.
    CREATED: {SEALED, FAILED, SUPERSEDED},
    SEALED: {OUTBOX_COMMITTED, FAILED, SUPERSEDED},
    OUTBOX_COMMITTED: {DELIVERY_ATTEMPTED, FAILED, SUPERSEDED},
    DELIVERY_ATTEMPTED: {DELIVERED, FAILED, QUARANTINED, SUPERSEDED},
    # A delivered message can be redelivered from the stored container; the
    # attempt is recorded, the outcome is not a new lifecycle.
    DELIVERED: {DELIVERY_ATTEMPTED, SUPERSEDED},
    # Receiving side. A logical message is keyed by its ENVELOPE_ID and starts
    # at RECEIPT_OBSERVED, which is written when the body is durable and before
    # the index row -- so a crash in that window is visible here.
    RECEIPT_OBSERVED: {OPENED, REPLIED, SUPERSEDED},
    OPENED: {REPLIED, SUPERSEDED},
    REPLIED: {SUPERSEDED},
    # A terminal failure is re-armable: an explicit retry records a new attempt.
    FAILED: {DELIVERY_ATTEMPTED, SUPERSEDED},
    QUARANTINED: {SUPERSEDED},
    SUPERSEDED: set(),
}

#: Ledger health, three-valued. UNKNOWN is the honest answer for a ledger that
#: exists but cannot be read; it must never degrade to a zero.
HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
UNKNOWN = "UNKNOWN"

STATE_OK = "OK"
STATE_ABSENT = "ABSENT"
STATE_UNREADABLE = "UNREADABLE"

LEDGER_UNREADABLE = "LEDGER_UNREADABLE"
LEDGER_CHAIN_BROKEN = "LEDGER_CHAIN_BROKEN"
LEDGER_LOCK_TIMEOUT = "LEDGER_LOCK_TIMEOUT"
LEDGER_WRITE_FAILED = "LEDGER_WRITE_FAILED"
BAD_CURSOR = postoffice.BAD_CURSOR
BAD_EVENT = "BAD_LEDGER_EVENT"

OPERATOR_ACTION_CODES = frozenset({
    LEDGER_UNREADABLE, LEDGER_CHAIN_BROKEN, LEDGER_LOCK_TIMEOUT, LEDGER_WRITE_FAILED,
})

_EVENT_FIELDS = frozenset({"schema", "seq", "event", "message_id", "envelope_id",
                           "actor", "at", "attempt", "causal", "prev", "hash",
                           "detail"})

MAX_DETAIL_BYTES = 512
MAX_LINE_BYTES = 8 * 1024
DEFAULT_FEED_LIMIT = 50


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _operator_action(result: dict) -> dict:
    """Mark one result as needing a human, whatever the generic rule says.

    A record nobody can read is not a clean run. The generic `command_result`
    would call UNKNOWN fine, because it only knows about refusal and
    quarantine, so the ledger says so itself.
    """
    result["ok"] = False
    result["operator_action_required"] = True
    return result


def _event_bytes(event: dict) -> bytes:
    """The hashed body: every field except the hash itself."""
    return _canonical_bytes({name: value for name, value in event.items()
                             if name != "hash"})


def _root_of(target) -> Path:
    """Accept a workspace view or a bare mailbox root.

    The Post Office knows only its own root, and importing a workspace there
    would be a cycle; the ledger is the same durable record either way.

    `Path` is matched first on purpose: `pathlib.PurePath.root` is the drive
    anchor -- ``"V:\\"``, not the mailbox. Reading `.root` off a bare Path would
    file every Post Office note under the root of the volume.
    """
    if isinstance(target, PurePath):
        return Path(target)
    return Path(getattr(target, "root", target))


def _seat_of(target, default: str = "") -> str:
    return getattr(target, "seat", default)


def ledger_path(target) -> Path:
    return _root_of(target) / LEDGER_DIR / LEDGER_NAME


def _lock(target):
    return postoffice._OsFileLock(_root_of(target) / LEDGER_DIR / LOCK_NAME,
                                  busy_code=LEDGER_LOCK_TIMEOUT)


def _parse_line(raw: bytes, lineno: int) -> dict:
    try:
        event = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _reject(LEDGER_UNREADABLE, f"ledger line {lineno} is not canonical JSON: {exc}")
    if not isinstance(event, dict) or set(event) != _EVENT_FIELDS:
        _reject(LEDGER_UNREADABLE, f"ledger line {lineno} has an unexpected field set")
    if event["schema"] != LEDGER_SCHEMA:
        _reject(LEDGER_UNREADABLE, f"ledger line {lineno} declares an unknown schema")
    if event["event"] not in EVENTS:
        _reject(LEDGER_UNREADABLE, f"ledger line {lineno} names unknown event "
                                   f"{event['event']!r}")
    if not isinstance(event["seq"], int) or event["seq"] < 1:
        _reject(LEDGER_UNREADABLE, f"ledger line {lineno} has a bad sequence number")
    if event["hash"] != _sha256(_event_bytes(event)):
        _reject(LEDGER_CHAIN_BROKEN,
                f"ledger line {lineno} does not hash to its own recorded hash")
    return event


@dataclass
class _LedgerSnapshot:
    state: str = STATE_ABSENT
    positions: list = field(default_factory=list)
    first_seq: int = 0
    last_hash: str | None = None
    lines: int = 0
    terminated: bool = True


def _load_ledger(path):
    snapshot = _LedgerSnapshot()
    try:
        handle = path.open("rb")
    except FileNotFoundError:
        return snapshot
    snapshot.state = STATE_OK
    with handle:
        while True:
            offset = handle.tell()
            raw = handle.readline(MAX_LINE_BYTES + 3)
            if not raw:
                break
            snapshot.lines += 1
            snapshot.terminated = raw.endswith(b"\n")
            raw = raw.rstrip(b"\r\n")
            if len(raw) > MAX_LINE_BYTES:
                _reject(LEDGER_UNREADABLE,
                        f"ledger line {snapshot.lines} exceeds {MAX_LINE_BYTES} bytes")
            if not raw.strip():
                continue
            event = _parse_line(raw, snapshot.lines)
            if event["prev"] != snapshot.last_hash:
                _reject(LEDGER_CHAIN_BROKEN,
                        f"ledger seq {event['seq']} does not chain to the previous record")
            expected = snapshot.first_seq + len(snapshot.positions)
            if snapshot.positions and event["seq"] != expected:
                _reject(LEDGER_CHAIN_BROKEN,
                        f"ledger sequence is not contiguous: expected {expected}, "
                        f"found {event['seq']}")
            if not snapshot.positions:
                snapshot.first_seq = event["seq"]
            snapshot.positions.append((offset, snapshot.lines))
            snapshot.last_hash = event["hash"]
    return snapshot


def _window(path, cache, snapshot, start=0, limit=None):
    positions = snapshot.positions[start:] if limit is None else snapshot.positions[start:start + limit]
    events = []
    if positions:
        with path.open("rb") as handle:
            for offset, lineno in positions:
                handle.seek(offset)
                events.append(_parse_line(handle.readline(MAX_LINE_BYTES + 3).rstrip(b"\r\n"), lineno))
    cache.check(path)
    return events


def read_events(target) -> tuple:
    """``(events, state)``. ABSENT is empty; UNREADABLE is not empty.

    The distinction is the module's reason for existing, so the reader never
    converts one into the other: a caller that receives an empty tuple is told,
    separately and explicitly, whether there was no history or unreadable
    history.
    """
    path = ledger_path(target)
    cache = _journal_cache.for_path(path)
    try:
        with cache.lock:
            snapshot = cache.load(path, _load_ledger)
            return _window(path, cache, snapshot), snapshot.state
    except OSError as exc:
        _reject(LEDGER_UNREADABLE, f"ledger cannot be read: {exc}")


def append(target, event: str, *, message_id: str, actor: str, at: str,
           envelope_id=None, attempt: int = 0, causal=None, detail=None) -> dict | None:
    """Record one fact. Best effort: a send that already happened is not undone.

    Returns the appended event, or ``None`` when the record could not be
    written -- which :func:`health` then reports. Raising here would turn a
    bookkeeping failure into a false delivery failure.
    """
    # Caller mistakes are validated before the best-effort block and DO raise:
    # an unknown event name or an oversized detail is a bug in this codebase,
    # and hiding it would leave a silent hole in the record. Only genuine I/O
    # failure below is swallowed.
    if event not in EVENTS:
        _reject(BAD_EVENT, f"unknown ledger event {event!r}; the set is closed")
    payload = _bounded_detail(detail)
    path = ledger_path(target)
    cache = _journal_cache.for_path(path)
    try:
        with _lock(target), cache.lock:
            snapshot = cache.load(path, _load_ledger)
            if not snapshot.terminated:
                _reject(LEDGER_UNREADABLE, "ledger has an unterminated final row; refusing append")
            previous = snapshot.last_hash
            seq = snapshot.first_seq + len(snapshot.positions) if snapshot.positions else 1
            record = {"schema": LEDGER_SCHEMA, "seq": seq, "event": event,
                      "message_id": message_id, "envelope_id": envelope_id,
                      "actor": actor, "at": at, "attempt": int(attempt),
                      "causal": causal, "prev": previous, "detail": payload}
            record["hash"] = _sha256(_event_bytes(record))
            path.parent.mkdir(parents=True, exist_ok=True)
            line = _canonical_bytes(record) + b"\n"

            def advance(value, offset):
                value.lines += 1
                if not value.positions:
                    value.first_seq = seq
                value.positions.append((offset, value.lines))
                value.last_hash = record["hash"]
                value.state = STATE_OK

            cache.append(path, line, advance)
        return record
    except SailangError:
        return None
    except OSError:
        return None


def _bounded_detail(detail) -> dict | None:
    if detail is None:
        return None
    if not isinstance(detail, dict):
        _reject(BAD_EVENT, "ledger detail is a small object or absent")
    trimmed = {}
    for name, value in detail.items():
        if not isinstance(name, str) or len(name) > 64:
            _reject(BAD_EVENT, "ledger detail keys are short strings")
        text = value if isinstance(value, str) else str(value)
        if len(text.encode("utf-8")) > MAX_DETAIL_BYTES:
            _reject(BAD_EVENT, f"ledger detail {name!r} exceeds {MAX_DETAIL_BYTES} bytes")
        trimmed[name] = text
    return trimmed


def note(target, event: str, **fields) -> None:
    """The integration shim: record a fact, never raise at the call site."""
    try:
        append(target, event, **fields)
    except SailangError:
        return


def fold(events) -> dict:
    """Current state per logical message, plus every rejected transition.

    Pure: same events in, same answer out. Duplicates are idempotent (the same
    hash twice changes nothing), and a transition the table forbids is
    collected under ``invalid`` instead of being folded as if it had happened.
    """
    state: dict = {}
    invalid: list = []
    seen: set = set()
    for event in events:
        digest = event.get("hash")
        if digest in seen:
            continue
        seen.add(digest)
        message_id = event["message_id"]
        previous = state.get(message_id)
        if previous is not None and event["event"] not in TRANSITIONS[previous["state"]]:
            invalid.append({"message_id": message_id, "seq": event["seq"],
                            "from": previous["state"], "to": event["event"],
                            "reason": "ILLEGAL_TRANSITION"})
            continue
        history = previous["history"] if previous else []
        history.append(event["event"])
        state[message_id] = {
            "message_id": message_id,
            "state": event["event"],
            "envelope_id": event.get("envelope_id") or (previous or {}).get("envelope_id"),
            "actor": event.get("actor"),
            "last_at": event.get("at"),
            "seq": event["seq"],
            "attempts": (previous or {}).get("attempts", 0) + (
                1 if event["event"] == DELIVERY_ATTEMPTED else 0),
            "history": history,
        }
    return {"messages": state, "invalid": invalid}


def feed(workspace, *, cursor: int = 0, limit: int = DEFAULT_FEED_LIMIT) -> dict:
    """A bounded, gap-aware view of the record.

    A cursor older than the oldest retained sequence is a CONTINUITY GAP and is
    reported as one. A trimmed feed that quietly returns the next page would let
    a reader believe it saw everything.
    """
    if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
        _reject(BAD_CURSOR, "cursor is a non-negative integer")
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        _reject(BAD_EVENT, "limit is a positive integer")
    try:
        path = ledger_path(workspace)
        cache = _journal_cache.for_path(path)
        with cache.lock:
            snapshot = cache.load(path, _load_ledger)
            state = snapshot.state
            oldest = snapshot.first_seq
            count = len(snapshot.positions)
            last_seq = oldest + count - 1 if count else 0
            start = max(0, cursor + 1 - oldest) if count else 0
            window = _window(path, cache, snapshot, start, limit)
    except (SailangError, OSError) as exc:
        code = exc.code if isinstance(exc, SailangError) else LEDGER_UNREADABLE
        return _operator_action(_workspace.command_result(
            "ledger-feed", UNKNOWN, workspace=workspace,
            ledger={"schema": LEDGER_SCHEMA, "state": STATE_UNREADABLE,
                    "reason": code},
            events=[], gap=False, cursor=cursor,
            detail=f"ledger is {UNKNOWN} ({code}); history was NOT reported as empty"))
    gap = bool(count) and cursor + 1 < oldest
    return _workspace.command_result(
        "ledger-feed", state, workspace=workspace,
        ledger={"schema": LEDGER_SCHEMA, "state": state, "count": count,
                "first_seq": oldest, "last_seq": last_seq},
        events=window, gap=gap, truncated=bool(window) and window[-1]["seq"] < (
            last_seq),
        cursor=window[-1]["seq"] if window else cursor,
        detail=("continuity GAP: the requested cursor predates the oldest retained "
                "record" if gap else f"{len(window)} event(s) after seq {cursor}"))


def health(workspace) -> dict:
    """Whether the record can be read, and whether it can still be written."""
    state = HEALTHY
    reason = None
    counts: dict = {}
    folded = {"messages": {}, "invalid": []}
    try:
        events, read_state = read_events(workspace)
    except SailangError as exc:
        events, read_state = [], STATE_UNREADABLE
        state, reason = UNKNOWN, exc.code
    if state != UNKNOWN:
        if read_state == STATE_ABSENT:
            reason = "NO_HISTORY"
        else:
            folded = fold(events)
            counts = {name: sum(1 for item in folded["messages"].values()
                                if item["state"] == name)
                      for name in EVENTS}
            if folded["invalid"]:
                state, reason = DEGRADED, "ILLEGAL_TRANSITIONS"
    result = _workspace.command_result(
        "ledger-health", state, workspace=workspace,
        ledger={"schema": LEDGER_SCHEMA, "version": LEDGER_VERSION,
                "state": state, "read_state": read_state, "reason": reason,
                "counts": counts,
                "messages": len(folded["messages"])},
        detail=f"ledger {state}"
               + (f" ({reason})" if reason else "; a missing ledger is no history, "
                  "an unreadable one is UNKNOWN"))
    # A record nobody can read is not a healthy record, and not a clean zero:
    # the operator has to act on it, and `ok` is the field they read.
    if state in (UNKNOWN, DEGRADED):
        _operator_action(result)
    return result


def reconcile(workspace, *, clock=None) -> dict:
    """Rebuild the missing projections from the canonical sources.

    Three rules, and the third is the whole point:

    1. An unreadable ledger is never reconciled from. Repairing off a record
       nobody can read would be guessing with extra steps, so this reports
       UNKNOWN and changes nothing.
    2. Every repair reads a CANONICAL source: the authenticated bundle for a
       mailbox projection, the sealed container bytes for an outbox copy. The
       ledger says what *should* exist; it is never itself the bytes.
    3. Nothing is ever invented. A message the record names but whose canonical
       bytes are gone everywhere is reported ``UNREPAIRABLE`` and left absent.
       A repair that made mail appear out of nothing would be worse than the
       crash it is repairing.
    """
    try:
        events, read_state = read_events(workspace)
    except SailangError as exc:
        return _operator_action(_workspace.command_result(
            "ledger-reconcile", UNKNOWN, workspace=workspace,
            ledger={"schema": LEDGER_SCHEMA, "state": STATE_UNREADABLE,
                    "reason": exc.code, "count": 0, "considered": 0},
            restored={"index": [], "outbox": []}, unrepairable=[], invented=[],
            detail=f"ledger is {UNKNOWN} ({exc.code}); nothing was repaired, because "
                   f"repairing off a record nobody can read is guessing"))
    folded = fold(events)
    office = workspace.office(clock=clock) if hasattr(workspace, "office") else None
    restored_index: list = []
    restored_outbox: list = []
    unrepairable: list = []
    considered = 0
    intent_containers = None
    for message in folded["messages"].values():
        envelope_id = message.get("envelope_id")
        if not envelope_id:
            continue
        considered += 1
        # Canonical source 1: a bundle this mailbox actually holds. An
        # envelope_id the Post Office cannot even address is not a source -- it
        # is a row nothing can repair -- so it is reported rather than allowed
        # to abort the pass over every other message behind it.
        try:
            state = office.bundle_state(envelope_id) if office is not None \
                else "NEITHER"
        except SailangError:
            unrepairable.append(envelope_id)
            continue
        if state in ("UNREAD", "READ", "BOTH"):
            row = office.read_index_row(envelope_id)
            if row is None:
                raw = office._read_bundle_container(
                    office.inbox_bundle(envelope_id)
                    if state == "UNREAD" else office.read_bundle(envelope_id))
                header = envelope.parse_header(raw)
                envelope.verify(header, office.sender_registry)
                _, stored_at = postoffice._read_receipt(
                    office.inbox_bundle(envelope_id)
                    if state == "UNREAD" else office.read_bundle(envelope_id))
                if office.ensure_index_row(header, envelope_id, stored_at):
                    restored_index.append(envelope_id)
            continue
        # Canonical source 2: the sealed container this workspace authored.
        path = _workspace._outbox_path(workspace, envelope_id)
        if path.is_file():
            continue
        if intent_containers is None:
            intent_containers = _containers_from_intents(workspace)
        recovered = intent_containers.get(envelope_id)
        if recovered is None:
            unrepairable.append(envelope_id)
            continue
        _workspace._store_outbox(workspace, envelope_id, recovered)
        restored_outbox.append(envelope_id)
    return _workspace.command_result(
        "ledger-reconcile", read_state, workspace=workspace,
        ledger={"schema": LEDGER_SCHEMA, "state": read_state,
                "count": len(events), "considered": considered},
        restored={"index": restored_index, "outbox": restored_outbox},
        unrepairable=unrepairable,
        invented=[],
        detail=(f"{len(restored_index)} mailbox row(s) and {len(restored_outbox)} outbox "
                f"copy/copies rebuilt from canonical bytes; "
                f"{len(unrepairable)} message(s) have no canonical source and were NOT "
                f"invented"))


def _containers_from_intents(workspace) -> dict[str, str]:
    """One verified envelope-to-container snapshot for a reconciliation pass.

    The intent is a projection too, but it is the one that still holds the
    sealed bytes; recovering a container from them proves the recovery rather
    than asserting it.
    """
    from saimail import outbox

    try:
        intents = outbox._all_intents(workspace)
    except SailangError:
        return {}
    containers = {}
    for intent in intents:
        envelope_id = intent.get("envelope_id")
        if envelope_id and isinstance(
                intent.get("container"), str) and intent["container"]:
            try:
                if envelope.envelope_id(intent["container"]) != envelope_id:
                    continue
            except SailangError:
                continue
            containers.setdefault(envelope_id, intent["container"])
    return containers


def reconstruct(workspace, *, clock=None) -> dict:
    """Current delivery state folded from the record, per logical message.

    This is the answer to "what actually happened", and it is deliberately
    available even when the projection files disagree with it.
    """
    events, read_state = read_events(workspace)
    folded = fold(events)
    messages = [dict(name, invalid=False) for name in
                sorted(folded["messages"].values(), key=lambda item: item["seq"])]
    for item in folded["invalid"]:
        messages.append(dict(item, invalid=True))
    return _workspace.command_result(
        "ledger-reconstruct", read_state, workspace=workspace,
        ledger={"schema": LEDGER_SCHEMA, "state": read_state,
                "count": len(events), "invalid": len(folded["invalid"])},
        messages=messages,
        detail=f"{len(folded['messages'])} message(s) reconstructed from the record"
               + (f"; {len(folded['invalid'])} illegal transition(s) recorded"
                  if folded["invalid"] else ""))


__all__ = [
    "BAD_EVENT",
    "CREATED",
    "DEGRADED",
    "DELIVERED",
    "DELIVERY_ATTEMPTED",
    "EVENTS",
    "FAILED",
    "HEALTHY",
    "LEDGER_CHAIN_BROKEN",
    "LEDGER_LOCK_TIMEOUT",
    "LEDGER_SCHEMA",
    "LEDGER_UNREADABLE",
    "LEDGER_WRITE_FAILED",
    "OPENED",
    "OPERATOR_ACTION_CODES",
    "OUTBOX_COMMITTED",
    "QUARANTINED",
    "RECEIPT_OBSERVED",
    "REPLIED",
    "SEALED",
    "STATE_ABSENT",
    "STATE_OK",
    "STATE_UNREADABLE",
    "SUPERSEDED",
    "TRANSITIONS",
    "UNKNOWN",
    "append",
    "feed",
    "fold",
    "health",
    "ledger_path",
    "note",
    "read_events",
    "reconcile",
    "reconstruct",
]
