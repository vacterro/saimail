# Useful correspondence and successor reserve v1

Decision [D-066](DECISIONS-D066.md). This adds an application contract over SENV2,
the admitted participant registry and durable outbox; the wire format is unchanged.
The host owns its Work lifecycle. Letter contents, hashes and receiver decisions
remain information, never authority to execute instructions or promote knowledge.

## Letter

`SAIMAIL_LETTER_1` has exactly: schema, lineage, issue, trigger, sender_work,
recipient_work, observation, impact, request, done_when, uncertainty, evidence,
scope, expires_at, in_reply_to. Four utility text fields are required single-line
UTF-8, at most 2048 bytes each. At most 16 KiB per JSON body; duplicate fields,
unknown fields, invalid Unicode, unsupported triggers and ambiguous paths refuse.
Evidence is up to eight `{path, sha256}` objects; absent evidence requires explicit
uncertainty. Scope is one to eight exact project-relative files, no glob or parent
escape. Symlink/junction escapes and files above 8 MiB refuse at hashing time.
SHA-256 identifies bytes; it cannot establish semantic truth or novelty.

Dispatch checks host lineage/seat/BOARD binding, sender and recipient Work, admitted
recipient, relevance expiry and local evidence bytes before outbox submission.
Stable issue identity binds sender Work; rewording the same decision conflicts
instead of spending more attention. Existing notify budgets and crash/retry
semantics apply. Changed purpose must have an explicit distinct issue.

New letter topic: `l.<32 lineage hex>.<recipient Work>`. The encrypted body must
match this public routing context after authentication. This separates projects
sharing one mailbox and `T-9`, including every continuation page. Legacy telegram
topics keep their format. Early local bare-topic structured letters can be read
explicitly after authenticated lineage verification, but are excluded from new
keyless discovery; their project is not guessed from an unscoped header.

## Receiver and generations

Explicit review opens/reopens authentic content and rechecks evidence. A metadata
case starts PENDING; delivery and reading never record ACTION_TAKEN. Receiver
decisions: ACCEPTED/ACTION_PLANNED; DEFERRED/WAITING_DEPENDENCY or OUTSIDE_CURRENT_WORK;
DECLINED/ALREADY_KNOWN, NOT_ACTIONABLE, WRONG_RECIPIENT or OUTSIDE_SCOPE;
RESOLVED/ACTION_TAKEN; STALE/CONDITION_CHANGED, EVIDENCE_CHANGED or EXPIRED.
Resolving requires current local result evidence, which may differ from the
original reproduction after a fix. Identical current decisions are idempotent;
terminal corrections require explicit revise and append history (maximum 100).

Only explicit retain of an unexpired RESOLVED case with current result evidence
enters the reserve. A successor discovers retained recommendations by exact file
scope even with a different current Work. Discovery is keyless, checks no file
bodies and creates no database. It has separate inbox/case cursors, with a page
budget of 1..100. A bounded `continuation` token binds both cursors to the mailbox,
lineage, Work and exact scope; completed axes are not restarted. Changed context
refuses continuation; raw cursors require the returned context hash. Expiry stops
discovery but does not delete history. Explicit
review reports both original and latest result evidence states. A retained flag
does not certify current evidence; every reading recommendation requests a recheck.

`correspondence.sqlite3` version 1 is identity-bound and transactional. It stores
routing, paths, hashes, decisions, timestamps and bounded history; no observation,
impact, request or decrypted body. This metadata, like clear envelope headers,
is not encrypted. The sealed Post Office is content authority. An unavailable or
corrupt metadata database refuses; no guessed reconstruction or host-state write.

Report sends the latest explicit receiver decision to the authenticated original
sender/Work through the same outbox. ACCEPTED, DEFERRED, DECLINED and STALE carry
their closed decision/reason codes; RESOLVED still carries current result evidence.
PENDING cannot generate a report. A report links one original envelope, uses the
decision time for relevance expiry, and remains stable across retries. A revised
decision gets its own issue identity; it preserves earlier letters rather than
conflicting with their outbox keys. The first resolution retains its original v1
issue/body for compatibility with already submitted reports.

