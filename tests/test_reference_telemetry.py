"""FG-04A reference telemetry: classification, privacy, bounds, history.

The observer must classify exactly, persist no plaintext, repair nothing and
hold no acceptance authority. Historical T-74 evidence stays read-only.
"""

import hashlib
import json
import pathlib
import socket

import pytest

from lab import reference_telemetry as rt
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag

ROOT = pathlib.Path(__file__).resolve().parent.parent
CREATED = "2026-09-20T00:00:00Z"

T74_LIVE_ARTIFACT = ROOT / "lab" / "out" / "project_corpus_budget4096_live_20260920T005752Z.json"
T74_PINS = {
    "lab/out/project_corpus_budget4096_live_20260920T005752Z.json":
        "0af0735ade363c9e2fc96d84de1a5768263031053c52b15b805bbd4d2bd61474",
    "lab/out/PROJECT_CORPUS_BUDGET4096_REPORT_20260920T005752Z.md":
        "bdbb9158d3073ea7df809c755195d1cf467adeeee0fdaf86c33ddde92a290982",
    "lab/analysis/project_corpus_budget4096_20260920T005752Z.md":
        "bdbb9158d3073ea7df809c755195d1cf467adeeee0fdaf86c33ddde92a290982",
    "lab/analysis/project_corpus_budget4096_closure.md":
        "28c182a1698f1293cf5da72636176480766377f8232e2992a3dbcf1ed1af0ea4",
}

BANNED_TELEMETRY_KEYS = frozenset({
    "preview", "raw_ref", "raw_value", "statement", "model_text",
    "prefix", "suffix", "nearest_ref", "edit_distance", "similarity",
})


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


def candidate(observed, counter, *, work_context="work context",
              observed_scope="one scope", inferred="inferred text",
              suggested="suggested text", uncertainty="uncertainty text"):
    return aa.AllyAdvice(
        created=CREATED,
        work_context=work_context,
        observed_scope=observed_scope,
        observed=tuple(aa.AdviceObservation("observed statement.", tuple(sorted(group)))
                       for group in observed),
        inferred=inferred,
        guidance_mode=aa.CONSIDER_CHANGE,
        suggested=suggested,
        counterevidence=tuple(aa.AdviceCounterevidence("counter statement.", tuple(sorted(group)))
                              for group in counter),
        uncertainty=uncertainty,
    )


def payload(result):
    return rt.serialize_reference_telemetry(result).decode("utf-8")


def object_of(result):
    return json.loads(payload(result))


def malformed_value():
    return SailangError


# --------------------------------------------------------------------
# classification (1-6)
# --------------------------------------------------------------------


def test_known_evidence_ref_is_exactly_corpus_membership():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.known_evidence_ref_count == 4
    assert result.unknown_or_invalid_ref_count == 0
    assert result.corpus_ref_relation == rt.CLEAN
    assert rt.classify_reference_value(ref("o1"), source) == rt.KNOWN_EVIDENCE_REF


