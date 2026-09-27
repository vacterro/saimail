# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-060 — sends are durable intents keyed by an idempotency key; seal once, replay bytes (T-119)

The defect class is a send that cannot be retried safely. Sealing is randomized
and the receiver deduplicates by the ENVELOPE_ID of exact bytes (D-031), so a
caller retry after a crash or an unclear result became a second logical message.
T-119 measured it on the pre-existing path: two `send_message` calls for the same
finding left two messages at the receiver.

**Decision.** `saimail.outbox` records each send as an intent file keyed by a
caller-supplied idempotency key and moves it PENDING -> SEALED -> DELIVERED or
FAILED, each transition an atomic write (`spec/28-DURABLE-OUTBOX-v0.md`).

- **Seal once, replay bytes.** The container is persisted before any delivery and
  every retry replays it, so the receiver's existing deduplication makes delivery
  at-least-once with exactly one observable message. No exactly-once transport is
  claimed.
- **The key stays with the sender.** It binds one request digest (alias, kind,
  topic, content); reuse with another request is `IDEMPOTENCY_KEY_CONFLICT`. No
  SENV2 field is added.
- **Ciphertext at rest.** The plaintext record leaves the intent when it is sealed.
- **One OS lock** serializes transitions and dies with its process.
- **Temporary failures back off** (30 s doubling to one hour); terminal refusals
  are `FAILED` and only an explicit `retry` re-arms them. A sender cannot retry
  itself into a loop.
- **Sealed delivery is keyless,** so the D-059 header view can resume delivery
  without touching custody.

**Boundary.** Additive: `send_message`, `reply_message` and the wire are
unchanged, and `send --redeliver` still replays the `.senv` copies the outbox also
writes. No daemon, no receiver acknowledgement protocol and no flood budget in
this decision. Checkout-only; the frozen `0.0.2a3` wheel does not contain it.

**Evidence.** `tests/test_outbox.py` (24 controls, including real `os._exit`
kills at four transitions and 6/8-process races). Red controls in
`.saipen/evidence/T-119-outbox/red-controls.txt`: the pre-T-119 retry duplicates;
source mutants without the lock, re-sealing on retry, keeping plaintext, or
treating transient failures as terminal each turn their controls red.
