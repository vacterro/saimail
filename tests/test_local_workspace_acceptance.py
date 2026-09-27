"""V2-01 one-command acceptance harness: isolated root, multi-invocation proof.

Runs the installed entrypoint's own ``acceptance`` subcommand and asserts the
bounded ``LOCAL_WORKSPACE_RESULT_1`` result: two persistent workspaces, a real
send/list/open across separate processes, duplicate suppression, identity
persistence, privacy and zero network/model calls.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCEPTANCE_CLAIM = "v2-01 synthetic operator message 7c1d"


def _run(args, cwd=ROOT, env=None):
    return subprocess.run([sys.executable, "-m", "saimail_local", *args],
                          cwd=cwd, capture_output=True, text=True, check=False, env=env)


def test_acceptance_harness_passes_and_is_bounded(tmp_path):
    root = tmp_path / "acceptance"
    completed = _run(["acceptance", "--root", str(root), "--out", str(tmp_path / "out"),
                      "--json"])
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["schema"] == "LOCAL_WORKSPACE_RESULT_1"
    assert result["version"] == 1
    assert result["status"] == "PASS"
    assert result["checks"] and all(entry["ok"] for entry in result["checks"])
    assert result["send"]["status"] == "ACCEPTED"
    assert result["duplicate"]["status"] == "DUPLICATE"
    assert result["duplicate"]["same_received_at"] is True
    assert result["duplicate"]["messages_after"] == 1
    assert result["duplicate"]["unread_after"] == 0
    assert result["restart"]["invocations"] >= 11
    assert result["privacy"] == {"private_key_material_in_outputs": False,
                                 "plaintext_marker_on_disk": False,
                                 "plaintext_marker_in_results": False}
    assert result["zero_network_model"]["network_attempts"] == 0
    assert result["zero_network_model"]["model_calls"] == 0
    assert ACCEPTANCE_CLAIM not in completed.stdout
    written = json.loads((tmp_path / "out" / "local_workspace_result.json").read_text(
        encoding="utf-8"))
    assert written["status"] == "PASS"
    identity = json.loads(
        (root / "workspace-a" / "identity" / "identity.json").read_text(encoding="utf-8"))
    assert identity["sender_private_key"] not in completed.stdout
    assert identity["recipient_private_key"] not in completed.stdout


def test_acceptance_refuses_a_nonempty_root(tmp_path):
    root = tmp_path / "acceptance"
    root.mkdir()
    (root / "leftover.txt").write_text("operator data", encoding="utf-8")
    completed = _run(["acceptance", "--root", str(root), "--json"])
    assert completed.returncode == 1
    result = json.loads(completed.stdout)
    assert result["status"] == "FAIL"
    assert result["checks"][0]["id"] == "isolated_root"
    assert result["checks"][0]["ok"] is False


def test_acceptance_works_from_a_foreign_cwd(tmp_path):
    root = tmp_path / "acceptance"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    completed = _run(["acceptance", "--root", str(root), "--json"], cwd=elsewhere, env=env)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout)
    assert result["status"] == "PASS"
    assert all(step["ok"] for step in result["steps"])


def test_privacy_scanner_recognizes_a_planted_marker(tmp_path):
    """Instrument control: the plaintext scanner can go red on a known-bad input."""
    import saimail_local

    base = tmp_path / "scan"
    base.mkdir()
    scanner = saimail_local._Acceptance(base)
    assert scanner._marker_in_files(ACCEPTANCE_CLAIM) is False
    (base / "planted.txt").write_text(ACCEPTANCE_CLAIM, encoding="utf-8")
    assert scanner._marker_in_files(ACCEPTANCE_CLAIM) is True
