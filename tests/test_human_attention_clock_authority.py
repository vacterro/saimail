"""Corrective B-011 proofs: receiver clock and admission own all timestamps."""

import hashlib
import inspect
import json

import pytest

from sailang.errors import SailangError

from saimail import human_attention as ha

HUMAN = "human-id:sha256:" + "8d" * 32
T0 = "2026-09-19T12:00:00Z"
T1 = "2026-09-19T12:00:10Z"


class MutableReceiverClock:
    def __init__(self, value=T0):
        self.value = value
        self.reads = 0

    def __call__(self):
        self.reads += 1
        return self.value

    def set(self, value):
        self.value = value


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode("utf-8")).hexdigest()


def queue(tmp_path, *, clock=None, **kwargs):
    return ha.AttentionQueue(
        tmp_path,
        human_id=HUMAN,
        clock=clock if clock is not None else MutableReceiverClock(),
        **kwargs,
    )


def admit(q, tag, *, allocation="DECISION_REQUEST",
          deferral_policy="QUEUE_AND_CONTINUE", source_kind=ha.HUMAN_PRIVATE,
          source_ref=None):
    return q.admit_receiver_candidate(
        source_kind=source_kind,
        source_ref=source_ref if source_ref is not None else ref(tag),
        allocation=allocation,
        deferral_policy=deferral_policy,
    )


def record_root(tmp_path):
    return tmp_path / ha.ATTENTION_DIR / HUMAN.rsplit(":", 1)[1]


def test_public_operation_signatures_have_no_time_override():
    assert list(inspect.signature(ha.AttentionQueue.reserve_next).parameters) == ["self"]
    assert list(inspect.signature(ha.AttentionQueue.ack_presented).parameters) == [
        "self", "reservation_id",
    ]
    assert list(inspect.signature(ha.AttentionQueue.budget_state).parameters) == ["self"]
    assert list(inspect.signature(ha.AttentionQueue.release).parameters) == [
        "self", "reservation_id",
    ]


def test_public_per_operation_time_arguments_are_rejected(tmp_path):
    q = queue(tmp_path)
    admit(q, "one")
    reservation = q.reserve_next().reservation
    with pytest.raises(TypeError):
        q.reserve_next(now=T0)
    with pytest.raises(TypeError):
        q.ack_presented(reservation.reservation_id, now=T0)
    with pytest.raises(TypeError):
        q.budget_state(now=T0)


def test_admission_signature_has_no_receiver_owned_arguments():
    parameters = inspect.signature(
        ha.AttentionQueue.admit_receiver_candidate).parameters
    assert "to_human" not in parameters
    assert "enqueued_at" not in parameters
    assert list(parameters) == [
        "self", "source_kind", "source_ref", "allocation", "deferral_policy",
    ]


def test_admission_rejects_a_pre_stamped_candidate(tmp_path):
    q = queue(tmp_path)
    forged = ha.AttentionCandidate(
        to_human=HUMAN,
        source_kind=ha.HUMAN_PRIVATE,
        source_ref=ref("forged"),
        allocation="DECISION_REQUEST",
        deferral_policy="QUEUE_AND_CONTINUE",
        enqueued_at="2000-01-01T00:00:00Z",
    )
    with pytest.raises(TypeError):
        q.admit_receiver_candidate(forged)


def test_admission_mints_queue_identity_and_clock(tmp_path):
    clock = MutableReceiverClock(T1)
    result = admit(queue(tmp_path, clock=clock), "minted")
    assert result.candidate.to_human == HUMAN
    assert result.candidate.enqueued_at == T1


def test_idempotent_re_admission_preserves_first_timestamp(tmp_path):
    clock = MutableReceiverClock(T0)
    q = queue(tmp_path, clock=clock)
    first = admit(q, "same")
    clock.set("2026-09-19T13:00:00Z")
    second = admit(q, "same")
    assert second.status == ha.IDEMPOTENT
    assert second.candidate == first.candidate
    assert second.candidate.enqueued_at == T0


def test_changed_receiver_policy_still_conflicts(tmp_path):
    q = queue(tmp_path)
    admit(q, "same")
    with pytest.raises(SailangError) as exc:
        admit(q, "same", allocation="CRITICAL_RECOVERY")
    assert exc.value.code == ha.ATTENTION_CANDIDATE_CONFLICT


def test_source_created_time_cannot_influence_enqueued_at(tmp_path):
    q = queue(tmp_path)
    result = admit(
        q,
        "unused",
        source_kind=ha.EXTERNAL_REFERENCE,
        source_ref="created_at:2000:01:01T00:00:00Z",
    )
    assert result.candidate.enqueued_at == T0


def test_sender_looking_external_token_cannot_inject_time(tmp_path):
    q = queue(tmp_path)
    result = admit(
        q,
        "unused",
        source_kind=ha.EXTERNAL_REFERENCE,
        source_ref="ENQUEUED_AT:1900-01-01T00:00:00Z",
    )
    assert result.candidate.enqueued_at == T0


def test_same_allocation_order_follows_actual_admission_time(tmp_path):
    clock = MutableReceiverClock(T0)
    q = queue(tmp_path, clock=clock)
    first = admit(q, "first").candidate
    clock.set(T1)
    second = admit(q, "second").candidate
    clock.set("2026-09-19T12:00:20Z")
    selected = q.reserve_next()
    assert selected.candidate.candidate_id == first.candidate_id
    assert first.enqueued_at < second.enqueued_at


