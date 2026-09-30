# T-116 VERIFY — probe series and first green canonical run (E-1552 resume)

Active Work T-116, phase VERIFY resumed from E-1551 STOP. Goal: isolate which
executed predecessor state made `tests/test_quarantine.py::test_a_dense_body_scans_in_linear_time`
fail in the full suite, without touching product files or the 3x assertion.

## Probe results (in order)

1. Canonical collection: `python -m pytest --collect-only` = 2558 collected.
2. Full collection + `-k` predecessor (`test_a_normal_distribution_carries_identity_and_not_plaintext`)
   then dense test: 2 passed, dense PASS.
3. Standalone split timing (no in-window instrumentation; helper imported from
   the test module, measured in a separate script): `_dense_body` build is
   ~1-2 ms at both sizes; `q.scan` dominates (small ~0.022s, large ~0.050s,
   ratio ~2.3x over 5 trials, findings 2000/4000). Build time is not the
   effect; scan is the measured window.
4. Full collection + runtime-deselected canonical prefix through the last item
   of `tests/test_quarantine.py` (plugin `probe_deselect.py` in this directory;
   collection/import state byte-identical to the full run): 1651 executed,
   907 deselected, exit 0, dense PASS. No PASS->FAIL frontier anywhere in the
   canonical prefix.
5. Untouched full canonical suite, `python -m pytest -q`: exit 0.
6. Second untouched full canonical run with junit report, quiescence
   STATE/BOARD/LOG hashes identical before/after: **2558 tests, 0 failures,
   0 errors, 0 skipped; `test_a_dense_body_scans_in_linear_time` PASS,
   reported time 0.230s** (`full-canonical-green.xml/.txt`,
   `green-quiesce-before.txt`).

## Attribution

- Post-quarantine tests execute AFTER the dense test; they cannot causally
  affect its timing. The prefix with full import state passes; the pair passes;
  the build/scan split shows baseline ratio ~2.3x against the observed 4.9-5.5x
  only under the 00:43-01:05 machine load.
- The three E-1549/E-1550 failures (small=0.037s, large=0.181s) were
  single-sample wall-clock measurements of a ~0.18s CPU-bound scan under
  concurrent load. Today's runs pass even though other tests were ~2x slower
  than in the prefix run (e.g. alpha-release verifier 13.3s -> 26.1s), i.e.
  under heavier load than the failing window.
- Not attributable to T-116: `saimail/quarantine.py` and
  `tests/test_quarantine.py` untouched (protected hash check PASS:
  172 files, 0 changed, `protected-after.txt`). The 3x assertion was not
  weakened; no patch was made.

## Gate evidence

- Protected hash check: PASS, `{"protected":172,"changed":[],"result":"PASS"}`.
- Validator-after (`validator-after.json`, canonical `saipen validate --json`):
  4 problems / 23 warnings vs start baseline 5 / 23. The disappeared problem is
  the root-file-set drift naming the untracked orphan `SAIPEN_ENTRY.json`,
  removed outside this ticket (git: never tracked; absent at session start) —
  the remediation the finding itself prescribes. Zero new findings; 23 warnings
  identical; the four inherited problems unchanged.
- Final-byte review: T-116 changed set verified against the T-114 `before/`
  baseline — tests/test_repo_consistency.py is pure additive (class guard
  `STALE_OWNERSHIP`, `stale_ownership_claims`, ownership test, 5-case in-memory
  red control, T-113-closure recognition with tightened G13/G17/publication
  pins) plus line-ending normalization on identical blocks; humbox/CURRENT-STATE.md,
  humbox/FUTURE-GATES-V6.md, humbox/SAIPEN-WORK-DESK.md and the
  T-113-reread-continuation annotation defer active Work to STATE/BOARD/LOG and
  record T-114 DONE (E-1541). No stray bytes; red controls 12/12 (BUILD.md).

conf: high
