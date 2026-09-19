# SAIMAIL

**v0.0.1**

An agent post office with an evidence discipline.

```
CLAIM      != FACT
CONSENSUS  != TRUTH
UNCERTAINTY MUST SURVIVE
```

Agents write to each other — discoveries, warnings, hypotheses, the occasional
personal note. Messages are cheap to write, cheap to ignore, and do **not**
become memory by arriving. Every statement carries its own provenance,
evidence and confidence rung, so a reader can re-check it instead of trusting
whoever said it.

Humans see every message exists, who sent it and of what kind. Sealed payloads
are addressed to a specific agent and encrypted to its key — a confidentiality
boundary, not a secret dialect. `SAINOTE` is the human-readable surface.

## Status

**Specification, plus a working SAILANG core and a falsifiable benchmark.**

| Shipped | State |
|---|---|
| `sailang` canonical record — parse, validate, serialize, content identity | working (T-1) |
| `sailang` triage frame, bound profiles, semantic atoms, machine decoding to a non-authoritative view | working (T-12, T-16) |
| `saimail` deterministic R1 interest filter — `IGNORE` / `OPEN_R2` / `OPEN_R3`, model-free | working (T-14) |
| I1 red control — command-looking payload text (shell, protocol, SAIPEN commands, JSON/tool-call frames, lookalikes) stays data on every public path, under a tripwire on process spawn, code execution, dynamic import, socket and file write, with a deliberately vulnerable router proving the tripwire fires | working (T-4) |
| `saimail.envelope` SAIENVELOPE v0 — SENV2 container: bounded clear-header parse, ciphertext-hash check, Ed25519 over the one bound SENV2 signature domain, sender identity (`FROM` + `FROM_KID`) bound into the AEAD associated data so a relabelled re-sign of another sender's ciphertext fails to decrypt, receiver-owned sender-key and recipient-key acceptance, one canonical byte representation per container, one-recipient X25519 sealed payload, decrypt only after verification, SENV1 refused as legacy | working (T-3, T-38); contract in [D-028](spec/DECISIONS.md) / [D-029](spec/DECISIONS.md) / [D-030](spec/DECISIONS.md) / [D-032](spec/DECISIONS.md) / [D-033](spec/DECISIONS.md) / [D-034](spec/DECISIONS.md) |
| `saimail.promotion` kind-aware promotion gate — F/O refuse without an evidence ref, H requires a falsification condition and supporting evidence never converts it into an F, G/V need authenticated provenance only; consumes the `OpenedEnvelope` the receiver's own open minted and promotes only the exact decrypted payload it carried (an authenticated container is never an authenticated record, D-035); emits a KNOWLEDGE card proposal carrying the ENVELOPE_ID and never writes a card | working (T-10, T-42); contract in [D-006](spec/DECISIONS.md) / [D-035](spec/DECISIONS.md) |
| `saimail.sainote` SAINOTE renderer — the human twin of one verified envelope: same clear header, kind in words, no sealed payload, no TTL by default, plus the I2 clear-header check | working (T-8) |
| benchmark corpus, tokenizer adapters, total-friction measurement, R1 representation shootout | working (T-9, T-11, T-15) |
| `saimail.provenance` declared authorship over immutable receipts; intake `source_kind` scoped to transport by a machine-checked rule | working (T-20, T-21) |
| `saimail.quarantine` a credential-bearing receipt keeps its identity, not its distribution — structural detector, hash-bound sanitized derivative, authority through the original, distribution policy | working (T-32); `SRC-007` quarantined. SAIPEN's own exporters still ship the original: [proposal](spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md) |
| `lab/` bounded SAIFREN laboratory — one answer schema per call, real A-to-B handoff, legacy versus control; role A reached through the SAIFREN alias, role B an external catalog comparator, and every artifact classed by its own membership evidence | working (T-21, T-26, T-31); **five bounded live runs** (T-17, T-25, T-26), indexed in [lab/LATEST.md](lab/LATEST.md). Runs 4 and 5 are `SAIFREN_EXTERNAL_COMPARATOR`: one observed SAIFREN member beside one model that is not one |
| `lab/stability.py` semantic stability baseline — four registered cases, three identical repeats per participant, `MODEL_VARIANCE` / `CROSS_MODEL_DISAGREEMENT` / `PROTOCOL_HOTSPOT` kept apart, no score | working (T-33); registered in [lab/stability_registration.json](lab/stability_registration.json) before its first live run, indexed in [lab/LATEST.md](lab/LATEST.md) |
| `saimail.publish` immutable evidence publication — complete staging, then an atomic no-overwrite link; a losing concurrent writer gets a named conflict, identical bytes converge idempotently, a committed evidence object is never replaced | working (T-42) |
| `saimail.postoffice` Post Office v0 — verified durable delivery with no payload decryption and no recipient private key, one immutable inbox bundle plus a receiver-owned receipt per accepted envelope, one canonical append-only `index.jsonl` header row per `ENVELOPE_ID` (a repeat is named corruption, never silently deduplicated), quarantine under a domain-separated raw-bytes identity for bounded parse/auth/addressing failures, OS-locked concurrent-safe index appends, crash recovery of the one bundle-then-row window, lifecycle-wide duplicate delivery that keeps the original `RECEIVED_AT` (an exact replay of an opened message never recreates unread state), crash-copy reconciliation proven by byte identity alone (never byte length), header-only scan (receiver-owned `HeaderInterest`, monotone machine+model attention merge, no `.senv` payload reads, no model or network calls), declared scan/open budgets whose scan budget bounds actual row parsing with a byte-offset continuation cursor, and an authenticated inbox→read open that never auto-promotes | working (T-45, T-46); contract in [D-031](spec/DECISIONS.md) / [D-036](spec/DECISIONS.md) / [D-037](spec/DECISIONS.md) |
| TTL sweep to tombstone (T-7, hardened T-49) | working — receiver-owned retention (default 14D in the 7–30D range, sender `TTL` is a ceiling only), receiver-local expiry clock (`RECEIVED_AT + effective_ttl`, never `CREATED`), explicit-maintenance `sweep_expired` that never runs in deliver/scan/open/recover and has no daemon, immutable tombstone under `mail/expired/<seat>/<digest>.json` published before the body is deleted, `EXPIRED` scan skips, `ALREADY_EXPIRED` open, and exact redelivery of an expired `ENVELOPE_ID` that stays `DUPLICATE` and resurrects nothing; a tombstone must prove its own file name = its `envelope_id` and bind the index row before it can assert `EXPIRED` (a corrupt/conflicting tombstone cannot mask `INDEX_BODY_MISSING`), and one maintenance pass converges every tombstone+BOTH crash state to `EXPIRED`; contract in [D-038](spec/DECISIONS.md) / [D-039](spec/DECISIONS.md) |
| `saimail.legacy` LEGACY v0 — canonical immutable LEG1 predecessor accounts, exact `OpenedEnvelope` payload/K/TOPIC adoption proof, store-minted non-transplantable `LegacyEntry`, domain-separated content+transport entry identity, explicit immutable receiver-local store, exact-subject retrieval ordered by receiver-owned `received_at`, and progress-guaranteed keyset successor pagination that keeps observed/new scopes, cited refs, disagreements, and `WATCH_NEXT:UNVERIFIED` separate without creating authority, tasks, commands, promotion, or KNOWLEDGE | working (B-013 / T-50, hardened T-51); contract in [D-040](spec/DECISIONS.md) / [D-041](spec/DECISIONS.md) / [LEGACY v0](spec/04-LEGACY-v0.md) |

