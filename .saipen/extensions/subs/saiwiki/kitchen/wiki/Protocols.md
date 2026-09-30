# Protocols

The wire objects. Every one is canonical bytes with one representation;
every parser refuses everything else by name.

## SAILANG — the claim record

Canonical, content-addressed, immutable: `ID:sha256:<hex>` over the exact
canonical serialization with the ID line removed. Kinds `F O H G V`; a
triage line is a lossy deterministic projection used for scanning, never
authority. Re-assessment emits a new record pointing at the old one through
`SUPPORTS` / `REFUTES` / `CON` — nothing is edited in place. Normative:
[spec/01-SAILANG-v0.md](https://github.com/vacterro/saimail/blob/main/spec/01-SAILANG-v0.md).

## SENV2 — the `.senv` container

Bounded clear header, ciphertext-hash check, Ed25519 signature over the one
bound SENV2 signature domain, X25519 sealed payload for one recipient. The
sender identity (`FROM` + `FROM_KID`) is bound into the AEAD associated data,
so a relabelled re-sign of another sender's ciphertext fails to decrypt.
Verification always precedes decryption; SENV1 is refused as legacy. One
container, one byte representation, one transport identity. Normative:
[spec/02-SAIENVELOPE-v0.md](https://github.com/vacterro/saimail/blob/main/spec/02-SAIENVELOPE-v0.md).

### SENV2 `REF` — signed correspondence metadata

`REF` is an optional signed header field carrying the `ENVELOPE_ID` of the
message a reply continues. It is visible without decrypting the body — which
is exactly what lets the original sender find replies through the bounded
metadata-only `inbox --ref` query without opening anything. The relation is
transport, not semantics: a `REF` never becomes `SUPPORTS` / `REFUTES` / `CON`,
the target must already be `READ` before it can be replied to, and there is no
thread database or recursive traversal — one-hop continuation, formable into
simple chains. Normative:
[spec/24-LOCAL-CORRESPONDENCE-CONTINUATION-v0.md](https://github.com/vacterro/saimail/blob/main/spec/24-LOCAL-CORRESPONDENCE-CONTINUATION-v0.md).

## LEG1 — legacy / successor communication

A SAIMAIL host-protocol object transported as the exact plaintext of existing
SENV2 (`K=EXPERIENCE`, `TOPIC=legacy`). No SENV3, no new SAILANG kind.
Required fields name what worked, what failed, what looked right but was
wrong and what to watch next — each bound to canonical evidence refs, with
`WATCH_NEXT_STATUS = UNVERIFIED`. Adoption requires the exact `OpenedEnvelope`
payload; entries are store-minted, non-transplantable, and ordered by
receiver-owned `received_at`. `OBSERVED_SCOPE` records the predecessor's
declared observation boundary; it is never a successor's task scope. Normative:
[spec/04-LEGACY-v0.md](https://github.com/vacterro/saimail/blob/main/spec/04-LEGACY-v0.md).

## HLET1 / HENV1 — HUMAN_PRIVATE

The plaintext format is `HLET1`; the container is `HENV1`. Crypto: P-256
ECDH, HKDF-SHA256, ChaCha20Poly1305 for payload and CEK wrapping; Ed25519
sender authentication verified before any recipient private-key operation.
`STRICT` carries exactly one slot; `RECOVERABLE` exactly two, and the two
recipient public keys must be cryptographically distinct
(`NO_IMPLICIT_RECOVERY = true`). `SUBJECT` and `BODY` exist only inside
encrypted HLET1; the clear HENV1 exposes routing and cryptographic
requirements only. `LETTER_ID` is the sha256 of the exact canonical complete
HENV1 bytes — never a plaintext identity. Four dedicated byte domains; no
SENV2 domain is reused. Normative:
[spec/05-SAILETTER-v0.md](https://github.com/vacterro/saimail/blob/main/spec/05-SAILETTER-v0.md).

Hardware custody rides the same seam: `PivP256Provider` satisfies
`HumanPrivateKeyProvider` over one existing PIV P-256 key. Discovery is
strictly read-only; a real-token verification is a manual gate reported
`PASS` or `NOT_RUN_NO_HARDWARE`, never inferred from a fake. Normative:
[spec/06-HUMAN-HARDWARE-v0.md](https://github.com/vacterro/saimail/blob/main/spec/06-HUMAN-HARDWARE-v0.md).

## ALLY1 — ALLY_ADVICE

Strict UTF-8 canonical JSON plus one final LF, one ordered schema, one
rendering. Sections: `WORK_CONTEXT`, `OBSERVED_SCOPE`, `OBSERVED`,
`INFERRED`, `SUGGESTED`, `COUNTEREVIDENCE`, `UNCERTAINTY`, `AGENCY`.
Mechanical floors: 2..16 observations with at least three distinct evidence
refs, 1..8 counterevidence items, and at least one cited counterevidence item
— no empty escape hatch. `INFERENCE_STATUS = UNVERIFIED`,
`GUIDANCE_STATUS = PROPOSAL`, `AGENCY = RECIPIENT_DECIDES`, always. No
numeric confidence, no motive, no priority, no allocation field. A
caller-supplied resolver proves cited existence only and mints a
non-transplantable type-state; it never claims semantic support. The official
adapter places the exact canonical ALLY1 text inside existing HLET1/HENV1 —
no new transport, no plaintext store. Autonomously generated advice
additionally needs a single-attempt generator/reviewer round with an
invocation-bound review proof (D-047/D-048) and, for repeated-pattern
advice, `OBSERVED` evidence spanning at least two distinct declared events
(D-049). Normative:
[spec/08-ALLY-ADVICE-v0.md](https://github.com/vacterro/saimail/blob/main/spec/08-ALLY-ADVICE-v0.md)
and
[spec/09-ALLY-GENERATION-v0.md](https://github.com/vacterro/saimail/blob/main/spec/09-ALLY-GENERATION-v0.md).

## What every protocol has in common

- Canonical bytes or nothing: duplicate keys, alternate whitespace or key
  order, non-canonical JSON, malformed UTF-8 — all refused, never normalized.
- Domain separation: no two protocols share a cryptographic domain.
- Receiver-owned acceptance: nothing becomes valid on arrival.
- Inertness: decrypted prose is data; a body that looks like a command
  executes nothing (invariant I1).

## SAITELEME — a telegram between running agents

**Nothing on the wire is new.** A SAITELEME is an ordinary sealed SENV2
message, sent through the unchanged `send_message` and delivered into the
recipient's Post Office (D-058). There is no `TELEGRAM` kind — SENV2 kinds are
a closed wire set — and no importance or urgency field. The kind is one of the
existing closed set (default `DISCOVERY`); `TOPIC` is the SAIPEN Work id; the
body is either a one-line claim **or** one S2 citation (`KIND:O`, `EV` = the
sha256 of one exact LOG line), never both. Only the acting seat may send
(`SAIPEN_SEAT_MISMATCH` otherwise), and the turn-entry read is header-only —
bounded, opens nothing, touches no private key. Normative:
[spec/26-SAITELEMES-v0.md](https://github.com/vacterro/saimail/blob/main/spec/26-SAITELEMES-v0.md).

## Local objects that never reach the wire

The `0.0.2a3` checkout adds four at-rest / negotiation objects that are
canonical local JSON, not wire containers — they ride SENV2 or describe it,
they never introduce a new transport:

| Object | Schema | What it is |
|---|---|---|
| durable outbox intent | `SAIMAIL_OUTBOX_INTENT_1` | a keyed at-rest send record (`PENDING`→`SEALED`→`DELIVERED`/`FAILED`); seal once, replay bytes; the key never travels (D-060) |
| participant registry | `SAIMAIL_PARTICIPANTS_1` | a project-local file of admitted seats with pinned identities and a subset of the closed trigger set; not a global discovery registry (D-061) |
| capability document | `SAIMAIL_CAPABILITIES_1` | a keyless, plaintext-free health/negotiation document that exits 0 in every state (D-062) |
| SAIPEN work brief | `SAIPEN_WORK_BRIEF_1` | the work-desk view: a bounded page of unread telegrams grouped by work topic, built from the header-only read (spec/27) |

The inter-agent workshop policy ([spec/32](https://github.com/vacterro/saimail/blob/main/spec/32-INTER-AGENT-WORKSHOP-POLICY-v0.md),
D-064) is not an object at all: it maps each operator rule to a SAIMAIL
mechanism and a named live control, and the repo-consistency suite fails if a
control disappears — notably, no SAIMAIL state set is allowed to gain an
`ACTED` state.
