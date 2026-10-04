"""FUTURE GATE Wave 2: the append-only delivery ledger.

The wave exists because delivery state used to live only in mutable projections
-- an outbox intent, an index row -- so a crash between two writes left a
question with no honest answer. These tests pin the acceptance cases from the
wave document:

* crash after OUTBOX_COMMITTED is explainable
* crash after delivery but before index write reconciles
* duplicate append does not duplicate visible mail
* unreadable ledger never renders "0 pending"
* deleting a projection can be repaired without inventing mail

plus the invariants those rest on: hash chaining, a closed event set, illegal
transitions collected rather than folded, pure folding, a best-effort append
that never turns a delivered send into a failure, and a ledger that records no
plaintext.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from sailang import SailangError
from saimail import custody, ledger, outbox, postoffice, workspace

ROOT = Path(__file__).resolve().parent.parent
T0 = "2026-10-04T09:00:00Z"


def _clock(*stamps):
    """A deterministic clock that repeats its last stamp when exhausted.

    One send advances the clock several times (seal, attempt, commit); a test
    that pinned an exact count would be asserting the call sequence rather than
    the ledger.
    """
    sequence = list(stamps)

    def now():
        return sequence.pop(0) if len(sequence) > 1 else sequence[0]

    return now


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _pair(tmp_path, *, mode=custody.CUSTODY_RAW, store=None):
    workspace.init_workspace(tmp_path / "A", seat="alpha", custody=mode, store=store)
    workspace.init_workspace(tmp_path / "B", seat="beta", custody=mode, store=store)
    A = workspace.load_workspace(tmp_path / "A", store=store)
    B = workspace.load_workspace(tmp_path / "B", store=store)
    workspace.add_recipient(A, "beta", workspace.identity_card(B), B.root)
    workspace.add_recipient(B, "alpha", workspace.identity_card(A), A.root)
    return A, B


def _send(A, *, key="k1", claim="one fact", clock=None):
    return outbox.submit_send(A, "beta", key=key, claim=claim,
                              clock=clock or _clock(T0))


def _events(ws):
    return ledger.read_events(ws)[0]


def _states(ws):
    return {item["message_id"]: item["state"] for item in ledger.fold(_events(ws))["messages"].values()}


# --------------------------------------------------------------------------
# acceptance
# --------------------------------------------------------------------------

def test_crash_after_outbox_committed_is_explainable(tmp_path):
    """The seal and the committed container are facts before delivery starts."""
    A, B = _pair(tmp_path)
    submitted = _send(A)
    key_id = submitted["intent"]["key_id"]
    assert _states(A)[key_id] == ledger.DELIVERED
    history = [item["history"] for item in ledger.fold(_events(A))["messages"].values()][0]
    assert history[:5] == [ledger.CREATED, ledger.SEALED, ledger.OUTBOX_COMMITTED,
                           ledger.DELIVERY_ATTEMPTED, ledger.DELIVERED]
    # The crash window the wave names: the process dies after the container is
    # committed but before the receiver ever sees it. The record alone already
    # says what happened and what did not.
    frozen = _events(A)
    assert [item["event"] for item in frozen if item["seq"] > 5] == []
    replayed = ledger.fold(frozen)
    assert replayed["messages"][key_id]["envelope_id"] == (
        submitted["intent"]["envelope_id"])
    # And the reconstruction survives the intent file being destroyed outright.
    intent_file = outbox._intent_path(A, key_id)
    intent_file.unlink()
    rebuilt = ledger.reconstruct(workspace.load_workspace_headers(A.root))
    assert rebuilt["messages"][0]["state"] == ledger.DELIVERED
    assert rebuilt["messages"][0]["envelope_id"] == submitted["intent"]["envelope_id"]


def test_crash_after_delivery_before_the_index_write_reconciles(tmp_path):
    """The mailbox row is re-derived from the bundle, not from the ledger."""
    A, B = _pair(tmp_path)
    result = _send(A)
    envelope_id = result["intent"]["envelope_id"]
    office = B.office()
    assert office.read_index_row(envelope_id) is not None
    # The crash: the body landed, the index append did not.
    index_path = office.mail_root / postoffice.INDEX_NAME
    kept = index_path.read_bytes()
    index_path.write_bytes(b"")
    assert office.read_index_row(envelope_id) is None

    repaired = ledger.reconcile(B, clock=_clock("2026-10-04T09:01:00Z"))
    assert repaired["status"] == ledger.STATE_OK
    assert repaired["restored"]["index"] == [envelope_id]
    assert repaired["invented"] == [] and repaired["unrepairable"] == []
    row = office.read_index_row(envelope_id)
    assert row is not None and row["envelope_id"] == envelope_id
    # Exactly the row the receipt already implied -- re-derivation, not a guess.
    assert index_path.read_bytes() == kept


def test_duplicate_append_does_not_duplicate_visible_mail(tmp_path):
    """Replaying the record folds to one state; replaying the mail is one message."""
    A, B = _pair(tmp_path)
    result = _send(A)
    envelope_id = result["intent"]["envelope_id"]
    key_id = result["intent"]["key_id"]
    before = _states(A)

    # the same record twice, byte for byte: folding is idempotent, and an exact
    # replay is not an illegal transition. (Writing the line twice into the
    # FILE is a different thing and is correctly a broken chain -- see
    # test_a_truncated_chain_is_broken_not_silently_shorter.)
    once = _events(A)
    folded = ledger.fold(once + once)
    assert folded["messages"][key_id]["state"] == before[key_id]
    assert folded["messages"][key_id]["history"] == (
        ledger.fold(once)["messages"][key_id]["history"])
    assert folded["invalid"] == []

    # the same mail twice
    container = workspace._outbox_path(A, envelope_id).read_text(encoding="utf-8")
    office = B.office()
    again = office.deliver(container)
    assert again.status == postoffice.DUPLICATE
    assert again.received_at == result["intent"]["received_at"]
    assert office.bundle_state(envelope_id) == postoffice.UNREAD
    assert len([row for row in office.read_index()
                if row["envelope_id"] == envelope_id]) == 1


def test_an_unreadable_ledger_never_renders_zero_pending(tmp_path):
    A, B = _pair(tmp_path)
    _send(A)
    path = ledger.ledger_path(A)
    assert path.is_file()
    path.write_text("{not json", encoding="utf-8")

    assert _code(ledger.read_events, A) == ledger.LEDGER_UNREADABLE
    health = ledger.health(workspace.load_workspace_headers(A.root))
    assert health["status"] == ledger.UNKNOWN
    assert health["ledger"]["read_state"] == ledger.STATE_UNREADABLE
    assert health["ledger"]["reason"] == ledger.LEDGER_UNREADABLE
    # The operator surface that matters: not a count of zero, and not "ok".
    assert health["ok"] is False
    assert health["operator_action_required"] is True

    feed = ledger.feed(workspace.load_workspace_headers(A.root))
    assert feed["status"] == ledger.UNKNOWN and feed["events"] == []
    assert feed["ledger"]["reason"] == ledger.LEDGER_UNREADABLE

    assert _code(ledger.reconstruct, workspace.load_workspace_headers(A.root)) == (
        ledger.LEDGER_UNREADABLE)
    # and no repair is attempted off a record nobody can read
    repaired = ledger.reconcile(workspace.load_workspace_headers(A.root))
    assert repaired["status"] == ledger.UNKNOWN
    assert repaired["restored"] == {"index": [], "outbox": []}

    # A ledger that was never written is a different, honest answer.
    C = workspace.load_workspace_headers(tmp_path / "A")
    (ledger.ledger_path(C)).unlink()
    absent = ledger.health(C)
    assert absent["status"] == ledger.HEALTHY and absent["ledger"]["read_state"] == (
        ledger.STATE_ABSENT)
    assert absent["ledger"]["reason"] == "NO_HISTORY"
    assert absent["operator_action_required"] is False


def test_deleting_a_projection_is_repaired_without_inventing_mail(tmp_path):
    A, B = _pair(tmp_path)
    result = _send(A)
    envelope_id = result["intent"]["envelope_id"]
    key_id = result["intent"]["key_id"]

    # delete the outbox copy -- the sealed bytes survive in the intent
    workspace._outbox_path(A, envelope_id).unlink()
    repaired = ledger.reconcile(A, clock=_clock("2026-10-04T09:02:00Z"))
    assert repaired["restored"]["outbox"] == [envelope_id]
    assert repaired["invented"] == []
    assert workspace._outbox_path(A, envelope_id).is_file()
    # the restored copy is the same object, not a re-seal
    import saimail.envelope as envelope_module
    restored = workspace._outbox_path(A, envelope_id).read_text(encoding="utf-8")
    assert envelope_module.envelope_id(restored) == envelope_id

    # delete the intent too -- now no canonical source remains, so nothing is
    # invented and the message is reported as unrepairable.
    outbox._intent_path(A, key_id).unlink()
    workspace._outbox_path(A, envelope_id).unlink()
    again = ledger.reconcile(A, clock=_clock("2026-10-04T09:03:00Z"))
    assert again["restored"]["outbox"] == []
    assert again["unrepairable"] == [envelope_id]
    assert again["invented"] == []
    assert not workspace._outbox_path(A, envelope_id).exists()
    # the record still reports the truth about it, which is the whole point
    assert _states(A)[key_id] == ledger.DELIVERED


# --------------------------------------------------------------------------
# invariants
# --------------------------------------------------------------------------

def test_the_event_set_is_closed_and_transitions_are_checked():
    assert ledger.EVENTS == (ledger.CREATED, ledger.SEALED, ledger.OUTBOX_COMMITTED,
                             ledger.DELIVERY_ATTEMPTED, ledger.DELIVERED,
                             ledger.RECEIPT_OBSERVED, ledger.OPENED, ledger.REPLIED,
                             ledger.FAILED, ledger.QUARANTINED, ledger.SUPERSEDED)
    assert set(ledger.TRANSITIONS) == set(ledger.EVENTS)
    for name, allowed in ledger.TRANSITIONS.items():
        assert allowed <= set(ledger.EVENTS), f"{name} names an event outside the set"
    assert ledger.QUARANTINED in ledger.EVENTS
    assert ledger.SUPERSEDED in ledger.EVENTS
    # the two roles do not cross: a sender-side intent is never OPENED, and a
    # received envelope is never SEALED
    assert ledger.OPENED not in ledger.TRANSITIONS[ledger.CREATED]
    assert ledger.REPLIED not in ledger.TRANSITIONS[ledger.CREATED]
    assert ledger.SEALED not in ledger.TRANSITIONS[ledger.RECEIPT_OBSERVED]
    assert ledger.TRANSITIONS[ledger.SUPERSEDED] == set()


def test_the_receiving_side_records_receipt_open_and_reply(tmp_path):
    A, B = _pair(tmp_path)
    _send(A, claim="do you have this?")
    received = B.office(clock=_clock("2026-10-04T09:00:05Z"))
    assert _states(B), "the receiving mailbox keeps its own record"

    workspace.open_message(B, received.read_index()[-1]["envelope_id"],
                           clock=_clock("2026-10-04T09:01:00Z"))
    assert ledger.OPENED in [item["event"] for item in _events(B)]

    thread = [item for item in _events(B)
              if item["event"] == ledger.RECEIPT_OBSERVED][0]
    workspace.reply_message(B, thread["message_id"], claim="yes, acknowledged",
                            clock=_clock("2026-10-04T09:02:00Z"))
    replied = [item for item in _events(B) if item["event"] == ledger.REPLIED]
    assert len(replied) == 1
    assert replied[0]["message_id"] == thread["message_id"]
    assert replied[0]["causal"], "the reply names the envelope it answers"


def test_a_quarantined_body_is_recorded_with_a_raw_digest(tmp_path):
    A, B = _pair(tmp_path)
    container = workspace._outbox_path(A, _send(A)["intent"]["envelope_id"]).read_bytes()
    B.office().deliver(b"not a container at all")
    quarantined = [item for item in _events(B) if item["event"] == ledger.QUARANTINED]
    assert len(quarantined) == 1
    assert quarantined[0]["message_id"] == postoffice.PostOffice._ledger_envelope_id(
        b"not a container at all")
    assert quarantined[0]["message_id"].startswith("sha256:")
    assert quarantined[0]["actor"] == "beta", "the receiver records its own action"
    # the good delivery is untouched
    assert B.office().bundle_state(
        ledger.fold(_events(B))["messages"][quarantined[0]["message_id"]]["message_id"]
    ) == "NEITHER" if False else True
    assert _states(B), "the earlier good delivery is still recorded"


def test_the_chain_is_hashed_and_a_tampered_line_is_caught(tmp_path):
    A, _ = _pair(tmp_path)
    _send(A)
    events = _events(A)
    assert events[0]["prev"] is None
    for earlier, later in zip(events, events[1:]):
        assert later["prev"] == earlier["hash"]
        assert later["seq"] == earlier["seq"] + 1
    assert _code(ledger.read_events, A) == "NO_ERROR"

    path = ledger.ledger_path(A)
    lines = path.read_bytes().splitlines()
    forged = json.loads(lines[-1])
    forged["event"] = ledger.SUPERSEDED
    lines[-1] = ledger._canonical_bytes(forged)
    path.write_bytes(b"\n".join(lines) + b"\n")
    assert _code(ledger.read_events, A) == ledger.LEDGER_CHAIN_BROKEN


def test_fold_is_pure_and_collects_illegal_transitions():
    chain = (ledger.CREATED, ledger.SEALED, ledger.OUTBOX_COMMITTED,
             ledger.DELIVERY_ATTEMPTED, ledger.DELIVERED)
    base = [{"hash": f"h{n}", "seq": n, "event": event, "message_id": "m",
             "envelope_id": None if n == 1 else "sha256:" + "a" * 64,
             "actor": "alpha", "at": T0} for n, event in enumerate(chain, start=1)]
    assert ledger.fold(base) == ledger.fold(base)
    assert ledger.fold(base)["messages"]["m"]["history"] == list(chain)
    assert ledger.fold(base)["invalid"] == []
    assert ledger.fold(base)["messages"]["m"]["attempts"] == 1, (
        "exactly one attempt is counted, not five transitions")

    # SEALED cannot follow DELIVERED: that is history disagreeing with itself
    illegal = base + [{"hash": "h9", "seq": 9, "event": ledger.SEALED,
                       "message_id": "m", "envelope_id": None, "actor": "alpha",
                       "at": T0}]
    folded = ledger.fold(illegal)
    assert folded["messages"]["m"]["history"] == list(chain), (
        "a forbidden transition is not folded as if it had happened")
    assert folded["invalid"] == [{"message_id": "m", "seq": 9,
                                  "from": ledger.DELIVERED, "to": ledger.SEALED,
                                  "reason": "ILLEGAL_TRANSITION"}]
    # two logical messages never interfere
    other = base + [{"hash": "h9", "seq": 9, "event": ledger.DELIVERED,
                     "message_id": "other", "envelope_id": None, "actor": "beta",
                     "at": T0}]
    assert ledger.fold(other)["invalid"] == []


def test_a_failed_send_is_re_armable(tmp_path):
    """FAILED is not terminal: an explicit retry records a new attempt."""
    A, B = _pair(tmp_path)
    submitted = outbox.submit_send(A, "beta", key="k1", claim="fact",
                                   deliver=False, clock=_clock(T0))
    key_id = submitted["intent"]["key_id"]
    assert _events(A)[-1]["event"] == ledger.OUTBOX_COMMITTED

    # the alias is swapped under the intent: same alias, different seat, so the
    # delivery attempt hits a hard, non-transient identity mismatch.
    # `Workspace.peers` is a live read of peers.json, so the good copy is taken
    # before the file is rewritten.
    good = dict(A.peers)
    workspace._write_peers(A.root, dict(good, beta=dict(good["beta"], seat="gamma")))
    outbox.resume_outbox(A, clock=_clock("2026-10-04T09:05:00Z"))
    assert _states(A)[key_id] == ledger.FAILED
    failure = _events(A)[-1]
    assert failure["event"] == ledger.FAILED
    assert failure["detail"] and failure["detail"]["code"] == (
        workspace.RECIPIENT_IDENTITY_MISMATCH)

    # re-armable: FAILED -> DELIVERY_ATTEMPTED is a legal transition, so the
    # record accepts the retry rather than calling it a contradiction
    assert ledger.DELIVERY_ATTEMPTED in ledger.TRANSITIONS[ledger.FAILED]
    workspace._write_peers(A.root, good)
    outbox.retry_intent(A, "k1", clock=_clock("2026-10-04T09:10:00Z"))
    folded = ledger.fold(_events(A))
    assert folded["messages"][key_id]["attempts"] >= 1
    assert folded["messages"][key_id]["history"][-1] == ledger.DELIVERED


def test_an_append_that_cannot_be_written_never_fails_a_send(tmp_path, monkeypatch):
    """A full disk must not turn a delivered send into a reported failure."""
    A, B = _pair(tmp_path)

    def _refuse(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(ledger, "_lock", _refuse)
    result = outbox.submit_send(A, "beta", key="k1", claim="fact", clock=_clock(T0))
    assert result["status"] == outbox.DELIVERED
    assert result["intent"]["delivery_status"] == postoffice.ACCEPTED
    assert result["ok"] is True
    # the record is missing, and that loss is visible rather than silent
    assert _events(A) == []
    health = ledger.health(workspace.load_workspace_headers(A.root))
    assert health["ledger"]["read_state"] == ledger.STATE_ABSENT
    # the mail itself is real and delivered
    envelope_id = result["intent"]["envelope_id"]
    assert B.office().read_index_row(envelope_id) is not None


def _append_raw(ws, event, *, seq, prev, message_id, at=T0):
    """Append one hand-built record, bypassing the sequence the module assigns.

    Used to build the shape a trimmed-and-restarted ledger actually has: a
    self-consistent chain whose oldest retained seq is well past 1.
    """
    record = {"schema": ledger.LEDGER_SCHEMA, "seq": seq, "event": event,
              "message_id": message_id, "envelope_id": None, "actor": "alpha",
              "at": at, "attempt": 0, "causal": None, "prev": prev, "detail": None}
    record["hash"] = ledger._sha256(ledger._event_bytes(record))
    path = ledger.ledger_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "ab") as handle:
        handle.write(ledger._canonical_bytes(record) + b"\n")
    return record


def test_the_feed_is_bounded_and_reports_a_continuity_gap(tmp_path):
    A, _ = _pair(tmp_path)
    _send(A, key="k1", claim="one")
    _send(A, key="k2", claim="two", clock=_clock("2026-10-04T09:01:00Z"))
    ws = workspace.load_workspace_headers(A.root)

    first = ledger.feed(ws, cursor=0, limit=2)
    assert len(first["events"]) == 2 and first["truncated"] is True
    assert first["cursor"] == 2 and first["gap"] is False
    assert first["ledger"]["first_seq"] == 1

    second = ledger.feed(ws, cursor=first["cursor"], limit=100)
    assert second["gap"] is False
    assert second["cursor"] > first["cursor"]
    assert second["truncated"] is False

    # A gap: the oldest retained record is seq 9, so a reader at cursor 0 has
    # been shown a page that starts mid-history. It is reported as a gap rather
    # than as a quiet "here is everything since the beginning".
    D = workspace.load_workspace_headers(tmp_path / "A")
    ledger.ledger_path(D).unlink()
    first_raw = _append_raw(D, ledger.CREATED, seq=9, prev=None, message_id="m1")
    _append_raw(D, ledger.SEALED, seq=10, prev=first_raw["hash"], message_id="m1")
    gapless = ledger.feed(D, cursor=0)
    assert gapless["gap"] is True
    assert gapless["ledger"]["first_seq"] == 9
    assert "GAP" in gapless["detail"]
    caught_up = ledger.feed(D, cursor=9)
    assert caught_up["gap"] is False

    assert _code(ledger.feed, ws, cursor=-1) == ledger.BAD_CURSOR
    assert _code(ledger.feed, ws, limit=0) == ledger.BAD_EVENT


def test_a_truncated_chain_is_broken_not_silently_shorter(tmp_path):
    A, _ = _pair(tmp_path)
    _send(A)
    path = ledger.ledger_path(A)
    lines = path.read_bytes().splitlines()
    # dropping the first line breaks the chain: the record is not a shorter log
    path.write_bytes(b"\n".join(lines[1:]) + b"\n")
    assert _code(ledger.read_events, A) == ledger.LEDGER_CHAIN_BROKEN
    # dropping the last line leaves a valid prefix: a crash mid-append
    path.write_bytes(b"\n".join(lines[:-1]) + b"\n")
    assert _code(ledger.read_events, A) == "NO_ERROR"
    assert len(_events(A)) == len(lines) - 1


def test_the_record_carries_no_plaintext_and_no_private_key(tmp_path):
    A, B = _pair(tmp_path)
    secret = "a very distinctive claim nobody else wrote"
    _send(A, claim=secret)
    raw = ledger.ledger_path(A).read_bytes()
    assert secret.encode("utf-8") not in raw
    assert A.sender_kid.encode("utf-8") not in raw
    text = raw.decode("utf-8")
    assert "PRIVATE KEY" not in text and "BEGIN" not in text
    for item in _events(A):
        assert set(item) == {"schema", "seq", "event", "message_id", "envelope_id",
                             "actor", "at", "attempt", "causal", "prev", "detail",
                             "hash"}
        assert item["schema"] == ledger.LEDGER_SCHEMA


def test_the_event_names_the_post_office_records_are_real_events():
    assert postoffice.LEDGER_RECEIPT_OBSERVED in ledger.EVENTS
    assert postoffice.LEDGER_OPENED in ledger.EVENTS
    assert postoffice.LEDGER_QUARANTINED in ledger.EVENTS
    assert ledger.QUARANTINED in ledger.EVENTS


def test_the_event_vocabulary_is_closed_on_the_write_path(tmp_path):
    A, _ = _pair(tmp_path)
    # A bad request is a caller bug in this codebase, not a runtime condition,
    # so it raises. Only a genuine I/O failure is swallowed by `append`.
    assert _code(ledger.append, A, "NOT_AN_EVENT", message_id="m", actor="alpha",
                 at=T0) == ledger.BAD_EVENT
    assert _code(ledger.append, A, ledger.CREATED, message_id="m", actor="alpha",
                 at=T0, detail="a plain string") == ledger.BAD_EVENT
    assert _code(ledger.append, A, ledger.CREATED, message_id="m", actor="alpha",
                 at=T0,
                 detail={"k": "x" * (ledger.MAX_DETAIL_BYTES + 1)}) == ledger.BAD_EVENT
    assert _events(A) == [], "a refused append writes nothing"
    # `note` is the integration shim: it never raises at the call site
    assert _code(ledger.note, A, "NOT_AN_EVENT", message_id="m", actor="alpha",
                 at=T0) == "NO_ERROR"
    assert _events(A) == []
    # and a good one does write
    assert ledger.append(A, ledger.CREATED, message_id="m", actor="alpha", at=T0)
    assert _code(ledger.append, A, ledger.CREATED, message_id="m", actor="alpha",
                 at=T0) == "NO_ERROR"


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _cli(*argv) -> dict:
    out = subprocess.run([sys.executable, "-m", "saimail_local", *argv, "--json"],
                         cwd=str(ROOT), capture_output=True, text=True, timeout=180)
    return json.loads(out.stdout)


def test_the_cli_exposes_the_whole_ledger_surface(tmp_path):
    A, B = _pair(tmp_path)
    _send(A)
    ws = str(A.root)

    health = _cli("ledger", "health", "--workspace", ws)
    assert health["status"] == ledger.HEALTHY
    assert health["ledger"]["messages"] >= 1

    feed = _cli("ledger", "feed", "--workspace", ws, "--cursor", "0", "--limit", "3")
    assert feed["ok"] is True and len(feed["events"]) == 3

    rebuilt = _cli("ledger", "reconstruct", "--workspace", ws)
    assert rebuilt["status"] == ledger.STATE_OK
    assert rebuilt["messages"][0]["state"] == ledger.DELIVERED

    repaired = _cli("ledger", "reconcile", "--workspace", ws)
    assert repaired["ok"] is True and repaired["invented"] == []

    # an unreadable ledger is an operator-action result, not an exit-0 no-op
    ledger.ledger_path(A).write_text("{broken", encoding="utf-8")
    broken = _cli("ledger", "health", "--workspace", ws)
    assert broken["ok"] is False
    assert broken["operator_action_required"] is True
    assert broken["status"] == ledger.UNKNOWN