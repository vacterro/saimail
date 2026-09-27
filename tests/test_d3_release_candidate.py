"""D3 focused acceptance: the frozen 0.0.2a3 candidate and its evidence.

Areas: current a3 version surfaces, candidate location/identity, extended
P1/V4-01/V5-01 content proof, GUI optional boundary, a1/a2 immutability,
refusal to inherit a2 proof, a3 evidence wheel-hash binding, gate matrix,
publication NOT_PUBLISHED, G17 ABSENT, pending external proof shape.
Contract: spec/18-LOCAL-ALPHA-v0.md, D-056.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
EVIDENCE = ROOT / "release" / "evidence"
A3_BUNDLE = ROOT / "release" / "candidates" / "0.0.2a3"
A3_EVIDENCE = EVIDENCE / "a3"
D3_EVIDENCE = EVIDENCE / "d3"
A2_BUNDLE = ROOT / "release" / "candidates" / "0.0.2a2"
A1_BUNDLE = ROOT / "release" / "local-alpha"
A1_SHA256 = "ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a"
A2_SHA256 = "d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d"
A2_EXTERNAL_PROOF_SHA256 = "2d77e13dd1e414e8642fb5a1b60e216e2136bb267bf1789c7e1169adfaa1d5c2"
A3_SHA256 = "6427feab24c310184e7fd3ec4bb33dc3f5b1581b00128e2ec08d456fa5aa10cc"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lar = _load("local_alpha_release", TOOLS / "local_alpha_release.py")
d3 = _load("d3_release_evidence", TOOLS / "d3_release_evidence.py")


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _a3_manifest() -> dict:
    return _json(A3_BUNDLE / "local_alpha_candidate.json")


def _candidate_identity() -> dict:
    return {
        "version": "0.0.2a3",
        "wheel_filename": "saimail-0.0.2a3-py3-none-any.whl",
        "wheel_sha256": A3_SHA256,
        "publication_status": "NOT_PUBLISHED",
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _strict_acceptance() -> dict:
    identity = _candidate_identity()
    return {
        "schema": d3.a3_acceptor.ACCEPT_SCHEMA,
        "version": 1,
        "status": "PASS",
        "failures": [],
        "candidate_version": identity["version"],
        "candidate_sha256": identity["wheel_sha256"],
        "external_schema": "LOCAL_ALPHA_VERIFICATION_1",
        "external_proof_sha256": "a" * 64,
        "proof_provenance": "OPERATOR_SUPPLIED_UNVERIFIED",
        "publication": "NONE",
        "checks": {key: True for key in d3.a3_acceptor.ACCEPTANCE_REQUIRED_CHECKS},
    }


def _run_gate(tmp_path: Path, *, suite="valid", saipen="valid",
              documentation="valid", external=None, gui="valid",
              repro="valid", integrity="valid", privacy="valid"):
    identity = _candidate_identity()
    source = {
        "verification": A3_EVIDENCE / "local_alpha_verification.json",
        "osstore": A3_EVIDENCE / "windows_os_store_proof.json",
        "privacy": A3_EVIDENCE / "privacy_controls.json",
        "integrity": A3_EVIDENCE / "integrity_controls.json",
        "repro": A3_EVIDENCE / "reproducibility.json",
        "gui": A3_EVIDENCE / "gui_install_matrix.json",
    }
    evidence = {key: _json(path) for key, path in source.items()}
    for key in ("privacy", "integrity"):
        evidence[key]["candidate"] = identity
        evidence[key]["failures"] = []
    evidence["repro"]["candidate"] = identity

    args = argparse.Namespace(
        bundle=str(A3_BUNDLE),
        verification=str(_write_json(tmp_path / "verification.json", evidence["verification"])),
        osstore_proof=str(_write_json(tmp_path / "osstore.json", evidence["osstore"])),
        privacy=str(_write_json(tmp_path / "privacy.json", evidence["privacy"])),
        integrity=str(_write_json(tmp_path / "integrity.json", evidence["integrity"])),
        repro=str(_write_json(tmp_path / "repro.json", evidence["repro"])),
        gui_matrix=(str(_write_json(tmp_path / "gui.json", evidence["gui"]))
                    if gui == "valid" else None),
        external_acceptance=None,
        full_suite=None,
        saipen=None,
        documentation=None,
        state=None, board=None, current_state=None, roadmap=None, external_request=None,
        out=str(tmp_path / "gate.json"),
    )
    if isinstance(gui, dict):
        args.gui_matrix = str(_write_json(tmp_path / "gui.json", gui))
    if suite != "not_run":
        suite_record = {
            "schema": "SAIMAIL_D3_FULL_SUITE_1", "version": 1,
            "candidate_version": identity["version"],
            "candidate_wheel_filename": identity["wheel_filename"],
            "candidate_wheel_sha256": identity["wheel_sha256"],
            "status": "PASS", "tests": 2477, "failures": 0, "errors": 0,
            "skipped": 0, "failed_tests": [], "run_returncode": 0,
            "junit_sha256": "b" * 64, "source_tree_unchanged_during_run": True,
            "source_tree_fingerprint": d3._source_tree_fingerprint(),
            "command": [sys.executable, "-m", "pytest", "-q", "-o", "addopts=",
                        "--basetemp", str(tmp_path / "basetemp"), "--tb=short",
                        "--junitxml", str(tmp_path / "junit.xml")],
        }
        if isinstance(suite, dict):
            suite_record.update(suite)
        args.full_suite = str(_write_json(tmp_path / "suite.json", suite_record))
    if saipen != "not_run":
        problem_signatures = [
            {"rule_id": f"inherited-{index}", "subject_id": f"T-{index}",
             "detail_hash": f"{index:016x}"} for index in range(4)]
        saipen_record = {
            "schema": "SAIMAIL_D3_SAIPEN_VALIDATION_1", "version": 1,
            "candidate_version": identity["version"],
            "candidate_wheel_filename": identity["wheel_filename"],
            "candidate_wheel_sha256": identity["wheel_sha256"],
            "baseline": {"problems": 4, "warnings": 23,
                         "problem_signatures": problem_signatures},
            "problems": 4, "warnings": 23,
            "problem_signatures": problem_signatures,
            "new_problem_signatures": [],
            "new_candidate_attributable_failures": 0,
            "failure_lines": ["inherited"] * 4, "warning_lines": [],
            "warning_details_available": False,
            "canonical_validator_verdict": "FAIL", "validator_exit_code": 1,
            "result": "INHERITED_BASELINE_MATCH",
            "source_tree_fingerprint": d3._source_tree_fingerprint(),
        }
        if isinstance(saipen, dict):
            saipen_record.update(saipen)
        args.saipen = str(_write_json(tmp_path / "saipen.json", saipen_record))
    if documentation != "not_run":
        doc_args = argparse.Namespace(bundle=str(A3_BUNDLE), out=str(
            tmp_path / "documentation.json"), state=None, board=None,
            current_state=None, roadmap=None, external_request=None)
        d3.cmd_documentation(doc_args)
        doc_record = _json(Path(doc_args.out))
        if isinstance(documentation, dict):
            doc_record.update(documentation)
        args.documentation = str(_write_json(tmp_path / "documentation.json", doc_record))
    if external is not None:
        args.external_acceptance = str(_write_json(
            tmp_path / "external.json", external))
    if isinstance(repro, dict):
        _write_json(Path(args.repro), repro)
    if isinstance(integrity, dict):
        _write_json(Path(args.integrity), integrity)
    if isinstance(privacy, dict):
        _write_json(Path(args.privacy), privacy)
    result = d3.cmd_gates(args)
    return result, _json(Path(args.out))


def test_current_a3_version_surfaces():
    assert (ROOT / "VERSION").read_text(encoding="utf-8").strip() == "0.0.2a3"
    assert _json(ROOT / "lab" / "stable_local_api.json")["release"] == "0.0.2a3"
    assert 'version = "0.0.2a3"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for name in ("README.md", "README.ee.md", "README.ded.md", "README.ja.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "0.0.2a3" in text, name
    assert "## 0.0.2a3" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_a3_candidate_location_and_manifest_identity():
    assert (A3_BUNDLE / "local_alpha_candidate.json").is_file()
    manifest = _a3_manifest()
    assert manifest["package_version"] == "0.0.2a3"
    wheel = A3_BUNDLE / manifest["wheel"]["filename"]
    assert wheel.name == "saimail-0.0.2a3-py3-none-any.whl"
    assert manifest["wheel"]["sha256"] == A3_SHA256
    assert _sha256(wheel) == A3_SHA256
    assert wheel != A2_BUNDLE / "saimail-0.0.2a2-py3-none-any.whl"
    assert A3_SHA256 != A2_SHA256 != A1_SHA256
    assert manifest["wheel"]["member_count"] == 65
    assert wheel.name not in {p.name for p in A2_BUNDLE.iterdir()}
    assert manifest["publication_status"] == "NOT_PUBLISHED"
    assert manifest["historical_candidate_a1"]["sha256"] == A1_SHA256
    assert manifest["historical_candidate_a2"]["sha256"] == A2_SHA256


def test_extended_p1_v401_v501_content_proof():
    manifest = _a3_manifest()
    wheel = A3_BUNDLE / manifest["wheel"]["filename"]
    proof = lar.wheel_content_proof(wheel, require_product_delta=True)
    assert proof["status"] == "PASS", proof["failures"]
    assert proof["product_delta"]["status"] == "PASS"
    checks = proof["checks"]
    for key in ("custody_module", "workspace_module", "identity_schema_v2",
                "os_store_mode", "cli_custody_flag", "cli_custody_status",
                "cli_custody_migrate", "first_run_notice",
                "p1_inbox_query_module", "p1_query_projection", "p1_cli_inbox_filters",
                "v401_correspondence_continuation", "v401_cli_reply",
                "v501_gui_adapter", "v501_gui_app", "v501_gui_theme",
                "v501_gui_entrypoint", "v501_gui_extra_declares_pyside6",
                "pyside6_not_core_dependency"):
        assert checks[key] is True, key
    names = set(zipfile.ZipFile(wheel).namelist())
    for expected in ("saimail/inbox_query.py", "saimail/workspace.py",
                     "saimail/gui_app.py", "saimail/gui_adapter.py",
                     "saimail/gui_theme.py", "saimail/custody.py"):
        assert expected in names, expected
    assert len(names) == manifest["wheel"]["member_count"]


def test_gui_optional_dependency_boundary():
    manifest = _a3_manifest()
    wheel = A3_BUNDLE / manifest["wheel"]["filename"]
    checks = (manifest.get("content_proof") or {}).get("product_delta", {}).get("checks", {})
    assert checks.get("v501_gui_extra_declares_pyside6") is True
    assert checks.get("pyside6_not_core_dependency") is True
    # At least one wheel constraint: PySide6 must never be in core requires.
    with zipfile.ZipFile(wheel) as z:
        requires = [line for line in z.read(
            "saimail-0.0.2a3.dist-info/METADATA").decode("utf-8").splitlines()
                    if line.startswith("Requires-Dist:")]
    core = [line for line in requires if "extra ==" not in line]
    assert not any("PySide6" in line for line in core)
    assert any("PySide6" in line and 'extra == "gui"' in line for line in requires)
    manifest_alias = manifest.get("content_proof", {}).get("checks", {})
    assert manifest_alias.get("pyside6_not_core_dependency") is True


def test_a1_immutability_via_d3():
    wheel = A1_BUNDLE / "saimail-0.0.2a1-py3-none-any.whl"
    assert _sha256(wheel) == A1_SHA256
    report = lar.verify_historical_a1(ROOT)
    assert report["status"] == "PASS", report["failures"]
    hist = _json(D3_EVIDENCE / "immutability.json")
    assert hist["a1"]["status"] == "PASS"
    assert hist["a1"]["actual_sha256"] == A1_SHA256


def test_a2_immutability_via_d3():
    wheel = A2_BUNDLE / "saimail-0.0.2a2-py3-none-any.whl"
    assert _sha256(wheel) == A2_SHA256
    report = lar.verify_historical_a2(ROOT)
    assert report["status"] == "PASS", report["failures"]
    hist = _json(D3_EVIDENCE / "immutability.json")
    assert hist["a2"]["status"] == "PASS"
    assert hist["a2"]["actual_sha256"] == A2_SHA256
    assert hist["a2_external_proof_sha256"] == A2_EXTERNAL_PROOF_SHA256


def test_refusal_to_inherit_a2_external_proof():
    decision = _json(D3_EVIDENCE / "release_decision.json")
    boundary = decision["release_evidence_applicability_boundary"]
    assert boundary["a1_external_proof"]["inherited_by_this_candidate"] is False
    assert boundary["a2_external_proof"]["inherited_by_this_candidate"] is False
    a3_m = _a3_manifest()
    assert a3_m["wheel"]["sha256"] != A2_SHA256
    a3_claims = _json(A3_EVIDENCE / "claim_matrix.json")
    assert a3_claims["candidate"]["wheel_sha256"] == A3_SHA256
    external = _json(A3_EVIDENCE / "gate_evaluation.json")
    g13_row = next((gate for gate in external["gates"] if gate["id"] == "G13"), None)
    assert g13_row is not None
    assert g13_row["status"] == "PENDING_EXTERNAL"
    assert A3_SHA256 in g13_row["evidence"]
    assert "ed930e38" not in g13_row["evidence"]
    assert "d1f97537" not in g13_row["evidence"]
    assert a3_claims["proven_externally_on_exact_a3_wheel"] == []
    assert a3_claims["not_yet_externally_proven"] == (
        ["this exact a3 wheel on a genuinely separate external environment (G13)",
         "os-store custody on any non-Windows platform"])


def test_d3_evidence_wheel_hash_binding():
    manifest = _a3_manifest()
    assert manifest["wheel"]["sha256"] == A3_SHA256
    for name in ("local_alpha_verification.json", "windows_os_store_proof.json",
                 "integrity_controls.json", "privacy_controls.json",
                 "reproducibility.json", "claim_matrix.json", "gate_evaluation.json",
                 "gui_install_matrix.json"):
        payload = _json(A3_EVIDENCE / name)
        if "candidate" in payload:
            assert payload["candidate"]["wheel_sha256"] == A3_SHA256, name
        elif "selected_candidate" in payload:
            assert payload["selected_candidate"] == A3_SHA256, name
        if name == "local_alpha_verification.json":
            assert payload["status"] == "PASS"
        if name in ("integrity_controls.json", "privacy_controls.json"):
            assert payload["status"] == "PASS"
        if name == "reproducibility.json":
            assert payload["status"] == "PASS"
        if name == "claim_matrix.json":
            assert payload["status"] == "PASS"
        if name == "gui_install_matrix.json":
            assert payload["status"] == "PASS"
            assert payload["integrity"]["status"] == "PASS"


def test_d3_gate_matrix_and_pending_external():
    gates = _json(A3_EVIDENCE / "gate_evaluation.json")
    assert gates["candidate"]["wheel_sha256"] == A3_SHA256
    assert gates["status"] == "PASS"
    assert gates["terminal"] == "READY_FOR_EXTERNAL_INSTALL_PROOF"
    assert gates["publication"] == "NONE"
    by_id = {g["id"]: g for g in gates["gates"]}
    assert by_id["G13"]["status"] == "PENDING_EXTERNAL"
    assert by_id["G17"]["status"] == "ABSENT"
    for gate_id in ("G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9",
                    "G10", "G11", "G12"):
        assert by_id[gate_id]["status"] == "PASS", gate_id
    assert by_id["G14"]["status"] == "PASS"
    assert by_id["G15"]["status"] == "PASS"
    assert by_id["G16"]["status"] == "PASS"
    assert by_id["G18"]["status"] == "PASS"
    assert by_id["G19"]["status"] == "PASS"
    assert by_id["G20"]["status"] == "PASS"
    assert A3_SHA256 in by_id["G13"]["evidence"]
    required = set(gates.get("required_local_gates") or [])
    assert required == {f"G{n}" for n in range(1, 13)} | {"G14", "G15", "G16"} | {"G18", "G19", "G20"}
    assert gates["blocked_local_gates"] is None


def test_real_gate_engine_requires_g15_and_g16_before_external_ready(tmp_path):
    not_run_dir = tmp_path / "not-run"
    not_run_dir.mkdir()
    result, packet = _run_gate(not_run_dir, suite="not_run")
    assert result == 1
    assert packet["terminal"] == "LOCAL_BLOCKED"
    assert next(g for g in packet["gates"] if g["id"] == "G15")["status"] == "NOT_RUN"

    bad_suite_dir = tmp_path / "bad-suite"
    bad_suite_dir.mkdir()
    result, packet = _run_gate(bad_suite_dir, suite={"tests": 0, "failures": 4,
                                                       "errors": 3})
    assert result == 1
    assert next(g for g in packet["gates"] if g["id"] == "G15")["status"] == "FAIL"

    not_run_saipen_dir = tmp_path / "not-run-saipen"
    not_run_saipen_dir.mkdir()
    result, packet = _run_gate(not_run_saipen_dir, saipen="not_run")
    assert result == 1
    assert next(g for g in packet["gates"] if g["id"] == "G16")["status"] == "NOT_RUN"


@pytest.mark.parametrize("wrong_identity", [
    {"candidate_version": "0.0.2a2"},
    {"candidate_wheel_filename": "saimail-0.0.2a2-py3-none-any.whl"},
    {"candidate_wheel_sha256": A2_SHA256},
])
def test_real_gate_engine_rejects_wrong_candidate_full_suite_pass(tmp_path, wrong_identity):
    result, packet = _run_gate(tmp_path, suite=wrong_identity)
    by_id = {gate["id"]: gate["status"] for gate in packet["gates"]}
    assert result == 1
    assert packet["status"] == "FAIL"
    assert packet["terminal"] == "LOCAL_BLOCKED"
    assert by_id["G15"] == "FAIL"


def test_real_gate_engine_rejects_contradictory_full_suite_pass(tmp_path):
    result, packet = _run_gate(tmp_path, suite={
        "failures": 2, "errors": 1, "failed_tests": ["test_fake_failure"],
    })
    by_id = {gate["id"]: gate["status"] for gate in packet["gates"]}
    assert result == 1
    assert packet["status"] == "FAIL"
    assert packet["terminal"] == "LOCAL_BLOCKED"
    assert by_id["G15"] == "FAIL"


@pytest.mark.parametrize("drift", [
    {"problems": 5, "warnings": 23, "result": "FAIL"},
    {"problems": 4, "warnings": 24, "result": "FAIL"},
    {"problems": 4, "warnings": 23, "new_candidate_attributable_failures": 1,
     "result": "FAIL"},
    {"candidate_wheel_sha256": "0" * 64},
    {"candidate_version": "0.0.2a2"},
])
def test_real_gate_engine_rejects_saipen_drift_and_wrong_candidate(tmp_path, drift):
    result, packet = _run_gate(tmp_path, saipen=drift)
    assert result == 1
    assert packet["terminal"] == "LOCAL_BLOCKED"
    assert next(g for g in packet["gates"] if g["id"] == "G16")["status"] == "FAIL"


def test_real_gate_engine_requires_documentation_evidence(tmp_path):
    result, packet = _run_gate(tmp_path, documentation="not_run")
    assert result == 1
    assert next(g for g in packet["gates"] if g["id"] == "G14")["status"] == "NOT_RUN"


def test_real_gate_engine_rejects_failed_documentation_evidence(tmp_path):
    result, packet = _run_gate(tmp_path, documentation={
        "status": "FAIL", "failures": ["CURRENT_STATE_CONTRADICTS_TICKET"],
    })
    by_id = {gate["id"]: gate["status"] for gate in packet["gates"]}
    assert result == 1
    assert packet["terminal"] == "LOCAL_BLOCKED"
    assert by_id["G14"] == "FAIL"


def test_real_gate_engine_rejects_wrong_documentation_candidate(tmp_path):
    result, packet = _run_gate(tmp_path, documentation={
        "candidate": {**_candidate_identity(), "wheel_sha256": "0" * 64}})
    assert result == 1
    assert next(g for g in packet["gates"] if g["id"] == "G14")["status"] == "FAIL"


@pytest.mark.parametrize("bad_report, gate_id", [
    ({"selected_candidate": "0" * 64}, "G2"),
    ({"candidate": {**_candidate_identity(), "wheel_sha256": "0" * 64}}, "G2"),
])
def test_real_gate_engine_checks_repro_identity(tmp_path, bad_report, gate_id):
    result, packet = _run_gate(tmp_path, repro=bad_report)
    assert result == 1
    assert next(g for g in packet["gates"] if g["id"] == gate_id)["status"] == "FAIL"


def test_real_gate_engine_checks_red_controls_and_gui_identity(tmp_path):
    result, packet = _run_gate(
        tmp_path,
        integrity={"candidate": {**_candidate_identity(), "wheel_sha256": "0" * 64}},
        privacy={"candidate": {**_candidate_identity(), "wheel_sha256": "0" * 64}},
        gui={"candidate": {**_candidate_identity(), "wheel_sha256": "0" * 64}},
    )
    assert result == 1
    by_id = {gate["id"]: gate["status"] for gate in packet["gates"]}
    assert by_id["G10"] == "FAIL"
    assert by_id["G11"] == "FAIL"
    assert by_id["G20"] == "FAIL"


def test_fake_or_wrong_candidate_external_acceptance_is_refused(tmp_path):
    fake = {"status": "PASS", "candidate_sha256": A3_SHA256}
    with pytest.raises(SystemExit, match="EXTERNAL_ACCEPTANCE_NOT_STRICT_A3_PROOF"):
        _run_gate(tmp_path, external=fake)

    empty_dir = tmp_path / "empty-external"
    empty_dir.mkdir()
    with pytest.raises(SystemExit, match="EXTERNAL_ACCEPTANCE_NOT_STRICT_A3_PROOF"):
        _run_gate(empty_dir, external={})

    wrong = _strict_acceptance()
    wrong["candidate_version"] = "0.0.2a2"
    wrong["candidate_sha256"] = A2_SHA256
    wrong["checks"]["not_a2_proof"] = False
    with pytest.raises(SystemExit, match="EXTERNAL_ACCEPTANCE_NOT_STRICT_A3_PROOF"):
        _run_gate(tmp_path, external=wrong)


@pytest.mark.parametrize("field, value", [
    ("schema", "SAIMAIL_A2_EXTERNAL_PROOF_ACCEPTANCE_1"),
    ("version", 2),
    ("candidate_version", "0.0.2a1"),
    ("candidate_sha256", A1_SHA256),
])
def test_real_gate_engine_rejects_wrong_schema_version_or_historical_acceptance(
        tmp_path, field, value):
    invalid = _strict_acceptance()
    invalid[field] = value
    with pytest.raises(SystemExit, match="EXTERNAL_ACCEPTANCE_NOT_STRICT_A3_PROOF"):
        _run_gate(tmp_path, external=invalid)


def test_external_acceptance_cannot_override_a_failed_local_gate(tmp_path):
    result, packet = _run_gate(tmp_path, suite={"tests": 0, "failures": 4},
                               external=_strict_acceptance())
    assert result == 1
    assert packet["terminal"] == "LOCAL_BLOCKED"


def test_real_gate_engine_accepts_only_full_evidence_and_strict_external_record(tmp_path):
    result, packet = _run_gate(tmp_path, external=_strict_acceptance())
    assert result == 0
    assert packet["status"] == "PASS"
    assert packet["terminal"] == "DONE"
    assert packet["publication"] == "NONE"


def test_real_gate_engine_marks_missing_external_proof_pending(tmp_path):
    result, packet = _run_gate(tmp_path)
    assert result == 0
    assert packet["terminal"] == "READY_FOR_EXTERNAL_INSTALL_PROOF"
    assert next(g for g in packet["gates"] if g["id"] == "G13")["status"] == "PENDING_EXTERNAL"


def test_saipen_validation_compares_candidate_findings_to_canonical_baseline(tmp_path):
    signatures = [
        {"rule_id": "inherited-a", "subject_id": "T-1", "detail_hash": "a" * 16},
        {"rule_id": "inherited-b", "subject_id": None, "detail_hash": "b" * 16},
    ]
    baseline = {
        "schema": "SAIMAIL_D3_SAIPEN_BASELINE_1", "version": 1,
        "problems": 2, "warnings": 3, "problem_signatures": signatures,
    }
    receipt = {
        "kind": "conformance_receipt", "gate": "core", "verdict": "FAIL",
        "exit_code": 1, "receipt_id": "receipt-test", "timestamp_utc": "2026-09-23T00:00:00Z",
        "source_tree_fingerprint": "git-delta-test",
        "blocking_findings": {"status": "complete", "problem_count": 2,
                               "warning_count": 3, "problems": signatures},
    }
    status = {"conformance_status": {"status": "CURRENT_FAIL", "receipt": receipt},
              "validator": {"summary": "Validation FAILED"}}
    _write_json(tmp_path / "baseline.json", baseline)
    _write_json(tmp_path / "status.json", status)
    args = argparse.Namespace(bundle=str(A3_BUNDLE), baseline=str(tmp_path / "baseline.json"),
                              status_json=str(tmp_path / "status.json"),
                              out=str(tmp_path / "saipen.json"))

    assert d3.cmd_saipen_validation(args) == 0
    record = _json(Path(args.out))
    assert record["result"] == "INHERITED_BASELINE_MATCH"
    assert record["new_candidate_attributable_failures"] == 0
    assert d3._saipen_validation_valid(record, _candidate_identity())

    status["conformance_status"]["receipt"]["blocking_findings"]["warning_count"] = 4
    _write_json(Path(args.status_json), status)
    assert d3.cmd_saipen_validation(args) == 1
    record = _json(Path(args.out))
    assert record["result"] == "FAIL"
    assert not d3._saipen_validation_valid(record, _candidate_identity())


def test_g13_stays_pending_while_local_gate_is_blocked(tmp_path):
    result, packet = _run_gate(tmp_path, suite={"tests": 0, "failures": 4})
    by_id = {gate["id"]: gate["status"] for gate in packet["gates"]}
    assert result == 1
    assert packet["status"] == "FAIL"
    assert packet["terminal"] == "LOCAL_BLOCKED"
    assert by_id["G13"] == "PENDING_EXTERNAL"
    assert by_id["G15"] == "FAIL"
    assert packet["publication"] == "NONE"


def test_publication_not_published_and_g17_absent():
    assert _a3_manifest()["publication_status"] == "NOT_PUBLISHED"
    decision = _json(D3_EVIDENCE / "release_decision.json")
    assert decision["publication"] == "NONE"
    assert decision["publication_authorization"] == "ABSENT"
    a3_claims = _json(A3_EVIDENCE / "claim_matrix.json")
    assert a3_claims["candidate"]["publication_status"] == "NOT_PUBLISHED"
    gates = _json(A3_EVIDENCE / "gate_evaluation.json")
    by_id = {g["id"]: g for g in gates["gates"]}
    assert by_id["G17"]["status"] == "ABSENT"


# ------------------------------------------------------------------ monotonicity regression tests (Section 10)


def _setup_closure_state(tmp_path: Path):
    """Set up temporary valid T-107 closure state files and return paths dict."""
    state_file = tmp_path / "STATE.md"
    board_file = tmp_path / "BOARD.md"
    current_state_file = tmp_path / "CURRENT-STATE.md"
    roadmap_file = tmp_path / "FUTURE-GATES-V6.md"
    external_request_file = tmp_path / "EXTERNAL_VERIFICATION_REQUEST.md"
    closure_ctx_file = tmp_path / "t107_closure_context.json"
    g14_file = tmp_path / "documentation.json"

    # Copy authoritative files
    current_state_file.write_text((ROOT / "humbox" / "CURRENT-STATE.md").read_text(encoding="utf-8"), encoding="utf-8")
    roadmap_file.write_text((ROOT / "humbox" / "FUTURE-GATES-V6.md").read_text(encoding="utf-8"), encoding="utf-8")
    external_request_file.write_text((A3_EVIDENCE / "EXTERNAL_VERIFICATION_REQUEST.md").read_text(encoding="utf-8"), encoding="utf-8")

    # Construct clean closure state: T-107 is DONE
    state_file.write_text(
        "---\nphase: DONE\ntask: T-107\nnext_action: NONE\nblocker: ''\n---\n",
        encoding="utf-8",
    )
    board_file.write_text(
        "# Board\n\n## DOING\n\n## TODO\n\n## DONE\n"
        "- [x] T-107 [P1] Repair D3 release-control and cold-recovery inconsistencies\n"
        "- [x] T-106 [P1] Execute Roadmap v6 D3\n"
        "- [x] T-108 [P1] S2 seam bridge\n"
        "- [x] T-109 [P1] SAITELEMES\n"
        "- [x] T-110 [P1] SAIPEN Work Desk\n",
        encoding="utf-8",
    )

    ctx_args = argparse.Namespace(
        bundle=str(A3_BUNDLE),
        out=str(closure_ctx_file),
        state=str(state_file),
        board=str(board_file),
        current_state=str(current_state_file),
        roadmap=str(roadmap_file),
        external_request=str(external_request_file),
        closure_event="E-1502",
        source_fingerprint=d3._source_tree_fingerprint(),
        created_utc="2026-09-23T17:42:00Z",
    )
    assert d3.cmd_closure_context(ctx_args) == 0

    doc_args = argparse.Namespace(
        bundle=str(A3_BUNDLE),
        out=str(g14_file),
        state=str(state_file),
        board=str(board_file),
        current_state=str(current_state_file),
        roadmap=str(roadmap_file),
        external_request=str(external_request_file),
        closure_context=str(closure_ctx_file),
        created_utc="2026-09-23T17:43:00Z",
    )
    assert d3.cmd_documentation(doc_args) == 0

    return {
        "state": state_file,
        "board": board_file,
        "current_state": current_state_file,
        "roadmap": roadmap_file,
        "external_request": external_request_file,
        "closure_context": closure_ctx_file,
        "g14": g14_file,
        "doc_args": doc_args,
    }


def test_monotonicity_test_a_subsequent_ticket_does_not_invalidate_closure(tmp_path):
    """Test A: subsequent ticket transition (e.g. T-113 BUILD) does not invalidate historical G14."""
    env = _setup_closure_state(tmp_path)
    identity = _candidate_identity()
    g14_record = _json(env["g14"])
    assert d3._documentation_record_valid(g14_record, identity, env["doc_args"])

    # Transition STATE and BOARD to an unrelated subsequent task: T-113 BUILD
    env["state"].write_text(
        "---\nphase: BUILD\ntask: T-113\nnext_action: 'PHASE BUILD T-113'\nblocker: ''\n---\n",
        encoding="utf-8",
    )
    # T-113 is in DOING, T-107 remains in DONE
    env["board"].write_text(
        "# Board\n\n## DOING\n"
        "- [/] T-113 [P1] SAIGIMN reread continuation\n\n"
        "## TODO\n\n## DONE\n"
        "- [x] T-107 [P1] Repair D3 release-control and cold-recovery inconsistencies\n"
        "- [x] T-106 [P1] Execute Roadmap v6 D3\n"
        "- [x] T-108 [P1] S2 seam bridge\n"
        "- [x] T-109 [P1] SAITELEMES\n"
        "- [x] T-110 [P1] SAIPEN Work Desk\n",
        encoding="utf-8",
    )

    # Historical G14 closure evidence must remain valid!
    assert d3._documentation_record_valid(g14_record, identity, env["doc_args"])


def test_monotonicity_test_b_later_board_additions_do_not_invalidate_closure(tmp_path):
    """Test B: later BOARD ticket rows (e.g. T-114 BLOCKED, T-115 TODO) do not invalidate historical G14."""
    env = _setup_closure_state(tmp_path)
    identity = _candidate_identity()
    g14_record = _json(env["g14"])

    # Add future ticket rows to board
    env["board"].write_text(
        "# Board\n\n## DOING\n"
        "- [/] T-113 [P1] SAIGIMN reread continuation\n\n"
        "## TODO\n"
        "- [ ] T-115 [P1] Next autonomous engineering work\n\n"
        "## DONE\n"
        "- [x] T-107 [P1] Repair D3 release-control and cold-recovery inconsistencies\n"
        "- [x] T-106 [P1] Execute Roadmap v6 D3\n"
        "- [x] T-108 [P1] S2 seam bridge\n"
        "- [x] T-109 [P1] SAITELEMES\n"
        "- [x] T-110 [P1] SAIPEN Work Desk\n\n"
        "## BLOCKED\n"
        "- [ ] T-114 [P1] Future continuation | needs: T-113 | blocked_on: T-113\n",
        encoding="utf-8",
    )

    assert d3._documentation_record_valid(g14_record, identity, env["doc_args"])


def test_monotonicity_test_c_real_t107_contradiction_fails(tmp_path):
    """Test C: real T-107 contradiction (e.g. marking T-107 non-DONE or removing it) fails validation."""
    env = _setup_closure_state(tmp_path)
    identity = _candidate_identity()
    g14_record = _json(env["g14"])

    # Alter T-107 from DONE to non-DONE
    env["board"].write_text(
        "# Board\n\n## DOING\n\n## TODO\n"
        "- [ ] T-107 [P1] Repair D3 release-control and cold-recovery inconsistencies\n\n"
        "## DONE\n"
        "- [x] T-106 [P1] Execute Roadmap v6 D3\n"
        "- [x] T-108 [P1] S2 seam bridge\n"
        "- [x] T-109 [P1] SAITELEMES\n"
        "- [x] T-110 [P1] SAIPEN Work Desk\n",
        encoding="utf-8",
    )

    assert not d3._documentation_record_valid(g14_record, identity, env["doc_args"])


def test_monotonicity_test_d_candidate_identity_drift_fails(tmp_path):
    """Test D: candidate identity drift fails validation."""
    env = _setup_closure_state(tmp_path)
    identity = _candidate_identity()
    g14_record = _json(env["g14"])

    # Drift candidate hash in identity
    drifted_identity = {**identity, "wheel_sha256": "0" * 64}
    assert not d3._documentation_record_valid(g14_record, drifted_identity, env["doc_args"])


def test_monotonicity_test_e_external_publication_contradiction_fails(tmp_path):
    """Test E: claiming publication authorization or unauthorized state fails."""
    env = _setup_closure_state(tmp_path)
    identity = _candidate_identity()
    g14_record = _json(env["g14"])

    # Corrupt state with unauthorized publication
    env["state"].write_text(
        "---\nphase: DONE\ntask: T-107\npublication_status: published\n---\n",
        encoding="utf-8",
    )
    assert not d3._documentation_record_valid(g14_record, identity, env["doc_args"])


def test_monotonicity_test_f_stale_gate_chronology_fails(tmp_path):
    """Test F: gate evaluation created_utc earlier than consumed evidence created_utc is refused."""
    gate_created = "2026-09-23T17:00:00Z"
    suite_created = "2026-09-23T17:46:00Z"

    stale_gate_packet = {
        "schema": d3.GATE_SCHEMA,
        "version": 1,
        "created_utc": gate_created,
        "status": "PASS",
        "candidate": _candidate_identity(),
        "gates": [{"id": f"G{n}", "status": "PASS"} for n in range(1, 13)]
                 + [{"id": "G14", "status": "PASS"}, {"id": "G15", "status": "PASS"},
                    {"id": "G16", "status": "PASS"}, {"id": "G18", "status": "PASS"},
                    {"id": "G19", "status": "PASS"}, {"id": "G20", "status": "PASS"},
                    {"id": "G13", "status": "PENDING_EXTERNAL"}, {"id": "G17", "status": "ABSENT"}],
        "required_local_gates": [f"G{n}" for n in range(1, 13)] + ["G14", "G15", "G16", "G18", "G19", "G20"],
        "consumed_evidence": {
            "verification": {"path": str(tmp_path / "v.json"), "sha256": "a" * 64, "created_utc": "2026-09-23T16:00:00Z"},
            "osstore_proof": {"path": str(tmp_path / "o.json"), "sha256": "a" * 64, "created_utc": "2026-09-23T16:00:00Z"},
            "privacy": {"path": str(tmp_path / "p.json"), "sha256": "a" * 64, "created_utc": "2026-09-23T16:00:00Z"},
            "integrity": {"path": str(tmp_path / "i.json"), "sha256": "a" * 64, "created_utc": "2026-09-23T16:00:00Z"},
            "repro": {"path": str(tmp_path / "r.json"), "sha256": "a" * 64, "created_utc": "2026-09-23T16:00:00Z"},
            "documentation": {"path": str(tmp_path / "d.json"), "sha256": "a" * 64, "created_utc": "2026-09-23T16:50:00Z"},
            "full_suite": {"path": str(tmp_path / "s.json"), "sha256": "a" * 64, "created_utc": suite_created},
            "saipen": {"path": str(tmp_path / "sp.json"), "sha256": "a" * 64, "created_utc": "2026-09-23T16:55:00Z"},
        },
    }

    # Gate evaluation validator must reject stale chronology
    assert not d3._gate_evaluation_valid(stale_gate_packet, _candidate_identity())

    # And cmd_gates itself must refuse to generate when input is in the future
    future_suite = tmp_path / "future_suite.json"
    _write_json(future_suite, {
        "schema": "SAIMAIL_D3_FULL_SUITE_1", "version": 1,
        "candidate_version": "0.0.2a3",
        "candidate_wheel_filename": "saimail-0.0.2a3-py3-none-any.whl",
        "candidate_wheel_sha256": A3_SHA256,
        "status": "PASS", "tests": 100, "failures": 0, "errors": 0, "skipped": 0,
        "failed_tests": [], "run_returncode": 0, "source_tree_unchanged_during_run": True,
        "created_utc": "2099-01-01T00:00:00Z",
        "source_tree_fingerprint": d3._source_tree_fingerprint(),
        "command": [sys.executable, "-m", "pytest", "-q", "-o", "addopts=",
                    "--basetemp", "t", "--junitxml", "j"],
    })
    with pytest.raises(SystemExit, match="GATE_CHRONOLOGY_VIOLATION"):
        _run_gate(tmp_path, suite=_json(future_suite))


def test_monotonicity_test_g_evidence_replacement_fails_provenance(tmp_path):
    """Test G: replacing a consumed evidence file after gate generation invalidates aggregation."""
    result, packet = _run_gate(tmp_path)
    assert result == 0
    assert d3._gate_evaluation_valid(packet, _candidate_identity())

    # Tamper with consumed verification file by replacing bytes
    verif_path = Path(packet["consumed_evidence"]["verification"]["path"])
    verif_path.write_text('{"tampered": true}', encoding="utf-8")

    # Aggregation is now invalid because sha256 no longer matches
    assert not d3._gate_evaluation_valid(packet, _candidate_identity())


def test_monotonicity_test_h_valid_final_generation_passes(tmp_path):
    """Test H: valid generation with correct chronology and provenance produces READY_FOR_EXTERNAL_INSTALL_PROOF."""
    result, packet = _run_gate(tmp_path)
    assert result == 0
    assert packet["status"] == "PASS"
    assert packet["terminal"] == "READY_FOR_EXTERNAL_INSTALL_PROOF"
    assert d3._gate_evaluation_valid(packet, _candidate_identity())
    assert "consumed_evidence" in packet
    for logical_id in ("verification", "osstore_proof", "privacy", "integrity", "repro", "documentation", "full_suite", "saipen"):
        assert logical_id in packet["consumed_evidence"]
        assert packet["consumed_evidence"][logical_id]["sha256"]
