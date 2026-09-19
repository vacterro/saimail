"""T-32 acceptance: a credential-bearing receipt keeps its identity, not its distribution (D-023).

Every check that touches the quarantined material compares bytes in memory and
asserts on a boolean, a count or a list of paths. No assertion here can print
the withheld component, and nothing here copies the original to disk: the
archive is built in memory and unpacked only after it is proven clean.
"""

from __future__ import annotations

import copy
import io
import json
import pathlib
import zipfile

import pytest

from sailang import SailangError
from saimail import quarantine as q
from saimail.provenance import (AMBIGUOUS, USER_ACCEPTANCE, USER_ACCEPTANCE_OBSERVED,
                                Attribution, Segment, SegmentMap, intent_authority,
                                load_attributions, load_maps, receipt_intent_authority)
from tools import quarantine_receipt as tool

ROOT = pathlib.Path(__file__).resolve().parent.parent
PROV = ROOT / "provenance"
QDIR = PROV / q.QUARANTINE_DIR
MEMORY_ROOT = ".saipen"
INTAKE = ROOT / MEMORY_ROOT / "intake" / "active"
MANIFEST = ROOT / MEMORY_ROOT / "MANIFEST.json"
PROPOSAL = ROOT / "spec" / "PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md"

ORIGINAL_ABSENT = ("the quarantined original is not in this distribution; checks against its "
                   "bytes run only where the original exists (D-023)")
#: Assembled at run time so no credential-shaped literal sits in this file.
LABEL = "to" + "ken"


def err(fn, *a, **k):
    with pytest.raises(SailangError) as e:
        fn(*a, **k)
    return e.value.code


@pytest.fixture(scope="module")
def records():
    return q.load_records(QDIR)


@pytest.fixture(scope="module")
def maps():
    return load_maps(PROV)


@pytest.fixture()
def raw():
    return json.loads((QDIR / "SRC-007.json").read_text(encoding="utf-8"))


def original(record):
    return q.find_original(ROOT, record)


def derivative(record):
    return (ROOT / record.derivative.path).read_bytes()


def withheld(record, body):
    return q.withheld_fragments(record, body)


def carries_any(data: bytes, pieces) -> bool:
    lowered = data.lower()
    return any(piece in lowered for piece in pieces)


# ------------------------------------------------ A1: the incident, proven by structure


def test_src007_holds_credential_bearing_material_found_by_structure_alone(records):
    record = records["SRC-007"]
    body = original(record)
    if body is None:
        pytest.skip(ORIGINAL_ABSENT)
    findings = q.scan(body)
    assert sorted({f.category for f in findings}) == [q.CREDENTIAL_LABELLED_FILENAME]
    assert [f.line for f in findings] == [3]
    assert [f.as_record() for f in findings] == [f.as_record() for f in record.findings]


def test_the_evidence_of_the_incident_never_carries_the_material(records, capsys):
    record = records["SRC-007"]
    body = original(record)
    if body is None:
        pytest.skip(ORIGINAL_ABSENT)
    pieces = withheld(record, body)
    findings = q.scan(body)
    assert tool.main(["--check"]) == 0
    surfaces = {
        "finding repr": repr(findings).encode("utf-8"),
        "finding records": json.dumps([f.as_record() for f in findings]).encode("utf-8"),
        "tool output": capsys.readouterr().out.encode("utf-8"),
        "quarantine record": (QDIR / "SRC-007.json").read_bytes(),
        "sanitized derivative": derivative(record),
        "detector source": (ROOT / "saimail" / "quarantine.py").read_bytes(),
        "writer source": (ROOT / "tools" / "quarantine_receipt.py").read_bytes(),
        "these tests": pathlib.Path(__file__).read_bytes(),
        "decision log": (ROOT / "spec" / "DECISIONS.md").read_bytes(),
        "protocol change proposal": PROPOSAL.read_bytes(),
    }
    leaked = sorted(name for name, data in surfaces.items() if carries_any(data, pieces))
    assert leaked == []
    named = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                   if carries_any(p.name.encode("utf-8"), pieces))
    assert named == []


def test_intake_metadata_understates_the_receipt_and_the_record_says_so(records):
    record = records["SRC-007"]
    meta = json.loads((INTAKE / "SRC-007.meta.json").read_text(encoding="utf-8"))
    assert meta["source_sha256"] == record.original_sha256
    snapshot = record.evidence["original"]["intake_metadata_at_quarantine"]
    assert snapshot["sensitive"] is False and snapshot["redaction_applied"] is False
    assert record.evidence["reason"]["metadata_disagreement"] == q.SENSITIVITY_METADATA_UNDERSTATED
    assert record.evidence["reason"]["credential_rotation"] == q.ROTATION_UNKNOWN


