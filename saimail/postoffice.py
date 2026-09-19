"""SAIMAIL Post Office v0 — durable delivery, header-only scan, budgeted open.

The contract is `spec/03-POST-OFFICE.md` and `spec/DECISIONS.md` D-031/D-037;
this module implements it and never invents a second one. Four properties are
load-bearing here:

* **Delivery is verified before it is stored.** Raw SENV2 bytes are parsed,
  signature-checked against the receiver's own `KeyRegistry`, checked against
  this seat and this seat's `RecipientKeyRegistry`, and only then written as one
  immutable inbox bundle plus one canonical index row. A bounded object that
  fails any of those gates goes to `quarantine/` under a raw-bytes hash that is
  never an `ENVELOPE_ID`; no recipient private key is needed and no payload is
  decrypted during delivery.
* **The commit is ordered and crash-recoverable.** The immutable bundle is
  published first, the index row second; `recover()` re-derives the missing row
  from the bundle's own `receipt.json`, so the original `RECEIVED_AT` is kept
  and a replay never becomes a second message (D-031). Deduplication covers the
  whole active lifecycle: a replay of an object that already sits in `read/` is
  a `DUPLICATE` that resurrects nothing, never a fresh unread inbox bundle, and
  an abnormal pair of crash copies is reconciled only by mechanical byte
  identity — never by byte length.
* **Scan is header-only and its budget bounds real work.** `scan()` streams
  `index.jsonl` from a byte-offset cursor, parses at most the declared number of
  new rows per call and stops there, and reads the mailbox's directory state —
  never `.senv` payload bytes, never `parse_header`/`verify`/`open`, never a
  model. Attention is the receiver-owned `HeaderInterest` rule, and an optional
  caller-supplied model recommendation is merged monotonically: it may raise
  attention, never lower it (D-036/D-037).
* **Opening is explicit and budgeted.** One `PostOfficeSession` declares a scan
  budget (index rows examined per scan operation) and an open budget (open
  attempts per session); exhaustion is a named refusal and never a silent stop.
  A successful open moves the same bundle from `inbox/` to `read/` without
  touching the index and returns the `OpenedEnvelope`; promotion stays a
  separate, payload-bound caller decision — this module never calls it.

The Post Office root is supplied by the caller; no user path is hardcoded. The
layout is `mail/{inbox/<seat>,read/<seat>,quarantine,expired/<seat>,promoted}`
plus `mail/index.jsonl`. `expired/<seat>/` holds immutable TTL tombstones
(D-038/T-7, hardened by D-039); `promoted/` stays reserved and holds nothing.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, FrozenSet, Mapping, Optional, Tuple

from sailang.errors import SailangError

from saimail import envelope, publish
from saimail.envelope import Header, OpenedEnvelope
from saimail.selector import DEFER, IGNORE, OPEN_R2, OPEN_R3, VERDICTS, Decision, depth

SCHEMA_VERSION = 1
INDEX_NAME = "index.jsonl"
INBOX = "inbox"
READ = "read"
QUARANTINE = "quarantine"
EXPIRED = "expired"
PROMOTED = "promoted"

CONTAINER_NAME = "envelope.senv"
RECEIPT_NAME = "receipt.json"
OBJECT_NAME = "object.bin"
REASON_NAME = "reason.json"
MAIL_DIR = "mail"

ACCEPTED = "ACCEPTED"
DUPLICATE = "DUPLICATE"
QUARANTINED = "QUARANTINED"
REFUSED = "REFUSED"

PUBLISHED = "PUBLISHED"
IDEMPOTENT = "IDEMPOTENT"

UNREAD = "UNREAD"
READ_STATE = "READ"
BOTH = "BOTH"
NEITHER = "NEITHER"
EXPIRED_STATE = "EXPIRED"

#: Refusal codes owned by this module. A caller branches on these, never on
#: the human detail.
OPEN_BUDGET_EXHAUSTED = "OPEN_BUDGET_EXHAUSTED"
ALREADY_READ = "ALREADY_READ"
INDEX_CORRUPT = "INDEX_CORRUPT"
INDEX_DUPLICATE_ENVELOPE_ID = "INDEX_DUPLICATE_ENVELOPE_ID"
INDEX_ROW_CONFLICT = "INDEX_ROW_CONFLICT"
INDEX_BODY_MISSING = "INDEX_BODY_MISSING"
READ_BUNDLE_CONFLICT = "READ_BUNDLE_CONFLICT"
RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
ENVELOPE_ID_CONFLICT = "ENVELOPE_ID_CONFLICT"
RECEIPT_CORRUPT = "RECEIPT_CORRUPT"
BUNDLE_INVALID = "BUNDLE_INVALID"
UNKNOWN_MODEL_VERDICT = "UNKNOWN_MODEL_VERDICT"
BAD_BUDGET = "BAD_BUDGET"
BAD_CURSOR = "BAD_CURSOR"
NOT_A_POST_OFFICE = "NOT_A_POST_OFFICE"
NOT_A_SESSION = "NOT_A_SESSION"

#: TTL sweep refusals and states (D-038).
RECEIVER_TTL_OUT_OF_RANGE = "RECEIVER_TTL_OUT_OF_RANGE"
BAD_TTL_POLICY = "BAD_TTL_POLICY"
ALREADY_EXPIRED = "ALREADY_EXPIRED"
EXPIRY_RECONCILIATION_REQUIRED = "EXPIRY_RECONCILIATION_REQUIRED"
EXPIRY_STATE_CONFLICT = "EXPIRY_STATE_CONFLICT"
EXPIRED_TOMBSTONE_CONFLICT = "EXPIRED_TOMBSTONE_CONFLICT"
EXPIRED_TOMBSTONE_CORRUPT = "EXPIRED_TOMBSTONE_CORRUPT"
LIFECYCLE_LOCK_TIMEOUT = "LIFECYCLE_LOCK_TIMEOUT"
TTL_EXPIRED = "TTL_EXPIRED"

TOMBSTONE_NAME = "tombstone.json"
LIFECYCLE_LOCK_NAME = "lifecycle.lock"
INDEX_LOCK_NAME = "index.lock"

#: Receiver-owned default retention (D-038): 14 days, inside the allowed v0
#: range. The sender `TTL` header is a retention CEILING over this default,
#: never an authority to force longer storage.
DEFAULT_TTL_SECONDS = 14 * 24 * 60 * 60
MIN_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_TTL_SECONDS = 30 * 24 * 60 * 60
_TOMBSTONE_SCHEMA = 1
_TOMBSTONE_KEYS = frozenset({
    "schema", "envelope_id", "sender", "recipient", "kind", "received_at",
    "expired_at", "effective_ttl_seconds", "reason",
})

#: Delivery-level addressing refusals (the wire vocabulary itself supplies the
#: parse/verify codes, which are recorded verbatim in quarantine).
WRONG_RECIPIENT_SEAT = "WRONG_RECIPIENT_SEAT"
UNKNOWN_RECIPIENT_SEAT = "UNKNOWN_RECIPIENT_SEAT"
RECIPIENT_KEY_NOT_ACCEPTED = "RECIPIENT_KEY_NOT_ACCEPTED"
CONTAINER_OVERSIZE = "CONTAINER_OVERSIZE"
UNKNOWN_ENVELOPE = "UNKNOWN_ENVELOPE"

#: One index line is bounded; every field in it is parser-bounded too, so this
#: is a corruption tripwire, not a normal-size limit.
MAX_INDEX_LINE_BYTES = 4096
MAX_REASON_LINE_BYTES = 1024

#: Quarantine identity is derived from the raw bytes but domain-separated from
#: the ENVELOPE_ID namespace, so a quarantined object can never be mistaken for
#: (or collide with) the transport identity of an accepted envelope.
QUARANTINE_DOMAIN = b"SAIMAIL-QUARANTINE\x00"

_EID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_SEAT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TOPIC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

INDEX_REQUIRED_KEYS = frozenset({
    "schema", "envelope_id", "received_at", "from", "from_kid", "to", "to_kid",
    "kind", "topic", "created",
})
INDEX_OPTIONAL_KEYS = frozenset({"ref"})

#: The header policy evaluation order. OPEN rules first, strongest depth first;
#: a declared OPEN declaration always beats an overlapping IGNORE declaration
#: (false-ignore is more expensive than false-open, D-037).
_OPEN_RULES = (
    (OPEN_R3, "open_r3_topics", "topic", "HEADER-OPEN-R3-TOPIC"),
    (OPEN_R3, "open_r3_kinds", "kind", "HEADER-OPEN-R3-KIND"),
    (OPEN_R3, "open_r3_senders", "sender", "HEADER-OPEN-R3-SENDER"),
    (OPEN_R2, "open_r2_topics", "topic", "HEADER-OPEN-R2-TOPIC"),
    (OPEN_R2, "open_r2_kinds", "kind", "HEADER-OPEN-R2-KIND"),
    (OPEN_R2, "open_r2_senders", "sender", "HEADER-OPEN-R2-SENDER"),
)
_IGNORE_RULES = (
    ("ignore_topics", "topic", "HEADER-IGNORE-TOPIC"),
    ("ignore_kinds", "kind", "HEADER-IGNORE-KIND"),
    ("ignore_senders", "sender", "HEADER-IGNORE-SENDER"),
)


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def utc_now() -> str:
    """The receiver clock, in the one header format SENV2 already uses."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_utc(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(text, *, code: str) -> datetime:
    if not isinstance(text, str) or not _UTC_RE.match(text):
        _reject(code, f"expected a UTC instant, got {text!r}")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _reject(code, f"{text!r} is not a real UTC instant")


