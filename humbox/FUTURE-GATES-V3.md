# SAIMAIL: Roadmap v3 (POST-V2-02)

Updated: 2026-09-20. Authority: this file, for work after V2-02. It supersedes
`humbox/FUTURE-GATES-V2.md` as the *current* roadmap; v1 and v2 stay intact and
identifiable as completed historical planning evidence. This is a plan, not
permission to publish, to make a live model call, or to change any proven
contract.

Roadmap v2 is complete for its non-optional gates: V2-01 (persistent local
workspace) and V2-04 (scoped local alpha + external install proof) are DONE;
V2-02 (selector coverage) is DONE as a measured **negative** evidence gate; V2-03
(reviewer output format) stays optional research. Roadmap v3's first gate
V3-01 (local key-at-rest custody) is DONE via T-89: protected `os-store` custody
is implemented as an explicit opt-in, the threat model and decision are recorded
(D-053). D1 (release decision packet) is DONE via T-90 with outcome
`NEW_CANDIDATE_REQUIRED`; D2 (post-V3-01 release candidate refresh) executed via
T-91 and closed DONE via T-92 — the exact `0.0.2a2` wheel is frozen, locally
proven and externally proven in a genuinely separate Linux / Python 3.13.5
environment (G13 PASS). The candidate is `NOT_PUBLISHED` and publication
authorization (G17) is ABSENT. **P1 (local inbox triage/search) is DONE via
T-93** and **U1 (drift-safe coverage without new ignore authority) is DONE via
T-94** with outcome `COVERAGE_GAIN_WITH_EXTRA_OPENS`; no Work is active after
T-94. Roadmap v3's selected non-optional gates are therefore all DONE, so T-94
created `humbox/FUTURE-GATES-V4.md` as the new current roadmap authority and
selected exactly one next executable gate there (V4-01, NOT STARTED). This file
is now completed historical planning evidence.

## 1. Current proven baseline (unchanged from v2 unless stated)

- Deterministic local composition (FG-05), installable entrypoint and stable maps
  (FG-06), reproducibility discipline (spec/13), offline reference diagnostics
  (FG-04A), partial generative reachability (FG-04B), persistent workspace
  (V2-01), frozen `0.0.2a1` with external install proof (V2-04).
- **V2-02 result:** one receiver-owned `ignore_topics` change is rejected
  for safety (`CANDIDATE_REJECTED_SAFETY`). Static topic ignore reduces transport/header-policy fallback opens
  (246 -> 68 on the frozen fixtures) but loses two relevant `ci-ok` messages per
  direction under topic drift. `utility stays conditional`, and the selector
  lane's safe frontier is now bounded by that negative result.
- **D1 result (new):** `NEW_CANDIDATE_REQUIRED`. The frozen `0.0.2a1` wheel is
  `HISTORICAL_VERIFIED_ALPHA` only (no V3-01 custody inside it); the current
  checkout is `CURRENT_SOURCE_CAPABILITY`, not externally verified; next
  candidate `0.0.2a2`; custody default stays `raw` with `os-store` explicit
  (D-054); publication `NONE` and authorization `ABSENT`.
- **V3-01 result (new):** `OS_STORE_CUSTODY_IMPLEMENTED` (opt-in). Workspace
  identity custody is an explicit mode: `raw` (legacy/default) keeps the V2-01
  layout, `os-store` keeps the private keys in the checked OS credential store
  under `credential://saimail-workspace/...` and only handles plus public
  material in `identity/identity.json` (schema v2). Migration is explicit,
  transactional and fingerprint-preserving. Claim boundary: a copied workspace
  directory alone does not reveal the keys; same-user malware, admin/kernel
  compromise, human-identity proof, hardware isolation, physical presence and
  automatic recovery are NOT claimed (spec/20, D-053).

## 2. Current limitations

- **L1 — Local key custody is raw by default.** `saimail/workspace.py` stores
  the operator identity private keys as plaintext software keys unless the
  operator explicitly creates or migrates the workspace into `os-store`
  custody. The mechanism and the honest claim boundary now exist (V3-01);
  whether the distributed default should change is a release-decision question
  (D1). Raw remains the main remaining operator-facing risk for a default
  workspace.
- **L2 — Utility is conditional.** The measured win collapses toward neutral as
  open rate or fallback rate rises; V2-02 shows the obvious cheap fix is unsafe.
- **L3 — Reviewer reply shape blocks semantic review** (optional research).
- **L4 — Distribution is a decision, not a task.** D1 compiled the decision
  (T-90): the frozen candidate is `HISTORICAL_VERIFIED_ALPHA` only and
  `NOT_PUBLISHED`; a post-V3-01 candidate must be built and proven before any
  publication question, and publication itself remains an explicit operator
  action (G17).
