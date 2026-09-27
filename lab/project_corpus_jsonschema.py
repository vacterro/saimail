"""FG-04B: one registered bounded live JSON_SCHEMA reachability experiment (T-81).

    ONE NEW VARIABLE: generator/probe response_format ABSENT -> JSON_SCHEMA.
    EVERYTHING ELSE FROZEN: corpus, routes, roles, prompts, budgets, no retry.

This harness is the T-74 budget4096 experiment with exactly one intentional
change: the generator (and the capability probe) request carries a registered
``json_schema`` response format.  The reviewer stays ``response_format`` absent
at 2048 tokens, the generator stays 4096, the local 4000-character projection is
still replaced by the LAB-only ephemeral full-visible-output path, and the
unchanged B-016 production gates decide every outcome.

The registered schema policy is ``CORPUS_ENUM``: ``EVIDENCE_REFS`` values are
enumerated to the exact frozen B-018 corpus evidence-ref set.  The schema
therefore participates in restricting reference vocabulary BEFORE the existing
product reference gate, which remains independently authoritative.  The
``SYNTAX_ONLY`` alternative was considered and rejected in the registration
because T-74 already observed an outside-corpus rejection under no schema at
all: re-testing the same membership failure with a shape-only constraint cannot
distinguish non-enforcement from vocabulary confusion.

Only metadata is durable: identities, hashes, byte lengths, routes, verdicts and
counts.  No prompt text, corpus content, generated prose, reviewer rationale or
provider error body is persisted.  The full ephemeral output exists only inside
one stage and is scrubbed in a ``finally`` block even on a parse failure.

Admission is mechanical and precedes the first network call: the
EXPERIMENT-MANIFEST-1 manifest is loaded, ``verify_current`` and ``admit_live``
are run, and every registered identity (manifest, schema bytes, allowed refs,
implementation, inputs, budgets, telemetry contract) is re-proved.  Historical
verification alone never authorizes this run.

    python lab/project_corpus_jsonschema.py --register
    python lab/project_corpus_jsonschema.py --dry-run
    python lab/project_corpus_jsonschema.py --run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import uuid
from collections.abc import Mapping

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lab import ally_generation_live as al
from lab import ally_generation_scenarios as sc
from lab import ephemeral_output as eph
from lab import experiment_manifest as em
from lab import parse_shape as shape
from lab import project_corpus_generation_pilot as pilot
from lab import project_corpus_reachability as reach
from lab import reference_telemetry as ref
from lab import saifren_population as pop
from lab import saifren_run as live
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag
from saimail.credentials import CredentialError, CredentialNotProvisioned, resolve
from saimail.publish import PUBLISHED, publish_immutable

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRATION_FILE = "lab/project_corpus_jsonschema_registration.json"
SCHEMA_FILE = "lab/project_corpus_jsonschema_schema.json"
MANIFEST_FILE = "lab/project_corpus_jsonschema_manifest.json"
VERSION = "PROJECT-CORPUS-JSONSCHEMA-1"
RULES = "saimail-project-corpus-jsonschema/1"
EXPERIMENT_NAME = "ALLY_ADVICE REAL PROJECT BOUNDED JSON_SCHEMA REACHABILITY EXPERIMENT"
MANIFEST_EXPERIMENT_ID = "FG-04B-PROJECT-CORPUS-JSONSCHEMA-1"

ROUTES = {"A": "SAIFREN", "B": "goat/MiniMaxAI/MiniMax-M3"}

POLICY_CORPUS_ENUM = "CORPUS_ENUM"
POLICY_SYNTAX_ONLY = "SYNTAX_ONLY"
SCHEMA_WRAPPER_NAME = "saimail_ally_advice_candidate"
KIND_JSON_SCHEMA = "JSON_SCHEMA"
KIND_NONE = "NONE"

PROBE_PROMPT = 'Reply with exactly one JSON object and nothing else: {"result":"NO_ADVICE"}'

TOKEN_BUDGETS = {"PROBE": live.PROBE_MAX_TOKENS, "GENERATOR": 4096, "REVIEWER": 2048}
MAX_LIVE_CALLS = 6
PROBE_MAX = 2
GENERATION_MAX = 2
REVIEW_MAX = 2
PLANNED_CALLS_MAX = PROBE_MAX + GENERATION_MAX + REVIEW_MAX
LEGACY_OUTPUT_CHARS = live.MAX_OUTPUT_CHARS
ATTEMPT_MARKER = "lab/out/project_corpus_jsonschema_live_attempt.json"

TRANSPORT_FAILURE = "TRANSPORT_FAILURE"
JSON_PARSE_FAILURE = "JSON_PARSE_FAILURE"
JSON_SCHEMA_FAILURE = "JSON_SCHEMA_FAILURE"
REFERENCE_GATE_FAILURE = "REFERENCE_GATE_FAILURE"
EVENT_FLOOR_FAILURE = "EVENT_FLOOR_FAILURE"
REVIEWER_NOT_REACHED = "REVIEWER_NOT_REACHED"
REVIEWER_FAIL = "REVIEWER_FAIL"
REVIEWER_UNKNOWN = "REVIEWER_UNKNOWN"
REVIEWER_ERROR = "REVIEWER_ERROR"
NO_ADVICE_OUTCOME = "NO_ADVICE"
REVIEWER_PASS = "REVIEWER_PASS"
OUTCOME_CLASSES = frozenset({
    TRANSPORT_FAILURE, JSON_PARSE_FAILURE, JSON_SCHEMA_FAILURE,
    REFERENCE_GATE_FAILURE, EVENT_FLOOR_FAILURE, REVIEWER_NOT_REACHED,
    REVIEWER_FAIL, REVIEWER_UNKNOWN, REVIEWER_ERROR, NO_ADVICE_OUTCOME,
    REVIEWER_PASS})

JSON_NOT_TEXT = "NOT_TEXT"
JSON_BAD_JSON = "BAD_JSON"
JSON_EXTRA_DATA = "EXTRA_DATA"
JSON_DUPLICATE_KEY = "DUPLICATE_KEY"
JSON_NOT_OBJECT = "NOT_OBJECT"
JSON_OK = "OK"
JSON_STATUSES = frozenset({JSON_NOT_TEXT, JSON_BAD_JSON, JSON_EXTRA_DATA,
                           JSON_DUPLICATE_KEY, JSON_NOT_OBJECT, JSON_OK})
SCHEMA_VALID = "VALID"
SCHEMA_INVALID = "INVALID"
SCHEMA_NOT_EVALUABLE = "NOT_EVALUABLE"
SCHEMA_STATUSES = frozenset({SCHEMA_VALID, SCHEMA_INVALID, SCHEMA_NOT_EVALUABLE})
SCHEMA_REASONS = frozenset({"CONSTRAINT", "DUPLICATE_KEY", "TYPE"})

CAP_ACCEPTED = "REQUEST_ACCEPTED"
CAP_REJECTED = "REQUEST_REJECTED"
CAP_TRANSPORT_ERROR = "TRANSPORT_ERROR"
CAP_NOT_RUN = "NOT_RUN"
CAPABILITIES = frozenset({CAP_ACCEPTED, CAP_REJECTED, CAP_TRANSPORT_ERROR, CAP_NOT_RUN})

ENFORCEMENT_NOT_PROVEN = "NOT_PROVEN"

JSONSCHEMA_REGISTRATION_MISMATCH = "JSONSCHEMA_REGISTRATION_MISMATCH"
JSONSCHEMA_REGISTRATION_MISSING = "JSONSCHEMA_REGISTRATION_MISSING"
JSONSCHEMA_REGISTRATION_UNREADABLE = "JSONSCHEMA_REGISTRATION_UNREADABLE"
JSONSCHEMA_SCHEMA_EXISTS = "JSONSCHEMA_SCHEMA_EXISTS"
JSONSCHEMA_MANIFEST_EXISTS = "JSONSCHEMA_MANIFEST_EXISTS"
JSONSCHEMA_REGISTRATION_EXISTS = "JSONSCHEMA_REGISTRATION_EXISTS"
JSONSCHEMA_MANIFEST_DRIFT = "JSONSCHEMA_MANIFEST_DRIFT"
JSONSCHEMA_ADMISSION_REFUSED = "JSONSCHEMA_ADMISSION_REFUSED"
JSONSCHEMA_CORPUS_DRIFT = "JSONSCHEMA_CORPUS_DRIFT"
JSONSCHEMA_SCHEMA_DRIFT = "JSONSCHEMA_SCHEMA_DRIFT"
JSONSCHEMA_REF_SET_DRIFT = "JSONSCHEMA_REF_SET_DRIFT"
JSONSCHEMA_PROMPT_DRIFT = "JSONSCHEMA_PROMPT_DRIFT"
JSONSCHEMA_TOKEN_BUDGET_DRIFT = "JSONSCHEMA_TOKEN_BUDGET_DRIFT"
JSONSCHEMA_IMPLEMENTATION_DRIFT = "JSONSCHEMA_IMPLEMENTATION_DRIFT"
JSONSCHEMA_TELEMETRY_UNAVAILABLE = "JSONSCHEMA_TELEMETRY_UNAVAILABLE"
JSONSCHEMA_CREDENTIAL_UNAVAILABLE = "JSONSCHEMA_CREDENTIAL_UNAVAILABLE"
JSONSCHEMA_ALREADY_ATTEMPTED = "JSONSCHEMA_ALREADY_ATTEMPTED"
JSONSCHEMA_DRY_CONTROL_REQUIRED = "JSONSCHEMA_DRY_CONTROL_REQUIRED"
JSONSCHEMA_DRY_CONTROL_FAILED = "JSONSCHEMA_DRY_CONTROL_FAILED"
JSONSCHEMA_ARTIFACT_EXISTS = "JSONSCHEMA_ARTIFACT_EXISTS"
JSONSCHEMA_VALIDATOR_UNSUPPORTED_KEYWORD = "JSONSCHEMA_VALIDATOR_UNSUPPORTED_KEYWORD"
JSONSCHEMA_DESIGN_BUDGET_INSUFFICIENT = "JSONSCHEMA_DESIGN_BUDGET_INSUFFICIENT"
JSONSCHEMA_HARNESS_ERROR = "JSONSCHEMA_HARNESS_ERROR"

IMPL_ROLES = {
    "lab/ally_generation_live.py": "PARSER",
    "lab/ephemeral_output.py": "EXTRACTOR",
    "lab/experiment_manifest.py": "RUNNER",
    "lab/parse_shape.py": "PARSER",
    "lab/project_corpus_generation_pilot.py": "EXTRACTOR",
    "lab/project_corpus_jsonschema.py": "RUNNER",
    "lab/reference_telemetry.py": "PARSER",
    "saimail/ally_advice.py": "GRADER",
    "saimail/ally_generation.py": "GRADER",
}

ADMISSION_CHECKS = (
    "manifest_newly_registered",
    "manifest_identity_matches_registration",
    "implementation_identity_matches_registration",
    "input_identities_match_registration",
    "current_corpus_matches_frozen_corpus",
    "schema_bytes_match_registration",
    "allowed_reference_set_matches_registration",
    "budgets_match_registration",
    "call_ceiling_active",
    "fg04a_telemetry_available",
    "live_admission_granted_by_admit_live",
)

_JSON_TYPES = {"object": dict, "array": list, "string": str}
_SCHEMA_KEYWORDS = frozenset({
    "type", "oneOf", "enum", "properties", "required", "additionalProperties",
    "items", "minItems", "maxItems", "uniqueItems", "minLength"})


class DryTransport:
    """Deterministic wire outputs through the same dispatch and strict parsers."""

    def __init__(self, corpus: ag.ReflectionCorpus, *,
                 candidate: aa.AllyAdvice | None = None) -> None:
        self.corpus = corpus
        self._candidate = candidate or pilot.two_event_candidate(corpus)

    def send_dispatched(self, prompt: str, *, model: str | None = None,
                        max_tokens: int = TOKEN_BUDGETS["PROBE"],
                        response_format: dict | None = None) -> dict:
        if prompt == PROBE_PROMPT:
            output = '{"result":"NO_ADVICE"}'
        elif response_format is None:
            output = pilot.wire_review_text(self._candidate, self.corpus)
        elif model == ROUTES["A"]:
            output = pilot.wire_candidate_text(self._candidate)
        else:
            output = '{"result":"NO_ADVICE"}'
        return {
            "output": output[:LEGACY_OUTPUT_CHARS],
            "full_output": output,
            "reported_model": model,
            "http_status": 200,
            "finish_reason": "stop",
            "output_truncated": False,
            "inline_trace_removed": False,
            "latency_s": 0.0,
            "usage": {},
            "error_class": None,
            "request_body_sha256": shape.digest(
                json.dumps({"model": model, "stream": False, "max_tokens": max_tokens,
                            "messages": [{"role": "user", "content": prompt}]})),
            "request_body_bytes": len(json.dumps(
                {"model": model, "stream": False, "max_tokens": max_tokens,
                 "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")),
        }


class SchemaTransport(eph.EphemeralTransport):
    """The ephemeral full-output transport plus one registered response_format.

    One dispatch is one request.  When a format is present the exact outgoing
    body is rewritten once before the single delegation; the body that is
    dispatched is the body that is recorded, so the schema identity is provable
    from the artifact rather than asserted.
    """

    def send_dispatched(self, prompt: str, *, model: str | None = None,
                        max_tokens: int = live.MAX_TOKENS,
                        response_format: dict | None = None) -> dict:
        bodies: list = []
        chunks: list = []
        inner = self._opener

        def watch(request, timeout):
            data = getattr(request, "data", None)
            if response_format is not None and isinstance(data, (bytes, bytearray)):
                body = json.loads(bytes(data).decode("utf-8"))
                body["response_format"] = response_format
                request.data = json.dumps(body).encode("utf-8")
                data = request.data
            if isinstance(data, (bytes, bytearray)):
                bodies.append(bytes(data))
            return eph._CaptureResponse(inner(request, timeout), chunks)

        self._opener = watch
        try:
            result = live.HttpTransport.send(self, prompt, model=model, max_tokens=max_tokens)
        finally:
            self._opener = inner
        result = dict(result)
        if len(bodies) == 1:
            result["request_body_sha256"] = hashlib.sha256(bodies[0]).hexdigest()
            result["request_body_bytes"] = len(bodies[0])
        else:
            result["request_body_sha256"] = None
            result["request_body_bytes"] = None
        result["full_output"] = None
        result["output_truncated"] = None
        result["legacy_projection_would_truncate"] = None
        if result.get("error_class"):
            return result
        payload = eph._parse_payload(b"".join(chunks)) if chunks else None
        if payload is None:
            return result
        full = eph.visible_full(payload)
        result["full_output"] = full
        result["output_truncated"] = False
        result["legacy_projection_would_truncate"] = len(full) > LEGACY_OUTPUT_CHARS
        return result


def _reject(code: str, detail: str = "registered JSON_SCHEMA boundary refused") -> None:
    raise SailangError(code, detail)


def canonical_bytes(document) -> bytes:
    """Canonical compact JSON, sorted keys, UTF-8, no trailing newline."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def registration_bytes(document) -> bytes:
    return canonical_bytes(document) + b"\n"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: pathlib.Path) -> str:
    return _digest(path.read_bytes())


