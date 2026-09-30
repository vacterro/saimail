# SAIMAIL: Roadmap v6 (POST-V5 / GITHUB IDENTITY + PRESENTATION LANE)

Updated: 2026-09-23. Authority: this file, for work after V5-01. It supersedes
`humbox/FUTURE-GATES-V5.md` as the *current* roadmap; v1 through v5 stay intact
and identifiable as completed historical planning evidence. This is a plan, not
permission to publish, to make a live model call, or to change any proven
contract.

Roadmap v5 closed with **V5-01 DONE via T-97** and no selected next GUI gate.
The operator then supplied a **new explicit distribution/presentation goal**:
make GitHub describe the SAIMAIL that actually exists — canonical logo, social
preview, honest README first screen, public security surface, and a roadmap
that records the new lane. That operator authority is the only reason this
roadmap generation exists.

**V6-01 (GitHub Identity and Presentation Sync) is DONE via T-104.** It was the
only gate executed under T-104; no second gate was started inside it.

## 1. Current proven baseline (post-V5)

- Deterministic local composition (FG-05), installable entrypoint and stable maps
  (FG-06), reproducibility discipline (spec/13), persistent workspace (V2-01),
  custody (V3-01), inbox query (P1), correspondence continuation (V4-01),
  desktop local messenger alpha (V5-01 via T-97).
- Historical `0.0.2a2` remains externally proven in a separate Linux / Python
  3.13.5 environment; that proof applies only to a2. T-106 built and froze the
  exact `0.0.2a3` candidate. It remains `NOT_PUBLISHED`; G17 authorization is
  ABSENT and G13 is `PENDING_EXTERNAL`.
- The checkout is ahead of frozen a3 by checkout-only T-108, T-109 and T-110
  work. T-107 DONE at E-1502: local release-control repair passed independent
  review. SRC-102 confirms `humbox/SAIGIMN.mp3` is user-owned and must
  remain; a narrow exact-path/hash/size manifest covers only that asset.
  Candidate-bound local evidence is under `release/evidence/a3/`.
- Zero runtime network/model/provider calls on every local path.
- Visual sources exist under `pics/` (SAIMAIL1–6, banner); canonical mark is
  `pics/SAIMAIL_LOGO.png` sourced from `SAIMAIL2`.

## 2. Current limitations (relevant to this lane)

- **L1 — Public face lags product truth.** README first screen and GitHub
  repository metadata do not yet communicate the desktop GUI, the local-only
  boundary, or the frozen-vs-checkout split with enough clarity for a new
  visitor.
- **L2 — No SECURITY.md.** The project handles cryptographic identity, sealed
  envelopes, OS credential custody and private-key boundaries but has no
  public reporting/scope document.
- **L3 — Source identity drift (resolved by T-106).** At V6 creation, the tree
  identified as `0.0.2a2` while containing post-a2 product work. T-106 aligned
  that source as frozen candidate `0.0.2a3`; the later T-108/T-109/T-110
  checkout-only changes do not alter the frozen candidate.
- **L4 — READ_REREAD_GAP remains real.** An already-`READ` message cannot be
  decrypted again in a later session. Explicitly out of scope for this lane.

## 3. Priority principles

- Present what exists; never enlarge capability claims.
- Separate frozen-release truth from development-checkout truth.
- Brand clearly without turning aesthetics into release semantics.
- Do not modify protocol semantics, selectors, PostOffice, custody authority
  or frozen release trees inside this lane.
- Every gate needs a stop condition; a gate whose evidence says "stop"
  succeeds.
- One gate at a time: V6-01 is DONE; D3 local repair is DONE via T-107;
  V6-02 remains NOT STARTED.

## 4. Lanes

**V6-01 — GitHub Identity and Presentation Sync: DONE via T-104.**

- Canonical logo asset: `pics/SAIMAIL_LOGO.png` from `pics/SAIMAIL2.png`.
- Social preview: `pics/SAIMAIL_SOCIAL_PREVIEW.png` at 1280×640 PNG <1 MB,
  recomposed (not stretched from the banner).
- README hero: LOCAL ONLY, desktop GUI discoverable, CLI/headless path
  visible, frozen `0.0.2a2` boundary explicit, deep research moved below the
  practical entry surface.
- Public docs: `SECURITY.md`; `CONTRIBUTING.md` only if concise and real.
- Roadmap: this file records V6-01 as the current gate.
- GitHub metadata prepared as exact description + topics; social preview
  asset ready. Settings upload may be `MANUAL_GITHUB_SETTINGS_REQUIRED` and
  does not block V6-01.