- **L5 — SAIPEN/accounting debt is real and separate** (SRC-017/T-41, SRC-036,
  stale improve-report fingerprint, `SAIPEN_DIGEST_DRIFT`).

## 3. Priority principles

- Remove an observed gap; do not accumulate features.
- Prefer the smallest user-facing step that exercises proven protocol
  semantics.
- One intentional variable per experiment; retain a strict call ceiling.
- Conditional utility survives; no gate rewrites a measured negative.
- Independent work stays independent; SAIPEN debt never blocks SAIMAIL.
- Every gate needs a stop condition; a gate whose evidence says "stop" succeeds.

## 4. Lanes

### PRACTICAL PRODUCT LANE

- **P1 — Local inbox triage/search over the persistent workspace: DONE via
  T-93.** See section 8. Observed gap closed: V2-01 listed messages and opened
  them, but an operator had no bounded way to find a prior message without
  reading the whole inbox.

### UTILITY / SELECTOR LANE

- **Candidate U1 — Drift-safe coverage without new ignore authority.** Observed
  gap: V2-02 rejected static topic ignore; safe coverage must not rest on a
  sender-controlled label. Target: test one mechanism that raises attention
  (never lowers it), e.g. a receiver-owned bounded watch over sender-asserted
  relations. Not selected now: the utility lane is a research option, and the
  v2-02 negative result already bounds it; it does not block practical usefulness.
- **Constrained by evidence:** no static receiver topic ignore may be promoted;
  no friction/weight retune; no fixture tuning to make a candidate win.

### SECURITY / CUSTODY LANE

- **V3-01 — Local key-at-rest custody decision: DONE via T-89.** See section 5.
  The lane's next questions (hardware custody for this identity family,
  recovery/rotation policy) stay deferred until evidence demands them.

### DISTRIBUTION LANE

- **Candidate D1 — Release decision packet.** Observed gap: `NOT_PUBLISHED`
  local alpha with an accepted external proof and no compiled release decision.
  Target: assemble the decision inputs (what is proven, what is not, the
  custody risk, the support scope) so the operator can make a publication
  decision. Not selected now: publication is an explicit operator action and
  must follow, not precede, the custody decision.

### OPTIONAL RESEARCH LANE

- **V2-03 — Reviewer output-format bounded experiment.** Stays optional and NOT
  STARTED. It does not become a dependency of local product usefulness.

### DEFERRED LANES

- Remote adapters, hosted service, multi-user network transport, full GUI,
  hardware-key provisioning on the base path, autonomous correspondence,
  semantic cache. Deferred until current evidence gives a concrete reason.

## 5. Completed gate — V3-01 (DONE via T-89)

**V3-01 — Local key-at-rest custody decision.** Outcome
`OS_STORE_CUSTODY_IMPLEMENTED` (opt-in).

- **Recorded decision.** D-053 (`spec/DECISIONS-D053.md`): `os-store` custody
  selected; the existing credential-store architecture is reused under the
  separate `credential://saimail-workspace/...` namespace; no new cryptography.
- **Threat model.** `spec/20-LOCAL-KEY-CUSTODY-v0.md`, cases A–G, objective
  `WORKSPACE_DIRECTORY_COPY_ALONE_DOES_NOT_REVEAL_PRIVATE_IDENTITY_KEYS`, and
  the explicit not-claimed list (same-user malware, admin/kernel compromise,
  human-identity proof, hardware isolation, physical presence, forward
  secrecy, automatic recovery).
- **Implementation.** Identity schema v2 carries handles + public material
  only; `init --custody os-store`, `custody status`, `custody migrate`
  (transactional, fingerprint-preserving, idempotent); named `CUSTODY_*`
  failures that keep absence, backend failure and mismatch distinct; raw mode
  unchanged and explicitly labeled.
- **Evidence.** 28 focused tests with injected stores (no real-store writes in
  the suite), full suite 2175 passed, real `WinVaultKeyring` classification and
  one disposable real-vault smoke with verified cleanup, frozen `0.0.2a1`
  integrity PASS.
- **Explicit non-goals honored.** No wire-format change; no new protocol
  semantics; no hardware-key provisioning; no server/daemon/network transport;
  no change to the frozen bundle; no publication.
- **Residual risk.** Same-user malware; OS-account/host migration availability;
  backend as an operational dependency; **raw remains the default for new
  workspaces** until D1 decides otherwise.

