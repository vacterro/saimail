# T-117 SCOUT: evaluation of the SAIPEN turn-entry hook against SAIMAIL

Source: SRC-106 ("continue by meaning; the beacon is humbox"). Seat: `claude-account2`
(agent home `.claude-account2`, CORE 1.4 / init.md seat derivation).

## Where humbox points

`humbox/CURRENT-STATE.md`, `humbox/FUTURE-GATES-V6.md` §13/§14 and
`humbox/SAIPEN-WORK-DESK.md` all name one next separate direction: evaluation of
the SAIPEN-owned turn-entry hook for Work Desk / SAITELEMES (bounded header-only
awareness, receiver-owned authority, zero automatic open). It needs its own Work,
source and admission. T-117 is that Work.

## What exists on the SAIPEN side (not recorded in humbox)

`_SAIPEN/future_gate/FUTURE GATE — SAITELEMES AUTOMATIC AGENT TELEGRAMS_20260922.md`
states PART 3 (turn-entry read) IMPLEMENTED by SAIPEN T-1497 (SAIPEN SRC-113),
2026-09-23. `tools/saipen_engine/telegrams.py` runs
`saimail-local --json saipen telegrams --workspace $SAIMAIL_WORKSPACE --scan-budget 200`
when `SAIMAIL_WORKSPACE` is set and `saimail-local` is on PATH, and reports
counts only (`unread`, `on_current_work`, `complete`) in `continue`/`status` JSON.
Automatic send (parts 1-2) remains unauthorized. SAIMAIL humbox still describes
the hook as unimplemented: a recovery-truth gap.

## Live end-to-end evaluation (scratch mailboxes, real CLI, real SAIPEN module)

- `saimail-local` on PATH is the editable install of this checkout.
- Two raw workspaces, mutual registration, two sends (topics `T-117`, `T-7`).
- `saimail-local --json saipen telegrams --workspace B --scan-budget 200`:
  exit 0, `ok true`, `match_count 2`, `exhausted false`, items carry `topic`.
- `saipen_engine.telegrams.turn_entry(...)` with task `T-117`:
  `state OK, unread 2, on_current_work 1, complete true`, counts only.

The fields SAIPEN consumes are `ok`/exit code, `match_count`, `exhausted`,
`items[].topic`. Nothing in SAIMAIL pins them as a cross-project contract.

## Defect found (red control)

`saipen telegrams` (and `saipen enter`/`brief`) call `load_workspace`, which in
`os-store` custody retrieves BOTH private keys from the OS credential store.
The index scan needs only public keys (`Workspace.office()` uses the recipient
public key and peers' public sender keys). Probe
(`probe_store_touch.py`, in-process CLI, counting in-memory store):

    send: ACCEPTED
    unlocked store: rc=0 status=OK match_count=1 secret_reads=2
    locked store:   rc=1 status=CUSTODY_ACCESS_FAILED match_count=None secret_reads=1

So every automatic turn entry pulls the signing and decryption keys out of
custody to count headers, and a locked or prompting store turns the count into
an error (SAIPEN `ERROR`) although no secret is needed. Least-privilege and
availability defect on the SAIMAIL side of the seam.

## Secondary observation (SAIPEN-owned, not changed here)

SAIPEN's `read_command` interpolates paths unquoted; a workspace path with a
space is not copy-pasteable. Recorded as a cross-project finding only.

## Reuse points / architecture

- `saimail/workspace.py`: `_validate_marker` (public keys + self-consistent kids),
  `_validate_identity_v2` (public projection, no store), `Workspace.office`,
  `query_inbox`, `command_result` (uses root/seat/kids/custody only).
- `saimail/saipen_bridge.py`: `telegrams`, `enter`, `work_brief` use only
  `workspace.seat/root` and `query_inbox`.
- `saimail_local.py` `_cmd_saipen`: the only place choosing the loader.
- Tests: `tests/test_saitelemes.py`, `tests/test_saipen_brief.py`,
  `tests/test_workspace_custody.py` (`InMemoryCredentialStore`,
  `set_credential_store`), `tests/test_local_entrypoint.py` (API map resolution).

## Commands (cited, KNOWLEDGE/VERIFICATION.md)

Full suite `python -m pytest -q`; lint `ruff check` per pyproject.

## Baselines

SAIPEN validator before edits: 2 blocking problems (inherited: `T-41`
source_receipt_unresolved_work; improve-report fingerprint) and 24 warnings.
