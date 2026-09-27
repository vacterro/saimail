"""T-107 focused acceptance: the a3 external proof acceptance path.

Contract: the a3 acceptor rejects a1/a2 proofs; it validates a genuine
separate-environment LOCAL_ALPHA_VERIFICATION_1 proof against the exact frozen
0.0.2a3 wheel only. Never fabricates acceptance; production evidence only
after a genuine external proof is later supplied.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
A3_EVIDENCE = ROOT / "release" / "evidence" / "a3"
A3_BUNDLE = ROOT / "release" / "candidates" / "0.0.2a3"
A3_WHEEL_SHA256 = (
    "6427feab24c310184e7fd3ec4bb33dc3f5b1581b00128e2ec08d456fa5aa10cc")
A3_VERSION = "0.0.2a3"

A1_SHA256 = "ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a"
A2_SHA256 = "d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load("accept_d3_external_proof", TOOLS / "accept_d3_external_proof.py")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _build_valid_proof() -> dict:
    return {
        "schema": "LOCAL_ALPHA_VERIFICATION_1",
        "version": 1,
        "status": "PASS",
        "failures": [],
        "candidate": {
            "version": A3_VERSION,
            "wheel_filename": "saimail-0.0.2a3-py3-none-any.whl",
            "wheel_sha256": A3_WHEEL_SHA256,
            "publication_status": "NOT_PUBLISHED",
        },
        "install": {"status": "INSTALLED", "wheel": "saimail-0.0.2a3-py3-none-any.whl"},
        "module_resolution": {
            "resolved_inside_environment": True,
            "paths": [r"C:\Temp\saimail-verify\venv\Lib\site-packages\saimail\__init__.py"],
        },
        "saimail_local_version": {
            "status": "PASS", "expected": A3_VERSION, "reported": A3_VERSION,
        },
        "api_map": {
            "schema": "SAIMAIL_STABLE_LOCAL_API_1",
            "path_exists": True,
            "release": A3_VERSION,
            "release_matches": True,
        },
        "fg05": {"schema": "LOCAL_SCENARIO_RESULT_1", "status": "PASS",
                 "network_attempts": 0},
        "fg06": {"schema": "FG06_UTILITY_RESULT_1", "outcome_category": "UTILITY_CONDITIONAL",
                 "expected_verdict": "UTILITY_CONDITIONAL",
                 "verdict_matches": True, "network_attempts": 0},
        "v201_acceptance": {"schema": "LOCAL_WORKSPACE_RESULT_1", "status": "PASS",
                            "network_attempts": 0},
        "v201_direct_command": {"schema": "LOCAL_WORKSPACE_COMMAND_1", "status": "CREATED",
                                "custody_mode": "raw", "first_run_notice": True,
                                "network_attempts": 0},
        "p1_v401": {"status": "PASS", "checks": {}},
        "privacy": {"status": "PASS", "private_key_material_found": False,
                    "findings": []},
        "runtime_counters": {
            "network_attempts": 0, "model_calls": 0, "provider_calls": 0,
        },
        "environment": {
            "platform": "win32", "python_version": "3.11.9",
            "verifier_version": 1,
        },
        "integrity": {
            "status": "PASS", "failures": [],
            "candidate_version": A3_VERSION,
            "wheel_sha256": A3_WHEEL_SHA256,
        },
        "custody_content_proof": {"status": "PASS"},
        "limitations": {"acknowledged": True, "utility_verdict": "UTILITY_CONDITIONAL"},
    }


def test_acceptor_accepts_windows_proof_without_unemitted_publication_field(tmp_path):
    proof_path = tmp_path / "windows-proof.json"
    proof_path.write_text(json.dumps(_build_valid_proof()), encoding="utf-8")

    record = checker.verify(proof_path)

    assert record["status"] == "PASS", record["failures"]
    assert record["candidate_sha256"] == A3_WHEEL_SHA256
    assert record["proof_provenance"] == "OPERATOR_SUPPLIED_UNVERIFIED"
    assert checker.ACCEPTANCE_REQUIRED_CHECKS <= record["checks"].keys()
    assert all(record["checks"][key] is True
               for key in checker.ACCEPTANCE_REQUIRED_CHECKS)


def test_acceptor_accepts_linux_native_paths(tmp_path):
    proof = _build_valid_proof()
    proof["environment"]["platform"] = "linux"
    proof["module_resolution"]["paths"] = [
        "/tmp/saimail-verify/venv/lib/python/site-packages/saimail/__init__.py"]
    proof_path = tmp_path / "linux-proof.json"
    proof_path.write_text(json.dumps(proof), encoding="utf-8")

    assert checker.verify(proof_path)["status"] == "PASS"


@pytest.mark.parametrize("path, value", [
    (("schema",), "LOCAL_ALPHA_VERIFICATION_2"),
    (("version",), 2),
    (("candidate", "version"), "0.0.2a2"),
    (("candidate", "wheel_filename"), "saimail-0.0.2a2-py3-none-any.whl"),
    (("candidate", "wheel_sha256"), A2_SHA256),
    (("integrity", "wheel_sha256"), A2_SHA256),
    (("saimail_local_version", "reported"), "0.0.2a2"),
    (("module_resolution", "resolved_inside_environment"), False),
    (("candidate", "publication_status"), "PUBLISHED"),
])
def test_acceptor_rejects_verifier_contract_identity_or_result_mismatch(
        tmp_path, path, value):
    proof = _build_valid_proof()
    target = proof
    for segment in path[:-1]:
        target = target[segment]
    target[path[-1]] = value
    proof_path = tmp_path / "invalid-proof.json"
    proof_path.write_text(json.dumps(proof), encoding="utf-8")

    record = checker.verify(proof_path)

    assert record["status"] == "FAIL"
    assert record["failures"]


def test_acceptor_rejects_platform_path_mismatch_and_publication_conflict(tmp_path):
    proof = _build_valid_proof()
    proof["module_resolution"]["paths"] = ["/tmp/saimail/__init__.py"]
    proof["publication"] = "PUBLISHED"
    proof_path = tmp_path / "bad-proof.json"
    proof_path.write_text(json.dumps(proof), encoding="utf-8")

    record = checker.verify(proof_path)

    assert record["status"] == "FAIL"
    assert "MODULE_RESOLUTION_PATHS_INVALID" in record["failures"]
    assert "PUBLICATION_IDENTITY_MISMATCH" in record["failures"]


def test_acceptor_rejects_a1_proof():
    a1_proof = A1_SHA256
    a1_proof_text = json.dumps({
        "schema": "LOCAL_ALPHA_VERIFICATION_1",
        "version": 1,
        "status": "PASS",
        "failures": [],
        "candidate": {"version": "0.0.2a1", "wheel_filename": "saimail-0.0.2a1-py3-none-any.whl",
                      "wheel_sha256": a1_proof, "publication_status": "NOT_PUBLISHED"},
        "install": {"status": "INSTALLED"},
        "saimail_local_version": {"status": "PASS", "expected": "0.0.2a1", "reported": "0.0.2a1"},
        "p1_v401": {"status": "PASS", "checks": {}},
        "fg05": {"schema": "LOCAL_SCENARIO_RESULT_1", "status": "PASS", "network_attempts": 0},
        "fg06": {"schema": "FG06_UTILITY_RESULT_1", "outcome_category": "UTILITY_CONDITIONAL",
                 "verdict_matches": True, "network_attempts": 0},
        "v201_acceptance": {"schema": "LOCAL_WORKSPACE_RESULT_1", "status": "PASS",
                            "network_attempts": 0},
        "v201_direct_command": {"schema": "LOCAL_WORKSPACE_COMMAND_1", "status": "CREATED",
                                "custody_mode": "raw", "first_run_notice": True,
                                "network_attempts": 0},
        "privacy": {"status": "PASS", "private_key_material_found": False, "findings": []},
        "runtime_counters": {"network_attempts": 0, "model_calls": 0, "provider_calls": 0},
        "environment": {"platform": "linux", "verifier_version": 1},
        "integrity": {"status": "PASS", "failures": [], "candidate_version": "0.0.2a1",
                      "wheel_sha256": a1_proof},
        "module_resolution": {"resolved_inside_environment": True, "paths": []},
        "custody_content_proof": {"status": "PASS"},
        "limitations": {"acknowledged": True, "utility_verdict": "UTILITY_CONDITIONAL"},
        "publication": "NONE",
    })
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(a1_proof_text)
        temp_path = Path(f.name)
    try:
        record = checker.verify(temp_path)
        assert record["status"] == "FAIL"
        assert any("a1" in f.lower() or "a1" in str(f) for f in record["failures"])
    finally:
        temp_path.unlink()


def test_acceptor_rejects_a2_proof():
    a2_proof = A2_SHA256
    a2_proof_text = json.dumps({
        "schema": "LOCAL_ALPHA_VERIFICATION_1",
        "version": 1,
        "status": "PASS",
        "failures": [],
        "candidate": {"version": "0.0.2a2", "wheel_filename": "saimail-0.0.2a2-py3-none-any.whl",
                      "wheel_sha256": a2_proof, "publication_status": "NOT_PUBLISHED"},
        "install": {"status": "INSTALLED"},
        "saimail_local_version": {"status": "PASS", "expected": "0.0.2a2", "reported": "0.0.2a2"},
        "p1_v401": {"status": "PASS", "checks": {}},
        "fg05": {"schema": "LOCAL_SCENARIO_RESULT_1", "status": "PASS", "network_attempts": 0},
        "fg06": {"schema": "FG06_UTILITY_RESULT_1", "outcome_category": "UTILITY_CONDITIONAL",
                 "verdict_matches": True, "network_attempts": 0},
        "v201_acceptance": {"schema": "LOCAL_WORKSPACE_RESULT_1", "status": "PASS",
                            "network_attempts": 0},
        "v201_direct_command": {"schema": "LOCAL_WORKSPACE_COMMAND_1", "status": "CREATED",
                                "custody_mode": "raw", "first_run_notice": True,
                                "network_attempts": 0},
        "privacy": {"status": "PASS", "private_key_material_found": False, "findings": []},
        "runtime_counters": {"network_attempts": 0, "model_calls": 0, "provider_calls": 0},
        "environment": {"platform": "linux", "verifier_version": 1},
        "integrity": {"status": "PASS", "failures": [], "candidate_version": "0.0.2a2",
                      "wheel_sha256": a2_proof},
        "module_resolution": {"resolved_inside_environment": True, "paths": []},
        "custody_content_proof": {"status": "PASS"},
        "limitations": {"acknowledged": True, "utility_verdict": "UTILITY_CONDITIONAL"},
        "publication": "NONE",
    })
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        f.write(a2_proof_text)
        temp_path = Path(f.name)
    try:
        record = checker.verify(temp_path)
        assert record["status"] == "FAIL"
        assert any("a2" in f.lower() or "a2" in str(f) for f in record["failures"])
    finally:
        temp_path.unlink()


def test_acceptor_rejects_non_pass_status():
    import tempfile
    proof = _build_valid_proof()
    proof["status"] = "FAIL"
    proof["failures"] = ["test failure"]
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(proof, f)
        temp_path = Path(f.name)
    try:
        record = checker.verify(temp_path)
        assert record["status"] == "FAIL"
        assert any("status" in f.lower() for f in record["failures"])
    finally:
        temp_path.unlink()


def test_acceptor_rejects_wrong_wheel_sha256():
    import tempfile
    proof = _build_valid_proof()
    proof["candidate"]["wheel_sha256"] = "0" * 64
    proof["integrity"]["wheel_sha256"] = "0" * 64
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(proof, f)
        temp_path = Path(f.name)
    try:
        record = checker.verify(temp_path)
        assert record["status"] == "FAIL"
    finally:
        temp_path.unlink()


def test_acceptor_rejects_duplicate_json_keys(tmp_path):
    with pytest.raises(ValueError):
        checker.strict_json(b'{"a": 1, "a": 2}')

    duplicate_path = tmp_path / "duplicate-proof.json"
    duplicate_path.write_text(
        '{"schema":"LOCAL_ALPHA_VERIFICATION_1",'
        '"schema":"LOCAL_ALPHA_VERIFICATION_1"}', encoding="utf-8")
    with pytest.raises(ValueError):
        checker.verify(duplicate_path)

    malformed_path = tmp_path / "malformed-proof.json"
    malformed_path.write_text('{"schema":', encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        checker.verify(malformed_path)


def test_acceptor_rejects_non_finite_json_constants():
    import pytest
    with pytest.raises(ValueError):
        checker.strict_json(b'{"a": Infinity}')
    with pytest.raises(ValueError):
        checker.strict_json(b'{"a": NaN}')
    with pytest.raises(ValueError):
        checker.strict_json(b'{"a": -Infinity}')
