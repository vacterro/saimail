# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-063 — automatic telegrams: closed triggers, admitted recipients, one message per fact, a receiver budget (T-122)

The defect class is information that must cross an ownership boundary but waits
for a human, and its mirror image, an automatic sender that chatters, guesses its
recipient, repeats itself or sets its own urgency. SRC-108 authorized automatic
sending for a closed trigger set; SRC-107 fixed the policy.

**Decision.** `saimail-local saipen notify` (`spec/31-SAITELEMES-NOTIFY-v0.md`) is
the only automatic send path:

- trigger from the closed set, recipient and kind from the participant registry
  (D-061); no kind, priority or urgency parameter exists;
- topic is the current Work or a BOARD-listed Work, never a guess;
- a deterministic idempotency key per fact, with a citation bound to its event
  and LOG line hash rather than its time-stamped bytes;
- submission through the durable outbox (D-060); a locked store records the
  intent for later instead of losing it;
- a receiver attention budget (20 per recipient, 5 per recipient and Work, per
  rolling hour) enforced under the outbox lock; overflow is suppressed, written
  nowhere and never retried;
- each call advances other due intents, so retries need no daemon.

**Boundary.** When to call it is the SAIPEN event trigger's decision (SAIPEN
project Work). `saipen telegram` remains the manual path. No wire, index or
custody change. Checkout-only; the frozen `0.0.2a3` wheel does not contain it.

**Evidence.** `tests/test_notify.py` (10 controls); six source mutants caught
(`.saipen/evidence/T-122-notify/red-controls.txt`), including a sender-chosen kind
that an earlier, weaker control had let through.
