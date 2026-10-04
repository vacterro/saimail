"""FUTURE GATE Wave 4: downtime recovery with a coalesced catch-up queue.

The wave exists because "we were down" used to mean one of two bad things:
nothing runs until a person notices, or everything runs at once and replays
work the system already did. These tests pin the acceptance cases from the wave
document:

* long downtime with many missed opportunities
* bounded catch-up work, no blind duplicate replay
* restart during catch-up remains idempotent
* an unreachable peer parks visibly
* normal current state supersedes stale owed work safely

plus the invariants those rest on: one entry per logical job forever, a plan
pass that never forgives a retry cooldown, a reap that only reclaims a stale
claim, a notice that states facts and refuses to name a cause, work that parks
instead of disappearing, and -- the defect that shaped this module -- a queue
that stays readable after its own first write.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

from sailang import SailangError
from saimail import catchup, custody, ledger, outbox, postoffice, trust, workspace

ROOT = Path(__file__).resolve().parent.parent
T0 = "2026-10-04T09:00:00Z"
T1 = "2026-10-04T12:00:00Z"
T2 = "2026-10-04T18:00:00Z"
T3 = "2026-10-05T09:00:00Z"


def _clock(*stamps):
    """A deterministic clock that repeats its last stamp when exhausted.

    A send advances the clock several times (seal, attempt, commit). A test that
    pinned a call count would be asserting the sequence, not the queue.
    """
    sequence = list(stamps)

    def now():
        return sequence.pop(0) if len(sequence) > 1 else sequence[0]

    return now


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _after(seconds: int, base: str) -> str:
    moment = (postoffice._parse_utc(base, code=catchup.QUEUE_UNREADABLE)
              + timedelta(seconds=seconds))
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _pair(tmp_path, *, mode=custody.CUSTODY_RAW, settle=True):
    """Two registered workspaces. `settle` pins trust, so tests that are not
    ABOUT trust do not have to explain a TRUST entry in every count."""
    workspace.init_workspace(tmp_path / "A", seat="alpha", custody=mode)
    workspace.init_workspace(tmp_path / "B", seat="beta", custody=mode)
    A = workspace.load_workspace(tmp_path / "A")
    B = workspace.load_workspace(tmp_path / "B")
    workspace.add_recipient(A, "beta", workspace.identity_card(B), B.root)
    workspace.add_recipient(B, "alpha", workspace.identity_card(A), A.root)
    if settle:
        trust.pin(A, "beta", source="test fixture", clock=_clock(T0))
        A = workspace.load_workspace(tmp_path / "A")
    return A, B


def _send(A, *, key, claim="one fact", to="beta", clock=None):
    return outbox.submit_send(A, to, key=key, claim=claim, clock=clock or _clock(T1))


def _view(A, *, now=T3):
    return catchup.queue(A, clock=_clock(now))["queue"]


def _entries(A, *, now=T3, kind=None):
    view = _view(A, now=now)
    entries = view["entries"] if isinstance(view, dict) and "entries" in view else []
    if kind is not None:
        entries = [entry for entry in entries if entry["kind"] == kind]
    return {entry["entry_id"]: entry for entry in entries}


def _cli(*argv):
    proc = subprocess.run(
        [sys.executable, "-m", "saimail_local", *argv, "--json"],
        cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _env_id(key: str) -> str:
    """A real envelope id: sha256 of the key, in the shape the Post Office names."""
    return "sha256:" + hashlib.sha256(key.encode("utf-8")).hexdigest()


def _aged(path: Path, seconds: int) -> None:
    """Backdate a path's mtime so it reads as stale residue."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        if path.suffix == ".staging":
            path.mkdir()
        else:
            path.write_bytes(b"")
    old = time.time() - seconds
    os.utime(path, (old, old))


def _crash_after_commit(A, keys):
    """Leave the ledger naming envelopes that were never delivered.

    The crash window the wave exists for: SEALED reached, the container is real,
    DELIVERED never happened. The record knows the envelope; neither this
    mailbox nor its outbox holds a body for it.
    """
    for key in keys:
        for event in (ledger.CREATED, ledger.SEALED):
            ledger.append(A, event, message_id=key, actor="alpha", at=T1,
                          envelope_id=_env_id(key))


