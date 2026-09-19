"""Tests for explicit ABI version bump (V3 -> V4), historical compatibility, and canonical evidence API."""

from __future__ import annotations

import pytest

from sailang import Record, SailangError
from sailang.frame import (
    FRAME_VERSION,
    BATCH_MARKER,
    PROFILE_MARKER,
    Profile,
    project,
    project_batch,
    Batch,
    decode,
)
from sailang.record import (
    EVIDENCE_ATTACHED,
    EVIDENCE_EXPLICITLY_ABSENT,
    EVIDENCE_NOT_APPLICABLE,
)
from saimail.acceptance import ProfileRegistry, receive, declared_profile_id

T = "2026-09-17T08:41:00Z"
REF_A = "sha256:" + "a" * 64


def fact(**over):
    fields = dict(KIND="F", SRC="AGENT:a17", SUBJ="queue", CLAIM="QUEUE_OWNERSHIP_STALE>RETRY",
                  TYPE="INT", EV=REF_A, STATUS="U2", CREATED=T)
    fields.update(over)
    for key in [k for k, v in fields.items() if v is None]:
        del fields[key]
    return Record.create(**fields)


def goal():
    return Record.create(KIND="G", SRC="HUMAN:vacterro", SUBJ="queue",
                         CLAIM="no duplicates", CREATED=T)


def value():
    return Record.create(KIND="V", SRC="HUMAN:vacterro", SUBJ="latency",
                         CLAIM="low latency preferred", CREATED=T)


def accepted(profile):
    """The receiver's acceptance capability, minted as a receiver would."""
    return ProfileRegistry.with_profiles(profile).resolve(profile.id)


def test_frame_version_is_v4():
    assert FRAME_VERSION == "4"
    assert BATCH_MARKER == "SAIB4"
    assert PROFILE_MARKER == "SAIP4"


def test_profile_identity_changes_between_v3_and_v4():
    p3 = Profile.load("1", frame_version="3")
    p4 = Profile.load("1", frame_version="4")
    assert p3.frame_version == "3"
    assert p4.frame_version == "4"
    assert p3.batch_marker == "SAIB3"
    assert p4.batch_marker == "SAIB4"
    assert p3.profile_marker == "SAIP3"
    assert p4.profile_marker == "SAIP4"
    assert p3.id != p4.id
    assert p3.descriptor().startswith(b"SAIP3\nFRAME:3\n")
    assert p4.descriptor().startswith(b"SAIP4\nFRAME:4\n")


def test_v4_projects_three_evidence_states():
    p4 = Profile.load("1", frame_version="4")
    # Attached
    f_att = fact(EV=REF_A, STATUS="U2")
    assert f_att.evidence_state == EVIDENCE_ATTACHED
    assert f_att.has_evidence is True
    assert project(f_att, p4).wire.split("|")[3] == "EV+"

    # Explicitly absent
    f_abs = fact(EV="0", STATUS="U1")
    assert f_abs.evidence_state == EVIDENCE_EXPLICITLY_ABSENT
    assert f_abs.has_evidence is False
    assert project(f_abs, p4).wire.split("|")[3] == "EV0"

    # Not applicable (G, V)
    g = goal()
    assert g.evidence_state == EVIDENCE_NOT_APPLICABLE
    assert g.has_evidence is None
    assert project(g, p4).wire.split("|")[3] == "EV-"

    v = value()
    assert v.evidence_state == EVIDENCE_NOT_APPLICABLE
    assert v.has_evidence is None
    assert project(v, p4).wire.split("|")[3] == "EV-"


def test_v3_projects_historical_ev0_for_goal():
    p3 = Profile.load("1", frame_version="3")
    g = goal()
    # In V3, G projected as EV0
    assert project(g, p3).wire.split("|")[3] == "EV0"
    f_att = fact(EV=REF_A, STATUS="U2")
    assert project(f_att, p3).wire.split("|")[3] == "EV+"


def test_v3_refuses_ev_minus_wire():
    p3 = Profile.load("1", frame_version="3")
    container = f"SAIB3|P:{p3.id}|N:1|D:0\nG|queue|-|EV-|no duplicates|-\n"
    batch = Batch.parse(container, accepted(p3))
    with pytest.raises(SailangError) as exc:
        decode(batch.frames[0])
    assert exc.value.code == "BAD_FRAME"
    assert "evidence slot on V3 must be EV0 or EV+" in str(exc.value)


def test_v4_decodes_typed_evidence_view():
    p4 = Profile.load("1", frame_version="4")
    records = [fact(EV=REF_A, STATUS="U2"), fact(EV="0", STATUS="U1"), goal()]
    batch = project_batch(records, p4)
    views = [decode(f) for f in batch.frames]

    # View 0: Attached
    assert views[0].evidence_state == EVIDENCE_ATTACHED
    assert views[0].has_evidence is True
    assert views[0].is_evidence_attached is True
    assert views[0].is_evidence_absent is False
    assert views[0].is_evidence_applicable is True

    # View 1: Explicitly absent
    assert views[1].evidence_state == EVIDENCE_EXPLICITLY_ABSENT
    assert views[1].has_evidence is False
    assert views[1].is_evidence_attached is False
    assert views[1].is_evidence_absent is True
    assert views[1].is_evidence_applicable is True

    # View 2: Not applicable
    assert views[2].evidence_state == EVIDENCE_NOT_APPLICABLE
    assert views[2].has_evidence is None
    assert views[2].is_evidence_attached is False
    assert views[2].is_evidence_absent is False
    assert views[2].is_evidence_applicable is False


def test_batch_cross_version_refusal():
    p3 = Profile.load("1", frame_version="3")
    p4 = Profile.load("1", frame_version="4")

    batch4_text = project_batch([fact()], p4).render()
    assert batch4_text.startswith(f"SAIB4|P:{p4.id}|")

    batch3_text = project_batch([fact()], p3).render()
    assert batch3_text.startswith(f"SAIB3|P:{p3.id}|")

    # V3 profile parsing V4 container fails on header
    with pytest.raises(SailangError) as exc:
        Batch.parse(batch4_text, accepted(p3))
    assert exc.value.code == "BAD_BATCH"
    assert "line 1 must be SAIB3" in str(exc.value)

    # V4 profile parsing V3 container fails on header
    with pytest.raises(SailangError) as exc:
        Batch.parse(batch3_text, accepted(p4))
    assert exc.value.code == "BAD_BATCH"
    assert "line 1 must be SAIB4" in str(exc.value)


def test_acceptance_registry_supports_both_v3_and_v4():
    p3 = Profile.load("1", frame_version="3")
    p4 = Profile.load("1", frame_version="4")
    registry = ProfileRegistry.with_profiles(p3, p4)

    batch3 = project_batch([fact(STATUS="U2")], p3).render()
    batch4 = project_batch([fact(STATUS="U2"), goal()], p4).render()

    assert declared_profile_id(batch3) == p3.id
    assert declared_profile_id(batch4) == p4.id

    views3 = receive(batch3, registry)
    assert len(views3) == 1
    assert views3[0].profile_id == p3.id
    assert views3[0].has_evidence is True

    views4 = receive(batch4, registry)
    assert len(views4) == 2
    assert views4[0].profile_id == p4.id
    assert views4[1].evidence_state == EVIDENCE_NOT_APPLICABLE
    assert views4[1].has_evidence is None
