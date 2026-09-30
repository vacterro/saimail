# T-116 BUILD checkpoint

Active Work T-116 (SRC-105), phase BUILD. No product code changed.

## Changed files (attributable)

| File | Change |
|---|---|
| humbox/CURRENT-STATE.md | top beacon, v6 position bullet and NEXT EXECUTABLE STEP: T-114 DONE (E-1541) recorded; active Work deferred to STATE/BOARD/LOG; next direction = separate turn-entry hook evaluation needing its own Work; `(this ticket)` deixis replaced by explicit T-79/T-81; digest drift re-observation + finding pointer |
| humbox/FUTURE-GATES-V6.md | intro, §3 principle, D3 lane bullet, §13 later closure, §14 release boundary, §10 recovery checklist: same rewrite |
| humbox/SAIPEN-WORK-DESK.md | Next useful direction: same rewrite |
| .saipen/kitchen/T-113-reread-continuation.md | later-closure annotation line only; historical design body untouched |
| tests/test_repo_consistency.py | removed positive `T-114 owns subsequent continuation` requirement; added `RECOVERY_DOCS`, `STALE_OWNERSHIP`, `stale_ownership_claims`, `test_recovery_docs_bind_no_ticket_as_active_owner`, 5-case in-memory `test_stale_ownership_guard_detects_the_defect_class`; G13/G17/publication checks tightened from bare tokens to `G13 PENDING_EXTERNAL`, `G17 ABSENT`, `publication NONE` |

Protocol artifacts: this evidence directory; kitchen helpers `t116_protect.py`,
`t116_red_control.py`, `t116_validate.py`, `t116_probe.py`, `t116_eol.py`.

## Oracle design

Class guard, not a ticket snapshot. In the recovery docs it rejects:
`T-<n> owns …`, `owns subsequent/that/next continuation`,
`T-<n> is/remains (still) (the) active/current …`, `current (truth) repair`,
`in/inside/outside/part of this repair`, `after … is accepted`. Blocks marked
`(historical)` or beginning `Historical` are allowed evidence. Positive
invariants: STATE/BOARD/LOG named as active-Work authority; `T-114 DONE
(E-1541)`; hook not implemented by T-114; existing T-113/V6-02/Reopen/
metadata-only/frozen-a3/G13/G17/publication/stable-API checks retained.
"STATE owns the current phase" alone is valid generic guidance (class E) and
is not banned.

## Red controls (red-controls.json)

12/12 FAILED_AS_EXPECTED through the real test function with `read`
substituted in memory: R1 old owner sentence, R2 "still the current repair
owner after E-1541", R3 restored "After truth reconciliation is accepted"
wording, each in all three docs; R0 the actual post-T-114 prose reconstructed
from T-114 `before/` + `final.diff`. Document bytes unchanged afterwards.

## Notes

- Existing T-114 guard `saved T-113.{0,50}next` flagged an intermediate
  sentence order; prose was reordered, the guard was not weakened.
- Line endings: the three humbox files and the test file had mixed CRLF/LF;
  editing tools normalized them. Content is unaffected (tests read text mode;
  git autocrlf normalizes the tracked test file).
- Lint: `ruff check --select E4,E7,E9,F` on touched Python: PASS.
- Focused `tests/test_repo_consistency.py`: green before VERIFY.
- Protected set: 172 hashes recorded before edits (protected-before.json).

Next exact action: VERIFY — focused suites, then canonical full suite with
zero concurrent STATE/BOARD/LOG/source writes, protected check, validator.
