"""spec/35: an agent cannot turn its own running commentary into operator mail.

The live incident is the fixture. One Work produced five letters in 41 minutes:
a tentative repair, a correction, a correction of the correction, a retraction and
a final hard stop. Prose etiquette already forbade that and did not stop it, so
every case below is a mechanical assertion on the receiver's admission, its
attention budget and its decision identity -- never on tone.
"""

from __future__ import annotations

import hashlib
import json
import threading

import pytest

from sailang.errors import SailangError
from saimail import human_attention as ha
from saimail import operator_interrupt as oi
from saimail import workspace

HUMAN = "human-id:sha256:" + "4c" * 32
OTHER_HUMAN = "human-id:sha256:" + "5d" * 32
NOW = "2026-10-01T10:00:00Z"
LATER = "2026-10-01T10:07:00Z"
DAY_LATER = "2026-10-02T10:07:00Z"

HARD_STOP = "SAIMASTER hard stopped.\nNeeded: resolve the SAIT-001 blocker."

# Every fail-closed way the receiver can decline to present. The queue keeps
# them apart for the operator surface; to this file they mean the same thing:
# nothing was interrupted.
SPENT = frozenset({ha.ATTENTION_BLOCKED, ha.DEFERRED, ha.ATTENTION_HALT_REQUIRED})


class Clock:
    """The receiver's own clock. Only receiver time may move a budget."""

    def __init__(self, value=NOW):
        self.value = value

    def __call__(self):
        return self.value

    def set(self, value):
        self.value = value


def envelope(tag):
    """A syntactically exact ENVELOPE_ID; only lowercase hex is a valid digest."""
    return "sha256:" + hashlib.sha256(str(tag).encode("utf-8")).hexdigest()


def receiver(tmp_path, *, human=HUMAN, clock=None, budget=None, root=None):
    return oi.Receiver(root or tmp_path, to_human=human, budget=budget,
                       clock=clock or Clock())


def stated(**overrides):
    fields = {"class_name": oi.OPERATOR_ACTION_REQUIRED, "decision_id": "sait-001",
              "work": "T-154", "body": HARD_STOP}
    fields.update(overrides)
    return oi.declaration(**fields)


def present_once(recv):
    """Reserve and acknowledge, the way an operator surface would."""
    reserved = recv.reserve()
    if reserved.get("reservation_id") is None:
        return reserved
    return recv.acknowledge(reserved["reservation_id"])


# --------------------------------------------------------------------
# the live SAIMASTER incident, replayed
# --------------------------------------------------------------------

def test_five_letters_from_one_work_present_at_most_one(tmp_path):
    """The reported incident, verbatim. Four unstable messages, one hard stop."""
    recv = receiver(tmp_path)
    chatter = [
        ("retirement command refused; try quarantine", "repair-try"),
        ("style_contract appears unfixable", "style-unfixable"),
        ("correction: write ded-71fc58de", "style-correction"),
        ("retract correction: do not write ded-71fc58de", "style-retraction"),
    ]
    for index, (body, decision_id) in enumerate(chatter):
        # Each was written mid-investigation, before the diagnosis had settled.
        admitted = recv.admit(envelope("1"), stated(
            decision_id=decision_id, body=body, settled=False))
        assert admitted["status"] == oi.UNSETTLED
        assert recv.reserve()["presented"] is False
        assert recv.status()["operator_unread"] == 0

    final = recv.admit(envelope("2"), stated(body=HARD_STOP))
    assert final["status"] == oi.ADMITTED
    shown = present_once(recv)
    assert shown["status"] == oi.PRESENTED

    assert recv.status()["operator_unread"] == 1
    # Nothing else in this period can reach the operator.
    assert recv.admit(envelope("3"), stated(decision_id="second", body="another"))["status"] \
        == oi.ADMITTED
    assert recv.reserve()["status"] in SPENT
    assert recv.status()["operator_unread"] == 1


def test_correction_chain_with_a_settled_decision_supersedes_and_presents_one(tmp_path):
    """A settled decision, corrected three times, still interrupts exactly once."""
    recv = receiver(tmp_path)
    for tag, body in (("a", "style marker is X"), ("b", "correction: marker is Y"),
                      ("c", "retract: marker should not change"),
                      ("d", "final: marker is Y, SAIMASTER stopped")):
        recv.admit(envelope(tag), stated(body=body))
    shown = present_once(recv)
    assert shown["status"] == oi.PRESENTED
    assert shown["body"] == "final: marker is Y, SAIMASTER stopped"
    assert recv.status()["operator_unread"] == 1
    assert recv.reserve()["status"] == ha.NO_MESSAGE


