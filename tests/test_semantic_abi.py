"""Semantic ABI conformance: WIRE / EXPECTED_TYPED_MEANING / FORBIDDEN_INTERPRETATIONS.

    DISAGREEMENT ABOUT REALITY IS ALLOWED.
    AMBIGUITY ABOUT PROTOCOL SEMANTICS IS NOT.

Two people may argue about whether a claim is true. They may not argue about
what the record describing that argument means. Every fixture below therefore
states one exact typed meaning and a list of plausible misreadings that must
NOT be what the wire decodes to.

Field-level forbidden interpretations are enforced mechanically. Prose-level
ones ("this means the evidence is weak") are enforced structurally instead:
the ABI provides no field in which such a reading could be encoded, and a test
asserts that absence. Where neither is possible the reading is documented and
labelled as documentation, not as a passing check.
"""

import pytest

from saimail.acceptance import ProfileRegistry
from sailang import Record, SailangError
from sailang.frame import Batch, Profile, decode, project, project_batch

T = "2026-09-17T08:41:00Z"
REF = "sha256:" + "a" * 64


@pytest.fixture(scope="module")
def profile():
    return Profile.load("1")


def accepted(profile):
    """The receiver's acceptance capability, minted as a receiver would."""
    return ProfileRegistry.with_profiles(profile).resolve(profile.id)


def view(record, profile):
    return decode(project(record, profile))


def rec(**over):
    fields = dict(KIND="F", SRC="AGENT:a17", SUBJ="queue", CLAIM="RETRY", TYPE="INT",
                  EV="0", STATUS="U1", CREATED=T)
    fields.update(over)
    for key in [k for k, v in fields.items() if v is None]:
        del fields[key]
    return Record.create(**fields)


# --------------------------------------------------------------------
# 1. evidence absent is not evidence weak
# --------------------------------------------------------------------


ABI_EVIDENCE = {
    "wire_slot": "EV0",
    "expected": "No admissible evidence reference is attached to this claim.",
    "forbidden_prose": [
        "the evidence is weak",
        "the agent is unsure",
        "the claim is probably false",
        "the claim was rejected",
    ],
}


def test_evidence_absent_means_exactly_one_thing(profile):
    absent = view(rec(EV="0", STATUS="U1"), profile)
    present = view(rec(EV=REF, STATUS="U2"), profile)
    assert absent.has_evidence is False
    assert present.has_evidence is True
    # EXPECTED: a boolean about attachment. FORBIDDEN: any gradation of quality.
    evidence_fields = sorted(name for name in vars(absent) if "evidence" in name or name == "ev")
    assert evidence_fields == ["evidence_state", "has_evidence"], (
        "the ABI must offer no field in which 'weak evidence' could be encoded; "
        f"found {evidence_fields}"
    )
    assert absent.evidence_state == "EVIDENCE_EXPLICITLY_ABSENT"
    assert present.evidence_state == "EVIDENCE_ATTACHED"
    assert isinstance(absent.has_evidence, bool)


def test_evidence_absence_is_independent_of_the_rung(profile):
    # U0 and U1 both with EV0: the rung says how confident, the flag says
    # whether anything is attached. Conflating them is the misreading.
    for status in ("U0", "U1"):
        v = view(rec(EV="0", STATUS=status), profile)
        assert v.has_evidence is False and v.status == status


# --------------------------------------------------------------------
# 2. BLOCKED is not BLOCKER
# --------------------------------------------------------------------


def test_blocked_and_blocker_decode_to_different_atoms(profile):
    blocked = view(rec(CLAIM="BLOCKED>DEPENDENCY"), profile)
    blocker = view(rec(CLAIM="BLOCKER>DEPENDENCY"), profile)
    assert blocked.claim_atoms == ("BLOCKED", "DEPENDENCY")
    assert blocker.claim_atoms == ("BLOCKER", "DEPENDENCY")
    # FORBIDDEN: the two collapsing to one meaning, at any layer.
    assert blocked.claim_atoms != blocker.claim_atoms
    assert blocked.claim_token != blocker.claim_token
    assert profile.atom_to_wire["BLOCKED"] != profile.atom_to_wire["BLOCKER"]


# --------------------------------------------------------------------
# 3. a factual claim is not a hypothesis
# --------------------------------------------------------------------


