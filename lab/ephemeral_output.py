"""LAB-only ephemeral full-visible-output transport (T-74).

    EPHEMERAL FULL OUTPUT != DURABLE OUTPUT STORAGE

The defect class this module closes: the generic LAB transport projects
``output = content[:4000]`` before the strict parser sees it, so a completion
that is complete at the provider can still become locally truncated.  That
replaces a remote completion limit with a local character limit -- one confound
for another.  This module removes the local confound **for the immediate
experiment parser only**, without weakening durable privacy.

Reuse, not a second HTTP stack (handoff B1).  Every wire concern stays in
``lab/saifren_run.py``: this is a thin subclass whose ``send_ephemeral_full``
runs the parent's unchanged ``send`` exactly once (body building, credential
header, timeout, response-size bound, HTTP error handling, scrubbing,
reported-model extraction, usage extraction, finish_reason handling all shared),
capturing the exact dispatched request bytes and the raw response bytes so the
*complete* visible content can be re-extracted after the historical projection.

The generic path is untouched: ``HttpTransport.send`` and ``observable`` keep
their historical 4000-character behaviour byte for byte, and old callers and
tests are unchanged.  A full visible completion that cannot be represented
within the registered hard response bound returns the parent's named transport
refusal -- never a parsed prefix:

    COMPLETE OR REFUSE -- never TRUNCATE AND PARSE.

The ephemeral full output lives only in the returned mapping for the length of
one stage.  It is never a durable field.  In-process ephemerality is not
cryptographic memory erasure: the guarantee is NO DURABLE PLAINTEXT PERSISTENCE,
not ZERO RAM RESIDENCE.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from lab import saifren_run as live

LEGACY_OUTPUT_CHARS = live.MAX_OUTPUT_CHARS  # 4000; imported, never re-declared


class _CaptureResponse:
    """Transparent response proxy: records exact bytes the parent reads."""

    def __init__(self, inner, sink: list) -> None:
        self._inner = inner
        self._sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self._inner.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    @property
    def status(self):
        return getattr(self._inner, "status", None)

    @property
    def headers(self):
        return getattr(self._inner, "headers", None)

    def read(self, *args):
        chunk = self._inner.read(*args)
        if isinstance(chunk, (bytes, bytearray)):
            self._sink.append(bytes(chunk))
        return chunk


class _CapturingOpener:
    """Records the exact outgoing body and the exact incoming bytes, once."""

    def __init__(self, inner, bodies: list, chunks: list) -> None:
        self.inner = inner
        self._bodies = bodies
        self._chunks = chunks

    def __call__(self, request, timeout):
        data = getattr(request, "data", None)
        if isinstance(data, (bytes, bytearray)):
            self._bodies.append(bytes(data))
        return _CaptureResponse(self.inner(request, timeout), self._chunks)


def visible_full(payload: dict) -> str:
    """The entire assistant-visible text, after reasoning removal, uncapped.

    This is ``lab.saifren_run.observable``'s content extraction with the same
    inline-reasoning removal semantics and WITHOUT the historical 4000-character
    projection.  It is the definition of FULL_VISIBLE_OUTPUT used by the
    ephemeral capture: not the raw body, not hidden reasoning fields.
    """
    choices = payload.get("choices")
    first = (choices[0] if isinstance(choices, list) and choices
             and isinstance(choices[0], dict) else {})
    message = first.get("message") if isinstance(first.get("message"), dict) else {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and part.get("type") in (None, "text")
            and isinstance(part.get("text"), str))
    content = content if isinstance(content, str) else ""
    content = live._INLINE_REASONING.sub("", content)
    content = live._UNCLOSED_REASONING.sub("", content).strip()
    return content


def _parse_payload(raw: bytes):
    """Decode one response body exactly as the parent transport does."""
    raw_text = raw.decode("utf-8", "replace").strip()
    if raw_text.endswith("data: [DONE]"):
        raw_text = raw_text[:-len("data: [DONE]")].strip()
    try:
        payload = json.loads(raw_text)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


class EphemeralTransport(live.HttpTransport):
    """The real HttpTransport plus one full-visible-output read path.

    ``send_ephemeral_full`` dispatches exactly one request through the parent's
    unchanged ``send`` and then re-extracts the complete visible content from the
    same response bytes.  All transport facts (status, usage, reported model,
    finish_reason, error classification, scrubbing) come from the parent result;
    only the parser-input projection differs.
    """

    def send_ephemeral_full(self, prompt: str, model: str | None = None,
                            max_tokens: int = live.MAX_TOKENS) -> dict:
        bodies: list = []
        chunks: list = []
        watch = _CapturingOpener(self._opener, bodies, chunks)
        self._opener = watch
        try:
            result = live.HttpTransport.send(
                self, prompt, model=model, max_tokens=max_tokens)
        finally:
            self._opener = watch.inner
        result = dict(result)
        if bodies and len(bodies) != 1:
            raise live.SecretLeak("the ephemeral path dispatched more than one request")
        if bodies:
            result["request_body_sha256"] = hashlib.sha256(bodies[0]).hexdigest()
            result["request_body_bytes"] = len(bodies[0])
        else:
            result["request_body_sha256"] = None
            result["request_body_bytes"] = None
        result["full_output"] = None
        result["output_truncated"] = None
        result["legacy_projection_would_truncate"] = None
        if result.get("error_class"):
            # COMPLETE OR REFUSE: an error (including ResponseTooLarge) carries
            # no parser input at all; the parent already refused, never a prefix.
            return result
        payload = _parse_payload(b"".join(chunks)) if chunks else None
        if payload is None:
            return result
        full = visible_full(payload)
        result["full_output"] = full
        result["output_truncated"] = False
        result["legacy_projection_would_truncate"] = len(full) > LEGACY_OUTPUT_CHARS
        return result


def ephemeral_full_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
