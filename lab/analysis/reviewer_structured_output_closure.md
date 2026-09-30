# V2-03 closure: reviewer structured-output bounded experiment

Registration `sha256:1e59dfc30f939fb34976d1b795ef49de037603261495bc76fdba430fcc87ba19`;
live artifact `lab/out/reviewer_structured_output_live_20260920T221857Z.json`
(`sha256:9997a9a23e59de250e81aee37d66924d9a1a8b42af3b6f6b3f449d091e268633`).
All statements below come from that artifact and from the runs named in it. No
raw model output, prompt text or corpus content was persisted, so none is quoted.

## STATUS

V2-03 is DONE with a measured **negative** outcome. The registered hypothesis
asked whether adding native structured-output enforcement to the independent
reviewer — the single intentional change from the FG-04B configuration — would
let the already-reached reviewer invocation produce one strict parseable
`SemanticReviewReport`. The answer is **no in this one bounded sample**: the
reviewer received the registered `json_schema` response format and still did not
return one strict JSON document, so the outcome is `REVIEWER_BAD_JSON` with zero
semantic verdicts. Replicate R2 answered `NO_ADVICE`. No retry, repair,
replacement or response-format fallback occurred.

## RECOVERED_STATE

State was recovered from `.saipen/STATE.md`, the current BOARD, the LOG tail,
`humbox/CURRENT-STATE.md`, `humbox/FUTURE-GATES-V4.md`,
`humbox/FUTURE-GATES-V2.md` (V2-03 section),
`spec/09-ALLY-GENERATION-v0.md`, `spec/13-EXPERIMENT-REPRODUCIBILITY-v0.md`,
the FG-04B closure/registration/manifest/schema/harness, the T-73 structured-
output capability registration, and the `lab/ally_generation_live.py` /
`saimail/ally_generation.py` parser and gate authorities. T-95 / V4-01 was DONE,
phase DONE, no active Work, no blocker and no operator action pending; V2-03 was
the only NOT STARTED gate and remained optional.

## OPTIONAL_RESEARCH_SELECTION

This gate was selected intentionally by the operator as **optional research**
after Roadmap v4 reached a natural product STOP. It is **not** promoted into a
product dependency. The work is LAB-only: no production `saimail/*` semantics
changed.

## NAVIGATION_DRIFT

`humbox/CURRENT-STATE.md` carried one stale historical sentence in the "Roadmap
v3 position (COMPLETED)" paragraph: "The next executable gate is V4-01, NOT
STARTED." The current truth is V4-01 DONE via T-95, no mandatory gate selected
after V4-01, and V2-03 explicitly selected for this run. The sentence was
corrected in place during this closure; no separate navigation ticket was
created.

## HISTORICAL_COMPARATOR

FG-04B / T-81. Registration `sha256:1e7784bb…`, manifest identity
`70f3cd8c…`. Under FG-04B the generator/probe carried `JSON_SCHEMA` and the
reviewer `response_format` was `ABSENT`; the R1 candidate passed the product
reference gate and event floor and the reviewer was invoked once, but its reply
was not one parseable JSON document (`ALLY_LAB_BAD_JSON`, 3801 bytes,
`finish_reason=stop`), outcome `REVIEWER_ERROR`, zero semantic verdicts.

## HYPOTHESIS

Holding the already-reached FG-04B path fixed, does adding native structured-
output enforcement to the independent reviewer (`response_format` ABSENT ->
`JSON_SCHEMA`) produce one strict parseable `SemanticReviewReport`?

## SINGLE_VARIABLE

`reviewer response_format ABSENT -> JSON_SCHEMA`. Everything else frozen:
generator route/format/schema, reviewer route, role assignment, corpus, prompts,
rubric, token budgets (generator 4096, reviewer 2048, probe 16), temperature
(`NOT_SENT`), reference gate, event floor, parser semantics, the ephemeral
full-output path, and retry/repair/replacement/fallback policy (all zero).

