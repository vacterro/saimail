"""FG-04A synthetic matrix: telemetry beside the unchanged product gates.

Every case is offline and deterministic. Fake generator/reviewer doubles stand
in for the model corridor; the product B-016 gate itself is unchanged and stays
the only acceptance authority. Reviewer calls are counted, so "reviewer 0" is
proved rather than asserted.
"""

import hashlib
import pathlib

import pytest

from lab import reference_telemetry as rt
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag

ROOT = pathlib.Path(__file__).resolve().parent.parent
CREATED = "2026-09-20T00:00:00Z"


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode()).hexdigest()


def corpus(*tags, events=None):
    events = events or {}
    return ag.ReflectionCorpus(items=tuple(
        ag.ReflectionItem(
            evidence_ref=ref(tag),
            source_domain=ag.PROJECT_OPERATIONAL,
            observed_at=CREATED,
            observed_scope="One project queue.",
            content=f"corpus item {tag}",
            event_ref=ref("event-" + events.get(tag, tag)),
        )
        for tag in tags
    ))


def two_event_corpus():
    return corpus("o1", "o2", "o3", "c1",
                  events={"o1": "A", "o2": "A", "o3": "B", "c1": "B"})


def candidate(observed, counter):
    return aa.AllyAdvice(
        created=CREATED,
        work_context="one project queue",
        observed_scope="one observed scope",
        observed=tuple(aa.AdviceObservation("observed statement.", tuple(sorted(group)))
                       for group in observed),
        inferred="inferred statement.",
        guidance_mode=aa.CONSIDER_CHANGE,
        suggested="suggested statement.",
        counterevidence=tuple(aa.AdviceCounterevidence("counter statement.", tuple(sorted(group)))
                              for group in counter),
        uncertainty="uncertainty statement.",
    )


class FakeGenerator:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def generate(self, source):
        self.calls += 1
        return self.result


class CountingReviewer:
    """Builds one valid PASS report for the exact candidate it is shown."""

    def __init__(self):
        self.calls = 0

    def review(self, resolved, source):
        self.calls += 1
        advice = resolved.advice
        citation = min(source.refs())
        verdicts = tuple(
            ag.ReviewVerdict(
                dimension, ag.PASS, f"{dimension} rationale.",
                (citation,) if dimension in ag.EVIDENCE_REQUIRED_DIMENSIONS else ())
            for dimension in ag.DIMENSIONS
        )
        return ag.SemanticReviewReport(
            ag.ally_candidate_id(advice), source.corpus_id, ag.RUBRIC_VERSION, verdicts)


def product_outcome(source, item):
    """Run the unchanged B-016 orchestration with counted fake halves."""
    generator = FakeGenerator(ag.GeneratorResult.of(item))
    reviewer = CountingReviewer()
    outcome = ag.generate_reviewed_ally_advice(source, generator, reviewer)
    return outcome, generator.calls, reviewer.calls


def forged_clean(source, item):
    """A schema-valid telemetry object that lies CLEAN about a bad candidate."""
    fields = rt.observe_candidate_references(item, source).to_object()
    fields.update(
        known_evidence_ref_count=fields["observed_ref_occurrences"]
        + fields["counterevidence_ref_occurrences"],
        known_event_ref_as_evidence_count=0,
        corpus_id_as_evidence_count=0,
        unknown_canonical_ref_count=0,
        malformed_ref_count=0,
        non_text_ref_count=0,
        unknown_or_invalid_ref_count=0,
        observed_unknown_or_invalid_ref_count=0,
        counterevidence_unknown_or_invalid_ref_count=0,
        known_observed_evidence_ref_count=fields["observed_ref_occurrences"],
        known_observed_distinct_event_count=2,
        event_floor_relation=rt.MET,
        corpus_ref_relation=rt.CLEAN,
        unknown_or_invalid_unique_token_count=0,
        unknown_or_invalid_fingerprints=[],
    )
    return rt.ReferenceTelemetry(**fields)


# --------------------------------------------------------------------
# C1 / 17 — clean two-event candidate
# --------------------------------------------------------------------


def test_c1_clean_two_event_candidate_is_clean_met_and_reaches_review():
    source = two_event_corpus()
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.corpus_ref_relation == rt.CLEAN
    assert result.event_floor_relation == rt.MET
    assert result.unknown_or_invalid_ref_count == 0
    assert result.observed_unknown_or_invalid_ref_count == 0
    assert result.counterevidence_unknown_or_invalid_ref_count == 0
    outcome, generator_calls, reviewer_calls = product_outcome(source, item)
    assert generator_calls == 1
    assert outcome.status == ag.APPROVED
    assert outcome.code is None
    assert reviewer_calls == 1


# --------------------------------------------------------------------
# C2 / 18 — unknown canonical observed ref
# --------------------------------------------------------------------


def test_c2_unknown_observed_ref_is_outside_canonical_and_product_rejects():
    source = two_event_corpus()
    outside = ref("outside-observed")
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"), outside)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.unknown_canonical_ref_count == 1
    assert result.observed_unknown_or_invalid_ref_count == 1
    assert result.corpus_ref_relation == rt.HAS_OUTSIDE_CANONICAL
    assert result.event_floor_relation == rt.NOT_EVALUABLE
    outcome, _, reviewer_calls = product_outcome(source, item)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert reviewer_calls == 0


# --------------------------------------------------------------------
# C3 — unknown canonical counterevidence ref
# --------------------------------------------------------------------


