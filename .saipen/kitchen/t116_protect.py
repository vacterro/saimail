"""T-116 protected-boundary snapshot: `before` records, `check` compares."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
out = root / '.saipen/evidence/T-116-truth'
t114 = json.loads((root / '.saipen/evidence/T-114-truth/protected-before.json').read_text(encoding='utf-8'))
paths = set(t114)
paths |= {p.relative_to(root).as_posix() for p in (root / 'saimail').rglob('*.py')}
paths |= {p.relative_to(root).as_posix() for p in (root / '.saipen/evidence/T-114-truth').rglob('*') if p.is_file()}
paths |= {p.relative_to(root).as_posix() for p in (root / '.saipen/intake/active').glob('SRC-10[345]*')}
paths |= {'.saipen/kitchen/T-114-user-mission.md', 'spec/26-SAITELEMES-v0.md',
          'spec/27-SAIPEN-WORK-DESK-v0.md', 'spec/25-DESKTOP-LOCAL-MESSENGER-v0.md'}


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
