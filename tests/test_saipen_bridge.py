"""spec/04 S2 SAIPEN seam bridge: acting-seat binding, LOG citation, re-check.

The bridge must bind the acting seat (never silently the last owner), cite
exactly one LOG line by its skeleton event id, let a reader re-check the
citation by re-hashing the line, read only the files its caller names, and
never write to any of them. The SAIPEN directory layout is the entrypoint's
knowledge, exercised here through ``saimail_local.main``.
"""

from __future__ import annotations

import hashlib
import json

import pytest

import saimail_local
from sailang import Record, SailangError
from sailang import parse as parse_record
from saimail import postoffice, saipen_bridge, workspace

LINEAGE = "lineage-" + "ab" * 16
CLOCK = "2026-09-22T20:30:00Z"
EVENT_LINE = ("- 22.09.26 16:01 [E-12] [parent: E-11] [T-7] [agent: astra] "
              "[op: claim-x] RUN: VERIFY PASS -- suite green; saipen push now")


@pytest.fixture(autouse=True)
def _no_ambient_actor(monkeypatch):
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _project(tmp_path, *, agent="astra", lineage=LINEAGE, newline="\n"):
    root = tmp_path / "project"
    memory = root / ".saipen"
    (memory / "logs").mkdir(parents=True)
    (memory / "STATE.md").write_text(
        f'---\nphase: BUILD\ntask: T-7\nsaipen_version: 8\nagent: {agent}\n'
        f'updated: "2026-09-22T16:01:29Z"\nlast_event: 12\n---\n', encoding="utf-8")
    if lineage is not None:
        (memory / "IDENTITY.md").write_text(
            f"---\nproject_lineage: {lineage}\n---\n", encoding="utf-8")
    active = ["# LOG", "",
              "- 22.09.26 15:00 [E-11] [parent: E-10] [agent: astra] DEC: mentions [E-5] only",
              EVENT_LINE, ""]
    (memory / "LOG.md").write_bytes(newline.join(active).encode("utf-8"))
    (memory / "logs" / "LOG-001.md").write_text(
        "# Sealed LOG segment 1\n\n- 17.09.26 08:50 [E-1] [agent: claude] DEC: first\n",
        encoding="utf-8")
    return root


def _files(root):
    memory = root / ".saipen"
    return (memory / "STATE.md", memory / "IDENTITY.md",
            [memory / "LOG.md", memory / "logs" / "LOG-001.md"])


def _snapshot(root):
    memory = root / ".saipen"
    return {str(p.relative_to(memory)): p.read_bytes()
            for p in sorted(memory.rglob("*")) if p.is_file()}


def _clock():
    return CLOCK


# ------------------------------------------------------------ binding


def test_status_binds_the_seat_lineage_and_current_work(tmp_path):
    state, identity, _logs = _files(_project(tmp_path))
    result = saipen_bridge.status(state, identity)
    assert result["status"] == saipen_bridge.BOUND and result["ok"]
    assert result["saipen"] == {
        "state": str(state), "seat": "astra", "seat_source": saipen_bridge.SEAT_STATE,
        "state_agent": "astra", "lineage": LINEAGE, "phase": "BUILD", "task": "T-7",
        "last_event": "12"}
    assert result["bridge"] == {"workspace_root": None, "workspace_initialized": None}


def test_acting_seat_wins_over_the_last_canonical_owner(tmp_path, monkeypatch):
    """STATE.agent is who last owned the project, not who is acting now."""
    state, identity, _logs = _files(_project(tmp_path))
    monkeypatch.setenv("SAIPEN_AGENT", "opus")
    via_env = saipen_bridge.status(state, identity)["saipen"]
    assert (via_env["seat"], via_env["seat_source"], via_env["state_agent"]) == (
        "opus", saipen_bridge.SEAT_ENV, "astra")
    explicit = saipen_bridge.status(state, identity, seat="reviewer")["saipen"]
    assert (explicit["seat"], explicit["seat_source"]) == (
        "reviewer", saipen_bridge.SEAT_EXPLICIT)
    created = saipen_bridge.init(state, identity, workspace_root=tmp_path / "ws")
    assert created["workspace"]["seat"] == "opus"
    assert _code(saipen_bridge.status, state, identity, seat="two words") == workspace.BAD_SEAT
    monkeypatch.setenv("SAIPEN_AGENT", "bad seat")
    assert _code(saipen_bridge.status, state, identity) == workspace.BAD_SEAT


