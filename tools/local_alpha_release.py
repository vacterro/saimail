"""V2-04 local alpha candidate: build, frozen identity and integrity tooling.

Builds the wheel from the frozen source state, writes the bounded
``LOCAL_ALPHA_CANDIDATE_1`` manifest, checksums, install/limitations README and
the standalone verifier into one candidate bundle, and verifies the bundle's
integrity against the recorded hashes. Contract: ``spec/18-LOCAL-ALPHA-v0.md``
and D-052.

    python tools/local_alpha_release.py build --out release/local-alpha
    python tools/local_alpha_release.py verify --bundle release/local-alpha
    python tools/local_alpha_release.py hash --wheel FILE

This tooling never publishes anything: ``publication_status`` is always
``NOT_PUBLISHED``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CANDIDATE_SCHEMA = "LOCAL_ALPHA_CANDIDATE_1"
CANDIDATE_VERSION = 1
PUBLICATION_STATUS = "NOT_PUBLISHED"
LIMITATIONS_IDENTITY = "LOCAL_ALPHA_LIMITATIONS_1"
VERIFIER_NAME = "verify_local_alpha.py"
VERIFIER_IDENTITY = "LOCAL_ALPHA_VERIFICATION_1"
VERIFIER_VERSION = 1
WHEEL_METADATA_NAME = "METADATA"

ALPHA_SCOPE = (
    "local filesystem messaging only; persistent V2-01 workspaces; explicit "
    "public identity-card exchange; deterministic recipient registration; "
    "current SENV2/PostOffice semantics with duplicate suppression and "
    "explicit open; raw default identity custody with explicit os-store "
    "opt-in (V3-01); the documented saimail-local command workflow"
)
PYTHON_SCOPE = ">=3.11"
PLATFORM_PROOF_SCOPE = (
    "CPython 3.11 on win32 (the host that produced the clean-install and "
    "verification evidence); no broader portability claimed"
)
RESULT_SCHEMAS = {
    "fg05": "LOCAL_SCENARIO_RESULT_1 v1",
    "fg06": "FG06_UTILITY_RESULT_1 v1",
    "v201_command": "LOCAL_WORKSPACE_COMMAND_1 v1",
    "v201_acceptance": "LOCAL_WORKSPACE_RESULT_1 v1",
}
CONTENT_PROOF_IDENTITY = "LOCAL_ALPHA_WHEEL_CONTENT_PROOF_1"
#: D3 additive proof: the accepted post-a2 product delta (P1 + V4-01 + V5-01)
#: must be present in a candidate that claims it. Only evaluated when a build
#: explicitly asks for it, so the frozen a2 custody proof is unchanged.
PRODUCT_DELTA_PROOF_IDENTITY = "LOCAL_ALPHA_WHEEL_PRODUCT_DELTA_PROOF_1"
PRODUCT_DELTA_ALPHA_SCOPE_EXTRA = (
    "local inbox query/triage (P1), explicit local correspondence continuation "
    "(V4-01) and the optional desktop local messenger GUI (V5-01, PySide6 "
    "optional extra; Qt never a base dependency)"
)

#: The D1/D-054 custody truth for a post-V3-01 candidate. Mode-separated on
#: purpose: the raw default and the optional protected mode make different
#: claims and the manifest must not blur them.
CUSTODY_TRUTH = {
    "default": "raw",
    "raw_storage": ("private Ed25519 signing and X25519 decryption software keys "
                    "in workspace identity/identity.json as raw hex; a copied "
                    "workspace directory carries the identity"),
    "os_store_selection": "explicit opt-in: init --custody os-store, or custody migrate",
    "os_store_requires": "the credentials extra (keyring>=24) and a checked persistent backend",
    "protected_workspace_metadata": "handles plus public material only",
    "protected_private_material": ("the OS credential store under "
                                   "credential://saimail-workspace/..."),
    "protects": "workspace-directory-copy exposure",
    "does_not_protect": [
        "malware running as the same OS user",
        "admin/kernel compromise",
        "hardware attack",
        "physical presence",
        "human identity proof",
    ],
    "not_provided": [
        "hardware custody",
        "key rotation",
        "automatic recovery",
        "forward secrecy beyond the existing SENV2 envelope",
    ],
    "os_store_platform_evidence": ("Windows only (WinVaultKeyring classification and "
                                   "one disposable installed-wheel acceptance); no "
                                   "second platform is claimed"),
    "silent_fallback": "never; requested protected custody fails closed with a named CUSTODY_* code",
}
SECURITY_LIMITATIONS = [
    ("raw custody is the default for new workspaces: private software keys are "
     "workspace files, not encrypted at rest"),
    ("os-store custody is an explicit opt-in requiring the credentials extra and "
     "a checked backend; it is not the default"),
    ("no protection is claimed in any mode against same-user malware, "
     "admin/kernel compromise, hardware attack, physical presence or "
     "human-identity proof"),
    ("hardware custody, key rotation and automatic recovery are not provided "
     "for this identity family"),
    ("os-store backend evidence is Windows-specific (WinVaultKeyring) unless new "
     "proof establishes more"),
    ("delivery requires write access to the recipient workspace (shared local "
     "filesystem path, not a network service)"),
    ("no key discovery: both sides must exchange public identity cards "
     "explicitly and register each other"),
    "the alpha is not a production communication service and is not published",
]

#: The frozen pre-V3-01 candidate. It is referenced, never rebuilt or reused:
#: a2 identity is its own wheel SHA-256 and inherits no a1 artifact proof.
HISTORICAL_BUNDLE_DIR = "release/local-alpha"
HISTORICAL_A1 = {
    "version": "0.0.2a1",
    "bundle_dir": HISTORICAL_BUNDLE_DIR,
    "wheel": "saimail-0.0.2a1-py3-none-any.whl",
    "sha256": "ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a",
    "member_count": 57,
    "classification": "HISTORICAL_VERIFIED_ALPHA",
    "publication_status": "NOT_PUBLISHED",
}

#: The frozen post-V3-01 candidate. Also immutable: a later candidate inherits
#: no part of its local, custody, reproducibility or external proof.
HISTORICAL_A2 = {
    "version": "0.0.2a2",
    "bundle_dir": "release/candidates/0.0.2a2",
    "wheel": "saimail-0.0.2a2-py3-none-any.whl",
    "sha256": "d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d",
    "member_count": 59,
    "classification": "HISTORICAL_VERIFIED_ALPHA",
    "publication_status": "NOT_PUBLISHED",
}


class ReleaseError(RuntimeError):
    """A named refusal from the release tooling."""

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


def wheel_members(wheel: Path) -> list:
    """Sorted (name, sha256, size) for every member of one wheel."""
    members = []
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            data = archive.read(info.filename)
            members.append((info.filename, hashlib.sha256(data).hexdigest(), len(data)))
    members.sort(key=lambda item: item[0])
    return members


def wheel_content_digest(members: list) -> str:
    """Domain-separated digest of the wheel's member names and content."""
    digest = hashlib.sha256()
    digest.update(b"SAIMAIL_LOCAL_ALPHA_WHEEL_CONTENT_1\n")
    for name, member_hash, _size in members:
        digest.update(name.encode("utf-8") + b" " + member_hash.encode("ascii") + b"\n")
    return digest.hexdigest()


