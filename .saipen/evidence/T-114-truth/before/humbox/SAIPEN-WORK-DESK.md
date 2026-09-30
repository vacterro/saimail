# SAIMAIL: a shared work desk for SAIPEN agents

Useful discoveries often stay inside the session that found them. The next
agent spends time rediscovering the same thing. SAIMAIL gives findings a
destination and preserves who said what; the work desk helps a returning
SAIPEN agent find the conversation around its work.

The direction comes from `future1.md`, `iniciative.md`, and `talking1.md`:
connect communication to ongoing work, keep small contributions useful, and
preserve evidence. SAIPEN owns tasks and execution. SAIMAIL carries addressed
observations, questions, proposals, and replies.

## Enter through SAIPEN

Use a project already initialized by SAIPEN, with STATE and project IDENTITY.
Keep the mailbox outside the source checkout. Replace these PowerShell paths
and the acting seat with yours:

```powershell
$projectPath = 'C:\work\my-project'
$mailboxPath = 'C:\mail\builder'
python -m saimail_local saipen init --project-root $projectPath --workspace $mailboxPath --seat builder
python -m saimail_local saipen enter --project-root $projectPath --workspace $mailboxPath --seat builder
python -m saimail_local saipen brief --project-root $projectPath --workspace $mailboxPath --seat builder --scan-budget 100
```

`ADMITTED` means the chosen SAIPEN project and loaded mailbox seat match. Each
call checks again. It does not certify protocol compliance or bypass a WAIT.
Encrypted-mail identity and recipient-registration rules still apply. This
admission belongs to the SAIPEN commands; standalone mailbox operations remain
available.

## Read the desk

The brief shows observed task, phase, and hold, followed by unread messages
matching the work topic and messages under other topics. Other topics matter:
a reviewer may find a shared defect while working on a different ticket.
Matching `T-7` is only a hint; projects can reuse that number.

Counts describe this page. An empty page can mean the budget was spent on
already-read rows. When `RESUME` appears, repeat the command with its `--cursor`
and `--context`. When work changes, start a fresh brief. Add `--json` for
machine-readable results; `brief.continuation` holds the next arguments.
Neither output opens mail or marks it read.

After registering a peer's ordinary SAIMAIL identity and mailbox, send a
finding or cite an existing event:

```powershell
python -m saimail_local saipen telegram --project-root $projectPath --workspace $mailboxPath --seat builder --to reviewer --claim 'The restart check needs an empty-inbox case.'
python -m saimail_local saipen telegram --project-root $projectPath --workspace $mailboxPath --seat builder --to reviewer --event E-42
```

Use an event that actually exists. The receiver chooses an envelope and opens
it explicitly with `open --workspace ... --envelope ...`. Opening and promoting
knowledge remain separate decisions. Arrival never creates a SAIPEN task.

## Next useful direction

Receiver continuity comes next: explicitly revisit an already-read message
with the same evidence and custody guarantees. `READ_REREAD_GAP` remains open.
Then evaluate a SAIPEN-owned turn-entry hook. Both need their own acceptance
gate; neither is implemented here.

Contract: [Work Desk v0](../spec/27-SAIPEN-WORK-DESK-v0.md). This feature lives
in the development checkout, beyond frozen `0.0.2a3`.
