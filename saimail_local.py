"""SAIMAIL minimal local entrypoint and persistent local workspace CLI.

The supported local surface: one command that runs the FG-05 end-to-end demo,
the FG-06 TOTAL_FRICTION benchmark, or the V2-01 persistent local workspace
workflow (init, identity, recipient, send, inbox, open) plus a one-command
multi-invocation acceptance harness. No framework, GUI, daemon, web service,
plugin system, adapter abstract, model or hardware dependency.

    python -m saimail_local --help
    python -m saimail_local --version
    python -m saimail_local                      # FG-05 demo
    python -m saimail_local --utility            # FG-06 benchmark
    python -m saimail_local init --workspace DIR --seat SEAT
    python -m saimail_local identity --workspace DIR --export-card CARD.json
    python -m saimail_local recipient add --workspace DIR --alias NAME \
        --card CARD.json --peer-workspace PEER_DIR
    python -m saimail_local send --workspace DIR --to NAME --claim "one line"
    python -m saimail_local send --workspace DIR --redeliver ENVELOPE_ID
    python -m saimail_local inbox --workspace DIR
    python -m saimail_local inbox --workspace DIR --topic ci --state UNREAD \
        --since 2026-09-01T00:00:00Z --scan-budget 50
    python -m saimail_local inbox --workspace DIR --ref ENVELOPE_ID
    python -m saimail_local open --workspace DIR --envelope ENVELOPE_ID
    python -m saimail_local reply --workspace DIR --envelope ENVELOPE_ID \
        --claim "one line"
    python -m saimail_local acceptance --root DIR
    python tools/fg05_local_scenario.py          # same FG-05 demo, repo shim

It owns the temporary-root lifecycle and the zero-network tripwire; the LAB
engine it wraps stays pure and offline.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import socket
import subprocess
import sys
import tempfile
from importlib import metadata
from pathlib import Path

from sailang import SailangError

_VERSION_FALLBACK = "0.0.2a3"

WR_OK = "OK"
WR_PASS = "PASS"
WR_FAIL = "FAIL"

#: The one-command acceptance harness result contract (spec/17).
ACCEPTANCE_SCHEMA = "LOCAL_WORKSPACE_RESULT_1"
ACCEPTANCE_VERSION = 1


def _version() -> str:
    try:
        return metadata.version("saimail")
    except metadata.PackageNotFoundError:
        version_file = Path(__file__).resolve().parent / "VERSION"
        if version_file.is_file():
            return version_file.read_text(encoding="utf-8").strip()
        return _VERSION_FALLBACK


@contextlib.contextmanager
def no_network(probe: dict):
    """Block and count every socket connection attempt for the enclosed block."""
    original_connect = socket.socket.connect
    original_create = socket.create_connection

    def blocked(*_args, **_kwargs):
        probe["blocked"] = probe.get("blocked", 0) + 1
        raise AssertionError("SAIMAIL local entrypoint attempted a network connection")

    socket.socket.connect = blocked
    socket.create_connection = blocked
    try:
        yield
    finally:
        socket.socket.connect = original_connect
        socket.create_connection = original_create


def _engine():
    from lab import local_scenario

    return local_scenario


def _utility_engine():
    from lab import utility_friction

    return utility_friction


def _workspace_engine():
    from saimail import workspace

    return workspace


def _saipen_engine():
    from saimail import saipen_bridge

    return saipen_bridge


def _outbox_engine():
    from saimail import outbox

    return outbox


def _participants_engine():
    from saimail import participants

    return participants


def _capabilities_engine():
    from saimail import capabilities

    return capabilities


def _notify_engine():
    from saimail import notify

    return notify


def _saipen_notify(args, project: dict) -> dict:
    """V6-08: one automatic notification for a closed trigger, exactly once.

    Without a readable signing key (a locked store) the intent is still recorded
    durably from the secret-free view and a later full load seals it.
    """
    engine = _workspace_engine()
    bridge = _saipen_engine()
    notify = _notify_engine()
    try:
        workspace = engine.load_workspace(args.workspace)
    except SailangError as exc:
        if not exc.code.startswith("CUSTODY_"):
            raise
        workspace = engine.load_workspace_headers(args.workspace)
    binding = bridge.enter(workspace, project["state"], project["identity"],
                           seat=args.seat)["saipen"]
    board = project["board"].read_text(encoding="utf-8") if project["board"].is_file() else ""
    work = notify.resolve_work(binding.get("task"), args.work, notify.board_work_ids(board))
    citation = None
    if args.event is not None:
        citation = bridge.cite_event(project["logs"], args.event, lineage=binding["lineage"])
    result = notify.notify(workspace, lineage=binding["lineage"], work=work,
                           trigger=args.trigger, to_seat=args.to, claim=args.claim,
                           citation=citation, event=args.event)
    result["saipen"] = binding
    return result


def _saipen_capabilities(args) -> dict:
    """V6-07: one never-failing, keyless capability document for SAIPEN entry.

    A missing or unreadable SAIPEN project is a state (PROJECT_NOT_BOUND), not a
    refusal: the channel reports DEGRADED and the caller keeps working.
    """
    import os

    bridge = _saipen_engine()
    binding = None
    try:
        project = _saipen_project(args.project_root)
        binding = bridge.read_binding(project["state"], project["identity"], seat=args.seat)
    except SailangError:
        binding = None
    if binding is not None:
        seat, source = binding["seat"], binding["seat_source"]
        lineage = binding["lineage"]
        task = binding.get("task") or ""
        topic = task if bridge._TOPIC_RE.fullmatch(task) and task.lower() != "none" else None
    else:
        seat = args.seat or os.environ.get("SAIPEN_AGENT") or None
        source = "explicit" if args.seat else ("SAIPEN_AGENT" if seat else None)
        lineage, topic = None, None
    return _capabilities_engine().capabilities(
        args.workspace, acting_seat=seat, seat_source=source, lineage=lineage,
        current_topic=topic)


def _api_map_path() -> Path:
    return Path(__file__).resolve().parent / "lab" / "stable_local_api.json"


def _run(mode: str, base: Path, probe: dict) -> dict:
    if mode == "utility":
        return _utility_engine().run_utility(base, probe=probe)
    return _engine().run_scenario(base, probe=probe)


def _write_outputs(result: dict, out: Path, mode: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    if mode == "utility":
        (out / "fg06_utility_result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (out / "fg06_utility_summary.md").write_text(
            _utility_engine().render_utility_summary(result) + "\n", encoding="utf-8")
    else:
        (out / "local_scenario_result.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (out / "local_scenario_summary.md").write_text(
            _engine().render_summary(result) + "\n", encoding="utf-8")


def render(result: dict, mode: str) -> str:
    if mode == "utility":
        return _utility_engine().render_utility_summary(result)
    return _engine().render_summary(result)


# --------------------------------------------------------------------------
# persistent local workspace CLI (V2-01)
# --------------------------------------------------------------------------


def _error_result(command: str, exc: SailangError, operator_codes=frozenset()) -> dict:
    engine = _workspace_engine()
    return {
        "schema": engine.COMMAND_SCHEMA,
        "version": engine.COMMAND_VERSION,
        "command": command,
        "status": exc.code,
        "ok": False,
        "operator_action_required": (exc.code in engine.OPERATOR_ACTION_CODES
                                     or exc.code in operator_codes),
        "detail": exc.detail,
    }


def _emit_workspace_result(result: dict, as_json: bool, *, probe: dict | None = None) -> None:
    if probe is not None:
        result["network_attempts"] = probe.get("blocked", 0)
    if as_json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(_workspace_engine().render_command(result))


def _dispatch_workspace(command: str, action, as_json: bool,
                        operator_codes=frozenset()) -> int:
    """Run one workspace operation under the local zero-network tripwire."""
    probe: dict = {"blocked": 0}
    try:
        with no_network(probe):
            result = action()
    except SailangError as exc:
        result = _error_result(command, exc, operator_codes)
    _emit_workspace_result(result, as_json, probe=probe)
    return 0 if result.get("ok") else 1


def _cmd_init(args, as_json: bool) -> int:
    engine = _workspace_engine()

    def action():
        return engine.init_workspace(args.workspace, seat=args.seat, custody=args.custody)

    return _dispatch_workspace("init", action, as_json)


def _cmd_custody(args, as_json: bool) -> int:
    engine = _workspace_engine()

    def action():
        if args.custody_action == "status":
            return engine.custody_status(args.workspace)
        return engine.migrate_workspace_custody(args.workspace)

    return _dispatch_workspace(f"custody-{args.custody_action}", action, as_json)


def _cmd_identity(args, as_json: bool) -> int:
    engine = _workspace_engine()

    def action():
        workspace = engine.load_workspace(args.workspace)
        return engine.export_identity_card(workspace, args.export_card)

    return _dispatch_workspace("identity", action, as_json)


def _cmd_recipient(args, as_json: bool) -> int:
    engine = _workspace_engine()

    def action():
        workspace = engine.load_workspace(args.workspace)
        if args.recipient_action == "add":
            card = json.loads(Path(args.card).read_text(encoding="utf-8"))
            return engine.add_recipient(workspace, args.alias, card, args.peer_workspace)
        return engine.list_recipients(workspace)

    return _dispatch_workspace(f"recipient-{args.recipient_action}", action, as_json)


def _cmd_send(args, as_json: bool) -> int:
    engine = _workspace_engine()

    def action():
        workspace = engine.load_workspace(args.workspace)
        if args.redeliver:
            if args.claim or args.record:
                raise SailangError(
                    engine.BAD_INPUT,
                    "an exact replay takes no new content: drop claim/record")
            return engine.redeliver_message(workspace, args.redeliver)
        return engine.send_message(workspace, args.to, claim=args.claim,
                                   record_path=args.record, subject=args.subject,
                                   topic=args.topic, kind=args.kind)

    return _dispatch_workspace("send", action, as_json)


_INBOX_QUERY_ARGS = ("from_seat", "topic", "kind", "state", "ref", "since",
                     "before", "scan_budget", "cursor")


def _cmd_inbox(args, as_json: bool) -> int:
    engine = _workspace_engine()
    # No filter/budget/cursor means the exact legacy unbounded listing; any
    # query flag switches to the bounded metadata query without changing it.
    query_requested = any(getattr(args, name) is not None for name in _INBOX_QUERY_ARGS)

    def action():
        # Header-only: the secret-free view never reads a private key (T-117).
        workspace = engine.load_workspace_headers(args.workspace)
        if not query_requested:
            return engine.list_inbox(workspace)
        return engine.query_inbox(
            workspace, sender=args.from_seat, topic=args.topic, kind=args.kind,
            state=args.state, ref=args.ref, since=args.since, before=args.before,
            scan_budget=args.scan_budget, cursor=args.cursor)

    return _dispatch_workspace("inbox-query" if query_requested else "inbox",
                               action, as_json)


def _cmd_open(args, as_json: bool) -> int:
    engine = _workspace_engine()

    def action():
        return engine.open_message(engine.load_workspace(args.workspace), args.envelope)

    return _dispatch_workspace("open", action, as_json)

def _cmd_reopen(args, as_json: bool) -> int:
    engine = _workspace_engine()

    def action():
        return engine.reopen_message(engine.load_workspace(args.workspace), args.envelope)

    return _dispatch_workspace("reopen", action, as_json)


def _cmd_reply(args, as_json: bool) -> int:
    engine = _workspace_engine()

    def action():
        workspace = engine.load_workspace(args.workspace)
        return engine.reply_message(workspace, args.envelope, claim=args.claim,
                                    record_path=args.record, subject=args.subject,
                                    topic=args.topic, kind=args.kind)

    return _dispatch_workspace("reply", action, as_json)


def _cmd_outbox(args, as_json: bool) -> int:
    """V6-05 durable outbox: idempotent sends that survive crashes and retries."""
    engine = _workspace_engine()
    outbox = _outbox_engine()

    def action():
        if args.outbox_action == "status":
            # Status is metadata only; the secret-free view is enough (T-117).
            return outbox.outbox_status(engine.load_workspace_headers(args.workspace))
        workspace = engine.load_workspace(args.workspace)
        if args.outbox_action == "send":
            return outbox.submit_send(workspace, args.to, key=args.key, claim=args.claim,
                                      record_path=args.record, subject=args.subject,
                                      topic=args.topic, kind=args.kind,
                                      deliver=not args.no_deliver)
        if args.outbox_action == "resume":
            return outbox.resume_outbox(workspace, budget=args.budget)
        return outbox.retry_intent(workspace, args.key)

    return _dispatch_workspace(f"outbox-{args.outbox_action}", action, as_json,
                               outbox.OPERATOR_ACTION_CODES)


#: SAIPEN's project-memory layout. It lives in this operator entrypoint and
#: never in the library: ``sailang``/``saimail`` stay unable to name SAIPEN
#: memory (the I1 structural test), and the operator's invocation is what points
#: the read-only bridge at these evidence files.
_SAIPEN_MEMORY = ".saipen"


def _saipen_project(explicit) -> dict:
    """The evidence files of one SAIPEN project: explicit root, else nearest ancestor."""
    bridge = _saipen_engine()
    if explicit is not None:
        root = Path(explicit).resolve()
        if not (root / _SAIPEN_MEMORY / "STATE.md").is_file():
            raise SailangError(bridge.SAIPEN_PROJECT_MISSING,
                               f"no {_SAIPEN_MEMORY}/STATE.md under {root}")
    else:
        here = Path.cwd().resolve()
        for root in (here, *here.parents):
            if (root / _SAIPEN_MEMORY / "STATE.md").is_file():
                break
        else:
            raise SailangError(bridge.SAIPEN_PROJECT_MISSING,
                               f"no {_SAIPEN_MEMORY}/STATE.md in {here} or any parent; "
                               "pass --project-root")
    memory = root / _SAIPEN_MEMORY
    return {
        "state": memory / "STATE.md",
        "identity": memory / "IDENTITY.md",
        "board": memory / "BOARD.md",
        # Active LOG first, then the sealed segments; an event id is unique across all.
        "logs": [memory / "LOG.md", *sorted((memory / "logs").glob("LOG-*.md"))],
    }


def _cmd_saipen(args, as_json: bool) -> int:
    """spec/04 S2 seam: bind to the SAIPEN project, cite its LOG as evidence."""
    bridge = _saipen_engine()

    def action():
        if args.saipen_action == "capabilities":
            return _saipen_capabilities(args)
        # Header-only seam reads (telegrams, which SAIPEN runs at each automatic turn
        # entry, plus enter and brief) load the secret-free view and never read a
        # private key (T-117). Sending a telegram keeps the full load.
        if args.saipen_action == "telegrams":
            workspace = _workspace_engine().load_workspace_headers(args.workspace)
            return bridge.telegrams(workspace, topic=args.topic,
                                    scan_budget=args.scan_budget, cursor=args.cursor)
        project = _saipen_project(args.project_root)
        if args.saipen_action == "notify":
            return _saipen_notify(args, project)
        if args.saipen_action == "participant":
            # V6-06: the project comes from the admitted SAIPEN binding, never a
            # caller string; registry work needs no private key (header view).
            registry = _participants_engine()
            workspace = _workspace_engine().load_workspace_headers(args.workspace)
            lineage = bridge.enter(workspace, project["state"], project["identity"],
                                   seat=args.seat)["saipen"]["lineage"]
            if args.participant_action == "admit":
                return registry.admit_participant(workspace, lineage, args.participant,
                                                  alias=args.alias, triggers=args.trigger)
            if args.participant_action == "revoke":
                return registry.revoke_participant(workspace, lineage, args.participant)
            if args.participant_action == "resolve":
                return registry.resolve_participant(workspace, lineage, args.participant,
                                                    trigger=args.trigger_name)
            return registry.list_participants(workspace, lineage)
        if args.saipen_action == "enter":
            workspace = _workspace_engine().load_workspace_headers(args.workspace)
            return bridge.enter(workspace, project["state"], project["identity"], seat=args.seat)
        if args.saipen_action == "brief":
            workspace = _workspace_engine().load_workspace_headers(args.workspace)
            return bridge.work_brief(workspace, project["state"], project["identity"],
                                     seat=args.seat, scan_budget=args.scan_budget,
                                     cursor=args.cursor, context=args.context)
        if args.saipen_action == "telegram":
            workspace = _workspace_engine().load_workspace(args.workspace)
            return bridge.telegram(workspace, args.to, project["state"], project["identity"],
                                   log_paths=project["logs"], claim=args.claim,
                                   event=args.event, kind=args.kind, topic=args.topic,
                                   seat=args.seat)
        if args.saipen_action == "status":
            return bridge.status(project["state"], project["identity"], seat=args.seat,
                                 workspace_root=args.workspace)
        if args.saipen_action == "init":
            return bridge.init(project["state"], project["identity"],
                               workspace_root=args.workspace, seat=args.seat,
                               custody=args.custody)
        lineage = bridge.read_lineage(project["identity"])
        if args.saipen_action == "cite":
            return bridge.cite(project["logs"], args.event, lineage=lineage, out=args.out)
        return bridge.verify_citation(args.record, project["logs"], lineage=lineage)

    return _dispatch_workspace(f"saipen-{args.saipen_action}", action, as_json,
                               bridge.OPERATOR_ACTION_CODES
                               | _participants_engine().OPERATOR_ACTION_CODES
                               | _notify_engine().OPERATOR_ACTION_CODES)


def _acceptance_runner() -> str:
    """The file to execute for one isolated invocation of this same CLI."""
    return str(Path(__file__).resolve())


class _Acceptance:
    """One isolated multi-invocation V2-01 acceptance run (spec/17)."""

    def __init__(self, base: Path):
        self.base = base
        self.checks: list = []
        self.steps: list = []
        self.results: dict = {}
        self.network_attempts = 0
        self.secret: str | None = None

    def check(self, check_id: str, condition: object, detail: str = "") -> bool:
        ok = bool(condition)
        self.checks.append({"id": check_id, "ok": ok,
                            "detail": "" if ok else (detail or "check failed")})
        return ok

    def step(self, step_id: str, *args: str) -> dict:
        completed = subprocess.run(
            [sys.executable, _acceptance_runner(), *args, "--json"],
            capture_output=True, text=True, check=False,
            cwd=str(self.base))
        payload = None
        try:
            payload = json.loads(completed.stdout)
        except ValueError:
            payload = None
        safe_args = ["<redacted>" if (self.secret and token == self.secret) else token
                     for token in args]
        record = {
            "id": step_id, "args": safe_args,
            "exit_code": completed.returncode,
            "status": (payload or {}).get("status"),
            "ok": completed.returncode == 0 and isinstance(payload, dict),
        }
        self.steps.append(record)
        self.results[step_id] = payload if isinstance(payload, dict) else {}
        self.network_attempts += int((payload or {}).get("network_attempts", 0) or 0)
        return payload or {}

    def run(self) -> dict:
        from saimail import workspace

        self.base.mkdir(parents=True, exist_ok=True)
        ws_a = self.base / "workspace-a"
        ws_b = self.base / "workspace-b"
        card_a = self.base / "identity-a.card.json"
        card_b = self.base / "identity-b.card.json"
        marker = "v2-01 synthetic operator message 7c1d"
        claim = marker + " queue-lease note"
        self.secret = claim

        init_a = self.step("init-a", "init", "--workspace", str(ws_a), "--seat", "SAIMAIL-A")
        init_b = self.step("init-b", "init", "--workspace", str(ws_b), "--seat", "SAIMAIL-B")
        self.check("init_created", init_a.get("status") == workspace.CREATED
                   and init_b.get("status") == workspace.CREATED)
        self.check("workspaces_distinct_roots",
                   ws_a.is_dir() and ws_b.is_dir() and ws_a != ws_b)
        self.check("identities_distinct",
                   init_a.get("identity", {}).get("sender_kid")
                   != init_b.get("identity", {}).get("sender_kid"))

        card_export_a = self.step("card-a", "identity", "--workspace", str(ws_a),
                                  "--export-card", str(card_a))
        card_export_b = self.step("card-b", "identity", "--workspace", str(ws_b),
                                  "--export-card", str(card_b))
        self.check("cards_exported", card_a.is_file() and card_b.is_file()
                   and card_export_a.get("status") == workspace.IDENTITY_CARD_EXPORTED
                   and card_export_b.get("status") == workspace.IDENTITY_CARD_EXPORTED)

        reg_a = self.step("recipient-a", "recipient", "add", "--workspace", str(ws_a),
                          "--alias", "bob", "--card", str(card_b),
                          "--peer-workspace", str(ws_b))
        reg_b = self.step("recipient-b", "recipient", "add", "--workspace", str(ws_b),
                          "--alias", "alice", "--card", str(card_a),
                          "--peer-workspace", str(ws_a))
        self.check("recipients_registered",
                   reg_a.get("status") == workspace.RECIPIENT_ADDED
                   and reg_b.get("status") == workspace.RECIPIENT_ADDED)

        sent = self.step("send", "send", "--workspace", str(ws_a), "--to", "bob",
                         "--claim", claim)
        envelope_id = (sent.get("message") or {}).get("envelope_id")
        received_at = (sent.get("message") or {}).get("received_at")
        self.check("send_accepted", sent.get("status") == "ACCEPTED"
                   and isinstance(envelope_id, str))
        # every step above ran in its own process: this IS the restart boundary

        inbox_one = self.step("inbox-after-send", "inbox", "--workspace", str(ws_b))
        items_one = inbox_one.get("items") or []
        self.check("inbox_one_unread", len(items_one) == 1
                   and items_one[0].get("state") == "UNREAD"
                   and items_one[0].get("envelope_id") == envelope_id,
                   f"items={[(i.get('envelope_id'), i.get('state')) for i in items_one]}")
        self.check("list_metadata_only", marker not in json.dumps(inbox_one))

        opened = self.step("open", "open", "--workspace", str(ws_b),
                           "--envelope", envelope_id)
        self.check("open_exact_message",
                   opened.get("status") == "READ"
                   and (opened.get("record") or {}).get("claim") == claim)
        self.check("open_no_promotion",
                   (opened.get("record") or {}).get("evidence_state")
                   == "EVIDENCE_EXPLICITLY_ABSENT"
                   and (opened.get("record") or {}).get("status") == "U1")

        inbox_read = self.step("inbox-after-open", "inbox", "--workspace", str(ws_b))
        items_read = inbox_read.get("items") or []
        self.check("read_state_persists", len(items_read) == 1
                   and items_read[0].get("state") == "READ")
        self.check("list_metadata_only_after_open", marker not in json.dumps(inbox_read))

        identity_again = self.step("identity-a-again", "identity", "--workspace", str(ws_a))
        self.check("identity_stable_across_invocations",
                   (identity_again.get("identity") or {}).get("sender_kid")
                   == (init_a.get("identity") or {}).get("sender_kid")
                   and (identity_again.get("identity") or {}).get("recipient_kid")
                   == (init_a.get("identity") or {}).get("recipient_kid"))

        replay = self.step("redeliver", "send", "--workspace", str(ws_a),
                           "--redeliver", envelope_id)
        self.check("duplicate_suppressed", replay.get("status") == "DUPLICATE")
        self.check("duplicate_same_received_at",
                   (replay.get("message") or {}).get("received_at") == received_at,
                   f"replay={(replay.get('message') or {}).get('received_at')} "
                   f"original={received_at}")
        inbox_after_replay = self.step("inbox-after-replay", "inbox", "--workspace", str(ws_b))
        items_replay = inbox_after_replay.get("items") or []
        self.check("duplicate_no_second_message",
                   len(items_replay) == 1
                   and sum(1 for i in items_replay if i.get("state") == "UNREAD") == 0)

        outputs = json.dumps(self.results) + "\n" + json.dumps(self.steps)
        private_hexes = [
            json.loads((target / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME)
                       .read_text(encoding="utf-8"))[field]
            for target in (ws_a, ws_b)
            for field in ("sender_private_key", "recipient_private_key")]
        key_in_outputs = any(private_hex in outputs for private_hex in private_hexes)
        marker_on_disk = self._marker_in_files(marker)
        self.check("privacy_key_material_absent_from_outputs", not key_in_outputs)
        self.check("privacy_plaintext_marker_not_on_disk", not marker_on_disk)
        self.check("zero_network_model",
                   self.network_attempts == 0
                   and all(step["ok"] for step in self.steps))

        result = {
            "schema": ACCEPTANCE_SCHEMA,
            "version": ACCEPTANCE_VERSION,
            "status": WR_FAIL,
            "workspaces": {
                "A": {"root": str(ws_a), "seat": "SAIMAIL-A",
                      "sender_kid": (init_a.get("identity") or {}).get("sender_kid"),
                      "recipient_kid": (init_a.get("identity") or {}).get("recipient_kid")},
                "B": {"root": str(ws_b), "seat": "SAIMAIL-B",
                      "sender_kid": (init_b.get("identity") or {}).get("sender_kid"),
                      "recipient_kid": (init_b.get("identity") or {}).get("recipient_kid")},
            },
            "steps": self.steps,
            "checks": self.checks,
            "send": {"envelope_id": envelope_id,
                     "status": sent.get("status"), "received_at": received_at},
            "duplicate": {"status": replay.get("status"),
                          "received_at": (replay.get("message") or {}).get("received_at"),
                          "same_received_at": (replay.get("message") or {}).get("received_at")
                                              == received_at,
                          "messages_after": len(items_replay),
                          "unread_after": sum(1 for i in items_replay
                                              if i.get("state") == "UNREAD")},
            "restart": {"invocations": len(self.steps),
                        "identity_stable": True,
                        "read_state_persisted": True},
            "privacy": {"private_key_material_in_outputs": key_in_outputs,
                        "plaintext_marker_on_disk": marker_on_disk,
                        "plaintext_marker_in_results": False},
            "zero_network_model": {"network_attempts": self.network_attempts,
                                   "provider_calls": 0, "model_calls": 0},
            "artifacts": {"root": str(self.base), "retained": True},
        }
        marker_in_result = marker in json.dumps(result)
        result["privacy"]["plaintext_marker_in_results"] = marker_in_result
        self.check("privacy_plaintext_marker_absent_from_result", not marker_in_result)
        result["status"] = WR_PASS if all(entry["ok"] for entry in self.checks) else WR_FAIL
        return result

    def _marker_in_files(self, marker: str) -> bool:
        needle = marker.encode("utf-8")
        for path in sorted(self.base.rglob("*")):
            if not path.is_file():
                continue
            try:
                if needle in path.read_bytes():
                    return True
            except OSError:
                continue
        return False


def _cmd_acceptance(args, as_json: bool) -> int:
    owned = args.root is None
    base = Path(args.root) if args.root else Path(
        tempfile.mkdtemp(prefix="saimail-workspace-acceptance-"))
    probe = {"blocked": 0, "python": sys.version.split()[0], "platform": sys.platform}
    try:
        if base.exists() and any(base.iterdir()):
            result = {
                "schema": ACCEPTANCE_SCHEMA, "version": ACCEPTANCE_VERSION, "status": WR_FAIL,
                "checks": [{"id": "isolated_root", "ok": False,
                            "detail": f"{base} is not empty; the acceptance root must be fresh"}],
                "artifacts": {"root": str(base), "retained": False},
            }
        else:
            with no_network(probe):
                result = _Acceptance(base).run()
            result["zero_network_model"]["network_attempts"] += probe["blocked"]
            if probe["blocked"]:
                result["status"] = WR_FAIL
            result["artifacts"]["retained"] = bool(args.keep or not owned)
        if args.out is not None:
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / "local_workspace_result.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if as_json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(_render_acceptance(result))
        return 0 if result["status"] == WR_PASS else 1
    finally:
        if owned and not args.keep:
            shutil.rmtree(base, ignore_errors=True)


def _render_acceptance(result: dict) -> str:
    checks = result.get("checks") or []
    lines = [
        "V2-01 LOCAL WORKSPACE ACCEPTANCE",
        f"STATUS:   {result.get('status')}",
        f"SCHEMA:   {result.get('schema')} v{result.get('version')}",
        f"STEPS:    {len(result.get('steps') or [])} isolated invocations",
        f"CHECKS:   {sum(1 for c in checks if c['ok'])}/{len(checks)} passed",
        "NETWORK:  " + str((result.get("zero_network_model") or {}).get("network_attempts")),
        f"ROOT:     {(result.get('artifacts') or {}).get('root')}",
    ]
    for entry in checks:
        if not entry["ok"]:
            lines.append(f"  FAILED {entry['id']}: {entry['detail']}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="saimail-local",
        description="SAIMAIL minimal local entrypoint (offline demo, utility benchmark "
                    "and persistent local workspace).")
    parser.add_argument("--version", action="store_true", help="print the version and result schemas")
    parser.add_argument("--demo", action="store_true", help="run the FG-05 end-to-end demo (default)")
    parser.add_argument("--utility", action="store_true", help="run the FG-06 utility benchmark")
    parser.add_argument("--out", default=None, help="write machine-readable result and summary to this directory")
    parser.add_argument("--keep", action="store_true", help="retain the temporary workspace and print its path")
    parser.add_argument("--json", action="store_true", help="print the machine-readable result to stdout")
    parser.add_argument("--api-map", action="store_true", help="print the shipped stable API map path")

    sub = parser.add_subparsers(dest="subcommand")

    init_p = sub.add_parser("init", help="initialize a persistent local workspace")
    init_p.add_argument("--workspace", required=True, help="workspace root directory")
    init_p.add_argument("--seat", required=True, help="this workspace's local seat identity")
    init_p.add_argument("--custody", default="raw",
                        help="identity key custody: raw (default, portable) or os-store "
                             "(private keys in the OS credential store; spec/20)")
    init_p.add_argument("--json", action="store_true", dest="sub_json")

    identity_p = sub.add_parser("identity", help="show this workspace's public identity")
    identity_p.add_argument("--workspace", required=True)
    identity_p.add_argument("--export-card", default=None,
                            help="write the public identity card (exchange artifact)")
    identity_p.add_argument("--json", action="store_true", dest="sub_json")

    recipient_p = sub.add_parser("recipient", help="manage explicit local recipients")
    recipient_sub = recipient_p.add_subparsers(dest="recipient_action", required=True)
    recipient_add = recipient_sub.add_parser("add", help="register one recipient by identity card")
    recipient_add.add_argument("--workspace", required=True)
    recipient_add.add_argument("--alias", required=True, help="the local operator name for this recipient")
    recipient_add.add_argument("--card", required=True, help="the recipient's public identity card file")
    recipient_add.add_argument("--peer-workspace", required=True,
                               help="the recipient workspace root used as the local delivery boundary")
    recipient_add.add_argument("--json", action="store_true", dest="sub_json")
    recipient_list = recipient_sub.add_parser("list", help="list registered recipients")
    recipient_list.add_argument("--workspace", required=True)
    recipient_list.add_argument("--json", action="store_true", dest="sub_json")

    send_p = sub.add_parser(
        "send",
        help="seal and deliver one real local message",
        description=(
            "Seal and deliver one real local message. A letter to a person is RARE on "
            "purpose: send one only when the operator is probably not reading the chat "
            "AND it changes what they must do or decide (a hard stop only they can lift, "
            "a risk of losing data or money, a discovery that changes other projects). "
            "Never for a finished ticket, test results, a summary or anything already said "
            "in the chat; at most one per decision. See README: When a letter is worth writing."
        ),
    )
    send_p.add_argument("--workspace", required=True)
    send_p.add_argument("--to", default=None, help="registered recipient alias")
    send_p.add_argument("--claim", default=None, help="one line of operator text (canonical wrapper)")
    send_p.add_argument("--record", default=None, help="existing canonical SAILANG record file")
    send_p.add_argument("--subject", default="local-message")
    send_p.add_argument("--topic", default="local-message")
    send_p.add_argument("--kind", default="PERSONAL_MESSAGE")
    send_p.add_argument("--redeliver", default=None,
                        help="replay one exact outbox container by ENVELOPE_ID")
    send_p.add_argument("--json", action="store_true", dest="sub_json")

    inbox_p = sub.add_parser(
        "inbox", help="list received messages (metadata only); add filters for a "
                      "bounded metadata query")
    inbox_p.add_argument("--workspace", required=True)
    inbox_p.add_argument("--from-seat", dest="from_seat", default=None,
                         help="exact sender seat filter")
    inbox_p.add_argument("--topic", default=None, help="exact topic token filter")
    inbox_p.add_argument("--kind", default=None,
                         help="exact closed SENV2 kind filter")
    inbox_p.add_argument("--state", default=None, choices=["UNREAD", "READ", "EXPIRED"],
                         help="durable state filter")
    inbox_p.add_argument("--ref", default=None, help="exact canonical ref filter")
    inbox_p.add_argument("--since", default=None,
                         help="received_at lower bound, inclusive (UTC timestamp)")
    inbox_p.add_argument("--before", default=None,
                         help="received_at upper bound, exclusive (UTC timestamp)")
    inbox_p.add_argument("--scan-budget", dest="scan_budget", type=int, default=None,
                         help="maximum index rows to examine (bounded query)")
    inbox_p.add_argument("--cursor", type=int, default=None,
                         help="opaque continuation offset from a previous query page")
    inbox_p.add_argument("--json", action="store_true", dest="sub_json")

    open_p = sub.add_parser("open", help="explicitly open one exact message")
    open_p.add_argument("--workspace", required=True)
    open_p.add_argument("--envelope", required=True, help="ENVELOPE_ID to open")
    open_p.add_argument("--json", action="store_true", dest="sub_json")

    reopen_p = sub.add_parser("reopen", help="explicitly reopen one already-opened (READ) message")
    reopen_p.add_argument("--workspace", required=True)
    reopen_p.add_argument("--envelope", required=True, help="ENVELOPE_ID of the already-read message to reopen")
    reopen_p.add_argument("--json", action="store_true", dest="sub_json")

    reply_p = sub.add_parser(
        "reply", help="continue one already-opened message (one-hop correspondence; "
                      "sets the existing SENV2 REF to the original ENVELOPE_ID)")
    reply_p.add_argument("--workspace", required=True)
    reply_p.add_argument("--envelope", required=True,
                         help="ENVELOPE_ID of the already-opened (READ) target")
    reply_p.add_argument("--claim", default=None, help="one line of operator text (canonical wrapper)")
    reply_p.add_argument("--record", default=None, help="existing canonical SAILANG record file")
    reply_p.add_argument("--subject", default="local-message")
    reply_p.add_argument("--topic", default=None,
                         help="reply topic; defaults to the original envelope topic")
    reply_p.add_argument("--kind", default="PERSONAL_MESSAGE",
                         help="reply transport kind; the original kind is never inherited")
    reply_p.add_argument("--json", action="store_true", dest="sub_json")

    custody_p = sub.add_parser("custody", help="workspace identity key custody at rest (V3-01)")
    custody_sub = custody_p.add_subparsers(dest="custody_action", required=True)
    custody_status_p = custody_sub.add_parser(
        "status", help="read-only custody diagnosis: mode, backend, loadability")
    custody_status_p.add_argument("--workspace", required=True)
    custody_status_p.add_argument("--json", action="store_true", dest="sub_json")
    custody_migrate_p = custody_sub.add_parser(
        "migrate", help="explicitly move one raw workspace identity into OS-store custody")
    custody_migrate_p.add_argument("--workspace", required=True)
    custody_migrate_p.add_argument("--json", action="store_true", dest="sub_json")

    outbox_p = sub.add_parser(
        "outbox", help="durable idempotent sends that survive crashes and retries (V6-05)")
    outbox_sub = outbox_p.add_subparsers(dest="outbox_action", required=True)
    outbox_send_p = outbox_sub.add_parser(
        "send", help="record one send under an idempotency key, then seal and deliver it once")
    outbox_send_p.add_argument("--to", required=True, help="registered recipient alias")
    outbox_send_p.add_argument("--key", required=True,
                               help="idempotency key: the same key never sends twice")
    outbox_body = outbox_send_p.add_mutually_exclusive_group(required=True)
    outbox_body.add_argument("--claim", default=None, help="one line of operator text")
    outbox_body.add_argument("--record", default=None, help="canonical SAILANG record file")
    outbox_send_p.add_argument("--subject", default="local-message")
    outbox_send_p.add_argument("--topic", default="local-message")
    outbox_send_p.add_argument("--kind", default="PERSONAL_MESSAGE")
    outbox_send_p.add_argument("--no-deliver", action="store_true",
                               help="record and seal only; a later resume delivers")
    outbox_resume_p = outbox_sub.add_parser(
        "resume", help="advance due pending intents; a replay is never a second message")
    outbox_resume_p.add_argument("--budget", type=int, default=25)
    outbox_retry_p = outbox_sub.add_parser(
        "retry", help="explicitly re-arm one FAILED intent and attempt it once")
    outbox_retry_p.add_argument("--key", required=True)
    outbox_status_p = outbox_sub.add_parser(
        "status", help="keyless, plaintext-free outbox health")
    for outbox_action_p in (outbox_send_p, outbox_resume_p, outbox_retry_p, outbox_status_p):
        outbox_action_p.add_argument("--workspace", required=True)
        outbox_action_p.add_argument("--json", action="store_true", dest="sub_json")

    saipen_p = sub.add_parser(
        "saipen", help="bind to the enclosing SAIPEN project and cite its LOG (spec/04 S2)")
    saipen_sub = saipen_p.add_subparsers(dest="saipen_action", required=True)
    saipen_status_p = saipen_sub.add_parser(
        "status", help="read-only: acting seat, lineage, current work")
    saipen_status_p.add_argument("--workspace", default=None,
                                 help="also report whether this workspace exists")
    saipen_init_p = saipen_sub.add_parser(
        "init", help="initialize a workspace for the acting SAIPEN seat")
    saipen_init_p.add_argument("--workspace", required=True,
                               help="workspace root directory (caller-supplied)")
    saipen_init_p.add_argument("--custody", default="raw", choices=["raw", "os-store"])
    for saipen_seat_p in (saipen_status_p, saipen_init_p):
        saipen_seat_p.add_argument(
            "--seat", default=None,
            help="acting seat (default: SAIPEN_AGENT, else STATE.agent)")
    saipen_cite_p = saipen_sub.add_parser(
        "cite", help="one KIND:O record whose EV is the sha256 of one exact LOG line")
    saipen_cite_p.add_argument("--event", required=True, help="SAIPEN event id, e.g. E-1358")
    saipen_cite_p.add_argument("--out", default=None, help="write the canonical record here")
    saipen_verify_p = saipen_sub.add_parser(
        "verify", help="re-hash the cited LOG line and compare it with the record's EV")
    saipen_verify_p.add_argument("--record", required=True, help="cited SAILANG record file")
    saipen_tel_p = saipen_sub.add_parser(
        "telegram", help="SAITELEME: tell one registered running agent one thing now (spec/26)")
    saipen_tel_p.add_argument("--workspace", required=True, help="the acting seat's workspace")
    saipen_tel_p.add_argument("--to", required=True, help="registered recipient alias")
    saipen_tel_body = saipen_tel_p.add_mutually_exclusive_group(required=True)
    saipen_tel_body.add_argument("--claim", default=None, help="one line of text")
    saipen_tel_body.add_argument("--event", default=None,
                                 help="cite this SAIPEN LOG event instead (E-###)")
    saipen_tel_p.add_argument("--kind", default="DISCOVERY",
                              help="closed SENV2 kind (default DISCOVERY)")
    saipen_tel_p.add_argument("--topic", default=None,
                              help="default: the SAIPEN Work id from STATE.task")
    saipen_tel_p.add_argument("--seat", default=None,
                              help="acting seat (default: SAIPEN_AGENT, else STATE.agent)")
    saipen_tels_p = saipen_sub.add_parser(
        "telegrams", help="turn-entry read: bounded header-only UNREAD rows, nothing opened")
    saipen_tels_p.add_argument("--workspace", required=True)
    saipen_tels_p.add_argument("--topic", default=None, help="exact topic (Work id) filter")
    saipen_tels_p.add_argument("--scan-budget", dest="scan_budget", type=int, default=None)
    saipen_tels_p.add_argument("--cursor", type=int, default=None)
    saipen_brief_p = saipen_sub.add_parser(
        "brief", help="work context and one bounded page of unread telegrams, grouped by topic")
    saipen_brief_p.add_argument("--workspace", required=True, help="the acting seat's workspace")
    saipen_brief_p.add_argument("--seat", default=None,
                                help="acting seat (default: SAIPEN_AGENT, else STATE.agent)")
    saipen_brief_p.add_argument("--scan-budget", type=int, default=None)
    saipen_brief_p.add_argument("--cursor", type=int, default=None)
    saipen_brief_p.add_argument("--context", default=None,
                                help="context token returned by brief; required with a continuation cursor")
    saipen_enter_p = saipen_sub.add_parser(
        "enter", help="check SAIPEN project participation and the acting workspace seat")
    saipen_enter_p.add_argument("--workspace", required=True)
    saipen_enter_p.add_argument("--seat", default=None,
                                help="acting seat (default: SAIPEN_AGENT, else STATE.agent)")
    saipen_notify_p = saipen_sub.add_parser(
        "notify", help="automatic SAITELEME for a closed trigger to an admitted participant (V6-08)")
    saipen_notify_p.add_argument("--workspace", required=True, help="the acting seat's workspace")
    saipen_notify_p.add_argument("--trigger", required=True,
                                 help="closed set: blocker, finding, dependency, ownership, "
                                      "handoff, reply")
    saipen_notify_p.add_argument("--to", required=True, help="admitted participant seat")
    saipen_notify_body = saipen_notify_p.add_mutually_exclusive_group(required=True)
    saipen_notify_body.add_argument("--claim", default=None, help="one line of text")
    saipen_notify_body.add_argument("--event", default=None,
                                    help="cite this SAIPEN LOG event instead (E-###)")
    saipen_notify_p.add_argument("--work", default=None,
                                 help="Work id on this project's BOARD (default: STATE.task)")
    saipen_notify_p.add_argument("--seat", default=None,
                                 help="acting seat (default: SAIPEN_AGENT, else STATE.agent)")
    saipen_caps_p = saipen_sub.add_parser(
        "capabilities", help="keyless capability and health document for SAIPEN entry (V6-07)")
    saipen_caps_p.add_argument("--workspace", required=True, help="the acting seat's workspace")
    saipen_caps_p.add_argument("--seat", default=None,
                               help="acting seat (default: SAIPEN_AGENT, else STATE.agent)")
    saipen_part_p = saipen_sub.add_parser(
        "participant", help="project-local participant registry for automatic routing (V6-06)")
    saipen_part_sub = saipen_part_p.add_subparsers(dest="participant_action", required=True)
    part_admit_p = saipen_part_sub.add_parser(
        "admit", help="explicitly admit one registered seat as a participant of this project")
    part_admit_p.add_argument("--alias", default=None,
                              help="registered recipient alias (default: the seat)")
    part_admit_p.add_argument("--trigger", action="append", default=None,
                              help="notify trigger this participant may receive (repeat; "
                                   "default: the whole closed set)")
    part_revoke_p = saipen_part_sub.add_parser("revoke", help="remove one participant")
    part_resolve_p = saipen_part_sub.add_parser(
        "resolve", help="the alias automation would use for one seat and trigger")
    part_resolve_p.add_argument("--trigger", dest="trigger_name", required=True)
    part_list_p = saipen_part_sub.add_parser("list", help="admitted participants of this project")
    for part_p in (part_admit_p, part_revoke_p, part_resolve_p):
        part_p.add_argument("--participant", required=True, help="participant seat")
    for part_p in (part_admit_p, part_revoke_p, part_resolve_p, part_list_p):
        part_p.add_argument("--workspace", required=True, help="the acting seat's workspace")
        part_p.add_argument("--seat", default=None,
                            help="acting seat (default: SAIPEN_AGENT, else STATE.agent)")
        part_p.add_argument("--project-root", default=None,
                            help="SAIPEN project root (default: nearest with .saipen/)")
        part_p.add_argument("--json", action="store_true", dest="sub_json")
    for saipen_action_p in (saipen_status_p, saipen_init_p, saipen_cite_p, saipen_verify_p,
                            saipen_tel_p, saipen_tels_p, saipen_brief_p, saipen_enter_p,
                            saipen_caps_p, saipen_notify_p):
        saipen_action_p.add_argument("--project-root", default=None,
                                     help="SAIPEN project root (default: nearest with .saipen/)")
        saipen_action_p.add_argument("--json", action="store_true", dest="sub_json")

    accept_p = sub.add_parser("acceptance", help="run the isolated multi-invocation V2-01 acceptance")
    accept_p.add_argument("--root", default=None, help="fresh root for the two workspaces")
    accept_p.add_argument("--out", default=None, help="write the machine-readable result here")
    accept_p.add_argument("--keep", action="store_true", help="retain the acceptance root")
    accept_p.add_argument("--json", action="store_true", dest="sub_json")
    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(f"saimail {_version()}")
        print(f"local scenario: {_engine().SCENARIO} v{_engine().SCENARIO_VERSION} "
              f"({_engine().RESULT_SCHEMA})")
        print(f"utility: {_utility_engine().UTILITY_SCHEMA} v{_utility_engine().UTILITY_VERSION}")
        print(f"local workspace: {_workspace_engine().WORKSPACE_SCHEMA} "
              f"v{_workspace_engine().WORKSPACE_VERSION} ({ACCEPTANCE_SCHEMA})")
        return 0
    if args.api_map:
        print(str(_api_map_path()))
        return 0

    if args.subcommand is not None:
        as_json = bool(getattr(args, "sub_json", False) or args.json)
        if args.subcommand == "init":
            return _cmd_init(args, as_json)
        if args.subcommand == "identity":
            return _cmd_identity(args, as_json)
        if args.subcommand == "recipient":
            return _cmd_recipient(args, as_json)
        if args.subcommand == "send":
            return _cmd_send(args, as_json)
        if args.subcommand == "inbox":
            return _cmd_inbox(args, as_json)
        if args.subcommand == "open":
            return _cmd_open(args, as_json)
        if args.subcommand == "reopen":
            return _cmd_reopen(args, as_json)
        if args.subcommand == "reply":
            return _cmd_reply(args, as_json)
        if args.subcommand == "custody":
            return _cmd_custody(args, as_json)
        if args.subcommand == "saipen":
            return _cmd_saipen(args, as_json)
        if args.subcommand == "outbox":
            return _cmd_outbox(args, as_json)
        if args.subcommand == "acceptance":
            return _cmd_acceptance(args, as_json)
        parser.error(f"unknown subcommand {args.subcommand!r}")

    mode = "utility" if args.utility else "demo"
    base = Path(tempfile.mkdtemp(prefix=f"saimail-{mode}-"))
    probe: dict = {"blocked": 0, "python": sys.version.split()[0], "platform": sys.platform}
    try:
        with no_network(probe):
            result = _run(mode, base, probe)
        if probe["blocked"]:
            result["status"] = "FAIL"
            result.setdefault("zero_network_model", {})["network_attempts"] = probe["blocked"]
        result.setdefault("entrypoint", {})["mode"] = mode
        result["entrypoint"]["version"] = _version()
        result["entrypoint"]["api_map"] = str(_api_map_path())
        result.setdefault("artifacts", {})["workspace"] = str(base)
        if args.out is not None:
            _write_outputs(result, Path(args.out), mode)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(render(result, mode))
        result["artifacts"]["retained"] = bool(args.keep)
        if args.keep:
            print(f"WORKSPACE RETAINED: {base}")
        status = result.get("status") or result.get("outcome_category")
        return 0 if status in ("PASS", "UTILITY_POSITIVE", "UTILITY_CONDITIONAL", "UTILITY_NEUTRAL") else 1
    finally:
        if not args.keep:
            shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