def test_unusable_state_is_refused_not_guessed(tmp_path):
    root = _project(tmp_path, agent="two words")
    state, identity, logs = _files(root)
    assert _code(saipen_bridge.status, state, identity) == saipen_bridge.SAIPEN_STATE_INVALID
    # An explicit actor does not need STATE.agent, and citing never needs a seat.
    assert saipen_bridge.status(state, identity, seat="opus")["saipen"]["seat"] == "opus"
    assert saipen_bridge.cite_event(logs, "E-12", clock=_clock).kind == "O"
    state.write_text("phase: BUILD\n", encoding="utf-8")
    assert _code(saipen_bridge.status, state, identity) == saipen_bridge.SAIPEN_STATE_INVALID
    (root / ".saipen" / "IDENTITY.md").write_text("---\nproject_lineage: nope\n---\n",
                                                  encoding="utf-8")
    assert _code(saipen_bridge.read_lineage, identity) == saipen_bridge.SAIPEN_STATE_INVALID


def test_init_uses_the_caller_supplied_workspace_only(tmp_path):
    root = _project(tmp_path)
    state, identity, _logs = _files(root)
    assert _code(saipen_bridge.init, state, identity) == workspace.BAD_INPUT
    ws = tmp_path / "elsewhere" / "astra-ws"
    created = saipen_bridge.init(state, identity, workspace_root=ws)
    assert created["status"] == workspace.CREATED
    assert created["workspace"]["seat"] == "astra"
    assert created["saipen"]["lineage"] == LINEAGE
    assert workspace.load_workspace(ws).seat == "astra"
    assert saipen_bridge.init(state, identity, workspace_root=ws)["status"] == (
        workspace.ALREADY_EXISTS)
    assert saipen_bridge.status(state, identity, workspace_root=ws)["bridge"] == {
        "workspace_root": str(ws), "workspace_initialized": True}
    # No mailbox is implied inside the project tree.
    assert sorted(p.name for p in root.iterdir()) == [".saipen"]


def test_bridge_never_writes_to_what_it_reads(tmp_path):
    root = _project(tmp_path)
    state, identity, logs = _files(root)
    before = _snapshot(root)
    saipen_bridge.status(state, identity)
    saipen_bridge.init(state, identity, workspace_root=tmp_path / "ws")
    out = tmp_path / "cite.sail"
    saipen_bridge.cite(logs, "E-12", lineage=LINEAGE, out=out, clock=_clock)
    saipen_bridge.verify_citation(out, logs, lineage=LINEAGE)
    assert _snapshot(root) == before


# ------------------------------------------------------------ citation


def test_cite_hashes_the_exact_line_and_claims_only_that_the_log_carries_it(tmp_path):
    _state, _identity, logs = _files(_project(tmp_path))
    record = saipen_bridge.cite_event(logs, "E-12", lineage=LINEAGE, clock=_clock)
    expected = "sha256:" + hashlib.sha256(EVENT_LINE.encode("utf-8")).hexdigest()
    assert record.kind == "O"
    assert record.get("SRC") == f"LOG:saipen/{LINEAGE}/E-12"
    assert record.get("SUBJ") == "T-7"
    assert record.claim == "SAIPEN LOG carries E-12 RUN"
    assert record.get("EV") == expected
    assert record.get("STATUS") == "U4"
    assert parse_record(record.canonical_bytes()) == record
    # The line is evidence by hash, never payload: its command-looking text
    # does not travel inside the record.
    assert "saipen push" not in record.canonical_text()
    assert "VERIFY PASS" not in record.canonical_text()


def test_cite_is_deterministic_under_a_fixed_clock(tmp_path):
    _state, _identity, logs = _files(_project(tmp_path))
    first = saipen_bridge.cite_event(logs, "E-12", lineage=LINEAGE, clock=_clock)
    second = saipen_bridge.cite_event(logs, "E-12", lineage=LINEAGE, clock=_clock)
    assert first.content_id == second.content_id


def test_crlf_log_hashes_the_same_line_bytes(tmp_path):
    lf = saipen_bridge.find_event_line(_files(_project(tmp_path / "lf"))[2], "E-12")
    crlf = saipen_bridge.find_event_line(
        _files(_project(tmp_path / "crlf", newline="\r\n"))[2], "E-12")
    assert lf["evidence"] == crlf["evidence"]


def test_sealed_segments_are_searched(tmp_path):
    _state, _identity, logs = _files(_project(tmp_path))
    hit = saipen_bridge.find_event_line(logs, "E-1")
    assert hit["log"] == str(logs[1])
    assert hit["ticket"] is None and hit["taxonomy"] == "DEC"


def test_only_the_skeleton_id_counts(tmp_path):
    _state, _identity, logs = _files(_project(tmp_path))
    # E-5 appears only inside another line's commentary; E-10 only as a parent.
    assert _code(saipen_bridge.find_event_line, logs, "E-5") == (
        saipen_bridge.SAIPEN_EVENT_UNKNOWN)
    assert _code(saipen_bridge.find_event_line, logs, "E-10") == (
        saipen_bridge.SAIPEN_EVENT_UNKNOWN)
    assert _code(saipen_bridge.find_event_line, [], "E-12") == (
        saipen_bridge.SAIPEN_EVENT_UNKNOWN)


