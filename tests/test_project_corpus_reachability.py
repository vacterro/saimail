"""Exact corpus, authoritative parsers, privacy failures and single-attempt controls."""

import hashlib
import json
import shutil
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from lab import parse_shape as shape
from lab import project_corpus_generation_pilot as pilot
from lab import project_corpus_reachability as reach
from lab import saifren_run as live
from sailang.errors import SailangError
from saimail import ally_generation as ag

CANARY = "PRIVATE_REACHABILITY_CANARY_a724c"
STARTED = "2026-09-20T00:00:00Z"


@pytest.fixture(scope="module")
def built():
    return pilot.prepare_input(reach.ROOT)


@pytest.fixture(scope="module")
def frozen_root(tmp_path_factory):
    """Validate T-71 against its exact inputs, including pre-T-65 quarantine.

    No registration or runtime drift gate is changed. The archived source is
    data only, never imported; current production behavior has its own tests.
    """
    root = tmp_path_factory.mktemp("t71-frozen-inputs")
    doc = json.loads(reach.REGISTRATION_PATH.read_bytes())
    for row in [doc["contract"], *doc["protected_files"]]:
        source = reach.ROOT / row["path"]
        if row["path"] == "saimail/quarantine.py":
            source = Path(__file__).parent / "fixtures/t71/quarantine.py.txt"
        elif row["path"] == "saimail/legacy.py":
            source = Path(__file__).parent / "fixtures/t71/legacy.py.txt"
        elif row["path"] == "saimail/postoffice.py":
            source = Path(__file__).parent / "fixtures/t71/postoffice.py.txt"
        elif row["path"] == "saimail/envelope.py":
            source = Path(__file__).parent / "fixtures/t71/envelope.py.txt"
        body = source.read_bytes()
        assert hashlib.sha256(body).hexdigest() == row["sha256"], row["path"]
        target = root / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
    return root


@pytest.fixture
def registered(frozen_root):
    return reach.registration(root=frozen_root)


def document(built, transport=None):
    return reach._experiment(built, transport or reach.DryTransport(built.reflection_corpus),
                              dry_run=True, started=STARTED)


class FixtureTransport(reach.DryTransport):
    def __init__(self, corpus, generator=None, reviewer=None):
        super().__init__(corpus)
        self.generator = generator
        self.reviewer = reviewer
        self.sends = 0

    def send(self, prompt, model=None):
        self.sends += 1
        if prompt == pilot.generator_prompt(self.corpus):
            text = self.generator if self.generator is not None else pilot.wire_candidate_text(self.candidate)
        else:
            text = self.reviewer if self.reviewer is not None else pilot.wire_review_text(self.candidate, self.corpus)
        return self._ok(text, model)


def test_registration_matches_frozen_inputs_and_prompts(registered):
    doc = registered
    assert doc["routes"] == reach.ROUTES
    assert doc["budget"]["max_live_calls"] == 6
    assert doc["prompts"]["changes_from_t69"] == "NONE"


def test_registration_refuses_changed_bytes(tmp_path):
    path = tmp_path / "registration.json"
    path.write_bytes(reach.REGISTRATION_PATH.read_bytes() + b" ")
    with pytest.raises(SailangError, match="REGISTRATION_MISMATCH"):
        reach.registration(path=path)


def test_prompt_change_refused(monkeypatch, frozen_root):
    monkeypatch.setattr(pilot, "GENERATOR_TEMPLATE", pilot.GENERATOR_TEMPLATE + " ")
    with pytest.raises(SailangError, match="PROMPT_DRIFT"):
        reach.registration(root=frozen_root)


def test_registration_refuses_protected_source_drift(frozen_root, tmp_path):
    root = tmp_path / "changed"
    shutil.copytree(frozen_root, root)
    path = root / "saimail/quarantine.py"
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(SailangError, match="PROTECTED_INPUT_DRIFT"):
        reach.registration(root=root)