def wheel_metadata_version(wheel: Path) -> str:
    with zipfile.ZipFile(wheel) as archive:
        for info in archive.infolist():
            if info.filename.endswith(f".dist-info/{WHEEL_METADATA_NAME}"):
                for line in archive.read(info.filename).decode("utf-8").splitlines():
                    if line.startswith("Version:"):
                        return line.split(":", 1)[1].strip()
    raise ReleaseError("WHEEL_METADATA_MISSING", str(wheel))


def wheel_product_delta_proof(wheel: Path) -> dict:
    """Mechanically prove the accepted post-a2 product delta inside one wheel.

    Reads the wheel's own members only (never the checkout): P1 inbox query,
    V4-01 correspondence continuation and V5-01 desktop GUI modules plus the
    ``saimail-gui`` console entrypoint and the optional ``gui`` extra. PySide6
    must be declared for the ``gui`` extra and must never appear in the core
    requirements.
    """
    with zipfile.ZipFile(wheel) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        names = {info.filename for info in infos}

        def _text(member: str) -> str:
            if not member or member not in names:
                return ""
            return archive.read(member).decode("utf-8", errors="replace")

        entry_points = _text(next(
            (i.filename for i in infos if i.filename.endswith(".dist-info/entry_points.txt")),
            ""))
        metadata = _text(next(
            (i.filename for i in infos if i.filename.endswith(".dist-info/METADATA")), ""))
        workspace_source = _text("saimail/workspace.py")
        cli_source = _text("saimail_local.py")

    requires = [line for line in metadata.splitlines() if line.startswith("Requires-Dist:")]
    core_requires = [line for line in requires if "extra ==" not in line]
    checks = {
        "p1_inbox_query_module": "saimail/inbox_query.py" in names,
        "p1_query_projection": ("query_inbox" in workspace_source
                                 or "query_inbox" in cli_source),
        "p1_cli_inbox_filters": ("inbox" in cli_source and "from_seat" in cli_source),
        "v401_correspondence_continuation": "reply_message" in workspace_source,
        "v401_cli_reply": ("reply" in cli_source and "reply_message" in cli_source),
        "v501_gui_adapter": "saimail/gui_adapter.py" in names,
        "v501_gui_app": "saimail/gui_app.py" in names,
        "v501_gui_theme": "saimail/gui_theme.py" in names,
        "v501_gui_entrypoint": "saimail-gui" in entry_points,
        "v501_gui_extra_declares_pyside6": any(
            "PySide6" in line and 'extra == "gui"' in line for line in requires),
        "pyside6_not_core_dependency": not any("PySide6" in line for line in core_requires),
    }
    failures = [name for name, ok in checks.items() if not ok]
    return {
        "schema": PRODUCT_DELTA_PROOF_IDENTITY,
        "version": 1,
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
    }


