"""B-011 budget contract: rolling receiver window, deferral outcomes, zero is success.

Consumption is measured from receiver-owned presented receipts and provisional
reservations. A period boundary is deterministic; an empty result is a normal
success, never a quota to fill.
"""

import hashlib

import pytest

from sailang.errors import SailangError

from saimail import human_attention as ha

HUMAN = "human-id:sha256:" + "4c" * 32
NOW = "2026-09-19T10:00:00Z"
BOUNDARY = "2026-09-19T10:01:40Z"


class MutableReceiverClock:
    def __init__(self, value):
        self.value = value

    def __call__(self):
        return self.value

    def set(self, value):
        self.value = value


def make_candidate(tag, *, allocation="DECISION_REQUEST", deferral="QUEUE_AND_CONTINUE",
                   enqueued_at=NOW):
    digest = hashlib.sha256(tag.encode("utf-8")).hexdigest()
    return ha.AttentionCandidate(
        to_human=HUMAN,
        source_kind=ha.HUMAN_PRIVATE,
        source_ref="sha256:" + digest,
        allocation=allocation,
        deferral_policy=deferral,
        enqueued_at=enqueued_at,
    )


def queue(tmp_path, **kwargs):
    kwargs.setdefault("clock", MutableReceiverClock(NOW))
    return ha.AttentionQueue(tmp_path, human_id=HUMAN, **kwargs)


def admit(q, candidate):
    return q.admit_receiver_candidate(
        source_kind=candidate.source_kind,
        source_ref=candidate.source_ref,
        allocation=candidate.allocation,
        deferral_policy=candidate.deferral_policy,
    )


# --------------------------------------------------------------------
# budget: defaults, rolling window, durability across restarts
# --------------------------------------------------------------------


def test_zero_presentations_is_a_valid_configuration():
    budget = ha.AttentionBudget(max_presentations=0)
    assert budget.max_presentations == 0
    assert budget.period_seconds == ha.DEFAULT_PERIOD_SECONDS


def test_negative_max_presentations_is_refused():
    with pytest.raises(SailangError) as exc:
        ha.AttentionBudget(max_presentations=-1)
    assert exc.value.code == ha.ATTENTION_BAD_BUDGET


def test_non_positive_period_is_refused():
    with pytest.raises(SailangError) as exc:
        ha.AttentionBudget(period_seconds=0)
    assert exc.value.code == ha.ATTENTION_BAD_BUDGET
    with pytest.raises(SailangError) as exc:
        ha.AttentionBudget(period_seconds=-5)
    assert exc.value.code == ha.ATTENTION_BAD_BUDGET


def test_non_positive_lease_seconds_is_refused(tmp_path):
    with pytest.raises(SailangError) as exc:
        queue(tmp_path, lease_seconds=0)
    assert exc.value.code == ha.ATTENTION_BAD_LEASE_SECONDS


def test_default_budget_allows_exactly_one_presentation(tmp_path):
    q = queue(tmp_path)
    admit(q, make_candidate("one"))
    result = q.reserve_next()
    assert result.status == ha.RESERVED
    state = q.budget_state()
    assert state.max_presentations == 1
    assert state.period_seconds == ha.DEFAULT_PERIOD_SECONDS
    assert state.consumed == 1
    assert state.available == 0


def test_second_candidate_in_the_window_is_deferred(tmp_path):
    q = queue(tmp_path)
    high = make_candidate("high", allocation="DECISION_REQUEST",
                          enqueued_at="2026-09-19T09:00:00Z")
    low = make_candidate("low", allocation="ROUTINE_AUDIT",
                         enqueued_at="2026-09-19T09:30:00Z")
    admit(q, high)
    admit(q, low)
    presentation = q.reserve_next()
    assert presentation.candidate.candidate_id == high.candidate_id
    q.ack_presented(presentation.reservation.reservation_id)
    blocked = q.reserve_next()
    assert blocked.status == ha.DEFERRED
    assert blocked.candidate.candidate_id == low.candidate_id
    assert blocked.reservation is None


def test_receipt_exactly_one_period_old_stops_consuming(tmp_path):
    q = queue(tmp_path, budget=ha.AttentionBudget(period_seconds=100))
    first = make_candidate("first")
    second = make_candidate("second")
    admit(q, first)
    admit(q, second)
    reservation = q.reserve_next().reservation
    q.ack_presented(reservation.reservation_id)
    q.clock.set(BOUNDARY)
    state = q.budget_state()
    assert state.presented_in_window == 0
    assert state.available == 1
    again = q.reserve_next()
    assert again.status == ha.RESERVED


def test_active_reservation_consumes_provisional_capacity(tmp_path):
    q = queue(tmp_path)
    admit(q, make_candidate("one"))
    admit(q, make_candidate("two"))
    assert q.reserve_next().status == ha.RESERVED
    state = q.budget_state()
    assert state.consumed == 1
    assert state.available == 0
    second = q.reserve_next()
    assert second.status == ha.DEFERRED


def test_released_reservation_restores_capacity(tmp_path):
    q = queue(tmp_path)
    admit(q, make_candidate("one"))
    reservation = q.reserve_next().reservation
    q.release(reservation.reservation_id)
    state = q.budget_state()
    assert state.consumed == 0
    assert state.available == 1
    assert q.reserve_next().status == ha.RESERVED