## REVIEWER_SCHEMA

`lab/reviewer_structured_output_schema.json`, template sha256
`8db0e5b00c8d817ce9130814ee5a952c6d1ead344539e7ce6aa4acdba6396bb9`, wrapper
`json_schema` name `saimail_ally_review_report`, `strict: true`. The template is
the existing reviewer parser contract expressed narrowly: object with
`additionalProperties: false` and exactly `candidate_id`, `corpus_id`,
`rubric_version`, `dimensions`; `dimensions` is an array of exactly eight rows;
each row is an object with `additionalProperties: false` and exactly `dimension`
(closed enum of the eight `DIMENSIONS`), `verdict` (closed enum PASS/FAIL/
UNKNOWN), `rationale` (string, 1..1024 bytes) and `evidence_refs` (array of
strings, bounded to `MAX_EVIDENCE_REFS_PER_ITEM`, `uniqueItems`). `rubric_version`
is pinned to `ALLY-REVIEW-1`; `candidate_id` and `corpus_id` are pinned per
invocation to the exact candidate and corpus identity the reviewer was given.

**Schema-vs-product boundary.** JSON Schema can require exactly eight rows but
cannot conveniently express "exactly one row for each of the eight dimensions".
The schema therefore bounds the row vocabulary and the array size; exact coverage
and uniqueness stay the product's business. The existing `SemanticReviewReport`
constructor remains authoritative and still rejects missing, duplicate and
unknown dimensions. Provider/schema acceptance never replaces product
validation, and the schema is not a second semantic reviewer.

## REGISTRATION

`lab/reviewer_structured_output_registration.json`
(`sha256:1e59dfc30f939fb34976d1b795ef49de037603261495bc76fdba430fcc87ba19`),
identity `REVIEWER-STRUCTURED-OUTPUT-1`, registered under T-96 / SRC-084. It pins
the experiment identity, the FG-04B historical comparator, the exact B-018 corpus
identity, routes, replicate roles, generator format (unchanged) and reviewer
format (JSON_SCHEMA), both schema paths and hashes, prompts and hashes, both
token budgets, the closed terminal-outcome vocabulary and precedence, the
`<=6` call ceiling with retries/repairs/replacements/fallbacks all zero, the
no-response-format-fallback policy, privacy rules and the admission
requirements.

## MANIFEST

`lab/reviewer_structured_output_manifest.json`, EXPERIMENT-MANIFEST-1, authority
`LIVE_ELIGIBLE`, experiment id `V2-03-REVIEWER-STRUCTURED-OUTPUT-1`. Three
whole-file inputs (registered reviewer schema, registered generator schema, B-018
corpus registration) and ten implementation bindings. `verify_current` and
`admit_live` were run and PASSed before the first network call; historical
verification alone was never used as authority. The FG-04B registered
configuration was re-proved reconstructable from the current checkout
(`fg04b_configuration_reconstructable`) before network.

## CORPUS / ROUTES / TOKEN_BUDGETS

Exact frozen B-018 corpus `sha256:b009bdf3…` (8 artifacts, 5 declared events;
build `sha256:0e05460a…`). Routes A `SAIFREN` / B `goat/MiniMaxAI/MiniMax-M3`;
role-swapped replicates (R1 generator A -> reviewer B, R2 generator B ->
reviewer A). Token budgets probe 16, generator 4096, reviewer 2048; temperature
`NOT_SENT`.

## DRY_CONTROLS

`A_valid_conforming`, `B_extra_top_field`, `C_missing_dimension`,
`D_duplicate_dimension`, `E_unknown_dimension`, `F_invalid_verdict`,
`G_candidate_mismatch`, `H_corpus_mismatch`, `I_rubric_mismatch`,
`J_malformed_json`, `K_format_rejected`, `L_no_advice_zero_reviewer` — all
PASS, deterministic and offline. The dry run reached `REVIEWER_VERDICT_PARSED`
and `NO_ADVICE` with 0 network calls. When the dry run is performed with the
registered reviewer schema template, `maxLength` is used, so the harness uses
its own bounded validator; the FG-04B schema bytes and the FG-04B harness itself
are unchanged.

