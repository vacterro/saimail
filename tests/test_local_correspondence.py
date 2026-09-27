"""V4-01 focused tests: one-hop local correspondence continuation (spec/24).

Covers the reply contract end to end: the target must already be READ and is
resolved from index metadata plus durable lifecycle state only; the reply is an
ordinary canonical record sealed through the unchanged SENV2 path with ``REF``
set to the original ``ENVELOPE_ID``; the reply recipient is bound to the
original sender identity; no SAILANG semantic relation is ever invented; the
existing P1 ``inbox --ref`` query finds the reply without opening anything; and
the target payload is never read or decrypted a second time.

No network, no model, no provider and no second payload-read path anywhere here.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from sailang import Record, SailangError, parse as parse_record
from saimail import envelope, postoffice, workspace

ORIGINAL = "v4-01 synthetic original message 3a7e"
REPLY = "v4-01 synthetic reply body 91bc"
RELATION_REF = "sha256:" + "a" * 64


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _init_pair(tmp_path):
    a_root = tmp_path / "ws-a"
    b_root = tmp_path / "ws-b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    a = workspace.load_workspace(a_root)
    b = workspace.load_workspace(b_root)
    workspace.add_recipient(a, "bob", workspace.identity_card(b), b_root)
    workspace.add_recipient(b, "alice", workspace.identity_card(a), a_root)
    return a, b, a_root, b_root


def _deliver(a, b, claim=ORIGINAL, **kwargs) -> str:
    sent = workspace.send_message(a, "bob", claim=claim, **kwargs)
    assert sent["status"] == postoffice.ACCEPTED, sent
    return sent["message"]["envelope_id"]


def _read_reply_container(receiver, outbox_root, envelope_id):
    """Parse and open a reply from the sender's outbox under the receiver identity."""
    digest = envelope_id.split(":", 1)[1]
    path = Path(outbox_root) / workspace.OUTBOX_DIR / (digest + ".senv")
    container = path.read_text(encoding="utf-8")
    office = receiver.office()
    verified = envelope.verify(envelope.parse_header(container), office.sender_registry)
    opened = envelope.open(verified, receiver.recipient_private_key,
                           office.recipient_registry)
    return verified.header, opened


def _snapshot(root: Path) -> dict:
    snapshot = {}
    for path in sorted(Path(root).rglob("*")):
        if path.is_file():
            snapshot[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return snapshot


def _poison_payload_paths(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("a reply reached a payload/open/decrypt path")

    monkeypatch.setattr(envelope, "open", boom)
    monkeypatch.setattr(postoffice.PostOfficeSession, "open_message", boom)
    monkeypatch.setattr(workspace, "open_message", boom)


# ------------------------------------------------ A. continuation contract


def test_reply_sets_existing_senv2_ref_and_inherits_topic(tmp_path):
    a, b, _a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)

    result = workspace.reply_message(b, x, claim=REPLY)
    assert result["schema"] == workspace.COMMAND_SCHEMA
    assert result["command"] == "reply"
    assert result["status"] == postoffice.ACCEPTED
    assert result["target"] == {"envelope_id": x, "state": postoffice.READ_STATE,
                                "from": "SAIMAIL-A", "from_kid": a.sender_kid,
                                "topic": "local-message"}
    assert result["reply"]["ref"] == x
    assert result["reply"]["to"] == "SAIMAIL-A"
    assert result["reply"]["kind"] == workspace.DEFAULT_REPLY_KIND
    assert result["reply"]["topic"] == "local-message"
    # the result never carries authored content or original plaintext
    assert REPLY not in json.dumps(result)
    assert ORIGINAL not in json.dumps(result)

    header, opened = _read_reply_container(a, b_root, result["reply"]["envelope_id"])
    assert header.get("REF") == x
    record = parse_record(opened.plaintext)
    assert record.claim == REPLY
    assert record.kind == workspace.WRAPPER_KIND
    assert record.status == workspace.WRAPPER_STATUS


def test_reply_refuses_unread_and_creates_no_outgoing_reply(tmp_path):
    a, b, _a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    outbox = b_root / workspace.OUTBOX_DIR
    before_rows = len(a.office().read_index())

    assert _code(workspace.reply_message, b, x, claim=REPLY) == workspace.REPLY_TARGET_UNREAD
    assert b.office().bundle_state(x) == postoffice.UNREAD
    assert list(outbox.iterdir()) == []
    assert len(a.office().read_index()) == before_rows


def test_reply_kind_is_never_inherited_and_explicit_fields_win(tmp_path):
    a, b, _a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b, kind="WARNING", topic="ops")
    workspace.open_message(b, x)

    defaulted = workspace.reply_message(b, x, claim=REPLY)
    header, _opened = _read_reply_container(a, b_root, defaulted["reply"]["envelope_id"])
    assert header.get("K") == "PERSONAL_MESSAGE"       # not WARNING
    assert header.get("TOPIC") == "ops"                # topic inherited

    explicit = workspace.reply_message(b, x, claim=REPLY, kind="QUESTION", topic="followup")
    header2, opened2 = _read_reply_container(a, b_root, explicit["reply"]["envelope_id"])
    assert header2.get("K") == "QUESTION"
    assert header2.get("TOPIC") == "followup"
    assert parse_record(opened2.plaintext).claim == REPLY


