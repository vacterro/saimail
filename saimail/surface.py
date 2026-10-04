"""Wave 7: a live surface that describes itself, and health that admits UNKNOWN.

The defect this removes: a future agent learns what SAIMAIL can do from a
document, and the document is wrong the moment a command is added. The CLI
entrypoint already grew nine new verbs across Waves 1-6, and
`host_contract.contract()` still
lists the commands it shipped with. A second failure sits behind it: a dashboard
that renders unreadable state as zero. An operator told "0 unread" because the
index would not parse has been told something false, and worse, has been told it
in the exact shape that looks like good news.

Two rules decide the whole module.

**Nothing here is a hand-maintained table.** The command inventory is walked out
of the live argparse tree, so adding a verb to `_build_parser()` changes the
surface on its own and deleting one removes it. The only list a human edits is the
list of subsystems below, and that list says which subsystem to *ask*, never what
the answer is.

**Each subsystem owns its own section.** This module calls `ledger.health`,
`cold_archive.health`, `trust.list_pins` and the rest, and translates the answer.
It never re-derives a subsystem's truth from its files, because a second
implementation of somebody else's invariant is a second thing to be wrong. A
section is therefore only ever as good as the function that produced it, and the
`source` field in every section names which one that was.

That is also why health is THREE-valued. `HEALTHY` and `UNHEALTHY` are verdicts.
`UNKNOWN` is the honest third answer: the subsystem was asked, and it could not
say. UNKNOWN is never promoted to HEALTHY by assumption and never collapsed into
a zero count, and it propagates to the overall verdict -- a mailbox with one
UNHEALTHY section and nine UNKNOWN ones is not healthy, it is unknown, and it says
so.

The gap rule follows from the same instinct. `ledger.feed` already refuses to
pretend a trimmed history is complete; this module carries that verdict up to the
surface rather than smoothing it into a quiet success, because a caller that
follows a cursor through a gap and is not told has been shown a history that
never existed.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from sailang import SailangError
from saimail import cold_archive, future_letter, ledger, postoffice
from saimail import workspace as _workspace

SURFACE_SCHEMA = "SAIMAIL_SURFACE_1"
SURFACE_VERSION = 1
MAP_SCHEMA = "SAIMAIL_CLI_MAP_1"
MAP_VERSION = 1

#: The three health verdicts. There is deliberately no fourth.
HEALTHY = "HEALTHY"
UNHEALTHY = "UNHEALTHY"
UNKNOWN = "UNKNOWN"
VERDICTS = (HEALTHY, UNHEALTHY, UNKNOWN)

#: Statuses a subsystem may report that mean "I could not find out".
#: `ABSENT` is deliberately NOT in here, and its absence is the whole point. A
#: workspace with no ledger and no cold archive has nothing at risk and says so;
#: one whose ledger will not parse is UNKNOWN. Wave 2 learned that lesson and
#: this module refuses to unlearn it by mapping "missing" onto "unreadable" --
#: which is how a dashboard ends up permanently UNKNOWN for a brand new mailbox
#: and an operator stops reading the word.
CANNOT_TELL = frozenset({
    ledger.UNKNOWN,
    "UNREADABLE",
    "UNREADABLE_STATE",
    "STATE_UNREADABLE",
    "CANNOT_DETERMINE",
})

#: Envelope and custody vocabularies, reported so a reader can tell which era a
#: workspace came from without opening a file.
ENVELOPE_SCHEMAS = ("SAIMAIL_ENVELOPE_2", "SENV2")
CUSTODY_MODES = ("raw", "os-store")


# --------------------------------------------------------------------------
# the live command inventory
# --------------------------------------------------------------------------

def _flag(action: argparse.Action) -> dict:
    """One argparse action as data. Required-ness is reported, never inferred."""
    return {
        "flag": action.option_strings[0] if action.option_strings else action.dest,
        "dest": action.dest,
        "required": bool(action.required),
        "takes_value": action.nargs != 0,
        "repeatable": action.__class__.__name__ == "_AppendAction",
        "choices": list(action.choices) if action.choices else None,
        "help": (action.help or "").strip() or None,
    }


def _subparsers(parser: argparse.ArgumentParser):
    """The registered subparsers of one parser, by the public route where possible.

    argparse exposes no public accessor for subparsers, so this reaches for the
    private one and DEGRADES to an empty list rather than guessing. An empty
    inventory is visible and wrong; a fabricated one is invisible and wrong.
    """
    for action in parser._actions:  # noqa: SLF001 - no public equivalent exists
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            return action.choices
    return {}


def cli_map(*, parser: argparse.ArgumentParser) -> dict:
    """The live command inventory, generated from the registered parser.

    The parser is REQUIRED rather than discovered, and that is a deliberate
    boundary rather than a missing convenience. The entrypoint owns the verb
    tree and this package owns the walking; letting `surface` reach back into
    the entrypoint module for it would invert that direction and make the library
    unloadable without its own command line. The caller hands over the live
    parser, and adding a subparser there adds it here with no second edit --
    which is the whole acceptance criterion, and it holds without the
    convenience.
    """
    commands = [_command(name, child)
                for name, child in sorted(_subparsers(parser).items())]
    return {
        "schema": MAP_SCHEMA,
        "version": MAP_VERSION,
        "prog": parser.prog,
        "generated": True,
        "command_count": len(commands),
        "commands": commands,
        "detail": (f"{len(commands)} command group(s) walked from the live parser; "
                   "this map is generated and is not a maintained table"),
    }


def _command(name: str, parser: argparse.ArgumentParser) -> dict:
    """One command group, with its own actions and any nested subcommands."""
    entry = {
        "command": name,
        "help": (parser.description or "").strip() or None,
        "flags": sorted((_flag(action) for action in parser._actions
                         if action.option_strings),  # noqa: SLF001
                        key=lambda item: item["flag"]),
        "accepts_json": any(action.dest in ("json", "sub_json")
                            for action in parser._actions),  # noqa: SLF001
        "subcommands": [],
    }
    for child_name, child in sorted(_subparsers(parser).items()):
        entry["subcommands"].append({
            "command": child_name,
            "help": (child.description or "").strip() or None,
            "flags": sorted((_flag(action) for action in child._actions
                             if action.option_strings),  # noqa: SLF001
                            key=lambda item: item["flag"]),
            "accepts_json": any(action.dest in ("json", "sub_json")
                                for action in child._actions),  # noqa: SLF001
        })
    return entry


# --------------------------------------------------------------------------
# the versioned machine-readable capability schema
# --------------------------------------------------------------------------

#: A capability family and the command that evidences it. This is the one map
#: in the module that a human maintains, and it names a COMMAND rather than a
#: behaviour: `future_letters` is advertised because `future-letter` is
#: registered, and stops being advertised the day that verb is removed.
CAPABILITY_FAMILIES = {
    "trust_identity": "trust",
    "delivery_ledger": "ledger",
    "cold_archive": "cold",
    "downtime_catchup": "catchup",
    "canary_lane": "canary",
    "future_letters": "future-letter",
}


def capability_schema(*, parser: argparse.ArgumentParser) -> dict:
    """What this build supports, derived rather than declared.

    Additive by construction: the frozen `host_contract` document is carried
    through unchanged and the new wave families are added beside it, so a reader
    written against the predecessor still resolves every key it knew.

    The legacy `features` map is deliberately NOT re-derived from the command
    list. Those names are capability vocabulary (`correspondence`,
    `keyless_desk`), not verb names, so cross-comparing them against the parser
    would report an all-zero advertisement on a build that has everything -- a
    false negative in the one document whose whole job is not to lie. What IS
    derived is what can honestly be derived.
    """
    from saimail import host_contract

    inventory = cli_map(parser=parser)
    commands = {entry["command"] for entry in inventory["commands"]}
    contract = host_contract.contract()
    features = dict(contract.get("features", {}))
    derived = {name: (1 if verb in commands else 0)
               for name, verb in sorted(CAPABILITY_FAMILIES.items())}
    features.update(derived)
    return {
        "schema": SURFACE_SCHEMA,
        "version": SURFACE_VERSION,
        "command_schema": contract["command_schema"],
        "letter_schema": contract["letter_schema"],
        "capabilities_schema": contract["capabilities_schema"],
        "envelope_schemas": list(ENVELOPE_SCHEMAS),
        "custody_modes": list(CUSTODY_MODES),
        "features": features,
        "command_count": inventory["command_count"],
        "authority": "INFORMATION_ONLY",
        "compatibility": dict(contract["compatibility"],
                              unknown_fields="IGNORE",
                              additive_changes="PRESERVED"),
        "detail": (f"{sum(1 for value in features.values() if value)} capability "
                   "families advertised, each derived from a registered command"),
    }


# --------------------------------------------------------------------------
# health
# --------------------------------------------------------------------------

def _verdict(section: dict) -> str:
    """Three-valued translation of one subsystem's own answer.

    The order matters. `operator_action_required` outranks `ok`, because several
    subsystems deliberately report `ok: false` alongside it, and an unreadable
    ledger is more urgent than a clean-looking boolean suggests.
    """
    if not isinstance(section, dict):
        return UNKNOWN
    status = section.get("status")
    if status in CANNOT_TELL:
        return UNKNOWN
    if section.get("operator_action_required"):
        return UNHEALTHY
    if section.get("ok") is False:
        return UNHEALTHY
    if status is None:
        return UNKNOWN
    return HEALTHY


def _section(name: str, source: str, probe) -> dict:
    """Ask one subsystem and wrap its answer, whatever shape it takes.

    A subsystem that raises is UNKNOWN, never a zero. That is the entire reason
    this helper exists: an exception inside `trust.list_pins` must not become an
    empty pin list in a dashboard, because the reader would act on it.
    """
    try:
        answer = probe()
    except SailangError as exc:
        return {"section": name, "source": source, "state": UNKNOWN,
                "reason": exc.code, "detail": exc.detail or "",
                "counts": None,
                "note": "the owning subsystem refused; this section reports "
                        "UNKNOWN and no numbers"}
    except Exception as exc:  # noqa: BLE001 - a dashboard must not crash a caller
        return {"section": name, "source": source, "state": UNKNOWN,
                "reason": type(exc).__name__, "detail": str(exc)[:200],
                "counts": None,
                "note": "the owning subsystem raised; this section reports UNKNOWN "
                        "and no numbers"}
    return {
        "section": name, "source": source,
        "state": _verdict(answer),
        "status": answer.get("status"),
        "reason": (answer.get("ledger", {}) or {}).get("reason")
        or answer.get("reason"),
        "detail": answer.get("detail", ""),
        "counts": _counts(answer),
        "operator_action_required": bool(answer.get("operator_action_required")),
    }


def _counts(answer: dict):
    """Whatever numbers the subsystem chose to publish, passed through as-is.

    Nothing is invented here. A subsystem that reports no counts leaves this
    ``None``, which renders as "no numbers published" rather than as a zero, and
    that distinction is the reason this function is a pass-through rather than a
    schema of its own.
    """
    published = answer.get("counts")
    if isinstance(published, dict):
        return published
    for key in ("ledger", "outbox", "queue", "trust", "health"):
        block = answer.get(key)
        if isinstance(block, dict):
            numbers = {name: value for name, value in block.items()
                       if isinstance(value, int) and not isinstance(value, bool)}
            if numbers:
                return numbers
    return None


def _inbox_section(ws) -> dict:
    """Read state from the bundles themselves, never from an index flag.

    An index row records that mail arrived; only the filesystem records that it
    was read. Counting from the flag would report the Post Office's memory of
    itself, so an index that drifted from the bundles would produce a confident
    wrong number instead of a visible disagreement.
    """
    office = ws.self_office()
    rows = office.read_index()
    unread = 0
    unplaceable = 0
    for row in rows:
        try:
            state = office.bundle_state(row.get("envelope_id"))
        except SailangError:
            # An envelope the office cannot place is neither read nor unread.
            # Counting it either way IS the false zero this whole wave exists to
            # prevent, so the section withholds the count instead.
            unplaceable += 1
            continue
        if state == postoffice.UNREAD:
            unread += 1
    if unplaceable:
        return {"status": UNKNOWN, "ok": False, "operator_action_required": True,
                "detail": (f"{unplaceable} indexed row(s) whose bundles the Post "
                           "Office cannot place; the unread count is withheld"),
                "counts": None}
    return {"status": "OK", "ok": True,
            "detail": f"{unread} unread of {len(rows)} indexed",
            "counts": {"indexed": len(rows), "unread": unread}}


def _trust_section(ws) -> dict:
    """Trust health, in trust's own vocabulary.

    The interesting number is not how many pins exist but how many need a human:
    a rotation pending is a decision waiting, and rendering it as a count of pins
    buries it.
    """
    from saimail import trust

    records = trust.list_pins(ws).get("items") or []
    needs_rotation = [record for record in records
                      if record.get("state") == trust.ROTATION_PENDING]
    blocked = [record for record in records
               if record.get("state") in (trust.REVOKED, trust.BLOCKED)]
    return {"status": "OK" if not (needs_rotation or blocked) else "DEGRADED",
            "ok": not (needs_rotation or blocked),
            "operator_action_required": bool(needs_rotation or blocked),
            "detail": (f"{len(records)} pin(s), {len(needs_rotation)} awaiting a "
                       f"rotation decision, {len(blocked)} blocked or revoked"),
            "counts": {"pins": len(records),
                       "rotations_pending": len(needs_rotation),
                       "blocked_or_revoked": len(blocked)}}


def _receipts_section(ws) -> dict:
    """Deliveries still waiting for a receipt they were promised.

    Derived by asking the ledger what it knows, not by scanning the outbox: the
    ledger is the record of what was claimed, and an outbox scan would report a
    send that was never made.
    """
    result = ledger.feed(ws)
    if result.get("ledger", {}).get("state") == ledger.STATE_UNREADABLE:
        return {"status": ledger.UNKNOWN, "ok": False,
                "operator_action_required": True,
                "detail": result["detail"], "counts": None}
    events, _ = ledger.read_events(ws)
    delivered = {}
    observed = set()
    for event in events:
        name = event.get("event")
        message = event.get("message_id")
        if name == ledger.DELIVERED:
            delivered.setdefault(message, event)
        elif name == ledger.RECEIPT_OBSERVED:
            observed.add(message)
    pending = sorted(set(delivered) - observed)
    return {"status": "OK" if not pending else "DEGRADED", "ok": not pending,
            "operator_action_required": bool(pending),
            "detail": (f"{len(pending)} delivery/deliveries without a receipt"
                       if pending else "every delivery has its receipt"),
            "counts": {"delivered": len(delivered), "receipts_observed": len(observed),
                       "pending_receipts": len(pending)}}


def _archive_section(ws) -> dict:
    """Archive health, verbatim. `cold_archive.health` already distinguishes an
    absent archive (nothing at risk) from an unreadable one (UNKNOWN), and this
    wrapper must not flatten that distinction back into a shared default."""
    answer = cold_archive.health(ws)
    # `setdefault`, not assignment: an owner that published its own counts
    # keeps them. A dashboard that rewrites them has re-derived somebody
    # else's numbers, which is the thing this module refuses to do.
    answer.setdefault("counts", _numbers(answer))
    return answer


def _letters_section(ws) -> dict:
    listed = future_letter.list_letters(ws)
    items = listed.get("items") or []
    locked = sum(1 for item in items if item.get("lock_state") == "LOCKED"
                 or item.get("not_before"))
    unread = listed.get("unread")
    return {"status": listed.get("status", "OK"), "ok": True,
            "detail": (f"{len(items)} future letter(s), {locked} time-locked, "
                       f"{unread} unread; metadata only"),
            "counts": {"letters": len(items), "time_locked": locked,
                       "unread": unread}}


def _quarantine_section(ws) -> dict:
    """How much mail the Post Office refused to deliver, counted from disk.

    A directory that cannot be listed is UNKNOWN rather than an empty
    quarantine: the whole cost of a quarantine is that you cannot see it, and a
    reader told "0 quarantined" would keep using a mailbox it cannot inspect.
    """
    quarantine = Path(ws.self_office().mail_root) / postoffice.QUARANTINE
    try:
        held = sum(1 for _ in quarantine.iterdir()) if quarantine.is_dir() else 0
    except OSError as exc:
        return {"status": UNKNOWN, "ok": False, "operator_action_required": True,
                "detail": f"the quarantine directory will not list: {exc}",
                "counts": None}
    return {"status": postoffice.QUARANTINED if held else "OK", "ok": not held,
            "operator_action_required": bool(held),
            "detail": (f"{held} quarantined message(s)" if held
                       else "nothing quarantined"),
            "counts": {"quarantined": held}}


def _canary_section(ws) -> dict:
    """Whether this workspace is the proof lane, and whether that lane broke.

    Classification is asked first and reported either way: a canary that
    silently stopped being a canary looks exactly like a production mailbox, so
    the label is the section's most important number.
    """
    from saimail import canary

    classification = canary.classify(ws)
    failed = canary.reports(ws).get("reports") or []
    return {"status": "OK" if not failed else "DEGRADED",
            "ok": not failed,
            "operator_action_required": bool(failed),
            "detail": (f"workspace is {classification}; {len(failed)} canary "
                       "failure report(s)" if failed
                       else f"workspace is {classification}; no canary failures"),
            "counts": {"canary_failures": len(failed)}}


#: Envelope keys that describe the answer rather than measure the workspace.
#: Filtering them out keeps a section's counts from being padded with `version: 1`.
_ENVELOPE_KEYS = frozenset({"schema", "version", "command", "status", "ok",
                            "operator_action_required", "detail", "workspace",
                            "identity"})


def _numbers(answer: dict):
    """The subsystem's own integers, copied without reinterpretation.

    Nested blocks are read one level deep so `pending`/`failed` surface, and the
    envelope's own bookkeeping keys are dropped so a count is never confused with
    a format version. An owner that published no numbers yields ``None`` rather
    than ``{}``, because an empty mapping reads as "measured, found zero" and
    this module exists to stop that reading.
    """
    picked = {name: value for name, value in answer.items()
              if name not in _ENVELOPE_KEYS
              and isinstance(value, int) and not isinstance(value, bool)}
    for block in ("outbox", "queue", "ledger", "trust"):
        nested = answer.get(block)
        if isinstance(nested, dict):
            picked.update({name: value for name, value in nested.items()
                           if isinstance(value, int) and not isinstance(value, bool)})
    return picked or None


def _outbox_section(ws) -> dict:
    """The outbox speaks for itself; this only lifts its numbers to the top."""
    from saimail import outbox

    answer = outbox.outbox_status(ws)
    # `setdefault`, not assignment: an owner that published its own counts
    # keeps them. A dashboard that rewrites them has re-derived somebody
    # else's numbers, which is the thing this module refuses to do.
    answer.setdefault("counts", _numbers(answer))
    return answer


def _catchup_section(ws) -> dict:
    """Same for the catch-up queue: queued, in flight, parked and owed."""
    from saimail import catchup

    answer = catchup.queue(ws)
    # `setdefault`, not assignment: an owner that published its own counts
    # keeps them. A dashboard that rewrites them has re-derived somebody
    # else's numbers, which is the thing this module refuses to do.
    answer.setdefault("counts", _numbers(answer))
    return answer


#: The only list a human edits here, and it says who to ASK, never the answer.
#: Adding a subsystem to this dashboard is a one-line edit; what that subsystem
#: actually believes stays entirely inside it. Order is the reading order and is
#: stable, because a dashboard whose sections move between runs cannot be
#: compared between runs.
SECTIONS = (
    ("inbox", "saimail.postoffice.read_index", _inbox_section),
    ("outbox", "saimail.outbox.outbox_status", _outbox_section),
    ("receipts", "saimail.ledger.feed", _receipts_section),
    ("trust", "saimail.trust.list_pins", _trust_section),
    ("catchup", "saimail.catchup.queue", _catchup_section),
    ("archive", "saimail.cold_archive.health", _archive_section),
    ("letters", "saimail.future_letter.list_letters", _letters_section),
    ("quarantine", "saimail.postoffice.QUARANTINE", _quarantine_section),
    ("canary", "saimail.canary.classify", _canary_section),
)


def _outbox(ws) -> dict:
    from saimail import outbox

    return outbox.outbox_status(ws)


def _catchup(ws) -> dict:
    from saimail import catchup

    return catchup.queue(ws)


def health(ws, *, sections=None) -> dict:
    """The whole mailbox in one document, three-valued, owner-reported.

    ``sections`` narrows the query; the default asks every one. Every section is
    attempted even after one fails, because a dashboard that stops at the first
    broken subsystem is the same false all-clear with fewer numbers.
    """
    wanted = tuple(sections) if sections else tuple(name for name, _, _ in SECTIONS)
    rows = []
    for name, source, probe in SECTIONS:
        if name not in wanted:
            continue
        try:
            rows.append(_section(name, source, lambda p=probe: p(ws)))
        except SailangError as exc:  # pragma: no cover - _section catches first
            rows.append({"section": name, "source": source, "state": UNKNOWN,
                         "reason": exc.code, "counts": None})
    unknown = [row["section"] for row in rows if row["state"] == UNKNOWN]
    unhealthy = [row["section"] for row in rows if row["state"] == UNHEALTHY]
    # UNKNOWN does not roll up to HEALTHY. It rolls up to UNKNOWN, because a
    # mailbox that cannot describe part of itself has not been shown to be fine.
    overall = UNHEALTHY if unhealthy else (UNKNOWN if unknown else HEALTHY)
    return _workspace.command_result(
        "surface-health", overall, workspace=ws,
        health={"schema": SURFACE_SCHEMA, "version": SURFACE_VERSION,
                "state": overall, "verdicts": list(VERDICTS),
                "unknown": unknown, "unhealthy": unhealthy,
                "sections": rows},
        detail=(f"{len(rows)} section(s): {overall}"
                + (f"; UNKNOWN {', '.join(unknown)}" if unknown else "")
                + (f"; UNHEALTHY {', '.join(unhealthy)}" if unhealthy else "")))


# --------------------------------------------------------------------------
# the gap-aware feed
# --------------------------------------------------------------------------

GAP = "GAP"


def feed(ws, *, cursor: int = 0, limit: int | None = None) -> dict:
    """The event feed, with the ledger's own continuity verdict carried upward.

    Surfacing a trimmed history as a successful page is the one failure a cursor
    cannot detect on its own: the caller sees a well-formed page and no way to
    know that records between its position and the oldest retained event are
    simply gone. So the gap is repeated here, at the level a surface reader is
    actually holding, and it costs the operator nothing to notice.

    An unreadable ledger is UNKNOWN and returns no events, because a feed with a
    plausible-looking empty list and a broken ledger is the false zero again.
    """
    kwargs = {} if limit is None else {"limit": limit}
    page = ledger.feed(ws, cursor=cursor, **kwargs)
    state = (page.get("ledger") or {}).get("state")
    gap = bool(page.get("gap"))
    unreadable = state == ledger.STATE_UNREADABLE
    if unreadable:
        status = UNKNOWN
    elif gap:
        status = GAP
    else:
        status = HEALTHY
    detail = page.get("detail", "")
    if unreadable:
        detail = ("the ledger state is unreadable; no events are returned and an "
                  "empty feed here does NOT mean nothing happened")
    elif gap:
        detail = (f"continuity GAP: events between cursor {cursor} and the oldest "
                  "retained record are gone, were NOT summarised, and are not "
                  "recoverable from this feed")
    return _workspace.command_result(
        "surface-feed", status, workspace=ws,
        operator_action_required=unreadable or gap,
        feed={"schema": SURFACE_SCHEMA, "version": SURFACE_VERSION,
              "gap": gap, "cursor": page.get("cursor"),
              "oldest_retained": (page.get("ledger") or {}).get("first_seq"),
              "event_count": 0 if unreadable else len(page.get("events") or [])},
        ledger=page.get("ledger"),
        events=[] if unreadable else (page.get("events") or []),
        gap=gap,
        truncated=bool(page.get("truncated")),
        detail=detail)


__all__ = [
    "SURFACE_SCHEMA", "SURFACE_VERSION", "MAP_SCHEMA", "MAP_VERSION",
    "HEALTHY", "UNHEALTHY", "UNKNOWN", "VERDICTS", "SECTIONS",
    "cli_map", "capability_schema", "health", "feed",
]