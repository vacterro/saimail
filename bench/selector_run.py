"""T-14 — a real interest filter, measured instead of assumed.

T-9B declared open rates of 5%, 20% and 50% and proved the arithmetic of
selective opening. It did not prove that anything can select correctly. This
run replaces the assumption with a filter and reports what it actually does.

Error costs are declared and kept apart. They are NOT collapsed into one score,
because no calibration exists that would justify a weighting:

    FALSE_IGNORE  >>  FALSE_OPEN  >>  EXTRA_BYTES

A filter that saves 80% of the context by silently dropping relevant
discoveries has not saved anything.

    python bench/selector_run.py --out bench/out
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bench import tokenizer_adapters  # noqa: E402
from bench.prose import full_prose, summary_prose  # noqa: E402
from bench.selector_corpus import CASES, CLASSES, INTEREST, TRUTH_COUNTS  # noqa: E402
from saimail.acceptance import ProfileRegistry  # noqa: E402
from saimail.selector import (DEFER, IGNORE, OPEN_R2, OPEN_R3, RULES, depth,  # noqa: E402
                              select)
from sailang import Record, SailangError  # noqa: E402
from sailang.frame import (Batch, Profile, TriageFrame, _bind_verified, decode,  # noqa: E402
                           project_batch)

ERROR_COSTS = {
    "order": "FALSE_IGNORE >> FALSE_OPEN >> EXTRA_BYTES",
    "note": (
        "Reported separately and never summed. A single score would need a "
        "calibrated exchange rate between a missed discovery and a wasted "
        "summary, and no such calibration exists."
    ),
}

LATENCY_ITERATIONS = 2000


def accepted(profile: Profile):
    """The receiver's acceptance capability, minted as a receiver would."""
    return ProfileRegistry.with_profiles(profile).resolve(profile.id)


