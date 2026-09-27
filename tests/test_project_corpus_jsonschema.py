"""T-81 FG-04B JSON_SCHEMA harness: registration freeze, schema identity, admission.

Dry controls run the harness against deterministic fakes: the exact B-018 corpus
is rebuilt locally, the generator and probe requests carry the registered
json_schema response format at frozen token budgets, the reviewer stays
``response_format`` absent, the product reference gate remains authoritative,
and no raw prose is durable.
"""

import json
import pathlib
import socket
from types import SimpleNamespace

import pytest

from lab import experiment_manifest as em
from lab import parse_shape as shape
from lab import project_corpus_generation_pilot as pilot
from lab import project_corpus_jsonschema as js
from lab import reference_telemetry as ref
from lab import saifren_run as live
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag

CANARY = "PRIVATE_JSONSCHEMA_CANARY_9f20e"
STARTED = "2026-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def built():
    return pilot.prepare_input(js.ROOT)


@pytest.fixture(scope="module")
def frozen(built):
    return js.check_registration(root=js.ROOT)


def document(built, transport=None):
    stored, _manifest, built_now, schema_bytes = js.check_registration(root=js.ROOT)
    schema = json.loads(schema_bytes.decode("utf-8"))
    return js._experiment(
        built_now, transport or js.DryTransport(built_now.reflection_corpus),
        schema=schema, schema_sha256=js._digest(schema_bytes),
        allowed_refs=stored["json_schema"]["allowed_evidence_refs"],
        registration_id="sha256:" + "0" * 64,
        registration_file_sha256="0" * 64, dry_run=True,
        started=STARTED, admission=None,
        manifest_block={"file": stored["manifest"]["file"],
                        "identity": stored["manifest"]["identity"],
                        "file_sha256": "0" * 64, "authority": "LIVE_ELIGIBLE",
                        "experiment_id": js.MANIFEST_EXPERIMENT_ID})


# ------------------------------------------------------------- REGISTRATION

def test_registration_matches_frozen_plan(frozen):
    stored, manifest = frozen[0], frozen[1]
    assert stored["routes"] == js.ROUTES
    assert stored["budget"]["max_live_calls"] == 6
    assert stored["budget"]["planned_calls_max"] == 6
    assert stored["token_budgets"]["generator_max_tokens"] == 4096
    assert stored["token_budgets"]["reviewer_max_tokens"] == 2048
    assert stored["token_budgets"]["probe_max_tokens"] == 16
    assert stored["manifest"]["authority"] == "LIVE_ELIGIBLE"
    assert manifest["authority"] == "LIVE_ELIGIBLE"
    assert manifest["experiment_id"] == js.MANIFEST_EXPERIMENT_ID
    assert em.manifest_identity(manifest) == stored["manifest"]["identity"]
    assert stored["single_variable"]["reviewer_response_format"] == "ABSENT (unchanged from T-74)"


def test_registration_refuses_changed_bytes(tmp_path):
    path = tmp_path / "registration.json"
    real = pathlib.Path(js.ROOT) / js.REGISTRATION_FILE
    path.write_bytes(real.read_bytes() + b" ")
    with pytest.raises(SailangError, match="REGISTRATION_MISMATCH"):
        js.check_registration(root=js.ROOT, path=path)


def test_prompt_change_refused(monkeypatch):
    monkeypatch.setattr(pilot, "GENERATOR_TEMPLATE", pilot.GENERATOR_TEMPLATE + " ")
    with pytest.raises(SailangError, match="REGISTRATION_MISMATCH"):
        js.check_registration(root=js.ROOT)


def test_schema_identity_and_policy(frozen):
    stored, _, built = frozen[0], frozen[1], frozen[2]
    schema_path = pathlib.Path(js.ROOT) / js.SCHEMA_FILE
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert js.canonical_bytes(schema) == schema_path.read_bytes()
    assert js._digest(schema_path.read_bytes()) == stored["json_schema"]["sha256"]
    refs = sorted({item.evidence_ref for item in built.reflection_corpus.items})
    assert stored["json_schema"]["allowed_evidence_refs"] == refs
    assert len(refs) == 8
    enum = (schema["oneOf"][1]["properties"]["OBSERVED"]["items"]["properties"]
            ["EVIDENCE_REFS"]["items"]["enum"])
    assert sorted(enum) == refs
    assert stored["schema_policy"]["chosen"] == js.POLICY_CORPUS_ENUM
    assert stored["schema_policy"]["product_gate_remains_authoritative"] is True
    wrapper = js.schema_response_format(schema)
    assert wrapper["type"] == "json_schema"
    assert wrapper["json_schema"]["strict"] is True


