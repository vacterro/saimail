"""T-73 capability gate: registration freeze, classification, privacy, dry controls.

Every probe here is synthetic and offline; the one real network path is covered
in ``tests/test_structured_output_transport.py`` through fake openers.
"""

import ast
import hashlib
import json
import pathlib
import socket
from types import SimpleNamespace

import pytest

from lab import parse_shape as shape
from lab import saifren_run as live
from lab import structured_output_capability as cap
from sailang.errors import SailangError

CANARY = "PRIVATE_CAPABILITY_CANARY_b31c7"
STARTED = "2026-09-20T00:00:00Z"


def document(transport=None, dry_run=True):
    return cap._experiment(transport or cap.DryTransport(), dry_run=dry_run, started=STARTED)


def registered():
    return json.loads(cap.REGISTRATION_PATH.read_text(encoding="utf-8"))


# ------------------------------------------------------------- REGISTRATION


def test_registration_freezes_routes_probes_and_budget():
    doc = registered()
    assert doc["routes"] == cap.ROUTES
    assert doc["probe_order"] == [f"{route}/{kind}" for route, kind in cap.PROBE_ORDER]
    assert doc["budget"]["max_live_calls"] == 6
    assert doc["budget"]["calls_per_route"] == 3
    assert doc["budget"]["discovery"] is False
    assert doc["budget"]["retries"] == 0
    assert doc["budget"]["repairs"] == 0
    assert doc["budget"]["replacements"] == 0
    assert doc["budget"]["fallbacks"] == 0
    assert set(doc["result_vocabulary"]) == cap.RESULT_VOCABULARY
    assert "SUPPORTED" not in doc["result_vocabulary"]


def test_registration_refuses_changed_bytes(tmp_path):
    path = tmp_path / "registration.json"
    path.write_bytes(cap.REGISTRATION_PATH.read_bytes() + b" ")
    with pytest.raises(SailangError, match="REGISTRATION_MISMATCH"):
        cap.registration(path=path)


def test_registration_identity_changes_on_capability_policy_mutation():
    doc = registered()
    assert cap.registration_sha256(doc) == cap.REGISTRATION_SHA256
    mutations = []
    budget = json.loads(json.dumps(doc))
    budget["budget"]["max_live_calls"] = 7
    mutations.append(budget)
    probe = json.loads(json.dumps(doc))
    probe["probes"][0]["max_tokens"] = 4095
    mutations.append(probe)
    ordering = json.loads(json.dumps(doc))
    ordering["probe_order"] = list(reversed(ordering["probe_order"]))
    mutations.append(ordering)
    vocabulary = json.loads(json.dumps(doc))
    vocabulary["result_vocabulary"].append("SUPPORTED")
    mutations.append(vocabulary)
    for mutated in mutations:
        assert cap.registration_sha256(mutated) != cap.REGISTRATION_SHA256


def test_synthetic_prompt_frozen_and_in_context_corridor():
    doc = registered()
    prompt = cap.synthetic_context_prompt()
    assert shape.digest(prompt) == doc["context"]["prompt_sha256"]
    assert len(prompt.encode("utf-8")) == doc["context"]["prompt_bytes"]
    tokens = live.estimate_tokens(prompt)
    assert tokens == doc["context"]["local_prompt_tokens"]
    low, high = doc["context"]["corridor"]
    assert low <= tokens <= high
    assert doc["context"]["contains_b018_corpus"] is False
    assert doc["context"]["contains_project_content"] is False


def test_probe_definitions_are_exact():
    doc = registered()
    probes = {row["probe_id"]: row for row in doc["probes"]}
    assert probes["A/BUDGET_4096"]["max_tokens"] == 4096
    assert probes["A/BUDGET_4096"]["response_format"] is None
    assert probes["B/BUDGET_4096"]["response_format"] is None
    for probe_id in ("A/JSON_OBJECT", "B/JSON_OBJECT"):
        assert probes[probe_id]["max_tokens"] == 128
        assert probes[probe_id]["response_format"] == {"type": "json_object"}
    for probe_id in ("A/JSON_SCHEMA", "B/JSON_SCHEMA"):
        assert probes[probe_id]["max_tokens"] == 128
        assert probes[probe_id]["response_format"] == cap.JSON_SCHEMA_FORMAT
    schema = cap.JSON_SCHEMA_FORMAT["json_schema"]
    assert schema["name"] == "saimail_capability_probe"
    assert schema["strict"] is True
    assert schema["schema"] == {"type": "object",
                                "properties": {"probe": {"type": "string", "enum": ["OK"]}},
                                "required": ["probe"], "additionalProperties": False}


