"""SAIPEN seam bridge: seat binding and LOG-event citation (spec/04 S2).

Defect class this module eliminates: SAIMAIL and SAIPEN lived side by side with
no mechanical link. An agent working under SAIPEN had to hand-copy its seat into
``saimail-local init --seat`` and could mention a SAIPEN event only in free
prose, so a message about project work carried no evidence a reader could
re-check -- testimony dressed as fact (``C != F``).

What the bridge does, and what it refuses to become (spec/04 sections 3 and 4):

* **Caller-supplied evidence only.** Every function takes the exact STATE,
  IDENTITY and LOG files to read. The library never names or locates SAIPEN's
  memory directory (the I1 structural test holds for this module like any
  other) and never writes to any file it reads. The SAIPEN layout lives in the
  operator entrypoint, the way ``tools/dev_access.py`` already keeps it outside
  the library.
* **Caller-supplied workspace.** ``init`` creates the ordinary V2-01 workspace
  at the root the caller names, exactly like ``saimail-local init``; the bridge
  checks project participation and supplies the seat. No mailbox is ever
  implied inside a project tree.
* **The acting seat, not the last owner.** The seat is an explicit ``seat``,
  else ``SAIPEN_AGENT`` (SAIPEN's own explicit actor carrier), else
  ``STATE.agent``. ``STATE.agent`` records who last owned the project, not who
  is acting now, so it is only the fallback; the binding reports which source
  won and what ``STATE.agent`` said.
* **A citation claims only that the LOG carries a line.** ``cite_event`` emits
  one ``KIND:O`` record whose ``EV`` is the sha256 of the exact LOG line bytes
  (line terminator excluded). What the line says is never asserted and its text
  never travels inside the record: the line is evidence by hash, not payload.
  A reader re-checks it by re-hashing the line (``verify_citation``), never by
  trusting the sender.

**SAITELEMES v0 (T-109, spec/26).** A telegram is one ordinary sealed message
from the acting seat to another running agent, sent in one call at discovery
time instead of after a human relay. Its kind comes from the closed SENV2 set,
its TOPIC defaults to the SAIPEN Work id, and its body is either the ordinary
one-line claim wrapper or the S2 citation of one LOG event. There is no
telegram kind, no importance field and no auto-open: ``telegrams`` is a bounded,
header-only unread check a receiver runs at turn entry. A workspace whose seat
is not the acting seat refuses to send, so a telegram cannot go out under
another agent's name.

**Work Desk v0 (T-110, spec/27).** ``enter`` checks local SAIPEN participation;
``brief`` joins that observed work context to a bounded unread page. Other
topics remain visible, and pagination refuses changed work/mailbox context.
``init`` and ``telegram`` share the participation prerequisite. This is a local
binding check, not proof of protocol compliance or a global mailbox ACL.

No new protocol, wire field or state field exists here. Remove this module and
both systems keep working unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from sailang import Record, SailangError
from sailang import parse as parse_record
from saimail import envelope, postoffice
from saimail import workspace as _workspace

SAIPEN_PROJECT_MISSING = "SAIPEN_PROJECT_MISSING"
SAIPEN_STATE_INVALID = "SAIPEN_STATE_INVALID"
SAIPEN_EVENT_UNKNOWN = "SAIPEN_EVENT_UNKNOWN"
SAIPEN_EVENT_AMBIGUOUS = "SAIPEN_EVENT_AMBIGUOUS"
SAIPEN_CITATION_INVALID = "SAIPEN_CITATION_INVALID"
SAIPEN_CITATION_FOREIGN = "SAIPEN_CITATION_FOREIGN"
SAIPEN_CITATION_MISMATCH = "SAIPEN_CITATION_MISMATCH"
SAIPEN_SEAT_MISMATCH = "SAIPEN_SEAT_MISMATCH"
SAIPEN_CONTEXT_CHANGED = "SAIPEN_CONTEXT_CHANGED"
SAIPEN_ADMISSION_REQUIRED = "SAIPEN_ADMISSION_REQUIRED"
CITATION_VERIFIED = "CITATION_VERIFIED"
BOUND = "BOUND"
CITED = "CITED"

#: Every bridge refusal names a fact only a human can repair.
OPERATOR_ACTION_CODES = frozenset({
    SAIPEN_PROJECT_MISSING, SAIPEN_STATE_INVALID, SAIPEN_EVENT_UNKNOWN,
    SAIPEN_EVENT_AMBIGUOUS, SAIPEN_CITATION_INVALID, SAIPEN_CITATION_FOREIGN,
    SAIPEN_CITATION_MISMATCH, SAIPEN_SEAT_MISMATCH,
    SAIPEN_ADMISSION_REQUIRED,
})

TELEGRAM_DEFAULT_KIND = "DISCOVERY"
TELEGRAM_FALLBACK_TOPIC = "saitelemes"
BRIEF_SCHEMA = "SAIPEN_WORK_BRIEF_1"
_TOPIC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

SEAT_EXPLICIT = "explicit"
SEAT_ENV = "SAIPEN_AGENT"
SEAT_STATE = "STATE.agent"

SRC_PREFIX = "LOG:saipen/"
_EVENT_RE = re.compile(r"^E-[1-9][0-9]*$")
_LINEAGE_RE = re.compile(r"^lineage-[0-9a-f]{32}$")
#: The fixed LOG skeleton owned by SAIPEN CORE 1.2: ``- DD.MM.YY HH:MM [E-###]``.
#: Only the event's own leading id counts; ``[parent: E-###]`` and commentary
#: never match, so a line that merely mentions an event cannot be cited as it.
_LINE_HEAD_RE = re.compile(rb"^- \d{2}\.\d{2}\.\d{2} \d{2}:\d{2} \[(E-[1-9][0-9]*)\]")
_TICKET_RE = re.compile(rb"\[(T-[0-9]+)\]")
_TAXONOMY_RE = re.compile(rb"\] ([A-Z]+): ")
_FRONTMATTER_LINE_RE = re.compile(r"^([a-z_]+):\s*(.*)$")


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _frontmatter(path, *, what: str, unique: bool = False) -> dict:
    """Flat ``key: value`` pairs between the leading ``---`` fences."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        _reject(SAIPEN_STATE_INVALID, f"{what} is missing at {path}")
    except (OSError, UnicodeDecodeError) as exc:
        _reject(SAIPEN_STATE_INVALID, f"{what} is unreadable: {exc}")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        _reject(SAIPEN_STATE_INVALID, f"{what} has no leading --- frontmatter")
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        match = _FRONTMATTER_LINE_RE.match(line.strip())
        if match:
            if unique and match.group(1) in fields:
                _reject(SAIPEN_STATE_INVALID, f"{what} repeats field {match.group(1)!r}")
            fields[match.group(1)] = match.group(2).strip().strip('"')
    _reject(SAIPEN_STATE_INVALID, f"{what} frontmatter is not closed by ---")


