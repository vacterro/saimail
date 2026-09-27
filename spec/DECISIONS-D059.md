# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-059 — header-only reads load a secret-free view; the SAIPEN turn-entry read never touches custody (T-117)

The defect class is a metadata read that holds secrets. SAIPEN T-1497 made the
SAITELEMES turn-entry read automatic: every SAIPEN `continue` and `status` runs
`saimail-local --json saipen telegrams` against the seat's mailbox. That command,
like `inbox`, `saipen enter` and `saipen brief`, performed the full workspace
load. In os-store custody the full load retrieves both private keys from the OS
credential store, so each unattended turn entry pulled the signing and decryption
keys into a process that only counts headers. A locked or prompting store turned
the count into `CUSTODY_ACCESS_FAILED`. T-117 measured it: two secret reads per
call, and a refused count with the store locked.

**Decision.** Header-only reads load `saimail.workspace.load_workspace_headers`,
which returns `WorkspaceHeaders`: root, seat, created, the recipient public key,
the two fingerprints and the custody mode. Nothing else.

- **Same public checks.** The full load and the header load share one validator
  (`_read_durable_identity`): the marker and its self-derived fingerprints, the
  identity file's field set and its agreement with the marker, the os-store public
  projection and handles, and the peers file. Every public refusal is identical.
- **No secret.** The header load builds no private-key object and never reads the
  credential store. Its Post Office is built from public keys, as the full load's
  already was.
- **No key operation.** The view has no private key, so it cannot open, reopen,
  send, reply or sign. Those operations, and `saipen telegram` and `saipen init`,
  keep the full fail-closed load. spec/20's rule that stored public keys never
  substitute for retrieved-private-key-derived identity is unchanged, because the
  view is not an identity load.
- **Stated boundary.** The view proves the public identity, not possession of the
  private one. A raw identity whose private key no longer matches the marker still
  lists headers; every key-using load refuses it.
- **Consumer contract.** The fields SAIPEN parses are pinned by test: exit code,
  `ok`, `match_count`, `exhausted`, `items[].topic`, and a refusal code carried in
  `status`.

**Boundary.** No wire, index, custody, Post Office, GUI or SAIPEN change. Three
SAIPEN-side findings are filed for the protocolist, not changed here: SAIPEN
reads a refusal from `code` while `LOCAL_WORKSPACE_COMMAND_1` carries it in
`status`; its `read_command` hint interpolates paths unquoted; and it counts a
mailbox without comparing the answer's `workspace.seat` with the acting seat
(the field is pinned by test). Checkout-only; the frozen `0.0.2a3` wheel does not
contain this change.

**Evidence.** `tests/test_turn_entry_headers.py`: zero store reads for `inbox`
(listing and query), `saipen telegrams`, `enter` and `brief` with the store
functions guarded; a locked store still yields counts while `open` refuses with
`CUSTODY_ACCESS_FAILED`; header and full loads give identical listings, queries,
telegram pages and a shared brief context; identical public refusals in both
custody modes; the private-identity boundary; the pinned SAIPEN-consumed fields.
Red controls: 7 of the 8 controls fail on the exact pre-T-117 bytes, and a
marker-only header loader fails both parity controls
(`.saipen/evidence/T-117-turn-entry/red-controls.txt`).
