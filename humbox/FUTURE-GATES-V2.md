# SAIMAIL: Roadmap v2 (POST-FG06) — COMPLETED / SUPERSEDED

> **Status: completed historical planning evidence.** Roadmap v2's non-optional
> gates are closed: V2-01 DONE via T-85, V2-02 DONE via T-88 (measured negative
> `CANDIDATE_REJECTED_SAFETY`), V2-04 DONE via T-86/T-87. V2-03 stays optional
> and NOT STARTED. `humbox/FUTURE-GATES-V3.md` is now the **current roadmap
> authority**; this file is preserved intact as evidence.

Updated: 2026-09-20. Authority when written: this file, for work after FG-06. It
supersedes `humbox/FUTURE-GATES.md` as the *current* roadmap; that file stays
intact and identifiable as the **completed Roadmap v1**. This is a plan, not
permission to publish, to make a live model call, or to change any proven
contract.

Roadmap v1 is complete: FG-00, FG-02, FG-03, FG-04A, FG-04B, FG-05 and FG-06
are DONE; FG-01 is diagnosed and externally blocked. No Work is active. The
goal of this document is to convert that completed evidence into the next
evidence-based plan, not to invent a successor gate because the carousel feels
empty.

Current position after T-88: **V2-01 DONE; V2-02 DONE (T-88,
`CANDIDATE_REJECTED_SAFETY`); V2-04 DONE; V2-03 optional, NOT STARTED.** With no
remaining non-optional gate, this roadmap is completed and superseded by
`humbox/FUTURE-GATES-V3.md`.

## 1. Current proven baseline

Everything below is demonstrated by stored evidence, not by intent.

- **Deterministic local composition (FG-05 / T-82).** A two-participant offline
  scenario composes source → typed record → signed/sealed envelope → delivery →
  deduplication → bounded header scan → explicit open → separate promotion, then
  proves restart, TTL/tombstone non-resurrection, LEGACY succession provenance,
  HUMAN_PRIVATE seal/store/open with exactly one attention reserve/ACK, and six
  injected durable-write failures. Zero network/model calls, no hardware
  provisioning, no production `saimail/*` change. Artifacts:
  `lab/local_scenario.py`, `tests/test_local_scenario.py`,
  `spec/15-LOCAL-SCENARIO-v0.md`.
- **Installable local entrypoint and stable maps (FG-06 / T-83).** A clean-wheel
  install and installable `saimail-local` entrypoint exist; clean isolated
  installation is proven from outside the checkout; `lab/stable_local_api.json`
  is the machine-readable stable API/type/failure map with `retry_safe`,
  `operator_action` and `authority_intact` flags.
- **Measured utility is conditional.** `UTILITY_CONDITIONAL`: a real cost win at
  a low open rate, neutral at moderate/high open rate and under fallback-heavy
  traffic, under the declared `TOTAL_FRICTION_FRICTION_UNITS_v1` model. The
  source of the win is selective resolution plus the zero-inference header scan,
  not the compact syntax.
- **Syntax cost is a preserved negative.** T-9B stands: the compact frame is
  **more expensive than information-equivalent triage prose per message** on
  every measured tokenizer, and the canonical record is never cheaper than
  equivalent prose (45/45 cases). The record is a storage/audit format, not a
  context format.
- **Generative reachability is partial, not solved.** FG-04B proved a
  schema-valid candidate can pass the reference gate, meet the event floor, and
  reach a real semantic reviewer invocation. It did **not** prove semantic
  reviewer success: the reviewer reply was not one parseable strict JSON
  document (`ALLY_LAB_BAD_JSON`, 3801 bytes, `finish_reason=stop`), so the
  outcome is `REVIEWER_ERROR` with zero semantic verdicts.
- **Reproducibility discipline exists.** `spec/13-EXPERIMENT-REPRODUCIBILITY-v0.md`
  separates historical verification, current-checkout verification and live
  admission; historical fixtures/mutations have negative controls.
- **Offline reference diagnostics exist.** `spec/14-REFERENCE-TELEMETRY-v0.md`
  and `lab/reference_telemetry.py` classify candidate evidence references
  without acceptance authority; the T-74 exact bad-ref class stays `UNKNOWN`.
- **Persistent local workflow (V2-01 / T-85).** Separate persistent workspaces
  exchange public identity cards, register recipients and perform local
  send/deliver/list/open across restarts with duplicate suppression.