def test_event_ref_used_as_evidence_is_not_unknown_canonical():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    event_ref = source.item_for(ref("o1")).event_ref
    assert rt.classify_reference_value(event_ref, source) == rt.KNOWN_EVENT_REF_AS_EVIDENCE
    item = candidate(
        ((ref("o1"), ref("o2")), (event_ref,)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.known_event_ref_as_evidence_count == 1
    assert result.unknown_canonical_ref_count == 0
    # an event ref is never mapped to, or counted as, member evidence
    assert result.known_evidence_ref_count == 3
    assert result.known_observed_evidence_ref_count == 2
    assert result.corpus_ref_relation == rt.HAS_IDENTIFIER_TYPE_CONFUSION


def test_corpus_id_used_as_evidence_is_a_confusion_not_an_unknown():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    assert rt.classify_reference_value(source.corpus_id, source) == rt.CORPUS_ID_AS_EVIDENCE
    item = candidate(
        ((ref("o1"), ref("o2")), (source.corpus_id,)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.corpus_id_as_evidence_count == 1
    assert result.unknown_canonical_ref_count == 0
    assert result.corpus_ref_relation == rt.HAS_IDENTIFIER_TYPE_CONFUSION


def test_unknown_canonical_ref_is_shape_only_identity():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    unknown = ref("not-in-this-corpus")
    assert rt.classify_reference_value(unknown, source) == rt.UNKNOWN_CANONICAL_REF
    assert rt.classify_reference_value(unknown) == rt.UNKNOWN_CANONICAL_REF
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"), unknown)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.unknown_canonical_ref_count == 1
    assert result.corpus_ref_relation == rt.HAS_OUTSIDE_CANONICAL


@pytest.mark.parametrize("value", [
    "0" * 64,                       # missing sha256: prefix
    "sha256:" + "A" * 64,           # uppercase hex
    "sha256:" + "a" * 63,           # 63 hex characters
    "sha256:" + "a" * 65,           # 65 hex characters
    "sha256:" + "g" + "a" * 63,     # non-hex character
    " sha256:" + "a" * 64,          # leading whitespace
    "sha256:" + "a" * 64 + " ",     # trailing whitespace
    "",                             # blank string
    "\ud800",                       # text that is not strict UTF-8
])
def test_malformed_matrix(value):
    source = corpus("o1", "o2", "o3", "c1")
    assert rt.classify_reference_value(value, source) == rt.MALFORMED_REF
    result = rt.observe_raw_references([value], [], corpus=source)
    assert result.malformed_ref_count == 1
    assert result.corpus_ref_relation == rt.HAS_MALFORMED
    if value:
        assert value not in payload(result)


def test_non_text_values_are_classified_without_repr():
    values = [None, 42, [1, 2, 3], {"k": "v"}]
    assert [rt.classify_reference_value(value) for value in values] == [rt.NON_TEXT_REF] * 4
    result = rt.observe_raw_references(values, [])
    assert result.non_text_ref_count == 4
    assert result.corpus_ref_relation == rt.HAS_NON_TEXT
    text = payload(result)
    for fragment in ("None", "[1, 2, 3]", "{'k': 'v'}", "dict", "list"):
        assert fragment not in text


def test_mixed_invalid_categories_report_mixed():
    result = rt.observe_raw_references([ref("unknown")], ["not-a-ref"])
    assert result.unknown_canonical_ref_count == 1
    assert result.malformed_ref_count == 1
    assert result.corpus_ref_relation == rt.MIXED_INVALID


# --------------------------------------------------------------------
# field distribution (7-11)
# --------------------------------------------------------------------


def test_observed_occurrences_count_repeats():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(((ref("o1"), ref("o2")), (ref("o1"), ref("o3"))), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.observed_ref_occurrences == 4
    assert result.observed_unique_ref_tokens == 3


def test_counterevidence_occurrences_count_each_item():
    source = corpus("o1", "o2", "o3", "c1", "c2", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"),)),
        ((ref("c1"),), (ref("c2"),)))
    result = rt.observe_candidate_references(item, source)
    assert result.counterevidence_ref_occurrences == 2
    assert result.counterevidence_unique_ref_tokens == 2


def test_observed_unknown_count_lands_in_the_observed_field():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"), ref("outside"))), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.observed_unknown_or_invalid_ref_count == 1
    assert result.counterevidence_unknown_or_invalid_ref_count == 0


def test_counterevidence_unknown_count_lands_in_its_own_field():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"), ref("outside")),))
    result = rt.observe_candidate_references(item, source)
    assert result.observed_unknown_or_invalid_ref_count == 0
    assert result.counterevidence_unknown_or_invalid_ref_count == 1
    assert result.unknown_canonical_ref_count == 1


def test_same_unknown_token_in_both_fields_is_one_unique_token():
    unknown = ref("shared-unknown")
    result = rt.observe_raw_references([unknown], [unknown])
    assert result.observed_ref_occurrences == 1
    assert result.counterevidence_ref_occurrences == 1
    assert result.observed_unique_ref_tokens == 1
    assert result.counterevidence_unique_ref_tokens == 1
    assert result.unknown_or_invalid_unique_token_count == 1
    assert result.unknown_or_invalid_fingerprints == (
        rt.reference_fingerprint(unknown),)


# --------------------------------------------------------------------
# event coverage (12-16)
# --------------------------------------------------------------------


def test_two_known_observed_events_met():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.known_observed_evidence_ref_count == 3
    assert result.known_observed_distinct_event_count == 2
    assert result.event_floor_relation == rt.MET


def test_one_known_observed_event_is_not_met():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "A"})
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.known_observed_distinct_event_count == 1
    assert result.event_floor_relation == rt.NOT_MET


def test_unknown_observed_ref_makes_the_floor_not_evaluable():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"), ref("outside"))), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert result.known_observed_distinct_event_count >= 2
    assert result.event_floor_relation == rt.NOT_EVALUABLE


def test_malformed_observed_ref_makes_the_floor_not_evaluable():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    result = rt.observe_raw_references(
        [ref("o1"), ref("o2"), ref("o3"), "not-a-ref"], [], corpus=source)
    assert result.event_floor_relation == rt.NOT_EVALUABLE


def test_unknown_counterevidence_does_not_rewrite_the_observed_event_count():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"), ref("outside")),))
    result = rt.observe_candidate_references(item, source)
    assert result.known_observed_distinct_event_count == 2
    assert result.event_floor_relation == rt.MET
    assert result.counterevidence_unknown_or_invalid_ref_count == 1
    assert result.corpus_ref_relation == rt.HAS_OUTSIDE_CANONICAL


# --------------------------------------------------------------------
# privacy (24-31)
# --------------------------------------------------------------------


def test_malformed_token_plaintext_is_absent_and_fingerprint_remains():
    canary = "PRIVATE_REFERENCE_CANARY_24"
    result = rt.observe_raw_references([canary], [])
    assert result.malformed_ref_count == 1
    text = payload(result)
    assert canary not in text
    assert result.unknown_or_invalid_fingerprints == (rt.reference_fingerprint(canary),)


def test_unknown_arbitrary_text_plaintext_is_absent():
    token = "please-cite-this-document-as-evidence"
    result = rt.observe_raw_references([token], [])
    text = payload(result)
    assert token not in text
    assert "please" not in text


def test_non_text_values_leave_no_repr_in_serialized_telemetry():
    result = rt.observe_raw_references([[1, 2, 3]], [{"k": "v"}])
    text = payload(result)
    assert "[1" not in text and "1, 2, 3" not in text
    assert "{'k'" not in text and "'v'" not in text


@pytest.mark.parametrize("field,canary", [
    ("work_context", "CANARY_WORK_CONTEXT_27"),
    ("observed_scope", "CANARY_OBSERVED_SCOPE_27"),
    ("inferred", "CANARY_INFERRED_27"),
    ("suggested", "CANARY_SUGGESTED_29"),
    ("uncertainty", "CANARY_UNCERTAINTY_30"),
])
def test_no_authored_prose_is_retained(field, canary):
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),),
                     **{field: canary})
    result = rt.observe_candidate_references(item, source)
    assert canary not in payload(result)


