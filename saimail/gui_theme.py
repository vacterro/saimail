"""SAIMAIL GUI theme -- Golden Default tokens and the canonical Qt style sheet.

The visual authority is ``<saipen_home>/saipen/UI.md`` (Golden Default,
Vintage Golden design language): a closed set of 21 colour values, Verdana
non-antialiased, zero rounded corners/shadow/gradient/animation, 2px bevel
depth only, 640x540 usable, visible focus and full keyboard reach.

This module is the single place those values live. It never invents a colour:
``TOKENS`` is the canonical table, ``SEMANTIC`` only aliases canonical tokens to
component roles, and :func:`style_sheet` renders a Qt style sheet whose every
hex literal traces back to ``TOKENS``. ``assert_canonical`` proves both facts and
is used by the project's own GUI test suite.
"""

from __future__ import annotations

from typing import Dict, Mapping, Tuple

#: ``saipen/UI.md`` revision evidence for the copy this table was transcribed
#: from. Recorded so a drift check can be run without packaging UI.md.
UI_SPEC_SHA256 = "162fa0574533456541b65fb79f1893fef863e9143aaab94ba99e0ea938ea5dd0"
UI_SPEC_PATH = r"V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN\saipen\UI.md"

#: The canonical Golden Default palette, exactly as ``saipen/UI.md`` declares
#: it. 21 values, closed set. Never edited here, never extended here.
TOKENS: Mapping[str, str] = {
    "background": "#1A1810",
    "backgroundSoft": "#232018",
    "surface": "#332E22",
    "surfaceRaised": "#3D372A",
    "surfaceAlt": "#453D30",
    "borderDark": "#100E08",
    "borderHighlight": "#F0D060",
    "bevelLight": "#75663D",
    "borderMuted": "#5A5040",
    "textPrimary": "#D4C89A",
    "textSecondary": "#9C9371",
    "textMuted": "#6E674E",
    "accentTeal": "#008080",
    "accentTealDeep": "#004C4C",
    "success": "#4A7A20",
    "warning": "#7A7A20",
    "danger": "#7A2020",
    "dangerText": "#D66464",
    "selection": "#3D372A",
    "compareBack": "#14120C",
    "link": "#F0D060",
}

#: The 640x540 canonical viewport, and the narrower 640x480 minimum a desktop
#: window must still be usable at on Windows 10.
MIN_VIEWPORT: Tuple[int, int] = (640, 480)
CANONICAL_VIEWPORT: Tuple[int, int] = (640, 540)

#: The only legal font sizes (UI.md typography rules).
FONT_SIZES: Tuple[int, ...] = (10, 11, 12, 14, 16)
FONT_FAMILY = "Verdana"

#: Component-role aliases. Every value MUST be one of :data:`TOKENS`; a new
#: colour is not allowed, only a new name for an existing canonical value.
SEMANTIC: Dict[str, str] = {
    "window": TOKENS["background"],
    "window_text": TOKENS["textPrimary"],
    "panel": TOKENS["surfaceRaised"],
    "panel_alt": TOKENS["backgroundSoft"],
    "panel_text": TOKENS["textPrimary"],
    "title_bar": TOKENS["surface"],
    "title_text": TOKENS["textPrimary"],
    "separator": TOKENS["borderMuted"],
    "bevel": TOKENS["bevelLight"],
    "bevel_dark": TOKENS["borderDark"],
    "body": TOKENS["textPrimary"],
    "metadata": TOKENS["textSecondary"],
    "disabled_text": TOKENS["textMuted"],
    "input": TOKENS["compareBack"],
    "mono_back": TOKENS["compareBack"],
    "content_back": TOKENS["compareBack"],
    "link": TOKENS["link"],
    "focus_accent": TOKENS["borderHighlight"],
    "success_text": TOKENS["textPrimary"],
    "success_back": TOKENS["success"],
    "warning_text": TOKENS["textPrimary"],
    "warning_back": TOKENS["warning"],
    "danger_text": TOKENS["dangerText"],
    "danger_back": TOKENS["danger"],
}

