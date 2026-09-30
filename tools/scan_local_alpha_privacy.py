"""Bounded privacy scan for the V2-04 local alpha candidate bundle.

Checks the bundle and its reports for known private material and bounded
secret shapes: Ed25519/X25519 private key fields, PEM private key headers,
API-token shapes, credential handles, planted privacy markers and unintended
absolute user secret paths. Contract: ``spec/18-LOCAL-ALPHA-v0.md`` (privacy
gate, red control) and D-052.

    python tools/scan_local_alpha_privacy.py --root release/local-alpha

The scanner is a bounded structural check, not a proof that no secret exists.
The red control plants a unique marker into a disposable copy and requires the
scanner to fail; the real candidate must pass.
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

SCAN_SCHEMA = "LOCAL_ALPHA_PRIVACY_SCAN_1"
SCAN_VERSION = 1
PLANTED_MARKER = "T86_PRIVACY_MARKER_9f2c1d"
MAX_SCAN_BYTES = 8_000_000

RULES = [
    ("private_key_hex_field",
     re.compile(r'"(?:sender_private_key|recipient_private_key)"\s*:\s*"[0-9a-f]{64}"')),
    ("pem_private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("api_token_shape", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("credential_value",
     re.compile(r"\bSAIROUTE_API_KEY\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{16,}"
                r"|\bBearer\s+[A-Za-z0-9_.\-]{20,}")),
    ("planted_marker", re.compile(re.escape(PLANTED_MARKER))),
    ("absolute_user_path",
     re.compile(r"[A-Za-z]:\\Users\\(?![^\\]*\\AppData\\Local\\Temp)[^\\\s\"']+\\")),
]


def _scan_text(label: str, text: str) -> list:
    findings = []
    for rule, pattern in RULES:
        for match in pattern.finditer(text):
            findings.append({"path": label, "rule": rule,
                             "match": match.group(0)[:80]})
    return findings


def _scan_bytes(label: str, data: bytes) -> list:
    if len(data) > MAX_SCAN_BYTES:
        return []
    return _scan_text(label, data.decode("utf-8", errors="ignore"))


def scan_path(path: Path) -> list:
    findings = []
    if path.suffix in (".whl", ".zip"):
        try:
            with zipfile.ZipFile(path) as archive:
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    findings.extend(_scan_bytes(f"{path.name}!{info.filename}",
                                                archive.read(info.filename)))
        except zipfile.BadZipFile:
            findings.extend(_scan_bytes(path.name, path.read_bytes()))
        return findings
    findings.extend(_scan_bytes(path.name, path.read_bytes()))
    return findings


def scan_tree(root: Path) -> dict:
    findings = []
    files = 0
    if not root.is_dir():
        return {"schema": SCAN_SCHEMA, "version": SCAN_VERSION, "status": "BLOCKED",
                "root": str(root), "files_scanned": 0,
                "findings": [], "failures": [f"root not found: {root}"]}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if ".venv" in path.parts or "venv" in path.parts:
            continue
        files += 1
        findings.extend(scan_path(path))
    return {
        "schema": SCAN_SCHEMA,
        "version": SCAN_VERSION,
        "status": "PASS" if not findings else "FAIL",
        "root": str(root),
        "files_scanned": files,
        "findings": findings,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, help="directory to scan")
    parser.add_argument("--out", default=None, help="write the JSON result here")
    args = parser.parse_args(argv)
    result = scan_tree(Path(args.root))
    if args.out is not None:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