def test_statements_are_never_retained():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),),
                     work_context="CANARY_STATEMENT_CONTEXT",
                     inferred="CANARY_STATEMENT_INFERRED")
    result = rt.observe_candidate_references(item, source)
    text = payload(result)
    assert "CANARY_STATEMENT" not in text


def test_fingerprint_is_deterministic_and_domain_separated():
    token = ref("fingerprint-token")
    expected = hashlib.sha256(
        rt.FINGERPRINT_DOMAIN + token.encode("utf-8")).hexdigest()
    assert rt.reference_fingerprint(token) == expected
    assert rt.reference_fingerprint(token) == rt.reference_fingerprint(token)
    assert rt.reference_fingerprint(token) != rt.reference_fingerprint(ref("other"))
    assert rt.FINGERPRINT_DOMAIN == b"SAIMAIL-REFERENCE-TELEMETRY1\x00"


# --------------------------------------------------------------------
# bounds and purity (32-37)
# --------------------------------------------------------------------


def test_raw_token_count_is_bounded_by_one_candidate():
    assert rt.MAX_REF_OCCURRENCES == (
        aa.MAX_OBSERVATIONS * aa.MAX_EVIDENCE_REFS_PER_ITEM
        + aa.MAX_COUNTEREVIDENCE * aa.MAX_EVIDENCE_REFS_PER_ITEM)
    observed = [f"malformed-observed-{index}" for index in range(256)]
    counterevidence = [f"malformed-counter-{index}" for index in range(128)]
    result = rt.observe_raw_references(observed, counterevidence)
    assert result.observed_ref_occurrences == 256
    assert result.counterevidence_ref_occurrences == 128
    with pytest.raises(SailangError) as excinfo:
        rt.observe_raw_references(observed, [*counterevidence, "one-more"])
    assert excinfo.value.code == rt.REFERENCE_TELEMETRY_CAP_EXCEEDED


