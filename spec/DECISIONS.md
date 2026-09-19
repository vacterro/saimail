# Spec decisions log

Every entry resolves a contradiction or an open question in the derived spec.
Authority order is unchanged and absolute:

```
AUTHORITATIVE RECEIPT LINEAGE > DERIVED SPEC > IMPLEMENTATION > TESTS
```

The lineage is `SRC-001 -> SRC-003` and `SRC-002 -> SRC-004` (the originals captured a path instead of a body and were amended, never rewritten). A single receipt id is one link in that lineage, not the ladder itself. Authorship inside a receipt is a separate question, answered by `provenance/` and never by style.

An entry here never rewrites the founding idea. It records where the derived
spec was wrong, ambiguous or self-contradictory, what was chosen, and why.

---

## D-001 — no free-text motive field (SAIHANDOFF correction A)

**Removed:** `INCENTIVE:<free text>` from the SAILANG record.

**Replaced with:** `INTEREST_REF:sha256:<hex>[,…]` — a reference to an evidence
record that documents a structural interest.

**Why.** `00-PRINCIPLES` §2 forbids intent inference outright. A free-text
field invites exactly the collapse it forbids: a model given

> "this source has a documented commercial relationship"

writes back

> "this source wants to deceive us."

`INTEREST_REF` can only say *there is evidence of a relevant structural
interest*. It cannot say *we know the motive*, because it holds no prose.

The six analytic axes in `00-PRINCIPLES` §5 are unchanged — `INCENTIVE` stays
a question an analyst asks. It is no longer a field an agent fills in.

---

## D-002 — the line is a lossy triage projection (SAIHANDOFF correction B)

The v0 draft said both that the line is projection-only and that it is
effectively lossless for an agent holding the dictionary. Those cannot both
hold. Resolved:

```
THE RECORD IS CANONICAL.
THE LINE IS A LOSSY, DETERMINISTIC TRIAGE PROJECTION.
```

The line exists for cheap scanning, indexes, headers, attention decisions and
compact references. It is never authoritative, never reconstructed into a
record, never cited as evidence.

**No line → record parser is built.** Its absence is asserted by a test, not by
a promise in prose.

When the line cannot represent an exact fact, the answer is `OPEN RECORD`,
never a guess. In the wire format that is the literal `?` token.

---

## D-003 — full cryptographic identity (SAIHANDOFF correction C)

`$ + 8 hex` is 32 bits. For a system meant to hold institutional memory for
years that is a birthday collision waiting to be someone's afternoon.

**Identity:** `ID:sha256:<64 lowercase hex>`. Same for every reference field
(`EV`, `CON`, `REFUTES`, `SUPPORTS`, `INTEREST_REF`). A truncated prefix may be
*rendered* for human reading; it is never accepted as identity on input.

### Canonical hashing

```
hash input = canonical serialization of the record
             with the ID line removed
             every other field present, in canonical order
             UTF-8, LF, no BOM, trailing LF after the last line
ID          = "sha256:" + hex(sha256(hash input))
```

- **No self-reference.** `ID` is excluded from its own input, so there is no
  fixed-point to solve and no ambiguity about which bytes were hashed.
- **No hidden normalization.** No NFC, no whitespace trimming, no case folding.
  The bytes that arrive are the bytes that are hashed. Unicode normalization
  would silently change identity for text that looks identical.
- **Deterministic order.** Field order is fixed by the spec, not by insertion
  order or dict iteration.

### Immutability, and where mutable assessment lives

A record is **immutable**. `STATUS` and `EV` state what the author asserted at
`CREATED`, and they are part of the identity.

Re-assessment does not edit the object. It emits a **new record** that points
at the old `ID` through `SUPPORTS`, `REFUTES` or `CON`. Current rung is a
ledger projection over those records — and, per the authority ladder, a
projection is never the authority.

This is the correction the handoff demanded: an object that calls itself
content-addressed must not be mutated in place. The API therefore exposes no
mutator at all.

---

## D-004 — `D` (decision) deferred out of v0 (SAIHANDOFF correction D)

`D` is removed from the kind set. Host protocols already own decision logs;
SAILANG will reference them rather than growing a second one. A record with
`KIND:D` is rejected with an error that names the deferral.

v0 kinds: `F O H G V`.

### TYPE narrowed

`TYPE` carried `GOAL` and `AUTH`, which duplicated `KIND:G` and smuggled
authority into an epistemic-channel field. v0 `TYPE` is `OBS | MEM | INT`,
required for `F/O/H`, forbidden for `G/V`.

### Kind validation matrix

| | `F` | `O` | `H` | `G` | `V` |
|---|---|---|---|---|---|
| `TYPE` | required | required, must be `OBS` | required | forbidden | forbidden |
| `SRC` channel id | optional | **required** | optional | optional | optional |
| `EV` | optional, `0` allowed | optional, `0` allowed | optional | forbidden | forbidden |
| `STATUS` | required | required | required | forbidden | forbidden |
| `FALSIFY` | forbidden | forbidden | **required** | forbidden | forbidden |
| max rung with `EV:0` | `U1` | `U1` | `U1` | — | — |
| max rung overall | `U4` | `U4` | `U3` | — | — |

Rules behind the table:

- **`F` may be honestly unverified.** `EV:0` is legal and produces a real
  record; it simply cannot climb past `U1`.
- **`O` must name its channel.** An observation whose source is `SRC:FS` with
  no path is not an observation, it is a rumour about a filesystem. And its
  confidence cannot outrun its evidence — the same `EV:0 → U1` ceiling applies.
- **`H` cannot masquerade as `F`.** `FALSIFY` is mandatory, and a hypothesis
  may not reach `U4`. A hypothesis that survives verification is restated as an
  `F` record citing the evidence; it does not get promoted in place.
- **`G/V` are not truth-apt.** No evidence, no rung, no probability. Forcing a
  goal through a truth verdict because the schema happens to own a `STATUS`
  field is exactly the category error `00-PRINCIPLES` §4 exists to stop.
  Provenance (`SRC`, `CREATED`) is still retained — who wants what, and when.
- `STATUS:C` requires `REFUTES`; `STATUS:D` requires `CON`. A verdict of
  contradiction must name what contradicts it.

---

## D-005 — no self-declared novelty or trust (SAIHANDOFF correction E)

`N:83` is removed from the SAIENVELOPE header in v0. A sender-scored novelty
that influences a reader is an authority channel with no evidence behind it —
`A != T` violated by a two-digit integer.

Deferred, explicitly, so a later implementation cannot mistake decoration for
epistemology:

- **Receiver-computed novelty** — measured against the receiver's own memory,
  not asserted by the sender. Not in v0.
- **Computed sender trust** — requires a calibration sample that does not
  exist. Inventing `trust = 0.83` from a handful of messages is the same
  uncalibrated-number failure `00-PRINCIPLES` §6 bans for confidence.

For v0 and until calibration data exists:

```
TRUST EVIDENCE, NOT SENDER REPUTATION.
```

---

## D-006 — promotion is kind-aware (SAIHANDOFF correction F)

Not implemented in this run. The future contract is corrected now so that it is
not built wrong later.

"Promotion requires evidence" is right for factual knowledge and wrong as a
universal rule. Promotion semantics by kind:

| Kind | To promote, requires |
|---|---|
| `F`, `O` | evidence ref — unchanged |
| `H` | provenance + falsification condition; evidence may support it **without** silently converting it into an `F` |
| `G`, `V` | authenticated provenance only — a stated goal or value is worth preserving and needs no pretend factual evidence |

A promoted record that is later contradicted is marked and **kept**. Forensic
history is never tidied.

---

## D-039 — A tombstone proves the object it represents; expiry converges in one pass

Recorded while repairing T-7 under `SRC-028` (T-49). D-038 froze the TTL sweep
but left two authority gaps, both measured by fresh reproduction. D-038 itself
is unchanged and stays historical; this entry tightens the read side and the
destructive-convergence side only.

**1. File existence is never expiry authority.** The defect:
`bundle_state()` treated `expired_tombstone(id).is_file()` as proof, so a
body-absent indexed envelope with a `not-json` tombstone reported `EXPIRED` and
scan skipped it — masking `INDEX_BODY_MISSING` as intentional expiry. That
violates `REFERENCE_EXISTS != REFERENCE_SUPPORTS_CLAIM`. A tombstone now proves
its object before it may assert anything:

- its file name is `<digest>.json`, and that digest IS the digest half of the
  tombstone's own `envelope_id` — path and object must agree, so a valid
  tombstone parked under another object's name is refused;
- the bytes are exactly the canonical serialization of the parsed object (one
  immutable evidence object, one accepted representation): duplicate keys,
  non-canonical equivalent JSON, malformed UTF-8 and unknown/missing fields are
  all `EXPIRED_TOMBSTONE_CORRUPT`;
- its own claims must bind the canonical index row — `envelope_id`, `sender`,
  `recipient`, `kind`, `received_at`, `reason = TTL_EXPIRED` — or
  `EXPIRED_TOMBSTONE_CONFLICT`. The tombstone intentionally omits topic,
  key ids, `created` and `ref`, so the index is never asked to reproduce a field
  the evidence object never carried.

So the three body-absent states are distinct and never collapse: valid bound
tombstone -> `EXPIRED`; no tombstone -> `INDEX_BODY_MISSING`;
invalid/conflicting tombstone -> the tombstone integrity refusal. Header-only
scan MAY read the small receiver-owned tombstone JSON to make this decision; it
still never reads `.senv` payload bytes.

**2. Expired redelivery requires a tombstone that describes that envelope.**
`_expired_dedup` now proves the tombstone against this receiver seat, the
persisted index identity, and the incoming verified header for every overlapping
field, before it may return `DUPLICATE`. A tombstone for another logical object
can never suppress delivery because someone placed it under the incoming
object's filename.

**3. One maintenance pass converges every expiry crash/BOTH state.** The defect:
`recover()` on `tombstone + inbox + read` removed only the inbox copy and left
`tombstone + read`, requiring a second call; and `sweep_expired()` on a BOTH
pair (no tombstone) expired one copy and left the other live. Now:

- `recover()` proves the inbox/read pair identical (existing exact
  content-identity checks), verifies the tombstone binds the index row and the
  verified live header, and removes BOTH bodies — one successful call leaves
  only the tombstone and `EXPIRED`;
- `sweep_expired()` on a BOTH pair proves the pair identical, evaluates TTL on
  one proven body, publishes the tombstone and removes the final body (and its
  exact crash copy), never leaving a live body under a "successful" sweep;
