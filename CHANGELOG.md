# Changelog

## Unreleased

- The beacon folder is now swept as a whole (T-155, T-158, T-159, T-160): a new
  `humbox/**/*.md` that no receipt accounts for fails the suite, identified by its
  path relative to `humbox/` so a nested file cannot pass on a basename a captured
  file already bound. No receipt can carry that binding -- the intake grammar has no
  source-path field -- so captured beacons are bound in `BEACON_BINDINGS` beside
  the check, and each row is verified against its receipt's own capture digest, so
  a binding is a fact rather than a claim. Registration is deliberately *not* read
  out of the BOARD or the journal: those are free text that the protocol is
  actively pruning, and a sentence naming a file while investigating it used to
  pass as a capture. The twenty-four pre-intake files that were never captured --
  ten of which had been passing on nothing but an incidental journal mention --
  are named in `LEGACY_UNREGISTERED_BEACON` rather than skipped in silence.

- Operator interruption is now a receiver-owned gate, not a sender's prose
  (T-154, spec/35). One Work produced five letters in 41 minutes -- tentative
  repair, correction, correction of the correction, retraction, real hard stop --
  and the existing README and `--help` rule did not stop it, because it was
  prose. New `saimail/operator_interrupt.py` separates *a message durably
  exists* from *an operator interruption was presented*. Only
  `OPERATOR_ACTION_REQUIRED`, `DATA_OR_MONEY_RISK` and
  `CROSS_PROJECT_CRITICAL_DISCOVERY` may interrupt; a declaration marked
  unsettled is never admitted; one decision identity gets exactly one
  interruption, so corrections, retractions, rewordings and split issues
  supersede rather than add; presentation reuses the existing `human_attention`
  queue at one per 24h by default with no second scheduler, and `origin` and
  `presence` are receiver-supplied so a sender can neither declare itself human
  nor claim presence; active-chat presence keeps an ordinary action request in
  the chat and an absent signal means `UNKNOWN`, not absent; the visible body is
  capped at 600 UTF-8 bytes / 4 lines and oversized requests are refused, never
  truncated. Zero presentations is a successful outcome. Generic human-authored
  `saimail-local send` is untouched, and the GUI mailbox view is unchanged.
  Admission also refuses a reclassification of an already-admitted decision
  (`INTERRUPT_BAD_CLASS`) and a repeated JSON key in the sealed claim, and the
  pending set is capped at eight waiting decisions: at the cap the next arrival
  of any class is refused with `PENDING_FULL` and stays durable mail, because
  evicting one would strand an attention candidate the queue cannot retire.

- Concurrent recipient registration (T-148): an OS lock covers fresh registry
  admission and atomic persistence across API and CLI processes. Distinct
  additions survive and competing identities cannot silently replace an alias.
  Lock/persistence refusals are structured; failed lock acquisition closes its
  descriptor. Listing stays read-only and registration stays keyless.

- Public recipient management (T-147): recipient list/add use the validated
  public workspace view and work with locked message custody. Invalid or
  unreadable identity-card files return structured RECIPIENT_MALFORMED errors.
  Public identity checks and alias conflicts remain fail-closed; sending still
  requires private keys. Zero peers remain valid and the optional real-use
  study does not block product development.

- Real-use recorder repair (T-144): the unchanged T142_REAL_USE_1 registration
  now admits a validated, bounded append-only observation sequence. Entry 1
  remains byte-identical; later entries observe the actual owned Work and bind
  canonical context and predecessor hashes. Repeated Work cannot inflate context
  boundaries. Empty observations and unproven independent behavior remain valid.

- Feedback provenance (T-143): metrics and host cycle/focus identify workspace
  receiver decisions about received letters. Older peers retain UNKNOWN origin;
  malformed present origin refuses projection. Sealed assessments of outgoing
  proposals still require explicit receiver review. Counts and temporal rules
  are unchanged; this establishes protocol semantics, not field improvement.

- Evolution objective audit (T-142): twelve humbox directions mapped to current
  source and behavioral evidence; controlled successor description separated
  from real Work execution. An immutable six-entry real-use registration begins
  with an empty configured T-142 observation. Host adoption and independently
  measured receiver/revision/successor behavior remain open. Evidence:
  `humbox/EVOLUTION-AUDIT.md`, `lab/analysis/evolution_audit_T142.md`.

