"""LAB-ONLY B-018 real-project corpus pilot: one frozen registration, one real build.

The defect class this module eliminates: **a "real-project corpus" that was
actually assembled by whatever the agent happened to look at.** The completed
B-017 builder refuses to search, group or repair, but nothing froze, before the
fact, which real files a pilot would read, which exact sections of them count as
artifacts, and what bytes those artifacts were. A pilot that reads first and
registers later cannot be reproduced, and a pilot that re-reads a changed file
under an old manifest silently measures a different subject.

So the pilot is two steps with a hard boundary between them:

1. ``freeze_registration`` writes one immutable canonical manifest *before* any
   corpus is built. It names the exact eight sources and selectors, records each
   source file's SHA-256 and each selected content's SHA-256, and its own bytes
   are the registration identity (``REGISTRATION_ID``). After the first real
   capture the file is never edited; a different selection is a new registration.
2. ``build_pilot_corpus`` re-reads only the registered paths, re-extracts only
   the registered selectors, refuses on any source-file or content pin mismatch,
   and hands the exact captures plus the explicit event grouping to the
   unchanged B-017 builder. B-017 remains the only identity authority:
   ``EVIDENCE_REF``, ``EVENT_REF``, ``BUILD_ID`` and ``CORPUS_ID`` are all
   minted there, never here.

The adapter reads no directory listing, no repository metadata, no SAIPEN state,
no network and no model. It knows three source files and eight selectors because
the registration names them; it never searches for more.

v0 fails closed when a registered source changed. The single narrow exception
is an append-only journal source whose every registered selector still proves
its exact frozen content pin: the growth is recorded as
``APPEND_ONLY_SOURCE_MATCHES_REGISTERED_CONTENT_PINS``, no new content is
extracted, and every other source change refuses with
``PROJECT_PILOT_SOURCE_CHANGED``.

    python lab/project_corpus_pilot.py --register
    python lab/project_corpus_pilot.py --run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import PurePosixPath

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sailang.errors import SailangError
from saimail import project_corpus as pc
from saimail.publish import publish_immutable

PILOT_VERSION = "PROJECT-CORPUS-PILOT-1"

SEED_FILE = "project_corpus_pilot_selection.json"
REGISTRATION_FILE = "project_corpus_pilot_registration.json"
ARTIFACT_TEMPLATE = "project_corpus_pilot_{stamp}.json"
REPORT_TEMPLATE = "PROJECT_CORPUS_PILOT_REPORT_{stamp}.md"

MARKDOWN_SECTION = "MARKDOWN_SECTION"
LOG_RECORD = "LOG_RECORD"
WHOLE_FILE = "WHOLE_FILE"
SELECTOR_KINDS = (MARKDOWN_SECTION, LOG_RECORD, WHOLE_FILE)

PROJECT_PILOT_REGISTRATION_INVALID = "PROJECT_PILOT_REGISTRATION_INVALID"
PROJECT_PILOT_REGISTRATION_CHANGED = "PROJECT_PILOT_REGISTRATION_CHANGED"
PROJECT_PILOT_SELECTOR_MISSING = "PROJECT_PILOT_SELECTOR_MISSING"
PROJECT_PILOT_SELECTOR_DUPLICATE = "PROJECT_PILOT_SELECTOR_DUPLICATE"
PROJECT_PILOT_SELECTOR_EMPTY = "PROJECT_PILOT_SELECTOR_EMPTY"
PROJECT_PILOT_SOURCE_UNREADABLE = "PROJECT_PILOT_SOURCE_UNREADABLE"
PROJECT_PILOT_SOURCE_CHANGED = "PROJECT_PILOT_SOURCE_CHANGED"
PROJECT_PILOT_SOURCE_MUTATED = "PROJECT_PILOT_SOURCE_MUTATED"
PROJECT_PILOT_ARTIFACT_COUNT_MISMATCH = "PROJECT_PILOT_ARTIFACT_COUNT_MISMATCH"
PROJECT_PILOT_EVENT_COUNT_MISMATCH = "PROJECT_PILOT_EVENT_COUNT_MISMATCH"
PROJECT_PILOT_ARTIFACT_UNASSIGNED = "PROJECT_PILOT_ARTIFACT_UNASSIGNED"
PROJECT_PILOT_ARTIFACT_MULTI_EVENT = "PROJECT_PILOT_ARTIFACT_MULTI_EVENT"
PROJECT_PILOT_UNKNOWN_EVENT_MEMBER = "PROJECT_PILOT_UNKNOWN_EVENT_MEMBER"
PROJECT_PILOT_REPRODUCIBILITY_FAILED = "PROJECT_PILOT_REPRODUCIBILITY_FAILED"
PROJECT_PILOT_ARTIFACT_CHANGED = "PROJECT_PILOT_ARTIFACT_CHANGED"

APPEND_ONLY_CONTENT_PIN_MATCH = "APPEND_ONLY_SOURCE_MATCHES_REGISTERED_CONTENT_PINS"

_SHA_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_LOG_MARKER_RE = re.compile(r"^\[E-\d{3}\]$")
_PROJECT_SCOPE_RE = re.compile(r"^project:[a-z0-9][a-z0-9._-]{0,127}$")


def selection_artifacts(seed_path=None) -> tuple[dict, ...]:
    """The seeded selection: exact artifacts, zero discovery, data not code.

    The seeds live in ``project_corpus_pilot_selection.json`` so this module
    never names a project path itself; the lab-isolation tripwire keeps its
    full force.
    """
    path = pathlib.Path(seed_path) if seed_path else (
        pathlib.Path(__file__).resolve().parent / SEED_FILE)
    try:
        document = json.loads(path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "the pilot selection seed must be one strict UTF-8 JSON document")
    if (not isinstance(document, dict)
            or set(document) != {"selection_version", "artifacts"}
            or document["selection_version"] != PILOT_VERSION
            or not isinstance(document["artifacts"], list)):
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "the pilot selection seed carries exactly a version and an artifact list")
    artifacts = []
    for entry in document["artifacts"]:
        if not isinstance(entry, dict) or set(entry) != {
                "label", "source_kind", "source_ref", "observed_at", "source",
                "selector"}:
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    "a seeded artifact carries exactly the frozen selection fields")
        artifacts.append(dict(entry))
    if not artifacts:
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "the pilot selection seed cannot be empty")
    return tuple(artifacts)


#: The exact operator-authorized grouping frozen by SRC-051: five explicit
#: declarations, an exact partition of A1..A8, no artifact in two events.
REGISTERED_EVENTS = (
    {
        "label": "P1",
        "name": "B016_INITIAL_GENERATION_GATE",
        "members": ("A1", "A2"),
        "meaning": (
            "D-047 design + its T-61 verification belong to one declared "
            "implementation occurrence."
        ),
    },
    {
        "label": "P2",
        "name": "REVIEW_INVOCATION_AUTHORITY_CORRECTION",
        "members": ("A3", "A4"),
        "meaning": (
            "D-048 corrective decision + T-62 verification belong to one "
            "declared correction occurrence."
        ),
    },
    {
        "label": "P3",
        "name": "SYNTHETIC_LIVE_GENERATION_EXPERIMENT",
        "members": ("A5",),
        "meaning": "One-artifact event is valid.",
    },
    {
        "label": "P4",
        "name": "EVENT_INDEPENDENCE_CORRECTION",
        "members": ("A6",),
        "meaning": "D-049 corrected the event identity of one evidence artifact.",
    },
    {
        "label": "P5",
        "name": "REAL_PROJECT_CORPUS_BUILDER",
        "members": ("A7", "A8"),
        "meaning": "D-050 builder policy + its T-67 verification belong to one occurrence.",
    },
)

GROUPING_LIMITATION = {
    "authority": "EXPLICIT_OPERATOR_AUTHORIZED_GROUPING",
    "proves_objectively_only_events": False,
    "p1_p5_causally_independent": False,
    "one_ticket_equals_one_event": False,
    "every_relevant_occurrence_selected": False,
    "grouping_proves_behavioural_pattern": False,
    "event_ref_is_truth": False,
}

CAPTURE_POLICY = {
    "registered_source_paths_only": True,
    "registered_selectors_only": True,
    "forbidden": (
        "directory enumeration for source selection",
        "recursive file search",
        "Git history reading",
        "semantic search",
        "model-assisted search",
        "related-file expansion",
        "SAIPEN ticket search",
        "automatic neighbouring LOG records",
    ),
    "selector_kinds": {
        MARKDOWN_SECTION: "exact heading prefix match to the next '## D-' boundary",
        LOG_RECORD: "exactly one canonical LOG line carrying the exact [E-N] token",
        WHOLE_FILE: "the complete source text, no normalisation",
    },
    "observed_at_authority": "REGISTERED_PILOT_METADATA_NEVER_INFERRED_FROM_FILESYSTEM",
    "source_change_rule": "PROJECT_PILOT_SOURCE_CHANGED_FAIL_CLOSED_NO_RECOVERY_V0",
}

NETWORK_MODEL_POLICY = {
    "live_model_calls_allowed": 0,
    "network_calls_allowed": 0,
    "model_adapter_present": False,
    "saifren_transport_present": False,
    "nine_router_transport_present": False,
}

PERSISTENCE_POLICY = {
    "lab_only": True,
    "authorized_by": "SRC-051 operator handoff",
    "not_a_project_corpus_store": True,
    "production_persistence_api": False,
    "artifact_forbidden_content": (
        "credentials",
        "personal profile",
        "ALLY_ADVICE content",
        "model output",
        "private mail",
    ),
}


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode("utf-8"))


def canonical_registration_bytes(document) -> bytes:
    """The exact canonical byte representation whose digest is REGISTRATION_ID."""
    return (json.dumps(document, ensure_ascii=False, separators=(",", ":"),
                       sort_keys=True) + "\n").encode("utf-8")


def registration_id_for(raw: bytes) -> str:
    return _sha256_bytes(raw)


def utc_stamp(now: datetime | None = None) -> str:
    moment = now or datetime.now(UTC)
    return moment.strftime("%Y%m%dT%H%M%SZ")


# --------------------------------------------------------------- extraction


def _line_spans(text: str) -> list[tuple[int, int]]:
    """Exact line spans, newline terminators included, no newline rewriting."""
    spans: list[tuple[int, int]] = []
    start = 0
    while start <= len(text):
        newline = text.find("\n", start)
        if newline == -1:
            if start < len(text):
                spans.append((start, len(text)))
            break
        spans.append((start, newline + 1))
        start = newline + 1
    return spans


def _line_body(text: str, start: int, end: int) -> str:
    body = text[start:end]
    body = body.removesuffix("\n")
    body = body.removesuffix("\r")
    return body


def extract_markdown_section(text: str, heading_prefix: str,
                             boundary_prefix: str) -> str:
    """Exact complete markdown section: one exact heading to the next boundary.

    Refuses a missing heading, a duplicate heading and a zero-length section.
    No fuzzy matching: a variant heading is a missing heading.
    """
    if not heading_prefix.startswith(boundary_prefix):
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "a section heading prefix must lie inside its own boundary family")
    spans = _line_spans(text)
    headings = [index for index, (start, end) in enumerate(spans)
                if _line_body(text, start, end).startswith(heading_prefix)]
    if not headings:
        _reject(PROJECT_PILOT_SELECTOR_MISSING,
                f"no exact heading begins with {heading_prefix!r}")
    if len(headings) > 1:
        _reject(PROJECT_PILOT_SELECTOR_DUPLICATE,
                f"heading {heading_prefix!r} appears {len(headings)} times")
    heading = headings[0]
    start = spans[heading][0]
    end = len(text)
    for later in range(heading + 1, len(spans)):
        boundary_start, boundary_end = spans[later]
        if _line_body(text, boundary_start, boundary_end).startswith(boundary_prefix):
            end = boundary_start
            break
    section = text[start:end]
    if section == text[start:spans[heading][1]]:
        _reject(PROJECT_PILOT_SELECTOR_EMPTY,
                f"section {heading_prefix!r} has no body before the next boundary")
    return section


def extract_log_record(text: str, marker: str) -> str:
    """Exactly one canonical LOG line carrying the exact [E-N] token.

    The returned record is the exact source line including its line terminator;
    no neighbouring record is captured and no multiline detail is reconstructed.
    """
    if not _LOG_MARKER_RE.fullmatch(marker):
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "a LOG record marker must be an exact [E-NNN] token")
    spans = _line_spans(text)
    matches = [index for index, (start, end) in enumerate(spans)
               if marker in _line_body(text, start, end)]
    if not matches:
        _reject(PROJECT_PILOT_SELECTOR_MISSING,
                f"no LOG line carries {marker}")
    if len(matches) > 1:
        _reject(PROJECT_PILOT_SELECTOR_DUPLICATE,
                f"{marker} appears in {len(matches)} LOG lines")
    start, end = spans[matches[0]]
    return text[start:end]


def extract_selected_content(text: str, selector) -> str:
    """Apply one validated selector to one exact source text."""
    kind = selector["kind"]
    if kind == MARKDOWN_SECTION:
        return extract_markdown_section(
            text, selector["heading_prefix"], selector["boundary_prefix"])
    if kind == LOG_RECORD:
        return extract_log_record(text, selector["marker"])
    if kind == WHOLE_FILE:
        return text
    _reject(PROJECT_PILOT_REGISTRATION_INVALID, f"unknown selector kind {kind!r}")


# ----------------------------------------------------------- registration


def _relative_source(value) -> str:
    if not isinstance(value, str) or not value.strip():
        _reject(PROJECT_PILOT_REGISTRATION_INVALID, "SOURCE must be non-blank text")
    if "\\" in value or value.startswith("/"):
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "SOURCE must be a relative forward-slash path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "SOURCE must stay inside the project root")
    return value


def _selector(value) -> dict:
    if not isinstance(value, dict):
        _reject(PROJECT_PILOT_REGISTRATION_INVALID, "SELECTOR must be an object")
    kind = value.get("kind")
    if kind == MARKDOWN_SECTION:
        expected = {"kind", "heading_prefix", "boundary_prefix"}
        if set(value) != expected:
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    "a MARKDOWN_SECTION selector carries exactly heading and boundary prefixes")
        heading = value["heading_prefix"]
        boundary = value["boundary_prefix"]
        if (not isinstance(heading, str) or not heading.startswith("## ")
                or not isinstance(boundary, str) or not boundary.startswith("## ")
                or heading == boundary or "\u2014" not in heading
                or not heading.startswith(boundary)):
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    "markdown selector prefixes must be exact '## D-NNN \u2014 ' family "
                    "heading prefixes")
        return dict(value)
    if kind == LOG_RECORD:
        if set(value) != {"kind", "marker"}:
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    "a LOG_RECORD selector carries exactly one marker")
        marker = value["marker"]
        if not isinstance(marker, str) or not _LOG_MARKER_RE.fullmatch(marker):
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    "a LOG_RECORD marker must be an exact [E-NNN] token")
        return dict(value)
    if kind == WHOLE_FILE:
        if set(value) != {"kind"}:
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    "a WHOLE_FILE selector carries no parameters")
        return dict(value)
    _reject(PROJECT_PILOT_REGISTRATION_INVALID, f"unknown selector kind {kind!r}")


@dataclass(frozen=True)
class RegisteredArtifact:
    label: str
    source_kind: str
    source_ref: str
    observed_at: str
    source: str
    selector: dict
    extracted_content_sha256: str


@dataclass(frozen=True)
class RegisteredEvent:
    label: str
    name: str
    members: tuple[str, ...]
    meaning: str


@dataclass(frozen=True)
class PilotRegistration:
    registration_version: str
    project_scope: str
    window_start: str
    window_end: str
    selection_basis: str
    completeness: str
    expected_artifact_count: int
    expected_event_count: int
    artifacts: tuple[RegisteredArtifact, ...]
    events: tuple[RegisteredEvent, ...]
    source_file_sha256: dict
    capture_policy: dict
    grouping_limitation: dict
    network_model_policy: dict
    persistence_policy: dict
    registration_id: str
    canonical_bytes: bytes

    def artifact_for(self, label: str) -> RegisteredArtifact:
        for entry in self.artifacts:
            if entry.label == label:
                return entry
        _reject(PROJECT_PILOT_REGISTRATION_INVALID, f"unknown artifact label {label!r}")

    def event_labels(self) -> tuple[str, ...]:
        return tuple(entry.label for entry in self.events)


def _registration_document(source_root: pathlib.Path, seed_path=None) -> dict:
    """Build the exact canonical document, pins included, before any write."""
    artifacts = []
    pins: dict[str, str] = {}
    for spec in selection_artifacts(seed_path):
        source = _relative_source(spec["source"])
        selector = _selector(spec["selector"])
        path = pathlib.Path(source_root) / source
        try:
            data = _read_source_bytes(path)
        except OSError as exc:
            _reject(PROJECT_PILOT_SOURCE_UNREADABLE,
                    f"registered source {source} cannot be read ({type(exc).__name__})")
        pins.setdefault(source, _sha256_bytes(data))
        text = _decode_source(data, source)
        content = extract_selected_content(text, selector)
        artifacts.append({
            "label": spec["label"],
            "source_kind": spec["source_kind"],
            "source_ref": spec["source_ref"],
            "observed_at": spec["observed_at"],
            "source": source,
            "selector": selector,
            "extracted_content_sha256": _sha256_text(content),
        })
    events = [
        {
            "label": spec["label"],
            "name": spec["name"],
            "members": list(spec["members"]),
            "meaning": spec["meaning"],
        }
        for spec in REGISTERED_EVENTS
    ]
    return {
        "registration_version": PILOT_VERSION,
        "project_scope": "project:saimail",
        "window_start": "2026-09-19T19:30:00Z",
        "window_end": "2026-09-19T21:20:00Z",
        "selection_basis": pc.SELECTION_BASIS,
        "completeness": pc.COMPLETENESS,
        "expected_artifact_count": len(artifacts),
        "expected_event_count": len(events),
        "source_file_sha256": dict(sorted(pins.items())),
        "artifacts": artifacts,
        "events": events,
        "capture_policy": CAPTURE_POLICY,
        "grouping_limitation": GROUPING_LIMITATION,
        "network_model_policy": NETWORK_MODEL_POLICY,
        "persistence_policy": PERSISTENCE_POLICY,
    }


def _decode_source(data: bytes, name: str) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _reject(PROJECT_PILOT_SOURCE_UNREADABLE,
                f"registered source {name} is not strict UTF-8")
    if text.startswith("\ufeff"):
        _reject(PROJECT_PILOT_SOURCE_UNREADABLE,
                f"registered source {name} carries a BOM")
    return text


def _read_source_bytes(path: pathlib.Path) -> bytes:
    """The single read seam: read-only, one exact registered file."""
    return pathlib.Path(path).read_bytes()


def freeze_registration(path, source_root, seed_path=None) -> PilotRegistration:
    """Write the immutable registration once; identical bytes converge."""
    document = _registration_document(pathlib.Path(source_root), seed_path)
    raw = canonical_registration_bytes(document)
    publish_immutable(pathlib.Path(path), raw,
                      conflict_code=PROJECT_PILOT_REGISTRATION_CHANGED)
    return load_registration(path)


def load_registration(path) -> PilotRegistration:
    """Load and fully validate one canonical registration; fail closed."""
    try:
        raw = pathlib.Path(path).read_bytes()
    except OSError as exc:
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                f"registration cannot be read ({type(exc).__name__})")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "registration must be one strict UTF-8 JSON document")
    if canonical_registration_bytes(document) != raw:
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "registration bytes are not the exact canonical representation")
    return _registration_from_document(document, raw)


def _registration_from_document(document, raw: bytes) -> PilotRegistration:
    expected_keys = {
        "registration_version", "project_scope", "window_start", "window_end",
        "selection_basis", "completeness", "expected_artifact_count",
        "expected_event_count", "source_file_sha256", "artifacts", "events",
        "capture_policy", "grouping_limitation", "network_model_policy",
        "persistence_policy",
    }
    if not isinstance(document, dict) or set(document) != expected_keys:
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "registration carries exactly the frozen pilot fields")
    if document["registration_version"] != PILOT_VERSION:
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                f"registration_version must be exactly {PILOT_VERSION}")
    if (not isinstance(document["project_scope"], str)
            or not _PROJECT_SCOPE_RE.fullmatch(document["project_scope"])):
        _reject(pc.PROJECT_CORPUS_BAD_SCOPE,
                "registration PROJECT_SCOPE must be a canonical project: token")
    for field in ("window_start", "window_end"):
        value = document[field]
        if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    f"{field} must be exact UTC YYYY-MM-DDTHH:MM:SSZ")
    if document["selection_basis"] != pc.SELECTION_BASIS:
        _reject(pc.PROJECT_CORPUS_SELECTION_BASIS_REFUSED,
                f"SELECTION_BASIS must be exactly {pc.SELECTION_BASIS}")
    if document["completeness"] != pc.COMPLETENESS:
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                f"COMPLETENESS must stay {pc.COMPLETENESS}")

    artifacts = []
    seen_labels: set[str] = set()
    for entry in document["artifacts"]:
        if not isinstance(entry, dict):
            _reject(PROJECT_PILOT_REGISTRATION_INVALID, "every artifact is an object")
        expected_artifact_keys = {
            "label", "source_kind", "source_ref", "observed_at", "source",
            "selector", "extracted_content_sha256",
        }
        if set(entry) != expected_artifact_keys:
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    "an artifact carries exactly the frozen pilot fields")
        label = entry["label"]
        if not isinstance(label, str) or not label.startswith("A") or label in seen_labels:
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    f"artifact labels are unique A-labels, got {label!r}")
        seen_labels.add(label)
        if entry["source_kind"] not in pc.SOURCE_KINDS:
            _reject(pc.PROJECT_CORPUS_SOURCE_KIND_UNKNOWN,
                    f"SOURCE_KIND must be one of the frozen v0 kinds {pc.SOURCE_KINDS}")
        source_ref = entry["source_ref"]
        if not isinstance(source_ref, str) or not source_ref.strip():
            _reject(PROJECT_PILOT_REGISTRATION_INVALID, "SOURCE_REF must be non-blank text")
        observed_at = entry["observed_at"]
        if not isinstance(observed_at, str) or not _UTC_RE.fullmatch(observed_at):
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    "OBSERVED_AT must be exact registered UTC metadata")
        pin = entry["extracted_content_sha256"]
        if not isinstance(pin, str) or not _SHA_RE.fullmatch(pin):
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    "EXTRACTED_CONTENT_SHA256 must be a sha256: pin")
        artifacts.append(RegisteredArtifact(
            label=label,
            source_kind=entry["source_kind"],
            source_ref=source_ref,
            observed_at=observed_at,
            source=_relative_source(entry["source"]),
            selector=_selector(entry["selector"]),
            extracted_content_sha256=pin,
        ))

    if len(artifacts) != document["expected_artifact_count"]:
        _reject(PROJECT_PILOT_ARTIFACT_COUNT_MISMATCH,
                "the registered artifact count is a frozen exact shape")
    pins = document["source_file_sha256"]
    if not isinstance(pins, dict) or not pins:
        _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                "SOURCE_FILE_SHA256 must pin every distinct source file")
    for source, value in pins.items():
        _relative_source(source)
        if not isinstance(value, str) or not _SHA_RE.fullmatch(value):
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    f"source pin for {source} must be a sha256: pin")
    for entry in artifacts:
        if entry.source not in pins:
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    f"every artifact source is pinned; {entry.source} is not")

    events = []
    seen_event_labels: set[str] = set()
    assignment: dict[str, str] = {}
    for entry in document["events"]:
        if not isinstance(entry, dict):
            _reject(PROJECT_PILOT_REGISTRATION_INVALID, "every event is an object")
        if set(entry) != {"label", "name", "members", "meaning"}:
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    "an event carries exactly the frozen pilot fields")
        label = entry["label"]
        if (not isinstance(label, str) or not label.startswith("P")
                or label in seen_event_labels):
            _reject(PROJECT_PILOT_REGISTRATION_INVALID,
                    f"event labels are unique P-labels, got {label!r}")
        seen_event_labels.add(label)
        members = entry["members"]
        if not isinstance(members, list) or not members:
            _reject(pc.PROJECT_CORPUS_EMPTY_EVENT,
                    "an event declaration needs at least one member")
        for member in members:
            if member not in seen_labels:
                _reject(PROJECT_PILOT_UNKNOWN_EVENT_MEMBER,
                        f"event {label} names an unregistered artifact {member!r}")
            if member in assignment:
                _reject(PROJECT_PILOT_ARTIFACT_MULTI_EVENT,
                        f"artifact {member} belongs to two events")
            assignment[member] = label
        events.append(RegisteredEvent(
            label=label,
            name=entry["name"],
            members=tuple(members),
            meaning=entry["meaning"],
        ))
    if len(events) != document["expected_event_count"]:
        _reject(PROJECT_PILOT_EVENT_COUNT_MISMATCH,
                "the registered event count is a frozen exact shape")
    unassigned = sorted(seen_labels - set(assignment))
    if unassigned:
        _reject(PROJECT_PILOT_ARTIFACT_UNASSIGNED,
                f"every artifact belongs to exactly one event; {unassigned[0]} belongs to none")

    return PilotRegistration(
        registration_version=document["registration_version"],
        project_scope=document["project_scope"],
        window_start=document["window_start"],
        window_end=document["window_end"],
        selection_basis=document["selection_basis"],
        completeness=document["completeness"],
        expected_artifact_count=document["expected_artifact_count"],
        expected_event_count=document["expected_event_count"],
        artifacts=tuple(artifacts),
        events=tuple(events),
        source_file_sha256=dict(pins),
        capture_policy=dict(document["capture_policy"]),
        grouping_limitation=dict(document["grouping_limitation"]),
        network_model_policy=dict(document["network_model_policy"]),
        persistence_policy=dict(document["persistence_policy"]),
        registration_id=registration_id_for(raw),
        canonical_bytes=bytes(raw),
    )


# ---------------------------------------------------------------- capture


@dataclass(frozen=True)
class PilotCapture:
    registration: PilotRegistration
    artifacts: tuple[pc.ProjectArtifact, ...]
    source_hashes_before: dict
    source_hashes_after: dict
    source_recovery: tuple[tuple[str, str], ...]
    read_paths: tuple[str, ...]


def source_hashes(registration: PilotRegistration, source_root) -> dict:
    """Recompute every registered source-file pin; the only read seam used."""
    root = pathlib.Path(source_root)
    hashes = {}
    for source in registration.source_file_sha256:
        try:
            data = _read_source_bytes(root / source)
        except OSError as exc:
            _reject(PROJECT_PILOT_SOURCE_UNREADABLE,
                    f"registered source {source} cannot be read ({type(exc).__name__})")
        hashes[source] = _sha256_bytes(data)
    return hashes


def _prove_append_only_recovery(registration: PilotRegistration,
                                source: str, root: pathlib.Path) -> str:
    """The one narrow recovery rule: a journal that only grew.

    Every registered selector on this source must be a LOG journal selector and
    must still extract bytes whose digest equals the frozen content pin; then the
    growth changed nothing registered and the recovery is recorded, never silent.
    Any other difference refuses with the strict source-change code.
    """
    entries = [entry for entry in registration.artifacts
               if entry.source == source]
    if not entries or not all(
            entry.selector["kind"] == LOG_RECORD for entry in entries):
        _reject(PROJECT_PILOT_SOURCE_CHANGED,
                f"registered source {source} changed since the registration was "
                "frozen; only an append-only journal can be recovered and this "
                "source has no journal selectors")
    for entry in entries:
        data = _read_source_bytes(root / source)
        text = _decode_source(data, source)
        content = extract_selected_content(text, entry.selector)
        if _sha256_text(content) != entry.extracted_content_sha256:
            _reject(PROJECT_PILOT_SOURCE_CHANGED,
                    f"the journal source {source} changed and its registered record "
                    f"for {entry.label} no longer matches the frozen content pin")
    return APPEND_ONLY_CONTENT_PIN_MATCH


def capture_registered_artifacts(registration: PilotRegistration,
                                 source_root) -> PilotCapture:
    """Read exactly the registered sources, extract exactly the registered bytes."""
    root = pathlib.Path(source_root)
    before = source_hashes(registration, root)
    recovery = []
    for source, pinned in registration.source_file_sha256.items():
        if before[source] != pinned:
            recovery.append(
                (source, _prove_append_only_recovery(registration, source, root)))
    artifacts = []
    read_paths = []
    for entry in registration.artifacts:
        data = _read_source_bytes(root / entry.source)
        read_paths.append(entry.source)
        text = _decode_source(data, entry.source)
        content = extract_selected_content(text, entry.selector)
        if _sha256_text(content) != entry.extracted_content_sha256:
            _reject(PROJECT_PILOT_SOURCE_CHANGED,
                    f"the selected content of {entry.source} for {entry.label} no "
                    "longer matches its registered pin")
        artifacts.append(pc.ProjectArtifact(
            project_scope=registration.project_scope,
            source_kind=entry.source_kind,
            source_ref=entry.source_ref,
            observed_at=entry.observed_at,
            content=content,
        ))
    after = source_hashes(registration, root)
    if before != after:
        _reject(PROJECT_PILOT_SOURCE_MUTATED,
                "a registered source changed during capture; the pilot observes "
                "history and never rewrites it")
    return PilotCapture(
        registration=registration,
        artifacts=tuple(artifacts),
        source_hashes_before=before,
        source_hashes_after=after,
        source_recovery=tuple(recovery),
        read_paths=tuple(read_paths),
    )


def declarations_for(capture: PilotCapture) -> tuple[pc.ProjectEventDeclaration, ...]:
    """Translate registered P-labels into exact EVIDENCE_REF membership.

    Only minted evidence refs enter a declaration; the manifest label itself
    never reaches the identity of an event.
    """
    by_label = {entry.label: artifact
                for entry, artifact in zip(capture.registration.artifacts,
                                           capture.artifacts, strict=True)}
    declarations = []
    for event in capture.registration.events:
        members = tuple(pc.project_evidence_ref(by_label[label])
                        for label in event.members)
        declarations.append(pc.ProjectEventDeclaration(
            project_scope=capture.registration.project_scope,
            member_evidence_refs=members,
        ))
    return tuple(declarations)


@dataclass(frozen=True)
class PilotResult:
    """One real pilot build: the exact B-017 proof plus bounded labelling."""

    registration: PilotRegistration
    built: pc.BuiltProjectCorpus
    capture: PilotCapture
    artifact_labels: tuple[tuple[str, str], ...]
    evidence_labels: tuple[tuple[str, str], ...]
    artifact_event_labels: tuple[tuple[str, str], ...]
    event_labels: tuple[tuple[str, tuple[str, ...]], ...]
    event_refs_by_label: tuple[tuple[str, str], ...]

    def evidence_ref_for(self, label: str) -> str:
        return dict(self.evidence_labels)[label]

    def event_ref_for_artifact(self, label: str) -> str:
        return dict(self.artifact_event_labels)[label]

    def event_ref_for_event(self, label: str) -> str:
        return dict(self.event_refs_by_label)[label]


def _label_maps(capture: PilotCapture,
                built: pc.BuiltProjectCorpus) -> tuple:
    receipts = {entry.evidence_ref: entry for entry in built.receipts()}
    artifact_labels = []
    evidence_labels = []
    artifact_event_labels = []
    for entry, artifact in zip(capture.registration.artifacts, capture.artifacts,
                               strict=True):
        evidence_ref = pc.project_evidence_ref(artifact)
        receipt = receipts[evidence_ref]
        artifact_labels.append((entry.label, artifact.source_ref))
        evidence_labels.append((entry.label, evidence_ref))
        artifact_event_labels.append((entry.label, receipt.event_ref))
    event_refs_by_label = []
    for event, declaration in zip(capture.registration.events,
                                  built.request.event_declarations, strict=True):
        event_refs_by_label.append((event.label, declaration.computed_event_ref))
    event_labels = tuple(
        (event.label, event.members) for event in capture.registration.events)
    return (tuple(artifact_labels), tuple(evidence_labels),
            tuple(artifact_event_labels), event_labels,
            tuple(event_refs_by_label))


def build_pilot_corpus(registration: PilotRegistration, source_root) -> PilotResult:
    """Capture the registered sources, then build through B-017 only."""
    capture = capture_registered_artifacts(registration, source_root)
    declarations = declarations_for(capture)
    request = pc.ProjectCorpusRequest(
        project_scope=registration.project_scope,
        window_start=registration.window_start,
        window_end=registration.window_end,
        selection_basis=registration.selection_basis,
        artifacts=capture.artifacts,
        event_declarations=declarations,
    )
    built = pc.build_project_corpus(request)
    if (built.artifact_count != registration.expected_artifact_count
            or built.event_count != registration.expected_event_count):
        _reject(PROJECT_PILOT_ARTIFACT_COUNT_MISMATCH,
                "the built corpus shape is not the registered exact shape")
    maps = _label_maps(capture, built)
    return PilotResult(
        registration=registration,
        built=built,
        capture=capture,
        artifact_labels=maps[0],
        evidence_labels=maps[1],
        artifact_event_labels=maps[2],
        event_labels=maps[3],
        event_refs_by_label=maps[4],
    )


# ------------------------------------------------------- projection/report


def pilot_artifact_document(result: PilotResult, stamp: str) -> dict:
    """The explicit lab snapshot: provenance, exact content, identities, limits."""
    built = result.built
    event_by_label = {label: ref for label, ref in result.event_refs_by_label}
    receipts = {entry.evidence_ref: entry for entry in built.receipts()}
    artifacts = []
    for entry, artifact in zip(
            result.registration.artifacts, result.capture.artifacts, strict=True):
        evidence_ref = pc.project_evidence_ref(artifact)
        receipt = receipts[evidence_ref]
        artifacts.append({
            "label": entry.label,
            "source_kind": entry.source_kind,
            "source_ref": entry.source_ref,
            "observed_at": entry.observed_at,
            "source": entry.source,
            "selector": entry.selector,
            "source_file_sha256": result.registration.source_file_sha256[entry.source],
            "extracted_content_sha256": entry.extracted_content_sha256,
            "evidence_ref": evidence_ref,
            "event_label": next(label for label, ref in result.artifact_event_labels
                                if label == entry.label),
            "event_ref": receipt.event_ref,
            "content": artifact.content,
            "content_sha256": _sha256_text(artifact.content),
        })
    events = []
    for event in result.registration.events:
        events.append({
            "label": event.label,
            "name": event.name,
            "members": list(event.members),
            "meaning": event.meaning,
            "event_ref": event_by_label[event.label],
            "member_evidence_refs": [
                evidence for label, evidence in result.evidence_labels
                if label in event.members],
        })
    return {
        "pilot_version": PILOT_VERSION,
        "registration_id": result.registration.registration_id,
        "registration_version": result.registration.registration_version,
        "stamp": stamp,
        "project_scope": built.project_scope,
        "window_start": built.window_start,
        "window_end": built.window_end,
        "selection_basis": built.selection_basis,
        "completeness": result.registration.completeness,
        "expected_artifact_count": result.registration.expected_artifact_count,
        "expected_event_count": result.registration.expected_event_count,
        "artifact_count": built.artifact_count,
        "event_count": built.event_count,
        "build_id": built.build_id,
        "corpus_id": built.corpus_id,
        "artifacts": artifacts,
        "events": events,
        "source_file_sha256": dict(result.registration.source_file_sha256),
        "capture_policy": dict(result.registration.capture_policy),
        "grouping_limitation": dict(result.registration.grouping_limitation),
        "network_model_policy": dict(result.registration.network_model_policy),
        "persistence_policy": dict(result.registration.persistence_policy),
        "limitations": [
            "completeness is NOT_PROVEN: EXPLICIT_BOUNDED_SET selection only",
            "the five event declarations are explicit operator-authorized grouping",
            "the grouping does not prove P1..P5 are causally independent",
            "one ticket never equals one event",
            "no behavioural, personal or semantic pattern is claimed",
            "EVENT_REF_IS_TRUTH = false",
        ],
        "no_model_network_proof": {
            "live_model_calls": 0,
            "network_calls": 0,
            "transport_invocations": 0,
        },
        "no_mail_attention_proof": {
            "human_private_conversions": 0,
            "seals": 0,
            "store_deliveries": 0,
            "attention_admissions": 0,
            "hlet1_created": 0,
            "henv1_created": 0,
        },
        "source_immutability": {
            "before": dict(result.capture.source_hashes_before),
            "after": dict(result.capture.source_hashes_after),
            "unchanged_during_capture": result.capture.source_hashes_before
            == result.capture.source_hashes_after,
            "source_recovery": [
                {"source": source, "reason": reason}
                for source, reason in result.capture.source_recovery],
        },
    }


def render_report(result: PilotResult, stamp: str, artifact_name: str) -> str:
    """Human-readable pilot report: exact selection, identities and limits."""
    built = result.built
    evidence_by_label = dict(result.evidence_labels)
    event_by_label = dict(result.event_refs_by_label)
    lines = [
        f"# PROJECT CORPUS PILOT REPORT {stamp}",
        "",
        "Status: REAL PROJECT CORPUS PILOT (B-018 / SRC-051). One immutable",
        "registration was frozen before capture; one BuiltProjectCorpus was minted",
        "through the B-017 builder; no live model, network, mail or attention path",
        "was invoked.",
        "",
        "## Exact selection",
        "",
        f"- PROJECT_SCOPE = {built.project_scope}",
        f"- WINDOW_START = {built.window_start}",
        f"- WINDOW_END = {built.window_end} (half-open: START <= OBSERVED_AT < END)",
        f"- SELECTION_BASIS = {built.selection_basis}",
        f"- COMPLETENESS = {result.registration.completeness}",
        (f"- expected artifacts = {result.registration.expected_artifact_count},"
         f" built = {built.artifact_count}"),
        (f"- expected events = {result.registration.expected_event_count},"
         f" built = {built.event_count}"),
        f"- lab snapshot = {artifact_name}",
        "",
        "## Identities",
        "",
        f"- REGISTRATION_ID = {result.registration.registration_id}",
        f"- BUILD_ID = {built.build_id}",
        f"- CORPUS_ID = {built.corpus_id}",
        "",
        "## Artifact mappings (A1..A8)",
        "",
        "| label | source kind | source ref | observed at | source | evidence ref | event |",
        "|---|---|---|---|---|---|---|",
    ]
    for entry, artifact in zip(result.registration.artifacts,
                               result.capture.artifacts, strict=True):
        lines.append(
            f"| {entry.label} | {entry.source_kind} | {entry.source_ref} |"
            f" {entry.observed_at} | {entry.source} | {evidence_by_label[entry.label]}"
            f" | {result.event_ref_for_artifact(entry.label)} |")
    lines.extend(["", "## Event mappings (P1..P5)", "",
                  "| label | name | members | event ref |", "|---|---|---|---|"])
    for event in result.registration.events:
        lines.append(
            f"| {event.label} | {event.name} | {', '.join(event.members)} |"
            f" {event_by_label[event.label]} |")
    lines.extend([
        "",
        "## Grouping limitation",
        "",
        "These five event declarations are explicit operator-authorized grouping",
        "for this pilot. They do NOT prove:",
        "",
        "- those are objectively the only events;",
        "- P1..P5 are causally independent;",
        "- one ticket always equals one event;",
        "- every relevant occurrence was selected;",
        "- the grouping proves any behavioural pattern.",
        "",
        "Preserved: EVENT_REF_IS_TRUTH = false. COMPLETENESS is NOT_PROVEN and no",
        "claim in this report describes the selection as complete or representative.",
        "This pilot is deliberately narrow: not all SAIMAIL history, not all relevant",
        "project evidence, not all failures, not all successful work, not all",
        "operator behaviour and not a personal profile.",
        "",
        "## Source hash pins and capture exactness",
        "",
        "| source | source file sha256 |", "|---|---|",
    ])
    for source, pin in sorted(result.registration.source_file_sha256.items()):
        lines.append(f"| {source} | {pin} |")
    lines.extend([
        "",
        "Every artifact's extracted content hash equals its frozen registration pin;",
        "the A5 whole-file capture is the exact registered report bytes below the",
        "B-017 per-item ceiling (no markdown normalization, no newline rewriting).",
        "",
        "## Reproducibility",
        "",
        "Deterministic rebuilds (same process and two fresh processes) reproduce the",
        "same evidence-ref mapping, event-ref mapping, BUILD_ID and CORPUS_ID; the",
        "pilot refuses to build at all when a registered source or selected content pin",
        "changed. Temporary fixture mutation controls live in the focused tests; the",
        "real registered sources were re-hashed unchanged after the pilot run.",
        "",
        "## Mutation controls (focused tests, temporary fixture copies only)",
        "",
        ("- one byte changed in the registered D-047 section -> old registration"
         " refuses (PROJECT_PILOT_SOURCE_CHANGED);"),
        "- the E-726 LOG record modified -> old registration refuses;",
        "- moving A8 into P4 changes the event-ref mapping, BUILD_ID and CORPUS_ID;",
        "- removing A4 refuses (registered count is a frozen exact shape);",
        "- OBSERVED_AT = WINDOW_END refuses (PROJECT_CORPUS_WINDOW_EXCLUDED);",
        "- an unknown source kind refuses (PROJECT_CORPUS_SOURCE_KIND_UNKNOWN).",
        "",
        "## B-016 structural compatibility",
        "",
        "The real BuiltProjectCorpus.reflection_corpus accepted a deterministic fake",
        "candidate citing evidence from two declared events and reached the semantic",
        "reviewer. The frozen partition's largest declared event holds two artifacts,",
        "while B-012 requires three distinct observed refs, so the one-declared-event",
        "control ran against a temporary explicitly regrouped registration copy over the",
        "same real sources and was refused with ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS",
        "and zero reviewer calls. A raw ReflectionCorpus still fails the future-pilot",
        "proof gate with PROJECT_CORPUS_BUILDER_PROOF_REQUIRED, and the generic B-016",
        "path is unchanged.",
        "",
        "## No-model / no-network proof",
        "",
        "No model adapter, SAIFREN transport, 9router transport, socket or HTTP path",
        "exists in the pilot module or was invoked by it: 0 live calls. The artifact",
        "and this report are deterministic projections; the in-process",
        "BuiltProjectCorpus type-state, not the JSON, is the proof.",
        "",
        "## No mail / attention side effect",
        "",
        "0 calls to reviewed_ally_to_human_private, seal_human_private,",
        "HumanPrivateStore.deliver and AttentionQueue.admit_receiver_candidate; no",
        "HLET1, no HENV1, no human-attention state.",
        "",
        "## Source immutability",
        "",
        "The pilot observes history and does not rewrite it: pre-capture and",
        "post-capture source hashes are identical. The T-63 historical report was",
        "read read-only and remains byte-identical.",
        "",
        "## Source pin status",
        "",
    ])
    if result.capture.source_recovery:
        lines.extend([
            "Append-only journal recovery applied (registered content pins proven",
            "byte-identical; no new content was extracted):",
            "",
        ])
        for source, reason in result.capture.source_recovery:
            lines.append(f"- {source}: {reason}")
    else:
        lines.append("No pin recovery was needed: every registered source file still")
        lines.append("matches its frozen SHA-256 pin exactly.")
    lines.extend([
        "",
        "## What this run does not show",
        "",
        "No completeness, no semantic pattern, no user or personality claim, no",
        "EVENT_REF truth claim and no model-quality claim. The corpus is tested as",
        "data-provenance infrastructure only.",
        "",
    ])
    return "\n".join(lines)


def run_pilot(registration: PilotRegistration, source_root, out_dir,
              *, stamp: str | None = None) -> tuple[PilotResult, pathlib.Path,
                                                     pathlib.Path]:
    """One real pilot run: capture, build, deterministic recheck, publish lab files."""
    result = build_pilot_corpus(registration, source_root)
    rebuild = build_pilot_corpus(registration, source_root)
    if (rebuild.built.build_id != result.built.build_id
            or rebuild.built.corpus_id != result.built.corpus_id
            or rebuild.evidence_labels != result.evidence_labels
            or rebuild.event_refs_by_label != result.event_refs_by_label):
        _reject(PROJECT_PILOT_REPRODUCIBILITY_FAILED,
                "a deterministic rebuild of the same registration and sources "
                "produced different identities")
    stamp = stamp or utc_stamp()
    out = pathlib.Path(out_dir)
    artifact_name = ARTIFACT_TEMPLATE.format(stamp=stamp)
    report_name = REPORT_TEMPLATE.format(stamp=stamp)
    document = pilot_artifact_document(result, stamp)
    artifact_bytes = (json.dumps(document, ensure_ascii=False, indent=2,
                                 sort_keys=True) + "\n").encode("utf-8")
    report_bytes = render_report(result, stamp, artifact_name).encode("utf-8")
    publish_immutable(out / artifact_name, artifact_bytes,
                      conflict_code=PROJECT_PILOT_ARTIFACT_CHANGED)
    publish_immutable(out / report_name, report_bytes,
                      conflict_code=PROJECT_PILOT_ARTIFACT_CHANGED)
    return result, out / artifact_name, out / report_name


def _cli(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--register", action="store_true",
                        help="freeze the immutable pilot registration")
    parser.add_argument("--run", action="store_true",
                        help="capture the registered sources and build one corpus")
    parser.add_argument("--root", default=str(pathlib.Path(__file__).resolve().parent.parent),
                        help="project root holding the registered sources")
    parser.add_argument("--out", default=None, help="artifact output directory")
    parser.add_argument("--stamp", default=None, help="UTC stamp override for tests")
    args = parser.parse_args(argv)
    root = pathlib.Path(args.root)
    if args.register:
        registration = freeze_registration(root / "lab" / REGISTRATION_FILE, root)
        print(f"REGISTRATION_ID = {registration.registration_id}")
        return 0
    if args.run:
        registration = load_registration(root / "lab" / REGISTRATION_FILE)
        out = pathlib.Path(args.out) if args.out else root / "lab" / "out"
        result, artifact_path, report_path = run_pilot(
            registration, root, out, stamp=args.stamp)
        print(f"BUILD_ID = {result.built.build_id}")
        print(f"CORPUS_ID = {result.built.corpus_id}")
        print(artifact_path)
        print(report_path)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
