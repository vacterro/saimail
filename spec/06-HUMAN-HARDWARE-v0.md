# SAILETTER hardware custody v0 — PIV P-256 provider and read-only discovery

Normative contract: [D-043](DECISIONS.md) and [D-042](DECISIONS.md). This
document describes the hardware extension of the HUMAN_PRIVATE provider seam:
what `HARDWARE_BACKED` means in SAIMAIL v0, how the PIV backend is structured,
what an operator tool may read, and what nothing in this layer may claim. It
does not change `spec/05-SAILETTER-v0.md`: HLET1, HENV1, the four domains and
every binding are untouched, and hardware-specific code lives outside
`sailetter.py`.

## 1. Three concepts, deliberately separate

```
HUMAN_IDENTITY          = human-id:sha256:<P256-SPKI-digest>   (D-042)
PRIVATE_KEY_CUSTODY     = where the private key lives           (software / PIV token)
LOCAL_INTERACTION_POLICY = PIN and/or touch demanded by the token before ECDH
```

None of these is collapsed into "authentication". A touch proves that the
physical device demanded a touch; it does not identify the person. A PIN proves
successful knowledge-factor verification according to the device/session policy;
it does not prove intent.

## 2. What HARDWARE_BACKED means

Claimed, and nothing else:

* the recipient P-256 private key is held by a supported hardware token;
* SAIMAIL receives only the public key and the ECDH shared secret;
* SAIMAIL never requests, exports or stores raw private-key material
  (`PRIVATE_KEY_EXPORT = forbidden`);
* the ECDH operation is performed by the token through the provider.

Not claimed: that the OS, an administrator or malware cannot observe decrypted
plaintext or invoke the provider; that the token proves subjective human intent;
that the sender knows who touched the device; that the whole application is
hardware-isolated.

## 3. Reference credential profile and slots

The future provisioned SAILETTER credential (a future explicit gate, never
performed by this wave):

```
KEY_TYPE     = ECCP256
PIN_POLICY   = ONCE        (ALWAYS accepted; ONCE preferred)
TOUCH_POLICY = ALWAYS
REFERENCE_SLOT = 9D        (operator-selected, never assumed free)
ALTERNATE_SLOTS = 82..95   (operator-selected retired-key slots)
AUTOMATIC_SLOT_WRITE = false
```

A pre-existing P-256 key may be cryptographically compatible while demanding
less interaction than the reference profile. Such a key is classified
`COMPATIBLE_WEAK_POLICY` (the handoff's
`COMPATIBLE_CRYPTO_WEAK_INTERACTION_POLICY`): usable through the provider,
never described as the canonical hardened credential. `PIN_POLICY = NEVER` and
`TOUCH_POLICY = NEVER` never satisfy the hardened profile. When the backend
cannot read policies the classification stays `UNKNOWN_POLICY`; uncertainty is
preserved, never inferred into security.

HENV1 identity does not change with the transport or the slot: the recipient
identity is the fingerprint of the public key itself. Serial number, slot and
firmware version are local operator metadata only and never enter HENV1.

## 4. Provider seam

`saimail/hardware_piv.py` implements `PivP256Provider`, which satisfies the
existing `HumanPrivateKeyProvider` protocol (`human_id` plus
`exchange(ephemeral_public_key) -> 32-byte P-256 ECDH secret`). The open path
(`open_verified`, `HumanPrivateStore.open`) needs no hardware branch: the only
new behavior travels through `exchange`, exactly as D-042 designed it.

Construction reads the configured slot's public key once, requires ECC P-256,
derives `human_id()` from the actual key, and refuses with
`HARDWARE_IDENTITY_MISMATCH` when a caller-supplied expected HUMAN_ID does not
match. RSA, P-384, empty and unreadable slots refuse before any decrypt
attempt. Identity is re-checked when a session opens for a private operation,
so a swapped token cannot silently answer for the configured identity.

The provider exposes no private-key accessor of any kind. The public slot key
is exposed as SPKI DER for verification and display.

### 4.1 Backend abstraction

The provider talks to a narrow internal backend interface, not to vendor code:

```
PivBackend.list_devices() -> tuple[PivDevice, ...]
PivBackend.open(device)   -> PivSessionHandle
PivSessionHandle.read_slot(slot) -> PivSlotInfo
PivSessionHandle.pin_required(slot) -> bool
PivSessionHandle.verify_pin(pin: str) -> None
PivSessionHandle.exchange(slot, ephemeral_public_key_spki) -> bytes
PivSessionHandle.close() -> None
```

The interface contains no operation that can mutate a token. Tests drive a
deterministic fake backend whose key is a real software P-256 private key, so
every ECDH result is genuine cryptography, not a constant. The production
`YubicoPivBackend` is a thin adapter over Yubico's maintained Python stack and
lazily imports it; without the optional extra it refuses with
`YUBIKEY_PROVIDER_UNAVAILABLE`. Backend and vendor failures are normalized into
the stable `HARDWARE_*` refusal codes below; raw APDU data and PIN material
never appear in an error.

### 4.2 Session, PIN and touch discipline

One explicit `exchange` call is one session: open, re-verify identity, optional
PIN verification, one ECDH operation, close — including on error. No background
operation, no polling, no cached session, no automatic decrypt.

The PIN never lives in provider constructor state. A narrow callback seam
(`PinProvider`) is consulted only when a private operation begins and the slot
demands PIN verification; the reference CLI uses `getpass` at that moment. One
user-supplied attempt per explicit request; an invalid PIN is surfaced as
`HARDWARE_PIN_INVALID` with the backend's remaining-attempt count when
available, and there is no speculative retry.

