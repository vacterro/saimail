# D1 — RELEASE DECISION PACKET v0

Status: working. Contract for `tools/release_decision.py`,
`release/evidence/release_decision_inputs.json`,
`release/evidence/release_decision.json`,
`release/evidence/RELEASE-DECISION.md` and `tests/test_release_decision.py`.
Decision: [D-054](DECISIONS-D054.md).

## 1. What this gate is

D1 compiles one authoritative, machine-readable release decision from the
current evidence: what artifact is actually proven, what the current source
checkout contains after that artifact was frozen, whether publication is GO or
NO-GO, which custody default the next distributable candidate must carry, what
version identity that candidate needs, and what the next executable gate is.

D1 does not publish. It adds no protocol semantics, no network path, no model
call, and it never mutates the frozen `0.0.2a1` bundle.

## 2. Decision inputs — `SAIMAIL_RELEASE_DECISION_INPUTS_1` v1

`tools/release_decision.py inputs` collects, mechanically:

* version identity for every surface (`VERSION` is the canonical authority, and
  agreement is measured, not assumed);
* artifact identity: recomputed wheel SHA-256 against the recorded manifest and
  checksum surfaces, plus the external proof's exact wheel binding;
* frozen capability: read from the wheel members themselves (custody module,
  identity schemas, CLI custody commands);
* checkout capability: read from the source tree;
* the post-candidate source delta and the external-evidence scope
  (`FROZEN_WHEEL_ONLY`).

## 3. Decision — `SAIMAIL_RELEASE_DECISION_1` v1

Closed outcome set: `READY_TO_PUBLISH_EXISTING_CANDIDATE`,
`NEW_CANDIDATE_REQUIRED`, `NO_GO_SECURITY`, `NO_GO_METADATA`, `NO_GO_EVIDENCE`,
`NO_GO_OTHER`.

The packet records the frozen artifact identity, the checkout delta, the version
decision, the custody default decision, support scope, a bounded claim matrix
(each claim proven/absent/not-proven per artifact identity), residual risks,
metadata status, the GO/NO-GO gates G1–G17, publication mechanics and the
publication authorization status.

## 4. Validation invariants

`tools/release_decision.py verify` recomputes the inputs and refuses a packet
that:

* cites a frozen hash that does not match the wheel bytes on disk;
* cites an external proof that does not bind that exact wheel;
* attributes a capability the wheel does not contain (for example `os-store`
  custody to a pre-V3-01 wheel);
* selects `READY_TO_PUBLISH_EXISTING_CANDIDATE` while the frozen wheel lacks a
  capability the packet claims for distribution;
* lets the next candidate version equal the frozen artifact version;
* leaves gaps in the claim matrix or the G1–G17 gate list.

## 5. Publication gating

`publication_allowed(packet, operator_authorization=None)` returns `False`
unless an explicit operator authorization exists and the packet outcome is
`READY_TO_PUBLISH_EXISTING_CANDIDATE`. Absent that, publication is forbidden
even when every engineering gate is green.

Publication mechanics are documented as five separated stages — local candidate
build, Git commit, Git tag, GitHub release, package-index upload — with the
repository's existing conventions recorded. No stage is executed by D1, and no
stage authenticates to any service.

## 6. What this does not claim

No publication, no push, no tag, no GitHub release, no package upload; no new
protocol semantics; no runtime default change; no external verification of the
current checkout; no mutation or rebuild of the frozen `0.0.2a1` candidate; no
repair of unrelated SAIPEN debt.
