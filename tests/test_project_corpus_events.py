"""B-017 events: grouping is an explicit caller declaration, never inferred.

Ticket ids, filenames, timestamps and identical text never mint or merge an
event.  Event identity is minted by the builder from the exact declaration, and
the declarations must exactly partition the selected artifact set.
"""

import dataclasses
import hashlib

import pytest

from sailang.errors import SailangError
from saimail import project_corpus as pc

CREATED = "2026-09-19T20:00:00Z"
SCOPE = "project:saimail"
WINDOW_START = "2026-09-01T00:00:00Z"
WINDOW_END = "2026-10-01T00:00:00Z"


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode()).hexdigest()


def artifact(tag, *, source_ref=None, observed_at=CREATED, content=None):
    return pc.ProjectArtifact(
        project_scope=SCOPE,
        source_kind=pc.RUNTIME_OBSERVATION,
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


def build(*tags, events=None, **changes):
    artifacts = tuple(artifact(tag) for tag in tags)
    groups = {}
    for tag in tags:
        groups.setdefault((events or {}).get(tag, tag), []).append(tag)
    values = {
        "project_scope": SCOPE,
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "selection_basis": pc.SELECTION_BASIS,
        "artifacts": artifacts,
        "event_declarations": tuple(
            declaration(*members) for members in groups.values()),
    }
    values.update(changes)
    return pc.build_project_corpus(pc.ProjectCorpusRequest(**values))


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


# ------------------------------------------------------------------
# declaration shape
# ------------------------------------------------------------------


def test_members_are_canonicalized_and_minted_from_the_exact_group():
    forward = pc.ProjectEventDeclaration(SCOPE, (evidence("c"), evidence("a"), evidence("b")))
    backward = pc.ProjectEventDeclaration(SCOPE, (evidence("b"), evidence("c"), evidence("a")))
    assert forward == backward
    assert forward.member_evidence_refs == tuple(sorted(forward.member_evidence_refs))
    assert forward.computed_event_ref == backward.computed_event_ref
    assert forward.computed_event_ref.startswith("sha256:")


def test_duplicate_member_is_refused():
    assert error(pc.ProjectEventDeclaration, SCOPE, (evidence("a"), evidence("a"))).code == (
        pc.PROJECT_CORPUS_DUPLICATE_MEMBER)


def test_empty_event_is_refused():
    assert error(pc.ProjectEventDeclaration, SCOPE, ()).code == pc.PROJECT_CORPUS_EMPTY_EVENT


def test_malformed_member_ref_is_refused():
    for malformed in ("saipen-event:E-1", "sha256:UPPER", "", "sha256:" + "a" * 63):
        assert error(pc.ProjectEventDeclaration, SCOPE, (malformed,)).code == (
            pc.PROJECT_CORPUS_BAD_DECLARATION), malformed


def test_caller_cannot_supply_an_event_ref():
    names = {field.name for field in dataclasses.fields(pc.ProjectEventDeclaration)}
    assert "event_ref" not in names
    with pytest.raises(TypeError):
        pc.ProjectEventDeclaration(SCOPE, (evidence("a"),), event_ref=ref("event-a"))


# ------------------------------------------------------------------
# matrix 25-31: event identity is the declared grouping only
# ------------------------------------------------------------------


def test_same_grouping_mints_the_same_event_ref():
    one = declaration("a", "b")
    two = declaration("b", "a")
    assert one.computed_event_ref == two.computed_event_ref


def test_grouping_change_mints_a_different_event_ref():
    assert declaration("a", "b").computed_event_ref != declaration("a", "b", "c").computed_event_ref


def captures(*pairs):
    built = tuple(
        pc.ProjectArtifact(SCOPE, pc.TEST_RESULT, source_ref, CREATED,
                           f"Operational evidence for {tag}.")
        for tag, source_ref in pairs)
    return built, tuple(pc.project_evidence_ref(capture) for capture in built)


def request_for(built, declarations, **changes):
    values = {
        "project_scope": SCOPE,
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "selection_basis": pc.SELECTION_BASIS,
        "artifacts": built,
        "event_declarations": declarations,
    }
    values.update(changes)
    return pc.ProjectCorpusRequest(**values)


def test_one_shared_ticket_does_not_decide_the_event():
    # C1: three captures under one ticket namespace become ONE event because
    # the caller declared one group, not because the ticket id matched.  Exact
    # duplicate SOURCE_REF entries are refused, so each capture carries its own
    # locator inside the same ticket namespace.
    built, refs = captures(
        ("r", "ticket:T-100/log"),
        ("t", "ticket:T-100/repro"),
        ("n", "ticket:T-100/review"),
    )
    declaration = pc.ProjectEventDeclaration(SCOPE, refs)
    result = pc.build_project_corpus(request_for(built, (declaration,)))
    assert result.event_count == 1
    assert len(result.event_refs()) == 1


def test_one_ticket_can_carry_two_declared_events():
    built, refs = captures(
        ("a", "ticket:T-100/repro"),
        ("b", "ticket:T-100/review"),
        ("c", "ticket:T-100/follow-up"),
        ("d", "ticket:T-100/incident"),
    )
    first = pc.ProjectEventDeclaration(SCOPE, (refs[0], refs[1]))
    second = pc.ProjectEventDeclaration(SCOPE, (refs[2], refs[3]))
    result = pc.build_project_corpus(request_for(built, (first, second)))
    assert result.event_count == 2
    assert len(result.event_refs()) == 2


def test_different_tickets_can_be_one_declared_event():
    built, refs = captures(
        ("a", "ticket:T-100"),
        ("b", "ticket:T-101"),
    )
    result = pc.build_project_corpus(request_for(
        built, (pc.ProjectEventDeclaration(SCOPE, refs),)))
    assert result.event_count == 1
    assert len(result.event_refs()) == 1


def test_equal_timestamps_do_not_group_and_one_declaration_spans_days():
    same_moment = build(
        "a", "b",
        artifacts=(
            artifact("a", observed_at="2026-09-10T10:00:00Z"),
            artifact("b", observed_at="2026-09-10T10:00:00Z"),
        ),
    )
    assert len(same_moment.event_refs()) == 2
    far_apart = build(
        "a", "b",
        artifacts=(
            artifact("a", observed_at="2026-09-02T10:00:00Z"),
            artifact("b", observed_at="2026-09-25T10:00:00Z"),
        ),
        event_declarations=(declaration("a", "b"),),
    )
    assert len(far_apart.event_refs()) == 1


def test_filenames_and_paths_do_not_group_automatically():
    captures = (
        artifact("a", source_ref="file:logs/foo.log"),
        artifact("b", source_ref="file:logs/bar.log"),
    )
    refs = tuple(pc.project_evidence_ref(capture) for capture in captures)
    result = pc.build_project_corpus(pc.ProjectCorpusRequest(
        SCOPE, WINDOW_START, WINDOW_END, pc.SELECTION_BASIS, captures,
        (pc.ProjectEventDeclaration(SCOPE, (refs[0],)),
         pc.ProjectEventDeclaration(SCOPE, (refs[1],)))))
    assert len(result.event_refs()) == 2
    assert result.event_count == 2


def test_identical_content_does_not_group_or_deduplicate():
    same_text = "Identical operational text under two distinct sources."
    captures = (
        artifact("a", source_ref="review:r1", content=same_text),
        artifact("b", source_ref="review:r2", content=same_text),
    )
    refs = tuple(pc.project_evidence_ref(capture) for capture in captures)
    result = pc.build_project_corpus(pc.ProjectCorpusRequest(
        SCOPE, WINDOW_START, WINDOW_END, pc.SELECTION_BASIS, captures,
        (pc.ProjectEventDeclaration(SCOPE, (refs[0],)),
         pc.ProjectEventDeclaration(SCOPE, (refs[1],)))))
    assert result.artifact_count == 2
    assert len(result.reflection_corpus.refs()) == 2
    assert len(result.event_refs()) == 2
    assert refs[0] != refs[1]


# ------------------------------------------------------------------
# matrix 16-23: exact partition
# ------------------------------------------------------------------


def test_single_artifact_event_is_valid():
    result = build("a", event_declarations=(declaration("a"),))
    assert result.event_count == 1
    assert result.artifact_count == 1


def test_many_artifacts_one_event_is_valid():
    result = build("a", "b", "c", event_declarations=(declaration("a", "b", "c"),))
    assert result.event_count == 1
    assert result.artifact_count == 3


def test_unknown_member_is_refused():
    unknown = declaration("outside")
    assert error(build, "a", event_declarations=(unknown,)).code == (
        pc.PROJECT_CORPUS_UNKNOWN_EVENT_MEMBER)


def test_unassigned_artifact_is_refused():
    assert error(build, "a", "b", event_declarations=(declaration("a"),)).code == (
        pc.PROJECT_CORPUS_UNASSIGNED_ARTIFACT)


def test_artifact_in_two_events_is_refused():
    assert error(build, "a", "b",
                 event_declarations=(declaration("a"), declaration("a", "b"))).code == (
        pc.PROJECT_CORPUS_ARTIFACT_MULTI_EVENT)


def test_exact_partition_is_accepted_and_minted():
    result = build("a", "b", "c", events={"b": "a"})
    assert result.event_count == 2
    mapping = dict(result.evidence_ref_to_event_ref())
    assert mapping[evidence("a")] == mapping[evidence("b")]
    assert mapping[evidence("c")] != mapping[evidence("a")]


def test_event_refs_are_bound_to_the_corpus_items():
    result = build("a", "b", "c", events={"b": "a"})
    declared = {item.event_ref for item in result.reflection_corpus.items}
    assert declared == result.event_refs()
    assert result.reflection_corpus.event_ref_for(evidence("a")) == (
        result.reflection_corpus.event_ref_for(evidence("b")))
