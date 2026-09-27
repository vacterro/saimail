"""Receiver-local human-attention budget: one scarce slot, owned by the receiver.

    MESSAGE EXISTS    !=  ATTENTION GRANTED
    CANDIDATE EXISTS  !=  MESSAGE SHOWN
    SENDER REQUEST    !=  RECEIVER CLASS
    ZERO DELIVERIES IS A SUCCESSFUL OUTCOME

The defect class this module eliminates: a transport object, its author, or an
automatic judge talking the receiver into spending human attention. A sender
cannot sign itself into importance. Only the receiver admits a candidate, sets
its class, and grants at most one presentation inside a rolling receiver-time
window. Delivery is two-phase -- RESERVE then ACK -- so a crash before the
human ever saw anything cannot silently consume the slot.

This layer is a scheduler of presentation opportunity. It never opens a sealed
source, never reads a private payload, never derives semantic worth, and never
changes another system's state. Deferral outcomes are returned as data to the
caller; acting on them is the caller's decision, not this module's.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from sailang.errors import SailangError

from .postoffice import _OsFileLock, utc_now
from .publish import publish_immutable

FORMAT = "SAIMAIL-HUMAN-ATTENTION1"
ATTENTION_DIR = "human-attention"

#: Receiver-owned closed sets. A transported object never assigns these to
#: itself; a parser never translates sender prose into them (A1/A5).
ALLOCATIONS = (
    "CRITICAL_RECOVERY",
    "AMBIGUITY_RESOLUTION",
    "DECISION_REQUEST",
    "ROUTINE_AUDIT",
    "IDLE_REPORT",
)
DEFERRAL_POLICIES = (
    "BLOCK_UNTIL_HUMAN",
    "QUEUE_AND_CONTINUE",
    "ESCALATE_AND_HALT",
)
SOURCE_KINDS = ("HUMAN_PRIVATE", "EXTERNAL_REFERENCE")
HUMAN_PRIVATE = "HUMAN_PRIVATE"
EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"

DEFAULT_MAX_PRESENTATIONS = 1
DEFAULT_PERIOD_SECONDS = 86_400
DEFAULT_LEASE_SECONDS = 300

#: Receiver-owned allocation precedence (A5). Within one class the receiver's
#: own ENQUEUED_AT decides, then the immutable candidate identity.
ALLOCATION_RANK = {name: rank for rank, name in enumerate(ALLOCATIONS)}

NO_MESSAGE = "NO_MESSAGE"
RESERVED = "RESERVED"
DEFERRED = "DEFERRED"
ATTENTION_BLOCKED = "ATTENTION_BLOCKED"
ATTENTION_HALT_REQUIRED = "ATTENTION_HALT_REQUIRED"
ADMITTED = "ADMITTED"
IDEMPOTENT = "IDEMPOTENT"
ACKED = "ACKED"
ALREADY_ACKED = "ALREADY_ACKED"
RELEASED = "RELEASED"

ATTENTION_BAD_HUMAN_ID = "ATTENTION_BAD_HUMAN_ID"
ATTENTION_WRONG_HUMAN = "ATTENTION_WRONG_HUMAN"
ATTENTION_BAD_ALLOCATION = "ATTENTION_BAD_ALLOCATION"
ATTENTION_BAD_DEFERRAL = "ATTENTION_BAD_DEFERRAL"
ATTENTION_BAD_SOURCE_KIND = "ATTENTION_BAD_SOURCE_KIND"
ATTENTION_BAD_SOURCE_REF = "ATTENTION_BAD_SOURCE_REF"
ATTENTION_BAD_ENQUEUED_AT = "ATTENTION_BAD_ENQUEUED_AT"
ATTENTION_BAD_BUDGET = "ATTENTION_BAD_BUDGET"
ATTENTION_BAD_LEASE_SECONDS = "ATTENTION_BAD_LEASE_SECONDS"
ATTENTION_BAD_CLOCK = "ATTENTION_BAD_CLOCK"
ATTENTION_BAD_RESERVATION = "ATTENTION_BAD_RESERVATION"
ATTENTION_UNKNOWN_RESERVATION = "ATTENTION_UNKNOWN_RESERVATION"
ATTENTION_RESERVATION_EXPIRED = "ATTENTION_RESERVATION_EXPIRED"
ATTENTION_CLOCK_REGRESSION = "ATTENTION_CLOCK_REGRESSION"
ATTENTION_CANDIDATE_ALREADY_PRESENTED = "ATTENTION_CANDIDATE_ALREADY_PRESENTED"
ATTENTION_CANDIDATE_CONFLICT = "ATTENTION_CANDIDATE_CONFLICT"
ATTENTION_CANDIDATE_CORRUPT = "ATTENTION_CANDIDATE_CORRUPT"
ATTENTION_PRESENTED_CONFLICT = "ATTENTION_PRESENTED_CONFLICT"
ATTENTION_PRESENTED_CORRUPT = "ATTENTION_PRESENTED_CORRUPT"
ATTENTION_LEASE_CORRUPT = "ATTENTION_LEASE_CORRUPT"
ATTENTION_LOCK_TIMEOUT = "ATTENTION_LOCK_TIMEOUT"
NOT_AN_ATTENTION_CANDIDATE = "NOT_AN_ATTENTION_CANDIDATE"

CANDIDATE_DOMAIN = b"SAIMAIL-HUMAN-ATTENTION-CANDIDATE1\x00"

_HUMAN_ID_RE = re.compile(r"^human-id:sha256:[0-9a-f]{64}$")
_PRIVATE_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EXTERNAL_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_RESERVATION_RE = re.compile(r"^[0-9a-f]{32}$")
_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_NAMES = re.compile(r"^([0-9a-f]{64})\.json$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_CANDIDATE_KEYS = frozenset({
    "SCHEMA", "CANDIDATE_ID", "TO_HUMAN", "SOURCE_KIND", "SOURCE_REF",
    "ALLOCATION", "DEFERRAL_POLICY", "ENQUEUED_AT",
})
_PRESENTED_KEYS = frozenset({
    "SCHEMA", "CANDIDATE_ID", "RESERVATION_ID", "PRESENTED_AT",
})
_LEASE_KEYS = frozenset({
    "SCHEMA", "CANDIDATE_ID", "RESERVATION_ID", "RESERVED_AT", "LEASE_UNTIL",
})

_DEFERRAL_OUTCOMES = {
    "QUEUE_AND_CONTINUE": DEFERRED,
    "BLOCK_UNTIL_HUMAN": ATTENTION_BLOCKED,
    "ESCALATE_AND_HALT": ATTENTION_HALT_REQUIRED,
}


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _canonical_json(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")


def _parse_instant(value, *, code: str) -> datetime:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        _reject(code, "a receiver instant is exact UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _reject(code, "the instant is not a real UTC calendar moment")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _reject(code, "the instant is not canonical UTC")
    return parsed


def _format_instant(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _loads_strict(text: str) -> dict:
    """Decode one JSON object, refusing duplicate keys outright (B3)."""
    def pairs(hook_pairs):
        seen = set()
        for key, _ in hook_pairs:
            if key in seen:
                _reject("ATTENTION_DUPLICATE_FIELD", f"JSON object repeats key {key!r}")
            seen.add(key)
        return dict(hook_pairs)

    return json.loads(text, object_pairs_hook=pairs)


def attention_candidate_id(to_human: str, source_kind: str, source_ref: str) -> str:
    """Domain-separated receiver identity over human, kind and source ref (A13).

    ENQUEUED_AT is deliberately outside the identity: a resubmitted source does
    not become a second candidate merely because it arrived later.
    """
    material = (CANDIDATE_DOMAIN + to_human.encode("utf-8") + b"\x00"
                + source_kind.encode("ascii") + b"\x00" + source_ref.encode("utf-8"))
    return "sha256:" + hashlib.sha256(material).hexdigest()


@dataclass(frozen=True)
class AttentionCandidate:
    """One immutable receiver-admitted pointer at an externally held source.

    The candidate is metadata only. For ``HUMAN_PRIVATE`` the SOURCE_REF is the
    stored LETTER_ID; nothing here opens it, and REFERENCE_EXISTS never means
    REFERENCE_SUPPORTS_CLAIM (A3/A4). No free-form field exists, by design: a
    "why this matters" text is a persuasion surface (B3).
    """

    to_human: str
    source_kind: str
    source_ref: str
    allocation: str
    deferral_policy: str
    enqueued_at: str

    def __post_init__(self) -> None:
        if not isinstance(self.to_human, str) or not _HUMAN_ID_RE.fullmatch(self.to_human):
            _reject(ATTENTION_BAD_HUMAN_ID,
                    "TO_HUMAN is human-id:sha256:<64 lowercase hex>")
        if self.source_kind not in SOURCE_KINDS:
            _reject(ATTENTION_BAD_SOURCE_KIND,
                    f"SOURCE_KIND must be one of {SOURCE_KINDS}")
        if self.source_kind == HUMAN_PRIVATE:
            if not isinstance(self.source_ref, str) \
                    or not _PRIVATE_REF_RE.fullmatch(self.source_ref):
                _reject(ATTENTION_BAD_SOURCE_REF,
                        "a HUMAN_PRIVATE source ref is the stored LETTER_ID "
                        "sha256:<64 lowercase hex>")
        elif not isinstance(self.source_ref, str) \
                or not _EXTERNAL_REF_RE.fullmatch(self.source_ref):
            _reject(ATTENTION_BAD_SOURCE_REF,
                    "an EXTERNAL_REFERENCE source ref is a bounded inert token, "
                    "at most 128 characters")
        if self.allocation not in ALLOCATIONS:
            _reject(ATTENTION_BAD_ALLOCATION,
                    f"ALLOCATION must be one of {ALLOCATIONS}")
        if self.deferral_policy not in DEFERRAL_POLICIES:
            _reject(ATTENTION_BAD_DEFERRAL,
                    f"DEFERRAL_POLICY must be one of {DEFERRAL_POLICIES}")
        _parse_instant(self.enqueued_at, code=ATTENTION_BAD_ENQUEUED_AT)

    @property
    def candidate_id(self) -> str:
        return attention_candidate_id(self.to_human, self.source_kind, self.source_ref)

    def render(self) -> bytes:
        return _canonical_json({
            "SCHEMA": 1,
            "CANDIDATE_ID": self.candidate_id,
            "TO_HUMAN": self.to_human,
            "SOURCE_KIND": self.source_kind,
            "SOURCE_REF": self.source_ref,
            "ALLOCATION": self.allocation,
            "DEFERRAL_POLICY": self.deferral_policy,
            "ENQUEUED_AT": self.enqueued_at,
        })


@dataclass(frozen=True)
class AttentionBudget:
    """Receiver-owned rolling budget. Zero presentations is a valid choice."""

    max_presentations: int = DEFAULT_MAX_PRESENTATIONS
    period_seconds: int = DEFAULT_PERIOD_SECONDS

    def __post_init__(self) -> None:
        if isinstance(self.max_presentations, bool) \
                or not isinstance(self.max_presentations, int) \
                or self.max_presentations < 0:
            _reject(ATTENTION_BAD_BUDGET,
                    "max_presentations must be a non-negative integer; zero is valid")
        if isinstance(self.period_seconds, bool) \
                or not isinstance(self.period_seconds, int) \
                or self.period_seconds <= 0:
            _reject(ATTENTION_BAD_BUDGET, "period_seconds must be a positive integer")


@dataclass(frozen=True)
class Reservation:
    """One receiver-local provisional attention slot; mutable operational state."""

    reservation_id: str
    candidate_id: str
    reserved_at: str
    lease_until: str


@dataclass(frozen=True)
class AdmissionResult:
    status: str
    candidate: AttentionCandidate
    path: Path


@dataclass(frozen=True)
class SelectionResult:
    status: str
    candidate: Optional[AttentionCandidate] = None
    reservation: Optional[Reservation] = None


@dataclass(frozen=True)
class PresentedReceipt:
    """Immutable receiver evidence that an application surfaced the item.

    It records a presentation attempt. It does not prove the human read,
    understood, agreed with or acted on anything (B11).
    """

    candidate_id: str
    reservation_id: str
    presented_at: str


@dataclass(frozen=True)
class AckResult:
    status: str
    receipt: PresentedReceipt
    path: Path


@dataclass(frozen=True)
class ReleaseResult:
    status: str
    reservation_id: str


@dataclass(frozen=True)
class BudgetState:
    max_presentations: int
    period_seconds: int
    consumed: int
    available: int
    presented_in_window: int
    active_reservations: int
    pending_candidates: int


@dataclass(frozen=True)
class _Lease:
    reservation_id: str
    candidate_id: str
    reserved_at: str
    lease_until: str
    reserved_at_instant: datetime
    lease_until_instant: datetime

    def render(self) -> bytes:
        return _canonical_json({
            "SCHEMA": 1,
            "CANDIDATE_ID": self.candidate_id,
            "RESERVATION_ID": self.reservation_id,
            "RESERVED_AT": self.reserved_at,
            "LEASE_UNTIL": self.lease_until,
        })


class _AttentionLock(_OsFileLock):
    """One process-safe lock serializing every attention state transition (B2)."""

    def __init__(self, path: Path):
        super().__init__(path, busy_code=ATTENTION_LOCK_TIMEOUT)


def _parse_candidate_bytes(data: bytes) -> AttentionCandidate:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _reject(ATTENTION_CANDIDATE_CORRUPT, "a candidate record is not strict UTF-8")
    if data.startswith(b"\xef\xbb\xbf"):
        _reject(ATTENTION_CANDIDATE_CORRUPT, "a candidate record carries no BOM")
    try:
        raw = _loads_strict(text)
    except SailangError:
        _reject(ATTENTION_CANDIDATE_CORRUPT, "a candidate record repeats a JSON key")
    except json.JSONDecodeError:
        _reject(ATTENTION_CANDIDATE_CORRUPT, "a candidate record is not JSON")
    if not isinstance(raw, dict) or set(raw) != _CANDIDATE_KEYS:
        _reject(ATTENTION_CANDIDATE_CORRUPT,
                "a candidate record has a missing or unknown field")
    if raw["SCHEMA"] != 1:
        _reject(ATTENTION_CANDIDATE_CORRUPT, "unknown candidate record schema")
    if _canonical_json(raw) != data:
        _reject(ATTENTION_CANDIDATE_CORRUPT, "a candidate record is not canonical JSON")
    try:
        candidate = AttentionCandidate(
            to_human=raw["TO_HUMAN"],
            source_kind=raw["SOURCE_KIND"],
            source_ref=raw["SOURCE_REF"],
            allocation=raw["ALLOCATION"],
            deferral_policy=raw["DEFERRAL_POLICY"],
            enqueued_at=raw["ENQUEUED_AT"],
        )
    except SailangError as exc:
        _reject(ATTENTION_CANDIDATE_CORRUPT, f"invalid stored candidate: {exc.detail}")
    if raw["CANDIDATE_ID"] != candidate.candidate_id:
        _reject(ATTENTION_CANDIDATE_CORRUPT,
                "a candidate record's identity disagrees with its fields")
    return candidate


def _parse_presented_bytes(data: bytes) -> PresentedReceipt:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _reject(ATTENTION_PRESENTED_CORRUPT, "a presented receipt is not strict UTF-8")
    if data.startswith(b"\xef\xbb\xbf"):
        _reject(ATTENTION_PRESENTED_CORRUPT, "a presented receipt carries no BOM")
    try:
        raw = _loads_strict(text)
    except SailangError:
        _reject(ATTENTION_PRESENTED_CORRUPT, "a presented receipt repeats a JSON key")
    except json.JSONDecodeError:
        _reject(ATTENTION_PRESENTED_CORRUPT, "a presented receipt is not JSON")
    if not isinstance(raw, dict) or set(raw) != _PRESENTED_KEYS:
        _reject(ATTENTION_PRESENTED_CORRUPT,
                "a presented receipt has a missing or unknown field")
    if raw["SCHEMA"] != 1:
        _reject(ATTENTION_PRESENTED_CORRUPT, "unknown presented receipt schema")
    if _canonical_json(raw) != data:
        _reject(ATTENTION_PRESENTED_CORRUPT, "a presented receipt is not canonical JSON")
    if not isinstance(raw["CANDIDATE_ID"], str) or not _REF_RE.fullmatch(raw["CANDIDATE_ID"]):
        _reject(ATTENTION_PRESENTED_CORRUPT, "a receipt candidate id is not a digest")
    if not isinstance(raw["RESERVATION_ID"], str) \
            or not _RESERVATION_RE.fullmatch(raw["RESERVATION_ID"]):
        _reject(ATTENTION_PRESENTED_CORRUPT, "a receipt reservation id is malformed")
    _parse_instant(raw["PRESENTED_AT"], code=ATTENTION_PRESENTED_CORRUPT)
    return PresentedReceipt(raw["CANDIDATE_ID"], raw["RESERVATION_ID"], raw["PRESENTED_AT"])


def _parse_lease_bytes(data: bytes) -> _Lease:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _reject(ATTENTION_LEASE_CORRUPT, "a lease is not strict UTF-8")
    if data.startswith(b"\xef\xbb\xbf"):
        _reject(ATTENTION_LEASE_CORRUPT, "a lease carries no BOM")
    try:
        raw = _loads_strict(text)
    except SailangError:
        _reject(ATTENTION_LEASE_CORRUPT, "a lease repeats a JSON key")
    except json.JSONDecodeError:
        _reject(ATTENTION_LEASE_CORRUPT, "a lease is not JSON")
    if not isinstance(raw, dict) or set(raw) != _LEASE_KEYS:
        _reject(ATTENTION_LEASE_CORRUPT, "a lease has a missing or unknown field")
    if raw["SCHEMA"] != 1:
        _reject(ATTENTION_LEASE_CORRUPT, "unknown lease schema")
    if _canonical_json(raw) != data:
        _reject(ATTENTION_LEASE_CORRUPT, "a lease is not canonical JSON")
    if not isinstance(raw["CANDIDATE_ID"], str) or not _REF_RE.fullmatch(raw["CANDIDATE_ID"]):
        _reject(ATTENTION_LEASE_CORRUPT, "a lease candidate id is not a digest")
    if not isinstance(raw["RESERVATION_ID"], str) \
            or not _RESERVATION_RE.fullmatch(raw["RESERVATION_ID"]):
        _reject(ATTENTION_LEASE_CORRUPT, "a lease reservation id is malformed")
    reserved = _parse_instant(raw["RESERVED_AT"], code=ATTENTION_LEASE_CORRUPT)
    until = _parse_instant(raw["LEASE_UNTIL"], code=ATTENTION_LEASE_CORRUPT)
    if until <= reserved:
        _reject(ATTENTION_LEASE_CORRUPT, "a lease must end after it was reserved")
    return _Lease(raw["RESERVATION_ID"], raw["CANDIDATE_ID"], raw["RESERVED_AT"],
                  raw["LEASE_UNTIL"], reserved, until)


def _replace_atomic(path: Path, data: bytes) -> None:
    """Operational state may be atomically replaced while the lock is held (B1)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with staged.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


