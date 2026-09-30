# saiui design package — SAIMAIL V5-01 Desktop Local Messenger Alpha

Adoption basis (required read order completed):
1. own STATE/BOARD/LOG — empty instance, UI-001 CLAIMED
2. `.saipen/extensions/subs/PROTOCOL.md` (read)
3. `.saipen/extensions/subs/saiui.md` (read)
4. `<saipen_home>/saipen/UI.md` — loaded by reference, never copied
   - absolute path: `V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN\saipen\UI.md`
   - SHA256: `162fa0574533456541b65fb79f1893fef863e9143aaab94ba99e0ea938ea5dd0`
   - bytes: 18655, lines: 429, revision line: none present
   - palette: Golden Default, closed set of 21 values
   - design language: Vintage Golden (Win95 geometry, instant states, 2px bevel)
   - viewport: 640x540 CSS px, no horizontal page scroll
   - type: Verdana, non-antialiased, `!important`, sizes 10/11/12/14/16 only
   - depth: 2px bevel only; no radius/shadow/gradient/blur/transparency/animation
   - focus: `outline: 1px dotted var(--textPrimary); outline-offset: -4px`
   - primary target >= 24px; secondary >= 16px; dense default 20px
5. target project UI implementation — none exists (new surface); UI tests — none
6. public backend/API surfaces actually called (read from `saimail/workspace.py`,
   `saimail/inbox_query.py`, `saimail/custody.py`)
7. README/screenshots last — not used as executable truth

## 1. Task Map

DAILY
- Refresh inbox
- Select message (metadata only)
- Open message explicitly
- New Message
- Reply
- Inspect status/error

SECONDARY
- inbox filters (sender, topic, kind, state)
- registered recipient selection
- inspect message metadata
- inspect replies / REF relation (metadata-only `inbox --ref`)

RARE
- Open Workspace
- Create Workspace
- Export Identity Card
- Add Recipient
- Custody Status
- Custody Migration

DESTRUCTIVE
- none (V5-01 adds none, and invents no placeholder)

RECOVERY
- show actionable backend failure information without stack traces; keep the
  selection and never mutate state optimistically

## 2. Action/State Map (visible controls)

| Control | exact action | scope | preconditions | enabled | disabled reason | success evidence | failure evidence | keyboard |
|---|---|---|---|---|---|---|---|---|
| Open Workspace | load workspace from a directory | one root | none | always (header + first run) | — | status bar `workspace opened` + header fills | status bar `WORKSPACE_MISSING: no workspace marker at <path>` | `Ctrl+O`, header button `Open Workspace` |
| Create Workspace | `init_workspace(seat, custody)` | one root | none | always | — | status bar `workspace created` + custody notice text | named `CUSTODY_*` / `BAD_SEAT` / `WORKSPACE_CONFLICT` code + reason | first-run button |
| Refresh | bounded metadata query page 1, reset cursor | current filter | workspace loaded | workspace loaded | `Open a workspace to refresh the mailbox.` | status bar `inbox refreshed (N rows examined)` | status bar with exact code | `Ctrl+R`, header button `Refresh` |
| inbox row select | move selection, show metadata | one row | rows exist | rows exist | `Inbox is empty.` | detail region shows metadata only + `UNREAD — content not loaded. Open to read.` | n/a | `Up/Down`, `Tab` into list, list keystrokes |
| Open | `open_message(envelope_id)` | selected row | row selected | row selected AND state==UNREAD | `Already open in this session (READ).` | detail shows returned record fields; state chip flips to READ | state NOT changed; status bar `OPEN refused: <CODE>`; selection kept | `Ctrl+Enter` / `Open` button; also `Enter` when list focused |
| Load More | next bounded page, append | current filter | `exhausted` true | `exhausted` true | hidden when no continuation | `N more rows examined; Load More hidden at end` | status bar with exact code | `Ctrl+M` / button |
| New Message | composer mode NEW | — | workspace loaded, >=1 recipient | workspace loaded AND recipients>0 | `Register a recipient to compose a message.` | composer clear only after backend success; status `message sent ACCEPTED to <alias>` | draft kept; status `SEND refused: <CODE>` | `Ctrl+N` |
| Reply | composer mode REPLY for READ target | selected row | selected row READ | selected row READ | `Open the message first to reply.` (visible, always) | status `reply sent ACCEPTED (ref <ENVELOPE_ID>)` | draft kept; status with exact code | `Ctrl+Shift+R` |
| Send | `send_message` / `reply_message` | composer | composer mode set, body non-empty | body non-empty | `Type a message to send.` | see above | see above | `Ctrl+Enter` |
| Close composer | discard composer mode | — | composing | composing | hidden otherwise | status `composer closed` | — | `Esc` |
| filters (sender/topic/kind/state) | applied on Refresh only | current query | workspace loaded | workspace loaded | `Open a workspace to filter.` | status `filters active: topic=ci state=UNREAD` | BAD_QUERY_FILTER code | `Tab` chain, combo keyboard nav |
| Reset Filters | clear all filters + refresh | current query | any filter set | any filter set | `No active filters.` | status `filters cleared` | — | `Ctrl+Shift+F` |
| Add Recipient | `add_recipient(alias, card, peer root)` | one recipient | workspace loaded | workspace loaded | `Open a workspace to manage recipients.` | status `recipient <alias> registered for seat <seat>` | `RECIPIENT_CONFLICT` / `RECIPIENT_IDENTITY_MISMATCH` / `DELIVERY_TARGET_UNAVAILABLE` | rare region, `Tab` |
| Recipient list | `list_recipients` | all | workspace loaded | workspace loaded | as above | alias + seat rows, metadata only | status code | rare region |
| Export Identity Card | `export_identity_card(dest)` | one file | workspace loaded | workspace loaded | as above | status `identity card exported to <path>` + seat + kid | `CARD_CONFLICT` | rare region |
| Custody Status | `custody_status` | one workspace | workspace loaded | workspace loaded | as above | mode `RAW`/`OS-STORE`, backend state, loadable | code shown verbatim | rare region |
| Custody Migration | `migrate_workspace_custody` | one workspace | workspace loaded AND mode==RAW | mode==RAW | `Identity is already in OS-store custody.` | `CUSTODY_MIGRATED`, fingerprints unchanged | `CUSTODY_*` verbatim; raw workspace still usable | rare region (explicit, non-default focus) |

