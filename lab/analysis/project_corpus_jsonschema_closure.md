# FG-04B registration and closure: one JSON_SCHEMA live experiment

Registration `sha256:1e7784bb5efc91531ad23fa91ecafd87dc899a26198b8e5e443590a31fb3f978`;
live artifact `lab/out/project_corpus_jsonschema_live_20260920T155227Z.json`
(`sha256:8ee8d5f77bff8b784304a704d7377e9ac13cb3fe98fac9b31d0d85506cd11334`).
All statements below come from that artifact and from the runs named in it. No
raw model output, prompt text or corpus content was persisted, so none is quoted.

## STATUS

FG-04B is DONE with a measured outcome. The registered hypothesis asked whether
enabling JSON_SCHEMA improves the path from generation through the reference
gate to the independent semantic reviewer with everything else frozen. The
answer is a measured, bounded **yes through the reference gate and the event
floor, and a first actual reviewer invocation, with no semantic verdict**:
replicate R1 reached the reviewer and the reviewer's own reply was not one
parseable JSON document, so the outcome is `REVIEWER_ERROR`. Replicate R2
answered `NO_ADVICE`. No retry, repair, replacement or fallback occurred.

## RECOVERED_STATE

State was recovered from `.saipen/STATE.md`, the current BOARD row, the LOG
tail, `humbox/CURRENT-STATE.md`, `humbox/FUTURE-GATES.md`,
`spec/13-EXPERIMENT-REPRODUCIBILITY-v0.md`,
`spec/14-REFERENCE-TELEMETRY-v0.md`, `lab/analysis/reference_telemetry_fg04a.md`,
the T-74 closure and T-80 closure evidence. T-80/FG-04A, T-79/FG-02 and
T-78/FG-03 were DONE; FG-04B was NOT STARTED; no blocker and no operator
action was pending. T-80 was not reopened.

## ROADMAP_POSITION

`humbox/FUTURE-GATES.md` remains roadmap, not state. FG-00 DONE; FG-01
diagnosed/externally blocked; FG-02 DONE; FG-03 DONE; FG-04A DONE; FG-04B DONE
by this closure. FG-04 is the A+B research brick and is now complete as
specified by the roadmap: A delivered the offline diagnostic layer, B delivered
one new registered experiment with a pre-registered outcome. The next product
target is FG-05; it is NOT STARTED and is not begun here.

## EXPERIMENT_REGISTRATION

A brand-new registration exists; T-74's historical registration was neither
continued nor mutated.

- registration: `lab/project_corpus_jsonschema_registration.json`
  `sha256:1e7784bb5efc91531ad23fa91ecafd87dc899a26198b8e5e443590a31fb3f978`
- schema: `lab/project_corpus_jsonschema_schema.json`
  `sha256:84304f73399c35f3dc755a1cf19780e4b66ba1a93308c8a81e04d95f8ca285ef`
- manifest: `lab/project_corpus_jsonschema_manifest.json`
  `sha256:121979de099e09633e5336d30dbde3237afbad62bd1e830b5c953500da5b08fe`,
  EXPERIMENT-MANIFEST-1 identity
  `70f3cd8c299c8ac22b9da3c7930b5c6d99031151a4a67acc1cd9946e2e8773fa`,
  authority `LIVE_ELIGIBLE`
- harness: `lab/project_corpus_jsonschema.py`; tests:
  `tests/test_project_corpus_jsonschema.py`
- attempt marker: `lab/out/project_corpus_jsonschema_live_attempt.json`
  `sha256:a9e201338bd51938c20202ebbc6346c2f6e2d81c954e4d11250cbe6f9464dbc9`

## SCHEMA_POLICY

Policy `CORPUS_ENUM` was chosen before registration and before any network
access; the alternative `SYNTAX_ONLY` is recorded in the registration as
considered and rejected. Under `CORPUS_ENUM` the schema's
`EVIDENCE_REFS.items.enum` is exactly the eight frozen B-018 corpus evidence
refs, so the schema itself restricts reference vocabulary before the existing
product reference gate, which remains independently authoritative. Rationale:
T-74 had already observed an outside-corpus rejection with no schema at all; a
syntax-only constraint would re-test the same membership failure and could not
isolate whether structured output changes the path. Expected diagnostic
distinction: under `CORPUS_ENUM` a product reference-gate rejection implies the
provider did not enforce the enum; under `SYNTAX_ONLY` an unknown canonical ref
would remain attributable to the model's own selection. No dynamic policy
switch occurred after model output was observed.

## FROZEN_VARIABLES

