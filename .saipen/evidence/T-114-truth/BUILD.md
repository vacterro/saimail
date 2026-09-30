# T-114 BUILD checkpoint

Source SRC-103 + exact steering SRC-104; active Work T-114. Product T-113 is
DONE E-1527. No parallel Work/goal and no reopen redesign.

Changed source/test/recovery files (relative to this slice's before copies):
- saimail/gui_adapter.py
- tests/test_gui_surface.py
- tests/test_gui_acceptance.py
- tests/test_repo_consistency.py
- spec/25-DESKTOP-LOCAL-MESSENGER-v0.md
- humbox/CURRENT-STATE.md
- humbox/FUTURE-GATES-V6.md
- humbox/SAIPEN-WORK-DESK.md

GUI changes are docstrings, two reason strings and removal of the obsolete gap
export. No executable Open/Reopen path changed. Tests now distinguish second
Open refusal from explicit Reopen success, inspect restarted GUI guidance and
button availability, count both decrypt paths during restart/refresh/selection,
prove unchanged durable bytes on success/failure, and guard the full acceptance
scenario with the existing no-network tripwire. The T-113 25-control matrix is
unchanged. Added Qt-independent current-capability and recovery consistency
oracles; chronological T-97/T-107/T-110 descriptions remain historical.

Focused actual results: reread 25; GUI surface 43; GUI acceptance 3;
repository consistency 43; local workspace + entrypoint 37. All passed, zero
failures/errors/skips (151 total); per-command JSON/XML/text evidence adjacent.
The first XML path used Windows backslashes that pytest's environment parser
consumed. Recovered the original XML files unchanged and derived counts from
them; repaired runner to use forward slashes and reject a missing report.
Touched-file ruff E4,E7,E9,F: PASS.
Red controls: restoring each original false reason string and original module
docstring in separate processes makes the same coherence test fail (three
expected failures, zero source edits during mutation tests).

Full suite is running through live exec session 50854; do not restart based on
this file. Poll the actual handle. Results will be full-result.json/full.xml.
Last canonical validator: inherited 4 problems / 23 warnings, no new signatures
observed; final validation pending. Remaining attributable finding: none found
in focused checks; full-suite and fresh final-byte review remain unproven.
Next exact action: enter VERIFY, poll full suite, validate canonical SAIPEN,
compare signatures/protected hashes, then perform independent final-byte review.

Additional state/evidence files: canonical STATE/BOARD/LOG, source SRC-104
body/meta/contract/coverage and intake index; this directory and the named
T-114 helper/mission files in .saipen/kitchen. No release file changed.
