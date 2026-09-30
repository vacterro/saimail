"""Read-only acceptance check for the T-92 external a2 install proof.

Validates the supplied Linux / Python 3.13.5 ``LOCAL_ALPHA_VERIFICATION_1``
proof against the exact frozen ``0.0.2a2`` wheel, requires the stored
byte-identical copy, records the base-vs-os-store claim boundary and links the
Windows installed-wheel os-store proof. Never rebuilds the candidate, never
modifies the proof, never changes advertised platform support.

    python tools/accept_a2_external_proof.py
    python tools/accept_a2_external_proof.py --out release/evidence/a2/external_verification_record.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROOF = (ROOT / ".saipen" / "evidence"
                 / "SAIMAIL_D2_a2_external_linux_verification.json")
STORED_COPY = ROOT / "release" / "evidence" / "a2" / "external_linux_verification.json"
BUNDLE = ROOT / "release" / "candidates" / "0.0.2a2"
WHEEL = "saimail-0.0.2a2-py3-none-any.whl"
OS_STORE_PROOF = ROOT / "release" / "evidence" / "a2" / "windows_os_store_proof.json"

PROOF_SHA256 = "2d77e13dd1e414e8642fb5a1b60e216e2136bb267bf1789c7e1169adfaa1d5c2"
WHEEL_SHA256 = "d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d"
ACCEPT_SCHEMA = "SAIMAIL_A2_EXTERNAL_PROOF_ACCEPTANCE_1"

EXPECTED = {
    "schema": "LOCAL_ALPHA_VERIFICATION_1",
    "version": 1,
    "status": "PASS",
    "failures": [],
    "candidate.version": "0.0.2a2",
    "candidate.wheel_filename": WHEEL,
    "candidate.wheel_sha256": WHEEL_SHA256,
    "candidate.publication_status": "NOT_PUBLISHED",
    "install.status": "INSTALLED",
    "install.wheel": WHEEL,
    "module_resolution.resolved_inside_environment": True,
    "saimail_local_version.status": "PASS",
    "saimail_local_version.expected": "0.0.2a2",
    "saimail_local_version.reported": "0.0.2a2",
    "api_map.schema": "SAIMAIL_STABLE_LOCAL_API_1",
    "api_map.path_exists": True,
    "api_map.release": "0.0.2a2",
    "api_map.release_matches": True,
    "custody_content_proof.status": "PASS",
    "fg05.schema": "LOCAL_SCENARIO_RESULT_1",
    "fg05.status": "PASS",
    "fg05.network_attempts": 0,
    "fg06.schema": "FG06_UTILITY_RESULT_1",
    "fg06.outcome_category": "UTILITY_CONDITIONAL",
    "fg06.expected_verdict": "UTILITY_CONDITIONAL",
    "fg06.verdict_matches": True,
    "fg06.network_attempts": 0,
    "v201_acceptance.schema": "LOCAL_WORKSPACE_RESULT_1",
    "v201_acceptance.status": "PASS",
    "v201_acceptance.network_attempts": 0,
    "v201_direct_command.schema": "LOCAL_WORKSPACE_COMMAND_1",
    "v201_direct_command.status": "CREATED",
    "v201_direct_command.custody_mode": "raw",
    "v201_direct_command.first_run_notice": True,
    "v201_direct_command.network_attempts": 0,
    "privacy.status": "PASS",
    "privacy.private_key_material_found": False,
    "privacy.findings": [],
    "runtime_counters.network_attempts": 0,
    "runtime_counters.model_calls": 0,
    "runtime_counters.provider_calls": 0,
    "environment.platform": "linux",
    "environment.python_version": "3.13.5",
    "environment.verifier_version": 1,
    "integrity.status": "PASS",
    "integrity.candidate_version": "0.0.2a2",
    "integrity.wheel_sha256": WHEEL_SHA256,
    "integrity.failures": [],
    "limitations.acknowledged": True,
    "limitations.utility_verdict": "UTILITY_CONDITIONAL",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError(f"non-finite JSON constant: {value}")


def strict_json(data: bytes) -> dict:
    return json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=reject_constant)


def _resolve(payload: dict, dotted: str):
    value = payload
    for part in dotted.split("."):
        value = value[part]
    return value


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def verify(root: Path = ROOT, proof_path: Path | None = None,
           stored_copy: Path | None = None) -> dict:
    proof_path = proof_path or (root / ".saipen" / "evidence"
                                / "SAIMAIL_D2_a2_external_linux_verification.json")
    stored_copy = stored_copy or (root / "release" / "evidence" / "a2"
                                  / "external_linux_verification.json")
    bundle = root / "release" / "candidates" / "0.0.2a2"
    os_store_proof = root / "release" / "evidence" / "a2" / "windows_os_store_proof.json"

    checks: dict[str, bool] = {}
    failures: list[str] = []

    if not proof_path.is_file():
        return {
            "schema": ACCEPT_SCHEMA, "version": 1, "status": "FAIL",
            "failures": [f"EXTERNAL_PROOF_MISSING: {proof_path}"],
            "checks": {"proof_present": False},
        }
    proof_bytes = proof_path.read_bytes()
    actual_proof_hash = digest(proof_bytes)
    actual_wheel_hash = digest((bundle / WHEEL).read_bytes())
    checks["supplied_proof_sha256"] = actual_proof_hash == PROOF_SHA256
    checks["frozen_wheel_sha256"] = actual_wheel_hash == WHEEL_SHA256
    checks["proof_byte_identical_copy"] = (
        stored_copy.is_file() and stored_copy.read_bytes() == proof_bytes)
    if not (checks["supplied_proof_sha256"] and checks["frozen_wheel_sha256"]):
        failures.append("EXTERNAL_PROOF_CANDIDATE_MISMATCH")

    proof = strict_json(proof_bytes)
    manifest = strict_json((bundle / "local_alpha_candidate.json").read_bytes())
    checks["strict_json"] = True

    for dotted, required in EXPECTED.items():
        try:
            value = _resolve(proof, dotted)
        except (KeyError, TypeError):
            value = object()
        checks[f"field:{dotted}"] = (type(value) is type(required)
                                     and value == required)

    scope = proof.get("scope") or {}
    checks["scope.base_candidate_verification"] = (
        scope.get("base_candidate_verification") == "TESTED_BY_THIS_VERIFIER")
    os_store_scope = scope.get("os_store_platform_verification")
    checks["scope.no_external_os_store_claim"] = (
        isinstance(os_store_scope, str)
        and os_store_scope.startswith("NOT_TESTED_HERE"))

    paths = (proof.get("module_resolution") or {}).get("paths") or []
    checks["installed_paths_are_external_linux"] = (
        bool(paths) and all(isinstance(p, str) and p.startswith("/tmp/")
                            for p in paths))

    checks["manifest_version_matches"] = manifest.get("package_version") == "0.0.2a2"
    checks["manifest_wheel_sha256_matches"] = (
        manifest.get("wheel", {}).get("sha256") == WHEEL_SHA256)
    checks["manifest_not_published"] = manifest.get("publication_status") == "NOT_PUBLISHED"

    os_store = strict_json(os_store_proof.read_bytes()) if os_store_proof.is_file() else {}
    checks["windows_os_store_linkage"] = (
        os_store.get("status") == "PASS"
        and os_store.get("candidate", {}).get("wheel_sha256") == WHEEL_SHA256)

    failures.extend(name for name, ok in checks.items() if not ok)

    record = {
        "schema": ACCEPT_SCHEMA,
        "version": 1,
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "source": _rel(proof_path, root),
        "stored_copy": _rel(stored_copy, root),
        "checker": "tools/accept_a2_external_proof.py",
        "external_proof_sha256": actual_proof_hash,
        "candidate_sha256": actual_wheel_hash,
        "candidate_version": proof.get("candidate", {}).get("version"),
        "proof_byte_identical_copy": checks["proof_byte_identical_copy"],
        "external_schema": proof.get("schema"),
        "base_candidate_verification": scope.get("base_candidate_verification"),
        "os_store_external_status": os_store_scope,
        "environment": proof.get("environment"),
        "verifier_version": (proof.get("environment") or {}).get("verifier_version"),
        "offline_mode": "DECLARED_VERIFIER_COMMAND --offline",
        "windows_os_store_linkage": {
            "path": "release/evidence/a2/windows_os_store_proof.json",
            "sha256": digest(os_store_proof.read_bytes()) if os_store_proof.is_file() else None,
            "status": os_store.get("status"),
            "backend": os_store.get("backend"),
        },
        "frozen_platform_proof_scope": manifest.get("platform_proof_scope"),
        "platform_scope_changed": False,
        "publication": "NONE",
        "checks": checks,
    }
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--proof", default=None,
                        help="supplied proof path (default: .saipen/evidence/...)")
    parser.add_argument("--stored-copy", default=None,
                        help="byte-identical copy path (default: release/evidence/a2/...)")
    parser.add_argument("--out", default=None, help="write the acceptance record here")
    args = parser.parse_args(argv)

    record = verify(ROOT,
                    Path(args.proof) if args.proof else None,
                    Path(args.stored_copy) if args.stored_copy else None)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    print(json.dumps({"schema": record["schema"], "status": record["status"],
                      "failures": record["failures"]}, indent=2, sort_keys=True))
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
