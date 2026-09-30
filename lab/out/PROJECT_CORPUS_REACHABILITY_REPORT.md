# Real-project strict-schema reachability

Registration: `sha256:825c0853dc1a5cd73939bbf91201fb1e4f8a8b40a62e0d69a87d0fcd6be7dc16`.
Status: `COMPLETED`; dry run: False.
Exact B-018 corpus: `sha256:b009bdf3a8efd28f29be76d0dfd9c2809c0e7dd010af8e92c94a97fbeeec19ac`; 8 artifacts / 5 declared events.
Calls: 4/6; probes 2, generation 2, review 0; retries 0; repairs 0.

## R1

Generator A / reviewer B: `ERROR`.
Candidate parsed: False; reviewer calls: 0; reviewed state minted: False.
Stages: GENERATOR_TRANSPORT=OK, GENERATOR_PARSE=SCHEMA_ERROR, GENERATOR_RESULT=ERROR, ALLY1_STRUCTURAL_GATE=NOT_REACHED, CORPUS_REF_GATE=NOT_REACHED, EVENT_FLOOR_GATE=NOT_REACHED, EVIDENCE_RESOLUTION=NOT_REACHED, REVIEWER_TRANSPORT=NOT_REACHED, REVIEWER_PARSE=NOT_REACHED, SEMANTIC_REVIEW=NOT_REACHED, FINAL_GATE_OUTCOME=ERROR.

## R2

Generator B / reviewer A: `NO_ADVICE`.
Candidate parsed: False; reviewer calls: 0; reviewed state minted: False.
Stages: GENERATOR_TRANSPORT=OK, GENERATOR_PARSE=OK, GENERATOR_RESULT=NO_ADVICE, ALLY1_STRUCTURAL_GATE=NOT_REACHED, CORPUS_REF_GATE=NOT_REACHED, EVENT_FLOOR_GATE=NOT_REACHED, EVIDENCE_RESOLUTION=NOT_REACHED, REVIEWER_TRANSPORT=NOT_REACHED, REVIEWER_PARSE=NOT_REACHED, SEMANTIC_REVIEW=SKIPPED, FINAL_GATE_OUTCOME=NO_ADVICE.

### R1 GENERATOR

Requested `SAIFREN`; reported known label `deepseek/deepseek-v4-flash` (SHA256 `6d0dcdfbe2d7fa1891744b4d7cb01c9523959bd052f9866984a7020c6f422f68`).
Parser `SCHEMA_ERROR` / `ALLY_LAB_BAD_JSON`; input bytes 1525; finish `length`; transport cap applied False.
Shape: {"blank": false, "duplicate_key_count": 0, "error_column": 1380, "error_line": 1, "error_position": 1379, "fence_token_present": false, "first_token": "OBJECT", "input_kind": "TEXT", "nested_item_count": null, "nested_missing_count": null, "nested_type_mismatch_count": null, "nested_unknown_count": null, "nonfinite_constant_count": 0, "result_kind": "ABSENT", "root_type": null, "syntax": "INVALID", "syntax_error": "INVALID_JSON", "top_missing_count": null, "top_type_mismatch_count": null, "top_unknown_count": null, "version": "PARSE-SHAPE-1"}.

### R2 GENERATOR

Requested `goat/MiniMaxAI/MiniMax-M3`; reported known label `MiniMaxAI/MiniMax-M3` (SHA256 `3fe8916ce3681f1b64311cccdf7078ae5a29c13e0c83dffd31276f78d55de524`).
Parser `OK` / `None`; input bytes 22; finish `stop`; transport cap applied False.
Shape: {"blank": false, "duplicate_key_count": 0, "error_column": null, "error_line": null, "error_position": null, "fence_token_present": false, "first_token": "OBJECT", "input_kind": "TEXT", "nested_item_count": 0, "nested_missing_count": 0, "nested_type_mismatch_count": 0, "nested_unknown_count": 0, "nonfinite_constant_count": 0, "result_kind": "NO_ADVICE", "root_type": "OBJECT", "syntax": "OK", "syntax_error": null, "top_missing_count": 0, "top_type_mismatch_count": 0, "top_unknown_count": 0, "version": "PARSE-SHAPE-1"}.

## Interpretation limits

Observability is not acceptance. Only unchanged strict parsers and B-016 gates decide outcomes.
T-69 R1 shape remains UNKNOWN: its 3218 bytes were discarded; hashes cannot reconstruct them.
Prompts, parser-input transport cap, corpus and requested routes match T-69. Two fixed-route probes replace catalog selection.
Reported models can change behind a requested route. One sample per role assignment is not a model ranking.
NO_ADVICE is successful; a reviewer PASS is not truth; corpus completeness remains NOT_PROVEN.
No generated advice, prompt, corpus content, reviewer rationale or error body is persisted or presented.
No mail, sealing, storage or attention operation is invoked. Provider retention/training use is NOT_VERIFIED_BY_SAIMAIL.
This single live attempt is terminal: no retry, repair, replacement or additional sample.