def test_fact_and_hypothesis_are_distinct_at_the_type_level(profile):
    fact = view(rec(KIND="F", CLAIM="RETRY>DUPLICATE_EXECUTION"), profile)
    hypothesis = view(Record.create(
        KIND="H", SRC="AGENT:a17", SUBJ="queue", CLAIM="RETRY>DUPLICATE_EXECUTION",
        TYPE="INT", FALSIFY="a fresh owner still duplicates", EV="0", STATUS="U1",
        CREATED=T), profile)
    assert fact.kind == "F" and hypothesis.kind == "H"
    assert hypothesis.falsifiable is True
    assert fact.falsifiable is False
    # FORBIDDEN: reading the hypothesis as a fact because their claims match.
    assert fact.claim_atoms == hypothesis.claim_atoms
    assert fact.kind != hypothesis.kind


def test_a_hypothesis_cannot_be_authored_at_the_verified_rung():
    with pytest.raises(SailangError) as excinfo:
        Record.create(KIND="H", SRC="AGENT:a", SUBJ="queue", CLAIM="RETRY",
                      TYPE="INT", FALSIFY="x", EV=REF, STATUS="U4", CREATED=T)
    assert excinfo.value.code == "RUNG_ABOVE_KIND_CEILING"


# --------------------------------------------------------------------
# 4. a goal or value is not truth-apt
# --------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["G", "V"])
def test_goal_and_value_carry_no_truth_verdict(kind, profile):
    v = view(Record.create(KIND=kind, SRC="HUMAN:vacterro", SUBJ="queue",
                           CLAIM="make duplicates impossible", CREATED=T), profile)
    assert v.kind == kind
    # EXPECTED: no rung, no evidence claim. FORBIDDEN: reading absence as U0,
    # or as "an unsupported factual claim".
    assert v.status is None
    assert v.evidence_state == "EVIDENCE_NOT_APPLICABLE"
    assert v.has_evidence is None
    assert v.is_evidence_applicable is False
    assert v.status != "U0"


def test_hostile_ev0_is_not_weak_evidence(profile):
    v = view(rec(EV="0", STATUS="U1"), profile)
    # EV:0 is attachment semantics only; no gradation of evidence quality exists in ABI
    assert v.evidence_state == "EVIDENCE_EXPLICITLY_ABSENT"
    assert not hasattr(v, "evidence_strength")
    assert not hasattr(v, "evidence_quality")
    assert not hasattr(v, "pconf")


def test_hostile_ev0_is_not_false_claim(profile):
    v = view(rec(EV="0", STATUS="U1"), profile)
    # A claim with EV:0 is not marked refuted or conflict or false
    assert v.refutes is False
    assert v.conflict is False
    assert v.status == "U1"  # unverified, not false/disproven


def test_hostile_ev0_is_not_claim_that_no_evidence_exists_in_world(profile):
    # EV:0 asserts absence of attached admissible ref in this packet, NOT nonexistence in reality
    v = view(rec(EV="0", STATUS="U1"), profile)
    assert v.evidence_state == "EVIDENCE_EXPLICITLY_ABSENT"
    assert v.is_evidence_absent is True
    # The record does not make an existential claim about world evidence
    assert not hasattr(v, "external_evidence")


def test_hostile_unverified_fact_is_not_a_hypothesis(profile):
    # Kind and rung are independent: U0/U1 Fact is NOT a Hypothesis
    fact_u1 = view(rec(KIND="F", EV="0", STATUS="U1"), profile)
    fact_u0 = view(rec(KIND="F", EV="0", STATUS="U0"), profile)
    assert fact_u1.kind == "F" and fact_u1.falsifiable is False
    assert fact_u0.kind == "F" and fact_u0.falsifiable is False
    assert fact_u1.kind != "H"


@pytest.mark.parametrize("field,value", [("STATUS", "U2"), ("EV", REF), ("FALSIFY", "x")])
def test_the_schema_refuses_to_make_a_goal_truth_apt(field, value):
    fields = dict(KIND="G", SRC="HUMAN:a", SUBJ="queue", CLAIM="be simpler", CREATED=T)
    fields[field] = value
    with pytest.raises(SailangError) as excinfo:
        Record.create(**fields)
    assert excinfo.value.code == "FIELD_FORBIDDEN_FOR_KIND"


# --------------------------------------------------------------------
# 5. contradiction is a ledger state, not an authored confidence
# --------------------------------------------------------------------


