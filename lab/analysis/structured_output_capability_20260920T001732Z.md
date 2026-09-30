# Structured-output capability gate -- analysis

Registration `sha256:e696db4c786ea60b9764b50e924fd93ed505efdf1b8b366529600ac100c4ffdf`; artifact started 2026-09-20T00:17:32Z.

## Measured request acceptance
- 4096 completion request: A `REQUEST_ACCEPTED_CONFORMING`, B `REQUEST_ACCEPTED_CONFORMING`.
- json_object: A `REQUEST_ACCEPTED_CONFORMING`, B `REQUEST_ACCEPTED_CONFORMING`.
- json_schema: A `REQUEST_ACCEPTED_CONFORMING`, B `REQUEST_ACCEPTED_CONFORMING`.

## Context comparability (descriptive only)
- Local synthetic prompt: 7734 tokens, 24829 bytes, SHA256 `0559b6e5583de1ef45559a469fdae6ee407d478ef2aecfd8b5a35f1653d9f4fc`.
- Gateway prompt tokens: {'A': 11515, 'B': 10722}; T-71 route history: {'A': 12065, 'B': 10973}; ratios: {'A': 0.95, 'B': 0.98}; bands: {'A': 'CONTEXT_SHAPE_COMPARABLE', 'B': 'CONTEXT_SHAPE_COMPARABLE'}.

## Bounded claims
- Request acceptance and output conformance are reported separately; native enforcement proven: False.
- Local parser-input cap remains 4000 characters; a real 4096 run through the unchanged local path is safe: False -- local next-gate requirement, not a remote capability statement.
- No retry, repair, replacement or fallback exists in this harness.
