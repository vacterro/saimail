"""Namespaced letters stay visible on the established, keyless work brief."""

import json

import pytest

import saimail_local
from saimail import letters, saipen_bridge, workspace


@pytest.fixture
def routed_desk(tmp_path, monkeypatch):
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)
    memory = tmp_path / "project" / ".saipen"
    memory.mkdir(parents=True)
    lineage = "lineage-" + "ab" * 16
    state = memory / "STATE.md"
    state.write_text("---\nphase: BUILD\ntask: T-7\nagent: builder\nlast_event: 1\n---\n", encoding="utf-8")
    identity = memory / "IDENTITY.md"
    identity.write_text(f"---\nproject_lineage: {lineage}\n---\n", encoding="utf-8")
    workspace.init_workspace(tmp_path / "sender", seat="reviewer")
    workspace.init_workspace(tmp_path / "receiver", seat="builder")
    sender = workspace.load_workspace(tmp_path / "sender")
    receiver = workspace.load_workspace(tmp_path / "receiver")
    workspace.add_recipient(sender, "builder", workspace.identity_card(receiver), receiver.root)
    workspace.add_recipient(receiver, "reviewer", workspace.identity_card(sender), sender.root)
    foreign = "lineage-" + "cd" * 16
    topics = ["T-7", letters.topic(lineage, "T-7"), letters.topic(foreign, "T-7"),
              letters.topic(lineage, "T-8")]
    sent = [workspace.send_message(sender, "builder", topic=t, claim="sealed data") for t in topics]
    assert all(result["status"] == "ACCEPTED" for result in sent)
    ids = [result["message"]["envelope_id"] for result in sent]
    return memory, state, identity, receiver, topics, ids


def test_work_brief_associates_only_this_project_letter_on_every_page(routed_desk, monkeypatch):
    memory, state, identity, receiver, topics, ids = routed_desk
    before = {p.name: p.read_bytes() for p in memory.iterdir()}
    monkeypatch.setattr(workspace, "open_message", lambda *a, **k: pytest.fail("unexpected decrypt"))
    monkeypatch.setattr(workspace, "reopen_message", lambda *a, **k: pytest.fail("unexpected decrypt"))
    headers = workspace.load_workspace_headers(receiver.root)
    page_args, found, relations = {}, [], []
    for _ in range(4):
        page = saipen_bridge.work_brief(headers, state, identity, scan_budget=1, **page_args)
        found.extend(row["envelope_id"] for row in page["items"])
        relations.extend(row["work_relation"] for row in page["items"])
        assert page["brief"]["current_letter_topic"] == topics[1]
        page_args = page["brief"]["continuation"]
        if page_args is None:
            break
    assert found == ids
    assert relations == ["current_topic", "current_topic", "other_topics", "other_topics"]
    assert {p.name: p.read_bytes() for p in memory.iterdir()} == before
    assert "sealed data" not in json.dumps(page)


def test_real_cli_brief_counts_namespaced_and_legacy_work_without_opening(routed_desk, capsys):
    memory, _, _, receiver, _, _ = routed_desk
    code = saimail_local.main(["--json", "saipen", "brief", "--workspace", str(receiver.root),
                              "--project-root", str(memory.parent), "--seat", "builder"])
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    assert result["brief"]["counts"] == {"current_topic": 2, "other_topics": 2}
    assert result["brief"]["association"] == "TOPIC_ONLY"
    assert result["brief"]["complete_from_start"]
    assert all(row["state"] == "UNREAD" for row in result["items"])
