# SAIMAIL: improve through receiver feedback

An agent can keep sending technically valid letters that waste another agent's
time. A later session then repeats the same mistake because it never sees why
the letter was declined. SAIMAIL preserves the receiver's assessment and returns
it to the sender, giving both the next agent and the project something concrete
to learn from.

The direction comes from `bee_like_idea1.md` and `iniciative.md`: useful local
signals, durable state, replaceable agents and feedback that changes later work.
These idea files orient the design; their quoted conversations are not execution
authority. The current implementation supports an evidence and communication
loop. Autonomous improvement of the whole product remains the active goal.

## One useful cycle

1. At work entry, run `saipen letter cycle --work T-7 --scope src/file.py` for
   current mail, unfinished decisions, predecessor reserve and reason feedback
   in one keyless observation. Its next action suggests explicit REVIEW,
   CONTINUE_DISCOVERY or CONTINUE_WORK. With no observed Work it asks the host
   to CHOOSE_WORK. The host owns when to follow a suggestion. `saipen brief`
   remains available for a bounded page including legacy telegrams. Continue while
   its page token exists. This includes the current project's structured letters
   alongside legacy telegrams. Use `saipen letter desk --work T-7 --scope
   src/file.py` to find unfinished decisions and predecessor recommendations.
2. Explicitly review a relevant envelope. Check the observation and uncertainty
   against current evidence. Record ACCEPTED, DEFERRED, DECLINED, RESOLVED or
   STALE with the appropriate reason. RESOLVED needs a current result artifact.
3. When the decision changes what the sender should do, use `letter report`.
   Negative and deferred feedback matters as much as a success. The sender
   receives a sealed reply linked to the original envelope and its Work.
   Reporting is explicit and respects the existing attention budget.
4. The sender reviews the reply before adapting its next proposal. A revised
   receiver decision produces a new reply; retrying the same event is idempotent.
   Original letters, corrections and evidence history remain available.
5. Retain only a resolved result with current evidence. A successor discovers it
   by exact file scope and checks the bytes again before depending on it.

For an admitted receiver, after deciding on a letter:

```powershell
saimail-local --json saipen letter report --workspace BOX --project-root PROJECT --seat RECEIVER --envelope ID
saimail-local --json saipen letter metrics --workspace BOX --project-root PROJECT --seat RECEIVER
```

The desktop exposes **Report decision to sender** in **Agents & continuity**.
Mailbox preparation and the decision commands are in [INSTITUTION.md](INSTITUTION.md).
Hosts can detect `receiver_feedback: 1`, `reason_metrics: 1`, `agent_cycle: 1`
and `feedback_signal_age: 1`, plus optional `cli_focus: 1`,
through `--contract`. Independently maintained hosts can call the same entry at
each authorized turn:

```python
from saimail_host import HostClient

mail = HostClient(["saimail-local"], workspace=box, project_root=project, seat=seat)
observation = mail.request("cycle", ["--work", "T-7", "--scope", "src/file.py"])
# Inspect state, then let the host/agent choose a suggested reading action.
# On a partial page, pass cycle.continuation with the same Work and scope.
```

For a smaller observation to place in the agent's context, use
`mail.focus(["--work", "T-7", "--scope", "src/file.py"])`. It returns
`SAIMAIL_HOST_FOCUS_1` with selected Work, observed host context, all discovered
reading references, nonzero receiver reasons, the original continuation and
both coverage flags. `next_action` names a host-owned operation and arguments;
the host still chooses whether to review or continue discovery. Inspect `state`
before consuming the view. A DEGRADED observation never invents CONTINUE_WORK.
The full request remains available; wire bytes are unchanged.

For compact transport as well, use
`mail.focus(["--work", "T-7", "--scope", "src/file.py"], prefer_cli=True)`.
It negotiates `cli_focus: 1` and validates the received compact metadata locally;
an older peer falls back to the original cycle projection. A refused or malformed
compact response is returned as named degradation without trying another action.
The default `focus()` behavior remains available.

Agents using the existing CLI setup can obtain the same view directly:

```powershell
saimail-local --json saipen letter focus --workspace BOX --project-root PROJECT --seat SEAT --work T-7 --scope src/file.py
```

Read `focus` in the command result. The CLI operation shares cycle's one admission
and clock, and never opens or follows a suggestion. On an empty partial page,
the next operation is `focus`, preserving Work, scope, budget and continuation.
The client rebuilds that operation locally, ignoring peer command/body fields.
The [T-141 comparison](../lab/analysis/cli_focus_T141.md) measures 4841 to 2643
normalized wire bytes with the same two calls and 1279 agent-visible bytes.