#: Windows 10 ships Verdana; these are the documented per-role sizes.
SIZE_TITLE = 16
SIZE_SECTION = 14
SIZE_BODY = 12
SIZE_METADATA = 10

#: Dense default for secondary controls and the mandatory primary minimum.
CONTROL_MIN_HEIGHT = 20
PRIMARY_MIN_HEIGHT = 24
ROW_HEIGHT = 18


def style_sheet() -> str:
    """Render the canonical Qt style sheet from :data:`TOKENS` alone.

    Every hex literal in the returned string is a canonical token value; the
    helper formatters below are the only things allowed to emit one.
    """
    t = TOKENS
    return f"""
* {{
    font-family: "{FONT_FAMILY}", sans-serif;
    font-size: {SIZE_BODY}px;
    border-radius: 0;
}}
QWidget {{
    background: {t['background']};
    color: {t['textPrimary']};
}}
QWidget#TitleBar {{
    background: {t['surface']};
    border: 2px solid;
    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
}}
QLabel#TitleLabel {{
    font-size: {SIZE_TITLE}px;
    color: {t['textPrimary']};
}}
QLabel#SectionLabel {{
    font-size: {SIZE_SECTION}px;
    color: {t['textPrimary']};
}}
QLabel#MetadataLabel, QLabel#MutedLabel {{
    font-size: {SIZE_METADATA}px;
    color: {t['textSecondary']};
}}
QLabel#DisabledReason {{
    font-size: {SIZE_METADATA}px;
    color: {t['textMuted']};
}}
QLabel#LocalOnlyLabel {{
    font-size: {SIZE_SECTION}px;
    color: {t['borderHighlight']};
    border: 2px solid {t['borderMuted']};
    padding: 1px 4px;
}}
QWidget#StatusStrip {{
    background: {t['backgroundSoft']};
    border: 2px solid;
    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
}}
QLabel#StatusText {{
    color: {t['textPrimary']};
}}
QLabel#StatusSuccess {{
    color: {t['textPrimary']};
    background: {t['success']};
    padding: 1px 4px;
}}
QLabel#StatusWarning {{
    color: {t['textPrimary']};
    background: {t['warning']};
    padding: 1px 4px;
}}
QLabel#StatusDanger {{
    color: {t['dangerText']};
    background: {t['danger']};
    padding: 1px 4px;
}}
QFrame#Panel {{
    background: {t['surfaceRaised']};
    border: 2px solid;
    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
}}
QFrame#ContentPane {{
    background: {t['compareBack']};
    border: 2px solid;
    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
}}
QPushButton {{
    background: {t['surfaceRaised']};
    color: {t['textPrimary']};
    border: 2px solid;
    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
    padding: 2px 6px;
    min-height: {CONTROL_MIN_HEIGHT}px;
    min-width: 24px;
}}
QPushButton:hover {{
    background: {t['surfaceAlt']};
}}
QPushButton:focus {{
    outline: 1px dotted {t['textPrimary']};
    outline-offset: -4px;
}}
QPushButton:pressed {{
    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
    background: {t['surface']};
    padding-top: 3px;
    padding-left: 7px;
}}
QPushButton:disabled {{
    color: {t['textMuted']};
    background: {t['surfaceRaised']};
}}
QPushButton#Primary {{
    min-height: {PRIMARY_MIN_HEIGHT}px;
}}
QLineEdit, QPlainTextEdit, QComboBox {{
    background: {t['compareBack']};
    color: {t['textPrimary']};
    border: 2px solid;
    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
    padding: 1px 3px;
    selection-background-color: {t['selection']};
    selection-color: {t['textPrimary']};
}}
QLineEdit, QComboBox {{
    min-height: {CONTROL_MIN_HEIGHT}px;
}}
QPlainTextEdit {{
    min-height: 64px;
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border-color: {t['borderHighlight']};
}}
QComboBox QAbstractItemView {{
    background: {t['surface']};
    color: {t['textPrimary']};
    border: 2px solid;
    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
    selection-background-color: {t['surfaceAlt']};
    selection-color: {t['textPrimary']};
    outline: none;
}}
QListWidget {{
    background: {t['surfaceRaised']};
    color: {t['textPrimary']};
    border: 2px solid;
    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
    outline: none;
}}
QListWidget::item {{
    min-height: {ROW_HEIGHT}px;
    padding: 0 2px;
    color: {t['textPrimary']};
}}
QListWidget::item:selected {{
    background: {t['selection']};
    border: 2px solid;
    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
}}
QListWidget:focus {{
    border-color: {t['borderHighlight']};
}}
QHeaderView::section {{
    background: {t['surfaceRaised']};
    color: {t['textPrimary']};
    border: 2px solid;
    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
    padding: 1px 3px;
}}
QScrollBar:vertical, QScrollBar:horizontal {{
    background: {t['backgroundSoft']};
    border: 2px solid;
    border-color: {t['borderDark']} {t['bevelLight']} {t['bevelLight']} {t['borderDark']};
    margin: 0;
    width: 14px;
    height: 14px;
}}
QScrollBar::handle {{
    background: {t['surfaceRaised']};
    border: 2px solid;
    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
    min-height: 16px;
    min-width: 16px;
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    background: {t['surfaceRaised']};
    border: 2px solid;
    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
    width: 14px;
    height: 14px;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: {t['backgroundSoft']};
}}
QSplitter::handle {{
    background: {t['borderMuted']};
    width: 2px;
    height: 2px;
}}
QGroupBox {{
    border: 2px solid;
    border-color: {t['bevelLight']} {t['borderDark']} {t['borderDark']} {t['bevelLight']};
    margin-top: 8px;
    padding: 4px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 6px;
    color: {t['textPrimary']};
}}
QToolTip {{
    background: {t['surfaceRaised']};
    color: {t['textPrimary']};
    border: 2px solid {t['borderDark']};
}}
""".strip()


