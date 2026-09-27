"""B-017 builder: deterministic bounded build, non-transferable proof, policy.

The builder converts one explicit bounded request into the existing B-016
``ReflectionCorpus``.  It discovers nothing, groups nothing automatically,
proves no completeness and mints a proof that cannot be transplanted onto a
different corpus, grouping, window or artifact set.
"""

import builtins
import dataclasses
import glob
import hashlib
import inspect
import io
import os
import socket
import subprocess

import pytest

from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag
from saimail import project_corpus as pc

CREATED = "2026-09-19T20:00:00Z"
SCOPE = "project:saimail"
WINDOW_START = "2026-09-01T00:00:00Z"
WINDOW_END = "2026-10-01T00:00:00Z"


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode()).hexdigest()


def artifact(tag, *, source_kind=pc.TEST_RESULT, source_ref=None, observed_at=CREATED,
             content=None, scope=SCOPE):
    return pc.ProjectArtifact(
        project_scope=scope,
        source_kind=source_kind,
        source_ref=source_ref or f"saipen-event:{tag}",
        observed_at=observed_at,
        content=content or f"Operational evidence for {tag}.",
    )


def evidence(tag, **kwargs):
    return pc.project_evidence_ref(artifact(tag, **kwargs))


def declaration(*tags, **artifact_kwargs):
    return pc.ProjectEventDeclaration(
        project_scope=SCOPE,
        member_evidence_refs=tuple(evidence(tag, **artifact_kwargs) for tag in tags),
    )


def declaration_for(*entries, scope=SCOPE):
    return pc.ProjectEventDeclaration(
        project_scope=scope,
        member_evidence_refs=tuple(pc.project_evidence_ref(entry) for entry in entries),
    )


def request_for(artifacts, declarations, **changes):
    values = {
        "project_scope": SCOPE,
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "selection_basis": pc.SELECTION_BASIS,
        "artifacts": artifacts,
        "event_declarations": declarations,
    }
    values.update(changes)
    return pc.ProjectCorpusRequest(**values)


def request(*tags, events=None, **changes):
    tags = tags or ("a1",)
    groups = {}
    for tag in tags:
        groups.setdefault((events or {}).get(tag, tag), []).append(tag)
    values = {
        "project_scope": SCOPE,
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "selection_basis": pc.SELECTION_BASIS,
        "artifacts": tuple(artifact(tag) for tag in tags),
        "event_declarations": tuple(
            declaration(*members) for members in groups.values()),
    }
    values.update(changes)
    return pc.ProjectCorpusRequest(**values)


def build(*tags, **changes):
    return pc.build_project_corpus(request(*tags, **changes))


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


# ------------------------------------------------------------------
# selection window
# ------------------------------------------------------------------


def test_invalid_window_is_refused():
    assert error(request, "a1", window_start=WINDOW_END, window_end=WINDOW_START).code == (
        pc.PROJECT_CORPUS_BAD_WINDOW)
    same = "2026-09-15T00:00:00Z"
    assert error(request, "a1", window_start=same, window_end=same).code == (
        pc.PROJECT_CORPUS_BAD_WINDOW)
    assert error(request, "a1", window_start="not-a-time").code == (
        pc.PROJECT_CORPUS_BAD_ITEM)


def test_window_membership_is_exact_and_never_clamped():
    assert error(request, "a1", artifacts=(artifact("a1", observed_at="2026-08-31T23:59:59Z"),)).code == (
        pc.PROJECT_CORPUS_WINDOW_EXCLUDED)
    accepted_start = build(
        "a1", artifacts=(artifact("a1", observed_at=WINDOW_START),),
        event_declarations=(declaration("a1", observed_at=WINDOW_START),))
    assert accepted_start.artifact_count == 1
    accepted_inside = build(
        "a1", artifacts=(artifact("a1", observed_at="2026-09-15T12:00:00Z"),),
        event_declarations=(declaration("a1", observed_at="2026-09-15T12:00:00Z"),))
    assert accepted_inside.artifact_count == 1
    assert error(request, "a1", artifacts=(artifact("a1", observed_at=WINDOW_END),)).code == (
        pc.PROJECT_CORPUS_WINDOW_EXCLUDED)


