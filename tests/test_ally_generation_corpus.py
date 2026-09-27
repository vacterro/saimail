"""B-016 corpus: bounded caller-supplied reflection items and identity."""

import hashlib
import inspect

import pytest

from sailang.errors import SailangError
from saimail import ally_generation as ag

CREATED = "2026-09-19T20:00:00Z"


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode()).hexdigest()


def item(tag, *, content=None, scope="One project queue.", observed_at=CREATED,
         source_domain=ag.PROJECT_OPERATIONAL, event=None):
    return ag.ReflectionItem(
        evidence_ref=ref(tag),
        source_domain=source_domain,
        observed_at=observed_at,
        observed_scope=scope,
        content=content or f"Operational evidence for {tag}.",
        event_ref=ref("event-" + (event or tag)),
    )


def direct(tag, event):
    return ag.ReflectionItem(
        evidence_ref=ref(tag),
        source_domain=ag.PROJECT_OPERATIONAL,
        observed_at=CREATED,
        observed_scope="One project queue.",
        content=f"Operational evidence for {tag}.",
        event_ref=event,
    )


def corpus(*tags, events=None, **changes):
    events = events or {}
    values = {"items": tuple(item(tag, event=events.get(tag, tag)) for tag in tags)}
    values.update(changes)
    return ag.ReflectionCorpus(**values)


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def test_canonical_bounded_corpus_construction_normalizes_item_order():
    built = corpus("c", "a", "b")
    expected = tuple(sorted(ref(tag) for tag in ("a", "b", "c")))
    assert tuple(entry.evidence_ref for entry in built.items) == expected
    assert built.corpus_id.startswith("sha256:")
    assert len(built.corpus_id) == len("sha256:") + 64
    assert built.refs() == {ref("a"), ref("b"), ref("c")}
    assert built.item_for(ref("b")).content == "Operational evidence for b."


def test_duplicate_evidence_ref_refuses():
    duplicate = item("a")
    assert error(ag.ReflectionCorpus, items=(duplicate, duplicate)).code == (
        ag.ALLY_GEN_DUPLICATE_EVIDENCE_REF)


def test_event_ref_is_required_and_canonical():
    with pytest.raises(TypeError):
        ag.ReflectionItem(
            evidence_ref=ref("a"),
            source_domain=ag.PROJECT_OPERATIONAL,
            observed_at=CREATED,
            observed_scope="One project queue.",
            content="Operational evidence for a.",
        )
    for malformed in ("sha256:UPPER", "event-a", "", "sha256:" + "a" * 63,
                      "sha256:" + "A" * 64, "sha256:" + "g" * 64):
        assert error(direct, "a", malformed).code == ag.ALLY_GEN_BAD_ITEM, malformed


def test_multiple_artifacts_may_share_one_event_ref():
    shared = corpus("a", "b", "c", events={"b": "a", "c": "a"})
    assert shared.event_ref_for(ref("a")) == ref("event-a")
    assert shared.event_ref_for(ref("b")) == ref("event-a")
    assert shared.event_ref_for(ref("c")) == ref("event-a")
    assert shared.event_refs_for((ref("a"), ref("b"), ref("c"))) == {ref("event-a")}
    assert tuple(entry.evidence_ref for entry in shared.items) == tuple(
        sorted(ref(tag) for tag in ("a", "b", "c")))


def test_event_grouping_is_deterministic_and_order_independent():
    forward = corpus("a", "b", "c", events={"a": "z", "c": "a"})
    backward = corpus("c", "b", "a", events={"a": "z", "c": "a"})
    assert forward.items == backward.items
    assert forward.corpus_id == backward.corpus_id
    assert tuple(entry.evidence_ref for entry in forward.items) == tuple(
        sorted(ref(tag) for tag in ("a", "b", "c")))
    assert forward.event_refs_for((ref("a"), ref("c"))) == {ref("event-z"), ref("event-a")}
    assert forward.event_ref_for(ref("absent")) is None
    assert forward.event_refs_for((ref("absent"),)) == frozenset()