- while a body still exists, the tombstone must be one that body could have
  produced: `effective_ttl_seconds` equals the policy implied by the signed live
  header and the mailbox default, and `expired_at` is no earlier than
  eligibility. A structurally valid tombstone can therefore never cause
  premature deletion.

Any disagreement among tombstone, index, receipt, inbox, read or verified SENV2
header fails closed BEFORE the last body is deleted, reusing
`EXPIRY_STATE_CONFLICT` / `EXPIRED_TOMBSTONE_CONFLICT` / `READ_BUNDLE_CONFLICT` /
`INDEX_ROW_CONFLICT`; conflicting evidence is never normalized. A crash DURING
cleanup may leave a body copy for the next recovery, but a successful return
never does. D-038's retention policy is unchanged.

---

## D-040 — LEG1 is evidence-bound operational transfer without authority gain

Recorded for B-013 before production implementation. The S5 laboratory is
supporting design evidence only; production has no dependency on it.

```
FORMAT = LEG1
HOST_PROTOCOL_OBJECT = true
SAILANG_KIND_ADDED = false
SENV_K = EXPERIENCE
SENV_TOPIC = legacy
REQUIRED_FIELDS = SUBJECT, OBSERVED_SCOPE, WHAT_WORKED,
  WHAT_WORKED_EVIDENCE, WHAT_FAILED, WHAT_FAILED_EVIDENCE,
  WHAT_LOOKED_RIGHT_BUT_WAS_WRONG, WHAT_WRONG_EVIDENCE, WATCH_NEXT,
  WATCH_NEXT_EVIDENCE, WATCH_NEXT_STATUS, CREATED
OBSERVED_SCOPE_RULE = predecessor observation only; never successor scope
EVIDENCE_REF_RULE = canonical sha256 refs; outcome refs non-empty;
  WATCH_NEXT_EVIDENCE may be literal 0; references are not proof
WATCH_NEXT_STATUS = UNVERIFIED
CONTENT_ID = sha256(exact canonical LEG1 bytes)
ENTRY_ID = sha256(b"SAIMAIL-LEGACY1-ENTRY\\0" + source ENVELOPE_ID ASCII
  + b"\\0" + exact canonical LEG1 bytes)
ADOPTION_REQUIRES = OpenedEnvelope
AUTO_ADOPTION = false
AUTHORITY_GAIN = none
KNOWLEDGE_PROMOTION = none
COMMAND_SEMANTICS = inert
```

LEG1 is a SAIMAIL host-protocol object transported as the exact plaintext of
existing SENV2. No SENV3 and no `KIND:L` are created. Canonical byte grammar,
bounds, durable layout, proof gate and successor view are normative in
`04-LEGACY-v0.md`.

Authentication proves which accepted sender delivered the exact container to
this receiver. It does not prove the sender's conclusion. Evidence references
record what was cited; they do not prove support. `OBSERVED_SCOPE` records the
declared observation boundary; `NEW_TASK_SCOPE` is caller-owned successor data
and is never derived from it. Multiple entries remain independent accounts.

---

## D-041 — successor provenance and recency are receiver-validated state

Recorded additively for the T-51 correction to B-013. D-040 and LEG1 wire
bytes remain unchanged. The defects were concrete: public construction and
`dataclasses.replace` could pair forged packet content with authentic-looking
provenance; sender-authored `CREATED` controlled a bounded successor slot; an
integer offset repeated an entry after a new head insertion; and a byte-bound
page could return zero entries with the same continuation forever.

```
RENDERABLE_ENTRY = LegacyStore-validated type-state
ENTRY_MINT = constructor-only InitVar, not retained
ORDER = received_at DESC, legacy_entry_id DESC
PREDECESSOR_CREATED != RETRIEVAL_RECENCY
CURSOR = legacy_entry_id of the last included entry
CONTINUATION = strictly after the cursor in current receiver-owned order
UNKNOWN_OR_CROSS_SUBJECT_CURSOR = LEGACY_BAD_CONTINUATION
TRUNCATED_PAGE_PROGRESS = at least one new entry and a changed cursor
NEXT_ENTRY_DOES_NOT_FIT = LEGACY_CONTEXT_ENTRY_TOO_LARGE
TOTAL_MATCHES = current exact-subject durable count
```

`LegacyStore._read_entry` remains the proof point: it mints only after packet
and provenance canonicality, content and entry identities, directory identity,
and receiver-owned source-index bindings all pass. The renderer duplicates no
partial validator; it consumes only this type-state.

Pagination is keyset continuation over the append-only store, not a frozen
snapshot. Entries newly adopted ahead of a cursor are visible on a fresh
request, not injected into an older continuation chain. Continuing after the
anchor repeats no returned entry and skips no entry that was already older
than that anchor. `CREATED` remains visible predecessor metadata and gains no
receiver authority.

---

## D-038 — TTL expiry is receiver-owned retention: tombstone before delete, no resurrection

Recorded while implementing T-7 under `SRC-026` (the T-7 execution-contract
handoff). D-031/D-037 left the Post Office with `AGE` derived from
`RECEIVED_AT` and no TTL logic at all; this entry freezes that TTL sweep. It is
transport-retention cleanup only — `MESSAGE RETENTION != KNOWLEDGE RETENTION`.

The frozen decision, in greppable machine form:

```
DEFAULT_TTL = 14D
RECEIVER_DEFAULT_RANGE = 7D..30D
TTL_IS_SENDER_RETENTION_CEILING = true
EFFECTIVE_TTL = min(sender_ttl_if_present, receiver_default)
EXPIRY_CLOCK = RECEIVED_AT
SWEEP = EXPLICIT_MAINTENANCE
TOMBSTONE_PATH = mail/expired/<seat>/<ENVELOPE_ID-digest>.json
TOMBSTONE_BEFORE_DELETE = true
INDEX_IS_PRESERVED = true
EXPIRED_SCAN_BEHAVIOR = skip (EXPIRED) / EXPIRY_RECONCILIATION_REQUIRED
EXPIRED_OPEN = ALREADY_EXPIRED
EXPIRED_REDELIVERY = DUPLICATE_NO_RESURRECTION
PROMOTION_LEDGER = OUT_OF_SCOPE
```


**1. Receiver-owned default, sender TTL is only a ceiling.** The receiver owns
retention. `default_ttl = 14 days`, and the allowed receiver configuration range
for v0 is `7 days <= default_ttl <= 30 days`; a value outside it is refused, never
silently accepted. The signed `TTL:<nD|nH>` header is a *retention ceiling*, not
a sender authority to force longer storage:

```
effective_ttl = receiver_default                       (envelope TTL absent)
effective_ttl = min(parsed_envelope_ttl, receiver_default)  (envelope TTL present)
```

So a receiver default of 14D with header `TTL:7D` yields 7D, and with header
`TTL:30D` yields 14D. The sender may request *shorter* retention; it may not
force longer. SENV2 syntax is unchanged: no new wire version, and a zero-valued
`TTL:0H`/`TTL:0D` is accepted by the existing parser. An effective TTL of zero
means the object is eligible on the first explicit sweep at or after
`RECEIVED_AT`; **nothing is ever auto-deleted during delivery**.

**2. Expiry clock is receiver-local.** `expires_at = RECEIVED_AT +
effective_ttl`, where `RECEIVED_AT` is the receiver-local observation. Never
`CREATED + TTL`, and never a current time measured against the sender's
`CREATED`; eligibility is `now >= expires_at` in UTC. `CREATED` stays
sender-authored metadata and cannot move expiry.

**3. Sweep is explicit maintenance only.** The v0 API is
`PostOffice.sweep_expired(now=...)` (or an equally narrow receiver-owned
operation). TTL work runs in **no** other path: not in `deliver()`, `scan()`,
`open_message()` or `recover()`, and there is **no** daemon, background thread,
timer, scheduler or network worker. The caller decides when maintenance runs, so
T-7 stays deterministic and testable.

**4. Tombstone location and schema.** An expired accepted envelope becomes an
immutable tombstone under `mail/expired/<seat>/<ENVELOPE_ID-digest>.json`. It
carries no plaintext, no ciphertext and no copy of `.senv`; its one canonical
schema is enough to preserve existence, addressing and expiry auditability:

```
schema
envelope_id
sender
recipient
kind
received_at
expired_at
effective_ttl_seconds
reason            # "TTL_EXPIRED"
```

`received_at` is the ORIGINAL receiver receipt time, `expired_at` is the
receiver maintenance observation at which the tombstone was committed, and
`effective_ttl_seconds` records the exact policy used so the expiry decision
stays auditable after the body is gone. No claim/payload/evidence content and no
model judgments. `index.jsonl` remains append-only and unchanged — it already
retains the clear header history.

**5. Crash order: tombstone committed before the body is deleted.** The order is
verify candidate bundle → prove TTL eligibility → construct the complete
canonical tombstone bytes → publish the tombstone atomically with no overwrite
(`saimail.publish`, the immutable publication discipline) → fsync → only then
delete the live inbox/read bundle → fsync the state directory. `delete body,
then try to tombstone` is forbidden: the fact of existence must survive every
crash window. An identical existing tombstone is idempotent; a *different*
tombstone for the same `ENVELOPE_ID` is a named conflict — the body is kept and
the winner is never overwritten. The only normal destructive-expiry crash window
is therefore "tombstone published, body not yet deleted"; `recover()` must prove
the pair describes the same `ENVELOPE_ID` and the same original receipt before
finishing the deletion, else `EXPIRY_STATE_CONFLICT`. There is never a supported
state of "body deleted and no tombstone": that is `INDEX_BODY_MISSING`, never a
retroactive invented tombstone.

**6. Verify before destroying.** Before deleting an accepted body, mechanically
establish: valid bundle directory identity; envelope bytes hash to the
`ENVELOPE_ID`; SENV2 parses canonically; the signature still verifies against the
receiver `KeyRegistry`; the recipient seat/key still agrees with the receiver
registry; the receipt `ENVELOPE_ID` matches; the index holds exactly one matching
row whose `RECEIVED_AT` equals the receipt `RECEIVED_AT`; and TTL eligibility is
true. Filesystem mtime/ctime are **not** TTL authority; a corrupted object is
never deleted merely because its timestamp is old.

