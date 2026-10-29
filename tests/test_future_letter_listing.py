"""Request-local listing state never retries unreadable identity/peer registries."""
import json

import pytest

from sailang import SailangError
from saimail import envelope, future_letter as fl, workspace

NOW = "2026-10-29T01:00:00Z"


def test_unavailable_office_is_built_once_and_refuses_visibly(tmp_path, monkeypatch):
    workspace.init_workspace(tmp_path / "self", seat="self")
    ws = workspace.load_workspace(tmp_path / "self")
    fl.create(ws, title="one", body="one", clock=lambda: NOW)
    builds = []

    def unavailable(*args, **kwargs):
        builds.append(1)
        raise SailangError(workspace.RECIPIENT_REGISTRY_UNAVAILABLE, "unreadable peers")

    monkeypatch.setattr(workspace, "_self_post_office", unavailable)
    with pytest.raises(SailangError) as error:
        fl.list_letters(ws, clock=lambda: NOW)
    assert error.value.code == workspace.RECIPIENT_REGISTRY_UNAVAILABLE
    assert builds == [1]


def test_next_metadata_request_observes_peer_and_read_changes(tmp_path, monkeypatch):
    workspace.init_workspace(tmp_path / "self", seat="self")
    workspace.init_workspace(tmp_path / "peer", seat="peer")
    ws = workspace.load_workspace(tmp_path / "self")
    peer = workspace.load_workspace(tmp_path / "peer")
    letter = fl.create(ws, title="freshness", body="PRIVATE BODY", clock=lambda: NOW)["letter"]
    original_office, original_open = workspace._self_post_office, envelope.open
    offices = []

    def counted(*args, **kwargs):
        office = original_office(*args, **kwargs)
        offices.append(office)
        return office

    def no_plaintext(*args, **kwargs):
        pytest.fail("metadata list attempted decryption")

    monkeypatch.setattr(workspace, "_self_post_office", counted)
    monkeypatch.setattr(envelope, "open", no_plaintext)
    first = fl.list_letters(ws, clock=lambda: NOW)
    assert len(offices) == 1 and not offices[0].sender_registry.accepted("peer")
    assert first["items"][0]["state"] == fl.READ_UNREAD
    monkeypatch.setattr(envelope, "open", original_open)
    monkeypatch.setattr(workspace, "_self_post_office", original_office)
    fl.open_letter(ws, letter["letter_id"], clock=lambda: NOW)
    workspace.add_recipient(ws, "peer", workspace.identity_card(peer), peer.root)
    monkeypatch.setattr(workspace, "_self_post_office", counted)
    monkeypatch.setattr(envelope, "open", no_plaintext)
    second = fl.list_letters(ws, clock=lambda: NOW)
    assert len(offices) == 2 and offices[0] is not offices[1]
    assert offices[1].sender_registry.accepted("peer")
    assert second["items"][0]["state"] == fl.READ_READ
    assert "PRIVATE BODY" not in json.dumps([first, second])
