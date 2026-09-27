"""ALLY_ADVICE v0: canonical private reflection with evidence-existence gating.

ALLY1 is a SAIMAIL host-protocol plaintext object, not a SAILANG kind and not
evidence, authority, knowledge, legacy or command.  It keeps observation,
inference, proposal, counterevidence, uncertainty and recipient agency
structurally separate.  The resolver gate proves only that cited objects
existed according to a caller-supplied resolver; it never claims semantic
support.

The only official private adapter accepts the constructor-guarded resolved
type-state and returns an ordinary HLET1 ``HumanPrivateLetter``.  Existing
HENV1 sealing and ``HumanPrivateStore`` provide the durable ciphertext path.
This module has no store, network, model, attention admission or automation.
"""

from __future__ import annotations

import json
import re
from dataclasses import InitVar, dataclass
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from sailang.errors import SailangError

from .sailetter import HumanPrivateLetter, OpenedHumanPrivateLetter

FORMAT = "ALLY1"
ALLY_ADVICE_SUBJECT = "ALLY_ADVICE"

INFERENCE_STATUS = "UNVERIFIED"
GUIDANCE_STATUS = "PROPOSAL"
OBSERVE_ONLY = "OBSERVE_ONLY"
CONSIDER_CHANGE = "CONSIDER_CHANGE"
GUIDANCE_MODES = (OBSERVE_ONLY, CONSIDER_CHANGE)
AGENCY = "RECIPIENT_DECIDES"

EXISTS = "EXISTS"
MISSING = "MISSING"

MIN_OBSERVATIONS = 2
MAX_OBSERVATIONS = 16
MIN_DISTINCT_OBSERVED_EVIDENCE_REFS = 3
MAX_COUNTEREVIDENCE = 8
MAX_EVIDENCE_REFS_PER_ITEM = 16
MAX_CONTEXT_BYTES = 2_048
MAX_PROSE_BYTES = 4_096
MAX_ALLY1_BYTES = 32_768

ALLY_BAD_INPUT = "ALLY_BAD_INPUT"
ALLY_BAD_UTF8 = "ALLY_BAD_UTF8"
ALLY_BAD_JSON = "ALLY_BAD_JSON"
ALLY_NONCANONICAL = "ALLY_NONCANONICAL"
ALLY_DUPLICATE_FIELD = "ALLY_DUPLICATE_FIELD"
ALLY_UNKNOWN_FIELD = "ALLY_UNKNOWN_FIELD"
ALLY_MISSING_FIELD = "ALLY_MISSING_FIELD"
ALLY_BAD_FIELD = "ALLY_BAD_FIELD"
ALLY_EMPTY_FIELD = "ALLY_EMPTY_FIELD"
ALLY_FIELD_OVERSIZE = "ALLY_FIELD_OVERSIZE"
ALLY_OVERSIZE = "ALLY_OVERSIZE"
ALLY_BAD_CREATED = "ALLY_BAD_CREATED"
ALLY_BAD_OBSERVATION = "ALLY_BAD_OBSERVATION"
ALLY_OBSERVATION_FLOOR = "ALLY_OBSERVATION_FLOOR"
ALLY_COUNTEREVIDENCE_REQUIRED = "ALLY_COUNTEREVIDENCE_REQUIRED"
ALLY_BAD_COUNTEREVIDENCE = "ALLY_BAD_COUNTEREVIDENCE"
ALLY_EVIDENCE_REF_INVALID = "ALLY_EVIDENCE_REF_INVALID"
ALLY_EVIDENCE_REF_DUPLICATE = "ALLY_EVIDENCE_REF_DUPLICATE"
ALLY_EVIDENCE_REF_ORDER = "ALLY_EVIDENCE_REF_ORDER"
ALLY_BAD_INFERENCE_STATUS = "ALLY_BAD_INFERENCE_STATUS"
ALLY_BAD_GUIDANCE_STATUS = "ALLY_BAD_GUIDANCE_STATUS"
ALLY_BAD_GUIDANCE_MODE = "ALLY_BAD_GUIDANCE_MODE"
ALLY_BAD_AGENCY = "ALLY_BAD_AGENCY"
ALLY_EVIDENCE_RESOLUTION_REQUIRED = "ALLY_EVIDENCE_RESOLUTION_REQUIRED"
ALLY_EVIDENCE_RESOLVER_INVALID = "ALLY_EVIDENCE_RESOLVER_INVALID"
ALLY_EVIDENCE_MISSING = "ALLY_EVIDENCE_MISSING"
ALLY_EVIDENCE_PROOF_FORGED = "ALLY_EVIDENCE_PROOF_FORGED"
ALLY_WRONG_RECIPIENT = "ALLY_WRONG_RECIPIENT"
ALLY_WRONG_SUBJECT = "ALLY_WRONG_SUBJECT"
ALLY_PRIVATE_OPEN_REQUIRED = "ALLY_PRIVATE_OPEN_REQUIRED"