def test_a_bare_string_is_not_a_token_collection():
    with pytest.raises(SailangError) as excinfo:
        rt.observe_raw_references("sha256:" + "a" * 64, [])
    assert excinfo.value.code == rt.REFERENCE_TELEMETRY_BAD_INPUT


def test_observer_does_not_open_files(monkeypatch):
    def exploding_open(*args, **kwargs):
        raise AssertionError("the observer opened a file")

    monkeypatch.setattr("builtins.open", exploding_open)
    result = rt.observe_raw_references(["not-a-ref"], [ref("unknown")])
    assert result.malformed_ref_count == 1


def test_observer_does_not_touch_the_network(monkeypatch):
    def exploding_socket(*args, **kwargs):
        raise AssertionError("the observer opened a socket")

    monkeypatch.setattr(socket, "socket", exploding_socket)
    result = rt.observe_raw_references([], [])
    assert result.observed_ref_occurrences == 0
    assert rt.serialize_reference_telemetry(result)


def test_module_has_no_filesystem_network_or_model_surface():
    source = (ROOT / "lab" / "reference_telemetry.py").read_text(encoding="utf-8")
    for forbidden in ("pathlib", "import os", "socket", "urllib", "requests",
                      "httpx", "subprocess", "open(", "generate_reviewed_ally_advice"):
        assert forbidden not in source, f"reference_telemetry.py reaches {forbidden!r}"


def test_membership_never_looks_beyond_the_supplied_corpus():
    source = corpus("o1", "o2", "o3")
    token = ref("o1")
    assert rt.classify_reference_value(token, source) == rt.KNOWN_EVIDENCE_REF
    assert rt.classify_reference_value(token) == rt.UNKNOWN_CANONICAL_REF
    elsewhere = corpus("o1", "x")
    assert rt.classify_reference_value(token, elsewhere) == rt.KNOWN_EVIDENCE_REF


@pytest.mark.parametrize("value,expected", [
    ("sha256:" + "A" * 64, rt.MALFORMED_REF),
    ("sha256:" + "a" * 64 + " ", rt.MALFORMED_REF),
    (" sha256:" + "a" * 64, rt.MALFORMED_REF),
    ("a" * 64, rt.MALFORMED_REF),
])
def test_no_normalization_repairs_a_token(value, expected):
    assert rt.classify_reference_value(value) == expected


