# V5-01 — DESKTOP LOCAL MESSENGER ALPHA v0

Status: done (T-97). Contract for `saimail/gui_adapter.py`,
`saimail/gui_app.py`, `saimail/gui_theme.py`, the optional `gui` extra, the
`saimail-gui` entrypoint and the focused tests in
`tests/test_gui_surface.py`, `tests/test_gui_acceptance.py` and the clean
install / entrypoint boundary tests.

## 1. Why this document exists

The proven local workflow (`saimail-local init/identity/recipient/send/inbox/
open/reply/custody/acceptance`) is entirely CLI. An operator who wants a
messenger-shaped daily workflow has no graphical surface, no visible
presentation of local-only state, durable message state or persistent action
evidence. V5-01 adds the smallest useful step: one native desktop application
that presents those existing capabilities. It adds no protocol rule, no wire
field, no second implementation, no database, no network path and no new
cryptography.

## 2. Architectural principle

**The GUI is a presentation layer.** The backend owns protocol truth:
`saimail.workspace`, `saimail.postoffice`, `saimail.inbox_query`,
`saimail.envelope` and the custody modules remain the only authority for
persistence, delivery, recipient discovery, deduplication, lifecycle, threads,
synchronization, protocol relations and custody policy. The GUI may validate UI
input shape, keep ephemeral presentation state, render backend results and
translate backend status into visible UI state. It may not invent any of the
backend-owned semantics.

## 3. Framework and dependency boundary

- **PySide6** is the framework, as an **optional extra only**:
  `gui = ["PySide6>=6.7,<7]`. It never enters base `dependencies` (which stays
  `[]`), and no other `saimail/*` module imports it.
- Entrypoint: `saimail-gui = "saimail.gui_app:main"`, with lazy GUI imports.
  With the extra absent, the entrypoint exits cleanly with one bounded
  actionable line (`pip install "saimail[gui]"`), never a traceback.
- `saimail-local`, the core package and the canonical zero-dependency suite must
  work and run without Qt.
- No Electron, webview, browser UI, localhost HTTP server, React or remote CDN
  asset.

## 4. Presentation adapter

`saimail/gui_adapter.py` is the whole domain-facing surface of the GUI. It wraps
only existing public capabilities: `load_workspace`, `init_workspace`,
`identity_card` / `export_identity_card`, `list_recipients`, `add_recipient`,
`query_inbox` / `list_inbox`, `open_message`, `reopen_message`, `send_message`,
`reply_message`, `custody_status`, `migrate_workspace_custody`. It implements
no domain semantics and it records, rather than fakes, any backend-capability gap.

### 4.1 Application state model (closed set)

`NO_WORKSPACE`, `WORKSPACE_LOADED`, `MESSAGE_SELECTED_UNREAD`,
`MESSAGE_SELECTED_READ`, `MESSAGE_OPENED_CURRENT_SESSION`, `COMPOSING_NEW`,
`COMPOSING_REPLY`, `BUSY`, `ERROR`. Presentation state is never protocol
authority.

### 4.2 Interaction invariants (non-negotiable)

- **Selecting a message does not open it.** `select()` reads one row's metadata
  from the already-loaded page; only `open_selected()` may call
  `workspace.open_message`, and content becomes visible only after that call
  returns.
- **Refresh is explicit.** There is no watcher, timer, thread, poll or daemon;
  the visible page changes only through `refresh()` (or an explicit `Load More`
  continuation) and rows already visible never jump or reorder.
- **Reply is READ-gated and recipient-fixed.** `reply_message` is reached only
  when the target durable state is `READ`; the recipient is resolved by the
  backend from the original sender, never chosen by the caller.
- **No optimistic mutation.** A failed Open keeps the message selected and shows
  persistent failure evidence; the composer clears only after backend success.
- **Filters are AND-only** with visible active state and a Reset action; there is
  no fuzzy/full-text/regex/semantic search.

### 4.3 Receiver re-read continuity and former capability gap (T-113)

Historically, `workspace.open_message` was the sole decryption path and refused
`ALREADY_READ`, leaving READ messages from prior sessions viewable only by
metadata with a reason label (`REASON_REOPEN_NOT_READ` / `REASON_REOPEN_NONE`).
T-113 resolves this gap: `workspace.reopen_message` provides an explicit,
fail-closed path to re-authenticate and decrypt an already-READ message across
sessions. The GUI exposes this via `reopen_selected()` and the explicit `Reopen`
button, while preserving the invariant that selecting or refreshing a row never
automatically decrypts content.

## 5. Visual compliance

All visual values come from the canonical `<saipen_home>/saipen/UI.md`
(Golden Default, Vintage Golden, 21 closed tokens, Verdana non-antialiased,
zero radius/shadow/gradient/animation, 2px bevel only, 640x480 usable, visible
focus, no colour-only meaning, no hover-only meaning, no auto-vanishing
feedback). `saimail/gui_theme.py` is the single transcription, verified by
`assert_canonical()` (21 tokens, values equal to the canonical table, no
non-canonical hex in the rendered style sheet). UI.md is never packaged as an
application runtime dependency.

## 6. Result / evidence

- Focused tests: `tests/test_gui_surface.py` (adapter state model and the
  offscreen Qt window: 640x480 usable, no overlapping critical controls,
  explicit Open reachable, UNREAD select reveals no content, Reply disabled for
  UNREAD with a visible reason, Open transitions visible state only after
  backend success, filters visible and resettable, Load More only when
  continuation exists, failures stay visible, keyboard focus order, Enter on
  the list is the documented Open route, double-click is NOT connected to Open).
- Acceptance: `tests/test_gui_acceptance.py` — the full two-workspace offline
  scenario through the GUI layer (create/exchange/register/send/refresh/
  select/Open/Reply/reply-discover/restart), asserting the mailbox tree is
  byte-identical across restarts and the whole path runs under a socket
  tripwire with zero network attempts.
- Dependency boundary: `tests/test_local_entrypoint.py` and
  `tests/test_clean_install.py` prove the base install works and `saimail-gui`
  exits with the bounded message when Qt is absent.
- Full canonical suite at closure: 2357 passed, 0 failed, 0 errors, 0 skipped.
  ruff `--select E4,E7,E9,F` clean on touched files. Frozen `0.0.2a2`
  (`d1f97537…`) and `0.0.2a1` (`ed930e38…`) byte-identical. Zero
  network/model/provider calls. `publication = NONE`; G17 ABSENT.

## 7. What this does NOT claim

V5-01 is a local messenger presentation, not a networked messenger, not email
integration, not a general chat system. It does not promise chat bubbles,
avatars, reactions, attachments, notifications, tray, background polling, a
thread database, recursive correspondence traversal, payload full-text or
semantic search, model features, telemetry, update checks, online accounts,
remote synchronization or any change to SENV2, selectors, PostOffice, custody
default or any existing contract. The GUI never proves or claims identity
beyond what the backend keys provide, and it does not claim the default
workspace identity is protected: `raw` stays the default.
