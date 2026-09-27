"""V2-03: reviewer structured-output bounded experiment (one intentional variable).

    ONE NEW VARIABLE: reviewer response_format ABSENT -> JSON_SCHEMA.
    EVERYTHING ELSE FROZEN, exactly as FG-04B / T-81 registered it.

FG-04B reached the independent semantic reviewer (a first for this research
line) but the reviewer reply was not one parseable strict JSON document
(``ALLY_LAB_BAD_JSON``, 3801 bytes, ``finish_reason=stop``), so semantic review
was never demonstrated.  V2-03 asks one smaller question: holding the already
reached FG-04B path fixed, does adding native structured-output enforcement to
the independent reviewer produce one strict parseable
``SemanticReviewReport``?

The single treatment change from the FG-04B registered configuration is the
reviewer ``response_format``: absent -> one registered ``json_schema`` wrapper
whose schema expresses the *existing* reviewer parser contract as narrowly as
practical.  The generator keeps its FG-04B ``JSON_SCHEMA`` format and its exact
frozen generator schema bytes; corpus, routes, role assignment, prompts, rubric,
token budgets, reference gate, event floor, parser semantics, retry/repair/
replacement policies and the local ephemeral full-output path all stay frozen.

The JSON Schema is NOT a second semantic reviewer.  It constrains the document
*shape*: the four top-level fields, the eight-row array size, the closed
dimension vocabulary, the closed verdict vocabulary and bounded lengths.  It
cannot conveniently express "exactly one row for each of the eight dimensions",
so exact coverage and uniqueness stay the product's business: the existing
``SemanticReviewReport`` constructor remains authoritative for missing,
duplicate and unknown dimensions.  Provider/schema acceptance never replaces
product validation.

Only metadata is durable: identities, hashes, byte lengths, routes, verdicts
and counts.  No prompt text, corpus content, generated prose, reviewer rationale
or provider error body is persisted.  The full ephemeral output exists only
inside one stage and is scrubbed in a ``finally`` block even on a parse failure.

Admission is mechanical and precedes the first network call: the
EXPERIMENT-MANIFEST-1 manifest is loaded, ``verify_current`` and ``admit_live``
are run, the FG-04B registered configuration is re-proved unchanged (the exact
reconstructability gate: a drifted checkout refuses with INPUT_DRIFT) and every
registered identity (manifest, generator schema bytes, reviewer schema template,
allowed refs, implementation, inputs, budgets) is re-proved.  Historical
verification alone never authorizes this run.

    python lab/reviewer_structured_output.py --register
    python lab/reviewer_structured_output.py --dry-run
    python lab/reviewer_structured_output.py --run
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
from lab import project_corpus_jsonschema as js
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
REGISTRATION_FILE = "lab/reviewer_structured_output_registration.json"
REVIEWER_SCHEMA_FILE = "lab/reviewer_structured_output_schema.json"
MANIFEST_FILE = "lab/reviewer_structured_output_manifest.json"
VERSION = "REVIEWER-STRUCTURED-OUTPUT-1"
RULES = "saimail-reviewer-structured-output/1"
EXPERIMENT_NAME = "ALLY_ADVICE REVIEWER STRUCTURED OUTPUT BOUNDED EXPERIMENT"
MANIFEST_EXPERIMENT_ID = "V2-03-REVIEWER-STRUCTURED-OUTPUT-1"

ROUTES = {"A": "SAIFREN", "B": "goat/MiniMaxAI/MiniMax-M3"}
PROBE_PROMPT = js.PROBE_PROMPT

#: The generator keeps the exact FG-04B registered schema file and wrapper name.
GENERATOR_SCHEMA_FILE = js.SCHEMA_FILE
GENERATOR_WRAPPER_NAME = js.SCHEMA_WRAPPER_NAME
#: The reviewer gets a NEW wrapper + schema, whose template is hash-pinned.
REVIEWER_WRAPPER_NAME = "saimail_ally_review_report"
CANDIDATE_ID_PLACEHOLDER = "__CANDIDATE_ID__"
CORPUS_ID_PLACEHOLDER = "__CORPUS_ID__"

KIND_JSON_SCHEMA = "JSON_SCHEMA"
KIND_NONE = "NONE"

TOKEN_BUDGETS = {"PROBE": js.TOKEN_BUDGETS["PROBE"], "GENERATOR": 4096, "REVIEWER": 2048}
MAX_LIVE_CALLS = 6
PROBE_MAX = 2
GENERATION_MAX = 2
REVIEW_MAX = 2
PLANNED_CALLS_MAX = PROBE_MAX + GENERATION_MAX + REVIEW_MAX
LEGACY_OUTPUT_CHARS = live.MAX_OUTPUT_CHARS
ATTEMPT_MARKER = "lab/out/reviewer_structured_output_live_attempt.json"

#: Historical FG-04B comparator identity (T-81), pinned so the treatment
#: difference is mechanically provable.
FG04B_REGISTRATION_ID = (
    "sha256:1e7784bb5efc91531ad23fa91ecafd87dc899a26198b8e5e443590a31fb3f978")
FG04B_MANIFEST_IDENTITY = (
    "70f3cd8c299c8ac22b9da3c7930b5c6d99031151a4a67acc1cd9946e2e8773fa")
FG04B_GENERATOR_SCHEMA_SHA256 = (
    "84304f73399c35f3dc755a1cf19780e4b66ba1a93308c8a81e04d95f8ca285ef")
FG04B_REVIEWER_RESPONSE_FORMAT = "ABSENT"

# ------------------------------------------------------------- terminal outcomes

REVIEWER_VERDICT_PARSED = "REVIEWER_VERDICT_PARSED"
REVIEWER_SCHEMA_ACCEPTED_BUT_PRODUCT_REJECTED = (
    "REVIEWER_SCHEMA_ACCEPTED_BUT_PRODUCT_REJECTED")
REVIEWER_BAD_JSON = "REVIEWER_BAD_JSON"
RESPONSE_FORMAT_REJECTED = "RESPONSE_FORMAT_REJECTED"
REVIEWER_TRANSPORT_ERROR = "REVIEWER_TRANSPORT_ERROR"
REVIEWER_NOT_REACHED = "REVIEWER_NOT_REACHED"
NO_ADVICE_OUTCOME = "NO_ADVICE"
AUTH_REFUSED = "AUTH_REFUSED"
INPUT_DRIFT = "INPUT_DRIFT"

OUTCOME_CLASSES = frozenset({
    REVIEWER_VERDICT_PARSED, REVIEWER_SCHEMA_ACCEPTED_BUT_PRODUCT_REJECTED,
    REVIEWER_BAD_JSON, RESPONSE_FORMAT_REJECTED, REVIEWER_TRANSPORT_ERROR,
    REVIEWER_NOT_REACHED, NO_ADVICE_OUTCOME, AUTH_REFUSED, INPUT_DRIFT})

DRY_CONTROL_NAMES = (
    "A_valid_conforming", "B_extra_top_field", "C_missing_dimension",
    "D_duplicate_dimension", "E_unknown_dimension", "F_invalid_verdict",
    "G_candidate_mismatch", "H_corpus_mismatch", "I_rubric_mismatch",
    "J_malformed_json", "K_format_rejected", "L_no_advice_zero_reviewer")

DRY_CONTROL_SCHEMA = {"control": frozenset(DRY_CONTROL_NAMES), "passed": bool}

JSON_NOT_TEXT = js.JSON_NOT_TEXT
JSON_BAD_JSON = js.JSON_BAD_JSON
JSON_EXTRA_DATA = js.JSON_EXTRA_DATA
JSON_DUPLICATE_KEY = js.JSON_DUPLICATE_KEY
JSON_NOT_OBJECT = js.JSON_NOT_OBJECT
JSON_OK = js.JSON_OK
JSON_STATUSES = js.JSON_STATUSES
SCHEMA_VALID = js.SCHEMA_VALID
SCHEMA_INVALID = js.SCHEMA_INVALID
SCHEMA_NOT_EVALUABLE = js.SCHEMA_NOT_EVALUABLE
SCHEMA_STATUSES = js.SCHEMA_STATUSES
SCHEMA_REASONS = js.SCHEMA_REASONS

CAP_ACCEPTED = js.CAP_ACCEPTED
CAP_REJECTED = js.CAP_REJECTED
CAP_TRANSPORT_ERROR = js.CAP_TRANSPORT_ERROR
CAP_NOT_RUN = js.CAP_NOT_RUN
CAPABILITIES = js.CAPABILITIES
ENFORCEMENT_NOT_PROVEN = js.ENFORCEMENT_NOT_PROVEN

REVIEWER_SCHEMA_PLACEHOLDERS_UNSUBSTITUTED = "REVIEWER_SCHEMA_PLACEHOLDERS_UNSUBSTITUTED"

RSO_REGISTRATION_MISMATCH = "RSO_REGISTRATION_MISMATCH"
RSO_REGISTRATION_MISSING = "RSO_REGISTRATION_MISSING"
RSO_REGISTRATION_UNREADABLE = "RSO_REGISTRATION_UNREADABLE"
RSO_SCHEMA_EXISTS = "RSO_SCHEMA_EXISTS"
RSO_MANIFEST_EXISTS = "RSO_MANIFEST_EXISTS"
RSO_REGISTRATION_EXISTS = "RSO_REGISTRATION_EXISTS"
RSO_MANIFEST_DRIFT = "RSO_MANIFEST_DRIFT"
RSO_ADMISSION_REFUSED = "RSO_ADMISSION_REFUSED"
RSO_INPUT_DRIFT = "RSO_INPUT_DRIFT"
RSO_GENERATOR_SCHEMA_DRIFT = "RSO_GENERATOR_SCHEMA_DRIFT"
RSO_PROMPT_DRIFT = "RSO_PROMPT_DRIFT"
RSO_TOKEN_BUDGET_DRIFT = "RSO_TOKEN_BUDGET_DRIFT"
RSO_CREDENTIAL_UNAVAILABLE = "RSO_CREDENTIAL_UNAVAILABLE"
RSO_ALREADY_ATTEMPTED = "RSO_ALREADY_ATTEMPTED"
RSO_DRY_CONTROL_REQUIRED = "RSO_DRY_CONTROL_REQUIRED"
RSO_DRY_CONTROL_FAILED = "RSO_DRY_CONTROL_FAILED"
RSO_ARTIFACT_EXISTS = "RSO_ARTIFACT_EXISTS"
RSO_VALIDATOR_UNSUPPORTED_KEYWORD = "RSO_VALIDATOR_UNSUPPORTED_KEYWORD"
RSO_HARNESS_ERROR = "RSO_HARNESS_ERROR"

IMPL_ROLES = {
    "lab/ally_generation_live.py": "PARSER",
    "lab/ephemeral_output.py": "EXTRACTOR",
    "lab/experiment_manifest.py": "RUNNER",
    "lab/parse_shape.py": "PARSER",
    "lab/project_corpus_generation_pilot.py": "EXTRACTOR",
    "lab/project_corpus_jsonschema.py": "EXTRACTOR",
    "lab/reference_telemetry.py": "PARSER",
    "lab/reviewer_structured_output.py": "RUNNER",
    "saimail/ally_advice.py": "GRADER",
    "saimail/ally_generation.py": "GRADER",
}

ADMISSION_CHECKS = (
    "manifest_newly_registered",
    "manifest_identity_matches_registration",
    "implementation_identity_matches_registration",
    "input_identities_match_registration",
    "current_corpus_matches_frozen_corpus",
    "generator_schema_bytes_match_fg04b",
    "reviewer_schema_template_matches_registration",
    "allowed_reference_set_matches_registration",
    "fg04b_configuration_reconstructable",
    "budgets_match_registration",
    "call_ceiling_active",
    "live_admission_granted_by_admit_live",
)

_JSON_TYPES = {"object": dict, "array": list, "string": str}
#: The bounded validator supports exactly the keyword set the two registered
#: schemas use.  ``maxLength`` is added for the reviewer rationale bound.
_SCHEMA_KEYWORDS = frozenset({
    "type", "oneOf", "enum", "properties", "required", "additionalProperties",
    "items", "minItems", "maxItems", "uniqueItems", "minLength", "maxLength"})


# ----------------------------------------------------------------- helpers


def _reject(code: str, detail: str = "registered V2-03 boundary refused") -> None:
    raise SailangError(code, detail)


def canonical_bytes(document) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def registration_bytes(document) -> bytes:
    return canonical_bytes(document) + b"\n"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha256(path: pathlib.Path) -> str:
    return _digest(path.read_bytes())


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
        "generator_schema_builder_sha256": _file_sha256(pathlib.Path(js.__file__)),
    }


def implementation_rows(root=ROOT) -> list:
    rows = []
    for relative, role in sorted(IMPL_ROLES.items()):
        path = pathlib.Path(root) / relative
        rows.append({"PATH": relative, "SHA256": _file_sha256(path), "ROLE": role})
    return rows


# ------------------------------------------------------- reviewer schema


def reviewer_schema_template() -> dict:
    """The registered reviewer-document schema; candidate/corpus stay pinned at build."""
    dimension = {
        "type": "object",
        "properties": {
            "dimension": {"type": "string", "enum": list(ag.DIMENSIONS)},
            "verdict": {"type": "string", "enum": list(ag.REVIEW_VERDICTS)},
            "rationale": {"type": "string", "minLength": 1,
                          "maxLength": ag.MAX_RATIONALE_BYTES},
            "evidence_refs": {
                "type": "array",
                "maxItems": aa.MAX_EVIDENCE_REFS_PER_ITEM,
                "uniqueItems": True,
                "items": {"type": "string"},
            },
        },
        "required": ["dimension", "verdict", "rationale", "evidence_refs"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string", "enum": [CANDIDATE_ID_PLACEHOLDER]},
            "corpus_id": {"type": "string", "enum": [CORPUS_ID_PLACEHOLDER]},
            "rubric_version": {"type": "string", "enum": [ag.RUBRIC_VERSION]},
            "dimensions": {"type": "array", "minItems": len(ag.DIMENSIONS),
                           "maxItems": len(ag.DIMENSIONS), "items": dimension},
        },
        "required": ["candidate_id", "corpus_id", "rubric_version", "dimensions"],
        "additionalProperties": False,
    }


def build_reviewer_schema(*, candidate_id: str, corpus_id: str) -> dict:
    """Pin the exact candidate and corpus identities into the registered template."""
    template = reviewer_schema_template()
    template["properties"]["candidate_id"]["enum"] = [candidate_id]
    template["properties"]["corpus_id"]["enum"] = [corpus_id]
    return template


def reviewer_response_format(schema: Mapping) -> dict:
    return {"type": "json_schema",
            "json_schema": {"name": REVIEWER_WRAPPER_NAME, "strict": True,
                            "schema": dict(schema)}}


def is_reviewer_format(response_format) -> bool:
    return (isinstance(response_format, Mapping)
            and isinstance(response_format.get("json_schema"), Mapping)
            and response_format["json_schema"].get("name") == REVIEWER_WRAPPER_NAME)


def is_generator_format(response_format) -> bool:
    return (isinstance(response_format, Mapping)
            and isinstance(response_format.get("json_schema"), Mapping)
            and response_format["json_schema"].get("name") == GENERATOR_WRAPPER_NAME)


def generator_response_format(root=ROOT, schema_bytes: bytes | None = None) -> dict:
    """The exact FG-04B generator response format, rebuilt byte-identically."""
    if schema_bytes is None:
        schema_bytes = (pathlib.Path(root) / GENERATOR_SCHEMA_FILE).read_bytes()
    schema = json.loads(schema_bytes.decode("utf-8"))
    return js.schema_response_format(schema)


def _generator_schema_refs(generator_schema_bytes: bytes) -> list:
    """The exact frozen B-018 evidence-ref enum the FG-04B generator schema carries."""
    schema = json.loads(generator_schema_bytes.decode("utf-8"))
    return sorted(schema["oneOf"][1]["properties"]["OBSERVED"]["items"]["properties"]
                  ["EVIDENCE_REFS"]["items"]["enum"])


def _schema_valid(value, schema) -> bool:
    for keyword in schema:
        if keyword not in _SCHEMA_KEYWORDS:
            _reject(RSO_VALIDATOR_UNSUPPORTED_KEYWORD,
                    f"the registered schema validator does not support {keyword!r}")
    if "oneOf" in schema:
        matches = sum(1 for option in schema["oneOf"] if _schema_valid(value, option))
        return matches == 1
    if "type" in schema:
        expected = _JSON_TYPES.get(schema["type"])
        if expected is None:
            _reject(RSO_VALIDATOR_UNSUPPORTED_KEYWORD,
                    f"the registered schema validator does not support type {schema['type']!r}")
        if type(value) is not expected:
            return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if type(value) is str:
        if "minLength" in schema and len(value) < schema["minLength"]:
            return False
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            return False
    if type(value) is list:
        if "minItems" in schema and len(value) < schema["minItems"]:
            return False
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            return False
        if schema.get("uniqueItems") is True:
            rendered = [json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value]
            if len(set(rendered)) != len(rendered):
                return False
        if "items" in schema:
            for item in value:
                if not _schema_valid(item, schema["items"]):
                    return False
    if type(value) is dict:
        if "additionalProperties" in schema and schema["additionalProperties"] is not False:
            _reject(RSO_VALIDATOR_UNSUPPORTED_KEYWORD,
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
    """Independent JSON and registered-schema observation of one raw output.

    Same strict JSON semantics as the FG-04B observer (duplicate keys, extra
    data and non-object roots are named statuses, never repaired), evaluated
    against this experiment's bounded validator so the reviewer schema's
    ``maxLength`` rationale bound is supported.
    """
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
    return js.classify_capability(record)


# ------------------------------------------------------------ transports


class DryTransport:
    """Deterministic wire outputs through the same dispatch and strict parsers.

    The reviewer request now carries the registered reviewer schema, so the dry
    wire answers by wrapper name rather than by "format absent".
    """

    def __init__(self, corpus: ag.ReflectionCorpus, *,
                 candidate: aa.AllyAdvice | None = None,
                 review_overrides=None, review_rationale: str | None = None) -> None:
        self.corpus = corpus
        self._candidate = candidate or pilot.two_event_candidate(corpus)
        self._review_overrides = dict(review_overrides or {})
        self._review_rationale = review_rationale

    def send_dispatched(self, prompt: str, *, model: str | None = None,
                        max_tokens: int = TOKEN_BUDGETS["PROBE"],
                        response_format: dict | None = None) -> dict:
        if prompt == PROBE_PROMPT:
            output = '{"result":"NO_ADVICE"}'
        elif is_reviewer_format(response_format):
            output = pilot.wire_review_text(
                self._candidate, self.corpus, overrides=self._review_overrides,
                rationale=self._review_rationale)
        elif is_generator_format(response_format):
            output = (pilot.wire_candidate_text(self._candidate)
                      if model == ROUTES["A"] else '{"result":"NO_ADVICE"}')
        elif response_format is None:
            output = pilot.wire_review_text(self._candidate, self.corpus)
        else:
            output = '{"result":"NO_ADVICE"}'
        body = json.dumps({"model": model, "stream": False, "max_tokens": max_tokens,
                           "messages": [{"role": "user", "content": prompt}]})
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
            "request_body_sha256": shape.digest(body),
            "request_body_bytes": len(body.encode("utf-8")),
        }


class SchemaTransport(eph.EphemeralTransport):
    """The ephemeral full-output transport plus one registered response_format.

    One dispatch is one request.  When a format is present the exact outgoing
    body is rewritten once before the single delegation; the body that is
    dispatched is the body that is recorded, so the response_format identity is
    provable from the artifact rather than asserted.
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


