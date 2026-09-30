# Structured-output / completion-budget capability gate

Registration: `sha256:e696db4c786ea60b9764b50e924fd93ed505efdf1b8b366529600ac100c4ffdf`; dry run: False; status: `COMPLETED`.
Calls: 6/6; dispatches 6; network calls 6; retries 0; repairs 0; fallbacks 0.

## Capability matrix

| probe | A | B |
|---|---|---|
| 4096 | REQUEST_ACCEPTED_CONFORMING | REQUEST_ACCEPTED_CONFORMING |
| json_object | REQUEST_ACCEPTED_CONFORMING | REQUEST_ACCEPTED_CONFORMING |
| json_schema | REQUEST_ACCEPTED_CONFORMING | REQUEST_ACCEPTED_CONFORMING |

## Fresh reported models

- A/BUDGET_4096: requested `SAIFREN`, reported known label `deepseek/deepseek-v4-flash` (SHA256 `6d0dcdfbe2d7fa1891744b4d7cb01c9523959bd052f9866984a7020c6f422f68`).
- B/BUDGET_4096: requested `goat/MiniMaxAI/MiniMax-M3`, reported known label `MiniMaxAI/MiniMax-M3` (SHA256 `3fe8916ce3681f1b64311cccdf7078ae5a29c13e0c83dffd31276f78d55de524`).
- A/JSON_OBJECT: requested `SAIFREN`, reported known label `deepseek/deepseek-v4-flash` (SHA256 `6d0dcdfbe2d7fa1891744b4d7cb01c9523959bd052f9866984a7020c6f422f68`).
- B/JSON_OBJECT: requested `goat/MiniMaxAI/MiniMax-M3`, reported known label `MiniMaxAI/MiniMax-M3` (SHA256 `3fe8916ce3681f1b64311cccdf7078ae5a29c13e0c83dffd31276f78d55de524`).
- A/JSON_SCHEMA: requested `SAIFREN`, reported known label `deepseek/deepseek-v4-flash` (SHA256 `6d0dcdfbe2d7fa1891744b4d7cb01c9523959bd052f9866984a7020c6f422f68`).
- B/JSON_SCHEMA: requested `goat/MiniMaxAI/MiniMax-M3`, reported known label `MiniMaxAI/MiniMax-M3` (SHA256 `3fe8916ce3681f1b64311cccdf7078ae5a29c13e0c83dffd31276f78d55de524`).

## Twelve questions

1. Route A accepted the 4096 request: REQUEST_ACCEPTED_CONFORMING.
2. Route B accepted the 4096 request: REQUEST_ACCEPTED_CONFORMING.
3. Synthetic context comparability to T-71: A CONTEXT_SHAPE_COMPARABLE, B CONTEXT_SHAPE_COMPARABLE (ratios {'A': 0.95, 'B': 0.98}).
4. Route A accepted json_object: REQUEST_ACCEPTED_CONFORMING.
5. Route B accepted json_object: REQUEST_ACCEPTED_CONFORMING.
6. Sample conformance per corresponding json_object result: A REQUEST_ACCEPTED_CONFORMING; B REQUEST_ACCEPTED_CONFORMING.
7. Route A accepted json_schema: REQUEST_ACCEPTED_CONFORMING.
8. Route B accepted json_schema: REQUEST_ACCEPTED_CONFORMING.
9. Sample conformance per corresponding json_schema result: A REQUEST_ACCEPTED_CONFORMING; B REQUEST_ACCEPTED_CONFORMING.
10. Native enforcement proven: False. One conforming sample is not stable enforcement.
11. A real 4096 run through the current local output path is safe: False (local visible-output cap 4000 characters).
12. Fallbacks/retries performed: fallbacks 0, retries 0.

## Interpretation limits

A capability probe is not product semantics: one accepted request is not stable capability, and one conforming output is not proven enforcement.
No model ranking is made: six capability calls are not model evaluation.
No real corpus, no AllyAdvice generation and no semantic review was involved.
Outputs are represented by SHA256 and byte count only; prompts by hash.
No mail, seal, store or attention operation is invoked.
Provider retention/training use is NOT_VERIFIED_BY_SAIMAIL.
