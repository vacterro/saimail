"""T-12/T-16 acceptance: Record / TriageFrame / TriageView, bound profiles, atoms.

Rules under test: spec/DECISIONS.md D-010 (decodable, never reconstructable),
D-011 (profile paid once), D-012 (atom / wire / render), D-013 (raw wire is not
decodable; the container establishes the binding).
"""

import ast
import dataclasses
import json
import pathlib

import pytest

from saimail.acceptance import ProfileRegistry
from sailang import Record, SailangError
from sailang.frame import (
    ABSENT,
    OPEN_RECORD,
    Batch,
    Profile,
    TriageFrame,
    _bind_verified as bind_verified,
    TriageView,
    decode,
    project,
    project_batch,
)

REF_A = "sha256:" + "a" * 64
REF_B = "sha256:" + "b" * 64


@pytest.fixture(scope="module")
def profile():
    return Profile.load("1")


def accepted(profile):
    """The receiver's acceptance capability, minted as a receiver would."""
    return ProfileRegistry.with_profiles(profile).resolve(profile.id)


def fact(**over):
    fields = dict(KIND="F", SRC="AGENT:a17", SUBJ="queue",
                  CLAIM="QUEUE_OWNERSHIP_STALE>RETRY>DUPLICATE_EXECUTION",
                  TYPE="INT", EV=REF_A, STATUS="U2", CREATED="2026-09-17T08:41:00Z")
    fields.update(over)
    for key in [k for k, v in fields.items() if v is None]:
        del fields[key]
    return Record.create(**fields)


def err(fn, *args, **kwargs):
    with pytest.raises(SailangError) as excinfo:
        fn(*args, **kwargs)
    return excinfo.value.code


def view_of(record, profile):
    return decode(project(record, profile))


# --------------------------------------------------------------------
# D-013 — raw wire has no provenance and is not decodable
# --------------------------------------------------------------------


def test_a_raw_wire_string_cannot_be_decoded_at_all(profile):
    frame = project(fact(), profile)
    assert err(decode, frame.wire) == "UNBOUND_WIRE"
    assert decode(frame).kind == "F"


def test_decode_takes_no_profile_argument(profile):
    frame = project(fact(), profile)
    with pytest.raises(TypeError):
        decode(frame, profile)


def test_a_frame_from_profile_a_cannot_be_read_under_profile_b(profile):
    other = Profile.inline("9", {"QUEUE_OWNERSHIP_STALE": {"wire": "QSTALE",
                                                           "render": "something else entirely"}})
    assert other.id != profile.id
    container = project_batch([fact()], profile).render()
    # the only public route from raw wire to a frame checks the container header
    assert err(Batch.parse, container, accepted(other)) == "PROFILE_MISMATCH"
    # and there is no second route
    assert err(decode, container.splitlines()[1]) == "UNBOUND_WIRE"


def test_a_frame_carries_the_profile_object_not_merely_its_id(profile):
    frame = project(fact(), profile)
    assert isinstance(frame.profile, Profile)
    assert frame.profile_id == profile.id
    assert decode(frame).profile_id == profile.id


def test_container_round_trip_binds_every_frame(profile):
    records = [fact(), fact(SUBJ="recovery"), fact(SUBJ="loader")]
    text = project_batch(records, profile).render()
    parsed = Batch.parse(text, accepted(profile))
    assert len(parsed.frames) == 3
    assert all(f.profile.id == profile.id for f in parsed.frames)
    assert [decode(f).subject for f in parsed.frames] == ["queue", "recovery", "loader"]


def test_container_header_declares_the_profile_once(profile):
    text = project_batch([fact(), fact(SUBJ="other")], profile).render()
    header, *body = text.splitlines()
    assert header == f"{profile.batch_marker}|P:{profile.id}|N:2|D:0"
    assert all("sha256:" not in line for line in body)


