"""Bounded host-side subprocess seam, outside the inert protocol library.

Callers supply a trusted installed executable (or a Python/module argv prefix).
The peer can offer capabilities, never commands to execute. All operations use
the client's own allowlist, shell=False, no stdin and no password environment.
Failure is informational DEGRADED and never drives a host's Work lifecycle.
"""

from __future__ import annotations

import json
import re
import subprocess
import threading
from datetime import UTC, datetime, timedelta
from pathlib import PurePosixPath

from saimail.host_contract import SCHEMA, contract

MAX_OUTPUT_BYTES = 256 * 1024
_COMMANDS = contract()["commands"]
_STATUSES = frozenset({"OK", "LETTER_REVIEWED", "LETTER_DECIDED", "LETTER_RETAINED",
                       "DELIVERED", "PENDING", "RETRY_WAIT", "NEEDS_ACTION", "NOTIFY_SUPPRESSED"})
FOCUS_SCHEMA = "SAIMAIL_HOST_FOCUS_1"
# A version-1 consumer vocabulary, independent of the peer implementation.
_REASONS = {
    "ACCEPTED": {"ACTION_PLANNED"}, "DEFERRED": {"WAITING_DEPENDENCY", "OUTSIDE_CURRENT_WORK"},
    "DECLINED": {"ALREADY_KNOWN", "NOT_ACTIONABLE", "WRONG_RECIPIENT", "OUTSIDE_SCOPE"},
    "RESOLVED": {"ACTION_TAKEN"}, "STALE": {"CONDITION_CHANGED", "EVIDENCE_CHANGED", "EXPIRED"},
}
_HINTS = {
    "ALREADY_KNOWN": "RECHECK_EXISTING_RESULTS", "NOT_ACTIONABLE": "ADD_REPRODUCTION_OR_DECISION_CRITERION",
    "WRONG_RECIPIENT": "CHECK_WORK_OWNER", "OUTSIDE_SCOPE": "NARROW_RECIPIENT_SCOPE",
    "WAITING_DEPENDENCY": "WAIT_FOR_DEPENDENCY_EVIDENCE", "OUTSIDE_CURRENT_WORK": "MATCH_CURRENT_WORK",
    "CONDITION_CHANGED": "RECHECK_CONDITION", "EVIDENCE_CHANGED": "REHASH_AND_REVIEW",
    "EXPIRED": "REFRESH_RELEVANCE_BEFORE_RESEND",
}
_HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
_WORK = re.compile(r"T-[0-9]+\Z")


def _degraded(reason, *, code=None):
    return {"state": "DEGRADED", "reason": reason, "code": code,
            "authority": "INFORMATION_ONLY"}


def _unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate field")
        value[key] = item
    return value


def _bounded_text(value, maximum=96):
    if not isinstance(value, str) or not value or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError("invalid text")
    return value


def _count(value, maximum=None):
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise ValueError("invalid count")
    return value