## 6. Completed gate — D1 (DONE via T-90)

**D1 — Release decision packet.** Outcome `NEW_CANDIDATE_REQUIRED`.

- **Compiled decision.** `release/evidence/release_decision.json`
  (`SAIMAIL_RELEASE_DECISION_1` v1) with inputs
  `release/evidence/release_decision_inputs.json`
  (`SAIMAIL_RELEASE_DECISION_INPUTS_1` v1), human report
  `release/evidence/RELEASE-DECISION.md`, contract
  `spec/21-RELEASE-DECISION-v0.md`.
- **Frozen artifact.** `saimail-0.0.2a1-py3-none-any.whl`
  (`ed930e38…`) is mechanically verified to contain no `saimail/custody.py`,
  no identity schema v2 and no custody CLI surface; it is classified
  `HISTORICAL_VERIFIED_ALPHA`, and its external Linux / Python 3.13.5 proof
  binds exactly those bytes only. `POST_CANDIDATE_SOURCE_DELTA = V3-01`.
- **Custody default decision.** D-054: `KEEP_RAW_DEFAULT` for the next
  distributable candidate; `os-store` stays the explicit opt-in; D2 must carry
  the first-run custody warning and the second-platform re-evaluation trigger.
- **Version decision.** Frozen artifact `0.0.2a1`; `NEXT_CANDIDATE_VERSION =
  0.0.2a2`; source keeps declaring `0.0.2a1` until D2 owns the bump; artifact
  identity is the wheel SHA-256, never a version string (D-052).
- **Publication.** `publication = NONE`, `publication_authorization = ABSENT`;
  the five publication stages are documented as templates only, nothing was
  pushed, tagged, released or uploaded.
- **Explicit non-goals honored.** No publication; no mutation or rebuild of the
  frozen bundle; no new custody default implemented in D1; no D2 work started.

## 7. Completed gate — D2 (DONE via T-91 / T-92)

**D2 — Post-V3-01 release candidate refresh.**

- **Result.** `0.0.2a2` is frozen at `release/candidates/0.0.2a2/` (wheel
  `saimail-0.0.2a2-py3-none-any.whl`, SHA-256 `d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d`,
  59 members, `NOT_PUBLISHED`). The historical `0.0.2a1` bundle is unchanged
  and the tooling refuses to touch it. The D-054 first-run custody notice,
  the post-V3-01 release truth, the installed-wheel base verification, the
  installed-wheel Windows `WinVaultKeyring` os-store acceptance with verified
  vault cleanup, the injected-store migration proof, privacy/integrity red
  controls, reproducibility, the claim matrix and the G1–G17 evaluation are
  all recorded under `release/evidence/a2/` and `spec/DECISIONS-D055.md`.
  Suites: full 2205 passed / 0 failed / 0 errors / 0 skipped; SAIPEN core
  3 FAIL / 21 WARN inherited, no new candidate-attributable failure.
- **External proof (T-92 closure).** The supplied Linux / Python 3.13.5
  `LOCAL_ALPHA_VERIFICATION_1` v1 `PASS` for exactly that wheel is stored
  byte-identically at
  `release/evidence/a2/external_linux_verification.json` (SHA-256
  `2d77e13d…`), accepted by `release/evidence/a2/external_verification_record.json`
  and recorded in `gate_evaluation.json` as G13 PASS with terminal `DONE`.
  `claim_matrix.json` now carries `proven_externally_on_exact_a2_wheel`; the
  proof reports `os_store_platform_verification: NOT_TESTED_HERE`, so Linux
  os-store support is not claimed and the Windows `WinVaultKeyring` evidence
  stays the os-store platform authority. Publication remains forbidden
  (G17 ABSENT).

- **Observed gap.** The current checkout (with V3-01 custody) has no
  distributable artifact and no external proof of its own; the frozen `0.0.2a1`
  candidate cannot represent it.
- **Target.** Implement the D1 custody-default decision (keep raw default; add
  the first-run custody warning), assign `0.0.2a2`, build a NEW candidate,
  verify the exact new artifact locally, obtain external proof for that exact
  artifact, preserve the historical `0.0.2a1` evidence, and stop before
  publication.
- **Dependency.** D1 (DONE), V3-01 (DONE), V2-04 (DONE).
- **Gate set.** The D1 GO/NO-GO gates G1–G17 in
  `release/evidence/release_decision.json` apply to D2; G17 stays with the
  operator.
- **Do not start it in D1.**

## 8. Completed gate — P1 (DONE via T-93)

**P1 — Local inbox triage/search over the persistent workspace.**

