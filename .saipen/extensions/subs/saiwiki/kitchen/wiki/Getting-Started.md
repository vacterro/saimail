# Getting Started

Everything below is the advertised command being the command that works. The
library itself has no dependencies; the `test` extra installs everything the
full suite needs.

## Install and test

```
pip install -e ".[test]"
python -m pytest -q
```

That is the canonical suite. Hardware custody is a separate optional extra,
never installed at runtime:

```
pip install -e ".[hardware-yubikey]"
python -m saimail.hardware_piv inspect          # strictly read-only
python -m saimail.hardware_piv verify --device NAME --slot 9D
```

Without the extra, every hardware entry point refuses with
`HARDWARE_PROVIDER_UNAVAILABLE`; with the extra but without a token, a manual
verification is reported `NOT_RUN_NO_HARDWARE` — never `PASS`, never `FAIL`.
Both commands are non-destructive: no provisioning, import, deletion or reset
path, no automatic slot choice, no `--pin` option. The PIN is only ever typed
at an interactive prompt.

## A persistent local workspace

Two workspaces, two persistent identities, one real local message across
separate process invocations:

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
saimail-local reopen --workspace ws-b --envelope sha256:...  # re-read an opened message, no state change
saimail-local send --workspace ws-a --redeliver sha256:...   # exact replay -> DUPLICATE
saimail-local acceptance --root fresh-dir       # one-command PASS/FAIL harness
```

Identity survives restarts: `saimail-local identity` returns the same public
fingerprints after any number of separate invocations. Repeating the exact
delivery is the canonical `DUPLICATE` — the original `RECEIVED_AT` is kept and
no second unread message appears. `open` requires the exact message identity,
moves it to read state and never promotes.

### Finding a message without opening it

`inbox` doubles as a bounded, metadata-only triage query. With no extra flags it
is the unchanged listing; adding any filter switches to the bounded
`inbox-query` result over the canonical index:

```
saimail-local inbox --workspace ws-b --state UNREAD
saimail-local inbox --workspace ws-b --from-seat SAIMAIL-A --topic ci
saimail-local inbox --workspace ws-b --scan-budget 50           # -> cursor
```

Filters combine with **AND only**; time bounds are receiver-local
`received_at`. A query never decrypts, opens, moves or mutates anything — there
is **no** full-text, substring, regex, fuzzy or semantic search. A match gives
you the `ENVELOPE_ID` for an explicit `open`.

### Answering a message

```
saimail-local open  --workspace ws-b --envelope sha256:ORIGINAL   # must be READ first
saimail-local reply --workspace ws-b --envelope sha256:ORIGINAL --claim "one line back"
saimail-local inbox --workspace ws-a --ref sha256:ORIGINAL        # discover the reply
```

`reply` continues one already-opened message through the existing SENV2 `REF`
header field. The target must be `READ` (`REPLY_TARGET_UNREAD` otherwise); the
reply recipient is the original sender, resolved from the message's own indexed
metadata — the caller cannot redirect a reply with `--to`.

### Identity key custody

A new workspace is `raw` by default: private keys as raw software files, **not
encrypted at rest** — a copied workspace directory copies the identity. Every
fresh `init` prints a bounded first-run custody notice saying exactly that
(D-054/D-055). Protected custody is an explicit opt-in:

```
saimail-local init --workspace ws-a --seat SAIMAIL-A --custody os-store
saimail-local custody status  --workspace ws-a
saimail-local custody migrate --workspace ws-a    # explicit; preserves fingerprints
```

In `os-store` custody the private keys live in the OS credential store under
the separate `credential://saimail-workspace/...` namespace. A missing,
substituted or failing store fails closed with a named `CUSTODY_*` error;
nothing is regenerated or read from an environment variable. Protected custody
requires the `credentials` extra (`pip install "saimail[credentials]"`).

### The desktop messenger

```
pip install "saimail[gui]"
saimail-gui
```

One native desktop window (PySide6, optional extra only; the base install works
without Qt and `saimail-gui` exits with one actionable line when the extra is
absent). It presents the workspace workflow above: inbox with metadata rows,
explicit Open, READ-gated Reply, explicit Refresh, AND-only filters, a
persistent status strip, and the custody status with explicit migration. The
visual language is the canonical Golden Default theme. It adds no protocol
rule, no network path, no background polling and no second backend.