def read_lineage(identity_path=None):
    """``IDENTITY.project_lineage`` or None when the file or field is absent."""
    if identity_path is None or not Path(identity_path).is_file():
        return None
    lineage = _frontmatter(identity_path, what="SAIPEN IDENTITY.md").get("project_lineage", "")
    if lineage and not _LINEAGE_RE.match(lineage):
        _reject(SAIPEN_STATE_INVALID, f"IDENTITY.project_lineage {lineage!r} is malformed")
    return lineage or None


def _resolve_seat(seat, state_agent: str) -> tuple:
    if seat is not None:
        if not isinstance(seat, str) or not _workspace.SEAT_RE.match(seat):
            _reject(_workspace.BAD_SEAT, f"seat {seat!r} is not a usable seat token")
        return seat, SEAT_EXPLICIT
    env = os.environ.get(SEAT_ENV, "").strip()
    if env:
        if not _workspace.SEAT_RE.match(env):
            _reject(_workspace.BAD_SEAT, f"{SEAT_ENV} {env!r} is not a usable seat token")
        return env, SEAT_ENV
    if not _workspace.SEAT_RE.match(state_agent):
        _reject(SAIPEN_STATE_INVALID,
                f"STATE.agent {state_agent!r} is not a usable seat token; pass --seat")
    return state_agent, SEAT_STATE


def _binding(state: dict, state_path, lineage, seat) -> dict:
    """Resolve a binding from one already-read STATE projection."""
    state_agent = state.get("agent", "")
    agent, seat_source = _resolve_seat(seat, state_agent)
    return {
        "state": str(state_path),
        "seat": agent,
        "seat_source": seat_source,
        "state_agent": state_agent or None,
        "lineage": lineage,
        "phase": state.get("phase") or None,
        "task": state.get("task") or None,
        "last_event": state.get("last_event") or None,
    }


