"""LAB-ONLY live adapter and runner for the registered AllyAdvice experiment.

The defect class this module eliminates: **a live run that cannot be told apart
from a demo.** Production B-016 is transport-agnostic on purpose; the moment a
model gateway is wired into it, three temptations appear -- retry a bad answer,
tune the prompt, or quietly call the second model when the first one stalls.
Each would leave a pretty artifact that no longer measures what was registered.
So this module is a narrow lab seam, and the seam has teeth:

* it never imports or calls a durable private path (``sealing``,
  ``HumanPrivateStore``, attention admission): a passing candidate is measured
  and dropped, never delivered;
* one logical dispatch is one call. Transport failure is recorded as ERROR, the
  logical call is not repeated, the participant is not replaced mid-experiment,
  and no retry exists for schema failure, review FAIL, review UNKNOWN or
  NO_ADVICE;
* both adapters parse strict bounded JSON with duplicate, unknown and missing
  field refusal, no repair prompt and no second call, and hand the result to
  the existing B-016 boundary (``generate_reviewed_ally_advice``,
  ``run_semantic_review``) so the production gate -- not a lab copy of it --
  decides the final outcome;
* the artifact is written once, carries the frozen registration identity, and
  keeps every call record: requested model, reported model, transport status,
  error class, usage and a bounded visible output with its hash. Credentials
  are scrubbed and checked absent before anything is written.

The dry run is part of the contract, not a courtesy: it executes the whole
plan against deterministic in-process fakes and proves the call plan, the
NO_ADVICE path spending zero reviewer calls, the rejected-candidate path
spending exactly one, and artifact/report serialization, with no network and
no credential touch.

    python lab/ally_generation_live.py --register --ticket T-63 \
        --source-receipt SRC-047
    python lab/ally_generation_live.py --out lab/out --dry-run
    python lab/ally_generation_live.py --out lab/out
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import uuid
from collections.abc import Mapping, Sequence

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lab import ally_generation_scenarios as sc
from lab import experiment_class as ec
from lab import saifren_population as pop
from lab import saifren_run as live
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag
from saimail.credentials import (
    DEFAULT_HANDLE,
    SOURCE_STORE,
    SOURCES,
    CredentialError,
    CredentialNotProvisioned,
    resolve,
)
from saimail.publish import publish_immutable

REGISTRATION = pathlib.Path(__file__).resolve().parent / sc.REGISTRATION_FILE
MAX_VISIBLE_OUTPUT = 4000
DRY_EXTERNAL = "UNRESOLVED_EXTERNAL_COMPARATOR"

ALLY_LAB_BAD_JSON = "ALLY_LAB_BAD_JSON"
ALLY_LAB_SCHEMA = "ALLY_LAB_SCHEMA"
ALLY_LAB_UNKNOWN_FIELD = "ALLY_LAB_UNKNOWN_FIELD"
ALLY_LAB_MISSING_FIELD = "ALLY_LAB_MISSING_FIELD"
ALLY_LAB_DUPLICATE_FIELD = "ALLY_LAB_DUPLICATE_FIELD"
ALLY_LAB_BOUNDS = "ALLY_LAB_BOUNDS"
ALLY_LAB_GENERATOR_TRANSPORT = "ALLY_LAB_GENERATOR_TRANSPORT"
ALLY_LAB_REVIEWER_TRANSPORT = "ALLY_LAB_REVIEWER_TRANSPORT"

_GENERATOR_TOP = ("result",)
_CANDIDATE_TOP = ("result", "WORK_CONTEXT", "OBSERVED_SCOPE", "OBSERVED", "INFERRED",
                  "GUIDANCE_MODE", "SUGGESTED", "COUNTEREVIDENCE", "UNCERTAINTY")
_ITEM_FIELDS = ("STATEMENT", "EVIDENCE_REFS")
_REVIEW_TOP = ("candidate_id", "corpus_id", "rubric_version", "dimensions")
_DIMENSION_FIELDS = ("dimension", "verdict", "rationale", "evidence_refs")

STATUS_COMPLETED = "COMPLETED"


class RegistrationMismatch(SystemExit):
    """The plan in code is not the plan that was registered. Nothing was called."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


