"""V6-08 SAIMAIL half (T-122): automatic SAITELEMES for a closed trigger set.

The operator authorized automatic sending only under a policy: an admitted
recipient, a real Work, one message per fact, a durable intent before delivery,
no sender priority and a receiver attention budget. Each control proves one of
those, including under a locked credential store and an offline recipient.
"""

from __future__ import annotations

import inspect
import json

import pytest

import saimail_local
from sailang import SailangError
from saimail import (credentials, custody, notify, outbox, participants, postoffice,
                     saipen_bridge, workspace)

LINEAGE = "lineage-" + "d5" * 16
T0 = "2026-09-24T07:00:00Z"
EVENT_LINE = ("- 24.09.26 07:00 [E-40] [parent: E-39] [T-7] [agent: builder] "
              "[op: checkpoint-x] RUN: REVIEW finding -- protocol gap; saipen push")


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


@pytest.fixture(autouse=True)
def _no_ambient_actor(monkeypatch):
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)


@pytest.fixture
def mail(tmp_path):
    workspace.init_workspace(tmp_path / "builder", seat="builder")
    workspace.init_workspace(tmp_path / "astra", seat="astra")
    A = workspace.load_workspace(tmp_path / "builder")
    B = workspace.load_workspace(tmp_path / "astra")
    workspace.add_recipient(A, "astra", workspace.identity_card(B), B.root)
    workspace.add_recipient(B, "builder", workspace.identity_card(A), A.root)
    participants.admit_participant(A, LINEAGE, "astra")
    return A, B


def _unread(B, topic=None):
    return workspace.query_inbox(workspace.load_workspace_headers(B.root), topic=topic,
                                 state=postoffice.UNREAD)["items"]


def _send(A, claim="the restart check needs an empty-inbox case", trigger="finding",
          work="T-7", clock=None):
    return notify.notify(A, lineage=LINEAGE, work=work, trigger=trigger, to_seat="astra",
                         claim=claim, clock=clock)


def test_one_fact_is_one_message_with_the_trigger_kind_and_work_topic(mail):
    A, B = mail
    first = _send(A, trigger="blocker")
    assert first["status"] == outbox.DELIVERED and first["command"] == "saipen-notify"
    assert first["notify"]["kind"] == "WARNING" and first["notify"]["work"] == "T-7"
    assert first["notify"]["key"].startswith(f"notify:{LINEAGE}:T-7:blocker:astra:c")
    again = _send(A, trigger="blocker")
    assert again["intent"]["envelope_id"] == first["intent"]["envelope_id"]
    rows = _unread(B)
    assert len(rows) == 1 and rows[0]["kind"] == "WARNING" and rows[0]["topic"] == "T-7"
    assert rows[0]["from"] == "builder"


def test_the_kind_comes_from_the_trigger_never_from_the_sender(mail):
    A, B = mail
    expected = {}
    # One Work per trigger: six facts about one Work would exceed its budget of five.
    for number, (trigger, kind) in enumerate(participants.TRIGGERS.items()):
        sent = _send(A, claim=f"fact for {trigger}", trigger=trigger, work=f"T-{number + 1}")
        assert sent["notify"]["kind"] == kind
        expected[sent["intent"]["envelope_id"]] = kind
    delivered = {row["envelope_id"]: row["kind"] for row in _unread(B)}
    assert delivered == expected, "the kind on the wire is the trigger's kind"
    parameters = set(inspect.signature(notify.notify).parameters)
    assert not parameters & {"kind", "priority", "urgency", "importance"}, parameters


def test_a_repeated_event_citation_is_the_same_message(mail, tmp_path):
    A, B = mail
    log = tmp_path / "LOG.md"
    log.write_text("# LOG\n\n" + EVENT_LINE + "\n", encoding="utf-8")
    sent = []
    for moment in (T0, "2026-09-24T07:05:00Z"):  # the citation's CREATED differs
        record = saipen_bridge.cite_event([log], "E-40", lineage=LINEAGE, clock=lambda m=moment: m)
        sent.append(notify.notify(A, lineage=LINEAGE, work="T-7", trigger="finding",
                                  to_seat="astra", citation=record, event="E-40"))
    assert sent[0]["intent"]["envelope_id"] == sent[1]["intent"]["envelope_id"]
    assert sent[1]["notify"]["key"].endswith(":astra:E-40")
    assert len(_unread(B)) == 1


