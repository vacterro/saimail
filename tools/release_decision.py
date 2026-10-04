"""D1 release decision packet: bounded decision inputs and decision validation.

Mechanically collects every release surface that can affect release truth
(version identity, artifact identity, frozen-vs-checkout capability, external
proof binding, publication surfaces), and validates one
``SAIMAIL_RELEASE_DECISION_1`` packet against the on-disk facts. Contract:
``spec/21-RELEASE-DECISION-v0.md`` and D-054.

    python tools/release_decision.py inputs --out release/evidence/release_decision_inputs.json
    python tools/release_decision.py verify --packet release/evidence/release_decision.json

Nothing here publishes anything, and no stage authenticates to any service.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INPUTS_SCHEMA = "SAIMAIL_RELEASE_DECISION_INPUTS_1"
DECISION_SCHEMA = "SAIMAIL_RELEASE_DECISION_1"
INPUTS_VERSION = 1
DECISION_VERSION = 1

BUNDLE_DIR = "release/local-alpha"
WHEEL_NAME = "saimail-0.0.2a1-py3-none-any.whl"
MANIFEST_NAME = "local_alpha_candidate.json"
CHECKSUMS_NAME = "SHA256SUMS.txt"
ACCEPTANCE_PATH = "release/evidence/external_proof_acceptance.json"
PROOF_PATH = "release/evidence/SAIMAIL_V2-04_external_linux_verification.json"

ALLOWED_OUTCOMES = (
    "READY_TO_PUBLISH_EXISTING_CANDIDATE",
    "NEW_CANDIDATE_REQUIRED",
    "NO_GO_SECURITY",
    "NO_GO_METADATA",
    "NO_GO_EVIDENCE",
    "NO_GO_OTHER",
)
ALLOWED_CUSTODY_DECISIONS = (
    "KEEP_RAW_DEFAULT",
    "OS_STORE_DEFAULT_WHERE_SUPPORTED",
    "REQUIRE_EXPLICIT_CHOICE",
)
CLAIM_STATES = ("PROVEN", "ABSENT", "NOT_PROVEN", "NOT_APPLICABLE")
REQUIRED_CLAIMS = (
    "package_installability",
    "stable_local_cli",
    "persistent_workspace",
    "send_list_open_restart_dedup",
    "fg05",
    "fg06",
    "external_install",
    "windows_support_evidence",
    "linux_external_evidence",
    "raw_custody",
    "os_store_custody",
    "custody_migration",
    "copied_workspace_protection",
    "zero_runtime_network_model",
    "privacy_checks",
    "integrity_checks",
)
PUBLICATION_STAGES = (
    "LOCAL_CANDIDATE_BUILD",
    "GIT_COMMIT",
    "GIT_TAG",
    "GITHUB_RELEASE",
    "PACKAGE_INDEX_UPLOAD",
)
GATE_IDS = tuple(f"G{index}" for index in range(1, 18))
CANONICAL_README = "README.md"
LOCALE_README_RE = re.compile(r"^README\.[A-Za-z0-9_-]+\.md$")

VERSION_RE = re.compile(r"[0-9]+(?:\.[0-9]+)*(?:[ab][0-9]+)?")
LOCALE_VERSION_RE = re.compile(r"^\*\*v([^*]+)\*\*$", flags=re.MULTILINE)
CANONICAL_VERSION_RE = re.compile(r"\*\*v([0-9][0-9A-Za-z.]*)", flags=re.MULTILINE)
IDENTITY_SCHEMA_RE = re.compile(r"SAIMAIL_LOCAL_IDENTITY_[0-9]+")


class DecisionError(RuntimeError):
    """A named refusal from the release-decision tooling."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code if not detail else f"{code}: {detail}")
        self.code = code
        self.detail = detail


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sibling(name: str):
    if name in sys.modules:
        return sys.modules[name]
    path = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _wheel_text(wheel: Path, member: str) -> str:
    with zipfile.ZipFile(wheel) as archive:
        return archive.read(member).decode("utf-8")


