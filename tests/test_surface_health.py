"""FUTURE GATE Wave 7: the surface that describes itself, and health that admits UNKNOWN.

Two defects meet here, and both are the same shape -- a document that is confident
and wrong.

The first is discovery. Waves 1 through 6 added nine verbs to `saimail-local`, and
a reader who consulted any static list learned a surface that had not existed for
five waves. The fix is to walk the registered parser instead of maintaining a
table beside it, so the map is wrong the instant a verb changes -- which is the
only way it can stay right.

The second is the false zero. A dashboard that renders unreadable state as `0`
unread has told an operator that a mailbox is empty when in fact the mailbox
could not be read, and it told them in the exact shape that looks like good news.
So health is three-valued and `UNKNOWN` rolls up to `UNKNOWN` rather than being
promoted to `HEALTHY` by assumption. The same instinct governs the feed: history
trimmed out from under a cursor surfaces as GAP, never as a clean page.

The acceptance cases below are the ones from the wave document:

* adding and removing a command changes the live inventory with no table edit
* unreadable state renders UNKNOWN, and never zero
* a trimmed feed reports its continuity gap
* health truth survives a restart, because it is re-derived and not cached
* the machine surface changes additively, so an older reader still resolves
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from sailang import SailangError
from saimail import ledger, outbox, surface, workspace

ROOT = Path(__file__).resolve().parent.parent
T0 = "2026-10-04T09:00:00Z"

SAIMAIL_LOCAL = ROOT / "saimail_local.py"


def _live_parser():
    """The entrypoint's real parser. A test may import it; `saimail` may not."""
    import saimail_local

    return saimail_local._build_parser()  # noqa: SLF001


def _one(tmp_path, seat="alpha"):
    workspace.init_workspace(tmp_path / seat, seat=seat)
    return workspace.load_workspace(tmp_path / seat)


def _pair(tmp_path):
    """Two crossed workspaces, for the tests that need real delivered mail."""
    workspace.init_workspace(tmp_path / "A", seat="alpha")
    workspace.init_workspace(tmp_path / "B", seat="beta")
    A = workspace.load_workspace(tmp_path / "A")
    B = workspace.load_workspace(tmp_path / "B")
    workspace.add_recipient(A, "beta", workspace.identity_card(B), B.root)
    workspace.add_recipient(B, "alpha", workspace.identity_card(A), A.root)
    return A, B


def _clock(*stamps):
    sequence = list(stamps)

    def now():
        return sequence.pop(0) if len(sequence) > 1 else sequence[0]

    return now


def _note(ws, event, message_id):
    ledger.note(ws, event, message_id=message_id, actor="alpha", at=T0)


def _corrupt_ledger(ws, text):
    """Damage the ledger in place, the way a disk would."""
    path = ledger.ledger_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _trim_ledger(ws, keep: int):
    """Drop the oldest events the way retention does: honestly, and re-chained.

    Rewriting the retained lines verbatim would break the hash chain and yield a
    CHAIN_BROKEN ledger -- a different fault, which would prove nothing about
    gaps. Retention re-chains, so the fixture does too.
    """
    events, _state = ledger.read_events(ws)
    retained = events[-keep:]
    previous = None
    lines = []
    for event in retained:
        record = dict(event)
        # The sequence number is NOT renumbered: retention removes records, it
        # does not pretend they never happened, and the surviving seq is what
        # makes a cursor older than the cut detectable at all.
        record["prev"] = previous
        record.pop("hash", None)
        record["hash"] = ledger._sha256(ledger._event_bytes(record))  # noqa: SLF001
        previous = record["hash"]
        lines.append(ledger._canonical_bytes(record))  # noqa: SLF001
    ledger.ledger_path(ws).write_bytes(b"".join(lines))
    return len(events), len(retained)


def _section(result, name):
    for row in result["health"]["sections"]:
        if row["section"] == name:
            return row
    raise AssertionError(f"no {name} section in {[r['section'] for r in result['health']['sections']]}")


def _state(result, name):
    return _section(result, name)["state"]


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


# --------------------------------------------------------------------------
# acceptance: the live inventory needs no table
# --------------------------------------------------------------------------

