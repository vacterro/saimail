"""Source-level mutant runner for the SRC-108 wave (T-120 onward).

Each mutant rewrites exact snippets of one module inside an isolated copy of the
repository (so child processes run the mutant too), runs one test file and
reports which controls turned red. An unmutated copy runs first as the
known-good control.

Usage: python .saipen/kitchen/wave_red_mutants.py <spec.json> <scratch-dir>
spec.json: {"module": "saimail/x.py", "test": "tests/test_x.py",
            "mutants": {"name": [["old", "new"], ...]}}
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
spec = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
scratch = Path(sys.argv[2]).resolve()


def copy_tree(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "tests").mkdir(parents=True)
    for name in ("sailang", "saimail", "lab"):
        shutil.copytree(root / name, dest / name,
                        ignore=shutil.ignore_patterns("__pycache__", "out", "history"))
    shutil.copy2(root / "conftest.py", dest / "conftest.py")
    shutil.copy2(root / "saimail_local.py", dest / "saimail_local.py")
    shutil.copy2(root / spec["test"], dest / spec["test"])


def run(where: Path):
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "-rA", spec["test"]], cwd=where, capture_output=True, text=True)
    failed = [ln.split(" - ")[0] for ln in proc.stdout.splitlines() if ln.startswith("FAILED")]
    return proc.returncode, failed, proc.stdout.strip().splitlines()[-1]


where = scratch / "baseline"
copy_tree(where)
rc, failed, summary = run(where)
print(f"== unmutated copy: rc={rc} {summary}")
for name, edits in spec["mutants"].items():
    where = scratch / name
    copy_tree(where)
    target = where / spec["module"]
    text = target.read_text(encoding="utf-8")
    for old, new in edits:
        assert text.count(old) == 1, (name, old[:60])
        text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")
    rc, failed, summary = run(where)
    print(f"== mutant {name}: rc={rc} {summary}")
    for line in failed:
        print("  " + line)
