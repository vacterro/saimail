# Changelog

## Unreleased

- A workspace now knows *which identity* it is talking to, and *what actually
  happened* to every letter, in two layers that answer the two questions an
  operator really has after an incident (`future_gate/` Wave 1 and Wave 2).

  Wave 1, `saimail/trust.py`, removes trust-by-name. `peers.json` binds an alias
  to a fingerprint but never says why a peer is trusted or refused *right now*,
  so a peer that rebuilt itself was silently substituted and a matching display
  name was the only continuity evidence left. Every pin now names a canonical key
  fingerprint — never a path, never a seat — and resolves to exactly one of
  `UNKNOWN`, `OBSERVED`, `TRUSTED`, `ROTATION_PENDING`, `REVOKED`, `BLOCKED`,
  with `IDENTITY_CHANGED` *derived* rather than stored so a changed key can never
  be silently promoted. Rotation needs two signatures and states its reason;
  `BLOCKED` survives a rotate-back attempt where `REVOKED` would not; enforcement
  is advisory by default and refusals persist across restart.

  Wave 2, `saimail/ledger.py`, removes the invisible crash window. The durable
  outbox is idempotency-keyed and the Post Office indexes on delivery, so a
  crash between the two left a mail neither side could account for. A hash-chained
  append-only JSONL record now writes CREATED, SEALED, OUTBOX_COMMITTED,
  DELIVERY_ATTEMPTED, DELIVERED, RECEIPT_OBSERVED, OPENED, REPLIED, FAILED,
  QUARANTINED and SUPERSEDED through a closed vocabulary, with the RECEIPT
  landing *before* the index row on purpose — a crash in that window then leaves
  a visible receipt and a hole in the projection, which `ledger reconcile` repairs
  from the authenticated bundle instead of hiding. State is a pure `fold()` over
  the chain; appends are best-effort so the ledger can never break a send;
  `ABSENT` is not `UNREADABLE`, so an unreadable record reports
  `operator_action_required` rather than rendering zero pending mail; and nothing
  is ever invented — a repair reads the bundle or the sealed container bytes or
  the message does not come back. `saimail-local ledger health|feed|reconstruct|
  reconcile` reads the whole thing.

  Wave 3, `saimail/cold_archive.py`, removes delete-before-verify. Bounding a
  mailbox means deleting old bundles, and that is data loss the moment the copy
  being deleted from is the only copy, which is exactly when a cold write is
  most likely to have failed and an operator most likely to be reaching for a
  delete. So the order is the module: write the cold archive, read it back off
  disk, hash-check it, reopen it where a key is held, write the archive receipt,
  and only then prune. Any failure before the receipt leaves the hot copy exactly
  as it was, and `prune` re-verifies independently, so a record whose cold copy
  was corrupted keeps its hot body. The cold format is versioned
  (`SAIMAIL_COLD_1`) and stores the canonical encrypted bytes, the receipt, the
  index-row provenance and the ledger link: no re-encoding, no lossy summary
  standing in as the only copy, and no plaintext derivative anywhere, which is
  why `search` is metadata-only, refuses a semantic query by name, and points
  every hit back at its canonical source. Pruning removes the body and never the
  index row, so a pruned message stays findable and restores by id, idempotently.
  Retention by age, count, size and kind spends every budget on the newest
  records; Future Letters are pinned by class; the default policy prunes nothing.
  `saimail-local cold health|verify|archive|prune|restore|search`.

  Wave 4, `saimail/catchup.py`, removes the silent gap between two ticks. A
  mailbox that was closed -- machine asleep, agent offline, Post Office down --
  loses every opportunity in the interval, and on restart nothing records that
  they were owed: the system either does nothing or replays blind. So downtime
  becomes an explicit, bounded queue under three rules. Nothing is dropped: a
  send whose recipient vanished parks under `PEER_UNREACHABLE`, deliberately not
  `DELIVERY_FAILED`, because the whole transient family (offline target, busy
  lock, IO error) says the far side is the problem and sends an operator
  somewhere else entirely. Nothing is invented: the cause of an outage stays
  `UNKNOWN` when no record says otherwise. And the system informs while the
  agent reasons -- `run` executes only the mechanical DELIVERY and RECONCILE
  entries, while anything needing judgement (a trust decision, a residue to
  read) parks with its evidence attached. Work coalesces on `kind:logical_id`,
  so a month-long downtime is one debt per real obligation rather than one per
  tick, and re-observation never refreshes `attempts` or `next_attempt_at`, or
  the queue would spend a bounded backlog on an unbounded retry loop. Owed work
  and observed fact deliberately keep different shapes: a free stale lock is a
  fact reported with `remedy: NONE`, never a debt, while an abandoned
  `.staging` directory is a job. The queue stamps its own schema and version on
  every write, because the empty default handed back on a first run carries
  neither -- writing that payload back verbatim produces a file the module then
  refuses to read. `saimail-local catchup tick|detect|notice|queue|plan|claim|
  complete|park|run`.

  Wave 5, `saimail/canary.py`, gives the destructive suite somewhere safe to aim.
  A crash-window proof run against whatever mailbox was closest is not a
  hypothetical failure mode: the moment a corrupt-container probe lands on
  somebody's mail, a green suite has demonstrated that it can delete real mail.
  So test data is a declared identity rather than a fixture -- a reserved seat
  prefix plus a sidecar `canary.json` stamp naming the seat and both key
  fingerprints it claims. The two checks fail in *opposite* directions on
  purpose, because they answer different questions: the seat prefix decides
  what a production view may see and never grants permission, while a verified
  stamp is the only thing that may authorise a destroy. A directory named
  `canary-decoy` carrying a forged, stale or unparseable stamp still reads as
  canary in a listing and is still refused by `reset`, byte for byte.
  Classification travels *inside* the sealed container rather than beside it, so
  an exported bundle arrives labelled somewhere it has never been. Production
  views exclude test data by default and report the count they hid -- an operator
  told "0 messages" while looking at a filtered inbox has been told something
  false -- while a canary's own mailbox always sees its own traffic, because the
  test lane's whole output is its inbox and hiding it there would blind the very
  thing the lane exists to exercise. Reset is deterministic, rotates the identity
  so the next test cannot inherit the keys, and moves failure reports to a
  sibling `*.chaos-history/` *before* the wipe, because a report living inside
  the target is deleted by the reset that documents it. The scenarios are real
  rather than mocked: bytes are overwritten on disk, and the crash proof spawns
  an actual child killed with `os._exit` after `SEALED`, so nothing unwinds,
  flushes or shuts down on the way out.
  `saimail-local canary seed|reset|status|record|reports`.

  Wave 6, `saimail/future_letter.py`, makes a letter able to refuse. The wave
  started from the obvious gap: a Future Letter can be written for a date, but
  nothing can wait, and nothing refuses, so the date was a comment in a title
  field. A capsule now carries `not_before` and `expires_after` *inside* the
  sealed container, and the lock is decided from those bytes after
  authentication and before the body is returned -- the only ordering that means
  anything, since a lock checked against a registry row could be defeated by
  editing a plain file and one checked after the body is in hand is a comment.
  Refusals are deterministic: the new `PostOfficeSession.peek_message`
  authenticates and decrypts without consuming the single unread transition,
  without spending the open budget and without writing a ledger note, so the
  first early attempt and the thousandth give the same answer instead of the
  first burning the transition and the second reporting `ALREADY_READ`. Nothing
  is armed when a letter becomes eligible -- no queue, no timer, no prompt --
  because a capsule that fired by itself would be a message nobody could audit,
  and the reader still has to ask. Three unauthorable capsules are refused by
  their author: a lock dated before the letter existed, a window that closes
  before it opens, and a window so long the lock is decoration. Expiry refuses
  rather than reopening, because a lock that quietly kept giving up its contents
  forever would not be a lock.

  Co-signing signs a *statement* naming the `letter_id` -- the hash of the
  canonical container, fixed before anybody signed -- so a body edited afterwards
  names a different object and the roster no longer matches it. The signature
  lives in a detached registry rather than inside the container it covers, which
  would be circular, and never beside a mutable body, which would prove nothing.
  `PARTIALLY_SIGNED` is reported as itself and never rounded up; zero verifiable
  signatures is `UNSIGNED` whatever the roster asks for, because "partially
  signed" over an empty set is a rounding-up of nothing and it is the exact
  phrase a reader skims past. One damaged signature is reported
  `verified: false` instead of making the whole roster unreadable, and a second
  signature from the same identity is refused rather than appended, so a roster
  cannot be padded into looking busier than it is. Because an import re-seals
  honestly as `source: IMPORTED` and so gets its own `letter_id`, a signature is
  matched through the `source_ref` it records -- the one journey a signature is
  meant to survive is the one an honest import would otherwise break. An import
  also carries the lock and the roster across, because rewriting provenance is
  honest while dropping a time lock to make the re-seal simpler would hand the
  next mailbox an unlocked, unrostered letter claiming to be the locked one.

  An audience (`SEAT`, `SUCCESSOR_OF`, `MAINTAINERS`, `OPERATOR`) records who a
  letter was *written for*, and every row publishes `audience_enforced: false`,
  because nothing in this module turns that into a gate and publishing the flag
  is what stops a successor address from being read as access control. The
  container schema is versioned, and the version is a `build_container`
  parameter rather than a constant: a v1 letter is rebuilt under v1 so its hash
  -- its identity -- does not move, and passing v2 fields to a v1 schema is
  refused rather than quietly dropped, because a silently dropped time lock opens
  early and never says why. `saimail-local future-letter cosign|signatures|
  export-signatures|import-signatures`, plus `--not-before`, `--expires-after`,
  `--required-signer` and `--audience-scope` on `create`.

  Wave 7, `saimail/surface.py`, makes the mailbox describe itself instead of being
  described. Waves 1 through 6 added nine verbs to `saimail-local`, and any
  reader consulting a static list was reading a surface that had not existed for
  five waves. `saimail-local surface map` now walks the registered argparse tree,
  so the inventory is wrong the instant a verb is added or removed -- which is
  the only way it stays right, and which is why the map lists the verb that
  prints it. The frozen `host_contract` intent map is left frozen: `health` there
  names an *intent*, not a verb, so cross-comparing it against the parser would
  report an all-zero advertisement on a build that has everything. It gains a
  `live_surface` pointer instead, additively, so a host written against v1 still
  resolves every key it knew. `surface schema` is the versioned capability
  advertisement, carrying the envelope schemas, the custody modes and one flag
  per capability family derived from the command that evidences it -- remove the
  verb and the claim goes with it, because a capability left advertised after its
  command is gone is how a host learns to send a request nothing can answer.

  Health is three-valued: `HEALTHY`, `UNHEALTHY`, `UNKNOWN`. There is no fourth,
  because the fourth is the failure this wave exists to remove -- a dashboard
  that renders unreadable state as `0 unread` has told an operator a mailbox is
  empty when in fact it could not be read, and has told them in the exact shape
  that looks like good news. Each section is produced by CALLING its owning
  subsystem's own function, never by re-deriving it, because a second
  implementation of somebody else's invariant is a second thing to be wrong; a
  section is exactly as good as the function that answered it, and every section
  names that function in `source`. A subsystem that raises or refuses becomes
  `UNKNOWN` with no numbers published -- an exception inside `trust.list_pins`
  must not become an empty pin list a reader would act on -- and `UNKNOWN` rolls
  up to `UNKNOWN`, never to `HEALTHY`, because a mailbox that cannot describe
  part of itself has not been shown to be fine. Every other section still answers
  when one breaks: a dashboard that stops at the first failure is the same
  all-clear with fewer numbers. `ABSENT` is deliberately *not* an UNKNOWN, so a
  brand new mailbox with no ledger and no archive reads `HEALTHY` rather than
  training its operator to ignore the word. Quarantined mail and a trust rotation
  awaiting a human are `UNHEALTHY`, because both are decisions waiting rather
  than footnotes.

  `surface feed` carries the ledger's continuity verdict upward instead of
  smoothing it away. A caller following a cursor through trimmed history sees a
  well-formed page and has no way to know records between its position and the
  oldest retained event are simply gone, so the page reports `GAP` and says the
  missing events were not summarised and are not recoverable from this feed; an
  unreadable ledger is `UNKNOWN` and returns no events at all, because a
  plausible-looking empty feed from a broken ledger is the false zero one more
  time. The gap is decided by sequence number, which retention preserves -- a
  trim that renumbered from 1 would erase the evidence of its own cut. The
  dashboard is derived on every call and cached nowhere, so a verdict survives a
  restart because it was about the workspace rather than about a live object.
  `saimail-local surface map|schema|health|feed`; `map` and `schema` need no
  mailbox, and a dashboard reporting `UNKNOWN` still exits 0, because failing
  would train every caller to retry an unfixable read and then ignore the word.

