"""Guidance identifies local receiver history without inventing peer feedback."""

import copy

import pytest
from test_correspondence import CLOCK, LINEAGE, decide, send
from test_correspondence import setup as _setup
from test_host_focus import full, host

from saimail import correspondence as co
from saimail import host_contract, workspace
from saimail_host import project_focus

setup = _setup
KNOWN = {"state": "KNOWN", "assessor": "WORKSPACE_RECEIVER", "subject": "RECEIVED_LETTERS"}
UNKNOWN = {"state": "UNKNOWN"}


def measured(box):
    return co.metrics(workspace.load_workspace_headers(box.root), lineage=LINEAGE,
                      clock=CLOCK)["metrics"]


def projected(pair, monkeypatch, value, *, compact):
    client = host(pair)
    client.negotiated = True
    client.features = host_contract.contract()["features"]
    calls = []

    def request(operation, arguments):
        calls.append(operation)
        return {"state": "OK", "data": {"focus": value} if compact else value}

    monkeypatch.setattr(client, "request", request)
    result = client.focus(["--work", "T-9"], prefer_cli=compact)
    assert calls == ["focus" if compact else "cycle"], "no retry/fallback after a received frame"
    return result


def frame(pair, compact):
    value = full(pair)
    return project_focus(value, "reviewer") if compact else value


def origin_container(value, compact):
    return value if compact else value["metrics"]


