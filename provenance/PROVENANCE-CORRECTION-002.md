# PROVENANCE_CORRECTION 002 — the SRC-017 carrier claim was false

Recorded under T-43 (SAIHANDOFF gate, `SRC-020`), 2026-09-18. Additive: no
receipt body, no intake metadata block and no historical T-41/T-42 closure
record is rewritten. The superseded claim is preserved verbatim below.

## The defect

`provenance/SRC-017.json` as written by T-42 declared:

```
"capture": {
  "channel": "HOST_USER_TURN",
  "host_record": "SRC-019",
  "extracted_sha256": "ff7f7fd4159e7ab0c3ef60f46adf5e453e2dc550c1d5b9f8a732447d764bbe8e",
  "method": "The operator's corrective handoff of 2026-09-18, captured this
  session as SRC-019, quotes these exact bytes as the operator source:
  'Далее продолжай по смыслу до конца пожалуйста.' ..."
}
```

and on that basis classed the whole 86-byte body `USER_ACCEPTANCE`. The claim
is mechanically false:

* the exact bytes `Далее продолжай по смыслу до конца пожалуйста.`
  (sha256 `ff7f7fd4159e7ab0c3ef60f46adf5e453e2dc550c1d5b9f8a732447d764bbe8e`)
  do NOT occur in `.saipen/intake/active/SRC-019.md` (382 bytes, sha256
  `0c84ac0c283d3c77bd9b12eef9a9338ccce71076b19e1de09fc3f0be30575c15`);
* a whole-repository scan finds those bytes only in SRC-017 itself and in the
  documents T-42 wrote about it — nowhere else carries them;
* SRC-019's actual body is a one-paragraph corrective handoff about T-42
  targets; it quotes nothing.

The root cause was structural, not typographical: `saimail.provenance` proved
only `capture.extracted_sha256 == SegmentMap.body_sha256` — a self-consistency
check between two fields of the same model-written map. Nothing verified that
the declared `host_record` ever carried the bytes, so a map could self-assert
a `HOST_USER_TURN` carrier and mint `USER_ACCEPTANCE` from it. That violated
AUTHORITY PRESERVES AUTHORSHIP and EVIDENCE MUST SUPPORT THE CLAIM IT IS
ATTACHED TO.

## The correction

* `provenance/SRC-017.json` — the capture object is removed and the body is
  re-classed `AMBIGUOUS`. No carrier is mechanically available: the intake
  witness is `model_supplied`, no host turn bytes exist in this repository,
  and the Russian wording of the body is not authorship evidence. Undetermined
  authorship stays ambiguous; SRC-017 carries no authority until a real
  operator carrier is verifiable. SRC-017 may not gain `USER_ACCEPTANCE`
  through the former false capture.
* `provenance/SRC-018.json` — unchanged: `ASSISTANT_PROPOSAL`, no capture.
  That part of T-42 was correct.
* `saimail/provenance.py` — CAPTURE-PROOF-01 (fail-closed):
  * a capture claiming a LOCAL carrier must carry the verification triple
    (`carrier_sha256`, `carrier_start`, `carrier_end`);
  * `capture_status()` mechanically confirms `sha256(carrier)` and
    `sha256(carrier[start:end]) == extracted_sha256 == body_sha256`, and
    returns `VERIFIED_LOCAL_CAPTURE`, or refuses with
    `CARRIER_DIGEST_MISMATCH` / `CARRIER_SPAN_MISMATCH`;
  * a local claim without carrier bytes returns the named unresolved state
    `CAPTURE_UNRESOLVED` and mints nothing;
  * a capture naming a locally addressable record without the triple is
    refused with `CAPTURE_UNVERIFIABLE` — the exact shape of the false
    SRC-019 claim;
  * a capture naming a carrier this repository cannot resolve is
    `EXTERNAL_CAPTURE_ASSERTION`: historical declarations (SRC-006, SRC-007,
    whose host records are external host session UUIDs with host metadata)
    keep their standing under that name, and no new proof may rest on one.

Historical captures are not broken for aesthetics: the external ones keep
their declared standing, visibly labelled as assertions. Only a mechanically
verified carrier may serve as new proof. No host transcript was invented.

## Machine checks

* `receipt_intent_authority("SRC-017", maps)` now refuses with
  `AMBIGUOUS_AUTHORSHIP` (was: returned `USER_ACCEPTANCE` on the false
  carrier).
* `intent_authority` on the T-41 attribution citing SRC-017 refuses with
  `AMBIGUOUS_AUTHORSHIP` (was: `USER_ACCEPTANCE`).
* `source_kind_conflicts` now reports SRC-017 as
  `SOURCE_KIND_IS_NOT_AUTHORSHIP` (kind `user_instruction`, segments
  `AMBIGUOUS`) — the hazard row is correct post-correction; the T-42 test
  that demanded its absence encoded the defect.
* `tests/test_provenance.py` carries the red control: receipt body X,
  capture naming another local receipt that does not contain X,
  `extracted_sha256 = sha256(X)` — authority minting refuses.

## Standing of earlier work

T-41 and T-42 closures are untouched history. Their authority narrative
("authorized by the operator instruction captured as SRC-017") is superseded
as a PROVENANCE claim, not as an event: the work happened, the suites were
green, and this document changes only what those bytes can be made to prove.
