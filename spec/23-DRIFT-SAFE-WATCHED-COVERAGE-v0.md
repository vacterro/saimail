# U1 — Drift-safe watched coverage without new ignore authority (v0)

This is a bounded, preregistered research gate. It tests whether one
receiver-owned watched canonical target can recover relevant messages whose
vocabulary or topic has drifted, **without** introducing any downward attention
change or any new ignore authority. It is a direct, deliberate counterpart to
V2-02.

V2-02 measured the dangerous direction: lowering attention from a
sender-controllable label. It tested one receiver-owned static topic ignore and
the result was `CANDIDATE_REJECTED_SAFETY` — fallback opens fell (`246 -> 68`)
but the topic-drift workload lost two relevant `ci-ok` messages per direction.
That result is immutable and is not retuned here.

U1 tests the opposite asymmetry:

```
the receiver owns what it watches;
the sender may point at it;
that pointer may raise attention;
it must never lower attention.
```

## Scope — the exact layer U1 measures

U1 operates at the **R1 selector layer**, over a decoded
`sailang.frame.TriageView` and a declared `saimail.selector.Interest`.

U1 does **not** test, measure or reduce:

- Post Office header `DEFER` fallback;
- transport/header scan opens;
- the V2-02 fallback-open count;
- the unknown wire-token fallback;
- the opaque-claim fallback.

U1 measures **attention coverage after an R1 TriageView exists**. Its numbers
must never be compared directly to V2-02 fallback-open savings: V2-02 measured
transport/header-policy suppression, U1 measures R1 attention escalation.

## One variable

Exactly one receiver variable changes: `Interest.watched`.

```
BASELINE   watched = {}
TREATMENT  watched = {WATCHED_TARGET}
```

Every other `Interest` field (`atoms`, `subjects`, `noise`) is byte/semantically
identical between the two arms. Every record and every frame is byte-identical
between the two arms; the only changed receiver input is the watched set. There
is no treatment-specific payload, relation, or truth label.

A **watched relation** is a canonical relation target appearing in the existing
R1 `relation_targets` projection. The sender may assert the relation; the
receiver alone declares whether the target is watched. Watching does not
validate the sender's assertion. It only raises receiver attention.

The mechanism is **raise-only by construction**: `R0-WATCHED` is the first rule
in `saimail/selector.py`, executes before `R4-NOISE`, and returns `OPEN_R3`
(depth 3). It never creates `IGNORE`.

## Frozen fixtures and independent truth