Frozen before the first live call and re-proved by the admission gate: corpus
(`CORPUS_ID sha256:b009bdf3…`, 8 artifacts, 5 declared events), routes A
`SAIFREN` / B `goat/MiniMaxAI/MiniMax-M3`, role-swapped replicates (R1 A->B,
R2 B->A), generator and reviewer prompt templates (hashes recorded), generator
budget 4096, reviewer budget 2048, probe budget 16, no-retry/no-repair/
no-replacement policy, the ephemeral full-visible-output path with the
historical 4000-character projection unchanged, and the LAB-only reference
telemetry contract `REFERENCE-TELEMETRY-1`. The single intentional change from
the retained T-74 design is the JSON_SCHEMA response format on generator and
probe calls; reviewer response format stayed absent.

## CALL_BUDGET

Ceiling 6: probe max 2, generation max 2, review max 2. Actual:
5 calls, 2 probes + 2 generation + 1 review. Spent 5/6; retries 0; repair
calls 0; replacements 0; fallbacks 0; network calls 5. `logical_dispatches` 5
equals `spent_total`, every call carries ordinal 1..5 and
`wrapper_retry = false`, so no hidden wrapper retry is possible in the
recorded accounting.

## PRE_LIVE_ADMISSION

Admission was proved before the first network call, inside the run and recorded
in the artifact: manifest identity `70f3cd8c…`, `verify_current` =
`CURRENT_MATCH`, `admit_live` admitted = true, `network_calls` 0 at admission.
Every check passed: newly registered manifest (identity distinct from the
historical T-71 manifest), manifest identity matches registration, implementation
identity matches registration, input identities match, current corpus matches
the frozen corpus, schema bytes match the registration, the allowed reference
set equals the rebuilt corpus refs, budgets match, the call ceiling is active,
and the FG-04A telemetry contract is available. Historical verification alone
was never used as authority.

## PROBE_RESULTS

Probes are recorded separately and were never promoted to generation results.

- `A/PROBE` (requested `SAIFREN`, reported `deepseek/deepseek-v4-flash`):
  transport returned, HTTP 200, `finish_reason=length`, empty visible content,
  error class `EmptyOutput`; parse `NOT_TEXT`, schema `NOT_EVALUABLE`. A
  16-token capability probe under `json_schema` produced no output.
- `B/PROBE` (requested `goat/MiniMaxAI/MiniMax-M3`, reported
  `MiniMaxAI/MiniMax-M3`): `REQUEST_ACCEPTED`, parse `OK`, schema `VALID`,
  conforming `{"result":"NO_ADVICE"}` sample.
- Provider enforcement is recorded as `NOT_PROVEN` by construction; a
  conforming sample is not enforcement.

## GENERATION_RESULTS

- R1 (generator A / reviewer B): HTTP 200, `finish_reason=stop`, 2345 visible
  bytes, parse `OK`, schema `VALID`. A candidate was parsed (candidate id
  `sha256:7ba64530b476450ae3f392da66a83961816b7dc1c7f5049bd9e734f4cbeb628f`,
  2 observed items, 1 counterevidence item, `observed_scope` exactly
  `project:saimail`).
- R2 (generator B / reviewer A): HTTP 200, `finish_reason=stop`, 22 bytes,
  parse `OK`, schema `VALID`, result `NO_ADVICE`.

## REFERENCE_TELEMETRY

R1 telemetry (REFERENCE-TELEMETRY-1, diagnostic only): `corpus_ref_relation`
`CLEAN`; known evidence refs 7; distinct declared events 4; unknown canonical
0; malformed 0; non-text 0; event refs misused as evidence 0; corpus ids misused
as evidence 0. R2 had no candidate, telemetry `NOT_EVALUABLE`. Telemetry held no
acceptance authority: the product gate re-read the actual candidate and corpus.

## PRODUCT_GATE_RESULTS

The unchanged production path decided every outcome. R1 passed the product
reference gate (zero outside-corpus refs against the frozen corpus) and the
event floor, then invoked the semantic reviewer exactly once. Reviewer
invocation failed at the strict reviewer parser, and the orchestration returned
`ERROR / ALLY_GEN_REVIEWER_ERROR`. R2 returned `NO_ADVICE` and spent zero
reviewer calls. No reviewed type-state was minted.

## EVENT_FLOOR

R1: `MET` — every observed ref was a known corpus evidence ref and the
candidate's observed refs spanned 4 distinct declared events (floor is 2).
R2: `NOT_EVALUABLE` (no candidate). `NOT_EVALUABLE` was not converted to `MET`
anywhere.

## REVIEWER_RESULTS

