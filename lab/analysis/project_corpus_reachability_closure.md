# T-71 reachability closure

All three sequential targets are complete. The one registered live experiment
used the unchanged B-018 corpus and requested T-69 routes. Semantic-review
reachability was **not demonstrated**: R1 failed strict JSON parsing; R2 returned
NO_ADVICE. This is a completed measurement with a negative reachability result.

## New observation, bounded interpretation

R1 requested SAIFREN and reported deepseek/deepseek-v4-flash. Its parser input
was 1525 UTF-8 bytes, began with an object token, contained no fence token, and
failed JSON syntax at character position 1379 (line 1, column 1380). The gateway
reported finish_reason=length; the inherited local 4000-character cap did not
truncate it. These are separate observations. They do not establish the exact
missing token, full original output, or a causal diagnosis of provider behavior.
Schema-field counts remain unavailable because complete JSON was not decoded.

R2 requested goat/MiniMaxAI/MiniMax-M3 and reported MiniMaxAI/MiniMax-M3. Its
22-byte object passed strict parsing as NO_ADVICE. No reviewer was called.

Budget: four actual calls (two fixed-route probes, two generators), within the
six-call ceiling. Two role assignments were executed. No retry, repair, replacement
or second experiment occurred. The immutable attempt marker is terminal even
after a crash or refusal. No further live execution belongs to this wave.

The historical T-69 R1 shape is still UNKNOWN. Its discarded 3218 bytes are not
reconstructed from this new result. T-69's three historical file hashes match the
SCOUT baseline. T-70's correction and the production parser/gates remain unchanged.

## Reproducibility and privacy evidence

- Contract: `spec/11-STRICT-SCHEMA-OBSERVABILITY-v0.md`.
- Registration: `lab/project_corpus_reachability_registration.json`, SHA256
  `825c0853dc1a5cd73939bbf91201fb1e4f8a8b40a62e0d69a87d0fcd6be7dc16`.
- Live artifact: `lab/out/project_corpus_reachability_live.json`, SHA256
  `a9c7905af2d8b4a79849e811637946411c47c977c51a99cc8788b2ff75dff43b`.
- Machine-generated report: `lab/out/PROJECT_CORPUS_REACHABILITY_REPORT.md`.
- Independent read-only audit: `.saipen/evidence/T-71-artifact-review.json`.
- Single-attempt marker: `.saipen/evidence/T-71-reachability-live-attempt.json`.

Dry controls used the real corpus locally and deterministic fake outputs through
the same parsers: R1 APPROVED with one reviewer call, R2 NO_ADVICE with zero.
Dry network calls: zero. The saved dry proof, live marker and live artifact agree
on observer/harness hashes. The test matrix exercises malformed generator/reviewer
outputs, duplicate/unknown/missing fields, wrong types and identities, outside
refs, the one-event floor, FAIL/UNKNOWN, authentication stop, observer failure,
and refusal of a second live attempt. The privacy gate's disabled-boundary RED
control leaks its canary as expected; the enabled boundary refuses persistence.

`python -m pytest -q`: 1677 passed (pre-live full suite).
Post-live focused command over `test_parse_shape`, `test_project_corpus_reachability`,
`test_project_corpus_generation_pilot` and `test_project_corpus_generation_privacy`:
129 passed. Ruff on the four new Python files: PASS. Protected-file audit:
36 unchanged files; zero corpus-content or long corpus-line matches in new
artifacts/reports. No original test oracle was changed by this wave.

Local output remains structural metadata. No prompt, corpus content, generated
advice, reviewer rationale or provider error body is persisted by this experiment.
No HUMAN_PRIVATE mail, sealing, storage or attention call is made. Provider-side
retention and training use remain NOT_VERIFIED_BY_SAIMAIL. One sample per route
does not support model rankings, corpus completeness or truth claims.

## Carried validation debt

SCOUT: `.saipen/evidence/T-71-validation-baseline.json`.
Post-live: `.saipen/evidence/T-71-validation-postlive.json`.
The exact failure lines are unchanged:

1. `FAIL: source receipts -- DONE Work T-41 has unresolved source receipt SRC-017`
2. `FAIL: source receipts -- source credential gate: SOURCE_CREDENTIALS_UNSAFE credential pattern in exact active source SRC-036; supply a user-authorized replacement or amendment before release`

Verdict: **CURRENT_FAIL / CARRIED_DEBT_UNCHANGED**, not VALID.
DEBT-000066 is carried; no new validation failure was introduced. T-65 and T-34
were not resumed. No historical receipt was rewritten. No commit, tag, push or
publication was performed. Stop after local closure.

Closure bookkeeping note: canonical `stop` at E-834 set `next_action` to
`saipen continue`, introducing an audit-route mismatch only after T-71 became
DONE. E-835 corrected this wave's new routing field through the existing journaled
checkpoint planner. The dormant audit route is recorded but was not executed;
the user's STOP remains in force. This does not repair either carried failure.
The transient failure and correction are retained in
`.saipen/evidence/T-71-closure-routing-correction.json`.