def test_container_count_and_shape_are_checked(profile):
    text = project_batch([fact(), fact(SUBJ="other")], profile).render()
    assert err(Batch.parse, text.replace("N:2", "N:5"), accepted(profile)) == "BAD_BATCH"
    assert err(Batch.parse, "nonsense\n", accepted(profile)) == "BAD_BATCH"
    assert err(Batch.parse, text, None) == "ACCEPTED_PROFILE_REQUIRED"


def test_projection_also_requires_an_explicit_profile():
    assert err(project, fact(), None) == "PROFILE_REQUIRED"


# --------------------------------------------------------------------
# T-40 — the binding is not transferable
# --------------------------------------------------------------------


def test_a_frame_cannot_be_replaced_into_another_wire_and_profile(profile):
    frame = project(fact(), profile)
    hostile = Profile.inline("hostile", {"QUEUE_OWNERSHIP_STALE":
                                         {"wire": "QSTALE", "render": "nothing to see here"}})
    wire = "F|queue|U1|EV0|QSTALE|-"
    assert err(dataclasses.replace, frame, wire=wire, profile=hostile) == "UNVERIFIED_BINDING"


def test_a_frame_retains_no_reusable_binding_token(profile):
    frame = project(fact(), profile)
    token = getattr(frame, "binding", None)
    assert token is None, "a minted instance must not store its mint token"
    hostile = Profile.inline("hostile", {"QUEUE_OWNERSHIP_STALE":
                                         {"wire": "QSTALE", "render": "nothing to see here"}})
    assert err(TriageFrame, "F|queue|U1|EV0|QSTALE|-", hostile, token) == "UNVERIFIED_BINDING"


# --------------------------------------------------------------------
# D-012 — atom, wire, render
# --------------------------------------------------------------------


def test_shipped_dictionary_is_injective(profile):
    assert len(profile.atom_to_wire) == len(profile.wire_to_atom)
    for atom, wire in profile.atom_to_wire.items():
        assert profile.wire_to_atom[wire] == atom


def test_a_dictionary_with_two_atoms_on_one_wire_is_refused():
    with pytest.raises(SailangError) as excinfo:
        Profile.inline("x", {
            "BLOCKED": {"wire": "BLK", "render": "work is blocked"},
            "BLOCKER": {"wire": "BLK", "render": "the thing doing the blocking"},
        })
    assert excinfo.value.code == "DICTIONARY_AMBIGUOUS"


def test_blocked_and_blocker_are_distinguishable_on_the_wire(profile):
    blocked = view_of(fact(CLAIM="BLOCKED>DEPENDENCY"), profile)
    blocker = view_of(fact(CLAIM="BLOCKER>VALIDATION"), profile)
    assert blocked.claim_atoms == ("BLOCKED", "DEPENDENCY")
    assert blocker.claim_atoms == ("BLOCKER", "VALIDATION")
    assert blocked.claim_token != blocker.claim_token


def test_view_exposes_canonical_atoms_not_abbreviations(profile):
    view = view_of(fact(), profile)
    assert view.claim_atoms == ("QUEUE_OWNERSHIP_STALE", "RETRY", "DUPLICATE_EXECUTION")
    assert view.claim_shape == "chain"
    assert view.claim_unknown_wires == ()
    # the abbreviation is available for diagnostics, and only for that
    assert view.claim_token == "QSTALE>RETRY>DUPEX"


def test_unknown_wire_tokens_stay_unknown_and_are_never_guessed(profile):
    view = view_of(fact(CLAIM="WOMBAT_SUBSYSTEM>RETRY"), profile)
    assert view.claim_atoms == ("RETRY",)
    assert view.claim_unknown_wires == ("WOMBAT_SUBSYSTEM",)
    assert view.has_unknown_atoms is True
    known = view_of(fact(), profile)
    assert known.has_unknown_atoms is False


