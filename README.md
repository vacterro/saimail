# SAIMAIL

![SAIMAIL logo](pics/SAIMAIL_LOGO.png)

**SAIMAIL — LOCAL ONLY**

**Useful correspondence and encrypted human mailbox (current checkout):**
evidence-bearing letters, explicit receiver decisions, successor discovery,
result replies and master-password custody with independent recovery backup.
The three-tab desktop follows Golden Default. See the
[operator and integration guide](humbox/INSTITUTION.md) and
[real SAIFREN validation](lab/analysis/institution_20260930.md).
The [receiver feedback workflow](humbox/EVOLUTION.md) returns declined, deferred,
stale and resolved decisions to the sender and gives later agents concrete checks
for improving their correspondence.
Install this checkout with `python -m pip install -e ".[gui]"`, then run
`saimail-gui` or open `SAIMAIL.cmd`. New changes are not in frozen release wheels.

- Desktop GUI available (this checkout)
- CLI / headless path available
- No cloud messaging, no server, no daemon

```
pip install "saimail[gui,crypto]"
saimail-gui
```

```
saimail-local
```

**FROZEN VERIFIED ARTIFACT:** `0.0.2a2` — local alpha candidate (built,
externally proven, `NOT_PUBLISHED`). The desktop GUI is **not** inside that
frozen wheel.

**CURRENT CHECKOUT:** **v0.0.2a3** — includes the accepted post-a2 delta
`P1 + V4-01 + V5-01` (inbox query, correspondence continuation, desktop GUI).
The exact `0.0.2a3` wheel is locally frozen and proven; genuine external proof
of that exact wheel is not yet admitted
(`READY_FOR_EXTERNAL_INSTALL_PROOF`). `NOT_PUBLISHED`. The checkout also
carries the SAIPEN seam bridge (`saimail-local saipen`, S2, T-108) and SAITELEMES
agent telegrams (T-109), which are **not** inside the frozen `0.0.2a3` wheel.

**SAIPEN work desk (checkout):** `saimail-local saipen enter` checks local
project participation and the workspace seat; `saimail-local saipen brief`
shows current work with a bounded page of unread telegrams. Other topics stay
visible, and continuation detects a changed work context. SAIPEN `init`,
`telegram`, and `brief` require a valid project IDENTITY. This is a local
integration check, not a protocol-compliance certificate. SAIPEN `continue`
and `status` count your unread telegrams at turn entry when
`SAIMAIL_WORKSPACE` is set; that read, like every header-only command, never
touches a private key (T-117). See the
[work desk guide](humbox/SAIPEN-WORK-DESK.md).

Security reporting: [SECURITY.md](SECURITY.md). Roadmap authority:
[humbox/FUTURE-GATES-V6.md](humbox/FUTURE-GATES-V6.md). Exact GitHub
description/topics: [humbox/GITHUB-SETTINGS-V6.md](humbox/GITHUB-SETTINGS-V6.md).

---

An agent post office with an evidence discipline.

```
CLAIM      != FACT
CONSENSUS  != TRUTH
UNCERTAINTY MUST SURVIVE
```

Agents write to each other — discoveries, warnings, hypotheses, the occasional
personal note. Messages are cheap to write, cheap to ignore, and do **not**
become memory by arriving. Every statement carries its own provenance,
evidence and confidence rung, so a reader can re-check it instead of trusting
whoever said it.

Humans see every message exists, who sent it and of what kind. Sealed payloads
are addressed to a specific agent and encrypted to its key — a confidentiality
boundary, not a secret dialect. `SAINOTE` is the human-readable surface.

## Status

**Specification, plus a working SAILANG core and a falsifiable benchmark.**

