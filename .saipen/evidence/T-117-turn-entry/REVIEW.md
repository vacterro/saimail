# T-117 REVIEW

## Independent rerun of the ticket verify

- First REVIEW full run: 2566 passed / 1 failed. The failure is
  `tests/test_quarantine.py::test_a_dense_body_scans_in_linear_time`, the
  wall-clock ratio test T-116 already attributed to load
  (`small=0.033s large=0.151s`, bound 0.149 s). T-117 diffs do not touch
  quarantine code or that test; the test passed isolated 5/5.
- Second quiescent REVIEW full run: 2567 passed / 0 failed / 0 errors /
  0 skipped (`review-full-2.xml`; dense test 0.167 s PASS). STATE/BOARD/LOG hash
  identical before and after both runs (`594611ae553e0be7`).
- Verdict on the verifier: the timing test is unstable under load, not a T-117
  regression; its assertion is untouched.

## What the diff did to the check

- New verifier `tests/test_turn_entry_headers.py`; its pre-fix FAIL was recorded
  with the SAME command and bytes (`REGRESSION-EVIDENCE FAIL verifier:895d38f5261c1aaf
  subject:6f9def08fac03bbd`, PASS against `subject:ec7427b95233e021`).
- `tests/test_repo_consistency.py`: additive only (0 lines removed, 40 added;
  `test_repo_consistency.diff`). No existing assertion, fixture or command moved.
- The verifier can still see the bug: the store-guard and locked-store controls
  fail on the restored pre-fix loader; a marker-only loader fails both parity
  controls.

## Final-byte code review

- `load_workspace` keeps its order of checks and every message; the raw private
  derivation and the os-store retrieval run exactly as before.
- `load_workspace_headers` shares `_read_durable_identity`, so the two loads
  cannot disagree on public well-formedness; it constructs only
  `X25519PublicKey` from the marker.
- The Post Office is built from the same public registries in both paths. Its
  constructor only `mkdir(exist_ok=True)`s mail directories, as before.
- Confidentiality: index rows were always plaintext on disk and were always
  read without a private key; the header view exposes nothing new. A copied
  os-store workspace without the store still cannot `load_workspace` (spec/20
  property intact); it can now list headers, which its files already reveal.
- CLI: only `inbox` and `saipen telegrams|enter|brief` switched; `open`,
  `reopen`, `reply`, `send`, `saipen telegram`, `saipen init` keep the full
  load (structural oracle in `test_repo_consistency.py`).

## Findings

No P0/P1. No P2/P3 inside SAIMAIL scope. Three SAIPEN-side findings are filed
for the protocolist (`SAIPEN-FINDINGS.md`), not SAIMAIL tickets.

Memory promotion: NO (the lesson is recorded as D-059 and in code; the timing
flake is generic and already recorded by T-116).

Verdict: DEC: SHIP.
