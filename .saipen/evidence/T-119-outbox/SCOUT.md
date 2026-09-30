# T-119 SCOUT: SAITELEMES reliable autonomous delivery v1 (SRC-108)

Operator decisions (SRC-108): order 1 -> 3 -> 4 -> 5 -> 2; SAIPEN code changes as
separate Work in the SAIPEN project; automatic send authorized for a closed trigger set.

## Constraint found at SCOUT

SAIPEN project: T-1505 DOING, owner astra, claimed 2026-09-24T06:16Z (live foreign
claim, goal execution). SAIPEN-side items (1 consumer fixes + reverify livelock,
5 SAIPEN half, 2 SAIPEN half) wait until that project is free; no foreign claim is
taken. SAIMAIL-side items proceed: 3 (this ticket), 4, 5 (SAIMAIL half), 2 (SAIMAIL half).

## Send path today (saimail/workspace.py)

`send_message` -> `_seal_deliver`: `envelope.seal` (random NONCE + ephemeral key),
`ENVELOPE_ID` = hash of exact container bytes, `_store_outbox` atomic copy,
`office.deliver(container)`. Receiver dedup (D-031) is by ENVELOPE_ID of exact bytes:
an exact replay is DUPLICATE; a re-seal is a NEW logical message. No durable intent,
no idempotency key: a caller retry after a crash can create a second logical message.

## Delivery outcomes

Success: ACCEPTED, DUPLICATE. Terminal: QUARANTINED (auth/addressing; receiver-owned),
REFUSED (oversize), RECIPIENT_IDENTITY_MISMATCH, RECIPIENT_UNKNOWN, OUTBOX_CONFLICT,
ENVELOPE_ID_CONFLICT, RECEIPT_CORRUPT. Transient: DELIVERY_TARGET_UNAVAILABLE,
LIFECYCLE_LOCK_TIMEOUT, INDEX_LOCK_TIMEOUT, OSError.

## Reuse

`postoffice._OsFileLock` (OS lock, released on process death: no stale leases),
`workspace._atomic_write_bytes`, `_canonical_json_bytes`, `_resolve_recipient`,
`_build_content_record`, `_recipient_office`, `_store_outbox`, `command_result`,
header view `load_workspace_headers` for keyless status.

## Design (T-119)

Intent file per idempotency key (`outbox/intents/<sha256(key)>.json`), states
PENDING -> SEALED -> DELIVERED | FAILED; request digest binds the key to one request
(different request -> IDEMPOTENCY_KEY_CONFLICT); seal once and persist the container
atomically before delivery; retry = replay exact bytes; plaintext dropped at SEALED;
one outbox OS lock; transient -> backoff, terminal -> FAILED, explicit retry re-arms.
Crash matrix by real process kill at each transition.
