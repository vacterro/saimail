# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-062 — SAIPEN negotiates the mail channel through one never-failing, keyless, seat-checked capability document (T-121)

The defect class is an orchestrator that learns whether a dependency works only
by calling it and parsing a failure. SAIPEN's turn-entry read got counts or an
exit code; it could not distinguish a wrong seat, a missing mailbox, a stuck
outbox or an incompatible build, and it showed counts for any mailbox it was
pointed at.

**Decision.** `saimail-local saipen capabilities` returns
`SAIMAIL_CAPABILITIES_1` (`spec/30-SAIPEN-CAPABILITIES-v0.md`) with exit code 0
for every state: API versions, seat binding, workspace health, per-capability
states in SAIOPP terms (AVAILABLE, DEGRADED, REQUIRES_HUMAN, UNAVAILABLE,
UNVERIFIED), outbox health, awareness counts and closed reason codes.

- **Seat-checked.** A mismatched seat gets `UNAVAILABLE` with no counts, ids or
  topics.
- **Keyless and plaintext-free.** Signing is reported `UNVERIFIED` rather than
  checked, because checking would read a private key.
- **Degrade, never break.** Missing project, no participants, outbox backlog or
  failures, and corrupt stores are named states; the caller keeps working.

**Boundary.** Additive; `saipen telegrams` stays for compatibility. The SAIPEN
half (registering SAIMAIL as an S4 extension and consuming this document) is
SAIPEN-project Work. Checkout-only; the frozen `0.0.2a3` wheel does not contain
it.

**Evidence.** `tests/test_capabilities.py` (10 controls); six source mutants
caught (`.saipen/evidence/T-121-capabilities/red-controls.txt`).