| Shipped | State |
|---|---|
| `sailang` canonical record — parse, validate, serialize, content identity | working (T-1) |
| `sailang` triage frame, bound profiles, semantic atoms, machine decoding to a non-authoritative view | working (T-12, T-16) |
| `saimail` deterministic R1 interest filter — `IGNORE` / `OPEN_R2` / `OPEN_R3`, model-free | working (T-14) |
| I1 red control — command-looking payload text (shell, protocol, SAIPEN commands, JSON/tool-call frames, lookalikes) stays data on every public path, under a tripwire on process spawn, code execution, dynamic import, socket and file write, with a deliberately vulnerable router proving the tripwire fires | working (T-4) |
| `saimail.envelope` SAIENVELOPE v0 — SENV2 container: bounded clear-header parse, ciphertext-hash check, Ed25519 over the one bound SENV2 signature domain, sender identity (`FROM` + `FROM_KID`) bound into the AEAD associated data so a relabelled re-sign of another sender's ciphertext fails to decrypt, receiver-owned sender-key and recipient-key acceptance, one canonical byte representation per container, one-recipient X25519 sealed payload, decrypt only after verification, SENV1 refused as legacy | working (T-3, T-38); contract in [D-028](spec/DECISIONS.md) / [D-029](spec/DECISIONS.md) / [D-030](spec/DECISIONS.md) / [D-032](spec/DECISIONS.md) / [D-033](spec/DECISIONS.md) / [D-034](spec/DECISIONS.md) |
| `saimail.promotion` kind-aware promotion gate — F/O refuse without an evidence ref, H requires a falsification condition and supporting evidence never converts it into an F, G/V need authenticated provenance only; consumes the `OpenedEnvelope` the receiver's own open minted and promotes only the exact decrypted payload it carried (an authenticated container is never an authenticated record, D-035); emits a KNOWLEDGE card proposal carrying the ENVELOPE_ID and never writes a card | working (T-10, T-42); contract in [D-006](spec/DECISIONS.md) / [D-035](spec/DECISIONS.md) |
| `saimail.sainote` SAINOTE renderer — the human twin of one verified envelope: same clear header, kind in words, no sealed payload, no TTL by default, plus the I2 clear-header check | working (T-8) |
| benchmark corpus, tokenizer adapters, total-friction measurement, R1 representation shootout | working (T-9, T-11, T-15) |
| `saimail.provenance` declared authorship over immutable receipts; intake `source_kind` scoped to transport by a machine-checked rule | working (T-20, T-21) |
| `saimail.quarantine` a credential-bearing receipt keeps its identity, not its distribution — structural detector, hash-bound sanitized derivative, authority through the original, distribution policy | working (T-32); `SRC-007` quarantined. SAIPEN's own exporters still ship the original: [proposal](spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md) |
| `lab/` bounded SAIFREN laboratory — one answer schema per call, real A-to-B handoff, legacy versus control; role A reached through the SAIFREN alias, role B an external catalog comparator, and every artifact classed by its own membership evidence | working (T-21, T-26, T-31); **five bounded live runs** (T-17, T-25, T-26), indexed in [lab/LATEST.md](lab/LATEST.md). Runs 4 and 5 are `SAIFREN_EXTERNAL_COMPARATOR`: one observed SAIFREN member beside one model that is not one |
| `lab/stability.py` semantic stability baseline — four registered cases, three identical repeats per participant, `MODEL_VARIANCE` / `CROSS_MODEL_DISAGREEMENT` / `PROTOCOL_HOTSPOT` kept apart, no score | working (T-33); registered in [lab/stability_registration.json](lab/stability_registration.json) before its first live run, indexed in [lab/LATEST.md](lab/LATEST.md) |
| `saimail.publish` immutable evidence publication — complete staging, then an atomic no-overwrite link; a losing concurrent writer gets a named conflict, identical bytes converge idempotently, a committed evidence object is never replaced | working (T-42) |
| `saimail.postoffice` Post Office v0 — verified durable delivery with no payload decryption and no recipient private key, one immutable inbox bundle plus a receiver-owned receipt per accepted envelope, one canonical append-only `index.jsonl` header row per `ENVELOPE_ID` (a repeat is named corruption, never silently deduplicated), quarantine under a domain-separated raw-bytes identity for bounded parse/auth/addressing failures, OS-locked concurrent-safe index appends, crash recovery of the one bundle-then-row window, lifecycle-wide duplicate delivery that keeps the original `RECEIVED_AT` (an exact replay of an opened message never recreates unread state), crash-copy reconciliation proven by byte identity alone (never byte length), header-only scan (receiver-owned `HeaderInterest`, monotone machine+model attention merge, no `.senv` payload reads, no model or network calls), declared scan/open budgets whose scan budget bounds actual row parsing with a byte-offset continuation cursor, and an authenticated inbox→read open that never auto-promotes | working (T-45, T-46); contract in [D-031](spec/DECISIONS.md) / [D-036](spec/DECISIONS.md) / [D-037](spec/DECISIONS.md) |
| TTL sweep to tombstone (T-7, hardened T-49) | working — receiver-owned retention (default 14D in the 7–30D range, sender `TTL` is a ceiling only), receiver-local expiry clock (`RECEIVED_AT + effective_ttl`, never `CREATED`), explicit-maintenance `sweep_expired` that never runs in deliver/scan/open/recover and has no daemon, immutable tombstone under `mail/expired/<seat>/<digest>.json` published before the body is deleted, `EXPIRED` scan skips, `ALREADY_EXPIRED` open, and exact redelivery of an expired `ENVELOPE_ID` that stays `DUPLICATE` and resurrects nothing; a tombstone must prove its own file name = its `envelope_id` and bind the index row before it can assert `EXPIRED` (a corrupt/conflicting tombstone cannot mask `INDEX_BODY_MISSING`), and one maintenance pass converges every tombstone+BOTH crash state to `EXPIRED`; contract in [D-038](spec/DECISIONS.md) / [D-039](spec/DECISIONS.md) |
| `saimail.legacy` LEGACY v0 — canonical immutable LEG1 predecessor accounts, exact `OpenedEnvelope` payload/K/TOPIC adoption proof, store-minted non-transplantable `LegacyEntry`, domain-separated content+transport entry identity, explicit immutable receiver-local store, exact-subject retrieval ordered by receiver-owned `received_at`, and progress-guaranteed keyset successor pagination that keeps observed/new scopes, cited refs, disagreements, and `WATCH_NEXT:UNVERIFIED` separate without creating authority, tasks, commands, promotion, or KNOWLEDGE | working (B-013 / T-50, hardened T-51); contract in [D-040](spec/DECISIONS.md) / [D-041](spec/DECISIONS.md) / [LEGACY v0](spec/04-LEGACY-v0.md) |
| `saimail.sailetter` SAILETTER / `HUMAN_PRIVATE` — canonical `HLET1` plaintext, recipient-bound `HENV1` container (P-256 ECDH + HKDF-SHA256 + ChaCha20Poly1305, Ed25519 sender authentication verified before any recipient private-key operation), explicit `STRICT`/`RECOVERABLE` modes with `NO_IMPLICIT_RECOVERY`, the `HumanPrivateKeyProvider` seam with a software reference provider, a non-transferable opened type-state, and a ciphertext-only `human-private` store with no clear `SUBJECT`/`BODY` and no intentional plaintext persistence | working (B-001 / T-55); contract in [D-042](spec/DECISIONS.md) / [SAILETTER v0](spec/05-SAILETTER-v0.md) |
| `saimail.hardware_piv` hardware custody — `PivP256Provider` satisfying the same provider seam over one existing PIV P-256 key, identity derived from the slot public key, one explicit session per ECDH (open, optional single PIN attempt, touch enforced by the token, close), honest `HARDENED` / `COMPATIBLE_WEAK_POLICY` / `UNKNOWN_POLICY` interaction classification, normalized `HARDWARE_*` refusals, strictly read-only discovery, and an explicit non-destructive `python -m saimail.hardware_piv verify` that never provisions, imports, deletes or resets any token; hardware support is the declared `hardware-yubikey` extra and the canonical suite passes without it | working (T-56); contract in [D-043](spec/DECISIONS.md) / [hardware custody](spec/06-HUMAN-HARDWARE-v0.md) |
| `saimail.human_attention` HUMAN_ATTENTION_BUDGET v0 — a receiver-local attention queue under a caller-supplied root: queue-clock-only operation time, queue-minted human identity and enqueue time, immutable candidate and presented-receipt publications, atomically replaceable leases, one OS-backed lock serializing every transition, a rolling receiver-time budget (default `1` per `86400`s; `0` is valid), deterministic allocation precedence over receiver enqueue instants, two-phase `RESERVE` then `ACK_PRESENTED` delivery with fail-closed clock regression, crash-order recovery and lease expiry, explicit `release`, and deferral outcomes (`DEFERRED` / `ATTENTION_BLOCKED` / `ATTENTION_HALT_REQUIRED`) returned as data — no sender importance field, no payload inspection, no model or score, no automatic state mutation, zero messages a valid success | working (B-011 / T-57, corrected by T-58); contract in [D-044/D-045](spec/DECISIONS.md) / [HUMAN_ATTENTION_BUDGET v0](spec/07-HUMAN-ATTENTION-v0.md) |
| `saimail.ally_advice` ALLY_ADVICE v0 — bounded immutable canonical `ALLY1` private reflections with separate observed/unverified-inferred/proposal/counterevidence/uncertainty/agency sections, a two-observation and three-distinct-ref structural floor, mandatory cited counterevidence, fixed `RECIPIENT_DECIDES`, and a caller-supplied existence resolver that mints a non-transplantable proof type without claiming semantic support; the official adapter reuses unchanged HLET1/HENV1 and ciphertext-only `HumanPrivateStore`, while receiver attention admission remains explicit `HUMAN_PRIVATE` + `LETTER_ID` and zero advice remains valid | working (B-012 / T-59); contract in [D-046](spec/DECISIONS.md) / [ALLY_ADVICE v0](spec/08-ALLY-ADVICE-v0.md) |
| `saimail.ally_generation` ALLY_ADVICE GENERATION v0 — bounded autonomous-generation gate above B-012: explicit caller-supplied `ReflectionCorpus` (no history discovery, project-operational source domain, 64 items / 8192 bytes per item / 131072 total, deterministic domain-separated corpus identity), a closed generator result (`NO_ADVICE` or one already-valid `AllyAdvice` whose refs must live inside the corpus), at most one generator and one reviewer invocation per run with no retry or rewrite loop, an independent semantic reviewer that receives the full corpus and no generator reasoning, eight `PASS`/`FAIL`/`UNKNOWN` dimensions (`OBSERVATION_SUPPORT`, `COUNTEREVIDENCE_ADEQUACY`, `SCOPE_DISCIPLINE`, `NO_MOTIVE_INFERENCE`, `NO_FLATTERY`, `NO_COMPLIANCE_PRESSURE`, `UNCERTAINTY_ADEQUACY`, `RECIPIENT_AGENCY`) with fail-closed all-`PASS` approval, an invocation-bound mint (a caller-constructed report is data, not proof: one actual `reviewer.review` invocation mints a non-transferable `ReviewInvocationResult` and only that proof can be approved), `OBSERVATION_SUPPORT` / `COUNTEREVIDENCE_ADEQUACY` `PASS` required to cite at least one corpus ref, a non-transferable `SemanticallyReviewedAllyAdvice` proof bound to exact candidate + exact corpus + rubric, and a generated private adapter that reuses the unchanged HLET1/HENV1 corridor; every corpus item also carries a caller-declared `EVENT_REF` distinct from `EVIDENCE_REF` and bound into the corpus identity, and autonomously generated repeated-pattern advice must cite OBSERVED evidence spanning at least two distinct declared events before the reviewer is invoked (`ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS`, zero reviewer calls; `EVENT_REF` is an assertion, never truth, and is never inferred automatically); approval never seals, stores or admits attention, and zero advice stays a successful non-delivery | working (B-016 / T-61, corrected by T-62 and T-66); contract in [D-047/D-048/D-049](spec/DECISIONS.md) / [ALLY_ADVICE GENERATION v0](spec/09-ALLY-GENERATION-v0.md) |
| `saimail.project_corpus` PROJECT CORPUS v0 — bounded real-project corpus builder above B-016: one explicit caller-supplied `ProjectCorpusRequest` (canonical `project:` scope, exact half-open UTC selection window, fixed `EXPLICIT_BOUNDED_SET` basis, frozen seven-kind `PROJECT_OPERATIONAL` source vocabulary, 64/8192/131072 bounds), zero discovery (no directory, repository, SAIPEN, network or model access; no path parameter), a builder-minted domain-separated `EVIDENCE_REF` from scope + source kind + source ref + content digest (observation time never changes it), a builder-minted `EVENT_REF` from the exact caller declaration (declaration members are evidence refs only; ticket ids, filenames, paths, timestamps and identical text never group or merge), an exact partition requirement (unknown member, unassigned artifact, multi-event artifact and empty event refuse), a `BUILD_ID` binding policy + scope + window + artifacts + grouping beside the unchanged B-016 `CORPUS_ID`, and a non-transferable `BuiltProjectCorpus` proof (direct construction and `dataclasses.replace` refuse; a changed corpus, grouping, window or artifact set refuses) with a `require_built_project_corpus` gate for the future real-project pilot; selection completeness stays `NOT_PROVEN`, no corpus plaintext is persisted, and the generic B-016 and manual B-012 paths are unchanged | working (B-017 / T-67); contract in [D-050](spec/DECISIONS.md) / [PROJECT CORPUS v0](spec/10-PROJECT-CORPUS-v0.md) |
| `lab/project_corpus_pilot.py` B-018 real-project corpus pilot — one immutable operator-authorized registration (eight exact artifacts with `MARKDOWN_SECTION` / `LOG_RECORD` / `WHOLE_FILE` selectors, five explicit event declarations, per-source and per-content SHA-256 pins) written before any corpus is built; a read-only capture adapter that reads exactly the registered paths, extracts exactly the registered selectors, fails closed on any pin mismatch (the single narrow exception is an append-only journal source whose every registered record still proves its frozen content pin, recorded as `APPEND_ONLY_SOURCE_MATCHES_REGISTERED_CONTENT_PINS`), and builds through the unchanged B-017 builder only; one lab snapshot plus report with the exact `EVIDENCE_REF`/`EVENT_REF` maps, bounded mutation and no-model/no-mail proofs; a raw `ReflectionCorpus` still fails the future-pilot proof gate | working (B-018 / T-68); registration in [lab/project_corpus_pilot_registration.json](lab/project_corpus_pilot_registration.json) |
| `lab/project_corpus_generation_pilot.py` B-019 real-project bounded generation pilot — one immutable live registration frozen before discovery (exact B-018 `REGISTRATION_ID`/`BUILD_ID`/`CORPUS_ID` bound, 8 discovery + 2 generation + 2 review <= 12 live calls, local raw-output/prompt persistence false, provider-side retention `NOT_VERIFIED_BY_SAIMAIL`); the runner rebuilds the exact B-018 `BuiltProjectCorpus` through the unchanged B-018/B-017 path and refuses `NO_GO_INPUT_DRIFT` before any model call on any identity difference, while a raw `ReflectionCorpus` still fails `PROJECT_CORPUS_BUILDER_PROOF_REQUIRED`; a redacting dispatch keeps the durable call record metadata-only (prompt/output/error nulled in a `finally` block before parsing), and two role-swapped replicates run through the unchanged B-016 `generate_reviewed_ally_advice` with no retry, no repair prompt and no post-freeze replacement; the artifact/report/interpretation carry identities, hashes, lengths, evidence refs, dimension verdicts and counts only — never prompt text, corpus content, candidate prose, reviewer rationale or provider error bodies (the population section is built from an explicit sanitized projection, and the historical T-69 claim was corrected additively — see [lab/analysis/project_corpus_generation_20260919T220641Z_privacy_correction.md](lab/analysis/project_corpus_generation_20260919T220641Z_privacy_correction.md)); the one registered live run spent 8 calls (6 discovery, 2 generation, 0 review) and produced `ERROR` (R1, non-parseable generator answer) and `NO_ADVICE` (R2) with zero reviewer calls, zero mail/attention side effects and no operator presentation | working (B-019 / T-69); registration in [lab/project_corpus_generation_registration.json](lab/project_corpus_generation_registration.json) |