def wheel_content_proof(wheel: Path, *, require_product_delta: bool = False) -> dict:
    """Mechanically prove the intended current-source features inside one wheel.

    Reads the wheel's own members and fails closed: a candidate whose bundled
    sources lack the V3-01 custody surface (module, identity schema v2, CLI
    ``--custody``/``custody status``/``custody migrate``) or the D-054 first-run
    notice cannot be built or shipped. With ``require_product_delta`` the
    accepted post-a2 product surface (P1 + V4-01 + V5-01) is proven too; the
    frozen a2 candidate is verified with the default (custody only).
    """
    with zipfile.ZipFile(wheel) as archive:
        names = {info.filename for info in archive.infolist() if not info.is_dir()}

        def _member_text(member: str) -> str:
            if member not in names:
                return ""
            return archive.read(member).decode("utf-8", errors="replace")

        custody_source = _member_text("saimail/custody.py")
        workspace_source = _member_text("saimail/workspace.py")
        cli_source = _member_text("saimail_local.py")
    checks = {
        "custody_module": "saimail/custody.py" in names,
        "workspace_module": "saimail/workspace.py" in names,
        "identity_schema_v2": "SAIMAIL_LOCAL_IDENTITY_2" in workspace_source,
        "os_store_mode": ("CUSTODY_OS_STORE" in custody_source
                          and "os-store" in custody_source),
        "cli_custody_flag": "--custody" in cli_source,
        "cli_custody_status": "custody_status" in cli_source,
        "cli_custody_migrate": "migrate_workspace_custody" in cli_source,
        "first_run_notice": "RAW_CUSTODY_DEFAULT" in workspace_source,
    }
    product_delta = None
    if require_product_delta:
        product_delta = wheel_product_delta_proof(wheel)
        checks.update(product_delta["checks"])
    failures = [name for name, ok in checks.items() if not ok]
    return {
        "schema": CONTENT_PROOF_IDENTITY,
        "version": 1,
        "status": "PASS" if not failures else "FAIL",
        "checks": checks,
        "failures": failures,
        "product_delta": product_delta,
    }


def verify_historical_a1(source_root: Path = ROOT) -> dict:
    """Recompute the frozen a1 identity without touching it. Never rebuilds."""
    bundle = Path(source_root) / HISTORICAL_BUNDLE_DIR
    wheel = bundle / HISTORICAL_A1["wheel"]
    checks = {"wheel_present": wheel.is_file()}
    failures = [] if checks["wheel_present"] else ["wheel missing"]
    actual_hash = None
    if checks["wheel_present"]:
        actual_hash = sha256_file(wheel)
        checks["wheel_sha256_matches"] = actual_hash == HISTORICAL_A1["sha256"]
        if not checks["wheel_sha256_matches"]:
            failures.append("wheel sha256 differs from the frozen a1 identity")
        checks["member_count_matches"] = (
            len(wheel_members(wheel)) == HISTORICAL_A1["member_count"])
        if not checks["member_count_matches"]:
            failures.append("wheel member count differs from the frozen a1 identity")
        manifest_path = bundle / "local_alpha_candidate.json"
        checks["manifest_present"] = manifest_path.is_file()
        if checks["manifest_present"]:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            checks["manifest_version_is_a1"] = (
                manifest.get("package_version") == HISTORICAL_A1["version"])
            checks["manifest_wheel_hash_matches"] = (
                manifest.get("wheel", {}).get("sha256") == HISTORICAL_A1["sha256"])
            checks["publication_not_published"] = (
                manifest.get("publication_status") == "NOT_PUBLISHED")
            for key in ("manifest_version_is_a1", "manifest_wheel_hash_matches",
                        "publication_not_published"):
                if not checks[key]:
                    failures.append(f"{key} is false")
    return {
        "schema": "LOCAL_ALPHA_HISTORICAL_A1_1",
        "version": 1,
        "status": "PASS" if not failures else "FAIL",
        "bundle_dir": HISTORICAL_BUNDLE_DIR,
        "wheel": HISTORICAL_A1["wheel"],
        "expected_sha256": HISTORICAL_A1["sha256"],
        "actual_sha256": actual_hash,
        "checks": checks,
        "failures": failures,
    }