def build_schema(evidence_refs) -> dict:
    """The exact registered JSON Schema for one corpus-enumerated EVIDENCE_REF set."""
    refs = sorted(set(evidence_refs))
    item = {
        "type": "object",
        "properties": {
            "STATEMENT": {"type": "string", "minLength": 1},
            "EVIDENCE_REFS": {
                "type": "array",
                "minItems": 1,
                "maxItems": aa.MAX_EVIDENCE_REFS_PER_ITEM,
                "uniqueItems": True,
                "items": {"type": "string", "enum": refs},
            },
        },
        "required": ["STATEMENT", "EVIDENCE_REFS"],
        "additionalProperties": False,
    }
    candidate = {
        "type": "object",
        "properties": {
            "result": {"type": "string", "enum": [ag.CANDIDATE]},
            "WORK_CONTEXT": {"type": "string", "minLength": 1},
            "OBSERVED_SCOPE": {"type": "string", "enum": [pilot.B018_PROJECT_SCOPE]},
            "OBSERVED": {
                "type": "array",
                "minItems": aa.MIN_OBSERVATIONS,
                "maxItems": aa.MAX_OBSERVATIONS,
                "items": item,
            },
            "INFERRED": {"type": "string", "minLength": 1},
            "GUIDANCE_MODE": {"type": "string", "enum": list(aa.GUIDANCE_MODES)},
            "SUGGESTED": {"type": "string", "minLength": 1},
            "COUNTEREVIDENCE": {
                "type": "array",
                "minItems": 1,
                "maxItems": aa.MAX_COUNTEREVIDENCE,
                "items": item,
            },
            "UNCERTAINTY": {"type": "string", "minLength": 1},
        },
        "required": ["result", "WORK_CONTEXT", "OBSERVED_SCOPE", "OBSERVED", "INFERRED",
                     "GUIDANCE_MODE", "SUGGESTED", "COUNTEREVIDENCE", "UNCERTAINTY"],
        "additionalProperties": False,
    }
    no_advice = {
        "type": "object",
        "properties": {"result": {"type": "string", "enum": [ag.NO_ADVICE]}},
        "required": ["result"],
        "additionalProperties": False,
    }
    return {"type": "object", "oneOf": [no_advice, candidate]}


def schema_response_format(schema: Mapping) -> dict:
    return {"type": "json_schema",
            "json_schema": {"name": SCHEMA_WRAPPER_NAME, "strict": True,
                            "schema": dict(schema)}}


def _schema_valid(value, schema) -> bool:
    """Bounded validator for exactly the keyword set the registered schema uses.

    An unsupported keyword is a hard refusal, never a silently ignored
    constraint, so a drifted schema cannot pass through a weaker check.
    """
    for keyword in schema:
        if keyword not in _SCHEMA_KEYWORDS:
            _reject(JSONSCHEMA_VALIDATOR_UNSUPPORTED_KEYWORD,
                    f"the registered schema validator does not support {keyword!r}")
    if "oneOf" in schema:
        matches = 0
        for option in schema["oneOf"]:
            if _schema_valid(value, option):
                matches += 1
        return matches == 1
    if "type" in schema:
        expected = _JSON_TYPES.get(schema["type"])
        if expected is None:
            _reject(JSONSCHEMA_VALIDATOR_UNSUPPORTED_KEYWORD,
                    f"the registered schema validator does not support type {schema['type']!r}")
        if type(value) is not expected:
            return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if type(value) is str and "minLength" in schema and len(value) < schema["minLength"]:
        return False
    if type(value) is list:
        if "minItems" in schema and len(value) < schema["minItems"]:
            return False
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return False
        if schema.get("uniqueItems") is True:
            rendered = [json.dumps(item, sort_keys=True, ensure_ascii=False)
                        for item in value]
            if len(set(rendered)) != len(rendered):
                return False
        if "items" in schema:
            for item in value:
                if not _schema_valid(item, schema["items"]):
                    return False
    if type(value) is dict:
        if "additionalProperties" in schema and schema["additionalProperties"] is not False:
            _reject(JSONSCHEMA_VALIDATOR_UNSUPPORTED_KEYWORD,
                    "only additionalProperties=False is supported")
        for name in schema.get("required", ()):
            if name not in value:
                return False
        properties = schema.get("properties", {})
        for name, item in value.items():
            if name in properties:
                if not _schema_valid(item, properties[name]):
                    return False
            elif schema.get("additionalProperties") is False:
                return False
    return True