_EVIDENCE_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_TOP_LEVEL_FIELDS = (
    "FORMAT",
    "CREATED",
    "WORK_CONTEXT",
    "OBSERVED_SCOPE",
    "OBSERVED",
    "INFERRED",
    "SUGGESTED",
    "COUNTEREVIDENCE",
    "UNCERTAINTY",
    "AGENCY",
)
_ITEM_FIELDS = ("STATEMENT", "EVIDENCE_REFS")
_INFERRED_FIELDS = ("STATUS", "TEXT")
_SUGGESTED_FIELDS = ("STATUS", "MODE", "TEXT")


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _text(name: str, value, limit: int) -> str:
    if not isinstance(value, str):
        _reject(ALLY_BAD_FIELD, f"{name} must be text")
    if not value.strip():
        _reject(ALLY_EMPTY_FIELD, f"{name} is required and cannot be blank")
    if "\x00" in value:
        _reject(ALLY_BAD_FIELD, f"{name} cannot contain NUL")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        _reject(ALLY_BAD_UTF8, f"{name} must be well-formed UTF-8 text")
    if len(encoded) > limit:
        _reject(ALLY_FIELD_OVERSIZE, f"{name} exceeds {limit} UTF-8 bytes")
    return value


def _created(value) -> str:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        _reject(ALLY_BAD_CREATED, "CREATED must be exact UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        _reject(ALLY_BAD_CREATED, "CREATED is not a real UTC calendar instant")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _reject(ALLY_BAD_CREATED, "CREATED is not canonical UTC")
    return value


def _evidence_refs(value, *, item_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)):
        _reject(ALLY_EVIDENCE_REF_INVALID, f"{item_name} evidence refs must be a collection")
    try:
        refs = tuple(value)
    except TypeError:
        _reject(ALLY_EVIDENCE_REF_INVALID, f"{item_name} evidence refs must be iterable")
    if not refs:
        _reject(ALLY_EVIDENCE_REF_INVALID, f"{item_name} requires at least one evidence ref")
    if len(refs) > MAX_EVIDENCE_REFS_PER_ITEM:
        _reject(ALLY_EVIDENCE_REF_INVALID,
                f"{item_name} exceeds {MAX_EVIDENCE_REFS_PER_ITEM} evidence refs")
    for ref in refs:
        if not isinstance(ref, str) or not _EVIDENCE_REF_RE.fullmatch(ref):
            _reject(ALLY_EVIDENCE_REF_INVALID,
                    "evidence refs are sha256:<64 lowercase hex>")
    if len(set(refs)) != len(refs):
        _reject(ALLY_EVIDENCE_REF_DUPLICATE,
                f"{item_name} contains a duplicate evidence ref")
    if refs != tuple(sorted(refs)):
        _reject(ALLY_EVIDENCE_REF_ORDER,
                f"{item_name} evidence refs must be in canonical lexical order")
    return refs


