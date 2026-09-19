# T-9 — SAILANG proof-of-value benchmark

**Verdict: CONDITIONAL**

Pre-registered classification rule, declared in `bench/cost_compare.py` before
any measurement and printed here unchanged:

> GO: zero semantic inversions AND deterministic projection AND median(line tokens / prose tokens) < 0.60 on every tokenizer. CONDITIONAL: zero inversions and that median in [0.60, 0.95). NO_GO: any semantic inversion, or non-determinism, or that median >= 0.95 on any tokenizer.

Corpus: 45 fixtures across 15 information classes.
Missing required classes: none.

## Tokenizer caveat

Every token count below is evidence **for the tokenizer that produced it**.
None of these are Claude, Sol, GLM, Qwen or DeepSeek tokenizers; those families
segment text differently and could move these ratios in either direction.
Measured here:

- `cl100k_base` (openai-gpt35-gpt4)
- `o200k_base` (openai-gpt4o)
- `p50k_base` (openai-codex-davinci)
- `gpt2` (gpt2-legacy)

## Token cost

| tokenizer | line/prose median | mean | p90 | best | worst | record/prose median |
|---|---|---|---|---|---|---|
| cl100k_base | 0.703 | 0.774 | 1.000 | 0.328 | 1.778 | 4.500 |
| o200k_base | 0.727 | 0.795 | 1.053 | 0.449 | 1.778 | 4.724 |
| p50k_base | 0.784 | 0.822 | 1.150 | 0.152 | 1.867 | 4.800 |
| gpt2 | 0.784 | 0.822 | 1.150 | 0.152 | 1.867 | 4.800 |

Bytes, median: line/prose 0.286, record/prose 2.095.

## Negative findings

- `cl100k_base`: line is not cheaper than prose in 7 case(s): dictterms-3, unknown-1, unknown-2, unknown-3, value-2, value-3, warning-3.
- `cl100k_base`: the canonical record costs at least as much as prose in 45 of 45 cases.
- `o200k_base`: line is not cheaper than prose in 6 case(s): dictterms-3, unknown-1, unknown-2, unknown-3, value-2, value-3.
- `o200k_base`: the canonical record costs at least as much as prose in 45 of 45 cases.
- `p50k_base`: line is not cheaper than prose in 8 case(s): dictterms-3, human-memory-3, unknown-1, unknown-2, unknown-3, value-2, value-3, warning-3.
- `p50k_base`: the canonical record costs at least as much as prose in 45 of 45 cases.
- `gpt2`: line is not cheaper than prose in 8 case(s): dictterms-3, human-memory-3, unknown-1, unknown-2, unknown-3, value-2, value-3, warning-3.
- `gpt2`: the canonical record costs at least as much as prose in 45 of 45 cases.

- The line deliberately drops the claim in 10 of 45 cases (OPEN RECORD): goal-1, goal-2, goal-3, value-1, value-2, warning-1, warning-2, unicode-1, unicode-2, unicode-3.
- Semantic inversions: 0.
- Non-deterministic cases: none.

## Dictionary overhead

- 30 terms, 1038 bytes on disk (paid once, not per line).
- Per-line version marker: 5 bytes, paid on every line.
- Bytes saved by substitution across the corpus: 360 (median 4 per line).

## Per-case detail

