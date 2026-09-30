FINAL REPORT — T-97 / V5-01

STATUS:
DONE — STOP

NEW_OPERATOR_GOAL:
desktop local messenger GUI

ROADMAP_V5:
humbox/FUTURE-GATES-V5.md (V5-01 DONE, no next gate selected)

CANONICAL_UI_SPEC:
path: V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN\saipen\UI.md
SHA256: 162fa0574533456541b65fb79f1893fef863e9143aaab94ba99e0ea938ea5dd0
revision: none (document carries no revision marker)

SAIUI:
spawned + adopted; UI-001: Task Map + Action/State Map + Capability Gap Map + information architecture + Golden Default transcription (saimail/gui_theme.py); collected as Core review hypothesis T-98 (package identity sha256:43c79c3d41cb687608c9bd62e097dfadb28d05de3616b29670aa3c821c768387); applied verbatim

UI_FRAMEWORK:
PySide6 6.x (optional extra only: gui = ["PySide6>=6.7,<7"])

DEPENDENCY_BOUNDARY:
base dependencies unchanged ([]); gui extra isolated; core saimail-local works without Qt; saimail-gui exits cleanly with one actionable line when Qt absent

ENTRYPOINT:
saimail-gui = "saimail.gui_app:main" (lazy Qt import)

UI_TASK_MAP:
DAILY: Refresh, Select, Open, New Message, Reply, Status/error
SECONDARY: Filters, Recipient selection, Metadata, REF inspection
RARE: Open/Create Workspace, Export Identity, Add Recipient, Custody Status/Migration
DESTRUCTIVE: None
RECOVERY: Actionable failure info, no stack traces

INFORMATION_ARCHITECTURE:
Header (SAIMAIL/LOCAL ONLY/seat/custody/Refresh) | Split (Inbox metadata | Detail with Open/Reply) | Composer (NEW/REPLY modes) | Rare strip | Persistent status strip

GOLDEN_DEFAULT:
verified against canonical UI.md (assert_canonical passes: 21 tokens, 19 distinct values, 0 stray hex in QSS)

TOKEN_COMPLIANCE:
21/21 values exact; no extra colours; semantic aliases only; QSS renders canonical hex only

MINIMUM_VIEWPORT:
640x480 PASS (offscreen test: no overlapping critical controls, usable geometry)

KEYBOARD_REACH:
daily actions reachable (Refresh Ctrl+R, Open Ctrl+Enter, New Ctrl+N, Reply Ctrl+Shift+R, Send Ctrl+Enter, Load More Ctrl+M, Reset Filters Ctrl+Shift+F, Esc closes composer, Enter on list opens, Tab chain covers all)

VISIBLE_FOCUS:
focus selectors present in canonical sheet (QPushButton:focus, QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QListWidget:focus); Enter is documented Open route; double-click deliberately NOT wired

WORKSPACE_FLOW:
open/create through first-run raw-custody notice; custody mode explicit

INBOX_FLOW:
bounded metadata page (50 rows default); explicit Load More when continuation exists; AND-only filters with visible active state and Reset; no fuzzy/full-text/semantic search

METADATA_ONLY_SELECTION:
UNREAD select shows metadata only; content note explains Open required

EXPLICIT_OPEN:
Open button + Enter key only route to content; state changes only after backend success; UNREAD → READ visible

NEW_MESSAGE:
recipient selected from registered aliases; composer clears only on backend success

REPLY:
READ-gated with visible disabled reason ("Open the message first to reply"); recipient fixed by backend-resolved original sender; no override

RECIPIENT_MANAGEMENT:
list/add through existing capability; identity card + peer workspace explicit

CUSTODY_SURFACE:
status shows RAW/OS-STORE + backend state + loadability; migrate explicit through existing backend call; honest claims only

REFRESH_POLICY:
explicit only (Refresh button + Ctrl+R); no background mutation of any kind

BACKGROUND_MUTATION:
NONE (no timer/thread/watcher/socket in adapter or GUI)

STATUS_ERROR_VISIBILITY:
persistent strip; never auto-hides; text + colour; level prefixes (OK/WARNING/ERROR); fails stay visible

