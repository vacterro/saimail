"""B-017 artifacts: explicit bounded project captures and minted evidence ids.

The builder mints ``EVIDENCE_REF``; the caller never writes it.  Source kind is
provenance metadata, never a truth rank, and an observation timestamp never
changes the artifact identity it is attached to.
"""

import hashlib
import inspect

import pytest

from sailang.errors import SailangError
from saimail import ally_generation as ag
from saimail import project_corpus as pc

CREATED = "2026-09-19T20:00:00Z"
SCOPE = "project:saimail"


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode()).hexdigest()


def artifact(tag, *, source_kind=pc.TEST_RESULT, source_ref=None, observed_at=CREATED,
             content=None, scope=SCOPE):
    return pc.ProjectArtifact(
        project_scope=scope,
        source_kind=source_kind,
        source_ref=source_ref or f"ticket:{tag}",
        observed_at=observed_at,
        content=content or f"Operational evidence for {tag}.",
    )


def declaration(*tags, scope=SCOPE):
    return pc.ProjectEventDeclaration(
        project_scope=scope,
        member_evidence_refs=tuple(
            pc.project_evidence_ref(artifact(tag)) for tag in tags),
    )


def request(*tags, events=None, **changes):
    tags = tags or ("a1",)
    events = events or {}
    groups = {}
    for tag in tags:
        groups.setdefault(events.get(tag, tag), []).append(tag)
    values = {
        "project_scope": SCOPE,
        "window_start": "2026-09-01T00:00:00Z",
        "window_end": "2026-10-01T00:00:00Z",
        "selection_basis": pc.SELECTION_BASIS,
        "artifacts": tuple(artifact(tag) for tag in tags),
        "event_declarations": tuple(
            declaration(*members) for members in groups.values()),
    }
    values.update(changes)
    return pc.ProjectCorpusRequest(**values)


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


# ------------------------------------------------------------------
# matrix 1-6: bounded artifact shape
# ------------------------------------------------------------------


def test_valid_project_artifact_is_accepted():
    built = artifact("a1")
    assert built.project_scope == SCOPE
    assert built.source_kind == pc.TEST_RESULT
    assert built.source_ref == "ticket:a1"
    assert built.observed_at == CREATED
    assert built.content == "Operational evidence for a1."


def test_source_kind_vocabulary_is_closed_and_not_a_truth_rank():
    assert pc.SOURCE_KINDS == (
        pc.OPERATOR_DECISION,
        pc.SPEC_DECISION,
        pc.IMPLEMENTATION_CHANGE,
        pc.TEST_RESULT,
        pc.REVIEW_FINDING,
        pc.INCIDENT,
        pc.RUNTIME_OBSERVATION,
    )
    assert error(artifact, "a1", source_kind="FREE_FORM_KIND").code == (
        pc.PROJECT_CORPUS_SOURCE_KIND_UNKNOWN)
    assert error(artifact, "a1", source_kind="test_result").code == (
        pc.PROJECT_CORPUS_SOURCE_KIND_UNKNOWN)


def test_malformed_project_scope_is_refused():
    for malformed in ("SAIMAIL", "project:", "project:SAIMail", "team:saimail",
                      "project:-x", " project:saimail", ""):
        assert error(artifact, "a1", scope=malformed).code == (
            pc.PROJECT_CORPUS_BAD_SCOPE), malformed


def test_malformed_observed_at_is_refused():
    for malformed in ("2026-09-19 20:00:00", "2026-13-99T00:00:00Z", "", "now"):
        assert error(artifact, "a1", observed_at=malformed).code == (
            pc.PROJECT_CORPUS_BAD_ITEM), malformed


def test_oversized_source_ref_and_content_are_refused_not_truncated():
    assert error(artifact, "a1", source_ref="r" * (pc.MAX_SOURCE_REF_BYTES + 1)).code == (
        pc.PROJECT_CORPUS_ITEM_OVERSIZE)
    assert error(artifact, "a1", content="x" * (ag.MAX_ITEM_BYTES + 1)).code == (
        pc.PROJECT_CORPUS_ITEM_OVERSIZE)
    assert error(artifact, "a1", content="bad\x00content").code == (
        pc.PROJECT_CORPUS_BAD_ITEM)


def test_scope_and_source_ref_bounds_are_the_b016_ceiling():
    assert pc.MAX_ITEMS == ag.MAX_ITEMS
    assert pc.MAX_ITEM_BYTES == ag.MAX_ITEM_BYTES
    assert pc.MAX_TOTAL_CONTENT_BYTES == ag.MAX_TOTAL_CONTENT_BYTES


# ------------------------------------------------------------------
# matrix 7-10: minted evidence identity
# ------------------------------------------------------------------


def test_same_exact_artifact_mints_the_same_evidence_ref():
    first = pc.project_evidence_ref(artifact("a1"))
    second = pc.project_evidence_ref(artifact("a1"))
    assert first == second
    assert first.startswith("sha256:")
    assert len(first) == len("sha256:") + 64


def test_changed_content_changes_the_evidence_ref():
    base = pc.project_evidence_ref(artifact("a1"))
    changed = pc.project_evidence_ref(artifact("a1", content="A different operational statement."))
    assert changed != base


def test_identical_content_under_distinct_source_refs_stays_distinct():
    left = pc.ProjectArtifact(SCOPE, pc.TEST_RESULT, "test-run:1", CREATED, "same bytes")
    right = pc.ProjectArtifact(SCOPE, pc.TEST_RESULT, "test-run:2", CREATED, "same bytes")
    assert pc.project_evidence_ref(left) != pc.project_evidence_ref(right)


def test_source_kind_participates_in_evidence_identity():
    base = pc.project_evidence_ref(artifact("a1"))
    other_kind = pc.project_evidence_ref(artifact("a1", source_kind=pc.INCIDENT))
    assert other_kind != base


def test_observed_at_alone_never_changes_the_evidence_ref():
    base = pc.project_evidence_ref(artifact("a1"))
    later = pc.project_evidence_ref(artifact("a1", observed_at="2026-09-20T00:00:00Z"))
    assert later == base


def test_duplicate_source_ref_is_refused_with_named_codes():
    exact = artifact("a1")
    assert error(request, artifacts=(exact, exact)).code == pc.PROJECT_SOURCE_REF_DUPLICATE
    conflicting = artifact("a1", content="A conflicting capture of the same source.")
    assert error(request, artifacts=(exact, conflicting)).code == (
        pc.PROJECT_SOURCE_REF_CONFLICT)


def test_artifact_module_has_no_discovery_or_persistence_surface():
    source = inspect.getsource(pc)
    for forbidden in ("open(", "read_text", "read_bytes", "os.walk", "scandir",
                      "subprocess", "socket", "requests", "urllib", "glob",
                      "Path(", "write_text", "write_bytes", ".saipen"):
        assert forbidden not in source, forbidden
