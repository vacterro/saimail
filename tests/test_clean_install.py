"""FG-06 acceptance H/I: clean isolated install and package content.

Builds the distribution wheel, installs it into a fresh virtual environment,
and runs the documented entrypoint from a working directory that is not the
checkout, proving the supported local path does not depend on repository-relative
imports. No network is used: the wheel is installed ``--no-deps`` into a
``--system-site-packages`` venv that already carries the declared extras.

This test is heavier than the rest of the suite; it is skipped only when the
build/venv tooling is genuinely unavailable, which is recorded, never faked.
"""

from __future__ import annotations

import json
import subprocess
import sys
import venv
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

pytest.importorskip("build", reason="the 'build' package is required to build the wheel")


def _bin(venv_dir: Path, name: str) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / f"{name}.exe"
    return venv_dir / "bin" / name


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    outdir = tmp_path_factory.mktemp("wheel")
    completed = _run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation",
         "--outdir", str(outdir), str(ROOT)], cwd=tmp_path_factory.mktemp("build-cwd"))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    wheels = list(outdir.glob("*.whl"))
    assert len(wheels) == 1
    return wheels[0]


def test_wheel_contains_the_local_surface(wheel: Path):
    names = set(zipfile.ZipFile(wheel).namelist())
    for required in ("saimail_local.py", "lab/__init__.py", "lab/local_scenario.py",
                     "lab/utility_friction.py", "lab/stable_local_api.json",
                     "saimail/workspace.py", "saimail_host.py", "saimail_project.py",
                     "saimail/letters.py", "saimail/correspondence.py", "saimail/keyvault.py",
                     "saimail/host_contract.py"):
        assert required in names, f"wheel is missing {required}"
    assert any(name.endswith("entry_points.txt") for name in names)
    # History/out/analysis artifacts are not package data and must not ship.
    assert not any(name.startswith("lab/out/") for name in names)
    assert not any(name.startswith("lab/analysis/") for name in names)
    assert not any(name.startswith("lab/history/") for name in names)


def test_clean_install_entrypoint_runs_outside_the_checkout(wheel: Path, tmp_path: Path):
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True, system_site_packages=True)
    python = _bin(env_dir, "python")
    install = _run([str(python), "-m", "pip", "install", "--no-deps",
                    "--no-build-isolation", str(wheel)], cwd=tmp_path)
    assert install.returncode == 0, install.stdout + install.stderr

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    probe = ("import saimail, lab, saimail_local; "
             "print(saimail.__file__); print(lab.__file__); print(saimail_local.__file__)")
    resolved = _run([str(python), "-c", probe], cwd=cwd)
    assert resolved.returncode == 0, resolved.stdout + resolved.stderr
    for line in resolved.stdout.splitlines():
        assert str(env_dir) in line, f"module resolved outside the install: {line}"

    version = _run([str(_bin(env_dir, "saimail-local")), "--version"], cwd=cwd)
    assert version.returncode == 0
    assert f"saimail {VERSION}" in version.stdout
    assert "FG06_UTILITY_RESULT_1" in version.stdout

    out = cwd / "out"
    utility = _run([str(_bin(env_dir, "saimail-local")), "--utility", "--out", str(out)], cwd=cwd)
    assert utility.returncode == 0, utility.stdout + utility.stderr
    result = json.loads((out / "fg06_utility_result.json").read_text(encoding="utf-8"))
    assert result["schema"] == "FG06_UTILITY_RESULT_1"
    assert result["zero_network_model"]["network_attempts"] == 0
    assert result["entrypoint"]["version"] == VERSION

    demo = _run([str(_bin(env_dir, "saimail-local")), "--demo", "--out", str(out)], cwd=cwd)
    assert demo.returncode == 0, demo.stdout + demo.stderr
    scenario = json.loads((out / "local_scenario_result.json").read_text(encoding="utf-8"))
    assert scenario["status"] == "PASS"


