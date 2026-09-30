"""T142 study evidence is append-only; scripted fixtures are not field actors."""

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import socket
from datetime import UTC, datetime
from pathlib import Path

import pytest

import saimail_local
from saimail import correspondence, credentials, letters, participants, workspace

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / ".saipen/evidence/T-142-evolution-audit"
REGISTRATION_HASH = "fec8b9908129b2dcbf5b86d92214ce5ab17cf6a71392c769c272c39cd0a4dc4f"
FIRST_HASH = "451d1960f397e4789dff611602376ed4395ba69f0db0531007fb9576140d147e"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def study(tmp_path, monkeypatch):
    evidence, project, foreign = (tmp_path / name for name in ("evidence", "project", "foreign"))
    evidence.mkdir()
    for name in ("registration.json", "runtime.json"):
        shutil.copyfile(STUDY / name, evidence / name)
    memory = project / ".saipen"
    memory.mkdir(parents=True)
    lineage = json.loads((evidence / "runtime.json").read_text())["explicit_focus"]["answer"]["focus"]["host"]["lineage"]
    (memory / "IDENTITY.md").write_text(f"---\nproject_lineage: {lineage}\n---\n", encoding="utf-8")
    (foreign / ".saipen").mkdir(parents=True)
    (foreign / ".saipen/STATE.md").write_bytes(b"foreign canonical state, do not edit\n")
    box = tmp_path / "box"
    workspace.init_workspace(box, seat="saipen-cli")
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)
    subject = Path(os.environ.get("T142_RECORDER_SUBJECT", str(STUDY)))
    capture = load(subject / "capture.py", "t142_test_capture")
    verify = load(STUDY / "verify.py", "t142_test_verify")
    for name, value in (("ROOT", project), ("OUT", evidence), ("HOST", foreign), ("BOX", box)):
        monkeypatch.setattr(capture, name, value)
    monkeypatch.setattr(capture.shutil, "which", lambda _: "saimail-local")
    calls = []

    def command(argv):
        calls.append(list(argv))
        started = datetime.now(UTC).isoformat()
        transcript = io.StringIO()
        with contextlib.redirect_stdout(transcript):
            code = saimail_local.main(argv[1:])
        return {"argv": argv, "started": started, "ended": datetime.now(UTC).isoformat(),
                "exit_code": code, "answer": json.loads(transcript.getvalue())}

    monkeypatch.setattr(capture, "command", command)

    def set_work(work="T-144", event=3000, phase="BUILD", owner="saipen-cli"):
        (memory / "STATE.md").write_text(
            f"---\nphase: {phase}\ntask: {work}\nagent: saipen-cli\nlast_event: {event}\nblocker: \"\"\n---\n",
            encoding="utf-8")
        (memory / "BOARD.md").write_text(
            f"# Board\n## DOING\n- [/] {work} [P1] actual authorized test Work | owner: {owner}\n## TODO\n",
            encoding="utf-8")
        (memory / "LOG.md").write_text(
            f"- 30.09.26 12:00 [E-{event}] [T-{work[2:]}] RUN: test context\n", encoding="utf-8")

    set_work()
    return capture, verify, evidence, project, foreign, box, set_work, calls


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def rewrite(path, record):
    path.write_text(json.dumps(record), encoding="utf-8")


def test_entry2_appends_and_preserves_history(study):
    cap, verify, evidence, *_ = study
    before = {n: (evidence / n).read_bytes() for n in ("runtime.json", "registration.json")}
    cap.main()
    record = read(evidence / "runtime-002.json")
    assert record["entry"] == 2 and record["work"] == "T-144"
    assert {n: (evidence / n).read_bytes() for n in before} == before
    assert hashlib.sha256(before["runtime.json"]).hexdigest() == FIRST_HASH
    assert hashlib.sha256(before["registration.json"]).hexdigest() == REGISTRATION_HASH
    assert verify.sequence(evidence)["retained_observations"] == 2


