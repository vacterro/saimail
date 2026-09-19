"""T-17 lab contract: what a live SAIFREN run may do, may keep, and may never become.

Every live path here runs through the real HttpTransport with a fake opener, so
the code that builds the Authorization header is the code under test.
"""

import ast
import hashlib
import io
import json
import pathlib
import socket
import urllib.error
import urllib.request

import pytest

from lab import saifren_run as lab
from lab import scenarios as sc
from saimail.provenance import (Attribution, MEASURED_EVIDENCE, Segment, SegmentMap,
                                intent_authority)
from sailang import SailangError
from sailang.frame import Profile

ROOT = pathlib.Path(__file__).resolve().parent.parent
KEY = "sk-SENTINEL-7f3a9c1e5b2d-DO-NOT-PERSIST"
THOUGHT = "PRIVATE-CHAIN-OF-THOUGHT-SENTINEL"


class FakeHeaders:
    def __init__(self, pairs):
        self._pairs = list(pairs)

    def items(self):
        return list(self._pairs)


class FakeResponse(io.BytesIO):
    def __init__(self, payload, status=200, headers=()):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        super().__init__(raw)
        self.status = status
        self.headers = FakeHeaders(headers)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def answer_for(prompt):
    """A stand-in participant: correct, schema-shaped answers chosen by prompt."""
    if "Write a message about this finding" in prompt:
        return sc.REFERENCE_OUTPUTS["handoff_a"]
    if "Another agent sent you the message below" in prompt:
        return sc.REFERENCE_OUTPUTS["handoff_b"]
    if "Write the legacy packet" in prompt:
        return sc.REFERENCE_OUTPUTS["legacy_a"]
    if "TASK: After last night's worker node restart" in prompt:
        return sc.REFERENCE_OUTPUTS["successor_legacy" if "LEGACY PACKET" in prompt
                                    else "successor_control"]
    if "M1:" in prompt:
        return "M1: OPEN\nM2: DEFER\nM3: OPEN\nM4: IGNORE"
    if "ANSWER: <YES|NO>" in prompt:
        return "ANSWER: NO"
    return "Q1: NO\nQ2: NO\nQ3: NO"


def completion(content, model="SAIFREN", **extra):
    return {"id": "gen-1", "model": model, "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content,
                                     "reasoning": THOUGHT, "reasoning_content": THOUGHT,
                                     "reasoning_details": [{"type": "reasoning.text",
                                                            "text": THOUGHT}]}}],
            "reasoning": THOUGHT,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                      "completion_tokens_details": {"reasoning_tokens": 99}},
            **extra}


class Opener:
    """Records every request; answers through ``respond(prompt, n)``."""

    def __init__(self, respond=None, headers=()):
        self.requests = []
        self.respond = respond or (lambda prompt, n: FakeResponse(
            completion(answer_for(prompt)), headers=headers))

    def __call__(self, request, timeout):
        self.requests.append(request)
        prompt = json.loads(request.data.decode("utf-8"))["messages"][0]["content"]
        result = self.respond(prompt, len(self.requests))
        if isinstance(result, BaseException):
            raise result
        return result


def live(tmp_path, opener, max_runs=lab.MAX_RUNS, key=KEY):
    transport = lab.HttpTransport(key, opener=opener, timeout=1)
    return lab.run(tmp_path, dry_run=False, api_key=key, transport=transport, max_runs=max_runs)


def written(tmp_path):
    return "".join(p.read_text(encoding="utf-8") for p in sorted(tmp_path.rglob("*")) if p.is_file())


def all_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from all_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from all_keys(item)


# ------------------------------------------------ MAX_RUNS


def test_max_runs_is_enforced_before_the_first_call(tmp_path):
    planned = sc.planned_calls(sc.build_plan(Profile.load("1")))
    assert planned <= lab.MAX_RUNS
    opener = Opener()
    with pytest.raises(SystemExit):
        live(tmp_path, opener, max_runs=planned - 1)
    assert opener.requests == [], "a plan over the cap makes no call at all"
    assert not any(tmp_path.iterdir())


