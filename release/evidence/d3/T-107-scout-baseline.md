# T-107 SCOUT baseline

Date: 2026-09-23
Ticket: T-107
Sources: SRC-095, SRC-098, and implementation append SRC-100
Candidate version: 0.0.2a3

This ticket resumed after T-108, T-109, and T-110 reached DONE. Existing T-107
code and evidence are inherited partial implementation from before those
interruptions. They are not closure evidence. The working tree already
contains extensive pre-existing untracked project files; none were discarded.

## Frozen candidate identities before repair

| Candidate | Wheel | SHA-256 |
| --- | --- | --- |
| a1 | `saimail-0.0.2a1-py3-none-any.whl` | `ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a` |
| a2 | `saimail-0.0.2a2-py3-none-any.whl` | `d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d` |
| a3 | `saimail-0.0.2a3-py3-none-any.whl` | `6427feab24c310184e7fd3ec4bb33dc3f5b1581b00128e2ec08d456fa5aa10cc` |

The a3 manifest also records 65 members and normalized content digest
`2f75bdb7d421a6838b8ab292f667a85bb51e207017f0760caf71c9c1e59c061d`.
The three on-disk wheel hashes matched these identities before repair.

## Independently reproduced open findings

- **P1-A, G13 acceptance:** the production `cmd_gates` accepts `status: PASS`
  plus the exact `candidate_sha256`. A temporary two-field acceptance object
  passed the real CLI and produced `PASS / DONE`.
- **P1-B, G15/G16 evidence:** G15 reads only `status`/`result`; G16 checks only
  new attributable failures and problem count, ignoring schema, a3 identity,
  contradictory test counts and warning regression. The real CLI accepted a
  fake zero-test suite with failures/errors, wrong-candidate SAIPEN data with
  999 warnings, and the two-field G13 object, producing `PASS / DONE`.
- **P1-C, G14:** the production gate hard-codes documentation as PASS.
- **P1-D, external acceptor:** the acceptor requires Linux, `/tmp/` paths, and
  raw top-level `publication: NONE`. The frozen verifier emits `sys.platform`,
  paths rooted in its fresh platform-native virtual environment, and
  `candidate.publication_status: NOT_PUBLISHED`; it emits no raw top-level
  `publication` field.
- **P1-E, production-path tests:** the G15/G16 red-control test reimplements
  gate decisions in a local `_evaluate` helper instead of invoking `cmd_gates`.
- **P1-F, stale evidence:** final suite evidence still claims 2,398 tests while
  T-110's canonical run at E-1412 recorded 2,477. Gate time is
  `2026-09-22T17:56:50Z`, earlier than the consumed suite record's declared
  `2026-09-22T19:00:00Z`. SAIPEN evidence still uses the older 3/21 baseline;
  current status carries a stale receipt with 4 problems and 23 warnings.
- **P1-G, recovery documentation:** current sections in CURRENT-STATE and
  Roadmap v6 still call D3 ACTIVE via T-106 and defer V6-02 while D3 is active,
  alongside newer corrective text. The external request prematurely claims
  T-107 repair complete.
- **P1-H, repository consistency:** `humbox/SAIGIMN.mp3` exists at 6,851,614
  bytes, is untracked and not ignored, and predates this repair by its file
  timestamp. The focused consistency suite fails at this asset. Its origin is
  not proven; preserve it and classify it as unrelated until an authorized
  disposition exists.

## Baseline verification

- Focused `tests/test_repo_consistency.py`: one failure, solely on
  `humbox/SAIGIMN.mp3`; the remaining collected tests passed.
- Real production-gate red control: fake G13, G15, and G16 evidence returned
  exit code 0 and `PASS / DONE`; all inputs and output were temporary files.
- a1, a2, and a3 wheel bytes are unchanged at this baseline. Recompute all
  three hashes after repair and compare them with the values above.
- No external proof was accepted or created. Publication remains `NONE`.