def test_comparison_claims_expose_atom_operator_and_value(profile):
    view = view_of(fact(CLAIM="TIMESTAMP>=2025"), profile)
    assert view.claim_shape == "comparison"
    assert view.claim_atoms == ("TIMESTAMP",)
    assert view.claim_operator == ">="
    assert view.claim_value == "2025"
    unknown = view_of(fact(CLAIM="DB_HISTORY>=2025"), profile)
    assert unknown.claim_atoms == ()
    assert unknown.claim_unknown_wires == ("DB_HISTORY",)


def test_render_carries_no_authority_and_is_not_in_the_view(profile):
    view = view_of(fact(), profile)
    assert not hasattr(view, "render")
    assert profile.render["QUEUE_OWNERSHIP_STALE"]


def test_profile_identity_binds_the_dictionary_content(profile):
    assert Profile.load("1").id == profile.id
    revised = Profile.inline("1", dict(
        (atom, {"wire": wire, "render": profile.render[atom]})
        for atom, wire in list(profile.atom_to_wire.items())[:5]))
    assert revised.id != profile.id


def test_malformed_dictionaries_are_refused(tmp_path, monkeypatch):
    import sailang.frame as module

    monkeypatch.setattr(module, "_DICTIONARY_DIR", tmp_path)
    (tmp_path / "v5.json").write_text("{not json", encoding="utf-8")
    assert err(Profile.load, "5") == "DICTIONARY_MALFORMED"
    (tmp_path / "v5.json").write_text('{"version":"5","atoms":{"A":{"wire":"a b","render":"x"}}}',
                                      encoding="utf-8")
    assert err(Profile.load, "5") == "DICTIONARY_MALFORMED"
    (tmp_path / "v5.json").write_text('{"version":"4","atoms":{}}', encoding="utf-8")
    assert err(Profile.load, "5") == "DICTIONARY_VERSION_MISMATCH"
    assert err(Profile.load, "404") == "DICTIONARY_MISSING"


def test_shipped_dictionary_file_declares_the_three_layers():
    data = json.loads(pathlib.Path("sailang/dictionary/v1.json").read_text(encoding="utf-8"))
    for atom, entry in data["atoms"].items():
        assert set(entry) == {"wire", "render"}, f"{atom} must declare wire and render"
    assert "BLOCKED" in data["atoms"] and "BLOCKER" in data["atoms"]
    assert data["atoms"]["BLOCKED"]["wire"] != data["atoms"]["BLOCKER"]["wire"]


# --------------------------------------------------------------------
# D-010 — decode produces a view, and only a view
# --------------------------------------------------------------------


def test_decode_returns_a_typed_non_authoritative_view(profile):
    view = view_of(fact(), profile)
    assert isinstance(view, TriageView)
    assert view.authoritative is False
    assert TriageFrame.authoritative is False


def test_no_api_accepts_a_view_where_a_record_is_required(profile):
    view = view_of(fact(), profile)
    frame = project(fact(), profile)
    assert err(project, view, profile) == "NOT_A_RECORD"
    assert err(project, frame, profile) == "NOT_A_RECORD"
    for candidate in (view, frame):
        assert not isinstance(candidate, Record)
        assert not hasattr(candidate, "canonical_bytes")
        assert not hasattr(candidate, "content_id")


