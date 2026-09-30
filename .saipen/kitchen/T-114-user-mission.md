SAIMAIL
CONTINUE EXISTING T-114.
DO NOT CREATE A WRAPPER TICKET.
DO NOT START A PARALLEL GOAL.

MISSION

Reconcile the completed T-113 receiver re-read implementation with every
runtime-facing, test-facing, roadmap-facing, and cold-recovery statement that
still claims the READ_REREAD_GAP exists.

The product capability already exists. This slice is NOT a redesign of reopen.
It is a capability-truth and recovery-truth repair.

CURRENT MACHINE TRUTH

Canonical lifecycle:
- STATE phase: SCOUT
- active Work: T-114
- source: SRC-103
- blocker: none
- T-107: DONE
- T-113: DONE
- T-115: DONE

T-113 implementation evidence:
- saimail/postoffice.py exposes PostOfficeSession.reopen_message()
- saimail/workspace.py exposes reopen_message()
- saimail_local.py exposes the distinct reopen CLI action
- saimail/gui_adapter.py exposes reopen_selected() / reopen_reason()
- saimail/gui_app.py exposes the explicit Reopen button
- lab/stable_local_api.json records reopen_message
- README.md documents saimail-local reopen
- spec/03-POST-OFFICE.md contains the reopen contract
- spec/25-DESKTOP-LOCAL-MESSENGER-v0.md 4.3 explicitly says T-113 resolves
  the former capability gap
- tests/test_reread_continuation.py contains the 25-control T-113 matrix
- LOG E-1521 records canonical full suite:
  2549 passed / 0 failed / 0 errors / 0 skipped
- LOG E-1524 records independent review PASS
- LOG E-1527 closes T-113

T-115 subsequently repaired D3 historical evidence monotonicity:
- focused D3 suite: 44 passed
- full suite recorded: 2522 passed at that checkpoint
- historical frozen candidate evidence remains separate from later checkout work

DO NOT REIMPLEMENT T-113.

PRIMARY FINDING

The checkout contains contradictory capability truth.

The backend and explicit Reopen action support re-reading a durable READ message,
but several GUI strings, tests, and recovery documents still claim that this is
impossible.

This contradiction can mislead both a human operator and a cold-recovery agent.

CONFIRMED STALE RUNTIME SURFACE

saimail/gui_adapter.py currently contains obsolete statements including:

- module-level documentation saying a durably READ message cannot be re-opened
  in a later session
- REASON_OPEN_ALREADY_READ claiming content cannot be shown again in a new
  session
- REASON_READ_NOT_THIS_SESSION claiming content is not re-readable
- READ_REREAD_GAP claiming workspace.open_message is the only decryption path
  and an already-READ message cannot be re-opened

These statements became false when T-113 introduced workspace.reopen_message.

The distinction that must remain is:

- Open is still first-open only
- calling Open on READ must still refuse
- selecting/refreshing a READ row must remain metadata-only
- content must not appear automatically
- an explicit Reopen action may re-authenticate/decrypt a READ message
- Reopen must remain budgeted, fail-closed, and non-mutating

Do not "fix" this by allowing Open to reopen.
Open and Reopen must stay separate actions.

CONFIRMED TEST CONTRADICTION

tests/test_gui_surface.py currently contains an obsolete test named approximately:

test_already_read_message_cannot_be_reopened_and_says_so

It correctly proves that a SECOND open_selected() is refused, but then
incorrectly treats that refusal as proof that explicit reread is impossible.

The same file later contains T-113 tests proving reopen_selected() succeeds.

tests/test_gui_acceptance.py also pins the old
REASON_READ_NOT_THIS_SESSION capability statement after restart.

The tests therefore currently allow mutually contradictory product truth.

A bounded local rerun of:

- tests/test_reread_continuation.py
- tests/test_gui_surface.py
- tests/test_gui_acceptance.py
- tests/test_repo_consistency.py

collected 66 tests and completed with 65 passed / 1 skipped on the inspected archive.

Do not treat that green result as proof the wording is correct. The obsolete
expectations themselves are the defect.

CONFIRMED STALE RECOVERY / ROADMAP SURFACE

At minimum inspect and reconcile:

humbox/CURRENT-STATE.md
humbox/FUTURE-GATES-V6.md
humbox/SAIPEN-WORK-DESK.md

Known stale claims include:

- READ_REREAD_GAP remains open
- already-READ content cannot be displayed later
- V6-02 is NOT STARTED
- V6-02 receiver reread continuity is the next implementation
- T-114 still has the saved T-113 design as its next candidate

Those statements were valid before T-113 and are no longer current truth.

Historical descriptions MUST remain historical.

