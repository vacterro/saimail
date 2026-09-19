# SAIMAIL post office v0 — delivery, attention, promotion

Status: DRAFT. Derived from the `SRC-001 -> SRC-003` receipt lineage.

The whole system in one line:

> **Write freely. Store cheaply. Read selectively. Promote slowly.**

Overpollution has exactly one cause, and it is worth naming as a failure mode
rather than a risk:

```
every message -> permanent memory -> automatically read by every agent
```

That is the road to a very expensive digital attic where agents write each
other philosophical postcards and then spend half a context window re-reading
their own emotional litter.

## 1. Layout

```
mail/
  outbox/                 written, not yet delivered
  inbox/<agent>/          delivered, unread
  read/<agent>/           opened, retained until TTL
  quarantine/             signature or parse failure, never auto-opened
  expired/<agent>/        tombstones only: id, kind, sender, reason, times, ttl (D-038)
  promoted/               index of envelopes that earned durable memory
  index.jsonl             one header row per envelope, append-only
```

`index.jsonl` is the only file an agent must ever scan. It holds headers, not
payloads.

## 2. Lifecycle

```
WRITE -> DELIVER -> SCAN -> (OPEN | DEFER | IGNORE) -> [PROMOTE from the opened payload] -> EXPIRE
```

`SCAN` reads headers only. `OPEN` is the first step that costs real context.
Promotion is never a scan output: it happens after an authenticated open, from
the opened payload, through the promotion gate (§5, D-035).
`EXPIRE` removes the body and leaves a tombstone — the fact that a message
existed is never deleted, only its content.

## 3. The interest filter

Before opening anything, an agent sees only:

```
topic  kind  sender  age
```

`age` is the receiver-local `HEADER_SCAN AGE`: `now - RECEIVED_AT`, never
`current_time - CREATED`. `CREATED` is sender-authored and signed and stays
visible metadata where useful; it is not the receiver's clock, and a sender
must not be able to influence attention or expiry ordering by choosing an old
or future `CREATED` (D-031). No TTL or expiry logic is implemented by this
section.

and decides:

| Verdict | Meaning |
|---|---|
| `OPEN` | spend context on the payload now |
| `DEFER` | re-evaluate at the next scan |
| `IGNORE` | not relevant to this seat |

`PROMOTE` is not a scan verdict (corrected for T-5 under `SRC-020`, T-43: the
original table listed it, which let a header-only verdict claim durable-memory
eligibility). Header attention and memory promotion are different things:

> **HEADER ATTENTION != MEMORY PROMOTION.** A header may cause `OPEN`. Only
> the authenticated opened payload may later produce a promotion proposal.

The scan verdicts are the selector's ladder (`OPEN_R2`/`OPEN_R3` for `OPEN`).
After D-036 a machine-required open is a floor, and D-037 completes the merge
for every verdict: the final attention is the monotone maximum of the
receiver-owned deterministic verdict and an optional caller-supplied model
recommendation (`IGNORE < DEFER < OPEN_R2 < OPEN_R3`), so a model may raise
attention, never lower it — and the Post Office itself never calls a model.

The header interest policy is receiver-owned (`HeaderInterest`): declared
`open_r3`/`open_r2` topics, kinds and senders, declared ignore sets, default
`DEFER`; strongest declared OPEN match wins, explicit IGNORE applies only when
no OPEN rule matched, and an OPEN declaration beats an overlapping IGNORE. It is
a separate policy from the SAILANG R1 selector, which reads a decoded
`TriageView` and cannot run on a clear header.

Not `novelty`, and not `trust`. Both were removed from v0 (`DECISIONS.md`
D-005): a sender-declared novelty score and an uncalibrated trust number are
decoration that would steer real decisions. They return only as
receiver-computed measurements, and only once there is a calibration sample to
compute them from.

This is what makes "an agent notices a letter in passing" affordable: a header
row is tens of bytes, a payload is hundreds of tokens.

**Budget rule:** a session declares a scan budget and an open budget. One scan
unit is one index row examined by one scan operation, and exhaustion returns an
explicit exhausted state plus a continuation cursor; a continuation never
re-charges a row already examined in the same chain. One open unit is one open
attempt inside one session, checked before any decryption, and a failed attempt
still consumes it because work was actually attempted. Exceeding the open budget
is a refusal, not a silent stop — the unread remainder stays in the inbox, and
the fact that budget was exhausted is logged.

