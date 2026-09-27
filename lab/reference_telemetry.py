"""REFERENCE-TELEMETRY-1: offline diagnosis of candidate evidence refs.

The defect class this module makes observable without retaining text: **a
rejected candidate whose one offending reference is gone.** T-74's durable
metadata proves `outside_ref_count = 1` and nothing else -- the raw ref was
never persisted, so the exact historical failure class is UNKNOWN and stays
that way. This layer classifies FUTURE outputs and synthetic controls instead.

Two pure observation levels, and no third:

``observe_raw_references(observed, counterevidence, corpus=...)``
    classifies explicitly supplied raw values. It parses no JSON and no prose,
    and it never walks a model-output document hunting for ref-shaped strings.
``observe_candidate_references(candidate, corpus)``
    classifies exactly ``candidate.observed[*].evidence_refs`` and
    ``candidate.counterevidence[*].evidence_refs`` of an already-valid
    ``AllyAdvice`` against one explicitly supplied ``ReflectionCorpus``. It
    builds no second ``AllyAdvice`` parser.

The closed classification is identity, never semantics: a token is a known
corpus evidence ref, a declared event ref used as evidence, the corpus id used
as evidence, an unknown canonical ref, malformed text, or non-text.
``UNKNOWN_REF != MALFORMED_REF`` and ``EVENT_REF != EVIDENCE_REF``.

``REFERENCE_TELEMETRY != ACCEPTANCE``. The observer reports; the unchanged
product gate decides. Nothing here opens a file, walks a directory, reads
repository history, queries SAIPEN or the network, invokes a model, resolves
refs globally, or repairs anything: no lowercasing, no prefix addition, no
whitespace trimming, no nearest-ref matching. Unknown or malformed tokens keep
at most a domain-separated fingerprint, never plaintext.
"""

from __future__ import annotations

import hashlib
import json
import re

from lab.parse_shape import validate as validate_closed_schema
from sailang.errors import SailangError
from saimail.ally_advice import (
    MAX_COUNTEREVIDENCE,
    MAX_EVIDENCE_REFS_PER_ITEM,
    MAX_OBSERVATIONS,
    AllyAdvice,
)
from saimail.ally_generation import (
    MIN_DISTINCT_OBSERVED_EVENTS,
    ReflectionCorpus,
)

CONTRACT_VERSION = "REFERENCE-TELEMETRY-1"

FINGERPRINT_DOMAIN = b"SAIMAIL-REFERENCE-TELEMETRY1\x00"

OBSERVED = "OBSERVED"
COUNTEREVIDENCE = "COUNTEREVIDENCE"
FIELDS = (OBSERVED, COUNTEREVIDENCE)

KNOWN_EVIDENCE_REF = "KNOWN_EVIDENCE_REF"
KNOWN_EVENT_REF_AS_EVIDENCE = "KNOWN_EVENT_REF_AS_EVIDENCE"
CORPUS_ID_AS_EVIDENCE = "CORPUS_ID_AS_EVIDENCE"
UNKNOWN_CANONICAL_REF = "UNKNOWN_CANONICAL_REF"
MALFORMED_REF = "MALFORMED_REF"
NON_TEXT_REF = "NON_TEXT_REF"
REFERENCE_CLASSES = (
    KNOWN_EVIDENCE_REF,
    KNOWN_EVENT_REF_AS_EVIDENCE,
    CORPUS_ID_AS_EVIDENCE,
    UNKNOWN_CANONICAL_REF,
    MALFORMED_REF,
    NON_TEXT_REF,
)

CLEAN = "CLEAN"
HAS_OUTSIDE_CANONICAL = "HAS_OUTSIDE_CANONICAL"
HAS_IDENTIFIER_TYPE_CONFUSION = "HAS_IDENTIFIER_TYPE_CONFUSION"
HAS_MALFORMED = "HAS_MALFORMED"
HAS_NON_TEXT = "HAS_NON_TEXT"
MIXED_INVALID = "MIXED_INVALID"
CORPUS_REF_RELATIONS = (
    CLEAN,
    HAS_OUTSIDE_CANONICAL,
    HAS_IDENTIFIER_TYPE_CONFUSION,
    HAS_MALFORMED,
    HAS_NON_TEXT,
    MIXED_INVALID,
)

MET = "MET"
NOT_MET = "NOT_MET"
NOT_EVALUABLE = "NOT_EVALUABLE"
EVENT_FLOOR_RELATIONS = (MET, NOT_MET, NOT_EVALUABLE)

