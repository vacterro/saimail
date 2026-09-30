# T-122 SCOUT: V6-08 SAIMAIL half, automatic notify (SRC-108 item 2, SRC-107 policy)

Operator authority: automatic send for a closed trigger set only (SRC-108 answers).
SAIMAIL half = the command SAIPEN's event trigger calls; the SAIPEN trigger itself
is SAIPEN-project Work (project still held by seat astra).

Facts:
- `saipen telegram` sends through `send_message` (no idempotency) and cites an event
  with `cite_event`, whose record CREATED is the call time: the record bytes change
  per call, so an outbox digest over record bytes would call a repeat of the same
  event a key conflict.
- Registry (D-061) resolves seat+trigger to alias+kind; outbox (D-060) gives one
  message per key; capabilities (D-062) needs a notify entry.
- Policy: retain pending outbound intent when the channel is degraded; never guess
  ticket numbers; no routine chatter; sender never assigns receiver priority.

Design: `saimail/notify.py`; outbox gains `content_identity` (digest over the
stable meaning) and a `gate` run under the outbox lock only for a new intent
(budget); PENDING intents without a signing key are recorded, not failed.
Key `notify:<lineage>:<work>:<trigger>:<seat>:<event|claim digest>`; budget
20 per recipient and 5 per recipient+Work per hour, overflow NOTIFY_SUPPRESSED
(nothing written, never retried); topic = current Work or an explicit Work that
exists on BOARD; each notify piggybacks a bounded resume of due intents.
