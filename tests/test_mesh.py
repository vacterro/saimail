"""Multi-agent mesh torture (T-123, SRC-108 item 8, SRC-109).

A real agent mesh is many independent processes writing into each other's
mailboxes at once, retrying, and dying in the middle. These controls build full
meshes of 2, 4, 8 and 12 agents, run two processes per agent that send the same
facts to every peer twice, kill every agent inside the outbox lock after a
delivery, restart them, and then check the one property that matters: every
recipient holds exactly one message per fact per sender, every index is intact,
and no outbox is left with a pending intent.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import timedelta
from pathlib import Path

import pytest

from saimail import outbox, participants, postoffice, workspace

ROOT = Path(__file__).resolve().parent.parent
LINEAGE = "lineage-" + "e6" * 16

AGENT = r"""
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
from saimail import notify, postoffice, workspace

root, lineage, me, peers, facts, go, die_after = (
    sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5].split(","), int(sys.argv[6]),
    sys.argv[7], int(sys.argv[8]))
if die_after:
    original = postoffice.PostOffice.deliver
    delivered = [0]
    def deliver_then_maybe_die(self, data):
        result = original(self, data)
        delivered[0] += 1
        if delivered[0] >= die_after:
            os._exit(77)  # inside the outbox lock, before DELIVERED is recorded
        return result
    postoffice.PostOffice.deliver = deliver_then_maybe_die
A = workspace.load_workspace(root)
deadline = time.monotonic() + 120
while not os.path.exists(go) and time.monotonic() < deadline:
    time.sleep(0.001)
statuses = {}
for fact in range(facts):
    for peer in peers:
        for _repeat in range(2):  # every fact is retried once
            result = notify.notify(A, lineage=lineage, work=f"T-{100 + fact}",
                                   trigger="finding", to_seat=peer,
                                   claim=f"fact {fact} from {me} to {peer}")
            statuses[result["status"]] = statuses.get(result["status"], 0) + 1
print(json.dumps(statuses))
"""


def _mesh(tmp_path, size):
    seats = [f"agent{number:02d}" for number in range(size)]
    boxes = {}
    for seat in seats:
        workspace.init_workspace(tmp_path / seat, seat=seat)
        boxes[seat] = workspace.load_workspace(tmp_path / seat)
    cards = {seat: workspace.identity_card(box) for seat, box in boxes.items()}
    for seat, box in boxes.items():
        for peer in seats:
            if peer != seat:
                workspace.add_recipient(box, peer, cards[peer], boxes[peer].root)
                participants.admit_participant(box, LINEAGE, peer, triggers=["finding"])
    return seats, boxes


def _launch(boxes, seats, *, per_agent, facts, go, die_after=0):
    procs = []
    for seat in seats:
        peers = ",".join(peer for peer in seats if peer != seat)
        for _copy in range(per_agent):
            procs.append(subprocess.Popen(
                [sys.executable, "-c", AGENT, str(ROOT), str(boxes[seat].root), LINEAGE, seat,
                 peers, str(facts), str(go), str(die_after)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
    return procs


def _wait(procs, *, expect):
    outcomes = []
    for proc in procs:
        out, err = proc.communicate(timeout=300)
        assert proc.returncode in expect, err[-2000:]
        outcomes.append(json.loads(out) if proc.returncode == 0 else None)
    return outcomes


def _drain(seats, boxes):
    """A later turn: resume every outbox with a clock past any backoff.

    A transient contention error leaves an intent durably SEALED for a retry;
    that is not a loss. Nothing may be FAILED.
    """
    later = postoffice._format_utc(postoffice._parse_utc(postoffice.utc_now(), code="BAD_CLOCK")
                                   + timedelta(hours=2))
    for seat in seats:
        status = outbox.outbox_status(workspace.load_workspace_headers(boxes[seat].root))
        assert status["outbox"]["counts"][outbox.FAILED] == 0, (seat, status["outbox"])
        # Contention is waited for (lock timeouts back off); an I/O error means a
        # lock let a writer fail instead of wait.
        assert all(item["last_error"] != outbox.DELIVERY_IO_ERROR
                   for item in status["outbox"]["open"]), (seat, status["outbox"]["open"])
        outbox.resume_outbox(boxes[seat], budget=500, clock=lambda: later)


def _assert_exactly_once(seats, boxes, facts):
    for receiver in seats:
        view = workspace.load_workspace_headers(boxes[receiver].root)
        rows = workspace.list_inbox(view)["items"]  # also validates the whole index
        seen = [(row["from"], row["topic"]) for row in rows]
        expected = {(sender, f"T-{100 + fact}") for sender in seats if sender != receiver
                    for fact in range(facts)}
        assert len(seen) == len(set(seen)), f"{receiver} holds a duplicate logical message"
        assert set(seen) == expected, f"{receiver} lost or gained messages"
        assert len({row["envelope_id"] for row in rows}) == len(rows)
    for sender in seats:
        status = outbox.outbox_status(workspace.load_workspace_headers(boxes[sender].root))
        box = status["outbox"]
        assert box["pending"] == 0 and box["counts"][outbox.FAILED] == 0, (sender, box)
        assert box["counts"][outbox.DELIVERED] == (len(seats) - 1) * facts


@pytest.mark.parametrize("size", [2, 4, 8, 12])
def test_a_full_mesh_of_racing_retrying_agents_delivers_every_fact_once(tmp_path, size):
    seats, boxes = _mesh(tmp_path, size)
    go = tmp_path / "go"
    procs = _launch(boxes, seats, per_agent=2, facts=1, go=go)
    time.sleep(1.5)
    go.write_text("go", encoding="utf-8")
    outcomes = _wait(procs, expect=(0,))
    for outcome in outcomes:
        assert set(outcome) <= {outbox.DELIVERED, outbox.PENDING_RETRY}, outcome
    _drain(seats, boxes)
    _assert_exactly_once(seats, boxes, facts=1)


def test_every_agent_killed_inside_the_outbox_lock_recovers_to_exactly_once(tmp_path):
    seats, boxes = _mesh(tmp_path, 4)
    go = tmp_path / "go"
    go.write_text("go", encoding="utf-8")
    killed = _launch(boxes, seats, per_agent=1, facts=2, go=go, die_after=2)
    _wait(killed, expect=(77,))
    started = time.monotonic()
    restarted = _launch(boxes, seats, per_agent=1, facts=2, go=go)
    _wait(restarted, expect=(0,))
    assert time.monotonic() - started < 120, "an abandoned outbox lock must not wedge a restart"
    _drain(seats, boxes)
    _assert_exactly_once(seats, boxes, facts=2)
