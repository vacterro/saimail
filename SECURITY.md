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
