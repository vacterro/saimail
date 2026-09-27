"""B-018 pilot capture (Target C): exact registered extraction, pins, refusals.

The capture adapter reads exactly the registered sources and extracts exactly
the registered selectors; these tests re-derive every expected byte with an
independent implementation, prove no fuzzy or neighboring selection exists, and
prove the source pins fail closed.
"""

import hashlib
import json
from pathlib import Path

import pytest

from lab import project_corpus_pilot as pcp
from sailang.errors import SailangError
from saimail import project_corpus as pc

ROOT = Path(__file__).resolve().parent.parent
REAL_REGISTRATION = ROOT / "lab" / pcp.REGISTRATION_FILE

D047_HEADING = "## D-047 \u2014 "
D048_HEADING = "## D-048 \u2014 "
D049_HEADING = "## D-049 \u2014 "
D050_HEADING = "## D-050 \u2014 "
LOG_PATH = ".saipen/LOG.md"
DECISIONS_PATH = "spec/DECISIONS.md"
REPORT_PATH = "lab/out/ALLY_GENERATION_REPORT_20260919T201826Z_2a73d98de110453a.md"


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-8")


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def expected_section(path: Path, heading: str, boundary: str = "## D-") -> str:
    """Independent exact-section slice: exact heading to the next boundary."""
    text = read_text(path)
    assert text.count(heading) == 1, f"{heading!r} is not a unique heading"
    start = text.index(heading)
    end = text.index(boundary, start + len(heading))
    return text[start:end]


def expected_log_record(path: Path, marker: str) -> str:
    """Independent exact-line slice: the line carrying the token plus terminator."""
    text = read_text(path)
    assert text.count(marker) == 1, f"{marker} is not unique"
    index = text.index(marker)
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    return text[start:] if end == -1 else text[start:end + 1]


def copy_registered_sources(target: Path) -> Path:
    for spec in pcp.selection_artifacts():
        destination = target / spec["source"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / spec["source"]).read_bytes())
    return target


@pytest.fixture(scope="module")
def real_result():
    registration = pcp.load_registration(REAL_REGISTRATION)
    return pcp.build_pilot_corpus(registration, ROOT)


def content_for(result, label):
    evidence_ref = result.evidence_ref_for(label)
    return result.built.reflection_corpus.item_for(evidence_ref).content


# ------------------------------------------------------- exact capture (8..15)


def test_d047_section_captured_exactly(real_result):
    assert content_for(real_result, "A1") == expected_section(
        ROOT / DECISIONS_PATH, D047_HEADING)


def test_e715_record_captured_exactly(real_result):
    assert content_for(real_result, "A2") == expected_log_record(
        ROOT / LOG_PATH, "[E-715]")


def test_d048_section_captured_exactly(real_result):
    assert content_for(real_result, "A3") == expected_section(
        ROOT / DECISIONS_PATH, D048_HEADING)


def test_e726_record_captured_exactly(real_result):
    assert content_for(real_result, "A4") == expected_log_record(
        ROOT / LOG_PATH, "[E-726]")


def test_t63_report_captured_exactly(real_result):
    assert content_for(real_result, "A5") == read_text(ROOT / REPORT_PATH)


def test_d049_section_captured_exactly(real_result):
    assert content_for(real_result, "A6") == expected_section(
        ROOT / DECISIONS_PATH, D049_HEADING)


def test_d050_section_captured_exactly(real_result):
    assert content_for(real_result, "A7") == expected_section(
        ROOT / DECISIONS_PATH, D050_HEADING)


def test_e779_record_captured_exactly(real_result):
    assert content_for(real_result, "A8") == expected_log_record(
        ROOT / LOG_PATH, "[E-779]")


def test_registered_extraction_pins_match_rebuilt_content(real_result):
    for entry in real_result.registration.artifacts:
        assert sha256_text(content_for(real_result, entry.label)) == (
            entry.extracted_content_sha256)


