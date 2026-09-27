# Strict-schema observer resource bound v0

This LAB correction makes the structural observer's JSON nesting limit explicit
and deterministic on every supported Python runtime. It corrects the
observation layer added by T-71 (`spec/11-STRICT-SCHEMA-OBSERVABILITY-v0.md`);
it does not change that contract, the strict parser it observes, or any
acceptance semantics. The defect measured on Python 3.13.5: `json.loads`
accepted an 1100-level array, so `safe_observe` returned `syntax = OK` where
the repository test expected `RESOURCE_LIMIT`. The bound depended on the
runtime's recursion behavior, not on a declared policy.

Applied rule:

```
MAX_OBSERVER_JSON_NESTING = 64
RESOURCE_LIMIT_IS_EXPLICIT = true
RESOURCE_LIMIT_DEPENDS_ON_RECURSIONERROR = false
OBSERVER_ONLY = true
STRICT_PARSER_SEMANTICS_CHANGED = false
HISTORICAL_T71_ARTIFACT_CHANGED = false
```

## Scope and authority

The bound applies only to LAB structural observation in `lab/parse_shape.py`.
It is not an ALLY1 schema rule, not a B-016 acceptance rule, not a SAILANG
rule, and not a provider capability claim. `lab/ally_generation_live.py`
remains the strict parser authority: `parse_generator_output`,
`parse_reviewer_output` and `_strict_object` are untouched, no fence stripping,
substring extraction or repair is added, and unknown-field behavior is
unchanged. Its bytes and the `spec/11` bytes stay pinned by the frozen T-71
registration; this document is additive and no historical artifact, report,
interpretation or telemetry record is rewritten.

## Lexical preflight

Before the observer calls `json.loads`, one O(n) lexical scan runs over the
already bounded (`len(raw) <= 4000`) parser-input string:

- `"` outside a string enters string state;
- `"` inside a string leaves it only when not escaped, and `\` escapes exactly
  the next character, so `\"` and `\\` preserve string state;
- `{` and `[` outside a string increase depth by one;
- `}` and `]` are structural closes with no semantic validation, and depth
  never goes below zero;
- as soon as depth would exceed 64 the scan reports exceeded.

An exceeded scan returns `syntax = RESOURCE_LIMIT` without invoking
`json.loads`. Depth exactly 64 does not mean valid: the ordinary JSON parser
still decides `OK` or `INVALID`. The scanner is a resource guard, never syntax
authority: brackets and braces inside strings never consume nesting budget, a
malformed shallow document stays parser-classified `INVALID`, and malformed
escapes remain the JSON parser's job.

The existing character bound (`len(raw) > 4000` -> `RESOURCE_LIMIT`) is
preserved and unchanged; the nesting bound is additive. The defensive
`except (RecursionError, ValueError)` handler remains only as a final safety
net; normative behavior and tests no longer depend on an exception being raised
at any particular depth. `sys.setrecursionlimit` is not used: the observer
never mutates process-global interpreter policy.

## Observable contract

The durable field schema is unchanged: `PARSE-SHAPE-1` remains the metadata
schema version, and every telemetry field keeps its meaning. The preflight
returns only exceeded / not exceeded internally and persists no substring,
prefix, suffix, string content or character around the depth boundary; the
existing structural telemetry privacy rules apply unchanged. Observer shape
still cannot grant review or approval, and an observer failure still records
`OBSERVER_ERROR` without changing the parser invocation or its result.

The runtime-independence control wraps `json.loads` in the observer's own
namespace and fails the test if it is called for input above the explicit
bound, so the contract is proven without requiring multiple Python binaries.
Red control on the exact defect bytes: `safe_observe("[" * 1100 + "]" * 1100)`
is `RESOURCE_LIMIT` after the correction on every runtime, including Python
3.13, without relying on `RecursionError`.

## Registration and closure

This correction is bound to T-72 and its captured receipts SRC-054, SRC-055
(T-71 lineage), SRC-056 and SRC-057. Validation compares exact validator
failure lines against the SCOUT baseline; `DEBT-000066` remains visible as
`CURRENT_FAIL / CARRIED_DEBT_UNCHANGED` when unchanged, and no debt repair,
receipt rewriting, T-65/T-34 work, commit, tag, push or publication is part of
this correction. No live model, provider or network call occurs.
