"""C2 — how much semantic coverage is worth buying?

T-9B found that a large share of opens were fallbacks: R1 could not read the
message, so it had to be opened. That makes vocabulary coverage, not filter
cleverness, the lever on cost. This measures the lever.

Atoms are stable semantic concepts, not English words. The stopping rule is
stated before the measurement: **stop adding atoms when opening R2 is cheaper
than expanding the ABI.**

    python bench/coverage_curve.py --out bench/out
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bench import tokenizer_adapters  # noqa: E402
from bench.prose import summary_prose  # noqa: E402
from bench.selector_corpus import CASES, INTEREST  # noqa: E402
from saimail.acceptance import ProfileRegistry  # noqa: E402
from saimail.selector import DEFER, IGNORE, OPEN_R2, OPEN_R3, select  # noqa: E402
from sailang import Record  # noqa: E402
from sailang.frame import Batch, Profile, decode, project_batch  # noqa: E402

STOPPING_RULE = (
    "Stop adding atoms when the marginal atom saves fewer emitted R2 tokens than "
    "it costs to define and carry. Reported as marginal tokens saved per atom "
    "added; a negative or near-zero tail is the signal to stop."
)


def accepted(profile: Profile):
    """The receiver's acceptance capability, minted as a receiver would."""
    return ProfileRegistry.with_profiles(profile).resolve(profile.id)


def _subset_profile(full: Profile, atoms: List[str], version: str) -> Profile:
    return Profile.inline(version, {
        atom: {"wire": full.atom_to_wire[atom], "render": full.render[atom]}
        for atom in atoms
    })


def run(out_dir: pathlib.Path) -> dict:
    full = Profile.load("1")
    adapters = tokenizer_adapters.available()
    records = [Record.create(**case.fields) for case in CASES]
    summaries = [summary_prose(record) for record in records]

    # Atoms ordered by how often the corpus actually uses them: a real dictionary
    # grows by observed need, not alphabetically.
    usage: Dict[str, int] = {}
    for record in records:
        for token in record.claim.replace(">", " ").replace("=", " ").split():
            if token in full.atom_to_wire:
                usage[token] = usage.get(token, 0) + 1
    ordered = sorted(full.atom_to_wire, key=lambda a: (-usage.get(a, 0), a))

    steps: List[dict] = []
    sizes = sorted({0, 2, 4, 6, 8, 10, 13, 16, 20, 25, len(ordered)})
    for size in sizes:
        atoms = ordered[:size]
        profile = _subset_profile(full, atoms, f"cov{size}")
        container = project_batch(records, profile).render()
        views = [decode(frame) for frame in Batch.parse(container, accepted(profile)).frames]
        decisions = [select(view, INTEREST) for view in views]
        fallback = sum(1 for d in decisions
                       if d.rule in ("R2-UNKNOWN", "R3-OPEN-RECORD"))
        emitted = {}
        for adapter in adapters:
            total = 0
            for decision, summary, record in zip(decisions, summaries, records):
                if decision.verdict == OPEN_R2:
                    total += adapter.count(summary)
                elif decision.verdict == OPEN_R3:
                    total += adapter.count(summary) + adapter.count(record.canonical_text())
            emitted[adapter.name] = total
        steps.append({
            "atoms": size,
            "coverage_of_used_atoms": (
                sum(1 for a in atoms if usage.get(a)) / max(1, len([a for a in ordered if usage.get(a)]))
            ),
            "wire_bytes": len(container.encode("utf-8")),
            "fallback_opens": fallback,
            "ignored": sum(1 for d in decisions if d.verdict == IGNORE),
            "deferred": sum(1 for d in decisions if d.verdict == DEFER),
            "opened": sum(1 for d in decisions if d.verdict in (OPEN_R2, OPEN_R3)),
            "open_rate": sum(1 for d in decisions if d.verdict in (OPEN_R2, OPEN_R3)) / len(views),
            "emitted_tokens": emitted,
            "dictionary_bytes": len(json.dumps(
                {a: {"wire": full.atom_to_wire[a], "render": full.render[a]} for a in atoms},
                ensure_ascii=False).encode("utf-8")),
        })

    primary = adapters[0].name if adapters else None
    marginal: List[dict] = []
    for previous, current in zip(steps, steps[1:]):
        added = current["atoms"] - previous["atoms"]
        saved = (previous["emitted_tokens"][primary] - current["emitted_tokens"][primary]
                 if primary else 0)
        marginal.append({
            "from_atoms": previous["atoms"], "to_atoms": current["atoms"],
            "atoms_added": added,
            "tokens_saved": saved,
            "tokens_saved_per_atom": saved / added if added else 0.0,
            "fallback_delta": current["fallback_opens"] - previous["fallback_opens"],
            "wire_bytes_delta": current["wire_bytes"] - previous["wire_bytes"],
        })

    result = {
        "corpus_size": len(records),
        "atom_order": ordered,
        "atom_usage": usage,
        "stopping_rule": STOPPING_RULE,
        "tokenizers": [a.name for a in adapters],
        "steps": steps,
        "marginal": marginal,
        "note": (
            "Coverage is measured against the atoms this corpus actually uses. A "
            "dictionary can always be made to look better by adding atoms nobody "
            "writes; that is why the curve is plotted against observed usage and "
            "why arbitrary English vocabulary is not added."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coverage_curve.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "COVERAGE_CURVE.md").write_text(render(result), encoding="utf-8")
    return result


def render(result: dict) -> str:
    primary = result["tokenizers"][0]
    lines = ["# C2 — semantic coverage curve", "",
             f"Corpus: {result['corpus_size']} messages. Token column: `{primary}`.", "",
             "> " + result["stopping_rule"], "",
             "| atoms | wire bytes | dict bytes | fallback opens | opened | open rate | emitted tokens |",
             "|---|---|---|---|---|---|---|"]
    for step in result["steps"]:
        lines.append(
            f"| {step['atoms']} | {step['wire_bytes']} | {step['dictionary_bytes']} "
            f"| {step['fallback_opens']} | {step['opened']} | {step['open_rate']:.3f} "
            f"| {step['emitted_tokens'][primary]} |")
    lines += ["", "## Marginal return per atom added", "",
              "| atoms | added | tokens saved | per atom | fallback delta |",
              "|---|---|---|---|---|"]
    for row in result["marginal"]:
        lines.append(
            f"| {row['from_atoms']}→{row['to_atoms']} | {row['atoms_added']} "
            f"| {row['tokens_saved']} | {row['tokens_saved_per_atom']:.1f} "
            f"| {row['fallback_delta']} |")
    lines += ["", "## Caveat", "", result["note"], ""]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="bench/out")
    args = parser.parse_args()
    result = run(pathlib.Path(args.out))
    primary = result["tokenizers"][0]
    print(json.dumps({
        "steps": [{"atoms": s["atoms"], "fallback": s["fallback_opens"],
                   "open_rate": round(s["open_rate"], 3),
                   "emitted": s["emitted_tokens"][primary]} for s in result["steps"]],
        "marginal_per_atom": [round(m["tokens_saved_per_atom"], 1) for m in result["marginal"]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
