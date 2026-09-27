# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-051 — credential assignments cannot cross a blank line (T-65)

The defect class is a prose label consuming unrelated text in the next
paragraph as a secret. In SRC-047, `scope token:` and a registered scope
constant were separated by a blank line, but the assignment detector's
unbounded whitespace joined them and caused a false-positive quarantine.

An assignment remains a recognized credential label, `:` or `=`, and a
non-placeholder value of at least eight non-whitespace characters. Each gap
around the separator may contain horizontal whitespace and at most one line
break. LF, CRLF and CR are supported; CRLF counts as one break. An empty or
whitespace-only intervening line terminates the assignment. Adjacent-line
values remain detectable, including indentation and a separator on its own
adjacent line. Existing value spans, UTF-8 byte offsets, label matching and
placeholder exclusions remain unchanged.

This narrows only `CREDENTIAL_ASSIGNMENT`. Known credential formats, bearer
values and credential-bearing paths retain their independent detection over
the entire receipt, even after a blank line. An unstructured secret below a
blank line is no longer classified solely by an earlier assignment label;
this is a structural heuristic, not a proof that the receipt contains no secret.

The decision changes future scans. It does not rewrite SRC-047, its quarantine
record, its sanitized derivative, or any other historical finding, and it does
not release quarantined material. Distribution remains governed by D-023.

Regression evidence: `tests/test_quarantine.py` covers empty and indented blank
lines on both sides of the separator, all three newline encodings, credential
labels and both separators, adjacent-line values, exact multibyte offsets,
placeholder exclusions and known-format detection after a blank line. The
unchanged tests fail on the original detector and pass on the bounded detector.

---
