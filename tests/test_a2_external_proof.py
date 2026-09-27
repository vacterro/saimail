"""T-92 focused acceptance: the external install proof for the exact frozen
0.0.2a2 wheel.

Contract: the base candidate path is externally verified by a genuine separate
Linux / Python 3.13.5 environment; os-store custody stays Windows-specific and
NOT_TESTED_HERE; publication stays NONE. Nothing here rebuilds the candidate or
modifies the proof.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
A2_EVIDENCE = ROOT / "release" / "evidence" / "a2"
A2_BUNDLE = ROOT / "release" / "candidates" / "0.0.2a2"
PROOF = A2_EVIDENCE / "external_linux_verification.json"
RECORD = A2_EVIDENCE / "external_verification_record.json"
PROOF_SHA256 = "2d77e13dd1e414e8642fb5a1b60e216e2136bb267bf1789c7e1169adfaa1d5c2"
WHEEL_SHA256 = "d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load("accept_a2_external_proof", TOOLS / "accept_a2_external_proof.py")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_external_proof_bytes_are_the_operator_supplied_exact_bytes():
    assert PROOF.is_file()
    assert _sha256(PROOF) == PROOF_SHA256
    record = _json(RECORD)
    assert record["external_proof_sha256"] == PROOF_SHA256
    assert record["proof_byte_identical_copy"] is True


def test_external_proof_validates_against_the_exact_frozen_wheel():
    record = checker.verify(ROOT)
    assert record["status"] == "PASS", record["failures"]
    assert record["external_proof_sha256"] == PROOF_SHA256
    assert record["candidate_sha256"] == WHEEL_SHA256
    assert record["candidate_version"] == "0.0.2a2"
    assert record["environment"] == {
        "platform": "linux", "python_version": "3.13.5",
        "verifier_version": 1, "verified_utc": record["environment"]["verified_utc"],
    }
    assert record["verifier_version"] == 1
    assert record["publication"] == "NONE"
    assert record["platform_scope_changed"] is False


def test_external_proof_records_base_pass_and_os_store_not_tested_here():
    proof = _json(PROOF)
    assert proof["scope"]["base_candidate_verification"] == "TESTED_BY_THIS_VERIFIER"
    assert proof["scope"]["os_store_platform_verification"].startswith("NOT_TESTED_HERE")
    assert proof["status"] == "PASS"
    assert proof["failures"] == []
    assert proof["fg05"]["status"] == "PASS"
    assert proof["fg06"]["outcome_category"] == "UTILITY_CONDITIONAL"
    assert proof["v201_acceptance"]["status"] == "PASS"
    assert proof["v201_direct_command"]["status"] == "CREATED"
    assert proof["v201_direct_command"]["custody_mode"] == "raw"
    assert proof["v201_direct_command"]["first_run_notice"] is True
    assert proof["privacy"]["status"] == "PASS"
    assert proof["privacy"]["private_key_material_found"] is False
    counters = proof["runtime_counters"]
    assert (counters["network_attempts"], counters["model_calls"],
            counters["provider_calls"]) == (0, 0, 0)
    # os-store is linked to the independent Windows installed-wheel authority.
    record = _json(RECORD)
    assert record["windows_os_store_linkage"]["status"] == "PASS"
    assert record["windows_os_store_linkage"]["backend"] == (
        "keyring.backends.Windows.WinVaultKeyring")


def test_external_proof_checker_detects_a_non_identical_copy(tmp_path):
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_bytes(PROOF.read_bytes() + b"\n")
    record = checker.verify(ROOT, stored_copy=corrupt)
    assert record["status"] == "FAIL"
    assert "proof_byte_identical_copy" in record["failures"]


def test_external_proof_checker_rejects_duplicate_json_keys():
    import pytest
    with pytest.raises(ValueError):
        checker.strict_json(b'{"a": 1, "a": 2}')


def test_external_proof_does_not_inherit_a1_and_keeps_a1_history_intact():
    record = _json(RECORD)
    assert record["candidate_sha256"] != (
        "ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a")
    manifest = _json(A2_BUNDLE / "local_alpha_candidate.json")
    assert manifest["publication_status"] == "NOT_PUBLISHED"
    assert manifest["historical_candidate_a1"]["publication_status"] == "NOT_PUBLISHED"
