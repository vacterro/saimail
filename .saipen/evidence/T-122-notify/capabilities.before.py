"""Capability and health document for SAIPEN negotiation (V6-07 SAIMAIL half, T-121).

Defect class this module eliminates: an orchestrator that can only learn whether
the mail channel works by calling it and parsing a failure. SAIPEN's turn entry
calls one command and gets counts or a bare exit code; it cannot tell "no mail"
from "wrong seat", "mailbox missing", "outbox stuck" or "newer API", and a
refusal either breaks the call or hides its cause.

``capabilities`` answers with one versioned document and never raises for a
state: every problem is a capability state plus a reason from a closed set, so
a consumer can continue its own work and report the channel as DEGRADED or
UNAVAILABLE. Nothing here decrypts, opens, reads a private key or touches the
credential store; message counts are reported only to the seat that owns the
mailbox, so a wrong seat never sees another agent's traffic.
"""

from __future__ import annotations

from sailang import SailangError
from saimail import outbox, participants, postoffice
from saimail import workspace as _workspace

CAPABILITIES_SCHEMA = "SAIMAIL_CAPABILITIES_1"
CAPABILITIES_VERSION = 1

#: Capability states (SAIOPP capability truth). UNVERIFIED is honest ignorance:
#: it is never promoted to AVAILABLE by assumption.
AVAILABLE = "AVAILABLE"
DEGRADED = "DEGRADED"
REQUIRES_HUMAN = "REQUIRES_HUMAN"
UNAVAILABLE = "UNAVAILABLE"
UNVERIFIED = "UNVERIFIED"

#: Closed reason codes.
WORKSPACE_MISSING = "WORKSPACE_MISSING"
WORKSPACE_INVALID = "WORKSPACE_INVALID"
SEAT_MISMATCH = "SEAT_MISMATCH"
SEAT_UNKNOWN = "SEAT_UNKNOWN"
PROJECT_NOT_BOUND = "PROJECT_NOT_BOUND"
NO_PARTICIPANTS = "NO_PARTICIPANTS"
OUTBOX_BACKLOG = "OUTBOX_BACKLOG"
OUTBOX_FAILED = "OUTBOX_FAILED"
OUTBOX_CORRUPT = "OUTBOX_CORRUPT"
PARTICIPANTS_CORRUPT = "PARTICIPANTS_CORRUPT"
INBOX_UNREADABLE = "INBOX_UNREADABLE"
KEYS_NOT_CHECKED = "KEYS_NOT_CHECKED"
REASONS = frozenset({
    WORKSPACE_MISSING, WORKSPACE_INVALID, SEAT_MISMATCH, SEAT_UNKNOWN, PROJECT_NOT_BOUND,
    NO_PARTICIPANTS, OUTBOX_BACKLOG, OUTBOX_FAILED, OUTBOX_CORRUPT, PARTICIPANTS_CORRUPT,
    INBOX_UNREADABLE, KEYS_NOT_CHECKED,
})

#: An open intent older than this makes the outbox DEGRADED (backlog).
OUTBOX_BACKLOG_SECONDS = 3600
AWARENESS_SCAN_BUDGET = 200


def _cap(state: str, reason=None, **fields) -> dict:
    return {"state": state, "reason": reason, **fields}


