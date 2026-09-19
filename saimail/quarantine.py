"""Sensitive receipt quarantine: a receipt keeps its identity, not its distribution.

    ORIGINAL HASH AND EXISTENCE ARE PRESERVED.
    SECRET PLAINTEXT IS NOT REQUIRED IN NORMAL DISTRIBUTION.

The defect class this module eliminates: **an immutable receipt whose bytes
carry a credential can only be distributed by distributing the credential.**
A receipt is never rewritten (SOURCE-AUTHORITY-01), so its bytes cannot change.
What can change is where those bytes are allowed to travel and what travels in
their place (D-023).

Three distribution states. They sit beside a receipt's intake lifecycle status
(``ACTIVE``, closed, retired) and never replace it; nothing here reads that
status to decide anything, and nothing here writes it:

``ACTIVE_NORMAL``
    No quarantine record. The receipt travels as it is.
``SENSITIVE_QUARANTINED``
    The receipt id, original digest, length and reason travel. The plaintext
    is excluded from a normal distribution. The original stays where it was
    captured; today that is the SAIPEN hot intake, which SAIPEN's own export
    contract ships, so it is not yet a protected location
    (``spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md`` says what that needs).
``SANITIZED_DERIVATIVE``
    A distributable representation of one quarantined receipt: the original
    bytes with each credential-bearing component replaced by an explicit
    marker, bound to the original digest, with no authority of its own.

Two rules shape everything below:

* **A representation is not an instruction.** The derivative has no segment
  map and cannot be cited on its own. The authority it carries is the original
  receipt's, resolved through the original's map and digest, so redaction
  neither adds a class nor removes one.
* **Withheld is not guessed.** A span that overlaps a redaction reads as
  ``UNRESOLVED``. Its content is never inferred from the marker, from context,
  or from anything else.

And one limit, stated so nobody mistakes this for more than it is: **this is
not a cryptographic boundary.** The original digest travels. A digest over a
body whose only unknown part is short, or made of ordinary words, is an offline
guessing oracle for that part. An exposed credential is remedied by rotating
it; quarantine only stops it from being redistributed.

The detector reports *where* credential-bearing material sits, as a category,
a line and a byte span. It never returns, stores or renders *what* it found.

Like ``provenance``, this module reads and returns values. The writer is
``tools/quarantine_receipt.py``.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import math
import pathlib
import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sailang.errors import SailangError
from saimail.provenance import SegmentMap, receipt_intent_authority

#: Closed set of distribution states (D-023).
ACTIVE_NORMAL = "ACTIVE_NORMAL"
SENSITIVE_QUARANTINED = "SENSITIVE_QUARANTINED"
SANITIZED_DERIVATIVE = "SANITIZED_DERIVATIVE"
DISTRIBUTION_STATES = (ACTIVE_NORMAL, SENSITIVE_QUARANTINED, SANITIZED_DERIVATIVE)

RECORD_SCHEMA = "saimail-receipt-quarantine/1"
DETECTOR = "saimail-credential-scan/1"
REDACTION_VERSION = "saimail-redaction/1"

#: The directory, inside ``provenance/``, that holds quarantine records. A
#: subdirectory on purpose: ``provenance.load_maps`` reads the top level only,
#: so a record can never be mistaken for a segment map.
QUARANTINE_DIR = "quarantine"

# ------------------------------------------------------------------ findings

#: A file name whose stem pairs a secret label with other runs: the name either
#: embeds the value or names the file that holds it.
CREDENTIAL_LABELLED_FILENAME = "CREDENTIAL_LABELLED_FILENAME"
#: A long run inside a path component that mixes upper case, lower case and
#: digits at high entropy: the shape of a generated key, not of a word.
HIGH_ENTROPY_PATH_COMPONENT = "HIGH_ENTROPY_PATH_COMPONENT"
#: A published credential format (``sk-``, ``ghp_``, ``AKIA``, a bearer token).
KNOWN_CREDENTIAL_SHAPE = "KNOWN_CREDENTIAL_SHAPE"
#: ``password = value``, ``api_key: value`` and their relatives.
CREDENTIAL_ASSIGNMENT = "CREDENTIAL_ASSIGNMENT"
FINDING_CATEGORIES = (CREDENTIAL_LABELLED_FILENAME, HIGH_ENTROPY_PATH_COMPONENT,
                      KNOWN_CREDENTIAL_SHAPE, CREDENTIAL_ASSIGNMENT)

#: Redaction reasons, one per kind of component withheld.
CREDENTIAL_BEARING_FILENAME = "CREDENTIAL_BEARING_FILENAME"
CREDENTIAL_BEARING_PATH_COMPONENT = "CREDENTIAL_BEARING_PATH_COMPONENT"
CREDENTIAL_VALUE = "CREDENTIAL_VALUE"
REDACTION_CATEGORIES = (CREDENTIAL_BEARING_FILENAME, CREDENTIAL_BEARING_PATH_COMPONENT,
                        CREDENTIAL_VALUE)
_REDACTION_FOR = {
    CREDENTIAL_LABELLED_FILENAME: CREDENTIAL_BEARING_FILENAME,
    HIGH_ENTROPY_PATH_COMPONENT: CREDENTIAL_BEARING_PATH_COMPONENT,
    KNOWN_CREDENTIAL_SHAPE: CREDENTIAL_VALUE,
    CREDENTIAL_ASSIGNMENT: CREDENTIAL_VALUE,
}

#: Recorded when intake metadata calls a receipt non-sensitive and the detector
#: disagrees. Evidence about the metadata, never a correction of it.
SENSITIVITY_METADATA_UNDERSTATED = "SENSITIVITY_METADATA_UNDERSTATED"
#: The only rotation state this repository can state: rotation is an operator
#: act outside it, and nothing here can observe whether it happened.
ROTATION_UNKNOWN = "UNKNOWN_CONFIRMED_BY_OPERATOR_ONLY"

#: Runs that name a secret when they stand as a whole run in a file name.
#: ``credential`` is absent on purpose: it names the concept, and a file called
#: ``credentials.py`` holds code, not a secret.
SECRET_LABELS = frozenset({"key", "keys", "apikey", "token", "tokens", "secret", "secrets",
                           "password", "passwords", "passwd", "pwd", "passphrase", "bearer"})

_TOKEN = re.compile(r"[^\s\"'`<>|()\[\]{},;]+")
_SEPARATOR = re.compile(r"[\\/]")
_RUN = re.compile(r"[A-Za-z0-9]+")
_LONG_RUN = re.compile(r"[A-Za-z0-9]{24,}")
_KNOWN_SHAPE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    r"sk-[A-Za-z0-9_\-]{20,}"
    r"|gh[pousr]_[A-Za-z0-9]{30,}"
    r"|github_pat_[A-Za-z0-9_]{30,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|xox[abprs]-[A-Za-z0-9\-]{10,}"
    r"|glpat-[A-Za-z0-9_\-]{20,}"
    r"|AIza[0-9A-Za-z_\-]{35}"
    r")")
_BEARER = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9_\-.=]{20,})")
_ASSIGNMENT = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?token|token|password|passwd|secret)\b\s*[:=]\s*"
    r"(?!<redacted>|\*{3}|<|\$\{)([^\s,;]{8,})")
_MIN_ENTROPY = 4.0


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Finding:
    """Where credential-bearing material sits in a body. Never what it is."""

    category: str
    line: int
    #: UTF-8 byte offsets into the body, end exclusive
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.category not in FINDING_CATEGORIES:
            _reject("BAD_FINDING_CATEGORY", f"{self.category!r} is not one of {FINDING_CATEGORIES}")
        if self.line < 1 or self.start < 0 or self.end <= self.start:
            _reject("BAD_FINDING", f"{self.category} at line {self.line} is not a span")

    def as_record(self) -> dict:
        return {"category": self.category, "line": self.line, "start": self.start,
                "end": self.end}


def _entropy(run: str) -> float:
    counts: Dict[str, int] = {}
    for char in run:
        counts[char] = counts.get(char, 0) + 1
    return -sum(n / len(run) * math.log2(n / len(run)) for n in counts.values())


def _is_generated_shape(run: str) -> bool:
    return (any(c.isupper() for c in run) and any(c.islower() for c in run)
            and any(c.isdigit() for c in run) and _entropy(run) >= _MIN_ENTROPY)


def _labelled(name: str) -> bool:
    runs = [(m.group(0), m.start()) for m in _RUN.finditer(name)]
    stem = runs
    if len(runs) > 1:
        last, at = runs[-1]
        if at > 0 and name[at - 1] == "." and at + len(last) == len(name):
            stem = runs[:-1]
    labels = [r for r, _ in stem if r.lower() in SECRET_LABELS]
    return bool(labels) and len(labels) < len(stem)


#: A file name ends in an extension, or the token is anchored like a path.
_EXTENSION = re.compile(r"\.[A-Za-z0-9]{1,12}$")
_PATH_ANCHOR = re.compile(r"^(?:[A-Za-z]:[\\/]|[\\/]|\.{1,2}[\\/]|~[\\/])")


def _path_shaped(token: str, name: str) -> bool:
    """A slash in prose is not a path (D-027).

    The incident class is a *file name*: a component that ends in an
    extension, or a token anchored as a path (backslash, drive letter, root,
    ``./``, ``../``, ``~/``). ``secret/private-key`` in running text is a
    hyphenated compound, not a file, and must not cost a redaction.
    """
    return bool(_EXTENSION.search(name)) or "\\" in token or bool(_PATH_ANCHOR.match(token))


def scan(body: bytes) -> Tuple[Finding, ...]:
    """Structural credential scan of one receipt body. Deterministic, text-free output.

    Known limits, accepted and declared: a path containing whitespace is
    examined one whitespace-delimited token at a time, and a labelled file name
    is only read where the token has a file shape -- an extension or a path
    anchor (D-027); a bare slash in prose is not a path. The scan is
    conservative: a false positive costs a redaction and a human look, a false
    negative costs a credential.

    Byte offsets and line numbers come from one linear preparation (PERF-003):
    the previous per-finding prefix re-encode and prefix newline count made a
    finding-dense body scan approximately quadratic, and this is the subsystem
    a sensitive export leans on.
    """
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        _reject("BODY_NOT_UTF8", "a receipt body is UTF-8 or it is not a receipt body")

    if text.isascii():
        def at(char_index: int) -> int:
            return char_index
    else:
        # one forward pass: the exact UTF-8 byte offset of every char index
        offsets = [0] * (len(text) + 1)
        total = 0
        for position, character in enumerate(text):
            code = ord(character)
            total += 1 if code < 0x80 else 2 if code < 0x800 else 3 if code < 0x10000 else 4
            offsets[position + 1] = total

        def at(char_index: int) -> int:
            return offsets[char_index]

    newlines = [index for index, character in enumerate(text) if character == "\n"]

    def line_of(char_index: int) -> int:
        return bisect.bisect_left(newlines, char_index) + 1

    found: List[Finding] = []
    for match in _TOKEN.finditer(text):
        token = match.group(0)
        if not _SEPARATOR.search(token):
            continue
        cut = max(token.rfind("\\"), token.rfind("/")) + 1
        name = token[cut:].rstrip(".:")
        if name and _path_shaped(token, name) and _labelled(name):
            begin = match.start() + cut
            found.append(Finding(CREDENTIAL_LABELLED_FILENAME, line_of(begin), at(begin),
                                 at(begin + len(name))))
        offset = match.start()
        for component in re.split(r"([\\/])", token):
            for run in _LONG_RUN.finditer(component):
                if _is_generated_shape(run.group(0)):
                    begin = offset + run.start()
                    found.append(Finding(HIGH_ENTROPY_PATH_COMPONENT, line_of(begin),
                                         at(begin), at(begin + len(run.group(0)))))
            offset += len(component)
    for match in _KNOWN_SHAPE.finditer(text):
        found.append(Finding(KNOWN_CREDENTIAL_SHAPE, line_of(match.start()),
                             at(match.start()), at(match.end())))
    for pattern, category in ((_BEARER, KNOWN_CREDENTIAL_SHAPE),
                              (_ASSIGNMENT, CREDENTIAL_ASSIGNMENT)):
        for match in pattern.finditer(text):
            found.append(Finding(category, line_of(match.start(1)), at(match.start(1)),
                                 at(match.end(1))))
    unique = {(f.start, f.end, f.category): f for f in found}
    return tuple(unique[k] for k in sorted(unique))


# ------------------------------------------------------------------ redaction


def marker(category: str) -> bytes:
    """The explicit marker that stands where a withheld component was."""
    if category not in REDACTION_CATEGORIES:
        _reject("BAD_REDACTION_CATEGORY", f"{category!r} is not one of {REDACTION_CATEGORIES}")
    return f"[REDACTED:{category}:{REDACTION_VERSION}]".encode("ascii")


@dataclass(frozen=True)
class Redaction:
    """One withheld span, in original and in sanitized coordinates."""

    original_start: int
    original_end: int
    sanitized_start: int
    sanitized_end: int
    category: str

    def as_record(self) -> dict:
        return {"original_start": self.original_start, "original_end": self.original_end,
                "sanitized_start": self.sanitized_start, "sanitized_end": self.sanitized_end,
                "category": self.category, "marker": marker(self.category).decode("ascii")}


def plan_redactions(findings: Sequence[Finding]) -> Tuple[Tuple[int, int, str], ...]:
    """Merge overlapping findings into disjoint spans, in body order."""
    spans: List[List] = []
    for finding in sorted(findings, key=lambda f: (f.start, f.end)):
        category = _REDACTION_FOR[finding.category]
        if spans and finding.start < spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], finding.end)
            continue
        spans.append([finding.start, finding.end, category])
    return tuple((s, e, c) for s, e, c in spans)


def sanitize(body: bytes, spans: Sequence[Tuple[int, int, str]]) -> Tuple[bytes, Tuple[Redaction, ...]]:
    """Replace each span with its marker. Every other byte is kept exactly."""
    out = bytearray()
    redactions: List[Redaction] = []
    cursor = 0
    for start, end, category in spans:
        if start < cursor or end > len(body) or end <= start:
            _reject("BAD_REDACTION_SPAN", f"span {start}:{end} is not a disjoint span of the body")
        out += body[cursor:start]
        sanitized_start = len(out)
        out += marker(category)
        redactions.append(Redaction(start, end, sanitized_start, len(out), category))
        cursor = end
    out += body[cursor:]
    return bytes(out), tuple(redactions)


# ------------------------------------------------------------------ records


@dataclass(frozen=True)
class Unresolved:
    """A clause the representation cannot interpret exactly, and why."""

    clause: str
    original_start: int
    original_end: int
    reason: str

    def as_record(self) -> dict:
        return {"clause": self.clause, "original_start": self.original_start,
                "original_end": self.original_end, "reason": self.reason}


@dataclass(frozen=True)
class Derivative:
    id: str
    path: str
    sha256: str
    length: int
    redactions: Tuple[Redaction, ...]
    unresolved: Tuple[Unresolved, ...]
    represents: str
    authoritative: bool = False
    newly_authored: bool = False
    redaction_version: str = REDACTION_VERSION


@dataclass(frozen=True)
class QuarantineRecord:
    """One quarantined receipt: identity, reason and its sanitized derivative.

    ``evidence`` keeps the record's descriptive fields (the intake metadata
    snapshot, the protected-location status, the operator statements, the
    SAIPEN export status) exactly as written, so a consumer reads them from
    one place and this type never has to guess their meaning.
    """

    receipt: str
    original_path: str
    original_sha256: str
    original_length: int
    reason_category: str
    detector: str
    findings: Tuple[Finding, ...]
    derivative: Derivative
    evidence: Mapping

    def __post_init__(self) -> None:
        d = self.derivative
        if d.represents != self.receipt:
            _reject("DERIVATIVE_RECEIPT_MISMATCH",
                    f"{d.id} represents {d.represents}, the record quarantines {self.receipt}")
        if d.authoritative or d.newly_authored:
            _reject("DERIVATIVE_CLAIMS_AUTHORITY",
                    f"{d.id} is a representation of {self.receipt}; it carries no authority of "
                    "its own and was authored by nobody")
        if d.redaction_version != REDACTION_VERSION:
            _reject("UNKNOWN_REDACTION_VERSION", f"{d.id}: {d.redaction_version!r}")
        if self.reason_category not in REDACTION_CATEGORIES:
            _reject("BAD_REDACTION_CATEGORY", f"{self.receipt}: {self.reason_category!r}")
        if not self.findings:
            _reject("QUARANTINE_WITHOUT_EVIDENCE",
                    f"{self.receipt}: a quarantine with no finding is a deletion by another name")
        if not d.redactions:
            _reject("DERIVATIVE_MALFORMED", f"{d.id} withholds nothing")
        cursor, shift = 0, 0
        for r in d.redactions:
            width = len(marker(r.category))
            if (r.original_start < cursor or r.original_end <= r.original_start
                    or r.original_end > self.original_length
                    or r.sanitized_start != r.original_start + shift
                    or r.sanitized_end - r.sanitized_start != width):
                _reject("DERIVATIVE_MALFORMED",
                        f"{d.id}: redaction {r.original_start}:{r.original_end} does not map onto "
                        "its marker")
            shift += width - (r.original_end - r.original_start)
            cursor = r.original_end
        if d.length != self.original_length + shift:
            _reject("DERIVATIVE_MALFORMED",
                    f"{d.id}: {d.length} bytes, the redactions account for "
                    f"{self.original_length + shift}")
        for finding in self.findings:
            if not any(r.original_start <= finding.start and finding.end <= r.original_end
                       for r in d.redactions):
                _reject("FINDING_NOT_REDACTED",
                        f"{self.receipt}: a {finding.category} finding on line {finding.line} "
                        "is outside every redaction")
        for item in d.unresolved:
            if not any(r.original_start < item.original_end and item.original_start < r.original_end
                       for r in d.redactions):
                _reject("UNRESOLVED_WITHOUT_REDACTION",
                        f"{d.id}: {item.clause} overlaps no redaction; unresolved is what a "
                        "redaction causes, not an opinion about the text")

    def spans(self) -> Tuple[Tuple[int, int, str], ...]:
        return tuple((r.original_start, r.original_end, r.category)
                     for r in self.derivative.redactions)


def record_from_dict(data: Mapping) -> QuarantineRecord:
    if data.get("schema") != RECORD_SCHEMA:
        _reject("UNKNOWN_QUARANTINE_SCHEMA", f"{data.get('schema')!r} is not {RECORD_SCHEMA}")
    if data.get("distribution_state") != SENSITIVE_QUARANTINED:
        _reject("BAD_DISTRIBUTION_STATE",
                f"a quarantine record describes a {SENSITIVE_QUARANTINED} receipt, "
                f"not {data.get('distribution_state')!r}")
    original, reason, derived = data["original"], data["reason"], data["derivative"]
    if derived.get("distribution_state") != SANITIZED_DERIVATIVE:
        _reject("BAD_DISTRIBUTION_STATE",
                f"a derivative is {SANITIZED_DERIVATIVE}, not {derived.get('distribution_state')!r}")
    authority = derived["authority"]
    derivative = Derivative(
        id=derived["id"], path=derived["path"], sha256=derived["sha256"],
        length=derived["length"], redaction_version=derived["redaction_version"],
        redactions=tuple(Redaction(r["original_start"], r["original_end"], r["sanitized_start"],
                                   r["sanitized_end"], r["category"])
                         for r in derived["redactions"]),
        unresolved=tuple(Unresolved(u["clause"], u["original_start"], u["original_end"],
                                    u["reason"]) for u in derived["unresolved"]),
        represents=authority["represents"], authoritative=authority["authoritative"],
        newly_authored=authority["newly_authored"])
    for r in derived["redactions"]:
        if r.get("marker") != marker(r["category"]).decode("ascii"):
            _reject("DERIVATIVE_MALFORMED", f"{derivative.id}: a recorded marker was altered")
    return QuarantineRecord(
        receipt=data["receipt"], original_path=original["path"],
        original_sha256=original["sha256"], original_length=original["length"],
        reason_category=reason["category"], detector=reason["detector"],
        findings=tuple(Finding(f["category"], f["line"], f["start"], f["end"])
                       for f in reason["findings"]),
        derivative=derivative,
        evidence={"original": {k: v for k, v in original.items()
                               if k not in ("path", "sha256", "length")},
                  "reason": {k: v for k, v in reason.items()
                             if k not in ("category", "detector", "findings")},
                  **{k: v for k, v in data.items()
                     if k not in ("schema", "receipt", "distribution_state", "original",
                                  "reason", "derivative")}})


def load_records(directory: pathlib.Path) -> Dict[str, QuarantineRecord]:
    """Every quarantine record in ``provenance/quarantine``. No directory, no records."""
    if not directory.is_dir():
        return {}
    records = {}
    for path in sorted(directory.glob("*.json")):
        record = record_from_dict(json.loads(path.read_text(encoding="utf-8")))
        if path.stem != record.receipt:
            _reject("RECORD_NAME_MISMATCH", f"{path.name} holds the record for {record.receipt}")
        records[record.receipt] = record
    return records


def distribution_state(identity: str, records: Mapping[str, QuarantineRecord]) -> str:
    """The distribution state of a receipt id or a derivative id."""
    if identity in records:
        return SENSITIVE_QUARANTINED
    if any(r.derivative.id == identity for r in records.values()):
        return SANITIZED_DERIVATIVE
    return ACTIVE_NORMAL


_UNRESOLVED_REASON = {
    CREDENTIAL_BEARING_FILENAME: (
        "the exact name of a file this receipt references is withheld; anything that depends "
        "on reading or naming that file cannot be interpreted exactly from this representation"),
    CREDENTIAL_BEARING_PATH_COMPONENT: (
        "a component of a path this receipt references is withheld; the path cannot be "
        "resolved exactly from this representation"),
    CREDENTIAL_VALUE: (
        "a credential value is withheld; nothing that depends on the value itself can be "
        "interpreted from this representation"),
}


def build_record(receipt: str, body: bytes, meta: Mapping, original_path: str,
                 derivative_path: str, evidence: Mapping) -> Tuple[dict, bytes]:
    """The record and sanitized bytes for one receipt. Pure and deterministic.

    Refuses a receipt the detector finds nothing in, and a receipt whose bytes
    no longer match the digest its intake metadata recorded.
    """
    digest = sha256_hex(body)
    if meta.get("source_sha256") != digest:
        _reject("RECEIPT_CHANGED", f"{receipt}: the body does not hash to its recorded digest")
    findings = scan(body)
    if not findings:
        _reject("NOTHING_TO_QUARANTINE",
                f"{receipt}: the detector found no credential-bearing material; a quarantine "
                "without evidence is a deletion by another name")
    spans = plan_redactions(findings)
    sanitized, redactions = sanitize(body, spans)
    text = body.decode("utf-8")
    lines = {f.start: f.line for f in findings}
    unresolved = []
    for r in redactions:
        line = lines.get(r.original_start) or text.count(
            "\n", 0, len(body[:r.original_start].decode("utf-8"))) + 1
        unresolved.append(Unresolved(f"line {line}", r.original_start, r.original_end,
                                     _UNRESOLVED_REASON[r.category]).as_record())
    categories = sorted({r.category for r in redactions})
    redaction_meta = meta.get("redaction") if isinstance(meta.get("redaction"), dict) else {}
    snapshot = {"status": meta.get("status"), "sensitive": meta.get("sensitive"),
                "redaction_applied": redaction_meta.get("applied")}
    record = {
        "schema": RECORD_SCHEMA,
        "receipt": receipt,
        "distribution_state": SENSITIVE_QUARANTINED,
        "original": {
            "path": original_path,
            "sha256": digest,
            "length": len(body),
            "intake_metadata_at_quarantine": snapshot,
            "plaintext_in_normal_distribution": False,
            **dict(evidence.get("original", {})),
        },
        "reason": {
            "category": categories[0],
            "detector": DETECTOR,
            "findings": [f.as_record() for f in findings],
            "metadata_disagreement": (SENSITIVITY_METADATA_UNDERSTATED
                                      if meta.get("sensitive") is not True else None),
            "credential_rotation": ROTATION_UNKNOWN,
            **dict(evidence.get("reason", {})),
        },
        "derivative": {
            "id": f"{receipt}/sanitized/1",
            "distribution_state": SANITIZED_DERIVATIVE,
            "path": derivative_path,
            "sha256": sha256_hex(sanitized),
            "length": len(sanitized),
            "redaction_version": REDACTION_VERSION,
            "redactions": [r.as_record() for r in redactions],
            "authority": {"represents": receipt, "authoritative": False,
                          "newly_authored": False,
                          "authority_source": "SEGMENT_MAP_OF_ORIGINAL_RECEIPT"},
            "unresolved": unresolved,
        },
        **{k: v for k, v in evidence.items() if k not in ("original", "reason")},
    }
    record_from_dict(record)  # the writer produces nothing the reader would refuse
    return record, sanitized


def render_record(record: Mapping) -> str:
    return json.dumps(record, indent=2, ensure_ascii=False) + "\n"


# ------------------------------------------------------------------ verification

VERIFIED_AGAINST_ORIGINAL = "VERIFIED_AGAINST_ORIGINAL"
#: The original is not present. The derivative is bound to the original digest
#: and its markers check out; that its other bytes equal the original's is what
#: the producer attested and can only be re-proven where the original exists.
HASH_BOUND = "HASH_BOUND"


def verify_derivative(record: QuarantineRecord, derivative_body: bytes,
                      original_body: Optional[bytes] = None) -> str:
    d = record.derivative
    if len(derivative_body) != d.length or sha256_hex(derivative_body) != d.sha256:
        _reject("DERIVATIVE_CHANGED", f"{d.id} does not hash to its recorded digest")
    for r in d.redactions:
        if derivative_body[r.sanitized_start:r.sanitized_end] != marker(r.category):
            _reject("DERIVATIVE_MALFORMED", f"{d.id}: no marker where a redaction is recorded")
    if original_body is None:
        return HASH_BOUND
    if len(original_body) != record.original_length or \
            sha256_hex(original_body) != record.original_sha256:
        _reject("RECEIPT_CHANGED", f"{record.receipt} does not hash to its quarantined digest")
    if sanitize(original_body, record.spans())[0] != derivative_body:
        _reject("DERIVATIVE_INFIDELITY",
                f"{d.id} is not the declared redaction of {record.receipt}")
    return VERIFIED_AGAINST_ORIGINAL


def represented_authority(record: QuarantineRecord, maps: Mapping[str, SegmentMap],
                          derivative_body: bytes, original_body: Optional[bytes] = None) -> dict:
    """What the derivative may be read as, and on whose authority.

    The answer is the original receipt's own authority, computed from the
    original's segment map, which is bound to the original digest the record
    preserves. The derivative contributes a readable body and a list of what it
    cannot say. It contributes no class.
    """
    if record.receipt not in maps:
        _reject("NO_SEGMENT_MAP", f"{record.receipt} has no segment map; a representation "
                                  "cannot supply the authorship its original never declared")
    segment_map = maps[record.receipt]
    if (segment_map.body_sha256 != record.original_sha256
            or segment_map.body_length != record.original_length):
        _reject("ORIGINAL_IDENTITY_MISMATCH",
                f"{record.receipt}: the segment map and the quarantine record describe "
                "different bytes")
    fidelity = verify_derivative(record, derivative_body, original_body)
    return {
        "receipt": record.receipt,
        "represented_by": record.derivative.id,
        "distribution_state": SANITIZED_DERIVATIVE,
        "authority": receipt_intent_authority(record.receipt, maps),
        "authority_source": "SEGMENT_MAP_OF_ORIGINAL_RECEIPT",
        "fidelity": fidelity,
        "unresolved": [u.as_record() for u in record.derivative.unresolved],
    }


RESOLVED = "RESOLVED"
UNRESOLVED = "UNRESOLVED"


def read_span(record: QuarantineRecord, derivative_body: bytes, start: int,
              end: int) -> Tuple[str, Optional[bytes]]:
    """Read an original-coordinate span through the derivative.

    The derivative is authenticated first (T-39/CORE-004): ``(RESOLVED, bytes)``
    means the recorded digest, length and markers all check out and those bytes
    are the original's. ``(UNRESOLVED, None)`` when a redaction touches the
    span: the marker is not content, and a neighbouring clause is not a
    substitute for the withheld one. A tampered body raises ``DERIVATIVE_CHANGED``
    from that check instead of ever returning RESOLVED bytes.
    """
    verify_derivative(record, derivative_body)
    if not 0 <= start < end <= record.original_length:
        _reject("BAD_SPAN", f"{start}:{end} is not a span of {record.receipt}")
    shift = 0
    for r in record.derivative.redactions:
        if r.original_start < end and start < r.original_end:
            return UNRESOLVED, None
        if r.original_end <= start:
            shift += (r.sanitized_end - r.sanitized_start) - (r.original_end - r.original_start)
    return RESOLVED, derivative_body[start + shift:end + shift]


# ------------------------------------------------------------------ distribution

#: Exclusion reasons of a normal distribution.
QUARANTINED_PLAINTEXT = "QUARANTINED_PLAINTEXT"
NON_EXPORTABLE = "NON_EXPORTABLE"
BUILD_CACHE = "BUILD_CACHE"
VCS_INTERNAL = "VCS_INTERNAL"

_CACHE_PARTS = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"})
_CACHE_SUFFIXES = (".pyc", ".pyo")


def distributable(paths: Iterable[str], records: Mapping[str, QuarantineRecord],
                  memory_root: str, non_exportable: Sequence[str],
                  digest_of: Optional[Callable[[str], Optional[str]]] = None,
                  ) -> Tuple[Tuple[str, ...], Dict[str, str]]:
    """Split a project inventory into what a normal distribution carries and what it does not.

    ``paths`` are project-relative. ``non_exportable`` is the memory root's own
    declaration (SAIPEN's audit manifest), relative to ``memory_root``. A
    quarantined original is excluded by its recorded path and, when
    ``digest_of`` is given, by its content digest wherever it now lives: closing
    a receipt moves its body into a cold archive, and a quarantine that only
    knew the old path would quietly start shipping the plaintext again. Its
    record, its metadata and its derivative are ordinary files and travel.
    """
    quarantined = {r.original_path.replace("\\", "/") for r in records.values()}
    digests = {r.original_sha256 for r in records.values()}
    prefix = memory_root.rstrip("/") + "/"
    included: List[str] = []
    excluded: Dict[str, str] = {}
    for raw in paths:
        path = raw.replace("\\", "/")
        parts = path.split("/")
        if path in quarantined:
            excluded[path] = QUARANTINED_PLAINTEXT
        elif path.startswith(prefix) and any(
                path[len(prefix):] == entry or (entry.endswith("/") and
                                                path[len(prefix):].startswith(entry))
                for entry in non_exportable):
            excluded[path] = NON_EXPORTABLE
        elif ".git" in parts:
            excluded[path] = VCS_INTERNAL
        elif (_CACHE_PARTS & set(parts) or any(p.endswith(".egg-info") for p in parts)
              or path.endswith(_CACHE_SUFFIXES)):
            excluded[path] = BUILD_CACHE
        elif digest_of is not None and digest_of(raw) in digests:
            excluded[path] = QUARANTINED_PLAINTEXT
        else:
            included.append(path)
    return tuple(sorted(included)), excluded


#: A single run this long is not an ordinary word, so it is searched on its own.
_LONE_RUN_FRAGMENT = 16


def withheld_fragments(record: QuarantineRecord, original_body: bytes) -> Tuple[bytes, ...]:
    """Every searchable piece of every withheld component, lower-cased.

    Which substring of a component is the secret is exactly what nobody may
    say, so the whole component is not enough to search for: a copy of the
    value alone would slip past it. Searched instead: every contiguous window of
    two or more alphanumeric runs with their own separators, and any single run
    long enough not to be a word. The price is a false positive on an innocent
    two-run phrase, which a human settles; the alternative is a missed copy.

    This is the exhaustive expansion and it stays public for compatibility and
    inspection, but it materializes O(R^2) windows for a component with R runs:
    a few-kilobyte withheld path once grew to hundreds of megabytes of fragment
    storage (PERF-004). Safety-critical leak checking routes through
    :func:`leak_basis`, which is sufficient and bounded.
    """
    if sha256_hex(original_body) != record.original_sha256:
        _reject("RECEIPT_CHANGED", f"{record.receipt} does not hash to its quarantined digest")
    pieces = set()
    for start, end, _ in record.spans():
        component = original_body[start:end].lower()
        pieces.update(_component_windows(component))
    return tuple(sorted(pieces))


def _component_windows(component: bytes) -> Iterable[bytes]:
    """Every contiguous multi-run window, plus qualifying lone runs, of one component."""
    runs = list(re.finditer(rb"[a-z0-9]+", component))
    # a file extension names a format, not a secret; searching it would only
    # match every other file of that format
    if len(runs) > 2 and runs[-1].end() == len(component) and \
            component[runs[-1].start() - 1:runs[-1].start()] == b".":
        runs = runs[:-1]
    if len(runs) < 2:
        yield component
        return
    for i, first in enumerate(runs):
        if len(first.group(0)) >= _LONE_RUN_FRAGMENT:
            yield first.group(0)
        for last in runs[i + 1:]:
            yield component[first.start():last.end()]


def leak_basis(record: QuarantineRecord, original_body: bytes) -> Tuple[bytes, ...]:
    """A bounded search basis with the same leak-decision power (PERF-004).

    Every contiguous window of two or more runs contains an *adjacent* two-run
    window, so searching adjacent run-pairs (with their separator bytes),
    qualifying long single runs and whole short components detects exactly the
    same files as the exhaustive expansion: for any exhaustive piece, either it
    is in this basis or a basis piece is a substring of it. O(R) pieces per
    component instead of O(R^2).
    """
    if sha256_hex(original_body) != record.original_sha256:
        _reject("RECEIPT_CHANGED", f"{record.receipt} does not hash to its quarantined digest")
    pieces = set()
    for start, end, _ in record.spans():
        component = original_body[start:end].lower()
        runs = list(re.finditer(rb"[a-z0-9]+", component))
        if len(runs) > 2 and runs[-1].end() == len(component) and \
                component[runs[-1].start() - 1:runs[-1].start()] == b".":
            runs = runs[:-1]
        if len(runs) < 2:
            pieces.add(component)
            continue
        for i, first in enumerate(runs):
            if len(first.group(0)) >= _LONE_RUN_FRAGMENT:
                pieces.add(first.group(0))
            if i + 1 < len(runs):
                pieces.add(component[first.start():runs[i + 1].end()])
    return tuple(sorted(pieces))


def find_original(root: pathlib.Path, record: QuarantineRecord) -> Optional[bytes]:
    """The original body wherever it is kept under ``root``, proven by digest; else None.

    The recorded path first; then any ``<receipt>.md`` under ``root`` whose bytes
    hash to the quarantined digest, which is where closure leaves it.
    """
    candidates = [root / record.original_path]
    candidates += sorted(p for p in root.rglob(f"{record.receipt}.md") if p not in candidates)
    for path in candidates:
        if path.is_file():
            body = path.read_bytes()
            if len(body) == record.original_length and sha256_hex(body) == record.original_sha256:
                return body
    return None


def plaintext_leaks(files: Mapping[str, bytes], record: QuarantineRecord,
                    original_body: bytes) -> Tuple[str, ...]:
    """Paths whose bytes contain any withheld fragment. Returns paths, never bytes.

    Searches the bounded :func:`leak_basis` (PERF-004) and lower-cases every
    candidate file exactly once, instead of re-lowering a whole file per
    secret fragment.
    """
    pieces = leak_basis(record, original_body)
    lowered = {path: data.lower() for path, data in files.items()}
    return tuple(sorted(path for path, data in lowered.items()
                        if any(piece in data for piece in pieces)))


HONOURED = "HONOURED"
NOT_HONOURED = "NOT_HONOURED"


def saipen_export_status(manifest: Mapping, records: Mapping[str, QuarantineRecord],
                         memory_root: str) -> str:
    """Does SAIPEN's own export contract keep every quarantined original out?

    Honoured only when each original is excluded by the manifest itself: named
    in ``non_exportable`` or in a declared ``quarantine.excluded_bodies`` list
    (the shape the protocol change proposal asks for). An export rule that
    ships the whole intake tree honours nothing, however the files are named.
    """
    evidence = manifest.get("evidence") if isinstance(manifest.get("evidence"), Mapping) else {}
    non_exportable = list(evidence.get("non_exportable") or [])
    quarantine = manifest.get("quarantine") if isinstance(manifest.get("quarantine"), Mapping) \
        else {}
    declared = set(quarantine.get("excluded_bodies") or [])
    prefix = memory_root.rstrip("/") + "/"
    for record in records.values():
        path = record.original_path.replace("\\", "/")
        relative = path[len(prefix):] if path.startswith(prefix) else path
        covered = relative in declared or any(
            relative == entry or (entry.endswith("/") and relative.startswith(entry))
            for entry in non_exportable)
        if not covered:
            return NOT_HONOURED
    return HONOURED
