# HUMAN_ATTENTION_BUDGET v0

The scarce resource this document governs is **human attention consumption**,
not message creation. A message may exist forever without ever being shown,
and zero shown messages is a valid, successful result:

```
MESSAGE_EXISTS   != ATTENTION_GRANTED
CANDIDATE_EXISTS != MESSAGE_SHOWN
SENDER_REQUEST   != RECEIVER_CLASS
ZERO_DELIVERIES IS A SUCCESSFUL OUTCOME
```

The defect class `saimail/human_attention.py` eliminates: a transport object,
its author or an automatic judge talking the receiver into spending attention.
A sender cannot sign itself into importance, because no sender-facing field
feeds this layer at all. Only the receiver admits a candidate, assigns its
class and grants at most one presentation inside a rolling receiver-time
window. The normative decisions are [D-044](DECISIONS.md) and its additive
receiver-time authority correction [D-045](DECISIONS.md).

## 1. Receiver-local layer

This is a receiver-local host protocol. It adds:

- no SAILANG kind,
- no SAILETTER wire field,
- no sender importance vocabulary (`IMPORTANT`, `URGENT`, `MUST_READ`,
  `BREAKTHROUGH`, `PRIORITY_SCORE` appear nowhere in the module or its
  records).

The queue lives under a caller-supplied root, one directory per human
identity digest, and the repository itself carries no mailbox:

```
<root>/human-attention/<human-id-digest>/
    candidates/<candidate-id-digest>.json
    presented/<candidate-id-digest>.json
    leases/<candidate-id-digest>.json
    attention.lock
```

`candidates/` and `presented/` hold immutable publications: the name appears
only with complete canonical bytes behind it and a committed record is never
replaced. `leases/` is operational state, atomically replaceable or removable
while the OS lock is held. No file ever holds source prose.

## 2. AttentionCandidate

An immutable receiver-built record that points at an externally managed
source. It is metadata, not the source payload.

| Field | Meaning |
|---|---|
| `TO_HUMAN` | receiver human identity, `human-id:sha256:<64 lowercase hex>` |
| `SOURCE_KIND` | closed set: `HUMAN_PRIVATE`, `EXTERNAL_REFERENCE` |
| `SOURCE_REF` | `HUMAN_PRIVATE`: the stored `LETTER_ID`; `EXTERNAL_REFERENCE`: a bounded inert token of at most 128 characters |
| `ALLOCATION` | receiver-owned class, closed set below |
| `DEFERRAL_POLICY` | receiver-owned policy, closed set below |
| `ENQUEUED_AT` | receiver-owned UTC instant, never a source's `CREATED` |

`ALLOCATION_SET = CRITICAL_RECOVERY, AMBIGUITY_RESOLUTION, DECISION_REQUEST,
ROUTINE_AUDIT, IDLE_REPORT`; `DEFERRAL_SET = BLOCK_UNTIL_HUMAN,
QUEUE_AND_CONTINUE, ESCALATE_AND_HALT`. There is no free-form "why this
matters" field: such a field becomes a persuasion surface immediately.

`REFERENCE_EXISTS != REFERENCE_SUPPORTS_CLAIM`. A reference says where a
candidate points; it never asserts that the object exists forever, that it
supports any claim, or that it proves the candidate is worth attention.
Scheduling is not epistemic promotion.

For `HUMAN_PRIVATE` the ref is an opaque ciphertext identity. The layer does
not decrypt, does not inspect `SUBJECT` or `BODY`, does not cache plaintext and
does not copy plaintext into queue state. This layer schedules presentation
opportunity; it does not interpret private prose.

### Candidate identity

```
CANDIDATE_ID = sha256("SAIMAIL-HUMAN-ATTENTION-CANDIDATE1\0" + TO_HUMAN + "\0" + SOURCE_KIND + "\0" + SOURCE_REF)
```

ENQUEUED_AT is deliberately outside the identity: the same source resubmitted
later is the same candidate, not a second one. Re-admission with identical
receiver policy is `IDEMPOTENT` and the first receiver `ENQUEUED_AT` stands. A
re-admission that changes `ALLOCATION` or `DEFERRAL_POLICY` refuses
`ATTENTION_CANDIDATE_CONFLICT`; receiver policy history is not rewritten.

### Canonical candidate record

