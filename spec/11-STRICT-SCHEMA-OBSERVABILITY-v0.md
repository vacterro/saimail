# Strict-schema observability / real-project reachability v0

This LAB contract eliminates an unobservable parser refusal without retaining
the refused text or changing its acceptance. T-69's discarded 3218 bytes cannot
be reconstructed or diagnosed from their hash. This contract concerns new calls.

## Authority and measured boundary

`lab/ally_generation_live.py` remains the strict parser authority. The unchanged
B-016 orchestration remains the structural, evidence, event and review authority.
The observer receives exactly the string handed to that parser. It returns
metadata only, never a candidate, replacement string, or acceptance decision.
Fences, surrounding prose, duplicate keys and invalid schemas remain refusals.
No stripping, extraction, repair, retry, second sample or third replicate exists.

The inherited transport's visible-output boundary remains unchanged: upstream
reasoning filtering and the 4000-character cap precede this observer. Consequently
telemetry describes parser-input bytes, not an unmodified provider response.
`output_truncated`, `inline_trace_removed` and a closed `finish_reason` are recorded
separately. A syntax error does not prove upstream truncation; a fence-token flag
does not prove that a fence caused rejection. Historical T-69 shape stays UNKNOWN.

## Closed structural telemetry

Every generator/reviewer call records the parser-input SHA256 and UTF-8 byte
length, input kind, blank flag, fence-token flag, first-token class (OBJECT,
ARRAY, STRING, NUMBER, LITERAL, OTHER, EMPTY), JSON syntax status, root type,
duplicate-key count, nonfinite-constant count, fixed syntax-error category and
numeric error position/line/column. JSON inspection starts only at the beginning
of the complete document; it never searches for embedded JSON.

For complete objects, record only the closed result discriminator (CANDIDATE,
NO_ADVICE, OTHER, ABSENT), top-level missing/unknown/type-mismatch counts,
nested item counts and nested missing/unknown/type-mismatch counts. Unknown key
names and values never leave memory. Invalid JSON has no invented schema counts.
An observer failure records OBSERVER_ERROR without exception text and does not
change the parser invocation or its result. Parser result and stable error code
are recorded after the authoritative parser actually executes, separately from
shape. No heuristic shape label may grant review or approval.

All durable output passes exact key/type/enum schemas, recursively. Extra fields,
free strings in telemetry, provider usage extensions, exception prose, raw output,
unknown field names, prompt/corpus/candidate/reviewer text must fail the privacy
tripwire before any artifact or report is written. Provider identity metadata is
a closed known label or OTHER with SHA256/byte length; arbitrary provider strings
are not copied. Usage retains only nonnegative integer token counts. Error bodies
may contribute only SHA256/byte length. Reports render the validated projection.
The T-70 population sanitizer is reused unchanged; no generic population record
is serialized. Credentials are checked against serialized outputs in memory.

## Registration and comparability

Exactly one new immutable `lab/project_corpus_reachability_registration.json`
binds this contract, frozen B-018 registration/build/corpus identities (8 artifacts,
5 declared events), T-69 artifact/report/interpretation hashes, unchanged generator
and reviewer template hashes, unchanged sampling limits, and requested routes:
R1 generator A=SAIFREN / reviewer B=goat/MiniMaxAI/MiniMax-M3; R2 reverses them.
Requested routes are fixed, reported models may change. Model/provider identity
is never inferred from an alias or namespace. Equal reported models are labeled.

The deliberate call-plan difference from T-69 is two fixed-route liveness probes
instead of catalog discovery/selection. Both must answer before corpus transmission.
There is no participant replacement, catalog refresh or selection retry. Budget:
2 probes + at most 2 generations + at most 2 reviews = 6 calls. Unspent calls stay
unspent. Authentication refusal stops remaining sends; transport failures retain
the existing stop rule. NO_ADVICE spends zero review calls and is successful.

Rebuild the exact B-018 BuiltProjectCorpus through its existing adapter before
credentials or network. Any identity drift refuses. Registration bytes, contract,
prompts and protected implementation hashes are verified before the experiment.
An exclusive, immutable registration-bound attempt marker is reserved before the
first network call. A second live invocation refuses, including after a crash,
NO_GO or malformed output. Changing output directories cannot bypass that marker.

## Required controls and closure

Before live calls, dry controls exercise both role assignments and actual unchanged
parsers: valid CANDIDATE reaching review, NO_ADVICE, fenced JSON, surrounding prose,
multiple objects, truncated/invalid JSON, duplicate keys, unknown/missing fields,
wrong root and nested types, wrong reviewer identities, FAIL, UNKNOWN, outside refs
and one-event refusal. Network/credential tripwires prove dry operation is offline.
Canaries cover values, unknown keys, rationale, exceptions, nested provider metadata
and population errors. Removing a privacy boundary must make its control fail.

The final metadata artifact/report/interpretation state separately: generator
transport reached, strict parse passed, candidate emitted, structural/ref/event
gates reached/passed, semantic reviewer invoked, reviewer parsed, and final B-016
outcome. No reachability is manufactured by retrying. No advice is presented, no
HUMAN_PRIVATE/HLET1/HENV1 is created, no sealing/storage/attention is invoked.

SCOUT and closure compare exact validator failure lines. DEBT-000066 remains
visible as CURRENT_FAIL / CARRIED_DEBT_UNCHANGED when unchanged. No debt repair,
receipt rewriting, T-65/T-34 work or commit/tag/push/publication is part of this
experiment. Local non-persistence makes no provider retention/training claim.
After the single bounded live attempt and its local verification/reporting, STOP.
