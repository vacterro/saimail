# SAIFREN live runs — index

**Latest: [run 5 — 2026-09-17T15:20:12Z](analysis/20260917T152012Z.md).** Latest stability run: [S1 — 2026-09-17T16:16:36Z](analysis/stability_20260917T161636Z.md).

This file is the index. It points at the newest interpretation and lists every
run that came before it. It does not summarise them: a summary of an experiment
is a place for a number to lose its denominator.

Three rules hold for everything below (D-022):

- **A run's artifact is immutable.** `lab/out/saifren_live_<stamp>.json` and its
  report `lab/out/SAIFREN_REPORT_<stamp>.md` are written once and never edited.
  `lab/out/SAIFREN_REPORT.md` is a copy of the newest one, kept for convenience.
- **A run's interpretation is immutable.** `lab/analysis/<stamp>.md` is the
  reading of that run. A later run may contradict it; it does not rewrite it.
- **A negative finding stays visible.** Nothing here is tidied because a later
  run looked better.

| # | started | artifact | protocol | live calls | routes observed | experiment class (derived, D-024) | verdicts | reading |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-09-17T10:51:04Z | `saifren_live_20260917T105104Z.json` | v3 / SAIB3 | 22 | 1 | `SAIFREN_SINGLE_ROUTE` | PASS 9, FAIL 2, MEASURED 3 | [analysis](analysis/20260917T105104Z.md) |
| 2 | 2026-09-17T11:46:16Z | `saifren_live_20260917T114616Z.json` | v3 / SAIB3 | 22 | 2 | `SAIFREN_NOT_OBSERVED` | PASS 8, FAIL 2, MEASURED 3, ERROR 1 | [analysis](analysis/20260917T114616Z.md) |
| 3 | 2026-09-17T12:23:46Z | `saifren_live_20260917T122346Z.json` | v4 / SAIB4 | 22 | 2 | `SAIFREN_NOT_OBSERVED` | PASS 8, FAIL 1, MEASURED 3, ERROR 2 | [analysis](analysis/20260917T122346Z.md) |
| 4 | 2026-09-17T15:16:23Z | `saifren_live_20260917T151623Z.json` | v4 / SAIB4 | 12 (6 discovery, 6 experiment) | 2 | `SAIFREN_EXTERNAL_COMPARATOR` | PASS 1, FAIL 1, MEASURED 1 | [analysis](analysis/20260917T151623Z.md) |
| 5 | 2026-09-17T15:20:12Z | `saifren_live_20260917T152012Z.json` | v4 / SAIB4 | 12 (6 discovery, 6 experiment) | 2 | `SAIFREN_EXTERNAL_COMPARATOR` | PASS 1, FAIL 1, MEASURED 1 | [analysis](analysis/20260917T152012Z.md) |

Runs 4 and 5 are a **narrow validation sample**, not a replacement for runs 1–3:
three units declared in source before they ran. Their numbers are not comparable
with a 22-unit plan and are not meant to be. Run 5 repeats run 4 against the
shipped code after review fixed three defects in the harness; run 4 measures the
revision before those fixes and stays on the record as such. The harness cap
moved from 24 to 30 between them, so a discovering run reserves its 8 probes
inside its own declared bound.

## Stability runs (D-025)

A registered repeat sample, not a replacement for any run above: four cases,
three identical calls per participant per case, analysis rules fixed in
`lab/stability_registration.json` before the first call. Its artifact and report
follow the same immutability rules as the runs above.

| # | started | artifact | registration | live calls | experiment class (derived, D-024) | findings | reading |
|---|---|---|---|---|---|---|---|
| S1 | 2026-09-17T16:16:36Z | `stability_live_20260917T161636Z.json` | `sha256:c60bc6ac…` | 30 (6 discovery, 24 experiment) | `SAIFREN_EXTERNAL_COMPARATOR` | MODEL_VARIANCE 4, CROSS_MODEL_DISAGREEMENT 0, PROTOCOL_HOTSPOT 0 | [analysis](analysis/stability_20260917T161636Z.md) |

