# V3-01 — LOCAL KEY-AT-REST CUSTODY v0

Status: working. Contract for `saimail/custody.py`, the custody mode of
`saimail/workspace.py`, the `init --custody` flag and the `custody status` /
`custody migrate` subcommands of `saimail_local.py`, and
`tests/test_workspace_custody.py`. Decision: [D-053](DECISIONS-D053.md).

## 1. Why this document exists

V2-01 gave the local workflow a persistent home, and the same place where a
copied workspace directory silently became a copied identity: the Ed25519 and
X25519 private keys sat as raw hex in `identity/identity.json`, protected only
by a requested owner-only file mode. A backup, an archive or a directory copy
carried the identity with it. V3-01 decides the smallest custody boundary that
materially improves that situation, and proves what the chosen boundary does
and does not achieve.

This is storage policy only. No wire format, SENV2 byte, Post Office semantic,
message identity, recipient addressing or dedup rule changes; no new
cryptography is invented. The existing, tested credential-store abstraction
(`saimail/credentials.py`, D-019) is reused under a separate namespace.

## 2. Threat model

The attacker/loss cases considered, and what the current raw layout does in
each:

| Case | Situation | Raw `identity.json` today | Protected (`os-store`) |
|------|-----------|---------------------------|------------------------|
| A | Offline workspace copy (archive, backup, synced folder) read without the authorized OS user context | Private keys exposed | Directory contains handles + public material only; keys need the store of that OS account |
| B | Local file read under another user / backup / accidental archive of workspace files | Exposed if file access permits | Exposed only through the OS credential store of the authorized account |
| C | Malware or a process running as the authorized user | Exposed | Also retrievable: an OS vault is not a boundary against the same user session. Explicitly not claimed |
| D | Full host admin / kernel compromise | Out of scope | Out of scope; no protection is claimed |
| E | Loss, reinstall, machine migration | Keys live in the workspace; a copy restores them | Keys are bound to the OS account and host store; a workspace copy alone is not a recovery. Availability and recovery are part of the decision |
| F | Backup / restore | Self-contained: the workspace carries everything | An ordinary workspace backup no longer carries usable keys by itself; the store entries must exist. Documented, not hidden |
| G | Silent custody substitution | A missing or unreadable identity file fails closed today | Equally fail-closed: an absent, unsuitable, failing or substituted store never regenerates, re-keys or falls back to raw bytes or environment variables |

Defect addressed by V3-01: A and B. Cases C, D and E are stated limitations of
any software key-at-rest mechanism here, not promises; F and G define the
recovery and fail-closed semantics.

### 2.1 Security objective

For the selected OS-store option the objective is exactly:

```
WORKSPACE_DIRECTORY_COPY_ALONE_DOES_NOT_REVEAL_PRIVATE_IDENTITY_KEYS
```

Not claimed, and never to be inferred from this document:

```
MALWARE_RUNNING_AS_AUTHORIZED_USER_CANNOT_ACCESS_KEYS
ADMIN_OR_KERNEL_COMPROMISE_PROTECTED
HUMAN_IDENTITY_PROVED
HARDWARE_ISOLATION
PHYSICAL_PRESENCE_ENFORCED
FORWARD_SECRECY
AUTOMATIC_RECOVERY
```

## 3. Options evaluated

**A — Keep raw file custody (current).** Simple, portable, self-contained
backups, no dependency. Keeps the primary remaining risk: a copied workspace is
a copied identity. Retained as the legacy mode for existing workspaces and as
an explicit opt-in for new ones (section 6).

**B — OS credential store (selected).** Reuses the tested store architecture
with a checked backend (WinVaultKeyring on Windows, `SAIROUTE_*`-style named
refusals elsewhere), removes private bytes from the workspace, is reversible
and adds no new cryptographic design. Residual risks: same-user malware,
account/machine migration, and backend availability as an operational
dependency. Selected.