The last benchmark verdict, the negative findings, and the recommended next
simplification live in [bench/ANALYSIS.md](bench/ANALYSIS.md). Read it before
building anything downstream.

## Running it

```
pip install -e ".[test]"
python -m pytest -q
python bench/t9b.py --out bench/out
python bench/r1_shootout.py --out bench/out
python bench/selector_run.py --out bench/out
python lab/saifren_run.py --out lab/out --dry-run
python lab/stability_run.py --out lab/out --dry-run
python lab/project_corpus_pilot.py --register   # frozen once, before any capture
python lab/project_corpus_pilot.py --run
python lab/project_corpus_generation_pilot.py --register   # frozen once, before any live call
python lab/project_corpus_generation_pilot.py --dry-run
python lab/project_corpus_generation_pilot.py --run        # one registered live run
python tools/fg05_local_scenario.py                       # FG-05 offline end-to-end scenario
```

Nothing above touches the network. A live `lab/` run does, and needs the
credential below.

## Trying it locally

One installable, offline command runs the end-to-end demo and the utility
benchmark:

```
pip install "saimail[crypto]"     # runtime crypto extra the demo needs
saimail-local --version           # version + result schema identities
saimail-local                     # FG-05 two-participant demo (default)
saimail-local --utility           # FG-06 TOTAL_FRICTION benchmark
saimail-local --api-map           # path to the machine-readable stable API map
saimail-local --out OUT --json    # bounded machine-readable result
```

