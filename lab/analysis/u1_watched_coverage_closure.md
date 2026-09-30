# U1 / T-94 closure — drift-safe watched coverage

Status: **DONE** as evidence. Terminal outcome:
**`COVERAGE_GAIN_WITH_EXTRA_OPENS`**. No production promotion, no publish, no
threshold, fixture, truth or watched-target change after the result.

## What closed

U1 tested exactly one receiver-owned R1 selector variable, `Interest.watched`,
in both A-to-B and B-to-A directions against frozen, independently labelled
fixtures: baseline watches nothing, treatment watches exactly one canonical
target. Holding the pre-existing `R0-WATCHED` rule (first in
`saimail/selector.py`) unchanged, the gate measured whether receiver-owned
watching rescues relevant messages under vocabulary/topic drift, and what
sender-caused attention inflation it costs.

The result is a bounded tradeoff, not a failure: watched relations raise
attention safely (zero downward changes, zero false ignores, zero missed
relevant, zero required-open downgrades) and rescue relevant drifted messages,
but a sender who asserts relations to a watched target can also force extra
opens on irrelevant and declared-noise messages.

## Preregistration (frozen before measurement)

- `lab/watched_coverage_registration.json`
  (`WATCHED_RELATION_COVERAGE_REGISTRATION_1` v1) pins the single treatment
  variable (`Interest.watched`), the watched and other canonical target
  identities, baseline/treatment `Interest`, fixture SHA-256, both directions,
  the seven frozen workloads, the truth authority, the four terminal outcomes,
  the four zero-tolerance safety invariants, the zero network/model/provider
  call budget, `production_promotion = NONE`, the post-result-adjustment
  prohibition and the `WATCHED_COVERAGE_RESULT_1` result schema.
- `lab/watched_coverage_manifest.json` (`EXPERIMENT-MANIFEST-1`) separates the
  three authorities: `verify_historical` (archived byte-identical copies),
  `verify_current` (live checkout + frozen implementation bindings) and
  `admit_live` (refused — `HISTORICAL_ONLY`, zero network, no live permission
  granted).
- Immutable public historical input copies live under
  `lab/history/u1-watched-coverage/`.

## Harness integrity (tested before the measured run)

`tests/test_watched_coverage.py` (27 tests) proves: preregistration identity;
preflight refusal on current input drift, current implementation drift and
historical fixture mismatch; a new/empty output directory; both directions
execute for every workload; baseline and treatment receive byte-identical
records and frames; relevance truth is not visible to the selector; exactly one
receiver variable changes; the watched target is receiver-owned and a sender
relation to another target does not trigger; a watched relation to the declared
target does trigger; treatment can only preserve or raise depth; no ignore
authority is created; `R0-WATCHED` beats `R4-NOISE`; the mandatory `OPEN_R2`/
`OPEN_R3` floor is not downgraded; unknown/opaque fallback is unchanged;
relation-spam and noise-overlap cost are counted; zero network/model/provider
calls; a bounded deterministic schema; and rerun determinism from the same
frozen inputs.

One lint-only pre-freeze fix was applied to `lab/watched_coverage.py` (an unused
import removed; no behaviour change) and the manifest implementation pin was
refreshed before the frozen run. The current checkout passes
`verify_current = CURRENT_MATCH` and `verify_historical = HISTORICAL_VERIFIED`.

## Result

`lab/out/U1_WATCHED_COVERAGE_20260920T211411Z/` — `result.json` (SHA-256
`a1c3699d619f412cf21c57c60a52d7459b3ed525f5adaac7f27095c3cceb2434`) and
`report.md` (SHA-256
`e05cd9fd0bf3f9d2072d3bb039f5d8151596342642a872ca51f40f5decd87cc7`).

Aggregate across both directions:

| metric | value |
|---|---:|
| relevant_attention_upgrades | 18 |
| irrelevant_attention_upgrades | 24 |
| total_attention_upgrades | 42 |
| relevant_drift_rescued | 14 |
| relevant_drift_not_rescued | 6 |
| unnecessary_extra_opens | 0 |
| relation_spam_extra_opens | 14 |
| noise_overlap_extra_opens | 10 |
| downward_attention_changes | 0 |
| new_false_ignores | 0 |
| new_missed_relevant | 0 |
| baseline_required_open_downgrades | 0 |
| baseline_total_open | 34 |
| treatment_total_open | 72 |

Per workload (both directions identical):

- `DRIFT_RESCUE` — 7 relevant upgrades per direction, all rescued by
  `R0-WATCHED`; 0 irrelevant upgrades; 0 downgrades.
- `OTHER_TARGET` — 0 treatment changes (relation to an unwatched target does not
  trigger).
- `NO_RELATION_RELEVANT` — 3 relevant messages per direction notch unchanged
  (DEFER); no magical rescue; this proves U1's bounded scope.
- `RELATION_SPAM` — 7 irrelevant upgrades per direction; sender-controlled
  attention inflation, reported equally prominently.
- `NOISE_OVERLAP` — 5 declared-noise messages per direction raised from IGNORE
  to OPEN_R3 by the pre-existing `R0-WATCHED`-before-`R4-NOISE` ordering.
- `MANDATORY_OPEN_CONTROL` — 11 of 12 rows baseline `OPEN_R2`/`OPEN_R3`; none
  downgraded; 2 rows raised further (R2-UNKNOWN floor → R0-WATCHED OPEN_R3).
- `UNKNOWN_OPAQUE_CONTROL` — 6 rows unchanged at `OPEN_R2`
  (`R2-UNKNOWN`/`R3-OPEN-RECORD`).

R1 stress control (unchanged `bench/selector_corpus.py`, existing selector): 51
cases, 4 watched-relation cases, 7 unknown-atom fallbacks, 8 opaque-claim
fallbacks, 0 false ignores, `changed_by_treatment = false`.

## Interpretation carried forward

A receiver-owned watched set can use sender-asserted relations as a conservative
**attention-escalation hint**. A relation to a watched target does **not** prove
relevance: the sender controls the assertion. U1 therefore can support **OPEN
MORE**, never **IGNORE MORE**. The safe frontier of the selector lane is
conservative escalation, not suppression — consistent with, and bounded by, the
V2-02 `CANDIDATE_REJECTED_SAFETY` negative.

U1's numbers are R1 attention coverage after a TriageView exists. They must not
be compared directly to the V2-02 transport/header fallback-open savings.

## Verification

- focused U1 harness: 27 passed;
- selector corpus and V2-02 selector-coverage suites: passed;
- experiment-manifest/reproducibility, FG-05 local-scenario, FG-06 utility,
  P1 inbox-query, repository-consistency, release-decision and a2
  release-candidate suites: passed;
- full canonical suite: **2264 passed, 0 failed, 0 errors, 0 skipped**
  (`V:\_TEMP_\opencode\T-94-full-suite.xml`). The pre-T-94 baseline was 2237;
  the +27 delta is exactly the new `tests/test_watched_coverage.py`. No test was
  weakened;
- lint: `python -m ruff check --select E4,E7,E9,F` on the touched Python files —
  clean;
- SAIPEN canonical validation: inherited baseline only, no new U1-attributable
  failure.

## Boundaries

No production `saimail/*` semantic change, no wire-format change, no new ignore
authority, no rebuild of the frozen `0.0.2a2` candidate, no support-scope
expansion, no model/provider/network call, no commit, tag, push or publication.
The U1 harness is LAB-only. `POST_A2_PRODUCT_DELTA = P1`;
`POST_A2_RESEARCH_EVIDENCE = U1`.