def test_manifest_inputs_and_implementation_are_consistent(frozen):
    manifest = frozen[1]
    stored = frozen[0]
    assert manifest["implementation"] == stored["frozen_implementation"]
    if manifest["implementation"] != stored["frozen_implementation"]:
        raise AssertionError("implementation rows drifted")
    inputs = {row["INPUT_ID"]: row for row in manifest["inputs"]}
    assert inputs["REGISTERED_JSON_SCHEMA"]["EXTRACTED_SHA256"] == (
        stored["json_schema"]["sha256"])
    assert inputs["B018_CORPUS_REGISTRATION"]["EXTRACTED_SHA256"] == (
        stored["frozen_inputs"]["b018_registration"]["sha256"])


# ------------------------------------------------------------- SCHEMA GATE

def test_schema_validator_classifies_and_refuses_drift(built):
    _stored, _, built_now, schema_bytes = js.check_registration(root=js.ROOT)
    schema = json.loads(schema_bytes.decode("utf-8"))
    candidate = pilot.two_event_candidate(built_now.reflection_corpus)
    raw = pilot.wire_candidate_text(candidate)
    assert js.schema_check(raw, schema) == (js.JSON_OK, js.SCHEMA_VALID, None)
    outside = pilot.outside_ref_candidate(built_now.reflection_corpus)
    assert js.schema_check(pilot.wire_candidate_text(outside), schema) == (
        js.JSON_OK, js.SCHEMA_INVALID, "CONSTRAINT")
    malformed = raw.replace('"INFERRED"', '"INFERRED_X"')
    assert js.schema_check(malformed, schema) == (
        js.JSON_OK, js.SCHEMA_INVALID, "CONSTRAINT")
    prose = "the model answered with prose and no JSON object"
    assert js.schema_check(prose, schema) == (
        js.JSON_BAD_JSON, js.SCHEMA_NOT_EVALUABLE, None)
    duplicate = '{"result":"NO_ADVICE","result":"NO_ADVICE"}'
    assert js.schema_check(duplicate, schema) == (
        js.JSON_DUPLICATE_KEY, js.SCHEMA_INVALID, "DUPLICATE_KEY")
    assert js.schema_check('{"result":"NO_ADVICE"}', schema) == (
        js.JSON_OK, js.SCHEMA_VALID, None)
    with pytest.raises(SailangError, match="UNSUPPORTED_KEYWORD"):
        js.schema_check('{"result":"NO_ADVICE"}',
                        {"type": "object", "format": "bogus"})


def test_call_ceiling_is_active_and_bounded():
    assert js.PLANNED_CALLS_MAX == 6
    assert js.PROBE_MAX + js.GENERATION_MAX + js.REVIEW_MAX == js.MAX_LIVE_CALLS
    budget = live.CallBudget(js.MAX_LIVE_CALLS)
    for _ in range(js.MAX_LIVE_CALLS):
        budget.spend()
    with pytest.raises(live.BudgetExceeded):
        budget.spend()


# ------------------------------------------------ DRY CONTROL: one variable

def test_dry_role_swap_reaches_review_and_no_advice_skips(built):
    result = document(built)
    assert [(r["generator_role"], r["reviewer_role"]) for r in result["replicates"]] == [
        ("A", "B"), ("B", "A")]
    assert [r["outcome_class"] for r in result["replicates"]] == js.expected_dry_classes()
    assert result["replicates"][0]["outcome"] == ag.APPROVED
    assert result["replicates"][0]["reviewer_calls"] == 1
    assert result["replicates"][0]["reviewed_state_minted"] is True
    assert result["replicates"][1]["outcome"] == ag.NO_ADVICE
    assert result["replicates"][1]["reviewer_calls"] == 0
    assert result["replicates"][0]["event_floor_relation"] == ref.MET
    assert result["replicates"][0]["telemetry"]["corpus_ref_relation"] == ref.CLEAN


