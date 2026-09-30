"""Run the pinned oracle on the actual original files, including child Python."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[3]
    evidence = Path(__file__).resolve().parent
    name = sys.argv[1] if len(sys.argv) == 2 else "original-bound.xml"
    if Path(name).name != name or not name.endswith(".xml"):
        raise ValueError("output must be one XML basename")
    output = evidence / name
    if output.exists():
        raise FileExistsError("retained original-subject output already exists")
    with tempfile.TemporaryDirectory(prefix="saimail-T148-original-") as d:
        staged = Path(d)
        for package in ("saimail", "sailang", "lab"):
            shutil.copytree(root / package, staged / package,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "out"))
        for name in ("saimail_local.py", "saimail_host.py", "saimail_project.py", "pyproject.toml"):
            shutil.copyfile(root / name, staged / name)
        for name in ("workspace.py", "postoffice.py"):
            shutil.copyfile(evidence / "before" / name, staged / "saimail" / name)
        (staged / "tests").mkdir()
        test = "tests/test_recipient_registration_concurrency.py"
        shutil.copyfile(root / test, staged / test)
        env = os.environ.copy()
        env["PYTHONPATH"] = str(staged)
        result = subprocess.run([sys.executable, "-m", "pytest", "-q", test,
                                 "--tb=no", "--junitxml=" + str(output)],
                                cwd=staged, env=env, check=False)
        return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
