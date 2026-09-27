"""SAIMAIL persistent local workspace and real local send/receive (V2-01).

Defect class this module eliminates: the proven local protocol path had no
persistent, operator-owned place to live. FG-05 composed the protocol inside one
process on throwaway temporary roots and FG-06 shipped an installable
entrypoint that still wrote only to a temporary demo root, so a real operator
could not initialize a workspace, keep one identity, address one known local
recipient, send a real message, list it, open it explicitly and find the same
durable state after the process exited.

The workspace is deliberately a thin durable shell around the already-proven
public APIs: keys are ordinary software Ed25519/X25519 keys, delivery goes
through ``saimail.envelope`` and ``saimail.postoffice``, listing reads the
canonical header-only index, and opening is the one existing explicit
Post Office transition. Nothing here re-implements a protocol gate, adds a
second dedup layer, encrypts anything new or reaches the network.

Durable layout under the workspace root (all metadata files are canonical JSON
written with a temp-file + atomic replace; an interrupted write leaves the
previous complete file, never a partial one):

    saimail-workspace.json   public marker: schema, version, seat, fingerprints
    identity/identity.json   identity in one of two custody modes:
                             v1 (raw)     software private keys in the file
                             v2 (os-store) public material + vault handles,
                                          private bytes in the OS credential
                                          store (V3-01; spec/20)
    peers.json               explicit alias -> public identity + recipient root
    outbox/<envelope_id>.senv  sealed container copies kept for exact replay
    mail/...                 the Post Office's own durable state

Custody is storage policy, not protocol: both modes carry the same public
identity, the same envelope and the same Post Office semantics. A raw workspace
keeps its raw layout until an explicit ``migrate_workspace_custody`` call; an
``os-store`` workspace fails closed when its store entry is missing or wrong and
never regenerates, falls back to raw bytes or reads an environment variable.

Local delivery boundary: the sender opens the recipient workspace root
supplied explicitly at ``recipient add`` time and delivers through that
workspace's own Post Office. This is a shared local filesystem path, not a
network service; the sender needs write access to the recipient root and that
limitation is stated, never hidden.

V4-01 adds one-hop correspondence continuation (``reply_message``): an
already-explicitly-opened message is continued by an ordinary canonical reply
record sealed through the unchanged path with the existing SENV2 ``REF`` field
set to the original ``ENVELOPE_ID``. It adds no wire field, no thread store and
no automatic correspondence, and it never infers a SAILANG ``SUPPORTS`` /
``REFUTES`` / ``CON`` semantic relation from correspondence (spec/24).
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey,
    X25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)

from sailang import Record, SailangError
from sailang import parse as parse_record
from saimail import custody as _custody
from saimail import envelope, inbox_query, postoffice

WORKSPACE_SCHEMA = "SAIMAIL_LOCAL_WORKSPACE_1"
WORKSPACE_VERSION = 1
IDENTITY_SCHEMA = "SAIMAIL_LOCAL_IDENTITY_1"
IDENTITY_SCHEMA_V2 = "SAIMAIL_LOCAL_IDENTITY_2"
IDENTITY_VERSION_V2 = 2
PEERS_SCHEMA = "SAIMAIL_WORKSPACE_PEERS_1"
CARD_SCHEMA = "SAIMAIL_IDENTITY_CARD_1"
CARD_VERSION = 1
COMMAND_SCHEMA = "LOCAL_WORKSPACE_COMMAND_1"
COMMAND_VERSION = 1

#: One completed explicit custody migration. Repeats are the named no-op
#: ``_custody.CUSTODY_ALREADY_PROTECTED``, never a second rewrite.
CUSTODY_MIGRATED = "CUSTODY_MIGRATED"

MARKER_NAME = "saimail-workspace.json"
IDENTITY_DIR = "identity"
IDENTITY_NAME = "identity.json"
PEERS_NAME = "peers.json"
OUTBOX_DIR = "outbox"

SEAT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HEX32_RE = re.compile(r"^[0-9a-f]{64}$")
_KID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

#: The one convenience wrapper for operator text. Deterministic and honest:
#: free text is a claim with evidence explicitly absent, so the uncertainty
#: rung is capped at U1 and no evidence semantics are invented for it.
WRAPPER_KIND = "F"
WRAPPER_TYPE = "OBS"
WRAPPER_EV = "0"
WRAPPER_STATUS = "U1"
DEFAULT_SUBJECT = "local-message"
DEFAULT_TOPIC = "local-message"
DEFAULT_KIND = "PERSONAL_MESSAGE"

#: V4-01: a reply is `PERSONAL_MESSAGE` by default and never inherits the
#: original transport kind (a reply to a WARNING is not automatically another
#: WARNING). The topic is inherited from the original envelope unless supplied.
DEFAULT_REPLY_KIND = "PERSONAL_MESSAGE"

#: Named outcomes. Transport statuses (ACCEPTED/DUPLICATE/QUARANTINED/REFUSED)
#: and Post Office codes (UNKNOWN_ENVELOPE, ALREADY_READ, ALREADY_EXPIRED, ...)
#: stay canonical: this module never relabels a protocol verdict.
CREATED = "CREATED"
ALREADY_EXISTS = "ALREADY_EXISTS"
INVALID_WORKSPACE = "INVALID_WORKSPACE"
WORKSPACE_MISSING = "WORKSPACE_MISSING"
WORKSPACE_CONFLICT = "WORKSPACE_CONFLICT"
BAD_SEAT = "BAD_SEAT"
IDENTITY_CARD_EXPORTED = "IDENTITY_CARD_EXPORTED"
CARD_CONFLICT = "CARD_CONFLICT"
RECIPIENT_ADDED = "RECIPIENT_ADDED"
RECIPIENT_ALREADY_REGISTERED = "RECIPIENT_ALREADY_REGISTERED"
RECIPIENT_CONFLICT = "RECIPIENT_CONFLICT"
RECIPIENT_MALFORMED = "RECIPIENT_MALFORMED"
RECIPIENT_UNKNOWN = "RECIPIENT_UNKNOWN"
RECIPIENT_IDENTITY_MISMATCH = "RECIPIENT_IDENTITY_MISMATCH"
DELIVERY_TARGET_UNAVAILABLE = "DELIVERY_TARGET_UNAVAILABLE"
OUTBOX_MISSING = "OUTBOX_MISSING"
OUTBOX_CONFLICT = "OUTBOX_CONFLICT"
BAD_INPUT = "BAD_INPUT"

#: V4-01 reply refusals. A reply is correspondence, not a second decryption
#: path: the target must already be READ, and the reply recipient is the
#: original sender resolved through the explicit peer registry, never chosen by
#: the caller.
REPLY_TARGET_UNKNOWN = "REPLY_TARGET_UNKNOWN"
REPLY_TARGET_UNREAD = "REPLY_TARGET_UNREAD"
REPLY_TARGET_EXPIRED = "REPLY_TARGET_EXPIRED"
REPLY_RECIPIENT_UNKNOWN = "REPLY_RECIPIENT_UNKNOWN"
REPLY_RECIPIENT_MISMATCH = "REPLY_RECIPIENT_MISMATCH"
REOPEN_NOT_READ = postoffice.REOPEN_NOT_READ

#: The first-run custody notice (D-054, D2). One stable machine-readable notice
#: plus one bounded human rendering; attached only to the result that CREATED a
#: new workspace, never to ALREADY_EXISTS and never to any later command.
NOTICE_SCHEMA = "SAIMAIL_CUSTODY_NOTICE_1"
NOTICE_VERSION = 1
NOTICE_RAW_CUSTODY_DEFAULT = "RAW_CUSTODY_DEFAULT"
NOTICE_OS_STORE_CUSTODY = "OS_STORE_CUSTODY"

RAW_CUSTODY_NOTICE_TEXT = (
    "raw custody is the default: this workspace stores its private Ed25519 "
    "signing and X25519 decryption identity keys in identity/identity.json, so "
    "copying the workspace directory copies the identity. "
    "`saimail-local init --custody os-store` keeps the private keys in the OS "
    "credential store where a checked backend is available; a requested "
    "protected custody never silently falls back to raw. os-store protects "
    "against workspace-directory-copy exposure only, not against malware "
    "running as the same OS user or against admin/kernel compromise."
)
OS_STORE_NOTICE_TEXT = (
    "os-store custody: this workspace stores handles and public material only; "
    "the private identity keys live in the OS credential store under "
    "credential://saimail-workspace/... . This protects against "
    "workspace-directory-copy exposure; it does not protect against malware "
    "running as the same OS user or against admin/kernel compromise, and it "
    "provides no hardware custody, key rotation or automatic recovery."
)

#: Outcomes whose next step is a HUMAN decision, never an automatic retry.
OPERATOR_ACTION_CODES = frozenset({
    WORKSPACE_MISSING, INVALID_WORKSPACE, WORKSPACE_CONFLICT, BAD_SEAT,
    CARD_CONFLICT, RECIPIENT_CONFLICT, RECIPIENT_MALFORMED, RECIPIENT_UNKNOWN,
    RECIPIENT_IDENTITY_MISMATCH, DELIVERY_TARGET_UNAVAILABLE, OUTBOX_MISSING,
    OUTBOX_CONFLICT, BAD_INPUT, REPLY_TARGET_UNKNOWN, REPLY_TARGET_UNREAD,
    REPLY_TARGET_EXPIRED, REPLY_RECIPIENT_UNKNOWN, REPLY_RECIPIENT_MISMATCH,
}) | _custody.CUSTODY_CODES


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Temp file in the same directory, fsync, atomic replace (never partial)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _canonical_json_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")


def _read_json(path: Path, *, code: str, what: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        _reject(code, f"{what} is missing at {path}")
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _reject(code, f"{what} is unreadable: {exc}")
    if not isinstance(payload, dict):
        _reject(code, f"{what} is not one JSON object")
    return payload


def _check_seat(name: str, value) -> str:
    if not isinstance(value, str) or not SEAT_RE.match(value):
        _reject(BAD_SEAT, f"{name} is one token of letters, digits, dot, dash or underscore")
    return value


def _check_utc(name: str, value) -> str:
    if not isinstance(value, str) or not _UTC_RE.match(value):
        _reject(INVALID_WORKSPACE, f"{name} must be YYYY-MM-DDTHH:MM:SSZ")
    return value


def _public_projection(seat: str, created: str, sender_public: Ed25519PublicKey,
                       recipient_public: X25519PublicKey) -> dict:
    return {
        "seat": seat,
        "created": created,
        "sender_public_key": sender_public.public_bytes(Encoding.Raw, PublicFormat.Raw).hex(),
        "recipient_public_key": recipient_public.public_bytes(
            Encoding.Raw, PublicFormat.Raw).hex(),
        "sender_kid": envelope.fingerprint(sender_public),
        "recipient_kid": envelope.fingerprint(recipient_public),
    }


def _marker_payload(projection: dict) -> dict:
    return {"schema": WORKSPACE_SCHEMA, "version": WORKSPACE_VERSION, **projection}


def _validate_marker(payload: dict, *, root: Path) -> dict:
    expected = {"schema", "version", "seat", "created", "sender_public_key",
                "recipient_public_key", "sender_kid", "recipient_kid"}
    if set(payload) != expected:
        _reject(INVALID_WORKSPACE, "workspace marker has an unexpected field set")
    if payload.get("schema") != WORKSPACE_SCHEMA or payload.get("version") != WORKSPACE_VERSION:
        _reject(INVALID_WORKSPACE,
                f"workspace marker declares {payload.get('schema')!r} "
                f"v{payload.get('version')!r}; this build reads {WORKSPACE_SCHEMA} "
                f"v{WORKSPACE_VERSION}")
    _check_seat("seat", payload.get("seat"))
    _check_utc("created", payload.get("created"))
    for field in ("sender_public_key", "recipient_public_key"):
        if not isinstance(payload.get(field), str) or not _HEX32_RE.match(payload[field]):
            _reject(INVALID_WORKSPACE, f"marker {field} is not 32 raw bytes of lowercase hex")
    for field in ("sender_kid", "recipient_kid"):
        if not isinstance(payload.get(field), str) or not _KID_RE.match(payload[field]):
            _reject(INVALID_WORKSPACE, f"marker {field} is not sha256:<64 lowercase hex>")
    sender_public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload["sender_public_key"]))
    recipient_public = X25519PublicKey.from_public_bytes(
        bytes.fromhex(payload["recipient_public_key"]))
    derived = _public_projection(payload["seat"], payload["created"], sender_public,
                                 recipient_public)
    if (derived["sender_kid"] != payload["sender_kid"]
            or derived["recipient_kid"] != payload["recipient_kid"]):
        _reject(INVALID_WORKSPACE, "marker fingerprints do not match its own public keys")
    return payload


def _identity_v2_payload(projection: dict, sender_handle: str, recipient_handle: str) -> dict:
    """The protected durable identity: handles and public material, no key bytes."""
    return {
        "schema": IDENTITY_SCHEMA_V2,
        "version": IDENTITY_VERSION_V2,
        "seat": projection["seat"],
        "created": projection["created"],
        "custody": _custody.CUSTODY_OS_STORE,
        "sender_handle": sender_handle,
        "recipient_handle": recipient_handle,
        "sender_public_key": projection["sender_public_key"],
        "recipient_public_key": projection["recipient_public_key"],
        "sender_kid": projection["sender_kid"],
        "recipient_kid": projection["recipient_kid"],
    }


def _validate_identity_v2(identity: dict, *, marker: dict) -> dict:
    expected = {"schema", "version", "seat", "created", "custody",
                "sender_handle", "recipient_handle", "sender_public_key",
                "recipient_public_key", "sender_kid", "recipient_kid"}
    if set(identity) != expected:
        _reject(INVALID_WORKSPACE,
                "protected workspace identity has an unexpected field set")
    if identity.get("custody") != _custody.CUSTODY_OS_STORE:
        _reject(INVALID_WORKSPACE,
                "protected workspace identity declares an unknown custody mode")
    for field in ("sender_public_key", "recipient_public_key"):
        if not isinstance(identity.get(field), str) or not _HEX32_RE.match(identity[field]):
            _reject(INVALID_WORKSPACE,
                    f"protected identity {field} is not 32 raw bytes of lowercase hex")
    if (identity["sender_public_key"] != marker["sender_public_key"]
            or identity["recipient_public_key"] != marker["recipient_public_key"]
            or identity["sender_kid"] != marker["sender_kid"]
            or identity["recipient_kid"] != marker["recipient_kid"]):
        _reject(INVALID_WORKSPACE,
                "protected workspace identity and marker disagree; refusing to serve it")
    if (not _custody.handle_matches(identity["sender_handle"], seat=identity["seat"],
                                   role=_custody.ROLE_SENDER, kid=identity["sender_kid"])
            or not _custody.handle_matches(identity["recipient_handle"],
                                          seat=identity["seat"],
                                          role=_custody.ROLE_RECIPIENT,
                                          kid=identity["recipient_kid"])):
        _reject(INVALID_WORKSPACE,
                "protected workspace identity handles do not name their own keys")
    return identity


def _load_protected_keys(identity: dict, *, store=None):
    """Retrieve both private keys from custody and prove they are this identity.

    Public keys and fingerprints are re-derived from the retrieved private
    material and compared with the durable public identity; a substituted,
    truncated or foreign key stops the load. Nothing is regenerated here, and
    no other source (raw file field, environment) is ever consulted.
    """
    sender_hex = _custody.validate_hex_key(
        _custody.read_key(store, identity["sender_handle"]),
        what="the custody sender key")
    recipient_hex = _custody.validate_hex_key(
        _custody.read_key(store, identity["recipient_handle"]),
        what="the custody recipient key")
    sender_private = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(sender_hex))
    recipient_private = X25519PrivateKey.from_private_bytes(bytes.fromhex(recipient_hex))
    derived = _public_projection(identity["seat"], identity["created"],
                                 sender_private.public_key(),
                                 recipient_private.public_key())
    if (derived["sender_public_key"] != identity["sender_public_key"]
            or derived["recipient_public_key"] != identity["recipient_public_key"]
            or derived["sender_kid"] != identity["sender_kid"]
            or derived["recipient_kid"] != identity["recipient_kid"]):
        _reject(_custody.CUSTODY_KEY_MISMATCH,
                "the private keys in custody do not derive the durable public identity; "
                "refusing to serve a substituted identity")
    return sender_private, recipient_private


def _read_peers(root: Path) -> dict:
    path = Path(root) / PEERS_NAME
    if not path.is_file():
        return {}
    payload = _read_json(path, code=INVALID_WORKSPACE, what="peers file")
    if payload.get("schema") != PEERS_SCHEMA or payload.get("version") != 1:
        _reject(INVALID_WORKSPACE, "peers file declares an unknown schema/version")
    recipients = payload.get("recipients")
    if not isinstance(recipients, dict):
        _reject(INVALID_WORKSPACE, "peers file carries no recipients object")
    for alias, record in recipients.items():
        _validate_peer_record(alias, record, code=INVALID_WORKSPACE)
    return {alias: dict(record) for alias, record in recipients.items()}


def _validate_peer_record(alias, record, *, code: str) -> dict:
    if not isinstance(alias, str) or not SEAT_RE.match(alias):
        _reject(code, f"recipient alias {alias!r} is not one address token")
    expected = {"seat", "created", "sender_public_key", "recipient_public_key",
                "sender_kid", "recipient_kid", "workspace", "added_at"}
    if not isinstance(record, dict) or set(record) != expected:
        _reject(code, f"recipient {alias!r} record has an unexpected field set")
    _check_seat("seat", record["seat"])
    for field in ("sender_public_key", "recipient_public_key"):
        if not isinstance(record[field], str) or not _HEX32_RE.match(record[field]):
            _reject(code, f"recipient {alias!r} {field} is not 32 raw bytes of lowercase hex")
    sender_public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(record["sender_public_key"]))
    recipient_public = X25519PublicKey.from_public_bytes(
        bytes.fromhex(record["recipient_public_key"]))
    if (envelope.fingerprint(sender_public) != record["sender_kid"]
            or envelope.fingerprint(recipient_public) != record["recipient_kid"]):
        _reject(code, f"recipient {alias!r} fingerprints do not match its own public keys")
    if not isinstance(record["workspace"], str) or not record["workspace"]:
        _reject(code, f"recipient {alias!r} carries no recipient workspace path")
    _check_utc("created", record["created"])
    _check_utc("added_at", record["added_at"])
    return record


def _write_peers(root: Path, recipients: dict) -> None:
    payload = {"schema": PEERS_SCHEMA, "version": 1, "recipients": recipients}
    _atomic_write_bytes(Path(root) / PEERS_NAME, _canonical_json_bytes(payload))


def _parse_card(payload: object) -> dict:
    expected = {"schema", "version", "seat", "created", "sender_public_key",
                "recipient_public_key", "sender_kid", "recipient_kid"}
    if not isinstance(payload, dict) or set(payload) != expected:
        _reject(RECIPIENT_MALFORMED, "identity card has an unexpected field set")
    if payload.get("schema") != CARD_SCHEMA or payload.get("version") != CARD_VERSION:
        _reject(RECIPIENT_MALFORMED,
                f"identity card declares {payload.get('schema')!r} v{payload.get('version')!r}; "
                f"this build reads {CARD_SCHEMA} v{CARD_VERSION}")
    _check_seat("seat", payload.get("seat"))
    _check_utc("created", payload.get("created"))
    for field in ("sender_public_key", "recipient_public_key"):
        if not isinstance(payload.get(field), str) or not _HEX32_RE.match(payload[field]):
            _reject(RECIPIENT_MALFORMED, f"identity card {field} is not 32 raw bytes of hex")
    sender_public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(payload["sender_public_key"]))
    recipient_public = X25519PublicKey.from_public_bytes(
        bytes.fromhex(payload["recipient_public_key"]))
    if (envelope.fingerprint(sender_public) != payload["sender_kid"]
            or envelope.fingerprint(recipient_public) != payload["recipient_kid"]):
        _reject(RECIPIENT_MALFORMED,
                "identity card fingerprints do not match its own public keys")
    return payload


@dataclass(frozen=True)
class Workspace:
    """One loaded persistent workspace; durable state is never cached on it."""

    root: Path
    seat: str
    created: str
    sender_private_key: Ed25519PrivateKey
    recipient_private_key: X25519PrivateKey
    sender_kid: str
    recipient_kid: str
    custody: str = _custody.CUSTODY_RAW

    @property
    def peers(self) -> dict:
        """The durable recipient mapping, re-read from disk on every use.

        A workspace object is a view, not a cache: a mapping written by a later
        command must be visible to this object without a restart.
        """
        return _read_peers(self.root)

    @property
    def identity(self) -> dict:
        """Public identity projection. Never carries private key material."""
        return {
            "seat": self.seat,
            "created": self.created,
            "sender_public_key": self.sender_private_key.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw).hex(),
            "recipient_public_key": self.recipient_private_key.public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw).hex(),
            "sender_kid": self.sender_kid,
            "recipient_kid": self.recipient_kid,
        }

    def office(self, *, clock=None) -> postoffice.PostOffice:
        return _post_office(self.root, self.seat, self.recipient_private_key.public_key(),
                            clock=clock)


@dataclass(frozen=True)
class WorkspaceHeaders:
    """A secret-free view of one workspace for header-only reads (T-117).

    Defect class it eliminates: a metadata read that retrieves private keys.
    Listing, querying and the SAIPEN turn-entry read need only public keys, yet
    they used to perform the full load, which in os-store custody pulls both
    private keys out of the OS credential store on every automatic turn entry
    and turns a locked store into a failed count. This view carries no private
    key and no way to obtain one, so it cannot open, reopen, send, reply or
    sign; those operations keep the full ``load_workspace``.
    """

    root: Path
    seat: str
    created: str
    recipient_public_key: X25519PublicKey
    sender_kid: str
    recipient_kid: str
    custody: str

    @property
    def peers(self) -> dict:
        """The durable recipient mapping, re-read from disk on every use."""
        return _read_peers(self.root)

    def office(self, *, clock=None) -> postoffice.PostOffice:
        return _post_office(self.root, self.seat, self.recipient_public_key, clock=clock)


def _post_office(root: Path, seat: str, recipient_public_key: X25519PublicKey, *,
                 clock=None) -> postoffice.PostOffice:
    """The workspace's Post Office, built from public keys only."""
    clock = clock or postoffice.utc_now
    sender_registry = envelope.KeyRegistry({
        record["seat"]: [Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(record["sender_public_key"]))]
        for record in _read_peers(root).values()
    })
    recipient_registry = envelope.RecipientKeyRegistry({seat: [recipient_public_key]})
    return postoffice.PostOffice(
        root, seat=seat, sender_registry=sender_registry,
        recipient_registry=recipient_registry, clock=clock)


