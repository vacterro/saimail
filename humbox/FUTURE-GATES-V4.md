# SAIMAIL: Roadmap v4 (POST-U1)

Updated: 2026-09-20. Authority: this file, for work after U1. It supersedes
`humbox/FUTURE-GATES-V3.md` as the *current* roadmap; v1, v2 and v3 stay intact
and identifiable as completed historical planning evidence. This is a plan, not
permission to publish, to make a live model call, or to change any proven
contract.

Roadmap v3 is complete for its selected non-optional gates: V3-01, D1, D2, P1
and U1 are DONE. U1 is DONE via T-94 with terminal outcome
`COVERAGE_GAIN_WITH_EXTRA_OPENS`: a receiver-owned watched canonical target safely
raises R1 attention under vocabulary/topic drift, at the cost of measurable
sender-caused extra opens. **V4-01 is DONE via T-95**: one explicit local `reply`
continues an already-opened message through the existing SENV2 `REF` and the
unchanged seal/deliver path. **V2-03 is DONE via T-96** with the measured
negative `REVIEWER_BAD_JSON`. No Work is active after T-96.

## 1. Current proven baseline

- Deterministic local composition (FG-05), installable entrypoint and stable maps
  (FG-06), reproducibility discipline (spec/13), offline reference diagnostics
  (FG-04A), partial generative reachability (FG-04B), persistent workspace
  (V2-01), scoped local alpha `0.0.2a1` with external install proof (V2-04).
- **V3-01:** `OS_STORE_CUSTODY_IMPLEMENTED` (opt-in); raw remains the default for
  new workspaces (D-053/D-054); a copied workspace directory alone does not
  reveal the private identity keys.
- **D1 / D2:** the exact `0.0.2a2` wheel is frozen, locally proven and externally
  proven in a separate Linux / Python 3.13.5 environment (G13 PASS);
  `NOT_PUBLISHED`; G17 authorization ABSENT.
- **P1:** a deterministic, bounded, metadata-only inbox query over the canonical
  Post Office index (`saimail-local inbox [filters]`), no payload access and no
  new persisted index.
- **U1:** one receiver-owned R1 selector variable, `Interest.watched`, yields 18
  relevant attention upgrades (14 relevant drift rescues) with 0 downward
  attention changes, 0 false ignores, 0 missed relevant messages and 0
  required-open downgrades, at a cost of 24 irrelevant attention upgrades
  (14 relation-spam, 10 noise-overlap). The selector lane's safe frontier is
  **conservative escalation, not suppression** (bounded by the V2-02
  `CANDIDATE_REJECTED_SAFETY` negative).
- **V4-01:** one explicit local `reply` continues an already-`READ` message with
  an ordinary canonical record sealed through the unchanged SENV2 path and
  `REF = original ENVELOPE_ID`; the original sender discovers it through the
  existing `inbox --ref` metadata query. No new wire field, no thread store and
  no invented semantic relation.

## 2. Current limitations

- **L1 — Local key custody is raw by default.** `os-store` is an explicit
  opt-in; changing the distributed default stays a release-decision question.
- **L2 — Utility is conditional.** The measured win collapses toward neutral as
  open rate or fallback rate rises; V2-02 shows the cheap suppression fix is
  unsafe.
- **L3 — Reviewer reply shape blocks semantic review (T-96 measured negative).**
  Under the registered reviewer `JSON_SCHEMA` request the reached reviewer still
  returned a non-strict-JSON reply (`REVIEWER_BAD_JSON`, 4178 bytes); one bounded
  sample could not reach a parseable semantic reviewer report. Reliability is
  unproven and generative research stays optional/deferred.
- **L4 — Distribution is a decision, not a task.** `0.0.2a2` is technically
  verified and `NOT_PUBLISHED`; the current checkout is ahead by the P1 product
  delta with U1 as additional research evidence. Publication is an explicit
  operator action (G17).