def test_unsupported_source_domain_refuses():
    assert error(item, "a", source_domain="PERSONAL_LIFE").code == (
        ag.ALLY_GEN_SOURCE_DOMAIN_REFUSED)
    assert error(item, "a", source_domain="project_operational").code == (
        ag.ALLY_GEN_SOURCE_DOMAIN_REFUSED)


def test_oversized_item_refuses():
    too_big = "x" * (ag.MAX_ITEM_BYTES + 1)
    assert error(item, "a", content=too_big).code == ag.ALLY_GEN_ITEM_OVERSIZE
    oversized_scope = "s" * (ag.MAX_SCOPE_BYTES + 1)
    assert error(item, "a", scope=oversized_scope).code == ag.ALLY_GEN_ITEM_OVERSIZE


def test_oversized_total_corpus_refuses():
    chunk = "y" * 8_000
    many = tuple(item(f"tag-{index}", content=chunk) for index in range(17))
    assert error(ag.ReflectionCorpus, items=many).code == ag.ALLY_GEN_CORPUS_OVERSIZE
    too_many = tuple(item(f"n-{index}") for index in range(ag.MAX_ITEMS + 1))
    assert error(ag.ReflectionCorpus, items=too_many).code == ag.ALLY_GEN_CORPUS_OVERSIZE


def test_caller_order_does_not_change_corpus_id():
    forward = corpus("a", "b", "c", "d")
    backward = corpus("d", "c", "b", "a")
    assert forward.corpus_id == backward.corpus_id
    assert forward.items == backward.items


def test_content_change_changes_corpus_id():
    base = corpus("a", "b", "c")
    changed = ag.ReflectionCorpus(items=(
        item("a"), item("b", content="A different operational statement."), item("c")))
    assert changed.corpus_id != base.corpus_id


def test_event_only_change_changes_corpus_id():
    base = corpus("a", "b", "c")
    same = corpus("a", "b", "c")
    regrouped = corpus("a", "b", "c", events={"c": "a"})
    assert same.corpus_id == base.corpus_id
    assert regrouped.corpus_id != base.corpus_id


def test_scope_change_changes_corpus_id():
    base = corpus("a", "b", "c")
    changed = corpus("a", "b", "c")
    scoped = ag.ReflectionCorpus(items=(
        item("a"), item("b", scope="One different queue."), item("c")))
    assert changed.corpus_id == base.corpus_id
    assert scoped.corpus_id != base.corpus_id


def test_observed_at_change_changes_corpus_id():
    base = corpus("a", "b", "c")
    later = ag.ReflectionCorpus(items=(
        item("a"), item("b", observed_at="2026-09-20T00:00:00Z"), item("c")))
    assert later.corpus_id != base.corpus_id


def test_item_field_validation_refuses_bad_shapes():
    assert error(item, "a", observed_at="2026-09-19 20:00:00").code == ag.ALLY_GEN_BAD_ITEM
    assert error(item, "a", observed_at="2026-13-99T00:00:00Z").code == ag.ALLY_GEN_BAD_ITEM
    assert error(item, "a", content=" ").code == ag.ALLY_GEN_BAD_ITEM
    assert error(item, "a", content="bad\x00content").code == ag.ALLY_GEN_BAD_ITEM
    assert error(ag.ReflectionItem, evidence_ref="sha256:UPPER", source_domain=ag.PROJECT_OPERATIONAL,
                 observed_at=CREATED, observed_scope="scope", content="body",
                 event_ref=ref("event-a")).code == (
        ag.ALLY_GEN_BAD_ITEM)


def test_corpus_retains_no_mutable_caller_collection():
    caller_items = [item("a"), item("b"), item("c")]
    built = ag.ReflectionCorpus(items=caller_items)
    caller_items.append(item("d"))
    caller_items.reverse()
    assert tuple(entry.evidence_ref for entry in built.items) == tuple(
        sorted(ref(tag) for tag in ("a", "b", "c")))


def test_corpus_has_no_store_or_persistence_surface():
    source = inspect.getsource(ag)
    for forbidden in ("class ReflectionCorpusStore", "class HumanPatternStore",
                      "class PersonalityProfile", "class AdviceHistoryProfile",
                      "class TraitDatabase", "open(", "write_bytes", "write_text"):
        assert forbidden not in source