def _verify_historical(source_root: Path, spec: dict, label: str) -> dict:
    """Recompute a frozen candidate identity without touching it. Never rebuilds."""
    bundle = Path(source_root) / spec["bundle_dir"]
    wheel = bundle / spec["wheel"]
    checks = {"wheel_present": wheel.is_file()}
    failures = [] if checks["wheel_present"] else ["wheel missing"]
    actual_hash = None
    if checks["wheel_present"]:
        actual_hash = sha256_file(wheel)
        checks["wheel_sha256_matches"] = actual_hash == spec["sha256"]
        if not checks["wheel_sha256_matches"]:
            failures.append(f"wheel sha256 differs from the frozen {label} identity")
        checks["member_count_matches"] = (
            len(wheel_members(wheel)) == spec["member_count"])
        if not checks["member_count_matches"]:
            failures.append(f"wheel member count differs from the frozen {label} identity")
        manifest_path = bundle / "local_alpha_candidate.json"
        checks["manifest_present"] = manifest_path.is_file()
        if checks["manifest_present"]:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            checks["manifest_version_matches"] = (
                manifest.get("package_version") == spec["version"])
            checks["manifest_wheel_hash_matches"] = (
                manifest.get("wheel", {}).get("sha256") == spec["sha256"])
            checks["publication_not_published"] = (
                manifest.get("publication_status") == "NOT_PUBLISHED")
            for key in ("manifest_version_matches", "manifest_wheel_hash_matches",
                        "publication_not_published"):
                if not checks[key]:
                    failures.append(f"{key} is false")
    return {
        "schema": f"LOCAL_ALPHA_HISTORICAL_{label.upper()}_1",
        "version": 1,
        "status": "PASS" if not failures else "FAIL",
        "bundle_dir": spec["bundle_dir"],
        "wheel": spec["wheel"],
        "expected_sha256": spec["sha256"],
        "actual_sha256": actual_hash,
        "checks": checks,
        "failures": failures,
    }


def verify_historical_a2(source_root: Path = ROOT) -> dict:
    """Recompute the frozen a2 identity without touching it. Never rebuilds."""
    return _verify_historical(source_root, HISTORICAL_A2, "a2")


def project_version(source_root: Path) -> str:
    version_file = source_root / "VERSION"
    if not version_file.is_file():
        raise ReleaseError("VERSION_FILE_MISSING", str(version_file))
    version = version_file.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)*(?:[ab][0-9]+)?", version):
        raise ReleaseError("VERSION_MALFORMED", version)
    return version


def git_identity(source_root: Path) -> dict:
    try:
        head = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False)
        status = subprocess.run(
            ["git", "-C", str(source_root), "status", "--porcelain"],
            capture_output=True, text=True, check=False)
    except OSError as exc:
        return {"git_head": None, "git_dirty": None, "note": f"git unavailable: {exc}"}
    if head.returncode != 0:
        return {"git_head": None, "git_dirty": None, "note": "no git HEAD at the source root"}
    dirty = bool(status.stdout.strip())
    return {
        "git_head": head.stdout.strip(),
        "git_dirty": dirty,
        "note": ("the worktree is dirty; no commit uniquely identifies this candidate, "
                 "so the exact wheel SHA-256 is the candidate identity"),
    }


def build_wheel(source_root: Path, outdir: Path) -> Path:
    completed = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation",
         "--outdir", str(outdir), str(source_root)],
        cwd=str(outdir), capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ReleaseError(
            "WHEEL_BUILD_FAILED", (completed.stdout + completed.stderr).strip()[-800:])
    wheels = sorted(outdir.glob("*.whl"))
    if len(wheels) != 1:
        raise ReleaseError("WHEEL_BUILD_AMBIGUOUS", f"{[w.name for w in wheels]}")
    return wheels[0]