def read_binding(state_path, identity_path=None, *, seat=None) -> dict:
    """The read-only SAIPEN facts SAIMAIL binds to: acting seat, lineage, current work."""
    return _binding(_frontmatter(state_path, what="SAIPEN STATE.md"),
                    state_path, read_lineage(identity_path), seat)


def status(state_path, identity_path=None, *, seat=None, workspace_root=None) -> dict:
    """Read-only: the acting seat, and whether the named workspace exists."""
    binding = read_binding(state_path, identity_path, seat=seat)
    bridge = {"workspace_root": None, "workspace_initialized": None}
    detail = f"seat {binding['seat']} bound via {binding['seat_source']}"
    if workspace_root is not None:
        initialized = (Path(workspace_root) / _workspace.MARKER_NAME).is_file()
        bridge = {"workspace_root": str(workspace_root), "workspace_initialized": initialized}
        detail += "; workspace " + ("initialized" if initialized else "not initialized")
    return _workspace.command_result("saipen-status", BOUND, saipen=binding, bridge=bridge,
                                     detail=detail)


def init(state_path, identity_path=None, *, workspace_root=None, seat=None,
         custody: str = "raw", store=None, clock=None) -> dict:
    """Create (or reopen) the ordinary workspace at ``workspace_root`` for the acting seat."""
    if workspace_root is None:
        _reject(_workspace.BAD_INPUT, "the workspace root is caller-supplied: pass --workspace")
    binding = _admission_binding(state_path, identity_path, seat)
    result = _workspace.init_workspace(workspace_root, seat=binding["seat"], custody=custody,
                                       store=store, clock=clock)
    result["saipen"] = binding
    return result


def find_event_line(log_paths, event_id: str) -> dict:
    """Exactly one line, across the given LOG files, whose skeleton id is ``event_id``."""
    if not isinstance(event_id, str) or not _EVENT_RE.match(event_id):
        _reject(_workspace.BAD_INPUT, f"event id must look like E-1234, got {event_id!r}")
    wanted = event_id.encode("ascii")
    hits = []
    searched = 0
    for path in log_paths:
        path = Path(path)
        if not path.is_file():
            continue
        searched += 1
        for raw in path.read_bytes().split(b"\n"):
            line = raw[:-1] if raw.endswith(b"\r") else raw
            head = _LINE_HEAD_RE.match(line)
            if head and head.group(1) == wanted:
                hits.append((path, line))
    if not hits:
        _reject(SAIPEN_EVENT_UNKNOWN,
                f"{event_id} heads no line in {searched} SAIPEN LOG file(s)")
    if len(hits) > 1:
        _reject(SAIPEN_EVENT_AMBIGUOUS,
                f"{event_id} heads {len(hits)} LOG lines; refusing to pick one")
    path, line = hits[0]
    ticket = _TICKET_RE.search(line)
    taxonomy = _TAXONOMY_RE.search(line)
    return {
        "event": event_id,
        "log": str(path),
        "line": line,
        "evidence": "sha256:" + hashlib.sha256(line).hexdigest(),
        "ticket": ticket.group(1).decode("ascii") if ticket else None,
        "taxonomy": taxonomy.group(1).decode("ascii") if taxonomy else None,
    }


def _src(lineage, event_id: str) -> str:
    return SRC_PREFIX + (f"{lineage}/{event_id}" if lineage else event_id)


def _citation(hit: dict, lineage, created: str) -> Record:
    """The one record a LOG line yields; ``cite_event`` and ``verify_citation`` share it."""
    claim = f"SAIPEN LOG carries {hit['event']}"
    if hit["taxonomy"]:
        claim += f" {hit['taxonomy']}"
    return Record.create(
        KIND="O", SRC=_src(lineage, hit["event"]), SUBJ=hit["ticket"] or hit["event"],
        CLAIM=claim, TYPE="OBS", EV=hit["evidence"], STATUS="U4",
        DIRECTNESS="HIGH", INTEGRITY="MED", CREATED=created)


