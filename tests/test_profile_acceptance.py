"""T-19 acceptance: identity is not acceptance, and the receiver owns the answer."""

import ast
import dataclasses
import pathlib

import pytest

from saimail.acceptance import (
    ACCEPTED,
    UNKNOWN,
    ProfileRegistry,
    declared_profile_id,
    receive,
)
from sailang import Batch, Record, SailangError
from sailang.frame import AcceptedProfile, Profile, decode, project_batch

T = "2026-09-17T08:41:00Z"
REF = "sha256:" + "a" * 64


@pytest.fixture(scope="module")
def profile():
    return Profile.load("1")


@pytest.fixture(scope="module")
def container(profile):
    records = [
        Record.create(KIND="F", SRC="AGENT:a", SUBJ="queue",
                      CLAIM="QUEUE_OWNERSHIP_STALE>RETRY", TYPE="INT", EV=REF,
                      STATUS="U2", CREATED=T),
        Record.create(KIND="G", SRC="HUMAN:v", SUBJ="queue", CLAIM="be faster", CREATED=T),
    ]
    return project_batch(records, profile).render()


def err(fn, *a, **k):
    with pytest.raises(SailangError) as e:
        fn(*a, **k)
    return e.value.code


# ------------------------------------------------ identity != acceptance


def test_a_known_identity_is_not_an_accepted_one(profile, container):
    empty = ProfileRegistry()
    assert empty.status(profile.id) == UNKNOWN
    # the identity is perfectly verifiable and still refused
    assert declared_profile_id(container) == profile.id
    assert err(receive, container, empty) == "PROFILE_NOT_ACCEPTED"


def test_the_receiver_decides_and_then_it_works(profile, container):
    registry = ProfileRegistry.with_profiles(profile)
    assert registry.status(profile.id) == ACCEPTED
    views = receive(container, registry)
    assert [v.kind for v in views] == ["F", "G"]
    assert views[0].claim_atoms == ("QUEUE_OWNERSHIP_STALE", "RETRY")


def test_two_states_only():
    registry = ProfileRegistry()
    assert {registry.status("sha256:" + "0" * 64)} == {UNKNOWN}
    source = pathlib.Path("saimail/acceptance.py").read_text(encoding="utf-8")
    assert 'REJECTED = ' not in source and 'REVOKED = ' not in source


def test_a_registry_accepts_profiles_not_descriptions_of_them():
    registry = ProfileRegistry()
    assert err(registry.accept, {"id": "sha256:" + "0" * 64}) == "NOT_A_PROFILE"
    assert err(registry.accept, "sha256:" + "0" * 64) == "NOT_A_PROFILE"


# ------------------------------------------------ external wire cannot define itself


def test_arriving_content_cannot_supply_its_own_dictionary(container):
    # A sender mints a profile, renders a container under it, and ships both.
    hostile = Profile.inline("hostile", {"QUEUE_OWNERSHIP_STALE":
                                         {"wire": "QSTALE", "render": "nothing to see here"}})
    records = [Record.create(KIND="F", SRC="AGENT:evil", SUBJ="queue",
                             CLAIM="QUEUE_OWNERSHIP_STALE", TYPE="INT", EV="0",
                             STATUS="U1", CREATED=T)]
    payload = project_batch(records, hostile).render()
    registry = ProfileRegistry.with_profiles(Profile.load("1"))
    assert err(receive, payload, registry) == "PROFILE_NOT_ACCEPTED"
    # and accepting it must be an act of the receiver, never of the message
    registry.accept(hostile)
    assert receive(payload, registry)[0].claim_atoms == ("QUEUE_OWNERSHIP_STALE",)


def test_receive_needs_the_receivers_own_registry(container):
    assert err(receive, container, None) == "REGISTRY_REQUIRED"
    assert err(receive, container, {"anything": "goes"}) == "REGISTRY_REQUIRED"


# ------------------------------------------------ raw wire needs acceptance (T-39, CORE-001)


def hostile_payload():
    hostile = Profile.inline("hostile", {"QUEUE_OWNERSHIP_STALE":
                                         {"wire": "QSTALE", "render": "nothing to see here"}})
    records = [Record.create(KIND="F", SRC="AGENT:evil", SUBJ="queue",
                             CLAIM="QUEUE_OWNERSHIP_STALE", TYPE="INT", EV="0",
                             STATUS="U1", CREATED=T)]
    return hostile, project_batch(records, hostile).render()


def test_possession_of_a_profile_does_not_authorize_raw_wire(profile, container):
    # identity is provable and is still not permission: binding raw wire needs
    # the receiver's acceptance capability, never a bare Profile object
    assert err(Batch.parse, container, profile) == "ACCEPTED_PROFILE_REQUIRED"


def test_an_unaccepted_hostile_profile_has_no_public_route_to_a_view(profile, container):
    hostile, payload = hostile_payload()
    # the registry refuses it, and the raw parser refuses the Profile itself
    assert err(receive, payload, ProfileRegistry()) == "PROFILE_NOT_ACCEPTED"
    assert err(Batch.parse, payload, hostile) == "ACCEPTED_PROFILE_REQUIRED"
    # a capability minted for a DIFFERENT accepted profile cannot read it either
    accepted = ProfileRegistry.with_profiles(profile).resolve(profile.id)
    assert err(Batch.parse, payload, accepted) == "PROFILE_MISMATCH"
    # and the hostile semantics never reach a view through any of those routes
    assert err(decode, payload.splitlines()[1]) == "UNBOUND_WIRE"


