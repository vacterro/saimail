"""T-33 acceptance: the lab tells a single response from repeated semantic behaviour (D-025)."""

from __future__ import annotations

import hashlib
import io
import json
import pathlib
import urllib.error

import pytest

from lab import experiment_class as ec
from lab import saifren_population as pop
from lab import saifren_run as lab
from lab import stability as st
from lab import stability_run as sr
from sailang.frame import Profile
from tests.test_lab_contract import (ALLOWED_CALL_KEYS, KEY, THOUGHT, FakeResponse, all_keys,
                                     completion, written)
from tests.test_lab_contract import _population as population_of

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORTED = {"SAIFREN": "vendor/one", "beta/big": "beta/one"}
FAIL = object()

CORRECT = {
    "S1.evidence_absent": "Q1: NO\nQ2: NO\nQ3: NO",
    "S1.contradiction": "Q1: YES\nQ2: NO\nQ3: YES",
    "S4.ev0_is_not_weak": "ANSWER: NO",
    "S3.mailbox": "M1: OPEN\nM2: DEFER\nM3: OPEN\nM4: IGNORE",
}


def unit_of(prompt):
    if "M1:" in prompt:
        return "S3.mailbox"
    if "EV:0 on a claim means exactly one thing" in prompt:
        return "S4.ev0_is_not_weak"
    if "Must the canonical record be opened" in prompt:
        return "S1.contradiction"
    if "mean the claim is false" in prompt:
        return "S1.evidence_absent"
    return None


class ScriptedOpener:
    """Answers per requested model and per repeat: the n-th time that model sees that prompt."""

    def __init__(self, script=None, reported=REPORTED):
        self.script = script or {}
        self.reported = reported
        self.seen = {}
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        body = json.loads(request.data.decode("utf-8"))
        model, prompt = body["model"], body["messages"][0]["content"]
        key = (model, hashlib.sha256(prompt.encode("utf-8")).hexdigest())
        repeat = self.seen[key] = self.seen.get(key, 0) + 1
        unit = unit_of(prompt)
        content = self.script.get((model, unit, repeat), CORRECT.get(unit, "OK"))
        if content is FAIL:
            raise urllib.error.HTTPError("http://x", 503, "upstream overloaded", {},
                                         io.BytesIO(b"{}"))
        payload = completion(content, model=self.reported[model])
        payload["usage"]["prompt_tokens"] = 3000
        return FakeResponse(payload)


def run(tmp_path, opener, population=None):
    transport = lab.HttpTransport(KEY, opener=opener, timeout=1)
    return sr.run(tmp_path, dry_run=False, api_key=KEY, transport=transport,
                  population=population or population_of())


def findings(result, kind):
    return result["fragility"][kind]


def row(result, model, scenario):
    return next(r for r in result["distributions"]
                if r["model"] == model and r["scenario"] == scenario)


# ------------------------------------------------ registered before measured


def test_the_registration_file_is_the_plan_in_code():
    stored = json.loads((ROOT / "lab" / st.REGISTRATION_FILE).read_text(encoding="utf-8"))
    declared = sr.declared_registration(Profile.load("1"))
    assert stored["registration"] == declared
    assert stored["digest"] == st.digest(declared)
    assert declared["repeats"] == st.REPEATS == 3
    assert [(c["case"], c["unit_id"]) for c in declared["cases"]] == [
        ("FACTUAL_UNVERIFIED", "S1.evidence_absent"), ("EV0_ATTACHMENT", "S4.ev0_is_not_weak"),
        ("OPEN_VERSUS_DEFER", "S3.mailbox"), ("RELATION_CONTRADICTION", "S1.contradiction")]
    assert declared["budget"] == {"experiment_calls": 24, "discovery_reserve": 8,
                                  "max_calls": 32}
    assert st.MAX_CALLS == st.EXPERIMENT_CALLS + pop.DISCOVERY_RESERVE


def test_raising_the_repeat_count_after_the_fact_is_refused_before_any_call(tmp_path,
                                                                           monkeypatch):
    monkeypatch.setattr(st, "REPEATS", 4)
    opener = ScriptedOpener()
    with pytest.raises(SystemExit) as refused:
        run(tmp_path, opener)
    assert "REGISTRATION_MISMATCH" in str(refused.value)
    assert opener.requests == []
    assert list(tmp_path.iterdir()) == []