@dataclass(frozen=True)
class AdviceObservation:
    """One bounded authored observation and the exact sources it cites."""

    statement: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text("OBSERVED.STATEMENT", self.statement, MAX_PROSE_BYTES)
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence_refs(self.evidence_refs, item_name="OBSERVED"),
        )


@dataclass(frozen=True)
class AdviceCounterevidence:
    """One bounded authored item that weakens the interpretation."""

    statement: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        _text("COUNTEREVIDENCE.STATEMENT", self.statement, MAX_PROSE_BYTES)
        if self.statement in ("NONE", "NO_COUNTEREVIDENCE_FOUND"):
            _reject(ALLY_COUNTEREVIDENCE_REQUIRED,
                    "a reserved no-counterevidence marker is not counterevidence")
        object.__setattr__(
            self,
            "evidence_refs",
            _evidence_refs(self.evidence_refs, item_name="COUNTEREVIDENCE"),
        )


@dataclass(frozen=True)
class AllyAdvice:
    """One immutable canonical ALLY1 reflection; never evidence or authority."""

    created: str
    work_context: str
    observed_scope: str
    observed: tuple[AdviceObservation, ...]
    inferred: str
    guidance_mode: str
    suggested: str
    counterevidence: tuple[AdviceCounterevidence, ...]
    uncertainty: str
    inference_status: str = INFERENCE_STATUS
    guidance_status: str = GUIDANCE_STATUS
    agency: str = AGENCY

    def __post_init__(self) -> None:
        _created(self.created)
        _text("WORK_CONTEXT", self.work_context, MAX_CONTEXT_BYTES)
        _text("OBSERVED_SCOPE", self.observed_scope, MAX_CONTEXT_BYTES)
        _text("INFERRED.TEXT", self.inferred, MAX_PROSE_BYTES)
        _text("SUGGESTED.TEXT", self.suggested, MAX_PROSE_BYTES)
        _text("UNCERTAINTY", self.uncertainty, MAX_PROSE_BYTES)

        if self.inference_status != INFERENCE_STATUS:
            _reject(ALLY_BAD_INFERENCE_STATUS,
                    f"INFERENCE_STATUS must be exactly {INFERENCE_STATUS}")
        if self.guidance_status != GUIDANCE_STATUS:
            _reject(ALLY_BAD_GUIDANCE_STATUS,
                    f"GUIDANCE_STATUS must be exactly {GUIDANCE_STATUS}")
        if self.guidance_mode not in GUIDANCE_MODES:
            _reject(ALLY_BAD_GUIDANCE_MODE,
                    f"guidance mode must be one of {GUIDANCE_MODES}")
        if self.agency != AGENCY:
            _reject(ALLY_BAD_AGENCY, f"AGENCY must be exactly {AGENCY}")

        if isinstance(self.observed, (str, bytes, bytearray)):
            _reject(ALLY_BAD_OBSERVATION, "OBSERVED must be a collection of items")
        try:
            observed = tuple(self.observed)
        except TypeError:
            _reject(ALLY_BAD_OBSERVATION, "OBSERVED must be an iterable collection")
        if not all(isinstance(item, AdviceObservation) for item in observed):
            _reject(ALLY_BAD_OBSERVATION, "every OBSERVED item must be AdviceObservation")
        if not MIN_OBSERVATIONS <= len(observed) <= MAX_OBSERVATIONS:
            _reject(ALLY_OBSERVATION_FLOOR,
                    f"OBSERVED requires {MIN_OBSERVATIONS}..{MAX_OBSERVATIONS} items")
        distinct_observed_refs = {
            ref for item in observed for ref in item.evidence_refs
        }
        if len(distinct_observed_refs) < MIN_DISTINCT_OBSERVED_EVIDENCE_REFS:
            _reject(ALLY_OBSERVATION_FLOOR,
                    "OBSERVED requires at least "
                    f"{MIN_DISTINCT_OBSERVED_EVIDENCE_REFS} distinct evidence refs")
        object.__setattr__(self, "observed", observed)

        if isinstance(self.counterevidence, (str, bytes, bytearray)):
            _reject(ALLY_BAD_COUNTEREVIDENCE,
                    "COUNTEREVIDENCE must be a collection of items")
        try:
            counterevidence = tuple(self.counterevidence)
        except TypeError:
            _reject(ALLY_BAD_COUNTEREVIDENCE,
                    "COUNTEREVIDENCE must be an iterable collection")
        if not counterevidence:
            _reject(ALLY_COUNTEREVIDENCE_REQUIRED,
                    "at least one cited COUNTEREVIDENCE item is required")
        if len(counterevidence) > MAX_COUNTEREVIDENCE:
            _reject(ALLY_BAD_COUNTEREVIDENCE,
                    f"COUNTEREVIDENCE exceeds {MAX_COUNTEREVIDENCE} items")
        if not all(isinstance(item, AdviceCounterevidence)
                   for item in counterevidence):
            _reject(ALLY_BAD_COUNTEREVIDENCE,
                    "every COUNTEREVIDENCE item must be AdviceCounterevidence")
        object.__setattr__(self, "counterevidence", counterevidence)

        if len(self.render()) > MAX_ALLY1_BYTES:
            _reject(ALLY_OVERSIZE, f"ALLY1 exceeds {MAX_ALLY1_BYTES} bytes")

    def _object(self) -> dict:
        def item(value) -> dict:
            return {
                "STATEMENT": value.statement,
                "EVIDENCE_REFS": list(value.evidence_refs),
            }

        return {
            "FORMAT": FORMAT,
            "CREATED": self.created,
            "WORK_CONTEXT": self.work_context,
            "OBSERVED_SCOPE": self.observed_scope,
            "OBSERVED": [item(value) for value in self.observed],
            "INFERRED": {
                "STATUS": self.inference_status,
                "TEXT": self.inferred,
            },
            "SUGGESTED": {
                "STATUS": self.guidance_status,
                "MODE": self.guidance_mode,
                "TEXT": self.suggested,
            },
            "COUNTEREVIDENCE": [item(value) for value in self.counterevidence],
            "UNCERTAINTY": self.uncertainty,
            "AGENCY": self.agency,
        }

    def render(self) -> bytes:
        """Return the single canonical ALLY1 byte representation."""
        return (json.dumps(self._object(), ensure_ascii=False, separators=(",", ":"))
                + "\n").encode("utf-8")

    @classmethod
    def parse(cls, data) -> AllyAdvice:
        """Parse exact canonical ALLY1; loose/equivalent JSON is refused."""
        raw = _input_bytes(data)
        if len(raw) > MAX_ALLY1_BYTES:
            _reject(ALLY_OVERSIZE, f"ALLY1 exceeds {MAX_ALLY1_BYTES} bytes")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            _reject(ALLY_BAD_UTF8, "ALLY1 must be strict UTF-8")
        if text.startswith("\ufeff"):
            _reject(ALLY_NONCANONICAL, "ALLY1 is UTF-8 without BOM")
        try:
            parsed = json.loads(
                text,
                object_pairs_hook=_unique_object,
                parse_constant=lambda token: _reject(
                    ALLY_BAD_JSON, f"non-finite JSON value {token} is forbidden"),
            )
        except json.JSONDecodeError as exc:
            _reject(ALLY_BAD_JSON, f"ALLY1 is not valid JSON: {exc.msg}")
        if not isinstance(parsed, dict):
            _reject(ALLY_BAD_JSON, "ALLY1 top level must be an object")
        advice = _advice_from_object(parsed)
        if advice.render() != raw:
            _reject(ALLY_NONCANONICAL,
                    "ALLY1 has exactly one byte representation; equivalent loose JSON refuses")
        return advice