What it changed about the findings below: the three typed-semantics cases were
stable across every repeat of both models; all four variance findings are in
`S3.mailbox`; and `MiniMax-M3` answered M3 `IGNORE` three times out of three —
one participant failing one item every time, which is neither a hotspot nor a
cross-model disagreement under the registered rules.

## What each run is entitled to call itself

The class column is derived from each stored artifact by
`lab/experiment_class.py` and checked against this table by
`tests/test_experiment_class.py`. The artifacts and their readings are not
edited (D-022); the class is added beside them, not written into them.

- **Run 1 is `SAIFREN_SINGLE_ROUTE`.** Every call went through the alias and all
  22 resolved to one model. One observed member, no cross-member claim.
- **Runs 2 and 3 are `SAIFREN_NOT_OBSERVED`.** Both participants were pinned
  catalog ids; no call went through the alias, so neither answering model has
  SAIFREN membership evidence *from that run*. They measured two models, not
  SAIFREN.
- **Runs 4 and 5 are `SAIFREN_EXTERNAL_COMPARATOR`.** Role A reached
  `deepseek/deepseek-v4-flash` through the alias: an observed member. Role B,
  `MiniMaxAI/MiniMax-M3`, was selected from the live catalog and is an
  **external comparator**. It is not a SAIFREN member, and nothing in either run
  shows it is. Where their readings say "two distinct observed participants",
  read: two distinct reported models, exactly one of them an observed SAIFREN
  member.

No run so far is `SAIFREN_INTERNAL`: the roster is not observable, and no alias
sample has resolved to more than one member.

Runs 2 and 3 shipped without an analysis file; theirs were written on
2026-09-17 from the stored artifacts, after the fact, and say so at the top.

## Findings that no later run has overturned

- **Hidden context.** Reported `prompt_tokens` exceed what the harness sent by
  roughly 2.8k tokens on every measured call, on every route. Every answer in
  every run was produced under instructions nobody here can read. This is a
  standing limit on every semantic conclusion drawn from this lab.
- **Hidden reasoning.** `completion_tokens` run far above the visible answers.
  None of it is stored, by design — and none of it is available to explain a
  result either.
- **Small samples, and unstable answers.** Most units are n=1. Runs 4 and 5 ran
  the identical `S3.mailbox` prompt on the identical model four minutes apart
  and got different answers on two of four items. A single run of this unit
  supports no conclusion about any model, including the runs here that report
  one. Stability run S1 repeated it three times per model: the
  instability is real on M1, M2 and M4, while the failing item M3 did not vary.
- **Routes were pinned, not discovered, in runs 2 and 3.** Those runs sent two
  model identifiers typed into the harness. They measured cross-model behaviour
  and claimed nothing about SAIFREN membership, because they could not. Run 4
  resolves participants from the discovery surface instead (D-020).
- **The roster is still not observable.** `GET /v1/models` lists the combo but
  carries no member list, and the administrative surface refuses the SAIRoute
  credential. Membership is *sampled* through the alias, and a sample is not a
  roster. Run 4 observed exactly one member and says so.
- **Most of this catalog does not answer.** Three of four ranked candidates in
  run 4 refused at the transport (upstream 429, 403 and 500). A declared
  replacement policy is load-bearing, not ceremony.

## ALLY_ADVICE live generation experiment (T-63)

A registered generator/reviewer experiment above the frozen B-016 layer: four synthetic scenarios, three reviewer red controls, two role-swapped replicates, one bounded live run. Its artifact and report follow the same immutability rules as the runs above; the interpretation lives in `lab/analysis/`.

- started: `2026-09-19T20:18:26Z`
- artifact: `ally_generation_live_20260919T201826Z_2a73d98de110453a.json`
- REGISTRATION_ID: `sha256:fc578a985cf81afa9f035bece368c78e668589ddfca0ac3529a353fc3b691ced`
- live calls: 25 (6 discovery, 19 experiment) of ceiling 30
- status: `COMPLETED`

