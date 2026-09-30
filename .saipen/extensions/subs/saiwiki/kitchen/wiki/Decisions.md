# Decisions

Every entry in [spec/DECISIONS.md](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS.md)
resolves a contradiction or an open question in the derived spec, and records
what was chosen and why. This page is the index; the file is the authority.
D-051..D-065 live in their own additive pages
([spec/DECISIONS-D051.md](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D051.md)…)
to keep the frozen parent file exact-hash stable.

| Decision | One line |
|---|---|
| [D-001](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS.md) | no free-text motive field — `INTEREST_REF` points at evidence, never at an inferred motive |
| D-002 | the line is a lossy triage projection; the record is canonical |
| D-003 | full cryptographic identity: `sha256` over canonical bytes, no self-reference, no hidden normalization |
| D-004 | `D` (decision) deferred out of v0; kinds are `F O H G V` |
| D-005 | no self-declared novelty or trust |
| D-006 | promotion is kind-aware |
| D-007 | T-9 may not be rigged |
| D-008 | `C` and `D` are ledger verdicts, not authored rungs |
| D-009 | `EV` is required for truth-apt records; omission is not silence |
| D-010 | a triage frame is machine-decodable; only reconstruction is forbidden |
| D-011 | profile framing is paid once, and the v0 line is kept as a baseline |
| D-012 | atom, wire and render are three different things |
| D-013 | raw wire is not decodable; the container establishes the binding |
| D-014 | one dependency contract, and the advertised command honours it |
| D-015 | profile identity is not profile acceptance |
| D-016 | one semantic atom, one canonical wire encoding |
| D-017 | a receipt's intake kind is transport; segments are authorship |
| D-018 | live agent output is experiment data, and the harness may not contradict itself |
| D-019 | a credential is resolved from a named handle, never inherited from the environment |
| D-020 | participants are discovered from the population, not pinned in source |
| D-021 | a frame ABI version is bumped when evidence semantics change |
| D-022 | observed scope is not successor scope, and a measurement is not a score |
| D-023 | a credential-bearing receipt keeps its identity, not its distribution |
| D-024 | a live run is named by its membership evidence, never by its participants' eligibility |
| D-025 | one response is not a model property |
| D-026 | a control that has never been seen to fail proves nothing |
| D-027 | a slash in prose is not a path |
| D-028 | SENV1 v0: wire, signature domain, key identity and crypto construction |
| D-029 | SENV1: no forward-secrecy claim, and one bound signature domain |
| D-030 | recipient key acceptance is receiver-owned; open binds seat, fingerprint and private key |
| D-031 | Post Office preconditions: transport identity, `CREATED` vs `RECEIVED_AT`, duplicates, the pending attention floor |
| D-032 | one envelope, one byte representation, one transport identity |
| D-033 | SENV1 authenticates the sender of the container, not the author of the payload |
| D-034 | SENV2: the sender identity is bound into the sealed layer |
| D-035 | an authenticated container is not an authenticated record |
| D-036 | `MACHINE_REQUIRED_OPEN` is a non-downgradable attention floor |
| D-037 | Post Office v0: deterministic header attention, monotone model merge, exact budgets |
| D-038 | TTL expiry is receiver-owned retention: tombstone before delete, no resurrection |
| D-039 | a tombstone proves the object it represents; expiry converges in one pass |
| D-040 | LEG1 is evidence-bound operational transfer without authority gain |
| D-041 | successor provenance and recency are receiver-validated state |
| D-042 | HUMAN_PRIVATE v0: HLET1/HENV1, explicit recovery, a ciphertext-only letter store |
| D-043 | hardware custody: PIV P-256 ECDH, read-only discovery, honest presence semantics |
| D-044 | HUMAN_ATTENTION_BUDGET v0: receiver-owned scarcity, reserve-then-ACK delivery |
| D-045 | B-011 correction: receiver time authority is mechanically queue-owned |
| D-046 | ALLY_ADVICE v0 is a private, evidence-citing proposal with recipient agency |
| D-047 | ALLY_ADVICE generation v0 is caller-supplied, single-attempt and review-bound |
| D-048 | a reviewed type-state requires an actual reviewer invocation; evidence-bearing PASS cites corpus refs |
| D-049 | `EVENT_REF` declares the underlying event; generated repeated-pattern advice needs two distinct declared events |
| D-050 | the real-project corpus builder is explicit-only, mints its identities and proves no completeness |
| [D-051](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D051.md) | credential assignments cannot cross a blank line (T-65) |
| [D-052](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D052.md) | the local alpha candidate is an exact hashed artifact, not a version number (T-86 / V2-04) |
| [D-053](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D053.md) | workspace identity key custody is a named mode, and the OS store is the protected one (T-89 / V3-01) |
| [D-054](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D054.md) | the next distributed candidate keeps raw custody as default, and its identity is 0.0.2a2 (T-90 / D1) |
| [D-055](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D055.md) | D2 freezes 0.0.2a2 as the post-V3-01 candidate, with the first-run custody notice and a separate evidence identity (T-91 / D2) |
| [D-056](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D056.md) | D3 freezes 0.0.2a3 as the post-GUI candidate, with an additive a3 evidence identity and no inherited a2 proof (T-106 / D3) |
| [D-057](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D057.md) | the SAIPEN seam S2 bridge reads caller-named evidence, binds the acting seat, and cites a LOG line by hash only (T-108 / S2) |
| [D-058](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D058.md) | SAITELEMES v0 is an ordinary sealed message on existing kinds, sent only by the acting seat, read header-only at turn entry (T-109) |
| [D-059](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D059.md) | header-only reads load a secret-free view; the SAIPEN turn-entry read never touches custody (T-117) |
| [D-060](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D060.md) | sends are durable intents keyed by an idempotency key; seal once, replay bytes (T-119) |
| [D-061](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D061.md) | automation routes only to explicitly admitted, identity-pinned project participants (T-120) |
| [D-062](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D062.md) | SAIPEN negotiates the mail channel through one never-failing, keyless, seat-checked capability document (T-121) |
| [D-063](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D063.md) | automatic telegrams: closed triggers, admitted recipients, one message per fact, a receiver budget (T-122) |
| [D-064](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D064.md) | every operator workshop rule is bound to a mechanism and a named live control (T-118) |
| [D-065](https://github.com/vacterro/saimail/blob/main/spec/DECISIONS-D065.md) | a contended lock initialization is waited for, never an I/O failure (T-123) |

Two decisions carry their own spec pages: [HUMAN_ATTENTION_BUDGET v0](https://github.com/vacterro/saimail/blob/main/spec/07-HUMAN-ATTENTION-v0.md)
(D-044/D-045) and [ALLY_ADVICE v0](https://github.com/vacterro/saimail/blob/main/spec/08-ALLY-ADVICE-v0.md)
(D-046). The wire objects themselves are indexed in [Protocols](Protocols.md).