Touch is hardware-enforced and never faked. The application requests the ECDH
operation; when the device reports touch required, timeout or cancellation, the
result is surfaced as `HARDWARE_TOUCH_REQUIRED`, `HARDWARE_TOUCH_TIMEOUT` or
`HARDWARE_OPERATION_CANCELLED` — never converted into "wrong key" or
"decryption failure".

### 4.3 Normalized refusals

At minimum, and as a closed set used by the provider:

```
HARDWARE_PROVIDER_UNAVAILABLE   optional YubiKey extra absent (also YUBIKEY_PROVIDER_UNAVAILABLE)
HARDWARE_NOT_FOUND              no matching PIV token
HARDWARE_MULTIPLE_MATCHES       more than one token and no explicit selection
HARDWARE_SLOT_EMPTY             no key in the selected slot
HARDWARE_ALGORITHM_UNSUPPORTED  wrong key type or curve (RSA, P-384, ...)
HARDWARE_IDENTITY_MISMATCH      slot key does not match the expected HUMAN_ID
HARDWARE_POLICY_WEAK            policy below the reference profile
HARDWARE_POLICY_UNKNOWN         policy not readable
HARDWARE_PIN_REQUIRED           PIN needed but no interactive source exists
HARDWARE_PIN_INVALID            PIN verification failed (with remaining attempts)
HARDWARE_PIN_BLOCKED            PIN blocked by the device
HARDWARE_TOUCH_REQUIRED         device demanded touch
HARDWARE_TOUCH_TIMEOUT          touch not registered in time
HARDWARE_OPERATION_CANCELLED    operation cancelled at the device
HARDWARE_OPERATION_FAILED       any other normalized backend failure
```

## 5. Read-only discovery

`inspect_devices(backend)` lists PIV-capable devices and reads slot metadata:
slot, key type, public HUMAN_ID when derivable, PIN/touch policy, origin when
available, and the hardened-policy classification. It may read device serial
and firmware as local operator disambiguation. It never asks for a PIN, never
requests touch, never performs ECDH, never authenticates with a management key
and never writes.

When more than one device is attached, discovery never picks one silently: the
operator selects. Likewise a slot is never chosen merely because it is the
first compatible one; discovery recommends, selection is explicit.

## 6. Operator tool

```
python -m saimail.hardware_piv inspect [--device NAME] [--slot SLOT ...]
python -m saimail.hardware_piv verify  --device NAME --slot SLOT
                                       [--expected-human-id ID]
```

`inspect` is strictly read-only. `verify` is allowed one private-key operation
and remains non-destructive: it opens the selected existing slot, reads the
public identity, requests a PIN interactively only if the slot needs one,
executes exactly one P-256 ECDH operation against a fresh software ephemeral
key, compares the hardware shared secret with the software counterpart, and
closes the session. It never provisions, generates, imports, deletes, resets or
changes policy. Both commands require explicit device and slot selection for
`verify`; there is no `--auto-write`, no `--best-slot`, no hidden fallback, and
no `--pin` option — the PIN is only ever typed at an interactive prompt, never
in shell history.

Without hardware or without the optional extra the manual gate reports
`NOT_RUN_NO_HARDWARE` or the named refusal; it is never reported as `PASS` and
never as `FAIL`. Verification output states the classification honestly and
never describes a weak or unknown policy as hardened, and never describes a
touch as human identity proof.

## 7. Optional dependency

Hardware support is an optional extra:

```
pip install -e ".[hardware-yubikey]"
```

The core install (`pip install -e ".[test]"`) and the canonical suite work
without YubiKey libraries and without hardware. The production backend is the
only module that imports the vendor stack, lazily; nothing is installed at
runtime, third-party code is not vendored, and no supported library operation
is replaced by a CLI subprocess.

## 8. Future provisioning gate (plan only, never executed here)

Creating a SAILETTER credential is a separate explicit operator gate; nothing
in this module can perform it. The planned outline, for that gate only:

* **device**: operator-selected, exactly one, never chosen silently;
* **slot**: an empty slot only — 9D preferred, otherwise an explicitly chosen
  retired slot from 82..95 — with the slot ownership recorded locally first;
* **key**: `ECCP256`, **generated on the device** (never imported), so no
  private key ever exists outside the token;
* **policies**: `PIN_POLICY = ONCE` (or `ALWAYS`), `TOUCH_POLICY = ALWAYS`;
* **identity**: capture the public HUMAN_ID from the generated key and record
  it as the slot's intended SAILETTER identity before sealing anything to it;
* **attestation**: optional, read-only check that the key was device-generated
  when the firmware supports it; never mandatory;
* **recovery implication**: with a single token, `RECOVERABLE` requires a
  second, cryptographically distinct recovery identity; otherwise the explicit
  choice is `STRICT` with its loss warning (D-042);
* **rollback / ownership record**: device serial, slot, key type and policies
  recorded in local operator state, so the credential can be retired
  deliberately rather than discovered later.

## 9. Non-goals

Not implemented and not implied: PIV key generation, import, deletion or
certificate provisioning; PIN/PUK/management-key change or reset; PIV reset;
retry-counter or slot-policy changes; FIDO2 registration, WebAuthn, or
FIDO2-backed decryption; automatic slot selection for writes; contextual
reveal; automatic letter opening; background token polling; a GUI or tray
integration; and any change to HLET1 or HENV1 bytes, domains or bindings.
Private prose remains inert data.
