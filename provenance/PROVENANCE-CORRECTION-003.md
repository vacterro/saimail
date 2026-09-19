# PROVENANCE_CORRECTION 003 — an external capture assertion is not captured bytes

Recorded under T-44 (the T-5 final preflight, `SRC-021`), 2026-09-18. Additive:
no receipt body, no segment map, no intake metadata block and no historical
closure record is rewritten. The superseded claim is preserved verbatim below.

## The defect

An independent review of the T-43 capture model reproduced a remaining authority
bypass. Construct:

* receipt body `X`, one segment declared `USER_ACCEPTANCE`;
* capture `channel = HOST_USER_TURN`, `host_record` = an arbitrary external id
  this repository cannot resolve, `extracted_sha256 = sha256(X)`;
* no `carrier_sha256`, no `carrier_start`, no `carrier_end`.

Before this correction:

```
capture_status(...)          -> EXTERNAL_CAPTURE_ASSERTION   (correct)
receipt_intent_authority(...) -> USER_ACCEPTANCE             (the bypass)
```

The status was honest, but the authority layer treated the assertion as
mechanically captured user acceptance, so an agent could avoid the local
carrier verification rule (`CAPTURE-PROOF-01`) by naming an unresolvable
external host record. This violated AUTHORITY PRESERVES AUTHORSHIP and
UNVERIFIED ASSERTION != CAPTURED USER ACT. Red control:
`tests/test_provenance.py::test_an_unresolvable_external_assertion_never_mints_captured_acceptance`
(fails on the pre-fix tree with `USER_ACCEPTANCE`).

## The correction

`CAPTURE-PROOF-02` in `saimail/provenance.py`:

* `EXTERNAL_CAPTURE_ASSERTION` stays a valid descriptive capture STATUS and
  remains historical evidence that somebody asserted an external host record.
  It is not, and can never be, mechanical proof of that record's bytes.
* Authority minting is capped by the status. External-asserted
  `USER_ACCEPTANCE` resolves to `USER_ACCEPTANCE_OBSERVED` -- the historical
  claim that an operator act was observed/asserted stays visible, without
  pretending its bytes were mechanically captured. Adoption of a proposal
  through such a segment resolves identically.
* A declared `USER_INTENT` under an external assertion refuses with
  `EXTERNAL_CAPTURE_NOT_PROOF`: no observed intent rung exists, and borrowing
  the captured name would be the same defect renamed. This follows correction
  002's precedent, where an unverifiable capture claim yielded no intent
  authority (`AMBIGUOUS_AUTHORSHIP` for SRC-017).
* The rule follows the evidence class, not identity: no receipt-id allowlist,
  no external-UUID allowlist. `CAPTURE_UNRESOLVED` still refuses outright, and
  a verified local carrier still mints the captured rung.

The superseded claim, from `PROVENANCE-CORRECTION-002.md`, is preserved
verbatim:

> a capture naming a carrier this repository cannot resolve is
> `EXTERNAL_CAPTURE_ASSERTION`: historical declarations (SRC-006, SRC-007,
> whose host records are external host session UUIDs with host metadata)
> keep their standing under that name, and no new proof may rest on one.

"Keep their standing" is what this correction narrows: the standing an
unresolvable external capture keeps is the observed/asserted rung. That the
external captures were once treated more strongly (as plain `USER_ACCEPTANCE`
under correction 002, which introduced the status names) is the historical
reason this correction exists and is deliberately not erased.

## Historical SRC-006 / SRC-007

Their receipt bodies and segment maps are untouched; no host transcript bytes
were invented and no local carrier triples were manufactured. Current authority
evaluation: `USER_ACCEPTANCE_OBSERVED` for both receipts, and for the B-011,
B-012, B-013 attributions that cite SRC-007.

## Machine checks

* `receipt_intent_authority("SRC-006"/"SRC-007", maps)` -> `USER_ACCEPTANCE_OBSERVED`
  (was `USER_ACCEPTANCE`).
* `intent_authority` on SRC-007 citations -> `USER_ACCEPTANCE_OBSERVED`.
* Synthetic red control, adoption cap and the `USER_INTENT` refusal are
  covered by tests in `tests/test_provenance.py`; the A5 matrix test walks
  every required row in one place.
* `saimail.quarantine.represented_authority` reports the capped rung, and the
  quarantine tests assert it.

## Standing of earlier work

T-41, T-42 and T-43 closures stand as events; the suites they verified remain
green. This document changes only what an external capture assertion can be
made to prove.
