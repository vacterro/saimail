"""FG-06 acceptance: minimal entrypoint, stable API map and failure map.

Focused areas G, J, K, L, M. Packaging content (H, I) is proven separately in
``tests/test_clean_install.py``.
"""

from __future__ import annotations

import importlib
import json
import socket
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

import saimail_local

ROOT = Path(__file__).resolve().parent.parent
API_MAP = ROOT / "lab" / "stable_local_api.json"


def _run(args, cwd=ROOT):
    return subprocess.run([sys.executable, "-m", "saimail_local", *args],
                          cwd=cwd, capture_output=True, text=True, check=False)


# ------------------------------------------------------------------ G. CLI


def test_version_flag_is_externally_discoverable():
    completed = _run(["--version"])
    assert completed.returncode == 0
    assert "saimail" in completed.stdout
    assert "FG05-LOCAL-SCENARIO" in completed.stdout
    assert "FG06_UTILITY_RESULT_1" in completed.stdout


def test_utility_mode_writes_machine_readable_result(tmp_path):
    completed = _run(["--utility", "--out", str(tmp_path)])
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads((tmp_path / "fg06_utility_result.json").read_text(encoding="utf-8"))
    assert result["schema"] == "FG06_UTILITY_RESULT_1"
    assert result["outcome_category"] in {
        "UTILITY_POSITIVE", "UTILITY_CONDITIONAL", "UTILITY_NEUTRAL", "UTILITY_NEGATIVE"}
    assert result["zero_network_model"]["network_attempts"] == 0


def test_json_stdout_is_the_result(tmp_path):
    completed = _run(["--utility", "--json"])
    assert completed.returncode == 0
    parsed = json.loads(completed.stdout)
    assert parsed["schema"] == "FG06_UTILITY_RESULT_1"


def test_api_map_flag_prints_a_shipped_path():
    completed = _run(["--api-map"])
    assert completed.returncode == 0
    path = Path(completed.stdout.strip())
    assert path.is_file() and path.name == "stable_local_api.json"


# ------------------------------------------------------------ J. API map


def test_every_documented_api_resolves():
    mapping = json.loads(API_MAP.read_text(encoding="utf-8"))
    assert mapping["schema"] == "SAIMAIL_STABLE_LOCAL_API_1"
    seen = set()
    for entry in mapping["apis"]:
        assert entry["stability"] in ("stable", "lab-only")
        module = importlib.import_module(entry["module"])
        assert hasattr(module, entry["symbol"]), f"{entry['module']}.{entry['symbol']} missing"
        seen.add((entry["module"], entry["symbol"]))
    assert len(seen) == len(mapping["apis"])
    assert ("saimail_local", "main") in seen
    assert ("saimail.envelope", "seal") in seen
    assert ("saimail.postoffice", "PostOffice") in seen
    assert ("saimail.human_attention", "AttentionQueue") in seen


# -------------------------------------------------------- K. failure map


def test_every_documented_failure_code_is_backed():
    mapping = json.loads(API_MAP.read_text(encoding="utf-8"))
    codes = mapping["failure_codes"]
    assert codes
    for entry in codes:
        source = (ROOT / entry["where"]).read_text(encoding="utf-8")
        assert entry["code"] in source, (
            f"{entry['code']} documented as {entry['group']} but absent from {entry['where']}")
        for field in ("retry_safe", "operator_action", "authority_intact"):
            assert isinstance(entry[field], bool)


# ------------------------------------------------------------- L. privacy


def test_entrypoint_result_has_no_private_marker(tmp_path):
    from lab import local_scenario as ls

    completed = _run(["--demo", "--out", str(tmp_path)])
    assert completed.returncode == 0
    payload = (tmp_path / "local_scenario_result.json").read_text(encoding="utf-8")
    assert ls.PRIVATE_MARKER not in payload


# ------------------------------------------------------- M. zero network


def test_entrypoint_tripwire_blocks_connections():
    probe = {"blocked": 0}
    with pytest.raises(AssertionError), saimail_local.no_network(probe):
        socket.create_connection(("127.0.0.1", 9))
    assert probe["blocked"] == 1


# -------------------------------------------------- packaging declaration


def test_pyproject_declares_the_entrypoint_and_packages():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["scripts"]["saimail-local"] == "saimail_local:main"
    assert "lab" in data["tool"]["setuptools"]["packages"]
    assert "saimail_local" in data["tool"]["setuptools"]["py-modules"]
    assert "stable_local_api.json" in data["tool"]["setuptools"]["package-data"]["lab"]


# ------------------------------------------- V5-01 GUI dependency boundary


def test_gui_entrypoint_and_optional_dependency_boundary():
    """V5-01: the desktop client is an optional extra, never a core dependency."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert project["dependencies"] == [], (
        "PySide6 must never enter the core dependency list")
    assert project["scripts"]["saimail-gui"] == "saimail.gui_app:main"
    assert project["scripts"]["saimail-local"] == "saimail_local:main"
    gui = project["optional-dependencies"]["gui"]
    assert any(dep.startswith("PySide6") for dep in gui)
    assert any("<7" in dep for dep in gui), "the Qt major range must be bounded"
    for name, deps in project["optional-dependencies"].items():
        if name == "gui":
            continue
        assert not any("PySide6" in dep for dep in deps), (
            f"the {name!r} extra must not pull Qt")


def test_core_imports_do_not_touch_qt():
    """The core package must import and serve the CLI with no Qt available."""
    import ast as _ast

    for path in sorted((ROOT / "saimail").glob("*.py")):
        if path.name in ("gui_app.py",):
            continue
        tree = _ast.parse(path.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("PySide6"), path
            elif isinstance(node, _ast.ImportFrom):
                assert not (node.module or "").startswith("PySide6"), path