@pytest.mark.parametrize("verdict", ["C", "D"])
def test_ledger_verdicts_cannot_be_authored_in_a_record(verdict):
    with pytest.raises(SailangError) as excinfo:
        Record.create(KIND="F", SRC="AGENT:a", SUBJ="queue", CLAIM="RETRY",
                      TYPE="INT", EV="0", STATUS=verdict, CREATED=T)
    assert excinfo.value.code == "LEDGER_VERDICT_IN_RECORD"


@pytest.mark.parametrize("verdict", ["C", "D"])
def test_ledger_verdicts_cannot_appear_in_a_frame(verdict, profile):
    from sailang.frame import _bind_verified as bind_verified

    with pytest.raises(SailangError) as excinfo:
        decode(bind_verified(f"F|queue|{verdict}|EV0|RETRY|-", profile))
    assert excinfo.value.code == "BAD_FRAME"


def test_a_refutation_is_carried_as_a_relation_not_as_a_rung(profile):
    v = view(rec(EV=REF, STATUS="U4", REFUTES=REF), profile)
    assert v.refutes is True
    # EXPECTED: the refuting record is confident about its OWN claim.
    # FORBIDDEN: reading U4 as "the refuted claim is now U4".
    assert v.status == "U4"
    assert v.claim_atoms == ("RETRY",)


# --------------------------------------------------------------------
# 6. an unknown token stays unknown
# --------------------------------------------------------------------


def test_an_unknown_wire_token_is_reported_not_resolved(profile):
    v = view(rec(CLAIM="WOMBAT_SUBSYSTEM>RETRY"), profile)
    assert v.claim_unknown_wires == ("WOMBAT_SUBSYSTEM",)
    assert v.claim_atoms == ("RETRY",)
    # FORBIDDEN: silently mapping it to the nearest-looking atom, or dropping it.
    assert "WOMBAT_SUBSYSTEM" not in v.claim_atoms
    assert v.has_unknown_atoms is True


def test_an_unknown_token_does_not_make_the_frame_invalid(profile):
    # Unknown is a state a reader must act on, not a parse error.
    v = view(rec(CLAIM="ZEPHYR_LAYER"), profile)
    assert v.kind == "F" and v.has_unknown_atoms


# --------------------------------------------------------------------
# 7. open record means open the record
# --------------------------------------------------------------------


def test_open_record_is_a_requirement_not_a_hint(profile):
    v = view(rec(CLAIM="stale ownership survives a retry"), profile)
    assert v.claim_open_record is True
    # EXPECTED: nothing about the claim is available. FORBIDDEN: a summary,
    # a truncation, or an empty-but-present claim that reads as "no claim".
    assert v.claim_atoms == ()
    assert v.claim_token is None
    assert v.claim_shape is None
    assert v.claim_value is None


# --------------------------------------------------------------------
# 8. profile mismatch refuses rather than reinterprets
# --------------------------------------------------------------------


def test_a_container_under_another_profile_is_refused(profile):
    other = Profile.inline("other", {"RETRY": {"wire": "RTY", "render": "a retry"}})
    container = project_batch([rec()], profile).render()
    with pytest.raises(SailangError) as excinfo:
        Batch.parse(container, accepted(other))
    assert excinfo.value.code == "PROFILE_MISMATCH"


def test_the_same_wire_under_two_profiles_is_never_silently_the_same(profile):
    other = Profile.inline("other", {"RETRY": {"wire": "QSTALE", "render": "something else"}})
    assert other.id != profile.id
    assert profile.to_atom("QSTALE") == "QUEUE_OWNERSHIP_STALE"
    assert other.to_atom("QSTALE") == "RETRY"
    # The wire token is identical and the meaning is not. That is precisely why
    # the container binds a profile digest rather than a version number.
    assert profile.dictionary_digest != other.dictionary_digest


# --------------------------------------------------------------------
# the invariant itself
# --------------------------------------------------------------------


def test_documented_forbidden_prose_readings_have_no_field_to_live_in(profile):
    v = view(rec(EV="0", STATUS="U1"), profile)
    names = set(vars(v))
    for forbidden_concept in ("weak", "strength", "quality", "likelihood",
                              "probability", "score", "trust", "novelty"):
        assert not any(forbidden_concept in name for name in names), (
            f"the ABI exposes a field that invites the reading {forbidden_concept!r}"
        )
    assert ABI_EVIDENCE["expected"]
    assert ABI_EVIDENCE["forbidden_prose"]
