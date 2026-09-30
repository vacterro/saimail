"""D2 installed-wheel proof: Windows os-store custody and raw->os-store migration.

Runs on the supported Windows host only. Verifies a frozen candidate bundle,
installs the exact wheel into a fresh virtual environment **outside the
checkout**, proves that modules resolve inside that environment, and then
executes one bounded disposable acceptance against the real Windows credential
store (``WinVaultKeyring``) plus one fingerprint-preserving migration proof with
an injected durable in-memory store.

The real-store acceptance uses a unique test-only seat and the dedicated
``credential://saimail-workspace/...`` namespace, deletes every entry it created
and re-checks absence. Residue is reported, never hidden. No private key value
is ever written to the evidence file; the driver prints counts and fingerprints
only.

    python tools/prove_a2_windows_os_store.py --bundle release/candidates/0.0.2a2 \
        --out release/evidence/a2/windows_os_store_proof.json

Evidence schema: ``SAIMAIL_A2_WINDOWS_OS_STORE_PROOF_1`` v1. Nothing here
publishes anything.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROOF_SCHEMA = "SAIMAIL_A2_WINDOWS_OS_STORE_PROOF_1"
PROOF_VERSION = 1
EXPECTED_BACKEND = "keyring.backends.Windows.WinVaultKeyring"

DRIVER_SOURCE = r'''
"""Disposable installed-wheel driver. Prints exactly one JSON document."""
import json
import platform
import shutil
import sys
from pathlib import Path

from saimail import custody, workspace
from saimail.credentials import BackendError, get_credential_store
from sailang import SailangError


class _MemoryStore:
    """Durable in-process store used for the migration proof (no real vault)."""

    def __init__(self, fail_on=()):
        self.data = {}
        self._fail_on = set(fail_on)

    def check_backend(self):
        return "in-memory-durable-test-store"

    def get(self, handle):
        if "get" in self._fail_on:
            raise BackendError("injected read failure")
        return self.data.get(handle)

    def set(self, handle, value):
        if "set" in self._fail_on:
            raise BackendError("injected write failure")
        self.data[handle] = value

    def delete(self, handle):
        self.data.pop(handle, None)


def _run():
    result = {"checks": {}, "errors": [], "residue": []}
    result["python_version"] = platform.python_version()
    result["platform"] = sys.platform
    import saimail
    import sailang
    import saimail_local
    result["module_files"] = {"saimail": saimail.__file__,
                              "sailang": sailang.__file__,
                              "saimail_local": saimail_local.__file__}

    base = Path(sys.argv[1])
    seat = sys.argv[2]
    seal = sys.argv[3]
    checks = result["checks"]
    checks["platform_windows"] = sys.platform == "win32"

    store = get_credential_store()
    result["backend"] = custody.classify_backend(store)
    checks["backend_is_winvault"] = result["backend"] == sys.argv[4]

    protected = base / "protected"
    raw_peer = base / "raw-peer"
    protected_handles = []
    try:
        created = workspace.init_workspace(protected, seat=seat,
                                           custody=custody.CUSTODY_OS_STORE, store=store)
        checks["protected_init_created"] = created.get("status") == workspace.CREATED
        checks["protected_notice_is_os_store"] = [
            n.get("id") for n in created.get("notices") or []] == ["OS_STORE_CUSTODY"]
        checks["protected_label"] = (created.get("identity") or {}).get("custody") == "os-store"
        loaded = workspace.load_workspace(protected, store=store)
        protected_handles = [
            custody.handle_for(loaded.seat, custody.ROLE_SENDER, loaded.sender_kid),
            custody.handle_for(loaded.seat, custody.ROLE_RECIPIENT, loaded.recipient_kid)]
        result["identity"] = {"seat": loaded.seat, "sender_kid": loaded.sender_kid,
                              "recipient_kid": loaded.recipient_kid}

        identity_path = protected / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME
        identity = json.loads(identity_path.read_text(encoding="utf-8"))
        checks["identity_schema_v2"] = identity.get("schema") == workspace.IDENTITY_SCHEMA_V2
        checks["identity_version_v2"] = identity.get("version") == workspace.IDENTITY_VERSION_V2
        checks["no_raw_private_fields"] = not any(
            field in identity for field in ("sender_private_key", "recipient_private_key"))

        stored_values = [custody.read_key(store, handle) for handle in protected_handles]
        checks["store_holds_both_keys"] = len(stored_values) == 2 and all(stored_values)
        hits = []
        for path in protected.rglob("*"):
            if path.is_file():
                blob = path.read_bytes()
                hits.extend(handle for handle in protected_handles
                            if handle.encode("utf-8") in blob
                            and path.name != workspace.IDENTITY_NAME)
                for value in stored_values:
                    if value.encode("utf-8") in blob:
                        hits.append(value[:8] + "...")
        checks["no_private_material_in_workspace"] = hits == []
        result["private_material_hits"] = hits

        card = workspace.identity_card(loaded)
        checks["public_fingerprints_valid"] = (
            card["sender_kid"] == loaded.sender_kid
            and card["recipient_kid"] == loaded.recipient_kid
            and "private" not in json.dumps(card))

        again = workspace.load_workspace(protected, store=store)
        checks["restart_load_stable"] = (
            again.sender_kid == loaded.sender_kid
            and again.recipient_kid == loaded.recipient_kid)

        status = workspace.custody_status(protected, store=store)
        checks["custody_status_protected"] = (
            status.get("custody", {}).get("mode") == "os-store"
            and status.get("custody", {}).get("loadable") is True
            and status.get("custody", {}).get("backend") == result["backend"])

        raw = workspace.init_workspace(raw_peer, seat=seal)
        checks["raw_peer_created"] = raw.get("status") == workspace.CREATED
        checks["raw_peer_notice_is_raw"] = [
            n.get("id") for n in raw.get("notices") or []] == ["RAW_CUSTODY_DEFAULT"]
        loaded_peer = workspace.load_workspace(raw_peer)
        card_dir = base / "cards"
        card_dir.mkdir(parents=True, exist_ok=True)
        card_prot = card_dir / "protected.card.json"
        card_raw = card_dir / "raw.card.json"
        workspace.export_identity_card(loaded, card_prot)
        workspace.export_identity_card(loaded_peer, card_raw)
        workspace.add_recipient(loaded, "peer",
                                json.loads(card_raw.read_text(encoding="utf-8")), raw_peer)
        workspace.add_recipient(loaded_peer, "protected",
                                json.loads(card_prot.read_text(encoding="utf-8")), protected)
        sent = workspace.send_message(loaded, "peer", claim="d2 installed-wheel os-store proof")
        checks["send_accepted"] = sent.get("status") == "ACCEPTED"
        listing = workspace.list_inbox(workspace.load_workspace(raw_peer))
        checks["list_semantics_valid"] = (
            len(listing.get("items") or []) == 1
            and listing["items"][0]["state"] == "UNREAD")
        opened = workspace.open_message(workspace.load_workspace(raw_peer),
                                        sent["message"]["envelope_id"])
        checks["open_semantics_valid"] = (
            opened.get("record", {}).get("claim") == "d2 installed-wheel os-store proof")

        # ---- migration proof with an injected durable store (installed wheel path)
        migration = {}
        memory = _MemoryStore()
        raw_mig = base / "raw-migrate"
        workspace.init_workspace(raw_mig, seat=seal + "-MIG")
        before = workspace.load_workspace(raw_mig)
        before_card = workspace.identity_card(before)
        before_identity = (raw_mig / workspace.IDENTITY_DIR
                           / workspace.IDENTITY_NAME).read_bytes()
        migrated = workspace.migrate_workspace_custody(raw_mig, store=memory)
        after = workspace.load_workspace(raw_mig, store=memory)
        mig_identity = json.loads((raw_mig / workspace.IDENTITY_DIR
                                   / workspace.IDENTITY_NAME).read_text(encoding="utf-8"))
        migration["status"] = migrated.get("status")
        migration["fingerprints_preserved"] = (
            (after.sender_kid, after.recipient_kid)
            == (before.sender_kid, before.recipient_kid)
            and workspace.identity_card(after) == before_card)
        migration["v2_protected_metadata"] = mig_identity.get("schema") == workspace.IDENTITY_SCHEMA_V2
        migration["raw_values_gone"] = (
            b"sender_private_key" not in mig_identity_bytes(raw_mig)
            and b"recipient_private_key" not in mig_identity_bytes(raw_mig))
        migration["two_keys_stored"] = len(memory.data) == 2
        migration["store_values_usable"] = all(
            custody.validate_hex_key(value, what="migration proof value") == value
            for value in memory.data.values())
        repeated = workspace.migrate_workspace_custody(raw_mig, store=memory)
        migration["repeated_is_terminal"] = repeated.get("status") == custody.CUSTODY_ALREADY_PROTECTED
        failed_store = _MemoryStore(fail_on={"set"})
        raw_fail = base / "raw-failed"
        workspace.init_workspace(raw_fail, seat=seal + "-FAIL")
        fail_bytes = (raw_fail / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME).read_bytes()
        try:
            workspace.migrate_workspace_custody(raw_fail, store=failed_store)
            failed_code = "NO_ERROR"
        except SailangError as exc:
            failed_code = exc.code
        migration["failed_migration_code"] = failed_code
        migration["failed_leaves_raw_usable"] = (
            (raw_fail / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME).read_bytes()
            == fail_bytes
            and workspace.load_workspace(raw_fail).custody == custody.CUSTODY_RAW
            and failed_store.data == {})
        checks["migration_proof"] = all(
            value is True for key, value in migration.items()
            if key in ("fingerprints_preserved", "v2_protected_metadata",
                       "raw_values_gone", "two_keys_stored", "store_values_usable",
                       "repeated_is_terminal", "failed_leaves_raw_usable"))
        result["migration"] = migration
    finally:
        if protected_handles:
            residue = custody.release_keys(store, protected_handles)
            result["residue"] = residue
            result["keys_absent_after_delete"] = all(
                custody.key_present(store, handle) is False for handle in protected_handles)
        for path in (protected, raw_peer, base / "cards", base / "raw-migrate",
                     base / "raw-failed"):
            shutil.rmtree(path, ignore_errors=True)
    return result


def mig_identity_bytes(root):
    from pathlib import Path as _Path
    return (_Path(root) / "identity" / "identity.json").read_bytes()


try:
    _result = _run()
except BaseException as exc:  # noqa: BLE001 - report, never a bare traceback only
    _result = {"checks": {}, "errors": [f"{type(exc).__name__}: {exc}"],
               "residue": [], "fatal": True}
print(json.dumps(_result, sort_keys=True))
'''


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(args, cwd=None):
    return subprocess.run([str(item) for item in args], cwd=cwd,
                          capture_output=True, text=True, check=False)


def venv_bin(venv: Path, name: str) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / f"{name}.exe"
    return venv / "bin" / name


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--work", default=None)
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--schema", default=PROOF_SCHEMA,
                        help="evidence schema identity (defaults to the a2 schema so "
                             "the historical proof is unchanged)")
    parsed = parser.parse_args(argv)

    lar = _load("local_alpha_release", ROOT / "tools" / "local_alpha_release.py")
    bundle = Path(parsed.bundle).resolve()
    evidence = {
        "schema": parsed.schema,
        "version": PROOF_VERSION,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "BLOCKED",
        "candidate": {},
        "environment": {"python_version": sys.version.split()[0], "platform": sys.platform},
        "checks": {},
        "failures": [],
        "residue": [],
        "note": ("installed-wheel Windows os-store acceptance plus injected-store migration "
                 "proof; no private key value is stored in this evidence file"),
    }

    integrity = lar.verify_bundle_integrity(bundle, source_root=ROOT)
    manifest = json.loads(
        (bundle / "local_alpha_candidate.json").read_text(encoding="utf-8"))
    evidence["candidate"] = {
        "version": manifest.get("package_version"),
        "wheel_filename": manifest.get("wheel", {}).get("filename"),
        "wheel_sha256": manifest.get("wheel", {}).get("sha256"),
        "publication_status": manifest.get("publication_status"),
    }
    evidence["integrity"] = {"status": integrity.get("status"),
                             "failures": integrity.get("failures")}
    if integrity.get("status") != "PASS":
        evidence["failures"].append("bundle integrity gate failed")
        _write(parsed.out, evidence)
        return 1
    if sys.platform != "win32":
        evidence["failures"].append("the os-store proof requires the supported Windows host")
        _write(parsed.out, evidence)
        return 2

    owned = parsed.work is None
    work = Path(parsed.work) if parsed.work else Path(
        tempfile.mkdtemp(prefix="saimail-a2-osstore-proof-"))
    try:
        venv = work / "venv"
        created = run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)])
        if created.returncode != 0:
            evidence["failures"].append("virtual environment creation failed")
            evidence["status"] = "BLOCKED"
            _write(parsed.out, evidence)
            return 2
        python = venv_bin(venv, "python")
        wheel = bundle / manifest["wheel"]["filename"]
        installed = run([python, "-m", "pip", "install", "--no-deps", "--no-index",
                         "--no-build-isolation", str(wheel)], cwd=work)
        if installed.returncode != 0:
            evidence["failures"].append("wheel installation failed")
            _write(parsed.out, evidence)
            return 1
        deps = run([python, "-c",
                    "import cryptography, keyring; print(cryptography.__file__); "
                    "print(keyring.__file__)"])
        dep_paths = [line for line in deps.stdout.splitlines() if line.strip()]
        if deps.returncode != 0:
            dep_resolution = "MISSING"
        elif dep_paths and all(str(venv) in path for path in dep_paths):
            dep_resolution = "INSTALLED_IN_ENVIRONMENT"
        else:
            dep_resolution = "HOST_SITE_PACKAGES"
        evidence["dependencies"] = {"status": "AVAILABLE" if deps.returncode == 0 else "MISSING",
                                    "resolution": dep_resolution,
                                    "note": "optional dependency origin; no host paths recorded"}
        if deps.returncode != 0:
            evidence["failures"].append(
                "the credentials/crypto capability is unavailable for this proof")
            evidence["status"] = "BLOCKED"
            _write(parsed.out, evidence)
            return 2

        token = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        seat = f"D2PROOF{token}"
        peer_seat = f"D2PROOF{token}PEER"
        driver = work / "proof_driver.py"
        driver.write_text(DRIVER_SOURCE, encoding="utf-8")
        base = work / "proof-root"
        base.mkdir(parents=True, exist_ok=True)
        completed = run([python, str(driver), str(base), seat, peer_seat, EXPECTED_BACKEND],
                        cwd=work)
        evidence["driver_exit_code"] = completed.returncode
        payload = None
        for line in reversed((completed.stdout or "").splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    payload = json.loads(line)
                    break
                except ValueError:
                    continue
        if payload is None:
            evidence["failures"].append("the installed-wheel driver produced no JSON result")
            evidence["driver_stderr_tail"] = (completed.stderr or "")[-800:]
            _write(parsed.out, evidence)
            return 1

        module_files = payload.get("module_files") or {}
        resolved_inside = bool(module_files) and all(
            str(venv) in str(path) for path in module_files.values())
        evidence["module_resolution"] = {
            "resolved_inside_environment": resolved_inside,
            "paths": module_files,
            "checked_modules": ["saimail", "sailang", "saimail_local"],
            "note": "dependency modules (keyring/cryptography) may resolve from host site-packages",
        }
        if not resolved_inside:
            evidence["failures"].append("installed modules do not resolve inside the fresh environment")

        evidence["backend"] = payload.get("backend")
        evidence["identity"] = payload.get("identity")
        evidence["checks"] = payload.get("checks") or {}
        evidence["migration"] = payload.get("migration")
        evidence["residue"] = payload.get("residue") or []
        evidence["driver_errors"] = payload.get("errors") or []
        evidence["driver_python"] = payload.get("python_version")
        evidence["driver_platform"] = payload.get("platform")

        if payload.get("fatal"):
            evidence["failures"].append("the installed-wheel driver refused to complete")
        for name, ok in evidence["checks"].items():
            if ok is not True:
                evidence["failures"].append(f"check failed: {name}")
        if evidence["residue"]:
            evidence["failures"].append(
                "credential-store cleanup is incomplete: " + ", ".join(evidence["residue"]))
        if payload.get("keys_absent_after_delete") is not True:
            evidence["failures"].append("deleted credential entries are not proven absent")
        if evidence["backend"] != EXPECTED_BACKEND:
            evidence["failures"].append(f"backend classification is not {EXPECTED_BACKEND}")
        evidence["keys_absent_after_delete"] = payload.get("keys_absent_after_delete")

        for path in (work / "proof-root",):
            shutil.rmtree(path, ignore_errors=True)
        evidence["workspace_removed"] = not (work / "proof-root").exists()
        if not evidence["workspace_removed"]:
            evidence["failures"].append("temporary proof workspace was not removed")

        evidence["status"] = "PASS" if not evidence["failures"] else "FAIL"
        _write(parsed.out, evidence)
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        if owned and not parsed.keep:
            shutil.rmtree(work, ignore_errors=True)


def _write(path, payload) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: payload.get(key) for key in
                      ("schema", "status", "failures", "backend", "candidate")},
                     indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