def make_manifest(wheel: Path, source_root: Path, *, created_utc: str | None = None,
                  require_product_delta: bool = False) -> dict:
    version = project_version(source_root)
    metadata_version = wheel_metadata_version(wheel)
    if metadata_version != version:
        raise ReleaseError(
            "VERSION_SURFACE_MISMATCH",
            f"wheel metadata {metadata_version!r} != VERSION {version!r}")
    members = wheel_members(wheel)
    content_digest = wheel_content_digest(members)
    content_proof = wheel_content_proof(wheel, require_product_delta=require_product_delta)
    if content_proof["status"] != "PASS":
        raise ReleaseError(
            "CANDIDATE_CONTENT_PROOF_FAILED", ", ".join(content_proof["failures"]))
    created = created_utc or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    alpha_scope = ALPHA_SCOPE
    if require_product_delta:
        alpha_scope = f"{ALPHA_SCOPE}; {PRODUCT_DELTA_ALPHA_SCOPE_EXTRA}"
    manifest = {
        "schema": CANDIDATE_SCHEMA,
        "version": CANDIDATE_VERSION,
        "package_name": "saimail",
        "package_version": version,
        "alpha_scope": alpha_scope,
        "python_scope": PYTHON_SCOPE,
        "platform_proof_scope": PLATFORM_PROOF_SCOPE,
        "created_utc": created,
        "wheel": {
            "filename": wheel.name,
            "size_bytes": wheel.stat().st_size,
            "sha256": sha256_file(wheel),
            "content_digest_sha256": content_digest,
            "member_count": len(members),
        },
        "source_identity": dict(git_identity(source_root), package_version_source="VERSION"),
        "result_schemas": dict(RESULT_SCHEMAS),
        "content_proof": content_proof,
        "custody": dict(CUSTODY_TRUTH),
        "verification": {
            "procedure": VERIFIER_NAME,
            "identity": f"{VERIFIER_IDENTITY} v{VERIFIER_VERSION}",
            "verifier_version": VERIFIER_VERSION,
        },
        "limitations": {
            "identity": LIMITATIONS_IDENTITY,
            "reference": "README-LOCAL-ALPHA.md#limitations-and-security",
            "utility_verdict": "UTILITY_CONDITIONAL",
        },
        "security_limitations": list(SECURITY_LIMITATIONS),
        "zero_runtime_network_expected": True,
        "zero_model_calls_expected": True,
        "publication_status": PUBLICATION_STATUS,
    }
    if version != HISTORICAL_A1["version"]:
        manifest["historical_candidate_a1"] = {
            "version": HISTORICAL_A1["version"],
            "bundle_dir": HISTORICAL_A1["bundle_dir"],
            "wheel": HISTORICAL_A1["wheel"],
            "sha256": HISTORICAL_A1["sha256"],
            "classification": HISTORICAL_A1["classification"],
            "publication_status": HISTORICAL_A1["publication_status"],
            "note": ("immutable historical artifact; its external proof binds its own "
                     "wheel bytes only and is never inherited by this candidate"),
        }
    if version not in (HISTORICAL_A1["version"], HISTORICAL_A2["version"]):
        manifest["historical_candidate_a2"] = {
            "version": HISTORICAL_A2["version"],
            "bundle_dir": HISTORICAL_A2["bundle_dir"],
            "wheel": HISTORICAL_A2["wheel"],
            "sha256": HISTORICAL_A2["sha256"],
            "classification": HISTORICAL_A2["classification"],
            "publication_status": HISTORICAL_A2["publication_status"],
            "note": ("immutable historical artifact; its local, custody, reproducibility "
                     "and external proof bind its own wheel bytes only and are never "
                     "inherited by this candidate"),
        }
    return manifest


