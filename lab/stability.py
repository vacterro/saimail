"""Semantic stability baseline: one response is not a model property (D-025).

The defect class this module eliminates: **a single answer read as what a model
does.** Runs 4 and 5 sent the identical ``S3.mailbox`` prompt to the identical
model four minutes apart and got different answers on two of four items. Every
per-model sentence in this lab's history rests on one call per unit.

So a small repeat sample is declared here, before any live call, and frozen in
``stability_registration.json`` beside this file:

* four cases, each an existing unit with its existing schema, expectation and
  deterministic grader: factual claim plus unverified rung, EV:0 attachment
  semantics, OPEN versus DEFER, and one contradiction relation;
* ``REPEATS`` identical calls per available participant per case;
* a fixed order -- round, then case, then participant -- so no participant or
  case owns a block of time;
* a call budget that covers the whole plan plus the discovery reserve;
* the analysis rules below.

The registration digest covers all of that and the exact prompt bytes. The
runner refuses to start when this code and the registered file disagree, so the
repeat count cannot be raised after a result without a new registration that
anyone can see.

Three findings, never merged, never scored:

``MODEL_VARIANCE``
    The same participant, one stimulus digest, at least two different answers
    on one boundary across its repeats.
``CROSS_MODEL_DISAGREEMENT``
    At least two participants that are each unanimous on a boundary across
    their answered repeats, with different answers.
``PROTOCOL_HOTSPOT``
    At least two independent participants -- distinct reported models -- each
    failing the registered expectation on the same boundary in at least
    ``REPEATED_FAILURE`` of their repeats.

A boundary is one question field (``Q1``, ``ANSWER``) or one mailbox item
(``M1``). An unparsed answer and a transport failure are facts about format
and delivery: they are counted, and they never count as variance, disagreement
or failure. Nothing here infers a motive or a hidden reasoning step, and
nothing combines the findings into a quality number.

Pure: no network, no clock, no filesystem. The runner is ``stability_run.py``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sailang.frame import Profile

from . import saifren_population as pop
from . import scenarios as sc
from .answer_schema import ATTENTION_CLASSES, classify_attention, grade, normalize

RULES = "saimail-stability/1"
REGISTRATION_FILE = "stability_registration.json"

#: Identical calls per participant per case. Registered; never raised after a result.
REPEATS = 3
#: (case label, unit id), in the declared order.
CASES = (
    ("FACTUAL_UNVERIFIED", "S1.evidence_absent"),
    ("EV0_ATTACHMENT", "S4.ev0_is_not_weak"),
    ("OPEN_VERSUS_DEFER", "S3.mailbox"),
    ("RELATION_CONTRADICTION", "S1.contradiction"),
)
#: Role A is the combo alias; role B is one external comparator when one answers.
MAX_PARTICIPANTS = 2
EXPERIMENT_CALLS = MAX_PARTICIPANTS * len(CASES) * REPEATS
MAX_CALLS = EXPERIMENT_CALLS + pop.DISCOVERY_RESERVE
#: A participant fails a boundary "repeatedly" at this many failed repeats.
REPEATED_FAILURE = 2
#: A hotspot needs this many independent participants failing repeatedly.
HOTSPOT_PARTICIPANTS = 2
#: A participant is unanimous on a boundary only over at least this many answers.
UNANIMITY_MIN_ANSWERS = 2

MODEL_VARIANCE = "MODEL_VARIANCE"
CROSS_MODEL_DISAGREEMENT = "CROSS_MODEL_DISAGREEMENT"
PROTOCOL_HOTSPOT = "PROTOCOL_HOTSPOT"
#: Repeats of one case that did not carry one prompt digest. Never variance.
STIMULUS_CHANGED = "STIMULUS_CHANGED"

UNPARSED = "UNPARSED"
NO_MODEL = "(no model reported)"


def cases(profile: Profile) -> Tuple[Tuple[str, sc.Single], ...]:
    plan = {u.unit_id: u for u in sc.build_plan(profile)}
    missing = [unit_id for _, unit_id in CASES if unit_id not in plan]
    if missing:
        raise ValueError(f"the registered cases name units the plan does not build: {missing}")
    return tuple((label, plan[unit_id]) for label, unit_id in CASES)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def registration(profile: Profile, protocol_version: str, max_tokens: int) -> dict:
    """Everything the run is bound to, in one canonical structure."""
    return {
        "rules": RULES,
        "repeats": REPEATS,
        "order": "round, then case, then participant role",
        "cases": [{"case": label, "unit_id": unit.unit_id, "scenario": unit.scenario,
                   "prompt_sha256": _sha256(unit.prompt()),
                   "boundaries": [f.name for f in unit.schema.fields],
                   "expect": {k: list(v) for k, v in unit.expect.items()},
                   "reference": dict(unit.reference)}
                  for label, unit in cases(profile)],
        "participants": {"max": MAX_PARTICIPANTS, "selection_rule": pop.SELECTION_RULE,
                         "replacement_policy": pop.REPLACEMENT_POLICY,
                         "roles": {"A": "the SAIFREN combo alias",
                                   "B": "one external catalog comparator, when one answers"}},
        "budget": {"experiment_calls": EXPERIMENT_CALLS,
                   "discovery_reserve": pop.DISCOVERY_RESERVE, "max_calls": MAX_CALLS},
        "request": {"protocol_version": protocol_version, "max_tokens": max_tokens,
                    "temperature": "NOT_SENT"},
        "analysis": {"repeated_failure": REPEATED_FAILURE,
                     "hotspot_participants": HOTSPOT_PARTICIPANTS,
                     "unanimity_min_answers": UNANIMITY_MIN_ANSWERS,
                     "findings": [MODEL_VARIANCE, CROSS_MODEL_DISAGREEMENT, PROTOCOL_HOTSPOT],
                     "not_counted_as_semantic": [UNPARSED, "ERROR", "NOT_RUN"]},
    }


def digest(declared: Mapping) -> str:
    canonical = json.dumps(declared, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + _sha256(canonical)


@dataclass(frozen=True)
class Step:
    repeat: int
    case: str
    unit: sc.Single
    role: str
    requested: str


def participants_of(population, combo: str) -> Tuple[Tuple[str, str], ...]:
    """(role, requested id) per resolved participant; the alias alone when none resolved."""
    resolved = [(p.role, p.requested) for p in getattr(population, "participants", ())]
    return tuple(resolved[:MAX_PARTICIPANTS]) or (("A", combo),)


def plan(participants: Sequence[Tuple[str, str]],
         declared: Sequence[Tuple[str, sc.Single]]) -> Tuple[Step, ...]:
    return tuple(Step(repeat, label, unit, role, requested)
                 for repeat in range(1, REPEATS + 1)
                 for label, unit in declared
                 for role, requested in participants)


# ------------------------------------------------------------------ analysis


def observe(step: Step, call: Mapping) -> dict:
    """One graded observation. A call that did not answer is recorded, never graded."""
    unit = step.unit
    base = {"call_id": call.get("call_id"), "repeat": step.repeat, "case": step.case,
            "unit_id": unit.unit_id, "role": step.role,
            "requested_model": call.get("requested_model"),
            "reported_model": call.get("reported_model") or NO_MODEL,
            "prompt_sha256": call.get("prompt_sha256"), "status": call.get("status")}
    if call.get("status") != "OK":
        base["verdict"] = call.get("status") or "ERROR"
        base["answers"] = {f.name: None for f in unit.schema.fields}
        if unit.reference:
            base["attention"] = classify_attention(unit.reference, {})["items"]
        return base
    graded = grade(unit.schema, unit.expect, call.get("output") or "")
    base["verdict"] = "PASS" if graded["pass"] else "FAIL"
    base["answers"] = dict(graded["values"])
    base["violations"] = [v["code"] for v in graded["violations"]]
    if unit.reference:
        base["attention"] = classify_attention(unit.reference, graded["values"])["items"]
    return base


def _failed(unit: sc.Single, boundary: str, answer: Optional[str]) -> Optional[bool]:
    """True/False against the registered expectation; None when nothing is registered or answered."""
    if answer is None or boundary not in unit.expect:
        return None
    return normalize(answer) not in {normalize(v) for v in unit.expect[boundary]}


def distributions(observations: Sequence[Mapping], units: Mapping[str, sc.Single],
                  protocol_version: str) -> List[dict]:
    """One row per model, route, scenario and protocol version. Counts only."""
    rows: Dict[tuple, dict] = {}
    for o in observations:
        key = (o["reported_model"], o["requested_model"], o["unit_id"])
        unit = units[o["unit_id"]]
        row = rows.setdefault(key, {
            "model": o["reported_model"], "route": o["requested_model"],
            "scenario": o["unit_id"], "case": o["case"], "protocol_version": protocol_version,
            "repeats": 0, "verdicts": {v: 0 for v in ("PASS", "FAIL", "ERROR", "NOT_RUN")},
            "answers": {f.name: {} for f in unit.schema.fields},
        })
        row["repeats"] += 1
        row["verdicts"][o["verdict"]] = row["verdicts"].get(o["verdict"], 0) + 1
        if o["status"] == "OK":
            for boundary, answer in o["answers"].items():
                name = answer if answer is not None else UNPARSED
                row["answers"][boundary][name] = row["answers"][boundary].get(name, 0) + 1
        if unit.reference:
            attention = row.setdefault("attention", {item: {c: 0 for c in ATTENTION_CLASSES}
                                                     for item in unit.reference})
            for item, detail in o["attention"].items():
                attention[item][detail["class"]] += 1
    return [rows[k] for k in sorted(rows)]


def fragility(observations: Sequence[Mapping], units: Mapping[str, sc.Single]) -> dict:
    answered = [o for o in observations if o["status"] == "OK" and o["reported_model"] != NO_MODEL]
    variance, changed = [], []
    by_participant: Dict[tuple, List[Mapping]] = {}
    for o in answered:
        by_participant.setdefault((o["requested_model"], o["reported_model"], o["unit_id"]),
                                  []).append(o)
    for (route, model, unit_id), group in sorted(by_participant.items()):
        if len({o["prompt_sha256"] for o in group}) > 1:
            changed.append({"finding": STIMULUS_CHANGED, "model": model, "route": route,
                            "scenario": unit_id})
            continue
        for boundary in (f.name for f in units[unit_id].schema.fields):
            values = [o["answers"][boundary] for o in group if o["answers"][boundary] is not None]
            if len(set(values)) >= 2:
                variance.append({"finding": MODEL_VARIANCE, "model": model, "route": route,
                                 "scenario": unit_id, "boundary": boundary,
                                 "answers": {v: values.count(v) for v in sorted(set(values))},
                                 "answered_repeats": len(values),
                                 "stimulus_sha256": group[0]["prompt_sha256"]})

    by_model: Dict[tuple, List[Mapping]] = {}
    for o in answered:
        by_model.setdefault((o["unit_id"], o["reported_model"]), []).append(o)
    disagreement, hotspots = [], []
    for unit_id, unit in sorted(units.items()):
        for boundary in (f.name for f in unit.schema.fields):
            stable, failing = {}, {}
            for (scenario, model), group in by_model.items():
                if scenario != unit_id:
                    continue
                values = [o["answers"][boundary] for o in group
                          if o["answers"][boundary] is not None]
                if len(values) >= UNANIMITY_MIN_ANSWERS and len(set(values)) == 1:
                    stable[model] = values[0]
                failures = sum(1 for v in values if _failed(unit, boundary, v))
                if failures >= REPEATED_FAILURE:
                    failing[model] = {"failed": failures, "answered": len(values)}
            if len(stable) >= 2 and len(set(stable.values())) >= 2:
                disagreement.append({"finding": CROSS_MODEL_DISAGREEMENT, "scenario": unit_id,
                                     "boundary": boundary,
                                     "stable_answers": dict(sorted(stable.items()))})
            if len(failing) >= HOTSPOT_PARTICIPANTS:
                hotspots.append({"finding": PROTOCOL_HOTSPOT, "scenario": unit_id,
                                 "boundary": boundary,
                                 "expected": list(unit.expect[boundary]),
                                 "failing_participants": dict(sorted(failing.items()))})
    return {MODEL_VARIANCE: variance, CROSS_MODEL_DISAGREEMENT: disagreement,
            PROTOCOL_HOTSPOT: hotspots, STIMULUS_CHANGED: changed}


def opaque_context(calls: Iterable[Mapping], estimate) -> dict:
    """Local estimate against gateway-reported input, per call and per model."""
    rows = []
    for call in calls:
        if call.get("status") == "NOT_RUN":
            continue
        local = estimate(call.get("prompt") or "")
        reported = (call.get("usage") or {}).get("prompt_tokens")
        rows.append({"call_id": call.get("call_id"), "unit_id": call.get("unit_id"),
                     "model": call.get("reported_model") or NO_MODEL,
                     "local_estimated_input": local, "gateway_reported_input": reported,
                     "delta": reported - local if isinstance(reported, int) else None})
    per_model: Dict[str, dict] = {}
    for row in rows:
        deltas = per_model.setdefault(row["model"], {"calls": 0, "deltas": []})
        deltas["calls"] += 1
        if row["delta"] is not None:
            deltas["deltas"].append(row["delta"])
    summary = {model: {"calls": d["calls"], "measured": len(d["deltas"]),
                       "delta_min": min(d["deltas"]) if d["deltas"] else None,
                       "delta_max": max(d["deltas"]) if d["deltas"] else None}
               for model, d in sorted(per_model.items())}
    return {"visibility": "OPAQUE", "per_model": summary, "per_call": rows}
