# FUTURE GATE — COLONY SIGNALING AND COMMUNICATION HOMEOSTASIS

Status: REFERENCE ONLY / NOT AUTHORIZED FOR IMPLEMENTATION

## IDEA

Explore whether selected coordination properties observed in social insect colonies can improve SAIMAIL's agent communication architecture.

This gate does not propose biological simulation, anthropomorphic agents, swarm intelligence branding, or a "bee algorithm".

The useful abstraction is narrower:

> many replaceable participants can coordinate through cheap local signals, durable environmental state, bounded recruitment, progressive attention, and negative feedback without requiring a central conversational controller.

SAIMAIL already contains several compatible foundations:

- progressive decoding and bounded opening;
- explicit provenance;
- immutable receipts;
- durable delivery;
- receiver-owned attention;
- explicit promotion;
- message != authority;
- consensus != truth.

The future question is whether these can be extended into a coherent communication-homeostasis model.

## BIOLOGICAL ANALOGY BOUNDARY

The biological source is inspiration only.

No claim is made that bee behavior maps directly to software agents.

The implementation must be justified by measurable software properties, not by biological resemblance.

A feature is admissible only if it improves one or more of:

- total communication friction;
- bounded attention;
- continuation reliability;
- delivery reliability;
- stale-signal resistance;
- congestion behavior;
- fault tolerance;
- provenance quality;
- operator load.

"Bees do it" is never an acceptance criterion.

## PRINCIPLE 1 — CHEAP SIGNAL BEFORE EXPENSIVE ATTENTION

A colony does not require every participant to inspect every available source in full.

SAIMAIL should preserve and strengthen the principle:

