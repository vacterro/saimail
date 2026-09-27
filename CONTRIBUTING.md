# Contributing

SAIMAIL is local-first. Keep patches small, evidence-backed and offline.

## Ground rules

- Do not modify frozen release trees: `release/local-alpha/`,
  `release/candidates/0.0.2a2/`, `release/evidence/a2/`.
- Do not bump `VERSION` or publish unless an operator ticket says so.
- The base package stays dependency-free; optional work goes in extras
  (`gui`, `crypto`, `credentials`, `lab`, `hardware-yubikey`).
- No network or model calls on local CLI paths. Lab live runs need an
  explicit registered ticket.
- Never commit private keys, seed material, OS credential-store secrets, or
  sealed payload content belonging to someone else.

## Checks before you open a change

```
pip install -e ".[test]"
python -m pytest -q
python -m ruff check
```

Repository consistency (README links, roadmap authority, version mirrors,
release boundaries) lives in `tests/test_repo_consistency.py`. The full suite
is the gate; do not weaken or skip tests to make a change pass.

## Security

Report vulnerabilities per [SECURITY.md](SECURITY.md). Do not open public
issues for unpatched vulnerabilities.

## Scope

Protocol changes need an explicit decision record in `spec/DECISIONS.md`
(or an additive `DECISIONS-D###.md` when the parent file is hash-pinned).
Presentation-only work belongs to the current roadmap gate in `humbox/`.
