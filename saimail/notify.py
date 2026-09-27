"""Automatic SAITELEMES notify for a closed trigger set (V6-08 SAIMAIL half, T-122).

Defect class this module eliminates: information that must cross an ownership
boundary waiting for a human relay, and the opposite failure, an automatic sender
that chatters, guesses its recipient or repeats itself. The operator authorized
automatic sending only for a closed set of triggers (SRC-108) under a policy
(SRC-107): resolve the recipient from the admitted participant registry, bind the
message to a real Work, give it a deterministic idempotency key, write the intent
durably before delivery, and never let the sender set the receiver's priority.

``notify`` is the one call a SAIPEN event trigger makes. It resolves the admitted
participant for the trigger (D-061), derives the key from project, Work, trigger,
recipient and the event or claim, applies a per-recipient flood budget under the
outbox lock, and submits through the durable outbox (D-060), then advances other
due intents so retries happen without a daemon. The body is a one-line claim or
the S2 citation of one LOG event; either is data and grants no authority.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from datetime import timedelta
from pathlib import Path

from sailang import SailangError
from saimail import outbox, participants, postoffice
from saimail import workspace as _workspace

NOTIFY_KEY_PREFIX = "notify:"
NOTIFY_SUPPRESSED = "NOTIFY_SUPPRESSED"
NOTIFY_NO_WORK = "NOTIFY_NO_WORK"
NOTIFY_WORK_UNKNOWN = "NOTIFY_WORK_UNKNOWN"
NOTIFY_BUDGET_EXCEEDED = "NOTIFY_BUDGET_EXCEEDED"

OPERATOR_ACTION_CODES = frozenset({NOTIFY_NO_WORK, NOTIFY_WORK_UNKNOWN})

#: Receiver attention is a budget the sender cannot spend freely. Over it, a new
#: notification is suppressed (nothing written, never retried); a repeat of an
#: already recorded notification is never counted.
BUDGET_WINDOW_SECONDS = 3600
BUDGET_PER_RECIPIENT = 20
BUDGET_PER_RECIPIENT_WORK = 5
RESUME_BUDGET = 10

_WORK_RE = re.compile(r"^T-[0-9]+$")
_BOARD_WORK_RE = re.compile(r"^\s*- \[[ xX/!~-]\] (T-[0-9]+)\b", re.MULTILINE)
_EVENT_RE = re.compile(r"^E-[1-9][0-9]*$")


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def board_work_ids(board_text: str) -> frozenset:
    """The Work ids a SAIPEN BOARD lists; a notify may only name one of these."""
    return frozenset(_BOARD_WORK_RE.findall(board_text or ""))


def resolve_work(current_task, explicit=None, board_ids=frozenset()) -> str:
    """The Work a notification belongs to: explicit and listed on BOARD, else current."""
    if explicit is not None:
        if not isinstance(explicit, str) or not _WORK_RE.match(explicit):
            _reject(NOTIFY_WORK_UNKNOWN, "a Work id is T-<number>")
        if explicit not in board_ids:
            _reject(NOTIFY_WORK_UNKNOWN, f"{explicit} is not a Work on this project's BOARD")
        return explicit
    task = current_task or ""
    if not _WORK_RE.match(task):
        _reject(NOTIFY_NO_WORK, "a notification belongs to a Work; there is no active Work "
                "and none was named")
    return task


def notify_key(lineage: str, work: str, trigger: str, seat: str, basis: str) -> str:
    return f"{NOTIFY_KEY_PREFIX}{lineage}:{work}:{trigger}:{seat}:{basis}"


def _budget_gate(seat: str, work: str, now: str):
    cutoff = postoffice._format_utc(postoffice._parse_utc(now, code="BAD_CLOCK")
                                    - timedelta(seconds=BUDGET_WINDOW_SECONDS))

    def gate(intents) -> None:
        recent = [item for item in intents
                  if item["key"].startswith(NOTIFY_KEY_PREFIX)
                  and item["recipient_seat"] == seat and item["recorded_at"] >= cutoff]
        if len(recent) >= BUDGET_PER_RECIPIENT:
            _reject(NOTIFY_BUDGET_EXCEEDED,
                    f"{seat} already has {len(recent)} notifications this hour")
        if sum(1 for item in recent if item["topic"] == work) >= BUDGET_PER_RECIPIENT_WORK:
            _reject(NOTIFY_BUDGET_EXCEEDED,
                    f"{seat} already has {BUDGET_PER_RECIPIENT_WORK} notifications about {work} "
                    "this hour")
    return gate


def notify(workspace, *, lineage: str, work: str, trigger: str, to_seat: str, claim=None,
           citation=None, event=None, clock=None) -> dict:
    """Send one automatic notification exactly once, or suppress it by budget.

    Exactly one body: ``claim`` (one line) or ``citation`` (the S2 record of
    ``event``). The recipient, kind and alias come from the participant registry;
    the key makes every repeat of the same fact the same message.
    """
    if (claim is None) == (citation is None):
        _reject(_workspace.BAD_INPUT, "a notification carries exactly one of a claim or a citation")
    resolved = participants.resolve_participant(workspace, lineage, to_seat,
                                                trigger=trigger)["participant"]
    if citation is not None:
        if not isinstance(event, str) or not _EVENT_RE.match(event):
            _reject(_workspace.BAD_INPUT, "a citation names its event id E-<number>")
        basis = event
        identity = {"form": "citation", "event": event, "ev": citation.get("EV")}
    else:
        if not isinstance(claim, str) or not claim.strip() or "\n" in claim or "\r" in claim:
            _reject(_workspace.BAD_INPUT, "a notification claim is one non-empty line")
        basis = "c" + hashlib.sha256(claim.strip().encode("utf-8")).hexdigest()[:24]
        identity = None
    key = notify_key(lineage, work, trigger, to_seat, basis)
    now = (clock or postoffice.utc_now)()
    kwargs = {"key": key, "subject": work, "topic": work, "kind": resolved["kind"],
              "content_identity": identity, "gate": _budget_gate(to_seat, work, now),
              "clock": clock}
    try:
        if citation is not None:
            with tempfile.TemporaryDirectory(prefix="saimail-notify-") as scratch:
                path = Path(scratch) / "citation.sail"
                path.write_bytes(citation.canonical_bytes())
                sent = outbox.submit_send(workspace, resolved["alias"], record_path=path,
                                          **kwargs)
        else:
            sent = outbox.submit_send(workspace, resolved["alias"], claim=claim.strip(),
                                      **kwargs)
    except SailangError as exc:
        if exc.code != NOTIFY_BUDGET_EXCEEDED:
            raise
        return _workspace.command_result(
            "saipen-notify", NOTIFY_SUPPRESSED, workspace=workspace,
            notify=_view(trigger, to_seat, resolved, work, key),
            detail=f"suppressed by the receiver attention budget: {exc.detail}; nothing written")
    resumed = outbox.resume_outbox(workspace, budget=RESUME_BUDGET, clock=clock)["counts"]
    result = dict(sent)
    result.update(command="saipen-notify", notify=_view(trigger, to_seat, resolved, work, key),
                  resumed=resumed)
    return result


def _view(trigger, seat, resolved, work, key) -> dict:
    return {"trigger": trigger, "to_seat": seat, "alias": resolved["alias"],
            "kind": resolved["kind"], "work": work, "key": key}


__all__ = [
    "BUDGET_PER_RECIPIENT",
    "BUDGET_PER_RECIPIENT_WORK",
    "BUDGET_WINDOW_SECONDS",
    "NOTIFY_BUDGET_EXCEEDED",
    "NOTIFY_NO_WORK",
    "NOTIFY_SUPPRESSED",
    "NOTIFY_WORK_UNKNOWN",
    "OPERATOR_ACTION_CODES",
    "board_work_ids",
    "notify",
    "notify_key",
    "resolve_work",
]
