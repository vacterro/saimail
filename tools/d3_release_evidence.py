"""D3 release evidence driver (post-GUI candidate 0.0.2a3).

Additive to the a2 driver: it never rewrites `tools/a2_release_evidence.py` or any
frozen a2 evidence. It provides the D3 decision packet, the frozen a1/a2
immutability proof, the candidate claim matrix and the a3 gate evaluation, and
delegates the generic integrity / privacy / reproducibility red-control passes to
the a2 driver with D3 schema identities.

    python tools/d3_release_evidence.py decide    --out release/evidence/d3/release_decision.json
    python tools/d3_release_evidence.py immutability --out release/evidence/d3/immutability.json
    python tools/d3_release_evidence.py integrity --bundle release/candidates/0.0.2a3 \
        --out release/evidence/a3/integrity_controls.json
    python tools/d3_release_evidence.py privacy   --bundle release/candidates/0.0.2a3 \
        [--evidence-dir release/evidence/a3] --out release/evidence/a3/privacy_controls.json
    python tools/d3_release_evidence.py repro     --first-bundle DIR --second-bundle DIR \
        --first-verification F --second-verification F --out FILE
    python tools/d3_release_evidence.py claims    --bundle DIR --verification F \
        --osstore-proof F [--external-acceptance F] --out FILE
    python tools/d3_release_evidence.py gates     --bundle DIR --verification F \
        --osstore-proof F --privacy F --integrity F --repro F \
        [--gui-matrix F] [--external-acceptance F] [--full-suite F] [--saipen F] --out FILE

Nothing here publishes anything.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import tomllib
import xml.etree.ElementTree as ET
import zipfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DECISION_SCHEMA = "SAIMAIL_D3_RELEASE_DECISION_1"
CLAIM_SCHEMA = "SAIMAIL_D3_CLAIM_MATRIX_1"
GATE_SCHEMA = "SAIMAIL_D3_GATE_EVALUATION_1"
IMMUTABILITY_SCHEMA = "SAIMAIL_D3_IMMUTABILITY_1"
CLOSURE_CONTEXT_SCHEMA = "SAIMAIL_T107_CLOSURE_CONTEXT_1"
DOCUMENTATION_SCHEMA = "SAIMAIL_D3_DOCUMENTATION_VALIDATION_1"

IDENTITY_SCHEMA_RE = re.compile(r"SAIMAIL_LOCAL_IDENTITY_[0-9]+")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


lar = _load("local_alpha_release", ROOT / "tools" / "local_alpha_release.py")
a2 = _load("a2_release_evidence", ROOT / "tools" / "a2_release_evidence.py")
a3_acceptor = _load(
    "accept_d3_external_proof", ROOT / "tools" / "accept_d3_external_proof.py")

FROZEN_A1 = lar.HISTORICAL_A1
FROZEN_A2 = lar.HISTORICAL_A2
A2_EXTERNAL_PROOF_SHA256 = "2d77e13dd1e414e8642fb5a1b60e216e2136bb267bf1789c7e1169adfaa1d5c2"


def _read(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(path, payload, summary_keys) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: payload.get(key) for key in summary_keys}, indent=2,
                     sort_keys=True))


def _manifest(bundle: Path) -> dict:
    return _read(bundle / "local_alpha_candidate.json")


def _candidate_identity(bundle: Path) -> tuple[dict, dict]:
    expected_bundle = ROOT / "release" / "candidates" / "0.0.2a3"
    if bundle.resolve() != expected_bundle.resolve():
        raise SystemExit(json.dumps({
            "status": "REFUSED", "code": "D3_BUNDLE_NOT_FROZEN_A3",
            "detail": str(bundle)}))
    manifest = _manifest(bundle)
    wheel = bundle / a3_acceptor.A3_WHEEL
    actual_sha256 = lar.sha256_file(wheel)
    identity = {
        "version": a3_acceptor.A3_VERSION,
        "wheel_filename": a3_acceptor.A3_WHEEL,
        "wheel_sha256": a3_acceptor.A3_WHEEL_SHA256,
        "publication_status": "NOT_PUBLISHED",
    }
    if (manifest.get("package_version") != identity["version"]
            or manifest.get("wheel", {}).get("filename") != identity["wheel_filename"]
            or manifest.get("wheel", {}).get("sha256") != identity["wheel_sha256"]
            or manifest.get("publication_status") != identity["publication_status"]
            or actual_sha256 != identity["wheel_sha256"]):
        raise SystemExit(json.dumps({
            "status": "REFUSED", "code": "D3_FROZEN_A3_IDENTITY_MISMATCH",
            "detail": {"manifest": manifest.get("wheel"),
                       "actual_sha256": actual_sha256}}))
    return manifest, identity


def _candidate_matches(payload: dict, identity: dict) -> bool:
    candidate = payload.get("candidate")
    return (isinstance(candidate, dict)
            and candidate.get("version") == identity["version"]
            and candidate.get("wheel_filename") == identity["wheel_filename"]
            and candidate.get("wheel_sha256") == identity["wheel_sha256"]
            and candidate.get("publication_status") == identity["publication_status"])


def _has_schema(payload: dict, schema: str) -> bool:
    return (isinstance(payload, dict) and payload.get("schema") == schema
            and type(payload.get("version")) is int and payload["version"] == 1)


def _candidate_record(payload: dict, schema: str, identity: dict,
                      *, require_pass: bool = True) -> bool:
    return (_has_schema(payload, schema)
            and _candidate_matches(payload, identity)
            and (not require_pass or payload.get("status") == "PASS")
            and payload.get("failures") == [])


def _acceptance_is_strict(payload: dict, identity: dict) -> bool:
    checks = payload.get("checks") if isinstance(payload, dict) else None
    proof_sha256 = payload.get("external_proof_sha256") if isinstance(payload, dict) else None
    return (
        _has_schema(payload, a3_acceptor.ACCEPT_SCHEMA)
        and payload.get("status") == "PASS"
        and payload.get("candidate_version") == identity["version"]
        and payload.get("candidate_sha256") == identity["wheel_sha256"]
        and payload.get("external_schema") == "LOCAL_ALPHA_VERIFICATION_1"
        and isinstance(proof_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", proof_sha256) is not None
        and payload.get("proof_provenance") == "OPERATOR_SUPPLIED_UNVERIFIED"
        and payload.get("publication") == "NONE"
        and payload.get("failures") == []
        and isinstance(checks, dict)
        and a3_acceptor.ACCEPTANCE_REQUIRED_CHECKS.issubset(checks)
        and all(type(value) is bool and value for value in checks.values()))


def _verification_valid(payload: dict, identity: dict) -> bool:
    return (_candidate_record(payload, "LOCAL_ALPHA_VERIFICATION_1", identity)
            and (payload.get("install") or {}).get("status") == "INSTALLED"
            and (payload.get("module_resolution") or {}).get(
                "resolved_inside_environment") is True)


def _osstore_valid(payload: dict, identity: dict) -> bool:
    checks = payload.get("checks") if isinstance(payload, dict) else None
    return (_candidate_record(payload, "SAIMAIL_D3_WINDOWS_OS_STORE_PROOF_1", identity)
            and isinstance(checks, dict) and bool(checks)
            and all(type(value) is bool and value for value in checks.values())
            and (payload.get("integrity") or {}).get("status") == "PASS"
            and not payload.get("driver_errors")
            and payload.get("driver_exit_code") == 0
            and payload.get("workspace_removed") is True
            and payload.get("keys_absent_after_delete") is True
            and payload.get("residue") == [])


def _gui_valid(payload: dict, identity: dict) -> bool:
    checks = payload.get("checks") if isinstance(payload, dict) else None
    return (_candidate_record(payload, "SAIMAIL_D3_GUI_INSTALL_MATRIX_1", identity)
            and isinstance(checks, dict) and bool(checks)
            and all(type(value) is bool and value for value in checks.values())
            and (payload.get("install") or {}).get("status") == "INSTALLED"
            and (payload.get("integrity") or {}).get("status") == "PASS"
            and (payload.get("module_resolution") or {}).get(
                "resolved_inside_environment") is True)


def _repro_valid(payload: dict, identity: dict) -> bool:
    checks = payload.get("checks") if isinstance(payload, dict) else None
    first, second = (payload.get("first") or {}, payload.get("second") or {}) \
        if isinstance(payload, dict) else ({}, {})
    return (
        _has_schema(payload, "SAIMAIL_D3_REPRODUCIBILITY_1")
        and payload.get("status") == "PASS"
        and _candidate_matches(payload, identity)
        and isinstance(checks, dict) and bool(checks)
        and all(type(value) is bool and value for value in checks.values())
        and payload.get("selected_candidate") == identity["wheel_sha256"]
        and first.get("wheel") == identity["wheel_filename"]
        and first.get("sha256") == identity["wheel_sha256"]
        and first.get("metadata_version") == identity["version"]
        and first.get("content_digest_sha256") == a3_acceptor.A3_CONTENT_DIGEST
        and second.get("wheel") == identity["wheel_filename"]
        and second.get("metadata_version") == identity["version"]
        and second.get("content_digest_sha256") == a3_acceptor.A3_CONTENT_DIGEST
        and type(second.get("sha256")) is str
        and re.fullmatch(r"[0-9a-f]{64}", second["sha256"]) is not None)


def _red_controls_valid(payload: dict, identity: dict, kind: str) -> bool:
    if (not _candidate_record(payload, "SAIMAIL_D3_RED_CONTROLS_1", identity)
            or not isinstance(payload.get("red_controls"), list)
            or not payload["red_controls"]
            or any(item.get("ok") is not True
                   or item.get("expected") != "FAIL"
                   or item.get("observed") != "FAIL"
                   for item in payload["red_controls"] if isinstance(item, dict))
            or any(not isinstance(item, dict) for item in payload["red_controls"])):
        return False
    if kind == "integrity":
        nested = payload.get("integrity") or {}
        return (nested.get("status") == "PASS"
                and nested.get("candidate_version") == identity["version"]
                and nested.get("wheel_filename") == identity["wheel_filename"]
                and nested.get("wheel_sha256") == identity["wheel_sha256"]
                and nested.get("failures") == [])
    if kind == "privacy":
        nested = payload.get("privacy") or {}
        return (nested.get("schema") == "LOCAL_ALPHA_PRIVACY_SCAN_1"
                and nested.get("version") == 1 and nested.get("status") == "PASS"
                and nested.get("findings") == []
                and isinstance(payload.get("evidence_scan"), dict)
                and payload["evidence_scan"].get("status") == "PASS"
                and payload["evidence_scan"].get("findings") == [])
    return False


def _source_tree_fingerprint(root: Path = ROOT) -> str:
    extensions = {".py", ".toml", ".md", ".json", ".txt"}
    bases = ("saimail", "sailang", "lab", "tests", "tools", "spec", "humbox")
    paths = [root / "VERSION", root / "pyproject.toml", root / "saimail_local.py"]
    for name in bases:
        base = root / name
        if base.is_dir():
            paths.extend(path for path in base.rglob("*")
                         if path.is_file() and path.suffix.lower() in extensions)
    digest = hashlib.sha256(b"SAIMAIL_D3_SOURCE_TREE_1\n")
    for path in sorted(set(paths), key=lambda item: item.relative_to(root).as_posix()):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8") + b" "
                      + hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii")
                      + b"\n")
    return digest.hexdigest()


def _documentation_paths(args) -> dict[str, Path]:
    closure_arg = getattr(args, "closure_context", None)
    if not closure_arg:
        closure_arg = ROOT / "release" / "evidence" / "a3" / "t107_closure_context.json"
    return {
        "state": Path(getattr(args, "state", None) or ROOT / ".saipen" / "STATE.md"),
        "board": Path(getattr(args, "board", None) or ROOT / ".saipen" / "BOARD.md"),
        "current_state": Path(getattr(args, "current_state", None)
                              or ROOT / "humbox" / "CURRENT-STATE.md"),
        "roadmap": Path(getattr(args, "roadmap", None)
                        or ROOT / "humbox" / "FUTURE-GATES-V6.md"),
        "external_request": Path(getattr(args, "external_request", None)
                                 or ROOT / "release" / "evidence" / "a3"
                                 / "EXTERNAL_VERIFICATION_REQUEST.md"),
        "closure_context": Path(closure_arg),
    }


def _state_value(text: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s#]+))", text)
    if match is None:
        return None
    return next((value for value in match.groups() if value is not None), None)


def _board_done(board: str, ticket: str) -> bool:
    match = re.search(rf"(?m)^\s*-\s*\[([ x/])\]\s*{re.escape(ticket)}\b", board)
    return match is not None and match.group(1) == "x"


def _board_active(board: str, ticket: str) -> bool:
    match = re.search(rf"(?m)^\s*-\s*\[([ x/])\]\s*{re.escape(ticket)}\b", board)
    return match is not None and match.group(1) == "/"


def _board_blocked(board: str, ticket: str) -> bool:
    match = re.search(rf"(?m)^\s*-\s*\[[ x/]\]\s*{re.escape(ticket)}\b([^\n]*)",
                      board)
    if match is None:
        return False
    row = match.group(1)
    blocker = re.search(r"\|\s*blocker:\s*(.*?)\s*(?:\||$)", row)
    return blocker is not None and bool(blocker.group(1))


def _closure_context_valid(payload: dict, identity: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("schema") != CLOSURE_CONTEXT_SCHEMA or payload.get("version") != 1:
        return False
    candidate = payload.get("candidate")
    if not isinstance(candidate, dict):
        return False
    if candidate.get("wheel_sha256") != identity["wheel_sha256"]:
        return False
    if candidate.get("version") != identity["version"]:
        return False
    if candidate.get("wheel_filename") != identity["wheel_filename"]:
        return False
    if candidate.get("publication_status") != "NOT_PUBLISHED":
        return False
    if payload.get("closure_event") != "E-1502":
        return False
    lifecycle = payload.get("lifecycle_at_closure") or {}
    for ticket in ("T-106", "T-107", "T-108", "T-109", "T-110"):
        if lifecycle.get(ticket) != "DONE":
            return False
    expected_gates = payload.get("expected_gates") or {}
    if expected_gates.get("G13") != "PENDING_EXTERNAL":
        return False
    if expected_gates.get("G17") != "ABSENT":
        return False
    if expected_gates.get("publication") != "NONE":
        return False
    if payload.get("v602_state_at_closure") != "NOT_STARTED":
        return False
    docs = payload.get("authoritative_documents_at_closure") or {}
    for key in ("current_state_sha256", "roadmap_sha256", "external_request_sha256"):
        val = docs.get(key)
        if not val or not isinstance(val, str) or len(val) != 64:
            return False
    return True


def _documentation_checks(paths: dict[str, Path], identity: dict) -> dict[str, bool]:
    try:
        state = paths["state"].read_text(encoding="utf-8")
        board = paths["board"].read_text(encoding="utf-8")
        current = paths["current_state"].read_text(encoding="utf-8")
        roadmap = paths["roadmap"].read_text(encoding="utf-8")
        request = paths["external_request"].read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return {"sources_readable": False}

    current_head = current.split("## READ IN THIS ORDER", 1)[0]
    current_next = current.split("## NEXT EXECUTABLE STEP", 1)[-1]
    current_authority = current_head + "\n" + current_next
    roadmap_current = roadmap[:roadmap.find("## 7.") if "## 7." in roadmap else len(roadmap)]
    roadmap_selected = roadmap.split("## 9.", 1)[-1].split("## 11.", 1)[0]
    roadmap_authority = roadmap_current + "\n" + roadmap_selected
    authority = current_authority + "\n" + roadmap_authority

    phase = _state_value(state, "phase")
    task = _state_value(state, "task")
    blocker = _state_value(state, "blocker") or ""
    if _board_done(board, "T-107"):
        ticket_status = "DONE"
    elif _board_blocked(board, "T-107"):
        ticket_status = "BLOCKED"
    elif task == "T-107" and (phase == "BLOCKED" or blocker not in ("", "none")):
        ticket_status = "BLOCKED"
    elif task == "T-107" and _board_active(board, "T-107"):
        ticket_status = "ACTIVE"
    else:
        ticket_status = "NOT_ACTIVE"

    hash_text = identity["wheel_sha256"]
    closure_p = paths.get("closure_context")
    closure_present = bool(closure_p and closure_p.is_file())
    closure_valid = False
    if closure_present:
        try:
            ctx = _read(closure_p)
            closure_valid = _closure_context_valid(ctx, identity)
        except Exception:
            closure_valid = False

    checks = {
        "sources_readable": True,
        "canonical_t106_done": _board_done(board, "T-106"),
        "canonical_t108_t110_done": all(
            _board_done(board, f"T-{number}") for number in (108, 109, 110)),
        "canonical_t107_status_known": ticket_status != "NOT_ACTIVE",
        "current_t107_status_matches": f"T-107 {ticket_status}" in current_authority,
        "roadmap_t107_status_matches": f"T-107 {ticket_status}" in roadmap_authority,
        "current_candidate_exact": (identity["version"] in current_authority
                                     and hash_text in current_authority),
        "roadmap_candidate_exact": (identity["version"] in roadmap_authority
                                    and hash_text in roadmap_authority),
        "request_candidate_exact": (
            identity["version"] in request
            and "release/candidates/0.0.2a3/" in request
            and identity["wheel_filename"] in request
            and hash_text in request),
        "no_t106_active_claim": not re.search(
            r"\bACTIVE\s+via\s+T-106\b|T-106\s+is\s+the\s+active\s+D3", authority,
            flags=re.IGNORECASE),
        "current_g13_pending": "G13" in current_authority
                                and "PENDING_EXTERNAL" in current_authority,
        "roadmap_g13_pending": "G13" in roadmap_authority
                               and "PENDING_EXTERNAL" in roadmap_authority,
        "request_g13_pending": "PENDING_EXTERNAL" in request,
        "current_g17_absent": "G17" in current_authority
                               and "ABSENT" in current_authority,
        "roadmap_g17_absent": "G17" in roadmap_authority
                              and "ABSENT" in roadmap_authority,
        "request_g17_absent": "G17" in request and "ABSENT" in request,
        "current_publication_none": "publication" in current_authority.lower()
                                     and "NONE" in current_authority,
        "roadmap_publication_none": "publication" in roadmap_authority.lower()
                                    and "NONE" in roadmap_authority,
        "request_not_publication": "publication" in request.lower()
                                   and "NONE" in request and "G17" in request,
        "current_v602_not_started": "V6-02" in current_authority
                                    and "NOT STARTED" in current_authority,
        "roadmap_v602_not_started": "V6-02" in roadmap_authority
                                    and "NOT STARTED" in roadmap_authority,
        "request_has_one_bounded_external_procedure": (
            "## Exact steps on the second machine" in request
            and re.search(r"genuinely separate machine\s*/\s*VM\s*/\s*host", request,
                          flags=re.IGNORECASE) is not None
            and "python verify_local_alpha.py --bundle . --out verification" in request),
        "request_waits_for_local_closure": (
            ticket_status == "DONE"
            or ("T-107 DONE" not in request
                and re.search(r"do not execute.{0,100}T-107", request,
                              flags=re.IGNORECASE | re.DOTALL) is not None)),
        "closure_context_valid": closure_valid if closure_present else True,
    }
    return checks


def _documentation_record_valid(payload: dict, identity: dict, args) -> bool:
    if (not _candidate_record(payload, DOCUMENTATION_SCHEMA, identity)
            or payload.get("failures") != []):
        return False
    checks = payload.get("checks")
    if not isinstance(checks, dict) or not checks or not all(
            type(value) is bool and value for value in checks.values()):
        return False
    paths = _documentation_paths(args)

    # 1. Authoritative static documents check (current_state, roadmap, external_request, closure_context)
    # Stored hashes must match the actual file bytes.
    # State and Board are intentionally excluded from bitwise hash matching to prevent normal lifecycle transitions from invalidating historical closure evidence.
    recorded_hashes = payload.get("authoritative_documents_sha256") or payload.get("source_files_sha256") or {}
    for name in ("current_state", "roadmap", "external_request", "closure_context"):
        if name in recorded_hashes and recorded_hashes[name] is not None:
            p = paths.get(name)
            if not p or not p.is_file() or lar.sha256_file(p) != recorded_hashes[name]:
                return False

    # 2. Closure context verification
    closure_p = paths.get("closure_context")
    if closure_p and closure_p.is_file():
        try:
            ctx = _read(closure_p)
            if not _closure_context_valid(ctx, identity):
                return False
        except Exception:
            return False

    # 3. Live workflow state (STATE.md & BOARD.md) non-contradiction check
    try:
        live_board = paths["board"].read_text(encoding="utf-8")
        live_state = paths["state"].read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False

    # T-107 must remain DONE on the board
    if not _board_done(live_board, "T-107"):
        return False
    if not _board_done(live_board, "T-106"):
        return False
    for number in (108, 109, 110):
        if not _board_done(live_board, f"T-{number}"):
            return False

    # T-107 cannot be ACTIVE in STATE or BOARD
    live_task = _state_value(live_state, "task")
    live_phase = _state_value(live_state, "phase")
    if live_task == "T-107" and live_phase in ("BUILD", "SCOUT", "VERIFY", "REVIEW", "BLOCKED"):
        return False
    if _board_active(live_board, "T-107"):
        return False

    # Live state must not authorize publication
    if "publication_status: published" in live_state.lower():
        return False

    return True


def cmd_closure_context(args) -> int:
    bundle = Path(args.bundle)
    manifest, identity = _candidate_identity(bundle)
    paths = _documentation_paths(args)

    current_state_hash = lar.sha256_file(paths["current_state"]) if paths["current_state"].is_file() else None
    roadmap_hash = lar.sha256_file(paths["roadmap"]) if paths["roadmap"].is_file() else None
    external_request_hash = lar.sha256_file(paths["external_request"]) if paths["external_request"].is_file() else None

    source_fp = getattr(args, "source_fingerprint", None) or _source_tree_fingerprint()
    created_utc = getattr(args, "created_utc", None) or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    payload = {
        "schema": CLOSURE_CONTEXT_SCHEMA,
        "version": 1,
        "created_utc": created_utc,
        "candidate": {
            **identity,
            "member_count": manifest.get("wheel", {}).get("member_count", 65),
        },
        "closure_event": getattr(args, "closure_event", None) or "E-1502",
        "lifecycle_at_closure": {
            "T-106": "DONE",
            "T-107": "DONE",
            "T-108": "DONE",
            "T-109": "DONE",
            "T-110": "DONE",
        },
        "expected_gates": {
            "G13": "PENDING_EXTERNAL",
            "G17": "ABSENT",
            "publication": "NONE",
        },
        "v602_state_at_closure": "NOT_STARTED",
        "authoritative_documents_at_closure": {
            "current_state_sha256": current_state_hash,
            "roadmap_sha256": roadmap_hash,
            "external_request_sha256": external_request_hash,
        },
        "source_fingerprint": source_fp,
        "provenance": "Derived from canonical live state at T-107 E-1502 closure boundary.",
    }
    _write(args.out, payload, ("schema", "closure_event", "candidate"))
    return 0


def cmd_documentation(args) -> int:
    _, identity = _candidate_identity(Path(args.bundle))
    paths = _documentation_paths(args)
    checks = _documentation_checks(paths, identity)
    failures = sorted(name for name, ok in checks.items() if not ok)
    closure_p = paths.get("closure_context")
    closure_hash = (
        lar.sha256_file(closure_p)
        if (closure_p and closure_p.is_file())
        else None
    )
    auth_hashes = {
        "current_state": lar.sha256_file(paths["current_state"]) if paths["current_state"].is_file() else None,
        "roadmap": lar.sha256_file(paths["roadmap"]) if paths["roadmap"].is_file() else None,
        "external_request": lar.sha256_file(paths["external_request"]) if paths["external_request"].is_file() else None,
    }
    if closure_hash is not None:
        auth_hashes["closure_context"] = closure_hash
    payload = {
        "schema": DOCUMENTATION_SCHEMA,
        "version": 1,
        "created_utc": getattr(args, "created_utc", None) or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS" if not failures else "FAIL",
        "candidate": identity,
        "closure_context_sha256": closure_hash,
        "authoritative_documents_sha256": auth_hashes,
        "source_files_sha256": auth_hashes,
        "checks": checks,
        "failures": failures,
    }
    _write(args.out, payload, ("schema", "status", "failures"))
    return 0 if not failures else 1


def _full_suite_valid(payload: dict, identity: dict) -> bool:
    tests, failures = payload.get("tests"), payload.get("failures")
    errors, skipped = payload.get("errors"), payload.get("skipped")
    command = payload.get("command")
    return (
        _has_schema(payload, "SAIMAIL_D3_FULL_SUITE_1")
        and payload.get("candidate_version") == identity["version"]
        and payload.get("candidate_wheel_filename") == identity["wheel_filename"]
        and payload.get("candidate_wheel_sha256") == identity["wheel_sha256"]
        and payload.get("status") == "PASS"
        and type(tests) is int and tests > 0
        and type(failures) is int and failures == 0
        and type(errors) is int and errors == 0
        and type(skipped) is int and skipped == 0
        and payload.get("failed_tests") == []
        and payload.get("run_returncode") == 0
        and payload.get("source_tree_unchanged_during_run") is True
        and isinstance(command, list)
        and command[:5] == [sys.executable, "-m", "pytest", "-q", "-o"]
        and len(command) > 5 and command[5] == "addopts="
        and "--basetemp" in command and "--junitxml" in command
        and re.fullmatch(r"[0-9a-f]{64}", payload.get("junit_sha256", "")) is not None
        and payload.get("source_tree_fingerprint") == _source_tree_fingerprint())


def _full_suite_structure_valid(payload: dict, identity: dict) -> bool:
    """Platform-agnostic structural inspection of full-suite evidence record."""
    tests, failures = payload.get("tests"), payload.get("failures")
    errors, skipped = payload.get("errors"), payload.get("skipped")
    command = payload.get("command")
    return (
        _has_schema(payload, "SAIMAIL_D3_FULL_SUITE_1")
        and payload.get("candidate_version") == identity["version"]
        and payload.get("candidate_wheel_filename") == identity["wheel_filename"]
        and payload.get("candidate_wheel_sha256") == identity["wheel_sha256"]
        and payload.get("status") == "PASS"
        and type(tests) is int and tests > 0
        and type(failures) is int and failures == 0
        and type(errors) is int and errors == 0
        and type(skipped) is int and skipped == 0
        and payload.get("failed_tests") == []
        and payload.get("run_returncode") == 0
        and payload.get("source_tree_unchanged_during_run") is True
        and isinstance(command, list)
        and len(command) > 5 and "-m" in command and "pytest" in command
        and "--basetemp" in command and "--junitxml" in command
        and re.fullmatch(r"[0-9a-f]{64}", payload.get("junit_sha256", "")) is not None
    )


def _junit_counts(path: Path) -> tuple[int, int, int, int, list[str]]:
    root = ET.parse(path).getroot()
    suites = list(root) if root.tag == "testsuites" else [root]
    totals = {name: 0 for name in ("tests", "failures", "errors", "skipped")}
    failed_tests = []
    for suite in suites:
        for name in totals:
            totals[name] += int(suite.attrib.get(name, "0"))
        for case in suite.iter("testcase"):
            if any(case.find(tag) is not None for tag in ("failure", "error")):
                failed_tests.append("::".join(filter(None, (
                    case.attrib.get("classname"), case.attrib.get("name")))))
    return (totals["tests"], totals["failures"], totals["errors"],
            totals["skipped"], sorted(failed_tests))


def cmd_full_suite(args) -> int:
    _, identity = _candidate_identity(Path(args.bundle))
    before = _source_tree_fingerprint()
    base = Path(args.basetemp) if args.basetemp else Path(
        tempfile.mkdtemp(prefix="saimail-d3-pytest-"))
    if base.resolve().is_relative_to(ROOT.resolve()):
        raise SystemExit("basetemp must be outside the repository")
    if base.exists() and any(base.iterdir()):
        raise SystemExit(f"basetemp must be new or empty: {base}")
    base.mkdir(parents=True, exist_ok=True)
    junit = base / "junit.xml"
    command = [sys.executable, "-m", "pytest", "-q", "-o", "addopts=",
               "--basetemp", str(base), "--tb=short", "--junitxml", str(junit)]
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    try:
        tests, failures, errors, skipped, failed_tests = _junit_counts(junit)
        junit_sha256 = lar.sha256_file(junit)
    except (OSError, ET.ParseError, ValueError):
        tests, failures, errors, skipped, failed_tests = 0, 0, 1, 0, []
        junit_sha256 = None
    after = _source_tree_fingerprint()
    passed = (run.returncode == 0 and tests > 0 and failures == 0 and errors == 0
              and skipped == 0 and before == after)
    payload = {
        "schema": "SAIMAIL_D3_FULL_SUITE_1",
        "version": 1,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidate_version": identity["version"],
        "candidate_wheel_filename": identity["wheel_filename"],
        "candidate_wheel_sha256": identity["wheel_sha256"],
        "status": "PASS" if passed else "FAIL",
        "tests": tests,
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "failed_tests": failed_tests,
        "source_tree_fingerprint": after,
        "source_tree_unchanged_during_run": before == after,
        "run_returncode": run.returncode,
        "junit_sha256": junit_sha256,
        "command": command,
        "note": "Canonical Windows repository suite; counts parsed from its JUnit report.",
    }
    _write(args.out, payload, ("schema", "status", "tests", "failures", "errors", "skipped"))
    if run.stdout:
        print(run.stdout, end="")
    if run.stderr:
        print(run.stderr, file=sys.stderr, end="")
    return 0 if passed else 1


def _saipen_validation_valid(payload: dict, identity: dict) -> bool:
    if (not _has_schema(payload, "SAIMAIL_D3_SAIPEN_VALIDATION_1")
            or payload.get("candidate_version") != identity["version"]
            or payload.get("candidate_wheel_filename") != identity["wheel_filename"]
            or payload.get("candidate_wheel_sha256") != identity["wheel_sha256"]
            or payload.get("source_tree_fingerprint") != _source_tree_fingerprint()):
        return False
    baseline = payload.get("baseline")
    problems, warnings = payload.get("problems"), payload.get("warnings")
    new_failures = payload.get("new_candidate_attributable_failures")
    if (not isinstance(baseline, dict)
            or type(baseline.get("problems")) is not int
            or type(baseline.get("warnings")) is not int
            or type(problems) is not int or type(warnings) is not int
            or type(new_failures) is not int
            or not isinstance(payload.get("failure_lines"), list)
            or not isinstance(payload.get("warning_lines"), list)
            or any(not isinstance(line, str) for line in payload["failure_lines"])
            or any(not isinstance(line, str) for line in payload["warning_lines"])):
        return False
    expected_result = (
        "INHERITED_BASELINE_MATCH"
        if new_failures == 0 and problems <= baseline["problems"]
        and warnings <= baseline["warnings"] else "FAIL")
    baseline_signatures = baseline.get("problem_signatures")
    current_signatures = payload.get("problem_signatures")
    new_signatures = payload.get("new_problem_signatures")
    if (not isinstance(baseline_signatures, list)
            or not isinstance(current_signatures, list)
            or not isinstance(new_signatures, list)
            or any(not isinstance(item, dict) for item in
                   baseline_signatures + current_signatures + new_signatures)):
        return False
    def signature(item):
        return (item.get("rule_id"), item.get("subject_id"),
                item.get("detail_hash"))
    if any(not isinstance(item.get("rule_id"), str)
           or not isinstance(item.get("detail_hash"), str)
           or (item.get("subject_id") is not None
               and not isinstance(item.get("subject_id"), str))
           for item in baseline_signatures + current_signatures + new_signatures):
        return False
    baseline_set = {signature(item) for item in baseline_signatures}
    current_set = {signature(item) for item in current_signatures}
    new_set = {signature(item) for item in new_signatures}
    return (
        payload.get("result") == expected_result == "INHERITED_BASELINE_MATCH"
        and len(baseline_signatures) == baseline["problems"]
        and len(current_signatures) == problems
        and new_set == current_set - baseline_set
        and new_failures == len(new_set)
        and payload.get("canonical_validator_verdict") in ("PASS", "FAIL")
        and type(payload.get("validator_exit_code")) is int
        and payload.get("warning_details_available") is False
        and payload.get("warning_lines") == [])


def _problem_signature(problem: dict) -> dict:
    return {
        "rule_id": problem.get("rule_id"),
        "subject_id": problem.get("subject_id"),
        "detail_hash": problem.get("detail_hash"),
    }


def cmd_saipen_validation(args) -> int:
    _, identity = _candidate_identity(Path(args.bundle))
    status = _read(args.status_json)
    baseline_record = _read(args.baseline)
    conformance = status.get("conformance_status") or {}
    receipt = conformance.get("receipt") or {}
    findings = receipt.get("blocking_findings") or {}
    baseline = baseline_record.get("problem_signatures")
    problems = findings.get("problems")
    if (not _has_schema(baseline_record, "SAIMAIL_D3_SAIPEN_BASELINE_1")
            or not isinstance(baseline, list)
            or not isinstance(problems, list)
            or findings.get("status") != "complete"
            or conformance.get("status") not in ("CURRENT_FAIL", "CURRENT_PASS")
            or receipt.get("kind") != "conformance_receipt"
            or receipt.get("gate") != "core"
            or type(findings.get("problem_count")) is not int
            or len(problems) != findings.get("problem_count")
            or type(findings.get("warning_count")) is not int
            or len(baseline) != baseline_record.get("problems")
            or len(baseline) != len({json.dumps(item, sort_keys=True) for item in baseline})
            or type(baseline_record.get("warnings")) is not int):
        raise SystemExit(json.dumps({"status": "REFUSED",
                                     "code": "SAIPEN_VALIDATION_OR_BASELINE_INVALID"}))
    current_signatures = [_problem_signature(problem) for problem in problems]
    signatures = baseline + current_signatures
    if any(not isinstance(item.get("rule_id"), str)
           or not isinstance(item.get("detail_hash"), str)
           or (item.get("subject_id") is not None
               and not isinstance(item.get("subject_id"), str))
           for item in signatures):
        raise SystemExit(json.dumps({"status": "REFUSED",
                                     "code": "SAIPEN_FINDING_SIGNATURE_INVALID"}))
    baseline_by_key = {json.dumps(item, sort_keys=True): item for item in baseline}
    current_by_key = {json.dumps(item, sort_keys=True): item for item in current_signatures}
    new_keys = sorted(set(current_by_key) - set(baseline_by_key))
    new_signatures = [current_by_key[key] for key in new_keys]
    current_problem_count = findings["problem_count"]
    current_warning_count = findings["warning_count"]
    new_failures = len(new_signatures)
    inherited_match = (new_failures == 0
                       and current_problem_count <= baseline_record["problems"]
                       and current_warning_count <= baseline_record["warnings"])
    payload = {
        "schema": "SAIMAIL_D3_SAIPEN_VALIDATION_1",
        "version": 1,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candidate_version": identity["version"],
        "candidate_wheel_filename": identity["wheel_filename"],
        "candidate_wheel_sha256": identity["wheel_sha256"],
        "baseline": {
            "problems": baseline_record["problems"],
            "warnings": baseline_record["warnings"],
            "receipt_id": baseline_record.get("receipt_id"),
            "problem_signatures": baseline,
            "observed_before": baseline_record.get("observed_before"),
        },
        "problems": current_problem_count,
        "warnings": current_warning_count,
        "problem_signatures": current_signatures,
        "new_problem_signatures": new_signatures,
        "new_candidate_attributable_failures": new_failures,
        "failure_lines": [
            f"{item['rule_id']} [{item.get('subject_id') or 'global'}] "
            f"detail {item['detail_hash']}" for item in current_signatures],
        "warning_lines": [],
        "warning_details_available": False,
        "validator_summary": (status.get("validator") or {}).get("summary"),
        "canonical_validator_verdict": receipt.get("verdict"),
        "validator_exit_code": receipt.get("exit_code"),
        "receipt_id": receipt.get("receipt_id"),
        "canonical_timestamp_utc": receipt.get("timestamp_utc"),
        "canonical_source_tree_fingerprint": receipt.get("source_tree_fingerprint"),
        "source_tree_fingerprint": _source_tree_fingerprint(),
        "result": "INHERITED_BASELINE_MATCH" if inherited_match else "FAIL",
        "gate": receipt.get("gate"),
        "note": (
            "SAIPEN canonical validation itself remains FAIL with inherited findings. "
            "The active T-107 resume baseline is the pre-repair 4/23 receipt; the older "
            "a3 record's 3/21 counts predate T-108/T-109/T-110 and are retained as "
            "inherited baseline drift. Problem signatures are compared exactly; warning "
            "details were not emitted by the canonical status surface, so their count is "
            "compared and the limitation is recorded."),
    }
    _write(args.out, payload, ("schema", "result", "problems", "warnings",
                               "new_candidate_attributable_failures"))
    return 0 if inherited_match else 1


# --------------------------------------------------------------- capabilities


def _wheel_text_facts(wheel: Path) -> dict:
    with zipfile.ZipFile(wheel) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        names = {info.filename for info in infos}

        def _text(member: str) -> str:
            if member not in names:
                return ""
            return archive.read(member).decode("utf-8", errors="replace")

        workspace_source = _text("saimail/workspace.py")
        cli_source = _text("saimail_local.py")
        entry_points = _text(next(
            (i.filename for i in infos if i.filename.endswith(".dist-info/entry_points.txt")),
            ""))
        metadata = _text(next(
            (i.filename for i in infos if i.filename.endswith(".dist-info/METADATA")), ""))
    requires = [line for line in metadata.splitlines() if line.startswith("Requires-Dist:")]
    core_requires = [line for line in requires if "extra ==" not in line]
    return {
        "member_count": len(names),
        "member_names": sorted(names),
        "has_custody_module": "saimail/custody.py" in names,
        "identity_schemas": sorted(set(IDENTITY_SCHEMA_RE.findall(workspace_source))),
        "cli_custody_commands": "--custody" in cli_source and "custody" in cli_source,
        "cli_os_store": "os-store" in cli_source,
        "has_inbox_query_module": "saimail/inbox_query.py" in names,
        "has_query_projection": ("query_inbox" in workspace_source
                                 or "query_inbox" in cli_source),
        "has_cli_inbox_filters": "inbox" in cli_source and "from_seat" in cli_source,
        "has_correspondence_continuation": "reply_message" in workspace_source,
        "has_cli_reply": "reply" in cli_source and "reply_message" in cli_source,
        "has_gui_modules": all(f"saimail/gui_{part}.py" in names
                               for part in ("adapter", "app", "theme")),
        "console_scripts": sorted(re.findall(
            r"^([A-Za-z0-9_.-]+)\s*=", entry_points, flags=re.MULTILINE)),
        "gui_extra_declares_pyside6": any(
            "PySide6" in line and 'extra == "gui"' in line for line in requires),
        "pyside6_in_core_requires": any("PySide6" in line for line in core_requires),
        "core_requires": core_requires,
    }


def wheel_capabilities(wheel: Path) -> dict:
    facts = _wheel_text_facts(wheel)
    members = lar.wheel_members(wheel)
    return {
        "identity_kind": "EXACT_WHEEL_BYTES",
        "filename": wheel.name,
        "size_bytes": wheel.stat().st_size,
        "sha256": lar.sha256_file(wheel),
        "content_digest_sha256": lar.wheel_content_digest(members),
        "metadata_version": lar.wheel_metadata_version(wheel),
        **facts,
    }


def source_capabilities(root: Path) -> dict:
    workspace_source = (root / "saimail" / "workspace.py").read_text(encoding="utf-8")
    cli_source = (root / "saimail_local.py").read_text(encoding="utf-8")
    config = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    project = config["project"]
    return {
        "declared_version": (root / "VERSION").read_text(encoding="utf-8").strip(),
        "has_custody_module": (root / "saimail" / "custody.py").is_file(),
        "identity_schemas": sorted(set(IDENTITY_SCHEMA_RE.findall(workspace_source))),
        "cli_custody_commands": "--custody" in cli_source and "custody" in cli_source,
        "cli_os_store": "os-store" in cli_source,
        "has_inbox_query_module": (root / "saimail" / "inbox_query.py").is_file(),
        "has_query_projection": ("query_inbox" in workspace_source
                                 or "query_inbox" in cli_source),
        "has_cli_inbox_filters": "inbox" in cli_source and "from_seat" in cli_source,
        "has_correspondence_continuation": "reply_message" in workspace_source,
        "has_cli_reply": "reply" in cli_source and "reply_message" in cli_source,
        "has_gui_modules": all((root / "saimail" / f"gui_{part}.py").is_file()
                               for part in ("adapter", "app", "theme")),
        "console_scripts": sorted(project["scripts"]),
        "gui_extra_declares_pyside6": any(
            "PySide6" in dep for dep in project["optional-dependencies"].get("gui", [])),
        "core_requires": list(project["dependencies"]),
        "optional_extras": sorted(project["optional-dependencies"]),
    }


# -------------------------------------------------------------------- decide

PRODUCT_FEATURES = ("has_inbox_query_module", "has_correspondence_continuation",
                    "has_gui_modules")
ENTRYPOINT_FEATURES = ("console_scripts", "gui_extra_declares_pyside6")


def cmd_decide(args) -> int:
    frozen_wheel = ROOT / FROZEN_A2["bundle_dir"] / FROZEN_A2["wheel"]
    frozen = wheel_capabilities(frozen_wheel)
    if frozen["sha256"] != FROZEN_A2["sha256"]:
        raise SystemExit(json.dumps({
            "status": "REFUSED", "code": "FROZEN_A2_MUTATED",
            "detail": f"{frozen['sha256']} != {FROZEN_A2['sha256']}"}))
    import tempfile
    with tempfile.TemporaryDirectory(prefix="saimail-d3-decide-") as tmp:
        current_wheel = lar.build_wheel(ROOT, Path(tmp))
        current = wheel_capabilities(current_wheel)
    declared_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    product_delta = [name for name in ("P1", "V4-01", "V5-01")
                     if any(current[feature] and not frozen[feature]
                            for feature in _feature_group(name))]
    member_delta = sorted(set(current["member_names"]) - set(frozen["member_names"]))
    entrypoint_delta = {
        "frozen": frozen["console_scripts"],
        "current": current["console_scripts"],
        "added": sorted(set(current["console_scripts"]) - set(frozen["console_scripts"])),
    }
    dependency_delta = {
        "frozen_core_requires": frozen["core_requires"],
        "current_core_requires": current["core_requires"],
        "frozen_gui_extra": frozen["gui_extra_declares_pyside6"],
        "current_gui_extra_declares_pyside6": current["gui_extra_declares_pyside6"],
    }
    documentation_delta = {
        "frozen_candidate_docs": [
            "spec/18-LOCAL-ALPHA-v0.md", "spec/20-LOCAL-KEY-CUSTODY-v0.md",
            "spec/DECISIONS-D055.md"],
        "current_checkout_adds": [
            "spec/22-LOCAL-INBOX-QUERY-v0.md", "spec/24-LOCAL-CORRESPONDENCE-CONTINUATION-v0.md",
            "spec/25-DESKTOP-LOCAL-MESSENGER-v0.md", "spec/DECISIONS-D056.md",
            "CHANGELOG 0.0.2a3"],
    }
    version_mismatch = {
        "frozen_wheel_metadata_version": frozen["metadata_version"],
        "current_wheel_metadata_version": current["metadata_version"],
        "current_source_declared_version": declared_version,
        "mismatch": frozen["metadata_version"] != current["metadata_version"],
    }
    applicability = {
        "a1_external_proof": {
            "binding": "EXACT_WHEEL_BYTES", "sha256": FROZEN_A1["sha256"],
            "classification": "HISTORICAL_ONLY",
            "inherited_by_this_candidate": False},
        "a2_external_proof": {
            "binding": "EXACT_WHEEL_BYTES", "sha256": FROZEN_A2["sha256"],
            "proof_bytes_sha256": _a2_proof_bytes_sha256(),
            "classification": "HISTORICAL_ONLY",
            "inherited_by_this_candidate": False},
    }
    new_required = bool(product_delta) or bool(entrypoint_delta["added"]) or any([
        dependency_delta["current_gui_extra_declares_pyside6"]])
    outcome = "NEW_CANDIDATE_REQUIRED" if new_required else "NO_NEW_CANDIDATE"
    packet = {
        "schema": DECISION_SCHEMA,
        "version": 1,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "outcome": outcome,
        "decision_reason": (
            "The frozen 0.0.2a2 wheel predates the accepted post-a2 product delta "
            "(P1 local inbox query, V4-01 local correspondence continuation, V5-01 "
            "desktop GUI) and the saimail-gui console entrypoint / gui optional "
            "extra. Its external proof binds exactly its own wheel bytes. The "
            "current checkout is not externally verified, so the frozen a2 wheel "
            "cannot truthfully represent the current checkout and needs a new "
            "candidate identity."
            if outcome == "NEW_CANDIDATE_REQUIRED" else
            "Frozen a2 wheel capabilities already match the checkout."),
        "frozen_artifact": frozen,
        "current_built_wheel": current,
        "current_source_declared_version": declared_version,
        "package_member_delta": member_delta,
        "entrypoint_delta": entrypoint_delta,
        "dependency_extra_delta": dependency_delta,
        "documentation_delta": documentation_delta,
        "version_identity_mismatch": version_mismatch,
        "product_delta": product_delta,
        "release_evidence_applicability_boundary": applicability,
        "version_decision": {
            "current_frozen_artifact_version": frozen["metadata_version"],
            "current_source_declared_version": declared_version,
            "next_candidate_version": "0.0.2a3"},
        "custody_default_decision": "KEEP_RAW_DEFAULT",
        "publication": "NONE",
        "publication_authorization": "ABSENT",
    }
    _write(args.out, packet, ("schema", "outcome", "product_delta"))
    return 0 if outcome == "NEW_CANDIDATE_REQUIRED" else 0


def _feature_group(name: str):
    if name == "P1":
        return ("has_inbox_query_module", "has_query_projection", "has_cli_inbox_filters")
    if name == "V4-01":
        return ("has_correspondence_continuation", "has_cli_reply")
    if name == "V5-01":
        return ("has_gui_modules",)
    return ()


def _a2_proof_bytes_sha256() -> str | None:
    proof = ROOT / "release" / "evidence" / "a2" / "external_linux_verification.json"
    if not proof.is_file():
        return None
    return lar.sha256_file(proof)


# ---------------------------------------------------------------- immutability


def cmd_immutability(args) -> int:
    a1 = lar.verify_historical_a1(ROOT)
    a2_report = lar.verify_historical_a2(ROOT)
    a2_bundle = ROOT / FROZEN_A2["bundle_dir"]
    a2_manifest = _manifest(a2_bundle)
    a2_external = ROOT / "release" / "evidence" / "a2" / "external_linux_verification.json"
    a2_acceptance = ROOT / "release" / "evidence" / "a2" / "external_verification_record.json"
    external_proof = a2_external.is_file()
    external_hash = lar.sha256_file(a2_external) if external_proof else None
    acceptance = _read(a2_acceptance) if a2_acceptance.is_file() else {}
    checks = {
        "a1_unchanged": a1["status"] == "PASS",
        "a2_unchanged": a2_report["status"] == "PASS",
        "a2_manifest_not_published": a2_manifest.get("publication_status") == "NOT_PUBLISHED",
        "a2_external_proof_bytes_match": (
            external_proof and external_hash == A2_EXTERNAL_PROOF_SHA256),
        "a2_external_proof_binds_a2_wheel": (
            acceptance.get("candidate_sha256") == FROZEN_A2["sha256"]),
        "a2_acceptance_not_rewritten": acceptance.get("status") == "PASS",
    }
    ok = all(checks.values())
    payload = {
        "schema": IMMUTABILITY_SCHEMA,
        "version": 1,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS" if ok else "FAIL",
        "a1": a1,
        "a2": a2_report,
        "a2_external_proof_sha256": external_hash,
        "checks": checks,
    }
    _write(args.out, payload, ("schema", "status", "a1", "a2"))
    return 0 if ok else 1


# -------------------------------------------------------------------- claims


def cmd_claims(args) -> int:
    bundle = Path(args.bundle)
    verification = _read(args.verification)
    proof = _read(args.osstore_proof)
    manifest, identity = _candidate_identity(bundle)
    expected = identity["wheel_sha256"]
    if not _verification_valid(verification, identity):
        raise SystemExit(json.dumps({"status": "REFUSED",
                                     "code": "VERIFICATION_NOT_BOUND_TO_FROZEN_A3"}))
    if not _osstore_valid(proof, identity):
        raise SystemExit(json.dumps({"status": "REFUSED",
                                     "code": "OSSTORE_PROOF_NOT_BOUND_TO_FROZEN_A3"}))
    checks = proof.get("checks") or {}
    product = (manifest.get("content_proof") or {}).get("product_delta") or {}
    product_checks = product.get("checks") or {}
    p1v401 = verification.get("p1_v401") or {}
    p1v401_checks = p1v401.get("checks") or {}
    external_supplied = bool(getattr(args, "external_acceptance", None))
    external = _read(args.external_acceptance) if external_supplied else {}
    if external_supplied and not _acceptance_is_strict(external, identity):
        raise SystemExit(json.dumps({
            "status": "REFUSED", "code": "EXTERNAL_ACCEPTANCE_NOT_STRICT_A3_PROOF"}))
    external_ok = external_supplied

    def _ok(name, condition):
        return {"claim": name, "status": "PROVEN" if condition else "NOT_PROVEN"}

    proven = [
        _ok("package_install", verification.get("install", {}).get("status") == "INSTALLED"),
        _ok("module_resolution_outside_checkout",
            (verification.get("module_resolution") or {}).get(
                "resolved_inside_environment") is True),
        _ok("base_raw_workflow",
            (verification.get("v201_acceptance") or {}).get("status") == "PASS"
            and (verification.get("v201_direct_command") or {}).get("custody_mode") == "raw"),
        _ok("first_run_raw_custody_notice",
            (verification.get("v201_direct_command") or {}).get("first_run_notice") is True),
        _ok("custody_module_shipped", manifest.get("content_proof", {}).get("status") == "PASS"),
        _ok("os_store_backend_classification",
            proof.get("backend") == "keyring.backends.Windows.WinVaultKeyring"),
        _ok("os_store_init", checks.get("protected_init_created") is True),
        _ok("protected_metadata_no_raw_keys",
            checks.get("no_raw_private_fields") is True
            and checks.get("no_private_material_in_workspace") is True),
        _ok("custody_restart_stable", checks.get("restart_load_stable") is True),
        _ok("custody_status_protected", checks.get("custody_status_protected") is True),
        _ok("installed_send_list_open",
            checks.get("send_accepted") is True and checks.get("list_semantics_valid") is True
            and checks.get("open_semantics_valid") is True),
        _ok("migration", checks.get("migration_proof") is True
            and (proof.get("migration") or {}).get("fingerprints_preserved") is True),
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
        _ok("p1_inbox_query_installed",
            p1v401_checks.get("p1_query_command") is True
            and p1v401_checks.get("p1_query_found") is True
            and p1v401_checks.get("p1_query_metadata_only") is True),
        _ok("v401_correspondence_continuation_installed",
            p1v401_checks.get("v401_reply_command") is True
            and p1v401_checks.get("v401_reply_ref") is True
            and p1v401_checks.get("v401_reply_delivered") is True),
        _ok("v501_gui_in_wheel",
            product_checks.get("v501_gui_adapter") is True
            and product_checks.get("v501_gui_app") is True
            and product_checks.get("v501_gui_theme") is True
            and product_checks.get("v501_gui_entrypoint") is True
            and product_checks.get("v501_gui_extra_declares_pyside6") is True
            and product_checks.get("pyside6_not_core_dependency") is True),
    ]
    externally = [
        _ok("exact_wheel_identity",
            external.get("external_proof_sha256") is not None
            and external.get("candidate_sha256") == expected),
        _ok("clean_install_in_external_environment",
            (external.get("checks") or {}).get("field:install.status") is True),
        _ok("base_raw_default_local_workflow",
            (external.get("checks") or {}).get("field:v201_acceptance.status") is True),
        _ok("fg05", (external.get("checks") or {}).get("field:fg05.status") is True),
        _ok("fg06_utility_conditional",
            (external.get("checks") or {}).get("field:fg06.outcome_category") is True),
        _ok("v201_workflow",
            (external.get("checks") or {}).get("field:v201_acceptance.status") is True),
        _ok("privacy_gate", (external.get("checks") or {}).get("field:privacy.status") is True),
        _ok("zero_runtime_network_model_provider",
            (external.get("checks") or {}).get(
                "field:runtime_counters.network_attempts") is True),
    ] if external_ok else []

    ok = all(entry["status"] == "PROVEN" for entry in proven) and (
        not external or (external_ok and all(entry["status"] == "PROVEN" for entry in externally)))
    payload = {
        "schema": CLAIM_SCHEMA,
        "version": 1,
        "created_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "PASS" if ok else "FAIL",
        "candidate": {
            **identity,
        },
        "proven_on_windows_exact_a3_wheel": proven,
        "proven_externally_on_exact_a3_wheel": externally,
        "not_yet_externally_proven": (
            ["os-store custody on any non-Windows platform"] if external_ok else [
                "this exact a3 wheel on a genuinely separate external environment (G13)",
                "os-store custody on any non-Windows platform",
            ]),
        "boundaries": [
            "os-store backend evidence is Windows-specific (WinVaultKeyring)",
            "the base verifier tests P1/V4-01 but not os-store custody",
            "the a2 and a1 external proofs bind their own frozen wheel bytes only and "
            "are never inherited",
            "publication authorization (G17) is absent; publication is forbidden",
        ],
    }
    _write(args.out, payload, ("schema", "status"))
    return 0 if ok else 1


# --------------------------------------------------------------------- gates


def cmd_gates(args) -> int:
    bundle = Path(args.bundle)
    manifest, identity = _candidate_identity(bundle)
    verification = _read(args.verification)
    proof = _read(args.osstore_proof)
    privacy_report = _read(args.privacy)
    integrity_report = _read(args.integrity)
    repro = _read(args.repro)
    if not _verification_valid(verification, identity):
        raise SystemExit(json.dumps({"status": "REFUSED",
                                     "code": "VERIFICATION_NOT_BOUND_TO_FROZEN_A3"}))
    if not _osstore_valid(proof, identity):
        raise SystemExit(json.dumps({"status": "REFUSED",
                                     "code": "OSSTORE_PROOF_NOT_BOUND_TO_FROZEN_A3"}))
    expected = identity["wheel_sha256"]
    external_supplied = bool(getattr(args, "external_acceptance", None))
    external = _read(args.external_acceptance) if external_supplied else {}
    if external_supplied and not _acceptance_is_strict(external, identity):
        raise SystemExit(json.dumps({
            "status": "REFUSED", "code": "EXTERNAL_ACCEPTANCE_NOT_STRICT_A3_PROOF"}))
    external_ok = external_supplied
    gui_matrix = _read(args.gui_matrix) if getattr(args, "gui_matrix", None) else {}
    version_file = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    checks = proof.get("checks") or {}
    suite = _read(args.full_suite) if args.full_suite else {}
    saipen = _read(args.saipen) if args.saipen else {}
    documentation = _read(args.documentation) if getattr(
        args, "documentation", None) else {}
    documentation_ok = bool(documentation) and _documentation_record_valid(
        documentation, identity, args)
    suite_status = ("NOT_RUN" if not suite else
                    "PASS" if _full_suite_valid(suite, identity) else "FAIL")
    saipen_status = ("NOT_RUN" if not saipen else
                     "PASS" if _saipen_validation_valid(saipen, identity) else "FAIL")

    product = (manifest.get("content_proof") or {}).get("product_delta") or {}
    product_checks = product.get("checks") or {}
    p1v401 = verification.get("p1_v401") or {}
    pchecks = p1v401.get("checks") or {}
    gui_proven = _gui_valid(gui_matrix, identity)

    gates = [
        {"id": "G1", "name": "VERSION CONSISTENCY",
         "status": "PASS" if (manifest.get("package_version") == version_file
                              and verification.get("saimail_local_version", {}).get(
                                  "reported") == version_file) else "FAIL",
         "evidence": "VERSION, wheel metadata, saimail-local --version"},
        {"id": "G2", "name": "PACKAGE CONTENT",
         "status": "PASS" if (manifest.get("content_proof") or {}).get("status") == "PASS"
                   and _repro_valid(repro, identity) else "FAIL",
         "evidence": "manifest content_proof (custody + product_delta P1/V4-01/V5-01) "
                     "+ two-build content identity"},
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
                   else "FAIL", "evidence": "installed FG-05 result"},
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
         "status": "PASS" if _red_controls_valid(
             integrity_report, identity, "integrity") else "FAIL",
         "evidence": "a3 bundle integrity + wheel/hash/checksum red controls"},
        {"id": "G11", "name": "PRIVACY",
         "status": "PASS" if _red_controls_valid(
             privacy_report, identity, "privacy") else "FAIL",
         "evidence": "a3 candidate privacy scan + planted marker/key-material red controls"},
        {"id": "G12", "name": "RUNTIME NETWORK/MODEL",
         "status": "PASS" if all((verification.get("runtime_counters") or {}).get(
             field) == 0 for field in ("network_attempts", "model_calls", "provider_calls"))
                   else "FAIL",
         "evidence": "runtime counters zero on the verification path"},
        {"id": "G13", "name": "EXTERNAL INSTALL",
         "status": "PASS" if external_ok else "PENDING_EXTERNAL",
         "evidence": (
             "external LOCAL_ALPHA_VERIFICATION_1 PASS against the exact a3 wheel "
             "(proof sha256 %s)" % external.get("external_proof_sha256", "?")
             if external_ok else
             "no genuinely separate environment on this host; blocked until the exact "
             "a3 wheel (sha256 %s) runs in one (READY_FOR_EXTERNAL_INSTALL_PROOF)" % expected)},
        {"id": "G14", "name": "DOCUMENTATION",
         "status": "PASS" if documentation_ok else
                  "FAIL" if documentation else "NOT_RUN",
         "evidence": "candidate-bound documentation validation of canonical ticket state, "
                     "current-state, roadmap and external request"},
        {"id": "G15", "name": "FULL SUITE", "status": suite_status,
         "evidence": "canonical full pytest run with parsed JUnit counts and current source fingerprint"},
        {"id": "G16", "name": "SAIPEN", "status": saipen_status,
         "evidence": "canonical SAIPEN validation bound to current source fingerprint and baseline"},
        {"id": "G17", "name": "PUBLICATION AUTHORIZATION", "status": "ABSENT",
         "evidence": "operator authorization absent; publication forbidden, not an "
                     "engineering blocker"},
        {"id": "G18", "name": "P1 PRODUCT SURFACE",
         "status": "PASS" if (pchecks.get("p1_query_command") is True
                              and pchecks.get("p1_query_found") is True
                              and pchecks.get("p1_query_metadata_only") is True
                              and product_checks.get("p1_inbox_query_module") is True)
                   else "FAIL",
         "evidence": "installed-wheel P1 query proof + manifest product_delta"},
        {"id": "G19", "name": "V4-01 PRODUCT SURFACE",
         "status": "PASS" if (pchecks.get("v401_reply_command") is True
                              and pchecks.get("v401_reply_ref") is True
                              and pchecks.get("v401_reply_delivered") is True
                              and product_checks.get("v401_correspondence_continuation") is True)
                   else "FAIL",
         "evidence": "installed-wheel V4-01 reply proof + manifest product_delta"},
        {"id": "G20", "name": "V5-01 GUI PRODUCT SURFACE",
         "status": ("PASS" if gui_proven and product_checks.get(
             "v501_gui_extra_declares_pyside6") is True and product_checks.get(
                 "pyside6_not_core_dependency") is True else
             "NOT_RUN" if not gui_matrix else "FAIL"),
         "evidence": ("GUI clean-install matrix (gui extra installs PySide6, saimail-gui "
                      "entrypoint, offscreen acceptance over the canonical local API)"
                      if gui_proven else
                      "GUI matrix not supplied; manifest product_delta only")},
    ]
    required_local = {f"G{n}" for n in range(1, 13)} | {"G14", "G15", "G16"} | {"G18", "G19", "G20"}
    by_id = {gate["id"]: gate for gate in gates}
    local_green = all(by_id[gid]["status"] == "PASS" for gid in required_local)
    blocked_local = [gid for gid in sorted(required_local)
                     if by_id[gid]["status"] not in ("PASS",)]
    g13_pending = by_id["G13"]["status"] == "PENDING_EXTERNAL"
    if local_green and external_ok:
        terminal = "DONE"
        status = "PASS"
    elif local_green and g13_pending:
        terminal = "READY_FOR_EXTERNAL_INSTALL_PROOF"
        status = "PASS"
    else:
        terminal = "LOCAL_BLOCKED"
        status = "FAIL"
    gate_created_utc = getattr(args, "created_utc", None) or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    consumed_evidence = {}
    inputs_to_check = [
        ("verification", args.verification, verification),
        ("osstore_proof", args.osstore_proof, proof),
        ("privacy", args.privacy, privacy_report),
        ("integrity", args.integrity, integrity_report),
        ("repro", args.repro, repro),
    ]
    if getattr(args, "gui_matrix", None):
        inputs_to_check.append(("gui_matrix", args.gui_matrix, gui_matrix))
    if getattr(args, "documentation", None):
        inputs_to_check.append(("documentation", args.documentation, documentation))
    if getattr(args, "full_suite", None):
        inputs_to_check.append(("full_suite", args.full_suite, suite))
    if getattr(args, "saipen", None):
        inputs_to_check.append(("saipen", args.saipen, saipen))
    if external_supplied:
        inputs_to_check.append(("external_acceptance", args.external_acceptance, external))

    for logical_id, file_path, data in inputs_to_check:
        p = Path(file_path)
        created = data.get("created_utc")
        if created and gate_created_utc < created:
            raise SystemExit(json.dumps({
                "status": "REFUSED",
                "code": "GATE_CHRONOLOGY_VIOLATION",
                "detail": f"{logical_id} created_utc ({created}) is after gate_evaluation ({gate_created_utc})",
            }))
        consumed_evidence[logical_id] = {
            "logical_id": logical_id,
            "path": str(file_path),
            "schema": data.get("schema"),
            "created_utc": created,
            "sha256": lar.sha256_file(p),
        }

    payload = {
        "schema": GATE_SCHEMA,
        "version": 1,
        "created_utc": gate_created_utc,
        "status": status,
        "candidate": {
            **identity,
        },
        "gates": gates,
        "required_local_gates": sorted(required_local),
        "consumed_evidence": consumed_evidence,
        "g17_note": "G17 ABSENT does not block D3 engineering closure; publication stays forbidden",
        "terminal": terminal,
        "blocked_local_gates": blocked_local or None,
        "publication": "NONE" if terminal != "DONE" else "NONE",
    }
    _write(args.out, payload, ("schema", "status", "terminal"))
    return 0 if payload["status"] == "PASS" else 1


def _gate_evaluation_valid(payload: dict, identity: dict) -> bool:
    if (not _has_schema(payload, GATE_SCHEMA)
            or not _candidate_matches(payload, identity)
            or payload.get("status") != "PASS"
            or payload.get("blocked_local_gates") is not None):
        return False
    gate_created = payload.get("created_utc")
    if not gate_created:
        return False
    consumed = payload.get("consumed_evidence")
    if not isinstance(consumed, dict) or not consumed:
        return False

    required_inputs = {"verification", "osstore_proof", "privacy", "integrity", "repro", "documentation", "full_suite", "saipen"}
    if not required_inputs.issubset(consumed.keys()):
        return False

    for logical_id, item in consumed.items():
        if not isinstance(item, dict):
            return False
        item_created = item.get("created_utc")
        if item_created and gate_created < item_created:
            return False
        item_path = item.get("path")
        recorded_sha256 = item.get("sha256")
        if not item_path or not recorded_sha256:
            return False
        p = Path(item_path)
        if not p.is_file():
            return False
        if lar.sha256_file(p) != recorded_sha256:
            return False

    gates = {g["id"]: g["status"] for g in payload.get("gates", [])}
    required_local = set(payload.get("required_local_gates", []))
    if not all(gates.get(gid) == "PASS" for gid in required_local):
        return False

    return True


# ------------------------------------------------------------------ delegated


def _delegate(name: str, args) -> int:
    """Run a generic a2 driver subcommand under D3 schema identities."""
    a2.RED_SCHEMA = "SAIMAIL_D3_RED_CONTROLS_1"
    a2.REPRO_SCHEMA = "SAIMAIL_D3_REPRODUCIBILITY_1"
    return getattr(a2, name)(args)


def cmd_integrity(args) -> int:
    _, identity = _candidate_identity(Path(args.bundle))
    result = _delegate("cmd_integrity", args)
    payload = _read(args.out)
    payload["candidate"] = identity
    payload["failures"] = [] if result == 0 else ["INTEGRITY_OR_RED_CONTROL_FAILED"]
    _write(args.out, payload, ("schema", "status"))
    return result


def cmd_privacy(args) -> int:
    _, identity = _candidate_identity(Path(args.bundle))
    result = _delegate("cmd_privacy", args)
    payload = _read(args.out)
    payload["candidate"] = identity
    payload["failures"] = [] if result == 0 else ["PRIVACY_OR_RED_CONTROL_FAILED"]
    _write(args.out, payload, ("schema", "status"))
    return result


def cmd_repro(args) -> int:
    _, identity = _candidate_identity(Path(args.first_bundle))
    second_bundle = Path(args.second_bundle)
    result = _delegate("cmd_repro", args)
    payload = _read(args.out)
    second_manifest = _manifest(second_bundle)
    second_wheel = second_bundle / second_manifest["wheel"]["filename"]
    second_digest = lar.wheel_content_digest(lar.wheel_members(second_wheel))
    if (payload.get("selected_candidate") != identity["wheel_sha256"]
            or (payload.get("first") or {}).get("sha256") != identity["wheel_sha256"]
            or second_manifest.get("package_version") != identity["version"]
            or second_manifest.get("publication_status") != "NOT_PUBLISHED"
            or (second_manifest.get("wheel") or {}).get("filename")
            != identity["wheel_filename"]
            or (second_manifest.get("wheel") or {}).get("sha256")
            != (payload.get("second") or {}).get("sha256")
            or second_digest != a3_acceptor.A3_CONTENT_DIGEST
            or (payload.get("second") or {}).get("content_digest_sha256")
            != a3_acceptor.A3_CONTENT_DIGEST):
        raise SystemExit(json.dumps({"status": "REFUSED",
                                     "code": "REPRODUCIBILITY_NOT_BOUND_TO_A3"}))
    payload["candidate"] = identity
    _write(args.out, payload, ("schema", "status", "byte_identical_wheels"))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    decide = sub.add_parser("decide")
    decide.add_argument("--out", required=True)
    decide.set_defaults(func=cmd_decide)

    immutability = sub.add_parser("immutability")
    immutability.add_argument("--out", required=True)
    immutability.set_defaults(func=cmd_immutability)

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

    closure_ctx = sub.add_parser("closure-context")
    closure_ctx.add_argument("--bundle", required=True)
    closure_ctx.add_argument("--out", required=True)
    closure_ctx.add_argument("--state", default=None)
    closure_ctx.add_argument("--board", default=None)
    closure_ctx.add_argument("--current-state", default=None)
    closure_ctx.add_argument("--roadmap", default=None)
    closure_ctx.add_argument("--external-request", default=None)
    closure_ctx.add_argument("--closure-event", default="E-1502")
    closure_ctx.add_argument("--source-fingerprint", default=None)
    closure_ctx.add_argument("--created-utc", default=None)
    closure_ctx.set_defaults(func=cmd_closure_context)

    documentation = sub.add_parser("documentation")
    documentation.add_argument("--bundle", required=True)
    documentation.add_argument("--out", required=True)
    documentation.add_argument("--closure-context", default=None)
    documentation.add_argument("--state", default=None)
    documentation.add_argument("--board", default=None)
    documentation.add_argument("--current-state", default=None)
    documentation.add_argument("--roadmap", default=None)
    documentation.add_argument("--external-request", default=None)
    documentation.add_argument("--created-utc", default=None)
    documentation.set_defaults(func=cmd_documentation)

    full_suite = sub.add_parser("full-suite")
    full_suite.add_argument("--bundle", required=True)
    full_suite.add_argument("--out", required=True)
    full_suite.add_argument("--basetemp", default=None)
    full_suite.set_defaults(func=cmd_full_suite)

    saipen_validation = sub.add_parser("saipen-validation")
    saipen_validation.add_argument("--bundle", required=True)
    saipen_validation.add_argument("--status-json", required=True)
    saipen_validation.add_argument("--baseline", required=True)
    saipen_validation.add_argument("--out", required=True)
    saipen_validation.set_defaults(func=cmd_saipen_validation)

    claims = sub.add_parser("claims")
    claims.add_argument("--bundle", required=True)
    claims.add_argument("--verification", required=True)
    claims.add_argument("--osstore-proof", required=True)
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
    gates.add_argument("--gui-matrix", default=None)
    gates.add_argument("--external-acceptance", default=None)
    gates.add_argument("--full-suite", default=None)
    gates.add_argument("--saipen", default=None)
    gates.add_argument("--documentation", default=None)
    gates.add_argument("--closure-context", default=None)
    gates.add_argument("--state", default=None)
    gates.add_argument("--board", default=None)
    gates.add_argument("--current-state", default=None)
    gates.add_argument("--roadmap", default=None)
    gates.add_argument("--external-request", default=None)
    gates.add_argument("--created-utc", default=None)
    gates.add_argument("--out", required=True)
    gates.set_defaults(func=cmd_gates)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