- **Result.** A deterministic, bounded, metadata-only query over the canonical
  Post Office index; no new protocol semantics, no database, no new persisted
  index, no payload access, no state mutation. Contract
  `spec/22-LOCAL-INBOX-QUERY-v0.md`; implementation `saimail/inbox_query.py`,
  projection `saimail.workspace.query_inbox`, CLI
  `saimail-local inbox [filters]`.
- **Filters (exact, AND only).** Sender seat (`--from-seat`), topic, kind,
  state (`UNREAD`/`READ`/`EXPIRED`), ref, `--since` (inclusive) and `--before`
  (exclusive) over receiver-local `received_at`. No full-text, substring,
  regex, fuzzy, ranking, embedding or semantic search.
- **Bounds.** `--scan-budget` default 100, hard maximum 10000; a validated
  byte-offset `--cursor` resumes exactly after the last examined row. Abnormal
  lifecycle states stay fail-closed.
- **Isolation.** Implemented as its own module because the frozen V2-02 /
  FG-04B registrations hash-pin `saimail/postoffice.py`; P1 reuses that
  module's bounded streaming primitives and `bundle_state`, and never routes
  through `HeaderInterest`, attention merging or selector rules. A
  selector-ignored topic remains findable.
- **Proof.** Red-control poisoning proves no payload/open path is reached; the
  `mail/` tree is byte-identical before/after a query; legacy unfiltered
  `inbox` is unchanged; continuation pages are disjoint and complete;
  large-index work is bounded by the declared budget; multi-invocation
  acceptance proves restart stability. Full suite 2237/0/0/0; SAIPEN core
  3 FAIL / 21 WARN inherited only.
- **Source delta.** `POST_A2_SOURCE_DELTA = P1`. The frozen `0.0.2a2`
  (`d1f97537…`) and `0.0.2a1` (`ed930e38…`) wheels are byte-for-byte
  unchanged; publication = NONE, G17 ABSENT.

## 9. Completed gate — U1 (DONE via T-94)

**U1 — Drift-safe coverage without new ignore authority.** Outcome
`COVERAGE_GAIN_WITH_EXTRA_OPENS`.

- **Result.** One preregistered offline R1 selector experiment, both directions,
  testing exactly one receiver-owned variable, `Interest.watched`
  (`{}` -> `{WATCHED_TARGET}`), against frozen labelled fixtures. The
  pre-existing `R0-WATCHED` production rule is used unchanged. Measured (both
  directions): 18 relevant attention upgrades (14 relevant drift rescues), 24
  irrelevant attention upgrades, 0 downward attention changes, 0 new false
  ignores, 0 new missed relevant, 0 baseline required-open downgrades; extra
  cost 14 relation-spam opens + 10 noise-overlap opens.
- **Boundary.** The receiver owns what it watches; the sender may point at it;
  that pointer may raise attention and must never lower it. U1 can support
  **OPEN MORE**, never **IGNORE MORE**; a relation to a watched target does not
  prove relevance. U1 measures R1 attention coverage after a TriageView exists
  and is never compared to the V2-02 transport/header fallback numbers.
- **Provider.** `spec/23-DRIFT-SAFE-WATCHED-COVERAGE-v0.md`;
  `lab/watched_coverage_registration.json`,
  `lab/watched_coverage_manifest.json` (EXPERIMENT-MANIFEST-1, `HISTORICAL_ONLY`),
  `lab/watched_coverage.py`, `tools/watched_coverage_experiment.py`,
  `lab/watched_coverage_fixtures.json`, `lab/history/u1-watched-coverage/`,
  `tests/test_watched_coverage.py`, `lab/analysis/u1_watched_coverage_closure.md`,
  `lab/out/U1_WATCHED_COVERAGE_20260920T211411Z/`.
- **Source delta.** `POST_A2_PRODUCT_DELTA = P1`;
  `POST_A2_RESEARCH_EVIDENCE = U1`. `publication = NONE`, G17 ABSENT; frozen
  `0.0.2a2` (`d1f97537…`) and `0.0.2a1` (`ed930e38…`) unchanged and not rebuilt.
- **Suites.** Full canonical suite 2264/0/0/0; SAIPEN core 3 FAIL / 21 WARN
  inherited only.

## 10. Dependencies

```
V3-01  <- V2-01 (DONE)                                   [DONE via T-89]
V2-03  <- FG-04A, FG-04B (DONE); optional; new registration
P1     <- V2-01 (DONE)                                   [DONE via T-93]
D1     <- V3-01 (DONE), V2-04 (DONE)                     [DONE via T-90]
D2     <- D1 (DONE), V3-01 (DONE)                        [DONE via T-91/T-92]
U1     <- V2-02 (DONE); selected next, NOT STARTED   [DONE via T-94]
```

