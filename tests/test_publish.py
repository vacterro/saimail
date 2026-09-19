"""T-42/C2 acceptance: immutable evidence publication never overwrites a winner.

``saimail.publish.publish_immutable`` is the one primitive behind the
quarantine record/derivative writes and the stability registration. What is
proven here, mechanically and with real concurrent writers:

* two writers with different bytes and one target produce exactly one winner;
  the loser receives the named conflict and the winner's bytes are untouched;
* two writers with identical bytes converge idempotently and neither rewrites
  the other's object;
* a failure before the publish step leaves no target and no staged temporary;
* a filesystem without hard links degrades to exclusive creation, which keeps
  the no-overwrite contract (documented as weaker: bytes stream into the name).
"""

from __future__ import annotations

import os
import threading

import pytest

from sailang import SailangError
from saimail.publish import IDEMPOTENT, PUBLISHED, publish_immutable


def err(fn, *a, **k):
    with pytest.raises(SailangError) as e:
        fn(*a, **k)
    return e.value.code


def test_one_writer_publishes_complete_bytes(tmp_path):
    target = tmp_path / "evidence" / "SRC-001.json"
    assert publish_immutable(target, b"complete bytes\n",
                             conflict_code="EVIDENCE_EXISTS_DIFFERENT") == PUBLISHED
    assert target.read_bytes() == b"complete bytes\n"
    assert list(tmp_path.joinpath("evidence").iterdir()) == [target], \
        "no staged temporary survives a successful publish"


def test_two_writers_different_bytes_produce_exactly_one_winner(tmp_path):
    """The T-42/C2 reproduction: a real race, not a sequential simulation."""
    target = tmp_path / "winner.json"
    barrier = threading.Barrier(2)
    outcome = {}

    def writer(payload):
        barrier.wait()
        try:
            outcome[payload] = publish_immutable(
                target, payload, conflict_code="EVIDENCE_EXISTS_DIFFERENT")
        except SailangError as exc:
            outcome[payload] = exc.code

    threads = [threading.Thread(target=writer, args=(payload,))
               for payload in (b"writer A", b"writer B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    published = [payload for payload, result in outcome.items() if result == PUBLISHED]
    assert len(published) == 1, outcome
    loser = next(payload for payload in outcome if payload != published[0])
    assert outcome[loser] == "EVIDENCE_EXISTS_DIFFERENT", \
        "the loser gets the named conflict, not silence"
    assert target.read_bytes() == published[0], "the winner's bytes remain untouched"
    assert list(tmp_path.iterdir()) == [target], "no staged temporaries are left behind"


def test_two_writers_identical_bytes_converge_without_rewriting(tmp_path):
    target = tmp_path / "same.json"
    barrier = threading.Barrier(2)
    results = []

    def writer():
        barrier.wait()
        results.append(publish_immutable(target, b"identical evidence\n",
                                         conflict_code="EVIDENCE_EXISTS_DIFFERENT"))

    threads = [threading.Thread(target=writer) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert set(results) <= {PUBLISHED, IDEMPOTENT} and results, results
    assert PUBLISHED in results, "someone did publish the object exactly once"
    assert target.read_bytes() == b"identical evidence\n"
    # and a later identical writer still converges instead of failing
    assert publish_immutable(target, b"identical evidence\n",
                             conflict_code="EVIDENCE_EXISTS_DIFFERENT") == IDEMPOTENT
    assert target.read_bytes() == b"identical evidence\n"


def test_a_failure_before_publication_leaves_nothing_visible(tmp_path, monkeypatch):
    target = tmp_path / "partial.json"
    real_fsync = os.fsync

    def failing(descriptor):
        raise OSError("disk went away")

    monkeypatch.setattr(os, "fsync", failing)
    with pytest.raises(OSError):
        publish_immutable(target, b"staged but never published\n",
                          conflict_code="EVIDENCE_EXISTS_DIFFERENT")
    monkeypatch.setattr(os, "fsync", real_fsync)
    assert not target.exists(), "no evidence object appeared"
    assert list(tmp_path.iterdir()) == [], "the staged temporary was cleaned up"


def test_a_filesystem_without_hard_links_still_never_overwrites(tmp_path, monkeypatch):
    target = tmp_path / "fallback.json"
    real_link = os.link

    def refusing(source, destination):
        raise OSError("hard links are not supported on this filesystem")

    monkeypatch.setattr(os, "link", refusing)
    assert publish_immutable(target, b"via the exclusive fallback\n",
                             conflict_code="EVIDENCE_EXISTS_DIFFERENT") == PUBLISHED
    monkeypatch.setattr(os, "link", real_link)
    assert target.read_bytes() == b"via the exclusive fallback\n"
    assert err(publish_immutable, target, b"different bytes entirely\n",
               conflict_code="EVIDENCE_EXISTS_DIFFERENT") == "EVIDENCE_EXISTS_DIFFERENT"
    assert target.read_bytes() == b"via the exclusive fallback\n"