def test_every_credential_bearing_receipt_present_is_quarantined(records):
    unexamined = sorted(path.stem for path in INTAKE.glob("SRC-*.md")
                        if q.scan(path.read_bytes()) and path.stem not in records)
    assert unexamined == []


def test_a_slash_in_prose_is_not_a_path():
    # SRC-011 carries `secret/private-key sweep`; prose must not be read as a
    # file name, and a correction receipt must not demand a quarantine (D-027).
    for prose in ("a sweep for secret/private-key material\n",
                  "delete keys/prod-token before shipping\n",
                  "add the credential/private-key check\n",
                  "see docs/token.md\n"):
        assert q.scan(prose.encode("utf-8")) == (), prose
    # a real file shape still trips: backslash path, root anchor, extension
    assert [f.category for f in q.scan(b"x\nC:\\k\\ops_token_live\n")] == \
        [q.CREDENTIAL_LABELLED_FILENAME]
    assert [f.category for f in q.scan(b"x\n/var/keys/my_secret_store\n")] == \
        [q.CREDENTIAL_LABELLED_FILENAME]


def test_a_filename_pairing_a_secret_label_with_other_runs_is_found():
    body = f"intro\nsee C:\\tmp\\deploy_{LABEL}_prod.txt now\n".encode("utf-8")
    (finding,) = q.scan(body)
    assert (finding.category, finding.line) == (q.CREDENTIAL_LABELLED_FILENAME, 2)
    assert body[finding.start:finding.end] == f"deploy_{LABEL}_prod.txt".encode("utf-8")


@pytest.mark.parametrize("text", [
    "saimail/credentials.py",
    "tools/provision_sairoute_credential.py",
    "lab/out/saifren_live_20260917T152012Z.json",
    "credential://9router/sairoute",
    "http://127.0.0.1:20128/v1/models",
    f"docs/{LABEL}.md",
    "sha256:" + "ab12" * 16,
])
def test_ordinary_paths_and_digests_are_not_findings(text):
    assert q.scan(f"see {text} here".encode("utf-8")) == ()


def test_generated_and_published_credential_shapes_are_found():
    generated = "Zq8Lr2Tv9Wy4Pb6Nc3Md7Kf1Hg5"
    prefixed = "s" + "k-" + "A1b2C3d4E5f6G7h8J9k0"
    assigned = "pass" + "word = " + "hunter22hunter"
    body = f"a/{generated}/b\nuse {prefixed}\n{assigned}\n".encode("utf-8")
    categories = [(f.category, f.line) for f in q.scan(body)]
    assert (q.HIGH_ENTROPY_PATH_COMPONENT, 1) in categories
    assert (q.KNOWN_CREDENTIAL_SHAPE, 2) in categories
    assert (q.CREDENTIAL_ASSIGNMENT, 3) in categories


def test_findings_are_positions_and_never_text():
    value = "s" + "k-" + "Q9w8E7r6T5y4U3i2O1p0"
    findings = q.scan(f"key material {value} end".encode("utf-8"))
    assert findings
    assert {k for f in findings for k in f.as_record()} == {"category", "line", "start", "end"}
    assert value not in repr(findings)
    assert value not in json.dumps([f.as_record() for f in findings])


def test_offsets_are_utf8_bytes_and_the_scan_is_deterministic():
    body = f"— ünïcödé —\nC:\\x\\my_{LABEL}_file.txt\n".encode("utf-8")
    (finding,) = q.scan(body)
    assert body[finding.start:finding.end].decode("utf-8") == f"my_{LABEL}_file.txt"
    assert q.scan(body) == q.scan(body)
    assert err(q.scan, b"\xff\xfe not utf-8") == "BODY_NOT_UTF8"


# ------------------------------------------------ A2: the states


def test_distribution_states_are_a_closed_set_beside_intake_status(records):
    assert q.DISTRIBUTION_STATES == ("ACTIVE_NORMAL", "SENSITIVE_QUARANTINED",
                                     "SANITIZED_DERIVATIVE")
    assert q.distribution_state("SRC-007", records) == q.SENSITIVE_QUARANTINED
    assert q.distribution_state(records["SRC-007"].derivative.id, records) == \
        q.SANITIZED_DERIVATIVE
    for meta in INTAKE.glob("SRC-*.meta.json"):
        receipt = meta.name[: -len(".meta.json")]
        if receipt != "SRC-007":
            assert q.distribution_state(receipt, records) == q.ACTIVE_NORMAL, receipt


def test_intake_lifecycle_status_decides_nothing_here():
    body = f"x\nC:\\k\\ops_{LABEL}_live.txt\n".encode("utf-8")
    meta = {"source_sha256": q.sha256_hex(body), "sensitive": False,
            "redaction": {"applied": False}}
    built = {status: q.build_record("SRC-900", body, {**meta, "status": status}, "o.md", "d.md",
                                    evidence={})
             for status in ("ACTIVE", "CLOSED")}
    active, closed = built["ACTIVE"], built["CLOSED"]
    assert active[1] == closed[1]
    for record in (active[0], closed[0]):
        record["original"].pop("intake_metadata_at_quarantine")
    assert active[0] == closed[0]


