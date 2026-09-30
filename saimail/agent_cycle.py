"""One bounded, keyless work entry for independent agent hosts.

The host chooses when to observe, open and act. Returned actions are fixed
reading suggestions, never executable mail content or lifecycle authority.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from sailang import SailangError
from saimail import correspondence, letters, saipen_bridge
from saimail import workspace as ws

SCHEMA = "SAIMAIL_AGENT_CYCLE_1"
CURSOR_SCHEMA = "SAIMAIL_AGENT_CYCLE_CURSOR_1"
MAX_CURSOR = 2048


def _continuation(token, expected_context):
    if token is None:
        return None
    if not isinstance(token, str) or len(token) > MAX_CURSOR:
        raise SailangError(letters.BAD_LETTER, "cycle continuation must be a bounded token")
    try:
        value = json.loads(base64.b64decode(token, altchars=b"-_", validate=True),
                           object_pairs_hook=letters._unique_pairs)
    except (ValueError, UnicodeError, RecursionError):
        raise SailangError(letters.BAD_LETTER, "invalid cycle continuation") from None
    if (not isinstance(value, dict) or set(value) != {"schema", "context", "desk"}
            or value["schema"] != CURSOR_SCHEMA or not isinstance(value["desk"], str)
            or len(value["desk"]) > 1024):
        raise SailangError(letters.BAD_LETTER, "unknown cycle continuation")
    if value["context"] != expected_context:
        raise SailangError(saipen_bridge.SAIPEN_CONTEXT_CHANGED,
                           "cycle work context changed; restart without continuation")
    return value["desk"]


def entry(workspace, state_path, identity_path=None, *, seat=None, work=None, scope=None,
          budget=20, continuation=None, clock=None):
    """Observe work mail, unfinished decisions, reserve and feedback in one call.

    At most budget inbox rows and budget case rows plus one sentinel are read.
    No content is opened, evidence hashed, database created or decision changed.
    A continuation binds the desk cursors to the fresh observed host context.
    """
    if type(budget) is not int or not 1 <= budget <= correspondence.MAX_PAGE:
        raise SailangError(letters.BAD_LETTER, "cycle page budget is 1..100")
    watched = [] if scope is None else scope
    if not isinstance(watched, list) or len(watched) > letters.MAX_EVIDENCE:
        raise SailangError(letters.BAD_LETTER, "cycle scope is a bounded list of exact files")
    for path in watched:
        letters.check_path(path)
    observed_at = correspondence._now(clock)
    observed_clock = lambda: observed_at
    admission = saipen_bridge.enter(workspace, state_path, identity_path, seat=seat)
    binding = admission["saipen"]
    current = binding.get("task") or ""
    selected = work if work is not None else (current if letters._WORK.fullmatch(current) else None)
    if selected is not None:
        letters.topic(binding["lineage"], selected)
    witness = {"schema": SCHEMA, "saipen": binding, "work": selected,
               "scope": sorted(set(watched)), "workspace": str(Path(workspace.root).resolve()),
               "recipient_kid": workspace.recipient_kid,
               "state_path": str(Path(state_path).resolve()),
               "identity_path": str(Path(identity_path).resolve()) if identity_path is not None else None}
    context = "sha256:" + hashlib.sha256(letters.encode(witness).encode("utf-8")).hexdigest()
    desk_cursor = _continuation(continuation, context)
    page = (correspondence.desk(workspace, lineage=binding["lineage"], work=selected,
                                scope=watched, budget=budget, continuation=desk_cursor, clock=observed_clock)
            if selected is not None else None)
    measured = correspondence.metrics(workspace, lineage=binding["lineage"], clock=observed_clock)["metrics"]
    if saipen_bridge._admission_binding(state_path, identity_path, seat) != binding:
        raise SailangError(saipen_bridge.SAIPEN_CONTEXT_CHANGED,
                           "work context changed during cycle observation; restart")
    actions, seen = [], set()
    for row, reason in ([] if page is None else (
            [(row, "CURRENT_MAIL") for row in page["items"]]
            + [(row, row["match"]) for row in page["cases"]])):
        if row["envelope_id"] in seen:
            continue
        seen.add(row["envelope_id"])
        actions.append({"action": "REVIEW", "reason": reason, "envelope_id": row["envelope_id"],
                        "command": ["saipen", "letter", "review"],
                        "arguments": ["--envelope", row["envelope_id"]], "authority": "INFORMATION_ONLY"})
    next_page = None
    if page is not None and page["continuation"] is not None:
        next_page = base64.urlsafe_b64encode(letters.encode({
            "schema": CURSOR_SCHEMA, "context": context,
            "desk": page["continuation"]}).encode("utf-8")).decode("ascii")
    if actions:
        next_action = actions[0]
    elif next_page:
        arguments = ["--work", selected]
        for path in watched:
            arguments.extend(["--scope", path])
        arguments.extend(["--budget", str(budget), "--continuation", next_page])
        next_action = {"action": "CONTINUE_DISCOVERY", "reason": "PAGE_BUDGET",
                       "command": ["saipen", "letter", "cycle"], "arguments": arguments,
                       "authority": "INFORMATION_ONLY"}
    else:
        next_action = {"action": "CHOOSE_WORK" if page is None else "CONTINUE_WORK",
                       "authority": "INFORMATION_ONLY"}
    return ws.command_result(
        "agent-cycle", "OK", workspace=workspace, saipen=binding, desk=page, metrics=measured,
        cycle={"schema": SCHEMA, "context": context, "work": selected, "scope": watched,
               "actions": actions, "next_action": next_action, "continuation": next_page,
               "complete": page is not None and page["complete"],
               "complete_from_start": page is not None and page["complete_from_start"],
               "authority": "INFORMATION_ONLY", "automatic_execution": False},
        detail="metadata only; host chooses when to review and act; evidence must be rechecked")


__all__ = ["SCHEMA", "entry"]