def test_reply_from_a_canonical_record_file(tmp_path):
    a, b, _a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    record = Record.create(KIND="F", SRC="HUMAN:SAIMAIL-B", SUBJ="continuation",
                           CLAIM="canonical continuation record", TYPE="OBS", EV="0",
                           STATUS="U1", CREATED=postoffice.utc_now())
    record_path = tmp_path / "reply.sailang"
    record_path.write_text(record.canonical_text(), encoding="utf-8")

    result = workspace.reply_message(b, x, record_path=record_path)
    assert result["status"] == postoffice.ACCEPTED
    _header, opened = _read_reply_container(a, b_root, result["reply"]["envelope_id"])
    assert parse_record(opened.plaintext).content_id == record.content_id


# ------------------------------------------------------ B. target failures


def test_unknown_and_malformed_targets_are_refused(tmp_path):
    _a, b, _a_root, _b_root = _init_pair(tmp_path)
    assert _code(workspace.reply_message, b, "sha256:" + "0" * 64,
                 claim=REPLY) == workspace.REPLY_TARGET_UNKNOWN
    assert _code(workspace.reply_message, b, "not-an-envelope-id",
                 claim=REPLY) == workspace.BAD_INPUT


def test_expired_target_is_refused_without_resurrection(tmp_path):
    a, b, _a_root, _b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    b.office().sweep_expired(now="2099-01-01T00:00:00Z")
    assert _code(workspace.reply_message, b, x, claim=REPLY) == workspace.REPLY_TARGET_EXPIRED
    assert b.office().bundle_state(x) == postoffice.EXPIRED_STATE


def test_both_crash_state_fails_closed(tmp_path):
    a, b, _a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    read = b.office().read_bundle(x)
    inbox = b.office().inbox_bundle(x)
    shutil.copytree(read, inbox)
    assert _code(workspace.reply_message, b, x, claim=REPLY) == (
        postoffice.RECONCILIATION_REQUIRED)


def test_index_row_without_body_fails_closed(tmp_path):
    a, b, _a_root, _b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    inbox = b.office().inbox_bundle(x)
    shutil.rmtree(inbox)
    assert _code(workspace.reply_message, b, x, claim=REPLY) == (
        postoffice.INDEX_BODY_MISSING)


# ------------------------------------------------- C. recipient resolution


def test_unregistered_original_sender_is_refused(tmp_path):
    a, b, _a_root, _b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    workspace._write_peers(b.root, {})
    assert _code(workspace.reply_message, b, x, claim=REPLY) == (
        workspace.REPLY_RECIPIENT_UNKNOWN)


def test_seat_only_peer_does_not_redirect_the_reply(tmp_path):
    a, b, _a_root, _b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    # A different identity that happens to reuse the same seat label must not
    # receive a reply aimed at the original sender's key.
    impostor_root = tmp_path / "ws-a-impostor"
    workspace.init_workspace(impostor_root, seat="SAIMAIL-A")
    impostor = workspace.load_workspace(impostor_root)
    card = workspace.identity_card(impostor)
    workspace._write_peers(b.root, {"alice": {
        "seat": card["seat"], "created": card["created"],
        "sender_public_key": card["sender_public_key"],
        "recipient_public_key": card["recipient_public_key"],
        "sender_kid": card["sender_kid"], "recipient_kid": card["recipient_kid"],
        "workspace": str(impostor_root), "added_at": postoffice.utc_now()}})
    assert _code(workspace.reply_message, b, x, claim=REPLY) == (
        workspace.REPLY_RECIPIENT_MISMATCH)


def test_delivery_failure_is_not_a_fabricated_success(tmp_path):
    a, b, a_root, _b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    # Remove the receiver-side mapping that accepts B's key: the reply is now
    # quarantined by A's Post Office and must not report ACCEPTED.
    workspace._write_peers(a_root, {})
    result = workspace.reply_message(b, x, claim=REPLY)
    assert result["status"] == postoffice.QUARANTINED
    assert result["ok"] is False
    assert result["delivery"]["reason"] == "UNKNOWN_SENDER_KEY"


# ------------------------------------------- D. no second decrypt path


