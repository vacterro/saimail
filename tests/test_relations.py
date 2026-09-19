"""T-18 acceptance: a relation to a watched record is not missed, and the alias stays local.

The first two tests prove the failure BEFORE the fix is exercised: without
relation targets on the wire, a message whose vocabulary looks unrelated is
dropped even though it refutes something the reader watches.
"""

import pathlib

import pytest

from bench.selector_corpus import CASES, INTEREST, WATCHED
from saimail.acceptance import ProfileRegistry
from saimail.selector import DEFER, IGNORE, OPEN_R2, OPEN_R3, Interest, select
from sailang import Record, SailangError
from sailang.frame import Batch, Profile, decode, project, project_batch

T = "2026-09-17T08:41:00Z"
REF = "sha256:" + "a" * 64
OTHER = "sha256:" + "c" * 64


@pytest.fixture(scope="module")
def profile():
    return Profile.load("1")


def accepted(profile):
    """The receiver's acceptance capability, minted as a receiver would."""
    return ProfileRegistry.with_profiles(profile).resolve(profile.id)


def unrelated_looking_refutation():
    """Another team's vocabulary entirely, refuting the watched record."""
    return Record.create(KIND="F", SRC="AGENT:z", SUBJ="envelope",
                         CLAIM="SIGNATURE>ENVELOPE", TYPE="INT", EV=REF, STATUS="U2",
                         REFUTES=WATCHED, CREATED=T)


def views_of(records, profile, with_aliases=True):
    container = project_batch(records, profile, with_aliases=with_aliases).render()
    return [decode(f) for f in Batch.parse(container, accepted(profile)).frames]


# --------------------------------------------------------------------
# first, prove the failure
# --------------------------------------------------------------------


def test_without_relation_targets_a_watched_refutation_is_dropped(profile):
    # This is the pre-fix behaviour, reproduced on purpose: the relation is
    # present but nameless, so the reader sees "someone refuted something".
    view = views_of([unrelated_looking_refutation()], profile, with_aliases=False)[0]
    assert view.refutes is True
    assert view.relation_targets == ()
    verdict = select(view, INTEREST).verdict
    assert verdict != OPEN_R3, "the pre-fix selector cannot know this matters"
    assert verdict in (DEFER, IGNORE)


def test_with_relation_targets_the_same_message_reaches_the_record(profile):
    view = views_of([unrelated_looking_refutation()], profile)[0]
    assert view.relation_targets == (("R", WATCHED),)
    decision = select(view, INTEREST)
    assert decision.verdict == OPEN_R3
    assert decision.rule == "R0-WATCHED"


# --------------------------------------------------------------------
# the hostile cases
# --------------------------------------------------------------------


@pytest.mark.parametrize("field,mark", [("REFUTES", "R"), ("CON", "C"), ("SUPPORTS", "S")])
def test_every_relation_kind_to_a_watched_record_opens(profile, field, mark):
    record = Record.create(KIND="F", SRC="AGENT:z", SUBJ="db", CLAIM="DATABASE>METADATA",
                           TYPE="INT", EV=REF, STATUS="U2", CREATED=T, **{field: WATCHED})
    view = views_of([record], profile)[0]
    assert (mark, WATCHED) in view.relation_targets
    assert select(view, INTEREST).verdict == OPEN_R3


def test_a_relevant_looking_message_relating_only_elsewhere_does_not_escalate(profile):
    record = Record.create(KIND="F", SRC="AGENT:z", SUBJ="envelope",
                           CLAIM="SIGNATURE>VALIDATION", TYPE="INT", EV=REF, STATUS="U2",
                           REFUTES=OTHER, CREATED=T)
    view = views_of([record], profile)[0]
    assert view.relation_targets == (("R", OTHER),)
    assert select(view, INTEREST).verdict != OPEN_R3


def test_multiple_relations_to_different_targets_are_all_carried(profile):
    record = Record.create(KIND="F", SRC="AGENT:z", SUBJ="db", CLAIM="DATABASE>METADATA",
                           TYPE="INT", EV=REF, STATUS="U2", CREATED=T,
                           REFUTES=OTHER, SUPPORTS=WATCHED, CON=REF)
    view = views_of([record], profile)[0]
    assert dict(view.relation_targets) == {"R": OTHER, "S": WATCHED, "C": REF}
    assert select(view, INTEREST).verdict == OPEN_R3


