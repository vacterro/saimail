"""V2-01 focused acceptance: persistent local workspace, identity, recipient
mapping, send/list/open across restarts, dedup, error UX, privacy, no network.

Areas A-J of the V2-01 contract (spec/17-LOCAL-WORKSPACE-v0.md). The engine is
exercised directly for state proof and through ``python -m saimail_local`` for
the multi-invocation and packaging surfaces.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sailang import SailangError
from saimail import envelope, postoffice, workspace

ROOT = Path(__file__).resolve().parent.parent
MARKER = "v2-01 synthetic private marker 5e9b"


def _run(args, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "saimail_local", *args],
                          cwd=cwd, capture_output=True, text=True, check=False)


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _init_pair(tmp_path) -> tuple[workspace.Workspace, workspace.Workspace, Path, Path]:
    a_root = tmp_path / "ws-a"
    b_root = tmp_path / "ws-b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    return (workspace.load_workspace(a_root), workspace.load_workspace(b_root),
            a_root, b_root)


def _link(A: workspace.Workspace, B: workspace.Workspace, tmp_path) -> None:
    card_a = workspace.identity_card(A)
    card_b = workspace.identity_card(B)
    workspace.add_recipient(A, "bob", card_b, B.root)
    workspace.add_recipient(B, "alice", card_a, A.root)


# ---------------------------------------------------------------- A. init


def test_init_creates_and_reopen_is_idempotent(tmp_path):
    root = tmp_path / "ws"
    created = workspace.init_workspace(root, seat="SAIMAIL-A")
    assert created["status"] == workspace.CREATED
    assert (root / workspace.MARKER_NAME).is_file()
    first = workspace.load_workspace(root)
    again = workspace.init_workspace(root, seat="SAIMAIL-A")
    assert again["status"] == workspace.ALREADY_EXISTS
    second = workspace.load_workspace(root)
    assert (first.sender_kid, first.recipient_kid) == (second.sender_kid, second.recipient_kid)


def test_init_refuses_foreign_nonempty_directory(tmp_path):
    root = tmp_path / "ws"
    root.mkdir()
    (root / "notes.txt").write_text("operator data", encoding="utf-8")
    assert _code(workspace.init_workspace, root, seat="SAIMAIL-A") == workspace.WORKSPACE_CONFLICT


def test_init_refuses_partial_workspace_without_marker(tmp_path):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    (root / workspace.MARKER_NAME).unlink()
    assert _code(workspace.init_workspace, root, seat="SAIMAIL-A") == workspace.WORKSPACE_CONFLICT


def test_missing_and_malformed_workspace_are_distinct(tmp_path):
    assert _code(workspace.load_workspace, tmp_path / "absent") == workspace.WORKSPACE_MISSING
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    (root / workspace.MARKER_NAME).write_text("{not json", encoding="utf-8")
    assert _code(workspace.load_workspace, root) == workspace.INVALID_WORKSPACE


def test_stale_marker_against_changed_identity_is_refused(tmp_path):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    identity_path = root / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME
    identity = json.loads(identity_path.read_text(encoding="utf-8"))
    identity["recipient_private_key"] = "ab" * 32
    identity_path.write_text(json.dumps(identity), encoding="utf-8")
    assert _code(workspace.load_workspace, root) == workspace.INVALID_WORKSPACE


# ------------------------------------------------------------ B. identity


def test_identity_is_stable_and_never_prints_private_keys(tmp_path):
    root = tmp_path / "ws"
    created = workspace.init_workspace(root, seat="SAIMAIL-A")
    private_hex = json.loads(
        (root / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME).read_text(encoding="utf-8"))
    assert private_hex["sender_private_key"] not in json.dumps(created)
    assert private_hex["recipient_private_key"] not in json.dumps(created)
    card = workspace.identity_card(workspace.load_workspace(root))
    assert card["schema"] == workspace.CARD_SCHEMA
    assert "private" not in json.dumps(card)
    reloaded = workspace.load_workspace(root)
    assert (card["sender_kid"], card["recipient_kid"]) == (
        reloaded.sender_kid, reloaded.recipient_kid)
    assert reloaded.identity["sender_public_key"] != private_hex["sender_private_key"]


def test_identity_card_export_is_idempotent_and_conflict_safe(tmp_path):
    A, _B, _a_root, _b_root = _init_pair(tmp_path)
    card_path = tmp_path / "card.json"
    first = workspace.export_identity_card(A, card_path)
    assert first["status"] == workspace.IDENTITY_CARD_EXPORTED
    same = workspace.export_identity_card(A, card_path)
    assert same["status"] == workspace.IDENTITY_CARD_EXPORTED
    card_path.write_text(json.dumps({"schema": "something-else"}), encoding="utf-8")
    assert _code(workspace.export_identity_card, A, card_path) == workspace.CARD_CONFLICT


# ----------------------------------------------------------- C. recipient


def test_recipient_add_persists_and_is_idempotent(tmp_path):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    card_b = workspace.identity_card(B)
    added = workspace.add_recipient(A, "bob", card_b, B.root)
    assert added["status"] == workspace.RECIPIENT_ADDED
    reloaded = workspace.load_workspace(A.root)
    assert reloaded.peers["bob"]["recipient_kid"] == B.recipient_kid
    again = workspace.add_recipient(reloaded, "bob", card_b, B.root)
    assert again["status"] == workspace.RECIPIENT_ALREADY_REGISTERED


def test_recipient_conflicts_refuse_without_overwrite(tmp_path):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    workspace.add_recipient(A, "bob", workspace.identity_card(B), B.root)
    C = tmp_path / "ws-c"
    workspace.init_workspace(C, seat="SAIMAIL-C")
    card_c = workspace.identity_card(workspace.load_workspace(C))
    assert _code(workspace.add_recipient, A, "bob", card_c, C) == workspace.RECIPIENT_CONFLICT
    assert _code(workspace.add_recipient, A, "bob", workspace.identity_card(B),
                 A.root) == workspace.RECIPIENT_IDENTITY_MISMATCH
    assert _code(workspace.add_recipient, A, "bad alias", workspace.identity_card(B),
                 B.root) == workspace.RECIPIENT_MALFORMED
    assert _code(workspace.add_recipient, A, "bob2", {"schema": 1}, B.root) == (
        workspace.RECIPIENT_MALFORMED)
    assert _code(workspace.add_recipient, A, "bob3", workspace.identity_card(B),
                 tmp_path / "absent") == workspace.DELIVERY_TARGET_UNAVAILABLE


def test_unknown_recipient_is_refused(tmp_path):
    A, _B, _a_root, _b_root = _init_pair(tmp_path)
    assert _code(workspace.send_message, A, "nobody", claim="hello") == workspace.RECIPIENT_UNKNOWN


# ---------------------------------------------------------------- D. send


def test_send_uses_the_production_seal_and_deliver_path(tmp_path, monkeypatch):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    calls = {"seal": 0}
    original = envelope.seal

    def counting(*args, **kwargs):
        calls["seal"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(workspace.envelope, "seal", counting)
    sent = workspace.send_message(A, "bob", claim="queue-lease note " + MARKER)
    assert sent["status"] == postoffice.ACCEPTED
    assert calls["seal"] == 1
    envelope_id = sent["message"]["envelope_id"]
    B_office = B.office()
    assert B_office.has_index_row(envelope_id)
    assert B_office.bundle_state(envelope_id) == postoffice.UNREAD
    outbox = workspace._outbox_path(A, envelope_id)
    container = outbox.read_text(encoding="utf-8")
    assert container.startswith(envelope.FORMAT_VERSION)
    verified = envelope.verify(envelope.parse_header(container),
                               B_office.sender_registry)
    assert verified.header.get("K") == workspace.DEFAULT_KIND


def test_delivery_from_unregistered_sender_is_quarantined(tmp_path):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    workspace.add_recipient(A, "bob", workspace.identity_card(B), B.root)
    sent = workspace.send_message(A, "bob", claim="unregistered sender")
    assert sent["status"] == postoffice.QUARANTINED
    assert sent["delivery"]["reason"] == "UNKNOWN_SENDER_KEY"


def test_send_with_a_canonical_record_file(tmp_path):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    from sailang import Record

    record = Record.create(KIND="F", SRC="HUMAN:operator", SUBJ="review-note",
                           CLAIM="canonical record payload", TYPE="OBS", EV="0",
                           STATUS="U1", CREATED=postoffice.utc_now())
    record_path = tmp_path / "message.sailang"
    record_path.write_text(record.canonical_text(), encoding="utf-8")
    sent = workspace.send_message(A, "bob", record_path=record_path)
    assert sent["status"] == postoffice.ACCEPTED
    opened = workspace.open_message(B, sent["message"]["envelope_id"])
    assert opened["record"]["claim"] == "canonical record payload"
    assert opened["record"]["content_id"] == record.content_id


# ---------------------------------------------------------------- E. list


def test_inbox_is_metadata_only_and_survives_reload(tmp_path):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    sent = workspace.send_message(A, "bob", claim="list proof " + MARKER)
    reloaded = workspace.load_workspace(B.root)
    listing = workspace.list_inbox(reloaded)
    assert listing["schema"] == workspace.COMMAND_SCHEMA
    assert len(listing["items"]) == 1
    item = listing["items"][0]
    assert item["envelope_id"] == sent["message"]["envelope_id"]
    assert item["state"] == postoffice.UNREAD
    assert item["kind"] == workspace.DEFAULT_KIND
    assert MARKER not in json.dumps(listing)


# ---------------------------------------------------------------- F. open


def test_open_is_exact_and_state_persists(tmp_path):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    first = workspace.send_message(A, "bob", claim="first message")
    second = workspace.send_message(A, "bob", claim="second message")
    opened = workspace.open_message(B, first["message"]["envelope_id"])
    assert opened["status"] == postoffice.READ_STATE
    assert opened["record"]["claim"] == "first message"
    assert opened["record"]["evidence_state"] == "EVIDENCE_EXPLICITLY_ABSENT"
    reloaded = workspace.load_workspace(B.root)
    listing = workspace.list_inbox(reloaded)
    states = {item["envelope_id"]: item["state"] for item in listing["items"]}
    assert states[first["message"]["envelope_id"]] == postoffice.READ_STATE
    assert states[second["message"]["envelope_id"]] == postoffice.UNREAD
    assert _code(workspace.open_message, B, first["message"]["envelope_id"]) == "ALREADY_READ"
    assert _code(workspace.open_message, B, "sha256:" + "0" * 64) == "UNKNOWN_ENVELOPE"
    promoted = B.root / "mail" / postoffice.PROMOTED
    assert list(promoted.iterdir()) == []


def test_expired_message_refuses_open(tmp_path):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    sent = workspace.send_message(A, "bob", claim="ttl candidate")
    B.office().sweep_expired(now="2099-01-01T00:00:00Z")
    assert _code(workspace.open_message, B,
                 sent["message"]["envelope_id"]) == "ALREADY_EXPIRED"
    listing = workspace.list_inbox(B)
    assert listing["items"][0]["state"] == postoffice.EXPIRED_STATE


# ------------------------------------------------------------ G. duplicate


def test_redeliver_duplicate_keeps_identity_and_unread_state(tmp_path):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    sent = workspace.send_message(A, "bob", claim="dedup proof")
    envelope_id = sent["message"]["envelope_id"]
    before_rows = len(B.office().read_index())
    replay = workspace.redeliver_message(A, envelope_id)
    assert replay["status"] == postoffice.DUPLICATE
    assert replay["message"]["received_at"] == sent["message"]["received_at"]
    listing = workspace.list_inbox(B)
    assert len(listing["items"]) == 1
    assert len(B.office().read_index()) == before_rows


def test_redeliver_missing_outbox_is_named(tmp_path):
    A, _B, _a_root, _b_root = _init_pair(tmp_path)
    assert _code(workspace.redeliver_message, A,
                 "sha256:" + "1" * 64) == workspace.OUTBOX_MISSING


def test_redeliver_of_tampered_container_is_quarantined(tmp_path):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    sent = workspace.send_message(A, "bob", claim="tamper target")
    path = workspace._outbox_path(A, sent["message"]["envelope_id"])
    container = path.read_text(encoding="utf-8")
    prefix, _, b64 = container.partition("CIPHERTEXT:")
    b64 = b64.strip()
    flipped = "A" if b64[100] != "A" else "B"
    b64 = b64[:100] + flipped + b64[101:]
    path.write_text(prefix + "CIPHERTEXT:" + b64 + "\n", encoding="utf-8")
    replay = workspace.redeliver_message(A, sent["message"]["envelope_id"])
    assert replay["status"] == postoffice.QUARANTINED
    assert replay["delivery"]["reason"] == "CIPHER_HASH_MISMATCH"


# ----------------------------------------------------------- H. CLI / UX


def test_cli_multi_invocation_workflow(tmp_path):
    A, B, a_root, b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    sent = _run(["send", "--workspace", str(a_root), "--to", "bob",
                 "--claim", "cli invocation proof", "--json"])
    assert sent.returncode == 0, sent.stdout + sent.stderr
    payload = json.loads(sent.stdout)
    envelope_id = payload["message"]["envelope_id"]
    inbox = _run(["inbox", "--workspace", str(b_root), "--json"])
    assert json.loads(inbox.stdout)["items"][0]["envelope_id"] == envelope_id
    opened = _run(["open", "--workspace", str(b_root), "--envelope", envelope_id, "--json"])
    assert json.loads(opened.stdout)["record"]["claim"] == "cli invocation proof"


def test_cli_refusals_keep_distinct_codes(tmp_path):
    missing = _run(["inbox", "--workspace", str(tmp_path / "absent"), "--json"])
    assert missing.returncode == 1
    assert json.loads(missing.stdout)["status"] == workspace.WORKSPACE_MISSING
    _A, _B, a_root, _b_root = _init_pair(tmp_path)
    unknown = _run(["send", "--workspace", str(a_root), "--to", "nobody",
                    "--claim", "x", "--json"])
    assert json.loads(unknown.stdout)["status"] == workspace.RECIPIENT_UNKNOWN
    bad = _run(["send", "--workspace", str(a_root), "--to", "nobody",
                "--claim", "x", "--record", "y", "--json"])
    assert json.loads(bad.stdout)["status"] == workspace.BAD_INPUT
    malformed = json.loads((tmp_path / "ws-a" / workspace.MARKER_NAME).read_text(encoding="utf-8"))
    malformed.pop("sender_kid")
    (tmp_path / "ws-a" / workspace.MARKER_NAME).write_text(
        json.dumps(malformed), encoding="utf-8")
    broken = _run(["inbox", "--workspace", str(tmp_path / "ws-a"), "--json"])
    assert json.loads(broken.stdout)["status"] == workspace.INVALID_WORKSPACE


# ------------------------------------------------------------- J. privacy


def test_no_private_material_in_any_cli_result(tmp_path):
    A, B, a_root, b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    identity = json.loads(
        (a_root / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME).read_text(encoding="utf-8"))
    sent = _run(["send", "--workspace", str(a_root), "--to", "bob",
                 "--claim", "privacy scan " + MARKER, "--json"])
    listing = _run(["inbox", "--workspace", str(b_root), "--json"])
    opened = _run(["open", "--workspace", str(b_root), "--envelope",
                   json.loads(sent.stdout)["message"]["envelope_id"], "--json"])
    for completed in (sent, listing, opened):
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert identity["sender_private_key"] not in completed.stdout
        assert identity["recipient_private_key"] not in completed.stdout
    assert MARKER not in listing.stdout
    assert MARKER in opened.stdout


def test_no_plaintext_persisted_by_send(tmp_path):
    A, B, _a_root, _b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    workspace.send_message(A, "bob", claim="persisted check " + MARKER)
    needle = MARKER.encode("utf-8")
    for root in (A.root, B.root):
        for path in root.rglob("*"):
            if path.is_file():
                assert needle not in path.read_bytes(), path


# ------------------------------------------------------------- K. network


def test_engine_imports_no_network_surface_and_makes_no_calls(tmp_path):
    source = (ROOT / "saimail" / "workspace.py").read_text(encoding="utf-8")
    for forbidden in ("import socket", "import urllib", "import http", "requests"):
        assert forbidden not in source
    import saimail_local

    A, B, _a_root, _b_root = _init_pair(tmp_path)
    _link(A, B, tmp_path)
    probe = {"blocked": 0}
    with saimail_local.no_network(probe):
        sent = workspace.send_message(A, "bob", claim="network proof")
        workspace.list_inbox(B)
        workspace.open_message(B, sent["message"]["envelope_id"])
    assert probe["blocked"] == 0


def test_private_bytes_in_identity_file_are_not_the_public_material(tmp_path):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    workspace_loaded = workspace.load_workspace(root)
    identity = json.loads(
        (root / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME).read_text(encoding="utf-8"))
    assert identity["sender_private_key"] != workspace_loaded.identity["sender_public_key"]
    assert identity["recipient_private_key"] != workspace_loaded.identity["recipient_public_key"]


def test_unsupported_workspace_version_is_refused(tmp_path):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    marker_path = root / workspace.MARKER_NAME
    marker = json.loads(marker_path.read_text(encoding="utf-8"))
    marker["version"] = 99
    marker_path.write_text(json.dumps(marker), encoding="utf-8")
    assert _code(workspace.load_workspace, root) == workspace.INVALID_WORKSPACE
