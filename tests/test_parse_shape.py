"""Structural observations never normalize, disclose or grant acceptance."""

import json

import pytest

from lab import ally_generation_live as strict
from lab import parse_shape as shape
from sailang.errors import SailangError

CANARY = "PRIVATE_SHAPE_CANARY_7f39e"


@pytest.mark.parametrize("raw,syntax,root,error", [
    ('{"result":"NO_ADVICE"}', "OK", "OBJECT", None),
    ('```json\n{"result":"NO_ADVICE"}\n```', "INVALID", None, "INVALID_JSON"),
    ('prefix {"result":"NO_ADVICE"}', "INVALID", None, "INVALID_JSON"),
    ('{"result":"NO_ADVICE"} prose', "INVALID", None, "EXTRA_DATA"),
    ('{"result":"NO_ADVICE"} {}', "INVALID", None, "EXTRA_DATA"),
    ('{"result":', "INVALID", None, "INVALID_JSON"),
    ('[]', "OK", "ARRAY", None),
    ('null', "OK", "NULL", None),
    ('42', "OK", "NUMBER", None),
    ('true', "OK", "BOOLEAN", None),
    ('"secret string"', "OK", "STRING", None),
    ('', "INVALID", None, "INVALID_JSON"),
    (' \n ', "INVALID", None, "INVALID_JSON"),
])
def test_full_document_shape(raw, syntax, root, error):
    result = shape.safe_observe(raw, "GENERATOR")
    shape.validate(result, shape.SHAPE_SCHEMA)
    assert result["syntax"] == syntax
    assert result["root_type"] == root
    assert result["syntax_error"] == error
    if error:
        assert type(result["error_position"]) is int


@pytest.mark.parametrize("raw", [
    '```json\n{"result":"NO_ADVICE"}\n```',
    'prose {"result":"NO_ADVICE"}',
    '{"result":"NO_ADVICE"} trailing',
    '{"result":"NO_ADVICE"} {}',
    '{"result":"NO_ADVICE","result":"NO_ADVICE"}',
    '{"result":"NO_ADVICE","unknown":1}', '{}', '[]', 'null',
    '{"result":"CANDIDATE","WORK_CONTEXT":',
])
def test_telemetry_cannot_make_rejection_pass(raw):
    with pytest.raises(SailangError) as before:
        strict.parse_generator_output(raw)
    shape.safe_observe(raw, "GENERATOR")
    with pytest.raises(SailangError) as after:
        strict.parse_generator_output(raw)
    assert before.value.code == after.value.code


def test_duplicate_keys_at_every_depth_and_unknown_names_are_counts_only():
    raw = '{"result":"CANDIDATE","OBSERVED":[{"' + CANARY + '":1,"' + CANARY + '":2}]}'
    result = shape.safe_observe(raw, "GENERATOR")
    assert result["duplicate_key_count"] == 1
    assert result["nested_unknown_count"] == 1
    assert result["nested_missing_count"] == 2
    assert result["top_missing_count"] == 7
    assert CANARY not in json.dumps(result)


def test_wrong_field_types_and_nested_types():
    result = shape.safe_observe(json.dumps({"result": "CANDIDATE", "WORK_CONTEXT": [],
        "OBSERVED": [None, {"STATEMENT": 1, "EVIDENCE_REFS": [2]}]}), "GENERATOR")
    assert result["top_type_mismatch_count"] == 1
    assert result["nested_type_mismatch_count"] == 3


def test_reviewer_shape_discards_rationale_values_and_unknown_names():
    result = shape.safe_observe(json.dumps({"candidate_id": CANARY, "corpus_id": CANARY,
        "rubric_version": CANARY, "dimensions": [{"dimension": CANARY,
            "verdict": CANARY, "rationale": CANARY, "evidence_refs": [], CANARY: CANARY}]}), "REVIEWER")
    assert result["top_missing_count"] == 0
    assert result["nested_unknown_count"] == 1
    assert CANARY not in json.dumps(result)


def test_resource_limit_and_non_text_are_bounded():
    assert shape.safe_observe("x" * 4001, "GENERATOR")["syntax"] == "RESOURCE_LIMIT"
    assert shape.safe_observe("[" * 1100 + "]" * 1100, "GENERATOR")["syntax"] == "RESOURCE_LIMIT"
    assert shape.safe_observe(None, "GENERATOR")["input_kind"] == "ABSENT"
    assert shape.safe_observe({CANARY: CANARY}, "GENERATOR")["input_kind"] == "NON_TEXT"


def test_explicit_nesting_bound_boundary():
    assert shape.MAX_OBSERVER_JSON_NESTING == 64
    assert shape.safe_observe("[" * 65 + "]" * 65, "GENERATOR")["syntax"] == "RESOURCE_LIMIT"
    assert shape.safe_observe("[" * 64 + "]" * 64, "GENERATOR")["syntax"] == "OK"


def test_nonfinite_is_observation_only():
    result = shape.safe_observe('{"result":"NO_ADVICE","x":NaN}', "GENERATOR")
    assert result["nonfinite_constant_count"] == 1
    assert result["top_unknown_count"] == 1


def test_observer_fault_keeps_no_exception_body(monkeypatch):
    def boom(*args):
        raise RuntimeError(CANARY)
    monkeypatch.setattr(shape, "observe", boom)
    result = shape.safe_observe(CANARY, "GENERATOR")
    assert result["syntax"] == "OBSERVER_ERROR"
    assert CANARY not in json.dumps(result)


@pytest.mark.parametrize("path", ["extra", "syntax", "duplicate_key_count", "error_position"])
def test_telemetry_schema_rejects_prose_even_under_metadata_keys(path):
    result = shape.safe_observe('{"result":"NO_ADVICE"}', "GENERATOR")
    result[path] = CANARY
    with pytest.raises(SailangError, match=shape.PRIVACY_TRIPWIRE) as caught:
        shape.validate(result, shape.SHAPE_SCHEMA)
    assert CANARY not in str(caught.value)
