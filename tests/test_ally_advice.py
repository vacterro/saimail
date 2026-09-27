"""Canonical ALLY1 schema, epistemic separation, bounds and rendering."""

import dataclasses
import hashlib
import json

import pytest

from sailang.errors import SailangError
from sailang.record import KINDS
from saimail import ally_advice as aa


def ref(tag):
    return "sha256:" + hashlib.sha256(tag.encode("utf-8")).hexdigest()


def refs(*tags):
    return tuple(sorted(ref(tag) for tag in tags))


def advice(**changes):
    values = {
        "created": "2026-09-19T19:00:00Z",
        "work_context": "Architecture review\nacross two completed work waves.",
        "observed_scope": "Receiver-owned protocol decisions during this week.",
        "observed": (
            aa.AdviceObservation("Two decisions preceded uncertainty checks.", refs("o1", "o2")),
            aa.AdviceObservation("A later correction restored the missing gate.", refs("o3")),
        ),
        "inferred": "You may be committing to architecture before uncertainty is reduced.",
        "guidance_mode": aa.CONSIDER_CHANGE,
        "suggested": "Consider writing the falsification check before freezing the next design.",
        "counterevidence": (
            aa.AdviceCounterevidence(
                "The latest correction was initiated without external prompting.", refs("c1")),
        ),
        "uncertainty": "The sample is small and may reflect deadline pressure rather than a pattern.",
    }
    values.update(changes)
    return aa.AllyAdvice(**values)


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def canonical_object(item=None):
    return json.loads((item or advice()).render())


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()


def test_canonical_ally1_round_trip_is_exact_and_multiline_safe():
    original = advice()
    wire = original.render()
    assert wire.startswith(b'{"FORMAT":"ALLY1","CREATED":')
    assert wire.endswith(b"\n") and not wire.endswith(b"\n\n")
    assert aa.AllyAdvice.parse(wire) == original
    assert aa.AllyAdvice.parse(wire).render() == wire
    assert aa.AllyAdvice.parse(wire.decode("utf-8")) == original
    assert "\n" in original.work_context


def test_collections_are_snapshotted_as_immutable_tuples():
    evidence = list(refs("o1", "o2"))
    observation = aa.AdviceObservation("statement", evidence)
    observed = [observation, aa.AdviceObservation("second", refs("o3"))]
    counters = [aa.AdviceCounterevidence("weakens it", refs("c1"))]
    item = advice(observed=observed, counterevidence=counters)
    evidence.append(ref("late"))
    observed.clear()
    counters.clear()
    assert isinstance(item.observed, tuple)
    assert isinstance(item.counterevidence, tuple)
    assert observation.evidence_refs == refs("o1", "o2")
    assert len(item.observed) == 2 and len(item.counterevidence) == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.inferred = "changed"


def test_missing_unknown_and_duplicate_fields_refuse():
    missing = canonical_object()
    del missing["UNCERTAINTY"]
    assert error(aa.AllyAdvice.parse, encoded(missing)).code == aa.ALLY_MISSING_FIELD

    unknown = canonical_object()
    unknown["CONFIDENCE"] = 0.83
    assert error(aa.AllyAdvice.parse, encoded(unknown)).code == aa.ALLY_UNKNOWN_FIELD

    wire = advice().render().replace(
        b'{"FORMAT":"ALLY1",', b'{"FORMAT":"ALLY1","FORMAT":"ALLY1",', 1)
    assert error(aa.AllyAdvice.parse, wire).code == aa.ALLY_DUPLICATE_FIELD


def test_nested_unknown_and_duplicate_fields_refuse():
    unknown = canonical_object()
    unknown["INFERRED"]["CONFIDENCE"] = 0.83
    assert error(aa.AllyAdvice.parse, encoded(unknown)).code == aa.ALLY_UNKNOWN_FIELD

    wire = advice().render().replace(
        b'{"STATUS":"UNVERIFIED",',
        b'{"STATUS":"UNVERIFIED","STATUS":"UNVERIFIED",',
        1,
    )
    assert error(aa.AllyAdvice.parse, wire).code == aa.ALLY_DUPLICATE_FIELD


