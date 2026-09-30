# SAIMAIL: Roadmap v5 (POST-V4 / GUI PRODUCT LANE)

Updated: 2026-09-21. Authority: this file, for work after V4-01 and V2-03. It
supersedes `humbox/FUTURE-GATES-V4.md` as the *current* roadmap; v1, v2, v3 and
v4 stay intact and identifiable as completed historical planning evidence. This
is a plan, not permission to publish, to make a live model call, or to change
any proven contract.

Roadmap v4 closed with **NO SELECTED NEXT GATE**: V4-01 (local correspondence
continuation) is DONE via T-95 and V2-03 (reviewer structured output) is DONE
via T-96 with the measured negative `REVIEWER_BAD_JSON`. No mandatory or
observed product gap remained in the CLI-only local workflow.

The operator then supplied a **new explicit product goal**: a GUI /
messenger-like desktop client for the existing local SAIMAIL workflow. That new
operator authority is the only reason this roadmap generation exists.

**V5-01 is DONE via T-97** (Desktop Local Messenger Alpha). No next GUI gate is
selected and none is started.

## 1. Current proven baseline (post-V4)

- Deterministic local composition (FG-05), installable entrypoint and stable maps
  (FG-06), reproducibility discipline (spec/13), persistent workspace (V2-01),
  custody (V3-01), inbox query (P1), correspondence continuation (V4-01).
- `0.0.2a2` frozen, externally proven in a separate Linux / Python 3.13.5
  environment, `NOT_PUBLISHED`; G17 publication authorization ABSENT.
- Checkout is ahead of a2 by `P1 + V4-01` with `U1 + V2-03` as research
  evidence.
- Zero runtime network/model/provider calls on every local path.

## 2. Current limitations (relevant to this lane)

- **L1 — No graphical surface.** Every local action is a CLI subcommand with
  flags. An operator who wants a messenger-shaped workflow has to remember
  command syntax for the daily actions.
- Custody remains raw-by-default (D-053/D-054); `os-store` is explicit.
- Reviewer/generative research remains optional and unproven (L3 in v4).
- SAIPEN/accounting debt is real and separate (L6 in v4).

## 3. Priority principles

- Remove an observed gap; do not accumulate features.
- The GUI is a **presentation layer**. The backend owns protocol truth.
- Prefer the smallest user-facing step that exercises proven capabilities.
- One intentional variable per experiment; the GUI invents no domain semantics.
- Every gate needs a stop condition; a gate whose evidence says "stop" succeeds.
- Do not create a gate merely because a control sounds messenger-like.
- The canonical `<saipen_home>/saipen/UI.md` owns the visual language.

## 4. Lanes

**V5-01 — Desktop Local Messenger Alpha: DONE via T-97.** See section 8.

- Utility/selector lane: closed by U1; no U2 created.
- Security/custody lane: V3-01 DONE; do not reopen without new evidence.
- Distribution lane: `0.0.2a2` verified, `NOT_PUBLISHED`; G17 operator-owned.
- Optional research lane: V2-03 DONE (negative); no generative production work.

## 5. Dependencies

```
V5-01  <- V2-01 (DONE), P1 (DONE), V4-01 (DONE), V3-01 (DONE)   [this gate]
```

- SAIPEN debt is not a dependency of V5-01.

## 6. Selected gate

**V5-01 — Desktop Local Messenger Alpha: DONE via T-97.** See section 8.

## 7. What not to claim

- Do not claim universal utility (`UTILITY_CONDITIONAL` stands).
- Do not claim the GUI is a network messenger: it is **LOCAL ONLY**.
- Do not claim the GUI adds protocol semantics, delivery, threading, dedup,
  custody or discovery authority; the backend owns all of that.
- Do not claim semantic reviewer reliability or any generative capability.
- Do not claim default identity protection: `raw` stays the default.
- Do not claim publication or external verification of the current checkout.
- Do not claim compatibility with any theme other than Golden Default.

