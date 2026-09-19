"""T-31 acceptance: no live report can confuse an external comparator with a SAIFREN member (D-024)."""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from lab import experiment_class as ec
from lab import saifren_run as lab
from tests.test_lab_contract import KEY, FakeResponse, answer_for, completion
from tests.test_lab_contract import _population as population_of

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "lab" / "out"
COMBO = "SAIFREN"


def call(requested, reported, status="OK", call_id=None):
    return {"call_id": call_id or f"{requested}->{reported}", "requested_model": requested,
            "reported_model": reported, "status": status}


# ------------------------------------------------ the classes


def test_two_members_through_the_alias_and_nothing_else_is_internal():
    klass = ec.classify_calls(COMBO, [call(COMBO, "x/one"), call(COMBO, "y/two")])
    assert klass["experiment_class"] == ec.SAIFREN_INTERNAL
    assert klass["observed_combo_members"] == ["x/one", "y/two"]
    assert klass["external_comparators"] == []
    assert klass["cross_member_claim"] is True


def test_a_member_beside_a_catalog_model_is_an_external_comparator():
    klass = ec.classify_calls(COMBO, [call(COMBO, "x/one"), call("goat/z/three", "z/three")])
    assert klass["experiment_class"] == ec.SAIFREN_EXTERNAL_COMPARATOR
    assert klass["observed_combo_members"] == ["x/one"]
    assert klass["external_comparators"] == ["z/three"]
    assert klass["distinct_reported_models"] == ["x/one", "z/three"]
    assert klass["cross_member_claim"] is False


def test_two_members_plus_an_external_model_is_still_a_comparator_run():
    calls = [call(COMBO, "x/one"), call(COMBO, "y/two"), call("goat/z/three", "z/three")]
    assert ec.classify_calls(COMBO, calls)["experiment_class"] == ec.SAIFREN_EXTERNAL_COMPARATOR


def test_one_member_is_a_single_route_even_when_reached_twice():
    klass = ec.classify_calls(COMBO, [call(COMBO, "x/one"), call(COMBO, "x/one"),
                                      call("goat/x/one", "x/one")])
    assert klass["experiment_class"] == ec.SAIFREN_SINGLE_ROUTE
    assert klass["external_comparators"] == [], "the same model by another route is not a comparator"


def test_pinned_catalog_models_observe_no_member():
    klass = ec.classify_calls(COMBO, [call("goat/x/one", "x/one"), call("or/z/three", "z/three")])
    assert klass["experiment_class"] == ec.SAIFREN_NOT_OBSERVED
    assert klass["observed_combo_members"] == []


def test_an_alias_that_reports_no_model_observes_no_member():
    klass = ec.classify_calls(COMBO, [call(COMBO, COMBO), call(COMBO, COMBO)])
    assert klass["experiment_class"] == ec.SAIFREN_NOT_OBSERVED
    assert klass["distinct_reported_models"] == []
    assert klass["membership_evidence"]["alias_only_answers"] == 2


def test_nothing_answered_is_not_measured():
    calls = [call(COMBO, None, status="ERROR"), call("goat/z", "z/three", status="NOT_RUN")]
    assert ec.classify_calls(COMBO, calls)["experiment_class"] == ec.NOT_MEASURED


def test_a_transport_failure_is_neither_a_member_nor_a_comparator():
    calls = [call(COMBO, "x/one"), call("goat/z/three", None, status="ERROR")]
    klass = ec.classify_calls(COMBO, calls)
    assert klass["experiment_class"] == ec.SAIFREN_SINGLE_ROUTE
    assert klass["external_comparators"] == []


# ------------------------------------------------ evidence, not labels


def test_catalog_eligibility_and_member_labels_are_not_membership_evidence():
    population = {"combo": COMBO, "roster_status": "ROSTER_NOT_EXPOSED", "observed_members": [],
                  "participants": [
                      {"requested": "goat/z/three", "reported_model": "z/three",
                       "member_status": "OBSERVED_COMBO_MEMBER", "source": "CATALOG_ELIGIBLE"}]}
    klass = ec.classify_calls(COMBO, [call("goat/z/three", "z/three")], population)
    assert klass["experiment_class"] == ec.SAIFREN_NOT_OBSERVED
    assert klass["observed_combo_members"] == []


def test_a_membership_probe_in_the_same_run_is_evidence():
    population = {"combo": COMBO, "roster_status": "ROSTER_NOT_EXPOSED",
                  "observed_members": ["x/one"], "participants": []}
    klass = ec.classify_calls(COMBO, [call("goat/x/one", "x/one")], population)
    assert klass["experiment_class"] == ec.SAIFREN_SINGLE_ROUTE
    assert klass["membership_evidence"]["membership_probes"] == ["x/one"]


def test_the_roster_is_not_observable_until_one_is_read():
    assert ec.roster_status(None) == {"roster_status": "NOT_OBSERVABLE",
                                      "roster_status_basis": "NO_POPULATION_RECORD"}
    assert ec.roster_status({"roster_status": "ROSTER_NOT_EXPOSED"})["roster_status"] == \
        "NOT_OBSERVABLE"
    assert ec.roster_status({"roster_status": "ROSTER_OBSERVED"})["roster_status"] == "OBSERVED"


def test_a_historical_run_that_mixed_alias_and_pins_is_refused_not_guessed():
    artifact = {"harness": {"model_alias": COMBO, "route_a": COMBO, "route_b": "goat/z"},
                "calls": [{"status": "OK", "reported_model": "z/three", "call_id": "c1"}]}
    with pytest.raises(ec.UnattributableRun):
        ec.classify_artifact(artifact)


