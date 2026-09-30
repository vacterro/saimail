"""Bounded standalone verifier for a SAIMAIL local alpha candidate bundle.

Runs on a machine that does NOT have the source checkout. It verifies the
bundle integrity against the recorded hashes, installs the exact frozen wheel
into a fresh virtual environment, and runs the documented local workflows from
the installed artifact, producing one bounded machine-readable result:

    LOCAL_ALPHA_VERIFICATION_1 v1

Usage:

    python verify_local_alpha.py --bundle DIR [--out DIR] [--keep]

Contract: spec/18-LOCAL-ALPHA-v0.md, D-052 and the D-054 custody notice.
Stdlib only; the host interpreter never imports saimail. No private key
material and no opened plaintext is stored in the result. Dependency
installation is reported separately from SAIMAIL runtime network activity
(which must stay zero).

This verifier proves the BASE candidate on any supported host: install,
version, raw-default workflow (including the first-run custody notice),
FG-05, FG-06 and the V2-01 acceptance. Protected `os-store` custody is a
platform-specific capability and is deliberately NOT tested here; the result
records that boundary explicitly instead of implying universal coverage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

RESULT_SCHEMA = "LOCAL_ALPHA_VERIFICATION_1"
RESULT_VERSION = 1
CANDIDATE_SCHEMA = "LOCAL_ALPHA_CANDIDATE_1"
VERIFIER_VERSION = 1

PRIVATE_HEX_FIELDS = ("sender_private_key", "recipient_private_key")
PRIVATE_KEY_RE = re.compile(
    r'"(?:sender_private_key|recipient_private_key)"\s*:\s*"[0-9a-f]{64}"')
PEM_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
TOKEN_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")

#: Installed-wheel proof of the accepted post-a2 product surface (P1 + V4-01).
#: Runs inside the fresh environment through the installed public API only; the
#: verifier module itself never imports saimail/lab/sailang. Uses metadata-only
#: operations (no network, no model) and prints exactly one JSON document.
PRODUCT_DRIVER_SOURCE = r'''
"""Disposable installed-wheel P1/V4-01 driver. Prints exactly one JSON doc."""
import json
import sys
from pathlib import Path

from saimail import workspace


def _run():
    base = Path(sys.argv[1])
    checks = {}
    errors = []
    try:
        a_root = base / "A"
        b_root = base / "B"
        workspace.init_workspace(a_root, seat="P1A")
        workspace.init_workspace(b_root, seat="P1B")
        a = workspace.load_workspace(a_root)
        b = workspace.load_workspace(b_root)
        workspace.add_recipient(a, "peer", workspace.identity_card(b), b_root)
        workspace.add_recipient(b, "peer", workspace.identity_card(a), a_root)

        sent = workspace.send_message(a, "peer",
                                      claim="p1/v401 installed-wheel proof",
                                      topic="p1-topic")
        checks["send_accepted"] = sent.get("status") == "ACCEPTED"
        eid = (sent.get("message") or {}).get("envelope_id")

        query = workspace.query_inbox(b, sender=a.seat, state="UNREAD")
        checks["p1_query_command"] = query.get("command") == "inbox-query"
        checks["p1_query_found"] = query.get("match_count") == 1
        checks["p1_query_metadata_only"] = all(
            "claim" not in item for item in (query.get("items") or []))

        opened = workspace.open_message(b, eid)
        checks["open_ok"] = (opened.get("record") or {}).get("claim") == (
            "p1/v401 installed-wheel proof")

        reply = workspace.reply_message(b, eid, claim="p1/v401 reply")
        checks["v401_reply_command"] = reply.get("command") == "reply"
        checks["v401_reply_ref"] = (reply.get("reply") or {}).get("ref") == eid
        checks["v401_reply_delivered"] = (
            (reply.get("delivery") or {}).get("status") == "ACCEPTED")

        back = workspace.query_inbox(a, ref=eid)
        checks["v401_reply_ref_findable"] = back.get("match_count") == 1
    except BaseException as exc:  # noqa: BLE001 - report, never a bare traceback only
        errors.append(f"{type(exc).__name__}: {exc}")
    return {"checks": checks, "errors": errors}


print(json.dumps(_run(), sort_keys=True))
'''


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums(text: str) -> dict:
    entries = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise ValueError(f"malformed checksums line: {line[:120]!r}")
        entries[match.group(2)] = match.group(1)
    return entries


def verify_integrity(bundle: Path) -> dict:
    failures = []
    manifest_path = bundle / "local_alpha_candidate.json"
    if not manifest_path.is_file():
        return {"status": "BLOCKED", "failures": ["manifest missing"]}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != CANDIDATE_SCHEMA:
        failures.append(f"manifest schema {manifest.get('schema')!r}")
    wheel_path = bundle / manifest["wheel"]["filename"]
    if not wheel_path.is_file():
        failures.append("wheel missing from the bundle")
    else:
        if wheel_path.stat().st_size != manifest["wheel"]["size_bytes"]:
            failures.append("wheel size differs from the manifest")
        actual = sha256_file(wheel_path)
        if actual != manifest["wheel"]["sha256"]:
            failures.append("wheel sha256 differs from the manifest")
        with zipfile.ZipFile(wheel_path) as archive:
            members = sorted(
                (i.filename, hashlib.sha256(archive.read(i.filename)).hexdigest())
                for i in archive.infolist() if not i.is_dir())
        digest = hashlib.sha256(b"SAIMAIL_LOCAL_ALPHA_WHEEL_CONTENT_1\n")
        for name, member_hash in members:
            digest.update(name.encode("utf-8") + b" " + member_hash.encode("ascii") + b"\n")
        if digest.hexdigest() != manifest["wheel"]["content_digest_sha256"]:
            failures.append("wheel content digest differs from the manifest")
        if len(members) != manifest["wheel"].get("member_count"):
            failures.append("wheel member count differs from the manifest")
    sums_path = bundle / "SHA256SUMS.txt"
    if not sums_path.is_file():
        failures.append("SHA256SUMS.txt missing")
    else:
        try:
            entries = parse_checksums(sums_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            entries = {}
            failures.append(f"checksums malformed: {exc}")
        for name, expected in sorted(entries.items()):
            path = bundle / name
            if not path.is_file() or sha256_file(path) != expected:
                failures.append(f"checksum mismatch: {name}")
        expected_names = {p.name for p in bundle.iterdir()
                          if p.is_file() and p.name != "SHA256SUMS.txt"}
        for name in sorted(expected_names - set(entries)):
            failures.append(f"checksum entry missing: {name}")
    return {
        "status": "PASS" if not failures else "FAIL",
        "manifest_schema": manifest.get("schema"),
        "candidate_version": manifest.get("package_version"),
        "wheel_filename": manifest.get("wheel", {}).get("filename"),
        "wheel_sha256": manifest.get("wheel", {}).get("sha256"),
        "failures": failures,
    }


def run(args, cwd=None):
    return subprocess.run([str(a) for a in args], cwd=cwd, capture_output=True,
                          text=True, check=False)


def venv_bin(venv: Path, name: str) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / f"{name}.exe"
    return venv / "bin" / name


def probe_privacy(payloads: dict) -> dict:
    findings = []
    for label, text in payloads.items():
        if PRIVATE_KEY_RE.search(text):
            findings.append(f"{label}: private key hex field")
        if PEM_RE.search(text):
            findings.append(f"{label}: pem private key header")
        if TOKEN_RE.search(text):
            findings.append(f"{label}: api-token shape")
    return {"status": "PASS" if not findings else "FAIL",
            "private_key_material_found": any("private key" in f for f in findings),
            "findings": findings}


class Verification:
    def __init__(self, bundle: Path, work: Path, *, offline: bool = False):
        self.bundle = bundle
        self.work = work
        self.offline = offline
        self.failures = []
        self.payloads: dict = {}
        self.result: dict = {}

    def fail(self, message: str):
        self.failures.append(message)

    def _reinstall_with_host_interpreter(self, wheel: Path) -> tuple:
        """Recreate the environment sharing the host's installed packages."""
        venv = self.work / "venv"
        shutil.rmtree(venv, ignore_errors=True)
        created = run([sys.executable, "-m", "venv", "--system-site-packages", str(venv)])
        python = venv_bin(venv, "python")
        installed = created.returncode == 0 and run(
            [python, "-m", "pip", "install", "--no-deps", "--no-index",
             "--no-build-isolation", str(wheel)], cwd=self.work).returncode == 0
        crypto = run([python, "-c", "import cryptography"])
        return installed and crypto.returncode == 0

    def _run_product_delta(self, python: Path, cwd: Path) -> dict:
        """Prove P1 + V4-01 inside the installed environment (metadata-only)."""
        driver = self.work / "product_delta_driver.py"
        driver.write_text(PRODUCT_DRIVER_SOURCE, encoding="utf-8")
        base = self.work / "product-delta"
        base.mkdir(parents=True, exist_ok=True)
        completed = run([python, str(driver), str(base)], cwd=cwd)
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
            return {"status": "FAIL", "checks": {},
                    "errors": ["the installed-wheel product driver produced no JSON"],
                    "stderr_tail": (completed.stderr or "")[-400:]}
        checks = payload.get("checks") or {}
        errors = payload.get("errors") or []
        ok = bool(checks) and all(value is True for value in checks.values()) and not errors
        return {"status": "PASS" if ok else "FAIL", "checks": checks, "errors": errors}

    def run(self) -> dict:
        verified_utc = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        integrity = verify_integrity(self.bundle)
        self.result["integrity"] = integrity
        self.payloads["integrity"] = json.dumps(integrity)
        if integrity.get("status") != "PASS":
            self.fail("bundle integrity gate failed")
            return self.finish("FAIL", verified_utc, integrity)

        manifest = json.loads(
            (self.bundle / "local_alpha_candidate.json").read_text(encoding="utf-8"))
        wheel = self.bundle / manifest["wheel"]["filename"]

        venv = self.work / "venv"
        created = run([sys.executable, "-m", "venv", str(venv)])
        if created.returncode != 0:
            self.fail("virtual environment creation failed")
            return self.finish("BLOCKED", verified_utc, integrity)
        python = venv_bin(venv, "python")
        installed = run([python, "-m", "pip", "install", "--no-deps", "--no-index",
                         "--no-build-isolation", str(wheel)], cwd=self.work)
        dependency_source = "NOT_NEEDED"
        if installed.returncode != 0:
            installed = run([python, "-m", "pip", "install", "--no-deps",
                             "--no-build-isolation", str(wheel)], cwd=self.work)
        if installed.returncode != 0:
            self.fail("wheel installation failed")
            return self.finish("FAIL", verified_utc, integrity)
        crypto = run([python, "-c", "import cryptography"])
        if crypto.returncode != 0:
            dependency_source = "HOST_SITE_PACKAGES"
            recovered = self._reinstall_with_host_interpreter(wheel)
            if not recovered and not self.offline:
                dependency_source = "PACKAGE_INDEX"
                fetched = run([python, "-m", "pip", "install", "cryptography"],
                              cwd=self.work)
                recovered = fetched.returncode == 0
                if not recovered:
                    recovered = self._reinstall_with_host_interpreter(wheel)
            if not recovered:
                self.fail("the declared crypto dependency is unavailable for this verifier")
                return self.finish("BLOCKED", verified_utc, integrity)
            python = venv_bin(self.work / "venv", "python")
        self.result["install"] = {
            "status": "INSTALLED",
            "wheel": wheel.name,
            "dependency_source": dependency_source,
            "note": ("dependency installation is separate from SAIMAIL runtime "
                     "network activity"),
        }

        cwd = self.work / "cwd"
        cwd.mkdir(parents=True, exist_ok=True)
        probe = run([python, "-c",
                     ("import saimail, lab, saimail_local; "
                      "print(saimail.__file__); print(lab.__file__); "
                      "print(saimail_local.__file__)")], cwd=cwd)
        self.payloads["module_resolution"] = probe.stdout
        paths = probe.stdout.splitlines()
        inside = (probe.returncode == 0 and paths
                  and all(str(venv) in path for path in paths))
        self.result["module_resolution"] = {
            "resolved_inside_environment": inside,
            "paths": paths,
        }
        if not inside:
            self.fail("installed modules do not resolve inside the fresh environment")

        script = venv_bin(venv, "saimail-local")
        version = run([script, "--version"], cwd=cwd)
        self.payloads["version"] = version.stdout + version.stderr
        reported = None
        match = re.search(r"^saimail (\S+)", version.stdout, flags=re.MULTILINE)
        if match:
            reported = match.group(1)
        self.result["saimail_local_version"] = {
            "status": "PASS" if reported == manifest["package_version"] else "FAIL",
            "reported": reported,
            "expected": manifest["package_version"],
        }
        if reported != manifest["package_version"]:
            self.fail(f"saimail-local --version reports {reported!r}")

        api_map_flag = run([script, "--api-map"], cwd=cwd)
        map_path = Path(api_map_flag.stdout.strip()) if api_map_flag.returncode == 0 else None
        if map_path and map_path.is_file():
            mapping = json.loads(map_path.read_text(encoding="utf-8"))
            self.result["api_map"] = {
                "path_exists": True,
                "schema": mapping.get("schema"),
                "release": mapping.get("release"),
                "release_matches": mapping.get("release") == manifest["package_version"],
            }
            if mapping.get("release") != manifest["package_version"]:
                self.fail("stable API map release marker differs from the candidate")
        else:
            self.result["api_map"] = {"path_exists": False}
            self.fail("stable API map is not shipped")

        demo = run([script, "--demo", "--out", str(self.work / "demo")], cwd=cwd)
        if demo.returncode != 0:
            self.fail("FG-05 demo exited non-zero")
        demo_result_path = self.work / "demo" / "local_scenario_result.json"
        self.result["fg05"] = {"status": "MISSING"}
        if demo_result_path.is_file():
            scenario = json.loads(demo_result_path.read_text(encoding="utf-8"))
            self.payloads["fg05"] = demo_result_path.read_text(encoding="utf-8")
            self.result["fg05"] = {
                "schema": scenario.get("schema"),
                "status": scenario.get("status"),
                "network_attempts": (scenario.get("zero_network_model") or {}).get(
                    "network_attempts"),
            }
            if scenario.get("schema") != "LOCAL_SCENARIO_RESULT_1" or \
                    scenario.get("status") != "PASS":
                self.fail("FG-05 demo did not PASS")
        else:
            self.fail("FG-05 demo produced no machine-readable result")

        utility = run([script, "--utility", "--out", str(self.work / "utility")], cwd=cwd)
        if utility.returncode != 0:
            self.fail("FG-06 benchmark exited non-zero")
        utility_path = self.work / "utility" / "fg06_utility_result.json"
        self.result["fg06"] = {"status": "MISSING"}
        if utility_path.is_file():
            bench = json.loads(utility_path.read_text(encoding="utf-8"))
            self.payloads["fg06"] = utility_path.read_text(encoding="utf-8")
            expected_verdict = (manifest.get("limitations") or {}).get("utility_verdict")
            self.result["fg06"] = {
                "schema": bench.get("schema"),
                "outcome_category": bench.get("outcome_category"),
                "expected_verdict": expected_verdict,
                "verdict_matches": bench.get("outcome_category") == expected_verdict,
                "network_attempts": (bench.get("zero_network_model") or {}).get(
                    "network_attempts"),
            }
            if bench.get("schema") != "FG06_UTILITY_RESULT_1":
                self.fail("FG-06 benchmark produced the wrong schema")
            if bench.get("outcome_category") != expected_verdict:
                self.fail("FG-06 verdict does not match the declared candidate verdict "
                          f"{expected_verdict!r}")
        else:
            self.fail("FG-06 benchmark produced no machine-readable result")

        acceptance = run([script, "acceptance", "--root", str(self.work / "acceptance"),
                          "--json"], cwd=cwd)
        self.payloads["v201_acceptance"] = acceptance.stdout
        self.result["v201_acceptance"] = {"status": "MISSING"}
        try:
            accepted = json.loads(acceptance.stdout)
        except ValueError:
            accepted = {}
        if accepted:
            self.result["v201_acceptance"] = {
                "schema": accepted.get("schema"),
                "status": accepted.get("status"),
                "network_attempts": (accepted.get("zero_network_model") or {}).get(
                    "network_attempts"),
            }
            if accepted.get("schema") != "LOCAL_WORKSPACE_RESULT_1" or \
                    accepted.get("status") != "PASS":
                self.fail("V2-01 acceptance did not PASS")
        else:
            self.fail("V2-01 acceptance produced no machine-readable result")

        direct_root = self.work / "direct-workspace"
        direct = run([script, "init", "--workspace", str(direct_root), "--seat",
                      "ALPHA-VERIFY", "--json"], cwd=cwd)
        self.payloads["v201_direct"] = direct.stdout
        try:
            direct_result = json.loads(direct.stdout)
        except ValueError:
            direct_result = {}
        direct_identity = direct_result.get("identity") or {}
        direct_notices = [notice for notice in (direct_result.get("notices") or [])
                          if isinstance(notice, dict)
                          and notice.get("id") == "RAW_CUSTODY_DEFAULT"]
        self.result["v201_direct_command"] = {
            "schema": direct_result.get("schema"),
            "status": direct_result.get("status"),
            "network_attempts": direct_result.get("network_attempts"),
            "custody_mode": direct_identity.get("custody"),
            "first_run_notice": bool(direct_notices),
        }
        if direct_result.get("schema") != "LOCAL_WORKSPACE_COMMAND_1" or \
                direct_result.get("status") != "CREATED":
            self.fail("direct workspace command did not report CREATED")
        if direct_identity.get("custody") != "raw":
            self.fail("the base candidate's default init is not raw custody")
        if not direct_notices:
            self.fail("the raw first-run custody notice is missing from the init result")

        product_delta = self._run_product_delta(python, cwd)
        self.payloads["p1_v401"] = json.dumps(product_delta)
        self.result["p1_v401"] = product_delta
        if product_delta.get("status") != "PASS":
            self.fail("the installed wheel failed the P1/V4-01 product-surface proof")

        content_proof = manifest.get("content_proof") or {}
        self.result["custody_content_proof"] = {
            "status": content_proof.get("status"),
            "checks": content_proof.get("checks"),
        }
        if content_proof.get("status") != "PASS":
            self.fail("the candidate wheel content proof is not PASS")

        custody_truth = manifest.get("custody") or {}
        self.result["custody"] = {
            "default": custody_truth.get("default"),
            "os_store_selection": custody_truth.get("os_store_selection"),
            "os_store_requires": custody_truth.get("os_store_requires"),
            "platform_evidence": custody_truth.get("os_store_platform_evidence"),
        }
        self.result["scope"] = {
            "base_candidate_verification": "TESTED_BY_THIS_VERIFIER",
            "os_store_platform_verification": (
                "NOT_TESTED_HERE platform-specific; independent Windows evidence is "
                "recorded in the candidate evidence set"),
        }

        counters = {
            "network_attempts": sum(int((entry or {}).get("network_attempts") or 0)
                                    for entry in (
                                        self.result.get("fg05") or {},
                                        self.result.get("fg06") or {},
                                        self.result.get("v201_acceptance") or {},
                                        self.result.get("v201_direct_command") or {},
                                    )),
            "model_calls": 0,
            "provider_calls": 0,
            "note": "the local base path has no model or provider surface",
        }
        self.result["runtime_counters"] = counters
        if self.result.get("fg05", {}).get("network_attempts") not in (0,) or \
                self.result.get("v201_acceptance", {}).get("network_attempts") not in (0,):
            self.fail("a local workflow reported a runtime network attempt")

        privacy = probe_privacy(self.payloads)
        self.result["privacy"] = privacy
        if privacy["status"] != "PASS":
            self.fail("privacy scan found material in the verification output")

        self.result["limitations"] = {
            "identity": (manifest.get("limitations") or {}).get("identity"),
            "utility_verdict": (manifest.get("limitations") or {}).get("utility_verdict"),
            "acknowledged": True,
        }
        return self.finish("FAIL" if self.failures else "PASS", verified_utc, integrity)

    def finish(self, status: str, verified_utc: str, integrity: dict) -> dict:
        self.result.update({
            "schema": RESULT_SCHEMA,
            "version": RESULT_VERSION,
            "status": status,
            "candidate": {
                "version": integrity.get("candidate_version"),
                "wheel_filename": integrity.get("wheel_filename"),
                "wheel_sha256": integrity.get("wheel_sha256"),
                "publication_status": "NOT_PUBLISHED",
            },
            "environment": {
                "python_version": platform.python_version(),
                "platform": sys.platform,
                "verifier_version": VERIFIER_VERSION,
                "verified_utc": verified_utc,
            },
            "failures": list(self.failures),
        })
        return self.result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", required=True, help="candidate bundle directory")
    parser.add_argument("--out", default=None, help="write the result JSON here")
    parser.add_argument("--work", default=None, help="work directory for the fresh venv")
    parser.add_argument("--keep", action="store_true", help="retain the work directory")
    parser.add_argument("--offline", action="store_true",
                        help="never use a package index; require the host interpreter "
                             "to provide the crypto dependency")
    args = parser.parse_args(argv)

    bundle = Path(args.bundle).resolve()
    if not bundle.is_dir():
        print(json.dumps({"schema": RESULT_SCHEMA, "version": RESULT_VERSION,
                          "status": "BLOCKED",
                          "failures": [f"bundle directory not found: {bundle}"]},
                         indent=2, sort_keys=True))
        return 2
    owned = args.work is None
    work = Path(args.work) if args.work else Path(
        tempfile.mkdtemp(prefix="saimail-local-alpha-verify-"))
    try:
        result = Verification(bundle, work, offline=args.offline).run()
        if args.out is not None:
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            (out / "local_alpha_verification.json").write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["status"] == "PASS" else 1
    finally:
        if owned and not args.keep:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
