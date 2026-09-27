"""B-017 project corpus builder: explicit bounded real-project capture policy.

One immutable request carries the exact caller-supplied project captures and
the exact caller-declared event grouping; the builder converts them into the
existing B-016 ``ReflectionCorpus`` and mints a non-transferable
``BuiltProjectCorpus`` proof bound to the exact policy, scope, window,
artifacts and grouping.  The builder discovers nothing: no directory, no
repository metadata, no SAIPEN state, no network, no model, no clock.  Every
capture arrives as data, and every event membership arrives as an explicit
declaration.

The proof means only that this corpus was deterministically built from one
explicit bounded request under this exact policy.  It never means the selection
is complete, unbiased or exhaustive, that the declared grouping is true, or
that a set of distinct declared event refs proves a semantic pattern.  Ticket
ids, filenames, paths and observation times are provenance metadata: none of
them mints or merges an event identity.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import InitVar, dataclass
from datetime import UTC, datetime

from sailang.errors import SailangError

from .ally_generation import (
    MAX_ITEM_BYTES,
    MAX_ITEMS,
    MAX_TOTAL_CONTENT_BYTES,
    PROJECT_OPERATIONAL,
    ReflectionCorpus,
    ReflectionItem,
)

POLICY_VERSION = "PROJECT-CORPUS-1"

SELECTION_BASIS = "EXPLICIT_BOUNDED_SET"
COMPLETENESS = "NOT_PROVEN"

OPERATOR_DECISION = "OPERATOR_DECISION"
SPEC_DECISION = "SPEC_DECISION"
IMPLEMENTATION_CHANGE = "IMPLEMENTATION_CHANGE"
TEST_RESULT = "TEST_RESULT"
REVIEW_FINDING = "REVIEW_FINDING"
INCIDENT = "INCIDENT"
RUNTIME_OBSERVATION = "RUNTIME_OBSERVATION"
SOURCE_KINDS = (
    OPERATOR_DECISION,
    SPEC_DECISION,
    IMPLEMENTATION_CHANGE,
    TEST_RESULT,
    REVIEW_FINDING,
    INCIDENT,
    RUNTIME_OBSERVATION,
)

MAX_PROJECT_SCOPE_BYTES = 512
MAX_SOURCE_REF_BYTES = 512

EVIDENCE_REF_DOMAIN = b"SAIMAIL-PROJECT-ARTIFACT1\x00"
EVENT_REF_DOMAIN = b"SAIMAIL-PROJECT-EVENT1\x00"
BUILD_ID_DOMAIN = b"SAIMAIL-PROJECT-BUILD1\x00"

PROJECT_CORPUS_BAD_ITEM = "PROJECT_CORPUS_BAD_ITEM"
PROJECT_CORPUS_ITEM_OVERSIZE = "PROJECT_CORPUS_ITEM_OVERSIZE"
PROJECT_CORPUS_CORPUS_OVERSIZE = "PROJECT_CORPUS_CORPUS_OVERSIZE"
PROJECT_CORPUS_BAD_REQUEST = "PROJECT_CORPUS_BAD_REQUEST"
PROJECT_CORPUS_SOURCE_KIND_UNKNOWN = "PROJECT_CORPUS_SOURCE_KIND_UNKNOWN"
PROJECT_CORPUS_BAD_SCOPE = "PROJECT_CORPUS_BAD_SCOPE"
PROJECT_CORPUS_SCOPE_MISMATCH = "PROJECT_CORPUS_SCOPE_MISMATCH"
PROJECT_CORPUS_BAD_WINDOW = "PROJECT_CORPUS_BAD_WINDOW"
PROJECT_CORPUS_WINDOW_EXCLUDED = "PROJECT_CORPUS_WINDOW_EXCLUDED"
PROJECT_SOURCE_REF_DUPLICATE = "PROJECT_SOURCE_REF_DUPLICATE"
PROJECT_SOURCE_REF_CONFLICT = "PROJECT_SOURCE_REF_CONFLICT"
PROJECT_CORPUS_BAD_DECLARATION = "PROJECT_CORPUS_BAD_DECLARATION"
PROJECT_CORPUS_EMPTY_EVENT = "PROJECT_CORPUS_EMPTY_EVENT"
PROJECT_CORPUS_DUPLICATE_MEMBER = "PROJECT_CORPUS_DUPLICATE_MEMBER"
PROJECT_CORPUS_UNKNOWN_EVENT_MEMBER = "PROJECT_CORPUS_UNKNOWN_EVENT_MEMBER"
PROJECT_CORPUS_UNASSIGNED_ARTIFACT = "PROJECT_CORPUS_UNASSIGNED_ARTIFACT"
PROJECT_CORPUS_ARTIFACT_MULTI_EVENT = "PROJECT_CORPUS_ARTIFACT_MULTI_EVENT"
PROJECT_CORPUS_SELECTION_BASIS_REFUSED = "PROJECT_CORPUS_SELECTION_BASIS_REFUSED"
PROJECT_CORPUS_PROOF_FORGED = "PROJECT_CORPUS_PROOF_FORGED"
PROJECT_CORPUS_BUILDER_PROOF_REQUIRED = "PROJECT_CORPUS_BUILDER_PROOF_REQUIRED"

_PROJECT_SCOPE_RE = re.compile(r"^project:[a-z0-9][a-z0-9._-]{0,127}$")
_SHA_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _bounded_text(name: str, value, limit: int) -> str:
    if not isinstance(value, str):
        _reject(PROJECT_CORPUS_BAD_ITEM, f"{name} must be text")
    if not value.strip():
        _reject(PROJECT_CORPUS_BAD_ITEM, f"{name} is required and cannot be blank")
    if "\x00" in value:
        _reject(PROJECT_CORPUS_BAD_ITEM, f"{name} cannot contain NUL")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _reject(PROJECT_CORPUS_BAD_ITEM, f"{name} must be well-formed UTF-8 text")
    if len(encoded) > limit:
        _reject(PROJECT_CORPUS_ITEM_OVERSIZE, f"{name} exceeds {limit} UTF-8 bytes")
    return value


def _canonical_utc(name: str, value) -> str:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        _reject(PROJECT_CORPUS_BAD_ITEM, f"{name} must be exact UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        _reject(PROJECT_CORPUS_BAD_ITEM, f"{name} is not a real UTC calendar instant")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _reject(PROJECT_CORPUS_BAD_ITEM, f"{name} is not canonical UTC")
    return value


def _project_scope(name: str, value) -> str:
    if not isinstance(value, str):
        _reject(PROJECT_CORPUS_BAD_ITEM, f"{name} must be text")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _reject(PROJECT_CORPUS_BAD_ITEM, f"{name} must be well-formed UTF-8 text")
    if len(encoded) > MAX_PROJECT_SCOPE_BYTES:
        _reject(PROJECT_CORPUS_ITEM_OVERSIZE,
                f"{name} exceeds {MAX_PROJECT_SCOPE_BYTES} UTF-8 bytes")
    if "\x00" in value or not _PROJECT_SCOPE_RE.fullmatch(value):
        _reject(
            PROJECT_CORPUS_BAD_SCOPE,
            f"{name} must be a bounded canonical token like project:saimail",
        )
    return value


def _source_ref(name: str, value) -> str:
    return _bounded_text(name, value, MAX_SOURCE_REF_BYTES)


def _evidence_ref_value(name: str, value, code: str) -> str:
    if not isinstance(value, str) or not _SHA_REF_RE.fullmatch(value):
        _reject(code, f"{name} must be sha256:<64 lowercase hex>")
    return value


def _canonical_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                       sort_keys=True) + "\n").encode("utf-8")


def _identity(domain: bytes, value) -> str:
    return "sha256:" + hashlib.sha256(domain + _canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ProjectArtifact:
    """One explicit caller-supplied project capture; not a location to crawl.

    ``EVIDENCE_REF`` is not a field: the builder mints it from the exact scope,
    source kind, source ref and content bytes, so two identical captures of one
    source stay one identity while two different sources with identical text
    stay two.  ``OBSERVED_AT`` is informational source time and never
    participates in the evidence identity.
    """

    project_scope: str
    source_kind: str
    source_ref: str
    observed_at: str
    content: str

    def __post_init__(self) -> None:
        _project_scope("PROJECT_SCOPE", self.project_scope)
        if self.source_kind not in SOURCE_KINDS:
            _reject(
                PROJECT_CORPUS_SOURCE_KIND_UNKNOWN,
                f"SOURCE_KIND must be one of the frozen v0 kinds {SOURCE_KINDS}",
            )
        _source_ref("SOURCE_REF", self.source_ref)
        _canonical_utc("OBSERVED_AT", self.observed_at)
        _bounded_text("CONTENT", self.content, MAX_ITEM_BYTES)


def project_evidence_ref(artifact: ProjectArtifact) -> str:
    """Deterministic domain-separated identity of one explicit capture.

    SOURCE_REF participates, so identical text under distinct sources stays
    distinct; content participates as its digest, so a changed capture changes
    identity; OBSERVED_AT and any caller-supplied event claim do not.
    """
    if not isinstance(artifact, ProjectArtifact):
        _reject(PROJECT_CORPUS_BAD_ITEM, "an evidence identity requires one ProjectArtifact")
    return _identity(EVIDENCE_REF_DOMAIN, {
        "PROJECT_SCOPE": artifact.project_scope,
        "SOURCE_KIND": artifact.source_kind,
        "SOURCE_REF": artifact.source_ref,
        "CONTENT_SHA256": hashlib.sha256(artifact.content.encode("utf-8")).hexdigest(),
    })


@dataclass(frozen=True)
class ProjectEventDeclaration:
    """One explicit caller declaration that these captures are one occurrence.

    Membership references minted ``EVIDENCE_REF`` values only; there is no
    ``event_ref`` input, so a caller cannot assert an event identity directly.
    The declaration is an explicit assertion, never truth: it is never derived
    from a ticket id, filename, path, timestamp or text resemblance.
    """

    project_scope: str
    member_evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _project_scope("PROJECT_SCOPE", self.project_scope)
        if isinstance(self.member_evidence_refs, (str, bytes, bytearray)):
            _reject(PROJECT_CORPUS_BAD_DECLARATION,
                    "MEMBER_EVIDENCE_REFS must be a collection of evidence refs")
        try:
            members = tuple(self.member_evidence_refs)
        except TypeError:
            _reject(PROJECT_CORPUS_BAD_DECLARATION, "MEMBER_EVIDENCE_REFS must be iterable")
        if not members:
            _reject(PROJECT_CORPUS_EMPTY_EVENT, "an event declaration needs at least one member")
        for member in members:
            _evidence_ref_value("MEMBER_EVIDENCE_REF", member, PROJECT_CORPUS_BAD_DECLARATION)
        if len(set(members)) != len(members):
            _reject(PROJECT_CORPUS_DUPLICATE_MEMBER,
                    "an event declaration cannot repeat a member evidence ref")
        object.__setattr__(self, "member_evidence_refs", tuple(sorted(members)))

    @property
    def computed_event_ref(self) -> str:
        """The builder-minted event identity of this exact declaration."""
        return project_event_ref(self)


def project_event_ref(declaration: ProjectEventDeclaration) -> str:
    """Deterministic domain-separated identity of one exact declared grouping.

    The same canonical group mints the same identity; any membership change,
    including regrouping one capture into another event, mints a different one.
    """
    if not isinstance(declaration, ProjectEventDeclaration):
        _reject(PROJECT_CORPUS_BAD_DECLARATION,
                "an event identity requires one ProjectEventDeclaration")
    return _identity(EVENT_REF_DOMAIN, {
        "PROJECT_SCOPE": declaration.project_scope,
        "MEMBER_EVIDENCE_REFS": list(declaration.member_evidence_refs),
    })


@dataclass(frozen=True)
class ProjectCorpusRequest:
    """One immutable bounded build request: data, never a location to crawl.

    The request carries the explicit scope, the exact half-open selection
    window, the fixed explicit-bounded-set selection basis, the captures and
    the event declarations.  A stronger completeness claim, a foreign scope, an
    out-of-window capture and a duplicate source ref all refuse at construction.
    """

    project_scope: str
    window_start: str
    window_end: str
    selection_basis: str
    artifacts: tuple[ProjectArtifact, ...]
    event_declarations: tuple[ProjectEventDeclaration, ...]

    def __post_init__(self) -> None:
        _project_scope("PROJECT_SCOPE", self.project_scope)
        _canonical_utc("WINDOW_START", self.window_start)
        _canonical_utc("WINDOW_END", self.window_end)
        if not self.window_start < self.window_end:
            _reject(PROJECT_CORPUS_BAD_WINDOW,
                    "WINDOW_START must be strictly before WINDOW_END")
        if self.selection_basis != SELECTION_BASIS:
            _reject(
                PROJECT_CORPUS_SELECTION_BASIS_REFUSED,
                f"SELECTION_BASIS must be exactly {SELECTION_BASIS}; a stronger "
                "completeness claim is not a machine-trusted v0 value",
            )
        if isinstance(self.artifacts, (str, bytes, bytearray)):
            _reject(PROJECT_CORPUS_BAD_REQUEST, "ARTIFACTS must be a collection")
        try:
            artifacts = tuple(self.artifacts)
        except TypeError:
            _reject(PROJECT_CORPUS_BAD_REQUEST, "ARTIFACTS must be iterable")
        if not all(isinstance(entry, ProjectArtifact) for entry in artifacts):
            _reject(PROJECT_CORPUS_BAD_REQUEST, "every artifact must be a ProjectArtifact")
        if not artifacts:
            _reject(PROJECT_CORPUS_BAD_REQUEST, "a build request needs at least one artifact")
        if len(artifacts) > MAX_ITEMS:
            _reject(
                PROJECT_CORPUS_CORPUS_OVERSIZE,
                f"request exceeds {MAX_ITEMS} items; overflow refuses, never truncates",
            )
        seen_source_refs: dict[str, ProjectArtifact] = {}
        total_bytes = 0
        for entry in artifacts:
            if entry.project_scope != self.project_scope:
                _reject(
                    PROJECT_CORPUS_SCOPE_MISMATCH,
                    "every artifact scope must match the request scope exactly",
                )
            if not self.window_start <= entry.observed_at < self.window_end:
                _reject(
                    PROJECT_CORPUS_WINDOW_EXCLUDED,
                    f"artifact OBSERVED_AT {entry.observed_at} is outside the exact "
                    "half-open selection window; the build refuses rather than "
                    "silently changing the selected set",
                )
            earlier = seen_source_refs.get(entry.source_ref)
            if earlier is not None:
                if earlier == entry:
                    _reject(PROJECT_SOURCE_REF_DUPLICATE,
                            "one upstream source identity appears twice in one build")
                _reject(
                    PROJECT_SOURCE_REF_CONFLICT,
                    "one SOURCE_REF carries two different captures; never silently "
                    "accept two versions of one upstream source identity",
                )
            seen_source_refs[entry.source_ref] = entry
            total_bytes += len(entry.content.encode("utf-8"))
        if total_bytes > MAX_TOTAL_CONTENT_BYTES:
            _reject(
                PROJECT_CORPUS_CORPUS_OVERSIZE,
                f"request content exceeds {MAX_TOTAL_CONTENT_BYTES} UTF-8 bytes; "
                "overflow refuses, never truncates",
            )
        if isinstance(self.event_declarations, (str, bytes, bytearray)):
            _reject(PROJECT_CORPUS_BAD_REQUEST,
                    "EVENT_DECLARATIONS must be a collection of declarations")
        try:
            declarations = tuple(self.event_declarations)
        except TypeError:
            _reject(PROJECT_CORPUS_BAD_REQUEST, "EVENT_DECLARATIONS must be iterable")
        if not all(isinstance(entry, ProjectEventDeclaration) for entry in declarations):
            _reject(PROJECT_CORPUS_BAD_REQUEST,
                    "every event declaration must be a ProjectEventDeclaration")
        for entry in declarations:
            if entry.project_scope != self.project_scope:
                _reject(
                    PROJECT_CORPUS_SCOPE_MISMATCH,
                    "every declaration scope must match the request scope exactly",
                )
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "event_declarations", declarations)


@dataclass(frozen=True)
class ProjectArtifactReceipt:
    """Bounded local provenance metadata for one capture; not part of ALLY1."""

    evidence_ref: str
    event_ref: str
    source_ref: str
    source_kind: str
    observed_at: str


def _partition_map(request: ProjectCorpusRequest) -> dict[str, str]:
    """Prove the declarations exactly partition the selected artifact set."""
    selected = {project_evidence_ref(entry) for entry in request.artifacts}
    membership: dict[str, str] = {}
    for declaration in request.event_declarations:
        event_ref = project_event_ref(declaration)
        for member in declaration.member_evidence_refs:
            if member not in selected:
                _reject(
                    PROJECT_CORPUS_UNKNOWN_EVENT_MEMBER,
                    "an event declaration references an artifact outside the "
                    "selected set; the grouping is not repaired automatically",
                )
            if member in membership:
                _reject(
                    PROJECT_CORPUS_ARTIFACT_MULTI_EVENT,
                    "a selected artifact belongs to two events; v0 requires an "
                    "exact partition",
                )
            membership[member] = event_ref
    unassigned = sorted(selected - set(membership))
    if unassigned:
        _reject(
            PROJECT_CORPUS_UNASSIGNED_ARTIFACT,
            "a selected artifact belongs to no event; v0 requires an exact partition",
        )
    return membership


def _reflection_items(request: ProjectCorpusRequest,
                      membership: dict[str, str]) -> tuple[ReflectionItem, ...]:
    items = []
    for artifact in sorted(request.artifacts, key=project_evidence_ref):
        evidence_ref = project_evidence_ref(artifact)
        items.append(ReflectionItem(
            evidence_ref=evidence_ref,
            source_domain=PROJECT_OPERATIONAL,
            observed_at=artifact.observed_at,
            observed_scope=artifact.project_scope,
            content=artifact.content,
            event_ref=membership[evidence_ref],
        ))
    return tuple(items)


def _build_id_for(request: ProjectCorpusRequest, membership: dict[str, str]) -> str:
    artifacts = [
        {
            "EVIDENCE_REF": project_evidence_ref(artifact),
            "SOURCE_KIND": artifact.source_kind,
            "SOURCE_REF": artifact.source_ref,
            "OBSERVED_AT": artifact.observed_at,
        }
        for artifact in sorted(request.artifacts, key=project_evidence_ref)
    ]
    events = [
        {
            "EVENT_REF": project_event_ref(declaration),
            "MEMBERS": list(declaration.member_evidence_refs),
        }
        for declaration in request.event_declarations
    ]
    events.sort(key=lambda entry: entry["EVENT_REF"])
    return _identity(BUILD_ID_DOMAIN, {
        "POLICY_VERSION": POLICY_VERSION,
        "PROJECT_SCOPE": request.project_scope,
        "WINDOW_START": request.window_start,
        "WINDOW_END": request.window_end,
        "SELECTION_BASIS": request.selection_basis,
        "ARTIFACTS": artifacts,
        "EVENTS": events,
    })


_MINT_TOKEN = object()


@dataclass(frozen=True)
class BuiltProjectCorpus:
    """Non-transferable proof that this exact corpus came from this exact build.

    ``BuiltProjectCorpus`` is minted only by ``build_project_corpus``; direct
    construction and ``dataclasses.replace`` refuse, because the mint token is a
    constructor-only ``InitVar`` that is not retained.  Even a leaked token path
    is checked: the bound ``BUILD_ID`` and corpus identity are recomputed from
    the bound request and must match.  The proof wraps the exact resulting B-016
    ``ReflectionCorpus``; it cannot carry a different corpus, grouping, window
    or artifact set.
    """

    request: ProjectCorpusRequest
    reflection_corpus: ReflectionCorpus
    build_id: str
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _MINT_TOKEN:
            _reject(
                PROJECT_CORPUS_PROOF_FORGED,
                "BuiltProjectCorpus is minted only by build_project_corpus; the "
                "mint is not retained, so the proof cannot be copied or transplanted",
            )
        if not isinstance(self.request, ProjectCorpusRequest):
            _reject(PROJECT_CORPUS_BAD_REQUEST, "a built proof binds one ProjectCorpusRequest")
        if not isinstance(self.reflection_corpus, ReflectionCorpus):
            _reject(PROJECT_CORPUS_BAD_REQUEST, "a built proof binds one ReflectionCorpus")
        _evidence_ref_value("BUILD_ID", self.build_id, PROJECT_CORPUS_PROOF_FORGED)
        membership = _partition_map(self.request)
        if self.build_id != _build_id_for(self.request, membership):
            _reject(
                PROJECT_CORPUS_PROOF_FORGED,
                "the bound BUILD_ID does not match the bound request; the proof "
                "cannot transfer across a changed policy, window or grouping",
            )
        expected = ReflectionCorpus(items=_reflection_items(self.request, membership))
        if self.reflection_corpus.corpus_id != expected.corpus_id:
            _reject(
                PROJECT_CORPUS_PROOF_FORGED,
                "the bound corpus is not the corpus this exact request builds; the "
                "proof cannot transfer across a changed artifact set",
            )

    @property
    def corpus_id(self) -> str:
        return self.reflection_corpus.corpus_id

    @property
    def project_scope(self) -> str:
        return self.request.project_scope

    @property
    def window_start(self) -> str:
        return self.request.window_start

    @property
    def window_end(self) -> str:
        return self.request.window_end

    @property
    def selection_basis(self) -> str:
        return self.request.selection_basis

    @property
    def artifact_count(self) -> int:
        return len(self.request.artifacts)

    @property
    def event_count(self) -> int:
        return len(self.request.event_declarations)

    def evidence_refs(self) -> frozenset[str]:
        return frozenset(project_evidence_ref(entry) for entry in self.request.artifacts)

    def event_refs(self) -> frozenset[str]:
        return frozenset(
            project_event_ref(entry) for entry in self.request.event_declarations)

    def receipts(self) -> tuple[ProjectArtifactReceipt, ...]:
        """Bounded audit metadata: capture, kind, evidence ref and event ref."""
        membership = _partition_map(self.request)
        return tuple(
            ProjectArtifactReceipt(
                evidence_ref=project_evidence_ref(artifact),
                event_ref=membership[project_evidence_ref(artifact)],
                source_ref=artifact.source_ref,
                source_kind=artifact.source_kind,
                observed_at=artifact.observed_at,
            )
            for artifact in sorted(self.request.artifacts, key=project_evidence_ref)
        )

    def evidence_ref_to_event_ref(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            (entry.evidence_ref, entry.event_ref) for entry in self.receipts())

    def source_kind_for(self, evidence_ref: str) -> str:
        for entry in self.receipts():
            if entry.evidence_ref == evidence_ref:
                return entry.source_kind
        _reject(PROJECT_CORPUS_BAD_ITEM,
                "the evidence ref is not part of this built corpus")


def build_project_corpus(request: ProjectCorpusRequest) -> BuiltProjectCorpus:
    """One deterministic bounded build; no discovery, no repair, no truncation.

    Validation order is fixed: artifact and window validation happen at request
    construction, the exact event partition is proven here, event identities and
    the reflection corpus are constructed, ``BUILD_ID`` is minted, and only then
    is the proof minted.  Any refusal leaves no partial result.
    """
    if not isinstance(request, ProjectCorpusRequest):
        _reject(PROJECT_CORPUS_BAD_REQUEST, "a build requires one ProjectCorpusRequest")
    membership = _partition_map(request)
    corpus = ReflectionCorpus(items=_reflection_items(request, membership))
    build_id = _build_id_for(request, membership)
    return BuiltProjectCorpus(request, corpus, build_id, _MINT_TOKEN)


def is_built_project_corpus(value) -> bool:
    """True only for a corpus produced by this explicit builder path."""
    return isinstance(value, BuiltProjectCorpus)


def require_built_project_corpus(value) -> BuiltProjectCorpus:
    """The future real-project pilot gate: a proof-bearing corpus, nothing less.

    A generic B-016 ``ReflectionCorpus`` stays valid for synthetic experiments;
    a real-project ingestion path that needs this gate calls this helper and
    refuses a raw corpus with a named code.
    """
    if not isinstance(value, BuiltProjectCorpus):
        _reject(
            PROJECT_CORPUS_BUILDER_PROOF_REQUIRED,
            "a real-project corpus path requires BuiltProjectCorpus from "
            "build_project_corpus, not an arbitrary ReflectionCorpus",
        )
    return value


__all__ = [
    "BUILD_ID_DOMAIN",
    "COMPLETENESS",
    "EVIDENCE_REF_DOMAIN",
    "EVENT_REF_DOMAIN",
    "IMPLEMENTATION_CHANGE",
    "INCIDENT",
    "MAX_ITEM_BYTES",
    "MAX_ITEMS",
    "MAX_PROJECT_SCOPE_BYTES",
    "MAX_SOURCE_REF_BYTES",
    "MAX_TOTAL_CONTENT_BYTES",
    "OPERATOR_DECISION",
    "POLICY_VERSION",
    "PROJECT_CORPUS_ARTIFACT_MULTI_EVENT",
    "PROJECT_CORPUS_BAD_DECLARATION",
    "PROJECT_CORPUS_BAD_ITEM",
    "PROJECT_CORPUS_BAD_REQUEST",
    "PROJECT_CORPUS_BAD_SCOPE",
    "PROJECT_CORPUS_BAD_WINDOW",
    "PROJECT_CORPUS_BUILDER_PROOF_REQUIRED",
    "PROJECT_CORPUS_CORPUS_OVERSIZE",
    "PROJECT_CORPUS_DUPLICATE_MEMBER",
    "PROJECT_CORPUS_EMPTY_EVENT",
    "PROJECT_CORPUS_ITEM_OVERSIZE",
    "PROJECT_CORPUS_PROOF_FORGED",
    "PROJECT_CORPUS_SCOPE_MISMATCH",
    "PROJECT_CORPUS_SELECTION_BASIS_REFUSED",
    "PROJECT_CORPUS_SOURCE_KIND_UNKNOWN",
    "PROJECT_CORPUS_UNASSIGNED_ARTIFACT",
    "PROJECT_CORPUS_UNKNOWN_EVENT_MEMBER",
    "PROJECT_CORPUS_WINDOW_EXCLUDED",
    "PROJECT_SOURCE_REF_CONFLICT",
    "PROJECT_SOURCE_REF_DUPLICATE",
    "REVIEW_FINDING",
    "RUNTIME_OBSERVATION",
    "SELECTION_BASIS",
    "SOURCE_KINDS",
    "SPEC_DECISION",
    "TEST_RESULT",
    "BuiltProjectCorpus",
    "ProjectArtifact",
    "ProjectArtifactReceipt",
    "ProjectCorpusRequest",
    "ProjectEventDeclaration",
    "build_project_corpus",
    "is_built_project_corpus",
    "project_evidence_ref",
    "project_event_ref",
    "require_built_project_corpus",
]
