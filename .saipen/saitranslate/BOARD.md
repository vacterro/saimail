# Board

## TODO
- [ ] SAIT-005 translate the 27 remaining producer-owned README locales from current source -- needs an operator scope decision (27 full README translations per run is a standing cost, and `status: ready` is unreachable until they exist)
- [ ] SAIT-006 translate the GUI string surface in saimail/gui_app.py and saimail/gui_adapter.py -- BLOCKED on a Core/operator decision: the repository ships no locale format, and this producer is forbidden to invent one

## DOING
(none)

## DONE
- [x] SAIT-001 initial ja+uk translations (v0.0.1 tree) -- superseded by source drift, OUTBOX entry marked stale
- [x] SAIT-002 rebuild ja+uk README translations against current tree (README.md drifted 163->428 lines, v0.0.1->v0.0.2a2); published ready package sha256:7828d51a @epoch 2 -- corrected 25.09.26: that package is STALE, never collectable; this row previously claimed it awaited collection
- [x] SAIT-003 rebuild ja+uk README translations against the v0.0.2a3 tree; GUI surface found real with no locale format to translate it into; status draft, intentionally not collectable
- [x] SAIT-004 re-verify SAIT-003 without rebuilding: source identity byte-identical, both markers current under the pinned canonical recipe (kitchen/_source_digest.py), SCOUT's "payload stale" claim refuted; two validator defects handed to Core (E-9)