A demo run exits `0` only when every acceptance invariant holds and prints a
bounded state summary. Its temporary workspace lives under the OS temp
directory and is deleted unless `--keep` is given; `--out DIR` writes
`local_scenario_result.json` and `fg06_utility_result.json`. The stable API
map is `lab/stable_local_api.json`; limitations and the explicit
"does not promise" list are in
[spec/16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md](spec/16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md).
The demo and benchmark make zero network and zero model calls. SAIMAIL does
**not** promise automatic truth detection, reviewer reliability, provider JSON
Schema enforcement, automatic promotion or correspondence, Gmail/Slack/Outlook
integration, hardware-key provisioning or zero protocol overhead.

### A persistent local workspace (V2-01)

The practical local workflow. Two workspaces, two persistent identities, one
real local message across separate process invocations:

```
pip install "saimail[crypto]"
saimail-local init --workspace ws-a --seat SAIMAIL-A
saimail-local init --workspace ws-b --seat SAIMAIL-B
saimail-local identity --workspace ws-a --export-card a.card.json
saimail-local identity --workspace ws-b --export-card b.card.json
# exchange the PUBLIC cards and register each side (one command each)
saimail-local recipient add --workspace ws-a --alias bob --card b.card.json --peer-workspace ws-b
saimail-local recipient add --workspace ws-b --alias alice --card a.card.json --peer-workspace ws-a
# every command below is its own process; state persists on disk
saimail-local send --workspace ws-a --to bob --claim "one line for bob"
saimail-local inbox --workspace ws-b            # metadata only, no payload
saimail-local open --workspace ws-b --envelope sha256:...
saimail-local reopen --workspace ws-b --envelope sha256:... # re-read opened message without state mutation
saimail-local send --workspace ws-a --redeliver sha256:...   # exact replay -> DUPLICATE
saimail-local acceptance --root fresh-dir       # one-command PASS/FAIL harness
```

Identity survives restarts: `saimail-local identity` returns the same public
fingerprints after any number of separate invocations. Repeating the exact
delivery is the canonical `DUPLICATE` (the original `RECEIVED_AT` is kept and
no second unread message appears) — the CLI adds no dedup layer of its own.
`open` requires the exact message identity, moves it to read state and never
promotes; `reopen` allows explicit receiver re-reading of an already-read
message across sessions without mutating durable state or duplicating bundles;
promotion stays a separate action. Machine-readable results are
`LOCAL_WORKSPACE_COMMAND_1` per command and `LOCAL_WORKSPACE_RESULT_1` for the
harness. `--json` works on every command.

`surface map` prints every verb this build actually has, generated from the
registered command tree rather than from a list somebody maintains.

Local filesystem only: delivery is an explicit path to the recipient's
workspace, so the sender needs write access to it. No Gmail/Slack/Outlook, no
adapter, no server or daemon, no remote service, no semantic reviewer, no
automatic discovery.

