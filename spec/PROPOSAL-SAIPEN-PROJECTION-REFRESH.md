# Proposal — canonical refresh for human-facing SAIPEN projections

**Status: PROPOSED to SAIPEN Core. Not implemented there, and not worked
around from here.** Origin: `SRC-023`, ticket T-46 (the T-5 corrective
correctness close); the same class was earlier noted for ticket descriptions
(`PROPOSAL-SAIPEN-TICKET-DESCRIPTION-MUTATION.md`).

## The defect class

A human-facing projection of canonical state has no canonical refresh path.
`BOARD.md`, `STATE.md` and `LOG.md` are machine state and are mutated only
through SAIOPS; projections that summarise them (`.saipen/kitchen/digest.md`,
a ticket's blocker prose once the blocker has been superseded) are ordinary
documents with no owning producer. When canonical facts move, a projection can
keep asserting a superseded world with nothing able to repair it:

* `.saipen/kitchen/digest.md` still states that T-5 is "resumed at SCOUT,
  unblocked, not implemented" and that "next act is T-5 implementation", while
  T-5 closed under `SRC-022` and its correctness closure T-46 is complete.
* The T-34 blocker text still says "T-5 Post Office and T-7 TTL sweep
  intentionally unstarted" and names the T-5 attention-floor decision as the
  next act; `B-014` was decided by D-036 and T-5 is done.

Manual editing of projections is not a repair: BLOCKED/STATE/LOG may not be
hand-edited, and rewriting a historical blocker sentence would forge the record
of what was true while the ticket was worked. Neither editing path is
acceptable, and no third path exists.

Reproduced on 2026-09-19 against protocol 8.0.1 and this project's `.saipen/`:

1. `saipen --help` command surface: `context cold|hot|audit|orient`, `brief`,
   `focus` render projections; no verb writes `kitchen/digest.md` or any other
   human-facing projection.
2. `saipen context hot --dry-run --json` -> `CONTEXT_HOT`,
   `changed_files: []` — the hot projection is rendered, never persisted.
3. `saipen brief --dry-run --json` -> an ephemeral JSON projection with no
   `changed_files`; it does not rewrite `kitchen/`.
4. The stale text above is present verbatim in the files named, and no
   canonical operation exists to update it; T-46 deliberately left it in
   place rather than hand-edit or forge.

## PROTOCOL_CHANGE_PROPOSAL

1. Give human-facing projections an owning producer and a refresh operation
   (for example `saipen context refresh`), so a projection is a generated view
   over BOARD/STATE/LOG rather than a hand-maintained document, journaled like
   every other SAIOPS mutation (one `DEC` line, BOARD and STATE checkpointed
   together).
2. If no operation is adopted, mark projection files as generated or ephemeral
   with a header naming their producer and last generation event, so staleness
   is mechanically detectable instead of trusted.
3. Keep the existing prohibitions: never repair a stale projection by editing
   BOARD/STATE/LOG, and never rewrite historical blocker text; a stale
   projection is refreshed or superseded, not forged.

The defect class this eliminates: a projection that contradicts the canonical
record it summarises, with no protocol path to reconcile it and no way for a
reader to detect the contradiction mechanically.

## Scope

Protocol change proposal for the SAIPEN installation; this repository records
the finding only. No code, BOARD, STATE or LOG change is part of this file.