def test_no_discovery_or_replacement_path_exists():
    source = pathlib.Path(cap.__file__).read_text(encoding="utf-8")
    assert "saifren_population" not in source
    assert "get_json" not in source
    assert not hasattr(cap, "resolve_population")
    assert not hasattr(cap, "select_participant")


# ---------------------------------------------------------- CLASSIFICATION


@pytest.mark.parametrize("call_status,error_class,http_status,output,expected,conformed", [
    ("OK", None, 200, '{"probe":"OK"}', cap.RESULT_ACCEPTED_CONFORMING, True),
    ("OK", None, 200, '```json\n{"probe":"OK"}\n```',
     cap.RESULT_ACCEPTED_NONCONFORMING, False),
    ("OK", None, 200, '{"probe":"OK"} trailing prose',
     cap.RESULT_ACCEPTED_NONCONFORMING, False),
    ("OK", None, 200, 'prefix {"probe":"OK"}', cap.RESULT_ACCEPTED_NONCONFORMING, False),
    ("OK", None, 200, '{"probe":"OK","extra":1}', cap.RESULT_ACCEPTED_NONCONFORMING, False),
    ("OK", None, 200, '{"probe":"NO"}', cap.RESULT_ACCEPTED_NONCONFORMING, False),
    ("OK", None, 200, '[{"probe":"OK"}]', cap.RESULT_ACCEPTED_NONCONFORMING, False),
    ("OK", None, 200, '{"probe":"OK","probe":"OK"}',
     cap.RESULT_ACCEPTED_NONCONFORMING, False),
    ("OK", None, 200, '', cap.RESULT_ACCEPTED_NONCONFORMING, False),
    ("ERROR", "HTTPError", 400, "", cap.RESULT_REJECTED, False),
    ("ERROR", "HTTPError", 404, "", cap.RESULT_REJECTED, False),
    ("ERROR", "HTTPError", 415, "", cap.RESULT_REJECTED, False),
    ("ERROR", "HTTPError", 422, "", cap.RESULT_REJECTED, False),
    ("ERROR", "HTTPError", 401, "", cap.RESULT_AUTH_REFUSED, False),
    ("ERROR", "HTTPError", 403, "", cap.RESULT_AUTH_REFUSED, False),
    ("ERROR", "URLError", None, "", cap.RESULT_TRANSPORT_ERROR, False),
    ("ERROR", "TimeoutError", None, "", cap.RESULT_TRANSPORT_ERROR, False),
    ("ERROR", "MalformedResponse", 200, "", cap.RESULT_TRANSPORT_ERROR, False),
    ("ERROR", "EmptyOutput", 200, "", cap.RESULT_ACCEPTED_NONCONFORMING, False),
    ("ERROR", "HARNESS_ERROR", None, "", cap.RESULT_TRANSPORT_ERROR, False),
    ("NOT_RUN", None, None, "", cap.RESULT_NOT_RUN, False),
])
def test_closed_classification_mapping(call_status, error_class, http_status, output,
                                        expected, conformed):
    status, result_conformed = cap.classify(call_status, error_class, http_status, output)
    assert status == expected
    assert result_conformed is conformed


# ------------------------------------------------------------- DRY CONTROLS


def test_dry_run_is_deterministic_and_spends_exactly_six_calls():
    first = document()
    second = document()
    assert first["matrix"] == cap.expected_dry_matrix()
    assert first["budget"] == {"max_live_calls": 6, "spent": 6, "dispatch_count": 6,
                               "retries": 0, "repairs": 0, "replacements": 0,
                               "fallbacks": 0, "network_calls": 0}
    assert [call["probe_id"] for call in first["calls"]] == [
        f"{route}/{kind}" for route, kind in cap.PROBE_ORDER]
    assert all(call["sent"] for call in first["calls"])
    assert first["status"] == "COMPLETED"
    assert first["stop_reason"] is None
    assert first["calls"] == second["calls"]
    assert first["context"] == second["context"]


def test_dry_run_records_the_4000_character_local_cap_observation():
    result = document()
    capped = [call for call in result["calls"] if call["output_truncated"]]
    assert [call["probe_id"] for call in capped] == ["A/JSON_SCHEMA"]
    assert capped[0]["output_bytes"] == cap.LOCAL_VISIBLE_OUTPUT_CAP_CHARS
    assert result["local_output_cap_chars"] == 4000
    assert result["real_4096_run_safe_with_current_local_output_path"] is False
    assert result["native_enforcement_proven"] is False