# ------------------------------------------------------------------
# project scope and selection basis
# ------------------------------------------------------------------


def test_project_scope_matches_exactly_and_mixed_builds_refuse():
    assert error(request, "a1", artifacts=(artifact("a1", scope="project:saimail-test"),)).code == (
        pc.PROJECT_CORPUS_SCOPE_MISMATCH)
    assert error(request, "a1", artifacts=(artifact("a1", scope="project:other"),)).code == (
        pc.PROJECT_CORPUS_SCOPE_MISMATCH)
    assert error(request, "a1", event_declarations=(
        pc.ProjectEventDeclaration("project:saimail-test", (evidence("a1"),)),)).code == (
        pc.PROJECT_CORPUS_SCOPE_MISMATCH)


def test_stronger_selection_claims_are_mechanically_refused():
    for claim in ("COMPLETE", "ALL_RELEVANT", "EXHAUSTIVE", "UNBIASED"):
        assert error(request, "a1", selection_basis=claim).code == (
            pc.PROJECT_CORPUS_SELECTION_BASIS_REFUSED), claim
    assert pc.SELECTION_BASIS == "EXPLICIT_BOUNDED_SET"
    assert pc.COMPLETENESS == "NOT_PROVEN"


def test_corpus_bounds_are_the_b016_ceiling_and_overflow_refuses():
    many = tuple(artifact(f"tag-{index}") for index in range(ag.MAX_ITEMS + 1))
    declarations = tuple(
        pc.ProjectEventDeclaration(SCOPE, (pc.project_evidence_ref(entry),))
        for entry in many)
    assert error(pc.ProjectCorpusRequest, SCOPE, WINDOW_START, WINDOW_END,
                 pc.SELECTION_BASIS, many, declarations).code == (
        pc.PROJECT_CORPUS_CORPUS_OVERSIZE)
    fat = tuple(
        artifact(f"fat-{index}", content="y" * 8_000) for index in range(17))
    fat_declarations = tuple(
        pc.ProjectEventDeclaration(SCOPE, (pc.project_evidence_ref(entry),))
        for entry in fat)
    assert error(pc.ProjectCorpusRequest, SCOPE, WINDOW_START, WINDOW_END,
                 pc.SELECTION_BASIS, fat, fat_declarations).code == (
        pc.PROJECT_CORPUS_CORPUS_OVERSIZE)


# ------------------------------------------------------------------
# determinism and build/corpus identity
# ------------------------------------------------------------------


def test_caller_order_never_changes_build_id_or_corpus_id():
    forward = build("a1", "a2", "a3", "c1", events={"a2": "a1"})
    backward = build("c1", "a3", "a2", "a1", events={"a2": "a1"})
    assert forward.build_id == backward.build_id
    assert forward.corpus_id == backward.corpus_id
    assert forward.build_id.startswith("sha256:")
    assert len(forward.build_id) == len("sha256:") + 64
    assert forward.build_id != forward.corpus_id


def test_content_mutation_changes_build_and_corpus_identity():
    base = build("a1", "a2", "a3")
    changed_captures = (
        artifact("a1"),
        artifact("a2", content="A different operational statement."),
        artifact("a3"),
    )
    changed = pc.build_project_corpus(request_for(
        changed_captures, tuple(declaration_for(entry) for entry in changed_captures)))
    assert changed.build_id != base.build_id
    assert changed.corpus_id != base.corpus_id


def test_regrouping_changes_event_set_build_id_and_corpus_id():
    first = build("a1", "a2", "a3", events={"a2": "a1"})
    regrouped = build("a1", "a2", "a3", event_declarations=(declaration("a1", "a2", "a3"),))
    assert first.event_refs() != regrouped.event_refs()
    assert first.build_id != regrouped.build_id
    assert first.corpus_id != regrouped.corpus_id