# ----------------------------------------------------------- strict JSON


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject(ALLY_LAB_DUPLICATE_FIELD, f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _strict_object(text) -> dict:
    if not isinstance(text, str) or not text.strip():
        _reject(ALLY_LAB_BAD_JSON, "the model output is empty or not text")
    stripped = text.strip()
    try:
        value, end = json.JSONDecoder(object_pairs_hook=_unique_object).raw_decode(stripped)
    except SailangError:
        raise
    except json.JSONDecodeError as exc:
        _reject(ALLY_LAB_BAD_JSON, f"the model output is not one JSON document: {exc.msg}")
    if end != len(stripped):
        _reject(ALLY_LAB_BAD_JSON, "prose outside the JSON object is refused")
    if not isinstance(value, dict):
        _reject(ALLY_LAB_SCHEMA, "the model output must be one JSON object")
    return value


def _exact_fields(value: Mapping, expected: Sequence[str], section: str) -> None:
    unknown = sorted(set(value) - set(expected))
    if unknown:
        _reject(ALLY_LAB_UNKNOWN_FIELD, f"{section} has unknown field {unknown[0]!r}")
    missing = sorted(set(expected) - set(value))
    if missing:
        _reject(ALLY_LAB_MISSING_FIELD, f"{section} is missing field {missing[0]!r}")


def _wire_items(value, section: str):
    if not isinstance(value, list):
        _reject(ALLY_LAB_SCHEMA, f"{section} must be an array")
    rows = []
    for raw in value:
        if not isinstance(raw, dict):
            _reject(ALLY_LAB_SCHEMA, f"every {section} item must be an object")
        _exact_fields(raw, _ITEM_FIELDS, f"{section} item")
        refs = raw["EVIDENCE_REFS"]
        if not isinstance(refs, list) or not refs:
            _reject(ALLY_LAB_SCHEMA, f"{section}.EVIDENCE_REFS must be a non-empty array")
        if not all(isinstance(ref, str) for ref in refs):
            _reject(ALLY_LAB_SCHEMA, f"{section}.EVIDENCE_REFS must be strings")
        rows.append((raw["STATEMENT"], tuple(refs)))
    return tuple(rows)


def parse_generator_output(text) -> ag.GeneratorResult:
    """Strict bounded JSON to one closed GeneratorResult; no repair, no second call."""
    payload = _strict_object(text)
    if "result" not in payload:
        _reject(ALLY_LAB_MISSING_FIELD, "the generator object is missing field 'result'")
    kind = payload["result"]
    if kind == ag.NO_ADVICE:
        _exact_fields(payload, _GENERATOR_TOP, "NO_ADVICE")
        return ag.GeneratorResult.no_advice()
    if kind != ag.CANDIDATE:
        _reject(ALLY_LAB_SCHEMA,
                f"result must be exactly {ag.NO_ADVICE!r} or {ag.CANDIDATE!r}")
    _exact_fields(payload, _CANDIDATE_TOP, "CANDIDATE")
    observed = _wire_items(payload["OBSERVED"], "OBSERVED")
    counterevidence = _wire_items(payload["COUNTEREVIDENCE"], "COUNTEREVIDENCE")
    advice = aa.AllyAdvice(
        created=sc.CREATED,
        work_context=payload["WORK_CONTEXT"],
        observed_scope=payload["OBSERVED_SCOPE"],
        observed=tuple(aa.AdviceObservation(statement, refs) for statement, refs in observed),
        inferred=payload["INFERRED"],
        guidance_mode=payload["GUIDANCE_MODE"],
        suggested=payload["SUGGESTED"],
        counterevidence=tuple(
            aa.AdviceCounterevidence(statement, refs)
            for statement, refs in counterevidence),
        uncertainty=payload["UNCERTAINTY"],
    )
    return ag.GeneratorResult.of(advice)


def parse_reviewer_output(text, candidate: aa.AllyAdvice,
                          corpus: ag.ReflectionCorpus) -> ag.SemanticReviewReport:
    """Strict bounded JSON to the existing eight-dimension SemanticReviewReport."""
    payload = _strict_object(text)
    _exact_fields(payload, _REVIEW_TOP, "review")
    expected_candidate = ag.ally_candidate_id(candidate)
    if payload["candidate_id"] != expected_candidate:
        _reject(ALLY_LAB_SCHEMA, "the review does not bind the exact candidate identity")
    if payload["corpus_id"] != corpus.corpus_id:
        _reject(ALLY_LAB_SCHEMA, "the review does not bind the exact corpus identity")
    if payload["rubric_version"] != ag.RUBRIC_VERSION:
        _reject(ALLY_LAB_SCHEMA, f"rubric must be exactly {ag.RUBRIC_VERSION}")
    rows = payload["dimensions"]
    if not isinstance(rows, list):
        _reject(ALLY_LAB_SCHEMA, "dimensions must be an array")
    verdicts = []
    for raw in rows:
        if not isinstance(raw, dict):
            _reject(ALLY_LAB_SCHEMA, "every dimension must be an object")
        _exact_fields(raw, _DIMENSION_FIELDS, "dimension")
        refs = raw["evidence_refs"]
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            _reject(ALLY_LAB_SCHEMA, "evidence_refs must be an array of strings")
        verdicts.append(ag.ReviewVerdict(
            dimension=raw["dimension"], verdict=raw["verdict"],
            rationale=raw["rationale"], evidence_refs=tuple(refs)))
    return ag.SemanticReviewReport(
        candidate_id=expected_candidate, corpus_id=corpus.corpus_id,
        rubric_version=ag.RUBRIC_VERSION, verdicts=tuple(verdicts))


# ---------------------------------------------------------------- adapters


class CallLog:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def append(self, record: dict) -> None:
        self.records.append(record)


class Dispatch:
    """One logical call through the existing Runner; one call per logical call."""

    def __init__(self, runner: live.Runner, log: CallLog) -> None:
        self._runner = runner
        self._log = log

    def __call__(self, prompt: str, model: str | None, *, unit_id: str, replicate: int,
                 role: str, function: str) -> dict:
        call = self._runner.call(unit_id, role, prompt, model=model)
        output = call.get("output")
        output = output[:MAX_VISIBLE_OUTPUT] if isinstance(output, str) else None
        usage = call.get("usage") if isinstance(call.get("usage"), dict) else {}
        local_estimate = live.estimate_tokens(prompt)
        gateway_tokens = usage.get("prompt_tokens")
        entry = {
            "call_id": call.get("call_id"),
            "unit_id": unit_id,
            "replicate": replicate,
            "role": role,
            "function": function,
            "requested_model": call.get("requested_model"),
            "reported_model": call.get("reported_model"),
            "provider": call.get("provider"),
            "provider_basis": call.get("provider_basis"),
            "timestamp": call.get("timestamp"),
            "prompt_sha256": call.get("prompt_sha256"),
            "visible_output": output,
            "visible_output_sha256": _sha256(output) if output is not None else None,
            "status": call.get("status"),
            "error_class": call.get("error_class"),
            "http_status": call.get("http_status"),
            "latency_s": call.get("latency_s"),
            "finish_reason": call.get("finish_reason"),
            "output_truncated": call.get("output_truncated"),
            "usage": usage,
            "error": call.get("error"),
            "local_estimated_input_tokens": local_estimate,
            "gateway_reported_prompt_tokens": gateway_tokens,
            "prompt_token_delta": (gateway_tokens - local_estimate)
                                  if isinstance(gateway_tokens, int) else None,
        }
        self._log.append(entry)
        return call


class LabGenerator:
    """A bounded AllyAdviceGenerator backed by one gateway call per invocation."""

    def __init__(self, dispatch: Dispatch, *, unit_id: str, replicate: int, role: str,
                 requested: str) -> None:
        self._dispatch = dispatch
        self.unit_id = unit_id
        self.replicate = replicate
        self.role = role
        self.requested = requested
        self.transport_status = sc.STAGE_NOT_ATTEMPTED
        self.parse_status = sc.STAGE_NOT_ATTEMPTED
        self.structural_gate = sc.STAGE_NOT_REACHED
        self.ref_gate = sc.STAGE_NOT_REACHED
        self.last_error: str | None = None
        self.candidate: aa.AllyAdvice | None = None
        self.record: dict | None = None

    def generate(self, corpus: ag.ReflectionCorpus) -> ag.GeneratorResult:
        prompt = sc.generator_prompt(corpus)
        call = self._dispatch(prompt, self.requested, unit_id=self.unit_id,
                              replicate=self.replicate, role=self.role,
                              function="GENERATOR")
        self.record = call
        if call.get("status") != "OK":
            self.transport_status = sc.STAGE_ERROR
            self.last_error = call.get("error_class") or call.get("status")
            _reject(ALLY_LAB_GENERATOR_TRANSPORT,
                    "the generator transport did not answer; no retry exists")
        self.transport_status = sc.STAGE_OK
        try:
            result = parse_generator_output(call.get("output") or "")
        except SailangError as exc:
            self.parse_status = sc.STAGE_SCHEMA_ERROR
            self.last_error = exc.code
            if not exc.code.startswith("ALLY_LAB_"):
                self.structural_gate = sc.STAGE_FAIL
            raise
        self.parse_status = sc.STAGE_OK
        if result.kind == ag.NO_ADVICE:
            return result
        candidate = result.candidate
        self.structural_gate = sc.STAGE_PASS
        self.candidate = candidate
        outside = [ref for ref in sc.candidate_refs(candidate) if ref not in corpus.refs()]
        self.ref_gate = sc.STAGE_FAIL if outside else sc.STAGE_PASS
        if outside:
            self.last_error = ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
        return result


class LabReviewer:
    """A bounded AllyAdviceSemanticReviewer backed by one gateway call per review."""

    def __init__(self, dispatch: Dispatch, *, unit_id: str, replicate: int, role: str,
                 requested: str) -> None:
        self._dispatch = dispatch
        self.unit_id = unit_id
        self.replicate = replicate
        self.role = role
        self.requested = requested
        self.transport_status = sc.STAGE_NOT_ATTEMPTED
        self.parse_status = sc.STAGE_NOT_ATTEMPTED
        self.last_error: str | None = None
        self.report: ag.SemanticReviewReport | None = None
        self.record: dict | None = None

    def review(self, evidence_resolved_advice: aa.EvidenceResolvedAllyAdvice,
               corpus: ag.ReflectionCorpus) -> ag.SemanticReviewReport:
        prompt = sc.reviewer_prompt(evidence_resolved_advice.advice, corpus)
        call = self._dispatch(prompt, self.requested, unit_id=self.unit_id,
                              replicate=self.replicate, role=self.role,
                              function="REVIEWER")
        self.record = call
        if call.get("status") != "OK":
            self.transport_status = sc.STAGE_ERROR
            self.last_error = call.get("error_class") or call.get("status")
            _reject(ALLY_LAB_REVIEWER_TRANSPORT,
                    "the reviewer transport did not answer; no retry exists")
        self.transport_status = sc.STAGE_OK
        try:
            report = parse_reviewer_output(call.get("output") or "",
                                           evidence_resolved_advice.advice, corpus)
        except SailangError as exc:
            self.parse_status = sc.STAGE_SCHEMA_ERROR
            self.last_error = exc.code
            raise
        self.parse_status = sc.STAGE_OK
        self.report = report
        return report


class DryGenerator:
    """Deterministic dry-run generator: the registered fixture, zero network."""

    def __init__(self, code: str, *, unit_id: str, replicate: int, role: str,
                 requested: str) -> None:
        self.code = code
        self.unit_id = unit_id
        self.replicate = replicate
        self.role = role
        self.requested = requested
        self.transport_status = sc.STAGE_NOT_ATTEMPTED
        self.parse_status = sc.STAGE_NOT_ATTEMPTED
        self.structural_gate = sc.STAGE_NOT_REACHED
        self.ref_gate = sc.STAGE_NOT_REACHED
        self.last_error: str | None = None
        self.candidate: aa.AllyAdvice | None = None
        self.record: dict | None = None
        self.calls = 0

    def generate(self, corpus: ag.ReflectionCorpus) -> ag.GeneratorResult:
        self.calls += 1
        self.transport_status = sc.STAGE_NOT_ATTEMPTED
        self.parse_status = sc.STAGE_NOT_ATTEMPTED
        fixture = sc.fixture_candidate(self.code)
        if fixture is None:
            return ag.GeneratorResult.no_advice()
        self.structural_gate = sc.STAGE_PASS
        self.candidate = fixture
        outside = [ref for ref in sc.candidate_refs(fixture) if ref not in corpus.refs()]
        self.ref_gate = sc.STAGE_FAIL if outside else sc.STAGE_PASS
        if outside:
            self.last_error = ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
        return ag.GeneratorResult.of(fixture)


_DRY_REVIEW_FAILS = {
    sc.G3: (ag.COUNTEREVIDENCE_ADEQUACY,),
    sc.G4: (ag.SCOPE_DISCIPLINE,),
}


class DryReviewer:
    """Deterministic dry-run reviewer: registered verdict pattern, zero network."""

    def __init__(self, unit_id: str, *, replicate: int, role: str, requested: str,
                 control_dimension: str | None = None,
                 control_expected: str | None = None) -> None:
        self.unit_id = unit_id
        self.replicate = replicate
        self.role = role
        self.requested = requested
        self.control_dimension = control_dimension
        self.control_expected = control_expected
        self.transport_status = sc.STAGE_NOT_ATTEMPTED
        self.parse_status = sc.STAGE_NOT_ATTEMPTED
        self.last_error: str | None = None
        self.report: ag.SemanticReviewReport | None = None
        self.record: dict | None = None
        self.calls = 0

    def _failed(self, code: str) -> tuple[str, ...]:
        if self.control_dimension is not None:
            return (self.control_dimension,)
        return _DRY_REVIEW_FAILS.get(code, ())

    def review(self, evidence_resolved_advice: aa.EvidenceResolvedAllyAdvice,
               corpus: ag.ReflectionCorpus) -> ag.SemanticReviewReport:
        self.calls += 1
        candidate = evidence_resolved_advice.advice
        refs = sc.candidate_refs(candidate)
        fallback = corpus.items[0].evidence_ref
        failed = set(self._failed(self.unit_id.split(".")[0]))
        verdicts = []
        for dimension in ag.DIMENSIONS:
            if dimension in failed:
                verdicts.append(ag.ReviewVerdict(
                    dimension, ag.FAIL, f"{dimension} scripted dry-run failure."))
                continue
            if dimension in ag.EVIDENCE_REQUIRED_DIMENSIONS:
                verdicts.append(ag.ReviewVerdict(
                    dimension, ag.PASS, f"{dimension} scripted dry-run pass.",
                    (refs[0] if refs else fallback,)))
            else:
                verdicts.append(ag.ReviewVerdict(
                    dimension, ag.PASS, f"{dimension} scripted dry-run pass."))
        report = ag.SemanticReviewReport(
            candidate_id=ag.ally_candidate_id(candidate), corpus_id=corpus.corpus_id,
            rubric_version=ag.RUBRIC_VERSION, verdicts=tuple(verdicts))
        self.report = report
        return report


# -------------------------------------------------------------- discovery


def _transport_status(result: Mapping) -> str:
    """ERROR iff the transport result carries an explicit failure condition.

    A successful ``HttpTransport.send`` answer is the observable payload and
    carries no ``status`` key, so status is derived from the failure state
    (``error_class`` present, an explicit non-2xx HTTP status, or an explicit
    non-OK status marker on a dispatch-shaped record) rather than from a key
    the success path never sets.
    """
    if result.get("error_class"):
        return "ERROR"
    http_status = result.get("http_status")
    if isinstance(http_status, int) and not 200 <= http_status < 300:
        return "ERROR"
    if result.get("status") in ("ERROR", "NOT_RUN"):
        return "ERROR"
    return "OK"


def _discovery_probe_record(model: str, result: Mapping) -> dict:
    output = result.get("output")
    output = output[:MAX_VISIBLE_OUTPUT] if isinstance(output, str) else None
    return {
        "call_id": uuid.uuid4().hex[:12],
        "unit_id": "DISCOVERY.probe",
        "replicate": 0,
        "role": "DISCOVERY",
        "function": "DISCOVERY",
        "requested_model": model,
        "reported_model": result.get("reported_model"),
        "provider": result.get("provider"),
        "provider_basis": result.get("provider_basis"),
        "timestamp": live._now(),
        "prompt_sha256": _sha256(pop.PROBE_PROMPT),
        "visible_output": output,
        "visible_output_sha256": _sha256(output) if output is not None else None,
        "status": _transport_status(result),
        "error_class": result.get("error_class"),
        "http_status": result.get("http_status"),
        "latency_s": result.get("latency_s"),
        "usage": result.get("usage") if isinstance(result.get("usage"), dict) else {},
        "local_estimated_input_tokens": live.estimate_tokens(pop.PROBE_PROMPT),
        "gateway_reported_prompt_tokens": (result.get("usage") or {}).get("prompt_tokens"),
        "prompt_token_delta": None,
    }


def resolve_population(transport, budget: live.CallBudget, log: CallLog,
                       combo: str = live.COMBO):
    """Discovery, membership sampling and selection, every probe recorded."""
    observed_at = live._now()

    def catalog():
        try:
            return transport.get_json(pop.DISCOVERY_PATH)
        except Exception as exc:  # a transport fault is classified here
            if getattr(exc, "code", None) in (401, 403):
                raise live.AuthRefused(
                    f"HTTP {getattr(exc, 'code', None)} during catalog discovery") from None
            raise

    def probe(model: str) -> dict:
        try:
            budget.spend()
        except live.BudgetExceeded as exc:
            return {"error_class": "BudgetExceeded", "error": str(exc)[:live.MAX_ERROR_CHARS]}
        try:
            result = transport.probe(model)
        except Exception as exc:  # noqa: BLE001 - a probe fault is data, not a crash
            if getattr(exc, "code", None) in (401, 403):
                raise live.AuthRefused(
                    f"HTTP {getattr(exc, 'code', None)} during a membership probe") from None
            return {"error_class": type(exc).__name__, "error": str(exc)[:live.MAX_ERROR_CHARS]}
        if result.get("http_status") in (401, 403):
            raise live.AuthRefused(f"HTTP {result['http_status']} during a membership probe")
        log.append(_discovery_probe_record(model, result))
        return result

    try:
        return pop.resolve_population(combo, catalog, probe, observed_at)
    except live.AuthRefused:
        raise
    except Exception as exc:  # noqa: BLE001 - discovery is evidence, not a gate
        return pop.offline_population(
            combo, observed_at,
            f"the discovery surface {pop.DISCOVERY_PATH} could not be read "
            f"({type(exc).__name__})")


# ------------------------------------------------------------- experiment


def frozen_participants(population) -> tuple[dict, ...]:
    rows = tuple({"role": p.role, "requested": p.requested,
                  "reported_model": p.reported_model, "member_status": p.member_status,
                  "source": p.source, "provider": p.provider}
                 for p in getattr(population, "participants", ()))
    return rows[:2]


def heterogeneous(participants: Sequence[Mapping]) -> bool:
    """Two answering participants whose reported models are actually distinct."""
    if len(participants) < 2:
        return False
    reported = [row.get("reported_model") for row in participants]
    if not all(reported):
        return False
    return len(set(reported)) >= 2


def _stages(generator, reviewer, outcome: ag.GenerationOutcome) -> dict:
    stages = {name: sc.STAGE_NOT_REACHED for name in sc.STAGES}
    stages["GENERATOR_TRANSPORT"] = generator.transport_status
    stages["GENERATOR_PARSE"] = generator.parse_status
    if outcome.status == ag.NO_ADVICE:
        stages["GENERATOR_RESULT"] = sc.STAGE_NO_ADVICE
        stages["SEMANTIC_REVIEW"] = sc.STAGE_SKIPPED
        stages["FINAL_GATE_OUTCOME"] = ag.NO_ADVICE
        return stages
    if generator.candidate is None:
        stages["GENERATOR_RESULT"] = sc.STAGE_ERROR
        stages["FINAL_GATE_OUTCOME"] = outcome.status
        return stages
    stages["GENERATOR_RESULT"] = sc.STAGE_CANDIDATE
    stages["ALLY1_STRUCTURAL_GATE"] = generator.structural_gate
    stages["CORPUS_REF_GATE"] = generator.ref_gate
    if generator.ref_gate == sc.STAGE_FAIL:
        stages["SEMANTIC_REVIEW"] = sc.STAGE_SKIPPED
        stages["FINAL_GATE_OUTCOME"] = outcome.status
        return stages
    if outcome.code == ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS:
        stages["EVENT_FLOOR_GATE"] = sc.STAGE_FAIL
        stages["SEMANTIC_REVIEW"] = sc.STAGE_SKIPPED
        stages["FINAL_GATE_OUTCOME"] = outcome.status
        return stages
    stages["EVENT_FLOOR_GATE"] = sc.STAGE_PASS
    stages["EVIDENCE_RESOLUTION"] = sc.STAGE_PASS
    stages["REVIEWER_TRANSPORT"] = reviewer.transport_status
    stages["REVIEWER_PARSE"] = reviewer.parse_status
    if reviewer.report is not None:
        stages["SEMANTIC_REVIEW"] = sc.STAGE_PASS
    elif reviewer.transport_status == sc.STAGE_OK and reviewer.parse_status == sc.STAGE_OK:
        stages["SEMANTIC_REVIEW"] = sc.STAGE_NOT_REACHED
    elif reviewer.transport_status == sc.STAGE_ERROR or reviewer.parse_status == sc.STAGE_SCHEMA_ERROR:
        stages["SEMANTIC_REVIEW"] = sc.STAGE_SKIPPED
    stages["FINAL_GATE_OUTCOME"] = outcome.status
    return stages


def _unit_record(code: str, replicate: int, generator, reviewer,
                 outcome: ag.GenerationOutcome, corpus: ag.ReflectionCorpus) -> dict:
    candidate = generator.candidate
    verdicts = ({v.dimension: v.verdict for v in reviewer.report.verdicts}
                if reviewer.report is not None else {})
    same_pair = bool(
        generator.record and reviewer.record
        and generator.record.get("reported_model")
        and generator.record.get("reported_model") == reviewer.record.get("reported_model"))
    return {
        "unit_id": f"{code}.r{replicate}",
        "scenario": code,
        "scenario_name": sc.SCENARIO_NAMES[code],
        "replicate": replicate,
        "corpus_id": corpus.corpus_id,
        "generator": {"role": generator.role, "requested_model": generator.requested,
                      "reported_model": (generator.record or {}).get("reported_model")},
        "reviewer": {"role": reviewer.role, "requested_model": reviewer.requested,
                     "reported_model": (reviewer.record or {}).get("reported_model")},
        "same_reported_model_pair": same_pair,
        "stages": _stages(generator, reviewer, outcome),
        "outcome": {"status": outcome.status, "code": outcome.code},
        "error": generator.last_error or reviewer.last_error,
        "reviewer_calls": getattr(reviewer, "calls", None),
        "measurement": sc.measure(code, candidate, verdicts, outcome.status),
    }


def _control_record(code: str, role: str, reviewer, report, error: str | None,
                    expected: str) -> dict:
    if report is None:
        report = getattr(reviewer, "report", None)
    verdicts = ({v.dimension: v.verdict for v in report.verdicts}
                if report is not None else {})
    verdict = verdicts.get(expected)
    outcome = sc.control_outcome(verdict, None if report is not None else error)
    return {
        "unit_id": f"{code}.{role}",
        "control": code,
        "role": role,
        "requested_model": reviewer.requested,
        "reported_model": (reviewer.record or {}).get("reported_model"),
        "expected_dimension": expected,
        "verdict": verdict,
        "verdicts": verdicts,
        "outcome": outcome,
        "error": error,
    }


def _execute(population, log: CallLog, make_generator, make_reviewer, budget) -> dict:
    participants = frozen_participants(population)
    by_role = {row["role"]: row for row in participants}
    units = []
    for code in sc.SCENARIO_CODES:
        corpus = sc.corpus_for(code)
        for replicate in (1, 2):
            gen_role, rev_role = ("A", "B") if replicate == 1 else ("B", "A")
            unit_id = f"{code}.r{replicate}"
            generator = make_generator(code, unit_id, replicate, gen_role,
                                       by_role[gen_role]["requested"])
            reviewer = make_reviewer(unit_id, replicate, rev_role,
                                     by_role[rev_role]["requested"])
            try:
                outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
            except SailangError as exc:
                outcome = ag.GenerationOutcome(status=ag.ERROR, code=exc.code)
            units.append(_unit_record(code, replicate, generator, reviewer, outcome, corpus))
    controls = []
    control_corpus = sc.control_corpus()
    for code in sc.CONTROL_CODES:
        candidate, expected_dimension = sc.control_candidate(code)
        resolved = aa.resolve_ally_evidence(
            candidate, ag.CorpusEvidenceResolver(control_corpus))
        for role in ("A", "B"):
            unit_id = f"{code}.{role}"
            reviewer = make_reviewer(unit_id, 0, role, by_role[role]["requested"],
                                     control_dimension=expected_dimension,
                                     control_expected=expected_dimension)
            report, error = None, None
            try:
                proof = ag.run_semantic_review(resolved, control_corpus, reviewer)
                report = proof.report
            except SailangError as exc:
                error = exc.code
            controls.append(_control_record(code, role, reviewer, report, error,
                                            expected_dimension))
    return {"participants": participants, "units": units, "review_controls": controls,
            "budget_used": budget.used}


def _counts(units: Sequence[Mapping]) -> dict:
    def count(predicate):
        return sum(1 for unit in units if predicate(unit))
    verdicts: dict[str, dict[str, int]] = {d: {} for d in ag.DIMENSIONS}
    for unit in units:
        for dimension, verdict in unit["measurement"]["reviewer_verdicts"].items():
            verdicts[dimension][verdict] = verdicts[dimension].get(verdict, 0) + 1
    return {
        "generator_attempts": len(units),
        "no_advice": count(lambda u: u["measurement"]["no_advice"]),
        "candidates": count(lambda u: u["measurement"]["candidate_emitted"]),
        "schema_errors": count(lambda u: u["stages"]["GENERATOR_PARSE"]
                               == sc.STAGE_SCHEMA_ERROR),
        "outside_corpus_refs": count(lambda u: u["stages"]["CORPUS_REF_GATE"]
                                     == sc.STAGE_FAIL),
        "scope_widening": count(lambda u: u["measurement"]["scope_widened"] is True),
        "false_pattern_candidates": count(
            lambda u: u["measurement"]["false_pattern_candidate"] is True),
        "missed_registered_counterevidence": count(
            lambda u: u["measurement"]["missed_registered_counterevidence"] is True),
        "final_outcomes": {
            status: count(lambda u, s=status: u["stages"]["FINAL_GATE_OUTCOME"] == s)
            for status in (ag.NO_ADVICE, ag.APPROVED, ag.REJECTED, ag.ERROR)},
        "review_verdicts": verdicts,
    }


def _route_identity(units: Sequence[Mapping]) -> tuple[dict, ...]:
    rows = []
    for unit in units:
        rows.append({
            "unit_id": unit["unit_id"],
            "generator_requested": unit["generator"]["requested_model"],
            "generator_reported": unit["generator"]["reported_model"],
            "reviewer_requested": unit["reviewer"]["requested_model"],
            "reviewer_reported": unit["reviewer"]["reported_model"],
            "same_reported_model_pair": unit["same_reported_model_pair"],
        })
    return tuple(rows)


def _control_counts(controls: Sequence[Mapping]) -> dict:
    rows: dict[str, dict[str, int]] = {}
    for control in controls:
        row = rows.setdefault(control["control"], {
            sc.CONTROL_DETECTED: 0, sc.CONTROL_UNCERTAIN: 0,
            sc.CONTROL_MISSED: 0, sc.CONTROL_ERROR: 0})
        row[control["outcome"]] = row.get(control["outcome"], 0) + 1
    return rows


def _artifact(status: str, registered: Mapping, population, log: CallLog, result: dict,
              budget: live.CallBudget, dry_run: bool, credential: Mapping,
              started: str, discovery_calls: int, stopped: str | None,
              reason: str | None = None) -> dict:
    population_record = population.as_record()
    units = result.get("units", [])
    controls = result.get("review_controls", [])
    counts = _counts(units)
    counts["review_controls"] = _control_counts(controls)
    artifact = {
        "authority": live.AUTHORITY,
        "is_not": list(live.IS_NOT),
        "note": live.NOTE,
        "status": status,
        "reason": reason,
        "dry_run": dry_run,
        "registration": dict(registered),
        "experiment_class": ec.classify_calls(population.combo, log.records,
                                              population_record),
        "harness": {"gateway": "9router", "base_url": live.BASE_URL,
                    "model_alias": live.COMBO, "protocol_version": live.PROTOCOL_VERSION,
                    "max_tokens": sc.registration()["prompts"]["max_tokens"],
                    "timeout_s": live.TIMEOUT_SECONDS,
                    "replicates": sc.REPLICATES, "scenarios": list(sc.SCENARIO_CODES),
                    "controls": list(sc.CONTROL_CODES)},
        "credential": dict(credential),
        "population": population_record,
        "participants_frozen": list(result.get("participants", ())),
        "route_identity": list(_route_identity(units)),
        "started": started,
        "max_calls": sc.MAX_CALLS,
        "planned_calls_max": sc.DISCOVERY_RESERVE + sc.GENERATION_CALLS_MAX
                             + sc.CONTROL_CALLS_MAX,
        "live_calls": budget.used,
        "discovery_calls": discovery_calls,
        "experiment_calls": budget.used - discovery_calls,
        "stopped": stopped,
        "counts": counts,
        "units": units,
        "review_controls": controls,
        "calls": log.records,
    }
    return artifact


def render(artifact: Mapping) -> str:
    """Counts with denominators per scenario, role, route and control. No score."""
    klass = artifact["experiment_class"]
    counts = artifact["counts"]
    out = [
        "# ALLY_ADVICE live generation experiment report",
        "",
        f"Authority: `{artifact['authority']}`, which is not "
        + ", ".join(f"`{x}`" for x in artifact["is_not"]) + ".",
        artifact["note"],
        "",
        f"Status `{artifact['status']}`"
        + (f" ({artifact['reason']})" if artifact.get("reason") else "")
        + f"; registration `{artifact['registration'].get('digest')}`; "
        f"{artifact['live_calls']} live calls "
        f"({artifact['discovery_calls']} discovery, {artifact['experiment_calls']} "
        f"experiment) of ceiling {artifact['max_calls']}; stopped: "
        f"{artifact['stopped'] or 'no'}.",
        ("Counts below are attached to scenario, role, route and replicate. They are not "
         "a model quality number and must not be read as one."),
        "",
        "## REGISTRATION",
        "",
        f"- REGISTRATION_ID: `{artifact['registration'].get('digest')}`",
        f"- REGISTRATION_FILE_SHA256: `{artifact['registration'].get('file_sha256')}`",
        f"- REGISTERED_UNDER: `{json.dumps(artifact['registration'].get('registered_under') or {})}`",
        "",
        "## EXPERIMENT_CLASS",
        "",
        f"- EXPERIMENT_CLASS: `{klass['experiment_class']}`",
        f"- COMBO: `{klass['combo']}`",
        "- OBSERVED_COMBO_MEMBERS: "
        + (", ".join(f"`{m}`" for m in klass["observed_combo_members"]) or "none"),
        "- EXTERNAL_COMPARATORS: "
        + (", ".join(f"`{m}`" for m in klass["external_comparators"]) or "none"),
        "- DISTINCT_REPORTED_MODELS: "
        + (", ".join(f"`{m}`" for m in klass["distinct_reported_models"]) or "none"),
        f"- ROSTER_STATUS: `{klass['roster_status']}`",
        "",
        "## GENERATOR_RESULTS",
        "",
    ]
    for code in sc.SCENARIO_CODES:
        rows = [u for u in artifact["units"] if u["scenario"] == code]
        if not rows:
            continue
        out.append(f"### {code} {sc.SCENARIO_NAMES[code]}")
        for row in rows:
            measurement = row["measurement"]
            out.append(
                f"- `{row['unit_id']}` generator `{row['generator']['reported_model']}` "
                f"reviewer `{row['reviewer']['reported_model']}`: "
                f"candidate_emitted={measurement['candidate_emitted']} "
                f"no_advice={measurement['no_advice']} "
                f"final={measurement['final_gate_outcome']}"
                + (f" false_pattern_candidate={measurement['false_pattern_candidate']}"
                   if measurement["false_pattern_candidate"] is not None else "")
                + (f" scope_widened={measurement['scope_widened']}"
                   if measurement["scope_widened"] is not None else "")
                + (f" counterexample_ref_cited={measurement['counterexample_ref_cited']}"
                   if measurement["counterexample_ref_cited"] is not None else "")
                + (f" registered_weakening_ref_cited="
                   f"{measurement['registered_weakening_ref_cited']}"
                   if measurement["registered_weakening_ref_cited"] is not None else "")
                + (f" outcome_code={row['outcome']['code']}"
                   if row["outcome"]["code"] else "")
                + (" same_reported_model_pair=true"
                   if row["same_reported_model_pair"] else ""))
        out.append("")
    out += [
        "## GENERATOR_TOTALS",
        "",
        f"- attempts {counts['generator_attempts']}",
        f"- NO_ADVICE {counts['no_advice']}/{counts['generator_attempts']}",
        f"- candidates {counts['candidates']}/{counts['generator_attempts']}",
        f"- schema errors {counts['schema_errors']}/{counts['generator_attempts']}",
        (f"- candidates citing outside-corpus refs {counts['outside_corpus_refs']}/"
         f"{counts['generator_attempts']}"),
        (f"- scope-widening events {counts['scope_widening']}/{counts['candidates']} "
         "emitted candidates"),
        f"- FALSE_PATTERN_CANDIDATE events {counts['false_pattern_candidates']}",
        (f"- MISSED_REGISTERED_COUNTEREVIDENCE events "
         f"{counts['missed_registered_counterevidence']}"),
        f"- final gate outcomes {json.dumps(counts['final_outcomes'])}",
        "",
        "## SEMANTIC_REVIEW",
        "",
    ]
    for dimension, verdicts in counts["review_verdicts"].items():
        shown = ", ".join(f"{k} {v}" for k, v in sorted(verdicts.items())) or "no calls"
        out.append(f"- {dimension}: {shown}")
    out += ["", "## REVIEW_CONTROL_RESULTS", ""]
    expected = {row["code"]: row for row in sc.control_registration()}
    for code in sc.CONTROL_CODES:
        row = counts["review_controls"].get(code, {})
        out.append(f"- {code} (expected dimension `{expected[code]['expected_dimension']}`): "
                   + ", ".join(f"{k} {v}" for k, v in sorted(row.items()) if v))
    out += ["", "## TRANSPORT", ""]
    functions: dict[str, int] = {}
    for call in artifact["calls"]:
        functions[call["function"]] = functions.get(call["function"], 0) + 1
    for name, count in sorted(functions.items()):
        out.append(f"- {name}: {count} call(s)")
    errors = [c for c in artifact["calls"] if c.get("status") == "ERROR"]
    out.append(f"- errors: {len(errors)}")
    for call in errors:
        out.append(f"  - `{call['unit_id']}` {call['function']} "
                   f"{call.get('error_class')}: {call.get('error')}")
    out += ["", "## HIDDEN_CONTEXT_OBSERVATION", ""]
    out.append("Gateway-reported input tokens against the locally estimated prompt, per "
               "call. What fills any difference is not visible and is not guessed at.")
    deltas = [c["prompt_token_delta"] for c in artifact["calls"]
              if isinstance(c.get("prompt_token_delta"), int)]
    out.append(f"- measured calls: {len(deltas)}; delta range: "
               f"{min(deltas) if deltas else 'n/a'}..{max(deltas) if deltas else 'n/a'}")
    out += [
        "",
        "## WHAT THIS RUN DOES NOT SHOW",
        "",
        ("- It does not show which model is better, smarter or more trustworthy: each "
         "scenario has two role-swapped samples and one control result is a behaviour "
         "sample, not a model property."),
        ("- It does not show that any generated interpretation is true, that a pattern is "
         "real or that a reviewer verdict is correct."),
        ("- It does not generalise from this registered sample to model behaviour, to "
         "SAIFREN as a population, or to any other corpus."),
        "- It does not measure novelty, usefulness or the content of any hidden context.",
        "",
    ]
    return "\n".join(out)


# ---------------------------------------------------------------- runner


def declared_registration() -> dict:
    return sc.registration()


def check_registration(path: pathlib.Path = REGISTRATION,
                       expected_registration_id: str | None = None) -> dict:
    declared = declared_registration()
    if not path.is_file():
        raise RegistrationMismatch(f"{sc.REGISTRATION_MISSING}: {path.name} does not exist; "
                                   "the experiment plan is registered before it runs")
    try:
        raw = path.read_bytes()
        stored = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        raise RegistrationMismatch(
            f"{sc.REGISTRATION_UNREADABLE}: {path.name} is not a readable registration "
            f"({type(exc).__name__}); an interrupted registration is re-created by an "
            "explicit decision, not by a rerun") from None
    if not isinstance(stored, dict):
        raise RegistrationMismatch(f"{sc.REGISTRATION_UNREADABLE}: {path.name} is not a "
                                   "registration object")
    if stored.get("registration") != declared or stored.get("digest") != sc.digest(declared):
        raise RegistrationMismatch(
            f"{sc.REGISTRATION_MISMATCH}: the plan in code differs from {path.name}; a "
            "changed scenario, control, prompt, budget or rule is a new registration, "
            "never an edit")
    identity = stored["digest"]
    if expected_registration_id is not None and expected_registration_id != identity:
        raise RegistrationMismatch(
            f"{sc.REGISTRATION_MISMATCH}: the runner was started for registration "
            f"{expected_registration_id!r} but the file holds {identity!r}")
    return {"digest": identity, "file": path.name,
            "file_sha256": "sha256:" + hashlib.sha256(raw).hexdigest(),
            "registered_under": stored.get("registered_under")}


def register(path: pathlib.Path = REGISTRATION, registered_under: dict | None = None) -> dict:
    declared = declared_registration()
    record = {"registration": declared, "digest": sc.digest(declared),
              "registered_under": registered_under or {}}
    payload = (json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        publish_immutable(path, payload, conflict_code=sc.REGISTRATION_CONFLICT)
    except SailangError as exc:
        raise RegistrationMismatch(f"{exc.code}: {exc.detail}") from None
    return record


def _budget_check() -> int:
    planned = sc.DISCOVERY_RESERVE + sc.GENERATION_CALLS_MAX + sc.CONTROL_CALLS_MAX
    if planned > sc.MAX_CALLS:
        raise SystemExit(f"the registered plan needs up to {planned} calls, over the "
                         f"ceiling of {sc.MAX_CALLS}")
    return planned


def run(out_dir: pathlib.Path, dry_run: bool, api_key: str = "",
        transport: object | None = None, population=None, discover: bool | None = None,
        credential_source: str = SOURCE_STORE, handle: str = DEFAULT_HANDLE,
        registration_path: pathlib.Path = REGISTRATION,
        expected_registration_id: str | None = None,
        update_latest: bool = True) -> dict:
    registered = check_registration(registration_path, expected_registration_id)
    planned = _budget_check()
    log = CallLog()
    budget = live.CallBudget(sc.MAX_CALLS)
    credential = {"handle": handle, "source": credential_source, "backend": None}
    started = live._now()

    if dry_run:
        population = _dry_population()
        result = _execute(
            population, log,
            lambda code, unit_id, replicate, role, requested: DryGenerator(
                code, unit_id=unit_id, replicate=replicate, role=role, requested=requested),
            lambda unit_id, replicate, role, requested, control_dimension=None,
            control_expected=None: DryReviewer(
                unit_id, replicate=replicate, role=role, requested=requested,
                control_dimension=control_dimension, control_expected=control_expected),
            budget)
        artifact = _artifact("DRY_RUN", registered, population, log, result, budget, True,
                             credential, started, 0, None)
        _assert_dry_run(result, artifact, planned)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "ally_generation_dry_run.json"
        live._write_immutable(path, json.dumps(artifact, indent=2, ensure_ascii=False) + "\n")
        return {**artifact, "artifact": str(path), "planned_calls_max": planned}

    if not dry_run and transport is None:
        if not api_key:
            try:
                resolved = resolve(handle=handle, source=credential_source)
            except (CredentialNotProvisioned, CredentialError) as exc:
                return _write_no_go(
                    out_dir, registered, sc.LIVE_NOT_RUN_CREDENTIAL_UNAVAILABLE,
                    str(exc), log, budget, started, credential)
            api_key, credential["backend"] = resolved.secret, resolved.backend
        transport = live.HttpTransport(api_key)

    discovering = (transport is not None) if discover is None else (
        bool(discover) and not dry_run)
    auth_refused_note = None
    if population is None:
        if discovering and transport is not None:
            try:
                population = resolve_population(transport, budget, log)
            except live.AuthRefused as exc:
                auth_refused_note = str(exc)
                population = pop.offline_population(
                    live.COMBO, live._now(), f"authentication refused: {auth_refused_note}")
        else:
            population = pop.offline_population(live.COMBO, live._now(),
                                                "discovery was not requested")
    discovery_calls = budget.used
    participants = frozen_participants(population)
    if not heterogeneous(participants):
        return _write_no_go(
            out_dir, registered, sc.NO_GO_POPULATION,
            "fewer than two answering distinct requested participants resolved within the "
            "bounded selection policy; no scenario call was started",
            log, budget, started, credential, population=population,
            discovery_calls=discovery_calls)

    runner = live.Runner(None if transport is None else transport.send, budget,
                         alias=live.COMBO)
    if auth_refused_note:
        runner.stopped = f"AUTH_REFUSED: {auth_refused_note}"
    dispatch = Dispatch(runner, log)
    result = _execute(
        population, log,
        lambda code, unit_id, replicate, role, requested: LabGenerator(
            dispatch, unit_id=unit_id, replicate=replicate, role=role, requested=requested),
        lambda unit_id, replicate, role, requested, control_dimension=None,
        control_expected=None: LabReviewer(
            dispatch, unit_id=unit_id, replicate=replicate, role=role, requested=requested),
        budget)
    artifact = _artifact(STATUS_COMPLETED, registered, population, log, result, budget,
                         False, credential, started, discovery_calls, runner.stopped)
    serialized = json.dumps(artifact, indent=2, ensure_ascii=False)
    live.assert_no_secret(serialized, api_key)
    report_text = render(artifact)
    live.assert_no_secret(report_text, api_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.replace("-", "").replace(":", "")
    run_id = uuid.uuid4().hex[:16]
    name = f"ally_generation_live_{stamp}_{run_id}.json"
    path = out_dir / name
    live._write_immutable(path, serialized + "\n")
    report = out_dir / f"ALLY_GENERATION_REPORT_{stamp}_{run_id}.md"
    live._write_immutable(report, f"Source artifact: `{name}`\n\n{report_text}")
    written = {"artifact": str(path), "report": str(report)}
    if update_latest:
        written["latest"] = str(update_latest_index(out_dir.parent / "LATEST.md", artifact,
                                                    name, stamp))
    return {**artifact, **written}


def _dry_population():
    population = pop.offline_population(live.COMBO, live._now(), "a dry run makes no call")
    population.participants = (
        pop.Participant(role="A", requested=live.COMBO, reported_model=None,
                        member_status=pop.OBSERVED_COMBO_MEMBER, source="COMBO_ALIAS"),
        pop.Participant(role="B", requested=DRY_EXTERNAL, reported_model=None,
                        member_status=pop.NOT_PROVEN_COMBO_MEMBER,
                        source="CATALOG_ELIGIBLE"),
    )
    return population


def _assert_dry_run(result: Mapping, artifact: Mapping, planned: int) -> None:
    """The registered dry-run proofs; a failed one refuses to write anything."""
    assert planned <= sc.MAX_CALLS, "the registered plan exceeds the call ceiling"
    by_id = {unit["unit_id"]: unit for unit in result["units"]}
    for unit in result["units"]:
        if unit["measurement"]["no_advice"]:
            assert unit["reviewer_calls"] == 0, (
                "NO_ADVICE must spend zero reviewer calls")
            assert unit["stages"]["SEMANTIC_REVIEW"] == sc.STAGE_SKIPPED
        if unit["measurement"]["final_gate_outcome"] == ag.REJECTED:
            assert unit["reviewer_calls"] == 1, (
                "a rejected candidate spends exactly one reviewer call")
    assert by_id["G1.r1"]["generator"]["role"] == "A"
    assert by_id["G1.r1"]["reviewer"]["role"] == "B"
    assert by_id["G1.r2"]["generator"]["role"] == "B"
    assert by_id["G1.r2"]["reviewer"]["role"] == "A"
    assert len(result["review_controls"]) == 6, "3 controls x 2 participants"
    assert all(row["outcome"] == sc.CONTROL_DETECTED
               for row in result["review_controls"]), (
        "the dry reviewer must detect every registered control defect")
    json.dumps(artifact, ensure_ascii=False)


def _no_go_artifact(registered: Mapping, status: str, reason: str, log: CallLog,
                    budget: live.CallBudget, started: str, credential: Mapping,
                    population=None, discovery_calls: int = 0) -> dict:
    if population is None:
        population = pop.offline_population(live.COMBO, live._now(), reason)
    result = {"participants": frozen_participants(population), "units": [],
              "review_controls": [], "budget_used": budget.used}
    artifact = _artifact(status, registered, population, log, result, budget, False,
                         credential, started, discovery_calls, None, reason=reason)
    return artifact


def _write_no_go(out_dir: pathlib.Path, registered: Mapping, status: str, reason: str,
                 log: CallLog, budget: live.CallBudget, started: str,
                 credential: Mapping, population=None, discovery_calls: int = 0) -> dict:
    artifact = _no_go_artifact(registered, status, reason, log, budget, started,
                               credential, population, discovery_calls)
    serialized = json.dumps(artifact, indent=2, ensure_ascii=False)
    live.assert_no_secret(serialized, "")
    report_text = render(artifact)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.replace("-", "").replace(":", "")
    run_id = uuid.uuid4().hex[:16]
    name = f"ally_generation_nogo_{stamp}_{run_id}.json"
    path = out_dir / name
    live._write_immutable(path, serialized + "\n")
    report = out_dir / f"ALLY_GENERATION_REPORT_{stamp}_{run_id}.md"
    live._write_immutable(report, f"Source artifact: `{name}`\n\n{report_text}")
    return {**artifact, "artifact": str(path), "report": str(report)}


def update_latest_index(path: pathlib.Path, artifact: Mapping, artifact_name: str,
                        stamp: str) -> pathlib.Path:
    """Additive ALLY_ADVICE section in the lab index; never rewrites earlier rows."""
    section = [
        "",
        "## ALLY_ADVICE live generation experiment (T-63)",
        "",
        ("A registered generator/reviewer experiment above the frozen B-016 layer: four "
         "synthetic scenarios, three reviewer red controls, two role-swapped replicates, "
         "one bounded live run. Its artifact and report follow the same immutability rules "
         "as the runs above; the interpretation lives in `lab/analysis/`."),
        "",
        f"- started: `{artifact['started']}`",
        f"- artifact: `{artifact_name}`",
        f"- REGISTRATION_ID: `{artifact['registration'].get('digest')}`",
        (f"- live calls: {artifact['live_calls']} "
         f"({artifact['discovery_calls']} discovery, {artifact['experiment_calls']} "
         f"experiment) of ceiling {artifact['max_calls']}"),
        f"- status: `{artifact['status']}`",
        "",
    ]
    text = path.read_text(encoding="utf-8") if path.exists() else "# SAIFREN live runs — index\n"
    marker = f"- artifact: `{artifact_name}`"
    if marker not in text:
        text = text.rstrip("\n") + "\n" + "\n".join(section).rstrip("\n") + "\n"
        path.write_text(text, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Registered AllyAdvice live generation/review experiment (LAB ONLY). "
                    "The credential is resolved from the named handle through the local "
                    "credential store; no secret is read from the environment.")
    parser.add_argument("--out", default="lab/out")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--register", action="store_true",
                        help="write the registration file once, before any live call")
    parser.add_argument("--ticket")
    parser.add_argument("--source-receipt")
    parser.add_argument("--decision")
    parser.add_argument("--handle", default=DEFAULT_HANDLE)
    parser.add_argument("--credential-source", choices=list(SOURCES), default=SOURCE_STORE)
    parser.add_argument("--expected-registration-id",
                        help="refuse live calls unless the registration file carries this "
                             "frozen identity")
    args = parser.parse_args(argv)
    if args.register:
        record = register(registered_under={
            "ticket": args.ticket, "source_receipt": args.source_receipt,
            "decision": args.decision})
        print(json.dumps({"registered": REGISTRATION.name, "digest": record["digest"]},
                         indent=2))
        return 0
    result = run(pathlib.Path(args.out), args.dry_run, credential_source=args.credential_source,
                 handle=args.handle, expected_registration_id=args.expected_registration_id)
    shown = {k: result.get(k) for k in
             ("artifact", "report", "authority", "dry_run", "status", "reason",
              "registration", "live_calls", "discovery_calls", "experiment_calls",
              "max_calls", "stopped", "credential", "counts")}
    shown["experiment_class"] = {
        k: result["experiment_class"][k] for k in
        ("experiment_class", "observed_combo_members", "external_comparators",
         "roster_status")}
    printed = json.dumps(shown, indent=2)
    live.assert_no_secret(printed, "")
    print(printed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
