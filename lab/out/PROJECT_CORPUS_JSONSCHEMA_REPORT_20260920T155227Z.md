# FG-04B JSON_SCHEMA reachability experiment

Registration: `sha256:1e7784bb5efc91531ad23fa91ecafd87dc899a26198b8e5e443590a31fb3f978`.
Schema policy: `CORPUS_ENUM`; schema sha256 `84304f73399c35f3dc755a1cf19780e4b66ba1a93308c8a81e04d95f8ca285ef`.
Status: `COMPLETED`; dry run: False.
Exact B-018 corpus: `sha256:b009bdf3a8efd28f29be76d0dfd9c2809c0e7dd010af8e92c94a97fbeeec19ac`; 8 artifacts / 5 declared events.
Token budgets: probe 16, generator 4096, reviewer 2048; generator/probe response_format JSON_SCHEMA, reviewer ABSENT.
Calls: 5/6; probes 2, generation 2, review 1; retries 0; repairs 0.

## ADMISSION

verify_current `CURRENT_MATCH`; admit_live `True`; granted before first network call `True`.

## PROBES

- `A/PROBE` requested `SAIFREN`; transport `ERROR`; capability `TRANSPORT_ERROR`; parse `NOT_TEXT`; schema `NOT_EVALUABLE`; enforcement `NOT_PROVEN`.
- `B/PROBE` requested `goat/MiniMaxAI/MiniMax-M3`; transport `OK`; capability `REQUEST_ACCEPTED`; parse `OK`; schema `VALID`; enforcement `NOT_PROVEN`.

## R1

Generator A / reviewer B: `ERROR` / class `REVIEWER_ERROR`.
Candidate parsed: True; reviewer calls: 1; reviewed state minted: False; event floor `MET`; outside refs 0.
Stages: GENERATOR_TRANSPORT=OK, GENERATOR_PARSE=OK, GENERATOR_RESULT=CANDIDATE, ALLY1_STRUCTURAL_GATE=PASS, CORPUS_REF_GATE=PASS, EVENT_FLOOR_GATE=PASS, EVIDENCE_RESOLUTION=PASS, REVIEWER_TRANSPORT=OK, REVIEWER_PARSE=SCHEMA_ERROR, SEMANTIC_REVIEW=SKIPPED, FINAL_GATE_OUTCOME=ERROR.

## R2

Generator B / reviewer A: `NO_ADVICE` / class `NO_ADVICE`.
Candidate parsed: False; reviewer calls: 0; reviewed state minted: False; event floor `NOT_EVALUABLE`; outside refs 0.
Stages: GENERATOR_TRANSPORT=OK, GENERATOR_PARSE=OK, GENERATOR_RESULT=NO_ADVICE, ALLY1_STRUCTURAL_GATE=NOT_REACHED, CORPUS_REF_GATE=NOT_REACHED, EVENT_FLOOR_GATE=NOT_REACHED, EVIDENCE_RESOLUTION=NOT_REACHED, REVIEWER_TRANSPORT=NOT_REACHED, REVIEWER_PARSE=NOT_REACHED, SEMANTIC_REVIEW=SKIPPED, FINAL_GATE_OUTCOME=NO_ADVICE.

## REFERENCE_TELEMETRY

- R1: relation `CLEAN`; known evidence refs 7; unknown canonical 0; malformed 0; non-text 0; event refs as evidence 0; corpus ids as evidence 0; event floor `MET`.
- R2: no parsed candidate; telemetry NOT_EVALUABLE.

## PRODUCT_GATE_AND_REVIEW

- R1: outcome `ERROR` code `ALLY_GEN_REVIEWER_ERROR`; reviewer verdicts: not reached.
- R2: outcome `NO_ADVICE`; reviewer verdicts: not reached.

## INTERPRETATION LIMITS

Observability is not acceptance. Only the unchanged strict parsers and B-016 gates decide outcomes.
One sample per role assignment is not a model property; no ranking is made.
A conforming probe sample does not prove that the provider enforces the schema.
Under CORPUS_ENUM the schema participates in restricting reference vocabulary before the product reference gate, which remains independently authoritative.
NO_ADVICE is successful; a reviewer PASS is not truth; corpus completeness remains NOT_PROVEN.
No generated advice, prompt, corpus content, reviewer rationale or error body is persisted or presented.
No mail, sealing, storage or attention operation is invoked. Provider retention is NOT_VERIFIED_BY_SAIMAIL.
This single live attempt is terminal: no retry, repair, replacement or additional sample.