- Distribution finding recorded: **CURRENT SOURCE IS MATERIALLY AHEAD OF
  FROZEN 0.0.2a2.**

Utility/selector lane: closed by U1; no U2 created.
Security/custody lane: V3-01 DONE; do not reopen without new evidence.
Distribution/release lane: D3 candidate `0.0.2a3` remains frozen and
`NOT_PUBLISHED`; T-107 DONE after T-108/T-109/T-110. Candidate-bound G15/G16
records document the final local repair; subsequent checkout work is separate.
G13 remains `PENDING_EXTERNAL`, G17 `ABSENT`, and publication `NONE`.
Optional research lane: V2-03 DONE (negative); no generative production work.
GUI product lane: V5-01 DONE via T-97; V5-01 enters the D3 candidate unchanged
(optionally behind `gui` extra; base install stays Qt-free); no new GUI gate selected.
SAIPEN seam lane: **S2 DONE via T-108** (operator request SRC-096; `spec/04`
stage S2, D-057; see §11). Checkout-only: the checkout is ahead of frozen
`0.0.2a3` by S2. S3 promotion proposals already exist (T-10); S4 (registered
SAIPEN extension) is not started and needs its own operator goal.
SAITELEMES lane: **SAITELEMES v0 DONE via T-109** (operator request SRC-097;
`spec/26`, D-058; see §12). Also checkout-only. The SAIPEN-side trigger and
turn-entry hook are filed with the protocolist as a future gate.

## 5. Dependencies

```
V6-01  <- V5-01 (DONE), V4-01 (DONE), P1 (DONE), V3-01 (DONE)   [this gate]
S2     <- V2-01 (DONE, workspace), T-10 (DONE, promotion), spec/04 seam
SAITELEMES v0 <- S2 (DONE, T-108), P1 (DONE, metadata query)
```

- SAIPEN debt is not a dependency of V6-01 or of S2. S2 reads SAIPEN files as
  evidence; it never repairs, validates or writes SAIPEN state.
- D3 — Post-GUI release candidate / source identity alignment — created the
  frozen candidate via T-106 (E-1356). T-107 DONE at E-1502. The earlier
  2512/1 full-suite result predates SRC-102's authorized exact-asset manifest;
  it is historical and is not current G15 authority. Candidate `0.0.2a3`
  (`release/candidates/0.0.2a3/`, wheel
  `saimail-0.0.2a3-py3-none-any.whl`,
  `6427feab24c310184e7fd3ec4bb33dc3f5b1581b00128e2ec08d456fa5aa10cc`, 65
  members, digest `2f75bdb7…`) remains frozen and `NOT_PUBLISHED`. Local
  repair passed 2514 tests and a 111-test independent review. G13 is `PENDING_EXTERNAL`; G17 is
  `ABSENT`; publication is `NONE`. V6-02 is NOT STARTED.

## 6. Selected gate

**V6-01 — GitHub Identity and Presentation Sync: DONE via T-104.** See
section 7. **D3 — Post-GUI candidate 0.0.2a3: local repair DONE via T-107** (see §9).

## 7. V6-01 — GitHub Identity and Presentation Sync (SPECIFICATION)

**Status at file creation: CURRENT (executed under T-104 / SRC-089,
continuation SRC-091).** **Closure: DONE via T-104.**

- **Observed gap.** The public-facing repository surface (README hero,
  canonical logo name, social preview, SECURITY.md, GitHub description/topics)
  does not yet present the product that exists: local-only agent post office,
  optional desktop GUI, CLI/headless path, and an honest frozen-vs-checkout
  boundary.
- **Target.** One coherent presentation state: stable canonical logo asset;
  1280×640 social preview; README first screen that communicates SAIMAIL /
  LOCAL ONLY / desktop GUI available / CLI path available and separates
  frozen `0.0.2a2` from the current checkout (`ahead by P1 + V4-01 + V5-01`);
  concrete `SECURITY.md`; exact GitHub description and topics prepared;
  this roadmap file as authority.
- **Non-goals.** No protocol change; no VERSION bump; no `0.0.2a3` build; no
  tag; no push for ceremony; no publication; no release; no frozen-tree
  mutation under `release/local-alpha/`, `release/candidates/0.0.2a2/`,
  `release/evidence/a2/`; no reread implementation; no network transport; no
  AI features; no capability claims beyond what is proven.
- **Acceptance evidence.** Canonical logo byte-identical to SAIMAIL2;
  social preview 1280×640 PNG under 1 MB; README links and version mirrors
  still consistent with `VERSION`; `SECURITY.md` present; this file present;
  repository consistency suite green; distribution finding recorded.