The local report result adds a `SAIMAIL_RECEIVER_FEEDBACK_1` receipt with original
envelope id, receiver-local event id, decision, reason and decision time. This
receipt is informational; the sealed reply is the sender's content authority.
The new receiver independently decides what the feedback establishes. Nothing
sends feedback merely because a letter arrived or was opened.

Metrics count current explicit receiver dispositions and their closed reasons,
scoped to one lineage. Corrections replace the current count while preserving
event history. `feedback_hints` suggests bounded communication checks for observed
negative/deferred reasons (for example ALREADY_KNOWN -> RECHECK_EXISTING_RESULTS).
Hints carry INFORMATION_ONLY authority. They never change routing, budgets, Work
or knowledge, and matching bytes or delivery counts never prove model improvement.

The T-140 temporal addition eliminates undated lifetime hints presented as current
guidance. Lifetime `feedback_hints` are labelled `feedback_hints_scope:
LIFETIME_HISTORY`. `metrics.feedback_signals` has schema
`SAIMAIL_FEEDBACK_SIGNALS_1`, observed_at, window_start, window_days (fixed 7),
basis LATEST_EXPLICIT_ASSESSMENT_AT, active, excluded, INFORMATION_ONLY authority
and automatic_execution false. Active rows carry a closed decision/reason,
positive count, first_at, last_at, kind and a fixed suggestion when defined;
there are at most eleven rows. The inclusive window uses the last distinct
decision's updated_at, never a read/report/retain/retry timestamp. Counts partition
each latest case once, in order: PENDING, FUTURE_ASSESSMENT, OUTSIDE_WINDOW,
LETTER_EXPIRED for nonterminal decisions, otherwise active.

ACCEPTED/DEFERRED require unexpired recorded letter relevance and have kind
UNEXPIRED_RELEVANCE. Recent DECLINED/RESOLVED/STALE are ASSESSMENT_ONLY even when
relevance has expired; this describes a dated outcome, not source actionability.
The sealed-envelope TTL and evidence are still checked by explicit review.
No timestamp renews relevance, resurrects content, changes a decision or purges
history. Metrics use one read snapshot. Cycle shares one sampled host clock
between desk and metrics; each continuation freshly samples its temporal window.

## Independently maintained hosts

`saimail-local --contract` returns `SAIMAIL_HOST_CONTRACT_1`, integer version 1,
without a mailbox, Qt or cryptography. Clients require supported correspondence,
keyless_desk, receiver_decisions and successor_reserve versions before actions.
Optional features `receiver_feedback: 1` and `reason_metrics: 1` advertise these
additions. Unknown fields may be ignored; unknown major schema, required feature, result
status, timeout or malformed JSON is DEGRADED, never an instruction to advance Work.
Legacy CLI/JSON schemas remain available. Optional `agent_cycle: 1` supports one
keyless entry over the desk and reason metrics through `saipen letter cycle`.
Optional `feedback_signal_age: 1` advertises the additive dated view.
It returns `SAIMAIL_AGENT_CYCLE_1` inside the command result. Suggested reading
actions use fixed allowlisted review/cycle command arrays; no mail body enters
an action. An empty partial page suggests CONTINUE_DISCOVERY, not completion.
No Work returns CHOOSE_WORK with no false mailbox-coverage claim.

The cycle's continuation wraps the existing dual-axis desk token and binds it
to the observed SAIPEN state/seat, mailbox, explicit Work and exact file scope.
It checks the state again after observation and refuses mixed contexts. The
budget is 1..100 per axis, plus one case sentinel; actions are at most twice
the budget. Metrics are current receiver assessments, not an atomic mailbox
snapshot or proof that historical feedback is still relevant. The host owns
recurrence, explicit opening and execution.

