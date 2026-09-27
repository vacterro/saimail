"""D2 focused acceptance: the frozen 0.0.2a2 candidate and its evidence.

Areas: historical a1 immutability (wheel bytes, manifest, external proof
binding, publication), the new candidate's separate identity-bearing path, the
mechanical build guards, version surfaces at 0.0.2a2, the wheel content proof,
and the binding of every a2 evidence file to the exact frozen wheel SHA-256.
Contract: spec/18-LOCAL-ALPHA-v0.md, D-054 and D-055.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
EVIDENCE = ROOT / "release" / "evidence"
A2_BUNDLE = ROOT / "release" / "candidates" / "0.0.2a2"
A2_EVIDENCE = EVIDENCE / "a2"
A1_BUNDLE = ROOT / "release" / "local-alpha"
A1_SHA256 = "ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lar = _load("local_alpha_release", TOOLS / "local_alpha_release.py")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _a2_manifest() -> dict:
    return _json(A2_BUNDLE / "local_alpha_candidate.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_historical_a1_is_byte_identical_and_still_verifies():
    wheel = A1_BUNDLE / "saimail-0.0.2a1-py3-none-any.whl"
    assert _sha256(wheel) == A1_SHA256
    manifest = _json(A1_BUNDLE / "local_alpha_candidate.json")
    assert manifest["package_version"] == "0.0.2a1"
    assert manifest["wheel"]["sha256"] == A1_SHA256
    assert manifest["publication_status"] == "NOT_PUBLISHED"
    acceptance = _json(EVIDENCE / "external_proof_acceptance.json")
    assert acceptance["candidate_sha256"] == A1_SHA256
    proof = _json(EVIDENCE / "SAIMAIL_V2-04_external_linux_verification.json")
    assert proof["candidate"]["wheel_sha256"] == A1_SHA256
    report = lar.verify_historical_a1(ROOT)
    assert report["status"] == "PASS", report["failures"]
    assert report["actual_sha256"] == A1_SHA256


def test_build_tooling_refuses_to_touch_the_historical_bundle():
    try:
        lar.build_candidate(ROOT, A1_BUNDLE)
    except lar.ReleaseError as exc:
        assert exc.code == "HISTORICAL_BUNDLE_PROTECTED"
    else:
        raise AssertionError("building into the historical a1 bundle was not refused")


def test_build_tooling_refuses_to_overwrite_any_frozen_bundle(tmp_path):
    frozen = tmp_path / "candidate"
    frozen.mkdir()
    (frozen / "local_alpha_candidate.json").write_text("{}\n", encoding="utf-8")
    try:
        lar.build_candidate(ROOT, frozen)
    except lar.ReleaseError as exc:
        assert exc.code == "BUNDLE_ALREADY_FROZEN"
    else:
        raise AssertionError("an existing frozen bundle was not refused")


def test_new_candidate_lives_in_its_own_identity_bearing_path():
    assert (A2_BUNDLE / "local_alpha_candidate.json").is_file()
    manifest = _a2_manifest()
    assert manifest["package_version"] == "0.0.2a2"
    wheel = A2_BUNDLE / manifest["wheel"]["filename"]
    assert wheel.name == "saimail-0.0.2a2-py3-none-any.whl"
    a2_hash = _sha256(wheel)
    assert a2_hash != A1_SHA256
    assert manifest["wheel"]["sha256"] == a2_hash
    assert manifest["publication_status"] == "NOT_PUBLISHED"
    assert manifest["historical_candidate_a1"]["sha256"] == A1_SHA256


def test_frozen_a2_wheel_passes_the_mechanical_content_proof():
    manifest = _a2_manifest()
    wheel = A2_BUNDLE / manifest["wheel"]["filename"]
    proof = lar.wheel_content_proof(wheel)
    assert proof["status"] == "PASS", proof["failures"]
    assert proof["checks"]["custody_module"] is True
    assert proof["checks"]["identity_schema_v2"] is True
    assert proof["checks"]["cli_custody_flag"] is True
    assert proof["checks"]["cli_custody_status"] is True
    assert proof["checks"]["cli_custody_migrate"] is True
    assert proof["checks"]["first_run_notice"] is True
    names = set(zipfile.ZipFile(wheel).namelist())
    assert "saimail/custody.py" in names
    assert len(names) == manifest["wheel"]["member_count"]


def test_version_surfaces_are_a2_everywhere():
    """Historical a2 bundle stays 0.0.2a2; current source truth belongs to D3/a3 tests."""
    manifest = _a2_manifest()
    assert manifest["package_version"] == "0.0.2a2"
    wheel = A2_BUNDLE / manifest["wheel"]["filename"]
    assert wheel.name == "saimail-0.0.2a2-py3-none-any.whl"
    a2_hash = _sha256(wheel)
    assert a2_hash == "d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d"
    assert manifest["wheel"]["sha256"] == a2_hash
    hist = _json(EVIDENCE / "d3" / "immutability.json")
    assert hist["a2"]["expected_sha256"] == a2_hash
    assert hist["a2"]["status"] == "PASS"
    decision = _json(EVIDENCE / "d3" / "release_decision.json")
    assert decision["outcome"] == "NEW_CANDIDATE_REQUIRED"
    assert decision["version_decision"]["current_frozen_artifact_version"] == "0.0.2a2"
    assert decision["version_decision"]["current_source_declared_version"] == "0.0.2a3"


def test_every_a2_evidence_file_binds_the_exact_frozen_wheel():
    manifest = _a2_manifest()
    expected = manifest["wheel"]["sha256"]
    verification = _json(A2_EVIDENCE / "local_alpha_verification.json")
    osstore = _json(A2_EVIDENCE / "windows_os_store_proof.json")
    repro = _json(A2_EVIDENCE / "reproducibility.json")
    claims = _json(A2_EVIDENCE / "claim_matrix.json")
    gates = _json(A2_EVIDENCE / "gate_evaluation.json")
    external = _json(A2_EVIDENCE / "external_linux_verification.json")
    acceptance = _json(A2_EVIDENCE / "external_verification_record.json")
    assert verification["candidate"]["wheel_sha256"] == expected
    assert verification["status"] == "PASS", verification["failures"]
    assert osstore["candidate"]["wheel_sha256"] == expected
    assert osstore["status"] == "PASS", osstore["failures"]
    assert repro["status"] == "PASS", repro["checks"]
    assert repro["selected_candidate"] == expected
    assert claims["candidate"]["wheel_sha256"] == expected
    assert claims["status"] == "PASS"
    assert gates["candidate"]["wheel_sha256"] == expected
    assert external["candidate"]["wheel_sha256"] == expected
    assert external["status"] == "PASS", external["failures"]
    assert acceptance["candidate_sha256"] == expected
    assert acceptance["status"] == "PASS", acceptance["failures"]


def test_a2_privacy_and_integrity_gates_pass_with_red_controls():
    privacy = _json(A2_EVIDENCE / "privacy_controls.json")
    integrity = _json(A2_EVIDENCE / "integrity_controls.json")
    assert privacy["status"] == "PASS"
    assert privacy["privacy"]["status"] == "PASS"
    assert all(control["ok"] for control in privacy["red_controls"])
    assert {control["control"] for control in privacy["red_controls"]} == {
        "planted_plaintext_marker", "planted_generated_private_key_material"}
    assert integrity["status"] == "PASS"
    assert integrity["integrity"]["status"] == "PASS"
    assert all(control["ok"] for control in integrity["red_controls"])
    assert {control["control"] for control in integrity["red_controls"]} == {
        "corrupt_wheel", "corrupt_recorded_wheel_hash", "corrupt_checksum_entry"}


def test_gate_evaluation_records_external_closure_and_open_publication():
    gates = _json(A2_EVIDENCE / "gate_evaluation.json")
    by_id = {gate["id"]: gate for gate in gates["gates"]}
    assert list(by_id) == [f"G{index}" for index in range(1, 18)]
    for gate_id in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9",
                    "G10", "G11", "G12", "G13", "G14", "G15", "G16"):
        assert by_id[gate_id]["status"] == "PASS", gate_id
    # G17 (publication authorization) stays with the operator: ABSENT, not a
    # blocker to D2 engineering closure.
    assert by_id["G17"]["status"] == "ABSENT"
    assert gates["terminal"] == "DONE"
    assert "2d77e13d" in by_id["G13"]["evidence"]


def test_no_published_a2_artifact_is_claimed():
    manifest = _a2_manifest()
    assert manifest["publication_status"] == "NOT_PUBLISHED"
    claims = _json(A2_EVIDENCE / "claim_matrix.json")
    assert claims["candidate"]["publication_status"] == "NOT_PUBLISHED"
    # The base candidate path is now externally proven; only non-Windows
    # os-store custody stays unproven and publication is forbidden.
    assert claims["not_yet_externally_proven"] == [
        "os-store custody on any non-Windows platform"]
    assert any(entry["claim"] == "fg05" for entry in
               claims["proven_externally_on_exact_a2_wheel"])
    assert claims["external_verification"]["external_proof_sha256"] == (
        "2d77e13dd1e414e8642fb5a1b60e216e2136bb267bf1789c7e1169adfaa1d5c2")
    # The D1 decision packet is history and must not have been rewritten for a2.
    decision = _json(EVIDENCE / "release_decision.json")
    assert decision["outcome"] == "NEW_CANDIDATE_REQUIRED"
    assert decision["version_decision"]["next_candidate_version"] == "0.0.2a2"
    assert decision["publication"] == "NONE"
