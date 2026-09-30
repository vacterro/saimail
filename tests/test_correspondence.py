"""Useful correspondence survives sessions, closes its loop, and stays inert."""

from __future__ import annotations

import copy
import json
import sqlite3

import pytest

import saimail_local
from sailang import SailangError
from saimail import correspondence as co
from saimail import letters, outbox, participants, workspace
from saimail_host import HostClient

LINEAGE = "lineage-" + "ab" * 16
NOW = "2026-09-30T10:00:00Z"
CLOCK = lambda: NOW


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)
    root = tmp_path / "project"
    memory = root / ".saipen"
    memory.mkdir(parents=True)
    (memory / "STATE.md").write_text("---\nphase: BUILD\ntask: T-7\nagent: builder\nlast_event: 40\n---\n", encoding="utf-8")
    (memory / "IDENTITY.md").write_text(f"---\nproject_lineage: {LINEAGE}\n---\n", encoding="utf-8")
    (memory / "BOARD.md").write_text(
        "## DOING\n- [/] T-7 [P1] producer | owner: builder\n"
        "- [/] T-9 [P1] consumer | owner: reviewer\n## TODO\n- [ ] T-12 [P2] next generation\n",
        encoding="utf-8")
    (memory / "LOG.md").write_text("# LOG\n", encoding="utf-8")
    (root / "failure.txt").write_text("Empty inbox leaves the continuation cursor stuck.\n", encoding="utf-8")
    (root / "result.txt").write_text("Empty-inbox recovery passes after fix.\n", encoding="utf-8")
    boxes = []
    for seat in ("builder", "reviewer"):
        workspace.init_workspace(tmp_path / seat, seat=seat, clock=CLOCK)
        boxes.append(workspace.load_workspace(tmp_path / seat))
    a, b = boxes
    workspace.add_recipient(a, "reviewer", workspace.identity_card(b), b.root)
    workspace.add_recipient(b, "builder", workspace.identity_card(a), a.root)
    participants.admit_participant(a, LINEAGE, "reviewer", clock=CLOCK)
    participants.admit_participant(b, LINEAGE, "builder", clock=CLOCK)
    letter = letters.template(LINEAGE, "T-7", "T-9", issue="empty-inbox-recovery", clock=CLOCK)
    letter.update(observation="Empty inboxes get a non-advancing recovery cursor.",
                  impact="T-9 cannot safely reuse the cursor after a receiver restart.",
                  request="Check and correct empty-inbox continuation before adopting this adapter.",
                  done_when="A restarted receiver reaches an empty-inbox completion without a repeat.",
                  uncertainty="The attached reproduction is local; other platforms are untested.",
                  evidence=[letters.evidence_ref(root, "failure.txt")], scope=["saimail/inbox_query.py"])
    return a, b, root, letter


def send(setup, **changes):
    a, _, root, letter = setup
    value = copy.deepcopy(letter)
    value.update(changes)
    return co.dispatch(a, value, lineage=LINEAGE, sender_work="T-7", to_seat="reviewer",
                       project_root=root, clock=CLOCK)


def review(setup, envelope_id):
    _, b, root, _ = setup
    return co.review(b, envelope_id, lineage=LINEAGE, project_root=root, clock=CLOCK)


def test_shared_mailbox_same_work_isolated_by_lineage_on_every_page(setup):
    a, b, root, letter = setup
    foreign = "lineage-" + "cd" * 16
    participants.admit_participant(a, foreign, "reviewer", clock=CLOCK)
    expected = send(setup)["intent"]["envelope_id"]
    other = copy.deepcopy(letter)
    other.update(lineage=foreign, issue="foreign-project")
    forbidden = co.dispatch(a, other, lineage=foreign, sender_work="T-7", to_seat="reviewer",
                            project_root=root, clock=CLOCK)["intent"]["envelope_id"]
    headers = workspace.load_workspace_headers(b.root)
    found = []
    continuation = None
    for _ in range(10):
        page = co.desk(headers, lineage=LINEAGE, work="T-9", budget=1,
                       continuation=continuation, clock=CLOCK)
        found.extend(row["envelope_id"] for row in page["items"])
        continuation = page["continuation"]
        if continuation is None:
            break
    assert forbidden not in found
    assert found == [expected]


