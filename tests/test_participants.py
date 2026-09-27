"""V6-06 project-local participant registry (T-120): automation never guesses.

Routing to an agent needs an explicit, project-scoped admission that pins the
agent's identity and the notify triggers it may receive. Every control here
checks a refusal that replaces a guess, and that admission grants nothing at the
receiver.
"""

from __future__ import annotations

import json

import pytest

import saimail_local
from sailang import SailangError
from saimail import credentials, custody, outbox, participants, postoffice, saipen_bridge, workspace

L1 = "lineage-" + "1a" * 16
L2 = "lineage-" + "2b" * 16


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


@pytest.fixture
def mail(tmp_path, monkeypatch):
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)
    workspace.init_workspace(tmp_path / "builder", seat="builder")
    workspace.init_workspace(tmp_path / "astra", seat="astra")
    A = workspace.load_workspace(tmp_path / "builder")
    B = workspace.load_workspace(tmp_path / "astra")
    workspace.add_recipient(A, "astra", workspace.identity_card(B), B.root)
    return A, B


def test_admit_resolve_list_and_revoke(mail):
    A, _B = mail
    admitted = participants.admit_participant(A, L1, "astra", triggers=["blocker", "finding"])
    assert admitted["status"] == participants.ADMITTED
    again = participants.admit_participant(A, L1, "astra", triggers=["finding", "blocker"])
    assert again["status"] == participants.ALREADY_ADMITTED
    resolved = participants.resolve_participant(A, L1, "astra", trigger="blocker")
    assert resolved["participant"]["alias"] == "astra"
    assert resolved["participant"]["kind"] == "WARNING"
    listing = participants.list_participants(A, L1)["participants"]
    assert list(listing[L1]) == ["astra"]
    assert participants.revoke_participant(A, L1, "astra")["status"] == participants.REVOKED
    assert _code(participants.resolve_participant, A, L1, "astra",
                 trigger="blocker") == participants.PARTICIPANT_UNKNOWN


def test_resolution_refuses_instead_of_guessing(mail, tmp_path):
    A, _B = mail
    participants.admit_participant(A, L1, "astra", triggers=["finding"])
    resolve = participants.resolve_participant
    assert _code(resolve, A, L2, "astra", trigger="finding") == participants.PARTICIPANT_UNKNOWN
    assert _code(resolve, A, L1, "reviewer", trigger="finding") == participants.PARTICIPANT_UNKNOWN
    assert _code(resolve, A, L1, "astra",
                 trigger="blocker") == participants.PARTICIPANT_TRIGGER_NOT_ADMITTED
    assert _code(resolve, A, L1, "astra", trigger="chatter") == participants.BAD_TRIGGER
    assert _code(resolve, A, L1, "builder", trigger="finding") == participants.PARTICIPANT_SELF
    assert _code(resolve, A, "lineage-XYZ", "astra", trigger="finding") == participants.BAD_LINEAGE

    # The same seat name under a new identity is not the admitted participant.
    workspace.init_workspace(tmp_path / "impostor", seat="astra")
    impostor = workspace.identity_card(workspace.load_workspace(tmp_path / "impostor"))
    peers = json.loads((A.root / workspace.PEERS_NAME).read_text(encoding="utf-8"))
    peers["recipients"]["astra"].update(
        {name: impostor[name] for name in ("sender_public_key", "recipient_public_key",
                                           "sender_kid", "recipient_kid")},
        workspace=str(tmp_path / "impostor"))
    (A.root / workspace.PEERS_NAME).write_text(json.dumps(peers), encoding="utf-8")
    assert _code(resolve, A, L1, "astra",
                 trigger="finding") == participants.PARTICIPANT_IDENTITY_CHANGED


def test_admission_is_explicit_and_consistent(mail, tmp_path):
    A, _B = mail
    admit = participants.admit_participant
    assert _code(admit, A, L1, "reviewer") == workspace.RECIPIENT_UNKNOWN
    assert _code(admit, A, L1, "reviewer", alias="astra") == participants.PARTICIPANT_CONFLICT
    assert _code(admit, A, L1, "builder") == participants.PARTICIPANT_SELF
    assert _code(admit, A, "not-a-lineage", "astra") == participants.BAD_LINEAGE
    assert _code(admit, A, L1, "astra", triggers=[]) == participants.BAD_TRIGGER
    assert _code(admit, A, L1, "astra", triggers=["gossip"]) == participants.BAD_TRIGGER
    assert not (A.root / participants.PARTICIPANTS_NAME).exists()
    admit(A, L1, "astra", triggers=["finding"])
    assert _code(admit, A, L1, "astra",
                 triggers=["blocker"]) == participants.PARTICIPANT_CONFLICT
    assert participants.list_participants(A)["participants"][L1]["astra"]["triggers"] == [
        "finding"]