def _lands(A, key):
    """The out-of-band fix: the send finally lands and the record learns it.

    The chain is walked in full. `fold` collects a forbidden transition as
    ILLEGAL rather than pretending it happened, so a helper that skipped
    OUTBOX_COMMITTED would leave the message stuck at SEALED -- which is the
    ledger being right and the test being wrong.
    """
    for event in (ledger.OUTBOX_COMMITTED, ledger.DELIVERY_ATTEMPTED,
                  ledger.DELIVERED):
        ledger.append(A, event, message_id=key, actor="alpha", at=T2,
                      envelope_id=_env_id(key), attempt=1)


# --------------------------------------------------------------------------
# acceptance
# --------------------------------------------------------------------------

def test_long_downtime_coalesces_missed_opportunities(tmp_path):
    """Twelve missed windows, three logical jobs, three entries -- not twelve."""
    A, B = _pair(tmp_path)
    catchup.record_tick(A, clock=_clock(T0))
    _crash_after_commit(A, ("job-0", "job-1", "job-2"))

    # Twelve plan passes across twelve hours of "being down": each observes the
    # same three debts. The queue must not grow and must not age-reset.
    for hour in range(10, 22):
        catchup.plan(A, clock=_clock(f"2026-10-04T{hour:02d}:00:00Z"))

    owed = _entries(A, kind=catchup.RECONCILE)
    assert len(owed) == 3, "one entry per logical job, forever"
    assert {entry["logical_id"] for entry in owed.values()} == {
        _env_id(key) for key in ("job-0", "job-1", "job-2")}
    # first_owed_at is the FIRST pass that saw them, not the latest.
    assert {entry["first_owed_at"] for entry in owed.values()} == \
        {"2026-10-04T10:00:00Z"}
    assert all(entry["attempts"] == 0 for entry in owed.values()), \
        "observing is not attempting"

    # The gap is reported honestly: a long duration, and no cause invented.
    gap = catchup.detect_gaps(A, clock=_clock("2026-10-04T21:00:00Z"))["gap"]
    assert gap["state"] == "DOWN"
    assert gap["downtime_seconds"] == 12 * 3600
    assert gap["outage_cause"] == catchup.UNKNOWN_CAUSE
    assert catchup.notice(A, clock=_clock("2026-10-04T21:00:00Z"))[
        "notice"]["owed_jobs"] == 3


def test_plan_pass_does_not_forgive_a_cooldown(tmp_path):
    """Re-observing owed work must not reset its retry history."""
    A, B = _pair(tmp_path)
    _crash_after_commit(A, ("job-0",))
    catchup.plan(A, clock=_clock(T1))
    entry_id = f"RECONCILE:{_env_id('job-0')}"
    first_owed = _entries(A, now=T1)[entry_id]["first_owed_at"]

    claimed = catchup.claim(A, limit=4, clock=_clock(T1))
    catchup.park(A, claimed["claimed"][0]["entry_id"], catchup.STILL_OWED,
                 detail="still owed", clock=_clock(T1))
    parked = _entries(A, now=T1)[entry_id]
    cooldown, attempts = parked["next_attempt_at"], parked["attempts"]
    assert cooldown, "a parked entry carries a cooldown"

    # Six more plan passes during the cooldown. None may forgive it.
    for hour in range(13, 19):
        catchup.plan(A, clock=_clock(f"2026-10-04T{hour:02d}:00:00Z"))
    after = _entries(A, now="2026-10-04T18:00:00Z")[entry_id]
    assert after["first_owed_at"] == first_owed, "the age of the debt must not reset"
    assert after["attempts"] == attempts, "observing is not attempting"
    assert after["next_attempt_at"] == cooldown, "a cooldown survives observation"
    assert after["parked_reason"] == catchup.STILL_OWED, "parking is not forgotten"

    # And a claim INSIDE the cooldown window hands out nothing.
    assert catchup.claim(A, limit=4,
                        clock=_clock(_after(30, T1)))["counts"]["claimed"] == 0
    # Past it, the entry is due again.
    assert catchup.claim(A, limit=4, clock=_clock(T2))["counts"]["claimed"] == 1