def custody_notice(mode: str) -> dict:
    """One stable bounded notice for the custody mode a new workspace was created in.

    Machine-readable and mode-accurate: a raw workspace gets the raw-default
    notice (default storage, workspace copy consequence, the os-store opt-in and
    the exact os-store claim boundary); an os-store workspace gets the protected
    notice and never claims raw storage. The text is fixed, carries no secret and
    no path, and is bounded to one message string.
    """
    if mode == _custody.CUSTODY_RAW:
        notice_id, message = NOTICE_RAW_CUSTODY_DEFAULT, RAW_CUSTODY_NOTICE_TEXT
    elif mode == _custody.CUSTODY_OS_STORE:
        notice_id, message = NOTICE_OS_STORE_CUSTODY, OS_STORE_NOTICE_TEXT
    else:
        _reject(BAD_INPUT, f"unknown custody mode {mode!r}; no notice exists for it")
    return {"schema": NOTICE_SCHEMA, "version": NOTICE_VERSION, "id": notice_id,
            "mode": mode, "message": message}


def _identity_v1_payload(seat: str, created: str, sender_hex: str,
                         recipient_hex: str) -> dict:
    """The legacy V2-01 durable identity: raw private hex in the workspace file."""
    return {
        "schema": IDENTITY_SCHEMA, "version": 1, "seat": seat, "created": created,
        "sender_private_key": sender_hex,
        "recipient_private_key": recipient_hex,
    }


