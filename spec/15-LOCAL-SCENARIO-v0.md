# FG-05 — END-TO-END LOCAL SCENARIO v0

Status: working. Contract for `lab/local_scenario.py`,
`tools/fg05_local_scenario.py` and `tests/test_local_scenario.py`.

## 1. Why this document exists

Every module below already has its own tests and its own spec. What none of them
proves alone is that the parts compose into one workflow: a typed record that is
sealed, delivered, deduplicated, scanned by header, explicitly opened, promoted as
a separate act, survived across a process restart, expired into a tombstone,
succeeded to a LEGACY successor, and paired with a HUMAN_PRIVATE branch that
reserves human attention exactly once. FG-05 is the joint contract. It is
integration evidence, not a framework, a live deployment, a GUI or a generative
experiment.

The scenario uses only public/stable project APIs (`saimail.envelope`,
`saimail.postoffice`, `saimail.promotion`, `saimail.legacy`, `saimail.sailetter`,
`saimail.human_attention`, `saimail.ally_advice`, `saimail.ally_generation`). It
never writes a database or a bundle directly to make a step green, and it never
monkeypatches a protocol gate away. Tests may inspect durable files for proof;
state transitions happen through the real operations.

## 2. Participants

Two isolated participants, A and B, each with:

* its own temporary root, Post Office, letter store and attention queue;
* its own sender (Ed25519), recipient (X25519) and human (P-256) identity;
* deterministic software keys derived by domain-separated hashing of a scenario
  label, so identity is reproducible and no hardware/host secret is involved.

There is no shared mutable directory that bypasses the protocol boundary, no FIDO
or hardware provisioning, and no operator-specific machine state. SENV2 minting
is randomised per transport object (D-028); the scenario therefore fixes
identities and assertions, not container bytes.

## 3. Core path

1. **Source → typed record.** One canonical `Record` (SAILANG) carries its own
   claim, evidence ref and uncertainty rung.
2. **Packaging.** `envelope.seal` produces the signed SENV2 container
   (D-028/D-034).
3. **Delivery.** `PostOffice.deliver` verifies sender and addressing and commits
   one immutable bundle plus one index row, without decrypting (D-031).
4. **Deduplication.** An exact re-delivery of an `ENVELOPE_ID` is `DUPLICATE` and
   keeps the original `RECEIVED_AT` (D-031).
5. **Header/discovery scan.** `PostOfficeSession.scan` reads index rows only,
   bounded by a declared scan budget, with a byte-offset continuation cursor
   (D-037).
6. **Explicit open.** `PostOfficeSession.open_message` is the only path that
   decrypts, and it moves `inbox/` to `read/` (D-037).
7. **Claim / evidence / uncertainty.** The opened payload is parsed back into the
   canonical record; the three data classes stay separate and travel into the
   promotion proposal.
8. **Promotion.** `promotion.propose` is a separate action over the exact
   `OpenedEnvelope` payload (D-035). Delivery and opening never imply promotion,
   and the gate never writes a card.

## 4. Failure and lifecycle proof

* **Restart.** After durable state exists, the participants' live objects are
  released and reconstructed from the same roots. Index rows, read/unread/expired
  state, tombstone, LEGACY entry, letter store and attention receipt must all
  survive; a replay after restart stays a duplicate; a message left unread can
  still be opened through the public API.
* **TTL / tombstone** (D-038/D-039). `sweep_expired` publishes an immutable
  tombstone before deleting the body. An expired object is `EXPIRED`, a re-delivery
  is `DUPLICATE`, and neither restart nor re-delivery resurrects the payload.
* **LEGACY succession** (D-040/D-041, FG-03 recovery). An adopted entry preserves
  source envelope identity, source seat and the `WATCH_NEXT:UNVERIFIED`
  uncertainty; successor rendering gains no authority. An interrupted adoption is
  detected and repaired through the authenticated recovery operation.
* **HUMAN_PRIVATE** (D-042). The letter is sealed, stored and opened explicitly;
  the synthetic private marker is absent from disk before and after opening. The
  receiver admits one attention candidate, re-admission is idempotent, and exactly
  one reserve/ACK pair is consumed.
* **NO_ADVICE / unverified advice** (D-046/D-047). A `NO_ADVICE` generation run
  invokes no reviewer and delivers nothing; a semantically unverified advice
  object cannot be converted (`ALLY_EVIDENCE_RESOLUTION_REQUIRED`) or resolved
  (`ALLY_EVIDENCE_MISSING`). Neither path consumes human attention.

## 5. Durable failure injection

Failures are injected at durable-write boundaries, not only at top-level
functions: bundle write, index commit, read-state transition, attention ACK
publication, LEGACY pair write and the tombstone-before-delete window. Every
injected failure must produce one of: a named refusal, an explicitly incomplete
and detectable state, or repair through the existing recovery operation. No
partial state is ever classified as success.

## 6. Side-effect contract

The scenario counts logical deliveries, durable message creations, duplicate
suppressions, explicit opens, promotions, attention reservations and
acknowledgements, tombstones and LEGACY adoption/recovery. Expected counts are
part of the contract, and a restart or retry must not raise them. The
machine-readable result (`LOCAL_SCENARIO_RESULT_1`) also carries participant
fingerprints, envelope identities, per-area proofs, the injected-failure
outcomes, the zero-network sentinel and a final status.

## 7. One command

```
python tools/fg05_local_scenario.py
```

It creates isolated temporary roots, runs the scenario, prints a bounded state
summary (never private payloads), and exits non-zero if any acceptance invariant
fails. `--out DIR` writes the JSON result and a markdown summary; `--keep`
retains the temporary roots. The pure engine is `lab/local_scenario.py`; the
runner `tools/fg05_local_scenario.py` owns the temporary-root lifecycle and the
socket tripwire, and records the observed connection-attempt count (zero) as
offline proof. The LAB isolation contract keeps `socket`/`shutil` out of
`lab/`.
