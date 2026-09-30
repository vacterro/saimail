# A smaller work entry for the agent's context

T-138 found that cycle saved one CLI invocation but returned more JSON. T-139
adds an opt-in host projection over the same observation. It preserves the
reading references, latest receiver assessments and coverage limits while
removing repeated transport metadata and zero-valued reason rows.

## Registered comparison

`python lab/agent_cycle_run.py --out lab/out/AGENT_CYCLE_FOCUS_T139` registers
version 2 before each attempt. The original T-138 version-1 attempts remain
unchanged. Each of three entries observes the same unread letter through
separate awareness/metrics, full cycle and `HostClient.focus`. Their order
rotates, and every entry uses a fresh host process and contract negotiation.

| Measure per entry, attempt-001 | Separate discovery | Full cycle | Focus |
| --- | ---: | ---: | ---: |
| CLI invocations, including negotiation | 3 | 2 | 2 |
| Normalized CLI payload, including contract | 3749 bytes | 4379 bytes | 4379 bytes |
| Agent-visible normalized JSON, excluding contract | 2689 bytes | 3319 bytes | 978 bytes |
| Median CLI seconds, descriptive only | 0.4179 | 0.2614 | 0.2955 |

Focus reduces agent-visible JSON by 2341 bytes (70.5%) relative to full cycle
in this fixture. It does not reduce wire bytes or promise a latency improvement.
Payload bytes are a context-cost proxy; no model token count or comprehension
measurement is claimed.

The 23 checks include the original feedback/continuity controls and comparisons
of focused discovery, context, continuation, both completion flags and decision
counts. Focused negative/deferred feedback, fresh successor reserve, changed
host context, absent correspondence state and stale correction also run through
independent processes. The original T-137 before/after evidence is unchanged;
sender and receiver choices remain scripted.

## Actual host entry

The active agent also used focus on its actual T-139 Work and configured local
mailbox, scoped to `saimail_host.py`. The recorded observation is
`.saipen/evidence/T-139-focus/actual-entry.json`: BUILD/T-139, complete discovery
from the start, zero mail/cases and informational CONTINUE_WORK. No body was
opened and no mailbox or Work decision was changed. This is one real empty
work-entry observation, not evidence of field usefulness or multi-agent comfort.

## Contract preserved

`HostClient.focus(arguments)` negotiates and requests the existing optional
cycle feature. Full `request("cycle", arguments)` remains available. The
projection emits `SAIMAIL_HOST_FOCUS_1` and reconstructs allowlisted reading
operations from every discovered desk reference. It never forwards peer command
hints or follows an operation automatically. Explicit review still opens and
rechecks sealed content.

The projection retains selected Work, exact scope, observed host context, both
coverage flags, examined rows, the unchanged continuation, all deduplicated
envelope references and nonzero latest reason counts. Negative reason suggestions
come from the client version-1 vocabulary. Assessments remain INFORMATION_ONLY,
with automatic execution and proof of model improvement both false. Unavailable
or unsupported peers keep their named degradation; malformed/mixed cycle data
returns INVALID_CYCLE with no fabricated next action.

Actual recurring sessions, measured receiver effort and independently chosen
successor behavior remain part of the broad evolution objective. This work
closes one measured local feedback loop: observe a cost, admit a bounded
improvement, change the host entry and repeat the registered checks.

## Isolation repair

The first full repository run found the replay harness in the wrong layer:
the unchanged laboratory-isolation guard forbids owning process invocation or
project-memory paths in laboratory modules. The operational implementation now
lives in `tools/agent_cycle_replay.py`, outside the inert packages. The recorded
`python lab/agent_cycle_run.py ...` command is a thin, lazy checkout-only
compatibility entry. No isolation assertion was removed or weakened. The earlier
registrations and their source hashes remain available, and the relocated
implementation registers its own hash before another attempt.
