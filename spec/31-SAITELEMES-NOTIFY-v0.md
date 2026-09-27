# SAITELEMES notify v0 — automatic telegrams for a closed trigger set

Status: SAIMAIL half implemented in the development checkout under T-122 (SRC-108
wave item 2, gate V6-08). Decision: D-063. The SAIPEN half (the event trigger that
decides when to call this) is SAIPEN-project Work. Checkout-only.

## 1. Why

Information that must cross an ownership boundary waited for a human relay
(T-108 measured it). The operator authorized automatic sending (SRC-108) only for
a closed trigger set and under a policy (SRC-107): resolve the recipient from the
admitted participant registry, bind the message to a real Work, create a
deterministic idempotency key, write the intent durably before delivery, send no
chatter, and never let the sender set the receiver's priority.

## 2. Command

```
saimail-local saipen notify --workspace WS --trigger T --to SEAT (--claim TEXT | --event E-###)
                            [--work T-###] [--seat ACTING] [--project-root P] [--json]
```

Library: `saimail.notify.notify(workspace, *, lineage, work, trigger, to_seat,
claim | citation+event)`.

## 3. Rules

- **Admitted recipient only.** The trigger (`blocker`, `finding`, `dependency`,
  `ownership`, `handoff`, `reply`) and seat resolve through the participant
  registry (D-061); the kind is the trigger's fixed SENV2 kind. The command has no
  kind, priority or urgency parameter.
- **A real Work.** The topic and subject are the current Work (`STATE.task`) or an
  explicit `--work` that the project's BOARD lists. No Work: `NOTIFY_NO_WORK`;
  unlisted: `NOTIFY_WORK_UNKNOWN`.
- **One fact, one message.** Key
  `notify:<lineage>:<work>:<trigger>:<seat>:<event id | c + 24 hex of sha256(claim)>`.
  A citation's digest binds the event id and its `EV` (the LOG line hash), not
  the record bytes, whose CREATED changes per call.
- **Durable first.** Submission goes through the durable outbox (D-060). Without a
  readable signing key (a locked store) the intent is recorded PENDING from the
  secret-free view and a later full load seals and delivers it.
- **Receiver attention budget.** Per recipient per rolling hour: 20
  notifications, and 5 per Work. The check runs under the outbox lock for a new
  intent only; a repeat of a recorded fact is never counted. Over budget the
  result is `NOTIFY_SUPPRESSED` (exit 0, nothing written, never retried).
- **Retries without a daemon.** Each notify advances up to 10 other due intents.
- **Inert body.** The body is a one-line claim or the S2 citation of one event;
  command-looking text is delivered and opened as data.

## 4. Results

`DELIVERED`, `PENDING_RETRY`, `FAILED` (from the outbox), `NOTIFY_SUPPRESSED`,
plus refusals from admission (`SAIPEN_SEAT_MISMATCH`, `SAIPEN_ADMISSION_REQUIRED`),
the registry (`PARTICIPANT_*`, `BAD_TRIGGER`) and `NOTIFY_NO_WORK` /
`NOTIFY_WORK_UNKNOWN`. The `notify` block names trigger, recipient seat, alias,
kind, Work and key; `resumed` counts the piggybacked retries.

## 5. Evidence

`tests/test_notify.py` (10 controls) and six source mutants caught
(`.saipen/evidence/T-122-notify/`).