def _input_bytes(data) -> bytes:
    if isinstance(data, str):
        try:
            return data.encode("utf-8")
        except UnicodeEncodeError:
            _reject(ALLY_BAD_UTF8, "ALLY1 must be well-formed UTF-8")
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    _reject(ALLY_BAD_INPUT, "ALLY1 input must be text or UTF-8 bytes")


def _unique_object(pairs) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _reject(ALLY_DUPLICATE_FIELD, f"duplicate ALLY1 field {key!r}")
        result[key] = value
    return result


def _require_fields(value, expected: tuple[str, ...], section: str) -> dict:
    if not isinstance(value, dict):
        _reject(ALLY_BAD_FIELD, f"{section} must be an object")
    unknown = set(value) - set(expected)
    if unknown:
        _reject(ALLY_UNKNOWN_FIELD,
                f"{section} has unknown field {min(unknown)!r}")
    missing = set(expected) - set(value)
    if missing:
        _reject(ALLY_MISSING_FIELD,
                f"{section} is missing field {min(missing)!r}")
    return value


def _items_from_object(value, *, counterevidence: bool):
    name = "COUNTEREVIDENCE" if counterevidence else "OBSERVED"
    if not isinstance(value, list):
        _reject(ALLY_BAD_FIELD, f"{name} must be an array")
    item_type = AdviceCounterevidence if counterevidence else AdviceObservation
    items = []
    for raw in value:
        parsed = _require_fields(raw, _ITEM_FIELDS, f"{name} item")
        refs = parsed["EVIDENCE_REFS"]
        if not isinstance(refs, list):
            _reject(ALLY_EVIDENCE_REF_INVALID,
                    f"{name}.EVIDENCE_REFS must be an array")
        items.append(item_type(parsed["STATEMENT"], tuple(refs)))
    return tuple(items)