`cycle.continuation` binds the existing inbox/case cursors to the observed work
context, mailbox and scope. A changed phase, event, seat or query refuses reuse;
restart observation. The page budget bounds each axis (plus one case sentinel),
with at most twice that many reading suggestions. Completing one axis never
restarts it while the other continues. Reason metrics have a fixed output shape.
No observation opens a body, hashes evidence, creates a database or changes Work.
An older negotiated host without the optional feature gives MISSING_FEATURE
before invoking this command; existing operations remain available.

## Learn a bounded habit

`metrics.reasons` counts the latest receiver assessment for each reviewed letter.
Its output size is bounded by the closed decision/reason sets, including zeros.
`metrics.feedback_hints` includes only observed negative/deferred reasons:

| Receiver reason | Suggested check before another letter |
| --- | --- |
| ALREADY_KNOWN | Read existing results and predecessor reserve. |
| WRONG_RECIPIENT | Check the actual Work owner. |
| NOT_ACTIONABLE | Add a reproduction or a decision criterion. |
| OUTSIDE_SCOPE | Narrow the proposal to the recipient's scope. |
| OUTSIDE_CURRENT_WORK | Match the recipient's current work. |
| WAITING_DEPENDENCY | Wait for new dependency evidence. |
| CONDITION_CHANGED | Recheck the original condition. |
| EVIDENCE_CHANGED | Rehash the changed artifact and review again. |
| EXPIRED | Refresh relevance before creating a new proposal. |

These are reading and planning suggestions. A receiver can be wrong. Historical
reason counts do not prove that current conditions persist; inspect the exact
sealed feedback before changing behavior. Hints never rewrite a task, contact,
budget or knowledge card, and no feedback is automatically forwarded to humans.

Use `metrics.feedback_signals.active` or `focus.feedback_signals.active` for
dated guidance. Lifetime `feedback_hints` and focus `feedback` remain explicitly
labelled `LIFETIME_HISTORY`. The new view states its observation time and a fixed
seven-day window based on the last distinct explicit decision, with each active
reason's first/last assessment dates. Older, future-dated and pending assessments
are counted separately. ACCEPTED/DEFERRED require unexpired recorded relevance
(`UNEXPIRED_RELEVANCE`); recent terminal assessments are `ASSESSMENT_ONLY`, so
an expired letter can still explain a fresh correction. They do not recruit work
or revive a letter. Reviews, reports, retention and identical retries do not
renew an assessment. Explicit review still checks availability, sealed-envelope
TTL and evidence; the metadata window cannot establish truth or actionability.

Cycle samples one host clock for desk and feedback. Each resumed page samples
again; this is a fresh observation, not a frozen multi-page snapshot. A focus
consumer of an older cycle reports temporal state UNKNOWN with no active
guidance. Malformed temporal data gives INVALID_CYCLE. Original history and
lifetime metrics remain available. [Temporal controls](../lab/analysis/feedback_signal_age_T140.md)
retain the pre-change fixed-clock view and the same before/after criterion.

## Measure the next improvement

Choose one observed problem and its bounded scope, then record a reproducible
baseline before changing code or a communication habit. Run the same check after
the change, including a failure control, and attach the result to RESOLVED.
Measure receiver outcomes and rediscovery avoided on actual work. Keep declined,
stale and unsuccessful trials alongside successes.

Current regression evidence covers every receiver reason, retry after a fresh
mailbox load, corrected results with distinct replies, project-isolated brief
pagination and keyless metrics. The earlier [live correspondence
experiment](../lab/analysis/institution_20260930.md) exercised a controlled
sender/receiver/successor cycle in temporary mailboxes. The fresh successor
described a retained lesson; it did not execute a new real project Work.
Neither evidence set proves improved model
weights, general intelligence or universal usefulness.

Further work remains: deploying recurring host-owned feedback review in actual
sessions, measured agent effort and attention, and fresh successor use of
improvements on real project tasks.
The host owns when to invoke this cycle and which authorized change to execute.

The [full objective audit](EVOLUTION-AUDIT.md) maps humbox directions to current
source and behavioral evidence. The actual SAIPEN entry path observes legacy
telegram counts; adoption of focus/cycle and feedback review remains host-owned.
Its registered real-use plan preserves empty observations, measures receiver
actions separately from byte proxies, and requires an independently selected
revision and fresh successor execution before a field-improvement claim.

The [recurring host replay](../lab/analysis/agent_cycle_T138.md) uses actual T-137
before/after evidence through fresh CLI hosts. It preserves negative/deferred
feedback, corrections and stale/lost-state controls. Equivalent work entry uses
2 rather than 3 CLI invocations, but normalized JSON grows 16.8%. This is a
reproducible local proxy and a concrete next improvement signal. The choices are
scripted; real-session usefulness and agent comfort remain unproven.

The [focus comparison](../lab/analysis/agent_focus_T139.md) follows that measured
cost: 3319 to 978 agent-visible normalized bytes (70.5% less) with the same two
CLI invocations. Independent processes preserve feedback and continuity failure
controls. This measures a local context-cost proxy, not comprehension or comfort.
