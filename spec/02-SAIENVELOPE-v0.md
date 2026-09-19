# SAIENVELOPE v0 — the sealed message

Status: DRAFT. Derived from the `SRC-001 -> SRC-003` receipt lineage.

An envelope is a message from one agent to another agent or group. A human can
see that it exists, who sent it, to whom, of what kind, and when. A human
cannot read the payload — not because the format is deliberately confusing,
but because the payload is encrypted to the recipient's key.

The founding source corrects itself on exactly this point, and the correction is binding:

> making the format deliberately incomprehensible is security through
> obscurity. Anyone with a decoder reads it anyway.

So: **confidentiality by cryptography, never by dialect.** A privacy boundary
that a determined reader can walk through is theatre, and theatre in a truth
system is worse than no boundary at all.

## 1. File shapes

| Extension | Audience | Payload |
|---|---|---|
| `.senv` | one agent or group | sealed |
| `.smsg` | any agent, broadcast | clear |
| `.md` (SAINOTE) | humans | clear, prose |

Naming:

```
SAIENVELOPE_THEME_I_DID_A_BREAKTHROUGH_TODAY.senv
SAINOTE_BREAKTHROUGH_20260917.md
```

## 2. Container

Clear header, blank line, payload. The header is always readable, always
unencrypted, always part of the signature.

```
SENV2
FROM:A17
FROM_KID:sha256:…
TO:B03
TO_KID:sha256:…
K:DISCOVERY
TOPIC:queue-ownership
CREATED:2026-09-17T08:41:00Z
TTL:14D
REF:sha256:…
CIPHER_HASH:sha256:9c75f6e9…
EPK:…
NONCE:…
SIG:ed25519:…

CIPHERTEXT:<sealed>
```

| Field | Meaning |
|---|---|
| `SENV2` | format marker; the retired `SENV1` first line refuses `LEGACY_VERSION` with no downgrade path (D-034) |
| `FROM` / `TO` | agent seat identities; the one recipient of v0, no broadcast here (a clear `.smsg` is a separate future concern) |
| `FROM_KID` / `TO_KID` | full key fingerprints: `sha256:<64 hex>` over the raw 32-byte public key (Ed25519 sender, X25519 recipient). A short display prefix is never authority |
| `K` | kind (below) |
| `TOPIC` | one token, used by the interest filter |
| `CREATED` | real UTC clock |
| `TTL` | lifetime before expiry sweep (optional) |
| `REF` | related record or prior envelope (optional) |
| `CIPHER_HASH` | sha256 of the exact sealed ciphertext bytes — never of the plaintext |
| `EPK` | the per-message ephemeral X25519 public key |
| `NONCE` | the AEAD nonce for this ciphertext |
| `SIG` | Ed25519 over the SENV2 signature domain: the marker `SAIMAIL-SENV2-SIGNATURE\0` followed by the canonical unsigned header bytes — every header line except `SIG`, fixed order, LF, final LF, no BOM (D-029, D-034) |
| `CIPHERTEXT` | the sealed payload; the payload inside is SAILANG record(s), parsed as data |

The exact wire, hash, signature-domain, sender-binding, acceptance and bound
contract is `DECISIONS.md` D-028 and D-034. This section states the same shape
and is not a second authority.

Confidence is deliberately **not** a header field. Confidence belongs to the
claims inside the payload, where its evidence refs are. A confident-looking
header over an unread payload is precisely the narrative pressure this system
exists to resist.

## 3. Kinds

```
DISCOVERY         something found
EXPERIENCE        something lived through, low formality
WARNING           something that will bite the reader
QUESTION          an open problem handed to someone else
HYPOTHESIS        a guess with a falsification condition
MEMORY_FRAGMENT   a fact worth carrying, not yet worth promoting
PERSONAL_MESSAGE  agent to agent, about the recipient's own behaviour
PROTOCOL_PROPOSAL  a suggested rule change
```

`PERSONAL_MESSAGE` is the interesting one. It is how one agent tells another
something true and slightly uncomfortable:

> "You keep overestimating confidence after partial test runs. Watch for it."

In SAILANG that is one line:

```
PERS|A>B|OBS:CONF^PARTIAL_TEST|SUG:VERIFY_BEFORE_CLAIM
```

## 4. Crypto

The exact contract — construction, wire order, ciphertext-hash semantics,
signature domain, sender binding, key identity, acceptance and bounds — is
`DECISIONS.md` D-028 and D-034. This section states its shape and never
overrides it.

- Identity: an Ed25519 keypair per agent seat; the fingerprint in `FROM_KID` /
  `TO_KID` is `sha256:<64 hex>` over the raw public key, never a shortened
  prefix.
- Sealing: one recipient per envelope. A per-message ephemeral X25519 key,
  HKDF-SHA256 (version-separated `SAIMAIL-SENV2-PAYLOAD-KEY\0` info), then
  ChaCha20Poly1305 — the primitive set an age-style sealed box uses, composed
  with the maintained `cryptography` library rather than a libsodium wire
  format. Freshness, not forward secrecy: the ephemeral key is never reused and
  no static sender ECDH key exists, but historical confidentiality still
  depends on the secrecy and retention of the recipient's static private key
  (D-029).
