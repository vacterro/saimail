Source artifact: `stability_live_20260917T161636Z.json`

# SAIFREN stability report

Authority: `EXPERIMENT_DATA`, which is not `CONSENSUS`, `TRUTH`, `PROTOCOL_CHANGE`, `USER_INTENT`.
Live output is experiment data. It is not consensus, not truth, not a protocol change and not user intent. Disagreement between agents is preserved per call. Reasoning traces are dropped before storage.

Registration `sha256:c60bc6ac40bf913ba6f464275736483a1ab7b2920d282bfc647b701d12402b5c`; N=3 per participant per case; 30 live calls (6 discovery, 24 experiment) of cap 32; stopped: no.
Three repeats is a distribution, not a population estimate. A sample remains a sample.

## EXPERIMENT_CLASS

- EXPERIMENT_CLASS: `SAIFREN_EXTERNAL_COMPARATOR`
- COMBO: `SAIFREN`
- OBSERVED_COMBO_MEMBERS: `deepseek/deepseek-v4-flash`
- EXTERNAL_COMPARATORS: `MiniMaxAI/MiniMax-M3`
- DISTINCT_REPORTED_MODELS: `MiniMaxAI/MiniMax-M3`, `deepseek/deepseek-v4-flash`
- ROSTER_STATUS: `NOT_OBSERVABLE` (basis `ROSTER_NOT_EXPOSED`)

Membership is sampled through the combo alias, never read from a roster and never inferred from catalog eligibility. OBSERVED_COMBO_MEMBERS is what this run saw, not what SAIFREN contains. EXTERNAL_COMPARATORS are live catalog models answering beside SAIFREN for contrast; nothing in the run shows they are SAIFREN members.

## STABILITY_RUNS

### `MiniMaxAI/MiniMax-M3` via `goat/MiniMaxAI/MiniMax-M3` — RELATION_CONTRADICTION (`S1.contradiction`, SAILANG frame v4 / SAIB4)
- external comparator, not a SAIFREN member; repeats 3; verdicts PASS 3
- Q1: YES 3
- Q2: NO 3
- Q3: YES 3

### `MiniMaxAI/MiniMax-M3` via `goat/MiniMaxAI/MiniMax-M3` — FACTUAL_UNVERIFIED (`S1.evidence_absent`, SAILANG frame v4 / SAIB4)
- external comparator, not a SAIFREN member; repeats 3; verdicts PASS 3
- Q1: NO 3
- Q2: NO 3
- Q3: NO 3

### `MiniMaxAI/MiniMax-M3` via `goat/MiniMaxAI/MiniMax-M3` — OPEN_VERSUS_DEFER (`S3.mailbox`, SAILANG frame v4 / SAIB4)
- external comparator, not a SAIFREN member; repeats 3; verdicts FAIL 3
- M1: DEFER 1, OPEN 2
- M2: OPEN 1, DEFER 2
- M3: IGNORE 3
- M4: DEFER 1, IGNORE 2
- M1 attention: EXACT 2, UNDER_OPEN 1
- M2 attention: EXACT 2, OVER_OPEN 1
- M3 attention: FALSE_IGNORE 3
- M4 attention: EXACT 2, OTHER 1

### `MiniMaxAI/MiniMax-M3` via `goat/MiniMaxAI/MiniMax-M3` — EV0_ATTACHMENT (`S4.ev0_is_not_weak`, SAILANG frame v4 / SAIB4)
- external comparator, not a SAIFREN member; repeats 3; verdicts PASS 3
- ANSWER: NO 3

### `deepseek/deepseek-v4-flash` via `SAIFREN` — RELATION_CONTRADICTION (`S1.contradiction`, SAILANG frame v4 / SAIB4)
- observed SAIFREN member, reached through the alias; repeats 3; verdicts PASS 3
- Q1: YES 3
- Q2: NO 3
- Q3: YES 3

### `deepseek/deepseek-v4-flash` via `SAIFREN` — FACTUAL_UNVERIFIED (`S1.evidence_absent`, SAILANG frame v4 / SAIB4)
- observed SAIFREN member, reached through the alias; repeats 3; verdicts PASS 3
- Q1: NO 3
- Q2: NO 3
- Q3: NO 3

### `deepseek/deepseek-v4-flash` via `SAIFREN` — OPEN_VERSUS_DEFER (`S3.mailbox`, SAILANG frame v4 / SAIB4)
- observed SAIFREN member, reached through the alias; repeats 3; verdicts PASS 3
- M1: OPEN 3
- M2: DEFER 3
- M3: DEFER 2, OPEN 1
- M4: IGNORE 3
- M1 attention: EXACT 3
- M2 attention: EXACT 3
- M3 attention: EXACT 1, UNDER_OPEN 2
- M4 attention: EXACT 3

### `deepseek/deepseek-v4-flash` via `SAIFREN` — EV0_ATTACHMENT (`S4.ev0_is_not_weak`, SAILANG frame v4 / SAIB4)
- observed SAIFREN member, reached through the alias; repeats 3; verdicts PASS 3
- ANSWER: NO 3

## MODEL_VARIANCE

same participant, same stimulus, different answers: 4
- {"model": "deepseek/deepseek-v4-flash", "route": "SAIFREN", "scenario": "S3.mailbox", "boundary": "M3", "answers": {"DEFER": 2, "OPEN": 1}, "answered_repeats": 3, "stimulus_sha256": "d0a47e204d7b11f6f862602567bc21ccff25ece94cc4abf416d0e68ceab1ecee"}
- {"model": "MiniMaxAI/MiniMax-M3", "route": "goat/MiniMaxAI/MiniMax-M3", "scenario": "S3.mailbox", "boundary": "M1", "answers": {"DEFER": 1, "OPEN": 2}, "answered_repeats": 3, "stimulus_sha256": "d0a47e204d7b11f6f862602567bc21ccff25ece94cc4abf416d0e68ceab1ecee"}
- {"model": "MiniMaxAI/MiniMax-M3", "route": "goat/MiniMaxAI/MiniMax-M3", "scenario": "S3.mailbox", "boundary": "M2", "answers": {"DEFER": 2, "OPEN": 1}, "answered_repeats": 3, "stimulus_sha256": "d0a47e204d7b11f6f862602567bc21ccff25ece94cc4abf416d0e68ceab1ecee"}
- {"model": "MiniMaxAI/MiniMax-M3", "route": "goat/MiniMaxAI/MiniMax-M3", "scenario": "S3.mailbox", "boundary": "M4", "answers": {"DEFER": 1, "IGNORE": 2}, "answered_repeats": 3, "stimulus_sha256": "d0a47e204d7b11f6f862602567bc21ccff25ece94cc4abf416d0e68ceab1ecee"}

## CROSS_MODEL_DISAGREEMENT

participants each stable, stably different: 0

## PROTOCOL_HOTSPOT

independent participants repeatedly failing one boundary: 0

## STIMULUS_CHANGED

repeats that did not share one prompt digest: 0

## OPAQUE_CONTEXT

Gateway-reported input minus the locally estimated prompt. What fills the difference is not visible here and is not guessed at.

- `MiniMaxAI/MiniMax-M3`: 12 call(s), 12 measured; delta 2879..2889 tokens
- `deepseek/deepseek-v4-flash`: 12 call(s), 12 measured; delta 2781..2796 tokens

## ERRORS

- none
