"""T-9B — total-friction benchmark for the v0.1 transport surface.

Built to be able to say NO. Every threshold is declared here, before any
measurement, and printed with the result.

Four questions, deliberately kept apart:

Q1  TRIAGE      triage prose  vs  v0 line  vs  v0.1 frame (standalone and batched)
Q2  FULL        full-semantics prose  vs  canonical record
Q3  WORKLOAD    progressive resolution vs eager loading, at declared open rates
Q4  ALIASES     transport-local aliases for repeated canonical identities

    python bench/t9b.py --out bench/out
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import pathlib
import statistics
import sys
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bench import tokenizer_adapters  # noqa: E402
from bench.corpus import CASES, REQUIRED_CLASSES, classes  # noqa: E402
from bench.prose import (  # noqa: E402
    FULL_TEMPLATE,
    TRIAGE_TEMPLATE,
    full_prose,
    summary_prose,
    triage_prose,
)
from sailang import Record  # noqa: E402
from sailang.frame import Profile, decode, project, project_batch  # noqa: E402
from sailang.line import Dictionary, default_dictionary  # noqa: E402
from sailang.line import project as project_v0  # noqa: E402

# ---------------------------------------------------------------- pre-registered

THRESHOLDS = {
    "rule": (
        "GO requires ALL of: zero semantic inversions; decode of every frame "
        "reproduces the declared triage ground truth; zero non-deterministic "
        "cases; at a 20% open rate the progressive workload costs below 0.70 of "
        "the eager full-prose baseline on every tokenizer; the local-alias "
        "break-even is at most 4 repeats on every tokenizer; and the v0.1 frame "
        "shows no p90 regression above 1.10x against triage prose. "
        "CONDITIONAL: semantics are clean and deterministic but at least one "
        "quantitative bar is missed. "
        "NO_GO: any semantic inversion, any decode mismatch, any "
        "non-determinism, or the progressive workload failing to beat eager "
        "loading at a 20% open rate."
    ),
    "workload_open_rate_for_gate": 0.20,
    "workload_go_below": 0.70,
    "alias_break_even_max": 4,
    "p90_regression_ceiling": 1.10,
}

#: Declared BEFORE measurement and not tuned afterwards.
WORKLOAD = {
    "messages": 100,
    "open_rates": (0.05, 0.20, 0.50),
    "escalation_to_record": 0.40,
    "note": (
        "Of the messages opened to a summary, a declared 40% escalate to the "
        "canonical record. R4 (attached evidence) is excluded: no real evidence "
        "artifacts exist yet, and inventing a size would be fabricated evidence. "
        "Including it would only widen the gap, since fewer than half the opened "
        "messages ever reach it."
    ),
}

TRIAGE_FIELDS = ("kind", "subject", "status", "has_evidence",
                 "refutes", "supports", "conflict", "falsifiable", "claim_open_record")


def percentile(values: List[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def stats(ratios: List[float]) -> Dict[str, float]:
    return {
        "median": statistics.median(ratios),
        "mean": statistics.fmean(ratios),
        "p90": percentile(ratios, 0.90),
        "best": min(ratios),
        "worst": max(ratios),
        "cases_not_cheaper": sum(1 for r in ratios if r >= 1.0),
    }


def lowercase_claim_slot(wire: str) -> str:
    """Mutate ONLY the claim vocabulary.

    The previous variant benchmark lowercased the whole line, which also
    lowercased the kind letter, the rung and the evidence marker. That measured
    a format nobody proposed. Fixed here; the old number is not carried forward.
    """
    slots = wire.split("|")
    slots[4] = slots[4].lower()
    return "|".join(slots)


def run(out_dir: pathlib.Path) -> dict:
    adapters = tokenizer_adapters.available()
    if not adapters:
        raise SystemExit("no tokenizer adapter available; a token count is required evidence")

    profile = Profile.load("1")
    empty_profile = Profile.inline("empty", {})
    v0_dictionary = default_dictionary()

    records = [Record.create(**case.fields) for case in CASES]
    rows: List[dict] = []
    inversions: List[dict] = []
    decode_mismatches: List[dict] = []
    nondeterministic: List[str] = []
    open_record_cases: List[str] = []

    for case, record in zip(CASES, records):
        frame = project(record, profile)
        if project(Record.create(**case.fields), profile).wire != frame.wire:
            nondeterministic.append(case.case)
        view = decode(frame)

        # ground truth is declared by hand in the corpus, never derived here
        for field in TRIAGE_FIELDS:
            expected = case.expect[field]
            actual = getattr(view, field)
            if field in ("subject", "status") and expected is not None and actual is None:
                continue  # declared loss, not an inversion
            if actual != expected:
                inversions.append({"case": case.case, "field": field,
                                   "expected": expected, "actual": actual})
        if view.claim_open_record:
            open_record_cases.append(case.case)

        # a frame decoded through a batch must yield the identical view
        batch_view = decode(project_batch([record], profile).frames[0])
        if batch_view != view:
            decode_mismatches.append({"case": case.case, "reason": "batch decode differs"})

        representations = {
            "A1_triage_prose": triage_prose(record, profile),
            "A2_full_prose": full_prose(record),
            "A3_human_prose": case.prose,
            "B_record": record.canonical_text(),
            "C1_line_v0": project_v0(record, v0_dictionary),
            "C2_frame_v01": frame.wire,
            "C3_frame_lowercase_claim": lowercase_claim_slot(frame.wire),
            "C4_frame_no_dictionary": project(record, empty_profile).wire,
        }
        for name, text in representations.items():
            row = {"case": case.case, "class": case.klass, "representation": name,
                   "utf8_bytes": len(text.encode("utf-8")), "characters": len(text),
                   "text": text}
            for adapter in adapters:
                row[f"tokens_{adapter.name}"] = adapter.count(text)
            rows.append(row)

    by_case: Dict[str, Dict[str, dict]] = {}
    for row in rows:
        by_case.setdefault(row["case"], {})[row["representation"]] = row

    # batch amortization: one header for the whole corpus
    batch_text = project_batch(records, profile).render()
    batch_header = batch_text.splitlines()[0]

    metrics: Dict[str, dict] = {}
    for adapter in adapters:
        key = f"tokens_{adapter.name}"
        q1 = {}
        for representation in ("C1_line_v0", "C2_frame_v01", "C3_frame_lowercase_claim",
                               "C4_frame_no_dictionary"):
            q1[representation] = stats([
                by_case[name][representation][key] / by_case[name]["A1_triage_prose"][key]
                for name in by_case
            ])
        q2 = {
            "B_record_over_A2_full_prose": stats([
                by_case[name]["B_record"][key] / by_case[name]["A2_full_prose"][key]
                for name in by_case
            ]),
        }
        header_tokens = adapter.count(batch_header)
        frame_total = sum(by_case[name]["C2_frame_v01"][key] for name in by_case)
        v0_total = sum(by_case[name]["C1_line_v0"][key] for name in by_case)
        metrics[adapter.name] = {
            "family": adapter.family,
            "q1_triage": q1,
            "q2_full_transfer": q2,
            "totals": {
                "A1_triage_prose": sum(by_case[n]["A1_triage_prose"][key] for n in by_case),
                "A2_full_prose": sum(by_case[n]["A2_full_prose"][key] for n in by_case),
                "A3_human_prose": sum(by_case[n]["A3_human_prose"][key] for n in by_case),
                "B_record": sum(by_case[n]["B_record"][key] for n in by_case),
                "C1_line_v0": v0_total,
                "C2_frame_v01": frame_total,
                "C2_frame_v01_plus_batch_header": frame_total + header_tokens,
                "C3_frame_lowercase_claim": sum(
                    by_case[n]["C3_frame_lowercase_claim"][key] for n in by_case),
                "C4_frame_no_dictionary": sum(
                    by_case[n]["C4_frame_no_dictionary"][key] for n in by_case),
            },
            "batch_header_tokens": header_tokens,
            "v0_marker_saving": v0_total - frame_total,
        }

    workload = _workload(by_case, adapters, records, profile)
    aliases = _aliases(records, adapters)

    verdict = classify(metrics, workload, aliases, len(inversions),
                       len(decode_mismatches), len(nondeterministic), adapters)

    result = {
        "corpus_size": len(CASES),
        "classes": classes(),
        "missing_classes": sorted(set(REQUIRED_CLASSES) - set(classes())),
        "tokenizers": [{"name": a.name, "family": a.family} for a in adapters],
        "thresholds": THRESHOLDS,
        "workload_declaration": WORKLOAD,
        "templates": {"triage": TRIAGE_TEMPLATE, "full": FULL_TEMPLATE},
        "profile": {"id": profile.id, "dictionary_version": profile.dictionary_version,
                    "dictionary_digest": profile.dictionary_digest,
                    "atoms": len(profile.atom_to_wire)},
        "metrics": metrics,
        "workload": workload,
        "aliases": aliases,
        "semantic": {
            "inversions": inversions,
            "inversion_count": len(inversions),
            "decode_mismatches": decode_mismatches,
            "open_record_cases": open_record_cases,
        },
        "determinism": {"nondeterministic_cases": nondeterministic},
        "verdict": verdict,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = ["case", "class", "representation", "utf8_bytes", "characters"] + [
        f"tokens_{a.name}" for a in adapters]
    with (out_dir / "t9b_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    (out_dir / "t9b_results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "T9B_REPORT.md").write_text(render(result, adapters), encoding="utf-8")
    return result


def _workload(by_case, adapters, records, profile) -> dict:
    """Progressive resolution against eager loading, at declared open rates."""
    order = [CASES[i % len(CASES)].case for i in range(WORKLOAD["messages"])]
    summaries = {case.case: summary_prose(record) for case, record in zip(CASES, records)}
    out: Dict[str, dict] = {}
    for adapter in adapters:
        key = f"tokens_{adapter.name}"
        frame_cost = [by_case[name]["C2_frame_v01"][key] for name in order]
        summary_cost = [adapter.count(summaries[name]) for name in order]
        record_cost = [by_case[name]["B_record"][key] for name in order]
        eager_full = sum(by_case[name]["A2_full_prose"][key] for name in order)
        eager_record = sum(record_cost)
        header = adapter.count(f"SAIB1|P:{profile.id}|N:{WORKLOAD['messages']}")
        scenarios = {}
        for rate in WORKLOAD["open_rates"]:
            opened = int(round(WORKLOAD["messages"] * rate))
            escalated = int(round(opened * WORKLOAD["escalation_to_record"]))
            total = header + sum(frame_cost) + sum(summary_cost[:opened]) + sum(record_cost[:escalated])
            scenarios[f"{int(rate * 100)}pct"] = {
                "opened": opened,
                "escalated_to_record": escalated,
                "progressive_tokens": total,
                "eager_full_prose_tokens": eager_full,
                "eager_record_tokens": eager_record,
                "ratio_vs_eager_full_prose": total / eager_full,
                "ratio_vs_eager_record": total / eager_record,
            }
        out[adapter.name] = scenarios
    return out


def _aliases(records, adapters) -> dict:
    """Break-even for a transport-local alias over a canonical identity.

    The canonical identity is never replaced: an alias is a batch-local
    reference that expands to the full CID through an explicit declaration.
    """
    sample_cid = next((r.get("EV").split(",")[0] for r in records
                       if r.get("EV") and r.get("EV") != "0"), None)
    refs: Dict[str, int] = {}
    for record in records:
        for field in ("EV", "REFUTES", "SUPPORTS", "CON", "INTEREST_REF"):
            value = record.get(field)
            if not value or value == "0":
                continue
            for ref in value.split(","):
                refs[ref] = refs.get(ref, 0) + 1
    out: Dict[str, dict] = {}
    for adapter in adapters:
        cid = adapter.count(sample_cid)
        alias = adapter.count("@7")
        declaration = adapter.count(f"DEF @7={sample_cid}")
        gain = cid - alias
        break_even = math.inf if gain <= 0 else declaration / gain
        distinct = len(refs)
        total_refs = sum(refs.values())
        repeated = sum(count for count in refs.values() if count > 1)
        naive = total_refs * cid
        aliased = distinct * declaration + total_refs * alias
        out[adapter.name] = {
            "cid_tokens": cid,
            "alias_tokens": alias,
            "declaration_tokens": declaration,
            "break_even_repeats": break_even,
            "break_even_repeats_ceiling": math.inf if gain <= 0 else math.ceil(break_even),
            "corpus_distinct_refs": distinct,
            "corpus_total_refs": total_refs,
            "corpus_repeated_refs": repeated,
            "corpus_naive_tokens": naive,
            "corpus_aliased_tokens": aliased,
            "corpus_saving_tokens": naive - aliased,
        }
    return out


def classify(metrics, workload, aliases, inversions, decode_mismatches,
             nondeterministic, adapters) -> str:
    if inversions or decode_mismatches or nondeterministic:
        return "NO_GO"
    gate_key = f"{int(THRESHOLDS['workload_open_rate_for_gate'] * 100)}pct"
    for adapter in adapters:
        ratio = workload[adapter.name][gate_key]["ratio_vs_eager_full_prose"]
        if ratio >= 1.0:
            return "NO_GO"
    conditional = False
    for adapter in adapters:
        ratio = workload[adapter.name][gate_key]["ratio_vs_eager_full_prose"]
        if ratio >= THRESHOLDS["workload_go_below"]:
            conditional = True
        if aliases[adapter.name]["break_even_repeats_ceiling"] > THRESHOLDS["alias_break_even_max"]:
            conditional = True
        p90 = metrics[adapter.name]["q1_triage"]["C2_frame_v01"]["p90"]
        if p90 > THRESHOLDS["p90_regression_ceiling"]:
            conditional = True
    return "CONDITIONAL" if conditional else "GO"


def render(result: dict, adapters) -> str:
    lines: List[str] = []
    out = lines.append
    out("# T-9B — total-friction benchmark (v0.1 transport surface)")
    out("")
    out(f"**Verdict: {result['verdict']}**")
    out("")
    out("Pre-registered rule, declared in `bench/t9b.py` before measurement:")
    out("")
    out("> " + result["thresholds"]["rule"])
    out("")
    out(f"Corpus: {result['corpus_size']} fixtures, {len(result['classes'])} classes. "
        f"Profile `{result['profile']['id'][:19]}…`, dictionary v"
        f"{result['profile']['dictionary_version']}, {result['profile']['atoms']} atoms.")
    out("")
    out("## Baselines, and why there are two of them")
    out("")
    out("| Baseline | Carries | Used for |")
    out("|---|---|---|")
    out("| `A1_triage_prose` | exactly the frame's triage semantics | Q1 |")
    out("| `A2_full_prose` | everything the record carries, full 64-hex ids included | Q2, workload |")
    out("| `A3_human_prose` | informal hand-written text, **not** equivalent | reference only, excluded from every verdict |")
    out("")
    out(f"Triage template: `{result['templates']['triage']}`")
    out("")
    out(f"Full template: `{result['templates']['full']}`")
    out("")
    out("## Q1 — triage: frame versus triage prose")
    out("")
    out("| tokenizer | v0 line | v0.1 frame | frame p90 | lowercase claim | no dictionary |")
    out("|---|---|---|---|---|---|")
    for adapter in adapters:
        q1 = result["metrics"][adapter.name]["q1_triage"]
        out(f"| {adapter.name} | {q1['C1_line_v0']['median']:.3f} "
            f"| **{q1['C2_frame_v01']['median']:.3f}** "
            f"| {q1['C2_frame_v01']['p90']:.3f} "
            f"| {q1['C3_frame_lowercase_claim']['median']:.3f} "
            f"| {q1['C4_frame_no_dictionary']['median']:.3f} |")
    out("")
    for adapter in adapters:
        m = result["metrics"][adapter.name]
        out(f"- `{adapter.name}`: dropping the per-frame marker saved "
            f"{m['v0_marker_saving']} tokens over {result['corpus_size']} frames; the batch "
            f"header costs {m['batch_header_tokens']} tokens once.")
    out("")
    out("## Q2 — full transfer: record versus complete prose")
    out("")
    out("| tokenizer | record/full-prose median | mean | p90 | best | worst | record cheaper in |")
    out("|---|---|---|---|---|---|---|")
    for adapter in adapters:
        s = result["metrics"][adapter.name]["q2_full_transfer"]["B_record_over_A2_full_prose"]
        cheaper = result["corpus_size"] - s["cases_not_cheaper"]
        out(f"| {adapter.name} | {s['median']:.3f} | {s['mean']:.3f} | {s['p90']:.3f} "
            f"| {s['best']:.3f} | {s['worst']:.3f} | {cheaper}/{result['corpus_size']} |")
    out("")
    out("## Q3 — progressive decoding workload")
    out("")
    out(f"{result['workload_declaration']['messages']} messages; of those opened to a "
        f"summary, a declared {int(result['workload_declaration']['escalation_to_record'] * 100)}% "
        "escalate to the canonical record. Declared before the run and not tuned.")
    out("")
    out("> " + result["workload_declaration"]["note"])
    out("")
    out("| tokenizer | open rate | progressive | eager full prose | ratio | vs eager records |")
    out("|---|---|---|---|---|---|")
    for adapter in adapters:
        for rate, data in result["workload"][adapter.name].items():
            out(f"| {adapter.name} | {rate} | {data['progressive_tokens']} "
                f"| {data['eager_full_prose_tokens']} "
                f"| **{data['ratio_vs_eager_full_prose']:.3f}** "
                f"| {data['ratio_vs_eager_record']:.3f} |")
    out("")
    out("## Q4 — local alias break-even")
    out("")
    out("| tokenizer | CID | alias | declaration | break-even repeats | corpus saving |")
    out("|---|---|---|---|---|---|")
    for adapter in adapters:
        a = result["aliases"][adapter.name]
        out(f"| {adapter.name} | {a['cid_tokens']} | {a['alias_tokens']} "
            f"| {a['declaration_tokens']} | {a['break_even_repeats']:.2f} "
            f"| {a['corpus_saving_tokens']} |")
    out("")
    a = result["aliases"][adapters[0].name]
    out(f"Corpus reference distribution: {a['corpus_total_refs']} references over "
        f"{a['corpus_distinct_refs']} distinct identities, of which "
        f"{a['corpus_repeated_refs']} appear more than once.")
    out("")
    out("## Semantics")
    out("")
    out(f"- Semantic inversions: {result['semantic']['inversion_count']}.")
    for item in result["semantic"]["inversions"]:
        out(f"  - {item['case']}.{item['field']}: expected {item['expected']!r}, got {item['actual']!r}")
    out(f"- Batch/standalone decode mismatches: {len(result['semantic']['decode_mismatches'])}.")
    out(f"- Non-deterministic cases: {result['determinism']['nondeterministic_cases'] or 'none'}.")
    out(f"- Frames that carry no claim (OPEN RECORD): "
        f"{len(result['semantic']['open_record_cases'])} of {result['corpus_size']}.")
    out("")
    out("## Tokenizer caveat")
    out("")
    out("Every count is evidence for the tokenizer that produced it. None of these are")
    out("Claude, Sol, GLM, Qwen or DeepSeek tokenizers. A vocabulary tuned to one family")
    out("and called universal is exactly the error this section exists to prevent.")
    out("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="bench/out")
    args = parser.parse_args()
    result = run(pathlib.Path(args.out))
    gate = f"{int(THRESHOLDS['workload_open_rate_for_gate'] * 100)}pct"
    print(json.dumps({
        "verdict": result["verdict"],
        "inversions": result["semantic"]["inversion_count"],
        "decode_mismatches": len(result["semantic"]["decode_mismatches"]),
        "q1_frame_over_triage_prose_median": {
            name: round(m["q1_triage"]["C2_frame_v01"]["median"], 4)
            for name, m in result["metrics"].items()},
        "q2_record_over_full_prose_median": {
            name: round(m["q2_full_transfer"]["B_record_over_A2_full_prose"]["median"], 4)
            for name, m in result["metrics"].items()},
        f"workload_{gate}_ratio": {
            name: round(scen[gate]["ratio_vs_eager_full_prose"], 4)
            for name, scen in result["workload"].items()},
        "alias_break_even": {
            name: a["break_even_repeats_ceiling"] for name, a in result["aliases"].items()},
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