def test_no_neighboring_log_record_is_captured(real_result):
    for label, neighbour in (("A2", "[E-716]"), ("A4", "[E-727]"),
                             ("A8", "[E-780]")):
        content = content_for(real_result, label)
        assert neighbour not in content
        assert content.endswith("\n")
        assert content.count("\n") == 1


# --------------------------------------------- no rewriting, no trimming (B4)


def test_no_newline_rewriting_on_a_crlf_fixture(tmp_path):
    root = copy_registered_sources(tmp_path / "project")
    log = root / LOG_PATH
    log.write_bytes(log.read_bytes().replace(b"\n", b"\r\n"))
    report = root / REPORT_PATH
    report.write_bytes(report.read_bytes().replace(b"\n", b"\r\n"))
    registration = pcp.freeze_registration(tmp_path / pcp.REGISTRATION_FILE, root)
    result = pcp.build_pilot_corpus(registration, root)
    for label in ("A2", "A4", "A8"):
        content = content_for(result, label)
        assert "\r\n" in content
    assert content_for(result, "A2") == expected_log_record(log, "[E-715]")
    assert content_for(result, "A5") == report.read_bytes().decode("utf-8")


def test_no_strip_of_edge_whitespace(tmp_path):
    root = copy_registered_sources(tmp_path / "project")
    decisions = root / DECISIONS_PATH
    text = read_text(decisions)
    marker = "## D-048 \u2014 "
    index = text.index(marker)
    insert = text.index("\n", index) + 1
    whisper = "   \n"
    decisions.write_bytes((text[:insert] + whisper + text[insert:]).encode("utf-8"))
    registration = pcp.freeze_registration(tmp_path / pcp.REGISTRATION_FILE, root)
    result = pcp.build_pilot_corpus(registration, root)
    content = content_for(result, "A3")
    assert whisper in content
    assert content == expected_section(decisions, marker)


# ------------------------------------------------ selector refusals (16..17)


def freeze_with(monkeypatch, tmp_path, spec, *sources):
    monkeypatch.setattr(pcp, "selection_artifacts",
                        lambda seed_path=None, spec=spec: (spec,))
    monkeypatch.setattr(pcp, "REGISTERED_EVENTS", ())
    root = tmp_path / "project"
    for relative, content in sources:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def section_spec(prefix):
    return {
        "label": "A1",
        "source_kind": pc.SPEC_DECISION,
        "source_ref": "decision:D-001",
        "observed_at": "2026-09-19T19:32:00Z",
        "source": DECISIONS_PATH,
        "selector": {"kind": pcp.MARKDOWN_SECTION, "heading_prefix": prefix,
                     "boundary_prefix": "## D-"},
    }


def test_fuzzy_heading_variants_are_missing_not_matched(monkeypatch, tmp_path):
    body = "## D-047 \u2014 exact\ntext\n\n## D-048 \u2014 next\ntext\n"
    for index, variant in enumerate(("## D-47 \u2014 ", "## D-047x \u2014 ")):
        area = tmp_path / f"miss-{index}"
        root = freeze_with(monkeypatch, area, section_spec(variant),
                           (DECISIONS_PATH, body))
        assert error(pcp.freeze_registration,
                     area / pcp.REGISTRATION_FILE, root).code == (
            pcp.PROJECT_PILOT_SELECTOR_MISSING)
    for index, variant in enumerate(("## D047", "## D-047 ", "## generation decision")):
        area = tmp_path / f"invalid-{index}"
        root = freeze_with(monkeypatch, area, section_spec(variant),
                           (DECISIONS_PATH, body))
        assert error(pcp.freeze_registration,
                     area / pcp.REGISTRATION_FILE, root).code == (
            pcp.PROJECT_PILOT_REGISTRATION_INVALID)