# --------------------------------------------------------- classification


def classify_terminal(generator, reviewer, outcome, *, stopped: str | None) -> str:
    """The registered terminal-outcome precedence; product pipeline first.

    ``AUTH_REFUSED`` is checked first because a credential boundary is systemic
    and independent of document semantics.  ``RESPONSE_FORMAT_REJECTED`` is
    distinguished from a generic transport error by an explicit capability 4xx
    status on the reviewer call, and never falls back to an unstructured call.
    """
    gen = (generator.record or {}).get("metadata")
    rev = (reviewer.record or {}).get("metadata")
    if stopped and stopped.startswith("AUTH_REFUSED"):
        return AUTH_REFUSED
    if rev is not None and rev.get("http_status") in (401, 403):
        return AUTH_REFUSED
    if gen is None or gen["status"] != "OK":
        return REVIEWER_NOT_REACHED
    if gen.get("parser_status") == sc.STAGE_SCHEMA_ERROR:
        return REVIEWER_NOT_REACHED
    if outcome.status == ag.NO_ADVICE:
        return NO_ADVICE_OUTCOME
    if outcome.code in (ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS,
                        ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS):
        return REVIEWER_NOT_REACHED
    if rev is None or getattr(reviewer, "calls", 0) == 0:
        return REVIEWER_NOT_REACHED
    if rev["status"] != "OK":
        if isinstance(rev.get("http_status"), int) and 400 <= rev["http_status"] < 500:
            return RESPONSE_FORMAT_REJECTED
        return REVIEWER_TRANSPORT_ERROR
    if rev.get("parser_status") == sc.STAGE_OK:
        if outcome.code == ag.ALLY_GEN_REVIEW_REF_OUTSIDE_CORPUS:
            return REVIEWER_SCHEMA_ACCEPTED_BUT_PRODUCT_REJECTED
        return REVIEWER_VERDICT_PARSED
    if rev.get("parser_error_code") == al.ALLY_LAB_BAD_JSON:
        return REVIEWER_BAD_JSON
    return REVIEWER_SCHEMA_ACCEPTED_BUT_PRODUCT_REJECTED


