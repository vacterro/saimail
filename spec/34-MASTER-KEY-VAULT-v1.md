# Human mailbox master-key vault v1

Decision [D-066](DECISIONS-D066.md). Master-key custody adds encrypted software
identity storage; it does not change Ed25519/X25519 identities or sealed mail.
The GUI extra includes Qt and cryptography. Core dependency-free installs retain
their existing lazy crypto boundary.

`SAIMAIL_IDENTITY_3`, version 3, custody `master-key`: exact fields schema,
version, seat, created, custody, vault. `SAIMAIL_KEY_VAULT_1`: schema, kdf, salt,
nonce, ciphertext. scrypt N=131072, r=8, p=1 derives 32 bytes with a fresh 16-byte
salt; AES-256-GCM wraps both private keys with a fresh 12-byte nonce and associated
data consisting of a domain separator plus the canonical public mailbox marker.
Parameters and lengths are validated before derivation; arbitrary file-provided
KDF cost is not permitted. Wrong password or tampering fails authentication.
New passwords require at least 16 characters and at most 1024 UTF-8 bytes. Length
checks are not entropy estimates: recommend independent random words.

Create writes encrypted identity directly. Protect validates loaded private keys
against the current public marker, wraps and authenticates the new vault before
one atomic replacement. Identity fingerprints stay unchanged. Headers and delivery
do not derive a password or fetch private keys. Python references are discarded
on Lock/close, with no promise of forensic RAM erasure or defence against a
compromised unlocked OS session. Passwords are not passed through CLI arguments,
environment variables, logs, telemetry or background prompt requests.

Recovery format `SAIMAIL_RECOVERY_BACKUP_1` contains version 1, the public marker
and the independently wrapped identity. Its random 200-bit base32 recovery key
is returned only to the explicit operator action; it is not stored in that file.
Backup uses exclusive creation outside the mailbox and flush/fsync. It contains
identity keys only; sealed mail and metadata require their own folder backup.
Restore bounds input to 16 KiB, authenticates the same public identity, requires
an empty destination and wraps recovered keys with a new master password. Wrong
recovery credentials create no mailbox. Already-created backups remain capable
of restoring the identity after a password change; password changes do not revoke
independently held key material. This is stated in the operator guide.

FIDO2 authentication alone is not a decryptor. A possible future native unlock
must use authenticator PRF/hmac-secret plus domain-separated key derivation to
wrap the same identity, tested hardware and an independent recovery path. No
FIDO unlock or untested hardware security claim is shipped here. See Yubico's
[PRF developer guide](https://developers.yubico.com/WebAuthn/Concepts/PRF_Extension/Developers_Guide_to_PRF.html).
The primitives follow cryptography's
[scrypt interface](https://cryptography.io/en/3.4/hazmat/primitives/key-derivation-functions.html#scrypt)
and [AESGCM interface](https://cryptography.io/en/3.4/hazmat/primitives/aead.html#cryptography.hazmat.primitives.ciphers.aead.AESGCM).

Verification: `tests/test_keyvault.py` covers sealed old mail after backup restore,
wrong credentials, unchanged fingerprints, stale loaded identity refusal,
tampered/bounded KDF, independent recovery and locked keyless awareness. Qt tests
cover explicit asynchronous key jobs, competing-action blocking and clearing
plaintext displays. UI screenshots are actual Qt output at the canonical size.