def test_dry_rejection_does_not_stop_independent_probes():
    result = document()
    assert result["matrix"]["json_object"]["B"] == cap.RESULT_REJECTED
    assert result["matrix"]["json_schema"]["A"] == cap.RESULT_ACCEPTED_NONCONFORMING
    assert result["budget"]["spent"] == 6
    assert result["budget"]["fallbacks"] == 0


def stub_result(model, prompt, max_tokens, response_format, **extra):
    body = cap.request_body(model, prompt, max_tokens, response_format)
    result = {"output": "", "reported_model": model, "http_status": None,
              "finish_reason": "stop", "output_truncated": False, "usage": {},
              "request_body_sha256": hashlib.sha256(body).hexdigest(),
              "request_body_bytes": len(body)}
    result.update(extra)
    return result


def test_auth_refusal_stops_remaining_and_marks_them_not_run():
    class AuthRefusing(cap.DryTransport):
        def send_probe(self, prompt, *, model, max_tokens, response_format=None):
            self.dispatches += 1
            return stub_result(model, prompt, max_tokens, response_format,
                               error_class="HTTPError", error="HTTP 401 synthetic",
                               http_status=401)

    result = document(AuthRefusing())
    assert result["status"] == "STOPPED"
    assert result["stop_reason"] == "AUTH_REFUSED"
    assert result["calls"][0]["status"] == cap.RESULT_AUTH_REFUSED
    assert all(call["status"] == cap.RESULT_NOT_RUN for call in result["calls"][1:])
    assert result["budget"]["spent"] == 1
    assert result["budget"]["dispatch_count"] == 1


def test_missing_request_body_evidence_refuses_the_run():
    class Mute(cap.DryTransport):
        def send_probe(self, prompt, *, model, max_tokens, response_format=None):
            return {"output": '{"probe":"OK"}', "reported_model": model,
                    "http_status": 200, "finish_reason": "stop",
                    "output_truncated": False, "usage": {}}
    with pytest.raises(SailangError, match="CAPABILITY_EVIDENCE_MISSING"):
        document(Mute())


def test_error_body_is_hashed_never_persisted():
    class Leaky(cap.DryTransport):
        def send_probe(self, prompt, *, model, max_tokens, response_format=None):
            return stub_result(model, prompt, max_tokens, response_format,
                               error_class="HTTPError", http_status=400,
                               error=f"HTTP 400 request_id=req_{CANARY} {CANARY}")

    result = document(Leaky())
    serialized = json.dumps(result)
    assert CANARY not in serialized
    first = result["calls"][0]
    assert first["error_sha256"] == shape.digest(
        f"HTTP 400 request_id=req_{CANARY} {CANARY}")
    assert first["error_bytes"] == len(
        f"HTTP 400 request_id=req_{CANARY} {CANARY}".encode())
    assert first["error_class"] == "HTTPError"


def test_closed_schema_refuses_unexpected_keys_before_any_write(tmp_path, monkeypatch):
    result = document()
    result["calls"][0][CANARY] = CANARY
    with pytest.raises(SailangError):
        cap._write(tmp_path, cap.registration(), result, "")
    assert not list(tmp_path.rglob("*"))
    monkeypatch.setattr(shape, "validate", lambda *args: None)
    paths = cap._write(tmp_path, cap.registration(), result, "")
    assert CANARY in pathlib.Path(paths["dry"]).read_text(encoding="utf-8")


def imported_modules(path):
    tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_side_effects_and_protected_inputs():
    result = document()
    assert set(result["side_effects"].values()) == {0}
    assert set(result["privacy"].values()) == {False}
    doc = cap.registration()
    protected = {row["path"] for row in doc["protected_files"]}
    assert {"lab/ally_generation_live.py", "lab/saifren_run.py",
            "saimail/ally_generation.py", "saimail/publish.py"} <= protected
    forbidden = {"saimail.ally_advice", "saimail.ally_generation",
                 "saimail.project_corpus", "saimail.human_attention",
                 "saimail.acceptance", "saimail.postoffice",
                 "lab.ally_generation_live", "lab.project_corpus_generation_pilot"}
    assert imported_modules(cap.__file__) & forbidden == set()
    assert result["side_effects"]["b018_corpus_reads"] == 0
    assert result["side_effects"]["production_generation"] == 0
    assert result["side_effects"]["reviewer_calls"] == 0


# --------------------------------------------------------- ARTIFACTS & RUN