def test_two_seats_keep_local_decisions_separate_from_the_returned_assessment(setup):
    sender, receiver, project, _ = setup
    envelope = send(setup)["intent"]["envelope_id"]
    before = [measured(sender), measured(receiver)]
    decide(setup, envelope, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    first = co.report(receiver, envelope, lineage=LINEAGE, project_root=project, clock=CLOCK)
    after_report = [measured(sender), measured(receiver)]
    opened = co.review(sender, first["intent"]["envelope_id"], lineage=LINEAGE,
                       project_root=project, clock=CLOCK)
    after_review = measured(sender)
    assert opened["case"]["decision"] == "PENDING"
    assert "WAITING_DEPENDENCY" in opened["letter"]["observation"]
    assert after_review["decisions"]["DEFERRED"] == 0 and after_review["feedback_hints"] == []
    # The sender chooses its own disposition of the reply; it is a new local
    # receiver decision, not an adoption of the original receiver's assessment.
    co.decide(sender, first["intent"]["envelope_id"], lineage=LINEAGE, project_root=project,
              decision="ACCEPTED", reason="ACTION_PLANNED", clock=CLOCK)
    own_reply_decision = measured(sender)
    decide(setup, envelope, decision="DECLINED", reason="NOT_ACTIONABLE")
    second = co.report(receiver, envelope, lineage=LINEAGE, project_root=project, clock=CLOCK)
    retried = co.report(workspace.load_workspace(receiver.root), envelope,
                        lineage=LINEAGE, project_root=project, clock=CLOCK)
    assert second["intent"]["envelope_id"] == retried["intent"]["envelope_id"]
    assert second["intent"]["envelope_id"] != first["intent"]["envelope_id"]
    corrected = measured(receiver)
    sender_still_own = measured(sender)
    assert [m["reviewed"] for m in before] == [0, 0]
    assert [m["reviewed"] for m in after_report] == [0, 1]
    assert after_report[1]["decisions"]["DEFERRED"] == 1
    assert after_review["decisions"]["PENDING"] == 1
    assert own_reply_decision["decisions"]["ACCEPTED"] == 1
    assert corrected["decisions"]["DEFERRED"] == 0 and corrected["decisions"]["DECLINED"] == 1
    assert sender_still_own["decisions"]["ACCEPTED"] == 1
    assert sender_still_own["decisions"]["DECLINED"] == 0
    for metric in [*before, *after_report, after_review, own_reply_decision, corrected, sender_still_own]:
        assert metric["feedback_origin"] == KNOWN
        assert metric["basis"] == "EXPLICIT_RECEIVER_DECISIONS"


def test_origin_read_is_keyless_and_does_not_create_state_or_open_unread_mail(setup, monkeypatch):
    envelope = send(setup)["intent"]["envelope_id"]
    sender, receiver, project, _ = setup
    before = {p.name: p.read_bytes() for p in (project / ".saipen").iterdir()}
    monkeypatch.setattr(workspace, "open_message", lambda *a, **k: pytest.fail("unexpected open"))
    monkeypatch.setattr(workspace, "reopen_message", lambda *a, **k: pytest.fail("unexpected reopen"))
    for box in (sender, receiver):
        assert measured(box)["feedback_origin"] == KNOWN
        assert not (box.root / co.DB_NAME).exists()
    value = project_focus(full(setup), "reviewer")
    assert value["feedback_origin"] == KNOWN and value["reading"][0]["envelope_id"] == envelope
    assert workspace.query_inbox(receiver)["items"][0]["state"] == "UNREAD"
    assert {p.name: p.read_bytes() for p in (project / ".saipen").iterdir()} == before


@pytest.mark.parametrize("compact", [False, True])
def test_actual_cli_and_client_preserve_origin_and_existing_bases(setup, compact):
    envelope = send(setup)["intent"]["envelope_id"]
    decide(setup, envelope, decision="DECLINED", reason="WRONG_RECIPIENT")
    value = host(setup).focus(["--work", "T-9"], prefer_cli=compact)
    assert value["state"] == "OK" and value["feedback_origin"] == KNOWN
    assert value["feedback_basis"] == "LATEST_RECEIVER_ASSESSMENT"
    assert value["feedback_scope"] == "LIFETIME_HISTORY"
    assert value["feedback"][0]["reason"] == "WRONG_RECIPIENT"
    assert value["feedback_signals"]["active"][0]["reason"] == "WRONG_RECIPIENT"
    assert not value["automatic_execution"] and not value["model_improvement_proven"]


@pytest.mark.parametrize("compact", [False, True])
def test_older_cycle_or_compact_peer_has_unknown_origin_despite_other_known_metadata(setup, monkeypatch, compact):
    envelope = send(setup)["intent"]["envelope_id"]
    decide(setup, envelope, decision="DECLINED", reason="ALREADY_KNOWN")
    value = frame(setup, compact)
    origin_container(value, compact).pop("feedback_origin", None)
    result = projected(setup, monkeypatch, value, compact=compact)
    assert result["state"] == "OK" and result["feedback_origin"] == UNKNOWN
    assert result["feedback"][0]["count"] == 1 and result["feedback_signals"]["state"] == "KNOWN"


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("bad", [
    None, "WORKSPACE_RECEIVER", [], {},
    {"state": "KNOWN"},
    {"state": "KNOWN", "assessor": "PEER_RECEIVER", "subject": "RECEIVED_LETTERS"},
    {"state": "KNOWN", "assessor": "WORKSPACE_RECEIVER", "subject": "OUTGOING_PROPOSALS"},
    {"state": "UNKNOWN", "assessor": "WORKSPACE_RECEIVER"},
    {"state": "UNKNOWN", "subject": "RECEIVED_LETTERS"},
    {"state": "FUTURE_ORIGIN"},
])
def test_malformed_present_origin_is_named_degradation_without_retry(setup, monkeypatch, compact, bad):
    value = frame(setup, compact)
    origin_container(value, compact)["feedback_origin"] = bad
    result = projected(setup, monkeypatch, value, compact=compact)
    assert result["state"] == "DEGRADED"
    assert result["reason"] == ("INVALID_FOCUS" if compact else "INVALID_CYCLE")
    assert "feedback_origin" not in result


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("origin", [KNOWN, UNKNOWN])
def test_origin_is_rebuilt_locally_and_peer_text_is_ignored(setup, monkeypatch, compact, origin):
    value = frame(setup, compact)
    claimed = copy.deepcopy(origin)
    claimed.update(body="peer-body", command=["peer-command"], suggestion="invented-policy")
    origin_container(value, compact)["feedback_origin"] = claimed
    result = projected(setup, monkeypatch, value, compact=compact)
    assert result["state"] == "OK" and result["feedback_origin"] == origin
    assert result["feedback_origin"] is not claimed
    assert result["next_action"]["action"] == "CONTINUE_WORK"


def test_provenance_is_an_optional_contract_feature_with_unchanged_commands():
    contract = host_contract.contract()
    assert contract["features"]["feedback_origin"] == 1
    assert contract["version"] == 1 and contract["schema"] == "SAIMAIL_HOST_CONTRACT_1"
    assert contract["commands"]["focus"] == ["saipen", "letter", "focus"]