One JSON object, canonical (sorted keys, `,`/`:` separators, one final LF,
strict UTF-8, no BOM), exact key set:

```
{"ALLOCATION":"…","CANDIDATE_ID":"sha256:…","DEFERRAL_POLICY":"…","ENQUEUED_AT":"…","SCHEMA":1,"SOURCE_KIND":"…","SOURCE_REF":"…","TO_HUMAN":"…"}
```

Unknown fields, missing fields, duplicate JSON keys, non-canonical bytes, a
non-`1` `SCHEMA` and an identity that disagrees with the fields or the file
name all refuse `ATTENTION_CANDIDATE_CORRUPT`.

## 3. Admission is an explicit receiver decision

Only `AttentionQueue.admit_receiver_candidate` admits a candidate, and only a
receiver-side decision calls it:

- no transport parser calls it,
- no HENV1 delivery calls it automatically,
- no LEGACY adoption calls it automatically,
- no sender field can reach it.

The supported admission call supplies only `SOURCE_KIND`, `SOURCE_REF`,
`ALLOCATION` and `DEFERRAL_POLICY`. The queue supplies `TO_HUMAN` from its
configured `human_id` and mints `ENQUEUED_AT` from its constructor-injected
clock while holding the queue lock. A caller-created, pre-stamped
`AttentionCandidate` is not admission authority. The durable type remains
publicly readable and parser-constructible for persisted records.

## 4. Budget: a rolling receiver window

```
DEFAULT_MAX_PRESENTATIONS = 1
DEFAULT_PERIOD_SECONDS     = 86400
```

At receiver instant `now`:

```
consumed = presented receipts with presented_at > now - period
         + active non-expired reservations
```

The boundary rule is explicit: a presentation exactly one full period old no
longer consumes. Receiver configuration may choose another positive period.
`MAX_PRESENTATIONS = 0` is valid and means no human attention may be consumed
through this queue; it is not a configuration error. Negative maxima and
non-positive periods refuse `ATTENTION_BAD_BUDGET`.

Only receiver-owned instants count: `ENQUEUED_AT`, `RESERVED_AT`,
`LEASE_UNTIL`, `PRESENTED_AT`. No source-authored timestamp ever affects
ordering, budget or expiry.

Public production operations accept no per-call `now`: `reserve_next()`,
`ack_presented(reservation_id)`, `budget_state()` and
`release(reservation_id)` obtain receiver time only from the queue clock. Each
reads that clock once after acquiring the operational lock and uses the same
instant for the complete transition. Tests remain exact by injecting and
advancing a deterministic constructor clock.

## 5. Selection and reservation protocol

`reserve_next` runs under the one process-safe lock and, in order:

1. loads and validates durable state (candidates, receipts, leases;
   corrupt state fails closed),
2. expires stale leases and drops leases superseded by a receipt,
3. computes the rolling budget,
4. orders pending candidates:
   `ALLOCATION_PRECEDENCE`, then `ENQUEUED_AT` ascending, then `CANDIDATE_ID`
   ascending,
5. with budget available, creates exactly one reservation and returns
   `RESERVED`,
6. otherwise returns the highest-ranked pending candidate's deferral outcome.

Precedence is fixed: `CRITICAL_RECOVERY > AMBIGUITY_RESOLUTION >
DECISION_REQUEST > ROUTINE_AUDIT > IDLE_REPORT`. There is no ranking by
semantic worth, no probability, no reputation and no engagement feedback.

A reservation is receiver-local operational state containing
`reservation_id`, `candidate_id`, `reserved_at` and `lease_until`. An active
reservation provisionally consumes one slot, so two concurrent calls with
`max_presentations = 1` cannot both return `RESERVED`.

### Two-phase delivery

No budget is consumed because a scheduler selected a candidate. External
presentation is a side effect that must be acknowledged:

```
reserve -> present -> ack_presented
```

`ack_presented` proves the reservation exists, its candidate exists, the
reservation is active, its candidate is not yet presented, then publishes an
immutable receipt:

```
{"CANDIDATE_ID":"sha256:…","PRESENTED_AT":"…","RESERVATION_ID":"…","SCHEMA":1}
```

