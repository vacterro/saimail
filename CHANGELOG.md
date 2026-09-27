# Changelog

## Unreleased

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
