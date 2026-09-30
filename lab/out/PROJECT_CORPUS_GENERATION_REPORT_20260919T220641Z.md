Source artifact: `project_corpus_generation_live_20260919T220641Z.json`

# PROJECT CORPUS GENERATION PILOT REPORT

Status `COMPLETED`; dry run: False; started `2026-09-19T22:06:41Z`; stopped: no.

## LIVE REGISTRATION

- LIVE_REGISTRATION_ID: `sha256:5d750a8aaf166a02d7f1bc13c98f7bbde91728dd616083a0d2cde563e1f40b6e`
- registration file: `project_corpus_generation_registration.json`

## EXACT INPUT IDENTITY (B-018)

- B018_REGISTRATION_ID: `sha256:dfd8b48dded34de8426181f309032da31c86e83f675412add15076fc421a096f`
- BUILD_ID: `sha256:0e05460aae1645b6bdfeec887f02a978a185026422faf74c90238f0938bd4e35`
- CORPUS_ID: `sha256:b009bdf3a8efd28f29be76d0dfd9c2809c0e7dd010af8e92c94a97fbeeec19ac`
- PROJECT_SCOPE: `project:saimail`
- artifact_count: 8
- event_count: 5
- COMPLETENESS: `NOT_PROVEN`

## PARTICIPANTS (frozen before content calls)

- role `A` requested `SAIFREN` reported `deepseek/deepseek-v4-flash` member_status `OBSERVED_COMBO_MEMBER` source `COMBO_ALIAS`
- role `B` requested `goat/MiniMaxAI/MiniMax-M3` reported `MiniMaxAI/MiniMax-M3` member_status `NOT_PROVEN_COMBO_MEMBER` source `CATALOG_ELIGIBLE`

## CALL BUDGET (declared / spent)

- declared max: 12; planned max: 12
- spent: total 8 (discovery 6, generation 2, review 0)
- retries: 0; repair calls: 0

## REPLICATES

### R1 generator `A` reviewer `B`
- generator requested `SAIFREN` reported `deepseek/deepseek-v4-flash`; reviewer requested `goat/MiniMaxAI/MiniMax-M3` reported `None`
- same_reported_model_pair: False
- outcome: `ERROR` code `ALLY_GEN_PROVIDER_ERROR`; reviewer calls: 0

### R2 generator `B` reviewer `A`
- generator requested `goat/MiniMaxAI/MiniMax-M3` reported `MiniMaxAI/MiniMax-M3`; reviewer requested `SAIFREN` reported `None`
- same_reported_model_pair: False
- outcome: `NO_ADVICE`; reviewer calls: 0

## SEMANTIC REVIEW SUMMARY

- R1: no semantic review call
- R2: no semantic review call

## EXTERNAL DATA HANDLING LIMIT

SAIMAIL did not persist local raw generated/reviewer prose under this pilot policy. The corpus and any generated candidate were nevertheless transmitted to external inference endpoints as required by the registered experiment. Provider-side retention/use was not established by this experiment.

## PLAINTEXT RETENTION PROOF

- prompt text: not persisted
- generator output: not persisted (SHA-256 and byte length only)
- candidate prose: not persisted (candidate id, refs and counts only)
- reviewer rationale: not persisted (verdict, refs and dimension only)
- provider error bodies: not persisted (error class and HTTP status only)
- in-process ephemerality is not claimed as cryptographic memory erasure

## HIDDEN CONTEXT OBSERVATION

- measured calls: 2; delta range: 3050..4142
- a positive delta is opaque upstream context or accounting, never inferred

## WHAT THIS RUN DOES NOT SHOW

- It does not show which model is better, safer or more trustworthy: each role assignment has one generation sample.
- It does not show that any generated interpretation is true, that a pattern is real or that a reviewer verdict is correct.
- APPROVED, if present, means only that one reviewer invocation returned PASS on all frozen B-016 dimensions for that exact candidate/corpus; it is not accepted advice and was not shown to the operator.
- It does not generalise from this registered sample to model behaviour, to SAIFREN as a population, or to any other corpus.
- It does not measure provider-side retention or training use.