Only after publication is the lease removed. A crash between the two steps
therefore cannot lose the fact that attention was consumed: recovery seeing a
receipt plus a lease treats the candidate as presented and removes the
redundant lease. Repeating an exact ACK is `ALREADY_ACKED` (idempotent). A
malformed token refuses `ATTENTION_BAD_RESERVATION`; an unknown one refuses
`ATTENTION_UNKNOWN_RESERVATION`; an expired one refuses
`ATTENTION_RESERVATION_EXPIRED`. A candidate already presented under another
reservation refuses `ATTENTION_CANDIDATE_ALREADY_PRESENTED`.

A successful ACK additionally requires
`RESERVED_AT <= PRESENTED_AT < LEASE_UNTIL`. If the receiver clock is earlier
than durable `RESERVED_AT`, the operation refuses
`ATTENTION_CLOCK_REGRESSION`: no receipt is published and the original lease
remains. The same fail-closed rule prevents reserve, release or budget cleanup
from treating future durable leases as expired. A valid immutable receipt with
`PRESENTED_AT` later than current receiver time remains inside the rolling
consumption count; rollback never manufactures capacity or rewrites history.

`release` removes one active lease, keyed exactly by its reservation token,
and consumes no budget; the candidate stays queued. One reservation can never
release another.

A lease expires at `now >= lease_until` (default 300 seconds; configurable for
tests). A crashed presenter cannot permanently consume attention. Cleanup is
mechanical: it happens during the next explicit queue operation, with no
daemon and no cleanup thread.

## 6. Outcomes are data

Closed result vocabulary for `reserve_next`:

| Result | Meaning |
|---|---|
| `NO_MESSAGE` | empty queue, no eligible candidate, or budget unavailable with nothing pending |
| `RESERVED` | one reservation created; caller may present the candidate |
| `DEFERRED` | pending candidate, policy `QUEUE_AND_CONTINUE` |
| `ATTENTION_BLOCKED` | pending candidate, policy `BLOCK_UNTIL_HUMAN` |
| `ATTENTION_HALT_REQUIRED` | pending candidate, policy `ESCALATE_AND_HALT` |

No result performs the caller's action automatically. The module never stops a
process, never mutates another system's state, never creates work and never
manufactures a filler message because a period started. Zero messages is a
normal success.

## 7. Boundaries

- **Privacy.** The scheduler performs no private-key operation, requests no
  PIN, requests no physical interaction and reads no private store. A human
  never touches a token merely because a scheduler is deciding whether an
  attention slot exists. Stored attention files carry no `SUBJECT`, no `BODY`
  and no source prose.
- **Time.** Only receiver instants decide ordering, budget and expiry.
- **Authority.** No allocation bypasses the budget, including
  `CRITICAL_RECOVERY`: its escalation path is the caller receiving
  `ATTENTION_HALT_REQUIRED`, never a silent extra presentation.
- **No semantic scoring.** No value, probability, model ranking, sentiment,
  relevance model, reputation or click feedback exists in v0.
- **No external control.** `ATTENTION_BLOCKED` and
  `ATTENTION_HALT_REQUIRED` are inert data; what they mean operationally is a
  future integration decision.
- **Corruption.** Invalid stored state fails closed with a named refusal;
  malformed receiver state is never silently deleted.

## 8. Presentation semantics

A presented receipt records that the receiver application reported a
successful surfacing. It does not prove the human read, understood, agreed
with or acted on anything. v0 has no reminder, snooze, repeat delivery, read
receipt or ignored-inference; a presented candidate is not automatically
requeued.

## 9. Module surface

`saimail/human_attention.py` exposes `AttentionCandidate`,
`AttentionBudget`, `AttentionQueue`, `attention_candidate_id`, the closed-set
constants, the result vocabulary and the refusal codes used above. The module
builds only on repository primitives: `sailang.errors.SailangError`,
`saimail.publish.publish_immutable` for immutable records and
`saimail.postoffice`'s OS-backed lock for process safety.

The full suite proves the contract in
`tests/test_human_attention_queue.py` and
`tests/test_human_attention_budget.py`, plus the corrective attack controls in
`tests/test_human_attention_clock_authority.py`, including zero-message outcomes,
allocation precedence, rolling-window boundaries, restart reconstruction,
real concurrent reservation and ACK races, lease expiry, crash-order recovery,
corruption fail-closure and the sender-self-priority and privacy tripwires.