Do not rewrite an older roadmap statement when it is explicitly describing the
state "at T-107 closure" or another historical checkpoint. Instead annotate or
add a later closure statement so chronology remains honest.

The current/restart sections, however, MUST report the present state.

MILESTONE A  SCOUT AND CLASSIFICATION

1. Read:
   - .saipen/STATE.md
   - current BOARD row
   - LOG from E-1486 through E-1528
   - .saipen/kitchen/T-113-reread-continuation.md
   - spec/03-POST-OFFICE.md
   - spec/25-DESKTOP-LOCAL-MESSENGER-v0.md
   - humbox/CURRENT-STATE.md
   - humbox/FUTURE-GATES-V6.md
   - humbox/SAIPEN-WORK-DESK.md

2. Search the complete repository for stale reread capability language,
   including conceptual variants of:
   - READ_REREAD_GAP
   - not re-readable
   - cannot be re-opened
   - cannot be shown again
   - only decryption path
   - V6-02 NOT STARTED
   - V6-02 next
   - receiver reread gap

3. Classify every match:
   A. current false capability claim
   B. intentionally historical statement
   C. valid first-open-only statement
   D. valid Reopen refusal for UNREAD/non-READ state
   E. unrelated textual match

Only category A requires correction.
Historical evidence must not be silently rewritten.

Checkpoint the exact classification before editing.

MILESTONE B  RUNTIME UX TRUTH REPAIR

Repair saimail/gui_adapter.py so the presentation layer accurately exposes the
T-113 semantics.

Required behavior:

UNREAD:
- Open available
- Reopen unavailable
- content hidden until explicit Open

READ with no content loaded in this GUI session:
- Open unavailable because first-open is already complete
- Reopen available
- content note must explain that the message is READ and can be explicitly
  re-opened/re-read
- do not imply automatic content availability

READ after successful Open/Reopen in the current session:
- content visible from ephemeral presentation state
- durable mailbox state remains READ

Do not alter protocol semantics merely to repair wording.

Strong preference:
remove or rename READ_REREAD_GAP if it no longer represents a real gap.

If compatibility requires keeping an exported symbol temporarily, make its
meaning non-false and document why it remains. Do not preserve a known false
claim solely because a test imports it.

Update the module docstring to describe Open versus Reopen correctly.

MILESTONE C  TEST ORACLE REPAIR

Update tests so they prove the intended split rather than the obsolete gap.

Required controls:

1. READ refuses a second open_selected().
2. That refusal does NOT imply Reopen is unavailable.
3. Fresh GUI session + READ row:
   - content remains hidden
   - Reopen is visibly available
   - explanatory text points to explicit Reopen rather than claiming
     impossibility.
4. Explicit Reopen returns the content.
5. Selection alone never decrypts.
6. Refresh alone never decrypts.
7. Restart alone never decrypts.
8. Reopen preserves READ state.
9. Failed Reopen leaves durable state unchanged.
10. No plaintext persistence.
11. No network/model/provider calls.
12. Existing Open semantics remain unchanged.

Rename obsolete test names whose names themselves encode the old capability
claim.

Do not weaken T-113 tests to obtain green.

RED CONTROL

Before accepting the repair, demonstrate that reintroducing the old
"not re-readable / cannot be reopened" runtime truth causes at least one
capability-coherence test to fail.

Prefer a deterministic source/string/behavior assertion over brittle prose
matching when practical.

MILESTONE D  CURRENT ROADMAP / RECOVERY TRUTH

Reconcile current authority documents.

humbox/CURRENT-STATE.md must clearly state:

- T-113 DONE
- receiver re-read continuity implemented
- V6-02 / READ_REREAD_GAP is resolved by T-113, if V6-02 is the canonical
  name for that work
- distinct Open and Reopen semantics
- current checkout is ahead of frozen 0.0.2a3 by the applicable checkout-only
  work
- T-114 owns subsequent continuation

humbox/FUTURE-GATES-V6.md must preserve historical chronology while updating
the current roadmap position.

For example:
- statements explicitly scoped to "at T-107 closure" may remain historical
- current limitation / current position / restart sections must not say the
  gap is still open
- record T-113 as the closure of the receiver reread lane
- do not pretend T-113 was part of frozen 0.0.2a3
- do not alter G13/G17/publication truth

humbox/SAIPEN-WORK-DESK.md must stop directing a new agent to implement
receiver continuity as future work.

Its next-direction section may instead point to the still-separate
SAIPEN-owned turn-entry hook, but DO NOT implement that hook in this repair
slice.

MILESTONE E  REPOSITORY CONSISTENCY