def schema_check(raw, schema: Mapping) -> tuple[str, str, str | None]:
    """Independent JSON and registered-schema observation of one raw output."""
    if not isinstance(raw, str) or not raw.strip():
        return JSON_NOT_TEXT, SCHEMA_NOT_EVALUABLE, None
    duplicates: list = []

    def pairs(items):
        seen = {}
        for key, value in items:
            if key in seen:
                duplicates.append(key)
            seen[key] = value
        return seen

    stripped = raw.strip()
    try:
        value, end = json.JSONDecoder(object_pairs_hook=pairs).raw_decode(stripped)
    except (json.JSONDecodeError, ValueError):
        return JSON_BAD_JSON, SCHEMA_NOT_EVALUABLE, None
    if end != len(stripped):
        return JSON_EXTRA_DATA, SCHEMA_NOT_EVALUABLE, None
    if duplicates:
        return JSON_DUPLICATE_KEY, SCHEMA_INVALID, "DUPLICATE_KEY"
    if type(value) is not dict:
        return JSON_NOT_OBJECT, SCHEMA_INVALID, "TYPE"
    if _schema_valid(value, schema):
        return JSON_OK, SCHEMA_VALID, None
    return JSON_OK, SCHEMA_INVALID, "CONSTRAINT"


def classify_capability(record: Mapping) -> str:
    if record["status"] == "NOT_RUN":
        return CAP_NOT_RUN
    if record["status"] == "OK":
        return CAP_ACCEPTED
    status = record.get("http_status")
    if isinstance(status, int) and 400 <= status < 500:
        return CAP_REJECTED
    return CAP_TRANSPORT_ERROR


def classify_replicate(generator, reviewer, outcome) -> str:
    """The registered outcome matrix; product pipeline first, schema observation last.

    The product gate is authoritative, so an outside-corpus rejection is
    ``REFERENCE_GATE_FAILURE`` even though the same token is also schema-invalid
    under CORPUS_ENUM; the schema observation is recorded per call and does not
    preempt the product verdict. ``JSON_SCHEMA_FAILURE`` covers a strict-shape
    parse refusal and -- for a future syntax-only arm -- a product-accepted
    candidate the registered schema still rejects.
    """
    call = (generator.record or {}).get("metadata")
    if call is None or call["status"] != "OK":
        return TRANSPORT_FAILURE
    if call["parser_status"] == sc.STAGE_SCHEMA_ERROR:
        if call["parser_error_code"] == al.ALLY_LAB_BAD_JSON:
            return JSON_PARSE_FAILURE
        return JSON_SCHEMA_FAILURE
    if outcome.status == ag.NO_ADVICE:
        return NO_ADVICE_OUTCOME
    if outcome.status == ag.APPROVED:
        return REVIEWER_PASS
    if outcome.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS:
        return REFERENCE_GATE_FAILURE
    if outcome.code == ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS:
        return EVENT_FLOOR_FAILURE
    if outcome.code == ag.ALLY_GEN_REVIEW_REJECTED:
        return REVIEWER_FAIL
    if outcome.code == ag.ALLY_GEN_REVIEW_UNCERTAIN:
        return REVIEWER_UNKNOWN
    if outcome.status == ag.ERROR and reviewer.calls > 0:
        return REVIEWER_ERROR
    if call["parser_status"] == sc.STAGE_OK and call["schema_status"] == SCHEMA_INVALID:
        return JSON_SCHEMA_FAILURE
    return REVIEWER_NOT_REACHED


CALL_SCHEMA = {
    "call_id": ("regex", r"[0-9a-f]{12}"),
    "ordinal": int,
    "category": frozenset({"PROBE", "GENERATION", "REVIEW"}),
    "function": frozenset({"PROBE", "GENERATOR", "REVIEWER"}),
    "purpose": frozenset({"CAPABILITY_PROBE", "GENERATOR_CANDIDATE", "SEMANTIC_REVIEW"}),
    "replicate": frozenset({0, 1, 2}),
    "role": frozenset({"A", "B"}),
    "requested_model": frozenset(ROUTES.values()),
    "reported_model": reach.LABEL_SCHEMA,
    "provider": shape.TEXT_METADATA_SCHEMA,
    "provider_basis": frozenset({"RESPONSE_FIELD", "RESPONSE_HEADER", "NOT_EXPOSED", "OTHER"}),
    "request_max_tokens": frozenset(set(TOKEN_BUDGETS.values())),
    "response_format_kind": frozenset({KIND_NONE, KIND_JSON_SCHEMA}),
    "response_format_sha256": shape.nullable(shape.HASH),
    "request_body_sha256": shape.nullable(shape.HASH),
    "request_body_bytes": shape.nullable(int),
    "prompt_sha256": shape.HASH,
    "sent": bool,
    "returned": bool,
    "wrapper_retry": frozenset({False}),
    "status": frozenset({"OK", "ERROR", "NOT_RUN"}),
    "error_class": shape.nullable(reach.ERRORS),
    "error_body": shape.TEXT_METADATA_SCHEMA,
    "http_status": shape.nullable(int),
    "latency_s": shape.nullable(float),
    "finish_reason": shape.nullable(frozenset({"stop", "length", "content_filter",
                                               "tool_calls", "OTHER"})),
    "output_truncated": shape.nullable(bool),
    "inline_trace_removed": shape.nullable(bool),
    "full_output_sha256": shape.nullable(shape.HASH),
    "full_output_bytes": shape.nullable(int),
    "legacy_projection_would_truncate": shape.nullable(bool),
    "usage": {key: shape.nullable(int) for key in live._KEPT_USAGE},
    "local_estimated_input_tokens": int,
    "parse_shape": shape.nullable(shape.SHAPE_SCHEMA),
    "json_status": frozenset(JSON_STATUSES),
    "schema_status": frozenset(SCHEMA_STATUSES),
    "schema_error": shape.nullable(SCHEMA_REASONS),
    "parser_status": reach.PARSE,
    "parser_error_code": shape.nullable(reach.CODES),
}

PROBE_SCHEMA = {
    "probe_id": frozenset(f"{route}/PROBE" for route in ROUTES),
    "route": frozenset({"A", "B"}),
    "requested_model": frozenset(ROUTES.values()),
    "reported_model": reach.LABEL_SCHEMA,
    "transport_status": frozenset({"OK", "ERROR", "NOT_RUN"}),
    "error_class": shape.nullable(reach.ERRORS),
    "http_status": shape.nullable(int),
    "sent": bool,
    "returned": bool,
    "structured_output_capability": frozenset(CAPABILITIES),
    "provider_claims_json_schema": frozenset({True}),
    "provider_enforces_json_schema": frozenset({ENFORCEMENT_NOT_PROVEN}),
    "parse_result": frozenset(JSON_STATUSES),
    "schema_result": frozenset(SCHEMA_STATUSES),
    "response_format_kind": frozenset({KIND_JSON_SCHEMA}),
    "response_format_sha256": shape.HASH,
    "request_body_sha256": shape.nullable(shape.HASH),
    "request_body_bytes": shape.nullable(int),
    "prompt_sha256": shape.HASH,
    "output_sha256": shape.nullable(shape.HASH),
    "output_bytes": shape.nullable(int),
    "finish_reason": shape.nullable(frozenset({"stop", "length", "content_filter",
                                               "tool_calls", "OTHER"})),
    "ordinal": int,
    "wrapper_retry": frozenset({False}),
}

REVIEW_VERDICT_SCHEMA = {
    "dimension": frozenset(ag.DIMENSIONS),
    "verdict": frozenset(ag.REVIEW_VERDICTS),
    "evidence_refs": ("list", shape.IDENTITY, aa.MAX_EVIDENCE_REFS_PER_ITEM),
}

REPLICATE_SCHEMA = {
    "replicate": frozenset({1, 2}),
    "generator_role": frozenset({"A", "B"}),
    "reviewer_role": frozenset({"A", "B"}),
    "call_id": shape.nullable(("regex", r"[0-9a-f]{12}")),
    "reviewer_call_id": shape.nullable(("regex", r"[0-9a-f]{12}")),
    "outcome": frozenset(ag.OUTCOME_STATUSES),
    "outcome_code": shape.nullable(reach.CODES),
    "outcome_class": frozenset(OUTCOME_CLASSES),
    "reviewer_calls": int,
    "candidate_emitted": bool,
    "candidate_id": shape.nullable(shape.IDENTITY),
    "observed_scope_exact": shape.nullable(bool),
    "observed_item_count": int,
    "counterevidence_item_count": int,
    "observed_event_count": int,
    "outside_ref_count": int,
    "telemetry": shape.nullable(ref.TELEMETRY_SCHEMA),
    "event_floor_relation": frozenset(ref.EVENT_FLOOR_RELATIONS),
    "review_verdicts": ("list", REVIEW_VERDICT_SCHEMA, len(ag.DIMENSIONS)),
    "reviewed_state_minted": bool,
    "same_reported_model_pair": shape.nullable(bool),
    "stages": {name: frozenset(reach.STAGE_VALUES) for name in sc.STAGES},
}

