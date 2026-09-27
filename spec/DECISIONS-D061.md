# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-061 — automation routes only to explicitly admitted, identity-pinned project participants (T-120)

The defect class is an automatic sender that guesses its recipient. `peers.json`
maps aliases to mailboxes but says nothing about project membership, so automatic
routing could only pick a mailbox by name or convention.

**Decision.** The acting workspace keeps a project-local participant registry
(`spec/29-PARTICIPANT-REGISTRY-v0.md`): per SAIPEN project lineage, explicitly
admitted seats, each bound to a registered alias with its identity pinned and the
notify triggers it may receive. Resolution refuses rather than guesses: unknown
project or seat, trigger outside the admission, self-address, or identity drift.

- **Closed trigger set** (`blocker`, `finding`, `dependency`, `ownership`,
  `handoff`, `reply`) with a fixed existing SENV2 kind each. No new wire kind, no
  sender priority.
- **No discovery, no global registry.** Admission is local and explicit.
- **Receiver-owned trust unchanged.** Admission is the sender's routing choice;
  the receiver still quarantines a sender it did not register.
- **Project identity from the admitted binding,** never from a free-text argument.
- **Keyless.** Registry operations run on the D-059 header view.

**Boundary.** No change to peers, delivery, the wire or SAIPEN. Checkout-only;
the frozen `0.0.2a3` wheel does not contain it.

**Evidence.** `tests/test_participants.py` (12 controls); red controls in
`.saipen/evidence/T-120-registry/red-controls.txt` (five source mutants caught).
