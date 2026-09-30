"""Persist the reviewed pre-edit classification; never rewrite original matches."""
import collections
import json
from pathlib import Path

out = Path('.saipen/evidence/T-114-truth')
data = json.loads((out / 'search-before.json').read_text(encoding='utf-8'))
for match in data['matches']:
    path, line = match['path'], match['line']
    if path.startswith(('build/', '.pytest_cache/')):
        category, reason = 'E', 'Generated staging/cache, not imported source or recovery authority; do not hand-edit.'
    elif path.startswith(('.saipen/', 'release/')) or path == 'humbox/FUTURE-GATES-V5.md':
        category, reason = 'B', 'Historical receipt, closure proof, saved pre-T-113 design, or source-fingerprint-bound producer package.'
    elif path == 'tools/d3_release_evidence.py':
        category, reason = 'B', 'T-107 closure check; retains NOT STARTED at that historical boundary, not current product capability.'
    elif path == 'spec/25-DESKTOP-LOCAL-MESSENGER-v0.md':
        category, reason = 'B', 'Explicitly former gap / Historically, followed by T-113 closure.'
    elif path == 'saimail/gui_adapter.py' and line in (397, 426):
        category, reason = 'D', 'Refusal is guarded by state != READ; valid non-READ refusal.'
    elif path == 'humbox/CURRENT-STATE.md' and line in (794, 800, 801):
        category, reason = 'B', 'T-97 closure description; add explicit historical scope and later T-113 resolution.'
    elif path == 'humbox/CURRENT-STATE.md' and line == 900:
        category, reason = 'B', 'Explicit T-107 closure boundary; preceding saved-design future instruction is A (see additional findings).'
    elif path == 'humbox/FUTURE-GATES-V6.md' and line in (154, 183, 266):
        category, reason = 'B', 'T-104/T-107/T-110 historical boundary; adjacent current continuation must point to T-113 DONE.'
    else:
        category, reason = 'A', 'Current runtime/test/recovery assertion incorrectly denies or postpones implemented explicit Reopen.'
    match.update(category=category, rationale=reason)
data['additional_context_findings'] = [
    {'path': 'saimail/gui_adapter.py', 'lines': '13-14', 'category': 'A', 'claim': 'Content becomes visible only after open_selected; must include explicit reopen_selected.'},
    {'path': 'spec/25-DESKTOP-LOCAL-MESSENGER-v0.md', 'lines': '63-65', 'category': 'A', 'claim': 'Current interaction invariant names only first Open as content producer.'},
    {'path': 'humbox/CURRENT-STATE.md', 'lines': '898-900', 'category': 'A', 'claim': 'T-114 still directed to saved T-113 design as its first future candidate.'},
    {'path': 'humbox/FUTURE-GATES-V6.md', 'lines': '183-184', 'category': 'A', 'claim': 'After historical T-107 boundary, saved T-113 design incorrectly assigned as next for T-114.'},
    {'path': 'humbox/FUTURE-GATES-V6.md', 'lines': '266-268', 'category': 'A', 'claim': 'T-110 historical next evaluation needs dated scope and later closure annotation.'},
    {'path': 'saimail/gui_adapter.py', 'lines': '343-355, 378-381', 'category': 'C', 'claim': 'Open requires UNREAD and refuses READ; preserve.'},
    {'path': 'saimail/postoffice.py', 'lines': '1685-1736', 'category': 'C', 'claim': 'First Open lifecycle transition and ALREADY_READ refusal; preserve.'},
    {'path': 'saimail/postoffice.py', 'lines': '1757-1766', 'category': 'D', 'claim': 'Reopen requires durable READ; preserve.'},
    {'path': 'spec/02-SAIENVELOPE-v0.md; spec/04-LEGACY-v0.md; saimail/inbox_query.py; tests/test_local_workspace.py', 'category': 'E', 'claim': 'Broader reread/reopen search: cryptographic key semantics, pagination rereads and workspace reentry, unrelated to message reread gap.'},
]
(out / 'classification.json').write_text(json.dumps(data, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
print('Classified all',len(data['matches']),'matches:',dict(collections.Counter(m['category'] for m in data['matches'])))