# --------------------------------------------------------------------
# eligibility: a closed class set, never a tone match
# --------------------------------------------------------------------

@pytest.mark.parametrize("class_name", sorted(oi.ELIGIBLE_CLASSES))
def test_only_the_three_declared_classes_exist(tmp_path, class_name):
    recv = receiver(tmp_path)
    admitted = recv.admit(envelope("a"), stated(class_name=class_name))
    assert admitted["status"] == oi.ADMITTED
    assert present_once(recv)["status"] == oi.PRESENTED


@pytest.mark.parametrize("body", [
    "T-154 finished; all 218 tests pass.",
    "Progress: 60% of the audit done.",
    "Test run: 41 passed, 1 skipped.",
    "Intermediate: the marker parser rejects the new token.",
    "FYI, the ded hash changed upstream.",
    "Next step suggestion: maybe try the other flag.",
])
def test_ordinary_agent_correspondence_never_becomes_an_interruption(tmp_path, body):
    """Cases 1-4 and the whole ineligible list: eligible class, wrong content.

    The content is not inspected anywhere in this path; what makes these
    ineligible is that the sender either never settled a single operator
    decision or never asked for one. Both leave durable transport behind.
    """
    recv = receiver(tmp_path)
    admitted = recv.admit(envelope("a"), stated(body=body, settled=False))
    assert admitted["status"] == oi.UNSETTLED
    assert recv.reserve()["status"] == ha.NO_MESSAGE
    assert recv.status()["operator_unread"] == 0


def test_an_invented_class_is_refused_before_anything_is_written(tmp_path):
    with pytest.raises(SailangError) as raised:
        oi.declaration(class_name="URGENT_MUST_READ", decision_id="d", work="T-1", body="x")
    assert raised.value.code == oi.INTERRUPT_BAD_CLASS
    assert receiver(tmp_path).status()["operator_unread"] == 0


def test_a_record_without_a_declaration_is_ordinary_transport(tmp_path):
    recv = receiver(tmp_path)
    from sailang import Record
    plain = Record.create(KIND="O", SRC="AGENT:saipen-cli", SUBJ="T-154",
                          CLAIM="T-154 finished; all 218 tests pass.",
                          TYPE="OBS", STATUS="U1", EV="0", CREATED=NOW)
    assert oi.parse_declaration(plain) is None
    assert recv.status()["operator_unread"] == 0


# --------------------------------------------------------------------
# one decision = one interruption
# --------------------------------------------------------------------

def test_exact_retry_is_idempotent(tmp_path):
    recv = receiver(tmp_path)
    first = recv.admit(envelope("a"), stated())
    assert first["status"] == oi.ADMITTED
    assert recv.admit(envelope("a"), stated())["status"] == oi.DUPLICATE_DECISION
    assert len(recv.entries()) == 1
    assert present_once(recv)["status"] == oi.PRESENTED


def test_reworded_same_decision_is_the_same_decision(tmp_path):
    """Wording, subject, trigger and envelope cannot buy a second interruption."""
    recv = receiver(tmp_path)
    recv.admit(envelope("a"), stated(body="SAIMASTER stopped. Please look at SAIT-001."))
    rewording = recv.admit(envelope("b"), stated(body="URGENT: SAIMASTER is stopped!"))
    assert rewording["status"] == oi.SUPERSEDED
    assert rewording["decision"] == first_decision(recv)
    assert present_once(recv)["status"] == oi.PRESENTED
    assert recv.admit(envelope("c"), stated(body="third wording"))["status"] == oi.ALREADY_PRESENTED
    assert recv.status()["operator_unread"] == 1


def first_decision(recv):
    return recv.entries()[0]["DECISION"]


def test_a_split_decision_cannot_beat_the_budget(tmp_path):
    """Splitting one decision into three issues buys one slot, not three."""
    recv = receiver(tmp_path)
    for index in range(3):
        recv.admit(envelope(chr(97 + index)), stated(decision_id=f"part-{index}"))
    presented = [present_once(recv)["status"] == oi.PRESENTED]
    assert presented == [True]
    assert recv.reserve()["status"] in SPENT
    assert recv.status()["operator_unread"] == 1


# --------------------------------------------------------------------
# receiver attention budget
# --------------------------------------------------------------------