## Real-project corpus pilot (B-018)

The first corpus built from real project artifacts. One immutable registration
was frozen before capture (eight exact artifacts, five explicit event
declarations, per-source and per-content SHA-256 pins) and the corpus was built
through the unchanged B-017 builder. The snapshot and report are written once
and never edited; there were no live model, network, mail or attention calls.

- registration: `lab/project_corpus_pilot_registration.json`
- REGISTRATION_ID: `sha256:dfd8b48dded34de8426181f309032da31c86e83f675412add15076fc421a096f`
- BUILD_ID: `sha256:0e05460aae1645b6bdfeec887f02a978a185026422faf74c90238f0938bd4e35`
- CORPUS_ID: `sha256:b009bdf3a8efd28f29be76d0dfd9c2809c0e7dd010af8e92c94a97fbeeec19ac`
- snapshot: `lab/out/project_corpus_pilot_20260919T213939Z.json`
- report: `lab/out/PROJECT_CORPUS_PILOT_REPORT_20260919T213939Z.md`
- earlier snapshots of the same build (same `BUILD_ID`/`CORPUS_ID`): `lab/out/project_corpus_pilot_20260919T212833Z.json`, `lab/out/project_corpus_pilot_20260919T213252Z.json`, `lab/out/project_corpus_pilot_20260919T213631Z.json`
- source-pin note: the registered journal `.saipen/LOG.md` grew after the freeze (SAIPEN keeps checkpointing); the newest snapshot records the single narrow recovery `APPEND_ONLY_SOURCE_MATCHES_REGISTERED_CONTENT_PINS`, and every registered record still matches its frozen content pin
- status: `BUILT` (completeness `NOT_PROVEN`)

## Real-project bounded generation pilot (B-019)

The registered two-role live generation/review pilot over the frozen B-018 BuiltProjectCorpus. Metadata-only artifacts: no prompt text, corpus content, candidate prose or reviewer rationale is persisted locally. Two role-swapped replicates, at most 12 live calls including discovery.

- started: `2026-09-19T22:06:41Z`
- artifact: `project_corpus_generation_live_20260919T220641Z.json`
- LIVE_REGISTRATION_ID: `sha256:5d750a8aaf166a02d7f1bc13c98f7bbde91728dd616083a0d2cde563e1f40b6e`
- live calls: 8 (discovery 6, generation 2, review 0) of ceiling 12
- status: `COMPLETED`
- privacy correction (T-70, 2026-09-20): the historical claim was too broad —
  the durable population section kept raw discovery/selection error text — and
  future artifacts now build from an explicit sanitized population projection.
  The historical artifact, report and interpretation above are unchanged; see
  [privacy correction](analysis/project_corpus_generation_20260919T220641Z_privacy_correction.md).

## Strict-schema reachability (T-71)

One registered experiment on the exact B-018 corpus and fixed T-69 requested
routes. LAB-only structural telemetry; unchanged prompts, strict parsers and
acceptance gates. Four calls of a six-call ceiling; no retry or repair.

- [Registration](project_corpus_reachability_registration.json)
- [Live metadata](out/project_corpus_reachability_live.json)
- [Report](out/PROJECT_CORPUS_REACHABILITY_REPORT.md)
- [Closure and interpretation](analysis/project_corpus_reachability_closure.md)
- R1: strict JSON refusal, 1525 bytes, finish reason `length`, no local cap applied.
- R2: valid `NO_ADVICE`. Semantic reviewer calls: 0; reachability not demonstrated.
- Dry control reached review offline; full suite 1677 passed, post-live focused 129 passed.
- SAIPEN: `CURRENT_FAIL / CARRIED_DEBT_UNCHANGED`; no new failure. STOP.

## Structured-output / completion-budget capability gate (T-73)