`lab/watched_coverage_fixtures.json` declares seven workloads before any run.
Truth (the fixture row's `relevant` flag) is declared independently of the
selector and is never visible to the selector; the sender-asserted relation is
an attention hint, never relevance truth.

- `DRIFT_RESCUE` — relevant messages whose vocabulary/subjects are outside the
  receiver's ordinary interest but carry `SUPPORTS`/`REFUTES`/`CON` pointing at
  `WATCHED_TARGET`. Baseline `DEFER`; treatment `OPEN_R3` via `R0-WATCHED`.
- `OTHER_TARGET` — the same structural relation shape pointing at another valid
  canonical target the receiver does not watch. No treatment change.
- `NO_RELATION_RELEVANT` — relevant drifted messages with no relation to
  `WATCHED_TARGET`. No magical rescue; this proves U1's bounded scope.
- `RELATION_SPAM` — independently labelled irrelevant messages assert
  `SUPPORTS`/`REFUTES`/`CON` against `WATCHED_TARGET`. This mandatory workload
  measures the cost of sender-controlled attention inflation.
- `NOISE_OVERLAP` — messages otherwise matching receiver-declared noise also
  relate to `WATCHED_TARGET`. The existing `R0-WATCHED`-before-`R4-NOISE`
  ordering is measured honestly and the resulting extra opens are reported.
- `MANDATORY_OPEN_CONTROL` — messages already requiring `OPEN_R2`/`OPEN_R3`
  through existing higher-information rules. Treatment must never reduce depth.
- `UNKNOWN_OPAQUE_CONTROL` — preserves the existing conservative fallback; the
  watched treatment must not weaken it.

Both logical directions (`A_TO_B`, `B_TO_A`) run for every workload.

## Pre-registration and integrity

`lab/watched_coverage_registration.json`
(`WATCHED_RELATION_COVERAGE_REGISTRATION_1` v1) pins the experiment id, the
single treatment variable, `WATCHED_TARGET` identity, baseline/treatment
`Interest`, fixture path and SHA-256, workload ids, both directions, the
selector and frame/projection implementation identity, the truth authority, the
success criteria, the safety invariants, the terminal outcomes, the zero-call
budget, `production_promotion = NONE`, the post-result-adjustment prohibition,
the result schema and the new-and-empty output-directory rule.

`lab/watched_coverage_manifest.json` uses EXPERIMENT-MANIFEST-1 and separates the
three authorities (`verify_historical`, `verify_current`, `admit_live`), pinning
the fixture, registration, harness, entrypoint, `saimail/selector.py` and the
relevant `sailang` frame/record/dictionary code. Public input copies under
`lab/history/u1-watched-coverage/` allow historical input verification
independently of a later checkout. No live permission is granted. The measured
experiment refuses to run if any pinned input or implementation byte drifts.

## Safety invariants

For every message:

```
depth(treatment_verdict) >= depth(baseline_verdict)
DOWNWARD_ATTENTION_CHANGES            = 0
NEW_FALSE_IGNORES                     = 0
NEW_MISSED_RELEVANT                   = 0
BASELINE_REQUIRED_OPEN_DOWNGRADES     = 0
```

Any violation is terminal `SAFETY_INVARIANT_VIOLATION`; no cost/coverage
improvement can override it.

## Measurements and terminal outcomes

Reported separately, never collapsed into one scalar:

`relevant_attention_upgrades`, `irrelevant_attention_upgrades`,
`total_attention_upgrades`, `relevant_drift_rescued`, `relevant_drift_not_rescued`,
`unnecessary_extra_opens`, `relation_spam_extra_opens`,
`noise_overlap_extra_opens`, `downward_attention_changes`, `new_false_ignores`,
`new_missed_relevant`, `baseline_required_open_downgrades`.

An extra open is never declared equivalent to a missed relevant message, and the
FG-06 friction weights are not retuned. If the FG-06 friction model is shown it
is secondary modeled context only; U1's primary evidence is coverage versus
attention inflation.

Terminal outcomes (closed set, fixed before measurement):

- `COVERAGE_GAIN_NO_EXTRA_OPENS` — relevant drift coverage improves and
  irrelevant attention does not increase;
- `COVERAGE_GAIN_WITH_EXTRA_OPENS` — relevant drift coverage improves safely but
  some irrelevant messages are also raised; a bounded tradeoff finding, **not** a
  failure;
- `NO_COVERAGE_GAIN` — no relevant attention gain;
- `SAFETY_INVARIANT_VIOLATION` — any downward change, new false ignore, new
  missed relevant message, or required-open downgrade.

The `bench/selector_corpus.py` R1 stress corpus is a **secondary control** only:
its declared truth is not rewritten and its verdict fingerprint is reported
separately. U1 does not reduce the transport/header fallback measured by V2-02.

## Interpretation boundary

A sender relation is an attention hint, not relevance truth. Therefore U1 can
support **OPEN MORE** but never **IGNORE MORE**. The correct reading of a
supported result is: a receiver-owned watched set can use sender-asserted
relations as a conservative attention-escalation hint. The incorrect reading is:
a relation to a watched target proves relevance.

## No automatic production change

The `R0-WATCHED` mechanism already exists in the production selector and is used
unchanged. U1 does not populate watched targets automatically, infer them from
traffic, persist learned watched targets, create sender-owned watch lists, alter
rule ordering, add ignore rules, change `PostOffice.HeaderInterest`, or change
the P1 inbox query. If the evidence supports the existing mechanism, only
documentation/roadmap truth is updated.

## Boundaries

No production wire or semantic change, no new ignore authority, no frozen
candidate rebuild, no version bump, no support-scope expansion, no
model/provider/network call, no commit, tag, push or publication. The U1 harness
is LAB-only. U1 is post-`0.0.2a2` research evidence:
`POST_A2_PRODUCT_DELTA = P1`, `POST_A2_RESEARCH_EVIDENCE = U1`.