def test_the_capability_is_minted_only_by_the_registry(profile, container):
    assert err(AcceptedProfile, profile) == "UNVERIFIED_ACCEPTANCE"
    accepted = ProfileRegistry.with_profiles(profile).resolve(profile.id)
    assert isinstance(accepted, AcceptedProfile)
    assert Batch.parse(container, accepted).frames[0].profile.id == profile.id


# ------------------------------------------------ the capability is not transferable (T-40)


def test_an_accepted_capability_cannot_be_replaced_into_another_profile(profile):
    accepted = ProfileRegistry.with_profiles(profile).resolve(profile.id)
    hostile, payload = hostile_payload()
    assert err(dataclasses.replace, accepted, profile=hostile) == "UNVERIFIED_ACCEPTANCE"
    # and nothing that passed through replacement can bind the hostile wire
    assert err(Batch.parse, payload, hostile) == "ACCEPTED_PROFILE_REQUIRED"


def test_an_accepted_profile_retains_no_reusable_token(profile):
    accepted = ProfileRegistry.with_profiles(profile).resolve(profile.id)
    token = getattr(accepted, "binding", None)
    assert token is None, "a minted instance must not store its mint token"
    hostile, _ = hostile_payload()
    assert err(AcceptedProfile, hostile, token) == "UNVERIFIED_ACCEPTANCE"


def test_a_malformed_container_is_refused_before_any_profile_lookup():
    registry = ProfileRegistry()
    for bad in ("", "   ", "not a header\n", "SAIB2|P:nope|N:1\n"):
        assert err(declared_profile_id, bad) in {"BAD_BATCH"}
        assert err(receive, bad, registry) in {"BAD_BATCH"}


# ------------------------------------------------ no assertion-style public API


def test_assertion_style_binding_is_not_public():
    import sailang
    import sailang.frame as frame

    assert "bind_verified" not in sailang.__all__
    assert not hasattr(sailang, "bind_verified")
    assert not hasattr(frame, "bind_verified")
    assert hasattr(frame, "_bind_verified")


def test_the_only_public_raw_wire_route_is_receive():
    tree = ast.parse(pathlib.Path("saimail/acceptance.py").read_text(encoding="utf-8"))
    public = {n.name for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")}
    assert public <= {"receive", "declared_profile_id", "accept", "status", "resolve",
                      "with_profiles", "accepted_ids"}
    # exactly one of them takes raw wire
    module = pathlib.Path("saimail/acceptance.py").read_text(encoding="utf-8")
    assert module.count("def receive(") == 1


def test_the_boundary_is_described_as_type_state_not_security():
    source = pathlib.Path("sailang/frame.py").read_text(encoding="utf-8")
    assert "not a security boundary" in source


# ------------------------------------------------ canonical encoding (D-016)


def test_one_atom_has_one_wire_encoding(profile):
    assert profile.to_wire("RETRY") == "RETRY"          # no abbreviation: itself
    assert profile.to_wire("QUEUE_OWNERSHIP_STALE") == "QSTALE"
    assert profile.is_non_canonical("QUEUE_OWNERSHIP_STALE") is True
    assert profile.is_non_canonical("QSTALE") is False
    assert profile.is_non_canonical("RETRY") is False


def test_a_non_canonical_spelling_is_refused_not_quietly_accepted(profile):
    from sailang.frame import _bind_verified, decode

    assert err(decode, _bind_verified("F|queue|U2|EV+|QUEUE_OWNERSHIP_STALE|-", profile)) == \
        "NON_CANONICAL_ENCODING"
    assert err(decode, _bind_verified("F|queue|U2|EV+|QUEUE_OWNERSHIP_STALE=1|-", profile)) == \
        "NON_CANONICAL_ENCODING"
    # the canonical spelling decodes to the same atom the long form named
    assert decode(_bind_verified("F|queue|U2|EV+|QSTALE|-", profile)).claim_atoms == \
        ("QUEUE_OWNERSHIP_STALE",)


def test_a_non_canonical_spelling_is_not_merely_unknown(profile):
    from sailang.frame import _bind_verified, decode

    unknown = decode(_bind_verified("F|queue|U2|EV+|WOMBAT_THING|-", profile))
    assert unknown.claim_unknown_wires == ("WOMBAT_THING",)
    # an atom spelled the wrong way is a different failure from a token nobody knows
    assert err(decode, _bind_verified("F|queue|U2|EV+|WOMBAT_THING>QUEUE_OWNERSHIP_STALE|-",
                                      profile)) == "NON_CANONICAL_ENCODING"


def test_every_shipped_atom_round_trips_through_its_canonical_wire_only(profile):
    for atom, wire in profile.atom_to_wire.items():
        assert profile.to_atom(wire) == atom
        if wire != atom:
            assert profile.to_atom(atom) is None
            assert profile.is_non_canonical(atom)