```text
EXISTS
→ ROUTE
→ INTEREST
→ SUMMARY
→ PAYLOAD
→ EVIDENCE

The lowest-cost useful representation should be consumed first.
A receiver must not decrypt, parse, model-evaluate, or context-load a full payload merely to determine whether the message is relevant.
Existing R0-R4 ideas remain the conceptual basis.
Desired property
A large increase in message volume should not produce a proportional increase in:
- model calls;
- payload opens;
- token consumption;
- human interruptions;
- private-key operations.
PRINCIPLE 2 — SIGNALS ARE NOT COMMANDS
A recruitment signal may advertise:
- available information;
- discovered risk;
- possible work;
- a changed condition;
- a request for attention;
- a candidate dependency.
It must not acquire authority merely because it exists or because several agents repeat it.
Invariant:
MESSAGE != AUTHORITY
RECRUITMENT != ASSIGNMENT
CONSENSUS != TRUTH
URGENCY CLAIM != URGENCY AUTHORITY

A sender may advertise a condition.
The receiver, policy layer, or authorized lifecycle owner decides whether any action follows.
PRINCIPLE 3 — STIGMERGIC COMMUNICATION
Prefer coordination through durable externally visible state over repeated conversational synchronization.
Conceptual pattern:
agent observes condition
→ emits bounded durable signal
→ signal becomes part of receiver-visible environment
→ another agent independently encounters the signal
→ explicit handling occurs
→ resulting state is durably recorded

The original sender does not need to remain alive.
The receiving agent does not need the sender's conversation history.
The signal should survive session death without becoming authority.
Potential examples:
- immutable receipt;
- bounded topic marker;
- dependency-change signal;
- verified artifact-available signal;
- failure-observed signal;
- explicit request-for-review signal.
PRINCIPLE 4 — SIGNAL EVAPORATION
Biological recruitment signals lose effect when the underlying condition disappears.
SAIMAIL should investigate an equivalent concept for non-authoritative relevance metadata.
A signal may become less relevant because:
- the referenced state changed;
- a newer verified signal superseded it;
- its bounded validity interval expired;
- the referenced artifact disappeared;
- the receiver already handled it;
- repeated scans found no continuing relevance.
This must never silently delete historical evidence.
Separate:
HISTORICAL EXISTENCE
from
CURRENT RELEVANCE

A message may remain permanently auditable while no longer contributing to active attention.
Safety requirement
Expiration of relevance must not erase:
- provenance;
- delivery evidence;
- audit receipts;
- supersession history;
- security evidence.
PRINCIPLE 5 — RECEIVER-OWNED HOMEOSTASIS
Communication throughput must respond to receiver capacity.
If the receiver is congested, the system should prefer:
defer
compress
summarize
batch
ignore low-interest material
reduce recruitment

rather than:
increase notifications
increase repeated sends
open more payloads
escalate everything

Existing HUMAN_ATTENTION_BUDGET concepts provide a partial foundation.
Future work may investigate separate bounded budgets for:
- header scans;
- payload opens;
- semantic reviews;
- model-assisted triage;
- human presentation;
- sender retry;
- topic recruitment.
No sender may allocate the receiver's attention budget.
PRINCIPLE 6 — SHARED RESERVE
A colony stores resources for participants that do not yet exist.
SAIMAIL should preserve an analogous software property:
useful evidence should remain available to future agents even when the producing and consuming sessions never overlap.

This does not imply storing all conversation.
The preferred reserve is:
small durable signal
+ provenance
+ immutable evidence pointer
+ explicit current relevance

rather than raw context accumulation.
The reserve exists for recovery and continuation, not for indiscriminate memory injection.
PRINCIPLE 7 — RECRUITMENT BY OBSERVED VALUE
A future scout-like producer may advertise a discovered opportunity.
Example:
DISCOVERED:
  failing subsystem
  useful artifact
  unresolved contradiction
  available provider capability
  candidate optimization

The signal may contain bounded evidence supporting why another participant could inspect it.
It must not self-assign other agents.
Possible conceptual flow:
SCOUT OBSERVATION
→ EVIDENCE-BOUND SIGNAL
→ RECEIVER INTEREST FILTER
→ OPTIONAL OPEN
→ LOCAL DECISION

PRINCIPLE 8 — QUORUM WITHOUT TRUTH COLLAPSE
Multiple independent signals may justify increased attention.
They must not automatically promote a claim to truth.
Future aggregation may distinguish:
ONE SOURCE
MULTIPLE REPORTS / SAME SOURCE
MULTIPLE INDEPENDENT SOURCES
MULTIPLE AGENTS / SAME EVIDENCE
MULTIPLE AGENTS / DISTINCT EVIDENCE

These are not equivalent.
Any quorum mechanism must preserve source independence.
Invariant:
N AGENTS REPEATING ONE CLAIM != N INDEPENDENT OBSERVATIONS

PRINCIPLE 9 — CONGESTION FEEDBACK
A healthy communication system must contain negative feedback.
Potential observable congestion signals:
- unread queue depth;
- age of oldest unread item;
- open budget exhaustion;
- human-attention exhaustion;
- repeated duplicate delivery;
- topic fan-out;
- model-review backlog;
- unresolved high-severity messages.
A future implementation may use these only to adjust delivery and attention behavior.
Congestion must never silently modify truth, authority, or project lifecycle state.
PRINCIPLE 10 — FAILURE OF ONE PARTICIPANT IS ORDINARY
SAIMAIL must continue to assume that senders and receivers can disappear between any two operations.
No communication contract should require:
- sender session continuity;
- conversational memory;
- the same model;
- the same provider;
- the same process;
- synchronized uptime.
Durable state must remain sufficient for a replacement participant to understand what happened.
NON-GOALS
This gate does NOT authorize:
- autonomous execution of commands received through mail;
- unrestricted swarm behavior;
- agents creating agents without authority;
- majority-vote truth;
- sender-controlled priority;
- automatic promotion to knowledge;
- central AI supervision of every message;
- biological simulation;
- neural or evolutionary algorithms merely because the inspiration is biological;
- infinite durable storage;
- background polling without bounded resource policy.
POSSIBLE METRICS
Any future implementation should be measured against a non-colony baseline.
Candidate metrics:
messages delivered
payload-open ratio
mean headers inspected per useful message
token cost
model-call count
human-presentations per day
duplicate work triggered
stale-signal activation rate
time-to-useful-message
recovery after sender loss
queue convergence after burst load
TOTAL_FRICTION

The design should be rejected if it merely moves complexity into hidden infrastructure.
ENTRY CONDITIONS
Do not activate this gate until:
- current local post-office semantics remain stable;
- sender and receiver identity are stable;
- receiver-owned attention behavior is proven;
- duplicate and replay handling remain proven;
- current provenance contracts remain stable;
- measurable multi-agent communication load exists;
- there is evidence of communication congestion or unnecessary payload opening;
- the simpler current behavior can serve as a comparison baseline.
FIRST IMPLEMENTATION SLICE
If activated, begin with only:
ONE SIGNAL TYPE
ONE RECEIVER
ONE TOPIC
NO MODEL
NO HUMAN INTERRUPTION
NO AUTOMATIC EXECUTION

Recommended first experiment:
STATE_CHANGE signal
→ durable header
→ bounded interest
→ optional explicit open
→ handled marker
→ relevance expiry

Prove:
1. The sender can disappear immediately after delivery.
2. The receiver can discover the signal without opening the payload.
3. Historical evidence remains immutable.
4. Current relevance can expire without deleting history.
5. A stale signal cannot continue recruiting attention indefinitely.
6. Duplicate sends do not multiply effective urgency.
7. A replacement receiver can recover the same state.
8. No message can acquire lifecycle authority.
SUCCESS CRITERION
The gate succeeds only if SAIMAIL can support more participants and more messages while increasing useful information flow slower than it increases attention cost.
The target is not:
"Agents behave like bees."

The target is:
"Useful signals survive, stale signals fade, attention remains bounded, and no individual participant is required for the communication system to continue."


А вот **SAIPEN** я бы сделал ещё серьёзнее, потому что здесь пчелиная модель почти до неприличия хорошо совпадает с направлением проекта. У тебя уже есть `future_gate/`, и текущие документы там как раз имеют статус `REFERENCE ONLY / NOT AUTHORIZED FOR IMPLEMENTATION`. Поэтому этот документ ляжет туда естественно.

Например:

`future_gate/FUTURE GATE — STIGMERGIC COLONY ORCHESTRATION_20260929.md`

Готовый текст:

```markdown
# FUTURE GATE — STIGMERGIC COLONY ORCHESTRATION

