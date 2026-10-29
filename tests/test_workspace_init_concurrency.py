"""Workspace initialization is one create-or-reopen transaction (W2-001)."""

import json
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from sailang import SailangError
from saimail import workspace


def test_concurrent_initializers_cannot_replace_a_reported_identity(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    generating = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    second_finished = threading.Event()
    original = workspace.Ed25519PrivateKey.generate

    def paused_generate():
        if not generating.is_set():
            generating.set()
            assert release.wait(10), "creator was never released"
        return original()

    monkeypatch.setattr(workspace.Ed25519PrivateKey, "generate", paused_generate)

    def initialize(second=False):
        if second:
            second_started.set()
        result = workspace.init_workspace(root, seat="SAIMAIL-A")
        if second:
            second_finished.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(initialize)
        try:
            assert generating.wait(10)
            second = pool.submit(initialize, True)
            assert second_started.wait(10)
            # The old preflight lets B finish while A is generating keys.
            second_finished.wait(0.5)
        finally:
            release.set()
        results = [first.result(timeout=15), second.result(timeout=15)]
    assert sorted(item["status"] for item in results) == [
        workspace.ALREADY_EXISTS, workspace.CREATED]
    loaded = workspace.load_workspace(root)
    assert all(item["identity"]["sender_kid"] == loaded.sender_kid for item in results)
    assert all(item["identity"]["recipient_kid"] == loaded.recipient_kid for item in results)


RACER = """
import json, os, sys, time
from saimail import workspace
from sailang import SailangError
root, seat, ready, go = sys.argv[1:]
open(ready, 'w').close()
deadline = time.monotonic() + 15
while not os.path.exists(go):
    if time.monotonic() > deadline:
        raise SystemExit('barrier timeout')
    time.sleep(0.005)
try:
    print(json.dumps(workspace.init_workspace(root, seat=seat)))
except SailangError as exc:
    print(json.dumps({'error': exc.code}))
"""


@pytest.mark.parametrize("different_seats", [False, True])
def test_process_initializers_converge_or_refuse_the_other_seat(tmp_path, different_seats):
    import time

    root = tmp_path / "workspace"
    go = tmp_path / "GO"
    seats = ["SAIMAIL-A", "SAIMAIL-B" if different_seats else "SAIMAIL-A"]
    procs = []
    try:
        for index, seat in enumerate(seats):
            procs.append(subprocess.Popen(
                [sys.executable, "-c", RACER, str(root), seat,
                 str(tmp_path / f"ready-{index}"), str(go)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        deadline = time.monotonic() + 15
        while not all((tmp_path / f"ready-{i}").exists() for i in range(2)):
            assert time.monotonic() < deadline, "child startup timeout"
            time.sleep(0.005)
        go.touch()
        results = []
        for proc in procs:
            out, err = proc.communicate(timeout=20)
            assert proc.returncode == 0, err
            results.append(json.loads(out))
        loaded = workspace.load_workspace(root)
        winners = [row for row in results if row.get("status") == workspace.CREATED]
        assert len(winners) == 1, results
        assert winners[0]["identity"]["sender_kid"] == loaded.sender_kid
        assert winners[0]["identity"]["recipient_kid"] == loaded.recipient_kid
        other = next(row for row in results if row is not winners[0])
        if different_seats:
            assert other == {"error": workspace.WORKSPACE_CONFLICT}
        else:
            assert other["status"] == workspace.ALREADY_EXISTS
            assert other["identity"] == winners[0]["identity"]
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
            proc.communicate()


def test_init_failure_after_identity_never_regenerates_private_material(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    original = workspace._atomic_write_bytes

    def fail_marker(path, data):
        if path.name == workspace.MARKER_NAME:
            raise OSError("marker write failed")
        return original(path, data)

    with monkeypatch.context() as patch:
        patch.setattr(workspace, "_atomic_write_bytes", fail_marker)
        with pytest.raises(OSError, match="marker write failed"):
            workspace.init_workspace(root, seat="SAIMAIL-A")
    identity_path = root / workspace.IDENTITY_DIR / workspace.IDENTITY_NAME
    before = identity_path.read_bytes()
    with pytest.raises(SailangError) as exc:
        workspace.init_workspace(root, seat="SAIMAIL-A")
    assert exc.value.code == workspace.WORKSPACE_CONFLICT
    assert identity_path.read_bytes() == before