def _raise_with_cleanup(store, written: list, exc: BaseException) -> None:
    """Re-raise one failed attempt after releasing entries this attempt created.

    A store entry that cannot be released is named in the re-raised error beside
    the original failure: residue is reported, never hidden, and never replaced
    by a different error code.
    """
    if written:
        remaining = _custody.release_keys(store, written)
        if remaining:
            code = getattr(exc, "code", _custody.CUSTODY_ACCESS_FAILED)
            detail = getattr(exc, "detail", str(exc))
            raise SailangError(
                code,
                f"{detail}; vault cleanup incomplete for {', '.join(remaining)}") from None
    raise exc


def _provision_protected(identity_payload: dict, entries, store, written: list) -> None:
    """Store both private keys under their handles, then prove the read-back.

    Entries this attempt creates are appended to ``written`` as they go, so a
    failure in the middle (or in the read-back) still names exactly what the
    caller must release. No durable workspace file exists yet, so a store
    failure leaves no half-protected workspace behind.
    """
    _custody.classify_backend(store)
    for handle, value in entries:
        if _custody.write_key(store, handle, value):
            written.append(handle)
    _load_protected_keys(identity_payload, store=store)


def init_workspace(root, *, seat: str, custody: str = _custody.CUSTODY_RAW,
                   store=None, clock=None) -> dict:
    """Create one durable workspace; refuse to overwrite or regenerate anything.

    Outcomes: ``CREATED``, ``ALREADY_EXISTS`` (an already-initialized valid
    workspace, identity untouched -- reopened through its own custody mode),
    ``INVALID_WORKSPACE`` (marker present but unreadable/foreign),
    ``WORKSPACE_CONFLICT`` (a partial initialisation or a non-empty foreign
    directory is never adopted) and ``BAD_INPUT`` for an unknown custody mode.

    ``custody`` is ``raw`` (the default: portable, self-contained, raw private
    key files protected only by file location) or ``os-store`` (protected:
    private keys live in the checked OS credential store and the workspace file
    carries handles only; requires the credentials extra; spec/20).
    """
    clock = clock or postoffice.utc_now
    root = Path(root)
    _check_seat("seat", seat)
    if custody not in _custody.CUSTODY_MODES:
        _reject(BAD_INPUT,
                f"unknown custody mode {custody!r}; expected one of {_custody.CUSTODY_MODES}")
    marker = root / MARKER_NAME
    identity_path = root / IDENTITY_DIR / IDENTITY_NAME
    if marker.is_file():
        existing = _validate_marker(
            _read_json(marker, code=INVALID_WORKSPACE, what="workspace marker"),
            root=root)
        loaded = load_workspace(root, store=store)
        return command_result(
            "init", ALREADY_EXISTS, workspace=loaded,
            detail=f"workspace already initialized for seat {existing['seat']}")
    if identity_path.exists():
        _reject(WORKSPACE_CONFLICT,
                "identity material exists but the workspace marker is absent; refusing to "
                "adopt or regenerate a partial workspace")
    if root.exists() and any(root.iterdir()):
        _reject(WORKSPACE_CONFLICT,
                f"{root} is not empty and carries no workspace marker; refusing to adopt it")
    created = clock()
    sender_private = Ed25519PrivateKey.generate()
    recipient_private = X25519PrivateKey.generate()
    projection = _public_projection(seat, created, sender_private.public_key(),
                                    recipient_private.public_key())
    sender_hex = sender_private.private_bytes(Encoding.Raw, PrivateFormat.Raw,
                                              NoEncryption()).hex()
    recipient_hex = recipient_private.private_bytes(Encoding.Raw, PrivateFormat.Raw,
                                                    NoEncryption()).hex()
    written: list = []
    try:
        if custody == _custody.CUSTODY_OS_STORE:
            identity_payload = _identity_v2_payload(
                projection,
                _custody.handle_for(seat, _custody.ROLE_SENDER, projection["sender_kid"]),
                _custody.handle_for(seat, _custody.ROLE_RECIPIENT,
                                    projection["recipient_kid"]))
            _provision_protected(
                identity_payload,
                [(identity_payload["sender_handle"], sender_hex),
                 (identity_payload["recipient_handle"], recipient_hex)],
                store, written)
        else:
            identity_payload = _identity_v1_payload(seat, created, sender_hex, recipient_hex)
        root.mkdir(parents=True, exist_ok=True)
        (root / IDENTITY_DIR).mkdir(parents=True, exist_ok=True)
        (root / OUTBOX_DIR).mkdir(parents=True, exist_ok=True)
        _atomic_write_bytes(identity_path, _canonical_json_bytes(identity_payload))
        try:
            os.chmod(identity_path, 0o600)
        except OSError:
            pass
        _write_peers(root, {})
        # The marker is the commit point: until it exists the workspace is a
        # detectable partial initialisation, never a usable one.
        _atomic_write_bytes(marker, _canonical_json_bytes(_marker_payload(projection)))
    except BaseException as exc:  # noqa: BLE001 - cleanup, then the failure itself
        _raise_with_cleanup(store, written, exc)
    return command_result("init", CREATED, workspace=load_workspace(root, store=store),
                          notices=[custody_notice(custody)],
                          detail=f"workspace initialized for seat {seat} in {custody} custody")