def test_write_produces_artifact_report_and_analysis(tmp_path):
    result = document(dry_run=False)
    paths = cap._write(tmp_path, cap.registration(), result, "")
    assert set(paths) == {"artifact", "report", "analysis"}
    artifact = json.loads(pathlib.Path(paths["artifact"]).read_text(encoding="utf-8"))
    shape.validate(artifact, cap.ARTIFACT_SCHEMA)
    assert artifact["dry_run"] is False
    report = pathlib.Path(paths["report"]).read_text(encoding="utf-8")
    analysis = pathlib.Path(paths["analysis"]).read_text(encoding="utf-8")
    for number in range(1, 13):
        assert f"{number}. " in report
    assert "analysis" in analysis.lower()
    assert all(pathlib.Path(path).name for path in paths.values())


def test_report_answers_all_twelve_questions():
    result = document()
    report = cap.render_report(result)
    for number in range(1, 13):
        assert f"{number}. " in report
    assert "REQUEST_ACCEPTED_NONCONFORMING" in report
    assert "Native enforcement proven: False" in report
    assert "safe: False" in report
    assert "fallbacks 0" in report
    analysis = cap.render_analysis(result)
    assert "descriptive only" in analysis
    assert "local next-gate requirement" in analysis


def test_run_dry_then_live_is_exclusive_and_credential_gated(tmp_path, monkeypatch):
    doc = cap.registration()
    monkeypatch.setattr(cap, "registration", lambda *args, **kwargs: doc)
    dry = cap.run(dry_run=True, root=tmp_path)
    assert dry["budget"]["network_calls"] == 0
    marker = tmp_path / doc["attempt_marker"]
    assert not marker.exists()

    def unavailable():
        raise cap.CredentialNotProvisioned("no credential for the test")
    monkeypatch.setattr(cap, "resolve", unavailable)
    with pytest.raises(SailangError, match="CAPABILITY_CREDENTIAL_UNAVAILABLE"):
        cap.run(root=tmp_path)
    assert not marker.exists()

    monkeypatch.setattr(cap, "resolve", lambda: SimpleNamespace(secret="fake-test-secret"))
    monkeypatch.setattr(cap, "CapabilityTransport", lambda key: cap.DryTransport())
    live_result = cap.run(root=tmp_path)
    assert live_result["status"] == "COMPLETED"
    assert marker.exists()
    artifact_path = pathlib.Path(live_result["artifacts"]["artifact"])
    assert artifact_path.name.startswith("structured_output_capability_")
    assert live_result["artifacts"]["report"].endswith(".md")
    assert not list(tmp_path.rglob("*.tmp"))


def test_one_attempt_marker_survives_second_invocation(tmp_path, monkeypatch):
    doc = cap.registration()
    monkeypatch.setattr(cap, "registration", lambda *args, **kwargs: doc)
    cap.run(dry_run=True, root=tmp_path)
    monkeypatch.setattr(cap, "resolve", lambda: SimpleNamespace(secret="fake-test-secret"))
    monkeypatch.setattr(cap, "CapabilityTransport", lambda key: cap.DryTransport())
    cap.run(root=tmp_path)
    marker = tmp_path / doc["attempt_marker"]
    original = marker.read_bytes()
    with pytest.raises(SailangError, match="ALREADY_ATTEMPTED"):
        cap.run(root=tmp_path)
    assert marker.read_bytes() == original


def test_live_requires_a_matching_dry_control(tmp_path, monkeypatch):
    doc = cap.registration()
    monkeypatch.setattr(cap, "registration", lambda *args, **kwargs: doc)
    monkeypatch.setattr(cap, "resolve", lambda: pytest.fail("credential touched too early"))
    with pytest.raises(SailangError, match="CAPABILITY_DRY_CONTROL_REQUIRED"):
        cap.run(root=tmp_path)
    assert not list(tmp_path.rglob("*"))


def test_reserve_is_publish_once(tmp_path):
    path = tmp_path / "attempt.json"
    cap._reserve(path)
    with pytest.raises(SailangError, match="CAPABILITY_ALREADY_ATTEMPTED"):
        cap._reserve(path)


def test_dry_run_never_touches_network_or_credentials(tmp_path, monkeypatch):
    doc = cap.registration()
    monkeypatch.setattr(cap, "registration", lambda *args, **kwargs: doc)

    def forbidden(*args, **kwargs):
        pytest.fail("dry run attempted network or credential resolution")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(cap, "resolve", forbidden)
    monkeypatch.setattr(live, "HttpTransport", forbidden)
    result = cap.run(dry_run=True, root=tmp_path)
    assert result["budget"]["network_calls"] == 0
    assert result["status"] == "COMPLETED"