def test_no_function_reconstructs_a_record_from_a_frame_or_view():
    import sailang.frame as module

    tree = ast.parse(pathlib.Path(module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            returns = getattr(node.returns, "id", None)
            args = [a.arg for a in node.args.args]
            assert not (returns == "Record" and {"frame", "view", "wire"} & set(args))
    public = {name for name in dir(module) if not name.startswith("_")}
    for forbidden in ("to_record", "as_record", "promote", "unproject", "rehydrate"):
        assert forbidden not in public


def test_view_carries_only_what_the_frame_carried(profile):
    view = view_of(fact(), profile)
    assert (view.kind, view.subject, view.status, view.has_evidence) == ("F", "queue", "U2", True)
    assert REF_A not in str(view)


def test_unrepresentable_claim_decodes_to_open_record_not_a_guess(profile):
    view = view_of(fact(CLAIM="stale queue ownership survives a retry"), profile)
    assert view.claim_open_record is True
    assert view.claim_atoms == () and view.claim_token is None


def test_goal_decodes_with_no_status_and_no_invented_evidence(profile):
    goal = Record.create(KIND="G", SRC="HUMAN:vacterro", SUBJ="maintenance",
                         CLAIM="reduce maintenance burden", CREATED="2026-09-17T08:41:00Z")
    view = view_of(goal, profile)
    assert (view.kind, view.status, view.evidence_state, view.has_evidence) == ("G", None, "EVIDENCE_NOT_APPLICABLE", None)
    assert project(goal, profile).wire.split("|")[2] == ABSENT
    assert project(goal, profile).wire.split("|")[3] == "EV-"


def test_flags_survive_the_round_trip(profile):
    view = view_of(fact(REFUTES=REF_B, SUPPORTS=REF_A), profile)
    assert view.refutes and view.supports and not view.conflict
    hypothesis = Record.create(KIND="H", SRC="AGENT:a", SUBJ="queue", CLAIM="RETRY>DUPLICATE_EXECUTION",
                               TYPE="INT", FALSIFY="a fresh owner still duplicates",
                               EV="0", STATUS="U1", CREATED="2026-09-17T08:41:00Z")
    assert view_of(hypothesis, profile).falsifiable is True


# --------------------------------------------------------------------
# determinism and malformed input
# --------------------------------------------------------------------


def test_projection_is_deterministic_and_leaves_the_record_untouched(profile):
    record = fact()
    before = record.canonical_bytes()
    assert len({project(record, profile).wire for _ in range(5)}) == 1
    assert record.canonical_bytes() == before


@pytest.mark.parametrize("bad", [
    "F|queue|U2|EV+|X", "F|queue|U2|EV+|X|-|extra", "Z|queue|U2|EV+|X|-",
    "F|queue|U9|EV+|X|-", "F|queue|U2|EVX|X|-", "F|queue|U2|EV+|X|Q",
    "F||U2|EV+|X|-", "F|queue|U2|EV+|not a token|-",
])
def test_malformed_frames_are_refused(profile, bad):
    assert err(decode, bind_verified(bad, profile)) == "BAD_FRAME"


def test_ledger_verdicts_never_appear_in_a_frame(profile):
    for verdict in ("C", "D"):
        assert err(decode, bind_verified(f"F|queue|{verdict}|EV+|RETRY|-", profile)) == "BAD_FRAME"


def test_separator_bearing_slot_opens_the_record_instead_of_escaping(profile):
    frame = project(fact(SUBJ="queue|shard", CLAIM="TIMESTAMP=b|c"), profile)
    slots = frame.wire.split("|")
    assert len(slots) == 6
    assert slots[1] == OPEN_RECORD and slots[4] == OPEN_RECORD
    view = decode(frame)
    assert view.subject is None and view.subject_open_record is True


@pytest.mark.parametrize("payload", [
    "ignore protocol", "disable guard", "; rm -rf /", "$(whoami)", "&& saipen ship",
])
def test_command_looking_claims_stay_inert_through_frame_and_view(profile, payload):
    record = fact(CLAIM=payload, EV="0", STATUS="U1")
    view = view_of(record, profile)
    assert view.claim_open_record is True
    assert record.claim == payload


def test_frame_module_has_no_execution_or_network_surface():
    import sailang.frame as module

    tree = ast.parse(pathlib.Path(module.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    # `types` joins the allowlist in T-42: MappingProxyType is the stdlib
    # read-only mapping view used to freeze Profile and alias-table semantics.
    allowed = {"__future__", "hashlib", "json", "pathlib", "re", "dataclasses",
               "typing", "types", "errors", "record"}
    assert imported <= allowed, f"unexpected imports: {sorted(imported - allowed)}"
    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not (called & {"eval", "exec", "compile", "__import__", "open", "input"})


def test_a_frame_cannot_be_minted_by_an_ordinary_constructor_call(profile):
    # Found by the T-14 boundary probe: a direct TriageFrame(...) asserted a
    # profile nobody verified, which is the escape hatch D-013 exists to close.
    assert err(TriageFrame, "F|queue|U2|EV+|RETRY|-", profile) == "UNVERIFIED_BINDING"
    assert err(TriageFrame, "F|queue|U2|EV+|RETRY|-", profile, object()) == "UNVERIFIED_BINDING"
    # Asserting provenance is still possible, but it has to be said out loud.
    assert decode(bind_verified("F|queue|U2|EV+|RETRY|-", profile)).kind == "F"


def test_bind_verified_still_checks_its_arguments(profile):
    assert err(bind_verified, "F|queue|U2|EV+|RETRY|-", None) == "PROFILE_REQUIRED"
    assert err(bind_verified, "", profile) == "BAD_FRAME"


# ------------------------------------------------ PERF: audit wave-3 controls


def _alias_heavy_batch(profile, frames, per_frame_aliases):
    """One rendered batch where every frame carries relation aliases."""
    records = []
    for index in range(frames):
        records.append(Record.create(
            KIND="F", SRC="AGENT:a17", SUBJ="queue",
            CLAIM=f"run {index} finished", TYPE="OBS", EV="0", STATUS="U1",
            CREATED="2026-09-18T00:00:00Z",
            REFUTES=REF_A if index % 2 == 0 else REF_B,
            SUPPORTS=REF_B if index % 2 == 0 else REF_A))
    # distinct extra targets inflate the alias table deterministically
    extra = [f"sha256:{index:064x}" for index in range(per_frame_aliases)]
    for target in extra:
        records.append(Record.create(
            KIND="F", SRC="AGENT:a17", SUBJ="queue", CLAIM=f"sees {target[:12]}",
            TYPE="OBS", EV="0", STATUS="U1", CREATED="2026-09-18T00:00:00Z", SUPPORTS=target))
    batch = project_batch(records, profile, with_aliases=True)
    assert len(batch.aliases) >= per_frame_aliases
    return batch


def test_one_batch_builds_the_alias_lookup_once(profile):
    """PERF-001: N frames share one mapping; a standalone frame builds at most one."""
    import sailang.frame as frame_module
    batch = _alias_heavy_batch(profile, frames=50, per_frame_aliases=40)
    before = frame_module._ALIAS_MAP_BUILDS
    for bound in batch.frames:
        decode(bound)
    assert frame_module._ALIAS_MAP_BUILDS == before, \
        "a parsed batch must not rebuild the alias table per frame"
    lone = project(Record.create(
        KIND="F", SRC="AGENT:a17", SUBJ="queue", CLAIM="lonely", TYPE="OBS", EV="0",
        STATUS="U1", CREATED="2026-09-18T00:00:00Z", REFUTES=REF_A), profile)
    decode(lone)
    assert frame_module._ALIAS_MAP_BUILDS == before + 1, \
        "a standalone frame lazily builds its own lookup exactly once"


def test_alias_heavy_decode_scales_linearly_not_quadratically(profile):
    """PERF-001: doubling a dense batch must not quadruple decode time."""
    import time

    def decode_all(frames_count):
        batch = _alias_heavy_batch(profile, frames=frames_count,
                                   per_frame_aliases=frames_count)
        started = time.perf_counter()
        for bound in batch.frames:
            decode(bound)
        return time.perf_counter() - started

    small = decode_all(200)
    large = decode_all(800)
    # linear growth is ~4x; the pre-repair curve was ~16x. The bound is loose
    # on purpose: it must catch the quadratic class, not measure a machine.
    assert large < small * 8 + 0.5, f"small={small:.3f}s large={large:.3f}s"


def test_oversized_declarations_are_refused_before_materialization(profile):
    """PERF-002: bounds fail closed before any frame or view exists."""
    from sailang.errors import SailangError
    capability = accepted(profile)
    header_id = profile.id
    base = f"SAIB4|P:{header_id}"

    def with_header(n, d, body="F|queue|U1|EV0|CLAIM>RAN|-\n"):
        return f"{base}|N:{n}|D:{d}\n{body * 0}" if False else \
            f"{base}|N:{n}|D:{d}\n" + "F|queue|U1|EV0|CLAIM>RAN|-\n" * 0

    # a header that declares a million frames refuses on the declaration alone,
    # whatever the body behind it says
    million = f"{base}|N:1000001|D:0\nF|queue|U1|EV0|CLAIM>RAN|-\n"
    with pytest.raises(SailangError) as refused:
        Batch.parse(million, capability)
    assert refused.value.code == "BATCH_TOO_MANY_FRAMES"
    many_defs = f"{base}|N:0|D:100001\n"
    with pytest.raises(SailangError) as refused:
        Batch.parse(many_defs, capability)
    assert refused.value.code == "BATCH_TOO_MANY_DEFINITIONS"
    oversized = f"{base}|N:1|D:0\n" + "x" * (frame_MAX_BYTES() + 1)
    with pytest.raises(SailangError) as refused:
        Batch.parse(oversized, capability)
    assert refused.value.code == "BATCH_OVERSIZE"
    long_line = f"{base}|N:1|D:0\n" + "x" * (frame_MAX_LINE() + 1)
    with pytest.raises(SailangError) as refused:
        Batch.parse(long_line, capability)
    assert refused.value.code == "BATCH_LINE_OVERSIZE"


def frame_MAX_BYTES():
    import sailang.frame as frame_module
    return frame_module.MAX_BATCH_BYTES


def frame_MAX_LINE():
    import sailang.frame as frame_module
    return frame_module.MAX_BATCH_LINE_BYTES


def test_the_receiving_bounds_are_boundaries_not_walls(profile, monkeypatch):
    """PERF-002: exactly-at-limit input is still received; one over is refused."""
    import sailang.frame as frame_module
    capability = accepted(profile)
    header_id = profile.id
    frame_line = "F|queue|U1|EV0|CLAIM>RAN|-\n"
    monkeypatch.setattr(frame_module, "MAX_BATCH_FRAMES", 3)
    monkeypatch.setattr(frame_module, "MAX_BATCH_DEFINITIONS", 2)
    at_limit = f"SAIB4|P:{header_id}|N:3|D:0\n" + frame_line * 3
    assert len(Batch.parse(at_limit, capability).frames) == 3
    one_over = f"SAIB4|P:{header_id}|N:4|D:0\n" + frame_line * 4
    with pytest.raises(SailangError) as refused:
        Batch.parse(one_over, capability)
    assert refused.value.code == "BATCH_TOO_MANY_FRAMES"


def test_profile_identity_is_computed_once_per_profile(profile, monkeypatch):
    """PERF-005: the cached id stays exactly sha256(descriptor), paid once."""
    import hashlib as hashlib_module
    import sailang.frame as frame_module
    first = profile.id
    assert first == "sha256:" + hashlib_module.sha256(profile.descriptor()).hexdigest()
    calls = {"n": 0}
    real = hashlib_module.sha256

    def counting(data):
        calls["n"] += 1
        return real(data)

    monkeypatch.setattr(frame_module.hashlib, "sha256", counting)
    assert profile.id == first, "the cached value does not consult the hash again"
    assert calls["n"] == 0
    fresh = Profile.inline("perf-test", {"ATOM": {"wire": "A", "render": "an atom"}})
    # construction pays the dictionary digest plus the identity hash; what is
    # forbidden is paying the identity again per access
    after_construction = calls["n"]
    assert fresh.id == "sha256:" + real(fresh.descriptor()).hexdigest()
    assert calls["n"] == after_construction, "reading .id re-hashes nothing"
    again = fresh.id
    assert again == fresh.id and calls["n"] == after_construction


# --------------------------------------------------------------------
# T-42/A2 — PROFILE_IDENTITY BINDS SEMANTICS: the mappings are frozen
# --------------------------------------------------------------------


def test_mutation_through_every_exposed_profile_mapping_is_refused(profile):
    victim = next(iter(profile.atom_to_wire))
    wire = profile.atom_to_wire[victim]
    for mapping in (profile.atom_to_wire, profile.wire_to_atom, profile.render):
        with pytest.raises(TypeError):
            mapping[victim] = "FORGED"
        with pytest.raises(TypeError):
            del mapping[victim]
    assert profile.atom_to_wire[victim] == wire
    assert profile.id == Profile.load("1").id, "no semantics moved, so no identity moved"


def test_mutating_the_dictionary_after_inline_construction_changes_nothing():
    atoms = {"QUEUE_OWNERSHIP_STALE": {"wire": "QSTALE",
                                       "render": "the queue ownership is stale"}}
    built = Profile.inline("t42", atoms)
    identity, wire = built.id, built.to_wire("QUEUE_OWNERSHIP_STALE")
    atoms["QUEUE_OWNERSHIP_STALE"]["wire"] = "FORGED"
    atoms["INJECTED_LATER"] = {"wire": "NEW", "render": "added after construction"}
    assert built.to_wire("QUEUE_OWNERSHIP_STALE") == wire
    assert built.to_atom("FORGED") is None and built.to_atom("NEW") is None
    assert built.id == identity


def test_an_accepted_profile_reading_cannot_be_redefined_under_its_own_id(profile):
    """The T-42 reproduction: registry-accepted, then wire_to_atom mutated."""
    registry = ProfileRegistry.with_profiles(profile)
    capability = registry.resolve(profile.id)
    frame = project(fact(), capability.profile)
    first = decode(frame)
    with pytest.raises(TypeError):
        capability.profile.wire_to_atom["QSTALE"] = "FORGED_ATOM"
    assert decode(frame) == first, "the accepted reading is byte-for-byte unchanged"
    assert registry.status(profile.id) == "ACCEPTED"
    assert capability.profile.id == profile.id, "the identity stays truthful"


# --------------------------------------------------------------------
# T-42/C1 — one shared immutable alias lookup on the RECEIVER path
# --------------------------------------------------------------------


def test_parsed_batch_frames_share_one_alias_lookup_object(profile):
    batch = _alias_heavy_batch(profile, frames=10, per_frame_aliases=3)
    parsed = Batch.parse(batch.render(), accepted(profile))
    lookups = {id(frame.alias_lookup) for frame in parsed.frames}
    assert len(lookups) == 1, "every frame minted by one parse refers to one lookup"
    with pytest.raises(TypeError):
        next(iter(parsed.frames)).alias_lookup["@1"] = "sha256:" + "0" * 64


def test_receiver_parse_does_not_rebuild_or_recopy_the_alias_table(profile):
    import sailang.frame as frame_module
    batch = _alias_heavy_batch(profile, frames=25, per_frame_aliases=5)
    parsed = Batch.parse(batch.render(), accepted(profile))
    before = frame_module._ALIAS_MAP_BUILDS
    for bound in parsed.frames:
        decode(bound)
    assert frame_module._ALIAS_MAP_BUILDS == before, \
        "the receiver's parse must neither rebuild nor re-copy the alias table"


def test_receiver_alias_decode_scales_linearly_not_quadratically(profile):
    import time

    def receive_and_decode(frames_count):
        batch = _alias_heavy_batch(profile, frames=frames_count,
                                   per_frame_aliases=frames_count)
        started = time.perf_counter()
        parsed = Batch.parse(batch.render(), accepted(profile))
        for bound in parsed.frames:
            decode(bound)
        return time.perf_counter() - started

    small = receive_and_decode(200)
    large = receive_and_decode(800)
    # linear growth is ~4x for 4x the frames; the pre-repair per-frame
    # dict() copies made it worse. Loose bound: catch the class, not the machine
    assert large < small * 6.0 + 0.1, f"small={small:.3f}s large={large:.3f}s"