class AttentionQueue:
    """One receiver human's durable attention queue under a caller-supplied root.

    The queue holds candidate metadata, immutable presentation receipts and
    provisional leases. It has no background activity: leases expire only when
    an explicit operation next runs, which makes every recovery mechanical and
    leaves no daemon behind.
    """

    def __init__(self, root, *, human_id: str, budget: Optional[AttentionBudget] = None,
                 lease_seconds: int = DEFAULT_LEASE_SECONDS,
                 clock: Callable[[], str] = utc_now):
        if not isinstance(human_id, str) or not _HUMAN_ID_RE.fullmatch(human_id):
            _reject(ATTENTION_BAD_HUMAN_ID,
                    "HUMAN_ID is human-id:sha256:<64 lowercase hex>")
        if budget is None:
            budget = AttentionBudget()
        if not isinstance(budget, AttentionBudget):
            _reject(ATTENTION_BAD_BUDGET, "budget must be an AttentionBudget")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, int) \
                or lease_seconds <= 0:
            _reject(ATTENTION_BAD_LEASE_SECONDS, "lease_seconds must be positive")
        if not callable(clock):
            _reject(ATTENTION_BAD_CLOCK, "clock must be a callable receiver clock")
        self.human_id = human_id
        self.budget = budget
        self.lease_seconds = lease_seconds
        self.clock = clock
        self.root = Path(root) / ATTENTION_DIR / human_id.rsplit(":", 1)[1]

    # -- paths ---------------------------------------------------------

    def _candidate_path(self, candidate_id: str) -> Path:
        return self.root / "candidates" / (candidate_id.rsplit(":", 1)[1] + ".json")

    def _receipt_path(self, candidate_id: str) -> Path:
        return self.root / "presented" / (candidate_id.rsplit(":", 1)[1] + ".json")

    def _lease_path(self, candidate_id: str) -> Path:
        return self.root / "leases" / (candidate_id.rsplit(":", 1)[1] + ".json")

    # -- durable state -------------------------------------------------

    def _read_records(self, directory: Path, parse, corrupt_code: str) -> Dict[str, object]:
        records: Dict[str, object] = {}
        if not directory.is_dir():
            return records
        for path in sorted(directory.iterdir()):
            if path.name.startswith("."):
                continue  # a crashed staging file is not a committed record
            if not _NAMES.fullmatch(path.name):
                _reject(corrupt_code, f"{path.name!r} is not a canonical record name")
            try:
                data = path.read_bytes()
            except OSError:
                _reject(corrupt_code, f"{path.name} cannot be read back")
            record = parse(data)
            digest = path.name[:-len(".json")]
            identity = getattr(record, "candidate_id", None)
            if identity is None or identity.rsplit(":", 1)[1] != digest:
                _reject(corrupt_code, f"{path.name} disagrees with its own identity")
            records[identity] = record
        return records

    def _load_candidates(self) -> Dict[str, AttentionCandidate]:
        return self._read_records(self.root / "candidates", _parse_candidate_bytes,
                                  ATTENTION_CANDIDATE_CORRUPT)

    def _load_presented(self) -> Dict[str, PresentedReceipt]:
        return self._read_records(self.root / "presented", _parse_presented_bytes,
                                  ATTENTION_PRESENTED_CORRUPT)

    def _load_leases(self) -> Dict[str, _Lease]:
        records = {}
        directory = self.root / "leases"
        if not directory.is_dir():
            return records
        for path in sorted(directory.iterdir()):
            if path.name.startswith("."):
                continue
            if not _NAMES.fullmatch(path.name):
                _reject(ATTENTION_LEASE_CORRUPT, f"{path.name!r} is not a canonical lease name")
            try:
                data = path.read_bytes()
            except OSError:
                _reject(ATTENTION_LEASE_CORRUPT, f"{path.name} cannot be read back")
            lease = _parse_lease_bytes(data)
            if lease.candidate_id.rsplit(":", 1)[1] != path.name[:-len(".json")]:
                _reject(ATTENTION_LEASE_CORRUPT, f"{path.name} disagrees with its own lease")
            records[lease.candidate_id] = lease
        return records

    def _remove_lease(self, candidate_id: str) -> None:
        self._lease_path(candidate_id).unlink(missing_ok=True)

    def _validate_receipts(self, presented: Dict[str, PresentedReceipt],
                           candidates: Dict[str, AttentionCandidate],
                           leases: Optional[Dict[str, _Lease]] = None) -> None:
        for receipt in presented.values():
            if receipt.candidate_id not in candidates:
                _reject(ATTENTION_PRESENTED_CORRUPT,
                        "a presented receipt names no durable candidate")
            lease = leases.get(receipt.candidate_id) if leases is not None else None
            if lease is None:
                continue
            presented_at = _parse_instant(receipt.presented_at,
                                          code=ATTENTION_PRESENTED_CORRUPT)
            if (receipt.reservation_id != lease.reservation_id
                    or presented_at < lease.reserved_at_instant
                    or presented_at >= lease.lease_until_instant):
                _reject(ATTENTION_PRESENTED_CORRUPT,
                        "a presented receipt contradicts its known reservation history")

    def _refuse_lease_clock_regression(self, leases: Dict[str, _Lease],
                                       now: datetime) -> None:
        if any(now < lease.reserved_at_instant for lease in leases.values()):
            _reject(ATTENTION_CLOCK_REGRESSION,
                    "receiver clock is earlier than durable RESERVED_AT")

    def _cleanup_leases(self, leases: Dict[str, _Lease],
                        presented: Dict[str, PresentedReceipt],
                        now: datetime) -> Dict[str, _Lease]:
        """Expire stale leases and drop leases already superseded by a receipt."""
        self._refuse_lease_clock_regression(leases, now)
        active: Dict[str, _Lease] = {}
        for candidate_id, lease in leases.items():
            if candidate_id in presented or now >= lease.lease_until_instant:
                self._remove_lease(candidate_id)
                continue
            active[candidate_id] = lease
        return active

    def _order_key(self, candidate: AttentionCandidate) -> Tuple[int, str, str]:
        return (ALLOCATION_RANK[candidate.allocation], candidate.enqueued_at,
                candidate.candidate_id)

    def _pending(self, candidates: Dict[str, AttentionCandidate],
                 presented: Dict[str, PresentedReceipt],
                 active: Dict[str, _Lease]) -> Tuple[AttentionCandidate, ...]:
        eligible = [candidate for candidate_id, candidate in candidates.items()
                    if candidate_id not in presented and candidate_id not in active]
        return tuple(sorted(eligible, key=self._order_key))

    # -- explicit receiver API -----------------------------------------

    def admit_receiver_candidate(self, *, source_kind: str, source_ref: str,
                                 allocation: str,
                                 deferral_policy: str) -> AdmissionResult:
        """Admit one candidate by explicit receiver decision, never by transport.

        Queue identity supplies TO_HUMAN and the queue clock mints ENQUEUED_AT.
        Re-admission with identical receiver policy is idempotent and the first
        timestamp stands; changed policy refuses without rewriting history.
        """
        with self._lock():
            instant = self._instant()
            candidate = AttentionCandidate(
                to_human=self.human_id,
                source_kind=source_kind,
                source_ref=source_ref,
                allocation=allocation,
                deferral_policy=deferral_policy,
                enqueued_at=_format_instant(instant),
            )
            path = self._candidate_path(candidate.candidate_id)
            if path.is_file():
                try:
                    existing = _parse_candidate_bytes(path.read_bytes())
                except OSError:
                    _reject(ATTENTION_CANDIDATE_CORRUPT,
                            "the committed candidate cannot be read back")
                if (existing.allocation != candidate.allocation
                        or existing.deferral_policy != candidate.deferral_policy):
                    _reject(ATTENTION_CANDIDATE_CONFLICT,
                            "a committed candidate holds different receiver policy; "
                            "history is not rewritten")
                return AdmissionResult(IDEMPOTENT, existing, path)
            try:
                outcome = publish_immutable(path, candidate.render(),
                                            conflict_code=ATTENTION_CANDIDATE_CONFLICT)
            except SailangError as exc:
                if exc.code != ATTENTION_CANDIDATE_CONFLICT:
                    raise
                existing = _parse_candidate_bytes(path.read_bytes())
                if (existing.allocation != candidate.allocation
                        or existing.deferral_policy != candidate.deferral_policy):
                    raise
                return AdmissionResult(IDEMPOTENT, existing, path)
            status = ADMITTED if outcome == "PUBLISHED" else IDEMPOTENT
            return AdmissionResult(status, candidate, path)

    def reserve_next(self) -> SelectionResult:
        """Propose one presentation slot without presenting anything.

        A successful reservation provisionally consumes one budget slot so two
        concurrent workers cannot both take the final one (A11/B7). If the
        budget is exhausted, the outcome is the highest-ranked pending
        candidate's deferral policy returned as data (C2).
        """
        with self._lock():
            instant = self._instant()
            candidates = self._load_candidates()
            presented = self._load_presented()
            leases = self._load_leases()
            self._validate_receipts(presented, candidates, leases)
            active = self._cleanup_leases(leases, presented, instant)
            pending = self._pending(candidates, presented, active)
            consumed = self._consumed(presented, active, instant)
            if consumed < self.budget.max_presentations and pending:
                candidate = pending[0]
                reservation = self._create_reservation(candidate, instant)
                return SelectionResult(RESERVED, candidate, reservation)
            if pending:
                return SelectionResult(_DEFERRAL_OUTCOMES[pending[0].deferral_policy],
                                       candidate=pending[0])
            return SelectionResult(NO_MESSAGE)

    def ack_presented(self, reservation_id: str) -> AckResult:
        """Record successful external presentation; this is the only consumption.

        The immutable receipt is published first and only then is the lease
        removed, so a crash between the two steps cannot lose the fact that the
        slot was spent; recovery treats receipt-plus-lease as presented (B9).
        """
        if not isinstance(reservation_id, str) or not _RESERVATION_RE.fullmatch(reservation_id):
            _reject(ATTENTION_BAD_RESERVATION,
                    "a reservation id is 32 lowercase hex characters")
        with self._lock():
            instant = self._instant()
            candidates = self._load_candidates()
            presented = self._load_presented()
            leases = self._load_leases()
            self._validate_receipts(presented, candidates, leases)
            self._refuse_lease_clock_regression(leases, instant)
            matched = next((lease for lease in leases.values()
                            if lease.reservation_id == reservation_id), None)
            for candidate_id, lease in list(leases.items()):
                if lease is matched:
                    continue
                if candidate_id in presented or instant >= lease.lease_until_instant:
                    self._remove_lease(candidate_id)
            if matched is None:
                receipt = self._receipt_for_reservation(presented, reservation_id)
                if receipt is not None:
                    return AckResult(ALREADY_ACKED, receipt,
                                     self._receipt_path(receipt.candidate_id))
                _reject(ATTENTION_UNKNOWN_RESERVATION,
                        "no reservation with this token is on record")
            existing = presented.get(matched.candidate_id)
            if existing is not None:
                self._remove_lease(matched.candidate_id)
                if existing.reservation_id == reservation_id:
                    return AckResult(ALREADY_ACKED, existing,
                                     self._receipt_path(existing.candidate_id))
                _reject(ATTENTION_CANDIDATE_ALREADY_PRESENTED,
                        "this candidate was presented under another reservation")
            if instant >= matched.lease_until_instant:
                self._remove_lease(matched.candidate_id)
                _reject(ATTENTION_RESERVATION_EXPIRED,
                        "the reservation lease has expired; the candidate is queued again")
            receipt = PresentedReceipt(matched.candidate_id, reservation_id,
                                       _format_instant(instant))
            path = self._receipt_path(matched.candidate_id)
            publish_immutable(path, _canonical_json({
                "SCHEMA": 1,
                "CANDIDATE_ID": receipt.candidate_id,
                "RESERVATION_ID": receipt.reservation_id,
                "PRESENTED_AT": receipt.presented_at,
            }), conflict_code=ATTENTION_PRESENTED_CONFLICT)
            self._remove_lease(matched.candidate_id)
            return AckResult(ACKED, receipt, path)

    def release(self, reservation_id: str) -> ReleaseResult:
        """Drop one active lease; the candidate stays queued and nothing is spent."""
        if not isinstance(reservation_id, str) or not _RESERVATION_RE.fullmatch(reservation_id):
            _reject(ATTENTION_BAD_RESERVATION,
                    "a reservation id is 32 lowercase hex characters")
        with self._lock():
            instant = self._instant()
            candidates = self._load_candidates()
            presented = self._load_presented()
            leases = self._load_leases()
            self._validate_receipts(presented, candidates, leases)
            active = self._cleanup_leases(leases, presented, instant)
            for candidate_id, lease in active.items():
                if lease.reservation_id == reservation_id:
                    self._remove_lease(candidate_id)
                    return ReleaseResult(RELEASED, reservation_id)
            _reject(ATTENTION_UNKNOWN_RESERVATION,
                    "no active reservation with this token; another lease is not released")

    def budget_state(self) -> BudgetState:
        """Report the current rolling consumption; explicit, read-only state."""
        with self._lock():
            instant = self._instant()
            candidates = self._load_candidates()
            presented = self._load_presented()
            leases = self._load_leases()
            self._validate_receipts(presented, candidates, leases)
            active = self._cleanup_leases(leases, presented, instant)
            consumed = self._consumed(presented, active, instant)
            window = self._presented_in_window(presented, instant)
            pending = self._pending(candidates, presented, active)
            return BudgetState(
                max_presentations=self.budget.max_presentations,
                period_seconds=self.budget.period_seconds,
                consumed=consumed,
                available=max(0, self.budget.max_presentations - consumed),
                presented_in_window=len(window),
                active_reservations=len(active),
                pending_candidates=len(pending),
            )

    # -- internals -----------------------------------------------------

    def _lock(self) -> _AttentionLock:
        return _AttentionLock(self.root / "attention.lock")

    def _instant(self) -> datetime:
        return _parse_instant(self.clock(), code=ATTENTION_BAD_CLOCK)

    def _presented_in_window(self, presented: Dict[str, PresentedReceipt],
                             now: datetime) -> Tuple[PresentedReceipt, ...]:
        lower = now - timedelta(seconds=self.budget.period_seconds)
        # A clock rollback cannot turn an immutable future receipt into capacity.
        # Future PRESENTED_AT remains greater than the lower bound and consumes.
        return tuple(receipt for receipt in presented.values()
                     if _parse_instant(receipt.presented_at,
                                       code=ATTENTION_PRESENTED_CORRUPT) > lower)

    def _consumed(self, presented: Dict[str, PresentedReceipt],
                  active: Dict[str, _Lease], now: datetime) -> int:
        return len(self._presented_in_window(presented, now)) + len(active)

    def _receipt_for_reservation(self, presented: Dict[str, PresentedReceipt],
                                 reservation_id: str) -> Optional[PresentedReceipt]:
        for receipt in presented.values():
            if receipt.reservation_id == reservation_id:
                return receipt
        return None

    def _create_reservation(self, candidate: AttentionCandidate,
                            now: datetime) -> Reservation:
        reservation = Reservation(
            reservation_id=secrets.token_hex(16),
            candidate_id=candidate.candidate_id,
            reserved_at=_format_instant(now),
            lease_until=_format_instant(now + timedelta(seconds=self.lease_seconds)),
        )
        lease = _Lease(reservation.reservation_id, reservation.candidate_id,
                       reservation.reserved_at, reservation.lease_until,
                       now, now + timedelta(seconds=self.lease_seconds))
        _replace_atomic(self._lease_path(candidate.candidate_id), lease.render())
        return reservation


