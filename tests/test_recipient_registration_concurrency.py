"""Concurrent public registration controls; no enrolled study participants."""

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import saimail_local
from sailang import SailangError
from saimail import postoffice, workspace

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def trio(tmp_path, monkeypatch):
    monkeypatch.delenv("SAIPEN_AGENT", raising=False)
    roots = [tmp_path / name for name in ("local", "beta", "gamma")]
    for root, name in zip(roots, ("local", "beta", "gamma")):
        workspace.init_workspace(root, seat=name)
    cards = [workspace.identity_card(workspace.load_workspace(root)) for root in roots[1:]]
    return roots, cards


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("view", ["public", "full"])
@pytest.mark.parametrize("case", ["distinct", "conflict", "identical"])
def test_two_writers_preserve_mapping_and_alias_authority(trio, monkeypatch, view, case):
    roots, cards = trio
    load = workspace.load_workspace_headers if view == "public" else workspace.load_workspace
    a = load(roots[0])
    before_foreign = [snapshot(root) for root in roots[1:]]
    entered = threading.Event()
    release = threading.Event()
    second_done = threading.Event()
    write = workspace._write_peers
    outcomes = {}

    def hold_first_write(root, peers):
        if threading.current_thread().name == "first":
            entered.set()
            assert release.wait(10), "test controller failed to release writer"
        write(root, peers)

    monkeypatch.setattr(workspace, "_write_peers", hold_first_write)

    def add(name, alias, card, peer):
        try:
            outcomes[name] = workspace.add_recipient(a, alias, card, peer)["status"]
        except SailangError as exc:
            outcomes[name] = exc.code
        except Exception as exc:  # noqa: BLE001 - retain worker failures for the main assertion
            outcomes[name] = type(exc).__name__
        finally:
            if name == "second":
                second_done.set()

    second_alias = "gamma" if case == "distinct" else "beta"
    second_card, second_root = (cards[0], roots[1]) if case == "identical" else (cards[1], roots[2])
    first = threading.Thread(target=add, name="first", args=("first", "beta", cards[0], roots[1]))
    second = threading.Thread(target=add, name="second", args=("second", second_alias, second_card, second_root))
    first.start()
    assert entered.wait(10)
    second.start()
    # The old implementation finishes writer 2 while writer 1 holds an older
    # snapshot, then writer 1 silently overwrites it. A serialized writer waits.
    second_done.wait(0.5)
    release.set()
    first.join(10)
    second.join(10)
    assert not first.is_alive() and not second.is_alive(), outcomes
    peers = workspace.load_workspace_headers(a.root).peers
    assert outcomes["first"] == workspace.RECIPIENT_ADDED
    if case == "distinct":
        assert outcomes["second"] == workspace.RECIPIENT_ADDED
        assert set(peers) == {"beta", "gamma"}
        assert peers["gamma"]["recipient_kid"] == cards[1]["recipient_kid"]
    elif case == "conflict":
        assert outcomes["second"] == workspace.RECIPIENT_CONFLICT
        assert set(peers) == {"beta"}
    else:
        assert outcomes["second"] == workspace.RECIPIENT_ALREADY_REGISTERED
        assert set(peers) == {"beta"}
    assert peers["beta"]["recipient_kid"] == cards[0]["recipient_kid"]
    assert before_foreign == [snapshot(root) for root in roots[1:]]
    assert not list((a.root / "outbox").glob("*.senv"))


@pytest.mark.parametrize("conflict", [False, True])
def test_fresh_process_writers_share_registry_lock(trio, tmp_path, conflict):
    roots, cards = trio
    helper = tmp_path / "writer.py"
    helper.write_text('''import json,sys,time
from pathlib import Path
from saimail import workspace
from sailang import SailangError
local,peer,card,alias,ready,go=sys.argv[1:]
view=workspace.load_workspace_headers(local)
payload=json.loads(Path(card).read_text())
Path(ready).write_text("ready")
deadline=time.monotonic()+15
while not Path(go).exists():
    if time.monotonic()>deadline: raise RuntimeError("test start gate timed out")
    time.sleep(.01)
try: result=workspace.add_recipient(view,alias,payload,peer)
except SailangError as e: result={"status":e.code}
print(json.dumps(result))
''', encoding="utf-8")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    go = tmp_path / "go"
    ready = [tmp_path / f"ready-{i}" for i in range(2)]
    procs = []
    foreign = [snapshot(root) for root in roots[1:]]
    try:
        for i in range(2):
            card = tmp_path / f"card-{i}.json"
            card.write_text(json.dumps(cards[i]), encoding="utf-8")
            alias = "same" if conflict else ("beta", "gamma")[i]
            procs.append(subprocess.Popen([sys.executable, str(helper), str(roots[0]),
                                          str(roots[i + 1]), str(card), alias,
                                          str(ready[i]), str(go)],
                                         cwd=ROOT, env=env, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, text=True))
        deadline = time.monotonic() + 15
        while not all(p.exists() for p in ready):
            assert time.monotonic() < deadline, "fresh process setup timed out"
            time.sleep(0.01)
        go.write_text("start", encoding="utf-8")
        results = []
        for proc in procs:
            out, err = proc.communicate(timeout=20)
            assert proc.returncode == 0 and not err, (out, err)
            results.append(json.loads(out))
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.kill()
                proc.communicate()
    peers = workspace.load_workspace_headers(roots[0]).peers
    if conflict:
        assert sorted(r["status"] for r in results) == sorted([
            workspace.RECIPIENT_ADDED, workspace.RECIPIENT_CONFLICT])
        winner = next(i for i, r in enumerate(results) if r["status"] == workspace.RECIPIENT_ADDED)
        assert peers["same"]["recipient_kid"] == cards[winner]["recipient_kid"]
    else:
        assert all(r["status"] == workspace.RECIPIENT_ADDED for r in results)
        assert set(peers) == {"beta", "gamma"}
    assert foreign == [snapshot(root) for root in roots[1:]]