@pytest.mark.parametrize("mutate", [
    lambda wire: wire[:-1],
    lambda wire: wire.replace(b'":', b'": ', 1),
    lambda wire: b"\xef\xbb\xbf" + wire,
    lambda wire: wire.replace(b'{"FORMAT":"ALLY1","CREATED":',
                              b'{"CREATED":', 1).replace(
                                  b',"WORK_CONTEXT":',
                                  b',"FORMAT":"ALLY1","WORK_CONTEXT":', 1),
])
def test_equivalent_noncanonical_representations_refuse(mutate):
    assert error(aa.AllyAdvice.parse, mutate(advice().render())).code == aa.ALLY_NONCANONICAL


def test_malformed_utf8_and_non_object_json_refuse():
    assert error(aa.AllyAdvice.parse, b'\xff\n').code == aa.ALLY_BAD_UTF8
    assert error(aa.AllyAdvice.parse, b'[]\n').code == aa.ALLY_BAD_JSON


def test_individual_and_total_bounds_refuse_oversized_dossiers():
    assert error(advice, work_context="x" * (aa.MAX_CONTEXT_BYTES + 1)).code == \
        aa.ALLY_FIELD_OVERSIZE
    huge_observations = tuple(
        aa.AdviceObservation("x" * aa.MAX_PROSE_BYTES, refs(str(number)))
        for number in range(aa.MAX_OBSERVATIONS)
    )
    assert error(advice, observed=huge_observations).code == aa.ALLY_OVERSIZE
    assert error(aa.AllyAdvice.parse, b"x" * (aa.MAX_ALLY1_BYTES + 1)).code == \
        aa.ALLY_OVERSIZE


def test_observation_floor_requires_two_items_and_three_distinct_refs():
    one = (aa.AdviceObservation("only", refs("o1", "o2", "o3")),)
    assert error(advice, observed=one).code == aa.ALLY_OBSERVATION_FLOOR
    two_refs = (
        aa.AdviceObservation("first", refs("o1")),
        aa.AdviceObservation("second", refs("o2")),
    )
    assert error(advice, observed=two_refs).code == aa.ALLY_OBSERVATION_FLOOR
    allowed = advice(observed=(
        aa.AdviceObservation("first", refs("o1", "o2")),
        aa.AdviceObservation("second", refs("o3")),
    ))
    assert len({ref for item in allowed.observed for ref in item.evidence_refs}) == 3


def test_each_observation_requires_canonical_unique_evidence_refs():
    assert error(aa.AdviceObservation, "claim", ()).code == aa.ALLY_EVIDENCE_REF_INVALID
    assert error(aa.AdviceObservation, "claim", ("LOG-123",)).code == \
        aa.ALLY_EVIDENCE_REF_INVALID
    same = ref("same")
    assert error(aa.AdviceObservation, "claim", (same, same)).code == \
        aa.ALLY_EVIDENCE_REF_DUPLICATE
    unsorted = tuple(reversed(refs("a", "b")))
    assert error(aa.AdviceObservation, "claim", unsorted).code == aa.ALLY_EVIDENCE_REF_ORDER


def test_counterevidence_is_mandatory_cited_and_retained_exactly():
    assert error(advice, counterevidence=()).code == aa.ALLY_COUNTEREVIDENCE_REQUIRED
    assert error(aa.AdviceCounterevidence, "weakens", ()).code == \
        aa.ALLY_EVIDENCE_REF_INVALID
    for escape in ("NONE", "NO_COUNTEREVIDENCE_FOUND"):
        assert error(aa.AdviceCounterevidence, escape, refs("c1")).code == \
            aa.ALLY_COUNTEREVIDENCE_REQUIRED
    counter = aa.AdviceCounterevidence("exact\nmultiline", refs("c1", "c2"))
    parsed = aa.AllyAdvice.parse(advice(counterevidence=(counter,)).render())
    assert parsed.counterevidence == (counter,)