def _advice_from_object(value: dict) -> AllyAdvice:
    parsed = _require_fields(value, _TOP_LEVEL_FIELDS, "ALLY1")
    if parsed["FORMAT"] != FORMAT:
        _reject(ALLY_BAD_FIELD, f"FORMAT must be exactly {FORMAT}")
    inferred = _require_fields(parsed["INFERRED"], _INFERRED_FIELDS, "INFERRED")
    suggested = _require_fields(parsed["SUGGESTED"], _SUGGESTED_FIELDS, "SUGGESTED")
    return AllyAdvice(
        created=parsed["CREATED"],
        work_context=parsed["WORK_CONTEXT"],
        observed_scope=parsed["OBSERVED_SCOPE"],
        observed=_items_from_object(parsed["OBSERVED"], counterevidence=False),
        inferred=inferred["TEXT"],
        guidance_mode=suggested["MODE"],
        suggested=suggested["TEXT"],
        counterevidence=_items_from_object(
            parsed["COUNTEREVIDENCE"], counterevidence=True),
        uncertainty=parsed["UNCERTAINTY"],
        inference_status=inferred["STATUS"],
        guidance_status=suggested["STATUS"],
        agency=parsed["AGENCY"],
    )


def render_ally_advice(advice: AllyAdvice) -> str:
    """Render every epistemic section visibly without rewriting authored prose."""
    if not isinstance(advice, AllyAdvice):
        _reject(ALLY_BAD_INPUT, "human rendering requires an AllyAdvice")
    lines = [
        "WORK CONTEXT",
        advice.work_context,
        "",
        "OBSERVED",
        f"SCOPE: {advice.observed_scope}",
    ]
    for number, observation in enumerate(advice.observed, 1):
        lines.extend((f"OBSERVATION {number}", observation.statement, "EVIDENCE REFS"))
        lines.extend(f"- {ref}" for ref in observation.evidence_refs)
    lines.extend((
        "",
        f"INFERRED — {INFERENCE_STATUS}",
        advice.inferred,
        "",
        f"SUGGESTED — {GUIDANCE_STATUS} — {advice.guidance_mode}",
        advice.suggested,
        "",
        "COUNTEREVIDENCE",
    ))
    for number, item in enumerate(advice.counterevidence, 1):
        lines.extend((f"COUNTEREVIDENCE {number}", item.statement, "EVIDENCE REFS"))
        lines.extend(f"- {ref}" for ref in item.evidence_refs)
    lines.extend((
        "",
        "UNCERTAINTY",
        advice.uncertainty,
        "",
        "AGENCY — RECIPIENT DECIDES",
    ))
    return "\n".join(lines) + "\n"


