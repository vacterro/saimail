"""T-9: does SAILANG buy a real information advantage, or just shorter syntax?

This benchmark is built to be able to say NO. The classification thresholds are
declared here, before the numbers, and are printed with every run so a reader
can check that they were not moved afterwards (spec/DECISIONS.md D-007).

    python bench/cost_compare.py --out bench/out
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib
import statistics
import sys
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bench import tokenizer_adapters  # noqa: E402
from bench.corpus import CASES, REQUIRED_CLASSES, classes  # noqa: E402
from sailang import Record  # noqa: E402
from sailang.line import Dictionary, default_dictionary, project, triage  # noqa: E402

#: Pre-registered classification rule. Stated before the measurement, printed
#: with the result, and capable of returning NO_GO.
THRESHOLDS = {
    "rule": (
        "GO: zero semantic inversions AND deterministic projection AND "
        "median(line tokens / prose tokens) < 0.60 on every tokenizer. "
        "CONDITIONAL: zero inversions and that median in [0.60, 0.95). "
        "NO_GO: any semantic inversion, or non-determinism, or that median >= 0.95 "
        "on any tokenizer."
    ),
    "go_below": 0.60,
    "no_go_at_or_above": 0.95,
}

TRIAGE_FIELDS = (
    "kind", "subject", "status", "has_evidence",
    "refutes", "supports", "conflict", "falsifiable", "claim_open_record",
)


def classify(medians: List[float], inversion_count: int, nondeterministic_count: int) -> str:
    """Apply the pre-registered rule. Separate from measurement so it can be
    tested against inputs that must produce NO_GO."""
    if inversion_count or nondeterministic_count:
        return "NO_GO"
    if not medians:
        return "NO_GO"
    worst = max(medians)
    if worst >= THRESHOLDS["no_go_at_or_above"]:
        return "NO_GO"
    if worst < THRESHOLDS["go_below"]:
        return "GO"
    return "CONDITIONAL"


def percentile(values: List[float], fraction: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def measure_text(text: str, adapters) -> Dict[str, object]:
    row: Dict[str, object] = {
        "utf8_bytes": len(text.encode("utf-8")),
        "characters": len(text),
    }
    for adapter in adapters:
        row[f"tokens_{adapter.name}"] = adapter.count(text)
    return row


def run(out_dir: pathlib.Path) -> dict:
    adapters = tokenizer_adapters.available()
    if not adapters:
        raise SystemExit(
            "no tokenizer adapter is available; a token count is required evidence "
            "and must not be approximated"
        )

    dictionary = default_dictionary()
    empty_dictionary = Dictionary("X", {})

    rows: List[dict] = []
    semantic: List[dict] = []
    inversions: List[dict] = []
    intentional_losses: List[dict] = []
    nondeterministic: List[str] = []
    dictionary_savings: List[int] = []

    for case in CASES:
        record = Record.create(**case.fields)
        record_text = record.canonical_text()
        line = project(record, dictionary)
        line_again = project(Record.create(**case.fields), dictionary)
        if line != line_again:
            nondeterministic.append(case.case)

        undicted = project(record, empty_dictionary)
        dictionary_savings.append(len(undicted.encode("utf-8")) - len(line.encode("utf-8")))

        for representation, text in (
            ("A_prose", case.prose),
            ("B_record", record_text),
            ("C_line", line),
        ):
            row = {"case": case.case, "class": case.klass, "representation": representation}
            row.update(measure_text(text, adapters))
            row["text"] = text
            rows.append(row)

        view = triage(record, dictionary)
        case_inversions = []
        case_losses = []
        for field in TRIAGE_FIELDS:
            expected = case.expect[field]
            actual = view[field]
            if field in ("subject", "status") and expected is not None and actual is None:
                case_losses.append({"case": case.case, "field": field, "expected": expected})
                continue
            if actual != expected:
                case_inversions.append(
                    {"case": case.case, "field": field, "expected": expected, "actual": actual}
                )
        if view["claim_open_record"]:
            case_losses.append({"case": case.case, "field": "claim", "expected": record.claim})
        inversions.extend(case_inversions)
        intentional_losses.extend(case_losses)
        semantic.append(
            {
                "case": case.case,
                "class": case.klass,
                "line": line,
                "triage_fields_preserved": len(TRIAGE_FIELDS) - len(case_inversions) - len(
                    [loss for loss in case_losses if loss["field"] != "claim"]
                ),
                "triage_fields_total": len(TRIAGE_FIELDS),
                "inversions": len(case_inversions),
                "claim_open_record": view["claim_open_record"],
            }
        )

    by_case: Dict[str, Dict[str, dict]] = {}
    for row in rows:
        by_case.setdefault(row["case"], {})[row["representation"]] = row

    metrics: Dict[str, dict] = {}
    for adapter in adapters:
        key = f"tokens_{adapter.name}"
        line_over_prose, record_over_prose, line_over_record = [], [], []
        prose_minus_line = []
        for case_name, reps in by_case.items():
            prose, record_row, line_row = reps["A_prose"], reps["B_record"], reps["C_line"]
            line_over_prose.append(line_row[key] / prose[key])
            record_over_prose.append(record_row[key] / prose[key])
            line_over_record.append(line_row[key] / record_row[key])
            prose_minus_line.append((case_name, prose[key] - line_row[key]))
        metrics[adapter.name] = {
            "family": adapter.family,
            "line_over_prose": {
                "median": statistics.median(line_over_prose),
                "mean": statistics.fmean(line_over_prose),
                "p90": percentile(line_over_prose, 0.90),
                "best": min(line_over_prose),
                "worst": max(line_over_prose),
            },
            "record_over_prose": {
                "median": statistics.median(record_over_prose),
                "mean": statistics.fmean(record_over_prose),
                "p90": percentile(record_over_prose, 0.90),
                "best": min(record_over_prose),
                "worst": max(record_over_prose),
            },
            "line_over_record": {
                "median": statistics.median(line_over_record),
                "mean": statistics.fmean(line_over_record),
                "p90": percentile(line_over_record, 0.90),
            },
            "line_larger_than_prose_cases": sorted(
                name for name, delta in prose_minus_line if delta <= 0
            ),
            "record_larger_than_prose_cases": sorted(
                name for name, reps in by_case.items()
                if reps["B_record"][key] >= reps["A_prose"][key]
            ),
        }

    byte_ratios = [
        by_case[name]["C_line"]["utf8_bytes"] / by_case[name]["A_prose"]["utf8_bytes"]
        for name in by_case
    ]
    record_byte_ratios = [
        by_case[name]["B_record"]["utf8_bytes"] / by_case[name]["A_prose"]["utf8_bytes"]
        for name in by_case
    ]

    medians = [metrics[a.name]["line_over_prose"]["median"] for a in adapters]
    verdict = classify(medians, len(inversions), len(nondeterministic))

    dictionary_path = pathlib.Path(__file__).resolve().parent.parent / "sailang" / "dictionary" / "v0.json"
    result = {
        "corpus_size": len(CASES),
        "classes": classes(),
        "required_classes": list(REQUIRED_CLASSES),
        "missing_classes": sorted(set(REQUIRED_CLASSES) - set(classes())),
        "tokenizers": [{"name": a.name, "family": a.family} for a in adapters],
        "thresholds": THRESHOLDS,
        "metrics": metrics,
        "bytes": {
            "line_over_prose_median": statistics.median(byte_ratios),
            "record_over_prose_median": statistics.median(record_byte_ratios),
        },
        "semantic": {
            "inversions": inversions,
            "inversion_count": len(inversions),
            "intentional_losses": intentional_losses,
            "intentional_loss_count": len(intentional_losses),
            "claim_open_record_cases": [s["case"] for s in semantic if s["claim_open_record"]],
        },
        "determinism": {"nondeterministic_cases": nondeterministic},
        "dictionary": {
            "path": str(dictionary_path),
            "file_bytes": dictionary_path.stat().st_size,
            "terms": len(default_dictionary().terms),
            "bytes_saved_total": sum(dictionary_savings),
            "bytes_saved_median": statistics.median(dictionary_savings),
            "line_marker_bytes": len(f"L1D{dictionary.version}|".encode("utf-8")),
        },
        "verdict": verdict,
        "per_case": semantic,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        fieldnames = ["case", "class", "representation", "utf8_bytes", "characters"] + [
            f"tokens_{a.name}" for a in adapters
        ] + ["tokenizer_families", "triage_fields_preserved", "notes"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        semantic_by_case = {s["case"]: s for s in semantic}
        for row in rows:
            entry = dict(row)
            entry["tokenizer_families"] = ";".join(a.family for a in adapters)
            info = semantic_by_case[row["case"]]
            entry["triage_fields_preserved"] = (
                f"{info['triage_fields_preserved']}/{info['triage_fields_total']}"
                if row["representation"] == "C_line" else ""
            )
            entry["notes"] = (
                "claim not representable in the line: OPEN RECORD"
                if row["representation"] == "C_line" and info["claim_open_record"] else ""
            )
            writer.writerow(entry)
    (out_dir / "results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "REPORT.md").write_text(render_report(result, by_case, adapters), encoding="utf-8")
    return result


def render_report(result: dict, by_case: dict, adapters) -> str:
    lines: List[str] = []
    out = lines.append
    out("# T-9 — SAILANG proof-of-value benchmark")
    out("")
    out(f"**Verdict: {result['verdict']}**")
    out("")
    out("Pre-registered classification rule, declared in `bench/cost_compare.py` before")
    out("any measurement and printed here unchanged:")
    out("")
    out("> " + result["thresholds"]["rule"])
    out("")
    out(f"Corpus: {result['corpus_size']} fixtures across {len(result['classes'])} "
        "information classes.")
    missing = result["missing_classes"]
    out(f"Missing required classes: {missing if missing else 'none'}.")
    out("")
    out("## Tokenizer caveat")
    out("")
    out("Every token count below is evidence **for the tokenizer that produced it**.")
    out("None of these are Claude, Sol, GLM, Qwen or DeepSeek tokenizers; those families")
    out("segment text differently and could move these ratios in either direction.")
    out("Measured here:")
    out("")
    for entry in result["tokenizers"]:
        out(f"- `{entry['name']}` ({entry['family']})")
    out("")
    out("## Token cost")
    out("")
    out("| tokenizer | line/prose median | mean | p90 | best | worst | record/prose median |")
    out("|---|---|---|---|---|---|---|")
    for adapter in adapters:
        m = result["metrics"][adapter.name]
        lop, rop = m["line_over_prose"], m["record_over_prose"]
        out(
            f"| {adapter.name} | {lop['median']:.3f} | {lop['mean']:.3f} | {lop['p90']:.3f} "
            f"| {lop['best']:.3f} | {lop['worst']:.3f} | {rop['median']:.3f} |"
        )
    out("")
    out(f"Bytes, median: line/prose {result['bytes']['line_over_prose_median']:.3f}, "
        f"record/prose {result['bytes']['record_over_prose_median']:.3f}.")
    out("")
    out("## Negative findings")
    out("")
    for adapter in adapters:
        m = result["metrics"][adapter.name]
        larger_line = m["line_larger_than_prose_cases"]
        larger_record = m["record_larger_than_prose_cases"]
        out(f"- `{adapter.name}`: line is not cheaper than prose in "
            f"{len(larger_line)} case(s){': ' + ', '.join(larger_line) if larger_line else ''}.")
        out(f"- `{adapter.name}`: the canonical record costs at least as much as prose in "
            f"{len(larger_record)} of {result['corpus_size']} cases.")
    out("")
    losses = result["semantic"]["claim_open_record_cases"]
    out(f"- The line deliberately drops the claim in {len(losses)} of "
        f"{result['corpus_size']} cases (OPEN RECORD): {', '.join(losses) if losses else 'none'}.")
    out(f"- Semantic inversions: {result['semantic']['inversion_count']}.")
    if result["semantic"]["inversions"]:
        for item in result["semantic"]["inversions"]:
            out(f"  - {item['case']}.{item['field']}: expected {item['expected']!r}, "
                f"got {item['actual']!r}")
    out(f"- Non-deterministic cases: {result['determinism']['nondeterministic_cases'] or 'none'}.")
    out("")
    out("## Dictionary overhead")
    out("")
    d = result["dictionary"]
    out(f"- {d['terms']} terms, {d['file_bytes']} bytes on disk (paid once, not per line).")
    out(f"- Per-line version marker: {d['line_marker_bytes']} bytes, paid on every line.")
    out(f"- Bytes saved by substitution across the corpus: {d['bytes_saved_total']} "
        f"(median {d['bytes_saved_median']} per line).")
    out("")
    out("## Per-case detail")
    out("")
    out("| case | class | prose B | record B | line B | triage kept | line |")
    out("|---|---|---|---|---|---|---|")
    for entry in result["per_case"]:
        reps = by_case[entry["case"]]
        out(
            f"| {entry['case']} | {entry['class']} | {reps['A_prose']['utf8_bytes']} "
            f"| {reps['B_record']['utf8_bytes']} | {reps['C_line']['utf8_bytes']} "
            f"| {entry['triage_fields_preserved']}/{entry['triage_fields_total']} "
            f"| `{entry['line']}` |"
        )
    out("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="bench/out", help="output directory")
    args = parser.parse_args()
    result = run(pathlib.Path(args.out))
    print(json.dumps({
        "verdict": result["verdict"],
        "corpus_size": result["corpus_size"],
        "inversions": result["semantic"]["inversion_count"],
        "tokenizers": [t["name"] for t in result["tokenizers"]],
        "line_over_prose_median": {
            name: round(m["line_over_prose"]["median"], 4)
            for name, m in result["metrics"].items()
        },
        "thresholds": THRESHOLDS,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
