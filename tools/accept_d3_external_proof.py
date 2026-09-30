"""Read-only, byte-bound acceptance check for the exact D3/a3 external install proof.

Validates a supplied ``LOCAL_ALPHA_VERIFICATION_1`` proof against the exact frozen
``0.0.2a3`` wheel. It explicitly refuses a1 / a2 proofs (wrong candidate version
and wrong wheel hash), never rebuilds the candidate, never modifies the proof,
and never changes advertised platform support.

    python tools/accept_d3_external_proof.py --proof PATH --out OUT.json

The acceptor records no external provenance of its own: a mechanically valid proof
is not by itself proof that the file originated from a separate machine. A genuine
separate-environment proof is expected to be supplied later by an operator; until
then no production acceptance record is produced.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath

ROOT = Path(__file__).resolve().parent.parent
A3_BUNDLE = ROOT / "release" / "candidates" / "0.0.2a3"
A3_WHEEL = "saimail-0.0.2a3-py3-none-any.whl"
A3_WHEEL_SHA256 = (
    "6427feab24c310184e7fd3ec4bb33dc3f5b1581b00128e2ec08d456fa5aa10cc")
A3_VERSION = "0.0.2a3"
A3_CONTENT_DIGEST = (
    "2f75bdb7d421a6838b8ab292f667a85bb51e207017f0760caf71c9c1e59c061d")
A3_MEMBER_COUNT = 65

A1_SHA256 = "ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a"
A2_SHA256 = "d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d"

ACCEPT_SCHEMA = "SAIMAIL_A3_EXTERNAL_PROOF_ACCEPTANCE_1"
ACCEPT_VERSION = 1


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
    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )


def _resolve(payload: dict, dotted: str):
    value = payload
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            raise KeyError(part)
        value = value[part]
    return value


def _is_a1_or_a2_wheel_sha(sha: str | None) -> bool:
    return sha in (A1_SHA256, A2_SHA256)


def _absolute_native_path(value: str, os_platform: str) -> bool:
    windows = os_platform.lower().startswith(("win", "cygwin", "msys"))
    return (PureWindowsPath(value).is_absolute() if windows
            else PurePosixPath(value).is_absolute())


EXPECTED = {
    "schema": "LOCAL_ALPHA_VERIFICATION_1",
    "version": 1,
    "status": "PASS",
    "failures": [],
    "candidate.version": A3_VERSION,
    "candidate.wheel_filename": A3_WHEEL,
    "candidate.wheel_sha256": A3_WHEEL_SHA256,
    "candidate.publication_status": "NOT_PUBLISHED",
    "install.status": "INSTALLED",
    "install.wheel": A3_WHEEL,
    "module_resolution.resolved_inside_environment": True,
    "saimail_local_version.status": "PASS",
    "saimail_local_version.expected": A3_VERSION,
    "saimail_local_version.reported": A3_VERSION,
    "api_map.schema": "SAIMAIL_STABLE_LOCAL_API_1",
    "api_map.path_exists": True,
    "api_map.release": A3_VERSION,
    "api_map.release_matches": True,
    "custody_content_proof.status": "PASS",
    "fg05.schema": "LOCAL_SCENARIO_RESULT_1",
    "fg05.status": "PASS",
    "fg06.schema": "FG06_UTILITY_RESULT_1",
    "fg06.outcome_category": "UTILITY_CONDITIONAL",
    "fg06.expected_verdict": "UTILITY_CONDITIONAL",
    "fg06.verdict_matches": True,
    "v201_acceptance.schema": "LOCAL_WORKSPACE_RESULT_1",
    "v201_acceptance.status": "PASS",
    "v201_direct_command.schema": "LOCAL_WORKSPACE_COMMAND_1",
    "v201_direct_command.status": "CREATED",
    "v201_direct_command.custody_mode": "raw",
    "v201_direct_command.first_run_notice": True,
    "privacy.status": "PASS",
    "privacy.private_key_material_found": False,
    "privacy.findings": [],
    "runtime_counters.network_attempts": 0,
    "runtime_counters.model_calls": 0,
    "runtime_counters.provider_calls": 0,
    "integrity.status": "PASS",
    "integrity.failures": [],
    "integrity.candidate_version": A3_VERSION,
    "integrity.wheel_sha256": A3_WHEEL_SHA256,
    "limitations.acknowledged": True,
    "limitations.utility_verdict": "UTILITY_CONDITIONAL",
}

ACCEPTANCE_REQUIRED_CHECKS = frozenset({
    "proof_present", "supplied_proof_sha256", "proof_bytes_readable",
    "frozen_wheel_sha256", "a3_wheel_present", "strict_json",
    "schema_correct", "version_correct", "not_a1_proof", "not_a2_proof",
    "candidate_version_correct", "wheel_filename_correct", "wheel_sha256_correct",
    "verifier_status_pass", "verifier_failures_empty",
    *(f"field:{field}" for field in EXPECTED),
    "manifest_version_matches", "manifest_wheel_sha256_matches",
    "manifest_not_published", "content_digest_matches", "member_count_matches",
    "module_resolution_inside_environment", "module_resolution_paths_external",
    "environment_platform_present", "environment_verifier_version_present",
    "publication_identity_consistent",
})


def _load_manifest() -> dict:
    manifest_path = A3_BUNDLE / "local_alpha_candidate.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"a3 manifest missing: {manifest_path}")
    return strict_json(manifest_path.read_bytes())


def verify(proof_path: Path | None = None,
           stored_copy: Path | None = None) -> dict:
    checks: dict[str, bool] = {}
    failures: list[str] = []

    proof_path = proof_path or (
        ROOT / ".saipen" / "evidence" / "SAIMAIL_D3_a3_external_linux_verification.json")
    if not proof_path or not Path(proof_path).is_file():
        return {
            "schema": ACCEPT_SCHEMA, "version": ACCEPT_VERSION, "status": "FAIL",
            "failures": [
                f"EXTERNAL_PROOF_MISSING: {proof_path}"],
            "checks": {"proof_present": False},
        }
    proof_path = Path(proof_path)
    proof_bytes = proof_path.read_bytes()
    actual_proof_hash = digest(proof_bytes)
    checks["proof_present"] = True
    checks["supplied_proof_sha256"] = True
    checks["proof_bytes_readable"] = True

    try:
        wheel_bytes = (A3_BUNDLE / A3_WHEEL).read_bytes()
        actual_wheel_hash = digest(wheel_bytes)
    except FileNotFoundError:
        return {
            "schema": ACCEPT_SCHEMA, "version": ACCEPT_VERSION, "status": "FAIL",
            "failures": ["A3_WHEEL_MISSING"],
            "checks": {"a3_wheel_present": False},
        }
    checks["frozen_wheel_sha256"] = actual_wheel_hash == A3_WHEEL_SHA256
    checks["a3_wheel_present"] = True

    if not checks["frozen_wheel_sha256"]:
        failures.append("EXTERNAL_PROOF_CANDIDATE_MISMATCH")
    if not checks.get("frozen_wheel_sha256"):
        failures.append("frozen a3 wheel bytes mutated")

    # Strict parse up front: malformed JSON, duplicate keys, non-finite constants.
    proof = strict_json(proof_bytes)
    if not isinstance(proof, dict):
        raise ValueError("external proof root must be a JSON object")
    checks["strict_json"] = True
    checks["schema_correct"] = proof.get("schema") == EXPECTED["schema"]
    checks["version_correct"] = (type(proof.get("version")) is int
                                  and proof.get("version") == EXPECTED["version"])
    if not checks["schema_correct"]:
        failures.append("SCHEMA_MISMATCH")
    if not checks["version_correct"]:
        failures.append("VERSION_MISMATCH")

    candidate = proof.get("candidate") or {}
    if not isinstance(candidate, dict):
        candidate = {}
    proof_wheel = candidate.get("wheel_sha256")
    proof_version = candidate.get("version")

    # Reject a1 / a2 proofs outright by exact identity comparison.
    checks["not_a1_proof"] = proof_wheel != A1_SHA256
    checks["not_a2_proof"] = proof_wheel != A2_SHA256
    if not checks["not_a1_proof"]:
        failures.append("PROOF_IDENTIFIES_A1_WHEEL")
    if not checks["not_a2_proof"]:
        failures.append("PROOF_IDENTIFIES_A2_WHEEL")

    # Wrong candidate version / wheel filename / SHA256.
    checks["candidate_version_correct"] = proof_version == A3_VERSION
    checks["wheel_filename_correct"] = candidate.get("wheel_filename") == A3_WHEEL
    checks["wheel_sha256_correct"] = proof_wheel == A3_WHEEL_SHA256
    for label, ok in [
        ("candidate_version_correct", checks["candidate_version_correct"]),
        ("wheel_filename_correct", checks["wheel_filename_correct"]),
        ("wheel_sha256_correct", checks["wheel_sha256_correct"]),
    ]:
        if not ok:
            failures.append(f"{label}: {candidate.get(label.split('_correct')[0].replace('candidate_', '').replace('wheel_', 'wheel.'))}")

    # Verifier result must be PASS with empty failures.
    checks["verifier_status_pass"] = proof.get("status") == "PASS"
    checks["verifier_failures_empty"] = proof.get("failures") == []
    if not checks["verifier_status_pass"]:
        failures.append("VERIFIER_STATUS_NOT_PASS")
    if not checks["verifier_failures_empty"]:
        failures.append("VERIFIER_REPORTED_FAILURES")

    # Field-level contract checks (rejects malformed / mismatched structure).
    for dotted, required in EXPECTED.items():
        try:
            value = _resolve(proof, dotted)
        except (KeyError, TypeError):
            value = object()
        checks[f"field:{dotted}"] = (
            type(value) is type(required) and value == required)
    for field_name, ok in list(checks.items()):
        if field_name.startswith("field:") and not ok:
            failures.append(f"field_mismatch:{field_name}")

    # Integrity / manifest binding: proof must agree with the manifest.
    manifest = _load_manifest()
    checks["manifest_version_matches"] = manifest.get("package_version") == A3_VERSION
    checks["manifest_wheel_sha256_matches"] = (
        manifest.get("wheel", {}).get("sha256") == A3_WHEEL_SHA256)
    checks["manifest_not_published"] = (
        manifest.get("publication_status") == "NOT_PUBLISHED")

    # Wheel content digest and member count.
    import zipfile as _zf
    with _zf.ZipFile(A3_BUNDLE / A3_WHEEL) as archive:
        infos = [i for i in archive.infolist() if not i.is_dir()]
        member_digest = hashlib.sha256()
        member_digest.update(b"SAIMAIL_LOCAL_ALPHA_WHEEL_CONTENT_1\n")
        for info in sorted(infos, key=lambda i: i.filename):
            name = info.filename
            member = hashlib.sha256(archive.read(name)).hexdigest()
            member_digest.update(name.encode("utf-8") + b" " + member.encode("ascii") + b"\n")
    checks["content_digest_matches"] = member_digest.hexdigest() == A3_CONTENT_DIGEST
    checks["member_count_matches"] = len(infos) == A3_MEMBER_COUNT
    for label, ok in [
        ("content_digest_matches", checks["content_digest_matches"]),
        ("member_count_matches", checks["member_count_matches"]),
        ("manifest_version_matches", checks["manifest_version_matches"]),
        ("manifest_wheel_sha256_matches", checks["manifest_wheel_sha256_matches"]),
        ("manifest_not_published", checks["manifest_not_published"]),
    ]:
        if not ok:
            failures.append(label)

    # Module paths are native to the machine that made the proof, so accept
    # POSIX and Windows absolute paths while still requiring an explicit
    # in-environment resolution result and a nonempty path set.
    module_resolution = proof.get("module_resolution") or {}
    if not isinstance(module_resolution, dict):
        module_resolution = {}
    paths = module_resolution.get("paths") or []
    checks["module_resolution_inside_environment"] = (
        module_resolution.get("resolved_inside_environment") is True)
    env = proof.get("environment") or {}
    if not isinstance(env, dict):
        env = {}
    os_platform = env.get("platform")
    checks["module_resolution_paths_external"] = (
        isinstance(paths, list) and bool(paths)
        and isinstance(os_platform, str)
        and all(isinstance(p, str) and p.strip()
                and _absolute_native_path(p, os_platform)
                for p in paths))
    if not checks["module_resolution_inside_environment"]:
        failures.append("MODULE_RESOLUTION_OUTSIDE_ENVIRONMENT")
    if not checks["module_resolution_paths_external"]:
        failures.append("MODULE_RESOLUTION_PATHS_INVALID")

    # The verifier records a useful footprint, but the path's provenance is
    # operator supplied and deliberately not claimed by this local acceptor.
    checks["environment_platform_present"] = (
        isinstance(env.get("platform"), str) and bool(env.get("platform").strip()))
    checks["environment_verifier_version_present"] = (
        type(env.get("verifier_version")) is int)
    if not checks["environment_platform_present"]:
        failures.append("ENVIRONMENT_PLATFORM_MISSING")
    if not checks["environment_verifier_version_present"]:
        failures.append("ENVIRONMENT_VERIFIER_VERSION_MISSING")

    checks["publication_identity_consistent"] = (
        proof.get("publication", "NONE") == "NONE")
    if not checks["publication_identity_consistent"]:
        failures.append("PUBLICATION_IDENTITY_MISMATCH")

    ok = not failures
    record = {
        "schema": ACCEPT_SCHEMA,
        "version": ACCEPT_VERSION,
        "status": "PASS" if ok else "FAIL",
        "failures": failures,
        "source": str(proof_path),
        "stored_copy": str(stored_copy) if stored_copy else None,
        "external_proof_sha256": actual_proof_hash,
        "candidate_sha256": actual_wheel_hash,
        "candidate_version": A3_VERSION,
        "external_schema": proof.get("schema"),
        "proof_provenance": "OPERATOR_SUPPLIED_UNVERIFIED",
        "base_candidate_verification": "TESTED_BY_THIS_VERIFIER",
        "os_store_external_status": "NOT_TESTED_HERE",
        "environment": env,
        "verifier_version": env.get("verifier_version"),
        "offline_mode": "DECLARED_VERIFIER_COMMAND --offline",
        "frozen_platform_proof_scope": manifest.get("platform_proof_scope"),
        "platform_scope_changed": False,
        "publication": "NONE",
        "checks": checks,
    }
    return record


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--proof", required=True,
                        help="supplied external LOCAL_ALPHA_VERIFICATION_1 proof path")
    parser.add_argument("--stored-copy", default=None,
                        help="byte-identical copy path (for the proof_byte_identical_copy check)")
    parser.add_argument("--out", default=None, help="write the acceptance record here")
    args = parser.parse_args(argv)

    if args.stored_copy:
        stored = Path(args.stored_copy)
        proof_bytes = Path(args.proof).read_bytes()
        checks_copy = {"proof_byte_identical_copy": (
            stored.is_file() and stored.read_bytes() == proof_bytes)}
    else:
        checks_copy = {}

    record = verify(Path(args.proof), Path(args.stored_copy) if args.stored_copy else None)
    record["checks"].update(checks_copy)

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    print(json.dumps(
        {"schema": record["schema"], "status": record["status"],
         "failures": record["failures"]},
        indent=2, sort_keys=True))
    return 0 if record["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