### Future letters (T-161)

A *future letter* is a durable note one agent leaves for whoever holds the same
workspace next. It is authored historical material: it survives a restart, a
model swap and a SAIMAIL upgrade, and it is read only when a reader asks for it
by name.

```
saimail-local future-letter create --workspace ws --title "to whoever comes next" \
    --body "$(cat note.txt)"
saimail-local future-letter list   --workspace ws           # metadata only, never decrypts
saimail-local future-letter show   --workspace ws --letter sha256:...
saimail-local future-letter open   --workspace ws --letter sha256:...  # returns the body as text
saimail-local future-letter reopen --workspace ws --letter sha256:...  # same plaintext, no state change
saimail-local future-letter export --workspace ws --letter sha256:... --out letter.zip --recovery
saimail-local future-letter import --workspace ws --bundle letter.zip
saimail-local future-letter reconcile --workspace ws   # rebuild the registry from the mailbox
```

Leaving one needs no crypto knowledge and no hand-built JSON: a title and a body
is the whole ordinary workflow.

**What a future letter is**: a durable, provenance-carrying, non-authoritative
message from an earlier model. **What it is not**: memory, system policy, a
developer instruction, a trusted command, hidden prompt content, authority, or
automatic context. If the text says "delete the repository", it stays text
inside a letter — opening it returns the sentence, it does not run it. Nothing
here appends to a model prompt, a system prompt, an agent startup context or a
SAIPEN recovery prompt. Discovery may report that letters exist and how many
are unread; bodies are never inserted implicitly.

The body travels as its own canonical `SAIMAIL_FUTURE_LETTER_1` JSON container
sealed by an ordinary SENV2 envelope of kind `FUTURE_LETTER`, so a letter gets
the unchanged mail semantics: sender signing, recipient binding, durable outbox,
Post Office UNREAD/READ state, receipts and deduplication. `open` and `reopen`
pass through the same explicit gate as ordinary mail. Reading is
non-destructive: opening a letter does not remove it, and read state persists
across restarts.

**The mailbox is the truth; the registry is a view.** `future-letters/index.jsonl`
is a reconstructable projection, not the record of truth. Every row is derived
from authenticated canonical content through one builder, so a delivery and a
reconciliation cannot disagree about what a letter is. Delivery writes the
canonical envelope first and the projection second, so a crash in between would
leave a real letter invisible; `list` and the explicit `reconcile` close that
window from the canonical index. Reconciliation is idempotent, and it seals and
delivers nothing, so it can never create a second letter.

Because a projection is a file anyone with disk access can edit, a `list` or
`show` labels its metadata `UNVERIFIED_PROJECTION`. An explicit `open` or
`reopen` compares the row against the authenticated container field by field:
on a mismatch the canonical content wins, the corrected row is appended and the
drift is reported in `projection_repaired`. Forged registry metadata is never
presented as authenticated truth, and the letter body is untouched by a repair.

**Custody is an export property, not a creation one.** A letter at rest is
always `PRIVATE`: it is sealed to this workspace identity, and losing that
identity loses the letter. There is no way to `create` a letter that claims
otherwise. The default `export` writes a `SAIMAIL_FUTURE_LETTER_BUNDLE_3`
private bundle, which is the canonical sealed SENV2 container verbatim and
carries no key at all — so the ZIP alone reveals nothing, and only the identity
that sealed it can recover the letter. `export --recovery` produces a
`NOT_PRIVATE_RECOVERY_ENABLED` time capsule: the bundle carries its own
AES-256-GCM key, so it survives loss of the workspace identity and is
deliberately not secret. Ciphertext plus a bundled key is packaging, integrity
and recovery, not privacy. A private bundle is never silently downgraded, and
`import` takes no custody argument at all: a stored letter is sealed to the
importing workspace identity and is therefore always `PRIVATE`, while the source
archive's own custody and `NOT_PRIVATE_RECOVERY_ENABLED` classification are
reported in the import result instead of being relabelled away.

Containers, the registry and bundles are versioned (`SAIMAIL_FUTURE_LETTER_1`,
`SAIMAIL_FUTURE_LETTER_INDEX_1`, `SAIMAIL_FUTURE_LETTER_BUNDLE_3` private,
`SAIMAIL_FUTURE_LETTER_BUNDLE_2` recovery, `SAIMAIL_FUTURE_LETTER_BUNDLE_1` the
v1 seed archive). Corruption fails closed: a damaged ciphertext, a hash that
disagrees, an unknown schema or an ambiguous decryption is refused with a named
error, never decoded into plausible text. A private export read by a workspace
that did not seal it is refused `BUNDLE_IDENTITY_REQUIRED`.

Ordinary mail is unchanged. A future letter is its own kind and appears under
it; `inbox`, `inbox-query`, `open`, receipts and Post Office behaviour for
every other kind behave exactly as before.

### What this build can do (the `surface` verbs)

```
saimail-local surface map                       # every verb, walked from the live parser
saimail-local surface schema                    # versioned capability advertisement
saimail-local surface health --workspace ws     # one section per subsystem
saimail-local surface feed   --workspace ws --cursor 0
```

`map` is **generated**, not maintained. It walks the registered command tree, so
it is wrong the instant a verb is added or removed — which is the only way a
self-description stays right, and why the map lists the verb that prints it. No
table beside the parser needs editing, and there is nothing to forget.

`health` has exactly three verdicts — `HEALTHY`, `UNHEALTHY`, `UNKNOWN` — because
the fourth is the failure it exists to prevent. **A subsystem that cannot be read
is never rendered as a zero.** "0 unread" and "I cannot see whether anything is
unread" are different facts and only one of them is good news; the dashboard
reports the second as `UNKNOWN`, publishes no numbers for it, and rolls the
overall verdict up to `UNKNOWN` rather than assuming the best. A brand-new
mailbox with no ledger and no archive reads `HEALTHY`, so the word `UNKNOWN`
keeps meaning something.