**7. Scan after expiry.** An indexed envelope with no inbox bundle, no read
bundle and a valid expired tombstone is `EXPIRED`, not `INDEX_BODY_MISSING`:
header scan skips it and does not fail because the intentionally expired body is
gone. Index row + no inbox + no read + **no** valid tombstone remains
`INDEX_BODY_MISSING`, so disappearance is never made indistinguishable from
intentional expiry. A tombstone coexisting with a live body is
`EXPIRY_RECONCILIATION_REQUIRED`; header scan does not read `.senv` to resolve
it — maintenance does. Expiry still consumes the normal index scan unit because
its row was examined.

**8. Open, redelivery and the promotion boundary.** Opening an expired
`ENVELOPE_ID` is `ALREADY_EXPIRED`: no decryption, no state mutation, and no
open-budget consumption when expiry is established before any work. Exact
redelivery of an expired `ENVELOPE_ID` must not resurrect the message:
`deliver()` returns `DUPLICATE` with the original `RECEIVED_AT`, recreating no
inbox/read, resetting no `RECEIVED_AT`, appending no second index row and
removing no tombstone — the incoming bytes themselves hash to the id, so the
exact transport identity is mechanically established even though the historical
body is gone. The same plaintext freshly resealed is a different `ENVELOPE_ID`
and follows normal delivery. This preserves D-031. T-7 owns **transport
retention only**: it creates no KNOWLEDGE card, alters none, marks no promotion
state `C`, inspects no promotion ledger and invents no promoted-object
persistence. The historical T-7 phrase "contradicted promotions marked C and
kept" assumed a durable promotion ledger no ticket created and T-5 deliberately
never auto-promotes; it is out of scope here and preserved as history.

**9. One mailbox lifecycle lock.** The destructive transition needs an OS-backed
lifecycle lock (`mail/lifecycle.lock`), reusing/generalising the existing OS lock
primitive. Lock-file existence, a Python thread mutex and PID text are never the
authority; the OS lock is. The fixed ordering is `LIFECYCLE LOCK` then
`INDEX LOCK`, never the reverse. At minimum `deliver`, the inbox→read transition,
`recover` and `sweep_expired` participate; normal header-only scan does not need
the destructive lock. The sweep surface is `inbox/<seat>/` and `read/<seat>/`
only — never `quarantine/`, `promoted/` or arbitrary project files; index rows
are never deleted and a receipt is never deleted independently of its bundle.
`mail/promoted/` stays reserved and is not special-cased; no durable promotion
ledger exists.

---

## D-035 — an authenticated container is not an authenticated record

Recorded while closing T-42 under `SRC-019`. T-10's promotion gate took a
record, the container bytes and the `VerifiedEnvelope`, re-parsed the bytes
and proved the two agreed — and proved nothing about the record. A benign
envelope carrying a goal record happily promoted an unrelated forged fact:
the container's provenance leaked onto whatever record the caller happened to
hold. Resolved in two mechanical steps:

1. `open()` returns an `OpenedEnvelope` — a constructor-guarded type-state
   that can only be minted after parse, signature verification, recipient
   acceptance and AEAD decryption of one exact envelope, carrying the exact
   plaintext bytes, the `VerifiedEnvelope`, and the `ENVELOPE_ID` derived
   from the canonical container bytes. The mint is a constructor-only
   `InitVar` (the T-40 pattern), so opened state cannot be transplanted by
   `dataclasses.replace` or a copy.
2. `promotion.propose(record, opened, reason=...)` proceeds only when
   `record.canonical_bytes() == opened.plaintext`. Anything else refuses with
   `PROMOTION_PAYLOAD_MISMATCH` — including the same claim under different
   canonical metadata, and a container whose payload is not one canonical
   record at all.

The currently supported payload shape is exactly one canonical record per
envelope; a multi-record payload is a protocol decision nobody has made, and
this gate deliberately refuses to invent matching for it.

This is a normal-public-API type-state boundary, not hostile-process security
(same scope as D-015).

---

## D-036 — `MACHINE_REQUIRED_OPEN` is a non-downgradable attention floor

Recorded under `SRC-020` (T-43, the T-5 pre-implementation gate). This entry
decides `B-014`, the question D-031 carried as pending. **Decided.**

**The floor.** For deterministic selector verdicts (a machine-required open):

- `OPEN_R2`: the final resolution may be `OPEN_R2` or `OPEN_R3`, never `DEFER`
  or `IGNORE`.
- `OPEN_R3`: the final resolution remains `OPEN_R3`.

A model reader may increase the resolution of a machine-required open; it may
not reduce it. Attention depth is the only direction of travel
(`IGNORE < DEFER < OPEN_R2 < OPEN_R3`).

**Reason.** The recorded stability sample (T-33) repeatedly observed a model
answering `IGNORE` on unknown semantics — an item whose claim carries a term
the reader's dictionary does not define — precisely the item class for which
the deterministic selector requires `OPEN` because the semantics are NOT
understood. A probabilistic reader must not convert
`UNKNOWN -> REQUIRED_OPEN` into `UNKNOWN -> IGNORE`. Downgrading the one
verdict that exists because the content was unreadable destroys the reason the
verdict exists.

**Scope.** Narrowly the machine-required `OPEN`s above. This entry does not
define the remaining `DEFER`/`IGNORE` interactions (noise declarations,
budget interactions, repeated-scan decay): those stay open until the Post
Office reader that must enforce them exists. Selector semantics themselves are
unchanged by this entry; the floor binds whatever model-side resolution step
consumes a deterministic selector verdict, and it is enforced, not advisory,
when T-5 implements that step.

---

## D-037 — Post Office v0: deterministic header attention, monotone model merge, exact budgets

Recorded while implementing T-5 under `SRC-022`. D-036 decided the
machine-required `OPEN` floor and left the remaining `DEFER`/`IGNORE`
interactions open "until the Post Office reader that must enforce them exists".
The reader now exists. Five points are frozen; none of them changes a selector
semantic or a wire format.

**1. No model or network call inside the Post Office core.** Delivery, index,
scan and open are deterministic filesystem and crypto operations. A model
attention recommendation is caller-supplied DATA — an optional per-`ENVELOPE_ID`
verdict passed into `scan` — never an oracle the Post Office consults. The core
never calls SAIFREN, 9router, an LLM or the network, and chooses no provider or
model.

**2. The merge rule is the full monotone max.** Attention depth is
`IGNORE = 0 < DEFER = 1 < OPEN_R2 = 2 < OPEN_R3 = 3`, and

```
final_attention = max(machine_attention, model_attention)
```

for every machine verdict, not only the machine-required opens D-036 scoped. A
model may raise attention over machine `IGNORE`/`DEFER`; it may never lower a
receiver-owned deterministic verdict. A missing recommendation leaves the
machine verdict unchanged; an unknown verdict token is refused, never guessed.
The decided cases:

```
machine IGNORE + model DEFER    -> DEFER
machine IGNORE + model OPEN_R2  -> OPEN_R2
machine DEFER  + model OPEN_R3  -> OPEN_R3
machine OPEN_R2 + model IGNORE  -> OPEN_R2
machine OPEN_R3 + model OPEN_R2 -> OPEN_R3
no model recommendation         -> machine verdict unchanged
```

No confidence score, no trust weight, no numeric vote per verdict.

**3. Header interest is receiver-owned and is not the SAILANG R1 selector.**
`saimail.selector.select(TriageView, Interest)` reads decoded R1 semantics and
cannot run before a payload open; the scan sees only the clear index header. The
header policy is a separate `HeaderInterest` carrying explicit declared sets
(`open_r3_topics` / `open_r2_topics`, the matching `..._kinds` and `..._senders`,
`ignore_topics` / `ignore_kinds` / `ignore_senders`), defaulting to `DEFER`,
resolved as: strongest declared OPEN match wins, else explicit IGNORE, else
DEFER. A declaration that is both OPEN and IGNORE opens — a false ignore costs
more than a false open, and a receiver that declares an interest means it.
Interests are never inferred from traffic; no novelty and no trust are added.

**4. AGE is receiver-local.** Scan derives `age = now - RECEIVED_AT` at scan
time from the receiver's own observation; `CREATED` remains sender-authored
metadata and can move a message in neither the receiver's attention nor expiry
order. No TTL logic exists in T-5.

**5. Budget units are exact and exhaustion is explicit.** One scan unit is one
index row examined by one scan operation; when the declared scan budget runs
out, `scan` returns an explicit exhausted state and a continuation cursor, and a
continuation never re-charges a row already examined in the same chain. One
open unit is one open attempt inside one `PostOfficeSession`; the attempt is
checked before any decryption, a failed authenticated open still consumes it
(work was attempted), and exhaustion is the named refusal
`OPEN_BUDGET_EXHAUSTED` with no decrypt, no move and no state mutation. No token
estimation: the container already carries a bounded payload.

---

## D-034 — SENV2: the sender identity is bound into the sealed layer

Recorded while closing T-38 under `SRC-016`. This entry adopts the wire change
D-033 left open, under the name and rules the D-033 proposal sketched. D-033
itself stays untouched as the historical evidence of why SENV1 was insufficient.

**WIRE_VERSION:** `SENV2`. It is the only version the ordinary parser accepts,
the only version `seal` emits. A container whose first line is exactly `SENV1`
refuses `LEGACY_VERSION` — a distinct refusal code, so a retired object can
never be mistaken for current accepted mail. There is no dual-version
production reader and no in-code legacy decoder: no `.senv` object exists
anywhere (re-checked for this entry), so the migration surface is zero and none
is invented.

**Two forms rejected before adoption.**

- *The full current canonical unsigned header as AEAD associated data* —
  circular: the AAD would commit to `CIPHER_HASH`, which commits to the
  ciphertext, which depends on the AAD. Refused.
- *`FROM_KID` alone as the sender identity binding* — key identity is not seat
  identity. `KeyRegistry` legitimately accepts one fingerprint under more than
  one seat, so `FROM_KID` alone does not bind `FROM` + `FROM_KID` as one
  identity. Refused; this is exactly what the same-key different-seat control
  pins.

**EXACT_BOUND_FIELDS:** `FROM` and `FROM_KID`, nothing else.

**EXACT_CANONICAL_BYTES** (`canonical_sender_identity`):

```
"FROM:" <seat> "\n" "FROM_KID:" <full fingerprint> "\n"
```

UTF-8, LF, final LF, no BOM, fixed field order. Both values are already
parser-constrained (`seat` matches `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`, the
fingerprint is `sha256:` + 64 lowercase hex); neither can contain `:` in a
position that ambiguates the pair, a newline, or a BOM, so the serialization is
one-to-one and reversible. It is derived only from the parsed header fields in
fixed order, never from dict iteration.

