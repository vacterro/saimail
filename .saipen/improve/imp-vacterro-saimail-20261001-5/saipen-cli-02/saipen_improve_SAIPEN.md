agent: saipen-cli-02
role: core
model_or_runtime: unknown
project: vacterro-saimail
saipen_version: 8.0.1
protocol_fingerprint: sha256:0ff34c183c5f4ff5a11809c99b7055e22a89a71b140ff7f5d30e5c9e303ab5fd
source_head: 12e30059c509b4b340c72f9a953fc97b6881c237
source_tree_fingerprint: git-delta-v1:d8259675da9b38aa00d996eabab42c531efaec2206d5a046894c568bfe81a386
discovery_model: git-delta-v1
context_scope: SAIPEN audit, phase DONE
context_available: partial
report_status: complete

## RUN 1

Replacement-seat audit on the current tree, same scope as saipen-cli-01: the beacon registration sweep in tests/test_repo_consistency.py and the CHANGELOG entry that describes it. This seat exists because saipen-cli-01's report is sealed against a tree that T-160 then changed, and a stale report cannot authorize fresh canonical work.

What the delta contains: T-160 closed RUN-1/IMP-001, which had found that registration was decided by substring containment over free text (intake receipts + .saipen/BOARD.md + .saipen/LOG.md), so a file named anywhere in the journal passed the sweep as 'registered' without any receipt. The demonstration was the audit's own residue: a T-159 verify checkpoint had written the sentence 'Scenario D (new arrival at humbox/_p.md): caught' into the LOG, and from that moment a planted humbox/_p.md produced unregistered = [] -- a silent pass for an uncaptured operator file.

The fix, re-read line by line on the current tree: BEACON_REGISTRY and the corpus predicate are gone rather than tightened; BEACON_BINDINGS now holds a bare receipt id per beacon; a new helper reads request_provenance.compared_digest out of the receipt's meta.json and returns '' when the receipt is absent or unparsable, so a missing receipt fails the binding instead of raising; the sweep accepts a binding only when that digest equals sha256 of the live file's bytes or of its LF-normalized form, and separately reports every humbox/**/*.md that is neither bound nor explicitly exempted. Both structural sources, no prose. Ten files that had been passing on nothing but an incidental journal mention were moved into LEGACY_UNREGISTERED_BEACON, which is the truthful label for files no receipt ever carried.

Verification reproduced here, not inherited: the sweep test exits 0 on the clean folder; the same test exits 1 with 'operator material in humbox/ that no receipt accounts for: ['_p.md']' when that journal-mentioned probe file is planted -- the exact case the old predicate swallowed -- and the probe was removed afterwards; python -m pytest -q exits 0 across the suite; ruff --select E4,E7,E9,F is clean; and both existing rows were checked by hand against their receipts (SRC-117 compared_digest 58ede0b0902ac3c2... equals sha256 of LF-normalized humbox/milestoned1.md; SRC-119 compared_digest 0cc711fd6ed51ad0... equals sha256 of LF-normalized humbox/YAZADAYU_born1.md). The identity question T-159 settled -- basename versus path relative to humbox/ -- is untouched and still exercised by the nested probe.

NO_FINDINGS -- the delta audited here is one self-inflicted defect and its repair, both re-read against the current bytes and both re-proved by a probe that used to fail the check and now fires it. What was looked for and not found: any surviving path by which prose re-enters the registration predicate (the corpus constant is deleted, not narrowed -- confirmed by grep, no reference to BEACON_REGISTRY remains); any way a binding can be asserted without the receipt vouching for it (the digest comparison runs before the exemption test and a vanished file is reported as drift rather than skipped); any other test or helper depending on the removed constant. The one ceiling that remains is deliberate and was recorded in T-160's review: the binding row lives in a test file, so capturing a beacon is now two steps and the sweep is loud rather than silent in between. That is a workflow cost with the right failure direction, not a defect, and the proper fix -- a source-path field in the intake grammar -- belongs to SAIPEN, outside this repository.

VERDICT: no finding on this delta. saipen-cli-01's IMP-001 is fixed and verified here against current bytes, which is what superseding it onto this seat asserts.
