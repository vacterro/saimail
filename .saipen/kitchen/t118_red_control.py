"""T-118 red controls for the workshop-policy oracle.

Each case copies the repository (minus heavy trees), breaks one link the oracle
guards, and runs only the policy oracle, which must go red:
- renamed_control: a mapped control is renamed away
- gate_dropped:    the SAIPEN-side gate V6-08 disappears from the roadmap table
- acted_state:     the outbox state set gains ACTED

Usage: python .saipen/kitchen/t118_red_control.py <scratch-dir>
"""
import shutil
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
scratch = Path(sys.argv[1]).resolve()
SKIP = shutil.ignore_patterns(".git", ".saipen", "release", "build", "dist", "__pycache__",
                              "*.mp3", "pics", "bench", "lab", ".pytest_cache", ".ruff_cache")

CASES = {
    "renamed_control": [("tests/test_notify.py",
                         "def test_a_notification_belongs_to_a_real_work(",
                         "def test_renamed_away(")],
    "gate_dropped": [("humbox/FUTURE-GATES-V6.md", "| V6-08 |", "| V6-99 |")],
    "acted_state": [("saimail/outbox.py",
                     "STATES = (PENDING, SEALED, DELIVERED, FAILED)",
                     "ACTED = \"ACTED\"\nSTATES = (PENDING, SEALED, DELIVERED, FAILED, ACTED)")],
}


def run(where: Path):
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "tests/test_repo_consistency.py", "-k", "workshop"],
                          cwd=where, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip().splitlines()[-1]


def copy(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(root, dest, ignore=SKIP)
    shutil.copytree(root / "lab", dest / "lab",
                    ignore=shutil.ignore_patterns("out", "history", "__pycache__"))


where = scratch / "baseline"
copy(where)
print("== unmutated copy: rc=%d %s" % run(where))
for name, edits in CASES.items():
    where = scratch / name
    copy(where)
    for rel, old, new in edits:
        target = where / rel
        text = target.read_bytes().decode("utf-8")
        assert text.count(old) == 1, (name, old)
        target.write_bytes(text.replace(old, new).encode("utf-8"))
    print(f"== {name}: rc=%d %s" % run(where))