**AEAD_AAD_DOMAIN:**

```
AEAD_AAD = b"SAIMAIL-SENV2-SENDER-BINDING\x00" || canonical_sender_identity
```

The domain marker prevents the binding bytes from being replayed as another
protocol's AAD. `CIPHER_HASH` and `SIG` are never part of the AEAD AAD.

**HKDF_DOMAIN:** the payload key derivation is version-separated:

```
HKDF info = b"SAIMAIL-SENV2-PAYLOAD-KEY\x00"
```

The SENV1 info string (`SENV1-v0 payload key`) is not reused across the wire
transition, so no SENV1 and SENV2 payload key can coincide for the same shared
secret. Salt stays the raw ephemeral public key, as in D-028.

**SIGNATURE_DOMAIN:**

```
b"SAIMAIL-SENV2-SIGNATURE\x00" || canonical unsigned SENV2 header bytes
```

Same construction as D-029, renamed to the new version marker.

**PROPERTY_GAINED:** an existing SENV2 ciphertext sealed under sender identity
`FROM = A`, `FROM_KID = K_A` cannot be relabelled to `FROM = B`, `FROM_KID =
K_B` and successfully opened merely because B is another accepted signing peer
— nor relabelled to another seat that accepts the *same* key. Changing the
bound sender identity changes the AEAD authentication context and the old
ciphertext refuses at decryption (`DECRYPTION_FAILED`), not as a signature
failure: the outer re-signature of a relabelled header can still verify, by
design, and the refusal belongs to the sealed layer.

**PROPERTY_NOT_GAINED:** unchanged from D-033 — no plaintext authorship, no
originality, no first transmission, no proof that one physical process
performed both the encryption and the signing, and no defence against a sender
who legitimately obtained the plaintext and reseals it itself. The payload key
still derives only from the recipient-side ECDH, so the signer is not
cryptographically present in the key agreement; the binding is to the AEAD
authentication context, which is the narrower, honest claim. `CONTAINER SENDER
!= PAYLOAD AUTHOR` unless payload-level evidence proves otherwise.

**Why the minimal binding and not the stronger one.** Binding `TO`, `TO_KID`,
`K`, `TOPIC`, `CREATED`, `TTL`, `REF`, `EPK` or `NONCE` into the AEAD AAD would
change the semantic guarantee — those clear values would become tied to the
encryption event itself. No current requirement asks for that: the whole header
is already inside the signature domain, D-033 demonstrates only the
relabel/re-sign attack, and closing that attack needs exactly the sender
identity in the AEAD context. More authenticated data is not a free good; it is
adopted when a consumer needs the stronger guarantee, not because it sounds
safer.

**MIGRATION_IMPACT:** zero. No `.senv` object exists in the repository or the
project artifacts; SENV1 bytes exist only as ephemeral test-generated data,
which this entry rewrites. Every SENV2 container is newly sealed.

**DOWNGRADE_POLICY:** there is no downgrade path. The ordinary receive path
does not accept SENV1, so the known D-033 semantics cannot be reached through
the current parser; a future historical SENV1 decoder, if ever needed for
forensics, must live outside the ordinary receive/open path and be explicitly
legacy. Dual-version production support is not invented without evidence that
it is needed.

---

## D-033 — SENV1 authenticates the sender of the container, not the author of the payload

Recorded while independently reviewing T-36 under `SRC-013`. Nothing in the
wire, the code or the tests changed for this entry: it names a guarantee the
construction does **not** provide, so no later reader infers one from silence.

**Demonstrated.** A17 seals a payload to B03. M99 — a peer whose Ed25519 key
B03 already accepts — copies the `EPK`, `NONCE` and `CIPHERTEXT` bytes
unchanged, rewrites `FROM` / `FROM_KID` (and `TOPIC`, `K`, `CREATED`) to its
own, and signs the result with its own key. Every check passes: `CIPHER_HASH`
matches the untouched ciphertext, M99's key is accepted for its seat, the
signature covers the whole domain, and `open` binds B03's seat, fingerprint and
private key. B03 decrypts A17's plaintext and the container says M99 sent it.
M99 never read the payload.

**Why the construction allows it.** The AEAD's associated data is empty and the
payload key is `HKDF(ECDH(ephemeral, recipient static))` — nothing in the
sealed layer binds the sender's identity. The Ed25519 signature is over the
header, and the header commits to the ciphertext, so the signature proves
exactly this: *this accepted key put these exact ciphertext bytes on this
envelope to this recipient.* It does not prove the signer produced, could read,
or was the first to send the plaintext. This is surreptitious forwarding; it is
a property of encrypt-then-sign without a sender-bound KEM, not a bug in the
implementation of D-028.

**Decided (no code change).** The guarantee boundary is stated explicitly here,
in `02-SAIENVELOPE-v0.md` §4 and in the D-028 `SECURITY_PROPERTIES` list:
`FROM` is the accepted key that sent this container, never proof of authorship.
Anything that needs authorship — a legacy packet, a promotion, an evidence
chain — carries it inside the payload, where SAILANG `SRC` and the evidence
refs already live and are covered by the same signature.

**PROTOCOL_CHANGE_PROPOSAL (not adopted; a v1 wire decision).**

- **PRIMITIVE:** unchanged — X25519 + HKDF-SHA256 + ChaCha20Poly1305, Ed25519.
- **CHANGE:** bind the sender to the sealed layer, either by feeding the
  canonical unsigned header bytes to the AEAD as associated data, or by mixing
  `FROM_KID` into the HKDF `info`. Either one makes a re-signed copy fail
  decryption instead of succeeding under a new name.
- **PROPERTY_GAINED:** a decrypting recipient learns that the signer is the
  party that sealed these bytes to it.
- **PROPERTY_NOT_GAINED:** still no proof the sender authored the plaintext it
  sealed; a sender who legitimately received a plaintext can always reseal it.
- **MIGRATION_IMPACT:** every existing container stops decrypting, so this is a
  wire version, not an in-place repair. No `.senv` object exists today, so the
  cost is currently zero and will not stay that way.
- **WHY IT IS NOT DONE HERE:** `SRC-013` authorizes repairs that do not change
  persistent wire semantics. This one does. It is a decision, and it is made
  once, on evidence, with the v1 question open in `02-SAIENVELOPE-v0.md` §7.

---

## D-032 — One envelope, one byte representation, one transport identity

Recorded while independently reviewing T-36 under `SRC-013`. D-028 already
decided the invariant — "exactly one byte representation per header" — and
D-031 built `ENVELOPE_ID` on top of it. The parser did not enforce it.

**The defect class: a second accepted spelling of one object.** Two byte-
distinct containers both parsed, both verified and both opened to the same
plaintext, while `envelope_id` returned two different ids:

- **Missing final LF.** `parse_header` popped one trailing empty line, so a
  container with its final LF stripped was accepted as canonical.
- **Base64 last quantum.** `base64.b64decode(..., validate=True)` checks the
  alphabet, not the discarded bits of the final quantum: `YQ==` and `YR==`
  decode to the same byte. The ciphertext line therefore had several accepted
  spellings whenever the sealed bytes were not a multiple of three.

Neither is a signature break — the signed domain covers header fields, not the
container's outer encoding — which is exactly what made it dangerous. A relay
that adds or removes one byte mints a new `ENVELOPE_ID` for an envelope that is
cryptographically identical, so the D-031 contract "the same `ENVELOPE_ID` seen
again is a duplicate delivery event" would never fire, and a future Post Office
would count one message as many. The attention economy the whole system is
built on (R0..R4) is a budget; an unbounded id supply spends it.

**Decided.** `parse_header` compares the input against the canonical rendering
of what it just parsed and refuses `NON_CANONICAL_CONTAINER` on any difference.
One equality closes both holes and every later serializer slack with them:
whatever `seal` produces is accepted, and nothing else is. The check runs after
the bounded field validation and before any crypto, so it costs a malformed
input nothing.

**MIGRATION_IMPACT: none.** No `.senv` object exists; every container `seal`
has ever produced is canonical and still parses. Only containers SAIMAIL never
emitted are now refused.

**Wording aligned.** `envelope_id` documents what it measures: it hashes the
bytes it is given, by design and without a key or a parse, and it is the
identity of a transport *object* where those bytes are a container
`parse_header` accepts — which is now one spelling per envelope. D-031's
"exact canonical SENV1 container bytes" and the implementation now mean the
same thing.

---
## D-031 — Post Office preconditions: transport identity, CREATED vs RECEIVED_AT, duplicates, and the pending attention floor

Recorded while building T-36 Target C under `SRC-012`. Semantics only: no Post
Office store, queue, TTL sweep or renderer is started by this entry.

**ENVELOPE_ID.** The transport-object identity is derived, never declared:

```
ENVELOPE_ID = sha256(exact canonical SENV1 container bytes)
```

- same exact container bytes -> same `ENVELOPE_ID`;
- the same plaintext sealed again is normally a different transport object
  (fresh ephemeral key and nonce), therefore a different `ENVELOPE_ID`;
- `ENVELOPE_ID` is not plaintext identity, semantic-message identity, knowledge
  identity, evidence identity, sender identity or trust.

It is not a signed header field: a derived identity already covers every
container byte, and a declared copy would be one more thing to keep true.

**CREATED vs RECEIVED_AT.** `CREATED` is sender-authored, signed, and declares
when the sender says the message was created. `RECEIVED_AT` is a receiver-local
observation, created when the transport object enters a given Post Office.
They are not interchangeable; future ordering or TTL policy must not silently
treat `CREATED` as `RECEIVED_AT`. A sender may provide a stale, future or
simply incorrect `CREATED` without changing any receiver-local `RECEIVED_AT`.

**Duplicate delivery.** Observing the same `ENVELOPE_ID` again is a duplicate
delivery event, not a new message -- and not the same as the same semantic
plaintext resealed into a new envelope, which is a different transport object
with a different id. A future Post Office may retain `FIRST_RECEIVED_AT` and a
duplicate count as duplicate-event metadata; this entry does not implement the
store.