def wheel_facts(wheel: Path) -> dict:
    """Exact frozen-artifact capability facts, read from the wheel itself."""
    lar = _sibling("local_alpha_release")
    names = lar.wheel_members(wheel)
    member_names = [name for name, _hash, _size in names]
    workspace = _wheel_text(wheel, "saimail/workspace.py")
    entrypoint = _wheel_text(wheel, "saimail_local.py")
    return {
        "filename": wheel.name,
        "size_bytes": wheel.stat().st_size,
        "sha256": sha256_file(wheel),
        "content_digest_sha256": lar.wheel_content_digest(names),
        "member_count": len(member_names),
        "wheel_metadata_version": lar.wheel_metadata_version(wheel),
        "has_custody_module": "saimail/custody.py" in member_names,
        "identity_schemas": sorted(set(IDENTITY_SCHEMA_RE.findall(workspace))),
        "cli_custody_commands": "--custody" in entrypoint and "custody" in entrypoint,
        "cli_os_store": "os-store" in entrypoint,
    }


def readme_mirrors(root: Path) -> tuple[str, ...]:
    """The canonical README plus every locale mirror that is actually present.

    ship.md 6b.2 requires the release gate to DISCOVER locale mirrors rather
    than maintain a second hardcoded list of them, and that is what this does.
    The previous constant named README.ee.md and README.ded.md, which the
    translation kitchen has never produced -- it emits README.ja.md and
    README.uk.md -- so the list was wrong before the mirrors were deleted, and
    deleting them turned a stale name into a hard FileNotFoundError inside the
    release gate.
    """
    names = [CANONICAL_README]
    names += sorted(
        path.name for path in root.iterdir()
        if path.is_file() and LOCALE_README_RE.match(path.name)
    )
    return tuple(names)


def version_surfaces(root: Path) -> dict:
    """Every version-bearing surface, as observed; canonical authority is VERSION."""
    import tomllib

    canonical = (root / "VERSION").read_text(encoding="utf-8").strip()
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    api_map = _read_json(root / "lab" / "stable_local_api.json")
    entrypoint = (root / "saimail_local.py").read_text(encoding="utf-8")
    fallback = re.search(r'_VERSION_FALLBACK = "([^"]+)"', entrypoint)
    surfaces = {
        "VERSION": canonical,
        "pyproject.toml": pyproject["project"]["version"],
        "saimail_local.py._VERSION_FALLBACK": fallback.group(1) if fallback else None,
        "lab/stable_local_api.json.release": api_map.get("release"),
    }
    for name in readme_mirrors(root):
        text = (root / name).read_text(encoding="utf-8")
        match = (CANONICAL_VERSION_RE if name == CANONICAL_README
                 else LOCALE_VERSION_RE).search(text)
        surfaces[name] = match.group(1).strip() if match else None
    return {
        "canonical_authority": "VERSION",
        "canonical": canonical,
        "surfaces": surfaces,
        "agreement": all(value == canonical for value in surfaces.values()),
    }


def checkout_facts(root: Path) -> dict:
    workspace = (root / "saimail" / "workspace.py").read_text(encoding="utf-8")
    entrypoint = (root / "saimail_local.py").read_text(encoding="utf-8")
    version = version_surfaces(root)
    return {
        "declared_version": version["canonical"],
        "version_surfaces_agree": version["agreement"],
        "has_custody_module": (root / "saimail" / "custody.py").is_file(),
        "identity_schemas": sorted(set(IDENTITY_SCHEMA_RE.findall(workspace))),
        "cli_custody_commands": "--custody" in entrypoint and "custody" in entrypoint,
        "cli_os_store": "os-store" in entrypoint,
    }


def artifact_facts(root: Path) -> dict:
    """Frozen bundle identity, recomputed and cross-checked against its records."""
    bundle = root / BUNDLE_DIR
    wheel = bundle / WHEEL_NAME
    if not wheel.is_file():
        raise DecisionError("FROZEN_WHEEL_MISSING", str(wheel))
    manifest = _read_json(bundle / MANIFEST_NAME)
    lar = _sibling("local_alpha_release")
    recorded = manifest["wheel"]["sha256"]
    actual = sha256_file(wheel)
    if recorded != actual:
        raise DecisionError("FROZEN_WHEEL_MUTATED", f"{recorded} != {actual}")
    checksums = lar.parse_checksums((bundle / CHECKSUMS_NAME).read_text(encoding="utf-8"))
    checksums_ok = checksums.get(WHEEL_NAME) == actual
    external = {
        "acceptance_path": ACCEPTANCE_PATH,
        "acceptance": _read_json(root / ACCEPTANCE_PATH),
    }
    external["proof_bytes_sha256"] = sha256_file(root / PROOF_PATH)
    external["proof_bytes_match"] = (
        external["proof_bytes_sha256"] == external["acceptance"]["external_proof_sha256"]
    )
    return {
        "bundle_dir": BUNDLE_DIR,
        "manifest_publication_status": manifest["publication_status"],
        "wheel_sha256_actual": actual,
        "wheel_sha256_recorded": recorded,
        "wheel_sha256_agreement": recorded == actual,
        "checksums_include_wheel": checksums_ok,
        "external_proof": external,
    }