# ------------------------------------------------------------- dispatch


def _scrub(call: dict) -> None:
    for key in ("prompt", "output", "error", "full_output"):
        if key in call:
            call[key] = None


class SendSchema:
    """One logical call through the existing Runner; durable part is metadata only.

    The reviewer request carries the registered reviewer ``json_schema`` built
    for the exact candidate/corpus pair; the generator and probe keep the frozen
    FG-04B generator schema.  The dispatched body is the recorded body.
    """

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

    def reviewer_format_for(self, candidate: aa.AllyAdvice, corpus: ag.ReflectionCorpus) -> dict:
        schema = build_reviewer_schema(candidate_id=ag.ally_candidate_id(candidate),
                                       corpus_id=corpus.corpus_id)
        return reviewer_response_format(schema)

    def _capture(self, call: dict, prompt: str, model: str, unit_id: str,
                 replicate: int, role: str, function: str, before: int) -> tuple:
        sent = self.runner.budget.used > before
        raw = None
        try:
            candidate = call.get("full_output")
            if not isinstance(candidate, str):
                candidate = call.get("output")
            raw = candidate if isinstance(candidate, str) else None
            if function == "REVIEWER":
                schema = self.current.get("reviewer_schema")
                fmt_kind = KIND_JSON_SCHEMA
                fmt_sha = self.current.get("reviewer_schema_sha256")
            elif function == "GENERATOR":
                schema = self.current.get("generator_schema")
                fmt_kind = KIND_JSON_SCHEMA
                fmt_sha = self.current.get("generator_schema_sha256")
            else:
                schema = self.current.get("generator_schema")
                fmt_kind = KIND_JSON_SCHEMA
                fmt_sha = self.current.get("generator_schema_sha256")
            if raw is not None and schema is not None:
                json_status, schema_status, schema_error = schema_check(raw, schema)
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
                "response_format_kind": fmt_kind if sent else KIND_NONE,
                "response_format_sha256": fmt_sha if sent else None,
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
    def __init__(self, dispatch, **kwargs) -> None:
        super().__init__(dispatch, **kwargs)
        self._schema = None

    def review(self, evidence_resolved_advice, corpus):
        wrapper = self._dispatch.reviewer_format_for(
            evidence_resolved_advice.advice, corpus)
        self._dispatch.current["reviewer_schema"] = wrapper["json_schema"]["schema"]
        self._dispatch.current["reviewer_schema_sha256"] = _digest(
            canonical_bytes(wrapper["json_schema"]["schema"]))
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
    return js.probe_record(record, route)


