# T-97 / V5-01 — Desktop Local Messenger Alpha — closure

Status: DONE. Source: `SRC-085`
(`V:\_TEMP_\fastprompter_drag\SAIMAIL_20260921_0138.md`), the operator's new
explicit product goal for a GUI desktop local messenger.

## Rewards / outcome

- **NEW_OPERATOR_GOAL:** desktop local messenger GUI.
- **ROADMAP_V5:** `humbox/FUTURE-GATES-V5.md` created by T-97; V5-01 selected
  and then DONE; no next V5 gate selected (evidence: no usability gap observed
  in V5-01 beyond the honest READ-reread gap, which is a backend capability
  boundary, not a GUI feature gap).
- **CANONICAL_UI_SPEC:** `V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN\saipen\UI.md`
  SHA256 `162fa0574533456541b65fb79f1893fef863e9143aaab94ba99e0ea938ea5dd0`
  (429 lines, 21 clear Golden Default tokens, Vintage Golden design language,
  640x540 viewport / 640x480 minimum, Verdana non-AA, 2px bevel, no radius/
  shadow/gradient/animation, accessibility floor; revision marker: none — the
  document carries no revision line, recorded as absent).
- **SAIUI:** spawned + adopted; UI-001 (Task Map, Action/State Map, Capability
  Gap Map, information architecture, Golden Default transcription as
  `saimail/gui_theme.py`); collected as Core review hypothesis T-98 with a
  verified OUTBOX package; applied verbatim after review.
- **UI_FRAMEWORK:** PySide6 6.x, optional extra only.
- **DEPENDENCY_BOUNDARY:** base `dependencies` unchanged (`[]`); other extras
  untouched; `gui` extra isolated; clean base-install proves the core CLI works
  Qt-free and `saimail-gui` exits cleanly without Qt.
- **ENTRYPOINT:** `saimail-gui = "saimail.gui_app:main"` (lazy Qt import).
- **UI_TASK_MAP:** daily (refresh, select, open, new, reply, status/error);
  secondary (filters, recipient list, metadata, REF); rare (open/create
  workspace, export identity, add recipient, custody status/migrate);
  destructive none; recovery (actionable failure info, no stack traces).
- **INFORMATION_ARCHITECTURE:** header (SAIMAIL/LOCAL ONLY/seat/custody/
  Refresh) — mail split (inbox metadata | detail with explicit Open/Reply) —
  composer — rare strip — persistent status strip.
- **GOLDEN_DEFAULT / TOKEN_COMPLIANCE:** verified by `assert_canonical()`;
  21 tokens exact, no second theme, no rounded corners, bevel selection first,
  disabled via `--textMuted` only.
- **MINIMUM_VIEWPORT:** 640x480 PASS (offscreen test asserts no overlapping
  critical controls and usable geometry).
- **KEYBOARD_REACH / VISIBLE_FOCUS:** daily actions all reachable in the focus
  chain; focus selectors present in the canonical sheet; Enter on the list is
  the documented Open route; double-click deliberately not wired to Open.
- **WORKSPACE_FLOW / INBOX_FLOW:** open/create through first-run raw-custody
  notice; bounded metadata-only page with filters, explicit Load More, and
  continuation visibility.
- **METADATA_ONLY_SELECTION / EXPLICIT_OPEN:** selecting UNREAD reveals no
  content; Open is the only decryption path; state changes only after backend
  success.
- **NEW_MESSAGE / REPLY:** NEW selects a registered recipient; REPLY is
  READ-gated, visible disabled reason, recipient fixed by backend.
- **RECIPIENT_MANAGEMENT / CUSTODY_SURFACE:** list/add only through existing
  capabilities; custody status/state visible; migration explicit through the
  existing call; no overclaim.
- **REFRESH_POLICY:** explicit only; **BACKGROUND_MUTATION:** NONE (adapter and
  GUI carry no timer/thread/watcher/socket).
- **STATUS_ERROR_VISIBILITY:** persistent, never auto-hidden, text + colour.
- **ZERO_NETWORK_MODEL:** socket-tripwire acceptance proves 0 network, 0 model,
  0 provider calls.
