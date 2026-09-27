"""T-96 / V2-03 reviewer structured-output harness: registration, schema, admission.

The single intentional variable is the reviewer ``response_format``:
ABSENT (FG-04B) -> JSON_SCHEMA.  These are offline controls: no network, no
credential, no live model.  They prove the registered reviewer schema expresses
the existing reviewer parser contract, that exact coverage and uniqueness stay
the product's business, that the treatment difference from FG-04B is mechanical,
and that admission refuses before any network call.
"""

import json
import pathlib
import socket

import pytest

from lab import ally_generation_live as al
from lab import ally_generation_scenarios as sc
from lab import experiment_manifest as em
from lab import project_corpus_generation_pilot as pilot
from lab import project_corpus_jsonschema as js
from lab import reference_telemetry as ref
from lab import reviewer_structured_output as rso
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag

CANARY = "PRIVATE_V203_CANARY_7a41c"
STARTED = "2026-01-01T00:00:00Z"


@pytest.fixture(scope="module")
def built():
    return pilot.prepare_input(rso.ROOT)


@pytest.fixture(scope="module")
def frozen(built):
    return rso.check_registration(root=rso.ROOT)


def document(built, transport=None):
    stored, _manifest, built_now, gsb, rtb = rso.check_registration(root=rso.ROOT)
    controls = rso.dry_controls(built_now)
    schema = json.loads(gsb.decode("utf-8"))
    return rso._experiment(
        built_now, transport or rso.DryTransport(built_now.reflection_corpus),
        generator_schema=schema, generator_schema_sha256=rso._digest(gsb),
        reviewer_schema_template_sha256=rso._digest(rtb),
        allowed_refs=rso._generator_schema_refs(gsb),
        registration_id="sha256:" + "0" * 64, registration_file_sha256="0" * 64,
        dry_run=True, started=STARTED, admission=None,
        manifest_block={"file": stored["manifest"]["file"],
                        "identity": stored["manifest"]["identity"],
                        "file_sha256": "0" * 64, "authority": "LIVE_ELIGIBLE",
                        "experiment_id": rso.MANIFEST_EXPERIMENT_ID},
        controls=controls)


# ------------------------------------------------------------- REGISTRATION

def test_registration_matches_frozen_plan(frozen):
    stored, manifest = frozen[0], frozen[1]
    assert stored["routes"] == rso.ROUTES
    assert stored["budget"]["max_live_calls"] == 6
    assert stored["token_budgets"]["generator_max_tokens"] == 4096
    assert stored["token_budgets"]["reviewer_max_tokens"] == 2048
    assert stored["token_budgets"]["probe_max_tokens"] == 16
    assert stored["manifest"]["authority"] == "LIVE_ELIGIBLE"
    assert em.manifest_identity(manifest) == stored["manifest"]["identity"]
    assert stored["single_variable"]["change"] == (
        "reviewer response_format ABSENT -> JSON_SCHEMA")
    assert stored["optional_research_gate"] is True


def test_single_variable_differs_from_fg04b_only_by_reviewer_format(frozen):
    stored = frozen[0]
    comparator = stored["historical_comparator"]
    assert comparator["registration_id"] == rso.FG04B_REGISTRATION_ID
    assert comparator["reviewer_response_format"] == "ABSENT"
    assert stored["single_variable"]["generator_response_format"] == "JSON_SCHEMA"
    assert stored["generator_schema"]["unchanged_from_fg04b"] is True
    assert stored["generator_schema"]["sha256"] == rso.FG04B_GENERATOR_SCHEMA_SHA256


def test_registration_refuses_changed_bytes(tmp_path):
    path = tmp_path / "registration.json"
    real = pathlib.Path(rso.ROOT) / rso.REGISTRATION_FILE
    path.write_bytes(real.read_bytes() + b" ")
    with pytest.raises(SailangError, match="REGISTRATION_MISMATCH"):
        rso.check_registration(root=rso.ROOT, path=path)