def _as_instant(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            _reject("BAD_CLOCK", "an instant must carry a timezone")
        return value
    return _parse_utc(value, code="BAD_CLOCK")


# --------------------------------------------------------------------------
# header attention (D-037): receiver-owned, deterministic, separate from R1
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HeaderInterest:
    """The receiver's declared header-only attention policy.

    This is deliberately not `saimail.selector.Interest`: the R1 selector reads
    a decoded `TriageView` and cannot run before a payload open; the Post
    Office scan sees only the clear index header. Sets are declared by the
    receiver and never inferred from traffic. Resolution is: strongest declared
    OPEN match wins, else an explicit IGNORE, else `DEFER`. An OPEN declaration
    beats an overlapping IGNORE declaration.
    """

    open_r3_topics: FrozenSet[str] = field(default_factory=frozenset)
    open_r2_topics: FrozenSet[str] = field(default_factory=frozenset)
    open_r3_kinds: FrozenSet[str] = field(default_factory=frozenset)
    open_r2_kinds: FrozenSet[str] = field(default_factory=frozenset)
    open_r3_senders: FrozenSet[str] = field(default_factory=frozenset)
    open_r2_senders: FrozenSet[str] = field(default_factory=frozenset)
    ignore_topics: FrozenSet[str] = field(default_factory=frozenset)
    ignore_kinds: FrozenSet[str] = field(default_factory=frozenset)
    ignore_senders: FrozenSet[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, frozenset(getattr(self, name)))

    @classmethod
    def of(cls, **sets) -> "HeaderInterest":
        unknown = set(sets) - set(cls.__dataclass_fields__)
        if unknown:
            _reject("UNKNOWN_HEADER_INTEREST",
                    f"not a declared header policy set: {sorted(unknown)}")
        return cls(**sets)

    def decide(self, view: "HeaderView") -> Decision:
        """One deterministic verdict for one header. No model, no network."""
        for verdict, attr, field_name, rule in _OPEN_RULES:
            value = getattr(view, field_name)
            if value is not None and value in getattr(self, attr):
                return Decision(verdict, rule,
                                f"declared {field_name} {value!r} opens at {verdict}")
        for attr, field_name, rule in _IGNORE_RULES:
            value = getattr(view, field_name)
            if value is not None and value in getattr(self, attr):
                return Decision(IGNORE, rule,
                                f"declared {field_name} {value!r} is ignored")
        return Decision(DEFER, "HEADER-DEFAULT", "no declared header rule matched; defer")


def merge_attention(machine: str, model: Optional[str]) -> Tuple[str, Optional[str], str]:
    """Merge a machine verdict with an optional caller-supplied model verdict.

    The smallest monotone rule (D-037): `final = max(machine, model)` on the
    attention depth ladder. A model may raise attention, never lower a
    receiver-owned deterministic verdict; a missing recommendation leaves the
    machine verdict untouched; an unknown token is refused, never guessed.
    """
    if machine not in VERDICTS:
        _reject("BAD_MACHINE_VERDICT", f"{machine!r} is not a selector verdict")
    if model is None:
        return machine, None, "MACHINE"
    if model not in VERDICTS:
        _reject(UNKNOWN_MODEL_VERDICT,
                f"{model!r} is not one of {list(VERDICTS)}; refusing to guess")
    if depth(model) > depth(machine):
        return model, model, "MODEL-RAISED"
    return machine, model, "MACHINE"


@dataclass(frozen=True)
class HeaderView:
    """One immutable clear header derived from an index row.

    It carries no payload bytes and no ciphertext: `envelope_id` names the
    transport object, `received_at` is the receiver's own observation, and
    `age_seconds` is derived at scan time from `received_at` — never from the
    sender-authored `created` (D-031). `sender`/`recipient` are the header's
    `FROM`/`TO` seats.
    """

    envelope_id: str
    sender: str
    recipient: str
    kind: str
    topic: str
    created: str
    received_at: str
    age_seconds: float
    ref: Optional[str] = None
    from_kid: Optional[str] = None
    to_kid: Optional[str] = None

    @property
    def age(self) -> timedelta:
        return timedelta(seconds=self.age_seconds)


# --------------------------------------------------------------------------
# results
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    envelope_id: Optional[str] = None
    received_at: Optional[str] = None
    quarantine_id: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class RecoveryResult:
    bundles_scanned: int
    rows_appended: int


@dataclass(frozen=True)
class SweepResult:
    """One explicit maintenance sweep (D-038).

    `examined` counts every live/expired candidate reached; `expired` counts
    bodies deleted after a tombstone commit; `retained` counts candidates not
    yet old enough; `already_expired` counts valid tombstones with no live body
    (idempotent re-sweep).
    """

    examined: int
    expired: int
    retained: int
    already_expired: int


@dataclass(frozen=True)
class ScanCursor:
    """A deterministic continuation point: the byte offset of the next row.

    The offset is a position in append-only `index.jsonl`, always at a line
    boundary; a continuation seeks there and parses no earlier row. It carries
    no prefix state, so duplicate-`ENVELOPE_ID` detection across separate scan
    calls belongs to `read_index()`, the full integrity read.
    """

    offset: int


@dataclass(frozen=True)
class ScanItem:
    view: HeaderView
    machine_verdict: str
    machine_rule: str
    machine_reason: str
    model_verdict: Optional[str]
    final_verdict: str
    final_rule: str


@dataclass(frozen=True)
class ScanResult:
    items: Tuple[ScanItem, ...]
    exhausted: bool
    cursor: Optional[ScanCursor]
    rows_examined: int


# --------------------------------------------------------------------------
# filesystem helpers
# --------------------------------------------------------------------------


def _fsync_directory(directory: Path) -> None:
    """Persist a directory entry where the platform allows it (publish.py's rule)."""
    if os.name == "nt":
        return
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _write_complete(path: Path, data: bytes) -> None:
    with path.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _canonical_json_line(payload: Mapping) -> bytes:
    line = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return (line + "\n").encode("utf-8")


def _duplicate_guard(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            _reject(INDEX_CORRUPT, f"index JSON object repeats key {key!r}")
        seen.add(key)
    return dict(pairs)


class _OsFileLock:
    """An OS-backed exclusive lock; the OS lock is the authority.

    The lock file is not ownership evidence — process death releases it
    automatically (Windows `msvcrt`, POSIX `fcntl`), which is what lets
    concurrent writers append without rewriting the index or trusting Python
    threading. `busy_code` names the refusal a timed-out waiter receives, so the
    index lock and the lifecycle lock keep their own vocabularies.
    """

    TIMEOUT_SECONDS = 30.0

    def __init__(self, path: Path, *, busy_code: str = "INDEX_LOCK_TIMEOUT"):
        self._path = path
        self._busy_code = busy_code
        self._fd: Optional[int] = None

    def __enter__(self) -> "_OsFileLock":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = os.open(self._path, os.O_RDWR | os.O_CREAT, 0o600)
        if os.fstat(self._fd).st_size == 0:
            os.write(self._fd, b"\0")
        os.lseek(self._fd, 0, os.SEEK_SET)
        self._acquire(self._fd, self._busy_code)
        return self

    def __exit__(self, *exc_info) -> None:
        if self._fd is not None:
            try:
                self._release(self._fd)
            finally:
                os.close(self._fd)
                self._fd = None

    @classmethod
    def _acquire(cls, fd: int, busy_code: str) -> None:
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + cls.TIMEOUT_SECONDS
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    return
                except OSError:
                    if time.monotonic() > deadline:
                        _reject(busy_code, "another process holds this mailbox lock")
                    time.sleep(0.01)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)

    @classmethod
    def _release(cls, fd: int) -> None:
        if os.name == "nt":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)


class _MailboxLock(_OsFileLock):
    """The index lock: appends one canonical row per ENVELOPE_ID in order."""

    def __init__(self, path: Path):
        super().__init__(path, busy_code="INDEX_LOCK_TIMEOUT")


class _LifecycleLock(_OsFileLock):
    """The mailbox lifecycle lock (D-038).

    One fixed ordering exists: `LIFECYCLE LOCK` then `INDEX LOCK`, never the
    reverse. Every destructive lifecycle transition (`deliver`, the inbox→read
    transition, `recover`, `sweep_expired`) holds it, so an open/sweep or
    replay/sweep race resolves to exactly one coherent lifecycle state.
    """

    def __init__(self, path: Path):
        super().__init__(path, busy_code="LIFECYCLE_LOCK_TIMEOUT")


# --------------------------------------------------------------------------
# index rows
# --------------------------------------------------------------------------


def _bundle_name(envelope_id: str) -> str:
    """The filesystem name of one bundle: the digest half of the ENVELOPE_ID.

    A bundle path is a directory name, and Windows path segments cannot carry
    the ``sha256:`` prefix's colon; the full ENVELOPE_ID stays the logical
    identity in every index row and receipt.
    """
    if not isinstance(envelope_id, str) or not _EID_RE.match(envelope_id):
        _reject("BAD_ENVELOPE_ID", "an envelope id is sha256:<64 lowercase hex>")
    return envelope_id.split(":", 1)[1]


def _contract_fields(header: Header) -> dict:
    fields = {"from": header.get("FROM"), "from_kid": header.get("FROM_KID"),
              "to": header.get("TO"), "to_kid": header.get("TO_KID"),
              "kind": header.get("K"), "topic": header.get("TOPIC"),
              "created": header.get("CREATED")}
    ref = header.get("REF")
    if ref is not None:
        fields["ref"] = ref
    return fields


