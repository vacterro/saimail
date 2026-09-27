# Durable outbox v0 — one logical message per idempotency key

Status: implemented in the development checkout under T-119 (SRC-108, wave
"SAITELEMES reliable autonomous delivery v1", gate V6-05). Decision: D-060.
Checkout-only; the frozen `0.0.2a3` wheel does not contain it.

## 1. Why

An automatic sender retries. SAIMAIL could not retry safely: `envelope.seal`
draws a fresh NONCE and ephemeral key on every call, the ENVELOPE_ID hashes the
exact container bytes, and the receiver deduplicates by that id (D-031). A caller
that repeated `send_message` after a crash or an unclear result therefore sealed
and delivered a second logical message. Measured before T-119: two calls, two
messages at the receiver. Nothing recorded that a send had been intended.

## 2. States

Each send is one intent file, `outbox/intents/<sha256(key)>.json`
(`SAIMAIL_OUTBOX_INTENT_1`), written atomically at every transition:

| State | Meaning | Durable content |
|---|---|---|
| `PENDING` | intent recorded, not sealed | request digest, alias, recipient seat, kind, topic, subject, created, canonical record |
| `SEALED` | sealed exactly once, not yet confirmed delivered | container and ENVELOPE_ID (also `outbox/<digest>.senv`); the plaintext record is removed |
| `DELIVERED` | recipient Post Office answered `ACCEPTED` or `DUPLICATE` | delivery status, receipt time |
| `FAILED` | terminal refusal | failure code and reason |

Rules:

- **Seal once.** A container is persisted before any delivery. Every later
  attempt replays those bytes; the receiver turns a replay into `DUPLICATE`.
  Transport is at-least-once; the observable effect is one message.
- **Key binds request.** The request digest covers alias, kind, topic and content
  (claim text and subject, or the canonical record digest). The same key with the
  same request resumes; with a different request it is `IDEMPOTENCY_KEY_CONFLICT`
  and nothing changes. The key is 1-256 printable ASCII characters without spaces
  and never travels on the wire.
- **Ciphertext at rest.** Plaintext exists only while `PENDING` (and in a
  `FAILED` intent that failed before sealing). Sealed and delivered intents hold
  only the container.
- **One lock.** Intent transitions run under one OS-backed lock
  (`outbox/intents.lock`). The OS releases it when the holding process dies, so
  an abandoned lease cannot wedge the outbox. Lock order: sender outbox, then the
  recipient's lifecycle and index locks; no path waits for an outbox lock while
  holding a mailbox lock.
- **Transient versus terminal.** `DELIVERY_TARGET_UNAVAILABLE`,
  `LIFECYCLE_LOCK_TIMEOUT`, `INDEX_LOCK_TIMEOUT` and `DELIVERY_IO_ERROR` keep the
  intent `SEALED` with `next_attempt_at` = now + 30 s x 2^(attempts-1), capped at
  one hour. Every other refusal (`QUARANTINED`, `REFUSED`,
  `RECIPIENT_IDENTITY_MISMATCH`, `RECIPIENT_UNKNOWN`, ...) is `FAILED` and is never
  retried automatically.
- **Recipient binding.** The recipient seat is recorded at intent time. If the
  alias later names another seat, sealing and delivery refuse
  `RECIPIENT_IDENTITY_MISMATCH`; sealed bytes never reach another seat.
- **Keyless delivery.** Delivering a `SEALED` intent needs no private key, so the
  secret-free header view (D-059) can drive `resume_outbox` and `outbox_status`.
  A `PENDING` intent waits for the full load (`needs_signing_key`).

## 3. Interface

Library (`saimail.outbox`): `submit_send(workspace, alias, *, key, claim |
record_path, subject, topic, kind, deliver=True)`, `resume_outbox(workspace, *,
budget=25)`, `retry_intent(workspace, key)`, `outbox_status(workspace)`,
`key_id(key)`.

CLI:

```
saimail-local outbox send   --workspace WS --to ALIAS --key KEY (--claim TEXT | --record FILE)
                            [--kind K] [--topic T] [--subject S] [--no-deliver]
saimail-local outbox resume --workspace WS [--budget N]
saimail-local outbox retry  --workspace WS --key KEY
saimail-local outbox status --workspace WS
```

Statuses: `DELIVERED`, `PENDING_RETRY` (durable, a later resume delivers; exit 0),
`FAILED` (exit 1, operator action). `outbox status` reports counts per state,
pending and retrying counts, total attempts, oldest pending age, last error class
and last delivery time; never plaintext, containers or keys.

## 4. Refusals

| Code | When |
|---|---|
| `IDEMPOTENCY_KEY_INVALID` | empty, over 256 characters, spaces, control or non-ASCII characters |
| `IDEMPOTENCY_KEY_CONFLICT` | the key already names a different request |
| `INTENT_UNKNOWN` / `INTENT_NOT_FAILED` | `retry` of a missing or non-`FAILED` intent |
| `OUTBOX_INTENT_CORRUPT` | an intent with an unknown field set, schema or state, plaintext in a sealed state, or a container that does not hash to its ENVELOPE_ID; status, resume and send refuse |
| `OUTBOX_LOCK_TIMEOUT` | the outbox lock stayed busy past its bound |
| `SIGNING_KEY_REQUIRED` | a header view was asked to seal |

## 5. Evidence

`tests/test_outbox.py`: one key is one message; a reused key with another request
changes nothing; bad keys write nothing; an offline recipient backs off (30 s,
then 60 s) and is delivered once; a quarantine is terminal until `retry`; an alias
rebound to another seat never receives the bytes; a process killed by `os._exit`
after the intent, after `SEALED`, before delivery and after delivery each resumes
to exactly one message; the outbox lock makes a second process wait; six
processes racing one key produce one message, eight racing distinct keys produce
eight; status and sealed delivery read no custody secret; tampered intents fail
closed; the CLI round trip. Red controls: `.saipen/evidence/T-119-outbox/`.

## 6. Not in v0

No daemon and no timer: `resume_outbox` runs when something calls it (the
SAITELEMES notify path, V6-08, calls it). No receiver acknowledgement beyond the
Post Office delivery result, no agent flood budget (V6-08) and no participant
registry (V6-06).
