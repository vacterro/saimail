"""Project-local participant registry: who automation may address (V6-06, T-120).

Defect class this module eliminates: an automatic sender that has to guess its
recipient. ``peers.json`` says how to reach an alias, not which agents take part
in which project, so automation would have to pick a mailbox by name or by
convention. A wrong guess delivers project work to the wrong agent.

The acting workspace keeps ``participants.json``: for each project lineage
(``lineage-<32 hex>``, the SAIPEN project identity) the seats explicitly admitted
as participants, each pointing at a registered alias with its identity pinned at
admission, and the notify triggers it may receive. Resolution never falls back:
an unknown project, an unadmitted seat, a changed identity, a trigger outside the
admission or an address to oneself is refused. There is no discovery and no
global registry; receiver-owned acceptance is unchanged, because the recipient
still decides whether it accepts the sender at delivery.

The closed notify trigger set lives here, each with the existing SENV2 kind it
travels as, so the notify path (V6-08) cannot invent a trigger or a kind.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from sailang import SailangError
from saimail import postoffice
from saimail import workspace as _workspace

PARTICIPANTS_SCHEMA = "SAIMAIL_PARTICIPANTS_1"
PARTICIPANTS_VERSION = 1
PARTICIPANTS_NAME = "participants.json"
LOCK_NAME = "participants.lock"

#: The closed notify trigger set (SRC-107, SRC-108) and the SENV2 kind each uses.
#: Kind classifies content; it is never a priority the sender assigns.
TRIGGERS = {
    "blocker": "WARNING",        # a blocker needs action from another admitted seat
    "finding": "DISCOVERY",      # a finding materially affects another active Work
    "dependency": "DISCOVERY",   # another seat owns a dependency, or it became actionable
    "ownership": "DISCOVERY",    # ownership or dependency state changed
    "handoff": "QUESTION",       # a bounded handoff is requested
    "reply": "DISCOVERY",        # information another agent requested from this Work
}

ADMITTED = "PARTICIPANT_ADMITTED"
ALREADY_ADMITTED = "PARTICIPANT_ALREADY_ADMITTED"
REVOKED = "PARTICIPANT_REVOKED"
RESOLVED = "PARTICIPANT_RESOLVED"

PARTICIPANT_UNKNOWN = "PARTICIPANT_UNKNOWN"
PARTICIPANT_CONFLICT = "PARTICIPANT_CONFLICT"
PARTICIPANT_IDENTITY_CHANGED = "PARTICIPANT_IDENTITY_CHANGED"
PARTICIPANT_TRIGGER_NOT_ADMITTED = "PARTICIPANT_TRIGGER_NOT_ADMITTED"
PARTICIPANT_SELF = "PARTICIPANT_SELF"
PARTICIPANTS_CORRUPT = "PARTICIPANTS_CORRUPT"
PARTICIPANTS_LOCK_TIMEOUT = "PARTICIPANTS_LOCK_TIMEOUT"
BAD_LINEAGE = "BAD_LINEAGE"
BAD_TRIGGER = "BAD_TRIGGER"

OPERATOR_ACTION_CODES = frozenset({
    PARTICIPANT_UNKNOWN, PARTICIPANT_CONFLICT, PARTICIPANT_IDENTITY_CHANGED,
    PARTICIPANT_TRIGGER_NOT_ADMITTED, PARTICIPANT_SELF, PARTICIPANTS_CORRUPT,
    BAD_LINEAGE, BAD_TRIGGER,
})

_LINEAGE_RE = re.compile(r"^lineage-[0-9a-f]{32}$")
_RECORD_FIELDS = frozenset({"alias", "sender_kid", "recipient_kid", "triggers", "admitted_at"})


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _check_lineage(lineage) -> str:
    if not isinstance(lineage, str) or not _LINEAGE_RE.match(lineage):
        _reject(BAD_LINEAGE, "a project lineage is lineage-<32 lowercase hex>")
    return lineage


def _check_seat(seat) -> str:
    if not isinstance(seat, str) or not _workspace.SEAT_RE.match(seat):
        _reject(_workspace.BAD_SEAT, "a seat is one token of letters, digits, dot, dash or underscore")
    return seat


def _check_triggers(triggers) -> list:
    if triggers is None:
        return sorted(TRIGGERS)
    chosen = sorted(set(triggers))
    unknown = [name for name in chosen if name not in TRIGGERS]
    if not chosen or unknown:
        _reject(BAD_TRIGGER, f"triggers come from the closed set {sorted(TRIGGERS)}; "
                f"got {unknown or 'none'}")
    return chosen


def _path(workspace) -> Path:
    return Path(workspace.root) / PARTICIPANTS_NAME


def _lock(workspace) -> postoffice._OsFileLock:
    return postoffice._OsFileLock(Path(workspace.root) / LOCK_NAME,
                                  busy_code=PARTICIPANTS_LOCK_TIMEOUT)


def _read(workspace) -> dict:
    """The validated registry; a missing file is an empty registry."""
    path = _path(workspace)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        _reject(PARTICIPANTS_CORRUPT, f"participants file is unreadable: {exc}")
    if (not isinstance(payload, dict) or set(payload) != {"schema", "version", "projects"}
            or payload["schema"] != PARTICIPANTS_SCHEMA
            or payload["version"] != PARTICIPANTS_VERSION
            or not isinstance(payload["projects"], dict)):
        _reject(PARTICIPANTS_CORRUPT, "participants file declares an unknown shape")
    for lineage, seats in payload["projects"].items():
        if not _LINEAGE_RE.match(lineage) or not isinstance(seats, dict):
            _reject(PARTICIPANTS_CORRUPT, f"participants project {lineage!r} is malformed")
        for seat, record in seats.items():
            if (not _workspace.SEAT_RE.match(seat) or not isinstance(record, dict)
                    or set(record) != _RECORD_FIELDS
                    or not isinstance(record["triggers"], list)
                    or any(name not in TRIGGERS for name in record["triggers"])):
                _reject(PARTICIPANTS_CORRUPT, f"participant {seat!r} in {lineage} is malformed")
    return payload["projects"]


def _write(workspace, projects: dict) -> None:
    _workspace._atomic_write_bytes(_path(workspace), _workspace._canonical_json_bytes(
        {"schema": PARTICIPANTS_SCHEMA, "version": PARTICIPANTS_VERSION,
         "projects": projects}))


def _peer_for(workspace, alias: str, seat: str) -> dict:
    record = _workspace._resolve_recipient(workspace, alias)
    if record["seat"] != seat:
        _reject(PARTICIPANT_CONFLICT,
                f"alias {alias} is registered for seat {record['seat']}, not {seat}")
    return record


def admit_participant(workspace, lineage: str, seat: str, *, alias=None, triggers=None,
                      clock=None) -> dict:
    """Explicitly admit one registered seat as a participant of one project."""
    lineage = _check_lineage(lineage)
    seat = _check_seat(seat)
    if seat == workspace.seat:
        _reject(PARTICIPANT_SELF, "a workspace does not address itself")
    alias = seat if alias is None else alias
    chosen = _check_triggers(triggers)
    with _lock(workspace):
        peer = _peer_for(workspace, alias, seat)
        projects = _read(workspace)
        record = {"alias": alias, "sender_kid": peer["sender_kid"],
                  "recipient_kid": peer["recipient_kid"], "triggers": chosen,
                  "admitted_at": (clock or postoffice.utc_now)()}
        existing = projects.get(lineage, {}).get(seat)
        if existing is not None:
            same = {name: existing[name] for name in _RECORD_FIELDS - {"admitted_at"}}
            if same == {name: record[name] for name in _RECORD_FIELDS - {"admitted_at"}}:
                return _result(ALREADY_ADMITTED, workspace, lineage, seat, existing,
                               "identical admission already recorded")
            _reject(PARTICIPANT_CONFLICT,
                    f"seat {seat} is already admitted in {lineage} with another alias, "
                    "identity or trigger set; revoke it first")
        projects.setdefault(lineage, {})[seat] = record
        _write(workspace, projects)
    return _result(ADMITTED, workspace, lineage, seat, record,
                   f"seat {seat} admitted in {lineage} via alias {alias}")


def revoke_participant(workspace, lineage: str, seat: str) -> dict:
    lineage = _check_lineage(lineage)
    seat = _check_seat(seat)
    with _lock(workspace):
        projects = _read(workspace)
        record = projects.get(lineage, {}).pop(seat, None)
        if record is None:
            _reject(PARTICIPANT_UNKNOWN, f"seat {seat} is not admitted in {lineage}")
        if not projects[lineage]:
            del projects[lineage]
        _write(workspace, projects)
    return _result(REVOKED, workspace, lineage, seat, record, f"seat {seat} revoked")


def list_participants(workspace, lineage=None) -> dict:
    """Admitted participants, for one project or all; public metadata only."""
    projects = _read(workspace)
    if lineage is not None:
        lineage = _check_lineage(lineage)
        projects = {lineage: projects.get(lineage, {})}
    return _workspace.command_result(
        "participants", "OK", workspace=workspace,
        participants={name: dict(sorted(seats.items())) for name, seats in sorted(projects.items())},
        detail=f"{sum(len(seats) for seats in projects.values())} participant(s)")


def resolve_participant(workspace, lineage: str, seat: str, *, trigger: str) -> dict:
    """The registered alias automation may use for one seat, trigger and project.

    Refuses rather than guesses: the seat must be admitted in this project, for
    this trigger, and its registered identity must still be the pinned one.
    """
    lineage = _check_lineage(lineage)
    seat = _check_seat(seat)
    if trigger not in TRIGGERS:
        _reject(BAD_TRIGGER, f"trigger {trigger!r} is not in the closed set {sorted(TRIGGERS)}")
    if seat == workspace.seat:
        _reject(PARTICIPANT_SELF, "a workspace does not address itself")
    record = _read(workspace).get(lineage, {}).get(seat)
    if record is None:
        _reject(PARTICIPANT_UNKNOWN, f"seat {seat} is not an admitted participant of {lineage}")
    if trigger not in record["triggers"]:
        _reject(PARTICIPANT_TRIGGER_NOT_ADMITTED,
                f"seat {seat} is admitted for {record['triggers']}, not {trigger}")
    try:
        peer = _peer_for(workspace, record["alias"], seat)
    except SailangError as exc:
        _reject(PARTICIPANT_IDENTITY_CHANGED,
                f"participant {seat} no longer resolves to its admitted alias: {exc.code}")
    if (peer["sender_kid"], peer["recipient_kid"]) != (record["sender_kid"],
                                                       record["recipient_kid"]):
        _reject(PARTICIPANT_IDENTITY_CHANGED,
                f"participant {seat} changed identity since admission; re-admit explicitly")
    return _result(RESOLVED, workspace, lineage, seat, record,
                   f"{trigger} for {seat} goes to alias {record['alias']} as {TRIGGERS[trigger]}",
                   trigger=trigger, kind=TRIGGERS[trigger])


def _result(status, workspace, lineage, seat, record, detail, **extra) -> dict:
    return _workspace.command_result(
        "participant", status, workspace=workspace,
        participant={"lineage": lineage, "seat": seat, **record, **extra}, detail=detail)


__all__ = [
    "ADMITTED",
    "ALREADY_ADMITTED",
    "BAD_LINEAGE",
    "BAD_TRIGGER",
    "OPERATOR_ACTION_CODES",
    "PARTICIPANTS_CORRUPT",
    "PARTICIPANTS_LOCK_TIMEOUT",
    "PARTICIPANTS_SCHEMA",
    "PARTICIPANT_CONFLICT",
    "PARTICIPANT_IDENTITY_CHANGED",
    "PARTICIPANT_SELF",
    "PARTICIPANT_TRIGGER_NOT_ADMITTED",
    "PARTICIPANT_UNKNOWN",
    "RESOLVED",
    "REVOKED",
    "TRIGGERS",
    "admit_participant",
    "list_participants",
    "resolve_participant",
    "revoke_participant",
]