def test_candidate_identity_still_excludes_receiver_enqueue_time(tmp_path):
    clock = MutableReceiverClock(T0)
    q = queue(tmp_path, clock=clock)
    first = admit(q, "same").candidate
    clock.set(T1)
    second = admit(q, "same").candidate
    assert first.candidate_id == second.candidate_id
    assert first.candidate_id == ha.attention_candidate_id(
        HUMAN, ha.HUMAN_PRIVATE, ref("same"))


def test_backward_clock_ack_refuses_and_preserves_live_lease(tmp_path):
    clock = MutableReceiverClock(T0)
    q = queue(tmp_path, clock=clock)
    candidate = admit(q, "one").candidate
    reservation = q.reserve_next().reservation
    clock.set("2020-01-01T00:00:00Z")
    with pytest.raises(SailangError) as exc:
        q.ack_presented(reservation.reservation_id)
    assert exc.value.code == ha.ATTENTION_CLOCK_REGRESSION
    root = record_root(tmp_path)
    assert not list((root / "presented").glob("*.json"))
    lease = root / "leases" / (candidate.candidate_id.rsplit(":", 1)[1] + ".json")
    assert lease.is_file()
    clock.set(T1)
    assert q.budget_state().active_reservations == 1
    assert q.budget_state().available == 0


def test_backward_clock_cannot_mint_second_reservation(tmp_path):
    clock = MutableReceiverClock(T0)
    q = queue(tmp_path, clock=clock)
    admit(q, "first")
    admit(q, "second")
    original = q.reserve_next().reservation
    clock.set("2020-01-01T00:00:00Z")
    with pytest.raises(SailangError) as exc:
        q.reserve_next()
    assert exc.value.code == ha.ATTENTION_CLOCK_REGRESSION
    clock.set(T1)
    state = q.budget_state()
    assert state.active_reservations == 1
    leases = list((record_root(tmp_path) / "leases").glob("*.json"))
    assert len(leases) == 1
    assert json.loads(leases[0].read_text("utf-8"))["RESERVATION_ID"] == \
        original.reservation_id


def test_future_per_call_time_cannot_expire_live_lease(tmp_path):
    q = queue(tmp_path)
    admit(q, "first")
    admit(q, "second")
    original = q.reserve_next().reservation
    with pytest.raises(TypeError):
        q.reserve_next(now="2099-01-01T00:00:00Z")
    assert q.budget_state().active_reservations == 1
    lease = next((record_root(tmp_path) / "leases").glob("*.json"))
    assert json.loads(lease.read_text("utf-8"))["RESERVATION_ID"] == \
        original.reservation_id


def test_future_immutable_receipt_counts_after_clock_rollback(tmp_path):
    clock = MutableReceiverClock(T0)
    q = queue(tmp_path, clock=clock)
    admit(q, "first")
    reservation = q.reserve_next().reservation
    clock.set(T1)
    receipt = q.ack_presented(reservation.reservation_id).receipt
    assert receipt.presented_at == T1
    clock.set("2020-01-01T00:00:00Z")
    state = q.budget_state()
    assert state.presented_in_window == 1
    assert state.consumed == 1
    assert state.available == 0


def test_normal_ack_obeys_reservation_temporal_bounds(tmp_path):
    clock = MutableReceiverClock(T0)
    q = queue(tmp_path, clock=clock)
    admit(q, "one")
    reservation = q.reserve_next().reservation
    clock.set(T1)
    receipt = q.ack_presented(reservation.reservation_id).receipt
    assert reservation.reserved_at <= receipt.presented_at < reservation.lease_until


def test_known_impossible_receipt_lease_relationship_fails_closed(tmp_path):
    clock = MutableReceiverClock(T0)
    q = queue(tmp_path, clock=clock)
    candidate = admit(q, "one").candidate
    reservation = q.reserve_next().reservation
    clock.set(T1)
    q.ack_presented(reservation.reservation_id)
    lease_path = record_root(tmp_path) / "leases" / (
        candidate.candidate_id.rsplit(":", 1)[1] + ".json")
    lease_path.parent.mkdir(parents=True, exist_ok=True)
    impossible = {
        "CANDIDATE_ID": candidate.candidate_id,
        "LEASE_UNTIL": "2026-09-19T12:04:00Z",
        "RESERVED_AT": "2026-09-19T12:03:00Z",
        "RESERVATION_ID": reservation.reservation_id,
        "SCHEMA": 1,
    }
    lease_path.write_bytes(
        (json.dumps(impossible, sort_keys=True, separators=(",", ":")) + "\n")
        .encode("utf-8"))
    clock.set("2026-09-19T12:03:30Z")
    with pytest.raises(SailangError) as exc:
        q.budget_state()
    assert exc.value.code == ha.ATTENTION_PRESENTED_CORRUPT


def test_each_transition_reads_queue_clock_once(tmp_path):
    clock = MutableReceiverClock(T0)
    q = queue(tmp_path, clock=clock)
    before = clock.reads
    admit(q, "one")
    assert clock.reads == before + 1
    before = clock.reads
    reservation = q.reserve_next().reservation
    assert clock.reads == before + 1
    before = clock.reads
    q.budget_state()
    assert clock.reads == before + 1
    before = clock.reads
    q.release(reservation.reservation_id)
    assert clock.reads == before + 1
    admit(q, "two")
    second = q.reserve_next().reservation
    before = clock.reads
    q.ack_presented(second.reservation_id)
    assert clock.reads == before + 1