def execute_replicate(dispatch: SendSchema, corpus: ag.ReflectionCorpus,
                      replicate: int, *, stopped: str | None) -> dict:
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
            "outcome_code": (reach._enum(outcome.code, reach.CODES) if outcome.code
                             else None),
            "outcome_class": classify_terminal(generator, reviewer, outcome,
                                               stopped=stopped),
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


# ------------------------------------------------------------- artifact


def _roundtrip(value) -> object:
    return json.loads(json.dumps(value, ensure_ascii=False))


CALL_SCHEMA = dict(js.CALL_SCHEMA)
CALL_SCHEMA["response_format_kind"] = frozenset({KIND_NONE, KIND_JSON_SCHEMA})

REVIEW_VERDICT_SCHEMA = js.REVIEW_VERDICT_SCHEMA

REPLICATE_SCHEMA = dict(js.REPLICATE_SCHEMA)
REPLICATE_SCHEMA["outcome_class"] = frozenset(OUTCOME_CLASSES)
#: Terminal outcomes prove the reviewer boundary; APPROVED is not required.
REPLICATE_SCHEMA["reviewed_state_minted"] = bool

PROBE_SCHEMA = js.PROBE_SCHEMA

PARTICIPANT_SCHEMA = js.PARTICIPANT_SCHEMA

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
    "historical_comparator": frozenset({FG04B_REGISTRATION_ID}),
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
        "shape_sha256", "generator_schema_builder_sha256")},
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
                        "reviewer": frozenset({KIND_JSON_SCHEMA})},
    "single_variable": {
        "field": frozenset({"reviewer response_format"}),
        "from": frozenset({FG04B_REVIEWER_RESPONSE_FORMAT}),
        "to": frozenset({KIND_JSON_SCHEMA}),
    },
    "generator_schema": {
        "file": frozenset({GENERATOR_SCHEMA_FILE}),
        "sha256": frozenset({FG04B_GENERATOR_SCHEMA_SHA256}),
        "unchanged_from_fg04b": frozenset({True}),
    },
    "reviewer_schema": {
        "file": frozenset({REVIEWER_SCHEMA_FILE}),
        "template_sha256": shape.HASH,
        "wrapper_name": frozenset({REVIEWER_WRAPPER_NAME}),
        "candidate_id_pinned_per_invocation": frozenset({True}),
        "corpus_id_pinned_per_invocation": frozenset({True}),
        "dimension_cardinality_schema_bounded": frozenset({len(ag.DIMENSIONS)}),
        "coverage_and_uniqueness": frozenset({"PRODUCT_VALIDATION"}),
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
    "provider_enforcement": frozenset({ENFORCEMENT_NOT_PROVEN}),
    "historical_shape": frozenset({"UNKNOWN_BYTES_DISCARDED"}),
    "stop_reason": shape.nullable(frozenset({"AUTH_REFUSED", "GATEWAY_UNREACHABLE",
                                             "OTHER"})),
    "dry_controls": shape.nullable(("list", DRY_CONTROL_SCHEMA, len(DRY_CONTROL_NAMES))),
}


def _experiment(built, transport, *, generator_schema: Mapping,
                generator_schema_sha256: str, reviewer_schema_template_sha256: str,
                allowed_refs, registration_id: str, registration_file_sha256: str,
                dry_run: bool, started: str, admission: dict | None,
                manifest_block: Mapping, controls: list | None = None) -> dict:
    current = {"function": "PROBE", "max_tokens": TOKEN_BUDGETS["PROBE"],
               "generator_schema": _roundtrip(generator_schema),
               "generator_schema_sha256": generator_schema_sha256,
               "reviewer_schema": None, "reviewer_schema_sha256": None}
    generator_wrapper = js.schema_response_format(generator_schema)

    def send(prompt: str, model: str | None = None) -> dict:
        if current["function"] == "REVIEWER":
            response_format = current["reviewer_wrapper"]
        else:
            response_format = generator_wrapper
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

    # The reviewer wrapper is built from the exact candidate before each review;
    # this hook lets SendSchema reach it without a second pipeline.
    original_reviewer_format_for = dispatch.reviewer_format_for

    def recording_format_for(candidate, corpus):
        wrapper = original_reviewer_format_for(candidate, corpus)
        current["reviewer_wrapper"] = wrapper
        return wrapper

    dispatch.reviewer_format_for = recording_format_for

    replicates = []
    for replicate in (1, 2):
        replicates.append(execute_replicate(dispatch, built.reflection_corpus, replicate,
                                            stopped=runner.stopped))
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
        "historical_comparator": FG04B_REGISTRATION_ID,
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
                            "reviewer": KIND_JSON_SCHEMA},
        "single_variable": {"field": "reviewer response_format",
                            "from": FG04B_REVIEWER_RESPONSE_FORMAT,
                            "to": KIND_JSON_SCHEMA},
        "generator_schema": {"file": GENERATOR_SCHEMA_FILE,
                             "sha256": generator_schema_sha256,
                             "unchanged_from_fg04b": True},
        "reviewer_schema": {"file": REVIEWER_SCHEMA_FILE,
                            "template_sha256": reviewer_schema_template_sha256,
                            "wrapper_name": REVIEWER_WRAPPER_NAME,
                            "candidate_id_pinned_per_invocation": True,
                            "corpus_id_pinned_per_invocation": True,
                            "dimension_cardinality_schema_bounded": len(ag.DIMENSIONS),
                            "coverage_and_uniqueness": "PRODUCT_VALIDATION"},
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
        "provider_enforcement": ENFORCEMENT_NOT_PROVEN,
        "historical_shape": "UNKNOWN_BYTES_DISCARDED",
        "dry_controls": controls,
        "stop_reason": ("AUTH_REFUSED" if runner.stopped and
                        runner.stopped.startswith("AUTH_REFUSED") else
                        "GATEWAY_UNREACHABLE" if runner.stopped == "GATEWAY_UNREACHABLE"
                        else "OTHER" if runner.stopped else None),
    }
    shape.validate(document, ARTIFACT_SCHEMA)
    return document