def test_dry_role_swap_reaches_review_and_no_advice_skips(built):
    result = document(built)
    assert result["budget"] == {"max_calls": 6, "spent_total": 5, "spent_probe": 2,
        "spent_generation": 2, "spent_review": 1, "retries": 0, "repair_calls": 0, "network_calls": 0}
    assert [(r["generator_role"], r["reviewer_role"]) for r in result["replicates"]] == [("A", "B"), ("B", "A")]
    assert [r["outcome"] for r in result["replicates"]] == [ag.APPROVED, ag.NO_ADVICE]
    assert [r["reviewer_calls"] for r in result["replicates"]] == [1, 0]
    assert all(c["parser_status"] == "OK" for c in result["calls"] if c["function"] != "PROBE")


@pytest.mark.parametrize("raw", [
    '```json\n{"result":"NO_ADVICE"}\n```', 'prefix {"result":"NO_ADVICE"}',
    '{"result":"NO_ADVICE"} suffix', '{"result":"NO_ADVICE"} {}',
    '{"result":', '{"result":"NO_ADVICE","result":"NO_ADVICE"}',
    '{"result":"NO_ADVICE","' + CANARY + '":"' + CANARY + '"}',
    '{}', '[]', '{"result":"CANDIDATE","OBSERVED":"bad"}',
])
def test_generator_malformed_is_not_retried_or_reviewed(built, raw):
    transport = FixtureTransport(built.reflection_corpus, generator=raw)
    result = document(built, transport)
    assert transport.sends == 2
    assert result["budget"]["spent_review"] == 0
    assert all(r["outcome"] == ag.ERROR for r in result["replicates"])
    assert CANARY not in json.dumps(result)


@pytest.mark.parametrize("kind", ["fence", "wrong_identity", "unknown", "missing", "duplicate", "wrong_type"])
def test_reviewer_malformed_is_not_repaired(built, kind):
    transport = FixtureTransport(built.reflection_corpus)
    text = pilot.wire_review_text(transport.candidate, transport.corpus, rationale=CANARY)
    row = json.loads(text)
    if kind == "fence":
        text = "```json\n" + text + "\n```"
    elif kind == "duplicate":
        text = text[:-1] + ',"candidate_id":"' + CANARY + '"}'
    else:
        if kind == "wrong_identity":
            row["candidate_id"] = "sha256:" + "0" * 64
        elif kind == "unknown":
            row["dimensions"][0][CANARY] = CANARY
        elif kind == "missing":
            del row["dimensions"][0]["rationale"]
        else:
            row["dimensions"] = CANARY
        text = json.dumps(row)
    transport.reviewer = text
    result = document(built, transport)
    assert transport.sends == 4
    assert result["budget"]["spent_review"] == 2
    assert all(not r["reviewed_state_minted"] for r in result["replicates"])
    assert all(c["parser_status"] == "SCHEMA_ERROR" for c in result["calls"] if c["function"] == "REVIEWER")
    assert CANARY not in json.dumps(result)


@pytest.mark.parametrize("verdict", [ag.FAIL, ag.UNKNOWN])
def test_review_fail_unknown_refuse_approval(built, verdict):
    transport = FixtureTransport(built.reflection_corpus)
    transport.reviewer = pilot.wire_review_text(transport.candidate, transport.corpus,
        overrides={ag.OBSERVATION_SUPPORT: verdict}, rationale=CANARY)
    result = document(built, transport)
    assert all(r["outcome"] == ag.REJECTED for r in result["replicates"])
    assert all(not r["reviewed_state_minted"] for r in result["replicates"])


def test_outside_ref_gate_skips_review(built):
    transport = FixtureTransport(built.reflection_corpus,
        generator=pilot.wire_candidate_text(pilot.outside_ref_candidate(built.reflection_corpus)))
    result = document(built, transport)
    assert all(r["outcome_code"] == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS for r in result["replicates"])
    assert result["budget"]["spent_review"] == 0


def test_one_event_gate_skips_review():
    corpus = pilot.one_event_fixture()
    raw = pilot.wire_candidate_text(pilot.one_event_candidate(corpus))
    def send(prompt, model=None):
        return reach.DryTransport._ok(raw, model)
    dispatch = reach.ObservingDispatch(live.Runner(send, live.CallBudget(6)))
    result = reach.execute_replicate(dispatch, corpus, 1)
    assert result["outcome_code"] == ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS
    assert result["reviewer_calls"] == 0