def test_duplicate_heading_refused(monkeypatch, tmp_path):
    body = "## D-047 \u2014 first\ntext\n## D-047 \u2014 second\nmore\n"
    root = freeze_with(monkeypatch, tmp_path, section_spec("## D-047 \u2014 "),
                       (DECISIONS_PATH, body))
    assert error(pcp.freeze_registration,
                 tmp_path / pcp.REGISTRATION_FILE, root).code == (
        pcp.PROJECT_PILOT_SELECTOR_DUPLICATE)


def test_zero_length_section_refused(monkeypatch, tmp_path):
    body = "## D-001 \u2014 empty\n## D-002 \u2014 next\ntext\n"
    root = freeze_with(monkeypatch, tmp_path, section_spec("## D-001 \u2014 "),
                       (DECISIONS_PATH, body))
    assert error(pcp.freeze_registration,
                 tmp_path / pcp.REGISTRATION_FILE, root).code == (
        pcp.PROJECT_PILOT_SELECTOR_EMPTY)


def test_log_selector_requires_exactly_one_exact_token(monkeypatch, tmp_path):
    spec = {
        "label": "A1",
        "source_kind": pc.TEST_RESULT,
        "source_ref": "saipen-log:E-715",
        "observed_at": "2026-09-19T19:32:00Z",
        "source": LOG_PATH,
        "selector": {"kind": pcp.LOG_RECORD, "marker": "[E-715]"},
    }
    missing = freeze_with(monkeypatch, tmp_path, spec, (LOG_PATH, "- no marker\n"))
    assert error(pcp.freeze_registration,
                 tmp_path / pcp.REGISTRATION_FILE, missing).code == (
        pcp.PROJECT_PILOT_SELECTOR_MISSING)
    duplicate = freeze_with(
        monkeypatch, tmp_path / "second", spec,
        (LOG_PATH, "- [E-715] one\n- [E-715] two\n"))
    assert error(pcp.freeze_registration,
                 tmp_path / "second" / pcp.REGISTRATION_FILE, duplicate).code == (
        pcp.PROJECT_PILOT_SELECTOR_DUPLICATE)


def test_selector_pin_mismatch_fails_closed(monkeypatch, tmp_path):
    root = copy_registered_sources(tmp_path / "project")
    registration = pcp.freeze_registration(tmp_path / pcp.REGISTRATION_FILE, root)
    document = json.loads(registration.canonical_bytes.decode("utf-8"))
    document["artifacts"][3]["selector"] = {"kind": pcp.LOG_RECORD,
                                            "marker": "[E-727]"}
    (tmp_path / pcp.REGISTRATION_FILE).write_bytes(
        pcp.canonical_registration_bytes(document))
    loaded = pcp.load_registration(tmp_path / pcp.REGISTRATION_FILE)
    assert error(pcp.build_pilot_corpus, loaded, root).code == (
        pcp.PROJECT_PILOT_SOURCE_CHANGED)


# ------------------------------------ exactly registered reads, no ninth (16)


def test_capture_reads_only_registered_paths(monkeypatch, tmp_path):
    root = copy_registered_sources(tmp_path / "project")
    decoy = root / "spec" / "EXTRA_DECISIONS_BACKUP.md"
    decoy.parent.mkdir(parents=True, exist_ok=True)
    decoy.write_text("## D-047 \u2014 decoy\n[E-715]\n", encoding="utf-8")
    registration = pcp.freeze_registration(tmp_path / pcp.REGISTRATION_FILE, root)
    reads = []
    original = pcp._read_source_bytes

    def spy(path):
        reads.append(str(path))
        return original(path)

    monkeypatch.setattr(pcp, "_read_source_bytes", spy)
    result = pcp.build_pilot_corpus(registration, root)
    assert result.built.artifact_count == 8
    assert set(result.capture.read_paths) == set(registration.source_file_sha256)
    registered = {str(root / source) for source in registration.source_file_sha256}
    assert set(reads) <= registered
    assert str(decoy) not in reads
    # 3 hash passes over distinct sources plus 8 exact selector reads
    assert len(reads) == 2 * len(registration.source_file_sha256) + 8
