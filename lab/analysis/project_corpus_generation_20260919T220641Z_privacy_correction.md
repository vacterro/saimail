# B-019 privacy correction — population error-text persistence

Additive correction recorded 2026-09-20 under T-70 / `SRC-053`. It rewrites no
history: T-69 remains DONE and the historical artifact, report and interpretation
are unchanged (SHA-256 pins below). The old artifact was not privacy-perfect, and
this note says so plainly instead of restating the original claim.

## What T-69 got right

T-69 correctly prevented persistence of corpus prompts, generator prose and
reviewer rationale: the redacting dispatch kept durable call records
metadata-only, the corpus content never entered an artifact, report or
interpretation, and no generated candidate or reviewer rationale was stored.
The one registered live run was metadata-only, within budget and free of mail,
attention or operator-presentation side effects.

Discovery happened before corpus transmission. The discovery and participant
selection calls carried no B-018 corpus data: the corpus is transmitted only in
the generator and reviewer prompts, and the defect below lives entirely in the
discovery/population metadata recorded before those prompts were built.

## The defect

The durable artifact serialized the generic population record
(`Population.as_record()`) unchanged. That generic record keeps raw diagnostic
error text by design: `population.discovery.alias_transport_errors[*].error`
and `population.rejected_candidates[*].error` held provider/gateway response
snippets (HTTP 429 quota text, HTTP 403 access-restricted text, HTTP 500
empty-response text) plus one local empty-output note.

The artifact therefore declared `plaintext_retention.provider_error_bodies = false`
while containing raw provider error text. The historical claim was too broad:
the boolean was true for the content-call records and false for the serialized
population section.

## What this does not mean

No evidence indicates B-018 corpus content entered those discovery or provider
error strings. They carry provider/gateway diagnostics only. This finding is not
leakage of project corpus content, generated advice, reviewer rationale or
HUMAN_PRIVATE data — it is a durable-artifact privacy/contract defect.

## The correction

Future artifacts are built from an explicit sanitized population projection
(T-70), never from the generic raw record. The projection preserves the
experiment topology (combo and membership identity, catalog and membership
digests, participants, requested routes, selection/rejection reasons,
`error_class`, probe counts, notes) and replaces every raw
error/response/body/exception payload with `error_sha256` plus `error_bytes`.
The privacy booleans are coupled to a structural test, so a future serializer
that loses this boundary fails the suite instead of silently contradicting the
declaration.

The generic population machinery and the other SAIFREN experiments keep their
own evidence-retention contracts: the stricter consumer boundary was fixed
first, and no historical semantics were changed.

## Recorded decision (T-70)

`spec/DECISIONS.md` is a pinned B-018 corpus source: any edit to it breaks the
frozen `BUILD_ID`/`CORPUS_ID` reproduction, so this additive decision is
recorded here and in `spec/BACKLOG.md` instead, with no D-051 entry.

```
GENERIC_POPULATION_RECORD != PRIVATE_PILOT_DURABLE_POPULATION_RECORD
PRIVATE_PILOT_PROVIDER_ERROR_BODY_PERSISTENCE = false
ERROR_METADATA_ALLOWED = CLASS + CODE/REASON + HASH/LENGTH
RAW_ERROR_TEXT_ALLOWED = false
PRIVACY_CLAIM_REQUIRES_STRUCTURAL_TEST = true
HISTORICAL_T69_ARTIFACT_REWRITTEN = false
```

## Frozen identities (byte-identical before and after this correction)

- `lab/out/project_corpus_generation_live_20260919T220641Z.json`
  — sha256 `e9745fcbb84f12f29f8e54c7f891e0b9a61949710e40d48224e9352889caa5d7`
- `lab/out/PROJECT_CORPUS_GENERATION_REPORT_20260919T220641Z.md`
  — sha256 `f442512fc28d7e31d54b0ae01510c9ee78985dc46024d56873c31b42e4f860b5`
- `lab/analysis/project_corpus_generation_20260919T220641Z.md`
  — sha256 `f4f2d92c60fbab134ef5b404968a6dc853f3ca2914fe83ae269376b791157617`
