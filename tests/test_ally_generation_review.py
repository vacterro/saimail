"""B-016 review: report canonicality, exact binding, fail-closed approval."""

import dataclasses
import hashlib

import pytest

from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag

CREATED = "2026-09-19T20:00:00Z"


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


def resolved(item, source=None):
    source = source or corpus("o1", "o2", "o3", "c1", "r1")
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


class ReviewerReturning:
    """A fake reviewer that returns one prepared report and counts invocations."""

    def __init__(self, report):
        self.report = report
        self.calls = 0

    def review(self, resolved_advice, source):
        self.calls += 1
        return self.report


def report(item=None, source=None, **overrides):
    item = item or advice()
    source = source or corpus("o1", "o2", "o3", "c1", "r1")
    return ag.SemanticReviewReport(
        candidate_id=ag.ally_candidate_id(item),
        corpus_id=source.corpus_id,
        rubric_version=ag.RUBRIC_VERSION,
        verdicts=verdicts(**overrides),
    )


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def test_every_corpus_backed_resolver_uses_existing_b012_type_state():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    resolved_item = aa.resolve_ally_evidence(item, ag.CorpusEvidenceResolver(source))
    assert isinstance(resolved_item, aa.EvidenceResolvedAllyAdvice)
    assert resolved_item.resolved_refs == tuple(sorted(refs("o1", "o2", "o3", "c1")))