def test_catchup_work_is_bounded_and_never_duplicated(tmp_path):
    """Claim is capped, and an entry in flight is never handed out twice."""
    A, B = _pair(tmp_path)
    for index in range(10):
        _crash_after_commit(A, (f"job-{index}",))
    catchup.plan(A, clock=_clock(T1))

    first = catchup.claim(A, limit=3, clock=_clock(T2))
    assert len(first["claimed"]) == 3
    held = {entry["entry_id"] for entry in first["claimed"]}
    assert all(entry["state"] == catchup.IN_FLIGHT for entry in first["claimed"])
    assert all(entry["attempts"] == 1 for entry in first["claimed"])

    # A second claim must not touch what is already in flight.
    second = catchup.claim(A, limit=8, clock=_clock(T2))
    assert held.isdisjoint({entry["entry_id"] for entry in second["claimed"]})
    assert len(second["claimed"]) <= catchup.MAX_CLAIM_LIMIT

    # The in-flight slice stays in flight until it completes or goes stale.
    assert all(_entries(A)[entry_id]["state"] == catchup.IN_FLIGHT
               for entry_id in held)

    # Asking again is a no-op, not a second copy.
    before = json.dumps(_entries(A)[sorted(held)[0]], sort_keys=True)
    catchup.claim(A, limit=8, clock=_clock(T2))
    assert json.dumps(_entries(A)[sorted(held)[0]], sort_keys=True) == before

    # The limit is a hard ceiling even when far more work is due.
    for index in range(10, 30):
        _crash_after_commit(A, (f"job-{index}",))
    catchup.plan(A, clock=_clock(T2))
    assert len(catchup.claim(A, limit=5, clock=_clock(T2))["claimed"]) == 5


def test_restart_during_catchup_is_idempotent(tmp_path):
    """A crash mid-catch-up loses no work and repeats none of it."""
    A, B = _pair(tmp_path)
    for index in range(4):
        _crash_after_commit(A, (f"job-{index}",))
    catchup.plan(A, clock=_clock(T1))
    claimed = catchup.claim(A, limit=2, clock=_clock(T2))
    held = [entry["entry_id"] for entry in claimed["claimed"]]

    # The process dies here. A new process reads the same queue off disk.
    restarted = workspace.load_workspace(A.root)
    assert _view(restarted)["totals"][catchup.IN_FLIGHT] == 2
    reclaimed = catchup.claim(restarted, limit=8, clock=_clock(T2))
    assert set(held).isdisjoint({entry["entry_id"] for entry in reclaimed["claimed"]})

    # Past the in-flight timeout the claim is stale and IS reclaimed -- counted
    # out loud, never silently duplicated.
    reap_time = _after(catchup.IN_FLIGHT_TIMEOUT_SECONDS + 60, T2)
    reaped = catchup.claim(restarted, limit=8, clock=_clock(reap_time))
    # Both claims are now stale, so all four entries are reclaimed -- and the
    # reap is counted, so the history says a crash happened.
    assert reaped["counts"]["reaped"] == 4
    assert set(held) <= {entry["entry_id"] for entry in reaped["claimed"]}
    # Four claims total, each entry counted once per claim: not sixteen.
    assert _view(restarted, now=reap_time)["attempts"] == 8


def test_unreachable_peer_parks_visibly(tmp_path):
    """A peer we cannot reach gets its own named reason, and stays visible."""
    A, B = _pair(tmp_path)
    # The peer is registered, then its mailbox disappears: the send fails on IO
    # and the intent is left FAILED, which is what catch-up has to clean up.
    shutil.rmtree(B.root)
    sent = _send(A, key="job-0", to="beta", clock=_clock(T1))
    # A vanished mailbox is a TRANSIENT failure: the intent stays durable and
    # retry-pending rather than failing outright.
    assert sent["status"] == outbox.PENDING_RETRY
    assert outbox._all_intents(A)[0]["last_error"] in outbox.TRANSIENT_CODES

    planned = catchup.plan(A, clock=_clock(T2))
    assert planned["ok"] is True
    deliveries = _entries(A, kind=catchup.DELIVERY)
    assert deliveries, "an undeliverable send must show up as owed work"
    entry = next(iter(deliveries.values()))
    assert entry["peer"] == "beta"
    assert entry["state"] == catchup.PARKED, "already known to be undeliverable"
    assert entry["parked_reason"] == catchup.PEER_UNREACHABLE

    result = catchup.run(A, limit=8, clock=_clock(T2))
    assert entry["entry_id"] in result["parked"], "unreachable parks, never drops"
    after = _entries(A)[entry["entry_id"]]
    assert after["state"] == catchup.PARKED
    assert after["parked_reason"] == catchup.PEER_UNREACHABLE
    assert after["next_attempt_at"], "a parked entry carries a cooldown"

    # Visible in the queue view AND in the notice, not just in the file.
    assert _view(A)["totals"][catchup.PARKED] >= 1
    notice = catchup.notice(A, clock=_clock(T2))
    assert notice["parked_reasons"][catchup.PEER_UNREACHABLE] >= 1
    assert notice["notice"]["parked"] >= 1


