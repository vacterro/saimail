# UI-003 -- refreshed V5-01 review pass against the current bytes

- reviewer: saiui (adopted in the Core session for T-128)
- date: 2026-09-25
- canonical authority: `<saipen_home>/saipen/UI.md`, sha256
  `66fb92db8a63404291fa09bdf941bb8dbeafcc8ecbb28387a35d111760490572`, 454 lines
  (re-hashed on current bytes at review start; UI-002 reviewed
  `162fa0574533456541b65fb79f1893fef863e9143aaab94ba99e0ea938ea5dd0`, 429 lines)
- source identity reviewed: `source_head`
  `3fa8f2295f564a6a75733905388ddee55b2f73b8`, `source_tree_fingerprint`
  `git-delta-v1:8b5376574aa5f803b4d48b6863a90b58aa658d9684c6b42332a8762015a5763f`
- role revision: `sha256:f2e3685b908a3b9837917f12c5414628d847c35fb72567f0306e2c8b19a8dab8`
  (charter unchanged)
- files verified: `saimail/gui_adapter.py`, `saimail/gui_app.py`,
  `saimail/gui_theme.py`, `tests/test_gui_surface.py`,
  `tests/test_gui_acceptance.py`, `spec/25-DESKTOP-LOCAL-MESSENGER-v0.md`

## Why this pass exists

UI-002 was rendered stale by evidence, not by age: its recorded tree
fingerprint is `git-delta-v1:2447ef10...` while the current tree computes
`git-delta-v1:8b537657...`. The canonical specification moved too, so a
re-run against the new bytes is the only honest way to keep a current
verdict.

## What actually changed, and what did not

The specification grew by 25 lines and changed hash. The Golden Default
`:root` block did not: re-parsed from the new `UI.md` it yields the same 21
names, the same 21 hex values, in the same declaration order, with 19
distinct values. The palette is therefore unchanged, and the theme module
still matches it exactly.

The product surface is unchanged in every subject this pass cites: the same
`gui_adapter.py`, `gui_app.py` and `gui_theme.py` are the live ones, and the
focused GUI suites grew from 43 to 46 cases, which is the only measured
movement on the implementation side.

## Method

Both sides of the token comparison were parsed, not read: the `:root` block
out of `UI.md` and `TOKENS` out of `gui_theme`, compared name by name and
value by value, plus order and distinct-value count. The 18 required checks
are re-asserted by the focused suites that carry them; where a check is a
code-reading claim rather than a test, it is unchanged in its subject and is
cited by its file and symbol.

## Measured evidence (this run)

| Check | Verdict | Evidence |
|---|---|---|
| Golden Default tokens exact | PASS | 21 canonical names, 21 values, 0 mismatches, declaration order identical, 19 distinct values |
| focused GUI suites | PASS | `python -m pytest tests/test_gui_surface.py tests/test_gui_acceptance.py` -> 46 passed |
| full repository suite | PASS | `python -m pytest -o addopts="" -q` -> 2639 passed, 0 failed, 0 errors, 0 skipped, exit 0 |
| vendored-asset condition | PASS | `tests/test_repo_consistency.py` -> 56 passed with `humbox/SAIGIMN.mp3` (6,851,614 bytes) still present and unignored, so the condition that had this suite red is no longer reproducing |
| 18 required checks | PASS | re-asserted by the 46 focused cases above; code-reading checks unchanged in subject |

## Recorded limitation (unchanged, still unprovable here)

Non-antialiased Verdana rendering. `UI.md` iron law 1 and the QA list require
it; a Qt style sheet cannot express smoothing hints, and no mechanism on this
host can prove the backend's choice. The module expresses the law as far as
the Qt surface permits and claims no rendering guarantee it cannot prove. A
real-display probe would be needed to settle it, and that is outside this
harness.

## Verdict

PASS. No UI violation found, no palette drift introduced by the
specification change, and no pen patch required. UI-003 is the current-source
review package; UI-001 and UI-002 are history.