Six synthetic probes, no project content, two frozen routes and one immutable
registration: a 4096 completion budget, `json_object` and `json_schema` on both
routes. No retry, repair, replacement or fallback; no production change.

- [Registration](structured_output_capability_registration.json)
- [Live metadata](out/structured_output_capability_20260920T001732Z.json)
- [Report](out/STRUCTURED_OUTPUT_CAPABILITY_REPORT_20260920T001732Z.md)
- [Analysis](analysis/structured_output_capability_20260920T001732Z.md)
- All six probes `REQUEST_ACCEPTED_CONFORMING`; route A reported
  `deepseek/deepseek-v4-flash`, route B reported `MiniMaxAI/MiniMax-M3`;
  synthetic context sits at 0.95-0.98 of the T-71 gateway prompt tokens.
- One accepting sample is not enforcement: native enforcement, stable
  capability and a safe real 4096 run through the 4000-character local output
  path are all explicitly NOT claimed.
- SAIPEN: `CURRENT_FAIL / CARRIED_DEBT_UNCHANGED`; no new failure. STOP.

## Ephemeral full-output / 4096 completion budget (T-74)

One registered run over the unchanged B-018 corpus, with the generator budget
raised to 4096, reviewer budget held at 2048 and `response_format` absent.
The LAB-only ephemeral path supplies complete visible output to the parser;
the generic transport keeps its historical 4000-character projection.

- [Registration](project_corpus_budget4096_registration.json)
- live artifact: `lab/out/project_corpus_budget4096_live_20260920T005752Z.json`
- report: `lab/out/PROJECT_CORPUS_BUDGET4096_REPORT_20260920T005752Z.md`
- analysis: `lab/analysis/project_corpus_budget4096_20260920T005752Z.md`
- closure: `lab/analysis/project_corpus_budget4096_closure.md`
- R1: `4096 -> finish_reason=stop -> strict JSON CANDIDATE ->
  ALLY_GENERATED_REF_OUTSIDE_CORPUS -> reviewer 0`.
- R2: `NO_ADVICE -> reviewer 0`.
- Four calls out of six; no retry, repair, fallback, delivery or attention spend.
- Neither response exceeded the historical local cap. The full-output path
  was separately tested with longer deterministic responses.
- Semantic-review reachability remains unproven. The next experiment needs
  a new registration and a decision about the schema/reference failure.
- Historical validation: 1785 tests passed; the run's carried protocol debt
  is documented in its closure. Later repository repairs do not revise it.

## Registered JSON_SCHEMA reachability experiment (T-81 / FG-04B)

One newly registered bounded live experiment over the unchanged B-018 corpus
with exactly one intentional change from T-74: generator/probe
`response_format` `ABSENT -> JSON_SCHEMA` with schema policy `CORPUS_ENUM`
(`EVIDENCE_REFS` enumerated to the eight frozen corpus evidence refs). Reviewer
stays `response_format` absent at 2048; generator stays 4096; no retry, repair
or replacement; admission (`verify_current` + `admit_live`) proved before the
first network call.

- [Registration](project_corpus_jsonschema_registration.json)
- [Registered JSON Schema](project_corpus_jsonschema_schema.json)
- [LIVE_ELIGIBLE manifest](project_corpus_jsonschema_manifest.json)
- live artifact: `lab/out/project_corpus_jsonschema_live_20260920T155227Z.json`
- report: `lab/out/PROJECT_CORPUS_JSONSCHEMA_REPORT_20260920T155227Z.md`
- analysis: `lab/analysis/project_corpus_jsonschema_20260920T155227Z.md`
- closure: `lab/analysis/project_corpus_jsonschema_closure.md`
- R1: schema-valid candidate -> product reference gate PASS -> event floor MET
  (`CLEAN`, 7 known refs, 4 declared events) -> reviewer invoked once ->
  reviewer reply not one parseable JSON document (`ALLY_LAB_BAD_JSON`,
  3801 bytes) -> `REVIEWER_ERROR`, zero semantic verdicts.
