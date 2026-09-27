"""LAB-only structured-output / completion-budget capability gate (T-73).

    CAPABILITY_PROBE != PRODUCT_SEMANTICS
    OBSERVABILITY != ACCEPTANCE

Six synthetic probes, two frozen routes, one immutable registration, and one
live attempt: this module measures whether the current gateway accepts a 4096
completion budget under a context-shaped synthetic request and whether it
accepts OpenAI-compatible ``json_object`` / ``json_schema`` response formats.
It changes no production code, weakens no parser, transmits no real corpus and
performs no retry, repair, replacement or fallback.

Deliberate conservatism, frozen in the registration:

* one conforming response proves only that THIS registered request was accepted
  and that THIS output conformed -- ``native_enforcement_proven`` stays ``false``;
* the local transport keeps its 4000-character parser-input projection,
  so a future arbitrary 4096-token generation is NOT declared safe through the
  unchanged local path (``real_4096_run_safe_with_current_local_output_path``
  stays ``false``);
* the strict parser in ``lab/ally_generation_live.py`` is not touched; these
  tiny probes use their own exact object check.

    python lab/structured_output_capability.py --dry-run
    python lab/structured_output_capability.py --run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lab import parse_shape as shape
from lab import saifren_run as live
from sailang.errors import SailangError
from saimail.credentials import (
    CredentialError,
    CredentialNotProvisioned,
    resolve,
)
from saimail.publish import PUBLISHED, publish_immutable

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRATION_PATH = ROOT / "lab/structured_output_capability_registration.json"
REGISTRATION_SHA256 = "e696db4c786ea60b9764b50e924fd93ed505efdf1b8b366529600ac100c4ffdf"
VERSION = "STRUCTURED-OUTPUT-CAPABILITY-1"

ROUTES = {"A": "SAIFREN", "B": "goat/MiniMaxAI/MiniMax-M3"}
PROBE_ORDER = (("A", "BUDGET_4096"), ("B", "BUDGET_4096"),
               ("A", "JSON_OBJECT"), ("B", "JSON_OBJECT"),
               ("A", "JSON_SCHEMA"), ("B", "JSON_SCHEMA"))

KIND_NONE = "NONE"
KIND_JSON_OBJECT = "JSON_OBJECT"
KIND_JSON_SCHEMA = "JSON_SCHEMA"

RESULT_ACCEPTED_CONFORMING = "REQUEST_ACCEPTED_CONFORMING"
RESULT_ACCEPTED_NONCONFORMING = "REQUEST_ACCEPTED_NONCONFORMING"
RESULT_REJECTED = "REQUEST_REJECTED"
RESULT_TRANSPORT_ERROR = "TRANSPORT_ERROR"
RESULT_AUTH_REFUSED = "AUTH_REFUSED"
RESULT_NOT_RUN = "NOT_RUN"
RESULT_VOCABULARY = frozenset({
    RESULT_ACCEPTED_CONFORMING, RESULT_ACCEPTED_NONCONFORMING, RESULT_REJECTED,
    RESULT_TRANSPORT_ERROR, RESULT_AUTH_REFUSED, RESULT_NOT_RUN})

ERROR_CLASSES = frozenset({
    "OTHER", "HTTPError", "EmptyOutput", "TimeoutError", "URLError", "ConnectionError",
    "OSError", "BudgetExceeded", "HARNESS_ERROR", "MalformedResponse", "ResponseTooLarge",
    "GatewayError"})

MATRIX_LABELS = {"BUDGET_4096": "4096", "JSON_OBJECT": "json_object",
                 "JSON_SCHEMA": "json_schema"}

#: History from T-71, per requested route. Descriptive comparison only.
HISTORICAL_GATEWAY_PROMPT_TOKENS = {"A": 12065, "B": 10973}
COMPARABLE_LOW = 0.85
COMPARABLE_HIGH = 1.15
BAND_COMPARABLE = "CONTEXT_SHAPE_COMPARABLE"
BAND_NOT_COMPARABLE = "CONTEXT_SHAPE_NOT_COMPARABLE"
BAND_UNAVAILABLE = "NOT_AVAILABLE"

LOCAL_VISIBLE_OUTPUT_CAP_CHARS = live.MAX_OUTPUT_CHARS
REAL_4096_RUN_SAFE_WITH_CURRENT_LOCAL_OUTPUT_PATH = False
NATIVE_ENFORCEMENT_PROVEN = False

TINY_PROMPT = 'Reply with exactly one JSON object and nothing else: {"probe":"OK"}'

JSON_OBJECT_FORMAT = {"type": "json_object"}
JSON_SCHEMA_FORMAT = {
    "type": "json_schema",
    "json_schema": {
        "name": "saimail_capability_probe",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {"probe": {"type": "string", "enum": ["OK"]}},
            "required": ["probe"],
            "additionalProperties": False,
        },
    },
}

SYNTHETIC_HEADER = "SYNTHETIC OPERATIONAL CONTEXT -- NO PROJECT CONTENT FOLLOWS"
SYNTHETIC_TAIL = 'Reply with exactly one JSON object and nothing else: {"probe":"OK"}'
SYNTHETIC_BLOCK_REPEATS = 100

PROBE_SPECS = {
    "BUDGET_4096": {"max_tokens": 4096, "response_format": None, "kind": KIND_NONE},
    "JSON_OBJECT": {"max_tokens": 128, "response_format": JSON_OBJECT_FORMAT,
                    "kind": KIND_JSON_OBJECT},
    "JSON_SCHEMA": {"max_tokens": 128, "response_format": JSON_SCHEMA_FORMAT,
                    "kind": KIND_JSON_SCHEMA},
}

KNOWN_MODELS = frozenset({*ROUTES.values(), "deepseek/deepseek-v4-flash",
                          "MiniMaxAI/MiniMax-M3"})
LABEL_SCHEMA = {**shape.TEXT_METADATA_SCHEMA,
                "known": shape.nullable(KNOWN_MODELS | {"OTHER"})}
USAGE_SCHEMA = {key: shape.nullable(int) for key in live._KEPT_USAGE}
FINISH_SCHEMA = frozenset({"stop", "length", "content_filter", "tool_calls", "OTHER"})
CALL_SCHEMA = {
    "probe_id": frozenset(f"{route}/{kind}" for route, kind in PROBE_ORDER),
    "route": frozenset({"A", "B"}),
    "requested_model": frozenset(ROUTES.values()),
    "reported_model": LABEL_SCHEMA,
    "request_body_sha256": shape.nullable(shape.HASH),
    "request_body_bytes": shape.nullable(int),
    "prompt_sha256": shape.HASH,
    "local_prompt_tokens": int,
    "gateway_prompt_tokens": shape.nullable(int),
    "max_tokens": frozenset({4096, 128}),
    "response_format_kind": frozenset({KIND_NONE, KIND_JSON_OBJECT, KIND_JSON_SCHEMA}),
    "http_status": shape.nullable(int),
    "sent": bool,
    "status": frozenset(RESULT_VOCABULARY),
    "finish_reason": shape.nullable(FINISH_SCHEMA),
    "usage": USAGE_SCHEMA,
    "output_sha256": shape.nullable(shape.HASH),
    "output_bytes": shape.nullable(int),
    "output_truncated": bool,
    "output_conformed": bool,
    "error_class": shape.nullable(ERROR_CLASSES),
    "error_sha256": shape.nullable(shape.HASH),
    "error_bytes": shape.nullable(int),
}
BAND_VALUES = frozenset({BAND_COMPARABLE, BAND_NOT_COMPARABLE, BAND_UNAVAILABLE})
ARTIFACT_SCHEMA = {
    "version": frozenset({VERSION}),
    "registration_id": shape.IDENTITY,
    "implementation": {"harness_sha256": shape.HASH},
    "started": ("regex", r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"),
    "dry_run": bool,
    "status": frozenset({"COMPLETED", "STOPPED"}),
    "routes": {key: frozenset({value}) for key, value in ROUTES.items()},
    "budget": {"max_live_calls": frozenset({6}), "spent": int, "dispatch_count": int,
               "retries": frozenset({0}), "repairs": frozenset({0}),
               "replacements": frozenset({0}), "fallbacks": frozenset({0}),
               "network_calls": int},
    "matrix": {label: {route: frozenset(RESULT_VOCABULARY) for route in ROUTES}
               for label in MATRIX_LABELS.values()},
    "context": {
        "prompt_sha256": shape.HASH, "prompt_bytes": int, "local_prompt_tokens": int,
        "historical_gateway_prompt_tokens": {route: frozenset({value}) for route, value
                                             in HISTORICAL_GATEWAY_PROMPT_TOKENS.items()},
        "observed_gateway_prompt_tokens": {route: shape.nullable(int) for route in ROUTES},
        "ratio": {route: shape.nullable(float) for route in ROUTES},
        "band": {route: frozenset(BAND_VALUES) for route in ROUTES},
    },
    "local_output_cap_chars": frozenset({LOCAL_VISIBLE_OUTPUT_CAP_CHARS}),
    "real_4096_run_safe_with_current_local_output_path": frozenset(
        {REAL_4096_RUN_SAFE_WITH_CURRENT_LOCAL_OUTPUT_PATH}),
    "native_enforcement_proven": frozenset({NATIVE_ENFORCEMENT_PROVEN}),
    "calls": ("list", CALL_SCHEMA, 6),
    "privacy": {key: frozenset({False}) for key in (
        "prompt_persisted", "output_persisted", "error_body_persisted",
        "auth_token_persisted")},
    "side_effects": {key: frozenset({0}) for key in (
        "mail", "seal", "store", "attention", "advice_presentation",
        "production_generation", "reviewer_calls", "b018_corpus_reads")},
    "stop_reason": shape.nullable(frozenset({"AUTH_REFUSED", "GATEWAY_UNREACHABLE", "OTHER"})),
    "provider_retention": frozenset({"NOT_VERIFIED_BY_SAIMAIL"}),
}


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def registration(root=ROOT, path=REGISTRATION_PATH) -> dict:
    """The frozen gate: bytes, routes, probes, budget, prompts and protected inputs."""
    raw = pathlib.Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != REGISTRATION_SHA256:
        _reject("CAPABILITY_REGISTRATION_MISMATCH",
                "the registration bytes do not match the pinned digest")
    document = json.loads(raw)
    if (document["routes"] != ROUTES
            or document["probe_order"] != [f"{route}/{kind}" for route, kind in PROBE_ORDER]):
        _reject("CAPABILITY_PROBE_DRIFT", "routes or probe order drifted from the frozen gate")
    budget = document["budget"]
    if (budget["max_live_calls"] != 6 or budget["retries"] != 0 or budget["repairs"] != 0
            or budget["replacements"] != 0 or budget["fallbacks"] != 0):
        _reject("CAPABILITY_POLICY_DRIFT", "call budget or no-retry policy drifted")
    if (document["enforcement"]["native_enforcement_proven"] is not False
            or document["enforcement"]["real_4096_run_safe_with_current_local_output_path"]
            is not False
            or document["local_output_cap_chars"] != live.MAX_OUTPUT_CHARS):
        _reject("CAPABILITY_POLICY_DRIFT", "claim flags or the local output cap drifted")
    if set(document["result_vocabulary"]) != RESULT_VOCABULARY:
        _reject("CAPABILITY_POLICY_DRIFT", "the closed result vocabulary drifted")
    for row in document["protected_files"]:
        live_bytes = (pathlib.Path(root) / row["path"]).read_bytes()
        if hashlib.sha256(live_bytes).hexdigest() != row["sha256"]:
            _reject("CAPABILITY_PROTECTED_INPUT_DRIFT", f"{row['path']} changed since the freeze")
    prompt = synthetic_context_prompt()
    if (shape.digest(prompt) != document["context"]["prompt_sha256"]
            or len(prompt.encode("utf-8")) != document["context"]["prompt_bytes"]
            or live.estimate_tokens(prompt) != document["context"]["local_prompt_tokens"]):
        _reject("CAPABILITY_PROMPT_DRIFT",
                "synthetic context bytes or the local token estimate drifted")
    if shape.digest(TINY_PROMPT) != document["prompts"]["tiny_prompt_sha256"]:
        _reject("CAPABILITY_PROMPT_DRIFT", "the tiny probe prompt drifted")
    return document


def _enum(value, allowed):
    return value if type(value) is str and value in allowed else "OTHER"


def _model_label(value) -> dict:
    return {**shape.text_metadata(value),
            "known": _enum(value, KNOWN_MODELS | {"OTHER"}) if type(value) is str else None}


def implementation() -> dict:
    return {"harness_sha256": hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest()}


def synthetic_context_prompt() -> str:
    """Deterministic synthetic filler; contains nothing from the project."""
    lines = [SYNTHETIC_HEADER]
    for index in range(1, SYNTHETIC_BLOCK_REPEATS + 1):
        lines.append(
            f"SYNTHETIC_EVENT_{index:04d} status=OBSERVED priority=P3 "
            f"SYNTHETIC_EVIDENCE_{index:04d} class=synthetic_operational_record "
            f"SYNTHETIC_CONTENT_BLOCK_{index:04d} "
            f"payload=harmless_filler_value_{(index * 7919) % 100000:05d} "
            f"SYNTHETIC_ACTOR_{index:04d} role=observer "
            f"SYNTHETIC_SCOPE project:SYNTHETIC_ONLY")
    lines.extend(["", SYNTHETIC_TAIL])
    return "\n".join(lines) + "\n"


def prompt_for(kind: str) -> str:
    return synthetic_context_prompt() if kind == "BUDGET_4096" else TINY_PROMPT


def request_body(model: str, prompt: str, max_tokens: int,
                 response_format: dict | None) -> bytes:
    """The one body builder both transports use; no second construction path."""
    document = {"model": model, "stream": False, "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}]}
    if response_format is not None:
        document["response_format"] = response_format
    return json.dumps(document).encode("utf-8")


def conforms_to_probe_object(raw) -> bool:
    """Exact registered probe shape: one object, one key, value OK, nothing else."""
    if type(raw) is not str or not raw.strip():
        return False
    stripped = raw.strip()

    def unique(pairs):
        seen = {}
        for key, value in pairs:
            if key in seen:
                raise ValueError("duplicate key")
            seen[key] = value
        return seen

    try:
        value, end = json.JSONDecoder(object_pairs_hook=unique).raw_decode(stripped)
    except (ValueError, json.JSONDecodeError):
        return False
    if end != len(stripped) or type(value) is not dict:
        return False
    return value == {"probe": "OK"}


def classify(call_status, error_class, http_status, output):
    """The frozen closed mapping from transport facts to the result vocabulary."""
    if call_status == "NOT_RUN":
        return RESULT_NOT_RUN, False
    if http_status in (401, 403):
        return RESULT_AUTH_REFUSED, False
    if error_class is None:
        conformed = conforms_to_probe_object(output)
        return (RESULT_ACCEPTED_CONFORMING if conformed
                else RESULT_ACCEPTED_NONCONFORMING), conformed
    if error_class == "EmptyOutput":
        return RESULT_ACCEPTED_NONCONFORMING, False
    if http_status is not None and 400 <= http_status < 500:
        return RESULT_REJECTED, False
    return RESULT_TRANSPORT_ERROR, False


def registration_sha256(document) -> str:
    canonical = json.dumps(document, indent=2, ensure_ascii=False, sort_keys=False) + "\n"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class _OpenerWatch:
    """Records the parent's own exact outgoing body; optionally adds one key.

    ``lab/saifren_run.py`` is the only module allowed to construct the wire
    request (and its bytes are frozen by the T-71 registration), so the
    capability path does not duplicate credential, body, error or scrub
    handling: it wraps the transport's opener, records the exact bytes the
    parent built -- adding the registered ``response_format`` key when there is
    one -- and delegates once. A body that cannot be rewritten is a hard fault,
    never a silent plain request.
    """

    def __init__(self, inner, response_format: dict | None = None) -> None:
        self._inner = inner
        self._response_format = response_format
        self.dispatched = []

    def __call__(self, request, timeout):
        if self._response_format is not None:
            body = json.loads(request.data.decode("utf-8"))
            body["response_format"] = self._response_format
            request.data = json.dumps(body).encode("utf-8")
        self.dispatched.append(request.data)
        return self._inner(request, timeout)


class CapabilityTransport(live.HttpTransport):
    """The real HttpTransport, plus one registered response_format.

    With ``response_format=None`` the probe goes through the parent ``send``
    itself, so the bytes equal the parent's exactly. With a format, the opener
    is wrapped for exactly one dispatch and the exact mutated body hash is
    attached as evidence. One ``send_probe`` is one HTTP request; a rejection
    is recorded, never retried, and a failed rewrite never becomes a fallback.
    """

    def send_probe(self, prompt: str, *, model: str | None, max_tokens: int,
                   response_format: dict | None = None) -> dict:
        watch = _OpenerWatch(self._opener, response_format)
        self._opener = watch
        try:
            result = self.send(prompt, model=model, max_tokens=max_tokens)
        finally:
            self._opener = watch._inner
        if len(watch.dispatched) != 1:
            _reject("CAPABILITY_EVIDENCE_MISSING",
                    "the registered request body was not dispatched exactly once")
        result["request_body_sha256"] = hashlib.sha256(watch.dispatched[0]).hexdigest()
        result["request_body_bytes"] = len(watch.dispatched[0])
        return result


class ProbeDispatch:
    """Project metadata explicitly, erase the Runner carrier even on failure."""

    def __init__(self, runner) -> None:
        self.runner = runner
        self.records = []

    def __call__(self, route, kind, prompt, spec) -> dict:
        probe_id = f"{route}/{kind}"
        before = self.runner.budget.used
        call = self.runner.call(probe_id, route, prompt, model=ROUTES[route])
        try:
            raw = call.get("output")
            output = raw if type(raw) is str else ""
            truncated = call.get("output_truncated") if type(call.get("output_truncated")) is bool \
                else False
            usage = call.get("usage") if type(call.get("usage")) is dict else {}
            error = call.get("error") if type(call.get("error")) is str else ""
            error_class = call.get("error_class")
            http_status = call.get("http_status")
            if type(http_status) is not int:
                http_status = None
            status, conformed = classify(call.get("status"), error_class, http_status, output)
            body_sha256, body_bytes = _request_evidence(call)
            record = {
                "probe_id": probe_id, "route": route,
                "requested_model": ROUTES[route],
                "reported_model": _model_label(call.get("reported_model")),
                "request_body_sha256": body_sha256,
                "request_body_bytes": body_bytes,
                "prompt_sha256": shape.digest(prompt),
                "local_prompt_tokens": live.estimate_tokens(prompt),
                "gateway_prompt_tokens": _count(usage.get("prompt_tokens"), nullable=True),
                "max_tokens": spec["max_tokens"],
                "response_format_kind": spec["kind"],
                "http_status": http_status,
                "sent": self.runner.budget.used > before,
                "status": status,
                "finish_reason": _enum(call.get("finish_reason"), FINISH_SCHEMA)
                    if call.get("finish_reason") is not None else None,
                "usage": {key: _count(usage.get(key), nullable=True) for key in live._KEPT_USAGE},
                "output_sha256": shape.digest(output) if output else None,
                "output_bytes": len(output.encode("utf-8", "surrogatepass")) if output else None,
                "output_truncated": truncated,
                "output_conformed": conformed,
                "error_class": _enum(error_class, ERROR_CLASSES) if error_class else None,
                "error_sha256": shape.digest(error) if error else None,
                "error_bytes": len(error.encode("utf-8", "surrogatepass")) if error else None,
            }
            shape.validate(record, CALL_SCHEMA)
            self.records.append(record)
            return record
        finally:
            call.clear()


def _request_evidence(call) -> tuple:
    """A dispatched probe owes its exact body evidence; a skipped one has none."""
    if call.get("status") == "NOT_RUN":
        return None, None
    body_sha256 = call.get("request_body_sha256")
    body_bytes = call.get("request_body_bytes")
    if (type(body_sha256) is not str or len(body_sha256) != 64
            or type(body_bytes) is not int or body_bytes < 0):
        _reject("CAPABILITY_EVIDENCE_MISSING",
                "the transport reported no exact request-body evidence")
    return body_sha256, body_bytes


def _count(value, nullable: bool = False):
    if type(value) is int and 0 <= value < 2**63:
        return value
    return None if nullable else 0


class DryTransport:
    """Deterministic registered dry world; proves the harness, makes no call.

    Route A: 4096 conforming, json_object conforming, json_schema accepted but
    nonconforming (with the 4000-character transport cap visible). Route B:
    4096 conforming, json_object rejected with HTTP 400 (and the experiment
    continues), json_schema conforming.
    """

    def __init__(self) -> None:
        self.dispatches = 0

    def _result(self, model, prompt, spec, output, *, error_class=None, error="",
                http_status=None, finish="stop", truncated=None) -> dict:
        body = request_body(model, prompt, spec["max_tokens"], spec["response_format"])
        result = {"output": output, "reported_model": model, "http_status": http_status,
                  "finish_reason": finish,
                  "output_truncated": (len(output) > live.MAX_OUTPUT_CHARS
                                       if truncated is None else truncated),
                  "inline_trace_removed": False, "latency_s": 0.0, "usage": {},
                  "request_body_sha256": hashlib.sha256(body).hexdigest(),
                  "request_body_bytes": len(body)}
        if error_class:
            result.update({"error_class": error_class, "error": error,
                           "output": output[:live.MAX_OUTPUT_CHARS]})
        return result

    def send_probe(self, prompt, *, model, max_tokens, response_format=None) -> dict:
        self.dispatches += 1
        kind = ("BUDGET_4096" if max_tokens == 4096 else
                "JSON_OBJECT" if response_format == JSON_OBJECT_FORMAT else "JSON_SCHEMA")
        spec = PROBE_SPECS[kind]
        if kind == "BUDGET_4096":
            return self._result(model, prompt, spec, '{"probe":"OK"}')
        if kind == "JSON_OBJECT":
            if model == ROUTES["B"]:
                return self._result(model, prompt, spec, "",
                                    error_class="HTTPError", error="HTTP 400 rejected: synthetic",
                                    http_status=400)
            return self._result(model, prompt, spec, '{"probe":"OK"}')
        if model == ROUTES["A"]:
            filler = "x" * 4200
            return self._result(model, prompt, spec, filler[:live.MAX_OUTPUT_CHARS],
                                truncated=True)
        return self._result(model, prompt, spec, '{"probe":"OK"}')


def _sent(records) -> int:
    return sum(1 for record in records if record["sent"])


def _matrix(records) -> dict:
    table = {label: {route: RESULT_NOT_RUN for route in ROUTES}
             for label in MATRIX_LABELS.values()}
    for record in records:
        kind = record["probe_id"].split("/", 1)[1]
        table[MATRIX_LABELS[kind]][record["route"]] = record["status"]
    return table


def _band(ratio) -> str:
    if ratio is None:
        return BAND_UNAVAILABLE
    return BAND_COMPARABLE if COMPARABLE_LOW <= ratio <= COMPARABLE_HIGH else BAND_NOT_COMPARABLE


def _context(records) -> dict:
    prompt = synthetic_context_prompt()
    observed = {route: None for route in ROUTES}
    for record in records:
        if record["probe_id"].endswith("/BUDGET_4096"):
            observed[record["route"]] = record["gateway_prompt_tokens"]
    ratio = {route: (round(observed[route] / HISTORICAL_GATEWAY_PROMPT_TOKENS[route], 2)
                     if observed[route] is not None else None) for route in ROUTES}
    return {
        "prompt_sha256": shape.digest(prompt),
        "prompt_bytes": len(prompt.encode("utf-8")),
        "local_prompt_tokens": live.estimate_tokens(prompt),
        "historical_gateway_prompt_tokens": dict(HISTORICAL_GATEWAY_PROMPT_TOKENS),
        "observed_gateway_prompt_tokens": observed,
        "ratio": ratio,
        "band": {route: _band(ratio[route]) for route in ROUTES},
    }


def _stop_reason(stopped) -> str | None:
    if not stopped:
        return None
    if stopped.startswith("AUTH_REFUSED"):
        return "AUTH_REFUSED"
    if stopped.startswith("GATEWAY_UNREACHABLE"):
        return "GATEWAY_UNREACHABLE"
    return "OTHER"


def _experiment(transport, *, dry_run: bool, started: str) -> dict:
    registration()  # validate the frozen gate before any dispatch
    budget = live.CallBudget(6)
    dispatch_count = {"n": 0}

    def send(prompt, model=None):
        kind = dispatch_count["current"]
        dispatch_count["n"] += 1
        return transport.send_probe(
            prompt, model=model, max_tokens=PROBE_SPECS[kind]["max_tokens"],
            response_format=PROBE_SPECS[kind]["response_format"])

    runner = live.Runner(send, budget, alias=ROUTES["A"])
    dispatch = ProbeDispatch(runner)
    for route, kind in PROBE_ORDER:
        dispatch_count["current"] = kind
        dispatch(route, kind, prompt_for(kind), PROBE_SPECS[kind])
    network_calls = 0 if dry_run else _sent(dispatch.records)
    document = {
        "version": VERSION,
        "registration_id": "sha256:" + REGISTRATION_SHA256,
        "implementation": implementation(),
        "started": started, "dry_run": dry_run,
        "status": "STOPPED" if runner.stopped else "COMPLETED",
        "routes": dict(ROUTES),
        "budget": {"max_live_calls": 6, "spent": budget.used,
                   "dispatch_count": dispatch_count["n"],
                   "retries": 0, "repairs": 0, "replacements": 0, "fallbacks": 0,
                   "network_calls": network_calls},
        "matrix": _matrix(dispatch.records),
        "context": _context(dispatch.records),
        "local_output_cap_chars": LOCAL_VISIBLE_OUTPUT_CAP_CHARS,
        "real_4096_run_safe_with_current_local_output_path":
            REAL_4096_RUN_SAFE_WITH_CURRENT_LOCAL_OUTPUT_PATH,
        "native_enforcement_proven": NATIVE_ENFORCEMENT_PROVEN,
        "calls": dispatch.records,
        "privacy": {key: False for key in ARTIFACT_SCHEMA["privacy"]},
        "side_effects": {key: 0 for key in ARTIFACT_SCHEMA["side_effects"]},
        "stop_reason": _stop_reason(runner.stopped),
        "provider_retention": "NOT_VERIFIED_BY_SAIMAIL",
    }
    shape.validate(document, ARTIFACT_SCHEMA)
    return document


def expected_dry_matrix() -> dict:
    return {
        "4096": {"A": RESULT_ACCEPTED_CONFORMING, "B": RESULT_ACCEPTED_CONFORMING},
        "json_object": {"A": RESULT_ACCEPTED_CONFORMING, "B": RESULT_REJECTED},
        "json_schema": {"A": RESULT_ACCEPTED_NONCONFORMING, "B": RESULT_ACCEPTED_CONFORMING},
    }


def _answer(number: int, document: dict) -> str:
    matrix = document["matrix"]
    bands = ", ".join(f"{route} {document['context']['band'][route]}" for route in ROUTES)
    answers = {
        1: f"1. Route A accepted the 4096 request: {matrix['4096']['A']}.",
        2: f"2. Route B accepted the 4096 request: {matrix['4096']['B']}.",
        3: f"3. Synthetic context comparability to T-71: {bands}"
           f" (ratios {document['context']['ratio']}).",
        4: f"4. Route A accepted json_object: {matrix['json_object']['A']}.",
        5: f"5. Route B accepted json_object: {matrix['json_object']['B']}.",
        6: "6. Sample conformance per corresponding json_object result: "
           + "; ".join(f"{route} {matrix['json_object'][route]}" for route in ROUTES) + ".",
        7: f"7. Route A accepted json_schema: {matrix['json_schema']['A']}.",
        8: f"8. Route B accepted json_schema: {matrix['json_schema']['B']}.",
        9: "9. Sample conformance per corresponding json_schema result: "
           + "; ".join(f"{route} {matrix['json_schema'][route]}" for route in ROUTES) + ".",
        10: f"10. Native enforcement proven: {document['native_enforcement_proven']}."
            " One conforming sample is not stable enforcement.",
        11: "11. A real 4096 run through the current local output path is safe: "
            f"{document['real_4096_run_safe_with_current_local_output_path']}"
            f" (local visible-output cap {document['local_output_cap_chars']} characters).",
        12: f"12. Fallbacks/retries performed: fallbacks {document['budget']['fallbacks']}, "
            f"retries {document['budget']['retries']}.",
    }
    return answers[number]


def render_report(document: dict) -> str:
    shape.validate(document, ARTIFACT_SCHEMA)
    lines = ["# Structured-output / completion-budget capability gate", "",
             (f"Registration: `{document['registration_id']}`; dry run: {document['dry_run']}; "
              f"status: `{document['status']}`."),
             (f"Calls: {document['budget']['spent']}/6; dispatches "
              f"{document['budget']['dispatch_count']}; network calls "
              f"{document['budget']['network_calls']}; retries 0; repairs 0; fallbacks 0."),
             "", "## Capability matrix", "",
             "| probe | A | B |", "|---|---|---|"]
    for label in ("4096", "json_object", "json_schema"):
        row = document["matrix"][label]
        lines.append(f"| {label} | {row['A']} | {row['B']} |")
    lines.extend(["", "## Fresh reported models", ""])
    for record in document["calls"]:
        lines.append(f"- {record['probe_id']}: requested `{record['requested_model']}`, "
                     f"reported known label `{record['reported_model']['known']}` "
                     f"(SHA256 `{record['reported_model']['sha256']}`).")
    lines.extend(["", "## Twelve questions", ""])
    lines.extend(_answer(number, document) for number in range(1, 13))
    lines.extend(["", "## Interpretation limits", "",
        ("A capability probe is not product semantics: one accepted request is not"
         " stable capability, and one conforming output is not proven enforcement."),
        "No model ranking is made: six capability calls are not model evaluation.",
        "No real corpus, no AllyAdvice generation and no semantic review was involved.",
        "Outputs are represented by SHA256 and byte count only; prompts by hash.",
        "No mail, seal, store or attention operation is invoked.",
        "Provider retention/training use is NOT_VERIFIED_BY_SAIMAIL.", ""])
    return "\n".join(lines)


def render_analysis(document: dict) -> str:
    shape.validate(document, ARTIFACT_SCHEMA)
    context = document["context"]
    registration_line = (f"Registration `{document['registration_id']}`; artifact started "
                         f"{document['started']}.")
    prompt_line = (f"- Local synthetic prompt: {context['local_prompt_tokens']} tokens, "
                   f"{context['prompt_bytes']} bytes, SHA256 `{context['prompt_sha256']}`.")
    gateway_line = (f"- Gateway prompt tokens: {context['observed_gateway_prompt_tokens']}; "
                    f"T-71 route history: {context['historical_gateway_prompt_tokens']}; "
                    f"ratios: {context['ratio']}; bands: {context['band']}.")
    lines = ["# Structured-output capability gate -- analysis", "",
             registration_line, "",
             "## Measured request acceptance",
             (f"- 4096 completion request: A `{document['matrix']['4096']['A']}`, "
              f"B `{document['matrix']['4096']['B']}`."),
             (f"- json_object: A `{document['matrix']['json_object']['A']}`, "
              f"B `{document['matrix']['json_object']['B']}`."),
             (f"- json_schema: A `{document['matrix']['json_schema']['A']}`, "
              f"B `{document['matrix']['json_schema']['B']}`."),
             "", "## Context comparability (descriptive only)",
             prompt_line, gateway_line, "",
             "## Bounded claims",
             (f"- Request acceptance and output conformance are reported separately; "
              f"native enforcement proven: {document['native_enforcement_proven']}."),
             (f"- Local parser-input cap remains {document['local_output_cap_chars']} "
              f"characters; a real 4096 run through the unchanged local path is safe: "
              f"{document['real_4096_run_safe_with_current_local_output_path']} -- local "
              f"next-gate requirement, not a remote capability statement."),
             "- No retry, repair, replacement or fallback exists in this harness.", ""]
    return "\n".join(lines)


def _reserve(path, dry_sha256=None) -> None:
    payload = json.dumps({"registration_id": "sha256:" + REGISTRATION_SHA256,
                          "implementation": implementation(),
                          "dry_sha256": dry_sha256, "attempt_id": uuid.uuid4().hex,
                          "started": live._now()})
    result = publish_immutable(pathlib.Path(path), (payload + "\n").encode(),
                               conflict_code="CAPABILITY_ALREADY_ATTEMPTED")
    if result != PUBLISHED:
        _reject("CAPABILITY_ALREADY_ATTEMPTED", "the registered live attempt already ran")


def _write(root, doc, document, api_key) -> dict:
    shape.validate(document, ARTIFACT_SCHEMA)
    text = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    report = render_report(document)
    analysis = render_analysis(document)
    live.assert_no_secret(text, api_key)
    live.assert_no_secret(report, api_key)
    live.assert_no_secret(analysis, api_key)
    stamp = document["started"].replace("-", "").replace(":", "")
    paths = {"dry": pathlib.Path(root) / doc["artifacts"]["dry"]} if document["dry_run"] else {
        "artifact": pathlib.Path(root) / doc["artifacts"]["artifact"].replace("<UTCSTAMP>", stamp),
        "report": pathlib.Path(root) / doc["artifacts"]["report"].replace("<UTCSTAMP>", stamp),
        "analysis": pathlib.Path(root) / doc["artifacts"]["analysis"].replace("<UTCSTAMP>", stamp),
    }
    for key, path in paths.items():
        publish_immutable(path, (text if key in ("dry", "artifact") else
                                 report if key == "report" else analysis).encode("utf-8"),
                          conflict_code="CAPABILITY_ARTIFACT_EXISTS")
    return {key: str(path) for key, path in paths.items()}


def run(*, dry_run: bool = False, root=ROOT, registration_path=REGISTRATION_PATH) -> dict:
    doc = registration(root, registration_path)
    started = live._now()
    api_key = ""
    if dry_run:
        transport = DryTransport()
        document = _experiment(transport, dry_run=True, started=started)
        if document["matrix"] != expected_dry_matrix() or document["budget"]["network_calls"] != 0:
            _reject("CAPABILITY_DRY_CONTROL_FAILED", "deterministic dry matrix drifted")
    else:
        marker = pathlib.Path(root) / doc["attempt_marker"]
        if marker.exists():
            _reject("CAPABILITY_ALREADY_ATTEMPTED", "the registered live attempt already ran")
        dry_path = pathlib.Path(root) / doc["artifacts"]["dry"]
        if not dry_path.exists():
            _reject("CAPABILITY_DRY_CONTROL_REQUIRED", "run the dry control first")
        proof = json.loads(dry_path.read_text(encoding="utf-8"))
        shape.validate(proof, ARTIFACT_SCHEMA)
        if (not proof["dry_run"] or proof["registration_id"] != "sha256:" + REGISTRATION_SHA256
                or proof["implementation"] != implementation()
                or proof["matrix"] != expected_dry_matrix()
                or proof["budget"]["network_calls"] != 0):
            _reject("CAPABILITY_DRY_CONTROL_REQUIRED", "the dry proof does not match this gate")
        try:
            credential = resolve()
            api_key = credential.secret
        except (CredentialNotProvisioned, CredentialError):
            _reject("CAPABILITY_CREDENTIAL_UNAVAILABLE", "no credential message reaches console")
        _reserve(marker, hashlib.sha256(dry_path.read_bytes()).hexdigest())
        document = _experiment(CapabilityTransport(api_key), dry_run=False, started=started)
    paths = _write(root, doc, document, api_key)
    return {"status": document["status"], "dry_run": dry_run, "matrix": document["matrix"],
            "budget": document["budget"], "artifacts": paths}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(dry_run=args.dry_run, root=ROOT)
    except SailangError as exc:
        print(json.dumps({"status": "REFUSED", "code": exc.code}))
        return 1
    except Exception:  # noqa: BLE001 - exception text must never reach the console
        print(json.dumps({"status": "REFUSED", "code": "CAPABILITY_HARNESS_ERROR"}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
