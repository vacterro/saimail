"""T-9B acceptance: the comparison is fair and the gate can still say no.

Nothing here asserts that the frame wins. It asserts that the two questions are
kept apart, that the baselines carry what they claim to carry, and that the
verdict rule is capable of every outcome.
"""

import json
import pathlib
import re

import pytest

from bench.corpus import CASES
from bench.prose import full_prose, summary_prose, triage_prose
from bench.t9b import THRESHOLDS, WORKLOAD, classify, lowercase_claim_slot, run
from sailang import Record
from sailang.frame import Profile, decode, project

HEX64 = re.compile(r"sha256:[0-9a-f]{64}")


@pytest.fixture(scope="module")
def profile():
    return Profile.load("1")


@pytest.fixture(scope="module")
def records():
    return [Record.create(**case.fields) for case in CASES]


# --------------------------------------------------------------------
# the two questions are kept apart
# --------------------------------------------------------------------


def test_triage_prose_never_carries_a_full_evidence_identity(profile, records):
    # Comparing a frame that says "EV+" against prose that spells out 64 hex
    # characters is comparing different information.
    for record in records:
        assert not HEX64.search(triage_prose(record, profile))


def test_full_prose_carries_every_evidence_identity_in_full(profile, records):
    for record in records:
        evidence = record.get("EV")
        text = full_prose(record)
        if evidence and evidence != "0":
            for ref in evidence.split(","):
                assert ref in text, "full prose must be information-equivalent to the record"
        for field in ("REFUTES", "SUPPORTS", "CON"):
            if record.get(field):
                assert record.get(field) in text


def test_full_prose_carries_provenance_and_time(profile, records):
    for record in records:
        text = full_prose(record)
        assert record.get("CREATED") in text
        assert record.get("SRC") in text
        assert record.claim in text


def test_triage_prose_matches_the_frame_semantics_exactly(profile, records):
    rung_word = {"U0": "unknown", "U1": "unverified", "U2": "supported",
                 "U3": "strongly supported", "U4": "verified"}
    for case, record in zip(CASES, records):
        view = decode(project(record, profile))
        text = triage_prose(record, profile)
        if view.status:
            assert rung_word[view.status] in text
        if view.has_evidence is not None:
            assert ("evidence attached" in text) == view.has_evidence
            assert ("no evidence" in text) == (not view.has_evidence)
        else:
            assert "no evidence applies" in text
        assert ("open the record" in text) == view.claim_open_record
        assert ("refutes another record" in text) == view.refutes
        assert ("falsifiable" in text) == view.falsifiable


def test_human_prose_is_kept_but_never_used_as_an_equivalent_baseline():
    source = pathlib.Path("bench/t9b.py").read_text(encoding="utf-8")
    assert "A3_human_prose" in source
    # It may be measured and reported; it must not appear in the verdict rule.
    rule_region = source[source.index("def classify("):source.index("def render(")]
    assert "A3_human_prose" not in rule_region


# --------------------------------------------------------------------
# the fixed variant defect
# --------------------------------------------------------------------


def test_lowercase_variant_mutates_only_the_claim_slot():
    wire = "F|queue|U2|EV+|QSTALE>RETRY>DUP_EXEC|R"
    mutated = lowercase_claim_slot(wire)
    before, after = wire.split("|"), mutated.split("|")
    assert len(after) == len(before)
    assert after[4] == before[4].lower()
    for index in (0, 1, 2, 3, 5):
        assert after[index] == before[index], (
            "only the claim vocabulary may change; lowercasing the whole line "
            "measured a format nobody proposed"
        )


def test_old_whole_line_lowercase_result_is_not_carried_forward():
    analysis = pathlib.Path("bench/ANALYSIS.md").read_text(encoding="utf-8")
    assert "superseded" in analysis.lower() or "T-9B" in analysis


# --------------------------------------------------------------------
# the gate can say no
# --------------------------------------------------------------------


class _Adapter:
    def __init__(self, name):
        self.name = name


