"""D2 focused acceptance: the D-054 first-run custody notice.

Areas: the notice is attached exactly to the creation of a new workspace, it
states the raw default honestly (storage location, copy consequence, os-store
opt-in, os-store claim boundary), the protected mode never claims raw storage,
ALREADY_EXISTS is not a first run, the result stays bounded valid JSON, the
human rendering shows it, later commands do not spam it, and no private key
material or secret path appears in any notice.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from saimail import custody, workspace
from saimail.credentials import InMemoryCredentialStore

ROOT = Path(__file__).resolve().parent.parent
RAW = custody.CUSTODY_RAW
PROTECTED = custody.CUSTODY_OS_STORE


def _run(args, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "saimail_local", *args],
                          cwd=cwd, capture_output=True, text=True, check=False)


def _notice_ids(result: dict) -> list:
    return [notice.get("id") for notice in result.get("notices") or []]


def test_implicit_raw_init_carries_the_raw_notice(tmp_path):
    result = workspace.init_workspace(tmp_path / "ws", seat="SAIMAIL-A")
    assert result["status"] == workspace.CREATED
    assert result["identity"]["custody"] == RAW
    assert _notice_ids(result) == [workspace.NOTICE_RAW_CUSTODY_DEFAULT]
    notice = result["notices"][0]
    assert notice["schema"] == workspace.NOTICE_SCHEMA
    assert notice["version"] == workspace.NOTICE_VERSION
    assert notice["mode"] == RAW
    message = notice["message"]
    for needle in ("raw custody is the default",
                   "identity/identity.json",
                   "copying the workspace directory copies the identity",
                   "--custody os-store",
                   "OS credential store",
                   "workspace-directory-copy exposure",
                   "same OS user",
                   "admin/kernel compromise"):
        assert needle in message, f"the raw notice does not state {needle!r}"
    assert "protects fully" not in message and "all threats" not in message


def test_explicit_raw_init_has_the_same_warning_semantics(tmp_path):
    implicit = workspace.init_workspace(tmp_path / "a", seat="SAIMAIL-A")
    explicit = workspace.init_workspace(tmp_path / "b", seat="SAIMAIL-A",
                                        custody=RAW)
    assert _notice_ids(explicit) == _notice_ids(implicit)
    assert explicit["notices"] == implicit["notices"]


def test_os_store_init_does_not_claim_raw_storage(tmp_path):
    store = InMemoryCredentialStore()
    result = workspace.init_workspace(tmp_path / "ws", seat="SAIMAIL-A",
                                      custody=PROTECTED, store=store)
    assert result["status"] == workspace.CREATED
    assert result["identity"]["custody"] == PROTECTED
    assert _notice_ids(result) == [workspace.NOTICE_OS_STORE_CUSTODY]
    message = result["notices"][0]["message"]
    assert "handles and public material only" in message
    assert "identity/identity.json" not in message
    assert "raw custody is the default" not in message
    assert "same OS user" in message and "admin/kernel compromise" in message
    assert "no hardware custody" in message


def test_already_exists_is_not_a_first_run(tmp_path):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    again = workspace.init_workspace(root, seat="SAIMAIL-A")
    assert again["status"] == workspace.ALREADY_EXISTS
    assert not again.get("notices")


def test_later_commands_do_not_spam_the_notice(tmp_path):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="SAIMAIL-A")
    loaded = workspace.load_workspace(root)
    assert not workspace.list_inbox(loaded).get("notices")
    assert not workspace.list_recipients(loaded).get("notices")
    assert not workspace.custody_status(root).get("notices")
    assert not workspace.export_identity_card(loaded).get("notices")


def test_notice_is_bounded_json_without_secret_material(tmp_path):
    store = InMemoryCredentialStore()
    raw = workspace.init_workspace(tmp_path / "raw", seat="SAIMAIL-A")
    protected = workspace.init_workspace(tmp_path / "prot", seat="SAIMAIL-B",
                                         custody=PROTECTED, store=store)
    blocks = json.dumps(raw) + json.dumps(protected)
    for result in (raw, protected):
        for notice in result["notices"]:
            assert set(notice) == {"schema", "version", "id", "mode", "message"}
            assert 0 < len(notice["message"]) <= 600
    assert "sender_private_key" not in blocks and "recipient_private_key" not in blocks
    assert "credential://9router" not in blocks
    stored = [str(value) for value in store._data.values()]
    for value in stored:
        assert value not in blocks
    identity = json.loads(
        (tmp_path / "raw" / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME)
        .read_text(encoding="utf-8"))
    assert identity["sender_private_key"] not in blocks


def test_human_rendering_shows_the_notice(tmp_path):
    result = workspace.init_workspace(tmp_path / "ws", seat="SAIMAIL-A")
    rendered = workspace.render_command(result)
    assert "NOTICE:" in rendered
    assert "raw custody is the default" in rendered


def test_cli_json_and_human_modes_carry_the_notice(tmp_path):
    root = tmp_path / "ws"
    as_json = _run(["init", "--workspace", str(root), "--seat", "SAIMAIL-A", "--json"])
    assert as_json.returncode == 0, as_json.stdout + as_json.stderr
    payload = json.loads(as_json.stdout)
    assert _notice_ids(payload) == [workspace.NOTICE_RAW_CUSTODY_DEFAULT]

    human = _run(["init", "--workspace", str(tmp_path / "ws2"), "--seat", "SAIMAIL-B"])
    assert human.returncode == 0, human.stdout + human.stderr
    assert "NOTICE:" in human.stdout
    assert "raw custody is the default" in human.stdout


def test_unknown_custody_mode_has_no_notice_and_no_workspace(tmp_path):
    result = _run(["init", "--workspace", str(tmp_path / "ws"), "--seat", "SAIMAIL-A",
                   "--custody", "sideways", "--json"])
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == workspace.BAD_INPUT
    assert not payload.get("notices")
    assert not (tmp_path / "ws" / workspace.MARKER_NAME).exists()
