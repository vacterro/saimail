"""Bounded live validation through 9router -> SAIRoute -> SAIFREN.

Role A is whatever the SAIFREN alias resolves to; role B, when one answers, is an
external catalog comparator beside it, never a SAIFREN member, and every
artifact says which class of run it was (D-024).

This is the ONLY module in the repository that touches the network, and it is
never imported by ``sailang`` or ``saimail``. Everything it writes is
**experiment data** (D-018):

    LIVE OUTPUT = EXPERIMENT DATA
    not CONSENSUS, not TRUTH, not a PROTOCOL CHANGE, not USER INTENT

Agents may disagree, and disagreement is kept per call, never voted away. A
repeated failure may justify proposing a protocol change; it never makes one.

The contract, each clause tested in ``tests/test_lab_contract.py``:

* at most ``MAX_RUNS`` live calls per suite run, refused before the first call
  when the plan is larger and refused again at every call;
* the credential is resolved from the named handle
  ``credential://9router/sairoute`` through the local credential store
  (D-019). The ordinary command reads no secret from the environment; the
  legacy variable is reachable only by naming ``--credential-source env``, and
  whichever source was used is recorded in the artifact by label. The secret
  lives in the transport object and is checked for absence before any artifact
  is written; no Authorization header value is ever persisted;
* a dry run performs zero network calls;
* a call record keeps observable output only: content, finish reason, the
  model id the gateway reported, allow-listed routing headers, token counts.
  ``reasoning`` / ``reasoning_details`` and every other payload field are
  dropped before anything is stored;
* a failure or timeout becomes a bounded ERROR record and the suite goes on,
  except an authentication refusal, which stops it: that failure is systemic;
* provider identity is recorded only when the gateway states it. A reported
  model id is kept exactly as reported, and its prefix is labelled a namespace,
  not a provider.

    python tools/provision_sairoute_credential.py        # once, interactively
    python lab/saifren_run.py --out lab/out --dry-run    # renders everything, no calls
    python lab/saifren_run.py --out lab/out              # bounded live run
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import pathlib
import re
import socket
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Callable, Dict, List, Mapping, Optional

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sailang.frame import Profile  # noqa: E402

from lab import experiment_class as ec  # noqa: E402
from lab import saifren_population as pop  # noqa: E402
from lab import scenarios as sc  # noqa: E402
from lab.answer_schema import ATTENTION_CLASSES, classify_attention, grade  # noqa: E402
from lab.report import render as render_report  # noqa: E402
from saimail.credentials import (  # noqa: E402
    DEFAULT_HANDLE, SOURCE_ENV, SOURCE_STORE, SOURCES, CredentialNotProvisioned,
    CredentialError, resolve)

BASE_URL = os.environ.get("SAIROUTE_BASE_URL", "http://127.0.0.1:20128")
COMBO = os.environ.get("SAIFREN_COMBO", "SAIFREN")
CONTEXT_VISIBILITY = "OPAQUE"
#: Retained so an existing workflow keeps a name to point at. It is read only
#: when ``--credential-source env`` is named on the command line (D-019).
KEY_ENV = "SAIROUTE_API_KEY"
#: Unit prefixes of the narrow validation sample (``--sample``). Declared here
#: rather than chosen after a run: the sample proves the canonical credential
#: path, two distinct participants completing one A-to-B handoff, the attention
#: classification, and one claim-bound legacy packet reaching a successor.
SAMPLE_UNITS = ("S2.chain1", "S3.mailbox", "S5.trial1")
#: Probe answers are tiny; a probe measures reachability and identity, not skill.
PROBE_MAX_TOKENS = 16
#: Hard cap on live calls in one suite run, discovery included. A live experiment
#: has a bounded run count or it is not an experiment. The full plan is 22 calls
#: and a discovering run reserves 8 more for membership sampling and participant
#: selection, so the cap is exactly what such a run needs and not one call more.
MAX_RUNS = 30
TIMEOUT_SECONDS = 120
MAX_TOKENS = 2048
MAX_RESPONSE_BYTES = 2_000_000
MAX_OUTPUT_CHARS = 4000
MAX_ERROR_CHARS = 240
#: Consecutive transport failures after which the gateway is treated as down.
MAX_CONSECUTIVE_TRANSPORT_ERRORS = 3
#: The error classes a genuine transport failure arrives as (W2-001). Transport
#: health is read from this closed set, never inferred from ``http_status is
#: None`` alone: a harness exception or an operational failure is not gateway
#: unavailability.
TRANSPORT_ERROR_CLASSES = frozenset({
    "URLError", "TimeoutError", "timeout", "ConnectionError", "OSError",
})
PROTOCOL_VERSION = "SAILANG frame v4 / SAIB4"

AUTHORITY = "EXPERIMENT_DATA"
IS_NOT = ("CONSENSUS", "TRUTH", "PROTOCOL_CHANGE", "USER_INTENT")
NOTE = ("Live output is experiment data. It is not consensus, not truth, not a protocol "
        "change and not user intent. Disagreement between agents is preserved per call. "
        "Reasoning traces are dropped before storage.")

_KEPT_USAGE = ("prompt_tokens", "completion_tokens", "total_tokens")
_ROUTE_HEADER = re.compile(r"(?i)(model|provider|route|combo|upstream)")
_SECRET_HEADER = re.compile(r"(?i)(key|auth|token|cookie|secret|session|account|email|user)")
_HEADER_VALUE = re.compile(r"(?i)\b(authorization|proxy-authorization)\s*[:=]\s*\S+(?:\s+\S+)?")
_BEARER = re.compile(r"(?i)\bbearer\s+\S+")
#: The shape of a persisted header, as opposed to a model mentioning the word.
_HEADER_LINE = re.compile(r"(?i)\"?authorization\"?\s*[:=]\s*\"?bearer\s")
_INLINE_REASONING = re.compile(r"(?is)<(think|thinking|reasoning)>.*?</\1>")
_UNCLOSED_REASONING = re.compile(r"(?is)^\s*<(think|thinking|reasoning)>.*$")


class BudgetExceeded(RuntimeError):
    """The call budget is spent. Raised before a call, never after one."""


class SecretLeak(RuntimeError):
    """An artifact would have carried the credential. Nothing is written."""


class AuthRefused(RuntimeError):
    """The gateway rejected the credential (HTTP 401/403). Systemic, not local.

    An authentication refusal means no further request of any kind will
    succeed, so it stops discovery, probing and the experiment alike (W2-002);
    it is never recategorised as unavailability of a candidate model.
    """


def _accepts_model_kwarg(send: Callable) -> bool:
    """Decide send-call capability before the first dispatch (W2-001).

    Retrying a TypeError after a real dispatch would double a live call without
    spending a second budget unit, so capability is determined once, up front,
    and every logical call executes the callback exactly once. A callable whose
    signature cannot be read is called positionally only.
    """
    try:
        signature = inspect.signature(send)
    except (TypeError, ValueError):
        return False
    parameters = signature.parameters.values()
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return True
    return "model" in signature.parameters


def _write_immutable(path: pathlib.Path, text: str) -> None:
    """Create historical experiment evidence once or refuse (D-022, W2-003).

    A second-resolution timestamp is readability, not identity: artifacts are
    named by a unique run id, and a write that would replace bytes that already
    exist and differ refuses instead of deleting the evidence an earlier
    interpretation cited.
    """
    if path.exists():
        if path.read_text(encoding="utf-8") == text:
            return
        raise FileExistsError(
            f"{path.name} already exists with different content; immutable experiment "
            "evidence is never replaced")
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


class CallBudget:
    def __init__(self, cap: int = MAX_RUNS) -> None:
        self.cap = cap
        self.used = 0

    def spend(self) -> None:
        if self.used >= self.cap:
            raise BudgetExceeded(f"call {self.used + 1} exceeds the cap of {self.cap}")
        self.used += 1


def scrub(text: str, secret: str = "") -> str:
    text = text if isinstance(text, str) else str(text)
    if secret:
        text = text.replace(secret, "[REDACTED]")
    text = _HEADER_VALUE.sub("[REDACTED]", text)
    return _BEARER.sub("[REDACTED]", text)


def observable(payload: dict, headers: Mapping[str, str], alias: str) -> dict:
    """Reduce a chat completion to what an outside observer may keep.

    Allow-list, not deny-list: a field the gateway adds tomorrow is dropped
    until somebody decides it is observable. Reasoning never survives this.
    """
    choices = payload.get("choices")
    first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) \
        else {}
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(part.get("text", "") for part in content
                          if isinstance(part, dict) and part.get("type") in (None, "text")
                          and isinstance(part.get("text"), str))
    content = content if isinstance(content, str) else ""
    # Some models put their reasoning inline. It is reasoning all the same: removed
    # before storage and before grading, and the removal itself is recorded.
    visible = _INLINE_REASONING.sub("", content)
    visible = _UNCLOSED_REASONING.sub("", visible).strip()
    inline_removed = visible != content.strip()
    content = visible

    reported = payload.get("model") if isinstance(payload.get("model"), str) else None
    route_headers = {name.lower(): str(value)[:120] for name, value in headers.items()
                     if _ROUTE_HEADER.search(name) and not _SECRET_HEADER.search(name)}
    provider, basis = None, "NOT_EXPOSED"
    if isinstance(payload.get("provider"), str) and payload["provider"]:
        provider, basis = payload["provider"], "RESPONSE_FIELD"
    else:
        named = sorted(n for n in route_headers if "provider" in n)
        if named:
            provider, basis = route_headers[named[0]], f"RESPONSE_HEADER:{named[0]}"
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    finish = first.get("finish_reason")
    return {
        "output": content[:MAX_OUTPUT_CHARS],
        "output_truncated": len(content) > MAX_OUTPUT_CHARS,
        "inline_trace_removed": inline_removed,
        "finish_reason": finish if isinstance(finish, str) else None,
        "reported_model": reported,
        "route_resolution": "ALIAS_ONLY" if reported in (None, alias) else "MODEL_REPORTED",
        # the part of a reported id before "/"; a namespace label, not a provider claim
        "model_namespace": reported.split("/", 1)[0] if reported and "/" in reported else None,
        "provider": provider,
        "provider_basis": basis,
        "route_headers": route_headers,
        "gen_id": payload.get("id") if isinstance(payload.get("id"), str) else None,
        "usage": {k: usage[k] for k in _KEPT_USAGE if isinstance(usage.get(k), int)},
    }


class HttpTransport:
    """One OpenAI-compatible chat call per ``send``. Holds the key; never shows it."""

    def __init__(self, api_key: str, base_url: str = BASE_URL, alias: str = COMBO,
                 timeout: float = TIMEOUT_SECONDS, opener: Optional[Callable] = None) -> None:
        self._key = api_key
        self._base_url = base_url.rstrip("/")
        self._alias = alias
        self._timeout = timeout
        # resolved per call, so nothing captures the real urlopen at import time
        self._opener = opener or (lambda request, timeout: urllib.request.urlopen(
            request, timeout=timeout))

    def __repr__(self) -> str:
        return f"HttpTransport({self._base_url!r}, alias={self._alias!r}, key=<hidden>)"

    def _error(self, error_class: str, message: str, started: float,
               http_status: Optional[int] = None) -> dict:
        return {"error_class": error_class,
                "error": scrub(message, self._key)[:MAX_ERROR_CHARS],
                "http_status": http_status,
                "latency_s": round(time.perf_counter() - started, 2)}

    def get_json(self, path: str) -> dict:
        """One authenticated read-only GET. Used for catalog discovery only."""
        request = urllib.request.Request(f"{self._base_url}{path}", method="GET",
                                         headers={"Authorization": f"Bearer {self._key}"})
        with self._opener(request, timeout=self._timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError(f"{path} returned more than {MAX_RESPONSE_BYTES} bytes")
        payload = json.loads(raw.decode("utf-8", "replace"))
        if not isinstance(payload, dict):
            raise ValueError(f"{path} did not return a JSON object")
        return payload

    def probe(self, model: str) -> dict:
        """The smallest call that still reports which model answered."""
        return self.send(pop.PROBE_PROMPT, model=model, max_tokens=PROBE_MAX_TOKENS)

    def send(self, prompt: str, model: Optional[str] = None,
             max_tokens: int = MAX_TOKENS) -> dict:
        target_model = model or self._alias
        body = json.dumps({"model": target_model, "stream": False, "max_tokens": max_tokens,
                           "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url}/v1/chat/completions", data=body, method="POST",
            headers={"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"})
        started = time.perf_counter()
        try:
            with self._opener(request, timeout=self._timeout) as response:
                status = getattr(response, "status", None)
                headers = dict(response.headers.items()) if getattr(response, "headers", None) \
                    else {}
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read(300).decode("utf-8", "replace")
            except Exception:  # noqa: BLE001 - an unreadable error body is still an error
                detail = ""
            return self._error("HTTPError", f"HTTP {exc.code} {detail}".strip(), started,
                               http_status=exc.code)
        except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError,
                OSError) as exc:
            return self._error(type(exc).__name__, str(exc), started)
        if len(raw) > MAX_RESPONSE_BYTES:
            return self._error("ResponseTooLarge", f"more than {MAX_RESPONSE_BYTES} bytes",
                               started, http_status=status)
        raw_text = raw.decode("utf-8", "replace").strip()
        if raw_text.endswith("data: [DONE]"):
            raw_text = raw_text[:-len("data: [DONE]")].strip()
        try:
            payload = json.loads(raw_text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._error("MalformedResponse", "response body is not JSON", started,
                               http_status=status)
        if not isinstance(payload, dict):
            return self._error("MalformedResponse", "response JSON is not an object", started,
                               http_status=status)
        if payload.get("error") and not payload.get("choices"):
            error = payload["error"]
            message = error.get("message") if isinstance(error, dict) else error
            return self._error("GatewayError", str(message), started, http_status=status)
        seen = observable(payload, headers, target_model)
        seen.update({"http_status": status, "latency_s": round(time.perf_counter() - started, 2)})
        if not seen["output"]:
            # An empty answer is an operational failure (often a token budget spent
            # on hidden reasoning), not a semantic one; grading it would blur the two.
            return {**seen, "error_class": "EmptyOutput",
                    "error": f"no content; finish_reason={seen['finish_reason']}"}
        return seen


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Runner:
    """Executes a plan with one budget. ``send`` is None in a dry run.

    Every call record names the model id it requested -- the alias when no
    participant was named -- because membership evidence is a property of what
    was asked for as much as of what answered (D-024).
    """

    def __init__(self, send: Optional[Callable[[str], dict]], budget: CallBudget,
                 alias: Optional[str] = None) -> None:
        self.send = send
        self.budget = budget
        self.alias = alias
        self.calls: List[dict] = []
        self.stopped: Optional[str] = None
        self._transport_errors = 0
        # capability is settled here, once, before any dispatch exists (W2-001)
        self._send_takes_model = _accepts_model_kwarg(send) if send is not None else False

    def call(self, unit_id: str, role: str, prompt: str, model: Optional[str] = None) -> dict:
        record = {"call_id": uuid.uuid4().hex[:12], "unit_id": unit_id, "role": role,
                  "requested_model": model or self.alias,
                  "timestamp": _now(), "prompt": prompt,
                  "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()}
        if self.send is None:
            record.update({"status": "NOT_RUN", "output": None})
        elif self.stopped:
            record.update({"status": "NOT_RUN", "output": None, "skipped_because": self.stopped})
        else:
            try:
                self.budget.spend()
            except BudgetExceeded as exc:
                record.update({"status": "ERROR", "output": None, "error_class": "BudgetExceeded",
                               "error": str(exc)[:MAX_ERROR_CHARS]})
                self.calls.append(record)
                return record
            # exactly one dispatch per logical call: no arity negotiation by
            # retry (W2-001), and no second spend-free call after a dispatch
            try:
                if model and self._send_takes_model:
                    result = self.send(prompt, model=model)
                else:
                    result = self.send(prompt)
            except Exception as exc:  # noqa: BLE001 - a harness bug is recorded, never retried
                result = {"error_class": "HARNESS_ERROR",
                          "error": f"{type(exc).__name__}: {exc}"[:MAX_ERROR_CHARS]}
            record.update(result)
            record["status"] = "ERROR" if result.get("error_class") else "OK"
            record.setdefault("output", None)
            if record["status"] == "ERROR" and result.get("http_status") in (401, 403):
                self.stopped = f"AUTH_REFUSED: HTTP {result['http_status']}"
            elif (record["status"] == "ERROR"
                  and result.get("http_status") is None
                  and result.get("error_class") in TRANSPORT_ERROR_CLASSES):
                self._transport_errors += 1
                if self._transport_errors >= MAX_CONSECUTIVE_TRANSPORT_ERRORS:
                    self.stopped = "GATEWAY_UNREACHABLE"
            else:
                self._transport_errors = 0
        self.calls.append(record)
        return record


def _ok(record: Optional[dict]) -> bool:
    return bool(record) and record.get("status") == "OK"


def _route(record: Optional[dict]) -> Optional[str]:
    return record.get("reported_model") if record else None


def routes_of(population) -> tuple:
    """The two model identifiers this run sends, or ``(None, None)``.

    ``None`` means "send the combo alias and let the gateway resolve it", which
    is what a run with no resolved participants is entitled to do. It is never a
    hidden default model id.
    """
    requested = [p.requested for p in getattr(population, "participants", ())]
    if len(requested) >= 2:
        return requested[0], requested[1]
    if len(requested) == 1:
        return requested[0], requested[0]
    return None, None


def execute(units, runner: Runner, profile: Profile, dry_run: bool,
            population=None) -> List[dict]:
    route_a, route_b = routes_of(population)
    results = []
    for i, unit in enumerate(units):
        if isinstance(unit, sc.Single):
            model = route_a if i % 2 == 0 else route_b
            call = runner.call(unit.unit_id, "single", unit.prompt(), model=model)
            entry = {"unit_id": unit.unit_id, "scenario": unit.scenario,
                     "input_class": unit.input_class, "hypothesis": unit.hypothesis,
                     "failure_condition": unit.failure_condition,
                     "schema": [f.name for f in unit.schema.fields],
                     "expect": {k: list(v) for k, v in unit.expect.items()},
                     "reference": dict(unit.reference), "call_id": call["call_id"]}
            if _ok(call):
                graded = grade(unit.schema, unit.expect, call["output"])
                entry.update({"grade": graded, "verdict": "PASS" if graded["pass"] else "FAIL"})
                if unit.reference:
                    # An observation beside the verdict, never inside it: the
                    # registered expectation decided PASS before this ran.
                    entry["attention"] = classify_attention(unit.reference, graded["values"])
            else:
                entry["verdict"] = "NOT_RUN" if call["status"] == "NOT_RUN" else "ERROR"
            results.append(entry)

        elif isinstance(unit, sc.HandoffChain):
            entry = {"unit_id": unit.unit_id, "scenario": unit.scenario,
                     "hypothesis": unit.hypothesis, "failure_condition": unit.failure_condition,
                     "raw_finding": unit.raw_finding}
            a_model = route_a if getattr(unit, "replicate", 1) % 2 != 0 else route_b
            b_model = route_b if getattr(unit, "replicate", 1) % 2 != 0 else route_a
            a = runner.call(unit.unit_id, "A", sc.handoff_a_prompt(unit), model=a_model)
            entry["a_call_id"] = a["call_id"]
            a_output = a["output"] if _ok(a) else (
                sc.REFERENCE_OUTPUTS["handoff_a"] if dry_run else None)
            transformed = sc.transform_finding(unit, a_output, profile) if a_output else None
            entry["transform"] = transformed
            b = None
            if transformed and transformed["result"] == "ACCEPTED":
                b = runner.call(unit.unit_id, "B", sc.handoff_b_prompt(transformed), model=b_model)
                entry["b_call_id"] = b["call_id"]
            if dry_run:
                entry.update({"verdict": "NOT_RUN",
                              "dry_run_note": "A output is REFERENCE_OUTPUTS['handoff_a'], a "
                                              "hand-written fixture, used only to render B"})
            elif not _ok(a) or (b is not None and not _ok(b)):
                entry["verdict"] = "ERROR"
            else:
                metrics = sc.measure_handoff(a["output"], transformed, b["output"] if b else None)
                metrics.update({"route_a": _route(a), "route_b": _route(b),
                                "routes_differ": (b is not None and _route(a) != _route(b))})
                entry["metrics"] = metrics
                a_ok = not metrics["a_confidence_inflation"] and not metrics["a_evidence_invention"]
                b_ok = b is not None and grade(sc.B_SCHEMA, sc.B_EXPECT, b["output"])["pass"]
                entry["verdict"] = "PASS" if a_ok and b_ok else "FAIL"
            results.append(entry)

        elif isinstance(unit, sc.LegacyTrial):
            entry = {"unit_id": unit.unit_id, "scenario": unit.scenario,
                     "hypothesis": unit.hypothesis, "failure_condition": unit.failure_condition}
            a = runner.call(unit.unit_id, "A", sc.legacy_a_prompt(), model=route_a)
            entry["a_call_id"] = a["call_id"]
            a_output = a["output"] if _ok(a) else (
                sc.REFERENCE_OUTPUTS["legacy_a"] if dry_run else None)
            packet = sc.transform_packet(a_output) if a_output else None
            entry["packet_transform"] = packet
            arms = unit.arm_order
            calls = {}
            for arm in arms:
                if arm == "legacy":
                    if packet and packet["result"] == "ACCEPTED":
                        calls[arm] = runner.call(unit.unit_id, "B_legacy",
                                                 sc.successor_prompt(packet["packet"]),
                                                 model=route_b if unit.replicate % 2 != 0 else route_a)
                else:
                    calls[arm] = runner.call(unit.unit_id, "B_control", sc.successor_prompt(None),
                                             model=route_a if unit.replicate % 2 != 0 else route_b)
            entry["arm_order"] = list(arms)
            entry.update({f"{arm}_call_id": c["call_id"] for arm, c in calls.items()})
            if dry_run:
                entry["verdict"] = "NOT_RUN"
            else:
                measured = {"route_a": _route(a)}
                if _ok(a):
                    measured["packet"] = sc.measure_packet(a["output"])
                for arm, c in calls.items():
                    if _ok(c):
                        measured[arm] = {**sc.measure_successor(c["output"], arm),
                                         "route": _route(c)}
                entry["metrics"] = measured
                # no PASS/FAIL: a trial is a measurement, not a single verdict
                entry["verdict"] = ("MEASURED" if _ok(a) or any(_ok(c) for c in calls.values())
                                    else "ERROR")
            results.append(entry)
    return results


def estimate_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text))
    except Exception:
        return len(text.split())


def summarize(results: List[dict], calls: List[dict]) -> dict:
    """Counts and per-call listings. No vote, no majority, no merged answer."""
    live = [c for c in calls if c["status"] != "NOT_RUN"]
    routes = sorted({c["reported_model"] for c in live if c.get("reported_model")})
    distinct_route_count = len(routes)
    cross_family_measured = distinct_route_count >= 2
    opaque_accounting = []
    for c in live:
        prompt_text = c.get("prompt") or ""
        local_est = estimate_tokens(prompt_text)
        gateway_reported = c.get("usage", {}).get("prompt_tokens")
        delta = (gateway_reported - local_est) if gateway_reported is not None else None
        opaque_accounting.append({
            "call_id": c["call_id"],
            "unit_id": c["unit_id"],
            "role": c["role"],
            "route": c.get("reported_model"),
            "local_estimated_input_tokens": local_est,
            "gateway_reported_prompt_tokens": gateway_reported,
            "delta": delta,
        })
    attention = {name: 0 for name in ATTENTION_CLASSES}
    for result in results:
        for name, count in result.get("attention", {}).get("counts", {}).items():
            attention[name] = attention.get(name, 0) + count
    return {
        "verdicts": {v: sum(1 for r in results if r.get("verdict") == v)
                     for v in ("PASS", "FAIL", "MEASURED", "ERROR", "NOT_RUN")},
        "attention": attention,
        "calls_attempted": len(live),
        "calls_ok": sum(1 for c in live if c["status"] == "OK"),
        "routes_observed": routes,
        "distinct_route_count": distinct_route_count,
        "cross_family_measured": cross_family_measured,
        "context_visibility": CONTEXT_VISIBILITY,
        "route_resolution": {k: sum(1 for c in live if c.get("route_resolution") == k)
                             for k in ("ALIAS_ONLY", "MODEL_REPORTED")},
        "providers_stated_by_gateway": sorted({c["provider"] for c in live if c.get("provider")}),
        "errors": [{"unit_id": c["unit_id"], "role": c["role"],
                    "error_class": c.get("error_class"), "error": c.get("error")}
                   for c in live if c["status"] == "ERROR"],
        "opaque_context_measurements": opaque_accounting,
        "answers_by_route": _answers_by_route(results, calls),
    }


def _answers_by_route(results: List[dict], calls: List[dict]) -> Dict[str, dict]:
    """Every graded answer next to the route that gave it. Disagreement stays visible."""
    by_id = {c["call_id"]: c for c in calls}
    table: Dict[str, dict] = {}
    for result in results:
        if "grade" not in result:
            continue
        call = by_id[result["call_id"]]
        table[result["unit_id"]] = {"route": call.get("reported_model"),
                                    "answers": result["grade"]["values"],
                                    "verdict": result["verdict"]}
    return table


def assert_no_secret(serialized: str, secret: str) -> None:
    """Fail closed before writing. Model text that merely mentions a word is not a header."""
    if secret and secret in serialized:
        raise SecretLeak("an artifact would have carried the credential; nothing was written")
    if _HEADER_LINE.search(serialized):
        raise SecretLeak("an artifact would have carried an Authorization header; "
                         "nothing was written")


def select_units(units, sample: bool):
    """The declared narrow sample, or the whole plan. Never a post-hoc subset."""
    if not sample:
        return tuple(units)
    chosen = tuple(u for u in units if u.unit_id in SAMPLE_UNITS)
    missing = set(SAMPLE_UNITS) - {u.unit_id for u in chosen}
    if missing:
        raise SystemExit("the declared sample names units the plan does not build: "
                         f"{sorted(missing)}")
    return chosen


def resolve_population(transport, budget: CallBudget, combo: str = COMBO):
    """Discovery and selection, with every probe spent from the run's own budget.

    A discovery failure is recorded, never fatal: a run with no resolved
    participants sends the combo alias and claims nothing about heterogeneity.
    An authentication refusal is the exception (W2-002): it is systemic, stops
    every further network call, and is raised as :class:`AuthRefused`.
    """
    observed_at = _now()

    def catalog():
        try:
            return transport.get_json(pop.DISCOVERY_PATH)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AuthRefused(f"HTTP {exc.code} during catalog discovery") from None
            raise

    def probe(model: str) -> dict:
        try:
            budget.spend()
        except BudgetExceeded as exc:
            return {"error_class": "BudgetExceeded", "error": str(exc)[:MAX_ERROR_CHARS]}
        try:
            result = transport.probe(model)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AuthRefused(f"HTTP {exc.code} during a membership probe") from None
            return {"error_class": type(exc).__name__,
                    "error": str(exc)[:MAX_ERROR_CHARS]}
        except Exception as exc:  # noqa: BLE001 - a probe fault is data, not a crash
            return {"error_class": type(exc).__name__, "error": str(exc)[:MAX_ERROR_CHARS]}
        if result.get("http_status") in (401, 403):
            raise AuthRefused(f"HTTP {result['http_status']} during a membership probe")
        return result

    try:
        return pop.resolve_population(combo, catalog, probe, observed_at)
    except AuthRefused:
        raise
    except Exception as exc:  # noqa: BLE001 - discovery is evidence, not a gate
        return pop.offline_population(
            combo, observed_at,
            f"the discovery surface {pop.DISCOVERY_PATH} could not be read "
            f"({type(exc).__name__})")


def run(out_dir: pathlib.Path, dry_run: bool, api_key: str = "",
        transport: Optional[object] = None, max_runs: int = MAX_RUNS,
        population=None, discover: Optional[bool] = None, sample: bool = False,
        credential_source: str = SOURCE_STORE, handle: str = DEFAULT_HANDLE) -> dict:
    profile = Profile.load("1")
    units = select_units(sc.build_plan(profile), sample)
    planned = sc.planned_calls(units)
    # Discovery is the ordinary live command's own step. A caller that hands in a
    # transport hands in the world too: it says what the population is, or gets a
    # record that claims nothing.
    discovering = (transport is None and not dry_run) if discover is None else bool(discover)
    reserve = pop.DISCOVERY_RESERVE if (discovering and not dry_run) else 0
    if planned + reserve > max_runs:
        detail = (f"the plan needs {planned} calls plus a discovery reserve of {reserve}, "
                  f"over the declared cap of {max_runs}") if reserve else (
            f"the plan needs {planned} calls, over the declared cap of {max_runs}")
        if reserve:
            detail += ". Declare a larger cap with --max-runs, or run the narrow sample "
            detail += "with --sample."
        raise SystemExit(detail)
    for unit in units:
        if not unit.hypothesis.strip() or not unit.failure_condition.strip():
            raise SystemExit(f"{unit.unit_id} declares no hypothesis or failure condition")
    credential_backend = None
    built_transport = False
    if not dry_run and transport is None:
        if not api_key:
            try:
                resolved = resolve(handle=handle, source=credential_source)
            except (CredentialNotProvisioned, CredentialError) as exc:
                raise SystemExit(str(exc)) from None
            api_key, credential_backend = resolved.secret, resolved.backend
        transport = HttpTransport(api_key)
        built_transport = True
    budget = CallBudget(max_runs)
    auth_refused_note = None
    if population is None:
        want = discovering and (built_transport or discover is True)
        if want and not dry_run:
            try:
                population = resolve_population(transport, budget)
            except AuthRefused as exc:
                # systemic (W2-002): no experiment request follows a refused
                # credential; the artifact records the stop, the plan is not graded
                auth_refused_note = str(exc)
                population = pop.offline_population(
                    COMBO, _now(), f"authentication refused: {auth_refused_note}")
        else:
            population = pop.offline_population(
                COMBO, _now(),
                "a dry run makes no call" if dry_run
                else "discovery was not requested for this run")
    discovery_calls = budget.used
    runner = Runner(None if dry_run else transport.send, budget, alias=COMBO)
    if auth_refused_note:
        runner.stopped = f"AUTH_REFUSED: {auth_refused_note}"
    results = execute(units, runner, profile, dry_run, population)
    started = runner.calls[0]["timestamp"] if runner.calls else _now()
    summary = summarize(results, runner.calls)
    population_record = population.as_record()
    artifact = {
        "authority": AUTHORITY,
        "is_not": list(IS_NOT),
        "note": NOTE,
        "experiment_class": ec.classify_calls(population.combo, runner.calls, population_record),
        "context_visibility": CONTEXT_VISIBILITY,
        "distinct_route_count": summary["distinct_route_count"],
        "cross_family_measured": summary["cross_family_measured"],
        "dry_run": dry_run,
        "harness": {"gateway": "9router", "base_url": BASE_URL, "model_alias": COMBO,
                    "route_a": routes_of(population)[0], "route_b": routes_of(population)[1],
                    "protocol_version": PROTOCOL_VERSION, "max_tokens": MAX_TOKENS,
                    "timeout_s": TIMEOUT_SECONDS, "sample": sample,
                    "sample_units": list(SAMPLE_UNITS) if sample else [],
                    "transforms": [sc.HANDOFF_TRANSFORM, sc.LEGACY_TRANSFORM]},
        "credential": {"handle": handle, "source": credential_source,
                       "backend": credential_backend},
        "population": population_record,
        "started": started,
        "max_runs": max_runs,
        "planned_calls": planned,
        "live_calls": budget.used,
        "discovery_calls": discovery_calls,
        "experiment_calls": budget.used - discovery_calls,
        "stopped": runner.stopped,
        "summary": summary,
        "units": results,
        "calls": runner.calls,
    }
    serialized = json.dumps(artifact, indent=2, ensure_ascii=False)
    assert_no_secret(serialized, api_key)
    report_text = None if dry_run else render_report(artifact)
    if report_text is not None:
        assert_no_secret(report_text, api_key)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.replace("-", "").replace(":", "")
    run_id = uuid.uuid4().hex[:16]
    name = "saifren_dry_run.json" if dry_run else f"saifren_live_{stamp}_{run_id}.json"
    path = out_dir / name
    _write_immutable(path, serialized + "\n")
    written = {"artifact": str(path)}
    if report_text is not None:
        # One report per run, named by the run. A single SAIFREN_REPORT.md was
        # overwritten by the next run, which quietly deleted the evidence the
        # previous interpretation cited (D-022). The unstamped copy stays as the
        # convenience pointer at the newest one; the stamped artifacts carry a
        # unique run id so two same-second runs can never collide (W2-003).
        body = f"Source artifact: `{name}`\n\n{report_text}"
        stamped = out_dir / f"SAIFREN_REPORT_{stamp}_{run_id}.md"
        _write_immutable(stamped, body)
        latest = out_dir / "SAIFREN_REPORT.md"
        latest.write_text(body, encoding="utf-8")
        written["report"] = str(stamped)
        written["latest_report"] = str(latest)
    return {**artifact, **written}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bounded SAIFREN laboratory run. The credential is resolved from the "
                    "named handle through the local credential store; no secret is read "
                    "from the environment unless --credential-source env says so.")
    parser.add_argument("--out", default="lab/out")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-runs", type=int, default=MAX_RUNS,
                        help="declared cap on live calls for this run, discovery included "
                             "(default: %(default)s)")
    parser.add_argument("--sample", action="store_true",
                        help="run only the declared narrow validation sample "
                             f"({', '.join(SAMPLE_UNITS)})")
    parser.add_argument("--handle", default=DEFAULT_HANDLE,
                        help="logical credential handle (default: %(default)s)")
    parser.add_argument("--credential-source", choices=list(SOURCES), default=SOURCE_STORE,
                        help=f"where the credential comes from: {SOURCE_STORE!r} is the "
                             f"canonical local store; {SOURCE_ENV!r} is the explicit legacy "
                             f"mode that reads {KEY_ENV} and nothing else "
                             "(default: %(default)s)")
    args = parser.parse_args(argv)
    result = run(pathlib.Path(args.out), args.dry_run, sample=args.sample,
                 max_runs=args.max_runs, credential_source=args.credential_source,
                 handle=args.handle)
    shown = {k: result[k] for k in ("artifact", "authority", "dry_run", "planned_calls",
                                    "live_calls", "discovery_calls", "experiment_calls",
                                    "max_runs", "stopped")}
    shown["credential"] = result["credential"]
    shown["verdicts"] = result["summary"]["verdicts"]
    shown["routes_observed"] = result["summary"]["routes_observed"]
    shown["participants"] = result["population"]["participants"]
    # Every value in `shown` comes from the artifact, which run() already
    # scrubbed against the real credential before writing it. The header check
    # still runs here, on the shape rather than the value.
    printed = json.dumps(shown, indent=2)
    assert_no_secret(printed, "")
    print(printed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
