# V2-04 review (T-86) — release-boundary checklist

Independent inline review after VERIFY. The ticket's own verification was
re-run here, not read: `tests/test_local_alpha_release.py` 7 passed,
`local_alpha_release.py verify` PASS (wheel sha256
`ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a`), privacy
scan PASS on the bundle and on `release/evidence/`.

| # | Review area | Result |
|---|---|---|
| 1 | Accidental checkout dependency | Clear. `verify_local_alpha.py` is stdlib-only and AST-checked; the verifier resolves modules inside the fresh venv and runs from a work dir outside the checkout. |
| 2 | Wrong package content | Clear. 57-member wheel; required runtime files present; `lab/out`, `lab/analysis`, `lab/history` absent. |
| 3 | Version drift | Clear. `0.0.2a1` agrees across pyproject, VERSION, entrypoint fallback, stable API map, wheel METADATA and manifest; consistency test enforces it. |
| 4 | Result-schema mutation | Clear. `LOCAL_SCENARIO_RESULT_1`, `FG06_UTILITY_RESULT_1`, `LOCAL_WORKSPACE_COMMAND_1`, `LOCAL_WORKSPACE_RESULT_1` unchanged and re-proved from the installed candidate. |
| 5 | Unbounded report output | Clear. Evidence files are 163 B – 2.6 KB; the verifier emits bounded fields plus a failures list. |
| 6 | Secrets in release artifacts | Clear. Privacy scan PASS; red control FAILs on a planted marker; no private key material in the manifest or results. |
| 7 | Plaintext persistence | Clear. No runtime change; the V2-01 acceptance privacy checks still pass from the installed wheel. |
| 8 | Mistaken network/service claims | Clear. Docs state local filesystem only; runtime counters zero; dependency installation reported separately. |
| 9 | Hidden cwd dependence | Clear. Workspace commands take explicit `--workspace`; acceptance takes `--root`; verifier uses an explicit work dir. |
| 10 | Missing crypto dependency | Clear. `crypto` extra declared and exercised; verifier records dependency source and supports `--offline`. |
| 11 | Broken clean install | Clear. Fresh venv install from the frozen wheel PASS, outside the checkout. |
| 12 | Verifier trust model | Clear. It hashes the actual wheel, re-derives the member content digest and checks every `SHA256SUMS.txt` entry before installing; corruptions are rejected. |
| 13 | Same-host evidence mislabeled | Clear. No external claim is made; the state is `READY_FOR_EXTERNAL_INSTALL_PROOF` with one bounded request. |
| 14 | Accidental publication commands | Clear. No commit, tag, push, upload or release; tags unchanged. |
| 15 | Overly broad platform claims | Clear. Platform proof scope is CPython 3.11 on win32, stated in manifest and spec. |

## Observations (not defects)

- Wheel bytes vary across rebuilds because setuptools stamps generated
  dist-info members with build-time timestamps; member content is identical
  across two clean builds and to the frozen wheel, and this is documented in
  `reproducibility.json` rather than faked as byte equality.
- The worktree is dirty and no commit identifies the candidate; the manifest
  records that and the exact wheel SHA-256 is the candidate identity.

## Verdict

`DEC: SHIP` — no P0/P1 findings. P2/P3 follow-ups: none required; the external
environment proof is the only open gate and stays a blocked operator action.