#: One invalid category -> its own relation; several -> MIXED_INVALID.
CLASS_INVALID_CATEGORY = {
    UNKNOWN_CANONICAL_REF: HAS_OUTSIDE_CANONICAL,
    KNOWN_EVENT_REF_AS_EVIDENCE: HAS_IDENTIFIER_TYPE_CONFUSION,
    CORPUS_ID_AS_EVIDENCE: HAS_IDENTIFIER_TYPE_CONFUSION,
    MALFORMED_REF: HAS_MALFORMED,
    NON_TEXT_REF: HAS_NON_TEXT,
}

#: The maximum reference occurrences one valid AllyAdvice candidate can carry.
MAX_REF_OCCURRENCES = (
    MAX_OBSERVATIONS * MAX_EVIDENCE_REFS_PER_ITEM
    + MAX_COUNTEREVIDENCE * MAX_EVIDENCE_REFS_PER_ITEM
)

REFERENCE_TELEMETRY_BAD_INPUT = "REFERENCE_TELEMETRY_BAD_INPUT"
REFERENCE_TELEMETRY_BAD_CORPUS = "REFERENCE_TELEMETRY_BAD_CORPUS"
REFERENCE_TELEMETRY_CAP_EXCEEDED = "REFERENCE_TELEMETRY_CAP_EXCEEDED"
REFERENCE_TELEMETRY_SCHEMA_REFUSED = "REFERENCE_TELEMETRY_SCHEMA_REFUSED"

_SHA_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

TELEMETRY_SCHEMA = {
    "version": frozenset({CONTRACT_VERSION}),
    "observed_ref_occurrences": int,
    "observed_unique_ref_tokens": int,
    "counterevidence_ref_occurrences": int,
    "counterevidence_unique_ref_tokens": int,
    "known_evidence_ref_count": int,
    "known_event_ref_as_evidence_count": int,
    "corpus_id_as_evidence_count": int,
    "unknown_canonical_ref_count": int,
    "malformed_ref_count": int,
    "non_text_ref_count": int,
    "unknown_or_invalid_ref_count": int,
    "observed_unknown_or_invalid_ref_count": int,
    "counterevidence_unknown_or_invalid_ref_count": int,
    "known_observed_evidence_ref_count": int,
    "known_observed_distinct_event_count": int,
    "event_floor_relation": frozenset(EVENT_FLOOR_RELATIONS),
    "corpus_ref_relation": frozenset(CORPUS_REF_RELATIONS),
    "unknown_or_invalid_unique_token_count": int,
    "unknown_or_invalid_fingerprints": ("list", ("regex", r"[0-9a-f]{64}"),
                                        MAX_REF_OCCURRENCES),
}


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _require_corpus(corpus) -> ReflectionCorpus | None:
    if corpus is None:
        return None
    if not isinstance(corpus, ReflectionCorpus):
        _reject(REFERENCE_TELEMETRY_BAD_CORPUS,
                "membership exists only against one explicitly supplied ReflectionCorpus")
    return corpus


def _declared_event_refs(corpus: ReflectionCorpus) -> frozenset[str]:
    return frozenset(item.event_ref for item in corpus.items)


def classify_reference_value(value, corpus: ReflectionCorpus | None = None) -> str:
    """The one closed classification of a raw reference value.

    Identity only, in fixed precedence: corpus evidence membership, declared
    event ref, corpus id, canonical-shape unknown, malformed, non-text. No
    close match, no repair, no normalization. With no corpus, corpus identity
    cannot be established and a canonical token is an unknown canonical ref.
    """
    corpus = _require_corpus(corpus)
    if not isinstance(value, str):
        return NON_TEXT_REF
    if corpus is not None:
        if value in corpus.refs():
            return KNOWN_EVIDENCE_REF
        if value in _declared_event_refs(corpus):
            return KNOWN_EVENT_REF_AS_EVIDENCE
        if value == corpus.corpus_id:
            return CORPUS_ID_AS_EVIDENCE
    if _SHA_REF_RE.fullmatch(value):
        return UNKNOWN_CANONICAL_REF
    return MALFORMED_REF