def test_write_failure_releases_lock_without_changing_mapping(trio, monkeypatch):
    roots, cards = trio
    a = workspace.load_workspace_headers(roots[0])
    before = (a.root / workspace.PEERS_NAME).read_bytes()
    original = workspace._write_peers

    def fail(*args):
        raise PermissionError("test disk refusal")

    monkeypatch.setattr(workspace, "_write_peers", fail)
    with pytest.raises(SailangError) as exc:
        workspace.add_recipient(a, "beta", cards[0], roots[1])
    assert exc.value.code == workspace.RECIPIENT_REGISTRY_UNAVAILABLE
    assert (a.root / workspace.PEERS_NAME).read_bytes() == before
    monkeypatch.setattr(workspace, "_write_peers", original)
    assert workspace.add_recipient(a, "beta", cards[0], roots[1])["ok"]


def test_lock_timeout_is_structured_and_does_not_modify_registry(trio, monkeypatch, capsys, tmp_path):
    roots, cards = trio
    card = tmp_path / "card.json"
    card.write_text(json.dumps(cards[0]), encoding="utf-8")
    before = (roots[0] / workspace.PEERS_NAME).read_bytes()

    def busy(cls, fd, code):
        raise SailangError(code, "test contention")

    monkeypatch.setattr(postoffice._OsFileLock, "_acquire", classmethod(busy))
    rc = saimail_local.main(["recipient", "add", "--workspace", str(roots[0]),
                             "--alias", "beta", "--card", str(card),
                             "--peer-workspace", str(roots[1]), "--json"])
    answer = json.loads(capsys.readouterr().out)
    assert rc == 1 and answer["status"] == workspace.RECIPIENT_LOCK_TIMEOUT
    assert answer["network_attempts"] == 0
    assert (roots[0] / workspace.PEERS_NAME).read_bytes() == before


def test_failed_lock_acquisition_closes_descriptor(tmp_path, monkeypatch):
    captured = []

    def busy(cls, fd, code):
        captured.append(fd)
        raise SailangError(code, "test contention")

    monkeypatch.setattr(postoffice._OsFileLock, "_acquire", classmethod(busy))
    # Exercise the production registry lock. The pre-change subject used the
    # shared primitive; the repaired subject adds only local entry cleanup.
    lock_type = getattr(workspace, "_RecipientRegistryLock", postoffice._OsFileLock)
    lock = lock_type(tmp_path / "lock")
    try:
        with pytest.raises(SailangError), lock:
            pytest.fail("a refused acquisition cannot enter the critical section")
        with pytest.raises(OSError):
            os.fstat(captured[0])
    finally:
        if lock._fd is not None:
            os.close(lock._fd)
            lock._fd = None


def test_corrupt_registry_after_view_load_refuses_without_rewrite(trio):
    roots, cards = trio
    a = workspace.load_workspace_headers(roots[0])
    path = a.root / workspace.PEERS_NAME
    malformed = b'{"schema":'
    path.write_bytes(malformed)
    with pytest.raises(SailangError) as exc:
        workspace.add_recipient(a, "beta", cards[0], roots[1])
    assert exc.value.code == workspace.INVALID_WORKSPACE
    assert path.read_bytes() == malformed


def test_listing_remains_read_only_and_keyless(trio):
    roots, _ = trio
    a = workspace.load_workspace_headers(roots[0])
    before = snapshot(a.root)
    assert workspace.list_recipients(a)["recipients"] == []
    assert snapshot(a.root) == before


def test_invalid_card_creates_no_registry_lock_or_mapping(trio):
    roots, _ = trio
    a = workspace.load_workspace_headers(roots[0])
    before = snapshot(a.root)
    with pytest.raises(SailangError):
        workspace.add_recipient(a, "beta", {}, roots[1])
    assert snapshot(a.root) == before