def load_workspace(root, *, store=None) -> Workspace:
    """Reopen one workspace from durable files only. Fails closed on any mismatch.

    Raw (v1) and os-store (v2) identities both load here; the custody mode is
    read from the durable identity file and is never inferred from the platform,
    defaulted or switched. In os-store mode both private keys are retrieved from
    the custody store and must re-derive the durable public identity.
    """
    root = Path(root)
    marker, identity, mode = _read_durable_identity(root)
    if mode == _custody.CUSTODY_RAW:
        sender_private = Ed25519PrivateKey.from_private_bytes(
            bytes.fromhex(identity["sender_private_key"]))
        recipient_private = X25519PrivateKey.from_private_bytes(
            bytes.fromhex(identity["recipient_private_key"]))
        projection = _public_projection(marker["seat"], marker["created"],
                                        sender_private.public_key(),
                                        recipient_private.public_key())
        if (projection["sender_kid"] != marker["sender_kid"]
                or projection["recipient_kid"] != marker["recipient_kid"]):
            _reject(INVALID_WORKSPACE,
                    "workspace marker does not match the durable private identity; refusing "
                    "to serve a forged or stale workspace")
    else:
        sender_private, recipient_private = _load_protected_keys(identity, store=store)
    # Validate the durable mapping at load time; the property re-reads it on use.
    _read_peers(root)
    return Workspace(root=root, seat=marker["seat"], created=marker["created"],
                     sender_private_key=sender_private,
                     recipient_private_key=recipient_private,
                     sender_kid=marker["sender_kid"],
                     recipient_kid=marker["recipient_kid"], custody=mode)


def load_workspace_headers(root) -> WorkspaceHeaders:
    """Reopen one workspace for header-only reads without touching a secret.

    Every public check of ``load_workspace`` runs unchanged: the marker and its
    self-derived fingerprints, the identity file's field set and its agreement
    with the marker, and in os-store custody the durable public projection and
    handles. No private-key object is built and the credential store is never
    read. Proving that the private identity matches is the full load's job,
    done exactly when a key is needed (open, reopen, send, reply).
    """
    root = Path(root)
    marker, _identity, mode = _read_durable_identity(root)
    _read_peers(root)
    return WorkspaceHeaders(
        root=root, seat=marker["seat"], created=marker["created"],
        recipient_public_key=X25519PublicKey.from_public_bytes(
            bytes.fromhex(marker["recipient_public_key"])),
        sender_kid=marker["sender_kid"], recipient_kid=marker["recipient_kid"],
        custody=mode)


def _read_durable_identity(root: Path) -> tuple[dict, dict, str]:
    """Validate the public marker and the identity file; return them and the custody mode.

    Shared by the full and the header-only load so the two can never disagree
    about which workspace is well formed. Private key bytes (raw custody) are
    checked for shape only; they are not turned into keys here.
    """
    marker_path = root / MARKER_NAME
    if not marker_path.is_file():
        _reject(WORKSPACE_MISSING, f"no workspace marker at {marker_path}")
    marker = _validate_marker(
        _read_json(marker_path, code=INVALID_WORKSPACE, what="workspace marker"), root=root)
    identity_path = root / IDENTITY_DIR / IDENTITY_NAME
    if not identity_path.is_file():
        _reject(INVALID_WORKSPACE, f"workspace identity is missing at {identity_path}")
    identity = _read_json(identity_path, code=INVALID_WORKSPACE, what="workspace identity")
    if identity.get("seat") != marker["seat"] or identity.get("created") != marker["created"]:
        _reject(INVALID_WORKSPACE, "workspace identity and marker disagree")
    if identity.get("schema") == IDENTITY_SCHEMA and identity.get("version") == 1:
        expected = {"schema", "version", "seat", "created", "sender_private_key",
                    "recipient_private_key"}
        if set(identity) != expected:
            _reject(INVALID_WORKSPACE,
                    "workspace identity has an unknown schema or field set")
        for field in ("sender_private_key", "recipient_private_key"):
            if not isinstance(identity.get(field), str) or not _HEX32_RE.match(identity[field]):
                _reject(INVALID_WORKSPACE,
                        f"workspace identity {field} is not 32 raw bytes of hex")
        return marker, identity, _custody.CUSTODY_RAW
    if (identity.get("schema") == IDENTITY_SCHEMA_V2
            and identity.get("version") == IDENTITY_VERSION_V2):
        _validate_identity_v2(identity, marker=marker)
        return marker, identity, _custody.CUSTODY_OS_STORE
    _reject(INVALID_WORKSPACE, "workspace identity has an unknown schema or field set")
    raise AssertionError("unreachable")


def migrate_workspace_custody(root, *, store=None) -> dict:
    """Explicitly move one raw workspace identity into OS-store custody.

    Transaction order (spec/20 section 5): validate the workspace and its raw
    private material, store both keys under their handles, read them back,
    derive the public identity, prove exact fingerprint equality, atomically
    replace the durable identity file, and only then report success. A failure
    at any step releases entries this run created and leaves the raw workspace
    intact; there is no silent migration, re-keying or partial identity.
    """
    root = Path(root)
    loaded = load_workspace(root, store=store)
    if loaded.custody == _custody.CUSTODY_OS_STORE:
        return command_result(
            "custody-migrate", _custody.CUSTODY_ALREADY_PROTECTED, workspace=loaded,
            detail="this workspace identity is already in OS-store custody; nothing changed")
    identity_path = root / IDENTITY_DIR / IDENTITY_NAME
    original_bytes = identity_path.read_bytes()
    marker = _validate_marker(
        _read_json(root / MARKER_NAME, code=INVALID_WORKSPACE, what="workspace marker"),
        root=root)
    sender_hex = loaded.sender_private_key.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    recipient_hex = loaded.recipient_private_key.private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    identity_payload = _identity_v2_payload(
        marker,
        _custody.handle_for(loaded.seat, _custody.ROLE_SENDER, loaded.sender_kid),
        _custody.handle_for(loaded.seat, _custody.ROLE_RECIPIENT, loaded.recipient_kid))
    written: list = []
    try:
        _provision_protected(
            identity_payload,
            [(identity_payload["sender_handle"], sender_hex),
             (identity_payload["recipient_handle"], recipient_hex)],
            store, written)
        _atomic_write_bytes(identity_path, _canonical_json_bytes(identity_payload))
    except BaseException as exc:  # noqa: BLE001 - cleanup, then the failure itself
        _raise_with_cleanup(store, written, exc)
    try:
        migrated = load_workspace(root, store=store)
    except BaseException as exc:  # noqa: BLE001 - roll the durable file back
        _atomic_write_bytes(identity_path, original_bytes)
        _raise_with_cleanup(store, written, exc)
    return command_result(
        "custody-migrate", CUSTODY_MIGRATED, workspace=migrated,
        detail="identity fingerprints unchanged; private keys now require the OS "
               "credential store")