def reference_fingerprint(token: str) -> str:
    """The domain-separated fingerprint of one exact text token, never plaintext."""
    if not isinstance(token, str):
        _reject(REFERENCE_TELEMETRY_BAD_INPUT, "a fingerprint is defined for text only")
    try:
        raw = token.encode("utf-8")
    except UnicodeEncodeError:
        _reject(REFERENCE_TELEMETRY_BAD_INPUT,
                "a fingerprint requires strict UTF-8 text")
    return hashlib.sha256(FINGERPRINT_DOMAIN + raw).hexdigest()


def _fingerprint_or_none(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return reference_fingerprint(value)
    except SailangError:
        return None


def validate_reference_telemetry_object(value) -> None:
    """The closed recursive schema gate; an unknown key or type refuses."""
    try:
        validate_closed_schema(value, TELEMETRY_SCHEMA)
    except SailangError:
        _reject(
            REFERENCE_TELEMETRY_SCHEMA_REFUSED,
            "telemetry is exactly the closed REFERENCE-TELEMETRY-1 schema",
        )


class ReferenceTelemetry:
    """Immutable bounded diagnostic metadata; never acceptance, never evidence."""

    __slots__ = (
        "corpus_id_as_evidence_count",
        "corpus_ref_relation",
        "counterevidence_ref_occurrences",
        "counterevidence_unique_ref_tokens",
        "counterevidence_unknown_or_invalid_ref_count",
        "event_floor_relation",
        "known_event_ref_as_evidence_count",
        "known_evidence_ref_count",
        "known_observed_distinct_event_count",
        "known_observed_evidence_ref_count",
        "malformed_ref_count",
        "non_text_ref_count",
        "observed_ref_occurrences",
        "observed_unique_ref_tokens",
        "observed_unknown_or_invalid_ref_count",
        "unknown_canonical_ref_count",
        "unknown_or_invalid_fingerprints",
        "unknown_or_invalid_ref_count",
        "unknown_or_invalid_unique_token_count",
        "version",
    )

    def __init__(self, **fields) -> None:
        expected = set(TELEMETRY_SCHEMA)
        if set(fields) != expected:
            _reject(REFERENCE_TELEMETRY_SCHEMA_REFUSED,
                    "telemetry fields are exactly the closed REFERENCE-TELEMETRY-1 schema")
        for name in expected:
            object.__setattr__(self, name, fields[name])
        self.__post_init__()

    def __post_init__(self) -> None:
        fingerprints = self.unknown_or_invalid_fingerprints
        if isinstance(fingerprints, (str, bytes, bytearray)):
            _reject(REFERENCE_TELEMETRY_SCHEMA_REFUSED,
                    "fingerprints are a collection of domain-separated digests")
        fingerprints = tuple(fingerprints)
        if fingerprints != tuple(sorted(set(fingerprints))):
            _reject(REFERENCE_TELEMETRY_SCHEMA_REFUSED,
                    "fingerprints are unique and in canonical lexical order")
        object.__setattr__(self, "unknown_or_invalid_fingerprints", fingerprints)
        validate_reference_telemetry_object(self.to_object())

    def __eq__(self, other) -> bool:
        return isinstance(other, ReferenceTelemetry) and self.to_object() == other.to_object()

    def __hash__(self) -> int:
        return hash((CONTRACT_VERSION, self.unknown_or_invalid_fingerprints,
                     self.observed_ref_occurrences, self.counterevidence_ref_occurrences))

    def to_object(self) -> dict:
        """The exact closed telemetry object; every field, nothing else."""
        return {
            "version": self.version,
            "observed_ref_occurrences": self.observed_ref_occurrences,
            "observed_unique_ref_tokens": self.observed_unique_ref_tokens,
            "counterevidence_ref_occurrences": self.counterevidence_ref_occurrences,
            "counterevidence_unique_ref_tokens": self.counterevidence_unique_ref_tokens,
            "known_evidence_ref_count": self.known_evidence_ref_count,
            "known_event_ref_as_evidence_count": self.known_event_ref_as_evidence_count,
            "corpus_id_as_evidence_count": self.corpus_id_as_evidence_count,
            "unknown_canonical_ref_count": self.unknown_canonical_ref_count,
            "malformed_ref_count": self.malformed_ref_count,
            "non_text_ref_count": self.non_text_ref_count,
            "unknown_or_invalid_ref_count": self.unknown_or_invalid_ref_count,
            "observed_unknown_or_invalid_ref_count":
                self.observed_unknown_or_invalid_ref_count,
            "counterevidence_unknown_or_invalid_ref_count":
                self.counterevidence_unknown_or_invalid_ref_count,
            "known_observed_evidence_ref_count":
                self.known_observed_evidence_ref_count,
            "known_observed_distinct_event_count":
                self.known_observed_distinct_event_count,
            "event_floor_relation": self.event_floor_relation,
            "corpus_ref_relation": self.corpus_ref_relation,
            "unknown_or_invalid_unique_token_count":
                self.unknown_or_invalid_unique_token_count,
            "unknown_or_invalid_fingerprints": list(self.unknown_or_invalid_fingerprints),
        }


def serialize_reference_telemetry(result: ReferenceTelemetry) -> bytes:
    """Canonical closed-schema bytes; the validated projection, nothing else."""
    if not isinstance(result, ReferenceTelemetry):
        _reject(REFERENCE_TELEMETRY_BAD_INPUT,
                "serialization requires a ReferenceTelemetry result")
    value = result.to_object()
    validate_reference_telemetry_object(value)
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                       sort_keys=True) + "\n").encode("utf-8")