def _index_row(header: Header, envelope_id: str, received_at: str) -> dict:
    row = {"schema": SCHEMA_VERSION, "envelope_id": envelope_id,
           "received_at": received_at}
    row.update(_contract_fields(header))
    return row


def _row_line_bytes(row: Mapping) -> bytes:
    data = _canonical_json_line(row)
    if len(data) > MAX_INDEX_LINE_BYTES:
        _reject("INDEX_LINE_OVERSIZE",
                f"one index line exceeds {MAX_INDEX_LINE_BYTES} bytes")
    return data


def _parse_index_line(raw: bytes) -> dict:
    if len(raw) > MAX_INDEX_LINE_BYTES:
        _reject(INDEX_CORRUPT, "an index line exceeds the declared bound")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _reject(INDEX_CORRUPT, "an index line is not UTF-8")
    try:
        row = json.loads(text, object_pairs_hook=_duplicate_guard)
    except SailangError:
        raise
    except ValueError as exc:
        _reject(INDEX_CORRUPT, f"an index line is not JSON: {exc}")
    if not isinstance(row, dict):
        _reject(INDEX_CORRUPT, "an index line is not a JSON object")
    keys = set(row)
    missing = INDEX_REQUIRED_KEYS - keys
    extra = keys - INDEX_REQUIRED_KEYS - INDEX_OPTIONAL_KEYS
    if missing or extra:
        _reject(INDEX_CORRUPT,
                f"index row keys deviate from the contract: missing {sorted(missing)}, "
                f"extra {sorted(extra)}")
    if row.get("schema") != SCHEMA_VERSION:
        _reject(INDEX_CORRUPT, f"unknown index row schema {row.get('schema')!r}")
    if not isinstance(row["envelope_id"], str) or not _EID_RE.match(row["envelope_id"]):
        _reject(INDEX_CORRUPT, "envelope_id is not sha256:<64 lowercase hex>")
    _parse_utc(row["received_at"], code=INDEX_CORRUPT)
    _parse_utc(row["created"], code=INDEX_CORRUPT)
    for key in ("from", "to"):
        if not isinstance(row[key], str) or not _SEAT_RE.match(row[key]):
            _reject(INDEX_CORRUPT, f"{key} is not a seat token")
    for key in ("from_kid", "to_kid"):
        if not isinstance(row[key], str) or not _EID_RE.match(row[key]):
            _reject(INDEX_CORRUPT, f"{key} is not sha256:<64 lowercase hex>")
    if row["kind"] not in envelope.KINDS:
        _reject(INDEX_CORRUPT, "kind is outside the closed SENV2 kind set")
    if not isinstance(row["topic"], str) or not _TOPIC_RE.match(row["topic"]):
        _reject(INDEX_CORRUPT, "topic is not a topic token")
    ref = row.get("ref")
    if ref is not None and (not isinstance(ref, str) or not _EID_RE.match(ref)):
        _reject(INDEX_CORRUPT, "ref is not sha256:<64 lowercase hex>")
    return row


def _read_index_file(path: Path) -> Tuple[dict, ...]:
    """Every canonical index row, fail-closed on the first malformed one.

    Uniqueness is part of the contract: exactly one row per `ENVELOPE_ID`, so
    a repeated id — identical bytes or not — is corruption, never silently
    deduplicated evidence (`INDEX_DUPLICATE_ENVELOPE_ID`).
    """
    if not path.exists():
        return ()
    data = path.read_bytes()
    if not data:
        return ()
    if not data.endswith(b"\n"):
        _reject(INDEX_CORRUPT, "index.jsonl is not newline terminated")
    rows = []
    seen = set()
    for number, raw in enumerate(data.split(b"\n")[:-1], start=1):
        if not raw:
            _reject(INDEX_CORRUPT, f"index.jsonl line {number} is empty")
        row = _parse_index_line(raw)
        if row["envelope_id"] in seen:
            _reject(INDEX_DUPLICATE_ENVELOPE_ID,
                    f"index.jsonl line {number} repeats ENVELOPE_ID "
                    f"{row['envelope_id']}; the contract is exactly one row per envelope")
        seen.add(row["envelope_id"])
        rows.append(row)
    return tuple(rows)


def _checked_cursor_offset(path: Path, offset: int) -> int:
    """Refuse a cursor that is not a real position in this index file.

    Nonsense is rejected mechanically: a negative or non-integer offset, an
    offset past EOF, and an offset that is not a line boundary (seeking there
    would land inside a UTF-8/JSON row).
    """
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        _reject(BAD_CURSOR, "a cursor offset is a non-negative integer")
    if not path.exists():
        if offset != 0:
            _reject(BAD_CURSOR, "a cursor offset past the end of a missing index is refused")
        return 0
    size = path.stat().st_size
    if offset > size:
        _reject(BAD_CURSOR, "a cursor offset past the end of the index is refused")
    if offset > 0:
        with path.open("rb") as handle:
            handle.seek(offset - 1)
            if handle.read(1) != b"\n":
                _reject(BAD_CURSOR,
                        "a cursor offset that is not a line boundary is refused")
    return offset


def _stream_index_rows(path: Path, *, start_offset: int, max_rows: int) -> Tuple[Tuple[dict, ...], int, bool]:
    """Read at most `max_rows` validated rows from `start_offset`, sequentially.

    This is the real work bound of D-037: rows beyond the budget are never
    parsed, and continuation is a byte offset, so a later call resumes without
    re-reading the prefix. `exhausted` is a byte-size fact (`next_offset <
    file size`) — determining it never parses the remaining rows.
    """
    if not path.exists():
        return (), 0, False
    size = path.stat().st_size
    if start_offset > size:
        _reject(BAD_CURSOR, "a cursor offset past the end of the index is refused")
    rows = []
    offset = start_offset
    if start_offset < size:
        with path.open("rb") as handle:
            handle.seek(start_offset)
            while len(rows) < max_rows:
                raw = handle.readline(MAX_INDEX_LINE_BYTES + 2)
                if not raw:
                    break
                if not raw.endswith(b"\n"):
                    if len(raw) > MAX_INDEX_LINE_BYTES:
                        _reject(INDEX_CORRUPT, "an index line exceeds the declared bound")
                    _reject(INDEX_CORRUPT, "index.jsonl is not newline terminated")
                content = raw[:-1]
                if not content:
                    _reject(INDEX_CORRUPT, "an index line is empty")
                rows.append(_parse_index_line(content))
                offset += len(raw)
    return tuple(rows), offset, offset < size


# --------------------------------------------------------------------------
# immutable publication (staging + atomic no-overwrite rename)
# --------------------------------------------------------------------------


def _existing_bundle_status(target: Path, senv_bytes: bytes) -> str:
    try:
        winner = (target / CONTAINER_NAME).read_bytes()
    except OSError as exc:
        _reject(ENVELOPE_ID_CONFLICT,
                f"bundle {target.name} exists and cannot be read back "
                f"({type(exc).__name__}); a committed bundle is never replaced")
    if winner == senv_bytes:
        return IDEMPOTENT
    _reject(ENVELOPE_ID_CONFLICT,
            f"bundle {target.name} already holds different bytes; a committed "
            "transport object is never overwritten")


def _publish_dir(parent: Path, name: str, files: Mapping[str, bytes],
                 *, conflict_code: str, identity_name: str = CONTAINER_NAME) -> str:
    """Publish one complete directory in one atomic no-overwrite step.

    The staged directory is fully written and fsynced before the rename, so the
    name only ever appears with complete bytes behind it. An existing committed
    directory is never replaced: identical identity bytes converge
    idempotently, any difference is the caller's named conflict. The winner's
    other files stay untouched — a duplicate delivery keeps the original
    receiver receipt (and therefore the original `RECEIVED_AT`).
    """
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / name
    if target.exists():
        return _existing_dir_status(target, files, conflict_code, identity_name)
    staged = parent / f".{name}.{uuid.uuid4().hex}.staging"
    try:
        staged.mkdir()
        for file_name, data in files.items():
            _write_complete(staged / file_name, data)
        _fsync_directory(staged)
        try:
            os.rename(staged, target)
        except OSError:
            if target.exists():
                return _existing_dir_status(target, files, conflict_code, identity_name)
            raise
        _fsync_directory(parent)
        return PUBLISHED
    finally:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)


def _existing_dir_status(target: Path, files: Mapping[str, bytes], conflict_code: str,
                         identity_name: str) -> str:
    if identity_name not in files:
        _reject(conflict_code, f"{target.name} has no {identity_name} to compare")
    try:
        winner = (target / identity_name).read_bytes()
    except OSError as exc:
        _reject(conflict_code,
                f"{target.name}/{identity_name} exists and cannot be read back "
                f"({type(exc).__name__})")
    if winner != files[identity_name]:
        _reject(conflict_code,
                f"{target.name}/{identity_name} already holds different bytes; a "
                "committed object is never overwritten")
    return IDEMPOTENT


def _receipt_bytes(envelope_id: str, received_at: str) -> bytes:
    return _canonical_json_line({"schema": SCHEMA_VERSION, "envelope_id": envelope_id,
                                 "received_at": received_at})