**Attention floor (pending T-5 decision, carried under `B-014`).** The
stability experiment observed one participant answering `IGNORE` in all three
repeats for an item whose claim carries a term the reader's dictionary does not
define -- an item the deterministic selector opens for exactly that reason.
Before T-5 is implemented, one explicit, evidence-backed decision is required:
may model judgment downgrade `MACHINE_REQUIRED_OPEN`? The strong candidate is a
floor -- `DEFER -> OPEN` and `OPEN -> OPEN_R3` may increase attention, while
`MACHINE_REQUIRED_OPEN -> DEFER` and `MACHINE_REQUIRED_OPEN -> IGNORE` are
potentially forbidden. No selector semantics change inside this wave.

---

## D-030 — Recipient key acceptance is receiver-owned, and open binds seat, fingerprint and private key

Recorded while building T-36 Target B under `SRC-012`. D-028's `open` proved
only that `TO_KID` equals the fingerprint of the presented private key; it did
not prove that the `TO` seat is authorized to use that key, so a sender could
define another participant's seat-to-key identity by choosing the pair. The
sender side already had `KEY_IDENTITY != KEY_ACCEPTANCE`; this entry applies the
same split to the recipient.

**Decided.**

- `RecipientKeyRegistry` (in `saimail.envelope`) is the receiver-owned
  seat -> accepted X25519 fingerprint registry, the mirror of the sender-side
  `KeyRegistry`.
- The normal open path accepts only when all three agree: the header's `TO`
  seat is known to the registry, its `TO_KID` fingerprint is accepted for that
  seat, and the presented private key matches that fingerprint.
- Refusal states: `UNKNOWN_RECIPIENT_SEAT`, `RECIPIENT_KEY_NOT_ACCEPTED`
  (new, beside the existing `RECIPIENT_KEY_MISMATCH`), plus the type guards
  `NOT_X25519_KEY` and `NOT_A_RECIPIENT_REGISTRY`. Error strings never carry
  private key material or plaintext.
- A sender cannot self-authorize a recipient identity: the registry is held by
  the receiver and is never constructed or extended from envelope bytes. No
  network discovery, no TOFU, no automatic enrollment, no group identity.
- Rotation is unchanged (D-028 B6): a retired sender public key may stay for
  historical signature verification; historical decryption of an envelope
  encrypted to a retired recipient key needs that retired private key, and no
  decryptability is claimed that key rotation cannot demonstrate.

---

## D-029 — SENV1: no forward-secrecy claim, and one bound signature domain

Recorded while opening T-36 (`SRC-012`). Two defects in D-028 are corrected in
place; no primitive, field or construction changed beyond the signed byte
sequence.

**The claim that was false.** D-028 said the ephemeral X25519 key "gives
payload-recovery forward secrecy". It does not, against compromise of the
recipient's static private key: given the stored ciphertext, the stored `EPK`
and a later-compromised recipient private key, the historical shared secret is
recomputed and the payload opens. The truthful property, stated without the
phrase:

- every envelope uses a fresh sender-side ephemeral X25519 key;
- no static sender ECDH key is required or used;
- the ephemeral private material is not retained;
- historical confidentiality still depends on the secrecy and retention of the
  recipient's static private key.

**The domain that was missing.** `SIG` covered only the header field block, so
the signed bytes carried no protocol/version context. There is now exactly one
canonical signed byte sequence:

```
SAIMAIL-SENV1-SIGNATURE\0 || canonical unsigned SENV1 header bytes
```

`FIELD:value` lines in the fixed D-028 order, LF, final LF, UTF-8, no BOM;
`SIG` excluded from its own input; `FROM`, `FROM_KID`, `TO`, `TO_KID`, `K`,
`TOPIC`, `CREATED`, `TTL`, `REF`, `CIPHER_HASH`, `EPK` and `NONCE` all inside
the domain; duplicate fields and unknown fields are refused by the parser before
any crypto. Nothing relies on dict iteration order, serializer behaviour or
parser normalization.

**MIGRATION_IMPACT: none.** A3 checked before the change: no `.senv` file exists
anywhere in the repository or project artifacts, and SENV1 bytes exist only as
ephemeral, test-generated data.

**NON_GOALS, stated so a later reader does not mistake the wording:** no
ratchets, no recipient prekeys, no double ratchet, no ephemeral recipient
infrastructure, no Signal-like sessions, and no forward-secrecy claim.

---

## D-028 — SENV1 v0: wire, signature domain, key identity and crypto construction

Recorded before any T-3 code, as `SRC-011` requires. Where this entry and
`02-SAIENVELOPE-v0.md` disagree, this entry is the decision; the spec document
was updated to state the same contract, not to argue with it.

### Construction (`cryptography`, maintenance path)

`cryptography` supplies every primitive: Ed25519 signatures, X25519 ECDH,
HKDF-SHA256, ChaCha20Poly1305 AEAD. SHA-256 comes from `hashlib`; randomness
from the library's own key generation and `os.urandom` for the nonce. Nothing
here implements curve arithmetic, an AEAD, a KDF or a random generator.

Sealing (one recipient; group sealing is out of scope, `SRC-011` B7):

```
ephemeral X25519 keypair per message          (library RNG)
shared  = ECDH(ephemeral private, recipient public)
key     = HKDF-SHA256(salt = ephemeral public key, info = b"SENV1-v0 payload key", ikm = shared)
nonce   = 12 bytes from os.urandom
ciphertext = ChaCha20Poly1305(key).encrypt(nonce, payload, aad = b"")
```

The AEAD's associated data is empty on purpose: the ciphertext is bound to
the header through `CIPHER_HASH` plus the signature, and both are checked
before decryption. The sender's Ed25519 key is the only authentication of the
sender. The per-message ephemeral X25519 key is freshness, not forward secrecy:
no static sender ECDH key exists and the ephemeral private material is never
retained, but historical confidentiality still depends on the secrecy of the
recipient's static private key, so no forward-secrecy claim is made (D-029).

### PROTOCOL_CHANGE_PROPOSAL

- **PRIMITIVE:** X25519 + HKDF-SHA256 + ChaCha20Poly1305 for sealing; Ed25519
  for signatures.
- **SECURITY_PROPERTIES:** 128-bit AEAD confidentiality and integrity;
  sender authentication through the signature over the whole visible header,
  bound to the SENV1 protocol domain (D-029); a fresh sender-side ephemeral
  X25519 key per message, no static sender ECDH key and no retained ephemeral
  private material -- historical confidentiality depends on the recipient's
  static private key, and no forward secrecy is claimed (D-029); no
  recipient-visible metadata beyond the clear header by design (I2). The
  signature authenticates the sender of the container, never the authorship of
  the payload -- an accepted peer can re-sign another sender's ciphertext, and
  the sealed layer carries no sender binding (D-033).
- **DIFFERENCE_FROM_CURRENT_SPEC:** `02-SAIENVELOPE-v0.md` §4 said "age-style
  sealed box". The primitive set is the one age's X25519 stanza uses, but the
  construction is composed here rather than taken from libsodium's sealed-box
  API, and no age or libsodium wire compatibility was ever promised. Accepted
  for v0; recorded so a later reader does not mistake the wording for an
  interop claim.
- **MIGRATION_IMPACT:** none. No SENV1 bytes exist anywhere yet (re-confirmed
  before the signature domain changed, T-36 A3).

### Wire (canonical)

```
SENV1
FROM:<seat>
FROM_KID:sha256:<64 hex>
TO:<seat>
TO_KID:sha256:<64 hex>
K:<kind>
TOPIC:<token>
CREATED:<YYYY-MM-DDTHH:MM:SSZ>
TTL:<nD|nH>                     optional
REF:sha256:<64 hex>             optional
CIPHER_HASH:sha256:<64 hex>
EPK:<64 hex>
NONCE:<24 hex>
SIG:ed25519:<128 hex>

CIPHERTEXT:<base64>
```

- Fixed field order, UTF-8, LF, no BOM, final LF; exactly one byte
  representation per header, and per container: the parser compares the input
  with its own canonical rendering and refuses anything else
  (`NON_CANONICAL_CONTAINER`, D-032). Duplicate fields, unknown fields, wrong
  order, a missing marker or blank line, content after the ciphertext line,
  malformed key ids, hashes, signatures, EPK, nonce or base64 all refuse.
- `K` comes from the closed kind set in the spec; `TOPIC` is one token.

### Ciphertext hash (B1)

`CIPHER_HASH = sha256(ciphertext bytes)` — the exact sealed bytes, never the
plaintext. A receiver compares it before resolving keys or verifying. If a
plaintext content hash is ever useful it belongs inside the payload; the field
carries one meaning only.

### Signature domain (B2)

`SIG` signs one exact byte sequence: the protocol domain marker
`SAIMAIL-SENV1-SIGNATURE\0` followed by the canonical serialization of every
header line except `SIG` itself, in the fixed order above, as `FIELD:value`
lines joined with LF and a final LF, UTF-8, no BOM (D-029). `FROM`, `FROM_KID`,
`TO`, `TO_KID`, `K`, `TOPIC`, `CREATED`, `TTL`, `REF`, `CIPHER_HASH`, `EPK` and
`NONCE` are inside the domain. Duplicate fields and unknown fields are refused.
Nothing relies on dict ordering or parser normalization.

### Key identity and acceptance (B3, B4)

- `FROM_KID` / `TO_KID` are full fingerprints: `sha256:<64 hex>` over the raw
  32-byte public key — Ed25519 for the sender, X25519 for the recipient. A
  display prefix is never authority.
- Identity is not acceptance: a receiver-owned `KeyRegistry` records which
  exact sender keys it accepts for a seat. An unknown seat/key is
  `UNKNOWN_SENDER_KEY`; a known seat whose fingerprint is not accepted is
  `SENDER_KEY_NOT_ACCEPTED`. Both refuse; no TOFU, no automatic first contact.
- Verification order: bounded header parse, `CIPHER_HASH` compare, accepted
  sender key resolution, Ed25519 verification, recipient key resolution by
  `TO_KID` through the receiver-owned `RecipientKeyRegistry` (D-030),
  decryption, and only then does the caller parse the payload as data. The
  public API is `parse_header -> VerifiedEnvelope -> open`; plaintext is not
  reachable through any normal call before the signature succeeds.

### Rotation (B6)

A retired sender public key may stay in a receiver's registry for historical
signature verification. Historical decryption of an envelope encrypted to a
retired recipient key requires the retired private key; v0 does not custody
private keys, so no decryptability claim is made. Tests use ephemeral
in-memory keys, and no private key or plaintext may appear in a repository
file, receipt, report, log or error message.

### Bounds (B8)