**Trust is computed, not declared — and until it can be computed honestly, it
does not exist.** A sender's trust may one day be derived from the outcomes of
its previous messages (promoted / corroborated / contradicted), never from its
identity, seat name or seniority. v0 ships no trust number at all, because a
score derived from a handful of messages is the uncalibrated-confidence failure
wearing a different hat (`DECISIONS.md` D-005). This is `A != T` applied to
mail, including to the metric itself.

## 4. Three memory tiers

```
EPHEMERAL    the default. TTL 7–30 days. Costs nothing to ignore.
INTERESTING  a reader marked it useful. TTL extended. Still not memory.
PROMOTED     durable. Entered institutional memory with provenance.
```

**`message != memory`** is the load-bearing rule of the entire design.

```
SAIENVELOPE may enter the inbox freely,
but durable memory requires promotion.
```

Without it, a year of operation produces a million records of the form
"today I noticed an unusual pattern in retry logic" that nobody ever used.

## 5. Promotion

Promotion is an operation with a reason and evidence, not a feeling. It is
also payload-bound (D-035): a promotion proposal may only be made from an
`OpenedEnvelope` whose exact plaintext bytes are one canonical record, through
the kind-aware gate below. A header, however interesting, proposes nothing.
Signals:

| Signal | Question |
|---|---|
| novelty | is it new to the **receiver's** memory — measured there, never declared by the sender |
| independent corroboration | did a separate source confirm it |
| downstream usefulness | did it change a decision or a fix |
| reuse count | has it been cited again |
| confidence | what rung does its claim hold |
| evidence attached | can the next agent re-check it |

A promotion record:

```
PROMOTE sha256:a17f0c3b…64 hex…
REASON: reused_in_T1342
EVIDENCE: test_pass_24/24
RUNG: U3
```

**Promotion is kind-aware** (`DECISIONS.md` D-006). "Evidence required" is
right for factual knowledge and wrong as a universal rule:

| Kind | To promote, requires |
|---|---|
| `F`, `O` | an evidence ref — refused without one, not warned |
| `H` | provenance + falsification condition; evidence may support it without silently converting it into an `F` |
| `G`, `V` | authenticated provenance only — a stated goal or value needs no pretend factual evidence |

For `F`/`O` that refusal is the single gate separating institutional memory
from a shared mood.

Promotion is one-way in effect but not in authority: a promoted item that is
later contradicted is marked `C` and kept, with the contradicting evidence
attached. Nothing is deleted to keep the record tidy. See 00-PRINCIPLES §7.

## 6. Cost model

The reason this is affordable at all:

```
prose:   "Today I found that after recovery, stale queue ownership can persist
          between retries and this causes duplicate execution…"   ~ hundreds of tokens

SAILANG: L1|F|queue|U2|EV+|QSTALE>RETRY>DUP_EXEC|-            ~ tens of bytes
```

Plus content addressing (identical bodies stored once), delta encoding against
a referenced prior envelope, and a short-lived inbox that empties itself.

Cost discipline is a first-class requirement, not an optimisation: a mail
system that is expensive to ignore will be switched off, and a mail system that
is cheap to ignore can afford to carry thoughts that turn out to matter later.

## 7. What emerges, and what must not

Expected, and welcome: one agent writes warnings, another writes compressed
lessons, a third writes rarely but is worth reading every time. A trust graph
forms from outcomes. Local dialects appear in the dictionary.

Not welcome, and structurally prevented:

- private mail acquiring authority (`I1`)
- traffic that no human can see (`I2`)
- memory that grows without a promotion gate (`I3`)
- reputation attaching to identity rather than to outcomes (§3)

## 8. Post Office v0 semantics (D-031, D-036, D-037)

`DECISIONS.md` D-031 is the authority for these; this section states them where
the Post Office design will read them.

- `ENVELOPE_ID = sha256(exact canonical container bytes)` — derived, not
  a signed field. Same bytes, same id; the same plaintext resealed is normally
  a different transport object with a different id. It is never plaintext,
  semantic-message, knowledge, evidence, sender or trust identity. (Stated for
  SENV1 when D-031 was recorded; the formula is version-neutral and hashes
  whatever canonical container bytes `parse_header` accepts, which since D-034
  is SENV2 only.)
- `CREATED` is sender-authored and signed; `RECEIVED_AT` is a receiver-local
  observation made when the object enters that Post Office. Future ordering and
  TTL policy must not treat one as the other.
- `HEADER_SCAN AGE` is receiver-local age derived from `RECEIVED_AT`:
  `now - RECEIVED_AT`, never `current_time - CREATED`. A sender choosing an
  old or future `CREATED` cannot move its own message in the receiver's
  attention or expiry order; `CREATED` stays visible metadata, not the
  receiver's clock. No TTL is implemented by this preflight.