@pytest.mark.parametrize("damage", [
    lambda payload: payload.update(schema="OTHER"),
    lambda payload: payload["projects"].update({"lineage-bad": {}}),
    lambda payload: payload["projects"][L1]["astra"].update(triggers=["gossip"]),
    lambda payload: payload["projects"][L1]["astra"].update(extra=1),
])
def test_a_tampered_registry_fails_closed(mail, damage):
    A, _B = mail
    participants.admit_participant(A, L1, "astra")
    path = A.root / participants.PARTICIPANTS_NAME
    payload = json.loads(path.read_text(encoding="utf-8"))
    damage(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert _code(participants.resolve_participant, A, L1, "astra",
                 trigger="finding") == participants.PARTICIPANTS_CORRUPT
    assert _code(participants.list_participants, A) == participants.PARTICIPANTS_CORRUPT


def test_the_trigger_set_is_closed_and_uses_existing_kinds():
    from saimail import envelope

    assert set(participants.TRIGGERS) == {"blocker", "finding", "dependency", "ownership",
                                          "handoff", "reply"}
    assert set(participants.TRIGGERS.values()) <= envelope.KINDS


def test_admission_grants_nothing_at_the_receiver(mail):
    A, B = mail
    participants.admit_participant(A, L1, "astra")
    alias = participants.resolve_participant(A, L1, "astra",
                                             trigger="finding")["participant"]["alias"]
    # astra never registered builder: the receiver still decides.
    sent = outbox.submit_send(A, alias, key="k:1", claim="unsolicited", topic="T-7",
                              kind="DISCOVERY")
    assert sent["status"] == outbox.FAILED
    assert sent["intent"]["failure"] == postoffice.QUARANTINED
    assert workspace.list_inbox(workspace.load_workspace_headers(B.root))["items"] == []


class _Store(credentials.InMemoryCredentialStore):
    def __init__(self):
        super().__init__()
        self.reads = 0

    def get(self, handle):
        self.reads += 1
        raise credentials.BackendError("the credential store is locked")


def test_the_registry_needs_no_private_key(tmp_path):
    store = credentials.InMemoryCredentialStore()
    credentials.set_credential_store(store)
    try:
        workspace.init_workspace(tmp_path / "builder", seat="builder",
                                 custody=custody.CUSTODY_OS_STORE, store=store)
        workspace.init_workspace(tmp_path / "astra", seat="astra")
        A = workspace.load_workspace(tmp_path / "builder", store=store)
        workspace.add_recipient(A, "astra", workspace.identity_card(
            workspace.load_workspace(tmp_path / "astra")), tmp_path / "astra")
        locked = _Store()
        credentials.set_credential_store(locked)
        view = workspace.load_workspace_headers(A.root)
        participants.admit_participant(view, L1, "astra")
        assert participants.resolve_participant(view, L1, "astra", trigger="handoff")[
            "participant"]["kind"] == "QUESTION"
        assert locked.reads == 0
    finally:
        credentials.set_credential_store(None)


def _project(tmp_path, *, agent="builder", identity=True):
    memory = tmp_path / "project" / ".saipen"
    memory.mkdir(parents=True)
    (memory / "STATE.md").write_text(
        f"---\nphase: BUILD\ntask: T-7\nagent: {agent}\nlast_event: 40\n---\n", encoding="utf-8")
    if identity:
        (memory / "IDENTITY.md").write_text(f"---\nproject_lineage: {L1}\n---\n",
                                            encoding="utf-8")
    return memory.parent


def test_cli_takes_the_project_from_the_admitted_binding(mail, tmp_path, capsys):
    A, _B = mail
    root = _project(tmp_path)

    def cli(*argv):
        code = saimail_local.main(["saipen", "participant", *argv, "--workspace", str(A.root),
                                   "--project-root", str(root), "--json"])
        return code, json.loads(capsys.readouterr().out)

    code, admitted = cli("admit", "--participant", "astra", "--trigger", "blocker")
    assert code == 0 and admitted["participant"]["lineage"] == L1
    assert admitted["participant"]["triggers"] == ["blocker"]
    code, resolved = cli("resolve", "--participant", "astra", "--trigger", "blocker")
    assert code == 0 and resolved["participant"]["kind"] == "WARNING"
    code, refused = cli("resolve", "--participant", "astra", "--trigger", "finding")
    assert code == 1 and refused["status"] == participants.PARTICIPANT_TRIGGER_NOT_ADMITTED
    code, listing = cli("list")
    assert code == 0 and list(listing["participants"][L1]) == ["astra"]
    code, mismatch = cli("admit", "--participant", "astra", "--seat", "reviewer")
    assert code == 1 and mismatch["status"] == saipen_bridge.SAIPEN_SEAT_MISMATCH
    code, revoked = cli("revoke", "--participant", "astra")
    assert code == 0 and revoked["status"] == participants.REVOKED


def test_cli_refuses_without_project_identity(mail, tmp_path, capsys):
    A, _B = mail
    root = _project(tmp_path, identity=False)
    code = saimail_local.main(["saipen", "participant", "admit", "--participant", "astra",
                               "--workspace", str(A.root), "--project-root", str(root),
                               "--json"])
    refused = json.loads(capsys.readouterr().out)
    assert code == 1 and refused["status"] == saipen_bridge.SAIPEN_ADMISSION_REQUIRED
    assert not (A.root / participants.PARTICIPANTS_NAME).exists()
