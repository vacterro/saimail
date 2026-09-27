"""B-016 corrective: the reviewer invocation is the mint boundary.

RED controls for T-62 / D-048: a caller-constructed ``SemanticReviewReport``
is data and can never mint the reviewed type-state; one actual
``reviewer.review`` invocation is required; and required evidence-bearing
dimensions cannot ``PASS`` with an evidence-free report.
"""

import hashlib

import pytest

from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag

CREATED = "2026-09-19T20:00:00Z"
HUMAN = "human-id:sha256:" + "0" * 64


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode()).hexdigest()


def refs(*tags):
    return tuple(sorted(ref(tag) for tag in tags))


def corpus(*tags, events=None):
    events = events or {}
    return ag.ReflectionCorpus(items=tuple(
        ag.ReflectionItem(
            evidence_ref=ref(tag),
            source_domain=ag.PROJECT_OPERATIONAL,
            observed_at=CREATED,
            observed_scope="One project queue.",
            content=f"Operational evidence for {tag}.",
            event_ref=ref("event-" + events.get(tag, tag)),
        )
        for tag in tags
    ))


def advice(**changes):
    values = {
        "created": CREATED,
        "work_context": "Generation gate work.",
        "observed_scope": "Three decisions in one project queue.",
        "observed": (
            aa.AdviceObservation("Recovery paths were added after failures.", refs("o1", "o2")),
            aa.AdviceObservation("Scope notes were added before review.", refs("o3")),
        ),
        "inferred": "The queue may benefit from one reversible review pass.",
        "guidance_mode": aa.CONSIDER_CHANGE,
        "suggested": "Consider one reversible pass before the next release.",
        "counterevidence": (
            aa.AdviceCounterevidence("Later reviews closed without findings.", refs("c1")),
        ),
        "uncertainty": "This small sample may be specific to one release window.",
    }
    values.update(changes)
    return aa.AllyAdvice(**values)


def resolved(item=None, source=None):
    item = item or advice()
    source = source or corpus("o1", "o2", "o3", "c1")
    return aa.resolve_ally_evidence(item, ag.CorpusEvidenceResolver(source))


def verdicts(**overrides):
    built = []
    for dimension in ag.DIMENSIONS:
        evidence_refs = (
            (ref("o1"),) if dimension == ag.OBSERVATION_SUPPORT
            else (ref("c1"),) if dimension == ag.COUNTEREVIDENCE_ADEQUACY
            else ())
        built.append(ag.ReviewVerdict(
            dimension=dimension,
            verdict=overrides.get(dimension, ag.PASS),
            rationale=f"{dimension} rationale.",
            evidence_refs=evidence_refs,
        ))
    return tuple(built)


def report(item=None, source=None, **overrides):
    item = item or advice()
    source = source or corpus("o1", "o2", "o3", "c1")
    return ag.SemanticReviewReport(
        candidate_id=ag.ally_candidate_id(item),
        corpus_id=source.corpus_id,
        rubric_version=ag.RUBRIC_VERSION,
        verdicts=verdicts(**overrides),
    )


class ReviewerReturning:
    def __init__(self, report):
        self.report = report
        self.calls = 0

    def review(self, resolved_advice, source):
        self.calls += 1
        return self.report


class ExplodingReviewer:
    def __init__(self):
        self.calls = 0

    def review(self, resolved_advice, source):
        self.calls += 1
        raise RuntimeError("reviewer unavailable")


class RawReportReviewer:
    def __init__(self):
        self.calls = 0

    def review(self, resolved_advice, source):
        self.calls += 1
        return {"verdicts": "not a report"}


class CountingGenerator:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def generate(self, source):
        self.calls += 1
        return self.result