`HostClient(trusted_argv_prefix, workspace=..., project_root=..., seat=...)`
negotiates then `request("awareness", ["--work", "T-9", "--scope", "src/file.py"])`.
Supported actions: awareness, dispatch, review, decision, retain, report, metrics,
and optional cycle/focus. A client refuses cycle before invocation when the negotiated
peer lacks the supported agent_cycle version.
Commands come from the client's allowlist, never peer-provided strings or mail.
The supported adapter lives in `saimail_host`, outside the inert protocol library.
The client uses shell=False, DEVNULL stdin, a maximum 30-second timeout (default
10), and a 256 KiB cap on each output pipe. It never forwards stderr or requests
passwords. Its DEGRADED output is informational; the host keeps ownership of
unrelated work. Explicit discovery is the new integration hook, not a daemon.

`HostClient.focus(arguments)` is an opt-in client-side projection over the same
negotiated cycle. It returns `SAIMAIL_HOST_FOCUS_1`, with state OK, selected Work,
exact scope, observed seat/lineage/phase/task/event/blocker, the cycle context,
all deduplicated reading references, a host-owned next operation, both coverage
flags and examined-row counts, the original continuation, current disposition
counts and nonzero latest reason feedback. It omits repeated transport metadata
and zero-valued reason rows. It does not reduce CLI wire bytes.

Operations are reconstructed from desk references using the client's allowlist;
peer command hints and unknown body fields never enter the projection. Negative
reason suggestions use the independent version-1 consumer vocabulary. Full
`request("cycle", ...)` stays available. Unsupported/unavailable peers preserve
named degradation; malformed or mixed cycle/coverage/count data yields
INVALID_CYCLE and no next operation. Partial discovery and no selected Work
retain their original incomplete-coverage meaning. No projection opens content,
executes a suggestion or proves model improvement.

Focus preserves lifetime feedback with feedback_scope LIFETIME_HISTORY and adds
feedback_signals with state KNOWN, the dated basis/window, active rows and exclusion
counts. The independent consumer checks dates, closed codes, counts and partition
consistency, then reconstructs suggestions locally. An older cycle without the
addition yields state UNKNOWN and an empty active list; malformed temporal data
yields INVALID_CYCLE. Temporal eligibility never becomes Work authority.

The T-141 optional `cli_focus: 1` feature adds `saipen letter focus` with the same
Work/scope/budget/continuation inputs as cycle. It shares cycle's fresh one-admission
binding, final context recheck and sampled clock. The command result carries only
`focus: SAIMAIL_HOST_FOCUS_1` plus the normal status/detail fields, eliminating
transport metadata that the compact view already represents. A partial view
reconstructs operation `focus` for resumption. No private key, body read, evidence
hash, database creation or lifecycle action is added.

`HostClient.focus(arguments, prefer_cli=True)` negotiates compact transport;
missing or unsupported optional versions fall back to its existing cycle
projection before invocation. The default remains the original projection.
Explicit `request("focus", ...)` refuses MISSING_FEATURE when unsupported.
Peer command advertisements do not replace the client's allowlist. The compact
consumer expands only closed metadata into the independent version-1 validator,
then reconstructs references, reason suggestions and operations locally. Unknown
body, operation and coverage fields are dropped. Malformed compact metadata gives
INVALID_FOCUS; a refusal never triggers a second observation with another action.

The pure `saimail_host.project_focus(cycle_result, seat, arguments)` exposes the
same CLI projection for trusted operator integrations; it raises ValueError or
the corresponding structural error on inconsistent metadata. The CLI translates
that failure to INVALID_CYCLE. It performs no subprocess or suggested action.

Verified boundaries: `tests/test_correspondence.py`, `tests/test_host_client.py`,
existing notify/outbox tests and the live SAIFREN artifact in
`lab/out/INSTITUTION_20260930/`. Existing ZAICODE real-CLI readers and SAIPEN
turn-entry tests were exercised against this checkout without editing their code.