# ------------------------------------------------------------- dry controls


def _parse_doc(candidate, corpus, overrides=None, rationale=None) -> str:
    return pilot.wire_review_text(candidate, corpus, overrides=overrides,
                                  rationale=rationale)


def dry_controls(built) -> list:
    """The registered V2-03 dry control matrix (A-L); deterministic, offline."""
    corpus = built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)
    checks = []

    def record(name, passed, _detail):
        checks.append({"control": name, "passed": bool(passed)})

    # A. valid schema-conforming eight-dimension reviewer document
    doc = json.loads(_parse_doc(candidate, corpus))
    schema = build_reviewer_schema(candidate_id=ag.ally_candidate_id(candidate),
                                   corpus_id=corpus.corpus_id)
    json_status, schema_status, _ = schema_check(json.dumps(doc), schema)
    try:
        report = al.parse_reviewer_output(json.dumps(doc), candidate, corpus)
        parsed = isinstance(report, ag.SemanticReviewReport) and len(report.verdicts) == 8
    except SailangError:
        parsed = False
    record("A_valid_conforming", json_status == JSON_OK and schema_status == SCHEMA_VALID
           and parsed, "parser and SemanticReviewReport accept the eight verdicts")

    # B. extra top-level field
    extra = dict(doc, EXTRA="x")
    record("B_extra_top_field", _refused(lambda: al.parse_reviewer_output(
        json.dumps(extra), candidate, corpus)), "extra top-level field is refused")

    # C. missing dimension -> product validation refuses
    missing = dict(doc, dimensions=doc["dimensions"][:7])
    record("C_missing_dimension", _refused(lambda: al.parse_reviewer_output(
        json.dumps(missing), candidate, corpus)), "missing dimension refused")

    # D. duplicate dimension -> product validation refuses
    dup = dict(doc, dimensions=doc["dimensions"][:7] + [doc["dimensions"][0]])
    record("D_duplicate_dimension", _refused(lambda: al.parse_reviewer_output(
        json.dumps(dup), candidate, corpus)), "duplicate dimension refused")

    # E. unknown dimension
    unknown = json.loads(json.dumps(doc))
    unknown["dimensions"][0]["dimension"] = "NOT_A_DIMENSION"
    record("E_unknown_dimension", _refused(lambda: al.parse_reviewer_output(
        json.dumps(unknown), candidate, corpus)), "unknown dimension refused")

    # F. invalid verdict
    invalid = json.loads(json.dumps(doc))
    invalid["dimensions"][0]["verdict"] = "MAYBE"
    record("F_invalid_verdict", _refused(lambda: al.parse_reviewer_output(
        json.dumps(invalid), candidate, corpus)), "invalid verdict refused")

    # G. candidate_id mismatch
    mismatch = dict(doc, candidate_id="sha256:" + "0" * 64)
    record("G_candidate_mismatch", _refused(lambda: al.parse_reviewer_output(
        json.dumps(mismatch), candidate, corpus)), "candidate_id mismatch refused")

    # H. corpus_id mismatch
    mismatch = dict(doc, corpus_id="sha256:" + "0" * 64)
    record("H_corpus_mismatch", _refused(lambda: al.parse_reviewer_output(
        json.dumps(mismatch), candidate, corpus)), "corpus_id mismatch refused")

    # I. rubric_version mismatch
    mismatch = dict(doc, rubric_version="ALLY-REVIEW-2")
    record("I_rubric_mismatch", _refused(lambda: al.parse_reviewer_output(
        json.dumps(mismatch), candidate, corpus)), "rubric_version mismatch refused")

    # J. malformed JSON despite the response-format request
    bad = "not json at all, {dimensions:"
    try:
        al.parse_reviewer_output(bad, candidate, corpus)
        malformed_code = None
    except SailangError as exc:
        malformed_code = exc.code
    record("J_malformed_json", malformed_code == al.ALLY_LAB_BAD_JSON,
           "malformed JSON is a named reviewer parse error")

    # K. provider rejects response_format -> named transport result, no fallback
    gen_call = {"status": "OK", "parser_status": sc.STAGE_OK, "http_status": None}
    rev_call = {"status": "ERROR", "parser_status": sc.STAGE_NOT_ATTEMPTED,
                "http_status": 400, "parser_error_code": None}
    generator = type("G", (), {"record": {"metadata": gen_call}, "calls": 1})()
    reviewer = type("R", (), {"record": {"metadata": rev_call}, "calls": 1})()
    outcome = type("O", (), {"status": ag.ERROR, "code": ag.ALLY_GEN_REVIEWER_ERROR})()
    record("K_format_rejected",
           classify_terminal(generator, reviewer, outcome, stopped=None)
           == RESPONSE_FORMAT_REJECTED,
           "a 4xx reviewer response format is RESPONSE_FORMAT_REJECTED, never a fallback")

    # L. NO_ADVICE generator result -> reviewer zero calls
    gen_call = {"status": "OK", "parser_status": sc.STAGE_OK, "http_status": None}
    generator = type("G", (), {"record": {"metadata": gen_call}, "calls": 1})()
    reviewer = type("R", (), {"record": None, "calls": 0})()
    outcome = type("O", (), {"status": ag.NO_ADVICE, "code": None})()
    record("L_no_advice_zero_reviewer",
           classify_terminal(generator, reviewer, outcome, stopped=None) == NO_ADVICE_OUTCOME,
           "NO_ADVICE spends zero reviewer calls")
    return checks


def _refused(thunk) -> bool:
    try:
        thunk()
    except SailangError:
        return True
    return False


# ------------------------------------------------------------ registration