## The SAIPEN work desk (checkout only)

These commands live on the current tree, ahead of the frozen `0.0.2a3` wheel.
They let an agent working under SAIPEN bind to its enclosing project, tell one
other running agent one thing, and read what is waiting — all header-only, no
private key touched (T-117). SAIPEN `init`, `telegram` and `brief` require a
valid project IDENTITY:

```
saimail-local saipen enter --workspace ws-a
saimail-local saipen brief --workspace ws-a
saimail-local saipen status --workspace ws-a
saimail-local --json saipen telegrams --workspace ws-a    # turn-entry unread count
```

A SAITELEME is one sealed SENV2 message to one registered running agent — no
new wire kind, no importance field (D-058). Send one, then read the bounded
header-only rows:

```
saimail-local saipen telegram --workspace ws-a --to bob --claim "one line for bob"
saimail-local saipen telegram --workspace ws-a --to bob --event E-1358   # cite a LOG line instead
saimail-local saipen telegrams --workspace ws-a --topic T-124            # exact Work id filter
```

`--claim` and `--event` are mutually exclusive: a telegram carries one line of
text **or** one S2 citation, never both. The default `--kind` is `DISCOVERY`
and the default `--topic` is the SAIPEN Work id from `STATE.task`.

### Automatic notifications to admitted participants

Automation routes only to seats explicitly admitted for this project (D-061),
and `saipen notify` is the only automatic send path (D-063):

```
saimail-local saipen participant admit --workspace ws-a --participant SAIMAIL-B --alias bob
saimail-local saipen participant list --workspace ws-a
saimail-local saipen notify --workspace ws-a --trigger blocker --to SAIMAIL-B --claim "one line"
saimail-local saipen capabilities --workspace ws-a       # keyless health, exits 0 always
```

The `--trigger` is a closed set — `blocker`, `finding`, `dependency`,
`ownership`, `handoff`, `reply` — and the trigger alone fixes the SENV2 kind;
there is no priority or urgency parameter. Over the receiver's rolling
attention budget the send becomes `NOTIFY_SUPPRESSED`: exit 0, nothing written,
never retried.

### Durable idempotent sends

`outbox` records a send under an idempotency key, seals it once, and replays
identical bytes on retry — the same key never sends twice (D-060):

```
saimail-local outbox send --workspace ws-a --to bob --key ci-42 --claim "one line for bob"
saimail-local outbox resume --workspace ws-a --budget 25   # advance due PENDING intents
saimail-local outbox retry  --workspace ws-a --key ci-42   # re-arm one FAILED intent, once
saimail-local outbox status --workspace ws-a               # keyless, plaintext-free health
```

`--claim` and `--record` (a canonical SAILANG record file) are mutually
exclusive. A `SEALED` intent can be delivered from the secret-free header view;
transient failures back off automatically, terminal ones need the explicit
`retry`.

## Run the benchmarks

```
python bench/t9b.py --out bench/out
python bench/r1_shootout.py --out bench/out
python bench/selector_run.py --out bench/out
python lab/saifren_run.py --out lab/out --dry-run
python lab/stability_run.py --out lab/out --dry-run
python lab/project_corpus_pilot.py --register   # frozen once, before any capture
python lab/project_corpus_pilot.py --run
python lab/project_corpus_generation_pilot.py --register   # frozen once, before any live call
python lab/project_corpus_generation_pilot.py --dry-run
```

Nothing above touches the network. A live `lab/` run does, and needs the
credential below.

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
python tools/provision_sairoute_credential.py --delete      # remove it
python lab/saifren_run.py --out lab/out                     # the ordinary live run
```

The secret is typed at an interactive non-echoing prompt and confirmed once.
There is no `--key`, no `--secret` and no standard-input path. Without a TTY
the tool refuses with `SAIROUTE_PROVISIONING_REQUIRES_TTY`.

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

## Read before writing code

[Architecture](Architecture.md) first; the canonical integration path is
[spec/04-SAIPEN-SEAM.md](https://github.com/vacterro/saimail/blob/main/spec/04-SAIPEN-SEAM.md).
Most of the truth layer described in the spec already runs inside SAIPEN for
human intent; SAIMAIL generalises it to agent-to-agent mail rather than
rebuilding it.