def test_expired_reservation_restores_capacity(tmp_path):
    q = queue(tmp_path, lease_seconds=60)
    admit(q, make_candidate("one"))
    q.reserve_next()
    q.clock.set("2026-09-19T10:00:59Z")
    assert q.budget_state().active_reservations == 1
    assert q.reserve_next().status == ha.NO_MESSAGE
    q.clock.set("2026-09-19T10:01:00Z")
    assert q.reserve_next().status == ha.RESERVED


def test_restart_reconstructs_budget_from_disk(tmp_path):
    q = queue(tmp_path, budget=ha.AttentionBudget(period_seconds=86_400))
    first = make_candidate("first")
    second = make_candidate("second")
    q.clock.set("2026-09-19T09:00:00Z")
    admit(q, first)
    q.clock.set("2026-09-19T09:10:00Z")
    admit(q, second)
    q.clock.set(NOW)
    reservation = q.reserve_next().reservation
    q.ack_presented(reservation.reservation_id)
    fresh = queue(tmp_path)
    state = fresh.budget_state()
    assert state.presented_in_window == 1
    assert state.consumed == 1
    assert state.available == 0
    assert state.pending_candidates == 1
    deferred = fresh.reserve_next()
    assert deferred.status == ha.DEFERRED
    assert deferred.candidate.candidate_id == second.candidate_id


# --------------------------------------------------------------------
# deferral: outcomes are data for a caller, never automatic action
# --------------------------------------------------------------------


def test_queue_and_continue_maps_to_deferred(tmp_path):
    q = queue(tmp_path, budget=ha.AttentionBudget(max_presentations=0))
    admit(q, make_candidate("quiet", deferral="QUEUE_AND_CONTINUE"))
    result = q.reserve_next()
    assert result.status == ha.DEFERRED


def test_block_until_human_maps_to_attention_blocked(tmp_path):
    q = queue(tmp_path, budget=ha.AttentionBudget(max_presentations=0))
    admit(q, make_candidate("wait", deferral="BLOCK_UNTIL_HUMAN"))
    result = q.reserve_next()
    assert result.status == ha.ATTENTION_BLOCKED
    assert result.candidate is not None
    assert result.reservation is None


def test_escalate_and_halt_maps_to_halt_required(tmp_path):
    q = queue(tmp_path, budget=ha.AttentionBudget(max_presentations=0))
    admit(q, make_candidate("alarm", deferral="ESCALATE_AND_HALT"))
    result = q.reserve_next()
    assert result.status == ha.ATTENTION_HALT_REQUIRED


def test_zero_budget_with_queue_and_continue_is_deferred(tmp_path):
    q = queue(tmp_path, budget=ha.AttentionBudget(max_presentations=0))
    admit(q, make_candidate("quiet"))
    result = q.reserve_next()
    assert result.status == ha.DEFERRED


def test_deferral_result_never_mutates_or_halts(tmp_path):
    q = queue(tmp_path, budget=ha.AttentionBudget(max_presentations=0))
    admit(q, make_candidate("alarm", deferral="ESCALATE_AND_HALT"))
    result = q.reserve_next()
    assert result.status == ha.ATTENTION_HALT_REQUIRED
    assert result.candidate is not None
    state = q.budget_state()
    assert state.pending_candidates == 1
    assert state.active_reservations == 0


def test_critical_recovery_cannot_bypass_the_budget(tmp_path):
    q = queue(tmp_path)
    first = make_candidate("first", allocation="ROUTINE_AUDIT",
                           enqueued_at="2026-09-19T09:00:00Z")
    crisis = make_candidate("crisis", allocation="CRITICAL_RECOVERY",
                            deferral="ESCALATE_AND_HALT",
                            enqueued_at="2026-09-19T09:10:00Z")
    admit(q, first)
    admit(q, crisis)
    presentation = q.reserve_next()
    assert presentation.candidate.candidate_id == crisis.candidate_id
    q.ack_presented(presentation.reservation.reservation_id)
    later = make_candidate("later-crisis", allocation="CRITICAL_RECOVERY",
                           deferral="ESCALATE_AND_HALT",
                           enqueued_at="2026-09-19T09:20:00Z")
    admit(q, later)
    result = q.reserve_next()
    assert result.status == ha.ATTENTION_HALT_REQUIRED
    assert result.reservation is None
    assert result.candidate.candidate_id == later.candidate_id


# --------------------------------------------------------------------
# zero is a successful outcome
# --------------------------------------------------------------------


def test_empty_queue_returns_no_message_not_a_synthesized_one(tmp_path):
    q = queue(tmp_path)
    assert q.reserve_next().status == ha.NO_MESSAGE
    assert q.budget_state().pending_candidates == 0


def test_everything_presented_returns_no_message(tmp_path):
    q = queue(tmp_path)
    candidate = make_candidate("only")
    admit(q, candidate)
    reservation = q.reserve_next().reservation
    q.ack_presented(reservation.reservation_id)
    result = queue(tmp_path).reserve_next()
    assert result.status == ha.NO_MESSAGE


def test_window_with_room_but_nothing_pending_returns_no_message(tmp_path):
    q = queue(tmp_path, budget=ha.AttentionBudget(period_seconds=100))
    candidate = make_candidate("only")
    admit(q, candidate)
    reservation = q.reserve_next().reservation
    q.ack_presented(reservation.reservation_id)
    q.clock.set(BOUNDARY)
    state = q.budget_state()
    assert state.available == 1
    assert state.pending_candidates == 0
    assert q.reserve_next().status == ha.NO_MESSAGE