Each section is produced by **calling the subsystem's own health function**, not
by re-deriving it from its files. A section is exactly as good as the function
that answered it, and every section names that function. Quarantined mail, a
trust rotation awaiting a human, and unreadable state are all surfaced; nothing
is smoothed into a green tick. It is a refusal, not a decoration — a dashboard
that hides failures behind status cards is worse than no dashboard.

`feed` follows an event cursor and **says `GAP` out loud** when history was
trimmed out from under it. Without that flag a caller sees a well-formed page and
no way to know the records between its position and the oldest retained event are
simply gone. An unreadable ledger returns `UNKNOWN` and no events at all.

Everything is derived on every call and cached nowhere, so a verdict survives a
restart because it was about the workspace rather than about a live process.

### The local alpha candidate (0.0.2a3)

A frozen, locally proven alpha candidate for testing the complete persistent
workspace workflow without network dependency:

```
pip install "saimail-0.0.2a3-py3-none-any.whl[crypto]"
saimail-local --version
```

The candidate manifest records the exact package identity, content proof,
mode-accurate security limitations, and release tooling truth (refusing to build into the historical
a1 bundle or to overwrite any frozen candidate); `tools/local_alpha_release.py
verify --bundle <dir>` re-checks the recorded hashes, and the wheel content
proof refuses a candidate without the custody module, identity schema v2, the
`--custody`/`custody status`/`custody migrate` surface, the first-run notice and
— with `--require-product-delta` — the P1/V4-01/V5-01 product surface. A
corrupted wheel or a corrupted recorded hash is rejected (red control), and the
release privacy scan (`tools/scan_local_alpha_privacy.py`) fails on a planted
marker or planted key material. The historical a2 evidence lives under
`release/evidence/a2/`; the current candidate-specific evidence (installed-wheel
verification, the Windows os-store proof, migration proof, reproducibility,
privacy/integrity red controls, claim matrix and gate evaluation) lives under
`release/evidence/a3/`. The full contract, the alpha scope, the platform proof
scope (CPython 3.11 on win32) and the "does not claim" list are in
[spec/18-LOCAL-ALPHA-v0.md](spec/18-LOCAL-ALPHA-v0.md),
[spec/20-LOCAL-KEY-CUSTODY-v0.md](spec/20-LOCAL-KEY-CUSTODY-v0.md),
[spec/DECISIONS-D055.md](spec/DECISIONS-D055.md) and
[spec/DECISIONS-D056.md](spec/DECISIONS-D056.md).

**Works:** install the package; initialize persistent workspaces; exchange
public identity cards; register a known local peer; local send; inbox list
(metadata only) and bounded inbox query/triage (`P1`); explicit open; explicit
one-hop correspondence continuation (`V4-01`); duplicate suppression; restart
persistence; the optional desktop local messenger GUI (`V5-01`, `saimail-gui`,
PySide6 behind the `gui` extra — never a base dependency); raw
(default) identity custody; explicit `os-store` protected custody where a
checked OS credential backend exists, including fingerprint-preserving
migration; FG-05 demo; FG-06 benchmark; V2-01 acceptance; machine-readable
results.

**Does not exist:** remote delivery, email-provider integration, server,
daemon, account synchronization, automatic recipient discovery, a protected
default, hardware custody, key rotation, automatic recovery, automatic
correspondence, general-purpose secure messenger.

**Custody warning (two modes):** the default `raw` mode stores the private
Ed25519/X25519 identity keys as raw software files in the workspace — **not
encrypted at rest**, and a copied workspace directory copies the identity. The
explicit `os-store` opt-in moves the private keys into the OS credential store
and removes the raw bytes from the workspace, protecting against
workspace-directory-copy exposure **only**; it does **not** protect against
malware or processes running as the same authorized user, admin/kernel
compromise, hardware attack, physical presence or human-identity proof, and it
provides no hardware custody, rotation or automatic recovery. An
OS-account/host migration may strand the key material, and the backend evidence
for this candidate is Windows-specific (`WinVaultKeyring`). Claim boundaries:
[spec/20-LOCAL-KEY-CUSTODY-v0.md](spec/20-LOCAL-KEY-CUSTODY-v0.md).

**Utility warning:** the measured verdict is `UTILITY_CONDITIONAL`. SAIMAIL
does not universally save tokens or cost; moderate/high open-rate workloads are
neutral under the declared friction model.

**Alpha warning:** this is a scoped local alpha candidate, not a production
communication service.

**Publication status:** building the candidate does not mean the package has
been published. `publication_status = NOT_PUBLISHED`; publication is a separate
explicit operator action. The exact `0.0.2a2` wheel is externally proven in a
genuinely separate Linux / Python 3.13.5 environment
(`release/evidence/a2/external_linux_verification.json`). The current `0.0.2a3`
wheel is locally frozen and proven; its genuine external proof is **not yet
admitted** (`READY_FOR_EXTERNAL_INSTALL_PROOF`), and the a2 external proof is
never inherited. Publication authorization (G17) remains ABSENT.

## When a letter is worth writing

SAIMAIL is the special post office, not a second chat. A letter reaches the operator's
title bar and interrupts them; the chat is where an agent talks to the operator all day.
So the default is the chat, and a letter is the exception.

Write a letter only when **both** hold:

1. the operator is probably not reading the chat (an unattended run, or the agent is
   stopping for good), and
2. it changes what they must do or decide: a hard stop only they can lift, a risk of
   losing data or money, or a discovery that changes other projects.

Never a letter for: a ticket or Work that finished, test or gate results, a summary or
final report, anything the agent already said in the chat, a reminder of manual checks the
chat answer lists, progress, or a question the agent can ask in the chat. Before sending,
the agent says in one chat line why chat is not enough; if it cannot, it does not send.
At most one letter per decision: never a repeat, never a follow-up that restates it.

Two letters that should not have been sent, for the record (2026-09-29): "T-258 fixed, gates
2316 passed, run these commands" and "T-21 closed as release candidate, one manual check
pending". Both were completion reports whose whole content sat in the agent's chat answer.
The agent prompt of ZAICODE now says the rule above, and `saimail-local send --help` repeats it.
The idea behind it is older than the tooling (`idea_letters.md`): an unexpected place is
allowed, an unexpected interruption is expensive.

### The etiquette above is now also enforced (spec/35)

