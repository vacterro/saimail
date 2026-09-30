"""V6-07 SAIMAIL half (T-121): a capability document SAIPEN can negotiate against.

Every channel problem must arrive as a state and a closed reason, never as a
crash or a bare exit code, so SAIPEN can keep working and report the channel as
DEGRADED. A wrong seat must see nothing of another agent's mailbox, and the
check must never touch a private key.
"""

from __future__ import annotations

import json

import pytest

import saimail_local
from saimail import capabilities as caps
from saimail import credentials, custody, outbox, participants, workspace

LINEAGE = "lineage-" + "c4" * 16


@pytest.fixture(autouse=True)
def _no_ambient_actor(monkeypatch):
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)


def _pair(tmp_path, *, mode=custody.CUSTODY_RAW, store=None):
    workspace.init_workspace(tmp_path / "builder", seat="builder", custody=mode, store=store)
    workspace.init_workspace(tmp_path / "astra", seat="astra")
    A = workspace.load_workspace(tmp_path / "builder", store=store)
    B = workspace.load_workspace(tmp_path / "astra")
    workspace.add_recipient(A, "astra", workspace.identity_card(B), B.root)
    workspace.add_recipient(B, "builder", workspace.identity_card(A), A.root)
    return A, B


def _doc(root, **kwargs):
    return caps.capabilities(root, **kwargs)["capabilities"]


def test_a_healthy_channel_is_available_with_seat_checked_counts(tmp_path):
    A, B = _pair(tmp_path)
    participants.admit_participant(A, LINEAGE, "astra")
    for topic in ("T-7", "T-7", "T-8"):
        workspace.send_message(B, "builder", claim="secret body text", topic=topic,
                               kind="DISCOVERY")
    result = caps.capabilities(A.root, acting_seat="builder", lineage=LINEAGE,
                               current_topic="T-7")
    doc = result["capabilities"]
    assert result["status"] == caps.AVAILABLE and result["ok"] is True
    assert doc["overall"] == caps.AVAILABLE and doc["reasons"] == []
    assert doc["awareness"] == {"unread": 3, "current_topic": "T-7", "on_current_topic": 2,
                                "complete": True, "scan_budget": caps.AWARENESS_SCAN_BUDGET}
    states = {name: entry["state"] for name, entry in doc["capabilities"].items()}
    assert states == {"signing": caps.UNVERIFIED, "header_awareness": caps.AVAILABLE,
                      "durable_outbox": caps.AVAILABLE, "participant_registry": caps.AVAILABLE}
    assert doc["seat"] == {"acting": "builder", "source": None, "workspace": "builder",
                           "matches": True}
    assert "secret body text" not in json.dumps(result)


def test_a_wrong_seat_sees_nothing_of_the_mailbox(tmp_path):
    A, B = _pair(tmp_path)
    sent = workspace.send_message(B, "builder", claim="private", topic="T-7", kind="WARNING")
    result = caps.capabilities(A.root, acting_seat="astra", lineage=LINEAGE,
                               current_topic="T-7")
    doc = result["capabilities"]
    assert doc["overall"] == caps.UNAVAILABLE and doc["reasons"] == [caps.SEAT_MISMATCH]
    assert doc["awareness"] is None and doc["outbox"] is None and doc["capabilities"] == {}
    text = json.dumps(result)
    assert sent["message"]["envelope_id"] not in text and "T-7" not in text


@pytest.mark.parametrize("damage, reason", [
    (lambda root: None, caps.WORKSPACE_MISSING),
    (lambda root: (root / workspace.MARKER_NAME).write_text("{}", encoding="utf-8"),
     caps.WORKSPACE_INVALID),
])
def test_an_unusable_mailbox_is_a_state_not_a_crash(tmp_path, damage, reason):
    root = tmp_path / "missing"
    if reason == caps.WORKSPACE_INVALID:
        workspace.init_workspace(root, seat="builder")
        damage(root)
    doc = _doc(root, acting_seat="builder", lineage=LINEAGE)
    assert doc["overall"] == caps.UNAVAILABLE and reason in doc["reasons"]
    assert doc["workspace"]["state"] == caps.UNAVAILABLE


def test_no_project_and_no_participants_degrade_instead_of_failing(tmp_path):
    A, _B = _pair(tmp_path)
    unbound = _doc(A.root, acting_seat="builder")
    assert unbound["overall"] == caps.DEGRADED
    assert unbound["reasons"] == [caps.PROJECT_NOT_BOUND]
    assert unbound["capabilities"]["participant_registry"]["state"] == caps.UNAVAILABLE
    assert unbound["awareness"]["unread"] == 0
    nobody = _doc(A.root, acting_seat="builder", lineage=LINEAGE)
    assert nobody["overall"] == caps.DEGRADED and nobody["reasons"] == [caps.NO_PARTICIPANTS]
    assert nobody["capabilities"]["participant_registry"]["state"] == caps.REQUIRES_HUMAN
    anonymous = _doc(A.root)
    assert caps.SEAT_UNKNOWN in anonymous["reasons"]