def test_observer_error_does_not_change_acceptance(built, monkeypatch):
    def boom(*args):
        raise RuntimeError(CANARY)
    monkeypatch.setattr(shape, "observe", boom)
    result = document(built)
    assert [r["outcome"] for r in result["replicates"]] == [ag.APPROVED, ag.NO_ADVICE]
    assert all(c["parse_shape"]["syntax"] == "OBSERVER_ERROR" for c in result["calls"] if c["function"] != "PROBE")
    assert CANARY not in json.dumps(result)


def test_provider_nested_metadata_and_runner_are_scrubbed(built):
    def send(prompt, model=None):
        return {"output": '{"result":"NO_ADVICE"}', "reported_model": CANARY,
            "provider": CANARY, "usage": {"prompt_tokens": CANARY, "nested": {"body": CANARY}},
            "route_headers": {CANARY: CANARY}, "body": CANARY, "exception": CANARY,
            "response": {"body": CANARY}, "finish_reason": CANARY}
    runner = live.Runner(send, live.CallBudget(6))
    dispatch = reach.ObservingDispatch(runner)
    result = reach.execute_replicate(dispatch, built.reflection_corpus, 1)
    assert result["outcome"] == ag.NO_ADVICE
    assert runner.calls == [{}]
    assert CANARY not in json.dumps(dispatch.calls)
    assert dispatch.calls[0]["reported_model"]["known"] == "OTHER"


def test_transport_exception_body_never_escapes(built):
    def boom(prompt, model=None):
        raise RuntimeError(CANARY)
    runner = live.Runner(boom, live.CallBudget(6))
    dispatch = reach.ObservingDispatch(runner)
    result = reach.execute_replicate(dispatch, built.reflection_corpus, 1)
    assert result["outcome"] == ag.ERROR
    assert dispatch.calls[0]["error_body"]["bytes"] > 0
    assert CANARY not in json.dumps(dispatch.calls)
    assert runner.calls == [{}]


@pytest.mark.parametrize("status", [401, 403, 500])
def test_failed_probe_stops_without_content_or_replacement(built, status):
    class Failed(reach.DryTransport):
        def probe(self, model):
            return {"error_class": "HTTPError", "http_status": status, "error": CANARY}
        def send(self, *args, **kwargs):
            pytest.fail("corpus must not be sent after failed probe")
    result = document(built, Failed(built.reflection_corpus))
    assert result["status"] == "NO_GO_POPULATION"
    assert result["budget"]["spent_total"] == 1
    assert not result["replicates"]
    assert CANARY not in json.dumps(result)


def test_auth_refusal_in_generation_stops_later_sends(built):
    class Failed(reach.DryTransport):
        def send(self, *args, **kwargs):
            return {"error_class": "HTTPError", "http_status": 401, "error": CANARY}
    result = document(built, Failed(built.reflection_corpus))
    assert result["status"] == "STOPPED"
    assert result["budget"]["spent_total"] == 3
    assert result["budget"]["spent_generation"] == 1


def test_same_reported_model_does_not_claim_cross_model(built):
    class Same(reach.DryTransport):
        @staticmethod
        def _ok(output, model):
            return reach.DryTransport._ok(output, "MiniMaxAI/MiniMax-M3")
    result = document(built, Same(built.reflection_corpus))
    assert result["replicates"][0]["same_reported_model_pair"] is True


@pytest.mark.parametrize("location", ["root", "shape", "usage", "replicate", "rationale"])
def test_privacy_tripwire_refuses_before_writes(built, tmp_path, location, registered):
    result = document(built)
    target = {"root": result, "shape": result["calls"][2]["parse_shape"],
              "usage": result["calls"][2]["usage"], "replicate": result["replicates"][0],
              "rationale": result["replicates"][0]["review_verdicts"][0]}[location]
    target[CANARY] = CANARY
    with pytest.raises(SailangError, match=shape.PRIVACY_TRIPWIRE):
        reach._write(tmp_path, registered, result, "")
    assert not list(tmp_path.iterdir())


