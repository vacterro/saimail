"""T-117 red controls.

1. Pre-fix bytes: run tests/test_turn_entry_headers.py in an isolated copy whose
   saimail/workspace.py and saimail_local.py are the exact pre-T-117 files.
2. Mutation: a weakened header loader that validates the marker only must be
   caught by the public-check parity test.

Usage: python .saipen/kitchen/t117_red_control.py <scratch-dir>
"""
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
before = root / ".saipen/evidence/T-117-turn-entry/before"
scratch = Path(sys.argv[1]).resolve()
TEST = "tests/test_turn_entry_headers.py"

MUTANT = '''
import pytest
from saimail import workspace as _ws


def _marker_only(root):
    from pathlib import Path
    root = Path(root)
    path = root / _ws.MARKER_NAME
    if not path.is_file():
        _ws._reject(_ws.WORKSPACE_MISSING, "no marker")
    marker = _ws._read_json(path, code=_ws.INVALID_WORKSPACE, what="marker")
    return _ws.WorkspaceHeaders(
        root=root, seat=marker["seat"], created=marker["created"],
        recipient_public_key=None, sender_kid=marker["sender_kid"],
        recipient_kid=marker["recipient_kid"], custody="raw")


@pytest.fixture(autouse=True)
def _weakened_header_loader(monkeypatch):
    monkeypatch.setattr(_ws, "load_workspace_headers", _marker_only)
'''


def run(where: Path, *extra: str) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "-rA", TEST, *extra], cwd=where, capture_output=True, text=True)
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith(("PASSED", "FAILED"))]
    return proc.returncode, "\n".join(lines + proc.stdout.strip().splitlines()[-1:])


def copy_tree(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "tests").mkdir(parents=True)
    for name in ("sailang", "saimail", "lab"):
        shutil.copytree(root / name, dest / name,
                        ignore=shutil.ignore_patterns("__pycache__", "out", "history"))
    shutil.copy2(root / "conftest.py", dest / "conftest.py")
    shutil.copy2(root / "saimail_local.py", dest / "saimail_local.py")
    shutil.copy2(root / TEST, dest / TEST)


pre = scratch / "prefix"
copy_tree(pre)
shutil.copy2(before / "workspace.py", pre / "saimail/workspace.py")
shutil.copy2(before / "saimail_local.py", pre / "saimail_local.py")
code, report = run(pre)
print("== pre-fix bytes (expect failures) rc=%d\n%s" % (code, report))

mut = scratch / "mutant"
copy_tree(mut)
(mut / "tests/conftest.py").write_text(MUTANT, encoding="utf-8")
code, report = run(mut, "-k", "public_check")
print("== weakened header loader (expect parity failures) rc=%d\n%s" % (code, report))