def test_default_receiver_budget_is_one_presentation_per_period(tmp_path):
    recv = receiver(tmp_path)
    assert recv.budget.max_presentations == ha.DEFAULT_MAX_PRESENTATIONS == 1
    assert recv.budget.period_seconds == ha.DEFAULT_PERIOD_SECONDS == 86400
    recv.admit(envelope("a"), stated(decision_id="one"))
    recv.admit(envelope("b"), stated(decision_id="two"))
    assert present_once(recv)["status"] == oi.PRESENTED
    assert recv.reserve()["status"] in SPENT
    assert recv.status()["budget"]["consumed"] == 1


def test_receiver_max_presentations_zero_spends_nothing(tmp_path):
    recv = receiver(tmp_path, budget=ha.AttentionBudget(max_presentations=0))
    assert recv.admit(envelope("a"), stated())["status"] == oi.ADMITTED
    result = recv.reserve()
    assert result["status"] == ha.ATTENTION_BLOCKED
    assert result["presented"] is False
    assert recv.status()["operator_unread"] == 0
    assert recv.status()["pending"][0]["envelope_id"] == envelope("a")


def test_a_new_risk_stays_pending_when_the_budget_is_spent(tmp_path):
    """The critical exception: pending is allowed, extra presentations are not."""
    clock = Clock()
    recv = receiver(tmp_path, clock=clock)
    recv.admit(envelope("a"), stated())
    assert present_once(recv)["status"] == oi.PRESENTED
    recv.admit(envelope("b"), stated(class_name=oi.DATA_OR_MONEY_RISK, decision_id="risk"))
    result = recv.reserve()
    assert result["status"] == ha.ATTENTION_HALT_REQUIRED
    assert result["presented"] is False
    clock.set(DAY_LATER)
    assert present_once(recv)["status"] == oi.PRESENTED
    assert recv.status()["operator_unread"] == 2


def test_zero_presented_is_a_successful_outcome(tmp_path):
    recv = receiver(tmp_path, budget=ha.AttentionBudget(max_presentations=0))
    recv.admit(envelope("a"), stated(decision_id="quiet"))
    assert recv.reserve()["status"] == ha.ATTENTION_BLOCKED
    state = recv.status()
    assert state["operator_unread"] == 0
    assert state["pending"] and state["pending"][0]["work"] == "T-154"


def test_two_concurrent_presenters_cannot_both_spend_the_one_slot(tmp_path):
    recv = receiver(tmp_path)
    recv.admit(envelope("a"), stated())
    results = []
    barrier = threading.Barrier(2)

    def attempt():
        barrier.wait()
        results.append(recv.reserve())

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    reserved = [r for r in results if r["status"] == ha.RESERVED]
    assert len(reserved) == 1
    shown = recv.acknowledge(reserved[0]["reservation_id"])
    assert shown["status"] == oi.PRESENTED
    assert recv.status()["budget"]["consumed"] == 1


# --------------------------------------------------------------------
# transport existence is not presentation permission
# --------------------------------------------------------------------

def test_a_pending_decision_is_not_a_presented_one(tmp_path):
    recv = receiver(tmp_path)
    recv.admit(envelope("a"), stated())
    state = recv.status()
    assert len(state["pending"]) == 1
    assert state["presented"] == []
    assert state["operator_unread"] == 0
    assert state["budget"]["consumed"] == 0


def test_reserving_without_acknowledging_spends_nothing(tmp_path):
    recv = receiver(tmp_path)
    recv.admit(envelope("a"), stated())
    reserved = recv.reserve()
    assert reserved["status"] == ha.RESERVED
    assert recv.status()["operator_unread"] == 0
    recv.release(reserved["reservation_id"])
    assert recv.status()["pending"][0]["envelope_id"] == envelope("a")
    assert present_once(recv)["status"] == oi.PRESENTED


def test_restart_preserves_dedup_and_attention_consumption(tmp_path):
    clock = Clock()
    first = receiver(tmp_path, clock=clock)
    first.admit(envelope("a"), stated())
    assert present_once(first)["status"] == oi.PRESENTED

    # A fresh process rebuilds the whole receiver from durable files.
    restarted = receiver(tmp_path, clock=clock)
    assert restarted.status()["operator_unread"] == 1
    assert restarted.status()["budget"]["consumed"] == 1
    assert restarted.reserve()["status"] == ha.NO_MESSAGE
    assert restarted.admit(envelope("a"), stated())["status"] == oi.ALREADY_PRESENTED
    assert restarted.status()["operator_unread"] == 1


