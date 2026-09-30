"""Read-only repository search and before-byte evidence for T-114."""
import collections
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path.cwd()
OUT = ROOT / '.saipen/evidence/T-114-truth'
OUT.mkdir(exist_ok=True)
targets = ['saimail/gui_adapter.py', 'tests/test_gui_surface.py',
           'tests/test_gui_acceptance.py', 'tests/test_repo_consistency.py',
           'humbox/CURRENT-STATE.md', 'humbox/FUTURE-GATES-V6.md',
           'humbox/SAIPEN-WORK-DESK.md', 'spec/25-DESKTOP-LOCAL-MESSENGER-v0.md']
for rel in targets:
    dest = OUT / 'before' / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        shutil.copyfile(ROOT / rel, dest)
protected = [p for prefix in ('release',) for p in (ROOT / prefix).rglob('*') if p.is_file()]
protected += [ROOT / p for p in ('humbox/SAIGIMN.mp3', 'humbox/media-assets.json',
    'saimail/postoffice.py', 'saimail/workspace.py', 'saimail_local.py',
    'saimail/gui_app.py', 'lab/stable_local_api.json', 'tests/test_reread_continuation.py',
    'spec/03-POST-OFFICE.md', 'VERSION', 'pyproject.toml')]
pins = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(protected)}
pinfile = OUT / 'protected-before.json'
if not pinfile.exists():
    pinfile.write_text(json.dumps(pins, indent=2) + '\n', encoding='utf-8')
pattern = (r'READ_REREAD_GAP|not re-readable|cannot be re-?opened|cannot be shown again|'
           r'(only|one|sole) (explicit )?decryption (path|action)|'
           r'V6-02|receiver (re-?read|continuity).{0,70}(gap|next)|'
           r'already.{0,10}READ.{0,60}cannot|content is not re-readable|'
           r'(open|reopen|reread).{0,45}(only route|impossible)|'
           r'REASON_READ_NOT_THIS_SESSION|cannot_be_reopened')
command = ['rg', '--json', '--hidden', '--no-ignore', '-i', '-g', '!.git/**',
           '-g', '!.saipen/evidence/T-114-truth/**',
           '-g', '!.saipen/kitchen/t114_scout.py', pattern, '.']
result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
assert result.returncode in (0, 1), result.stderr
matches = []
for raw in result.stdout.splitlines():
    item = json.loads(raw)
    if item['type'] == 'match':
        data = item['data']
        matches.append({'path': data['path']['text'].removeprefix('.\\').replace('\\', '/'),
                        'line': data['line_number'], 'text': data['lines']['text'].rstrip()})
(OUT / 'search-before.json').write_text(json.dumps({'command': command, 'matches': matches},
    indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps({'protected_files': len(pins), 'matches': len(matches),
                  'paths': dict(collections.Counter(m['path'] for m in matches))}, indent=2))
