SAIMAIL

SAIHANDOFF — FUTURE GATE WAVE 3
HOT/COLD ARCHIVE — ARCHIVE → VERIFY → PRUNE

STATUS
FUTURE GATE. Depends on Waves 1–2.

INSPIRATION
AIPass memory archives first, verifies read-back, then removes hot entries. Remove-before-verify is treated as data loss.

GOAL
Keep active mail compact without ever deleting the only recoverable copy.

PIPELINE
HOT → WRITE COLD ARCHIVE → VERIFY INTEGRITY/READ-BACK → ARCHIVE RECEIPT → PRUNE HOT

BUILD
- retention by age/count/size and message kind
- stronger default retention for Future Letters/time capsules
- versioned cold format preserving canonical encrypted payload + provenance + ledger links
- verify hashes and authorized reopen where possible before prune
- restore by id/hash, idempotently
- metadata search always; optional semantic search only under explicit plaintext-derivative policy
- search result always points back to canonical source
- pinned never-prune class
- archive health and corruption detection

ACCEPTANCE
- archive, verify, prune, restore exact logical content
- forced write/verify failure leaves hot copy untouched
- Future Letter stays discoverable after hot prune
- cold corruption is visible

NON_GOALS
Automatic context injection, lossy summaries as sole copy, mandatory cloud.