def test_a_discovering_run_reserves_its_probes_inside_the_cap(tmp_path, monkeypatch):
    """A budget spent half way through is not a bound; it is a surprise."""
    from lab import saifren_population as pop

    planned = sc.planned_calls(sc.build_plan(Profile.load("1")))
    assert planned + pop.DISCOVERY_RESERVE <= lab.MAX_RUNS, \
        "the declared cap covers the plan plus the declared discovery reserve"

    opener = Opener()
    monkeypatch.setattr(urllib.request, "urlopen", opener)
    with pytest.raises(SystemExit) as exc:
        lab.run(tmp_path, dry_run=False, api_key=KEY, discover=True,
                max_runs=planned + pop.DISCOVERY_RESERVE - 1)
    assert "discovery reserve" in str(exc.value) and "--sample" in str(exc.value)
    assert opener.requests == [], "a plan over the cap makes no call at all"
    assert not any(tmp_path.iterdir())


def test_a_run_that_hands_in_a_transport_reserves_nothing(tmp_path):
    planned = sc.planned_calls(sc.build_plan(Profile.load("1")))
    result = live(tmp_path, Opener(), max_runs=planned)
    assert result["discovery_calls"] == 0
    assert result["live_calls"] <= planned


def test_max_runs_is_enforced_at_every_call():
    budget = lab.CallBudget(2)
    budget.spend()
    budget.spend()
    with pytest.raises(lab.BudgetExceeded):
        budget.spend()
    sent = []
    runner = lab.Runner(lambda prompt: sent.append(prompt) or {"output": "x"}, lab.CallBudget(3))
    records = [runner.call("U", "single", f"p{i}") for i in range(5)]
    assert len(sent) == 3
    assert [r["status"] for r in records] == ["OK", "OK", "OK", "ERROR", "ERROR"]
    assert records[-1]["error_class"] == "BudgetExceeded"


# ------------------------------------------------ the credential


def test_the_key_authenticates_the_call_and_is_never_persisted(tmp_path, capsys):
    opener = Opener()
    result = live(tmp_path, opener)
    assert opener.requests, "the live path really ran"
    assert all(r.get_header("Authorization") == f"Bearer {KEY}" for r in opener.requests)
    text = written(tmp_path)
    assert result["live_calls"] == len(opener.requests)
    assert KEY not in text
    assert "Bearer" not in text and "bearer " not in text.lower()
    assert "authorization" not in text.lower()
    assert KEY not in capsys.readouterr().out


def test_an_error_echoing_the_credential_is_scrubbed(tmp_path):
    def respond(prompt, n):
        if n == 1:
            body = io.BytesIO(f"bad request, Authorization: Bearer {KEY}".encode())
            return urllib.error.HTTPError("http://x", 500, "boom", {}, body)
        return FakeResponse(completion(answer_for(prompt)))
    live(tmp_path, Opener(respond))
    text = written(tmp_path)
    assert KEY not in text and "authorization" not in text.lower()
    assert "[REDACTED]" in text


def test_a_leak_fails_closed_and_writes_nothing(tmp_path):
    echo = Opener(lambda prompt, n: FakeResponse(completion(f"sure, your key is {KEY}")))
    with pytest.raises(lab.SecretLeak):
        live(tmp_path, echo)
    assert not any(tmp_path.iterdir())


def test_missing_credential_fails_with_named_operational_error(tmp_path, monkeypatch):
    monkeypatch.delenv(lab.KEY_ENV, raising=False)
    with pytest.raises(SystemExit) as exc:
        lab.main(["--out", str(tmp_path)])
    assert "SAIROUTE_CREDENTIAL_NOT_PROVISIONED" in str(exc.value)
    with pytest.raises(SystemExit):
        lab.main(["--out", str(tmp_path), "--key", KEY])  # no such option
    with pytest.raises(SystemExit):
        lab.main(["--out", str(tmp_path), "--secret", KEY])  # nor this one
    assert KEY not in repr(lab.HttpTransport(KEY))


def test_the_ordinary_command_never_reads_the_environment(tmp_path, monkeypatch):
    """D-019: an inherited variable may not stand in for a provisioned credential."""
    monkeypatch.setenv(lab.KEY_ENV, KEY)
    monkeypatch.setattr(urllib.request, "urlopen", Opener())
    with pytest.raises(SystemExit) as exc:
        lab.main(["--out", str(tmp_path)])
    assert "SAIROUTE_CREDENTIAL_NOT_PROVISIONED" in str(exc.value)
    assert not any(tmp_path.iterdir()), "no artifact is written from an environment secret"


