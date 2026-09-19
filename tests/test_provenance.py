"""T-20 acceptance: authorship survives capture, and proposals never become orders."""

import hashlib
import json
import pathlib

import pytest

from saimail.provenance import (
    AMBIGUOUS,
    ASSISTANT_PROPOSAL,
    AUTHORITY_LADDER,
    Attribution,
    CAPTURE_UNRESOLVED,
    Capture,
    EXTERNAL_CAPTURE_ASSERTION,
    HOST_USER_TURN,
    MEASURED_EVIDENCE,
    SCOPE_RULE_FILE,
    SOURCE_CLASSES,
    SOURCE_KIND_IS_NOT_AUTHORSHIP,
    Segment,
    SegmentMap,
    SYSTEM_OBSERVATION,
    TRANSPORT_INTAKE_ONLY,
    UNEXAMINED_NO_AUTHORITY,
    USER_ACCEPTANCE,
    USER_ACCEPTANCE_OBSERVED,
    USER_INTENT,
    VERIFIED_LOCAL_CAPTURE,
    capture_status,
    intent_authority,
    load_attributions,
    load_maps,
    receipt_intent_authority,
    source_kind_conflicts,
)
from saimail import quarantine
from sailang import SailangError

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROV = ROOT / "provenance"
INTAKE = ROOT / ".saipen" / "intake" / "active"
QUARANTINE = PROV / quarantine.QUARANTINE_DIR


@pytest.fixture(scope="module")
def maps():
    return load_maps(PROV)


def err(fn, *a, **k):
    with pytest.raises(SailangError) as e:
        fn(*a, **k)
    return e.value.code


def seg(cls, start=0, end=10, receipt="R"):
    return Segment(receipt=receipt, start=start, end=end, source_class=cls)


def one_map(cls, receipt="R"):
    return {receipt: SegmentMap(receipt=receipt, body_sha256="x" * 64, body_length=10,
                                segments=(seg(cls, receipt=receipt),))}


# ------------------------------------------------ receipts stay untouched


def test_maps_describe_the_immutable_receipt_body_not_the_working_file(maps):
    # The working file drifts; the receipt does not. A map that pointed at the
    # working file would go stale every time the steward edited the document.
    for name in ("SRC-003", "SRC-004", "SRC-005", "SRC-006", "SRC-007"):
        source = json.loads((PROV / f"{name}.json").read_text(encoding="utf-8"))["source_path"]
        assert source.startswith(".saipen/intake/active/"), name


def test_receipts_are_not_modified_by_the_provenance_layer(maps):
    records = quarantine.load_records(QUARANTINE)
    for name, segment_map in maps.items():
        source = json.loads((PROV / f"{name}.json").read_text(encoding="utf-8"))["source_path"]
        body = ROOT / source
        if not body.is_file() and name in records:
            # A normal distribution carries a quarantined receipt's identity, not its
            # bytes (D-023). The map must still describe exactly the quarantined digest.
            record = records[name]
            assert (record.original_sha256, record.original_length) == (
                segment_map.body_sha256, segment_map.body_length), name
            continue
        segment_map.verify_against(body.read_bytes())


def test_a_changed_body_invalidates_its_map(maps):
    segment_map = maps["SRC-003"]
    assert err(segment_map.verify_against, b"different bytes") == "RECEIPT_CHANGED"


def test_the_layer_writes_nothing_into_saipen_state():
    source = (ROOT / "saimail" / "provenance.py").read_text(encoding="utf-8")
    assert ".saipen" not in source
    for forbidden in ("write_text", "write_bytes", "open(", "mkdir"):
        assert forbidden not in source, f"the provenance layer must not write: {forbidden}"


# ------------------------------------------------ mixed sources cannot contaminate


def test_every_class_is_from_the_closed_set():
    assert err(Segment, "R", 0, 5, "VIBES") == "BAD_SOURCE_CLASS"
    assert len(SOURCE_CLASSES) == 6


def test_unexamined_text_must_be_declared_not_skipped():
    assert err(SegmentMap, "R", "x" * 64, 20, (seg(AMBIGUOUS, 0, 5),)) == "SEGMENT_COVERAGE"
    assert err(SegmentMap, "R", "x" * 64, 20,
               (seg(AMBIGUOUS, 0, 5), seg(USER_INTENT, 8, 20))) == "SEGMENT_GAP"


@pytest.mark.parametrize("cls,expected", [
    (USER_INTENT, USER_INTENT),
    (USER_ACCEPTANCE, USER_ACCEPTANCE),
])
def test_user_authored_spans_carry_intent(cls, expected):
    att = Attribution("X", "R", 0)
    assert intent_authority(att, one_map(cls)) == expected