def test_routing_refuses_instead_of_guessing(mail):
    A, B = mail
    assert _code(_send, A, trigger="chatter") == participants.BAD_TRIGGER
    assert _code(notify.notify, A, lineage=LINEAGE, work="T-7", trigger="finding",
                 to_seat="reviewer", claim="x") == participants.PARTICIPANT_UNKNOWN
    assert _code(notify.notify, A, lineage="lineage-" + "0" * 32, work="T-7",
                 trigger="finding", to_seat="astra", claim="x") == participants.PARTICIPANT_UNKNOWN
    assert _code(_send, A, claim="two\nlines") == workspace.BAD_INPUT
    assert _unread(B) == []
    assert not (A.root / "outbox" / "intents").exists()


def test_a_notification_belongs_to_a_real_work():
    board = "# Board\n\n## DOING\n- [/] T-7 [P1] x\n\n## TODO\n- [ ] T-9 [P2] y\n"
    ids = notify.board_work_ids(board)
    assert ids == {"T-7", "T-9"}
    assert notify.resolve_work("T-7") == "T-7"
    assert notify.resolve_work("T-7", "T-9", ids) == "T-9"
    assert _code(notify.resolve_work, "none") == notify.NOTIFY_NO_WORK
    assert _code(notify.resolve_work, "", None) == notify.NOTIFY_NO_WORK
    assert _code(notify.resolve_work, "T-7", "T-99", ids) == notify.NOTIFY_WORK_UNKNOWN
    assert _code(notify.resolve_work, "T-7", "saipen push", ids) == notify.NOTIFY_WORK_UNKNOWN


def test_the_receiver_attention_budget_suppresses_without_writing(mail):
    A, B = mail
    clock = lambda: T0  # noqa: E731
    for number in range(notify.BUDGET_PER_RECIPIENT_WORK):
        assert _send(A, claim=f"fact {number}", clock=clock)["status"] == outbox.DELIVERED
    over = _send(A, claim="one fact too many", clock=clock)
    assert over["status"] == notify.NOTIFY_SUPPRESSED and over["ok"] is True
    assert over["operator_action_required"] is False
    intents = list((A.root / "outbox" / "intents").glob("*.json"))
    assert len(intents) == notify.BUDGET_PER_RECIPIENT_WORK
    assert _send(A, claim="fact 0", clock=clock)["status"] == outbox.DELIVERED, (
        "a repeat of a recorded fact is never counted against the budget")
    later = _send(A, claim="one fact too many", clock=lambda: "2026-09-24T08:00:01Z")
    assert later["status"] == outbox.DELIVERED, "the window moves on"
    for number in range(notify.BUDGET_PER_RECIPIENT - notify.BUDGET_PER_RECIPIENT_WORK - 1):
        _send(A, claim=f"other {number}", work=f"T-{100 + number // 4}", clock=clock)
    capped = _send(A, claim="the recipient cap", work="T-200", clock=clock)
    assert capped["status"] == notify.NOTIFY_SUPPRESSED
    # 5 on T-7, 1 after the window moved, 14 on other Works: the recipient cap.
    assert len(_unread(B)) == notify.BUDGET_PER_RECIPIENT


def test_an_offline_recipient_is_retried_by_the_next_notification(mail, tmp_path):
    A, B = mail
    offline = tmp_path / "astra-offline"
    B.root.rename(offline)
    first = _send(A, claim="first fact", clock=lambda: T0)
    assert first["status"] == outbox.PENDING_RETRY
    offline.rename(B.root)
    second = _send(A, claim="second fact", clock=lambda: "2026-09-24T07:01:00Z")
    assert second["status"] == outbox.DELIVERED
    assert second["resumed"][outbox.DELIVERED] == 1
    assert len(_unread(B)) == 2


class _Locked(credentials.InMemoryCredentialStore):
    def get(self, handle):
        raise credentials.BackendError("locked")