def custody_status(root, *, store=None) -> dict:
    """Read-only custody diagnosis: mode, backend availability, loadability.

    Never mutates the workspace or the store and never raises a backend error:
    an unavailable or unsuitable store is part of what a diagnosis must report.
    """
    root = Path(root)
    marker_path = root / MARKER_NAME
    if not marker_path.is_file():
        _reject(WORKSPACE_MISSING, f"no workspace marker at {marker_path}")
    marker = _validate_marker(
        _read_json(marker_path, code=INVALID_WORKSPACE, what="workspace marker"), root=root)
    identity_path = root / IDENTITY_DIR / IDENTITY_NAME
    identity = _read_json(identity_path, code=INVALID_WORKSPACE, what="workspace identity")
    if identity.get("schema") == IDENTITY_SCHEMA and identity.get("version") == 1:
        mode = _custody.CUSTODY_RAW
        handles = None
    elif (identity.get("schema") == IDENTITY_SCHEMA_V2
            and identity.get("version") == IDENTITY_VERSION_V2):
        _validate_identity_v2(identity, marker=marker)
        mode = _custody.CUSTODY_OS_STORE
        handles = {"sender": identity["sender_handle"],
                   "recipient": identity["recipient_handle"]}
    else:
        _reject(INVALID_WORKSPACE, "workspace identity has an unknown schema or field set")
    backend = None
    backend_state = "NOT_APPLICABLE"
    try:
        backend = _custody.classify_backend(store)
        backend_state = "AVAILABLE"
    except SailangError as exc:
        backend_state = exc.code
    loadable = False
    load_error = None
    keys_present = None
    try:
        load_workspace(root, store=store)
        loadable = True
        keys_present = {"sender": True, "recipient": True}
    except SailangError as exc:
        load_error = exc.code
        if mode == _custody.CUSTODY_OS_STORE and handles:
            keys_present = {role: _custody.key_present(store, handle)
                            for role, handle in handles.items()}
    detail = ("raw custody: private keys are files in this workspace directory; "
              "'saimail-local custody migrate' moves the identity into the OS store"
              if mode == _custody.CUSTODY_RAW else
              "os-store custody: private keys require the OS credential store")
    return command_result(
        "custody-status", "OK",
        seat=marker["seat"], sender_kid=marker["sender_kid"],
        recipient_kid=marker["recipient_kid"],
        custody={"mode": mode, "backend": backend, "backend_state": backend_state,
                 "loadable": loadable, "load_error": load_error,
                 "keys_present": keys_present, "handles": handles},
        detail=detail)


def identity_card(workspace: Workspace) -> dict:
    """The public card another workspace needs; no private key material."""
    return {"schema": CARD_SCHEMA, "version": CARD_VERSION, **workspace.identity}


def export_identity_card(workspace: Workspace, dest=None) -> dict:
    """Return the public identity card and optionally persist it for exchange."""
    card = identity_card(workspace)
    path = None
    if dest is not None:
        path = Path(dest)
        data = _canonical_json_bytes(card)
        if path.is_file():
            if path.read_bytes() != data:
                _reject(CARD_CONFLICT,
                        f"{path} already holds a different identity card; refusing to "
                        "overwrite it")
            _atomic_write_bytes(path, data)
        else:
            _atomic_write_bytes(path, data)
    return command_result("identity", IDENTITY_CARD_EXPORTED, workspace=workspace,
                          card=card, card_path=str(path) if path else None,
                          detail="public identity card only; no private key material")


def add_recipient(workspace: Workspace, alias: str, card: object, peer_workspace,
                  *, clock=None) -> dict:
    """Bind one operator alias to one explicit public identity and delivery root."""
    clock = clock or postoffice.utc_now
    if not isinstance(alias, str) or not SEAT_RE.match(alias):
        _reject(RECIPIENT_MALFORMED, "alias is one token of letters, digits, dot, dash or underscore")
    parsed = _parse_card(card)
    peer_root = Path(peer_workspace)
    peer_marker_path = peer_root / MARKER_NAME
    if not peer_marker_path.is_file():
        _reject(DELIVERY_TARGET_UNAVAILABLE,
                f"recipient workspace marker is missing at {peer_marker_path}")
    peer_marker = _validate_marker(
        _read_json(peer_marker_path, code=DELIVERY_TARGET_UNAVAILABLE,
                   what="recipient workspace marker"), root=peer_root)
    if peer_marker["seat"] != parsed["seat"]:
        _reject(RECIPIENT_IDENTITY_MISMATCH,
                f"the card names seat {parsed['seat']} but the workspace at {peer_root} "
                f"belongs to seat {peer_marker['seat']}")
    if (peer_marker["sender_kid"] != parsed["sender_kid"]
            or peer_marker["recipient_kid"] != parsed["recipient_kid"]):
        _reject(RECIPIENT_IDENTITY_MISMATCH,
                "the card does not describe the workspace it was registered for")
    record = {
        "seat": parsed["seat"], "created": parsed["created"],
        "sender_public_key": parsed["sender_public_key"],
        "recipient_public_key": parsed["recipient_public_key"],
        "sender_kid": parsed["sender_kid"], "recipient_kid": parsed["recipient_kid"],
        "workspace": str(peer_root),
        "added_at": clock(),
    }
    existing = workspace.peers.get(alias)
    if existing is not None:
        same = all(existing[field] == record[field] for field in
                   ("seat", "sender_kid", "recipient_kid", "workspace"))
        if same:
            return command_result("recipient-add", RECIPIENT_ALREADY_REGISTERED,
                                  workspace=workspace, recipient={"alias": alias, **record},
                                  detail="identical recipient mapping already registered")
        _reject(RECIPIENT_CONFLICT,
                f"alias {alias!r} already maps to seat {existing['seat']} "
                f"({existing['recipient_kid']}); no silent overwrite")
    peers = dict(workspace.peers)
    peers[alias] = record
    _write_peers(workspace.root, peers)
    return command_result("recipient-add", RECIPIENT_ADDED, workspace=workspace,
                          recipient={"alias": alias, **record},
                          detail=f"recipient {alias!r} registered for seat {record['seat']}")


def list_recipients(workspace: Workspace) -> dict:
    items = [{"alias": alias, **record} for alias, record in sorted(workspace.peers.items())]
    return command_result("recipient-list", "OK", workspace=workspace, recipients=items,
                          detail=f"{len(items)} recipient(s)")


def _resolve_recipient(workspace: Workspace, alias: str) -> dict:
    record = workspace.peers.get(alias) if isinstance(alias, str) else None
    if record is None:
        _reject(RECIPIENT_UNKNOWN,
                f"no recipient is registered under alias {alias!r}; add it first")
    return _validate_peer_record(alias, record, code=INVALID_WORKSPACE)


def _recipient_office(record: dict, *, clock) -> postoffice.PostOffice:
    peer_root = Path(record["workspace"])
    marker_path = peer_root / MARKER_NAME
    if not marker_path.is_file():
        _reject(DELIVERY_TARGET_UNAVAILABLE,
                f"recipient workspace marker is missing at {marker_path}")
    marker = _validate_marker(
        _read_json(marker_path, code=DELIVERY_TARGET_UNAVAILABLE,
                   what="recipient workspace marker"), root=peer_root)
    if marker["seat"] != record["seat"]:
        _reject(RECIPIENT_IDENTITY_MISMATCH,
                f"recipient workspace at {peer_root} belongs to seat {marker['seat']}, "
                f"not registered seat {record['seat']}")
    if (marker["sender_kid"] != record["sender_kid"]
            or marker["recipient_kid"] != record["recipient_kid"]):
        _reject(RECIPIENT_IDENTITY_MISMATCH,
                "recipient workspace identity no longer matches the registered card")
    peer_peers = _read_peers(peer_root)
    sender_registry = envelope.KeyRegistry({
        item["seat"]: [Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(item["sender_public_key"]))]
        for item in peer_peers.values()
    })
    recipient_registry = envelope.RecipientKeyRegistry({
        marker["seat"]: [X25519PublicKey.from_public_bytes(
            bytes.fromhex(marker["recipient_public_key"]))]})
    return postoffice.PostOffice(
        peer_root, seat=marker["seat"], sender_registry=sender_registry,
        recipient_registry=recipient_registry, clock=clock)


def _wrapper_record(workspace: Workspace, claim: str, subject: str, created: str) -> Record:
    return Record.create(
        KIND=WRAPPER_KIND, SRC="HUMAN:" + workspace.seat, SUBJ=subject, CLAIM=claim,
        TYPE=WRAPPER_TYPE, EV=WRAPPER_EV, STATUS=WRAPPER_STATUS, CREATED=created)


def _outbox_path(workspace: Workspace, envelope_id: str) -> Path:
    # A Windows path segment cannot carry ':' (it is alternate-data-stream
    # syntax), so the outbox file is named by the digest half of the id.
    digest = envelope_id.split(":", 1)[1] if ":" in envelope_id else envelope_id
    return workspace.root / OUTBOX_DIR / (digest + ".senv")