def test_an_assistant_proposal_is_never_an_instruction_on_its_own():
    att = Attribution("X", "R", 0)
    assert err(intent_authority, att, one_map(ASSISTANT_PROPOSAL)) == "ADOPTION_WITHOUT_ACCEPTANCE"


def test_ambiguous_authorship_stays_ambiguous():
    att = Attribution("X", "R", 0)
    assert err(intent_authority, att, one_map(AMBIGUOUS)) == "AMBIGUOUS_AUTHORSHIP"


def test_evidence_never_becomes_intent():
    att = Attribution("X", "R", 0)
    assert err(intent_authority, att, one_map(MEASURED_EVIDENCE)) == "EVIDENCE_IS_NOT_INTENT"


def test_adoption_requires_an_acceptance_that_is_actually_an_acceptance():
    maps = {**one_map(ASSISTANT_PROPOSAL, "P"), **one_map(MEASURED_EVIDENCE, "E")}
    att = Attribution("X", "P", 0, accepted_by=("E", 0))
    assert err(intent_authority, att, maps) == "NOT_AN_ACCEPTANCE"


def test_a_captured_acceptance_and_an_observed_one_are_different_authorities():
    captured = {**one_map(ASSISTANT_PROPOSAL, "P"), **one_map(USER_ACCEPTANCE, "A")}
    observed = {**one_map(ASSISTANT_PROPOSAL, "P"), **one_map(SYSTEM_OBSERVATION, "O")}
    assert intent_authority(Attribution("X", "P", 0, ("A", 0)), captured) == USER_ACCEPTANCE
    assert intent_authority(Attribution("X", "P", 0, ("O", 0)), observed) == USER_ACCEPTANCE_OBSERVED
    assert USER_ACCEPTANCE != USER_ACCEPTANCE_OBSERVED


def test_authorship_is_never_inferred_from_style():
    # Structural, not a grep over prose: what does the module import, and what
    # does it define? A classifier would need text machinery and a function that
    # returns a class from a body.
    import ast

    tree = ast.parse((ROOT / "saimail" / "provenance.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "hashlib", "json", "pathlib", "dataclasses",
                        "typing", "sailang"}
    assert "re" not in imported, "a regex here would be the beginning of style inference"
    functions = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    for forbidden in ("classify", "detect_author", "guess_class", "infer_class"):
        assert forbidden not in functions
    # every source class reaches a Segment only as a declared argument
    assert "source_class" in {
        a.arg for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) for a in n.args.args
    } | {"source_class"}


# ------------------------------------------------ the real audit


def test_the_shipped_sources_are_honestly_classified(maps):
    for name in ("SRC-003", "SRC-004", "SRC-005"):
        classes = maps[name].classes()
        assert set(classes) == {AMBIGUOUS}, (
            f"{name} is a transcript with no authorship markers; declaring anything else "
            "would be style inference"
        )


def test_the_backlog_audit_produces_the_recorded_verdicts(maps):
    expected = {
        "B-001": USER_ACCEPTANCE_OBSERVED, "B-002": USER_ACCEPTANCE_OBSERVED,
        "B-003": "AMBIGUOUS_AUTHORSHIP", "B-004": USER_ACCEPTANCE_OBSERVED,
        "B-005": USER_ACCEPTANCE_OBSERVED, "B-006": "AMBIGUOUS_AUTHORSHIP",
        "B-007": "AMBIGUOUS_AUTHORSHIP", "B-008": "EVIDENCE_IS_NOT_INTENT",
        "B-009": "EVIDENCE_IS_NOT_INTENT", "B-010": "EVIDENCE_IS_NOT_INTENT",
        # B-011..B-013 cite SRC-007 directly; T-44 correction 003 caps the
        # external host record it names at the observed rung (was USER_ACCEPTANCE
        # under correction 002, when an unresolvable assertion still minted it).
        "B-011": USER_ACCEPTANCE_OBSERVED, "B-012": USER_ACCEPTANCE_OBSERVED,
        "B-013": USER_ACCEPTANCE_OBSERVED,
        # provenance correction 001 declared T-41 authorized by SRC-017;
        # correction 002 removed the false SRC-019 carrier, SRC-017 is
        # AMBIGUOUS, and the attribution now refuses like any unattributed span
        "T-41": "AMBIGUOUS_AUTHORSHIP",
    }
    for att in load_attributions(PROV / "ATTRIBUTIONS.json"):
        try:
            got = intent_authority(att, maps)
        except SailangError as exc:
            got = exc.code
        assert got == expected[att.requirement], f"{att.requirement}: {got}"


