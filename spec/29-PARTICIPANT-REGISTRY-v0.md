# Participant registry v0 — who automation may address

Status: implemented in the development checkout under T-120 (SRC-108 wave item
4, gate V6-06). Decision: D-061. Checkout-only; the frozen `0.0.2a3` wheel does
not contain it.

## 1. Why

`peers.json` answers "how do I reach alias X", not "which agents take part in
this project". An automatic sender therefore had nothing to route by except a
guessed name. The operator policy (SRC-107) forbids exactly that: resolve the
recipient from the admitted project-local participant registry, and never guess
recipients, ownership or project identity. A global discovery registry stays
forbidden.

## 2. Model

The acting workspace keeps `participants.json` (`SAIMAIL_PARTICIPANTS_1`):

```
projects:
  lineage-<32 hex>:                 # SAIPEN IDENTITY.project_lineage
    <seat>:
      alias: <registered peers.json alias for that seat>
      sender_kid / recipient_kid:   # identity pinned at admission
      triggers: [...]               # subset of the closed notify trigger set
      admitted_at: <UTC>
```

Closed notify trigger set and the existing SENV2 kind each travels as (a kind
classifies content; it is never a priority):

| Trigger | Meaning | Kind |
|---|---|---|
| `blocker` | a blocker needs action from another admitted seat | `WARNING` |
| `finding` | a finding materially affects another active Work | `DISCOVERY` |
| `dependency` | another seat owns a dependency, or it became actionable | `DISCOVERY` |
| `ownership` | ownership or dependency state changed | `DISCOVERY` |
| `handoff` | a bounded handoff is requested | `QUESTION` |
| `reply` | information another agent requested from this Work | `DISCOVERY` |

## 3. Rules

- **Explicit admission.** `admit` needs a registered alias whose seat is the
  participant seat. It pins that alias's current identity. An identical
  re-admission is a no-op; a different alias, identity or trigger set is
  `PARTICIPANT_CONFLICT` until revoked.
- **Resolution never falls back.** `resolve(lineage, seat, trigger)` refuses:
  another project or an unadmitted seat (`PARTICIPANT_UNKNOWN`), a trigger outside
  the admission (`PARTICIPANT_TRIGGER_NOT_ADMITTED`), an unknown trigger
  (`BAD_TRIGGER`), the workspace's own seat (`PARTICIPANT_SELF`), and an alias that
  no longer carries the pinned identity (`PARTICIPANT_IDENTITY_CHANGED`).
- **Receiver-owned trust is unchanged.** Admission is the sender's routing
  decision. The recipient still quarantines a sender it never registered; the
  registry grants nothing at the receiver.
- **Project from the binding.** The CLI takes the lineage from the admitted
  SAIPEN binding (the Work Desk `enter` check: project IDENTITY present, acting
  seat equals the workspace seat), never from a free-text argument.
- **No secret.** Registry operations use the header view (D-059).
- **Fail closed.** An unknown shape, lineage, seat or trigger in the file is
  `PARTICIPANTS_CORRUPT`. Writes are atomic under an OS lock.

## 4. Interface

Library `saimail.participants`: `admit_participant`, `revoke_participant`,
`list_participants`, `resolve_participant`, `TRIGGERS`.

```
saimail-local saipen participant admit   --workspace WS --participant SEAT [--alias A] [--trigger T ...]
saimail-local saipen participant revoke  --workspace WS --participant SEAT
saimail-local saipen participant resolve --workspace WS --participant SEAT --trigger T
saimail-local saipen participant list    --workspace WS
            [--seat ACTING] [--project-root P] [--json]
```

## 5. Evidence

`tests/test_participants.py` (12 controls) and red controls in
`.saipen/evidence/T-120-registry/` (mutants without the identity pin, without
project scope, without the trigger check, allowing self-address, or reading the
file leniently each turn controls red).