def _instant(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", value):
        raise ValueError("invalid UTC assessment time")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def _feedback_signals(value, metrics):
    """Version-1 consumer validates dates and rebuilds suggestions locally."""
    if value is None:
        return {"state": "UNKNOWN", "active": []}
    if (value["schema"] != "SAIMAIL_FEEDBACK_SIGNALS_1" or value["window_days"] != 7
            or type(value["window_days"]) is not int or value["basis"] != "LATEST_EXPLICIT_ASSESSMENT_AT"
            or value["authority"] != "INFORMATION_ONLY" or value["automatic_execution"] is not False):
        raise ValueError("unsupported feedback age")
    observed, start = _instant(value["observed_at"]), _instant(value["window_start"])
    if observed - start != timedelta(days=7):
        raise ValueError("mixed feedback window")
    source = value["active"]
    if not isinstance(source, list) or len(source) > 11:
        raise ValueError("unbounded feedback")
    active, seen = [], set()
    for row in source:
        decision, reason = row["decision"], row["reason"]
        if decision not in _REASONS or reason not in _REASONS[decision] or (decision, reason) in seen:
            raise ValueError("invalid feedback reason")
        seen.add((decision, reason))
        count = _count(row["count"], metrics["reasons"][decision][reason])
        first, last = _instant(row["first_at"]), _instant(row["last_at"])
        kind = "UNEXPIRED_RELEVANCE" if decision in {"ACCEPTED", "DEFERRED"} else "ASSESSMENT_ONLY"
        if count == 0 or not start <= first <= last <= observed or row["kind"] != kind:
            raise ValueError("invalid feedback eligibility")
        item = {"decision": decision, "reason": reason, "count": count,
                "first_at": row["first_at"], "last_at": row["last_at"], "kind": kind}
        if reason in _HINTS:
            item["suggestion"] = _HINTS[reason]
        active.append(item)
    excluded = {name: _count(value["excluded"][name]) for name in
                ("PENDING", "FUTURE_ASSESSMENT", "OUTSIDE_WINDOW", "LETTER_EXPIRED")}
    if (sum(row["count"] for row in active) + sum(excluded.values()) != metrics["reviewed"]
            or excluded["PENDING"] != metrics["decisions"]["PENDING"]):
        raise ValueError("inconsistent feedback partition")
    return {"state": "KNOWN", "observed_at": value["observed_at"], "window_start": value["window_start"],
            "window_days": 7, "basis": "LATEST_EXPLICIT_ASSESSMENT_AT", "active": active, "excluded": excluded}


def _focus(data, seat, arguments):
    """Project metadata; construct operations locally and retain coverage limits."""
    cycle, metrics, binding = data["cycle"], data["metrics"], data["saipen"]
    if (cycle["schema"] != "SAIMAIL_AGENT_CYCLE_1" or cycle["authority"] != "INFORMATION_ONLY"
            or cycle["automatic_execution"] is not False or not _HASH.fullmatch(cycle["context"])
            or binding["seat"] != seat or not re.fullmatch(r"lineage-[0-9a-f]{32}", binding["lineage"])
            or metrics["basis"] != "EXPLICIT_RECEIVER_DECISIONS"
            or metrics["model_improvement_proven"] is not False):
        raise ValueError("unsupported cycle")
    work, scope, continuation = cycle["work"], cycle["scope"], cycle["continuation"]
    if work is not None and not _WORK.fullmatch(work):
        raise ValueError("invalid Work")
    if not isinstance(scope, list) or len(scope) > 8:
        raise ValueError("invalid scope")
    for path in scope:
        _bounded_text(path, 512)
        if (PurePosixPath(path).is_absolute() or any(p in {"", ".", ".."} for p in path.split("/"))
                or "\\" in path or ":" in path):
            raise ValueError("invalid scope path")
    if continuation is not None:
        _bounded_text(continuation, 2048)
    complete, from_start = cycle["complete"], cycle["complete_from_start"]
    if (type(complete) is not bool or type(from_start) is not bool or (from_start and not complete)
            or (complete and continuation is not None)):
        raise ValueError("invalid coverage")
    reading, seen = [], set()
    page = data["desk"]
    rows = cases = 0
    if work is None:
        if page is not None or complete or from_start or continuation is not None:
            raise ValueError("unbound coverage")
    else:
        if (type(page["complete"]) is not bool or type(page["complete_from_start"]) is not bool
                or page["complete"] != complete or page["complete_from_start"] != from_start
                or (not complete and continuation is None)):
            raise ValueError("mixed coverage")
        rows = _count(page["rows_examined"], 100)
        cases = _count(page["cases_examined"], 100)
        if (not isinstance(page["items"], list) or len(page["items"]) > rows
                or not isinstance(page["cases"], list) or len(page["cases"]) > cases):
            raise ValueError("unbounded page")
        for row, reason in ([(row, "CURRENT_MAIL") for row in page["items"]]
                            + [(row, row["match"]) for row in page["cases"]]):
            envelope = row["envelope_id"]
            if not _HASH.fullmatch(envelope) or reason not in {"CURRENT_MAIL", "CURRENT_WORK", "SUCCESSOR_RESERVE"}:
                raise ValueError("invalid reading reference")
            if envelope not in seen:
                seen.add(envelope)
                reading.append({"envelope_id": envelope, "reason": reason})
    decisions = {name: _count(metrics["decisions"][name]) for name in ["PENDING", *_REASONS]}
    reviewed = _count(metrics["reviewed"])
    if sum(decisions.values()) != reviewed:
        raise ValueError("inconsistent assessments")
    feedback = []
    for decision, reasons in _REASONS.items():
        counts = {reason: _count(metrics["reasons"][decision][reason]) for reason in sorted(reasons)}
        if sum(counts.values()) != decisions[decision]:
            raise ValueError("inconsistent reasons")
        for reason, count in counts.items():
            if count:
                value = {"decision": decision, "reason": reason, "count": count}
                if reason in _HINTS:
                    value["suggestion"] = _HINTS[reason]
                feedback.append(value)
    budget = 20
    for index, part in enumerate(arguments):
        if part == "--budget":
            budget = int(arguments[index + 1])
        elif part.startswith("--budget="):
            budget = int(part.split("=", 1)[1])
    if not 1 <= budget <= 100:
        raise ValueError("invalid budget")
    if reading:
        next_action = {"action": "REVIEW", "operation": "review",
                       "arguments": ["--envelope", reading[0]["envelope_id"]]}
    elif continuation:
        resume = ["--work", work]
        for path in scope:
            resume.extend(["--scope", path])
        resume.extend(["--budget", str(budget), "--continuation", continuation])
        next_action = {"action": "CONTINUE_DISCOVERY", "operation": "cycle", "arguments": resume}
    else:
        next_action = {"action": "CHOOSE_WORK" if work is None else "CONTINUE_WORK"}
    host = {"seat": _bounded_text(binding["seat"]), "lineage": binding["lineage"],
            "phase": _bounded_text(binding["phase"]), "task": binding["task"],
            "last_event": _bounded_text(binding["last_event"]), "blocker": binding["blocker"]}
    if host["task"] is not None:
        _bounded_text(host["task"])
    if host["blocker"] is not None:
        _bounded_text(host["blocker"], 300)
    return {"schema": FOCUS_SCHEMA, "state": "OK", "context": cycle["context"], "host": host,
            "work": work, "scope": list(scope), "reading": reading, "next_action": next_action,
            "coverage": {"complete": complete, "complete_from_start": from_start,
                         "rows_examined": rows, "cases_examined": cases},
            "continuation": continuation, "reviewed": reviewed, "decisions": decisions,
            "retained": _count(metrics["retained"]), "model_improvement_proven": False,
            "feedback": feedback, "feedback_basis": "LATEST_RECEIVER_ASSESSMENT",
            "feedback_scope": "LIFETIME_HISTORY",
            "feedback_signals": _feedback_signals(metrics.get("feedback_signals"), metrics),
            "authority": "INFORMATION_ONLY", "automatic_execution": False}


def project_focus(data, seat, arguments=()):
    """Project a cycle for the CLI, with a locally constructed focus resume."""
    view = _focus(data, seat, arguments)
    if view["next_action"]["action"] == "CONTINUE_DISCOVERY":
        view["next_action"]["operation"] = "focus"
    return view


def _from_focus(value, seat, arguments):
    """Validate compact metadata through the independent cycle consumer.

    Expand only closed metadata into the existing validator; never forward a
    peer operation, body, suggestion or unknown field into the returned view.
    """
    if (value["schema"] != FOCUS_SCHEMA or value["state"] != "OK"
            or value["authority"] != "INFORMATION_ONLY" or value["automatic_execution"] is not False
            or value["model_improvement_proven"] is not False
            or value["feedback_basis"] != "LATEST_RECEIVER_ASSESSMENT"
            or value["feedback_scope"] != "LIFETIME_HISTORY"):
        raise ValueError("unsupported compact focus")
    coverage = value["coverage"]
    rows = _count(coverage["rows_examined"], 100)
    examined_cases = _count(coverage["cases_examined"], 100)
    reading = value["reading"]
    if not isinstance(reading, list) or len(reading) > 200:
        raise ValueError("unbounded compact reading")
    items, cases, seen = [], [], set()
    for row in reading:
        envelope, reason = row["envelope_id"], row["reason"]
        if not _HASH.fullmatch(envelope) or envelope in seen:
            raise ValueError("invalid compact reference")
        seen.add(envelope)
        if reason == "CURRENT_MAIL":
            items.append({"envelope_id": envelope})
        elif reason in {"CURRENT_WORK", "SUCCESSOR_RESERVE"}:
            cases.append({"envelope_id": envelope, "match": reason})
        else:
            raise ValueError("invalid compact reading reason")
    reasons = {decision: {reason: 0 for reason in vocabulary} for decision, vocabulary in _REASONS.items()}
    feedback = value["feedback"]
    if not isinstance(feedback, list) or len(feedback) > 11:
        raise ValueError("unbounded compact feedback")
    for row in feedback:
        decision, reason = row["decision"], row["reason"]
        if decision not in reasons or reason not in reasons[decision] or reasons[decision][reason] != 0:
            raise ValueError("invalid compact assessment")
        count = _count(row["count"])
        if count == 0:
            raise ValueError("empty compact assessment")
        reasons[decision][reason] = count
    temporal = value["feedback_signals"]
    if temporal["state"] == "KNOWN":
        temporal = {**temporal, "schema": "SAIMAIL_FEEDBACK_SIGNALS_1",
                    "authority": "INFORMATION_ONLY", "automatic_execution": False}
    elif temporal["state"] == "UNKNOWN" and temporal["active"] == []:
        temporal = None
    else:
        raise ValueError("invalid compact temporal state")
    page = {"items": items, "cases": cases, "complete": coverage["complete"],
            "complete_from_start": coverage["complete_from_start"],
            "rows_examined": rows, "cases_examined": examined_cases}
    if value["work"] is None:
        if reading or rows != 0 or examined_cases != 0:
            raise ValueError("unbound compact coverage")
        page = None
    data = {"saipen": value["host"], "desk": page,
            "metrics": {"decisions": value["decisions"], "reviewed": value["reviewed"],
                        "retained": value["retained"], "reasons": reasons, "feedback_signals": temporal,
                        "basis": "EXPLICIT_RECEIVER_DECISIONS", "model_improvement_proven": False},
            "cycle": {"schema": "SAIMAIL_AGENT_CYCLE_1", "context": value["context"],
                      "work": value["work"], "scope": value["scope"], "continuation": value["continuation"],
                      "complete": coverage["complete"], "complete_from_start": coverage["complete_from_start"],
                      "authority": "INFORMATION_ONLY", "automatic_execution": False}}
    return project_focus(data, seat, arguments)


def _invoke(argv, timeout):
    """Drain both pipes within a fixed byte cap; terminate oversize or slow peers."""
    try:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, shell=False,
                                   **({"creationflags": subprocess.CREATE_NO_WINDOW}
                                      if hasattr(subprocess, "CREATE_NO_WINDOW") else {}))
    except OSError:
        return _degraded("UNAVAILABLE")
    buffers = [bytearray(), bytearray()]
    overflow = threading.Event()
    pipe_error = threading.Event()

    def drain(stream, buffer):
        try:
            while True:
                chunk = stream.read(8192)
                if not chunk:
                    break
                if len(buffer) + len(chunk) > MAX_OUTPUT_BYTES:
                    overflow.set()
                    try:
                        process.kill()
                    except OSError:
                        pass
                    break
                buffer.extend(chunk)
        except OSError:
            pipe_error.set()
        finally:
            stream.close()

    readers = [threading.Thread(target=drain, args=(stream, buffer), daemon=True)
               for stream, buffer in zip((process.stdout, process.stderr), buffers, strict=True)]
    for reader in readers:
        reader.start()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        for reader in readers:
            reader.join(timeout=1)
        return _degraded("TIMEOUT")
    for reader in readers:
        reader.join(timeout=1)
    if pipe_error.is_set() or any(reader.is_alive() for reader in readers):
        return _degraded("PIPE_UNAVAILABLE")
    if overflow.is_set():
        return _degraded("OUTPUT_BUDGET")
    try:
        result = json.loads(buffers[0].decode("utf-8"), object_pairs_hook=_unique)
    except (ValueError, UnicodeError, RecursionError):
        return _degraded("INVALID_JSON")
    if not isinstance(result, dict):
        return _degraded("INVALID_JSON")
    if process.returncode != 0:
        # Never forward stderr, bodies, credentials or remote execution hints.
        code = result.get("status") or result.get("code")
        return _degraded("REFUSED", code=code if isinstance(code, str) and len(code) <= 96 else None)
    return {"state": "OK", "data": result, "authority": "INFORMATION_ONLY"}


