"""Where does the line form actually spend its tokens?

Supplementary to `cost_compare.py`. The main benchmark answers "is the shipped
line cheaper than prose". This one answers "which parts of the shipped line are
worth their bytes", which is what a CONDITIONAL verdict needs in order to name
a simplification instead of guessing one.

Variants are measured, not implemented. Nothing here changes SAILANG.

    python bench/variants.py --out bench/out
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bench import tokenizer_adapters  # noqa: E402
from bench.corpus import CASES  # noqa: E402
from sailang import Record  # noqa: E402
from sailang.line import Dictionary, default_dictionary, project  # noqa: E402

VARIANTS = {
    "shipped": "the line exactly as SAILANG v0 emits it",
    "no_version_marker": "shipped, minus the per-line L1D<v>| prefix",
    "no_dictionary": "shipped, minus the prefix and with substitution disabled",
    "lowercase_claim": "shipped, minus the prefix, claim segments lowercased",
    "no_claim_slot": "shipped, minus the prefix, claim always OPEN RECORD",
}


def build(case) -> Dict[str, str]:
    record = Record.create(**case.fields)
    shipped = project(record, default_dictionary())
    markerless = shipped.split("|", 1)[1]
    slots = shipped.split("|")
    slots[5] = "?"
    return {
        "shipped": shipped,
        "no_version_marker": markerless,
        "no_dictionary": project(record, Dictionary("X", {})).split("|", 1)[1],
        "lowercase_claim": markerless.lower(),
        "no_claim_slot": "|".join(slots).split("|", 1)[1],
    }


def run(out_dir: pathlib.Path) -> dict:
    adapters = tokenizer_adapters.available()
    if not adapters:
        raise SystemExit("no tokenizer adapter available")

    texts = [build(case) for case in CASES]
    prose = [case.prose for case in CASES]

    result: dict = {"corpus_size": len(CASES), "variants": VARIANTS, "tokenizers": {}}
    for adapter in adapters:
        base = [adapter.count(text) for text in prose]
        per_variant: Dict[str, dict] = {}
        for name in VARIANTS:
            counts = [adapter.count(row[name]) for row in texts]
            ratios: List[float] = [c / b for c, b in zip(counts, base)]
            per_variant[name] = {
                "total_tokens": sum(counts),
                "median_over_prose": statistics.median(ratios),
                "mean_over_prose": statistics.fmean(ratios),
                "worst_over_prose": max(ratios),
                "cases_not_cheaper_than_prose": sum(1 for r in ratios if r >= 1.0),
                "total_bytes": sum(len(row[name].encode("utf-8")) for row in texts),
            }
        shipped = per_variant["shipped"]["total_tokens"]
        per_variant_marker = shipped - per_variant["no_version_marker"]["total_tokens"]
        dictionary_delta = (
            per_variant["no_dictionary"]["total_tokens"]
            - per_variant["no_version_marker"]["total_tokens"]
        )
        result["tokenizers"][adapter.name] = {
            "family": adapter.family,
            "prose_total_tokens": sum(base),
            "variants": per_variant,
            "version_marker_token_cost": per_variant_marker,
            "dictionary_token_saving": dictionary_delta,
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "variants.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="bench/out")
    args = parser.parse_args()
    result = run(pathlib.Path(args.out))
    for name, data in result["tokenizers"].items():
        print(f"== {name}")
        print(f"   version marker costs {data['version_marker_token_cost']} tokens across "
              f"{result['corpus_size']} lines")
        print(f"   dictionary saves     {data['dictionary_token_saving']} tokens")
        for variant, stats in data["variants"].items():
            print(f"   {variant:20s} median={stats['median_over_prose']:.3f} "
                  f"total={stats['total_tokens']} "
                  f"not_cheaper={stats['cases_not_cheaper_than_prose']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
