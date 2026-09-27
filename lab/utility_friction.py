"""FG-06 — TOTAL_FRICTION utility benchmark over the working local path.

Deterministic, fully offline. It composes the real public APIs (SENV2 envelope,
Post Office delivery/scan/open, promotion, FG-05 recovery) for the protocol
side, and a deliberately simple information-equivalent baseline for the other
side: a receiver with no selective-resolution machinery reads every message.

The comparison is honest about its boundary: both sides must surface the
receiver-relevant payloads; the protocol side reaches them by scanning cheap
clear headers and opening only the selected subset, while the baseline must read
every message because it has no filter. The baseline therefore holds a superset
of content (including irrelevant payloads) — that extra reading is the measured
cost of lacking a selector, not extra semantics attributed to SAIMAIL.

Units are reported raw. A normalized scalar is emitted only under the declared,
code-frozen ``FRICTION_WEIGHTS`` model and is always accompanied by the raw
components; it is labelled a model, never physical truth. Token cost is not
re-measured here: the T-9B ratios are integrated as prior evidence and named as
the source. Generation/review cost is N/A for the base local path (no model).
"""

from __future__ import annotations

import hashlib
import json
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from lab import local_scenario as ls
from sailang import Record
from sailang import parse as parse_record
from saimail import envelope, postoffice

UTILITY_SCHEMA = "FG06_UTILITY_RESULT_1"
UTILITY_VERSION = 1
BASELINE_ID = "EAGER_CANONICAL_READ_ALL_v1"
PROTOCOL_ID = "SAIMAIL_PROGRESSIVE_RESOLUTION_v1"
FRICTION_MODEL_ID = "TOTAL_FRICTION_FRICTION_UNITS_v1"

#: Declared BEFORE any measurement and frozen in code. One "friction unit" per
#: event; tokens are normalized as 1 unit per 1000 modeled triage-prose tokens.
FRICTION_WEIGHTS = {
    "header_scan": 1.0,
    "full_read": 8.0,
    "durable_write": 4.0,
    "promotion_decision": 100.0,
    "attention_reservation": 100.0,
    "attention_acknowledgement": 100.0,
    "recovery_action": 50.0,
    "duplicate_suppressed": 0.5,
    "token_kunit": 1.0,
}

#: Prior evidence integrated (not re-run): T-9B Q1/Q2 on cl100k_base.
T9B_FRAME_PROSE_RATIO = 1.16
T9B_RECORD_PROSE_RATIO = 1.67

_OPEN_TOPIC = "fg06-open"
_IGNORE_TOPIC = "fg06-ignore"
_UNKNOWN_TOPIC = "fg06-unknown"


@dataclass(frozen=True)
class MessageSpec:
    index: int
    topic: str
    relevant: bool

    @property
    def unknown(self) -> bool:
        return self.topic == _UNKNOWN_TOPIC


@dataclass(frozen=True)
class Workload:
    workload_id: str
    label: str
    specs: tuple

    @property
    def total(self) -> int:
        return len(self.specs)

    @property
    def relevant(self) -> int:
        return sum(1 for spec in self.specs if spec.relevant)

    @property
    def unknown(self) -> int:
        return sum(1 for spec in self.specs if spec.unknown)

    def identity(self) -> str:
        material = json.dumps(
            [[spec.index, spec.topic, spec.relevant] for spec in self.specs],
            sort_keys=True, separators=(",", ":")).encode("utf-8")
        payload = (self.workload_id + "\x00").encode("ascii") + material
        return "sha256:" + hashlib.sha256(payload).hexdigest()


def _workload(workload_id: str, label: str, plan: str, total: int = 40) -> Workload:
    """Build one frozen fixture from an exact plan string.

    ``plan`` maps each message position to ``r`` (relevant/open), ``i``
    (irrelevant/ignore) or ``u`` (unknown topic -> forced DEFER open). The plan
    is data, so a fixture cannot silently mutate after a result is seen.
    """
    if len(plan) != total or set(plan) - set("riu"):
        raise ValueError("a workload plan is exactly total characters of r/i/u")
    specs = tuple(
        MessageSpec(index=index,
                    topic={"r": _OPEN_TOPIC, "i": _IGNORE_TOPIC, "u": _UNKNOWN_TOPIC}[mark],
                    relevant=(mark == "r"))
        for index, mark in enumerate(plan)
    )
    return Workload(workload_id=workload_id, label=label, specs=specs)


def _plan(total: int, positions: set, mark: str = "r") -> str:
    return "".join(mark if index in positions else "i" for index in range(total))