def external_proof_applies(acceptance: dict, wheel_sha256: str) -> bool:
    """An external proof is evidence for exactly the wheel bytes it tested."""
    if not wheel_sha256:
        return False
    return acceptance.get("candidate_sha256") == wheel_sha256


def build_decision_inputs(root: Path = ROOT) -> dict:
    version = version_surfaces(root)
    artifact = artifact_facts(root)
    checkout = checkout_facts(root)
    frozen = wheel_facts(root / BUNDLE_DIR / WHEEL_NAME)
    delta = []
    if checkout["has_custody_module"] and not frozen["has_custody_module"]:
        delta.append("V3-01")
    return {
        "schema": INPUTS_SCHEMA,
        "version": INPUTS_VERSION,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "version_identity": version,
        "artifact_identity": artifact,
        "frozen_capability": frozen,
        "checkout_capability": checkout,
        "source_lineage": {
            "post_candidate_source_delta": delta,
            "frozen_classification": "HISTORICAL_VERIFIED_ALPHA",
            "delta_classification": "CURRENT_SOURCE_CAPABILITY",
            "external_evidence_scope": "FROZEN_WHEEL_ONLY",
        },
    }


def publication_allowed(packet: dict, operator_authorization: str | None = None) -> bool:
    """Publication is forbidden unless an explicit operator authorization exists."""
    if operator_authorization is None or not str(operator_authorization).strip():
        return False
    if packet.get("publication_authorization") != "PRESENT":
        return False
    if packet.get("outcome") != "READY_TO_PUBLISH_EXISTING_CANDIDATE":
        return False
    return True


