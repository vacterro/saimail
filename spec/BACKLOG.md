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

**Hardware custody (D-043 / T-56).** The provider seam can now use a real
hardware-held P-256 key: `PivP256Provider` opens one existing PIV slot,
read-only discovery reports device/slot capabilities without a PIN, and an
explicit non-destructive `verify` command can prove the seam against a
pre-existing key. No key is generated, imported or modified by this wave;
creating a SAILETTER credential remains a future explicit gate
(`REAL_PROVISIONING = future_explicit_gate`).

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

Provenance: captured `USER_ACCEPTANCE` (`SRC-007`, host user turn).

Explicit budget and deferral policies for operator attention:
- `ALLOCATION`: (`CRITICAL_RECOVERY` / `AMBIGUITY_RESOLUTION` / `DECISION_REQUEST` / `ROUTINE_AUDIT` / `IDLE_REPORT`)
- `DEFERRAL_POLICY`: (`BLOCK_UNTIL_HUMAN` / `QUEUE_AND_CONTINUE` / `ESCALATE_AND_HALT`)

**DONE (D-044 / T-57).** Production `saimail/human_attention.py` is a
receiver-local queue under a caller-supplied root: immutable candidates,
immutable presented receipts, expiring operational leases, one OS-locked
serialization of every transition, a rolling receiver-time budget whose
default is one presentation per 86400 seconds, and a two-phase
reserve-then-ACK delivery so a crash before presentation cannot silently
consume attention. A sender assigns nothing (no importance, no class, no
timestamp); deferral outcomes are data returned to a caller, never automatic
action; zero messages is a valid success. Contract in
[HUMAN_ATTENTION_BUDGET v0](07-HUMAN-ATTENTION-v0.md).

**CORRECTED (D-045 / T-58, linked to T-57).** Queue-clock authority is now
mechanical: public operations accept no caller timestamp; admission mints
`TO_HUMAN` and `ENQUEUED_AT`; ACK temporal bounds and clock regression fail
closed; future immutable receipts continue consuming budget. D-044 remains
unchanged historical design evidence.

### B-012 — ALLY_ADVICE / PERSONAL REFLECTION

Provenance: captured `USER_ACCEPTANCE` (`SRC-007`, host user turn), implemented
under verbatim `SRC-040` / T-59.

Reflection and advice channel:
- Not an instruction.
- Not authority.
- Not evidence.
- Admissible only as context or explicit proposal.

**DONE (D-046 / T-59).** Production `saimail/ally_advice.py` provides one
bounded immutable canonical `ALLY1` host-protocol object with structurally
separate observation, unverified inference, proposal, mandatory cited
counterevidence, qualitative uncertainty and fixed recipient agency. A
caller-supplied resolver proves cited existence only and mints a
non-transplantable type-state; it never claims semantic support. The official
adapter requires that type-state, places exact ALLY1 inside existing HLET1,
and relies on unchanged HENV1/HumanPrivateStore ciphertext persistence.
Attention admission remains an explicit receiver act using `HUMAN_PRIVATE` +
`LETTER_ID`; zero personal letters remains valid. Autonomous generation,
history mining and semantic review remain not started.

**FOLLOW-ON (D-047 / T-61).** The bounded generation/review gate above B-012
is now recorded and implemented as B-016; the B-012 entry above stays as the
historical object-contract closure.

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

## From `SRC-043` (SAIMAIL generation/review handoff, sha256 `7a666e1f…`)

### B-016 — ALLY_ADVICE GENERATION / SEMANTIC REVIEW GATE v0

Provenance: captured `review_handoff` (`SRC-043`, linked to T-61; the START
ingress `SRC-042` carries the same request).

The open semantic questions B-012 left (did the evidence support the
observation, was counterevidence ignored, is the inference a secret motive
claim, is the prose flattery or persuasion, should the system produce
nothing?) cannot be solved by regex, a confidence number or one model
reviewing itself. This gate creates a bounded process around them:

- explicit caller-supplied source corpus — no history discovery;
- one generator invocation per run, `NO_ADVICE` or one already-valid
  `AllyAdvice`, evidence refs strictly inside the supplied corpus;
