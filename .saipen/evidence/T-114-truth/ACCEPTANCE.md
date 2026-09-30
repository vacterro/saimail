# T-114 — capability and recovery truth reconciliation

Local engineering acceptance: PASS. T-113 was already DONE at E-1527; this
slice repairs its contradictory presentation and recovery truth. Existing Work
T-114, source SRC-103 with exact steering SRC-104. No wrapper ticket or parallel
goal. Canonical lifecycle completion follows this evidence; STATE/BOARD/LOG
remain the phase authority.

## Scope and classification

Pre-edit SCOUT checkpoint E-1529 precedes BUILD E-1530. Required STATE, BOARD,
LOG E-1486–E-1528, saved T-113 design, specs and recovery documents were inspected.
`classification.json` assigns every one of 246 repository-wide matches:
26 A (current false), 203 B (historical), 2 D (valid non-READ refusal), 15 E
(generated/cache). Additional contextual findings include valid C first-open
guards and multiline A claims. Historical sources, producer packages and
closure proofs were preserved; generated build/cache files are not source.
The saved T-113 design received a later-closure annotation, not a rewritten past.

Nine reviewed source/test/recovery files and their exact hashes are recorded
in `final-bytes.json`; complete attributable changes are in `final.diff`:
gui_adapter, GUI surface/acceptance and repository-consistency tests, spec/25,
CURRENT-STATE, Roadmap v6, Work Desk and the saved T-113 design annotation.
Protocol artifacts also include this evidence, helpers/mission under kitchen,
SRC-104 intake records and canonical checkpoints/digest. No unrelated dirty
checkout work was reverted or included in a commit.

## Acceptance evidence

| Requirement | Final evidence |
|---|---|
| GUI truth and distinct actions | gui_adapter docstring and two READ reasons point to explicit Reopen; obsolete READ_REREAD_GAP export removed. All executable adapter function ASTs equal the before snapshot. |
| C1: READ refuses second Open | renamed `test_read_refuses_second_open_but_explicit_reopen_remains_available`; acceptance invokes Open on restarted READ and asserts OPEN_NOT_UNREAD with zero backend calls. |
| C2: refusal leaves Reopen available | same adapter control plus enabled Reopen button after refused Open in acceptance. |
| C3: fresh READ content hidden, Reopen visible, useful text | surface `test_reopen_in_window` and restarted acceptance window inspect hidden plaintext, enabled button and Reopen guidance. |
| C4: explicit Reopen returns content | actual button click calls workspace.reopen_message once and returns the private acceptance marker. |
| C5/C6/C7: selection/refresh/restart never decrypt | acceptance spies on BOTH workspace open functions before restart; zero calls after each operation. Unchanged T-113 selection/refresh controls also pass. |
| C8: READ preserved | selected and durable states stay READ; complete workspace byte snapshots match after Reopen; unchanged T-113 state controls. |
| C9: failed Reopen non-mutating | new failed-Reopen surface control checks selection, hidden content, error and complete durable tree equality; unchanged T-113 wrong-key/sender/index/receipt/corruption/expiry/crash controls pass. |
| C10: no plaintext persistence | acceptance checks byte-identical workspace trees and absence of private marker; unchanged T-113 plaintext/container controls pass. |
| C11: no network/model/provider calls | full two-workspace acceptance now uses real no_network tripwire; unchanged T-113 no-network control passes. Source trace remains GUI -> workspace -> PostOffice -> crypto; no provider/model path added. |
| C12: Open unchanged | executable function AST equality; PostOffice/workspace/CLI/window byte hashes unchanged; T-113 first-open/CLI/double-click controls pass. |
| D: current recovery and chronology | CURRENT-STATE top/current/next sections, Roadmap v6 current/restart/§14 lane row, Work Desk next direction and saved design annotation say T-113 DONE. T-97/T-107/T-110 checkpoint descriptions remain historical. |
| E: recurrence oracle | two new Qt-independent repository tests bind READ guidance to Reopen, V6-02 DONE/T-113/E-1527, explicit frozen exclusion and stable API open/reopen entries. No paragraph snapshot. |
| Red control | original two runtime strings and original module docstring each make the same runtime coherence test fail; injected stale current-roadmap claim makes recovery oracle fail. Four expected red runs, isolated in memory; logs and red-controls.json retained. |
| Frozen and media boundaries | all 90 protected files hash-identical: every release file including a1/a2/a3 bundles/evidence, exact SAIGIMN.mp3 and manifest, T-113 core/CLI/API/window/matrix/spec03, VERSION and pyproject. |

