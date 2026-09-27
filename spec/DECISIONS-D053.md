# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-053 — workspace identity key custody is a named mode, and the OS store is the protected one (T-89 / V3-01)

The defect class is a workspace directory that is also an identity: V2-01 wrote
the Ed25519 and X25519 private keys as raw hex into
`identity/identity.json`, so copying the directory copied the identity. V3-01
records the threat model and chooses the smallest custody boundary that
materially improves it.

**Decision.** `OS_STORE_CUSTODY_SELECTED`. Workspace identity custody is an
explicit, durable mode. The protected mode stores both private keys in the
already-tested OS credential store (`saimail/credentials.py`, D-019) under the
separate `credential://saimail-workspace/...` namespace; the durable identity
file (`SAIMAIL_LOCAL_IDENTITY_2` v1, version 2) carries handles and public
material only. There is no new cryptography, no wire-format change and no
protocol semantics change; the SAIRoute credential handle and namespace are
never reused. Hardware custody (D-043) belongs to another identity family and
is explicitly not part of this decision.

**Objective.** Exactly `WORKSPACE_DIRECTORY_COPY_ALONE_DOES_NOT_REVEAL_PRIVATE_IDENTITY_KEYS`.
Malware running as the authorized user, admin/kernel compromise, human-identity
proof, hardware isolation, physical presence, forward secrecy and automatic
recovery are not claimed; loss/reinstall/migration availability is a stated
residual risk. The threat model, option comparison and claim boundaries live in
[spec/20](20-LOCAL-KEY-CUSTODY-v0.md).

**Modes and defaults.** `raw` (the V2-01 layout) remains readable and is never
silently mutated; it stays the documented default for new workspaces because
the core package keeps zero required runtime dependencies and the alpha's
install contract is unchanged. `os-store` is selected explicitly at
`init --custody os-store` or by the explicit, transactional
`custody migrate` command, which preserves fingerprints exactly and leaves the
old workspace intact on any failure. Repeated migration is the named no-op
`CUSTODY_ALREADY_PROTECTED`. Failure semantics are named and never collapsed:
`CUSTODY_BACKEND_UNAVAILABLE`, `CUSTODY_BACKEND_UNSUITABLE`,
`CUSTODY_KEY_MISSING`, `CUSTODY_KEY_MISMATCH`, `CUSTODY_ACCESS_FAILED`,
`CUSTODY_MIGRATION_CONFLICT`.

**Dependency.** `keyring` remains an optional `credentials` extra; protected
custody requires it and fails with a named error and an install hint when it is
absent. Moving the default to protected custody for a distributed package is a
release-decision question (candidate D1), not a side effect of this ticket.

**Evidence.** `tests/test_workspace_custody.py` proves the contract with
injectable stores: no raw key bytes in protected metadata, restart and copy
behavior, fail-closed missing/substituted/unsuitable/unavailable cases,
no-regeneration and no-environment-fallback guards, transactional migration and
rollback, exact fingerprint stability and the unchanged V2-01 workflow under
the new mode. The canonical suite never writes into the operator's real
credential store.

Regression evidence: `spec/20-LOCAL-KEY-CUSTODY-v0.md`,
`saimail/custody.py`, `saimail/workspace.py`, `saimail_local.py`,
`lab/stable_local_api.json`, `tests/test_workspace_custody.py`.

---