def test_adding_a_command_changes_the_inventory_without_a_table(tmp_path):
    """A verb registered in the parser shows up; one removed disappears.

    The proof is a parser, not the shipping one: if the map were backed by a
    literal, these two edits would leave it untouched.
    """
    parser = argparse.ArgumentParser(prog="probe")
    sub = parser.add_subparsers(dest="subcommand")
    sub.add_parser("alpha", help="the first verb")
    sub.add_parser("beta", help="the second verb")
    before = surface.cli_map(parser=parser)
    assert [item["command"] for item in before["commands"]] == ["alpha", "beta"]
    assert before["generated"] is True

    sub.add_parser("gamma", help="added after the first map was taken")
    after = surface.cli_map(parser=parser)
    assert "gamma" in {item["command"] for item in after["commands"]}
    assert after["command_count"] == 3

    del parser._subparsers._group_actions[0].choices["beta"]  # noqa: SLF001
    removed = surface.cli_map(parser=parser)
    assert "beta" not in {item["command"] for item in removed["commands"]}
    assert removed["command_count"] == 2


def test_the_shipping_map_walks_the_real_parser():
    """The source is the entrypoint's own parser, not a copy of it."""
    inventory = surface.cli_map(parser=_live_parser())
    registered = set(_live_parser()._subparsers._group_actions[0].choices)  # noqa: SLF001
    assert {item["command"] for item in inventory["commands"]} == registered
    assert inventory["prog"] == "saimail-local"


def test_the_package_never_imports_the_entrypoint():
    """The dependency runs one way.

    `surface` needs the verb tree and `saimail_local` holds it, so the temptation
    is to reach back for it. That would make the library unloadable without its
    own command line, and the repo-consistency check refuses it for exactly that
    reason -- so the boundary is pinned here rather than left to be rediscovered.
    """
    import saimail

    assert "saimail_local" not in (ROOT / "saimail" / "surface.py").read_text(
        encoding="utf-8")
    assert surface.cli_map.__doc__ is not None
    assert saimail.__file__


def test_the_map_carries_flags_and_nesting():
    """A reader gets the shape it would otherwise have to run --help to learn."""
    inventory = surface.cli_map(parser=_live_parser())
    commands = {item["command"]: item for item in inventory["commands"]}
    init = commands["init"]
    flags = {flag["flag"]: flag for flag in init["flags"]}
    assert flags["--workspace"]["required"] is True
    assert flags["--seat"]["required"] is True
    assert flags["--custody"]["required"] is False
    assert flags["--custody"]["takes_value"] is True
    assert init["accepts_json"] is True
    # `saipen init` is the one that constrains custody to a closed set, so the
    # map must carry `choices` where the parser declares them and nowhere else.
    saipen_children = {child["command"]: child
                       for child in commands["saipen"]["subcommands"]}
    saipen_init = saipen_children["init"]
    custody = {flag["flag"]: flag for flag in saipen_init["flags"]}["--custody"]
    assert custody["choices"] == ["raw", "os-store"]
    # `recipient` nests, so a flat map would describe only half the surface.
    assert {child["command"] for child in commands["recipient"]["subcommands"]} >= {"add", "list"}
    assert commands["surface"]["subcommands"], "a nested group lost its children"
    assert {child["command"] for child in commands["surface"]["subcommands"]} == {
        "map", "schema", "health", "feed"}


# --------------------------------------------------------------------------
# acceptance: unreadable state is UNKNOWN, not zero
# --------------------------------------------------------------------------

def test_health_has_exactly_three_verdicts():
    assert surface.VERDICTS == (surface.HEALTHY, surface.UNHEALTHY, surface.UNKNOWN)
    assert "ABSENT" not in surface.CANNOT_TELL


def test_a_fresh_mailbox_is_healthy_not_unknown(tmp_path):
    """No ledger and no archive is nothing at risk, and must not read as a fault.

    An UNKNOWN that appears on every brand new workspace is an UNKNOWN an
    operator learns to ignore, which is the same as having no UNKNOWN at all.
    """
    result = surface.health(_one(tmp_path))
    assert result["health"]["state"] == surface.HEALTHY
    assert result["health"]["unknown"] == []
    assert result["health"]["unhealthy"] == []


