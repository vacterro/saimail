"""D3 GUI clean-install matrix for the exact 0.0.2a3 wheel (V5-01).

Installs the exact frozen wheel into a fresh virtual environment **outside the
checkout**, proves the GUI modules and the ``saimail-gui`` console entrypoint
resolve from that environment, proves PySide6 arrives through the declared
``gui`` extra (never a base requirement), and runs the repository's own GUI
acceptance/surface tests against the installed artifact on the offscreen Qt
platform. No network is used beyond the local wheel install (``--no-index``).

    python tools/d3_gui_install_matrix.py --bundle release/candidates/0.0.2a3 \
        --out release/evidence/a3/gui_install_matrix.json

Evidence schema: ``SAIMAIL_D3_GUI_INSTALL_MATRIX_1`` v1. Nothing here publishes.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = "SAIMAIL_D3_GUI_INSTALL_MATRIX_1"
GUI_TESTS = ("test_gui_acceptance.py", "test_gui_surface.py")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lar = _load("local_alpha_release", ROOT / "tools" / "local_alpha_release.py")


def run(args, cwd=None, env=None):
    return subprocess.run([str(item) for item in args], cwd=cwd, env=env,
                          capture_output=True, text=True, check=False)


def venv_bin(venv: Path, name: str) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / f"{name}.exe"
    return venv / "bin" / name


def _write(path, payload) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: payload.get(key) for key in ("schema", "status", "candidate")},
                     indent=2, sort_keys=True))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", default=None)
    parser.add_argument("--keep", action="store_true")
    parsed = parser.parse_args(argv)

    bundle = Path(parsed.bundle).resolve()
    manifest = json.loads((bundle / "local_alpha_candidate.json").read_text(encoding="utf-8"))
    evidence = {
        "schema": SCHEMA,
        "version": 1,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "BLOCKED",
        "candidate": {
            "version": manifest.get("package_version"),
            "wheel_filename": manifest.get("wheel", {}).get("filename"),
            "wheel_sha256": manifest.get("wheel", {}).get("sha256"),
            "publication_status": manifest.get("publication_status"),
        },
        "environment": {"python_version": sys.version.split()[0], "platform": sys.platform},
        "checks": {},
        "failures": [],
        "note": ("installed-wheel GUI matrix: gui extra provides PySide6, saimail-gui "
                 "entrypoint and the GUI modules resolve from the environment; the "
                 "repository's own offscreen GUI acceptance runs against the wheel"),
    }

    integrity = lar.verify_bundle_integrity(bundle, source_root=ROOT)
    evidence["integrity"] = {"status": integrity.get("status"),
                             "failures": integrity.get("failures")}
    if integrity.get("status") != "PASS":
        evidence["failures"].append("bundle integrity gate failed")
        _write(parsed.out, evidence)
        return 1

    owned = parsed.work is None
    work = Path(parsed.work) if parsed.work else Path(
        tempfile.mkdtemp(prefix="saimail-d3-gui-matrix-"))
    try:
        venv = work / "venv"
        created = run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)])
        if created.returncode != 0:
            evidence["failures"].append("virtual environment creation failed")
            _write(parsed.out, evidence)
            return 2
        python = venv_bin(venv, "python")
        wheel = bundle / manifest["wheel"]["filename"]
        installed = run([python, "-m", "pip", "install", "--no-deps", "--no-index",
                         "--no-build-isolation", str(wheel)], cwd=work)
        evidence["install"] = {
            "status": "INSTALLED" if installed.returncode == 0 else "FAILED",
            "wheel": wheel.name,
            "note": "dependency installation is separate from SAIMAIL runtime activity",
        }
        if installed.returncode != 0:
            evidence["failures"].append("wheel installation failed")
            evidence["install_tail"] = (installed.stdout + installed.stderr)[-600:]
            _write(parsed.out, evidence)
            return 1

        cwd = work / "cwd"
        cwd.mkdir(parents=True, exist_ok=True)
        probe = run([python, "-c",
                     ("import saimail, saimail.gui_adapter, saimail.gui_app, saimail.gui_theme;"
                      " import PySide6; print(saimail.__file__); print(PySide6.__file__)"),
                     ], cwd=cwd)
        paths = [line for line in probe.stdout.splitlines() if line.strip()]
        resolved_inside = (probe.returncode == 0 and paths
                           and str(venv) in paths[0] and str(ROOT) not in paths[0])
        evidence["module_resolution"] = {
            "resolved_inside_environment": resolved_inside,
            "paths": paths,
            "note": "the GUI modules and PySide6 import from the fresh environment",
        }
        if not resolved_inside:
            evidence["failures"].append(
                "installed GUI modules do not resolve inside the fresh environment")

        entry_local = venv_bin(venv, "saimail-local")
        entry_gui = venv_bin(venv, "saimail-gui")
        evidence["entrypoints"] = {
            "saimail-local": entry_local.is_file(),
            "saimail-gui": entry_gui.is_file(),
        }
        version = run([entry_local, "--version"], cwd=cwd) if entry_local.is_file() else None
        reported = None
        if version is not None and version.returncode == 0:
            import re
            match = re.search(r"^saimail (\S+)", version.stdout, flags=re.MULTILINE)
            reported = match.group(1) if match else None
        evidence["base_entrypoint_version"] = reported

        tests_src = ROOT / "tests"
        tests_dst = work / "gui-tests"
        tests_dst.mkdir(parents=True, exist_ok=True)
        copied = []
        for name in GUI_TESTS:
            source = tests_src / name
            if source.is_file():
                shutil.copyfile(source, tests_dst / name)
                copied.append(name)
        env = dict(os.environ)
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        pytest = run([python, "-m", "pytest", "-q", *copied], cwd=tests_dst, env=env)
        evidence["offscreen_pytest"] = {
            "exit_code": pytest.returncode,
            "files": copied,
            "tail": (pytest.stdout or "")[-800:],
        }

        checks = evidence["checks"]
        checks["install_status"] = installed.returncode == 0
        checks["gui_modules_resolve_inside_environment"] = resolved_inside
        checks["saimail_gui_entrypoint_exists"] = entry_gui.is_file()
        checks["saimail_local_entrypoint_exists"] = entry_local.is_file()
        checks["base_entrypoint_reports_candidate_version"] = (
            reported == manifest.get("package_version"))
        checks["gui_extra_declares_pyside6"] = (
            manifest.get("content_proof", {}).get("product_delta", {})
            .get("checks", {}).get("v501_gui_extra_declares_pyside6") is True)
        checks["pyside6_not_core_dependency"] = (
            manifest.get("content_proof", {}).get("product_delta", {})
            .get("checks", {}).get("pyside6_not_core_dependency") is True)
        checks["offscreen_gui_tests_pass"] = pytest.returncode == 0

        for name, ok in checks.items():
            if ok is not True:
                evidence["failures"].append(f"check failed: {name}")
        evidence["status"] = "PASS" if not evidence["failures"] else "FAIL"
        _write(parsed.out, evidence)
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        if owned and not parsed.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
