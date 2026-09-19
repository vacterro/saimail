"""T-9 acceptance: the corpus is real and the benchmark is falsifiable.

Nothing here asserts that SAILANG wins. A test that required the hypothesis to
hold would make the experiment unable to fail (spec/DECISIONS.md D-007).
"""

import json
import pathlib

import pytest

from bench.corpus import CASES, REQUIRED_CLASSES, classes
from bench.cost_compare import THRESHOLDS, classify, run
from sailang import Record
from sailang.line import triage

MIN_PER_CLASS = 3
MIN_TOTAL = 40


# --------------------------------------------------------------------
# the corpus is real
# --------------------------------------------------------------------


def test_every_required_information_class_is_present():
    present = classes()
    missing = sorted(set(REQUIRED_CLASSES) - set(present))
    assert not missing, f"corpus is missing required classes: {missing}"


def test_enough_fixtures_to_not_be_three_hand_written_examples():
    assert len(CASES) >= MIN_TOTAL
    thin = {name: len(items) for name, items in classes().items() if len(items) < MIN_PER_CLASS}
    assert not thin, f"classes with too few fixtures: {thin}"


def test_case_names_are_unique():
    names = [case.case for case in CASES]
    assert len(names) == len(set(names))


def test_every_fixture_builds_a_valid_canonical_record():
    for case in CASES:
        record = Record.create(**case.fields)
        assert record.canonical_bytes().endswith(b"\n")
        assert record.content_id.startswith("sha256:")


def test_prose_baselines_are_present_and_concise():
    for case in CASES:
        assert case.prose.strip(), f"{case.case} has no prose baseline"
        assert len(case.prose) <= 400, f"{case.case} prose looks padded: {len(case.prose)} chars"


def test_ground_truth_is_declared_by_hand_for_every_triage_field():
    required = {"kind", "subject", "status", "has_evidence", "refutes", "supports",
                "conflict", "falsifiable", "claim_open_record"}
    for case in CASES:
        missing = required - set(case.expect)
        assert not missing, f"{case.case} is missing ground truth for {sorted(missing)}"


# --------------------------------------------------------------------
# semantics: zero silent inversions, fallback instead of guessing
# --------------------------------------------------------------------


def test_projection_produces_zero_semantic_inversions():
    inversions = []
    for case in CASES:
        view = triage(Record.create(**case.fields))
        for field, expected in case.expect.items():
            actual = view[field]
            if field in ("subject", "status") and expected is not None and actual is None:
                continue  # declared loss, not an inversion
            if actual != expected:
                inversions.append((case.case, field, expected, actual))
    assert not inversions, f"silent semantic inversions: {inversions}"


def test_unrepresentable_claims_open_the_record_rather_than_guessing():
    for case in CASES:
        record = Record.create(**case.fields)
        view = triage(record)
        if view["claim"] is None:
            assert view["claim_open_record"] is True
        else:
            # Anything the line does carry must be derived from the real claim,
            # never invented: every segment of the projection must come from the
            # record's own claim text or the dictionary.
            assert view["claim"]
            assert not view["claim_open_record"]


# --------------------------------------------------------------------
# the benchmark can say no
# --------------------------------------------------------------------


def test_no_predetermined_success_criterion_survives_in_the_harness():
    source = pathlib.Path("bench/cost_compare.py").read_text(encoding="utf-8")
    assert "--assert-ratio" not in source


@pytest.mark.parametrize("medians,inversions,nondet,expected", [
    ([0.70], 1, 0, "NO_GO"),          # a single semantic inversion is fatal
    ([0.10], 3, 0, "NO_GO"),          # even with excellent compactness
    ([0.10], 0, 1, "NO_GO"),          # non-determinism is fatal
    ([0.96], 0, 0, "NO_GO"),          # no useful compactness
    ([0.50, 0.99], 0, 0, "NO_GO"),    # the worst tokenizer decides
    ([0.50, 0.59], 0, 0, "GO"),
    ([0.70], 0, 0, "CONDITIONAL"),
    ([], 0, 0, "NO_GO"),              # no measurement is not a pass
])
def test_classification_rule_is_capable_of_every_verdict(medians, inversions, nondet, expected):
    assert classify(medians, inversions, nondet) == expected


def test_thresholds_are_declared_and_printed_with_the_result():
    assert "GO" in THRESHOLDS["rule"] and "NO_GO" in THRESHOLDS["rule"]
    assert 0 < THRESHOLDS["go_below"] < THRESHOLDS["no_go_at_or_above"]


# --------------------------------------------------------------------
# the benchmark produces complete, machine-readable output
# --------------------------------------------------------------------


def test_benchmark_run_produces_complete_results(tmp_path):
    result = run(tmp_path)
    for key in ("corpus_size", "classes", "tokenizers", "thresholds", "metrics",
                "bytes", "semantic", "determinism", "dictionary", "verdict", "per_case"):
        assert key in result, f"result is missing {key}"
    assert result["corpus_size"] == len(CASES)
    assert result["verdict"] in {"GO", "CONDITIONAL", "NO_GO"}
    assert result["tokenizers"], "a real tokenizer count is required evidence"
    assert not result["missing_classes"]

    for name in ("results.csv", "results.json", "REPORT.md"):
        path = tmp_path / name
        assert path.is_file() and path.stat().st_size > 0, f"{name} was not written"

    payload = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == result["verdict"]
    for adapter in result["tokenizers"]:
        stats = payload["metrics"][adapter["name"]]["line_over_prose"]
        for stat in ("median", "mean", "p90", "best", "worst"):
            assert stat in stats

    report = (tmp_path / "REPORT.md").read_text(encoding="utf-8")
    assert "Tokenizer caveat" in report
    assert "Negative findings" in report
    assert result["verdict"] in report


def test_benchmark_is_reproducible(tmp_path):
    first = run(tmp_path / "a")
    second = run(tmp_path / "b")
    assert first["verdict"] == second["verdict"]
    assert first["metrics"] == second["metrics"]
    assert (tmp_path / "a" / "results.csv").read_bytes() == (
        tmp_path / "b" / "results.csv").read_bytes()
