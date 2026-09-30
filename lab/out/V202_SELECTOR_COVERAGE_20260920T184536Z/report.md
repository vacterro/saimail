# V2-02 selector coverage experiment

Experiment: PASS; candidate: CANDIDATE_REJECTED_SAFETY.

| Workload / direction | Opens before / after | Fallback before / after | New false ignores | Required-open downgrades |
|---|---:|---:|---:|---:|
| ROUTINE / A_TO_B | 40 / 4 | 38 / 2 | 0 | 0 |
| ROUTINE / B_TO_A | 40 / 4 | 38 / 2 | 0 | 0 |
| MIXED_NOVEL / A_TO_B | 36 / 16 | 28 / 8 | 0 | 0 |
| MIXED_NOVEL / B_TO_A | 36 / 16 | 28 / 8 | 0 | 0 |
| MANDATORY_OVERLAP / A_TO_B | 40 / 28 | 24 / 12 | 0 | 0 |
| MANDATORY_OVERLAP / B_TO_A | 40 / 28 | 24 / 12 | 0 | 0 |
| TOPIC_DRIFT / A_TO_B | 40 / 20 | 32 / 12 | 2 | 0 |
| TOPIC_DRIFT / B_TO_A | 40 / 20 | 32 / 12 | 2 | 0 |
| LOW_VOLUME / A_TO_B | 2 / 1 | 1 / 0 | 0 | 0 |
| LOW_VOLUME / B_TO_A | 2 / 1 | 1 / 0 | 0 | 0 |

False ignores and unnecessary opens are separate harms. Cost savings on an unsafe arm are not a utility win.
Both arms receive identical sealed bytes. Both directions are reported separately.
R1 unknown-atom/opaque-claim fallbacks are unchanged; this is a transport-header experiment.
Two receiver setup edits and ongoing topic maintenance are outside the frozen friction scalar; maintenance, latency and subjective pleasantness are NOT_MEASURED.
No production promotion, model/provider/network call, frozen-candidate rebuild or publication.
