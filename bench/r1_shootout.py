"""T-15 — does the custom SAILANG wire justify its own syntax?

R1 is a machine data plane. It is not inserted into model context during
ordinary mailbox scanning, so token count is a **secondary** diagnostic here,
not the metric.

Acceptance criteria are declared below, before any measurement, and printed
with the result. A decision to drop the custom syntax is a successful outcome:
the semantic schema can outlive the wire that carried it.

    python bench/r1_shootout.py --out bench/out
"""

from __future__ import annotations

import argparse
import ast
import inspect
import json
import pathlib
import statistics
import sys
import time
import tracemalloc
from typing import Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from bench import r1_codecs, tokenizer_adapters  # noqa: E402
from bench.corpus import CASES  # noqa: E402
from sailang import Record, SailangError  # noqa: E402
from sailang.frame import Profile  # noqa: E402

# ---------------------------------------------------------------- pre-registered

CRITERIA = {
    "rule": (
        "Correctness gates first, and they disqualify: a codec must round-trip "
        "every fixture to an identical TriageView, refuse every malformed input, "
        "refuse an unknown field, and refuse a container whose profile differs. "
        "A codec that fails any of those is out regardless of its numbers. "
        "Among the survivors: KEEP_CUSTOM_WIRE only if the SAILANG wire is at "
        "most 0.85x the bytes of the best standard codec AND at most 1.25x its "
        "decode latency AND at most 1.50x its code surface. Otherwise "
        "DROP_CUSTOM_WIRE while keeping the semantic schema. REDESIGN_R1 if no "
        "codec passes the correctness gates."
    ),
    "bytes_advantage_required": 0.85,
    "decode_latency_ceiling": 1.25,
    "code_surface_ceiling": 1.50,
    "latency_repeats": 7,
    "latency_iterations": 200,
}

MALFORMED = {
    "truncated_container": lambda text: text.split("\n")[0] + "\n",
    "count_mismatch": lambda text: text.replace("N:45", "N:99").replace(
        '"n":45', '"n":99').replace("n=45", "n=99"),
    "garbage_body": lambda text: text.rstrip("\n") + "\nnot a frame at all\n",
    "empty": lambda text: "",
    "header_only_garbage": lambda text: "garbage\n" + "\n".join(text.split("\n")[1:]),
}


def _logical_lines(function_names, module) -> int:
    """Code surface: logical statements, comments and docstrings excluded."""
    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    total = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in function_names:
            for child in ast.walk(node):
                if isinstance(child, ast.stmt) and not isinstance(
                    child, (ast.FunctionDef, ast.Expr)
                ):
                    total += 1
                elif isinstance(child, ast.Expr) and not isinstance(child.value, ast.Constant):
                    total += 1
    return total


def _time(callable_, repeats: int, iterations: int) -> float:
    """Median of repeats, each the mean over `iterations` calls, in ns per call."""
    samples = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        for _ in range(iterations):
            callable_()
        samples.append((time.perf_counter_ns() - start) / iterations)
    return statistics.median(samples)