PARTICIPANT_SCHEMA = {
    "role": frozenset({"A", "B"}),
    "requested": frozenset(ROUTES.values()),
    "reported_model": reach.LABEL_SCHEMA,
    "member_status": frozenset({pop.OBSERVED_COMBO_MEMBER, pop.NOT_PROVEN_COMBO_MEMBER}),
    "source": frozenset({"COMBO_ALIAS", "T69_FIXED_ROUTE"}),
    "provider": shape.TEXT_METADATA_SCHEMA,
}

ADMISSION_SCHEMA = {
    "verify_current": frozenset({em.CURRENT_MATCH}),
    "admit_live": frozenset({True}),
    "network_calls": frozenset({0}),
    "granted_before_first_network_call": frozenset({True}),
    "checks": {name: frozenset({True}) for name in ADMISSION_CHECKS},
}

ARTIFACT_SCHEMA = {
    "version": frozenset({VERSION}),
    "registration_id": shape.IDENTITY,
    "registration_file_sha256": shape.HASH,
    "manifest": {
        "file": frozenset({MANIFEST_FILE}),
        "identity": shape.HASH,
        "file_sha256": shape.HASH,
        "authority": frozenset({"LIVE_ELIGIBLE"}),
        "experiment_id": frozenset({MANIFEST_EXPERIMENT_ID}),
    },
    "admission": shape.nullable(ADMISSION_SCHEMA),
    "implementation": {key: shape.HASH for key in (
        "harness_sha256", "observer_sha256", "transport_sha256", "parser_sha256",
        "prompts_sha256", "gates_sha256", "advice_sha256", "manifest_module_sha256",
        "shape_sha256")},
    "started": ("regex", r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"),
    "dry_run": bool,
    "status": frozenset({"COMPLETED", "STOPPED"}),
    "input": {"registration_id": shape.IDENTITY, "build_id": shape.IDENTITY,
              "corpus_id": shape.IDENTITY, "artifact_count": int, "event_count": int,
              "project_scope": frozenset({pilot.B018_PROJECT_SCOPE})},
    "routes": {key: frozenset({value}) for key, value in ROUTES.items()},
    "token_budgets": {"probe": frozenset({TOKEN_BUDGETS["PROBE"]}),
                      "generator": frozenset({TOKEN_BUDGETS["GENERATOR"]}),
                      "reviewer": frozenset({TOKEN_BUDGETS["REVIEWER"]})},
    "response_format": {"probe": frozenset({KIND_JSON_SCHEMA}),
                        "generator": frozenset({KIND_JSON_SCHEMA}),
                        "reviewer": frozenset({"ABSENT"})},
    "schema": {
        "policy": frozenset({POLICY_CORPUS_ENUM}),
        "file": frozenset({SCHEMA_FILE}),
        "sha256": shape.HASH,
        "allowed_evidence_refs": ("list", shape.IDENTITY, ag.MAX_ITEMS),
        "response_format_kind": frozenset({"json_schema"}),
        "enum_constrained": frozenset({True}),
    },
    "call_ceiling": {"max_live_calls": frozenset({MAX_LIVE_CALLS}),
                     "probe_max": frozenset({PROBE_MAX}),
                     "generation_max": frozenset({GENERATION_MAX}),
                     "review_max": frozenset({REVIEW_MAX})},
    "budget": {"spent_total": int, "spent_probe": int, "spent_generation": int,
               "spent_review": int, "logical_dispatches": int,
               "retries": frozenset({0}), "repair_calls": frozenset({0}),
               "replacements": frozenset({0}), "fallbacks": frozenset({0}),
               "network_calls": int},
    "probes": ("list", PROBE_SCHEMA, PROBE_MAX),
    "calls": ("list", CALL_SCHEMA, MAX_LIVE_CALLS),
    "replicates": ("list", REPLICATE_SCHEMA, 2),
    "population": {
        "combo": frozenset({ROUTES["A"]}),
        "projection": frozenset({pilot.POPULATION_PROJECTION_VERSION}),
        "participants": ("list", PARTICIPANT_SCHEMA, 2),
        "participants_ready": bool,
    },
    "privacy": {key: frozenset({False}) for key in (
        "prompt_persisted", "output_persisted", "candidate_prose_persisted",
        "reviewer_rationale_persisted", "error_body_persisted", "full_output_persisted",
        "auth_token_persisted")},
    "side_effects": {key: frozenset({0}) for key in (
        "mail", "seal", "store", "attention", "advice_presentation")},
    "provider_retention": frozenset({"NOT_VERIFIED_BY_SAIMAIL"}),
    "historical_shape": frozenset({"UNKNOWN_BYTES_DISCARDED"}),
    "stop_reason": shape.nullable(frozenset({"AUTH_REFUSED", "GATEWAY_UNREACHABLE", "OTHER"})),
}


def implementation(root=ROOT) -> dict:
    return {
        "harness_sha256": _file_sha256(pathlib.Path(__file__)),
        "observer_sha256": _file_sha256(pathlib.Path(ref.__file__)),
        "transport_sha256": _file_sha256(pathlib.Path(eph.__file__)),
        "parser_sha256": _file_sha256(pathlib.Path(al.__file__)),
        "prompts_sha256": _file_sha256(pathlib.Path(pilot.__file__)),
        "gates_sha256": _file_sha256(pathlib.Path(ag.__file__)),
        "advice_sha256": _file_sha256(pathlib.Path(aa.__file__)),
        "manifest_module_sha256": _file_sha256(pathlib.Path(em.__file__)),
        "shape_sha256": _file_sha256(pathlib.Path(shape.__file__)),
    }


def implementation_rows(root=ROOT) -> list:
    rows = []
    for relative, role in sorted(IMPL_ROLES.items()):
        path = pathlib.Path(root) / relative
        rows.append({"PATH": relative, "SHA256": _file_sha256(path), "ROLE": role})
    return rows


def _scrub(call: dict) -> None:
    for key in ("prompt", "output", "error", "full_output"):
        if key in call:
            call[key] = None


def _is_hex(value) -> bool:
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value))


class SendSchema:
    """One logical call through the existing Runner; durable part is metadata only."""

    def __init__(self, transport, runner: live.Runner, current: dict) -> None:
        self.transport = transport
        self.runner = runner
        self.current = current
        self.calls: list = []

    def __call__(self, prompt: str, model: str | None, *, unit_id: str, replicate: int,
                 role: str, function: str) -> dict:
        self.current["function"] = function
        self.current["max_tokens"] = TOKEN_BUDGETS[function]
        before = self.runner.budget.used
        call = self.runner.call(unit_id, role, prompt, model=model)
        record, raw = self._capture(call, prompt, model, unit_id, replicate, role,
                                    function, before)
        self.calls.append(record)
        return {"call_id": record["call_id"], "status": record["status"],
                "error_class": record["error_class"],
                "http_status": record["http_status"],
                "reported_model": call.get("reported_model"),
                "metadata": record,
                "output": raw}

    def probe(self, route: str) -> dict:
        self.current["function"] = "PROBE"
        self.current["max_tokens"] = TOKEN_BUDGETS["PROBE"]
        before = self.runner.budget.used
        call = self.runner.call("PROBE", route, PROBE_PROMPT, model=ROUTES[route])
        record, _raw = self._capture(call, PROBE_PROMPT, ROUTES[route], "PROBE", 0, route,
                                     "PROBE", before)
        self.calls.append(record)
        return record

    def _capture(self, call: dict, prompt: str, model: str, unit_id: str,
                 replicate: int, role: str, function: str, before: int) -> tuple:
        sent = self.runner.budget.used > before
        raw = None
        try:
            candidate = call.get("full_output")
            if not isinstance(candidate, str):
                candidate = call.get("output")
            raw = candidate if isinstance(candidate, str) else None
            applied = function != "REVIEWER"
            schema = self.current["schema"] if applied else None
            if raw is not None and schema is not None:
                json_status, schema_status, schema_error = schema_check(raw, schema)
            elif function == "REVIEWER":
                json_status, schema_status, schema_error = (
                    schema_check(raw, self.current["schema"])[0], SCHEMA_NOT_EVALUABLE, None)
            else:
                json_status, schema_status, schema_error = (
                    JSON_NOT_TEXT, SCHEMA_NOT_EVALUABLE, None)
            usage = call.get("usage") if type(call.get("usage")) is dict else {}
            provider_basis = call.get("provider_basis")
            basis = ("RESPONSE_HEADER" if type(provider_basis) is str and
                     provider_basis.startswith("RESPONSE_HEADER:") else
                     reach._enum(provider_basis or "NOT_EXPOSED", CALL_SCHEMA["provider_basis"]))
            latency = call.get("latency_s")
            if type(latency) not in (float, int) or not 0 <= latency < 86400:
                latency = None
            record = {
                "call_id": call["call_id"],
                "ordinal": self.runner.budget.used if sent else 0,
                "category": {"PROBE": "PROBE", "GENERATOR": "GENERATION",
                             "REVIEWER": "REVIEW"}[function],
                "function": function,
                "purpose": {"PROBE": "CAPABILITY_PROBE", "GENERATOR": "GENERATOR_CANDIDATE",
                            "REVIEWER": "SEMANTIC_REVIEW"}[function],
                "replicate": replicate,
                "role": role,
                "requested_model": model,
                "reported_model": reach._model(call.get("reported_model")),
                "provider": shape.text_metadata(call.get("provider")),
                "provider_basis": basis,
                "request_max_tokens": TOKEN_BUDGETS[function],
                "response_format_kind": KIND_JSON_SCHEMA if applied else KIND_NONE,
                "response_format_sha256": (
                    self.current["schema_sha256"] if applied else None),
                "request_body_sha256": call.get("request_body_sha256"),
                "request_body_bytes": call.get("request_body_bytes"),
                "prompt_sha256": shape.digest(prompt),
                "sent": sent,
                "returned": sent and call["status"] in ("OK", "ERROR"),
                "wrapper_retry": False,
                "status": call["status"],
                "error_class": (reach._enum(call["error_class"], reach.ERRORS)
                                if call.get("error_class") else None),
                "error_body": shape.text_metadata(call.get("error")),
                "http_status": reach._number(call.get("http_status")),
                "latency_s": latency,
                "finish_reason": (reach._enum(call["finish_reason"],
                                              CALL_SCHEMA["finish_reason"][1])
                                  if call.get("finish_reason") is not None else None),
                "output_truncated": False if raw is not None else None,
                "inline_trace_removed": (call.get("inline_trace_removed")
                                         if type(call.get("inline_trace_removed")) is bool
                                         else None),
                "full_output_sha256": shape.digest(raw) if raw is not None else None,
                "full_output_bytes": (len(raw.encode("utf-8", "surrogatepass"))
                                      if raw is not None else None),
                "legacy_projection_would_truncate": (len(raw) > LEGACY_OUTPUT_CHARS
                                                     if raw is not None else None),
                "usage": {key: reach._number(usage.get(key)) for key in live._KEPT_USAGE},
                "local_estimated_input_tokens": live.estimate_tokens(prompt),
                "parse_shape": (shape.safe_observe(raw, function)
                                if raw is not None and function != "PROBE" else None),
                "json_status": json_status,
                "schema_status": schema_status,
                "schema_error": schema_error,
                "parser_status": sc.STAGE_NOT_ATTEMPTED,
                "parser_error_code": None,
            }
            shape.validate(record, CALL_SCHEMA)
            return record, raw
        finally:
            _scrub(call)

    def finish(self, adapter) -> None:
        if adapter.record is None:
            return
        record = adapter.record.get("metadata")
        if record is None:
            return
        record["parser_status"] = adapter.parse_status
        record["parser_error_code"] = (reach._enum(adapter.last_error, reach.CODES)
                                       if adapter.last_error else None)
        adapter.record["output"] = None


