# PROVENANCE_CORRECTION 001 — SRC-017 / SRC-018 authorship and lineage

Recorded under T-42 (corrective work item linked to T-41), 2026-09-18.
Additive: no receipt body and no intake metadata block written before this
correction is rewritten. Every statement below is about authorship and
linkage, never about bytes.

## The defect

Two contradictions sat side by side in the intake lineage:

1. **SRC-017 was orphaned.** The receipt holding the actual operator bytes
   ("Далее продолжай по смыслу до конца пожалуйста.", sha256
   `ff7f7fd4159e7ab0c3ef60f46adf5e453e2dc550c1d5b9f8a732447d764bbe8e`, 86
   bytes) had no intake sidecar and no index entry — the crash-after-body
   half-commit SAIPEN calls `ORPHAN_RECEIPT`, reported by conformance as
   `source_receipt_orphan` (DEBT-000035..000037).
2. **SRC-018 carried exact user authorship it never earned.** Its body is a
   model-generated expansion ("Continue SAIMAIL by meaning ... repair
   W2-001..006 ... PERF-001..006 ..."), yet its intake metadata declared
   `source_kind: user_instruction` with `source_authority.mode: exact` and
   `request_provenance.witness: model_supplied`.

`mode: exact` is a true statement about BYTES and a false one about WORDS
when read next to `source_kind: user_instruction`: a consumer that skips
segments reads "the operator wrote this, verbatim". That is the
REQUEST-PROVENANCE-01 defect class, present here not because anyone forged a
witness but because the derived plan was useful and nothing marked it as
derived.

## The correction (what changed, additively)

* SRC-017's orphan state was repaired through the canonical engine operation
  (`saipen source capture` with byte-identical input; engine answer
  `ORPHAN_RECEIPT_RECOVERED`, linked_work T-41). The body digest is unchanged.
* `provenance/SRC-017.json` — segment map declaring the whole body
  `USER_ACCEPTANCE`, capture channel `HOST_USER_TURN`, operator carrier
  SRC-019 (the corrective handoff quotes these exact bytes; digest compared).
* `provenance/SRC-018.json` — segment map declaring the whole body
  `ASSISTANT_PROPOSAL`, no capture. Model-derived interpretation, execution
  plan, authorship of the session that wrote it.
* `provenance/ATTRIBUTIONS.json` — T-41's requirement now cites `SRC-017`
  segment 0 (operator instruction), not SRC-018.

## The resulting lineage

```
SRC-017   actual operator source: "continue by meaning to the end"
audit/1.md  auditor evidence: RUN_ID acb-mu62wwu7, the W2/PERF finding set
SRC-018   model-derived interpretation / execution plan (no authority of its own)
T-41      derived work: authorized by SRC-017, scoped using audit/1.md
T-42      this correction: authorized by SRC-019 (operator corrective handoff)
```

Historical T-41 closure is preserved untouched; this document re-states its
authority lineage, it does not re-open the ticket.

## Machine checks

`saimail.provenance` enforces the corrected state:

* `receipt_intent_authority("SRC-017")` resolves (every segment intent-carrying).
* `receipt_intent_authority("SRC-018")` refuses with `MIXED_AUTHORSHIP`.
* `intent_authority` on an attribution citing SRC-018 without a cited
  acceptance refuses with `ADOPTION_WITHOUT_ACCEPTANCE`.
* `source_kind_conflicts` reports SRC-018 as
  `SOURCE_KIND_IS_NOT_AUTHORSHIP` (kind `user_instruction`, segments
  `ASSISTANT_PROPOSAL`) and reports nothing for SRC-017.

## Residual protocol gap (proposal, not implemented here)

SAIPEN's intake schema cannot state, at capture time, that a receipt's bytes
are model-authored: `source_kind` is transport, `source_authority.mode`
describes bytes, and `request_provenance.witness` describes who compared —
none of them says who WROTE the body. Proposed for SAIPEN core:

* allow a `source_kind` for session-derived material (for example
  `model_expansion`) that does not sound like a user voice, and/or
* make `source_authority.mode: exact` on a `user_instruction` kind carry a
  loud conformance finding whenever `witness` is `model_supplied`, so the
  naive reading fails a gate instead of passing silently.

Until such a change exists, segment maps remain the only authorship
authority (RECEIPT-KIND-SCOPE-01), which is exactly how this correction was
recorded.
