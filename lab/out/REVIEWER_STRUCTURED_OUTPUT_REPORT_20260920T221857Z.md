# V2-03 reviewer structured-output experiment

Registration: `sha256:1e59dfc30f939fb34976d1b795ef49de037603261495bc76fdba430fcc87ba19`.
Single variable: `reviewer response_format` ABSENT -> JSON_SCHEMA.
Generator response format: `JSON_SCHEMA` (unchanged); reviewer response format: `JSON_SCHEMA`.
Reviewer schema template sha256 `8db0e5b00c8d817ce9130814ee5a952c6d1ead344539e7ce6aa4acdba6396bb9`; wrapper `saimail_ally_review_report`.
Status: `COMPLETED`; dry run: False.
Token budgets: probe 16, generator 4096, reviewer 2048.
Calls: 5/6; probes 2, generation 2, review 1; retries 0; repairs 0.

## ADMISSION

verify_current `CURRENT_MATCH`; admit_live `True`; granted before first network call `True`.

## PROBES

- `A/PROBE` requested `SAIFREN`; transport `ERROR`; capability `TRANSPORT_ERROR`; parse `NOT_TEXT`; schema `NOT_EVALUABLE`; enforcement `NOT_PROVEN`.
- `B/PROBE` requested `goat/MiniMaxAI/MiniMax-M3`; transport `OK`; capability `REQUEST_ACCEPTED`; parse `OK`; schema `VALID`; enforcement `NOT_PROVEN`.

## R1

Generator A / reviewer B: `ERROR` / class `REVIEWER_BAD_JSON`.
Candidate parsed: True; reviewer calls: 1; reviewed state minted: False; event floor `MET`; outside refs 0.
Stages: GENERATOR_TRANSPORT=OK, GENERATOR_PARSE=OK, GENERATOR_RESULT=CANDIDATE, ALLY1_STRUCTURAL_GATE=PASS, CORPUS_REF_GATE=PASS, EVENT_FLOOR_GATE=PASS, EVIDENCE_RESOLUTION=PASS, REVIEWER_TRANSPORT=OK, REVIEWER_PARSE=SCHEMA_ERROR, SEMANTIC_REVIEW=SKIPPED, FINAL_GATE_OUTCOME=ERROR.

## R2

Generator B / reviewer A: `NO_ADVICE` / class `NO_ADVICE`.
Candidate parsed: False; reviewer calls: 0; reviewed state minted: False; event floor `NOT_EVALUABLE`; outside refs 0.
Stages: GENERATOR_TRANSPORT=OK, GENERATOR_PARSE=OK, GENERATOR_RESULT=NO_ADVICE, ALLY1_STRUCTURAL_GATE=NOT_REACHED, CORPUS_REF_GATE=NOT_REACHED, EVENT_FLOOR_GATE=NOT_REACHED, EVIDENCE_RESOLUTION=NOT_REACHED, REVIEWER_TRANSPORT=NOT_REACHED, REVIEWER_PARSE=NOT_REACHED, SEMANTIC_REVIEW=SKIPPED, FINAL_GATE_OUTCOME=NO_ADVICE.

## REVIEWER_VERDICTS

- R1: outcome `ERROR` code `ALLY_GEN_REVIEWER_ERROR`; reviewer verdicts: not reached.
- R2: outcome `NO_ADVICE`; reviewer verdicts: not reached.

## INTERPRETATION LIMITS

Observability is not acceptance. Only the unchanged strict parsers and B-016 gates decide outcomes.
Provider/schema acceptance never replaces product validation; the existing SemanticReviewReport remains authoritative for coverage and uniqueness.
A conforming probe sample does not prove that the provider enforces the schema; provider enforcement remains NOT_PROVEN.
REQUEST SENT WITH SCHEMA != PROVIDER ENFORCED SCHEMA.
One sample per role assignment is not a model property; no ranking is made.
A parseable FAIL or UNKNOWN report still proves output-format reachability; PARSEABLE REVIEW != APPROVED ADVICE.
NO_ADVICE is successful; a reviewer PASS is not truth; corpus completeness remains NOT_PROVEN.
No generated advice, prompt, corpus content, reviewer rationale or error body is persisted or presented.
No mail, sealing, storage or attention operation is invoked. Provider retention is NOT_VERIFIED_BY_SAIMAIL.
This single live attempt is terminal: no retry, repair, replacement or response-format fallback.
