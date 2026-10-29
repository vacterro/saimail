"""Logical letter dedup spans canonical delivery and registry publication."""

import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from sailang import SailangError
from saimail import future_letter as fl, postoffice, workspace

NOW = "2026-10-29T01:00:00Z"


def _create(ws):
    try:
        return fl.create(ws, title="same letter", body="same body", clock=lambda: NOW)["status"]
    except SailangError as exc:
        return exc.code


def test_two_threads_cannot_deliver_the_same_logical_letter(tmp_path, monkeypatch):
    workspace.init_workspace(tmp_path / "ws", seat="agent-a")
    ws = workspace.load_workspace(tmp_path / "ws")
    delivering = threading.Event()
    release = threading.Event()
    second_finished = threading.Event()
    original = workspace.deliver_payload

    def pause_delivery(*args, **kwargs):
        if not delivering.is_set():
            delivering.set()
            assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(workspace, "deliver_payload", pause_delivery)

    def second():
        result = _create(ws)
        second_finished.set()
        return result

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_create, ws)
        try:
            assert delivering.wait(10)
            other = pool.submit(second)
            second_finished.wait(0.5)
        finally:
            release.set()
        outcomes = [first.result(timeout=15), other.result(timeout=15)]
    assert sorted(outcomes) == sorted([postoffice.ACCEPTED, fl.LETTER_ALREADY_IMPORTED])
    assert len(ws.self_office().read_index()) == 1
    assert fl.list_letters(ws)["count"] == 1


RACER = """
import json, os, sys, time
from saimail import workspace, future_letter as fl
from sailang import SailangError
root, ready, go = sys.argv[1:]
ws = workspace.load_workspace(root)
open(ready, 'w').close()
deadline = time.monotonic() + 15
while not os.path.exists(go):
    if time.monotonic() > deadline:
        raise SystemExit('barrier timeout')
    time.sleep(0.005)
try:
    result = fl.create(ws, title='same letter', body='same body',
                       clock=lambda: '2026-10-29T01:00:00Z')
    print(json.dumps({'outcome': result['status']}))
except SailangError as exc:
    print(json.dumps({'outcome': exc.code}))
"""


def test_separate_processes_publish_one_logical_letter(tmp_path):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="agent-a")
    go = tmp_path / "GO"
    procs = []
    try:
        for index in range(3):
            procs.append(subprocess.Popen(
                [sys.executable, "-c", RACER, str(root), str(tmp_path / f"ready-{index}"),
                 str(go)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        deadline = time.monotonic() + 15
        while not all((tmp_path / f"ready-{i}").exists() for i in range(3)):
            assert time.monotonic() < deadline
            time.sleep(0.005)
        go.touch()
        outcomes = []
        for proc in procs:
            out, err = proc.communicate(timeout=20)
            assert proc.returncode == 0, err
            outcomes.append(json.loads(out)["outcome"])
        assert outcomes.count(postoffice.ACCEPTED) == 1, outcomes
        assert outcomes.count(fl.LETTER_ALREADY_IMPORTED) == 2, outcomes
        ws = workspace.load_workspace(root)
        assert len(ws.self_office().read_index()) == 1
        assert fl.list_letters(ws)["count"] == 1
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
            proc.communicate()


def test_retry_after_delivery_without_projection_never_seals_a_second_copy(tmp_path, monkeypatch):
    root = tmp_path / "ws"
    workspace.init_workspace(root, seat="agent-a")
    ws = workspace.load_workspace(root)

    def power_cut(*args, **kwargs):
        raise OSError("projection write failed")

    with monkeypatch.context() as patch:
        patch.setattr(fl, "_append_registry", power_cut)
        with pytest.raises(OSError, match="projection write failed"):
            _create(ws)
    assert len(ws.self_office().read_index()) == 1
    assert _create(workspace.load_workspace(root)) == fl.LETTER_ALREADY_IMPORTED
    assert len(ws.self_office().read_index()) == 1
    assert fl.list_letters(ws)["count"] == 1
