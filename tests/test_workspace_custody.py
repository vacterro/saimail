"""V3-01 focused acceptance: workspace identity key custody at rest (spec/20).

Areas A-L of the V3-01 contract: protected identity metadata carries no raw
private bits, custody survives restart, missing/wrong/unavailable stores fail
closed, substitution is detected, copies without the store cannot load, no
silent regeneration/raw/environment fallback, explicit transactional migration
preserves exact fingerprints, and the unchanged V2-01 workflow runs under the
new custody mode. All automated cases use injectable stores; the canonical
suite never writes into the operator's real credential store.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)

from sailang import SailangError
from saimail import custody, workspace
from saimail.credentials import (
    InMemoryCredentialStore,
    KeyringCredentialStore,
    UnsuitableBackend,
)

ROOT = Path(__file__).resolve().parent.parent
MARKER = "v3-01 synthetic custody marker 4f7a"
RAW_MODE = custody.CUSTODY_RAW
PROTECTED = custody.CUSTODY_OS_STORE


def _run(args, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "saimail_local", *args],
                          cwd=cwd, capture_output=True, text=True, check=False)


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _identity_path(root) -> Path:
    return Path(root) / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME


def _identity_bytes(root) -> bytes:
    return _identity_path(root).read_bytes()


def _init(root, seat, store, mode=PROTECTED):
    return workspace.init_workspace(root, seat=seat, custody=mode, store=store)


def _handles(loaded: workspace.Workspace) -> dict:
    return {
        "sender": custody.handle_for(loaded.seat, custody.ROLE_SENDER, loaded.sender_kid),
        "recipient": custody.handle_for(loaded.seat, custody.ROLE_RECIPIENT,
                                        loaded.recipient_kid),
    }


def _stored_hexes(store) -> list[str]:
    return sorted(str(value) for value in store._data.values())


def _raw_key_hits(root, needles) -> list[str]:
    hits = []
    for path in Path(root).rglob("*"):
        if path.is_file():
            blob = path.read_bytes()
            for needle in needles:
                if needle.encode("utf-8") in blob:
                    hits.append(str(path))
    return hits


class _UnsuitableStore(InMemoryCredentialStore):
    """Answers like a plaintext file keyring would; still must be refused."""

    def check_backend(self):
        raise UnsuitableBackend("the selected backend is not a persistent store")


class _LyingStore(InMemoryCredentialStore):
    """Returns a substituted value for one handle after it was written."""

    def __init__(self, lie_handle, **kwargs):
        super().__init__(**kwargs)
        self._lie_handle = lie_handle

    def get(self, handle):
        value = super().get(handle)
        if handle == self._lie_handle and value is not None:
            return Ed25519PrivateKey.generate().private_bytes(
                Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
        return value


# ------------------------------------------------- A. protected metadata


def test_protected_identity_file_carries_handles_not_private_bytes(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    created = _init(root, "SAIMAIL-A", store)
    assert created["status"] == workspace.CREATED
    assert created["identity"]["custody"] == PROTECTED
    identity = json.loads(_identity_bytes(root).decode("utf-8"))
    assert identity["schema"] == workspace.IDENTITY_SCHEMA_V2
    assert identity["version"] == workspace.IDENTITY_VERSION_V2
    assert "sender_private_key" not in identity and "recipient_private_key" not in identity
    needles = _stored_hexes(store)
    assert len(needles) == 2
    assert _raw_key_hits(root, needles) == []


def test_protected_keys_survive_restart_and_fingerprints_are_stable(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    one = workspace.load_workspace(root, store=store)
    two = workspace.load_workspace(root, store=store)
    assert one.custody == PROTECTED and two.custody == PROTECTED
    assert (one.sender_kid, one.recipient_kid) == (two.sender_kid, two.recipient_kid)
    card = workspace.identity_card(two)
    assert card["sender_kid"] == one.sender_kid
    assert card["recipient_kid"] == one.recipient_kid
    assert "private" not in json.dumps(card)


def test_legacy_raw_workspace_still_loads_and_is_labeled(tmp_path):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    loaded = workspace.load_workspace(root)
    assert loaded.custody == RAW_MODE
    raw_identity = json.loads(_identity_bytes(root).decode("utf-8"))
    assert raw_identity["schema"] == workspace.IDENTITY_SCHEMA
    assert "sender_private_key" in raw_identity
    card = workspace.identity_card(loaded)
    assert card["sender_kid"] == loaded.sender_kid


def test_unknown_custody_mode_is_refused(tmp_path):
    store = InMemoryCredentialStore()
    assert _code(workspace.init_workspace, tmp_path / "ws", seat="SAIMAIL-A",
                 custody="sideways", store=store) == workspace.BAD_INPUT
    assert store._data == {}


# ------------------------------------------------- B. failure semantics


def test_missing_sender_key_fails_closed(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    before = _identity_bytes(root)
    store.delete(_handles(workspace.load_workspace(root, store=store))["sender"])
    assert _code(workspace.load_workspace, root, store=store) == custody.CUSTODY_KEY_MISSING
    assert _identity_bytes(root) == before


def test_missing_recipient_key_fails_closed(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    store.delete(_handles(workspace.load_workspace(root, store=store))["recipient"])
    assert _code(workspace.load_workspace, root, store=store) == custody.CUSTODY_KEY_MISSING


def test_backend_failure_is_distinct_from_absence(tmp_path):
    failing = InMemoryCredentialStore(fail_on={"get"})
    root = tmp_path / "ws"
    empty = InMemoryCredentialStore()
    assert _code(workspace.init_workspace, root, seat="SAIMAIL-A", custody=PROTECTED,
                 store=failing) == custody.CUSTODY_ACCESS_FAILED
    assert not (root / workspace.MARKER_NAME).exists()
    set_failing = InMemoryCredentialStore(fail_on={"set"})
    assert _code(workspace.init_workspace, root, seat="SAIMAIL-A", custody=PROTECTED,
                 store=set_failing) == custody.CUSTODY_ACCESS_FAILED
    assert set_failing._data == {}
    _init(root, "SAIMAIL-A", empty)
    assert _code(workspace.load_workspace, root,
                 store=InMemoryCredentialStore()) == custody.CUSTODY_KEY_MISSING


def test_unsuitable_backend_is_refused_before_any_read(tmp_path):
    good = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", good)
    plaintext = _UnsuitableStore(initial=dict(good._data))
    assert _code(workspace.load_workspace, root,
                 store=plaintext) == custody.CUSTODY_BACKEND_UNSUITABLE
    assert _code(workspace.init_workspace, tmp_path / "ws2", seat="SAIMAIL-A",
                 custody=PROTECTED, store=plaintext) == custody.CUSTODY_BACKEND_UNSUITABLE
    assert plaintext._data == good._data


def test_unavailable_backend_is_refused(tmp_path):
    store = KeyringCredentialStore()
    store._keyring = None
    root = tmp_path / "ws"
    assert _code(workspace.init_workspace, root, seat="SAIMAIL-A", custody=PROTECTED,
                 store=store) == custody.CUSTODY_BACKEND_UNAVAILABLE
    assert not (root / workspace.MARKER_NAME).exists()


def test_substituted_key_is_detected(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    handle = _handles(workspace.load_workspace(root, store=store))["sender"]
    store.set(handle, Ed25519PrivateKey.generate().private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex())
    assert _code(workspace.load_workspace, root, store=store) == custody.CUSTODY_KEY_MISMATCH


def test_malformed_stored_value_is_a_mismatch_not_a_crash(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    handle = _handles(workspace.load_workspace(root, store=store))["recipient"]
    store.set(handle, "not-a-key")
    assert _code(workspace.load_workspace, root, store=store) == custody.CUSTODY_KEY_MISMATCH


# ------------------------------------------------- C. copies and fallbacks


def test_copied_workspace_without_the_store_cannot_load(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    copy_root = tmp_path / "copy"
    shutil.copytree(root, copy_root)
    identity_before = _identity_bytes(copy_root)
    assert _code(workspace.load_workspace, copy_root,
                 store=InMemoryCredentialStore()) == custody.CUSTODY_KEY_MISSING
    assert _identity_bytes(copy_root) == identity_before


def test_copied_workspace_with_the_store_is_the_same_identity(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    original = workspace.load_workspace(root, store=store)
    copy_root = tmp_path / "copy"
    shutil.copytree(root, copy_root)
    copied = workspace.load_workspace(copy_root, store=store)
    assert (copied.sender_kid, copied.recipient_kid) == (
        original.sender_kid, original.recipient_kid)


def test_no_silent_regeneration_or_raw_fallback_on_failure(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    handles = _handles(workspace.load_workspace(root, store=store))
    store.delete(handles["sender"])
    before = _identity_bytes(root)
    assert _code(workspace.init_workspace, root, seat="SAIMAIL-A",
                 custody=PROTECTED, store=store) == custody.CUSTODY_KEY_MISSING
    assert _code(workspace.init_workspace, root, seat="SAIMAIL-A",
                 custody=RAW_MODE, store=store) == custody.CUSTODY_KEY_MISSING
    assert _identity_bytes(root) == before
    assert handles["recipient"] in store._data


def test_no_environment_variable_fallback(tmp_path, monkeypatch):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    handles = _handles(workspace.load_workspace(root, store=store))
    store.delete(handles["sender"])
    plant = Ed25519PrivateKey.generate().private_bytes(
        Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    for name in ("SAIROUTE_API_KEY", "SAIMAIL_WORKSPACE_KEY", "SAIMAIL_CUSTODY_KEY"):
        monkeypatch.setenv(name, plant)
    assert _code(workspace.load_workspace, root, store=store) == custody.CUSTODY_KEY_MISSING


def test_handles_are_a_separate_namespace_from_sairoute(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    assert store._data, "the protected identity must have store entries"
    for handle in store._data:
        assert handle.startswith(custody.HANDLE_PREFIX)
        assert handle != "credential://9router/sairoute"
        assert "9router" not in handle


def test_init_over_a_raw_workspace_never_imports_it(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    before = _identity_bytes(root)
    again = workspace.init_workspace(root, seat="SAIMAIL-A", custody=PROTECTED,
                                     store=store)
    assert again["status"] == workspace.ALREADY_EXISTS
    assert again["identity"]["custody"] == RAW_MODE
    assert store._data == {}
    assert _identity_bytes(root) == before


def test_custody_module_has_no_network_surface():
    source = (ROOT / "saimail" / "custody.py").read_text(encoding="utf-8")
    for forbidden in ("import socket", "import urllib", "import http", "requests"):
        assert forbidden not in source


# ------------------------------------------------- D. migration


def test_migration_preserves_exact_fingerprints_and_removes_raw_bytes(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    before = workspace.load_workspace(root)
    result = workspace.migrate_workspace_custody(root, store=store)
    assert result["status"] == workspace.CUSTODY_MIGRATED
    after = workspace.load_workspace(root, store=store)
    assert after.custody == PROTECTED
    assert (after.sender_kid, after.recipient_kid) == (before.sender_kid,
                                                       before.recipient_kid)
    assert workspace.identity_card(after) == workspace.identity_card(before)
    raw_identity = _identity_bytes(root)
    assert b"sender_private_key" not in raw_identity
    assert _raw_key_hits(root, _stored_hexes(store)) == []


def test_migration_failure_preserves_the_usable_raw_workspace(tmp_path):
    store = InMemoryCredentialStore(fail_on={"set"})
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    before = workspace.load_workspace(root)
    before_bytes = _identity_bytes(root)
    assert _code(workspace.migrate_workspace_custody, root,
                 store=store) == custody.CUSTODY_ACCESS_FAILED
    assert _identity_bytes(root) == before_bytes
    after = workspace.load_workspace(root)
    assert after.custody == RAW_MODE
    assert (after.sender_kid, after.recipient_kid) == (before.sender_kid,
                                                       before.recipient_kid)
    assert store._data == {}


def test_migration_readback_mismatch_rolls_back_and_releases_entries(tmp_path):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    handle = custody.handle_for("SAIMAIL-A", custody.ROLE_SENDER,
                                workspace.load_workspace(root).sender_kid)
    store = _LyingStore(handle)
    before_bytes = _identity_bytes(root)
    assert _code(workspace.migrate_workspace_custody, root,
                 store=store) == custody.CUSTODY_KEY_MISMATCH
    assert _identity_bytes(root) == before_bytes
    assert store._data == {}, "entries created by the failed attempt are released"
    assert workspace.load_workspace(root).custody == RAW_MODE


def test_repeated_migration_is_named_already_protected(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    workspace.migrate_workspace_custody(root, store=store)
    identity_after_first = _identity_bytes(root)
    stored_after_first = dict(store._data)
    again = workspace.migrate_workspace_custody(root, store=store)
    assert again["status"] == custody.CUSTODY_ALREADY_PROTECTED
    assert again["ok"] is True
    assert _identity_bytes(root) == identity_after_first
    assert store._data == stored_after_first


# ------------------------------------------------- E. status


def test_custody_status_reports_mode_backend_and_loadability(tmp_path):
    store = InMemoryCredentialStore()
    raw_root = tmp_path / "raw"
    workspace.init_workspace(raw_root, seat="SAIMAIL-A")
    raw = workspace.custody_status(raw_root, store=store)
    assert raw["status"] == "OK"
    assert raw["custody"]["mode"] == RAW_MODE
    assert raw["custody"]["loadable"] is True
    assert raw["custody"]["handles"] is None

    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    protected = workspace.custody_status(root, store=store)
    assert protected["custody"]["mode"] == PROTECTED
    assert protected["custody"]["loadable"] is True
    assert protected["custody"]["load_error"] is None
    assert protected["custody"]["backend"] == "saimail.credentials.InMemoryCredentialStore"
    assert protected["custody"]["keys_present"] == {"sender": True, "recipient": True}

    store.delete(_handles(workspace.load_workspace(root, store=store))["sender"])
    broken = workspace.custody_status(root, store=store)
    assert broken["status"] == "OK"
    assert broken["custody"]["loadable"] is False
    assert broken["custody"]["load_error"] == custody.CUSTODY_KEY_MISSING
    assert broken["custody"]["keys_present"]["sender"] is False
    assert broken["custody"]["keys_present"]["recipient"] is True


# ------------------------------------------------- F. privacy of outputs


def test_results_and_errors_never_carry_private_material(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    secrets = _stored_hexes(store)
    loaded = workspace.load_workspace(root, store=store)
    results = [
        json.dumps(workspace.init_workspace(root, seat="SAIMAIL-A", custody=PROTECTED,
                                            store=store)),
        json.dumps(workspace.identity_card(loaded)),
        json.dumps(workspace.custody_status(root, store=store)),
        workspace.render_command(workspace.custody_status(root, store=store)),
    ]
    store.delete(_handles(loaded)["sender"])
    error_text = ""
    try:
        workspace.load_workspace(root, store=store)
    except SailangError as exc:
        error_text = f"{exc.code}: {exc.detail}"
    results.append(error_text)
    for secret in secrets:
        for text in results:
            assert secret not in text


# ------------------------------------------------- G. workflow acceptance


def _office_workflow(tmp_path, store):
    a_root, b_root = tmp_path / "ws-a", tmp_path / "ws-b"
    _init(a_root, "SAIMAIL-A", store)
    _init(b_root, "SAIMAIL-B", store)
    A = workspace.load_workspace(a_root, store=store)
    B = workspace.load_workspace(b_root, store=store)
    card_a = tmp_path / "a.card.json"
    card_b = tmp_path / "b.card.json"
    workspace.export_identity_card(A, card_a)
    workspace.export_identity_card(B, card_b)
    workspace.add_recipient(A, "bob", json.loads(card_b.read_text(encoding="utf-8")), b_root)
    workspace.add_recipient(B, "alice", json.loads(card_a.read_text(encoding="utf-8")), a_root)
    sent = workspace.send_message(A, "bob", claim="protected custody proof " + MARKER)
    B_restart = workspace.load_workspace(b_root, store=store)
    listing = workspace.list_inbox(B_restart)
    opened = workspace.open_message(B_restart, sent["message"]["envelope_id"])
    replay = workspace.redeliver_message(A, sent["message"]["envelope_id"])
    return a_root, b_root, sent, listing, opened, replay


def test_protected_workflow_acceptance_with_injected_store(tmp_path):
    store = InMemoryCredentialStore()
    a_root, b_root, sent, listing, opened, replay = _office_workflow(tmp_path, store)
    assert sent["status"] == "ACCEPTED"
    assert sent["identity"]["custody"] == PROTECTED
    assert len(listing["items"]) == 1
    assert listing["items"][0]["state"] == "UNREAD"
    assert listing["items"][0]["envelope_id"] == sent["message"]["envelope_id"]
    assert opened["record"]["claim"] == "protected custody proof " + MARKER
    assert replay["status"] == "DUPLICATE"
    assert replay["message"]["received_at"] == sent["message"]["received_at"]
    assert MARKER not in json.dumps(listing)
    needles = _stored_hexes(store)
    assert needles
    for root in (a_root, b_root):
        assert _raw_key_hits(root, needles) == []
    assert MARKER.encode("utf-8") not in _identity_bytes(a_root)


def test_migrated_workspaces_keep_the_unchanged_workflow(tmp_path):
    store = InMemoryCredentialStore()
    a_root, b_root = tmp_path / "ws-a", tmp_path / "ws-b"
    workspace.init_workspace(a_root, seat="SAIMAIL-A")
    workspace.init_workspace(b_root, seat="SAIMAIL-B")
    A = workspace.load_workspace(a_root)
    B = workspace.load_workspace(b_root)
    card_a = tmp_path / "a.card.json"
    card_b = tmp_path / "b.card.json"
    workspace.export_identity_card(A, card_a)
    workspace.export_identity_card(B, card_b)
    workspace.add_recipient(A, "bob", json.loads(card_b.read_text(encoding="utf-8")), b_root)
    workspace.add_recipient(B, "alice", json.loads(card_a.read_text(encoding="utf-8")), a_root)
    pre = workspace.send_message(A, "bob", claim="pre-migration message",
                                 subject="pre", topic="pre")
    assert pre["status"] == "ACCEPTED"
    a_kid_before = A.sender_kid
    workspace.migrate_workspace_custody(a_root, store=store)
    workspace.migrate_workspace_custody(b_root, store=store)
    A2 = workspace.load_workspace(a_root, store=store)
    B2 = workspace.load_workspace(b_root, store=store)
    assert A2.sender_kid == a_kid_before
    assert A2.custody == PROTECTED and B2.custody == PROTECTED
    listing = workspace.list_inbox(B2)
    assert {item["envelope_id"] for item in listing["items"]} == {
        pre["message"]["envelope_id"]}
    opened_pre = workspace.open_message(B2, pre["message"]["envelope_id"])
    assert opened_pre["record"]["claim"] == "pre-migration message"
    post = workspace.send_message(A2, "bob", claim="post-migration message",
                                  subject="post", topic="post")
    assert post["status"] == "ACCEPTED"
    listing = workspace.list_inbox(B2)
    assert {item["envelope_id"] for item in listing["items"]} == {
        pre["message"]["envelope_id"], post["message"]["envelope_id"]}
    opened = workspace.open_message(B2, post["message"]["envelope_id"])
    assert opened["record"]["claim"] == "post-migration message"
    replay = workspace.redeliver_message(A2, post["message"]["envelope_id"])
    assert replay["status"] == "DUPLICATE"


# ------------------------------------------------- H. scanner control


def test_raw_key_scanner_can_go_red(tmp_path):
    store = InMemoryCredentialStore()
    root = tmp_path / "ws"
    _init(root, "SAIMAIL-A", store)
    needles = _stored_hexes(store)
    assert _raw_key_hits(root, needles) == []
    (root / "planted.bin").write_text(needles[0], encoding="utf-8")
    assert _raw_key_hits(root, needles) == [str(root / "planted.bin")]


# ------------------------------------------------- I. CLI surface


def test_cli_custody_flags_and_refusals(tmp_path):
    bad = _run(["init", "--workspace", str(tmp_path / "ws"), "--seat", "SAIMAIL-A",
                "--custody", "sideways", "--json"])
    assert bad.returncode == 1
    assert json.loads(bad.stdout)["status"] == workspace.BAD_INPUT
    absent = _run(["custody", "migrate", "--workspace", str(tmp_path / "absent"),
                   "--json"])
    assert absent.returncode == 1
    assert json.loads(absent.stdout)["status"] == workspace.WORKSPACE_MISSING
    root = tmp_path / "raw"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    status = _run(["custody", "status", "--workspace", str(root), "--json"])
    assert status.returncode == 0, status.stdout + status.stderr
    payload = json.loads(status.stdout)
    assert payload["custody"]["mode"] == RAW_MODE
    assert payload["custody"]["loadable"] is True