## ADMISSION

Proved before the first network call and recorded in the artifact:
`verify_current` `CURRENT_MATCH`, `admit_live` true, `network_calls` 0 at
admission, `granted_before_first_network_call` true. Every check passed:
manifest newly registered and identity matching, implementation identity
matching, input identities matching, current corpus matching the frozen corpus,
generator schema bytes matching the FG-04B hash, reviewer schema template
matching the registration, allowed reference set matching, FG-04B configuration
reconstructable, budgets matching, call ceiling active, and live admission
granted by `admit_live`.

## CALL_BUDGET

Ceiling 6 (probe 2, generation 2, review 2). Actual 5 calls: 2 probes + 2
generation + 1 review. Spent 5/6; retries 0; repair calls 0; replacements 0;
fallbacks 0; network calls 5. `logical_dispatches` 5 equals `spent_total`, all
`wrapper_retry` false.

## PROBE_RESULTS

- `A/PROBE` (requested `SAIFREN`): HTTP 200, `finish_reason=length`, empty
  visible content, transport `ERROR`, `EmptyOutput`, parse `NOT_TEXT`, schema
  `NOT_EVALUABLE` — the same 16-token probe behaviour FG-04B recorded for route A.
- `B/PROBE` (requested `goat/MiniMaxAI/MiniMax-M3`): `REQUEST_ACCEPTED`, parse
  `OK`, schema `VALID`, conforming `{"result":"NO_ADVICE"}` sample.
- Provider enforcement is `NOT_PROVEN` by construction; a conforming sample is
  not enforcement.

## GENERATION_RESULTS

- R1 (generator A): HTTP 200, `finish_reason=stop`, 2529 visible bytes, parse
  `OK`, schema `VALID`; a candidate passed the product reference gate (`CLEAN`)
  and the event floor (`MET`, 4 distinct declared events) with zero outside refs.
- R2 (generator B): HTTP 200, `finish_reason=stop`, 22 bytes, result
  `NO_ADVICE`.

## REVIEWER_RESULT

One reviewer call (ordinal 4, requested `SAIFREN` in R1's role swap; reported
`MiniMaxAI/MiniMax-M3`), 2048 tokens. **The reviewer request carried the
registered reviewer `json_schema`**: `response_format_kind` `JSON_SCHEMA`,
`response_format_sha256`
`91a32e66d89b376783d86edaab7d811e11199c94b399f1b2537a35a3fabe662a` (the exact
reviewer schema built for the R1 candidate/corpus pair), `request_body_sha256`
`e0cbd6704210e0e60fe1906167a1f82fe159222ce3fbbc6611ce774482447104`,
`request_body_bytes` 35907. The reply was HTTP 200, `finish_reason=stop`, 4178
visible bytes, and the strict reviewer parser refused it: `json_status`
`BAD_JSON`, `schema_status` `NOT_EVALUABLE`, `parser_error_code`
`ALLY_LAB_BAD_JSON`. Zero of the eight semantic dimensions were decided; the R1
terminal class is `REVIEWER_BAD_JSON`. The parse-shape observer records a fence
token present and a non-JSON first token (structural observation only; the raw
text is not retained).

## REQUEST_FORMAT_VS_ENFORCEMENT

`response_format` was present and corresponds to the registered JSON_SCHEMA
wrapper, proved mechanically from the dispatched request body — not inferred
from the returned shape. **REQUEST SENT WITH SCHEMA != PROVIDER ENFORCED
SCHEMA.** Provider enforcement remains `NOT_PROVEN`; this experiment records a
request, not an enforcement guarantee.

## NO_REPAIR_PROOF