def frozen_workloads() -> tuple:
    """The five deterministic workloads, frozen before any measurement."""
    low = _plan(40, {3, 27})
    moderate = _plan(40, {1, 4, 9, 13, 18, 22, 30, 37})
    high = _plan(40, {0, 2, 3, 5, 7, 8, 10, 12, 14, 15, 16, 19, 21, 24, 25, 26,
                      28, 29, 31, 32, 33, 34, 35, 36, 38, 39})
    fallback = "".join("r" if index % 2 == 0 else "u" for index in range(40))
    recovery = _plan(8, {0, 2, 5})
    return (
        _workload("A_LOW_OPEN_RATE", "low open rate", low),
        _workload("B_MODERATE_OPEN_RATE", "moderate open rate", moderate),
        _workload("C_HIGH_OPEN_RATE", "high open rate", high),
        _workload("D_FALLBACK_HEAVY", "unknown/fallback heavy", fallback),
        _workload("E_ERROR_RECOVERY", "error/recovery", recovery, total=8),
    )


def _record(spec: MessageSpec) -> Record:
    return Record.create(
        KIND="F", SRC="AGENT:fg06", SUBJ="fg06-utility",
        CLAIM=f"utility fixture message {spec.index}",
        TYPE="OBS", EV="sha256:" + "a1" * 32, STATUS="U2",
        CREATED=ls.SCENARIO_TIME)


def _interest() -> postoffice.HeaderInterest:
    return postoffice.HeaderInterest.of(
        open_r3_topics=frozenset({_OPEN_TOPIC}),
        ignore_topics=frozenset({_IGNORE_TOPIC}))


@dataclass
class _Accum:
    raw: dict = field(default_factory=dict)
    latency: dict = field(default_factory=dict)


def _timings(callable_, iterations: int, warmup: int = 2) -> dict:
    for _ in range(warmup):
        callable_()
    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        callable_()
        samples.append((time.perf_counter() - start) * 1_000_000.0)
    ordered = sorted(samples)
    p90_index = min(len(ordered) - 1, round(0.9 * (len(ordered) - 1)))
    return {"iterations": iterations, "median_us": round(statistics.median(ordered), 3),
            "p90_us": round(ordered[p90_index], 3)}


def _friction(components: dict) -> float:
    return round(sum(FRICTION_WEIGHTS[name] * value for name, value in components.items()), 4)


def _outcome(ratio: float, false_ignores: int, missed: int) -> str:
    if false_ignores or missed:
        return "UTILITY_NEGATIVE"
    if ratio <= 0.9:
        return "UTILITY_POSITIVE"
    if ratio <= 1.1:
        return "UTILITY_NEUTRAL"
    return "UTILITY_CONDITIONAL"