def test_generator_and_probe_carry_schema_and_reviewer_does_not(built):
    result = document(built)
    gens = [c for c in result["calls"] if c["function"] == "GENERATOR"]
    revs = [c for c in result["calls"] if c["function"] == "REVIEWER"]
    probes = [c for c in result["calls"] if c["function"] == "PROBE"]
    assert all(c["request_max_tokens"] == 4096 for c in gens)
    assert all(c["request_max_tokens"] == 2048 for c in revs)
    assert all(c["request_max_tokens"] == 16 for c in probes)
    assert all(c["response_format_kind"] == js.KIND_JSON_SCHEMA for c in gens + probes)
    assert all(c["response_format_sha256"] == result["schema"]["sha256"]
               for c in gens + probes)
    assert all(c["response_format_kind"] == js.KIND_NONE for c in revs)
    assert all(c["response_format_sha256"] is None for c in revs)
    assert len(result["probes"]) == 2
    assert all(row["schema_result"] == js.SCHEMA_VALID for row in result["probes"])
    assert all(row["structured_output_capability"] == js.CAP_ACCEPTED
               for row in result["probes"])
    assert all(row["provider_enforces_json_schema"] == js.ENFORCEMENT_NOT_PROVEN
               for row in result["probes"])


def test_no_hidden_retry_and_exact_call_accounting(built):
    result = document(built)
    sent = [c for c in result["calls"] if c["sent"]]
    assert len(sent) == result["budget"]["logical_dispatches"]
    assert result["budget"]["logical_dispatches"] == result["budget"]["spent_total"]
    assert result["budget"]["spent_total"] == 5
    assert result["budget"]["network_calls"] == 0
    assert result["budget"]["retries"] == 0
    assert result["budget"]["repair_calls"] == 0
    assert result["budget"]["replacements"] == 0
    assert result["budget"]["fallbacks"] == 0
    assert all(c["wrapper_retry"] is False for c in result["calls"])
    assert sorted(c["ordinal"] for c in sent) == [1, 2, 3, 4, 5]
    assert [p["ordinal"] for p in result["probes"]] == [1, 2]


def test_reference_gate_and_telemetry_parity_with_outside_ref(built):
    corpus = built.reflection_corpus
    transport = js.DryTransport(corpus, candidate=pilot.outside_ref_candidate(corpus))
    result = document(built, transport)
    first = result["replicates"][0]
    assert first["outcome"] == ag.REJECTED
    assert first["outcome_code"] == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert first["outcome_class"] == js.REFERENCE_GATE_FAILURE
    assert first["outside_ref_count"] == 1
    assert first["reviewer_calls"] == 0
    assert first["telemetry"]["corpus_ref_relation"] == ref.HAS_OUTSIDE_CANONICAL
    assert first["event_floor_relation"] == ref.NOT_EVALUABLE


# ------------------------------------------------ OUTCOME MATRIX UNIT MATRIX

def _generator_stub(metadata):
    return SimpleNamespace(record={"metadata": metadata}, candidate=None)


def _metadata(**overrides):
    record = {"status": "OK", "parser_status": "OK", "parser_error_code": None,
              "schema_status": js.SCHEMA_VALID}
    record.update(overrides)
    return record


def test_outcome_class_matrix_is_total():
    outcome = SimpleNamespace(status=ag.REJECTED, code=None)
    reviewer = SimpleNamespace(calls=0)
    cases = [
        (js.TRANSPORT_FAILURE, _metadata(status="ERROR"), reviewer,
         SimpleNamespace(status=ag.ERROR, code=ag.ALLY_GEN_PROVIDER_ERROR)),
        (js.JSON_PARSE_FAILURE,
         _metadata(parser_status="SCHEMA_ERROR", parser_error_code="ALLY_LAB_BAD_JSON"),
         reviewer, outcome),
        (js.JSON_SCHEMA_FAILURE,
         _metadata(parser_status="SCHEMA_ERROR", parser_error_code="ALLY_LAB_MISSING_FIELD"),
         reviewer, outcome),
        (js.JSON_SCHEMA_FAILURE, _metadata(schema_status=js.SCHEMA_INVALID), reviewer,
         outcome),
        (js.REFERENCE_GATE_FAILURE, _metadata(), reviewer,
         SimpleNamespace(status=ag.REJECTED, code=ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS)),
        (js.EVENT_FLOOR_FAILURE, _metadata(), reviewer,
         SimpleNamespace(status=ag.REJECTED, code=ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS)),
        (js.REVIEWER_FAIL, _metadata(), SimpleNamespace(calls=1),
         SimpleNamespace(status=ag.REJECTED, code=ag.ALLY_GEN_REVIEW_REJECTED)),
        (js.REVIEWER_UNKNOWN, _metadata(), SimpleNamespace(calls=1),
         SimpleNamespace(status=ag.REJECTED, code=ag.ALLY_GEN_REVIEW_UNCERTAIN)),
        (js.REVIEWER_ERROR, _metadata(), SimpleNamespace(calls=1),
         SimpleNamespace(status=ag.ERROR, code=ag.ALLY_GEN_REVIEWER_ERROR)),
        (js.REVIEWER_NOT_REACHED, _metadata(), SimpleNamespace(calls=0),
         SimpleNamespace(status=ag.REJECTED, code="ALLY_GEN_BAD_REPORT")),
        (js.NO_ADVICE_OUTCOME, _metadata(), reviewer,
         SimpleNamespace(status=ag.NO_ADVICE, code=None)),
        (js.REVIEWER_PASS, _metadata(), SimpleNamespace(calls=1),
         SimpleNamespace(status=ag.APPROVED, code=None)),
    ]
    for expected, metadata, reviewer_stub, result in cases:
        assert js.classify_replicate(_generator_stub(metadata), reviewer_stub, result) == (
            expected), expected
    assert js.OUTCOME_CLASSES == frozenset({expected for expected, _, _, _ in cases})


