# SAILETTER v0 — HUMAN_PRIVATE letters (HLET1 / HENV1)

This document is the contract `D-042` records and `saimail/sailetter.py`
implements. It never invents a second contract. The addressee classes are
`HUMAN_PUBLIC` (today's SAINOTE), `HUMAN_PRIVATE` (this document), and
`HUMAN_EPHEMERAL` (future; not implemented).

A HUMAN_PRIVATE letter is one human's prose, encrypted to that human's own
cryptographic identity. Agent-private transport (SENV2) and human-private
transport are separate protocols: no SENV2 field, domain, byte layout or parser
behaviour is reused, and this container is `HENV1`, never `SENV3`.

## 1. Identity — `HUMAN_ID`

```
human-id:sha256:<64 lowercase hex>
```

The digest is `sha256` over the exact canonical DER `SubjectPublicKeyInfo` of a
P-256 public key. The primary public key defines the human identity; a display
name is never authorization. A caller-supplied `human_id` is verified against
the key and refused on mismatch. A recovery public key must have a different
digest than the primary key.

## 2. Plaintext grammar — `HLET1`

```
HLET1
CLASS:HUMAN_PRIVATE
TO_HUMAN:human-id:sha256:<64 lowercase hex>
CREATED:YYYY-MM-DDTHH:MM:SSZ
SUBJECT_B64:<base64>
BODY_B64:<base64>
```

* UTF-8, LF only, no BOM, no CR, exactly one final LF. Exactly these six lines,
  in this order; missing, duplicate, reordered or unknown lines refuse.
* `SUBJECT` and `BODY` are UTF-8 text encoded as one canonical standard base64
  value with padding. `BODY` may be multiline; no trimming, no Unicode
  normalization, no other transformation is applied. The bytes that arrive are
  the bytes that round-trip.
* `SUBJECT` is 1..256 UTF-8 bytes, `BODY` is 1..65536 UTF-8 bytes, and the whole
  canonical `HLET1` rendering is at most 98304 bytes. Each is checked before any
  crypto.
* `CREATED` is an exact canonical UTC instant. `TO_HUMAN` is a full `HUMAN_ID`.
* One logical letter has exactly one accepted byte representation: `parse`
  compares the input against its own canonical rendering and refuses anything
  else.
* Inner `TO_HUMAN` must equal outer `HENV1` `TO_HUMAN` after decryption; the
  layer that decrypts enforces it.

## 3. Container grammar — `HENV1`

```
HENV1
FROM:<seat>
FROM_KID:sha256:<64 lowercase hex>
TO_HUMAN:human-id:sha256:<64 lowercase hex>
MODE:<STRICT|RECOVERABLE>
PRIMARY_KID:human-id:sha256:<64 lowercase hex>
RECOVERY_KID:human-id:sha256:<64 lowercase hex>|NONE
PRIMARY_EPK:<base64>
PRIMARY_WRAP_NONCE:<24 lowercase hex>
PRIMARY_WRAPPED_CEK:<base64>
RECOVERY_EPK:<base64>
RECOVERY_WRAP_NONCE:<24 lowercase hex>
RECOVERY_WRAPPED_CEK:<base64>
PAYLOAD_NONCE:<24 lowercase hex>
PAYLOAD_B64:<base64>
SIG:ed25519:<128 lowercase hex>
```

* `TO_HUMAN` equals `PRIMARY_KID`: the primary key is the human identity.
* `MODE:STRICT` carries exactly one slot: `RECOVERY_KID:NONE`, and the three
  `RECOVERY_*` lines are absent. `MODE:RECOVERABLE` carries exactly two slots:
  a full `RECOVERY_KID` and all three `RECOVERY_*` lines, with
  `RECOVERY_KID != PRIMARY_KID`. Any other cardinality, an unknown mode, a third
  slot, a duplicate field or an out-of-order field refuses at parse time.
* `EPK` values are DER `SubjectPublicKeyInfo`, base64; the parser refuses bytes
  that are not a P-256 public key before any key agreement runs.
* `WRAP_NONCE` and `PAYLOAD_NONCE` are 12-byte values as 24 lowercase hex.
  `WRAPPED_CEK` is the 48-byte AEAD output (32-byte key plus 16-byte tag) as
  base64. `PAYLOAD_B64` is at most 98304 + 16 bytes decoded.
* Container bytes are at most 262144. One container has exactly one accepted
  byte representation: `parse` re-renders and refuses any difference, so the
  same logical container cannot be minted twice under two `LETTER_ID`s.
* The clear container exposes routing and cryptographic requirements only.
  `SUBJECT`, `BODY`, a clear plaintext hash and any display name are absent.

## 4. Domain separation

Four immutable byte domains; no SENV2 domain is reused:

```
SAIMAIL-HENV1-PAYLOAD\0
SAIMAIL-HENV1-CEK-PRIMARY\0
SAIMAIL-HENV1-CEK-RECOVERY\0
SAIMAIL-HENV1-SIGNATURE\0
```

## 5. Key schedule

One fresh random 256-bit `CEK` per container encrypts the canonical `HLET1`
bytes exactly once:

```
payload nonce      = 12 random bytes
payload key        = CEK
payload AAD        = PAYLOAD_DOMAIN || canonical payload binding (section 6)
payload ciphertext = ChaCha20Poly1305(CEK).encrypt(nonce, HLET1, AAD)
```

For every authorized slot (fresh ephemeral keypair per slot):

```
ephemeral          = fresh P-256 keypair
epk                = DER SubjectPublicKeyInfo of the ephemeral public key
shared             = ECDH(ephemeral private, slot recipient public)
wrap key           = HKDF-SHA256(ikm = shared, salt = epk, length = 32,
                                 info = CEK-PRIMARY or CEK-RECOVERY domain)
wrap AAD           = slot domain || canonical wrap binding (section 6)
wrapped CEK        = ChaCha20Poly1305(wrap key).encrypt(wrap nonce, CEK, AAD)
```

`STRICT` creates exactly the `PRIMARY` slot; `RECOVERABLE` creates exactly
`PRIMARY` and `RECOVERY`. When `RECOVERABLE` is selected without an explicitly
supplied, cryptographically distinct recovery public key, sealing refuses. No
recovery key is derived, duplicated, inferred or invented.

## 6. Bindings (acyclic)

Canonical payload binding, UTF-8, LF, final LF, fixed order:

```
HENV1
FROM:<seat>
FROM_KID:<fingerprint>
TO_HUMAN:<human-id>
MODE:<STRICT|RECOVERABLE>
PRIMARY_KID:<human-id>
RECOVERY_KID:<human-id|NONE>
```

Canonical wrap binding, UTF-8, LF, final LF, fixed order:

```
HENV1
FROM:<seat>
FROM_KID:<fingerprint>
TO_HUMAN:<human-id>
MODE:<STRICT|RECOVERABLE>
SLOT:<PRIMARY|RECOVERY>
RECIPIENT_KID:<slot human-id>
```

Payload AAD is the payload domain followed by the payload binding; wrap AAD is
the slot domain followed by the wrap binding. No ciphertext hash, no `SIG` and no
`LETTER_ID` enters any binding, so no construction is circular.

The signature input is the signature domain followed by every container line
except `SIG`, in canonical order. Relabelling `FROM`, `FROM_KID`, `TO_HUMAN`,
`PRIMARY_KID` or `RECOVERY_KID` and re-signing with another accepted key still
fails decryption, because the sealed layer authenticates the binding it was
created under.

`LETTER_ID = "sha256:" + hex(sha256(exact canonical complete HENV1 bytes))`.
It is transport identity, never plaintext, semantic-message, knowledge or
evidence identity.

## 7. Modes, recovery and refusals

```
STRICT       exactly one authorized key; loss of it means loss of
             decryptability; no recovery path is inferable
RECOVERABLE  PRIMARY and an explicitly supplied, cryptographically distinct
             RECOVERY key; both are authorized decryptors
```

`RECOVERABLE` never degrades into `STRICT` silently and `STRICT` never grows a
recovery slot silently. An unrelated recipient private key refuses before any
key agreement. In `RECOVERABLE`, opening through `PRIMARY` and opening through
`RECOVERY` each yield the identical canonical `HLET1` bytes.

## 8. Open order — verify before private-key work

```
bounded parse
-> structural and canonical validation
-> sender key resolution (receiver-owned acceptance)
-> Ed25519 signature verification
-> recipient identity, mode and slot validation (provider identity only)
-> recipient private-key provider ECDH operation
-> CEK unwrap
-> payload decrypt
-> canonical HLET1 parse
-> inner/outer TO_HUMAN equality
```

No recipient private-key provider operation may occur before signature
verification succeeds:

```
INVALID_SENDER_SIGNATURE -> ZERO_RECIPIENT_PRIVATE_KEY_CALLS
```

## 9. Provider seam

`HumanPrivateKeyProvider` exposes only:

* `human_id` — the recipient key identity it holds; and
* `exchange(ephemeral_public_key) -> shared secret` — the P-256 ECDH operation.

Core never requires, exports or retains private-key bytes. `SoftwareP256Provider`
is a reference implementation for tests: its key lives in process memory and it
provides no hardware protection and no claim of one.

## 10. Ciphertext-only store

Layout under a caller-supplied root, one immutable file per committed letter:

```
<root>/human-private/<human-id-digest>/<LETTER_ID-digest>.henv1
```

* **Delivery** takes raw `HENV1` bytes, parses, verifies the sender signature
  against the receiver-owned acceptance registry, matches the recipient
  `HUMAN_ID`, and publishes immutably. No decryption, no recipient private key.
  An exact `LETTER_ID` replay is `DUPLICATE` and idempotent; nothing is
  overwritten.
* **Listing** reveals only clear `HENV1` metadata genuinely present: letter
  identity, sender seat and fingerprint, mode, slot identities and file size.
  Never `SUBJECT`, never `BODY`, and no invented clear subject field.
* **Open** is explicit and stateless: load the immutable container, parse,
  verify the sender signature, run the provider operation, decrypt, return the
  opened type-state. `HLET1` plaintext is never persisted; no read-state
  metadata is created.
* No plaintext sidecar, subject index, body cache, decrypted cache or
  sent-plaintext archive is ever created. `PLAINTEXT_PERSISTENCE_BY_SAIMAIL =
  forbidden`. No cross-system write, no model or network call, no command
  execution.

## 11. Opened type-state

`OpenedHumanPrivateLetter` is minted only after an authenticated successful
decrypt, through a constructor-only `InitVar` mint that is not retained on the
instance. Direct construction, `dataclasses.replace` and any transplant refuse.
This is normal-public-API integrity, not hostile-process security (D-015).

## 12. Claims and non-claims

Claimed: ciphertext cannot be decrypted through SAILETTER without an authorized
recipient private-key operation, and SAIMAIL APIs do not intentionally persist
decrypted plaintext.

Not claimed: that plaintext never exists in process memory; that root or
administrators cannot capture plaintext; that malware cannot; that screen
capture is impossible; that Python erases plaintext memory; that FIDO2 encrypts
a message; or that the software reference provider is hardware-backed. After
legitimate decryption the normal OS and recipient process are outside the
cryptographic confidentiality guarantee.

## 13. Non-goals

Not implemented by v0 and not implied by this document: `HUMAN_EPHEMERAL`,
hardware key providers (PIV, OpenPGP, PKCS#11), FIDO2 presence, contextual
reveal, human UI, notifications, background or automatic decryption, plaintext
search, server key escrow, agent recovery keys, and any automatic LEGACY,
KNOWLEDGE or memory write from private prose. Private prose is inert data.
