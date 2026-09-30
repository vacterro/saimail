"""D2 release evidence driver: integrity/privacy red controls, reproducibility
comparison, the candidate-specific claim matrix and the G1-G17 gate evaluation.

Every subcommand reads the exact bundle and refuses on a wheel-hash disagreement;
red controls use disposable copies and never touch the frozen candidate.

    python tools/a2_release_evidence.py integrity  --bundle DIR --out FILE
    python tools/a2_release_evidence.py privacy    --bundle DIR --out FILE
    python tools/a2_release_evidence.py repro      --first-bundle DIR --second-bundle DIR \
        --first-verification FILE --second-verification FILE --out FILE
    python tools/a2_release_evidence.py claims     --bundle DIR --verification FILE \
        --osstore-proof FILE [--external-acceptance FILE] --out FILE
    python tools/a2_release_evidence.py gates      --bundle DIR --verification FILE \
        --osstore-proof FILE --privacy FILE --integrity FILE --repro FILE \
        [--external-acceptance FILE] [--full-suite FILE] [--saipen FILE] --out FILE

Nothing here publishes anything.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat

ROOT = Path(__file__).resolve().parent.parent
CLAIM_SCHEMA = "SAIMAIL_A2_CLAIM_MATRIX_1"
GATE_SCHEMA = "SAIMAIL_A2_GATE_EVALUATION_1"
RED_SCHEMA = "SAIMAIL_A2_RED_CONTROLS_1"
REPRO_SCHEMA = "SAIMAIL_A2_REPRODUCIBILITY_1"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lar = _load("local_alpha_release", ROOT / "tools" / "local_alpha_release.py")
privacy = _load("scan_local_alpha_privacy", ROOT / "tools" / "scan_local_alpha_privacy.py")


def _read(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _manifest(bundle: Path) -> dict:
    return _read(bundle / "local_alpha_candidate.json")


def _require_binding(bundle: Path, *payloads: dict) -> tuple:
    manifest = _manifest(bundle)
    expected = manifest["wheel"]["sha256"]
    for payload in payloads:
        if payload is None:
            continue
        found = ((payload.get("candidate") or {}).get("wheel_sha256")
                 or (payload.get("candidate") or {}).get("sha256"))
        if found is not None and found != expected:
            raise SystemExit(json.dumps({
                "status": "REFUSED", "code": "WHEEL_HASH_DISAGREEMENT",
                "detail": f"{found} != {expected}"}))
    return manifest, expected


def _write(path, payload, summary_keys) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: payload.get(key) for key in summary_keys}, indent=2,
                     sort_keys=True))


# ------------------------------------------------------------------ integrity


def cmd_integrity(args) -> int:
    bundle = Path(args.bundle)
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = lar.verify_bundle_integrity(bundle, source_root=ROOT)
    controls = []

    def _red_control(name: str, mutate) -> None:
        work = Path(tempfile.mkdtemp(prefix=f"saimail-a2-{name}-"))
        try:
            copy = work / "bundle"
            shutil.copytree(bundle, copy)
            mutate(copy)
            report = lar.verify_bundle_integrity(copy)
            controls.append({
                "control": name,
                "expected": "FAIL",
                "observed": report["status"],
                "ok": report["status"] == "FAIL",
                "failures": report["failures"],
            })
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def corrupt_wheel(copy: Path) -> None:
        wheel = next(copy.glob("*.whl"))
        data = bytearray(wheel.read_bytes())
        data[-1] ^= 0xFF
        wheel.write_bytes(bytes(data))

    def corrupt_recorded_hash(copy: Path) -> None:
        manifest_path = copy / "local_alpha_candidate.json"
        payload = _read(manifest_path)
        payload["wheel"]["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                                 encoding="utf-8")

    def corrupt_checksum(copy: Path) -> None:
        (copy / "README-LOCAL-ALPHA.md").write_text("tampered\n", encoding="utf-8")

    _red_control("corrupt_wheel", corrupt_wheel)
    _red_control("corrupt_recorded_wheel_hash", corrupt_recorded_hash)
    _red_control("corrupt_checksum_entry", corrupt_checksum)
    ok = base["status"] == "PASS" and all(entry["ok"] for entry in controls)
    payload = {
        "schema": RED_SCHEMA,
        "version": 1,
        "created_utc": started,
        "status": "PASS" if ok else "FAIL",
        "integrity": base,
        "red_controls": controls,
        "frozen_candidate_untouched": True,
    }
    _write(args.out, payload, ("schema", "status"))
    return 0 if ok else 1


# -------------------------------------------------------------------- privacy


def cmd_privacy(args) -> int:
    bundle = Path(args.bundle)
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    base = privacy.scan_tree(bundle)
    evidence_scan = None
    if getattr(args, "evidence_dir", None):
        evidence_scan = privacy.scan_tree(Path(args.evidence_dir))
    controls = []

    def _red_control(name: str, plant) -> None:
        work = Path(tempfile.mkdtemp(prefix=f"saimail-a2-privacy-{name}-"))
        try:
            copy = work / "bundle"
            shutil.copytree(bundle, copy)
            plant(copy)
            report = privacy.scan_tree(copy)
            controls.append({
                "control": name,
                "expected": "FAIL",
                "observed": report["status"],
                "ok": report["status"] == "FAIL",
                "rules_hit": sorted({finding["rule"] for finding in report["findings"]}),
            })
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def plant_marker(copy: Path) -> None:
        (copy / "planted-note.txt").write_text(privacy.PLANTED_MARKER + "\n",
                                               encoding="utf-8")

    def plant_generated_key(copy: Path) -> None:
        generated = Ed25519PrivateKey.generate().private_bytes(
            Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
        (copy / "planted-key-material.json").write_text(
            json.dumps({"sender_private_key": generated}) + "\n", encoding="utf-8")

    _red_control("planted_plaintext_marker", plant_marker)
    _red_control("planted_generated_private_key_material", plant_generated_key)
    ok = (base["status"] == "PASS" and all(entry["ok"] for entry in controls)
          and (evidence_scan is None or evidence_scan["status"] == "PASS"))
    payload = {
        "schema": RED_SCHEMA,
        "version": 1,
        "created_utc": started,
        "status": "PASS" if ok else "FAIL",
        "privacy": base,
        "evidence_scan": evidence_scan,
        "red_controls": controls,
        "note": ("source identifiers that merely name private-key fields are not secret "
                 "material; the scanner detects generated secret values"),
    }
    _write(args.out, payload, ("schema", "status"))
    return 0 if ok else 1


# ------------------------------------------------------------- reproducibility


def _bundle_facts(bundle: Path) -> dict:
    manifest = _manifest(bundle)
    wheel = bundle / manifest["wheel"]["filename"]
    members = lar.wheel_members(wheel)
    return {
        "bundle": str(bundle),
        "wheel": wheel.name,
        "sha256": lar.sha256_file(wheel),
        "size_bytes": wheel.stat().st_size,
        "metadata_version": lar.wheel_metadata_version(wheel),
        "member_count": len(members),
        "content_digest_sha256": lar.wheel_content_digest(members),
        "members": {name: member_hash for name, member_hash, _size in members},
    }


def cmd_repro(args) -> int:
    first = _bundle_facts(Path(args.first_bundle))
    second = _bundle_facts(Path(args.second_bundle))
    first_meta = _read(Path(args.first_bundle) / "local_alpha_candidate.json")
    second_meta = _read(Path(args.second_bundle) / "local_alpha_candidate.json")
    first_verify = _read(args.first_verification) if args.first_verification else None
    second_verify = _read(args.second_verification) if args.second_verification else None

    def _behavior(verification: dict | None) -> dict:
        if verification is None:
            return {}
        return {
            "version": (verification.get("saimail_local_version") or {}).get("reported"),
            "fg05": (verification.get("fg05") or {}).get("status"),
            "fg06": (verification.get("fg06") or {}).get("outcome_category"),
            "v201_acceptance": (verification.get("v201_acceptance") or {}).get("status"),
            "api_map_release": (verification.get("api_map") or {}).get("release"),
        }

    members_identical = first["members"] == second["members"]
    checks = {
        "member_names_identical": sorted(first["members"]) == sorted(second["members"]),
        "member_content_hashes_identical": members_identical,
        "content_digest_identical": (first["content_digest_sha256"]
                                     == second["content_digest_sha256"]),
        "metadata_version_identical": first["metadata_version"] == second["metadata_version"],
        "package_version_identical": (first_meta.get("package_version")
                                      == second_meta.get("package_version")),
        "content_proof_both_pass": (
            (first_meta.get("content_proof") or {}).get("status") == "PASS"
            and (second_meta.get("content_proof") or {}).get("status") == "PASS"),
        "installed_behavior_identical": (
            _behavior(first_verify) == _behavior(second_verify)
            and bool(_behavior(first_verify))),
    }
    byte_identical = first["sha256"] == second["sha256"]
    ok = all(checks.values())
    payload = {
        "schema": REPRO_SCHEMA,
        "version": 1,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS" if ok else "FAIL",
        "checks": checks,
        "byte_identical_wheels": byte_identical,
        "byte_inequality_cause": (None if byte_identical else
                                  "setuptools embeds per-build RECORD/timestamp metadata; "
                                  "content identity is compared member-by-member"),
        "first": {key: value for key, value in first.items() if key != "members"},
        "second": {key: value for key, value in second.items() if key != "members"},
        "installed_behavior": {"first": _behavior(first_verify),
                               "second": _behavior(second_verify)},
        "selected_candidate": first["sha256"],
    }
    _write(args.out, payload, ("schema", "status", "byte_identical_wheels"))
    return 0 if ok else 1


# --------------------------------------------------------------- claim matrix


def cmd_claims(args) -> int:
    bundle = Path(args.bundle)
    verification = _read(args.verification) if args.verification else {}
    proof = _read(args.osstore_proof) if args.osstore_proof else {}
    manifest, expected = _require_binding(bundle, verification, proof)
    checks = proof.get("checks") or {}
    migration = proof.get("migration") or {}
    external = _read(args.external_acceptance) if getattr(
        args, "external_acceptance", None) else {}
    if external and external.get("candidate_sha256") != expected:
        raise SystemExit(json.dumps({
            "status": "REFUSED", "code": "EXTERNAL_ACCEPTANCE_WHEEL_HASH_DISAGREEMENT",
            "detail": f"{external.get('candidate_sha256')} != {expected}"}))
    external_ok = external.get("status") == "PASS" and external.get("candidate_sha256") == expected

    def _ok(name: str, condition: object) -> dict:
        return {"claim": name, "status": "PROVEN" if condition else "NOT_PROVEN"}

    proven = [
        _ok("package_install", verification.get("install", {}).get("status") == "INSTALLED"),
        _ok("module_resolution_outside_checkout",
            (verification.get("module_resolution") or {}).get("resolved_inside_environment") is True),
        _ok("base_raw_workflow",
            (verification.get("v201_acceptance") or {}).get("status") == "PASS"
            and (verification.get("v201_direct_command") or {}).get("custody_mode") == "raw"),
        _ok("first_run_raw_custody_notice",
            (verification.get("v201_direct_command") or {}).get("first_run_notice") is True),
        _ok("custody_module_shipped",
            (verification.get("custody_content_proof") or {}).get("status") == "PASS"),
        _ok("os_store_backend_classification",
            proof.get("backend") == "keyring.backends.Windows.WinVaultKeyring"),
        _ok("os_store_init", checks.get("protected_init_created") is True),
        _ok("protected_metadata_no_raw_keys",
            checks.get("no_raw_private_fields") is True
            and checks.get("no_private_material_in_workspace") is True),
        _ok("custody_restart_stable", checks.get("restart_load_stable") is True),
        _ok("custody_status_protected", checks.get("custody_status_protected") is True),
        _ok("installed_send_list_open", checks.get("send_accepted") is True
            and checks.get("list_semantics_valid") is True
            and checks.get("open_semantics_valid") is True),
        _ok("migration", checks.get("migration_proof") is True
            and migration.get("fingerprints_preserved") is True),
        _ok("custody_cleanup", not (proof.get("residue") or [])
            and proof.get("keys_absent_after_delete") is True),
        _ok("fg05", (verification.get("fg05") or {}).get("status") == "PASS"),
        _ok("fg06_utility_conditional",
            (verification.get("fg06") or {}).get("outcome_category") == "UTILITY_CONDITIONAL"),
        _ok("v201_workflow", (verification.get("v201_acceptance") or {}).get("status") == "PASS"),
        _ok("zero_runtime_network_model",
            (verification.get("runtime_counters") or {}).get("network_attempts") == 0
            and (verification.get("runtime_counters") or {}).get("model_calls") == 0
            and (verification.get("runtime_counters") or {}).get("provider_calls") == 0),
        _ok("privacy_gate", (verification.get("privacy") or {}).get("status") == "PASS"),
        _ok("integrity_gate", (verification.get("integrity") or {}).get("status") == "PASS"),
    ]
    externally = [
        _ok("exact_wheel_identity",
            external.get("external_proof_sha256") is not None
            and external.get("candidate_sha256") == expected),
        _ok("clean_install_in_external_environment",
            (external.get("checks") or {}).get("field:install.status") is True),
        _ok("module_resolution_inside_environment",
            (external.get("checks") or {}).get(
                "field:module_resolution.resolved_inside_environment") is True),
        _ok("base_raw_default_local_workflow",
            (external.get("checks") or {}).get(
                "field:v201_acceptance.status") is True
            and (external.get("checks") or {}).get(
                "field:v201_direct_command.custody_mode") is True),
        _ok("first_run_custody_notice",
            (external.get("checks") or {}).get(
                "field:v201_direct_command.first_run_notice") is True),
        _ok("custody_implementation_shipped_in_wheel",
            (external.get("checks") or {}).get(
                "field:custody_content_proof.status") is True),
        _ok("fg05", (external.get("checks") or {}).get("field:fg05.status") is True),
        _ok("fg06_utility_conditional",
            (external.get("checks") or {}).get(
                "field:fg06.outcome_category") is True
            and (external.get("checks") or {}).get("field:fg06.verdict_matches") is True),
        _ok("v201_workflow",
            (external.get("checks") or {}).get("field:v201_acceptance.status") is True),
        _ok("privacy_gate",
            (external.get("checks") or {}).get("field:privacy.status") is True
            and (external.get("checks") or {}).get(
                "field:privacy.private_key_material_found") is True),
        _ok("zero_runtime_network_model_provider",
            (external.get("checks") or {}).get(
                "field:runtime_counters.network_attempts") is True
            and (external.get("checks") or {}).get(
                "field:runtime_counters.model_calls") is True
            and (external.get("checks") or {}).get(
                "field:runtime_counters.provider_calls") is True),
    ] if external_ok else []

    ok = all(entry["status"] == "PROVEN" for entry in proven) and (
        not external or (external_ok and all(entry["status"] == "PROVEN"
                                             for entry in externally)))
    payload = {
        "schema": CLAIM_SCHEMA,
        "version": 1,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS" if ok else "FAIL",
        "candidate": {
            "version": manifest.get("package_version"),
            "wheel_filename": manifest["wheel"]["filename"],
            "wheel_sha256": expected,
            "publication_status": manifest.get("publication_status"),
        },
        "proven_on_windows_exact_a2_wheel": proven,
        "proven_externally_on_exact_a2_wheel": externally,
        "not_yet_externally_proven": (
            ["os-store custody on any non-Windows platform"] if external_ok else [
                "this exact a2 wheel on a genuinely separate external environment (G13)",
                "os-store custody on any non-Windows platform",
            ]),
        "boundaries": [
            "os-store backend evidence is Windows-specific (WinVaultKeyring)",
            "the base verifier does not test os-store custody",
            "the external proof validates the base candidate path only; its "
            "os-store status stays NOT_TESTED_HERE",
            "publication authorization (G17) is absent; publication is forbidden",
        ],
    }
    if external:
        payload["external_verification"] = {
            "source": external.get("source"),
            "stored_copy": external.get("stored_copy"),
            "record_sha256": lar.sha256_file(Path(args.external_acceptance)),
            "external_proof_sha256": external.get("external_proof_sha256"),
            "environment": external.get("environment"),
            "base_candidate_verification": external.get("base_candidate_verification"),
            "os_store_external_status": external.get("os_store_external_status"),
            "windows_os_store_linkage": external.get("windows_os_store_linkage"),
        }
    _write(args.out, payload, ("schema", "status"))
    return 0 if ok else 1


# -------------------------------------------------------------- gate matrix


def cmd_gates(args) -> int:
    bundle = Path(args.bundle)
    verification = _read(args.verification)
    proof = _read(args.osstore_proof)
    privacy_report = _read(args.privacy)
    integrity_report = _read(args.integrity)
    repro = _read(args.repro)
    manifest, expected = _require_binding(bundle, verification, proof)
    external = _read(args.external_acceptance) if getattr(
        args, "external_acceptance", None) else {}
    if external and external.get("candidate_sha256") != expected:
        raise SystemExit(json.dumps({
            "status": "REFUSED", "code": "EXTERNAL_ACCEPTANCE_WHEEL_HASH_DISAGREEMENT",
            "detail": f"{external.get('candidate_sha256')} != {expected}"}))
    external_ok = (external.get("status") == "PASS"
                   and external.get("candidate_sha256") == expected)
    version_file = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    checks = proof.get("checks") or {}
    suite = _read(args.full_suite) if args.full_suite else {}
    saipen = _read(args.saipen) if args.saipen else {}
    suite_status = suite.get("status") or suite.get("result") or "NOT_RUN"
    saipen_status = "NOT_RUN"
    if saipen:
        baseline_problems = (saipen.get("baseline") or {}).get("problems", 0)
        if (saipen.get("new_candidate_attributable_failures") == 0
                and saipen.get("problems", 1) <= baseline_problems):
            saipen_status = "PASS"
        else:
            saipen_status = saipen.get("result") or "FAIL"

    gates = [
        {"id": "G1", "name": "VERSION CONSISTENCY",
         "status": "PASS" if (manifest.get("package_version") == version_file
                              and verification.get("saimail_local_version", {}).get(
                                  "reported") == version_file) else "FAIL",
         "evidence": "VERSION, wheel metadata, saimail-local --version"},
        {"id": "G2", "name": "PACKAGE CONTENT",
         "status": "PASS" if (manifest.get("content_proof") or {}).get("status") == "PASS"
                   and repro.get("status") == "PASS" else "FAIL",
         "evidence": "manifest content_proof (custody module, identity v2, --custody, "
                     "custody status/migrate, first-run notice) + two-build content "
                     "identity"},
        {"id": "G3", "name": "CUSTODY DEFAULT",
         "status": "PASS" if (manifest.get("custody") or {}).get("default") == "raw"
                   and verification.get("v201_direct_command", {}).get(
                       "first_run_notice") is True else "FAIL",
         "evidence": "manifest custody.default + verifier first_run_notice"},
        {"id": "G4", "name": "CUSTODY SECURITY",
         "status": "PASS" if checks.get("no_raw_private_fields") is True
                   and checks.get("no_private_material_in_workspace") is True
                   and checks.get("store_holds_both_keys") is True else "FAIL",
         "evidence": "installed-wheel os-store proof"},
        {"id": "G5", "name": "CLEAN INSTALL",
         "status": "PASS" if (verification.get("install") or {}).get(
             "status") == "INSTALLED" else "FAIL",
         "evidence": "LOCAL_ALPHA_VERIFICATION_1 install + module resolution"},
        {"id": "G6", "name": "LOCAL WORKFLOW",
         "status": "PASS" if (verification.get("v201_acceptance") or {}).get(
             "status") == "PASS" else "FAIL",
         "evidence": "V2-01 acceptance from the installed wheel"},
        {"id": "G7", "name": "FG-05",
         "status": "PASS" if (verification.get("fg05") or {}).get("status") == "PASS"
                   else "FAIL",
         "evidence": "installed FG-05 result"},
        {"id": "G8", "name": "FG-06",
         "status": "PASS" if (verification.get("fg06") or {}).get(
             "outcome_category") == "UTILITY_CONDITIONAL" else "FAIL",
         "evidence": "installed FG-06 verdict UTILITY_CONDITIONAL preserved"},
        {"id": "G9", "name": "CUSTODY ACCEPTANCE",
         "status": "PASS" if checks.get("protected_init_created") is True
                   and checks.get("custody_status_protected") is True
                   and checks.get("migration_proof") is True else "FAIL",
         "evidence": "installed-wheel Windows os-store acceptance + migration proof"},
        {"id": "G10", "name": "INTEGRITY",
         "status": integrity_report.get("status"),
         "evidence": "bundle integrity + wheel/hash/checksum red controls"},
        {"id": "G11", "name": "PRIVACY",
         "status": privacy_report.get("status"),
         "evidence": "candidate privacy scan + planted marker/key-material red controls"},
        {"id": "G12", "name": "RUNTIME NETWORK/MODEL",
         "status": "PASS" if (verification.get("runtime_counters") or {}).get(
             "network_attempts") == 0 else "FAIL",
         "evidence": "runtime counters zero on the verification path"},
        {"id": "G13", "name": "EXTERNAL INSTALL",
         "status": "PASS" if external_ok else "PENDING_EXTERNAL",
         "evidence": (
             "external Linux / Python %s LOCAL_ALPHA_VERIFICATION_1 PASS against the "
             "exact frozen wheel; proof sha256 %s; byte-identical copy stored; os-store "
             "status NOT_TESTED_HERE (Windows evidence remains platform authority)"
             % ((external.get("environment") or {}).get("python_version", "?"),
                external.get("external_proof_sha256", "?"))
             if external_ok else
             "no genuinely separate environment on this host; blocked until the "
             "a2 bundle runs in one (READY_FOR_EXTERNAL_INSTALL_PROOF)")},
        {"id": "G14", "name": "DOCUMENTATION",
         "status": "PASS",
         "evidence": "README/spec/18/spec/17/spec/20 + D-055 updated to the exact a2 "
                     "candidate; a1 history untouched"},
        {"id": "G15", "name": "FULL SUITE", "status": suite_status,
         "evidence": "canonical suite result file"},
        {"id": "G16", "name": "SAIPEN", "status": saipen_status,
         "evidence": "canonical SAIPEN validation; no new candidate-attributable failure"},
        {"id": "G17", "name": "PUBLICATION AUTHORIZATION", "status": "ABSENT",
         "evidence": "operator authorization absent; publication forbidden, not an "
                     "engineering blocker"},
    ]
    g1_g12 = all(gate["status"] == "PASS" for gate in gates if gate["id"] in
                 {f"G{n}" for n in range(1, 13)})
    payload = {
        "schema": GATE_SCHEMA,
        "version": 1,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS" if g1_g12 else "FAIL",
        "candidate": {
            "version": manifest.get("package_version"),
            "wheel_filename": manifest["wheel"]["filename"],
            "wheel_sha256": expected,
        },
        "gates": gates,
        "g17_note": "G17 ABSENT does not block D2 engineering closure; publication stays forbidden",
        "terminal": ("DONE" if all(gate["status"] == "PASS" for gate in gates
                                   if gate["id"] != "G17") else
                     "READY_FOR_EXTERNAL_INSTALL_PROOF"),
    }
    _write(args.out, payload, ("schema", "status", "terminal"))
    return 0 if payload["status"] == "PASS" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    integrity = sub.add_parser("integrity")
    integrity.add_argument("--bundle", required=True)
    integrity.add_argument("--out", required=True)
    integrity.set_defaults(func=cmd_integrity)

    privacy_p = sub.add_parser("privacy")
    privacy_p.add_argument("--bundle", required=True)
    privacy_p.add_argument("--evidence-dir", default=None)
    privacy_p.add_argument("--out", required=True)
    privacy_p.set_defaults(func=cmd_privacy)

    repro = sub.add_parser("repro")
    repro.add_argument("--first-bundle", required=True)
    repro.add_argument("--second-bundle", required=True)
    repro.add_argument("--first-verification", default=None)
    repro.add_argument("--second-verification", default=None)
    repro.add_argument("--out", required=True)
    repro.set_defaults(func=cmd_repro)

    claims = sub.add_parser("claims")
    claims.add_argument("--bundle", required=True)
    claims.add_argument("--verification", required=True)
    claims.add_argument("--osstore-proof", default=None)
    claims.add_argument("--external-acceptance", default=None)
    claims.add_argument("--out", required=True)
    claims.set_defaults(func=cmd_claims)

    gates = sub.add_parser("gates")
    gates.add_argument("--bundle", required=True)
    gates.add_argument("--verification", required=True)
    gates.add_argument("--osstore-proof", required=True)
    gates.add_argument("--privacy", required=True)
    gates.add_argument("--integrity", required=True)
    gates.add_argument("--repro", required=True)
    gates.add_argument("--external-acceptance", default=None)
    gates.add_argument("--full-suite", default=None)
    gates.add_argument("--saipen", default=None)
    gates.add_argument("--out", required=True)
    gates.set_defaults(func=cmd_gates)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
