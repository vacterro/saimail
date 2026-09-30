# T-114 VERIFY checkpoint — stable-source retry

Active Work T-114, phase VERIFY. Final changed-file set is now nine files:
the eight in BUILD.md plus `.saipen/kitchen/T-113-reread-continuation.md`,
which received only a later-closure annotation; original historical text remains.
Exact final bytes and protected hashes are in final-bytes.json / final.diff.

Focused 151 passed / 0 failed / 0 errors / 0 skipped; lint PASS.
First canonical full suite: 2551 passed / 1 failed / 0 errors / 0 skipped.
Failure: test_reviewer_structured_output::test_candidate_prose_and_canary_are_not_durable,
PROJECT_PILOT_SOURCE_MUTATED. This is a real failed mandatory pass, not a PASS.
`lab/project_corpus_pilot.py` capture_registered_artifacts hashes registered
sources before and after capture and refuses any concurrent mutation. The
registration includes `.saipen/LOG.md`; this run overlapped our E-1531/E-1532
checkpoint writes. Thus the observed source-change guard is consistent with
our concurrent checkpoint, not evidence requiring a product change. Exact
failed output/XML preserved as full-first.* and full-first-result.json.

Changed verification condition: complete checkpoints before the retry; no
STATE/BOARD/LOG/source mutations while pytest runs. Rerun the failed test in
isolation, then the exact full command against a quiescent checkout. No test,
fixture, registration, historical artifact, product code or oracle is weakened.

Canonical validator after repair: 4 inherited problems / 23 warnings, zero
new problem signatures (validator-delta.json). All 90 protected hashes match;
all GuiAdapter executable function ASTs are identical (docstrings excluded).
Remaining attributable finding: none in product; full validation is outstanding.
Next exact action: stable-source focused failure check then canonical full suite.