| case | class | prose B | record B | line B | triage kept | line |
|---|---|---|---|---|---|---|
| verified-test-1 | verified_test_result | 147 | 290 | 41 | 9/9 | `L1D0|O|queue|U4|EV+|TSUITE=574_574_PASS|-` |
| verified-test-2 | verified_test_result | 113 | 294 | 42 | 9/9 | `L1D0|O|recovery|U4|EV+|TSUITE=88_88_PASS|-` |
| verified-test-3 | verified_test_result | 140 | 297 | 35 | 9/9 | `L1D0|O|validate|U4|EV+|VALID=PASS|-` |
| human-memory-1 | contradicted_human_memory | 143 | 215 | 44 | 9/9 | `L1D0|F|opencode.db|U1|EV0|DB_HISTORY>=2025|-` |
| human-memory-2 | contradicted_human_memory | 171 | 422 | 49 | 9/9 | `L1D0|O|opencode.db|U4|EV+|DB_CREATED=2026-08-23|R` |
| human-memory-3 | contradicted_human_memory | 124 | 296 | 39 | 9/9 | `L1D0|F|retry.cfg|U1|EV0|CFG=UNCHANGED|C` |
| overclaim-1 | agent_overclaim | 182 | 222 | 52 | 9/9 | `L1D0|F|retry|U1|EV0|RCAUSE=CLAIMED_ON_PARTIAL_TEST|-` |
| overclaim-2 | agent_overclaim | 137 | 282 | 30 | 9/9 | `L1D0|O|b03|U2|EV+|CONF>PTEST|-` |
| overclaim-3 | agent_overclaim | 129 | 273 | 42 | 9/9 | `L1D0|F|fix|U0|EV0|TSUITE=CLAIMED_NOT_RUN|C` |
| queue-discovery-1 | queue_retry_duplicate_discovery | 166 | 305 | 43 | 9/9 | `L1D0|F|queue|U2|EV+|QSTALE>RETRY>DUP_EXEC|-` |
| queue-discovery-2 | queue_retry_duplicate_discovery | 168 | 374 | 43 | 9/9 | `L1D0|F|queue|U2|EV+|RECOV>QSTALE>DUP_EXEC|S` |
| queue-discovery-3 | queue_retry_duplicate_discovery | 134 | 310 | 39 | 9/9 | `L1D0|O|queue|U3|EV+|CONC>QSTALE>DLOCK|-` |
| blocker-1 | blocker | 133 | 200 | 45 | 9/9 | `L1D0|F|ship|U1|EV0|BLK=SOURCE_COVERAGE_OPEN|-` |
| blocker-2 | blocker | 161 | 268 | 31 | 9/9 | `L1D0|O|release|U2|EV+|BLK>DEP|-` |
| blocker-3 | blocker | 124 | 262 | 32 | 9/9 | `L1D0|F|T-1367|U2|EV+|BLK>VALID|-` |
| hypothesis-1 | hypothesis | 213 | 320 | 36 | 9/9 | `L1D0|H|queue|U3|EV+|RETRY>DUP_EXEC|X` |
| hypothesis-2 | hypothesis | 177 | 258 | 31 | 9/9 | `L1D0|H|loader|U1|EV0|CFG>REGR|X` |
| hypothesis-3 | hypothesis | 186 | 335 | 33 | 9/9 | `L1D0|H|session|U2|EV+|CKPT>PERF|X` |
| goal-1 | human_goal | 100 | 185 | 28 | 9/9 | `L1D0|G|maintenance|-|EV0|?|-` |
| goal-2 | human_goal | 84 | 187 | 25 | 9/9 | `L1D0|G|opencode|-|EV0|?|-` |
| goal-3 | human_goal | 75 | 206 | 24 | 9/9 | `L1D0|G|saimail|-|EV0|?|-` |
| value-1 | human_value | 101 | 179 | 25 | 9/9 | `L1D0|V|priority|-|EV0|?|-` |
| value-2 | human_value | 57 | 197 | 25 | 9/9 | `L1D0|V|tradeoff|-|EV0|?|-` |
| value-3 | human_value | 56 | 167 | 34 | 9/9 | `L1D0|V|style|-|EV0|SIMPLE>CLEVER|-` |
| observation-1 | evidence_backed_observation | 146 | 327 | 48 | 9/9 | `L1D0|O|STATE.md|U4|EV+|TS=2026-09-17T08:50:40Z|-` |
| observation-2 | evidence_backed_observation | 118 | 287 | 33 | 9/9 | `L1D0|O|HEAD|U4|EV+|HEAD=10a2989|-` |
| observation-3 | evidence_backed_observation | 132 | 328 | 34 | 9/9 | `L1D0|O|intake|U4|EV+|RECEIPTS=51|-` |
| unknown-1 | unknown_uncertain | 101 | 221 | 46 | 9/9 | `L1D0|F|delivery|U0|EV0|DUP_EXEC=INTERMITTENT|-` |
| unknown-2 | unknown_uncertain | 102 | 211 | 33 | 9/9 | `L1D0|F|mirror|U0|EV0|META=STALE|-` |
| unknown-3 | unknown_uncertain | 95 | 199 | 45 | 9/9 | `L1D0|F|session|U1|EV0|SESS=UNBOUNDED_GROWTH|-` |
| warning-1 | warning | 160 | 274 | 27 | 9/9 | `L1D0|F|promotion|U2|EV+|?|-` |
| warning-2 | warning | 157 | 279 | 26 | 9/9 | `L1D0|F|envelope|U3|EV+|?|-` |
| warning-3 | warning | 130 | 195 | 35 | 9/9 | `L1D0|F|recovery|U1|EV0|CKPT>RECOV|-` |
| crossref-1 | cross_reference | 161 | 354 | 41 | 9/9 | `L1D0|F|queue|U2|EV+|DUP_EXEC=REPRODUCED|S` |
| crossref-2 | cross_reference | 142 | 373 | 46 | 9/9 | `L1D0|O|LOG.md|U4|EV+|TS=2026-09-17T08:55:00Z|R` |
| crossref-3 | cross_reference | 142 | 338 | 35 | 9/9 | `L1D0|F|b03|U2|EV+|CONF=CALIBRATED|C` |
| unicode-1 | unicode_content | 230 | 303 | 29 | 9/9 | `L1D0|O|opencode.db|U4|EV+|?|-` |
| unicode-2 | unicode_content | 117 | 280 | 24 | 9/9 | `L1D0|F|検証|U2|EV+|?|-` |
| unicode-3 | unicode_content | 85 | 280 | 26 | 9/9 | `L1D0|F|tõendus|U2|EV+|?|-` |
| longpath-1 | long_path_reference | 193 | 381 | 65 | 9/9 | `L1D0|O|operations.py:1860|U4|EV+|VALID=REFUSES_WITHOUT_EVIDENCE|-` |
| longpath-2 | long_path_reference | 172 | 360 | 63 | 9/9 | `L1D0|O|subs/PROTOCOL.md|U4|EV+|SUBSAIPEN=NO_SECOND_WRITE_PATH|-` |
| longpath-3 | long_path_reference | 163 | 355 | 59 | 9/9 | `L1D0|O|phases/verify.md|U4|EV+|VALID=RED_CONTROL_REQUIRED|-` |
| dictterms-1 | repeated_dictionary_terms | 168 | 310 | 54 | 9/9 | `L1D0|F|queue|U2|EV+|RECOV>QSTALE>RETRY>DUP_EXEC>REGR|-` |
| dictterms-2 | repeated_dictionary_terms | 162 | 297 | 48 | 9/9 | `L1D0|F|envelope|U2|EV+|CKPT>VALID>SIG>ENV>REGR|-` |
| dictterms-3 | repeated_dictionary_terms | 167 | 305 | 43 | 9/9 | `L1D0|F|db|U2|EV+|DB>META>TS>CFG>PERF>CONC|-` |

