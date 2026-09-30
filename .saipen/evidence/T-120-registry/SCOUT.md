# T-120 SCOUT: V6-06 project-local participant registry (SRC-108 item 4, SRC-107 policy)

Requirement: explicit local mapping project -> participating seats -> mailbox ->
accepted identity -> capabilities; no discovery; receiver-owned trust unchanged;
never guess recipients, ticket numbers, ownership or project identity.

Facts:
- Routing today is `peers.json` (alias -> seat, public keys, kids, workspace root),
  written only by explicit `recipient add`; no notion of project membership.
- Project identity is SAIPEN `IDENTITY.project_lineage` (`lineage-<32 hex>`), read
  by `saipen_bridge.read_lineage` (entrypoint names `.saipen`, library never does).
- SENV2 kinds are a closed set; no new kind may be added.
- Receiver acceptance: the recipient's Post Office quarantines unknown senders.

Design: `saimail/participants.py` + `participants.json` in the acting workspace:
`{lineage: {seat: {alias, sender_kid, recipient_kid, triggers, admitted_at}}}`.
Explicit admit/revoke; resolve(lineage, seat, trigger) refuses unknown participant,
identity drift against the pinned kids, a trigger not admitted, and self-address.
The closed notify trigger set (blocker, finding, dependency, ownership, handoff,
reply) is defined here with its SENV2 kind so V6-08 cannot invent triggers.
CLI under `saipen participant admit|revoke|list|resolve`, lineage from the
enclosing project, gated by the Work Desk admission (acting seat = workspace seat).