def _observe(observed_values: tuple, counterevidence_values: tuple,
             corpus: ReflectionCorpus | None) -> ReferenceTelemetry:
    counts = {name: 0 for name in REFERENCE_CLASSES}
    occurrences = {OBSERVED: len(observed_values),
                   COUNTEREVIDENCE: len(counterevidence_values)}
    unique_tokens = {}
    invalid_per_field = {}
    fingerprints: set[str] = set()
    observed_classes = []
    for field, values in ((OBSERVED, observed_values),
                          (COUNTEREVIDENCE, counterevidence_values)):
        tokens = set()
        invalid = 0
        for value in values:
            reference_class = classify_reference_value(value, corpus)
            counts[reference_class] += 1
            if field == OBSERVED:
                observed_classes.append(reference_class)
            if isinstance(value, str):
                tokens.add(value)
            if reference_class != KNOWN_EVIDENCE_REF:
                invalid += 1
                fingerprint = _fingerprint_or_none(value)
                if fingerprint is not None:
                    fingerprints.add(fingerprint)
        unique_tokens[field] = len(tokens)
        invalid_per_field[field] = invalid

    unknown_or_invalid = sum(
        counts[name] for name in REFERENCE_CLASSES if name != KNOWN_EVIDENCE_REF)

    known_observed = [value for value, reference_class
                      in zip(observed_values, observed_classes)
                      if reference_class == KNOWN_EVIDENCE_REF]
    if any(reference_class != KNOWN_EVIDENCE_REF
           for reference_class in observed_classes):
        event_floor_relation = NOT_EVALUABLE
    else:
        distinct_events = len({
            corpus.event_ref_for(value) for value in known_observed
        }) if corpus is not None else 0
        event_floor_relation = (
            MET if distinct_events >= MIN_DISTINCT_OBSERVED_EVENTS else NOT_MET)

    categories = {
        CLASS_INVALID_CATEGORY[name] for name, count in counts.items()
        if count and name != KNOWN_EVIDENCE_REF
    }
    if not categories:
        corpus_ref_relation = CLEAN
    elif len(categories) == 1:
        corpus_ref_relation = next(iter(categories))
    else:
        corpus_ref_relation = MIXED_INVALID

    return ReferenceTelemetry(
        version=CONTRACT_VERSION,
        observed_ref_occurrences=occurrences[OBSERVED],
        observed_unique_ref_tokens=unique_tokens[OBSERVED],
        counterevidence_ref_occurrences=occurrences[COUNTEREVIDENCE],
        counterevidence_unique_ref_tokens=unique_tokens[COUNTEREVIDENCE],
        known_evidence_ref_count=counts[KNOWN_EVIDENCE_REF],
        known_event_ref_as_evidence_count=counts[KNOWN_EVENT_REF_AS_EVIDENCE],
        corpus_id_as_evidence_count=counts[CORPUS_ID_AS_EVIDENCE],
        unknown_canonical_ref_count=counts[UNKNOWN_CANONICAL_REF],
        malformed_ref_count=counts[MALFORMED_REF],
        non_text_ref_count=counts[NON_TEXT_REF],
        unknown_or_invalid_ref_count=unknown_or_invalid,
        observed_unknown_or_invalid_ref_count=invalid_per_field[OBSERVED],
        counterevidence_unknown_or_invalid_ref_count=invalid_per_field[COUNTEREVIDENCE],
        known_observed_evidence_ref_count=len(known_observed),
        known_observed_distinct_event_count=(
            len({corpus.event_ref_for(value) for value in known_observed})
            if corpus is not None else 0),
        event_floor_relation=event_floor_relation,
        corpus_ref_relation=corpus_ref_relation,
        unknown_or_invalid_unique_token_count=len(fingerprints),
        unknown_or_invalid_fingerprints=tuple(sorted(fingerprints)),
    )