def test_missing_corpus_ref_refuses_and_existence_is_not_support():
    item = advice()
    short = corpus("o1", "o2", "o3")  # c1 absent
    assert error(aa.resolve_ally_evidence, item,
                 ag.CorpusEvidenceResolver(short)).code == aa.ALLY_EVIDENCE_MISSING
    contradictory = ag.ReflectionCorpus(items=(
        ag.ReflectionItem(ref("c1"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.",
                          "The opposite of the candidate statement is what happened.",
                          ref("event-c1")),
        ag.ReflectionItem(ref("o1"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.", "a",
                          ref("event-o1")),
        ag.ReflectionItem(ref("o2"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.", "b",
                          ref("event-o2")),
        ag.ReflectionItem(ref("o3"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.", "c",
                          ref("event-o3")),
    ))
    resolver = ag.CorpusEvidenceResolver(contradictory)
    assert resolver.resolve(ref("c1")) == aa.EXISTS
    assert resolver.resolve(ref("absent")) == aa.MISSING


def test_report_requires_exactly_eight_dimensions():
    item = advice()
    full = report(item)
    assert tuple(entry.dimension for entry in full.verdicts) == ag.DIMENSIONS
    seven = tuple(entry for entry in full.verdicts if entry.dimension != ag.NO_FLATTERY)
    assert error(ag.SemanticReviewReport, full.candidate_id, full.corpus_id,
                 ag.RUBRIC_VERSION, seven).code == ag.ALLY_GEN_REVIEW_DIMENSION_MISSING
    duplicate = full.verdicts + (full.verdicts[0],)
    assert error(ag.SemanticReviewReport, full.candidate_id, full.corpus_id,
                 ag.RUBRIC_VERSION, duplicate).code == ag.ALLY_GEN_REVIEW_DIMENSION_DUPLICATE
    assert error(ag.ReviewVerdict, "EXTRA", ag.PASS, "x").code == (
        ag.ALLY_GEN_REVIEW_DIMENSION_UNKNOWN)


def test_verdict_values_are_only_pass_fail_unknown():
    assert error(ag.ReviewVerdict, ag.NO_FLATTERY, "MAYBE", "x").code == (
        ag.ALLY_GEN_REVIEW_VERDICT_INVALID)
    assert error(ag.ReviewVerdict, ag.NO_FLATTERY, "pass", "x").code == (
        ag.ALLY_GEN_REVIEW_VERDICT_INVALID)
    assert error(ag.ReviewVerdict, ag.NO_FLATTERY, ag.PASS, "").code == ag.ALLY_GEN_BAD_REPORT
    big = "r" * (ag.MAX_RATIONALE_BYTES + 1)
    assert error(ag.ReviewVerdict, ag.NO_FLATTERY, ag.PASS, big).code == (
        ag.ALLY_GEN_REVIEW_RATIONALE_OVERSIZE)


def test_total_rationale_boundary_is_exact_and_accepted():
    # Eight dimensions at the per-dimension maximum sit exactly on the 8192
    # total bound; the total check only refuses a report that exceeds it.
    entries = tuple(
        ag.ReviewVerdict(
            dimension, ag.PASS, "r" * ag.MAX_RATIONALE_BYTES,
            (ref("o1"),) if dimension == ag.OBSERVATION_SUPPORT
            else (ref("c1"),) if dimension == ag.COUNTEREVIDENCE_ADEQUACY
            else ())
        for dimension in ag.DIMENSIONS)
    source = corpus("o1", "o2", "o3", "c1")
    accepted = ag.SemanticReviewReport(ag.ally_candidate_id(advice()), source.corpus_id,
                                       ag.RUBRIC_VERSION, entries)
    assert len(accepted.verdicts) == len(ag.DIMENSIONS)


def test_rubric_version_is_exact():
    item = advice()
    assert error(ag.SemanticReviewReport, ag.ally_candidate_id(item),
                 corpus("o1", "o2", "o3", "c1").corpus_id, "ALLY-REVIEW-2",
                 verdicts()).code == ag.ALLY_GEN_RUBRIC_MISMATCH


def test_review_refs_outside_corpus_refuse():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    outside = ag.ReviewVerdict(ag.OBSERVATION_SUPPORT, ag.PASS,
                               "outside ref", (ref("outside"),))
    entries = tuple(outside if entry.dimension == ag.OBSERVATION_SUPPORT else entry
                    for entry in verdicts())
    wire = ag.SemanticReviewReport(ag.ally_candidate_id(item), source.corpus_id,
                                   ag.RUBRIC_VERSION, entries)
    reviewer = ReviewerReturning(wire)
    assert error(ag.run_semantic_review, resolved(item, source), source,
                 reviewer).code == ag.ALLY_GEN_REVIEW_REF_OUTSIDE_CORPUS
    assert reviewer.calls == 1


def test_candidate_and_corpus_identity_mismatches_refuse():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    proof = resolved(item, source)
    other = advice(inferred="A different inference text.")
    wrong_candidate = ag.SemanticReviewReport(ag.ally_candidate_id(other),
                                              source.corpus_id, ag.RUBRIC_VERSION,
                                              verdicts())
    assert error(ag.run_semantic_review, proof, source,
                 ReviewerReturning(wrong_candidate)).code == (
        ag.ALLY_GEN_REVIEW_CANDIDATE_MISMATCH)
    other_source = corpus("o1", "o2", "o3", "c1", "r1")
    wrong_corpus = ag.SemanticReviewReport(ag.ally_candidate_id(item),
                                           other_source.corpus_id, ag.RUBRIC_VERSION,
                                           verdicts())
    assert error(ag.run_semantic_review, proof, source,
                 ReviewerReturning(wrong_corpus)).code == (
        ag.ALLY_GEN_REVIEW_CORPUS_MISMATCH)


def test_all_pass_mints_the_non_transferable_type_state():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    resolved_item = resolved(item, source)
    reviewer = ReviewerReturning(report(item, source))
    invocation = ag.run_semantic_review(resolved_item, source, reviewer)
    assert reviewer.calls == 1
    assert isinstance(invocation, ag.ReviewInvocationResult)
    reviewed = ag.approve_semantic_review(invocation)
    assert isinstance(reviewed, ag.SemanticallyReviewedAllyAdvice)
    assert reviewed.candidate is resolved_item
    assert reviewed.corpus is source
    assert reviewed.report.candidate_id == ag.ally_candidate_id(item)


def test_any_fail_or_unknown_fails_closed():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    proof = resolved(item, source)
    for dimension in ag.DIMENSIONS:
        failed = error(ag.run_semantic_review, proof, source,
                       ReviewerReturning(report(item, source, **{dimension: ag.FAIL})))
        assert failed.code == ag.ALLY_GEN_REVIEW_REJECTED, dimension
    for dimension in ag.DIMENSIONS:
        uncertain = error(ag.run_semantic_review, proof, source,
                          ReviewerReturning(report(item, source, **{dimension: ag.UNKNOWN})))
        assert uncertain.code == ag.ALLY_GEN_REVIEW_UNCERTAIN, dimension


def test_direct_construction_and_replace_transplant_refuse():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    resolved_item = resolved(item, source)
    wire = report(item, source)
    assert error(ag.ReviewInvocationResult, resolved_item, source,
                 wire).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED
    assert error(ag.SemanticallyReviewedAllyAdvice, resolved_item, source,
                 wire).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED
    invocation = ag.run_semantic_review(resolved_item, source, ReviewerReturning(wire))
    assert error(dataclasses.replace, invocation).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED
    other = advice(inferred="A different inference text.")
    other_proof = resolved(other, source)
    assert error(dataclasses.replace, invocation,
                 candidate=other_proof).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED
    assert error(dataclasses.replace, invocation,
                 corpus=corpus("o1", "o2", "o3", "c1")).code == (
        ag.ALLY_GEN_REVIEW_PROOF_FORGED)
    assert error(dataclasses.replace, invocation,
                 report=report(other, source)).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED
    reviewed = ag.approve_semantic_review(invocation)
    assert error(dataclasses.replace, reviewed).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED
    assert error(dataclasses.replace, reviewed,
                 candidate=other_proof).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED


def test_old_report_cannot_transfer_to_changed_candidate_or_corpus():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    wire = report(item, source)
    changed = advice(inferred="A changed inference text.")
    changed_proof = resolved(changed, source)
    assert error(ag.run_semantic_review, changed_proof, source,
                 ReviewerReturning(wire)).code == ag.ALLY_GEN_REVIEW_CANDIDATE_MISMATCH
    widened = ag.ReflectionCorpus(items=(
        ag.ReflectionItem(ref("c1"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.", "x",
                          ref("event-c1")),
        ag.ReflectionItem(ref("o1"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.", "a",
                          ref("event-o1")),
        ag.ReflectionItem(ref("o2"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.", "b",
                          ref("event-o2")),
        ag.ReflectionItem(ref("o3"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.", "c",
                          ref("event-o3")),
        ag.ReflectionItem(ref("r9"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.", "d",
                          ref("event-r9")),
    ))
    assert error(ag.run_semantic_review, resolved(item, source), widened,
                 ReviewerReturning(wire)).code == ag.ALLY_GEN_REVIEW_CORPUS_MISMATCH


def test_event_regrouping_invalidates_review_proof():
    # Same evidence refs, same content, same timestamps and scope: only the
    # declared event grouping of one artifact changes.  Corpus identity binds
    # EVENT_REF, so the old report, invocation and reviewed state cannot follow.
    item = advice()
    first = corpus("o1", "o2", "o3", "c1", events={"o2": "o1"})
    regrouped = corpus("o1", "o2", "o3", "c1", events={"o2": "o1", "o3": "o1"})
    assert first.corpus_id != regrouped.corpus_id
    resolved_item = resolved(item, first)
    wire = report(item, first)
    invocation = ag.run_semantic_review(resolved_item, first, ReviewerReturning(wire))
    reviewed = ag.approve_semantic_review(invocation)
    assert reviewed.corpus.corpus_id == first.corpus_id
    assert reviewed.report.corpus_id == first.corpus_id
    assert error(ag.run_semantic_review, resolved(item, regrouped), regrouped,
                 ReviewerReturning(wire)).code == ag.ALLY_GEN_REVIEW_CORPUS_MISMATCH
    assert reviewed.corpus.corpus_id != regrouped.corpus_id


def test_report_and_verdicts_are_immutable_values():
    item = advice()
    source = corpus("o1", "o2", "o3", "c1")
    wire = report(item, source)
    with pytest.raises(dataclasses.FrozenInstanceError):
        wire.candidate_id = ag.ally_candidate_id(advice(inferred="changed"))
    with pytest.raises(dataclasses.FrozenInstanceError):
        wire.verdicts[0].verdict = ag.FAIL
    assert wire.verdict_for(ag.NO_FLATTERY) == ag.PASS


def test_reviewer_interface_carries_no_generator_reasoning_parameter():
    import inspect

    parameters = tuple(inspect.signature(
        ag.AllyAdviceSemanticReviewer.review).parameters)
    assert parameters == ("self", "evidence_resolved_advice", "corpus")
    for forbidden in ("reasoning", "chain_of_thought", "cot", "scratchpad"):
        assert forbidden not in parameters