def test_outbox_trouble_is_reported_with_its_class(tmp_path):
    A, B = _pair(tmp_path)
    participants.admit_participant(A, LINEAGE, "astra")
    offline = tmp_path / "astra-offline"
    B.root.rename(offline)
    outbox.submit_send(A, "astra", key="k:slow", claim="c", topic="T-7", kind="DISCOVERY",
                       clock=lambda: "2026-09-24T07:00:00Z")
    fresh = _doc(A.root, acting_seat="builder", lineage=LINEAGE,
                 clock=lambda: "2026-09-24T07:10:00Z")
    assert fresh["capabilities"]["durable_outbox"]["state"] == caps.AVAILABLE
    assert fresh["outbox"]["pending"] == 1 and fresh["outbox"]["retrying"] == 1
    assert fresh["outbox"]["last_error"] == workspace.DELIVERY_TARGET_UNAVAILABLE
    stale = _doc(A.root, acting_seat="builder", lineage=LINEAGE,
                 clock=lambda: "2026-09-24T09:00:00Z")
    assert stale["capabilities"]["durable_outbox"]["reason"] == caps.OUTBOX_BACKLOG
    assert stale["overall"] == caps.DEGRADED
    offline.rename(B.root)
    workspace.init_workspace(tmp_path / "stranger", seat="stranger")
    stranger = workspace.load_workspace(tmp_path / "stranger")
    workspace.add_recipient(A, "stranger", workspace.identity_card(stranger), stranger.root)
    outbox.submit_send(A, "stranger", key="k:quarantined", claim="c", topic="T-7",
                       kind="DISCOVERY")
    failed = _doc(A.root, acting_seat="builder", lineage=LINEAGE)
    assert failed["capabilities"]["durable_outbox"] == {"state": caps.REQUIRES_HUMAN,
                                                        "reason": caps.OUTBOX_FAILED}
    assert failed["outbox"]["failed"] == 1


def test_corrupt_stores_are_named_and_the_document_still_arrives(tmp_path):
    A, _B = _pair(tmp_path)
    participants.admit_participant(A, LINEAGE, "astra")
    outbox.submit_send(A, "astra", key="k:1", claim="c", topic="T-7", kind="DISCOVERY")
    intent = next((A.root / "outbox" / "intents").glob("*.json"))
    intent.write_text("{broken", encoding="utf-8")
    (A.root / participants.PARTICIPANTS_NAME).write_text("[]", encoding="utf-8")
    doc = _doc(A.root, acting_seat="builder", lineage=LINEAGE)
    assert doc["capabilities"]["durable_outbox"]["reason"] == caps.OUTBOX_CORRUPT
    assert doc["capabilities"]["participant_registry"]["reason"] == caps.PARTICIPANTS_CORRUPT
    assert doc["overall"] == caps.DEGRADED
    assert doc["capabilities"]["header_awareness"]["state"] == caps.AVAILABLE


class _Locked(credentials.InMemoryCredentialStore):
    reads = 0

    def get(self, handle):
        type(self).reads += 1
        raise credentials.BackendError("locked")


def test_the_check_never_touches_a_private_key(tmp_path):
    store = credentials.InMemoryCredentialStore()
    credentials.set_credential_store(store)
    try:
        A, _B = _pair(tmp_path, mode=custody.CUSTODY_OS_STORE, store=store)
        participants.admit_participant(A, LINEAGE, "astra")
        credentials.set_credential_store(_Locked())
        doc = _doc(A.root, acting_seat="builder", lineage=LINEAGE)
        assert doc["overall"] == caps.AVAILABLE and _Locked.reads == 0
        assert doc["workspace"]["custody"] == custody.CUSTODY_OS_STORE
    finally:
        credentials.set_credential_store(None)


def _project(tmp_path, agent="builder", task="T-7"):
    memory = tmp_path / "project" / ".saipen"
    memory.mkdir(parents=True)
    (memory / "STATE.md").write_text(
        f"---\nphase: BUILD\ntask: {task}\nagent: {agent}\nlast_event: 40\n---\n",
        encoding="utf-8")
    (memory / "IDENTITY.md").write_text(f"---\nproject_lineage: {LINEAGE}\n---\n",
                                        encoding="utf-8")
    return memory.parent


def test_cli_answers_every_state_with_exit_zero(tmp_path, capsys, monkeypatch):
    A, B = _pair(tmp_path)
    participants.admit_participant(A, LINEAGE, "astra")
    workspace.send_message(B, "builder", claim="c", topic="T-7", kind="DISCOVERY")
    root = _project(tmp_path)

    def cli(*argv):
        code = saimail_local.main(["saipen", "capabilities", *argv, "--json"])
        return code, json.loads(capsys.readouterr().out)["capabilities"]

    code, doc = cli("--workspace", str(A.root), "--project-root", str(root))
    assert code == 0 and doc["overall"] == caps.AVAILABLE
    assert doc["project"]["lineage"] == LINEAGE and doc["awareness"]["on_current_topic"] == 1
    assert doc["seat"] == {"acting": "builder", "source": "STATE.agent", "workspace": "builder",
                           "matches": True}
    code, doc = cli("--workspace", str(A.root), "--project-root", str(root), "--seat", "astra")
    assert code == 0 and doc["reasons"] == [caps.SEAT_MISMATCH]
    code, doc = cli("--workspace", str(tmp_path / "nowhere"), "--project-root", str(root))
    assert code == 0 and doc["overall"] == caps.UNAVAILABLE
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SAIPEN_AGENT", "builder")
    code, doc = cli("--workspace", str(A.root))
    assert code == 0 and doc["reasons"] == [caps.PROJECT_NOT_BOUND]
    assert doc["seat"] == {"acting": "builder", "source": "SAIPEN_AGENT", "workspace": "builder",
                           "matches": True}


def test_the_document_contract_is_pinned():
    assert caps.CAPABILITIES_SCHEMA == "SAIMAIL_CAPABILITIES_1" and caps.CAPABILITIES_VERSION == 1
    assert caps.REASONS == {
        "WORKSPACE_MISSING", "WORKSPACE_INVALID", "SEAT_MISMATCH", "SEAT_UNKNOWN",
        "PROJECT_NOT_BOUND", "NO_PARTICIPANTS", "OUTBOX_BACKLOG", "OUTBOX_FAILED",
        "OUTBOX_CORRUPT", "PARTICIPANTS_CORRUPT", "INBOX_UNREADABLE", "KEYS_NOT_CHECKED"}