def test_prompt_change_refused(monkeypatch):
    monkeypatch.setattr(pilot, "REVIEWER_TEMPLATE", pilot.REVIEWER_TEMPLATE + " ")
    with pytest.raises(SailangError, match="REGISTRATION_MISMATCH"):
        rso.check_registration(root=rso.ROOT)


# ------------------------------------------------------------- SCHEMA

def test_reviewer_schema_identity_and_bounds(frozen):
    stored = frozen[0]
    schema_path = pathlib.Path(rso.ROOT) / rso.REVIEWER_SCHEMA_FILE
    template = json.loads(schema_path.read_text(encoding="utf-8"))
    assert rso.canonical_bytes(template) == schema_path.read_bytes()
    assert rso._digest(schema_path.read_bytes()) == stored["json_schema"]["template_sha256"]
    assert template["additionalProperties"] is False
    assert sorted(template["required"]) == sorted(
        ["candidate_id", "corpus_id", "rubric_version", "dimensions"])
    assert template["properties"]["rubric_version"]["enum"] == [ag.RUBRIC_VERSION]
    dims = template["properties"]["dimensions"]
    assert dims["minItems"] == len(ag.DIMENSIONS)
    assert dims["maxItems"] == len(ag.DIMENSIONS)
    row = dims["items"]
    assert row["additionalProperties"] is False
    assert row["properties"]["dimension"]["enum"] == list(ag.DIMENSIONS)
    assert row["properties"]["verdict"]["enum"] == list(ag.REVIEW_VERDICTS)
    assert row["properties"]["rationale"]["maxLength"] == ag.MAX_RATIONALE_BYTES
    wrapper = rso.reviewer_response_format(template)
    assert wrapper["type"] == "json_schema"
    assert wrapper["json_schema"]["name"] == rso.REVIEWER_WRAPPER_NAME
    assert wrapper["json_schema"]["strict"] is True


def test_reviewer_schema_pins_exact_identities(built):
    corpus = built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)
    schema = rso.build_reviewer_schema(candidate_id=ag.ally_candidate_id(candidate),
                                       corpus_id=corpus.corpus_id)
    assert schema["properties"]["candidate_id"]["enum"] == [ag.ally_candidate_id(candidate)]
    assert schema["properties"]["corpus_id"]["enum"] == [corpus.corpus_id]
    assert rso.CANDIDATE_ID_PLACEHOLDER not in json.dumps(schema)


def test_schema_accepts_conforming_and_refuses_shape_drift(built):
    corpus = built.reflection_corpus
    candidate = pilot.two_event_candidate(corpus)
    schema = rso.build_reviewer_schema(candidate_id=ag.ally_candidate_id(candidate),
                                       corpus_id=corpus.corpus_id)
    good = pilot.wire_review_text(candidate, corpus)
    assert rso.schema_check(good, schema) == (rso.JSON_OK, rso.SCHEMA_VALID, None)
    # extra dimension row -> schema cardinality refuses
    doc = json.loads(good)
    doc["dimensions"].append(doc["dimensions"][0])
    assert rso.schema_check(json.dumps(doc), schema)[1] == rso.SCHEMA_INVALID
    # unknown verdict -> schema refuses
    doc = json.loads(good)
    doc["dimensions"][0]["verdict"] = "MAYBE"
    assert rso.schema_check(json.dumps(doc), schema)[1] == rso.SCHEMA_INVALID
    # wrong candidate id -> schema refuses
    doc = json.loads(good)
    doc["candidate_id"] = "sha256:" + "0" * 64
    assert rso.schema_check(json.dumps(doc), schema)[1] == rso.SCHEMA_INVALID
    # prose -> named bad JSON, schema not evaluable
    assert rso.schema_check("prose only", schema) == (
        rso.JSON_BAD_JSON, rso.SCHEMA_NOT_EVALUABLE, None)