class ObservedGenerator(pilot.PilotGenerator):
    def generate(self, corpus):
        try:
            return super().generate(corpus)
        finally:
            self._finish()

    def _finish(self) -> None:
        if self.record is not None:
            metadata = self.record.get("metadata")
            if metadata is not None:
                metadata["parser_status"] = self.parse_status
                metadata["parser_error_code"] = (
                    reach._enum(self.last_error, reach.CODES) if self.last_error else None)
            self.record["output"] = None


class ObservedReviewer(pilot.PilotReviewer):
    def review(self, evidence_resolved_advice, corpus):
        try:
            return super().review(evidence_resolved_advice, corpus)
        finally:
            if self.record is not None:
                metadata = self.record.get("metadata")
                if metadata is not None:
                    metadata["parser_status"] = self.parse_status
                    metadata["parser_error_code"] = (
                        reach._enum(self.last_error, reach.CODES) if self.last_error else None)
                self.record["output"] = None


def probe_record(record: Mapping, route: str) -> dict:
    return {
        "probe_id": f"{route}/PROBE",
        "route": route,
        "requested_model": record["requested_model"],
        "reported_model": record["reported_model"],
        "transport_status": record["status"],
        "error_class": record["error_class"],
        "http_status": record["http_status"],
        "sent": record["sent"],
        "returned": record["returned"],
        "structured_output_capability": classify_capability(record),
        "provider_claims_json_schema": True,
        "provider_enforces_json_schema": ENFORCEMENT_NOT_PROVEN,
        "parse_result": record["json_status"],
        "schema_result": record["schema_status"],
        "response_format_kind": record["response_format_kind"],
        "response_format_sha256": record["response_format_sha256"],
        "request_body_sha256": record["request_body_sha256"],
        "request_body_bytes": record["request_body_bytes"],
        "prompt_sha256": record["prompt_sha256"],
        "output_sha256": record["full_output_sha256"],
        "output_bytes": record["full_output_bytes"],
        "finish_reason": record["finish_reason"],
        "ordinal": record["ordinal"],
        "wrapper_retry": False,
    }


def execute_replicate(dispatch: SendSchema, corpus: ag.ReflectionCorpus,
                      replicate: int) -> dict:
    gen_role, rev_role = ("A", "B") if replicate == 1 else ("B", "A")
    common = {"unit_id": f"R{replicate}", "replicate": replicate}
    generator = ObservedGenerator(dispatch, role=gen_role, requested=ROUTES[gen_role],
                                  **common)
    reviewer = ObservedReviewer(dispatch, role=rev_role, requested=ROUTES[rev_role],
                                **common)
    try:
        outcome = ag.generate_reviewed_ally_advice(corpus, generator, reviewer)
        candidate = generator.candidate
        telemetry = (ref.observe_candidate_references(candidate, corpus)
                     if candidate is not None else None)
        observed = ({ref_value for item in candidate.observed
                     for ref_value in item.evidence_refs}
                    if candidate is not None else set())
        all_refs = ({ref_value
                     for item in (*candidate.observed, *candidate.counterevidence)
                     for ref_value in item.evidence_refs}
                    if candidate is not None else set())
        gen_model = (generator.record or {}).get("reported_model")
        rev_model = (reviewer.record or {}).get("reported_model")
        generation_call = (generator.record or {}).get("metadata")
        reviewer_call = (reviewer.record or {}).get("metadata")
        result = {
            "replicate": replicate,
            "generator_role": gen_role,
            "reviewer_role": rev_role,
            "call_id": generation_call["call_id"] if generation_call else None,
            "reviewer_call_id": reviewer_call["call_id"] if reviewer_call else None,
            "outcome": outcome.status,
            "outcome_code": outcome.code,
            "outcome_class": classify_replicate(generator, reviewer, outcome),
            "reviewer_calls": reviewer.calls,
            "candidate_emitted": candidate is not None,
            "candidate_id": ag.ally_candidate_id(candidate) if candidate else None,
            "observed_scope_exact": (candidate.observed_scope == pilot.B018_PROJECT_SCOPE
                                     if candidate else None),
            "observed_item_count": len(candidate.observed) if candidate else 0,
            "counterevidence_item_count": (len(candidate.counterevidence)
                                           if candidate else 0),
            "observed_event_count": (len(corpus.event_refs_for(observed))
                                     if candidate else 0),
            "outside_ref_count": len(all_refs - corpus.refs()) if candidate else 0,
            "telemetry": telemetry.to_object() if telemetry else None,
            "event_floor_relation": (telemetry.event_floor_relation if telemetry
                                     else ref.NOT_EVALUABLE),
            "review_verdicts": ([{"dimension": verdict.dimension,
                                  "verdict": verdict.verdict,
                                  "evidence_refs": list(verdict.evidence_refs)}
                                 for verdict in reviewer.report.verdicts]
                                if reviewer.report else []),
            "reviewed_state_minted": outcome.reviewed is not None,
            "same_reported_model_pair": (gen_model == rev_model
                                         if gen_model and rev_model else None),
            "stages": al._stages(generator, reviewer, outcome),
        }
        shape.validate(result, REPLICATE_SCHEMA)
        return result
    finally:
        generator.candidate = None
        reviewer.report = None


def _roundtrip(value) -> object:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _experiment(built, transport, *, schema: Mapping, schema_sha256: str,
                allowed_refs, registration_id: str, registration_file_sha256: str,
                dry_run: bool, started: str, admission: dict | None,
                manifest_block: Mapping) -> dict:
    current = {"function": "PROBE", "max_tokens": TOKEN_BUDGETS["PROBE"],
               "schema": _roundtrip(schema), "schema_sha256": schema_sha256}
    wrapper = schema_response_format(schema)

    def send(prompt: str, model: str | None = None) -> dict:
        response_format = (None if current["function"] == "REVIEWER" else wrapper)
        return transport.send_dispatched(prompt, model=model,
                                         max_tokens=current["max_tokens"],
                                         response_format=response_format)

    budget = live.CallBudget(MAX_LIVE_CALLS)
    runner = live.Runner(send, budget, alias=ROUTES["A"])
    dispatch = SendSchema(transport, runner, current)
    probes = []
    participants = []
    for role, route in ROUTES.items():
        current["function"] = "PROBE"
        current["max_tokens"] = TOKEN_BUDGETS["PROBE"]
        before = budget.used
        call = runner.call("PROBE", role, PROBE_PROMPT, model=route)
        record, _raw = dispatch._capture(call, PROBE_PROMPT, route, "PROBE", 0, role,
                                         "PROBE", before)
        dispatch.calls.append(record)
        probes.append(probe_record(record, role))
        participants.append({
            "role": role,
            "requested": route,
            "reported_model": record["reported_model"],
            "member_status": (pop.OBSERVED_COMBO_MEMBER if role == "A"
                              else pop.NOT_PROVEN_COMBO_MEMBER),
            "source": "COMBO_ALIAS" if role == "A" else "T69_FIXED_ROUTE",
            "provider": record["provider"],
        })
    ready = all(probe["transport_status"] == "OK" for probe in probes)
    replicates = []
    for replicate in (1, 2):
        replicates.append(execute_replicate(dispatch, built.reflection_corpus, replicate))
    spent = {"probe": 0, "generation": 0, "review": 0}
    for record in dispatch.calls:
        if record["sent"]:
            spent["probe" if record["function"] == "PROBE" else
                  "generation" if record["function"] == "GENERATOR" else "review"] += 1
    calls = list(dispatch.calls)
    document = {
        "version": VERSION,
        "registration_id": registration_id,
        "registration_file_sha256": registration_file_sha256,
        "manifest": dict(manifest_block),
        "admission": admission,
        "implementation": implementation(),
        "started": started,
        "dry_run": dry_run,
        "status": "STOPPED" if runner.stopped else "COMPLETED",
        "input": {"registration_id": pilot.B018_REGISTRATION_ID,
                  "build_id": built.build_id, "corpus_id": built.corpus_id,
                  "artifact_count": built.artifact_count, "event_count": built.event_count,
                  "project_scope": built.project_scope},
        "routes": dict(ROUTES),
        "token_budgets": {"probe": TOKEN_BUDGETS["PROBE"],
                          "generator": TOKEN_BUDGETS["GENERATOR"],
                          "reviewer": TOKEN_BUDGETS["REVIEWER"]},
        "response_format": {"probe": KIND_JSON_SCHEMA, "generator": KIND_JSON_SCHEMA,
                            "reviewer": "ABSENT"},
        "schema": {"policy": POLICY_CORPUS_ENUM, "file": SCHEMA_FILE,
                   "sha256": schema_sha256,
                   "allowed_evidence_refs": sorted(set(allowed_refs)),
                   "response_format_kind": "json_schema", "enum_constrained": True},
        "call_ceiling": {"max_live_calls": MAX_LIVE_CALLS, "probe_max": PROBE_MAX,
                         "generation_max": GENERATION_MAX, "review_max": REVIEW_MAX},
        "budget": {"spent_total": budget.used, "spent_probe": spent["probe"],
                   "spent_generation": spent["generation"], "spent_review": spent["review"],
                   "logical_dispatches": sum(1 for record in calls if record["sent"]),
                   "retries": 0, "repair_calls": 0, "replacements": 0, "fallbacks": 0,
                   "network_calls": 0 if dry_run else budget.used},
        "probes": probes,
        "calls": calls,
        "replicates": replicates,
        "population": {"combo": ROUTES["A"],
                       "projection": pilot.POPULATION_PROJECTION_VERSION,
                       "participants": participants, "participants_ready": ready},
        "privacy": {key: False for key in ARTIFACT_SCHEMA["privacy"]},
        "side_effects": {key: 0 for key in ARTIFACT_SCHEMA["side_effects"]},
        "provider_retention": "NOT_VERIFIED_BY_SAIMAIL",
        "historical_shape": "UNKNOWN_BYTES_DISCARDED",
        "stop_reason": ("AUTH_REFUSED" if runner.stopped and
                        runner.stopped.startswith("AUTH_REFUSED") else
                        "GATEWAY_UNREACHABLE" if runner.stopped == "GATEWAY_UNREACHABLE"
                        else "OTHER" if runner.stopped else None),
    }
    shape.validate(document, ARTIFACT_SCHEMA)
    return document


