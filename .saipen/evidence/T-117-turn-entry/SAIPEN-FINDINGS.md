# T-117 cross-project findings for the SAIPEN protocolist

Scope: `V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN\tools\saipen_engine\telegrams.py`
(SAIPEN T-1497, SRC-113), evaluated from SAIMAIL T-117 (V6-03). Nothing in the
SAIPEN tree was changed from this repository.

## Works

Real route, read-only: `SAIMAIL_WORKSPACE=<scratch mailbox> saipen status --json`
returned `state OK, unread 2, on_current_work 1, complete true`
(`live-saipen-status-telegrams.json`); without the carrier it returned
`NOT_CONFIGURED` and started no process.

## Finding 1 — refusal cause read from the wrong field

`turn_entry()` takes the cause from `answer.get("code")`. SAIMAIL's
`LOCAL_WORKSPACE_COMMAND_1` refusal is `ok: false`, exit 1, code in `status`,
and has no `code` field (pinned by
`tests/test_turn_entry_headers.py::test_the_saipen_turn_entry_contract_fields_are_pinned`).
Result: every refusal renders as `saimail-local saipen telegrams exited 1` with
no cause. Option: read `status` when `ok` is false.

## Finding 2 — read_command is not copy-safe

`read_command` interpolates `--project-root`, `--workspace` and `--seat`
unquoted. A path with a space yields a hint that does not run when pasted.
Option: quote per host shell, or also return an argv list.

## Observation 3 — the count is not seat-checked

The read counts whatever mailbox `SAIMAIL_WORKSPACE` names. In the live run the
mailbox seat was `beta` and the acting seat `claude-account2`; counts were shown,
and the suggested `saipen brief` would then refuse `SAIPEN_SEAT_MISMATCH`. The
answer already carries `workspace.seat` (now pinned by the same test). Option:
compare it with the acting seat and report a mismatch state instead of counts.

## Context fixed on the SAIMAIL side (FYI)

The SAIMAIL read used the full workspace load; in os-store custody each SAIPEN
turn entry retrieved both private keys from the OS credential store to count
headers, and a locked store produced SAIPEN `ERROR`. SAIMAIL D-059
(`load_workspace_headers`) removes that: zero store reads, and a locked store
still yields counts.