def test_dimension_coverage_is_product_authority():
    """The schema bounds row vocabulary/size; product validation owns coverage.

    JSON Schema can require exactly eight rows, but it cannot express "exactly
    one row for each of the eight dimensions".  A duplicate dimension that
    replaces another keeps the row count at eight: the schema accepts it and the
    existing SemanticReviewReport constructor refuses it.
    """
    corpus = pilot.one_event_fixture()
    candidate = pilot.one_event_candidate(corpus)
    schema = rso.build_reviewer_schema(candidate_id=ag.ally_candidate_id(candidate),
                                       corpus_id=corpus.corpus_id)
    full = json.loads(pilot.wire_review_text(candidate, corpus))
    assert len(full["dimensions"]) == len(ag.DIMENSIONS)
    short = dict(full, dimensions=full["dimensions"][:7])
    # seven rows is a cardinality failure at the schema layer too
    assert rso.schema_check(json.dumps(short), schema)[1] == rso.SCHEMA_INVALID
    # an eight-row document with a duplicate+missing dimension passes the schema
    dup = dict(full, dimensions=full["dimensions"][:7] + [full["dimensions"][0]])
    assert len(dup["dimensions"]) == len(ag.DIMENSIONS)
    assert rso.schema_check(json.dumps(dup), schema)[1] == rso.SCHEMA_VALID
    with pytest.raises(SailangError, match="DIMENSION"):
        al.parse_reviewer_output(json.dumps(dup), candidate, corpus)


def test_generator_schema_unchanged_from_fg04b(built):
    generator_bytes = (pathlib.Path(rso.ROOT) / rso.GENERATOR_SCHEMA_FILE).read_bytes()
    assert rso._digest(generator_bytes) == rso.FG04B_GENERATOR_SCHEMA_SHA256
    corpus_refs = sorted({item.evidence_ref for item in built.reflection_corpus.items})
    assert rso._generator_schema_refs(generator_bytes) == corpus_refs
    wrapper = rso.generator_response_format(rso.ROOT, generator_bytes)
    assert wrapper["json_schema"]["name"] == rso.GENERATOR_WRAPPER_NAME
    assert js.canonical_bytes(wrapper["json_schema"]["schema"]) == generator_bytes


# ------------------------------------------------------------- DRY CONTROLS

def test_all_registered_dry_controls_pass(built):
    controls = rso.dry_controls(built)
    assert [row["control"] for row in controls] == list(rso.DRY_CONTROL_NAMES)
    assert all(row["passed"] for row in controls)


def test_dry_roles_reach_review_and_no_advice_skips(built):
    result = document(built)
    assert [r["outcome_class"] for r in result["replicates"]] == [
        rso.REVIEWER_VERDICT_PARSED, rso.NO_ADVICE_OUTCOME]
    assert result["replicates"][0]["reviewed_state_minted"] is True
    assert len(result["replicates"][0]["review_verdicts"]) == 8
    assert result["replicates"][1]["reviewer_calls"] == 0
    assert result["replicates"][0]["event_floor_relation"] == ref.MET


def test_reviewer_carries_schema_and_generator_keeps_its_schema(built):
    result = document(built)
    gens = [c for c in result["calls"] if c["function"] == "GENERATOR"]
    revs = [c for c in result["calls"] if c["function"] == "REVIEWER"]
    probes = [c for c in result["calls"] if c["function"] == "PROBE"]
    assert all(c["request_max_tokens"] == 4096 for c in gens)
    assert all(c["request_max_tokens"] == 2048 for c in revs)
    assert all(c["request_max_tokens"] == 16 for c in probes)
    assert all(c["response_format_kind"] == rso.KIND_JSON_SCHEMA for c in gens + revs + probes)
    # the reviewer schema hash differs from the generator schema hash: two wrappers
    assert all(c["response_format_sha256"] == result["generator_schema"]["sha256"]
               for c in gens + probes)
    assert all(c["response_format_sha256"] != result["generator_schema"]["sha256"]
               for c in revs)
    assert len(result["probes"]) == 2
    assert all(row["schema_result"] == rso.SCHEMA_VALID for row in result["probes"])
    assert all(row["provider_enforces_json_schema"] == rso.ENFORCEMENT_NOT_PROVEN
               for row in result["probes"])


