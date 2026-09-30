# U1 watched-coverage experiment

Experiment: PASS; outcome: **COVERAGE_GAIN_WITH_EXTRA_OPENS**.

Treatment variable: `Interest.watched` (raise-only). The sender-asserted relation is an attention hint, never relevance truth.

| Workload / direction | Relevant upgrades | Irrelevant upgrades | Rescued | Not rescued | Spam opens | Noise opens | Downgrades |
|---|---:|---:|---:|---:|---:|---:|---:|
| DRIFT_RESCUE / A_TO_B | 7 | 0 | 7 | 0 | 0 | 0 | 0 |
| DRIFT_RESCUE / B_TO_A | 7 | 0 | 7 | 0 | 0 | 0 | 0 |
| OTHER_TARGET / A_TO_B | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| OTHER_TARGET / B_TO_A | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| NO_RELATION_RELEVANT / A_TO_B | 0 | 0 | 0 | 3 | 0 | 0 | 0 |
| NO_RELATION_RELEVANT / B_TO_A | 0 | 0 | 0 | 3 | 0 | 0 | 0 |
| RELATION_SPAM / A_TO_B | 0 | 7 | 0 | 0 | 7 | 0 | 0 |
| RELATION_SPAM / B_TO_A | 0 | 7 | 0 | 0 | 7 | 0 | 0 |
| NOISE_OVERLAP / A_TO_B | 0 | 5 | 0 | 0 | 0 | 5 | 0 |
| NOISE_OVERLAP / B_TO_A | 0 | 5 | 0 | 0 | 0 | 5 | 0 |
| MANDATORY_OPEN_CONTROL / A_TO_B | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| MANDATORY_OPEN_CONTROL / B_TO_A | 2 | 0 | 0 | 0 | 0 | 0 | 0 |
| UNKNOWN_OPAQUE_CONTROL / A_TO_B | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| UNKNOWN_OPAQUE_CONTROL / B_TO_A | 0 | 0 | 0 | 0 | 0 | 0 | 0 |

## Aggregate (both directions)

- relevant_attention_upgrades: 18
- irrelevant_attention_upgrades: 24
- total_attention_upgrades: 42
- relevant_drift_rescued: 14
- relevant_drift_not_rescued: 6
- unnecessary_extra_opens: 0
- relation_spam_extra_opens: 14
- noise_overlap_extra_opens: 10
- downward_attention_changes: 0
- new_false_ignores: 0
- new_missed_relevant: 0
- baseline_required_open_downgrades: 0

False opens are measurable cost; false ignores are information loss. They are reported separately and never exchanged for each other.
R0-WATCHED is the pre-existing production rule; U1 did not modify the selector, and no ignore authority was created by this experiment.
This is an R1 attention-coverage measurement after a TriageView exists. It must not be compared to the V2-02 transport/header fallback-open savings.
No production default change, no model/provider/network call, no frozen-candidate rebuild and no publication.