def decide(setup, envelope_id, decision="RESOLVED", reason="ACTION_TAKEN", **kwargs):
    _, b, root, _ = setup
    return co.decide(b, envelope_id, lineage=LINEAGE, project_root=root, decision=decision,
                     reason=reason, clock=CLOCK, **kwargs)


def test_full_generation_cycle_routes_to_recipient_work_and_returns_result(setup):
    a, b, root, letter = setup
    sent = send(setup)
    eid = sent["intent"]["envelope_id"]
    assert sent["status"] == outbox.DELIVERED
    assert sent["notify"]["content_contract"] == letters.SCHEMA
    assert workspace.query_inbox(workspace.load_workspace_headers(b.root), topic=letters.topic(LINEAGE, "T-9"))["match_count"] == 1
    assert workspace.query_inbox(workspace.load_workspace_headers(b.root), topic=letters.topic(LINEAGE, "T-7"))["match_count"] == 0
    opened = review(setup, eid)
    assert opened["letter"] == letter and opened["evidence_current"]
    assert opened["case"]["decision"] == "PENDING", "reading is not doing"
    # A correction may change the original reproduction; result evidence is
    # the proof of resolution, not continued existence of the old failure.
    (root / "failure.txt").write_text("Now fixed.\n", encoding="utf-8")
    proof = [letters.evidence_ref(root, "result.txt")]
    resolved = decide(setup, eid, evidence=proof)
    assert resolved["case"]["decision"] == "RESOLVED"
    co.retain(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    # Simulate a successor with no in-process memory.
    replacement = workspace.load_workspace_headers(b.root)
    desk = co.desk(replacement, lineage=LINEAGE, work="T-12", scope=letter["scope"], clock=CLOCK)
    assert len(desk["cases"]) == 1 and desk["cases"][0]["match"] == "SUCCESSOR_RESERVE"
    assert not desk["cases"][0]["actionable"]
    reply = co.report(workspace.load_workspace(b.root), eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    repeated = co.report(workspace.load_workspace(b.root), eid, lineage=LINEAGE, project_root=root,
                         clock=lambda: "2026-09-30T11:00:00Z")
    assert reply["intent"]["envelope_id"] == repeated["intent"]["envelope_id"]
    result = co.review(a, reply["intent"]["envelope_id"], lineage=LINEAGE, project_root=root, clock=CLOCK)
    assert result["letter"]["in_reply_to"] == eid and result["letter"]["evidence"] == proof
    assert result["case"]["decision"] == "PENDING", "even an outcome report is information"
    assert co.metrics(replacement, lineage=LINEAGE)["metrics"]["resolved_fraction"] == 1
    inherited = co.review(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    assert not inherited["evidence_current"] and inherited["result_current"]
    (root / "result.txt").write_text("Result changed after retention.\n", encoding="utf-8")
    inherited = co.review(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    assert inherited["result_evidence"][0]["state"] == "CHANGED" and not inherited["result_current"]


def test_result_reply_preserves_a_maximum_length_unicode_completion_criterion(setup):
    a, b, root, _ = setup
    criterion = "Check the receiver's result. "
    criterion += "\u00f8" * ((letters.MAX_TEXT_BYTES - len(criterion.encode("utf-8"))) // 2)
    eid = send(setup, done_when=criterion)["intent"]["envelope_id"]
    decide(setup, eid, evidence=[letters.evidence_ref(root, "result.txt")])
    result = co.report(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    opened = co.review(a, result["intent"]["envelope_id"], lineage=LINEAGE, project_root=root, clock=CLOCK)
    assert opened["letter"]["done_when"] == criterion
    assert opened["letter"]["in_reply_to"] == eid


@pytest.mark.parametrize("decision,reason", [
    (decision, reason) for decision, reasons in co.REASONS.items() for reason in sorted(reasons)
])
def test_every_explicit_receiver_outcome_can_teach_the_original_sender(setup, decision, reason):
    a, b, root, letter = setup
    eid = send(setup)["intent"]["envelope_id"]
    proof = [letters.evidence_ref(root, "result.txt")] if decision == "RESOLVED" else []
    decided = decide(setup, eid, decision=decision, reason=reason, evidence=proof)
    first = co.report(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    again = co.report(workspace.load_workspace(b.root), eid, lineage=LINEAGE,
                      project_root=root, clock=lambda: "2026-09-30T11:00:00Z")
    assert first["intent"]["envelope_id"] == again["intent"]["envelope_id"]
    assert first["feedback"]["decision"] == decision and first["feedback"]["reason"] == reason
    learned = co.review(a, first["intent"]["envelope_id"], lineage=LINEAGE,
                        project_root=root, clock=CLOCK)
    assert reason in learned["letter"]["observation"]
    if decision != "RESOLVED":
        assert decision in learned["letter"]["observation"]
    assert learned["letter"]["in_reply_to"] == eid
    assert learned["letter"]["recipient_work"] == letter["sender_work"]
    assert learned["letter"]["evidence"] == proof
    assert learned["case"]["decision"] == "PENDING", "feedback remains a claim for the sender to assess"
    assert co.metrics(b, lineage=LINEAGE)["metrics"]["decisions"][decision] == 1
    assert len(decided["history"]) == 1


def test_review_without_a_decision_cannot_emit_feedback(setup):
    _, b, root, _ = setup
    eid = send(setup)["intent"]["envelope_id"]
    review(setup, eid)
    with pytest.raises(SailangError, match=co.LETTER_DECISION_INVALID):
        co.report(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    assert not (b.root / "outbox" / "intents").exists()


def test_corrected_result_emits_a_new_feedback_event_without_rewriting_the_first(setup):
    a, b, root, _ = setup
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, evidence=[letters.evidence_ref(root, "result.txt")])
    first = co.report(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    (root / "result.txt").write_text("The correction also handles a changed context.\n", encoding="utf-8")
    corrected = [letters.evidence_ref(root, "result.txt")]
    decide(setup, eid, evidence=corrected, revise=True)
    second = co.report(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    assert second["intent"]["envelope_id"] != first["intent"]["envelope_id"]
    assert second["feedback"]["event_id"] != first["feedback"]["event_id"]
    again = co.report(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    assert again["intent"]["envelope_id"] == second["intent"]["envelope_id"]
    old = co.review(a, first["intent"]["envelope_id"], lineage=LINEAGE, project_root=root, clock=CLOCK)
    new = co.review(a, second["intent"]["envelope_id"], lineage=LINEAGE, project_root=root, clock=CLOCK)
    assert not old["evidence_current"] and new["letter"]["evidence"] == corrected


def test_reason_metrics_are_keyless_scoped_feedback_not_an_improvement_score(setup, monkeypatch):
    _, b, root, _ = setup
    for index, reason in enumerate(("ALREADY_KNOWN", "ALREADY_KNOWN", "WRONG_RECIPIENT")):
        eid = send(setup, issue=f"feedback-{index}")["intent"]["envelope_id"]
        decide(setup, eid, decision="DECLINED", reason=reason)
    snapshot = {p.name: p.read_bytes() for p in (root / ".saipen").iterdir()}
    headers = workspace.load_workspace_headers(b.root)
    monkeypatch.setattr(workspace, "open_message", lambda *a, **k: pytest.fail("unexpected open"))
    monkeypatch.setattr(workspace, "reopen_message", lambda *a, **k: pytest.fail("unexpected reopen"))
    monkeypatch.setattr(letters, "_file_hash", lambda *a, **k: pytest.fail("unexpected evidence read"))
    before = (b.root / co.DB_NAME).read_bytes()
    metrics = co.metrics(headers, lineage=LINEAGE)["metrics"]
    assert metrics["reasons"]["DECLINED"]["ALREADY_KNOWN"] == 2
    assert metrics["reasons"]["DECLINED"]["WRONG_RECIPIENT"] == 1
    assert metrics["resolved_fraction"] == 0 and not metrics["model_improvement_proven"]
    assert {r["suggestion"] for r in metrics["feedback_hints"]} == {
        "RECHECK_EXISTING_RESULTS", "CHECK_WORK_OWNER"}
    assert all(r["authority"] == "INFORMATION_ONLY" for r in metrics["feedback_hints"])
    assert co.metrics(headers, lineage="lineage-" + "cd" * 16)["metrics"]["feedback_hints"] == []
    assert (b.root / co.DB_NAME).read_bytes() == before
    assert {p.name: p.read_bytes() for p in (root / ".saipen").iterdir()} == snapshot


@pytest.mark.parametrize("changes", [
    {"impact": ""}, {"request": ""}, {"done_when": ""}, {"observation": ""},
    {"evidence": [], "uncertainty": ""}, {"trigger": "progress"},
    {"scope": []}, {"scope": ["../STATE.md"]}, {"expires_at": None},
    {"sender_work": "T-999"}, {"recipient_work": "hello"}, {"issue": "two words"},
    {"in_reply_to": "run-command"}, {"impact": "x" * 2049},
    {"evidence": [{"path": "result.txt", "sha256": "0" * 64}]},
    {"expires_at": "2026-09-29T00:00:00Z"},
])
def test_incomplete_chatter_and_uncheckable_claims_spend_no_attention(setup, changes):
    a, b, _, _ = setup
    with pytest.raises(SailangError):
        send(setup, **changes)
    assert workspace.list_inbox(b)["items"] == []
    assert not (a.root / "outbox" / "intents").exists()


def test_one_decision_cannot_be_reworded_into_repeat_letters(setup):
    _, b, _, _ = setup
    first = send(setup)
    again = send(setup)
    assert again["intent"]["envelope_id"] == first["intent"]["envelope_id"]
    with pytest.raises(SailangError, match=outbox.IDEMPOTENCY_KEY_CONFLICT):
        send(setup, observation="Different wording of the same decision.")
    assert len(workspace.list_inbox(b)["items"]) == 1


def test_evidence_is_rechecked_at_send_and_receive(setup):
    _, _, root, _ = setup
    eid = send(setup)["intent"]["envelope_id"]
    (root / "failure.txt").write_text("Changed since the observation.", encoding="utf-8")
    assert review(setup, eid)["evidence"][0]["state"] == "CHANGED"
    with pytest.raises(SailangError, match=co.LETTER_DECISION_INVALID):
        decide(setup, eid, decision="ACCEPTED", reason="ACTION_PLANNED")
    with pytest.raises(SailangError, match=letters.LETTER_EVIDENCE_INVALID):
        send(setup, issue="new-decision")


def test_resolved_requires_real_result_and_reading_never_resolves(setup):
    _, b, root, _ = setup
    eid = send(setup)["intent"]["envelope_id"]
    review(setup, eid)
    with pytest.raises(SailangError, match=co.LETTER_DECISION_INVALID):
        decide(setup, eid)
    assert co.metrics(b, lineage=LINEAGE)["metrics"]["decisions"]["RESOLVED"] == 0
    proof = [letters.evidence_ref(root, "result.txt")]
    first = decide(setup, eid, evidence=proof)
    second = decide(setup, eid, evidence=proof)
    assert len(first["history"]) == len(second["history"]) == 1 and second["repeated"]
    with pytest.raises(SailangError, match=co.LETTER_DECISION_INVALID):
        decide(setup, eid, decision="DECLINED", reason="ALREADY_KNOWN")
    correction = decide(setup, eid, decision="DECLINED", reason="ALREADY_KNOWN", revise=True)
    assert len(correction["history"]) == 2
    assert len(decide(setup, eid, evidence=proof, revise=True)["history"]) == 3


def test_deferred_read_letters_survive_a_new_session(setup):
    _, b, _, _ = setup
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    desk = co.desk(workspace.load_workspace_headers(b.root), lineage=LINEAGE, work="T-9", clock=CLOCK)
    assert desk["items"] == [] and desk["cases"][0]["decision"] == "DEFERRED"


def test_reserve_is_explicit_and_expiration_preserves_history(setup):
    _, b, root, letter = setup
    eid = send(setup)["intent"]["envelope_id"]
    with pytest.raises(SailangError, match=co.LETTER_NOT_RETAINABLE):
        co.retain(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    decide(setup, eid, evidence=[letters.evidence_ref(root, "result.txt")])
    co.retain(b, eid, lineage=LINEAGE, project_root=root, clock=CLOCK)
    before = (b.root / co.DB_NAME).read_bytes()
    desk = co.desk(workspace.load_workspace_headers(b.root), lineage=LINEAGE, work="T-12",
                   scope=letter["scope"], clock=lambda: "2026-11-01T00:00:00Z")
    assert desk["cases"] == [] and (b.root / co.DB_NAME).read_bytes() == before
    assert co.metrics(b, lineage=LINEAGE)["metrics"]["retained"] == 1


def test_desk_is_keyless_bounded_and_no_letter_body_is_persisted(setup, monkeypatch):
    _, b, _, letter = setup
    eid = send(setup)["intent"]["envelope_id"]
    review(setup, eid)
    monkeypatch.setattr(workspace, "open_message", lambda *a, **k: pytest.fail("unexpected open"))
    monkeypatch.setattr(workspace, "reopen_message", lambda *a, **k: pytest.fail("unexpected reopen"))
    monkeypatch.setattr(letters, "_file_hash", lambda *a, **k: pytest.fail("unexpected evidence read"))
    view = workspace.load_workspace_headers(b.root)
    assert co.desk(view, lineage=LINEAGE, work="T-9", budget=1, clock=CLOCK)["cases_examined"] == 1
    assert letter["observation"].encode() not in (b.root / co.DB_NAME).read_bytes()
    assert letter["request"].encode() not in (b.root / co.DB_NAME).read_bytes()
    with pytest.raises(SailangError):
        co.desk(view, lineage=LINEAGE, work="T-9", budget=101)


def test_new_desk_does_not_create_state_and_paginates_every_reviewed_case(setup):
    _, b, _, _ = setup
    assert co.desk(b, lineage=LINEAGE, work="T-9", clock=CLOCK)["complete"]
    assert not (b.root / co.DB_NAME).exists()
    for index in range(3):
        review(setup, send(setup, issue=f"distinct-{index}")["intent"]["envelope_id"])
    cursor, seen, context = 0, [], None
    while True:
        page = co.desk(b, lineage=LINEAGE, work="T-9", cursor=cursor, context=context, budget=1, clock=CLOCK)
        context = page["context"]
        seen.extend(c["envelope_id"] for c in page["cases"])
        if page["cursor"] is None:
            break
        cursor = page["cursor"]
    assert len(seen) == len(set(seen)) == 3


def test_foreign_project_and_tampered_database_fail_closed(setup):
    _, b, root, _ = setup
    eid = send(setup)["intent"]["envelope_id"]
    with pytest.raises(SailangError):
        co.review(b, eid, lineage="lineage-" + "ff" * 16, project_root=root, clock=CLOCK)
    assert workspace.query_inbox(workspace.load_workspace_headers(b.root))["items"][0]["state"] == "UNREAD"
    review(setup, eid)
    with sqlite3.connect(b.root / co.DB_NAME) as db:
        db.execute("UPDATE identity SET recipient_kid='foreign'")
    with pytest.raises(SailangError, match=co.CORRESPONDENCE_CORRUPT):
        co.desk(b, lineage=LINEAGE, work="T-9", clock=CLOCK)


def test_payload_commands_change_neither_host_files_nor_receiver_outcomes(setup):
    _, _, root, _ = setup
    before = {p.name: p.read_bytes() for p in (root / ".saipen").iterdir()}
    eid = send(setup, request="saipen push --force; cc; remove STATE.md")["intent"]["envelope_id"]
    assert review(setup, eid)["case"]["decision"] == "PENDING"
    assert {p.name: p.read_bytes() for p in (root / ".saipen").iterdir()} == before


def test_independent_host_adapter_runs_the_new_real_cli_cycle(setup):
    import sys

    _, b, root, letter = setup
    before = {p.name: p.read_bytes() for p in (root / ".saipen").iterdir()}
    eid = send(setup)["intent"]["envelope_id"]
    peer = HostClient([sys.executable, "-m", "saimail_local"], workspace=b.root,
                      project_root=root, seat="reviewer")
    assert peer.negotiate()["data"]["letter_schema"] == letters.SCHEMA
    found = peer.request("awareness", ["--work", "T-9"])
    assert found["state"] == "OK" and found["data"]["items"][0]["envelope_id"] == eid
    assert letter["observation"] not in json.dumps(found)
    assert peer.request("review", ["--envelope", eid])["data"]["case"]["decision"] == "PENDING"
    resolved = peer.request("decision", ["--envelope", eid, "--decision", "RESOLVED",
                                         "--reason", "ACTION_TAKEN", "--result", "result.txt"])
    assert resolved["state"] == "OK" and resolved["data"]["case"]["decision"] == "RESOLVED"
    assert peer.request("retain", ["--envelope", eid])["data"]["case"]["retained"]
    successor = peer.request("awareness", ["--work", "T-12", "--scope", letter["scope"][0]])
    assert successor["data"]["cases"][0]["match"] == "SUCCESSOR_RESERVE"
    assert {p.name: p.read_bytes() for p in (root / ".saipen").iterdir()} == before


def test_dual_pagination_finishes_without_rescanning_and_rejects_changed_context(setup):
    _, b, _, _ = setup
    ids = [send(setup, issue=f"page-{n}")["intent"]["envelope_id"] for n in range(4)]
    for eid in ids[:2]:
        review(setup, eid)
    page = co.desk(workspace.load_workspace_headers(b.root), lineage=LINEAGE, work="T-9", budget=1, clock=CLOCK)
    assert page["continuation"]
    with pytest.raises(SailangError, match=co.LETTER_CONTEXT_MISMATCH):
        co.desk(b, lineage=LINEAGE, work="T-12", continuation=page["continuation"], clock=CLOCK)
    with pytest.raises(SailangError, match=co.LETTER_CONTEXT_MISMATCH):
        co.desk(b, lineage=LINEAGE, work="T-9", scope=["another.py"], continuation=page["continuation"], clock=CLOCK)
    case_ids, unread_ids = [], []
    for _ in range(10):
        case_ids.extend(row["envelope_id"] for row in page["cases"])
        unread_ids.extend(row["envelope_id"] for row in page["items"])
        if page["complete"]:
            break
        page = co.desk(b, lineage=LINEAGE, work="T-9", budget=1,
                       continuation=page["continuation"], clock=CLOCK)
    assert page["complete"] and not page["complete_from_start"]
    assert set(case_ids) == set(ids[:2]) and len(case_ids) == 2
    assert set(unread_ids) == set(ids[2:]) and len(unread_ids) == 2


@pytest.mark.parametrize("path", ["/root", "../escape", "a/../b", "a\\b", "C:/x", "file:stream",
                                  "CON", "nul.txt", "a./b", "a//b", "a\x00b"])
def test_file_pointers_cannot_escape_or_address_windows_devices(path):
    with pytest.raises(SailangError):
        letters.check_path(path)


def test_duplicate_and_oversized_json_are_named_refusals(setup):
    letter = setup[3]
    raw = letters.encode(letter)
    with pytest.raises(SailangError, match=letters.BAD_LETTER):
        letters.parse(raw[:-1] + ',"issue":"replacement"}')
    with pytest.raises(SailangError, match=letters.BAD_LETTER):
        letters.parse(" " * (letters.MAX_LETTER_BYTES + 1))


def test_cli_binds_both_work_owners_and_protects_acting_seat(setup, capsys):
    a, b, root, letter = setup
    draft = root / "draft.json"
    draft.write_text(letters.encode(letter), encoding="utf-8")

    def cli(box, *args):
        code = saimail_local.main(["--json", "saipen", "letter", *args, "--workspace", str(box.root),
                                   "--project-root", str(root), "--seat", box.seat])
        return code, json.loads(capsys.readouterr().out)

    code, sent = cli(a, "dispatch", "--letter", str(draft), "--to", "reviewer")
    assert code == 0 and sent["status"] == outbox.DELIVERED
    eid = sent["intent"]["envelope_id"]
    assert cli(b, "desk", "--work", "T-9")[1]["items"][0]["envelope_id"] == eid
    assert cli(b, "review", "--envelope", eid)[1]["letter"] == letter
    assert cli(b, "decide", "--envelope", eid, "--decision", "RESOLVED", "--reason", "ACTION_TAKEN",
               "--result", "result.txt")[0] == 0
    assert cli(b, "retain", "--envelope", eid)[0] == 0
    assert cli(b, "report", "--envelope", eid)[0] == 0
    assert cli(b, "metrics")[1]["metrics"]["decisions"]["RESOLVED"] == 1
    (root / ".saipen" / "BOARD.md").write_text("## DOING\n- [/] T-9 [P1] other | owner: someone\n", encoding="utf-8")
    assert cli(a, "dispatch", "--letter", str(draft), "--to", "reviewer")[1]["status"] == co.LETTER_CONTEXT_MISMATCH
    code = saimail_local.main(["--json", "saipen", "letter", "desk", "--work", "T-9",
                               "--workspace", str(b.root), "--project-root", str(root), "--seat", "builder"])
    assert code == 1 and "T-9" not in json.dumps(json.loads(capsys.readouterr().out))