def test_an_undeclared_alias_is_unresolved_and_never_ignored(profile):
    from sailang.frame import _bind_verified

    frame = _bind_verified("F|envelope|U2|EV+|SIG|R@9", profile, aliases=(("@1", WATCHED),))
    view = decode(frame)
    assert view.refutes is True
    assert view.relation_targets == ()
    assert view.unresolved_aliases == ("@9",)
    decision = select(view, INTEREST)
    assert decision.verdict == OPEN_R2
    assert decision.rule == "R1-UNRESOLVED-RELATION"


def test_a_duplicate_alias_definition_is_refused(profile):
    header = f"{profile.batch_marker}|P:{profile.id}|N:1|D:2"
    body = f"DEF @1={WATCHED}\nDEF @1={OTHER}\nF|queue|U2|EV+|RETRY|R@1"
    with pytest.raises(SailangError) as exc:
        Batch.parse(header + "\n" + body + "\n", accepted(profile))
    assert exc.value.code == "DUPLICATE_ALIAS"


def test_a_malformed_alias_definition_is_refused(profile):
    header = f"{profile.batch_marker}|P:{profile.id}|N:1|D:1"
    body = "DEF @1=not-a-hash\nF|queue|U2|EV+|RETRY|R@1"
    with pytest.raises(SailangError) as exc:
        Batch.parse(header + "\n" + body + "\n", accepted(profile))
    assert exc.value.code == "BAD_ALIAS_DEF"


# --------------------------------------------------------------------
# the alias is transport, never identity
# --------------------------------------------------------------------


def test_the_view_exposes_canonical_identities_not_aliases(profile):
    view = views_of([unrelated_looking_refutation()], profile)[0]
    for _, target in view.relation_targets:
        assert target.startswith("sha256:") and len(target) == 71
        assert not target.startswith("@")


def test_the_same_record_gets_the_same_alias_within_a_batch_and_owns_none_outside(profile):
    records = [unrelated_looking_refutation(),
               Record.create(KIND="F", SRC="AGENT:y", SUBJ="db", CLAIM="DATABASE",
                             TYPE="INT", EV=REF, STATUS="U2", SUPPORTS=WATCHED, CREATED=T)]
    container = project_batch(records, profile).render()
    assert container.count(f"DEF @1={WATCHED}") == 1
    assert container.count("R@1") == 1 and container.count("S@1") == 1
    # standalone projection has no batch, therefore no alias and no target
    lone = project(records[0], profile)
    assert "@" not in lone.wire


def test_relation_targets_cost_only_what_they_declare(profile):
    records = [Record.create(**case.fields) for case in CASES]
    without = project_batch(records, profile, with_aliases=False).render()
    with_targets = project_batch(records, profile).render()
    added = len(with_targets.encode()) - len(without.encode())
    per_message = added / len(records)
    assert added > 0
    # a DEF line is 76 bytes and is paid once per distinct target; the in-frame
    # reference is 2-3 bytes. This is a measurement, not a threshold.
    assert per_message < 60, f"{per_message:.1f} bytes per message is not a local alias"


def test_relation_awareness_does_not_break_the_declared_ground_truth(profile):
    views = views_of([Record.create(**case.fields) for case in CASES], profile)
    missed = [case.name for case, view in zip(CASES, views)
              if select(view, INTEREST).verdict == IGNORE and case.truth != IGNORE]
    assert not missed, f"false ignores after adding relations: {missed}"


def test_watched_is_receiver_owned(profile):
    view = views_of([unrelated_looking_refutation()], profile)[0]
    # another reader, watching nothing, is not forced to care
    indifferent = Interest.of(atoms=INTEREST.atoms, subjects=INTEREST.subjects)
    assert select(view, indifferent).verdict != OPEN_R3
    assert select(view, INTEREST).verdict == OPEN_R3


def test_the_selector_still_reads_nothing_but_the_view():
    source = pathlib.Path("saimail/selector.py").read_text(encoding="utf-8")
    assert "Batch" not in source and "Profile" not in source