- **L5 — Correspondence continuation is one-hop only (V4-01 DONE).** The local
  surface (`init`, `identity`, `recipient`, `send`, `inbox`, `open`, `reply`,
  `custody`, `acceptance`) can find, open and answer a message; `reply` links a
  response to the message it answers through the existing SENV2 `REF`. There is
  no thread store and no recursive chain traversal: a longer correspondence is
  followed one explicit `REF` hop at a time.
- **L6 — SAIPEN/accounting debt is real and separate** (SRC-017/T-41, SRC-036,
  stale improve-report fingerprint, `SAIPEN_DIGEST_DRIFT`).

## 3. Priority principles

- Remove an observed gap; do not accumulate features.
- Prefer the smallest user-facing step that exercises proven protocol semantics.
- One intentional variable per experiment; retain a strict call ceiling.
- Conditional utility survives; no gate rewrites a measured negative.
- Independent work stays independent; SAIPEN debt never blocks SAIMAIL.
- Every gate needs a stop condition; a gate whose evidence says "stop" succeeds.
- Do not create a gate merely to tune an already-measured cost.

## 4. Lanes

### PRACTICAL PRODUCT LANE

- **V4-01 — Local correspondence continuation: DONE via T-95.** See section 8.

### UTILITY / SELECTOR LANE

- U1 establishes that a receiver-owned watched set is a safe **attention
  escalation** hint and that sender-asserted relations to a watched target cost
  measurable extra opens. **Do not immediately create U2 just to tune the
  extra-open count.** A future candidate (recorded here but not selected) is an
  explicit operator-declared watch surface in the local workspace; it must never
  infer watched targets from traffic, allow a sender to own the watch list, or
  create any ignore authority.
- **Constrained by evidence:** no static receiver topic ignore may be promoted;
  no friction/weight retune; no fixture tuning to make a candidate win; no
  relation-to-watched target may ever be treated as relevance truth.

### SECURITY / CUSTODY LANE

- V3-01 is DONE. **Do not reopen custody unless new evidence requires it.**
  Hardware custody, recovery and rotation policy stay deferred.

### DISTRIBUTION LANE

- `0.0.2a2` remains technically verified and `NOT_PUBLISHED`; the product source
  is ahead by P1. G17 remains operator-owned. **Do not create a publication task
  without operator authorization.**

### OPTIONAL RESEARCH LANE

- **V2-03 — Reviewer output-format bounded experiment: DONE via T-96.** One
  registered bounded live experiment changed exactly one variable (reviewer
  `response_format` ABSENT -> `JSON_SCHEMA`) and closed with the measured
  negative `REVIEWER_BAD_JSON`: the reviewer carried the registered schema and
  still did not return one strict JSON document. It never became a dependency of
  local product usefulness. No generative-advice production work is created.

### DEFERRED LANES

- Remote adapters, hosted service, multi-user network transport, full GUI,
  hardware-key provisioning on the base path, autonomous correspondence,
  semantic cache. Deferred until current evidence gives a concrete reason.

## 5. Dependencies

```
V4-01  <- V2-01 (DONE), P1 (DONE)                 [DONE via T-95]
V2-03  <- FG-04A, FG-04B (DONE)                   [DONE via T-96, REVIEWER_BAD_JSON]
U2     <- U1 (DONE); NOT selected, not created
```

- SAIPEN debt (FG-01 / SRC-017/T-41, SRC-036, improve-report fingerprint,
  `SAIPEN_DIGEST_DRIFT`) is not a dependency of any V4 gate.

## 6. Next executable brick

**No new gate is selected.** V4-01 (local correspondence continuation) is DONE
via T-95 and closed the observed product gap: P1 closes "find a message", V2-01
closes "send and open", and V4-01 closes "answer what was found". V2-03 (reviewer
output-format bounded experiment) is DONE via T-96 as the measured negative
`REVIEWER_BAD_JSON`; it was optional research and never a product dependency.
Re-evaluating Roadmap v4 from evidence finds no new practical gap that justifies
a new gate, so the roadmap truthfully ends with **NO SELECTED NEXT GATE**. U2 /
operator-declared watched targets are not created. Publication remains an
operator decision (G17). No v5 is created.

## 7. What not to claim

