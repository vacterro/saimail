"""Capture requested commands without altering their pytest selection."""
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[2]
out = root / '.saipen/evidence/T-114-truth'
focused = [
    ('reread', ['tests/test_reread_continuation.py']),
    ('gui-surface', ['tests/test_gui_surface.py']),
    ('gui-acceptance', ['tests/test_gui_acceptance.py']),
    ('repo-consistency', ['tests/test_repo_consistency.py']),
    ('local', ['tests/test_local_workspace.py', 'tests/test_local_entrypoint.py']),
]
selected = [('full', [])] if '--full' in sys.argv else focused
for label, paths in selected:
    command = [sys.executable, '-m', 'pytest', '-q', *paths]
    xml = out / f'{label}.xml'
    env = {**os.environ, 'PYTHONIOENCODING': 'utf-8',
           'PYTEST_ADDOPTS': f'{os.environ.get("PYTEST_ADDOPTS", "")} --junitxml={xml.as_posix()}'}
    print('RUN', 'python -m pytest -q', ' '.join(paths), flush=True)
    with (out / f'{label}.txt').open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT)
    counts = {key: 0 for key in ('tests', 'failures', 'errors', 'skipped')}
    assert xml.is_file(), f'Missing test report: {xml}'
    for suite in ET.parse(xml).getroot().iter('testsuite'):
        for key in counts:
            counts[key] += int(suite.attrib.get(key, 0))
    report = {'command': ['python', '-m', 'pytest', '-q', *paths],
              'exit_code': result.returncode, **counts}
    report['passed'] = counts['tests'] - counts['failures'] - counts['errors'] - counts['skipped']
    (out / f'{label}-result.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report), flush=True)
    if result.returncode:
        print((out / f'{label}.txt').read_text(encoding='utf-8')[-8000:], flush=True)
        raise SystemExit(result.returncode)
