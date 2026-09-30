# T-65: assignment paragraph boundary

The credential-assignment detector no longer joins a label and an unrelated
value across an empty or whitespace-only line. Inline and adjacent-line values
still match; LF, CRLF and CR are covered. Known-format and path detectors keep
their independent behavior. SRC-047's original quarantine record and sanitized
derivative retain their exact SHA-256 hashes.

The decision is the additive `spec/DECISIONS-D051.md`. The intended entry in
`spec/DECISIONS.md` exposed that B-018 registers the entire parent file by hash.
The parent was restored to its exact frozen digest
`9fc9a54a9fc906224a94c1a6c0d8ca668a7463a957663ded0e5a89182e0a1ba6`;
the consistency check now recognizes explicit decision-log addenda.

T-71 also registers the old production quarantine source. Historical harness
tests now use an inert exact-hash source fixture in a temporary tree. The
registration, production harness and drift refusal are unchanged; an explicit
changed-source control verifies that refusal. This does not authorize a fresh
live run under the old registration.

Validation:

- Original detector: the 130 new cases produced 30 failures and 100 passes.
- Corrected detector: the same 130 cases pass. The verifier file did not change
  between those runs; hashes and preserved quarantine hashes are recorded in
  `T-65-regression.json`.
- Integration and review: 249 passing tests each.
- Final full suite: **1916 passed, zero failures, errors or skips**, exit 0;
  authoritative JUnit result: `T-65-verified-suite.xml`.
- Ruff with explicit `E4,E7,E9,F` rules and Git whitespace checks pass. The
  environment's broader default Ruff profile reports typing/encoding
  modernization findings; it is not claimed clean.
- Core protocol validation still reports the two pre-existing source issues:
  SRC-017/T-41 unresolved closure and SRC-036 credential detection. This patch
  modifies SAIMAIL's detector, not the separate SAIPEN source gate. Overall
  protocol validation is not PASS.

Earlier failed suite XML files preserve the discovered historical-input
coupling; they are superseded as final validation by `T-65-verified-suite.xml`.
No original source receipt, historical registration or live artifact was edited.
No model call, commit, tag, push or publication was performed.