def test_a_deregistered_peer_is_also_unreachable(tmp_path):
    """Losing the peer registration is its own park reason, not a send failure."""
    A, B = _pair(tmp_path)
    _send(A, key="job-0", clock=_clock(T1))
    intent = outbox._all_intents(A)[0]
    intent["state"] = outbox.FAILED
    intent["failure"] = "SOMETHING_ELSE"
    outbox._write(A, intent)

    (A.root / "peers.json").unlink()
    stranded = workspace.load_workspace(A.root)
    catchup.plan(stranded, clock=_clock(T2))
    entry = _entries(stranded, kind=catchup.DELIVERY)
    assert entry and next(iter(entry.values()))["parked_reason"] == \
        catchup.PEER_UNREACHABLE


def test_current_state_supersedes_stale_owed_work(tmp_path):
    """When the debt is gone, the entry is retired -- never deleted."""
    A, B = _pair(tmp_path)
    _crash_after_commit(A, ("job-0",))
    catchup.plan(A, clock=_clock(T1))
    entry_id = f"RECONCILE:{_env_id('job-0')}"
    assert entry_id in _entries(A, now=T1)

    # The work is done by other means: the send lands and the record learns it.
    _lands(A, "job-0")
    planned = catchup.plan(A, clock=_clock(T2))
    assert planned["planned"]["superseded"] == 1

    view = _view(A)
    assert view["totals"][catchup.SUPERSEDED] == 1
    assert view["retired"] == 1
    # Retired is not gone: the entry is still readable, with its evidence.
    stored = catchup.read_queue(A)["entries"][entry_id]
    assert stored["state"] == catchup.SUPERSEDED
    assert stored["evidence"]["superseded_at"] == T2
    assert stored["evidence"]["ledger_state"], "the evidence survives retirement"

    # And re-planning changes nothing.
    assert catchup.plan(A, clock=_clock(T2))["planned"]["superseded"] == 0


# --------------------------------------------------------------------------
# the defects that shaped the module
# --------------------------------------------------------------------------

def test_a_delivered_message_is_never_owed_work(tmp_path):
    """A send that succeeded leaves nothing behind to replay.

    The body of a delivered message lives in the RECEIVER's mailbox, so the
    sender legitimately holds no local copy. Reading that absence as "owed"
    would turn every healthy delivery into permanent debt -- a replay storm
    generated by the recovery path itself.
    """
    A, B = _pair(tmp_path)
    for index in range(6):
        _send(A, key=f"job-{index}", clock=_clock(T1))
    assert ledger.fold(ledger.read_events(A)[0])["messages"], "the sends are recorded"

    planned = catchup.plan(A, clock=_clock(T2))
    assert planned["planned"]["observed"] == 0
    assert _view(A)["entries"] == []
    assert catchup.run(A, limit=16, clock=_clock(T2))["ran"]["claimed"] == 0


def test_the_queue_survives_its_own_first_write(tmp_path):
    """A first plan must not write a file the module then refuses to read."""
    A, B = _pair(tmp_path)
    _crash_after_commit(A, ("job-0",))
    catchup.plan(A, clock=_clock(T1))
    raw = json.loads(catchup._queue_path(A).read_bytes())
    assert raw["schema"] == catchup.CATCHUP_SCHEMA
    assert raw["version"] == catchup.CATCHUP_VERSION
    # Readable now, and still readable after a restart.
    assert _view(A, now=T1)["totals"][catchup.QUEUED] == 1
    assert _view(workspace.load_workspace(A.root), now=T1)["entries"]