def run(out_dir: pathlib.Path) -> dict:
    profile = Profile.load("1")
    records = [Record.create(**case.fields) for case in CASES]

    # The filter only ever sees what a container handed it.
    container = project_batch(records, profile).render()
    frames = Batch.parse(container, accepted(profile)).frames
    views = [decode(frame) for frame in frames]

    decisions = [select(view, INTEREST) for view in views]

    start = time.perf_counter_ns()
    for _ in range(LATENCY_ITERATIONS):
        for view in views:
            select(view, INTEREST)
    selector_ns_per_message = (time.perf_counter_ns() - start) / (LATENCY_ITERATIONS * len(views))

    adapters = tokenizer_adapters.available()
    summaries = [summary_prose(record) for record in records]
    fulls = [full_prose(record) for record in records]

    rows: List[dict] = []
    false_ignores: List[dict] = []
    false_opens: List[dict] = []
    under_opens: List[dict] = []
    for case, view, decision, summary, full in zip(CASES, views, decisions, summaries, fulls):
        row = {
            "case": case.case if hasattr(case, "case") else case.name,
            "class": case.klass,
            "truth": case.truth,
            "verdict": decision.verdict,
            "rule": decision.rule,
            "reason": decision.reason,
            "why_truth": case.why,
            "agrees": decision.verdict == case.truth,
            "unknown_atoms": list(view.claim_unknown_wires),
            "claim_open_record": view.claim_open_record,
        }
        if decision.verdict == IGNORE and depth(case.truth) > depth(IGNORE):
            false_ignores.append(row)
        elif depth(decision.verdict) > depth(IGNORE) and case.truth == IGNORE:
            false_opens.append(row)
        elif depth(decision.verdict) < depth(case.truth):
            under_opens.append(row)
        rows.append(row)

    scanned = len(views)
    opened_r2 = sum(1 for d in decisions if d.verdict == OPEN_R2)
    opened_r3 = sum(1 for d in decisions if d.verdict == OPEN_R3)
    ignored = sum(1 for d in decisions if d.verdict == IGNORE)
    deferred = sum(1 for d in decisions if d.verdict == DEFER)

    context: Dict[str, dict] = {}
    for adapter in adapters:
        emitted = 0
        eager_full = sum(adapter.count(text) for text in fulls)
        for decision, summary, full in zip(decisions, summaries, fulls):
            if decision.verdict == OPEN_R2:
                emitted += adapter.count(summary)
            elif decision.verdict == OPEN_R3:
                emitted += adapter.count(summary) + adapter.count(full)
        context[adapter.name] = {
            "emitted_tokens": emitted,
            "eager_full_tokens": eager_full,
            "ratio_vs_eager": emitted / eager_full,
        }

    # Refusals at the container boundary: these never reach the selector.
    refusals = _boundary_refusals(container, profile)

    result = {
        "corpus_size": scanned,
        "classes": CLASSES,
        "interest": {"atoms": sorted(INTEREST.atoms), "subjects": sorted(INTEREST.subjects)},
        "rules": [{"id": rid, "reason": reason} for rid, reason in RULES],
        "error_costs": ERROR_COSTS,
        "truth_distribution": TRUTH_COUNTS,
        "counts": {
            "r1_scanned": scanned,
            "r2_opened": opened_r2,
            "r3_opened": opened_r3,
            "ignored": ignored,
            "deferred": deferred,
            "actual_open_rate": (opened_r2 + opened_r3) / scanned,
            "r3_rate": opened_r3 / scanned,
            "unknown_fallback": sum(1 for r in rows if r["unknown_atoms"]),
            "open_record_fallback": sum(1 for r in rows if r["claim_open_record"]),
            "agreement": sum(1 for r in rows if r["agrees"]) / scanned,
        },
        "errors": {
            "false_ignore_count": len(false_ignores),
            "false_ignore": false_ignores,
            "false_open_count": len(false_opens),
            "false_open": false_opens,
            "under_open_count": len(under_opens),
            "under_open": under_opens,
        },
        "bytes": {
            "r1_container_bytes": len(container.encode("utf-8")),
            "r1_bytes_per_message": len(container.encode("utf-8")) / scanned,
        },
        "context_cost": context,
        "selector_ns_per_message": selector_ns_per_message,
        "boundary_refusals": refusals,
        "rules_by_verdict": _rule_histogram(decisions),
        "per_case": rows,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "selector_results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "SELECTOR_REPORT.md").write_text(render(result, adapters), encoding="utf-8")
    return result


def _rule_histogram(decisions) -> dict:
    out: Dict[str, int] = {}
    for decision in decisions:
        out[decision.rule] = out.get(decision.rule, 0) + 1
    return dict(sorted(out.items()))


def _boundary_refusals(container: str, profile: Profile) -> dict:
    """Malformed frames and stale profiles never produce a view at all."""
    out: Dict[str, str] = {}
    stale = Profile.inline("stale", {"WOMBAT": {"wire": "WMB", "render": "a wombat"}})
    try:
        Batch.parse(container, accepted(stale))
        out["stale_profile"] = "ACCEPTED"
    except SailangError as exc:
        out["stale_profile"] = exc.code
    broken = container.rstrip("\n") + "\nF|queue|U2|EV+\n"
    try:
        Batch.parse(broken, accepted(profile))
        out["malformed_frame_container"] = "ACCEPTED"
    except SailangError as exc:
        out["malformed_frame_container"] = exc.code
    lines = container.rstrip("\n").split("\n")
    header, body = lines[0].split("|"), lines[1:]
    defs = [line for line in body if line.startswith("DEF ")]
    frames = [line for line in body if not line.startswith("DEF ")]
    header[2] = f"N:{len(frames) + 1}"
    fixed = "|".join(header) + "\n" + "\n".join(
        defs + frames + ["F|queue|U2|EV+"]) + "\n"
    try:
        parsed = Batch.parse(fixed, accepted(profile))
        decode(parsed.frames[-1])
        out["malformed_frame_decode"] = "ACCEPTED"
    except SailangError as exc:
        out["malformed_frame_decode"] = exc.code
    try:
        TriageFrame(wire="F|queue|U2|EV+|RETRY|-", profile=stale)
        out["forged_frame_binding"] = "ACCEPTED"
    except SailangError as exc:
        out["forged_frame_binding"] = exc.code
    # The sanctioned route still works, and is meant to: a decoder that has
    # verified a container header says so by name.
    out["explicitly_bound_frame"] = decode(
        _bind_verified("F|queue|U2|EV+|WMB|-", stale)).kind
    return out


def render(result: dict, adapters) -> str:
    lines: List[str] = []
    add = lines.append
    counts = result["counts"]
    errors = result["errors"]
    add("# T-14 — real interest filter over R1")
    add("")
    add(f"Corpus: {result['corpus_size']} messages across {len(result['classes'])} "
        "selection-stress classes. Declared interest: atoms "
        f"{result['interest']['atoms']}, subjects {result['interest']['subjects']}.")
    add("")
    add("Ground truth is what a reader who already knew everything would have done,")
    add("declared per fixture and not derived from the rules.")
    add("")
    add("## Rules, declared before the run")
    add("")
    for rule in result["rules"]:
        add(f"- `{rule['id']}` — {rule['reason']}")
    add("")
    add("## What the filter actually did")
    add("")
    add("| measure | value |")
    add("|---|---|")
    add(f"| R1 scanned | {counts['r1_scanned']} |")
    add(f"| opened to R2 | {counts['r2_opened']} |")
    add(f"| opened to R3 | {counts['r3_opened']} |")
    add(f"| ignored | {counts['ignored']} |")
    add(f"| **actual open rate** | **{counts['actual_open_rate']:.3f}** |")
    add(f"| agreement with declared truth | {counts['agreement']:.3f} |")
    add(f"| unknown-atom fallbacks | {counts['unknown_fallback']} |")
    add(f"| open-record fallbacks | {counts['open_record_fallback']} |")
    add(f"| selector latency | {result['selector_ns_per_message']:.0f} ns per message |")
    add(f"| R1 bytes per message | {result['bytes']['r1_bytes_per_message']:.1f} |")
    add("")
    add("Truth distribution for reference: "
        + ", ".join(f"{k} {v}" for k, v in result["truth_distribution"].items()) + ".")
    add("")
    add("## Errors, kept apart on purpose")
    add("")
    add("> " + result["error_costs"]["order"])
    add(">")
    add("> " + result["error_costs"]["note"])
    add("")
    add(f"- **false ignore: {errors['false_ignore_count']}** — the expensive failure")
    for row in errors["false_ignore"]:
        add(f"  - `{row['case']}` ({row['class']}): truth {row['truth']}, "
            f"rule {row['rule']} — {row['why_truth']}")
    add(f"- false open: {errors['false_open_count']}")
    for row in errors["false_open"]:
        add(f"  - `{row['case']}` ({row['class']}): rule {row['rule']} — {row['reason']}")
    add(f"- under-open (opened, but not deep enough): {errors['under_open_count']}")
    for row in errors["under_open"]:
        add(f"  - `{row['case']}`: truth {row['truth']}, got {row['verdict']}")
    add("")
    add("## Context actually emitted")
    add("")
    add("| tokenizer | emitted at R2/R3 | eager full prose | ratio |")
    add("|---|---|---|---|")
    for adapter in adapters:
        c = result["context_cost"][adapter.name]
        add(f"| {adapter.name} | {c['emitted_tokens']} | {c['eager_full_tokens']} "
            f"| **{c['ratio_vs_eager']:.3f}** |")
    add("")
    add("## Rule usage")
    add("")
    for rule, count in result["rules_by_verdict"].items():
        add(f"- `{rule}`: {count}")
    add("")
    add("## Boundary refusals")
    add("")
    add("These never reach the selector at all.")
    add("")
    for label, code in result["boundary_refusals"].items():
        add(f"- {label}: `{code}`")
    add("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="bench/out")
    args = parser.parse_args()
    result = run(pathlib.Path(args.out))
    print(json.dumps({
        "counts": result["counts"],
        "false_ignore": result["errors"]["false_ignore_count"],
        "false_open": result["errors"]["false_open_count"],
        "under_open": result["errors"]["under_open_count"],
        "context_ratio": {k: round(v["ratio_vs_eager"], 4)
                          for k, v in result["context_cost"].items()},
        "selector_ns_per_message": round(result["selector_ns_per_message"]),
        "boundary_refusals": result["boundary_refusals"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
