Source artifact: `saifren_live_20260930T125211Z_b9d3f9d3fd22479c.json`

# SAIFREN live run report

Authority: `EXPERIMENT_DATA`, which is not `CONSENSUS`, `TRUTH`, `PROTOCOL_CHANGE`, `USER_INTENT`.
Live output is experiment data. It is not consensus, not truth, not a protocol change and not user intent. Disagreement between agents is preserved per call. Reasoning traces are dropped before storage.

Started 2026-09-30T12:52:11Z; 9 live calls of 6 planned, cap 14; stopped: no.

## LIVE_RUN_COUNT

- calls attempted: 6; returned content: 6; errors: 0
- unit verdicts: PASS 2, FAIL 0, MEASURED 1, ERROR 0, NOT_RUN 0

## EXPERIMENT_CLASS

- EXPERIMENT_CLASS: `SAIFREN_EXTERNAL_COMPARATOR` (rule `saifren-experiment-class/1`, membership evidence from CALL_RECORDS)
- COMBO: `SAIFREN`
- OBSERVED_COMBO_MEMBERS: `stealth/space-bunny-alpha`
- EXTERNAL_COMPARATORS: `gemini-3-flash`
- DISTINCT_REPORTED_MODELS: `gemini-3-flash`, `stealth/space-bunny-alpha`
- ROSTER_STATUS: `NOT_OBSERVABLE` (basis `ROSTER_NOT_EXPOSED`)

Membership is sampled through the combo alias, never read from a roster and never inferred from catalog eligibility. OBSERVED_COMBO_MEMBERS is what this run saw, not what SAIFREN contains. EXTERNAL_COMPARATORS are live catalog models answering beside SAIFREN for contrast; nothing in the run shows they are SAIFREN members.

## ROUTES_OBSERVED

- `gemini-3-flash`: 3 call(s); external comparator, not a SAIFREN member
- `stealth/space-bunny-alpha`: 3 call(s); observed SAIFREN member, reached through the alias
- resolution: {'ALIAS_ONLY': 0, 'MODEL_REPORTED': 6}; provider stated by gateway: ['Stealth'] (a model id prefix is a namespace, not a provider claim)

## R2_SEMANTIC_RESULTS (S1)


## TRUE_AGENT_HANDOFF_RESULTS (S2)

- S2.chain1: PASS; A via `stealth/space-bunny-alpha` said kind=hypothesis rung=unverified evidence_invented=False; transform ACCEPTED ; B via `gemini-3-flash` evidence=NO inflation=False qualifier_retained=True next=COLLECT ARTIFACT; routes differ: True

## LEGACY_CONTROL_RESULTS (S5)

Sample: 1 trial(s). Every line is a separate measurement; none is a score, and a sample this small supports no generalization.

### legacy arm, n=1
- correct_first_verification_target: 1/1
- repeated_known_mistake: 0/1
- orientation_failure: 0/1
- timeout_ruled_out: 1/1
- open_suspicion_ruled_out: 0/1
- invented_evidence: 0/1 [[]]
- unnecessary_work: 0/1 [[]]
- task_relevant_semantic_retention: 1/1
- qualifier_retention: 1/1
- scope_retention: 1/1
- transferred_hypothesis_hardened: 0/1
- first targets ['B'], steps [['B', 'D']], routes ['gemini-3-flash']
### control arm, n=1
- correct_first_verification_target: 1/1
- repeated_known_mistake: 0/1
- orientation_failure: 0/1
- timeout_ruled_out: 0/1
- open_suspicion_ruled_out: 0/1
- invented_evidence: 0/1 [[]]
- unnecessary_work: 1/1 [['E']]
- task_relevant_semantic_retention: 1/1
- first targets ['B'], steps [['B', 'D', 'E']], routes ['stealth/space-bunny-alpha']
### packets written by A, n=1
- packet_complete: 1/1
- packet_red_herring_captured: 1/1
- packet_open_question_kept: 1/1
- packet_scope_caveat_kept: 1/1
- packet_ungrounded_advice: 0/1
- packet_invented_refs: [[]]
- packet_evidence_misattribution: [[]]

## CONFIDENCE_INFLATION

- S2 A rung above unverified: 0/1
- S2 B acts on or cites the unverified claim: 0/1
- S2 B hardening words in KNOWN: [[]]
- S1 hypothesis read as established fact: not run
- S4 SUPPORTED read as proven: not run
- S5 packet hardening in WATCH_NEXT: [[]]

## EVIDENCE_INVENTION

- S2 A claims attached evidence: 0/1
- S2 B says evidence exists: 0/1
- S1 absent evidence read as asserted: not run
- S5 packet refs not in the investigation: [[]]
- S5 legacy arm refs not in its input: [[]]
- S5 control arm refs not in its input: [[]]

## AUTHORITY_CONFUSION

- S4 assistant proposal read as user instruction: not run
- S1 goal read as a statement about the world: not run
- S1 goal read as needing evidence: not run

## QUALIFIER_LOSS

- S2 B drops what remains unverified: 0/1
- S1 'no evidence attached' read as false: not run
- S4 EV:0 read as weak evidence: not run
- S4 UNKNOWN read as false: not run
- S5 legacy arm rules out the open heartbeat suspicion: 0/1
- S5 legacy arm keeps the open suspicion: 1/1
- S5 legacy arm retains observed scope: 1/1

## DEFER_BEHAVIOR (S3)

Four named outcomes, reported separately. `EXACT` is agreement with the deterministic selector; `FALSE_IGNORE` is an item the selector opened and the agent dropped; `UNDER_OPEN` is one the selector opened and the agent kept for later; `OVER_OPEN` is context spent on what the filter did not ask for. None of them is a verdict, and a unit's PASS is decided by its registered expectation, not by this table.

- run totals: EXACT 4
- S3.mailbox via `gemini-3-flash`: PASS
  - M1: agent OPEN, deterministic selector OPEN -> EXACT
  - M2: agent DEFER, deterministic selector DEFER -> EXACT
  - M3: agent OPEN, deterministic selector OPEN -> EXACT
  - M4: agent IGNORE, deterministic selector IGNORE -> EXACT
  - EXACT 4

## OPAQUE_CONTEXT_FINDINGS

- route `gemini-3-flash`: 3 call(s); delta range 3426..3867 tokens (local prompt est 395..520, gateway prompt 3837..4387)
- route `stealth/space-bunny-alpha`: 3 call(s); delta range 2878..2884 tokens (local prompt est 170..558, gateway prompt 3048..3442)

### Per-call token accounting
- S2.chain1:A via `stealth/space-bunny-alpha`: local_est=170, gateway_reported=3048, delta=2878
- S2.chain1:B via `gemini-3-flash`: local_est=395, gateway_reported=4176, delta=3781
- S3.mailbox:single via `gemini-3-flash`: local_est=411, gateway_reported=3837, delta=3426
- S5.trial1:A via `stealth/space-bunny-alpha`: local_est=558, gateway_reported=3442, delta=2884
- S5.trial1:B_legacy via `gemini-3-flash`: local_est=520, gateway_reported=4387, delta=3867
- S5.trial1:B_control via `stealth/space-bunny-alpha`: local_est=320, gateway_reported=3201, delta=2881

## ERRORS_TIMEOUTS

- none