def test_observed_time_mutation_keeps_evidence_ref_and_changes_identity():
    base = build("a1")
    later = build(
        "a1", artifacts=(artifact("a1", observed_at="2026-09-20T00:00:00Z"),),
        event_declarations=(declaration("a1", observed_at="2026-09-20T00:00:00Z"),))
    assert pc.project_evidence_ref(artifact("a1")) == (
        pc.project_evidence_ref(artifact("a1", observed_at="2026-09-20T00:00:00Z")))
    assert base.build_id != later.build_id
    assert base.corpus_id != later.corpus_id


def test_source_kind_mutation_changes_identity_and_binding():
    base = build("a1")
    other = build(
        "a1", artifacts=(artifact("a1", source_kind=pc.INCIDENT),),
        event_declarations=(declaration("a1", source_kind=pc.INCIDENT),))
    assert base.build_id != other.build_id
    assert base.corpus_id != other.corpus_id
    assert base.receipts()[0].source_kind == pc.TEST_RESULT
    assert other.receipts()[0].source_kind == pc.INCIDENT


# ------------------------------------------------------------------
# proof type-state
# ------------------------------------------------------------------


def test_direct_construction_and_replace_cannot_mint_the_proof():
    built = build("a1", "a2", "a3", events={"a2": "a1"})
    assert error(pc.BuiltProjectCorpus, built.request, built.reflection_corpus,
                 built.build_id).code == pc.PROJECT_CORPUS_PROOF_FORGED
    assert error(dataclasses.replace, built).code == pc.PROJECT_CORPUS_PROOF_FORGED


def test_proof_cannot_transfer_corpus_grouping_window_or_artifact_set():
    built = build("a1", "a2", "a3", events={"a2": "a1"})
    other_corpus = build("z1").reflection_corpus
    regrouped = build("a1", "a2", "a3",
                      event_declarations=(declaration("a1", "a2", "a3"),))
    moved_window = build(
        "a1", "a2", "a3", events={"a2": "a1"},
        window_end="2026-10-02T00:00:00Z")
    mutated_captures = (
        artifact("a1"),
        artifact("a2", content="Mutated capture."),
        artifact("a3"),
    )
    mutated = pc.build_project_corpus(request_for(
        mutated_captures,
        (declaration_for(mutated_captures[0], mutated_captures[1]),
         declaration_for(mutated_captures[2]))))
    forged = pc.PROJECT_CORPUS_PROOF_FORGED
    assert error(dataclasses.replace, built, reflection_corpus=other_corpus).code == forged
    assert error(dataclasses.replace, built, request=regrouped.request).code == forged
    assert error(dataclasses.replace, built, request=moved_window.request).code == forged
    assert error(dataclasses.replace, built, request=mutated.request).code == forged
    assert not any(field.name == "binding"
                   for field in dataclasses.fields(pc.BuiltProjectCorpus))


def test_proof_metadata_is_bounded_audit_data_only():
    built = build("a1", "a2", "a3", "c1", events={"a2": "a1"})
    assert built.project_scope == SCOPE
    assert built.window_start == WINDOW_START
    assert built.window_end == WINDOW_END
    assert built.artifact_count == 4
    assert built.event_count == 3
    receipts = built.receipts()
    assert len(receipts) == 4
    assert tuple(entry.evidence_ref for entry in receipts) == tuple(
        sorted(entry.evidence_ref for entry in receipts))
    assert {entry.source_ref for entry in receipts} == {
        "saipen-event:a1", "saipen-event:a2", "saipen-event:a3", "saipen-event:c1"}
    assert built.source_kind_for(evidence("a1")) == pc.TEST_RESULT
    mapping = dict(built.evidence_ref_to_event_ref())
    assert set(mapping) == {evidence(tag) for tag in ("a1", "a2", "a3", "c1")}
    assert mapping[evidence("a1")] == mapping[evidence("a2")]


