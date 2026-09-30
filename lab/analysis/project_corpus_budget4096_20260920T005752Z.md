# Real-project 4096 budget-only reachability

Registration: `sha256:ac6a940220d65916355dc648f4c1dbc4cb24331254cb793cc1c2ec1a6c383190`.
Status: `COMPLETED`; dry run: False.
Exact B-018 corpus: `sha256:b009bdf3a8efd28f29be76d0dfd9c2809c0e7dd010af8e92c94a97fbeeec19ac`; 8 artifacts / 5 declared events.
Token budgets: probe 16, generator 4096, reviewer 2048; response_format NONE.
Calls: 4/6; probes 2, generation 2, review 0; retries 0; repairs 0.

## R1

Generator A / reviewer B: `REJECTED`.
Candidate parsed: True; reviewer calls: 0; reviewed state minted: False.
Stages: GENERATOR_TRANSPORT=OK, GENERATOR_PARSE=OK, GENERATOR_RESULT=CANDIDATE, ALLY1_STRUCTURAL_GATE=PASS, CORPUS_REF_GATE=FAIL, EVENT_FLOOR_GATE=NOT_REACHED, EVIDENCE_RESOLUTION=NOT_REACHED, REVIEWER_TRANSPORT=NOT_REACHED, REVIEWER_PARSE=NOT_REACHED, SEMANTIC_REVIEW=SKIPPED, FINAL_GATE_OUTCOME=REJECTED.

## R2

Generator B / reviewer A: `NO_ADVICE`.
Candidate parsed: False; reviewer calls: 0; reviewed state minted: False.
Stages: GENERATOR_TRANSPORT=OK, GENERATOR_PARSE=OK, GENERATOR_RESULT=NO_ADVICE, ALLY1_STRUCTURAL_GATE=NOT_REACHED, CORPUS_REF_GATE=NOT_REACHED, EVENT_FLOOR_GATE=NOT_REACHED, EVIDENCE_RESOLUTION=NOT_REACHED, REVIEWER_TRANSPORT=NOT_REACHED, REVIEWER_PARSE=NOT_REACHED, SEMANTIC_REVIEW=SKIPPED, FINAL_GATE_OUTCOME=NO_ADVICE.

### R1 GENERATOR

Requested `SAIFREN`; max_tokens 4096; response_format NONE.
Reported known label `deepseek/deepseek-v4-flash` (SHA256 `6d0dcdfbe2d7fa1891744b4d7cb01c9523959bd052f9866984a7020c6f422f68`).
Parser `OK` / `ALLY_GENERATED_REF_OUTSIDE_CORPUS`; full output bytes 3280; legacy 4000 would truncate False; finish `stop`.
Shape: {"blank": false, "duplicate_key_count": 0, "error_column": null, "error_line": null, "error_position": null, "fence_token_present": false, "first_token": "OBJECT", "input_kind": "TEXT", "nested_item_count": 3, "nested_missing_count": 0, "nested_type_mismatch_count": 0, "nested_unknown_count": 0, "nonfinite_constant_count": 0, "result_kind": "CANDIDATE", "root_type": "OBJECT", "syntax": "OK", "syntax_error": null, "top_missing_count": 0, "top_type_mismatch_count": 0, "top_unknown_count": 0, "version": "PARSE-SHAPE-1"}.

### R2 GENERATOR

Requested `goat/MiniMaxAI/MiniMax-M3`; max_tokens 4096; response_format NONE.
Reported known label `MiniMaxAI/MiniMax-M3` (SHA256 `3fe8916ce3681f1b64311cccdf7078ae5a29c13e0c83dffd31276f78d55de524`).
Parser `OK` / `None`; full output bytes 22; legacy 4000 would truncate False; finish `stop`.
Shape: {"blank": false, "duplicate_key_count": 0, "error_column": null, "error_line": null, "error_position": null, "fence_token_present": false, "first_token": "OBJECT", "input_kind": "TEXT", "nested_item_count": 0, "nested_missing_count": 0, "nested_type_mismatch_count": 0, "nested_unknown_count": 0, "nonfinite_constant_count": 0, "result_kind": "NO_ADVICE", "root_type": "OBJECT", "syntax": "OK", "syntax_error": null, "top_missing_count": 0, "top_type_mismatch_count": 0, "top_unknown_count": 0, "version": "PARSE-SHAPE-1"}.

## Interpretation limits

Observability is not acceptance. Only unchanged strict parsers and B-016 gates decide outcomes.
The local 4000-character parser-input projection is replaced by an ephemeral full-output path; the generic transport keeps its historical 4000-character behaviour byte for byte.
T-69 R1 shape remains UNKNOWN: its 3218 bytes were discarded; hashes cannot reconstruct them.
Prompts, corpus and requested routes match T-71; only generator max_tokens changed 2048 -> 4096.
Reported models can change behind a requested route. One sample per role assignment is not a model ranking.
NO_ADVICE is successful; a reviewer PASS is not truth; corpus completeness remains NOT_PROVEN.
No generated advice, prompt, corpus content, reviewer rationale or error body is persisted or presented.
No mail, sealing, storage or attention operation is invoked. Provider retention is NOT_VERIFIED_BY_SAIMAIL.
This single live attempt is terminal: no retry, repair, replacement or additional sample.