- V2-03 does not block D2 or any practical gate.
- D2 does not block V2-03.
- SAIPEN debt (FG-01 / SRC-017/T-41, SRC-036, improve-report fingerprint,
  `SAIPEN_DIGEST_DRIFT`) is not a dependency of any V3 gate.

## 11. Next executable brick

**V3 has no remaining selected non-optional gate.** U1 — the last one — is DONE
via T-94 (`COVERAGE_GAIN_WITH_EXTRA_OPENS`); P1 is DONE and `POST_A2_SOURCE_DELTA
= P1`; D2 stays `NOT_PUBLISHED` (G17 ABSENT); V2-03 remains optional research.
T-94 created `humbox/FUTURE-GATES-V4.md` as the current roadmap authority and
selected exactly one next executable gate there (**V4-01**, NOT STARTED).

## 12. What not to claim

- Do not claim universal utility (`UTILITY_CONDITIONAL` stands).
- Do not claim the compact syntax is the source of the workflow benefit (T-9B).
- Do not claim semantic reviewer reliability.
- Do not claim static topic ignore is safe to promote (V2-02 rejected it).
- Do not claim live multi-user service readiness, provider integration,
  hardware-key provisioning, automatic correspondence, or zero protocol
  overhead.
- Do not claim the default workspace identity is protected: `raw` remains the
  default for new workspaces; `os-store` is an explicit opt-in (D-053).
- Do not claim protection against same-user malware, admin/kernel compromise,
  human-identity proof, hardware isolation, physical presence, forward secrecy
  or automatic recovery (spec/20).
- Do not claim publication.
- Do not claim the current checkout is externally verified because `0.0.2a1`
  was (D1 evidence boundary). The `0.0.2a2` wheel is externally verified as
  that exact wheel only.
- Do not claim Linux os-store support: the external proof reports
  `os_store_platform_verification: NOT_TESTED_HERE`; the Windows installed-wheel
  `WinVaultKeyring` evidence stays the platform-specific authority.
- Do not claim `os-store` is the distributed default: raw remains the default
  for new workspaces (D-053 / D-054).

## 13. Restart / context-loss entry

1. `humbox/CURRENT-STATE.md` — where the project is and which roadmap is current.
2. `humbox/FUTURE-GATES-V4.md` — the current roadmap authority.
3. `humbox/FUTURE-GATES-V3.md` (this file) — completed Roadmap v3 (historical).
4. `humbox/FUTURE-GATES-V2.md` — completed Roadmap v2 (historical evidence).
5. `humbox/FUTURE-GATES.md` — completed Roadmap v1 (historical evidence).
6. `.saipen/STATE.md`, the current BOARD row and the LOG tail.
7. `lab/analysis/u1_watched_coverage_closure.md` — the U1 result.
8. `lab/analysis/v202_selector_coverage_closure.md` — the V2-02 negative result.
9. `spec/20-LOCAL-KEY-CUSTODY-v0.md` — the V3-01 custody contract and limits.
10. `release/evidence/RELEASE-DECISION.md` and `spec/DECISIONS-D054.md` — the D1
   release decision, custody default and next-candidate identity.
11. `release/evidence/a2/gate_evaluation.json`,
   `release/evidence/a2/external_verification_record.json`,
   `spec/DECISIONS-D055.md` and the D2 section of `humbox/CURRENT-STATE.md` —
   the exact `0.0.2a2` candidate, its evidence set and the G13 external proof
   (terminal `DONE`).

Recovery checklist: Roadmap v3 is completed (V2-01, V2-02, V2-04, V3-01, D1,
**D2**, **P1** and **U1** are DONE; D1 outcome `NEW_CANDIDATE_REQUIRED`; D2
closed via T-92 with the exact `0.0.2a2` wheel externally proven, G13 PASS; P1
DONE via T-93; U1 DONE via T-94, `COVERAGE_GAIN_WITH_EXTRA_OPENS`); V2-03 is
optional and NOT STARTED. The current roadmap authority is
`humbox/FUTURE-GATES-V4.md`; **V4-01 is the selected next executable gate, NOT
STARTED**. Completed gates must not be reopened. The frozen `0.0.2a1` candidate
is historical and immutable; the `0.0.2a2` candidate is frozen, externally
proven and `NOT_PUBLISHED`. Publication remains a separate operator action (G17
ABSENT).