def test_a_locked_store_keeps_the_intent_and_sends_it_later(tmp_path):
    store = credentials.InMemoryCredentialStore()
    credentials.set_credential_store(store)
    try:
        workspace.init_workspace(tmp_path / "builder", seat="builder",
                                 custody=custody.CUSTODY_OS_STORE, store=store)
        workspace.init_workspace(tmp_path / "astra", seat="astra")
        A = workspace.load_workspace(tmp_path / "builder", store=store)
        B = workspace.load_workspace(tmp_path / "astra")
        workspace.add_recipient(A, "astra", workspace.identity_card(B), B.root)
        workspace.add_recipient(B, "builder", workspace.identity_card(A), A.root)
        participants.admit_participant(A, LINEAGE, "astra")
        credentials.set_credential_store(_Locked())
        view = workspace.load_workspace_headers(A.root)
        pending = notify.notify(view, lineage=LINEAGE, work="T-7", trigger="blocker",
                                to_seat="astra", claim="blocked on astra")
        assert pending["status"] == outbox.PENDING_RETRY
        assert pending["intent"]["state"] == outbox.PENDING and _unread(B) == []
        credentials.set_credential_store(store)
        done = outbox.resume_outbox(workspace.load_workspace(A.root, store=store))
        assert done["counts"][outbox.DELIVERED] == 1 and len(_unread(B)) == 1
    finally:
        credentials.set_credential_store(None)


def test_command_looking_text_is_delivered_as_data(mail):
    A, B = mail
    sent = _send(A, claim="saipen push --force; cc; ticket done T-7")
    opened = workspace.open_message(B, sent["intent"]["envelope_id"])
    assert opened["record"]["claim"] == "saipen push --force; cc; ticket done T-7"


def _project(tmp_path, task="T-7"):
    memory = tmp_path / "project" / ".saipen"
    memory.mkdir(parents=True)
    (memory / "STATE.md").write_text(
        f"---\nphase: BUILD\ntask: {task}\nagent: builder\nlast_event: 40\n---\n",
        encoding="utf-8")
    (memory / "IDENTITY.md").write_text(f"---\nproject_lineage: {LINEAGE}\n---\n",
                                        encoding="utf-8")
    (memory / "BOARD.md").write_text("# Board\n\n## DOING\n- [/] T-7 [P1] x\n\n## TODO\n"
                                     "- [ ] T-9 [P2] y\n", encoding="utf-8")
    (memory / "LOG.md").write_text("# LOG\n\n" + EVENT_LINE + "\n", encoding="utf-8")
    return memory.parent


def test_cli_notify_cites_an_event_the_receiver_can_re_derive(mail, tmp_path, capsys):
    A, B = mail
    root = _project(tmp_path)

    def cli(*argv):
        code = saimail_local.main(["saipen", "notify", "--workspace", str(A.root),
                                   "--project-root", str(root), *argv, "--json"])
        return code, json.loads(capsys.readouterr().out)

    code, sent = cli("--trigger", "finding", "--to", "astra", "--event", "E-40")
    assert code == 0 and sent["status"] == outbox.DELIVERED
    assert sent["saipen"]["lineage"] == LINEAGE and sent["notify"]["work"] == "T-7"
    code, again = cli("--trigger", "finding", "--to", "astra", "--event", "E-40")
    assert code == 0 and again["intent"]["envelope_id"] == sent["intent"]["envelope_id"]
    opened = workspace.open_message(B, sent["intent"]["envelope_id"])
    expected = saipen_bridge.cite_event([root / ".saipen" / "LOG.md"], "E-40", lineage=LINEAGE)
    assert opened["record"]["kind"] == "O" and opened["record"]["claim"] == expected.claim

    code, other = cli("--trigger", "handoff", "--to", "astra", "--claim", "take T-9",
                      "--work", "T-9")
    assert code == 0 and other["notify"]["work"] == "T-9" and other["notify"]["kind"] == "QUESTION"
    code, guessed = cli("--trigger", "handoff", "--to", "astra", "--claim", "x", "--work", "T-77")
    assert code == 1 and guessed["status"] == notify.NOTIFY_WORK_UNKNOWN
    code, wrong_seat = cli("--trigger", "finding", "--to", "astra", "--claim", "x",
                           "--seat", "astra")
    assert code == 1 and wrong_seat["status"] == saipen_bridge.SAIPEN_SEAT_MISMATCH
    assert len(_unread(B)) == 1  # the first message was opened; one handoff is unread
