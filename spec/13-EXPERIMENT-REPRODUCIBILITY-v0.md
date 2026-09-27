# Experiment reproducibility v0: one input manifest, three separated authorities

Historical experiment verification and current-checkout verification have been
coupled in this repository three times. A new decision appended to the shared
`spec/DECISIONS.md` invalidated B-018 source-file pins even though the
registered section had not changed. The T-65 fix in `saimail/quarantine.py`
invalidated the historical T-71 tests. The T-78 change to `saimail/legacy.py`
again required a frozen fixture. Each narrow fix was correct; the missing piece
was a written contract that says

```
HISTORICAL_GREEN != CURRENT_CODE_GREEN
CURRENT_CODE_GREEN != LIVE_RUN_AUTHORIZED
HISTORICAL_REGISTRATION != LIVE_AUTHORIZATION
CURRENT_SOURCE_CONTAINER_HASH != SELECTED_INPUT_HASH
ARCHIVED_PUBLIC_INPUT != PRIVATE_INPUT_RETENTION_PERMISSION
MISSING_PRIVATE_PLAINTEXT != LICENSE_TO_RECONSTRUCT_IT
```

This document defines one additive manifest vocabulary for FUTURE experiments
and three mechanically separate operations over it. It does not rewrite any
historical registration (B-018, T-63, T-69, T-71, T-74) and does not change
their hashing rules; those remain historical formats.

Implementation: `lab/experiment_manifest.py` (LAB only). Tests:
`tests/test_experiment_manifest.py`. Nothing here performs a model or network
call, and nothing here modifies a production `saimail/*` module.

## EXPERIMENT-MANIFEST-1

A manifest is one JSON object with exactly these fields and nothing else:

```
manifest_version   EXPERIMENT-MANIFEST-1
experiment_id      [A-Z][A-Z0-9._-]{0,63}
authority          HISTORICAL_ONLY | LIVE_ELIGIBLE
inputs             non-empty list of input records
implementation     list of implementation components (may be empty)
```

Unknown fields, an unknown `manifest_version`, an unknown `extraction_kind`,
an unknown `extractor_version` and an unknown role refuse. There is no
best-effort interpretation of a manifest.

Applied identity rule:

```
MANIFEST_IDENTITY = sha256(exact canonical JSON bytes)
CANONICAL_JSON = sorted keys, compact separators, UTF-8, no trailing newline
MANIFEST_CONTAINS_OWN_DIGEST = false
SELF_REFERENTIAL_HASHING = false
```

The manifest never contains its own digest; the identity is computed over the
bytes as stored and is never written back into the document.

### Input record

Each input record carries exactly:

```
INPUT_ID          required, [A-Z][A-Z0-9_-]{0,63}, unique
SENSITIVITY       required, closed v0: PUBLIC_ARCHIVABLE | PRIVATE_EPHEMERAL
SOURCE_KIND       required, closed v0: TEXT_FILE | MARKDOWN_DOCUMENT | LOG_FILE |
                  IMMUTABLE_FIXTURE
EXTRACTION_KIND   required, closed v0: WHOLE_FILE | MARKDOWN_SECTION | LOG_RECORD |
                  IMMUTABLE_FIXTURE
EXTRACTOR_VERSION required, exactly the version of that extraction kind:
                  WHOLE-FILE-1 | MARKDOWN-SECTION-1 | LOG-RECORD-1 |
                  IMMUTABLE-FIXTURE-1
EXTRACTED_SHA256  required, lowercase sha256 of the exact SELECTED bytes
REQUIRED_FOR_LIVE required boolean
SOURCE_PATH       required for every kind except IMMUTABLE_FIXTURE
SELECTOR          required for MARKDOWN_SECTION and LOG_RECORD
ARCHIVED_FIXTURE  optional for PUBLIC_ARCHIVABLE; refused for PRIVATE_EPHEMERAL
CONTAINER_SHA256_AT_REGISTRATION
                  optional evidence about the historical container
```

`PUBLIC_ARCHIVABLE` means the exact selected bytes MAY be preserved as an
immutable fixture for historical verification. It does not mean publish
automatically. `PRIVATE_EPHEMERAL` means the manifest may retain hash and
metadata only: it MUST NOT copy plaintext into a fixture merely to improve
reproducibility.

### Selected input vs container

For a selected-section input the registered semantic identity is
`EXTRACTED_SHA256`, not the hash of unrelated bytes elsewhere in the same
mutable container. `CONTAINER_SHA256_AT_REGISTRATION` may remain evidence about
the historical container state, but an unrelated append outside the registered
selector must not invalidate the registered input identity. This is the rule
that ends the shared-`DECISIONS.md` coupling.

For `WHOLE_FILE` the container bytes ARE the selected input: a file change is
an extracted-input change, with no special exception.

Selector formats are closed and deliberately small; no generic query language
is defined:

- `MARKDOWN_SECTION` — `md-heading:<exact heading line>`: the selection starts
  at the first line equal to that heading and ends before the next heading of
  the same or a higher level (or EOF).
- `LOG_RECORD` — `log-line:<exact line>`: the selection is the first line equal
  to that text, excluding its line ending.

For `IMMUTABLE_FIXTURE` the archived fixture bytes ARE the selected input.

### Public fixture and private input

A `PUBLIC_ARCHIVABLE` selected input may carry `ARCHIVED_FIXTURE`. The fixture
bytes must hash exactly to `EXTRACTED_SHA256`. Historical verification may use
that fixture even if the current checkout source changed later. Fixture
substitution fails closed: a fixture whose bytes do not match is
`HISTORICAL_MISMATCH`, and the verifier never falls back to current source.