- An agent can now leave a durable note for whoever holds its workspace next
  (T-161, SRC-120). `saimail-local future-letter create|list|show|open|reopen|
  export|import` stores the body as a canonical `SAIMAIL_FUTURE_LETTER_1`
  container sealed by an ordinary SENV2 envelope of kind `FUTURE_LETTER`, so a
  letter inherits the existing transport unchanged: sender signing, recipient
  binding, durable outbox, Post Office UNREAD/READ state, receipts and
  deduplication. It needed no parallel mailbox — the only extension to the
  existing contracts is a `deliver_payload` route that seals payload bytes
  instead of a one-line SAILANG record, plus a Post Office built over peers and
  the workspace's own public key so an agent can address its own successor
  without registering a peer.

  The hard part of the ticket was not storage, it was authority. A future
  letter is provenance, never permission: it is not memory, system policy, a
  developer instruction, a trusted command, hidden prompt content, authority,
  automatic context or task creation, and its claims are not evidence that they
  are true. So `list` and `show` read a metadata registry and never decrypt;
  reading stays an explicit `open`/`reopen` through the same gate as ordinary
  mail; opening is non-destructive and read state survives restart; and nothing
  in the module appends a body to a model prompt, a system prompt, an agent
  startup context or a SAIPEN recovery prompt. Nine hostile-looking bodies —
  shell commands, fake system prompts, "ignore previous instructions",
  protocol-shaped JSON, SAIPEN command lines, chat-template markers, credential
  paths, bidi-overridden text and 40 KB of filler — are stored, returned
  byte-for-byte and executed by nothing.

  Custody is named rather than implied. A `PRIVATE` export bundles no key beside
  the ciphertext. `--recovery` produces a `NOT_PRIVATE_RECOVERY_ENABLED` time
  capsule carrying its own AES-256-GCM key: it survives loss of the workspace
  identity, and a key shipped with its ciphertext is packaging and recovery,
  not secrecy. There is no way to relabel a custody on the way in: a stored
  letter is sealed to the importing workspace identity and is therefore always
  `PRIVATE`, and the archive it came from keeps its own non-private label in the
  import result. Containers, the registry and
  bundles are versioned, and corruption — damaged ciphertext, a hash that
  disagrees, an unknown schema, ambiguous decryption — fails closed by name
  instead of decoding into plausible text.