# --------------------------------------------------------------------
# the compact operator body
# --------------------------------------------------------------------

def test_an_oversized_operator_body_is_refused_before_presentation(tmp_path):
    recv = receiver(tmp_path)
    long_body = "full investigation report. " * 30
    with pytest.raises(SailangError) as raised:
        stated(body=long_body)
    assert raised.value.code == oi.OPERATOR_BODY_TOO_LARGE
    assert recv.status()["operator_unread"] == 0
    assert recv.reserve()["status"] == ha.NO_MESSAGE


def test_an_oversized_body_reaching_admission_is_also_refused(tmp_path):
    """A hand-built declaration is not a way around the size contract."""
    recv = receiver(tmp_path)
    forged = dict(stated(), body="x" * 601)
    with pytest.raises(SailangError) as raised:
        recv.admit(envelope("a"), forged)
    assert raised.value.code == oi.OPERATOR_BODY_TOO_LARGE
    assert recv.status()["operator_unread"] == 0


def test_too_many_lines_is_refused_even_when_short(tmp_path):
    with pytest.raises(SailangError) as raised:
        stated(body="one\ntwo\nthree\nfour\nfive")
    assert raised.value.code == oi.OPERATOR_BODY_TOO_LARGE


def test_a_compact_hard_stop_body_is_admitted_and_presented(tmp_path):
    recv = receiver(tmp_path)
    recv.admit(envelope("a"), stated(body=HARD_STOP))
    shown = present_once(recv)
    assert shown["status"] == oi.PRESENTED
    assert shown["body"] == HARD_STOP
    assert len(shown["body"].encode("utf-8")) <= oi.MAX_OPERATOR_BODY_BYTES
    assert len(recv.status()["presented"]) == 1


def test_the_visible_body_is_never_truncated(tmp_path):
    """Refusal is the contract; a shortened popup would be a different claim."""
    exact = stated(body="a" * oi.MAX_OPERATOR_BODY_BYTES)
    assert len(exact["body"]) == oi.MAX_OPERATOR_BODY_BYTES
    with pytest.raises(SailangError):
        stated(body="a" * (oi.MAX_OPERATOR_BODY_BYTES + 1))


# --------------------------------------------------------------------
# active chat and unknown presence
# --------------------------------------------------------------------

def test_active_chat_keeps_an_ordinary_action_request_in_the_chat(tmp_path):
    recv = receiver(tmp_path)
    admitted = recv.admit(envelope("a"), stated(), presence=oi.PRESENCE_ACTIVE_CHAT)
    assert admitted["status"] == oi.PRESENCE_CHAT_SUFFICIENT
    assert recv.reserve()["status"] == ha.NO_MESSAGE
    assert recv.status()["operator_unread"] == 0


def test_active_chat_still_admits_a_data_or_money_risk(tmp_path):
    recv = receiver(tmp_path)
    admitted = recv.admit(envelope("a"), stated(class_name=oi.DATA_OR_MONEY_RISK),
                          presence=oi.PRESENCE_ACTIVE_CHAT)
    assert admitted["status"] == oi.ADMITTED
    assert present_once(recv)["status"] == oi.PRESENTED


def test_unknown_presence_does_not_bypass_the_receiver_budget(tmp_path):
    """No trustworthy signal is not proof of absence, and not a free pass either."""
    clock = Clock()
    recv = receiver(tmp_path, clock=clock)
    assert oi.PRESENCE_UNKNOWN in oi.PRESENCE_STATES
    assert "ABSENT" not in oi.PRESENCE_STATES
    recv.admit(envelope("a"), stated(decision_id="one"), presence=oi.PRESENCE_UNKNOWN)
    assert present_once(recv)["status"] == oi.PRESENTED
    recv.admit(envelope("b"), stated(decision_id="two"), presence=oi.PRESENCE_UNKNOWN)
    assert recv.reserve()["status"] in SPENT
    assert recv.status()["operator_unread"] == 1


def test_presence_is_receiver_owned_context_and_validated(tmp_path):
    recv = receiver(tmp_path)
    for bad in ("ABSENT", "active_chat", "", None, "operator is busy"):
        with pytest.raises(SailangError) as raised:
            recv.admit(envelope("a"), stated(), presence=bad)
        assert raised.value.code == oi.INTERRUPT_BAD_PRESENCE