- R2: `{"result":"NO_ADVICE"}` -> `NO_ADVICE`, reviewer 0.
- Probes: route B accepted the schema with a conforming sample; route A
  returned an empty completion at a 16-token capability probe
  (`finish_reason=length`), recorded separately and never promoted.
- Five calls of six; wrapper retries 0; no plaintext persisted; no mail,
  sealing, storage or attention operation.
- T-74's exact bad-reference cause is still not claimed. Semantic review is
  still not demonstrated, now because of the reviewer's own reply shape.
- A new reviewer-output-format hypothesis is recorded as future work; it would
  need a new registration and is not executed here.

## V2-02 selector-coverage experiment (T-88)

One preregistered offline experiment on frozen labelled fixtures, both
directions, testing exactly one receiver-owned `HeaderInterest.ignore_topics`
change (`{noise}` -> `{noise, ci-ok}`). Registration and manifest frozen before
measurement; immutable historical input copies under `lab/history/`.

- [Registration](selector_coverage_registration.json)
- [HISTORICAL_ONLY manifest](selector_coverage_manifest.json)
- [Fixtures](selector_coverage_fixtures.json)
- result: `lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/result.json`
- report: `lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/report.md`
- analysis: `lab/analysis/v202_selector_coverage_20260920T184536Z.md`
- closure: `lab/analysis/v202_selector_coverage_closure.md`
- Outcome: **`CANDIDATE_REJECTED_SAFETY`**. Aggregate fallback opens 246 -> 68
  (-178), but TOPIC_DRIFT loses 2 relevant `ci-ok` messages per direction
  (`TOPIC_DRIFT-018`, `TOPIC_DRIFT-019`); the modeled saving on that arm is
  declared inadmissible.
- Routine `ci-ok` suppression reduces opens, but a static topic ignore cannot be
  treated as relevance authority when semantic topic drift is possible.
- R1 unknown-atom/opaque-claim fallbacks are unchanged and separately reported
  (51 cases; 7 unknown-atom, 8 opaque-claim, 0 false ignores).
- Zero network/model/provider calls; no production promotion, no rebuild, no
  publication. Negative evidence closes V2-02.

## V2-03 reviewer structured-output experiment (T-96)

One registered bounded live experiment reusing the exact FG-04B pipeline with a
single intentional change: the reviewer response_format ABSENT -> JSON_SCHEMA.
The reviewer carried the registered reviewer json_schema (template sha256
8db0e5b00c8d817ce9130814ee5a952c6d1ead344539e7ce6aa4acdba6396bb9) and still did
not return one strict JSON document; the generator keeps its FG-04B schema.

- [registration](reviewer_structured_output_registration.json)
- [reviewer schema](reviewer_structured_output_schema.json)
- [LIVE_ELIGIBLE manifest](reviewer_structured_output_manifest.json)
- live artifact: `lab/out/reviewer_structured_output_live_20260920T221857Z.json`
- report: `lab/out/REVIEWER_STRUCTURED_OUTPUT_REPORT_20260920T221857Z.md`
- analysis: `lab/analysis/reviewer_structured_output_20260920T221857Z.md`
- closure: `lab/analysis/reviewer_structured_output_closure.md`
- Outcome: **`REVIEWER_BAD_JSON`** (R1) and `NO_ADVICE` (R2). The reviewer was
  reached with the registered JSON_SCHEMA request (`response_format_sha256`
  `91a32e66...`, request body 35907 bytes) and still returned a 4178-byte,
  non-strict-JSON reply (`ALLY_LAB_BAD_JSON`); zero semantic dimensions reached.
- 5/6 calls; retries 0; repairs 0; replacements 0; fallbacks 0; admission
  CURRENT_MATCH proved before the first network call.
- REQUEST SENT WITH SCHEMA != PROVIDER ENFORCED SCHEMA; provider enforcement
  remains NOT_PROVEN.
- One sample proves reachability questions only, not reviewer reliability.
  Negative evidence closes V2-03.
