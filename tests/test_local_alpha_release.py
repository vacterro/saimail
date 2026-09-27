"""V2-04 focused acceptance: candidate bundle, hashing, integrity, verifier, privacy.

Focused areas: release manifest schema, candidate hashing, corrupted-hash red
control, wheel contents, version consistency, installed FG-05/FG-06/V2-01 via
the bounded verifier, verifier output schema, privacy scan and its red control,
and no-checkout-import leakage. Contract: spec/18-LOCAL-ALPHA-v0.md, D-052.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

import saimail_local

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lar = _load("local_alpha_release", TOOLS / "local_alpha_release.py")
privacy = _load("scan_local_alpha_privacy", TOOLS / "scan_local_alpha_privacy.py")


@pytest.fixture(scope="module")
def candidate(tmp_path_factory):
    out = tmp_path_factory.mktemp("local-alpha-candidate")
    manifest = lar.build_candidate(ROOT, out)
    return out, manifest


def test_version_surfaces_agree():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    api_map = json.loads((ROOT / "lab" / "stable_local_api.json").read_text(encoding="utf-8"))
    surfaces = {
        "pyproject": pyproject["project"]["version"],
        "VERSION": VERSION,
        "entrypoint_fallback": saimail_local._VERSION_FALLBACK,
        "stable_api_map": api_map["release"],
    }
    assert len(set(surfaces.values())) == 1, surfaces
    assert surfaces["VERSION"] == VERSION
    assert saimail_local._version() == surfaces["pyproject"], (
        "the installed/editable distribution metadata drifted from the version surfaces"
    )


def test_candidate_manifest_is_bounded_and_exactly_hashed(candidate):
    bundle, manifest = candidate
    assert manifest["schema"] == "LOCAL_ALPHA_CANDIDATE_1"
    assert manifest["version"] == 1
    assert manifest["package_name"] == "saimail"
    assert manifest["package_version"] == VERSION
    assert manifest["publication_status"] == "NOT_PUBLISHED"
    assert manifest["zero_runtime_network_expected"] is True
    assert manifest["zero_model_calls_expected"] is True
    assert manifest["python_scope"] == ">=3.11"
    assert manifest["result_schemas"] == {
        "fg05": "LOCAL_SCENARIO_RESULT_1 v1",
        "fg06": "FG06_UTILITY_RESULT_1 v1",
        "v201_command": "LOCAL_WORKSPACE_COMMAND_1 v1",
        "v201_acceptance": "LOCAL_WORKSPACE_RESULT_1 v1",
    }
    wheel = bundle / manifest["wheel"]["filename"]
    assert wheel.is_file()
    assert manifest["wheel"]["sha256"] == lar.sha256_file(wheel)
    assert manifest["wheel"]["size_bytes"] == wheel.stat().st_size
    members = lar.wheel_members(wheel)
    assert manifest["wheel"]["member_count"] == len(members)
    assert manifest["wheel"]["content_digest_sha256"] == lar.wheel_content_digest(members)
    assert (bundle / "local_alpha_candidate.json").is_file()
    assert (bundle / lar.VERIFIER_NAME).is_file()
    assert (bundle / "SHA256SUMS.txt").is_file()
    assert (bundle / "README-LOCAL-ALPHA.md").is_file()
    assert "PRIVATE KEY" not in json.dumps(manifest)
    assert "private_key" not in json.dumps(manifest)


def test_candidate_manifest_carries_post_v301_custody_truth(candidate):
    _bundle, manifest = candidate
    proof = manifest["content_proof"]
    assert proof["schema"] == lar.CONTENT_PROOF_IDENTITY
    assert proof["status"] == "PASS", proof["failures"]
    assert all(proof["checks"].values()), proof["checks"]
    custody_truth = manifest["custody"]
    assert custody_truth["default"] == "raw"
    assert custody_truth["os_store_selection"].startswith("explicit opt-in")
    assert "credentials extra" in custody_truth["os_store_requires"]
    assert custody_truth["protects"] == "workspace-directory-copy exposure"
    assert "malware running as the same OS user" in custody_truth["does_not_protect"]
    assert "admin/kernel compromise" in custody_truth["does_not_protect"]
    assert "hardware custody" in custody_truth["not_provided"]
    assert "Windows only" in custody_truth["os_store_platform_evidence"]
    assert custody_truth["silent_fallback"].startswith("never")
    manifest_text = json.dumps(manifest)
    assert "no OS credential vault" not in manifest_text
    assert "no OS vault" not in manifest_text
    historical = manifest["historical_candidate_a1"]
    assert historical["sha256"] == lar.HISTORICAL_A1["sha256"]
    assert "never inherited" in historical["note"]


def test_bundle_integrity_gate_and_red_controls(candidate, tmp_path):
    bundle, manifest = candidate
    report = lar.verify_bundle_integrity(bundle)
    assert report["status"] == "PASS", report
    assert report["wheel_sha256"] == manifest["wheel"]["sha256"]

    corrupt_wheel = tmp_path / "corrupt-wheel"
    shutil.copytree(bundle, corrupt_wheel)
    wheel = next(corrupt_wheel.glob("*.whl"))
    data = bytearray(wheel.read_bytes())
    data[-1] ^= 0xFF
    wheel.write_bytes(bytes(data))
    report = lar.verify_bundle_integrity(corrupt_wheel)
    assert report["status"] == "FAIL"
    assert any("wheel sha256" in failure for failure in report["failures"])

    corrupt_hash = tmp_path / "corrupt-hash"
    shutil.copytree(bundle, corrupt_hash)
    manifest_path = corrupt_hash / "local_alpha_candidate.json"
    tampered = json.loads(manifest_path.read_text(encoding="utf-8"))
    tampered["wheel"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    report = lar.verify_bundle_integrity(corrupt_hash)
    assert report["status"] == "FAIL"

    corrupt_checksum = tmp_path / "corrupt-checksum"
    shutil.copytree(bundle, corrupt_checksum)
    (corrupt_checksum / "README-LOCAL-ALPHA.md").write_text(
        "tampered\n", encoding="utf-8")
    report = lar.verify_bundle_integrity(corrupt_checksum)
    assert report["status"] == "FAIL"
    assert any("checksum" in failure for failure in report["failures"])


def test_wheel_contains_the_release_surface(candidate):
    bundle, manifest = candidate
    wheel = bundle / manifest["wheel"]["filename"]
    names = set(zipfile.ZipFile(wheel).namelist())
    for required in ("saimail_local.py", "lab/__init__.py", "lab/local_scenario.py",
                     "lab/utility_friction.py", "lab/stable_local_api.json",
                     "saimail/workspace.py", "saimail/custody.py"):
        assert required in names, f"wheel is missing {required}"
    assert any(name.endswith("entry_points.txt") for name in names)
    assert not any(name.startswith("lab/out/") for name in names)
    assert not any(name.startswith("lab/analysis/") for name in names)
    assert not any(name.startswith("lab/history/") for name in names)
    assert lar.wheel_metadata_version(wheel) == manifest["package_version"]


def test_privacy_scan_and_red_control(candidate, tmp_path):
    bundle, _manifest = candidate
    report = privacy.scan_tree(bundle)
    assert report["status"] == "PASS", report["findings"]
    assert report["files_scanned"] >= 5

    planted = tmp_path / "planted"
    shutil.copytree(bundle, planted)
    (planted / "planted-note.txt").write_text(
        f"{privacy.PLANTED_MARKER}\n", encoding="utf-8")
    report = privacy.scan_tree(planted)
    assert report["status"] == "FAIL"
    assert any(finding["rule"] == "planted_marker" for finding in report["findings"])


def test_verifier_source_is_standalone():
    import ast

    source = (TOOLS / "verify_local_alpha.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] not in ("saimail", "lab", "sailang"), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in ("saimail", "lab", "sailang"), \
                node.module


def test_verifier_proves_the_installed_candidate_outside_the_checkout(candidate, tmp_path):
    bundle, manifest = candidate
    out = tmp_path / "verification"
    completed = subprocess.run(
        [sys.executable, str(bundle / lar.VERIFIER_NAME),
         "--bundle", str(bundle), "--out", str(out), "--offline"],
        capture_output=True, text=True, check=False, timeout=900)
    assert completed.returncode == 0, completed.stdout[-2000:] + completed.stderr[-2000:]
    result = json.loads((out / "local_alpha_verification.json").read_text(encoding="utf-8"))
    assert result["schema"] == "LOCAL_ALPHA_VERIFICATION_1"
    assert result["version"] == 1
    assert result["status"] == "PASS", result["failures"]
    assert result["candidate"]["version"] == manifest["package_version"]
    assert result["candidate"]["wheel_sha256"] == manifest["wheel"]["sha256"]
    assert result["candidate"]["publication_status"] == "NOT_PUBLISHED"
    assert result["integrity"]["status"] == "PASS"
    assert result["custody_content_proof"]["status"] == "PASS"
    assert result["custody"]["default"] == "raw"
    assert result["scope"]["base_candidate_verification"] == "TESTED_BY_THIS_VERIFIER"
    assert result["scope"]["os_store_platform_verification"].startswith("NOT_TESTED_HERE")
    assert result["install"]["status"] == "INSTALLED"
    assert result["module_resolution"]["resolved_inside_environment"] is True
    for path in result["module_resolution"]["paths"]:
        assert str(ROOT) not in path, f"module resolved from the checkout: {path}"
    assert result["saimail_local_version"]["status"] == "PASS"
    assert result["api_map"]["release_matches"] is True
    assert result["fg05"]["schema"] == "LOCAL_SCENARIO_RESULT_1"
    assert result["fg05"]["status"] == "PASS"
    assert result["fg06"]["schema"] == "FG06_UTILITY_RESULT_1"
    assert result["v201_acceptance"]["schema"] == "LOCAL_WORKSPACE_RESULT_1"
    assert result["v201_acceptance"]["status"] == "PASS"
    assert result["v201_direct_command"]["schema"] == "LOCAL_WORKSPACE_COMMAND_1"
    assert result["v201_direct_command"]["status"] == "CREATED"
    assert result["v201_direct_command"]["custody_mode"] == "raw"
    assert result["v201_direct_command"]["first_run_notice"] is True
    assert result["fg06"]["outcome_category"] == "UTILITY_CONDITIONAL"
    assert result["fg06"]["verdict_matches"] is True
    assert result["runtime_counters"]["network_attempts"] == 0
    assert result["runtime_counters"]["model_calls"] == 0
    assert result["runtime_counters"]["provider_calls"] == 0
    assert result["privacy"]["status"] == "PASS"
    assert result["limitations"]["identity"] == lar.LIMITATIONS_IDENTITY
    assert result["limitations"]["utility_verdict"] == "UTILITY_CONDITIONAL"
    assert result["environment"]["platform"] == sys.platform