def expected_dry_classes() -> list:
    return [REVIEWER_PASS, NO_ADVICE_OUTCOME]


def render(document: Mapping) -> str:
    shape.validate(document, ARTIFACT_SCHEMA)
    lines = ["# FG-04B JSON_SCHEMA reachability experiment", "",
             f"Registration: `{document['registration_id']}`.",
             (f"Schema policy: `{document['schema']['policy']}`; schema sha256 "
              f"`{document['schema']['sha256']}`."),
             f"Status: `{document['status']}`; dry run: {document['dry_run']}.",
             (f"Exact B-018 corpus: `{document['input']['corpus_id']}`; 8 artifacts / "
              "5 declared events."),
             (f"Token budgets: probe {document['token_budgets']['probe']}, generator "
              f"{document['token_budgets']['generator']}, reviewer "
              f"{document['token_budgets']['reviewer']}; generator/probe response_format "
              "JSON_SCHEMA, reviewer ABSENT."),
             (f"Calls: {document['budget']['spent_total']}/6; probes "
              f"{document['budget']['spent_probe']}, generation "
              f"{document['budget']['spent_generation']}, review "
              f"{document['budget']['spent_review']}; retries 0; repairs 0."),
             ""]
    admission = document["admission"]
    lines.extend(["## ADMISSION", "",
                  ("Admission: not applicable to a dry run." if admission is None else
                   f"verify_current `{admission['verify_current']}`; admit_live "
                   f"`{admission['admit_live']}`; granted before first network call "
                   f"`{admission['granted_before_first_network_call']}`."), ""])
    lines.extend(["## PROBES", ""])
    for probe in document["probes"]:
        lines.append(
            f"- `{probe['probe_id']}` requested `{probe['requested_model']}`; transport "
            f"`{probe['transport_status']}`; capability "
            f"`{probe['structured_output_capability']}`; parse "
            f"`{probe['parse_result']}`; schema `{probe['schema_result']}`; enforcement "
            f"`{probe['provider_enforces_json_schema']}`.")
    lines.append("")
    for row in document["replicates"]:
        lines.extend([f"## R{row['replicate']}", "",
            (f"Generator {row['generator_role']} / reviewer {row['reviewer_role']}: "
             f"`{row['outcome']}` / class `{row['outcome_class']}`."),
            (f"Candidate parsed: {row['candidate_emitted']}; reviewer calls: "
             f"{row['reviewer_calls']}; reviewed state minted: "
             f"{row['reviewed_state_minted']}; event floor "
             f"`{row['event_floor_relation']}`; outside refs {row['outside_ref_count']}."),
            "Stages: " + ", ".join(f"{k}={v}" for k, v in row["stages"].items()) + ".", ""])
    lines.extend(["## REFERENCE_TELEMETRY", ""])
    for row in document["replicates"]:
        telemetry = row["telemetry"]
        if telemetry is None:
            lines.append(f"- R{row['replicate']}: no parsed candidate; telemetry "
                         "NOT_EVALUABLE.")
            continue
        lines.append(
            f"- R{row['replicate']}: relation `{telemetry['corpus_ref_relation']}`; "
            f"known evidence refs {telemetry['known_evidence_ref_count']}; unknown "
            f"canonical {telemetry['unknown_canonical_ref_count']}; malformed "
            f"{telemetry['malformed_ref_count']}; non-text "
            f"{telemetry['non_text_ref_count']}; event refs as evidence "
            f"{telemetry['known_event_ref_as_evidence_count']}; corpus ids as evidence "
            f"{telemetry['corpus_id_as_evidence_count']}; event floor "
            f"`{telemetry['event_floor_relation']}`.")
    lines.extend(["", "## PRODUCT_GATE_AND_REVIEW", ""])
    for row in document["replicates"]:
        verdicts = ", ".join(f"{item['dimension']}={item['verdict']}"
                             for item in row["review_verdicts"]) or "not reached"
        lines.append(f"- R{row['replicate']}: outcome `{row['outcome']}`"
                     + (f" code `{row['outcome_code']}`" if row["outcome_code"] else "")
                     + f"; reviewer verdicts: {verdicts}.")
    lines.extend(["", "## INTERPRETATION LIMITS", "",
        ("Observability is not acceptance. Only the unchanged strict parsers and B-016 "
         "gates decide outcomes."),
        "One sample per role assignment is not a model property; no ranking is made.",
        "A conforming probe sample does not prove that the provider enforces the schema.",
        ("Under CORPUS_ENUM the schema participates in restricting reference vocabulary "
         "before the product reference gate, which remains independently authoritative."),
        ("NO_ADVICE is successful; a reviewer PASS is not truth; corpus completeness "
         "remains NOT_PROVEN."),
        ("No generated advice, prompt, corpus content, reviewer rationale or error body "
         "is persisted or presented."),
        ("No mail, sealing, storage or attention operation is invoked. Provider retention "
         "is NOT_VERIFIED_BY_SAIMAIL."),
        ("This single live attempt is terminal: no retry, repair, replacement or "
         "additional sample."), ""])
    return "\n".join(lines)


def _reserve(path, registration_id: str, dry_sha256=None) -> None:
    payload = json.dumps({"registration_id": registration_id,
                          "implementation": implementation(), "dry_sha256": dry_sha256,
                          "attempt_id": uuid.uuid4().hex, "started": live._now()})
    result = publish_immutable(pathlib.Path(path), (payload + "\n").encode(),
                               conflict_code=JSONSCHEMA_ALREADY_ATTEMPTED)
    if result != PUBLISHED:
        _reject(JSONSCHEMA_ALREADY_ATTEMPTED,
                "the registered live attempt already ran")


def _write(root, doc, document, api_key) -> dict:
    shape.validate(document, ARTIFACT_SCHEMA)
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    report = render(document)
    live.assert_no_secret(text, api_key)
    live.assert_no_secret(report, api_key)
    if document["dry_run"]:
        paths = {"dry": pathlib.Path(root) / doc["artifacts"]["dry"]}
    else:
        stamp = document["started"].replace("-", "").replace(":", "")
        paths = {
            "live": pathlib.Path(root) / doc["artifacts"]["live"].replace("<UTCSTAMP>", stamp),
            "report": pathlib.Path(root) / doc["artifacts"]["report"].replace("<UTCSTAMP>", stamp),
            "analysis": pathlib.Path(root) / doc["artifacts"]["analysis"].replace(
                "<UTCSTAMP>", stamp),
        }
    for key, path in paths.items():
        publish_immutable(path, (text if key in ("dry", "live") else report).encode("utf-8"),
                          conflict_code=JSONSCHEMA_ARTIFACT_EXISTS)
    return {key: str(path) for key, path in paths.items()}