class HostClient:
    def __init__(self, prefix, *, workspace, project_root, seat, timeout=10):
        if (not isinstance(prefix, (list, tuple)) or not prefix
                or any(not isinstance(part, str) or not part for part in prefix)
                or isinstance(timeout, bool) or not 0 < timeout <= 30):
            raise ValueError("trusted executable argv and a timeout of at most 30 seconds are required")
        self.prefix = list(prefix)
        self.common = ["--workspace", str(workspace), "--project-root", str(project_root), "--seat", str(seat)]
        self.timeout = timeout
        self.negotiated = False
        self.features = {}
        self.seat = str(seat)

    def negotiate(self):
        self.negotiated = False
        self.features = {}
        answer = _invoke(self.prefix + ["--contract"], self.timeout)
        if answer["state"] != "OK":
            return answer
        data = answer["data"]
        if data.get("schema") != SCHEMA or type(data.get("version")) is not int or data["version"] != 1:
            return _degraded("SCHEMA_MISMATCH")
        features = data.get("features")
        if (not isinstance(features, dict)
                or any(type(features.get(name)) is not int or features[name] != 1
                       for name in ("correspondence", "keyless_desk", "receiver_decisions", "successor_reserve"))):
            return _degraded("MISSING_FEATURE")
        self.negotiated = True
        self.features = dict(features)
        return answer

    def focus(self, arguments=(), *, prefer_cli=False):
        """Observe one cycle, then return a compact view for the agent's context.

        With prefer_cli, negotiate compact transport and validate it locally;
        older peers fall back to the original cycle projection. No body opens
        or suggested action runs. The full request API remains available.
        """
        if type(prefer_cli) is not bool:
            raise ValueError("prefer_cli must be an explicit boolean")
        compact = False
        if prefer_cli:
            if not self.negotiated:
                answer = self.negotiate()
                if answer["state"] != "OK":
                    return answer
            compact = type(self.features.get("cli_focus")) is int and self.features["cli_focus"] == 1
        answer = self.request("focus" if compact else "cycle", arguments)
        if answer["state"] != "OK":
            return answer
        try:
            return (_from_focus(answer["data"]["focus"], self.seat, arguments) if compact else
                    _focus(answer["data"], self.seat, arguments))
        except (KeyError, TypeError, ValueError, IndexError):
            return _degraded("INVALID_FOCUS" if compact else "INVALID_CYCLE")

    def request(self, action, arguments=()):
        """Trusted host arguments only; sealed letter contents never reach argv."""
        if action not in _COMMANDS or action == "health":
            raise ValueError("unknown correspondence operation")
        if (not isinstance(arguments, (list, tuple)) or len(arguments) > 64
                or any(not isinstance(part, str) or len(part) > 4096 for part in arguments)
                or any(part.split("=", 1)[0] in {"--workspace", "--project-root", "--seat", "--unlock"}
                       for part in arguments)):
            raise ValueError("operation arguments cannot replace host binding or request a password")
        if not self.negotiated:
            answer = self.negotiate()
            if answer["state"] != "OK":
                return answer
        optional = {"cycle": "agent_cycle", "focus": "cli_focus"}.get(action)
        if optional and (type(self.features.get(optional)) is not int or self.features[optional] != 1):
            return _degraded("MISSING_FEATURE")
        answer = _invoke(self.prefix + ["--json", *_COMMANDS[action], *self.common, *arguments], self.timeout)
        if answer["state"] != "OK":
            return answer
        data = answer["data"]
        status = data.get("status")
        safe_code = status if isinstance(status, str) and len(status) <= 96 else None
        if data.get("schema") != "LOCAL_WORKSPACE_COMMAND_1" or safe_code not in _STATUSES:
            return _degraded("UNKNOWN_RESULT", code=safe_code)
        if data.get("ok") is not True:
            return _degraded("REFUSED", code=data.get("status"))
        return answer


__all__ = ["FOCUS_SCHEMA", "HostClient", "project_focus"]
