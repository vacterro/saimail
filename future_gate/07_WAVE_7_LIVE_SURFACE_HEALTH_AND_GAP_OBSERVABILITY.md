SAIMAIL

SAIHANDOFF — FUTURE GATE WAVE 7
SELF-DESCRIBING LIVE SURFACE + HEALTH/GAP OBSERVABILITY

STATUS
FUTURE GATE. Consolidation wave.

INSPIRATION
AIPass generates live command inventories from code and treats unreadable/gapped state as first-class facts instead of healthy zeroes.

GOAL
Let future agents inspect SAIMAIL correctly without stale command docs or false-all-clear dashboards.

BUILD
- generated CLI/self-map from registered live commands
- versioned machine-readable capability schema
- report envelope versions, custody modes, feature flags, Future Letters/archive/canary support
- health summary: inbox/outbox, pending receipts, trust rotations, catch-up queue, archive health, Future Letters, quarantine, canary failures
- three-valued health where needed: HEALTHY / UNHEALTHY / UNKNOWN
- gap-aware event feed/cursor; trimmed history must expose GAP
- each subsystem owns only its own dashboard section

ACCEPTANCE
- command add/remove changes live inventory without editing a command table
- unreadable state renders UNKNOWN, not zero
- trimmed feed reports continuity gap
- restart preserves health truth
- machine surface changes additively where feasible

NON_GOALS
Giant new GUI or hiding failures behind pretty status cards.