# ------------------------------------------------------------------
# future real-pilot type gate
# ------------------------------------------------------------------


def test_future_pilot_type_gate_accepts_only_a_built_corpus():
    assert pc.is_built_project_corpus(build("a1")) is True
    assert pc.is_built_project_corpus(build("a1").reflection_corpus) is False
    assert error(pc.require_built_project_corpus, build("a1").reflection_corpus).code == (
        pc.PROJECT_CORPUS_BUILDER_PROOF_REQUIRED)
    assert pc.require_built_project_corpus(build("a1")).artifact_count == 1


# ------------------------------------------------------------------
# B-016 integration
# ------------------------------------------------------------------


class FixedGenerator:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def generate(self, corpus):
        self.calls += 1
        return self.result


class ReportReviewer:
    def __init__(self, **overrides):
        self.overrides = overrides
        self.calls = 0

    def review(self, resolved, corpus):
        self.calls += 1
        verdicts = tuple(
            ag.ReviewVerdict(
                dimension,
                self.overrides.get(dimension, ag.PASS),
                f"{dimension} rationale.",
                (evidence("a1"),) if dimension == ag.OBSERVATION_SUPPORT
                else (evidence("c1"),) if dimension == ag.COUNTEREVIDENCE_ADEQUACY
                else ())
            for dimension in ag.DIMENSIONS
        )
        return ag.SemanticReviewReport(
            ag.ally_candidate_id(resolved.advice), corpus.corpus_id,
            ag.RUBRIC_VERSION, verdicts)


def candidate():
    return aa.AllyAdvice(
        created=CREATED,
        work_context="Project corpus builder verification work.",
        observed_scope="One bounded project window.",
        observed=(
            aa.AdviceObservation("First observation across two captures.",
                                 (evidence("a1"), evidence("a2"))),
            aa.AdviceObservation("Second observation from another declared event.",
                                 (evidence("a3"),)),
        ),
        inferred="The captures may describe a recurring operational shape.",
        guidance_mode=aa.CONSIDER_CHANGE,
        suggested="Consider one reversible review pass before the next release.",
        counterevidence=(
            aa.AdviceCounterevidence("Counterevidence capture limits the inference.",
                                     (evidence("c1"),)),
        ),
        uncertainty="This bounded sample may be specific to one window.",
    )


def two_event_result():
    return build("a1", "a2", "a3", "c1", events={"a2": "a1"})


def test_builder_output_is_a_valid_b016_corpus_with_exact_mapping():
    built = two_event_result()
    corpus = built.reflection_corpus
    assert isinstance(corpus, ag.ReflectionCorpus)
    for item in corpus.items:
        assert item.source_domain == ag.PROJECT_OPERATIONAL
        assert item.observed_scope == SCOPE
        assert item.observed_at == CREATED
        assert item.event_ref in built.event_refs()
    item = corpus.item_for(evidence("a1"))
    assert item.content == "Operational evidence for a1."


def test_one_declared_event_fails_the_existing_b016_event_floor():
    built = build(
        "a1", "a2", "a3", "c1",
        event_declarations=(declaration("a1", "a2", "a3"), declaration("c1")))
    generator = FixedGenerator(ag.GeneratorResult.of(candidate()))
    reviewer = ReportReviewer()
    outcome = ag.generate_reviewed_ally_advice(built.reflection_corpus, generator, reviewer)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS
    assert reviewer.calls == 0
    assert outcome.reviewed is None