## 8. V5-01 — Desktop Local Messenger Alpha (SPECIFICATION)

**Status: DONE via T-97.** Contract source: operator handoff
`V:\_TEMP_\fastprompter_drag\SAIMAIL_20260921_0138.md` (T-97 / SRC-085);
implementation contract `spec/25-DESKTOP-LOCAL-MESSENGER-v0.md`.

- **Observed gap.** The proven local workflow (`init`, `identity`, `recipient`,
  `send`, `inbox` + metadata query, `open`, `reply`, `custody`, `acceptance`) is
  CLI-only. An operator wanting a messenger-like daily workflow has no
  graphical surface, and there is no visible presentation of local-only state,
  durable message state or persistent action evidence.
- **Target.** One usable native desktop application for the existing local
  SAIMAIL workflow, in the operator's environment (Windows 10), that makes
  these daily actions comfortable: open an existing workspace; view and filter
  inbox metadata; explicitly open one message; compose a new message to a
  registered recipient; reply to an already-opened message; refresh the mailbox
  explicitly; see persistent success/error/status evidence. Secondary: inspect
  registered recipients; register a recipient; export the public identity card;
  inspect custody status. Rare: create a workspace; migrate raw custody to
  os-store where supported.
- **Architectural principle.** The GUI is a presentation layer over the
  existing tested public APIs (`saimail.workspace`, `saimail.inbox_query`,
  `saimail.envelope`, `saimail.postoffice`, custody modules). It may validate
  UI input shape, hold ephemeral presentation state, render backend results and
  translate backend status into visible UI state. It may NOT invent
  persistence rules, delivery semantics, recipient discovery, deduplication,
  message lifecycle, thread semantics, background synchronization, protocol
  relations or custody policy.
- **Framework.** A native Python desktop framework: **PySide6** as an
  **optional dependency only** (`gui = ["PySide6>=6.7,<7"]`), never in base
  `dependencies`; a dedicated `saimail-gui` entrypoint with lazy GUI imports, so
  core install and the canonical suite never require Qt. No Electron, webview,
  browser UI, localhost HTTP server, React or remote CDN assets. Missing GUI
  extra exits cleanly with a bounded actionable error, never a traceback.
- **Presentation adapter.** A narrow adapter (`saimail/gui_adapter.py`) wrapping
  only existing public capabilities, with an explicit application state model
  (`NO_WORKSPACE`, `WORKSPACE_LOADED`, `MESSAGE_SELECTED_UNREAD`,
  `MESSAGE_SELECTED_READ`, `MESSAGE_OPENED_CURRENT_SESSION`, `COMPOSING_NEW`,
  `COMPOSING_REPLY`, `BUSY`, `ERROR`). Unsupported backend capabilities are
  recorded as explicit gaps; never faked in UI code.
- **Non-negotiable interaction boundaries.** Selecting a message must NOT open
  it; changing a filter must NOT open anything; displaying metadata must NOT
  decrypt anything. Only the explicit **Open** action may call
  `workspace.open_message`. Reply is unavailable until the target durable state
  is `READ`. Reply recipient is fixed by the backend-resolved original sender
  and cannot be overridden. Refresh is explicit only: no watcher, polling,
  timer, daemon or background sync. Filters are AND-only with visible active
  state and a Reset Filters action; no fuzzy/full-text/regex/semantic search.
  Paging respects the P1 scan budget and cursor with an explicit continuation
  action and no reordering of already-visible rows.
- **Visual authority.** `<saipen_home>/saipen/UI.md` — Golden Default palette
  (21 closed tokens), Vintage Golden design language, Verdana non-antialiased,
  zero rounded corners/shadow/gradient/animation, 2px bevel depth only,
  640x540 usable with no horizontal page scroll, visible focus, full keyboard
  reach, no colour-only meaning, no hover-only meaning, no auto-vanishing
  feedback. Loaded and hashed at Milestone 1; the SHA256 is recorded in
  evidence. UI.md is never packaged as an application runtime dependency.
