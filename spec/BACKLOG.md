# Backlog derived from the source receipts

Source requirements, not permission to build. Every entry names the receipt it
came from. Nothing here is implemented unless a board ticket says so, and an
entry being *measured* by a benchmark is not an entry being built.

Authority: `AUTHORITATIVE RECEIPT LINEAGE > DERIVED SPEC > IMPLEMENTATION > TESTS`. The receipts in this lineage are `SRC-003` and `SRC-004`.
Every entry below carries its provenance class; an entry with no cited acceptance is an
idea, not an instruction (`provenance/ATTRIBUTIONS.json`).

## From `SRC-004` (`idea_continue.md`, sha256 `cbe876fe…`; amends `SRC-002`)

### B-001 — SAILETTER / `HUMAN_PRIVATE`

Provenance: `AMBIGUOUS` source, adopted `USER_ACCEPTANCE_OBSERVED` (A3: preserved as backlog).

A third addressee class beside agent-private and human-public: a letter for one
named human, encrypted to that human's own cryptographic identity.

- Three classes: `HUMAN_PUBLIC` (today's SAINOTE), `HUMAN_PRIVATE`,
  `HUMAN_EPHEMERAL` (plaintext lives only inside one authenticated session).
- Authentication and encryption stay separate. FIDO2 proves presence; it is a
  door key, not a container. A PIV/OpenPGP identity whose private key never
  leaves the hardware token is what the letter is actually encrypted to.
- Recipient identity is cryptographic, not a name: `TO: human-id:<fingerprint>`
  with the display name as a label only. Another user of the same machine
  cannot simply press Open.
- The honest security boundary, stated in the receipt and binding:
  **ciphertext unreadable without the recipient credential; decrypted plaintext
  exists only inside the authenticated recipient session.** Nothing is claimed
  beyond that — a compromised OS, malware with administrator rights, or a
  camera pointed at the screen all remain outside what cryptography can promise.
- Recovery dilemma: `STRICT` (one key, no recovery, loud warning that losing the
  key kills every such letter) versus `RECOVERABLE` (recipient key plus a
  separately protected recovery identity). With a single physical token,
  `RECOVERABLE` is the only responsible default. Neither the server nor SAIMAIL
  ever holds a decryption key.
- Mail semantics worth keeping: the sender may discard its own plaintext and
  retain only hash plus metadata — "I know I sent letter X and I can no longer
  read it".
- Register: privacy is not a licence. A private channel never relaxes safety or
  authority boundaries (invariant `I1` applies unchanged). What it may drop is
  operational boilerplate — a personal letter needs no `STATUS / ACCEPTANCE /
  EVIDENCE / NEXT ACTION` scaffolding, and may simply be prose.

**DONE (D-042 / T-55).** `HUMAN_PUBLIC` remains the existing SAINOTE;
`HUMAN_PRIVATE` is `HLET1`/`HENV1` with explicit `STRICT`/`RECOVERABLE` modes,
recipient-bound P-256 crypto, sender authentication before any recipient
private-key operation, and a ciphertext-only `human-private` store.
`HUMAN_EPHEMERAL` stays unimplemented. The recovery sentence above is preserved
as historical planning evidence; the execution contract is
`NO_IMPLICIT_RECOVERY = true` (D-042), so `RECOVERABLE` requires an explicitly
supplied, cryptographically distinct recovery key and refuses without one.

### B-002 — `CID` / `EID` / `LID` identity separation

Provenance: `AMBIGUOUS` source, adopted `USER_ACCEPTANCE_OBSERVED` (A1: alias experiment instructed).

| Class | Purpose | Wire size |
|---|---|---|
| `CID` | immutable content identity | 256 bit |
| `EID` | entity / agent / message identity | 128 bit |
| `LID` | session- or batch-local alias | 8–32 bit |

The rule that makes it safe: **the short id is local, the long id is
canonical.** A global namespace of `A1`, `B2`, `T7` becomes a collision
graveyard within a year. A local alias must never become canonical identity.

Measured, not implemented, by the alias experiment in `bench/`.

### B-003 — Dynamic dictionaries and `DEF` frames

Provenance: `AMBIGUOUS` source, **never adopted** — an idea, not an instruction.

`D1=@1:agent-alpha,@2:T1342,…` once, then `@1>@2:+B:$@4` many times. A macro must
carry an immutable definition hash so nobody can redefine `Q7` next week as
something else entirely.

### B-004 — `TOTAL_FRICTION` as the objective function

Provenance: `AMBIGUOUS` source, adopted `USER_ACCEPTANCE_OBSERVED` (A1: objective function).

```
TOTAL_FRICTION =
    transport_bits
  + token_cost
  + decode_latency
  + ambiguity_cost
  + recovery_cost
  + error_probability
```

Not `strlen()`. The receipt is explicit that the real latency lives in
serialization → routing → context insertion → tokenizer → inference → tool
execution → verification, and that inference dominates; so a format must
minimise *cognitive decode cost*, not characters. This is adopted as the
benchmark's objective.

### B-005 — Progressive decoding, `R0`–`R4`

Provenance: `AMBIGUOUS` source, adopted `USER_ACCEPTANCE_OBSERVED` (A2: workload instructed).

```
R0  existence
R1  routing / header
R2  semantic summary
R3  canonical full payload
R4  attached evidence
```

An agent starts at `R1`, and only an interested agent asks for `R2`, then `R3`,
then `R4`. Measured as a workload, not implemented as a transport.

### B-006 — Context-local semantic cache

Provenance: `AMBIGUOUS` source, **never adopted** — an idea, not an instruction.

Agreed macros (`Q7 = ticket closed + tests passed + zero regressions +
accepted`) referenced as `Q7:@12`, where `Q7` resolves to an immutable
definition hash. Mutable semantics is the failure mode being designed against.

### B-007 — The six-line philosophy

Provenance: `AMBIGUOUS` source, **never adopted** — an idea, not an instruction.

```
IDENTIFY ONCE
REFERENCE CHEAPLY
SEND DELTAS
OPEN ON DEMAND
VERIFY BY HASH
NEVER GUESS
```

Goal, in the receipt's own words: minimally sufficient information reaching the
right mind with minimal latency, minimal ambiguity, and no need to rebuild
context.

## From measurement (T-9, `bench/ANALYSIS.md`)

### B-008 — Claim grammar gap: chains ending in a comparison

Provenance: `MEASURED_EVIDENCE` — measurement supports a claim and never asks for work.

`A>B=C` is idiomatic and unsupported by v0 grammar; the projector correctly
falls back to `OPEN RECORD`. Candidate v1 extension, deliberately not applied
inside the run that measured it.

### B-009 — Non-ASCII claim vocabulary

Provenance: `MEASURED_EVIDENCE` — measurement supports a claim and never asks for work.

The compact claim grammar is ASCII-only, so every non-English claim degrades to
`OPEN RECORD`. For a system whose own sources are written in three languages,
that is a gap rather than a feature.

### B-010 — Vocabulary chosen for tokenizers, not for looks

Provenance: `MEASURED_EVIDENCE` — measurement supports a claim and never asks for work.

`SHOUTING_SNAKE_CASE` measurably costs tokens against ordinary words. A v1
vocabulary experiment should optimise for measured tokenizer behaviour across
families, and must not be tuned to a single family and then called universal.

## From `SRC-007` (steward turn, sha256 `0f9a68d3…`)

### B-011 — HUMAN_ATTENTION_BUDGET

Provenance: captured `USER_ACCEPTANCE` (`SRC-007`, host user turn). Backlog only, do not implement.

Explicit budget and deferral policies for operator attention:
- `ALLOCATION`: (`CRITICAL_RECOVERY` / `AMBIGUITY_RESOLUTION` / `DECISION_REQUEST` / `ROUTINE_AUDIT` / `IDLE_REPORT`)
- `DEFERRAL_POLICY`: (`BLOCK_UNTIL_HUMAN` / `QUEUE_AND_CONTINUE` / `ESCALATE_AND_HALT`)

### B-012 — ALLY_ADVICE / PERSONAL REFLECTION

Provenance: captured `USER_ACCEPTANCE` (`SRC-007`, host user turn). Backlog only, do not implement.

Reflection and advice channel:
- Not an instruction.
- Not authority.
- Not evidence.
- Admissible only as context or explicit proposal.

### B-013 — LEGACY / SUCCESSOR COMMUNICATION

Provenance: captured `USER_ACCEPTANCE` (`SRC-007`, host user turn).

Cross-session operational transfer:
- What worked / what failed / what looked right but was wrong.
- Must be bound to evidence and scope, never ungrounded advice.

**DONE (D-040 / T-50).** Production `LEG1` is an immutable SAIMAIL
host-protocol object transported by SENV2 `K=EXPERIENCE`, `TOPIC=legacy`.
Authenticated adoption requires the exact `OpenedEnvelope` payload and an
explicit store operation. Exact-subject successor rendering keeps observed
scope separate from new task scope, retains `WATCH_NEXT=UNVERIFIED`, and adds
no authority, promotion, task, command, score, or consensus semantics.

## From `SRC-011` (steward turn, T-34 continuation correction)

### B-014 — UNKNOWN semantics may need a non-downgradable attention floor

Provenance: captured `USER_ACCEPTANCE` (`SRC-011`, host user turn). T-5 design finding, backlog only.

The stability experiment (T-33) observed one participant answering `IGNORE`
in all three repeats for the `S3.mailbox` M3 item — the message whose claim
carries a term the reader's dictionary does not define, and which the
deterministic selector opens for exactly that reason. Before T-5 is
implemented, decide whether `MACHINE_REQUIRED_OPEN` outranks a model
`DEFER`/`IGNORE`, and whether that floor is enforced rather than advisory.
`03-POST-OFFICE.md` section 8 carries the state marker
(`ATTENTION_FLOOR: PENDING`) and a test refuses a Post Office while it is
pending.
The decision must be evidence-backed and explicit; selector semantics are not
to be modified inside a T-4/T-3 wave.

**DECIDED (D-036, recorded under `SRC-020` / T-43): the floor exists and is
enforced, not advisory.** A deterministic `OPEN_R2` may end at `OPEN_R2` or
`OPEN_R3`, never `DEFER`/`IGNORE`; a deterministic `OPEN_R3` stays `OPEN_R3`;
a model may raise the resolution of a machine-required open, never reduce it.
The entry above stays as the original planning evidence; `03-POST-OFFICE.md`
section 8 now carries `ATTENTION_FLOOR: DECIDED`.

## From `SRC-030` (T-51 corrective handoff)

### B-015 — P2 LEGACY_PARTIAL_ADOPTION_RECOVERY

Deferred reliability work; do not fold it into T-51. Adoption publishes
`packet.leg1` and then `provenance.json` inside an already-visible entry
directory. A crash between those immutable writes leaves an incomplete
directory, and `LegacyStore.all()` correctly fails closed until the exact
adoption is retried. A later design may provide explicit recovery without
weakening immutable publication. The condition is recorded, not hidden; no
recovery mechanism is implemented by B-013/T-51.


## Provenance of this file

Every entry above carries a provenance class from `provenance/ATTRIBUTIONS.json`,
audited against declared segment maps in `provenance/`.

The audit produced one uncomfortable and correct result: **`SRC-003` and
`SRC-004` are wholly `AMBIGUOUS`.** They are transcribed dialogues with no
authorship markers in the bytes — a human voice and an assistant voice alternate
with nothing but style separating them, and style is exactly what may not be
used to attribute authorship. So nothing in this backlog draws authority from
"the founding source said so".

What authority exists comes from acts the steward performed later, recorded as
`SYSTEM_OBSERVATION` in `provenance/ACCEPTANCES.md` and surfacing as
`USER_ACCEPTANCE_OBSERVED` — deliberately weaker than a captured word, because an
agent's note that a person said something is evidence about an act, not the act.

Three entries have no acceptance at all and remain ideas. Three more are
measurements, and measurement never asks for work.
