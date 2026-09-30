# PROJECT CORPUS PILOT REPORT 20260919T212833Z

Status: REAL PROJECT CORPUS PILOT (B-018 / SRC-051). One immutable
registration was frozen before capture; one BuiltProjectCorpus was minted
through the B-017 builder; no live model, network, mail or attention path
was invoked.

## Exact selection

- PROJECT_SCOPE = project:saimail
- WINDOW_START = 2026-09-19T19:30:00Z
- WINDOW_END = 2026-09-19T21:20:00Z (half-open: START <= OBSERVED_AT < END)
- SELECTION_BASIS = EXPLICIT_BOUNDED_SET
- COMPLETENESS = NOT_PROVEN
- expected artifacts = 8, built = 8
- expected events = 5, built = 5
- lab snapshot = project_corpus_pilot_20260919T212833Z.json

## Identities

- REGISTRATION_ID = sha256:dfd8b48dded34de8426181f309032da31c86e83f675412add15076fc421a096f
- BUILD_ID = sha256:0e05460aae1645b6bdfeec887f02a978a185026422faf74c90238f0938bd4e35
- CORPUS_ID = sha256:b009bdf3a8efd28f29be76d0dfd9c2809c0e7dd010af8e92c94a97fbeeec19ac

## Artifact mappings (A1..A8)

| label | source kind | source ref | observed at | source | evidence ref | event |
|---|---|---|---|---|---|---|
| A1 | SPEC_DECISION | decision:D-047 | 2026-09-19T19:32:00Z | spec/DECISIONS.md | sha256:0c4d8190d42036d5e43d11fe2dd2a2510e20118b28f0ad26091adc680e1dca6b | sha256:f838da4914db0597df13da821cb5e3187e7d20a3284f857e6ac66095f0093aab |
| A2 | TEST_RESULT | saipen-log:E-715 | 2026-09-19T19:32:00Z | .saipen/LOG.md | sha256:470467bf49b1609e5ffc5cf33a71ceadc8a49462b0864b36c54f7b1c5b5d9db4 | sha256:f838da4914db0597df13da821cb5e3187e7d20a3284f857e6ac66095f0093aab |
| A3 | SPEC_DECISION | decision:D-048 | 2026-09-19T19:48:00Z | spec/DECISIONS.md | sha256:25cf1d478c1fb0b930e6336f1ab41df98c9e03f06cee00225565ddb1bb99928a | sha256:c3a72d9c171876a8b5bfbf6f636c9730e46b0953ba06381b7743346174637b57 |
| A4 | TEST_RESULT | saipen-log:E-726 | 2026-09-19T19:49:00Z | .saipen/LOG.md | sha256:f8042d041c400a6fac9d692087e09db84b90adfeeb966676d7881f75111d9cd5 | sha256:c3a72d9c171876a8b5bfbf6f636c9730e46b0953ba06381b7743346174637b57 |
| A5 | REVIEW_FINDING | lab-report:ALLY_GENERATION_REPORT_20260919T201826Z_2a73d98de110453a | 2026-09-19T20:18:26Z | lab/out/ALLY_GENERATION_REPORT_20260919T201826Z_2a73d98de110453a.md | sha256:ddfdbb5ef8ff1df279496a3e13d906495f06e343c0b30fe6af6b0bd1d3e9ca21 | sha256:10677f09d37904702cb4f6817838ae768171ae9db8c285d9f88d9bf4aff43915 |
| A6 | SPEC_DECISION | decision:D-049 | 2026-09-19T20:46:00Z | spec/DECISIONS.md | sha256:98afe4373bceb06a635b441723cc4772fcd8ddac1768a5ca7de54a8cf8c2152d | sha256:6016dfd42c8d9c655bf5ca19726ba706499e00d5bf897845f8523f2c0ee4fe9f |
| A7 | SPEC_DECISION | decision:D-050 | 2026-09-19T21:16:00Z | spec/DECISIONS.md | sha256:e0649c6f4971f41c91937c85bf1b76d7a6e4cd739c8ccc0f47fe2b15c888bb5c | sha256:77b3cc53850a1e942cd4fe5043fdf59dc56c10c4aa945f8db5cb4c0fca2daa4f |
| A8 | TEST_RESULT | saipen-log:E-779 | 2026-09-19T21:17:00Z | .saipen/LOG.md | sha256:77a0bf1f67abe52a7be10af84746adb20db8762e7a0a2ca6ddb193d1cd58cc92 | sha256:77b3cc53850a1e942cd4fe5043fdf59dc56c10c4aa945f8db5cb4c0fca2daa4f |

## Event mappings (P1..P5)

