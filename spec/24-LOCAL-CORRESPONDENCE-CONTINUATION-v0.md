# V4-01 — LOCAL CORRESPONDENCE CONTINUATION v0

Status: working. Contract for `saimail.workspace.reply_message`, the filtered
`saimail-local reply` subcommand, and the focused tests in
`tests/test_local_correspondence.py` /
`tests/test_local_correspondence_acceptance.py`.

## 1. Why this document exists

The shipped local surface (`saimail-local init/identity/recipient/send/inbox/
open/custody/acceptance`) can find a prior message (P1) and open it, but a
response was an unrelated fresh send with no linkage to the message it answers.
The original sender therefore could not discover the response as a continuation
of that message through the existing metadata query filters. V4-01 adds the
smallest user-facing step that closes "answer what was found": one explicit
local `reply` operation that reuses only already-proven protocol semantics —
explicit open, the existing SENV2 `REF` header field, canonical send and the
existing `inbox --ref` metadata query.

It adds no protocol rule, no new wire field, no thread store, no second dedup
layer, no new cryptography and no network path.

## 2. Two relation domains, never collapsed

Correspondence and truth are different graphs. Both happen to carry a `sha256`
reference, which is exactly why they must not be conflated.

### Transport / correspondence relation — SENV2 `REF`

```
SENV2 REF = prior envelope identity
```

Meaning: this envelope is explicitly related to that prior transport message.
It carries no truth verdict. `spec/02-SAIENVELOPE-v0.md` already defines `REF`
as "related record or prior envelope"; V4-01 uses only the prior-envelope branch
of that existing meaning. `REF` is signed header metadata (it is inside the
SENV2 signature domain, D-029/D-034), so it is visible without decrypting the
message body. That visibility is intentional: it is what makes the existing
`inbox --ref` metadata query possible.

### SAILANG semantic relation — `SUPPORTS` / `REFUTES` / `CON`

Meaning: the authored record makes the corresponding semantic claim about
another immutable record (`spec/01-SAILANG-v0.md` section 4). These fields are
substantive statements about the referenced record and are never inferred from
correspondence.

```
REPLY != SUPPORTS
REPLY != REFUTES
REPLY != CON
```

A reply may independently carry one of those semantic relations only when the
operator explicitly supplies a canonical record that contains it. The reply
mechanism itself never adds, infers or guesses a semantic relation.

## 3. Command surface

```
saimail-local reply --workspace DIR --envelope ENVELOPE_ID --claim "one line"
saimail-local reply --workspace DIR --envelope ENVELOPE_ID --record RECORD.sailang
```

Exactly one content form is accepted, the same mutually exclusive forms `send`
already supports:

* `--claim TEXT` — one line of operator text, wrapped by the same deterministic
  operator-text contract `send` uses (section 6);
* `--record FILE` — an existing canonical SAILANG record file, sent as its own
  canonical bytes exactly as `send` already does.

Optional presentation fields follow the send conventions but stay narrow:
`--subject` (default `local-message`), `--topic` and `--kind`. Defaults:

* transport kind `PERSONAL_MESSAGE`;
* topic inherited from the original envelope `TOPIC` unless an explicit
  `--topic` is supplied.

The original transport kind is deliberately **not** inherited: a reply to a
`WARNING` is not automatically another `WARNING`.

There is no `--to`, `--thread`, `--conversation`, `--parent-chain` or
`--root-message`. The reply recipient is the original sender, resolved from the
target's own metadata; the caller cannot choose an arbitrary reply recipient.

## 4. Explicit-open prerequisite

`reply` is not a second decryption path. The target message must already be in
durable `READ` state, reached through the one explicit `open --envelope`
transition. Reply resolves the target from canonical index metadata plus durable
lifecycle state (section 5) and never reads or decrypts the target payload.

| Target state | Outcome |
|---|---|
| `READ` | proceed |
| `UNREAD` | `REPLY_TARGET_UNREAD` — open the exact envelope explicitly first; the target stays `UNREAD` and no reply is created |
| `EXPIRED` | `REPLY_TARGET_EXPIRED` — an expired message is never resurrected |
| `BOTH` | `RECONCILIATION_REQUIRED` — maintenance must prove pair identity first |
| `NEITHER` (indexed) | `INDEX_BODY_MISSING` |
| tombstone + live body | `EXPIRY_RECONCILIATION_REQUIRED` |
| invalid tombstone | `EXPIRED_TOMBSTONE_CONFLICT` |
| unknown envelope id | `REPLY_TARGET_UNKNOWN` |
| malformed envelope id | `BAD_INPUT` |

The operator flow is therefore `open -> reply`, and `open` remains the one
explicit read transition.

## 5. Target metadata authority

The reply target is resolved mechanically through the canonical Post Office
index (`saimail.postoffice.PostOffice.read_index_row` plus
`bundle_state`). The operation obtains, from the index row alone:

* the original `envelope_id`;
* the original sender seat (`from`);
* the original sender key fingerprint (`from_kid`);
* the original `topic`;
* the derived durable state.

Caller-supplied sender identity is never trusted, and no `--to` override exists.

## 6. Reply record