# --------------------------------------------------------------------
# backward compatibility and transport survival
# --------------------------------------------------------------------

def test_an_ordinary_human_send_never_reaches_the_interrupt_layer(tmp_path):
    """A person writing to another person is not an automated interruption."""
    a_root, b_root = tmp_path / "ws-a", tmp_path / "ws-b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    a = workspace.load_workspace(a_root)
    b = workspace.load_workspace(b_root)
    # Both directions, exactly like a real pair: the receiving Post Office must
    # know the sender's key before the envelope is not quarantined.
    workspace.add_recipient(a, "bob", workspace.identity_card(b), b_root)
    workspace.add_recipient(b, "alice", workspace.identity_card(a), a_root)

    sent = workspace.send_message(a, "bob", claim="lunch at one?")
    assert sent["status"] == "ACCEPTED"
    listing = workspace.list_inbox(workspace.load_workspace(b_root))
    assert any(item["from"] == "SAIMAIL-A" for item in listing["items"])

    recv = oi.Receiver(b_root, to_human=oi.human_id(workspace.load_workspace_headers(b_root)))
    assert recv.status()["operator_unread"] == 0
    assert recv.status()["pending"] == []


def test_agent_to_agent_transport_still_delivers_with_a_declaration_attached(tmp_path):
    """The gate gates attention, not transport: the message still lands."""
    a_root, b_root = tmp_path / "ws-a", tmp_path / "ws-b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    a = workspace.load_workspace(a_root)
    b = workspace.load_workspace(b_root)
    workspace.add_recipient(a, "bob", workspace.identity_card(b), b_root)
    workspace.add_recipient(b, "alice", workspace.identity_card(a), a_root)

    record = oi.declaration_record(seat=a.seat, class_name=oi.OPERATOR_ACTION_REQUIRED,
                                   decision_id="sait-001", work="T-154", body=HARD_STOP)
    path = tmp_path / "interrupt.sail"
    path.write_bytes(record.canonical_bytes())
    sent = workspace.send_message(a, "bob", record_path=path, subject="T-154", topic="T-154")
    assert sent["status"] == "ACCEPTED"

    receiver_workspace = workspace.load_workspace(b_root)
    opened = workspace.open_message(receiver_workspace, sent["message"]["envelope_id"])
    # Exactly what `saimail-local open --json` hands a receiver.
    parsed = oi.parse_declaration(opened["record"])
    assert parsed["decision_id"] == "sait-001"
    assert parsed["class"] == oi.OPERATOR_ACTION_REQUIRED

    recv = oi.Receiver(b_root, to_human=oi.human_id(workspace.load_workspace_headers(b_root)))
    assert recv.admit(sent["message"]["envelope_id"], parsed)["status"] == oi.ADMITTED
    assert present_once(recv)["status"] == oi.PRESENTED
    assert recv.status()["operator_unread"] == 1


def test_the_receiver_human_identity_is_derived_not_declared(tmp_path):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    headers = workspace.load_workspace_headers(root)
    identity = oi.human_id(headers)
    assert identity.startswith("human-id:sha256:")
    assert identity == oi.human_id(headers)
    other = oi.Receiver(root, to_human=identity)
    assert other.status()["to_human"] == identity
    with pytest.raises(SailangError):
        oi.Receiver(root, to_human="operator")


# --------------------------------------------------------------------
# integrity: the ledger and the declaration are checked, never trusted
# --------------------------------------------------------------------

def test_a_tampered_ledger_entry_fails_closed(tmp_path):
    recv = receiver(tmp_path)
    recv.admit(envelope("a"), stated())
    path = recv._entry_path(recv.entries()[0]["DECISION"])
    path.write_text(json.dumps({**json.loads(path.read_text()), "STATE": "PENDING",
                                "BODY": "trust me"}), encoding="utf-8")
    with pytest.raises(SailangError) as raised:
        recv.status()
    assert raised.value.code == oi.INTERRUPT_LEDGER_CORRUPT


def test_a_declaration_with_an_extra_field_is_refused():
    from sailang import Record
    record = oi.declaration_record(seat="agent", class_name=oi.OPERATOR_ACTION_REQUIRED,
                                   decision_id="d", work="T-1", body="x")
    payload = json.loads(record.claim)
    payload["urgency"] = "MAXIMUM"
    forged = Record.create(KIND="O", SRC=record.get("SRC"), SUBJ=record.get("SUBJ"),
                           CLAIM=json.dumps(payload), TYPE="OBS", STATUS="U1",
                           EV="0", CREATED=NOW)
    with pytest.raises(SailangError) as raised:
        oi.parse_declaration(forged)
    assert raised.value.code == oi.INTERRUPT_MALFORMED