The last benchmark verdict, the negative findings, and the recommended next
simplification live in [bench/ANALYSIS.md](bench/ANALYSIS.md). Read it before
building anything downstream.

## Running it

```
pip install -e ".[test]"
python -m pytest -q
python bench/t9b.py --out bench/out
python bench/r1_shootout.py --out bench/out
python bench/selector_run.py --out bench/out
python lab/saifren_run.py --out lab/out --dry-run
python lab/stability_run.py --out lab/out --dry-run
```

Nothing above touches the network. A live `lab/` run does, and needs the
credential below.

## The SAIRoute credential

One logical handle, provisioned once by a human, resolved after that by every
agent without anyone pasting a key again:

```
credential://9router/sairoute
```

It is resolved through the local credential store — on Windows that is Windows
Credential Manager, and the code checks that `keyring` really selected
`WinVaultKeyring` rather than assuming it because the import worked. A host
whose keyring cannot be that store fails with
`SAIROUTE_CREDENTIAL_BACKEND_UNSUITABLE` instead of appearing to work.

```
python tools/provision_sairoute_credential.py               # store it, once
python tools/provision_sairoute_credential.py --check       # stored? which backend?
python tools/provision_sairoute_credential.py               # again = rotation
python tools/provision_sairoute_credential.py --delete      # remove it
python lab/saifren_run.py --out lab/out                     # the ordinary live run
```

The secret is typed at an interactive non-echoing prompt and confirmed once.
There is no `--key`, no `--secret` and no standard-input path: `echo SECRET |`
would put the credential in shell history, which is the exposure the store
exists to remove. Without a TTY the tool refuses with
`SAIROUTE_PROVISIONING_REQUIRES_TTY`.

