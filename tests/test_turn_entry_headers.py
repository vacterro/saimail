"""T-117: the SAIPEN turn-entry read, and every header-only read, holds no secret.

SAIPEN T-1497 runs ``saimail-local --json saipen telegrams`` at each automatic
turn entry and reports counts. The index scan needs public keys only, yet the
read used the full workspace load, which in os-store custody retrieved both
private keys from the OS credential store on every call; a locked or prompting
store turned the count into an error. ``load_workspace_headers`` keeps every
public check of the full load, builds no private key and never reads the store.
Operations that use a key keep the full load and still fail closed.
"""

from __future__ import annotations

import json
from dataclasses import fields

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

import saimail_local
from sailang import SailangError
from saimail import credentials, custody, postoffice, saipen_bridge, workspace

LINEAGE = "lineage-" + "cd" * 16
PROTECTED = custody.CUSTODY_OS_STORE


class _Store(credentials.InMemoryCredentialStore):
    """Counts secret reads; ``locked`` fails every read like a locked keychain."""

    def __init__(self):
        super().__init__()
        self.reads = 0
        self.locked = False

    def get(self, handle):
        self.reads += 1
        if self.locked:
            raise credentials.BackendError("the credential store is locked")
        return super().get(handle)


@pytest.fixture(autouse=True)
def _no_ambient_actor(monkeypatch):
    # An agent running this suite under SAIPEN may carry SAIPEN_AGENT; the seat
    # these controls act as must come from their own fixtures.
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)


@pytest.fixture
def store():
    active = _Store()
    credentials.set_credential_store(active)
    yield active
    credentials.set_credential_store(None)


def _project(tmp_path, *, agent="builder", task="T-7"):
    memory = tmp_path / "project" / ".saipen"
    memory.mkdir(parents=True)
    (memory / "STATE.md").write_text(
        f"---\nphase: BUILD\ntask: {task}\nagent: {agent}\nlast_event: 40\n---\n",
        encoding="utf-8")
    (memory / "IDENTITY.md").write_text(f"---\nproject_lineage: {LINEAGE}\n---\n",
                                        encoding="utf-8")
    return memory.parent


def _pair(tmp_path, store, *, mode=PROTECTED):
    """A reviewer that sends and a builder that receives, both in ``mode`` custody."""
    workspace.init_workspace(tmp_path / "reviewer", seat="reviewer", custody=mode, store=store)
    workspace.init_workspace(tmp_path / "builder", seat="builder", custody=mode, store=store)
    sender = workspace.load_workspace(tmp_path / "reviewer", store=store)
    receiver = workspace.load_workspace(tmp_path / "builder", store=store)
    workspace.add_recipient(sender, "builder", workspace.identity_card(receiver), receiver.root)
    workspace.add_recipient(receiver, "reviewer", workspace.identity_card(sender), sender.root)
    for number, topic in enumerate(("T-7", "T-8")):
        workspace.send_message(sender, "builder", claim=f"private finding {number}",
                               topic=topic, kind="DISCOVERY")
    return sender, receiver


def _cli(capsys, *argv):
    code = saimail_local.main([*argv, "--json"])
    return code, json.loads(capsys.readouterr().out)


def test_the_header_view_holds_no_private_key_and_offers_no_key_operation(tmp_path, store):
    _pair(tmp_path, store)
    store.reads = 0
    view = workspace.load_workspace_headers(tmp_path / "builder")
    assert store.reads == 0
    assert {f.name for f in fields(view)} == {
        "root", "seat", "created", "recipient_public_key", "sender_kid", "recipient_kid",
        "custody"}
    assert not any(isinstance(getattr(view, f.name), (Ed25519PrivateKey, X25519PrivateKey))
                   for f in fields(view))
    assert not hasattr(view, "identity")
    assert view.seat == "builder" and view.custody == PROTECTED


def test_no_header_read_touches_the_credential_store(tmp_path, store, capsys, monkeypatch):
    root = _project(tmp_path)
    _pair(tmp_path, store)
    builder = str(tmp_path / "builder")
    monkeypatch.setenv("SAIPEN_AGENT", "builder")

    def never(*_args, **_kwargs):
        raise AssertionError("a header-only read reached the credential store")

    with monkeypatch.context() as guard:
        guard.setattr(custody, "read_key", never)
        guard.setattr(custody, "classify_backend", never)
        store.reads = 0
        for argv in (("saipen", "telegrams", "--workspace", builder, "--scan-budget", "200"),
                     ("inbox", "--workspace", builder),
                     ("inbox", "--workspace", builder, "--state", "UNREAD"),
                     ("saipen", "enter", "--workspace", builder, "--project-root", str(root)),
                     ("saipen", "brief", "--workspace", builder, "--project-root", str(root))):
            code, result = _cli(capsys, *argv)
            assert code == 0 and result["ok"] is True, (argv, result)
        assert store.reads == 0


