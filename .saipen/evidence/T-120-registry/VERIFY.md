# T-120 VERIFY

- First canonical run: 2606 passed, 1 red:
  `tests/test_turn_entry_headers.py::test_header_view_results_equal_the_full_load_results`
  -> `SAIPEN_SEAT_MISMATCH: acting seat claude-account2 ...`. Cause: the runner
  shell had `SAIPEN_AGENT` exported for the SAIPEN checkpoint commands, and the
  T-117 control lacked the `_no_ambient_actor` fixture its neighbours have. A
  latent T-117 test-hygiene defect: any agent running the suite under SAIPEN with
  a seat carrier would see it. Isolated reruns 3/3 green in a clean environment.
- Fix: autouse `_no_ambient_actor` fixture in `tests/test_turn_entry_headers.py`
  (assertions unchanged).
- Canonical `python -m pytest -q`, clean environment: 2607 passed / 0 failed /
  0 errors / 0 skipped (`full-canonical.xml`).
- Same suite with `SAIPEN_AGENT=claude-account2` exported: 2607 passed / 0 failed
  (`full-with-carrier.xml`), proving the suite no longer depends on the carrier.
- Red controls: five participant mutants caught (`red-controls.txt`).
- conf: high