def test_entry3_follows_deterministically_without_replacing_entry2(study):
    cap, verify, evidence, _, _, _, set_work, _ = study
    cap.main()
    previous = files(evidence)
    set_work("T-145", 3001)
    cap.main()
    assert read(evidence / "runtime-003.json")["entry"] == 3
    assert all((evidence / n).read_bytes() == value for n, value in previous.items())
    summary = verify.sequence(evidence)
    assert summary["retained_observations"] == summary["qualifying_work_context_boundaries"] == 3


@pytest.mark.parametrize("change,match", [
    (lambda r: r.update(entry=1), "entry"),
    (lambda r: r.update(study="wrong"), "study"),
    (lambda r: r.update(registration_sha256="0" * 64), "registration"),
    (lambda r: r.update(work="T-999"), "Work"),
    (lambda r: r.update(field_improvement="PROVEN"), "independent"),
    (lambda r: r.update(independent_receiver=True), "independent"),
    (lambda r: r.update(independent_successor=True), "independent"),
    (lambda r: r.update(independent_revision="CHOSEN"), "independent"),
    (lambda r: r.update(successor_execution="RUN"), "independent"),
    (lambda r: r.update(receiver_effort="MEASURED"), "EMPTY"),
    (lambda r: r["explicit_focus"]["answer"]["focus"]["coverage"].update(complete_from_start=False), "EMPTY"),
    (lambda r: r["canonical_context"].update(work="T-999"), "context"),
    (lambda r: r["canonical_context"].update(last_event="9999"), "context"),
    (lambda r: r["canonical_context"].update(focus_context="sha256:" + "0" * 64), "context"),
    (lambda r: r.update(qualifies_context_boundary=False), "boundary"),
    (lambda r: r.update(previous_observation_sha256="0" * 64), "previous observation"),
    (lambda r: r["explicit_focus"].update(argv=["saimail-local", "send"]), "observational authority"),
    (lambda r: r["memory_after"].update(**{"STATE.md": "0" * 64}), "memory"),
    (lambda r: r.update(foreign_state_after_sha256="0" * 64), "foreign"),
])
def test_malformed_retained_observation_refuses_capture_and_verifier(study, change, match):
    cap, verify, evidence, *_ = study
    cap.main()
    path = evidence / "runtime-002.json"
    record = read(path)
    change(record)
    rewrite(path, record)
    before = files(evidence)
    with pytest.raises(ValueError, match=match):
        cap.observe()
    with pytest.raises(ValueError, match=match):
        verify.sequence(evidence)
    assert files(evidence) == before


@pytest.mark.parametrize("name", ["runtime-001.json", "runtime-2.json", "runtime-002-copy.json", "runtime-000.json"])
def test_duplicate_or_noncanonical_numbering_fails_closed(study, name):
    cap, verify, evidence, *_ = study
    shutil.copyfile(evidence / "runtime.json", evidence / name)
    before = files(evidence)
    with pytest.raises(ValueError, match="filename"):
        cap.observe()
    with pytest.raises(ValueError, match="filename"):
        verify.sequence(evidence)
    assert files(evidence) == before


def test_sequence_gap_fails_closed(study):
    cap, verify, evidence, *_ = study
    shutil.copyfile(evidence / "runtime.json", evidence / "runtime-003.json")
    with pytest.raises(ValueError, match="gap"):
        cap.observe()
    with pytest.raises(ValueError, match="gap"):
        verify.sequence(evidence)


@pytest.mark.parametrize("payload", [b"{", b'[]', b'{"entry":2,"entry":2}', b'{"entry":NaN}'])
def test_invalid_previous_json_fails_closed(study, payload):
    cap, verify, evidence, *_ = study
    (evidence / "runtime-002.json").write_bytes(payload)
    with pytest.raises(ValueError):
        cap.observe()
    with pytest.raises(ValueError):
        verify.sequence(evidence)


@pytest.mark.parametrize("name", ["registration.json", "runtime.json"])
def test_immutable_evidence_hash_mismatch_fails_closed(study, name):
    cap, verify, evidence, *_ = study
    with (evidence / name).open("ab") as target:
        target.write(b" ")
    before = files(evidence)
    with pytest.raises(ValueError, match="immutable"):
        cap.observe()
    with pytest.raises(ValueError, match="immutable"):
        verify.sequence(evidence)
    assert files(evidence) == before