def test_an_unreadable_ledger_renders_unknown_and_publishes_no_numbers(tmp_path):
    """The headline case of this wave.

    Wave 2 promised that an unreadable ledger never renders `0 pending`. The
    dashboard has to keep that promise: a reader must be able to tell "nothing
    happened" from "I cannot see what happened", and the numbers must be absent
    rather than zero.
    """
    ws = _one(tmp_path)
    _note(ws, ledger.DELIVERY_ATTEMPTED, "m1")
    _corrupt_ledger(ws, "{ this is not the ledger")

    result = surface.health(ws)
    assert result["health"]["state"] == surface.UNKNOWN
    assert "receipts" in result["health"]["unknown"]
    receipts = _section(result, "receipts")
    assert receipts["state"] == surface.UNKNOWN
    assert receipts["counts"] is None, "an unknown section published numbers"
    assert "0" not in json.dumps(receipts["counts"])


def test_unknown_does_not_roll_up_to_healthy(tmp_path):
    """A mailbox that cannot describe part of itself has not been shown fine."""
    ws = _one(tmp_path)
    _note(ws, ledger.DELIVERY_ATTEMPTED, "m1")
    _corrupt_ledger(ws, "garbage")
    result = surface.health(ws)
    assert result["health"]["state"] == surface.UNKNOWN
    assert result["health"]["unknown"], "the unreadable ledger was not surfaced"
    # Every other section still answered; a dashboard that stops at the first
    # broken subsystem is the same all-clear with fewer numbers.
    assert _state(result, "trust") == surface.HEALTHY
    assert _state(result, "archive") == surface.HEALTHY


def test_a_raising_subsystem_is_unknown_rather_than_an_exception(tmp_path, monkeypatch):
    """An exception inside somebody else's function must not crash the caller."""
    ws = _one(tmp_path)

    def explode(_ws):
        raise RuntimeError("the trust registry is on fire")

    monkeypatch.setattr(surface, "SECTIONS",
                        (("trust", "saimail.trust.list_pins", explode),))
    result = surface.health(ws)
    assert result["health"]["state"] == surface.UNKNOWN
    row = _section(result, "trust")
    assert row["reason"] == "RuntimeError"
    assert row["counts"] is None


def test_a_sailang_refusal_is_unknown_and_keeps_its_code(tmp_path, monkeypatch):
    """A subsystem that refuses is UNKNOWN with its own code, not flattened."""
    ws = _one(tmp_path)

    def refuse(_ws):
        raise SailangError("LEDGER_LOCK_TIMEOUT", "the ledger lock is held")

    monkeypatch.setattr(surface, "SECTIONS",
                        (("ledger", "saimail.ledger.feed", refuse),))
    row = _section(surface.health(ws), "ledger")
    assert row["state"] == surface.UNKNOWN
    assert row["reason"] == "LEDGER_LOCK_TIMEOUT"


def test_an_unplaceable_envelope_withholds_the_unread_count(tmp_path, monkeypatch):
    """An index row whose bundles are gone is neither read nor unread.

    Counting it as unread invents an operator task; counting it as read hides a
    delivery. The honest answer is to publish no count at all. The office is
    asked where every other section asks, and its refusal is what is reported.
    """
    from saimail import postoffice

    ws = _one(tmp_path)
    ghost = "sha256:" + "0" * 64
    # Patched on the CLASS: `self_office()` hands back a fresh instance on every
    # call, so a patch on one instance would never be seen by the dashboard.
    monkeypatch.setattr(postoffice.PostOffice, "read_index",
                        lambda _self: ({"envelope_id": ghost},))

    def unplaceable(_self, _envelope_id):
        raise SailangError(postoffice.UNKNOWN_ENVELOPE, "no bundle for it")

    monkeypatch.setattr(postoffice.PostOffice, "bundle_state", unplaceable)
    row = _section(surface.health(ws), "inbox")
    assert row["state"] == surface.UNKNOWN
    assert row["counts"] is None
    assert "withheld" in row["detail"]


def test_an_index_row_with_a_placed_bundle_is_counted(tmp_path, monkeypatch):
    """The negative control: withholding is for what cannot be placed."""
    from saimail import postoffice

    ws = _one(tmp_path)
    ghost = "sha256:" + "0" * 64
    monkeypatch.setattr(postoffice.PostOffice, "read_index",
                        lambda _self: ({"envelope_id": ghost},))
    monkeypatch.setattr(postoffice.PostOffice, "bundle_state",
                        lambda _self, _id: postoffice.UNREAD)
    row = _section(surface.health(ws), "inbox")
    assert row["state"] == surface.HEALTHY
    assert row["counts"] == {"indexed": 1, "unread": 1}