def _store_outbox(workspace: Workspace, envelope_id: str, container: str) -> str:
    path = _outbox_path(workspace, envelope_id)
    data = container.encode("utf-8")
    if path.is_file() and path.read_bytes() != data:
        _reject(OUTBOX_CONFLICT,
                f"outbox already holds different bytes for {envelope_id}")
    _atomic_write_bytes(path, data)
    return str(path)


def _build_content_record(workspace: Workspace, *, claim, record_path,
                          subject: str, created: str) -> Record:
    """Resolve exactly one content form into a canonical record (send/reply).

    ``claim`` is the deterministic operator-text wrapper; ``record_path`` is an
    existing canonical SAILANG record sent as its own canonical bytes. The two
    forms are mutually exclusive and neither grants extra authority.
    """
    if claim is not None:
        if not isinstance(claim, str) or not claim.strip():
            _reject(BAD_INPUT, "claim text is required")
        claim = claim.strip()
        if "\n" in claim or "\r" in claim:
            _reject(BAD_INPUT,
                    "claim text is one line; put multi-line content in a canonical record "
                    "file and send it with record_path")
        return _wrapper_record(workspace, claim, subject, created)
    source = Path(record_path)
    try:
        raw = source.read_bytes()
    except OSError as exc:
        _reject(BAD_INPUT, f"record file is unreadable: {exc}")
    return parse_record(raw)


def _seal_deliver(workspace: Workspace, message: Record, recipient: dict, *,
                  alias: str, kind: str, topic: str, created: str,
                  ref: str = None, clock) -> dict:
    """Seal one canonical record and deliver it through the unchanged path.

    Shared by ``send`` and ``reply``: one canonical record resolution, one
    recipient sealing call through ``saimail.envelope``, one outbox copy and one
    recipient Post Office delivery. ``ref`` is the existing SENV2 ``REF`` header
    field -- absent for an ordinary send and the original ``ENVELOPE_ID`` for a
    reply. Nothing else differs between the two callers.
    """
    office = _recipient_office(recipient, clock=clock)
    container = envelope.seal(
        message.canonical_bytes(), sender_private_key=workspace.sender_private_key,
        sender_seat=workspace.seat, recipient_seat=recipient["seat"],
        recipient_public_key=X25519PublicKey.from_public_bytes(
            bytes.fromhex(recipient["recipient_public_key"])),
        kind=kind, topic=topic, created=created, ref=ref)
    envelope_id = envelope.envelope_id(container)
    _store_outbox(workspace, envelope_id, container)
    delivery = office.deliver(container)
    return {
        "office": office, "delivery": delivery, "envelope_id": envelope_id,
        "origin": {"alias": alias, "seat": recipient["seat"],
                   "workspace": recipient["workspace"]},
        "state": _state_for(office, envelope_id),
    }


def send_message(workspace: Workspace, alias: str, *, claim=None, record_path=None,
                 subject: str = DEFAULT_SUBJECT, topic: str = DEFAULT_TOPIC,
                 kind: str = DEFAULT_KIND, clock=None) -> dict:
    """Seal one typed record and deliver it into the recipient's own Post Office.

    Exactly one content form is accepted: ``claim`` (one line of operator text,
    wrapped deterministically as documented in ``_wrapper_record``) or
    ``record_path`` (an existing canonical SAILANG record file, sent as its own
    canonical bytes). The sealed container is kept in the sender's outbox under
    the transport identity so an exact replay is the SAME delivery. An ordinary
    send carries no SENV2 ``REF``.
    """
    clock = clock or postoffice.utc_now
    if (claim is None) == (record_path is None):
        _reject(BAD_INPUT, "provide exactly one of claim text or a canonical record file")
    record = _resolve_recipient(workspace, alias)
    created = clock()
    message = _build_content_record(workspace, claim=claim, record_path=record_path,
                                    subject=subject, created=created)
    delivered = _seal_deliver(workspace, message, record, alias=alias, kind=kind,
                              topic=topic, created=created, clock=clock)
    delivery = delivered["delivery"]
    return command_result(
        "send", delivery.status, workspace=workspace,
        recipient=delivered["origin"],
        message={
            "envelope_id": delivered["envelope_id"],
            "state": delivered["state"],
            "received_at": delivery.received_at,
            "from": workspace.seat,
            "kind": kind,
            "topic": topic,
            "created": created,
        },
        delivery={"status": delivery.status, "reason": delivery.reason,
                  "quarantine_id": delivery.quarantine_id},
        detail=_send_detail(delivery))


def _state_for(office: postoffice.PostOffice, envelope_id: str) -> str:
    try:
        return office.bundle_state(envelope_id)
    except SailangError:
        return postoffice.NEITHER


def _send_detail(delivery) -> str:
    if delivery.status == postoffice.ACCEPTED:
        return "delivered into the recipient workspace"
    if delivery.status == postoffice.DUPLICATE:
        return "exact re-delivery; the original RECEIVED_AT is preserved"
    if delivery.status == postoffice.QUARANTINED:
        return f"quarantined by the recipient Post Office: {delivery.reason}"
    return f"refused by the recipient Post Office: {delivery.reason}"


def _resolve_reply_target(workspace: Workspace, envelope_id, *, clock) -> dict:
    """Resolve one already-READ target through the canonical index, never payload.

    The target's metadata and durable lifecycle state are read from the
    canonical Post Office index alone: no `.senv` bytes are read and nothing is
    decrypted here. A target that is not already READ fails closed with a named
    refusal, so `reply` never becomes a second payload-decryption path.
    """
    if not isinstance(envelope_id, str) or not _KID_RE.match(envelope_id):
        _reject(BAD_INPUT, "an envelope id is sha256:<64 lowercase hex>")
    office = workspace.office(clock=clock)
    row = office.read_index_row(envelope_id)
    if row is None:
        _reject(REPLY_TARGET_UNKNOWN,
                f"no received envelope {envelope_id} is in this workspace index")
    state = office.bundle_state(envelope_id, row=row)
    if state == postoffice.READ_STATE:
        return row
    if state == postoffice.UNREAD:
        _reject(REPLY_TARGET_UNREAD,
                f"envelope {envelope_id} is UNREAD; open the exact envelope explicitly first")
    if state == postoffice.EXPIRED_STATE:
        _reject(REPLY_TARGET_EXPIRED,
                f"envelope {envelope_id} is expired; an expired message is never resurrected")
    if state == postoffice.NEITHER:
        _reject(postoffice.INDEX_BODY_MISSING,
                f"indexed envelope {envelope_id} has no durable body to continue")
    if state == postoffice.BOTH:
        _reject(postoffice.RECONCILIATION_REQUIRED,
                f"envelope {envelope_id} exists as both an inbox and a read bundle; "
                "maintenance reconciliation must prove identity first")
    if state == postoffice.EXPIRY_RECONCILIATION_REQUIRED:
        _reject(postoffice.EXPIRY_RECONCILIATION_REQUIRED,
                f"envelope {envelope_id} has an expired tombstone and a live bundle; "
                "maintenance reconciliation must prove identity first")
    _reject(REPLY_TARGET_UNKNOWN,
            f"envelope {envelope_id} is not in a replyable state ({state})")


def _resolve_reply_recipient(workspace: Workspace, row: dict) -> tuple:
    """Bind the reply recipient to the original sender identity, never a label.

    A registered peer must match both the original index row `from` seat and its
    `from_kid` sender fingerprint. A seat-only match is refused: the reply is
    never redirected to a different identity merely because a seat label matches.
    """
    seat = row["from"]
    kid = row["from_kid"]
    seat_matches = sorted(
        (alias, record) for alias, record in workspace.peers.items()
        if record["seat"] == seat)
    if not seat_matches:
        _reject(REPLY_RECIPIENT_UNKNOWN,
                f"no registered peer carries seat {seat!r}; register the original sender first")
    key_matches = [(alias, record) for alias, record in seat_matches
                   if record["sender_kid"] == kid]
    if not key_matches:
        _reject(REPLY_RECIPIENT_MISMATCH,
                f"the registered peer for seat {seat!r} carries a different sender key than "
                f"{kid}; refusing to redirect the reply to another identity")
    alias, record = key_matches[0]
    return alias, _validate_peer_record(alias, record, code=INVALID_WORKSPACE)