def declared_registration(*, root=ROOT, built, generator_schema_bytes: bytes,
                          reviewer_template_bytes: bytes,
                          manifest_identity: str) -> dict:
    refs = sorted({item.evidence_ref for item in built.reflection_corpus.items})
    return {
        "registration_version": VERSION,
        "rules": RULES,
        "experiment": EXPERIMENT_NAME,
        "registered_under": {"ticket": "T-96", "source_receipt": "SRC-084"},
        "optional_research_gate": True,
        "historical_comparator": {
            "gate": "FG-04B",
            "ticket": "T-81",
            "registration_id": FG04B_REGISTRATION_ID,
            "manifest_identity": FG04B_MANIFEST_IDENTITY,
            "reviewer_response_format": FG04B_REVIEWER_RESPONSE_FORMAT,
            "outcome": "REVIEWER_ERROR (ALLY_LAB_BAD_JSON, 3801 bytes, finish_reason=stop)",
        },
        "hypothesis": ("Holding the already-reached FG-04B path fixed, does adding native "
                       "structured-output enforcement to the independent reviewer produce "
                       "one strict parseable SemanticReviewReport?"),
        "single_variable": {
            "change": "reviewer response_format ABSENT -> JSON_SCHEMA",
            "generator_response_format": "JSON_SCHEMA",
            "generator_response_format_unchanged_from_fg04b": True,
            "generator_schema": "unchanged (FG-04B bytes)",
            "reviewer_schema": "new, registered below",
            "everything_else_frozen": True,
        },
        "json_schema": {
            "file": REVIEWER_SCHEMA_FILE,
            "template_sha256": _digest(reviewer_template_bytes),
            "canonical_bytes": "compact JSON, sorted keys, UTF-8, no trailing newline",
            "response_format_kind": "json_schema",
            "wrapper": {"type": "json_schema",
                        "json_schema": {"name": REVIEWER_WRAPPER_NAME, "strict": True}},
            "candidate_id_placeholder": CANDIDATE_ID_PLACEHOLDER,
            "corpus_id_placeholder": CORPUS_ID_PLACEHOLDER,
            "candidate_id_pinned_per_invocation": True,
            "corpus_id_pinned_per_invocation": True,
            "rubric_version_enum": [ag.RUBRIC_VERSION],
            "dimension_enum": list(ag.DIMENSIONS),
            "verdict_enum": list(ag.REVIEW_VERDICTS),
            "dimensions_cardinality": len(ag.DIMENSIONS),
            "rationale_max_length": ag.MAX_RATIONALE_BYTES,
            "evidence_refs_max_items": aa.MAX_EVIDENCE_REFS_PER_ITEM,
            "coverage_and_uniqueness": "PRODUCT_VALIDATION",
            "schema_is_not_a_second_semantic_reviewer": True,
            "validator": "BOUNDED_REGISTERED_SCHEMA_VALIDATOR_1",
            "validator_keywords": sorted(_SCHEMA_KEYWORDS),
        },
        "generator_schema": {
            "file": GENERATOR_SCHEMA_FILE,
            "sha256": _digest(generator_schema_bytes),
            "unchanged_from_fg04b": _digest(generator_schema_bytes)
            == FG04B_GENERATOR_SCHEMA_SHA256,
        },
        "b018_input": {
            "registration_file": pilot.B018_REGISTRATION_FILE,
            "registration_id": pilot.B018_REGISTRATION_ID,
            "build_id": pilot.B018_BUILD_ID,
            "corpus_id": pilot.B018_CORPUS_ID,
            "project_scope": pilot.B018_PROJECT_SCOPE,
            "artifact_count": pilot.B018_ARTIFACT_COUNT,
            "event_count": pilot.B018_EVENT_COUNT,
            "input_identity_gate": "NO_GO_INPUT_DRIFT",
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
            "AUTH_REFUSED first; then product pipeline first: transport, strict parse "
            "shape, reference gate, event floor; a reached reviewer call is "
            "REVIEWER_VERDICT_PARSED when the strict parser returned one "
            "SemanticReviewReport, REVIEWER_BAD_JSON when the reply was not one JSON "
            "document, REVIEWER_SCHEMA_ACCEPTED_BUT_PRODUCT_REJECTED when the product "
            "report contract rejected a strict reply, RESPONSE_FORMAT_REJECTED on an "
            "explicit reviewer 4xx capability status, REVIEWER_TRANSPORT_ERROR on "
            "transport failure, REVIEWER_NOT_REACHED when the earlier path stopped"),
        "dry_controls": [
            "A_valid_conforming", "B_extra_top_field", "C_missing_dimension",
            "D_duplicate_dimension", "E_unknown_dimension", "F_invalid_verdict",
            "G_candidate_mismatch", "H_corpus_mismatch", "I_rubric_mismatch",
            "J_malformed_json", "K_format_rejected", "L_no_advice_zero_reviewer"],
        "replacement_policy": {
            "no_retry": True,
            "no_repair_prompt": True,
            "no_participant_replacement": True,
            "no_rerun_for_bad_content": True,
            "no_response_format_fallback": True,
            "auth": "401/403 stops the remaining live calls",
        },
        "stop_conditions": [
            "registration does not match the declared plan",
            "manifest identity or inputs drifted",
            "FG-04B configuration no longer reconstructable (INPUT_DRIFT)",
            "admission refused",
            "planned calls exceed the ceiling",
            "corpus, generator schema, reviewer schema, prompts or budgets drifted",
            "credential unavailable",
            "authentication refused during any live phase",
            "consecutive transport failures reach the stop rule",
        ],
        "privacy": {
            "local_raw_generator_output_persistence": False,
            "local_reviewer_rationale_persistence": False,
            "local_prompt_persistence": False,
            "provider_side_retention": "NOT_VERIFIED_BY_SAIMAIL",
        },
        "claim_boundary": (
            "one registered reviewer invocation produced one parseable product-valid "
            "semantic review document under the registered JSON_SCHEMA request; this "
            "proves output-format reachability in one sample, not reviewer reliability, "
            "semantic correctness, provider enforcement in general or production "
            "readiness"),
        "attempt_marker": ATTEMPT_MARKER,
        "artifacts": {
            "dry": "lab/out/reviewer_structured_output_dry_run.json",
            "live": "lab/out/reviewer_structured_output_live_<UTCSTAMP>.json",
            "report": "lab/out/REVIEWER_STRUCTURED_OUTPUT_REPORT_<UTCSTAMP>.md",
            "analysis": "lab/analysis/reviewer_structured_output_<UTCSTAMP>.md",
        },
        "frozen_inputs": {
            "reviewer_schema": {"path": REVIEWER_SCHEMA_FILE,
                                "sha256": _digest(reviewer_template_bytes),
                                "candidate_id_placeholder": CANDIDATE_ID_PLACEHOLDER},
            "generator_schema": {"path": GENERATOR_SCHEMA_FILE,
                                 "sha256": _digest(generator_schema_bytes)},
            "b018_registration": {
                "path": "lab/" + pilot.B018_REGISTRATION_FILE,
                "sha256": _file_sha256(
                    pathlib.Path(root) / "lab" / pilot.B018_REGISTRATION_FILE)},
        },
        "frozen_implementation": implementation_rows(root),
    }