def hex_literals(style: str) -> set:
    """Every ``#rrggbb`` literal in a rendered style sheet, lower-cased."""
    return {part.strip(";, )").lower() for part in style.replace("\n", " ").split()
            if part.startswith("#")}


def assert_canonical() -> None:
    """Prove the theme is Golden Default only. Raises ``AssertionError``.

    Three facts, each mechanically checkable: the token table has exactly 21
    entries; every semantic alias resolves to a canonical token value; and every
    hex literal in the rendered style sheet is a canonical token value.

    The 21 entries are NOT 21 distinct colours: ``saipen/UI.md`` declares
    ``--selection`` equal to ``--surfaceRaised`` and ``--link`` equal to
    ``--borderHighlight``, which is why the distinct-value count is asserted
    exactly rather than assumed.
    """
    assert len(TOKENS) == 21, f"Golden Default has 21 tokens, found {len(TOKENS)}"
    allowed = {value.lower() for value in TOKENS.values()}
    assert len(allowed) == 19, (
        f"Golden Default declares 19 distinct colours across its 21 tokens, "
        f"found {len(allowed)}")
    assert TOKENS["selection"] == TOKENS["surfaceRaised"], (
        "UI.md declares --selection equal to --surfaceRaised; the selected-row "
        "rule depends on that")
    assert TOKENS["link"] == TOKENS["borderHighlight"], (
        "UI.md declares --link equal to --borderHighlight")
    for name, value in SEMANTIC.items():
        assert value.lower() in allowed, f"semantic alias {name!r} is not a canonical token"
    stray = hex_literals(style_sheet()) - allowed
    assert not stray, f"style sheet carries non-canonical colours: {sorted(stray)}"


__all__ = [
    "CANONICAL_VIEWPORT",
    "CONTROL_MIN_HEIGHT",
    "FONT_FAMILY",
    "FONT_SIZES",
    "MIN_VIEWPORT",
    "PRIMARY_MIN_HEIGHT",
    "ROW_HEIGHT",
    "SEMANTIC",
    "SIZE_BODY",
    "SIZE_METADATA",
    "SIZE_SECTION",
    "SIZE_TITLE",
    "TOKENS",
    "UI_SPEC_PATH",
    "UI_SPEC_SHA256",
    "assert_canonical",
    "hex_literals",
    "style_sheet",
]