def _read_receipt(bundle: Path) -> Tuple[str, str]:
    try:
        raw = (bundle / RECEIPT_NAME).read_bytes()
    except OSError as exc:
        _reject(RECEIPT_CORRUPT,
                f"bundle {bundle.name} has no readable receipt ({type(exc).__name__})")
    try:
        receipt = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_guard)
    except SailangError:
        raise
    except (UnicodeDecodeError, ValueError):
        _reject(RECEIPT_CORRUPT, f"bundle {bundle.name} receipt is not canonical JSON")
    if set(receipt) != {"schema", "envelope_id", "received_at"}:
        _reject(RECEIPT_CORRUPT, f"bundle {bundle.name} receipt has unexpected keys")
    if receipt["schema"] != SCHEMA_VERSION:
        _reject(RECEIPT_CORRUPT, f"bundle {bundle.name} receipt schema is unknown")
    _parse_utc(receipt["received_at"], code=RECEIPT_CORRUPT)
    if not isinstance(receipt["envelope_id"], str) or not _EID_RE.match(receipt["envelope_id"]):
        _reject(RECEIPT_CORRUPT, f"bundle {bundle.name} receipt envelope_id is malformed")
    return receipt["envelope_id"], receipt["received_at"]


# --------------------------------------------------------------------------
# TTL policy and expiry tombstones (D-038)
# --------------------------------------------------------------------------


def parse_ttl_seconds(value: str) -> int:
    """Seconds in one SENV2 `TTL:<nD|nH>` value, or a named refusal.

    The wire syntax is unchanged (D-038); this only decodes the already-validated
    token. Zero is legal (`0H`/`0D`) and makes an object eligible on the first
    explicit sweep at or after `RECEIVED_AT`.
    """
    if not isinstance(value, str) or not envelope._TTL_RE.match(value):
        _reject(BAD_TTL_POLICY, f"TTL {value!r} is not a count followed by D or H")
    number = int(value[:-1])
    return number * (24 * 60 * 60 if value[-1] == "D" else 60 * 60)


def validate_receiver_default(seconds) -> int:
    """A receiver TTL policy must sit in the declared v0 range (D-038).

    An out-of-range policy is refused, never silently clamped: `7 days <=
    default_ttl <= 30 days`. A non-integer, bool or negative value is refused
    for the same reason — it is not a policy the protocol defines.
    """
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0:
        _reject(BAD_TTL_POLICY, "a receiver default_ttl is a non-negative integer count of seconds")
    if not (MIN_TTL_SECONDS <= seconds <= MAX_TTL_SECONDS):
        _reject(RECEIVER_TTL_OUT_OF_RANGE,
                f"receiver default_ttl {seconds}s is outside the allowed v0 range "
                f"{MIN_TTL_SECONDS}s..{MAX_TTL_SECONDS}s (7..30 days)")
    return seconds


def effective_ttl_seconds(header: Header, receiver_default: int) -> int:
    """`min(sender_ttl_if_present, receiver_default)` — the ceiling rule (D-038).

    The sender may request SHORTER retention; it may never force longer. An
    absent header TTL leaves the receiver default intact.
    """
    validate_receiver_default(receiver_default)
    declared = header.get("TTL")
    if declared is None:
        return receiver_default
    return min(parse_ttl_seconds(declared), receiver_default)


def _expires_at(received_at: str, ttl_seconds: int) -> datetime:
    return _parse_utc(received_at, code=RECEIPT_CORRUPT) + timedelta(seconds=ttl_seconds)


def _tombstone_bytes(tombstone: Mapping) -> bytes:
    return _canonical_json_line(tombstone)


