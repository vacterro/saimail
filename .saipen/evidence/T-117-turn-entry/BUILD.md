# T-117 BUILD: secret-free header reads for the SAIPEN turn-entry hook

Defect class eliminated: a metadata (header-only) read that holds secrets.

## Product change

- `saimail/workspace.py` (diff: `workspace.diff`, before bytes hash-verified
  against `.saipen/evidence/T-114-truth/protected-before.json` via the identical
  `build/lib` copy):
  - `_read_durable_identity(root)`: the public validation formerly inline in
    `load_workspace` (marker, identity file, seat/created agreement, v1 field set
    and hex shape, v2 public projection and handles). Error codes and messages
    unchanged; order unchanged.
  - `load_workspace` = shared validator + private-key step (raw derivation or
    os-store retrieval), unchanged behaviour.
  - `load_workspace_headers(root)` -> `WorkspaceHeaders` (root, seat, created,
    recipient public key, kids, custody). No private-key object, no store read.
  - `_post_office(...)`: one Post Office constructor from public keys, used by
    `Workspace.office` and `WorkspaceHeaders.office` (same registries as before).
  - `list_inbox`/`query_inbox` annotations accept either view; `__all__` exports.
- `saimail_local.py` (diff: `saimail_local.diff`): `inbox`, `saipen telegrams`,
  `saipen enter`, `saipen brief` load the header view; `saipen telegram`, `open`,
  `reopen`, `reply`, `send` keep the full load.
- `lab/stable_local_api.json` (diff: `stable_local_api.diff`): two additive
  stable entries.

Line endings of every touched file preserved (workspace.py and saimail_local.py
CRLF, specs LF, roadmap CRLF, README CR-CR-LF, CHANGELOG mixed).

## Tests

- New `tests/test_turn_entry_headers.py` (8): no private key on the view; zero
  store reads for all five header commands with `custody.read_key` and
  `custody.classify_backend` guarded; locked store still counts while `open`
  refuses `CUSTODY_ACCESS_FAILED`; results identical to the full load (listing,
  three queries, telegrams, brief context shared across loads); every public
  refusal identical in raw and os-store; the private-identity boundary; the
  SAIPEN-consumed fields pinned (refusal code in `status`, no `code`).
- `tests/test_repo_consistency.py`: V6-03 oracle (humbox table row, spec/26 §7,
  D-059, API map, and a structural check that header commands load the view
  while open/reopen/reply/telegram keep the full load).

## Red controls (`red-controls.txt`, `.saipen/kitchen/t117_red_control.py`)

- Exact pre-T-117 bytes in an isolated copy: 7 failed / 1 passed (the pinned
  contract, as designed); the two behavioural failures are the defect itself
  ("a header-only read reached the credential store"; locked store count).
- Marker-only header loader mutant: both public-check parity controls fail.
- Store-touch probe (`.saipen/kitchen/t117_probe_store_touch.py`): before
  `secret_reads=2`, locked `CUSTODY_ACCESS_FAILED`; after `secret_reads=0`,
  locked `OK match_count=1`.

## Docs

`humbox/CURRENT-STATE.md` (banner, V6-03 section, next step),
`humbox/FUTURE-GATES-V6.md` (header, L5, deps, §13/§14 pointers, §15),
`humbox/SAIPEN-WORK-DESK.md` (turn-entry setup), `spec/26` (§3, §6 update, §7),
`spec/27` (admission load), `spec/20` (header view is not an identity load),
`spec/DECISIONS-D059.md`, `README.md` (one sentence), `CHANGELOG.md`.
Lifecycle wording defers to STATE/BOARD/LOG (T-116 class guard green).

## Checks at BUILD end

- Lint `ruff check --select E4,E7,E9,F` on touched Python: PASS. Default ruff
  shows the same 2 pre-existing findings in workspace.py before and after
  (RUF013 `_seal_deliver`, RUF022 `__all__` order).
- Protected boundary `t117_protect.py check`: 222 protected, 0 changed.
- Focused: 383 prior controls + new suite + repo consistency green.

## Cross-project findings (recorded, not changed)

SAIPEN `telegrams.py` reads `answer["code"]` on refusal; SAIMAIL carries it in
`status`. SAIPEN `read_command` interpolates paths unquoted.