def test_a_missing_registration_refuses_and_an_existing_one_is_never_overwritten(tmp_path,
                                                                                monkeypatch):
    with pytest.raises(SystemExit) as missing:
        sr.run(tmp_path, dry_run=True, registration_path=tmp_path / "absent.json")
    assert "REGISTRATION_MISSING" in str(missing.value)
    existing = tmp_path / "registered.json"
    sr.register(Profile.load("1"), path=existing)
    before = existing.read_bytes()
    # identical bytes converge idempotently (T-42/C2): a retry never rewrites
    # the winner, and it is not an error to ask again for the same plan
    sr.register(Profile.load("1"), path=existing)
    assert existing.read_bytes() == before
    # a different plan may never take this name
    monkeypatch.setattr(sr, "declared_registration", lambda profile: {"changed": "plan"})
    with pytest.raises(SystemExit) as again:
        sr.register(Profile.load("1"), path=existing)
    assert "REGISTRATION_EXISTS" in str(again.value)
    assert existing.read_bytes() == before


def test_the_order_interleaves_rounds_cases_and_participants():
    steps = st.plan((("A", "SAIFREN"), ("B", "beta/big")), st.cases(Profile.load("1")))
    assert len(steps) == 24
    assert [s.repeat for s in steps[:8]] == [1] * 8
    assert [s.role for s in steps[:4]] == ["A", "B", "A", "B"]
    assert [s.case for s in steps[:8:2]] == [label for label, _ in st.CASES]