- The same `ENVELOPE_ID` seen again is a duplicate delivery event, not a new
  message — and not the same as the same plaintext resealed into a new
  envelope. A future store may keep `FIRST_RECEIVED_AT` and a duplicate count.
- The T-5 attention floor is decided (`B-014`, decided by D-036 under
  `SRC-020`): `ATTENTION_FLOOR: DECIDED` — `MACHINE_REQUIRED_OPEN` is a
  non-downgradable floor. A deterministic `OPEN_R2` may end at `OPEN_R2` or
  `OPEN_R3`, never `DEFER`/`IGNORE`; a deterministic `OPEN_R3` stays
  `OPEN_R3`. A model reader may raise the resolution of a machine-required
  open, never reduce it. The scope is the machine-required opens alone; the
  remaining `DEFER`/`IGNORE` interactions stay open until the reader that
  must enforce them exists. `tests/test_repo_consistency.py` refuses a Post
  Office that appears with no decided floor on record.
- The attention merge for header attention is exact and total (D-037). A
  machine selector verdict is one of `IGNORE`, `DEFER`, `OPEN_R2`, `OPEN_R3`;
  an optional model recommendation may only raise attention
  (`IGNORE < DEFER < OPEN_R2 < OPEN_R3`), `final = max(machine, model)`:

  * machine `OPEN_R2` + model `IGNORE` -> `OPEN_R2`
  * machine `OPEN_R2` + model `DEFER` -> `OPEN_R2`
  * machine `OPEN_R2` + model `OPEN_R3` -> `OPEN_R3`
  * machine `OPEN_R3` + any lower verdict -> `OPEN_R3`
  * machine `IGNORE` + model `DEFER` -> `DEFER`
  * machine `IGNORE` + model `OPEN_R2` -> `OPEN_R2`
  * machine `DEFER` + model `OPEN_R3` -> `OPEN_R3`
  * no model recommendation -> the machine verdict unchanged

  An unknown model verdict token is refused; the Post Office never calls a
  model and never invents a confidence score.

T-45 implements the delivery store, canonical index, header-only scan, budget
accounting and the authenticated open transition described by this section.
T-7's TTL sweep is implemented by section 9 below, and promotion stays the
separate payload-bound gate above — `HEADER ATTENTION != MEMORY PROMOTION`.

## 9. TTL sweep (D-038)

`EXPIRE` (section 2) removes a body and leaves a tombstone: the fact that a
message existed is never deleted, only its content. The full contract is
`DECISIONS.md` D-038; this section states it where the Post Office reads it.

**Retention is receiver-owned.** The receiver declares `default_ttl = 14 days`
inside the allowed v0 range `7 days <= default_ttl <= 30 days`; an out-of-range
value is refused, never silently accepted. The signed `TTL:<nD|nH>` header is a
**retention ceiling**, not a sender authority to force longer storage:

```
effective_ttl = receiver_default                            (envelope TTL absent)
effective_ttl = min(parsed_envelope_ttl, receiver_default)   (envelope TTL present)
```

A receiver default of 14D therefore yields 7D for header `TTL:7D` and 14D for
header `TTL:30D`. The sender may request shorter retention; it may not force
longer. SENV2 syntax is unchanged and zero-valued `TTL:0H`/`TTL:0D` stays
accepted; an effective TTL of zero is eligible on the first explicit sweep at or
after `RECEIVED_AT`. Nothing is auto-deleted during delivery.

**The expiry clock is receiver-local.** `expires_at = RECEIVED_AT +
effective_ttl`, eligibility `now >= expires_at` in UTC. Never `CREATED + TTL`,
never a receiver time measured against the sender's `CREATED`: `CREATED` stays
sender-authored metadata and moves neither attention nor expiry.

**Sweep is explicit maintenance only** — `PostOffice.sweep_expired(now=...)`, or
an equally narrow receiver-owned operation. It never runs inside `deliver()`,
`scan()`, `open_message()` or `recover()`, and there is no daemon, background
thread, timer, scheduler or network worker. The caller decides when maintenance
runs, which keeps sweep deterministic and testable.

**Tombstone before delete.** An expired accepted envelope becomes an immutable
tombstone under `mail/expired/<seat>/<ENVELOPE_ID-digest>.json` carrying no
plaintext, no ciphertext and no `.senv` body copy. One canonical schema suffices
for existence, addressing and expiry auditability:

```
schema  envelope_id  sender  recipient  kind
received_at  expired_at  effective_ttl_seconds  reason   # reason = "TTL_EXPIRED"
```