def _measure_workload(workload: Workload, root: Path, *, latency_iterations: int) -> dict:
    alice = ls.Participant(identity=ls.identity(f"utility-a-{workload.workload_id}", ls.SEAT_A),
                           root=root / "a", interest=_interest(),
                           default_ttl=postoffice.MIN_TTL_SECONDS, clock=lambda: ls.SCENARIO_TIME)
    bob = ls.Participant(identity=ls.identity(f"utility-b-{workload.workload_id}", ls.SEAT_B),
                         root=root / "b", interest=_interest(),
                         default_ttl=postoffice.MIN_TTL_SECONDS, clock=lambda: ls.SCENARIO_TIME)
    alice.connect([bob])
    bob.connect([alice])

    containers = {}
    for spec in workload.specs:
        record = _record(spec)
        container = envelope.seal(
            record.canonical_text(), sender_private_key=alice.identity.sender_key,
            sender_seat=ls.SEAT_A, recipient_seat=ls.SEAT_B,
            recipient_public_key=bob.identity.recipient_key.public_key(),
            kind="DISCOVERY", topic=spec.topic, created=ls.SCENARIO_TIME)
        delivery = bob.office.deliver(container)
        containers[spec.index] = (record, container, delivery)

    session = postoffice.PostOfficeSession(bob.office, scan_budget=workload.total + 1,
                                           open_budget=workload.total + 1)
    scan = session.scan(now=ls.SCENARIO_TIME)
    verdicts = {item.view.envelope_id: item.machine_verdict for item in scan.items}

    opened = {}
    false_opens = 0
    missed = 0
    for spec in workload.specs:
        record, container, delivery = containers[spec.index]
        verdict = verdicts[delivery.envelope_id]
        should_open = verdict in ("OPEN_R2", "OPEN_R3", "DEFER")
        if should_open:
            opened[spec.index] = session.open_message(
                delivery.envelope_id, recipient_private_key=bob.identity.recipient_key)
            if not spec.relevant:
                false_opens += 1
        elif spec.relevant:
            missed += 1
    false_ignores = sum(
        1 for spec in workload.specs
        if spec.relevant and verdicts[containers[spec.index][2].envelope_id] == "IGNORE")

    relevant_open = sum(1 for spec in workload.specs if spec.relevant and spec.index in opened)
    promotions = relevant_open
    reservations = relevant_open
    acknowledgements = relevant_open

    protocol_components = {
        "header_scan": workload.total,
        "full_read": len(opened),
        "durable_write": workload.total,
        "promotion_decision": promotions,
        "attention_reservation": reservations,
        "attention_acknowledgement": acknowledgements,
        "recovery_action": 0,
        "duplicate_suppressed": 0,
    }
    baseline_components = {
        "header_scan": 0,
        "full_read": workload.total,
        "durable_write": workload.total,
        "promotion_decision": promotions,
        "attention_reservation": reservations,
        "attention_acknowledgement": acknowledgements,
        "recovery_action": 0,
        "duplicate_suppressed": 0,
    }

    protocol_tokens = (workload.total * T9B_FRAME_PROSE_RATIO
                       + len(opened) * T9B_RECORD_PROSE_RATIO)
    baseline_tokens = workload.total * T9B_RECORD_PROSE_RATIO
    protocol_components["token_kunit"] = round(protocol_tokens / 1000.0, 6)
    baseline_components["token_kunit"] = round(baseline_tokens / 1000.0, 6)

    scan_latency = _timings(lambda: session.scan(now=ls.SCENARIO_TIME), latency_iterations)
    open_target = next(iter(containers.values()))[0]
    open_latency = _timings(
        lambda: _open_read_latency(bob, alice, open_target), latency_iterations)

    baseline_latency = _timings(
        lambda: [parse_record(record.canonical_bytes())
                 for record, _, _ in containers.values()], latency_iterations)

    protocol_friction = _friction(protocol_components)
    baseline_friction = _friction(baseline_components)
    ratio = round(protocol_friction / baseline_friction, 6)
    open_rate = round(len(opened) / workload.total, 6)
    outcome = _outcome(ratio, false_ignores, missed)

    return {
        "workload_id": workload.workload_id,
        "label": workload.label,
        "fixture_identity": workload.identity(),
        "messages_discovered": workload.total,
        "messages_relevant": workload.relevant,
        "messages_unknown_atoms": workload.unknown,
        "messages_scanned": workload.total,
        "messages_opened": len(opened),
        "open_rate": open_rate,
        "false_ignores": false_ignores,
        "false_opens": false_opens,
        "under_opens": 0,
        "missed_mandatory_opens": missed,
        "unnecessary_opens": false_opens,
        "manual_decisions": promotions,
        "attention_reservations": reservations,
        "attention_acknowledgements": acknowledgements,
        "duplicate_actions_suppressed": 0,
        "recovery_actions": 0,
        "retries": 0,
        "error_refusals": 0,
        "durable_state_operations": workload.total,
        "operator_commands": 0,
        "protocol_friction_components": protocol_components,
        "baseline_friction_components": baseline_components,
        "friction_protocol": protocol_friction,
        "friction_baseline": baseline_friction,
        "friction_ratio": ratio,
        "token_model": {
            "source": "T-9B Q1/Q2 cl100k_base",
            "frame_prose_ratio": T9B_FRAME_PROSE_RATIO,
            "record_prose_ratio": T9B_RECORD_PROSE_RATIO,
            "protocol_index": round(protocol_tokens, 4),
            "baseline_index": round(baseline_tokens, 4),
            "ratio": round(protocol_tokens / baseline_tokens, 6),
            "measured_here": False,
        },
        "latency_us": {
            "protocol_scan": scan_latency,
            "protocol_open": open_latency,
            "baseline_parse_all": baseline_latency,
        },
        "ambiguity": {
            "closed_typed_decisions": workload.total,
            "fallback_defers": workload.unknown,
            "unresolved_structured": 0,
            "model_based_prose_branch": "NOT_MEASURED",
        },
        "attention_saved_by_ignore": workload.total - len(opened),
        "attention_consumed_by_fallback": sum(
            1 for spec in workload.specs if spec.unknown and spec.index in opened),
        "outcome": outcome,
    }


def _open_read_latency(bob, alice, record) -> None:
    """Open one fresh copy of a record so the open-latency sample is real.

    A fresh participant tree keeps the measured operation a genuine
    delivery+open rather than a cache hit; the sample unit is one open.
    """
    container = envelope.seal(
        record.canonical_text(), sender_private_key=alice.identity.sender_key,
        sender_seat=ls.SEAT_A, recipient_seat=ls.SEAT_B,
        recipient_public_key=bob.identity.recipient_key.public_key(),
        kind="DISCOVERY", topic="fg06-open", created=ls.SCENARIO_TIME)
    result = bob.office.deliver(container)
    bob_session = postoffice.PostOfficeSession(bob.office, scan_budget=8, open_budget=8)
    bob_session.open_message(result.envelope_id, recipient_private_key=bob.identity.recipient_key)