def bundle_readme(manifest: dict) -> str:
    version = manifest["package_version"]
    wheel_name = manifest["wheel"]["filename"]
    wheel_hash = manifest["wheel"]["sha256"]
    product = (manifest.get("content_proof") or {}).get("product_delta")
    product_extra = ""
    if product and product.get("status") == "PASS":
        product_extra = """
## Post-a2 product delta (P1 + V4-01 + V5-01)

This candidate additionally ships the accepted post-`0.0.2a2` product surface,
proven present in this exact wheel by the manifest
`content_proof.product_delta` block (never inferred from the checkout):

* **P1** — metadata-only local inbox query/triage (`saimail-local inbox` with
  bounded AND-only filters and a validated byte-offset cursor);
* **V4-01** — explicit local correspondence continuation (`saimail-local reply`,
  recipient resolved from the original sender; target must already be `READ`);
* **V5-01** — the desktop local messenger alpha (`saimail-gui`), shipped behind
  the optional `gui` extra. PySide6 is never a base dependency, the base install
  works without Qt, and `saimail-local` stays Qt-free.
"""
    return f"""# SAIMAIL local alpha candidate {version}

Scoped **local** alpha candidate with the V3-01 identity custody modes. Built
and hashed, **NOT PUBLISHED**.

## Install

```
python -m venv venv
venv\\Scripts\\activate            (POSIX: source venv/bin/activate)
pip install "{wheel_name}[crypto]"
saimail-local --version           # must print saimail {version}
```

`cryptography` is the one runtime extra the local workflow needs. Protected
`os-store` custody additionally needs the `credentials` extra
(`pip install "{wheel_name}[crypto,credentials]"`). If the machine has no
package index access, either install the extras first from local wheels or a
`--system-site-packages` environment, or run the verifier with `--offline`
when the host interpreter already provides them; dependency installation is
separate from SAIMAIL runtime network activity, which is zero.

## Verify

```
python verify_local_alpha.py --bundle . --out verification [--offline]
```

Writes `verification/local_alpha_verification.json` with schema
`LOCAL_ALPHA_VERIFICATION_1` v1 and status `PASS` / `FAIL` / `BLOCKED`.
Integrity is checked against this bundle's `SHA256SUMS.txt` and the manifest's
wheel SHA-256 before anything is installed:

```
sha256 wheel: {wheel_hash}
```

The bundled verifier proves the **base** candidate on any supported host. It
does not test `os-store` custody: that backend is platform-specific and its
evidence is Windows-only in this candidate (see the limitations below).

## What works

* install the package and run `saimail-local --version`, `--api-map`,
  `--demo`, `--utility`;
* initialize persistent workspaces and exchange public identity cards;
* register a known local peer explicitly;
* local send -> inbox list (metadata only) -> explicit open;
* duplicate suppression of an exact replay, restart persistence;
* raw (default) identity custody and the explicit `init --custody os-store`
  protected mode where a checked OS credential backend exists
  (`custody status`, `custody migrate`); the first-run result of a new
  workspace carries the bounded custody notice;
* FG-05 demo (`LOCAL_SCENARIO_RESULT_1`) and FG-06 benchmark
  (`FG06_UTILITY_RESULT_1`) with machine-readable results;
* V2-01 acceptance harness (`LOCAL_WORKSPACE_RESULT_1`).
{product_extra}
## What does not exist

Remote delivery, email-provider integration, a server or daemon, account
synchronization, automatic recipient discovery, a protected default, hardware
custody, key rotation, automatic recovery, automatic correspondence, and any
general-purpose secure-messenger claim.

## Limitations and security

**Raw custody (default).** New workspaces store their private Ed25519/X25519
identity keys as raw software key files in `identity/identity.json`, protected
only by their file location (owner-only mode requested where the OS honours
it). A copied workspace directory copies the identity. No encryption at rest,
no rotation.

**os-store custody (explicit opt-in).** `init --custody os-store` (or
`custody migrate`) keeps only handles and public material in the workspace and
stores the private keys in the OS credential store under
`credential://saimail-workspace/...`, where a checked persistent backend
exists. It protects against workspace-directory-copy exposure **only**. It
does not protect against malware running as the same OS user, admin/kernel
compromise, hardware attack, physical presence or human-identity proof, and
it provides no hardware custody, key rotation or automatic recovery. A
requested protected custody never silently falls back to raw; a missing or
unsuitable store fails closed with a named `CUSTODY_*` code. Backend evidence
for this candidate is Windows-specific (`WinVaultKeyring`).

**Other limits.** Delivery is an explicit path to the recipient workspace; the
sender needs write access to it, and a shared local path is not network
messaging. Both sides must exchange public identity cards and register each
other; there is no automatic discovery. Utility is `UTILITY_CONDITIONAL`: a
measured cost win at low open rate, neutral at moderate/high and
fallback-heavy workloads. The demonstrated platform is CPython 3.11 on win32;
broader portability is not claimed.

## Publication status

`publication_status = NOT_PUBLISHED`. This bundle was built, hashed and
locally verified. Nothing here has been pushed, tagged, uploaded or announced;
publication is a separate explicit operator action. See
`spec/18-LOCAL-ALPHA-v0.md`, `spec/20-LOCAL-KEY-CUSTODY-v0.md` and
D-052 / D-053 / D-054 in the source repository for the full contract. The
pre-V3-01 `0.0.2a1` candidate remains a separate historical artifact
(`release/local-alpha/`) and its external proof is never inherited here.
"""


def checksums_text(bundle_dir: Path) -> str:
    lines = []
    for path in sorted(bundle_dir.iterdir()):
        if path.name in ("SHA256SUMS.txt", "checksums.tmp"):
            continue
        if not path.is_file():
            continue
        lines.append(f"{sha256_file(path)}  {path.name}")
    return "\n".join(lines) + "\n"