def test_no_backlog_entry_claims_plain_user_acceptance(maps):
    # T-44 correction 003: no shipped attribution earns a plain captured
    # USER_ACCEPTANCE. SRC-007's external host record resolves at the observed
    # rung, ambiguous authorship refuses, and plain acceptance would require a
    # verified local carrier -- none exists in this repository.
    for att in load_attributions(PROV / "ATTRIBUTIONS.json"):
        try:
            assert intent_authority(att, maps) != USER_ACCEPTANCE, (
                f"{att.requirement} claims a captured acceptance, but chat is not captured"
            )
        except SailangError:
            pass


# --------------------------------------- provenance correction 001 (T-42)


def test_the_operator_source_carries_intent_and_the_model_plan_does_not(maps):
    # correction 002: the SRC-019 carrier claim was mechanically false, so
    # SRC-017 may not mint USER_ACCEPTANCE through it; undetermined authorship
    # is AMBIGUOUS and refuses, and SRC-018 still refuses as a model plan
    assert err(receipt_intent_authority, "SRC-017", maps) == "AMBIGUOUS_AUTHORSHIP", (
        "SRC-017 has no verifiable operator carrier; it must not carry intent"
    )
    assert err(receipt_intent_authority, "SRC-018", maps) == "MIXED_AUTHORSHIP", (
        "SRC-018 is a model-derived plan; as a whole receipt it must never direct work"
    )


def test_the_model_plan_cannot_adopt_itself(maps):
    plan = Attribution("derived-plan", "SRC-018", 0)
    assert err(intent_authority, plan, maps) == "ADOPTION_WITHOUT_ACCEPTANCE"


def test_src_017_and_src_018_have_the_maps_the_correction_declares(maps):
    for name in ("SRC-017", "SRC-018"):
        assert name in maps, f"{name} has no segment map; unexamined is not attributed"
        maps[name].verify_against((INTAKE / f"{name}.md").read_bytes())
    # correction 002: no capture at all -- the SRC-019 carrier claim was false
    assert maps["SRC-017"].capture is None, (
        "SRC-017 has no verifiable carrier; a capture object would re-assert one"
    )
    assert [s.source_class for s in maps["SRC-017"].segments] == [AMBIGUOUS]
    assert maps["SRC-018"].capture is None, "the model plan has no capture channel"


def test_the_kind_of_src_018_is_reported_as_transport_not_authorship(maps):
    metas = {
        "SRC-017": json.loads((INTAKE / "SRC-017.meta.json").read_text(encoding="utf-8")),
        "SRC-018": json.loads((INTAKE / "SRC-018.meta.json").read_text(encoding="utf-8")),
    }
    rows = {row["receipt"]: row for row in source_kind_conflicts(maps, metas)}
    assert rows["SRC-018"]["verdict"] == SOURCE_KIND_IS_NOT_AUTHORSHIP, (
        "SRC-018 arrived as user_instruction but is ASSISTANT_PROPOSAL; the hazard must "
        "be reported, not read as authority"
    )
    # correction 002 inverted this expectation: SRC-017's kind still SAYS
    # user_instruction while its segments are AMBIGUOUS, and that divergence
    # is exactly what the conflict row exists to report
    assert rows["SRC-017"]["verdict"] == SOURCE_KIND_IS_NOT_AUTHORSHIP, (
        "SRC-017 arrived as user_instruction but its authorship is undetermined; "
        "the hazard must be reported, not read as authority"
    )


def test_the_backlog_file_shows_its_provenance():
    text = (ROOT / "spec" / "BACKLOG.md").read_text(encoding="utf-8")
    for entry in ("B-001", "B-003", "B-008", "B-011", "B-012", "B-013"):
        index = text.index(f"### {entry}")
        assert "Provenance:" in text[index:index + 400], f"{entry} has no visible provenance"
    assert "never adopted" in text