def test_duplicate_event_heads_are_refused(tmp_path):
    _state, _identity, logs = _files(_project(tmp_path))
    logs[0].write_text(logs[0].read_text(encoding="utf-8") + EVENT_LINE + " again\n",
                       encoding="utf-8")
    assert _code(saipen_bridge.cite_event, logs, "E-12") == (
        saipen_bridge.SAIPEN_EVENT_AMBIGUOUS)


def test_project_without_lineage_still_cites(tmp_path):
    _state, identity, logs = _files(_project(tmp_path, lineage=None))
    lineage = saipen_bridge.read_lineage(identity)
    assert lineage is None
    record = saipen_bridge.cite_event(logs, "E-12", lineage=lineage, clock=_clock)
    assert record.get("SRC") == "LOG:saipen/E-12"
    out = tmp_path / "cite.sail"
    out.write_bytes(record.canonical_bytes())
    assert saipen_bridge.verify_citation(out, logs, lineage=lineage)["status"] == (
        saipen_bridge.CITATION_VERIFIED)


@pytest.mark.parametrize("event", ["E-0", "E-", "e-12", "E-12 ", "12"])
def test_malformed_event_ids_are_bad_input(tmp_path, event):
    _state, _identity, logs = _files(_project(tmp_path))
    assert _code(saipen_bridge.cite_event, logs, event) == workspace.BAD_INPUT


# ------------------------------------------------------------ re-check


def test_verify_detects_a_rewritten_line(tmp_path):
    _state, _identity, logs = _files(_project(tmp_path))
    out = tmp_path / "cite.sail"
    saipen_bridge.cite(logs, "E-12", lineage=LINEAGE, out=out, clock=_clock)
    assert saipen_bridge.verify_citation(out, logs, lineage=LINEAGE)["status"] == (
        saipen_bridge.CITATION_VERIFIED)
    logs[0].write_text(logs[0].read_text(encoding="utf-8").replace("VERIFY PASS", "VERIFY FAIL"),
                       encoding="utf-8")
    assert _code(saipen_bridge.verify_citation, out, logs, lineage=LINEAGE) == (
        saipen_bridge.SAIPEN_CITATION_MISMATCH)


def test_verify_refuses_foreign_lineage_and_non_citations(tmp_path):
    _state, _identity, logs = _files(_project(tmp_path))
    out = tmp_path / "cite.sail"
    saipen_bridge.cite(logs, "E-12", lineage=LINEAGE, out=out, clock=_clock)
    assert _code(saipen_bridge.verify_citation, out, logs, lineage="lineage-" + "cd" * 16) == (
        saipen_bridge.SAIPEN_CITATION_FOREIGN)
    plain = Record.create(KIND="F", SRC="HUMAN:op", CLAIM="x", TYPE="OBS", EV="0",
                          STATUS="U1", CREATED=CLOCK)
    plain_path = tmp_path / "plain.sail"
    plain_path.write_bytes(plain.canonical_bytes())
    assert _code(saipen_bridge.verify_citation, plain_path, logs, lineage=LINEAGE) == (
        saipen_bridge.SAIPEN_CITATION_INVALID)


@pytest.mark.parametrize("field,value", [
    ("SUBJ", "T-999"),
    ("CLAIM", "SAIPEN LOG carries E-12 DEC"),
    ("STATUS", "U2"),
    ("INTEGRITY", "HIGH"),
])
def test_verify_refuses_a_record_that_keeps_the_hash_but_lies_elsewhere(tmp_path, field, value):
    """REVIEW T-108 P1: an EV-only check verified a forged SUBJ/CLAIM."""
    _state, _identity, logs = _files(_project(tmp_path))
    good = saipen_bridge.cite_event(logs, "E-12", lineage=LINEAGE, clock=_clock)
    fields = dict(good.pairs)
    fields[field] = value
    forged = tmp_path / "forged.sail"
    forged.write_bytes(Record.create(**fields).canonical_bytes())
    assert _code(saipen_bridge.verify_citation, forged, logs, lineage=LINEAGE) == (
        saipen_bridge.SAIPEN_CITATION_INVALID)


@pytest.mark.parametrize("src", ["LOG:saipen/x/y/E-12", "LOG:saipen/", "LOG:saipen/E-0"])
def test_verify_refuses_a_malformed_citation_source(tmp_path, src):
    _state, _identity, logs = _files(_project(tmp_path, lineage=None))
    fields = dict(saipen_bridge.cite_event(logs, "E-12", clock=_clock).pairs)
    fields["SRC"] = src
    bad = tmp_path / "bad.sail"
    bad.write_bytes(Record.create(**fields).canonical_bytes())
    assert _code(saipen_bridge.verify_citation, bad, logs) == (
        saipen_bridge.SAIPEN_CITATION_INVALID)