def test_near_match_ref_is_unknown_and_never_repaired():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    known = ref("o1")
    flipped = known[:-1] + ("0" if known[-1] != "0" else "1")
    assert flipped != known and len(flipped) == len(known)
    item = candidate(
        ((ref("o1"), ref("o2")), (ref("o3"), flipped)), ((ref("c1"),),))
    result = rt.observe_candidate_references(item, source)
    assert rt.classify_reference_value(flipped, source) == rt.UNKNOWN_CANONICAL_REF
    assert result.unknown_canonical_ref_count == 1
    assert result.known_evidence_ref_count == 4
    text = payload(result)
    for label in ("NEAR_MATCH", "TYPO", "LIKELY_INTENDED_REF", "PROBABLY_MEANT",
                  "nearest", "edit_distance", "similarity"):
        assert label not in text
    source_text = (ROOT / "lab" / "reference_telemetry.py").read_text(encoding="utf-8")
    for forbidden in ("edit_distance", "Levenshtein", "nearest_ref", "LIKELY_TYPO"):
        assert forbidden not in source_text


# --------------------------------------------------------------------
# closed schema
# --------------------------------------------------------------------


def test_serialization_schema_is_closed():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),))
    obj = object_of(rt.observe_candidate_references(item, source))
    assert set(obj) == set(rt.TELEMETRY_SCHEMA)
    assert not BANNED_TELEMETRY_KEYS & set(obj)
    forged = dict(obj)
    forged["preview"] = "leak"
    with pytest.raises(SailangError) as excinfo:
        rt.validate_reference_telemetry_object(forged)
    assert excinfo.value.code == rt.REFERENCE_TELEMETRY_SCHEMA_REFUSED
    forged = dict(obj)
    forged["observed_ref_occurrences"] = "three"
    with pytest.raises(SailangError):
        rt.validate_reference_telemetry_object(forged)


def test_construction_refuses_unknown_or_missing_fields():
    source = corpus("o1", "o2", "o3", "c1", events={"o1": "A", "o2": "A", "o3": "B"})
    item = candidate(((ref("o1"), ref("o2")), (ref("o3"),)), ((ref("c1"),),))
    fields = rt.observe_candidate_references(item, source).to_object()
    with pytest.raises(SailangError) as excinfo:
        rt.ReferenceTelemetry(**{**fields, "raw_ref": "x"})
    assert excinfo.value.code == rt.REFERENCE_TELEMETRY_SCHEMA_REFUSED
    missing = {key: value for key, value in fields.items() if key != "version"}
    with pytest.raises(SailangError):
        rt.ReferenceTelemetry(**missing)


# --------------------------------------------------------------------
# historical T-74 control (38-42)
# --------------------------------------------------------------------


def test_t74_durable_metadata_is_the_bounded_historical_control():
    artifact = json.loads(T74_LIVE_ARTIFACT.read_text(encoding="utf-8"))
    replicate = artifact["replicates"][0]
    assert replicate["outside_ref_count"] == 1
    assert replicate["outcome_code"] == "ALLY_GENERATED_REF_OUTSIDE_CORPUS"
    assert replicate["reviewer_calls"] == 0
    assert replicate["candidate_emitted"] is True


def test_t74_artifact_report_and_analysis_remain_hash_pinned():
    for rel, expected in T74_PINS.items():
        digest = hashlib.sha256((ROOT / rel).read_bytes()).hexdigest()
        assert digest == expected, f"{rel} changed"


def test_t74_exact_bad_ref_class_remains_unknown():
    spec = (ROOT / "spec" / "14-REFERENCE-TELEMETRY-v0.md").read_text(encoding="utf-8")
    assert "T74_EXACT_REF_CLASS = UNKNOWN_FROM_RETAINED_EVIDENCE" in spec
    assert "T-74 is never" in spec
    source = (ROOT / "lab" / "reference_telemetry.py").read_text(encoding="utf-8")
    assert "KNOWN_EVENT_REF_AS_EVIDENCE" in source
    assert "T74_EXACT_REF_CLASS" not in source


def test_telemetry_has_no_stored_historical_classification():
    artifact = json.loads(T74_LIVE_ARTIFACT.read_text(encoding="utf-8"))
    assert artifact["historical_shape"] == "UNKNOWN_BYTES_DISCARDED"
    result = rt.observe_raw_references([], [])
    assert result.version == rt.CONTRACT_VERSION
    assert rt.CONTRACT_VERSION == "REFERENCE-TELEMETRY-1"