def test_seventh_entry_is_refused(study):
    cap, verify, evidence, _, _, _, set_work, _ = study
    for entry in range(2, 7):
        set_work(f"T-{142 + entry}", 3000 + entry)
        cap.main()
    assert verify.sequence(evidence)["retained_observations"] == 6
    before = files(evidence)
    set_work("T-149", 4000)
    with pytest.raises(ValueError, match="limit"):
        cap.observe()
    assert files(evidence) == before and not (evidence / "runtime-007.json").exists()


def test_retained_seventh_entry_is_also_refused(study):
    cap, verify, evidence, *_ = study
    shutil.copyfile(evidence / "runtime.json", evidence / "runtime-007.json")
    with pytest.raises(ValueError, match="limit"):
        verify.sequence(evidence)
    with pytest.raises(ValueError, match="limit"):
        cap.observe()


def test_same_work_event_phase_and_focus_changes_do_not_inflate_boundaries(study):
    cap, verify, evidence, _, _, _, set_work, _ = study
    cap.main()
    before = files(evidence)
    for event, phase in ((3000, "BUILD"), (3001, "BUILD"), (3002, "VERIFY")):
        set_work(event=event, phase=phase)
        with pytest.raises(ValueError, match="already observed"):
            cap.observe()
    assert files(evidence) == before
    assert verify.sequence(evidence)["qualifying_work_context_boundaries"] == 2


def test_verifier_rejects_same_boundary_under_new_number(study):
    cap, verify, evidence, *_ = study
    cap.main()
    record = read(evidence / "runtime-002.json")
    record["entry"] = 3
    record["previous_observation_sha256"] = verify.sha(evidence / "runtime-002.json")
    rewrite(evidence / "runtime-003.json", record)
    with pytest.raises(ValueError, match="boundary"):
        verify.sequence(evidence)


@pytest.mark.parametrize("owner,phase", [("another-seat", "BUILD"), ("saipen-cli", "DONE")])
def test_recorder_refuses_unowned_or_ended_work(study, owner, phase):
    cap, _, evidence, _, _, _, set_work, calls = study
    set_work(owner=owner, phase=phase)
    with pytest.raises(ValueError, match="authorized"):
        cap.observe()
    assert calls == [] and not (evidence / "runtime-002.json").exists()