def test_the_original_keeps_its_identity(records, maps):
    record = records["SRC-007"]
    meta = json.loads((INTAKE / "SRC-007.meta.json").read_text(encoding="utf-8"))
    assert record.original_sha256 == meta["source_sha256"] == maps["SRC-007"].body_sha256
    assert record.original_length == maps["SRC-007"].body_length
    body = original(record)
    if body is not None:
        assert q.sha256_hex(body) == record.original_sha256


def test_the_quarantine_layer_writes_nothing():
    source = (ROOT / "saimail" / "quarantine.py").read_text(encoding="utf-8")
    assert ".saipen" not in source
    for forbidden in ("write_text", "write_bytes", "open(", "mkdir", "unlink", ".rename(",
                      "rmtree"):
        assert forbidden not in source, f"the quarantine layer must not write: {forbidden}"


# ------------------------------------------------ A3: the sanitized derivative


def test_the_derivative_records_what_the_contract_names(records, raw):
    record = records["SRC-007"]
    body = derivative(record)
    assert raw["receipt"] == "SRC-007"
    assert len(raw["original"]["sha256"]) == 64
    assert raw["derivative"]["sha256"] == q.sha256_hex(body)
    assert raw["reason"]["category"] == q.CREDENTIAL_BEARING_FILENAME
    assert raw["derivative"]["redaction_version"] == q.REDACTION_VERSION == "saimail-redaction/1"
    assert raw["derivative"]["authority"]["represents"] == "SRC-007"


def test_an_explicit_marker_stands_where_the_component_was(records):
    record = records["SRC-007"]
    body = derivative(record)
    (redaction,) = record.derivative.redactions
    assert body[redaction.sanitized_start:redaction.sanitized_end] == q.marker(redaction.category)
    line = body.decode("utf-8").split("\n")[2]
    assert line.endswith(q.marker(q.CREDENTIAL_BEARING_FILENAME).decode("ascii"))
    assert line.startswith("v:\\")


def test_the_derivative_is_faithful_everywhere_else(records):
    record = records["SRC-007"]
    body = derivative(record)
    original_body = original(record)
    fidelity = q.verify_derivative(record, body, original_body)
    if original_body is None:
        assert fidelity == q.HASH_BOUND
        return
    assert fidelity == q.VERIFIED_AGAINST_ORIGINAL
    (r,) = record.derivative.redactions
    assert body[:r.sanitized_start] == original_body[:r.original_start]
    assert body[r.sanitized_end:] == original_body[r.original_end:]


def test_the_record_is_reproduced_exactly_from_the_original(records, raw):
    record = records["SRC-007"]
    if original(record) is None:
        pytest.skip(ORIGINAL_ABSENT)
    under = raw["quarantined_under"]
    rebuilt, sanitized = tool.build(ROOT, "SRC-007", under["source_receipt"], under["ticket"],
                                    under["decision"],
                                    raw["reason"]["operator_statement"]["says"])
    assert q.render_record(rebuilt).encode("utf-8") == (QDIR / "SRC-007.json").read_bytes()
    assert sanitized == derivative(record)


def test_a_changed_derivative_is_refused(records):
    record = records["SRC-007"]
    assert err(q.verify_derivative, record, derivative(record) + b" ") == "DERIVATIVE_CHANGED"


@pytest.mark.parametrize("field", ["authoritative", "newly_authored"])
def test_a_derivative_cannot_claim_authority_of_its_own(raw, field):
    raw["derivative"]["authority"][field] = True
    assert err(q.record_from_dict, raw) == "DERIVATIVE_CLAIMS_AUTHORITY"


def test_the_record_refuses_every_inconsistency(raw):
    cases = {
        "DERIVATIVE_MALFORMED": lambda d: d["derivative"]["redactions"][0].update(marker="[gone]"),
        "QUARANTINE_WITHOUT_EVIDENCE": lambda d: d["reason"].update(findings=[]),
        "FINDING_NOT_REDACTED": lambda d: d["reason"]["findings"][0].update(start=0, end=5),
        "UNRESOLVED_WITHOUT_REDACTION": lambda d: d["derivative"]["unresolved"][0].update(
            original_start=0, original_end=5),
        "BAD_DISTRIBUTION_STATE": lambda d: d.update(distribution_state=q.ACTIVE_NORMAL),
        "DERIVATIVE_RECEIPT_MISMATCH": lambda d: d["derivative"]["authority"].update(
            represents="SRC-006"),
    }
    for code, mutate in cases.items():
        data = copy.deepcopy(raw)
        mutate(data)
        assert err(q.record_from_dict, data) == code, code
    data = copy.deepcopy(raw)
    data["derivative"]["length"] += 1
    assert err(q.record_from_dict, data) == "DERIVATIVE_MALFORMED"


