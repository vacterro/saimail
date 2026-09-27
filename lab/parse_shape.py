"""LAB-only structural observation. Never returns text or an acceptance decision."""

from __future__ import annotations

import hashlib
import json
import math
import re

from sailang.errors import SailangError

PRIVACY_TRIPWIRE = "REACHABILITY_PRIVACY_TRIPWIRE"
VERSION = "PARSE-SHAPE-1"
MAX_OBSERVER_JSON_NESTING = 64
TYPES = frozenset({"OBJECT", "ARRAY", "STRING", "NUMBER", "BOOLEAN", "NULL"})
HASH = ("regex", r"[0-9a-f]{64}")
IDENTITY = ("regex", r"sha256:[0-9a-f]{64}")


def nullable(schema):
    return ("nullable", schema)


def validate(value, schema) -> None:
    """Closed recursive persistence gate; rejection never echoes the rejected value."""
    valid = False
    if isinstance(schema, dict):
        valid = type(value) is dict and value.keys() == schema.keys()
        if valid:
            for key, child in schema.items():
                validate(value[key], child)
    elif isinstance(schema, frozenset):
        valid = any(type(value) is type(option) and value == option for option in schema)
    elif isinstance(schema, tuple):
        if schema[0] == "nullable":
            if value is None:
                return
            validate(value, schema[1])
            return
        if schema[0] == "regex":
            valid = type(value) is str and re.fullmatch(schema[1], value) is not None
        elif schema[0] == "list":
            valid = type(value) is list and len(value) <= schema[2]
            if valid:
                for item in value:
                    validate(item, schema[1])
    elif schema is int:
        valid = type(value) is int and 0 <= value <= 2**63 - 1
    elif schema is float:
        valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
    elif schema is bool:
        valid = type(value) is bool
    if not valid:
        raise SailangError(PRIVACY_TRIPWIRE, "closed metadata schema refused persistence")


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="surrogatepass")).hexdigest()


def text_metadata(value) -> dict:
    is_text = type(value) is str
    return {"sha256": digest(value) if is_text else None,
            "bytes": len(value.encode("utf-8", errors="surrogatepass")) if is_text else None}


TEXT_METADATA_SCHEMA = {"sha256": nullable(HASH), "bytes": nullable(int)}
SHAPE_SCHEMA = {
    "version": frozenset({VERSION}),
    "input_kind": frozenset({"TEXT", "ABSENT", "NON_TEXT"}),
    "blank": bool,
    "fence_token_present": bool,
    "first_token": frozenset({"OBJECT", "ARRAY", "STRING", "NUMBER", "LITERAL",
                               "OTHER", "EMPTY"}),
    "syntax": frozenset({"OK", "INVALID", "NOT_ATTEMPTED", "RESOURCE_LIMIT",
                          "OBSERVER_ERROR"}),
    "root_type": nullable(TYPES),
    "duplicate_key_count": int,
    "nonfinite_constant_count": int,
    "syntax_error": nullable(frozenset({"EXTRA_DATA", "INVALID_JSON"})),
    "error_position": nullable(int),
    "error_line": nullable(int),
    "error_column": nullable(int),
    "result_kind": frozenset({"CANDIDATE", "NO_ADVICE", "OTHER", "ABSENT"}),
    "top_missing_count": nullable(int),
    "top_unknown_count": nullable(int),
    "top_type_mismatch_count": nullable(int),
    "nested_item_count": nullable(int),
    "nested_missing_count": nullable(int),
    "nested_unknown_count": nullable(int),
    "nested_type_mismatch_count": nullable(int),
}
GENERATOR_FIELDS = {
    "result": str, "WORK_CONTEXT": str, "OBSERVED_SCOPE": str, "OBSERVED": list,
    "INFERRED": str, "GUIDANCE_MODE": str, "SUGGESTED": str,
    "COUNTEREVIDENCE": list, "UNCERTAINTY": str,
}
REVIEW_FIELDS = {"candidate_id": str, "corpus_id": str,
                 "rubric_version": str, "dimensions": list}
ITEM_FIELDS = {"STATEMENT": str, "EVIDENCE_REFS": list}
DIMENSION_FIELDS = {"dimension": str, "verdict": str,
                    "rationale": str, "evidence_refs": list}


def _type(value):
    return {dict: "OBJECT", list: "ARRAY", str: "STRING", int: "NUMBER",
            float: "NUMBER", bool: "BOOLEAN", type(None): "NULL"}[type(value)]


