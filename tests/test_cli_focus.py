"""Compact CLI transport preserves metadata, compatibility and local authority."""

import copy
import json
import sys

import pytest
from test_correspondence import decide, send
from test_correspondence import setup as _setup
from test_host_focus import full, host

import saimail_host
import saimail_local
from saimail import correspondence, host_contract, saipen_bridge, workspace

setup = _setup


def compact(pair, arguments=("--work", "T-9")):
    return host(pair).focus(list(arguments), prefer_cli=True)


def packet(pair):
    return workspace.command_result("agent-focus", "OK",
                                    focus=saimail_host.project_focus(full(pair), "reviewer", []))


def fake_packet(pair, monkeypatch, value):
    client = host(pair)
    client.negotiated = True
    client.features = host_contract.contract()["features"]
    monkeypatch.setattr(client, "request", lambda *args: {"state": "OK", "data": value})
    return client.focus(["--work", "T-9"], prefer_cli=True)


def test_real_cli_focus_needs_no_client_object_and_does_not_change_work_or_mail(setup, capsys):
    eid = send(setup)["intent"]["envelope_id"]
    before = {p.name: p.read_bytes() for p in (setup[2] / ".saipen").iterdir()}
    code = saimail_local.main(["--json", "saipen", "letter", "focus", "--workspace", str(setup[1].root),
                              "--project-root", str(setup[2]), "--seat", "reviewer", "--work", "T-9"])
    result = json.loads(capsys.readouterr().out)
    assert code == 0 and result["schema"] == "LOCAL_WORKSPACE_COMMAND_1" and result["command"] == "agent-focus"
    focused = result["focus"]
    assert focused["reading"] == [{"envelope_id": eid, "reason": "CURRENT_MAIL"}]
    assert focused["next_action"] == {"action": "REVIEW", "operation": "review", "arguments": ["--envelope", eid]}
    assert focused["feedback_signals"]["state"] == "KNOWN" and focused["coverage"]["complete_from_start"]
    assert {p.name: p.read_bytes() for p in (setup[2] / ".saipen").iterdir()} == before
    assert workspace.query_inbox(setup[1])["items"][0]["state"] == "UNREAD"
    assert not (setup[1].root / correspondence.DB_NAME).exists()
    assert setup[3]["observation"] not in json.dumps(result)


def test_preferred_compact_transport_preserves_the_original_view_with_less_wire(setup, monkeypatch):
    send(setup)
    invoke, calls = saimail_host._invoke, []

    def measured(argv, timeout):
        result = invoke(argv, timeout)
        calls.append((list(argv), len(json.dumps(result.get("data", result), sort_keys=True, separators=(",", ":")))))
        return result

    monkeypatch.setattr(saimail_host, "_invoke", measured)
    local = host(setup).focus(["--work", "T-9"])
    old_calls, old_bytes = len(calls), sum(row[1] for row in calls)
    calls.clear()
    focused = compact(setup)
    assert focused["state"] == "OK" and len(calls) == old_calls == 2
    assert calls[-1][0][4:7] == ["saipen", "letter", "focus"]
    assert sum(row[1] for row in calls) < old_bytes * 0.75
    for key in ("reading", "host", "context", "coverage", "continuation", "next_action", "feedback", "decisions"):
        assert focused[key] == local[key]
    assert focused["feedback_signals"]["active"] == local["feedback_signals"]["active"]


@pytest.mark.parametrize("feature", [None, 2, True])
def test_missing_or_unknown_optional_focus_falls_back_before_invocation(setup, monkeypatch, feature):
    send(setup)
    client = host(setup)
    assert client.negotiate()["state"] == "OK"
    if feature is None:
        client.features.pop("cli_focus")
    else:
        client.features["cli_focus"] = feature
    invoke, calls = saimail_host._invoke, []

    def recorded(argv, timeout):
        calls.append(argv)
        return invoke(argv, timeout)

    monkeypatch.setattr(saimail_host, "_invoke", recorded)
    result = client.focus(["--work", "T-9"], prefer_cli=True)
    assert result["state"] == "OK" and len(calls) == 1 and "cycle" in calls[0] and "focus" not in calls[0]
    calls.clear()
    refused = client.request("focus", ["--work", "T-9"])
    assert refused["reason"] == "MISSING_FEATURE" and calls == []


def test_fresh_process_negotiates_an_older_peer_and_never_invokes_its_missing_command(setup, tmp_path):
    eid = send(setup)["intent"]["envelope_id"]
    contract = host_contract.contract()
    contract["features"].pop("cli_focus")
    contract["commands"].pop("focus")
    marker, script = tmp_path / "commands.json", tmp_path / "older_peer.py"
    script.write_text(
        "import json,runpy,sys\nfrom pathlib import Path\n"
        f"contract = {contract!r}\nmarker = Path({str(marker)!r})\n"
        "if '--contract' in sys.argv:\n    print(json.dumps(contract))\n"
        "else:\n    marker.write_text(json.dumps(sys.argv[1:]))\n"
        "    runpy.run_module('saimail_local', run_name='__main__')\n", encoding="utf-8")
    client = saimail_host.HostClient([sys.executable, str(script)], workspace=setup[1].root,
                                    project_root=setup[2], seat="reviewer")
    result = client.focus(["--work", "T-9"], prefer_cli=True)
    assert result["state"] == "OK" and result["reading"][0]["envelope_id"] == eid
    assert "cycle" in json.loads(marker.read_text()) and "focus" not in json.loads(marker.read_text())