- **CORE_DEPENDENCIES:** unchanged. **GUI_DEPENDENCY:** optional only.
- **POST_A2_PRODUCT_DELTA:** P1 + V4-01 + V5-01.
- **FROZEN_A2:** UNCHANGED (`d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d`).
- **GUI_FOCUSED_TESTS:** 50 additive (adapter + surface + acceptance), green.
- **CORE_FULL_SUITE:** 2357 passed / 0 failed / 0 errors / 0 skipped (2307
  inherited + 50 additive).
- **LINT:** ruff `--select E4,E7,E9,F` clean on touched files.
- **SAIPEN_VALIDATION:** logs 4 FAIL / 22 WARN in the closure scan — T-41
  release-linkage FAIL, SRC-036 credential gate FAIL and stale improve-report
  fingerprint FAIL are the carried inherited baseline; a root-file-set FAIL
  names three `SAIPEN — SAIHANDOFF — *.md` files that a prior session's
  `git add -A` placed inside the SAIPEN-home clone's `tools/` area (outside
  this project tree, not created by V5-01); the one V5-01-attributable item
  (saiui STATE `next_action` shape) surfaced on the same scan and was fixed in
  T-99. No V5-01-attributable failure remains.
- **SAIUI_FINAL_REVIEW:** inline review of the implemented surface against the
  canonical rules (see this file, section REVIEW_FINDINGS).
- **REVIEW_FINDINGS:** no P0/P1/P2 findings open. Noted and fixed during
  verification: `assert_canonical()` first assumed 21 distinct colours, but
  UI.md deliberately aliases `--selection` = `--surfaceRaised` and
  `--link` = `--borderHighlight` (19 distinct values across 21 tokens); the
  check now asserts exactly that and keeps the two aliases' equality explicit.
- **FILES_CREATED:** `saimail/gui_adapter.py`, `saimail/gui_app.py`,
  `saimail/gui_theme.py`, `tests/test_gui_surface.py`,
  `tests/test_gui_acceptance.py`, `spec/25-DESKTOP-LOCAL-MESSENGER-v0.md`,
  `humbox/FUTURE-GATES-V5.md`.
- **FILES_CHANGED:** `pyproject.toml` (+`gui` extra, +`saimail-gui` script),
  `README.md` (badge parity and the works/does-not list), `humbox/CURRENT-STATE.md`
  (v5 authority + V5-01 section), `tests/test_local_entrypoint.py` and
  `tests/test_clean_install.py` (dependency-boundary tests).
- **SAIPEN_LIFECYCLE:** SCOUT (E-1211) → BUILD (E-1212) → VERIFY PASS (E-1217)
  → REVIEW PASS (E-1219) → SHIP no-publish (E-1229) → DONE (E-1230).
- **ROADMAP_AUTHORITY:** `humbox/FUTURE-GATES-V5.md`.
- **ROADMAP_REFRESH / NEXT_TARGET:** refreshed from evidence; no next gate
  selected (`NONE`), none started.
- **BLOCKER:** NONE. **OPERATOR_ACTION:** NONE.
- **NEXT_EXACT_ACTION:** NONE — the local messenger workflow is usable; a
  concrete gap would be the only reason to create the next V5 gate.

## One honest boundary used in production

`workspace.open_message` is the single decryption transition and it is
non-repeatable (`ALREADY_READ`). A READ message from an earlier session is
therefore shown as metadata with a stated reason, and the recorded
backend-capability gap lands in `adapter.READ_REREAD_GAP` instead of being
faked in the UI.

## Evidence pointers

- Acceptance: `tests/test_gui_acceptance.py` (two-workspace flow, tree
  byte-identity across restart, socket tripwire).
- Surface: `tests/test_gui_surface.py` (640x480, overlap, Open/Reply bounds,
  keyboard reach).
- Theme: `saimail/gui_theme.py` + `test_theme_is_canonical_golden_default_only`.
- Clean install / entrypoint: `tests/test_clean_install.py`,
  `tests/test_local_entrypoint.py`.
- Contract: `spec/25-DESKTOP-LOCAL-MESSENGER-v0.md`.
- Roadmap: `humbox/FUTURE-GATES-V5.md`.