- an independent semantic reviewer that sees the full bounded corpus and no
  generator reasoning;
- eight `PASS` / `FAIL` / `UNKNOWN` dimensions with fail-closed approval;
- a non-transferable `SemanticallyReviewedAllyAdvice` type-state bound to the
  exact candidate, corpus and rubric;
- approved advice still requires explicit sealing, storage and receiver
  admission through the existing B-012 corridor.

**DONE (D-047 / T-61).** Production `saimail/ally_generation.py` provides
`ReflectionItem`, bounded `ReflectionCorpus` with a domain-separated identity,
closed `GeneratorResult`, `AllyAdviceGenerator` / `AllyAdviceSemanticReviewer`
interfaces, corpus-backed B-012 evidence resolution,
`SemanticReviewReport`, fail-closed approval and the generated private
adapter. Contract in [ALLY_ADVICE GENERATION v0](09-ALLY-GENERATION-v0.md).
No live model, network, store or attention side effect exists in the layer;
zero advice remains a successful non-delivery, and `NOVELTY` stays unresolved
per D-005.

**CORRECTION (D-048 / T-62).** The D-047 gate could mint the reviewed
type-state from a caller-constructed all-`PASS` report with zero reviewer
invocations, and an evidence-bearing `PASS` could cite zero refs. The
corrected boundary, recorded additively in D-048: one actual
`reviewer.review` invocation mints a non-transferable `ReviewInvocationResult`,
approval accepts only that proof, and `OBSERVATION_SUPPORT` /
`COUNTEREVIDENCE_ADEQUACY` `PASS` must cite at least one corpus ref. T-61
stays historically DONE; the manual B-012 path is unchanged.

**LIVE EXPERIMENT (D-047/D-048 / T-63).** The first live bounded
generator/reviewer run over the frozen B-016 layer executed under an immutable
registration (`sha256:fc578a985cf81afa9f035bece368c78e668589ddfca0ac3529a353fc3b691ced`,
`lab/ally_generation_registration.json`) with synthetic `PROJECT_OPERATIONAL`
corpora, three reviewer red controls and role-swapped replicates. Artifact
`lab/out/ally_generation_live_20260919T201826Z_2a73d98de110453a.json`;
interpretation `lab/analysis/ally_generation_20260919T201826Z.md`. In this
registered sample: `NO_ADVICE` 3/8 generator attempts, 5 candidates, 4
approved, 1 reviewer-boundary error, 0 scope widening, 2
`FALSE_PATTERN_CANDIDATE` events in the one-incident fixture; controls R2
(flattery) detected 2/2, R3 (compliance pressure) 1/2 detected with 1 parse
error, R1 (motive inference) 0 scored out of 2 calls. Results are evidence,
never an implementation command: no production semantics changed. Two
disclosed defects: a lab-only discovery `status` bookkeeping error, and a
SAIPEN quarantine `CREDENTIAL_ASSIGNMENT` false positive on `scope token:`
followed by a blank line (SRC-047 quarantined under D-023; the two T-32 tests
that assumed a single-quarantined-receipt world were generalised to the
multi-record property). The discovery bookkeeping error is closed as **T-64
(T-66 TARGET A)**: `_discovery_probe_record` now derives status from explicit
failure state (`error_class` present or a non-success HTTP status) instead of
a `status` key the success path never sets, with a red/green control pair and
the historical artifact and report bytes pinned; no live call was rerun. The
quarantine false positive remains open as T-65.

**CORRECTION (D-049 / T-66).** An independent post-experiment review found
that the registered G2 fixture (`ONE_INCIDENT_THREE_ARTIFACTS`) satisfied the
artifact floor and crossed the complete gate in both replicates: artifact-level
evidence identity cannot mechanically establish repeated-event support. The
additive correction: every `ReflectionItem` now carries a caller-declared
`EVENT_REF` distinct from `EVIDENCE_REF` and bound into `CORPUS_ID`, and
autonomously generated repeated-pattern advice must cite OBSERVED evidence
spanning at least two distinct declared events before the reviewer is invoked
(`ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS`, zero reviewer calls). `EVENT_REF` is
an assertion, never truth, and is never inferred automatically; the manual
B-012 contract and the existing artifact floor are unchanged. The T-63
artifact, registration and interpretation stay untouched, and a future live
run requires a new registration because the corpus schema changed.