def test_a_malformed_envelope_id_is_reported_not_fatal(tmp_path):
    """The ledger does not police the shape of an envelope_id, so one the Post
    Office cannot address reaches us from a record written in good faith. One
    bad row must not take down the whole planning pass."""
    A, B = _pair(tmp_path)
    ledger.append(A, ledger.CREATED, message_id="job-0", actor="alpha", at=T1,
                  envelope_id="not-a-real-envelope-id")
    result = catchup.plan(A, clock=_clock(T2))
    assert result["ok"] is True
    entry = _entries(A, kind=catchup.RECONCILE)
    assert entry, "the bad id is still owed work, and still visible"
    assert next(iter(entry.values()))["evidence"]["malformed"] \
        == "BAD_ENVELOPE_ID"
    # And it parks rather than vanishing or crashing the runner.
    assert catchup.run(A, limit=8, clock=_clock(T2))["ran"]["claimed"] == 1


# --------------------------------------------------------------------------
# invariants
# --------------------------------------------------------------------------

def test_gap_detection_reports_duration_and_never_a_cause(tmp_path):
    A, B = _pair(tmp_path)
    first = catchup.detect_gaps(A, clock=_clock(T0))["gap"]
    assert first["state"] == "FIRST_OBSERVATION"
    assert first["downtime_seconds"] is None

    catchup.record_tick(A, clock=_clock(T0))
    current = catchup.detect_gaps(A, clock=_clock(T0))["gap"]
    assert current["state"] == "CURRENT"
    assert current["downtime_seconds"] == 0

    down = catchup.detect_gaps(A, clock=_clock(T1))["gap"]
    assert down["state"] == "DOWN"
    assert down["downtime_seconds"] == 3 * 3600
    assert down["outage_cause"] == catchup.UNKNOWN_CAUSE
    assert down["evidence"] == ["DOWNTIME_DURATION_ONLY"]


def test_unreadable_service_state_is_not_no_downtime(tmp_path):
    A, B = _pair(tmp_path)
    catchup.record_tick(A, clock=_clock(T0))
    catchup._service_path(A).write_bytes(b"{not json")
    result = catchup.detect_gaps(A, clock=_clock(T1))
    assert result["status"] == catchup.QUEUE_UNREADABLE
    assert result["operator_action_required"] is True
    assert "not the same as no gap" in result["detail"]


def test_notice_states_facts_only(tmp_path):
    A, B = _pair(tmp_path)
    catchup.record_tick(A, clock=_clock(T0))
    _crash_after_commit(A, ("job-0", "job-1"))
    catchup.plan(A, clock=_clock(T1))

    result = catchup.notice(A, clock=_clock(T3))
    notice = result["notice"]
    assert notice["outage_cause"] == catchup.UNKNOWN_CAUSE
    assert notice["owed_jobs"] == 2
    assert notice["downtime_seconds"] == 24 * 3600, "measured from the last tick"
    assert notice["oldest_owed_seconds"] == 21 * 3600, "measured from the debt"
    assert notice["attempts"] == 0
    assert "UNKNOWN" in result["detail"]

    # Facts, not instructions. A notice is exactly what an operator acts on
    # without checking, so it must never read as advice.
    body = json.dumps(notice).lower()
    for word in ("should", "recommend", "you must", "probably", "likely"):
        assert word not in body, f"the notice stated an opinion: {word!r}"


def test_an_unsettled_trust_verdict_is_owed_and_never_settled_for_you(tmp_path):
    """A peer nobody ever decided about is owed a human, not a default."""
    A, B = _pair(tmp_path, settle=False)
    assert trust.decide(A, "beta")["state"] == trust.UNKNOWN

    catchup.plan(A, clock=_clock(T1))
    entry = _entries(A, kind=catchup.TRUST)
    assert len(entry) == 1
    assert next(iter(entry.values()))["peer"] == "beta"

    result = catchup.run(A, limit=8, clock=_clock(T1))
    assert result["ran"]["parked"] == 1
    stored = catchup.read_queue(A)["entries"]
    assert [item for item in stored.values() if item["state"] == catchup.DONE] == [], \
        "the queue must not decide trust on the operator's behalf"
    assert next(iter(stored.values()))["parked_reason"] == catchup.TRUST_NEEDS_REVIEW
    # And the verdict really is still unset.
    assert trust.decide(A, "beta")["state"] == trust.UNKNOWN