Header ≤ 4096 bytes, ≤ 24 fields, container text ≤ 384 KiB, ciphertext
≤ 256 KiB + tag, plaintext ≤ 256 KiB, all enforced before any crypto call.

---

## D-027 — A slash in prose is not a path

Recorded while opening T-3 under `SRC-011`. The steward's correction receipt
contains the validation phrase `secret/private-key sweep`. The structural
credential detector (D-023) read the token as a path, the last component
`private-key` as a credential-labelled file name, and reported a finding on a
body that carries no credential. The invariant test then demanded a quarantine
of `SRC-011`, while the distribution-state test requires `SRC-007` to be the
only quarantined receipt — the detector's own rule was the defect. The receipt
is immutable and was not touched.

**Resolved.** `CREDENTIAL_LABELLED_FILENAME` applies only where the token has
a file shape:

- the name ends in an extension, or
- the token is anchored like a path — a backslash anywhere, a drive letter, a
  root, or `./`, `../`, `~/`.

`secret/private-key` is a hyphenated compound in running text and costs no
redaction. **Known limit, recorded:** an extensionless Unix-style relative
path (`secrets/prod-key`) no longer matches the filename rule. The
high-entropy and known-shape rules are unchanged, and the conservative bias
of the scan still points the same way.

**Why not quarantine `SRC-011` instead.** The distribution vocabulary and its
tests declare exactly one credential-bearing receipt. Quarantining the
steward's own instruction would withhold the correction from distribution and
create a second false positive rather than fix the first.

Regression: `tests/test_quarantine.py::test_a_slash_in_prose_is_not_a_path`
holds both directions — prose stays unflagged, a Windows path and a rooted
path stay flagged.

---

## D-026 — A control that has never been seen to fail proves nothing

Recorded while closing T-4 under `SRC-011`.

The I1 red control asserts a negative: command-looking text inside a SAILANG
record, a triage container or a receipt never reaches anything that acts
(`02-SAIENVELOPE-v0.md` §5). A negative no harness could falsify is a promise,
not a control, so the surface is two halves that must agree:

- **The control.** Every hostile payload in the corpus runs through every
  public data path while a tripwire sits on each way this process could act on
  text: process spawn, code execution, dynamic import, socket connect,
  filesystem write. The tripwire must stay silent, and a hostile claim must
  earn exactly the verdict a harmless claim of the same shape earns.
- **The red control.** A deliberately vulnerable router — payload words mapped
  onto actions, on purpose — runs through the same harness, and the tripwire
  must be observed to fire on each sink. Only then does the silence above
  count as a measurement.

**The wire must be sharp enough to stay usable.** The first version wired
`eval`/`exec` unconditionally and fired while importing `_strptime`: Python's
import machinery executes a code object, not payload text, and the test runner
itself compiles source while rendering a failing test. A wire that cannot tell
payload text from the interpreter's own source reds on the tools, not on the
defect. The rule kept here:

- trip when **textual source** (`str`/`bytes`) reaches `eval`, `exec` or
  `compile` **from code that lives in this repository** — the shape every
  payload-to-code route has to pass through;
- pass through when the call comes from outside the repository (the
  interpreter, the import machinery, the test runner);
- dynamic import (`importlib.import_module`) trips unconditionally.

The remaining hole is stated rather than hidden: a dependency executing
payload text would sit outside the repository's frames. The library's import
surface is bounded to data-only modules by an ast audit in the same test file,
so that hole is closed structurally, not by the wire.

Both directions are tested: a payload string trips the wire, an
already-compiled code object does not, and a vulnerable router that reaches
each sink with payload text is observed to fail.

---

## D-025 — One response is not a model property

**The defect.** Runs 4 and 5 sent the identical `S3.mailbox` prompt to the
identical model four minutes apart; it answered item M1 `OPEN` once and `DEFER`
the next time. Every per-model sentence in this lab's history rests on one call
per unit, so none of them could tell a model's behaviour from one draw of it.

**Decided.** A small repeat sample, registered before it runs
(`lab/stability.py`, frozen in `lab/stability_registration.json`, its digest
logged before the first live call):

- four existing units with their existing schemas, expectations and graders —
  `FACTUAL_UNVERIFIED` (`S1.evidence_absent`), `EV0_ATTACHMENT`
  (`S4.ev0_is_not_weak`), `OPEN_VERSUS_DEFER` (`S3.mailbox`) and
  `RELATION_CONTRADICTION` (`S1.contradiction`);
- `N = 3` identical calls per available participant per case, in the order
  round, case, participant; role A is the combo alias and role B one external
  comparator when one answers (D-020, D-024);
- a cap of 32 calls: the whole plan plus the discovery reserve.

The runner refuses to call anything when the code and the registration
disagree. Raising `N` after a result is not an edit; it is a new registration,
and the old one stays on the record.

Reported per model, route, scenario and protocol version: verdict counts,
answer counts per boundary, and for `S3.mailbox` the attention classes per item
(D-022). Three findings, kept apart because they mean different things:

```
MODEL_VARIANCE            one participant, one stimulus digest, different answers on a boundary
CROSS_MODEL_DISAGREEMENT  participants each unanimous on a boundary, with different answers
PROTOCOL_HOTSPOT          two or more distinct models each failing the registered
                          expectation on one boundary in at least two of three repeats
```

A boundary is one question field or one mailbox item. Unparsed answers and
transport failures are counted and never feed a finding. Nothing is scored,
ranked or merged, and no motive or hidden reasoning is inferred. Opaque context
stays recorded per call as local estimate, gateway-reported input and their
difference.

Three repeats is still a small sample. It can show that one answer was not a
model's only answer; it cannot say what the model's answer is.

---

## D-024 — A live run is named by its membership evidence, never by its participants' eligibility

Clarifies D-020 and the T-28 record additively. Neither is rewritten.

**The defect.** Runs 4 and 5 sent role A through the SAIFREN alias and put an
independently selected catalog model beside it as role B, labelled
`NOT_PROVEN_COMBO_MEMBER`. The label was correct and the result was correctly
called heterogeneous — and "participants discovered from the population", "two
distinct observed participants" and "SAIFREN is the population" all read
naturally as *two SAIFREN members*. Nothing in either run shows role B is one.
The distinction lived in one field of one participant record.

**Decided.** Every live artifact states what it is, derived from membership
evidence inside that run (`lab/experiment_class.py`, rule
`saifren-experiment-class/1`):

```
SAIFREN_INTERNAL             every answering participant an observed member; at least two members
SAIFREN_EXTERNAL_COMPARATOR  at least one observed member plus at least one external live model
SAIFREN_SINGLE_ROUTE         exactly one observed member, nothing external; no cross-member claim
SAIFREN_NOT_OBSERVED         something answered, no answering participant is an observed member
NOT_MEASURED                 nothing answered
```

**Membership evidence is one thing:** a call in the same run that requested the
combo alias and was answered with a reported model other than the alias. A
discovery probe that did the same counts. A catalog listing, a `member_status`
field, and a model's appearance in an earlier run do not.

Every artifact carries `experiment_class`, `combo`, `observed_combo_members`,
`external_comparators`, `distinct_reported_models` and `roster_status`, and the
mechanical report prints them first and labels every route line as an observed
member or an external comparator. `roster_status` is `NOT_OBSERVABLE` until a
roster is actually read; the population record's `ROSTER_NOT_EXPOSED` is kept as
its basis, not renamed. Every call record now names the model id it requested.

Stored artifacts are not edited (D-022). They are classified as they stand, on
the weaker basis they carry — the population record for runs 4 and 5, the
harness routes for runs 1 to 3 — and `lab/LATEST.md` shows the result: run 1
`SAIFREN_SINGLE_ROUTE`, runs 2 and 3 `SAIFREN_NOT_OBSERVED` (both participants
were pinned catalog ids), runs 4 and 5 `SAIFREN_EXTERNAL_COMPARATOR`. No run is
`SAIFREN_INTERNAL`.

`9router -> SAIRoute -> SAIFREN` stays the canonical live lab. When no proven
multi-member roster is available, an external comparator run is still worth
running; it is named for what it is.

---

## D-023 — A credential-bearing receipt keeps its identity, not its distribution

`SRC-007` is an immutable receipt whose body carries a file name that, per the
operator (`SRC-009`), embeds a credential value. Its intake metadata says
`sensitive: false`, SAIPEN's credential gate reports it safe, and every normal
export ships it. Immutability had quietly become a promise to distribute that
credential forever.

**The receipt is not touched.** Its bytes, digest, metadata and segment map stay
exactly as captured. What changes is where its bytes may travel:

```
ACTIVE_NORMAL          no quarantine record; travels as it is
SENSITIVE_QUARANTINED  id, digest, length and reason travel; the plaintext does not
SANITIZED_DERIVATIVE   the body with each credential-bearing component replaced by
                       an explicit marker, hash-bound to the original
```

These are distribution states beside the intake lifecycle status, never a new
meaning for it. `saimail/quarantine.py` holds the vocabulary and the checks;
`tools/quarantine_receipt.py` is the only writer; `provenance/quarantine/` holds
the record and the derivative.

- **Proven by structure, never by quotation.** A deterministic scan reports a
  category, a line and a byte span. No test, report, record or file name
  carries the material; the tests prove that by searching every surface in
  memory for every fragment of the withheld component.
- **A representation is not an instruction.** The derivative has no segment map
  and cannot be cited. Its authority is the original's, resolved through the
  original's map and the digest the record preserves — so `SRC-007` and the
  backlog entries derived from it stay `USER_ACCEPTANCE` whether the original is
  present or not. Redaction adds no class and removes none.
- **Withheld is unresolved, not guessed.** A span that overlaps a redaction reads
  as `UNRESOLVED`; line 3 of `SRC-007` is recorded that way.
- **A normal distribution excludes the original by path** and carries the
  record, the derivative and the intake metadata. Where the original exists, the
  derivative is re-proven against it; where it does not, the derivative is
  `HASH_BOUND` and says so.

**Two limits, recorded rather than discovered later.** Quarantine is not a
cryptographic boundary: the original digest travels, and it is an offline
guessing oracle for a short or word-like component, so rotation is the remedy
and quarantine only stops redistribution. And SAIPEN's own exporters still ship
the original, because keeping a SAIPEN receipt out of SAIPEN's export needs
SAIPEN Core semantics; that requirement is stated with evidence in
[PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md](PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md)
and not worked around here.

---

## D-022 — Observed scope is not successor scope, and a measurement is not a score