def build_manifest(*, root=ROOT, reviewer_template_sha256: str,
                   generator_schema_sha256: str) -> dict:
    return {
        "manifest_version": em.MANIFEST_VERSION,
        "experiment_id": MANIFEST_EXPERIMENT_ID,
        "authority": "LIVE_ELIGIBLE",
        "inputs": [
            {
                "INPUT_ID": "REGISTERED_REVIEWER_SCHEMA",
                "SENSITIVITY": "PUBLIC_ARCHIVABLE",
                "SOURCE_KIND": "TEXT_FILE",
                "EXTRACTION_KIND": "WHOLE_FILE",
                "EXTRACTOR_VERSION": "WHOLE-FILE-1",
                "EXTRACTED_SHA256": reviewer_template_sha256,
                "REQUIRED_FOR_LIVE": True,
                "SOURCE_PATH": REVIEWER_SCHEMA_FILE,
            },
            {
                "INPUT_ID": "REGISTERED_GENERATOR_SCHEMA",
                "SENSITIVITY": "PUBLIC_ARCHIVABLE",
                "SOURCE_KIND": "TEXT_FILE",
                "EXTRACTION_KIND": "WHOLE_FILE",
                "EXTRACTOR_VERSION": "WHOLE-FILE-1",
                "EXTRACTED_SHA256": generator_schema_sha256,
                "REQUIRED_FOR_LIVE": True,
                "SOURCE_PATH": GENERATOR_SCHEMA_FILE,
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


def check_registration(root=ROOT, path=None, *, built=None,
                       generator_schema_bytes=None, reviewer_template_bytes=None):
    target = (pathlib.Path(path) if path is not None
              else pathlib.Path(root) / REGISTRATION_FILE)
    if not target.is_file():
        _reject(RSO_REGISTRATION_MISSING,
                f"{REGISTRATION_FILE} does not exist; the plan is registered before "
                "the first live call")
    try:
        raw = target.read_bytes()
    except OSError as exc:
        _reject(RSO_REGISTRATION_UNREADABLE,
                f"registration cannot be read ({type(exc).__name__})")
    try:
        stored = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        _reject(RSO_REGISTRATION_UNREADABLE,
                "registration must be one strict UTF-8 JSON document")
    if built is None:
        built = pilot.prepare_input(root)
    if generator_schema_bytes is None:
        generator_schema_bytes = (pathlib.Path(root) / GENERATOR_SCHEMA_FILE).read_bytes()
    if reviewer_template_bytes is None:
        reviewer_template_bytes = (pathlib.Path(root) / REVIEWER_SCHEMA_FILE).read_bytes()
    manifest = em.load(pathlib.Path(root) / MANIFEST_FILE)
    identity = em.manifest_identity(manifest)
    declared = declared_registration(root=root, built=built,
                                     generator_schema_bytes=generator_schema_bytes,
                                     reviewer_template_bytes=reviewer_template_bytes,
                                     manifest_identity=identity)
    if (not isinstance(stored, dict) or not isinstance(stored.get("manifest"), dict)
            or stored["manifest"].get("identity") != identity):
        _reject(RSO_MANIFEST_DRIFT,
                "the manifest identity does not match the registered identity")
    if registration_bytes(declared) != raw:
        _reject(RSO_REGISTRATION_MISMATCH,
                "the plan in code differs from the stored registration; a changed "
                "schema, input, budget, prompt or implementation binding is a new "
                "registration, never an edit")
    return stored, manifest, built, generator_schema_bytes, reviewer_template_bytes


def register(root=ROOT) -> dict:
    built = pilot.prepare_input(root)
    generator_schema_bytes = (pathlib.Path(root) / GENERATOR_SCHEMA_FILE).read_bytes()
    if _digest(generator_schema_bytes) != FG04B_GENERATOR_SCHEMA_SHA256:
        _reject(RSO_GENERATOR_SCHEMA_DRIFT,
                "the FG-04B generator schema bytes drifted from the frozen hash")
    reviewer_template_bytes = canonical_bytes(reviewer_schema_template())
    publish_immutable(pathlib.Path(root) / REVIEWER_SCHEMA_FILE, reviewer_template_bytes,
                      conflict_code=RSO_SCHEMA_EXISTS)
    manifest = build_manifest(root=root,
                              reviewer_template_sha256=_digest(reviewer_template_bytes),
                              generator_schema_sha256=_digest(generator_schema_bytes))
    em.validate(manifest)
    identity = em.manifest_identity(manifest)
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8")
    publish_immutable(pathlib.Path(root) / MANIFEST_FILE, manifest_bytes,
                      conflict_code=RSO_MANIFEST_EXISTS)
    declared = declared_registration(root=root, built=built,
                                     generator_schema_bytes=generator_schema_bytes,
                                     reviewer_template_bytes=reviewer_template_bytes,
                                     manifest_identity=identity)
    publish_immutable(pathlib.Path(root) / REGISTRATION_FILE,
                      registration_bytes(declared),
                      conflict_code=RSO_REGISTRATION_EXISTS)
    return {"registration": str(pathlib.Path(root) / REGISTRATION_FILE),
            "reviewer_schema_sha256": _digest(reviewer_template_bytes),
            "generator_schema_sha256": _digest(generator_schema_bytes),
            "manifest_identity": identity}


def _budget_check() -> int:
    if PLANNED_CALLS_MAX > MAX_LIVE_CALLS:
        _reject(js.JSONSCHEMA_DESIGN_BUDGET_INSUFFICIENT,
                f"the registered plan needs up to {PLANNED_CALLS_MAX} calls, over "
                f"the ceiling of {MAX_LIVE_CALLS}")
    return PLANNED_CALLS_MAX


def _fg04b_reconstructable(root=ROOT) -> bool:
    """The exact FG-04B registered configuration must still be reconstructable."""
    try:
        js.check_registration(root=root)
    except SailangError:
        return False
    return True


def pre_live_admission(*, root=ROOT, doc: Mapping, built, generator_schema_bytes: bytes,
                       reviewer_template_bytes: bytes, manifest: Mapping) -> dict:
    identity = em.manifest_identity(manifest)
    t71 = em.load(pathlib.Path(root) / "lab/history/t71_manifest.json")
    refs = sorted({item.evidence_ref for item in built.reflection_corpus.items})
    checks = {
        "manifest_newly_registered": identity != em.manifest_identity(t71),
        "manifest_identity_matches_registration": identity == doc["manifest"]["identity"],
        "implementation_identity_matches_registration": (
            manifest["implementation"] == doc["frozen_implementation"]),
        "input_identities_match_registration": (
            manifest["inputs"][0]["EXTRACTED_SHA256"] == _digest(reviewer_template_bytes)
            and manifest["inputs"][1]["EXTRACTED_SHA256"] == _digest(generator_schema_bytes)
            and manifest["inputs"][2]["EXTRACTED_SHA256"]
            == doc["frozen_inputs"]["b018_registration"]["sha256"]),
        "current_corpus_matches_frozen_corpus": (
            built.build_id == pilot.B018_BUILD_ID
            and built.corpus_id == pilot.B018_CORPUS_ID
            and built.artifact_count == pilot.B018_ARTIFACT_COUNT
            and built.event_count == pilot.B018_EVENT_COUNT),
        "generator_schema_bytes_match_fg04b": (
            _digest(generator_schema_bytes) == FG04B_GENERATOR_SCHEMA_SHA256),
        "reviewer_schema_template_matches_registration": (
            _digest(reviewer_template_bytes) == doc["json_schema"]["template_sha256"]),
        "allowed_reference_set_matches_registration": (
            refs == _generator_schema_refs(generator_schema_bytes)),
        "fg04b_configuration_reconstructable": _fg04b_reconstructable(root),
        "budgets_match_registration": (
            TOKEN_BUDGETS["PROBE"] == doc["token_budgets"]["probe_max_tokens"]
            and TOKEN_BUDGETS["GENERATOR"] == doc["token_budgets"]["generator_max_tokens"]
            and TOKEN_BUDGETS["REVIEWER"] == doc["token_budgets"]["reviewer_max_tokens"]),
        "call_ceiling_active": (
            MAX_LIVE_CALLS == doc["budget"]["max_live_calls"]
            and PLANNED_CALLS_MAX <= MAX_LIVE_CALLS),
        "live_admission_granted_by_admit_live": True,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        _reject(RSO_ADMISSION_REFUSED, f"failed admission check {failed[0]}")
    if not checks["fg04b_configuration_reconstructable"]:
        _reject(RSO_INPUT_DRIFT,
                "the FG-04B registered configuration is no longer reconstructable")
    current = em.verify_current(manifest, root=root)
    if current["verdict"] != em.CURRENT_MATCH:
        _reject(RSO_ADMISSION_REFUSED,
                f"verify_current returned {current['verdict']}")
    try:
        admitted = em.admit_live(manifest, root=root)
    except SailangError as exc:
        _reject(RSO_ADMISSION_REFUSED, f"admit_live refused with {exc.code}")
    if not admitted.get("admitted"):
        _reject(RSO_ADMISSION_REFUSED, "admit_live did not admit")
    return {"verify_current": current["verdict"],
            "admit_live": True,
            "network_calls": 0,
            "granted_before_first_network_call": True,
            "checks": checks}


# --------------------------------------------------------------- run


def _dry_expected_classes() -> list:
    return [REVIEWER_VERDICT_PARSED, NO_ADVICE_OUTCOME]


def run(*, dry_run: bool = False, root=ROOT, registration_path=None,
        transport=None) -> dict:
    _budget_check()
    doc, manifest, built, generator_schema_bytes, reviewer_template_bytes = (
        check_registration(root=root, path=registration_path))
    generator_schema = json.loads(generator_schema_bytes.decode("utf-8"))
    generator_schema_sha256 = _digest(generator_schema_bytes)
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
        controls = dry_controls(built)
        failed = [row["control"] for row in controls if not row["passed"]]
        if failed:
            _reject(RSO_DRY_CONTROL_FAILED, f"dry control failed: {failed[0]}")
        document = _experiment(built, DryTransport(built.reflection_corpus),
                               generator_schema=generator_schema,
                               generator_schema_sha256=generator_schema_sha256,
                               reviewer_schema_template_sha256=_digest(
                                   reviewer_template_bytes),
                               allowed_refs=_generator_schema_refs(generator_schema_bytes),
                               registration_id=registration_id,
                               registration_file_sha256=registration_file_sha256,
                               dry_run=True, started=started, admission=None,
                               manifest_block=manifest_block, controls=controls)
        if document["budget"]["network_calls"] != 0:
            _reject(RSO_DRY_CONTROL_FAILED, "a dry run made a network call")
        classes = [row["outcome_class"] for row in document["replicates"]]
        if classes != _dry_expected_classes():
            _reject(RSO_DRY_CONTROL_FAILED,
                    f"the deterministic dry classes drifted: {classes}")
        paths = _write(root, doc, document, api_key)
    else:
        admission = pre_live_admission(root=root, doc=doc, built=built,
                                       generator_schema_bytes=generator_schema_bytes,
                                       reviewer_template_bytes=reviewer_template_bytes,
                                       manifest=manifest)
        marker = pathlib.Path(root) / doc["attempt_marker"]
        if marker.exists():
            _reject(RSO_ALREADY_ATTEMPTED, "the registered live attempt already ran")
        dry_path = pathlib.Path(root) / doc["artifacts"]["dry"]
        if not dry_path.exists():
            _reject(RSO_DRY_CONTROL_REQUIRED, "run the dry control first")
        proof = json.loads(dry_path.read_text(encoding="utf-8"))
        shape.validate(proof, ARTIFACT_SCHEMA)
        if (not proof["dry_run"] or proof["manifest"]["identity"]
                != doc["manifest"]["identity"]
                or proof["implementation"] != implementation()
                or proof["reviewer_schema"]["template_sha256"]
                != _digest(reviewer_template_bytes)
                or proof["input"]["corpus_id"] != built.corpus_id
                or proof["input"]["build_id"] != built.build_id
                or proof["budget"]["network_calls"] != 0):
            _reject(RSO_DRY_CONTROL_REQUIRED,
                    "the dry proof does not match this registration")
        try:
            credential = resolve()
            api_key = credential.secret
        except (CredentialNotProvisioned, CredentialError):
            _reject(RSO_CREDENTIAL_UNAVAILABLE, "no credential message reaches the console")
        _reserve(marker, registration_id,
                 hashlib.sha256(dry_path.read_bytes()).hexdigest())
        live_transport = transport or SchemaTransport(api_key)
        document = _experiment(built, live_transport,
                               generator_schema=generator_schema,
                               generator_schema_sha256=generator_schema_sha256,
                               reviewer_schema_template_sha256=_digest(
                                   reviewer_template_bytes),
                               allowed_refs=_generator_schema_refs(generator_schema_bytes),
                               registration_id=registration_id,
                               registration_file_sha256=registration_file_sha256,
                               dry_run=False, started=started, admission=admission,
                               manifest_block=manifest_block)
        paths = _write(root, doc, document, api_key)
    return {"status": document["status"], "dry_run": dry_run,
            "outcome_classes": [row["outcome_class"] for row in document["replicates"]],
            "budget": document["budget"], "artifacts": paths}


def _reserve(path, registration_id: str, dry_sha256=None) -> None:
    payload = json.dumps({"registration_id": registration_id,
                          "implementation": implementation(), "dry_sha256": dry_sha256,
                          "attempt_id": uuid.uuid4().hex, "started": live._now()})
    result = publish_immutable(pathlib.Path(path), (payload + "\n").encode(),
                               conflict_code=RSO_ALREADY_ATTEMPTED)
    if result != PUBLISHED:
        _reject(RSO_ALREADY_ATTEMPTED, "the registered live attempt already ran")


def render(document: Mapping) -> str:
    shape.validate(document, ARTIFACT_SCHEMA)
    lines = ["# V2-03 reviewer structured-output experiment", "",
             f"Registration: `{document['registration_id']}`.",
             (f"Single variable: `{document['single_variable']['field']}` "
              f"{document['single_variable']['from']} -> {document['single_variable']['to']}."),
             (f"Generator response format: `{document['response_format']['generator']}` "
              f"(unchanged); reviewer response format: "
              f"`{document['response_format']['reviewer']}`."),
             (f"Reviewer schema template sha256 `{document['reviewer_schema']['template_sha256']}`; "
              f"wrapper `{document['reviewer_schema']['wrapper_name']}`."),
             f"Status: `{document['status']}`; dry run: {document['dry_run']}.",
             (f"Token budgets: probe {document['token_budgets']['probe']}, generator "
              f"{document['token_budgets']['generator']}, reviewer "
              f"{document['token_budgets']['reviewer']}."),
             (f"Calls: {document['budget']['spent_total']}/6; probes "
              f"{document['budget']['spent_probe']}, generation "
              f"{document['budget']['spent_generation']}, review "
              f"{document['budget']['spent_review']}; retries 0; repairs 0."), ""]
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
    lines.extend(["## REVIEWER_VERDICTS", ""])
    for row in document["replicates"]:
        verdicts = ", ".join(f"{item['dimension']}={item['verdict']}"
                             for item in row["review_verdicts"]) or "not reached"
        lines.append(f"- R{row['replicate']}: outcome `{row['outcome']}`"
                     + (f" code `{row['outcome_code']}`" if row["outcome_code"] else "")
                     + f"; reviewer verdicts: {verdicts}.")
    if document.get("dry_controls") is not None:
        lines.extend(["", "## DRY_CONTROLS", ""])
        for row in document["dry_controls"]:
            lines.append(f"- `{row['control']}`: "
                         f"{'PASS' if row['passed'] else 'FAIL'}")
    lines.extend(["", "## INTERPRETATION LIMITS", "",
        ("Observability is not acceptance. Only the unchanged strict parsers and B-016 "
         "gates decide outcomes."),
        ("Provider/schema acceptance never replaces product validation; the existing "
         "SemanticReviewReport remains authoritative for coverage and uniqueness."),
        ("A conforming probe sample does not prove that the provider enforces the schema; "
         "provider enforcement remains NOT_PROVEN."),
        ("REQUEST SENT WITH SCHEMA != PROVIDER ENFORCED SCHEMA."),
        "One sample per role assignment is not a model property; no ranking is made.",
        ("A parseable FAIL or UNKNOWN report still proves output-format reachability; "
         "PARSEABLE REVIEW != APPROVED ADVICE."),
        ("NO_ADVICE is successful; a reviewer PASS is not truth; corpus completeness "
         "remains NOT_PROVEN."),
        ("No generated advice, prompt, corpus content, reviewer rationale or error body "
         "is persisted or presented."),
        ("No mail, sealing, storage or attention operation is invoked. Provider retention "
         "is NOT_VERIFIED_BY_SAIMAIL."),
        ("This single live attempt is terminal: no retry, repair, replacement or "
         "response-format fallback."), ""])
    return "\n".join(lines)


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
                          conflict_code=RSO_ARTIFACT_EXISTS)
    return {key: str(path) for key, path in paths.items()}


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
        print(json.dumps({"status": "REFUSED", "code": RSO_HARNESS_ERROR}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