def test_request_body_evidence_is_recorded(built):
    result = document(built)
    reviewer = [c for c in result["calls"] if c["function"] == "REVIEWER"][0]
    assert reviewer["response_format_kind"] == rso.KIND_JSON_SCHEMA
    assert reviewer["response_format_sha256"] is not None
    assert reviewer["request_body_sha256"] is not None
    assert reviewer["request_body_bytes"] > 0


def test_no_hidden_retry_and_exact_call_accounting(built):
    result = document(built)
    assert result["budget"]["spent_total"] == 5
    assert result["budget"]["logical_dispatches"] == result["budget"]["spent_total"]
    assert result["budget"]["network_calls"] == 0
    assert result["budget"]["retries"] == 0
    assert result["budget"]["repair_calls"] == 0
    assert result["budget"]["replacements"] == 0
    assert result["budget"]["fallbacks"] == 0
    assert all(c["wrapper_retry"] is False for c in result["calls"])


# -------------------------------------------------- OUTCOME CLASS MATRIX

def _metadata(**overrides):
    record = {"status": "OK", "parser_status": sc.STAGE_OK, "parser_error_code": None,
              "schema_status": rso.SCHEMA_VALID, "http_status": None}
    record.update(overrides)
    return record


def _gen(metadata):
    return type("G", (), {"record": {"metadata": metadata}, "calls": 1})()


def _rev(metadata, calls=1):
    return type("R", (), {"record": ({"metadata": metadata} if metadata else None),
                          "calls": calls})()


def test_terminal_outcome_matrix_is_total():
    cases = [
        (rso.AUTH_REFUSED, _gen(_metadata()), _rev(_metadata(http_status=401)),
         type("O", (), {"status": ag.ERROR, "code": ag.ALLY_GEN_REVIEWER_ERROR})(),
         "AUTH_REFUSED: HTTP 401"),
        (rso.REVIEWER_NOT_REACHED, _gen(_metadata(status="ERROR")), _rev(None, 0),
         type("O", (), {"status": ag.ERROR, "code": ag.ALLY_GEN_PROVIDER_ERROR})(), None),
        (rso.NO_ADVICE_OUTCOME, _gen(_metadata()), _rev(None, 0),
         type("O", (), {"status": ag.NO_ADVICE, "code": None})(), None),
        (rso.REVIEWER_NOT_REACHED, _gen(_metadata()), _rev(None, 0),
         type("O", (), {"status": ag.REJECTED,
                        "code": ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS})(), None),
        (rso.RESPONSE_FORMAT_REJECTED, _gen(_metadata()),
         _rev(_metadata(status="ERROR", http_status=400, parser_status="NOT_ATTEMPTED")),
         type("O", (), {"status": ag.ERROR, "code": ag.ALLY_GEN_REVIEWER_ERROR})(), None),
        (rso.REVIEWER_TRANSPORT_ERROR, _gen(_metadata()),
         _rev(_metadata(status="ERROR", http_status=None, parser_status="NOT_ATTEMPTED")),
         type("O", (), {"status": ag.ERROR, "code": ag.ALLY_GEN_REVIEWER_ERROR})(), None),
        (rso.REVIEWER_BAD_JSON, _gen(_metadata()),
         _rev(_metadata(parser_status="SCHEMA_ERROR", parser_error_code="ALLY_LAB_BAD_JSON")),
         type("O", (), {"status": ag.ERROR, "code": ag.ALLY_GEN_REVIEWER_ERROR})(), None),
        (rso.REVIEWER_SCHEMA_ACCEPTED_BUT_PRODUCT_REJECTED, _gen(_metadata()),
         _rev(_metadata()),
         type("O", (), {"status": ag.REJECTED,
                        "code": ag.ALLY_GEN_REVIEW_REF_OUTSIDE_CORPUS})(), None),
        (rso.REVIEWER_VERDICT_PARSED, _gen(_metadata()), _rev(_metadata()),
         type("O", (), {"status": ag.APPROVED, "code": None})(), None),
    ]
    produced = set()
    for expected, generator, reviewer, outcome, stopped in cases:
        got = rso.classify_terminal(generator, reviewer, outcome, stopped=stopped)
        assert got == expected, (expected, got)
        produced.add(got)
    assert produced <= rso.OUTCOME_CLASSES
    assert rso.INPUT_DRIFT in rso.OUTCOME_CLASSES