- Compact CLI transport (T-141): optional `saipen letter focus` and negotiated
  `HostClient.focus(..., prefer_cli=True)` preserve metadata with independent
  client validation and older-peer fallback. Registered wire bytes fall from
  4841 to 2643 while calls and visible context stay unchanged. Existing focus
  and full cycle remain available. Evidence: `lab/analysis/cli_focus_T141.md`.

- Dated feedback (T-140): a host-owned seven-day assessment window separates
  eligible informational guidance from lifetime history. Expired live decisions,
  old and future assessments are counted explicitly; recent terminal corrections
  remain assessment-only. Cycle shares one clock with desk/metrics; focus validates
  the basis and marks older peers UNKNOWN. History, retries and sealed TTL stay
  intact. Evidence: `lab/analysis/feedback_signal_age_T140.md`.

- Compact agent context (T-139): opt-in `HostClient.focus` preserves current
  Work, reading references, latest reason feedback and continuation/coverage
  while reconstructing operations locally. Registered comparison reduces
  agent-visible normalized JSON from 3319 to 978 bytes (70.5%); wire payload
  and full cycle API stay available. Evidence: `lab/analysis/agent_focus_T139.md`.

- Recurring host evaluation (T-138): preregistered fresh-process replay of real
  T-137 evidence, equivalent separate-discovery/cycle measurements and 15
  continuity/feedback controls. Cycle uses 2 rather than 3 CLI invocations;
  normalized JSON grows 16.8%. Scripted choices and unfavorable outcomes remain
  explicit in `lab/analysis/agent_cycle_T138.md`.

- Agent cycle entry (T-137): one keyless observation over mail, unfinished
  decisions, predecessor reserve and reason feedback; bounded context-bound
  pagination, explicit reading suggestions and optional independent-host
  negotiation through `HostClient.request("cycle", ...)`.

- Receiver feedback loop (T-136): sealed replies for every explicit disposition,
  distinct revision identities with stable retries, closed reason metrics and
  informational communication hints. The existing keyless work brief recognizes
  this project's namespaced letters. Workflow: `humbox/EVOLUTION.md`.

- Useful correspondence and encrypted human desktop (D-066): structured utility
  contracts, project-isolated recipient topics, explicit receiver outcomes,
  result evidence/replies and successor reserve; negotiated bounded CLI host
  adapter; Golden Default tabs, master-password custody, independent recovery
  backup and restore. Real SAIFREN cycle and regression evidence are in
  `lab/analysis/institution_20260930.md`. Current checkout only; frozen artifacts
  and adjacent projects unchanged. Operator guide: `humbox/INSTITUTION.md`.

- Letter etiquette (SRC-084): the operator's mailbox held two agent letters that were completion
  reports already written in the chat. `README.md` gains "When a letter is worth writing" (chat
  first; a letter only when the operator is not reading AND it changes what they must do or
  decide; never a finished ticket, results or a summary; one per decision) and
  `saimail-local send --help` states it. The rule an agent is told lives in ZAICODE's prompt.
  Documentation and help text only; `tests/test_letter_etiquette.py` pins the help text.

- Mesh torture + contended-lock fix (T-123, D-065, `spec/DECISIONS-D065.md`):
  `tests/test_mesh.py` proves the §16 delivery chain under full meshes of
  2/4/8/12 agents (two racing processes per agent, every fact retried, all
  agents killed inside the outbox lock and restarted): exactly one message per
  fact per sender, intact indexes, no FAILED intents, no wedged restart. The
  defect the torture found — concurrent first deliveries into a fresh mailbox
  failing with `DELIVERY_IO_ERROR` because Windows refuses the initializing
  write into a byte another process already locked — is fixed in
  `_OsFileLock.__enter__`: the contended initialization is waited for under the
  ordinary lock deadline. `tests/test_mailbox_lock_init.py` is red on pre-fix
  bytes and green after. Checkout-only.

- Workshop policy mapped (T-118, D-064, `spec/32-INTER-AGENT-WORKSHOP-POLICY-v0.md`):
  the operator's inter-agent workshop policy (SRC-107) with each rule bound to its
  SAIMAIL mechanism and a named live control; the consistency suite fails if a
  control disappears or a SAIMAIL state set gains `ACTED`. Two rules wait for the
  SAIPEN halves of V6-07/V6-08. Docs and oracle only.

