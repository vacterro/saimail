# T-116 STOP checkpoint (operator `saipen stop`)

- Active Work: T-116 (SRC-105), phase VERIFY. Not closed.
- Changed files (final, reviewed): humbox/CURRENT-STATE.md,
  humbox/FUTURE-GATES-V6.md, humbox/SAIPEN-WORK-DESK.md,
  .saipen/kitchen/T-113-reread-continuation.md (annotation line only),
  tests/test_repo_consistency.py. Details: BUILD.md.
- Truth classification: SCOUT.md. No A-class stale ownership remains in the
  recovery docs (guard green); B/C history untouched.
- Red controls: 12/12 detected (red-controls.json), bytes unchanged.
- Focused: reread 25, gui-surface 43, gui-acceptance 3, repo-consistency 49 =
  120 PASS. Lint (ruff E4,E7,E9,F) PASS.
- Full suite: NOT YET PASSING. Three quiescent canonical runs (STATE/BOARD/
  LOG hashes identical before/after each): 2557 passed / 1 failed / 0 / 0
  each (full-first.*, full-second.*, full.*). Same failure every time:
  `tests/test_quarantine.py::test_a_dense_body_scans_in_linear_time`
  (large/small wall-clock ratio ~4.9–5.5 vs bound 3.0x+0.05s).
- Attribution analysis so far:
  - quarantine.py/test_quarantine.py untouched since 2026-09-20 (hash-protected);
  - the test runs at index 1645, before every T-116 test (1818+);
  - isolated 5/5 PASS; module alone PASS; full collection with only that test
    selected PASS; GC heap probe (3M objects) ratio ~2x (flake-gc-probe.txt);
  - suite prefix up to and including test_quarantine (no T-116 tests):
    run 1 = 1651 tests, 0 failures, dense test 0.138s (flake-prefix.txt).
    Prefix run 2 was stopped by the operator's `saipen stop`.
  - T-114 full run passed this test at 0.148s.
  Open question: why the full run fails consistently while the identical-order
  prefix passes. Candidate: state from full-module collection plus the prefix run
  (collection of later modules alone passed). Not yet attributable to T-116; do
  not weaken the test.
- Protected-hash check (t116_protect.py check) and validator-after: NOT YET RUN.
  Validator start baseline 5/23 (validator-before.json; 5th = SAIPEN-home
  root-file-set drift predating T-116).
- Cross-project finding recorded: FINDING-SAIPEN-DIGEST.md.
- Remaining attributable finding: none known. Open blocker: canonical full
  suite not green (the test above).

Next exact action: run the full-suite-order bisection. Suggested: run the full
test list with `-p no:randomly` if present, first minus the modules after
test_quarantine, which already passed; then the full list minus
test_repo_consistency.py. Settle attribution, get a quiescent green canonical
run, then `python .saipen/kitchen/t116_protect.py check`, `saipen validate
--json` > validator-after.json and compare signatures, final-byte REVIEW, SHIP
(no publish), finish.