def test_the_authority_ladder_is_the_lineage_not_one_receipt():
    assert AUTHORITY_LADDER == (
        "AUTHORITATIVE RECEIPT LINEAGE > DERIVED SPEC > IMPLEMENTATION > TESTS")
    for name in ("README.md", "spec/DECISIONS.md", "spec/BACKLOG.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "SRC-001 receipt  >  derived spec" not in text
        assert "SRC receipt  >  derived spec" not in text


# ------------------------------------------------ one receipt, one map (T-39/CORE-003)


def _write_map(directory, filename, receipt="SRC-900", cls=USER_INTENT):
    data = {"receipt": receipt, "body_sha256": "x" * 64, "body_length": 10,
            "receipt_source_kind_scope": TRANSPORT_INTAKE_ONLY,
            "segments": [{"start": 0, "end": 10, "source_class": cls}]}
    (directory / filename).write_text(json.dumps(data), encoding="utf-8")


def _map_dir(tmp_path, *files):
    scope = json.loads((PROV / SCOPE_RULE_FILE).read_text(encoding="utf-8"))
    (tmp_path / SCOPE_RULE_FILE).write_text(json.dumps(scope), encoding="utf-8")
    for name, cls in files:
        _write_map(tmp_path, name, "SRC-900", cls)
    return tmp_path


def test_a_receipt_declared_twice_is_refused_whichever_order(tmp_path):
    for index, order in enumerate((
            (("SRC-900.json", USER_INTENT), ("ZZZ-2.json", USER_ACCEPTANCE)),
            (("ZZZ-2.json", USER_ACCEPTANCE), ("SRC-900.json", USER_INTENT)))):
        directory = tmp_path / f"dup{index}"
        directory.mkdir()
        assert err(load_maps, _map_dir(directory, *order)) == "DUPLICATE_SEGMENT_MAP"


def test_a_map_file_must_be_named_after_the_receipt_it_declares(tmp_path):
    directory = tmp_path / "misnamed"
    directory.mkdir()
    assert err(load_maps, _map_dir(directory, ("WRONG.json", USER_INTENT))) == \
        "MAP_NAME_MISMATCH"


# ------------------------------------------------ RECEIPT-KIND-SCOPE-01 (D-017)


def metas():
    return {p.name[: -len(".meta.json")]: json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(INTAKE.glob("SRC-*.meta.json"))}


def naive_consumer_authority(meta):
    """An old consumer that predates segment maps and trusts the intake label."""
    return USER_INTENT if meta.get("source_kind") == "user_instruction" else None


def test_every_shipped_map_declares_the_source_kind_scope():
    rule = json.loads((PROV / SCOPE_RULE_FILE).read_text(encoding="utf-8"))
    assert rule["field"] == "source_kind"
    assert rule["scope"] == TRANSPORT_INTAKE_ONLY
    assert rule["authorship_authority"] == "SEGMENT_PROVENANCE"
    for path in sorted(PROV.glob("*.json")):
        if path.name in ("ATTRIBUTIONS.json", SCOPE_RULE_FILE):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["receipt_source_kind_scope"] == TRANSPORT_INTAKE_ONLY, path.name


def _copy_provenance(tmp_path, drop_rule=False, mutate=None):
    for path in PROV.glob("*.json"):
        if drop_rule and path.name == SCOPE_RULE_FILE:
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if mutate:
            data = mutate(path.name, data)
        (tmp_path / path.name).write_text(json.dumps(data), encoding="utf-8")
    return tmp_path


def test_no_rule_file_means_no_maps(tmp_path):
    assert err(load_maps, _copy_provenance(tmp_path, drop_rule=True)) == "SOURCE_KIND_SCOPE_UNDECLARED"


def test_a_map_silent_about_the_scope_is_refused(tmp_path):
    def strip(name, data):
        if name == "SRC-005.json":
            del data["receipt_source_kind_scope"]
        return data
    assert err(load_maps, _copy_provenance(tmp_path, mutate=strip)) == "SOURCE_KIND_SCOPE_UNDECLARED"


@pytest.mark.parametrize("name,key,value", [
    (SCOPE_RULE_FILE, "scope", "AUTHORSHIP"),
    (SCOPE_RULE_FILE, "authorship_authority", "RECEIPT_SOURCE_KIND"),
    ("SRC-005.json", "receipt_source_kind_scope", "AUTHORSHIP"),
])
def test_the_scope_cannot_be_weakened(tmp_path, name, key, value):
    def weaken(file_name, data):
        if file_name == name:
            data[key] = value
        return data
    assert err(load_maps, _copy_provenance(tmp_path, mutate=weaken)) == "SOURCE_KIND_SCOPE_INVALID"


def test_the_naive_consumer_hazard_is_real_and_machine_detected(maps):
    intake = metas()
    # The hazard, stated as a fact rather than assumed: an old consumer reads
    # SRC-005 as user intent.
    assert naive_consumer_authority(intake["SRC-005"]) == USER_INTENT
    rows = {row["receipt"]: row for row in source_kind_conflicts(maps, intake)}
    for receipt in ("SRC-003", "SRC-004", "SRC-005"):
        assert rows[receipt]["verdict"] == SOURCE_KIND_IS_NOT_AUTHORSHIP
        assert rows[receipt]["source_kind"] == "user_instruction"
        assert rows[receipt]["segment_classes"] == {AMBIGUOUS: maps[receipt].body_length}
        assert rows[receipt]["rule"] == "RECEIPT-KIND-SCOPE-01"
    for receipt in ("SRC-001", "SRC-002"):
        assert rows[receipt]["verdict"] == UNEXAMINED_NO_AUTHORITY
    assert "SRC-006" not in rows, "a clean captured turn is not a conflict"


def test_the_authority_api_refuses_what_the_naive_consumer_grants(maps):
    for receipt, meta in metas().items():
        naive = naive_consumer_authority(meta)
        try:
            real = receipt_intent_authority(receipt, maps, meta)
        except SailangError as exc:
            real = exc.code
        if receipt in ("SRC-003", "SRC-004", "SRC-005"):
            assert naive == USER_INTENT and real == "AMBIGUOUS_AUTHORSHIP", receipt
        elif receipt in ("SRC-001", "SRC-002"):
            assert real == "NO_SEGMENT_MAP", receipt
        assert real != USER_INTENT, f"{receipt}: nothing shipped is plain user intent"


def test_hostile_metadata_cannot_upgrade_or_substitute(maps):
    body = maps["SRC-005"].body_sha256
    hostile = {"receipt_id": "SRC-005", "source_kind": "user_instruction", "source_sha256": body,
               "source_class": USER_INTENT, "authority": USER_INTENT, "segments": USER_INTENT}
    assert err(receipt_intent_authority, "SRC-005", maps, hostile) == "AMBIGUOUS_AUTHORSHIP"
    stale = dict(hostile, source_sha256="0" * 64)
    assert err(receipt_intent_authority, "SRC-005", maps, stale) == "RECEIPT_CHANGED"
    borrowed = dict(metas()["SRC-006"])
    assert err(receipt_intent_authority, "SRC-005", maps, borrowed) == "SEGMENT_RECEIPT_MISMATCH"
    # metadata alone never substitutes for a map
    assert err(receipt_intent_authority, "SRC-999", maps,
               dict(hostile, receipt_id="SRC-999")) == "NO_SEGMENT_MAP"


def test_no_receipt_with_an_ambiguous_span_is_intent_whatever_its_kind():
    import itertools

    meta_kinds = ("user_instruction", "user_audit", "external_audit", None)
    checked = 0
    for size in (1, 2, 3):
        for classes in itertools.product(SOURCE_CLASSES, repeat=size):
            segments = tuple(seg(c, start=i * 10, end=(i + 1) * 10) for i, c in enumerate(classes))
            maps = {"R": SegmentMap("R", "x" * 64, 10 * size, segments)}
            for kind in meta_kinds:
                meta = {"receipt_id": "R", "source_kind": kind, "source_sha256": "x" * 64}
                try:
                    got = receipt_intent_authority("R", maps, meta)
                except SailangError as exc:
                    got = exc.code
                if AMBIGUOUS in classes:
                    assert got == "AMBIGUOUS_AUTHORSHIP", classes
                elif set(classes) <= {USER_INTENT, USER_ACCEPTANCE}:
                    assert got == (USER_ACCEPTANCE if USER_ACCEPTANCE in classes else USER_INTENT)
                else:
                    assert got == "MIXED_AUTHORSHIP", classes
                checked += 1
    assert checked == (6 + 36 + 216) * len(meta_kinds)


def test_segment_level_precision_survives_the_receipt_level_refusal():
    maps = {"R": SegmentMap("R", "x" * 64, 20, (seg(USER_INTENT, 0, 10), seg(AMBIGUOUS, 10, 20)))}
    assert intent_authority(Attribution("X", "R", 0), maps) == USER_INTENT
    assert err(intent_authority, Attribution("X", "R", 1), maps) == "AMBIGUOUS_AUTHORSHIP"
    assert err(receipt_intent_authority, "R", maps) == "AMBIGUOUS_AUTHORSHIP"


def test_source_kind_never_reaches_a_class():
    import ast

    tree = ast.parse((ROOT / "saimail" / "provenance.py").read_text(encoding="utf-8"))
    readers = set()
    for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
        for node in ast.walk(fn):
            if isinstance(node, ast.Constant) and node.value == "source_kind":
                readers.add(fn.name)
            if isinstance(node, ast.Name) and node.id == "source_kind":
                readers.add(fn.name)
    # the detector reports the hazard and the loader checks that the rule names
    # the field; neither returns a source class
    assert readers <= {"source_kind_conflicts", "load_scope_rule"}, readers
    for authority_fn in ("intent_authority", "receipt_intent_authority"):
        assert authority_fn not in readers


def test_capture_is_bound_to_the_bytes_it_names():
    capture = Capture(channel=HOST_USER_TURN, host_record="r1", extracted_sha256="y" * 64)
    assert err(SegmentMap, "R", "x" * 64, 10, (seg(USER_ACCEPTANCE),),
               capture=capture) == "CAPTURE_MISMATCH"
    assert err(Capture, "EMAIL_FORWARD", "r1", "x" * 64) == "BAD_CAPTURE_CHANNEL"
    assert err(SegmentMap, "R", "x" * 64, 10, (seg(USER_INTENT),),
               source_kind_scope="AUTHORSHIP") == "SOURCE_KIND_SCOPE_INVALID"


# --------------------------------------------- capture carrier proof (T-43 / correction 002)

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _carrier_map(capture: Capture, cls=USER_ACCEPTANCE, receipt="SRC-950"):
    digest = _sha(b"operator words here")
    return SegmentMap(receipt=receipt, body_sha256=digest, body_length=19,
                      segments=(Segment(receipt=receipt, start=0, end=19,
                                        source_class=cls),), capture=capture)


def _local_carriers():
    body = b"operator words here"
    carrier = b"preamble chatter\n" + body + b"\ntrailing chatter"
    other = b"a completely different local receipt that carries nothing relevant"
    return body, {
        "CARRIER-REC": carrier,
        "OTHER-REC": other,
    }


#: the body sits in CARRIER-REC at [17:35]: len(b"preamble chatter\n") == 17
_BODY_SPAN = (17, 36)


def _verified_capture(carriers, start=_BODY_SPAN[0], end=_BODY_SPAN[1],
                      carrier_sha=None):
    return Capture(channel=HOST_USER_TURN, host_record="CARRIER-REC",
                   extracted_sha256=_sha(b"operator words here"),
                   carrier_sha256=carrier_sha or _sha(carriers["CARRIER-REC"]),
                   carrier_start=start, carrier_end=end)


def test_a_self_asserted_local_carrier_cannot_mint_acceptance():
    # the SRC-017 defect, as a red control: receipt body X, capture names
    # another LOCAL receipt that does not contain X, extracted = sha256(X).
    # Before CAPTURE-PROOF-01 this map was authority-bearing; now the locally
    # addressable carrier without a verifiable span claim is refused.
    body, carriers = _local_carriers()
    capture = Capture(channel=HOST_USER_TURN, host_record="OTHER-REC",
                      extracted_sha256=_sha(body))
    segment_map = _carrier_map(capture)
    assert err(capture_status, segment_map, carriers) == "CAPTURE_UNVERIFIABLE"
    assert err(receipt_intent_authority, "SRC-950", {"SRC-950": segment_map},
               None, carriers) == "CAPTURE_UNVERIFIABLE"


def test_an_exact_local_carrier_span_verifies():
    _, carriers = _local_carriers()
    segment_map = _carrier_map(_verified_capture(carriers))
    assert capture_status(segment_map, carriers) == VERIFIED_LOCAL_CAPTURE
    assert receipt_intent_authority("SRC-950", {"SRC-950": segment_map},
                                    None, carriers) == USER_ACCEPTANCE


def test_a_wrong_span_refuses():
    _, carriers = _local_carriers()
    for start, end in ((18, 37), (0, 18)):
        segment_map = _carrier_map(_verified_capture(carriers, start, end))
        assert err(capture_status, segment_map, carriers) == "CARRIER_SPAN_MISMATCH"
        assert err(receipt_intent_authority, "SRC-950", {"SRC-950": segment_map},
                   None, carriers) == "CARRIER_SPAN_MISMATCH"


def test_a_wrong_carrier_digest_refuses():
    _, carriers = _local_carriers()
    segment_map = _carrier_map(_verified_capture(carriers, carrier_sha="0" * 64))
    assert err(capture_status, segment_map, carriers) == "CARRIER_DIGEST_MISMATCH"


def test_a_missing_local_carrier_is_unresolved_not_external():
    # a capture that DECLARES a local carrier must not fall back to the
    # external-assertion path when its bytes are absent: the named state is
    # CAPTURE_UNRESOLVED and nothing is minted
    _, carriers = _local_carriers()
    segment_map = _carrier_map(_verified_capture(carriers))
    assert capture_status(segment_map, {}) == CAPTURE_UNRESOLVED
    assert err(receipt_intent_authority, "SRC-950", {"SRC-950": segment_map}) == (
        "CAPTURE_UNRESOLVED")


def test_an_external_host_record_stays_a_named_assertion():
    # historical shape (SRC-006/SRC-007): a host record this repository cannot
    # resolve keeps its standing, under a name that says it was never verified.
    # T-44 correction 003: the standing it keeps is the observed/asserted rung
    # -- an assertion is not captured bytes (historical reason preserved: this
    # shape was once trusted as USER_ACCEPTANCE under correction 002).
    _, carriers = _local_carriers()
    capture = Capture(channel=HOST_USER_TURN, host_record="c21ffd04-0000-0000-0000-1",
                      extracted_sha256=_sha(b"operator words here"))
    segment_map = _carrier_map(capture)
    assert capture_status(segment_map, carriers) == EXTERNAL_CAPTURE_ASSERTION
    assert capture_status(segment_map) == EXTERNAL_CAPTURE_ASSERTION
    assert receipt_intent_authority("SRC-950", {"SRC-950": segment_map}) == (
        USER_ACCEPTANCE_OBSERVED)


def test_a_local_carrier_claim_is_complete_or_absent():
    assert err(Capture, HOST_USER_TURN, "r", "x" * 64, "y" * 64, 0) == "BAD_CAPTURE"
    assert err(Capture, HOST_USER_TURN, "r", "x" * 64, None, 0, 10) == "BAD_CAPTURE"
    assert err(Capture, HOST_USER_TURN, "r", "x" * 64, "y" * 64, 10, 2) == "BAD_CAPTURE"


def test_the_loader_reads_the_carrier_triple(tmp_path):
    import shutil
    work = tmp_path / "prov"
    work.mkdir()
    for name in (SCOPE_RULE_FILE,):
        shutil.copy(PROV / name, work / name)
    body, carriers = _local_carriers()
    carrier = carriers["CARRIER-REC"]
    data = {"receipt": "SRC-951", "body_sha256": _sha(body), "body_length": len(body),
            "receipt_source_kind_scope": TRANSPORT_INTAKE_ONLY,
            "capture": {"channel": HOST_USER_TURN, "host_record": "CARRIER-REC",
                        "extracted_sha256": _sha(body), "carrier_sha256": _sha(carrier),
                        "carrier_start": _BODY_SPAN[0], "carrier_end": _BODY_SPAN[1]},
            "segments": [{"start": 0, "end": len(body), "source_class": USER_ACCEPTANCE}]}
    (work / "SRC-951.json").write_text(json.dumps(data), encoding="utf-8")
    loaded = load_maps(work)
    assert loaded["SRC-951"].capture.declares_local_carrier
    assert capture_status(loaded["SRC-951"], carriers) == VERIFIED_LOCAL_CAPTURE


def test_the_steward_turn_006_is_an_external_assertion_capped_at_observed(maps):
    segment_map = maps["SRC-006"]
    body = (INTAKE / "SRC-006.md").read_bytes()
    segment_map.verify_against(body)
    assert segment_map.capture.channel == HOST_USER_TURN
    assert segment_map.capture.extracted_sha256 == segment_map.body_sha256
    assert [s.source_class for s in segment_map.segments] == [USER_ACCEPTANCE]
    meta = metas()["SRC-006"]
    assert meta["source_kind"] == "user_instruction"
    assert meta["transport"]["transport_transform"] == "none"
    # T-44 correction 003: the declared class is preserved, but the external
    # host record was never resolvable, so the authority resolves at the
    # observed rung, never as mechanically captured acceptance.
    assert receipt_intent_authority("SRC-006", maps, meta) == USER_ACCEPTANCE_OBSERVED
    # exactly one turn: the capture boundary is the turn boundary
    text = body.decode("utf-8")
    assert text.startswith("SAIMAIL\n\nCONTINUATION CORRECTION")
    assert text.endswith("STOP after T-17.\nDo not start crypto.")


def test_the_steward_turn_007_is_an_external_assertion_capped_at_observed(maps):
    segment_map = maps["SRC-007"]
    record = quarantine.load_records(QUARANTINE)["SRC-007"]
    path = INTAKE / "SRC-007.md"
    original = path.read_bytes() if path.is_file() else None
    if original is not None:
        segment_map.verify_against(original)
    # SRC-007 is quarantined (D-023): its words are read through the sanitized
    # derivative, the surface that travels, bound to the digest this map describes.
    body = (ROOT / record.derivative.path).read_bytes()
    assert quarantine.verify_derivative(record, body, original) == (
        quarantine.VERIFIED_AGAINST_ORIGINAL if original is not None else quarantine.HASH_BOUND)
    assert record.original_sha256 == segment_map.body_sha256
    assert segment_map.capture.channel == HOST_USER_TURN
    assert segment_map.capture.extracted_sha256 == segment_map.body_sha256
    assert [s.source_class for s in segment_map.segments] == [USER_ACCEPTANCE]
    meta = metas()["SRC-007"]
    assert meta["source_kind"] == "user_instruction"
    assert meta["transport"]["transport_transform"] == "none"
    # T-44 correction 003: same cap as SRC-006 -- asserted externally, observed.
    assert receipt_intent_authority("SRC-007", maps, meta) == USER_ACCEPTANCE_OBSERVED
    text = body.decode("utf-8")
    assert "SAIMAIL" in text
    assert "STOP BEFORE CRYPTO" in text


# ------------------------------- external capture assertion ceiling (T-44 / SRC-021)


def _external_assertion_map(host_record, cls=USER_ACCEPTANCE, receipt="SRC-960"):
    capture = Capture(channel=HOST_USER_TURN, host_record=host_record,
                      extracted_sha256=_sha(b"operator words here"))
    return _carrier_map(capture, cls=cls, receipt=receipt)


def test_an_unresolvable_external_assertion_never_mints_captured_acceptance():
    # T-44 Target A red control: a newly invented external host id, no
    # repository carrier, no verification triple. An assertion is not captured
    # bytes, so the strongest rung it supports is the observed/asserted one.
    invented = "0f4b7c21-9d3e-4a55-b0c6-6a1f2e8d4b93"
    segment_map = _external_assertion_map(invented)
    assert capture_status(segment_map) == EXTERNAL_CAPTURE_ASSERTION
    assert receipt_intent_authority("SRC-960", {"SRC-960": segment_map}) == (
        USER_ACCEPTANCE_OBSERVED)
    assert intent_authority(Attribution("X", "SRC-960", 0), {"SRC-960": segment_map}) == (
        USER_ACCEPTANCE_OBSERVED)


def test_adoption_through_an_external_assertion_stays_observed():
    proposal = one_map(ASSISTANT_PROPOSAL, "P")
    segment_map = _external_assertion_map("4a1c8f60-3d7b-4e29-9c05-81b6f2d0e7a3",
                                          receipt="SRC-961")
    att = Attribution("X", "P", 0, accepted_by=("SRC-961", 0))
    assert intent_authority(att, {**proposal, "SRC-961": segment_map}) == (
        USER_ACCEPTANCE_OBSERVED)


def test_an_external_assertion_cannot_mint_declared_user_intent():
    # USER_INTENT has no weaker observed rung: authorship that can only be
    # asserted is refused rather than returned under a stronger name.
    segment_map = _external_assertion_map("b7e2d94a-5c68-4f13-8a70-90d3e5c1b246",
                                          cls=USER_INTENT, receipt="SRC-962")
    assert err(receipt_intent_authority, "SRC-962", {"SRC-962": segment_map}) == (
        "EXTERNAL_CAPTURE_NOT_PROOF")
    assert err(intent_authority, Attribution("X", "SRC-962", 0),
               {"SRC-962": segment_map}) == "EXTERNAL_CAPTURE_NOT_PROOF"


def test_the_capture_authority_matrix_is_mechanical(maps):
    # T-44 Target A / A5: every required row in one place.
    _, carriers = _local_carriers()

    verified = _carrier_map(_verified_capture(carriers))
    assert receipt_intent_authority("SRC-950", {"SRC-950": verified}, None, carriers) == (
        USER_ACCEPTANCE)

    wrong_span = _carrier_map(_verified_capture(carriers, start=0, end=19))
    assert err(receipt_intent_authority, "SRC-950", {"SRC-950": wrong_span}, None,
               carriers) == "CARRIER_SPAN_MISMATCH"

    missing = _carrier_map(_verified_capture(carriers))
    assert err(receipt_intent_authority, "SRC-950", {"SRC-950": missing}, None, {}) == (
        "CAPTURE_UNRESOLVED")

    external = _external_assertion_map("d5b1e803-7a4c-4f16-9e28-3c0b6d9f1a72")
    assert receipt_intent_authority("SRC-960", {"SRC-960": external}) != USER_ACCEPTANCE
    assert receipt_intent_authority("SRC-960", {"SRC-960": external}) == (
        USER_ACCEPTANCE_OBSERVED)
    assert receipt_intent_authority("SRC-006", maps, metas()["SRC-006"]) == (
        USER_ACCEPTANCE_OBSERVED)

    assert err(receipt_intent_authority, "R", one_map(AMBIGUOUS)) == "AMBIGUOUS_AUTHORSHIP"

    proposal = one_map(ASSISTANT_PROPOSAL, "P")
    assert err(receipt_intent_authority, "P", proposal) == "MIXED_AUTHORSHIP"
    assert err(intent_authority, Attribution("X", "P", 0), proposal) == (
        "ADOPTION_WITHOUT_ACCEPTANCE")
    observed = {**proposal, **one_map(SYSTEM_OBSERVATION, "O")}
    assert intent_authority(Attribution("X", "P", 0, ("O", 0)), observed) == (
        USER_ACCEPTANCE_OBSERVED)
