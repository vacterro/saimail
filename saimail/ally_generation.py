"""ALLY_ADVICE generation v0: bounded, caller-supplied and review-bound.

This layer sits above the completed B-012 ALLY1 contract.  It never discovers
history: the caller supplies one bounded, in-memory ``ReflectionCorpus`` and
the generation layer may inspect only the objects in it.  One orchestration
call invokes at most one generator and at most one independent reviewer; the
reviewer sees the exact candidate and the full normalized corpus, receives no
generator hidden reasoning, and every semantic dimension must be ``PASS``
before a non-transferable ``SemanticallyReviewedAllyAdvice`` type-state is
minted.

The gate does not prove that a pattern is real, that an observation is true,
that evidence semantically entails the prose, that counterevidence is
globally strongest, that motive or flattery detection was perfect, that the
advice is novel or useful, or that any reviewer or model is correct.  It
provides explicit source bounds, full-corpus review visibility, semantic
separation, a separate review invocation, fail-closed uncertainty, no
automatic rewrite loop and provenance of what was reviewed.  A silent
``NO_ADVICE`` outcome is a first-class successful result.

The defect class the event identity closes: **a repeated pattern asserted from
one occurrence's paperwork.**  ``EVIDENCE_REF`` identifies one evidence
artifact; it never identified the operational event the artifact describes, so
three artifacts of ONE incident satisfied the artifact floor and read as
repetition.  The caller now declares an ``EVENT_REF`` beside every
``EVIDENCE_REF``, the corpus identity binds it, and autonomously generated
advice must cite at least ``MIN_DISTINCT_OBSERVED_EVENTS`` distinct declared
events before the semantic reviewer is invoked.  This is a structural
independence floor, not epistemology: ``EVENT_REF_IS_TRUTH = false`` and
``DISTINCT_EVENT_REFS != SEMANTIC_PATTERN_PROOF``.

A ``SemanticReviewReport`` is data, not proof: the reviewed type-state is
minted only from a ``ReviewInvocationResult``, which exists only because one
actual ``reviewer.review`` call happened.  A ``PASS`` on
``OBSERVATION_SUPPORT`` or ``COUNTEREVIDENCE_ADEQUACY`` must cite at least one
corpus ref; the ref is what the reviewer says informed the verdict, never
semantic proof that it is entailed.

The module has no store, no network, no model adapter, no provider selection
and no automation: sealing, durable storage and receiver admission remain
explicit later acts.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import InitVar, dataclass, field
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from sailang.errors import SailangError

from .ally_advice import (
    EXISTS,
    MISSING,
    AllyAdvice,
    EvidenceResolvedAllyAdvice,
    ally_to_human_private,
    resolve_ally_evidence,
)
from .sailetter import HumanPrivateLetter

RUBRIC_VERSION = "ALLY-REVIEW-1"

PROJECT_OPERATIONAL = "PROJECT_OPERATIONAL"

NO_ADVICE = "NO_ADVICE"
CANDIDATE = "CANDIDATE"
GENERATOR_RESULT_KINDS = (NO_ADVICE, CANDIDATE)

APPROVED = "APPROVED"
REJECTED = "REJECTED"
ERROR = "ERROR"
OUTCOME_STATUSES = (NO_ADVICE, APPROVED, REJECTED, ERROR)

PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"
REVIEW_VERDICTS = (PASS, FAIL, UNKNOWN)

OBSERVATION_SUPPORT = "OBSERVATION_SUPPORT"
COUNTEREVIDENCE_ADEQUACY = "COUNTEREVIDENCE_ADEQUACY"
SCOPE_DISCIPLINE = "SCOPE_DISCIPLINE"
NO_MOTIVE_INFERENCE = "NO_MOTIVE_INFERENCE"
NO_FLATTERY = "NO_FLATTERY"
NO_COMPLIANCE_PRESSURE = "NO_COMPLIANCE_PRESSURE"
UNCERTAINTY_ADEQUACY = "UNCERTAINTY_ADEQUACY"
RECIPIENT_AGENCY = "RECIPIENT_AGENCY"
DIMENSIONS = (
    OBSERVATION_SUPPORT,
    COUNTEREVIDENCE_ADEQUACY,
    SCOPE_DISCIPLINE,
    NO_MOTIVE_INFERENCE,
    NO_FLATTERY,
    NO_COMPLIANCE_PRESSURE,
    UNCERTAINTY_ADEQUACY,
    RECIPIENT_AGENCY,
)

#: Dimensions whose ``PASS`` must cite at least one corpus evidence ref: the
#: reviewer claims to have assessed supplied evidence, so an evidence-free
#: ``PASS`` leaves no auditable trace of what it relied on.  Purely
#: prose-semantic dimensions stay optional.
EVIDENCE_REQUIRED_DIMENSIONS = (OBSERVATION_SUPPORT, COUNTEREVIDENCE_ADEQUACY)

MAX_ITEMS = 64
MAX_ITEM_BYTES = 8_192
MAX_TOTAL_CONTENT_BYTES = 131_072
MAX_SCOPE_BYTES = 512
MAX_RATIONALE_BYTES = 1_024
MAX_TOTAL_RATIONALE_BYTES = 8_192

#: Structural recurrence floor for autonomously generated repeated-pattern
#: advice: support must span at least this many distinct declared events.
MIN_DISTINCT_OBSERVED_EVENTS = 2

CORPUS_ID_DOMAIN = b"SAIMAIL-ALLY-GENERATION-CORPUS1\x00"
CANDIDATE_ID_DOMAIN = b"SAIMAIL-ALLY-GENERATION-CANDIDATE1\x00"

ALLY_GEN_BAD_INPUT = "ALLY_GEN_BAD_INPUT"
ALLY_GEN_BAD_ITEM = "ALLY_GEN_BAD_ITEM"
ALLY_GEN_SOURCE_DOMAIN_REFUSED = "ALLY_GEN_SOURCE_DOMAIN_REFUSED"
ALLY_GEN_ITEM_OVERSIZE = "ALLY_GEN_ITEM_OVERSIZE"
ALLY_GEN_CORPUS_OVERSIZE = "ALLY_GEN_CORPUS_OVERSIZE"
ALLY_GEN_DUPLICATE_EVIDENCE_REF = "ALLY_GEN_DUPLICATE_EVIDENCE_REF"
ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS = "ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS"
ALLY_GEN_BAD_CORPUS = "ALLY_GEN_BAD_CORPUS"
ALLY_GEN_BAD_GENERATOR = "ALLY_GEN_BAD_GENERATOR"
ALLY_GEN_BAD_RESULT = "ALLY_GEN_BAD_RESULT"
ALLY_GEN_PROVIDER_ERROR = "ALLY_GEN_PROVIDER_ERROR"
ALLY_GEN_BAD_REVIEWER = "ALLY_GEN_BAD_REVIEWER"
ALLY_GEN_REVIEWER_ERROR = "ALLY_GEN_REVIEWER_ERROR"
ALLY_GENERATED_REF_OUTSIDE_CORPUS = "ALLY_GENERATED_REF_OUTSIDE_CORPUS"
ALLY_GEN_BAD_REPORT = "ALLY_GEN_BAD_REPORT"
ALLY_GEN_REVIEW_DIMENSION_MISSING = "ALLY_GEN_REVIEW_DIMENSION_MISSING"
ALLY_GEN_REVIEW_DIMENSION_UNKNOWN = "ALLY_GEN_REVIEW_DIMENSION_UNKNOWN"
ALLY_GEN_REVIEW_DIMENSION_DUPLICATE = "ALLY_GEN_REVIEW_DIMENSION_DUPLICATE"
ALLY_GEN_REVIEW_VERDICT_INVALID = "ALLY_GEN_REVIEW_VERDICT_INVALID"
ALLY_GEN_REVIEW_RATIONALE_OVERSIZE = "ALLY_GEN_REVIEW_RATIONALE_OVERSIZE"
ALLY_GEN_REVIEW_REF_OUTSIDE_CORPUS = "ALLY_GEN_REVIEW_REF_OUTSIDE_CORPUS"
ALLY_GEN_REVIEW_CANDIDATE_MISMATCH = "ALLY_GEN_REVIEW_CANDIDATE_MISMATCH"
ALLY_GEN_REVIEW_CORPUS_MISMATCH = "ALLY_GEN_REVIEW_CORPUS_MISMATCH"
ALLY_GEN_RUBRIC_MISMATCH = "ALLY_GEN_RUBRIC_MISMATCH"
ALLY_GEN_REVIEW_REJECTED = "ALLY_GEN_REVIEW_REJECTED"
ALLY_GEN_REVIEW_UNCERTAIN = "ALLY_GEN_REVIEW_UNCERTAIN"
ALLY_GEN_REVIEW_EVIDENCE_REQUIRED = "ALLY_GEN_REVIEW_EVIDENCE_REQUIRED"
ALLY_GEN_REVIEW_PROOF_FORGED = "ALLY_GEN_REVIEW_PROOF_FORGED"
ALLY_GEN_PRIVATE_PROOF_REQUIRED = "ALLY_GEN_PRIVATE_PROOF_REQUIRED"

#: A fault of the review invocation itself, mapped to ERROR by the
#: orchestrator; every other invocation failure is a named rejection.
_REVIEW_INVOCATION_FAULT_CODES = (ALLY_GEN_REVIEWER_ERROR, ALLY_GEN_BAD_REPORT)

_EVIDENCE_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _bounded_text(name: str, value, limit: int) -> str:
    if not isinstance(value, str):
        _reject(ALLY_GEN_BAD_ITEM, f"{name} must be text")
    if not value.strip():
        _reject(ALLY_GEN_BAD_ITEM, f"{name} is required and cannot be blank")
    if "\x00" in value:
        _reject(ALLY_GEN_BAD_ITEM, f"{name} cannot contain NUL")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _reject(ALLY_GEN_BAD_ITEM, f"{name} must be well-formed UTF-8 text")
    if len(encoded) > limit:
        _reject(ALLY_GEN_ITEM_OVERSIZE, f"{name} exceeds {limit} UTF-8 bytes")
    return value


def _canonical_utc(name: str, value) -> str:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        _reject(ALLY_GEN_BAD_ITEM, f"{name} must be exact UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        _reject(ALLY_GEN_BAD_ITEM, f"{name} is not a real UTC calendar instant")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _reject(ALLY_GEN_BAD_ITEM, f"{name} is not canonical UTC")
    return value


def _evidence_ref(name: str, value) -> str:
    if not isinstance(value, str) or not _EVIDENCE_REF_RE.fullmatch(value):
        _reject(ALLY_GEN_BAD_ITEM, f"{name} must be sha256:<64 lowercase hex>")
    return value


def _canonical_refs(name: str, value) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)):
        _reject(ALLY_GEN_BAD_ITEM, f"{name} must be a collection of evidence refs")
    try:
        refs = tuple(value)
    except TypeError:
        _reject(ALLY_GEN_BAD_ITEM, f"{name} must be iterable")
    for ref in refs:
        _evidence_ref(name, ref)
    if len(set(refs)) != len(refs):
        _reject(ALLY_GEN_BAD_ITEM, f"{name} contains a duplicate evidence ref")
    if refs != tuple(sorted(refs)):
        _reject(ALLY_GEN_BAD_ITEM, f"{name} must be in canonical lexical order")
    return refs


def _canonical_json(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def _identity(domain: bytes, value) -> str:
    return "sha256:" + hashlib.sha256(domain + _canonical_json(value)).hexdigest()


@dataclass(frozen=True)
class ReflectionItem:
    """One explicit caller-supplied operational evidence item; not memory.

    ``EVIDENCE_REF`` identifies this evidence artifact; ``EVENT_REF`` is the
    caller-declared identity of the underlying operational occurrence/group the
    artifact belongs to.  Several artifacts may share one ``EVENT_REF``; one
    artifact belongs to exactly one declared event in v0.  ``EVENT_REF`` is an
    assertion, never truth, and is never inferred from CONTENT, OBSERVED_AT,
    the evidence ref or a model.
    """

    evidence_ref: str
    source_domain: str
    observed_at: str
    observed_scope: str
    content: str
    event_ref: str

    def __post_init__(self) -> None:
        _evidence_ref("EVIDENCE_REF", self.evidence_ref)
        _evidence_ref("EVENT_REF", self.event_ref)
        if self.source_domain != PROJECT_OPERATIONAL:
            _reject(
                ALLY_GEN_SOURCE_DOMAIN_REFUSED,
                f"SOURCE_DOMAIN must be exactly {PROJECT_OPERATIONAL}; "
                "the source-domain marker is an explicit caller assertion",
            )
        _canonical_utc("OBSERVED_AT", self.observed_at)
        _bounded_text("OBSERVED_SCOPE", self.observed_scope, MAX_SCOPE_BYTES)
        _bounded_text("CONTENT", self.content, MAX_ITEM_BYTES)

    def _object(self) -> dict:
        return {
            "EVIDENCE_REF": self.evidence_ref,
            "EVENT_REF": self.event_ref,
            "SOURCE_DOMAIN": self.source_domain,
            "OBSERVED_AT": self.observed_at,
            "OBSERVED_SCOPE": self.observed_scope,
            "CONTENT": self.content,
        }


@dataclass(frozen=True)
class ReflectionCorpus:
    """One immutable bounded in-memory corpus with a deterministic identity.

    Item order is normalized (evidence ref ascending) and the corpus id binds
    the ordered identities, event declarations, scopes, content bytes and
    source-domain declarations.  Nothing is persisted; a changed item
    invalidates the id; regrouping artifacts across events changes the id.
    """

    items: tuple[ReflectionItem, ...]
    corpus_id: str = field(init=False)

    def __post_init__(self) -> None:
        if isinstance(self.items, (str, bytes, bytearray)):
            _reject(ALLY_GEN_BAD_CORPUS, "ITEMS must be a collection of ReflectionItem")
        try:
            items = tuple(self.items)
        except TypeError:
            _reject(ALLY_GEN_BAD_CORPUS, "ITEMS must be iterable")
        if not all(isinstance(item, ReflectionItem) for item in items):
            _reject(ALLY_GEN_BAD_CORPUS, "every corpus item must be a ReflectionItem")
        if len(items) > MAX_ITEMS:
            _reject(
                ALLY_GEN_CORPUS_OVERSIZE,
                f"corpus exceeds {MAX_ITEMS} items; overflow refuses, never truncates",
            )
        refs = [item.evidence_ref for item in items]
        if len(set(refs)) != len(refs):
            _reject(
                ALLY_GEN_DUPLICATE_EVIDENCE_REF,
                "duplicate evidence ref in corpus",
            )
        total = sum(len(item.content.encode("utf-8")) for item in items)
        if total > MAX_TOTAL_CONTENT_BYTES:
            _reject(
                ALLY_GEN_CORPUS_OVERSIZE,
                f"corpus content exceeds {MAX_TOTAL_CONTENT_BYTES} UTF-8 bytes; "
                "overflow refuses, never truncates",
            )
        ordered = tuple(sorted(items, key=lambda item: item.evidence_ref))
        object.__setattr__(self, "items", ordered)
        object.__setattr__(self, "corpus_id", _identity(
            CORPUS_ID_DOMAIN, [item._object() for item in ordered]))

    def refs(self) -> frozenset[str]:
        return frozenset(item.evidence_ref for item in self.items)

    def item_for(self, evidence_ref: str) -> ReflectionItem | None:
        for item in self.items:
            if item.evidence_ref == evidence_ref:
                return item
        return None

    def event_ref_for(self, evidence_ref: str) -> str | None:
        """The declared EVENT_REF of one corpus artifact, or None if absent."""
        item = self.item_for(evidence_ref)
        return item.event_ref if item is not None else None

    def event_refs_for(self, evidence_refs) -> frozenset[str]:
        """The distinct declared EVENT_REF values behind the given artifact refs.

        Only refs present in this exact corpus contribute; refs outside it are
        the existing membership refusal's business, never grouped here.  No
        clustering, similarity or heuristic grouping exists: the declared
        EVENT_REF is the only source of event identity.
        """
        wanted = set(evidence_refs)
        return frozenset(
            item.event_ref for item in self.items if item.evidence_ref in wanted
        )


@dataclass(frozen=True)
class GeneratorResult:
    """The closed generator result: NO_ADVICE or one canonical candidate."""

    kind: str
    candidate: AllyAdvice | None = None

    def __post_init__(self) -> None:
        if self.kind not in GENERATOR_RESULT_KINDS:
            _reject(ALLY_GEN_BAD_RESULT, f"generator result kind must be one of {GENERATOR_RESULT_KINDS}")
        if self.kind == CANDIDATE:
            if not isinstance(self.candidate, AllyAdvice):
                _reject(ALLY_GEN_BAD_RESULT, "CANDIDATE requires one valid AllyAdvice")
        elif self.candidate is not None:
            _reject(ALLY_GEN_BAD_RESULT, "NO_ADVICE carries no candidate")

    @classmethod
    def no_advice(cls) -> GeneratorResult:
        return cls(NO_ADVICE)

    @classmethod
    def of(cls, candidate: AllyAdvice) -> GeneratorResult:
        return cls(CANDIDATE, candidate)


@runtime_checkable
class AllyAdviceGenerator(Protocol):
    """One bounded generation invocation over the exact supplied corpus."""

    def generate(self, corpus: ReflectionCorpus) -> GeneratorResult:
        """Return NO_ADVICE or one already-valid AllyAdvice candidate."""


@dataclass(frozen=True)
class ReviewVerdict:
    """One dimension verdict with bounded rationale and cited corpus refs.

    A ``PASS`` on an evidence-bearing dimension must cite at least one ref;
    the refs are what the reviewer says informed the verdict, never proof that
    the sources semantically entail it.
    """

    dimension: str
    verdict: str
    rationale: str
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.dimension not in DIMENSIONS:
            _reject(
                ALLY_GEN_REVIEW_DIMENSION_UNKNOWN,
                f"{self.dimension!r} is not a review dimension of rubric {RUBRIC_VERSION}",
            )
        if self.verdict not in REVIEW_VERDICTS:
            _reject(
                ALLY_GEN_REVIEW_VERDICT_INVALID,
                f"verdict must be exactly one of {REVIEW_VERDICTS}",
            )
        if not isinstance(self.rationale, str):
            _reject(ALLY_GEN_BAD_REPORT, "rationale must be text")
        if not self.rationale.strip():
            _reject(ALLY_GEN_BAD_REPORT, "every dimension carries a non-blank rationale")
        try:
            encoded = self.rationale.encode("utf-8")
        except UnicodeEncodeError:
            _reject(ALLY_GEN_BAD_REPORT, "rationale must be well-formed UTF-8 text")
        if len(encoded) > MAX_RATIONALE_BYTES:
            _reject(
                ALLY_GEN_REVIEW_RATIONALE_OVERSIZE,
                f"rationale exceeds {MAX_RATIONALE_BYTES} UTF-8 bytes",
            )
        object.__setattr__(
            self, "evidence_refs", _canonical_refs("REVIEW.EVIDENCE_REFS", self.evidence_refs))
        if (self.verdict == PASS and self.dimension in EVIDENCE_REQUIRED_DIMENSIONS
                and not self.evidence_refs):
            _reject(
                ALLY_GEN_REVIEW_EVIDENCE_REQUIRED,
                f"{self.dimension} PASS must cite at least one corpus evidence ref; "
                "an evidence-free PASS leaves no auditable trace",
            )


@dataclass(frozen=True)
class SemanticReviewReport:
    """One immutable bounded review verdict bound to candidate and corpus ids."""

    candidate_id: str
    corpus_id: str
    rubric_version: str
    verdicts: tuple[ReviewVerdict, ...]

    def __post_init__(self) -> None:
        _evidence_ref("CANDIDATE_ID", self.candidate_id)
        _evidence_ref("CORPUS_ID", self.corpus_id)
        if self.rubric_version != RUBRIC_VERSION:
            _reject(
                ALLY_GEN_RUBRIC_MISMATCH,
                f"RUBRIC_VERSION must be exactly {RUBRIC_VERSION}",
            )
        if isinstance(self.verdicts, (str, bytes, bytearray)):
            _reject(ALLY_GEN_BAD_REPORT, "VERDICTS must be a collection of ReviewVerdict")
        try:
            verdicts = tuple(self.verdicts)
        except TypeError:
            _reject(ALLY_GEN_BAD_REPORT, "VERDICTS must be iterable")
        if not all(isinstance(item, ReviewVerdict) for item in verdicts):
            _reject(ALLY_GEN_BAD_REPORT, "every verdict must be a ReviewVerdict")
        names = [item.dimension for item in verdicts]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            _reject(
                ALLY_GEN_REVIEW_DIMENSION_DUPLICATE,
                f"duplicate review dimension {duplicates[0]!r}",
            )
        unknown = sorted(set(names) - set(DIMENSIONS))
        if unknown:
            _reject(
                ALLY_GEN_REVIEW_DIMENSION_UNKNOWN,
                f"unknown review dimension {unknown[0]!r}",
            )
        missing = sorted(set(DIMENSIONS) - set(names))
        if missing:
            _reject(
                ALLY_GEN_REVIEW_DIMENSION_MISSING,
                f"missing review dimension {missing[0]!r}; all eight are required",
            )
        total = sum(len(item.rationale.encode("utf-8")) for item in verdicts)
        if total > MAX_TOTAL_RATIONALE_BYTES:
            _reject(
                ALLY_GEN_REVIEW_RATIONALE_OVERSIZE,
                f"total rationale exceeds {MAX_TOTAL_RATIONALE_BYTES} UTF-8 bytes",
            )
        object.__setattr__(self, "verdicts", verdicts)

    def verdict_for(self, dimension: str) -> str:
        for item in self.verdicts:
            if item.dimension == dimension:
                return item.verdict
        _reject(ALLY_GEN_REVIEW_DIMENSION_MISSING, f"{dimension!r} is not in this report")


@runtime_checkable
class AllyAdviceSemanticReviewer(Protocol):
    """One independent review invocation over the exact candidate and corpus.

    The interface carries no parameter for generator reasoning, chain of
    thought or a private scratchpad; only the externally visible candidate and
    the full normalized corpus arrive.
    """

    def review(self, evidence_resolved_advice: EvidenceResolvedAllyAdvice,
               corpus: ReflectionCorpus) -> SemanticReviewReport:
        """Return one bounded SemanticReviewReport for the exact pair."""


def ally_candidate_id(advice: AllyAdvice) -> str:
    """Domain-separated identity of one canonical candidate."""
    if not isinstance(advice, AllyAdvice):
        _reject(ALLY_GEN_BAD_INPUT, "candidate identity requires an AllyAdvice")
    return "sha256:" + hashlib.sha256(CANDIDATE_ID_DOMAIN + advice.render()).hexdigest()


def _candidate_refs(candidate: EvidenceResolvedAllyAdvice) -> tuple[str, ...]:
    return tuple(sorted({
        ref
        for item in (*candidate.advice.observed, *candidate.advice.counterevidence)
        for ref in item.evidence_refs
    }))


class CorpusEvidenceResolver:
    """The smallest resolver: EXISTS only for refs in the exact corpus.

    It answers existence within this supplied corpus and nothing else.  No
    global, filesystem or network lookup exists here, and existence never
    claims semantic support.
    """

    def __init__(self, corpus: ReflectionCorpus):
        if not isinstance(corpus, ReflectionCorpus):
            _reject(ALLY_GEN_BAD_CORPUS, "resolver requires one ReflectionCorpus")
        self._refs = corpus.refs()

    def resolve(self, evidence_ref: str) -> str:
        _evidence_ref("EVIDENCE_REF", evidence_ref)
        return EXISTS if evidence_ref in self._refs else MISSING


def _verify_review_binding(
        candidate: EvidenceResolvedAllyAdvice,
        corpus: ReflectionCorpus,
        report: SemanticReviewReport) -> None:
    """Prove the exact candidate/corpus/report binding; fail closed on verdicts."""
    if not isinstance(candidate, EvidenceResolvedAllyAdvice):
        _reject(
            ALLY_GEN_BAD_INPUT,
            "approval requires the existing B-012 EvidenceResolvedAllyAdvice type-state",
        )
    if not isinstance(corpus, ReflectionCorpus):
        _reject(ALLY_GEN_BAD_CORPUS, "approval requires one ReflectionCorpus")
    if not isinstance(report, SemanticReviewReport):
        _reject(ALLY_GEN_BAD_REPORT, "approval requires one SemanticReviewReport")
    corpus_refs = corpus.refs()
    outside = sorted(ref for ref in _candidate_refs(candidate) if ref not in corpus_refs)
    if outside:
        _reject(
            ALLY_GENERATED_REF_OUTSIDE_CORPUS,
            f"candidate cites a ref outside the supplied corpus: {outside[0]}",
        )
    if report.candidate_id != ally_candidate_id(candidate.advice):
        _reject(
            ALLY_GEN_REVIEW_CANDIDATE_MISMATCH,
            "the review report does not bind this exact candidate",
        )
    if report.corpus_id != corpus.corpus_id:
        _reject(
            ALLY_GEN_REVIEW_CORPUS_MISMATCH,
            "the review report does not bind this exact corpus",
        )
    if report.rubric_version != RUBRIC_VERSION:
        _reject(ALLY_GEN_RUBRIC_MISMATCH, f"rubric must be exactly {RUBRIC_VERSION}")
    report_refs = {ref for item in report.verdicts for ref in item.evidence_refs}
    outside = sorted(ref for ref in report_refs if ref not in corpus_refs)
    if outside:
        _reject(
            ALLY_GEN_REVIEW_REF_OUTSIDE_CORPUS,
            f"the review report cites a ref outside the supplied corpus: {outside[0]}",
        )
    for dimension in DIMENSIONS:
        verdict = report.verdict_for(dimension)
        if verdict == FAIL:
            _reject(ALLY_GEN_REVIEW_REJECTED, f"review dimension {dimension} failed")
        if verdict == UNKNOWN:
            _reject(ALLY_GEN_REVIEW_UNCERTAIN, f"review dimension {dimension} is unknown")
        if verdict != PASS:
            _reject(ALLY_GEN_REVIEW_VERDICT_INVALID, f"verdict {verdict!r} is invalid")


_REVIEW_APPROVED = object()
_REVIEW_INVOCATION = object()


@dataclass(frozen=True)
class ReviewInvocationResult:
    """Non-transferable proof that one actual reviewer invocation produced a report.

    Minted only by ``run_semantic_review`` immediately after it called
    ``reviewer.review`` exactly once; it binds the exact candidate, the exact
    corpus and the exact returned report.  The mint is a constructor-only
    ``InitVar`` (the B-012 pattern) and is not retained, so direct construction
    and ``dataclasses.replace`` transplant refuse.  An ordinary
    ``SemanticReviewReport`` is data and never satisfies this boundary.
    """

    candidate: EvidenceResolvedAllyAdvice
    corpus: ReflectionCorpus
    report: SemanticReviewReport
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _REVIEW_INVOCATION:
            _reject(
                ALLY_GEN_REVIEW_PROOF_FORGED,
                "ReviewInvocationResult is minted only by run_semantic_review "
                "after an actual reviewer invocation; the mint is not retained, "
                "so the proof cannot be copied or transplanted",
            )
        _verify_review_binding(self.candidate, self.corpus, self.report)


@dataclass(frozen=True)
class SemanticallyReviewedAllyAdvice:
    """One candidate that passed all dimensions against one exact corpus.

    The type means only that one bounded review invocation found no listed
    disqualifier in this exact candidate against this exact supplied corpus
    under this rubric.  It is not good, true, safe, best or novel advice.
    """

    candidate: EvidenceResolvedAllyAdvice
    corpus: ReflectionCorpus
    report: SemanticReviewReport
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _REVIEW_APPROVED:
            _reject(
                ALLY_GEN_REVIEW_PROOF_FORGED,
                "SemanticallyReviewedAllyAdvice is minted only by "
                "approve_semantic_review from a ReviewInvocationResult "
                "produced by an actual reviewer invocation; the mint is not "
                "retained, so proof cannot be copied or transplanted",
            )
        _verify_review_binding(self.candidate, self.corpus, self.report)


def approve_semantic_review(
        proof: ReviewInvocationResult) -> SemanticallyReviewedAllyAdvice:
    """Mint the reviewed type-state from an actual invocation proof only.

    A caller-constructed ``SemanticReviewReport`` is data, not proof: it can
    never satisfy this boundary, because ``ReviewInvocationResult`` is minted
    only by ``run_semantic_review``.
    """
    if not isinstance(proof, ReviewInvocationResult):
        _reject(
            ALLY_GEN_REVIEW_PROOF_FORGED,
            "approval requires a ReviewInvocationResult minted by an actual "
            "reviewer invocation; report data alone has no approval authority",
        )
    return SemanticallyReviewedAllyAdvice(
        proof.candidate, proof.corpus, proof.report, _REVIEW_APPROVED)


def _invoke_reviewer_once(
        candidate: EvidenceResolvedAllyAdvice,
        corpus: ReflectionCorpus,
        reviewer: AllyAdviceSemanticReviewer) -> SemanticReviewReport:
    """Call ``reviewer.review`` exactly once; a fault never mints a proof."""
    try:
        report = reviewer.review(candidate, corpus)
    except Exception:  # noqa: BLE001 - a reviewer fault is a named failure, not approval
        # The failure maps to a named code without echoing reviewer text,
        # which could carry supplied content.
        _reject(
            ALLY_GEN_REVIEWER_ERROR,
            "the reviewer invocation failed; no invocation proof is minted",
        )
    if not isinstance(report, SemanticReviewReport):
        _reject(
            ALLY_GEN_BAD_REPORT,
            "the reviewer did not return one SemanticReviewReport; "
            "no invocation proof is minted",
        )
    return report


def run_semantic_review(
        candidate: EvidenceResolvedAllyAdvice,
        corpus: ReflectionCorpus,
        reviewer: AllyAdviceSemanticReviewer) -> ReviewInvocationResult:
    """One actual bounded review invocation; the invocation is the mint boundary.

    Validates the exact B-012 resolved candidate and the exact corpus, invokes
    the reviewer exactly once, validates the returned report, binds
    candidate/corpus/report and mints the non-transferable proof.  No
    caller-supplied report can reach this proof, there is no retry, and a
    reviewer fault or a non-report return mints nothing.
    """
    if not isinstance(candidate, EvidenceResolvedAllyAdvice):
        _reject(
            ALLY_GEN_BAD_INPUT,
            "semantic review requires the existing B-012 EvidenceResolvedAllyAdvice type-state",
        )
    if not isinstance(corpus, ReflectionCorpus):
        _reject(ALLY_GEN_BAD_CORPUS, "semantic review requires one ReflectionCorpus")
    if (not isinstance(reviewer, AllyAdviceSemanticReviewer)
            or not callable(getattr(reviewer, "review", None))):
        _reject(
            ALLY_GEN_BAD_REVIEWER,
            "reviewer must implement review(evidence_resolved_advice, corpus) "
            "-> SemanticReviewReport and receives no generator reasoning",
        )
    report = _invoke_reviewer_once(candidate, corpus, reviewer)
    return ReviewInvocationResult(candidate, corpus, report, _REVIEW_INVOCATION)


def reviewed_ally_to_human_private(
        reviewed: SemanticallyReviewedAllyAdvice,
        *,
        recipient_human_id: str) -> HumanPrivateLetter:
    """Convert only semantically reviewed advice into HLET1; sealing stays explicit."""
    if not isinstance(reviewed, SemanticallyReviewedAllyAdvice):
        _reject(
            ALLY_GEN_PRIVATE_PROOF_REQUIRED,
            "the generated private path requires SemanticallyReviewedAllyAdvice; "
            "manually authored B-012 objects keep their own explicit path",
        )
    return ally_to_human_private(reviewed.candidate, recipient_human_id=recipient_human_id)


@dataclass(frozen=True)
class GenerationOutcome:
    """One bounded orchestration result; APPROVED carries the reviewed proof."""

    status: str
    reviewed: SemanticallyReviewedAllyAdvice | None = None
    report: SemanticReviewReport | None = None
    code: str | None = None

    def __post_init__(self) -> None:
        if self.status not in OUTCOME_STATUSES:
            _reject(ALLY_GEN_BAD_RESULT, f"outcome status must be one of {OUTCOME_STATUSES}")
        if self.status == APPROVED:
            if not isinstance(self.reviewed, SemanticallyReviewedAllyAdvice):
                _reject(ALLY_GEN_BAD_RESULT, "APPROVED carries the reviewed type-state")
        elif self.reviewed is not None:
            _reject(ALLY_GEN_BAD_RESULT, f"{self.status} carries no reviewed advice")


def generate_reviewed_ally_advice(
        corpus: ReflectionCorpus,
        generator: AllyAdviceGenerator,
        reviewer: AllyAdviceSemanticReviewer) -> GenerationOutcome:
    """One bounded run: at most one generator call and at most one review call.

    There is no retry, no prompt mutation and no review-driven optimization
    loop; rejection never invokes the generator again, and NO_ADVICE never
    invokes the reviewer at all.  Before any reviewer invocation, observed
    evidence must span at least ``MIN_DISTINCT_OBSERVED_EVENTS`` distinct
    declared ``EVENT_REF`` values: artifact count is not event count, so a
    candidate built from several artifacts of one declared occurrence is
    refused with ``ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS`` and the reviewer is
    never called.  The reviewed type-state is reached only through the actual
    invocation proof minted by ``run_semantic_review``.
    """
    if not isinstance(corpus, ReflectionCorpus):
        _reject(ALLY_GEN_BAD_CORPUS, "orchestration requires one bounded ReflectionCorpus")
    if (not isinstance(generator, AllyAdviceGenerator)
            or not callable(getattr(generator, "generate", None))):
        _reject(
            ALLY_GEN_BAD_GENERATOR,
            "generator must implement generate(corpus) -> GeneratorResult",
        )
    if (not isinstance(reviewer, AllyAdviceSemanticReviewer)
            or not callable(getattr(reviewer, "review", None))):
        _reject(
            ALLY_GEN_BAD_REVIEWER,
            "reviewer must implement review(evidence_resolved_advice, corpus) "
            "-> SemanticReviewReport and receives no generator reasoning",
        )

    try:
        result = generator.generate(corpus)
    except Exception:  # noqa: BLE001 - a provider fault is a named failure, not NO_ADVICE
        # A provider failure is not a deliberate NO_ADVICE.  The failure maps
        # to a named code without echoing provider text, which could carry
        # supplied content.
        return GenerationOutcome(status=ERROR, code=ALLY_GEN_PROVIDER_ERROR)

    if not isinstance(result, GeneratorResult):
        return GenerationOutcome(status=ERROR, code=ALLY_GEN_BAD_RESULT)
    if result.kind == NO_ADVICE:
        return GenerationOutcome(status=NO_ADVICE)
    if result.candidate is None:
        return GenerationOutcome(status=ERROR, code=ALLY_GEN_BAD_RESULT)

    advice = result.candidate
    corpus_refs = corpus.refs()
    outside = sorted({
        ref
        for item in (*advice.observed, *advice.counterevidence)
        for ref in item.evidence_refs
        if ref not in corpus_refs
    })
    if outside:
        return GenerationOutcome(
            status=REJECTED, code=ALLY_GENERATED_REF_OUTSIDE_CORPUS)

    observed_refs = {ref for item in advice.observed for ref in item.evidence_refs}
    if len(corpus.event_refs_for(observed_refs)) < MIN_DISTINCT_OBSERVED_EVENTS:
        return GenerationOutcome(
            status=REJECTED, code=ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS)

    try:
        resolved = resolve_ally_evidence(advice, CorpusEvidenceResolver(corpus))
    except SailangError as exc:
        return GenerationOutcome(status=REJECTED, code=exc.code)

    try:
        proof = run_semantic_review(resolved, corpus, reviewer)
    except SailangError as exc:
        if exc.code in _REVIEW_INVOCATION_FAULT_CODES:
            return GenerationOutcome(status=ERROR, code=exc.code)
        return GenerationOutcome(status=REJECTED, code=exc.code)
    reviewed = approve_semantic_review(proof)
    return GenerationOutcome(status=APPROVED, reviewed=reviewed, report=proof.report)


__all__ = [
    "ALLY_GENERATED_REF_OUTSIDE_CORPUS",
    "ALLY_GEN_BAD_CORPUS",
    "ALLY_GEN_BAD_GENERATOR",
    "ALLY_GEN_BAD_INPUT",
    "ALLY_GEN_BAD_ITEM",
    "ALLY_GEN_BAD_REPORT",
    "ALLY_GEN_BAD_RESULT",
    "ALLY_GEN_BAD_REVIEWER",
    "ALLY_GEN_CORPUS_OVERSIZE",
    "ALLY_GEN_DUPLICATE_EVIDENCE_REF",
    "ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS",
    "ALLY_GEN_ITEM_OVERSIZE",
    "ALLY_GEN_PRIVATE_PROOF_REQUIRED",
    "ALLY_GEN_PROVIDER_ERROR",
    "ALLY_GEN_REVIEWER_ERROR",
    "ALLY_GEN_REVIEW_CANDIDATE_MISMATCH",
    "ALLY_GEN_REVIEW_CORPUS_MISMATCH",
    "ALLY_GEN_REVIEW_DIMENSION_DUPLICATE",
    "ALLY_GEN_REVIEW_DIMENSION_MISSING",
    "ALLY_GEN_REVIEW_DIMENSION_UNKNOWN",
    "ALLY_GEN_REVIEW_EVIDENCE_REQUIRED",
    "ALLY_GEN_REVIEW_PROOF_FORGED",
    "ALLY_GEN_REVIEW_RATIONALE_OVERSIZE",
    "ALLY_GEN_REVIEW_REF_OUTSIDE_CORPUS",
    "ALLY_GEN_REVIEW_REJECTED",
    "ALLY_GEN_REVIEW_UNCERTAIN",
    "ALLY_GEN_REVIEW_VERDICT_INVALID",
    "ALLY_GEN_RUBRIC_MISMATCH",
    "ALLY_GEN_SOURCE_DOMAIN_REFUSED",
    "APPROVED",
    "CANDIDATE",
    "CORPUS_ID_DOMAIN",
    "COUNTEREVIDENCE_ADEQUACY",
    "DIMENSIONS",
    "ERROR",
    "EVIDENCE_REQUIRED_DIMENSIONS",
    "FAIL",
    "GENERATOR_RESULT_KINDS",
    "MAX_ITEMS",
    "MAX_ITEM_BYTES",
    "MAX_RATIONALE_BYTES",
    "MAX_SCOPE_BYTES",
    "MAX_TOTAL_CONTENT_BYTES",
    "MAX_TOTAL_RATIONALE_BYTES",
    "MIN_DISTINCT_OBSERVED_EVENTS",
    "NO_ADVICE",
    "NO_COMPLIANCE_PRESSURE",
    "NO_FLATTERY",
    "NO_MOTIVE_INFERENCE",
    "OBSERVATION_SUPPORT",
    "OUTCOME_STATUSES",
    "PASS",
    "PROJECT_OPERATIONAL",
    "RECIPIENT_AGENCY",
    "REJECTED",
    "REVIEW_VERDICTS",
    "RUBRIC_VERSION",
    "SCOPE_DISCIPLINE",
    "UNCERTAINTY_ADEQUACY",
    "UNKNOWN",
    "AllyAdviceGenerator",
    "AllyAdviceSemanticReviewer",
    "CorpusEvidenceResolver",
    "GenerationOutcome",
    "GeneratorResult",
    "ReflectionCorpus",
    "ReflectionItem",
    "ReviewInvocationResult",
    "ReviewVerdict",
    "SemanticReviewReport",
    "SemanticallyReviewedAllyAdvice",
    "ally_candidate_id",
    "approve_semantic_review",
    "generate_reviewed_ally_advice",
    "reviewed_ally_to_human_private",
    "run_semantic_review",
]