def test_a_derivative_that_is_not_the_declared_redaction_is_infidelity():
    body = f"a\nC:\\k\\ops_{LABEL}_live.txt\nb\n".encode("utf-8")
    meta = {"source_sha256": q.sha256_hex(body)}
    record, sanitized = q.build_record("SRC-900", body, meta, "o.md", "d.md", evidence={})
    forged = sanitized[:-2] + b"c\n"
    record["derivative"]["sha256"] = q.sha256_hex(forged)
    parsed = q.record_from_dict(record)
    assert err(q.verify_derivative, parsed, forged, body) == "DERIVATIVE_INFIDELITY"
    assert q.verify_derivative(parsed, forged) == q.HASH_BOUND  # without the original, only the binding


# ------------------------------------------------ A4: authority


def test_redaction_neither_adds_nor_removes_authority(records, maps):
    record = records["SRC-007"]
    direct = receipt_intent_authority("SRC-007", maps)
    present = q.represented_authority(record, maps, derivative(record), original(record))
    absent = q.represented_authority(record, maps, derivative(record), None)
    # T-44 correction 003: the external host record SRC-007 names is not
    # resolvable here, so its declared acceptance resolves at the observed rung.
    assert direct == present["authority"] == absent["authority"] == USER_ACCEPTANCE_OBSERVED
    assert absent["fidelity"] == q.HASH_BOUND
    assert present["authority_source"] == "SEGMENT_MAP_OF_ORIGINAL_RECEIPT"
    for attribution in load_attributions(PROV / "ATTRIBUTIONS.json"):
        if attribution.receipt == "SRC-007":
            assert intent_authority(attribution, maps) == USER_ACCEPTANCE_OBSERVED


def test_the_derivative_is_not_a_receipt_and_cannot_be_cited_as_one(records, maps):
    citation = Attribution("B-X", records["SRC-007"].derivative.id, 0)
    assert err(intent_authority, citation, maps) == "NO_SEGMENT_MAP"


def test_redaction_cannot_launder_ambiguous_authorship():
    body = f"a\nC:\\k\\ops_{LABEL}_live.txt\nb\n".encode("utf-8")
    record_data, sanitized = q.build_record("SRC-900", body, {"source_sha256": q.sha256_hex(body)},
                                            "o.md", "d.md", evidence={})
    record = q.record_from_dict(record_data)
    ambiguous = {"SRC-900": SegmentMap("SRC-900", q.sha256_hex(body), len(body),
                                       (Segment("SRC-900", 0, len(body), AMBIGUOUS),))}
    assert err(q.represented_authority, record, ambiguous, sanitized) == "AMBIGUOUS_AUTHORSHIP"
    other = {"SRC-900": SegmentMap("SRC-900", "f" * 64, len(body),
                                   (Segment("SRC-900", 0, len(body), USER_ACCEPTANCE),))}
    assert err(q.represented_authority, record, other, sanitized) == "ORIGINAL_IDENTITY_MISMATCH"


def test_a_withheld_span_is_unresolved_and_everything_else_reads_exactly(records):
    record = records["SRC-007"]
    body = derivative(record)
    (r,) = record.derivative.redactions
    assert q.read_span(record, body, r.original_start, r.original_end) == (q.UNRESOLVED, None)
    assert q.read_span(record, body, r.original_start - 4, r.original_start + 1) == \
        (q.UNRESOLVED, None)
    assert q.read_span(record, body, 0, 7) == (q.RESOLVED, b"SAIMAIL")
    assert [u.clause for u in record.derivative.unresolved] == ["line 3"]

    # the section B-011..B-013 were derived from reads back exactly
    text = body.decode("utf-8")
    shift = (r.sanitized_end - r.sanitized_start) - (r.original_end - r.original_start)
    begin = len(text[:text.index("HUMAN_ATTENTION_BUDGET")].encode("utf-8")) - shift
    end = len(text[:text.index("Capture these as backlog")].encode("utf-8")) - shift
    status, section = q.read_span(record, body, begin, end)
    assert status == q.RESOLVED
    assert section.decode("utf-8").startswith("HUMAN_ATTENTION_BUDGET")
    assert "LEGACY / SUCCESSOR COMMUNICATION" in section.decode("utf-8")
    original_body = original(record)
    if original_body is not None:
        assert section == original_body[begin:end]


# ------------------------------------------------ CORE-004: read_span authenticates