def test_empty_no_provider_no_correspondence_or_project_or_foreign_mutation(study, monkeypatch):
    cap, verify, evidence, project, foreign, box, _, calls = study

    def forbidden(*args, **kwargs):
        pytest.fail("observation attempted a provider, body open or correspondence mutation")

    for name in ("dispatch", "review", "decide", "retain", "report"):
        monkeypatch.setattr(correspondence, name, forbidden)
    monkeypatch.setattr(credentials, "resolve", forbidden)
    monkeypatch.setattr(workspace, "send_message", forbidden)
    monkeypatch.setattr(workspace, "open_message", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    before = {"project": files(project), "foreign": files(foreign), "box": files(box)}
    cap.main()
    assert {"project": files(project), "foreign": files(foreign), "box": files(box)} == before
    assert all("focus" in c or "--contract" in c for c in calls)
    record = read(evidence / "runtime-002.json")
    assert record["observation"] == "EMPTY"
    assert record["receiver_effort"] == "UNKNOWN_NO_RECEIVER_OPPORTUNITY"
    assert record["independent_revision"] == record["successor_execution"] == "NOT_RUN"
    summary = verify.sequence(evidence)
    assert summary["eligible_receiver_opportunities"] == 0
    assert summary["independent_receiver_assessments"] == 0
    assert summary["independently_chosen_revisions"] == 0
    assert summary["fresh_successor_executions"] == 0
    assert summary["field_improvement"] == "UNPROVEN"


def test_changed_context_during_focus_is_not_retained(study, monkeypatch):
    cap, _, evidence, _, _, _, set_work, _ = study
    original = cap.command

    def changed(argv):
        answer = original(argv)
        if "focus" in argv:
            set_work("T-145", 4000)
        return answer

    monkeypatch.setattr(cap, "command", changed)
    with pytest.raises(ValueError, match="memory"):
        cap.observe()
    assert not (evidence / "runtime-002.json").exists()


def test_atomic_destination_race_never_replaces_existing_file(study, monkeypatch):
    cap, _, evidence, *_ = study
    original = cap.append
    occupied = b"another writer retained this observation\n"

    def race(path, record):
        path.write_bytes(occupied)
        return original(path, record)

    monkeypatch.setattr(cap, "append", race)
    with pytest.raises(FileExistsError):
        cap.observe()
    assert (evidence / "runtime-002.json").read_bytes() == occupied


def test_original_single_observation_mechanical_status(study):
    _, verify, evidence, *_ = study
    summary = verify.sequence(evidence)
    assert summary["retained_observations"] == summary["qualifying_work_context_boundaries"] == 1
    assert summary["minimum_work_context_boundaries"] == 3
    assert summary["entry_limit"] == 6
    assert summary["field_improvement"] == "UNPROVEN"


def test_nonempty_is_metadata_only_and_does_not_become_independent_behavior(study, monkeypatch):
    cap, verify, evidence, project, foreign, box, _, _ = study
    recipient = workspace.load_workspace(box)
    sender_path = box.parent / "test-sender"
    workspace.init_workspace(sender_path, seat="test-sender")
    sender = workspace.load_workspace(sender_path)
    lineage = verify.sequence(evidence)["project_lineage"]
    workspace.add_recipient(sender, "saipen-cli", workspace.identity_card(recipient), box)
    workspace.add_recipient(recipient, "test-sender", workspace.identity_card(sender), sender.root)
    participants.admit_participant(sender, lineage, "saipen-cli")
    participants.admit_participant(recipient, lineage, "test-sender")
    (project / "test-evidence.txt").write_text("Controlled test evidence only.\n", encoding="utf-8")
    letter = letters.template(lineage, "T-1", "T-144", issue="fixture-opportunity")
    letter.update(observation="Controlled fixture", impact="Test read-only collection", request="Explicit review",
                  done_when="Receiver chooses", uncertainty="No independent behavior in this test",
                  evidence=[letters.evidence_ref(project, "test-evidence.txt")], scope=["test-evidence.txt"])
    dispatched = correspondence.dispatch(sender, letter, lineage=lineage, sender_work="T-1",
                                         to_seat="saipen-cli", project_root=project)
    assert dispatched["intent"]["envelope_id"] is not None
    assert len(workspace.query_inbox(recipient)["items"]) == 1
    before = {"box": files(box), "project": files(project), "foreign": files(foreign)}

    def forbidden(*args, **kwargs):
        pytest.fail("collection opened or mutated a sealed letter")

    for name in ("dispatch", "review", "decide", "retain", "report"):
        monkeypatch.setattr(correspondence, name, forbidden)
    monkeypatch.setattr(workspace, "open_message", forbidden)
    monkeypatch.setattr(workspace, "send_message", forbidden)
    cap.main()
    assert {"box": files(box), "project": files(project), "foreign": files(foreign)} == before
    record = read(evidence / "runtime-002.json")
    assert record["observation"] == "INSPECT_RECORDED_RESULT"
    summary = verify.sequence(evidence)
    assert summary["eligible_receiver_opportunities"] == 1
    assert summary["independent_receiver_assessments"] == 0
    assert summary["field_improvement"] == "UNPROVEN"


def test_predecessor_binding_detects_replacement_of_semantically_valid_history(study):
    cap, verify, evidence, _, _, _, set_work, _ = study
    cap.main()
    set_work("T-145", 3001)
    cap.main()
    path = evidence / "runtime-002.json"
    record = read(path)
    record["timestamp"] = record["explicit_focus"]["ended"]
    rewrite(path, record)
    with pytest.raises(ValueError, match="previous observation"):
        verify.sequence(evidence)