def test_a_dry_run_calls_nothing_and_plans_the_registered_sample(tmp_path, monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("a dry run opened a connection")
    monkeypatch.setattr(lab.urllib.request, "urlopen", refuse)
    result = sr.run(tmp_path, dry_run=True)
    assert result["live_calls"] == 0 and result["planned_experiment_calls"] == 24
    assert all(c["status"] == "NOT_RUN" for c in result["calls"])
    assert result["experiment_class"]["experiment_class"] == ec.NOT_MEASURED
    assert not list(tmp_path.glob("STABILITY_REPORT_*.md"))


# ------------------------------------------------ distributions, not verdicts


def test_stable_answers_give_distributions_and_no_finding(tmp_path):
    result = run(tmp_path, ScriptedOpener())
    assert result["live_calls"] == result["experiment_calls"] == 24
    assert len(result["distributions"]) == 8
    for model in ("vendor/one", "beta/one"):
        for scenario in ("S1.evidence_absent", "S4.ev0_is_not_weak", "S1.contradiction"):
            assert row(result, model, scenario)["verdicts"]["PASS"] == 3
        mailbox = row(result, model, "S3.mailbox")
        assert mailbox["attention"]["M1"]["EXACT"] == 3
        assert mailbox["protocol_version"] == lab.PROTOCOL_VERSION
    assert all(rows == [] for rows in result["fragility"].values())
    assert result["experiment_class"]["experiment_class"] == ec.SAIFREN_EXTERNAL_COMPARATOR


def test_model_variance_is_named_for_the_participant_that_varied(tmp_path):
    script = {("SAIFREN", "S3.mailbox", 2): "M1: DEFER\nM2: DEFER\nM3: OPEN\nM4: IGNORE"}
    result = run(tmp_path, ScriptedOpener(script))
    (variance,) = findings(result, st.MODEL_VARIANCE)
    assert (variance["model"], variance["route"], variance["scenario"], variance["boundary"]) == \
        ("vendor/one", "SAIFREN", "S3.mailbox", "M1")
    assert variance["answers"] == {"DEFER": 1, "OPEN": 2}
    assert row(result, "vendor/one", "S3.mailbox")["attention"]["M1"]["UNDER_OPEN"] == 1
    assert findings(result, st.CROSS_MODEL_DISAGREEMENT) == []
    assert findings(result, st.PROTOCOL_HOTSPOT) == []


def test_cross_model_disagreement_needs_each_participant_stable(tmp_path):
    script = {("beta/big", "S4.ev0_is_not_weak", n): "ANSWER: YES" for n in (1, 2, 3)}
    result = run(tmp_path, ScriptedOpener(script))
    (disagreement,) = findings(result, st.CROSS_MODEL_DISAGREEMENT)
    assert disagreement["stable_answers"] == {"beta/one": "YES", "vendor/one": "NO"}
    assert findings(result, st.MODEL_VARIANCE) == []
    assert findings(result, st.PROTOCOL_HOTSPOT) == [], "one participant failing is not a hotspot"
    assert row(result, "beta/one", "S4.ev0_is_not_weak")["verdicts"]["FAIL"] == 3


@pytest.mark.parametrize("failed_repeats,hotspot", [((1, 2), True), ((1,), False)])
def test_a_hotspot_needs_independent_participants_failing_repeatedly(tmp_path, failed_repeats,
                                                                     hotspot):
    wrong = "Q1: YES\nQ2: YES\nQ3: YES"
    script = {(model, "S1.contradiction", n): wrong
              for model in ("SAIFREN", "beta/big") for n in failed_repeats}
    result = run(tmp_path, ScriptedOpener(script))
    hotspots = findings(result, st.PROTOCOL_HOTSPOT)
    if not hotspot:
        assert hotspots == []
        return
    (found,) = hotspots
    assert (found["scenario"], found["boundary"]) == ("S1.contradiction", "Q2")
    assert found["failing_participants"] == {"beta/one": {"failed": 2, "answered": 3},
                                             "vendor/one": {"failed": 2, "answered": 3}}
    assert len(findings(result, st.MODEL_VARIANCE)) == 2, "each participant also varied"


def test_a_transport_failure_is_never_variance_disagreement_or_failure(tmp_path):
    script = {("beta/big", unit, n): FAIL for unit in CORRECT for n in (1, 2, 3)}
    result = run(tmp_path, ScriptedOpener(script))
    assert all(rows == [] for rows in result["fragility"].values())
    refused = [r for r in result["distributions"] if r["route"] == "beta/big"]
    assert refused and all(r["model"] == st.NO_MODEL for r in refused)
    assert all(r["verdicts"]["ERROR"] == 3 and r["verdicts"]["FAIL"] == 0 for r in refused)
    mailbox = next(r for r in refused if r["scenario"] == "S3.mailbox")
    assert mailbox["attention"]["M1"]["UNANSWERED"] == 3
    assert result["experiment_class"]["experiment_class"] == ec.SAIFREN_SINGLE_ROUTE
    assert result["stopped"] is None


def test_a_changed_stimulus_is_never_called_variance():
    unit = dict(st.cases(Profile.load("1")))["EV0_ATTACHMENT"]
    observations = [{"status": "OK", "requested_model": "SAIFREN", "reported_model": "x/one",
                     "unit_id": unit.unit_id, "prompt_sha256": digest, "answers": {"ANSWER": answer}}
                    for digest, answer in (("a" * 64, "NO"), ("b" * 64, "YES"))]
    result = st.fragility(observations, {unit.unit_id: unit})
    assert result[st.MODEL_VARIANCE] == []
    assert [f["finding"] for f in result[st.STIMULUS_CHANGED]] == [st.STIMULUS_CHANGED]


# ------------------------------------------------ the lab contract still holds


def test_every_repeat_carries_the_registered_stimulus(tmp_path):
    result = run(tmp_path, ScriptedOpener())
    registered = {c["unit_id"]: c["prompt_sha256"]
                  for c in sr.declared_registration(Profile.load("1"))["cases"]}
    assert {o["unit_id"]: o["prompt_sha256"] for o in result["observations"]} == registered
    assert result["registration"]["digest"] == json.loads(
        (ROOT / "lab" / st.REGISTRATION_FILE).read_text(encoding="utf-8"))["digest"]


def test_the_artifact_keeps_the_lab_contract_and_reports_opaque_context(tmp_path):
    result = run(tmp_path, ScriptedOpener())
    text = written(tmp_path)
    assert KEY not in text and THOUGHT not in text
    assert result["authority"] == "EXPERIMENT_DATA"
    for call in result["calls"]:
        assert set(call) <= ALLOWED_CALL_KEYS, set(call) - ALLOWED_CALL_KEYS
    klass = result["experiment_class"]
    for field in ("experiment_class", "combo", "observed_combo_members", "external_comparators",
                  "distinct_reported_models", "roster_status"):
        assert field in klass
    per_call = result["opaque_context"]["per_call"]
    assert len(per_call) == 24
    assert all(r["gateway_reported_input"] == 3000 and r["delta"] == 3000 - r["local_estimated_input"]
               for r in per_call)
    assert result["opaque_context"]["visibility"] == "OPAQUE"
    report = pathlib.Path(result["report"]).read_text(encoding="utf-8")
    for section in ("## EXPERIMENT_CLASS", "## STABILITY_RUNS", "## MODEL_VARIANCE",
                    "## CROSS_MODEL_DISAGREEMENT", "## PROTOCOL_HOTSPOT", "## OPAQUE_CONTEXT"):
        assert section in report, section
    assert "external comparator, not a SAIFREN member" in report


def test_nothing_is_scored_ranked_or_merged(tmp_path):
    result = run(tmp_path, ScriptedOpener({("SAIFREN", "S3.mailbox", 2): "M1: DEFER"}))
    forbidden = ("score", "rank", "quality", "winner", "consensus", "majority", "vote", "best")
    for key in all_keys(result):
        assert not any(word in str(key).lower() for word in forbidden), key


def test_a_discovering_run_stays_inside_its_registered_cap(tmp_path):
    class Discovering(lab.HttpTransport):
        def get_json(self, path):
            return {"data": [{"id": "SAIFREN", "owned_by": "combo"},
                             {"id": "beta/big", "owned_by": "beta", "context_length": 10,
                              "capabilities": {}}]}

    transport = Discovering(KEY, opener=ScriptedOpener(), timeout=1)
    result = sr.run(tmp_path, dry_run=False, api_key=KEY, transport=transport, discover=True)
    assert 0 < result["discovery_calls"] <= pop.DISCOVERY_RESERVE
    assert result["live_calls"] <= st.MAX_CALLS
    assert [p["requested"] for p in result["population"]["participants"]] == ["SAIFREN",
                                                                             "beta/big"]
    assert result["experiment_calls"] == 24


# ------------------------------------------------ stored stability runs


STORED = sorted((ROOT / "lab" / "out").glob("stability_live_*.json"))


@pytest.mark.parametrize("path", STORED, ids=[p.stem for p in STORED])
def test_every_stored_stability_run_rederives_from_its_own_evidence(path):
    artifact = json.loads(path.read_text(encoding="utf-8"))
    profile = Profile.load("1")
    registration = json.loads((ROOT / "lab" / st.REGISTRATION_FILE).read_text(encoding="utf-8"))
    assert artifact["registration"]["digest"] == registration["digest"]
    units = {unit.unit_id: unit for _, unit in st.cases(profile)}
    assert st.fragility(artifact["observations"], units) == artifact["fragility"]
    assert st.distributions(artifact["observations"], units,
                            artifact["harness"]["protocol_version"]) == artifact["distributions"]
    assert ec.classify_artifact(artifact) == artifact["experiment_class"]
    index = (ROOT / "lab" / "LATEST.md").read_text(encoding="utf-8")
    row = next(line for line in index.splitlines() if path.name in line)
    assert f"`{artifact['experiment_class']['experiment_class']}`" in row
    counts = {k: len(v) for k, v in artifact["fragility"].items()}
    for finding in (st.MODEL_VARIANCE, st.CROSS_MODEL_DISAGREEMENT, st.PROTOCOL_HOTSPOT):
        assert f"{finding} {counts[finding]}" in row


# ------------------------------------------------ W2: audit wave-2 lifecycle controls


def test_two_same_second_stability_runs_keep_both_artifacts(tmp_path, monkeypatch):
    """W2-003: the stability runner shares the unique-run-id naming contract."""
    frozen = "2026-09-18T12:00:00Z"
    monkeypatch.setattr(lab, "_now", lambda: frozen)
    first = run(tmp_path, ScriptedOpener())
    second = run(tmp_path, ScriptedOpener())
    p1, p2 = pathlib.Path(first["artifact"]), pathlib.Path(second["artifact"])
    assert p1 != p2 and p1.is_file() and p2.is_file()


def test_registration_is_a_single_writer_commit(tmp_path):
    """W2-005: two concurrent registrations produce one winner, no silent overwrite."""
    import threading

    path = tmp_path / "registered.json"
    barrier = threading.Barrier(2)
    outcome = {}

    def writer(name):
        barrier.wait()
        try:
            sr.register(Profile.load("1"), path=path, registered_under={"ticket": name})
            outcome[name] = "WON"
        except SystemExit as exc:
            outcome[name] = str(exc)

    threads = [threading.Thread(target=writer, args=(f"T-{n}",)) for n in (1, 2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    winners = [n for n, v in outcome.items() if v == "WON"]
    assert len(winners) == 1, outcome
    assert "REGISTRATION_EXISTS" in outcome[next(n for n in outcome if n != winners[0])]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["registered_under"]["ticket"] == winners[0], "the loser never touched it"


def test_an_interrupted_registration_is_a_named_refusal(tmp_path):
    """W2-005: a partial write is unreadable evidence, refused by name, never replaced."""
    path = tmp_path / "registered.json"
    path.write_text("{ interrupted", encoding="utf-8")
    with pytest.raises(SystemExit) as refused:
        sr.check_registration(Profile.load("1"), path=path)
    assert "REGISTRATION_UNREADABLE" in str(refused.value)
