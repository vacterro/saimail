"""B-011 queue contract: receiver authority, durable candidates, crash-safe slots.

The scarce resource is human attention consumption, not message creation.
These tests hold the receiver-owned boundary: identity, admission, ordering,
reservation/ACK/release, crash recovery, corruption and privacy tripwires.
"""

import hashlib
import json
import multiprocessing
import re
import threading
from pathlib import Path

import pytest

from sailang.errors import SailangError

from saimail import human_attention as ha

HUMAN = "human-id:sha256:" + "7a" * 32
DIGEST = HUMAN.rsplit(":", 1)[1]
NOW = "2026-09-19T10:00:00Z"
AFTER_LEASE = "2026-09-19T10:05:00Z"


class MutableReceiverClock:
    def __init__(self, value: str):
        self.value = value
        self.reads = 0

    def __call__(self) -> str:
        self.reads += 1
        return self.value

    def set(self, value: str) -> None:
        self.value = value


def attention_root(tmp_path: Path) -> Path:
    return tmp_path / ha.ATTENTION_DIR / DIGEST


def ref(tag: str) -> str:
    return "sha256:" + hashlib.sha256(tag.encode("utf-8")).hexdigest()


def make_candidate(
    tag: str = "a",
    *,
    kind: str = ha.HUMAN_PRIVATE,
    allocation: str = "DECISION_REQUEST",
    deferral: str = "QUEUE_AND_CONTINUE",
    enqueued_at: str = NOW,
    to_human: str = HUMAN,
    source_ref: str = None,
) -> ha.AttentionCandidate:
    return ha.AttentionCandidate(
        to_human=to_human,
        source_kind=kind,
        source_ref=source_ref if source_ref is not None else ref(tag),
        allocation=allocation,
        deferral_policy=deferral,
        enqueued_at=enqueued_at,
    )


def queue(tmp_path: Path, **kwargs) -> ha.AttentionQueue:
    kwargs.setdefault("clock", MutableReceiverClock(NOW))
    return ha.AttentionQueue(tmp_path, human_id=HUMAN, **kwargs)


def admit(q: ha.AttentionQueue, candidate: ha.AttentionCandidate):
    return q.admit_receiver_candidate(
        source_kind=candidate.source_kind,
        source_ref=candidate.source_ref,
        allocation=candidate.allocation,
        deferral_policy=candidate.deferral_policy,
    )


def candidate_path(tmp_path: Path, candidate: ha.AttentionCandidate) -> Path:
    return (attention_root(tmp_path) / "candidates"
            / (candidate.candidate_id.rsplit(":", 1)[1] + ".json"))