def test_a_locked_store_still_yields_counts_but_never_an_open(tmp_path, store, capsys):
    """Red control of the T-117 defect: before the fix this read returned
    CUSTODY_ACCESS_FAILED and SAIPEN reported ERROR instead of the counts."""
    _pair(tmp_path, store)
    builder = str(tmp_path / "builder")
    store.locked = True
    code, counted = _cli(capsys, "saipen", "telegrams", "--workspace", builder,
                         "--scan-budget", "200")
    assert code == 0 and counted["match_count"] == 2
    envelope_id = counted["items"][0]["envelope_id"]

    # Anything that needs a key still performs the full load and fails closed.
    code, refused = _cli(capsys, "open", "--workspace", builder, "--envelope", envelope_id)
    assert code == 1 and refused["status"] == custody.CUSTODY_ACCESS_FAILED
    store.locked = False
    code, still = _cli(capsys, "saipen", "telegrams", "--workspace", builder)
    assert code == 0 and still["match_count"] == 2


def test_header_view_results_equal_the_full_load_results(tmp_path, store):
    _pair(tmp_path, store, mode=custody.CUSTODY_RAW)
    full = workspace.load_workspace(tmp_path / "builder")
    view = workspace.load_workspace_headers(tmp_path / "builder")
    assert workspace.list_inbox(view) == workspace.list_inbox(full)
    for kwargs in ({}, {"topic": "T-7"}, {"state": postoffice.UNREAD, "scan_budget": 1}):
        assert workspace.query_inbox(view, **kwargs) == workspace.query_inbox(full, **kwargs)
    assert saipen_bridge.telegrams(view) == saipen_bridge.telegrams(full)
    root = _project(tmp_path)
    state, identity = root / ".saipen" / "STATE.md", root / ".saipen" / "IDENTITY.md"
    # A brief begun on one load continues on the other: the context witness agrees.
    first = saipen_bridge.work_brief(full, state, identity, scan_budget=1)
    token = first["brief"]["continuation"]
    assert token is not None
    rest = saipen_bridge.work_brief(view, state, identity, scan_budget=1,
                                    cursor=token["cursor"], context=token["context"])
    assert rest["brief"]["context"] == first["brief"]["context"]


def _code(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _rewrite(path, **changes):
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.update(changes)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize("mode", [custody.CUSTODY_RAW, PROTECTED])
def test_every_public_check_refuses_the_header_view_exactly_like_the_full_load(
        tmp_path, store, mode):
    workspace.init_workspace(tmp_path / "ws", seat="builder", custody=mode, store=store)
    marker = tmp_path / "ws" / workspace.MARKER_NAME
    identity = tmp_path / "ws" / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME
    good_marker, good_identity = marker.read_bytes(), identity.read_bytes()
    other = json.loads((tmp_path / "ws" / workspace.MARKER_NAME).read_text(encoding="utf-8"))
    corruptions = [
        lambda: _rewrite(marker, sender_kid="sha256:" + "0" * 64),
        lambda: _rewrite(identity, seat="intruder"),
        lambda: _rewrite(identity, schema="SAIMAIL_LOCAL_IDENTITY_9"),
        lambda: _rewrite(identity, stray=True),
        lambda: (tmp_path / "ws" / workspace.PEERS_NAME).write_text("[]", encoding="utf-8"),
        lambda: marker.unlink(),
    ]
    if mode == PROTECTED:
        corruptions.append(lambda: _rewrite(identity, recipient_kid=other["sender_kid"]))
    for corrupt in corruptions:
        corrupt()
        header_code = _code(workspace.load_workspace_headers, tmp_path / "ws")
        assert header_code in (workspace.INVALID_WORKSPACE, workspace.WORKSPACE_MISSING)
        assert header_code == _code(workspace.load_workspace, tmp_path / "ws", store=store)
        marker.write_bytes(good_marker)
        identity.write_bytes(good_identity)
        workspace._write_peers(tmp_path / "ws", {})


def test_the_private_identity_proof_stays_with_the_key_using_load(tmp_path):
    """The boundary, stated: a raw identity whose private key no longer matches the
    marker still lists headers, and every key-using load refuses it."""
    workspace.init_workspace(tmp_path / "ws", seat="builder")
    identity = tmp_path / "ws" / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME
    _rewrite(identity, recipient_private_key="11" * 32)
    assert workspace.load_workspace_headers(tmp_path / "ws").seat == "builder"
    assert _code(workspace.load_workspace, tmp_path / "ws") == workspace.INVALID_WORKSPACE


def test_the_saipen_turn_entry_contract_fields_are_pinned(tmp_path, store, capsys):
    """SAIPEN T-1497 parses exactly these fields; a SAIMAIL change must not move them."""
    _pair(tmp_path, store)
    code, answer = _cli(capsys, "saipen", "telegrams", "--workspace",
                        str(tmp_path / "builder"), "--scan-budget", "200")
    assert code == 0 and answer["ok"] is True
    assert answer["command"] == "saipen-telegrams"
    # The mailbox names its own seat, so a consumer can refuse to count a mailbox
    # that is not the acting seat's.
    assert answer["workspace"]["seat"] == "builder"
    assert isinstance(answer["match_count"], int) and answer["match_count"] == 2
    assert answer["exhausted"] is False and answer["cursor"] is None
    assert sorted(item["topic"] for item in answer["items"]) == ["T-7", "T-8"]
    assert "private finding" not in json.dumps(answer)
    assert answer["network_attempts"] == 0

    code, refused = _cli(capsys, "saipen", "telegrams", "--workspace",
                         str(tmp_path / "missing"))
    # A refusal exits 1 and names its code in `status`; there is no `code` field.
    assert code == 1 and refused["ok"] is False
    assert refused["status"] == workspace.WORKSPACE_MISSING and "code" not in refused
