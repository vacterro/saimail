# SAIPEN capability document v0 — negotiate, degrade, never break the caller

Status: SAIMAIL half implemented in the development checkout under T-121 (SRC-108
wave item 5, gate V6-07). Decision: D-062. The SAIPEN half (a registered S4
extension calling this document at entry) is SAIPEN-project Work. Checkout-only.

## 1. Why

SAIPEN's turn entry (T-1497) calls `saipen telegrams` and gets counts or a bare
exit code. It cannot tell no mail from a wrong seat, a missing mailbox, a stuck
outbox or an incompatible build; it reads a refusal code from a field SAIMAIL
never writes; and it shows counts for whatever mailbox it is pointed at. The
operator requirement (SRC-108): capability negotiation on entry, and an
incompatibility gives DEGRADED instead of breaking `saipen continue`.

## 2. Command

```
saimail-local saipen capabilities --workspace WS [--project-root P] [--seat S] --json
```

Exit code 0 for every state. The acting seat and project come from the SAIPEN
binding (`--seat` > `SAIPEN_AGENT` > `STATE.agent`, lineage from IDENTITY); a
missing or unreadable project is the state `PROJECT_NOT_BOUND`, not a refusal.

## 3. Document (`SAIMAIL_CAPABILITIES_1` v1, in `capabilities`)

| Field | Content |
|---|---|
| `api` | command schema/version, outbox and participants schemas, the closed trigger list |
| `seat` | acting seat, its source, the mailbox seat, `matches` |
| `project` | bound lineage or UNAVAILABLE |
| `workspace` | root, state, custody mode, peer count |
| `capabilities` | per capability: `state`, `reason` (+ detail) |
| `awareness` | unread headers, current topic, on-current-topic count, `complete`, scan budget |
| `outbox` | pending, retrying, attempts, failed, oldest pending seconds, last error, last delivery |
| `overall`, `reasons` | channel state and sorted closed reasons |

Capability states follow SAIOPP capability truth: `AVAILABLE`, `DEGRADED`,
`REQUIRES_HUMAN`, `UNAVAILABLE`, `UNVERIFIED` (never promoted by assumption).
Capabilities: `signing` (always `UNVERIFIED`, reason `KEYS_NOT_CHECKED`: the check
touches no key), `header_awareness`, `durable_outbox` (`REQUIRES_HUMAN` on failed
intents, `DEGRADED` when an open intent is older than one hour),
`participant_registry` (`REQUIRES_HUMAN` with no admitted participant). A later
capability (notify, V6-08) adds its own entry.

Closed reasons: `WORKSPACE_MISSING`, `WORKSPACE_INVALID`, `SEAT_MISMATCH`,
`SEAT_UNKNOWN`, `PROJECT_NOT_BOUND`, `NO_PARTICIPANTS`, `OUTBOX_BACKLOG`,
`OUTBOX_FAILED`, `OUTBOX_CORRUPT`, `PARTICIPANTS_CORRUPT`, `INBOX_UNREADABLE`,
`KEYS_NOT_CHECKED`.

Overall: `UNAVAILABLE` when the mailbox is unusable or the seat does not match;
`DEGRADED` when any capability is not available or no project is bound;
otherwise `AVAILABLE`.

## 4. Invariants

- **A wrong seat sees nothing.** On `SEAT_MISMATCH` the document carries no
  awareness, outbox or capability entries: no counts, ids or topics of another
  agent's mailbox (the SAIMAIL-side answer to the T-117 seat finding).
- **No secret.** The header view (D-059) only; zero credential-store reads.
- **No plaintext.** Counts and classes only.
- **Never a crash.** Corrupt outbox or registry files are named reasons; the
  document still arrives.

## 5. Evidence

`tests/test_capabilities.py` (10 controls) and six source mutants caught
(`.saipen/evidence/T-121-capabilities/`).