Status: REFERENCE ONLY / NOT AUTHORIZED FOR IMPLEMENTATION

## IDEA

Explore a future SAIPEN coordination model inspired by one useful property of social insect colonies:

> replaceable workers coordinate through persistent environmental state and local feedback rather than depending on one continuously present controller.

This is not a proposal for biological simulation or uncontrolled swarm intelligence.

The software goal is:

```text
DURABLE PROJECT STATE
+ REPLACEABLE AGENTS
+ TEMPORARY WORK OWNERSHIP
+ LOCAL DECISIONS
+ BOUNDED RECRUITMENT
+ NEGATIVE FEEDBACK
= CONTINUOUS PROJECT PROGRESS

SAIPEN already contains several compatible properties:
- project-local durable state;
- cold-agent continuation;
- explicit lifecycle state;
- validation;
- evidence;
- recovery;
- task ownership boundaries;
- protocol-level continuation.
This gate asks whether those pieces can eventually become a genuinely self-stabilizing multi-agent work system.
CORE PRINCIPLE
The project is persistent.
The worker is temporary.
Invariant:
AGENT != PROJECT
SESSION != PROJECT
LEASE != OWNERSHIP
CONVERSATION != STATE

A project must remain understandable and resumable after any individual worker disappears.
PRINCIPLE 1 — STIGMERGY OVER CONVERSATIONAL COORDINATION
Agents should coordinate primarily by changing canonical project state, not by requiring direct agent-to-agent conversation.
Conceptual flow:
agent observes project
→ claims bounded work
→ changes verified project state
→ leaves evidence
→ releases or loses lease
→ next agent observes changed project
→ continues

The changed environment becomes the coordination medium.
Conversation may supplement this process but must not be required for correctness.
A fresh agent should not need access to the previous agent's private reasoning.
PRINCIPLE 2 — WORK BELONGS TO THE PROJECT
A task is never permanently owned by an agent.
Ownership is a bounded operational lease.
Conceptual state:
AVAILABLE
CLAIMED
WORKING
VERIFY
DONE

or

CLAIMED
→ LEASE EXPIRES
→ RECOVERABLE
→ AVAILABLE

Agent disappearance must be treated as an ordinary recoverable condition.
No ticket should become permanently blocked merely because:
- a model limit was reached;
- a provider disappeared;
- a session crashed;
- a cloud runner died;
- a user closed a terminal;
- an agent lost context.
PRINCIPLE 3 — REPLACEABLE WORKERS
The system should assume heterogeneous temporary workers.
Workers may differ by:
- model;
- provider;
- context window;
- tool availability;
- operating environment;
- cost;
- speed;
- reasoning quality;
- specialization.
Canonical project state must remain provider-neutral.
A worker may contribute only if it can prove the minimum capabilities required by the current work slice.
No project state may require reconstruction from one provider's private session.
PRINCIPLE 4 — DYNAMIC SPECIALIZATION
Social colonies do not require every worker to perform every role simultaneously.
A future SAIPEN system may support dynamic operational roles such as:
SCOUT
IMPLEMENTER
VERIFIER
RECOVERY
MAINTAINER
AUDITOR
RELEASE

These are temporary capabilities, not permanent identities.
An agent may change roles between slices.
Role assignment should depend on:
- current project state;
- available capabilities;
- task requirements;
- provider constraints;
- evidence requirements;
- current system load.
Roles must not become authority shortcuts.
An agent called VERIFIER is not automatically correct.
PRINCIPLE 5 — SCOUTING WITHOUT WORK EXPLOSION
A scout may discover candidate work.
Discovery does not automatically create active work.
Conceptual separation:
OBSERVED FRICTION
→ CANDIDATE
→ EVIDENCE
→ ADMISSION
→ BACKLOG
→ SCHEDULABLE WORK

This prevents an agent from converting every observation into another ticket.
The system must distinguish:
interesting
important
actionable
admitted
currently schedulable

These are not the same state.
PRINCIPLE 6 — RECRUITMENT WITHOUT COMMAND AUTHORITY
An agent may advertise that work is available.
It may not command arbitrary other agents merely by publishing the advertisement.
Example:
SCOUT:
  "T-204 may be blocked by X.
   Evidence: E-98.
   Capability needed: filesystem + Python tests."

A scheduler, authorized policy layer, or next participant decides whether to claim it.
Invariant:
DISCOVERY != TASK
TASK != CLAIM
CLAIM != AUTHORITY OVER OTHER AGENTS

PRINCIPLE 7 — PROJECT HOMEOSTASIS
The objective is not maximum agent activity.
The objective is stable useful progress.
A healthy system should regulate work-in-progress.
Possible observed project signals:
TODO depth
DOING depth
VERIFY depth
blocked age
claim age
failure recurrence
validator failures
unreviewed evidence
release debt
provider availability
human attention demand

A future scheduler may use these signals to adjust recruitment.
Examples:
VERIFY backlog high
→ reduce new implementation claims

many blocked tickets
→ favor diagnosis/recovery

high unfinished WIP
→ suppress scouting

clean project + empty admitted backlog
→ permit bounded improvement discovery

The scheduler must not create fake work merely to keep agents busy.
Zero useful work is a valid stable state.
PRINCIPLE 8 — WIP PRESSURE MUST CREATE NEGATIVE FEEDBACK
Without negative feedback, autonomous agents produce backlog faster than they resolve it.
Future SAIPEN orchestration should prefer:
finish
verify
recover
converge

before:
discover
expand
generalize
invent

Candidate rule:
NEW_WORK_ADMISSION decreases as unresolved WIP increases.

This should be measurable, not rhetorical.
PRINCIPLE 9 — SIGNAL EVAPORATION
Old urgency must not remain urgent forever.
Candidate scheduling signals may carry bounded freshness.
Examples:
- temporary provider outage;
- transient test failure;
- stale audit recommendation;
- old performance bottleneck;
- historical blocker that no longer exists.
Historical evidence remains immutable.
Scheduling influence may decay.
Separate:
HISTORICAL FACT
CURRENT CONDITION
CURRENT PRIORITY

They must never be collapsed into one field.
PRINCIPLE 10 — SHARED PROJECT RESERVE
A colony stores energy for workers that do not yet exist.
SAIPEN should treat verified project knowledge and evidence as a reserve for future agents.
The reserve may include:
- architectural decisions;
- verified failure modes;
- recovery procedures;
- acceptance evidence;
- stable conventions;
- known environmental constraints;
- rejected approaches and reasons;
- durable handoff state.
The reserve must not become an unlimited conversation archive.
Preferred form:
small maintained knowledge
→ provenance pointer
→ original evidence on demand

The purpose is continuation.
The purpose is not perfect memory.
PRINCIPLE 11 — COLD-AGENT FIRST
Every important workflow should be evaluated against a cold replacement worker.
Question:
If the current agent disappears now, what minimum durable state allows a different agent to continue correctly?

A future acceptance harness should deliberately kill or replace agents between lifecycle boundaries.
Example:
Agent A claims
→ exits

Agent B recovers
→ implements
→ exits

Agent C verifies
→ exits

Agent D closes

The resulting project state should be equivalent to a healthy single-agent run.
PRINCIPLE 12 — NO SPECIAL QUEEN PROCESS
The biological colony analogy must stop before introducing a permanent central AI ruler.
SAIPEN should not require one immortal coordinator whose context contains the "real project".
A coordinator, scheduler, or maintainer process may exist operationally, but canonical truth must remain outside it.
If the coordinator disappears:
project state survives
leases survive or expire safely
evidence survives
work remains recoverable
replacement coordinator can reconstruct the same scheduling view

No hidden central memory is permitted to become the project authority.
PRINCIPLE 13 — QUORUM IS NOT TRUTH
Multiple agents may independently verify a condition.
This may increase confidence but must not replace evidence.
The system should distinguish:
same agent repeated
multiple agents / same evidence
multiple agents / independent evidence
different implementations / same result
different environments / same result

A future quorum mechanism may be useful for high-risk actions.
It must never implement:
3 agents voted YES
therefore the claim is true

Evidence remains primary.
PRINCIPLE 14 — HYGIENIC BEHAVIOR
Healthy colonies remove damaged or dangerous material.
SAIPEN needs an equivalent for project-state hygiene.
Candidate targets:
- orphan claims;
- expired leases;
- contradictory lifecycle projections;
- duplicate tickets;
- stale generated artifacts;
- broken evidence references;
- impossible dependencies;
- abandoned temporary branches;
- dead audit outputs;
- persistent failed recovery markers.
Cleanup must preserve historical evidence where required.
Hygiene means removing active contamination, not rewriting history.
PRINCIPLE 15 — RESOURCE-AWARE LABOR
Work scheduling should eventually consider available resources.
Possible inputs:
provider available
provider unavailable
context budget
rate limit
tool capability
local machine capability
network availability
human availability
cost budget

The project should degrade gracefully.
Example:
preferred worker unavailable
→ compatible weaker worker handles bounded safe slice

all capable workers unavailable
→ work remains recoverable and waits

"Better than zero" is valid only when the weaker worker cannot damage correctness.
Capability requirements must remain explicit.
PRINCIPLE 16 — NO BUSYWORK
An autonomous colony-style scheduler must recognize a stable idle state.
If:
no admitted work
no recovery needed
no verification pending
no meaningful changed source
no authorized improvement target

then:
IDLE

is correct.
Agents must not manufacture tasks merely to preserve activity.
Autonomy means continuing useful work without a human.
It does not mean creating infinite work.
TARGET ARCHITECTURE
Long-term conceptual shape:
                    ┌──────────────┐
                    │ PROJECT STATE│
                    └──────┬───────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
       SCOUT           IMPLEMENT         VERIFY
          │                │                │
          └──── evidence / lifecycle ───────┘
                           │
                    ┌──────▼───────┐
                    │ HOMEOSTASIS  │
                    │   SIGNALS    │
                    └──────┬───────┘
                           │
                    bounded scheduler
                           │
                    next useful claim

All boxes except durable project state are replaceable.
SCHEDULER INPUT CONTRACT
A future scheduler should operate only on explicit project-visible inputs.
Potential inputs:
CURRENT_PHASE
ADMITTED_WORK
ACTIVE_LEASES
LEASE_AGE
BLOCKERS
VERIFY_QUEUE
RECOVERY_STATE
VALIDATION_STATE
KNOWN_CAPABILITY_REQUIREMENTS
AVAILABLE_WORKER_CAPABILITIES
HUMAN_DECISION_REQUIRED
RESOURCE_BUDGET

It must not depend on private chain-of-thought.
SCHEDULER OUTPUT CONTRACT
The scheduler should produce a bounded proposal such as:
NEXT_ACTION
TARGET
REASON
REQUIRED_CAPABILITIES
LEASE_POLICY
EVIDENCE_REFS

The proposal itself is not execution.
Existing SAIPEN authority rules remain unchanged.
FAILURE MODEL
The architecture must explicitly tolerate:
agent disappears
agent times out
provider rate-limits
provider disappears
tool unavailable
worktree dirty
validation fails
network disappears
machine reboots
duplicate continuation attempt
two workers attempt same claim
stale worker returns after replacement

Each condition must converge to one visible recoverable state.
CONCURRENCY MODEL
Multiple workers require explicit protection from double work.
At minimum, future implementation must define:
claim identity
claim owner
lease start
lease expiration
heartbeat or progress evidence
release
recovery
stale-worker behavior

A stale agent returning after lease loss must not silently continue mutation.
It must re-enter through current project state.
SAFETY BOUNDARIES
The colony model must never override:
- user authority;
- project scope;
- tool permissions;
- safety policy;
- lifecycle validation;
- evidence requirements;
- explicit STOP conditions;
- external system authorization.
Emergent coordination is permitted only inside these boundaries.
NON-GOALS
This gate does NOT authorize:
- unlimited autonomous agent spawning;
- uncontrolled parallelism;
- majority-vote truth;
- permanent AI management authority;
- replacing SAIPEN lifecycle state with emergent behavior;
- removing explicit tickets or evidence;
- background work without bounded resource policy;
- automatic execution of every discovered improvement;
- global optimization across unrelated projects;
- agents assigning arbitrary work to other agents;
- hidden scheduler state;
- dependence on one model provider;
- biological simulation.
POSSIBLE METRICS
Measure against the current SAIPEN baseline.
Candidate metrics:
time to recover after agent loss
fraction of work recoverable by cold agent
duplicate work rate
stale-claim rate
mean WIP
VERIFY backlog age
blocked-ticket age
human interventions per completed ticket
tokens per completed ticket
provider-switch recovery time
false work admission rate
idle correctness
project convergence time
regression rate

A colony architecture is valuable only if it improves continuation and convergence.
More simultaneous agents is not itself success.
ENTRY CONDITIONS
Do not activate this gate until:
- single-agent lifecycle semantics are stable;
- claim and recovery behavior are mechanically trustworthy;
- project identity is stable;
- validation is reliable;
- current-state projection is reliable;
- cold-agent continuation works consistently;
- agent output follows protocol mechanically;
- duplicate claim behavior is understood;
- SAIMAIL/other communication channels do not bypass lifecycle authority;
- multi-agent demand is demonstrated rather than hypothetical.
FIRST IMPLEMENTATION SLICE
If activated, begin with a failure-recovery experiment, not full scheduling.
Scope:
ONE PROJECT
ONE TICKET
TWO AGENTS
ONE CLAIM LEASE
NO PARALLEL IMPLEMENTATION
NO AUTO-SPAWN
NO MODEL-BASED SCHEDULER

Experiment:
1. Agent A claims one ticket.
2. Agent A records bounded progress.
3. Agent A is deliberately terminated.
4. The lease expires or is explicitly recovered.
5. Agent B starts cold.
6. Agent B reconstructs the current state only from canonical project artifacts.
7. Agent B continues the same ticket.
8. Agent B moves it through VERIFY.
9. Normal validation proves project consistency.
10. No hidden state from Agent A is required.
Red control:
Agent A returns after lease loss and attempts to continue using stale state.
Expected result:
STALE_WORKER_REFUSED

or an equivalent explicit re-entry requirement.
SECOND IMPLEMENTATION SLICE
Only after the first slice is proven:
TWO INDEPENDENT AVAILABLE TICKETS
TWO WORKERS
EXPLICIT NON-OVERLAPPING CLAIMS
BOUNDED WIP = 2

Demonstrate that parallelism improves completion time without increasing:
- duplicate mutation;
- validation failures;
- lifecycle ambiguity;
- recovery complexity;
- human supervision.
THIRD IMPLEMENTATION SLICE
Only after bounded parallel claims are proven, experiment with homeostatic scheduling.
Example rule:
IF VERIFY_QUEUE >= LIMIT:
    DO NOT ADMIT NEW IMPLEMENTATION WORK
    PREFER VERIFICATION

IF BLOCKED_QUEUE >= LIMIT:
    PREFER RECOVERY / DIAGNOSIS

IF WIP >= LIMIT:
    DO NOT SCOUT

IF NO ADMITTED WORK AND SOURCE UNCHANGED:
    IDLE

Begin deterministic.
Do not introduce model-based scheduling until deterministic policy has a measurable baseline.
SUCCESS CRITERION
A successful implementation should allow useful project progress to survive replacement of every individual worker.
The desired property is:
no agent is indispensable, no conversation is canonical, work ownership is temporary, and project state is sufficient for correct continuation.

The deeper target is not "many agents working".
It is:
a project that behaves as a stable system even though every worker is temporary.


И вот тут есть ещё один важный design insight.

У пчёл **нет задачи максимизировать количество занятых пчёл**. Их distributed system стремится держать colony viable. Если nectar source исчез, recruitment туда ослабевает. Если появляется хороший источник, recruitment усиливается. Если ресурсов хватает, поведение меняется.

Для SAIPEN это может оказаться фундаментальным:

> **не максимизировать количество работающих агентов; максимизировать скорость устойчивой сходимости проекта.**

То есть 12 агентов, которые одновременно нашли 47 улучшений, могут иметь меньший КПД, чем 3 агента, которые `implement → verify → close` без хвостов.

Это почти противоположность типичному AI-agent hype, где красивый screenshot показывает 50 агентов, бегающих вокруг как тараканы после включения света.

Для твоего SAIPEN правильнее будет:

`AUTONOMY ≠ ACTIVITY`

а:

`AUTONOMY = USEFUL CONTINUATION WITHOUT HUMAN DEPENDENCY`

Вот эту фразу я бы вообще сделал одним из будущих core principles.

И ещё одна штука мне особенно нравится: **pheromone evaporation → priority evaporation**. Сейчас software systems очень плохо умеют забывать старую срочность. Кто-то однажды написал `URGENT`, и эта хуерга может лежать красной три месяца, хотя проблема исчезла. В bee-inspired SAIPEN evidence остаётся навсегда, но **scheduling influence должен иметь freshness**. Это реально сильная идея.

Условный КПД вдохновения я бы оценил так: для SAIMAIL около **80