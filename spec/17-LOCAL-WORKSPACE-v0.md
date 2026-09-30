# V2-01 — PERSISTENT LOCAL WORKSPACE AND REAL SEND/RECEIVE v0

Status: working. Contract for `saimail/workspace.py`, the workspace subcommands of
`saimail_local.py` and `tests/test_local_workspace.py` /
`tests/test_local_workspace_acceptance.py`.

## 1. Why this document exists

FG-05 proved that the local protocol components compose inside one process on
throwaway roots, and FG-06 shipped an installable entrypoint whose only durable
behaviour was still a temporary demo. A real operator therefore had no
persistent place for an identity, no way to address a known local recipient and
no `send → deliver → list → open` path that survived the process that ran it.
V2-01 is the smallest user-facing step that turns the already-proven semantics
into one practical local workflow. It is a thin durable shell: it adds no
protocol rule, no second dedup layer, no new cryptography and no network path.

## 2. Workspace contract

A workspace is one caller-supplied root directory plus a public marker file.
It must carry, deterministically discoverable from its own files:

* a stable root directory;
* `saimail-workspace.json` — schema `SAIMAIL_LOCAL_WORKSPACE_1` v1, the seat,
  the creation instant and the PUBLIC keys/fingerprints only;
* `identity/identity.json` — schema `SAIMAIL_LOCAL_IDENTITY_1` v1, the software
  Ed25519 (sender) and X25519 (recipient) private keys, hex-encoded raw bytes;
* `peers.json` — schema `SAIMAIL_WORKSPACE_PEERS_1` v1, the explicit
  operator-owned alias → public identity + recipient workspace mapping;
* `outbox/<envelope_id>.senv` — sealed container copies kept so an exact replay
  is the same transport object;
* `mail/…` — the Post Office's own durable state, created by `PostOffice`.

The marker is the commit point. A missing marker with identity material
present, or a non-empty directory without a marker, is `WORKSPACE_CONFLICT`;
a marker that is unreadable, foreign or inconsistent with the durable private
identity is `INVALID_WORKSPACE`. Identity is generated exactly once: rerunning
`init` over a valid workspace returns `ALREADY_EXISTS` and never regenerates or
substitutes keys. Nothing relies on the current working directory, the
repository checkout, process-global state, temporary directories or implicit
machine-specific paths; only the explicitly supplied workspace roots and the
registered recipient workspace path are used.

## 3. Commands

```
saimail-local init --workspace DIR --seat SEAT
saimail-local identity --workspace DIR [--export-card CARD.json]
saimail-local recipient add --workspace DIR --alias NAME --card CARD.json \
    --peer-workspace PEER_DIR
saimail-local recipient list --workspace DIR
saimail-local send --workspace DIR --to NAME --claim "one line"
saimail-local send --workspace DIR --to NAME --record RECORD.sailang
saimail-local send --workspace DIR --redeliver ENVELOPE_ID
saimail-local inbox --workspace DIR
saimail-local open --workspace DIR --envelope ENVELOPE_ID
saimail-local acceptance [--root DIR] [--out DIR] [--keep]
```

Every workspace command accepts `--json` and prints one bounded
`LOCAL_WORKSPACE_COMMAND_1` result: schema, version, command, status code, the
public workspace identity, the relevant message identity/state and an
`operator_action_required` flag. No result ever carries private key material or
a plaintext payload; `open` returns the exact record it explicitly opened.

D2 addendum: the result that **created** a new workspace additionally carries a
bounded `notices` list — one `SAIMAIL_CUSTODY_NOTICE_1` entry for the custody
mode actually created (`RAW_CUSTODY_DEFAULT` or `OS_STORE_CUSTODY`: id, mode,
one fixed message string). The list is absent from every other result,
`ALREADY_EXISTS` is not a first run and carries no notice, and the human
rendering prints a `NOTICE:` line. This is additive to v1; no existing field
changed.

## 4. Identity exchange and recipient addressing

`identity --export-card` writes the public card
(`SAIMAIL_IDENTITY_CARD_1` v1): seat, creation instant, raw public keys and
fingerprints. `recipient add` validates that card byte-for-byte (closed field
set, key lengths, fingerprints recomputed) and validates that the supplied
`--peer-workspace` really carries a marker for that same seat, sender key and
recipient key. The mapping is deterministic, persistent and inspectable, with
no fuzzy matching, no network lookup, no automatic key discovery and no silent
substitution: an identical re-add is `RECIPIENT_ALREADY_REGISTERED`, a
different identity under the same alias or workspace is refused as
`RECIPIENT_CONFLICT`, malformed cards/aliases are `RECIPIENT_MALFORMED` and a
card/workspace mismatch is `RECIPIENT_IDENTITY_MISMATCH`. Both workspaces must
register each other: the receiver needs the sender's accepted public key to
verify delivery, and the sender needs the receiver's public key and root to
address and deliver.

`recipient list` and explicit `recipient add` use the public workspace view.
They do not retrieve private keys from credential custody and remain usable
while that store is locked, including an empty recipient list. All public
workspace/card/peer identity checks and alias conflict refusals still apply.
Missing, unreadable, non-UTF-8 or malformed JSON card files return the structured
`RECIPIENT_MALFORMED` command result without modifying the mapping. Registration
does not send, admit a study participant or unlock custody; message operations
retain their existing private-key requirements.