@runtime_checkable
class EvidenceResolver(Protocol):
    """Caller-supplied existence oracle; it says nothing about semantic support."""

    def resolve(self, evidence_ref: str) -> str:
        """Return exactly ``EXISTS`` or ``MISSING`` for one canonical ref."""


_EVIDENCE_RESOLVED = object()


def _all_evidence_refs(advice: AllyAdvice) -> tuple[str, ...]:
    return tuple(sorted({
        ref
        for item in (*advice.observed, *advice.counterevidence)
        for ref in item.evidence_refs
    }))


@dataclass(frozen=True)
class EvidenceResolvedAllyAdvice:
    """All cited objects existed at one explicit check; semantic support is unproven."""

    advice: AllyAdvice
    resolved_refs: tuple[str, ...]
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _EVIDENCE_RESOLVED:
            _reject(ALLY_EVIDENCE_PROOF_FORGED,
                    "EvidenceResolvedAllyAdvice is minted only by resolve_ally_evidence; "
                    "the mint is not retained, so proof cannot be copied or transplanted")
        if not isinstance(self.advice, AllyAdvice):
            _reject(ALLY_EVIDENCE_PROOF_FORGED, "resolved proof must bind one AllyAdvice")
        expected = _all_evidence_refs(self.advice)
        if self.resolved_refs != expected:
            _reject(ALLY_EVIDENCE_PROOF_FORGED,
                    "resolved refs must exactly match the bound advice")


def resolve_ally_evidence(
        advice: AllyAdvice,
        resolver: EvidenceResolver | None = None) -> EvidenceResolvedAllyAdvice:
    """Resolve cited existence and mint the narrow non-transferable type-state."""
    if not isinstance(advice, AllyAdvice):
        _reject(ALLY_BAD_INPUT, "evidence resolution requires an AllyAdvice")
    if resolver is None:
        _reject(ALLY_EVIDENCE_RESOLUTION_REQUIRED,
                "ALLY_ADVICE requires a caller-supplied EvidenceResolver before conversion")
    if (not isinstance(resolver, EvidenceResolver)
            or not callable(getattr(resolver, "resolve", None))):
        _reject(ALLY_EVIDENCE_RESOLVER_INVALID,
                "resolver must implement resolve(ref) -> EXISTS | MISSING")
    refs = _all_evidence_refs(advice)
    missing = []
    for ref in refs:
        outcome = resolver.resolve(ref)
        if outcome == MISSING:
            missing.append(ref)
        elif outcome != EXISTS:
            _reject(ALLY_EVIDENCE_RESOLVER_INVALID,
                    "resolver must return exactly EXISTS or MISSING")
    if missing:
        _reject(ALLY_EVIDENCE_MISSING,
                f"cited evidence object does not exist: {missing[0]}")
    return EvidenceResolvedAllyAdvice(advice, refs, _EVIDENCE_RESOLVED)


def ally_to_human_private(
        resolved: EvidenceResolvedAllyAdvice,
        *,
        recipient_human_id: str) -> HumanPrivateLetter:
    """Convert resolved ALLY1 into HLET1; sealing and delivery remain explicit."""
    if not isinstance(resolved, EvidenceResolvedAllyAdvice):
        _reject(ALLY_EVIDENCE_RESOLUTION_REQUIRED,
                "official ALLY_ADVICE conversion requires EvidenceResolvedAllyAdvice")
    advice = resolved.advice
    return HumanPrivateLetter(
        to_human=recipient_human_id,
        created=advice.created,
        subject=ALLY_ADVICE_SUBJECT,
        body=advice.render().decode("utf-8"),
    )