def cite_event(log_paths, event_id: str, *, lineage=None, clock=None) -> Record:
    """One canonical ``KIND:O`` record: this SAIPEN LOG carries this exact line."""
    clock = clock or postoffice.utc_now
    return _citation(find_event_line(log_paths, event_id), lineage, clock())


def cite(log_paths, event_id: str, *, lineage=None, out=None, clock=None) -> dict:
    """Cite one event; write the canonical record to ``out`` when given."""
    record = cite_event(log_paths, event_id, lineage=lineage, clock=clock)
    written = None
    if out is not None:
        out = Path(out)
        data = record.canonical_bytes()
        if out.is_file() and out.read_bytes() != data:
            _reject(_workspace.BAD_INPUT, f"{out} already holds a different record")
        _workspace._atomic_write_bytes(out, data)
        written = str(out)
    return _workspace.command_result(
        "saipen-cite", CITED,
        record={"id": record.content_id, "src": record.get("SRC"),
                "subj": record.get("SUBJ"), "ev": record.get("EV"),
                "claim": record.claim, "path": written,
                "canonical": record.canonical_text()},
        detail=f"{event_id} cited as {record.short_id()}"
               + (f"; send with `saimail-local send --record {written}`" if written else ""))


def verify_citation(record_path, log_paths, *, lineage=None) -> dict:
    """Re-check a cited record against the reader's own view of the LOG bytes.

    The record must be exactly the citation the line yields today at the
    record's own ``CREATED``. Checking ``EV`` alone would pass a record that
    keeps the right hash but lies in ``SUBJ`` or ``CLAIM``.
    """
    try:
        record = parse_record(Path(record_path).read_bytes())
    except OSError as exc:
        _reject(_workspace.BAD_INPUT, f"record file is unreadable: {exc}")
    src = record.get("SRC") or ""
    if record.kind != "O" or not src.startswith(SRC_PREFIX):
        _reject(SAIPEN_CITATION_INVALID, "record is not a SAIPEN LOG citation")
    tail = src[len(SRC_PREFIX):].split("/")
    if len(tail) not in (1, 2) or not _EVENT_RE.match(tail[-1]):
        _reject(SAIPEN_CITATION_INVALID,
                f"SRC {src!r} is not {SRC_PREFIX}[<lineage>/]E-###")
    event_id = tail[-1]
    cited_lineage = tail[0] if len(tail) == 2 else None
    if cited_lineage != lineage:
        _reject(SAIPEN_CITATION_FOREIGN,
                f"record cites lineage {cited_lineage}, this project is {lineage}")
    hit = find_event_line(log_paths, event_id)
    if record.get("EV") != hit["evidence"]:
        _reject(SAIPEN_CITATION_MISMATCH,
                f"{event_id} in {hit['log']} no longer hashes to the cited evidence")
    expected = _citation(hit, lineage, record.get("CREATED"))
    if expected.content_id != record.content_id:
        differing = sorted(key for key in set(expected.keys()) | set(record.keys())
                           if expected.get(key) != record.get(key))
        _reject(SAIPEN_CITATION_INVALID,
                f"record is not the citation {event_id} yields; differing: "
                + ", ".join(differing))
    return _workspace.command_result(
        "saipen-verify", CITATION_VERIFIED,
        record={"id": record.content_id, "src": src, "ev": hit["evidence"],
                "log": hit["log"]},
        detail=f"{event_id} re-hashed from {hit['log']}: record matches the line")