# ------------------------------------------------------------- ADMISSION

def test_historical_manifest_is_not_live_authority():
    t71 = em.load(pathlib.Path(rso.ROOT) / "lab/history/t71_manifest.json")
    assert t71["authority"] == "HISTORICAL_ONLY"
    with pytest.raises(SailangError, match="HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY"):
        em.admit_live(t71, root=rso.ROOT)


def test_live_manifest_admits_and_drift_refuses(frozen):
    manifest = frozen[1]
    built = frozen[2]
    gsb = (pathlib.Path(rso.ROOT) / rso.GENERATOR_SCHEMA_FILE).read_bytes()
    rtb = (pathlib.Path(rso.ROOT) / rso.REVIEWER_SCHEMA_FILE).read_bytes()
    evidence = rso.pre_live_admission(root=rso.ROOT, doc=frozen[0], built=built,
                                      generator_schema_bytes=gsb,
                                      reviewer_template_bytes=rtb, manifest=manifest)
    assert evidence["admit_live"] is True
    assert evidence["network_calls"] == 0
    assert all(evidence["checks"].values())
    drifted = json.loads(json.dumps(manifest))
    drifted["authority"] = "HISTORICAL_ONLY"
    with pytest.raises(SailangError, match="HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY"):
        em.admit_live(drifted, root=rso.ROOT)


def test_fg04b_reconstructability_is_checked(frozen):
    assert rso._fg04b_reconstructable(rso.ROOT) is True


# ------------------------------------------------------------- PRIVACY

def test_candidate_prose_and_canary_are_not_durable(built, tmp_path):
    corpus = built.reflection_corpus
    base = pilot.two_event_candidate(corpus)
    candidate = aa.AllyAdvice(
        created=base.created, work_context=base.work_context,
        observed_scope=base.observed_scope, observed=base.observed,
        inferred=CANARY, guidance_mode=base.guidance_mode, suggested=base.suggested,
        counterevidence=base.counterevidence, uncertainty=base.uncertainty)
    result = document(built, rso.DryTransport(corpus, candidate=candidate))
    serialized = json.dumps(result, ensure_ascii=False)
    assert CANARY not in serialized
    assert pilot.wire_candidate_text(candidate) not in serialized
    for item in corpus.items:
        assert item.content not in serialized


# ------------------------------------------------------------- RUN LIFECYCLE

def test_dry_run_never_touches_network_or_credentials(tmp_path, monkeypatch, built):
    def forbidden(*args, **kwargs):
        pytest.fail("dry run attempted network or credential resolution")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(rso, "resolve", forbidden)
    monkeypatch.setattr(rso, "SchemaTransport", forbidden)
    real_write = rso._write
    monkeypatch.setattr(rso, "_write", lambda root, doc, doc_, key: real_write(
        tmp_path, doc, doc_, key))
    result = rso.run(dry_run=True, root=rso.ROOT)
    assert result["budget"]["network_calls"] == 0
    assert result["outcome_classes"] == [rso.REVIEWER_VERDICT_PARSED, rso.NO_ADVICE_OUTCOME]


def test_live_requires_dry_control_and_marker(tmp_path, monkeypatch):
    monkeypatch.setattr(rso, "resolve", lambda: pytest.fail("credential touched too early"))
    with pytest.raises(SailangError, match="REGISTRATION_MISSING"):
        rso.run(root=tmp_path)


def test_reserve_is_publish_once(tmp_path):
    path = tmp_path / "attempt.json"
    rso._reserve(path, "sha256:" + "0" * 64)
    with pytest.raises(SailangError, match="ALREADY_ATTEMPTED"):
        rso._reserve(path, "sha256:" + "0" * 64)
