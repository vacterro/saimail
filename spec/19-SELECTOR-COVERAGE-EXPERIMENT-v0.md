# V2-02: receiver topic coverage experiment v0

This experiment tests a tempting shortcut before it can hide an important
message: let each receiver explicitly declare routine `ci-ok` traffic as noise.
It measures the benefit and the failure boundary for both participants, using
the existing Post Office policy rather than changing a production selector.

## One variable

The baseline has `open_r3_topics={action}`, `open_r3_kinds={WARNING}` and
`ignore_topics={noise}`. The treatment changes exactly one policy field:
`ignore_topics={noise, ci-ok}`. Both receivers make the same declaration.
There is no learned relevance, content lookup, label lookup or model call.
The receiver policy sees only the existing authenticated clear header.

Both arms open DEFER messages, as the frozen FG-06 fallback-heavy workload
does. This is a workload choice, not a change to the Post Office default.
OPEN declarations still beat overlapping IGNORE declarations. All baseline
machine-required OPEN_R2/OPEN_R3 verdicts must retain their depth in treatment;
the D-036 floor and D-037 merge implementation remain unchanged.

## Frozen fixtures and independent truth

`lab/selector_coverage_fixtures.json` declares five workloads before any run:
routine traffic, mixed novel topics, an overlapping mandatory-open policy,
topic drift/misclassification, and low volume. Every item declares semantic
relevance independently of the header policy. In particular, an actionable
payload can carry a routine-looking topic. Both A-to-B and B-to-A directions
run; reporting must not average away harm to either receiver.

Each arm receives the exact same sealed envelopes and canonical records in
separate temporary stores. Truth is used only by the grader after the scan.
The sender performs no treatment-specific classification or additional send.
One-time policy setup and maintenance burden are reported explicitly rather
than assumed free or folded into an invented scalar weight.

The historical R1 stress corpus and FG-06 workload definitions are unchanged
controls. Unknown R1 atoms and opaque R1 claims are a different stage from
unmatched header topics; a reduction here must not be reported as a reduction
of R1 unknowns. The current R1 corpus is measured separately using the existing
selector. Historical published numbers stay historical, even if the current
corpus contains more fixtures.

## Pre-registration and integrity

`lab/selector_coverage_registration.json` freezes the mechanism, fixture hash,
success/refusal criteria, zero-call budget and unchanged friction weights.
`lab/selector_coverage_manifest.json` uses EXPERIMENT-MANIFEST-1 and pins the
fixture, registration and current implementation dependencies. Public input
copies under `lab/history/v202-selector-coverage/` allow historical input
verification independently of a later checkout. No live permission is granted.
An input or implementation mismatch refuses before execution. Results are
written only to a new output directory; existing evidence is not overwritten.

## Measurements and acceptance

Report per workload, direction and arm: delivered/scanned/opened messages,
fallback opens, unnecessary opens, false ignores, missed relevant messages,
and missed baseline machine-required opens. Report lost message identities;
false ignores and false opens are never summed or exchanged for a lower cost.

Use the unchanged FG-06 TOTAL_FRICTION weights and token ratios as a declared
model, with raw counts and sender/receiver work alongside it. A lower modeled
cost that misses relevant content is not a utility win. Latency and subjective
pleasantness are NOT_MEASURED, not invented from counts.

Accept the candidate only if fallback opens decrease, **every** direction and
workload has zero new false ignores, zero new missed relevant messages, and
zero baseline required-open downgrades. Any safety failure rejects the
candidate even if routine traffic becomes cheaper. A negative result closes
V2-02 as evidence, with no production promotion. No thresholds, weights,
fixtures, labels or policy adjustments are allowed after observing results.

## Boundaries and continuation

No production changes, new wire format, release rebuild, support-scope
expansion, model/provider/network call, commit, tag, push or publication.
The frozen 0.0.2a1 bundle and its external proof remain immutable.
After the result, update CURRENT-STATE and FUTURE-GATES-V2 with its actual
verdict, limitations and a concrete next development gate. V2-03 remains
optional; it does not become a dependency of local product usefulness.