def telegram(workspace, alias: str, state_path, identity_path=None, *, log_paths=(),
             claim=None, event=None, kind: str = TELEGRAM_DEFAULT_KIND, topic=None,
             seat=None, clock=None) -> dict:
    """Send one SAITELEME: the acting seat tells a registered running agent one thing now.

    Exactly one body: ``claim`` (the ordinary evidence-absent one-line wrapper)
    or ``event`` (the S2 citation of one LOG event, re-derivable by the reader).
    TOPIC defaults to the SAIPEN Work id so the receiver can find every telegram
    about one audit with one exact filter.
    """
    if (claim is None) == (event is None):
        _reject(_workspace.BAD_INPUT, "a telegram carries exactly one of claim text or --event")
    if kind not in envelope.KINDS:
        _reject(_workspace.BAD_INPUT,
                f"kind {kind!r} is outside the closed SENV2 kind set {sorted(envelope.KINDS)}")
    binding = enter(workspace, state_path, identity_path, seat=seat)["saipen"]
    task = binding.get("task") or ""
    if task.lower() == "none":  # SAIPEN's own spelling of "no active Work"
        task = ""
    if topic is None:
        topic = task if _TOPIC_RE.match(task) else TELEGRAM_FALLBACK_TOPIC
    subject = task if task and not any(c.isspace() for c in task) else TELEGRAM_FALLBACK_TOPIC
    if claim is not None:
        result = _workspace.send_message(workspace, alias, claim=claim, subject=subject,
                                         topic=topic, kind=kind, clock=clock)
        form = "claim"
    else:
        record = cite_event(log_paths, event, lineage=read_lineage(identity_path), clock=clock)
        with tempfile.TemporaryDirectory(prefix="saitelemes-") as scratch:
            path = Path(scratch) / "citation.sail"
            path.write_bytes(record.canonical_bytes())
            result = _workspace.send_message(workspace, alias, record_path=path,
                                             subject=subject, topic=topic, kind=kind,
                                             clock=clock)
        form = "citation"
    result["command"] = "saipen-telegram"
    result["saipen"] = binding
    result["telegram"] = {"form": form, "event": event, "topic": topic, "kind": kind}
    return result


def telegrams(workspace, *, topic=None, scan_budget=None, cursor=None, clock=None) -> dict:
    """Turn-entry read: bounded, header-only UNREAD rows; nothing is opened."""
    result = _workspace.query_inbox(workspace, topic=topic, state=postoffice.UNREAD,
                                    scan_budget=scan_budget, cursor=cursor, clock=clock)
    result["command"] = "saipen-telegrams"
    return result


def _admission_binding(state_path, identity_path, seat) -> dict:
    state = _frontmatter(state_path, what="SAIPEN STATE.md", unique=True)
    if identity_path is None or not Path(identity_path).is_file():
        _reject(SAIPEN_ADMISSION_REQUIRED, "entry requires the SAIPEN project's IDENTITY.md")
    identity = _frontmatter(identity_path, what="SAIPEN IDENTITY.md", unique=True)
    lineage = identity.get("project_lineage", "")
    if not _LINEAGE_RE.fullmatch(lineage):
        _reject(SAIPEN_ADMISSION_REQUIRED, "entry requires a valid SAIPEN project_lineage")
    if not state.get("phase") or not state.get("last_event", "").isdigit():
        _reject(SAIPEN_ADMISSION_REQUIRED, "entry requires SAIPEN phase and numeric last_event")
    binding = _binding(state, state_path, lineage, seat)
    binding["blocker"] = state.get("blocker") or None
    return binding


def enter(workspace, state_path, identity_path=None, *, seat=None) -> dict:
    """Check local SAIPEN participation and seat identity before using the work desk.

    This is a fresh observation, not a transferable capability or a proof that
    the agent obeys SAIPEN. The caller chooses the project evidence to trust.
    """
    binding = _admission_binding(state_path, identity_path, seat)
    if binding["seat"] != workspace.seat:
        # The seat is not a fact only a human can repair: the workspace records
        # its own seat operator in saimail-workspace.json, so name that seat and
        # the command that adopts it. The code stays in OPERATOR_ACTION_CODES --
        # whether an agent may SILENTLY adopt the operator seat is the owner's
        # trust decision, and this refusal does not get to make it.
        _reject(SAIPEN_SEAT_MISMATCH,
                f"acting seat {binding['seat']} is not this workspace's seat "
                f"{workspace.seat}; that seat is recorded in the workspace's "
                f"saimail-workspace.json, so re-run with --seat {workspace.seat}")
    return _workspace.command_result(
        "saipen-enter", "ADMITTED", workspace=workspace, saipen=binding,
        admission={"basis": "LOCAL_SAIPEN_BINDING", "persistent": False,
                   "protocol_compliance": "NOT_VERIFIED"},
        detail="SAIPEN project and workspace seat match; entry observation only; nothing opened")