- **Stop condition.** When the public face describes the SAIMAIL that actually
  exists, frozen-release truth is separate from checkout truth, and the
  canonical suite is green — stop. Do not start D3 or V6-02 inside T-104.
- **Negative evidence closes it:** yes. A measured negative is a successful
  research closure.

## 8. What not to claim

- Do not claim the GUI exists inside frozen `0.0.2a2`.
- Do not claim the current checkout is an externally verified a2 artifact.
- Do not claim cloud messaging, autonomous agents, AI replies or semantic
  reviewer reliability.
- Do not claim publication or external verification of the current checkout.
- Do not claim default identity protection: `raw` custody stays the default.

## 9. Current release decision (D3 local repair complete via T-107)

V6-01 selected one direction after evaluation:

- **D3 — post-GUI release candidate / source identity alignment: LOCALLY COMPLETE;
  T-107 DONE after T-108/T-109/T-110.** Candidate
  `0.0.2a3` (`release/candidates/0.0.2a3/`,
  wheel `saimail-0.0.2a3-py3-none-any.whl`,
  `6427feab24c310184e7fd3ec4bb33dc3f5b1581b00128e2ec08d456fa5aa10cc`, 65 members,
  content digest `2f75bdb7…`. The historical pre-T-106 D3 packet
  `release/evidence/d3/release_decision.json` recorded `NEW_CANDIDATE_REQUIRED`
  (D-056); T-106 built that candidate. The wheel stays frozen and
  `NOT_PUBLISHED`. The earlier 2512/1 full-suite record predates SRC-102 and is
  stale. SRC-102 authorizes retaining the exact user asset through
  `humbox/media-assets.json`; local G15/G16 evidence is candidate-bound.
  G13 is `PENDING_EXTERNAL`, G17 `ABSENT`, publication `NONE`.)
- **V6-02 — READ_REREAD_GAP: NOT STARTED at T-107 closure.** Later SRC-102/SRC-103
  authorize checkout improvements; the saved T-113 design is next for T-114.
- **External operator action:** follow `release/evidence/a3/EXTERNAL_VERIFICATION_REQUEST.md`
  on a genuinely separate machine/VM/host and return raw verifier JSON. No active
  implementation ticket waits solely for G13; publication remains unauthorized.

## 11. S2 — SAIPEN seam bridge (T-108)