Recorded after the fact across T-25 and T-26. Three places where one word was
covering two different things, fixed the same way each time: name both.

**Observed scope versus successor scope.** A legacy packet says what an
investigation *saw*. A successor task says what the next agent should *do*. When
the packet's caveat — "measured on worker-7 only" — is dropped on the way
across, the successor inherits a finding with a wider scope than anything anyone
observed. `scope_retention` is measured separately from
`task_relevant_semantic_retention` for that reason: a packet can transfer the
useful part of a finding and still lose the sentence that bounds it.

**`PASS` versus what happened to each item.** Run 3's `S3.mailbox` PASSed with
the deterministic selector saying `OPEN` and the agent saying `DEFER`. The PASS
is right — the registered failure is a *false ignore*, an opened item the agent
drops, and a deferred item is kept. But `PASS` was the whole report, and the
disagreement vanished into it. Four outcomes are now named and counted beside
the verdict, never inside it:

```
EXACT         agent matches the selector
FALSE_IGNORE  selector OPEN   -> agent IGNORE      the item is dropped
UNDER_OPEN    selector OPEN   -> agent DEFER       the item is kept, not read
OVER_OPEN     selector DEFER/IGNORE -> agent OPEN  context spent uninvited
```

Plus `OTHER` for the pairs those four do not cover and `UNANSWERED` for an item
with no parsable answer, because a bucket that absorbs what it was not defined
for is how a measurement starts lying. **`UNDER_OPEN` is not defined as a
failure.** An agent saying *keep this, not now* may be making the better call.
It is an observation; whether it is a problem is a question, not a verdict.
Historical verdicts are not regraded: the vocabulary is applied to stored
evidence, and every run's recorded PASS or FAIL stands as measured.

**One report file versus one report per run.** `lab/out/SAIFREN_REPORT.md` was
overwritten by each run, which deleted the evidence the previous interpretation
cited. Reports are now stamped per run, interpretations live in
`lab/analysis/<stamp>.md`, and `lab/LATEST.md` says which is current. Old
readings stay readable, including where a later run contradicts them.

---

## D-021 — A frame ABI version is bumped when evidence semantics change

Recorded after the fact: T-24 made the change; this entry states the rule it
followed.

Under `SAIB3`, an evidence field was present or it was not, and a reader had to
guess which of two very different things an absence meant: *the author asserted
there is no evidence* or *this channel cannot carry one*. D-009 had already
settled that omission is not silence for a record; the frame had not caught up.

`SAIB4` carries three states explicitly:

```
ATTACHED          an admissible evidence reference is present
EXPLICITLY_ABSENT the author asserts none is attached (EV:0)
NOT_APPLICABLE    this kind cannot carry one at all
```

**Why a version bump rather than a compatible addition.** A `SAIB3` reader
handed a `SAIB4` frame would read `NOT_APPLICABLE` as *absent*, and quietly turn
"the question does not apply" into "the author says no". That is a semantic
change to an existing field, not a new field, so the wire version says so:
`SAIB3` / `SAIP3` stay decodable and keep their historical meaning, `SAIB4` /
`SAIP4` are the current encoding, and the v0 line baseline is frozen as the
control it was always meant to be (D-011).

The rule, stated once: **a field whose old values would be misread under the new
meaning needs a new version number.** Adding a field nobody has to understand
does not.

---

## D-020 — Participants are discovered from the population, not pinned in source

Recorded after the fact: T-25 achieved two observable routes, T-26 changed where
they come from.

**The defect.** The harness held two model identifiers as constants, sent them
to the gateway, and reported that two models disagreed. True, and beside the
point. Nothing in the run observed SAIFREN, so nothing in the artifact could say
which population was tested; and the day somebody edits the combo, the
constants keep working and keep being wrong. A live experiment whose
participants are an assertion is measuring the assertion.

**Decided.** `9router -> SAIRoute -> SAIFREN -> selected current member(s)` is
resolved at run time, from what the authorized read-only surface actually shows.

**What that surface gives, and what it does not.** `GET /v1/models` lists the
combo (`owned_by: "combo"`) and the full eligible catalog. It carries **no
member list**, and the administrative endpoint that might refuses the SAIRoute
credential. So the roster is recorded as `ROSTER_NOT_EXPOSED` and membership is
*sampled*: bounded calls to the combo alias, each of which the gateway resolves
to a concrete model and reports back. Every distinct model reported that way is
an observed member, because the gateway chose it.

A sample is not a roster, and the code says so rather than rounding up. An alias
sample of *n* cannot tell a one-member combo from a combo with a deterministic
primary, the artifact carries that note, and a sample that observes nothing
records `SAIFREN_MEMBERSHIP_NOT_OBSERVABLE` instead of dressing constants up as
membership.

**Selection, declared before any run** (`saifren-selection/1`): role A is the
alias itself, whatever it resolves to. Role B is drawn from the observed
catalog — the best entry of each namespace, ranked by capabilities stated, then
context length, then id, with an operator preference available through an
environment variable so a change to the population never needs a source edit —
and it becomes a participant only after a probe answers *and* reports a model
different from role A's. It is labelled `NOT_PROVEN_COMBO_MEMBER`, because an
unobservable roster cannot be claimed.

**Replacement, also declared before any run** (`saifren-replacement/1`): a
candidate that fails at the transport is replaced by the next ranked one, at
most a fixed number of probes, all spent from the same call budget. It fires
only while resolving participants, never during the experiment, and no answer's
*content* ever triggers a retry. Runs 2 and 3 both hit bounded upstream
overloads on one member; that is a reason to have a declared policy, not a
licence to re-roll until an answer looks better.

**A transport failure is not a disagreement.** A route that did not answer said
nothing. Unanswered units are `ERROR`, never `FAIL`, and are never graded.

Every heterogeneous artifact records the combo, when membership was observed,
the catalog and membership digests, the observed members, the selection rule and
replacement policy, each participant's requested id, reported model and member
status, and the provider **only when the gateway states it** — a model id prefix
is a namespace, not a provider claim.

---

## D-019 — A credential is resolved from a named handle, never inherited from the environment

Recorded after the fact: T-23 built the resolver and T-26 made it the only path
an ordinary command takes. This entry describes what is implemented; it is not
permission to build more.

**The defect.** `lab/saifren_run.py` resolved the credential store *and*, if
that came back empty, `SAIROUTE_API_KEY`. Two authorities with an invisible
order between them. An inherited variable — from a parent shell, a CI job, a
stale `.env` somebody sourced in March — would satisfy the run silently, and the
artifact would say nothing about which one had authenticated it. A secret nobody
can point at is a secret nobody can rotate or revoke.

**Decided.** One logical handle, and exactly one source per run, named by the
caller:

```
credential://9router/sairoute   ->  resolver  ->  local credential store  ->  transport
```

* `--credential-source store` (the default) reads the credential store and
  nothing else. Absent is `SAIROUTE_CREDENTIAL_NOT_PROVISIONED`, never a
  fall-through.
* `--credential-source env` is the explicit legacy mode. It reads
  `SAIROUTE_API_KEY` and nothing else, and the artifact records
  `credential.source`.

There is no precedence rule, because the defect *was* the precedence rule.
Compatibility is kept — an existing workflow that exports the variable still
runs — but it has to say so, and the evidence says so too.

**Two consequences, both implemented.**

*The backend is checked, not assumed.* "Windows Credential Manager via keyring"
was a claim about an import. `keyring` selects a backend at run time and one of
them stores nothing at all, so on Windows the resolver now requires
`WinVaultKeyring` and reports `SAIROUTE_CREDENTIAL_BACKEND_UNSUITABLE`
otherwise, looking through `ChainerBackend` rather than naming the dispatcher.

*Provisioning is interactive or it does not happen.* The tool used to fall back
to `stdin.readline()` off a TTY, which makes `echo SECRET | provision.py` work —
and puts the credential in shell history and the process table, the exact
exposure the store exists to remove. The non-TTY path is gone, no `--key` or
`--secret` replaces it, and a pipe gets
`SAIROUTE_PROVISIONING_REQUIRES_TTY`. Tests inject a fake backend and replace
the prompt; the suite never touches the real store.

---

## D-018 — Live agent output is experiment data, and the harness may not contradict itself

T-17 runs real agents from the SAIFREN population through 9router. Their answers
are measurements of how a rendering is read, never a vote on what is true.

```
LIVE OUTPUT = EXPERIMENT DATA
not CONSENSUS, not TRUTH, not a PROTOCOL CHANGE, not USER INTENT
```

- Every artifact carries `authority: EXPERIMENT_DATA`. Disagreement is kept per
  call beside the route that produced it; nothing is merged, voted or scored.
- A repeated failure may justify **proposing** a protocol change. A proposal
  stays a proposal until the steward accepts it.
- One answer schema per call drives both the prompt and the grade, so a correct
  participant cannot fail because the harness asked for one spelling and graded
  another (the S2 defect: `RUNG: unverified` asked, `U1` graded, and a forbidden
  phrase `verified` matching inside `unverified`). Grading is mechanical; free
  text is measured beside the grade and never folded into it.
- Handoffs are real: what agent B reads is agent A's output after a declared,
  deterministic, refusing transform through `Record.create`, so an inflated
  finding is stopped by SAILANG's own rung gate instead of reaching B.
- The credential comes from the environment only and is checked for absence
  before any artifact is written; reasoning fields are dropped before storage; a
  provider is recorded only when the gateway states one.

The contract is `tests/test_lab_contract.py`; the grader is `tests/test_lab_grader.py`.

---

## D-017 — A receipt's intake kind is transport; segments are authorship (RECEIPT-KIND-SCOPE-01)

SRC-005 carries `source_kind: user_instruction` in its immutable intake
metadata and is wholly `AMBIGUOUS` in its segment map. Both are true, about
different questions, and a consumer that only knows the metadata reads the
transcript as a user order.

The receipts are not rewritten. The scope of the field is fixed instead, in a
form a machine can check:

- `provenance/RECEIPT_KIND_SCOPE.json` declares that `source_kind` is
  `TRANSPORT_INTAKE_ONLY` and that authorship authority is
  `SEGMENT_PROVENANCE`. `load_maps` refuses to load maps without it.
- Every segment map repeats `receipt_source_kind_scope: TRANSPORT_INTAKE_ONLY`,
  so a consumer holding only a map still reads the rule; a map that omits or
  weakens it is refused.
