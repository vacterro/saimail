"""T-73 transport seam: exact outgoing bodies, one dispatch, no fallback.

Every live path here runs the real ``CapabilityTransport`` (a subclass of the
real ``HttpTransport``) against a fake opener, so the body-building and
credential-header code under test is the code that would run live.
"""

import hashlib
import io
import json
import urllib.error

import pytest

from lab import saifren_run as live
from lab import structured_output_capability as cap
from sailang.errors import SailangError

KEY = "sk-CAPABILITY-SENTINEL-9d1f2a-DO-NOT-PERSIST"
CANARY = "PRIVATE_TRANSPORT_CANARY_c40f1"


class FakeHeaders:
    def __init__(self, pairs=()):
        self._pairs = list(pairs)

    def items(self):
        return list(self._pairs)


class FakeResponse(io.BytesIO):
    def __init__(self, payload, status=200, headers=()):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        super().__init__(raw)
        self.status = status
        self.headers = FakeHeaders(headers)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def completion(content, model="SAIFREN", usage=None):
    return {"id": "gen-1", "model": model, "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}],
            "usage": usage or {"prompt_tokens": 11, "completion_tokens": 5, "total_tokens": 16}}


class Opener:
    """Records every request; ``respond(request, n)`` may raise an exception."""

    def __init__(self, respond=None):
        self.requests = []
        self.respond = respond or (
            lambda request, n: FakeResponse(completion('{"probe":"OK"}',
                                                       model=json.loads(request.data)["model"])))

    def __call__(self, request, timeout):
        self.requests.append(request)
        result = self.respond(request, len(self.requests))
        if isinstance(result, BaseException):
            raise result
        return result


def bodies(opener):
    return [json.loads(request.data.decode("utf-8")) for request in opener.requests]


def transport(opener):
    return cap.CapabilityTransport(KEY, opener=opener, timeout=1)


def registered_probe(probe_id):
    doc = json.loads(cap.REGISTRATION_PATH.read_text(encoding="utf-8"))
    return {row["probe_id"]: row for row in doc["probes"]}[probe_id]


# --------------------------------------------------------------- EXACT BODIES


def test_p1_body_is_4096_without_response_format_and_byte_identical_to_parent():
    opener = Opener()
    prompt = cap.prompt_for("BUDGET_4096")
    result = transport(opener).send_probe(prompt, model=cap.ROUTES["A"], max_tokens=4096)
    assert len(opener.requests) == 1
    body = bodies(opener)[0]
    assert body == {"model": cap.ROUTES["A"], "stream": False, "max_tokens": 4096,
                    "messages": [{"role": "user", "content": prompt}]}
    assert "response_format" not in body
    assert result["output"] == '{"probe":"OK"}'

    parent_opener = Opener()
    live.HttpTransport(KEY, opener=parent_opener, timeout=1).send(
        prompt, model=cap.ROUTES["A"], max_tokens=4096)
    assert opener.requests[0].data == parent_opener.requests[0].data
    assert opener.requests[0].get_header("Authorization") == f"Bearer {KEY}"


def test_p2_body_is_128_with_exact_json_object_format():
    opener = Opener()
    spec = registered_probe("A/JSON_OBJECT")
    transport(opener).send_probe(cap.prompt_for("JSON_OBJECT"), model=cap.ROUTES["A"],
                                 max_tokens=spec["max_tokens"],
                                 response_format=spec["response_format"])
    body = bodies(opener)[0]
    assert body["max_tokens"] == 128
    assert body["response_format"] == {"type": "json_object"}


def test_p3_body_carries_the_exact_registered_json_schema():
    opener = Opener()
    spec = registered_probe("A/JSON_SCHEMA")
    transport(opener).send_probe(cap.prompt_for("JSON_SCHEMA"), model=cap.ROUTES["A"],
                                 max_tokens=spec["max_tokens"],
                                 response_format=spec["response_format"])
    body = bodies(opener)[0]
    assert body["max_tokens"] == 128
    assert body["response_format"] == cap.JSON_SCHEMA_FORMAT
    wrapped = body["response_format"]["json_schema"]
    assert wrapped["strict"] is True
    assert wrapped["schema"]["additionalProperties"] is False
    assert wrapped["schema"]["properties"]["probe"]["enum"] == ["OK"]
    assert wrapped["schema"]["required"] == ["probe"]