`received_at` is the ORIGINAL receiver receipt time; `expired_at` is the
maintenance observation at which the tombstone committed;
`effective_ttl_seconds` records the exact policy used so the decision stays
auditable after the body is gone. No claim/payload/evidence content and no model
judgments. `index.jsonl` stays append-only and unchanged.

**A tombstone proves the object it represents (D-039).** File existence is never
expiry authority: `REFERENCE_EXISTS != REFERENCE_SUPPORTS_CLAIM`. Before a
tombstone may assert `EXPIRED`, its `<digest>.json` file name and its own
`envelope_id` must agree, its bytes must be exactly the canonical serialization
of its object, and its `envelope_id`/`sender`/`recipient`/`kind`/`received_at`
must bind the canonical index row. A body-absent indexed envelope therefore has
three distinct outcomes that never collapse: valid bound tombstone -> `EXPIRED`;
no tombstone -> `INDEX_BODY_MISSING`; invalid or conflicting tombstone ->
`EXPIRED_TOMBSTONE_CORRUPT` / `EXPIRED_TOMBSTONE_CONFLICT`. Header-only scan may
read the small receiver-owned tombstone JSON to decide this; it still never reads
`.senv` payload bytes.

The required order is: verify candidate bundle → prove TTL eligibility →
construct complete canonical tombstone bytes → publish atomically with no
overwrite → fsync → **only then** delete the live inbox/read bundle → fsync the
state directory. `delete body, then try to tombstone` is forbidden; the fact of
existence survives every crash window. An identical existing tombstone is
idempotent, a different tombstone for the same `ENVELOPE_ID` is a named conflict
that keeps the body and never overwrites the winner. The only normal destructive
crash window is "tombstone published, body not deleted"; `recover()` proves the
pair is the same `ENVELOPE_ID` and original receipt before finishing the
deletion, else `EXPIRY_STATE_CONFLICT`. "Body deleted and no tombstone" is never
supported: it is `INDEX_BODY_MISSING`, never a retroactive invented tombstone.

**One maintenance pass converges every expiry crash/BOTH state (D-039).**
`recover()` on `tombstone + inbox + read` proves the pair identical and removes
both bodies, leaving only the tombstone (`EXPIRED`) — never a second call. A BOTH
pair (no tombstone) that is sweep-eligible likewise converges in one
`sweep_expired()`: the pair is proven identical, TTL is evaluated on one proven
body, then the tombstone is published and the final body and its exact crash copy
are removed — a successful sweep never leaves a live body. While a body still
exists, the tombstone must be one that body could have produced
(`effective_ttl_seconds` matches the signed header policy and the mailbox
default; `expired_at` is no earlier than eligibility), so a structurally valid
tombstone can never cause premature deletion. Any disagreement among tombstone,
index, receipt, inbox, read or verified header fails closed before the last body
is deleted.

**Scan, open, redelivery.** An indexed envelope with no inbox, no read and a
valid expired tombstone is `EXPIRED`: header scan skips it and does not fail
because the intentionally expired body is gone, while index row + no inbox + no
read + **no** valid tombstone stays `INDEX_BODY_MISSING`, so disappearance is
never made indistinguishable from intentional expiry. A tombstone coexisting
with a live body is `EXPIRY_RECONCILIATION_REQUIRED`, resolved by maintenance,
never by a header scan that would have to read `.senv`; expiry still consumes the
normal index scan unit. Opening an expired `ENVELOPE_ID` is `ALREADY_EXPIRED`
with no decrypt, no mutation and no open-budget consumption. Exact redelivery of
an expired `ENVELOPE_ID` returns `DUPLICATE` with the original `RECEIVED_AT` and
resurrects nothing, while the same plaintext freshly resealed is a new
`ENVELOPE_ID` under normal rules (D-031).

**One mailbox lifecycle lock.** The destructive transition takes an OS-backed
lifecycle lock (`mail/lifecycle.lock`), reusing/generalising the existing OS lock
primitive — never lock-file existence, a thread mutex or PID text. Ordering is
`LIFECYCLE LOCK` then `INDEX LOCK`, never the reverse. `deliver`, the inbox→read
transition, `recover` and `sweep_expired` participate; ordinary header-only scan
does not. Sweep covers `inbox/<seat>/` and `read/<seat>/` only, never
`quarantine/`, `promoted/` or arbitrary files; index rows are never deleted and a
receipt is never deleted apart from its bundle. `mail/promoted/` stays reserved
and is not special-cased: no durable promotion ledger exists and T-7 owns
transport retention only — it creates or alters no KNOWLEDGE card and marks no
promotion state.

必要なものだけ残す — keep only what is needed.