No repair, normalization or substitution exists in the path: no markdown-fence
stripping, no JSON substring extraction from prose, and no fallback from
`JSON_SCHEMA` to `json_object`, plain text or a prompt-only request. There was no
retry, no repair prompt, no participant replacement and no second reviewer call.
A malformed reply is evidence.

## PRIVACY_PROOF

The artifact records `false` for prompt persistence, output persistence,
candidate prose persistence, reviewer rationale persistence, error-body
persistence, full-output persistence and auth-token persistence. Only hashes,
byte counts, identities, verdicts and counts are durable. The harness scrubs the
retained transport record in a `finally` block even on parse failure, and
`assert_no_secret` runs before any artifact write. Provider-side retention
remains `NOT_VERIFIED_BY_SAIMAIL`.

## NETWORK_MODEL_CALL_ACCOUNTING

| ordinal | category | role | requested | reported | purpose | returned | retry |
|---|---|---|---|---|---|---|---|
| 1 | PROBE | A | SAIFREN | (empty) | CAPABILITY_PROBE | yes | no |
| 2 | PROBE | B | goat/MiniMaxAI/MiniMax-M3 | MiniMaxAI/MiniMax-M3 | CAPABILITY_PROBE | yes | no |
| 3 | GENERATION | A | SAIFREN | (reported) | GENERATOR_CANDIDATE | yes | no |
| 4 | REVIEW | B | SAIFREN (role swap) | MiniMaxAI/MiniMax-M3 | SEMANTIC_REVIEW | yes | no |
| 5 | GENERATION | B | goat/MiniMaxAI/MiniMax-M3 | MiniMaxAI/MiniMax-M3 | GENERATOR_CANDIDATE | yes | no |

No participant was replaced; no call was repeated; no fallback occurred.

## CLAIM_BOUNDARY

The strongest justified conclusion is: **one registered reviewer invocation was
reached with the registered JSON_SCHEMA request and still did not return one
strict JSON document**. No success claim is made. Explicitly NOT claimed:
reviewer reliability, semantic correctness, provider enforcement in general,
stable route capability, universal structured-output support, reviewer
truthfulness, or production readiness of generative advice. One sample proves
reachability questions only.

## SEMANTIC_VERDICTS

Not reached: zero semantic verdicts were produced. A parseable FAIL or UNKNOWN
report would still have counted as output-format reachability; none occurred.

## NEGATIVE_FINDINGS

- Sending a registered reviewer `json_schema` response format did not, in this
  one bounded sample, make the reviewer return one strict JSON document. The
  observed blocker is unchanged in kind from FG-04B: the reviewer's own reply
  shape.
- The reply was larger (4178 bytes) than FG-04B's (3801 bytes) and still not
  strict JSON; the parse-shape observer records a fence token present, so the
  reply was not one bare JSON object.
- One sample per role assignment is not a model property and supports no
  ranking.
- Provider enforcement of the schema remains `NOT_PROVEN`; the request was sent,
  which is all this experiment controlled.

## FOCUSED_TESTS

`python -m pytest tests/test_reviewer_structured_output.py` — 22 tests, 0
failures, 0 errors, 0 skipped. They cover registration identity and refusal,
prompt-drift refusal, single-variable difference from FG-04B, reviewer schema
identity/bounds/identity pinning, the schema-vs-product coverage boundary, FG-04B
generator-schema immutability, all twelve dry controls, the terminal-outcome
matrix totality, admission and drift refusal, FG-04B reconstructability, privacy,
and the dry-run/credential/marker lifecycle.

## REGRESSION_TESTS

Project-corpus (FG-04B), experiment-manifest, reference-telemetry, FG-05/FG-06,
P1, U1, V2-02, release/a2 immutability, repo-consistency and the V2-03 tripwire
all pass. Frozen FG-04B artifacts and the frozen `0.0.2a2` / `0.0.2a1` wheels
are byte-identical.

## FULL_SUITE

