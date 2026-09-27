"""The observer nesting bound is explicit, lexical and runtime-independent."""

import hashlib
import json
import pathlib
from types import SimpleNamespace

import pytest

from lab import ally_generation_live as strict
from lab import parse_shape as shape
from sailang.errors import SailangError

CANARY = "PRIVATE_NESTING_CANARY_4c81b"
ROOT = pathlib.Path(__file__).resolve().parents[1]


def _array(depth):
    return "[" * depth + "]" * depth


def _object(depth):
    return '{"a":' * depth + "1" + "}" * depth


def _mixed(depth):
    objects = (depth + 1) // 2
    arrays = depth // 2
    return '{"a":' * objects + "[" * arrays + "1" + "]" * arrays + "}" * objects


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _without_json_loads(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("json.loads ran above the explicit observer nesting bound")
    monkeypatch.setattr(shape, "json", SimpleNamespace(loads=boom))


def test_explicit_bound_and_schema_version_are_frozen():
    assert shape.MAX_OBSERVER_JSON_NESTING == 64
    assert shape.VERSION == "PARSE-SHAPE-1"


def test_character_limit_is_unchanged():
    assert shape.safe_observe("x" * 4001, "GENERATOR")["syntax"] == "RESOURCE_LIMIT"
    assert shape.safe_observe("x" * 3999, "GENERATOR")["syntax"] == "INVALID"


@pytest.mark.parametrize("raw", [
    _array(65),
    _object(65),
    _mixed(65),
    _array(1100),
    _array(2000),
])
def test_over_bound_is_resource_limited_without_json_loads(raw, monkeypatch):
    _without_json_loads(monkeypatch)
    result = shape.safe_observe(raw, "GENERATOR")
    shape.validate(result, shape.SHAPE_SCHEMA)
    assert result["syntax"] == "RESOURCE_LIMIT"


def test_at_the_bound_still_reaches_the_ordinary_parser():
    result = shape.safe_observe(_array(64), "GENERATOR")
    assert result["syntax"] == "OK"
    assert result["root_type"] == "ARRAY"
    result = shape.safe_observe(_object(64), "GENERATOR")
    assert result["syntax"] == "OK"
    assert result["root_type"] == "OBJECT"


def test_malformed_at_or_below_the_bound_stays_parser_classified():
    assert shape.safe_observe('{"a":' * 63 + "1", "GENERATOR")["syntax"] == "INVALID"
    result = shape.safe_observe(_array(64) + "{}", "GENERATOR")
    assert result["syntax"] == "INVALID"
    assert result["syntax_error"] == "EXTRA_DATA"


def test_string_brackets_do_not_consume_nesting_budget():
    assert shape.safe_observe('{"x":"' + "[" * 3000 + '"}', "GENERATOR")["syntax"] == "OK"
    assert shape.safe_observe('{"x":"' + "}" * 3000 + '"}', "GENERATOR")["syntax"] == "OK"


def test_escaped_quote_and_backslash_keep_string_state():
    raw = '{"x":"' + '\\"' * 500 + "[" * 500 + '"}'
    assert shape.safe_observe(raw, "GENERATOR")["syntax"] == "OK"
    raw = '{"x":"' + "\\\\" * 500 + '"}'
    assert shape.safe_observe(raw, "GENERATOR")["syntax"] == "OK"


def test_malformed_shallow_string_is_not_promoted():
    assert shape.safe_observe('{"x":"' + "[" * 100, "GENERATOR")["syntax"] == "INVALID"
    assert shape.safe_observe('{"x":"unclosed', "GENERATOR")["syntax"] == "INVALID"


def test_nesting_preflight_returns_no_text():
    result = shape.safe_observe("[" * 65 + CANARY + "]" * 65, "GENERATOR")
    assert result["syntax"] == "RESOURCE_LIMIT"
    assert CANARY not in json.dumps(result)


def test_strict_parser_authority_pin_is_unchanged():
    registration = json.loads(
        (ROOT / "lab" / "project_corpus_reachability_registration.json")
        .read_text(encoding="utf-8"))
    contract = registration["contract"]
    assert _digest(ROOT / contract["path"]) == contract["sha256"]
    pins = {row["path"]: row["sha256"] for row in registration["protected_files"]}
    assert _digest(ROOT / "lab" / "ally_generation_live.py") == pins["lab/ally_generation_live.py"]


def test_observer_cannot_change_the_strict_parser_refusal():
    raw = _array(65)
    with pytest.raises(SailangError) as before:
        strict.parse_generator_output(raw)
    shape.safe_observe(raw, "GENERATOR")
    with pytest.raises(SailangError) as after:
        strict.parse_generator_output(raw)
    assert before.value.code == after.value.code
