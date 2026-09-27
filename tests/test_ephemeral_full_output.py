"""T-74 ephemeral full-output path: RED/GREEN controls, complete-or-refuse.

Every path here runs the real ``EphemeralTransport`` (a subclass of the real
``HttpTransport``) against a fake opener, so the body-building, credential,
response-bound, scrub and reasoning-removal code under test is the code that
would run live.

RED: the generic ``HttpTransport.send`` / ``observable`` projection still caps
visible content at 4000 characters.  GREEN: the ephemeral path delivers the
complete visible content to the immediate consumer, with an exact hash, byte
count and legacy-truncation flag, and refuses (never a parsed prefix) when the
hard transport response bound is crossed.
"""

import hashlib
import io
import json

from lab import ephemeral_output as eph
from lab import saifren_run as live

KEY = "sk-EPHEMERAL-SENTINEL-7c2f4a-DO-NOT-PERSIST"
CANARY = "PRIVATE_FULL_OUTPUT_CANARY_e19b"


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
    def __init__(self, respond=None):
        self.requests = []
        self.respond = respond or (
            lambda request, n: FakeResponse(completion("ok",
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
    return eph.EphemeralTransport(KEY, opener=opener, timeout=1)


# ------------------------------------------------ RED: the generic 4000 path

def test_generic_transport_still_truncates_at_4000_red_control():
    long = "y" * 5000
    opener = Opener(lambda request, n: FakeResponse(completion(long)))
    result = live.HttpTransport(KEY, opener=opener, timeout=1).send("p")
    assert len(result["output"]) == 4000
    assert result["output_truncated"] is True


# ---------------------------------------- GREEN: the ephemeral full path

def test_ephemeral_full_path_delivers_complete_content_beyond_4000():
    long = "y" * 5000
    opener = Opener(lambda request, n: FakeResponse(completion(long)))
    result = transport(opener).send_ephemeral_full("p")
    assert result["full_output"] == long
    assert len(result["full_output"]) == 5000
    assert result["output_truncated"] is False
    assert result["legacy_projection_would_truncate"] is True
    # the generic projection is untouched on the parent result
    assert len(result["output"]) == 4000


def test_ephemeral_hash_and_byte_count_are_exact():
    long = CANARY + "z" * 5000
    opener = Opener(lambda request, n: FakeResponse(completion(long)))
    result = transport(opener).send_ephemeral_full("p")
    assert result["full_output"] == long
    assert eph.ephemeral_full_digest(result["full_output"]) == hashlib.sha256(
        long.encode("utf-8")).hexdigest()
    assert len(result["full_output"].encode("utf-8")) == len(long.encode("utf-8"))


def test_exactly_one_request_per_logical_call():
    opener = Opener()
    transport(opener).send_ephemeral_full("p")
    assert len(opener.requests) == 1


def test_request_body_is_byte_identical_to_the_generic_send():
    opener = Opener()
    ephemeral_body_holder = Opener()
    eph_transport = transport(ephemeral_body_holder)
    eph_transport.send_ephemeral_full("same prompt", model="SAIFREN", max_tokens=4096)
    live.HttpTransport(KEY, opener=opener, timeout=1).send(
        "same prompt", model="SAIFREN", max_tokens=4096)
    assert ephemeral_body_holder.requests[0].data == opener.requests[0].data
    assert ephemeral_body_holder.requests[0].get_header("Authorization") == f"Bearer {KEY}"


def test_ephemeral_path_records_the_exact_request_body_evidence():
    opener = Opener()
    result = transport(opener).send_ephemeral_full("p", model="SAIFREN", max_tokens=4096)
    wire = opener.requests[0].data
    assert result["request_body_sha256"] == hashlib.sha256(wire).hexdigest()
    assert result["request_body_bytes"] == len(wire)


# ------------------------------------------------ tail canary

def test_tail_canary_after_4000_is_observed_by_the_parser_input():
    tail = "TAIL_" + CANARY
    content = "a" * 4500 + tail
    opener = Opener(lambda request, n: FakeResponse(completion(content)))
    result = transport(opener).send_ephemeral_full("p")
    assert tail in result["full_output"]
    assert result["full_output"].endswith(tail)
    assert len(result["full_output"]) > 4000


def test_generic_projection_would_have_dropped_the_tail_canary():
    tail = "TAIL_" + CANARY
    content = "a" * 4500 + tail
    opener = Opener(lambda request, n: FakeResponse(completion(content)))
    generic = live.HttpTransport(KEY, opener=opener, timeout=1).send("p")
    assert tail not in generic["output"]


# ------------------------------------------------ COMPLETE OR REFUSE

def test_oversize_response_refuses_and_carries_no_parser_input():
    big = b"{" + b" " * (live.MAX_RESPONSE_BYTES + 10) + b"}"
    opener = Opener(lambda request, n: FakeResponse(big))
    result = transport(opener).send_ephemeral_full("p")
    assert result["error_class"] == "ResponseTooLarge"
    assert result["full_output"] is None
    assert len(opener.requests) == 1


def test_transport_error_carries_no_full_output():
    def boom(request, n):
        raise OSError("connection refused")
    opener = Opener(boom)
    result = transport(opener).send_ephemeral_full("p")
    assert result["error_class"] == "OSError"
    assert result["full_output"] is None
    assert result["legacy_projection_would_truncate"] is None


def test_malformed_response_carries_no_full_output():
    opener = Opener(lambda request, n: FakeResponse(b"{not json"))
    result = transport(opener).send_ephemeral_full("p")
    assert result["error_class"] == "MalformedResponse"
    assert result["full_output"] is None


# ------------------------------------------------ reasoning removal

def test_inline_reasoning_is_removed_before_full_extraction():
    opener = Opener(lambda request, n: FakeResponse(completion(
        "<think>private plan</think>" + "x" * 5000)))
    result = transport(opener).send_ephemeral_full("p")
    assert result["full_output"] == "x" * 5000
    assert "private plan" not in result["full_output"]
    assert result["legacy_projection_would_truncate"] is True


def test_visible_full_matches_observable_extraction_semantics():
    payload = completion("  <thinking>hidden</thinking> visible  ")
    assert eph.visible_full(payload) == live.observable(payload, {}, "SAIFREN")["output"]


# ------------------------------------------------ secret handling

def test_ephemeral_path_scrubs_the_credential():
    def respond(request, n):
        raise OSError(f"refused with Authorization: Bearer {KEY}")
    opener = Opener(respond)
    result = transport(opener).send_ephemeral_full("p")
    assert KEY not in json.dumps(result)
    assert "[REDACTED]" in result["error"]