def _collect(name: str, values) -> tuple:
    if isinstance(values, (str, bytes, bytearray)):
        _reject(REFERENCE_TELEMETRY_BAD_INPUT,
                f"{name} must be a collection of raw reference values")
    try:
        return tuple(values)
    except TypeError:
        _reject(REFERENCE_TELEMETRY_BAD_INPUT, f"{name} must be iterable")


def observe_raw_references(observed, counterevidence, *,
                           corpus: ReflectionCorpus | None = None) -> ReferenceTelemetry:
    """Classify explicitly supplied raw ref values under one field identity.

    No JSON parsing, no prose parsing, no document traversal: the caller names
    every value. The total token count is bounded by one valid AllyAdvice
    candidate's maximum reference occurrences; overflow refuses.
    """
    corpus = _require_corpus(corpus)
    observed_values = _collect(OBSERVED, observed)
    counterevidence_values = _collect(COUNTEREVIDENCE, counterevidence)
    total = len(observed_values) + len(counterevidence_values)
    if total > MAX_REF_OCCURRENCES:
        _reject(
            REFERENCE_TELEMETRY_CAP_EXCEEDED,
            f"raw observation exceeds {MAX_REF_OCCURRENCES} reference occurrences; "
            "overflow refuses, never truncates",
        )
    return _observe(observed_values, counterevidence_values, corpus)


def observe_candidate_references(candidate: AllyAdvice,
                                 corpus: ReflectionCorpus) -> ReferenceTelemetry:
    """Classify exactly the refs of one already-valid AllyAdvice candidate.

    The candidate reached this call through the unchanged structural gate; this
    function does not re-parse it. Membership is checked only against the
    supplied corpus. The returned bounded metadata is the FG-04B surface: a
    future parsed response can be diagnosed without persisting raw refs.
    """
    if not isinstance(candidate, AllyAdvice):
        _reject(REFERENCE_TELEMETRY_BAD_INPUT,
                "candidate observation requires one already-valid AllyAdvice")
    if not isinstance(corpus, ReflectionCorpus):
        _reject(REFERENCE_TELEMETRY_BAD_CORPUS,
                "candidate observation requires one explicit ReflectionCorpus")
    observed_values = tuple(ref for item in candidate.observed
                            for ref in item.evidence_refs)
    counterevidence_values = tuple(ref for item in candidate.counterevidence
                                   for ref in item.evidence_refs)
    return _observe(observed_values, counterevidence_values, corpus)


__all__ = [
    "CLASS_INVALID_CATEGORY",
    "CLEAN",
    "CONTRACT_VERSION",
    "CORPUS_ID_AS_EVIDENCE",
    "CORPUS_REF_RELATIONS",
    "COUNTEREVIDENCE",
    "EVENT_FLOOR_RELATIONS",
    "FIELDS",
    "FINGERPRINT_DOMAIN",
    "HAS_IDENTIFIER_TYPE_CONFUSION",
    "HAS_MALFORMED",
    "HAS_NON_TEXT",
    "HAS_OUTSIDE_CANONICAL",
    "KNOWN_EVENT_REF_AS_EVIDENCE",
    "KNOWN_EVIDENCE_REF",
    "MALFORMED_REF",
    "MAX_REF_OCCURRENCES",
    "MET",
    "MIN_DISTINCT_OBSERVED_EVENTS",
    "MIXED_INVALID",
    "NON_TEXT_REF",
    "NOT_EVALUABLE",
    "NOT_MET",
    "OBSERVED",
    "REFERENCE_CLASSES",
    "REFERENCE_TELEMETRY_BAD_CORPUS",
    "REFERENCE_TELEMETRY_BAD_INPUT",
    "REFERENCE_TELEMETRY_CAP_EXCEEDED",
    "REFERENCE_TELEMETRY_SCHEMA_REFUSED",
    "TELEMETRY_SCHEMA",
    "UNKNOWN_CANONICAL_REF",
    "ReferenceTelemetry",
    "classify_reference_value",
    "observe_candidate_references",
    "observe_raw_references",
    "reference_fingerprint",
    "serialize_reference_telemetry",
    "validate_reference_telemetry_object",
]
