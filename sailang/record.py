"""Canonical SAILANG v0 record: parse, validate, serialize, identify.

DATA ONLY. This module reads text and returns text. It executes nothing,
routes nothing, imports no network or subprocess machinery, and writes no
protocol state. A record that contains the words ``ignore protocol`` is a
record containing those words (spec/01-SAILANG-v0.md section 6).

Normative spec: spec/01-SAILANG-v0.md, corrected by spec/DECISIONS.md
D-001 (no motive field), D-003 (sha256 identity, immutability),
D-004 (kind matrix, no ``D`` kind), D-008 (``C``/``D`` are ledger verdicts).
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from .errors import SailangError

MARKER = "SAIL1"
FORMAT_VERSION = "v0"

#: Canonical field order. Serialization follows it exactly; parsing requires
#: input to be a strictly increasing subsequence of it, which is also what
#: makes an injected field line detectable.
FIELD_ORDER = (
    "ID",
    "KIND",
    "SRC",
    "SUBJ",
    "CLAIM",
    "TYPE",
    "FALSIFY",
    "EV",
    "STATUS",
    "DIRECTNESS",
    "INDEPENDENCE",
    "INTEGRITY",
    "FRESHNESS",
    "INTEREST_REF",
    "CON",
    "REFUTES",
    "SUPPORTS",
    "CREATED",
)
_ORDER_INDEX = {key: i for i, key in enumerate(FIELD_ORDER)}

KINDS = ("F", "O", "H", "G", "V")
#: Kinds deliberately deferred out of v0, mapped to the decision that did it.
DEFERRED_KINDS = {"D": "D-004"}
TYPES = ("OBS", "MEM", "INT")
SRC_CLASSES = ("HUMAN", "FS", "NET", "TEST", "LOG", "GIT", "AGENT", "PROTO", "UNKNOWN")
#: Author rungs. ``C``/``D`` are ledger verdicts and never appear here (D-008).
RUNGS = ("U0", "U1", "U2", "U3", "U4")
LEDGER_VERDICTS = ("C", "D")
GRADES = ("HIGH", "MED", "LOW")

EVIDENCE_ATTACHED = "EVIDENCE_ATTACHED"
EVIDENCE_EXPLICITLY_ABSENT = "EVIDENCE_EXPLICITLY_ABSENT"
EVIDENCE_NOT_APPLICABLE = "EVIDENCE_NOT_APPLICABLE"
EVIDENCE_STATES = (EVIDENCE_ATTACHED, EVIDENCE_EXPLICITLY_ABSENT, EVIDENCE_NOT_APPLICABLE)

REQUIRED_ALWAYS = ("KIND", "SRC", "CLAIM", "CREATED")

#: Fields removed from the format, mapped to the decision that removed them.
REMOVED_FIELDS = {"INCENTIVE": "D-001"}
#: Fields reserved against a future that has not earned them yet.
RESERVED_FIELDS = {
    "PCONF": "numeric confidence stays banned until a calibration sample exists "
    "(00-PRINCIPLES section 6)"
}

#: Assessment machinery. Forbidden on G/V: a goal or a value is not truth-apt.
ASSESSMENT_FIELDS = frozenset(
    {
        "TYPE",
        "FALSIFY",
        "EV",
        "STATUS",
        "DIRECTNESS",
        "INDEPENDENCE",
        "INTEGRITY",
        "FRESHNESS",
        "INTEREST_REF",
        "CON",
        "REFUTES",
        "SUPPORTS",
    }
)

# `EV` is required for truth-apt kinds (D-009): omission must not quietly mean
# "no evidence" on the author's behalf.
_KIND_RULES = {
    "F": {"required": ("TYPE", "EV", "STATUS"), "forbidden": ("FALSIFY",), "max_rung": "U4", "src_id": False},
    "O": {"required": ("TYPE", "EV", "STATUS"), "forbidden": ("FALSIFY",), "max_rung": "U4", "src_id": True},
    "H": {"required": ("TYPE", "EV", "STATUS", "FALSIFY"), "forbidden": (), "max_rung": "U3", "src_id": False},
    "G": {"required": (), "forbidden": tuple(sorted(ASSESSMENT_FIELDS)), "max_rung": None, "src_id": False},
    "V": {"required": (), "forbidden": tuple(sorted(ASSESSMENT_FIELDS)), "max_rung": None, "src_id": False},
}

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_SINGLE_REF_FIELDS = ("CON", "REFUTES", "SUPPORTS")
_MULTI_REF_FIELDS = ("EV", "INTEREST_REF")
_GRADE_FIELDS = ("DIRECTNESS", "INDEPENDENCE", "INTEGRITY")

#: Character classes rejected inside any value. ``Cc`` covers TAB and every
#: other control; ``Zl``/``Zp`` are the Unicode line/paragraph separators that
#: some line splitters treat as newlines. ``Cf`` (ZWJ and friends) is allowed
#: so that emoji sequences and bidi-bearing scripts survive intact.
_BAD_CATEGORIES = frozenset({"Cc", "Zl", "Zp"})
_BOM = "﻿"


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _check_value_text(key: str, value: str) -> None:
    if value == "":
        _reject("EMPTY_VALUE", f"{key} has an empty value")
    if value != value.strip():
        _reject("VALUE_WHITESPACE", f"{key} has leading or trailing whitespace; no silent trimming")
    for ch in value:
        if ch == _BOM or unicodedata.category(ch) in _BAD_CATEGORIES:
            _reject(
                "VALUE_CONTROL_CHAR",
                f"{key} contains U+{ord(ch):04X}, which is a control or line separator",
            )


def _check_utc(key: str, value: str) -> None:
    if not _UTC_RE.match(value):
        _reject("BAD_UTC", f"{key} must be YYYY-MM-DDTHH:MM:SSZ, got {value!r}")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _reject("BAD_UTC", f"{key} is not a real UTC instant: {value!r}")


def _check_refs(key: str, value: str, multi: bool) -> None:
    parts = value.split(",") if multi else [value]
    if multi and len(parts) != len({p for p in parts}):
        _reject("DUPLICATE_REF", f"{key} repeats a reference")
    for part in parts:
        if not _HASH_RE.match(part):
            _reject(
                "BAD_REF",
                f"{key} must hold sha256:<64 lowercase hex>, got {part!r}; "
                "a shortened prefix is display only (D-003)",
            )


def _validate(fields: dict) -> tuple:
    """Validate a field mapping and return canonical ordered pairs."""
    for key in REQUIRED_ALWAYS:
        if key not in fields:
            _reject("MISSING_FIELD", f"{key} is required")

    kind = fields["KIND"]
    if kind in DEFERRED_KINDS:
        _reject(
            "KIND_DEFERRED",
            f"KIND {kind} is deferred out of v0 by {DEFERRED_KINDS[kind]}; "
            "host protocols own decision logs",
        )
    if kind not in KINDS:
        _reject("BAD_KIND", f"KIND must be one of {KINDS}, got {kind!r}")
    rules = _KIND_RULES[kind]

    src = fields["SRC"]
    src_class, _, src_id = src.partition(":")
    if src_class not in SRC_CLASSES:
        _reject("BAD_SRC", f"SRC class must be one of {SRC_CLASSES}, got {src_class!r}")
    if rules["src_id"] and not src_id:
        _reject(
            "OBSERVATION_CHANNEL_MISSING",
            "KIND O must name its observation channel as SRC:<CLASS>:<id> (D-004)",
        )

    for key in rules["required"]:
        if key not in fields:
            _reject("MISSING_FIELD", f"KIND {kind} requires {key}")
    for key in rules["forbidden"]:
        if key in fields:
            _reject(
                "FIELD_FORBIDDEN_FOR_KIND",
                f"KIND {kind} must not carry {key}: a goal or value is not truth-apt (D-004)"
                if kind in ("G", "V")
                else f"KIND {kind} must not carry {key}",
            )

    if "TYPE" in fields:
        if fields["TYPE"] not in TYPES:
            _reject("BAD_TYPE", f"TYPE must be one of {TYPES}, got {fields['TYPE']!r}")
        if kind == "O" and fields["TYPE"] != "OBS":
            _reject("BAD_TYPE", "KIND O requires TYPE:OBS")

    if "SUBJ" in fields and any(c.isspace() for c in fields["SUBJ"]):
        _reject("BAD_SUBJ", "SUBJ must be a single token with no whitespace")

    if "STATUS" in fields:
        status = fields["STATUS"]
        if status in LEDGER_VERDICTS:
            _reject(
                "LEDGER_VERDICT_IN_RECORD",
                f"STATUS {status} is a ledger verdict projected over REFUTES/CON edges "
                "and is never written into a record (D-008)",
            )
        if status not in RUNGS:
            _reject("BAD_STATUS", f"STATUS must be one of {RUNGS}, got {status!r}")
        max_rung = rules["max_rung"]
        if max_rung is not None and RUNGS.index(status) > RUNGS.index(max_rung):
            _reject(
                "RUNG_ABOVE_KIND_CEILING",
                f"KIND {kind} may not exceed {max_rung}; a verified hypothesis is "
                "restated as an F record citing its evidence (D-004)",
            )
        has_evidence = fields.get("EV", "0") != "0"  # EV presence is enforced above
        if not has_evidence and RUNGS.index(status) > RUNGS.index("U1"):
            _reject(
                "RUNG_WITHOUT_EVIDENCE",
                f"STATUS {status} with EV:0 is not allowed; no evidence caps the rung at U1",
            )

    if "EV" in fields and fields["EV"] != "0":
        _check_refs("EV", fields["EV"], multi=True)
    for key in _MULTI_REF_FIELDS:
        if key != "EV" and key in fields:
            _check_refs(key, fields[key], multi=True)
    for key in _SINGLE_REF_FIELDS:
        if key in fields:
            _check_refs(key, fields[key], multi=False)
    for key in _GRADE_FIELDS:
        if key in fields and fields[key] not in GRADES:
            _reject("BAD_GRADE", f"{key} must be one of {GRADES}, got {fields[key]!r}")

    _check_utc("CREATED", fields["CREATED"])
    if "FRESHNESS" in fields and fields["FRESHNESS"] != "STALE":
        _check_utc("FRESHNESS", fields["FRESHNESS"])

    return tuple((key, fields[key]) for key in FIELD_ORDER if key != "ID" and key in fields)


@dataclass(frozen=True)
class Record:
    """An immutable, content-addressed SAILANG statement.

    There is no mutator, by design (D-003). Re-assessment emits a new record
    that references this one through SUPPORTS / REFUTES / CON.
    """

    pairs: tuple

    # -- construction -------------------------------------------------

    @classmethod
    def create(cls, **fields: str) -> "Record":
        """Build a record from field values. ``ID`` is derived, never passed."""
        if "ID" in fields:
            _reject("ID_NOT_AUTHORABLE", "ID is derived from the record bytes and is never supplied")
        for key, value in fields.items():
            if not _KEY_RE.match(key):
                _reject("BAD_KEY", f"{key!r} is not a field name")
            if key in REMOVED_FIELDS:
                _reject(
                    "FIELD_REMOVED",
                    f"{key} was removed from the format by {REMOVED_FIELDS[key]}; "
                    "no free-text motive field exists",
                )
            if key in RESERVED_FIELDS:
                _reject("FIELD_RESERVED", f"{key} is reserved: {RESERVED_FIELDS[key]}")
            if key not in _ORDER_INDEX:
                _reject("UNKNOWN_FIELD", f"{key} is not a SAILANG v0 field")
            if not isinstance(value, str):
                _reject("NON_TEXT_VALUE", f"{key} must be a string")
            _check_value_text(key, value)
        return cls(_validate(dict(fields)))

    # -- access -------------------------------------------------------

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        for k, v in self.pairs:
            if k == key:
                return v
        return default

    def __contains__(self, key: object) -> bool:
        return any(k == key for k, _ in self.pairs)

    def keys(self) -> Iterable[str]:
        return tuple(k for k, _ in self.pairs)

    @property
    def kind(self) -> str:
        return self.get("KIND")

    @property
    def claim(self) -> str:
        return self.get("CLAIM")

    @property
    def status(self) -> Optional[str]:
        return self.get("STATUS")

    @property
    def evidence_state(self) -> str:
        if self.kind in ("G", "V") or "EV" not in self:
            return EVIDENCE_NOT_APPLICABLE
        return EVIDENCE_ATTACHED if self.get("EV") != "0" else EVIDENCE_EXPLICITLY_ABSENT

    @property
    def has_evidence(self) -> Optional[bool]:
        """Optional[bool]: True if attached, False if explicitly absent, None if not applicable."""
        state = self.evidence_state
        if state == EVIDENCE_ATTACHED:
            return True
        if state == EVIDENCE_EXPLICITLY_ABSENT:
            return False
        return None

    @property
    def is_evidence_attached(self) -> bool:
        return self.evidence_state == EVIDENCE_ATTACHED

    @property
    def is_evidence_absent(self) -> bool:
        return self.evidence_state == EVIDENCE_EXPLICITLY_ABSENT

    @property
    def is_evidence_applicable(self) -> bool:
        return self.evidence_state != EVIDENCE_NOT_APPLICABLE

    # -- identity and bytes -------------------------------------------

    def hash_input(self) -> bytes:
        """Canonical bytes with the ID line removed. The ID hashes exactly this."""
        lines = [MARKER] + [f"{k}:{v}" for k, v in self.pairs]
        return ("\n".join(lines) + "\n").encode("utf-8")

    @property
    def content_id(self) -> str:
        return "sha256:" + hashlib.sha256(self.hash_input()).hexdigest()

    def short_id(self, length: int = 12) -> str:
        """A truncated id for human reading. Never accepted as identity (D-003)."""
        return self.content_id[len("sha256:") : len("sha256:") + length]

    def canonical_text(self) -> str:
        lines = [MARKER, f"ID:{self.content_id}"] + [f"{k}:{v}" for k, v in self.pairs]
        return "\n".join(lines) + "\n"

    def canonical_bytes(self) -> bytes:
        return self.canonical_text().encode("utf-8")


def parse(data) -> Record:
    """Parse canonical SAILANG text or UTF-8 bytes into a Record.

    CRLF input is normalized to LF, which is the only normalization this
    parser performs; a lone CR is rejected rather than repaired.
    """
    if isinstance(data, (bytes, bytearray)):
        if bytes(data[:3]) == b"\xef\xbb\xbf":
            _reject("BOM_PRESENT", "canonical SAILANG is UTF-8 without BOM")
        try:
            text = bytes(data).decode("utf-8")
        except UnicodeDecodeError as exc:
            _reject("NOT_UTF8", str(exc))
    elif isinstance(data, str):
        text = data
        if text.startswith(_BOM):
            _reject("BOM_PRESENT", "canonical SAILANG is UTF-8 without BOM")
    else:
        _reject("NON_TEXT_INPUT", f"cannot parse {type(data).__name__}")

    text = text.replace("\r\n", "\n")
    if "\r" in text:
        _reject("LONE_CR", "a bare CR is not a line terminator here")

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        _reject("EMPTY_INPUT", "no content")
    if lines[0] != MARKER:
        _reject("BAD_MARKER", f"line 1 must be exactly {MARKER!r}")

    fields: dict = {}
    last_index = -1
    for lineno, raw in enumerate(lines[1:], start=2):
        if raw == "":
            _reject("BLANK_LINE", f"line {lineno} is blank; canonical records have no blank lines")
        if ":" not in raw:
            _reject("MALFORMED_FIELD", f"line {lineno} is not KEY:VALUE")
        key, value = raw.split(":", 1)
        if not _KEY_RE.match(key):
            _reject("BAD_KEY", f"line {lineno}: {key!r} is not a field name")
        if key in REMOVED_FIELDS:
            _reject(
                "FIELD_REMOVED",
                f"line {lineno}: {key} was removed by {REMOVED_FIELDS[key]}",
            )
        if key in RESERVED_FIELDS:
            _reject("FIELD_RESERVED", f"line {lineno}: {key} is reserved: {RESERVED_FIELDS[key]}")
        if key not in _ORDER_INDEX:
            _reject("UNKNOWN_FIELD", f"line {lineno}: {key} is not a SAILANG v0 field")
        if key in fields:
            _reject("DUPLICATE_FIELD", f"line {lineno}: {key} appears twice")
        index = _ORDER_INDEX[key]
        if index <= last_index:
            _reject(
                "FIELD_ORDER",
                f"line {lineno}: {key} is out of canonical order, which is also how an "
                "injected field line is detected",
            )
        last_index = index
        _check_value_text(key, value)
        fields[key] = value

    claimed_id = fields.pop("ID", None)
    if claimed_id is None:
        _reject("MISSING_FIELD", "ID is required")
    if not _HASH_RE.match(claimed_id):
        _reject("BAD_ID", f"ID must be sha256:<64 lowercase hex>, got {claimed_id!r}")

    record = Record(_validate(fields))
    if record.content_id != claimed_id:
        _reject(
            "ID_MISMATCH",
            f"declared {claimed_id} but the record bytes hash to {record.content_id}",
        )
    return record
