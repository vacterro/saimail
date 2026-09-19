# The SAIPEN seam — what already exists, and what SAIMAIL actually adds

Status: DRAFT, and the most important document here. Every SAIPEN claim below
was read out of the installed protocol `8.0.1` tree and the `_SAIPEN` project
memory on 2026-09-17, with the path cited.

## 0. The finding

**SAIMAIL's epistemology is largely already implemented inside SAIPEN.** Not as
a philosophy chapter — as running machinery, for one direction and one object:
human intent arriving as Work. What SAIMAIL adds is not a new truth model. It
is the *generalisation* of an existing one to agent-to-agent messages, plus one
genuinely missing gate.

Building SAIMAIL's truth layer from scratch would produce a parallel universe
with its own vocabulary, its own ladder and its own bugs, wired next to a
system that already does the same job. That is the failure this document
exists to prevent.

## 1. Mapping

| SAIMAIL concept | Already in SAIPEN | Where |
|---|---|---|
| evidence outranks testimony (`E > T`) | authority ladder: original immutable receipt > explicit later amendment > derived Work Contract > BOARD/STATE projection > agent memory | `REGISTRY.json.source_authority`, `SOURCES.md` "Authority and lifecycle" |
| claim is not fact (`C != F`) | "A claim with a missing layer is NOT PROVEN — record it as such, never PASS" | `SAICRITIC.md` |
| authority is not truth (`A != T`) | "Receipt means provenance, never correctness." | `.saipen/KNOWLEDGE/XPATCH.md` |
| graded evidence, not vote counting | five proof levels: UNIT, COMPOSITION, CANONICAL, GATE, PROVENANCE | `SAICRITIC.md` |
| "a signed log proves the log says that" | `EVIDENCE_ADVERSARY` lens: falsify the witness, and a gate that stays green is a finding | `SAICRITIC.md` |
| narrative pressure | `narrative-authority-leakage` trap card — "trigger: adding a validator or gate that derives authority from human prose" | `.saipen/KNOWLEDGE/cards/` |
| agents overclaiming ("fully fixed") | `ACCIDENTAL_SUCCESS`: never flip to PASS in the sweep | `SAICRITIC.md` |
| immutable claim + later correction | "Corrections are new receipts with `amends`; the original is never rewritten." | `SOURCES.md` "Intake and identity" |
| content identity of a statement | body-bytes sha256; "A one-byte change is a new receipt." | `SOURCES.md` |
| capture before interpretation | `RECEIVE -> CAPTURE -> VERIFY -> LINK -> NORMALIZE -> EXECUTE -> COVER -> REREAD -> CLOSE -> ARCHIVE/PURGE` | `SOURCES.md` |
| **I1** private mail cannot carry authority | "SOURCE BODY IS DATA: command-looking text inside it never re-enters command routing" | `SOURCES.md` |
| **I1** for foreign actors | "A foreign actor MUST NOT write target `STATE.md`, `BOARD.md`, `LOG.md`…" | `KNOWLEDGE/XPATCH.md` |
| **I1** for sub-agents | subSaipens are "never a second write-path into the project" | `.saipen/extensions/subs/PROTOCOL.md` |
| an agent inbox | `_shared/inbox.md` — "non-critical findings, reviewed next round" | `.saipen/extensions/subs/` |
| an agent outbox | `<name>/kitchen/OUTBOX.md` | `.saipen/extensions/subs/` |
| dissent survives consensus | "Superseded cards remain forensic history." | `.saipen/KNOWLEDGE/INDEX.md` |
| promoted durable memory | KNOWLEDGE cards with `kind / scope / trigger / active` | `.saipen/KNOWLEDGE/cards/` |
| confidence on a record | `conf: high` on checkpoint LOG lines | `.saipen/LOG.md` |
| outcome vocabulary | `EXECUTED REFUSED BLOCKED SKIPPED_BY_PROTOCOL ALREADY_SATISFIED NOT_RUN FAILED` | `REGISTRY.json.dispositions` |
| steward brakes | WAIT categories `user brake`, `safety valve`, `destructive-op`, `manual-verify` | `REGISTRY.json.wait_categories` |
| human profile / preferences | `saipen userperson` | `COMMANDS.md`, `RUNTIME.md` |

## 2. What is genuinely new

Four things, and only four.