def test_a_declaration_cannot_name_its_own_priority_or_presence():
    """No field exists to fill, so there is nothing to fill it with."""
    assert set(oi.declaration(class_name=oi.OPERATOR_ACTION_REQUIRED, decision_id="d",
                              work="T-1", body="x")) == {
        "schema", "class", "decision_id", "work", "settled", "body"}


def test_a_restricted_decision_id_is_refused():
    for bad in ("", "a" * 97, "../escape", "has space", "semi;colon"):
        with pytest.raises(SailangError) as raised:
            oi.declaration(class_name=oi.OPERATOR_ACTION_REQUIRED, decision_id=bad,
                           work="T-1", body="x")
        assert raised.value.code == oi.INTERRUPT_BAD_DECISION_ID


# --------------------------------------------------------------------
# the shipped CLI surface
# --------------------------------------------------------------------

def _cli(capsys, *argv):
    """One `saimail-local` invocation, exactly as a host would run it."""
    import saimail_local

    code = saimail_local.main([*argv, "--json"])
    captured = capsys.readouterr().out
    return code, json.loads(captured)


def _cli_letter(site, tmp_path, tag, **kwargs):
    record = oi.declaration_record(seat=site["a"].seat,
                                   class_name=kwargs.pop("class_name", oi.OPERATOR_ACTION_REQUIRED),
                                   decision_id=kwargs.pop("decision_id", "sait-001"),
                                   work=kwargs.pop("work", "T-154"), **kwargs)
    path = tmp_path / f"{tag}.sail"
    path.write_bytes(record.canonical_bytes())
    sent = workspace.send_message(site["a"], "bob", record_path=path,
                                  subject="T-154", topic="T-154")
    return path, sent["message"]["envelope_id"]


def test_the_cli_replays_the_incident_without_a_burst(tmp_path, capsys):
    """The five letters, driven through the shipped command surface."""
    a_root, b_root = tmp_path / "ws-a", tmp_path / "ws-b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    a = workspace.load_workspace(a_root)
    b = workspace.load_workspace(b_root)
    workspace.add_recipient(a, "bob", workspace.identity_card(b), b_root)
    workspace.add_recipient(b, "alice", workspace.identity_card(a), a_root)
    site = {"a": a, "b": b, "a_root": a_root, "b_root": b_root}

    for index, (tag, body) in enumerate([
            ("u1", "style_contract appears unfixable"),
            ("u2", "correction: write ded-71fc58de"),
            ("u3", "retract correction: do not write ded-71fc58de")]):
        path, envelope = _cli_letter(site, tmp_path, tag, body=body, settled=False)
        code, out = _cli(capsys, "interrupt", "admit", "--workspace", str(b_root),
                         "--envelope", envelope, "--declaration", str(path))
        assert code == 0 and out["status"] == oi.UNSETTLED

    path, envelope = _cli_letter(site, tmp_path, "final", body=HARD_STOP)
    code, out = _cli(capsys, "interrupt", "admit", "--workspace", str(b_root),
                     "--envelope", envelope, "--declaration", str(path))
    assert code == 0 and out["status"] == oi.ADMITTED

    code, out = _cli(capsys, "interrupt", "present", "--workspace", str(b_root))
    assert code == 0 and out["status"] == "RESERVED"
    assert out["body"] == HARD_STOP

    # The acknowledging call is a different invocation from the reserving one.
    code, out = _cli(capsys, "interrupt", "present", "--workspace", str(b_root), "--ack")
    assert code == 0 and out["status"] == oi.PRESENTED

    code, out = _cli(capsys, "interrupt", "present", "--workspace", str(b_root))
    assert code == 0 and out["status"] == "NO_MESSAGE"

    code, out = _cli(capsys, "interrupt", "status", "--workspace", str(b_root))
    state = out["operator_interrupts"]
    assert state["operator_unread"] == 1
    assert state["budget"]["consumed"] == 1
    assert state["budget"]["available"] == 0


