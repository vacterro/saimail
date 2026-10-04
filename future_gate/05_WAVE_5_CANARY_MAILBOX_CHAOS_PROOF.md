SAIMAIL

SAIHANDOFF — FUTURE GATE WAVE 5
PERMANENT CANARY MAILBOX + DESTRUCTIVE PROOF LANE

STATUS
FUTURE GATE. Best after Waves 1–4 contracts stabilize.

INSPIRATION
AIPass uses a permanent canary citizen so destructive lifecycle tests never target a working agent; all canary output is explicitly test data.

GOAL
Create a synthetic SAIMAIL identity/workspace/mailbox safe to break.

BUILD
- dedicated canary keys/workspace, unmistakably TEST DATA
- scenarios: corrupt SENV, wrong key, rotation, revocation, duplicate delivery, crash windows, ledger/index loss, archive restore, Future Letter export/import, recovery bundles
- canary events excluded from production metrics/inbox by default
- deterministic reset/reseed that can never target a non-canary identity
- preserve failure reports separately
- include real filesystem/process crash tests, not mocks only
- Windows-first proof plus other supported platforms

ACCEPTANCE
- destructive suite touches no real mailbox
- canary classification survives export/import
- production list/search excludes test data by default
- reset refuses non-canary target
- at least one real crash/recovery proof passes

NON_GOALS
Production work or treating canary artifacts as production acceptance evidence.