def work_brief(workspace, state_path, identity_path=None, *, seat=None,
               scan_budget=None, cursor=None, context=None, clock=None) -> dict:
    """Join one observed work context with one bounded page of unread headers.

    Topic equality is a navigation hint, never proof of project membership or
    relevance. Other topics stay visible. A continuation must carry the returned
    context hash so pages from different workspaces or work states cannot be
    silently combined. The hash detects changes; it is not authentication.
    """
    if context is not None and (not isinstance(context, str)
                                or re.fullmatch(r"sha256:[0-9a-f]{64}", context) is None):
        _reject(_workspace.BAD_INPUT, "context must be the sha256 token from a work brief")
    if cursor not in (None, 0) and context is None:
        _reject(_workspace.BAD_INPUT, "continuing a work brief requires --context from its first page")
    admission = enter(workspace, state_path, identity_path, seat=seat)
    binding = admission["saipen"]
    witness = {
        "schema": BRIEF_SCHEMA, "saipen": binding,
        "state_path": str(Path(state_path).resolve()),
        "identity_path": str(Path(identity_path).resolve()) if identity_path is not None else None,
        "workspace_root": str(Path(workspace.root).resolve()),
        "sender_kid": workspace.sender_kid, "recipient_kid": workspace.recipient_kid,
    }
    context_id = "sha256:" + hashlib.sha256(
        json.dumps(witness, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    if context is not None and context != context_id:
        _reject(SAIPEN_CONTEXT_CHANGED,
                "work context or workspace changed; restart brief without --cursor and --context")
    result = telegrams(workspace, scan_budget=scan_budget, cursor=cursor, clock=clock)
    if _admission_binding(state_path, identity_path, seat) != binding:
        _reject(SAIPEN_CONTEXT_CHANGED, "work context changed during the scan; restart brief")
    task = binding.get("task") or ""
    current_topic = task if task.lower() != "none" and _TOPIC_RE.fullmatch(task) else None
    current_letter_topic = None
    if current_topic is not None:
        from saimail import letters

        if letters._WORK.fullmatch(task) and len("l." + binding["lineage"].removeprefix("lineage-") + "." + task) <= 64:
            current_letter_topic = letters.topic(binding["lineage"], task)
    work_topics = {topic for topic in (current_topic, current_letter_topic) if topic is not None}
    counts = {"current_topic": 0, "other_topics": 0}
    for item in result["items"]:
        relation = "current_topic" if item["topic"] in work_topics else "other_topics"
        item["work_relation"] = relation
        counts[relation] += 1
    result["command"] = "saipen-brief"
    result["saipen"] = binding
    result["admission"] = admission["admission"]
    result["brief"] = {
        "schema": BRIEF_SCHEMA, "context": context_id, "current_topic": current_topic,
        "current_letter_topic": current_letter_topic,
        "association": "TOPIC_ONLY", "counts_scope": "PAGE", "counts": counts,
        "scan_from_start": cursor in (None, 0),
        "complete_from_start": cursor in (None, 0) and not result["exhausted"],
        "continuation": {"cursor": result["cursor"], "context": context_id}
        if result["cursor"] is not None else None,
    }
    result["detail"] = (
        f"{result['match_count']} unread header(s) in this page; topic equality is only a hint; "
        "open explicitly to inspect evidence; SAIPEN work and mailbox state are unchanged")
    return result


__all__ = [
    "BOUND",
    "BRIEF_SCHEMA",
    "CITATION_VERIFIED",
    "CITED",
    "OPERATOR_ACTION_CODES",
    "SAIPEN_ADMISSION_REQUIRED",
    "SAIPEN_CITATION_FOREIGN",
    "SAIPEN_CITATION_INVALID",
    "SAIPEN_CITATION_MISMATCH",
    "SAIPEN_CONTEXT_CHANGED",
    "SAIPEN_EVENT_AMBIGUOUS",
    "SAIPEN_EVENT_UNKNOWN",
    "SAIPEN_PROJECT_MISSING",
    "SAIPEN_SEAT_MISMATCH",
    "SAIPEN_STATE_INVALID",
    "SEAT_ENV",
    "SEAT_EXPLICIT",
    "SEAT_STATE",
    "TELEGRAM_DEFAULT_KIND",
    "TELEGRAM_FALLBACK_TOPIC",
    "cite",
    "cite_event",
    "enter",
    "find_event_line",
    "init",
    "read_binding",
    "read_lineage",
    "status",
    "telegram",
    "telegrams",
    "verify_citation",
    "work_brief",
]
