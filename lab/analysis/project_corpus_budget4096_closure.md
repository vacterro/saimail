# T-74 ephemeral full-output + 4096 budget-only closure

All three sequential targets are complete. The one registered live experiment
used the unchanged B-018 corpus and the same requested routes as T-71. Exactly
one experimental variable changed: the generator's remote completion budget,
2048 -> 4096. Reviewer stayed 2048 and `response_format` stayed absent. The
local 4000-character parser-input projection was replaced, for the immediate
experiment parser only, by a LAB-only ephemeral full-visible-output path. The
generic transport keeps its historical 4000-character behaviour byte for byte.

## Result, bounded interpretation

R1 requested SAIFREN and reported deepseek/deepseek-v4-flash. Under 4096 it
finished with `finish_reason=stop` (T-71 had `length` at 2048) and produced a
strict-JSON-valid CANDIDATE of 3280 UTF-8 bytes. The unchanged B-016 corpus-ref
gate then REJECTED it because at least one cited evidence ref is outside the
corpus; the semantic reviewer was not invoked. R2 requested
goat/MiniMaxAI/MiniMax-M3 and reported MiniMaxAI/MiniMax-M3; it returned a
22-byte NO_ADVICE and spent zero reviewer calls.

This is evidence that the increased completion budget is consistent with
removing the T-71 length/parse blockage for this invocation. It is NOT a claim
that 4096 universally fixes the model, and R1's corpus-ref rejection is a
separate, newly-observed formatting/grounding failure mode, not the budget.
Semantic-review reachability was NOT demonstrated: neither replicate reached the
B-016 reviewer. This maps to the handoff's CASE C: `4096 -> stop` but the strict
schema still did not yield an accepted candidate (it parsed, but was rejected at
the ref gate before review).

## Fourteen required answers

1. Was the B-018 subject reproduced? YES: registration_id,
   build_id `sha256:0e0546...`, corpus_id `sha256:b009bd...`, artifact_count 8,
   event_count 5 all matched the frozen values before any content call.
2. Were T-71 prompt templates unchanged? YES: generator
   `f2eb95c2...`, reviewer `6c64136d...` equal the T-71 pins.
3. Did generator requests use 4096? YES, both.
4. Did reviewer requests remain 2048? YES (no reviewer call was reached; the
   declared and mechanically-proven budget is 2048).
5. Was response_format absent? YES, on every content call
   (`response_format_kind = NONE`).
6. Did either output exceed the historical 4000-character projection? NO: R1
   3280 bytes, R2 22 bytes; both `legacy_projection_would_truncate = false`.
7. Did the parser receive complete visible output? YES: the ephemeral path
   delivered the complete visible content; no parser-input truncation occurred
   (`output_truncated = false`).
8. Did R1 still end with finish_reason=length? NO: `stop`.
9. Did R1 produce valid strict JSON? YES: parser OK, shape syntax OK.
10. Did R1 reach an AllyAdvice candidate? YES: a candidate was parsed and
    emitted, then rejected by the corpus-ref gate.
11. Did either replicate reach semantic review? NO.
12. Did any replicate return NO_ADVICE? YES: R2.
13. Were retry/repair/fallback counts zero? YES: retries 0, repair_calls 0, no
    replacement, no fallback.
14. Was durable plaintext leakage zero? YES: zero corpus-content or prompt
    plaintext in the artifact; the full output is represented by SHA256 and byte
    length only.

## Reproducibility and privacy evidence

- Contract: `spec/11-STRICT-SCHEMA-OBSERVABILITY-v0.md` (unchanged).
- Registration: `lab/project_corpus_budget4096_registration.json`, SHA256
  `ac6a940220d65916355dc648f4c1dbc4cb24331254cb793cc1c2ec1a6c383190`.
- Ephemeral transport: `lab/ephemeral_output.py`, SHA256
  `03212cf0799f3e7822c2098105c39d94ad4d79ae833e8e5b2334f30de52a61de`.
- Harness: `lab/project_corpus_budget4096.py`, SHA256
  `d96e185b98011d4988e38520d35adb5ff850fa9b247f17b71c4c7d4706a94bb7`.
- Live artifact:
  `lab/out/project_corpus_budget4096_live_20260920T005752Z.json`, SHA256
  `0af0735ade363c9e2fc96d84de1a5768263031053c52b15b805bbd4d2bd61474`.
- Machine report:
  `lab/out/PROJECT_CORPUS_BUDGET4096_REPORT_20260920T005752Z.md`, SHA256
  `bdbb9158d3073ea7df809c755195d1cf467adeeee0fdaf86c33ddde92a290982`.
- Single-attempt marker: `.saipen/evidence/T-74-budget4096-live-attempt.json`.

The ephemeral/full path was proven against deterministic fakes before the live
call: a >4000-character valid candidate reached the strict parser intact while
the generic transport still capped at 4000; a tail canary after character 4000
was observed by the parser input and absent from every durable output; a
malformed >4000 output still scrubbed full plaintext; an oversize response
refused rather than parsing a prefix (COMPLETE OR REFUSE). The full plaintext
carrier is nulled in a `finally` block, so no parse exception can leave it in a
retained record.

## Carried validation debt

Pre-work and post-work `tools/validate.py --gate core` report the identical
three failures (DEBT-000066): SRC-017/T-41 unresolved receipt, the SRC-036
credential gate, and the board.schema superseded-field cross-doc drift. Verdict:
**CURRENT_FAIL / CARRIED_DEBT_UNCHANGED**, not VALID. No new validation failure
was introduced; the full suite is 1785 passed, exit 0 (1751 at the T-73
baseline, +34 new tests). T-65 and T-34 were not resumed. No production
`saimail/*` file changed; the strict parser and the generic 4000-character path
are byte-identical. No historical T-69/T-70/T-71/T-72/T-73 artifact or
registration was rewritten. No commit, tag, push or publication was performed.

## What this run does not show

No model ranking or winner. No claim that the corpus-ref rejection is caused by
the budget; it is a distinct failure. No semantic-review reachability, no truth
claim, no advice quality. One sample per role assignment is not a model property,
and corpus completeness remains NOT_PROVEN. Provider-side retention and training
use remain NOT_VERIFIED_BY_SAIMAIL.

## Next target decision

`4096 -> stop` with a parsed candidate that failed the corpus-ref gate is not
CASE A and not CASE B. The prior 2048 length ceiling is no longer the only
observed blocker; grounding/formatting remains a separate failure mode. Per the
handoff, the next candidate gate may test native JSON_SCHEMA while holding 4096
fixed, but ONLY after this evidence is reviewed. NOT STARTED.