`PRIVATE_EPHEMERAL` inputs must not gain an archival plaintext fixture. If the
historical plaintext was intentionally destroyed, the historical replay result
is `HISTORICAL_INPUT_UNAVAILABLE_BY_DESIGN`, never `VERIFIED`, and no
reconstruction is attempted from hashes, model output, summaries, memory or
later files.

### Implementation identity

A manifest may bind the implementation components an experiment requires. Each
component carries exactly `PATH`, `SHA256`, `ROLE`, where a v0 role is one of
`PARSER`, `EXTRACTOR`, `RUNNER`, `GRADER`. This lets a result distinguish the
historical implementation from the current implementation without requiring
current production files to keep historical hashes forever.

## Three operations

### verify_historical — historical result verification

Re-proves a recorded experiment from its registered immutable evidence:
archived fixtures, recorded hashes, historical registrations. The operation
takes no current-source argument, reads no mutable checkout path and therefore
cannot substitute current bytes for missing history.

Result vocabulary:

```
HISTORICAL_VERIFIED
HISTORICAL_INPUT_UNAVAILABLE_BY_DESIGN
HISTORICAL_MISMATCH
```

A missing or substituted fixture is `HISTORICAL_MISMATCH`. A private input
without retained plaintext is `HISTORICAL_INPUT_UNAVAILABLE_BY_DESIGN`. The
result never authorizes a live run.

### verify_current — current checkout verification

Checks the current checkout against the manifest's selected-source extraction
rules and frozen implementation bindings. It reads the CURRENT selected bytes.

Result vocabulary:

```
CURRENT_MATCH
CURRENT_INPUT_DRIFT
CURRENT_IMPLEMENTATION_DRIFT
```

Input drift and implementation drift are reported independently. The operation
does not claim the historical experiment was rerun and does not grant live
authority by itself.

### admit_live — live admission

Gates a future network experiment BEFORE network. Admission requires: a known
manifest version, exact canonical manifest identity, every `REQUIRED_FOR_LIVE`
selected input available and matching its registered `EXTRACTED_SHA256`,
required implementation bindings matching the frozen registration for that NEW
experiment, and privacy requirements satisfied. A required `PRIVATE_EPHEMERAL`
input is `LIVE_PRIVATE_INPUT_UNVERIFIABLE` in v0: its current bytes cannot be
re-proved without the plaintext the retention promise forbids.

A manifest explicitly marked `HISTORICAL_ONLY` is refused by `admit_live` with
`HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY` even when every hash matches. This is
what keeps "the old run was valid" from becoming "therefore run it again".

Refusal results:

```
HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY
LIVE_INPUT_DRIFT
LIVE_IMPLEMENTATION_DRIFT
LIVE_PRIVATE_INPUT_UNVERIFIABLE
```

Network calls on any refusal: 0.

## Negative controls (normative)

```
C1 unrelated container append        registered section unchanged -> CURRENT_MATCH
C2 registered-section byte mutation  verify_current -> CURRENT_INPUT_DRIFT;
                                     admit_live refuses before network
C3 unknown manifest/extractor/kind   refuse, no interpretation
C4 fixture substitution              HISTORICAL_MISMATCH; no fallback to current
C5 private plaintext absent          HISTORICAL_INPUT_UNAVAILABLE_BY_DESIGN;
                                     never PASS, FAIL_AS_CORRUPT or RECONSTRUCTED
C6 perfect HISTORICAL_ONLY manifest  admit_live refuses; network calls 0
C7 implementation drift only         historical stays valid while verify_current
                                     reports CURRENT_IMPLEMENTATION_DRIFT
```

## T-71 historical control

`lab/history/t71_manifest.json` is one small historical manifest proving the
abstraction against the real problem already observed. It is
`HISTORICAL_ONLY` and binds only already authorized `PUBLIC_ARCHIVABLE`
fixtures required for the T-71 historical source-pin checks:

```
tests/fixtures/t71/quarantine.py.txt   sha256 0960dd992839ca149a81be3bdf80746fb6cd7397023ef2998d429cf03428b985
tests/fixtures/t71/legacy.py.txt       sha256 6e519e624ad6e33a5509337f43d7e8d7f742e2af23aef9a8257b7b568821fe2a
```

The manifest is an additive verification index, not a migration of the
historical T-71 registration. It invents no missing private historical input.
Historical verification stays green from the fixtures while current
`saimail/quarantine.py` and `saimail/legacy.py` legitimately carry different
hashes, and `admit_live` refuses the historical manifest before any network
step.

## Future decision journal policy

Historical `spec/DECISIONS.md` and its addenda are not migrated and not
rewritten. For future records, the policy is: an immutable decision record MAY
be stored as `spec/decisions/D-XYZ.md` with an additive
`spec/decisions/index.json`; a future decision record must never require
rewriting earlier decision bytes. `spec/DECISIONS.md` remains
historical/current compatibility material until a separate migration decision
exists, so current consumers are not broken. Physical creation of
`spec/decisions/` is deferred; recording the policy is the v0 scope.

## Boundaries

The manifest vocabulary applies to FUTURE experiments only. Historical
registrations keep their own formats and hashes. This contract is additive: no
historical artifact, receipt, report or registration is rewritten, no
production module changes, and no live call is made while it is adopted.
