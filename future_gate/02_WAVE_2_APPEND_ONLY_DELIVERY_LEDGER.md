SAIMAIL

SAIHANDOFF — FUTURE GATE WAVE 2
APPEND-ONLY DELIVERY LEDGER + RECONSTRUCTABLE STATE

STATUS
FUTURE GATE. Depends on Wave 1.

INSPIRATION
AIPass ai_mail writes the dispatch promise before spawn, appends completion later, and reconstructs current state by folding events. Missing state and unreadable state are deliberately different answers.

GOAL
Make SAIMAIL delivery state reconstructable after crashes without trusting mutable projections as the only truth.

EVENTS
CREATED, SEALED, OUTBOX_COMMITTED, DELIVERY_ATTEMPTED, DELIVERED, RECEIPT_OBSERVED, OPENED, REPLIED, FAILED, QUARANTINED, SUPERSEDED/DUPLICATE as justified.

BUILD
- Append-only event records with stable message/envelope id, actor, timestamp, schema version, causal/attempt id.
- Fold/reconstruct function where later valid events determine current state.
- Invalid transitions detected, duplicates idempotent.
- Persist intent before external delivery side effects where appropriate.
- Completion evidence written durably before operation claims/locks are released.
- Absent ledger means no history; unreadable ledger means UNKNOWN, never empty/healthy.
- Inbox/outbox/Future-Letter indexes become rebuildable projections.

ACCEPTANCE
- crash after OUTBOX_COMMITTED is explainable
- crash after delivery but before index write reconciles
- duplicate append does not duplicate visible mail
- unreadable ledger never renders "0 pending"
- deleting a projection can be repaired without inventing mail

NON_GOALS
Distributed consensus, blockchain, plaintext ledger, replacing SENV2.