def _counts(value, fields):
    return (len(fields.keys() - value.keys()), len(value.keys() - fields.keys()),
            sum(type(value[key]) is not kind for key, kind in fields.items() if key in value))


def _empty_shape(raw):
    return {
        "version": VERSION,
        "input_kind": "TEXT" if type(raw) is str else "ABSENT" if raw is None else "NON_TEXT",
        "blank": False, "fence_token_present": False, "first_token": "EMPTY",
        "syntax": "NOT_ATTEMPTED", "root_type": None,
        "duplicate_key_count": 0, "nonfinite_constant_count": 0,
        "syntax_error": None, "error_position": None, "error_line": None,
        "error_column": None, "result_kind": "ABSENT",
        **{key: None for key in SHAPE_SCHEMA if key.startswith(("top_", "nested_"))},
    }


def _nesting_exceeded(raw: str) -> bool:
    """Lexical resource preflight: reports only whether the explicit bound is crossed."""
    depth = 0
    in_string = False
    escaped = False
    for char in raw:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "{[":
            depth += 1
            if depth > MAX_OBSERVER_JSON_NESTING:
                return True
        elif char in "}]" and depth > 0:
            depth -= 1
    return False


def observe(raw, function: str) -> dict:
    """Inspect one complete parser input; no content fragment can be returned."""
    result = _empty_shape(raw)
    if type(raw) is not str:
        return result
    result["blank"] = not raw.strip()
    result["fence_token_present"] = "```" in raw or "~~~" in raw
    stripped = raw.lstrip()
    first = stripped[:1]
    result["first_token"] = (
        "EMPTY" if not first else "OBJECT" if first == "{" else "ARRAY" if first == "["
        else "STRING" if first == '"' else "NUMBER" if first in "-0123456789"
        else "LITERAL" if first in "tfnNI" else "OTHER")
    if len(raw) > 4000:
        result["syntax"] = "RESOURCE_LIMIT"
        return result
    if _nesting_exceeded(raw):
        result["syntax"] = "RESOURCE_LIMIT"
        return result

    def pairs(items):
        obj = {}
        for key, value in items:
            result["duplicate_key_count"] += int(key in obj)
            obj[key] = value
        return obj

    def constant(_value):
        result["nonfinite_constant_count"] += 1

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except json.JSONDecodeError as exc:
        result.update(syntax="INVALID", syntax_error=(
            "EXTRA_DATA" if exc.msg == "Extra data" else "INVALID_JSON"),
            error_position=exc.pos, error_line=exc.lineno, error_column=exc.colno)
        return result
    except (RecursionError, ValueError):
        result["syntax"] = "RESOURCE_LIMIT"
        return result
    result.update(syntax="OK", root_type=_type(value))
    if type(value) is not dict:
        return result
    discriminator = value.get("result")
    result["result_kind"] = (discriminator if type(discriminator) is str and discriminator
                             in {"CANDIDATE", "NO_ADVICE"} else
                             "OTHER" if "result" in value else "ABSENT")
    fields = (REVIEW_FIELDS if function == "REVIEWER" else
              {"result": str} if result["result_kind"] == "NO_ADVICE" else GENERATOR_FIELDS)
    counts = _counts(value, fields)
    for suffix, count in zip(("missing", "unknown", "type_mismatch"), counts):
        result[f"top_{suffix}_count"] = count
    nested = ([("dimensions", DIMENSION_FIELDS, "evidence_refs")] if function == "REVIEWER"
              else [(key, ITEM_FIELDS, "EVIDENCE_REFS") for key in ("OBSERVED", "COUNTEREVIDENCE")])
    totals = [0, 0, 0]
    count = 0
    for key, item_fields, refs_key in nested:
        rows = value.get(key)
        if type(rows) is not list:
            continue
        count += len(rows)
        for row in rows:
            if type(row) is not dict:
                totals[2] += 1
                continue
            totals = [a + b for a, b in zip(totals, _counts(row, item_fields))]
            refs = row.get(refs_key)
            if type(refs) is list:
                totals[2] += sum(type(ref) is not str for ref in refs)
    result["nested_item_count"] = count
    for suffix, count in zip(("missing", "unknown", "type_mismatch"), totals):
        result[f"nested_{suffix}_count"] = count
    return result


def safe_observe(raw, function: str) -> dict:
    """Observer failure cannot change parser authority or disclose exception text."""
    try:
        result = observe(raw, function)
        validate(result, SHAPE_SCHEMA)
        return result
    except Exception:  # noqa: BLE001 - observation failure must not change acceptance
        result = _empty_shape(raw)
        result["syntax"] = "OBSERVER_ERROR"
        return result