**Status: DONE via T-108** (operator request SRC-096: "Возведи и соедини с
SAIPEN как нибудь"; operator goal: "пусть это будет работать как задумано.
humbox как маяк"). Contract: `spec/04-SAIPEN-SEAM.md` "S2 as built", D-057.

- **Observed gap.** SAIMAIL and SAIPEN shared one directory and nothing else.
  The seat was copied by hand, and a message about project work could cite a
  SAIPEN event only in prose, with no witness a reader could re-check.
- **Target.** `saimail-local saipen status|init|cite|verify`: bind the acting
  seat (`--seat` > `SAIPEN_AGENT` > `STATE.agent`, source reported), create the
  ordinary V2-01 workspace at a caller-supplied `--workspace`, cite one LOG
  event as a `KIND:O` record whose `EV` is the sha256 of the exact LOG line,
  and re-check a citation by re-deriving it from the reader's own LOG bytes.
- **Non-goals.** No write into `.saipen/`; the library never names SAIPEN
  memory (I1 structural test); no mailbox inside a project tree; no new wire or
  state field; no SAIPEN extension registration (S4); no SAIPEN debt repair; no
  version bump, rebuild, tag, push or publication; the frozen `0.0.2a3` wheel
  is untouched and claims nothing about S2.
- **Acceptance evidence.** `tests/test_saipen_bridge.py` green;
  `tests/test_i1_inert_payload.py` green for the new module; full canonical
  suite green; live: E-1362 cited, sealed `opus -> reviewer`, opened `READ`
  with the cited content identity, `CITATION_VERIFIED`.
- **Measured failures that shaped it** (D-057): library naming SAIPEN memory
  (I1 red), repo mailbox (consistency red), last owner used as actor (operator
  report), EV-only verifier accepting forged `SUBJ`/`CLAIM` (REVIEW P1, red
  before fix and green after).
- **Stop condition.** One seat binding, one citation, one re-check, and a green
  canonical suite. Stop. S4 is not started inside T-108.

## 12. SAITELEMES v0 — telegrams between running agents (T-109)

**Status: DONE via T-109** (operator request SRC-097: "SAITELEMES - это как
телеграмма для другого работающего агента, это должно происходить автоматически
пока выясняется текущий аудит чтобы решались задачи эффективнее"). Contract:
`spec/26-SAITELEMES-v0.md`, D-058.

- **Observed gap.** A finding owned by another running agent waited for a human
  relay: the SAIPEN protocolist heard of the T-108 defects only after the operator
  asked, and the host cross-session message expired unapproved.
- **Target.** `saimail-local saipen telegram` sends one telegram in one call. The
  sender is the acting seat, the TOPIC is the SAIPEN Work id, the kind comes from
  the closed SENV2 set, and the body is a claim or an S2 citation.
  `saimail-local saipen telegrams` is the bounded, header-only turn-entry read.
- **Non-goals.** No `TELEGRAM` kind, no importance field, no daemon, no network, no
  auto-open, no Work created by arrival, no agent discovery registry, no SAIPEN
  change from this repository.
- **Acceptance evidence.** `tests/test_saitelemes.py` green; full canonical suite
  green; SAIPEN protocolist notified live and in its case file
  (`_SAIPEN/future_gate/FUTURE GATE — SAITELEMES AUTOMATIC AGENT
  TELEGRAMS_20260922.md`), with receipt acknowledged.
- **Stop condition.** One send and one turn-entry read, seat-guarded, on existing
  wire. The SAIPEN-side automatic trigger is the protocolist's to triage. Stop.

## 13. SAIPEN Work Desk v0 (T-110)

**DONE via T-110; development checkout only.**

The operator's new improvement request (SRC-099), clarified as SAIMAIL with
HUMBOX as the guide, selects a work desk connected to SAIPEN. Later steering
requires SAIPEN participation at entry.

- **Implemented:** `saipen enter` checks local project lineage and workspace
  seat; `saipen brief` joins observed work with one bounded unread page,
  preserving other topics and detecting context changes across continuation.
  SAIPEN `init` and `telegram` use the same participation prerequisite.
- **Authority:** this is local admission, not proof of SAIPEN compliance;
  standalone APIs remain available. SENV2 authentication is unchanged.
- **Evidence:** `tests/test_saipen_brief.py`, existing S2/SAITELEMES/I1 suites.
  Full regression: 2477 passed; focused review: 116 passed. An initial run had
  eight fixture errors from one Windows rename refusal; a fresh short temporary
  path passed the affected 22 tests and the complete suite. Disabling the entry
  gate in an isolated process made all four admission controls fail as expected.
  Contract: `spec/27-SAIPEN-WORK-DESK-v0.md`; operator guide:
  `humbox/SAIPEN-WORK-DESK.md`.
- **Boundary:** checkout-only, outside frozen `0.0.2a3`; no publish, extension
  registration, automatic send/open, or SAIPEN memory writes.
- **Next evaluation:** V6-02 receiver reread continuity, then a SAIPEN-owned
  turn-entry hook. Neither is started in T-110. T-107 release-control repair
  remains separate work.

## 10. Restart / context-loss entry

1. `humbox/CURRENT-STATE.md` — where the project is and which roadmap is current.
2. `humbox/FUTURE-GATES-V6.md` (this file) — the current roadmap authority.
3. `humbox/FUTURE-GATES-V5.md` — completed Roadmap v5 (historical evidence).
4. `humbox/FUTURE-GATES-V4.md`, `-V3.md`, `-V2.md`, `FUTURE-GATES.md` — historical.
5. `.saipen/STATE.md`, the current BOARD row and the LOG tail.
6. `<saipen_home>/saipen/UI.md` — the canonical visual authority.
7. `spec/25-DESKTOP-LOCAL-MESSENGER-v0.md`, `spec/17-LOCAL-WORKSPACE-v0.md`,
   `spec/20-LOCAL-KEY-CUSTODY-v0.md` — product contracts.

Recovery checklist: current roadmap is v6; V6-01 is DONE via T-104; T-106 is
historical DONE and T-107 DONE at E-1502; T-108/T-109/T-110 are DONE. STATE owns later work.
Candidate `0.0.2a3` remains frozen and `NOT_PUBLISHED`; final G15/G16 evidence
records local repair after SRC-102's exact-asset manifest. G13 is
`PENDING_EXTERNAL`, G17 `ABSENT`, publication `NONE`; V6-02 is NOT STARTED.
S2 SAIPEN seam bridge is DONE via T-108 (checkout-only, ahead of frozen
`0.0.2a3`, §11); SAITELEMES v0 is DONE via T-109 (§12); Work Desk v0 is DONE
via T-110 (§13); completed gates (v1–v5) must not be reopened.
The frozen `0.0.2a2`
candidate is externally proven and `NOT_PUBLISHED`; the frozen `0.0.2a1`
candidate is historical and immutable. Publication remains a separate operator
action (G17 ABSENT).