* `--claim` reuses the deterministic operator-text wrapper contract already used
  by `send`: `KIND:F SRC:HUMAN:<sender seat> SUBJ:<subject> CLAIM:<the line>
  TYPE:OBS EV:0 STATUS:U1 CREATED:<now>`. Reply text gets no extra authority: it
  stays evidence-absent, rung-capped, ordinary authored content. No SAILANG
  relation field is added.
* `--record` parses and validates the exact canonical record file exactly as
  `send` does, and never rewrites its semantic relation fields. A supplied
  record that legitimately contains `SUPPORTS`, `REFUTES` or `CON` is preserved
  unchanged.

## 7. Seal, delivery and discovery

The reply is sealed through the unchanged `saimail.envelope.seal` path with
`ref = ORIGINAL_ENVELOPE_ID`. No header field is added, no header order changes,
no signature domain changes, no encryption changes, no envelope-id computation
changes and no protocol version changes. The reply's `REF` is therefore signed
canonical header metadata and is indexed naturally by the recipient's existing
Post Office.

The reply container is stored in the sender's outbox exactly like an ordinary
send, and delivery reuses the unchanged recipient Post Office path. An exact
replay of the reply container through the existing `send --redeliver` is a
canonical `DUPLICATE` with the original `RECEIVED_AT`. Calling `reply` twice is
not idempotent: each newly sealed envelope is a new transport object, and that
is stated, not pretended otherwise.

The original sender discovers the reply through the existing P1 surface:

```
saimail-local inbox --workspace SENDER --ref <ORIGINAL_ENVELOPE_ID>
```

The query remains metadata-only, bounded, with zero payload reads and zero
implicit opens. Nothing reply-specific is added to P1.

## 8. Result contract

`LOCAL_WORKSPACE_COMMAND_1` (unchanged schema, `version = 1`) with
`command = "reply"`:

| Field | Meaning |
|---|---|
| `command` | `"reply"` |
| `status` | the canonical transport status (`ACCEPTED` / `DUPLICATE` / `QUARANTINED` / `REFUSED`) or a named refusal code |
| `target` | `envelope_id`, `state` (`READ`), `from`, `from_kid`, `topic` |
| `reply` | `envelope_id`, `ref`, `to`, `kind`, `topic`, `created`, `state` |
| `recipient` | the registered peer alias, seat and root the reply was delivered to |
| `delivery` | `status`, `reason`, `quarantine_id` |

The result never carries the original plaintext, the original claim, the reply
private key, a decrypted payload or peer private information. For `--record`,
the authored `content_id` is not returned, because the correspondence authority
is `SENV2 REF` to the original envelope id, not the record id.

## 9. Peer identity resolution

A local reply needs the original sender's recipient encryption key and workspace
root. Those are resolved only through the existing explicit peer registry
(`peers.json`), never by fuzzy alias matching, filesystem search, automatic
discovery or silent substitution. Resolution requires a registered peer whose
`seat` equals the original index row `from` **and** whose `sender_kid` equals
the original row `from_kid`:

* no peer with that seat → `REPLY_RECIPIENT_UNKNOWN`;
* a peer with that seat but a different `sender_kid` → `REPLY_RECIPIENT_MISMATCH`
  (fail closed; the reply is never redirected to another identity merely because
  a seat label matches).

The registered peer's workspace marker is re-validated through the existing
recipient-office path, so a changed or foreign peer workspace still fails closed
with the existing `DELIVERY_TARGET_UNAVAILABLE` / `RECIPIENT_IDENTITY_MISMATCH`
semantics.

## 10. One-hop composition

* **Multiple replies.** More than one reply may set `REF` to the same original
  envelope id. The existing bounded `inbox --ref` query returns all matching
  reply envelopes; there is no thread store and no conversation registry.
* **Reply to reply.** A reply may itself be opened and replied to, so `REF`
  chains form naturally (`X`, then `Y` with `REF X`, then `Z` with `REF Y`).
  V4-01 does not recursively traverse the chain and introduces no thread root,
  thread depth or conversation id; those may exist only later, if an observed
  need justifies them.

## 11. Backward compatibility

`send`, `inbox`, the bounded inbox query, `open`, `redeliver` and `custody`
retain their existing contracts. `send` is not changed to require `REF`: an
ordinary send continues with `REF` absent unless an existing lower-level caller
constructs it otherwise. No historical `REF` value is reinterpreted.

## 12. Security boundary and honest limits

* `SENV2 REF` is signed header metadata and is visible without decrypting the
  message body. Correspondence linkage is intentionally **not** private
  metadata; moving `REF` into the plaintext to hide it would break the existing
  `inbox --ref` discovery, which depends on indexed header metadata.
* Reply exposes no additional content: no original plaintext, claim or
  decrypted payload ever appears in a result.
* Fully offline: zero network, model, provider, hardware or other external
  calls.

## 13. What this does NOT claim

V4-01 is one-hop correspondence continuation, not a conversation system. It does
not promise threads, chat, a conversation database, a topic or subject search,
automatic correspondence, model-generated replies, automatic recipient
discovery, remote delivery, a GUI, or any change to SENV2, custody, delivery,
read/open, selector, attention or ignore semantics. `REPLY` is a relationship
between messages; it is not automatically a claim about truth.