def outcome(source, generator, reviewer):
    return ag.generate_reviewed_ally_advice(source, generator, reviewer)


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def test_plain_report_is_data_not_review_proof():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    wire = report(item, source)
    assert wire.verdict_for(ag.OBSERVATION_SUPPORT) == ag.PASS
    assert error(ag.approve_semantic_review, wire).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED
    assert error(ag.SemanticallyReviewedAllyAdvice, resolved(item, source), source,
                 wire).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED


def test_reviewer_invocation_alone_mints_the_proof():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    reviewer = ReviewerReturning(report(item, source))
    invocation = ag.run_semantic_review(resolved(item, source), source, reviewer)
    assert reviewer.calls == 1
    assert isinstance(invocation, ag.ReviewInvocationResult)
    assert invocation.report is reviewer.report
    reviewed = ag.approve_semantic_review(invocation)
    assert isinstance(reviewed, ag.SemanticallyReviewedAllyAdvice)


def test_approved_outcome_uses_exactly_one_invocation():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    generator = CountingGenerator(ag.GeneratorResult.of(item))
    reviewer = ReviewerReturning(report(item, source))
    result = outcome(source, generator, reviewer)
    assert result.status == ag.APPROVED
    assert generator.calls == 1
    assert reviewer.calls == 1
    assert isinstance(result.reviewed, ag.SemanticallyReviewedAllyAdvice)


def test_no_advice_never_reaches_the_reviewer_or_the_mint():
    source = corpus("o1", "o2", "o3", "c1")
    generator = CountingGenerator(ag.GeneratorResult.no_advice())
    reviewer = ReviewerReturning(report(source=source))
    result = outcome(source, generator, reviewer)
    assert result.status == ag.NO_ADVICE
    assert result.reviewed is None
    assert generator.calls == 1
    assert reviewer.calls == 0


def test_pre_review_rejection_never_invokes_the_reviewer():
    source = corpus("o1", "o2", "o3", "c1")
    outside = advice(observed=(
        aa.AdviceObservation("Uses an outside ref.", refs("o1", "o2")),
        aa.AdviceObservation("Also outside.", refs("outside")),
    ))
    reviewer = ReviewerReturning(report(outside, source))
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(outside)), reviewer)
    assert result.status == ag.REJECTED
    assert reviewer.calls == 0


def test_reviewer_fault_and_bad_return_mint_nothing():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    resolved_item = resolved(item, source)
    exploding = ExplodingReviewer()
    assert error(ag.run_semantic_review, resolved_item, source,
                 exploding).code == ag.ALLY_GEN_REVIEWER_ERROR
    assert exploding.calls == 1
    raw = RawReportReviewer()
    assert error(ag.run_semantic_review, resolved_item, source,
                 raw).code == ag.ALLY_GEN_BAD_REPORT
    assert raw.calls == 1


def test_approval_requires_an_invocation_proof_type():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    wire = report(item, source)
    assert error(ag.approve_semantic_review, resolved(item, source)).code == (
        ag.ALLY_GEN_REVIEW_PROOF_FORGED)
    assert error(ag.approve_semantic_review, wire).code == (
        ag.ALLY_GEN_REVIEW_PROOF_FORGED)
    assert error(ag.approve_semantic_review, None).code == (
        ag.ALLY_GEN_REVIEW_PROOF_FORGED)


def test_observation_support_pass_requires_one_corpus_ref():
    assert error(ag.ReviewVerdict, ag.OBSERVATION_SUPPORT, ag.PASS,
                 "no ref cited").code == ag.ALLY_GEN_REVIEW_EVIDENCE_REQUIRED
    accepted = ag.ReviewVerdict(ag.OBSERVATION_SUPPORT, ag.PASS,
                                "cites one ref", (ref("o1"),))
    assert accepted.evidence_refs == (ref("o1"),)
    orphan = ag.ReviewVerdict(ag.OBSERVATION_SUPPORT, ag.PASS,
                              "cites one ref", (ref("outside"),))
    assert orphan.evidence_refs == (ref("outside"),)


