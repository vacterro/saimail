# T-75: inherited audit verification

The exact audit generation `audit/1.md`, SHA-256
`aacdb343e0b9ae5d21a6783e10e54ddacb6448081d6ec06ca937a6a7990ba028`,
was routed again because it lacked the current audit-inbox consumption record.
SRC-062 captures those same bytes. Its 16 clauses preserve each finding's
repair/optimization, guardrail and verification instructions.

The implementations already exist under T-39, T-40, T-41 and T-42. This Work
adds verification and receipt-lifecycle evidence only; it owns no code patch.
Historical evidence includes T-41 E-380 through E-386 and T-42 E-413.

| Clause | Finding | Existing implementation | Current regression evidence |
|---|---|---|---|
| R001 | CORE-001 | `Batch.parse` requires receiver-minted acceptance | `test_profile_acceptance.py`: hostile profiles, public parsing, mint and replacement refusals |
| R002 | CORE-002 | Verified envelope state minted only by verification | `test_senv_container.py`: bad signatures, constructor/replacement refusals, valid opens |
| R003 | CORE-003 | Provenance registry rejects duplicate identities and wrong names | `test_provenance.py`: both duplicate orders and filename mismatch |
| R004 | CORE-004 | `read_span` verifies derivative bytes before resolution | `test_quarantine.py`: altered derivative refusal |
| R005 | W2-001 | Callback signature decided before dispatch | `test_lab_contract.py`: exactly one call, post-dispatch TypeError, harness-error classification |
| R006 | W2-002 | Auth refusal halts discovery/probes and content dispatch | `test_lab_contract.py`: catalog and membership 401/403, ordinary discovery failure control |
| R007 | W2-003 | Unique live run IDs and exclusive artifact creation | `test_lab_contract.py` and `test_stability.py`: same-second runs and immutable collision refusal |
| R008 | W2-004 | Derivative published before record commit marker | `test_quarantine.py`: interrupted writes, orphan adoption, conflicting derivative refusal; `test_publish.py`: atomic publication |
| R009 | W2-005 | Immutable registration publication | `test_stability.py`: concurrent creators and interrupted registration; `test_publish.py`: no-overwrite publication |
| R010 | W2-006 | Delete distinguishes absence from backend failure | `test_credentials.py`: absent/present/outage paths and secret-free CLI failure |
| R011 | PERF-001 | Shared immutable alias lookup | `test_triage_frame.py`: one lookup, receiver parse sharing, relation semantics and scaling |
| R012 | PERF-002 | Early byte/count/line bounds | `test_triage_frame.py`: oversized declarations before materialization and exact boundaries |
| R013 | PERF-003 | Linear UTF-8 offset preparation | `test_quarantine.py`: dense scan scaling and multibyte offsets |
| R014 | PERF-004 | Linear leak basis and one normalization per file | `test_quarantine.py`: exhaustive equivalence, 500-run bound and unmatched files |
| R015 | PERF-005 | Profile identity cached per immutable profile | `test_triage_frame.py`: descriptor identity and hashing count |
| R016 | PERF-006 | Single quarantine analysis pass | `test_quarantine.py`: one scan/sanitization and identical record/derivative |

Validation on 2026-09-20:

- `python -m pytest -q`: 1785 tests passed, exit 0, before any code change.
- The nine test files listed above: 349 tests passed, exit 0; durable result
  `T-75-inherited-audit-tests.xml`. Tests exercise positive and negative inputs;
  no existing test, fixture or implementation was changed by this Work.
- Core protocol validation remains failed on two pre-existing source issues:
  SRC-017/T-41 closure coverage and SRC-036 credential detection. These are
  separate from the 16 code findings. No overall protocol VALID claim is made.

Disposition: inherited verification, with T-41 as the primary implementation
lineage and T-39/T-40/T-42 as the related corrective lineage. No release,
remote write, model call, or original receipt rewrite is part of this closure.