__all__ = [
    "ACKED", "ADMITTED", "ALREADY_ACKED", "ALLOCATIONS", "ALLOCATION_RANK",
    "ATTENTION_BAD_ALLOCATION", "ATTENTION_BAD_BUDGET", "ATTENTION_BAD_CLOCK",
    "ATTENTION_BAD_DEFERRAL", "ATTENTION_BAD_ENQUEUED_AT",
    "ATTENTION_BAD_HUMAN_ID", "ATTENTION_BAD_LEASE_SECONDS",
    "ATTENTION_BAD_RESERVATION", "ATTENTION_BAD_SOURCE_KIND",
    "ATTENTION_BAD_SOURCE_REF", "ATTENTION_BLOCKED",
    "ATTENTION_CLOCK_REGRESSION",
    "ATTENTION_CANDIDATE_ALREADY_PRESENTED", "ATTENTION_CANDIDATE_CONFLICT",
    "ATTENTION_CANDIDATE_CORRUPT", "ATTENTION_DIR", "ATTENTION_HALT_REQUIRED",
    "ATTENTION_LEASE_CORRUPT", "ATTENTION_LOCK_TIMEOUT",
    "ATTENTION_PRESENTED_CONFLICT", "ATTENTION_PRESENTED_CORRUPT",
    "ATTENTION_RESERVATION_EXPIRED", "ATTENTION_UNKNOWN_RESERVATION",
    "ATTENTION_WRONG_HUMAN", "AckResult", "AdmissionResult", "AttentionBudget",
    "AttentionCandidate", "AttentionQueue", "BudgetState",
    "DEFAULT_LEASE_SECONDS", "DEFAULT_MAX_PRESENTATIONS",
    "DEFAULT_PERIOD_SECONDS", "DEFERRAL_POLICIES", "DEFERRED", "EXTERNAL_REFERENCE",
    "FORMAT", "HUMAN_PRIVATE", "IDEMPOTENT", "NO_MESSAGE",
    "NOT_AN_ATTENTION_CANDIDATE", "PresentedReceipt", "RELEASED", "RESERVED",
    "ReleaseResult", "Reservation", "SOURCE_KINDS", "SelectionResult",
    "attention_candidate_id",
]
