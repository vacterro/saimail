"""ALLY1 evidence existence gate and non-transferable proof type-state."""

import dataclasses
import hashlib

import pytest

from sailang.errors import SailangError
from saimail import ally_advice as aa


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode()).hexdigest()


def refs(*tags):
    return tuple(sorted(ref(tag) for tag in tags))


def advice(**changes):
    values = {
        "created": "2026-09-19T19:00:00Z",
        "work_context": "work context",
        "observed_scope": "bounded scope",
        "observed": (
            aa.AdviceObservation("first observation", refs("o1", "o2")),
            aa.AdviceObservation("second observation", refs("o3")),
        ),
        "inferred": "an operational interpretation",
        "guidance_mode": aa.OBSERVE_ONLY,
        "suggested": "No action is proposed.",
        "counterevidence": (aa.AdviceCounterevidence("weakening case", refs("c1")),),
        "uncertainty": "The sample may not generalize.",
    }
    values.update(changes)
    return aa.AllyAdvice(**values)


class Resolver:
    def __init__(self, existing, *, invalid=None):
        self.existing = set(existing)
        self.invalid = invalid
        self.calls = []

    def resolve(self, evidence_ref):
        self.calls.append(evidence_ref)
        if self.invalid is not None:
            return self.invalid
        return aa.EXISTS if evidence_ref in self.existing else aa.MISSING


def all_refs(item):
    return tuple(sorted({
        ref for part in (*item.observed, *item.counterevidence)
        for ref in part.evidence_refs
    }))


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def test_all_refs_exist_mints_narrow_resolved_type():
    item = advice()
    resolver = Resolver(all_refs(item))
    resolved = aa.resolve_ally_evidence(item, resolver)
    assert isinstance(resolved, aa.EvidenceResolvedAllyAdvice)
    assert resolved.advice is item
    assert resolved.resolved_refs == all_refs(item)
    assert resolver.calls == list(all_refs(item))


def test_missing_resolver_refuses_before_any_private_conversion():
    assert error(aa.resolve_ally_evidence, advice()).code == \
        aa.ALLY_EVIDENCE_RESOLUTION_REQUIRED


def test_missing_observed_ref_refuses():
    item = advice()
    existing = set(all_refs(item)) - {ref("o2")}
    assert error(aa.resolve_ally_evidence, item, Resolver(existing)).code == \
        aa.ALLY_EVIDENCE_MISSING


def test_missing_counterevidence_ref_refuses():
    item = advice()
    existing = set(all_refs(item)) - {ref("c1")}
    assert error(aa.resolve_ally_evidence, item, Resolver(existing)).code == \
        aa.ALLY_EVIDENCE_MISSING


def test_invalid_resolver_and_invalid_outcome_refuse():
    item = advice()
    assert error(aa.resolve_ally_evidence, item, object()).code == \
        aa.ALLY_EVIDENCE_RESOLVER_INVALID
    noncallable = type("NoncallableResolver", (), {"resolve": aa.EXISTS})()
    assert error(aa.resolve_ally_evidence, item, noncallable).code == \
        aa.ALLY_EVIDENCE_RESOLVER_INVALID
    assert error(aa.resolve_ally_evidence, item,
                 Resolver(all_refs(item), invalid="SUPPORTED")).code == \
        aa.ALLY_EVIDENCE_RESOLVER_INVALID


def test_direct_resolved_construction_refuses():
    item = advice()
    assert error(aa.EvidenceResolvedAllyAdvice, item, all_refs(item)).code == \
        aa.ALLY_EVIDENCE_PROOF_FORGED


def test_dataclasses_replace_cannot_transplant_proof():
    item = advice()
    resolved = aa.resolve_ally_evidence(item, Resolver(all_refs(item)))
    with pytest.raises(SailangError) as caught:
        dataclasses.replace(resolved)
    assert caught.value.code == aa.ALLY_EVIDENCE_PROOF_FORGED


def test_unrelated_advice_cannot_inherit_another_resolution_proof():
    first = advice()
    resolved = aa.resolve_ally_evidence(first, Resolver(all_refs(first)))
    unrelated = advice(inferred="another inference")
    with pytest.raises(SailangError) as caught:
        dataclasses.replace(resolved, advice=unrelated)
    assert caught.value.code == aa.ALLY_EVIDENCE_PROOF_FORGED


def test_changed_evidence_ref_cannot_retain_resolution_proof():
    first = advice()
    resolved = aa.resolve_ally_evidence(first, Resolver(all_refs(first)))
    changed = advice(observed=(
        aa.AdviceObservation("first observation", refs("o1", "changed")),
        aa.AdviceObservation("second observation", refs("o3")),
    ))
    with pytest.raises(SailangError) as caught:
        dataclasses.replace(resolved, advice=changed)
    assert caught.value.code == aa.ALLY_EVIDENCE_PROOF_FORGED


def test_resolution_claims_existence_not_semantic_support():
    resolved_fields = {field.name for field in dataclasses.fields(
        aa.EvidenceResolvedAllyAdvice)}
    assert resolved_fields == {"advice", "resolved_refs"}
    assert "semantic" not in repr(aa.resolve_ally_evidence)
    assert "semantic support is unproven" in aa.EvidenceResolvedAllyAdvice.__doc__
    assert aa.ALLY_ADVICE_SUBJECT == "ALLY_ADVICE"


def test_resolved_state_is_immutable():
    item = advice()
    resolved = aa.resolve_ally_evidence(item, Resolver(all_refs(item)))
    with pytest.raises(dataclasses.FrozenInstanceError):
        resolved.resolved_refs = ()
