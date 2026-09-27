# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-064 — every operator workshop rule is bound to a mechanism and a named live control (T-118)

The defect class is a policy that nothing enforces, or whose enforcing test can be
deleted without anyone noticing. The operator recorded the SAIMAIL inter-agent
workshop policy (SRC-107) "for the future"; after the SRC-108 wave the mechanisms
it asks for exist.

**Decision.** `spec/32-INTER-AGENT-WORKSHOP-POLICY-v0.md` maps each rule to its
SAIMAIL mechanism and to one named control (`tests/<file>::<test>`), or marks it
SAIPEN-SIDE with the wave gate that carries it. The repository consistency suite
parses the map: every ENFORCED row's control must exist, every SAIPEN-SIDE row's
gate must be in the Roadmap v6 §16 table, and no SAIMAIL state set may contain
`ACTED` (a message state never implies an action).

**Boundary.** No product code change. Rules D3 (SAIMAIL never a global SAIPEN
requirement) and O1 (no manual invocation in normal operation) need the SAIPEN
halves of V6-07/V6-08. Checkout-only.

**Evidence.** `tests/test_repo_consistency.py::test_workshop_policy_is_mapped_to_live_controls`
and its red controls (a renamed control, a dropped gate and an injected `ACTED`
state each turn it red; `.saipen/evidence/T-118-policy/`).