def test_partial_compact_resume_keeps_query_budget_and_context_refusal(setup):
    for n in range(2):
        eid = send(setup, issue=f"closed-{n}")["intent"]["envelope_id"]
        decide(setup, eid, decision="DECLINED", reason="ALREADY_KNOWN")
    first = compact(setup, ["--work", "T-9", "--scope", "src/file.py", "--budget=1"])
    assert first["state"] == "OK" and first["reading"] == [] and not first["coverage"]["complete"]
    action = first["next_action"]
    assert action["operation"] == "focus"
    assert action["arguments"] == ["--work", "T-9", "--scope", "src/file.py", "--budget", "1",
                                   "--continuation", first["continuation"]]
    assert compact(setup, action["arguments"])["coverage"]["complete"]
    state = setup[2] / ".saipen/STATE.md"
    state.write_text(state.read_text().replace("last_event: 40", "last_event: 41"), encoding="utf-8")
    refused = compact(setup, action["arguments"])
    assert refused["state"] == "DEGRADED" and refused["code"] == "SAIPEN_CONTEXT_CHANGED"


def test_compact_without_selected_work_keeps_unknown_coverage(setup):
    state = setup[2] / ".saipen/STATE.md"
    state.write_text(state.read_text().replace("task: T-7", "task: none"), encoding="utf-8")
    focused = compact(setup, [])
    assert focused["state"] == "OK" and focused["work"] is None
    assert focused["next_action"] == {"action": "CHOOSE_WORK"} and not focused["coverage"]["complete"]


def test_unbound_compact_view_still_requires_integer_examination_counts(setup, monkeypatch):
    state = setup[2] / ".saipen/STATE.md"
    state.write_text(state.read_text().replace("task: T-7", "task: none"), encoding="utf-8")
    data = full(setup)
    data["cycle"].update(work=None, complete=False, complete_from_start=False)
    data["desk"] = None
    response = workspace.command_result("agent-focus", "OK",
                                        focus=saimail_host.project_focus(data, "reviewer", []))
    response["focus"]["coverage"]["rows_examined"] = False
    assert fake_packet(setup, monkeypatch, response)["reason"] == "INVALID_FOCUS"


def test_compact_cli_has_one_admission_and_refuses_mid_observation_change(setup, monkeypatch, capsys):
    original, calls = saipen_bridge.enter, []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result["saipen"]["last_event"])
        state = setup[2] / ".saipen/STATE.md"
        state.write_text(state.read_text().replace("last_event: 40", "last_event: 41"), encoding="utf-8")
        return result

    monkeypatch.setattr(saipen_bridge, "enter", changed)
    code = saimail_local.main(["--json", "saipen", "letter", "focus", "--workspace", str(setup[1].root),
                              "--project-root", str(setup[2]), "--seat", "reviewer", "--work", "T-9"])
    result = json.loads(capsys.readouterr().out)
    assert code == 1 and result["status"] == "SAIPEN_CONTEXT_CHANGED" and len(calls) == 1
    assert "focus" not in result


def test_consumer_drops_peer_operations_bodies_suggestions_and_coverage_overrides(setup, monkeypatch):
    eid = send(setup)["intent"]["envelope_id"]
    decide(setup, eid, decision="DECLINED", reason="NOT_ACTIONABLE")
    value = packet(setup)
    focus = value["focus"]
    focus["next_action"] = {"action": "EXECUTE", "operation": "peer-command", "arguments": ["peer-body"]}
    focus["feedback"][0].update(suggestion="peer-command", body="peer-body")
    focus["coverage"]["items"] = [{"envelope_id": "sha256:" + "f" * 64, "body": "peer-body"}]
    focus["body"] = "peer-body"
    result = fake_packet(setup, monkeypatch, value)
    assert result["state"] == "OK" and result["next_action"] == {"action": "CONTINUE_WORK"}
    assert result["reading"] == [] and "peer-command" not in json.dumps(result) and "peer-body" not in json.dumps(result)


@pytest.mark.parametrize("path,value", [
    (("schema",), "SAIMAIL_HOST_FOCUS_2"), (("automatic_execution",), True),
    (("model_improvement_proven",), True), (("feedback_scope",), "CURRENT_TRUTH"),
    (("coverage", "complete"), 1), (("coverage", "rows_examined"), True),
    (("context",), "unbound"), (("scope",), ["../outside"]), (("reading",), [{"envelope_id": "bad", "reason": "CURRENT_MAIL"}]),
    (("reviewed",), 1), (("feedback_signals", "window_days"), 30), (("host", "seat"), "another"),
])
def test_malformed_compact_response_never_becomes_an_operation(setup, monkeypatch, path, value):
    send(setup)
    response = copy.deepcopy(packet(setup))
    target = response["focus"]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    result = fake_packet(setup, monkeypatch, response)
    assert result["state"] == "DEGRADED" and result["reason"] == "INVALID_FOCUS" and "next_action" not in result


def test_negotiated_compact_refusal_does_not_retry_a_different_operation(setup, monkeypatch):
    client = host(setup)
    client.negotiated, client.features = True, host_contract.contract()["features"]
    calls = []
    refusal = {"state": "DEGRADED", "reason": "REFUSED", "code": "SAIPEN_CONTEXT_CHANGED"}

    def refused(action, arguments):
        calls.append(action)
        return refusal

    monkeypatch.setattr(client, "request", refused)
    assert client.focus(prefer_cli=True) == refusal and calls == ["focus"]
