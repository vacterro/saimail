"""B-016 gate: bounded orchestration, fail-closed review, explicit corridor."""

import hashlib
import inspect
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag
from saimail import envelope
from saimail import human_attention as ha
from saimail.sailetter import (
    MODE_STRICT,
    HumanPrivateStore,
    HumanRecipient,
    SoftwareP256Provider,
    human_id,
    seal_human_private,
)

CREATED = "2026-09-19T20:00:00Z"
SENDER_SEAT = "ALLY_AGENT"
SENDER = Ed25519PrivateKey.generate()
PRIMARY = ec.generate_private_key(ec.SECP256R1())
HUMAN = human_id(PRIMARY.public_key())
MARKERS = {
    "observed": "observed-generation-marker-11aa",
    "inferred": "inferred-generation-marker-22bb",
    "counter": "counter-generation-marker-33cc",
    "item": "corpus-item-content-marker-44dd",
}


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode()).hexdigest()


def refs(*tags):
    return tuple(sorted(ref(tag) for tag in tags))


def corpus(*tags, content=None, events=None):
    events = events or {}
    return ag.ReflectionCorpus(items=tuple(
        ag.ReflectionItem(
            evidence_ref=ref(tag),
            source_domain=ag.PROJECT_OPERATIONAL,
            observed_at=CREATED,
            observed_scope="One project queue.",
            content=content or f"{MARKERS['item']} {tag}",
            event_ref=ref("event-" + events.get(tag, tag)),
        )
        for tag in tags
    ))


def advice(**changes):
    values = {
        "created": CREATED,
        "work_context": MARKERS["observed"] + " generation work.",
        "observed_scope": "Three decisions in one project queue.",
        "observed": (
            aa.AdviceObservation(MARKERS["observed"] + " recovery paths were added.",
                                 refs("o1", "o2")),
            aa.AdviceObservation("Scope notes were added before review.", refs("o3")),
        ),
        "inferred": MARKERS["inferred"] + " may describe premature convergence.",
        "guidance_mode": aa.CONSIDER_CHANGE,
        "suggested": "Consider one reversible review pass before the next release.",
        "counterevidence": (
            aa.AdviceCounterevidence(MARKERS["counter"] + " later work self-corrected.",
                                     refs("c1")),
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
    return tuple(
        ag.ReviewVerdict(
            dimension, overrides.get(dimension, ag.PASS),
            f"{dimension} rationale.",
            (ref("o1"),) if dimension == ag.OBSERVATION_SUPPORT
            else (ref("c1"),) if dimension == ag.COUNTEREVIDENCE_ADEQUACY
            else ())
        for dimension in ag.DIMENSIONS
    )


def report(item=None, source=None, **overrides):
    item = item or advice()
    source = source or corpus("o1", "o2", "o3", "c1")
    return ag.SemanticReviewReport(ag.ally_candidate_id(item), source.corpus_id,
                                   ag.RUBRIC_VERSION, verdicts(**overrides))


class CountingGenerator:
    def __init__(self, result):
        self.result = result
        self.calls = 0
        self.scratchpad = "generator-hidden-reasoning-must-not-travel"

    def generate(self, source):
        self.calls += 1
        return self.result


class RawResultGenerator:
    calls = 0

    def generate(self, source):
        self.calls += 1
        return {"kind": ag.CANDIDATE, "advice": advice()}


class ExplodingGenerator:
    calls = 0

    def generate(self, source):
        self.calls += 1
        raise RuntimeError("provider unavailable")


class RecordingReviewer:
    def __init__(self, **overrides):
        self.overrides = overrides
        self.calls = 0
        self.seen = []

    def review(self, resolved_advice, source):
        self.calls += 1
        self.seen.append((resolved_advice, source))
        return report(resolved_advice.advice, source, **self.overrides)


class FullCorpusReviewer(RecordingReviewer):
    """Proves the reviewer sees the full corpus, not generator-selected refs."""

    def review(self, resolved_advice, source):
        assert source.item_for(ref("c1")) is not None
        return super().review(resolved_advice, source)


class ExplodingReviewer:
    calls = 0

    def review(self, resolved_advice, source):
        self.calls += 1
        raise RuntimeError("reviewer unavailable")


class RawReportReviewer:
    calls = 0

    def review(self, resolved_advice, source):
        self.calls += 1
        return {"verdicts": "not a report"}


def outcome(source, generator, reviewer):
    return ag.generate_reviewed_ally_advice(source, generator, reviewer)


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def tree(root):
    root = Path(root)
    if not root.exists():
        return {}
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def registry():
    return envelope.KeyRegistry({SENDER_SEAT: [SENDER.public_key()]})


def recipient():
    return HumanRecipient(human_id=HUMAN, primary_public_key=PRIMARY.public_key())


def test_no_advice_never_invokes_the_reviewer():
    source = corpus("o1", "o2", "o3", "c1")
    generator = CountingGenerator(ag.GeneratorResult.no_advice())
    reviewer = RecordingReviewer()
    result = outcome(source, generator, reviewer)
    assert result.status == ag.NO_ADVICE
    assert result.reviewed is None
    assert result.code is None
    assert generator.calls == 1
    assert reviewer.calls == 0


def test_valid_candidate_uses_exactly_one_call_per_invocation():
    source = corpus("o1", "o2", "o3", "c1")
    generator = CountingGenerator(ag.GeneratorResult.of(advice()))
    reviewer = RecordingReviewer()
    result = outcome(source, generator, reviewer)
    assert result.status == ag.APPROVED
    assert generator.calls == 1
    assert reviewer.calls == 1
    assert isinstance(result.reviewed, ag.SemanticallyReviewedAllyAdvice)


def test_invalid_generator_result_refuses_before_review():
    source = corpus("o1", "o2", "o3", "c1")
    generator = RawResultGenerator()
    reviewer = RecordingReviewer()
    result = outcome(source, generator, reviewer)
    assert result.status == ag.ERROR
    assert result.code == ag.ALLY_GEN_BAD_RESULT
    assert reviewer.calls == 0


def test_outside_corpus_refs_refuse_before_review():
    source = corpus("o1", "o2", "o3", "c1")
    outside_observed = advice(observed=(
        aa.AdviceObservation("Uses an outside ref.", refs("o1", "o2")),
        aa.AdviceObservation("Also outside.", refs("outside")),
    ))
    reviewer = RecordingReviewer()
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(outside_observed)),
                     reviewer)
    assert result.status == ag.REJECTED
    assert result.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert reviewer.calls == 0

    outside_counter = advice(counterevidence=(
        aa.AdviceCounterevidence("Outside counterevidence.", refs("outside")),
    ))
    reviewer = RecordingReviewer()
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(outside_counter)),
                     reviewer)
    assert result.status == ag.REJECTED
    assert result.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert reviewer.calls == 0


