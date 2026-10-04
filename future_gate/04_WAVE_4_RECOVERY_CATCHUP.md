SAIMAIL

SAIHANDOFF — FUTURE GATE WAVE 4
DOWNTIME RECOVERY + COALESCED CATCH-UP

STATUS
FUTURE GATE. Depends on Waves 2–3.

INSPIRATION
AIPass daemon detects gaps, merges missed windows idempotently, queues one catch-up per logical job, and follows: the system informs, the agent reasons.

GOAL
Recover owed work after SAIMAIL/host downtime without replay storms.

BUILD
- gap detection from last successful scan/tick/service state
- never invent outage cause without evidence
- enumerate owed deliveries, receipts, reconciliation, stale locks, deferred trust checks
- coalesce repeated missed attempts by logical message/thread/peer
- bounded in-flight catch-up
- retry cooldown, visible parked state instead of silent drop
- visible queue: queued/in-flight/parked/completed/attempts/oldest
- recovery notice states facts only

ACCEPTANCE
- simulate long downtime with many missed opportunities
- bounded catch-up work, no blind duplicate replay
- restart during catch-up remains idempotent
- unreachable peer parks visibly
- normal current state can supersede stale owed work safely

NON_GOALS
Replaying every historical tick or telling agents what missed events mean.