- **Scoped local alpha readiness (V2-04 / T-86, T-87).** Frozen `0.0.2a1`
  has a hash-matched external installed-package PASS on Linux / Python 3.13.5,
  including FG-05, FG-06, V2-01 and privacy with zero runtime network/model/provider
  calls. See `release/evidence/T87-T86-closure.md` and
  `release/evidence/external_proof_acceptance.json`. The candidate remains
  NOT_PUBLISHED and its frozen advertised platform scope is unchanged.

## 2. Current limitations

Real, observed, and each one is either a blocker or explicitly optional.

- **L1 — Persistent workflow gap resolved by V2-01 / T-85.** The usable local
  identity and persistent send/receive workflow now exists outside the
  synthetic harness. Filesystem delivery and explicit identity exchange remain
  deliberate boundaries.
- **L2 — Utility is conditional and open-rate-sensitive.** The measured win
  collapses toward neutral as open rate or fallback rate rises. Finding 9 in
  `bench/ANALYSIS.md` identifies the cause: unknown atoms force opens, so
  vocabulary/selector coverage *is* selector efficiency.
- **L3 — Reviewer reply shape blocks semantic review.** The remaining observed
  blocker in the generative research line is that the reviewer did not return
  one parseable strict JSON document. This is a research hypothesis, not a
  product-path blocker.
- **L4 — External install gap resolved by V2-04 / T-86, T-87.** The scoped
  alpha package and the supplied external Linux / Python 3.13.5 installed proof
  identify the same frozen wheel. This is additional successful evidence,
  not an expansion of advertised platform support. Publication remains NONE.
- **L5 — SAIPEN/accounting debt is real and separate.** SRC-017/T-41, SRC-036,
  the stale improve-report fingerprint, and `SAIPEN_DIGEST_DRIFT` remain
  SAIPEN-side debt. They must not become dependencies of normal SAIMAIL work.

## 3. Priority principles

- **Remove an observed gap; do not accumulate features.** Every gate names the
  limitation it addresses and what becomes newly possible or newly proven.
- **Prefer the smallest user-facing step that exercises proven protocol
  semantics** over a new framework, GUI, adapter or service.
- **One intentional variable per experiment.** Retain a strict call ceiling; do
  not change schema, prompt, corpus and model at once.
- **Conditional utility survives.** No gate may rewrite measured neutral or
  negative results into a universal claim.
- **Independent work stays independent.** Optional research must not block the
  non-generative local path; SAIPEN debt must not block SAIMAIL; adapters must
  not block local readiness.
- **Every gate needs a stop condition.** A gate whose evidence says "stop" is a
  successful gate.

## 4. Roadmap table

| Gate | Status | Lane | Priority | Depends on | Newly possible / proven |
|---|---|---|---|---|---|
| V2-01 Persistent local workspace and real send/receive | DONE (T-85) | A — practical local productization | HIGH | FG-05, FG-06 (DONE) | A real user runs a persistent local send/receive workflow outside the harness |
| V2-02 Selector coverage / fallback-open reduction experiment | DONE (T-88) — `CANDIDATE_REJECTED_SAFETY` | C — utility/coverage | MEDIUM | none (independent) | One mechanism tested: static receiver topic ignore lowers fallback opens but is unsafe under topic drift |
| V2-03 Reviewer output-format bounded experiment | NOT STARTED; optional | B — generative research | LOW (optional) | FG-04B/FG-04A (DONE) | One parseable reviewer verdict document, or a measured refusal, under one changed variable |
| V2-04 Scoped local alpha release readiness | DONE (T-86/T-87) | D — distribution | MEDIUM | V2-01 (DONE) | A reproducible local-alpha package and another-machine install proof; publication stays separate |

Lane E (external adapters) and Lane F (live multi-user service) are evaluated
and deferred; see section 7.

## 5. Gate sections

### V2-01 — Persistent local workspace and real send/receive

- **Observed gap (L1).** The proven local protocol has no persistent workspace,
  no user-owned identity initialization, and no real send/receive outside the
  synthetic FG-05 scenario and the ephemeral demo.
- **Target.** The smallest user-facing step that exercises already proven
  protocol semantics: a persistent local workspace (durable root plus
  receiver-owned identity initialization) with a real off-harness
  send → deliver → scan → open → separate-promotion flow, reusable across
  process restarts.
