# Recurring host cycle: controlled replay of T-137 Work

The new cycle saves an independent host one CLI invocation per work entry while
returning the same discovery and receiver feedback as separate awareness and
metrics calls. Its returned JSON is larger. This experiment measures those
tradeoffs and continuity controls; actual agent comfort remains unmeasured.

## Registration and method

`python lab/agent_cycle_run.py --out lab/out/AGENT_CYCLE_T138` appends a fresh
registered attempt without overwriting earlier trials. `plan.json` records the
harness and input hashes before any trial invocation. Each observation runs a
fresh Python host process, which negotiates the real CLI contract and invokes
the actual correspondence commands. No provider call or external recipient is
involved. Private test identities and mutable project state use a temporary
directory, with a distinct experimental lineage.

The input is the actual T-137 CLI race evidence: the unchanged verifier returned
OK after two admissions before the fix and SAIPEN_CONTEXT_CHANGED after one
admission afterwards. The artifacts are copied byte for byte into the replay
project. Its BOARD/STATE and T-136/T-137/T-138 roles are explicitly experimental;
they confer no authority over real project Work.

Three paired entries alternate baseline/candidate order on the same unread
letter. Baseline calls awareness and metrics; candidate calls cycle. Both
include fresh contract negotiation. Equality checks cover items, cases, page
completion and reason metrics. JSON size is measured after normalization, not
as wire bytes or model tokens. Time includes local startup/cache variation and
has no performance threshold.

## Observations

| Measure, per entry | Separate awareness + metrics | Cycle |
| --- | ---: | ---: |
| CLI invocations including negotiation | 3 | 2 |
| Normalized returned payload bytes | 3749 | 4379 |
| Median CLI seconds, attempt-001 | 0.4267 | 0.2814 |
| Median CLI seconds, attempt-002 | 0.4398 | 0.2822 |

Cycle saves one invocation (33%) and returns 630 additional bytes (16.8%) in
this fixture. Less host work does not imply less model context. The larger
payload is retained as an unfavorable observation and a candidate for a later
host-owned compact projection.

All 15 registered checks passed in both attempts. Scripted DEFERRED and
DECLINED decisions return authenticated sealed feedback to a fresh sender
process. A scripted clarified request then carries a falsifiable completion
criterion. Resolution preserves the deferred history, survives an idempotent
report retry and becomes discoverable by a fresh successor process. The
successor explicitly rechecks the actual result artifact.

Failure controls establish why the result depends on durable state and current
evidence: removing the correspondence database removes reserve discovery
without inventing a database; changed result bytes return CHANGED; changing the
host event refuses a continuation; explicit STALE revision removes the retained
result and returns a distinct correction reply.

The initial registration at the output root stopped during dispatch because
the harness had not switched the simulated sender's active Work. Its plan and
refused observation remain available. The corrected harness binds T-136 for
sender dispatch and restores receiver context afterwards. No failed observation
was deleted or relabeled as a passing trial. Later attempts retain their own
registration and result, and `latest.json` is only a mutable navigation pointer.

## Limits and next use

This is controlled replay of real code evidence with scripted choices. It is
not a fresh model experiment, recurring field deployment, a measure of agent
attention, or proof of general autonomous improvement. The reproducible harness
can compare later host changes using the same inputs and controls. Real-session
usefulness, receiver effort and independently chosen successor behavior remain
part of the active broader evolution objective.
