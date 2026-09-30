# Project corpus generation pilot interpretation

Status `COMPLETED`; LIVE_REGISTRATION_ID `sha256:5d750a8aaf166a02d7f1bc13c98f7bbde91728dd616083a0d2cde563e1f40b6e`; started `2026-09-19T22:06:41Z`.

## Questions this pilot is allowed to answer

1. Was the exact B-018 input reproduced? `BUILD_ID = sha256:0e05460aae1645b6bdfeec887f02a978a185026422faf74c90238f0938bd4e35`, `CORPUS_ID = sha256:b009bdf3a8efd28f29be76d0dfd9c2809c0e7dd010af8e92c94a97fbeeec19ac`, artifact_count 8, event_count 5.
2. R1 generator outcome: `ERROR` code `ALLY_GEN_PROVIDER_ERROR`; reviewer calls 0.
3. R1 structural/event gates: generator result `ERROR`, structural gate `NOT_REACHED`, ref gate `NOT_REACHED`, event floor `NOT_REACHED`.
4. R1 refs confined to corpus: None; observed_scope exact: None.
5. R1 distinct declared events among observed refs: n/a; candidate guidance_mode: n/a.
6. R1 reviewer verdicts: no semantic review call.
7. R1 fail-closed semantics: outcome `ERROR`; reviewed state minted: False.
8. R1 routes: generator requested `SAIFREN` reported `deepseek/deepseek-v4-flash`; reviewer requested `goat/MiniMaxAI/MiniMax-M3` reported `None`; same reported model pair: False.
2. R2 generator outcome: `NO_ADVICE`; reviewer calls 0.
3. R2 structural/event gates: generator result `NO_ADVICE`, structural gate `NOT_REACHED`, ref gate `NOT_REACHED`, event floor `NOT_REACHED`.
4. R2 refs confined to corpus: None; observed_scope exact: None.
5. R2 distinct declared events among observed refs: n/a; candidate guidance_mode: n/a.
6. R2 reviewer verdicts: no semantic review call.
7. R2 fail-closed semantics: outcome `NO_ADVICE`; reviewed state minted: False.
8. R2 routes: generator requested `goat/MiniMaxAI/MiniMax-M3` reported `MiniMaxAI/MiniMax-M3`; reviewer requested `SAIFREN` reported `None`; same reported model pair: False.
9. Local plaintext retention prevented: prompt=False, generator_output=False, candidate_prose=False, reviewer_rationale=False, provider_error_bodies=False, discovery_probe_output=False, only_hashes_lengths_and_metadata=True.

## What cannot be concluded

- No model ranking, score or winner: one generation sample per role assignment.
- No truth claim about any generated interpretation, declared event or reviewer verdict.
- No claim about provider-side retention, deletion or training use; only local persistence was controlled.
- No generalisation beyond this registered corpus, roles and call plan; corpus completeness remains NOT_PROVEN.
- No operator-facing reading of any candidate content: this pilot intentionally does not learn what the advice said, only whether the frozen pipeline generated and reviewed something.