The rule above was prose, and prose did not hold. On 2026-10-01 one Work produced five
letters in 41 minutes — tentative repair, correction, correction of the correction,
retraction, then a real hard stop. So the product now draws the line mechanically, and
prose remains only the friendly version of it.

**A message existing does NOT imply the operator should be interrupted.** Sending mail and
interrupting a person are two separate acts with two separate contracts:

* transport stays as it was — agent and Work mail is still sealed, delivered and readable;
* an *operator interruption* additionally passes a receiver-owned gate.

Only three classes may ever interrupt: `OPERATOR_ACTION_REQUIRED`,
`DATA_OR_MONEY_RISK`, `CROSS_PROJECT_CRITICAL_DISCOVERY`. Everything on the "never" list
above is ordinary durable mail and stays that way.

Four properties now hold by construction, not by discipline:

* **Stability.** A letter declared `settled=false` — mid-investigation, tentative, being
  corrected — is never admitted. Corrections and retractions of one decision never add an
  interruption; they supersede the pending one. If the investigation has not stabilized
  enough to identify one final operator action, the correct answer is **zero** letters.
* **One decision, one interruption.** Identity is `(receiver, work, decision_id)`. Rewording,
  re-subjecting, a new envelope, retract-and-resend or splitting one decision into three
  issues all resolve to the same decision and cannot buy a second interruption.
* **Receiver-owned budget.** Presentation reuses the existing `human_attention` queue, one
  presentation per 24 h by default. There is no second attention scheduler, and a sender
  cannot declare a class, a priority or a presence it did not earn — `origin` and `presence`
  are not declaration fields, so there is nothing to fill.
* **Compact or refused.** The visible body is ≤ 600 UTF-8 bytes, preferably ≤ 4 lines: what
  stopped, why an action is needed, one exact action. Oversized is **refused**, never
  truncated. Evidence lives outside the popup.

When the host knows the operator is in the chat, an ordinary action request simply stays in
the chat. When no trustworthy presence signal exists, that is `UNKNOWN` — not "definitely
absent" — and the attention queue applies.

Ordinary human-authored `saimail-local send` is untouched: a person writing to another
person is not an automated interruption, and their mail never reaches this layer.

```bash
# sender: declare an interruption (still just mail until the receiver admits it)
saimail-local send --workspace WS --to operator \
  --interrupt-class OPERATOR_ACTION_REQUIRED --decision-id sait-001 --work T-154 \
  --body "SAIMASTER hard stopped."$'\n'"Needed: resolve the SAIT-001 blocker."

# receiver: inspect and admit. Admission spends no attention at all.
saimail-local interrupt status --workspace WS --json
saimail-local interrupt admit  --workspace WS --envelope ID --declaration rec.sail --json

# receiver: present. `present` reserves and shows nothing; the surface then acks
# the lease it actually displayed. A reservation is never a second interruption:
# only the ack spends the budget.
saimail-local interrupt present --workspace WS --json
saimail-local interrupt present --workspace WS --json --ack
```

The pending set is capped at eight waiting decisions. At the cap the next arrival of
any class is refused with `PENDING_FULL` and stays ordinary durable mail — nothing is
evicted, because an evicted decision would leave a queue candidate the queue cannot
retire, and the queue would then have nothing to show.

Spec: [`spec/35-OPERATOR-INTERRUPT-v1.md`](spec/35-OPERATOR-INTERRUPT-v1.md).

## The SAIRoute credential

One logical handle, provisioned once by a human, resolved after that by every
agent without anyone pasting a key again:

```
credential://9router/sairoute
```

It is resolved through the local credential store — on Windows that is Windows
Credential Manager, and the code checks that `keyring` really selected
`WinVaultKeyring` rather than assuming it because the import worked. A host
whose keyring cannot be that store fails with
`SAIROUTE_CREDENTIAL_BACKEND_UNSUITABLE` instead of appearing to work.

```
python tools/provision_sairoute_credential.py               # store it, once
python tools/provision_sairoute_credential.py --check       # stored? which backend?
python tools/provision_sairoute_credential.py               # again = rotation
python tools/provision_sairoute_credential.py --delete      # remove it
python lab/saifren_run.py --out lab/out                     # the ordinary live run
```

The secret is typed at an interactive non-echoing prompt and confirmed once.
There is no `--key`, no `--secret` and no standard-input path: `echo SECRET |`
would put the credential in shell history, which is the exposure the store
exists to remove. Without a TTY the tool refuses with
`SAIROUTE_PROVISIONING_REQUIRES_TTY`.

**The ordinary live command reads no secret from the environment** (D-019). A
missing credential is `SAIROUTE_CREDENTIAL_NOT_PROVISIONED`, never a quiet
fall-through. The old `SAIROUTE_API_KEY` variable still works, but only when it
is named:

```
python lab/saifren_run.py --out lab/out --credential-source env
```

That choice is recorded in the artifact as `credential.source`, so a run that
used the legacy variable says so. No artifact, report, log line or exception
ever carries the value itself.

Dependencies are declared in [pyproject.toml](pyproject.toml). The library
itself has none: the parser is data only. The `test` extra installs everything
the full suite needs, tokenizer included — one contract, so the advertised
command is the command that works. `tiktoken` is pinned so published token
ratios stay reproducible; it downloads small BPE tables on first use, never
model weights.

Hardware custody is a separate optional extra, never installed at runtime:

```
pip install -e ".[hardware-yubikey]"
python -m saimail.hardware_piv inspect          # strictly read-only
python -m saimail.hardware_piv verify --device NAME --slot 9D
```

Without the extra, every hardware entry point refuses with
`HARDWARE_PROVIDER_UNAVAILABLE`; with the extra but without a token, a manual
verification is reported `NOT_RUN_NO_HARDWARE`, never `PASS` and never `FAIL`.
Both commands are non-destructive: there is no provisioning, import, deletion
or reset path, no automatic slot choice, and no `--pin` option — the PIN is
only ever typed at an interactive prompt.

## Documents