def _read_tombstone(path: Path) -> dict:
    """One immutable expired tombstone, fully self-proving (D-038, T-49/A).

    File existence is never expiry authority (`REFERENCE_EXISTS !=
    REFERENCE_SUPPORTS_CLAIM`). A tombstone proves the exact transport object it
    represents only when ALL of these hold, or it is a named refusal:

    * the file name is `<digest>.json` and its digest is the digest half of the
      tombstone's own `envelope_id` — the path and the JSON must agree, so a
      valid tombstone parked under another object's name is refused (A2);
    * the bytes are exactly the canonical serialization of the parsed object, so
      one immutable evidence object has exactly one accepted representation (A5);
    * the schema is closed (no missing/unknown/duplicate keys) and every field
      is well-formed.

    The result is a structurally trustworthy tombstone; binding it to a specific
    index row and live header is the caller's job (`_tombstone_binds_index`).
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        _reject(EXPIRED_TOMBSTONE_CORRUPT,
                f"tombstone {path.name} cannot be read ({type(exc).__name__})")
    if not path.name.endswith(".json") or not _HEX64_RE.match(path.name[:-5]):
        _reject(EXPIRED_TOMBSTONE_CORRUPT,
                f"expired/ entry {path.name!r} is not a <digest>.json tombstone")
    try:
        tombstone = json.loads(raw.decode("utf-8"), object_pairs_hook=_duplicate_guard)
    except SailangError:
        raise
    except (UnicodeDecodeError, ValueError):
        _reject(EXPIRED_TOMBSTONE_CORRUPT, f"tombstone {path.name} is not canonical JSON")
    if not isinstance(tombstone, dict) or set(tombstone) != _TOMBSTONE_KEYS:
        _reject(EXPIRED_TOMBSTONE_CORRUPT,
                f"tombstone {path.name} keys deviate from the D-038 schema")
    if raw != _tombstone_bytes(tombstone):
        _reject(EXPIRED_TOMBSTONE_CORRUPT,
                f"tombstone {path.name} is not the canonical serialization of its object")
    if tombstone["schema"] != _TOMBSTONE_SCHEMA:
        _reject(EXPIRED_TOMBSTONE_CORRUPT, f"tombstone {path.name} schema is unknown")
    if not isinstance(tombstone["envelope_id"], str) or not _EID_RE.match(tombstone["envelope_id"]):
        _reject(EXPIRED_TOMBSTONE_CORRUPT, f"tombstone {path.name} envelope_id is malformed")
    if tombstone["envelope_id"] != envelope.HASH_PREFIX + path.name[:-5]:
        _reject(EXPIRED_TOMBSTONE_CORRUPT,
                f"tombstone {path.name} does not name the envelope its own file name "
                "identifies; path and object must agree")
    for key in ("sender", "recipient"):
        if not isinstance(tombstone[key], str) or not _SEAT_RE.match(tombstone[key]):
            _reject(EXPIRED_TOMBSTONE_CORRUPT, f"tombstone {path.name} {key} is not a seat token")
    if tombstone["kind"] not in envelope.KINDS:
        _reject(EXPIRED_TOMBSTONE_CORRUPT, f"tombstone {path.name} kind is outside the closed set")
    _parse_utc(tombstone["received_at"], code=EXPIRED_TOMBSTONE_CORRUPT)
    _parse_utc(tombstone["expired_at"], code=EXPIRED_TOMBSTONE_CORRUPT)
    ttl = tombstone["effective_ttl_seconds"]
    if isinstance(ttl, bool) or not isinstance(ttl, int) or ttl < 0:
        _reject(EXPIRED_TOMBSTONE_CORRUPT, f"tombstone {path.name} effective_ttl_seconds is invalid")
    if tombstone["reason"] != TTL_EXPIRED:
        _reject(EXPIRED_TOMBSTONE_CORRUPT, f"tombstone {path.name} reason is not {TTL_EXPIRED}")
    return tombstone


def _tombstone_binds_index(tombstone: Mapping, row: Mapping) -> bool:
    """The tombstone's own claims must agree with the canonical index row (A3).

    The tombstone intentionally omits topic/key ids/created/ref, so only the
    fields it DOES claim are compared — the row is never asked to reproduce a
    field the evidence object never carried.
    """
    return (
        tombstone["envelope_id"] == row["envelope_id"]
        and tombstone["sender"] == row["from"]
        and tombstone["recipient"] == row["to"]
        and tombstone["kind"] == row["kind"]
        and tombstone["received_at"] == row["received_at"]
        and tombstone["reason"] == TTL_EXPIRED
    )


def _tombstone_binds_header(tombstone: Mapping, header: Header) -> bool:
    """Overlapping live-header claims must agree with the tombstone (A4)."""
    return (
        tombstone["sender"] == header.get("FROM")
        and tombstone["recipient"] == header.get("TO")
        and tombstone["kind"] == header.get("K")
    )



# --------------------------------------------------------------------------
# the Post Office
# --------------------------------------------------------------------------


class PostOffice:
    """One receiver-side mailbox root: delivery, index, recovery.

    The root is caller-supplied; `mail/` and its reserved subdirectories are
    created under it. Registries are receiver-owned (envelope D-028/D-030) and
    are consulted, never modified, by any operation here.
    """

    def __init__(self, root, *, seat: str, sender_registry,
                 recipient_registry, interest: "HeaderInterest" = None,
                 clock: Callable[[], str] = utc_now,
                 default_ttl: int = DEFAULT_TTL_SECONDS):
        if not isinstance(seat, str) or not _SEAT_RE.match(seat):
            _reject("BAD_SEAT", "a seat is one token of letters, digits, dot, dash or underscore")
        if not isinstance(sender_registry, envelope.KeyRegistry):
            _reject("NOT_A_REGISTRY", "delivery verifies against the receiver's own KeyRegistry")
        if not isinstance(recipient_registry, envelope.RecipientKeyRegistry):
            _reject("NOT_A_RECIPIENT_REGISTRY",
                    "delivery checks against the receiver's own RecipientKeyRegistry")
        if interest is not None and not isinstance(interest, HeaderInterest):
            _reject("NOT_A_HEADER_INTEREST",
                    "the header policy is a receiver-owned HeaderInterest")
        self.default_ttl = validate_receiver_default(default_ttl)
        self.root = Path(root)
        self.seat = seat
        self.sender_registry = sender_registry
        self.recipient_registry = recipient_registry
        self.interest = interest if interest is not None else HeaderInterest()
        self.clock = clock
        self.mail_root = self.root / MAIL_DIR
        (self.mail_root / INBOX / seat).mkdir(parents=True, exist_ok=True)
        (self.mail_root / READ / seat).mkdir(parents=True, exist_ok=True)
        (self.mail_root / QUARANTINE).mkdir(parents=True, exist_ok=True)
        (self.mail_root / EXPIRED / seat).mkdir(parents=True, exist_ok=True)
        (self.mail_root / PROMOTED).mkdir(parents=True, exist_ok=True)

    # ---- paths -----------------------------------------------------------

    def inbox_bundle(self, envelope_id: str) -> Path:
        return self.mail_root / INBOX / self.seat / _bundle_name(envelope_id)

    def read_bundle(self, envelope_id: str) -> Path:
        return self.mail_root / READ / self.seat / _bundle_name(envelope_id)

    def expired_tombstone(self, envelope_id: str) -> Path:
        return self.mail_root / EXPIRED / self.seat / (_bundle_name(envelope_id) + ".json")

    def _lifecycle_lock(self) -> "_LifecycleLock":
        """The one destructive-lifecycle lock (D-038): LIFECYCLE then INDEX."""
        return _LifecycleLock(self.mail_root / LIFECYCLE_LOCK_NAME)

    # ---- index -----------------------------------------------------------

    def read_index(self) -> Tuple[dict, ...]:
        """Every canonical index row, fail-closed on the first malformed one."""
        return _read_index_file(self.mail_root / INDEX_NAME)

    def read_index_row(self, envelope_id: str) -> Optional[dict]:
        """The exactly-one index row for `envelope_id`, or None.

        A duplicate row fails closed through `read_index`; uniqueness is part
        of the contract, so "the row" is well-defined whenever it exists.
        """
        for row in self.read_index():
            if row["envelope_id"] == envelope_id:
                return row
        return None

    def has_index_row(self, envelope_id: str) -> bool:
        return any(row["envelope_id"] == envelope_id for row in self.read_index())

    def ensure_index_row(self, header: Header, envelope_id: str,
                         received_at: str) -> bool:
        """Append the one active row for `envelope_id` if it is missing.

        Runs under the OS mailbox lock and re-reads the index inside the lock.
        An existing row is not merely noticed: it must be exactly the row
        implied by the verified header and the original `RECEIVED_AT`, or the
        append-only evidence conflicts and this fails closed
        (`INDEX_ROW_CONFLICT`). A matching row is idempotent and never
        duplicated or rewritten.
        """
        expected = _index_row(header, envelope_id, received_at)
        line = _row_line_bytes(expected)
        with _MailboxLock(self.mail_root / "index.lock"):
            existing = self.read_index()
            for row in existing:
                if row["envelope_id"] != envelope_id:
                    continue
                if row != expected:
                    _reject(INDEX_ROW_CONFLICT,
                            f"index already carries a different row for {envelope_id}; "
                            "append-only evidence is never rewritten")
                return False
            path = self.mail_root / INDEX_NAME
            with path.open("ab") as handle:
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(path.parent)
            return True

    # ---- delivery --------------------------------------------------------

    def deliver(self, data) -> DeliveryResult:
        """Verify one raw SENV2 object and durably deliver it, or quarantine it.

        No payload is decrypted and no recipient private key is required. A
        bounded object that fails parse, sender authentication, recipient
        addressing or recipient-key acceptance is quarantined under a raw-bytes
        hash that is never an `ENVELOPE_ID`. An object over the container's
        hard bound is refused without persisting the hostile body.

        Deduplication covers the whole active lifecycle (D-031): an exact
        replay of an object already in `read/` returns the original
        `RECEIVED_AT`, creates no inbox bundle and unpacks no unread state; a
        stored read object that does not mechanically match fails closed and
        is never overwritten.
        """
        if isinstance(data, str):
            raw = data.encode("utf-8")
        elif isinstance(data, (bytes, bytearray)):
            raw = bytes(data)
        else:
            _reject("NON_TEXT_INPUT", "a container is text or UTF-8 bytes")
        if len(raw) > envelope.MAX_CONTAINER_BYTES:
            return DeliveryResult(status=REFUSED, reason=CONTAINER_OVERSIZE)

        try:
            header = envelope.parse_header(raw)
        except SailangError as exc:
            return self._quarantine(raw, exc.code)
        try:
            envelope.verify(header, self.sender_registry)
        except SailangError as exc:
            return self._quarantine(raw, exc.code)
        if header.get("TO") != self.seat:
            return self._quarantine(raw, WRONG_RECIPIENT_SEAT)
        if not self.recipient_registry.accepted(self.seat):
            return self._quarantine(raw, UNKNOWN_RECIPIENT_SEAT)
        if self.recipient_registry.resolves(self.seat, header.get("TO_KID")) is None:
            return self._quarantine(raw, RECIPIENT_KEY_NOT_ACCEPTED)

        envelope_id = envelope.envelope_id(raw)
        with self._lifecycle_lock():
            expired_at = self._expired_dedup(header, envelope_id)
            if expired_at is not None:
                return DeliveryResult(status=DUPLICATE, envelope_id=envelope_id,
                                      received_at=expired_at)
            read = self.read_bundle(envelope_id)
            if read.is_dir():
                stored_at = self._replay_read_object(read, raw, envelope_id)
                self.ensure_index_row(header, envelope_id, stored_at)
                return DeliveryResult(status=DUPLICATE, envelope_id=envelope_id,
                                      received_at=stored_at)
            received_at = self.clock()
            parent = self.mail_root / INBOX / self.seat
            status = _publish_dir(parent, _bundle_name(envelope_id),
                                  {CONTAINER_NAME: raw,
                                   RECEIPT_NAME: _receipt_bytes(envelope_id, received_at)},
                                  conflict_code=ENVELOPE_ID_CONFLICT)
            if status == IDEMPOTENT:
                stored_id, stored_at = _read_receipt(parent / _bundle_name(envelope_id))
                if stored_id != envelope_id:
                    _reject(RECEIPT_CORRUPT,
                            "the stored bundle's receipt names a different envelope")
                self.ensure_index_row(header, envelope_id, stored_at)
                return DeliveryResult(status=DUPLICATE, envelope_id=envelope_id,
                                      received_at=stored_at)
            self.ensure_index_row(header, envelope_id, received_at)
            return DeliveryResult(status=ACCEPTED, envelope_id=envelope_id,
                                  received_at=received_at)

    def _expired_dedup(self, header: Header, envelope_id: str) -> Optional[str]:
        """Expired-lifecycle dedup for `deliver` (D-038, C3/C6).

        An exact redelivery of an expired `ENVELOPE_ID` must NOT resurrect the
        message. A valid tombstone is proven against exactly one consistent
        index row, the incoming verified header and the receiver identity, and
        the delivery becomes a `DUPLICATE` returning the ORIGINAL `RECEIVED_AT`
        — no body, no row, no tombstone change. No tombstone means no expired
        claim; a corrupt or conflicting tombstone fails closed and is never
        overwritten. The caller holds the lifecycle lock.
        """
        tombstone_path = self.expired_tombstone(envelope_id)
        if not tombstone_path.exists():
            return None
        tombstone = _read_tombstone(tombstone_path)
        # The tombstone must describe THIS receiver seat, and its path already
        # proved it names this exact ENVELOPE_ID (T-49/A2).
        if tombstone["recipient"] != self.seat:
            _reject(EXPIRED_TOMBSTONE_CONFLICT,
                    f"tombstone {tombstone_path.name} names another recipient seat")
        row = self.read_index_row(envelope_id)
        if row is None:
            _reject(EXPIRED_TOMBSTONE_CONFLICT,
                    f"tombstone for {envelope_id} exists but the index carries no row")
        # A3: the tombstone's own claims must bind the persisted index identity.
        if not _tombstone_binds_index(tombstone, row):
            _reject(EXPIRED_TOMBSTONE_CONFLICT,
                    f"tombstone for {envelope_id} disagrees with its index row; "
                    "refusing the redelivery")
        # A4: and the incoming verified header must agree with every overlapping
        # field the tombstone claims, and the receiver's original RECEIVED_AT
        # must match. A tombstone for another logical object never suppresses
        # delivery merely because it was placed under this object's filename.
        if not _tombstone_binds_header(tombstone, header):
            _reject(EXPIRED_TOMBSTONE_CONFLICT,
                    f"incoming envelope {envelope_id} disagrees with the tombstone "
                    "under its name; refusing the redelivery")
        if _index_row(header, envelope_id, tombstone["received_at"]) != row:
            _reject(EXPIRED_TOMBSTONE_CONFLICT,
                    f"index row for {envelope_id} disagrees with the incoming header; "
                    "refusing the redelivery")
        return tombstone["received_at"]

    def _replay_read_object(self, read: Path, raw: bytes, envelope_id: str) -> str:
        """Prove a replay matches the stored read object; return original RECEIVED_AT.

        Identity is established mechanically, never by directory name alone:
        the receipt must name this `ENVELOPE_ID`, the stored container bytes
        must hash to it and must equal the delivered bytes exactly. Anything
        else fails closed and the committed read object is left untouched.
        """
        stored_id, stored_at = _read_receipt(read)
        if stored_id != envelope_id:
            _reject(READ_BUNDLE_CONFLICT,
                    f"read bundle {read.name} receipt names a different envelope")
        try:
            stored = (read / CONTAINER_NAME).read_bytes()
        except OSError as exc:
            _reject(READ_BUNDLE_CONFLICT,
                    f"read bundle {read.name} cannot be read back ({type(exc).__name__})")
        if envelope.envelope_id(stored) != envelope_id:
            _reject(READ_BUNDLE_CONFLICT,
                    f"read bundle {read.name} does not hash to its ENVELOPE_ID; "
                    "refusing the replay")
        if stored != raw:
            _reject(READ_BUNDLE_CONFLICT,
                    f"read bundle {read.name} holds different bytes; refusing the replay")
        return stored_at

    def _quarantine(self, raw: bytes, reason: str) -> DeliveryResult:
        digest = hashlib.sha256(QUARANTINE_DOMAIN + raw).hexdigest()
        quarantine_id = envelope.HASH_PREFIX + digest
        reason_bytes = _canonical_json_line(
            {"schema": SCHEMA_VERSION, "reason": reason, "object_sha256": quarantine_id})
        if len(reason_bytes) > MAX_REASON_LINE_BYTES:
            _reject("REASON_OVERSIZE", "quarantine reason line exceeds the declared bound")
        _publish_dir(self.mail_root / QUARANTINE, digest,
                     {OBJECT_NAME: raw, REASON_NAME: reason_bytes},
                     conflict_code="QUARANTINE_CONFLICT", identity_name=OBJECT_NAME)
        return DeliveryResult(status=QUARANTINED, quarantine_id=quarantine_id,
                              reason=reason)

    # ---- recovery --------------------------------------------------------

    def recover(self) -> RecoveryResult:
        """Maintenance: reconcile crash copies and re-derive missing index rows.

        Two jobs, both mechanical. First, for every `ENVELOPE_ID` present in
        both `inbox/` and `read/` (the crash window the read transition leaves
        open), identity is proven from content — same receipt, equal container
        bytes, bytes hash to the `ENVELOPE_ID`; identical copies resolve to
        read state and the redundant inbox copy is removed, a conflicting pair
        fails closed. Then every committed bundle is re-verified against the
        receiver's registries and its missing index row is appended exactly
        once — the other crash window the commit order leaves open. This is not
        the normal agent scan path.

        It also finishes the one normal destructive-expiry crash window
        (D-038, C4): a published tombstone whose live body was not yet deleted.
        The pair is proven to describe the same `ENVELOPE_ID` and the same
        original receipt before the redundant body is removed; a conflicting
        pair is `EXPIRY_STATE_CONFLICT` and nothing is guessed.
        """
        with self._lifecycle_lock():
            inbox_bundles = self._state_bundles(INBOX)
            read_bundles = self._state_bundles(READ)
            scanned = 0
            appended = 0
            for name in sorted(set(inbox_bundles) | set(read_bundles)):
                envelope_id = envelope.HASH_PREFIX + name
                inbox = inbox_bundles.get(name)
                read = read_bundles.get(name)
                if self._finish_expiry(name, inbox, read, envelope_id):
                    scanned += 1
                    continue
                pair = inbox is not None and read is not None
                if pair:
                    self._check_reconcilable(inbox, read, envelope_id)
                    bundle = read
                else:
                    bundle = inbox if inbox is not None else read
                header, stored_at = self._verify_bundle(bundle, envelope_id)
                if pair:
                    shutil.rmtree(inbox)
                    _fsync_directory(inbox.parent)
                scanned += 1
                if self.ensure_index_row(header, envelope_id, stored_at):
                    appended += 1
            return RecoveryResult(bundles_scanned=scanned, rows_appended=appended)

    def _finish_expiry(self, name: str, inbox: Optional[Path], read: Optional[Path],
                       envelope_id: str) -> bool:
        """Close the tombstone-before-delete crash window in ONE pass (D-038, T-49/B).

        Returns True when an expiry was handled (all live bodies finished off)
        and the ordinary recovery path must be skipped. A tombstone with no live
        body is a settled, idempotent expiry and also returns True. Without a
        tombstone this returns False — an ordinary bundle is not expiry work.

        The live evidence is checked BEFORE any deletion: the tombstone must be
        valid, canonical and path/object-bound (A1/A2/A5); its claims must bind
        the index row (A3) and the verified live header (A4); and while the body
        still exists the tombstone must be one that could legitimately have been
        created for it — `effective_ttl_seconds` equals the policy implied by the
        signed live header and this mailbox's current default, and `expired_at`
        is no earlier than eligibility (B3). A pair that fails any check is a
        named conflict and nothing is deleted. Identical inbox+read copies are
        proven equal, then BOTH are removed, so one successful call leaves only
        the tombstone.
        """
        tombstone_path = self.expired_tombstone(envelope_id)
        if not tombstone_path.exists():
            return False
        tombstone = _read_tombstone(tombstone_path)
        if tombstone["recipient"] != self.seat:
            _reject(EXPIRY_STATE_CONFLICT,
                    f"tombstone {tombstone_path.name} names another recipient seat")
        row = self.read_index_row(envelope_id)
        if row is None:
            _reject(EXPIRY_STATE_CONFLICT,
                    f"tombstone for {envelope_id} exists but the index carries no row")
        if not _tombstone_binds_index(tombstone, row):
            _reject(EXPIRY_STATE_CONFLICT,
                    f"tombstone for {envelope_id} disagrees with its index row")
        if inbox is None and read is None:
            return True  # settled: tombstone present, no live body — idempotent
        if inbox is not None and read is not None:
            self._check_reconcilable(inbox, read, envelope_id)
        bundle = read if read is not None else inbox
        header, stored_at = self._verify_bundle(bundle, envelope_id)
        if (stored_at != tombstone["received_at"]
                or not _tombstone_binds_header(tombstone, header)):
            _reject(EXPIRY_STATE_CONFLICT,
                    f"live bundle for {envelope_id} does not match its tombstone; "
                    "refusing to finish the expiry")
        # B3: the tombstone must be one this live body could have produced.
        expected_ttl = effective_ttl_seconds(header, self.default_ttl)
        if tombstone["effective_ttl_seconds"] != expected_ttl:
            _reject(EXPIRY_STATE_CONFLICT,
                    f"tombstone for {envelope_id} records a different effective TTL "
                    "than the signed live header implies; refusing premature deletion")
        if _parse_utc(tombstone["expired_at"], code=EXPIRY_STATE_CONFLICT) < \
                _expires_at(stored_at, expected_ttl):
            _reject(EXPIRY_STATE_CONFLICT,
                    f"tombstone for {envelope_id} is dated before eligibility; "
                    "refusing premature deletion")
        for path in (inbox, read):
            if path is not None:
                shutil.rmtree(path)
                _fsync_directory(path.parent)
        return True


    def _state_bundles(self, state: str) -> dict:
        """This seat's bundle directories in one state dir, keyed by digest."""
        base = self.mail_root / state / self.seat
        bundles = {}
        if not base.is_dir():
            return bundles
        for bundle in sorted(base.iterdir()):
            if not bundle.is_dir() or bundle.name.startswith("."):
                continue
            if not _HEX64_RE.match(bundle.name):
                _reject(BUNDLE_INVALID,
                        f"{state}/{self.seat} holds a directory {bundle.name!r} that "
                        "is not an ENVELOPE_ID bundle")
            bundles[bundle.name] = bundle
        return bundles

    def _verify_bundle(self, bundle: Path, envelope_id: str) -> Tuple[Header, str]:
        """Re-verify one committed bundle against the receiver's registries.

        Returns the parsed header and the bundle receipt's original
        `RECEIVED_AT`; raises the named integrity refusal on any deviation.
        """
        raw = self._read_bundle_container(bundle)
        try:
            header = envelope.parse_header(raw)
            envelope.verify(header, self.sender_registry)
        except SailangError as exc:
            _reject(BUNDLE_INVALID,
                    f"bundle {bundle.name} does not re-verify: {exc.code}")
        if header.get("TO") != self.seat:
            _reject(BUNDLE_INVALID,
                    f"bundle {bundle.name} is addressed to another seat")
        if self.recipient_registry.resolves(self.seat, header.get("TO_KID")) is None:
            _reject(BUNDLE_INVALID,
                    f"bundle {bundle.name} names a recipient key this seat does not accept")
        if envelope.envelope_id(raw) != envelope_id:
            _reject(BUNDLE_INVALID,
                    f"bundle {bundle.name} does not hash to its directory name")
        stored_id, stored_at = _read_receipt(bundle)
        if stored_id != envelope_id:
            _reject(RECEIPT_CORRUPT,
                    f"bundle {bundle.name} receipt names a different envelope")
        return header, stored_at

    def _read_bundle_container(self, bundle: Path) -> bytes:
        try:
            return (bundle / CONTAINER_NAME).read_bytes()
        except OSError as exc:
            _reject(BUNDLE_INVALID,
                    f"bundle {bundle.name} has no readable container ({type(exc).__name__})")

    # ---- current transport state ----------------------------------------

    def bundle_state(self, envelope_id: str, *, row: Optional[dict] = None) -> str:
        """UNREAD / READ / BOTH / EXPIRED / NEITHER, from filesystem state.

        Directory existence plus a VALID expiry tombstone — no `.senv` bytes.
        File existence alone is never expiry authority (T-49/A): a tombstone
        that is not structurally sound, canonical, or file-name-bound to its own
        `envelope_id` refuses `EXPIRED_TOMBSTONE_CORRUPT` rather than passing as
        intentional expiry. BOTH is an observed crash-window state, not a
        resolution: a byte length is not an identity, and proving pair identity
        needs `.senv` bytes, which header-only callers never read. Scan refuses
        BOTH with `RECONCILIATION_REQUIRED` and refuses the abnormal
        tombstone+body pair with `EXPIRY_RECONCILIATION_REQUIRED`; `recover()`
        is maintenance and proves byte identity before resolving either.

        `row` is the canonical index row when the caller already holds it (the
        header-only scan). It is used only to bind a present tombstone to that
        row (T-49/A3); when omitted and a tombstone exists, the row is read once.
        """
        if not self.expired_tombstone(envelope_id).exists():
            return self._body_state(envelope_id)
        if row is None:
            row = self.read_index_row(envelope_id)
        return self.expiry_state(envelope_id, row=row)

    def _body_state(self, envelope_id: str) -> str:
        inbox = self.inbox_bundle(envelope_id).is_dir()
        read = self.read_bundle(envelope_id).is_dir()
        if inbox and read:
            return BOTH
        if read:
            return READ_STATE
        if inbox:
            return UNREAD
        return NEITHER

    def expiry_state(self, envelope_id: str, *, row: Optional[dict]) -> str:
        """This object's state when a tombstone exists, or NEITHER if none.

        Validates the tombstone before it can assert anything (T-49/A1/A2/A5)
        and requires the tombstone's own claims to bind the canonical index row
        (T-49/A3). A structurally valid tombstone under the wrong file name, a
        non-canonical encoding, a tombstone with no index row, or one that
        disagrees with its row is a named refusal — never `EXPIRED`, and never a
        silent masking of `INDEX_BODY_MISSING`.
        """
        path = self.expired_tombstone(envelope_id)
        if not path.exists():
            return NEITHER
        tombstone = _read_tombstone(path)
        if row is None:
            _reject(EXPIRED_TOMBSTONE_CONFLICT,
                    f"tombstone for {envelope_id} exists but the index carries no row")
        if not _tombstone_binds_index(tombstone, row):
            _reject(EXPIRED_TOMBSTONE_CONFLICT,
                    f"tombstone for {envelope_id} disagrees with its index row")
        live = self._body_state(envelope_id)
        if live == NEITHER:
            return EXPIRED_STATE
        return EXPIRY_RECONCILIATION_REQUIRED

    # ---- explicit TTL sweep (D-038) -------------------------------------

    def sweep_expired(self, *, now=None) -> SweepResult:
        """Explicit maintenance: expire eligible accepted bodies (D-038).

        This is the ONLY TTL entry point. It never runs inside `deliver`,
        `scan`, `open_message` or `recover`, and there is no daemon, timer,
        scheduler or network worker — the caller decides when maintenance runs,
        which keeps sweep deterministic and testable.

        For each live bundle in `inbox/<seat>/` and `read/<seat>/`, the object
        is mechanically re-verified (parse, sender signature, recipient seat and
        key, bytes hash to the `ENVELOPE_ID`, one consistent index row whose
        `RECEIVED_AT` equals the receipt's) before any destructive effect. TTL
        eligibility uses the receiver-local clock: `expires_at = RECEIVED_AT +
        min(sender_ttl_if_present, default_ttl)`. An eligible body gets an
        immutable tombstone published BEFORE deletion; a body not yet old
        enough is retained; a valid tombstone with no live body is idempotent.
        Filesystem mtime/ctime are never TTL authority and a corrupt or
        conflicting object fails closed without deletion.
        """
        instant = _as_instant(now if now is not None else self.clock())
        with self._lifecycle_lock():
            inbox_bundles = self._state_bundles(INBOX)
            read_bundles = self._state_bundles(READ)
            examined = expired = retained = already = 0
            names = set(inbox_bundles) | set(read_bundles)
            # Settled tombstones (no live body) are already_expired and idempotent.
            for name in sorted(self._tombstone_names() - names):
                self._read_tombstone_for(name)
                examined += 1
                already += 1
            for name in sorted(names):
                envelope_id = envelope.HASH_PREFIX + name
                read = read_bundles.get(name)
                inbox = inbox_bundles.get(name)
                if self.expired_tombstone(envelope_id).exists():
                    # A tombstone beside a live body is the C4 crash window;
                    # finish it rather than expire it twice.
                    self._finish_expiry(name, inbox, read, envelope_id)
                    examined += 1
                    already += 1
                    continue
                examined += 1
                # B2: BOTH is a crash copy, never a licence to expire one half
                # and leave the other live. Prove the pair identical, then
                # authorise the expiry from one proven body and delete both.
                if inbox is not None and read is not None:
                    self._check_reconcilable(inbox, read, envelope_id)
                bundle = read if read is not None else inbox
                header, stored_at = self._verify_bundle(bundle, envelope_id)
                self._require_index_row(header, envelope_id, stored_at)
                ttl = effective_ttl_seconds(header, self.default_ttl)
                if instant < _expires_at(stored_at, ttl):
                    retained += 1
                    continue
                self._expire_bundle(bundle, header, envelope_id, stored_at, ttl, instant)
                if inbox is not None and read is not None:
                    # _expire_bundle removed the authoritative body; remove the
                    # remaining exact crash copy so the state is a clean EXPIRED.
                    leftover = inbox if bundle == read else read
                    if leftover.is_dir():
                        shutil.rmtree(leftover)
                        _fsync_directory(leftover.parent)
                expired += 1
            return SweepResult(examined=examined, expired=expired, retained=retained,
                               already_expired=already)

    def _tombstone_names(self) -> set:
        """The `<digest>` names of this seat's expiry tombstones."""
        base = self.mail_root / EXPIRED / self.seat
        if not base.is_dir():
            return set()
        names = set()
        for entry in base.iterdir():
            if not entry.is_file() or entry.name.startswith("."):
                continue
            if not entry.name.endswith(".json") or not _HEX64_RE.match(entry.name[:-5]):
                _reject(EXPIRED_TOMBSTONE_CORRUPT,
                        f"expired/{self.seat} holds {entry.name!r} that is not a tombstone")
            names.add(entry.name[:-5])
        return names

    def _read_tombstone_for(self, name: str) -> dict:
        return _read_tombstone(self.mail_root / EXPIRED / self.seat / (name + ".json"))

    def _require_index_row(self, header: Header, envelope_id: str, received_at: str) -> None:
        """Exactly one index row must match the verified bundle (D-038, B3)."""
        row = self.read_index_row(envelope_id)
        if row is None:
            _reject(INDEX_ROW_CONFLICT,
                    f"live bundle {envelope_id} has no matching index row; refusing expiry")
        if row != _index_row(header, envelope_id, received_at):
            _reject(INDEX_ROW_CONFLICT,
                    f"live bundle {envelope_id} disagrees with its index row; refusing expiry")

    def _expire_bundle(self, bundle: Path, header: Header, envelope_id: str,
                       received_at: str, ttl_seconds: int, instant: datetime) -> None:
        """Publish the tombstone, then delete the body (D-038, B2/B4).

        Tombstone publication happens FIRST and is immutable no-overwrite; an
        identical tombstone is idempotent, a different tombstone for the same
        `ENVELOPE_ID` is a named conflict that keeps the body and never
        overwrites the winner. Only after a committed tombstone is the live
        body deleted. `effective_ttl_seconds` records the exact policy used.
        """
        tombstone = {
            "schema": _TOMBSTONE_SCHEMA,
            "envelope_id": envelope_id,
            "sender": header.get("FROM"),
            "recipient": header.get("TO"),
            "kind": header.get("K"),
            "received_at": received_at,
            "expired_at": _format_utc(instant),
            "effective_ttl_seconds": ttl_seconds,
            "reason": TTL_EXPIRED,
        }
        data = _tombstone_bytes(tombstone)
        path = self.expired_tombstone(envelope_id)
        try:
            publish.publish_immutable(path, data, conflict_code=EXPIRED_TOMBSTONE_CONFLICT)
        except SailangError:
            raise
        _fsync_directory(path.parent)
        shutil.rmtree(bundle)
        _fsync_directory(bundle.parent)


    def _check_reconcilable(self, inbox: Path, read: Path, envelope_id: str) -> None:
        """Prove two bundle copies are the same transport object, or fail closed.

        Identity is content, never size: both receipts must name
        `envelope_id` with the same `RECEIVED_AT`, and the exact container
        bytes must be equal and hash to `envelope_id` itself. This reads
        `.senv`, so only the maintenance and open paths call it; header-only
        scan never resolves a BOTH pair.
        """
        try:
            inbox_receipt = (inbox / RECEIPT_NAME).read_bytes()
            read_receipt = (read / RECEIPT_NAME).read_bytes()
            inbox_raw = (inbox / CONTAINER_NAME).read_bytes()
            read_raw = (read / CONTAINER_NAME).read_bytes()
        except OSError as exc:
            _reject(READ_BUNDLE_CONFLICT,
                    f"inbox/read bundles cannot be reconciled ({type(exc).__name__})")
        if inbox_receipt != read_receipt:
            _reject(READ_BUNDLE_CONFLICT,
                    "inbox and read bundles carry different receipts; refusing to guess")
        if inbox_raw != read_raw:
            _reject(READ_BUNDLE_CONFLICT,
                    "inbox and read bundles carry different container bytes; refusing to guess")
        if envelope.envelope_id(inbox_raw) != envelope_id:
            _reject(READ_BUNDLE_CONFLICT,
                    "the bundle pair does not hash to its ENVELOPE_ID; refusing to guess")
        stored_id, _ = _read_receipt(inbox)
        if stored_id != envelope_id:
            _reject(RECEIPT_CORRUPT,
                    "the bundle pair receipt names a different envelope")