def test_canaries_absent_from_all_artifacts_and_report(built, tmp_path, registered):
    transport = FixtureTransport(built.reflection_corpus)
    wire = json.loads(pilot.wire_candidate_text(transport.candidate))
    for key in ("WORK_CONTEXT", "INFERRED", "SUGGESTED", "UNCERTAINTY"):
        wire[key] = CANARY
    for item in wire["OBSERVED"] + wire["COUNTEREVIDENCE"]:
        item["STATEMENT"] = CANARY
    transport.generator = json.dumps(wire)
    candidate = reach.strict.parse_generator_output(transport.generator).candidate
    transport.reviewer = pilot.wire_review_text(candidate, transport.corpus, rationale=CANARY)
    result = document(built, transport)
    result["dry_run"] = False
    paths = reach._write(tmp_path, registered, result, "")
    for path in paths.values():
        text = Path(path).read_text(encoding="utf-8")
        assert CANARY not in text
        assert all(item.content not in text for item in built.reflection_corpus.items)


def test_disabled_privacy_boundary_red_control(built, tmp_path, monkeypatch, registered):
    result = document(built)
    result[CANARY] = CANARY
    with pytest.raises(SailangError):
        reach._write(tmp_path, registered, result, "")
    monkeypatch.setattr(shape, "validate", lambda *args: None)
    paths = reach._write(tmp_path, registered, result, "")
    assert CANARY in Path(paths["dry"]).read_text(encoding="utf-8")


def setup_workspace(monkeypatch, tmp_path, built, doc):
    monkeypatch.setattr(reach, "registration", lambda *args: doc)
    monkeypatch.setattr(pilot, "prepare_input", lambda *args: built)
    path = tmp_path / "lab/out/project_corpus_generation_live_20260919T220641Z.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"harness": {"base_url": live.BASE_URL}}), encoding="utf-8")
    return doc


def test_dry_run_network_and_credential_tripwires(built, tmp_path, monkeypatch, registered):
    doc = setup_workspace(monkeypatch, tmp_path, built, registered)
    def forbidden(*args, **kwargs):
        pytest.fail("dry run attempted network or credential resolution")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(reach, "resolve", forbidden)
    monkeypatch.setattr(live, "HttpTransport", forbidden)
    result = reach.run(dry_run=True, root=tmp_path)
    assert result["budget"]["network_calls"] == 0
    assert not (tmp_path / doc["attempt_marker"]).exists()


def test_one_attempt_survives_second_invocation(built, tmp_path, monkeypatch, registered):
    doc = setup_workspace(monkeypatch, tmp_path, built, registered)
    reach.run(dry_run=True, root=tmp_path)
    monkeypatch.setattr(reach, "resolve", lambda: SimpleNamespace(secret="fake-test-secret"))
    monkeypatch.setattr(live, "HttpTransport", lambda key: reach.DryTransport(built.reflection_corpus))
    result = reach.run(root=tmp_path)
    assert result["status"] == "COMPLETED"
    marker = tmp_path / doc["attempt_marker"]
    original = marker.read_bytes()
    with pytest.raises(SailangError, match="ALREADY_ATTEMPTED"):
        reach.run(root=tmp_path)
    assert marker.read_bytes() == original


def test_exclusive_attempt_race_and_crash_never_allow_retry(tmp_path):
    path = tmp_path / "attempt.json"
    reach._reserve(path)
    with pytest.raises(SailangError, match="ALREADY_ATTEMPTED"):
        reach._reserve(path)


def test_input_drift_precedes_credentials_and_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(reach, "registration", lambda *args: reach.registration)
    def drift(*args):
        raise SailangError(pilot.NO_GO_INPUT_DRIFT, "test drift")
    monkeypatch.setattr(pilot, "prepare_input", drift)
    monkeypatch.setattr(reach, "resolve", lambda: pytest.fail("credential touched before input gate"))
    with pytest.raises(SailangError, match=pilot.NO_GO_INPUT_DRIFT):
        reach.run(root=tmp_path)
    assert not list(tmp_path.iterdir())