def test_read_span_refuses_a_derivative_that_does_not_hash(records):
    record = records["SRC-007"]
    body = derivative(record)
    (r,) = record.derivative.redactions
    assert q.read_span(record, body, 0, 7) == (q.RESOLVED, b"SAIMAIL")
    # same-length tamper outside the requested span
    outside = bytearray(body)
    outside[len(body) - 1] ^= 0x01
    assert err(q.read_span, record, bytes(outside), 0, 7) == "DERIVATIVE_CHANGED"
    # same-length tamper inside the requested span
    inside = bytearray(body)
    inside[2] ^= 0x01
    assert err(q.read_span, record, bytes(inside), 0, 7) == "DERIVATIVE_CHANGED"
    # length tamper
    assert err(q.read_span, record, body + b" ", 0, 7) == "DERIVATIVE_CHANGED"
    # a withheld span remains unresolved, now decided on authenticated bytes only
    assert q.read_span(record, body, r.original_start, r.original_end) == (q.UNRESOLVED, None)


# ------------------------------------------------ A5: distribution


def test_a_normal_distribution_carries_identity_and_not_plaintext(records, maps, tmp_path):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    inventory = [p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file()]
    included, excluded = q.distributable(
        inventory, records, MEMORY_ROOT, manifest["evidence"]["non_exportable"],
        digest_of=lambda path: q.sha256_hex((ROOT / path).read_bytes()))
    record = records["SRC-007"]
    body = original(record)
    if body is not None:
        held = sorted(path for path in inventory
                      if (ROOT / path).stat().st_size == record.original_length
                      and q.sha256_hex((ROOT / path).read_bytes()) == record.original_sha256)
        assert held and all(excluded[path] == q.QUARANTINED_PLAINTEXT for path in held)
    for travels in (record.derivative.path, "provenance/quarantine/SRC-007.json",
                    ".saipen/intake/active/SRC-007.meta.json", "provenance/SRC-007.json",
                    "provenance/ATTRIBUTIONS.json"):
        assert travels in included, travels

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in included:
            archive.write(ROOT / path, path)
    with zipfile.ZipFile(buffer) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    assert record.original_path not in files
    if body is not None:
        assert q.plaintext_leaks(files, record, body) == ()

    # proven clean in memory; only now does anything reach the disk
    for name, data in files.items():
        if name.startswith(("provenance/", ".saipen/intake/")):
            target = tmp_path / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    unpacked_maps = load_maps(tmp_path / "provenance")
    unpacked = q.load_records(tmp_path / "provenance" / q.QUARANTINE_DIR)["SRC-007"]
    assert not (tmp_path / unpacked.original_path).exists()
    result = q.represented_authority(unpacked, unpacked_maps,
                                     (tmp_path / unpacked.derivative.path).read_bytes())
    assert result["authority"] == receipt_intent_authority("SRC-007", maps) == (
        USER_ACCEPTANCE_OBSERVED)
    assert result["fidelity"] == q.HASH_BOUND
    local = {a.requirement: intent_authority(a, maps)
             for a in load_attributions(PROV / "ATTRIBUTIONS.json") if a.receipt == "SRC-007"}
    shipped = {a.requirement: intent_authority(a, unpacked_maps)
               for a in load_attributions(tmp_path / "provenance" / "ATTRIBUTIONS.json")
               if a.receipt == "SRC-007"}
    assert shipped == local and set(local) == {"B-011", "B-012", "B-013"}


def test_non_exportable_and_build_paths_stay_out(records):
    inventory = [".saipen/recovery/ops/x.json", ".saipen/locks/core.lock",
                 ".saipen/LOCAL_STATE.json", ".saipen/LOG.md", "saimail/__pycache__/a.pyc",
                 "saimail.egg-info/PKG-INFO", ".git/HEAD", "README.md",
                 records["SRC-007"].original_path]
    included, excluded = q.distributable(inventory, records, MEMORY_ROOT,
                                         ["locks/", "recovery/", "LOCAL_STATE.json"])
    assert included == (".saipen/LOG.md", "README.md")
    assert excluded == {
        ".saipen/recovery/ops/x.json": q.NON_EXPORTABLE,
        ".saipen/locks/core.lock": q.NON_EXPORTABLE,
        ".saipen/LOCAL_STATE.json": q.NON_EXPORTABLE,
        "saimail/__pycache__/a.pyc": q.BUILD_CACHE,
        "saimail.egg-info/PKG-INFO": q.BUILD_CACHE,
        ".git/HEAD": q.VCS_INTERNAL,
        records["SRC-007"].original_path: q.QUARANTINED_PLAINTEXT,
    }


