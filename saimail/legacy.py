"""Canonical LEG1 operational transfer without authority inflation (D-040).

The defect class this module eliminates is predecessor prose silently becoming
truth, task scope, command, or institutional memory.  LEG1 keeps the account,
its cited references, its observed scope, and its transport provenance exact;
successor rendering only prepares bounded data.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import InitVar, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Optional, Tuple

from sailang.errors import SailangError

from . import envelope, publish
from .postoffice import PostOffice

FORMAT = "LEG1"
LEGACY_KIND = "EXPERIENCE"
LEGACY_TOPIC = "legacy"
WATCH_NEXT_UNVERIFIED = "UNVERIFIED"

MAX_PACKET_BYTES = 32_768
MAX_FIELD_BYTES = 4_096
MAX_SUBJECT_BYTES = 128
DEFAULT_MAX_ENTRIES = 16
DEFAULT_MAX_RENDERED_BYTES = 32_768

REFERENCED = "REFERENCED"
RESOLVED = "RESOLVED"
UNRESOLVED = "UNRESOLVED"
ADOPTED = "ADOPTED"
ALREADY_ADOPTED = "ALREADY_ADOPTED"

LEGACY_ENTRY_CONFLICT = "LEGACY_ENTRY_CONFLICT"
LEGACY_ENTRY_CORRUPT = "LEGACY_ENTRY_CORRUPT"
LEGACY_CONTEXT_ENTRY_TOO_LARGE = "LEGACY_CONTEXT_ENTRY_TOO_LARGE"

_ENTRY_DOMAIN = b"SAIMAIL-LEGACY1-ENTRY\x00"
_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SUBJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")
_SEAT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_FIELDS = (
    "SUBJECT",
    "OBSERVED_SCOPE",
    "WHAT_WORKED",
    "WHAT_WORKED_EVIDENCE",
    "WHAT_FAILED",
    "WHAT_FAILED_EVIDENCE",
    "WHAT_LOOKED_RIGHT_BUT_WAS_WRONG",
    "WHAT_WRONG_EVIDENCE",
    "WATCH_NEXT",
    "WATCH_NEXT_EVIDENCE",
    "WATCH_NEXT_STATUS",
    "CREATED",
)
_PROVENANCE_KEYS = frozenset({
    "schema", "legacy_entry_id", "legacy_content_id", "source_envelope_id",
    "source_from", "source_from_kid", "recipient", "received_at", "adopted_at",
})


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _valid_utc(value: str, *, code: str = "LEGACY_BAD_CREATED") -> str:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        _reject(code, "timestamp must be exact UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _reject(code, "timestamp is not a real UTC calendar instant")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _reject(code, "timestamp is not canonical UTC")
    return value


def _text(value: str, name: str, *, limit: int = MAX_FIELD_BYTES) -> str:
    if not isinstance(value, str):
        _reject("LEGACY_BAD_FIELD", f"{name} must be text")
    if value == "":
        _reject("LEGACY_EMPTY_FIELD", f"{name} is required and cannot be empty")
    if "\n" in value or "\r" in value or "\x00" in value:
        _reject("LEGACY_MULTILINE_FIELD", f"{name} is one inert data line")
    if len(value.encode("utf-8")) > limit:
        _reject("LEGACY_FIELD_OVERSIZE", f"{name} exceeds {limit} UTF-8 bytes")
    return value


def _refs(values: Iterable[str], name: str, *, allow_zero: bool = False) -> Tuple[str, ...]:
    if isinstance(values, str):
        _reject("LEGACY_BAD_EVIDENCE", f"{name} must be an immutable reference collection")
    try:
        result = tuple(values)
    except TypeError:
        _reject("LEGACY_BAD_EVIDENCE", f"{name} must be a reference collection")
    if not result and not allow_zero:
        _reject("LEGACY_EVIDENCE_REQUIRED", f"{name} requires at least one content reference")
    for ref in result:
        if not isinstance(ref, str) or not _REF_RE.fullmatch(ref):
            _reject("LEGACY_BAD_EVIDENCE_REF",
                    f"{name} accepts only sha256:<64 lowercase hex> references")
    if len(set(result)) != len(result):
        _reject("LEGACY_DUPLICATE_EVIDENCE", f"{name} contains a duplicate reference")
    if result != tuple(sorted(result)):
        _reject("LEGACY_EVIDENCE_ORDER", f"{name} references must be bytewise sorted")
    return result


def _parse_ref_field(value: str, name: str, *, allow_zero: bool = False) -> Tuple[str, ...]:
    if allow_zero and value == "0":
        return ()
    if value == "0" or value == "":
        _reject("LEGACY_EVIDENCE_REQUIRED", f"{name} requires canonical content references")
    return _refs(value.split(","), name, allow_zero=allow_zero)


@dataclass(frozen=True)
class EvidenceReference:
    section: str
    ref: str
    state: str


@dataclass(frozen=True)
class LegacyPacket:
    """One immutable canonical predecessor account; its prose is inert data."""

    subject: str
    observed_scope: str
    what_worked: str
    what_worked_evidence: Tuple[str, ...]
    what_failed: str
    what_failed_evidence: Tuple[str, ...]
    what_looked_right_but_was_wrong: str
    what_wrong_evidence: Tuple[str, ...]
    watch_next: str
    watch_next_evidence: Tuple[str, ...]
    watch_next_status: str
    created: str

    def __post_init__(self) -> None:
        _text(self.subject, "SUBJECT", limit=MAX_SUBJECT_BYTES)
        if not _SUBJECT_RE.fullmatch(self.subject):
            _reject("LEGACY_BAD_SUBJECT",
                    "SUBJECT is lowercase letters/digits/hyphens with no path or wildcard syntax")
        for name, value in (
            ("OBSERVED_SCOPE", self.observed_scope),
            ("WHAT_WORKED", self.what_worked),
            ("WHAT_FAILED", self.what_failed),
            ("WHAT_LOOKED_RIGHT_BUT_WAS_WRONG", self.what_looked_right_but_was_wrong),
            ("WATCH_NEXT", self.watch_next),
        ):
            _text(value, name)
        object.__setattr__(self, "what_worked_evidence",
                           _refs(self.what_worked_evidence, "WHAT_WORKED_EVIDENCE"))
        object.__setattr__(self, "what_failed_evidence",
                           _refs(self.what_failed_evidence, "WHAT_FAILED_EVIDENCE"))
        object.__setattr__(self, "what_wrong_evidence",
                           _refs(self.what_wrong_evidence, "WHAT_WRONG_EVIDENCE"))
        object.__setattr__(self, "watch_next_evidence",
                           _refs(self.watch_next_evidence, "WATCH_NEXT_EVIDENCE",
                                 allow_zero=True))
        for name, refs in (
            ("WHAT_WORKED_EVIDENCE", self.what_worked_evidence),
            ("WHAT_FAILED_EVIDENCE", self.what_failed_evidence),
            ("WHAT_WRONG_EVIDENCE", self.what_wrong_evidence),
            ("WATCH_NEXT_EVIDENCE", self.watch_next_evidence),
        ):
            rendered = ",".join(refs) if refs else "0"
            if len(rendered.encode("utf-8")) > MAX_FIELD_BYTES:
                _reject("LEGACY_FIELD_OVERSIZE", f"{name} exceeds {MAX_FIELD_BYTES} UTF-8 bytes")
        if self.watch_next_status != WATCH_NEXT_UNVERIFIED:
            _reject("LEGACY_BAD_WATCH_STATUS", "v0 WATCH_NEXT_STATUS is exactly UNVERIFIED")
        _valid_utc(self.created)
        if len(self.render()) > MAX_PACKET_BYTES:
            _reject("LEGACY_PACKET_OVERSIZE", f"LEG1 exceeds {MAX_PACKET_BYTES} bytes")

    @classmethod
    def parse(cls, data: bytes) -> "LegacyPacket":
        if not isinstance(data, bytes):
            _reject("LEGACY_NOT_BYTES", "LEG1 input must be exact bytes")
        if len(data) > MAX_PACKET_BYTES:
            _reject("LEGACY_PACKET_OVERSIZE", f"LEG1 exceeds {MAX_PACKET_BYTES} bytes")
        if data.startswith(b"\xef\xbb\xbf"):
            _reject("LEGACY_NONCANONICAL", "UTF-8 BOM is not part of LEG1")
        if not data.endswith(b"\n") or b"\r" in data or b"\x00" in data:
            _reject("LEGACY_NONCANONICAL", "LEG1 is LF-only with one final LF and no NUL")
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            _reject("LEGACY_BAD_UTF8", "LEG1 must be strict UTF-8")
        lines = text[:-1].split("\n")
        if not lines or lines[0] != FORMAT:
            _reject("LEGACY_BAD_FORMAT", "the first line must be LEG1")
        if len(lines) != len(_FIELDS) + 1:
            _reject("LEGACY_FIELD_SET", "LEG1 has a missing, duplicate, or unknown field")
        parsed = {}
        seen = set()
        for expected, line in zip(_FIELDS, lines[1:]):
            if ":" not in line:
                _reject("LEGACY_FIELD_SET", f"expected {expected}:<value>")
            name, value = line.split(":", 1)
            if name in seen:
                _reject("LEGACY_DUPLICATE_FIELD", f"duplicate field {name}")
            seen.add(name)
            if name != expected:
                code = "LEGACY_UNKNOWN_FIELD" if name not in _FIELDS else "LEGACY_FIELD_ORDER"
                _reject(code, f"expected {expected}, found {name}")
            parsed[name] = value
        packet = cls(
            subject=parsed["SUBJECT"],
            observed_scope=parsed["OBSERVED_SCOPE"],
            what_worked=parsed["WHAT_WORKED"],
            what_worked_evidence=_parse_ref_field(
                parsed["WHAT_WORKED_EVIDENCE"], "WHAT_WORKED_EVIDENCE"),
            what_failed=parsed["WHAT_FAILED"],
            what_failed_evidence=_parse_ref_field(
                parsed["WHAT_FAILED_EVIDENCE"], "WHAT_FAILED_EVIDENCE"),
            what_looked_right_but_was_wrong=parsed["WHAT_LOOKED_RIGHT_BUT_WAS_WRONG"],
            what_wrong_evidence=_parse_ref_field(
                parsed["WHAT_WRONG_EVIDENCE"], "WHAT_WRONG_EVIDENCE"),
            watch_next=parsed["WATCH_NEXT"],
            watch_next_evidence=_parse_ref_field(
                parsed["WATCH_NEXT_EVIDENCE"], "WATCH_NEXT_EVIDENCE", allow_zero=True),
            watch_next_status=parsed["WATCH_NEXT_STATUS"],
            created=parsed["CREATED"],
        )
        if packet.render() != data:
            _reject("LEGACY_NONCANONICAL", "LEG1 bytes do not equal canonical rendering")
        return packet

    def render(self) -> bytes:
        values = (
            self.subject,
            self.observed_scope,
            self.what_worked,
            ",".join(self.what_worked_evidence),
            self.what_failed,
            ",".join(self.what_failed_evidence),
            self.what_looked_right_but_was_wrong,
            ",".join(self.what_wrong_evidence),
            self.watch_next,
            ",".join(self.watch_next_evidence) if self.watch_next_evidence else "0",
            self.watch_next_status,
            self.created,
        )
        lines = [FORMAT] + [f"{name}:{value}" for name, value in zip(_FIELDS, values)]
        return ("\n".join(lines) + "\n").encode("utf-8")

    @property
    def id(self) -> str:
        return "sha256:" + hashlib.sha256(self.render()).hexdigest()

    def evidence_reference_states(
        self, resolver: Optional[Callable[[str], bool]] = None
    ) -> Tuple[EvidenceReference, ...]:
        """Report citation availability without claiming evidentiary support."""
        groups = (
            ("WHAT_WORKED", self.what_worked_evidence),
            ("WHAT_FAILED", self.what_failed_evidence),
            ("WHAT_LOOKED_RIGHT_BUT_WAS_WRONG", self.what_wrong_evidence),
            ("WATCH_NEXT", self.watch_next_evidence),
        )
        out = []
        for section, refs in groups:
            for ref in refs:
                state = REFERENCED if resolver is None else (RESOLVED if resolver(ref) else UNRESOLVED)
                out.append(EvidenceReference(section, ref, state))
        return tuple(out)


def legacy_entry_id(source_envelope_id: str, packet: LegacyPacket) -> str:
    if not isinstance(source_envelope_id, str) or not _REF_RE.fullmatch(source_envelope_id):
        _reject("LEGACY_BAD_SOURCE_ENVELOPE", "source ENVELOPE_ID must be sha256:<64 hex>")
    if not isinstance(packet, LegacyPacket):
        _reject("NOT_A_LEGACY_PACKET", "entry identity requires LegacyPacket")
    material = (_ENTRY_DOMAIN + source_envelope_id.encode("ascii") + b"\x00" + packet.render())
    return "sha256:" + hashlib.sha256(material).hexdigest()


_AUTHENTICATED = object()


@dataclass(frozen=True)
class AuthenticatedLegacy:
    """Payload-bound adoption proof minted only from one OpenedEnvelope."""

    packet: LegacyPacket
    source_envelope_id: str
    source_from: str
    source_from_kid: str
    recipient: str
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _AUTHENTICATED:
            _reject("UNAUTHENTICATED_LEGACY",
                    "AuthenticatedLegacy is minted only from an exact OpenedEnvelope payload")

    @property
    def entry_id(self) -> str:
        return legacy_entry_id(self.source_envelope_id, self.packet)


def authenticate_legacy(opened: envelope.OpenedEnvelope,
                        packet: LegacyPacket) -> AuthenticatedLegacy:
    """Bind canonical LEG1 bytes to authenticated transport provenance."""
    if not isinstance(opened, envelope.OpenedEnvelope):
        _reject("LEGACY_REQUIRES_OPENED_ENVELOPE",
                "raw bytes, Header, and VerifiedEnvelope cannot authenticate LEGACY")
    if not isinstance(packet, LegacyPacket):
        _reject("NOT_A_LEGACY_PACKET", "adoption requires a parsed LegacyPacket")
    parsed = LegacyPacket.parse(opened.plaintext)
    if parsed.render() != packet.render():
        _reject("LEGACY_PAYLOAD_MISMATCH",
                "the supplied packet is not the exact OpenedEnvelope plaintext")
    header = opened.verified.header
    if header.get("K") != LEGACY_KIND:
        _reject("LEGACY_WRONG_KIND", "authenticated adoption requires SENV K=EXPERIENCE")
    if header.get("TOPIC") != LEGACY_TOPIC:
        _reject("LEGACY_WRONG_TOPIC", "authenticated adoption requires SENV TOPIC=legacy")
    return AuthenticatedLegacy(
        packet=parsed,
        source_envelope_id=opened.envelope_id,
        source_from=header.get("FROM"),
        source_from_kid=header.get("FROM_KID"),
        recipient=header.get("TO"),
        binding=_AUTHENTICATED,
    )


@dataclass(frozen=True)
class LegacyProvenance:
    schema: int
    legacy_entry_id: str
    legacy_content_id: str
    source_envelope_id: str
    source_from: str
    source_from_kid: str
    recipient: str
    received_at: str
    adopted_at: str


_VALIDATED_ENTRY = object()


@dataclass(frozen=True)
class LegacyEntry:
    """Store-validated packet/provenance pair.

    Only :meth:`LegacyStore._read_entry` may mint this state, after canonical
    packet/provenance bytes, directory identity, content/entry identities and
    the receiver-owned source index all agree.  The constructor-only mint is
    deliberately not retained, so ``dataclasses.replace`` cannot transplant
    validated provenance onto different content (the established T-40
    pattern).  This is normal-public-API correctness, not hostile-process
    security.
    """

    packet: LegacyPacket
    provenance: LegacyProvenance
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _VALIDATED_ENTRY:
            _reject("UNVERIFIED_LEGACY_ENTRY",
                    "LegacyEntry is minted only by LegacyStore after durable validation")

    @property
    def entry_id(self) -> str:
        return self.provenance.legacy_entry_id


@dataclass(frozen=True)
class AdoptionResult:
    status: str
    entry: LegacyEntry
    path: Path


def _canonical_json(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n").encode("utf-8")


def _parse_provenance(data: bytes) -> LegacyProvenance:
    try:
        text = data.decode("utf-8", errors="strict")
        raw = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        _reject(LEGACY_ENTRY_CORRUPT, "provenance.json is not canonical UTF-8 JSON")
    if not isinstance(raw, dict) or set(raw) != _PROVENANCE_KEYS or _canonical_json(raw) != data:
        _reject(LEGACY_ENTRY_CORRUPT, "provenance.json field set or bytes are noncanonical")
    if raw["schema"] != 1:
        _reject(LEGACY_ENTRY_CORRUPT, "unknown legacy provenance schema")
    for name in ("legacy_entry_id", "legacy_content_id", "source_envelope_id"):
        if not isinstance(raw[name], str) or not _REF_RE.fullmatch(raw[name]):
            _reject(LEGACY_ENTRY_CORRUPT, f"provenance {name} is not a content identity")
    for name in ("source_from", "recipient"):
        if not isinstance(raw[name], str) or not _SEAT_RE.fullmatch(raw[name]):
            _reject(LEGACY_ENTRY_CORRUPT, f"provenance {name} is not a seat token")
    if not isinstance(raw["source_from_kid"], str) or not _REF_RE.fullmatch(raw["source_from_kid"]):
        _reject(LEGACY_ENTRY_CORRUPT, "provenance source_from_kid is not a full fingerprint")
    _valid_utc(raw["received_at"], code=LEGACY_ENTRY_CORRUPT)
    _valid_utc(raw["adopted_at"], code=LEGACY_ENTRY_CORRUPT)
    return LegacyProvenance(**raw)


class LegacyStore:
    """Explicit immutable store under one receiver-owned PostOffice root."""

    def __init__(self, office: PostOffice):
        if not isinstance(office, PostOffice):
            _reject("NOT_A_POST_OFFICE", "LegacyStore requires the receiver's PostOffice")
        self.office = office
        self.root = office.mail_root / "legacy" / office.seat
        self.root.mkdir(parents=True, exist_ok=True)

    def entry_path(self, entry_id: str) -> Path:
        if not isinstance(entry_id, str) or not _REF_RE.fullmatch(entry_id):
            _reject("LEGACY_BAD_ENTRY_ID", "legacy entry id must be sha256:<64 hex>")
        return self.root / entry_id.split(":", 1)[1]

    def _read_entry(self, directory: Path) -> LegacyEntry:
        if not directory.is_dir() or not re.fullmatch(r"[0-9a-f]{64}", directory.name):
            _reject(LEGACY_ENTRY_CORRUPT, f"{directory.name!r} is not a legacy entry directory")
        try:
            packet_bytes = (directory / "packet.leg1").read_bytes()
            provenance_bytes = (directory / "provenance.json").read_bytes()
        except OSError as exc:
            _reject(LEGACY_ENTRY_CORRUPT,
                    f"legacy entry {directory.name} is incomplete ({type(exc).__name__})")
        packet = LegacyPacket.parse(packet_bytes)
        provenance = _parse_provenance(provenance_bytes)
        expected_entry_id = legacy_entry_id(provenance.source_envelope_id, packet)
        path_entry_id = "sha256:" + directory.name
        if (provenance.legacy_content_id != packet.id
                or provenance.legacy_entry_id != expected_entry_id
                or path_entry_id != expected_entry_id):
            _reject(LEGACY_ENTRY_CORRUPT, "packet, provenance, and entry path identities disagree")
        row = self.office.read_index_row(provenance.source_envelope_id)
        if row is None:
            _reject(LEGACY_ENTRY_CORRUPT,
                    "legacy provenance names no receiver-owned source index row")
        expected_source = {
            "from": provenance.source_from,
            "from_kid": provenance.source_from_kid,
            "to": provenance.recipient,
            "received_at": provenance.received_at,
            "kind": LEGACY_KIND,
            "topic": LEGACY_TOPIC,
        }
        if provenance.recipient != self.office.seat \
                or any(row.get(key) != value for key, value in expected_source.items()):
            _reject(LEGACY_ENTRY_CORRUPT,
                    "legacy provenance disagrees with the receiver-owned source index")
        return LegacyEntry(packet, provenance, binding=_VALIDATED_ENTRY)

    def adopt(self, authenticated: AuthenticatedLegacy) -> AdoptionResult:
        """Explicitly publish one authenticated packet; opening alone never calls this."""
        if not isinstance(authenticated, AuthenticatedLegacy):
            _reject("LEGACY_REQUIRES_AUTHENTICATED",
                    "durable adoption requires the payload-bound AuthenticatedLegacy proof")
        if authenticated.recipient != self.office.seat:
            _reject("LEGACY_WRONG_RECIPIENT", "legacy proof belongs to another receiver seat")
        row = self.office.read_index_row(authenticated.source_envelope_id)
        if row is None:
            _reject("LEGACY_SOURCE_NOT_RECEIVED",
                    "the receiver-owned index has no source envelope provenance")
        expected_row = {
            "envelope_id": authenticated.source_envelope_id,
            "from": authenticated.source_from,
            "from_kid": authenticated.source_from_kid,
            "to": authenticated.recipient,
            "kind": LEGACY_KIND,
            "topic": LEGACY_TOPIC,
        }
        if any(row.get(key) != value for key, value in expected_row.items()):
            _reject("LEGACY_SOURCE_CONFLICT",
                    "OpenedEnvelope provenance disagrees with the receiver-owned index")

        entry_id = authenticated.entry_id
        directory = self.entry_path(entry_id)
        packet_path = directory / "packet.leg1"
        provenance_path = directory / "provenance.json"
        if packet_path.is_file() and provenance_path.is_file():
            if packet_path.read_bytes() != authenticated.packet.render():
                _reject(LEGACY_ENTRY_CONFLICT,
                        "committed packet.leg1 differs at this entry identity; no overwrite")
            existing = self._read_entry(directory)
            self._require_same_adoption(existing, authenticated, row["received_at"])
            return AdoptionResult(ALREADY_ADOPTED, existing, directory)

        directory.mkdir(parents=True, exist_ok=True)
        packet_outcome = publish.publish_immutable(
            packet_path, authenticated.packet.render(), conflict_code=LEGACY_ENTRY_CONFLICT)
        if provenance_path.is_file():
            existing = self._read_entry(directory)
            self._require_same_adoption(existing, authenticated, row["received_at"])
            return AdoptionResult(ALREADY_ADOPTED, existing, directory)

        adopted_at = self.office.clock()
        _valid_utc(adopted_at, code="LEGACY_BAD_ADOPTION_TIME")
        raw = {
            "schema": 1,
            "legacy_entry_id": entry_id,
            "legacy_content_id": authenticated.packet.id,
            "source_envelope_id": authenticated.source_envelope_id,
            "source_from": authenticated.source_from,
            "source_from_kid": authenticated.source_from_kid,
            "recipient": authenticated.recipient,
            "received_at": row["received_at"],
            "adopted_at": adopted_at,
        }
        try:
            publish.publish_immutable(
                provenance_path, _canonical_json(raw), conflict_code=LEGACY_ENTRY_CONFLICT)
        except SailangError as exc:
            # Concurrent exact adoption may choose a different receiver-local
            # adoption instant. The first immutable provenance wins; prove all
            # identity-bearing fields, then converge without rewriting it.
            if exc.code != LEGACY_ENTRY_CONFLICT:
                raise
            existing = self._read_entry(directory)
            self._require_same_adoption(existing, authenticated, row["received_at"])
            return AdoptionResult(ALREADY_ADOPTED, existing, directory)
        entry = self._read_entry(directory)
        status = ADOPTED if packet_outcome == publish.PUBLISHED else ALREADY_ADOPTED
        return AdoptionResult(status, entry, directory)

    @staticmethod
    def _require_same_adoption(entry: LegacyEntry, authenticated: AuthenticatedLegacy,
                               received_at: str) -> None:
        p = entry.provenance
        if (entry.packet.render() != authenticated.packet.render()
                or p.legacy_entry_id != authenticated.entry_id
                or p.legacy_content_id != authenticated.packet.id
                or p.source_envelope_id != authenticated.source_envelope_id
                or p.source_from != authenticated.source_from
                or p.source_from_kid != authenticated.source_from_kid
                or p.recipient != authenticated.recipient
                or p.received_at != received_at):
            _reject(LEGACY_ENTRY_CONFLICT,
                    "committed legacy entry differs from this adoption; no overwrite")

    def all(self) -> Tuple[LegacyEntry, ...]:
        entries = []
        for path in self.root.iterdir():
            if path.name.startswith("."):
                continue
            entries.append(self._read_entry(path))
        return tuple(sorted(entries, key=_entry_order_key, reverse=True))

    def for_subject(self, subject: str) -> Tuple[LegacyEntry, ...]:
        _text(subject, "SUBJECT", limit=MAX_SUBJECT_BYTES)
        if not _SUBJECT_RE.fullmatch(subject):
            _reject("LEGACY_BAD_SUBJECT", "retrieval uses one exact machine subject token")
        return tuple(entry for entry in self.all() if entry.packet.subject == subject)

    def build_successor_context(self, subject: str, new_task_scope: str, **bounds):
        return render_successor_context(
            self.for_subject(subject), new_task_scope=new_task_scope, subject=subject, **bounds)


@dataclass(frozen=True)
class SuccessorContext:
    data: bytes
    total_matches: int
    included_entries: int
    truncated: bool
    continuation: Optional[str]
    max_entries: int
    max_total_bytes: int

    def text(self) -> str:
        return self.data.decode("utf-8")


def _entry_block(entry: LegacyEntry) -> str:
    packet = entry.packet
    return "\n".join((
        "ENTRY_BEGIN",
        f"LEGACY_ENTRY_ID:{entry.entry_id}",
        f"SOURCE_ENVELOPE_ID:{entry.provenance.source_envelope_id}",
        f"SOURCE_FROM:{entry.provenance.source_from}",
        f"CREATED:{packet.created}",
        f"OBSERVED_SCOPE:{packet.observed_scope}",
        f"WHAT_WORKED:{packet.what_worked}",
        "WHAT_WORKED_EVIDENCE:" + ",".join(packet.what_worked_evidence),
        "WHAT_FAILED_STATUS:FAILED_IN_OBSERVED_SCOPE",
        f"WHAT_FAILED:{packet.what_failed}",
        "WHAT_FAILED_EVIDENCE:" + ",".join(packet.what_failed_evidence),
        f"WHAT_LOOKED_RIGHT_BUT_WAS_WRONG:{packet.what_looked_right_but_was_wrong}",
        "WHAT_WRONG_EVIDENCE:" + ",".join(packet.what_wrong_evidence),
        f"WATCH_NEXT:{packet.watch_next}",
        ("WATCH_NEXT_EVIDENCE:" + ",".join(packet.watch_next_evidence)
         if packet.watch_next_evidence else "WATCH_NEXT_EVIDENCE:0"),
        f"WATCH_NEXT_STATUS:{WATCH_NEXT_UNVERIFIED}",
        "ENTRY_END",
    )) + "\n"


def _entry_order_key(entry: LegacyEntry) -> Tuple[str, str]:
    """Receiver-owned recency, then immutable identity (D-041)."""
    return entry.provenance.received_at, entry.entry_id


def render_successor_context(
    legacy_entries: Iterable[LegacyEntry], *, new_task_scope: str,
    subject: Optional[str] = None, max_entries: int = DEFAULT_MAX_ENTRIES,
    max_total_bytes: int = DEFAULT_MAX_RENDERED_BYTES,
    continuation: Optional[str] = None,
) -> SuccessorContext:
    """Render bounded keyset pages; no commands, tasks, models, or synthesis.

    ``continuation`` is the last included durable entry identity, never an
    offset into a mutable set. ``TOTAL_MATCHES`` describes the current input
    set; entries inserted ahead of an anchor require a fresh request (D-041).
    """
    entries = tuple(legacy_entries)
    if any(not isinstance(entry, LegacyEntry) for entry in entries):
        _reject("NOT_A_LEGACY_ENTRY", "successor rendering accepts durable LegacyEntry values")
    entries = tuple(sorted(entries, key=_entry_order_key, reverse=True))
    _text(new_task_scope, "NEW_TASK_SCOPE")
    if subject is None:
        subjects = {entry.packet.subject for entry in entries}
        if len(subjects) > 1:
            _reject("LEGACY_SUBJECT_MIX", "one successor context has one exact subject")
        subject = next(iter(subjects), "none")
    elif subject != "none":
        _text(subject, "SUBJECT", limit=MAX_SUBJECT_BYTES)
        if not _SUBJECT_RE.fullmatch(subject):
            _reject("LEGACY_BAD_SUBJECT", "successor subject is one exact machine token")
    if not isinstance(max_entries, int) or isinstance(max_entries, bool) or max_entries < 1:
        _reject("LEGACY_BAD_ENTRY_BOUND", "max_entries must be a positive integer")
    if not isinstance(max_total_bytes, int) or isinstance(max_total_bytes, bool) \
            or max_total_bytes < 256:
        _reject("LEGACY_BAD_BYTE_BOUND", "max_total_bytes must be an integer of at least 256")
    if continuation is not None \
            and (not isinstance(continuation, str) or not _REF_RE.fullmatch(continuation)):
        _reject("LEGACY_BAD_CONTINUATION",
                "continuation must be the last included legacy_entry_id")
    for entry in entries:
        if subject != "none" and entry.packet.subject != subject:
            _reject("LEGACY_SUBJECT_MIX", "an entry does not match the context subject")

    start = 0
    if continuation is not None:
        anchor = next((index for index, entry in enumerate(entries)
                       if entry.entry_id == continuation), None)
        if anchor is None:
            _reject("LEGACY_BAD_CONTINUATION",
                    "continuation entry is unknown or does not belong to this exact subject")
        start = anchor + 1

    def assemble(selected: Tuple[LegacyEntry, ...]) -> Tuple[bytes, bool, Optional[str]]:
        next_index = start + len(selected)
        truncated = next_index < len(entries)
        cursor = selected[-1].entry_id if truncated and selected else None
        header = "\n".join((
            "LEGACY_SUCCESSOR_CONTEXT1",
            f"SUBJECT:{subject}",
            f"NEW_TASK_SCOPE:{new_task_scope}",
            "AUTHORITY_GAIN:NONE",
            "EVIDENCE_SEMANTICS:REFERENCES_NOT_PROOF",
            f"TOTAL_MATCHES:{len(entries)}",
            f"AFTER_ENTRY:{continuation if continuation is not None else 'NONE'}",
            f"MAX_ENTRIES:{max_entries}",
            f"MAX_TOTAL_BYTES:{max_total_bytes}",
            f"INCLUDED_ENTRIES:{len(selected)}",
            f"TRUNCATED:{'YES' if truncated else 'NO'}",
            f"CONTINUATION:{cursor if cursor is not None else 'NONE'}",
        )) + "\n"
        return (header + "".join(_entry_block(item) for item in selected)).encode("utf-8"), \
            truncated, cursor

    selected: Tuple[LegacyEntry, ...] = ()
    base, truncated, cursor = assemble(selected)
    if len(base) > max_total_bytes:
        _reject("LEGACY_CONTEXT_BOUND_TOO_SMALL",
                "max_total_bytes cannot hold even explicit context metadata")
    limit = min(len(entries), start + max_entries)
    for end in range(start + 1, limit + 1):
        candidate = entries[start:end]
        rendered, candidate_truncated, candidate_cursor = assemble(candidate)
        if len(rendered) > max_total_bytes:
            break
        selected = candidate
        base, truncated, cursor = rendered, candidate_truncated, candidate_cursor
    if truncated and not selected:
        _reject(LEGACY_CONTEXT_ENTRY_TOO_LARGE,
                "the next complete legacy entry cannot fit max_total_bytes; increase the bound")
    return SuccessorContext(base, len(entries), len(selected), truncated, cursor,
                            max_entries, max_total_bytes)


def build_successor_context(subject: str, new_task_scope: str, *, store: LegacyStore,
                            **bounds) -> SuccessorContext:
    """Narrow future-SAIPEN seam: exact retrieval in, immutable data out."""
    if not isinstance(store, LegacyStore):
        _reject("NOT_A_LEGACY_STORE", "successor context requires LegacyStore")
    return store.build_successor_context(subject, new_task_scope, **bounds)


__all__ = [
    "ADOPTED", "ALREADY_ADOPTED", "AuthenticatedLegacy", "AdoptionResult",
    "EvidenceReference", "LEGACY_CONTEXT_ENTRY_TOO_LARGE", "LegacyEntry",
    "LegacyPacket", "LegacyProvenance",
    "LegacyStore", "REFERENCED", "RESOLVED", "SuccessorContext", "UNRESOLVED",
    "WATCH_NEXT_UNVERIFIED", "authenticate_legacy", "build_successor_context",
    "legacy_entry_id", "render_successor_context",
]
