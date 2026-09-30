"""Read-only, byte-bound acceptance check for the T-87 external proof.

Run from any directory. Prints the acceptance record; never rebuilds the
candidate, modifies the proof, or changes advertised platform support.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROOF = ".saipen/evidence/SAIMAIL_V2-04_external_linux_verification.json"
COPY = "release/evidence/SAIMAIL_V2-04_external_linux_verification.json"
PROOF_SHA256 = "819f3fcf445c051aec20864098960ccb37a69c8ce6aced0872f2198a96b95f94"
WHEEL_SHA256 = "ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a"
BUNDLE = ROOT / "release/local-alpha"
WHEEL = "saimail-0.0.2a1-py3-none-any.whl"


def digest(data):
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


def strict_json(data):
    return json.loads(data.decode("utf-8"), object_pairs_hook=unique_object,
                      parse_constant=reject_constant)


def verify():
    proof_bytes = (ROOT / PROOF).read_bytes()
    actual_proof_hash = digest(proof_bytes)
    actual_wheel_hash = digest((BUNDLE / WHEEL).read_bytes())
    if actual_proof_hash != PROOF_SHA256 or actual_wheel_hash != WHEEL_SHA256:
        raise ValueError("EXTERNAL_PROOF_CANDIDATE_MISMATCH")
    proof = strict_json(proof_bytes)
    manifest = strict_json((BUNDLE / "local_alpha_candidate.json").read_bytes())
    identity = (
        proof["candidate"]["version"] == manifest["package_version"] == "0.0.2a1"
        and proof["candidate"]["wheel_filename"] == manifest["wheel"]["filename"] == WHEEL
        and proof["candidate"]["wheel_sha256"] == manifest["wheel"]["sha256"]
        == actual_wheel_hash
        and proof["integrity"]["wheel_sha256"] == actual_wheel_hash
        and proof["integrity"]["candidate_version"] == "0.0.2a1"
        and proof["install"]["wheel"] == WHEEL
    )
    if not identity:
        raise ValueError("EXTERNAL_PROOF_CANDIDATE_MISMATCH")
    checks = {"proof_sha256": True, "wheel_sha256": True, "candidate_identity": True,
              "strict_json": True}
    expected = {
        "schema": "LOCAL_ALPHA_VERIFICATION_1", "version": 1,
        "status": "PASS", "failures": [],
        "candidate.publication_status": "NOT_PUBLISHED",
        "install.status": "INSTALLED",
        "module_resolution.resolved_inside_environment": True,
        "fg05.schema": "LOCAL_SCENARIO_RESULT_1", "fg05.status": "PASS",
        "fg06.schema": "FG06_UTILITY_RESULT_1", "fg06.outcome_category": "UTILITY_CONDITIONAL",
        "v201_acceptance.schema": "LOCAL_WORKSPACE_RESULT_1", "v201_acceptance.status": "PASS",
        "v201_direct_command.schema": "LOCAL_WORKSPACE_COMMAND_1", "v201_direct_command.status": "CREATED",
        "privacy.status": "PASS", "privacy.private_key_material_found": False,
        "privacy.findings": [], "runtime_counters.network_attempts": 0,
        "runtime_counters.model_calls": 0, "runtime_counters.provider_calls": 0,
        "environment.platform": "linux", "environment.python_version": "3.13.5",
        "environment.verifier_version": 1, "integrity.status": "PASS", "integrity.failures": [],
        "integrity.manifest_schema": "LOCAL_ALPHA_CANDIDATE_1",
        "api_map.schema": "SAIMAIL_STABLE_LOCAL_API_1", "api_map.path_exists": True,
        "api_map.release": "0.0.2a1", "api_map.release_matches": True,
        "saimail_local_version.status": "PASS", "saimail_local_version.expected": "0.0.2a1",
        "saimail_local_version.reported": "0.0.2a1", "limitations.acknowledged": True,
        "limitations.identity": "LOCAL_ALPHA_LIMITATIONS_1",
        "limitations.utility_verdict": "UTILITY_CONDITIONAL",
        "fg05.network_attempts": 0, "fg06.network_attempts": 0,
        "v201_acceptance.network_attempts": 0, "v201_direct_command.network_attempts": 0,
    }
    for field, required in expected.items():
        value = proof
        for part in field.split("."):
            value = value[part]
        checks[field] = type(value) is type(required) and value == required
    checks["manifest_not_published"] = manifest["publication_status"] == "NOT_PUBLISHED"
    paths = proof["module_resolution"]["paths"]
    prefix = "/tmp/saimail-local-alpha-verify-1d_du8a8/venv/lib/python3.13/site-packages/"
    checks["installed_module_paths"] = paths == [
        prefix + "saimail/__init__.py", prefix + "lab/__init__.py", prefix + "saimail_local.py"]
    if (ROOT / COPY).exists():
        checks["stored_copy_byte_identical"] = (ROOT / COPY).read_bytes() == proof_bytes
    failures = [field for field, passed in checks.items() if not passed]
    if failures:
        raise ValueError(f"EXTERNAL_PROOF_VALIDATION_FAILED: {failures}")
    return {
        "schema": "V204_EXTERNAL_PROOF_ACCEPTANCE_1", "version": 1,
        "status": "PASS", "failures": [], "source": PROOF,
        "stored_copy": COPY if (ROOT / COPY).exists() else None,
        "external_proof_sha256": actual_proof_hash, "candidate_sha256": actual_wheel_hash,
        "external_environment": proof["environment"], "checks": checks,
        "frozen_platform_proof_scope": manifest["platform_proof_scope"],
        "support_scope_changed": False, "publication": "NONE",
        "frozen_bundle_sha256": {
            str(path.relative_to(BUNDLE)).replace("\\", "/"): digest(path.read_bytes())
            for path in sorted(BUNDLE.rglob("*")) if path.is_file()
        },
    }


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2, sort_keys=True))
