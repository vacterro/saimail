# Proposal — canonical mutation of a ticket's description

**Status: PROPOSED to SAIPEN Core. Not implemented there, and not worked
around from here.** Origin: `SRC-021` Target B1, ticket T-44 (the T-5 final
preflight).

## The defect class

A ticket's **description** (the BOARD title) has no canonical mutation. The
SAIOPS ticket surface of protocol 8.0.1 is `add | compact | verify | done |
retire | block | block-for | unblock`:

* `ticket verify <T-###> <text>` updates the `verify` field only;
* `ticket compact <T-###>` refuses a record already within the 1200-character
  cap and re-renders the same description when it runs;
* every other verb moves a ticket between sections, forwards a claim, or
  retires it.

Manual BOARD editing is forbidden (protected canonical state), so a ticket
whose descriptive title has become misleading cannot be corrected through the
protocol at all. It is repairable only by hand -- the exact bypass the
canonical surface exists to close.

The live instance: T-5's description still lists header-attention verdicts
`OPEN DEFER IGNORE PROMOTE`, while `DECISIONS.md` D-036, `spec/03-POST-OFFICE.md`
section 3/8 and T-5's own verify clause all state that `PROMOTE` is not a
header-scan verdict (promotion is post-open, payload-bound, D-035). T-44 could
re-issue the contract through `ticket verify` (canonical), but the stale
description text remains, because no canonical operation can rewrite it.

## PROTOCOL_CHANGE_PROPOSAL

Give a ticket's description the same canonical mutation its verify clause
already has, e.g.:

```
saipen ticket describe <T-###> <text>
```

(or `ticket verify <T-###> <text> --description`). It must be one journaled
SAIOPS operation like `ticket verify`: one LOG `DEC` line naming the ticket,
BOARD and STATE checkpointed together, redaction and escaping through the one
shared writer, and the record-cap policy unchanged.

History-preserving variant, preferred: write the corrected description as a
new version whose predecessor text stays readable (in the LOG event and/or the
record's detail authority), so a correction never erases what the ticket
actually said while it was being worked. The defect class this eliminates: a
ticket title that contradicts the spec it is governed by, with no protocol
path to repair it.

## EVIDENCE

Reproduced on 2026-09-18 against protocol 8.0.1 and this project's `.saipen/`:

1. T-5 description (verbatim from BOARD): "Post office layout and header-only
   scan: index.jsonl rows, interest filter verdicts OPEN DEFER IGNORE PROMOTE,
   declared scan and open budgets".
2. `saipen ticket compact T-5 --dry-run --json` -> refused:
   `VALIDATION_FAILED`, "T-5 is already within the 1200-character BOARD cap"
   (no text surface reached).
3. `saipen ticket verify T-5 --dry-run --json <text>` -> `TICKET_VERIFIED`,
   `changed_files: [.saipen/LOG.md, .saipen/BOARD.md, .saipen/STATE.md]` --
   the verify field changes, the description does not.
4. The full ticket verb list above is the CLI's own refusal text
   (`saipen ticket` with no action), so no hidden description verb exists.

T-44 handled the instance without a workaround: the contract was re-issued
through the canonical `ticket verify` mutation, the stale description was left
untouched, and this proposal plus a negative finding in the T-44 report carry
the residual gap to Core.