# ------------------------------------------------ the stored runs, classified as they are


EXPECTED_HISTORY = {
    "20260917T105104Z": (ec.SAIFREN_SINGLE_ROUTE, ec.BASIS_HARNESS_ROUTES),
    "20260917T114616Z": (ec.SAIFREN_NOT_OBSERVED, ec.BASIS_HARNESS_ROUTES),
    "20260917T122346Z": (ec.SAIFREN_NOT_OBSERVED, ec.BASIS_HARNESS_ROUTES),
    "20260917T151623Z": (ec.SAIFREN_EXTERNAL_COMPARATOR, ec.BASIS_POPULATION_RECORD),
    "20260917T152012Z": (ec.SAIFREN_EXTERNAL_COMPARATOR, ec.BASIS_POPULATION_RECORD),
}


@pytest.mark.parametrize("stamp", sorted(EXPECTED_HISTORY))
def test_every_stored_run_is_classified_from_its_own_evidence(stamp):
    artifact = json.loads((OUT / f"saifren_live_{stamp}.json").read_text(encoding="utf-8"))
    klass = ec.classify_artifact(artifact)
    assert (klass["experiment_class"], klass["membership_evidence_basis"]) == \
        EXPECTED_HISTORY[stamp]
    assert klass["roster_status"] == "NOT_OBSERVABLE"


def test_runs_four_and_five_name_their_second_participant_honestly():
    for stamp in ("20260917T151623Z", "20260917T152012Z"):
        artifact = json.loads((OUT / f"saifren_live_{stamp}.json").read_text(encoding="utf-8"))
        klass = ec.classify_artifact(artifact)
        assert klass["observed_combo_members"] == ["deepseek/deepseek-v4-flash"]
        assert klass["external_comparators"] == ["MiniMaxAI/MiniMax-M3"]
        assert "MiniMaxAI/MiniMax-M3" not in klass["observed_combo_members"]


def test_the_run_index_states_the_derived_class_of_every_run():
    index = (ROOT / "lab" / "LATEST.md").read_text(encoding="utf-8")
    for stamp, (klass, _) in EXPECTED_HISTORY.items():
        row = next(line for line in index.splitlines()
                   if line.startswith("|") and f"saifren_live_{stamp}.json" in line)
        assert f"`{klass}`" in row, stamp


def test_current_documents_do_not_call_the_comparator_a_member():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "participants discovered from the population" not in readme
    assert "SAIFREN_EXTERNAL_COMPARATOR" in readme
    decisions = (ROOT / "spec" / "DECISIONS.md").read_text(encoding="utf-8")
    assert "## D-024" in decisions
    overclaim = re.compile(r"two (?:distinct )?(?:observed )?SAIFREN members", re.IGNORECASE)
    for doc in ("README.md", "lab/LATEST.md", "lab/saifren_population.py"):
        assert not overclaim.search((ROOT / doc).read_text(encoding="utf-8")), doc


# ------------------------------------------------ every new artifact says it


SIX = ("experiment_class", "combo", "observed_combo_members", "external_comparators",
       "distinct_reported_models", "roster_status")


class ModelOpener:
    """Answers each request as the model the gateway would report for the id it requested."""

    def __init__(self, reported):
        self.reported = reported

    def __call__(self, request, timeout):
        body = json.loads(request.data.decode("utf-8"))
        prompt = body["messages"][0]["content"]
        return FakeResponse(completion(answer_for(prompt), model=self.reported[body["model"]]))


def comparator_run(tmp_path):
    transport = lab.HttpTransport(KEY, timeout=1, opener=ModelOpener(
        {"SAIFREN": "vendor/one", "beta/big": "beta/one"}))
    return lab.run(tmp_path, dry_run=False, api_key=KEY, transport=transport,
                   population=population_of())


def test_every_new_live_artifact_reports_the_six_fields(tmp_path):
    result = comparator_run(tmp_path)
    klass = result["experiment_class"]
    assert all(field in klass for field in SIX)
    assert klass["experiment_class"] == ec.SAIFREN_EXTERNAL_COMPARATOR
    assert klass["external_comparators"] == ["beta/one"]
    assert klass["observed_combo_members"] == ["vendor/one"]
    assert all("requested_model" in c for c in result["calls"])
    on_disk = json.loads(pathlib.Path(result["artifact"]).read_text(encoding="utf-8"))
    assert on_disk["experiment_class"] == klass
    assert ec.classify_artifact(on_disk)["membership_evidence_basis"] == ec.BASIS_CALL_RECORDS


def test_the_report_names_the_class_and_never_promotes_the_comparator(tmp_path):
    result = comparator_run(tmp_path)
    report = pathlib.Path(result["report"]).read_text(encoding="utf-8")
    for label in ("EXPERIMENT_CLASS:", "COMBO:", "OBSERVED_COMBO_MEMBERS:",
                  "EXTERNAL_COMPARATORS:", "DISTINCT_REPORTED_MODELS:", "ROSTER_STATUS:"):
        assert label in report, label
    assert "EXPERIMENT_CLASS: `SAIFREN_EXTERNAL_COMPARATOR`" in report
    routes = {line.split("`")[1]: line for line in report.splitlines()
              if line.startswith("- `") and "call(s)" in line}
    assert "external comparator, not a SAIFREN member" in routes["beta/one"]
    assert "observed SAIFREN member" in routes["vendor/one"]


def test_a_dry_run_is_not_measured(tmp_path):
    result = lab.run(tmp_path, dry_run=True)
    assert result["experiment_class"]["experiment_class"] == ec.NOT_MEASURED
    assert result["experiment_class"]["roster_status"] == "NOT_OBSERVABLE"
