"""V4-01 multi-invocation acceptance: local correspondence continuation.

Every step runs as its own ``python -m saimail_local`` process, so the restart
boundary is real. The flow reproduces Milestone 17 of the V4-01 contract:
initialize two workspaces, exchange cards, register both peers, A sends an
original message, B is refused a reply before opening, B opens explicitly, a new
process reloads B and replies, the reply carries ``REF`` = original
``ENVELOPE_ID``, A discovers it through the bounded metadata-only
``inbox --ref`` query without opening it, A opens and continues the chain, B
discovers the continuation, exact redelivery stays ``DUPLICATE``, and the
correspondence metadata is unchanged across restarts.

Zero network/model calls.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from saimail import envelope, postoffice, workspace

ROOT = Path(__file__).resolve().parent.parent
MARKER = "v4-01 acceptance private marker 4d8e"


def _run(args, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "saimail_local", *args],
                          cwd=cwd, capture_output=True, text=True, check=False)


def _payload(completed) -> dict:
    assert completed.returncode in (0, 1), completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def _ids(result: dict) -> set:
    return {item["envelope_id"] for item in result["items"]}


def _outbox_header(root: Path, envelope_id: str):
    digest = envelope_id.split(":", 1)[1]
    container = (root / workspace.OUTBOX_DIR / (digest + ".senv")).read_text("utf-8")
    return envelope.parse_header(container)


def test_cli_correspondence_continuation_restart_acceptance(tmp_path):
    a_root = tmp_path / "ws-a"
    b_root = tmp_path / "ws-b"
    card_a = tmp_path / "card-a.json"
    card_b = tmp_path / "card-b.json"

    # 1-3: initialize, exchange cards, register each peer.
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

    # 4-5: A sends the original; record ENVELOPE_ID X.
    original = "original " + MARKER
    sent = _payload(_run(["send", "--workspace", str(a_root), "--to", "bob",
                          "--claim", original, "--topic", "correspondence", "--json"]))
    assert sent["status"] == "ACCEPTED", sent
    x = sent["message"]["envelope_id"]

    # 6: B sees X UNREAD.
    inbox = _payload(_run(["inbox", "--workspace", str(b_root), "--json"]))
    assert len(inbox["items"]) == 1 and inbox["items"][0]["state"] == postoffice.UNREAD

    # 7-8: a reply before an explicit open is refused and X stays UNREAD.
    refused = _payload(_run(["reply", "--workspace", str(b_root), "--envelope", x,
                             "--claim", "too early", "--json"]))
    assert refused["status"] == workspace.REPLY_TARGET_UNREAD
    assert refused["ok"] is False
    still = _payload(_run(["inbox", "--workspace", str(b_root), "--state", "UNREAD",
                           "--json"]))
    assert _ids(still) == {x}

    # 9-11: B opens X explicitly; the process exits and a new one reloads B.
    opened = _payload(_run(["open", "--workspace", str(b_root), "--envelope", x, "--json"]))
    assert opened["status"] == "READ" and opened["record"]["claim"] == original

    # 12-13: B replies in a fresh process; Y carries REF = X.
    replied = _payload(_run(["reply", "--workspace", str(b_root), "--envelope", x,
                             "--claim", "continuation " + MARKER, "--json"]))
    assert replied["status"] == "ACCEPTED", replied
    assert replied["target"]["envelope_id"] == x
    assert replied["target"]["from"] == "SAIMAIL-A"
    y = replied["reply"]["envelope_id"]
    assert replied["reply"]["ref"] == x
    assert replied["reply"]["topic"] == "correspondence"   # inherited
    assert replied["reply"]["kind"] == "PERSONAL_MESSAGE"
    assert _outbox_header(b_root, y).get("REF") == x

    # 14-15: A discovers Y through the bounded, metadata-only --ref query, and
    # the query does not open Y (Y is still UNREAD afterwards).
    discovered = _payload(_run(["inbox", "--workspace", str(a_root), "--ref", x, "--json"]))
    assert discovered["command"] == "inbox-query"
    assert _ids(discovered) == {y}
    assert discovered["items"][0]["ref"] == x
    assert discovered["items"][0]["state"] == postoffice.UNREAD
    assert MARKER not in json.dumps(discovered)
    after_query = _payload(_run(["inbox", "--workspace", str(a_root), "--state", "UNREAD",
                                 "--json"]))
    assert _ids(after_query) == {y}

    # 16-19: A opens Y and continues the chain; Z carries REF = Y and B finds Z.
    opened_y = _payload(_run(["open", "--workspace", str(a_root), "--envelope", y, "--json"]))
    assert opened_y["status"] == "READ"
    chained = _payload(_run(["reply", "--workspace", str(a_root), "--envelope", y,
                             "--claim", "reply to reply " + MARKER, "--json"]))
    assert chained["status"] == "ACCEPTED", chained
    z = chained["reply"]["envelope_id"]
    assert chained["reply"]["ref"] == y
    assert _outbox_header(a_root, z).get("REF") == y
    found_z = _payload(_run(["inbox", "--workspace", str(b_root), "--ref", y, "--json"]))
    assert _ids(found_z) == {z}

    # 20: exact redelivery of Y remains a canonical DUPLICATE.
    replay = _payload(_run(["send", "--workspace", str(b_root), "--redeliver", y, "--json"]))
    assert replay["status"] == postoffice.DUPLICATE
    assert replay["message"]["received_at"] == replied["reply"]["created"]

    # 21-22: restart both workspaces; the correspondence metadata is identical
    # (the ref link and envelope identities never change; A's own explicit open
    # of Y moved only Y's durable state UNREAD -> READ, which is not
    # correspondence metadata).
    re_a = _payload(_run(["inbox", "--workspace", str(a_root), "--ref", x, "--json"]))
    re_b = _payload(_run(["inbox", "--workspace", str(b_root), "--ref", y, "--json"]))
    assert re_a["query"] == discovered["query"]
    assert re_a["items"][0]["envelope_id"] == y and re_a["items"][0]["ref"] == x
    assert re_a["items"][0]["state"] == postoffice.READ_STATE
    assert re_b == found_z

    # privacy: no private key material and no plaintext claim in any non-open
    # result. The explicit `open` is the ONE surface that returns the opened
    # record it read; nothing else may leak the claim.
    identity = json.loads(
        (a_root / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME).read_text("utf-8"))
    for result in (sent, inbox, refused, opened, replied, discovered, after_query,
                   opened_y, chained, found_z, replay, re_a, re_b):
        blob = json.dumps(result)
        assert identity["sender_private_key"] not in blob
        assert identity["recipient_private_key"] not in blob
        assert result["network_attempts"] == 0
    for result in (sent, inbox, refused, replied, discovered, after_query, chained,
                   found_z, replay, re_a, re_b):
        assert MARKER not in json.dumps(result)
    assert opened["record"]["claim"] == original
    assert opened_y["record"]["claim"] == "continuation " + MARKER

    # every stored payload is still sealed: the marker never sits in clear.
    needle = MARKER.encode("utf-8")
    for root in (a_root, b_root):
        for path in sorted(root.rglob("*")):
            if path.is_file():
                assert needle not in path.read_bytes(), path


def test_cli_reply_refuses_unknown_target(tmp_path):
    a_root = tmp_path / "ws-a"
    _run(["init", "--workspace", str(a_root), "--seat", "SAIMAIL-A", "--json"])
    unknown = _payload(_run(["reply", "--workspace", str(a_root), "--envelope",
                             "sha256:" + "0" * 64, "--claim", "x", "--json"]))
    assert unknown["status"] == workspace.REPLY_TARGET_UNKNOWN

    neither = _run(["reply", "--workspace", str(a_root), "--envelope",
                    "sha256:" + "0" * 64, "--json"])
    assert neither.returncode == 1
    assert json.loads(neither.stdout)["status"] == workspace.BAD_INPUT