def test_counterevidence_adequacy_pass_requires_one_corpus_ref():
    assert error(ag.ReviewVerdict, ag.COUNTEREVIDENCE_ADEQUACY, ag.PASS,
                 "no ref cited").code == ag.ALLY_GEN_REVIEW_EVIDENCE_REQUIRED
    accepted = ag.ReviewVerdict(ag.COUNTEREVIDENCE_ADEQUACY, ag.PASS,
                                "cites one ref", (ref("c1"),))
    assert accepted.evidence_refs == (ref("c1"),)


def test_the_pre_fix_zero_evidence_report_is_unconstructible():
    # RED-2: before D-048 every dimension could PASS with evidence_refs = ()
    # and the report was approved; now the report itself refuses to exist
    # without the required citations.
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    with pytest.raises(SailangError) as caught:
        ag.SemanticReviewReport(
            ag.ally_candidate_id(item), source.corpus_id, ag.RUBRIC_VERSION,
            tuple(ag.ReviewVerdict(d, ag.PASS, f"{d} rationale.")
                  for d in ag.DIMENSIONS))
    assert caught.value.code == ag.ALLY_GEN_REVIEW_EVIDENCE_REQUIRED


def test_prose_dimensions_may_stay_evidence_free():
    for dimension in (ag.SCOPE_DISCIPLINE, ag.NO_MOTIVE_INFERENCE, ag.NO_FLATTERY,
                      ag.NO_COMPLIANCE_PRESSURE, ag.UNCERTAINTY_ADEQUACY,
                      ag.RECIPIENT_AGENCY):
        entry = ag.ReviewVerdict(dimension, ag.PASS, "candidate prose only.")
        assert entry.evidence_refs == ()
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    reviewed = ag.approve_semantic_review(
        ag.run_semantic_review(resolved(item, source), source,
                               ReviewerReturning(report(item, source))))
    assert isinstance(reviewed, ag.SemanticallyReviewedAllyAdvice)


def test_evidence_ref_outside_corpus_still_refuses():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    outside = ag.ReviewVerdict(ag.COUNTEREVIDENCE_ADEQUACY, ag.PASS,
                               "outside ref", (ref("outside"),))
    entries = tuple(outside if entry.dimension == ag.COUNTEREVIDENCE_ADEQUACY else entry
                    for entry in verdicts())
    wire = ag.SemanticReviewReport(ag.ally_candidate_id(item), source.corpus_id,
                                   ag.RUBRIC_VERSION, entries)
    assert error(ag.run_semantic_review, resolved(item, source), source,
                 ReviewerReturning(wire)).code == ag.ALLY_GEN_REVIEW_REF_OUTSIDE_CORPUS


def test_fail_and_unknown_still_fail_closed_without_retry():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    for verdict in (ag.FAIL, ag.UNKNOWN):
        generator = CountingGenerator(ag.GeneratorResult.of(item))
        reviewer = ReviewerReturning(report(item, source, **{ag.NO_FLATTERY: verdict}))
        result = outcome(source, generator, reviewer)
        assert result.status == ag.REJECTED
        assert result.reviewed is None
        assert generator.calls == 1
        assert reviewer.calls == 1


def test_generated_private_adapter_needs_invocation_minted_state():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    wire = report(item, source)
    resolved_item = resolved(item, source)
    assert error(ag.ReviewInvocationResult, resolved_item, source,
                 wire).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED
    assert error(ag.reviewed_ally_to_human_private, resolved_item,
                 recipient_human_id=HUMAN).code == ag.ALLY_GEN_PRIVATE_PROOF_REQUIRED
    reviewed = ag.approve_semantic_review(
        ag.run_semantic_review(resolved_item, source, ReviewerReturning(wire)))
    letter = ag.reviewed_ally_to_human_private(reviewed, recipient_human_id=HUMAN)
    assert letter.subject == aa.ALLY_ADVICE_SUBJECT
    assert letter.body.encode() == item.render()
