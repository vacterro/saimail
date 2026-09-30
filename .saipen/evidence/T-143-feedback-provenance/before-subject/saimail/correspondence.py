"""Receiver decisions and a bounded evidence reserve for successor agents.

The database contains routing, hashes and closed decision codes, never letter
bodies. The sealed Post Office remains the content authority. Observing mail
does not imply useful work; only explicit receiver decisions record outcomes.
Retained letters are context-linked reading recommendations, not knowledge
promotion or lifecycle authority.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from sailang import SailangError
from saimail import letters, notify, participants, postoffice
from saimail import workspace as ws

DB_NAME = "correspondence.sqlite3"
DB_VERSION = 1
CORRESPONDENCE_CORRUPT = "CORRESPONDENCE_CORRUPT"
CORRESPONDENCE_UNAVAILABLE = "CORRESPONDENCE_UNAVAILABLE"
LETTER_CONTEXT_MISMATCH = "LETTER_CONTEXT_MISMATCH"
LETTER_DECISION_INVALID = "LETTER_DECISION_INVALID"
LETTER_NOT_REVIEWED = "LETTER_NOT_REVIEWED"
LETTER_NOT_RETAINABLE = "LETTER_NOT_RETAINABLE"
MAX_PAGE = 100
MAX_HISTORY = 100
FEEDBACK_WINDOW_DAYS = 7
FEEDBACK_SCHEMA = "SAIMAIL_FEEDBACK_SIGNALS_1"

DECISIONS = frozenset({"ACCEPTED", "DEFERRED", "DECLINED", "RESOLVED", "STALE"})
REASONS = {
    "ACCEPTED": frozenset({"ACTION_PLANNED"}),
    "DEFERRED": frozenset({"WAITING_DEPENDENCY", "OUTSIDE_CURRENT_WORK"}),
    "DECLINED": frozenset({"ALREADY_KNOWN", "NOT_ACTIONABLE", "WRONG_RECIPIENT", "OUTSIDE_SCOPE"}),
    "RESOLVED": frozenset({"ACTION_TAKEN"}),
    "STALE": frozenset({"CONDITION_CHANGED", "EVIDENCE_CHANGED", "EXPIRED"}),
}
TERMINAL = frozenset({"DECLINED", "RESOLVED", "STALE"})
OPERATOR_ACTION_CODES = frozenset({CORRESPONDENCE_CORRUPT, CORRESPONDENCE_UNAVAILABLE})
FEEDBACK_HINTS = {
    "ALREADY_KNOWN": "RECHECK_EXISTING_RESULTS",
    "NOT_ACTIONABLE": "ADD_REPRODUCTION_OR_DECISION_CRITERION",
    "WRONG_RECIPIENT": "CHECK_WORK_OWNER",
    "OUTSIDE_SCOPE": "NARROW_RECIPIENT_SCOPE",
    "WAITING_DEPENDENCY": "WAIT_FOR_DEPENDENCY_EVIDENCE",
    "OUTSIDE_CURRENT_WORK": "MATCH_CURRENT_WORK",
    "CONDITION_CHANGED": "RECHECK_CONDITION",
    "EVIDENCE_CHANGED": "REHASH_AND_REVIEW",
    "EXPIRED": "REFRESH_RELEVANCE_BEFORE_RESEND",
}

_DDL = """
CREATE TABLE identity (version INTEGER NOT NULL, recipient_kid TEXT NOT NULL);
CREATE TABLE cases (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 envelope_id TEXT NOT NULL UNIQUE,
 lineage TEXT NOT NULL,
 sender TEXT NOT NULL,
 sender_work TEXT NOT NULL,
 recipient_work TEXT NOT NULL,
 issue TEXT NOT NULL,
 expires_at TEXT NOT NULL,
 scope TEXT NOT NULL,
 evidence TEXT NOT NULL,
 content_id TEXT NOT NULL,
 decision TEXT NOT NULL DEFAULT 'PENDING',
 reason TEXT,
 retained INTEGER NOT NULL DEFAULT 0,
 reviewed_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE INDEX context_cases ON cases(lineage, recipient_work, id);
CREATE TABLE events (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 envelope_id TEXT NOT NULL REFERENCES cases(envelope_id),
 decision TEXT NOT NULL,
 reason TEXT NOT NULL,
 evidence TEXT NOT NULL,
 at TEXT NOT NULL
);
"""


def _reject(code, detail):
    raise SailangError(code, detail)


def _now(clock):
    value = (clock or postoffice.utc_now)()
    postoffice._parse_utc(value, code="BAD_CLOCK")
    return value


@contextmanager
def _db(workspace, *, write=False):
    path = Path(workspace.root) / DB_NAME
    if not write and not path.exists():
        yield None
        return
    connection = None
    try:
        connection = sqlite3.connect(
            path if write else path.as_uri() + "?mode=ro", uri=not write, timeout=10)
        connection.row_factory = sqlite3.Row
        if write:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("BEGIN IMMEDIATE")
            exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='identity'").fetchone()
            if not exists:
                if connection.execute("SELECT 1 FROM sqlite_master WHERE type='table'").fetchone():
                    _reject(CORRESPONDENCE_CORRUPT, "unrecognized correspondence database")
                # execute individual statements: executescript commits an open
                # transaction and would race another initializer.
                for statement in _DDL.split(";"):
                    if statement.strip():
                        connection.execute(statement)
                connection.execute("INSERT INTO identity VALUES (?, ?)",
                                   (DB_VERSION, workspace.recipient_kid))
        identity = connection.execute("SELECT * FROM identity").fetchall()
        if (len(identity) != 1 or identity[0]["version"] != DB_VERSION
                or identity[0]["recipient_kid"] != workspace.recipient_kid):
            _reject(CORRESPONDENCE_CORRUPT, "correspondence belongs to another mailbox or schema")
        yield connection
        if write:
            connection.commit()
    except sqlite3.DatabaseError as exc:
        code = (CORRESPONDENCE_UNAVAILABLE if isinstance(exc, sqlite3.OperationalError)
                and any(word in str(exc).lower() for word in ("locked", "readonly", "open"))
                else CORRESPONDENCE_CORRUPT)
        _reject(code, "correspondence metadata is unavailable or invalid")
    finally:
        if connection is not None:
            connection.close()  # also rolls back an interrupted transaction


def dispatch(workspace, letter, *, lineage, sender_work, to_seat, project_root, clock=None):
    """Check utility inputs and evidence before spending receiver attention."""
    letters.validate(letter, lineage=lineage, sender_work=sender_work)
    now = _now(clock)
    if letters.is_expired(letter, now):
        _reject(letters.LETTER_EXPIRED, "an expired letter must not recruit attention")
    participants.resolve_participant(workspace, lineage, to_seat, trigger=letter["trigger"])
    if letter["in_reply_to"] is not None:
        original, opened = _opened_letter(workspace, letter["in_reply_to"], lineage, clock=clock)
        if (to_seat != opened["message"]["from"]
                or letter["sender_work"] != original["recipient_work"]
                or letter["recipient_work"] != original["sender_work"]):
            _reject(LETTER_CONTEXT_MISMATCH, "reply must return to the authenticated original work owner")
    letters.require_current(letter["evidence"], project_root)
    return notify.notify(workspace, lineage=lineage, work=letter["recipient_work"],
                         trigger=letter["trigger"], to_seat=to_seat, letter=letter, clock=clock)


def _opened_letter(workspace, envelope_id, lineage, *, clock=None):
    office = workspace.office(clock=clock)
    row = office.read_index_row(envelope_id)
    if row is None:
        _reject(LETTER_CONTEXT_MISMATCH, "letter is not in this receiver's mailbox")
    participants._check_lineage(lineage)
    if row["topic"].startswith("l.") and not row["topic"].startswith(
            "l." + lineage.removeprefix("lineage-") + "."):
        _reject(LETTER_CONTEXT_MISMATCH, "letter header belongs to another project")
    state = office.bundle_state(envelope_id, row=row)
    if state == postoffice.READ_STATE:
        result = ws.reopen_message(workspace, envelope_id, clock=clock)
    else:
        result = ws.open_message(workspace, envelope_id, clock=clock)
    letter = letters.parse(result["record"]["claim"])
    letters.validate(letter, lineage=lineage)
    # Early local letters used a bare Work topic. They remain explicitly
    # readable only after their authenticated body passes the lineage check;
    # keyless discovery never guesses their project from this bare header.
    if row["topic"] not in (letters.topic(lineage, letter["recipient_work"]), letter["recipient_work"]):
        _reject(LETTER_CONTEXT_MISMATCH, "sealed routing topic differs from the project and Work")
    if row["kind"] != participants.TRIGGERS[letter["trigger"]]:
        _reject(LETTER_CONTEXT_MISMATCH, "sealed letter kind differs from its stated trigger")
    return letter, result


def review(workspace, envelope_id, *, lineage, project_root, clock=None):
    """Explicit authenticated Open/Reopen, evidence recheck, no action inference."""
    now = _now(clock)
    letter, opened = _opened_letter(workspace, envelope_id, lineage, clock=clock)
    checked = letters.verify_evidence(letter["evidence"], project_root)
    with _db(workspace, write=True) as db:
        old = db.execute("SELECT * FROM cases WHERE envelope_id=?", (envelope_id,)).fetchone()
        if old is not None and old["content_id"] != opened["record"]["content_id"]:
            _reject(CORRESPONDENCE_CORRUPT, "sealed content identity differs from its review")
        if old is None:
            db.execute("""INSERT INTO cases (
                envelope_id, lineage, sender, sender_work, recipient_work, issue,
                expires_at, scope, evidence, content_id, reviewed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (envelope_id, lineage, opened["message"]["from"], letter["sender_work"],
                        letter["recipient_work"], letter["issue"], letter["expires_at"],
                        letters.encode(letter["scope"]), letters.encode(letter["evidence"]),
                        opened["record"]["content_id"], now, now))
        case = db.execute("SELECT * FROM cases WHERE envelope_id=?", (envelope_id,)).fetchone()
        case_view = _case_view(case, now)
        latest = db.execute("SELECT evidence FROM events WHERE envelope_id=? ORDER BY id DESC LIMIT 1",
                            (envelope_id,)).fetchone()
        result_refs = _metadata_json(latest["evidence"]) if latest is not None else []
        letters.check_evidence(result_refs)
    result_checked = letters.verify_evidence(result_refs, project_root)
    return ws.command_result(
        "letter-review", "LETTER_REVIEWED", workspace=workspace, letter=letter, case=case_view,
        evidence=checked, evidence_current=bool(checked) and all(r["state"] == "CURRENT" for r in checked),
        expired=letters.is_expired(letter, now),
        result_evidence=result_checked,
        result_current=bool(result_checked) and all(r["state"] == "CURRENT" for r in result_checked),
        detail="explicitly reviewed; hashes prove bytes, not truth; no action or promotion inferred")


def decide(workspace, envelope_id, *, lineage, project_root, decision, reason,
           evidence=None, revise=False, clock=None):
    """Record a receiver-owned outcome, reauthenticating the original each time.

    RESOLVED requires verifiable result evidence. Terminal corrections require
    explicit revise. Replaying the identical decision adds no second event.
    """
    if not isinstance(decision, str) or decision not in DECISIONS:
        _reject(LETTER_DECISION_INVALID, "choose an explicit receiver decision")
    if not isinstance(reason, str) or reason not in REASONS[decision]:
        _reject(LETTER_DECISION_INVALID, "reason must be one of the decision's closed reason codes")
    evidence = [] if evidence is None else evidence
    letters.check_evidence(evidence)
    if decision == "RESOLVED" and not evidence:
        _reject(LETTER_DECISION_INVALID, "RESOLVED needs evidence of the resulting work")
    letters.require_current(evidence, project_root)
    reviewed = review(workspace, envelope_id, lineage=lineage, project_root=project_root, clock=clock)
    if decision == "ACCEPTED" and (
            reviewed["expired"] or any(ref["state"] != "CURRENT" for ref in reviewed["evidence"])):
        _reject(LETTER_DECISION_INVALID, "stale evidence or expiry prevents an actionable decision")
    now = _now(clock)
    encoded = letters.encode(evidence)
    with _db(workspace, write=True) as db:
        case = db.execute("SELECT * FROM cases WHERE envelope_id=?", (envelope_id,)).fetchone()
        last = db.execute("SELECT * FROM events WHERE envelope_id=? ORDER BY id DESC LIMIT 1",
                          (envelope_id,)).fetchone()
        same = last is not None and (last["decision"], last["reason"], last["evidence"]) == (
            decision, reason, encoded)
        if not same:
            if case["decision"] in TERMINAL and not revise:
                _reject(LETTER_DECISION_INVALID, "changing a terminal decision requires explicit revise")
            count = db.execute("SELECT COUNT(*) FROM events WHERE envelope_id=?", (envelope_id,)).fetchone()[0]
            if count >= MAX_HISTORY:
                _reject(LETTER_DECISION_INVALID, "this letter's decision-history budget is exhausted")
            # A repeated older decision after a correction is a new event, so
            # remove no history and do not use INSERT OR REPLACE.
            db.execute("INSERT INTO events (envelope_id, decision, reason, evidence, at) "
                       "VALUES (?, ?, ?, ?, ?)", (envelope_id, decision, reason, encoded, now))
            db.execute("UPDATE cases SET decision=?, reason=?, updated_at=?, "
                       "retained=CASE WHEN ?='RESOLVED' THEN retained ELSE 0 END WHERE envelope_id=?",
                       (decision, reason, now, decision, envelope_id))
        case = db.execute("SELECT * FROM cases WHERE envelope_id=?", (envelope_id,)).fetchone()
        events = [dict(row) for row in db.execute(
            "SELECT decision, reason, evidence, at FROM events WHERE envelope_id=? ORDER BY id",
            (envelope_id,))]
    for event in events:
        event["evidence"] = json.loads(event["evidence"])
    return ws.command_result("letter-decide", "LETTER_DECIDED", workspace=workspace,
                             case=_case_view(case, now), history=events, repeated=same,
                             detail="receiver decision recorded; delivery and reading never imply resolution")


def retain(workspace, envelope_id, *, lineage, project_root, clock=None):
    """Explicitly retain a resolved, evidence-bearing letter for successor discovery."""
    reviewed = review(workspace, envelope_id, lineage=lineage, project_root=project_root, clock=clock)
    if reviewed["expired"]:
        _reject(LETTER_NOT_RETAINABLE, "expired relevance cannot enter the reserve")
    with _db(workspace, write=True) as db:
        case = db.execute("SELECT * FROM cases WHERE envelope_id=?", (envelope_id,)).fetchone()
        if case["decision"] != "RESOLVED":
            _reject(LETTER_NOT_RETAINABLE, "retain only after an explicit evidence-backed resolution")
        result = db.execute("SELECT evidence FROM events WHERE envelope_id=? AND decision='RESOLVED' "
                            "ORDER BY id DESC LIMIT 1", (envelope_id,)).fetchone()
        letters.require_current(json.loads(result["evidence"]), project_root)
        db.execute("UPDATE cases SET retained=1 WHERE envelope_id=?", (envelope_id,))
        case = db.execute("SELECT * FROM cases WHERE envelope_id=?", (envelope_id,)).fetchone()
    return ws.command_result("letter-retain", "LETTER_RETAINED", workspace=workspace,
                             case=_case_view(case, _now(clock)),
                             detail="retained as a context-linked reading recommendation; not promoted to knowledge")


def report(workspace, envelope_id, *, lineage, project_root, clock=None):
    """Return the latest explicit receiver decision, once per decision event.

    Negative and deferred feedback helps the sender reassess its next letter.
    RESOLVED still requires current result evidence. Revisions get distinct
    identities; retrying the same event never sends a second letter.
    """
    reviewed = review(workspace, envelope_id, lineage=lineage, project_root=project_root, clock=clock)
    with _db(workspace) as db:
        # One read snapshot binds the case, latest event and first resolution.
        db.execute("BEGIN")
        case = db.execute("SELECT * FROM cases WHERE envelope_id=?", (envelope_id,)).fetchone()
        if case["decision"] == "PENDING":
            _reject(LETTER_DECISION_INVALID, "report requires an explicit receiver decision")
        event = db.execute("SELECT * FROM events WHERE envelope_id=? "
                           "ORDER BY id DESC LIMIT 1", (envelope_id,)).fetchone()
        if (event is None or case["decision"] not in DECISIONS
                or event["decision"] != case["decision"] or event["reason"] != case["reason"]
                or event["reason"] not in REASONS[case["decision"]]):
            _reject(CORRESPONDENCE_CORRUPT, "receiver decision differs from its recorded event")
        first_resolution = db.execute(
            "SELECT MIN(id) FROM events WHERE envelope_id=? AND decision='RESOLVED'",
            (envelope_id,)).fetchone()[0]
    proof = _metadata_json(event["evidence"])
    letters.check_evidence(proof)
    resolved = case["decision"] == "RESOLVED"
    if resolved and not proof:
        _reject(CORRESPONDENCE_CORRUPT, "recorded resolution lacks result evidence")
    original = reviewed["letter"]
    # Preserve the original v1 identity/body for a first resolution already
    # reported by an older checkout. Subsequent resolutions are new events.
    issue = ("result-" if resolved else "feedback-") + envelope_id.split(":")[1][:32]
    if not resolved or event["id"] != first_resolution:
        issue += "-" + str(event["id"])
    response = letters.template(lineage, original["recipient_work"], original["sender_work"],
                                trigger="reply", issue=issue, clock=lambda: event["at"])
    response.update(
        observation="The receiver recorded ACTION_TAKEN for " + envelope_id,
        impact="The original sender can inspect the resulting artifact before repeating or depending on this work.",
        request="Check the result evidence against the original completion criterion carried in this result letter.",
        done_when=original["done_when"],
        uncertainty="A receiver-reported outcome and matching artifact bytes do not prove the claim is true.",
        evidence=proof, scope=original["scope"], in_reply_to=envelope_id)
    if not resolved:
        response.update(
            observation=f"The receiver recorded {case['decision']}/{case['reason']} for {envelope_id}.",
            impact="The original sender can reassess relevance, recipient and timing before repeating this request.",
            request="Assess this receiver feedback against the original completion criterion before planning another letter.",
            uncertainty="This is the receiver's recorded assessment; it does not prove the claim is true or that work was completed.")
    result = dispatch(workspace, response, lineage=lineage, sender_work=response["sender_work"],
                      to_seat=case["sender"], project_root=project_root, clock=clock)
    result["command"] = "letter-report"
    result["feedback"] = {"schema": "SAIMAIL_RECEIVER_FEEDBACK_1", "envelope_id": envelope_id,
                          "event_id": event["id"], "decision": case["decision"],
                          "reason": case["reason"], "at": event["at"],
                          "authority": "INFORMATION_ONLY"}
    return result


def _case_view(case, now):
    scope = _metadata_json(case["scope"])
    if not isinstance(scope, list) or not 1 <= len(scope) <= letters.MAX_EVIDENCE:
        _reject(CORRESPONDENCE_CORRUPT, "invalid correspondence scope")
    try:
        for path in scope:
            letters.check_path(path)
    except SailangError:
        _reject(CORRESPONDENCE_CORRUPT, "invalid correspondence scope path")
    if case["decision"] not in DECISIONS | {"PENDING"} or case["retained"] not in (0, 1):
        _reject(CORRESPONDENCE_CORRUPT, "invalid receiver decision metadata")
    expired = postoffice._parse_utc(case["expires_at"], code=CORRESPONDENCE_CORRUPT) <= \
        postoffice._parse_utc(now, code="BAD_CLOCK")
    return {name: case[name] for name in (
        "id", "envelope_id", "lineage", "sender", "sender_work", "recipient_work", "issue",
        "expires_at", "decision", "reason", "reviewed_at", "updated_at")} | {
            "scope": scope, "retained": bool(case["retained"]), "expired": expired,
            "actionable": not expired and case["decision"] not in TERMINAL,
            "evidence_recheck_required": True}


def _metadata_json(raw):
    try:
        return json.loads(raw)
    except (ValueError, TypeError, RecursionError):
        _reject(CORRESPONDENCE_CORRUPT, "invalid correspondence metadata JSON")


def desk(workspace, *, lineage, work, scope=None, budget=20, cursor=0, inbox_cursor=None,
         context=None, continuation=None, clock=None):
    """Keyless bounded discovery of unread mail, unfinished decisions and reserve.

    Two independent cursors cover the index and receiver database. No body is
    opened, no evidence file is read, no database is created by this query.
    """
    participants._check_lineage(lineage)
    if not isinstance(work, str) or not letters._WORK.fullmatch(work):
        _reject(letters.BAD_LETTER, "desk needs an exact Work id")
    if (isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= MAX_PAGE
            or isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0):
        _reject(letters.BAD_LETTER, "desk page budget is 1..100 and cursor is a nonnegative integer")
    watched = [] if scope is None else scope
    if not isinstance(watched, list) or len(watched) > letters.MAX_EVIDENCE:
        _reject(letters.BAD_LETTER, "desk scope is a bounded list of exact files")
    for path in watched:
        letters.check_path(path)
    witness = {"lineage": lineage, "work": work, "scope": sorted(set(watched)),
               "workspace": str(Path(workspace.root).resolve()), "recipient_kid": workspace.recipient_kid}
    context_id = "sha256:" + hashlib.sha256(letters.encode(witness).encode("utf-8")).hexdigest()
    scan_inbox = scan_cases = True
    if continuation is not None:
        if not isinstance(continuation, str) or len(continuation) > 1024 or cursor != 0 or inbox_cursor is not None:
            _reject(letters.BAD_LETTER, "use one bounded continuation, without raw cursors")
        try:
            token = json.loads(base64.b64decode(continuation, altchars=b"-_", validate=True))
        except (ValueError, UnicodeError, RecursionError):
            _reject(letters.BAD_LETTER, "invalid discovery continuation")
        if (not isinstance(token, dict) or set(token) != {"schema", "context", "cases", "inbox"}
                or token["schema"] != "SAIMAIL_DESK_CURSOR_1"):
            _reject(letters.BAD_LETTER, "unknown discovery continuation")
        context = token["context"]
        for field in ("cases", "inbox"):
            if token[field] is not None and (type(token[field]) is not int or token[field] < 0):
                _reject(letters.BAD_LETTER, "invalid discovery cursor")
        scan_cases, scan_inbox = token["cases"] is not None, token["inbox"] is not None
        cursor, inbox_cursor = token["cases"] or 0, token["inbox"]
    if context is not None and context != context_id:
        _reject(LETTER_CONTEXT_MISMATCH, "discovery context changed; restart without continuation")
    if (cursor != 0 or inbox_cursor not in (None, 0)) and context is None:
        _reject(letters.BAD_LETTER, "raw continuation cursors require their discovery context")
    now = _now(clock)
    page = (ws.query_inbox(workspace, topic=letters.topic(lineage, work), state=postoffice.UNREAD,
                           scan_budget=budget, cursor=inbox_cursor, clock=clock) if scan_inbox
            else {"items": [], "rows_examined": 0, "cursor": None})
    cases = []
    examined = 0
    case_cursor = None
    with _db(workspace) as db:
        if db is not None and scan_cases:
            # Fetch one sentinel to distinguish completion from a full page.
            rows = db.execute("SELECT * FROM cases WHERE lineage=? AND id>? ORDER BY id LIMIT ?",
                              (lineage, cursor, budget + 1)).fetchall()
            examined = min(len(rows), budget)
            for row in rows[:budget]:
                view = _case_view(row, now)
                in_work = view["recipient_work"] == work
                in_reserve = view["retained"] and bool(set(watched) & set(view["scope"]))
                if not view["expired"] and ((in_work and view["actionable"]) or in_reserve):
                    view["match"] = "SUCCESSOR_RESERVE" if in_reserve else "CURRENT_WORK"
                    cases.append(view)
            if len(rows) > budget:
                case_cursor = rows[budget - 1]["id"]
    next_page = None
    if case_cursor is not None or page["cursor"] is not None:
        next_page = base64.urlsafe_b64encode(letters.encode({"schema": "SAIMAIL_DESK_CURSOR_1",
            "context": context_id, "cases": case_cursor, "inbox": page["cursor"]}).encode("utf-8")).decode("ascii")
    return ws.command_result("letter-desk", "OK", workspace=workspace, items=page["items"],
                             cases=cases, rows_examined=page["rows_examined"],
                             cases_examined=examined, cursor=case_cursor, context=context_id,
                             inbox_cursor=page["cursor"],
                             continuation=next_page, complete=next_page is None,
                             complete_from_start=continuation is None and cursor == 0
                             and inbox_cursor in (None, 0) and next_page is None,
                             detail="metadata only; reserve evidence must be rechecked by explicit review")


def metrics(workspace, *, lineage, clock=None):
    """Lifetime dispositions plus dated, seven-day informational feedback.

    Live ACCEPTED/DEFERRED signals require unexpired relevance. Recent terminal
    assessments can explain even an expired letter; they never revive it.
    Review, report and identical retries do not renew the assessment timestamp.
    """
    participants._check_lineage(lineage)
    now = _now(clock)
    instant = postoffice._parse_utc(now, code="BAD_CLOCK")
    try:
        since = instant - timedelta(days=FEEDBACK_WINDOW_DAYS)
    except OverflowError:
        _reject("BAD_CLOCK", "feedback window precedes the supported calendar")
    counts = {state: 0 for state in sorted(DECISIONS | {"PENDING"})}
    reasons = {state: {reason: 0 for reason in sorted(REASONS[state])} for state in sorted(DECISIONS)}
    excluded = {name: 0 for name in ("PENDING", "FUTURE_ASSESSMENT", "OUTSIDE_WINDOW", "LETTER_EXPIRED")}
    signals = {}
    retained = 0
    with _db(workspace) as db:
        if db is not None:
            db.execute("BEGIN")  # all counts describe one read snapshot
            for row in db.execute("SELECT decision, reason, updated_at, expires_at, COUNT(*) AS n "
                                  "FROM cases WHERE lineage=? GROUP BY decision, reason, updated_at, expires_at",
                                  (lineage,)):
                state, reason = row["decision"], row["reason"]
                if state not in counts or (state == "PENDING" and reason is not None) or (
                        state != "PENDING" and reason not in reasons[state]):
                    _reject(CORRESPONDENCE_CORRUPT, "invalid receiver disposition")
                counts[state] += row["n"]
                if state != "PENDING":
                    reasons[state][reason] += row["n"]
                at = postoffice._parse_utc(row["updated_at"], code=CORRESPONDENCE_CORRUPT)
                expires = postoffice._parse_utc(row["expires_at"], code=CORRESPONDENCE_CORRUPT)
                omission = ("PENDING" if state == "PENDING" else
                            "FUTURE_ASSESSMENT" if at > instant else
                            "OUTSIDE_WINDOW" if at < since else
                            "LETTER_EXPIRED" if state not in TERMINAL and expires <= instant else None)
                if omission is not None:
                    excluded[omission] += row["n"]
                    continue
                key = (state, reason)
                if key not in signals:
                    signals[key] = {"decision": state, "reason": reason, "count": 0,
                                    "first_at": row["updated_at"], "last_at": row["updated_at"],
                                    "kind": "ASSESSMENT_ONLY" if state in TERMINAL else "UNEXPIRED_RELEVANCE"}
                signal = signals[key]
                signal["count"] += row["n"]
                signal["first_at"] = min(signal["first_at"], row["updated_at"])
                signal["last_at"] = max(signal["last_at"], row["updated_at"])
            retained = db.execute("SELECT COUNT(*) FROM cases WHERE lineage=? AND retained=1",
                                  (lineage,)).fetchone()[0]
    total = sum(counts.values())
    hints = [{"decision": state, "reason": reason, "count": count,
              "suggestion": FEEDBACK_HINTS[reason], "authority": "INFORMATION_ONLY"}
             for state, breakdown in reasons.items() for reason, count in breakdown.items()
             if count and reason in FEEDBACK_HINTS]
    active = [signals[key] for key in sorted(signals)]
    for signal in active:
        if signal["reason"] in FEEDBACK_HINTS:
            signal["suggestion"] = FEEDBACK_HINTS[signal["reason"]]
    temporal = {"schema": FEEDBACK_SCHEMA, "observed_at": now,
                "window_start": postoffice._format_utc(since), "window_days": FEEDBACK_WINDOW_DAYS,
                "basis": "LATEST_EXPLICIT_ASSESSMENT_AT", "active": active, "excluded": excluded,
                "authority": "INFORMATION_ONLY", "automatic_execution": False}
    return ws.command_result("letter-metrics", "OK", workspace=workspace,
                             metrics={"reviewed": total, "decisions": counts, "retained": retained,
                                      "reasons": reasons, "feedback_hints": hints,
                                      "feedback_hints_scope": "LIFETIME_HISTORY",
                                      "feedback_signals": temporal,
                                      "resolved_fraction": counts["RESOLVED"] / total if total else None,
                                      "basis": "EXPLICIT_RECEIVER_DECISIONS", "model_improvement_proven": False},
                             detail="receiver-recorded outcomes; no claim about model intelligence or universal utility")


__all__ = ["DECISIONS", "REASONS", "decide", "desk", "dispatch", "metrics", "report", "retain", "review"]