- Do not claim universal utility (`UTILITY_CONDITIONAL` stands).
- Do not claim the compact syntax is the source of the workflow benefit (T-9B).
- Do not claim semantic reviewer reliability.
- Do not claim static topic ignore is safe to promote (V2-02 rejected it).
- Do not claim a relation to a watched target proves relevance (U1 measured it as
  an attention hint only); do not claim `Interest.watched` reduces opens or
  creates ignore authority.
- Do not claim live multi-user service readiness, provider integration,
  hardware-key provisioning, automatic correspondence, or zero protocol
  overhead.
- Do not claim the default workspace identity is protected: `raw` remains the
  default; `os-store` is an explicit opt-in (D-053).
- Do not claim protection against same-user malware, admin/kernel compromise,
  human-identity proof, hardware isolation, physical presence, forward secrecy
  or automatic recovery (spec/20).
- Do not claim publication; do not claim the current checkout is externally
  verified because `0.0.2a2` was (that proof binds those exact bytes only).
- Do not claim Linux os-store support (`os_store_platform_verification:
  NOT_TESTED_HERE`); the Windows `WinVaultKeyring` evidence stays the
  platform-specific authority.
- Do not claim `os-store` is the distributed default (D-053 / D-054).

## 8. V4-01 — Local correspondence continuation (SPECIFICATION)

**Status: DONE via T-95.** Contract `spec/24-LOCAL-CORRESPONDENCE-CONTINUATION-v0.md`;
focused tests `tests/test_local_correspondence.py` and
`tests/test_local_correspondence_acceptance.py`.

- **Observed gap.** The shipped local surface (`saimail-local init/identity/
  recipient/send/inbox/open/custody/acceptance`) can find a prior message (P1)
  and open it, but a response was an unrelated fresh send with no linkage to the
  message it answers. The original sender therefore could not reliably discover
  the response as a continuation of that message through the existing metadata
  query filters.
- **Target.** One bounded local command that continues a received message: the
  target message must already have been explicitly opened; construct an ordinary
  canonical reply record and set the existing SENV2 header `REF` field to the
  original **ENVELOPE_ID**, then send it through the unchanged seal/deliver path
  — and prove the counterparty can discover the reply with the existing `inbox
  --ref <original envelope id>` filter.
- **Relation domain (corrected contract).** Correspondence and truth are
  different graphs. SENV2 `REF` is a *transport/correspondence* relation: "this
  message responds to that prior envelope." SAILANG `SUPPORTS` / `REFUTES` /
  `CON` are *semantic* relations between immutable statements. A reply is
  therefore linked with SENV2 `REF = ORIGINAL_ENVELOPE_ID`, never by inventing a
  semantic relation: `REPLY != SUPPORTS`, `REPLY != REFUTES`, `REPLY != CON`. A
  reply carries one of those semantic fields only when the operator supplies a
  canonical record that explicitly says so.
- **Why now.** P1 and V2-01 are DONE and the local product is otherwise a
  read-only inbox with a fire-and-forget send. This is the smallest user-facing
  step that exercises already-proven protocol semantics (explicit open, record
  relation fields, canonical send, metadata query) without new concepts.
- **Dependency.** V2-01 (DONE), P1 (DONE).
- **Acceptance evidence.** Focused tests plus the offline two-workspace
  acceptance harness: the reply is an explicit operator action; the target
  message must already be READ through the unchanged explicit-open path; the
  reply sets SENV2 `REF` to the original `ENVELOPE_ID` (no invented semantic
  relation) and a receiver can find it via `inbox --ref`; restart and duplicate
  suppression hold; no payload is read except through the explicit open; the envelope wire
  format, the selector, attention and the Post Office are unchanged; the frozen
  `0.0.2a2` candidate and all a1/a2 evidence stay byte-for-byte untouched; zero
  network/model calls.
- **Non-goals.** No automatic correspondence, no sender-owned linkage, no
  threading store, no new persisted index, no database, no new wire semantics,
  no GUI, no network transport, no change to selector/attention/ignore
  authority, no version bump, no rebuild, no publication.