- Five verified defects in future letters are repaired (T-162, SRC-121), all of
  them cases where the code promised more than it could keep.

  **A private export is now genuinely private, and genuinely recoverable.** It
  used to mint a fresh random AES-256-GCM key, wrap it to nothing, and ship it
  nowhere, so the archive implied a workspace-identity recovery that did not
  exist and importing it back failed `RECOVERY_KEY_REQUIRED` in the very
  workspace that produced it. A private export is now a
  `SAIMAIL_FUTURE_LETTER_BUNDLE_3` bundle carrying the canonical sealed SENV2
  container verbatim, with no key member at all: holding the ZIP reveals
  nothing, the owning workspace identity reopens it through the unchanged
  SENV2 path, and any other workspace is refused `BUNDLE_IDENTITY_REQUIRED`.
  No bespoke crypto, and no key stored beside the ciphertext.

  **Recovery is an export property, not a creation one.** `create` no longer
  accepts `--custody`: sealing to the workspace identity is the only custody
  that exists at rest, so a `RECOVERY_ENABLED` label there would have promised
  survival of that identity's loss while creating no recovery material. A
  stored letter is always `PRIVATE`; `export --recovery` remains the explicit,
  deliberately non-private time capsule. `import` loses its `--custody` knob for
  the same reason: whatever a source archive advertised, the letter it produces
  here is sealed to this workspace identity, so relabelling it would re-advertise
  a custody import cannot keep. The archive's own custody and
  `NOT_PRIVATE_RECOVERY_ENABLED` classification now travel in the import result,
  so the honest label is preserved instead of being discarded or forged.

  **The tamper test now tampers.** It replaced `CIPHER:`, which does not exist
  in SENV2, and passed only because text-mode rewriting turned the refusal into
  a line-ending complaint. It now flips one base64 character of the real
  `CIPHERTEXT` line, writes bytes rather than text, and asserts
  `CIPHER_HASH_MISMATCH`.

  **A crash between delivery and the registry row no longer loses a letter.**
  The canonical mailbox is the source of truth and `future-letters/index.jsonl`
  is a reconstructable projection: `list` and the new `future-letter
  reconcile` rebuild a row the crash lost, idempotently, sealing and
  delivering nothing, so recovery cannot manufacture a duplicate.

  **Forged registry provenance is detected rather than displayed.** Rows are
  now built from authenticated content in one place, a metadata-only listing
  labels itself `UNVERIFIED_PROJECTION`, and `open`/`reopen` compare the row
  against the authenticated container field by field — correcting and reporting
  the drift rather than presenting an edit as canonical truth. No listing
  decrypts a body.

  The GPT-5.6 Sol seed letter arrived as a v1 bootstrap archive that encrypted
  raw prose rather than a container, so it imports through the legacy path
  only; a damaged current bundle still refuses. It was recovered, hashed and
  imported through the canonical send/seal route with its body preserved
  byte-for-byte (`f5f2597a…`), its creation stamp normalized to UTC and nothing
  else touched. The original archive in `operator_import/future_letters/` is
  untouched and remains recovery evidence. Cold-start proof: a fresh workspace
  and a separate process discover the letter by metadata, listing decrypts
  nothing, an explicit open returns the exact expected plaintext, and a reopen
  after restart returns the same hash.

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
- Two performance gates that were measuring the machine now measure the product
  (T-164). `test_a_dense_body_scans_in_linear_time` and
  `test_receiver_alias_decode_scales_linearly_not_quadratically` both timed
  themselves with `perf_counter` and compared ratios with an additive floor;
  whenever the small case landed in low milliseconds the floor stopped the ratio
  binding and the gate became a fixed absolute deadline, and under suite-wide
  allocator pressure the same code measured 53x-75x growth for 4x the work. Both
  were red on roughly every other full-suite run and green in every isolated
  run, which is the signature of a bad instrument rather than a regression.

  They are replaced by counted work. The quarantine scan is fed a `bytes`
  subclass that tallies every character it decodes — `__getitem__` overridden so
  slices stay in the subclass, because slicing a `bytes` subclass yields plain
  `bytes` and would otherwise let the very re-encode under test escape the
  counter. Measured: linear scanner 80,890 → 162,890 characters for a 2x body
  (x2.01); deliberately quadratic control 80,362,385 → 324,221,385 (x4.03). The
  frame gate keeps two halves because no single instrument covers the class:
  `sys.settrace` line events scoped to `sailang/` catch super-linearity in the
  receiver's own control flow, and the existing `_ALIAS_MAP_BUILDS` counter
  catches the per-frame alias rebuild, which is one C-level `dict()` copy per
  frame and is therefore invisible to a line counter.

  Each gate was proved red against the reintroduced defect and green against the
  restore, byte-for-byte. `python -m pytest -q`: 3263 tests, 0 failed, twice
  consecutively, where the same command was red on three consecutive runs
  before. No tolerance was widened; both `time` imports are gone from those two
  tests. Test-only: no product behaviour changed.

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