## 3. Capability Gap Map

- existing capability hidden by UI → all of: workspace open/create, identity
  export, recipient add/list, send, inbox list/query, open, reply, custody
  status/migrate. This whole surface is being exposed for the first time; the
  GUI hides nothing that the CLI exposes for daily use.
- existing capability exposed ambiguously → none found (no prior UI).
- UI-only missing behavior → persistent status/evidence strip; visible
  local-only banner; metadata-vs-content distinction chip; selection bevel;
  composer mode indicator; explicit Load More state.
- **missing Core/backend contract → NONE.** Every control in section 2 maps to
  an existing, tested public function. No UI control is faked and no backend
  request is raised by V5-01.
- documentation drift → none found in the called surfaces.
- rejected noise → chat bubbles, avatars, reactions, attachments, notifications,
  tray, search-by-payload, semantic/recursive threads, auto-refresh, unread
  badges that imply remote presence, any "online" indicator (documented as
  rejected; V5-01 non-goals).

Explicit backend-capability gaps recorded: **none**. A delete/clear/reset
control is deliberately NOT added; per charter, no fake disabled placeholder was
invented for a capability the backend does not have.

## 4. Information Architecture (640x540)

    row 0   title/header region        SAIMAIL — LOCAL ONLY — seat — custody — [Refresh]
    row 1..N inbox region (left, ~55%) | detail region (right, ~45%)
              Raised header row         Metadata before Open; record fields after
              Sunken selected row       [Open] [Reply] + visible disabled reason
    row N+1 composer region            mode chip NEW|REPLY + recipient + body + [Send][Close]
    row N+2 secondary/rare region      Recipients | Identity | Custody  (text-labelled)
    row N+3 status strip               persistent evidence, never auto-hidden

Daily actions are on the main surface; secondary in one stable named region;
rare behind text-labelled controls in the same stable region. No destructive
control exists. `Local only` is stated in text, never implied by an icon.

## 5. Visual system (Golden Default only)

The 21 canonical values are used verbatim; there is no second palette and no
22nd colour. Semantic aliasing only:

    background -> --background            window/page
    backgroundSoft -> --backgroundSoft     inactive strip
    surface -> --surface                  sunken inputs, title bar, sunken selection
    surfaceRaised -> --surfaceRaised      raised buttons/panels, selected-row base
    surfaceAlt -> --surfaceAlt             hover
    borderDark -> --borderDark            bevel dark edge
    bevelLight -> --bevelLight            bevel light edge
    borderHighlight -> --borderHighlight  focus accent, link
    borderMuted -> --borderMuted          separator
    textPrimary -> --textPrimary          body
    textSecondary -> --textSecondary      metadata
    textMuted -> --textMuted              disabled label (never opacity)
    accentTeal/accentTealDeep             reserved; not used in V5-01 chrome
    success -> --success   warning -> --warning   danger -> --danger
    dangerText -> --dangerText            error text (readable without colour)
    selection -> --selection              selected row colour (bevel first)
    compareBack -> --compareBack          read-only technical values, content pane
    link -> --link

Selection rule followed literally: **bevel first (`--selection` equals
`--surfaceRaised` in the palette, so colour alone cannot carry selection),
colour second.**

Status vocabulary uses success/warning/danger exactly once each and never
overlaps: success = completed action, warning = operator action required,
danger = refused/failed. Every one of them also carries a leading text token
(`OK`, `ACTION`, `REFUSED`) so the meaning survives a colourless screenshot.

## 6. Patch wave

Wave 1 (existing API exposure, safe, measurable): the new GUI surface + theme
module. No backend change. See OUTBOX `UI-001`.

Wave 2 (new backend contracts): **none requested.**

## 7. Verification performed (pen)

- canonical token table compared value-by-value against `saipen/UI.md` lines
  119-146 — 21/21 exact matches, 0 extra colours;
- QSS generation asserted to contain only canonical hex values;
- token-count and closed-set assertions pass;
- the theme module imports with no Qt and no third-party import.

640x480 reachability and keyboard reach are asserted in the project's own GUI
test suite after integration (Core's VERIFY), because the pen has no live Qt
harness of its own. Residual risk recorded in the OUTBOX.
