# ALLY_ADVICE v0

Normative decision: [D-046](DECISIONS.md). This specification defines the
B-012 object and explicit delivery corridor. It adds neither a SAILANG kind nor
an encryption format.

## Purpose and authority

ALLY_ADVICE exists to carry a rare, private personal reflection in which
observation, interpretation, proposal, counterevidence, uncertainty and human
agency cannot collapse into one flattering paragraph. It is context or a
proposal only:

```
ALLY_ADVICE != FACT
ALLY_ADVICE != EVIDENCE
ALLY_ADVICE != AUTHORITY
ALLY_ADVICE != COMMAND
ALLY_ADVICE != KNOWLEDGE
ALLY_ADVICE != LEGACY
ALLY_ADVICE != SAIPEN TASK
REFERENCE_EXISTS != REFERENCE_SUPPORTS_CLAIM
```

No output is normal. Days or weeks with no valid personal letter are a valid
successful state.

## Canonical ALLY1 object

ALLY1 is strict UTF-8 canonical JSON with one final LF. Object-key order,
compact separators, Unicode rendering and field set are fixed by the canonical
serializer; the parser refuses duplicate/unknown/missing keys and requires the
input bytes to equal the serializer output exactly.

The ordered top-level schema is:

1. `FORMAT` — fixed `ALLY1`
2. `CREATED` — sender-authored canonical UTC instant
3. `WORK_CONTEXT` — bounded operational context
4. `OBSERVED_SCOPE` — bounded scope in which observations were made
5. `OBSERVED` — ordered immutable observation items
6. `INFERRED` — `{STATUS: UNVERIFIED, TEXT: ...}`
7. `SUGGESTED` — `{STATUS: PROPOSAL, MODE: ..., TEXT: ...}`
8. `COUNTEREVIDENCE` — ordered immutable counterevidence items
9. `UNCERTAINTY` — mandatory qualitative prose
10. `AGENCY` — fixed `RECIPIENT_DECIDES`

Each observation and counterevidence item is exactly
`{STATEMENT: text, EVIDENCE_REFS: [refs...]}`. References are strictly sorted,
unique `sha256:<64 lowercase hex>` identities. Symbolic ticket, log or model
labels are not evidence identities.

Mechanical limits:

- observations: 2..16;
- distinct observation refs: at least 3;
- counterevidence items: 1..8;
- evidence refs per item: 1..16;
- work context and observed scope: 2048 UTF-8 bytes each;
- each other prose field: 4096 UTF-8 bytes;
- total canonical ALLY1: 32768 bytes.

`STRUCTURAL_PATTERN_FLOOR != SEMANTIC_PATTERN_PROOF`. The floor prevents a
single incident from entering this protocol as sufficient pattern evidence; it
does not prove a pattern exists.

## Epistemic and agency markers

`INFERENCE_STATUS` is represented only as `UNVERIFIED`.
`GUIDANCE_STATUS` is represented only as `PROPOSAL`. Guidance mode is exactly
`OBSERVE_ONLY` or `CONSIDER_CHANGE`; observe-only may explicitly propose no
action. `AGENCY` is always `RECIPIENT_DECIDES` and human rendering must show it.

There is no numeric confidence, motive, personality, trait, diagnosis,
psychological-cause, priority, allocation, deferral, open-rate, compliance,
engagement or success field. The renderer preserves prose; it does not generate
flattery or persuasion.

## Evidence existence gate

The environment supplies an `EvidenceResolver` implementing
`resolve(ref) -> EXISTS | MISSING`. Resolution checks every observation and
counterevidence reference. No resolver causes
`ALLY_EVIDENCE_RESOLUTION_REQUIRED`; any missing object causes
`ALLY_EVIDENCE_MISSING`.

Success mints a non-transplantable `EvidenceResolvedAllyAdvice` type-state.
The type means only that every cited object existed according to that resolver
at validation time. It is not verified advice, proven inference or semantic
support. The mint token is not persisted.

## Private transport and explicit open

The only official conversion accepts the resolved type-state and produces:

```
HumanPrivateLetter(
    TO_HUMAN = explicit recipient HUMAN_ID,
    CREATED = ALLY1 CREATED,
    SUBJECT = "ALLY_ADVICE",
    BODY = exact canonical ALLY1 UTF-8 text,
)
```

Existing HENV1 sealing and `HumanPrivateStore` delivery then persist only
ciphertext. The clear HENV1 routing metadata does not expose the advice type.
There is no `AllyAdviceStore`, plaintext sidecar, reflection archive or human
profile.

After explicit recipient decrypt, the ALLY_ADVICE open helper requires the
expected recipient, fixed subject and exact canonical body before returning the
parsed object. Opening creates no task, LEGACY, KNOWLEDGE, promotion, profile or
acceptance state.

## Receiver-owned attention

Every step remains explicit:

```
construct ALLY1
-> resolve cited existence
-> convert to HLET1
-> seal existing HENV1
-> deliver ciphertext
-> receiver explicitly admits HUMAN_PRIVATE + LETTER_ID
-> reserve / ACK_PRESENTED
-> human explicitly decrypts and opens ALLY1
```

Construction, resolution, conversion, sealing and storage never call
`AttentionQueue.admit_receiver_candidate`. ALLY1 contains no receiver
allocation or deferral policy. The queue sees only `HUMAN_PRIVATE` and
`LETTER_ID`; sender prose such as `CRITICAL_RECOVERY` has zero priority effect.
`ACK_PRESENTED` means surfaced only, not read, agreement, acceptance, behavior
change or correctness.

## Honest semantic limit

B-012 v0 does not mechanically prove:

- prose is non-flattering;
- prose contains no hidden motive inference;
- cited evidence semantically supports an observation;
- counterevidence is the strongest available;
- a suggestion is novel to its recipient;
- a pattern is psychologically meaningful;
- advice is useful.

It guarantees structural separation, canonical provenance references, cited
existence at one explicit gate, immutable type-state, private transport and
receiver-owned attention. Autonomous generation, history mining and semantic
review remain out of scope.
