"""Mechanical report over one live SAIFREN artifact.

Counts and listings only. Every number names its denominator; nothing is
averaged across scenarios, nothing is voted, and no answer is promoted to
"what the agents think". Interpretation lives in lab/ANALYSIS.md, written by a
person or an agent and labelled as such.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from lab import experiment_class as ec


def _units(artifact: dict, prefix: str) -> List[dict]:
    return [u for u in artifact["units"] if u["unit_id"].startswith(prefix)]


def _call(artifact: dict, call_id: Optional[str]) -> dict:
    return next((c for c in artifact["calls"] if c["call_id"] == call_id), {})


def _answer(unit: dict, field: str) -> Optional[str]:
    return unit.get("grade", {}).get("values", {}).get(field)


def _count(rows: List[bool]) -> str:
    return f"{sum(1 for r in rows if r)}/{len(rows)}"


def render(artifact: dict) -> str:
    s = artifact["summary"]
    klass = artifact.get("experiment_class") or ec.classify_artifact(artifact)
    out: List[str] = [
        "# SAIFREN live run report",
        "",
        f"Authority: `{artifact['authority']}`, which is not " + ", ".join(
            f"`{x}`" for x in artifact["is_not"]) + ".",
        artifact["note"],
        "",
        f"Started {artifact['started']}; {artifact['live_calls']} live calls of "
        f"{artifact['planned_calls']} planned, cap {artifact['max_runs']}; "
        f"stopped: {artifact['stopped'] or 'no'}.",
        "",
        "## LIVE_RUN_COUNT",
        "",
        f"- calls attempted: {s['calls_attempted']}; returned content: {s['calls_ok']}; "
        f"errors: {len(s['errors'])}",
        "- unit verdicts: " + ", ".join(f"{k} {v}" for k, v in s["verdicts"].items()),
        "",
        "## EXPERIMENT_CLASS",
        "",
        f"- EXPERIMENT_CLASS: `{klass['experiment_class']}` (rule `{klass['rule']}`, "
        f"membership evidence from {klass['membership_evidence_basis']})",
        f"- COMBO: `{klass['combo']}`",
        "- OBSERVED_COMBO_MEMBERS: " + (", ".join(f"`{m}`" for m in klass["observed_combo_members"])
                                        or "none"),
        "- EXTERNAL_COMPARATORS: " + (", ".join(f"`{m}`" for m in klass["external_comparators"])
                                      or "none"),
        "- DISTINCT_REPORTED_MODELS: " + (", ".join(f"`{m}`" for m in
                                                    klass["distinct_reported_models"]) or "none"),
        f"- ROSTER_STATUS: `{klass['roster_status']}` (basis `{klass['roster_status_basis']}`)",
        "",
        klass["note"],
        "",
        "## ROUTES_OBSERVED",
        "",
    ]
    by_route: Dict[str, List[str]] = {}
    for call in artifact["calls"]:
        if call["status"] == "NOT_RUN":
            continue
        by_route.setdefault(call.get("reported_model") or "(none reported)", []).append(
            f"{call['unit_id']}:{call['role']}")
    for route, uses in sorted(by_route.items()):
        meaning = ("no model reported" if route == "(none reported)"
                   else ec.describe(route, klass))
        out.append(f"- `{route}`: {len(uses)} call(s); {meaning}")
    out.append(f"- resolution: {s['route_resolution']}; provider stated by gateway: "
               f"{s['providers_stated_by_gateway'] or 'never'} "
               "(a model id prefix is a namespace, not a provider claim)")

    out += ["", "## R2_SEMANTIC_RESULTS (S1)", ""]
    for unit in _units(artifact, "S1."):
        route = _call(artifact, unit.get("call_id")).get("reported_model")
        answers = unit.get("grade", {}).get("values")
        out.append(f"- {unit['unit_id']} via `{route}`: {unit['verdict']}; answers {answers}; "
                   f"expected {unit['expect']}")

    out += ["", "## TRUE_AGENT_HANDOFF_RESULTS (S2)", ""]
    for unit in _units(artifact, "S2."):
        m = unit.get("metrics", {})
        transform = unit.get("transform") or {}
        out.append(f"- {unit['unit_id']}: {unit['verdict']}; A via `{m.get('route_a')}` said "
                   f"kind={m.get('a_kind')} rung={m.get('a_rung')} "
                   f"evidence_invented={m.get('a_evidence_invention')}; transform "
                   f"{transform.get('result')} {transform.get('code') or ''}; B via "
                   f"`{m.get('route_b')}` evidence={m.get('b_evidence_reading')} "
                   f"inflation={m.get('b_confidence_inflation')} "
                   f"qualifier_retained={m.get('b_qualifier_retained')} next={m.get('b_next')}; "
                   f"routes differ: {m.get('routes_differ')}")

    trials = _units(artifact, "S5.")
    out += ["", "## LEGACY_CONTROL_RESULTS (S5)", "",
            f"Sample: {len(trials)} trial(s). Every line is a separate measurement; none is a "
            "score, and a sample this small supports no generalization.", ""]
    for arm in ("legacy", "control"):
        rows = [t.get("metrics", {}).get(arm) for t in trials]
        rows = [r for r in rows if r]
        out.append(f"### {arm} arm, n={len(rows)}")
        if not rows:
            out.append("- no measured calls")
            continue
        for key in ("correct_first_verification_target", "repeated_known_mistake",
                    "orientation_failure", "timeout_ruled_out", "open_suspicion_ruled_out"):
            out.append(f"- {key}: {_count([r[key] for r in rows])}")
        out.append(f"- invented_evidence: {_count([bool(r['invented_evidence']) for r in rows])} "
                   f"{[r['invented_evidence'] for r in rows]}")
        out.append(f"- unnecessary_work: {_count([bool(r['unnecessary_work']) for r in rows])} "
                   f"{[r['unnecessary_work'] for r in rows]}")
        out.append(f"- task_relevant_semantic_retention: "
                   f"{_count([bool(r['task_relevant_semantic_retention']) for r in rows])}")
        if arm == "legacy":
            out.append(f"- qualifier_retention: {_count([r['qualifier_retention'] for r in rows])}")
            out.append(f"- scope_retention: {_count([r['scope_retention'] for r in rows])}")
            out.append(f"- transferred_hypothesis_hardened: "
                       f"{_count([r['transferred_hypothesis_hardened'] for r in rows])}")
        out.append(f"- first targets {[r['first_target'] for r in rows]}, steps "
                   f"{[r['steps'] for r in rows]}, routes {[r['route'] for r in rows]}")
    packets = [t.get("metrics", {}).get("packet") for t in trials]
    packets = [p for p in packets if p]
    out.append(f"### packets written by A, n={len(packets)}")
    for key in ("packet_complete", "packet_red_herring_captured", "packet_open_question_kept",
                "packet_scope_caveat_kept", "packet_ungrounded_advice"):
        out.append(f"- {key}: {_count([p[key] for p in packets])}")
    out.append(f"- packet_invented_refs: {[p['packet_invented_refs'] for p in packets]}")
    out.append(f"- packet_evidence_misattribution: {[p.get('packet_evidence_misattribution') for p in packets]}")

    s1 = {u["unit_id"]: u for u in _units(artifact, "S1.")}
    s2 = [u.get("metrics", {}) for u in _units(artifact, "S2.")]
    s4 = {u["unit_id"]: u for u in _units(artifact, "S4.")}
    legacy = [t.get("metrics", {}).get("legacy") for t in trials]
    legacy = [r for r in legacy if r]
    control = [t.get("metrics", {}).get("control") for t in trials]
    control = [r for r in control if r]

    def yes(unit_id: str, field: str, table: dict) -> str:
        unit = table.get(unit_id)
        return "not run" if not unit or "grade" not in unit else str(_answer(unit, field) == "YES")

    out += ["", "## CONFIDENCE_INFLATION", "",
            f"- S2 A rung above unverified: {_count([m.get('a_confidence_inflation') for m in s2 if 'a_rung' in m])}",
            f"- S2 B acts on or cites the unverified claim: {_count([m.get('b_confidence_inflation') for m in s2 if 'b_next' in m])}",
            f"- S2 B hardening words in KNOWN: {[m.get('b_known_hardening') for m in s2 if 'b_next' in m]}",
            f"- S1 hypothesis read as established fact: {yes('S1.hypothesis', 'Q1', s1)}",
            f"- S4 SUPPORTED read as proven: {yes('S4.supported_is_not_proven', 'ANSWER', s4)}",
            f"- S5 packet hardening in WATCH_NEXT: {[p['packet_watch_next_hardening'] for p in packets]}",
            "", "## EVIDENCE_INVENTION", "",
            f"- S2 A claims attached evidence: {_count([m.get('a_evidence_invention') for m in s2 if 'a_rung' in m])}",
            f"- S2 B says evidence exists: {_count([m.get('b_evidence_invention') for m in s2 if 'b_next' in m])}",
            f"- S1 absent evidence read as asserted: {yes('S1.evidence_absent', 'Q1', s1)}",
            f"- S5 packet refs not in the investigation: {[p['packet_invented_refs'] for p in packets]}",
            f"- S5 legacy arm refs not in its input: {[r['invented_evidence'] for r in legacy]}",
            f"- S5 control arm refs not in its input: {[r['invented_evidence'] for r in control]}",
            "", "## AUTHORITY_CONFUSION", "",
            f"- S4 assistant proposal read as user instruction: {yes('S4.proposal_is_not_command', 'ANSWER', s4)}",
            f"- S1 goal read as a statement about the world: {yes('S1.goal', 'Q1', s1)}",
            f"- S1 goal read as needing evidence: {yes('S1.goal', 'Q2', s1)}",
            "", "## QUALIFIER_LOSS", "",
            f"- S2 B drops what remains unverified: {_count([not m.get('b_qualifier_retained') for m in s2 if 'b_next' in m])}",
            f"- S1 'no evidence attached' read as false: {yes('S1.evidence_absent', 'Q2', s1)}",
            f"- S4 EV:0 read as weak evidence: {yes('S4.ev0_is_not_weak', 'ANSWER', s4)}",
            f"- S4 UNKNOWN read as false: {yes('S4.unknown_is_not_false', 'ANSWER', s4)}",
            f"- S5 legacy arm rules out the open heartbeat suspicion: {_count([r['open_suspicion_ruled_out'] for r in legacy])}",
            f"- S5 legacy arm keeps the open suspicion: {_count([r['qualifier_retention'] for r in legacy])}",
            f"- S5 legacy arm retains observed scope: {_count([r['scope_retention'] for r in legacy])}",
            "", "## DEFER_BEHAVIOR (S3)", ""]
    out += ["Four named outcomes, reported separately. `EXACT` is agreement with the "
            "deterministic selector; `FALSE_IGNORE` is an item the selector opened and the "
            "agent dropped; `UNDER_OPEN` is one the selector opened and the agent kept for "
            "later; `OVER_OPEN` is context spent on what the filter did not ask for. None of "
            "them is a verdict, and a unit's PASS is decided by its registered expectation, "
            "not by this table.", ""]
    totals = s.get("attention", {})
    if totals:
        out.append("- run totals: " + ", ".join(f"{k} {v}" for k, v in totals.items() if v))
    for unit in _units(artifact, "S3."):
        answers = unit.get("grade", {}).get("values", {})
        route = _call(artifact, unit.get("call_id")).get("reported_model")
        out.append(f"- {unit['unit_id']} via `{route}`: {unit['verdict']}")
        classes = unit.get("attention", {}).get("items", {})
        for item, reference in unit["reference"].items():
            named = classes.get(item, {}).get("class", "not classified")
            out.append(f"  - {item}: agent {answers.get(item)}, deterministic selector "
                       f"{reference} -> {named}")
        counts = unit.get("attention", {}).get("counts")
        if counts:
            out.append("  - " + ", ".join(f"{k} {v}" for k, v in counts.items() if v))

    out += ["", "## OPAQUE_CONTEXT_FINDINGS", ""]
    accounting = s.get("opaque_context_measurements", [])
    if not accounting:
        out.append("- no live opaque context measurements recorded")
    else:
        routes = sorted({a["route"] for a in accounting if a.get("route")})
        for rt in routes:
            rt_entries = [a for a in accounting if a.get("route") == rt]
            deltas = [a["delta"] for a in rt_entries if a.get("delta") is not None]
            local_toks = [a["local_estimated_input_tokens"] for a in rt_entries if a.get("local_estimated_input_tokens") is not None]
            gw_toks = [a["gateway_reported_prompt_tokens"] for a in rt_entries if a.get("gateway_reported_prompt_tokens") is not None]
            if deltas:
                out.append(f"- route `{rt}`: {len(rt_entries)} call(s); delta range {min(deltas)}..{max(deltas)} tokens "
                           f"(local prompt est {min(local_toks)}..{max(local_toks)}, gateway prompt {min(gw_toks)}..{max(gw_toks)})")
            else:
                out.append(f"- route `{rt}`: {len(rt_entries)} call(s); no gateway usage reported")
        out.append("")
        out.append("### Per-call token accounting")
        for a in accounting:
            out.append(f"- {a['unit_id']}:{a['role']} via `{a.get('route')}`: "
                       f"local_est={a.get('local_estimated_input_tokens')}, "
                       f"gateway_reported={a.get('gateway_reported_prompt_tokens')}, "
                       f"delta={a.get('delta')}")

    out += ["", "## ERRORS_TIMEOUTS", ""]
    if not s["errors"]:
        out.append("- none")
    for error in s["errors"]:
        out.append(f"- {error['unit_id']}:{error['role']} {error['error_class']}: {error['error']}")
    out.append("")
    return "\n".join(out)
