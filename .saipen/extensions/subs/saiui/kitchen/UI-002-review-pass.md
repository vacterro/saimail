# UI-002 -- V5-01 post-implementation verification pass (Milestone 22)

- reviewer: saiui (adopted in the Core session, serial crew stage SC-5)
- date: 2026-09-21
- canonical authority: `_SAIPEN/saipen/UI.md`, sha256
  `162fa0574533456541b65fb79f1893fef863e9143aaab94ba99e0ea938ea5dd0`
  (re-hashed at review start on current bytes, 429 lines)
- source identity reviewed: `source_head`
  `3fa8f2295f564a6a75733905388ddee55b2f73b8`, `source_tree_fingerprint`
  `git-delta-v1:2447ef109f6596539ebb9334389aacecafe624d05774858797fc6c11181e04c1`
- files verified: `saimail/gui_adapter.py`, `saimail/gui_app.py`,
  `saimail/gui_theme.py`, `tests/test_gui_surface.py`,
  `tests/test_gui_acceptance.py`, `spec/25-DESKTOP-LOCAL-MESSENGER-v0.md`

## Method

Read UI.md completely, then read the full implemented surface above. Parsed the
canonical `:root` token block from UI.md and compared it name-by-name and
value-by-value with `gui_theme.TOKENS`; ran the focused GUI suites
(`tests/test_gui_surface.py tests/test_gui_acceptance.py`) and the full suite on
the current bytes. No Qt visual judgement by memory; every verdict cites code,
a test, or a measured count.

## Checks (SRC-099 objective B)

| # | Required check | Verdict | Evidence |
|---|---|---|---|
| 1 | implemented information architecture matches Task Map | PASS | `gui_app._build`: TitleBar / Inbox+Message split / Composer / rare strip / persistent StatusStrip; daily actions before rare in `_tab_order` |
| 2 | Action/State Map matches real controls | PASS | 16 visible controls; every unavailable action carries a visible `DisabledReason` (`open_reason`, `reply_reason`, `send_reason`, `REASON_*`) |
| 3 | 640x480 remains usable | PASS | `MIN_VIEWPORT=(640,480)`; `test_640x480_window_is_usable_and_has_no_overlapping_critical_controls` |
| 4 | canonical 640x540 target compliant | PASS | `CANONICAL_VIEWPORT=(640,540)`; vertical scroll normal, no horizontal page scroll (widgets shrink, text wraps) |
| 5 | keyboard reach matches implementation | PASS | explicit 26-widget tab chain + 8 shortcuts; `test_keyboard_focus_order_reaches_every_daily_action` |
| 6 | focus remains visible | PASS | per-widget `:focus` rules (buttons, inputs, text, combo, list); `test_every_interactive_control_has_a_visible_focus_rule` |
| 7 | selecting does not Open | PASS | `GuiAdapter.select` never calls `open_message` (spy test); Enter is the only list route; `itemActivated` has 0 receivers |
| 8 | Reply READ gating is visible | PASS | `REASON_REPLY_UNREAD` shown and Reply disabled until READ; `test_reply_unavailable_until_read_with_visible_reason` |
| 9 | Refresh is explicit | PASS | no timer/thread/poll in adapter or app (source greps); acceptance asserts an untouched page never changes |
| 10 | persistent failures do not auto-hide | PASS | status strip persists until dismissed or replaced; `test_status_never_auto_hides_and_colour_is_not_the_only_signal` |
| 11 | Local Only is textual | PASS | `LOCAL ONLY` label plus window title text; `test_local_only_is_stated_in_text` |
| 12 | no colour-only meaning | PASS | status line carries LEVEL + CODE + text; selected row uses sunken bevel plus colour; disabled state carries a text reason |
| 13 | no hover-only meaning | PASS | hover only changes background; every action has a button, shortcut and tab route |
| 14 | no second palette | PASS | `assert_canonical()`; token compare 21/21 exact vs UI.md, zero stray hex in the rendered sheet |
| 15 | Golden Default tokens remain exact | PASS | parsed UI.md `:root` vs `gui_theme.TOKENS`: same 21 names, zero mismatches |
| 16 | 21 token names / 19 distinct hex values | PASS | measured `distinct_values 19`; `assert_canonical` asserts exactly 19 and the two declared aliases (`selection==surfaceRaised`, `link==borderHighlight`) |
| 17 | no arbitrary Qt visual drift | PASS, one recorded limitation | zero radius/shadow/gradient/animation/opacity in the sheet; 2px bevels only; sizes from the closed 10/11/12/14/16 set; selected-row bevel ordering per UI.md Tables rule |
| 18 | no hidden backend semantics in the UI | PASS | the app forwards to `GuiAdapter`, which forwards to the tested public API; no persistence/protocol logic; source greps show no network/thread/timer machinery |

## Recorded limitation (not a violation)

Non-antialiased rendering: UI.md iron law 1 and the QA list require Verdana
rendered non-antialiased. Qt style sheets cannot express smoothing hints, and
an offscreen render probe on this host measured zero partial-alpha edge pixels
for both the default and `QFont.StyleStrategy.NoAntialias` fonts, so the
offscreen harness carries no mechanical signal and no code path can prove or
force the backend's choice. `gui_theme` therefore expresses the law as far as
the Qt surface permits (family, closed size set, zero smoothing CSS
equivalents) and does not claim a rendering guarantee it cannot prove. If a
desktop-pixel proof is ever required, it needs a real-display probe outside
this harness.

## Focused and full-suite evidence

- `python -m pytest tests/test_gui_surface.py tests/test_gui_acceptance.py -q`
  -> 43 passed, 0 failed, 0 errors, 0 skipped
- `python -m pytest -q` -> 2372 passed, 0 failed, 0 errors, 0 skipped
  (2358 pre-existing floor + 14 DEV ACCESS tests)
- `python -m ruff check tools/dev_access.py tests/test_dev_access.py` -> clean

## Verdict

PASS. No UI violation found; no pen patch required. UI-001 and UI-002 are
closed in this sub-state; the current-source review package is handed to Core
through `kitchen/OUTBOX.md` (status ready).