**C — Passphrase-encrypted identity file (rejected).** Would protect an offline
copy without the OS store, but adds KDF/salt/nonce/AEAD parameters, a passphrase
UX, secret lifetime in process memory, an unattended-operation cost, a recovery
story and a new cryptographic implementation surface — for a threat model the
OS store already covers in the supported Windows alpha. "Encryption sounds
stronger" is not evidence; rejected unless a concrete advantage over B is
demonstrated.

**D — Hardware custody (not in scope).** Recorded as a separate future explicit
gate. D-043 hardware custody applies to the HUMAN_PRIVATE P-256 identity
family, not to this V2-01 workspace Ed25519/X25519 identity; the two are not
conflated. No provisioning happens in V3-01.

## 4. Custody contract

Two modes, read from durable files and never inferred from the platform:

* `raw` — schema `SAIMAIL_LOCAL_IDENTITY_1` v1, raw private hex in the
  workspace file. Legacy V2-01 layout; explicitly identified, never silently
  mutated.
* `os-store` — schema `SAIMAIL_LOCAL_IDENTITY_2` v2 in the same file:

```json
{
  "schema": "SAIMAIL_LOCAL_IDENTITY_2",
  "version": 2,
  "seat": "...",
  "created": "YYYY-MM-DDTHH:MM:SSZ",
  "custody": "os-store",
  "sender_handle": "credential://saimail-workspace/<seat>/sender/<fingerprint-digest>",
  "recipient_handle": "credential://saimail-workspace/<seat>/recipient/<fingerprint-digest>",
  "sender_public_key": "...", "recipient_public_key": "...",
  "sender_kid": "sha256:...", "recipient_kid": "sha256:..."
}
```

Private bytes must not exist in that file. The public workspace marker
(`saimail-workspace.json`) is unchanged and remains the public authority: the
identity file's public keys and fingerprints must equal the marker's, and the
handles must structurally name the identity's own fingerprints. After loading
private material from custody the public keys and fingerprints are re-derived
and compared with the durable public identity; any mismatch refuses the load
(`CUSTODY_KEY_MISMATCH`). Caller-supplied or stored public keys never substitute
for retrieved-private-key-derived identity. The header-only view
(`load_workspace_headers`, T-117, D-059) is not such a substitute: it lists and
queries index rows, holds no private key and grants no key operation, so it
never reads the store. Every key-using operation still performs the load above.

**Namespace.** Handles use the service `saimail-workspace`, never
`credential://9router/sairoute`. The SAIRoute transport credential and workspace
identity custody are separate authority domains and never share an entry.

## 5. Migration

A pre-existing raw workspace continues under `raw` mode until an explicit
operator command:

```
saimail-local custody migrate --workspace DIR
```

Required transactional order:

1. validate the workspace fully (`load_workspace`, raw);
2. retrieve and validate the current private keys;
3. store both private keys under the new handles;
4. read them back;
5. derive public identities and recompute fingerprints;
6. prove exact fingerprint equality with the durable marker;
7. atomically replace the durable identity file with the v2 payload;
8. the atomic replace removes the raw bytes; nothing else is deleted.

Any failure releases entries this run created and leaves the old raw workspace
intact and loadable; a failed final re-read restores the original identity file
byte-for-byte. No silent migration, no re-keying, no import without a command,
no half-migrated identity. Fingerprints are stable through migration by
construction (steps 5-6), and a repeated migration returns the named no-op
`CUSTODY_ALREADY_PROTECTED`.

## 6. Failure semantics

Named, distinct, and never collapsed into a generic invalid-workspace result:

| Code | Meaning |
|------|---------|
| `CUSTODY_BACKEND_UNAVAILABLE` | no OS credential store exists here (keyring not installed) |
| `CUSTODY_BACKEND_UNSUITABLE` | the selected backend is not a persistent local store (null/fail/plaintext; on Windows, not `WinVaultKeyring`) |
| `CUSTODY_KEY_MISSING` | the handle holds no key; absence is established through the store |
| `CUSTODY_KEY_MISMATCH` | retrieved material is malformed or does not derive the durable public identity |
| `CUSTODY_ACCESS_FAILED` | the store failed while reading, writing or deleting |
| `CUSTODY_MIGRATION_CONFLICT` | the handle already holds a different key; overwrite refused |