- **Non-goals.** No GUI; no Gmail/Slack/Outlook or any adapter; no server,
  daemon or hosted service; no model/generation on the base path; no new
  protocol semantics; no change to FG-05's `LOCAL_SCENARIO_RESULT_1` contract.
- **Acceptance.** A documented command sequence starting from a clean install
  creates a persistent workspace, initializes two local identities, sends a real
  message, delivers/scans/opens it, promotes separately, and survives a process
  restart — with zero network/model calls and no production behavior regression.
- **Dependency.** FG-05 and FG-06 (DONE).
- **Reason for priority.** It directly addresses L1 and turns a proven local
  protocol into a usable operator path, which is the practical prerequisite for
  any release or adapter decision.

### V2-02 — Selector coverage / fallback-open reduction experiment

- **Result (T-88, DONE).** `CANDIDATE_REJECTED_SAFETY`. Extending
  `HeaderInterest.ignore_topics` from `{noise}` to `{noise, ci-ok}` reduced
  aggregate fallback opens 246 -> 68 on the frozen fixtures, but the
  `TOPIC_DRIFT` workload lost two relevant `ci-ok` messages per direction. A
  static topic ignore cannot be relevance authority when semantic topic drift is
  possible; the modeled saving was declared inadmissible. Evidence:
  `lab/analysis/v202_selector_coverage_closure.md`.
- **Observed gap (L2).** Utility collapses as open rate and fallback rate rise;
  fallback opens (unknown wire atoms, claims the frame cannot carry) are 36% of
  a stress corpus, and coverage is the selector's efficiency.
- **Target.** Test exactly one concrete mechanism expected to reduce
  unnecessary opens **without increasing false ignores** — for example an
  explicit receiver relevance declaration, a bounded atom/coverage extension, or
  an UNKNOWN-reduction rule — measured on frozen fixtures against the declared
  asymmetric false-ignore cost.
- **Non-goals.** No friction-weight tuning; no fixture tuning until SAIMAIL
  "wins"; no summing of false ignore and false open into one score; no change to
  the non-downgradable `MACHINE_REQUIRED_OPEN` floor (D-036); no production
  semantic change without a separate decision.
- **Acceptance.** A pre-registered experiment reports whether the mechanism
  lowers fallback opens with zero new false ignores; a negative result closes the
  gate as measured evidence.
- **Dependency.** None. Independent of V2-01, V2-03 and V2-04.
- **Reason for priority.** It attacks the one measured weakness FG-06 exposed
  and is the only lane that can widen the low-open-rate win.

### V2-03 — Reviewer output-format bounded experiment (optional research)

- **Observed gap (L3).** The reviewer path is reachable, but its reply was not
  one parseable strict JSON document; semantic review is still not demonstrated.
- **Target.** One newly registered bounded experiment that changes exactly one
  intentional variable (reviewer structured-output/response-format enforcement),
  reusing the unchanged corpus and reference gate, to see whether the
  already-reached reviewer invocation can produce one parseable verdict
  document.
- **Non-goals.** No prerequisite for the non-generative local path; no retry,
  repair prompt or participant replacement; no simultaneous change of schema,
  prompt, corpus and model; no claim of provider enforcement from one sample.
- **Acceptance.** Either one parseable reviewer verdict document, or a measured
  named refusal, under a strict ≤6-call ceiling with zero retries and admission
  proved before the first network call.
- **Dependency.** FG-04A and FG-04B (DONE); a new registration is mandatory.
- **Reason for priority.** It tests the only currently observed reviewer-output
  blocker and resolves the highest-value option uncertainty in the research
  line — but it stays optional and must not block V2-01/V2-04.

### V2-04 — Scoped local alpha release readiness

- **Observed gap (L4).** Clean install is proven only on this host; there is no
  reproducible another-machine/another-user proof and no deliberately scoped
  alpha package.
- **Target.** The smallest remaining work before a deliberately scoped **local**
  alpha can be released: a frozen release-candidate composition, a
  cross-machine/clean-venv install proof, a version marker, and published
  limitations.
- **Non-goals.** No publication in this or any planning ticket; publication
  stays a separate explicit operator action; no hosted service; no adapter; no
  universal-utility claim.
- **Acceptance.** Another machine installs the candidate from a clean
  environment, runs the V2-01 workflow and the FG-05/FG-06 benchmarks, and
  observes the same documented result shape with the explicit limitations.
- **Dependency.** V2-01 (a real local workflow is worth packaging).
- **Reason for priority.** It converts proven local capability into a
  distributable artifact while keeping publication an operator decision.

