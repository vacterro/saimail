"""Cold archive: archive, verify, then prune (FUTURE GATE Wave 3).

Defect class this module eliminates: an archive that deletes before it proves.
A mailbox kept only in hot storage grows without bound, and the obvious way to
bound it is to delete the oldest bundles. That is data loss the moment the copy
being deleted from is the only copy -- and the moment a write to cold storage
failed halfway, which is exactly when an operator is most likely to be deleting.

The order here is therefore not a preference, it is the whole module::

    HOT -> WRITE COLD ARCHIVE -> VERIFY INTEGRITY/READ-BACK -> ARCHIVE RECEIPT
        -> PRUNE HOT

Prune is the only step that removes anything, and it runs last, only for records
whose cold copy was written, read back off disk, hash-checked, and (when the
workspace holds a recipient key) actually reopened. A failure anywhere before
the receipt leaves the hot copy exactly as it was. There is no path in this
module that deletes a message whose cold copy is missing, unverified or corrupt.

What "hot" means here: the sealed container bytes of a delivered bundle. The
index row is the small metadata projection that makes a message discoverable, so
pruning does not remove it -- after a prune the message is still findable by
`search`, and `restore` brings the body back. That is what keeps a Future Letter
discoverable after its hot copy is gone.

What the cold copy is: the canonical encrypted payload, byte for byte, plus the
receipt, plus a versioned `SAIMAIL_COLD_1` manifest carrying the index-row
provenance and the ledger link. Nothing is re-encoded, re-sealed, summarised or
compressed in a way that changes bytes. There is no lossy summary standing in as
the only copy, and there is no plaintext derivative anywhere in this format --
which is why `search` is metadata-only and refuses a semantic query by name.

Custody is unchanged by archiving. A `FUTURE_LETTER` bundle is sealed to this
workspace identity and the archive stores exactly the mailbox bytes, so the
archive can never read anything the mailbox could not.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Mapping, Optional

from sailang import SailangError
from saimail import envelope
from saimail import ledger as _ledger
from saimail import postoffice
from saimail import workspace as _workspace

COLD_SCHEMA = "SAIMAIL_COLD_1"
COLD_VERSION = 1
COLD_DIR = "cold"
ITEMS_DIR = "items"
MANIFEST_NAME = "manifest.json"
CONTAINER_NAME = postoffice.CONTAINER_NAME
RECEIPT_NAME = postoffice.RECEIPT_NAME

#: Archive operation outcomes. `ok` is derived from these by
#: `command_result`, so an operator reading one field cannot be misled.
ARCHIVED = "ARCHIVED"
ALREADY_COLD = "ALREADY_COLD"
ALREADY_HOT = "ALREADY_HOT"
RESTORED = "RESTORED"
PRUNED = "PRUNED"
VERIFIED = "VERIFIED"

#: Three-valued read-back. `SKIPPED_NO_KEY` is the honest answer when the caller
#: holds no recipient key: the hash was checked, the payload was not opened, and
#: the report must not claim a stronger guarantee than it has.
REOPEN_OPENED = "OPENED"
REOPEN_SKIPPED = "SKIPPED_NO_KEY"
REOPEN_FAILED = "FAILED"

NOT_HOT = "COLD_NOTHING_TO_ARCHIVE"
NOT_COLD = "COLD_NOTHING_TO_RESTORE"
COLD_CORRUPT = "COLD_CORRUPT"
COLD_HASH_MISMATCH = "COLD_HASH_MISMATCH"
COLD_MANIFEST_INVALID = "COLD_MANIFEST_INVALID"
COLD_INCOMPLETE = "COLD_INCOMPLETE"
COLD_WRITE_FAILED = "COLD_WRITE_FAILED"
COLD_VERIFY_FAILED = "COLD_VERIFY_FAILED"
COLD_UNREADABLE = "COLD_UNREADABLE"
COLD_UNKNOWN_ID = "COLD_UNKNOWN_ID"
BAD_RETENTION = "COLD_BAD_RETENTION"
SEMANTIC_SEARCH_UNSUPPORTED = "COLD_SEMANTIC_SEARCH_UNSUPPORTED"

OPERATOR_ACTION_CODES = frozenset({
    COLD_CORRUPT, COLD_HASH_MISMATCH, COLD_MANIFEST_INVALID, COLD_INCOMPLETE,
    COLD_UNREADABLE,
})

_HEALTHY = "HEALTHY"
_DEGRADED = "DEGRADED"
_UNKNOWN = "UNKNOWN"

#: Never-prune by class. A Future Letter is the one message kind whose whole
#: purpose is to outlive the session that wrote it, and a time capsule is a
#: message that is not openable yet -- neither may be aged out of hot storage by
#: a retention count. Retention may still make them ineligible to ARCHIVE, but
#: once cold they are retained regardless of age, count and size.
PINNED_KINDS = frozenset({"FUTURE_LETTER"})

_MANIFEST_KEYS = frozenset({
    "schema", "version", "envelope_id", "container_sha256", "archived_at",
    "hot_state", "hot_removed", "pinned", "pinned_reason", "bytes",
    "ledger_message_id", "ledger_seq", "index_row", "verified", "receipt_at",
})

_MAX_SEARCH_LIMIT = 200
_DEFAULT_SEARCH_LIMIT = 50


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(payload: Mapping) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _parse_utc(text) -> datetime:
    if not isinstance(text, str):
        _reject(COLD_MANIFEST_INVALID, "a cold timestamp is not a string")
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _reject(COLD_MANIFEST_INVALID, f"cold timestamp {text!r} is not UTC Zulu")


def _operator_action(result: dict) -> dict:
    result["ok"] = False
    result["operator_action_required"] = True
    return result


def _refusal(result: dict) -> dict:
    """A refusal is not a health problem: nothing is corrupt, the caller asked
    for something this build does not do. `ok` still has to be False."""
    result["ok"] = False
    return result


# ---- layout ---------------------------------------------------------------


def cold_root(workspace) -> Path:
    """The archive root, next to `mail/` and `ledger/`, never inside either."""
    return Path(getattr(workspace, "root", workspace)) / COLD_DIR


def items_root(workspace) -> Path:
    return cold_root(workspace) / ITEMS_DIR


def record_path(workspace, envelope_id: str) -> Path:
    """One record directory. The ENVELOPE_ID is the directory name, so the
    path is derived from the content identity and not chosen by a caller."""
    return items_root(workspace) / _eid_hex(envelope_id)


def _eid_hex(envelope_id: str) -> str:
    if not isinstance(envelope_id, str) or not envelope_id.startswith("sha256:"):
        _reject(COLD_UNKNOWN_ID, f"{envelope_id!r} is not a sha256:<hex> ENVELOPE_ID")
    hex_part = envelope_id.split(":", 1)[1]
    if len(hex_part) != 64 or any(c not in "0123456789abcdef" for c in hex_part):
        _reject(COLD_UNKNOWN_ID, f"{envelope_id!r} is not sha256:<64 lowercase hex>")
    return hex_part


def _utc_now() -> str:
    return postoffice.utc_now()


# ---- the record -----------------------------------------------------------


def _parse_manifest(raw: bytes, envelope_id: str) -> dict:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        _reject(COLD_MANIFEST_INVALID,
                f"cold record {envelope_id} manifest is not UTF-8")
    try:
        manifest = json.loads(text, object_pairs_hook=postoffice._duplicate_guard)
    except SailangError:
        raise
    except ValueError as exc:
        _reject(COLD_MANIFEST_INVALID,
                f"cold record {envelope_id} manifest is not JSON: {exc}")
    if not isinstance(manifest, dict):
        _reject(COLD_MANIFEST_INVALID,
                f"cold record {envelope_id} manifest is not a JSON object")
    keys = set(manifest)
    if keys != _MANIFEST_KEYS:
        _reject(COLD_MANIFEST_INVALID,
                f"cold record {envelope_id} manifest keys deviate from the "
                f"contract: missing {sorted(_MANIFEST_KEYS - keys)}, "
                f"extra {sorted(keys - _MANIFEST_KEYS)}")
    if manifest["schema"] != COLD_SCHEMA or manifest["version"] != COLD_VERSION:
        _reject(COLD_MANIFEST_INVALID,
                f"cold record {envelope_id} manifest is version "
                f"{manifest['schema']}/{manifest['version']}")
    if manifest["envelope_id"] != envelope_id:
        _reject(COLD_MANIFEST_INVALID,
                f"cold record {envelope_id} manifest names a different envelope")
    if manifest["container_sha256"] != _eid_hex(envelope_id):
        _reject(COLD_MANIFEST_INVALID,
                f"cold record {envelope_id} manifest states a container hash that "
                "is not the ENVELOPE_ID")
    if manifest["hot_state"] not in ("UNREAD", "READ", "BOTH"):
        _reject(COLD_MANIFEST_INVALID,
                f"cold record {envelope_id} names an unknown hot state")
    if not isinstance(manifest["index_row"], dict):
        _reject(COLD_MANIFEST_INVALID,
                f"cold record {envelope_id} carries no provenance row")
    _parse_utc(manifest["archived_at"])
    return manifest


def read_record(workspace, envelope_id: str) -> Optional[dict]:
    """The manifest for one cold record, or None when there is no record.

    A manifest that exists but cannot be parsed is NOT None and not a raise: it
    is corruption, and `health` is where corruption becomes visible.
    """
    path = record_path(workspace, envelope_id)
    if not path.is_dir():
        return None
    raw = _read_or_none(path / MANIFEST_NAME)
    if raw is None:
        _reject(COLD_INCOMPLETE,
                f"cold record {envelope_id} has no manifest")
    try:
        return _parse_manifest(raw, envelope_id)
    except SailangError:
        raise


def _read_or_none(path: Path) -> Optional[bytes]:
    try:
        return path.read_bytes()
    except OSError:
        return None


def read_records(workspace) -> tuple:
    """Every readable manifest, ordered by ARCHIVED_AT then ENVELOPE_ID.

    A record whose manifest cannot be parsed is skipped here and reported by
    `health`, so a single corrupt entry cannot make the whole archive unreadable.
    """
    base = items_root(workspace)
    if not base.is_dir():
        return ()
    records = []
    for path in sorted(base.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        envelope_id = f"sha256:{path.name}"
        raw = _read_or_none(path / MANIFEST_NAME)
        if raw is None:
            continue
        try:
            records.append(_parse_manifest(raw, envelope_id))
        except SailangError:
            continue
    records.sort(key=lambda item: (item["archived_at"], item["envelope_id"]))
    return tuple(records)


def _write_manifest(workspace, manifest: dict) -> None:
    path = record_path(workspace, manifest["envelope_id"])
    postoffice._write_complete(path / MANIFEST_NAME, _canonical_json(manifest))


def _ledger_link(workspace, envelope_id: str) -> tuple:
    """`(message_id, seq)` for the last ledger event naming this envelope.

    The ledger's event vocabulary is closed and archiving is not a delivery
    fact, so the archive does not append to it: it stores the link to the event
    that established this message, which is what makes a pruned message
    traceable back to its own history. `(None, None)` when there is no record,
    which is a fact and not a failure.
    """
    try:
        events, state = _ledger.read_events(workspace)
    except SailangError:
        return None, None
    if state == _ledger.STATE_UNREADABLE or not events:
        return None, None
    message_id, seq = None, None
    for event in events:
        if event.get("envelope_id") == envelope_id:
            message_id, seq = event.get("message_id"), event.get("seq")
    return message_id, seq


# ---- verification ---------------------------------------------------------


def verify_record(workspace, envelope_id: str, *, clock=None,
                  opener=None) -> dict:
    """Hash the stored container, and reopen it when a key is available.

    Two strengths, both reported, neither implied by the other:

    * the hash check is unconditional -- `envelope_id` IS the sha256 of the
      container, so it proves the stored bytes are the ones that were sealed;
    * the reopen is "where possible". A header-only workspace holds no
      recipient key and cannot decrypt, and the report says SKIPPED_NO_KEY
      rather than implying the payload was opened.
    """
    manifest = read_record(workspace, envelope_id)
    if manifest is None:
        return _verify_failure(workspace, envelope_id, NOT_COLD,
                               f"{envelope_id} is not in the cold archive",
                               operator=False)
    base = record_path(workspace, envelope_id)
    raw = _read_or_none(base / CONTAINER_NAME)
    if raw is None:
        return _verify_failure(workspace, envelope_id, COLD_INCOMPLETE,
                               f"cold record {envelope_id} has no stored container")
    receipt = _read_or_none(base / RECEIPT_NAME)
    if receipt is None:
        return _verify_failure(workspace, envelope_id, COLD_INCOMPLETE,
                               f"cold record {envelope_id} has no stored receipt")
    try:
        recomputed = envelope.envelope_id(raw)
    except SailangError as exc:
        return _verify_failure(workspace, envelope_id, COLD_CORRUPT,
                               f"cold record {envelope_id} container does not parse "
                               f"({exc.code})")
    if recomputed != envelope_id:
        return _verify_failure(
            workspace, envelope_id, COLD_HASH_MISMATCH,
            f"cold record {envelope_id} hashes to {recomputed}")
    if _sha256(raw) != manifest["container_sha256"]:
        return _verify_failure(workspace, envelope_id, COLD_HASH_MISMATCH,
                               f"cold record {envelope_id} manifest states a "
                               "container hash the bytes do not have")
    reopen = REOPEN_SKIPPED
    if opener is not None:
        try:
            opener(raw)
        except SailangError as exc:
            return _verify_failure(workspace, envelope_id, COLD_VERIFY_FAILED,
                                   f"cold record {envelope_id} did not reopen "
                                   f"({exc.code})")
        except (ValueError, OSError) as exc:
            return _verify_failure(workspace, envelope_id, COLD_VERIFY_FAILED,
                                   f"cold record {envelope_id} did not reopen "
                                   f"({type(exc).__name__})")
        reopen = REOPEN_OPENED
    return _workspace.command_result(
        "cold-verify", VERIFIED, workspace=workspace,
        envelope_id=envelope_id,
        verified={"hash": True, "reopen": reopen,
                  "manifest_consistent": True, "receipt_present": True},
        detail=f"{envelope_id} verified: the stored container hashes to its own "
               f"ENVELOPE_ID and the manifest agrees; reopen {reopen}")


def _verify_failure(workspace, envelope_id: str, code: str, detail: str,
                    *, operator: bool = True) -> dict:
    result = _workspace.command_result(
        "cold-verify", code, workspace=workspace, envelope_id=envelope_id,
        verified={"hash": False, "reopen": REOPEN_FAILED,
                  "manifest_consistent": False, "receipt_present": False},
        detail=detail)
    return _operator_action(result) if operator else result


def _default_opener(workspace):
    """The authorized reopen, when this caller holds a recipient key.

    `WorkspaceHeaders` deliberately cannot open mail, so for that view there is
    no reopen to perform and the verification is honestly hash-only. Nothing
    here widens what a header-only caller can read.
    """
    private_key = getattr(workspace, "recipient_private_key", None)
    if private_key is None:
        return None
    # `self_office` where it exists: a Future Letter is sealed by this workspace
    # to itself, and a sender registry built from peers alone would refuse to
    # verify its own signed mail -- which would make every letter permanently
    # unverifiable in the archive. It is a superset of `office`, never a
    # weaker one.
    office = workspace.self_office() if hasattr(workspace, "self_office") \
        else workspace.office()
    sender_registry = office.sender_registry
    recipient_registry = office.recipient_registry

    def opener(raw: bytes) -> None:
        header = envelope.parse_header(raw)
        verified = envelope.verify(header, sender_registry)
        envelope.open(verified, private_key, recipient_registry)

    return opener


# ---- retention ------------------------------------------------------------


@dataclass(frozen=True)
class RetentionPolicy:
    """What may leave hot storage, and what may never.

    Every field is an independent bound and all of them apply: a record is
    retained if it is pinned, outside `kinds`, inside `older_than`, inside the
    `max_count` newest, or inside `max_bytes`. The default prunes nothing,
    because an unbounded mailbox is a smaller problem than a deleted letter.
    """
    older_than: Optional[timedelta] = None
    max_count: Optional[int] = None
    max_bytes: Optional[int] = None
    kinds: Optional[frozenset] = None
    pin_kinds: frozenset = PINNED_KINDS

    def __post_init__(self) -> None:
        for name in ("max_count", "max_bytes"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or value < 0):
                _reject(BAD_RETENTION, f"{name} must be a non-negative int or None")


DEFAULT_RETENTION = RetentionPolicy()


def _is_pinned(manifest: dict, policy: RetentionPolicy) -> tuple:
    """`(pinned, reason)`. The CLASS is checked before the stored flag so the
    reported reason stays the informative one: a Future Letter reports its kind
    whether or not anyone also pinned it by hand."""
    kind = (manifest.get("index_row") or {}).get("kind")
    if kind in policy.pin_kinds:
        return True, f"KIND_{kind}"
    if manifest.get("pinned"):
        return True, manifest.get("pinned_reason") or "EXPLICIT_PIN"
    return False, None


def select_for_prune(records, policy: RetentionPolicy, *, now=None) -> dict:
    """Split records into prunable and retained, with the reason for each.

    Newest-first by ARCHIVED_AT, and every bound spends its budget on the
    NEWEST records: `max_count=10` keeps the ten most recent hot and lets the
    rest go, `max_bytes=N` fills the budget from the newest down. The other
    reading -- spending the budget on the oldest -- would prune exactly the
    mail an operator most wants to read, so the order is not cosmetic.
    """
    now = now if isinstance(now, str) else (now or postoffice.utc_now())
    now = _parse_utc(now)
    ordered = sorted(records, key=lambda item: (item["archived_at"],
                                                item["envelope_id"]), reverse=True)
    prunable, retained = [], {}
    rank = 0
    used_bytes = 0
    for manifest in ordered:
        envelope_id = manifest["envelope_id"]
        pinned, reason = _is_pinned(manifest, policy)
        if pinned:
            retained[envelope_id] = reason
            continue
        if policy.kinds is not None and \
                (manifest.get("index_row") or {}).get("kind") not in policy.kinds:
            retained[envelope_id] = "KIND_OUT_OF_SCOPE"
            continue
        rank += 1
        # Every declared bound is consulted and ANY of them may retain. A record
        # is prunable only when at least one bound exists and every one of them
        # rejects it -- so a policy with no bounds at all prunes nothing, which
        # is why the default is safe.
        bounds, holding = 0, []
        if policy.max_count is not None:
            bounds += 1
            if rank <= policy.max_count:
                holding.append("WITHIN_COUNT")
        if policy.older_than is not None:
            bounds += 1
            if now - _parse_utc(manifest["archived_at"]) < policy.older_than:
                holding.append("NEWER_THAN_RETENTION")
        if policy.max_bytes is not None:
            bounds += 1
            used_bytes += int(manifest.get("bytes") or 0)
            if used_bytes <= policy.max_bytes:
                holding.append("WITHIN_BYTES")
        if bounds == 0 or holding:
            retained[envelope_id] = holding[0] if holding else "NO_RETENTION_BOUND"
            continue
        prunable.append(envelope_id)
    return {"prunable": prunable, "retained": retained, "considered": len(ordered)}


# ---- the pipeline ---------------------------------------------------------


def archive(workspace, envelope_id: str, *, clock=None, opener=None,
            retention=None, pin: bool = False, prune: bool = False) -> dict:
    """Write the cold copy, verify it off disk, then (only) prune the hot one.

    `prune=False` is the default because archiving is an additive, reversible
    act and pruning is a decision an operator should make under a stated
    policy. Set it to run the wave's full pipeline in one call; the prune step
    still honours the retention policy, so a pinned Future Letter is archived
    and retained.

    Every refusal before the receipt leaves the hot bundle untouched, and the
    cold directory is only ever published by an atomic rename of a fully written
    staging directory -- a half-written record is never visible under its own
    name.
    """
    _eid_hex(envelope_id)
    office = workspace.office(clock=clock)
    existing = read_record(workspace, envelope_id)
    if existing is not None:
        result = _workspace.command_result(
            "cold-archive", ALREADY_COLD, workspace=workspace,
            envelope_id=envelope_id, cold=existing,
            detail=f"{envelope_id} is already in the cold archive; archiving is "
                   "idempotent and nothing was rewritten")
        if not prune:
            return result
        return _prune_one(workspace, envelope_id, existing, clock=clock,
                          retention=retention)

    hot_state = office.bundle_state(envelope_id)
    if hot_state not in ("UNREAD", "READ", "BOTH"):
        return _workspace.command_result(
            "cold-archive", NOT_HOT, workspace=workspace, envelope_id=envelope_id,
            hot_state=hot_state,
            detail=f"{envelope_id} holds no hot bundle ({hot_state}); there is "
                   "nothing to archive and nothing was deleted")
    hot_bundle = office.inbox_bundle(envelope_id) if hot_state == "UNREAD" \
        else office.read_bundle(envelope_id)
    try:
        raw = (hot_bundle / CONTAINER_NAME).read_bytes()
    except OSError as exc:
        _reject(COLD_WRITE_FAILED,
                f"hot bundle {envelope_id} has no readable container "
                f"({type(exc).__name__})")
    try:
        stored_id = envelope.envelope_id(raw)
    except SailangError as exc:
        _reject(COLD_CORRUPT,
                f"hot bundle {envelope_id} does not parse as an envelope "
                f"({exc.code}); the hot copy was left untouched")
    if stored_id != envelope_id:
        _reject(COLD_HASH_MISMATCH,
                f"hot bundle {envelope_id} hashes to {stored_id}; the hot copy was "
                "left untouched")
    receipt_bytes = _read_or_none(hot_bundle / RECEIPT_NAME)
    if receipt_bytes is None:
        _reject(COLD_INCOMPLETE,
                f"hot bundle {envelope_id} has no receipt; the hot copy was left "
                "untouched")

    now = clock or _utc_now
    archived_at = now()
    message_id, seq = _ledger_link(workspace, envelope_id)
    row = office.read_index_row(envelope_id) or {}
    pinned_reason = None
    if pin:
        pinned_reason = "EXPLICIT_PIN"
    elif row.get("kind") in PINNED_KINDS:
        pinned_reason = f"KIND_{row['kind']}"
    manifest = {
        "schema": COLD_SCHEMA,
        "version": COLD_VERSION,
        "envelope_id": envelope_id,
        "container_sha256": _sha256(raw),
        "archived_at": archived_at,
        "hot_state": hot_state,
        "hot_removed": False,
        "pinned": pinned_reason is not None,
        "pinned_reason": pinned_reason,
        "bytes": len(raw),
        "ledger_message_id": message_id,
        "ledger_seq": seq,
        "index_row": row,
        "verified": {"hash": False, "reopen": REOPEN_SKIPPED,
                     "manifest_consistent": False, "receipt_present": False},
        "receipt_at": archived_at,
    }

    base = items_root(workspace)
    try:
        base.mkdir(parents=True, exist_ok=True)
        files = {CONTAINER_NAME: raw, RECEIPT_NAME: receipt_bytes,
                 MANIFEST_NAME: _canonical_json(manifest)}
        status = postoffice._publish_dir(base, _eid_hex(envelope_id), files,
                                         conflict_code=COLD_CORRUPT)
    except (OSError, SailangError) as exc:
        code = exc.code if isinstance(exc, SailangError) else COLD_WRITE_FAILED
        detail = exc.detail if isinstance(exc, SailangError) \
            else f"cold archive write failed ({type(exc).__name__})"
        return _operator_action(_workspace.command_result(
            "cold-archive", code, workspace=workspace, envelope_id=envelope_id,
            hot_state=hot_state,
            detail=f"{detail}; the hot copy was left untouched"))
    if status == postoffice.IDEMPOTENT:
        stored = read_record(workspace, envelope_id)
        return _workspace.command_result(
            "cold-archive", ALREADY_COLD, workspace=workspace,
            envelope_id=envelope_id, cold=stored or manifest,
            detail=f"{envelope_id} converged on an identical cold copy; nothing "
                   "was rewritten")

    # Read-back: verify what was actually STORED, not what we still hold in
    # memory. A copy that verifies against the buffer it came from proves
    # nothing about the disk.
    verified = verify_record(workspace, envelope_id, clock=clock,
                             opener=opener if opener is not None
                             else _default_opener(workspace))
    if verified["status"] != VERIFIED:
        _write_manifest(workspace, manifest)
        result = dict(verified)
        result["command"] = "cold-archive"
        result["hot_state"] = hot_state
        result["detail"] = (f"{verified['detail']}; the hot copy was left "
                            "untouched and the message is NOT pruned")
        return result

    # The archive receipt: written only now, after the read-back succeeded.
    manifest["verified"] = verified["verified"]
    manifest["receipt_at"] = archived_at
    _write_manifest(workspace, manifest)

    result = _workspace.command_result(
        "cold-archive", ARCHIVED, workspace=workspace, envelope_id=envelope_id,
        cold=manifest, verified=verified["verified"], hot_state=hot_state,
        pruned={"removed": False, "reason": "PRUNE_NOT_REQUESTED"},
        detail=f"{envelope_id} written to cold and read back: hash verified, "
               f"reopen {verified['verified']['reopen']}; the hot copy is intact")
    if prune:
        pruned = _prune_one(workspace, envelope_id, manifest, clock=clock,
                            retention=retention)
        result["pruned"] = pruned["pruned"]
        result["status"] = pruned["status"]
        result["ok"] = pruned["ok"]
        result["detail"] = f"{result['detail']}; {pruned['detail']}"
    return result


def _prune_one(workspace, envelope_id: str, manifest: dict, *, clock=None,
               retention=None) -> dict:
    """Remove one hot bundle, and only if the policy retains nothing."""
    policy = retention or DEFAULT_RETENTION
    decision = select_for_prune((manifest,), policy,
                                now=(clock or _utc_now)())
    if envelope_id in decision["retained"]:
        reason = decision["retained"][envelope_id]
        return _workspace.command_result(
            "cold-prune", "PRUNED_RETAINED", workspace=workspace,
            envelope_id=envelope_id,
            pruned={"removed": False, "reason": reason},
            detail=f"{envelope_id} stays in hot storage: {reason}")
    return _prune_bundle(workspace, envelope_id, manifest, clock=clock)


def _prune_bundle(workspace, envelope_id: str, manifest: dict, *,
                  clock=None, opener=None) -> dict:
    """Delete the hot bundle directory, and only a verified cold record's.

    Never the index row. The index row is what keeps the message discoverable
    after the body is gone, so pruning the body is what bounds the mailbox while
    leaving `search` and `restore` working. A prune that removed the row would
    turn a bounded mailbox into a silent one.

    The verification here is not decoration. A record whose cold copy was
    corrupted, or whose receipt never landed, must keep its hot copy: that is
    the whole difference between this module and a delete loop.
    """
    verified = verify_record(workspace, envelope_id, clock=clock,
                             opener=opener if opener is not None
                             else _default_opener(workspace))
    if verified["status"] != VERIFIED:
        return _operator_action(_workspace.command_result(
            "cold-prune", verified["status"], workspace=workspace,
            envelope_id=envelope_id,
            pruned={"removed": False, "reason": verified["status"]},
            detail=f"{verified['detail']}; the hot copy was KEPT, because a "
                   "message is never pruned on the strength of an unverified "
                   "archive"))
    office = workspace.office(clock=clock)
    hot_state = office.bundle_state(envelope_id)
    if hot_state not in ("UNREAD", "READ", "BOTH"):
        return _workspace.command_result(
            "cold-prune", "PRUNED_ABSENT", workspace=workspace,
            envelope_id=envelope_id,
            pruned={"removed": False, "reason": "NO_HOT_COPY", "hot_state": hot_state},
            detail=f"{envelope_id} has no hot bundle to remove ({hot_state})")
    removed = []
    for state_dir, bundle in (("inbox", office.inbox_bundle(envelope_id)),
                              ("read", office.read_bundle(envelope_id))):
        if not bundle.is_dir():
            continue
        try:
            _remove_tree(bundle)
        except OSError as exc:
            return _operator_action(_workspace.command_result(
                "cold-prune", COLD_WRITE_FAILED, workspace=workspace,
                envelope_id=envelope_id,
                pruned={"removed": False, "reason": type(exc).__name__},
                detail=f"hot {state_dir} copy of {envelope_id} could not be "
                       f"removed ({type(exc).__name__}); the cold copy is verified "
                       "and the message is still recoverable"))
        removed.append(state_dir)
    manifest["hot_removed"] = True
    _write_manifest(workspace, manifest)
    return _workspace.command_result(
        "cold-prune", PRUNED, workspace=workspace, envelope_id=envelope_id,
        pruned={"removed": True, "hot_dirs": removed, "index_row": True},
        detail=f"hot {', '.join(removed) or 'copy'} removed for {envelope_id}; the "
               "verified cold copy and the discoverability row remain, so "
               "restore by id brings it back")


def _remove_tree(path: Path) -> None:
    """Remove a bundle directory. Bounded: a bundle holds only its own files."""
    shutil.rmtree(path)


def prune(workspace, *, retention=None, clock=None, limit: Optional[int] = None,
          dry_run: bool = False) -> dict:
    """Apply the retention policy across the whole archive."""
    policy = retention or DEFAULT_RETENTION
    records = read_records(workspace)
    decision = select_for_prune(records, policy, now=(clock or _utc_now)())
    prunable = decision["prunable"]
    if limit is not None:
        prunable = prunable[:max(0, limit)]
    pruned, retained, failed = [], dict(decision["retained"]), []
    if dry_run:
        return _workspace.command_result(
            "cold-prune", "PRUNED_NONE", workspace=workspace,
            cold={"considered": decision["considered"],
                  "prunable": len(prunable), "policy": _policy_fields(policy)},
            pruned={"removed": [], "dry_run": True},
            retained=retained, failed=failed,
            detail=f"dry run: {len(prunable)} of {decision['considered']} cold "
                   f"record(s) would leave hot storage; nothing was removed")
    for envelope_id in prunable:
        manifest = read_record(workspace, envelope_id)
        if manifest is None:
            failed.append({"envelope_id": envelope_id, "reason": NOT_COLD})
            continue
        outcome = _prune_bundle(workspace, envelope_id, manifest, clock=clock)
        if outcome["status"] == PRUNED:
            pruned.append(envelope_id)
        else:
            retained[envelope_id] = outcome["pruned"].get("reason", outcome["status"])
            if not outcome["ok"]:
                failed.append({"envelope_id": envelope_id,
                               "reason": outcome["status"]})
    result = _workspace.command_result(
        "cold-prune", PRUNED if pruned else "PRUNED_NONE", workspace=workspace,
        cold={"considered": decision["considered"], "pruned": len(pruned),
              "policy": _policy_fields(policy)},
        pruned={"removed": pruned, "dry_run": False},
        retained=retained, failed=failed,
        detail=f"{len(pruned)} hot copy/copies removed, "
               f"{len(retained)} retained by policy, {len(failed)} failure(s)")
    if failed:
        _operator_action(result)
    return result


def _policy_fields(policy: RetentionPolicy) -> dict:
    return {
        "older_than_seconds": policy.older_than.total_seconds()
        if policy.older_than is not None else None,
        "max_count": policy.max_count,
        "max_bytes": policy.max_bytes,
        "kinds": sorted(policy.kinds) if policy.kinds is not None else None,
        "pin_kinds": sorted(policy.pin_kinds),
    }


def retention_policy(older_than_seconds=None, max_count=None, max_bytes=None,
                     kinds=None) -> RetentionPolicy:
    """Build a policy from CLI-shaped values, with the pinned class kept."""
    if kinds is not None:
        kinds = frozenset(kinds)
    return RetentionPolicy(
        older_than=timedelta(seconds=older_than_seconds)
        if older_than_seconds is not None else None,
        max_count=max_count, max_bytes=max_bytes, kinds=kinds)


# ---- restore --------------------------------------------------------------


def restore(workspace, envelope_id: str, *, clock=None, opener=None) -> dict:
    """Put a cold record back into hot storage, idempotently.

    Restoring re-publishes the canonical bytes, so a second restore of the same
    id converges instead of duplicating, and a restore of an id that is already
    hot with the same bytes changes nothing.
    """
    _eid_hex(envelope_id)
    manifest = read_record(workspace, envelope_id)
    if manifest is None:
        return _workspace.command_result(
            "cold-restore", NOT_COLD, workspace=workspace, envelope_id=envelope_id,
            detail=f"{envelope_id} is not in the cold archive; nothing was restored")
    verified = verify_record(workspace, envelope_id, clock=clock,
                             opener=opener if opener is not None
                             else _default_opener(workspace))
    if verified["status"] != VERIFIED:
        result = dict(verified)
        result["command"] = "cold-restore"
        result["detail"] = (f"{verified['detail']}; the cold copy was NOT "
                            "restored, because restoring unverifiable bytes would "
                            "repopulate hot storage with a corruption")
        return result
    base = record_path(workspace, envelope_id)
    raw = (base / CONTAINER_NAME).read_bytes()
    receipt_bytes = (base / RECEIPT_NAME).read_bytes()

    office = workspace.office(clock=clock)
    state_dir = postoffice.READ if manifest["hot_state"] == "READ" else postoffice.INBOX
    files = {CONTAINER_NAME: raw, RECEIPT_NAME: receipt_bytes}
    target = office.mail_root / state_dir / office.seat
    try:
        status = postoffice._publish_dir(target, _eid_hex(envelope_id), files,
                                         conflict_code=postoffice.ENVELOPE_ID_CONFLICT)
    except (OSError, SailangError) as exc:
        code = exc.code if isinstance(exc, SailangError) else COLD_WRITE_FAILED
        detail = exc.detail if isinstance(exc, SailangError) \
            else f"hot restore failed ({type(exc).__name__})"
        return _operator_action(_workspace.command_result(
            "cold-restore", code, workspace=workspace, envelope_id=envelope_id,
            detail=f"{detail}; the cold copy is intact"))
    if status == postoffice.IDEMPOTENT:
        manifest["hot_removed"] = False
        _write_manifest(workspace, manifest)
        return _workspace.command_result(
            "cold-restore", ALREADY_HOT, workspace=workspace,
            envelope_id=envelope_id,
            detail=f"{envelope_id} was already hot with identical bytes; restore "
                   "is idempotent and nothing was duplicated")
    row = manifest.get("index_row") or {}
    if row:
        try:
            header = envelope.parse_header(raw)
            office.ensure_index_row(header, envelope_id, manifest["receipt_at"])
        except SailangError:
            pass
    manifest["hot_removed"] = False
    _write_manifest(workspace, manifest)
    return _workspace.command_result(
        "cold-restore", RESTORED, workspace=workspace, envelope_id=envelope_id,
        cold=manifest,
        detail=f"{envelope_id} restored to {state_dir} from its verified cold copy")


# ---- search ---------------------------------------------------------------


def search(workspace, *, text=None, kinds=None, since=None, until=None,
           limit: int = _DEFAULT_SEARCH_LIMIT, semantic: bool = False) -> dict:
    """Metadata search over the archive, always; semantic search, never.

    Every hit points back at the canonical source: the `ENVELOPE_ID`, the cold
    record path, and whether `restore` would bring the body back. A search result
    is a locator, never a copy of the content, so nothing here decrypts and
    nothing here stores a plaintext derivative.
    """
    if semantic:
        return _refusal(_workspace.command_result(
            "cold-search", SEMANTIC_SEARCH_UNSUPPORTED, workspace=workspace,
            search_mode="METADATA_ONLY", hits=[],
            detail="semantic search is not available: this archive stores no "
                   "plaintext derivative, and building one is a declared policy "
                   "decision (COLD_PLAIN_DERIVATIVES) this build does not take"))
    if limit is not None and (not isinstance(limit, int) or limit < 1):
        _reject(BAD_RETENTION, "limit must be a positive int or None")
    ceiling = _MAX_SEARCH_LIMIT if limit is None else min(limit, _MAX_SEARCH_LIMIT)
    needle = text.lower() if isinstance(text, str) else None
    kind_filter = frozenset(kinds) if kinds is not None else None
    hits, scanned, truncated = [], 0, False
    for manifest in read_records(workspace):
        scanned += 1
        row = manifest.get("index_row") or {}
        if kind_filter is not None and row.get("kind") not in kind_filter:
            continue
        if needle is not None:
            haystack = " ".join(str(row.get(field, "")) for field in
                                ("topic", "from", "to", "kind", "created"))
            if needle not in haystack.lower():
                continue
        if since is not None and _parse_utc(manifest["archived_at"]) < since:
            continue
        if until is not None and _parse_utc(manifest["archived_at"]) > until:
            continue
        if len(hits) >= ceiling:
            truncated = True
            break
        hits.append({
            "envelope_id": manifest["envelope_id"],
            "kind": row.get("kind"),
            "topic": row.get("topic"),
            "from": row.get("from"),
            "to": row.get("to"),
            "created": row.get("created"),
            "archived_at": manifest["archived_at"],
            "pinned": manifest["pinned"],
            "hot_removed": manifest["hot_removed"],
            "restorable": manifest["hot_removed"],
            "canonical_source": str(record_path(workspace, manifest["envelope_id"])),
            "ledger_message_id": manifest.get("ledger_message_id"),
        })
    return _workspace.command_result(
        "cold-search", "SEARCHED", workspace=workspace,
        search_mode="METADATA_ONLY",
        cold={"scanned": scanned, "matched": len(hits), "truncated": truncated},
        hits=hits,
        detail=f"{len(hits)} metadata hit(s) over {scanned} cold record(s); "
               "each points at its canonical source and no plaintext derivative "
               "was read or written")


# ---- health ---------------------------------------------------------------


def health(workspace) -> dict:
    """Whether the archive is intact, and which records are not.

    Corruption is named per record. An archive that cannot be listed at all is
    UNKNOWN and never a clean zero, for the same reason the delivery ledger is:
    "I found nothing" and "I could not look" are different answers and only one
    of them is a reason to delete a mailbox.
    """
    base = items_root(workspace)
    if not base.exists():
        return _workspace.command_result(
            "cold-health", _HEALTHY, workspace=workspace,
            cold={"state": _HEALTHY, "reason": "NO_ARCHIVE", "records": 0,
                  "corrupt": [], "missing": []},
            detail="no cold archive exists; there is nothing to verify and "
                   "nothing at risk")
    try:
        entries = sorted(entry.name for entry in base.iterdir())
    except OSError as exc:
        result = _workspace.command_result(
            "cold-health", COLD_UNREADABLE, workspace=workspace,
            cold={"state": _UNKNOWN, "reason": type(exc).__name__, "records": 0,
                  "corrupt": [], "missing": []},
            detail=f"the cold archive cannot be listed ({type(exc).__name__}); "
                   "this is UNKNOWN, not an empty archive")
        return _operator_action(result)
    corrupt, missing, verified_count = [], [], 0
    for name in entries:
        if name.startswith("."):
            continue
        envelope_id = f"sha256:{name}"
        path = base / name
        try:
            manifest = read_record(workspace, envelope_id)
        except SailangError as exc:
            corrupt.append({"envelope_id": envelope_id, "reason": exc.code,
                            "detail": exc.detail})
            continue
        if manifest is None:
            missing.append(envelope_id)
            continue
        outcome = verify_record(workspace, envelope_id)
        if outcome["status"] == VERIFIED:
            verified_count += 1
        else:
            corrupt.append({"envelope_id": envelope_id,
                            "reason": outcome["status"],
                            "detail": outcome["detail"]})
    state = _HEALTHY if not corrupt and not missing else _DEGRADED
    result = _workspace.command_result(
        "cold-health", state, workspace=workspace,
        cold={"state": state, "records": len(entries), "verified": verified_count,
              "corrupt": corrupt, "missing": missing},
        detail=f"{verified_count} of {len(entries)} cold record(s) verified; "
               f"{len(corrupt)} corrupt, {len(missing)} missing; corruption is "
               "visible and nothing was repaired or removed")
    if corrupt or missing:
        _operator_action(result)
    return result


__all__ = [
    "ALREADY_COLD",
    "ALREADY_HOT",
    "ARCHIVED",
    "BAD_RETENTION",
    "COLD_CORRUPT",
    "COLD_DIR",
    "COLD_HASH_MISMATCH",
    "COLD_INCOMPLETE",
    "COLD_MANIFEST_INVALID",
    "COLD_NOT_HOT",
    "COLD_SCHEMA",
    "COLD_UNREADABLE",
    "COLD_UNKNOWN_ID",
    "COLD_VERIFY_FAILED",
    "COLD_WRITE_FAILED",
    "DEFAULT_RETENTION",
    "PINNED_KINDS",
    "PRUNED",
    "REOPEN_OPENED",
    "REOPEN_SKIPPED",
    "RESTORED",
    "RetentionPolicy",
    "SEMANTIC_SEARCH_UNSUPPORTED",
    "VERIFIED",
    "archive",
    "cold_root",
    "health",
    "items_root",
    "prune",
    "read_record",
    "read_records",
    "record_path",
    "restore",
    "retention_policy",
    "search",
    "select_for_prune",
    "verify_record",
]