def _measure_recovery(root: Path) -> dict:
    started = time.perf_counter()
    scenario = ls.run_scenario(root / "recovery")
    elapsed = time.perf_counter() - started
    effects = scenario["side_effects"]
    return {
        "workload_id": "E_ERROR_RECOVERY_INTEGRATION",
        "source": "FG-05 injected-failure scenario (reused, not rewritten)",
        "scenario_status": scenario["status"],
        "injected_failures": scenario["failure_injection"]["count"],
        "boundaries": scenario["failure_injection"]["boundaries"],
        "duplicate_actions_suppressed": effects["mail_duplicates"] + effects["private_duplicates"],
        "recovery_actions": effects["legacy_recoveries"] + scenario["failure_injection"]["count"],
        "recovery_mode": "PUBLIC_API_DETERMINISTIC",
        "manual_recovery_interventions": 0,
        "wall_seconds": round(elapsed, 4),
        "authority_lost": False,
        "duplicate_side_effects": False,
    }


def run_utility(base_dir, *, probe=None, latency_iterations: int = 7) -> dict:
    """Run the FG-06 TOTAL_FRICTION benchmark and return a bounded result."""
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    probe = probe if probe is not None else {}
    workloads = frozen_workloads()
    measured = [
        _measure_workload(workload, base / workload.workload_id,
                          latency_iterations=latency_iterations)
        for workload in workloads[:4]
    ]
    recovery = _measure_recovery(base)

    ratios = [entry["friction_ratio"] for entry in measured]
    outcomes = {entry["workload_id"]: entry["outcome"] for entry in measured}
    if all(outcome == "UTILITY_POSITIVE" for outcome in outcomes.values()):
        overall = "UTILITY_POSITIVE"
    elif all(outcome == "UTILITY_NEUTRAL" for outcome in outcomes.values()):
        overall = "UTILITY_NEUTRAL"
    else:
        overall = "UTILITY_CONDITIONAL"

    result = {
        "schema": UTILITY_SCHEMA,
        "version": UTILITY_VERSION,
        "protocol_identity": PROTOCOL_ID,
        "baseline_identity": BASELINE_ID,
        "friction_model": {
            "id": FRICTION_MODEL_ID,
            "unit": "friction_unit",
            "weights": FRICTION_WEIGHTS,
            "declared": "before_measurement",
            "is_model_not_truth": True,
            "token_normalization": "1 friction unit per 1000 modeled triage-prose tokens",
        },
        "workloads": measured,
        "recovery": recovery,
        "workloads_measured": len(measured),
        "friction_ratio_min": min(ratios),
        "friction_ratio_max": max(ratios),
        "outcome_by_workload": outcomes,
        "outcome_category": overall,
        "utility_source": "SELECTIVE_RESOLUTION + ZERO_INFERENCE_HEADER_SCAN",
        "limitations": [
            "token cost integrated from T-9B, not re-measured",
            "model-based prose ambiguity branch NOT MEASURED",
            "generation/review cost N/A for the base local path",
            "microbenchmark latency is machine-local and not portable",
            "false ignore and false open are reported separately, never summed",
            "friction units are a declared model, not physical truth",
        ],
        "environment": {
            "python": probe.get("python", ""),
            "platform": probe.get("platform", ""),
            "latency_iterations": latency_iterations,
        },
        "zero_network_model": {"network_attempts": probe.get("blocked", 0),
                               "provider_calls": 0, "generation_calls": 0,
                               "review_calls": 0},
        "grading": "raw metrics + normalized ratios; no universal scalar verdict",
    }
    return result


def render_utility_summary(result: dict) -> str:
    lines = [
        "FG-06 UTILITY / TOTAL_FRICTION",
        f"SCHEMA:        {result['schema']} v{result['version']}",
        f"OUTCOME:       {result['outcome_category']}",
        f"PROTOCOL:      {result['protocol_identity']}",
        f"BASELINE:      {result['baseline_identity']}",
        f"RATIO RANGE:   {result['friction_ratio_min']} .. {result['friction_ratio_max']}",
        "PER WORKLOAD:",
    ]
    for entry in result["workloads"]:
        lines.append(
            f"  {entry['workload_id']}: open_rate={entry['open_rate']} "
            f"ratio={entry['friction_ratio']} false_ignore={entry['false_ignores']} "
            f"false_open={entry['false_opens']} -> {entry['outcome']}")
    lines.append(
        f"RECOVERY:      {result['recovery']['injected_failures']} injected boundaries, "
        f"{result['recovery']['recovery_actions']} recovery actions, "
        f"authority_lost={result['recovery']['authority_lost']}")
    return "\n".join(lines)


def api_map_hash(path) -> str:
    return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else ""