def test_a_quarantined_body_moved_by_closure_is_still_excluded(records):
    record = records["SRC-007"]
    archived = ".saipen/archive/source/SRC-007.md"
    digests = {archived: record.original_sha256, "README.md": "0" * 64}
    included, excluded = q.distributable([archived, "README.md"], records, MEMORY_ROOT,
                                         ["locks/", "recovery/", "LOCAL_STATE.json"],
                                         digest_of=digests.get)
    assert included == ("README.md",)
    assert excluded == {archived: q.QUARANTINED_PLAINTEXT}
    without_identity, _ = q.distributable([archived], records, MEMORY_ROOT, [])
    assert without_identity == (archived,), "by path alone, a moved body would ship"


def test_the_saipen_export_status_is_stated_not_assumed(records):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    stated = records["SRC-007"].evidence["saipen_export"]["status"]
    assert stated == q.saipen_export_status(manifest, records, MEMORY_ROOT)
    assert stated == q.NOT_HONOURED
    proposed = {**manifest, "quarantine": {"excluded_bodies": ["intake/active/SRC-007.md"]}}
    assert q.saipen_export_status(proposed, records, MEMORY_ROOT) == q.HONOURED


def test_the_protocol_change_proposal_states_all_four_parts():
    text = PROPOSAL.read_text(encoding="utf-8")
    for heading in ("PROTOCOL_CHANGE_PROPOSAL", "EVIDENCE", "REQUIRED_CORE_CHANGE",
                    "SAFE_MIGRATION_PLAN"):
        assert f"## {heading}" in text, heading


# ------------------------------------------------ the writer


def test_the_writer_never_touches_the_receipt_and_never_regenerates_evidence(tmp_path, capsys):
    intake = tmp_path / MEMORY_ROOT / "intake" / "active"
    intake.mkdir(parents=True)
    body = f"note\nC:\\keys\\ops_{LABEL}_live.txt\n".encode("utf-8")
    (intake / "SRC-900.md").write_bytes(body)
    (intake / "SRC-900.meta.json").write_text(json.dumps(
        {"receipt_id": "SRC-900", "source_sha256": q.sha256_hex(body), "status": "ACTIVE",
         "sensitive": False, "redaction": {"applied": False}}), encoding="utf-8")
    args = ["SRC-900", "--source-receipt", "SRC-901", "--ticket", "T-1", "--decision", "D-023",
            "--root", str(tmp_path)]
    assert tool.main(args + ["--statement", "fixture"]) == 0
    out = capsys.readouterr().out
    assert f"ops_{LABEL}_live" not in out
    assert (intake / "SRC-900.md").read_bytes() == body
    written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")
                     if p.is_file() and "intake" not in p.parts)
    assert written == ["provenance/quarantine/SRC-900.json",
                       "provenance/quarantine/SRC-900.sanitized.md"]
    assert tool.main(args + ["--statement", "fixture"]) == 0  # identical evidence is idempotent
    capsys.readouterr()
    assert tool.main(args + ["--statement", "a different statement"]) == 1
    assert "RECORD_EXISTS_DIFFERENT" in capsys.readouterr().out

    clean = b"nothing sensitive in here\n"
    (intake / "SRC-902.md").write_bytes(clean)
    (intake / "SRC-902.meta.json").write_text(json.dumps(
        {"source_sha256": q.sha256_hex(clean)}), encoding="utf-8")
    assert tool.main(["SRC-902", "--source-receipt", "SRC-901", "--ticket", "T-1", "--decision",
                      "D-023", "--statement", "fixture", "--root", str(tmp_path)]) == 1
    assert "NOTHING_TO_QUARANTINE" in capsys.readouterr().out


# ------------------------------------------------ W2-004: the quarantine commit boundary


def _writable_root(tmp_path):
    intake = tmp_path / MEMORY_ROOT / "intake" / "active"
    intake.mkdir(parents=True, exist_ok=True)
    body = ("note" + chr(10) + "C:" + chr(92) + "keys" + chr(92)
            + f"ops_{LABEL}_commit.txt" + chr(10)).encode("utf-8")
    (intake / "SRC-910.md").write_bytes(body)
    (intake / "SRC-910.meta.json").write_text(json.dumps(
        {"receipt_id": "SRC-910", "source_sha256": q.sha256_hex(body), "status": "ACTIVE",
         "sensitive": False, "redaction": {"applied": False}}), encoding="utf-8")
    return tmp_path, body


def _quarantine_args(root):
    return ["SRC-910", "--source-receipt", "SRC-901", "--ticket", "T-1", "--decision", "D-023",
            "--statement", "fixture", "--root", str(root)]


