# T-143 source-supported feedback provenance

## Scope and finding

T-142 reviewed the broader objective and selected this local semantic gap, not
another byte optimization. `correspondence.metrics` aggregates the acting
workspace's cases table. Its basis is EXPLICIT_RECEIVER_DECISIONS. These are
local receiver decisions about received proposals, not peer assessments of this
seat's outgoing proposals. `report` returns an assessment to the original sender
in a sealed reply; the sender still needs explicit review before adapting work.

`saimail_host._focus` already preserves feedback_basis LATEST_RECEIVER_ASSESSMENT
and feedback_scope LIFETIME_HISTORY. Those fields must not be renamed or silently
reinterpreted. Add a separate explicit origin/provenance field, with locally
reconstructed closed metadata, to distinguish the source of the guidance.
Missing provenance on older peers should remain UNKNOWN. Malformed present
provenance must refuse the view. Do not automatically open peer replies or count
their contents as local explicit decisions.

## Reuse and ownership

Reuse the existing metrics dictionary, shared agent_cycle entry and root host
projection/compact consumer. The CLI already calls project_focus; no second
command or admission path is needed. Existing temporal eligibility, lifetime
counts, receiver feedback, coverage, reading refs and authority remain intact.
Optional host contract capability can advertise the addition. No database
migration, sealed-letter schema change, dependency, GUI or foreign SAIPEN edit
is needed. Current foreign ownership is not this ticket's authority.

Tier 2 graph searches found metrics/report and the focus helpers; complete
depth-one metrics trace returned five callers and nine callees, including
agent_cycle, CLI, GUI and historical experiment/replay artifacts. Graph generation
2026-09-30T10:56:48Z coverage reports metadata_changed without recorded gaps on
the eight selected source/test paths. Current source reads supply material
claims; graph heuristic call edges are not exhaustive caller evidence.

## Build and verification

Before edits, preserve the attributable source and pin a two-seat oracle using
the existing test_correspondence fixture. Its criterion must distinguish local
receiver history from sender-facing sealed feedback before and after explicit
report/review. Keep the same criterion for the restored-before and current
subject. Scripted seats verify protocol semantics; they are not independent
real-use participants.

Add meaningful controls for zero/local history, original/reply decisions,
correction and retries, keyless reads, older cycle/compact peers with UNKNOWN
origin, malformed origin refusal and locally reconstructed metadata. Carry the
origin through full cycle, local focus and compact CLI without changing existing
feedback_basis or feedback_scope. Run targeted pytest on the new provenance
controls and the existing correspondence, age, host-focus and compact-CLI suites;
then the canonical full suite from .saipen/KNOWLEDGE/VERIFICATION.md, lint and
owned whitespace checks. Preserve all failure and before/after artifacts.

Apply T142_REAL_USE_1 to the actual T-143 entry as entry 2 with the unchanged
registration hash and actual Work/actor/context. Keep the canonical host's
legacy-count path separate from explicit focus. An empty observation is EMPTY,
with receiver effort UNKNOWN and independent revision/successor NOT_RUN. Do not
modify the immutable registration, seed real mail or invent another actor.

The broad objective remains active after this ticket. A provenance label can
improve semantic usability; it cannot establish comfort or actual receiver
behavior by itself.