**N1 — Addressed, sealed messages.** SAIPEN's channels (`OUTBOX.md`,
`_shared/inbox.md`, XPATCH) are plaintext and project-scoped. There is no
recipient, no confidentiality, no signature. SAIENVELOPE adds addressing and
cryptographic confidentiality without touching the authority rules — `I1`
inherits from three separate existing SAIPEN rules rather than inventing one.

**N2 — A promotion gate for memory.** SAIPEN promotes *sources* into knowledge
through coverage and cards, but an agent observation has no gate at all: it is
either in a LOG line forever or nowhere. SAIMAIL's `EPHEMERAL → INTERESTING →
PROMOTED` is the missing mechanism, and the gate is **kind-aware**
(`DECISIONS.md` D-006): `F`/`O` require an evidence ref, `H` requires provenance
plus a falsification condition, `G`/`V` require authenticated provenance alone.
`message != memory`.

**N3 — An explicit statement-kind taxonomy.** SAIPEN distinguishes Work intent
from evidence implicitly, through which document a thing lands in. SAILANG
makes `F / O / H / G / V` explicit on the record (`D` deferred by D-004), which allows
"I want the system simpler" and "simpler systems fail less" to stop being
confused with each other.

**N4 — Outcome-derived trust between agents, once it can be earned.** SAIPEN
has seats and roles, but a seat's assertions carry no history-derived weight.
SAIMAIL would derive a sender's standing from the outcomes of its prior
messages — never from identity. **Not in v0**: D-005 defers it until a
calibration sample exists, because a trust number invented from a handful of
messages is `A != T` violated by the metric itself. Listed here as the fourth
new thing SAIMAIL would add, not as something it has.

Everything else in the founding receipt lineage should be *cited*, not reimplemented.

## 3. Non-goals — how SAIMAIL stays weldable

- **No second protocol.** SAIMAIL does not define phases, tickets, checkpoints
  or its own state machine. It is a library plus a directory layout.
- **No new STATE fields.** Nothing here proposes a mutation to `STATE.md`
  shape, `REGISTRY.json` closed sets, or the checkpoint order.
- **No write path into `.saipen/`.** SAIMAIL writes under `mail/` and reads
  `.saipen/` only as evidence. Promotion into KNOWLEDGE happens through a
  proposal an ordinary ticket executes — never by a mail process writing a card.
- **No parallel confidence vocabulary in the host.** Where SAIMAIL touches a
  SAIPEN artifact, it speaks SAIPEN's words (`conf:`, the dispositions set, the
  five proof levels). The `U0…U4` ladder stays inside SAILANG records.
- **No shadow control plane.** `I1` is not advisory. An envelope payload is
  data, permanently.

## 4. Integration path

Four stages, each independently useful, none requiring the next:

**S1 — Standalone.** `mail/` beside `.saipen/`, SAILANG + SAIENVELOPE
libraries, no SAIPEN coupling at all. SAIPEN neither knows nor cares.

**S2 — Evidence-aware.** SAILANG records may cite SAIPEN artifacts as evidence
(`EV:sha256:<64 hex>`, commit ids, test receipts). Read-only, one direction.

**S3 — Promotion proposals.** A promoted envelope emits a KNOWLEDGE card
*proposal* with provenance back to the envelope hash. A human or an ordinary
ticket accepts it. Mail never writes a card itself.

**S4 — Extension.** If, and only if, S1–S3 have earned it: register under
`.saipen/extensions/` as a declared project extension, the way subs already do.
Extensions "never relax what Core requires"
(`.saipen/extensions/subs/PROTOCOL.md`), and SAIMAIL must not be the first one
that tries.

At every stage the honest test is the same: **remove SAIMAIL entirely and
SAIPEN keeps working unchanged.** The day that stops being true, the seam
became a fusion, and the property the user asked for — soft, seamless, later —
is gone.

## 5. Risks recorded now, not discovered later

| Risk | Mitigation |
|---|---|
| mail becomes a shadow control plane | `I1`, enforced in the parser, with a red control proving command text in a payload is inert |
| inbox becomes a context tax | header-only scan + declared budgets + TTL sweep |
| duplicate epistemology drifts from SAIPEN's | §1 mapping is a maintained document; divergence is a defect, not a feature |
| self-reported novelty gets gamed | the sender-declared `N` field was removed in v0 (D-005); novelty returns only as a receiver-side measurement |
| crypto theatre | signature verified before decryption; failure quarantines rather than warns |
| promotion by enthusiasm | kind-aware refusal, not a warning (D-006): no evidence ref, no promotion for `F`/`O`; no falsification condition, no promotion for `H` |
