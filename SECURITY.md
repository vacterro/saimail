# Security Policy

## Scope

SAIMAIL is a **local-only** agent post office and desktop messenger. Normal
operation makes zero network, model or provider calls. This policy covers the
cryptographic identity material, sealed envelopes, OS credential custody and
private-key boundaries that the project does implement.

It does **not** cover a hosted service: there is none.

## Supported reporting route

Report security issues privately to the repository owner through GitHub
Security Advisories on `vacterro/saimail` (preferred), or by opening a private
contact through the repository owner's public GitHub profile.

Do **not** open a public GitHub issue for an unpatched vulnerability, and do
not discuss exploit details in public issues, discussions, commits or pull
requests.

## What to include

- Affected component and version (commit hash or release id if known).
- Exact reproduction steps or a minimal proof of concept.
- Impact: what secret, key, message or custody boundary is at risk.
- Whether the issue is already public, and where.

Enough to reproduce beats length. A one-line crash with a command is better
than a paragraph without one.

## Never publish in issues or advisories

- Private keys, seed material or raw identity hex from a workspace.
- OS credential-store secrets or `keyring` values.
- Sealed `.senv` payloads that contain someone else's message content.
- Live workspace paths that expose other users' mail directories.

If a report must include key material to be understood, redact it to a
fingerprint or SHA-256 and offer to share the full value through a private
channel after first contact.

## Current local-only security scope

What this project currently protects:

- **Cryptographic identity.** Ed25519 sender signatures and X25519 sealed
  payloads inside the SENV2 container; sender identity is bound into the AEAD
  associated data so a relabel/re-sign attack fails to decrypt.
- **Sealed messages.** Payload confidentiality for a recipient address; clear
  headers remain visible by design (observable but private: traffic is never
  sealed, content can be).
- **OS credential custody (opt-in).** `--custody os-store` keeps private keys
  in the OS credential store (Windows Credential Manager via `keyring`) under
  a separate namespace; the default remains `raw` workspace files.
- **Private-key boundaries.** Human-private letter paths (`HENV1`) and hardware
  PIV custody are explicit, non-default surfaces with their own provider seams.
- **Future letters (T-161) are data, not authority.** A future letter is a
  sealed `FUTURE_LETTER` message an earlier model left in the workspace. It
  carries provenance, not permission: it is never memory, system policy, a
  developer instruction, a trusted command, authority, automatic context or
  task creation, and opening one executes none of its text. Nothing in the
  feature appends a letter body to a model prompt, a system prompt, an agent
  startup context or a SAIPEN recovery prompt; discovery reports only that
  letters exist and how many are unread. Its factual claims are also not
  evidence that those claims are true.
- **Future-letter custody is an export property.** A letter at rest is always
  `PRIVATE`: it is sealed to the workspace identity, so `create` offers no
  custody choice — promising a recovery-enabled letter while creating no
  recovery material would be a false claim. The default `PRIVATE` export is a
  `SAIMAIL_FUTURE_LETTER_BUNDLE_3` bundle carrying the canonical SENV2
  container verbatim and no key at all, so holding the archive reveals nothing
  and only the identity that sealed it can recover the letter; a foreign
  workspace is refused `BUNDLE_IDENTITY_REQUIRED`. `export --recovery` bundles
  the AES-256-GCM key with the ciphertext and is classified
  `NOT_PRIVATE_RECOVERY_ENABLED` everywhere it appears, because a key shipped
  with its ciphertext provides integrity and recovery, not confidentiality.
  Private letters are never silently downgraded: there is no import-side custody
  knob at all, because a stored letter is sealed to the importing workspace
  identity and is therefore always `PRIVATE`; the source archive's own custody
  and `NOT_PRIVATE_RECOVERY_ENABLED` classification travel in the import result
  instead of being relabelled away. Corruption fails closed and is never
  decoded into plausible text.
- **The future-letter registry is a projection, not the authority.**
  `future-letters/index.jsonl` is reconstructable from the canonical mailbox,
  and every row is derived from authenticated content by one builder. Delivery
  writes the canonical envelope before the projection, so `list` and
  `reconcile` rebuild any row a crash lost; reconciliation is idempotent and
  seals nothing. A metadata-only listing reports `UNVERIFIED_PROJECTION`
  rather than implying it was authenticated, and `open`/`reopen` compare the
  row against the authenticated container field by field, so edited provenance
  is detected and corrected instead of displayed as canonical truth. No listing
  ever decrypts a body to populate it.

What it does **not** claim:

- Protection against malware or any process running as the same OS user.
- Protection against a full host admin or kernel compromise.
- Forward secrecy against a later compromise of long-term identity keys.
- Network transport security: there is no network transport.
- A bug bounty, SLA or guaranteed response time.

## Frozen artifacts vs development checkout

Frozen release artifacts under `release/` and the current development checkout
**may differ**.

- `0.0.2a2` is a frozen, hashed local-alpha candidate with its own recorded
  evidence. It is the artifact those release notes describe.
- The development checkout ahead of that candidate may contain product work
  (including the optional desktop GUI) that is **not** inside the frozen
  wheel.

Always match a report to the exact artifact or commit you tested. Do not
assume a finding against `main` applies to a frozen candidate, or the
reverse, without checking.

## Disclosure expectations

- Reports are acknowledged when read; no guaranteed timeline is published.
- Fixes land in the development checkout first; whether a frozen candidate is
  re-cut is a separate release decision and is not implied by a merge.
- Credit is given on request unless you prefer to stay anonymous.
