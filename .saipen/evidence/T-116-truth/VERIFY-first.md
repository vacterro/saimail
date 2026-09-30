# T-116 VERIFY — first canonical run (FAIL, retained)

Active Work T-116, phase VERIFY. Focused: reread 25, gui-surface 43,
gui-acceptance 3, repo-consistency 49 (was 43 at T-114: +1 class-guard test,
+5 parametrized in-memory red controls) = 120 passed / 0 failed.

First canonical `python -m pytest -q`: 2558 collected, 2557 passed /
1 failed / 0 errors / 0 skipped (full-first.txt/.xml, full-first-result.json).
STATE/BOARD/LOG SHA256 identical before and after the run (quiescent; no
PROJECT_PILOT_SOURCE_MUTATED).

Failure: `tests/test_quarantine.py::test_a_dense_body_scans_in_linear_time`
— `small=0.037s large=0.181s`, bound `small*3.0+0.05 = 0.161s`. This is a
single-sample wall-clock ratio measured under full-suite load. It is not
attributable to T-116: `saimail/quarantine.py` and `tests/test_quarantine.py`
are outside the changed set, and saimail/*.py are in the hash-protected set.
Isolated rerun: 5/5 PASS (flake-isolation.txt). The test is not weakened.

Next exact action: retry the exact canonical command with zero concurrent
STATE/BOARD/LOG/source writes; if it fails again, stop and investigate.