def reply_message(workspace: Workspace, envelope_id, *, claim=None, record_path=None,
                  subject: str = DEFAULT_SUBJECT, topic=None,
                  kind: str = DEFAULT_REPLY_KIND, clock=None) -> dict:
    """Continue one already-explicitly-opened message (V4-01 correspondence).

    One-hop local correspondence: the target must already be in durable READ
    state; the reply recipient is the original sender resolved through the
    explicit peer registry by both seat and sender-key fingerprint; the reply is
    an ordinary canonical record sealed through the unchanged SENV2 path with
    ``REF`` set to the original ``ENVELOPE_ID``. No SAILANG semantic relation
    (`SUPPORTS` / `REFUTES` / `CON`) is ever inferred from correspondence, and
    the target payload is never read or decrypted again.
    """
    clock = clock or postoffice.utc_now
    if (claim is None) == (record_path is None):
        _reject(BAD_INPUT, "provide exactly one of claim text or a canonical record file")
    row = _resolve_reply_target(workspace, envelope_id, clock=clock)
    alias, recipient = _resolve_reply_recipient(workspace, row)
    created = clock()
    message = _build_content_record(workspace, claim=claim, record_path=record_path,
                                    subject=subject, created=created)
    resolved_topic = row["topic"] if topic is None else topic
    delivered = _seal_deliver(workspace, message, recipient, alias=alias, kind=kind,
                              topic=resolved_topic, created=created, ref=envelope_id,
                              clock=clock)
    delivery = delivered["delivery"]
    return command_result(
        "reply", delivery.status, workspace=workspace,
        target={"envelope_id": envelope_id, "state": postoffice.READ_STATE,
                "from": row["from"], "from_kid": row["from_kid"], "topic": row["topic"]},
        reply={"envelope_id": delivered["envelope_id"], "ref": envelope_id,
               "to": recipient["seat"], "kind": kind, "topic": resolved_topic,
               "created": created, "state": delivered["state"]},
        recipient=delivered["origin"],
        delivery={"status": delivery.status, "reason": delivery.reason,
                  "quarantine_id": delivery.quarantine_id},
        detail=_send_detail(delivery))


def redeliver_message(workspace: Workspace, envelope_id: str, *, clock=None) -> dict:
    """Replay one exact outbox container through the existing delivery gate."""
    clock = clock or postoffice.utc_now
    if not isinstance(envelope_id, str) or not _KID_RE.match(envelope_id):
        _reject(BAD_INPUT, "an envelope id is sha256:<64 lowercase hex>")
    path = _outbox_path(workspace, envelope_id)
    if not path.is_file():
        _reject(OUTBOX_MISSING, f"no outbox copy for {envelope_id} in this workspace")
    container = path.read_text(encoding="utf-8")
    header = envelope.parse_header(container)
    if header.get("FROM") != workspace.seat:
        _reject(RECIPIENT_IDENTITY_MISMATCH,
                "outbox container was not authored by this workspace identity")
    target_seat = header.get("TO")
    alias = None
    record = None
    for candidate, item in workspace.peers.items():
        if item["seat"] == target_seat:
            alias, record = candidate, item
            break
    if record is None:
        _reject(RECIPIENT_UNKNOWN,
                f"no registered recipient carries seat {target_seat!r}")
    office = _recipient_office(record, clock=clock)
    delivery = office.deliver(container)
    return command_result(
        "redeliver", delivery.status, workspace=workspace,
        recipient={"alias": alias, "seat": record["seat"], "workspace": record["workspace"]},
        message={"envelope_id": envelope_id, "received_at": delivery.received_at,
                 "state": _state_for(office, envelope_id)},
        delivery={"status": delivery.status, "reason": delivery.reason,
                  "quarantine_id": delivery.quarantine_id},
        detail=_send_detail(delivery))


def list_inbox(workspace: Workspace | WorkspaceHeaders, *, clock=None) -> dict:
    """Header-only listing: canonical index rows plus durable bundle state."""
    office = workspace.office(clock=clock)
    items = []
    for row in office.read_index():
        state = office.bundle_state(row["envelope_id"], row=row)
        items.append({
            "envelope_id": row["envelope_id"], "from": row["from"], "to": row["to"],
            "kind": row["kind"], "topic": row["topic"], "created": row["created"],
            "received_at": row["received_at"], "state": state, "ref": row.get("ref"),
        })
    items.sort(key=lambda item: (item["received_at"], item["envelope_id"]))
    unread = sum(1 for item in items if item["state"] == postoffice.UNREAD)
    return command_result("inbox", "OK", workspace=workspace, items=items,
                          detail=f"{len(items)} message(s), {unread} unread")


def query_inbox(workspace: Workspace | WorkspaceHeaders, *, sender=None, topic=None,
                kind=None, state=None, ref=None, since=None, before=None,
                scan_budget=None, cursor=None, clock=None) -> dict:
    """Metadata-only bounded triage query over the canonical index (P1).

    Exact filters combined with AND, a declared row-scan budget and a byte-offset
    continuation cursor. It never decrypts, opens, moves, acknowledges or
    promotes anything: finding a message is metadata work, reading it stays the
    explicit `open --envelope` action. A query does not consult `HeaderInterest`,
    attention merging or any selector rule, so a message an old selector
    experiment would have ignored is still findable if its index row matches.
    """
    office = workspace.office(clock=clock)
    query = inbox_query.MetadataQuery(
        sender=sender, topic=topic, kind=kind, state=state, ref=ref,
        since=since, before=before)
    cursor_token = None if cursor is None else postoffice.ScanCursor(offset=cursor)
    result = inbox_query.query_metadata(office, query, cursor=cursor_token,
                                        scan_budget=scan_budget)
    budget = inbox_query.DEFAULT_SCAN_BUDGET if scan_budget is None else scan_budget
    query_view = {"sender": sender, "topic": topic, "kind": kind, "state": state,
                  "ref": ref, "since": since, "before": before,
                  "scan_budget": budget}
    return command_result(
        "inbox-query", "OK", workspace=workspace,
        query=query_view,
        items=[item.as_dict() for item in result.items],
        rows_examined=result.rows_examined,
        match_count=result.match_count,
        exhausted=result.exhausted,
        cursor=result.cursor.offset if result.cursor is not None else None,
        detail=(f"{result.match_count} match(es) of {result.rows_examined} row(s) "
                "examined; metadata only, nothing opened"))


def open_message(workspace: Workspace, envelope_id: str, *, clock=None) -> dict:
    """Explicitly open one exact message through the existing Post Office gate."""
    office = workspace.office(clock=clock)
    session = postoffice.PostOfficeSession(office, scan_budget=0, open_budget=1)
    opened = session.open_message(envelope_id,
                                  recipient_private_key=workspace.recipient_private_key)
    row = office.read_index_row(envelope_id) or {}
    record = parse_record(opened.plaintext)
    return command_result(
        "open", postoffice.READ_STATE, workspace=workspace,
        message={
            "envelope_id": envelope_id, "state": postoffice.READ_STATE,
            "from": row.get("from"), "kind": row.get("kind"), "topic": row.get("topic"),
            "created": row.get("created"), "received_at": row.get("received_at"),
        },
        record={
            "content_id": record.content_id, "kind": record.kind, "claim": record.claim,
            "subject": record.get("SUBJ"), "status": record.status,
            "evidence_state": record.evidence_state,
        },
        detail="opened explicitly; promotion stays a separate action")

def reopen_message(workspace: Workspace, envelope_id: str, *, clock=None) -> dict:
    """Explicitly reopen one already-opened (READ) message through the existing Post Office gate."""
    office = workspace.office(clock=clock)
    session = postoffice.PostOfficeSession(office, scan_budget=0, open_budget=1)
    opened = session.reopen_message(envelope_id,
                                    recipient_private_key=workspace.recipient_private_key)
    row = office.read_index_row(envelope_id) or {}
    record = parse_record(opened.plaintext)
    return command_result(
        "reopen", postoffice.READ_STATE, workspace=workspace,
        message={
            "envelope_id": envelope_id, "state": postoffice.READ_STATE,
            "from": row.get("from"), "kind": row.get("kind"), "topic": row.get("topic"),
            "created": row.get("created"), "received_at": row.get("received_at"),
        },
        record={
            "content_id": record.content_id, "kind": record.kind, "claim": record.claim,
            "subject": record.get("SUBJ"), "status": record.status,
            "evidence_state": record.evidence_state,
        },
        detail="reopened explicitly; durable state stays READ")


def command_result(command: str, status: str, *, workspace: Workspace | None = None,
                   detail: str = "", **fields) -> dict:
    """One bounded machine-readable result. Never carries private key material."""
    result = {
        "schema": COMMAND_SCHEMA,
        "version": COMMAND_VERSION,
        "command": command,
        "status": status,
        "ok": status not in (postoffice.REFUSED, postoffice.QUARANTINED),
        "operator_action_required": status in OPERATOR_ACTION_CODES,
        "detail": detail,
    }
    if workspace is not None:
        result["workspace"] = {"root": str(workspace.root), "seat": workspace.seat}
        result["identity"] = {"sender_kid": workspace.sender_kid,
                              "recipient_kid": workspace.recipient_kid,
                              "custody": workspace.custody}
    result.update(fields)
    return result


