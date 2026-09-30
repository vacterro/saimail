# FG-04A offline reference telemetry: closure report

Contract: `REFERENCE-TELEMETRY-1` (`spec/14-REFERENCE-TELEMETRY-v0.md`).
Implementation: `lab/reference_telemetry.py`. This report is deterministic: it
is produced offline from the synthetic matrix and the unchanged product gate,
and it contains no synthetic canary plaintext, no generated advice prose, no
model output and no live-run data.

## Scope

The observer answers one question per candidate reference token: which closed
class is it -- `KNOWN_EVIDENCE_REF`, `KNOWN_EVENT_REF_AS_EVIDENCE`,
`CORPUS_ID_AS_EVIDENCE`, `UNKNOWN_CANONICAL_REF`, `MALFORMED_REF` or
`NON_TEXT_REF` -- and where did it appear (`OBSERVED` / `COUNTEREVIDENCE`).
It records aggregate counts, a metadata-only corpus-ref relation
(`CLEAN`, `HAS_OUTSIDE_CANONICAL`, `HAS_IDENTIFIER_TYPE_CONFUSION`,
`HAS_MALFORMED`, `HAS_NON_TEXT`, `MIXED_INVALID`) and the event-floor relation
`MET` / `NOT_MET` / `NOT_EVALUABLE`. It holds no acceptance authority; the
unchanged B-016 gate remains the only one.

## Synthetic case names and expected classifications

Unit matrix (`tests/test_reference_telemetry.py`):

- known evidence ref -> `KNOWN_EVIDENCE_REF`, `CLEAN`
- event ref used as evidence -> `KNOWN_EVENT_REF_AS_EVIDENCE`, never
  `UNKNOWN_CANONICAL_REF`, never mapped to member evidence
- corpus id used as evidence -> `CORPUS_ID_AS_EVIDENCE`
- unknown canonical ref -> `UNKNOWN_CANONICAL_REF` with and without a corpus
- malformed matrix (missing prefix, uppercase hex, 63 hex, 65 hex, non-hex,
  leading whitespace, trailing whitespace, blank string, non-UTF-8 text) ->
  `MALFORMED_REF`, plaintext absent
- non-text values (`None`, integer, list, dict) -> `NON_TEXT_REF`, no repr
  persisted
- mixed invalid categories -> `MIXED_INVALID`
- field distribution: per-field occurrences, per-field unique tokens,
  per-field unknown counts; one token in both fields stays one unique token
  with one fingerprint
- event coverage: two known events `MET`, one known event `NOT_MET`, unknown
  or malformed observed ref `NOT_EVALUABLE`, counterevidence-only violation
  does not rewrite the observed event count
- privacy: malformed canary, arbitrary text canary, non-text repr, and all
  authored prose fields absent from serialized telemetry; fingerprints
  deterministic and domain-separated
- bounds: 384 raw occurrences accepted, 385 refused; bare string refused
- purity: file open and socket creation cannot occur; the module source has no
  filesystem, network, subprocess or model surface; membership never leaves
  the supplied corpus; no normalization repairs a token; a one-hex-char
  near-match stays `UNKNOWN_CANONICAL_REF` with no typo/nearest-ref label
- closed schema: exact key set, unknown fields refused, construction refuses
  unknown or missing fields

Integration matrix (`tests/test_reference_telemetry_integration.py`):

- `C1` clean two-event candidate: telemetry `CLEAN` + `MET`, zero unknown
  counts; product outcome `APPROVED` with exactly one fake reviewer call
- `C2` unknown canonical observed ref: `UNKNOWN_CANONICAL_REF` in `OBSERVED`,
  `HAS_OUTSIDE_CANONICAL`, `NOT_EVALUABLE`; product
  `ALLY_GENERATED_REF_OUTSIDE_CORPUS` with zero reviewer calls
- `C3` counterevidence-only unknown: field distribution identifies
  `COUNTEREVIDENCE`; product rejects at the corpus-ref gate, not as an
  observed event-floor failure; zero reviewer calls
- `C4`/`RED-A` exact real event ref used as evidence: naive outside count is
  exactly 1; telemetry says `KNOWN_EVENT_REF_AS_EVIDENCE`; product still
  rejects; zero reviewer calls
- `C5` corpus id used as evidence: `CORPUS_ID_AS_EVIDENCE`; product rejects
- `C6` one-event clean candidate: `CLEAN` + `NOT_MET`; product
  `ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS`; zero reviewer calls
- `C7`/`RED-B` unknown ref plus two known events: naive event count already
  reads as met; telemetry is `NOT_EVALUABLE`, never `MET`; product rejects at
  the corpus-ref gate first
- `RED-E` forged telemetry claiming `CLEAN` for a bad candidate: a
  schema-valid `ReferenceTelemetry` object cannot change the product outcome;
  product still rejects and the reviewer is still not called
- reviewer/genre calls by the observer itself: zero; production modules never
  import the LAB observer

Closed-schema/privacy controls: serialized telemetry key set equals the closed
schema, banned keys (`preview`, `raw_ref`, `raw_value`, `statement`,
`model_text`, `prefix`, `suffix`, `nearest_ref`, `edit_distance`, `similarity`)
cannot appear, and a canary token is absent from serialized output, stdout and
stderr (the per-token fingerprint may remain).

## Product parity outcomes

Every product outcome above was produced by the unchanged
`saimail.ally_generation.generate_reviewed_ally_advice` over the unchanged
`saimail.ally_advice` objects, with fake generator/reviewer doubles and counted
reviewer calls. `CORPUS_REF_RELATION = CLEAN` accompanied `APPROVED` for the
clean two-event case; every outside or confusion case was rejected by the
product corpus-ref gate independently of telemetry. Telemetry never turned a
rejection into a pass.

## T-74 historical limitation

The durable T-74 metadata proves only `outside_ref_count = 1`,
`outcome_code = ALLY_GENERATED_REF_OUTSIDE_CORPUS` and `reviewer_calls = 0` for
R1. The rejected raw ref was never persisted, so the exact historical failure
class remains `UNKNOWN_FROM_RETAINED_EVIDENCE`. No telemetry class is
manufactured for it, and the T-74 live artifact, machine report, analysis and
closure remain unchanged and hash-pinned.

## Zero-network proof

`lab/reference_telemetry.py` imports only stdlib hashing/JSON/regex, the
`lab.parse_shape` closed-schema gate and production data types/constants; it
has no filesystem, network, subprocess or model surface, and the synthetic
tests run with file-open and socket creation monkeypatched to fail. No model,
network, credential, publication or git operation was performed by FG-04A.

## Validation

- focused unit matrix: 52 passed
- focused integration/parity matrix: 12 passed
- product parity battery (`test_ally_generation_gate.py`,
  `test_ally_generation_corpus.py`, `test_project_corpus_budget4096.py`):
  69 passed
- full canonical suite at closure: recorded in `.saipen` LOG for T-80
- SAIPEN validate: `CURRENT_FAIL / CARRIED_DEBT_UNCHANGED` with the same three
  pre-existing debts and no new failure

## Boundary

FG-04B remains NOT STARTED. This report decides nothing about the future
JSON_SCHEMA experiment, including whether a future schema enum-constrains
`EVIDENCE_REF` values or only constrains their syntax.
