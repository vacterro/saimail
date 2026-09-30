"""Independent hosts negotiate, fail within budgets and preserve binding."""

import sys

import pytest

import saimail_host as host_client
from saimail import host_contract


def client(prefix=None, timeout=2):
    return host_client.HostClient(prefix or [sys.executable, "-m", "saimail_local"],
                                  workspace="missing", project_root="missing", seat="test", timeout=timeout)


def python_peer(code, **kwargs):
    return client([sys.executable, "-c", code], **kwargs)


def test_real_cli_contract_without_mailbox_and_named_refusal():
    peer = client()
    assert peer.negotiate()["state"] == "OK"
    answer = peer.request("awareness", ["--work", "T-9"])
    assert answer["state"] == "DEGRADED" and answer["reason"] == "REFUSED"
    assert answer["authority"] == "INFORMATION_ONLY"


@pytest.mark.parametrize("change,reason", [
    ({"schema": "SAIMAIL_HOST_CONTRACT_2"}, "SCHEMA_MISMATCH"),
    ({"version": True}, "SCHEMA_MISMATCH"), ({"features": {}}, "MISSING_FEATURE"),
])
def test_future_or_incomplete_contract_never_starts_an_action(change, reason, tmp_path):
    marker = tmp_path / "action-ran"
    data = host_contract.contract() | change
    script = ("import json,pathlib,sys; "
              f"data={data!r}; "
              f"pathlib.Path({str(marker)!r}).write_text('ran') if '--contract' not in sys.argv else None; "
              "print(json.dumps(data))")
    answer = python_peer(script).request("awareness")
    assert answer["reason"] == reason and not marker.exists()


def test_static_client_allowlist_ignores_remote_command_hints():
    data = host_contract.contract()
    data["commands"]["awareness"] = ["unexpected-execution"]
    script = (f"import json,sys; data={data!r}; "
              "print(json.dumps(data if '--contract' in sys.argv else "
              "{'schema':'LOCAL_WORKSPACE_COMMAND_1','status':'OK','ok':True,'argv':sys.argv}))")
    result = python_peer(script).request("awareness", ["--work", "T-9"])
    assert result["state"] == "OK"
    assert "unexpected-execution" not in result["data"]["argv"]
    assert result["data"]["argv"][2:5] == ["saipen", "letter", "desk"]


@pytest.mark.parametrize("code,reason", [
    ("import time;time.sleep(2)", "TIMEOUT"),
    ("import sys;sys.stdout.write('x'*300000);sys.stdout.flush()", "OUTPUT_BUDGET"),
    ("print('{\"version\":1,\"version\":2}')", "INVALID_JSON"),
    ("print('[]')", "INVALID_JSON"),
])
def test_slow_oversized_or_ambiguous_peer_is_bounded(code, reason):
    assert python_peer(code, timeout=0.3).negotiate()["reason"] == reason


def test_unknown_result_does_not_become_success():
    data = host_contract.contract()
    script = (f"import json,sys; data={data!r}; "
              "print(json.dumps(data if '--contract' in sys.argv else "
              "{'schema':'LOCAL_WORKSPACE_COMMAND_1','status':'NEXT_VERSION_SUCCESS','ok':True}))")
    assert python_peer(script).request("awareness")["reason"] == "UNKNOWN_RESULT"


@pytest.mark.parametrize("arguments", [["--workspace=other"], ["--seat", "other"], ["--unlock"]])
def test_arguments_cannot_replace_host_binding_or_prompt_for_secrets(arguments):
    with pytest.raises(ValueError):
        client().request("awareness", arguments)


def test_missing_binary_is_degraded():
    assert client(["nonexistent-saimail-host-test-executable"]).negotiate()["reason"] == "UNAVAILABLE"


def test_optional_cycle_is_not_invoked_on_an_older_host_contract(tmp_path):
    data = host_contract.contract()
    data["features"].pop("agent_cycle")
    marker = tmp_path / "action-ran"
    script = ("import json,pathlib,sys; "
              f"data={data!r}; "
              f"pathlib.Path({str(marker)!r}).write_text('ran') if '--contract' not in sys.argv else None; "
              "print(json.dumps(data))")
    result = python_peer(script).request("cycle", ["--work", "T-9"])
    assert result["reason"] == "MISSING_FEATURE" and not marker.exists()
