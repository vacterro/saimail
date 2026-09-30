"""Public recipient setup must work without unlocking message custody.

These are isolated product controls, not enrolled peers or real-use evidence.
"""

import hashlib
import json
from pathlib import Path

import pytest

import saimail_local
from saimail import credentials, custody, workspace


class LockedStore(credentials.InMemoryCredentialStore):
    def __init__(self):
        super().__init__()
        self.locked = False
        self.reads = 0

    def get(self, handle):
        self.reads += 1
        if self.locked:
            raise credentials.BackendError("locked test store")
        return super().get(handle)


@pytest.fixture
def pair(tmp_path, monkeypatch):
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)
    store = LockedStore()
    credentials.set_credential_store(store)
    try:
        a, b = tmp_path / "a", tmp_path / "b"
        for root, seat in ((a, "alpha"), (b, "beta")):
            workspace.init_workspace(root, seat=seat, custody=custody.CUSTODY_OS_STORE)
        card = tmp_path / "beta.card.json"
        workspace.export_identity_card(workspace.load_workspace(b), card)
        store.locked = True
        store.reads = 0
        yield a, b, card, store
    finally:
        credentials.set_credential_store(None)


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def cli(capsys, *args):
    code = saimail_local.main([*map(str, args), "--json"])
    captured = capsys.readouterr()
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["network_attempts"] == 0
    return code, result


def add(capsys, a, b, card, alias="beta"):
    return cli(capsys, "recipient", "add", "--workspace", a, "--alias", alias,
               "--card", card, "--peer-workspace", b)


def test_empty_recipient_list_works_with_locked_custody(pair, capsys):
    a, b, _, store = pair
    before = snapshot(a), snapshot(b)
    code, result = cli(capsys, "recipient", "list", "--workspace", a)
    assert code == 0 and result["status"] == "OK"
    assert result["recipients"] == []
    assert store.reads == 0
    assert before == (snapshot(a), snapshot(b))


def test_add_and_list_use_public_metadata_without_any_full_load(pair, capsys, monkeypatch):
    a, b, card, store = pair
    before_b = snapshot(b)

    def never(*args, **kwargs):
        raise AssertionError("public recipient management attempted a private-key load")

    monkeypatch.setattr(workspace, "load_workspace", never)
    code, result = add(capsys, a, b, card)
    assert code == 0 and result["status"] == workspace.RECIPIENT_ADDED
    code, listed = cli(capsys, "recipient", "list", "--workspace", a)
    assert code == 0 and listed["recipients"][0]["seat"] == "beta"
    before_a = snapshot(a)
    code, repeated = add(capsys, a, b, card)
    assert code == 0 and repeated["status"] == workspace.RECIPIENT_ALREADY_REGISTERED
    assert snapshot(a) == before_a and snapshot(b) == before_b
    assert store.reads == 0


@pytest.mark.parametrize("damage", ["missing", "directory", "encoding", "json", "array", "shape"])
@pytest.mark.parametrize("locked", [False, True])
def test_bad_card_returns_structured_error_without_mutation(pair, capsys, damage, locked):
    a, b, card, store = pair
    store.locked = locked
    if damage == "missing":
        card.unlink()
    elif damage == "directory":
        card.unlink()
        card.mkdir()
    elif damage == "encoding":
        card.write_bytes(b"\xff\xfe")
    elif damage == "json":
        card.write_text("{bad", encoding="utf-8")
    elif damage == "array":
        card.write_text("[]", encoding="utf-8")
    else:
        card.write_text("{}", encoding="utf-8")
    before = snapshot(a), snapshot(b)
    code, result = add(capsys, a, b, card)
    assert code == 1 and result["status"] == workspace.RECIPIENT_MALFORMED
    assert result["operator_action_required"] is True
    assert store.reads == 0
    assert before == (snapshot(a), snapshot(b))


def test_card_read_permission_error_is_structured(pair, capsys, monkeypatch):
    a, b, card, store = pair
    original = Path.read_text

    def denied(path, *args, **kwargs):
        if path == card:
            raise PermissionError("card access denied")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied)
    before = snapshot(a), snapshot(b)
    code, result = add(capsys, a, b, card)
    assert code == 1 and result["status"] == workspace.RECIPIENT_MALFORMED
    assert store.reads == 0
    assert before == (snapshot(a), snapshot(b))


@pytest.mark.parametrize("damage, expected", [
    ("missing", workspace.DELIVERY_TARGET_UNAVAILABLE),
    ("seat", workspace.RECIPIENT_IDENTITY_MISMATCH),
    ("fingerprint", workspace.INVALID_WORKSPACE),
])
def test_peer_public_identity_checks_remain_fail_closed(pair, capsys, damage, expected):
    a, b, card, store = pair
    marker = b / workspace.MARKER_NAME
    if damage == "missing":
        marker.unlink()
    else:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        payload["seat" if damage == "seat" else "sender_kid"] = (
            "other" if damage == "seat" else "sha256:" + "0" * 64)
        marker.write_text(json.dumps(payload), encoding="utf-8")
    before = snapshot(a), snapshot(b)
    code, result = add(capsys, a, b, card)
    assert code == 1 and result["status"] == expected
    assert store.reads == 0
    assert before == (snapshot(a), snapshot(b))


@pytest.mark.parametrize("command", ["list", "add"])
def test_local_public_identity_corruption_still_refuses(pair, capsys, command):
    a, b, card, store = pair
    marker = a / workspace.MARKER_NAME
    payload = json.loads(marker.read_text(encoding="utf-8"))
    payload["recipient_kid"] = "sha256:" + "0" * 64
    marker.write_text(json.dumps(payload), encoding="utf-8")
    before = snapshot(a), snapshot(b)
    code, result = (add(capsys, a, b, card) if command == "add" else
                    cli(capsys, "recipient", "list", "--workspace", a))
    assert code == 1 and result["status"] == workspace.INVALID_WORKSPACE
    assert store.reads == 0
    assert before == (snapshot(a), snapshot(b))


def test_recipient_alias_conflict_cannot_overwrite_the_mapping(pair, capsys):
    a, b, card, store = pair
    assert add(capsys, a, b, card)[0] == 0
    other = a.parent / "other"
    store.locked = False
    workspace.init_workspace(other, seat="other", custody=custody.CUSTODY_OS_STORE)
    card = a.parent / "other.card.json"
    workspace.export_identity_card(workspace.load_workspace(other), card)
    store.locked = True
    store.reads = 0
    before = snapshot(a), snapshot(b)
    code, result = add(capsys, a, other, card)
    assert code == 1 and result["status"] == workspace.RECIPIENT_CONFLICT
    assert store.reads == 0 and before == (snapshot(a), snapshot(b))


def test_send_still_requires_private_custody_after_public_setup(pair, capsys):
    a, b, card, store = pair
    assert add(capsys, a, b, card)[0] == 0 and store.reads == 0
    before = snapshot(a), snapshot(b)
    code, result = cli(capsys, "send", "--workspace", a, "--to", "beta", "--claim", "not sent")
    assert code == 1 and result["status"] == custody.CUSTODY_ACCESS_FAILED
    assert store.reads > 0
    assert before == (snapshot(a), snapshot(b))