def test_a_real_delivery_counts_as_unread(tmp_path):
    """The counter agrees with the mailbox, not only with a stub.

    A dashboard that says 0 unread on a mailbox holding an unread delivery is
    the false zero this wave exists to remove, and it is also the easiest thing
    to get wrong when the count is written by hand.
    """
    A, B = _pair(tmp_path)
    outbox.submit_send(A, "beta", key="k1", claim="a real fact", clock=_clock(T0))
    assert _section(surface.health(B), "inbox")["counts"]["unread"] == 1


def test_quarantined_mail_is_unhealthy_and_visible(tmp_path):
    """Mail the Post Office refused is a decision waiting, not a footnote."""
    ws = _one(tmp_path)
    quarantine = ws.self_office().mail_root / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    (quarantine / "sha256-deadbeef.json").write_text("{}", encoding="utf-8")
    result = surface.health(ws)
    assert _state(result, "quarantine") == surface.UNHEALTHY
    assert _section(result, "quarantine")["counts"] == {"quarantined": 1}
    assert "quarantine" in result["health"]["unhealthy"]
    assert result["health"]["state"] == surface.UNHEALTHY


def test_each_section_names_the_function_that_produced_it():
    """A dashboard that cannot say who answered a row cannot be audited."""
    result = surface.health.__doc__, None
    assert result is not None
    for name, source, _probe in surface.SECTIONS:
        assert source, f"{name} has no source"
        assert source.startswith("saimail."), f"{name} claims a foreign source"


def test_the_dashboard_asks_each_owner_rather_than_re_deriving(tmp_path, monkeypatch):
    """A section is only ever as good as the function that answered it."""
    ws = _one(tmp_path)
    seen = []

    def fake_health(workspace_arg):
        seen.append(workspace_arg)
        return {"status": "HEALTHY", "ok": True, "detail": "stubbed",
                "counts": {"bundles": 7}}

    monkeypatch.setattr(surface.cold_archive, "health", fake_health)
    row = _section(surface.health(ws), "archive")
    assert seen == [ws], "the archive section did not call cold_archive.health"
    assert row["counts"] == {"bundles": 7}, "the owner's answer was re-derived"


# --------------------------------------------------------------------------
# acceptance: the feed reports its gap
# --------------------------------------------------------------------------

def test_a_trimmed_feed_reports_gap_and_does_not_summarise_it(tmp_path):
    """The one failure a cursor cannot detect on its own.

    A caller following a cursor through trimmed history sees a well-formed page
    and has no way to know records are gone -- unless the feed says so.
    """
    ws = _one(tmp_path)
    for index in range(5):
        _note(ws, ledger.DELIVERY_ATTEMPTED, f"m{index}")

    page = ledger.feed(ws, limit=2, cursor=0)
    assert page["gap"] is False, "the fixture did not start gap-free"
    assert len(page["events"]) == 2

    before, kept = _trim_ledger(ws, keep=1)
    assert (before, kept) == (5, 1), "the trim did not remove four events"
    assert ledger.feed(ws, cursor=0)["ledger"]["state"] == ledger.STATE_OK, \
        "the trimmed ledger is not a readable ledger"

    result = surface.feed(ws, cursor=0)
    assert result["gap"] is True
    assert result["status"] == surface.GAP
    assert result["operator_action_required"] is True
    assert "GAP" in result["detail"]
    assert "not" in result["detail"].lower()
    assert result["feed"]["gap"] is True
    assert result["feed"]["oldest_retained"] == 5, "the retained window is misreported"
    assert len(result["events"]) == 1, "a gap must not be padded with invented events"


def test_a_cursor_at_the_retained_edge_raises_no_gap(tmp_path):
    """The gap is about being EARLY, not about a small ledger."""
    ws = _one(tmp_path)
    for index in range(5):
        _note(ws, ledger.DELIVERY_ATTEMPTED, f"m{index}")
    _trim_ledger(ws, keep=1)
    # The cut fell after seq 4, so a cursor of 0 is early and a cursor of 5 is
    # already inside the retained window. The middle is the interesting part.
    assert surface.feed(ws, cursor=0)["gap"] is True
    assert surface.feed(ws, cursor=3)["gap"] is True, "seq 3 predates the cut"
    assert surface.feed(ws, cursor=4)["gap"] is False, "a retained cursor was called a gap"