- V6-08 SAIMAIL half (T-122, D-063, `spec/31-SAITELEMES-NOTIFY-v0.md`):
  `saimail-local saipen notify` sends one automatic telegram per fact for a closed
  trigger set (`blocker`, `finding`, `dependency`, `ownership`, `handoff`, `reply`)
  to an admitted participant: trigger-fixed kind, Work from STATE or BOARD,
  deterministic idempotency key, durable outbox (intent kept when the key store is
  locked), a receiver attention budget with suppression that writes nothing, and
  piggybacked retries. The capability document gains a `notify` entry; the outbox
  gains a stable content identity and a budget gate. Checkout-only.

- V6-07 SAIMAIL half (T-121, D-062, `spec/30-SAIPEN-CAPABILITIES-v0.md`):
  `saimail-local saipen capabilities` returns one versioned, keyless,
  plaintext-free capability and health document (`SAIMAIL_CAPABILITIES_1`) with
  exit code 0 for every state: per-capability AVAILABLE/DEGRADED/REQUIRES_HUMAN/
  UNAVAILABLE/UNVERIFIED states, closed reasons, outbox health, and awareness
  counts only when the acting seat owns the mailbox. Checkout-only.

- V6-06 participant registry (T-120, D-061, `spec/29-PARTICIPANT-REGISTRY-v0.md`):
  `saimail.participants` and `saimail-local saipen participant
  admit|revoke|resolve|list`. Automation routes only to seats explicitly admitted
  for the SAIPEN project (lineage from the admitted binding), each pinned to its
  registered identity and to a subset of the closed notify trigger set, which maps
  to existing SENV2 kinds. Resolution refuses unknown project or seat, trigger
  outside the admission, self-address and identity drift. Receiver-owned trust
  unchanged; keyless. Checkout-only.

- V6-05 durable outbox (T-119, D-060, `spec/28-DURABLE-OUTBOX-v0.md`):
  `saimail.outbox` and `saimail-local outbox send|resume|retry|status`. A send is an
  intent keyed by an idempotency key (PENDING -> SEALED -> DELIVERED | FAILED, atomic
  writes); it is sealed once and persisted before delivery, and every retry
  replays the same bytes, so crashes, retries and concurrent writers yield one
  logical message. Plaintext leaves the intent when sealed; transient failures
  back off, terminal ones wait for an explicit `retry`; status and sealed delivery
  need no private key. Additive: `send`, `reply` and the wire are unchanged.
  Checkout-only.

- V6-03 SAIPEN turn-entry hook evaluation (T-117, D-059): SAIPEN T-1497 already
  counts unread telegrams at `continue`/`status` through `saimail-local --json
  saipen telegrams` when `SAIMAIL_WORKSPACE` is set; T-117 verified that end to
  end. Header-only reads (`inbox`, `saipen telegrams|enter|brief`) now load the
  secret-free `workspace.load_workspace_headers` view: every public
  marker/identity check, no private key, no credential-store read. In os-store
  custody they no longer retrieve both private keys on every turn entry, and a
  locked store still yields counts. Open, reopen, send, reply and `saipen
  telegram` keep the full fail-closed load. The fields SAIPEN parses are pinned
  by `tests/test_turn_entry_headers.py`. Checkout-only; `spec/26` section 7.

- SAIPEN Work Desk v0 (T-110): `saipen enter` checks project lineage and the
  acting workspace seat; `saipen brief` groups a bounded unread page by current
  work topic while preserving other topics and accurate page coverage. Cursor
  continuation requires the same observed work/mailbox context. SAIPEN `init`
  and `telegram` now require project IDENTITY; standalone mailbox APIs remain
  available. Admission is local binding, not protocol-compliance attestation.
  No mail is opened by entry/brief. Checkout-only; spec/27 and HUMBOX guide.

- SAIPEN seam S2 (`spec/04-SAIPEN-SEAM.md`): `saimail.saipen_bridge` and
  `saimail-local saipen status|init|cite|verify`. Binds a caller-supplied
  workspace to the acting seat (`--seat`, else `SAIPEN_AGENT`, else
  `STATE.agent`), cites one LOG event as a `KIND:O` record whose `EV` is the
  sha256 of the exact LOG line, and re-checks a citation by re-deriving the
  whole record from the reader's own LOG bytes. The library reads only
  caller-named files and writes none of them; the SAIPEN layout lives in the
  entrypoint. No new wire field. Not part of the frozen `0.0.2a3` wheel. See
  `spec/DECISIONS-D057.md` and `humbox/FUTURE-GATES-V6.md` §11.
