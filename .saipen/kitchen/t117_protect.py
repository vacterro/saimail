"""T-117 protected-boundary snapshot: `before` records, `check` compares.

Protected: frozen release trees and evidence, the user audio asset and its
manifest, version surfaces, Post Office / GUI product code, the frozen decisions
log, T-113 tests, earlier Work evidence and receipts. The files T-117 is allowed
to change (workspace loader, CLI seam dispatch, API map, specs, humbox docs,
changelog, tests) are deliberately excluded.
"""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
out = root / '.saipen/evidence/T-117-turn-entry'
ALLOWED = {'saimail/workspace.py', 'saimail_local.py', 'lab/stable_local_api.json'}
t114 = json.loads((root / '.saipen/evidence/T-114-truth/protected-before.json').read_text(encoding='utf-8'))
paths = set(t114) - ALLOWED
for tree in ('release', '.saipen/evidence/T-114-truth', '.saipen/evidence/T-116-truth'):
    paths |= {p.relative_to(root).as_posix() for p in (root / tree).rglob('*') if p.is_file()}
paths |= {p.relative_to(root).as_posix() for p in (root / '.saipen/intake/active').glob('SRC-10[0-6]*')}
paths |= {p.relative_to(root).as_posix() for p in (root / 'saimail').glob('*.py')} - ALLOWED
paths |= {'spec/DECISIONS.md', 'spec/03-POST-OFFICE.md', 'spec/25-DESKTOP-LOCAL-MESSENGER-v0.md',
          'humbox/SAIGIMN.mp3', 'humbox/media-assets.json', 'VERSION', 'pyproject.toml',
          'tests/test_reread_continuation.py'}


def snapshot():
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in sorted(paths)}


if sys.argv[1] == 'before':
    (out / 'protected-before.json').write_text(json.dumps(snapshot(), indent=1) + '\n', encoding='utf-8')
    print('recorded', len(paths))
else:
    before = json.loads((out / 'protected-before.json').read_text(encoding='utf-8'))
    now = snapshot()
    changed = sorted(p for p in before if before[p] != now.get(p))
    report = {'protected': len(before), 'changed': changed, 'result': 'PASS' if not changed else 'FAIL'}
    (out / 'protected-after.json').write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    print(json.dumps(report))
    raise SystemExit(1 if changed else 0)