def test_one_event_three_artifacts_is_refused_before_review():
    # The one-incident topology: three distinct evidence artifacts, one declared
    # underlying event, and prose that claims repetition.  Artifact count is not
    # event count, so the mechanical pre-review gate refuses and the reviewer is
    # never invoked (RED-D: prompt prose is not authority).
    source = corpus("o1", "o2", "o3", "c1",
                    events={"o2": "o1", "o3": "o1", "c1": "o1"})
    candidate = advice(observed=(
        aa.AdviceObservation("This stalled repeatedly across three artifacts.",
                             refs("o1", "o2")),
        aa.AdviceObservation("The same stall appears again in another artifact.",
                             refs("o3")),
    ), inferred="This may describe a recurring stall.")
    reviewer = RecordingReviewer()
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(candidate)), reviewer)
    assert result.status == ag.REJECTED
    assert result.code == ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS
    assert reviewer.calls == 0
    assert result.reviewed is None


def test_two_events_reach_the_reviewer_and_are_not_auto_approved():
    # A→X, B→X, C→Y: the existing artifact floor holds and support spans two
    # declared events, so the candidate is eligible for semantic review.  The
    # event gate answers recurrence eligibility only, so a FAIL still rejects.
    source = corpus("o1", "o2", "o3", "c1", events={"o2": "o1"})
    failing = RecordingReviewer(**{ag.NO_FLATTERY: ag.FAIL})
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(advice())), failing)
    assert failing.calls == 1
    assert result.status == ag.REJECTED
    assert result.code == ag.ALLY_GEN_REVIEW_REJECTED
    passing = RecordingReviewer()
    approved = outcome(source, CountingGenerator(ag.GeneratorResult.of(advice())), passing)
    assert passing.calls == 1
    assert approved.status == ag.APPROVED