Backend failures are classified before any read or write, so an unsuitable
backend cannot answer a lookup that a policy would ignore. No error, result,
`repr` or log carries a private key value; a handle is a location label.

## 7. Dependency and default decision

* `keyring` stays an optional dependency (`credentials` extra). The core
  package keeps zero required runtime dependencies.
* Protected custody is an optional capability that requires that extra. When
  it is absent, an os-store workspace fails with `CUSTODY_BACKEND_UNAVAILABLE`
  and the exact install hint; it never degrades silently.
* The default for **new** workspaces is `raw`, preserving the V2-01 install
  contract and the zero-dependency core; `--custody os-store` and
  `custody migrate` are the explicit protected paths. The default is a
  documented contract constant, never a platform detection result.
* Distribution consequences of the default (for example making protected
  custody the default for a published package) belong to the release decision
  packet (candidate D1), not to this gate.
* **D2 / D-054 first-run notice.** Every successful creation of a new
  workspace carries exactly one bounded `SAIMAIL_CUSTODY_NOTICE_1` notice for
  the mode actually created: `RAW_CUSTODY_DEFAULT` for raw (the implicit
  default and an explicit `--custody raw` alike) and `OS_STORE_CUSTODY` for the
  protected mode. The raw notice states that raw is the default, that the
  private keys are workspace files, that a copied workspace copies the
  identity, that `--custody os-store` exists where a checked backend is
  available, and that os-store protects against workspace-directory-copy
  exposure only — not same-user malware or admin/kernel compromise. The
  protected notice never claims raw storage. The notice is returned once on
  the creating result, is absent from `ALREADY_EXISTS` and from every later
  command, and carries no key value and no secret path.

## 8. Commands and results

```
saimail-local init --workspace DIR --seat SEAT [--custody raw|os-store]
saimail-local custody status --workspace DIR
saimail-local custody migrate --workspace DIR
```

`custody status` is read-only and never mutates workspace or store. It reports
the mode, the classified backend and its state, loadability, the load error and
key presence; backend trouble is reported, not raised. Command results remain
`LOCAL_WORKSPACE_COMMAND_1` v1; the additive `identity.custody` label states the
mode explicitly. `custody status` carries its diagnosis in a bounded `custody`
object.

## 9. Acceptance evidence

`tests/test_workspace_custody.py`: protected metadata carries no raw key bytes
(red control proves the scanner can fail); keys survive restart via an injected
durable store with stable fingerprints; missing sender/recipient keys fail
closed; backend failure is distinct from absence; unsuitable and unavailable
backends are refused before any read; a substituted or malformed stored value
is a named mismatch; a copied workspace without the store cannot load and is
not modified; no silent regeneration, raw fallback or environment fallback;
handles stay in their own namespace; migration preserves exact fingerprints and
removes raw bytes; failed migration (write failure and read-back substitution)
preserves the usable raw workspace and releases created entries; repeated
migration is a named no-op; the unchanged V2-01 workflow (send, list, open,
restart, duplicate) runs under os-store custody with injected stores; CLI
flags and refusals stay bounded. Every automated case injects a store; the
canonical suite never writes to the operator's real credential store.

## 10. What this does not claim

No wire-format or protocol change; no encryption at rest for the raw mode; no
protection against the authorized user's own session (case C), admin/kernel
compromise (D), hardware attack, human-identity proof or physical presence; no
automatic recovery on loss/reinstall/migration (E); no change to the frozen
`0.0.2a1` candidate; no publication. A workspace copy alone does not reveal the
private keys **only** in `os-store` mode, and only when the store of the
authorized account is intact.

SAIMAIL V2-01 section 10's limitation statement remains true for raw
workspaces; this document supersedes it for workspaces explicitly created or
migrated into `os-store` custody.