def test_an_untrimmed_feed_raises_no_gap(tmp_path):
    ws = _one(tmp_path)
    _note(ws, ledger.DELIVERY_ATTEMPTED, "m0")
    result = surface.feed(ws, cursor=0)
    assert result["gap"] is False
    assert result["status"] == surface.HEALTHY
    assert result["operator_action_required"] is False
    assert result["events"]


def test_an_unreadable_ledger_feed_is_unknown_and_returns_nothing(tmp_path):
    """An empty feed from a broken ledger is the false zero one more time."""
    ws = _one(tmp_path)
    _note(ws, ledger.DELIVERY_ATTEMPTED, "m1")
    _corrupt_ledger(ws, "not a ledger")
    result = surface.feed(ws, cursor=0)
    assert result["status"] == surface.UNKNOWN
    assert result["events"] == []
    assert result["feed"]["event_count"] == 0
    assert "does NOT mean nothing happened" in result["detail"]


def test_the_feed_cursor_advances(tmp_path):
    ws = _one(tmp_path)
    for index in range(4):
        _note(ws, ledger.DELIVERY_ATTEMPTED, f"m{index}")
    first = surface.feed(ws, cursor=0, limit=2)
    assert len(first["events"]) == 2
    second = surface.feed(ws, cursor=first["feed"]["cursor"], limit=2)
    assert second["events"]
    first_ids = {event["message_id"] for event in first["events"]}
    second_ids = {event["message_id"] for event in second["events"]}
    assert not (first_ids & second_ids), "the second page repeated the first"


# --------------------------------------------------------------------------
# acceptance: restart preserves the truth
# --------------------------------------------------------------------------

def test_health_truth_survives_a_restart(tmp_path):
    """Health is re-derived from the mailbox, never cached beside it.

    The child process shares nothing with this one except the directory, so a
    verdict that survived is a verdict about the workspace rather than about a
    live object.
    """
    ws = _one(tmp_path)
    ledger.note(ws, ledger.DELIVERY_ATTEMPTED, message_id="m1",
                actor="alpha", at=T0)
    (ledger.ledger_path(ws)).write_text("broken", encoding="utf-8")
    assert surface.health(ws)["health"]["state"] == surface.UNKNOWN

    script = (
        "import json,sys;sys.path.insert(0,%r)\n"
        "from saimail import surface, workspace\n"
        "ws = workspace.load_workspace(%r)\n"
        "print(json.dumps(surface.health(ws)['health']['state']))\n"
        % (str(ROOT), str(ws.root))
    )
    completed = subprocess.run([sys.executable, "-c", script],
                               capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip()) == surface.UNKNOWN


def test_health_truth_survives_a_restart_when_the_ledger_is_intact(tmp_path):
    """The positive half: a healthy verdict is not a startup artefact either."""
    ws = _one(tmp_path)
    _note(ws, ledger.DELIVERY_ATTEMPTED, "m1")
    script = (
        "import json,sys;sys.path.insert(0,%r)\n"
        "from saimail import surface, workspace\n"
        "ws = workspace.load_workspace(%r)\n"
        "print(json.dumps(surface.health(ws)['health']['state']))\n"
        % (str(ROOT), str(ws.root))
    )
    completed = subprocess.run([sys.executable, "-c", script],
                               capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.strip()) == surface.HEALTHY


# --------------------------------------------------------------------------
# acceptance: the machine surface changes additively
# --------------------------------------------------------------------------

def test_the_capability_schema_carries_the_frozen_contract_forward():
    """Every key a host written against v1 still resolves."""
    from saimail import host_contract

    contract = host_contract.contract()
    schema = surface.capability_schema(parser=_live_parser())
    for key in ("schema", "version", "command_schema", "letter_schema",
                "capabilities_schema", "features", "compatibility", "authority"):
        assert key in schema, f"{key} was dropped"
    for name, value in contract["features"].items():
        assert schema["features"][name] == value, f"feature {name} changed value"
    assert schema["features"] != contract["features"], "no capability was added"


