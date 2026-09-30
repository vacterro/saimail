# V2-02 selector-coverage experiment — interpretation

Run: `lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/result.json`
(`SELECTOR_COVERAGE_RESULT_1` v1, status PASS).
Outcome: **`CANDIDATE_REJECTED_SAFETY`**.

This is a successful research result. The preregistered experiment completed on
frozen inputs, and it rejected the candidate for a safety failure. No production
policy changed, no friction threshold moved, and no metric was exchanged for a
lower scalar cost.

## What was tested

One receiver-owned transport/header-policy variable, `HeaderInterest.ignore_topics`:

- baseline: `ignore_topics = {noise}`
- treatment: `ignore_topics = {noise, ci-ok}`

Both arms open `DEFER` messages (the frozen FG-06 fallback-heavy choice) and both
receivers make the same declaration. `OPEN_R3` topics `{action}` and kinds
`{WARNING}` are identical across arms. The R1 unknown-atom and opaque-claim
fallbacks are a **different stage** and are measured separately, unchanged.

## Result

| Workload / direction | Fallback opens before / after | False ignores | Missed relevant | Required-open downgrades | Safe |
|---|---:|---:|---:|---:|---|
| ROUTINE / A_TO_B | 38 / 2 | 0 | 0 | 0 | yes |
| ROUTINE / B_TO_A | 38 / 2 | 0 | 0 | 0 | yes |
| MIXED_NOVEL / A_TO_B | 28 / 8 | 0 | 0 | 0 | yes |
| MIXED_NOVEL / B_TO_A | 28 / 8 | 0 | 0 | 0 | yes |
| MANDATORY_OVERLAP / A_TO_B | 24 / 12 | 0 | 0 | 0 | yes |
| MANDATORY_OVERLAP / B_TO_A | 24 / 12 | 0 | 0 | 0 | yes |
| TOPIC_DRIFT / A_TO_B | 32 / 12 | 2 | 2 | 0 | **no** |
| TOPIC_DRIFT / B_TO_A | 32 / 12 | 2 | 2 | 0 | **no** |
| LOW_VOLUME / A_TO_B | 1 / 0 | 0 | 0 | 0 | yes |
| LOW_VOLUME / B_TO_A | 1 / 0 | 0 | 0 | 0 | yes |

Aggregate fallback opens fall (246 -> 68; -178 across both directions), and the
routine `ci-ok` traffic becomes dramatically cheaper. But the `TOPIC_DRIFT`
workload loses the same **two relevant messages per direction**
(`TOPIC_DRIFT-018`, `TOPIC_DRIFT-019`): payloads whose topic looks routine
(`ci-ok`) while the message itself carries an actionable finding. In a header-only
policy the label is not relevance truth, so a static ignore rule converts a
semantic surprise into a lost message.

## Verdict

The candidate is **rejected for safety**, not for lack of savings:

```
CANDIDATE_REJECTED_SAFETY
```

Every safe workload reduces fallback opens, so the mechanism is real. The
`TOPIC_DRIFT` false ignore — identical in both directions — is the failure
boundary. The stronger, general conclusion is:

> Receiver-owned static topic ignore can reduce transport/header-policy fallback
> and open friction, but it cannot safely treat a topic label as relevance
> authority when semantic topic drift is possible.

Because a safety failure overrides friction savings, the modeled cost delta
below is reported and **declared inadmissible** for the treatment as a whole.

## Utility interpretation (modeled, not truth)

Friction uses the unchanged FG-06 `TOTAL_FRICTION_FRICTION_UNITS_v1` weights
(`lab/utility_friction.py`, identity `TOTAL_FRICTION_FRICTION_UNITS_v1`). Token
ratios are the integrated T-9B values; token cost was not remeasured. The
comparison is a declared model.

Per-direction modeled friction delta (treatment minus baseline):

| Workload | Delta | Admissible? |
|---|---:|---|
| ROUTINE | -288.0601 | yes |
| MIXED_NOVEL | -160.0334 | yes |
| MANDATORY_OVERLAP | -96.02 | yes |
| TOPIC_DRIFT | -760.0334 | **no — safety failure** |
| LOW_VOLUME | -8.0017 | yes |

Kept separately visible and never summed into one score: fallback opens,
unnecessary opens, false ignores, missed relevant messages, required-open
downgrades, sender work, receiver work, setup burden, maintenance burden.

- Sender work: `sender_seals` per arm; `sender_extra_treatment_work = 0`.
- Receiver setup: two policy edits (one per participant), one new topic entry
  per receiver; the setup cost is **outside** the frozen friction scalar
  (`setup_cost_not_in_frozen_friction_model = true`).
- Future topic maintenance cost: `NOT_MEASURED`.
- Latency: `NOT_MEASURED`. Subjective pleasantness: `NOT_MEASURED`.
- Missed baseline machine-required opens: `0` in every workload and direction
  (D-036 floor and D-037 merge untouched).

## Controls and boundaries

- **R1 control:** the unchanged current R1 stress corpus was measured with the
  existing selector — 51 cases, 7 unknown-atom fallbacks, 8 opaque-claim
  fallbacks, 0 false ignores, `changed_by_treatment = false`. No reduction of
  unknown wire atoms is claimed.
- **Paired transport:** both arms received byte-identical sealed envelopes and
  canonical records in separate temporary stores; truth is used only by the
  grader.
- **Zero calls:** network attempts 0, model calls 0, provider calls 0.
- **No promotion:** `production_promotion = NONE`, `publication = NONE`; the
  frozen `0.0.2a1` candidate and its external proof are untouched.

## Immutable pins

- result: `lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/result.json` —
  `65e71e259f06160065af4ad801f9f1476d6e7fe2c42293be9564b08c875afdf1`
- report: `lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/report.md` —
  `d5d2e23dbca6e758c2df3ee16f47b1bc145201005976aadf8337f41c390b2fd1`
- fixtures `lab/selector_coverage_fixtures.json` —
  `a8fa4095ea4bbd1361a40c4c0d6be8968584e562a3cde3f47183a3cfccf9631e`
- registration `lab/selector_coverage_registration.json` —
  `9be09310122a3638155745b3955f769a8aad20a618a8c795a37eb78b1f6324fa`