def capabilities(workspace_root, *, acting_seat=None, seat_source=None, lineage=None,
                 current_topic=None, extra=None, clock=None) -> dict:
    """One keyless capability and health document; never raises for a state.

    ``acting_seat`` is who asks (from the SAIPEN binding); when it differs from
    the mailbox seat the document is UNAVAILABLE and carries no counts.
    ``lineage`` is the admitted project, when one is bound. ``extra`` lets a
    later capability (the notify path) add its own entry.
    """
    reasons: list = []
    document = {
        "schema": CAPABILITIES_SCHEMA, "version": CAPABILITIES_VERSION,
        "api": {"command_schema": _workspace.COMMAND_SCHEMA,
                "command_version": _workspace.COMMAND_VERSION,
                "outbox_schema": outbox.OUTBOX_INTENT_SCHEMA,
                "participants_schema": participants.PARTICIPANTS_SCHEMA,
                "triggers": sorted(participants.TRIGGERS)},
        "seat": {"acting": acting_seat, "source": seat_source, "workspace": None,
                 "matches": None},
        "project": {"lineage": lineage, "state": AVAILABLE if lineage else UNAVAILABLE},
        "workspace": {"root": str(workspace_root), "state": AVAILABLE, "custody": None,
                      "peers": None},
        "capabilities": {},
        "awareness": None,
        "outbox": None,
    }
    if lineage is None:
        reasons.append(PROJECT_NOT_BOUND)
    try:
        view = _workspace.load_workspace_headers(workspace_root)
    except SailangError as exc:
        reason = WORKSPACE_MISSING if exc.code == _workspace.WORKSPACE_MISSING else WORKSPACE_INVALID
        document["workspace"].update(state=UNAVAILABLE, reason=reason)
        return _finish(document, reasons + [reason], overall=UNAVAILABLE)
    document["workspace"].update(custody=view.custody, peers=len(view.peers))
    document["seat"]["workspace"] = view.seat
    if acting_seat is None:
        reasons.append(SEAT_UNKNOWN)
    elif acting_seat != view.seat:
        document["seat"]["matches"] = False
        return _finish(document, reasons + [SEAT_MISMATCH], overall=UNAVAILABLE)
    else:
        document["seat"]["matches"] = True

    caps = document["capabilities"]
    caps["signing"] = _cap(UNVERIFIED, KEYS_NOT_CHECKED, detail="private keys are not touched "
                           "by a capability check; open, reopen and send verify them")
    try:
        found = _workspace.query_inbox(view, state=postoffice.UNREAD,
                                       scan_budget=AWARENESS_SCAN_BUDGET, clock=clock)
        on_topic = (sum(1 for item in found["items"] if item["topic"] == current_topic)
                    if current_topic else None)
        document["awareness"] = {"unread": found["match_count"], "current_topic": current_topic,
                                 "on_current_topic": on_topic,
                                 "complete": found["exhausted"] is False,
                                 "scan_budget": AWARENESS_SCAN_BUDGET}
        caps["header_awareness"] = _cap(AVAILABLE, secret_free=True)
    except SailangError as exc:
        caps["header_awareness"] = _cap(UNAVAILABLE, INBOX_UNREADABLE, code=exc.code)
        reasons.append(INBOX_UNREADABLE)
    try:
        box = outbox.outbox_status(view, clock=clock)["outbox"]
        health = {name: box[name] for name in ("pending", "retrying", "attempts",
                                               "oldest_pending_seconds", "last_error",
                                               "last_delivered_at")}
        health["failed"] = box["counts"][outbox.FAILED]
        document["outbox"] = health
        if health["failed"]:
            caps["durable_outbox"] = _cap(REQUIRES_HUMAN, OUTBOX_FAILED)
            reasons.append(OUTBOX_FAILED)
        elif (health["oldest_pending_seconds"] or 0) > OUTBOX_BACKLOG_SECONDS:
            caps["durable_outbox"] = _cap(DEGRADED, OUTBOX_BACKLOG)
            reasons.append(OUTBOX_BACKLOG)
        else:
            caps["durable_outbox"] = _cap(AVAILABLE)
    except SailangError as exc:
        caps["durable_outbox"] = _cap(UNAVAILABLE, OUTBOX_CORRUPT, code=exc.code)
        reasons.append(OUTBOX_CORRUPT)
    try:
        admitted = participants.list_participants(view, lineage)["participants"] if lineage else {}
        count = len(admitted.get(lineage, {})) if lineage else 0
        if lineage is None:
            caps["participant_registry"] = _cap(UNAVAILABLE, PROJECT_NOT_BOUND)
        elif count == 0:
            caps["participant_registry"] = _cap(REQUIRES_HUMAN, NO_PARTICIPANTS, admitted=0)
            reasons.append(NO_PARTICIPANTS)
        else:
            caps["participant_registry"] = _cap(AVAILABLE, admitted=count)
    except SailangError as exc:
        caps["participant_registry"] = _cap(UNAVAILABLE, PARTICIPANTS_CORRUPT, code=exc.code)
        reasons.append(PARTICIPANTS_CORRUPT)
    for name, entry in (extra or {}).items():
        caps[name] = entry
        if entry.get("reason") and entry["state"] != AVAILABLE:
            reasons.append(entry["reason"])
    blocking = any(entry["state"] in (UNAVAILABLE, DEGRADED, REQUIRES_HUMAN)
                   for entry in caps.values())
    return _finish(document, reasons, overall=DEGRADED if blocking or lineage is None
                   else AVAILABLE)


def _finish(document: dict, reasons: list, *, overall: str) -> dict:
    ordered = sorted(set(reasons))
    if not set(ordered) <= REASONS:
        raise AssertionError(f"reason outside the closed set: {ordered}")
    document["overall"] = overall
    document["reasons"] = ordered
    return _workspace.command_result(
        "saipen-capabilities", overall, capabilities=document,
        detail=f"channel {overall}" + (f" ({', '.join(ordered)})" if ordered else "")
        + "; metadata only, nothing opened, no private key touched")


__all__ = [
    "AVAILABLE",
    "CAPABILITIES_SCHEMA",
    "CAPABILITIES_VERSION",
    "DEGRADED",
    "OUTBOX_BACKLOG_SECONDS",
    "REASONS",
    "REQUIRES_HUMAN",
    "UNAVAILABLE",
    "UNVERIFIED",
    "capabilities",
]