def test_a_capability_is_advertised_only_while_its_command_exists(monkeypatch):
    """Remove the verb and the claim goes with it.

    A capability left advertised after its command is gone is how a host learns
    to send a request that cannot be answered.
    """
    assert surface.capability_schema(parser=_live_parser())["features"]["future_letters"] == 1
    real = surface.cli_map

    monkeypatch.setattr(surface, "cli_map", lambda **_kwargs: {
        "command_count": 0,
        "commands": [{"command": name} for name in
                     ("init", "identity", "send", "trust", "ledger")],
    })
    features = surface.capability_schema(parser=_live_parser())["features"]
    assert features["future_letters"] == 0
    assert features["canary_lane"] == 0
    assert features["trust_identity"] == 1
    assert features["delivery_ledger"] == 1
    monkeypatch.setattr(surface, "cli_map", real)


def test_the_schema_reports_envelope_and_custody_vocabularies():
    schema = surface.capability_schema(parser=_live_parser())
    assert schema["envelope_schemas"], "a reader cannot tell which envelope era it faces"
    assert schema["custody_modes"] == ["raw", "os-store"]
    assert schema["command_schema"] == "LOCAL_WORKSPACE_COMMAND_1"


def test_the_host_contract_points_at_the_generated_map_without_importing_it():
    """The frozen document stays dependency-free and gains a pointer."""
    from saimail import host_contract

    contract = host_contract.contract()
    assert contract["live_surface"]["generated_by"] == "saimail.surface.cli_map"
    assert contract["authority"] == "INFORMATION_ONLY"
    # The intent map is frozen: `health` names an intent, not a verb.
    assert contract["commands"]["health"] == ["saipen", "capabilities"]


# --------------------------------------------------------------------------
# the CLI offers the same answers as the module
# --------------------------------------------------------------------------

def _cli(*argv):
    return subprocess.run([sys.executable, str(SAIMAIL_LOCAL), *argv],
                          capture_output=True, text=True, cwd=str(ROOT))


def test_the_cli_map_lists_the_surface_verb_itself(tmp_path):
    """The self-map is only credible if it includes the verb that prints it."""
    completed = _cli("surface", "map", "--json")
    assert completed.returncode == 0, completed.stderr
    document = json.loads(completed.stdout)["document"]
    assert document["command_count"] >= 20
    assert "surface" in {item["command"] for item in document["commands"]}
    assert "future-letter" in {item["command"] for item in document["commands"]}


def test_the_cli_health_matches_the_module(tmp_path):
    ws = _one(tmp_path)
    completed = _cli("surface", "health", "--workspace", str(ws.root), "--json")
    assert completed.returncode == 0, completed.stderr
    from_cli = json.loads(completed.stdout)["health"]
    from_module = surface.health(ws)["health"]
    assert from_cli["state"] == from_module["state"]
    assert from_cli["unknown"] == from_module["unknown"]
    assert {row["section"]: row["state"]
            for row in from_cli["sections"]} == {row["section"]: row["state"]
                                                 for row in from_module["sections"]}


def test_the_cli_reports_unknown_without_a_failure_exit(tmp_path):
    """UNKNOWN is a verdict, not a crash, and the exit code says so.

    Failing here would train every caller to retry an unfixable read and then
    ignore the word that was trying to reach them.
    """
    ws = _one(tmp_path)
    _corrupt_ledger(ws, "broken")
    completed = _cli("surface", "health", "--workspace", str(ws.root), "--json")
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["health"]["state"] == surface.UNKNOWN


def test_the_cli_feed_surfaces_a_gap(tmp_path):
    ws = _one(tmp_path)
    for index in range(4):
        _note(ws, ledger.DELIVERY_ATTEMPTED, f"m{index}")
    _trim_ledger(ws, keep=1)
    completed = _cli("surface", "feed", "--workspace", str(ws.root), "--cursor",
                     "0", "--json")
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["gap"] is True
    assert payload["status"] == surface.GAP


def test_the_cli_needs_a_workspace_for_the_stateful_verbs(tmp_path):
    """`map` and `schema` need no mailbox; `health` and `feed` do."""
    assert _cli("surface", "map").returncode == 0
    assert _cli("surface", "schema").returncode == 0
    assert _cli("surface", "health").returncode != 0
    assert _cli("surface", "feed").returncode != 0


def test_health_on_a_directory_that_is_not_a_workspace_is_refused(tmp_path):
    """A refusal stays a refusal; it does not become a dashboard of zeros."""
    bogus = tmp_path / "not-a-workspace"
    bogus.mkdir()
    assert _code(workspace.load_workspace, bogus) != "NO_ERROR"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
