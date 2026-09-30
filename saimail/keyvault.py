"""Password-wrapped identity keys and independent encrypted recovery backups.

The master password wraps existing Ed25519/X25519 identity material; it never
changes the mail encryption format or fingerprints. A recovery backup uses its
own random recovery key, so a forgotten password need not destroy the identity.
Secrets are returned only to an explicit interactive caller, never logged.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from sailang import SailangError

CUSTODY_MASTER_KEY = "master-key"
IDENTITY_SCHEMA = "SAIMAIL_IDENTITY_3"
VAULT_SCHEMA = "SAIMAIL_KEY_VAULT_1"
BACKUP_SCHEMA = "SAIMAIL_RECOVERY_BACKUP_1"
MASTER_KEY_REQUIRED = "MASTER_KEY_REQUIRED"
MASTER_KEY_INVALID = "MASTER_KEY_INVALID"
MASTER_KEY_WEAK = "MASTER_KEY_WEAK"
VAULT_INVALID = "VAULT_INVALID"
BACKUP_CONFLICT = "BACKUP_CONFLICT"
SCRYPT_N = 2 ** 17
_IDENTITY_FIELDS = {"schema", "version", "seat", "created", "custody", "vault"}
_VAULT_FIELDS = {"schema", "kdf", "salt", "nonce", "ciphertext"}
_KDF = {"name": "scrypt", "n": SCRYPT_N, "r": 8, "p": 1, "length": 32}


def _reject(code, detail):
    raise SailangError(code, detail)


def _password(value, *, creating=False):
    if value is None:
        _reject(MASTER_KEY_REQUIRED, "unlock this mailbox with its master password")
    if not isinstance(value, str):
        _reject(MASTER_KEY_INVALID, "password must be text")
    try:
        raw = value.encode("utf-8")
    except UnicodeError:
        _reject(MASTER_KEY_INVALID, "password is not valid Unicode")
    if len(raw) > 1024 or (creating and (len(value) < 16 or not value.strip())):
        _reject(MASTER_KEY_WEAK, "use at least 16 characters, preferably 5 or more random words")
    return raw


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hex(value, length):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length * 2) + r"}", value)


def validate(identity, marker):
    if (not isinstance(identity, dict) or set(identity) != _IDENTITY_FIELDS
            or identity["schema"] != IDENTITY_SCHEMA or identity["version"] != 3
            or identity["custody"] != CUSTODY_MASTER_KEY
            or identity["seat"] != marker["seat"] or identity["created"] != marker["created"]):
        _reject(VAULT_INVALID, "encrypted identity has an invalid public binding")
    vault = identity["vault"]
    if (not isinstance(vault, dict) or set(vault) != _VAULT_FIELDS or vault["schema"] != VAULT_SCHEMA
            or vault["kdf"] != _KDF or not _hex(vault["salt"], 16) or not _hex(vault["nonce"], 12)
            or not isinstance(vault["ciphertext"], str)
            or not re.fullmatch(r"[0-9a-f]{32,2048}", vault["ciphertext"])
            or len(vault["ciphertext"]) % 2):
        _reject(VAULT_INVALID, "vault parameters are invalid; no unbounded KDF is permitted")
    return identity


def _derive(password, salt):
    return Scrypt(salt=salt, length=32, n=SCRYPT_N, r=8, p=1).derive(_password(password))


def wrap(marker, sender_hex, recipient_hex, password):
    _password(password, creating=True)
    salt, nonce = os.urandom(16), os.urandom(12)
    data = _canonical({"sender": sender_hex, "recipient": recipient_hex})
    ciphertext = AESGCM(_derive(password, salt)).encrypt(
        nonce, data, b"SAIMAIL identity vault v1\x00" + _canonical(marker))
    return {"schema": IDENTITY_SCHEMA, "version": 3, "seat": marker["seat"],
            "created": marker["created"], "custody": CUSTODY_MASTER_KEY,
            "vault": {"schema": VAULT_SCHEMA, "kdf": dict(_KDF), "salt": salt.hex(),
                      "nonce": nonce.hex(), "ciphertext": ciphertext.hex()}}


def unwrap(identity, marker, password):
    validate(identity, marker)
    _password(password)
    vault = identity["vault"]
    try:
        data = AESGCM(_derive(password, bytes.fromhex(vault["salt"]))).decrypt(
            bytes.fromhex(vault["nonce"]), bytes.fromhex(vault["ciphertext"]),
            b"SAIMAIL identity vault v1\x00" + _canonical(marker))
    except InvalidTag:
        _reject(MASTER_KEY_INVALID, "password is wrong or the encrypted identity was altered")
    try:
        keys = json.loads(data)
    except (ValueError, UnicodeError):
        _reject(VAULT_INVALID, "decrypted key data is invalid")
    if (not isinstance(keys, dict) or set(keys) != {"sender", "recipient"}
            or not _hex(keys["sender"], 32) or not _hex(keys["recipient"], 32)):
        _reject(VAULT_INVALID, "decrypted identity contains invalid keys")
    return keys["sender"], keys["recipient"]


def _material(workspace):
    from saimail import workspace as ws

    marker, _, _ = ws._read_durable_identity(workspace.root)
    projection = ws._public_projection(workspace.seat, workspace.created,
                                       workspace.sender_private_key.public_key(),
                                       workspace.recipient_private_key.public_key())
    if ws._marker_payload(projection) != marker:
        _reject(VAULT_INVALID, "loaded keys no longer belong to this mailbox; reload before changing custody")
    sender = workspace.sender_private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    recipient = workspace.recipient_private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    return marker, sender, recipient


def protect(workspace, password):
    """Explicit rewrap; one atomic identity replacement, fingerprints unchanged."""
    from saimail import workspace as ws

    marker, sender, recipient = _material(workspace)
    identity = wrap(marker, sender, recipient, password)
    # Authenticate the new vault before replacing the old one.
    unwrap(identity, marker, password)
    ws._atomic_write_bytes(workspace.root / ws.IDENTITY_DIR / ws.IDENTITY_NAME, _canonical(identity))
    return ws.command_result("vault-protect", "MASTER_KEY_PROTECTED", workspace=workspace,
                             detail="identity protected with a master password; create a recovery backup")


def recovery_backup(workspace, dest):
    """Independent recovery key, displayed once; only encrypted bytes go to disk."""

    target = Path(dest)
    if target.exists():
        _reject(BACKUP_CONFLICT, "backup destination already exists; choose a new file")
    if target.resolve().is_relative_to(workspace.root.resolve()):
        _reject(BACKUP_CONFLICT, "save the recovery backup outside the mailbox")
    marker, sender, recipient = _material(workspace)
    key = base64.b32encode(secrets.token_bytes(25)).decode("ascii")
    identity = wrap(marker, sender, recipient, key)
    payload = {"schema": BACKUP_SCHEMA, "version": 1, "marker": marker, "identity": identity}
    # Exclusive create prevents racing exports from overwriting a recovery file.
    with target.open("xb") as stream:
        stream.write(_canonical(payload))
        stream.flush()
        os.fsync(stream.fileno())
    return {"schema": BACKUP_SCHEMA, "path": str(target), "recovery_key": key,
            "recipient_kid": marker["recipient_kid"],
            "scope": "IDENTITY_ONLY", "mail_backup_required": True}


def restore(backup, root, recovery_key, new_password):
    """Recover the same identity into an empty mailbox; never overwrite one."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

    from saimail import workspace as ws

    _password(new_password, creating=True)
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        _reject(BACKUP_CONFLICT, "restore requires an empty folder; existing mailboxes are not overwritten")
    try:
        with Path(backup).open("rb") as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            _reject(VAULT_INVALID, "backup exceeds its byte budget")
        payload = json.loads(raw)
    except (OSError, ValueError, UnicodeError):
        _reject(VAULT_INVALID, "recovery backup is unreadable or malformed")
    if (not isinstance(payload, dict) or set(payload) != {"schema", "version", "marker", "identity"}
            or payload["schema"] != BACKUP_SCHEMA or payload["version"] != 1):
        _reject(VAULT_INVALID, "unknown recovery backup format")
    marker = ws._validate_marker(payload["marker"], root=root)
    sender, recipient = unwrap(payload["identity"], marker, recovery_key)
    projection = ws._public_projection(marker["seat"], marker["created"],
                                       Ed25519PrivateKey.from_private_bytes(bytes.fromhex(sender)).public_key(),
                                       X25519PrivateKey.from_private_bytes(bytes.fromhex(recipient)).public_key())
    if ws._marker_payload(projection) != marker:
        _reject(VAULT_INVALID, "recovery keys differ from the original public identity")
    identity = wrap(marker, sender, recipient, new_password)
    root.mkdir(parents=True, exist_ok=True)
    (root / ws.IDENTITY_DIR).mkdir(exist_ok=True)
    (root / ws.OUTBOX_DIR).mkdir(exist_ok=True)
    ws._atomic_write_bytes(root / ws.IDENTITY_DIR / ws.IDENTITY_NAME, _canonical(identity))
    ws._write_peers(root, {})
    ws._atomic_write_bytes(root / ws.MARKER_NAME, _canonical(marker))
    return ws.command_result("vault-restore", "IDENTITY_RESTORED", detail=(
        "original identity restored; copy your separately backed-up sealed mail and re-register contacts"),
                             recipient_kid=marker["recipient_kid"], workspace_root=str(root))


__all__ = ["BACKUP_SCHEMA", "CUSTODY_MASTER_KEY", "MASTER_KEY_INVALID", "MASTER_KEY_REQUIRED",
           "protect", "recovery_backup", "restore"]