def validate_decision(root: Path, packet: dict) -> dict:
    """Bounded structural validation plus mechanical cross-checks against disk."""
    problems = []
    if packet.get("schema") != DECISION_SCHEMA:
        problems.append(f"schema must be {DECISION_SCHEMA}")
    if packet.get("version") != DECISION_VERSION:
        problems.append(f"version must be {DECISION_VERSION}")
    outcome = packet.get("outcome")
    if outcome not in ALLOWED_OUTCOMES:
        problems.append(f"outcome {outcome!r} is outside the closed set")
    if packet.get("publication") != "NONE":
        problems.append("publication must be NONE in a D1 packet")
    if packet.get("publication_authorization") != "ABSENT":
        problems.append("publication_authorization must be ABSENT unless the operator supplied it")

    inputs = build_decision_inputs(root)
    frozen = packet.get("frozen_artifact", {})
    actual = inputs["frozen_capability"]
    artifact = inputs["artifact_identity"]
    checkout = inputs["checkout_capability"]

    if frozen.get("sha256") != artifact["wheel_sha256_actual"]:
        problems.append("frozen_artifact.sha256 does not match the wheel on disk")
    if frozen.get("member_count") != actual["member_count"]:
        problems.append("frozen_artifact.member_count does not match the wheel")
    if frozen.get("has_custody_module") != actual["has_custody_module"]:
        problems.append("frozen_artifact.has_custody_module does not match the wheel")
    if frozen.get("publication_status") != artifact["manifest_publication_status"]:
        problems.append("frozen_artifact.publication_status does not match the manifest")
    if not artifact["wheel_sha256_agreement"]:
        problems.append("recorded wheel hash no longer matches the wheel bytes")
    if not artifact["external_proof"]["proof_bytes_match"]:
        problems.append("external proof bytes no longer match the recorded proof hash")
    if not external_proof_applies(artifact["external_proof"]["acceptance"],
                                  frozen.get("sha256", "")):
        problems.append("external proof does not bind this exact wheel hash")

    delta = packet.get("current_source_delta", {})
    if delta.get("has_custody_module") != checkout["has_custody_module"]:
        problems.append("current_source_delta.has_custody_module does not match the checkout")
    if delta.get("post_candidate_source_delta") != inputs["source_lineage"]["post_candidate_source_delta"]:
        problems.append("current_source_delta does not match the mechanically detected delta")

    if actual["has_custody_module"] is False:
        if outcome == "READY_TO_PUBLISH_EXISTING_CANDIDATE":
            problems.append("frozen wheel lacks V3-01 custody; READY is refused")
        if outcome == "NEW_CANDIDATE_REQUIRED" and not delta.get("post_candidate_source_delta"):
            problems.append("NEW_CANDIDATE_REQUIRED needs a non-empty post-candidate delta")

    version = packet.get("version_decision", {})
    frozen_version = version.get("current_frozen_artifact_version")
    next_version = version.get("next_candidate_version")
    if frozen_version != actual["wheel_metadata_version"]:
        problems.append("current_frozen_artifact_version does not match wheel metadata")
    if next_version == frozen_version:
        problems.append("next_candidate_version may not equal the frozen artifact version")
    if not (isinstance(next_version, str) and VERSION_RE.fullmatch(next_version)):
        problems.append("next_candidate_version is not a bounded PEP 440-style prerelease")

    custody = packet.get("custody_default_decision", {})
    if custody.get("decision") not in ALLOWED_CUSTODY_DECISIONS:
        problems.append("custody default decision is outside the closed set")

    gates = packet.get("gates", [])
    ids = [gate.get("id") for gate in gates]
    if ids != list(GATE_IDS):
        problems.append("gates must enumerate G1..G17 in order, exactly once")

    claims = packet.get("claims", [])
    seen = [row.get("claim") for row in claims]
    missing = [name for name in REQUIRED_CLAIMS if name not in seen]
    if missing:
        problems.append(f"claims matrix is missing {missing}")
    for row in claims:
        for column in ("frozen_0_0_2a1", "current_checkout", "next_distributable_candidate"):
            if row.get(column) not in CLAIM_STATES:
                problems.append(f"claim {row.get('claim')!r} column {column} has invalid state")
    if frozen.get("has_custody_module") is False:
        for row in claims:
            if row.get("claim") == "os_store_custody" and row.get("frozen_0_0_2a1") != "ABSENT":
                problems.append("os_store_custody may not be attributed to the frozen wheel")

    mechanics = packet.get("publication_mechanics", {})
    stages = [stage.get("stage") for stage in mechanics.get("stages", [])]
    if stages != list(PUBLICATION_STAGES):
        problems.append("publication_mechanics must enumerate the five publication stages")

    return {
        "schema": "SAIMAIL_RELEASE_DECISION_VALIDATION_1",
        "version": 1,
        "status": "PASS" if not problems else "FAIL",
        "outcome": outcome,
        "problems": problems,
    }


def _cmd_inputs(args) -> int:
    inputs = build_decision_inputs(Path(args.root).resolve())
    out = Path(args.out)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(inputs, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "COLLECTED",
        "schema": inputs["schema"],
        "out": str(out) if out else None,
        "version_agreement": inputs["version_identity"]["agreement"],
        "frozen_sha256": inputs["artifact_identity"]["wheel_sha256_actual"],
        "post_candidate_source_delta": inputs["source_lineage"]["post_candidate_source_delta"],
    }, indent=2, sort_keys=True))
    return 0


def _cmd_verify(args) -> int:
    packet = _read_json(Path(args.packet))
    report = validate_decision(Path(args.root).resolve(), packet)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    inputs = sub.add_parser("inputs", help="collect the release-surface inventory")
    inputs.add_argument("--out", required=True)
    inputs.add_argument("--root", default=str(ROOT))
    inputs.set_defaults(func=_cmd_inputs)
    verify = sub.add_parser("verify", help="validate one decision packet against disk")
    verify.add_argument("--packet", required=True)
    verify.add_argument("--root", default=str(ROOT))
    verify.set_defaults(func=_cmd_verify)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except DecisionError as exc:
        print(json.dumps({"status": "REFUSED", "code": exc.code,
                          "detail": exc.detail}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