- `receipt_intent_authority` answers for a whole receipt. Metadata may be passed
  and only its digest is read. Any `AMBIGUOUS` span refuses; any other
  non-intent span refuses as `MIXED_AUTHORSHIP`; no map refuses. An ast audit
  proves no authority function reads `source_kind`.
- `source_kind_conflicts` lists every receipt where the naive reading would
  mislead, as rows with the verdict `SOURCE_KIND_IS_NOT_AUTHORSHIP`.

The steward's T-17 correction was captured as `SRC-006` from exactly one host
user turn, extracted mechanically rather than retyped. Its map declares the
capture channel and classes it `USER_ACCEPTANCE`: the channel proves the
steward sent the instruction, which adopts it; who drafted the words is not in
the bytes, so `USER_INTENT` is not claimed.

---

## D-016 — One semantic atom, one canonical wire encoding

An atom with an abbreviation could previously travel either way: `QSTALE` or
`QUEUE_OWNERSHIP_STALE`, both decoding to the same atom. Two spellings for one
meaning is two cache keys, two dedup keys, two things to sign, and one more
shape an attacker can pick between.

Under a given profile an atom has exactly one legal encoding. A frame carrying
the long form where an abbreviation exists is refused with
`NON_CANONICAL_ENCODING` — not silently accepted, and not treated as an unknown
token either, because it is neither.

An atom with no abbreviation still travels verbatim; that is its canonical
encoding, not an alternative to one.

---

## D-015 — Profile identity is not profile acceptance

A digest proves *these semantics have this identity*. It says nothing about
whether a receiver agrees to read anything under them, and treating the two as
one is how arriving content ends up supplying the dictionary that gives its own
tokens meaning.

```
PROFILE_IDENTITY   = deterministic identity of exact profile semantics
PROFILE_ACCEPTANCE = receiver-owned authorization to interpret wire under them
```

- Acceptance lives in a receiver-owned registry (`saimail.acceptance`), holding
  `Profile` objects the receiver loaded itself. Two states, `ACCEPTED` and
  `UNKNOWN`; `REJECTED`/`REVOKED` are omitted because nothing in current
  behaviour distinguishes them from `UNKNOWN`, and a state that changes no
  decision is a state that will eventually be wrong.
- `receive(container, registry)` is the **only** public route from raw wire to
  decoded views. It reads the identity the container claims, asks the receiver
  whether that identity is acceptable, and only then parses.
- An unknown profile fails closed. Never a guess, never a default.
- `bind_verified` is gone from the public surface and is now the internal
  `_bind_verified`. An assertion-style public API lets any caller declare a
  profile nobody checked, which is precisely the escape hatch D-013 closed one
  layer up. **This is a correctness / type-state boundary, not a security
  boundary** — Python privacy stops accidents, not adversaries.
- `Profile.inline` stays for tests and benchmarks and is not a trust path for
  external input: nothing external reaches it.

---

## D-014 — One dependency contract, and the advertised command honours it

`pyproject.toml` advertised `python -m pytest -q` as runnable with the `test`
extra, while four tests in the suite import `tiktoken`, which only the `bench`
extra installed. A command documented as reproducible that an optional
dependency can break is not reproducible.

Contract chosen (option A of the two offered): **the `test` extra installs
everything the full suite needs**, tokenizer included. `bench` remains as an
alias for the same set so existing instructions keep working. The alternative —
marking benchmark tests and documenting two commands — was rejected because it
puts the burden on every future reader to remember which command is the real
one.

---

## D-013 — Raw wire is not decodable; the container establishes the binding

`decode(raw_string, profile)` was an escape hatch. A raw frame carries no
profile identity, so supplying the wrong profile left nothing to check against:
the caller asserted provenance and the decoder believed it.

The boundary is now one-way and has no side entrance:

```
raw wire -> Batch.parse(text, profile)   <- the only place a profile is asserted,
                                            and it is verified against the
                                            container header
         -> bound TriageFrame            <- carries the verified Profile itself
         -> decode(frame)                <- takes no profile argument at all
```

A `TriageFrame` holds a `Profile`, not a profile id, so a frame cannot exist
without the binding its container proved. `decode` of a `str` refuses with
`UNBOUND_WIRE`. There is no default profile, no current profile, and no
inference — a frame produced under profile A cannot be read under profile B by
any public path.

---

## D-012 — Atom, wire and render are three different things

The v0 dictionary mapped `BLOCKED -> BLK` and `BLOCKER -> BLK`. Two different
concepts arriving as one token is exactly the ambiguity the protocol forbids,
and the old "zero semantic inversions" metric never caught it because it only
checked coarse triage fields, never claim meaning.

| Layer | What it is | Authority |
|---|---|---|
| **atom** | canonical semantic identity, e.g. `QUEUE_OWNERSHIP_STALE` | the meaning |
| **wire** | profile-specific abbreviation, e.g. `QSTALE` | transport only |
| **render** | human phrase, e.g. "queue ownership left stale" | none |

Rules:

- The atom → wire map **must be injective**, checked at load time and refused
  as `DICTIONARY_AMBIGUOUS` otherwise. A wire token that could mean two things
  is not a wire token.
- A `TriageView` exposes **atoms**, never abbreviations. No consumer should
  have to know what `QSTALE` means to act on a frame.
- Expanding a wire token into its atom is **not** reconstruction of the record,
  and is therefore allowed and required. `TriageFrame -> Record` stays
  forbidden; `wire -> atom -> TriageView` is the required path.
- A wire token this profile has no atom for stays **unknown**: it is reported in
  `claim_unknown_wires` and never resolved to the nearest-looking entry.
  Unknown is a state, not a prompt to guess.
- Deliberately collapsing two source concepts is allowed only by declaring a
  new, explicitly coarser atom and recording the information loss. Accidental
  many-to-one mapping is a defect.

`v1.json` splits `BLOCKED` (`BLKD`) from `BLOCKER` (`BLKR`) and states the
distinction in the file. `v0.json` is kept unchanged as the historical profile
the v0 line arm still measures against.

---

## D-011 — Profile framing is paid once, and the v0 line is kept as a baseline

T-9 measured the per-frame `L1D<v>|` marker at 225 tokens over 45 lines —
roughly five times what the dictionary it announces saves. Version information
is not deleted; it moves to a scope where it is paid once.

- A **profile** binds the frame format version, the dictionary version and the
  **dictionary content digest**. Its identity is `sha256:<64 hex>` over a
  canonical descriptor, so a dictionary revision produces a different profile
  and a historical frame can never silently acquire new semantics.
- A **batch** declares the profile once in its header and carries N frames.
- A standalone frame carries no profile, therefore **decoding one without a
  profile is refused**, never guessed. "Either carry sufficient profile identity
  or refuse interpretation" is satisfied by refusing.
- There is no implicit mutable global dictionary. The profile is passed
  explicitly or the operation fails.
- Decoding never expands a dictionary token back to its long form. Expansion is
  reconstruction, and reconstruction belongs to the canonical record.

The v0 line (`sailang/line.py`, per-frame marker) is **kept, untouched, and
still tested**. It is the control arm: T-9B measures v0.1 against a real v0
implementation instead of simulating the old format with string surgery. The
closed T-2 ticket's verify command also stays runnable, which is the point of a
verify command.

---

## D-010 — A triage frame is machine-decodable; only reconstruction is forbidden

D-002 said the line is "never parsed back". Taken literally that made SAILANG a
machine format no machine may read, which is not a format, it is a decoration.

The forbidden operation is narrower and sharper:

```
FORBIDDEN:  TriageFrame -> Record
REQUIRED:   TriageFrame -> TriageView   (typed, deterministic, non-authoritative)
```

Three explicit types, and the boundary between them is enforced in code rather
than promised in prose:

| Type | Authority | Can it be evidence | Can it reconstruct what it omitted |
|---|---|---|---|
| `Record` | authoritative, immutable, content-addressed | yes | n/a |
| `TriageFrame` | none | no | no |
| `TriageView` | none | no | no |

A `TriageView` carries **only what the frame actually carries**. Missing
information stays missing and is reported as `OPEN RECORD`, never inferred. No
API that requires a `Record` accepts a `TriageView`, and a test proves it.

D-002 stands otherwise: the frame is lossy, deterministic, never authoritative
and never cited as evidence.

---

## D-009 — `EV` is required for truth-apt records; omission is not silence

Until now a missing `EV` was treated as identical to `EV:0`. That let an author
forget to state evidence and have the format quietly say "none attached" on
their behalf — a default standing in for a statement nobody made.

For `F`, `O` and `H`, `EV` is now **required**:

```
EV:0                      evidence explicitly absent, asserted by the author
EV:sha256:<64 hex>[,…]    evidence attached
EV omitted                REFUSED — MISSING_FIELD
```

`SRC-001` does not speak to omission semantics, so nothing is contradicted. What
it does say is that the presence or absence of evidence is the load-bearing fact
in the whole design, and a load-bearing fact should be asserted, not defaulted.

`G` and `V` still forbid `EV` entirely: they are not truth-apt (D-004).

---

## D-008 — `C` and `D` are ledger verdicts, not authored rungs

Found while implementing T-1. The converged spec said `STATUS:C` requires
`REFUTES` and `STATUS:D` requires `CON`. Under D-003 that is incoherent: a
record is an immutable statement by its author at `CREATED`, and no author
writes a fresh claim whose own stated verdict is "contradicted".

`REFUTES` on a record means *this record refutes that one* — the refuting
record's own `STATUS` describes its own claim, which is normally high.

Resolved:

- **In a record**, `STATUS` is the author's rung for their own `CLAIM`, and the
  only legal values are `U0 U1 U2 U3 U4`.
- **`C` (contradicted) and `D` (disputed) are ledger verdicts**, projected over
  the `REFUTES` / `CON` edges between immutable records. They are never written
  into a record, because they are not something an author knows about their own
  statement at the moment of writing it.

This keeps the authority ladder intact: the ledger is a projection, and a
projection never becomes the authority.

---

## D-007 — T-9 may not be rigged (SAIHANDOFF, T-9 section)

The original T-9 verify clause was:

```
python bench/cost_compare.py --assert-ratio 10
```

Removed. A benchmark whose exit code depends on the hypothesis being true is
propaganda with a shebang. T-9 must be able to return `NO_GO`, and a `NO_GO`
is a successful experiment.

The replacement verify clause runs the benchmark and asserts only that it
produced a complete, machine-readable result over the full corpus.