def test_reply_does_not_re_decrypt_the_target(tmp_path, monkeypatch):
    a, b, _a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    # The earlier explicit open is the ONLY payload read. Delete the read
    # bundle's container would break state; instead poison every decrypt path
    # and require reply to succeed from index metadata plus durable READ state.
    _poison_payload_paths(monkeypatch)
    result = workspace.reply_message(b, x, claim=REPLY)
    assert result["status"] == postoffice.ACCEPTED
    assert result["reply"]["ref"] == x


# ---------------------------------------------- E. semantic relations


def test_generic_reply_invents_no_semantic_relation(tmp_path):
    a, b, _a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    result = workspace.reply_message(b, x, claim=REPLY)
    _header, opened = _read_reply_container(a, b_root, result["reply"]["envelope_id"])
    record = parse_record(opened.plaintext)
    for relation in ("SUPPORTS", "REFUTES", "CON"):
        assert relation not in record


def test_explicit_semantic_relation_is_preserved_alongside_ref(tmp_path):
    a, b, _a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    record = Record.create(KIND="F", SRC="HUMAN:SAIMAIL-B", SUBJ="rebuttal",
                           CLAIM="the original claim is contradicted", TYPE="OBS",
                           EV="0", STATUS="U1", REFUTES=RELATION_REF,
                           CREATED=postoffice.utc_now())
    record_path = tmp_path / "rebuttal.sailang"
    record_path.write_text(record.canonical_text(), encoding="utf-8")

    result = workspace.reply_message(b, x, record_path=record_path)
    header, opened = _read_reply_container(a, b_root, result["reply"]["envelope_id"])
    # Two relation domains coexist without being conflated: the transport link
    # is SENV2 REF, and the author's semantic REFUTES claim is untouched.
    assert header.get("REF") == x
    assert parse_record(opened.plaintext).get("REFUTES") == RELATION_REF


# ------------------------------------------------- F. P1 discovery


def test_existing_ref_query_discovers_the_reply_without_opening(tmp_path, monkeypatch):
    a, b, a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    reply = workspace.reply_message(b, x, claim=REPLY)
    y = reply["reply"]["envelope_id"]

    before = _snapshot(a_root)
    _poison_payload_paths(monkeypatch)
    found = workspace.query_inbox(a, ref=x)
    assert [item["envelope_id"] for item in found["items"]] == [y]
    assert found["items"][0]["ref"] == x
    assert found["rows_examined"] >= 1
    assert _snapshot(a_root) == before


def test_multiple_replies_and_reply_to_reply_chain(tmp_path):
    a, b, _a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    first = workspace.reply_message(b, x, claim="first continuation")
    second = workspace.reply_message(b, x, claim="second continuation")
    y = first["reply"]["envelope_id"]
    assert second["reply"]["ref"] == x and second["reply"]["envelope_id"] != y

    found = workspace.query_inbox(a, ref=x)
    assert {item["envelope_id"] for item in found["items"]} == {
        y, second["reply"]["envelope_id"]}

    # A continues the chain from the reply it opened: Z refs Y, no thread root.
    workspace.open_message(a, y)
    third = workspace.reply_message(a, y, claim="reply to reply")
    z = third["reply"]["envelope_id"]
    assert third["reply"]["ref"] == y
    back = workspace.query_inbox(b, ref=y)
    assert [item["envelope_id"] for item in back["items"]] == [z]


# --------------------------------------------- G. backward compatibility


def test_ordinary_send_carries_no_ref_and_reply_replay_is_duplicate(tmp_path):
    a, b, a_root, b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    container = (a_root / workspace.OUTBOX_DIR
                 / (x.split(":", 1)[1] + ".senv")).read_text(encoding="utf-8")
    assert envelope.parse_header(container).get("REF") is None

    workspace.open_message(b, x)
    reply = workspace.reply_message(b, x, claim=REPLY)
    y = reply["reply"]["envelope_id"]
    replay = workspace.redeliver_message(b, y)
    assert replay["status"] == postoffice.DUPLICATE
    assert replay["message"]["received_at"] == reply["reply"]["created"]


# -------------------------------------------------------- H. bad input


def test_bad_content_forms_are_refused(tmp_path):
    a, b, _a_root, _b_root = _init_pair(tmp_path)
    x = _deliver(a, b)
    workspace.open_message(b, x)
    assert _code(workspace.reply_message, b, x) == workspace.BAD_INPUT
    assert _code(workspace.reply_message, b, x, claim="") == workspace.BAD_INPUT
    assert _code(workspace.reply_message, b, x, claim="one\ntwo") == workspace.BAD_INPUT
    assert _code(workspace.reply_message, b, x, claim=REPLY,
                 record_path=tmp_path / "missing.sailang") == workspace.BAD_INPUT
    bad = tmp_path / "bad.sailang"
    bad.write_text("NOT-A-SAILANG-RECORD\n", encoding="utf-8")
    assert _code(workspace.reply_message, b, x, record_path=bad) != "NO_ERROR"
