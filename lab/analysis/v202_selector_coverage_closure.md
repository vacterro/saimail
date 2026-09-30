# V2-02 / T-88 closure — selector-coverage experiment

Status: **DONE** as evidence. Terminal outcome:
**`CANDIDATE_REJECTED_SAFETY`**. No production promotion, no publish, no
threshold or fixture change after the result.

## What closed

V2-02 (Roadmap v2, utility/coverage lane) tested exactly one receiver-owned
transport/header-policy variable — `HeaderInterest.ignore_topics` extended from
`{noise}` to `{noise, ci-ok}` — against frozen, independently labelled fixtures
in both A-to-B and B-to-A directions. The gate closes on a measured negative:
routine `ci-ok` suppression cuts fallback opens, but the topic-drift workload
loses two relevant messages per direction, so the mechanism is rejected for
safety.

The result is not a failure of the gate. V2-02 asked whether one concrete
mechanism lowers fallback opens without any new false ignore, missed relevant
message or required-open downgrade; the answer is no, and that is the evidence.

## Preregistration (frozen before measurement)

- `lab/selector_coverage_registration.json` (`SELECTOR_COVERAGE_REGISTRATION_1`
  v1) pins the single treatment variable, baseline/treatment policies, fixture
  SHA-256, both directions, the five frozen workloads, success and rejection
  criteria, the unchanged FG-06 friction identity and weights, the zero
  network/model/provider call budget, `production_promotion = NONE`, the
  post-result-adjustment prohibition, and the `SELECTOR_COVERAGE_RESULT_1`
  result schema.
- `lab/selector_coverage_manifest.json` (`EXPERIMENT-MANIFEST-1`) separates the
  three authorities: `verify_historical` (archived byte-identical copies),
  `verify_current` (live checkout) and `admit_live` (refused —
  `HISTORICAL_ONLY`, zero network, no live permission granted).
- Immutable public historical input copies live under
  `lab/history/v202-selector-coverage/`.

## Harness integrity (tested before the measured run)

`tests/test_selector_coverage.py` proves: preregistration identity; preflight
refusal on current input drift, current implementation drift and historical
fixture mismatch; a new/empty output directory; both directions execute;
baseline and treatment receive byte-identical sealed inputs; relevance truth is
not visible to the header policy; overlapping OPEN beats IGNORE; the
`OPEN_R2`/`OPEN_R3` machine floor cannot be downgraded; false ignores and
unnecessary opens are counted independently; missed relevant messages are named
by message ID; friction savings are inadmissible on an unsafe arm; zero
network/model/provider calls; a bounded deterministic schema; and rerun
determinism from the same frozen inputs.

A pre-measurement defect was fixed and re-frozen before the run: the paired arm
expected delivery status `"DELIVERED"` while the Post Office returns `ACCEPTED`
(`lab/selector_coverage.py`). The registration was untouched by that fix; the
manifest implementation pin was refreshed before the frozen run.

## Result

`lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/` — `result.json` and
`report.md`.
Interpretation: `lab/analysis/v202_selector_coverage_20260920T184536Z.md`.

- aggregate fallback opens: 246 -> 68 (-178 across both directions);
- safe workloads (ROUTINE, MIXED_NOVEL, MANDATORY_OVERLAP, LOW_VOLUME): zero
  new false ignores, zero missed relevant, zero required-open downgrades, all in
  both directions;
- TOPIC_DRIFT: 2 new false ignores and 2 missed relevant per direction
  (`TOPIC_DRIFT-018`, `TOPIC_DRIFT-019`), modeled friction delta -760.0334 per
  direction but declared inadmissible;
- R1 control: 51 cases, 7 unknown-atom + 8 opaque-claim fallbacks, 0 false
  ignores, `changed_by_treatment = false`;
- zero network/model/provider calls; latency and subjective pleasantness
  `NOT_MEASURED`.

## Conclusion carried forward

Receiver-owned static topic ignore can reduce transport/header-policy fallback
and open friction, but it cannot safely treat a topic label as relevance
authority when semantic topic drift is possible. A candidate rejected here is
not repaired inside the same registered experiment and no alternative selector
rule is silently substituted.

## Verification

- focused V2-02 harness: 22 passed;
- selector corpus `tests/test_selector.py` and `tests/test_local_scenario.py`:
  passed;
- FG-06 utility, experiment-manifest/reproducibility and repository-consistency
  suites: passed;
- full canonical suite: **2146 passed, 0 failed, 0 errors, 0 skipped**
  (`lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/full-suite.xml`). The
  pre-T-88 baseline was 2123; the +23 delta is the 22 new V2-02 harness tests
  plus one new repository-consistency test. No test was weakened;
- lint: `python -m ruff check --select E4,E7,E9,F` on the touched files — all
  checks passed. A broader non-project rule set reports only pre-existing
  import-order/`with`-style findings on the manifest-bound frozen harness
  (`lab/selector_coverage.py`, `tools/selector_coverage_experiment.py`); those
  bytes are deliberately NOT edited after the measured run, because editing a
  manifest-pinned implementation would invalidate the frozen experiment;
- SAIPEN canonical validation: `CURRENT_FAIL`, **3 FAIL / 21 WARN** — exactly
  the inherited baseline (SRC-017/T-41 linkage, SRC-036 credential-source,
  stale improve-report fingerprint, plus inherited producer/cross-doc
  warnings). No new failure is attributable to T-88 / V2-02.

## Boundaries

No production `saimail/*` semantic change, no wire-format change, no rebuild of
the frozen `0.0.2a1` candidate, no support-scope expansion, no model/provider/
network call, no commit, tag, push or publication. The V2-02 harness is LAB-only.