def test_the_cli_refuses_an_oversized_body_with_a_nonzero_exit(tmp_path, capsys):
    a_root, b_root = tmp_path / "ws-a", tmp_path / "ws-b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    a = workspace.load_workspace(a_root)
    b = workspace.load_workspace(b_root)
    workspace.add_recipient(a, "bob", workspace.identity_card(b), b_root)
    workspace.add_recipient(b, "alice", workspace.identity_card(a), a_root)

    code, out = _cli(capsys, "send", "--workspace", str(a_root), "--to", "bob",
                     "--interrupt-class", oi.OPERATOR_ACTION_REQUIRED,
                     "--decision-id", "sait-001", "--work", "T-154",
                     "--body", "a full forensic report. " * 40)
    assert code != 0
    assert out["status"] == oi.OPERATOR_BODY_TOO_LARGE
    assert out["ok"] is False

    # Nothing was sealed: an oversized request never becomes mail.
    listing = workspace.list_inbox(workspace.load_workspace_headers(b_root))
    assert listing["items"] == []


def test_a_plain_human_send_is_unchanged_by_the_new_flags(tmp_path, capsys):
    a_root, b_root = tmp_path / "ws-a", tmp_path / "ws-b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    a = workspace.load_workspace(a_root)
    b = workspace.load_workspace(b_root)
    workspace.add_recipient(a, "bob", workspace.identity_card(b), b_root)
    workspace.add_recipient(b, "alice", workspace.identity_card(a), a_root)

    code, out = _cli(capsys, "send", "--workspace", str(a_root), "--to", "bob",
                     "--claim", "release build is green, tagging now")
    assert code == 0 and out["status"] == "ACCEPTED"
    code, state = _cli(capsys, "interrupt", "status", "--workspace", str(b_root))
    assert state["operator_interrupts"]["operator_unread"] == 0
    assert state["operator_interrupts"]["pending"] == []


def test_a_reservation_survives_to_the_next_process_and_can_be_acked(tmp_path):
    """A presentation is reserved and acknowledged by different invocations."""
    first = receiver(tmp_path)
    first.admit(envelope("a"), stated())
    reserved = first.reserve()
    reservation_id = reserved["reservation_id"]

    # A fresh process: only the receiver's own ledger knows what is outstanding.
    restarted = receiver(tmp_path)
    assert restarted.outstanding() == [reservation_id]
    assert restarted.status()["operator_unread"] == 0
    assert restarted.acknowledge(reservation_id)["status"] == oi.PRESENTED
    assert restarted.outstanding() == []
    assert restarted.status()["operator_unread"] == 1


def test_releasing_a_reservation_clears_the_outstanding_pointer(tmp_path):
    recv = receiver(tmp_path)
    recv.admit(envelope("a"), stated())
    reservation_id = recv.reserve()["reservation_id"]
    assert recv.outstanding() == [reservation_id]
    recv.release(reservation_id)
    assert recv.outstanding() == []
    assert recv.status()["pending"][0]["envelope_id"] == envelope("a")
    assert present_once(recv)["status"] == oi.PRESENTED


def test_a_superseded_pending_decision_keeps_no_stale_unread(tmp_path):
    """Replacing a pending letter must not leave two debts behind."""
    recv = receiver(tmp_path)
    recv.admit(envelope("a"), stated(body="draft wording"))
    recv.admit(envelope("b"), stated(body="final wording"))
    assert len(recv.status()["pending"]) == 1
    assert recv.outstanding() == []
    assert present_once(recv)["status"] == oi.PRESENTED
    assert recv.status()["operator_unread"] == 1


# --------------------------------------------------------------------
# review findings: each of these was exploitable before its fix
# --------------------------------------------------------------------

def test_reclassifying_one_decision_is_refused_before_anything_is_written(tmp_path):
    """A sender cannot buy a second slot by relabelling one decision."""
    recv = receiver(tmp_path)
    assert recv.admit(envelope("a"), stated(
        class_name=oi.CROSS_PROJECT_CRITICAL_DISCOVERY))["status"] == oi.ADMITTED
    before = recv.entries()
    with pytest.raises(SailangError) as raised:
        recv.admit(envelope("b"), stated(class_name=oi.DATA_OR_MONEY_RISK))
    assert raised.value.code == oi.INTERRUPT_BAD_CLASS
    # The ledger and the scheduler must not be left disagreeing about a class.
    assert recv.entries() == before
    assert recv.entries()[0]["CLASS"] == oi.CROSS_PROJECT_CRITICAL_DISCOVERY