def check_registration(root=ROOT, path=None, *, built=None, schema_bytes=None):
    """Load the stored registration and prove it is exactly the declared plan."""
    target = (pathlib.Path(path) if path is not None
              else pathlib.Path(root) / REGISTRATION_FILE)
    if not target.is_file():
        _reject(JSONSCHEMA_REGISTRATION_MISSING,
                f"{REGISTRATION_FILE} does not exist; the plan is registered before "
                "the first live call")
    try:
        raw = target.read_bytes()
    except OSError as exc:
        _reject(JSONSCHEMA_REGISTRATION_UNREADABLE,
                f"registration cannot be read ({type(exc).__name__})")
    try:
        stored = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        _reject(JSONSCHEMA_REGISTRATION_UNREADABLE,
                "registration must be one strict UTF-8 JSON document")
    if built is None:
        built = pilot.prepare_input(root)
    if schema_bytes is None:
        schema_bytes = (pathlib.Path(root) / SCHEMA_FILE).read_bytes()
    manifest_path = pathlib.Path(root) / MANIFEST_FILE
    manifest = em.load(manifest_path)
    identity = em.manifest_identity(manifest)
    declared = declared_registration(root=root, built=built, schema_bytes=schema_bytes,
                                     manifest_identity=identity)
    if (not isinstance(stored, dict) or not isinstance(stored.get("manifest"), dict)
            or stored["manifest"].get("identity") != identity):
        _reject(JSONSCHEMA_MANIFEST_DRIFT,
                "the manifest identity does not match the registered identity")
    if registration_bytes(declared) != raw:
        _reject(JSONSCHEMA_REGISTRATION_MISMATCH,
                "the plan in code differs from the stored registration; a changed "
                "schema, input, budget, prompt or implementation binding is a new "
                "registration, never an edit")
    return stored, manifest, built, schema_bytes


def declared_registration(*, root=ROOT, built, schema_bytes: bytes,
                          manifest_identity: str) -> dict:
    refs = sorted({item.evidence_ref for item in built.reflection_corpus.items})
    return {
        "registration_version": VERSION,
        "rules": RULES,
        "experiment": EXPERIMENT_NAME,
        "registered_under": {"ticket": "T-81", "source_receipt": "SRC-068"},
        "hypothesis": ("Does enabling JSON_SCHEMA improve the path from generation "
                       "through the reference gate to the independent semantic reviewer "
                       "while all other relevant experimental variables remain frozen?"),
        "single_variable": {
            "change": "generator and probe response_format ABSENT -> JSON_SCHEMA",
            "reviewer_response_format": "ABSENT (unchanged from T-74)",
            "probe_policy": "PROBES_INFORM_DO_NOT_GATE",
            "everything_else_frozen": True,
        },
        "schema_policy": {
            "chosen": POLICY_CORPUS_ENUM,
            "alternative_considered": POLICY_SYNTAX_ONLY,
            "rationale": (
                "T-74 already observed an outside-corpus rejection with no schema; a "
                "syntax-only constraint re-tests the same membership failure without "
                "isolating whether structured output changes the path. Corpus "
                "enumeration makes the reference gate pass diagnostic of schema "
                "non-enforcement rather than of unpinned vocabulary."),
            "expected_diagnostic_distinction": (
                "CORPUS_ENUM: a product reference-gate rejection under an accepted "
                "schema indicates the provider did not enforce the enum. SYNTAX_ONLY: "
                "an unknown canonical ref remains attributable to the model's own "
                "selection and cannot reach the reviewer for a different reason."),
            "schema_participates_before_product_gate": True,
            "product_gate_remains_authoritative": True,
            "no_dynamic_policy_switch": True,
        },
        "json_schema": {
            "file": SCHEMA_FILE,
            "sha256": _digest(schema_bytes),
            "canonical_bytes": "compact JSON, sorted keys, UTF-8, no trailing newline",
            "response_format_kind": "json_schema",
            "wrapper": {"type": "json_schema",
                        "json_schema": {"name": SCHEMA_WRAPPER_NAME, "strict": True}},
            "allowed_evidence_refs": refs,
            "evidence_ref_constraint": "enum" if POLICY_CORPUS_ENUM else "syntax",
            "validator": "BOUNDED_REGISTERED_SCHEMA_VALIDATOR_1",
            "validator_keywords": sorted(_SCHEMA_KEYWORDS),
        },
        "b018_input": {
            "registration_file": pilot.B018_REGISTRATION_FILE,
            "registration_id": pilot.B018_REGISTRATION_ID,
            "build_id": pilot.B018_BUILD_ID,
            "corpus_id": pilot.B018_CORPUS_ID,
            "project_scope": pilot.B018_PROJECT_SCOPE,
            "artifact_count": pilot.B018_ARTIFACT_COUNT,
            "event_count": pilot.B018_EVENT_COUNT,
            "input_identity_gate": pilot.NO_GO_INPUT_DRIFT if hasattr(pilot, "NO_GO_INPUT_DRIFT")
                else "NO_GO_INPUT_DRIFT",
            "rebuild_required": True,
        },
        "routes": dict(ROUTES),
        "roles": {"replicates": 2,
                  "replicate_1": {"generator": "A", "reviewer": "B"},
                  "replicate_2": {"generator": "B", "reviewer": "A"},
                  "third_replicate": False},
        "token_budgets": {"probe_max_tokens": TOKEN_BUDGETS["PROBE"],
                          "generator_max_tokens": TOKEN_BUDGETS["GENERATOR"],
                          "reviewer_max_tokens": TOKEN_BUDGETS["REVIEWER"],
                          "frozen": True},
        "budget": {"max_live_calls": MAX_LIVE_CALLS, "probe_max": PROBE_MAX,
                   "generation_max": GENERATION_MAX, "review_max": REVIEW_MAX,
                   "planned_calls_max": PLANNED_CALLS_MAX, "retries": 0,
                   "repair_calls": 0, "replacements": 0, "fallbacks": 0,
                   "quota": "a ceiling, never a quota"},
        "prompts": {
            "generator_template_sha256": shape.digest(pilot.GENERATOR_TEMPLATE),
            "reviewer_template_sha256": shape.digest(pilot.REVIEWER_TEMPLATE),
            "probe_prompt_sha256": shape.digest(PROBE_PROMPT),
            "semantic_prompt_change": "NONE",
            "temperature": "NOT_SENT",
            "chain_of_thought": "NOT_REQUESTED",
        },
        "full_output_contract": {
            "ephemeral_full_visible_output": True,
            "complete_or_refuse": True,
            "legacy_projection_unchanged": True,
            "legacy_max_output_chars": LEGACY_OUTPUT_CHARS,
        },
        "manifest": {
            "file": MANIFEST_FILE,
            "experiment_id": MANIFEST_EXPERIMENT_ID,
            "authority": "LIVE_ELIGIBLE",
            "identity": manifest_identity,
            "required_before_network": True,
            "operations": ["verify_current", "admit_live"],
            "historical_verification_alone_authorizes": False,
        },
        "outcome_matrix": sorted(OUTCOME_CLASSES),
        "outcome_class_precedence": (
            "PRODUCT_PIPELINE_FIRST: transport, strict parse shape, then the "
            "unchanged product gate outcome decides reference/event/review "
            "classes; the registered schema observation is recorded per call and "
            "classifies only when the product path raised no earlier rejection"),
        "telemetry": {
            "contract": ref.CONTRACT_VERSION,
            "module": "lab/reference_telemetry.py",
            "diagnostic_only": True,
        },
        "privacy": {
            "local_raw_generator_output_persistence": False,
            "local_reviewer_rationale_persistence": False,
            "local_prompt_persistence": False,
            "provider_side_retention": "NOT_VERIFIED_BY_SAIMAIL",
        },
        "replacement_policy": {
            "no_retry": True,
            "no_repair_prompt": True,
            "no_participant_replacement": True,
            "no_rerun_for_bad_content": True,
            "auth": "401/403 stops the remaining live calls",
        },
        "stop_conditions": [
            "registration does not match the declared plan",
            "manifest identity or inputs drifted",
            "admission refused",
            "planned calls exceed the ceiling",
            "corpus, schema, prompts or budgets drifted",
            "credential unavailable",
            "authentication refused during any live phase",
            "consecutive transport failures reach the stop rule",
        ],
        "privacy_notes": "see artifact privacy block; only metadata is durable",
        "attempt_marker": ATTEMPT_MARKER,
        "artifacts": {
            "dry": "lab/out/project_corpus_jsonschema_dry_run.json",
            "live": "lab/out/project_corpus_jsonschema_live_<UTCSTAMP>.json",
            "report": "lab/out/PROJECT_CORPUS_JSONSCHEMA_REPORT_<UTCSTAMP>.md",
            "analysis": "lab/analysis/project_corpus_jsonschema_<UTCSTAMP>.md",
        },
        "frozen_inputs": {
            "json_schema": {"path": SCHEMA_FILE, "sha256": _digest(schema_bytes),
                            "allowed_evidence_refs": refs},
            "b018_registration": {
                "path": "lab/" + pilot.B018_REGISTRATION_FILE,
                "sha256": _file_sha256(
                    pathlib.Path(root) / "lab" / pilot.B018_REGISTRATION_FILE)},
        },
        "frozen_implementation": implementation_rows(root),
    }


def build_manifest(*, root=ROOT, schema_sha256: str) -> dict:
    return {
        "manifest_version": em.MANIFEST_VERSION,
        "experiment_id": MANIFEST_EXPERIMENT_ID,
        "authority": "LIVE_ELIGIBLE",
        "inputs": [
            {
                "INPUT_ID": "REGISTERED_JSON_SCHEMA",
                "SENSITIVITY": "PUBLIC_ARCHIVABLE",
                "SOURCE_KIND": "TEXT_FILE",
                "EXTRACTION_KIND": "WHOLE_FILE",
                "EXTRACTOR_VERSION": "WHOLE-FILE-1",
                "EXTRACTED_SHA256": schema_sha256,
                "REQUIRED_FOR_LIVE": True,
                "SOURCE_PATH": SCHEMA_FILE,
            },
            {
                "INPUT_ID": "B018_CORPUS_REGISTRATION",
                "SENSITIVITY": "PUBLIC_ARCHIVABLE",
                "SOURCE_KIND": "TEXT_FILE",
                "EXTRACTION_KIND": "WHOLE_FILE",
                "EXTRACTOR_VERSION": "WHOLE-FILE-1",
                "EXTRACTED_SHA256": _file_sha256(
                    pathlib.Path(root) / "lab" / pilot.B018_REGISTRATION_FILE),
                "REQUIRED_FOR_LIVE": True,
                "SOURCE_PATH": "lab/" + pilot.B018_REGISTRATION_FILE,
            },
        ],
        "implementation": implementation_rows(root),
    }