## Verification

Every focused command is `python -m pytest -q` with these paths; JUnit output
adds reporting only, not altered test selection. Per-command text/XML/JSON is
stored beside this report.

| Paths / command | Passed | Failed | Errors | Skipped |
|---|---:|---:|---:|---:|
| tests/test_reread_continuation.py | 25 | 0 | 0 | 0 |
| tests/test_gui_surface.py | 43 | 0 | 0 | 0 |
| tests/test_gui_acceptance.py | 3 | 0 | 0 | 0 |
| tests/test_repo_consistency.py | 43 | 0 | 0 | 0 |
| tests/test_local_workspace.py tests/test_local_entrypoint.py | 37 | 0 | 0 | 0 |
| Canonical `python -m pytest -q` | **2552** | **0** | **0** | **0** |
| Fresh REVIEW rerun of first four focused files | 114 | 0 | 0 | 0 |

Python 3.11.9 / Windows, Qt 6.11.1. The new full count is historical T-113's
2549 plus three added tests. Touched-file ruff `--select E4,E7,E9,F` PASS.
The first full run was 2551/1 with PROJECT_PILOT_SOURCE_MUTATED, overlapping
our LOG checkpoint writes. The registered corpus includes LOG.md and rejects
changes during capture. The isolated test and subsequent quiescent full run
passed without any code/test/fixture relaxation. First-run evidence is retained
in full-first.*; VERIFY-retry.md documents the changed execution condition.

Canonical SAIPEN validation remains **4 inherited problems / 23 warnings**.
Exact comparison in validator-delta.json: **zero new problem signatures**.
Inherited signatures are explicitly separate from this slice:

- source_receipt_unresolved_work, T-41 / SRC-017 (detail hash 8e410875a794f3dc);
- source_credential_unsafe, SRC-017 (13c5015d6f0fe0c7; sensitive detail omitted);
- inherited STATE seat `opus` conformance finding (84a39e0eab234308);
- stale Improve protocol fingerprint (c7e6f36c086c115e).

No attributable finding calls for a registered executable repair. The returned
`saipen work reverify T-99` route concerns inherited unrelated provenance,
which this mission explicitly excludes. No historical provenance was invented,
renamed, quarantined or repaired to make the validator green.

## Fresh final-byte review

After full verification, REVIEW re-ran 114 controls and lint, re-read the actual
GUI reasons/actions/window renderer, PostOffice and workspace call paths, and
the final recovery sections, and rechecked all reviewed/protected hashes.
This is a separate review pass by the same executing agent, not a claim of an
additional reviewer identity. No attributable P0/P1 finding remains.

Inspected boundaries: no automatic decrypt, no persisted plaintext, no READ to
UNREAD reinterpretation, unchanged first-open transition, unchanged sender and
recipient verification, unchanged expiry/tombstone/crash refusal, no frozen
candidate mutation, honest roadmap chronology, historical evidence retained,
and no current instruction to redo T-113. Test changes strengthen the intended
split; the original bug still makes the new oracle fail. No reusable knowledge
card is needed for this transient reconciliation.

## Stop boundary

No version bump, candidate rebuild, commit, tag, push, publication, external
proof fabrication, audio recompression or hook implementation. G13 remains
PENDING_EXTERNAL, G17 ABSENT, publication NONE. The current corridor is complete.
Next separate target, only after acceptance: evaluate the SAIPEN-owned Work
Desk / SAITELEMES turn-entry hook, bounded header-only awareness with receiver
authority and zero automatic open. Do not start it as part of this repair.