def test_a_trailing_newline_cannot_mint_a_second_decision_for_one_work(tmp_path):
    """`T-154\n` is the same Work, not a new one with a fresh budget slot."""
    recv = receiver(tmp_path)
    recv.admit(envelope("a"), stated())
    with pytest.raises(SailangError) as raised:
        recv.admit(envelope("b"), stated(work="T-154\n"))
    assert raised.value.code == oi.INTERRUPT_BAD_WORK
    assert len(recv.entries()) == 1


def test_a_repeated_json_key_is_refused_rather_than_last_one_winning(tmp_path):
    """Another reader could resolve the duplicate the other way."""
    from sailang import Record
    doubled = ('{"schema":"SAIMAIL_OPERATOR_INTERRUPT_1",'
               '"class":"CROSS_PROJECT_CRITICAL_DISCOVERY",'
               '"class":"DATA_OR_MONEY_RISK","decision_id":"d","work":"T-1",'
               '"settled":true,"body":"x"}')
    record = Record.create(KIND="O", SRC="AGENT:x", SUBJ="T-1", CLAIM=doubled,
                          TYPE="OBS", STATUS="U1", EV="0", CREATED=NOW)
    with pytest.raises(SailangError) as raised:
        oi.parse_declaration(record)
    assert raised.value.code == oi.INTERRUPT_MALFORMED


def test_a_whitespace_only_body_is_refused_not_shown_as_an_empty_popup(tmp_path):
    # An empty body is malformed, not oversized: nothing was written, so there is
    # nothing for the size contract to have refused.
    with pytest.raises(SailangError) as raised:
        oi.declaration(class_name=oi.OPERATOR_ACTION_REQUIRED, decision_id="d",
                       work="T-1", body="\n\n\n   \n")
    assert raised.value.code == oi.INTERRUPT_MALFORMED


def test_a_crash_between_enqueue_and_ledger_leaves_a_self_healing_state(tmp_path):
    """The recovery direction matters: a candidate without a ledger entry heals."""
    recv = receiver(tmp_path)
    recv.admit(envelope("a"), stated())
    # Simulate the crash window: the candidate exists, the ledger entry does not.
    path = recv._entry_path(recv.entries()[0]["DECISION"])
    path.unlink()
    assert recv.reserve()["status"] == oi.NOTHING_PENDING

    # An exact retry re-enqueues and writes the entry, so the decision returns.
    assert recv.admit(envelope("a"), stated())["status"] == oi.ADMITTED
    assert present_once(recv)["status"] == oi.PRESENTED
    assert recv.status()["operator_unread"] == 1


def test_the_pending_set_never_evicts_a_decision_it_already_owns(tmp_path):
    """Evicting would strand a queue candidate the queue cannot retire.

    So the cap is a door, not a ranking: at the cap every class is refused, and
    the eight that are in stay presentable one after another.
    """
    clock = Clock()
    recv = receiver(tmp_path, clock=clock)
    for index in range(oi.MAX_PENDING_DECISIONS):
        recv.admit(envelope(chr(97 + index)),
                   stated(decision_id=f"discovery-{index}",
                          class_name=oi.CROSS_PROJECT_CRITICAL_DISCOVERY,
                          body="cross-project discovery"))
    assert len(recv.status()["pending"]) == oi.MAX_PENDING_DECISIONS

    with pytest.raises(SailangError) as raised:
        recv.admit(envelope("z"), stated(decision_id="real-stop"))
    assert raised.value.code == oi.PENDING_FULL

    # No ghost: every candidate the queue holds still names a live decision, so
    # each reservation finds one to show instead of an empty popup. One budget
    # period elapses between presentations, so the default cap of one per day is
    # the only thing pacing this.
    for day in range(1, oi.MAX_PENDING_DECISIONS + 1):
        clock.set(f"2026-10-{day + 1:02d}T10:00:00Z")
        shown = present_once(recv)
        assert shown["status"] == oi.PRESENTED
        assert shown["body"]
    assert recv.status()["pending"] == []


def test_a_weak_decision_is_refused_once_the_pending_set_is_full(tmp_path):
    recv = receiver(tmp_path)
    for index in range(oi.MAX_PENDING_DECISIONS):
        recv.admit(envelope(chr(97 + index)), stated(decision_id=f"d{index}"))
    with pytest.raises(SailangError) as raised:
        recv.admit(envelope("z"), stated(decision_id="one-more"))
    assert raised.value.code == oi.PENDING_FULL
    # Refused, not lost: the message is still durable mail for the operator.
    assert len(recv.status()["pending"]) == oi.MAX_PENDING_DECISIONS