def test_a_free_lock_is_an_observed_fact_not_owed_work(tmp_path):
    """A lock file with no holder is normal; the next writer reuses it.

    Making it a queue entry would manufacture a debt that can never clear,
    because the condition is permanently true for every workspace that has ever
    written. A debt nobody can clear is not a queue.
    """
    A, B = _pair(tmp_path)
    free = A.root / "mail" / "inbox" / "beta" / postoffice.INDEX_LOCK_NAME
    _aged(free, catchup.STALE_RESIDUE_SECONDS + 600)
    catchup.plan(A, clock=_clock(T3))
    assert _entries(A, kind=catchup.RESIDUE) == {}, "a free lock owes nothing"
    facts = _view(A)["residue"]
    assert any(item["path"].endswith(postoffice.INDEX_LOCK_NAME) for item in facts)
    assert all(item["remedy"] == "NONE" for item in facts)
    assert catchup.notice(A, clock=_clock(T3))["notice"][
        "free_locks_observed"] == len(facts)


def test_a_live_lock_is_not_observed_as_residue(tmp_path):
    """Probing must never mistake a held lock for a stale one."""
    A, B = _pair(tmp_path)
    held = A.root / "mail" / "inbox" / "beta" / postoffice.INDEX_LOCK_NAME
    _aged(held, catchup.STALE_RESIDUE_SECONDS + 600)
    lock = postoffice._OsFileLock(held, busy_code=catchup.QUEUE_LOCK_TIMEOUT)
    lock.__enter__()
    try:
        catchup.plan(A, clock=_clock(T3))
        assert not any(item["path"].endswith(postoffice.INDEX_LOCK_NAME)
                       for item in _view(A)["residue"]), "a held lock is not residue"
    finally:
        lock.__exit__(None, None, None)
    # Once released it becomes an observation again -- and still owes nothing.
    catchup.plan(A, clock=_clock(T3))
    assert any(item["path"].endswith(postoffice.INDEX_LOCK_NAME)
               for item in _view(A)["residue"])


def test_an_abandoned_staging_directory_parks_and_is_never_deleted(tmp_path):
    """Whether an interrupted publish can be cleaned is a judgement, not a fact."""
    A, B = _pair(tmp_path)
    staging = A.root / "mail" / "inbox" / "beta" / "tmp-orphan.staging"
    _aged(staging, catchup.STALE_RESIDUE_SECONDS + 60)

    catchup.plan(A, clock=_clock(T3))
    residue = _entries(A, kind=catchup.RESIDUE)
    assert len(residue) == 1
    assert next(iter(residue.values()))["evidence"]["kind"] == "STAGING"

    result = catchup.run(A, limit=16, clock=_clock(T3))
    assert result["ran"]["parked"] == 1
    stored = catchup.read_queue(A)["entries"]
    assert next(iter(stored.values()))["parked_reason"] == \
        catchup.RESIDUE_NEEDS_REVIEW
    assert staging.is_dir(), "reported, not deleted: a writer may be mid-publish"


def test_queue_view_shows_every_class(tmp_path):
    A, B = _pair(tmp_path)
    for index in range(5):
        _crash_after_commit(A, (f"job-{index}",))
    catchup.plan(A, clock=_clock(T1))
    claimed = catchup.claim(A, limit=3, clock=_clock(T2))
    first, second = claimed["claimed"][0], claimed["claimed"][1]
    catchup.park(A, first["entry_id"], catchup.STILL_OWED, clock=_clock(T2))
    catchup.complete(A, second["entry_id"], detail="done by hand", clock=_clock(T2))

    view = _view(A, now=T2)
    for key in ("totals", "by_kind", "attempts", "oldest_owed_at",
                "oldest_owed_seconds", "entries", "retired", "residue"):
        assert key in view
    assert view["totals"][catchup.PARKED] == 1
    assert view["totals"][catchup.DONE] == 1
    assert view["totals"][catchup.IN_FLIGHT] == 1
    assert view["totals"][catchup.QUEUED] == 2
    assert view["retired"] == 1
    assert view["oldest_owed_seconds"] == 6 * 3600
    assert view["attempts"] == 3, "one per claim, counted once"


def test_queue_write_failure_is_operator_action_not_a_silent_pass(tmp_path,
                                                                monkeypatch):
    A, B = _pair(tmp_path)
    _crash_after_commit(A, ("job-0",))

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(postoffice, "_write_complete", boom)
    assert _code(catchup.plan, A, clock=_clock(T3)) == catchup.QUEUE_WRITE_FAILED
    monkeypatch.undo()
    assert catchup.plan(A, clock=_clock(T3))["ok"] is True


