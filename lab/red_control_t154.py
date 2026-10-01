"""T-154 red control: the pre-fix product, with the operator gate removed.

A passing regression set only means something if it can go red. This plugin
replaces `saimail.operator_interrupt` with the shape the product had before
this Work: a sender may declare any class, any stability, any body length, and
every declared letter becomes its own operator interruption. The attention
queue itself is left alone, so the only thing being measured is the gate.

Run it against the real test files:

    python -m pytest tests/test_operator_interrupt.py tests/test_gui_operator_interrupt.py \
        -p lab.red_control_t154 -q

Every failure it produces is a property the gate is actually enforcing. A green
run here would mean the regression set is not load-bearing.
"""

from __future__ import annotations

from saimail import operator_interrupt as oi

_REAL_DECLARATION = oi.declaration


def _pre_fix_declaration(**fields):
    """No class set, no stability, no size contract: the sender states whatever."""
    return {
        "schema": oi.SCHEMA,
        "class": fields.get("class_name", oi.OPERATOR_ACTION_REQUIRED),
        "decision_id": fields.get("decision_id", "d"),
        "work": fields.get("work", "T-154"),
        "settled": fields.get("settled", True),
        "body": fields.get("body", ""),
    }


class _PreFixReceiver(oi.Receiver):
    """Every letter is an interruption, and every envelope is a new decision."""

    def admit(self, envelope_id, declared, *, origin=oi.ORIGIN_AGENT,
              presence=oi.PRESENCE_UNKNOWN):
        decision = oi.decision_key(self.to_human, declared.get("work", ""),
                                   declared.get("decision_id", ""))
        with self._lock():
            now = oi._check_now(self.clock())
            self._write_entry({
                "SCHEMA": 1, "DECISION": decision, "TO_HUMAN": self.to_human,
                "WORK": declared.get("work", ""), "CLASS": declared.get("class", ""),
                "ENVELOPE": envelope_id, "STATE": oi.PENDING,
                "BODY": declared.get("body", ""), "RESERVATION": "",
                "ENQUEUED_AT": now, "UPDATED_AT": now,
            })
            return self._view(oi.ADMITTED, str(envelope_id), declared, decision=decision,
                              detail="pre-fix product: the letter is the interruption")


def pytest_configure(config):
    oi.declaration = _pre_fix_declaration
    oi.Receiver = _PreFixReceiver


def pytest_unconfigure(config):
    oi.declaration = _REAL_DECLARATION