@pytest.mark.parametrize(("field", "value", "code"), [
    ("inference_status", "VERIFIED", aa.ALLY_BAD_INFERENCE_STATUS),
    ("guidance_status", "COMMAND", aa.ALLY_BAD_GUIDANCE_STATUS),
    ("guidance_mode", "MANDATE", aa.ALLY_BAD_GUIDANCE_MODE),
    ("agency", "MODEL_DECIDES", aa.ALLY_BAD_AGENCY),
])
def test_closed_epistemic_markers_refuse_alternatives(field, value, code):
    assert error(advice, **{field: value}).code == code


@pytest.mark.parametrize("mode", [aa.OBSERVE_ONLY, aa.CONSIDER_CHANGE])
def test_exact_two_guidance_modes_are_supported(mode):
    item = advice(guidance_mode=mode,
                  suggested="No action is proposed." if mode == aa.OBSERVE_ONLY
                  else "Consider one reversible change.")
    assert aa.AllyAdvice.parse(item.render()).guidance_mode == mode


def test_parser_refuses_changed_machine_markers():
    for section, field, value, code in (
        ("INFERRED", "STATUS", "TRUE", aa.ALLY_BAD_INFERENCE_STATUS),
        ("SUGGESTED", "STATUS", "REQUIREMENT", aa.ALLY_BAD_GUIDANCE_STATUS),
        ("SUGGESTED", "MODE", "COMMAND", aa.ALLY_BAD_GUIDANCE_MODE),
        (None, "AGENCY", "MODEL_DECIDES", aa.ALLY_BAD_AGENCY),
    ):
        obj = canonical_object()
        target = obj if section is None else obj[section]
        target[field] = value
        assert error(aa.AllyAdvice.parse, encoded(obj)).code == code


def test_renderer_surfaces_every_section_counterevidence_and_agency():
    item = advice()
    rendered = aa.render_ally_advice(item)
    headings = [
        "WORK CONTEXT", "OBSERVED", "SCOPE:", "INFERRED — UNVERIFIED",
        "SUGGESTED — PROPOSAL", "COUNTEREVIDENCE", "UNCERTAINTY",
        "AGENCY — RECIPIENT DECIDES",
    ]
    positions = [rendered.index(heading) for heading in headings]
    assert positions == sorted(positions)
    for evidence_ref in {ref for entry in (*item.observed, *item.counterevidence)
                         for ref in entry.evidence_refs}:
        assert evidence_ref in rendered
    assert item.counterevidence[0].statement in rendered


def test_schema_has_no_motive_priority_confidence_or_reward_surface():
    names = {field.name for field in dataclasses.fields(aa.AllyAdvice)}
    forbidden = {
        "motive", "personality", "trait", "diagnosis", "confidence", "priority",
        "allocation", "deferral_policy", "compliance", "open_rate", "helpfulness_score",
    }
    assert names.isdisjoint(forbidden)
    keys = set(canonical_object())
    assert keys.isdisjoint({name.upper() for name in forbidden})


def test_ally_advice_is_not_a_sailang_kind():
    assert "ALLY_ADVICE" not in KINDS
    assert aa.FORMAT == "ALLY1"


def test_created_is_sender_metadata_not_an_attention_control_surface():
    item = advice(created="2000-01-01T00:00:00Z")
    assert aa.AllyAdvice.parse(item.render()).created == "2000-01-01T00:00:00Z"
    assert set(canonical_object(item)).isdisjoint(
        {"ENQUEUED_AT", "PRESENTED_AT", "ALLOCATION", "DEFERRAL_POLICY", "PRIORITY"})