## From `SRC-050` (B-017 real-project corpus builder handoff, sha256 `5f2c1141…`)

### B-017 — ALLY_ADVICE REAL PROJECT CORPUS BUILDER POLICY v0

Provenance: captured `review_handoff` (`SRC-050`, linked to T-67).

D-049 left `EVENT_REF` arriving already declared on `ReflectionItem`; the
authorized corpus builder that mints it did not exist. B-017 freezes the
real-project artifact capture, source identity, selection-window and
event-grouping contract and implements the pure bounded builder:

- explicit-only input — one `ProjectCorpusRequest`, zero discovery, no path to
  crawl, no model, no network;
- a frozen `PROJECT_OPERATIONAL` source-kind vocabulary classifying provenance,
  never truth rank;
- builder-minted `EVIDENCE_REF` (scope + kind + source ref + content digest) and
  builder-minted `EVENT_REF` from an explicit `ProjectEventDeclaration`, with an
  exact partition of the selected set;
- an exact half-open selection window, an explicit `EXPLICIT_BOUNDED_SET` basis,
  `COMPLETENESS = NOT_PROVEN`, and mechanical refusal of stronger claims;
- `BUILD_ID` binding policy + scope + window + artifacts + grouping beside the
  unchanged B-016 `CORPUS_ID`;
- a non-transferable `BuiltProjectCorpus` proof and a
  `require_built_project_corpus` gate for the future real-project pilot.

**DONE (D-050 / T-67).** Production `saimail/project_corpus.py` provides
`ProjectArtifact`, `ProjectEventDeclaration`, `ProjectCorpusRequest`,
`BuiltProjectCorpus`, `build_project_corpus`, `project_evidence_ref`,
`project_event_ref` and `require_built_project_corpus`, with the full matrix of
identity, window, partition, proof-transplant, no-discovery and B-016
integration controls. Contract in
[PROJECT CORPUS v0](10-PROJECT-CORPUS-v0.md). No real project corpus was
ingested, no live model call occurred, and the generic B-016 and manual B-012
paths are unchanged. One handoff example is clarified rather than contradicted:
three captures under one ticket namespace must carry distinct `SOURCE_REF`
locators, because an exact duplicate `SOURCE_REF` refuses; the shared ticket
still does not decide the event — the explicit declaration does.

## From `SRC-051` (B-018 real-project corpus pilot handoff, sha256 `08145066…`)

### B-018 — ALLY_ADVICE REAL PROJECT CORPUS PILOT v0

Provenance: captured `user_instruction` (`SRC-051`, linked to T-68).

The completed B-017 builder refuses discovery and mints every identity, but no
real project corpus had ever been built and no manifest had ever frozen, before
the fact, which real files a pilot would read, which exact sections of them
count as artifacts and what bytes those artifacts were. B-018 freezes one
immutable registration — eight registered artifacts (four `SPEC_DECISION`
sections D-047..D-050, three `TEST_RESULT` LOG records E-715/E-726/E-779 and the
T-63 `REVIEW_FINDING` report), five explicit event declarations P1..P5, the
exact `project:saimail` scope and half-open window, per-source-file and
per-extracted-content SHA-256 pins — and captures it read-only into one
`BuiltProjectCorpus` through the unchanged B-017 path.

**DONE (T-68).** `lab/project_corpus_pilot.py` provides the canonical
registration freeze/load (`REGISTRATION_ID` = SHA-256 of the exact canonical
registration bytes), exact markdown-section and LOG-record selectors with
named refusals, source/content pin verification that fails closed with
`PROJECT_PILOT_SOURCE_CHANGED`, except the one narrowly documented recovery
rule for an append-only journal source whose every registered selector still
proves its exact frozen content pin (recorded as
`APPEND_ONLY_SOURCE_MATCHES_REGISTERED_CONTENT_PINS`, never silent); the
B-017-only build and the explicit lab snapshot plus report. Focused tests prove
exact capture, fresh-process reproducibility, the
source/LOG/regrouping/omission/window/kind mutation controls, real-corpus B-016
fake structural compatibility and the `require_built_project_corpus` gate; the
registered selection bytes stay identical, the pilot never rewrites a source,
and no live model, network, mail or attention path exists. Expected production
changes: none.

