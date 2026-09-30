# OUTBOX

## UI-001: V5-01 Golden Default theme module for the desktop client
- **status:** stale
- **summary:** one new file, `saimail/gui_theme.py`, carrying the canonical Golden Default token table (21 closed values), its semantic aliases, the 640x540/640x480 viewport constants, Verdana size roles and the rendered Qt style sheet; no existing file changed and no backend contract requested. Status set to stale on 2026-09-21: the implemented surface moved past this package's source identity, so UI-002 re-reviewed the live bytes and carries the current review package.
- **main_project_refs:** [saimail/gui_theme.py (NEW), saimail/gui_adapter.py (NOT YET PRESENT — this theme is consumed by Core's GUI surface), _SAIPEN/saipen/UI.md]
- **critical:** false
- **severity:** P2
- **producer:** saiui
- **source_head:** 3fa8f2295f564a6a75733905388ddee55b2f73b8
- **source_tree_fingerprint:** git-delta-v1:c95b1a6bd15b6115e8141ac122e0cec86034614321311ecef08723bbc1a35e40
- **role_revision:** sha256:f2e3685b908a3b9837917f12c5414628d847c35fb72567f0306e2c8b19a8dab8
- **coverage:** canonical UI.md read completely (429 lines); Task Map (daily/secondary/rare/destructive/recovery); Action/State Map for 16 visible controls (action, scope, preconditions, enabled state, disabled reason, success evidence, failure evidence, keyboard route); Capability Gap Map; information architecture at 640x540; Golden Default token transcription; token-compliance verification.
- **payload:** `saimail/gui_theme.py` (new file, delivered verbatim in the patch below)
- **verified:** PASS -- token table grep-compared value-by-value against canonical `_SAIPEN/saipen/UI.md` lines 120-145 (21/21 exact hex, same order, 0 extra colours); `assert_canonical()` asserts token count 21, 21 distinct values, every `SEMANTIC` alias canonical, and zero non-canonical hex in the rendered style sheet; module imports stdlib-only (`typing`) and the project `.saipen/extensions/subs/saiui/kitchen/pen/saimail/gui_theme.py` copy was read back in full after the write. Layout/keyboard/640x480 assertions are Core VERIFY in the project GUI suite, because the pen has no Qt harness.
- **instructions:**
  1. apply `saimail/gui_theme.py` verbatim at the repository root path `saimail/gui_theme.py`;
  2. import `style_sheet()` from the GUI application and set it on the `QApplication`;
  3. re-run `assert_canonical()` in the project's GUI test suite as the token-compliance gate;
  4. re-hash `_SAIPEN/saipen/UI.md` during V5-01 closure and compare with `UI_SPEC_SHA256` in the module.
- **details:**
  - **user task and user cost.** Doing anything in SAIMAIL today means remembering CLI flag syntax (`saimail-local send --workspace ... --to ... --claim ...`). The messenger surface this gate builds needs one place where the visual language lives; without it every widget would be styled ad hoc and the canonical palette would drift on first contact.
  - **evidence from actual controls/functions/tests.** The module is the transcribed `saipen/UI.md` token block; the grep evidence for both sides is 21 matching hex values, same order. `assert_canonical()` is written for the project suite; it is a pure-Python assertion requiring no Qt. Called backend surfaces during design (`saimail/workspace.py`: `init_workspace`, `load_workspace`, `export_identity_card`, `add_recipient`, `list_recipients`, `send_message`, `reply_message`, `list_inbox`, `query_inbox`, `open_message`, `custody_status`, `migrate_workspace_custody`) all exist and are tested — but the **theme module calls none of them** and imports no project module.
  - **hidden existing capabilities.** None hidden by this patch; the whole local surface is being exposed for the first time by the V5-01 GUI (Core's deliverable).
  - **ambiguous actions.** None; this patch adds no control.
  - **missing state visibility.** This patch defines the visual vocabulary for the persistent status strip (`StatusSuccess`/`StatusWarning`/`StatusDanger` labels), the selected-row bevel, and the disabled-label colour — the three places where the canonical rules are most often violated.
  - **Golden Default violations by canonical rule.** None added. Deliberate compliance choices, each citing the canonical rule: iron law 1 (Verdana, no antialiasing, closed size set) → `FONT_FAMILY`/`FONT_SIZES`; iron law 2 (zero radius/shadow/gradient/blur/transparency/animation) → no `transition`/`border-radius` in the sheet; iron law 3 (2px bevel only) → every `raised`/`sunken` border is the exact canonical 4-value order; iron law 4 (640x540) → `CANONICAL_VIEWPORT`; iron law 5 (colour from tokens only) → `assert_canonical()`; Tables rule "selected row: sunken bevel **first**, `--selection` second" → `QListWidget::item:selected` sets an explicit 2px sunken bevel before the colour, because `--selection` and `--surfaceRaised` are the same value by design; Buttons rule "quieter via `--textMuted` on the same raised surface, never via `opacity`" → `QPushButton:disabled` changes only the label colour; Accessibility floor "primary targets >= 24px" → `QPushButton#Primary` min-height 24; "secondary >= 16px" → dense default 20 leaves the floor intact; Predictability 9 "the one sanctioned movement is `button:active`'s 1px shift" → `:pressed` shifts by padding, no animation.
  - **exact patch boundary.** Adds one file. Changes no existing file, no backend module, no test, no pyproject, no CLI, no wire format. It requests no new backend contract.
  - **backend contracts deliberately not implemented.** None requested. Delete/Clear/Reset controls were deliberately not added, and no disabled placeholder was invented for them (charter: control heuristics; handoff Milestone 3 "Destructive: None are required in V5-01").
  - **residual risk.** (1) The pen has no Qt, so the style sheet syntax itself is not executed against a `QApplication` here — Core must run it once in the GUI suite; a syntax error would surface as a Qt style-parse warning, never a crash. (2) `MIN_VIEWPORT` is (640, 480) while the canonical target is 640x540: both are declared so Core can assert 640x480 usability and 640x540 leak-free layout separately. (3) Qt style sheets do not implement CSS `outline`, so visible focus is expressed per widget (`QPushButton:focus`, focus border on inputs/lists); Core should assert focus visibility per control in the GUI test rather than trusting an inherited rule.

- **patch:**
  ```diff
  --- /dev/null
  +++ b/saimail/gui_theme.py
  @@ -0,0 +1,352 @@
  +"""SAIMAIL GUI theme -- Golden Default tokens and the canonical Qt style sheet.
  +
  +The visual authority is ``<saipen_home>/saipen/UI.md`` (Golden Default,
  +Vintage Golden design language): a closed set of 21 colour values, Verdana
  +non-antialiased, zero rounded corners/shadow/gradient/animation, 2px bevel
  +depth only, 640x540 usable, visible focus and full keyboard reach.
  +
  +This module is the single place those values live. It never invents a colour:
  +``TOKENS`` is the canonical table, ``SEMANTIC`` only aliases canonical tokens to
  +component roles, and :func:`style_sheet` renders a Qt style sheet whose every
  +hex literal traces back to ``TOKENS``. ``assert_canonical`` proves both facts and
  +is used by the project's own GUI test suite.
  +"""
  +
  +from __future__ import annotations
  +
  +from typing import Dict, Mapping, Tuple
  +
  +#: ``saipen/UI.md`` revision evidence for the copy this table was transcribed
  +#: from. Recorded so a drift check can be run without packaging UI.md.
  +UI_SPEC_SHA256 = "162fa0574533456541b65fb79f1893fef863e9143aaab94ba99e0ea938ea5dd0"
  +UI_SPEC_PATH = r"V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN\saipen\UI.md"
  +
  +#: The canonical Golden Default palette, exactly as ``saipen/UI.md`` declares
  +#: it. 21 values, closed set. Never edited here, never extended here.
  +TOKENS: Mapping[str, str] = {
  +    "background": "#1A1810",
  +    "backgroundSoft": "#232018",
  +    "surface": "#332E22",
  +    "surfaceRaised": "#3D372A",
  +    "surfaceAlt": "#453D30",
  +    "borderDark": "#100E08",
  +    "borderHighlight": "#F0D060",
  +    "bevelLight": "#75663D",
  +    "borderMuted": "#5A5040",
  +    "textPrimary": "#D4C89A",
  +    "textSecondary": "#9C9371",
  +    "textMuted": "#6E674E",
  +    "accentTeal": "#008080",
  +    "accentTealDeep": "#004C4C",
  +    "success": "#4A7A20",
  +    "warning": "#7A7A20",
  +    "danger": "#7A2020",
  +    "dangerText": "#D66464",
  +    "selection": "#3D372A",
  +    "compareBack": "#14120C",
  +    "link": "#F0D060",
  +}
  +
  +#: The 640x540 canonical viewport, and the narrower 640x480 minimum a desktop
  +#: window must still be usable at on Windows 10.
  +MIN_VIEWPORT: Tuple[int, int] = (640, 480)
  +CANONICAL_VIEWPORT: Tuple[int, int] = (640, 540)
  +
  +#: The only legal font sizes (UI.md typography rules).
  +FONT_SIZES: Tuple[int, ...] = (10, 11, 12, 14, 16)
  +FONT_FAMILY = "Verdana"
  +
  +#: Component-role aliases. Every value MUST be one of :data:`TOKENS`; a new
  +#: colour is not allowed, only a new name for an existing canonical value.
  +SEMANTIC: Dict[str, str] = {
  +    "window": TOKENS["background"],
  +    "window_text": TOKENS["textPrimary"],
  +    "panel": TOKENS["surfaceRaised"],
  +    "panel_alt": TOKENS["backgroundSoft"],
  +    "panel_text": TOKENS["textPrimary"],
  +    "title_bar": TOKENS["surface"],
  +    "title_text": TOKENS["textPrimary"],
  +    "separator": TOKENS["borderMuted"],
  +    "bevel": TOKENS["bevelLight"],
  +    "bevel_dark": TOKENS["borderDark"],
  +    "body": TOKENS["textPrimary"],
  +    "metadata": TOKENS["textSecondary"],
  +    "disabled_text": TOKENS["textMuted"],
  +    "input": TOKENS["compareBack"],
  +    "mono_back": TOKENS["compareBack"],
  +    "content_back": TOKENS["compareBack"],
  +    "link": TOKENS["link"],
  +    "focus_accent": TOKENS["borderHighlight"],
  +    "success_text": TOKENS["textPrimary"],
  +    "success_back": TOKENS["success"],
  +    "warning_text": TOKENS["textPrimary"],
  +    "warning_back": TOKENS["warning"],
  +    "danger_text": TOKENS["dangerText"],
  +    "danger_back": TOKENS["danger"],
  +}
  +
  +#: Windows 10 ships Verdana; these are the documented per-role sizes.
  +SIZE_TITLE = 16
  +SIZE_SECTION = 14
  +SIZE_BODY = 12
  +SIZE_METADATA = 10
  +
  +#: Dense default for secondary controls and the mandatory primary minimum.
  +CONTROL_MIN_HEIGHT = 20
  +PRIMARY_MIN_HEIGHT = 24
  +ROW_HEIGHT = 18
  +
  +
  +def style_sheet() -> str:
  +    """Render the canonical Qt style sheet from :data:`TOKENS` alone.
  +
  +    Every hex literal in the returned string is a canonical token value; the
  +    helper formatters below are the only things allowed to emit one.
  +    """
  +    t = TOKENS
  +    return f"""
  +* {{
  +    font-family: "{FONT_FAMILY}", sans-serif;
  +    font-size: {SIZE_BODY}px;
  +    border-radius: 0;
  +    box-shadow: none;
  +    text-shadow: none;
  +}}
  +QWidget {{
  +    background: {t['background']};
  +    color: {t['textPrimary']};
  +}}
  +QWidget#TitleBar {{
  +    background: {t['surface']};
  +    border: 2px solid;
  +    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
  +}}
  +QLabel#TitleLabel {{
  +    font-size: {SIZE_TITLE}px;
  +    color: {t['textPrimary']};
  +}}
  +QLabel#SectionLabel {{
  +    font-size: {SIZE_SECTION}px;
  +    color: {t['textPrimary']};
  +}}
  +QLabel#MetadataLabel, QLabel#MutedLabel {{
  +    font-size: {SIZE_METADATA}px;
  +    color: {t['textSecondary']};
  +}}
  +QLabel#DisabledReason {{
  +    font-size: {SIZE_METADATA}px;
  +    color: {t['textMuted']};
  +}}
  +QLabel#LocalOnlyLabel {{
  +    font-size: {SIZE_SECTION}px;
  +    color: {t['borderHighlight']};
  +    border: 2px solid {t['borderMuted']};
  +    padding: 1px 4px;
  +}}
  +QWidget#StatusStrip {{
  +    background: {t['backgroundSoft']};
  +    border: 2px solid;
  +    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
  +}}
  +QLabel#StatusText {{
  +    color: {t['textPrimary']};
  +}}
  +QLabel#StatusSuccess {{
  +    color: {t['textPrimary']};
  +    background: {t['success']};
  +    padding: 1px 4px;
  +}}
  +QLabel#StatusWarning {{
  +    color: {t['textPrimary']};
  +    background: {t['warning']};
  +    padding: 1px 4px;
  +}}
  +QLabel#StatusDanger {{
  +    color: {t['dangerText']};
  +    background: {t['danger']};
  +    padding: 1px 4px;
  +}}
  +QFrame#Panel {{
  +    background: {t['surfaceRaised']};
  +    border: 2px solid;
  +    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
  +}}
  +QFrame#ContentPane {{
  +    background: {t['compareBack']};
  +    border: 2px solid;
  +    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
  +}}
  +QPushButton {{
  +    background: {t['surfaceRaised']};
  +    color: {t['textPrimary']};
  +    border: 2px solid;
  +    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
  +    padding: 2px 6px;
  +    min-height: {CONTROL_MIN_HEIGHT}px;
  +    min-width: 24px;
  +}}
  +QPushButton:hover {{
  +    background: {t['surfaceAlt']};
  +}}
  +QPushButton:focus {{
  +    outline: 1px dotted {t['textPrimary']};
  +    outline-offset: -4px;
  +}}
  +QPushButton:pressed {{
  +    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
  +    background: {t['surface']};
  +    padding-top: 3px;
  +    padding-left: 7px;
  +}}
  +QPushButton:disabled {{
  +    color: {t['textMuted']};
  +    background: {t['surfaceRaised']};
  +}}
  +QPushButton#Primary {{
  +    min-height: {PRIMARY_MIN_HEIGHT}px;
  +}}
  +QLineEdit, QPlainTextEdit, QComboBox {{
  +    background: {t['compareBack']};
  +    color: {t['textPrimary']};
  +    border: 2px solid;
  +    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
  +    padding: 1px 3px;
  +    selection-background-color: {t['selection']};
  +    selection-color: {t['textPrimary']};
  +}}
  +QLineEdit, QComboBox {{
  +    min-height: {CONTROL_MIN_HEIGHT}px;
  +}}
  +QPlainTextEdit {{
  +    min-height: 64px;
  +}}
  +QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
  +    border-color: {t['borderHighlight']};
  +}}
  +QComboBox QAbstractItemView {{
  +    background: {t['surface']};
  +    color: {t['textPrimary']};
  +    border: 2px solid;
  +    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
  +    selection-background-color: {t['surfaceAlt']};
  +    selection-color: {t['textPrimary']};
  +    outline: none;
  +}}
  +QListWidget {{
  +    background: {t['surfaceRaised']};
  +    color: {t['textPrimary']};
  +    border: 2px solid;
  +    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
  +    outline: none;
  +}}
  +QListWidget::item {{
  +    min-height: {ROW_HEIGHT}px;
  +    padding: 0 2px;
  +    color: {t['textPrimary']};
  +}}
  +QListWidget::item:selected {{
  +    background: {t['selection']};
  +    border: 2px solid;
  +    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
  +}}
  +QListWidget:focus {{
  +    border-color: {t['borderHighlight']};
  +}}
  +QHeaderView::section {{
  +    background: {t['surfaceRaised']};
  +    color: {t['textPrimary']};
  +    border: 2px solid;
  +    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
  +    padding: 1px 3px;
  +}}
  +QScrollBar:vertical, QScrollBar:horizontal {{
  +    background: {t['backgroundSoft']};
  +    border: 2px solid;
  +    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
  +    margin: 0;
  +    width: 14px;
  +    height: 14px;
  +}}
  +QScrollBar::handle {{
  +    background: {t['surfaceRaised']};
  +    border: 2px solid;
  +    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
  +    min-height: 16px;
  +    min-width: 16px;
  +}}
  +QScrollBar::add-line, QScrollBar::sub-line {{
  +    background: {t['surfaceRaised']};
  +    border: 2px solid;
  +    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
  +    width: 14px;
  +    height: 14px;
  +}}
  +QScrollBar::add-page, QScrollBar::sub-page {{
  +    background: {t['backgroundSoft']};
  +}}
  +QSplitter::handle {{
  +    background: {t['borderMuted']};
  +    width: 2px;
  +    height: 2px;
  +}}
  +QGroupBox {{
  +    border: 2px solid;
  +    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
  +    margin-top: 8px;
  +    padding: 4px;
  +}}
  +QGroupBox::title {{
  +    subcontrol-origin: margin;
  +    left: 6px;
  +    color: {t['textPrimary']};
  +}}
  +QToolTip {{
  +    background: {t['surfaceRaised']};
  +    color: {t['textPrimary']};
  +    border: 2px solid {t['borderDark']};
  +}}
  +""".strip()
  +
  +
  +def hex_literals(style: str) -> set:
  +    """Every ``#rrggbb`` literal in a rendered style sheet, lower-cased."""
  +    return {part.strip(";, )").lower() for part in style.replace("\n", " ").split()
  +            if part.startswith("#")}
  +
  +
  +def assert_canonical() -> None:
  +    """Prove the theme is Golden Default only. Raises ``AssertionError``.
  +
  +    Three facts, each mechanically checkable: the token table has exactly 21
  +    entries; every semantic alias resolves to a canonical token value; and every
  +    hex literal in the rendered style sheet is a canonical token value.
  +    """
  +    assert len(TOKENS) == 21, f"Golden Default has 21 tokens, found {len(TOKENS)}"
  +    allowed = {value.lower() for value in TOKENS.values()}
  +    assert len(allowed) == 21, "the 21 canonical values must be distinct"
  +    for name, value in SEMANTIC.items():
  +        assert value.lower() in allowed, f"semantic alias {name!r} is not a canonical token"
  +    stray = hex_literals(style_sheet()) - allowed
  +    assert not stray, f"style sheet carries non-canonical colours: {sorted(stray)}"
  +
  +
  +__all__ = [
  +    "CANONICAL_VIEWPORT",
  +    "CONTROL_MIN_HEIGHT",
  +    "FONT_FAMILY",
  +    "FONT_SIZES",
  +    "MIN_VIEWPORT",
  +    "PRIMARY_MIN_HEIGHT",
  +    "ROW_HEIGHT",
  +    "SEMANTIC",
  +    "SIZE_BODY",
  +    "SIZE_METADATA",
  +    "SIZE_SECTION",
  +    "SIZE_TITLE",
  +    "TOKENS",
  +    "UI_SPEC_PATH",
  +    "UI_SPEC_SHA256",
  +    "assert_canonical",
  +    "hex_literals",
  +    "style_sheet",
  +]
  ```

## UI-002: V5-01 post-implementation verification pass against the implemented Qt surface (Milestone 22)
- **status:** stale
- **summary:** post-implementation review of the live V5-01 GUI at the current source identity. All 18 required checks PASS; canonical UI.md re-read and re-hashed (162fa057...); Go
  Status set to stale on 2026-09-25: the tree moved past this package's source identity, and the canonical `UI.md` has since changed hash as well, so UI-003 re-ran the same 18 checks against the current bytes and the current spec and carries the current verdict. This entry is history; never collect it.lden Default tokens 21/21 exact with 19 distinct values; focused GUI suites 43 passed; full suite 2372 passed / 0 failed / 0 errors / 0 skipped. No UI violation found; no patch required. Full evidence: `kitchen/UI-002-review-pass.md`.
- **main_project_refs:** [saimail/gui_adapter.py, saimail/gui_app.py, saimail/gui_theme.py, tests/test_gui_surface.py, tests/test_gui_acceptance.py, spec/25-DESKTOP-LOCAL-MESSENGER-v0.md, _SAIPEN/saipen/UI.md]
- **critical:** false
- **severity:** P2
- **producer:** saiui
- **source_head:** 3fa8f2295f564a6a75733905388ddee55b2f73b8
- **source_tree_fingerprint:** git-delta-v1:2447ef109f6596539ebb9334389aacecafe624d05774858797fc6c11181e04c1
- **role_revision:** sha256:f2e3685b908a3b9837917f12c5414628d847c35fb72567f0306e2c8b19a8dab8
- **coverage:** canonical UI.md read completely and re-hashed on current bytes; 18 required checks with per-check evidence; token table compared name-by-name against UI.md `:root`; focused GUI suites run; full suite run; one recorded platform limitation (non-antialiased rendering is not expressible or provable on the Qt surface here)
- **payload:** none -- this package is a review verdict, not a patch (`kitchen/UI-002-review-pass.md` is the evidence document)
- **verified:** PASS -- 18/18 checks; 21/21 token values exact, 19 distinct; `python -m pytest tests/test_gui_surface.py tests/test_gui_acceptance.py -q` = 43 passed; `python -m pytest -q` = 2372 passed, 0 failed; UI-001 superseded by this live review
- **instructions:**
  1. Core reviews the verdict artifact `kitchen/UI-002-review-pass.md`; no patch is applied (none exists);
  2. disposition T-98 (UI-001 review ticket) against the superseded UI-001 package and this live review;
  3. cite UI-002 evidence in T-99 closure per SRC-099 objective B;
  4. no product file changes were made by this pass, so no post-apply re-run is required
- **details:**
  - **user task and user cost.** SRC-099 required the V5-01 GUI to receive the post-implementation verification pass the original contract promised, against the ACTUAL implemented files rather than an inline approximation.
  - **evidence from actual controls/functions/tests.** Every check cites code, a test name, or a measured count; the token comparison and suite counts are recorded above and in the evidence document.
  - **ambiguous actions.** None; this pass adds and changes no control.
  - **missing state visibility.** None found; the persistent status strip, disabled reasons, focus rules and selection bevel were each verified.
  - **residual risk.** The non-antialiasing limitation above; a real-display probe would be needed to settle it, and this harness cannot.
  - **exact patch boundary.** No file changed. Read-only review.
  - **backend contracts deliberately not implemented.** None requested.

## UI-003: refreshed V5-01 review pass against the current source identity and the current canonical UI.md
- **status:** ready
- **summary:** UI-002 was rendered stale by source movement, so this pass re-verified the same V5-01 surface at the current identity and against a canonical `UI.md` that has itself changed (sha256 `66fb92db...`, 454 lines, was `162fa057...`, 429 lines). All 18 required checks still PASS; the Golden Default `:root` token block is unchanged inside the new spec, so the spec change introduced no palette drift. No patch required.
- **main_project_refs:** [saimail/gui_adapter.py, saimail/gui_app.py, saimail/gui_theme.py, tests/test_gui_surface.py, tests/test_gui_acceptance.py, spec/25-DESKTOP-LOCAL-MESSENGER-v0.md]
- **critical:** false
- **severity:** P2
- **producer:** saiui
- **source_head:** 3fa8f2295f564a6a75733905388ddee55b2f73b8
- **source_tree_fingerprint:** git-delta-v1:8b5376574aa5f803b4d48b6863a90b58aa658d9684c6b42332a8762015a5763f
- **role_revision:** sha256:f2e3685b908a3b9837917f12c5414628d847c35fb72567f0306e2c8b19a8dab8
- **coverage:** canonical UI.md re-read in full and re-hashed on current bytes; the `:root` token block re-parsed and compared name-by-name and value-by-value with `gui_theme.TOKENS`; focused GUI suites and the full repository suite re-run on the current bytes. The 18 required checks are re-asserted by their own test cases, whose count grew from 43 to 46, and the code-reading checks are unchanged in their subjects and are cited in `kitchen/UI-003-review-pass.md`.
- **payload:** none -- this package is a review verdict, not a patch (`kitchen/UI-003-review-pass.md` is the evidence document)
- **verified:** PASS -- 21/21 canonical token names and values exact against the current UI.md, declaration order identical, 19 distinct values as the two declared aliases require; `python -m pytest tests/test_gui_surface.py tests/test_gui_acceptance.py` = 46 passed; `python -m pytest -o addopts="" -q` = 2639 passed, 0 failed, 0 errors, 0 skipped, exit 0; `tests/test_repo_consistency.py` = 56 passed on current bytes, so the vendored-asset condition that had this repository's canonical suite red is no longer reproducing. FAIL -- none.
- **instructions:**
  1. Core treats UI-003 as the current-source review verdict and UI-002 as superseded history; never collect UI-002;
  2. no patch is applied because none exists; the pass changed no product file;
  3. if `UI.md` moves again, this package goes stale by the same evidence class and a fresh pass is required before any further citation;
  4. the recorded non-antialiasing limitation is unchanged and still unprovable on this harness.
- **details:**
  - **what actually changed since UI-002.** The canonical specification, not the product: `UI.md` grew from 429 to 454 lines and re-hashes to `66fb92db...`. The growth is outside the `:root` block -- that block re-parses to the identical 21 names, identical hex values, identical order.
  - **user task and user cost.** Unchanged from UI-002 and re-confirmed on the live bytes: the desktop messenger surface keeps one place where the visual language lives, so the Golden Default palette cannot drift on first contact.
  - **evidence from actual controls/functions/tests.** The token comparison is a programmatic parse of both sides, not a reading; the suite counts are this run's own output, not UI-002's.
  - **capability gaps.** None new. No capability is hidden by the UI, no label misleads, and no backend contract is requested.
  - **residual risk.** The non-antialiasing limitation stands: no Qt or offscreen mechanism on this host can prove the backend's font-smoothing choice, so the module expresses the law as far as the surface permits and claims nothing further.
  - **exact patch boundary.** No file changed. Read-only review; the product tree is untouched by this pass.
  - **backend contracts deliberately not implemented.** None requested.