Concurrent `recipient add` commands serialize conflict admission and atomic
replacement under the existing OS file-lock mechanism. Each writer reads the
current registry after acquiring the lock: distinct aliases survive, competing
identities for one alias produce one successful registration and a conflict,
and identical additions remain idempotent. The local `.peers.lock` file carries
no identity or ownership authority; process exit releases the OS lock.
`recipient list` remains read-only and does not create this lock file.
`RECIPIENT_LOCK_TIMEOUT` asks the caller to retry after contention;
`RECIPIENT_REGISTRY_UNAVAILABLE` reports lock or persistence I/O refusal.
Neither outcome permits replacing a conflicting alias.

## 5. Message content

The existing stable typed representation is the message. `--record FILE` sends
an existing canonical SAILANG record exactly as its canonical bytes. The
`--claim` convenience wrapper is deterministic and documented: it creates

```
KIND:F  SRC:HUMAN:<sender seat>  SUBJ:<--subject, default local-message>
CLAIM:<the single operator line>  TYPE:OBS  EV:0  STATUS:U1  CREATED:<now>
```

`EV:0` is evidence EXPLICITLY absent and the uncertainty rung is capped at U1 —
free text is never dressed up as evidence. Multi-line content belongs in a
canonical record file, not in a silently transformed claim.

## 6. Local delivery boundary

Delivery is explicit and local: `send` opens the recipient workspace root
registered at `recipient add` time and calls that workspace's own
`PostOffice.deliver` through the standard `saimail.envelope` seal/verify path.
The sender therefore needs write access to the recipient workspace directory.
This is a shared local filesystem boundary — not a network service, not remote
delivery and not a hosted mailbox. All verification, quarantine, addressing and
dedup semantics remain the Post Office's: the CLI writes no recipient store
file directly, bypasses no gate and adds no dedup layer of its own. An exact
replay through `--redeliver ENVELOPE_ID` re-delivers the identical outbox
container and returns the canonical `DUPLICATE` with the original
`RECEIVED_AT`; an unknown sender key is quarantined by the receiver exactly as
in FG-05.

## 7. Listing and explicit open

`inbox` reads canonical index rows plus durable bundle state and reports
bounded metadata only: envelope id, sender/recipient seats, kind, topic,
created/`RECEIVED_AT`, `UNREAD`/`READ`/`EXPIRED` and the optional `ref`. It
never parses or decrypts a payload. `open --envelope ENVELOPE_ID` is the one
explicit transition: it requires the exact local message identity, passes
through `PostOfficeSession.open_message`, moves `inbox/` to `read/` under the
existing semantics and returns the parsed record (claim, kind, uncertainty
rung, evidence state). It does not promote, acknowledge attention, delete or
bulk-open anything; promotion stays a separate action over the opened payload.

## 8. Machine-readable contracts

* `LOCAL_WORKSPACE_COMMAND_1` v1 — one result per workspace command.
* `LOCAL_WORKSPACE_RESULT_1` v1 — the acceptance harness result: schema,
  version, PASS/FAIL, both workspaces' public identities, every isolated
  invocation, checks, send/duplicate/restart/privacy blocks and the
  zero-network/model counters.
* `LOCAL_SCENARIO_RESULT_1` (FG-05) and `FG06_UTILITY_RESULT_1` (FG-06) are
  untouched; V2-01 adds a third contract rather than mutating history.

## 9. One-command acceptance harness

`saimail-local acceptance --root DIR` creates two workspaces under an isolated
fresh root and runs the whole workflow through separate invocations of the
installed CLI itself (each documented command is its own process): init A,
init B, export both cards, register both recipients, send A→B, list B, open B,
list B again, re-export A's identity, redeliver the exact envelope, list B
again and scan the root. It prints a bounded PASS/FAIL result; a non-empty root
is refused. The harness is verification, not a replacement for the individual
operator commands.

## 10. Privacy, atomicity, and what this does NOT claim

* Private key material never appears in CLI stdout, machine results, README
  examples, evidence files or test snapshots; tests assert its absence.
* Every metadata file is written with a same-directory temp file, fsync and an
  atomic replace; an interrupted write leaves the previous complete file. The
  workspace marker is written last, so a partial init is always detectable —
  never adopted and never silently regenerated.
* Plaintext is not persisted anywhere new: only the sealed container exists in
  the outbox and in the recipient's Post Office; opening does not write it out.
* Known limitation, stated honestly: identity private keys are stored as raw
  software key files protected only by their file location (owner-only mode is
  requested where the OS honours it). There is no encryption at rest, no
  hardware provisioning (no FIDO/YubiKey/TPM), no OS credential vault, no key
  rotation and no forward secrecy beyond what the existing SENV2 envelope
  already provides. This is a local alpha workflow, not hardened production
  key custody.
* Fully local: the base path makes zero network calls and zero model calls; no
  generative branch exists in it.
* V3-01 addendum: the raw limitation above describes the default `raw` custody
  and every pre-existing V2-01 workspace. An opt-in `os-store` custody mode
  moves the private keys into the checked OS credential store and keeps only
  handles plus public material in the workspace; the contract and its claim
  boundaries are in
  [spec/20-LOCAL-KEY-CUSTODY-v0.md](20-LOCAL-KEY-CUSTODY-v0.md). No V2-01
  command, wire format or Post Office semantic changes in either mode.

SAIMAIL V2-01 does not promise remote delivery, Gmail/Slack/Outlook or any
external adapter, a server/daemon/background sync, a GUI/TUI, group messaging,
attachments, search, inbox rules, automatic promotion, automatic
correspondence, hardware-key provisioning, or service readiness. It does not
promise encryption at rest, and it does not turn a shared filesystem path into
"network messaging".