`python -m pytest -q --junitxml=...` — **2307 passed, 0 failed, 0 errors,
0 skipped**. Environment: the repository's canonical Python 3.11 interpreter
with the `[test]` extra; zero live calls during the suite. Additive delta over
the 2284 baseline is +23: the new `tests/test_reviewer_structured_output.py`
(22) plus one auto-discovered lab module parametrization. No test was weakened.

## LINT

`ruff --select E4,E7,E9,F` clean on the touched test files. The frozen harness
`lab/reviewer_structured_output.py` is the implementation bound into the live
artifact and its registration; it carries one pre-freeze `F841` (an unused local
`refs` left from an earlier draft). Editing the harness after the live run would
change its hash and invalidate the recorded implementation binding, so it is
left byte-identical to the registered implementation, exactly as the frozen
`lab/project_corpus_jsonschema.py` was left byte-identical after T-81.

## SAIPEN_VALIDATION

`python tools/validate.py --gate core` — inherited `3 FAIL / 21 WARN`, unchanged.
The three failures are the carried `SRC-017/T-41` receipt, `SRC-036` source
credential gate, and the stale improve-report fingerprint. No V2-03 file is
named. No unrelated SAIPEN debt was repaired.

## REVIEW_FINDINGS

Reviewed for more than one intentional variable, reviewer budget change,
reviewer prompt change, route/corpus/generator-schema change, parser repair,
markdown stripping, substring JSON extraction, response-format fallback,
malformed-result rerun, provider-refusal retry, live calls before admission,
schema acceptance called semantic validity, one sample called reliability,
candidate/release evidence touched, and secret persistence. No P0/P1/P2
findings.

## FILES_CHANGED

Added (LAB/tests/docs only; no production `saimail/*` change):
`lab/reviewer_structured_output.py`,
`lab/reviewer_structured_output_registration.json`,
`lab/reviewer_structured_output_schema.json`,
`lab/reviewer_structured_output_manifest.json`,
`lab/out/reviewer_structured_output_dry_run.json`,
`lab/out/reviewer_structured_output_live_20260920T221857Z.json`,
`lab/out/REVIEWER_STRUCTURED_OUTPUT_REPORT_20260920T221857Z.md`,
`lab/out/reviewer_structured_output_live_attempt.json`,
`lab/analysis/reviewer_structured_output_20260920T221857Z.md`,
`lab/analysis/reviewer_structured_output_closure.md`,
`tests/test_reviewer_structured_output.py`; updated: `lab/LATEST.md`,
`humbox/CURRENT-STATE.md` (navigation correction + V2-03 section),
`humbox/FUTURE-GATES-V4.md` (optional research lane + next brick),
`tests/test_repo_consistency.py` (new V2-03 tripwire), plus SAIPEN memory
through the canonical operations.

## SAIPEN_LIFECYCLE

One bounded SAIPEN task (T-96, source receipt SRC-084) was claimed, executed
through SCOUT/BUILD/VERIFY/REVIEW/SHIP with canonical checkpoints, and closed
locally. Ship performs no commit, tag, push or publication.

## ROADMAP_AUTHORITY

`humbox/FUTURE-GATES-V4.md` remains the current roadmap authority.

## ROADMAP_REFRESH

V4-01 is DONE. V2-03 is now closed with the measured negative
`REVIEWER_BAD_JSON`. L3 is narrowed from "reviewer reply shape blocks semantic
review" to "one bounded sample could not reach a parseable semantic reviewer
report even with the registered reviewer JSON_SCHEMA; the reviewer reply shape
remains the observed blocker in this sample". No generative-advice production
work is created. No new practical product gap is observed, so the roadmap may
truthfully end with NO SELECTED NEXT GATE; no v5 is created.

## NEXT_TARGET

NONE — no evidence-backed gate is justified. V2-03 is closed as negative
evidence. STOP.

## BLOCKER

NONE.

## OPERATOR_ACTION

NONE.

## NEXT_EXACT_ACTION

NONE — STOP.