def test_the_legacy_environment_source_is_explicit_and_recorded(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv(lab.KEY_ENV, KEY)
    monkeypatch.setattr(urllib.request, "urlopen", Opener())
    assert lab.main(["--out", str(tmp_path), "--credential-source", "env"]) == 0
    out = capsys.readouterr().out
    assert KEY not in out and "authorization" not in out.lower()
    assert KEY not in written(tmp_path)
    artifact = json.loads(next(tmp_path.glob("saifren_live_*.json")).read_text(encoding="utf-8"))
    assert artifact["credential"]["source"] == "env"
    assert artifact["credential"]["handle"] == "credential://9router/sairoute"
    assert KEY not in json.dumps(artifact["credential"])


def test_the_legacy_source_refuses_when_the_variable_is_unset(tmp_path, monkeypatch):
    monkeypatch.delenv(lab.KEY_ENV, raising=False)
    with pytest.raises(SystemExit) as exc:
        lab.main(["--out", str(tmp_path), "--credential-source", "env"])
    assert "SAIROUTE_CREDENTIAL_NOT_PROVISIONED" in str(exc.value)
    assert lab.KEY_ENV in str(exc.value)


def test_the_store_is_the_default_source_and_is_recorded(tmp_path, monkeypatch, capsys):
    from saimail.credentials import DEFAULT_HANDLE, InMemoryCredentialStore, set_credential_store

    store = InMemoryCredentialStore({DEFAULT_HANDLE: KEY})
    set_credential_store(store)
    monkeypatch.setenv(lab.KEY_ENV, "sk-WRONG-ENVIRONMENT-VALUE")
    opener = Opener()
    monkeypatch.setattr(urllib.request, "urlopen", opener)
    try:
        assert lab.main(["--out", str(tmp_path)]) == 0
    finally:
        set_credential_store(None)
    assert all(r.get_header("Authorization") == f"Bearer {KEY}" for r in opener.requests), \
        "the store value authenticates the call, not the environment value"
    artifact = json.loads(next(tmp_path.glob("saifren_live_*.json")).read_text(encoding="utf-8"))
    assert artifact["credential"]["source"] == "store"
    assert KEY not in written(tmp_path)
    assert KEY not in capsys.readouterr().out


# ------------------------------------------------ dry run


def test_dry_run_performs_zero_network_calls(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network touched during a dry run")

    import http.client

    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(http.client.HTTPConnection, "connect", forbidden)
    monkeypatch.delenv(lab.KEY_ENV, raising=False)
    assert lab.main(["--out", str(tmp_path), "--dry-run"]) == 0
    artifact = json.loads((tmp_path / "saifren_dry_run.json").read_text(encoding="utf-8"))
    assert artifact["live_calls"] == 0
    assert artifact["calls"] and all(c["status"] == "NOT_RUN" for c in artifact["calls"])
    assert all(u["verdict"] == "NOT_RUN" for u in artifact["units"])
    assert not (tmp_path / "SAIFREN_REPORT.md").exists()


# ------------------------------------------------ observable output only


ALLOWED_CALL_KEYS = {
    # requested_model is what the harness sent, not a payload field: membership
    # evidence needs it on every call (D-024)
    "requested_model",
    "call_id", "unit_id", "role", "timestamp", "prompt", "prompt_sha256", "status", "output",
    "output_truncated", "inline_trace_removed", "finish_reason", "reported_model",
    "route_resolution",
    "model_namespace", "provider", "provider_basis", "route_headers", "gen_id", "usage",
    "http_status", "latency_s", "error_class", "error", "skipped_because",
}


def test_live_artifacts_keep_observable_outputs_only(tmp_path):
    headers = [("x-9router-provider", "prov-x"), ("x-api-key", "leak-1"),
               ("set-cookie", "session=leak-2"), ("x-account-email", "leak-3@example.com"),
               ("x-model-route", "route-7"), ("content-type", "application/json")]
    result = live(tmp_path, Opener(headers=headers))
    for call in result["calls"]:
        assert set(call) <= ALLOWED_CALL_KEYS, set(call) - ALLOWED_CALL_KEYS
        assert set(call["usage"]) <= {"prompt_tokens", "completion_tokens", "total_tokens"}
        assert set(call["route_headers"]) == {"x-9router-provider", "x-model-route"}
    text = written(tmp_path)
    for leaked in ("leak-1", "leak-2", "leak-3"):
        assert leaked not in text


def test_reasoning_is_never_stored(tmp_path):
    result = live(tmp_path, Opener())
    text = written(tmp_path)
    assert THOUGHT not in text
    for key in all_keys(result):
        assert "reasoning" not in str(key).lower() and "thinking" not in str(key).lower()


def test_inline_reasoning_is_removed_before_storage_and_grading(tmp_path):
    def respond(prompt, n):
        return FakeResponse(completion(f"<think>{THOUGHT}</think>\n{answer_for(prompt)}"))
    result = live(tmp_path / "think", Opener(respond))
    assert THOUGHT not in written(tmp_path / "think")
    assert all(c["inline_trace_removed"] for c in result["calls"] if c["status"] == "OK")
    plain = live(tmp_path / "plain", Opener())
    assert result["summary"]["verdicts"] == plain["summary"]["verdicts"], (
        "grading saw the visible answer, not the reasoning")
    unclosed = lab.observable(completion(f"<think>{THOUGHT} and then the budget ran out"),
                              {}, "SAIFREN")
    assert unclosed["output"] == "" and unclosed["inline_trace_removed"]


def test_provider_identity_is_never_invented():
    alias = lab.observable(completion("x"), {}, "SAIFREN")
    assert alias["route_resolution"] == "ALIAS_ONLY"
    assert alias["provider"] is None and alias["provider_basis"] == "NOT_EXPOSED"
    named = lab.observable(completion("x", model="amd/DeepSeek-V4-Flash"), {}, "SAIFREN")
    assert named["reported_model"] == "amd/DeepSeek-V4-Flash"
    assert named["model_namespace"] == "amd" and named["provider"] is None
    stated = lab.observable(completion("x", provider="prov-y"), {}, "SAIFREN")
    assert (stated["provider"], stated["provider_basis"]) == ("prov-y", "RESPONSE_FIELD")
    header = lab.observable(completion("x"), {"X-Provider": "prov-z"}, "SAIFREN")
    assert header["provider"] == "prov-z" and header["provider_basis"].startswith("RESPONSE_HEADER")


# ------------------------------------------------ failures stay bounded


def test_failures_and_timeouts_become_bounded_error_records(tmp_path):
    big = "x" * 50_000
    failures = {
        1: TimeoutError("timed out " + big),
        2: urllib.error.HTTPError("http://x", 500, "boom", {}, io.BytesIO(big.encode())),
        3: FakeResponse(b"{not json" + big.encode()),
        5: urllib.error.URLError("refused " + big),
        6: FakeResponse(["a", "list"]),
        7: FakeResponse({"error": {"message": "upstream said no " + big}}),
        9: FakeResponse(completion("", finish_reason="length")),
        10: socket.timeout("read timed out"),
        12: FakeResponse(b"{" + b" " * (lab.MAX_RESPONSE_BYTES + 10) + b"}"),
    }

    def respond(prompt, n):
        return failures.get(n) or FakeResponse(completion(answer_for(prompt)))

    result = live(tmp_path, Opener(respond))
    errors = [c for c in result["calls"] if c["status"] == "ERROR"]
    assert len(errors) == len(failures)
    assert result["stopped"] is None, "isolated failures do not stop the suite"
    # planned is an upper bound: a failed first agent means its second agent is never called
    assert result["live_calls"] == len(result["calls"]) <= result["planned_calls"]
    assert result["units"][-1]["unit_id"] == "S5.trial3", "the suite ran to its end"
    for error in errors:
        assert error["error_class"] and len(error["error"]) <= lab.MAX_ERROR_CHARS
    classes = {e["error_class"] for e in errors}
    assert {"TimeoutError", "HTTPError", "MalformedResponse", "URLError", "GatewayError",
            "EmptyOutput", "ResponseTooLarge"} <= classes
    assert len(json.dumps(result["calls"])) < 200_000


def test_an_auth_refusal_stops_the_suite(tmp_path):
    def refuse(prompt, n):
        return urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, io.BytesIO(b"{}"))
    opener = Opener(refuse)
    result = live(tmp_path, opener)
    assert len(opener.requests) == 1
    assert result["stopped"].startswith("AUTH_REFUSED")
    assert sum(1 for c in result["calls"] if c["status"] == "ERROR") == 1


def test_an_unreachable_gateway_stops_after_a_bounded_number_of_tries(tmp_path):
    opener = Opener(lambda prompt, n: urllib.error.URLError("connection refused"))
    result = live(tmp_path, opener)
    assert len(opener.requests) == lab.MAX_CONSECUTIVE_TRANSPORT_ERRORS
    assert result["stopped"] == "GATEWAY_UNREACHABLE"


def test_a_transport_failure_is_never_graded_as_a_semantic_verdict(tmp_path):
    """B4: a route that did not answer said nothing. It did not disagree."""
    result = live(tmp_path, Opener(
        lambda prompt, n: urllib.error.HTTPError(
            "http://x", 503, "Service temporarily overloaded", {}, io.BytesIO(b""))))
    verdicts = {u["verdict"] for u in result["units"]}
    assert verdicts <= {"ERROR", "NOT_RUN"}
    assert "FAIL" not in verdicts and "PASS" not in verdicts
    assert all("grade" not in u for u in result["units"]), "nothing unanswered is graded"


def test_one_refusing_route_does_not_fail_the_units_that_answered(tmp_path):
    def respond(prompt, n):
        if n == 2:
            return urllib.error.HTTPError("http://x", 503, "overloaded", {}, io.BytesIO(b""))
        return FakeResponse(completion(answer_for(prompt)))

    result = live(tmp_path, Opener(respond))
    errored = [u for u in result["units"] if u["verdict"] == "ERROR"]
    assert errored, "the refusal reached a unit"
    assert result["summary"]["verdicts"]["PASS"] >= 1, "answered units keep their verdict"
    for unit in errored:
        assert "grade" not in unit


def test_an_empty_answer_is_an_operational_failure_not_a_wrong_answer(tmp_path):
    def respond(prompt, n):
        if n == 1:
            return FakeResponse(completion("", finish_reason="length"))
        return FakeResponse(completion(answer_for(prompt)))

    result = live(tmp_path, Opener(respond))
    first = result["calls"][0]
    assert first["status"] == "ERROR" and first["error_class"] == "EmptyOutput"
    unit = next(u for u in result["units"] if u["call_id"] == first["call_id"])
    assert unit["verdict"] == "ERROR" and "grade" not in unit


# ------------------------------------------------ the population, not two constants


def _population(role_b="beta/big"):
    from lab import saifren_population as pop

    participants = [pop.Participant(role="A", requested="SAIFREN",
                                    reported_model="vendor/one",
                                    member_status=pop.OBSERVED_COMBO_MEMBER,
                                    source="COMBO_ALIAS")]
    if role_b:
        participants.append(pop.Participant(role="B", requested=role_b,
                                            reported_model="beta/one",
                                            member_status=pop.NOT_PROVEN_COMBO_MEMBER,
                                            source="CATALOG_ELIGIBLE",
                                            catalog_namespace="beta"))
    return pop.Population(combo="SAIFREN", observed_at="2026-09-17T00:00:00Z",
                          membership_source=pop.COMBO_ALIAS_SAMPLE,
                          roster_status=pop.ROSTER_NOT_EXPOSED,
                          observed_members=("vendor/one",),
                          catalog_size=6, catalog_digest="sha256:cafe",
                          membership_digest="sha256:beef",
                          participants=tuple(participants))


def test_the_harness_sends_the_models_the_population_resolved(tmp_path):
    opener = Opener()
    transport = lab.HttpTransport(KEY, opener=opener, timeout=1)
    lab.run(tmp_path, dry_run=False, api_key=KEY, transport=transport,
            population=_population())
    sent = {json.loads(r.data.decode("utf-8"))["model"] for r in opener.requests}
    assert sent == {"SAIFREN", "beta/big"}


def test_a_run_with_no_resolved_participants_sends_only_the_alias(tmp_path):
    from lab import saifren_population as pop

    opener = Opener()
    transport = lab.HttpTransport(KEY, opener=opener, timeout=1)
    result = lab.run(tmp_path, dry_run=False, api_key=KEY, transport=transport,
                     population=pop.offline_population("SAIFREN", "t", "not requested"))
    sent = {json.loads(r.data.decode("utf-8"))["model"] for r in opener.requests}
    assert sent == {"SAIFREN"}, "no hidden default model id survives"
    assert result["population"]["heterogeneous_participants"] is False


def test_every_live_artifact_carries_its_membership_provenance(tmp_path):
    result = lab.run(tmp_path, dry_run=False, api_key=KEY,
                     transport=lab.HttpTransport(KEY, opener=Opener(), timeout=1),
                     population=_population())
    record = result["population"]
    assert record["combo"] == "SAIFREN"
    assert record["membership_observed_at"] == "2026-09-17T00:00:00Z"
    assert record["membership_digest"] == "sha256:beef"
    assert record["catalog_digest"] == "sha256:cafe"
    assert record["selection_rule"] and record["replacement_policy"]
    assert [p["requested"] for p in record["participants"]] == ["SAIFREN", "beta/big"]
    assert [p["reported_model"] for p in record["participants"]] == ["vendor/one", "beta/one"]
    assert record["participants"][0]["member_status"] == "OBSERVED_COMBO_MEMBER"
    assert record["participants"][1]["member_status"] == "NOT_PROVEN_COMBO_MEMBER"
    assert record["heterogeneous_participants"] is True
    written_text = written(tmp_path)
    assert "sha256:beef" in written_text, "the provenance reaches the artifact on disk"


def test_discovery_probes_are_spent_from_the_same_call_budget(tmp_path):
    opener = Opener()

    class Discovering(lab.HttpTransport):
        def get_json(self, path):
            assert path == "/v1/models"
            return {"data": [{"id": "SAIFREN", "owned_by": "combo"},
                             {"id": "beta/big", "owned_by": "beta",
                              "context_length": 10, "capabilities": {}}]}

    transport = Discovering(KEY, opener=opener, timeout=1)
    result = lab.run(tmp_path, dry_run=False, api_key=KEY, transport=transport,
                     discover=True, sample=True)
    assert result["discovery_calls"] > 0
    assert result["live_calls"] == result["discovery_calls"] + result["experiment_calls"]
    assert result["live_calls"] <= result["max_runs"]
    assert result["population"]["membership_probes_used"] > 0


def test_a_discovery_failure_is_recorded_and_never_fatal(tmp_path):
    """W2-002: an ordinary discovery failure (not an auth refusal) stays non-fatal."""

    class Broken(lab.HttpTransport):
        def get_json(self, path):
            raise urllib.error.HTTPError("http://x", 500, "Internal Server Error", {},
                                         io.BytesIO(b"{}"))

    transport = Broken(KEY, opener=Opener(), timeout=1)
    result = lab.run(tmp_path, dry_run=False, api_key=KEY, transport=transport,
                     discover=True, sample=True)
    record = result["population"]
    assert record["membership_source"] == "SAIFREN_MEMBERSHIP_NOT_OBSERVABLE"
    assert record["participants"] == []
    assert any("could not be read" in note for note in record["notes"])
    assert result["experiment_calls"] > 0, "the run still happened, claiming nothing"


def test_the_declared_sample_is_fixed_before_the_run(tmp_path):
    units = sc.build_plan(Profile.load("1"))
    chosen = lab.select_units(units, sample=True)
    assert [u.unit_id for u in chosen] == list(lab.SAMPLE_UNITS)
    assert sc.planned_calls(chosen) < sc.planned_calls(units)
    result = lab.run(tmp_path, dry_run=True, sample=True)
    assert {u["unit_id"] for u in result["units"]} == set(lab.SAMPLE_UNITS)


def test_a_dry_run_claims_no_population(tmp_path):
    result = lab.run(tmp_path, dry_run=True)
    assert result["population"]["membership_source"] == "SAIFREN_MEMBERSHIP_NOT_OBSERVABLE"
    assert result["population"]["participants"] == []
    assert result["discovery_calls"] == 0


def test_a_failed_first_agent_never_hands_off(tmp_path):
    def respond(prompt, n):
        if "Write a message about this finding" in prompt:
            return urllib.error.HTTPError("http://x", 502, "bad gateway", {}, io.BytesIO(b""))
        return FakeResponse(completion(answer_for(prompt)))
    result = live(tmp_path, Opener(respond))
    for unit in (u for u in result["units"] if u["unit_id"].startswith("S2.")):
        assert unit["verdict"] == "ERROR" and "b_call_id" not in unit


# ------------------------------------------------ experiment data is not authority


def _snapshot():
    digests = {}
    for base in ("provenance", "spec", "sailang", "saimail", ".saipen/intake"):
        for path in sorted((ROOT / base).rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                digests[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


def test_experiment_evidence_cannot_mutate_protocol_authority(tmp_path):
    before = _snapshot()
    result = live(tmp_path / "out", Opener())
    assert _snapshot() == before, "a live run changed a protocol or authority file"
    assert {p.parent for p in (tmp_path / "out").rglob("*") if p.is_file()} == {tmp_path / "out"}
    assert result["authority"] == "EXPERIMENT_DATA"
    assert result["is_not"] == ["CONSENSUS", "TRUTH", "PROTOCOL_CHANGE", "USER_INTENT"]
    report = (tmp_path / "out" / "SAIFREN_REPORT.md").read_text(encoding="utf-8")
    assert "EXPERIMENT_DATA" in report
    # even declared as measurement, a lab artifact asks for no work
    maps = {"LAB": SegmentMap("LAB", "x" * 64, 10,
                              (Segment("LAB", 0, 10, MEASURED_EVIDENCE),))}
    with pytest.raises(SailangError) as exc:
        intent_authority(Attribution("P-1", "LAB", 0), maps)
    assert exc.value.code == "EVIDENCE_IS_NOT_INTENT"


def test_live_output_is_never_merged_into_a_verdict_about_the_world(tmp_path):
    answers = iter(["Q1: YES\nQ2: NO\nQ3: NO", "Q1: NO\nQ2: NO\nQ3: NO"])

    def respond(prompt, n):
        if "Q1: <YES|NO>" in prompt and n <= 2:
            return FakeResponse(completion(next(answers), model=f"route/{n}"))
        return FakeResponse(completion(answer_for(prompt)))
    result = live(tmp_path, Opener(respond))
    table = result["summary"]["answers_by_route"]
    assert table["S1.evidence_absent"]["answers"]["Q1"] == "YES"
    assert table["S1.hypothesis"]["answers"]["Q1"] == "NO"
    assert table["S1.evidence_absent"]["route"] != table["S1.hypothesis"]["route"]
    forbidden = ("consensus", "majority", "agreed", "winner", "truth", "vote", "score")
    for key in all_keys(result):
        assert not any(word in str(key).lower() for word in forbidden), key


def test_the_lab_is_isolated_from_the_protocol_code():
    lab_files = sorted((ROOT / "lab").glob("*.py"))
    for path in lab_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                for marker in (".saipen", "provenance/", "spec/", "DECISIONS.md", "BACKLOG.md"):
                    assert marker not in node.value, f"{path.name} names {marker}"
        assert not imported & {"subprocess", "shutil", "saimail.provenance"}, path.name
        network = imported & {"urllib.request", "urllib.error", "socket", "http.client", "requests"}
        if path.name != "saifren_run.py":
            assert not network, f"{path.name} touches the network"
    for package in ("sailang", "saimail"):
        for path in (ROOT / package).glob("*.py"):
            text = path.read_text(encoding="utf-8")
            assert "import lab" not in text and "from lab" not in text, path


# ------------------------------------------------ declared before measured


def test_every_live_scenario_declares_hypothesis_and_failure_condition(tmp_path):
    plan = sc.build_plan(Profile.load("1"))
    assert {type(u).__name__ for u in plan} == {"Single", "HandoffChain", "LegacyTrial"}
    for unit in plan:
        assert unit.hypothesis.strip() and unit.failure_condition.strip(), unit.unit_id
    result = live(tmp_path, Opener())
    for unit in result["units"]:
        assert unit["hypothesis"] and unit["failure_condition"], unit["unit_id"]


def test_an_undeclared_scenario_is_refused_before_any_call(tmp_path, monkeypatch):
    plan = sc.build_plan(Profile.load("1"))
    broken = plan[:1] + (sc.HandoffChain(unit_id="S2.bad", hypothesis="h", failure_condition=" ",
                                         raw_finding="x", log_channel="LOG:x"),)
    monkeypatch.setattr(sc, "build_plan", lambda profile: broken)
    opener = Opener()
    with pytest.raises(SystemExit):
        live(tmp_path, opener)
    assert opener.requests == []


# ------------------------------------------------ W2: audit wave-2 lifecycle controls


def test_a_send_callback_that_raises_after_dispatch_never_re_dispatches():
    """W2-001: TypeError is not an arity probe once a dispatch happened."""
    dispatches = []

    def send(prompt, model=None):
        dispatches.append(model)
        raise TypeError("sent, then failed")

    runner = lab.Runner(send, lab.CallBudget(3))
    record = runner.call("u", "A", "p", model="m")
    assert dispatches == ["m"], "exactly one dispatch, carrying the model"
    assert record["status"] == "ERROR" and record["error_class"] == "HARNESS_ERROR"
    assert record.get("http_status") is None


def test_a_prompt_only_callback_receives_exactly_one_call():
    """W2-001: capability is decided before the first dispatch, not by retrying."""
    calls = []

    def send(prompt):
        calls.append(prompt)
        return {"output": "ok"}

    runner = lab.Runner(send, lab.CallBudget(3))
    record = runner.call("u", "A", "p", model="m")
    assert calls == ["p"]
    assert record["status"] == "OK"


def test_harness_exceptions_do_not_declare_the_gateway_unreachable():
    """W2-001: a local callback fault is not gateway transport health."""

    def boom(prompt, model=None):
        raise ValueError("harness bug")

    runner = lab.Runner(boom, lab.CallBudget(10))
    for _ in range(lab.MAX_CONSECUTIVE_TRANSPORT_ERRORS + 2):
        runner.call("u", "A", "p")
    assert runner.stopped is None
    assert {c["error_class"] for c in runner.calls} == {"HARNESS_ERROR"}
    # and a genuine transport failure still stops the run (existing control above)


def test_an_auth_refusal_during_catalog_discovery_stops_the_whole_run(tmp_path):
    """W2-002: a credential rejected at discovery is systemic, not unavailability."""

    class Refusing(lab.HttpTransport):
        def get_json(self, path):
            raise urllib.error.HTTPError("http://x", 401, "Unauthorized", {},
                                         io.BytesIO(b"{}"))

    opener = Opener()
    transport = Refusing(KEY, opener=opener, timeout=1)
    result = lab.run(tmp_path, dry_run=False, api_key=KEY, transport=transport,
                     discover=True, sample=True)
    assert result["stopped"].startswith("AUTH_REFUSED")
    assert result["experiment_calls"] == 0
    assert opener.requests == [], "no experiment traffic with a credential already refused"


def test_an_auth_refusal_during_a_membership_probe_stops_further_probes(tmp_path):
    """W2-002: the first 401/403 probe stops the probes, not just that one."""

    class Discovering(lab.HttpTransport):
        def get_json(self, path):
            return {"data": [{"id": "SAIFREN", "owned_by": "combo"},
                             {"id": "beta/big", "owned_by": "beta",
                              "context_length": 10, "capabilities": {}}]}

    opener = Opener(lambda prompt, n: urllib.error.HTTPError(
        "http://x", 403, "Forbidden", {}, io.BytesIO(b"{}")))
    transport = Discovering(KEY, opener=opener, timeout=1)
    result = lab.run(tmp_path, dry_run=False, api_key=KEY, transport=transport,
                     discover=True, sample=True)
    assert len(opener.requests) == 1, "the first refused probe is the last network call"
    assert result["stopped"].startswith("AUTH_REFUSED")
    assert result["experiment_calls"] == 0


def test_two_same_second_runs_keep_both_immutable_artifacts(tmp_path, monkeypatch):
    """W2-003: persistence identity is a unique run id, not a second-resolution stamp."""
    frozen = "2026-09-18T12:00:00Z"
    monkeypatch.setattr(lab, "_now", lambda: frozen)
    first = live(tmp_path, Opener(lambda prompt, n: FakeResponse(completion("one"))))
    second = live(tmp_path, Opener(lambda prompt, n: FakeResponse(completion("two"))))
    p1, p2 = pathlib.Path(first["artifact"]), pathlib.Path(second["artifact"])
    assert p1 != p2 and p1.is_file() and p2.is_file()
    assert json.loads(p1.read_text(encoding="utf-8"))["calls"][0]["output"] == "one"
    assert json.loads(p2.read_text(encoding="utf-8"))["calls"][0]["output"] == "two"
    reports = sorted(tmp_path.glob("SAIFREN_REPORT_*.md"))
    assert len(reports) == 2, "both stamped reports survive; only the latest pointer is mutable"


def test_an_immutable_artifact_is_never_silently_replaced(tmp_path, monkeypatch):
    """W2-003: a collision on an existing historical artifact refuses, never overwrites."""

    class ForcedId:
        hex = "cafebabe0000"

    monkeypatch.setattr(lab, "_now", lambda: "2026-09-18T12:00:00Z")
    monkeypatch.setattr(lab.uuid, "uuid4", lambda: ForcedId())
    first = live(tmp_path, Opener(lambda prompt, n: FakeResponse(completion("one"))))
    before = pathlib.Path(first["artifact"]).read_bytes()
    with pytest.raises(FileExistsError):
        live(tmp_path, Opener(lambda prompt, n: FakeResponse(completion("two"))))
    assert pathlib.Path(first["artifact"]).read_bytes() == before