def test_unreadable_queue_refuses_rather_than_planning_empty(tmp_path):
    """Planning onto an unreadable queue would lose what it already knew."""
    A, B = _pair(tmp_path)
    _crash_after_commit(A, ("job-0",))
    catchup.plan(A, clock=_clock(T1))

    catchup._queue_path(A).write_bytes(b'{"schema": "SAIMAIL_CATCHUP_1", '
                                       b'"version": 1, "entries": '
                                       b'{"RECONCILE:x": {"kind": "RECONCILE"}}}')
    result = catchup.plan(A, clock=_clock(T3))
    assert result["status"] == catchup.QUEUE_UNREADABLE
    assert result["operator_action_required"] is True
    assert result["detail"], "the refusal explains itself"
    # The damaged file is left as found; nothing was guessed over it.
    assert catchup._queue_path(A).read_bytes().startswith(b'{"schema"')


def test_bad_input_is_refused_by_name(tmp_path):
    A, B = _pair(tmp_path)
    assert _code(catchup.complete, A, "no-such-entry") == catchup.UNKNOWN_ENTRY
    assert _code(catchup.park, A, "no-such-entry", catchup.STILL_OWED) \
        == catchup.UNKNOWN_ENTRY
    _crash_after_commit(A, ("job-0",))
    catchup.plan(A, clock=_clock(T1))
    entry_id = f"RECONCILE:{_env_id('job-0')}"
    assert _code(catchup.park, A, entry_id, "") == catchup.BAD_INPUT
    assert _code(catchup.park, A, entry_id, None) == catchup.BAD_INPUT


def test_queue_records_no_plaintext_and_no_private_key(tmp_path):
    A, B = _pair(tmp_path)
    catchup.record_tick(A, clock=_clock(T0))
    _send(A, key="job-0", claim="THE SECRET CLAIM TEXT", clock=_clock(T1))
    _crash_after_commit(A, ("job-1",))
    catchup.plan(A, clock=_clock(T3))
    raw = catchup._queue_path(A).read_bytes()
    assert b"THE SECRET CLAIM TEXT" not in raw
    assert b"private" not in raw.lower()
    assert b"private" not in catchup._service_path(A).read_bytes().lower()


def test_secret_free_workspace_can_read_the_queue(tmp_path):
    """The read surfaces must not demand a signing key."""
    A, B = _pair(tmp_path)
    _crash_after_commit(A, ("job-0",))
    catchup.plan(A, clock=_clock(T1))
    headers = workspace.load_workspace_headers(A.root)
    assert _view(headers, now=T1)["totals"][catchup.QUEUED] == 1
    assert catchup.notice(headers, clock=_clock(T1))["notice"]["owed_jobs"] == 1


# --------------------------------------------------------------------------
# CLI surface
# --------------------------------------------------------------------------

def test_cli_surface(tmp_path):
    A, B = _pair(tmp_path)
    root = str(A.root)
    _crash_after_commit(A, ("job-0", "job-1"))

    assert _cli("catchup", "tick", "--workspace", root)["ok"] is True
    assert _cli("catchup", "detect", "--workspace", root)["gap"][
        "outage_cause"] == catchup.UNKNOWN_CAUSE

    planned = _cli("catchup", "plan", "--workspace", root)
    assert planned["command"] == "catchup-plan"
    assert planned["planned"]["observed"] == 2

    view = _cli("catchup", "queue", "--workspace", root)
    assert view["ok"] is True and len(view["queue"]["entries"]) == 2

    notice = _cli("catchup", "notice", "--workspace", root)
    assert notice["notice"]["outage_cause"] == catchup.UNKNOWN_CAUSE
    assert notice["notice"]["owed_jobs"] == 2

    claimed = _cli("catchup", "claim", "--workspace", root, "--limit", "1")
    entry_id = claimed["claimed"][0]["entry_id"]
    assert _cli("catchup", "park", "--workspace", root, "--entry-id", entry_id,
                "--reason", catchup.STILL_OWED)["ok"] is True
    assert _cli("catchup", "complete", "--workspace", root, "--entry-id",
                entry_id)["ok"] is True
    ran = _cli("catchup", "run", "--workspace", root, "--limit", "4")
    assert ran["ok"] is True and ran["ran"]["claimed"] == 1


@pytest.mark.parametrize("limit", [0, -1, "8", None, True, 1.5])
def test_claim_rejects_a_bad_limit(tmp_path, limit):
    A, B = _pair(tmp_path)
    assert _code(catchup.claim, A, limit=limit) == catchup.BAD_INPUT