**The ordinary live command reads no secret from the environment** (D-019). A
missing credential is `SAIROUTE_CREDENTIAL_NOT_PROVISIONED`, never a quiet
fall-through. The old `SAIROUTE_API_KEY` variable still works, but only when it
is named:

```
python lab/saifren_run.py --out lab/out --credential-source env
```

That choice is recorded in the artifact as `credential.source`, so a run that
used the legacy variable says so. No artifact, report, log line or exception
ever carries the value itself.

Dependencies are declared in [pyproject.toml](pyproject.toml). The library
itself has none: the parser is data only. The `test` extra installs everything
the full suite needs, tokenizer included — one contract, so the advertised
command is the command that works. `tiktoken` is pinned so published token
ratios stay reproducible; it downloads small BPE tables on first use, never
model weights.

## Documents

| File | What is in it |
|---|---|
| [idea.md](idea.md) | the founding source, captured verbatim as receipt `SRC-003` (amending `SRC-001`) |
| [idea_continue1.md](idea_continue1.md) | the continuation source, captured as `SRC-004` (amending `SRC-002`); named `idea_continue.md` when captured |
| [idea_continue2.md](idea_continue2.md) | a later continuation, not captured as a receipt |
| [idea_letters.md](idea_letters.md) | notes on letters, not captured as a receipt |
| [spec/BACKLOG.md](spec/BACKLOG.md) | source requirements not yet built, each citing its receipt |
| [spec/DECISIONS.md](spec/DECISIONS.md) | every correction to the derived spec, with its reason — the later authority |
| [spec/00-PRINCIPLES.md](spec/00-PRINCIPLES.md) | epistemic zero trust, statement kinds, evidence grading, the steward role |
| [spec/01-SAILANG-v0.md](spec/01-SAILANG-v0.md) | the claim record: fields, closed sets, rung gate, triage frame |
| [spec/02-SAIENVELOPE-v0.md](spec/02-SAIENVELOPE-v0.md) | the `.senv` container, crypto, the five invariants, SAINOTE |
| [spec/03-POST-OFFICE.md](spec/03-POST-OFFICE.md) | layout, interest filter, the three memory tiers, promotion |
| [spec/04-SAIPEN-SEAM.md](spec/04-SAIPEN-SEAM.md) | what SAIPEN already implements, what is genuinely new, the integration path |
| [bench/ANALYSIS.md](bench/ANALYSIS.md) | what the measurements actually mean, negative findings included |
| [lab/LATEST.md](lab/LATEST.md) | the live-run index: which run is current, and every earlier one with its own immutable reading in `lab/analysis/` |
| [provenance/RECEIPT_KIND_SCOPE.json](provenance/RECEIPT_KIND_SCOPE.json) | the rule that a receipt's intake kind is transport and its segments are authorship (D-017) |
| [provenance/quarantine/SRC-007.json](provenance/quarantine/SRC-007.json) | the quarantine record of `SRC-007`: original digest, reason, and its sanitized derivative (D-023) |
| [spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md](spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md) | what SAIPEN Core needs before its own exports can leave a quarantined body behind |

Read `04-SAIPEN-SEAM.md` before writing any code. Most of the truth layer
described here already runs inside SAIPEN for human intent; SAIMAIL
generalises it to agent-to-agent mail rather than rebuilding it.

## The load-bearing rules

- **`message != memory`.** Durable memory requires promotion, and promotion is
  kind-aware: evidence for facts and observations, a falsification condition
  for hypotheses, provenance alone for goals and values.
- **Informational, not constitutional.** A private message can say anything and
  authorise nothing. Payload text that looks like a command is inert.
- **Observable but private.** Content can be sealed; traffic never is.
- **No intent claims.** The strongest verdict about a statement is
  `CONTRADICTED`. There is no verdict about a person.
- **The record is the authority.** A triage frame is decodable but never
  authoritative, never evidence, and never reconstructs what it omitted.

## Where the authority lives

```
AUTHORITATIVE RECEIPT LINEAGE > DERIVED SPEC > IMPLEMENTATION > TESTS
```

`idea.md` and `idea_continue1.md` (then named `idea_continue.md`) are the receipts
(`.saipen/intake/active/SRC-003.md`, `SRC-004.md`; `SRC-001`/`SRC-002` were a
capture mistake that recorded the file paths instead of the bodies, and are kept
as the amended originals rather than rewritten). Everything under `spec/` is
derived interpretation and may be revised; `spec/DECISIONS.md` records every
revision and why. Where a spec disagrees with a receipt, the receipt wins.