def register(root=ROOT) -> dict:
    """Write the schema, manifest and registration once, before any live call."""
    built = pilot.prepare_input(root)
    refs = sorted({item.evidence_ref for item in built.reflection_corpus.items})
    schema_bytes = canonical_bytes(build_schema(refs))
    schema_path = pathlib.Path(root) / SCHEMA_FILE
    publish_immutable(schema_path, schema_bytes, conflict_code=JSONSCHEMA_SCHEMA_EXISTS)
    manifest = build_manifest(root=root, schema_sha256=_digest(schema_bytes))
    em.validate(manifest)
    identity = em.manifest_identity(manifest)
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8")
    publish_immutable(pathlib.Path(root) / MANIFEST_FILE, manifest_bytes,
                      conflict_code=JSONSCHEMA_MANIFEST_EXISTS)
    declared = declared_registration(root=root, built=built, schema_bytes=schema_bytes,
                                     manifest_identity=identity)
    publish_immutable(pathlib.Path(root) / REGISTRATION_FILE,
                      registration_bytes(declared),
                      conflict_code=JSONSCHEMA_REGISTRATION_EXISTS)
    return {"registration": str(pathlib.Path(root) / REGISTRATION_FILE),
            "schema_sha256": _digest(schema_bytes),
            "manifest_identity": identity}


def _budget_check() -> int:
    if PLANNED_CALLS_MAX > MAX_LIVE_CALLS:
        _reject(JSONSCHEMA_DESIGN_BUDGET_INSUFFICIENT,
                f"the registered plan needs up to {PLANNED_CALLS_MAX} calls, over "
                f"the ceiling of {MAX_LIVE_CALLS}")
    return PLANNED_CALLS_MAX


def pre_live_admission(*, root=ROOT, doc: Mapping, built, schema_bytes: bytes,
                       manifest: Mapping) -> dict:
    """Prove every registered identity before the first network call."""
    identity = em.manifest_identity(manifest)
    t71 = em.load(pathlib.Path(root) / "lab/history/t71_manifest.json")
    checks = {
        "manifest_newly_registered": identity != em.manifest_identity(t71),
        "manifest_identity_matches_registration": (
            identity == doc["manifest"]["identity"]),
        "implementation_identity_matches_registration": (
            manifest["implementation"] == doc["frozen_implementation"]),
        "input_identities_match_registration": (
            manifest["inputs"][0]["EXTRACTED_SHA256"] == _digest(schema_bytes)
            and manifest["inputs"][1]["EXTRACTED_SHA256"]
            == doc["frozen_inputs"]["b018_registration"]["sha256"]),
        "current_corpus_matches_frozen_corpus": (
            built.build_id == pilot.B018_BUILD_ID
            and built.corpus_id == pilot.B018_CORPUS_ID
            and built.artifact_count == pilot.B018_ARTIFACT_COUNT
            and built.event_count == pilot.B018_EVENT_COUNT),
        "schema_bytes_match_registration": (
            _digest(schema_bytes) == doc["json_schema"]["sha256"]),
        "allowed_reference_set_matches_registration": (
            sorted({item.evidence_ref for item in built.reflection_corpus.items})
            == sorted(doc["json_schema"]["allowed_evidence_refs"])),
        "budgets_match_registration": (
            TOKEN_BUDGETS["PROBE"] == doc["token_budgets"]["probe_max_tokens"]
            and TOKEN_BUDGETS["GENERATOR"] == doc["token_budgets"]["generator_max_tokens"]
            and TOKEN_BUDGETS["REVIEWER"] == doc["token_budgets"]["reviewer_max_tokens"]),
        "call_ceiling_active": (
            MAX_LIVE_CALLS == doc["budget"]["max_live_calls"]
            and PLANNED_CALLS_MAX <= MAX_LIVE_CALLS),
        "fg04a_telemetry_available": (
            ref.CONTRACT_VERSION == doc["telemetry"]["contract"]
            and callable(getattr(ref, "observe_candidate_references", None))),
        "live_admission_granted_by_admit_live": True,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        _reject(JSONSCHEMA_ADMISSION_REFUSED, f"failed admission check {failed[0]}")
    current = em.verify_current(manifest, root=root)
    if current["verdict"] != em.CURRENT_MATCH:
        _reject(JSONSCHEMA_ADMISSION_REFUSED,
                f"verify_current returned {current['verdict']}")
    try:
        admitted = em.admit_live(manifest, root=root)
    except SailangError as exc:
        _reject(JSONSCHEMA_ADMISSION_REFUSED, f"admit_live refused with {exc.code}")
    if not admitted.get("admitted"):
        _reject(JSONSCHEMA_ADMISSION_REFUSED, "admit_live did not admit")
    return {"verify_current": current["verdict"],
            "admit_live": True,
            "network_calls": 0,
            "granted_before_first_network_call": True,
            "checks": checks}


def run(*, dry_run: bool = False, root=ROOT, registration_path=None) -> dict:
    _budget_check()
    doc, manifest, built, schema_bytes = check_registration(
        root=root, path=registration_path)
    schema_document = json.loads(schema_bytes.decode("utf-8"))
    schema_sha256 = _digest(schema_bytes)
    registration_file_sha256 = _file_sha256(
        pathlib.Path(registration_path) if registration_path is not None
        else pathlib.Path(root) / REGISTRATION_FILE)
    registration_id = "sha256:" + registration_file_sha256
    manifest_block = {
        "file": doc["manifest"]["file"],
        "identity": doc["manifest"]["identity"],
        "file_sha256": _file_sha256(pathlib.Path(root) / doc["manifest"]["file"]),
        "authority": doc["manifest"]["authority"],
        "experiment_id": doc["manifest"]["experiment_id"],
    }
    started = live._now()
    api_key = ""
    if dry_run:
        transport = DryTransport(built.reflection_corpus)
        document = _experiment(built, transport, schema=schema_document,
                               schema_sha256=schema_sha256,
                               allowed_refs=doc["json_schema"]["allowed_evidence_refs"],
                               registration_id=registration_id,
                               registration_file_sha256=registration_file_sha256,
                               dry_run=True, started=started, admission=None,
                               manifest_block=manifest_block)
        if document["budget"]["network_calls"] != 0:
            _reject(JSONSCHEMA_DRY_CONTROL_FAILED, "a dry run made a network call")
        classes = [row["outcome_class"] for row in document["replicates"]]
        if classes != expected_dry_classes():
            _reject(JSONSCHEMA_DRY_CONTROL_FAILED,
                    f"the deterministic dry classes drifted: {classes}")
        paths = _write(root, doc, document, api_key)
    else:
        admission = pre_live_admission(root=root, doc=doc, built=built,
                                       schema_bytes=schema_bytes, manifest=manifest)
        marker = pathlib.Path(root) / doc["attempt_marker"]
        if marker.exists():
            _reject(JSONSCHEMA_ALREADY_ATTEMPTED,
                    "the registered live attempt already ran")
        dry_path = pathlib.Path(root) / doc["artifacts"]["dry"]
        if not dry_path.exists():
            _reject(JSONSCHEMA_DRY_CONTROL_REQUIRED, "run the dry control first")
        proof = json.loads(dry_path.read_text(encoding="utf-8"))
        shape.validate(proof, ARTIFACT_SCHEMA)
        if (not proof["dry_run"] or proof["manifest"]["identity"]
                != doc["manifest"]["identity"]
                or proof["implementation"] != implementation()
                or proof["schema"]["sha256"] != schema_sha256
                or proof["input"]["corpus_id"] != built.corpus_id
                or proof["input"]["build_id"] != built.build_id
                or proof["budget"]["network_calls"] != 0):
            _reject(JSONSCHEMA_DRY_CONTROL_REQUIRED,
                    "the dry proof does not match this registration")
        try:
            credential = resolve()
            api_key = credential.secret
        except (CredentialNotProvisioned, CredentialError):
            _reject(JSONSCHEMA_CREDENTIAL_UNAVAILABLE,
                    "no credential message reaches the console")
        _reserve(marker, registration_id,
                 hashlib.sha256(dry_path.read_bytes()).hexdigest())
        document = _experiment(built, SchemaTransport(api_key),
                               schema=schema_document, schema_sha256=schema_sha256,
                               allowed_refs=doc["json_schema"]["allowed_evidence_refs"],
                               registration_id=registration_id,
                               registration_file_sha256=registration_file_sha256,
                               dry_run=False, started=started, admission=admission,
                               manifest_block=manifest_block)
        paths = _write(root, doc, document, api_key)
    return {"status": document["status"], "dry_run": dry_run,
            "outcome_classes": [row["outcome_class"] for row in document["replicates"]],
            "budget": document["budget"], "artifacts": paths}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--register", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.register:
            result = register(ROOT)
        else:
            result = run(dry_run=args.dry_run, root=ROOT)
    except SailangError as exc:
        print(json.dumps({"status": "REFUSED", "code": exc.code}))
        return 1
    except Exception:  # noqa: BLE001 - exception text must never reach the console
        print(json.dumps({"status": "REFUSED", "code": JSONSCHEMA_HARNESS_ERROR}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