def open_ally_advice(
        opened: OpenedHumanPrivateLetter,
        *,
        recipient_human_id: str) -> AllyAdvice:
    """Explicitly parse ALLY1 only after authenticated HUMAN_PRIVATE opening."""
    if not isinstance(opened, OpenedHumanPrivateLetter):
        _reject(ALLY_PRIVATE_OPEN_REQUIRED,
                "ALLY_ADVICE open requires an authenticated OpenedHumanPrivateLetter")
    letter = opened.letter
    if (letter.to_human != recipient_human_id
            or opened.verified.parsed.to_human != recipient_human_id):
        _reject(ALLY_WRONG_RECIPIENT,
                "HLET1 and HENV1 recipient must match the explicit recipient")
    if letter.subject != ALLY_ADVICE_SUBJECT:
        _reject(ALLY_WRONG_SUBJECT,
                f"HLET1 SUBJECT must be exactly {ALLY_ADVICE_SUBJECT}")
    return AllyAdvice.parse(letter.body)


__all__ = [
    "AGENCY",
    "ALLY_ADVICE_SUBJECT",
    "ALLY_BAD_AGENCY",
    "ALLY_BAD_CREATED",
    "ALLY_BAD_FIELD",
    "ALLY_BAD_GUIDANCE_MODE",
    "ALLY_BAD_GUIDANCE_STATUS",
    "ALLY_BAD_INFERENCE_STATUS",
    "ALLY_BAD_INPUT",
    "ALLY_BAD_JSON",
    "ALLY_BAD_OBSERVATION",
    "ALLY_BAD_UTF8",
    "ALLY_COUNTEREVIDENCE_REQUIRED",
    "ALLY_DUPLICATE_FIELD",
    "ALLY_EVIDENCE_MISSING",
    "ALLY_EVIDENCE_PROOF_FORGED",
    "ALLY_EVIDENCE_REF_DUPLICATE",
    "ALLY_EVIDENCE_REF_INVALID",
    "ALLY_EVIDENCE_REF_ORDER",
    "ALLY_EVIDENCE_RESOLUTION_REQUIRED",
    "ALLY_EVIDENCE_RESOLVER_INVALID",
    "ALLY_FIELD_OVERSIZE",
    "ALLY_MISSING_FIELD",
    "ALLY_NONCANONICAL",
    "ALLY_OBSERVATION_FLOOR",
    "ALLY_OVERSIZE",
    "ALLY_PRIVATE_OPEN_REQUIRED",
    "ALLY_UNKNOWN_FIELD",
    "ALLY_WRONG_RECIPIENT",
    "ALLY_WRONG_SUBJECT",
    "CONSIDER_CHANGE",
    "EXISTS",
    "FORMAT",
    "GUIDANCE_MODES",
    "GUIDANCE_STATUS",
    "INFERENCE_STATUS",
    "MAX_ALLY1_BYTES",
    "MAX_CONTEXT_BYTES",
    "MAX_COUNTEREVIDENCE",
    "MAX_EVIDENCE_REFS_PER_ITEM",
    "MAX_OBSERVATIONS",
    "MAX_PROSE_BYTES",
    "MIN_DISTINCT_OBSERVED_EVIDENCE_REFS",
    "MIN_OBSERVATIONS",
    "MISSING",
    "OBSERVE_ONLY",
    "AdviceCounterevidence",
    "AdviceObservation",
    "AllyAdvice",
    "EvidenceResolvedAllyAdvice",
    "EvidenceResolver",
    "ally_to_human_private",
    "open_ally_advice",
    "render_ally_advice",
    "resolve_ally_evidence",
]
