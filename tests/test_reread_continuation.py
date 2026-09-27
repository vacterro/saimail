"""T-113 receiver re-read continuity regression matrix (Section 16).

Verifies all required invariants:
- unread message cannot use reopen
- first Open behavior unchanged
- valid READ message can explicitly reopen
- reopen leaves state READ
- reopen does not create a second lifecycle copy
- sealed bytes unchanged
- plaintext not persisted
- wrong recipient refused
- sender mismatch refused
- index mismatch refused
- receipt mismatch refused
- bundle corruption refused
- expired READ message refused
- tombstoned message refused
- exhausted budget refused
- successful reopen spends exactly the intended budget unit
- concurrent reopen is lifecycle-lock safe
- crash/interrupted state fails closed
- GUI selection remains metadata-only
- GUI refresh remains metadata-only
- double-click behavior unchanged
- CLI open unchanged
- CLI reopen is distinct
- no network/model/provider call
- workspace durability/restart preserves correct READ/reopen behavior
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

import saimail_local
from saimail import envelope, gui_adapter, postoffice, workspace
from sailang import SailangError

ROOT = Path(__file__).resolve().parent.parent
T = "2026-09-23T12:00:00Z"
SENDER = Ed25519PrivateKey.generate()
SENDER_SEAT = "ALICE"
RECIPIENT = X25519PrivateKey.generate()
SEAT = "BOB"


def _office_at(tmp_path, *, default_ttl=postoffice.DEFAULT_TTL_SECONDS, clock_fn=lambda: T):
    sender_reg = envelope.KeyRegistry({SENDER_SEAT: [SENDER.public_key()]})
    recip_reg = envelope.RecipientKeyRegistry({SEAT: [RECIPIENT.public_key()]})
    po = postoffice.PostOffice(tmp_path, seat=SEAT, sender_registry=sender_reg,
                               recipient_registry=recip_reg, clock=clock_fn,
                               default_ttl=default_ttl)
    return po


def _send_to(office, payload=b"test payload content 123", topic="ci", ttl=None):
    recip_pub = office.recipient_registry.resolves(office.seat, envelope.fingerprint(RECIPIENT.public_key()))
    container = envelope.seal(payload, sender_private_key=SENDER, sender_seat=SENDER_SEAT,
                              recipient_public_key=recip_pub, recipient_seat=office.seat,
                              kind="DISCOVERY", topic=topic, created=T, ttl=ttl)
    delivery = office.deliver(container)
    return delivery, payload


def _init_ws_pair(tmp_path):
    a_root = tmp_path / "ws_a"
    b_root = tmp_path / "ws_b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    a = workspace.load_workspace(a_root)
    b = workspace.load_workspace(b_root)
    card_a = workspace.export_identity_card(a)["card"]
    card_b = workspace.export_identity_card(b)["card"]
    workspace.add_recipient(a, "bob", card_b, b_root)
    workspace.add_recipient(b, "alice", card_a, a_root)
    return a, b


# 1. Unread message cannot use reopen
def test_unread_message_cannot_use_reopen(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.REOPEN_NOT_READ


# 2. First Open behavior unchanged
def test_first_open_behavior_unchanged(tmp_path):
    po = _office_at(tmp_path)
    delivery, payload = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    opened = session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert opened.plaintext == payload
    assert po.bundle_state(delivery.envelope_id) == postoffice.READ_STATE
    # Second open refused ALREADY_READ
    with pytest.raises(SailangError) as exc:
        session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.ALREADY_READ


# 3. Valid READ message can explicitly reopen
def test_valid_read_message_can_explicitly_reopen(tmp_path):
    po = _office_at(tmp_path)
    delivery, payload = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    # Reopen
    reopened = session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert reopened.plaintext == payload
    assert reopened.envelope_id == delivery.envelope_id


# 4. Reopen leaves state READ
def test_reopen_leaves_state_read(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert po.bundle_state(delivery.envelope_id) == postoffice.READ_STATE


# 5. Reopen does not create a second lifecycle copy
def test_reopen_does_not_create_second_copy(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    # inbox has 0 bundles
    inbox_bundles = [p for p in (po.mail_root / "inbox" / SEAT).iterdir() if p.is_dir()]
    assert len(inbox_bundles) == 0
    # read has exactly 1 bundle
    read_bundles = [p for p in (po.mail_root / "read" / SEAT).iterdir() if p.is_dir()]
    assert len(read_bundles) == 1


# 6. Sealed bytes unchanged
def test_sealed_bytes_unchanged(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    container_path = po.read_bundle(delivery.envelope_id) / postoffice.CONTAINER_NAME
    bytes_before = container_path.read_bytes()
    session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    bytes_after = container_path.read_bytes()
    assert bytes_before == bytes_after


# 7. Plaintext not persisted
def test_plaintext_not_persisted(tmp_path):
    po = _office_at(tmp_path)
    delivery, payload = _send_to(po, payload=b"super_secret_unique_string_XYZ987")
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    # Search all files under tmp_path for the plaintext
    for root, _, files in os.walk(tmp_path):
        for f in files:
            fp = Path(root) / f
            data = fp.read_bytes()
            assert b"super_secret_unique_string_XYZ987" not in data, f"Plaintext found in {fp}"


# 8. Wrong recipient refused
def test_wrong_recipient_refused(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    wrong_key = X25519PrivateKey.generate()
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=wrong_key)
    assert exc.value.code in ("RECIPIENT_KEY_NOT_ACCEPTED", "RECIPIENT_KEY_MISMATCH")


# 9. Sender mismatch refused
def test_sender_mismatch_refused(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    # Tamper sender registry in postoffice
    po.sender_registry = envelope.KeyRegistry({SENDER_SEAT: {}})
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.BUNDLE_INVALID


# 10. Index mismatch refused
def test_index_mismatch_refused(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    # Tamper index row
    index_file = po.mail_root / "index.jsonl"
    lines = index_file.read_bytes().splitlines()
    row = json.loads(lines[0])
    row["topic"] = "tampered_topic"
    index_file.write_bytes(postoffice._row_line_bytes(row))
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.INDEX_ROW_CONFLICT


# 11. Receipt mismatch refused
def test_receipt_mismatch_refused(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    receipt_file = po.read_bundle(delivery.envelope_id) / "receipt.json"
    r = json.loads(receipt_file.read_bytes())
    r["envelope_id"] = "sha256:" + "0" * 64
    receipt_file.write_bytes(postoffice._canonical_json_line(r))
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.RECEIPT_CORRUPT


# 12. Bundle corruption refused
def test_bundle_corruption_refused(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    container_file = po.read_bundle(delivery.envelope_id) / postoffice.CONTAINER_NAME
    container_file.write_bytes(container_file.read_bytes() + b"\n# corrupted")
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.BUNDLE_INVALID


# 13. Expired READ message refused
def test_expired_read_message_refused(tmp_path):
    po = _office_at(tmp_path, default_ttl=7 * 24 * 3600)
    delivery, _ = _send_to(po, ttl="7D")
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    # Advance clock past TTL
    po.clock = lambda: "2026-10-15T12:00:00Z"
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.ALREADY_EXPIRED


# 14. Tombstoned message refused
def test_tombstoned_message_refused(tmp_path):
    po = _office_at(tmp_path, default_ttl=7 * 24 * 3600)
    delivery, _ = _send_to(po, ttl="7D")
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    # Sweep expires it and creates tombstone
    sweep_res = po.sweep_expired(now="2026-10-15T12:00:00Z")
    assert sweep_res.expired == 1
    assert po.bundle_state(delivery.envelope_id) == postoffice.EXPIRED_STATE
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.ALREADY_EXPIRED


# 15. Exhausted budget refused
def test_exhausted_budget_refused(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=1)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert session.open_attempts_used == 1
    # open_budget was 1 and was used by open_message; reopen must be refused
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.OPEN_BUDGET_EXHAUSTED


# 16. Successful reopen spends exactly the intended budget unit
def test_successful_reopen_spends_budget_unit(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=3)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert session.open_attempts_used == 1
    session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert session.open_attempts_used == 2
    session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert session.open_attempts_used == 3
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.OPEN_BUDGET_EXHAUSTED


# 17. Concurrent reopen is lifecycle-lock safe
def test_concurrent_reopen_is_lifecycle_lock_safe(tmp_path):
    po = _office_at(tmp_path)
    delivery, payload = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=20)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)

    results = []
    errors = []

    def worker():
        try:
            s = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=10)
            opened = s.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
            results.append(opened.plaintext)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert len(results) == 5
    assert all(r == payload for r in results)


# 18. Crash/interrupted state fails closed
def test_crash_both_state_fails_closed(tmp_path):
    po = _office_at(tmp_path)
    delivery, _ = _send_to(po)
    session = postoffice.PostOfficeSession(po, scan_budget=10, open_budget=5)
    session.open_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    # Simulate crash copy in inbox
    shutil.copytree(po.read_bundle(delivery.envelope_id), po.inbox_bundle(delivery.envelope_id))
    assert po.bundle_state(delivery.envelope_id) == postoffice.BOTH
    with pytest.raises(SailangError) as exc:
        session.reopen_message(delivery.envelope_id, recipient_private_key=RECIPIENT)
    assert exc.value.code == postoffice.RECONCILIATION_REQUIRED


# 19. GUI selection remains metadata-only
def test_gui_selection_remains_metadata_only(tmp_path, monkeypatch):
    a, b = _init_ws_pair(tmp_path)
    sent = workspace.send_message(a, "bob", claim="gui metadata test")
    eid = sent["message"]["envelope_id"]
    workspace.open_message(b, eid)
    adapter = gui_adapter.GuiAdapter()
    adapter.open_workspace(b.root)
    adapter.refresh()

    calls = []
    monkeypatch.setattr(workspace, "reopen_message", lambda *args, **kwargs: calls.append("reopen"))
    monkeypatch.setattr(workspace, "open_message", lambda *args, **kwargs: calls.append("open"))

    adapter.select(eid)
    assert calls == []
    assert adapter.selected_id == eid
    assert adapter.selected_state == "READ"
    assert adapter.content() is None


# 20. GUI refresh remains metadata-only
def test_gui_refresh_remains_metadata_only(tmp_path, monkeypatch):
    a, b = _init_ws_pair(tmp_path)
    sent = workspace.send_message(a, "bob", claim="gui refresh test")
    eid = sent["message"]["envelope_id"]
    workspace.open_message(b, eid)
    adapter = gui_adapter.GuiAdapter()
    adapter.open_workspace(b.root)

    calls = []
    monkeypatch.setattr(workspace, "reopen_message", lambda *args, **kwargs: calls.append("reopen"))
    monkeypatch.setattr(workspace, "open_message", lambda *args, **kwargs: calls.append("open"))

    adapter.refresh()
    assert calls == []


# 21. Double-click behavior unchanged
def test_double_click_behavior_unchanged():
    pytest.importorskip("PySide6.QtWidgets")
    from saimail import gui_app
    QtCore = pytest.importorskip("PySide6.QtCore")
    QtGui = pytest.importorskip("PySide6.QtGui")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    cls = gui_app._build_window(QtCore, QtGui, QtWidgets)
    win = cls()
    try:
        assert win.inbox.receivers("2itemActivated(QListWidgetItem*)") == 0
    finally:
        win.close()


# 22. CLI open unchanged
def test_cli_open_unchanged(tmp_path):
    a, b = _init_ws_pair(tmp_path)
    sent = workspace.send_message(a, "bob", claim="cli open test")
    eid = sent["message"]["envelope_id"]

    # First open via CLI
    res = subprocess.run([sys.executable, str(ROOT / "saimail_local.py"), "open",
                          "--workspace", str(b.root), "--envelope", eid, "--json"],
                         capture_output=True, text=True, check=False)
    assert res.returncode == 0
    data = json.loads(res.stdout)
    assert data["ok"] is True
    assert data["status"] == "READ"
    assert data["record"]["claim"] == "cli open test"

    # Second open via CLI refused ALREADY_READ
    res2 = subprocess.run([sys.executable, str(ROOT / "saimail_local.py"), "open",
                           "--workspace", str(b.root), "--envelope", eid, "--json"],
                          capture_output=True, text=True, check=False)
    assert res2.returncode == 1
    data2 = json.loads(res2.stdout)
    assert data2["ok"] is False
    assert data2["status"] == "ALREADY_READ"


# 23. CLI reopen is distinct
def test_cli_reopen_is_distinct(tmp_path):
    a, b = _init_ws_pair(tmp_path)
    sent = workspace.send_message(a, "bob", claim="cli reopen test")
    eid = sent["message"]["envelope_id"]

    # Reopen on UNREAD refused REOPEN_NOT_READ
    res_unread = subprocess.run([sys.executable, str(ROOT / "saimail_local.py"), "reopen",
                                 "--workspace", str(b.root), "--envelope", eid, "--json"],
                                capture_output=True, text=True, check=False)
    assert res_unread.returncode == 1
    data_unread = json.loads(res_unread.stdout)
    assert data_unread["ok"] is False
    assert data_unread["status"] == "REOPEN_NOT_READ"

    # Open it
    workspace.open_message(b, eid)

    # Reopen on READ succeeds
    res_read = subprocess.run([sys.executable, str(ROOT / "saimail_local.py"), "reopen",
                               "--workspace", str(b.root), "--envelope", eid, "--json"],
                              capture_output=True, text=True, check=False)
    assert res_read.returncode == 0
    data_read = json.loads(res_read.stdout)
    assert data_read["ok"] is True
    assert data_read["status"] == "READ"
    assert data_read["command"] == "reopen"
    assert data_read["record"]["claim"] == "cli reopen test"


# 24. No network/model/provider call
def test_no_network_call_during_reopen(tmp_path):
    a, b = _init_ws_pair(tmp_path)
    sent = workspace.send_message(a, "bob", claim="zero network reopen test")
    eid = sent["message"]["envelope_id"]
    workspace.open_message(b, eid)

    probe = {"blocked": 0}
    with saimail_local.no_network(probe):
        result = workspace.reopen_message(b, eid)
    assert result["ok"] is True
    assert probe["blocked"] == 0


# 25. Workspace durability/restart preserves correct READ/reopen behavior
def test_workspace_durability_restart_preserves_reread(tmp_path):
    a, b = _init_ws_pair(tmp_path)
    sent = workspace.send_message(a, "bob", claim="durability reread test")
    eid = sent["message"]["envelope_id"]
    workspace.open_message(b, eid)

    # Fresh reload of workspace B from disk
    reloaded_b = workspace.load_workspace(b.root)
    result = workspace.reopen_message(reloaded_b, eid)
    assert result["ok"] is True
    assert result["status"] == "READ"
    assert result["record"]["claim"] == "durability reread test"
