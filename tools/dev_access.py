"""DEV ACCESS guardrail for SAIMAIL product work while the canonical SAIPEN
lane is occupied by unrelated protocol/closure work.

Manages only `.devaccess/**`. Never writes `.saipen/**`, `humbox/**` or any
release/frozen evidence surface. A guardrail, not a workflow engine.

    python tools/dev_access.py status
    python tools/dev_access.py admit [--dry-run]
    python tools/dev_access.py begin DEV-20260921-0410-gui-polish \\
        --request "<operator request>" --owns "saimail/**,tests/**" \\
        [--expects saimail/gui_app.py,tests/test_gui_surface.py]
    python tools/dev_access.py check DEV-20260921-0410-gui-polish
    python tools/dev_access.py finish-check DEV-20260921-0410-gui-polish
    python tools/dev_access.py finish DEV-20260921-0410-gui-polish \\
        --focused "pytest tests/test_x.py -> PASS" \\
        --lint "ruff -> clean" [--limitations "..."]
    python tools/dev_access.py disable --reason canonical_lane_available

v2 (this revision) owns the v1 -> v2 bootstrap migration:

* `admit` is the ONLY migration path. It upgrades a `SAIMAIL_DEV_ACCESS_1`
  ACTIVE.json to the v2 schema, derives `expires_at` from the recorded
  activation time plus `ttl_seconds`, and reconciles work records that v1 left
  open with no way to close them (every v1 guardrail verb refuses while
  ACTIVE is disabled, so an unfinished record could never advance). Original
  record bytes and both hashes are preserved inside the migration evidence.
* `check` persists the measured delta on the work record instead of holding it
  in stdout only, so drift is tracked between checkpoints and not just at the
  finish boundary.
* `finish-check` is the explicit finish gate: zero measured delta or any
  guardrail failure is recorded as FAIL and refuses `finish` until a later
  check passes.
* the STATE parser reads the frontmatter fence ONLY. A prose body that happens
  to contain `phase:` or `task:` is not authority -- the previous loose line
  scan would read fields out of exactly the kind of chat-shaped report that has
  already destroyed one project STATE.md.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACTIVE_PATH = ROOT / ".devaccess" / "ACTIVE.json"
WORK_DIR = ROOT / ".devaccess" / "work"
EVIDENCE_DIR = ROOT / ".devaccess" / "evidence"
STATE_PATH = ROOT / ".saipen" / "STATE.md"

FORBIDDEN_PATHS = [
    ".saipen/STATE.md",
    ".saipen/BOARD.md",
    ".saipen/LOG.md",
    ".saipen/intake/**",
    ".saipen/kitchen/**",
    ".saipen/evidence/**",
    ".saipen/**",
    "humbox/CURRENT-STATE.md",
    "humbox/FUTURE-GATES*.md",
    "release/**",
]

PROTECTED_ACTIONS = [
    "publish", "tag", "push", "create_github_release",
    "upload_package_artifacts", "version_bump", "rebuild_frozen_a2",
]

# v2 schema contract. The legacy names stay known so the surface can REFUSE a
# v1 overlay by name and route it to `admit`; they are never silently accepted.
ACTIVE_SCHEMA = "SAIMAIL_DEV_ACCESS_2"
ACTIVE_SCHEMA_VERSION = 2
LEGACY_ACTIVE_SCHEMAS = {"SAIMAIL_DEV_ACCESS_1": 1}
BASELINE_SCHEMA = "DEV_ACCESS_BASELINE_2"
LEGACY_BASELINE_SCHEMAS = {"DEV_ACCESS_BASELINE_1": 1}
RESULT_SCHEMA = "DEV_ACCESS_RESULT_2"
LEGACY_RESULT_SCHEMAS = {"DEV_ACCESS_RESULT_1": 1}
MIGRATION_SCHEMA = "DEV_ACCESS_MIGRATION_1"
RECONCILED_STATUS = "reconciled"
DEFAULT_TTL_SECONDS = 21600

SNAPSHOT_FILE_CAP = 20000
SNAPSHOT_BYTE_CAP = 16 * 1024 * 1024
EXEMPT_WALK_DIRS = {
    ".git", "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache",
}


class SnapshotLimit(RuntimeError):
    pass


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def relative_to_root(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _matches(rel: str, patterns) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern):
            return True
    return False


def _walk_files():
    for path in ROOT.rglob("*"):
        if any(part in EXEMPT_WALK_DIRS for part in path.parts):
            continue
        if path.is_file():
            yield path


def _snapshot(patterns) -> dict[str, str]:
    if not patterns:
        return {}
    out: dict[str, str] = {}
    for path in _walk_files():
        rel = relative_to_root(path)
        if not _matches(rel, patterns):
            continue
        if len(out) >= SNAPSHOT_FILE_CAP:
            raise SnapshotLimit(
                f"snapshot matched more than {SNAPSHOT_FILE_CAP} files; "
                "narrow the declared paths"
            )
        if path.stat().st_size > SNAPSHOT_BYTE_CAP:
            out[rel] = f"size:{path.stat().st_size}"
            continue
        out[rel] = sha256_file(path)
    return out


def _snapshot_diff(before: dict, after: dict) -> dict:
    return {
        "changed": sorted(
            rel for rel in before.keys() & after.keys()
            if before[rel] != after[rel]
        ),
        "added": sorted(after.keys() - before.keys()),
        "removed": sorted(before.keys() - after.keys()),
    }


def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        return {"__corrupt__": str(exc)}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _load_active():
    data = _load_json(ACTIVE_PATH)
    if data is not None and "__corrupt__" in data:
        return {"__corrupt__": data["__corrupt__"]}
    return data


#: Fields the guardrail is allowed to read out of canonical STATE. Nothing
#: else in that file is this tool's business, and prose is NEVER a field.
STATE_FIELDS = ("phase", "task", "mode", "schema_version")
STATE_FENCE_ERROR = "no opening --- frontmatter fence"


def _read_canonical_state() -> dict:
    """Fence-bounded STATE reader (v2).

    Only the region between the opening and closing `---` fence is parsed. A
    file with no opening fence has NO fields at all -- the loose v1 line scan
    would have read `phase:`/`task:` out of a chat-shaped report body, which is
    not a hypothetical: that is the exact shape that destroyed this project's
    `.saipen/STATE.md` on 21.09.26 and left every canonical verb refusing.
    """
    if not STATE_PATH.is_file():
        return {}
    lines = STATE_PATH.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {"__fence_error__": STATE_FENCE_ERROR}
    out: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return out
        match = re.match(r"^(\w+):\s*(.*)$", line.strip())
        if match and match.group(1) in STATE_FIELDS:
            value = match.group(2).strip().strip('"').strip("'")
            out[match.group(1)] = value
    return {"__fence_error__": "no closing --- frontmatter fence"}


def _state_phase_task(state: dict) -> tuple[str, str]:
    return state.get("phase", "unknown"), state.get("task", "unknown")


def _canonical_lane_available() -> bool:
    state = _read_canonical_state()
    return state.get("phase") == "DONE" and (
        state.get("task", "") in ("none", "", "None")
    )


def _parse_utc(text) -> datetime | None:
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        parsed = datetime.fromisoformat(text.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _expiry_due(active: dict) -> str | None:
    """Why the overlay must switch itself off now, or None.

    Two independent self-expiry brakes, highest first: the canonical lane is
    free again (the reason the overlay exists at all), or the declared TTL ran
    out. v1 knew only the first, so an overlay whose lane stayed occupied was
    unbounded in time while already carrying `expires_at` and `ttl_seconds`.
    """
    if _canonical_lane_available():
        return "canonical_lane_available"
    expires_at = _parse_utc(active.get("expires_at"))
    if expires_at is not None and datetime.now(UTC) >= expires_at:
        return "ttl_expired"
    return None


def _expire_if_due(active: dict | None) -> dict | None:
    if not active or not active.get("enabled"):
        return active
    reason = _expiry_due(active)
    if reason:
        active["enabled"] = False
        active["disabled_at"] = now_utc()
        active["disable_reason"] = reason
        _save_json(ACTIVE_PATH, active)
    return active


# v1 name kept as the canonical mutation point for the pre-migration readers.
_expire_if_lane_available = _expire_if_due


def _base(pattern: str) -> str:
    return pattern.rstrip("/*").rstrip("/")


def _overlap(a: str, b: str) -> bool:
    ba, bb = _base(a), _base(b)
    return ba == bb or ba.startswith(bb + "/") or bb.startswith(ba + "/")


def _parse_paths(text: str) -> list[str]:
    return [p for p in re.split(r"[,\s]+", text or "") if p]


def _active_conflict(owns: list[str], exclude: str | None) -> tuple[str, str] | None:
    for record_path in sorted(WORK_DIR.glob("*.json")):
        if exclude and record_path.stem == exclude:
            continue
        record = _load_json(record_path) or {}
        if record.get("status") != "active":
            continue
        for mine in owns:
            for theirs in record.get("writable_paths", []):
                if _overlap(mine, theirs):
                    return record_path.stem, mine
    return None


def _refuse(code: str, **extra) -> int:
    payload = {"status": "REFUSED", "code": code}
    payload.update(extra)
    print(json.dumps(payload, indent=2))
    return 1


def _active_schema_problem(active: dict) -> dict | None:
    """The refusal a legacy or unknown overlay schema earns, or None for v2.

    A schema bump is not a comment: a `SAIMAIL_DEV_ACCESS_1` overlay is refused
    BY NAME with the one command that migrates it, instead of being read under
    v2 semantics nobody ever verified for those bytes.
    """
    schema = active.get("schema")
    if schema == ACTIVE_SCHEMA:
        return None
    if schema in LEGACY_ACTIVE_SCHEMAS:
        return {
            "code": "DEV_ACCESS_V1_REQUIRES_ADMIT",
            "schema": schema,
            "detail": (
                f"{schema} is the superseded v1 overlay schema; the v2 bootstrap "
                "migration must admit these bytes before any guardrail verb "
                "reads them"
            ),
            "next_command": "python tools/dev_access.py admit",
        }
    return {
        "code": "DEV_ACCESS_SCHEMA_UNSUPPORTED",
        "schema": schema,
        "detail": f"unsupported DEV ACCESS overlay schema {schema!r}",
    }


def _schema_gate(active: dict) -> int | None:
    problem = _active_schema_problem(active)
    if problem is None:
        return None
    code = problem.pop("code")
    return _refuse(code, **problem)


def _open_work_records() -> list[str]:
    """Work records still `active` with no result -- v1 could orphan these."""
    open_ids = []
    for path in sorted(WORK_DIR.glob("*.json")):
        record = _load_json(path) or {}
        if (
            isinstance(record, dict)
            and record.get("status") == "active"
            and not (EVIDENCE_DIR / path.stem / "result.json").is_file()
        ):
            open_ids.append(path.stem)
    return open_ids


def cmd_status(args) -> int:
    active = _load_active()
    if active is None or not active.get("enabled"):
        note = "DEV ACCESS not enabled"
        if active and active.get("disable_reason"):
            note = f"DEV ACCESS disabled: {active['disable_reason']}"
        print(json.dumps({
            "status": "INACTIVE",
            "note": note,
            "schema": (active or {}).get("schema"),
            "schema_version": (active or {}).get("schema_version"),
            "open_work_records": _open_work_records(),
        }, indent=2))
        return 0
    active = _expire_if_due(active)
    if not active.get("enabled"):
        print(json.dumps({
            "status": "INACTIVE",
            "note": "DEV ACCESS self-expired: "
                    f"{active.get('disable_reason')}",
            "disable_reason": active.get("disable_reason"),
        }, indent=2))
        return 0
    state_info = _read_canonical_state()
    phase_now, task_now = _state_phase_task(state_info)
    print(json.dumps({
        "status": "ACTIVE",
        "schema": active.get("schema"),
        "schema_version": active.get("schema_version"),
        "requires_admit": active.get("schema") != ACTIVE_SCHEMA,
        "authority": active.get("authority"),
        "reason": active.get("reason"),
        "observed_phase": active.get("observed_saipen_phase"),
        "observed_task": active.get("observed_saipen_task"),
        "canonical_phase_now": phase_now,
        "canonical_task_now": task_now,
        "canonical_state_fence_error": state_info.get("__fence_error__"),
        "expires_at": active.get("expires_at"),
        "reconciliation_required": active.get("reconciliation_required"),
        "publication_allowed": active.get("publication_allowed"),
        "created_at": active.get("created_at"),
        "open_work_records": _open_work_records(),
        "work_records": sorted(
            record_path.stem for record_path in WORK_DIR.glob("*.json")
        ),
    }, indent=2))
    return 0


def cmd_begin(args) -> int:
    active = _expire_if_due(_load_active())
    if active is None:
        return _refuse("DEV_ACCESS_INACTIVE", note=".devaccess/ACTIVE.json missing")
    if not active.get("enabled"):
        return _refuse("DEV_ACCESS_DISABLED",
                       note=f"reason: {active.get('disable_reason')}")
    gate = _schema_gate(active)
    if gate is not None:
        return gate
    own = WORK_DIR / f"{args.dev_id}.json"
    if own.is_file():
        return _refuse("TASK_EXISTS", dev_id=args.dev_id)
    owns = _parse_paths(args.owns)
    if not owns:
        return _refuse("NO_OWN_LIST")
    expects = _parse_paths(args.expects or "")
    conflict = _active_conflict(owns, exclude=args.dev_id)
    if conflict:
        return _refuse("DEV_ACCESS_WRITE_CONFLICT",
                       conflict_with=conflict[0], path=conflict[1])
    state = _read_canonical_state()
    try:
        watched = _snapshot(owns + expects)
        forbidden = _snapshot(FORBIDDEN_PATHS)
    except SnapshotLimit as exc:
        return _refuse("DEV_ACCESS_SNAPSHOT_LIMIT", detail=str(exc))
    record = {
        "schema_version": ACTIVE_SCHEMA_VERSION,
        "dev_id": args.dev_id,
        "operator_request": args.request,
        "starting_canonical_state": {
            "phase": state.get("phase"),
            "task": state.get("task"),
        },
        "writable_paths": owns,
        "expects": expects,
        "forbidden_paths": FORBIDDEN_PATHS,
        "starting_source_hashes": watched,
        "started_at": now_utc(),
        "status": "active",
        "changed_files": [],
        "created_files": [],
        "deleted_files": [],
        "tests": {},
        "evidence_path": f".devaccess/evidence/{args.dev_id}",
    }
    evidence_dir = EVIDENCE_DIR / args.dev_id
    _save_json(own, record)
    _save_json(evidence_dir / "baseline.json", {
        "schema": BASELINE_SCHEMA,
        "schema_version": ACTIVE_SCHEMA_VERSION,
        "dev_id": args.dev_id,
        "operator_request": args.request,
        "starting_canonical_state": record["starting_canonical_state"],
        "writable_paths": owns,
        "expects": expects,
        "forbidden_paths": FORBIDDEN_PATHS,
        "starting_hashes": watched,
        "forbidden_snapshot": forbidden,
        "created_at": record["started_at"],
        "canonical_state_mutation_allowed": bool(
            active.get("canonical_state_mutation_allowed", False)),
        "publication_allowed": bool(active.get("publication_allowed", False)),
    })
    print(json.dumps({
        "status": "BEGUN",
        "dev_id": args.dev_id,
        "owns": owns,
        "watched_files": len(watched),
        "work_record": relative_to_root(own),
        "baseline": relative_to_root(evidence_dir / "baseline.json"),
    }, indent=2))
    return 0


def _dev_record(dev_id: str) -> dict | None:
    data = _load_json(WORK_DIR / f"{dev_id}.json")
    if data is None or "__corrupt__" in data:
        return None
    return data


def _baseline(dev_id: str) -> dict | None:
    data = _load_json(EVIDENCE_DIR / dev_id / "baseline.json")
    if data is None or "__corrupt__" in data:
        return None
    return data


def _guardrail(dev: dict, baseline: dict) -> tuple[list[str], dict]:
    """The v2 guardrail evaluation shared by `check` and `finish-check`.

    Returns (failures, current watched snapshot). Neither verb may drift from
    the other: a finish gate that checks something else than the check verb is
    not a gate.
    """
    failures: list[str] = []
    conflict = _active_conflict(dev.get("writable_paths", []), exclude=dev.get("dev_id"))
    if conflict:
        failures.append(
            f"write ownership overlaps active task {conflict[0]} at {conflict[1]}"
        )
    watched_now = _snapshot(dev.get("writable_paths", [])
                            + dev.get("expects", []))
    forbidden_now = _snapshot(FORBIDDEN_PATHS)
    canonical_diff = _snapshot_diff(baseline.get("forbidden_snapshot", {}),
                                    forbidden_now)
    if (any(canonical_diff.values())
            and not baseline.get("canonical_state_mutation_allowed", False)):
        failures.append("forbidden canonical surface changed: "
                        + json.dumps(canonical_diff, sort_keys=True))
    expects = set(dev.get("expects", []))
    drift = []
    for rel, digest in baseline.get("starting_hashes", {}).items():
        if watched_now.get(rel) == digest:
            continue
        if expects and rel not in expects:
            drift.append(rel)
    if drift:
        failures.append("baseline-owned files changed externally (not declared "
                        "in --expects): " + ", ".join(sorted(drift)))
    return failures, watched_now


def _watched_changes(diff: dict) -> dict:
    return (
        {rel: "changed" for rel in diff["changed"]}
        | {rel: "created" for rel in diff["added"]}
        | {rel: "deleted" for rel in diff["removed"]}
    )


def _open_gates(active: dict | None, dev_id: str) -> tuple[dict, dict] | int:
    """Shared prologue: enabled overlay, v2 schema, active record, baseline."""
    active = _expire_if_due(active)
    if active is None:
        return _refuse("ACTIVE_JSON_MISSING")
    if not active.get("enabled"):
        return _refuse("DEV_ACCESS_DISABLED",
                       note=f"reason: {active.get('disable_reason')}")
    gate = _schema_gate(active)
    if gate is not None:
        return gate
    dev = _dev_record(dev_id)
    if dev is None:
        return _refuse("TASK_NOT_FOUND", dev_id=dev_id)
    if dev.get("status") != "active":
        return _refuse("TASK_NOT_ACTIVE", dev_id=dev_id)
    baseline = _baseline(dev_id)
    if baseline is None:
        return _refuse("DEV_ACCESS_BASELINE_CORRUPT_OR_MISSING", dev_id=dev_id)
    return dev, baseline


def cmd_check(args) -> int:
    opened = _open_gates(_load_active(), args.dev_id)
    if isinstance(opened, int):
        return opened
    dev, baseline = opened
    try:
        failures, watched_now = _guardrail(dev, baseline)
    except SnapshotLimit as exc:
        return _refuse("DEV_ACCESS_SNAPSHOT_LIMIT", detail=str(exc))
    watched_diff = _snapshot_diff(baseline.get("starting_hashes", {}), watched_now)
    # v2 delta tracking: the measured delta is PERSISTED on the record, so drift
    # is evidence between checkpoints instead of stdout that dies with the run.
    delta = dev.get("delta") or {"changed": [], "added": [], "removed": []}
    for kind in ("changed", "added", "removed"):
        delta[kind] = sorted(set(delta.get(kind, [])) | set(watched_diff[kind]))
    dev["delta"] = delta
    dev["last_check"] = {
        "measured_at": now_utc(),
        "status": "FAIL" if failures else "OK",
        "failures": failures,
        "watched_changes": _watched_changes(watched_diff),
    }
    _save_json(WORK_DIR / f"{args.dev_id}.json", dev)
    if failures:
        print(json.dumps({"status": "FAIL", "dev_id": args.dev_id,
                          "failures": failures}, indent=2))
        return 1
    print(json.dumps({
        "status": "OK",
        "dev_id": args.dev_id,
        "checks": ["active enabled", "v2 schema", "no conflicting active task",
                   "canonical surface unchanged", "no external drift"],
        "watched_changes": _watched_changes(watched_diff),
        "delta": delta,
    }, indent=2))
    return 0


def _write_reconcile(dev_id: str, result: dict, record: dict) -> Path:
    path = EVIDENCE_DIR / dev_id / "RECONCILE.md"
    if path.is_file():
        return path
    lines = [
        "# DEV ACCESS Reconciliation Handoff",
        "",
        f"DEV ID: {dev_id}",
        f"USER REQUEST: {record.get('operator_request')}",
        "STARTING CANONICAL STATE: "
        + json.dumps(record.get("starting_canonical_state", {}), sort_keys=True),
        "FILES CHANGED: " + (", ".join(result["changed_files"]) or "none"),
        "FILES CREATED: " + (", ".join(result["created_files"]) or "none"),
        "FILES DELETED: " + (", ".join(result["deleted_files"]) or "none"),
        "FOCUSED TESTS: " + str(result.get("focused_tests")),
        "REGRESSION TESTS: " + str(result.get("regression_tests")),
        "LINT: " + str(result.get("lint")),
        "KNOWN LIMITATIONS: " + (", ".join(result.get("known_limitations", []))
                                 or "none recorded"),
        "PUBLICATION NONE: yes",
        "CANONICAL SAIPEN FILES MODIFIED: NO",
        "RECONCILIATION_REQUIRED: YES",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def cmd_finish_check(args) -> int:
    """The explicit v2 finish gate: measure NOW and record the verdict.

    v1 let `finish` be the first verb that ever measured the delta, so a task
    could be closed with nothing changed and nobody could tell whether it had
    been checked at all. The gate refuses an empty delta and any guardrail
    failure, records the verdict on the work record, and `finish` refuses while
    the newest recorded verdict is FAIL.
    """
    opened = _open_gates(_load_active(), args.dev_id)
    if isinstance(opened, int):
        return opened
    dev, baseline = opened
    try:
        failures, _watched_now = _guardrail(dev, baseline)
    except SnapshotLimit as exc:
        return _refuse("DEV_ACCESS_SNAPSHOT_LIMIT", detail=str(exc))
    recorded = dev.get("delta") or {}
    measured = sorted(
        set(recorded.get("changed", []))
        | set(recorded.get("added", []))
        | set(recorded.get("removed", []))
    )
    if not measured:
        failures.append(
            "no measured delta: closing a task with zero changed files is not "
            "evidence of anything"
        )
    dev["finish_check"] = {
        "checked_at": now_utc(),
        "status": "FAIL" if failures else "OK",
        "failures": failures,
    }
    _save_json(WORK_DIR / f"{args.dev_id}.json", dev)
    if failures:
        print(json.dumps({"status": "FAIL", "dev_id": args.dev_id,
                          "eligible": False, "failures": failures}, indent=2))
        return 1
    print(json.dumps({
        "status": "OK",
        "dev_id": args.dev_id,
        "eligible": True,
        "delta_files": measured,
        "checks": ["active enabled", "v2 schema", "no conflicting active task",
                   "canonical surface unchanged", "no external drift",
                   "non-empty measured delta"],
    }, indent=2))
    return 0


def cmd_finish(args) -> int:
    opened = _open_gates(_load_active(), args.dev_id)
    if isinstance(opened, int):
        return opened
    dev, baseline = opened
    recorded = dev.get("finish_check") or {}
    if recorded.get("status") == "FAIL":
        return _refuse(
            "DEV_ACCESS_FINISH_CHECK_FAILED",
            dev_id=args.dev_id,
            failures=recorded.get("failures", []),
            checked_at=recorded.get("checked_at"),
            next_command=(f"python tools/dev_access.py finish-check "
                          f"{args.dev_id}"),
            note="the newest recorded finish-check FAILED; resolve it and re-run "
                 "finish-check before closing the task",
        )
    try:
        failures, watched_now = _guardrail(dev, baseline)
    except SnapshotLimit as exc:
        return _refuse("DEV_ACCESS_SNAPSHOT_LIMIT", detail=str(exc))
    if any(f.startswith("forbidden canonical surface changed")
           for f in failures):
        return _refuse("DEV_ACCESS_CANONICAL_DRIFT",
                       failures=failures,
                       note="finish refused; canonical surface changed during task")
    if failures:
        return _refuse("DEV_ACCESS_FINISH_DRIFT",
                       dev_id=args.dev_id,
                       failures=failures)
    before = baseline.get("starting_hashes", {})
    diff = _snapshot_diff(before, watched_now)
    result = {
        "schema": RESULT_SCHEMA,
        "schema_version": ACTIVE_SCHEMA_VERSION,
        "dev_id": args.dev_id,
        "status": "DEV_COMPLETE",
        "finished_at": now_utc(),
        "base_hashes": {rel: before[rel]
                        for rel in diff["changed"] + diff["removed"]},
        "final_hashes": {rel: watched_now[rel]
                         for rel in diff["changed"] + diff["added"]},
        "changed_files": diff["changed"],
        "created_files": diff["added"],
        "deleted_files": diff["removed"],
        "focused_tests": args.focused or "not_recorded",
        "regression_tests": args.regression or "not_recorded",
        "lint": args.lint or "not_recorded",
        "known_limitations": args.limitations or [],
        "no_publication_assertion": True,
        "no_canonical_state_mutation_assertion": not any(failures),
        "canonical_surface_unchanged": not any(failures),
        "reconciliation_required": True,
    }
    evidence_dir = EVIDENCE_DIR / args.dev_id
    _save_json(evidence_dir / "result.json", result)
    reconcile = _write_reconcile(args.dev_id, result, dev)
    dev["status"] = "done"
    dev["finished_at"] = result["finished_at"]
    dev["changed_files"] = diff["changed"]
    dev["created_files"] = diff["added"]
    dev["deleted_files"] = diff["removed"]
    dev["tests"] = {
        "focused": result["focused_tests"],
        "regression": result["regression_tests"],
        "lint": result["lint"],
    }
    _save_json(WORK_DIR / f"{args.dev_id}.json", dev)
    print(json.dumps({
        "status": "DEV_COMPLETE",
        "dev_id": args.dev_id,
        "result": relative_to_root(evidence_dir / "result.json"),
        "reconcile": relative_to_root(reconcile),
        "changed_files": len(result["changed_files"]),
        "created_files": len(result["created_files"]),
        "deleted_files": len(result["deleted_files"]),
    }, indent=2))
    return 0


def cmd_admit(args) -> int:
    """The v1 -> v2 bootstrap migration. ONE cut, idempotent, never a rewrite.

    1. Upgrade a `SAIMAIL_DEV_ACCESS_1` ACTIVE.json to the v2 schema and derive
       `expires_at` from the recorded activation time plus `ttl_seconds` -- v1
       carried both fields and honoured neither.
    2. Reconcile the work records v1 orphaned: a record left `active` with no
       result can never advance under v1, because every guardrail verb refuses
       while ACTIVE is disabled. It is marked `reconciled` with a reason, and
       its ORIGINAL bytes plus both hashes are preserved inside the migration
       evidence before anything is rewritten.

    Nothing outside `.devaccess/**` is read or written, and `--dry-run` writes
    nothing at all.
    """
    path = Path(args.active).resolve() if args.active else ACTIVE_PATH
    if not path.is_file():
        return _refuse("ACTIVE_JSON_MISSING", path=str(path))
    raw = path.read_bytes()
    try:
        active = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _refuse("DEV_ACCESS_ACTIVE_CORRUPT", path=str(path),
                       detail=str(exc))
    if not isinstance(active, dict):
        return _refuse("DEV_ACCESS_ACTIVE_CORRUPT", path=str(path),
                       detail="ACTIVE.json is not a JSON object")
    schema = active.get("schema")
    if schema == ACTIVE_SCHEMA:
        legacy = False
    elif schema in LEGACY_ACTIVE_SCHEMAS:
        legacy = True
    else:
        return _refuse("DEV_ACCESS_SCHEMA_UNSUPPORTED", schema=schema,
                       path=str(path))
    open_ids = _open_work_records()
    if not legacy and not open_ids:
        print(json.dumps({
            "status": "ALREADY_UPGRADED",
            "schema": schema,
            "schema_version": active.get("schema_version"),
            "changed_files": [],
        }, indent=2))
        return 0
    before_active_sha = hashlib.sha256(raw).hexdigest()
    migrated = dict(active)
    if legacy:
        migrated["schema"] = ACTIVE_SCHEMA
        migrated["schema_version"] = ACTIVE_SCHEMA_VERSION
        migrated["migrated_from"] = schema
        migrated["migrated_at"] = now_utc()
        if not migrated.get("ttl_seconds"):
            migrated["ttl_seconds"] = DEFAULT_TTL_SECONDS
        if not migrated.get("expires_at"):
            anchor = _parse_utc(migrated.get("activated_at")
                                or migrated.get("created_at"))
            if anchor is not None:
                migrated["expires_at"] = (
                    anchor + timedelta(seconds=int(migrated["ttl_seconds"]))
                ).strftime("%Y-%m-%dT%H:%M:%SZ")
    reason = ("overlay_disabled_before_completion"
              if not migrated.get("enabled")
              else "bootstrapped_to_v2")
    planned_records = []
    changed_files = []
    if legacy:
        changed_files.append(relative_to_root(path))
    for dev_id in open_ids:
        record_path = WORK_DIR / f"{dev_id}.json"
        original = record_path.read_bytes()
        record = _load_json(record_path)
        if not isinstance(record, dict):
            return _refuse("DEV_ACCESS_WORK_RECORD_CORRUPT", dev_id=dev_id,
                           path=str(record_path))
        reconciled = dict(record)
        reconciled["schema_version"] = ACTIVE_SCHEMA_VERSION
        reconciled["status"] = RECONCILED_STATUS
        reconciled["reconciled_at"] = now_utc()
        reconciled["reconciled_reason"] = reason
        reconciled_bytes = (json.dumps(reconciled, indent=2) + "\n").encode("utf-8")
        migration = {
            "schema": MIGRATION_SCHEMA,
            "schema_version": ACTIVE_SCHEMA_VERSION,
            "dev_id": dev_id,
            "migration": "v1_to_v2_bootstrap",
            "migrated_at": reconciled["reconciled_at"],
            "reason": reason,
            "active_schema_before": schema,
            "active_schema_after": ACTIVE_SCHEMA,
            "original_record_sha256": hashlib.sha256(original).hexdigest(),
            "reconciled_record_sha256": hashlib.sha256(reconciled_bytes).hexdigest(),
            "original_record": json.loads(original.decode("utf-8")),
        }
        planned_records.append((record_path, reconciled, migration))
        changed_files.append(relative_to_root(record_path))
        changed_files.append(relative_to_root(
            EVIDENCE_DIR / dev_id / "MIGRATION.json"))
    if args.dry_run:
        print(json.dumps({
            "status": "PLAN",
            "dry_run": True,
            "migrated_from": schema if legacy else None,
            "reconciled_records": open_ids,
            "active_expires_at": migrated.get("expires_at"),
            "changed_files": sorted(changed_files),
        }, indent=2))
        return 0
    if legacy:
        _save_json(path, migrated)
    for record_path, reconciled, migration in planned_records:
        _save_json(record_path, reconciled)
        _save_json(EVIDENCE_DIR / reconciled["dev_id"] / "MIGRATION.json",
                   migration)
    print(json.dumps({
        "status": "ADMITTED",
        "migrated_from": schema if legacy else None,
        "active_schema": migrated.get("schema"),
        "active_expires_at": migrated.get("expires_at"),
        "active_before_sha256": before_active_sha,
        "reconciled_records": open_ids,
        "changed_files": sorted(changed_files),
    }, indent=2))
    return 0


def cmd_disable(args) -> int:
    active = _load_active()
    if active is None:
        return _refuse("ACTIVE_JSON_MISSING")
    active["enabled"] = False
    active["disabled_at"] = now_utc()
    active["disable_reason"] = args.reason
    _save_json(ACTIVE_PATH, active)
    print(json.dumps({"status": "DISABLED", "reason": args.reason}, indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="DEV ACCESS guardrail for SAIMAIL product work")
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="show current DEV ACCESS state")
    p_status.set_defaults(func=cmd_status)

    p_admit = sub.add_parser(
        "admit", help="v1 -> v2 bootstrap migration of the overlay")
    p_admit.add_argument("--active", default="",
                         help="alternate ACTIVE.json path")
    p_admit.add_argument("--dry-run", action="store_true",
                         help="report the migration plan, write nothing")
    p_admit.set_defaults(func=cmd_admit)

    p_begin = sub.add_parser("begin", help="start a DEV task")
    p_begin.add_argument("dev_id", help="DEV-YYYYMMDD-HHMM-<topic>")
    p_begin.add_argument("--request", required=True,
                         help="operator request one-liner")
    p_begin.add_argument("--owns", required=True,
                         help="comma/space separated writable path globs")
    p_begin.add_argument("--expects", default="",
                         help="optional exact files this task will edit")
    p_begin.set_defaults(func=cmd_begin)

    p_check = sub.add_parser("check", help="run DEV ACCESS guardrail checks")
    p_check.add_argument("dev_id")
    p_check.set_defaults(func=cmd_check)

    p_finish_check = sub.add_parser(
        "finish-check", help="run the explicit finish gate and record it")
    p_finish_check.add_argument("dev_id")
    p_finish_check.set_defaults(func=cmd_finish_check)

    p_finish = sub.add_parser("finish", help="mark a DEV task complete")
    p_finish.add_argument("dev_id")
    p_finish.add_argument("--focused", default="")
    p_finish.add_argument("--regression", default="")
    p_finish.add_argument("--lint", default="")
    p_finish.add_argument("--limitations", action="append", default=[])
    p_finish.set_defaults(func=cmd_finish)

    p_disable = sub.add_parser("disable", help="turn off DEV ACCESS")
    p_disable.add_argument("--reason", required=True)
    p_disable.set_defaults(func=cmd_disable)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as exc:
        print(json.dumps({"status": "REFUSED", "code": "NOT_FOUND",
                          "path": str(exc)}, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())