def _metrics(p90):
    return {"a": {"q1_triage": {"C2_frame_v01": {"p90": p90}}}}


def _workload(ratio):
    return {"a": {"20pct": {"ratio_vs_eager_full_prose": ratio}}}


def _aliases(break_even):
    return {"a": {"break_even_repeats_ceiling": break_even}}


@pytest.mark.parametrize("inv,mismatch,nondet,ratio,brk,p90,expected", [
    (1, 0, 0, 0.30, 2, 1.0, "NO_GO"),      # a semantic inversion is fatal
    (0, 1, 0, 0.30, 2, 1.0, "NO_GO"),      # a decode mismatch is fatal
    (0, 0, 1, 0.30, 2, 1.0, "NO_GO"),      # non-determinism is fatal
    (0, 0, 0, 1.00, 2, 1.0, "NO_GO"),      # selective loses to eager
    (0, 0, 0, 1.40, 2, 1.0, "NO_GO"),
    (0, 0, 0, 0.30, 2, 1.0, "GO"),
    (0, 0, 0, 0.80, 2, 1.0, "CONDITIONAL"),   # savings exist but below the bar
    (0, 0, 0, 0.30, 9, 1.0, "CONDITIONAL"),   # alias break-even too far away
    (0, 0, 0, 0.30, 2, 1.5, "CONDITIONAL"),   # p90 regression
])
def test_classification_rule_reaches_every_verdict(inv, mismatch, nondet, ratio, brk, p90, expected):
    assert classify(_metrics(p90), _workload(ratio), _aliases(brk),
                    inv, mismatch, nondet, [_Adapter("a")]) == expected


def test_thresholds_and_workload_are_declared_constants():
    assert THRESHOLDS["workload_open_rate_for_gate"] in WORKLOAD["open_rates"]
    assert 0 < THRESHOLDS["workload_go_below"] < 1
    assert WORKLOAD["messages"] >= 100
    assert 0 < WORKLOAD["escalation_to_record"] <= 1
    source = pathlib.Path("bench/t9b.py").read_text(encoding="utf-8")
    assert "--assert-ratio" not in source
    # The declaration must sit above the measurement, not be computed from it.
    assert source.index("WORKLOAD = {") < source.index("def run(")


# --------------------------------------------------------------------
# output completeness and reproducibility
# --------------------------------------------------------------------


def test_benchmark_produces_complete_output(tmp_path):
    result = run(tmp_path)
    for key in ("corpus_size", "tokenizers", "thresholds", "workload_declaration",
                "templates", "profile", "metrics", "workload", "aliases",
                "semantic", "determinism", "verdict"):
        assert key in result
    assert result["verdict"] in {"GO", "CONDITIONAL", "NO_GO"}
    assert not result["missing_classes"]
    for name in ("t9b_results.csv", "t9b_results.json", "T9B_REPORT.md"):
        path = tmp_path / name
        assert path.is_file() and path.stat().st_size > 0

    payload = json.loads((tmp_path / "t9b_results.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == result["verdict"]
    for adapter in result["tokenizers"]:
        scenarios = payload["workload"][adapter["name"]]
        for rate in WORKLOAD["open_rates"]:
            assert f"{int(rate * 100)}pct" in scenarios

    report = (tmp_path / "T9B_REPORT.md").read_text(encoding="utf-8")
    for heading in ("Q1", "Q2", "Q3", "Q4", "Tokenizer caveat"):
        assert heading in report


def test_benchmark_is_reproducible(tmp_path):
    first = run(tmp_path / "a")
    second = run(tmp_path / "b")
    assert first["metrics"] == second["metrics"]
    assert first["workload"] == second["workload"]
    assert first["aliases"] == second["aliases"]
    assert (tmp_path / "a" / "t9b_results.csv").read_bytes() == (
        tmp_path / "b" / "t9b_results.csv").read_bytes()


def test_summary_level_is_derived_from_the_record_not_invented(records):
    for record in records:
        assert record.claim in summary_prose(record)