def test_clean_install_runs_the_v201_workspace_workflow(wheel: Path, tmp_path: Path):
    """V2-01 area N: the persistent workspace workflow lives in the built wheel."""
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True, system_site_packages=True)
    python = _bin(env_dir, "python")
    install = _run([str(python), "-m", "pip", "install", "--no-deps",
                    "--no-build-isolation", str(wheel)], cwd=tmp_path)
    assert install.returncode == 0, install.stdout + install.stderr

    cwd = tmp_path / "cwd"
    cwd.mkdir()
    script = str(_bin(env_dir, "saimail-local"))

    acceptance = _run([script, "acceptance", "--root", str(cwd / "acceptance"), "--json"],
                      cwd=cwd)
    assert acceptance.returncode == 0, acceptance.stdout + acceptance.stderr
    result = json.loads(acceptance.stdout)
    assert result["schema"] == "LOCAL_WORKSPACE_RESULT_1"
    assert result["status"] == "PASS"
    assert result["duplicate"]["status"] == "DUPLICATE"
    assert result["zero_network_model"]["network_attempts"] == 0

    initialized = _run([script, "init", "--workspace", str(cwd / "ws"), "--seat",
                        "SAIMAIL-A", "--json"], cwd=cwd)
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    assert json.loads(initialized.stdout)["status"] == "CREATED"
    listing = _run([script, "inbox", "--workspace", str(cwd / "ws"), "--json"], cwd=cwd)
    assert listing.returncode == 0
    assert json.loads(listing.stdout)["schema"] == "LOCAL_WORKSPACE_COMMAND_1"


def test_base_install_keeps_the_core_intact_and_gui_exits_cleanly(
        wheel: Path, tmp_path: Path):
    """V5-01 area: the base install ships no Qt requirement and stays usable.

    The venv follows the suite's existing ``--no-deps`` +
    ``--system-site-packages`` convention (the base package deliberately does not
    declare ``cryptography``; it arrives through the documented extras). Qt's
    absence is simulated deterministically with a ``PySide6`` shadow package
    whose import raises, which is the exact failure a machine without the extra
    produces -- so the GUI entrypoint's bounded error path is really exercised.
    """
    env_dir = tmp_path / "venv-base"
    venv.create(env_dir, with_pip=True, system_site_packages=True)
    python = _bin(env_dir, "python")
    install = _run([str(python), "-m", "pip", "install", "--no-deps",
                    "--no-build-isolation", str(wheel)], cwd=tmp_path)
    assert install.returncode == 0, install.stdout + install.stderr

    cwd = tmp_path / "cwd-base"
    cwd.mkdir()
    assert _bin(env_dir, "saimail-local").is_file(), "core entrypoint missing"
    assert _bin(env_dir, "saimail-gui").is_file(), "gui entrypoint missing from the wheel"

    version = _run([str(_bin(env_dir, "saimail-local")), "--version"], cwd=cwd)
    assert version.returncode == 0, version.stdout + version.stderr
    assert f"saimail {VERSION}" in version.stdout

    # The adapter and the theme are Qt-free by construction.
    probe = ("import saimail.gui_adapter as a, saimail.gui_theme as t; "
             "t.assert_canonical(); a.GuiAdapter(); print('adapter ok')")
    completed = _run([str(python), "-c", probe], cwd=cwd)
    assert completed.returncode == 0, completed.stdout + completed.stderr

    # A shadow PySide6 that cannot import: the GUI entrypoint must exit with one
    # actionable line and no traceback.
    shadow = tmp_path / "no-qt"
    (shadow / "PySide6").mkdir(parents=True)
    (shadow / "PySide6" / "__init__.py").write_text(
        "raise ImportError(\"No module named 'PySide6'\")\n", encoding="utf-8")
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(shadow)
    gui = subprocess.run([str(_bin(env_dir, "saimail-gui"))], cwd=cwd, env=env,
                         capture_output=True, text=True, check=False)
    assert gui.returncode not in (0,), gui.stdout + gui.stderr
    assert "Traceback" not in gui.stderr, gui.stderr
    assert 'pip install "saimail[gui]"' in gui.stderr
    assert "saimail-local" in gui.stderr


def test_gui_extra_declares_qt_and_the_adapter_imports_without_it(wheel: Path,
                                                                  tmp_path: Path):
    """The GUI extra must actually carry Qt, and the wheel must ship the modules."""
    names = set(zipfile.ZipFile(wheel).namelist())
    for required in ("saimail/gui_app.py", "saimail/gui_adapter.py",
                     "saimail/gui_theme.py"):
        assert required in names, f"wheel is missing {required}"
    metadata = next(name for name in names if name.endswith("METADATA"))
    text = zipfile.ZipFile(wheel).read(metadata).decode("utf-8")
    requires = [line for line in text.splitlines()
                if line.startswith("Requires-Dist:")]
    assert any("PySide6" in line and 'extra == "gui"' in line for line in requires), (
        f"the gui extra does not declare PySide6: {requires}")
    core = [line for line in requires if "extra ==" not in line]
    assert not any("PySide6" in line for line in core), (
        f"PySide6 leaked into the base requirements: {core}")