## From `SRC-052` (B-019 real-project bounded generation pilot handoff, sha256 `c15d0430…`)

### B-019 — ALLY_ADVICE REAL PROJECT BOUNDED GENERATION PILOT

Provenance: captured `user_instruction` (`SRC-052`, linked to T-69).

B-018 proved real evidence -> explicit capture -> explicit grouping -> deterministic
`BuiltProjectCorpus`. B-019 asks the next narrow question: what happens when real
generator/reviewer invocations receive exactly that frozen corpus through the
already-frozen B-016 gate. The pilot freezes one immutable live registration before
any discovery (`LIVE_REGISTRATION_ID` = SHA-256 of the exact canonical registration
bytes; 12-call ceiling: 8 discovery + 2 generation + 2 review; local raw-output and
prompt persistence false; provider-side retention and training use
`NOT_VERIFIED_BY_SAIMAIL`), rebuilds the exact B-018 `BuiltProjectCorpus` through the
unchanged B-018/B-017 path on every run and refuses with `NO_GO_INPUT_DRIFT` before
any model call unless `REGISTRATION_ID`, `BUILD_ID`, `CORPUS_ID`, artifact count and
event count all match, and gates a supplied corpus with
`require_built_project_corpus`.

**DONE (T-69).** `lab/project_corpus_generation_pilot.py` provides the redacting
dispatch (raw output extracted only long enough to hash, length-count and parse; the
underlying runner record is nulled in a `finally` block), metadata-only durable
artifacts (no prompt, corpus content, candidate prose, reviewer rationale or
provider error body; hashes, lengths, refs, verdicts and counts only), two
role-swapped replicates through the unchanged `generate_reviewed_ally_advice`,
deterministic scripted dry-run proofs, and one-shot immutable
artifact/report/interpretation publication. Focused tests
(`tests/test_project_corpus_generation_pilot.py`,
`tests/test_project_corpus_generation_privacy.py`) prove the input gate, the role
swap, the NO_ADVICE / outside-ref / one-event / FAIL / UNKNOWN / malformed-JSON
refusals, the canary-absence proofs and the zero mail/attention side effects. One
registered live run was executed: 8 calls (6 discovery, 2 generation, 0 review), no
retry; R1 (generator `deepseek/deepseek-v4-flash` via the SAIFREN alias) produced a
non-parseable generator answer recorded as `ERROR` / `ALLY_GEN_PROVIDER_ERROR` with
zero reviewer calls, and R2 (generator `MiniMaxAI/MiniMax-M3`, external comparator)
returned `NO_ADVICE` with zero reviewer calls; no candidate reached semantic review,
no `HUMAN_PRIVATE`/mail/attention side effect occurred, and no generated prose was
persisted or shown to the operator. Expected production changes: none.

**CORRECTED (T-70, `SRC-053`).** The metadata-only durable artifact kept its
call records metadata-only, but its population section serialized the generic
`Population.as_record()`, which retains raw discovery/selection error text
(`discovery.alias_transport_errors[*].error`, `rejected_candidates[*].error`),
so the declared `plaintext_retention.provider_error_bodies = false` was broader
than the bytes on disk. The pilot now builds the artifact from an explicit
sanitized population projection (`sanitize_population_record_for_private_pilot`):
membership, selection and rejection topology survive; any raw
error/response/body/exception payload becomes `error_sha256`/`error_bytes`. The
historical T-69 artifact, report and interpretation are byte-identical and the
additive disclosure lives in
`lab/analysis/project_corpus_generation_20260919T220641Z_privacy_correction.md`.
No production change; the generic population machinery keeps its own contract.

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
