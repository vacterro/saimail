# SAIPEN Work Desk v0

Status: implemented in the development checkout under T-110 / SRC-099, with
the operator's clarification that SAIMAIL is the target, HUMBOX is the guide,
and entry should require SAIPEN participation.

## Problem

Agents assembled current SAIPEN work and incoming telegrams from separate
commands. Filtering only by the current ticket could hide a useful finding
under another topic; an empty budget-limited page could resemble an empty
inbox. Entry also lacked an explicit project-participation check.

HUMBOX `future1.md` suggests linking communication to projects and tasks;
`iniciative.md` values observable cooperation and continuity. This work desk
composes the existing S2 bridge and P1 query without a new protocol lifecycle.

## Admission

`saimail-local saipen enter --workspace MAILBOX [--project-root PROJECT]
[--seat SEAT] [--json]` requires readable STATE, a valid IDENTITY project
lineage, STATE phase and numeric last_event, and an acting seat matching the
workspace. Duplicate flat fields in either evidence file are refused. Seat
precedence stays `--seat` > `SAIPEN_AGENT` > `STATE.agent`. The CLI loads
`enter` and `brief` workspaces through the secret-free header view (T-117,
D-059): every public marker/identity consistency check of the full load, no
private key, no credential-store read. `init` and `telegram` keep the full
key/marker load because they create or sign.

Success is `ADMITTED`: `admission.basis=LOCAL_SAIPEN_BINDING`,
`persistent=false`, `protocol_compliance=NOT_VERIFIED`. The same check applies
to `saipen init`, `telegram`, and `brief`; creation/sending follows admission.
Idle projects may enter. No membership file or transferable permission is
issued. Bridge users without IDENTITY now need a valid project lineage for
these operations. Diagnostic `status` and historical lineage-free citations
remain available.

This is a local prerequisite, **not cryptographic attestation that an agent
runs or obeys SAIPEN**. The caller chooses the project files to trust; someone
controlling those files can declare a binding. SENV2 sender authentication and
receiver key acceptance remain authoritative. Standalone SAIMAIL APIs and
generic mailbox commands remain available: this is not global access control.

## Brief and continuity

`saimail-local saipen brief --workspace MAILBOX [--project-root PROJECT]
[--seat SEAT] [--scan-budget N] [--cursor OFFSET --context HASH] [--json]`

The bridge admits the workspace, reads one unfiltered UNREAD P1 page, and
re-reads the relevant project binding before returning. No message is opened
or ciphertext read. The CLI still loads workspace keys under ordinary custody
rules; this is not a keyless viewer.

The existing workspace result gains:

- `saipen`: observed seat/source, lineage, phase, task, last_event, and blocker.
  These are file observations, not a full protocol validation.
- `admission`: the entry observation above.
- `items[].work_relation`: `current_topic` for exact equality with a usable
  STATE task token, otherwise `other_topics`. Every unread match stays visible.
  Absent, `none`, or unusable task means no current topic.
- `brief.schema=SAIPEN_WORK_BRIEF_1`, `association=TOPIC_ONLY`. Equal ticket
  ids across projects do not prove membership, relevance, urgency, or truth.
- `brief.counts_scope=PAGE` and counts for both groups. Existing P1 scan fields
  (`rows_examined`, `match_count`, `exhausted`, `cursor`) remain unchanged.
- `brief.complete_from_start`: true only when this call started at offset zero
  and reached the observed end. A final continuation page is still partial.
- `brief.context`: SHA-256 of domain-labelled canonical JSON containing the
  observed binding, evidence paths, mailbox path, and public key ids.
- `brief.continuation`: the next cursor and context, or null at the observed end.

Nonzero cursors require context. A changed project, seat, lineage, phase,
task, event, blocker, mailbox, or key identity refuses before scanning. Drift
during the scan also refuses, returning no mixed-context page. Restart without
the old cursor/context. The hash detects changes; it is not authentication.
P1 concurrency semantics remain unchanged; no atomic inbox snapshot is claimed.

## Refusals and proof

New `SAIPEN_ADMISSION_REQUIRED` covers absent/invalid lineage and missing
phase/event facts. New `SAIPEN_CONTEXT_CHANGED` asks the agent to restart the
brief and does not require human approval. Existing project/state/seat and
P1/workspace refusals remain in force.

`tests/test_saipen_brief.py` covers missing/ambiguous participation, refused
entry/init/send with zero mutation, seat precedence, empty work/inbox,
unrelated topics, budget exhaustion, restart pagination, cross-project/mailbox
continuation, mid-scan drift, CLI text/JSON, ciphertext exclusion, and unchanged
project/mailbox bytes. Existing S2, SAITELEMES, and I1 tests remain oracles.

Stop: one admitted work desk, truthful bounded context, passing product checks.
Checkout-only, ahead of frozen `0.0.2a3`. No publication, automatic send/open,
SAIPEN extension registration, or SAIPEN-state mutation is performed.