def write_lease(tmp_path: Path, reservation: ha.Reservation) -> Path:
    path = (attention_root(tmp_path) / "leases"
            / (reservation.candidate_id.rsplit(":", 1)[1] + ".json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "CANDIDATE_ID": reservation.candidate_id,
        "LEASE_UNTIL": reservation.lease_until,
        "RESERVED_AT": reservation.reserved_at,
        "RESERVATION_ID": reservation.reservation_id,
        "SCHEMA": 1,
    }
    path.write_bytes((json.dumps(record, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False) + "\n").encode("utf-8"))
    return path


def _process_reserve(root: str, start, results) -> None:
    q = ha.AttentionQueue(root, human_id=HUMAN, clock=lambda: NOW)
    start.wait()
    results.put(q.reserve_next().status)


# --------------------------------------------------------------------
# contract: closed sets, identity, admission
# --------------------------------------------------------------------


def test_allocation_set_is_closed_receiver_vocabulary():
    assert ha.ALLOCATIONS == (
        "CRITICAL_RECOVERY", "AMBIGUITY_RESOLUTION", "DECISION_REQUEST",
        "ROUTINE_AUDIT", "IDLE_REPORT",
    )


def test_deferral_set_is_closed_receiver_vocabulary():
    assert ha.DEFERRAL_POLICIES == (
        "BLOCK_UNTIL_HUMAN", "QUEUE_AND_CONTINUE", "ESCALATE_AND_HALT",
    )


def test_source_kind_set_is_closed():
    assert ha.SOURCE_KINDS == (ha.HUMAN_PRIVATE, ha.EXTERNAL_REFERENCE)


def test_unknown_allocation_is_refused():
    with pytest.raises(SailangError) as exc:
        make_candidate(allocation="IMPORTANT")
    assert exc.value.code == ha.ATTENTION_BAD_ALLOCATION


def test_unknown_deferral_policy_is_refused():
    with pytest.raises(SailangError) as exc:
        make_candidate(deferral="MUST_READ")
    assert exc.value.code == ha.ATTENTION_BAD_DEFERRAL


def test_unknown_source_kind_is_refused():
    with pytest.raises(SailangError) as exc:
        make_candidate(kind="BREAKTHROUGH")
    assert exc.value.code == ha.ATTENTION_BAD_SOURCE_KIND


def test_unbounded_external_reference_is_refused():
    with pytest.raises(SailangError) as exc:
        make_candidate(kind=ha.EXTERNAL_REFERENCE, source_ref="x" * 129)
    assert exc.value.code == ha.ATTENTION_BAD_SOURCE_REF


def test_bad_human_id_is_refused():
    with pytest.raises(SailangError) as exc:
        make_candidate(to_human="human-id:sha256:" + "zz" * 32)
    assert exc.value.code == ha.ATTENTION_BAD_HUMAN_ID


def test_candidate_field_set_is_exactly_receiver_owned():
    fields = {field.name for field in ha.AttentionCandidate.__dataclass_fields__.values()}
    assert fields == {"to_human", "source_kind", "source_ref", "allocation",
                      "deferral_policy", "enqueued_at"}


def test_candidate_constructor_rejects_unknown_arguments():
    with pytest.raises(TypeError):
        ha.AttentionCandidate(to_human=HUMAN, source_kind=ha.HUMAN_PRIVATE,
                              source_ref=ref("a"), allocation="DECISION_REQUEST",
                              deferral_policy="QUEUE_AND_CONTINUE", enqueued_at=NOW,
                              IMPORTANT=True)


def test_candidate_id_is_stable_across_enqueue_times():
    first = make_candidate(enqueued_at="2026-09-19T09:00:00Z")
    second = make_candidate(enqueued_at="2026-09-19T09:30:00Z")
    assert first.candidate_id == second.candidate_id
    assert first.candidate_id == ha.attention_candidate_id(
        first.to_human, first.source_kind, first.source_ref)


def test_candidate_id_changes_with_source():
    assert make_candidate("a").candidate_id != make_candidate("b").candidate_id


def test_admission_does_not_accept_caller_human_identity(tmp_path):
    q = queue(tmp_path)
    with pytest.raises(TypeError):
        q.admit_receiver_candidate(
            to_human="human-id:sha256:" + "1b" * 32,
            source_kind=ha.HUMAN_PRIVATE,
            source_ref=ref("stranger"),
            allocation="DECISION_REQUEST",
            deferral_policy="QUEUE_AND_CONTINUE",
        )


def test_same_candidate_same_policy_is_idempotent(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    first = admit(q, candidate)
    second = admit(q, candidate)
    assert first.status == ha.ADMITTED
    assert second.status == ha.IDEMPOTENT
    files = list((attention_root(tmp_path) / "candidates").glob("*.json"))
    assert len(files) == 1


def test_re_admission_with_later_enqueue_keeps_the_first_instant(tmp_path):
    q = queue(tmp_path)
    first = make_candidate()
    later = make_candidate()
    q.clock.set("2026-09-19T09:00:00Z")
    admit(q, first)
    q.clock.set("2026-09-19T09:59:00Z")
    result = admit(q, later)
    assert result.status == ha.IDEMPOTENT
    assert result.candidate.enqueued_at == "2026-09-19T09:00:00Z"


def test_same_candidate_changed_allocation_conflicts(tmp_path):
    q = queue(tmp_path)
    admit(q, make_candidate(allocation="DECISION_REQUEST"))
    with pytest.raises(SailangError) as exc:
        admit(q, make_candidate(allocation="CRITICAL_RECOVERY"))
    assert exc.value.code == ha.ATTENTION_CANDIDATE_CONFLICT


def test_same_candidate_changed_deferral_conflicts(tmp_path):
    q = queue(tmp_path)
    admit(q, make_candidate(deferral="QUEUE_AND_CONTINUE"))
    with pytest.raises(SailangError) as exc:
        admit(q, make_candidate(deferral="ESCALATE_AND_HALT"))
    assert exc.value.code == ha.ATTENTION_CANDIDATE_CONFLICT


def test_stored_candidate_is_canonical_json(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    data = candidate_path(tmp_path, candidate).read_bytes()
    parsed = json.loads(data.decode("utf-8"))
    assert parsed == {
        "ALLOCATION": candidate.allocation,
        "CANDIDATE_ID": candidate.candidate_id,
        "DEFERRAL_POLICY": candidate.deferral_policy,
        "ENQUEUED_AT": candidate.enqueued_at,
        "SCHEMA": 1,
        "SOURCE_KIND": candidate.source_kind,
        "SOURCE_REF": candidate.source_ref,
        "TO_HUMAN": candidate.to_human,
    }
    canonical = json.dumps(parsed, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False) + "\n"
    assert data.decode("utf-8") == canonical


# --------------------------------------------------------------------
# selection: deterministic receiver ordering
# --------------------------------------------------------------------


def test_empty_queue_is_no_message(tmp_path):
    result = queue(tmp_path).reserve_next()
    assert result.status == ha.NO_MESSAGE
    assert result.candidate is None and result.reservation is None


def test_allocation_precedence_decides(tmp_path):
    q = queue(tmp_path)
    low = make_candidate("low", allocation="IDLE_REPORT",
                         enqueued_at="2026-09-19T09:00:00Z")
    high = make_candidate("high", allocation="CRITICAL_RECOVERY",
                          enqueued_at="2026-09-19T09:59:00Z")
    admit(q, low)
    admit(q, high)
    result = q.reserve_next()
    assert result.status == ha.RESERVED
    assert result.candidate.candidate_id == high.candidate_id


def test_oldest_receiver_enqueue_wins_within_allocation(tmp_path):
    q = queue(tmp_path)
    old = make_candidate("old")
    new = make_candidate("new")
    q.clock.set("2026-09-19T08:00:00Z")
    admit(q, old)
    q.clock.set("2026-09-19T09:00:00Z")
    admit(q, new)
    q.clock.set(NOW)
    result = q.reserve_next()
    assert result.candidate.candidate_id == old.candidate_id


def test_candidate_id_breaks_exact_tie(tmp_path):
    q = queue(tmp_path)
    first = make_candidate("tie-one", enqueued_at="2026-09-19T09:00:00Z")
    second = make_candidate("tie-two", enqueued_at="2026-09-19T09:00:00Z")
    admit(q, first)
    admit(q, second)
    expected = min(first.candidate_id, second.candidate_id)
    result = q.reserve_next()
    assert result.candidate.candidate_id == expected


def test_sender_written_words_do_not_move_a_candidate(tmp_path):
    # The only sender-controlled bytes are inside the immutable source the ref
    # names; the ref itself is an inert digest and the receiver sets the class.
    q = queue(tmp_path)
    plain = make_candidate("plain", allocation="ROUTINE_AUDIT")
    loud_ref = "sha256:" + hashlib.sha256(
        b"IMPORTANT MUST_READ BREAKTHROUGH CRITICAL_RECOVERY ESCALATE_AND_HALT").hexdigest()
    loud = make_candidate("loud", allocation="IDLE_REPORT", source_ref=loud_ref)
    admit(q, loud)
    admit(q, plain)
    result = q.reserve_next()
    assert result.candidate.candidate_id == plain.candidate_id


# --------------------------------------------------------------------
# reservation lifecycle: reserve / ack / release
# --------------------------------------------------------------------


def test_reserved_candidate_is_bound_to_one_lease(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    result = q.reserve_next()
    assert result.status == ha.RESERVED
    reservation = result.reservation
    assert reservation.candidate_id == candidate.candidate_id
    assert reservation.reserved_at == NOW
    assert reservation.lease_until == AFTER_LEASE
    lease = (attention_root(tmp_path) / "leases"
             / (candidate.candidate_id.rsplit(":", 1)[1] + ".json"))
    assert lease.is_file()


def test_ack_is_idempotent_and_publishes_one_receipt(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    reservation = q.reserve_next().reservation
    first = q.ack_presented(reservation.reservation_id)
    second = q.ack_presented(reservation.reservation_id)
    assert first.status == ha.ACKED
    assert second.status == ha.ALREADY_ACKED
    assert first.receipt == second.receipt
    assert first.receipt.candidate_id == candidate.candidate_id
    assert first.receipt.reservation_id == reservation.reservation_id
    assert first.receipt.presented_at == NOW
    receipts = list((attention_root(tmp_path) / "presented").glob("*.json"))
    assert len(receipts) == 1
    assert not list((attention_root(tmp_path) / "leases").glob("*.json"))


def test_wrong_reservation_token_is_refused(tmp_path):
    q = queue(tmp_path)
    admit(q, make_candidate())
    q.reserve_next()
    with pytest.raises(SailangError) as exc:
        q.ack_presented("not-a-reservation")
    assert exc.value.code == ha.ATTENTION_BAD_RESERVATION
    with pytest.raises(SailangError) as exc:
        q.ack_presented("f" * 32)
    assert exc.value.code == ha.ATTENTION_UNKNOWN_RESERVATION


def test_expired_reservation_cannot_be_acked(tmp_path):
    q = queue(tmp_path, lease_seconds=30)
    admit(q, make_candidate())
    reservation = q.reserve_next().reservation
    q.clock.set("2026-09-19T10:00:30Z")
    with pytest.raises(SailangError) as exc:
        q.ack_presented(reservation.reservation_id)
    assert exc.value.code == ha.ATTENTION_RESERVATION_EXPIRED


def test_release_restores_capacity_and_keeps_candidate_queued(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    reservation = q.reserve_next().reservation
    released = q.release(reservation.reservation_id)
    assert released.status == ha.RELEASED
    state = q.budget_state()
    assert state.active_reservations == 0
    assert state.pending_candidates == 1
    again = q.reserve_next()
    assert again.status == ha.RESERVED
    assert again.candidate.candidate_id == candidate.candidate_id


def test_wrong_reservation_cannot_release_another(tmp_path):
    q = queue(tmp_path, budget=ha.AttentionBudget(max_presentations=3))
    first = make_candidate("first", enqueued_at="2026-09-19T09:00:00Z")
    second = make_candidate("second", enqueued_at="2026-09-19T09:01:00Z")
    admit(q, first)
    admit(q, second)
    one = q.reserve_next().reservation
    two = q.reserve_next().reservation
    assert {one.candidate_id, two.candidate_id} == {first.candidate_id, second.candidate_id}
    q.release(one.reservation_id)
    state = q.budget_state()
    assert state.active_reservations == 1
    assert q.release(two.reservation_id).status == ha.RELEASED
    with pytest.raises(SailangError) as exc:
        q.release(one.reservation_id)
    assert exc.value.code == ha.ATTENTION_UNKNOWN_RESERVATION


# --------------------------------------------------------------------
# concurrency: the final slot is one slot
# --------------------------------------------------------------------


def test_concurrent_reserve_with_one_slot_reserves_once(tmp_path):
    q = queue(tmp_path)
    first = make_candidate("first")
    second = make_candidate("second")
    admit(q, first)
    admit(q, second)
    barrier = threading.Barrier(2)
    results = []

    def reserve(worker_queue):
        barrier.wait()
        results.append(worker_queue.reserve_next())

    workers = [threading.Thread(target=reserve, args=(queue(tmp_path),))
               for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    reserved = [item for item in results if item.status == ha.RESERVED]
    deferred = [item for item in results if item.status == ha.DEFERRED]
    assert len(reserved) == 1
    assert len(deferred) == 1
    assert q.budget_state().active_reservations == 1


def test_process_concurrency_with_one_slot_reserves_once(tmp_path):
    q = queue(tmp_path)
    admit(q, make_candidate("first"))
    admit(q, make_candidate("second"))
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    results = context.Queue()
    workers = [context.Process(target=_process_reserve,
                               args=(str(tmp_path), start, results))
               for _ in range(2)]
    for worker in workers:
        worker.start()
    start.set()
    statuses = sorted(results.get(timeout=10) for _ in workers)
    for worker in workers:
        worker.join(timeout=10)
        assert worker.exitcode == 0
    assert statuses == [ha.DEFERRED, ha.RESERVED]
    assert q.budget_state().active_reservations == 1


def test_concurrent_acks_publish_one_receipt(tmp_path):
    q = queue(tmp_path)
    admit(q, make_candidate())
    reservation = q.reserve_next().reservation
    barrier = threading.Barrier(2)
    results = []

    def ack(worker_queue):
        barrier.wait()
        results.append(worker_queue.ack_presented(reservation.reservation_id))

    workers = [threading.Thread(target=ack, args=(queue(tmp_path),))
               for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    statuses = sorted(item.status for item in results)
    assert statuses == [ha.ACKED, ha.ALREADY_ACKED]
    assert len(list((attention_root(tmp_path) / "presented").glob("*.json"))) == 1


# --------------------------------------------------------------------
# crash and corruption: fail closed, recover mechanically
# --------------------------------------------------------------------


def test_expired_lease_makes_candidate_reservable_again(tmp_path):
    q = queue(tmp_path, lease_seconds=30)
    first = make_candidate("first", enqueued_at="2026-09-19T09:00:00Z")
    second = make_candidate("second", enqueued_at="2026-09-19T09:10:00Z")
    admit(q, first)
    admit(q, second)
    assert q.reserve_next().candidate.candidate_id == first.candidate_id
    q.clock.set("2026-09-19T10:00:29Z")
    blocked = q.reserve_next()
    assert blocked.status == ha.DEFERRED
    assert blocked.candidate.candidate_id == second.candidate_id
    q.clock.set("2026-09-19T10:00:30Z")
    again = q.reserve_next()
    assert again.status == ha.RESERVED
    assert again.candidate.candidate_id == first.candidate_id


def test_receipt_plus_redundant_lease_is_treated_as_presented(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    reservation = q.reserve_next().reservation
    q.ack_presented(reservation.reservation_id)
    # Simulate a crash after the receipt published and before lease cleanup.
    lease = write_lease(tmp_path, reservation)
    assert lease.is_file()
    fresh = queue(tmp_path)
    result = fresh.reserve_next()
    assert result.status == ha.NO_MESSAGE
    assert not lease.is_file()
    receipts = list((attention_root(tmp_path) / "presented").glob("*.json"))
    assert len(receipts) == 1


def test_presented_candidate_is_never_reserved_twice(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    reservation = q.reserve_next().reservation
    q.ack_presented(reservation.reservation_id)
    result = queue(tmp_path).reserve_next()
    assert result.status == ha.NO_MESSAGE


def test_corrupt_presented_receipt_fails_closed(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    reservation = q.reserve_next().reservation
    q.ack_presented(reservation.reservation_id)
    receipt = (attention_root(tmp_path) / "presented"
               / (candidate.candidate_id.rsplit(":", 1)[1] + ".json"))
    receipt.write_bytes(b"{not json")
    with pytest.raises(SailangError) as exc:
        queue(tmp_path).reserve_next()
    assert exc.value.code == ha.ATTENTION_PRESENTED_CORRUPT


def test_corrupt_lease_fails_closed(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    lease = (attention_root(tmp_path) / "leases"
             / (candidate.candidate_id.rsplit(":", 1)[1] + ".json"))
    lease.parent.mkdir(parents=True, exist_ok=True)
    lease.write_bytes(b"{not json")
    with pytest.raises(SailangError) as exc:
        q.reserve_next()
    assert exc.value.code == ha.ATTENTION_LEASE_CORRUPT


def test_corrupt_candidate_fails_closed(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    candidate_path(tmp_path, candidate).write_bytes(b"{broken")
    with pytest.raises(SailangError) as exc:
        q.reserve_next()
    assert exc.value.code == ha.ATTENTION_CANDIDATE_CORRUPT


def test_candidate_with_unknown_field_fails_closed(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    record = json.loads(candidate_path(tmp_path, candidate).read_text("utf-8"))
    record["IMPORTANT"] = True
    candidate_path(tmp_path, candidate).write_bytes(
        (json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    with pytest.raises(SailangError) as exc:
        q.budget_state()
    assert exc.value.code == ha.ATTENTION_CANDIDATE_CORRUPT


def test_candidate_with_duplicate_field_fails_closed(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    text = candidate_path(tmp_path, candidate).read_text("utf-8")
    duplicated = text[:-2] + ',"ALLOCATION":"DECISION_REQUEST"}\n'
    candidate_path(tmp_path, candidate).write_bytes(duplicated.encode("utf-8"))
    with pytest.raises(SailangError) as exc:
        q.reserve_next()
    assert exc.value.code == ha.ATTENTION_CANDIDATE_CORRUPT


def test_noncanonical_candidate_fails_closed(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    record = json.loads(candidate_path(tmp_path, candidate).read_text("utf-8"))
    candidate_path(tmp_path, candidate).write_bytes(
        (json.dumps(record, indent=2) + "\n").encode("utf-8"))
    with pytest.raises(SailangError) as exc:
        q.reserve_next()
    assert exc.value.code == ha.ATTENTION_CANDIDATE_CORRUPT


def test_candidate_id_disagreeing_with_path_fails_closed(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate()
    admit(q, candidate)
    path = candidate_path(tmp_path, candidate)
    record = json.loads(path.read_text("utf-8"))
    record["CANDIDATE_ID"] = "sha256:" + "0" * 64
    path.write_bytes((json.dumps(record, sort_keys=True, separators=(",", ":"))
                      + "\n").encode("utf-8"))
    with pytest.raises(SailangError) as exc:
        q.reserve_next()
    assert exc.value.code == ha.ATTENTION_CANDIDATE_CORRUPT


# --------------------------------------------------------------------
# privacy and authority tripwires
# --------------------------------------------------------------------


def test_attention_store_never_carries_private_prose(tmp_path):
    secret_subject = "sekrit-subject-marker"
    secret_body = "sekrit-body-marker"
    marker = hashlib.sha256((secret_subject + secret_body).encode("utf-8")).hexdigest()
    q = queue(tmp_path)
    candidate = make_candidate("private", source_ref="sha256:" + marker)
    admit(q, candidate)
    q.reserve_next()
    for path in attention_root(tmp_path).rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        assert secret_subject.encode() not in data
        assert secret_body.encode() not in data
        assert b"SUBJECT" not in data
        assert b"BODY" not in data


def test_scheduler_never_opens_private_stores(tmp_path):
    # A store-shaped tree beside the attention root is not scanned or opened.
    private = tmp_path / "human-private" / DIGEST
    private.mkdir(parents=True)
    (private / "deadbeef.henv1").write_bytes(b"sealed-bytes")
    q = queue(tmp_path)
    admit(q, make_candidate())
    result = q.reserve_next()
    assert result.status == ha.RESERVED
    assert (private / "deadbeef.henv1").read_bytes() == b"sealed-bytes"


def test_presentation_receipt_is_exactly_receiver_evidence():
    fields = {field.name for field in ha.PresentedReceipt.__dataclass_fields__.values()}
    assert fields == {"candidate_id", "reservation_id", "presented_at"}


_SOURCE = Path(ha.__file__).read_text(encoding="utf-8").lower()


def test_module_never_reaches_for_private_key_paths():
    for token in ("sailetter", "hardware_piv", "humanprivatestore",
                  "open_human_private", "provider", "exchange"):
        assert token not in _SOURCE, f"attention module names {token!r}"


def test_module_has_no_pin_hardware_or_network_paths():
    for token in ("pin", "piv", "ecdh", "touch", "yubikey", "hardware",
                  "subprocess", "socket", "urlopen"):
        assert not re.search(rf"\b{token}\b", _SOURCE), f"attention module names {token!r}"


def test_module_never_consults_a_model_or_a_score():
    for token in ("model", "llm", "score", "ranking"):
        assert not re.search(rf"\b{token}\b", _SOURCE), f"attention module names {token!r}"


def test_module_has_no_sender_importance_vocabulary():
    for token in ("important", "urgent", "must_read", "breakthrough", "priority"):
        assert not re.search(rf"\b{token}\b", _SOURCE), f"attention module names {token!r}"


def test_module_never_mutates_saipen_state():
    for token in ("saipen", "board", "ticket", "log.md", "state.md"):
        assert not re.search(rf"\b{token}\b", _SOURCE), f"attention module names {token!r}"
