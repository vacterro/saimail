"""T-14 acceptance: the selector reads R1 only, and never silently drops.

The hard requirement is asymmetric and stated in the source: a false ignore is
the expensive failure. Everything else is a preference.
"""

import ast
import json
import pathlib

import pytest

from bench.selector_corpus import CASES, INTEREST
from bench.selector_run import run
from saimail.acceptance import ProfileRegistry
from saimail.selector import DEFER, IGNORE, OPEN_R2, OPEN_R3, RULES, Interest, depth, select
from sailang import Record
from sailang.frame import Batch, Profile, decode, project_batch


@pytest.fixture(scope="module")
def profile():
    return Profile.load("1")


def accepted(profile):
    """The receiver's acceptance capability, minted as a receiver would."""
    return ProfileRegistry.with_profiles(profile).resolve(profile.id)


@pytest.fixture(scope="module")
def views(profile):
    records = [Record.create(**case.fields) for case in CASES]
    container = project_batch(records, profile).render()
    return [decode(frame) for frame in Batch.parse(container, accepted(profile)).frames]


# --------------------------------------------------------------------
# the corpus declares its own truth
# --------------------------------------------------------------------


def test_every_fixture_declares_truth_and_a_reason():
    for case in CASES:
        assert case.truth in (IGNORE, DEFER, OPEN_R2, OPEN_R3), case.name
        assert case.why.strip(), f"{case.name} has no stated reason"
        assert case.klass


def test_the_corpus_covers_the_stress_classes():
    required = {
        "relevant_known", "irrelevant_known", "unknown_atom", "ambiguous_prose",
        "contradiction", "hypothesis", "goal_value", "warning", "repeated_topic",
        "novel_discovery", "same_topic_relation", "blocked_vs_blocker",
    }
    present = {case.klass for case in CASES}
    assert required <= present, f"missing selection classes: {sorted(required - present)}"


def test_truth_is_not_all_one_verdict():
    verdicts = {case.truth for case in CASES}
    assert verdicts == {IGNORE, DEFER, OPEN_R2, OPEN_R3}, (
        "a corpus whose truth is one verdict cannot measure a selector"
    )


# --------------------------------------------------------------------
# the selector sees R1 and nothing else
# --------------------------------------------------------------------


def test_selector_refuses_anything_that_is_not_a_typed_view(profile):
    for wrong in ("F|queue|U2|EV+|RETRY|-", 42, None,
                  Record.create(KIND="G", SRC="HUMAN:a", SUBJ="queue",
                                CLAIM="be simpler", CREATED="2026-09-17T08:41:00Z")):
        with pytest.raises(TypeError):
            select(wrong, INTEREST)


def test_selector_module_imports_only_the_typed_view():
    tree = ast.parse(pathlib.Path("saimail/selector.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "dataclasses", "typing", "sailang"}
    source = pathlib.Path("saimail/selector.py").read_text(encoding="utf-8")
    for forbidden in ("Record", "full_prose", "canonical_text", "requests", "urllib"):
        assert forbidden not in source, f"the selector must not reach for {forbidden}"


def test_selector_emits_only_the_declared_verdicts(views):
    for view in views:
        assert select(view, INTEREST).verdict in (IGNORE, DEFER, OPEN_R2, OPEN_R3)


def test_promote_is_not_implemented_yet():
    import saimail.selector as module

    assert not hasattr(module, "PROMOTE")
    assert "PROMOTE" not in {rule for rule, _ in RULES}


def test_selection_is_deterministic(views):
    first = [select(view, INTEREST) for view in views]
    second = [select(view, INTEREST) for view in views]
    assert first == second


def test_rules_are_declared_in_the_source_above_the_function():
    source = pathlib.Path("saimail/selector.py").read_text(encoding="utf-8")
    assert source.index("RULES = (") < source.index("def select(")


# --------------------------------------------------------------------
# the asymmetric requirement
# --------------------------------------------------------------------


def test_nothing_relevant_is_silently_ignored(views):
    missed = [
        (case.name, case.truth, case.why)
        for case, view in zip(CASES, views)
        if select(view, INTEREST).verdict == IGNORE and depth(case.truth) > 0
    ]
    assert not missed, f"false ignores, the expensive failure: {missed}"


def test_an_unreadable_token_is_never_ignored(views):
    for case, view in zip(CASES, views):
        if view.has_unknown_atoms:
            assert select(view, INTEREST).verdict != IGNORE, case.name


def test_a_claim_the_frame_could_not_carry_is_never_ignored(views):
    for case, view in zip(CASES, views):
        if view.claim_open_record:
            assert select(view, INTEREST).verdict != IGNORE, case.name


def test_a_narrower_interest_never_turns_an_unknown_into_an_ignore(views):
    narrow = Interest.of(atoms=set(), subjects=set())
    for view in views:
        if view.has_unknown_atoms or view.claim_open_record:
            assert select(view, narrow).verdict != IGNORE


def test_a_relevant_contradiction_goes_all_the_way_to_the_record(views):
    for case, view in zip(CASES, views):
        if case.klass == "contradiction" and case.truth == OPEN_R3:
            assert select(view, INTEREST).verdict == OPEN_R3, case.name


# --------------------------------------------------------------------
# the run reports what actually happened
# --------------------------------------------------------------------


def test_selector_run_reports_measured_behaviour(tmp_path):
    result = run(tmp_path)
    counts = result["counts"]
    assert counts["r1_scanned"] == len(CASES)
    assert (counts["r2_opened"] + counts["r3_opened"] + counts["ignored"]
            + counts["deferred"]) == len(CASES)
    assert 0.0 <= counts["actual_open_rate"] <= 1.0
    assert result["errors"]["false_ignore_count"] == 0
    for key in ("false_open_count", "under_open_count"):
        assert key in result["errors"]
    assert result["selector_ns_per_message"] > 0
    assert result["error_costs"]["order"].startswith("FALSE_IGNORE")
    for artifact in ("selector_results.json", "SELECTOR_REPORT.md"):
        assert (tmp_path / artifact).is_file()
    payload = json.loads((tmp_path / "selector_results.json").read_text(encoding="utf-8"))
    assert payload["counts"] == counts
    report = (tmp_path / "SELECTOR_REPORT.md").read_text(encoding="utf-8")
    assert "false ignore" in report
    assert "actual open rate" in report


def test_open_rates_are_measured_not_declared():
    source = pathlib.Path("bench/selector_run.py").read_text(encoding="utf-8")
    for assumed in ("0.05", "0.20", "0.50", "5%", "20%", "50%"):
        assert f"open_rate = {assumed}" not in source
    assert "actual_open_rate" in source


def test_error_costs_are_reported_separately_not_collapsed(tmp_path):
    result = run(tmp_path)
    errors = result["errors"]
    assert set(errors) >= {"false_ignore_count", "false_open_count", "under_open_count"}
    assert "score" not in errors and "total" not in errors, (
        "collapsing asymmetric errors into one number needs a calibration that does not exist"
    )


def test_boundary_refusals_are_measured(tmp_path):
    refusals = run(tmp_path)["boundary_refusals"]
    assert refusals["stale_profile"] == "PROFILE_MISMATCH"
    assert refusals["malformed_frame_container"] == "BAD_BATCH"
    assert refusals["malformed_frame_decode"] == "BAD_FRAME"
    assert refusals["forged_frame_binding"] == "UNVERIFIED_BINDING"
