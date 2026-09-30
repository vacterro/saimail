# T-144: executable preregistered real-use recorder

T-143 feedback provenance completed locally before this repair (E-2136).
No T-143 observation was manufactured from its SCOUT prose.

The original registration and observation 1 remain byte-identical:

- registration.json: fec8b9908129b2dcbf5b86d92214ce5ab17cf6a71392c769c272c39cd0a4dc4f
- runtime.json: 451d1960f397e4789dff611602376ed4395ba69f0db0531007fb9576140d147e

`capture.py` derives the next entry from the validated retained sequence and
creates runtime-002.json through runtime-006.json exclusively. It never takes a
caller-specified entry or Work. Corrupt/gapped/duplicate evidence, a changed
registration, an unowned/ended Work or the registered limit refuses observation.
Each new record binds its predecessor's exact hash. Partial files survive a crash
and refuse further capture; recovery must preserve them rather than overwrite.

The actual context is read from STATE, IDENTITY, the owned DOING row and the LOG
tail. Retained canonical bytes, before/after memory hashes, seat, phase, event,
timestamp and a reconstructed focus witness let later verification distinguish
the observed context from the current one. No canonical continue/lifecycle
command runs during capture. Only the existing configured contract and keyless
focus commands execute; they open no bodies and make no receiver decisions.
The foreign SAIPEN STATE hash is checked before and after observation.

Qualification is deliberately conservative: one boundary per project lineage
and Work. A new phase, checkpoint, focus hash, continuation, session or seat
inside the same Work cannot inflate the registered minimum. Repeats are refused
before commands. The verifier reports retained observations and boundaries
separately, as well as distinct eligible header references. Those references do
not establish an independent receiver assessment or evidence quality.

The verifier checks the sequence read-only by default:

    python .saipen/evidence/T-142-evolution-audit/verify.py

An optional new `--out <basename>.json` retains a check exclusively. Historical
verify.json, review.json and sources.json are preserved; current sequence
verification does not pretend the T-142 source-freshness receipt covers later
product changes. To observe a later actual authorized Work:

    python .saipen/evidence/T-142-evolution-audit/capture.py

The fixed regression criterion was red against the original recorder because it
refused when runtime.json existed, and green against the repaired recorder with
the same fixture and criterion. Additional controls cover malformed metadata,
registration binding, gaps, duplicate numbering, predecessor replacement,
same-Work repetition, the seventh entry, exclusive-create races and unowned
Work. Empty and nonempty isolated mailboxes both prove observation preserves
mail, project memory and foreign STATE. Scripted fixtures do not enter the study.

Actual observation 2 is retained as runtime-002.json: T-144, BUILD, event 2139,
ROOT_OBSERVER, EMPTY. The sequence-002.json receipt reports 2 observations,
2 qualifying boundaries, 0 eligible opportunities and 0 independent assessments,
chosen revisions or successor executions. It does not reach the three-boundary
minimum yet. Receiver effort is UNKNOWN_NO_RECEIVER_OPPORTUNITY; independent
revision and successor execution are NOT_RUN; field improvement remains UNPROVEN.

The six-entry study is now technically executable. Independent enrollment,
registered comparable effort evidence and genuine later Work execution remain
open; no serialized-byte, command-count or latency proxy closes that objective.