def test_distinct_event_floor_counts_observed_items_only():
    # The counterevidence artifact declares its own separate event, yet the
    # floor measures OBSERVED support: one declared observed event is not
    # eligible, and a counterevidence event never rescues it.
    source = corpus("o1", "o2", "o3", "c1",
                    events={"o2": "o1", "o3": "o1"})
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(advice())),
                     RecordingReviewer())
    assert result.status == ag.REJECTED
    assert result.code == ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS


def test_missing_corpus_ref_refuses_before_review():
    source = corpus("o1", "o2", "o3")  # c1 absent from the supplied corpus
    reviewer = RecordingReviewer()
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(advice())), reviewer)
    assert result.status == ag.REJECTED
    # Membership refuses first: the candidate cannot cite what the corpus does
    # not carry.  The B-012 existence boundary stays the resolver itself,
    # proven directly in the review file (ALLY_EVIDENCE_MISSING).
    assert result.code == ag.ALLY_GENERATED_REF_OUTSIDE_CORPUS
    assert reviewer.calls == 0


def test_provider_exception_is_not_no_advice():
    source = corpus("o1", "o2", "o3", "c1")
    reviewer = RecordingReviewer()
    result = outcome(source, ExplodingGenerator(), reviewer)
    assert result.status == ag.ERROR
    assert result.code == ag.ALLY_GEN_PROVIDER_ERROR
    assert result.status != ag.NO_ADVICE
    assert reviewer.calls == 0


def test_reviewer_exception_and_bad_report_are_errors():
    source = corpus("o1", "o2", "o3", "c1")
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(advice())),
                     ExplodingReviewer())
    assert result.status == ag.ERROR
    assert result.code == ag.ALLY_GEN_REVIEWER_ERROR
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(advice())),
                     RawReportReviewer())
    assert result.status == ag.ERROR
    assert result.code == ag.ALLY_GEN_BAD_REPORT


def test_rejection_never_loops_back_into_the_generator():
    source = corpus("o1", "o2", "o3", "c1")
    generator = CountingGenerator(ag.GeneratorResult.of(advice()))
    reviewer = RecordingReviewer(**{ag.NO_FLATTERY: ag.FAIL})
    result = outcome(source, generator, reviewer)
    assert result.status == ag.REJECTED
    assert result.code == ag.ALLY_GEN_REVIEW_REJECTED
    assert generator.calls == 1
    assert reviewer.calls == 1
    assert result.reviewed is None
    # A fresh explicit invocation is a new run; the rejected run kept no state.
    again = outcome(source, generator, RecordingReviewer())
    assert again.status == ag.APPROVED
    assert generator.calls == 2


@pytest.mark.parametrize("dimension", ag.DIMENSIONS)
def test_any_failed_dimension_blocks_the_letter(dimension):
    source = corpus("o1", "o2", "o3", "c1")
    generator = CountingGenerator(ag.GeneratorResult.of(advice()))
    reviewer = RecordingReviewer(**{dimension: ag.FAIL})
    result = outcome(source, generator, reviewer)
    assert result.status == ag.REJECTED
    assert result.code == ag.ALLY_GEN_REVIEW_REJECTED
    assert result.reviewed is None
    assert generator.calls == 1
    assert reviewer.calls == 1


def test_unknown_fails_closed_and_never_becomes_pass():
    source = corpus("o1", "o2", "o3", "c1")
    reviewer = RecordingReviewer(**{ag.UNCERTAINTY_ADEQUACY: ag.UNKNOWN})
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(advice())), reviewer)
    assert result.status == ag.REJECTED
    assert result.code == ag.ALLY_GEN_REVIEW_UNCERTAIN
    assert result.reviewed is None