# ------------------------------------------------ ADMISSION

def test_historical_manifest_is_not_live_authority():
    t71 = em.load(pathlib.Path(js.ROOT) / "lab/history/t71_manifest.json")
    assert t71["authority"] == "HISTORICAL_ONLY"
    with pytest.raises(SailangError, match="HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY"):
        em.admit_live(t71, root=js.ROOT)


def test_live_manifest_admits_and_drift_refuses(frozen):
    manifest = frozen[1]
    built = frozen[2]
    schema_bytes = (pathlib.Path(js.ROOT) / js.SCHEMA_FILE).read_bytes()
    evidence = js.pre_live_admission(root=js.ROOT, doc=frozen[0], built=built,
                                     schema_bytes=schema_bytes, manifest=manifest)
    assert evidence["admit_live"] is True
    assert evidence["network_calls"] == 0
    assert all(evidence["checks"].values())
    drifted = json.loads(json.dumps(manifest))
    drifted["authority"] = "HISTORICAL_ONLY"
    with pytest.raises(SailangError, match="HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY"):
        em.admit_live(drifted, root=js.ROOT)


# ------------------------------------------------ PRIVACY

def test_candidate_prose_and_canary_are_not_durable(built, tmp_path):
    corpus = built.reflection_corpus
    base = pilot.two_event_candidate(corpus)
    candidate = aa.AllyAdvice(
        created=base.created, work_context=base.work_context,
        observed_scope=base.observed_scope, observed=base.observed,
        inferred=CANARY, guidance_mode=base.guidance_mode, suggested=base.suggested,
        counterevidence=base.counterevidence, uncertainty=base.uncertainty)
    result = document(built, js.DryTransport(corpus, candidate=candidate))
    serialized = json.dumps(result, ensure_ascii=False)
    assert CANARY not in serialized
    assert pilot.wire_candidate_text(candidate) not in serialized
    for item in corpus.items:
        assert item.content not in serialized
    paths = js._write(tmp_path, js.check_registration(root=js.ROOT)[0], result, "")
    for path in paths.values():
        assert CANARY not in pathlib.Path(path).read_text(encoding="utf-8")


def test_privacy_tripwire_refuses_before_writes(built, tmp_path):
    result = document(built)
    result[CANARY] = CANARY
    with pytest.raises(SailangError, match=shape.PRIVACY_TRIPWIRE):
        js._write(tmp_path, js.check_registration(root=js.ROOT)[0], result, "")
    assert not list(tmp_path.iterdir())


# ------------------------------------------------ RUN LIFECYCLE

def test_dry_run_never_touches_network_or_credentials(tmp_path, monkeypatch, built):
    def forbidden(*args, **kwargs):
        pytest.fail("dry run attempted network or credential resolution")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(js, "resolve", forbidden)
    monkeypatch.setattr(js, "SchemaTransport", forbidden)
    real_write = js._write
    monkeypatch.setattr(js, "_write", lambda root, doc, doc_, key: real_write(
        tmp_path, doc, doc_, key))
    result = js.run(dry_run=True, root=js.ROOT)
    assert result["budget"]["network_calls"] == 0
    assert result["outcome_classes"] == js.expected_dry_classes()


def test_live_requires_dry_control_and_marker(tmp_path, monkeypatch, built):
    monkeypatch.setattr(js, "resolve", lambda: pytest.fail("credential touched too early"))
    with pytest.raises(SailangError, match="REGISTRATION_MISSING"):
        js.run(root=tmp_path)


def test_reserve_is_publish_once(tmp_path):
    path = tmp_path / "attempt.json"
    js._reserve(path, "sha256:" + "0" * 64)
    with pytest.raises(SailangError, match="ALREADY_ATTEMPTED"):
        js._reserve(path, "sha256:" + "0" * 64)
