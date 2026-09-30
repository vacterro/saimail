"""T-116 red controls: tamper recovery prose in memory only; real oracle functions must fail."""
import hashlib
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'tests'))
sys.dont_write_bytecode = True
import test_repo_consistency as oracle  # noqa: E402

out = root / '.saipen/evidence/T-116-truth'
DOCS = ('humbox/CURRENT-STATE.md', 'humbox/FUTURE-GATES-V6.md', 'humbox/SAIPEN-WORK-DESK.md')
ANCHOR = {
    'humbox/CURRENT-STATE.md': '## NEXT EXECUTABLE STEP\n',
    'humbox/FUTURE-GATES-V6.md': '## 14. V6-02 — Receiver re-read continuity (T-113)\n',
    'humbox/SAIPEN-WORK-DESK.md': '## Next useful direction\n',
}
CONTROLS = {
    'R1-old-owner-sentence': 'T-114 owns subsequent continuation.',
    'R2-current-repair-owner': 'T-114 is still the current repair owner after E-1541.',
    'R3-pending-acceptance': ('After truth reconciliation is accepted, evaluate the separate '
                              'SAIPEN-owned turn-entry hook.'),
}
before = {d: hashlib.sha256((root / d).read_bytes()).hexdigest() for d in DOCS}
real_read = oracle.read
results = []
for doc in DOCS:
    for name, sentence in CONTROLS.items():
        def tampered(path, doc=doc, sentence=sentence):
            text = real_read(path)
            if Path(path).resolve() == (root / doc).resolve():
                anchor = ANCHOR[doc]
                assert anchor in text, (doc, anchor)
                text = text.replace(anchor, anchor + '\n' + sentence + '\n', 1)
            return text
        oracle.read = tampered
        try:
            oracle.test_recovery_docs_bind_no_ticket_as_active_owner()
            outcome = 'NOT_DETECTED'
        except AssertionError as exc:
            outcome = 'FAILED_AS_EXPECTED'
            detail = str(exc).splitlines()[0][:200]
        finally:
            oracle.read = real_read
        results.append({'control': name, 'doc': doc, 'outcome': outcome,
                        'detail': detail if outcome != 'NOT_DETECTED' else None})


def post_t114_text(doc):
    """Content of `doc` as T-114 closed it: its before/ snapshot plus final.diff hunks."""
    import re
    diff = (root / '.saipen/evidence/T-114-truth/final.diff').read_bytes().decode('utf-8').replace('\r\n', '\n')
    section = diff.split(f'--- before/{doc}\n', 1)[1].split('\n--- ', 1)[0]
    old = (root / '.saipen/evidence/T-114-truth/before' / doc).read_text(encoding='utf-8').split('\n')
    new, pos = [], 0
    for m in re.finditer(r'^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@.*\n((?:[ +\-].*\n?)*)', section, re.M):
        start = int(m.group(1)) - 1 if m.group(2) != '0' else int(m.group(1))
        new += old[pos:start]
        pos = start
        for line in filter(None, m.group(3).split('\n')):
            if line[0] == ' ':
                new.append(old[pos])
                pos += 1
            elif line[0] == '-':
                pos += 1
            else:
                new.append(line[1:])
    return '\n'.join(new + old[pos:])


for doc in DOCS:
    stale = post_t114_text(doc)
    claims = oracle.stale_ownership_claims(stale)
    results.append({'control': 'R0-actual-post-T114-bytes', 'doc': doc,
                    'outcome': 'FAILED_AS_EXPECTED' if claims else 'NOT_DETECTED',
                    'detail': claims[:3]})
oracle.test_recovery_docs_bind_no_ticket_as_active_owner()  # restored bytes are green
after = {d: hashlib.sha256((root / d).read_bytes()).hexdigest() for d in DOCS}
report = {'controls': results, 'all_detected': all(r['outcome'] == 'FAILED_AS_EXPECTED' for r in results),
          'restored_green': True, 'doc_bytes_unchanged': before == after}
(out / 'red-controls.json').write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'controls'}), len(results))
raise SystemExit(0 if report['all_detected'] and report['doc_bytes_unchanged'] else 1)