def test_a_failure_during_the_derivative_write_leaves_no_committed_record(tmp_path, monkeypatch,
                                                                         capsys):
    """W2-004: the record is the commit marker, so a half-commit is invisible to --check."""
    root, _ = _writable_root(tmp_path)
    real = tool.publish_immutable
    state = {"failed": False}

    def flaky(path, data, *, conflict_code):
        if path.name.endswith(".sanitized.md") and not state["failed"]:
            state["failed"] = True
            raise OSError("disk went away")
        return real(path, data, conflict_code=conflict_code)

    monkeypatch.setattr(tool, "publish_immutable", flaky)
    assert tool.main(_quarantine_args(root)) == 1
    assert "QUARANTINE_WRITE_FAILED" in capsys.readouterr().out
    record = root / "provenance" / "quarantine" / "SRC-910.json"
    assert not record.exists(), "no record without its derivative"
    monkeypatch.setattr(tool, "publish_immutable", real)
    assert tool.main(_quarantine_args(root)) == 0, "the retry converges"


def test_a_failure_before_the_record_write_leaves_only_an_adoptable_derivative(
        tmp_path, monkeypatch):
    """W2-004: an unreferenced identical derivative is safe; a retry adopts it."""
    root, _ = _writable_root(tmp_path)
    real = tool.publish_immutable
    failed = {"no": False}

    def flaky(path, data, *, conflict_code):
        if path.name == "SRC-910.json" and not failed["no"]:
            failed["no"] = True
            raise OSError("power loss")
        return real(path, data, conflict_code=conflict_code)

    monkeypatch.setattr(tool, "publish_immutable", flaky)
    assert tool.main(_quarantine_args(root)) == 1
    derivative = root / "provenance" / "quarantine" / "SRC-910.sanitized.md"
    record = root / "provenance" / "quarantine" / "SRC-910.json"
    assert derivative.is_file() and not record.exists()
    assert tool.main(["--check", "--root", str(root)]) == 0, "no half-committed record is visible"
    monkeypatch.setattr(tool, "publish_immutable", real)
    assert tool.main(_quarantine_args(root)) == 0, "the identical derivative is adopted"


def test_a_conflicting_orphan_derivative_refuses_instead_of_being_replaced(tmp_path, monkeypatch,
                                                                          capsys):
    root, _ = _writable_root(tmp_path)
    orphan = root / "provenance" / "quarantine" / "SRC-910.sanitized.md"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"someone else's bytes\n")
    assert tool.main(_quarantine_args(root)) == 1
    assert "DERIVATIVE_EXISTS_DIFFERENT" in capsys.readouterr().out
    assert orphan.read_bytes() == b"someone else's bytes\n"
    assert not (root / "provenance" / "quarantine" / "SRC-910.json").exists()


# ------------------------------------------------ PERF: audit wave-3 controls


def _dense_body(lines):
    """One labelled credential filename per line: a finding-dense receipt."""
    parts = []
    for index in range(lines):
        parts.append("note " + str(index) + ": C:" + chr(92) + "keys" + chr(92)
                     + f"ops_{LABEL}_{index:05d}x9.txt")
    return ("\n".join(parts) + "\n").encode("utf-8")


def test_a_dense_body_scans_in_linear_time():
    """PERF-003: doubling a finding-dense body must not quadruple the scan."""
    import time
    small = time.perf_counter()
    first = q.scan(_dense_body(2000))
    small = time.perf_counter() - small
    large = time.perf_counter()
    second = q.scan(_dense_body(4000))
    large = time.perf_counter() - large
    assert len(second) > len(first) > 1000, "the bodies are finding-dense"
    # linear growth is ~2x; the pre-repair prefix re-encode made it ~4x and
    # worse. The bound is loose on purpose: catch the class, not the machine.
    assert large < small * 3.0 + 0.05, f"small={small:.3f}s large={large:.3f}s"


def test_multibyte_offsets_stay_exact_after_the_linear_scan():
    """PERF-003 guardrail: character indices were never byte offsets."""
    body = ("märkus teine rida\nC:" + chr(92) + "keys" + chr(92) + "ops_"
            + LABEL + "_üõš.txt\nkolmas rida\n").encode("utf-8")
    findings = q.scan(body)
    assert findings
    text = body.decode("utf-8")
    for finding in findings:
        decoded = text.encode("utf-8")[finding.start:finding.end].decode("utf-8")
        assert decoded in text
        assert finding.start == len(text[:text.index(decoded)].encode("utf-8"))


