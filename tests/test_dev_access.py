"""T-100/T-102 acceptance: DEV ACCESS overlay guardrail (v2 contract).

The helper must manage only `.devaccess/**`, and `check`/`finish` must fail
closed on canonical-surface drift, external drift of baseline-owned files and
overlapping write ownership. T-102 adds the v1 -> v2 bootstrap migration:
`admit` is the only migration path, a v1 overlay is refused by name, the STATE
reader is fence-bounded, the overlay self-expires on its TTL as well as on a
free canonical lane, `check` persists the measured delta, and `finish-check` is
an explicit gate that `finish` honours. These tests drive the real module
against a disposable project root.
"""

import hashlib
import importlib.util
import json
import pathlib

TOOL = pathlib.Path(__file__).resolve().parent.parent / "tools" / "dev_access.py"
ACTIVE = {
    "schema": "SAIMAIL_DEV_ACCESS_2",
    "schema_version": 2,
    "enabled": True,
    "authority": "explicit_operator",
    "reason": "canonical SAIPEN lifecycle occupied",
    "observed_saipen_phase": "VERIFY",
    "observed_saipen_task": "T-99",
    "created_at": "2026-09-21T00:00:00Z",
    "activated_at": "2026-09-21T00:00:00Z",
    "ttl_seconds": 21600,
    "expires_at": "2099-01-01T00:00:00Z",
    "publication_allowed": False,
    "canonical_state_mutation_allowed": False,
    "reconciliation_required": True,
}
LEGACY_ACTIVE = {
    "schema": "SAIMAIL_DEV_ACCESS_1",
    "enabled": True,
    "authority": "explicit_operator",
    "reason": "canonical SAIPEN lifecycle occupied",
    "observed_saipen_phase": "VERIFY",
    "observed_saipen_task": "T-99",
    "created_at": "2026-09-21T00:00:00Z",
    "activated_at": "2026-09-21T00:00:00Z",
    "ttl_seconds": 21600,
    "publication_allowed": False,
    "canonical_state_mutation_allowed": False,
    "reconciliation_required": True,
}


def load_tool(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("dev_access_under_test", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "ACTIVE_PATH",
                        tmp_path / ".devaccess" / "ACTIVE.json")
    monkeypatch.setattr(module, "WORK_DIR", tmp_path / ".devaccess" / "work")
    monkeypatch.setattr(module, "EVIDENCE_DIR",
                        tmp_path / ".devaccess" / "evidence")
    monkeypatch.setattr(module, "STATE_PATH", tmp_path / ".saipen" / "STATE.md")
    return module


def make_root(tmp_path, phase="SCOUT", task="T-100", active=None):
    (tmp_path / ".saipen").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".saipen" / "STATE.md").write_text(
        f"---\nphase: {phase}\ntask: {task}\n---\n", encoding="utf-8")
    (tmp_path / "saimail").mkdir(exist_ok=True)
    (tmp_path / "saimail" / "x.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_x.py").write_text(
        "def test_x():\n    assert True\n", encoding="utf-8")
    (tmp_path / ".devaccess").mkdir(exist_ok=True)
    (tmp_path / ".devaccess" / "ACTIVE.json").write_text(
        json.dumps(ACTIVE if active is None else active, indent=2) + "\n",
        encoding="utf-8")


def write_dev_record(tmp_path, dev_id, **fields):
    """A minimal work record, as `begin` would have left it."""
    record = {
        "dev_id": dev_id,
        "operator_request": "harden DEV ACCESS v1 to v2",
        "writable_paths": ["saimail/**"],
        "expects": [],
        "started_at": "2026-09-21T01:52:21Z",
        "status": "active",
        "changed_files": [],
        "created_files": [],
        "deleted_files": [],
        "tests": {},
        "evidence_path": f".devaccess/evidence/{dev_id}",
    }
    record.update(fields)
    work_dir = tmp_path / ".devaccess" / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / f"{dev_id}.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return path


def payload(capsys):
    return json.loads(capsys.readouterr().out)