def test_request_body_evidence_hash_matches_the_wire_bytes():
    opener = Opener()
    result = transport(opener).send_probe(cap.prompt_for("JSON_OBJECT"), model=cap.ROUTES["B"],
                                          max_tokens=128,
                                          response_format={"type": "json_object"})
    wire = opener.requests[0].data
    assert result["request_body_sha256"] == hashlib.sha256(wire).hexdigest()
    assert result["request_body_bytes"] == len(wire)


def test_gateway_usage_and_reported_model_are_observable():
    opener = Opener(lambda request, n: FakeResponse(
        completion('{"probe":"OK"}', model="deepseek/deepseek-v4-flash",
                   usage={"prompt_tokens": 4242, "completion_tokens": 7, "total_tokens": 4249})))
    result = transport(opener).send_probe(cap.prompt_for("JSON_OBJECT"), model=cap.ROUTES["A"],
                                          max_tokens=128,
                                          response_format={"type": "json_object"})
    assert result["reported_model"] == "deepseek/deepseek-v4-flash"
    assert result["usage"] == {"prompt_tokens": 4242, "completion_tokens": 7,
                               "total_tokens": 4249}
    assert result["finish_reason"] == "stop"


# -------------------------------------------------- ONE DISPATCH, NO FALLBACK


@pytest.mark.parametrize("status", [400, 404, 415, 422])
def test_capability_rejection_is_one_request_and_no_retry(status):
    def reject(request, n):
        raise urllib.error.HTTPError("http://127.0.0.1:20128/v1/chat/completions", status,
                                     "rejected", {}, io.BytesIO(b"unsupported"))
    opener = Opener(reject)
    result = transport(opener).send_probe(cap.prompt_for("JSON_SCHEMA"), model=cap.ROUTES["A"],
                                          max_tokens=128,
                                          response_format=cap.JSON_SCHEMA_FORMAT)
    assert len(opener.requests) == 1
    assert result["http_status"] == status
    assert result["error_class"] == "HTTPError"
    assert "response_format" in bodies(opener)[0]


def test_whole_gate_dispatches_each_probe_exactly_once_without_fallback(monkeypatch):
    doc = json.loads(cap.REGISTRATION_PATH.read_text(encoding="utf-8"))
    monkeypatch.setattr(cap, "registration", lambda *args, **kwargs: doc)

    def respond(request, n):
        body = json.loads(request.data.decode("utf-8"))
        if body.get("response_format", {}).get("type") == "json_schema":
            raise urllib.error.HTTPError(
                "http://127.0.0.1:20128/v1/chat/completions", 400, "no json_schema", {},
                io.BytesIO(b"json_schema is not supported"))
        return FakeResponse(completion('{"probe":"OK"}', model=body["model"]))
    opener = Opener(respond)
    result = cap._experiment(transport(opener), dry_run=False, started="2026-09-20T00:00:00Z")
    wire = bodies(opener)
    assert len(wire) == 6
    assert result["budget"]["dispatch_count"] == 6
    assert result["budget"]["fallbacks"] == 0
    assert "response_format" not in wire[0] and "response_format" not in wire[1]
    assert wire[2]["response_format"] == {"type": "json_object"}
    assert wire[3]["response_format"] == {"type": "json_object"}
    assert wire[4]["response_format"]["type"] == "json_schema"
    assert wire[5]["response_format"]["type"] == "json_schema"
    assert wire[4]["max_tokens"] == 128 and wire[0]["max_tokens"] == 4096
    rejected = [call for call in result["calls"] if call["status"] == cap.RESULT_REJECTED]
    assert [call["probe_id"] for call in rejected] == ["A/JSON_SCHEMA", "B/JSON_SCHEMA"]


