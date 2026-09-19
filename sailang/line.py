"""SAILANG v0 line form: a lossy, deterministic triage projection.

One direction only. There is no line parser in this module and there must
never be one: the line is not authoritative, is never reconstructed into a
record and is never cited as evidence (spec/DECISIONS.md D-002).

Slots:

    L1D<dict>|KIND|SUBJ|STATUS|EV0|EV+|CLAIMTOK|FLAGS

``?`` in any slot means **OPEN RECORD** — the line cannot carry that fact, so
the reader must open the canonical record. It never means "probably".
"""

from __future__ import annotations

import json
import pathlib
import re
from typing import Mapping

from .errors import SailangError
from .record import Record

LINE_FORMAT = "L1"
SEPARATOR = "|"
#: The literal that means "this line cannot carry that fact; open the record".
OPEN_RECORD = "?"
#: The literal that means "this record has no such field at all".
ABSENT = "-"

_DICTIONARY_DIR = pathlib.Path(__file__).resolve().parent / "dictionary"

#: A claim is projectable only when it is ALREADY a compact claim token.
_CHAIN_RE = re.compile(r"^[A-Z0-9_]+(?:>[A-Z0-9_]+)*$")
_COMPARISON_RE = re.compile(r"^([A-Z0-9_]+)(>=|<=|!=|=)(\S+)$")

_FLAGS = (("REFUTES", "R"), ("SUPPORTS", "S"), ("CON", "C"), ("FALSIFY", "X"))


class Dictionary:
    """A versioned term table. Unknown segments are carried verbatim."""

    def __init__(self, version: str, terms: Mapping[str, str]) -> None:
        self.version = version
        self.terms = dict(terms)

    @classmethod
    def load(cls, version: str = "0") -> "Dictionary":
        path = _DICTIONARY_DIR / f"v{version}.json"
        if not path.is_file():
            raise SailangError("DICTIONARY_MISSING", f"no dictionary at {path}")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SailangError("DICTIONARY_MALFORMED", f"{path}: {exc}") from None
        if not isinstance(data, dict) or "version" not in data or "terms" not in data:
            raise SailangError("DICTIONARY_MALFORMED", f"{path}: missing version or terms")
        terms = data["terms"]
        if not isinstance(terms, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in terms.items()
        ):
            raise SailangError("DICTIONARY_MALFORMED", f"{path}: terms must be text to text")
        for key, value in terms.items():
            if not _CHAIN_RE.match(key) or not _CHAIN_RE.match(value):
                raise SailangError(
                    "DICTIONARY_MALFORMED",
                    f"{path}: {key!r} -> {value!r} is not a segment pair",
                )
        if str(data["version"]) != str(version):
            raise SailangError(
                "DICTIONARY_VERSION_MISMATCH",
                f"{path} declares version {data['version']!r}, loaded as {version!r}",
            )
        return cls(str(data["version"]), terms)

    def segment(self, token: str) -> str:
        """Substitute one whole segment. An unknown segment is returned as-is."""
        return self.terms.get(token, token)


_DEFAULT = None


def default_dictionary() -> Dictionary:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = Dictionary.load("0")
    return _DEFAULT


def _claim_token(claim: str, dictionary: Dictionary) -> str:
    """Project a CLAIM, or return OPEN_RECORD. Never summarise, never truncate."""
    if _CHAIN_RE.match(claim):
        return ">".join(dictionary.segment(part) for part in claim.split(">"))
    comparison = _COMPARISON_RE.match(claim)
    if comparison:
        left, operator, right = comparison.groups()
        if SEPARATOR in right:
            return OPEN_RECORD
        return f"{dictionary.segment(left)}{operator}{right}"
    return OPEN_RECORD


def _safe_slot(value: str) -> str:
    """A slot that would break the separator becomes OPEN_RECORD, never escaped."""
    return OPEN_RECORD if SEPARATOR in value else value


def project(record: Record, dictionary: Dictionary | None = None) -> str:
    """Render the triage projection of a record. Pure: the record is untouched."""
    if not isinstance(record, Record):
        raise SailangError("NOT_A_RECORD", "project() takes a canonical Record")
    dictionary = dictionary or default_dictionary()

    subject = record.get("SUBJ")
    status = record.get("STATUS")
    evidence = "EV+" if record.has_evidence else "EV0"
    flags = "".join(mark for field, mark in _FLAGS if field in record)

    slots = [
        f"{LINE_FORMAT}D{dictionary.version}",
        record.kind,
        _safe_slot(subject) if subject else ABSENT,
        status if status else ABSENT,
        evidence,
        _claim_token(record.claim, dictionary),
        flags if flags else ABSENT,
    ]
    return SEPARATOR.join(slots)


def triage(record: Record, dictionary: Dictionary | None = None) -> dict:
    """The triage facts a reader may take from the line, and nothing more.

    ``claim`` is ``None`` when the line says OPEN RECORD: the caller must open
    the canonical record rather than guess.
    """
    line = project(record, dictionary)
    marker, kind, subject, status, evidence, claim, flags = line.split(SEPARATOR)
    return {
        "line": line,
        "marker": marker,
        "kind": kind,
        "subject": None if subject in (ABSENT, OPEN_RECORD) else subject,
        "subject_open_record": subject == OPEN_RECORD,
        "status": None if status == ABSENT else status,
        "has_evidence": evidence == "EV+",
        "claim": None if claim == OPEN_RECORD else claim,
        "claim_open_record": claim == OPEN_RECORD,
        "refutes": "R" in flags,
        "supports": "S" in flags,
        "conflict": "C" in flags,
        "falsifiable": "X" in flags,
    }
