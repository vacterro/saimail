# Architecture

One mail path, one evidence discipline, one authority ladder.

## The path a message takes

```
SAILANG record (canonical, content-addressed)
        |
        v
SENV2 .senv container   -- clear header, Ed25519 signature, X25519 sealed payload
        |
        v
Post Office             -- durable delivery, append-only index, header-only scan
        |                  (no payload decryption, no recipient private key)
        v
open (explicit)         -- receiver-side verification, then decryption
        |
        v
promotion (kind-aware)  -- the ONLY way a message becomes durable memory
```

Every arrow is a named module with a contract. The [Modules](Modules.md) page
lists them; the [Decisions](Decisions.md) page lists the contracts.

## The discipline

| Rule | Meaning |
|---|---|
| `message != memory` | Durable memory requires promotion, and promotion is kind-aware: evidence for facts and observations, a falsification condition for hypotheses, provenance alone for goals and values. |
| Informational, not constitutional | A private message can say anything and authorise nothing. Payload text that looks like a command is inert (invariant I1, red-tested). |
| Observable but private | Content can be sealed; traffic never is. |
| No intent claims | The strongest verdict about a statement is `CONTRADICTED`. There is no verdict about a person. |
| The record is the authority | A triage frame is decodable but never authoritative, never evidence, and never reconstructs what it omitted. |
| Reference exists != reference supports the claim | An evidence ref records what was cited; it does not prove support (D-040, D-046). |

## Where the authority lives

```
AUTHORITATIVE RECEIPT LINEAGE > DERIVED SPEC > IMPLEMENTATION > TESTS
```

`idea.md` and `idea_continue1.md` (then named `idea_continue.md`) are the
receipts (`.saipen/intake/active/SRC-003.md`, `SRC-004.md`; `SRC-001`/
`SRC-002` were a capture mistake that recorded the file paths instead of the
bodies, and are kept as the amended originals rather than rewritten).
Everything under `spec/` is derived interpretation and may be revised;
`spec/DECISIONS.md` records every revision and why. Where a spec disagrees
with a receipt, the receipt wins.

## Three memory tiers

Hot working memory, the durable promoted store, and the immutable
append-only record. Promotion moves a statement between tiers; it never
edits one. Forensic history is never tidied: a promoted record that is later
contradicted is marked and kept.

## The SAIPEN seam and the automation layer

The mail path above is the frozen wheel. The current checkout adds one seam
and an automation layer on top of it, without touching the wire:

```
SAIPEN LOG line ── S2 bridge ──> KIND:O citation (EV = sha256 of the exact line)
        │
        v
participant registry ── admitted seats only, identity pinned, closed triggers
        │
        v
notify / telegram ──> durable outbox ──> the same SENV2 send + Post Office
```

The S2 bridge reads only caller-named evidence and cites a LOG line by hash;
the participant registry decides who automation may address; the durable
outbox makes a send crash-safe by keying it and sealing once. None of these is
a new wire object — a SAITELEME is an ordinary sealed SENV2 message (D-058),
and the registry, outbox, capability document and work brief are local at-rest
JSON, not containers. See [Protocols](Protocols.md) for the split.

## The correspondence loop (D-066)

Above the mail path, the checkout adds a loop that turns a message into an
observed outcome. It is one turn of a cycle, and every arrow is explicit:

```
observation + request + done_when + evidence  (a SAIMAIL_LETTER_1, sealed SENV2,
        |                                       topic l.<lineage>.<recipient Work>)
        v
durable outbox ──> receiver Post Office ──> explicit review (recheck evidence)
        |                                                  |
        |                                                  v
        |                                    receiver decision: one closed
        |                                    DECISION + closed REASON; RESOLVED
        |                                    needs current result evidence
        v                                                  |
sealed report back to the sender  <── report ───────────────┤
                                                                   v
                                              retain (only unexpired RESOLVED
                                              with current evidence)
                                                                   |
                                                                   v
                                     successor desk discovery (keyless, by
                                     exact file scope) ──> a reading
                                     recommendation that always asks for a
                                     recheck
```

Three properties hold at every arrow. **Reading proves nothing** — delivery and
opening record no outcome, so a sender never mistakes silence for acceptance.
**The reserve is not memory** — a retained letter is a recommendation to look,
not promoted knowledge and not lifecycle authority, and a retained flag never
certifies that the evidence is still current. **The host owns the lifecycle** —
the loop returns suggestions and measurements, and a human or the host decides
what to do. A bounded, keyless `cycle` / `focus` entry lets an independently
maintained host take all of it in one call, through commands from its own
allowlist rather than anything a message advertises.
