# T-120 BUILD: V6-06 project-local participant registry (SRC-108 item 4)

Defect class eliminated: an automatic sender that has to guess its recipient.

- New `saimail/participants.py`: `participants.json` (`SAIMAIL_PARTICIPANTS_1`)
  lineage -> seat -> {alias, pinned sender/recipient kid, triggers, admitted_at};
  admit (explicit, pins identity, idempotent, conflict on change), revoke, list,
  resolve (refuses unknown project/seat, trigger not admitted, bad trigger, self,
  identity drift); closed trigger set with fixed existing SENV2 kinds; OS lock;
  strict fail-closed read.
- `saimail_local.py`: `saipen participant admit|revoke|resolve|list`; lineage from
  `bridge.enter` (Work Desk admission: IDENTITY present, acting seat = workspace
  seat); header view (keyless). `saimail/workspace.py`: renderer lines only.
- API map: 4 APIs + `local_participants` failure group.
- Tests: `tests/test_participants.py` (12); V6-06 oracle (additive, 0 removed lines).
- Red controls (`red-controls.txt`, runner `.saipen/kitchen/wave_red_mutants.py`,
  spec `mutants.json`): unmutated 12 passed; mutants no_identity_pin,
  no_project_scope, no_trigger_check, self_allowed, lenient_file all caught.
- Docs: spec/29, D-061, roadmap §16 row + subsection, CURRENT-STATE banner + wave
  bullet, CHANGELOG (line endings preserved by byte-scoped edits).