# --------------------------------------------------------------------------
# the session: budgets + header scan + budgeted open
# --------------------------------------------------------------------------


class PostOfficeSession:
    """One agent-side session over a mailbox, with declared budgets.

    `scan_budget` is the maximum number of index rows one `scan` call examines.
    `open_budget` is the maximum number of open attempts the session may make.
    Both are exact counts, not estimates (D-037).
    """

    def __init__(self, office: PostOffice, *, scan_budget: int, open_budget: int):
        if not isinstance(office, PostOffice):
            _reject(NOT_A_POST_OFFICE, "a session reads a PostOffice, not a path")
        for name, value in (("scan_budget", scan_budget), ("open_budget", open_budget)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                _reject(BAD_BUDGET, f"{name} is a non-negative integer count")
        self.office = office
        self.scan_budget = scan_budget
        self.open_budget = open_budget
        self._open_attempts = 0

    @property
    def open_attempts_used(self) -> int:
        return self._open_attempts

    # ---- scan ------------------------------------------------------------

    def scan(self, *, cursor: Optional[ScanCursor] = None, now=None,
             model_recommendations: Optional[Mapping[str, str]] = None) -> ScanResult:
        """Header-only, budget-bounded scan of the canonical index.

        Streams `index.jsonl` from a byte-offset cursor and parses at most
        `scan_budget` new rows per call — index rows plus directory state and
        nothing else: no `.senv` payload bytes, no `parse_header`, no `verify`,
        no `open`, no model, no network. On exhaustion the result is explicit
        and carries a continuation cursor that resumes without re-reading the
        prefix. A malformed row or a repeated `ENVELOPE_ID` that is actually
        reached fails closed; rows beyond the budget are not examined and
        cannot fail this call (D-037).
        """
        if cursor is not None and not isinstance(cursor, ScanCursor):
            _reject(BAD_CURSOR, "a continuation is a ScanCursor from a previous scan")
        if model_recommendations is None:
            recommendations: Mapping[str, str] = {}
        elif isinstance(model_recommendations, Mapping):
            recommendations = model_recommendations
        else:
            _reject("BAD_MODEL_RECOMMENDATIONS",
                    "model recommendations are a mapping of ENVELOPE_ID to verdict")
        for value in recommendations.values():
            if value not in VERDICTS:
                _reject(UNKNOWN_MODEL_VERDICT,
                        f"{value!r} is not one of {list(VERDICTS)}; refusing to guess")

        index_path = self.office.mail_root / INDEX_NAME
        start = _checked_cursor_offset(
            index_path, cursor.offset if cursor is not None else 0)
        rows, next_offset, exhausted = _stream_index_rows(
            index_path, start_offset=start, max_rows=self.scan_budget)
        instant = _as_instant(now if now is not None else self.office.clock())

        items = []
        seen = set()
        for row in rows:
            envelope_id = row["envelope_id"]
            if envelope_id in seen:
                _reject(INDEX_DUPLICATE_ENVELOPE_ID,
                        f"index repeats ENVELOPE_ID {envelope_id}; exactly one row "
                        "per envelope is the contract")
            seen.add(envelope_id)
            state = self.office.bundle_state(envelope_id, row=row)
            if state == NEITHER:
                _reject(INDEX_BODY_MISSING,
                        f"indexed envelope {envelope_id} has neither an inbox nor a read "
                        "bundle; refusing to forget it silently")
            if state == BOTH:
                _reject(RECONCILIATION_REQUIRED,
                        f"envelope {envelope_id} exists as both an inbox and a read "
                        "bundle; maintenance reconciliation must prove identity first")
            if state == EXPIRY_RECONCILIATION_REQUIRED:
                # D-038: a valid tombstone beside a live body is resolved by
                # maintenance, never by a header scan that would need `.senv`.
                _reject(EXPIRY_RECONCILIATION_REQUIRED,
                        f"envelope {envelope_id} has an expired tombstone and a live "
                        "bundle; maintenance reconciliation must prove identity first")
            if state in (READ_STATE, EXPIRED_STATE):
                continue  # read or intentionally expired: never reported as unread
            view = self._view_from_row(row, instant)
            machine = self.office.interest.decide(view)
            final, model_used, final_rule = merge_attention(
                machine.verdict, recommendations.get(envelope_id))
            items.append(ScanItem(view=view, machine_verdict=machine.verdict,
                                  machine_rule=machine.rule, machine_reason=machine.reason,
                                  model_verdict=model_used, final_verdict=final,
                                  final_rule=final_rule))
        return ScanResult(items=tuple(items), exhausted=exhausted,
                          cursor=ScanCursor(offset=next_offset) if exhausted else None,
                          rows_examined=len(rows))

    @staticmethod
    def _view_from_row(row: dict, instant: datetime) -> HeaderView:
        received = _parse_utc(row["received_at"], code=INDEX_CORRUPT)
        age_seconds = max(0.0, (instant - received).total_seconds())
        return HeaderView(envelope_id=row["envelope_id"], sender=row["from"],
                          recipient=row["to"], kind=row["kind"], topic=row["topic"],
                          created=row["created"], received_at=row["received_at"],
                          age_seconds=age_seconds, ref=row.get("ref"),
                          from_kid=row["from_kid"], to_kid=row["to_kid"])

    # ---- open ------------------------------------------------------------

    def open_message(self, envelope_id: str, *, recipient_private_key) -> OpenedEnvelope:
        """Open one unread message exactly once, under the open budget.

        Budget is checked before any decryption; an unread open consumes one
        attempt whether or not it succeeds (work was actually attempted). On
        success the immutable bundle moves from `inbox/<seat>/` to
        `read/<seat>/` without overwriting and without touching `index.jsonl`,
        and the `OpenedEnvelope` is returned. Opening calls no promotion
        operation — `MESSAGE != MEMORY`.
        """
        if not isinstance(envelope_id, str) or not _EID_RE.match(envelope_id):
            _reject("BAD_ENVELOPE_ID", "an envelope id is sha256:<64 lowercase hex>")
        # The destructive lifecycle lock brackets the whole read→decrypt→move
        # sequence (D-038 §9): a concurrent sweep either completes before this
        # open sees the body (then ALREADY_EXPIRED) or waits for the move, so
        # the pair can never leave two bodies or a body without a tombstone.
        with self.office._lifecycle_lock():
            state = self.office.bundle_state(envelope_id)
            if state in (EXPIRED_STATE, EXPIRY_RECONCILIATION_REQUIRED):
                # D-038 C2: expiry is established before any work, so no
                # decrypt, no state mutation and no open-budget consumption. A
                # tombstone beside a live body still never resurrects a payload.
                _reject(ALREADY_EXPIRED,
                        f"envelope {envelope_id} is expired; an expired message is never "
                        "decrypted or resurrected")
            if self._open_attempts >= self.open_budget:
                _reject(OPEN_BUDGET_EXHAUSTED,
                        f"this session has spent its {self.open_budget} open attempts; the "
                        "unread mail stays in the inbox and nothing was decrypted")
            if state == BOTH:
                _reject(RECONCILIATION_REQUIRED,
                        f"envelope {envelope_id} exists as both an inbox and a read bundle; "
                        "maintenance reconciliation must prove identity first")
            if state == READ_STATE:
                _reject(ALREADY_READ,
                        f"envelope {envelope_id} is already in read/; no second transition")
            if state == NEITHER:
                if self.office.has_index_row(envelope_id):
                    _reject(INDEX_BODY_MISSING,
                            f"indexed envelope {envelope_id} has no bundle to open")
                _reject(UNKNOWN_ENVELOPE, f"no bundle for {envelope_id}")

            self._open_attempts += 1
            raw = self.office._read_bundle_container(self.office.inbox_bundle(envelope_id))
            header = envelope.parse_header(raw)
            verified = envelope.verify(header, self.office.sender_registry)
            opened = envelope.open(verified, recipient_private_key,
                                   self.office.recipient_registry)
            self._transition_to_read(envelope_id)
            return opened

    def _transition_to_read(self, envelope_id: str) -> None:
        """Move the inbox bundle to read state. Caller holds the lifecycle lock."""
        inbox = self.office.inbox_bundle(envelope_id)
        read = self.office.read_bundle(envelope_id)
        read.parent.mkdir(parents=True, exist_ok=True)
        if read.exists():
            self.office._check_reconcilable(inbox, read, envelope_id)
            return  # read state wins when the pair is proven the same object
        try:
            os.rename(inbox, read)
            _fsync_directory(read.parent)
            _fsync_directory(inbox.parent)
            return
        except OSError:
            pass
        if read.exists():
            self.office._check_reconcilable(inbox, read, envelope_id)
            return
        # Portable fallback: publish the identical read bundle immutably, and
        # only then remove the inbox copy (crash-safe order).
        senv = self.office._read_bundle_container(inbox)
        _, stored_at = _read_receipt(inbox)
        status = _publish_dir(read.parent, read.name,
                              {CONTAINER_NAME: senv,
                               RECEIPT_NAME: _receipt_bytes(envelope_id, stored_at)},
                              conflict_code=READ_BUNDLE_CONFLICT)
        if status == PUBLISHED:
            shutil.rmtree(inbox)