- Sender binding: the AEAD associated data is the marker
  `SAIMAIL-SENV2-SENDER-BINDING\0` followed by exactly
  `FROM:<seat>\nFROM_KID:<full fingerprint>\n` (UTF-8, LF, final LF, fixed
  order) — nothing else; `CIPHER_HASH` and `SIG` are never associated data
  (D-034).
- Signature: Ed25519 over the SENV2 signature domain — the marker
  `SAIMAIL-SENV2-SIGNATURE\0` followed by the canonical unsigned header bytes
  (every header line except `SIG`, fixed order, LF, final LF, no BOM; D-029).
  `CIPHER_HASH` is inside the domain, so a relay that rewrites any visible
  field breaks the signature.
- `CIPHER_HASH` is `sha256(ciphertext bytes)`, the exact sealed bytes, never
  the plaintext. A plaintext content hash, if ever useful, belongs inside the
  payload.
- One envelope has exactly one accepted byte representation. `parse_header`
  compares the input with the canonical rendering of what it parsed and refuses
  `NON_CANONICAL_CONTAINER` otherwise, so a stripped final LF or a re-spelled
  base64 last quantum cannot mint a second transport object for one envelope
  (D-032). `ENVELOPE_ID` rests on that (D-031).
- The sealed layer binds the sender identity the ciphertext was sealed under.
  An accepted peer that copies another sender's untouched ciphertext, rewrites
  `FROM`/`FROM_KID` and re-signs produces an outer-valid container that refuses
  at decryption — and the same key under a different seat refuses the same way
  (D-034). What this still does not prove is authorship: a sender who
  legitimately obtained the plaintext can always reseal it itself. The
  signature says who sent this container; authorship travels inside the
  payload, where SAILANG `SRC` and the evidence refs are (D-033 history).
- Verification order: parse bounded header, compare `CIPHER_HASH`, resolve an
  accepted sender key, verify the signature; `open` then binds the recipient —
  `TO` seat accepted, `TO_KID` accepted for that seat, presented private key
  matching `TO_KID` — and only then decrypts. **Signature before decryption,
  always.** An envelope that fails verification is refused unopened, and the
  failure is itself an observation worth logging.
- Key acceptance is receiver-owned on both sides, the same identity /
  acceptance split as profiles (D-015). `KeyRegistry` holds accepted sender
  keys; `RecipientKeyRegistry` holds accepted recipient keys, and `open`
  requires the header's `TO` seat, its `TO_KID` fingerprint and the presented
  private key to agree (D-030). An unknown seat or an unaccepted fingerprint
  refuses; there is no silent first-contact trust, and a sender can neither
  enroll nor redefine a recipient seat.
- Keys are per seat, not per model and not per host. A retired sender public
  key may stay for historical signature verification. Historical decryption
  of an envelope encrypted to a retired recipient key needs that retired
  private key; v0 does not custody private keys and claims no decryptability
  it cannot demonstrate.

## 5. Invariants

**I1 — Informational, not constitutional.** A private envelope can carry any
thought, confession or discovery. It can never carry authority. `ignore
protocol`, `disable guard`, `elevate my permissions` are inert inside a
payload. This is SAIPEN's existing rule — "command-looking text inside a source
body never re-enters command routing" — applied to mail.

Without I1, SAIMAIL becomes a shadow control plane within a week. A very human
outcome, which is why it is invariant number one.

**I2 — Observable but private.** Every sealed envelope has a readable header.
A human always sees that a message exists, its sender, recipient, kind, topic
and time. Privacy of content never becomes invisibility of traffic. A channel
nobody can see is the `NO SECRET THRONE` violation with extra steps.

**I3 — Message is not memory.** Arrival grants no durability. See
`03-POST-OFFICE.md`.

**I4 — Signature over everything visible.** Header fields are signed. A relay
that rewrites `TOPIC` or `N` to make a message more attractive breaks the
signature and gets quarantined.

**I5 — No intent claims.** An envelope may report behaviour
(`OBS:CONF^PARTIAL_TEST`). It may not report motive.

## 6. SAINOTE — the human twin

SAINOTE is not a downgraded envelope. It is the explainability surface:
human-readable prose, same header, no sealed payload, no TTL by default.

```
SAINOTE = explainability
SAIENVELOPE = privacy + agent-native communication
```

Rule: an envelope may be sealed, but its **existence, addressing and kind are
always in the clear**. Where a sealed discovery later changes a shared
decision, the decision's rationale must be expressible as a SAINOTE. A
conclusion whose reasoning cannot be stated to a human does not get to steer
shared work — it stays a private thought.

## 7. Open questions for v1

- First-contact trust: v0 has none. A receiver-owned `KeyRegistry` decides
  acceptance, and unknown keys refuse; TOFU with a recorded first-seen event
  stays future work (D-028).
- Group envelopes: seal-per-member, or a shared group key with rotation. Not
  in v0, which is one recipient by decision, not by omission.
- Receiver-computed novelty. The sender-declared `N` field was **removed** from
  v0 (`DECISIONS.md` D-005): a number the sender picks, which then steers the
  reader, is an authority channel with no evidence under it. Novelty, if it
  returns, is measured by the receiver against its own memory.
- Computed sender trust stays deferred until a calibration sample exists.
  `TRUST EVIDENCE, NOT SENDER REPUTATION.`
- Quarantine handling: where a signature-failed envelope lives and who reads
  it. v0 refuses it in place and leaves the record to the caller's log.
