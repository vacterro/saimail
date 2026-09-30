"""Durable SAIMAIL outbox: send intents that survive crashes and retries (V6-05, T-119).

Defect class this module eliminates: a send that cannot be retried safely.
Sealing is randomized (a fresh NONCE and ephemeral key per call) and the receiver
deduplicates by the ENVELOPE_ID of the exact container bytes (D-031). A caller
that retried ``send_message`` after a crash or an unclear result therefore sealed
a NEW logical message, and an automatic sender would turn every retry into a
duplicate. Nothing recorded that a send had been intended before it happened.

The outbox keys every send by a caller-supplied idempotency key and moves it
through durable states, each written atomically before the next step starts:

    PENDING    the intent: request digest, recipient, header fields and the
               canonical record, recorded before anything is sealed.
    SEALED     sealed exactly once; the container is stored in the intent and
               in ``outbox/<digest>.senv`` before any delivery. The plaintext
               record leaves the intent here, so only ciphertext stays at rest.
    DELIVERED  the recipient Post Office answered ACCEPTED or DUPLICATE.
    FAILED     a terminal refusal (quarantine, identity change, unknown alias).
               It is never retried automatically; ``retry_intent`` re-arms it.

A crash at any point resumes from disk: PENDING seals once, SEALED replays the
same bytes, DELIVERED is a no-op. Transport is at-least-once and the observable
effect is one message, because every replay of the same bytes is the receiver's
DUPLICATE. The key never travels on the wire; no SENV2 field is added.

One OS-backed outbox lock serializes intent transitions. The OS releases it
when a process dies, so an abandoned lease cannot wedge the outbox. Temporary
delivery failures back off deterministically; delivering an already sealed
intent needs no private key, so a secret-free header view can drive it.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey

from sailang import SailangError
from sailang import parse as parse_record
from saimail import envelope, postoffice
from saimail import workspace as _workspace

OUTBOX_INTENT_SCHEMA = "SAIMAIL_OUTBOX_INTENT_1"
OUTBOX_INTENT_VERSION = 1
INTENTS_DIR = "intents"
LOCK_NAME = "intents.lock"

PENDING = "PENDING"
SEALED = "SEALED"
DELIVERED = "DELIVERED"
FAILED = "FAILED"
STATES = (PENDING, SEALED, DELIVERED, FAILED)

#: Command statuses. PENDING_RETRY means the intent is durable and will be
#: delivered by a later ``resume_outbox``; it is not an error.
PENDING_RETRY = "PENDING_RETRY"

IDEMPOTENCY_KEY_INVALID = "IDEMPOTENCY_KEY_INVALID"
IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
INTENT_UNKNOWN = "INTENT_UNKNOWN"
INTENT_NOT_FAILED = "INTENT_NOT_FAILED"
OUTBOX_INTENT_CORRUPT = "OUTBOX_INTENT_CORRUPT"
OUTBOX_LOCK_TIMEOUT = "OUTBOX_LOCK_TIMEOUT"
SIGNING_KEY_REQUIRED = "SIGNING_KEY_REQUIRED"
DELIVERY_IO_ERROR = "DELIVERY_IO_ERROR"

#: Failures a later attempt can cure without anyone acting: the recipient root
#: is offline or its mailbox locks are busy. Every other refusal is terminal.
TRANSIENT_CODES = frozenset({
    _workspace.DELIVERY_TARGET_UNAVAILABLE,
    postoffice.LIFECYCLE_LOCK_TIMEOUT,
    "INDEX_LOCK_TIMEOUT",
    DELIVERY_IO_ERROR,
})

OPERATOR_ACTION_CODES = frozenset({
    IDEMPOTENCY_KEY_INVALID, IDEMPOTENCY_KEY_CONFLICT, INTENT_UNKNOWN,
    INTENT_NOT_FAILED, OUTBOX_INTENT_CORRUPT, SIGNING_KEY_REQUIRED,
})

BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 3600
DEFAULT_RESUME_BUDGET = 25
STATUS_LIST_LIMIT = 20

_KEY_RE = re.compile(r"^[\x21-\x7e]{1,256}$")
_FIELDS = frozenset({
    "schema", "version", "key", "key_id", "request_digest", "alias",
    "recipient_seat", "kind", "topic", "subject", "created", "state", "record",
    "envelope_id", "container", "recorded_at", "sealed_at", "attempts",
    "last_attempt_at", "next_attempt_at", "last_error", "delivery_status",
    "received_at", "delivered_at", "failure", "failure_reason", "failed_at",
})


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def key_id(key: str) -> str:
    """The on-disk identity of one idempotency key."""
    if not isinstance(key, str) or not _KEY_RE.match(key):
        _reject(IDEMPOTENCY_KEY_INVALID,
                "an idempotency key is 1-256 printable ASCII characters without spaces")
    return _sha256(key.encode("ascii"))


def _outbox_root(workspace) -> Path:
    return Path(workspace.root) / _workspace.OUTBOX_DIR


def _intent_path(workspace, intent_key_id: str) -> Path:
    return _outbox_root(workspace) / INTENTS_DIR / (intent_key_id.split(":", 1)[1] + ".json")


def _lock(workspace) -> postoffice._OsFileLock:
    return postoffice._OsFileLock(_outbox_root(workspace) / LOCK_NAME,
                                  busy_code=OUTBOX_LOCK_TIMEOUT)


def _write(workspace, intent: dict) -> None:
    _workspace._atomic_write_bytes(_intent_path(workspace, intent["key_id"]),
                                   _workspace._canonical_json_bytes(intent))


def _check_intent(intent, *, path: Path) -> dict:
    """Fail closed on any intent that is not exactly what this module writes."""
    def corrupt(why: str) -> None:
        _reject(OUTBOX_INTENT_CORRUPT, f"outbox intent {path.name} {why}")

    if not isinstance(intent, dict) or set(intent) != _FIELDS:
        corrupt("has an unexpected field set")
    if (intent["schema"] != OUTBOX_INTENT_SCHEMA
            or intent["version"] != OUTBOX_INTENT_VERSION):
        corrupt("declares an unknown schema or version")
    if intent["state"] not in STATES:
        corrupt(f"has unknown state {intent['state']!r}")
    if key_id(intent["key"]) != intent["key_id"] or not path.name.startswith(
            intent["key_id"].split(":", 1)[1]):
        corrupt("does not belong to its idempotency key")
    if not isinstance(intent["attempts"], int) or intent["attempts"] < 0:
        corrupt("has a bad attempt count")
    sealed = intent["container"] is not None
    if intent["state"] == PENDING and (sealed or not isinstance(intent["record"], str)):
        corrupt("is PENDING without exactly one unsealed record")
    if intent["state"] in (SEALED, DELIVERED) and (not sealed or intent["record"] is not None):
        corrupt("is sealed but carries plaintext or no container")
    if sealed and envelope.envelope_id(intent["container"]) != intent["envelope_id"]:
        corrupt("stores a container that does not hash to its ENVELOPE_ID")
    return intent


def _read(workspace, intent_key_id: str):
    path = _intent_path(workspace, intent_key_id)
    if not path.is_file():
        return None
    try:
        intent = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _reject(OUTBOX_INTENT_CORRUPT, f"outbox intent {path.name} is unreadable: {exc}")
    return _check_intent(intent, path=path)


def _all_intents(workspace) -> list:
    folder = _outbox_root(workspace) / INTENTS_DIR
    if not folder.is_dir():
        return []
    intents = []
    for path in sorted(folder.glob("*.json")):
        try:
            intent = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            _reject(OUTBOX_INTENT_CORRUPT, f"outbox intent {path.name} is unreadable: {exc}")
        intents.append(_check_intent(intent, path=path))
    intents.sort(key=lambda item: (item["recorded_at"], item["key_id"]))
    return intents


def _now(clock) -> str:
    return (clock or postoffice.utc_now)()


def _due(intent: dict, now: str) -> bool:
    return intent["next_attempt_at"] is None or intent["next_attempt_at"] <= now


def _backoff_until(now: str, attempts: int) -> str:
    seconds = min(BACKOFF_BASE_SECONDS * 2 ** max(attempts - 1, 0), BACKOFF_MAX_SECONDS)
    instant = postoffice._parse_utc(now, code="BAD_CLOCK") + timedelta(seconds=seconds)
    return postoffice._format_utc(instant)


def _fail(intent: dict, now: str, code: str, reason=None) -> None:
    intent.update(state=FAILED, failure=code, failure_reason=reason, failed_at=now,
                  next_attempt_at=None)


def _request(workspace, alias: str, *, claim, record_path, subject: str, topic: str,
             kind: str, created: str) -> tuple:
    """Validate one send request and return its digest and canonical record.

    The digest binds the key to what the caller asked for (alias, header fields,
    content) and not to the current peer registry, so resubmitting a delivered
    intent answers from disk even after the alias changed.
    """
    if kind not in envelope.KINDS:
        _reject(_workspace.BAD_INPUT, f"kind must be one of the closed SENV2 set, got {kind!r}")
    if not isinstance(topic, str) or not envelope._TOPIC_RE.match(topic):
        _reject(_workspace.BAD_INPUT, "topic is one token of letters, digits, dot, dash "
                "or underscore")
    if (claim is None) == (record_path is None):
        _reject(_workspace.BAD_INPUT, "provide exactly one of claim text or a canonical record file")
    if not isinstance(alias, str) or not alias:
        _reject(_workspace.BAD_INPUT, "a recipient alias is required")
    record = _workspace._build_content_record(workspace, claim=claim, record_path=record_path,
                                              subject=subject, created=created)
    if claim is not None:
        content = {"form": "claim", "claim": claim.strip(), "subject": subject}
    else:
        content = {"form": "record", "record": _sha256(record.canonical_bytes())}
    request = {"alias": alias, "kind": kind, "topic": topic, "content": content}
    digest = _sha256(json.dumps(request, sort_keys=True, separators=(",", ":"),
                                ensure_ascii=False).encode("utf-8"))
    return digest, record.canonical_bytes().decode("utf-8")


def _seal(workspace, intent: dict, now: str) -> None:
    """PENDING -> SEALED, or FAILED when the request can no longer be sealed."""
    if getattr(workspace, "sender_private_key", None) is None:
        _reject(SIGNING_KEY_REQUIRED, "sealing a pending intent needs the full workspace load")
    try:
        recipient = _workspace._resolve_recipient(workspace, intent["alias"])
        if recipient["seat"] != intent["recipient_seat"]:
            _reject(_workspace.RECIPIENT_IDENTITY_MISMATCH,
                    f"alias {intent['alias']} now names seat {recipient['seat']}, "
                    f"not {intent['recipient_seat']}")
        container = envelope.seal(
            parse_record(intent["record"].encode("utf-8")).canonical_bytes(),
            sender_private_key=workspace.sender_private_key, sender_seat=workspace.seat,
            recipient_seat=recipient["seat"],
            recipient_public_key=X25519PublicKey.from_public_bytes(
                bytes.fromhex(recipient["recipient_public_key"])),
            kind=intent["kind"], topic=intent["topic"], created=intent["created"])
    except SailangError as exc:
        _fail(intent, now, exc.code)
        _write(workspace, intent)
        return
    intent.update(state=SEALED, record=None, container=container,
                  envelope_id=envelope.envelope_id(container), sealed_at=now)
    _write(workspace, intent)
    _workspace._store_outbox(workspace, intent["envelope_id"], container)


def _deliver(workspace, intent: dict, now: str, clock) -> None:
    """One delivery attempt of the stored bytes: SEALED -> DELIVERED | FAILED | SEALED."""
    if not _workspace._outbox_path(workspace, intent["envelope_id"]).is_file():
        _workspace._store_outbox(workspace, intent["envelope_id"], intent["container"])
    intent["attempts"] += 1
    intent["last_attempt_at"] = now
    try:
        recipient = _workspace._resolve_recipient(workspace, intent["alias"])
        if recipient["seat"] != intent["recipient_seat"]:
            _reject(_workspace.RECIPIENT_IDENTITY_MISMATCH,
                    f"alias {intent['alias']} now names seat {recipient['seat']}")
        office = _workspace._recipient_office(recipient, clock=clock or postoffice.utc_now)
        delivery = office.deliver(intent["container"])
    except SailangError as exc:
        if exc.code in TRANSIENT_CODES:
            intent.update(last_error=exc.code,
                          next_attempt_at=_backoff_until(now, intent["attempts"]))
        else:
            _fail(intent, now, exc.code)
        _write(workspace, intent)
        return
    except OSError:
        intent.update(last_error=DELIVERY_IO_ERROR,
                      next_attempt_at=_backoff_until(now, intent["attempts"]))
        _write(workspace, intent)
        return
    if delivery.status in (postoffice.ACCEPTED, postoffice.DUPLICATE):
        intent.update(state=DELIVERED, delivery_status=delivery.status,
                      received_at=delivery.received_at, delivered_at=now,
                      last_error=None, next_attempt_at=None)
    else:
        _fail(intent, now, delivery.status, delivery.reason)
    _write(workspace, intent)


def _advance(workspace, intent: dict, clock, *, force: bool = False,
             deliver: bool = True) -> None:
    now = _now(clock)
    if intent["state"] == PENDING:
        _seal(workspace, intent, now)
    if deliver and intent["state"] == SEALED and (force or _due(intent, now)):
        _deliver(workspace, intent, now, clock)


def _view(intent: dict) -> dict:
    """The bounded public projection of one intent: never plaintext or container."""
    return {name: intent[name] for name in (
        "key", "key_id", "state", "alias", "recipient_seat", "kind", "topic",
        "envelope_id", "recorded_at", "sealed_at", "attempts", "last_attempt_at",
        "next_attempt_at", "last_error", "delivery_status", "received_at",
        "delivered_at", "failure", "failure_reason", "failed_at")}


def _status_for(intent: dict) -> str:
    return {DELIVERED: DELIVERED, FAILED: FAILED}.get(intent["state"], PENDING_RETRY)


def _intent_result(command: str, workspace, intent: dict, detail: str) -> dict:
    result = _workspace.command_result(command, _status_for(intent), workspace=workspace,
                                       intent=_view(intent), detail=detail)
    if intent["state"] == FAILED:
        result["ok"] = False
        result["operator_action_required"] = True
    return result


def submit_send(workspace, alias: str, *, key: str, claim=None, record_path=None,
                subject: str = _workspace.DEFAULT_SUBJECT,
                topic: str = _workspace.DEFAULT_TOPIC, kind: str = _workspace.DEFAULT_KIND,
                deliver: bool = True, clock=None) -> dict:
    """Record one send under an idempotency key, then seal and deliver it once.

    Submitting the same key again with the same request resumes that intent and
    never creates a second logical message; the same key with a different
    request is ``IDEMPOTENCY_KEY_CONFLICT`` and changes nothing. ``deliver=False``
    seals without delivering, leaving the bytes for a later ``resume_outbox``.
    """
    intent_key_id = key_id(key)
    with _lock(workspace):
        now = _now(clock)
        digest, record = _request(
            workspace, alias, claim=claim, record_path=record_path, subject=subject,
            topic=topic, kind=kind, created=now)
        intent = _read(workspace, intent_key_id)
        if intent is None:
            recipient = _workspace._resolve_recipient(workspace, alias)
            intent = {name: None for name in _FIELDS}
            intent.update(schema=OUTBOX_INTENT_SCHEMA, version=OUTBOX_INTENT_VERSION,
                          key=key, key_id=intent_key_id, request_digest=digest,
                          alias=alias, recipient_seat=recipient["seat"], kind=kind,
                          topic=topic, subject=subject, created=now, state=PENDING,
                          record=record, recorded_at=now, attempts=0)
            _write(workspace, intent)
            fresh = True
        elif intent["request_digest"] != digest:
            _reject(IDEMPOTENCY_KEY_CONFLICT,
                    f"idempotency key {key!r} already names a different request")
        else:
            fresh = False
        _advance(workspace, intent, clock, deliver=deliver)
    detail = ("new intent" if fresh else "existing intent resumed; no second message") + (
        f"; state {intent['state']}")
    return _intent_result("outbox-send", workspace, intent, detail)


def resume_outbox(workspace, *, budget: int = DEFAULT_RESUME_BUDGET, clock=None) -> dict:
    """Advance due PENDING and SEALED intents, oldest first, within one budget.

    A secret-free header view can deliver SEALED intents; PENDING intents need
    the full load to seal and are counted as waiting for it.
    """
    if not isinstance(budget, int) or isinstance(budget, bool) or budget < 1:
        _reject(_workspace.BAD_INPUT, "budget is a positive integer")
    can_seal = getattr(workspace, "sender_private_key", None) is not None
    counts = {"examined": 0, DELIVERED: 0, FAILED: 0, PENDING_RETRY: 0,
              "not_due": 0, "needs_signing_key": 0}
    touched = []
    with _lock(workspace):
        now = _now(clock)
        for intent in _all_intents(workspace):
            if counts["examined"] >= budget:
                break
            if intent["state"] in (DELIVERED, FAILED):
                continue
            if intent["state"] == PENDING and not can_seal:
                counts["needs_signing_key"] += 1
                continue
            if intent["state"] == SEALED and not _due(intent, now):
                counts["not_due"] += 1
                continue
            counts["examined"] += 1
            _advance(workspace, intent, clock)
            counts[_status_for(intent)] += 1
            touched.append(_view(intent))
    return _workspace.command_result(
        "outbox-resume", "OK", workspace=workspace, counts=counts, items=touched,
        detail=f"{counts['examined']} intent(s) advanced; nothing is sent twice")


def retry_intent(workspace, key: str, *, clock=None) -> dict:
    """Explicitly re-arm one FAILED intent and attempt it once more."""
    intent_key_id = key_id(key)
    with _lock(workspace):
        intent = _read(workspace, intent_key_id)
        if intent is None:
            _reject(INTENT_UNKNOWN, f"no outbox intent for idempotency key {key!r}")
        if intent["state"] != FAILED:
            _reject(INTENT_NOT_FAILED, f"intent is {intent['state']}; only FAILED is re-armed")
        intent.update(state=SEALED if intent["container"] is not None else PENDING,
                      failure=None, failure_reason=None, failed_at=None,
                      next_attempt_at=None)
        _write(workspace, intent)
        _advance(workspace, intent, clock, force=True)
    return _intent_result("outbox-retry", workspace, intent,
                          f"re-armed by operator; state {intent['state']}")


def outbox_status(workspace, *, clock=None) -> dict:
    """Keyless, plaintext-free outbox health for one workspace (header view is enough)."""
    intents = _all_intents(workspace)
    now = postoffice._parse_utc(_now(clock), code="BAD_CLOCK")
    by_state = {state: 0 for state in STATES}
    for intent in intents:
        by_state[intent["state"]] += 1
    open_intents = [item for item in intents if item["state"] in (PENDING, SEALED)]
    oldest = None
    if open_intents:
        first = postoffice._parse_utc(open_intents[0]["recorded_at"], code="BAD_CLOCK")
        oldest = int((now - first).total_seconds())
    attempted = [item for item in intents if item["last_attempt_at"]]
    latest = max(attempted, key=lambda item: item["last_attempt_at"], default=None)
    delivered = [item["delivered_at"] for item in intents if item["delivered_at"]]
    return _workspace.command_result(
        "outbox-status", "OK", workspace=workspace,
        outbox={
            "schema": OUTBOX_INTENT_SCHEMA, "counts": by_state,
            "pending": len(open_intents),
            "retrying": sum(1 for item in open_intents if item["attempts"] > 0),
            "attempts": sum(item["attempts"] for item in intents),
            "oldest_pending_seconds": oldest,
            "last_error": latest["last_error"] if latest else None,
            "last_delivered_at": max(delivered) if delivered else None,
            "open": [_view(item) for item in open_intents[:STATUS_LIST_LIMIT]],
            "failed": [_view(item) for item in intents
                       if item["state"] == FAILED][:STATUS_LIST_LIMIT],
        },
        detail=f"{len(open_intents)} pending, {by_state[FAILED]} failed; metadata only")


__all__ = [
    "BACKOFF_BASE_SECONDS",
    "BACKOFF_MAX_SECONDS",
    "DEFAULT_RESUME_BUDGET",
    "DELIVERED",
    "DELIVERY_IO_ERROR",
    "FAILED",
    "IDEMPOTENCY_KEY_CONFLICT",
    "IDEMPOTENCY_KEY_INVALID",
    "INTENT_NOT_FAILED",
    "INTENT_UNKNOWN",
    "OPERATOR_ACTION_CODES",
    "OUTBOX_INTENT_CORRUPT",
    "OUTBOX_INTENT_SCHEMA",
    "OUTBOX_LOCK_TIMEOUT",
    "PENDING",
    "PENDING_RETRY",
    "SEALED",
    "SIGNING_KEY_REQUIRED",
    "TRANSIENT_CODES",
    "key_id",
    "outbox_status",
    "resume_outbox",
    "retry_intent",
    "submit_send",
]