| label | name | members | event ref |
|---|---|---|---|
| P1 | B016_INITIAL_GENERATION_GATE | A1, A2 | sha256:f838da4914db0597df13da821cb5e3187e7d20a3284f857e6ac66095f0093aab |
| P2 | REVIEW_INVOCATION_AUTHORITY_CORRECTION | A3, A4 | sha256:c3a72d9c171876a8b5bfbf6f636c9730e46b0953ba06381b7743346174637b57 |
| P3 | SYNTHETIC_LIVE_GENERATION_EXPERIMENT | A5 | sha256:10677f09d37904702cb4f6817838ae768171ae9db8c285d9f88d9bf4aff43915 |
| P4 | EVENT_INDEPENDENCE_CORRECTION | A6 | sha256:6016dfd42c8d9c655bf5ca19726ba706499e00d5bf897845f8523f2c0ee4fe9f |
| P5 | REAL_PROJECT_CORPUS_BUILDER | A7, A8 | sha256:77b3cc53850a1e942cd4fe5043fdf59dc56c10c4aa945f8db5cb4c0fca2daa4f |

## Grouping limitation

These five event declarations are explicit operator-authorized grouping
for this pilot. They do NOT prove:

- those are objectively the only events;
- P1..P5 are causally independent;
- one ticket always equals one event;
- every relevant occurrence was selected;
- the grouping proves any behavioural pattern.

Preserved: EVENT_REF_IS_TRUTH = false. COMPLETENESS is NOT_PROVEN and no
claim in this report describes the selection as complete or representative.
This pilot is deliberately narrow: not all SAIMAIL history, not all relevant
project evidence, not all failures, not all successful work, not all
operator behaviour and not a personal profile.

## Source hash pins and capture exactness

| source | source file sha256 |
|---|---|
| .saipen/LOG.md | sha256:b4095f9cf91f9b9e6643c891a2dc68a2b822b7c3945708c7315f05b8b9ca2dd6 |
| lab/out/ALLY_GENERATION_REPORT_20260919T201826Z_2a73d98de110453a.md | sha256:d56267a875899e09f0836b21d24a914b097aac13971bd8e99755bd2f5883c9ab |
| spec/DECISIONS.md | sha256:9fc9a54a9fc906224a94c1a6c0d8ca668a7463a957663ded0e5a89182e0a1ba6 |

Every artifact's extracted content hash equals its frozen registration pin;
the A5 whole-file capture is the exact registered report bytes below the
B-017 per-item ceiling (no markdown normalization, no newline rewriting).

## Reproducibility

Deterministic rebuilds (same process and two fresh processes) reproduce the
same evidence-ref mapping, event-ref mapping, BUILD_ID and CORPUS_ID; the
pilot refuses to build at all when a registered source or selected content pin
changed. Temporary fixture mutation controls live in the focused tests; the
real registered sources were re-hashed unchanged after the pilot run.

## Mutation controls (focused tests, temporary fixture copies only)

- one byte changed in the registered D-047 section -> old registration refuses (PROJECT_PILOT_SOURCE_CHANGED);
- the E-726 LOG record modified -> old registration refuses;
- moving A8 into P4 changes the event-ref mapping, BUILD_ID and CORPUS_ID;
- removing A4 refuses (registered count is a frozen exact shape);
- OBSERVED_AT = WINDOW_END refuses (PROJECT_CORPUS_WINDOW_EXCLUDED);
- an unknown source kind refuses (PROJECT_CORPUS_SOURCE_KIND_UNKNOWN).

## B-016 structural compatibility

The real BuiltProjectCorpus.reflection_corpus accepted a deterministic fake
candidate citing evidence from two declared events and reached the semantic
reviewer; a fake candidate whose observed refs came from one declared event
was refused with ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS and zero reviewer
calls. A raw ReflectionCorpus still fails the future-pilot proof gate with
PROJECT_CORPUS_BUILDER_PROOF_REQUIRED, and the generic B-016 path is
unchanged.

## No-model / no-network proof

No model adapter, SAIFREN transport, 9router transport, socket or HTTP path
exists in the pilot module or was invoked by it: 0 live calls. The artifact
and this report are deterministic projections; the in-process
BuiltProjectCorpus type-state, not the JSON, is the proof.

## No mail / attention side effect

0 calls to reviewed_ally_to_human_private, seal_human_private,
HumanPrivateStore.deliver and AttentionQueue.admit_receiver_candidate; no
HLET1, no HENV1, no human-attention state.

## Source immutability

The pilot observes history and does not rewrite it: pre-capture and
post-capture source hashes are identical and equal to the registered pins.
The T-63 historical report was read read-only and remains byte-identical.

## What this run does not show

No completeness, no semantic pattern, no user or personality claim, no
EVENT_REF truth claim and no model-quality claim. The corpus is tested as
data-provenance infrastructure only.