One reviewer call was made (ordinal 4, requested `SAIFREN` in R1's role swap;
reported `MiniMaxAI/MiniMax-M3`), 2048 tokens, `response_format` absent,
`finish_reason=stop`, 3801 visible bytes, and the strict reviewer parser
refused the reply: `json_status` `BAD_JSON`, `parser_status` `SCHEMA_ERROR`,
`parser_error_code` `ALLY_LAB_BAD_JSON`. Zero of the eight semantic dimensions
were decided; the replicate outcome class is `REVIEWER_ERROR`. Reviewer
rejection was not collapsed into a transport, schema or reference failure.

## T74_COMPARISON

Only retained measurable facts are compared. T-74 R1: strict JSON candidate ->
`ALLY_GENERATED_REF_OUTSIDE_CORPUS` -> reviewer calls 0. FG-04B R1: strict JSON
candidate -> product reference gate PASS (telemetry `CLEAN`, 7 known refs, 4
declared events) -> reviewer calls 1 -> reviewer reply unparseable
(`ALLY_LAB_BAD_JSON`) -> `REVIEWER_ERROR`. T-74 R2 and FG-04B R2 are both
`NO_ADVICE` with reviewer calls 0. No claim is made about why T-74 generated its
bad reference; the exact historical class remains `UNKNOWN`.

## NO_REPAIR_PROOF

No repair, normalization or substitution exists in the path: no lowercasing, no
prefix addition, no whitespace trimming, no nearest-ref matching, no event-ref
to evidence-ref mapping, no regeneration because a reference was bad, and no
candidate rewrite before product validation. A failed candidate is evidence.
The reviewer's unparseable reply was recorded, not repaired, and no second
reviewer call was made.

## PRIVACY_PROOF

The artifact records `false` for prompt persistence, output persistence,
candidate prose persistence, reviewer rationale persistence, error-body
persistence, full-output persistence and auth-token persistence. Only hashes,
byte counts, identities, verdicts and counts are durable. The harness scrubs
the retained transport record in a `finally` block even on parse failure, and
`assert_no_secret` runs before any artifact write. Provider-side retention
remains `NOT_VERIFIED_BY_SAIMAIL`.

## NETWORK_MODEL_CALL_ACCOUNTING

| ordinal | category | role | requested | reported | purpose | returned | retry |
|---|---|---|---|---|---|---|---|
| 1 | PROBE | A | SAIFREN | deepseek/deepseek-v4-flash | CAPABILITY_PROBE | yes | no |
| 2 | PROBE | B | goat/MiniMaxAI/MiniMax-M3 | MiniMaxAI/MiniMax-M3 | CAPABILITY_PROBE | yes | no |
| 3 | GENERATION | A | SAIFREN | deepseek/deepseek-v4-flash | GENERATOR_CANDIDATE | yes | no |
| 4 | REVIEW | B | goat/MiniMaxAI/MiniMax-M3 | MiniMaxAI/MiniMax-M3 | SEMANTIC_REVIEW | yes | no |
| 5 | GENERATION | B | goat/MiniMaxAI/MiniMax-M3 | MiniMaxAI/MiniMax-M3 | GENERATOR_CANDIDATE | yes | no |

Reported models are what the gateway stated; a prefix is a namespace, not a
provider claim. No participant was replaced; no call was repeated.

## FOCUSED_TESTS

`python -m pytest tests/test_project_corpus_jsonschema.py
tests/test_ally_generation_gate.py tests/test_ally_generation_corpus.py
tests/test_ally_generation_live.py tests/test_ally_generation_review.py
tests/test_ally_generation_review_authority.py tests/test_ephemeral_full_output.py
tests/test_experiment_manifest.py tests/test_project_corpus_budget4096.py
tests/test_project_corpus_reachability.py tests/test_reference_telemetry.py
tests/test_reference_telemetry_integration.py` — 304 tests, 0 failures,
0 errors, 0 skipped (run after the live artifact was written).

The focused experiment file alone is `tests/test_project_corpus_jsonschema.py`
with 19 tests: registration identity and refusal, prompt drift refusal, schema
identity/policy/enum, manifest input and implementation consistency, the
bounded schema validator (including an unsupported-keyword refusal), the call
ceiling, the dry role swap and the schema/response-format separation, exact
call accounting and no-hidden-retry, reference-gate/telemetry parity for an
outside ref, the full outcome-class matrix, historical-manifest refusal by
`admit_live`, live admission, privacy canaries, the write-time privacy
tripwire, a network-free dry run, and the publish-once attempt marker.

## REGRESSION_TESTS