def _refuse_protected_destination(source_root: Path, out_root: Path) -> None:
    """A frozen bundle is evidence, never a mutable 'latest' location.

    Two refusals: the historical a1 bundle path is closed to new builds, and an
    output directory that already holds a candidate manifest is never
    overwritten (a re-build needs a new, identity-bearing directory).
    """
    resolved = out_root.resolve()
    protected = (Path(source_root) / HISTORICAL_BUNDLE_DIR).resolve()
    if resolved == protected:
        raise ReleaseError(
            "HISTORICAL_BUNDLE_PROTECTED",
            f"{HISTORICAL_BUNDLE_DIR} holds the frozen 0.0.2a1 candidate; build a new "
            f"candidate into its own directory")
    if (out_root / "local_alpha_candidate.json").is_file():
        raise ReleaseError(
            "BUNDLE_ALREADY_FROZEN",
            f"{out_root} already holds a candidate bundle; a frozen candidate is never "
            f"overwritten")


def build_candidate(source_root: Path, out_root: Path, *, wheel: Path | None = None,
                    require_product_delta: bool = False) -> dict:
    _refuse_protected_destination(source_root, out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    if wheel is None:
        with tempfile.TemporaryDirectory(prefix="saimail-alpha-build-") as tmp:
            wheel_path = build_wheel(source_root, Path(tmp))
            staged = out_root / wheel_path.name
            shutil.copyfile(wheel_path, staged)
    else:
        staged = out_root / wheel.name
        if wheel.resolve() != staged.resolve():
            shutil.copyfile(wheel, staged)
    verifier_source = source_root / "tools" / VERIFIER_NAME
    if not verifier_source.is_file():
        raise ReleaseError("VERIFIER_MISSING", str(verifier_source))
    shutil.copyfile(verifier_source, out_root / VERIFIER_NAME)
    manifest = make_manifest(staged, source_root,
                             require_product_delta=require_product_delta)
    (out_root / "local_alpha_candidate.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out_root / "README-LOCAL-ALPHA.md").write_text(bundle_readme(manifest), encoding="utf-8")
    (out_root / "SHA256SUMS.txt").write_text(checksums_text(out_root), encoding="utf-8")
    return manifest


def parse_checksums(text: str) -> dict:
    entries = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ReleaseError("CHECKSUMS_MALFORMED", line[:120])
        entries[match.group(2)] = match.group(1)
    return entries


def verify_bundle_integrity(bundle_dir: Path, *, source_root: Path | None = None) -> dict:
    """Reject any wheel/recorded-hash disagreement. Returns a bounded report.

    ``source_root`` couples the bundle's declared version to that source tree's
    VERSION (the current-candidate reading). Without it the bundle is verified
    against its own recorded identity only — the historical reading, so a
    frozen candidate stays verifiable after the source moves on.
    """
    checks = {"manifest_ok": False, "wheel_hash_ok": False,
              "wheel_content_digest_ok": False, "checksums_ok": False}
    failures = []
    checksum_failures = []
    manifest_path = bundle_dir / "local_alpha_candidate.json"
    if not manifest_path.is_file():
        raise ReleaseError("MANIFEST_MISSING", str(manifest_path))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != CANDIDATE_SCHEMA or manifest.get("version") != CANDIDATE_VERSION:
        raise ReleaseError("MANIFEST_SCHEMA_MISMATCH", str(manifest.get("schema")))
    checks["manifest_ok"] = True

    if source_root is not None:
        expected_version = project_version(source_root)
        if manifest.get("package_version") != expected_version:
            failures.append(
                f"manifest version {manifest.get('package_version')} != VERSION {expected_version}")
        checks["version_surface_ok"] = not failures

    wheel_path = bundle_dir / manifest["wheel"]["filename"]
    if not wheel_path.is_file():
        raise ReleaseError("WHEEL_MISSING", str(wheel_path))
    actual_size = wheel_path.stat().st_size
    actual_hash = sha256_file(wheel_path)
    if actual_size != manifest["wheel"]["size_bytes"]:
        failures.append(f"wheel size {actual_size} != manifest {manifest['wheel']['size_bytes']}")
    if actual_hash != manifest["wheel"]["sha256"]:
        failures.append(f"wheel sha256 {actual_hash} != manifest {manifest['wheel']['sha256']}")
    checks["wheel_hash_ok"] = actual_hash == manifest["wheel"]["sha256"]

    members = wheel_members(wheel_path)
    actual_digest = wheel_content_digest(members)
    if actual_digest != manifest["wheel"]["content_digest_sha256"]:
        failures.append("wheel content digest mismatch")
    checks["wheel_content_digest_ok"] = actual_digest == manifest["wheel"]["content_digest_sha256"]
    if len(members) != manifest["wheel"].get("member_count"):
        failures.append("wheel member count mismatch")

    metadata_version = wheel_metadata_version(wheel_path)
    if metadata_version != manifest["package_version"]:
        failures.append(f"wheel metadata version {metadata_version} != {manifest['package_version']}")
    checks.setdefault("version_surface_ok", metadata_version == manifest["package_version"])

    sums_path = bundle_dir / "SHA256SUMS.txt"
    if not sums_path.is_file():
        raise ReleaseError("CHECKSUMS_MISSING", str(sums_path))
    entries = parse_checksums(sums_path.read_text(encoding="utf-8"))
    for name, expected in sorted(entries.items()):
        path = bundle_dir / name
        if not path.is_file():
            checksum_failures.append(f"checksums name {name} is not in the bundle")
            continue
        actual = sha256_file(path)
        if actual != expected:
            checksum_failures.append(f"checksums mismatch for {name}")
    expected_names = {p.name for p in bundle_dir.iterdir()
                      if p.is_file() and p.name != "SHA256SUMS.txt"}
    missing = expected_names - set(entries)
    extra = set(entries) - expected_names
    if missing:
        checksum_failures.append(f"checksums missing entries: {sorted(missing)}")
    if extra:
        checksum_failures.append(f"checksums unknown entries: {sorted(extra)}")
    checks["checksums_ok"] = not checksum_failures
    failures.extend(checksum_failures)

    return {
        "schema": "LOCAL_ALPHA_INTEGRITY_1",
        "version": 1,
        "status": "PASS" if not failures else "FAIL",
        "candidate_version": manifest.get("package_version"),
        "wheel_filename": manifest["wheel"]["filename"],
        "wheel_sha256": actual_hash,
        "checks": checks,
        "failures": failures,
    }


def _cmd_build(args) -> int:
    out_root = Path(args.out)
    manifest = build_candidate(Path(args.source).resolve(), out_root, wheel=(
        Path(args.wheel).resolve() if args.wheel else None),
        require_product_delta=getattr(args, "require_product_delta", False))
    print(json.dumps({
        "status": "BUILT",
        "bundle": str(out_root),
        "candidate_version": manifest["package_version"],
        "wheel": manifest["wheel"],
        "content_proof": manifest["content_proof"]["status"],
        "publication_status": manifest["publication_status"],
    }, indent=2, sort_keys=True))
    return 0


def _cmd_verify(args) -> int:
    bundle = Path(args.bundle)
    manifest_path = bundle / "local_alpha_candidate.json"
    bundle_version = None
    if manifest_path.is_file():
        bundle_version = json.loads(
            manifest_path.read_text(encoding="utf-8")).get("package_version")
    historical = bundle_version != project_version(ROOT)
    report = verify_bundle_integrity(bundle, source_root=None if historical else ROOT)
    report["bundle_version"] = bundle_version
    report["current_version"] = project_version(ROOT)
    report["historical"] = historical
    if historical and bundle.resolve() == (ROOT / HISTORICAL_BUNDLE_DIR).resolve():
        report["historical_a1"] = verify_historical_a1(ROOT)
        if report["historical_a1"]["status"] != "PASS":
            report["status"] = "FAIL"
    elif historical and bundle.resolve() == (
            ROOT / HISTORICAL_A2["bundle_dir"]).resolve():
        report["historical_a2"] = verify_historical_a2(ROOT)
        if report["historical_a2"]["status"] != "PASS":
            report["status"] = "FAIL"
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "PASS" else 1


def _cmd_hash(args) -> int:
    path = Path(args.wheel)
    print(json.dumps({
        "wheel": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "content_digest_sha256": wheel_content_digest(wheel_members(path)),
    }, indent=2, sort_keys=True))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="build one candidate bundle")
    build.add_argument("--out", required=True, help="bundle output directory")
    build.add_argument("--source", default=str(ROOT), help="source root (default: repository)")
    build.add_argument("--wheel", default=None, help="reuse an existing wheel instead of building")
    build.add_argument("--require-product-delta", action="store_true",
                       help="also prove the accepted post-a2 product surface "
                            "(P1 + V4-01 + V5-01) inside the built wheel")
    build.set_defaults(func=_cmd_build)
    verify = sub.add_parser("verify", help="verify bundle integrity against recorded hashes")
    verify.add_argument("--bundle", required=True)
    verify.set_defaults(func=_cmd_verify)
    hash_cmd = sub.add_parser("hash", help="print wheel hashes")
    hash_cmd.add_argument("--wheel", required=True)
    hash_cmd.set_defaults(func=_cmd_hash)
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ReleaseError as exc:
        print(json.dumps({"status": "REFUSED", "code": exc.code,
                          "detail": exc.detail}, indent=2, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