def render_command(result: dict) -> str:
    """Bounded human summary; never private keys and never other payloads."""
    lines = [f"SAIMAIL-LOCAL {result.get('command', '?')}: {result.get('status', '?')}"]
    workspace = result.get("workspace") or {}
    if workspace:
        lines.append(f"WORKSPACE:  {workspace.get('root')} (seat {workspace.get('seat')})")
    identity = result.get("identity") or {}
    if identity:
        label = identity.get("sender_kid")
        if identity.get("custody"):
            label = f"{label} [custody {identity['custody']}]"
        lines.append(f"IDENTITY:   {label}")
    custody_block = result.get("custody")
    if isinstance(custody_block, dict) and custody_block.get("mode"):
        lines.append(f"CUSTODY:    {custody_block.get('mode')} "
                     f"(backend {custody_block.get('backend_state')})")
    message = result.get("message") or {}
    if message.get("envelope_id"):
        lines.append(f"MESSAGE:    {message.get('envelope_id')} [{message.get('state')}]")
    target = result.get("target") or {}
    if target.get("envelope_id"):
        lines.append(f"TARGET:     {target.get('envelope_id')} [{target.get('state')}]")
    reply = result.get("reply") or {}
    if reply.get("envelope_id"):
        lines.append(f"REPLY:      {reply.get('envelope_id')} "
                     f"[ref {reply.get('ref')}, {reply.get('state')}]")
    saipen = result.get("saipen") or {}
    if saipen.get("seat"):
        lines.append(f"SAIPEN:     seat {saipen.get('seat')} via {saipen.get('seat_source')} "
                     f"(STATE.agent {saipen.get('state_agent')}; {saipen.get('phase')} "
                     f"{saipen.get('task')}; last E-{saipen.get('last_event')})")
    telegram = result.get("telegram") or {}
    admission = result.get("admission") or {}
    if admission.get("basis") == "LOCAL_SAIPEN_BINDING":
        lines.append("ENTRY:      SAIPEN project + matching workspace seat; local binding only")
    if telegram.get("form"):
        lines.append(f"TELEGRAM:   {telegram.get('kind')} topic {telegram.get('topic')} "
                     f"({telegram.get('form')}"
                     + (f" {telegram.get('event')})" if telegram.get("event") else ")"))
    intent = result.get("intent") or {}
    if intent.get("key_id"):
        lines.append(f"INTENT:     {intent.get('state')} key {intent.get('key')} -> "
                     f"{intent.get('recipient_seat')} topic {intent.get('topic')} "
                     f"(attempts {intent.get('attempts')}"
                     + (f", last error {intent.get('last_error')}" if intent.get("last_error")
                        else "")
                     + (f", failure {intent.get('failure')}" if intent.get("failure") else "")
                     + ")")
        if intent.get("envelope_id"):
            lines.append(f"ENVELOPE:   {intent.get('envelope_id')}")
    notice = result.get("notify") or {}
    if notice.get("key"):
        lines.append(f"NOTIFY:     {notice.get('trigger')} -> {notice.get('to_seat')} "
                     f"({notice.get('kind')}, Work {notice.get('work')})")
    caps = result.get("capabilities") or {}
    if caps.get("schema") == "SAIMAIL_CAPABILITIES_1":
        lines.append(f"CHANNEL:    {caps.get('overall')}"
                     + (f" ({', '.join(caps.get('reasons') or [])})" if caps.get("reasons")
                        else ""))
        seat = caps.get("seat") or {}
        lines.append(f"SEAT:       acting {seat.get('acting')} / mailbox {seat.get('workspace')}")
        for name, entry in sorted((caps.get("capabilities") or {}).items()):
            lines.append(f"CAPABILITY: {name} {entry.get('state')}"
                         + (f" ({entry.get('reason')})" if entry.get("reason") else ""))
        awareness = caps.get("awareness") or {}
        if awareness:
            lines.append(f"AWARENESS:  {awareness.get('unread')} unread header(s), "
                         f"{awareness.get('on_current_topic')} on {awareness.get('current_topic')}"
                         + ("" if awareness.get("complete") else " (page incomplete)"))
    participant = result.get("participant") or {}
    if participant.get("seat"):
        lines.append(f"PARTICIPANT: {participant.get('seat')} in {participant.get('lineage')} "
                     f"via alias {participant.get('alias')} "
                     f"(triggers {', '.join(participant.get('triggers') or [])})")
    for lineage, seats in sorted((result.get("participants") or {}).items()):
        for seat, record in sorted(seats.items()):
            lines.append(f"PARTICIPANT: {seat} in {lineage} via alias {record.get('alias')} "
                         f"(triggers {', '.join(record.get('triggers') or [])})")
    outbox_block = result.get("outbox") or {}
    if outbox_block.get("counts"):
        lines.append(f"OUTBOX:     {outbox_block.get('pending')} pending "
                     f"({outbox_block.get('retrying')} retrying), "
                     f"{outbox_block['counts'].get('FAILED')} failed, "
                     f"{outbox_block['counts'].get('DELIVERED')} delivered; oldest pending "
                     f"{outbox_block.get('oldest_pending_seconds')} s; last error "
                     f"{outbox_block.get('last_error')}")
    if result.get("command") == "outbox-resume":
        counts = result.get("counts") or {}
        lines.append("RESUME:     " + ", ".join(f"{name} {value}"
                                                for name, value in sorted(counts.items())))
    if result.get("command") == "saipen-telegrams":
        for item in result.get("items") or []:
            lines.append(f"UNREAD:     {item.get('envelope_id')} from {item.get('from')} "
                         f"{item.get('kind')} topic {item.get('topic')}")
    brief = result.get("brief") or {}
    if brief.get("schema") == "SAIPEN_WORK_BRIEF_1":
        counts = brief["counts"]
        lines.append(f"WORK TOPIC: {brief['current_topic'] or 'none'} (topic hint only)")
        if saipen.get("blocker"):
            lines.append(f"WORK HOLD:  {saipen['blocker']} (observed STATE value)")
        lines.append(f"PAGE:       {counts['current_topic']} matching work topic, "
                     f"{counts['other_topics']} other; {result['rows_examined']} rows examined")
        lines.append("COVERAGE:   " + (
            "scanned from start to current end" if brief["complete_from_start"]
            else "partial inbox view; counts describe this page only"))
        for relation, label in (("current_topic", "WORK"), ("other_topics", "OTHER")):
            for item in result.get("items") or []:
                if item["work_relation"] == relation:
                    lines.append(f"{label}: {item['envelope_id']} from {item['from']} "
                                 f"{item['kind']} topic {item['topic']}")
        continuation = brief.get("continuation")
        if continuation:
            lines.append(f"RESUME:     --cursor {continuation['cursor']} "
                         f"--context {continuation['context']}")
        lines.append("READ:       choose an envelope and run open --envelope explicitly")
    if str(result.get("command", "")).startswith("saipen-"):
        cited = result.get("record") or {}
        if cited.get("id"):
            lines.append(f"RECORD:     {cited.get('id')}")
            lines.append(f"EVIDENCE:   {cited.get('ev')} ({cited.get('src')})")
    if result.get("detail"):
        lines.append(f"DETAIL:     {result.get('detail')}")
    for notice in result.get("notices") or []:
        if isinstance(notice, dict) and notice.get("message"):
            lines.append(f"NOTICE:     {notice['message']}")
    if result.get("operator_action_required"):
        lines.append("ACTION:     operator attention required")
    return "\n".join(lines)


__all__ = [
    "ALREADY_EXISTS",
    "BAD_INPUT",
    "NOTICE_OS_STORE_CUSTODY",
    "NOTICE_RAW_CUSTODY_DEFAULT",
    "NOTICE_SCHEMA",
    "OS_STORE_NOTICE_TEXT",
    "RAW_CUSTODY_NOTICE_TEXT",
    "CARD_CONFLICT",
    "CARD_SCHEMA",
    "COMMAND_SCHEMA",
    "COMMAND_VERSION",
    "CREATED",
    "CUSTODY_MIGRATED",
    "DEFAULT_KIND",
    "DEFAULT_SUBJECT",
    "DEFAULT_TOPIC",
    "DELIVERY_TARGET_UNAVAILABLE",
    "IDENTITY_CARD_EXPORTED",
    "IDENTITY_SCHEMA",
    "IDENTITY_SCHEMA_V2",
    "IDENTITY_VERSION_V2",
    "INVALID_WORKSPACE",
    "MARKER_NAME",
    "OUTBOX_DIR",
    "OUTBOX_MISSING",
    "PEERS_SCHEMA",
    "RECIPIENT_ADDED",
    "RECIPIENT_ALREADY_REGISTERED",
    "RECIPIENT_CONFLICT",
    "RECIPIENT_IDENTITY_MISMATCH",
    "RECIPIENT_MALFORMED",
    "RECIPIENT_UNKNOWN",
    "REPLY_RECIPIENT_MISMATCH",
    "REPLY_RECIPIENT_UNKNOWN",
    "REPLY_TARGET_EXPIRED",
    "REPLY_TARGET_UNKNOWN",
    "REPLY_TARGET_UNREAD",
    "DEFAULT_REPLY_KIND",
    "WORKSPACE_CONFLICT",
    "WORKSPACE_MISSING",
    "WORKSPACE_SCHEMA",
    "WORKSPACE_VERSION",
    "Workspace",
    "WorkspaceHeaders",
    "add_recipient",
    "command_result",
    "custody_notice",
    "custody_status",
    "export_identity_card",
    "identity_card",
    "init_workspace",
    "list_inbox",
    "list_recipients",
    "load_workspace",
    "load_workspace_headers",
    "migrate_workspace_custody",
    "open_message",
    "query_inbox",
    "redeliver_message",
    "render_command",
    "reply_message",
    "send_message",
]