def test_two_declared_events_reach_the_existing_reviewer_unchanged():
    built = two_event_result()
    generator = FixedGenerator(ag.GeneratorResult.of(candidate()))
    reviewer = ReportReviewer()
    outcome = ag.generate_reviewed_ally_advice(built.reflection_corpus, generator, reviewer)
    assert outcome.status == ag.APPROVED
    assert generator.calls == 1
    assert reviewer.calls == 1
    assert isinstance(outcome.reviewed, ag.SemanticallyReviewedAllyAdvice)

    failing = ReportReviewer(**{ag.NO_FLATTERY: ag.FAIL})
    rejected = ag.generate_reviewed_ally_advice(
        built.reflection_corpus, FixedGenerator(ag.GeneratorResult.of(candidate())), failing)
    assert rejected.status == ag.REJECTED
    assert rejected.code == ag.ALLY_GEN_REVIEW_REJECTED
    assert failing.calls == 1


def test_generic_b016_corpus_and_manual_b012_path_stay_valid_without_the_builder():
    raw = ag.ReflectionCorpus(items=tuple(
        ag.ReflectionItem(
            evidence_ref=evidence(tag),
            source_domain=ag.PROJECT_OPERATIONAL,
            observed_at=CREATED,
            observed_scope=SCOPE,
            content=f"Operational evidence for {tag}.",
            event_ref=ref("event-" + ("x" if tag in ("a1", "a2") else tag)),
        )
        for tag in ("a1", "a2", "a3", "c1")
    ))
    generator = FixedGenerator(ag.GeneratorResult.of(candidate()))
    reviewer = ReportReviewer()
    outcome = ag.generate_reviewed_ally_advice(raw, generator, reviewer)
    assert outcome.status == ag.APPROVED

    manual = aa.resolve_ally_evidence(candidate(), ag.CorpusEvidenceResolver(raw))
    letter = aa.ally_to_human_private(
        manual, recipient_human_id="human-id:sha256:" + "0" * 64)
    assert letter.subject == aa.ALLY_ADVICE_SUBJECT


# ------------------------------------------------------------------
# side effects: no discovery, no store, no model, no network
# ------------------------------------------------------------------


def test_builder_touches_no_external_surface(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("the builder must not touch external surfaces")

    monkeypatch.setattr(builtins, "open", boom)
    monkeypatch.setattr(io, "open", boom)
    monkeypatch.setattr(os, "walk", boom)
    monkeypatch.setattr(os, "listdir", boom)
    monkeypatch.setattr(os, "scandir", boom)
    monkeypatch.setattr(glob, "glob", boom)
    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(socket, "socket", boom)
    built = build("a1", "a2", "a3", "c1", events={"a2": "a1"})
    assert built.artifact_count == 4


def test_builder_and_policy_have_no_discovery_model_or_store_surface():
    source = inspect.getsource(pc)
    for forbidden in (
        "open(", "read_text", "read_bytes", "write_text", "write_bytes",
        "os.walk", "listdir", "scandir", "subprocess", "socket", "requests",
        "urllib", "glob", "git", ".saipen", "SAIFREN", "9router",
        "model_name", "temperature", "confidence", "similarit", "embedding",
        "cluster", "basename", "HumanPatternStore", "ReflectionCorpusStore",
    ):
        assert forbidden not in source, forbidden
    parameters = tuple(inspect.signature(pc.build_project_corpus).parameters)
    assert parameters == ("request",)
    for name in ("cluster_artifacts", "infer_events", "group_by_ticket",
                 "group_by_timestamp", "group_by_filename", "discover_sources"):
        assert not hasattr(pc, name), name


def test_no_automatic_grouping_authority_is_exposed():
    # The only event identity path is the exact declaration plus the minted
    # ref; no helper accepts tickets, paths, timestamps or similarity as input.
    built = build("a1", "a2", events={"a2": "a1"})
    declaration = pc.ProjectEventDeclaration(SCOPE, (evidence("a1"), evidence("a2")))
    assert built.event_refs() == {declaration.computed_event_ref}
    assert declaration.computed_event_ref != pc.project_event_ref(
        pc.ProjectEventDeclaration(SCOPE, (evidence("a1"),)))
