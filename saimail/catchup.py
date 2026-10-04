"""Downtime recovery and coalesced catch-up (FUTURE GATE Wave 4).

Defect class this module eliminates: a recovery that replays everything. A host
that was down for six hours comes back and either does nothing -- leaving owed
work silently owed forever -- or retries every missed opportunity one at a
time, which is the same work N times over and looks exactly like an attack. Both
are wrong for the same reason: nobody ever wrote down what was owed.

So this module writes it down, and coalesces it. Five surfaces owe work after
downtime -- the outbox, the ledger's projections, the Post Office, leftover
locks and staging residue, and deferred trust checks -- and each is enumerated
into ONE queue entry per *logical* job, not per attempt or per missed tick.
Observing the same owed delivery a hundred times over a hundred missed windows
still produces one entry with one attempt counter, because what would be
replayed is the same idempotent delivery and the whole point is not to replay it.

Three rules the rest of the design follows from:

1. **Nothing is dropped.** A job that cannot run now becomes PARKED with a named
   reason and a cooldown, never a silent removal. An unreachable peer that
   vanishes from a queue is indistinguishable from one that was never owed.
2. **Nothing is invented.** The outage cause is reported as `UNKNOWN` unless a
   caller supplies evidence for it. A recovery notice that guesses "the host
   crashed" from a gap in a timestamp is telling the operator a story, and a
   recovery notice is exactly what they will act on.
3. **The system informs, the agent reasons.** `run` executes only the classes
   whose correct action is mechanical -- an idempotent send, a reconcile from
   canonical bytes -- and parks the rest with its evidence attached. It never
   deletes a staging directory or flips a trust verdict on its own.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sailang import SailangError
from saimail import canary as _canary
from saimail import ledger as _ledger
from saimail import outbox as _outbox
from saimail import postoffice
from saimail import trust as _trust
from saimail import workspace as _workspace

CATCHUP_SCHEMA = "SAIMAIL_CATCHUP_1"
CATCHUP_VERSION = 1
CATCHUP_DIR = "catchup"
SERVICE_NAME = "service.json"
QUEUE_NAME = "queue.json"
LOCK_NAME = "queue.lock"

QUEUED = "QUEUED"
IN_FLIGHT = "IN_FLIGHT"
PARKED = "PARKED"
DONE = "DONE"
SUPERSEDED = "SUPERSEDED"
STATES = (QUEUED, IN_FLIGHT, PARKED, DONE, SUPERSEDED)

DELIVERY = "DELIVERY"
RECONCILE = "RECONCILE"
RESIDUE = "RESIDUE"
TRUST = "TRUST"
KINDS = (DELIVERY, RECONCILE, RESIDUE, TRUST)

#: The only two classes `run` acts on. Both are idempotent by construction: the
#: outbox is keyed by idempotency key and the ledger repairs from canonical
#: bytes. RESIDUE needs a judgement about concurrent writers and TRUST needs a
#: human, so both park with evidence instead.
EXECUTABLE = (DELIVERY, RECONCILE)

#: How long an IN_FLIGHT claim survives a process that died holding it. Past
#: this the entry is re-claimable and the reappearance is counted, because a
#: crashed catch-up that silently stays IN_FLIGHT forever is indistinguishable
#: from one that is still working.
IN_FLIGHT_TIMEOUT_SECONDS = 900
STALE_RESIDUE_SECONDS = 300
COOLDOWN_BASE_SECONDS = 60
COOLDOWN_MAX_SECONDS = 3600
DEFAULT_CLAIM_LIMIT = 8
MAX_CLAIM_LIMIT = 64

PEER_UNREACHABLE = "PEER_UNREACHABLE"
DELIVERY_FAILED = "DELIVERY_FAILED"
NOT_DUE = "NOT_DUE"
NEEDS_SIGNING_KEY = "NEEDS_SIGNING_KEY"
STILL_OWED = "STILL_OWED"
TRUST_NEEDS_REVIEW = "TRUST_NEEDS_REVIEW"
RESIDUE_NEEDS_REVIEW = "RESIDUE_NEEDS_REVIEW"
STALE_CLAIM_REAPED = "STALE_CLAIM_REAPED"
UNKNOWN_CAUSE = "UNKNOWN"

QUEUE_UNREADABLE = "CATCHUP_QUEUE_UNREADABLE"
QUEUE_WRITE_FAILED = "CATCHUP_QUEUE_WRITE_FAILED"
QUEUE_LOCK_TIMEOUT = "CATCHUP_QUEUE_LOCK_TIMEOUT"
BAD_INPUT = _workspace.BAD_INPUT
UNKNOWN_ENTRY = "CATCHUP_UNKNOWN_ENTRY"

OPERATOR_ACTION_CODES = frozenset({
    QUEUE_UNREADABLE, QUEUE_WRITE_FAILED, QUEUE_LOCK_TIMEOUT,
})

_ENTRY_KEYS = frozenset({
    "entry_id", "kind", "logical_id", "peer", "topic", "state", "attempts",
    "first_owed_at", "last_owed_at", "next_attempt_at", "claimed_at",
    "parked_reason", "detail", "evidence",
})

#: Every lock file this project creates. Lets a real lock be told apart from an
#: unrelated `.lock` a caller happens to keep inside the workspace.
_LOCK_NAMES = frozenset({postoffice.INDEX_LOCK_NAME, postoffice.LIFECYCLE_LOCK_NAME,
                         _outbox.LOCK_NAME, _ledger.LOCK_NAME, _trust.LOCK_NAME})

#: An observed fact, not a job. Deliberately a different shape from
#: `_ENTRY_KEYS`: owed work and things worth knowing are different records, and a
#: queue that mixes them cannot tell an operator which is which.
_RESIDUE_FIELDS = frozenset({"path", "age_seconds", "free", "remedy", "detail"})


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _canonical_json(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _now(clock) -> str:
    return (clock or postoffice.utc_now)()


def _parse(text, *, code: str = QUEUE_UNREADABLE):
    return postoffice._parse_utc(text, code=code)


def _format(instant) -> str:
    return postoffice._format_utc(instant)


def _operator_action(result: dict) -> dict:
    result["ok"] = False
    result["operator_action_required"] = True
    return result


# ---- storage --------------------------------------------------------------


def catchup_root(workspace) -> Path:
    return Path(getattr(workspace, "root", workspace)) / CATCHUP_DIR


def _service_path(workspace) -> Path:
    return catchup_root(workspace) / SERVICE_NAME


def _queue_path(workspace) -> Path:
    return catchup_root(workspace) / QUEUE_NAME


def _lock(workspace):
    root = catchup_root(workspace)
    root.mkdir(parents=True, exist_ok=True)
    return postoffice._OsFileLock(root / LOCK_NAME, busy_code=QUEUE_LOCK_TIMEOUT)


def _read_json(path: Path, empty: dict, *, what: str) -> dict:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return dict(empty)
    except OSError as exc:
        _reject(QUEUE_UNREADABLE,
                f"{what} cannot be read ({type(exc).__name__})")
    try:
        payload = json.loads(raw.decode("utf-8"),
                             object_pairs_hook=postoffice._duplicate_guard)
    except SailangError:
        raise
    except (UnicodeDecodeError, ValueError) as exc:
        _reject(QUEUE_UNREADABLE, f"{what} is not canonical JSON: {exc}")
    if not isinstance(payload, dict) or payload.get("schema") != CATCHUP_SCHEMA \
            or payload.get("version") != CATCHUP_VERSION:
        _reject(QUEUE_UNREADABLE,
                f"{what} is not a {CATCHUP_SCHEMA} v{CATCHUP_VERSION} record")
    return payload


def _write_json(path: Path, payload: dict) -> None:
    postoffice._write_complete(path, _canonical_json(payload))


def read_service(workspace) -> dict:
    """The last successful service state, or an honest empty one.

    An unreadable service state is UNREADABLE, never "no downtime": the two
    answers send an operator to opposite places.
    """
    try:
        stored = _read_json(_service_path(workspace), {}, what="catch-up service state")
    except SailangError as exc:
        return {"schema": CATCHUP_SCHEMA, "version": CATCHUP_VERSION,
                "last_tick_at": None, "ticks": 0, "recoveries": 0,
                "read_state": QUEUE_UNREADABLE, "reason": exc.code}
    return {
        "schema": CATCHUP_SCHEMA, "version": CATCHUP_VERSION,
        "last_tick_at": stored.get("last_tick_at"),
        "ticks": stored.get("ticks", 0),
        "recoveries": stored.get("recoveries", 0),
        "read_state": "OK",
        "reason": None,
    }


def record_tick(workspace, *, clock=None, peers=None) -> dict:
    """Record one successful service pass. This is what a gap is measured from."""
    with _lock(workspace):
        state = read_service(workspace)
        if state["read_state"] != "OK":
            _reject(QUEUE_UNREADABLE,
                    "the service state is unreadable, so a tick cannot be recorded "
                    f"against it ({state['reason']})")
        now = _now(clock)
        payload = {"schema": CATCHUP_SCHEMA, "version": CATCHUP_VERSION,
                   "last_tick_at": now, "ticks": state["ticks"] + 1,
                   "recoveries": state["recoveries"], "peers": dict(peers or {})}
        try:
            _write_json(_service_path(workspace), payload)
        except OSError as exc:
            _reject(QUEUE_WRITE_FAILED,
                    f"the service state could not be written "
                    f"({type(exc).__name__})")
    return _workspace.command_result(
        "catchup-tick", "OK", workspace=workspace, service=payload,
        detail=f"service pass recorded at {now}; {payload['ticks']} tick(s) total")


def note_recovery(workspace, *, clock=None) -> dict:
    """Count a recovery, so the history says how often this happened."""
    with _lock(workspace):
        state = read_service(workspace)
        if state["read_state"] != "OK":
            _reject(QUEUE_UNREADABLE, "the service state is unreadable")
        payload = {"schema": CATCHUP_SCHEMA, "version": CATCHUP_VERSION,
                   "last_tick_at": state["last_tick_at"], "ticks": state["ticks"],
                   "recoveries": state["recoveries"] + 1, "peers": {}}
        _write_json(_service_path(workspace), payload)
    return _workspace.command_result(
        "catchup-tick", "OK", workspace=workspace, service=payload,
        detail=f"recovery counted; {payload['recoveries']} recovery(s) recorded")


# ---- gap detection --------------------------------------------------------


def detect_gaps(workspace, *, clock=None) -> dict:
    """How long since the last successful pass, and nothing more than that.

    A duration is measured from the recorded tick. A *cause* is not derivable
    from a duration, so `outage_cause` is `UNKNOWN` unless the caller supplies
    evidence, and the evidence list says so out loud rather than staying empty
    for a reader to interpret.
    """
    state = read_service(workspace)
    if state["read_state"] != "OK":
        result = _workspace.command_result(
            "catchup-detect", QUEUE_UNREADABLE, workspace=workspace,
            gap={"state": QUEUE_UNREADABLE, "reason": state["reason"],
                 "downtime_seconds": None, "outage_cause": UNKNOWN_CAUSE,
                 "evidence": []},
            detail="the service state cannot be read, so the size of the gap is "
                   "UNKNOWN -- which is not the same as no gap")
        return _operator_action(result)
    now = _parse(_now(clock))
    last_tick = state["last_tick_at"]
    if last_tick is None:
        return _workspace.command_result(
            "catchup-detect", "OK", workspace=workspace,
            gap={"state": "FIRST_OBSERVATION", "last_tick_at": None,
                 "downtime_seconds": None, "ticks": state["ticks"],
                 "outage_cause": UNKNOWN_CAUSE, "evidence": []},
            detail="no tick has ever been recorded, so there is no gap to measure "
                   "and no outage to attribute; this is the first observation")
    seconds = int((now - _parse(last_tick)).total_seconds())
    return _workspace.command_result(
        "catchup-detect", "OK", workspace=workspace,
        gap={"state": "DOWN" if seconds > 0 else "CURRENT",
             "last_tick_at": last_tick, "observed_at": _now(clock),
             "downtime_seconds": max(0, seconds), "ticks": state["ticks"],
             "recoveries": state["recoveries"],
             "outage_cause": UNKNOWN_CAUSE,
             "evidence": ["DOWNTIME_DURATION_ONLY"]},
        detail=f"{max(0, seconds)}s since the last successful pass; the cause is "
               f"{UNKNOWN_CAUSE}, because a duration is not evidence of a cause")


# ---- queue storage --------------------------------------------------------


def read_queue(workspace) -> dict:
    payload = _read_json(_queue_path(workspace), {}, what="catch-up queue")
    entries = payload.get("entries")
    if entries is None:
        payload["entries"] = {}
        return payload
    if not isinstance(entries, dict):
        _reject(QUEUE_UNREADABLE, "the catch-up queue is not an ENTRY_ID map")
    for entry_id, entry in entries.items():
        if not isinstance(entry, dict) or set(entry) != _ENTRY_KEYS \
                or entry.get("entry_id") != entry_id:
            _reject(QUEUE_UNREADABLE,
                    f"catch-up entry {entry_id!r} deviates from the contract")
    residue = payload.setdefault("residue", [])
    if not isinstance(residue, list) or any(
            not isinstance(item, dict) or set(item) != _RESIDUE_FIELDS
            for item in residue):
        _reject(QUEUE_UNREADABLE, "the observed residue is not a FACT list")
    return payload


def _write_queue(workspace, payload: dict) -> None:
    # The schema stamp is written here, not trusted from the caller. The empty
    # default `read_queue` hands back for a first run carries no schema, so
    # writing that payload back verbatim produces a file this module then
    # refuses to read -- a queue permanently unreadable from its own first write.
    payload["schema"] = CATCHUP_SCHEMA
    payload["version"] = CATCHUP_VERSION
    try:
        _write_json(_queue_path(workspace), payload)
    except OSError as exc:
        _reject(QUEUE_WRITE_FAILED,
                f"the catch-up queue could not be written ({type(exc).__name__})")


def _entry_id(kind: str, logical_id: str) -> str:
    """The coalescing key. One logical job, one entry, forever.

    Deliberately NOT derived from an attempt count or a tick: two observations
    of the same owed delivery are the same job, and treating them as two is
    what turns a long downtime into a replay storm.
    """
    return f"{kind}:{logical_id}"


def _new_entry(kind: str, logical_id: str, now: str, **fields) -> dict:
    entry = {"entry_id": _entry_id(kind, logical_id), "kind": kind,
             "logical_id": logical_id, "peer": None, "topic": None,
             "state": QUEUED, "attempts": 0, "first_owed_at": now,
             "last_owed_at": now, "next_attempt_at": None, "claimed_at": None,
             "parked_reason": None, "detail": "", "evidence": {}}
    entry.update(fields)
    return entry


#: Fields that describe WHAT is owed. Refreshed on every plan pass.
_DESCRIPTION_FIELDS = ("peer", "topic", "detail", "evidence")
#: Fields that describe the queue's own history of the job. Applied only when
#: the entry is created -- refreshing them on re-observation would silently
#: forgive a retry cooldown and make a repeatedly-failing job look fresh.
_INITIAL_FIELDS = ("state", "attempts", "parked_reason", "next_attempt_at")


def _observe(entries: dict, kind: str, logical_id: str, now: str,
             **fields) -> tuple:
    """Record that a job is still owed. Returns `(entry, created)`.

    Re-observing an entry NEVER increments `attempts`, never resets its
    cooldown and never revives a parked job. Attempts count real attempts and a
    cooldown counts down from the last failure; a plan pass that overwrote
    either would let a long downtime turn into an unbounded retry loop.
    """
    entry_id = _entry_id(kind, logical_id)
    existing = entries.get(entry_id)
    description = {name: value for name, value in fields.items()
                   if name in _DESCRIPTION_FIELDS}
    initial = {name: value for name, value in fields.items()
               if name in _INITIAL_FIELDS}
    if existing is not None:
        if existing["state"] in (DONE, SUPERSEDED):
            return existing, False
        existing["last_owed_at"] = now
        existing.update(description)
        return existing, False
    entry = _new_entry(kind, logical_id, now, **description, **initial)
    entries[entry_id] = entry
    return entry, True


# ---- owed-work enumeration ------------------------------------------------


def _delivery_verdict(intent, peers) -> tuple:
    """``(park_reason)`` for one outbox intent, or ``None`` when it is settled.

    A delivery that is merely waiting to be retried is still OWED -- the message
    did not arrive, and the queue is where an operator looks for that fact. So
    the test is the recorded failure, not the intent's state: a transient IO
    error, or an alias nobody has registered, means the PEER is the problem, and
    that sends an operator somewhere different from "the send failed".
    """
    if intent["state"] == _outbox.DELIVERED:
        return None
    failure = intent.get("failure") or intent.get("last_error")
    # The whole TRANSIENT family -- recipient offline, mailbox locks busy -- says
    # the far side is the problem, not the send.
    unreachable = (failure in _outbox.TRANSIENT_CODES
                   or intent.get("alias") not in peers)
    if unreachable:
        return PEER_UNREACHABLE
    if intent["state"] == _outbox.FAILED or failure:
        return DELIVERY_FAILED
    return None


def _owed_deliveries(workspace, now: str) -> list:
    """Outbox intents that are still owed, keyed by their idempotency key."""
    peers = workspace.peers
    owed = []
    for intent in _outbox._all_intents(workspace):
        reason = _delivery_verdict(intent, peers)
        if reason is None and intent["state"] == _outbox.DELIVERED:
            continue
        owed.append((DELIVERY, intent["key_id"], {
            "peer": intent.get("alias"),
            "topic": intent.get("topic"),
            "detail": intent.get("failure") or intent.get("failure_reason") or "",
            "evidence": {"intent_state": intent["state"],
                         "outbox_state": _outbox._status_for(intent),
                         "alias_registered": intent.get("alias") in peers,
                         "last_error": intent.get("last_error")},
            "state": PARKED if reason else QUEUED,
            "attempts": int(intent.get("attempts") or 0),
            "parked_reason": reason,
            "next_attempt_at": intent.get("next_attempt_at"),
        }))
    return owed


def _bundle_state(office, envelope_id: str):
    """``(state, error)``. An envelope id the Post Office cannot name is a
    finding, not a crash.

    The ledger does not police the shape of an ``envelope_id``, so one that is
    not `sha256:<64 hex>` reaches us from a record that was written in good
    faith. Letting it propagate would take down the whole planning pass over one
    bad row -- and the row is exactly the kind of thing the operator needs to
    see. So it is reported, and the entry it backs stays visible.
    """
    try:
        return office.bundle_state(envelope_id), None
    except SailangError as exc:
        return None, exc.code


def _owed_reconciles(workspace, now: str) -> list:
    """Ledger messages with an ENVELOPE_ID but no durable body on either side.

    Only a message the record does NOT say was delivered. A DELIVERED message
    lives in the RECEIVER's mailbox, not ours, so finding no local body for it is
    the normal state of a healthy send -- treating that as owed work would
    manufacture a permanent debt out of every successful delivery, which is the
    replay storm this module exists to prevent. What is genuinely owed is the
    crash window: an envelope the record committed and then never delivered.
    """
    try:
        events, state = _ledger.read_events(workspace)
    except SailangError:
        # An unreadable ledger owes nothing it can name. Reporting UNKNOWN
        # reconcile work for ids we cannot read would invent entries, and
        # `notice` already reports the unreadable ledger separately.
        return []
    if state == _ledger.STATE_UNREADABLE:
        return []
    office = workspace.office()
    owed = []
    for message in _ledger.fold(events)["messages"].values():
        envelope_id = message.get("envelope_id")
        if not envelope_id or message.get("state") == _ledger.DELIVERED:
            continue
        bundle, bad_id = _bundle_state(office, envelope_id)
        if bad_id is not None:
            owed.append((RECONCILE, envelope_id,
                         {"evidence": {"ledger_state": message["state"],
                                       "ledger_seq": message["seq"],
                                       "malformed": bad_id},
                          "detail": "the record names an envelope the Post Office "
                                    f"cannot address ({bad_id})"}))
            continue
        # EXPIRED is a deliberate tombstone, not an unfinished delivery.
        if bundle in ("UNREAD", "READ", "BOTH", "EXPIRED"):
            continue
        if office.read_index_row(envelope_id) is not None:
            continue
        owed.append((RECONCILE, envelope_id,
                     {"evidence": {"ledger_state": message["state"],
                                   "ledger_seq": message["seq"],
                                   "mailbox_state": bundle},
                      "detail": "the record names this envelope but no canonical "
                                "body or index row exists"}))
    return owed


def _observed_residue(workspace, now: str) -> list:
    """Lock files with no holder, reported as FACTS rather than as owed work.

    A free lock file is normal: `_OsFileLock` leaves the file behind on purpose,
    and the next writer reuses it. Nothing needs doing about it, so making it a
    queue entry would manufacture a permanent debt that never clears -- and a
    debt that never clears is a debt nobody can clear. An abandoned staging
    directory IS owed work (see `_owed_residue`); a lock file is a fact about
    the same interruption.
    """
    root = Path(workspace.root)
    facts = []
    for path in sorted(root.rglob("*.lock")):
        relative = path.relative_to(root).as_posix()
        if path.name not in _LOCK_NAMES or path.parent.name == CATCHUP_DIR:
            continue
        if not _lock_is_free(path):
            continue
        age = _age_seconds(path, now)
        if age is None or age < STALE_RESIDUE_SECONDS:
            continue
        facts.append({"path": relative, "age_seconds": age, "free": True,
                      "remedy": "NONE",
                      "detail": "no live writer holds this lock; the next one "
                                "reuses the same file, so nothing is owed"})
    return facts


def _owed_residue(workspace, now: str) -> list:
    """Staging directories an interrupted publish left behind.

    Probing is safe precisely because the OS releases a lock on process death:
    if this call acquires it, no live writer has it, and that IS the stale
    condition. Whether an abandoned staging directory can be cleaned is a
    judgement, not a fact, so the entry parks rather than deletes.
    """
    root = Path(workspace.root)
    owed = []
    for path in sorted(root.rglob("*.staging")):
        relative = path.relative_to(root).as_posix()
        age = _age_seconds(path, now)
        if age is None or age < STALE_RESIDUE_SECONDS:
            continue
        owed.append((RESIDUE, relative,
                     {"evidence": {"path": relative, "age_seconds": age,
                                   "kind": "STAGING"},
                      "detail": "an interrupted publish staging directory"}))
    return owed


def _lock_is_free(path: Path) -> bool:
    """True when nobody holds this lock, probed without ever blocking."""
    try:
        fd = os.open(path, os.O_RDWR)
    except OSError:
        return False
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        return True
    except OSError:
        return False
    finally:
        os.close(fd)


def _age_seconds(path: Path, now: str) -> Optional[int]:
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    mtime_instant = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return int((_parse(now) - mtime_instant).total_seconds())


def _owed_trust(workspace, now: str) -> list:
    """Peers whose trust verdict is not settled.

    An OBSERVED key nobody accepted, a ROTATION_PENDING key nothing
    authenticated, and an alias now resolving to different fingerprints are all
    decisions waiting for a person. They are enumerated so the queue says so,
    and `run` parks them rather than picking for the operator.
    """
    owed = []
    for alias in sorted(workspace.peers):
        try:
            verdict = _trust.decide(workspace, alias)
        except SailangError:
            continue
        state = verdict.get("state")
        if state in (None, _trust.TRUSTED):
            continue
        owed.append((TRUST, alias,
                     {"peer": alias,
                      "evidence": {"trust_state": state,
                                   "detail": verdict.get("detail")},
                      "detail": "trust is not settled for this alias"}))
    return owed


# ---- plan -----------------------------------------------------------------


def plan(workspace, *, clock=None) -> dict:
    """Enumerate owed work, coalesce it, and supersede what is already done.

    Idempotent: running it twice against unchanged state produces the same
    queue with no new entries and no new attempts. It is also the supersession
    point -- an owed job the current state already satisfies becomes SUPERSEDED
    with its evidence, which is how stale work stops being owed without anyone
    remembering to clear it.
    """
    now = _now(clock)
    with _lock(workspace):
        try:
            payload = read_queue(workspace)
        except SailangError as exc:
            result = _workspace.command_result(
                "catchup-plan", QUEUE_UNREADABLE, workspace=workspace,
                queue={"state": QUEUE_UNREADABLE, "reason": exc.code},
                detail=f"the catch-up queue cannot be read ({exc.code}); nothing "
                       "was planned, because planning onto an unreadable queue "
                       "would lose what it already knew")
            return _operator_action(result)
        entries = payload["entries"]
        owed = (_owed_deliveries(workspace, now)
                + _owed_reconciles(workspace, now)
                + _owed_residue(workspace, now)
                + _owed_trust(workspace, now))
        live = {(kind, logical) for kind, logical, _ in owed}
        created, superseded = 0, 0
        for kind, logical_id, fields in owed:
            _entry, fresh = _observe(entries, kind, logical_id, now, **fields)
            if fresh:
                created += 1
        for entry in list(entries.values()):
            if entry["state"] in (DONE, SUPERSEDED):
                continue
            if (entry["kind"], entry["logical_id"]) in live:
                continue
            # The job this entry described is no longer owed. That is the normal
            # case after a successful run or an out-of-band delivery, and it is
            # the only thing that may retire an entry.
            entry["state"] = SUPERSEDED
            entry["parked_reason"] = None
            entry["detail"] = "the condition that owed this work no longer holds"
            entry["evidence"] = dict(entry["evidence"], superseded_at=now)
            superseded += 1
        payload["updated_at"] = now
        payload["residue"] = _observed_residue(workspace, now)
        _write_queue(workspace, payload)
    view = _queue_view(payload, now=now)
    return _workspace.command_result(
        "catchup-plan", "OK", workspace=workspace, queue=view,
        planned={"observed": created, "superseded": superseded,
                 "ledger_readable": not _ledger_is_unreadable(workspace)},
        detail=f"{created} logical job(s) owed across {view['by_kind']} kind(s); "
               f"{superseded} stale entry/entries superseded by current state; "
               f"{view['totals'][QUEUED]} queued, {view['totals'][PARKED]} parked")


def _ledger_is_unreadable(workspace) -> bool:
    try:
        _events, state = _ledger.read_events(workspace)
    except SailangError:
        return True
    return state == _ledger.STATE_UNREADABLE


# ---- the visible queue ----------------------------------------------------


def _queue_view(payload: dict, *, now=None, include_test_data: bool = True) -> dict:
    entries = list(payload.get("entries", {}).values())
    entries, excluded = _canary.filter_items(entries,
                                              include_test_data=include_test_data,
                                              key="peer")
    totals = {state: 0 for state in STATES}
    by_kind = {}
    oldest, attempts = None, 0
    now_text = now
    for entry in entries:
        totals[entry["state"]] = totals.get(entry["state"], 0) + 1
        by_kind[entry["kind"]] = by_kind.get(entry["kind"], 0) + 1
        attempts += entry["attempts"]
        if entry["state"] in (DONE, SUPERSEDED):
            continue
        if oldest is None or entry["first_owed_at"] < oldest:
            oldest = entry["first_owed_at"]
    oldest_seconds = None
    if oldest is not None and now_text is not None:
        oldest_seconds = int((_parse(now_text) - _parse(oldest)).total_seconds())
    live = [entry for entry in entries if entry["state"] in (QUEUED, IN_FLIGHT, PARKED)]
    live.sort(key=lambda item: (item["first_owed_at"], item["entry_id"]))
    return {
        "schema": CATCHUP_SCHEMA,
        "totals": totals,
        "residue": list(payload.get("residue", [])),
        "by_kind": by_kind,
        "attempts": attempts,
        "oldest_owed_at": oldest,
        "oldest_owed_seconds": oldest_seconds,
        "entries": live,
        "retired": len(entries) - len(live),
        "excluded_test_data": excluded,
    }


def _include_test_data(workspace, include_test_data) -> bool:
    """The mailbox decides its own default; see `canary.visible_to`."""
    return _canary.visible_to(workspace, include_test_data)


def queue(workspace, *, clock=None, include_test_data=None) -> dict:
    """The visible queue: queued, in-flight, parked, completed, attempts, oldest.

    `retired` counts DONE and SUPERSEDED so a queue that is genuinely empty is
    visibly empty rather than indistinguishable from one that was never built.
    """
    try:
        payload = read_queue(workspace)
    except SailangError as exc:
        result = _workspace.command_result(
            "catchup-queue", QUEUE_UNREADABLE, workspace=workspace,
            queue={"state": QUEUE_UNREADABLE, "reason": exc.code},
            detail=f"the catch-up queue cannot be read ({exc.code}); an "
                   "unreadable queue is not an empty one")
        return _operator_action(result)
    now = _now(clock)
    view = _queue_view(payload, now=now,
                       include_test_data=_include_test_data(workspace,
                                                            include_test_data))
    detail = (f"{view['totals'][QUEUED]} queued, {view['totals'][IN_FLIGHT]} in "
              f"flight, {view['totals'][PARKED]} parked, "
              f"{view['totals'][DONE]} completed, "
              f"{view['totals'][SUPERSEDED]} superseded, "
              f"{view['retired']} retired; oldest owed "
              f"{view['oldest_owed_seconds']}s")
    if view["excluded_test_data"]:
        detail += (f"; {view['excluded_test_data']} test-data entry/entries hidden "
                   "(pass --include-test-data to see them)")
    return _workspace.command_result(
        "catchup-queue", "OK", workspace=workspace, queue=view,
        excluded_test_data=view["excluded_test_data"], detail=detail)


# ---- claim / complete / park ---------------------------------------------


def _cooldown(attempts: int) -> timedelta:
    seconds = min(COOLDOWN_BASE_SECONDS * 2 ** max(attempts - 1, 0),
                  COOLDOWN_MAX_SECONDS)
    return timedelta(seconds=seconds)


def claim(workspace, *, limit: int = DEFAULT_CLAIM_LIMIT, clock=None) -> dict:
    """Take at most `limit` due entries. Bounded in-flight is the whole point.

    An entry is claimable when it is QUEUED, or PARKED with its cooldown
    elapsed. A crashed claim is reaped after `IN_FLIGHT_TIMEOUT_SECONDS` and
    counted, so a catch-up interrupted by a restart resumes instead of sticking.
    """
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        _reject(BAD_INPUT, "limit is a positive integer")
    limit = min(limit, MAX_CLAIM_LIMIT)
    now = _now(clock)
    with _lock(workspace):
        payload = read_queue(workspace)
        entries = payload["entries"]
        claimed, reaped = [], []
        for entry in sorted(entries.values(),
                            key=lambda item: (item["first_owed_at"],
                                              item["entry_id"])):
            if len(claimed) >= limit:
                break
            if entry["state"] == IN_FLIGHT:
                age = _seconds_since(entry["claimed_at"], now)
                if age is None or age < IN_FLIGHT_TIMEOUT_SECONDS:
                    continue
                entry["state"] = QUEUED
                entry["parked_reason"] = STALE_CLAIM_REAPED
                entry["claimed_at"] = None
                reaped.append(entry["entry_id"])
            if entry["state"] not in (QUEUED, PARKED):
                continue
            if entry["next_attempt_at"] and \
                    _parse(entry["next_attempt_at"]) > _parse(now):
                continue
            entry["state"] = IN_FLIGHT
            entry["attempts"] += 1
            entry["claimed_at"] = now
            entry["parked_reason"] = None
            claimed.append(entry)
        payload["updated_at"] = now
        _write_queue(workspace, payload)
    return _workspace.command_result(
        "catchup-claim", "OK", workspace=workspace,
        claimed=[_public(entry) for entry in claimed],
        counts={"claimed": len(claimed), "reaped": len(reaped),
                "limit": limit},
        detail=f"{len(claimed)} entry/entries in flight (limit {limit}); "
               f"{len(reaped)} stale claim(s) reaped after "
               f"{IN_FLIGHT_TIMEOUT_SECONDS}s")


def _seconds_since(text, now: str) -> Optional[int]:
    if not text:
        return None
    return int((_parse(now) - _parse(text)).total_seconds())


def complete(workspace, entry_id: str, *, detail: str = "", clock=None) -> dict:
    with _lock(workspace):
        payload = read_queue(workspace)
        entry = _require_entry(payload, entry_id)
        entry["state"] = DONE
        entry["detail"] = detail or entry["detail"]
        entry["next_attempt_at"] = None
        entry["parked_reason"] = None
        entry["claimed_at"] = None
        payload["updated_at"] = _now(clock)
        _write_queue(workspace, payload)
    return _workspace.command_result(
        "catchup-complete", "OK", workspace=workspace, entry=_public(entry),
        detail=f"{entry_id} completed: {entry['detail'] or 'no detail recorded'}")


def park(workspace, entry_id: str, reason: str, *, detail: str = "",
         clock=None) -> dict:
    """Park an entry with a named reason and a cooldown. Never drop it.

    A parked entry is still in the queue and still counted. That is the
    difference between "this could not run now" and "this never existed".
    """
    if not isinstance(reason, str) or not reason:
        _reject(BAD_INPUT, "a parked entry needs a named reason")
    now = _now(clock)
    with _lock(workspace):
        payload = read_queue(workspace)
        entry = _require_entry(payload, entry_id)
        entry["state"] = PARKED
        entry["parked_reason"] = reason
        entry["detail"] = detail or entry["detail"]
        entry["claimed_at"] = None
        entry["next_attempt_at"] = _format(
            _parse(now) + _cooldown(entry["attempts"]))
        payload["updated_at"] = now
        _write_queue(workspace, payload)
    return _workspace.command_result(
        "catchup-park", "OK", workspace=workspace, entry=_public(entry),
        detail=f"{entry_id} parked as {reason} until {entry['next_attempt_at']}; "
               "it is still in the queue and was not dropped")


def _require_entry(payload: dict, entry_id: str) -> dict:
    entry = payload["entries"].get(entry_id)
    if entry is None:
        _reject(UNKNOWN_ENTRY, f"no catch-up entry {entry_id!r}")
    return entry


def _public(entry: dict) -> dict:
    return {name: entry[name] for name in sorted(_ENTRY_KEYS)}


# ---- execution ------------------------------------------------------------


def run(workspace, *, limit: int = DEFAULT_CLAIM_LIMIT, clock=None) -> dict:
    """Execute the mechanical classes; park the rest with evidence.

    DELIVERY goes through the durable outbox, which is already idempotency-
    keyed, and RECONCILE through the ledger, which repairs only from canonical
    bytes. Neither can be doubled by running this twice. RESIDUE and TRUST park:
    deleting residue needs a judgement about concurrent writers, and settling a
    trust verdict is the operator's, not the queue's.
    """
    claimed = claim(workspace, limit=limit, clock=clock)
    now = _now(clock)
    outcomes, parked = [], []
    reconcile_ran = False
    for entry in claimed["claimed"]:
        if entry["kind"] not in EXECUTABLE:
            park(workspace, entry["entry_id"],
                 TRUST_NEEDS_REVIEW if entry["kind"] == TRUST
                 else RESIDUE_NEEDS_REVIEW,
                 detail=f"the system informs, the agent reasons: {entry['detail']}",
                 clock=clock)
            parked.append(entry["entry_id"])
            continue
        if entry["kind"] == RECONCILE and not reconcile_ran:
            reconcile_ran = True
            _ledger.reconcile(workspace, clock=clock)
        verdict = _still_owed(workspace, entry)
        if verdict is None:
            complete(workspace, entry["entry_id"],
                     detail=f"{entry['kind']} satisfied by the current state",
                     clock=clock)
            outcomes.append({"entry_id": entry["entry_id"], "state": DONE})
            continue
        park(workspace, entry["entry_id"], verdict, clock=clock)
        parked.append(entry["entry_id"])
    return _workspace.command_result(
        "catchup-run", "OK", workspace=workspace,
        ran={"claimed": claimed["counts"]["claimed"],
             "reaped": claimed["counts"]["reaped"],
             "completed": len(outcomes), "parked": len(parked)},
        outcomes=outcomes, parked=parked, observed_at=now,
        detail=f"{len(outcomes)} job(s) completed, {len(parked)} parked with a "
               "named reason; nothing was dropped and nothing was replayed")


def _still_owed(workspace, entry: dict) -> Optional[str]:
    """Why this entry is still owed, or None when the current state settled it."""
    if entry["kind"] == DELIVERY:
        for intent in _outbox._all_intents(workspace):
            if intent["key_id"] != entry["logical_id"]:
                continue
            reason = _delivery_verdict(intent, workspace.peers)
            if reason is not None:
                return reason
            if getattr(workspace, "sender_private_key", None) is None:
                return NEEDS_SIGNING_KEY
            return NOT_DUE
        return None
    if entry["kind"] == RECONCILE:
        office = workspace.office()
        envelope_id = entry["logical_id"]
        bundle, bad_id = _bundle_state(office, envelope_id)
        if bad_id is not None:
            return STILL_OWED
        if bundle in ("UNREAD", "READ", "BOTH", "EXPIRED"):
            return None
        if office.read_index_row(envelope_id) is not None:
            return None
        return STILL_OWED
    return STILL_OWED


# ---- the notice -----------------------------------------------------------


def notice(workspace, *, clock=None, include_test_data=None) -> dict:
    """A recovery notice that states facts and nothing else.

    Facts are the gap duration, the counts, the attempts, the oldest owed age
    and the named park reasons. The cause is not a fact unless something
    recorded one, so it is reported as `UNKNOWN` with the reason it is unknown
    attached -- a notice that guessed would be the one thing an operator acts on
    without checking.
    """
    gap = detect_gaps(workspace, clock=clock)
    if gap["status"] != "OK":
        return gap
    try:
        view = _queue_view(read_queue(workspace), now=_now(clock),
                           include_test_data=_include_test_data(
                               workspace, include_test_data))
    except SailangError as exc:
        result = _workspace.command_result(
            "catchup-notice", QUEUE_UNREADABLE, workspace=workspace,
            gap=gap["gap"], queue={"state": QUEUE_UNREADABLE, "reason": exc.code},
            detail=f"the gap is {gap['gap']['downtime_seconds']}s but the queue "
                   f"cannot be read ({exc.code}); the notice reports what it knows "
                   "and no more")
        return _operator_action(result)
    reasons = {}
    for entry in view["entries"]:
        if entry["state"] == PARKED and entry["parked_reason"]:
            reasons[entry["parked_reason"]] = reasons.get(
                entry["parked_reason"], 0) + 1
    owed = view["totals"][QUEUED] + view["totals"][IN_FLIGHT] \
        + view["totals"][PARKED]
    return _workspace.command_result(
        "catchup-notice", "OK", workspace=workspace,
        gap=gap["gap"], queue=view, owed=owed, parked_reasons=reasons,
        notice={
            "downtime_seconds": gap["gap"]["downtime_seconds"],
            "owed_jobs": owed,
            "attempts": view["attempts"],
            "oldest_owed_seconds": view["oldest_owed_seconds"],
            "parked": view["totals"][PARKED],
            "free_locks_observed": len(view["residue"]),
            "outage_cause": UNKNOWN_CAUSE,
            "cause_evidence": gap["gap"]["evidence"],
        },
        detail=f"after {gap['gap']['downtime_seconds']}s of downtime, {owed} "
               f"logical job(s) are owed across {len(view['by_kind'])} kind(s); "
               f"{view['totals'][PARKED]} parked, oldest {view['attempts']} "
               f"attempt(s) total; the cause is {UNKNOWN_CAUSE}")


__all__ = [
    "BAD_INPUT",
    "CATCHUP_SCHEMA",
    "COOLDOWN_BASE_SECONDS",
    "DEFAULT_CLAIM_LIMIT",
    "DELIVERY",
    "DELIVERY_FAILED",
    "DONE",
    "EXECUTABLE",
    "IN_FLIGHT",
    "IN_FLIGHT_TIMEOUT_SECONDS",
    "KINDS",
    "NEEDS_SIGNING_KEY",
    "NOT_DUE",
    "OPERATOR_ACTION_CODES",
    "PARKED",
    "PEER_UNREACHABLE",
    "QUEUED",
    "QUEUE_LOCK_TIMEOUT",
    "QUEUE_UNREADABLE",
    "QUEUE_WRITE_FAILED",
    "RECONCILE",
    "RESIDUE",
    "STALE_CLAIM_REAPED",
    "STATES",
    "STILL_OWED",
    "SUPERSEDED",
    "TRUST",
    "TRUST_NEEDS_REVIEW",
    "UNKNOWN_CAUSE",
    "UNKNOWN_ENTRY",
    "catchup_root",
    "claim",
    "complete",
    "detect_gaps",
    "note_recovery",
    "notice",
    "park",
    "plan",
    "queue",
    "read_queue",
    "read_service",
    "record_tick",
    "run",
]