- **Stop condition.** If the linked reply is discoverable by the unchanged
  metadata query with no new ignore/attention authority and no new wire
  semantics, V4-01 is DONE and evidence is recorded. If it cannot be built
  without new wire semantics, V4-01 closes as negative evidence and no
  protocol change is smuggled in.
- **Outcome (T-95).** `DONE` — positive. The linked reply is discoverable by the
  unchanged `inbox --ref` metadata query with no new wire semantics; the target
  must already be `READ`; the reply never re-decrypts the target; the reply
  recipient is bound to the original sender identity; and no SAILANG semantic
  relation is invented (`REPLY != SUPPORTS/REFUTES/CON`).
- **Negative evidence closes it:** yes. A measured negative is a successful
  research closure.

## 8b. V2-03 — Reviewer output-format bounded experiment (DONE)

**Status: DONE via T-96 (`REVIEWER_BAD_JSON`).** Contract carried by the existing
`spec/09-ALLY-GENERATION-v0.md` parser and the FG-04B registration discipline;
new artifacts `lab/reviewer_structured_output_registration.json`,
`lab/reviewer_structured_output_schema.json`,
`lab/reviewer_structured_output_manifest.json`, `lab/reviewer_structured_output.py`,
`tests/test_reviewer_structured_output.py`.

- **Observed gap (L3).** The reviewer path was reachable but its reply was not
  one parseable strict JSON document.
- **Single variable.** Reviewer `response_format` ABSENT -> `JSON_SCHEMA`;
  generator route/format/schema, reviewer route, roles, corpus, prompts, rubric,
  budgets, gates, parser and retry/repair/replacement/fallback policy all frozen.
- **Outcome (T-96).** The reviewer was reached with the registered reviewer
  `json_schema` (`response_format_sha256` `91a32e66…`, request body 35907 bytes)
  and still returned a non-strict-JSON reply (4178 bytes, `ALLY_LAB_BAD_JSON`);
  class `REVIEWER_BAD_JSON`, zero semantic verdicts. R2 `NO_ADVICE`. 5/6 calls;
  retries/repairs/replacements/fallbacks 0; admission before the first network
  call.
- **Claim boundary.** One registered reviewer invocation did not produce a
  parseable product-valid report. No reliability, correctness, enforcement or
  readiness is claimed. `REQUEST SENT WITH SCHEMA != PROVIDER ENFORCED SCHEMA`.
- **Negative evidence closes it:** yes. A measured negative is a successful
  research closure.

## 9. Restart / context-loss entry

1. `humbox/CURRENT-STATE.md` — where the project is and which roadmap is current.
2. `humbox/FUTURE-GATES-V4.md` (this file) — the current roadmap authority.
3. `humbox/FUTURE-GATES-V3.md` — completed Roadmap v3 (historical evidence).
4. `humbox/FUTURE-GATES-V2.md` — completed Roadmap v2 (historical evidence).
5. `humbox/FUTURE-GATES.md` — completed Roadmap v1 (historical evidence).
6. `.saipen/STATE.md`, the current BOARD row and the LOG tail.
7. `lab/analysis/u1_watched_coverage_closure.md` — the U1 result.
8. `lab/analysis/v202_selector_coverage_closure.md` — the V2-02 negative result.
9. `lab/analysis/reviewer_structured_output_closure.md` — the V2-03 negative.
10. `spec/20-LOCAL-KEY-CUSTODY-v0.md`,
    `release/evidence/RELEASE-DECISION.md`, `spec/DECISIONS-D054.md` and
    `release/evidence/a2/gate_evaluation.json` — the custody and release truth.

Recovery checklist: current roadmap is v4; V2-01, V2-02, V2-03, V2-04, V3-01,
D1, D2, P1, U1 and V4-01 are DONE; no gate is selected after V4-01. Completed
gates must not be reopened. The frozen `0.0.2a2`
candidate is externally proven and `NOT_PUBLISHED`; the frozen `0.0.2a1`
candidate is historical and immutable. Publication remains a separate operator
action (G17 ABSENT).
