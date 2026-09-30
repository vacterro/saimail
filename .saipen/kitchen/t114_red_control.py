"""Run the real coherence oracle with original false runtime strings in memory."""
import ast
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[2]
out = root / '.saipen/evidence/T-114-truth'
old = ast.parse((out / 'before/saimail/gui_adapter.py').read_text(encoding='utf-8'))
values = {}
for node in old.body:
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in (
                    'REASON_OPEN_ALREADY_READ', 'REASON_READ_NOT_THIS_SESSION'):
                values[target.id] = ast.literal_eval(node.value)
values['__doc__'] = ast.get_docstring(old)
results = []
for name, value in values.items():
    code = (
        'import pytest\nfrom saimail import gui_adapter\n'
        f'setattr(gui_adapter, {name!r}, {value!r})\n'
        'raise SystemExit(pytest.main(["-q", "-o", "addopts=", '
        '"tests/test_repo_consistency.py::test_gui_read_capability_language_matches_explicit_reopen"]))\n'
    )
    result = subprocess.run([sys.executable, '-c', code], cwd=root,
                            capture_output=True, text=True, encoding='utf-8',
                            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    (out / f'red-{name}.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
    assert result.returncode == 1 and '1 failed' in result.stdout, result.stdout + result.stderr
    results.append({'mutation': name, 'exit_code': result.returncode, 'failed': 1})
    print(f'Expected RED: original {name} -> 1 failed', flush=True)
code = '''import pathlib
import pytest
root = pathlib.Path.cwd()
original = pathlib.Path.read_text
def stale(self, *args, **kwargs):
    result = original(self, *args, **kwargs)
    if self.resolve() == root / "humbox/CURRENT-STATE.md":
        result += "\\n\\nREAD_REREAD_GAP remains open.\\n"
    return result
pathlib.Path.read_text = stale
raise SystemExit(pytest.main(["-q", "-o", "addopts=",
    "tests/test_repo_consistency.py::test_current_recovery_recognizes_t113_closure_and_frozen_boundary"]))
'''
result = subprocess.run([sys.executable, '-c', code], cwd=root,
                        capture_output=True, text=True, encoding='utf-8',
                        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
(out / 'red-current-recovery.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
assert result.returncode == 1 and '1 failed' in result.stdout, result.stdout + result.stderr
results.append({'mutation': 'current recovery falsely reopens resolved gap', 'exit_code': 1, 'failed': 1})
print('Expected RED: contradictory current recovery -> 1 failed', flush=True)
(out / 'red-controls.json').write_text(json.dumps(results, indent=2)+'\n', encoding='utf-8')