## 6. Dependencies

```
V2-01  <- FG-05, FG-06 (DONE)
V2-02  <- none (independent)
V2-03  <- FG-04A, FG-04B (DONE); new registration
V2-04  <- V2-01
```

- V2-03 (research) does **not** block V2-01 or V2-04.
- V2-02 does **not** block any product gate.
- FG-01 / SAIPEN debt (SRC-017/T-41, SRC-036, improve-report fingerprint,
  `SAIPEN_DIGEST_DRIFT`) is **not** a dependency of any V2 gate unless a
  concrete operation actually requires it.
- Adapters and live service are not dependencies of local readiness.

## 7. Deferred work

Classified as candidates, not implemented. Revisit only if evidence changes.

- **Full GUI.** Deferred; V2-01 is a command workflow, not a UI.
- **Gmail / Slack / Outlook adapters and any adapter framework.** Deferred; an
  adapter must first show it teaches something the local path cannot, and needs
  a stable practical local workflow (V2-01) worth transporting.
- **Live multi-user service** (server, daemon, hosted service, synchronization,
  remote accounts, distributed coordination). Deferred; current evidence proves
  local two-party composition, not service readiness.
- **Autonomous personal correspondence; semantic cache; broad model/provider
  expansion; dynamic global dictionaries; global short-ID redesign;
  hardware-key provisioning.** Deferred as before; `humbox/future1.md` keeps
  the ideas.
- **Language/grammar extensions B-008/B-009/B-010.** Deferred; no new evidence
  since T-9B.
- **SAIPEN/accounting debt (FG-01).** Separate track; keeps its own diagnosis
  and is not scheduled here.

## 8. Next executable brick

Roadmap v2 has **no remaining non-optional brick**. V2-02 is DONE via T-88 as
the measured negative `CANDIDATE_REJECTED_SAFETY`; V2-01 is DONE via T-85;
V2-04 is DONE via T-86/T-87 after strict acceptance of the original external
proof (SHA256
`819f3fcf445c051aec20864098960ccb37a69c8ce6aced0872f2198a96b95f94`)
against the frozen wheel (SHA256
`ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a`).
V2-03 stays optional and NOT STARTED. The next executable gate is selected in
`humbox/FUTURE-GATES-V3.md` (V3-01) and is NOT STARTED. No candidate rebuild,
support-scope expansion or publication belongs to this closure. STOP.

## 9. Restart / context-loss entry

A new agent recovers by reading, in this order:

1. `humbox/CURRENT-STATE.md` — where the project is and which roadmap is current.
2. `humbox/FUTURE-GATES-V2.md` (this file) — the current Roadmap v2.
3. `humbox/FUTURE-GATES.md` — completed Roadmap v1, historical evidence only.
4. `.saipen/STATE.md` and the current BOARD row and LOG tail.
5. `spec/15-LOCAL-SCENARIO-v0.md` and `spec/16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md`
   — the proven local baseline and its limitations.
6. `bench/ANALYSIS.md` — the preserved negative findings (T-9B, R1).

Recovery checklist: roadmap v2 is completed/superseded; the current roadmap is
v3 (`humbox/FUTURE-GATES-V3.md`); V2-01, V2-02 and V2-04 are DONE; V2-03 is
optional and NOT STARTED; V3-01 is selected next and NOT STARTED. Completed FG
and V2 gates must not be reopened; FG-01 is external debt, not a prerequisite.
Publication remains a separate operator action, never an agent default.

## 10. What not to claim

- Do not claim **universal utility**. The measured verdict is
  `UTILITY_CONDITIONAL`; moderate/high-open-rate and fallback-heavy workloads
  are neutral under the declared friction model, and token/frame overhead is
  real.
- Do not claim the **compact syntax** is the source of the workflow benefit;
  T-9B showed the frame is more expensive than equivalent prose per message.
- Do not claim **semantic reviewer reliability**; only reachability was reached,
  and the reviewer reply shape remains the observed blocker.
- Do not claim **provider JSON Schema enforcement** from one sample.
- Do not claim **live multi-user service readiness**, production
  Gmail/Slack/Outlook integration, hardware-key provisioning, automatic
  correspondence, automatic memory promotion, or zero protocol overhead.
- Do not claim **publication**. No release, tag, push or publication occurs in
  planning; publication is a separate explicit operator action.