ZERO_NETWORK_MODEL:
socket tripwire acceptance proves 0 network, 0 model, 0 provider calls

CORE_DEPENDENCIES:
unchanged ([])

GUI_DEPENDENCY:
optional only (gui = ["PySide6>=6.7,<7"])

POST_A2_PRODUCT_DELTA:
P1 + V4-01 + V5-01

FROZEN_A2:
UNCHANGED (d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d)

GUI_FOCUSED_TESTS:
50 additive (adapter 27 + surface 13 + acceptance 10 + dependency-boundary 3), green

CORE_FULL_SUITE:
2358 passed, 0 failed, 0 errors, 0 skipped (2307 inherited + 51 additive)

LINT:
ruff --select E4,E7,E9,F clean on touched Python files

SAIPEN_VALIDATION:
4 FAIL / 22 WARN at closure — all inherited/unrelated:
  1. T-41 release-linkage (SRC-017) — inherited SAIPEN debt
  2. SRC-036 credential gate — inherited SAIPEN debt
  3. stale improve-report fingerprint — inherited SAIPEN debt
  4. root-file-set (3 SAIPEN handoff files in SAIPEN-home tools/) — parallel-session SAIPEN debt, not SAIMAIL
Zero V5-01-attributable failures. One V5-01-attributable item (saiui STATE next_action shape) fixed in T-99.

SAIUI_FINAL_REVIEW:
inline review complete; no findings

REVIEW_FINDINGS:
- assert_canonical() initially assumed 21 distinct colours; UI.md deliberately aliases --selection = --surfaceRaised and --link = --borderHighlight (19 distinct across 21 tokens); check updated to assert exactly that and keep aliases' equality explicit

FILES_CHANGED:
pyproject.toml (+gui extra, +saimail-gui script), README.md (badge parity, works/does-not list), humbox/CURRENT-STATE.md (v5 authority + V5-01 section), humbox/FUTURE-GATES-V5.md (v5 authority, V5-01 DONE), tests/test_local_entrypoint.py + tests/test_clean_install.py (dependency boundary tests), tests/test_repo_consistency.py (V5-01 durability test)

FILES_CREATED:
saimail/gui_adapter.py, saimail/gui_app.py, saimail/gui_theme.py, tests/test_gui_surface.py, tests/test_gui_acceptance.py, spec/25-DESKTOP-LOCAL-MESSENGER-v0.md, humbox/FUTURE-GATES-V5.md, .saipen/evidence/T-97-v5-01-closure.md

SAIPEN_LIFECYCLE:
SCOUT (E-1211) → BUILD (E-1212) → VERIFY PASS (E-1217) → REVIEW PASS (E-1219) → SHIP no-publish (E-1229) → DONE (E-1230) for T-97 (V5-01 implementation).
T-99 closure ticket blocked by VERIFY parser requiring V2-03-specific tokens (dry controls A-L, REVIEWER_BAD_JSON) not applicable to documentation ticket; all work complete and recorded.

ROADMAP_AUTHORITY:
humbox/FUTURE-GATES-V5.md

ROADMAP_REFRESH:
refreshed from evidence; V5-01 DONE, no next gate selected (NONE), none started

NEXT_TARGET:
NONE — STOP (local messenger workflow usable; no observed gap)

BLOCKER:
VERIFY parser blocks T-99 closure (requires V2-03-specific tokens: dry controls A-L all PASS, live terminal REVIEWER_BAD_JSON + NO_ADVICE) not applicable to documentation ticket; all V5-01 work complete and recorded; SAIPEN core 4 FAIL / 22 WARN all inherited

OPERATOR_ACTION:
NONE

NEXT_EXACT_ACTION:
NONE — STOP

SUCCESS PRINCIPLE
The GUI makes the proven local SAIMAIL workflow pleasant without becoming a second SAIMAIL implementation. Selecting is not opening. Opening is explicit. Replying uses the existing backend. Refresh is explicit. Local means local. The canonical UI.md owns the visual language. The backend owns protocol truth. The GUI owns presentation and interaction only.