def test_one_sided_generator_is_blocked_by_full_corpus_review():
    # The corpus contains a clear contradictory item; the fake generator cites
    # only confirming observations and the reviewer sees the whole corpus.
    source = ag.ReflectionCorpus(items=(
        ag.ReflectionItem(ref("o1"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.",
                          MARKERS["item"] + " confirming observation one.", ref("event-o1")),
        ag.ReflectionItem(ref("o2"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.",
                          MARKERS["item"] + " confirming observation two.", ref("event-o2")),
        ag.ReflectionItem(ref("o3"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.",
                          MARKERS["item"] + " confirming observation three.",
                          ref("event-o3")),
        ag.ReflectionItem(ref("c1"), ag.PROJECT_OPERATIONAL, CREATED, "One queue.",
                          MARKERS["item"] + " clear contradiction of the inference.",
                          ref("event-c1")),
    ))
    one_sided = advice()
    reviewer = FullCorpusReviewer(**{ag.COUNTEREVIDENCE_ADEQUACY: ag.FAIL})
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(one_sided)), reviewer)
    assert result.status == ag.REJECTED
    assert reviewer.calls == 1


@pytest.mark.parametrize("dimension,prose", [
    (ag.NO_MOTIVE_INFERENCE, "You do this because you are afraid of losing control."),
    (ag.NO_FLATTERY, "Your exceptional and brilliant judgement stands out."),
    (ag.NO_COMPLIANCE_PRESSURE, "You need to do this; this is the correct choice."),
    (ag.SCOPE_DISCIPLINE, "This happens in all your projects, always."),
    (ag.UNCERTAINTY_ADEQUACY, "I may be wrong."),
    (ag.RECIPIENT_AGENCY, "A responsible recipient will comply."),
])
def test_semantic_boundaries_are_fake_reviewer_decisions(dimension, prose):
    # The production core does not detect these semantics; the fake candidate
    # carries the suspect prose and the fake reviewer blocks it.  The test
    # proves orchestration behavior only.
    source = corpus("o1", "o2", "o3", "c1")
    candidate = advice(inferred=prose, uncertainty="I may be wrong.")
    reviewer = RecordingReviewer(**{dimension: ag.FAIL})
    result = outcome(source, CountingGenerator(ag.GeneratorResult.of(candidate)), reviewer)
    assert result.status == ag.REJECTED
    assert result.reviewed is None


def test_generator_hidden_reasoning_never_reaches_the_reviewer():
    source = corpus("o1", "o2", "o3", "c1")
    generator = CountingGenerator(ag.GeneratorResult.of(advice()))
    reviewer = RecordingReviewer()
    result = outcome(source, generator, reviewer)
    assert result.status == ag.APPROVED
    resolved_seen, corpus_seen = reviewer.seen[0]
    assert isinstance(resolved_seen, aa.EvidenceResolvedAllyAdvice)
    assert corpus_seen is source
    assert generator.scratchpad not in repr(reviewer.seen)
    assert generator.scratchpad not in repr(result.report)


def test_core_has_no_network_model_or_automation_surface():
    source = inspect.getsource(ag)
    for forbidden in (
        "import requests", "import urllib", "import socket", "import subprocess",
        "SAIFREN", "9router", "temperature", "model_name", "while True",
        "AttentionQueue(", ".admit_receiver_candidate(", "ATTENTION_PRIORITY",
        "DEFERRAL_POLICY", "ALLOCATION", "seal_human_private", "HumanPrivateStore",
        "from .legacy", "from .promotion", ".saipen",
    ):
        assert forbidden not in source, forbidden


def full_approved_stack():
    source = corpus("o1", "o2", "o3", "c1")
    generator = CountingGenerator(ag.GeneratorResult.of(advice()))
    reviewer = RecordingReviewer()
    result = outcome(source, generator, reviewer)
    assert result.status == ag.APPROVED
    return source, result


def test_approved_generated_advice_enters_the_existing_corridor(tmp_path):
    source, result = full_approved_stack()
    reviewed = result.reviewed
    assert reviewed.candidate.advice.observed == advice().observed
    assert reviewed.candidate.advice.counterevidence == advice().counterevidence
    assert reviewed.candidate.advice.uncertainty == advice().uncertainty

    # Generated adapter is the only bridge; the manual B-012 path stays valid.
    assert error(ag.reviewed_ally_to_human_private, reviewed.candidate,
                 recipient_human_id=HUMAN).code == ag.ALLY_GEN_PRIVATE_PROOF_REQUIRED
    manual = aa.ally_to_human_private(resolved(), recipient_human_id=HUMAN)
    assert manual.subject == aa.ALLY_ADVICE_SUBJECT

    letter = ag.reviewed_ally_to_human_private(reviewed, recipient_human_id=HUMAN)
    assert letter.body.encode() == advice().render()

    attention_root = tmp_path / "attention"
    queue = ha.AttentionQueue(attention_root, human_id=HUMAN,
                              clock=lambda: "2026-09-19T20:00:00Z")
    assert queue.reserve_next().status == ha.NO_MESSAGE

    sealed = seal_human_private(
        letter, sender_private_key=SENDER, sender_seat=SENDER_SEAT,
        recipient=recipient(), mode=MODE_STRICT)
    store = HumanPrivateStore(tmp_path / "mail", human_id=HUMAN,
                              sender_registry=registry())
    delivery = store.deliver(sealed)

    files = tree(tmp_path)
    for data in files.values():
        for marker in (
            *(value.encode() for value in MARKERS.values()),
            aa.ALLY_ADVICE_SUBJECT.encode(), b"ALLY1",
            source.corpus_id.encode(), ag.RUBRIC_VERSION.encode(),
            ag.OBSERVATION_SUPPORT.encode(),
        ):
            assert marker not in data
    assert files[str(store.letter_path(delivery.letter_id).relative_to(tmp_path))].startswith(
        b"HENV1")

    # Approval and storage still leave receiver attention untouched.
    state = queue.budget_state()
    assert state.pending_candidates == 0
    assert state.consumed == 0
    assert queue.reserve_next().status == ha.NO_MESSAGE

    admitted = queue.admit_receiver_candidate(
        source_kind=ha.HUMAN_PRIVATE, source_ref=delivery.letter_id,
        allocation="IDLE_REPORT", deferral_policy="QUEUE_AND_CONTINUE")
    assert admitted.candidate.source_ref == delivery.letter_id
    reservation = queue.reserve_next().reservation
    queue.ack_presented(reservation.reservation_id)

    opened = store.open(delivery.letter_id, provider=SoftwareP256Provider(PRIMARY))
    recovered = aa.open_ally_advice(opened, recipient_human_id=HUMAN)
    assert recovered == advice()
    assert recovered.inference_status == aa.INFERENCE_STATUS
    assert recovered.guidance_status == aa.GUIDANCE_STATUS
    assert recovered.agency == aa.AGENCY
    assert queue.budget_state().consumed == 1


def test_zero_advice_and_rejections_leave_zero_downstream_output(tmp_path):
    source = corpus("o1", "o2", "o3", "c1")
    queue = ha.AttentionQueue(tmp_path / "attention", human_id=HUMAN,
                              clock=lambda: "2026-09-19T20:00:00Z")
    for generator, reviewer, expected in (
        (CountingGenerator(ag.GeneratorResult.no_advice()), RecordingReviewer(),
         ag.NO_ADVICE),
        (CountingGenerator(ag.GeneratorResult.of(advice())),
         RecordingReviewer(**{ag.NO_MOTIVE_INFERENCE: ag.FAIL}), ag.REJECTED),
        (CountingGenerator(ag.GeneratorResult.of(advice())),
         RecordingReviewer(**{ag.NO_COMPLIANCE_PRESSURE: ag.UNKNOWN}), ag.REJECTED),
    ):
        result = outcome(source, generator, reviewer)
        assert result.status == expected
        assert result.reviewed is None
        if expected == ag.REJECTED:
            assert reviewer.calls == 1
        else:
            assert reviewer.calls == 0
    assert tree(tmp_path) == {}
    assert queue.budget_state().pending_candidates == 0
    assert queue.budget_state().consumed == 0
    assert queue.reserve_next().status == ha.NO_MESSAGE


def test_zero_advice_is_reported_as_success_not_error():
    source = corpus("o1", "o2", "o3", "c1")
    result = outcome(source, CountingGenerator(ag.GeneratorResult.no_advice()),
                     RecordingReviewer())
    assert result.status == ag.NO_ADVICE
    assert result.code is None
    assert result.status != ag.ERROR
    assert result.reviewed is None
    assert result.report is None


def test_approval_creates_no_truth_authority_or_attention_state(tmp_path):
    source, result = full_approved_stack()
    reviewed = result.reviewed
    proof = reviewed.candidate
    assert isinstance(proof, aa.EvidenceResolvedAllyAdvice)
    assert reviewed.corpus.corpus_id == source.corpus_id
    assert reviewed.report.rubric_version == ag.RUBRIC_VERSION
    assert proof.advice.inference_status == aa.INFERENCE_STATUS
    assert proof.advice.guidance_status == aa.GUIDANCE_STATUS
    assert proof.advice.agency == aa.AGENCY
    # The reviewed type-state creates no ALLY1 field, no knowledge record, no
    # promotion proposal and no receiver priority; nothing is persisted.
    assert tree(tmp_path) == {}
    assert error(ag.SemanticallyReviewedAllyAdvice, proof, source,
                 result.report).code == ag.ALLY_GEN_REVIEW_PROOF_FORGED
