# LEGACY v0

LEGACY is a SAIMAIL host-protocol object for bounded operational transfer. It
is not a SAILANG kind, fact, task, command, log dump, KNOWLEDGE card, or source
of authority. A packet records what one predecessor says it observed and what
it wants a successor to inspect; authentication identifies the accepted
sender of the container, not the truth of those statements.

## 1. Transport and object boundary

A transported packet is the exact plaintext of one canonical SENV2 envelope:

```
K:EXPERIENCE
TOPIC:legacy
```

No SENV3 or SAILANG ABI variant is introduced. `SUBJECT` remains inside the
packet. Opening such an envelope only returns `OpenedEnvelope`; durable LEGACY
state requires a separate explicit adoption operation.

## 2. Canonical LEG1 bytes

The one accepted representation is UTF-8 without BOM, LF only, with a final
LF and exactly this order:

```
LEG1
SUBJECT:<machine-token>
OBSERVED_SCOPE:<text>
WHAT_WORKED:<text>
WHAT_WORKED_EVIDENCE:<sha256 refs>
WHAT_FAILED:<text>
WHAT_FAILED_EVIDENCE:<sha256 refs>
WHAT_LOOKED_RIGHT_BUT_WAS_WRONG:<text>
WHAT_WRONG_EVIDENCE:<sha256 refs>
WATCH_NEXT:<text>
WATCH_NEXT_EVIDENCE:<sha256 refs or 0>
WATCH_NEXT_STATUS:UNVERIFIED
CREATED:<YYYY-MM-DDTHH:MM:SSZ>
```

`SUBJECT` is 1-128 ASCII lowercase letters, digits, or hyphens, starts with a
letter or digit, and has no whitespace, path, shell, or wildcard semantics.
Every text field is non-empty, single-line UTF-8 data. No value is trimmed or
Unicode-normalized. Each value is at most 4096 UTF-8 bytes and the complete
packet at most 32768 bytes.

Evidence references are `sha256:<64 lowercase hex>`, sorted bytewise and
unique. The three outcome sections require at least one reference.
`WATCH_NEXT_EVIDENCE` is either one or more references or the literal `0`;
the field is never omitted. `WATCH_NEXT_STATUS` has the sole v0 value
`UNVERIFIED`. A syntactically valid reference establishes `REFERENCED`, not
that the object is available or supports the claim.

Unknown, missing, duplicated, reordered, noncanonical, over-bound, or invalid
fields are refused. Command-looking text in any prose field remains inert
data and never enters command routing.

## 3. Identity and authenticated adoption

```
LEGACY_CONTENT_ID = "sha256:" + hex(SHA-256(exact canonical LEG1 bytes))

LEGACY_ENTRY_ID = "sha256:" + hex(SHA-256(
    b"SAIMAIL-LEGACY1-ENTRY\0"
    + source_envelope_id.encode("ascii")
    + b"\0"
    + exact canonical LEG1 bytes
))
```

The second NUL is the exact boundary between the fixed-form source envelope
identity and packet bytes. Identical content received in two envelopes is two
provenance events.

Only `OpenedEnvelope` can mint authenticated LEGACY. The adoption gate parses
its plaintext canonically, proves exact equality with the supplied packet, and
requires `K=EXPERIENCE` and `TOPIC=legacy`. Raw bytes, `Header`,
`VerifiedEnvelope`, and caller-supplied sender strings are insufficient. The
proof type uses a constructor-only `InitVar` mint; `dataclasses.replace()`
cannot transplant it. This is normal-public-API correctness, not hostile
process security.

## 4. Durable store

Explicit adoption publishes:

```
mail/legacy/<recipient-seat>/<LEGACY_ENTRY_ID digest>/
    packet.leg1
    provenance.json
```

`packet.leg1` is the exact canonical bytes. The canonical receiver-owned JSON
records schema, entry/content ids, source envelope id, accepted sender and key
id, recipient, original `received_at`, and `adopted_at`. Both files use
immutable no-overwrite publication. Exact repeat is `ALREADY_ADOPTED`; any
different committed bytes at that identity are a conflict. No private key,
unrelated plaintext, chain-of-thought, score, or confidence is stored.

The source envelope may later expire. Adopted LEGACY remains: provenance was
recorded at adoption, not a promise that the transport body remains forever.
Adoption never calls promotion and creates no KNOWLEDGE card or verdict.

## 5. Successor consumption

Retrieval is exact `SUBJECT` matching, ordered by receiver-owned
`received_at` descending and `legacy_entry_id` descending as the deterministic
tie-breaker (D-041). Sender-authored `CREATED` remains visible packet metadata
but never controls retrieval recency. Every matching predecessor remains
separate; disagreement is neither merged nor voted into consensus.

The caller supplies `NEW_TASK_SCOPE`; the immutable packet supplies
`OBSERVED_SCOPE`. A deterministic bounded context renders both labels,
preserves the four sections and exact evidence refs, labels failure
`FAILED_IN_OBSERVED_SCOPE`, and retains
`WATCH_NEXT_STATUS:UNVERIFIED`. It reports entry/byte bounds and explicit
continuation metadata whenever history is truncated.

A continuation is the `legacy_entry_id` of the final included entry. The next
page re-reads the current exact-subject set and continues strictly after that
anchor in receiver-owned order. An unknown anchor or one belonging to another
subject refuses as `LEGACY_BAD_CONTINUATION`. A new entry inserted ahead of
the anchor appears on a fresh request; it cannot shift the cursor, repeat a
returned entry, or hide a pre-existing older one. `TOTAL_MATCHES` is the
current durable exact-subject count, not a snapshot claim.

Every successful truncated page includes at least one new complete entry and
returns a cursor different from the one it consumed. If metadata fits but the
next complete entry does not, rendering refuses with
`LEGACY_CONTEXT_ENTRY_TOO_LARGE`; it never emits a zero-progress page.

Rendering returns data only. It creates no task or ticket, mutates no SAIPEN
state, runs no command or tool, calls no model or network, infers no evidence,
and assigns no truth rung. In particular:

```
OBSERVED_SCOPE != NEW_TASK_SCOPE
REFERENCE_EXISTS != REFERENCE_SUPPORTS_CLAIM
LEGACY != AUTHORITY
```

The S5 laboratory motivated the retained scope, qualifier, invented-evidence,
suspicion-hardening, and first-step checks. Production neither imports the lab
nor claims that the deterministic renderer improves model performance.
