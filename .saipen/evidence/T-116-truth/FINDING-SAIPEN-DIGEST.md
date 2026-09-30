# Cross-project finding: SAIPEN digest projects an ephemeral active task

Found by SAIMAIL T-116 (Milestone F). Owner: SAIPEN Core. Not patched from
SAIMAIL.

## Observation

`.saipen/kitchen/digest.md` at T-116 claim (E-1544):

    done: stopped via SAIOPS checkpoint
    remaining: T-107
    awaiting: nothing

T-107 finished at E-1502; STATE was DONE / task none at E-1541 and later
claimed T-116. CURRENT-STATE already recorded the same drift during T-79
(`remaining: T-78`).

## Mechanism (read-only inspection of SAIPEN home)

`tools/saipen_engine/operations.py::stop_checkpoint` writes
`remaining: {task or blocker or "see BOARD"}` into digest.md. The comment near
the release closure says ordinary `ticket done` "passes no digest and stays
LOG+BOARD+STATE only". A stop taken while a ticket is active therefore leaves
that ticket in the digest after `saipen finish` closes it.

## Class

Same defect class as SAIMAIL T-116: a durable projection binds current
continuation to an ephemeral active-ticket identity and becomes false at
close time.

## Suggested SAIPEN future gate (not implemented)

Either refresh/clear the digest on ticket completion, or stamp the digest with
the event it was projected at (for example `as_of: E-1485`) and treat it as
non-authoritative when STATE.last_event is later. SAIMAIL recovery docs treat
STATE/BOARD/LOG as the only lifecycle authority in the meantime.