- SAITELEMES v0 (`spec/26-SAITELEMES-v0.md`, D-058): `saimail-local saipen
  telegram` sends one telegram to a registered running agent in one call. Only
  the acting seat may send (`SAIPEN_SEAT_MISMATCH`), the TOPIC is the SAIPEN Work
  id, the kind comes from the closed SENV2 set, and the body is a claim or an S2
  citation. `saimail-local saipen telegrams` is the bounded header-only turn-entry
  read. No new wire kind, no importance field. Checkout-only.

## 0.0.2a3

- Post-GUI local alpha candidate (D3): the accepted post-`0.0.2a2` product delta
  ships in the artifact — `P1` bounded metadata-only inbox query/triage,
  `V4-01` explicit one-hop local correspondence continuation, and `V5-01` the
  optional desktop local messenger GUI (`saimail-gui`, PySide6 behind the `gui`
  extra; Qt is never a base dependency and `saimail-local` stays Qt-free).
- `raw` custody remains the default; `os-store` remains the explicit opt-in
  requiring the `credentials` extra and a checked backend. The first-run
  `SAIMAIL_CUSTODY_NOTICE_1` notice is unchanged.
- Current candidate only: the frozen `0.0.2a2` candidate (externally proven) and
  the frozen `0.0.2a1` candidate stay byte-identical and `NOT_PUBLISHED`; no a2
  or a1 proof is inherited. The exact `0.0.2a3` wheel is locally frozen and
  proven; genuine external proof of that exact wheel is not yet admitted
  (`READY_FOR_EXTERNAL_INSTALL_PROOF`).
- Release tooling gains an additive `--require-product-delta` wheel content
  proof that mechanically proves the P1/V4-01/V5-01 surface inside the built
  wheel, without changing the frozen a2 custody proof.
- Not published. See `spec/18-LOCAL-ALPHA-v0.md`,
  `spec/20-LOCAL-KEY-CUSTODY-v0.md`, `spec/DECISIONS-D055.md` and
  `spec/DECISIONS-D056.md`.

## 0.0.2a2

- Post-V3-01 local alpha candidate (D2): the V3-01 identity custody modes ship
  in the artifact. `raw` stays the default; `os-store` is an explicit opt-in
  that requires the `credentials` extra and an OS credential backend.
- First-run custody notice: creating a new workspace returns one bounded,
  machine-readable notice (`SAIMAIL_CUSTODY_NOTICE_1`) for the custody mode
  actually created, with the honest raw-default and os-store claim boundaries.
  It is not repeated on later commands, and `ALREADY_EXISTS` is not a first run.
- Release tooling truth for post-V3-01 source: the candidate manifest separates
  the raw default from the optional protected mode, mechanically proves the
  custody surface inside the built wheel, and the build refuses to touch the
  historical `0.0.2a1` bundle or to overwrite any frozen candidate.
- The historical `0.0.2a1` candidate remains immutable and NOT published; its
  external proof is never inherited. The exact `0.0.2a2` wheel carries its own
  local, custody, reproducibility, privacy and integrity evidence.
- Not published. See `spec/18-LOCAL-ALPHA-v0.md`,
  `spec/20-LOCAL-KEY-CUSTODY-v0.md` and `spec/DECISIONS-D055.md`.

## 0.0.2a1

- Scoped local alpha release candidate (V2-04): PEP 440 prerelease identity for
  the local filesystem messaging workflow added after 0.0.1 (persistent
  workspace, identity cards, explicit recipient registration, local
  send/deliver/list/open, duplicate suppression and restart persistence).
- Not published. See `spec/18-LOCAL-ALPHA-v0.md` and the candidate
  `README-LOCAL-ALPHA.md` in the release bundle for scope and limitations.

## 0.0.1

- Initial public snapshot of SAIMAIL, including SAILANG, SENV2 delivery,
  immutable Post Office lifecycle handling, and evidence-bound LEGACY transfer.
