# T-117 VERIFY

Ticket check (prose): "the requested change is present and demonstrated against
the user own description of it". User description (SRC-106): continue by meaning,
humbox as the beacon. Humbox named exactly one next direction: evaluation of the
SAIPEN-owned turn-entry hook (bounded header-only awareness, receiver-owned
authority, zero automatic open). Demonstrated below.

## Harness (KNOWLEDGE/VERIFICATION.md: `python -m pytest -q`)

- Canonical full suite, quiescent, final product bytes:
  2567 passed / 0 failed / 0 errors / 0 skipped (`full-canonical.xml`, 172 s).
- After the last verifier edit (pinned `workspace.seat`), rerun on final bytes:
  2567 passed / 0 failed / 0 errors / 0 skipped (`full-canonical-final.xml`, 141 s).
- After the final doc-only edits: `tests/test_repo_consistency.py`,
  `tests/test_d3_release_candidate.py`, `tests/test_turn_entry_headers.py` green.
- Lint `ruff check --select E4,E7,E9,F` on touched Python: PASS.

## Instrument controls (VERIFY-ORACLE-01)

Verifier `tests/test_turn_entry_headers.py` sha256 `d71f75f6b053e5be...`.
Pre-fix subject: `before/workspace.py` `b7f3c14ccd6f9806...` (equals the T-114
protected hash) and `before/saimail_local.py` `520cc01e41a81b4d...`.
Post-fix subject: `workspace.py` `0540f8f63350d30a...`, `saimail_local.py`
`8aa88718c1818f79...`.

- Same verifier against the pre-fix subject (isolated copy): 7 failed / 1 passed.
  The passing one is the consumer-contract pin, which pre-fix bytes also satisfy.
- Same verifier against a marker-only header loader: both public-check parity
  controls fail.
- Same verifier against the post-fix subject: 8 passed.
- Known-good control: the 383 pre-existing focused workspace/custody/seam/GUI
  controls stayed green, and the full suite is green.

Output: `red-controls.txt`. Probe (`t117_probe_store_touch.py`): before
`secret_reads=2` and locked `CUSTODY_ACCESS_FAILED`; after `secret_reads=0` and
locked `OK match_count=1` (`probe-after.txt`).

## Live demonstration against the user's own description

Real SAIPEN route, read-only: `SAIMAIL_WORKSPACE=<scratch>/e2e/B
SAIPEN_AGENT=claude-account2 saipen status --json` -> `telegrams: state OK,
unread 2, on_current_work 1, complete true`, counts only, nothing opened
(`live-saipen-status-telegrams.json`). Without the carrier: `NOT_CONFIGURED`.

## Boundaries

- Protected boundary `t117_protect.py check`: 222 protected, 0 changed
  (frozen release trees and evidence, audio asset and manifest, VERSION,
  pyproject, Post Office/GUI code, frozen DECISIONS.md, T-113 tests, earlier
  evidence and receipts).
- SAIPEN validator: before 2 problems / 24 warnings; after 3 / 24. The one
  difference is `a58af6fb41bd66f5` `source_credential_unsafe` on SRC-017, the
  inherited finding present with the same key in T-114 and T-116 snapshots
  (absent from the T-117 baseline sample only). Zero new problem signatures
  against the inherited set.
- No SAIPEN tree edit. Cross-project findings filed in the SAIPEN protocol
  incidents inbox with an INDEX row (`SAIPEN-FINDINGS.md`).

conf: high
