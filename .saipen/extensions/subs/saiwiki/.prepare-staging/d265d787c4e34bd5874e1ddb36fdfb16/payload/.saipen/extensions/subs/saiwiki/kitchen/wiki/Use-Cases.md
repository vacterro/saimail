# Use-Cases

Worked patterns, each pointing at the module that owns it. The full
walkthroughs with test names are in the spec; this page is the map.

| # | Pattern | What the code does |
|---|---|---|
| 1 | Send a verifiable claim | Build a SAILANG record, canonicalize it, sign a SENV2 container — the receiver verifies before it can decrypt (`sailang`, `saimail.envelope`) |
| 2 | Filter a mailbox without a model | The deterministic R1 selector classifies every header `IGNORE` / `OPEN_R2` / `OPEN_R3` from typed views only (`saimail.selector`) |
| 3 | Prove a command-looking payload stays inert | Invariant I1: shell text, protocol commands, JSON/tool-call frames inside a payload are data on every public path, under a tripwire proven by a deliberately vulnerable router |
| 4 | Promote a verified payload into memory | `promotion.propose(record, opened)` proceeds only when the record byte-equals the decrypted plaintext; emits a KNOWLEDGE card proposal, never writes a card (`saimail.promotion`, D-035) |
| 5 | Deliver durably, scan cheaply | The Post Office persists one immutable bundle plus a receipt per accepted envelope, appends one canonical index row, and scans headers only — no payload reads, no model calls (`saimail.postoffice`) |
| 6 | Let retention expire a message honestly | An explicit sweep publishes an immutable tombstone before deleting the body; a corrupt tombstone can never mask a missing body (`saimail.postoffice`, D-038/D-039) |
| 7 | Hand experience to a successor | A LEG1 packet rides SENV2 `K=EXPERIENCE`; the successor's store adopts it only from the exact `OpenedEnvelope` payload and keeps observed scope separate from new task scope (`saimail.legacy`, D-040/D-041) |
| 8 | Write a private letter to a human | HLET1 plaintext sealed in HENV1 to one human's P-256 identity, sender signature verified before any recipient private-key work, stored ciphertext-only (`saimail.sailetter`, D-042) |
| 9 | Keep the decryption key in hardware | The same provider seam over an existing PIV P-256 slot: read-only discovery, one explicit session per ECDH, honest policy classification (`saimail.hardware_piv`, D-043) |
| 10 | Ask for a human's scarce attention | A receiver-local queue with a rolling budget and reserve-then-ACK delivery; the sender assigns nothing and zero messages is a valid success (`saimail.human_attention`, D-044/D-045) |
| 11 | Find a message without opening it | The metadata-only inbox query: exact AND filters, declared scan budget, byte-offset continuation cursor, no decrypt/open/mutation (`saimail.inbox_query`, spec/22) |
| 12 | Use the same workflow as a desktop app | One native messenger window over the unchanged backend: explicit Open, explicit Refresh, READ-gated Reply, persistent status strip, zero network calls (`saimail.gui_adapter`/`gui_app`/`gui_theme`, V5-01) |
| 13 | Cite one SAIPEN LOG line by hash | The S2 seam mints a `KIND:O` record whose `EV` is the sha256 of one exact LOG line; the text never travels and the reader re-hashes to verify (`saimail.saipen_bridge`, D-057) |
| 14 | Tell one running agent one thing | A SAITELEME — one sealed SENV2 message on an existing kind, acting-seat-only, read header-only at turn entry (`saimail.saipen_bridge`, spec/26, D-058) |
| 15 | Survive a crash mid-send | The durable outbox keys the send by an idempotency key, seals once and replays identical bytes; the same key is never a second logical message (`saimail.outbox`, D-060) |
| 16 | Route automation only to admitted seats | The participant registry pins each admitted seat's identity and its subset of the closed trigger set; resolution never falls back (`saimail.participants`, D-061) |
| 17 | Send one automatic notification per fact | `notify` fires one telegram for a closed trigger to an admitted participant, kind fixed by the trigger, under a receiver attention budget that suppresses silently over cap (`saimail.notify`, D-063) |
| 18 | Negotiate the channel without a key | The capability document reports per-capability health with a closed reason set, exits 0 in every state, and reveals nothing to the wrong seat (`saimail.capabilities`, D-062) |
| 19 | Ask another agent for actual work | A `SAIMAIL_LETTER_1` carries an observation, an impact, a request, a completion criterion and evidence on the unchanged SENV2 transport, routed by `l.<lineage>.<recipient Work>` so a shared mailbox cannot leak one project into another (`saimail.letters`, D-066) |
| 20 | Learn whether the letter was any use | The receiver records one closed decision with its own closed reason; `RESOLVED` needs current result evidence and delivery or reading records nothing, so silence is never mistaken for acceptance (`saimail.correspondence`, D-066) |
| 21 | Return the outcome to the sender | `report` seals the latest explicit decision back to the authenticated original sender through the same durable outbox; a revised decision gets its own issue identity and preserves the earlier letters (`saimail.correspondence`, spec 33) |
| 22 | Let the next session skip the re-derivation | An explicitly retained unexpired `RESOLVED` case enters the successor reserve; a later agent or a different Work finds it by exact file scope, keylessly and without opening a body — as a recommendation to recheck, never as memory (`saimail.correspondence`, D-066) |
| 23 | Keep the human's keys behind a password, and still be able to recover them | `saimail.keyvault` wraps the existing identity material with scrypt + AES-256-GCM without changing a fingerprint or the mail format, and a separate recovery backup under its own random key means a forgotten password does not destroy the identity (`saimail.keyvault`, spec 34) |
| 24 | Integrate from a project maintained independently | `saimail-local --contract` returns the static versioned negotiation document; `HostClient` runs awareness/dispatch/review/decision/retain/report/metrics/cycle from its own allowlist with `shell=False`, a timeout and output caps, and reports `DEGRADED` instead of guessing (`saimail.host_contract`, `saimail_host`, D-066) |

## The one behind all of them

Message authorship is cheap and authority is never conferred by arrival. A
private channel drops operational boilerplate — a personal letter may simply
be prose — but it never relaxes safety or authority boundaries: invariant I1
applies unchanged, and decrypted prose is data everywhere.

ALLY_ADVICE (D-046) is the deliberate extreme of the same principle: a
private reflection that must carry observations, unverified inference, a
proposal, cited counterevidence and uncertainty as structurally separate
sections, with agency fixed at `RECIPIENT_DECIDES`. No output is normal;
days with no valid personal letter are a valid successful state.

The correspondence loop (D-066) applies the same rule one level up: a letter
is a request, and a request that was delivered is still not a result. The
observable thing is the receiver's explicit decision, and a retained letter is
a reading recommendation for whoever comes next — never promoted knowledge, and
never a change to what an agent is allowed to do next.