Add or update a repository-consistency oracle that catches future recurrence
of this exact drift.

The oracle should establish semantic invariants such as:

- current roadmap recognizes T-113 reread closure
- current-state does not label READ_REREAD_GAP open
- GUI current capability language does not claim READ messages are impossible
  to explicitly reopen
- stable API includes reopen_message
- frozen 0.0.2a3 is still described as not containing later checkout-only work

Avoid a giant exact-paragraph snapshot.
Test the meaningful invariants.

MILESTONE F  VALIDATION

Run focused:

python -m pytest -q tests/test_reread_continuation.py
python -m pytest -q tests/test_gui_surface.py
python -m pytest -q tests/test_gui_acceptance.py
python -m pytest -q tests/test_repo_consistency.py
python -m pytest -q tests/test_local_workspace.py tests/test_local_entrypoint.py

Run lint appropriate to touched Python files.

Then run the canonical full suite:

python -m pytest -q

If the suite differs from the historical T-113 count because tests were added
or legitimately changed, report the new exact count. Do not force the count to
remain 2549.

Run canonical SAIPEN validation.

KNOWN INHERITED SAIPEN CONFORMANCE DEBT

The inspected archive carries a known canonical validation baseline around:

- T-41 / SRC-017 unresolved source/release linkage
- SRC-017 credential/source safety finding
- seat/agent identity conformance finding
- stale improve-report protocol fingerprint
- associated warnings

The latest inspected evidence records 4 problems / 23 warnings.

These are inherited protocol debt, not permission to ignore new findings.

For this slice:
- introduce zero new validator problem signatures
- classify current inherited signatures explicitly
- do not casually repair unrelated historical provenance
- do not forge historical provenance to obtain a green validator
- if SAIPEN provides a registered executable repair for a current attributable
  finding, follow protocol; otherwise preserve and report the boundary

MILESTONE G  INDEPENDENT REVIEW

After all edits and tests, perform a fresh review against final bytes.

Explicitly inspect:

- gui_adapter Open/Reopen wording and behavior
- no automatic decrypt path
- no plaintext persistence
- no accidental reinterpretation of READ as UNREAD
- no change to first-open lifecycle transition
- no relaxed sender/recipient verification
- no weakened expiry/tombstone/crash refusal
- no frozen candidate mutation
- roadmap chronology remains honest
- historical evidence remains historical
- current recovery path no longer instructs another agent to redo T-113

If any P0/P1 attributable finding remains, return to BUILD rather than SHIP.

ACCEPTANCE CRITERIA

This slice is complete only when all are true:

- explicit Reopen remains operational across sessions
- Open still refuses already-READ messages
- the GUI never claims explicit reread is impossible
- a fresh-session READ selection explains the available Reopen path
- stale READ_REREAD_GAP current-state claims are removed/reclassified
- current Roadmap v6 records T-113 closure
- cold recovery no longer selects T-113/V6-02 as unimplemented work
- tests no longer encode contradictory capability truth
- focused suites pass
- canonical full suite passes
- zero new SAIPEN validation problem signatures
- frozen 0.0.2a1/a2/a3 bytes are untouched
- no publication, tag, push, candidate rebuild, version bump, or external-proof
  fabrication occurs

NON_GOALS

Do not:
- redesign reopen
- merge Open and Reopen
- add automatic opening
- add background polling
- add network transport
- add message notifications
- implement the SAIPEN automatic telegram trigger
- implement the SAIPEN turn-entry hook
- repair unrelated historical SAIPEN provenance debt
- rebuild 0.0.2a3
- publish anything
- remove or recompress SAIGIMN.mp3
- weaken exact asset manifest protection
- mutate frozen candidate evidence to include checkout-only T-113 behavior

RECOVERY / CONTEXT EXHAUSTION

At every meaningful checkpoint record:
- active Work and phase
- exact changed files
- focused-test result
- full-suite result when available
- current validator result
- remaining attributable finding
- next exact action

If context becomes scarce, leave a cold-recovery checkpoint before stopping.

Never require the next agent to reconstruct whether T-113 was implemented.
That fact must become mechanically visible in current recovery truth.

STOP CONDITION

Stop this corridor after capability truth, tests, and current recovery truth
agree on T-113.

Do not opportunistically start the SAIPEN-owned automatic turn-entry hook inside
the same repair.

NEXT EXACT TARGET AFTER ACCEPTANCE

Evaluate the SAIPEN-owned turn-entry hook for Work Desk / SAITELEMES:
automatic bounded header-only telegram awareness at agent turn entry, with
receiver-owned authority and zero automatic open.

That is a separate capability gate and must begin only after this T-113 truth
reconciliation is accepted.