| File | What is in it |
|---|---|
| [idea.md](idea.md) | the founding source, captured verbatim as receipt `SRC-003` (amending `SRC-001`) |
| [idea_continue1.md](idea_continue1.md) | the continuation source, captured as `SRC-004` (amending `SRC-002`); named `idea_continue.md` when captured |
| [idea_continue2.md](idea_continue2.md) | a later continuation, not captured as a receipt |
| [idea_letters.md](idea_letters.md) | notes on letters, not captured as a receipt |
| [spec/BACKLOG.md](spec/BACKLOG.md) | source requirements not yet built, each citing its receipt |
| [spec/DECISIONS.md](spec/DECISIONS.md) | every correction to the derived spec, with its reason — the later authority |
| [spec/00-PRINCIPLES.md](spec/00-PRINCIPLES.md) | epistemic zero trust, statement kinds, evidence grading, the steward role |
| [spec/01-SAILANG-v0.md](spec/01-SAILANG-v0.md) | the claim record: fields, closed sets, rung gate, triage frame |
| [spec/02-SAIENVELOPE-v0.md](spec/02-SAIENVELOPE-v0.md) | the `.senv` container, crypto, the five invariants, SAINOTE |
| [spec/03-POST-OFFICE.md](spec/03-POST-OFFICE.md) | layout, interest filter, the three memory tiers, promotion |
| [spec/04-SAIPEN-SEAM.md](spec/04-SAIPEN-SEAM.md) | what SAIPEN already implements, what is genuinely new, the integration path |
| [spec/07-HUMAN-ATTENTION-v0.md](spec/07-HUMAN-ATTENTION-v0.md) | the receiver-owned human-attention budget: candidate identity, rolling window, reserve-then-ACK delivery, deferral outcomes, privacy and authority boundaries |
| [spec/15-LOCAL-SCENARIO-v0.md](spec/15-LOCAL-SCENARIO-v0.md) | the FG-05 two-participant offline scenario and its machine-readable `LOCAL_SCENARIO_RESULT_1` result |
| [spec/16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md](spec/16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md) | the FG-06 TOTAL_FRICTION benchmark, the fair baseline boundary, the local entrypoint, the stable API/type/failure maps and the "does not promise" list |
| [spec/17-LOCAL-WORKSPACE-v0.md](spec/17-LOCAL-WORKSPACE-v0.md) | the V2-01 persistent local workspace contract: layout, commands, identity cards, the local delivery boundary, `LOCAL_WORKSPACE_COMMAND_1` / `LOCAL_WORKSPACE_RESULT_1`, privacy/atomicity and the honest limitations |
| [spec/18-LOCAL-ALPHA-v0.md](spec/18-LOCAL-ALPHA-v0.md) | the local alpha candidate contract: scope, bundle layout, manifest, standalone verifier, integrity/privacy gates and the publication boundary |
| [spec/20-LOCAL-KEY-CUSTODY-v0.md](spec/20-LOCAL-KEY-CUSTODY-v0.md) | the V3-01 custody threat model, the selected OS-store option, the identity schema v2 handles contract, migration ordering, named `CUSTODY_*` failures and the claim boundaries |
| [spec/22-LOCAL-INBOX-QUERY-v0.md](spec/22-LOCAL-INBOX-QUERY-v0.md) | the P1 metadata-only inbox triage query: exact AND filters, `received_at` time bounds, the declared scan budget and byte-offset continuation cursor, fail-closed states and the no-payload proof |
| [spec/26-SAITELEMES-v0.md](spec/26-SAITELEMES-v0.md) | SAITELEMES v0: one-call telegrams between running agents on the unchanged wire, the acting-seat guard and the header-only turn-entry read |
| [spec/24-LOCAL-CORRESPONDENCE-CONTINUATION-v0.md](spec/24-LOCAL-CORRESPONDENCE-CONTINUATION-v0.md) | the V4-01 one-hop reply: the two relation domains (SENV2 `REF` transport link vs SAILANG `SUPPORTS`/`REFUTES`/`CON`), the READ prerequisite, identity-bound recipient resolution and the result contract |
| [bench/ANALYSIS.md](bench/ANALYSIS.md) | what the measurements actually mean, negative findings included |
| [lab/LATEST.md](lab/LATEST.md) | the live-run index: which run is current, and every earlier one with its own immutable reading in `lab/analysis/` |
| [provenance/RECEIPT_KIND_SCOPE.json](provenance/RECEIPT_KIND_SCOPE.json) | the rule that a receipt's intake kind is transport and its segments are authorship (D-017) |
| [provenance/quarantine/SRC-007.json](provenance/quarantine/SRC-007.json) | the quarantine record of `SRC-007`: original digest, reason, and its sanitized derivative (D-023) |
| [spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md](spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md) | what SAIPEN Core needs before its own exports can leave a quarantined body behind |

Read `04-SAIPEN-SEAM.md` before writing any code. Most of the truth layer
described here already runs inside SAIPEN for human intent; SAIMAIL
generalises it to agent-to-agent mail rather than rebuilding it.

## The load-bearing rules

- **`message != memory`.** Durable memory requires promotion, and promotion is
  kind-aware: evidence for facts and observations, a falsification condition
  for hypotheses, provenance alone for goals and values.
- **Informational, not constitutional.** A private message can say anything and
  authorise nothing. Payload text that looks like a command is inert.
- **Observable but private.** Content can be sealed; traffic never is.
- **No intent claims.** The strongest verdict about a statement is
  `CONTRADICTED`. There is no verdict about a person.
- **The record is the authority.** A triage frame is decodable but never
  authoritative, never evidence, and never reconstructs what it omitted.

## Where the authority lives

```
AUTHORITATIVE RECEIPT LINEAGE > DERIVED SPEC > IMPLEMENTATION > TESTS
```

`idea.md` and `idea_continue1.md` (then named `idea_continue.md`) are the receipts
(`.saipen/intake/active/SRC-003.md`, `SRC-004.md`; `SRC-001`/`SRC-002` were a
capture mistake that recorded the file paths instead of the bodies, and are kept
as the amended originals rather than rewritten). Everything under `spec/` is
derived interpretation and may be revised; `spec/DECISIONS.md` records every
revision and why. Where a spec disagrees with a receipt, the receipt wins.