FG-04A telemetry regressions and product reference-gate parity pass on the
post-live tree (included in the 304-test battery above). Retained-artifact
verification: the live artifact, report, analysis, registration, schema,
manifest and attempt marker are hash-pinned by
`tests/test_repo_consistency.py`. Historical verification:
`verify_historical(lab/history/t71_manifest.json)` returned
`HISTORICAL_VERIFIED`; no frozen T-71 fixture was mutated. T-74's live
artifact, report, analysis and closure remained unchanged and stay pinned.
Relevant generation/reviewer regressions pass; production `saimail/*` modules
carry no JSON_SCHEMA-harness or telemetry dependency.

## FULL_SUITE

Command: `python -m pytest --junitxml=<temp>/t81-full.xml -q`, environment:
the repository's canonical Python 3.11 interpreter with the `[test]` extra
(`tiktoken 0.12.0`, `cryptography`, `keyring`), zero live calls during the
suite. Final result after all closure files were written: **2040 tests,
0 failures, 0 errors, 0 skipped, 15.3 s**.

## SAIPEN_VALIDATION

`python tools/validate.py --gate core`: **3 FAIL, 22 WARN**, verdict
`CURRENT_FAIL / CARRIED_DEBT_UNCHANGED` against the T-74/T-80 baseline count.
The three failures are the carried `SRC-017/T-41` unresolved receipt, the
carried `SRC-036` source-credential gate, and a stale improve-report
fingerprint (`improve-report`, from the earlier improve cycle, pre-existing and
not touched by T-81). No T-81 file is named in any failure. The kitchen digest
still reads `remaining: T-78` (SAIPEN lifecycle/navigation debt, not
hand-edited). These are carried SAIPEN debts reported separately from the
experiment outcome; no repair of FG-01, SRC-017/T-41, SRC-036 or the digest
was attempted.

## NEGATIVE_FINDINGS

- Semantic review is still not demonstrated; the blocker moved from the
  generator's reference vocabulary to the reviewer's reply shape.
- The exact T-74 bad-reference class remains `UNKNOWN`; nothing in this
  experiment classifies it.
- One conforming probe sample does not prove that the provider enforces JSON
  Schema; provider enforcement remains `NOT_PROVEN`.
- Route A's 16-token capability probe returned an empty completion under
  `json_schema`; a generated 2345-byte candidate from the same route at 4096
  tokens did succeed, so the probe is not a statement about generation.
- One sample per role assignment is not a model property and supports no
  ranking.

New research hypothesis recorded as future work (not executed in T-81): does
constraining or reformatting the reviewer's own output (for example a reviewer
`response_format`, or a different reviewer budget/route) change the same
generator path's ability to produce eight parseable semantic verdicts? This
requires a new registration and a new bounded task.

## FILES_CHANGED

Added (LAB/tests/docs only; no production `saimail/*` change):
`lab/project_corpus_jsonschema.py`,
`lab/project_corpus_jsonschema_registration.json`,
`lab/project_corpus_jsonschema_schema.json`,
`lab/project_corpus_jsonschema_manifest.json`,
`lab/out/project_corpus_jsonschema_dry_run.json`,
`lab/out/project_corpus_jsonschema_live_20260920T155227Z.json`,
`lab/out/PROJECT_CORPUS_JSONSCHEMA_REPORT_20260920T155227Z.md`,
`lab/out/project_corpus_jsonschema_live_attempt.json`,
`lab/analysis/project_corpus_jsonschema_20260920T155227Z.md`,
`lab/analysis/project_corpus_jsonschema_closure.md`,
`tests/test_project_corpus_jsonschema.py`; updated: `lab/LATEST.md`,
`humbox/CURRENT-STATE.md`, `tests/test_repo_consistency.py` (the two FG
navigation tripwires refreshed in place with T-81 evidence, plus the new
FG-04B tripwire), plus SAIPEN memory through the canonical operations.

## SAIPEN_LIFECYCLE

One bounded SAIPEN task (T-81, source receipt SRC-068) was claimed, executed
through SCOUT/BUILD/VERIFY/REVIEW/SHIP with canonical checkpoints, and closed
locally. Ship performs no commit, tag, push or publication: no explicit project
policy required one and no fake release was created.

## NEXT_TARGET

FG-05 — END-TO-END LOCAL SCENARIO. Not started in this task.

## BLOCKER

NONE for the experiment. Carried, unrelated SAIPEN debts stay carried:
SRC-017/T-41 closure provenance and the SRC-036 source-credential gate.

## OPERATOR_ACTION

NONE.

## NEXT_EXACT_ACTION

`saipen start "FG-05 end-to-end local scenario"` when the operator chooses to
begin the next roadmap brick.