def test_the_leak_basis_matches_the_exhaustive_expansion():
    """PERF-004: same leak decisions, bounded piece count."""
    import random
    rng = random.Random(20260918)
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    for _ in range(25):
        run_count = rng.randint(1, 7)
        component = ".".join([f"{LABEL}_{rng.randint(0, 99)}"] +
                             ["".join(rng.choice(alphabet)
                                      for _ in range(rng.randint(1, 9)))
                              for _ in range(run_count)])
        body = ("prefix\nvalue: C:" + chr(92) + "k" + chr(92) + component
                + ".txt\nsuffix\n").encode("utf-8")
        record = q.build_record("SRC-P4", body,
                                {"source_sha256": q.sha256_hex(body),
                                 "redaction": {"applied": False}},
                                original_path="x/SRC-P4.md",
                                derivative_path="x/SRC-P4.sanitized.md",
                                evidence={"reason": {}, "original": {}})[0]
        parsed = q.record_from_dict(record)
        exhaustive = q.withheld_fragments(parsed, body)
        basis = q.leak_basis(parsed, body)
        assert set(basis) <= set(exhaustive), "the basis searches real pieces only"
        # every exhaustive piece is either in the basis or contains a basis piece
        basis_list = list(basis)
        for piece in exhaustive:
            assert piece in basis_set_of(basis_list) or any(
                sub in piece for sub in basis_list), piece
        # leak decisions agree on random candidate files
        candidates = {}
        for index in range(12):
            take = rng.randrange(0, len(component) + 1)
            cut = rng.randrange(0, len(component) - take + 1) if take else 0
            candidates[f"f{index}"] = (f"noise {component[cut:cut + take]} noise"
                                       ).encode("utf-8")
        leaked_exhaustive = {path for path, data in candidates.items()
                             if any(p in data.lower() for p in exhaustive)}
        leaked_basis = {path for path, data in candidates.items()
                        if any(p in data.lower() for p in basis)}
        assert leaked_exhaustive == leaked_basis


def basis_set_of(basis_list):
    return set(basis_list)


def test_a_many_run_component_stays_bounded():
    """PERF-004: 500 runs once materialized ~124,750 windows; the basis is O(R)."""
    runs = ".".join(f"run{index:03d}x" for index in range(500))
    body = f"a\nsecret: {runs}\nb\n".encode("utf-8")
    record = q.build_record("SRC-P4B", body,
                            {"source_sha256": q.sha256_hex(body),
                             "redaction": {"applied": False}},
                            original_path="x/SRC-P4B.md",
                            derivative_path="x/SRC-P4B.sanitized.md",
                            evidence={"reason": {}, "original": {}})[0]
    parsed = q.record_from_dict(record)
    basis = q.leak_basis(parsed, body)
    assert len(basis) < 5 * 500, len(basis)


def test_one_receipt_analysis_per_quarantine_build(tmp_path, monkeypatch):
    """PERF-006: the dominant body analysis runs once, output stays identical."""
    intake = tmp_path / MEMORY_ROOT / "intake" / "active"
    intake.mkdir(parents=True, exist_ok=True)
    body = ("note\nC:" + chr(92) + "keys" + chr(92)
            + f"ops_{LABEL}_perf6.txt\n").encode("utf-8")
    (intake / "SRC-920.md").write_bytes(body)
    (intake / "SRC-920.meta.json").write_text(json.dumps(
        {"receipt_id": "SRC-920", "source_sha256": q.sha256_hex(body), "status": "ACTIVE",
         "sensitive": False, "redaction": {"applied": False}}), encoding="utf-8")
    calls = {"n": 0}
    real = q.build_record

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(q, "build_record", counting)
    monkeypatch.setattr(tool.q, "build_record", counting)
    record, _ = tool.build(tmp_path, "SRC-920", "SRC-901", "T-1", "D-023", "fixture")
    assert calls["n"] == 1, "one quarantine performs one receipt analysis"
    assert record["saipen_export"]["status"] in (q.HONOURED, q.NOT_HONOURED)


# ------------------------------------------------ T-42/C2: publication is no-overwrite


def test_two_concurrent_quarantine_writers_produce_one_committed_record(tmp_path, capsys):
    """The race the immutable publication primitive exists for: one winner, named loser."""
    import threading

    root, _ = _writable_root(tmp_path)
    barrier = threading.Barrier(2)
    outcome = {}

    def writer(statement):
        args = ["SRC-910", "--source-receipt", "SRC-901", "--ticket", "T-1",
                "--decision", "D-023", "--statement", statement, "--root", str(root)]
        barrier.wait()
        outcome[statement] = tool.main(args)

    threads = [threading.Thread(target=writer, args=(statement,))
               for statement in ("writer A", "writer B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    capsys.readouterr()  # both writers printed; only the aggregate outcome matters
    winners = [statement for statement, code in outcome.items() if code == 0]
    assert len(winners) == 1, outcome
    record = root / "provenance" / "quarantine" / "SRC-910.json"
    committed = json.loads(record.read_text(encoding="utf-8"))
    assert committed["reason"]["operator_statement"]["says"] == winners[0], \
        "the record on disk is the winner's, byte for byte"
    rerun = tool.main(["SRC-910", "--source-receipt", "SRC-901", "--ticket", "T-1",
                       "--decision", "D-023", "--statement", winners[0],
                       "--root", str(root)])
    assert rerun == 0, "the winner's own bytes are still adopted idempotently"