def test_c3_counterevidence_only_violation_is_rejected_by_the_ref_gate():
    source = two_event_corpus()
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"),)),
        ((ref("c1"), ref("outside-counter")),))
    result = rt.observe_candidate_references(item, source)
    assert result.counterevidence_unknown_or_invalid_ref_count == 1
    assert result.observed_unknown_or_invalid_ref_count == 0
    assert result.known_observed_distinct_event_count == 2
    assert result.event_floor_relation == rt.MET
    outcome, _, reviewer_calls = product_outcome(source, item)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert outcome.code != ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS
    assert reviewer_calls == 0


# --------------------------------------------------------------------
# C4 / RED-A — event ref used as evidence
# --------------------------------------------------------------------


def test_c4_event_ref_as_evidence_is_confusion_and_product_rejects():
    source = two_event_corpus()
    event_ref = source.item_for(ref("o1")).event_ref
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"), event_ref)), ((ref("c1"),),))
    naive_outside = sorted({
        value
        for evidence in (*item.observed, *item.counterevidence)
        for value in evidence.evidence_refs
        if value not in source.refs()
    })
    assert naive_outside == [event_ref], "the old metadata would count exactly one"
    result = rt.observe_candidate_references(item, source)
    assert result.known_event_ref_as_evidence_count == 1
    assert result.unknown_canonical_ref_count == 0
    assert result.corpus_ref_relation == rt.HAS_IDENTIFIER_TYPE_CONFUSION
    outcome, _, reviewer_calls = product_outcome(source, item)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert reviewer_calls == 0


# --------------------------------------------------------------------
# C5 — corpus id used as evidence
# --------------------------------------------------------------------


def test_c5_corpus_id_as_evidence_is_confusion_and_product_rejects():
    source = two_event_corpus()
    item = candidate(
        ((ref("o1"), ref("o2")), (source.corpus_id,)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.corpus_id_as_evidence_count == 1
    assert result.unknown_canonical_ref_count == 0
    assert result.corpus_ref_relation == rt.HAS_IDENTIFIER_TYPE_CONFUSION
    outcome, _, reviewer_calls = product_outcome(source, item)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert reviewer_calls == 0


# --------------------------------------------------------------------
# C6 / 21 — one-event clean candidate
# --------------------------------------------------------------------


def test_c6_one_event_clean_candidate_hits_the_event_floor_not_the_ref_gate():
    source = corpus("o1", "o2", "o3", "c1",
                    events={"o1": "A", "o2": "A", "o3": "A", "c1": "A"})
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.corpus_ref_relation == rt.CLEAN
    assert result.event_floor_relation == rt.NOT_MET
    outcome, _, reviewer_calls = product_outcome(source, item)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS
    assert reviewer_calls == 0


# --------------------------------------------------------------------
# C7 / RED-B — unknown ref plus two known events
# --------------------------------------------------------------------


def test_c7_known_two_events_plus_unknown_is_not_evaluable_never_met():
    source = two_event_corpus()
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"), ref("outside-extra"))),
        ((ref("c1"),),))
    known_events = source.event_refs_for(
        {value for evidence in item.observed for value in evidence.evidence_refs})
    assert len(known_events) >= 2, "the naive event count alone would read as met"
    result = rt.observe_candidate_references(item, source)
    assert result.event_floor_relation == rt.NOT_EVALUABLE
    assert result.event_floor_relation != rt.MET
    outcome, _, reviewer_calls = product_outcome(source, item)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert reviewer_calls == 0


# --------------------------------------------------------------------
# 22 / 23 / RED-E — telemetry holds no authority
# --------------------------------------------------------------------


def test_telemetry_never_invokes_generator_or_reviewer():
    source = two_event_corpus()
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),))
    generator = FakeGenerator(ag.GeneratorResult.of(item))
    reviewer = CountingReviewer()
    result = rt.observe_candidate_references(item, source)
    assert rt.serialize_reference_telemetry(result)
    assert generator.calls == 0
    assert reviewer.calls == 0


def test_forged_clean_telemetry_cannot_change_the_product_outcome(monkeypatch):
    source = two_event_corpus()
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"), ref("outside-forged"))),
        ((ref("c1"),),))
    forged = forged_clean(source, item)
    assert forged.corpus_ref_relation == rt.CLEAN
    assert forged.unknown_or_invalid_ref_count == 0
    monkeypatch.setattr(rt, "observe_candidate_references",
                        lambda candidate, corpus: forged)
    assert rt.observe_candidate_references(item, source) is forged
    outcome, _, reviewer_calls = product_outcome(source, item)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert reviewer_calls == 0


def test_product_modules_never_import_the_lab_observer():
    for rel in ("saimail/ally_generation.py", "saimail/ally_advice.py",
                "saimail/project_corpus.py"):
        source = (ROOT / rel).read_text(encoding="utf-8")
        assert "import lab" not in source and "from lab" not in source
        assert "reference_telemetry" not in source


def test_product_outcome_is_identical_with_and_without_telemetry():
    source = two_event_corpus()
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"), ref("outside-compare"))),
        ((ref("c1"),),))
    before = product_outcome(source, item)
    rt.observe_candidate_references(item, source)
    after = product_outcome(source, item)
    assert before == after
    assert before[0].code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS


def test_parsed_observation_refuses_a_non_candidate():
    source = two_event_corpus()
    with pytest.raises(SailangError) as excinfo:
        rt.observe_candidate_references({"OBSERVED": []}, source)
    assert excinfo.value.code == rt.REFERENCE_TELEMETRY_BAD_INPUT
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),))
    with pytest.raises(SailangError) as excinfo:
        rt.observe_candidate_references(item, source.refs())
    assert excinfo.value.code == rt.REFERENCE_TELEMETRY_BAD_CORPUS
