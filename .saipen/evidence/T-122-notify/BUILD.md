# T-122 BUILD: V6-08 SAIMAIL half, automatic notify (SRC-108 item 2, SRC-107 policy)

Defect class eliminated: cross-boundary information waiting for a human relay,
without turning the sender into a guessing, repeating, self-prioritizing chatterbox.

- New `saimail/notify.py`: closed-trigger notify through the participant registry,
  Work from STATE or a BOARD-listed id, deterministic key per fact (citation bound
  to event + EV), durable outbox, receiver budget gate (20/hour per recipient,
  5/hour per recipient and Work) under the outbox lock, suppression writes nothing,
  piggybacked `resume_outbox`.
- `saimail/outbox.py` (diff): `content_identity` for the request digest; `gate`
  run under the lock before a new intent; PENDING recorded without sealing when no
  signing key is loaded (no exception after the durable write).
- `saimail/capabilities.py` (diff): `notify` capability entry, budget from the
  notify constants.
- `saimail_local.py` (diff): `saipen notify`; full load with a custody fallback
  to the header view; `board` path in the project map.
- `saimail/workspace.py` (diff): renderer line.
- Tests: `tests/test_notify.py` (10); `tests/test_capabilities.py` expects the new
  `notify` entry (verifier change, recorded); V6-08 oracle (additive).
- Red controls: six source mutants caught; the sender-chosen-kind mutant first
  survived a control that read the reported kind instead of the wire kind; the
  control now checks the receiver index.
- Docs: spec/31, D-063, spec/26 §6 update, roadmap row + subsection + wave
  position, CURRENT-STATE, Work Desk guide, CHANGELOG, API map (3 APIs, local_notify).