def begin(tool, dev_id="DEV-20260921-0100-demo", owns="saimail/**,tests/**",
          expects=""):
    return tool.main(["begin", dev_id, "--request", "demo request",
                      "--owns", owns, "--expects", expects])


def snapshot_saipen(root):
    out = {}
    for path in (root / ".saipen").rglob("*"):
        if path.is_file():
            out[path.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def test_status_inactive_without_active_json(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    assert tool.main(["status"]) == 0
    assert payload(capsys)["status"] == "INACTIVE"


def test_begin_captures_record_and_baseline(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    assert begin(tool, expects="saimail/x.py") == 0
    assert payload(capsys)["status"] == "BEGUN"
    record = json.loads(
        (tmp_path / ".devaccess" / "work" / "DEV-20260921-0100-demo.json")
        .read_text(encoding="utf-8"))
    baseline = json.loads(
        (tmp_path / ".devaccess" / "evidence" / "DEV-20260921-0100-demo"
         / "baseline.json").read_text(encoding="utf-8"))
    assert record["status"] == "active"
    assert record["starting_canonical_state"] == {"phase": "SCOUT", "task": "T-100"}
    assert "saimail/x.py" in baseline["starting_hashes"]
    assert ".saipen/STATE.md" in baseline["forbidden_snapshot"]


def test_begin_refuses_overlapping_active_task(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    assert begin(tool, dev_id="DEV-20260921-0100-first", owns="saimail/**") == 0
    capsys.readouterr()
    assert begin(tool, dev_id="DEV-20260921-0101-second",
                 owns="saimail/gui.py") == 1
    assert payload(capsys)["code"] == "DEV_ACCESS_WRITE_CONFLICT"


def test_begin_refuses_without_own_list(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    assert tool.main(["begin", "DEV-20260921-0100-demo",
                      "--request", "r", "--owns", ""]) == 1
    assert payload(capsys)["code"] == "NO_OWN_LIST"


def test_check_ok_and_reports_expected_change(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    begin(tool, expects="saimail/x.py")
    capsys.readouterr()
    (tmp_path / "saimail" / "x.py").write_text("value = 2\n", encoding="utf-8")
    assert tool.main(["check", "DEV-20260921-0100-demo"]) == 0
    out = payload(capsys)
    assert out["status"] == "OK"
    assert out["watched_changes"]["saimail/x.py"] == "changed"


def test_check_fails_on_canonical_drift(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    begin(tool)
    capsys.readouterr()
    (tmp_path / ".saipen" / "STATE.md").write_text(
        "---\nphase: BUILD\ntask: T-100\n---\n", encoding="utf-8")
    assert tool.main(["check", "DEV-20260921-0100-demo"]) == 1
    assert "forbidden canonical surface changed" in payload(capsys)["failures"][0]


def test_check_fails_on_external_drift(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    begin(tool, expects="saimail/x.py")
    capsys.readouterr()
    (tmp_path / "tests" / "test_x.py").write_text(
        "def test_x():\n    assert 1\n", encoding="utf-8")
    assert tool.main(["check", "DEV-20260921-0100-demo"]) == 1
    assert "changed externally" in payload(capsys)["failures"][0]


def test_check_refuses_corrupt_baseline(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    begin(tool)
    capsys.readouterr()
    baseline = (tmp_path / ".devaccess" / "evidence" / "DEV-20260921-0100-demo"
                / "baseline.json")
    baseline.write_text('{"dev_id": "x",}\n', encoding="utf-8")
    assert tool.main(["check", "DEV-20260921-0100-demo"]) == 1
    assert payload(capsys)["code"] == "DEV_ACCESS_BASELINE_CORRUPT_OR_MISSING"


def test_finish_writes_result_with_derived_files(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    begin(tool, expects="saimail/x.py")
    capsys.readouterr()
    (tmp_path / "saimail" / "x.py").write_text("value = 2\n", encoding="utf-8")
    (tmp_path / "saimail" / "y.py").write_text("new = True\n", encoding="utf-8")
    assert tool.main(["finish", "DEV-20260921-0100-demo",
                      "--focused", "pytest -> PASS",
                      "--lint", "ruff -> clean",
                      "--limitations", "bounded"]) == 0
    out = payload(capsys)
    assert out["status"] == "DEV_COMPLETE"
    result = json.loads(
        (tmp_path / ".devaccess" / "evidence" / "DEV-20260921-0100-demo"
         / "result.json").read_text(encoding="utf-8"))
    assert result["changed_files"] == ["saimail/x.py"]
    assert result["created_files"] == ["saimail/y.py"]
    assert result["focused_tests"] == "pytest -> PASS"
    assert result["no_canonical_state_mutation_assertion"] is True
    assert "base_hashes" in result and "final_hashes" in result
    reconcile = tmp_path / ".devaccess" / "evidence" / "DEV-20260921-0100-demo" / "RECONCILE.md"
    assert "RECONCILIATION_REQUIRED: YES" in reconcile.read_text(encoding="utf-8")


def test_finish_refuses_on_canonical_drift(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    begin(tool)
    capsys.readouterr()
    (tmp_path / ".saipen" / "STATE.md").write_text(
        "---\nphase: VERIFY\ntask: T-100\n---\n", encoding="utf-8")
    assert tool.main(["finish", "DEV-20260921-0100-demo"]) == 1
    assert payload(capsys)["code"] == "DEV_ACCESS_CANONICAL_DRIFT"


def test_finish_refuses_inactive_task(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    begin(tool)
    capsys.readouterr()
    assert tool.main(["finish", "DEV-20260921-0100-demo"]) == 0
    capsys.readouterr()
    assert tool.main(["finish", "DEV-20260921-0100-demo"]) == 1
    assert payload(capsys)["code"] == "TASK_NOT_ACTIVE"


def test_self_expiry_disables_when_canonical_lane_available(
        tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path, phase="DONE", task="none")
    assert tool.main(["status"]) == 0
    assert payload(capsys)["status"] == "INACTIVE"
    active = json.loads(
        (tmp_path / ".devaccess" / "ACTIVE.json").read_text(encoding="utf-8"))
    assert active["enabled"] is False
    assert active["disable_reason"] == "canonical_lane_available"
    assert tool.main(["begin", "DEV-20260921-0100-demo",
                      "--request", "r", "--owns", "saimail/**"]) == 1
    assert payload(capsys)["code"] == "DEV_ACCESS_DISABLED"


def test_helper_never_writes_saipen(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    before = snapshot_saipen(tmp_path)
    begin(tool)
    capsys.readouterr()
    (tmp_path / "saimail" / "x.py").write_text("value = 3\n", encoding="utf-8")
    tool.main(["status"])
    tool.main(["check", "DEV-20260921-0100-demo"])
    tool.main(["finish", "DEV-20260921-0100-demo"])
    tool.main(["disable", "--reason", "canonical_lane_available"])
    capsys.readouterr()
    assert snapshot_saipen(tmp_path) == before


def test_disable_then_begin_refused(tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    assert tool.main(["disable", "--reason", "operator_stop"]) == 0
    capsys.readouterr()
    assert begin(tool) == 1
    assert payload(capsys)["code"] == "DEV_ACCESS_DISABLED"


def test_begin_refuses_legacy_v1_overlay_by_name(tmp_path, monkeypatch, capsys):
    """T-102: a schema bump refuses v1 BY NAME and names the migration."""
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path, active=LEGACY_ACTIVE)
    assert begin(tool) == 1
    out = payload(capsys)
    assert out["code"] == "DEV_ACCESS_V1_REQUIRES_ADMIT"
    assert out["next_command"] == "python tools/dev_access.py admit"


def test_admit_migrates_v1_overlay_and_is_idempotent(
        tmp_path, monkeypatch, capsys):
    """T-102: the bootstrap migration, and a second run changes nothing."""
    tool = load_tool(tmp_path, monkeypatch)
    legacy = dict(LEGACY_ACTIVE, ttl_seconds=315_360_000)
    make_root(tmp_path, active=legacy)
    active_path = tmp_path / ".devaccess" / "ACTIVE.json"
    before = active_path.read_bytes()
    assert tool.main(["admit", "--dry-run"]) == 0
    assert payload(capsys)["status"] == "PLAN"
    assert active_path.read_bytes() == before
    capsys.readouterr()
    assert tool.main(["admit"]) == 0
    out = payload(capsys)
    assert out["status"] == "ADMITTED"
    assert out["migrated_from"] == "SAIMAIL_DEV_ACCESS_1"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    assert active["schema"] == "SAIMAIL_DEV_ACCESS_2"
    assert active["schema_version"] == 2
    assert active["migrated_from"] == "SAIMAIL_DEV_ACCESS_1"
    # expires_at is DERIVED from activated_at + ttl_seconds (v1 carried both
    # fields and honoured neither)
    assert active["expires_at"] == "2036-09-18T00:00:00Z"
    settled = active_path.read_bytes()
    capsys.readouterr()
    assert tool.main(["admit"]) == 0
    assert payload(capsys)["status"] == "ALREADY_UPGRADED"
    assert active_path.read_bytes() == settled
    capsys.readouterr()
    assert begin(tool) == 0


def test_admit_refuses_corrupt_and_unsupported_active(
        tmp_path, monkeypatch, capsys):
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    active_path = tmp_path / ".devaccess" / "ACTIVE.json"
    active_path.write_text('{"schema": "SAIMAIL_DEV_ACCESS_2",}\n',
                           encoding="utf-8")
    assert tool.main(["admit"]) == 1
    assert payload(capsys)["code"] == "DEV_ACCESS_ACTIVE_CORRUPT"
    capsys.readouterr()
    active_path.write_text(json.dumps({"schema": "SAIMAIL_DEV_ACCESS_9"}) + "\n",
                           encoding="utf-8")
    assert tool.main(["admit"]) == 1
    assert payload(capsys)["code"] == "DEV_ACCESS_SCHEMA_UNSUPPORTED"
    capsys.readouterr()
    active_path.unlink()
    assert tool.main(["admit"]) == 1
    assert payload(capsys)["code"] == "ACTIVE_JSON_MISSING"


def test_admit_reconciles_orphaned_active_record(tmp_path, monkeypatch, capsys):
    """T-102: a v1 record left open by a disabled overlay is reconciled with
    its ORIGINAL bytes preserved in hash-bound migration evidence."""
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path, active=dict(
        LEGACY_ACTIVE, enabled=False, disabled_at="2026-09-21T02:54:28Z",
        disable_reason="canonical_lane_available"))
    dev_id = "DEV-20260921-0423-devaccess-hardening"
    record_path = write_dev_record(tmp_path, dev_id)
    before = record_path.read_bytes()
    assert tool.main(["admit"]) == 0
    out = payload(capsys)
    assert out["reconciled_records"] == [dev_id]
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["status"] == "reconciled"
    assert record["reconciled_reason"] == "overlay_disabled_before_completion"
    assert record["schema_version"] == 2
    assert record["operator_request"] == "harden DEV ACCESS v1 to v2"
    migration = json.loads(
        (tmp_path / ".devaccess" / "evidence" / dev_id / "MIGRATION.json")
        .read_text(encoding="utf-8"))
    assert migration["schema"] == "DEV_ACCESS_MIGRATION_1"
    assert migration["migration"] == "v1_to_v2_bootstrap"
    assert migration["original_record_sha256"] == hashlib.sha256(before).hexdigest()
    assert migration["original_record"]["status"] == "active"
    assert migration["active_schema_before"] == "SAIMAIL_DEV_ACCESS_1"


def test_state_reader_is_fence_bounded(tmp_path, monkeypatch, capsys):
    """T-102: prose is never a STATE field. The v1 line scan would read
    `phase: DONE` out of exactly the chat-shaped report that destroyed a real
    project STATE.md; no field may come from outside the fence."""
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    state_path = tmp_path / ".saipen" / "STATE.md"
    state_path.write_text(
        "STATUS\nToo kai\n\nRESULT\n- phase: DONE\n- task: none\n",
        encoding="utf-8")
    assert tool._read_canonical_state() == {
        "__fence_error__": tool.STATE_FENCE_ERROR}
    assert tool._canonical_lane_available() is False
    state_path.write_text(
        "---\nphase: SCOUT\ntask: T-100\n---\n\nphase: DONE\ntask: none\n",
        encoding="utf-8")
    assert tool._read_canonical_state() == {"phase": "SCOUT", "task": "T-100"}
    assert tool._canonical_lane_available() is False
    state_path.write_text("---\nphase: DONE\ntask: none\n---\n", encoding="utf-8")
    assert tool._canonical_lane_available() is True
    state_path.write_text("---\nphase: DONE\ntask: T-100\n", encoding="utf-8")
    assert tool._read_canonical_state() == {
        "__fence_error__": "no closing --- frontmatter fence"}


def test_ttl_self_expiry_disables_overlay(tmp_path, monkeypatch, capsys):
    """T-102: the TTL brake, independent of canonical-lane availability."""
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path, active=dict(ACTIVE, expires_at="2026-09-21T00:30:00Z"))
    assert tool.main(["status"]) == 0
    out = payload(capsys)
    assert out["status"] == "INACTIVE"
    assert out["disable_reason"] == "ttl_expired"
    active = json.loads(
        (tmp_path / ".devaccess" / "ACTIVE.json").read_text(encoding="utf-8"))
    assert active["enabled"] is False
    assert active["disable_reason"] == "ttl_expired"
    capsys.readouterr()
    assert begin(tool) == 1
    assert payload(capsys)["code"] == "DEV_ACCESS_DISABLED"


def test_check_persists_delta_and_finish_check_gates(
        tmp_path, monkeypatch, capsys):
    """T-102: delta tracking survives the run, and `finish` honours the
    recorded finish-check verdict."""
    tool = load_tool(tmp_path, monkeypatch)
    make_root(tmp_path)
    begin(tool, expects="saimail/x.py")
    capsys.readouterr()
    record_path = (tmp_path / ".devaccess" / "work"
                   / "DEV-20260921-0100-demo.json")
    assert tool.main(["finish-check", "DEV-20260921-0100-demo"]) == 1
    out = payload(capsys)
    assert out["eligible"] is False
    assert "no measured delta" in out["failures"][0]
    assert json.loads(record_path.read_text(encoding="utf-8"))[
        "finish_check"]["status"] == "FAIL"
    capsys.readouterr()
    assert tool.main(["finish", "DEV-20260921-0100-demo"]) == 1
    assert payload(capsys)["code"] == "DEV_ACCESS_FINISH_CHECK_FAILED"
    capsys.readouterr()
    (tmp_path / "saimail" / "x.py").write_text("value = 7\n", encoding="utf-8")
    assert tool.main(["check", "DEV-20260921-0100-demo"]) == 0
    capsys.readouterr()
    record = json.loads(record_path.read_text(encoding="utf-8"))
    assert record["delta"]["changed"] == ["saimail/x.py"]
    assert record["last_check"]["status"] == "OK"
    assert tool.main(["finish-check", "DEV-20260921-0100-demo"]) == 0
    assert payload(capsys)["eligible"] is True
    capsys.readouterr()
    assert tool.main(["finish", "DEV-20260921-0100-demo",
                      "--focused", "pytest -> PASS"]) == 0
    result = json.loads(
        (tmp_path / ".devaccess" / "evidence" / "DEV-20260921-0100-demo"
         / "result.json").read_text(encoding="utf-8"))
    assert result["schema"] == "DEV_ACCESS_RESULT_2"
    assert result["schema_version"] == 2
    assert result["changed_files"] == ["saimail/x.py"]