def run(out_dir: pathlib.Path) -> dict:
    profile = Profile.load("1")
    other_profile = Profile.inline("other", {"RETRY": {"wire": "RTY", "render": "a retry"}})
    records = [Record.create(**case.fields) for case in CASES]
    adapters = tokenizer_adapters.available()

    reference = r1_codecs.sailang_decode_all(
        r1_codecs.sailang_encode(records, profile), profile)

    results: Dict[str, dict] = {}
    for name, codec in r1_codecs.CODECS.items():
        encode, decode = codec["encode"], codec["decode"]
        text = encode(records, profile)
        body_bytes = len("\n".join(text.rstrip("\n").split("\n")[1:]).encode("utf-8"))
        header_bytes = len(text.rstrip("\n").split("\n")[0].encode("utf-8"))

        views = decode(text, profile)
        round_trip_ok = views == reference

        malformed_refusals = {}
        for label, mutate in MALFORMED.items():
            broken = mutate(text)
            try:
                decode(broken, profile)
                malformed_refusals[label] = "ACCEPTED"
            except (SailangError, ValueError, IndexError, KeyError, TypeError) as exc:
                malformed_refusals[label] = type(exc).__name__
        malformed_all_refused = all(v != "ACCEPTED" for v in malformed_refusals.values())

        try:
            decode(_with_unknown_field(text, name), profile)
            unknown_field = "ACCEPTED"
        except (SailangError, ValueError, IndexError, KeyError) as exc:
            unknown_field = getattr(exc, "code", type(exc).__name__)

        try:
            decode(text, other_profile)
            profile_behaviour = "ACCEPTED"
        except (SailangError, ValueError) as exc:
            profile_behaviour = getattr(exc, "code", type(exc).__name__)

        tracemalloc.start()
        encode(records, profile)
        _, encode_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        tracemalloc.start()
        decode(text, profile)
        _, decode_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        surface = _logical_lines(
            set(codec["functions"]) | set(r1_codecs.SHARED_FUNCTIONS), r1_codecs)

        row = {
            "bytes_total": len(text.encode("utf-8")),
            "bytes_body": body_bytes,
            "bytes_header": header_bytes,
            "bytes_per_frame": body_bytes / len(records),
            "encode_ns_per_batch": _time(lambda: encode(records, profile),
                                         CRITERIA["latency_repeats"],
                                         CRITERIA["latency_iterations"] // 10),
            "decode_ns_per_batch": _time(lambda: decode(text, profile),
                                         CRITERIA["latency_repeats"],
                                         CRITERIA["latency_iterations"] // 10),
            "encode_peak_bytes": encode_peak,
            "decode_peak_bytes": decode_peak,
            "code_surface_statements": surface,
            "round_trip_identical_view": round_trip_ok,
            "malformed_refusals": malformed_refusals,
            "malformed_all_refused": malformed_all_refused,
            "unknown_field_behaviour": unknown_field,
            "wrong_profile_behaviour": profile_behaviour,
            "correctness_ok": bool(round_trip_ok and malformed_all_refused
                                   and unknown_field != "ACCEPTED"
                                   and profile_behaviour != "ACCEPTED"),
        }
        for adapter in adapters:
            row[f"tokens_{adapter.name}"] = adapter.count(text)
        results[name] = row

    verdict, reasoning = classify(results)
    out = {
        "corpus_size": len(records),
        "profile": {"id": profile.id, "dictionary_version": profile.dictionary_version},
        "criteria": CRITERIA,
        "codecs": results,
        "verdict": verdict,
        "reasoning": reasoning,
        "tokenizers": [a.name for a in adapters],
        "note": (
            "Latency is wall-clock on one machine and one interpreter; it ranks "
            "codecs against each other on the same run, and is not an absolute "
            "figure. Token counts are a secondary diagnostic: R1 is not meant to "
            "enter model context during ordinary scanning. MEASUREMENT BOUNDARY, "
            "stated because it favours nobody only if it is stated: every codec "
            "ends at the same typed view produced by `sailang.frame.decode`, and "
            "that shared layer is counted against none of them. What `code surface` "
            "measures is therefore the EXTRA code each wire needs on top of a "
            "typed-view layer they all depend on -- not the total cost of owning "
            "the format."
        ),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "r1_shootout.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "R1_SHOOTOUT.md").write_text(render(out), encoding="utf-8")
    return out


def _with_unknown_field(text: str, codec_name: str) -> str:
    lines = text.rstrip("\n").split("\n")
    if codec_name == "B_compact_json":
        payload = json.loads(lines[1])
        payload["zz"] = "surprise"
        lines[1] = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    elif codec_name == "C_typed_kv":
        lines[1] = lines[1] + ";zz=surprise"
    else:
        lines[1] = lines[1] + "|surprise"
    return "\n".join(lines) + "\n"


def classify(results: Dict[str, dict]):
    reasoning: List[str] = []
    survivors = {name: row for name, row in results.items() if row["correctness_ok"]}
    for name, row in results.items():
        if not row["correctness_ok"]:
            reasoning.append(f"{name} failed a correctness gate and is disqualified")
    if not survivors:
        return "REDESIGN_R1", reasoning
    custom = results["A_sailang_wire"]
    if "A_sailang_wire" not in survivors:
        reasoning.append("the custom wire did not survive the correctness gates")
        return "DROP_CUSTOM_WIRE", reasoning
    standard = {n: r for n, r in survivors.items() if n != "A_sailang_wire"}
    if not standard:
        reasoning.append("no standard codec survived, so the custom wire stands by default")
        return "KEEP_CUSTOM_WIRE", reasoning
    best_bytes = min(r["bytes_body"] for r in standard.values())
    best_decode = min(r["decode_ns_per_batch"] for r in standard.values())
    best_surface = min(r["code_surface_statements"] for r in standard.values())
    bytes_ratio = custom["bytes_body"] / best_bytes
    decode_ratio = custom["decode_ns_per_batch"] / best_decode
    surface_ratio = custom["code_surface_statements"] / best_surface
    reasoning.append(f"custom/best-standard bytes {bytes_ratio:.3f} "
                     f"(needs <= {CRITERIA['bytes_advantage_required']})")
    reasoning.append(f"custom/best-standard decode latency {decode_ratio:.3f} "
                     f"(needs <= {CRITERIA['decode_latency_ceiling']})")
    reasoning.append(f"custom/best-standard code surface {surface_ratio:.3f} "
                     f"(needs <= {CRITERIA['code_surface_ceiling']})")
    if (bytes_ratio <= CRITERIA["bytes_advantage_required"]
            and decode_ratio <= CRITERIA["decode_latency_ceiling"]
            and surface_ratio <= CRITERIA["code_surface_ceiling"]):
        return "KEEP_CUSTOM_WIRE", reasoning
    return "DROP_CUSTOM_WIRE", reasoning


def render(out: dict) -> str:
    lines: List[str] = []
    add = lines.append
    add("# T-15 — R1 representation shootout")
    add("")
    add(f"**Verdict: {out['verdict']}**")
    add("")
    add("Pre-registered criteria, declared in `bench/r1_shootout.py` before measurement:")
    add("")
    add("> " + out["criteria"]["rule"])
    add("")
    add(f"Corpus: {out['corpus_size']} records, identical R1 semantics in every codec.")
    add("")
    add("## Correctness gates")
    add("")
    add("| codec | round-trip view | malformed refused | unknown field | wrong profile | passes |")
    add("|---|---|---|---|---|---|")
    for name, row in out["codecs"].items():
        add(f"| {name} | {row['round_trip_identical_view']} | "
            f"{row['malformed_all_refused']} | `{row['unknown_field_behaviour']}` | "
            f"`{row['wrong_profile_behaviour']}` | **{row['correctness_ok']}** |")
    add("")
    add("## Cost")
    add("")
    add("| codec | body bytes | bytes/frame | header | encode ns | decode ns | "
        "encode peak B | decode peak B | statements |")
    add("|---|---|---|---|---|---|---|---|---|")
    for name, row in out["codecs"].items():
        add(f"| {name} | {row['bytes_body']} | {row['bytes_per_frame']:.1f} | "
            f"{row['bytes_header']} | {row['encode_ns_per_batch']:.0f} | "
            f"{row['decode_ns_per_batch']:.0f} | {row['encode_peak_bytes']} | "
            f"{row['decode_peak_bytes']} | {row['code_surface_statements']} |")
    add("")
    add("## Secondary diagnostic — tokens")
    add("")
    add("R1 is not meant to enter model context during ordinary scanning, so this")
    add("ranks below every column above.")
    add("")
    header = "| codec |" + "".join(f" {name} |" for name in out["tokenizers"])
    add(header)
    add("|---" * (len(out["tokenizers"]) + 1) + "|")
    for name, row in out["codecs"].items():
        add(f"| {name} |" + "".join(f" {row[f'tokens_{t}']} |" for t in out["tokenizers"]))
    add("")
    add("## Reasoning")
    add("")
    for line in out["reasoning"]:
        add(f"- {line}")
    add("")
    add("## Caveat")
    add("")
    add(out["note"])
    add("")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="bench/out")
    args = parser.parse_args()
    out = run(pathlib.Path(args.out))
    print(json.dumps({
        "verdict": out["verdict"],
        "correctness": {n: r["correctness_ok"] for n, r in out["codecs"].items()},
        "bytes_body": {n: r["bytes_body"] for n, r in out["codecs"].items()},
        "decode_ns": {n: round(r["decode_ns_per_batch"]) for n, r in out["codecs"].items()},
        "statements": {n: r["code_surface_statements"] for n, r in out["codecs"].items()},
        "reasoning": out["reasoning"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