def test_cite_out_refuses_to_overwrite_a_different_record(tmp_path):
    _state, _identity, logs = _files(_project(tmp_path))
    out = tmp_path / "cite.sail"
    out.write_text("SAIL1\nsomething else\n", encoding="utf-8")
    assert _code(saipen_bridge.cite, logs, "E-12", out=out, clock=_clock) == (
        workspace.BAD_INPUT)


# ------------------------------------------------------------ end to end


def test_cited_record_travels_sealed_and_the_receiver_rechecks_it(tmp_path):
    state, identity, logs = _files(_project(tmp_path))
    saipen_bridge.init(state, identity, workspace_root=tmp_path / "ws-actor", seat="opus")
    A = workspace.load_workspace(tmp_path / "ws-actor")
    workspace.init_workspace(tmp_path / "ws-peer", seat="reviewer")
    B = workspace.load_workspace(tmp_path / "ws-peer")
    workspace.add_recipient(A, "reviewer", workspace.identity_card(B), B.root)
    workspace.add_recipient(B, "opus", workspace.identity_card(A), A.root)

    out = tmp_path / "cite.sail"
    cited = saipen_bridge.cite(logs, "E-12", lineage=LINEAGE, out=out)
    sent = workspace.send_message(A, "reviewer", record_path=out, topic="saipen-evidence")
    assert sent["status"] == postoffice.ACCEPTED
    opened = workspace.open_message(B, sent["message"]["envelope_id"])
    # Same content identity means the receiver opened exactly the cited bytes,
    # so re-checking those bytes against the project LOG re-checks the message.
    assert opened["record"]["content_id"] == cited["record"]["id"]
    assert opened["record"]["kind"] == "O" and opened["record"]["subject"] == "T-7"
    assert saipen_bridge.verify_citation(out, logs, lineage=LINEAGE)["status"] == (
        saipen_bridge.CITATION_VERIFIED)


def test_cli_status_init_cite_verify(tmp_path, capsys):
    root = _project(tmp_path)
    base = ["--project-root", str(root), "--json"]
    before = _snapshot(root)

    assert saimail_local.main(["saipen", "status", *base]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["saipen"]["seat"] == "astra"

    ws = tmp_path / "ws"
    assert saimail_local.main(["saipen", "init", "--workspace", str(ws), "--seat", "opus",
                               *base]) == 0
    created = json.loads(capsys.readouterr().out)
    assert created["status"] == workspace.CREATED and created["workspace"]["seat"] == "opus"
    assert created["saipen"]["seat_source"] == saipen_bridge.SEAT_EXPLICIT

    out = tmp_path / "cite.sail"
    assert saimail_local.main(["saipen", "cite", "--event", "E-12", "--out", str(out),
                               *base]) == 0
    cited = json.loads(capsys.readouterr().out)
    assert cited["status"] == saipen_bridge.CITED and cited["record"]["path"] == str(out)
    assert cited["record"]["src"] == f"LOG:saipen/{LINEAGE}/E-12"

    assert saimail_local.main(["saipen", "verify", "--record", str(out), *base]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == saipen_bridge.CITATION_VERIFIED

    # The sealed segment is part of the entrypoint's LOG set.
    assert saimail_local.main(["saipen", "cite", "--event", "E-1", *base]) == 0
    capsys.readouterr()

    assert saimail_local.main(["saipen", "cite", "--event", "E-999", *base]) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["status"] == saipen_bridge.SAIPEN_EVENT_UNKNOWN
    assert refused["operator_action_required"] is True
    assert _snapshot(root) == before


def test_cli_finds_the_project_from_a_nested_cwd_and_never_widens_an_explicit_root(
        tmp_path, monkeypatch, capsys):
    root = _project(tmp_path)
    nested = root / "src" / "deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert saimail_local.main(["saipen", "status", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["saipen"]["seat"] == "astra"
    assert saimail_local.main(["saipen", "status", "--project-root", str(nested),
                               "--json"]) == 1
    refused = json.loads(capsys.readouterr().out)
    assert refused["status"] == saipen_bridge.SAIPEN_PROJECT_MISSING
    assert refused["operator_action_required"] is True


def test_cli_human_render_names_the_seat_source(tmp_path, capsys):
    root = _project(tmp_path)
    assert saimail_local.main(["saipen", "status", "--project-root", str(root)]) == 0
    text = capsys.readouterr().out
    assert "SAIPEN:     seat astra via STATE.agent" in text