- **Dependency.** V2-01 (DONE), P1 (DONE), V4-01 (DONE), V3-01 (DONE).
- **Acceptance evidence.** GUI-focused headless/offscreen tests plus adapter
  tests proving: launch; 640x480 usability; no overlapping critical controls;
  explicit Open exists and is reachable; selecting `UNREAD` reveals no content;
  Reply disabled for `UNREAD` with a visible reason; Open transitions visible
  state only after backend success; Reply enabled for `READ`; composer mode
  cannot silently change recipient; Refresh is explicit; active filters visible;
  `Load More` only when continuation exists; backend failure remains visible;
  keyboard focus order reaches daily actions. Plus a two-workspace offline
  end-to-end acceptance through the adapter/model, and zero
  network/model/provider calls.
- **Non-goals.** No network transport, server, cloud accounts, adapters, email
  integration, automatic background refresh, daemon, tray, notifications,
  attachments, avatars, reactions, thread database, recursive correspondence
  traversal, payload full-text search, semantic search, model features,
  telemetry, update checks; no change to SENV2, selectors, PostOffice,
  custody default; no frozen-a2 mutation, rebuild, version bump, tag, push or
  publication.
- **Stop condition.** If the desktop application makes the proven local
  workflow usable at 640x480 under canonical UI.md, with explicit Open, explicit
  Refresh, no background mutation, zero network/model calls and an intact core
  CLI and canonical suite, V5-01 is DONE and evidence is recorded. If a required
  daily action cannot be built without inventing backend semantics, V5-01 closes
  as negative evidence for that action and no protocol change is smuggled in.
- **Outcome (T-97).** `DONE` — positive. The desktop application launches
  (PySide6 optional extra); opening/creating a workspace, metadata-only list
  and filters, explicit Open, New Message, READ-gated Reply with a fixed
  backend recipient, recipient management, identity export and custody
  status/migration are all wired to the existing tested public API through a
  presentation-only adapter; the canonical Golden Default theme is verified;
  640x480 is usable; every daily action is keyboard reachable; failures stay
  visible; the full two-workspace offline acceptance passes under a socket
  tripwire; the core CLI and the canonical suite remain intact; the frozen a2
  candidate is byte-identical and nothing was published. One recorded
  backend-capability gap is reported, not faked (an already-READ message cannot
  be re-opened to re-display content in a later session).
- **Negative evidence closes it:** yes. A measured negative is a successful
  research closure.

## 9. Restart / context-loss entry

1. `humbox/CURRENT-STATE.md` — where the project is and which roadmap is current.
2. `humbox/FUTURE-GATES-V5.md` (this file) — the current roadmap authority.
3. `humbox/FUTURE-GATES-V4.md` — completed Roadmap v4 (historical evidence).
4. `humbox/FUTURE-GATES-V3.md`, `-V2.md`, `FUTURE-GATES.md` — historical.
5. `.saipen/STATE.md`, the current BOARD row and the LOG tail.
6. `<saipen_home>/saipen/UI.md` — the canonical visual authority.
7. `spec/24-LOCAL-CORRESPONDENCE-CONTINUATION-v0.md`,
   `spec/22-LOCAL-INBOX-QUERY-v0.md`, `spec/17-LOCAL-WORKSPACE-v0.md`,
   `spec/20-LOCAL-KEY-CUSTODY-v0.md` — the local capability contracts.

Recovery checklist: current roadmap is v5; V5-01 is DONE via T-97 and no next
V5 gate is selected. Completed gates (v1–v4) must not be reopened. The frozen
`0.0.2a2` candidate is externally proven and `NOT_PUBLISHED`; the frozen
`0.0.2a1` candidate is historical and immutable. Publication remains a separate
operator action (G17 ABSENT).
