# T-87 / T-86 / V2-04 closure evidence

The final external-install gate is satisfied for the original frozen
`0.0.2a1` candidate. No product implementation or candidate rebuild belongs
to this closure. Publication: NONE.

## Evidence lineage

- T-86 / SRC-073 created the scoped local alpha and preserved its original
  local Windows / Python 3.11.9 evidence under `release/evidence/`.
- T-87 / SRC-074 was blocked solely because the completed external proof was
  unavailable. The original blocker events E-1041/E-1042 remain in LOG.
- The current operator closure request is captured as SRC-075, amending
  SRC-074. The operator supplied the original artifact path separately.
- Original, unchanged:
  `.saipen/evidence/SAIMAIL_V2-04_external_linux_verification.json`.
- Byte-identical evidence copy:
  `release/evidence/SAIMAIL_V2-04_external_linux_verification.json`.
- Proof SHA256:
  `819f3fcf445c051aec20864098960ccb37a69c8ce6aced0872f2198a96b95f94`.
- Independently hashed frozen wheel SHA256:
  `ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a`.
- Read-only mechanical check: `python release/evidence/check_external_proof.py`.
  Recorded result: `release/evidence/external_proof_acceptance.json`.
  This record also pins all five frozen bundle files for closure comparison.

## External result

`LOCAL_ALPHA_VERIFICATION_1 v1 PASS`, failures `[]`, verified externally at
`2026-09-20T17:47:02Z` on **Linux / Python 3.13.5**. Installation is INSTALLED;
all three module paths resolve inside the external installed environment.
The original source artifact, not the malformed chat rendering, was parsed
strictly: UTF-8, duplicate-key rejection, non-finite-value rejection, one JSON
document, and exact field types (including booleans versus integers).

| Gate | External evidence |
|---|---|
| FG-05 | LOCAL_SCENARIO_RESULT_1 / PASS |
| FG-06 | FG06_UTILITY_RESULT_1 / UTILITY_CONDITIONAL |
| V2-01 acceptance | LOCAL_WORKSPACE_RESULT_1 / PASS |
| Direct workspace command | LOCAL_WORKSPACE_COMMAND_1 / CREATED |
| Privacy | PASS; findings []; private_key_material_found false |
| Runtime counters | network_attempts 0; model_calls 0; provider_calls 0 |
| Candidate | 0.0.2a1; NOT_PUBLISHED; exact frozen wheel hash |
| API/version/limitations | Match the frozen candidate and acknowledged limitations |

The Linux result is additional successful external evidence only. The frozen
manifest continues to advertise its original CPython 3.11 / win32 proof scope.
No manifest, wheel, bundled verifier, checksums or bundled README was changed.

## Verification

- Focused release/integrity/repository checks: **40 passed**, 15.33 s,
  `T87-focused.xml`. Release tests build disposable fixtures; the original
  frozen candidate is never rebuilt or overwritten.
- After updating navigation, two existing repository checks exposed omitted
  literal historical completion markers. Restored the true markers, with no
  test changes. First full run retained in `T87-full-suite-first.xml`:
  2121 passed, 2 failed. Final repository checks: **33 passed**, 0.35 s,
  `T87-repo-consistency.xml`.
- Final full suite: **2123 passed, 0 failures, 0 errors, 0 skipped**, 64.07 s,
  Python 3.11.9 / win32; `T87-full-suite.xml`.
- Frozen bundle integrity: PASS, including exact wheel bytes, content digest,
  checksums and version surfaces. Both bundle and evidence privacy scans PASS;
  `T87-bundle-privacy.json`, `T87-evidence-privacy.json`.
- Checker controls: duplicate key, NaN, trailing document and missing braces
  rejected; wrong expected proof hash refused with
  `EXTERNAL_PROOF_CANDIDATE_MISMATCH`; original artifact accepted.
  `T87-checker-controls.json` preserves the results.
- `ruff check release/evidence/check_external_proof.py`: PASS.
- All five frozen bundle file hashes and Roadmap v1 SHA256 remain unchanged.

## SAIPEN validation

Inherited baseline: **3 FAIL / 22 WARN**. This turn observes **3 FAIL / 21 WARN**,
already at the first validation. No warning repair is claimed. The same three
carried failures remain: SRC-017/T-41 source linkage, SRC-036 source credential
gate, and stale improve-report fingerprint. No new T-87/T-86/V2-04 failure.
Global SAIPEN validation is still FAIL, not a clean bill of health.

Evidence: `T87-validation-before.json`, `T87-core-validation.txt`,
`T87-core-findings.json`, `T87-validation-comparison.json`; final closure
validation is recorded separately as `T87-T86-final-validation.txt` and
`T87-T86-final-findings.json`.

## Scope and stop boundary

`CURRENT-STATE.md` and `FUTURE-GATES-V2.md` now select V2-02 next, NOT STARTED.
V2-01 and V2-04 are DONE; V2-03 is optional, NOT STARTED. No experiment was
started. No commit, tag, push, publication or wider platform claim occurred.
No operator action remains for the external gate. NEXT_EXACT_ACTION: NONE / STOP.

Canonical lifecycle and source closure are recorded in `.saipen/LOG.md`,
`.saipen/BOARD.md` and `.saipen/STATE.md` through SAIOPS operations.

- T-87 unblocked at E-1043, proof accepted and reviewed through E-1055.
- The full continuation receipt SRC-075 includes T-86 closure. Its final clause
  stayed pending while the canonical dependency operation temporarily parked
  T-87 at E-1057 and ran T-86; no human action or new task was required.
- T-86 finished at E-1069; SAIOPS automatically resumed T-87 in SHIP at E-1070.
- After recording the completed cross-ticket clause, T-87 finished at E-1072.
- SRC-073, SRC-074 and SRC-075 are CLOSED and archived with their source hashes
  and coverage retained. Both BOARD rows are DONE; STATE is DONE / task none.
