"""The operator can lose a password, restore identity and read the same sealed mail."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace

import pytest

from sailang import SailangError
from saimail import gui_adapter, keyvault, workspace

PASSWORD = "five random words should go here 3948"
NEW_PASSWORD = "another independent long passphrase 6327"


def test_stale_loaded_identity_cannot_overwrite_another_mailbox(tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    workspace.init_workspace(first, seat="operator")
    workspace.init_workspace(second, seat="operator")
    stale = replace(workspace.load_workspace(first), root=second)
    identity_file = second / "identity" / "identity.json"
    before = identity_file.read_bytes()
    with pytest.raises(SailangError, match=keyvault.VAULT_INVALID):
        keyvault.protect(stale, PASSWORD)
    with pytest.raises(SailangError, match=keyvault.VAULT_INVALID):
        keyvault.recovery_backup(stale, tmp_path / "bad-backup.json")
    assert identity_file.read_bytes() == before and not (tmp_path / "bad-backup.json").exists()


def test_encrypted_identity_unlock_backup_recovery_and_old_mail(tmp_path):
    a_root, b_root = tmp_path / "agent", tmp_path / "operator"
    workspace.init_workspace(a_root, seat="agent")
    workspace.init_workspace(b_root, seat="operator", custody="master-key", password=PASSWORD)
    a = workspace.load_workspace(a_root)
    b = workspace.load_workspace(b_root, password=PASSWORD)
    workspace.add_recipient(a, "human", workspace.identity_card(b), b_root)
    workspace.add_recipient(b, "agent", workspace.identity_card(a), a_root)
    eid = workspace.send_message(a, "human", claim="A useful private finding for the operator.")["message"]["envelope_id"]
    # Locked awareness and delivery require no master password.
    assert workspace.query_inbox(workspace.load_workspace_headers(b_root))["match_count"] == 1
    with pytest.raises(SailangError, match=keyvault.MASTER_KEY_REQUIRED):
        workspace.load_workspace(b_root)
    with pytest.raises(SailangError, match=keyvault.MASTER_KEY_INVALID):
        workspace.load_workspace(b_root, password="wrong password")
    backup = keyvault.recovery_backup(b, tmp_path / "offline-recovery.json")
    raw = (tmp_path / "offline-recovery.json").read_bytes()
    assert PASSWORD.encode() not in raw and backup["recovery_key"].encode() not in raw
    restored_root = tmp_path / "restored"
    keyvault.restore(backup["path"], restored_root, backup["recovery_key"], NEW_PASSWORD)
    restored = workspace.load_workspace(restored_root, password=NEW_PASSWORD)
    assert restored.sender_kid == b.sender_kid and restored.recipient_kid == b.recipient_kid
    workspace.add_recipient(restored, "agent", workspace.identity_card(a), a_root)
    shutil.copytree(b_root / "mail", restored_root / "mail")
    assert workspace.open_message(restored, eid)["record"]["claim"] == "A useful private finding for the operator."
    with pytest.raises(SailangError, match=keyvault.BACKUP_CONFLICT):
        keyvault.restore(backup["path"], restored_root, backup["recovery_key"], NEW_PASSWORD)


def test_wrong_recovery_key_creates_no_mailbox(tmp_path):
    root = tmp_path / "original"
    workspace.init_workspace(root, seat="operator", custody="master-key", password=PASSWORD)
    b = workspace.load_workspace(root, password=PASSWORD)
    backup = keyvault.recovery_backup(b, tmp_path / "recovery.json")
    with pytest.raises(SailangError, match=keyvault.MASTER_KEY_INVALID):
        keyvault.restore(backup["path"], tmp_path / "new", "wrong recovery key", NEW_PASSWORD)
    assert not (tmp_path / "new").exists()


def test_password_change_preserves_identity_and_rejects_old_password(tmp_path):
    root = tmp_path / "box"
    workspace.init_workspace(root, seat="operator")
    old = workspace.load_workspace(root)
    keyvault.protect(old, PASSWORD)
    protected = workspace.load_workspace(root, password=PASSWORD)
    keyvault.protect(protected, NEW_PASSWORD)
    new = workspace.load_workspace(root, password=NEW_PASSWORD)
    assert old.recipient_kid == protected.recipient_kid == new.recipient_kid
    identity = (root / "identity" / "identity.json").read_text(encoding="utf-8")
    assert "sender_private_key" not in identity and "recipient_private_key" not in identity
    with pytest.raises(SailangError, match=keyvault.MASTER_KEY_INVALID):
        workspace.load_workspace(root, password=PASSWORD)


def test_tamper_is_refused_before_expensive_or_unbounded_derivation(tmp_path, monkeypatch):
    root = tmp_path / "box"
    workspace.init_workspace(root, seat="operator", custody="master-key", password=PASSWORD)
    path = root / "identity" / "identity.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["vault"]["kdf"]["n"] = 2 ** 40
    path.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(keyvault, "_derive", lambda *args: pytest.fail("unbounded derivation"))
    with pytest.raises(SailangError, match=keyvault.VAULT_INVALID):
        workspace.load_workspace(root, password=PASSWORD)


def test_header_reads_never_derive_or_unlock(tmp_path, monkeypatch):
    root = tmp_path / "box"
    workspace.init_workspace(root, seat="operator", custody="master-key", password=PASSWORD)
    monkeypatch.setattr(keyvault, "_derive", lambda *args: pytest.fail("unexpected key derivation"))
    view = workspace.load_workspace_headers(root)
    assert view.custody == "master-key"
    assert workspace.query_inbox(view)["match_count"] == 0
    assert workspace.custody_status(root)["custody"]["load_error"] == keyvault.MASTER_KEY_REQUIRED


def test_short_password_is_refused_without_creating_identity(tmp_path):
    with pytest.raises(SailangError, match=keyvault.MASTER_KEY_WEAK):
        workspace.init_workspace(tmp_path / "box", seat="operator", custody="master-key", password="short")
    assert not (tmp_path / "box").exists()


def test_adapter_lock_clears_plaintext_and_can_unlock_same_mailbox(tmp_path):
    model = gui_adapter.GuiAdapter()
    assert model.create_workspace(tmp_path / "box", "operator", "master-key", password=PASSWORD)["ok"]
    model._opened["example"] = {"claim": "private content"}
    model.lock_workspace()
    assert model.locked and model._opened == {} and model.content() is None
    assert model.send_reason() == "Unlock the mailbox before sending."
    assert not model.open_selected()["ok"]
    assert model.unlock_workspace(PASSWORD)["ok"] and not model.locked
    model.close_workspace()
    assert model.open_workspace(tmp_path / "box")["code"] == "MAILBOX_LOCKED"


def test_backup_overwrite_and_same_folder_are_refused(tmp_path):
    root = tmp_path / "box"
    workspace.init_workspace(root, seat="operator", custody="master-key", password=PASSWORD)
    box = workspace.load_workspace(root, password=PASSWORD)
    with pytest.raises(SailangError, match=keyvault.BACKUP_CONFLICT):
        keyvault.recovery_backup(box, root / "backup.json")
    keyvault.recovery_backup(box, tmp_path / "backup.json")
    with pytest.raises(SailangError, match=keyvault.BACKUP_CONFLICT):
        keyvault.recovery_backup(box, tmp_path / "backup.json")
