"""Trust pins and identity continuity (FUTURE GATE Wave 1).

Defect class this module eliminates: a peer that is trusted because it is
*named*. ``peers.json`` binds an alias to a key fingerprint and
``participants.json`` pins a project admission, but neither registry answers the
only question an operator actually has: is this the same identity I trusted, and
why is it trusted or refused right now. A workspace that re-registers an alias
after a peer rebuilt itself silently substitutes a new key, and a display name
matching is the only continuity evidence that survives.

The registry here is the answer. Every pin names a CANONICAL KEY FINGERPRINT,
never a path and never a display name:

    UNKNOWN            no pin exists for this alias
    OBSERVED           the alias resolves, but nobody accepted this key yet
    TRUSTED            this exact key pair was accepted, with a stated reason
    ROTATION_PENDING   a trusted peer presented a new key that nothing has
                       authenticated yet
    REVOKED            accepted once, refused now, and refused after restart
    BLOCKED            refused as compromised; distinct from REVOKED because a
                       compromised key must not be able to rotate back in

``IDENTITY_CHANGED`` is not stored: it is the derived verdict a TRUSTED pin
produces when the alias now resolves to different fingerprints. Deriving it is
what keeps a substituted key from being silently promoted to TRUSTED.

Trust by path alone is impossible (a pin is a fingerprint, and the fingerprint
must match the key that will actually sign). Trust by display name alone is
impossible (the seat is metadata on the pin, never the key it is matched on).
Silent key substitution is impossible (a changed key is a refusal with a named
reason, not an overwrite). Revocation survives restart (the registry is durable,
and a revoked pin refuses a rotation back).

Policy is itself versioned and hashed, so a material change to what this module
refuses is visible on every pin instead of arriving silently with a deployment.

Two modes, one registry: ``advisory`` (default) records and reports without
blocking, so existing workspaces keep working exactly as before;
``enforce`` makes a refusal binding for delivery. Nothing here decrypts, opens a
message, or reads a private key -- a pin is public metadata about a key.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from sailang import SailangError
from saimail import envelope, postoffice
from saimail import workspace as _workspace

TRUST_SCHEMA = "SAIMAIL_TRUST_PINS_1"
TRUST_VERSION = 1
TRUST_NAME = "trust.json"
LOCK_NAME = "trust.lock"

UNKNOWN = "UNKNOWN"
OBSERVED = "OBSERVED"
TRUSTED = "TRUSTED"
ROTATION_PENDING = "ROTATION_PENDING"
REVOKED = "REVOKED"
BLOCKED = "BLOCKED"
STATES = (UNKNOWN, OBSERVED, TRUSTED, ROTATION_PENDING, REVOKED, BLOCKED)

#: A derived verdict, never a stored state: a TRUSTED pin whose alias now
#: resolves to different fingerprints.
IDENTITY_CHANGED = "IDENTITY_CHANGED"

MODE_ADVISORY = "advisory"
MODE_ENFORCE = "enforce"
MODES = (MODE_ADVISORY, MODE_ENFORCE)

#: The policy that decides which states refuse. Hashed into every pin, so a
#: pin accepted under an older rule set says so.
POLICY_SCHEMA = "SAIMAIL_TRUST_POLICY_1"
POLICY_VERSION = 1
POLICY = {
    "schema": POLICY_SCHEMA,
    "version": POLICY_VERSION,
    "blocking_states": [BLOCKED, REVOKED, ROTATION_PENDING],
    "require_proof_of_possession": True,
}

#: The rotation receipt: the old identity authenticates the transition and the
#: new key proves it holds its own private half. Both sign the SAME body, so a
#: receipt can never authenticate one transition and prove another.
ROTATION_SCHEMA = "SAIMAIL_TRUST_ROTATION_1"
ROTATION_VERSION = 1
ROTATION_DOMAIN = b"SAIMAIL-TRUST-ROTATION\x00"

TRUST_REGISTRY_CORRUPT = "TRUST_REGISTRY_CORRUPT"
TRUST_LOCK_TIMEOUT = "TRUST_LOCK_TIMEOUT"
TRUST_UNKNOWN_PEER = "TRUST_UNKNOWN_PEER"
TRUST_ALREADY_PINNED = "TRUST_ALREADY_PINNED"
TRUST_ALREADY_REFUSED = "TRUST_ALREADY_REFUSED"
TRUST_ROTATION_INVALID = "TRUST_ROTATION_INVALID"
TRUST_ROTATION_SIGNATURE_INVALID = "TRUST_ROTATION_SIGNATURE_INVALID"
TRUST_ROTATION_NOTHING_CHANGED = "TRUST_ROTATION_NOTHING_CHANGED"
TRUST_ROTATION_SUPERSEDED = "TRUST_ROTATION_SUPERSEDED"
TRUST_IDENTITY_CHANGED = "TRUST_IDENTITY_CHANGED"
BAD_MODE = "BAD_MODE"
BAD_TRUST_SOURCE = "BAD_TRUST_SOURCE"

OPERATOR_ACTION_CODES = frozenset({
    TRUST_REGISTRY_CORRUPT, TRUST_LOCK_TIMEOUT, TRUST_UNKNOWN_PEER,
    TRUST_ALREADY_PINNED, TRUST_ALREADY_REFUSED, TRUST_ROTATION_INVALID,
    TRUST_ROTATION_SIGNATURE_INVALID, TRUST_ROTATION_NOTHING_CHANGED,
    TRUST_ROTATION_SUPERSEDED, TRUST_IDENTITY_CHANGED, BAD_MODE, BAD_TRUST_SOURCE,
})

_REGISTRY_FIELDS = frozenset({"schema", "version", "mode", "policy_hash", "peers"})
_RECORD_FIELDS = frozenset({
    "alias", "seat", "state", "sender_kid", "recipient_kid", "first_seen",
    "accepted_at", "trust_source", "revoked_at", "revocation_reason",
    "policy_version", "policy_hash", "rotations",
})
_ROTATION_FIELDS = frozenset({
    "receipt_id", "at", "from_sender_kid", "from_recipient_kid",
    "to_sender_kid", "to_recipient_kid", "receipt_hash",
})
_RECEIPT_BODY_FIELDS = frozenset({
    "schema", "version", "seat", "at", "old_sender_public_key",
    "old_recipient_public_key", "new_sender_public_key", "new_recipient_public_key",
    "note",
})
_RECEIPT_FIELDS = _RECEIPT_BODY_FIELDS | {"alias", "old_signature", "new_signature"}

#: A trust source is a short token naming WHY a key was accepted. It is
#: provenance an operator can audit, never an authority: nothing reads it as a
#: permission.
_MAX_SOURCE = 128


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def policy_hash() -> str:
    """The hash of the policy these pins are judged against."""
    return _sha256(_canonical_bytes(POLICY))


def _path(root: Path) -> Path:
    return Path(root) / TRUST_NAME


def _empty_registry() -> dict:
    return {"schema": TRUST_SCHEMA, "version": TRUST_VERSION, "mode": MODE_ADVISORY,
            "policy_hash": policy_hash(), "peers": {}}


def _check_record(alias, record) -> dict:
    if (not _workspace.SEAT_RE.match(alias) or not isinstance(record, dict)
            or set(record) != _RECORD_FIELDS):
        _reject(TRUST_REGISTRY_CORRUPT,
                f"trust pin {alias!r} has an unexpected field set")
    if record["state"] not in STATES or record["state"] == UNKNOWN:
        _reject(TRUST_REGISTRY_CORRUPT,
                f"trust pin {alias!r} has unknown state {record['state']!r}")
    if not _workspace.SEAT_RE.match(record["seat"] or ""):
        _reject(TRUST_REGISTRY_CORRUPT, f"trust pin {alias!r} carries no seat")
    for field in ("sender_kid", "recipient_kid"):
        if not isinstance(record[field], str) or not record[field].startswith("sha256:"):
            _reject(TRUST_REGISTRY_CORRUPT,
                    f"trust pin {alias!r} {field} is not a canonical key fingerprint")
    if not isinstance(record["rotations"], list):
        _reject(TRUST_REGISTRY_CORRUPT, f"trust pin {alias!r} has a malformed rotation chain")
    for entry in record["rotations"]:
        if not isinstance(entry, dict) or set(entry) != _ROTATION_FIELDS:
            _reject(TRUST_REGISTRY_CORRUPT,
                    f"trust pin {alias!r} has a malformed rotation receipt")
    return record


def _read(root: Path) -> dict:
    """The validated registry. A missing file is an empty ADVISORY registry.

    Corrupt is not empty: a damaged file refuses loudly, because a registry
    that silently read as "no pins" would turn every revoked peer back into an
    unknown one.
    """
    path = _path(root)
    if not path.is_file():
        return _empty_registry()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _reject(TRUST_REGISTRY_CORRUPT, f"trust registry is unreadable: {exc}")
    if (not isinstance(payload, dict) or set(payload) != _REGISTRY_FIELDS
            or payload["schema"] != TRUST_SCHEMA
            or payload["version"] != TRUST_VERSION
            or payload["mode"] not in MODES
            or not isinstance(payload["peers"], dict)
            or not isinstance(payload["policy_hash"], str)):
        _reject(TRUST_REGISTRY_CORRUPT, "trust registry declares an unknown shape")
    for alias, record in payload["peers"].items():
        _check_record(alias, record)
    return payload


def _write(root: Path, registry: dict) -> None:
    _workspace._atomic_write_bytes(_path(root), _canonical_bytes(registry))


def _lock(root: Path):
    return postoffice._OsFileLock(Path(root) / LOCK_NAME, busy_code=TRUST_LOCK_TIMEOUT)


def _now(clock) -> str:
    return (clock or postoffice.utc_now)()


def _peer_kids(record: dict) -> tuple:
    return record["sender_kid"], record["recipient_kid"]


def _registered_kids(workspace, alias: str) -> tuple:
    """The fingerprints the alias resolves to RIGHT NOW, or a named refusal.

    Display-name equality is not consulted anywhere in this path: the alias is
    a lookup key, and only the two fingerprints carry meaning.
    """
    record = workspace.peers.get(alias)
    if record is None:
        _reject(TRUST_UNKNOWN_PEER,
                f"alias {alias!r} names no registered recipient; register its identity "
                "card before pinning trust")
    return _peer_kids(record)


def _verdict(record, registry_mode: str, current: tuple | None) -> dict:
    """What the registry says about one peer right now, and why."""
    if record is None:
        return {"state": UNKNOWN, "reason": "NO_PIN", "blocking": False,
                "allowed": registry_mode == MODE_ADVISORY}
    state = record["state"]
    if state in (REVOKED, BLOCKED):
        return {"state": state, "reason": f"{state}_PIN", "blocking": True,
                "allowed": False}
    if state == ROTATION_PENDING:
        return {"state": state, "reason": "UNAUTHENTICATED_ROTATION", "blocking": True,
                "allowed": False}
    if state == TRUSTED and current is not None and current != _peer_kids(record):
        return {"state": IDENTITY_CHANGED,
                "reason": "PINNED_FINGERPRINT_NO_LONGER_RESOLVES", "blocking": True,
                "allowed": False}
    if state == TRUSTED:
        return {"state": TRUSTED, "reason": "PINNED_FINGERPRINT_MATCHES",
                "blocking": False, "allowed": True}
    return {"state": OBSERVED, "reason": "OBSERVED_NOT_ACCEPTED", "blocking": False,
            "allowed": registry_mode == MODE_ADVISORY}


def decide(workspace, alias: str) -> dict:
    """The trust verdict for one alias, plus the pin it was read from."""
    registry = _read(workspace.root)
    record = registry["peers"].get(alias)
    peer = workspace.peers.get(alias)
    current = _peer_kids(peer) if peer is not None else None
    verdict = _verdict(record, registry["mode"], current)
    return {"alias": alias, "mode": registry["mode"], "policy_version": POLICY_VERSION,
            "policy_hash": registry["policy_hash"], **verdict,
            "pinned": dict(record) if record is not None else None,
            "registered": {"sender_kid": current[0], "recipient_kid": current[1]}
            if current is not None else None}


def admit(workspace, alias: str, record: dict) -> None:
    """The delivery gate: refuse a blocked peer, and only in enforce mode.

    Advisory mode records and reports but never blocks, so enabling trust is an
    explicit act with an explicit blast radius.
    """
    registry = _read(workspace.root)
    verdict = _verdict(registry["peers"].get(alias), registry["mode"], _peer_kids(record))
    if registry["mode"] != MODE_ENFORCE or not verdict["blocking"]:
        return
    _reject(TRUST_IDENTITY_CHANGED if verdict["state"] == IDENTITY_CHANGED
            else TRUST_ALREADY_REFUSED,
            f"alias {alias!r} is {verdict['state']} ({verdict['reason']}); "
            "refused by the trust registry in enforce mode")


def observe(workspace, alias: str, *, clock=None) -> dict:
    """Record that this alias resolves to these keys, without accepting them.

    Observing is not trusting: a first sighting is exactly the state in which an
    operator has been asked to decide, so it stays unaccepted.
    """
    with _lock(workspace.root):
        now = _now(clock)
        kids = _registered_kids(workspace, alias)
        registry = _read(workspace.root)
        existing = registry["peers"].get(alias)
        if existing is not None:
            return _result("trust-observe", OBSERVED, workspace, existing,
                           "already observed; observing again changes nothing")
        peer = workspace.peers[alias]
        record = {name: None for name in _RECORD_FIELDS}
        record.update(alias=alias, seat=peer["seat"], state=OBSERVED,
                      sender_kid=kids[0], recipient_kid=kids[1], first_seen=now,
                      policy_version=POLICY_VERSION, policy_hash=policy_hash(),
                      rotations=[])
        registry["peers"][alias] = record
        _write(workspace.root, registry)
    return _result("trust-observe", OBSERVED, workspace, record,
                   f"alias {alias} observed at {kids[0][:19]}; NOT trusted yet")


def pin(workspace, alias: str, *, source: str, clock=None) -> dict:
    """Accept exactly the key the alias resolves to now, for a stated reason."""
    if not isinstance(source, str) or not source.strip() or len(source) > _MAX_SOURCE:
        _reject(BAD_TRUST_SOURCE,
                "a trust source is short text naming why this key was accepted")
    with _lock(workspace.root):
        now = _now(clock)
        kids = _registered_kids(workspace, alias)
        registry = _read(workspace.root)
        existing = registry["peers"].get(alias)
        if existing is not None and existing["state"] in (TRUSTED, REVOKED, BLOCKED):
            _reject(TRUST_ALREADY_PINNED,
                    f"alias {alias} is {existing['state']}; revoke it explicitly "
                    "before pinning again")
        peer = workspace.peers[alias]
        record = {name: None for name in _RECORD_FIELDS}
        record.update(alias=alias, seat=peer["seat"], state=TRUSTED,
                      sender_kid=kids[0], recipient_kid=kids[1], first_seen=now,
                      accepted_at=now, trust_source=source.strip(),
                      policy_version=POLICY_VERSION, policy_hash=policy_hash(),
                      rotations=list(existing["rotations"]) if existing else [])
        registry["peers"][alias] = record
        _write(workspace.root, registry)
    return _result("trust-pin", TRUSTED, workspace, record,
                   f"alias {alias} trusted at {kids[0][:19]} ({source.strip()})")


def _refuse_pin(workspace, alias: str, state: str, reason: str, *, clock=None) -> dict:
    with _lock(workspace.root):
        now = _now(clock)
        registry = _read(workspace.root)
        existing = registry["peers"].get(alias)
        if existing is None:
            peer = workspace.peers.get(alias) if alias in workspace.peers else None
            if peer is None:
                _reject(TRUST_UNKNOWN_PEER, f"alias {alias!r} names no registered recipient")
            kids = _peer_kids(peer)
            record = {name: None for name in _RECORD_FIELDS}
            record.update(alias=alias, seat=peer["seat"], state=state,
                          sender_kid=kids[0], recipient_kid=kids[1], first_seen=now,
                          rotations=[])
        else:
            record = dict(existing)
        if record["state"] == state and record["revoked_at"]:
            _reject(TRUST_ALREADY_REFUSED, f"alias {alias} is already {state}")
        record.update(state=state, revoked_at=now, revocation_reason=reason,
                      accepted_at=None)
        registry["peers"][alias] = record
        _write(workspace.root, registry)
    return _result("trust-refuse", state, workspace, record,
                   f"alias {alias} is {state} ({reason}); the refusal is durable")


def revoke(workspace, alias: str, *, reason: str, clock=None) -> dict:
    """Refuse this peer now and after every restart."""
    return _refuse_pin(workspace, alias, REVOKED, reason, clock=clock)


def block(workspace, alias: str, *, reason: str, clock=None) -> dict:
    """Refuse this peer as compromised.

    Distinct from REVOKED so the reason is legible later: a revoked peer may
    re-pin after an operator looks at it, a blocked one must not.
    """
    return _refuse_pin(workspace, alias, BLOCKED, reason, clock=clock)


def set_mode(workspace, mode: str, *, clock=None) -> dict:
    """Choose whether a blocked pin actually refuses delivery."""
    if mode not in MODES:
        _reject(BAD_MODE, f"mode must be one of {list(MODES)}, got {mode!r}")
    with _lock(workspace.root):
        registry = _read(workspace.root)
        registry["mode"] = mode
        registry["policy_hash"] = policy_hash()
        _write(workspace.root, registry)
    return _workspace.command_result(
        "trust-mode", "OK", workspace=workspace,
        trust={"mode": mode, "policy_version": POLICY_VERSION,
               "policy_hash": policy_hash(), "pins": len(registry["peers"])},
        detail=f"trust registry is {mode}; "
               + ("blocked pins refuse delivery" if mode == MODE_ENFORCE
                  else "blocked pins are reported but never block"))


# --------------------------------------------------------------------------
# rotation
# --------------------------------------------------------------------------

def _sign(private_key, body: dict) -> str:
    signature = private_key.sign(ROTATION_DOMAIN + _canonical_bytes(body))
    return signature.hex()


def _verify(public_key: Ed25519PublicKey, signature_hex, body: dict) -> bool:
    try:
        public_key.verify(bytes.fromhex(signature_hex),
                          ROTATION_DOMAIN + _canonical_bytes(body))
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


def _check_receipt(payload) -> dict:
    if not isinstance(payload, dict) or set(payload) != _RECEIPT_FIELDS:
        _reject(TRUST_ROTATION_INVALID, "rotation receipt has an unexpected field set")
    if (payload["schema"] != ROTATION_SCHEMA
            or payload["version"] != ROTATION_VERSION):
        _reject(TRUST_ROTATION_INVALID,
                f"rotation receipt declares {payload['schema']!r} "
                f"v{payload['version']!r}; this build reads {ROTATION_SCHEMA} "
                f"v{ROTATION_VERSION}")
    if not _workspace.SEAT_RE.match(payload["alias"] or ""):
        _reject(TRUST_ROTATION_INVALID, "a rotation receipt names one alias")
    if not _workspace.SEAT_RE.match(payload["seat"] or ""):
        _reject(TRUST_ROTATION_INVALID, "a rotation receipt names one seat")
    for field in ("old_sender_public_key", "old_recipient_public_key",
                  "new_sender_public_key", "new_recipient_public_key"):
        if (not isinstance(payload[field], str)
                or len(payload[field]) != 64
                or not _workspace._HEX32_RE.match(payload[field])):
            _reject(TRUST_ROTATION_INVALID,
                    f"rotation receipt {field} is not 32 raw bytes of lowercase hex")
    for field in ("old_signature", "new_signature"):
        if not isinstance(payload[field], str) or not payload[field]:
            _reject(TRUST_ROTATION_INVALID, f"rotation receipt {field} is required")
    return payload


def _receipt_body(receipt: dict) -> dict:
    return {name: receipt[name] for name in _RECEIPT_BODY_FIELDS}


def build_rotation_receipt(old_workspace, new_workspace, *, alias: str, clock=None,
                           note=None) -> dict:
    """The receipt a peer produces when it legitimately rotates its keys.

    Built from two live workspaces because a rotation is a two-party fact: the
    outgoing identity signs with the key that was pinned, and the incoming one
    signs with the key that is being installed. A single party cannot mint a
    receipt that satisfies both halves.
    """
    if old_workspace.seat != new_workspace.seat:
        _reject(TRUST_ROTATION_INVALID,
                f"a rotation keeps one seat: {old_workspace.seat} != {new_workspace.seat}")
    if not _workspace.SEAT_RE.match(alias or ""):
        _reject(TRUST_ROTATION_INVALID, "a rotation receipt names one alias")
    now = _now(clock)
    body = {
        "schema": ROTATION_SCHEMA, "version": ROTATION_VERSION,
        "seat": old_workspace.seat, "at": now,
        "old_sender_public_key": _public_hex(old_workspace, "sender"),
        "old_recipient_public_key": _public_hex(old_workspace, "recipient"),
        "new_sender_public_key": _public_hex(new_workspace, "sender"),
        "new_recipient_public_key": _public_hex(new_workspace, "recipient"),
        "note": note if isinstance(note, str) and note else None,
    }
    receipt = {name: body[name] for name in _RECEIPT_BODY_FIELDS}
    receipt.update(alias=alias,
                   old_signature=_sign(old_workspace.sender_private_key, body),
                   new_signature=_sign(new_workspace.sender_private_key, body))
    return receipt


def _public_hex(workspace, role: str) -> str:
    key = (workspace.sender_private_key if role == "sender"
           else workspace.recipient_private_key)
    return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()


def expect_rotation(workspace, alias: str, card, *, clock=None) -> dict:
    """Mark a trusted peer as presenting an unauthenticated new key.

    This is what an operator does when a peer says "I rebuilt my workspace".
    Nothing is trusted yet: the pin moves to ROTATION_PENDING, which blocks in
    enforce mode until ``apply_rotation`` proves the transition.
    """
    parsed = _workspace._parse_card(card)
    peer = workspace.peers.get(alias)
    if peer is None:
        _reject(TRUST_UNKNOWN_PEER, f"alias {alias!r} names no registered recipient")
    if parsed["seat"] != peer["seat"]:
        _reject(TRUST_ROTATION_INVALID,
                "the presented card names a different seat than the pinned alias; "
                "a display name is never continuity evidence")
    with _lock(workspace.root):
        registry = _read(workspace.root)
        record = registry["peers"].get(alias)
        if record is None:
            _reject(TRUST_ROTATION_INVALID, f"alias {alias!r} has no pin to rotate")
        if (record["sender_kid"], record["recipient_kid"]) == (parsed["sender_kid"],
                                                               parsed["recipient_kid"]):
            _reject(TRUST_ROTATION_NOTHING_CHANGED,
                    f"the presented card carries the pinned fingerprints; nothing rotates")
        record.update(state=ROTATION_PENDING, accepted_at=None)
        registry["peers"][alias] = record
        _write(workspace.root, registry)
    return _result("trust-rotation-pending", ROTATION_PENDING, workspace, record,
                   f"alias {alias} presented {parsed['sender_kid'][:19]}; "
                   "unauthenticated until a receipt proves it")


def _key_fingerprint(public_hex: str) -> str:
    return envelope.fingerprint(
        X25519PublicKey.from_public_bytes(bytes.fromhex(public_hex)))


def apply_rotation(workspace, alias: str, receipt, *, clock=None) -> dict:
    """Complete a rotation: the pinned key authenticates it, the new key proves it.

    Both halves are required. A receipt signed only by the new key is a new
    identity wearing an old name; a receipt signed only by the old key is an
    old identity handing its name to a stranger.
    """
    parsed = _check_receipt(receipt)
    if parsed["alias"] != alias:
        _reject(TRUST_ROTATION_INVALID,
                f"receipt names alias {parsed['alias']!r}, not {alias!r}")
    old_sender = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(parsed["old_sender_public_key"]))
    new_sender = Ed25519PublicKey.from_public_bytes(
        bytes.fromhex(parsed["new_sender_public_key"]))
    old_kids = (envelope.fingerprint(old_sender),
                _key_fingerprint(parsed["old_recipient_public_key"]))
    new_kids = (envelope.fingerprint(new_sender),
                _key_fingerprint(parsed["new_recipient_public_key"]))
    if old_kids == new_kids:
        _reject(TRUST_ROTATION_NOTHING_CHANGED,
                "the receipt names the same fingerprints as the outgoing identity")
    body = _receipt_body(parsed)
    with _lock(workspace.root):
        now = _now(clock)
        registry = _read(workspace.root)
        record = registry["peers"].get(alias)
        if record is None:
            _reject(TRUST_ROTATION_INVALID, f"alias {alias!r} has no pin to rotate")
        if record["state"] in (REVOKED, BLOCKED):
            _reject(TRUST_ROTATION_SUPERSEDED,
                    f"alias {alias} is {record['state']}; a refused peer cannot rotate "
                    "its way back in")
        if old_kids != _peer_kids(record):
            _reject(TRUST_ROTATION_SIGNATURE_INVALID,
                    "the receipt's outgoing fingerprints are not the pinned ones; "
                    "this is not a rotation of the trusted identity")
        if not _verify(old_sender, parsed["old_signature"], body):
            _reject(TRUST_ROTATION_SIGNATURE_INVALID,
                    "the pinned identity did not authenticate this transition")
        if not _verify(new_sender, parsed["new_signature"], body):
            _reject(TRUST_ROTATION_SIGNATURE_INVALID,
                    "the new key did not prove possession of its own private half")
        entry = {"receipt_id": _sha256(_canonical_bytes(body)),
                 "at": parsed["at"] or now,
                 "from_sender_kid": old_kids[0], "from_recipient_kid": old_kids[1],
                 "to_sender_kid": new_kids[0], "to_recipient_kid": new_kids[1],
                 "receipt_hash": _sha256(_canonical_bytes(
                     {name: parsed[name] for name in _RECEIPT_FIELDS}))}
        record.update(state=TRUSTED, sender_kid=new_kids[0], recipient_kid=new_kids[1],
                      accepted_at=now, revoked_at=None, revocation_reason=None,
                      policy_version=POLICY_VERSION, policy_hash=policy_hash(),
                      rotations=list(record["rotations"]) + [entry])
        registry["peers"][alias] = record
        _write(workspace.root, registry)
    return _result("trust-rotate", TRUSTED, workspace, record,
                   f"alias {alias} rotated to {new_kids[0][:19]}; lineage kept "
                   f"({len(record['rotations'])} receipt(s))")


# --------------------------------------------------------------------------
# reads
# --------------------------------------------------------------------------

def explain(workspace, alias: str) -> dict:
    """Why this peer is trusted or refused right now."""
    verdict = decide(workspace, alias)
    return _workspace.command_result(
        "trust-explain", "OK", workspace=workspace, trust=verdict,
        detail=f"alias {alias}: {verdict['state']} ({verdict['reason']}), "
               f"registry {verdict['mode']}")


def list_pins(workspace) -> dict:
    """Every pin and its current verdict; public metadata only."""
    registry = _read(workspace.root)
    items = []
    for alias in sorted(registry["peers"]):
        items.append({name: value for name, value in decide(workspace, alias).items()
                      if name != "pinned"} | {"pin": registry["peers"][alias]})
    return _workspace.command_result(
        "trust-list", "OK", workspace=workspace,
        trust={"mode": registry["mode"], "policy_version": POLICY_VERSION,
               "policy_hash": registry["policy_hash"], "count": len(items)},
        items=items,
        detail=f"{len(items)} pin(s); registry {registry['mode']}, "
               "keys are fingerprint-pinned, never name-pinned")


def _result(command: str, state: str, workspace, record: dict, detail: str) -> dict:
    result = _workspace.command_result(
        command, state, workspace=workspace, trust={"alias": record["alias"],
                                                    "seat": record["seat"],
                                                    "state": record["state"],
                                                    "sender_kid": record["sender_kid"],
                                                    "recipient_kid": record["recipient_kid"],
                                                    "accepted_at": record["accepted_at"],
                                                    "trust_source": record["trust_source"],
                                                    "first_seen": record["first_seen"],
                                                    "rotations": len(record["rotations"]),
                                                    "policy_hash": record["policy_hash"]},
        detail=detail)
    if state in (REVOKED, BLOCKED, ROTATION_PENDING):
        result["ok"] = False
        result["operator_action_required"] = True
    return result


__all__ = [
    "BLOCKED",
    "IDENTITY_CHANGED",
    "MODES",
    "MODE_ADVISORY",
    "MODE_ENFORCE",
    "OBSERVED",
    "OPERATOR_ACTION_CODES",
    "POLICY",
    "POLICY_VERSION",
    "REVOKED",
    "ROTATION_PENDING",
    "ROTATION_SCHEMA",
    "STATES",
    "TRUSTED",
    "TRUST_ALREADY_PINNED",
    "TRUST_ALREADY_REFUSED",
    "TRUST_IDENTITY_CHANGED",
    "TRUST_LOCK_TIMEOUT",
    "TRUST_REGISTRY_CORRUPT",
    "TRUST_ROTATION_INVALID",
    "TRUST_ROTATION_NOTHING_CHANGED",
    "TRUST_ROTATION_SIGNATURE_INVALID",
    "TRUST_ROTATION_SUPERSEDED",
    "TRUST_SCHEMA",
    "TRUST_UNKNOWN_PEER",
    "UNKNOWN",
    "admit",
    "apply_rotation",
    "block",
    "build_rotation_receipt",
    "decide",
    "expect_rotation",
    "explain",
    "list_pins",
    "observe",
    "pin",
    "policy_hash",
    "revoke",
    "set_mode",
]