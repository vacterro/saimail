"""P1 multi-invocation acceptance: bounded metadata inbox query over the CLI.

Every step runs as its own ``python -m saimail_local`` process, so the
persistence/restart boundary is real. The flow initializes two workspaces,
exchanges cards, sends four messages with varied metadata, opens exactly one
message, then queries all / unread / read / sender / topic / time range /
continuation cursor and proves the other messages never changed state, that a
repeat invocation returns the identical metadata result, and that the legacy
unfiltered listing is byte-for-byte unchanged in behaviour.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from saimail import postoffice, workspace

ROOT = Path(__file__).resolve().parent.parent
MARKER = "p1 acceptance private marker 9f2c"


def _run(args, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "saimail_local", *args],
                          cwd=cwd, capture_output=True, text=True, check=False)


def _payload(completed) -> dict:
    assert completed.returncode in (0, 1), completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def _ids(result: dict) -> set:
    return {item["envelope_id"] for item in result["items"]}


def _setup(tmp_path) -> dict:
    a_root = tmp_path / "ws-a"
    b_root = tmp_path / "ws-b"
    card_a = tmp_path / "card-a.json"
    card_b = tmp_path / "card-b.json"
    assert _payload(_run(["init", "--workspace", str(a_root), "--seat", "SAIMAIL-A",
                          "--json"]))["status"] == workspace.CREATED
    assert _payload(_run(["init", "--workspace", str(b_root), "--seat", "SAIMAIL-B",
                          "--json"]))["status"] == workspace.CREATED
    _run(["identity", "--workspace", str(a_root), "--export-card", str(card_a), "--json"])
    _run(["identity", "--workspace", str(b_root), "--export-card", str(card_b), "--json"])
    _run(["recipient", "add", "--workspace", str(a_root), "--alias", "bob",
          "--card", str(card_b), "--peer-workspace", str(b_root), "--json"])
    _run(["recipient", "add", "--workspace", str(b_root), "--alias", "alice",
          "--card", str(card_a), "--peer-workspace", str(a_root), "--json"])
    return {"a": a_root, "b": b_root, "card_a": card_a, "card_b": card_b}


def test_cli_query_filters_cursor_restart_and_state_invariance(tmp_path):
    ws = _setup(tmp_path)
    sends = [
        ("t1", "PERSONAL_MESSAGE", "first message " + MARKER),
        ("t1", "WARNING", "second message " + MARKER),
        ("t2", "PERSONAL_MESSAGE", "third message " + MARKER),
        ("t3", "DISCOVERY", "fourth message " + MARKER),
    ]
    envelopes = []
    for topic, kind, claim in sends:
        sent = _payload(_run(["send", "--workspace", str(ws["a"]), "--to", "bob",
                              "--claim", claim, "--topic", topic, "--kind", kind,
                              "--json"]))
        assert sent["status"] == "ACCEPTED", sent
        envelopes.append(sent["message"])

    # one deliberate explicit open constructs the READ fixture
    opened = _payload(_run(["open", "--workspace", str(ws["b"]), "--envelope",
                            envelopes[1]["envelope_id"], "--json"]))
    assert opened["status"] == "READ" and opened["record"]["claim"] == sends[1][2]

    legacy_before = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--json"]))
    assert legacy_before["command"] == "inbox" and legacy_before["status"] == "OK"
    assert len(legacy_before["items"]) == 4
    assert {item["envelope_id"] for item in legacy_before["items"]} == {
        m["envelope_id"] for m in envelopes}

    # state filters
    unread = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--state", "UNREAD",
                            "--json"]))
    assert unread["command"] == "inbox-query"
    assert _ids(unread) == {envelopes[0]["envelope_id"], envelopes[2]["envelope_id"],
                            envelopes[3]["envelope_id"]}
    read = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--state", "READ",
                          "--json"]))
    assert _ids(read) == {envelopes[1]["envelope_id"]}

    # sender / topic / kind filters
    by_sender = _payload(_run(["inbox", "--workspace", str(ws["b"]),
                               "--from-seat", "SAIMAIL-A", "--json"]))
    assert _ids(by_sender) == {m["envelope_id"] for m in envelopes}
    by_topic = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--topic", "t1",
                              "--json"]))
    assert _ids(by_topic) == {envelopes[0]["envelope_id"], envelopes[1]["envelope_id"]}
    by_kind = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--kind", "WARNING",
                             "--json"]))
    assert _ids(by_kind) == {envelopes[1]["envelope_id"]}

    # combined filters are AND, never OR
    combined = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--topic", "t1",
                              "--state", "READ", "--json"]))
    assert _ids(combined) == {envelopes[1]["envelope_id"]}

    # half-open receiver-receipt time bounds (tie-safe: computed from real times)
    since = envelopes[1]["received_at"]
    before = envelopes[3]["received_at"]
    window = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--since", since,
                            "--before", before, "--json"]))
    expected_window = {m["envelope_id"] for m in envelopes
                       if since <= m["received_at"] < before}
    assert _ids(window) == expected_window

    # bounded pagination with a continuation cursor
    page1 = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--scan-budget", "2",
                           "--json"]))
    assert page1["rows_examined"] == 2 and len(page1["items"]) == 2
    assert page1["exhausted"] is True and isinstance(page1["cursor"], int)
    page2 = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--scan-budget", "2",
                           "--cursor", str(page1["cursor"]), "--json"]))
    assert page2["rows_examined"] == 2
    assert _ids(page1).isdisjoint(_ids(page2))
    assert _ids(page1) | _ids(page2) == {m["envelope_id"] for m in envelopes}

    # no query mutated any durable state: the legacy listing is identical
    legacy_after = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--json"]))
    assert legacy_after == legacy_before

    # a fresh invocation repeats the same query with an identical result
    repeat = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--topic", "t1",
                            "--json"]))
    assert repeat == by_topic

    # privacy: no private key material and no plaintext claim in query output
    identity = json.loads(
        (ws["a"] / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME).read_text("utf-8"))
    for result in (unread, read, by_sender, by_topic, by_kind, combined, window,
                   page1, page2, repeat):
        blob = json.dumps(result)
        assert identity["sender_private_key"] not in blob
        assert identity["recipient_private_key"] not in blob
        assert MARKER not in blob
        assert result["network_attempts"] == 0

    # every stored payload is still sealed: the marker is not on disk in clear
    needle = MARKER.encode("utf-8")
    for path in sorted(ws["b"].rglob("*")):
        if path.is_file():
            assert needle not in path.read_bytes(), path


def test_cli_query_refuses_bad_cursor_and_bad_state(tmp_path):
    ws = _setup(tmp_path)
    _run(["send", "--workspace", str(ws["a"]), "--to", "bob", "--claim", "one",
          "--json"])
    negative = _payload(_run(["inbox", "--workspace", str(ws["b"]), "--cursor", "-1",
                              "--json"]))
    assert negative["status"] == postoffice.BAD_CURSOR
    assert negative["ok"] is False
    # argparse keeps the state domain closed and exits 2 on an unknown value
    invalid = _run(["inbox", "--workspace", str(ws["b"]), "--state", "BOTH", "--json"])
    assert invalid.returncode == 2