def test_a_harness_fault_dispatches_once_then_fails_closed(monkeypatch):
    doc = json.loads(cap.REGISTRATION_PATH.read_text(encoding="utf-8"))
    monkeypatch.setattr(cap, "registration", lambda *args, **kwargs: doc)

    def boom(request, n):
        raise RuntimeError("opener exploded")
    opener = Opener(boom)
    with pytest.raises(SailangError, match="CAPABILITY_EVIDENCE_MISSING"):
        cap._experiment(transport(opener), dry_run=False, started="2026-09-20T00:00:00Z")
    assert len(opener.requests) == 1, "one dispatch, and the gate refuses the rest"


# ------------------------------------------------------------------ AUTH STOP


@pytest.mark.parametrize("status", [401, 403])
def test_auth_refusal_stops_the_experiment_after_one_request(status, monkeypatch):
    doc = json.loads(cap.REGISTRATION_PATH.read_text(encoding="utf-8"))
    monkeypatch.setattr(cap, "registration", lambda *args, **kwargs: doc)
    opener = Opener(lambda request, n: urllib.error.HTTPError(
        "http://127.0.0.1:20128/v1/chat/completions", status, "denied", {},
        io.BytesIO(b"invalid api key")))
    result = cap._experiment(transport(opener), dry_run=False, started="2026-09-20T00:00:00Z")
    assert len(opener.requests) == 1
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "AUTH_REFUSED"
    assert result["calls"][0]["status"] == cap.RESULT_AUTH_REFUSED
    assert all(call["status"] == cap.RESULT_NOT_RUN for call in result["calls"][1:])
    assert result["budget"]["network_calls"] == 1


# ------------------------------------------------------------- PRIVACY / CAP


def test_error_body_is_hashed_and_never_persisted(monkeypatch):
    doc = json.loads(cap.REGISTRATION_PATH.read_text(encoding="utf-8"))
    monkeypatch.setattr(cap, "registration", lambda *args, **kwargs: doc)

    def reject(request, n):
        raise urllib.error.HTTPError(
            "http://127.0.0.1:20128/v1/chat/completions", 400, "bad", {},
            io.BytesIO(('{"error":{"message":"unsupported ' + CANARY
                        + '","request_id":"req_' + CANARY + '"}').encode("utf-8")))
    result = cap._experiment(transport(Opener(reject)), dry_run=False,
                             started="2026-09-20T00:00:00Z")
    serialized = json.dumps(result)
    assert CANARY not in serialized
    first = result["calls"][0]
    assert first["error_class"] == "HTTPError"
    assert first["error_bytes"] > 0
    assert len(first["error_sha256"]) == 64
    assert KEY not in serialized


def test_visible_output_beyond_4000_characters_is_flagged_not_passed(monkeypatch):
    doc = json.loads(cap.REGISTRATION_PATH.read_text(encoding="utf-8"))
    monkeypatch.setattr(cap, "registration", lambda *args, **kwargs: doc)
    opener = Opener(lambda request, n: FakeResponse(
        completion("y" * 5000, model=json.loads(request.data)["model"])))
    result = cap._experiment(transport(opener), dry_run=False, started="2026-09-20T00:00:00Z")
    assert all(call["output_bytes"] == live.MAX_OUTPUT_CHARS for call in result["calls"])
    assert all(call["output_truncated"] is True for call in result["calls"])
    assert all(call["output_conformed"] is False for call in result["calls"])
    assert result["local_output_cap_chars"] == 4000


def test_inline_reasoning_is_removed_before_conformance_check():
    opener = Opener(lambda request, n: FakeResponse(completion(
        "<think>private plan</think>" + '{"probe":"OK"}',
        model=json.loads(request.data)["model"])))
    result = transport(opener).send_probe(cap.prompt_for("JSON_OBJECT"), model=cap.ROUTES["A"],
                                          max_tokens=128,
                                          response_format={"type": "json_object"})
    assert result["output"] == '{"probe":"OK"}'
    assert result["inline_trace_removed"] is True
