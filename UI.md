# SAIMAIL desktop

The user's Golden Default is the visual authority:
[`../_SAIPEN/saipen/UI.md`](../_SAIPEN/saipen/UI.md).
The packaged transcription is `saimail/gui_theme.py`, with the source revision
SHA-256 recorded there. No runtime dependency on another checkout is required.

Use the existing 21 colours, Verdana without antialiasing, sizes 10/11/12/14/16,
square corners and two-pixel bevels. No animations, gradients, shadows or hidden
refresh. Window minimum 640×480; scrolling keeps controls reachable at that size.

Three fixed tabs: Mail, Agents & continuity, Keys & backup. Reading and key
retrieval require explicit actions. The composer expands when opened. Selection
shows metadata; Open/Reopen loads content. Status and refusal reasons stay visible.
Password derivation runs only after a requested key action and blocks competing
actions while keeping the UI event loop responsive. Closing drops loaded keys and
plaintext references. This is not a guarantee of Python memory zeroization.

`lab/out/INSTITUTION_20260930/gui/` contains captures using the real Qt window.
