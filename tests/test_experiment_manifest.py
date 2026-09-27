"""FG-02 / T-79: one manifest contract, three separated verification authorities.

Every test here is offline: deterministic fixtures, temp copies, no provider and
no network. The separation matrix is the point -- a historical fixture hash, a
current-checkout match and a live admission must never answer for one another.
"""

import copy
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from lab import experiment_manifest as em
from sailang.errors import SailangError

ROOT = Path(__file__).resolve().parent.parent
T71_MANIFEST_PATH = ROOT / "lab" / "history" / "t71_manifest.json"
T71_REGISTRATION_SHA = "825c0853dc1a5cd73939bbf91201fb1e4f8a8b40a62e0d69a87d0fcd6be7dc16"
QUARANTINE_FIXTURE = ROOT / "tests" / "fixtures" / "t71" / "quarantine.py.txt"
LEGACY_FIXTURE = ROOT / "tests" / "fixtures" / "t71" / "legacy.py.txt"
QUARANTINE_FIXTURE_SHA = "0960dd992839ca149a81be3bdf80746fb6cd7397023ef2998d429cf03428b985"
LEGACY_FIXTURE_SHA = "6e519e624ad6e33a5509337f43d7e8d7f742e2af23aef9a8257b7b568821fe2a"

MARKDOWN_SOURCE = "## Registered\nregistered body\n## Other\ntail\n"
MARKDOWN_SELECTED = "## Registered\nregistered body\n"


class Network:
    """A tripwire: any use is a failure, so every assertion is exactly zero."""

    def __init__(self):
        self.calls = 0

    def send(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("manifest verification attempted a network call")


def sha(data) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def write(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return path


def whole_file_input(input_id, rel, data, *, sensitivity="PUBLIC_ARCHIVABLE",
                     required=True, fixture=None, container=None):
    record = {
        "INPUT_ID": input_id,
        "SENSITIVITY": sensitivity,
        "SOURCE_KIND": "TEXT_FILE",
        "EXTRACTION_KIND": "WHOLE_FILE",
        "EXTRACTOR_VERSION": "WHOLE-FILE-1",
        "EXTRACTED_SHA256": sha(data),
        "REQUIRED_FOR_LIVE": required,
        "SOURCE_PATH": rel,
    }
    if fixture is not None:
        record["ARCHIVED_FIXTURE"] = fixture
    if container is not None:
        record["CONTAINER_SHA256_AT_REGISTRATION"] = container
    return record


def manifest(inputs, *, authority="HISTORICAL_ONLY", implementation=None, **overrides):
    document = {
        "manifest_version": em.MANIFEST_VERSION,
        "experiment_id": "TEST-EXPERIMENT",
        "authority": authority,
        "inputs": inputs,
        "implementation": list(implementation or []),
    }
    document.update(overrides)
    return document


def t71_manifest() -> dict:
    return em.load(T71_MANIFEST_PATH)


@pytest.fixture
def t71_tree(tmp_path):
    """A temp checkout that can be mutated without touching the repository."""
    root = tmp_path / "checkout"
    for rel in ("tests/fixtures/t71/quarantine.py.txt", "tests/fixtures/t71/legacy.py.txt",
                "lab/ally_generation_live.py", "lab/project_corpus_reachability.py"):
        write(root / rel, (ROOT / rel).read_bytes())
    return root


# ---------------------------------------------------------------------------
# MANIFEST
# ---------------------------------------------------------------------------


def test_canonical_manifest_identity_is_stable_and_not_self_referential(tmp_path):
    write(tmp_path / "source.txt", "payload")
    document = manifest([whole_file_input("MAIN", "source.txt", b"payload")])
    identity = em.manifest_identity(document)
    assert len(identity) == 64
    reordered = {key: document[key] for key in reversed(list(document))}
    assert em.manifest_identity(reordered) == identity
    reparsed = json.loads(json.dumps(document, indent=2))
    assert em.manifest_identity(reparsed) == identity
    canonical = em.canonical_bytes(document)
    assert canonical == json.dumps(json.loads(canonical), sort_keys=True,
                                   separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    assert not canonical.endswith(b"\n")
    assert identity.encode() not in canonical


def test_unknown_manifest_version_refused():
    document = manifest([], manifest_version="EXPERIMENT-MANIFEST-2")
    with pytest.raises(SailangError, match="MANIFEST_UNKNOWN_VERSION"):
        em.manifest_identity(document)


def test_unknown_extraction_kind_refused():
    record = whole_file_input("MAIN", "source.txt", b"payload")
    record["EXTRACTION_KIND"] = "REGEX_QUERY"
    with pytest.raises(SailangError, match="MANIFEST_UNKNOWN_EXTRACTION_KIND"):
        em.manifest_identity(manifest([record]))


def test_unknown_extractor_version_refused():
    record = whole_file_input("MAIN", "source.txt", b"payload")
    record["EXTRACTOR_VERSION"] = "WHOLE-FILE-2"
    with pytest.raises(SailangError, match="MANIFEST_UNKNOWN_EXTRACTOR_VERSION"):
        em.manifest_identity(manifest([record]))
    record["EXTRACTION_KIND"] = "MARKDOWN_SECTION"
    record["SELECTOR"] = "md-heading:## X"
    with pytest.raises(SailangError, match="MANIFEST_UNKNOWN_EXTRACTOR_VERSION"):
        em.manifest_identity(manifest([record]))


@pytest.mark.parametrize("where", ["top", "input", "implementation", "self_digest"])
def test_unknown_fields_refused(where):
    record = whole_file_input("MAIN", "source.txt", b"payload")
    component = {"PATH": "runner.py", "SHA256": "0" * 64, "ROLE": "RUNNER"}
    document = manifest([record], implementation=[component])
    if where == "top":
        document["notes"] = "hello"
    elif where == "input":
        record["EXTRA"] = 1
    elif where == "implementation":
        component["EXTRA"] = 1
    else:
        document["manifest_sha256"] = "0" * 64
    with pytest.raises(SailangError, match="MANIFEST_UNKNOWN_FIELD"):
        em.manifest_identity(document)


# ---------------------------------------------------------------------------
# PUBLIC INPUTS
# ---------------------------------------------------------------------------


def test_archived_public_fixtures_verify(tmp_path):
    document = t71_manifest()
    result = em.verify_historical(document, fixture_root=ROOT)
    assert result["verdict"] == em.HISTORICAL_VERIFIED
    assert [row["status"] for row in result["inputs"]] == [em.HISTORICAL_VERIFIED] * 2
    assert result["current_source_read"] is False


def test_fixture_substitution_refused(tmp_path):
    root = tmp_path / "evidence"
    for rel in ("tests/fixtures/t71/quarantine.py.txt", "tests/fixtures/t71/legacy.py.txt"):
        write(root / rel, (ROOT / rel).read_bytes())
    write(root / "tests/fixtures/t71/quarantine.py.txt",
          QUARANTINE_FIXTURE.read_bytes() + b"\n")
    result = em.verify_historical(t71_manifest(), fixture_root=root)
    assert result["verdict"] == em.HISTORICAL_MISMATCH
    statuses = {row["INPUT_ID"]: (row["status"], row.get("reason")) for row in result["inputs"]}
    assert statuses["T71-QUARANTINE-SOURCE"] == (em.HISTORICAL_MISMATCH,
                                                 "FIXTURE_SUBSTITUTION")
    assert statuses["T71-LEGACY-SOURCE"] == (em.HISTORICAL_VERIFIED, None)


def test_historical_verification_ignores_current_code_drift(tmp_path):
    root = tmp_path / "evidence"
    for rel in ("tests/fixtures/t71/quarantine.py.txt", "tests/fixtures/t71/legacy.py.txt"):
        write(root / rel, (ROOT / rel).read_bytes())
    write(tmp_path / "checkout/saimail/quarantine.py", "current code moved on\n")
    write(tmp_path / "checkout/saimail/legacy.py", "current code moved on too\n")
    assert sha(Path(tmp_path / "checkout/saimail/quarantine.py").read_bytes()) != QUARANTINE_FIXTURE_SHA
    result = em.verify_historical(t71_manifest(), fixture_root=root)
    assert result["verdict"] == em.HISTORICAL_VERIFIED


def test_unrelated_container_append_preserves_selected_identity(tmp_path):
    source = write(tmp_path / "doc.md", MARKDOWN_SOURCE)
    record = {
        "INPUT_ID": "SECTION",
        "SENSITIVITY": "PUBLIC_ARCHIVABLE",
        "SOURCE_KIND": "MARKDOWN_DOCUMENT",
        "EXTRACTION_KIND": "MARKDOWN_SECTION",
        "EXTRACTOR_VERSION": "MARKDOWN-SECTION-1",
        "EXTRACTED_SHA256": sha(MARKDOWN_SELECTED),
        "REQUIRED_FOR_LIVE": True,
        "SOURCE_PATH": "doc.md",
        "SELECTOR": "md-heading:## Registered",
        "ARCHIVED_FIXTURE": "archive/section.md",
        "CONTAINER_SHA256_AT_REGISTRATION": sha(MARKDOWN_SOURCE),
    }
    document = manifest([record])
    write(tmp_path / "archive/section.md", MARKDOWN_SELECTED)
    assert em.verify_current(document, root=tmp_path)["verdict"] == em.CURRENT_MATCH
    write(source, MARKDOWN_SOURCE + "## Appended\nunrelated bytes\n")
    current = em.verify_current(document, root=tmp_path)
    assert current["verdict"] == em.CURRENT_MATCH
    assert current["inputs"][0]["status"] == em.CURRENT_MATCH
    assert em.verify_historical(document, fixture_root=tmp_path)["verdict"] == \
        em.HISTORICAL_VERIFIED


def test_registered_section_mutation_detected(tmp_path):
    source = write(tmp_path / "doc.md", MARKDOWN_SOURCE)
    record = {
        "INPUT_ID": "SECTION",
        "SENSITIVITY": "PUBLIC_ARCHIVABLE",
        "SOURCE_KIND": "MARKDOWN_DOCUMENT",
        "EXTRACTION_KIND": "MARKDOWN_SECTION",
        "EXTRACTOR_VERSION": "MARKDOWN-SECTION-1",
        "EXTRACTED_SHA256": sha(MARKDOWN_SELECTED),
        "REQUIRED_FOR_LIVE": True,
        "SOURCE_PATH": "doc.md",
        "SELECTOR": "md-heading:## Registered",
    }
    document = manifest([record], authority="LIVE_ELIGIBLE")
    assert em.verify_current(document, root=tmp_path)["verdict"] == em.CURRENT_MATCH
    write(source, MARKDOWN_SOURCE.replace("registered body", "registered body!"))
    current = em.verify_current(document, root=tmp_path)
    assert current["verdict"] == em.CURRENT_INPUT_DRIFT
    with pytest.raises(SailangError, match="LIVE_INPUT_DRIFT"):
        em.admit_live(document, root=tmp_path, network=Network())


# ---------------------------------------------------------------------------
# PRIVATE INPUTS
# ---------------------------------------------------------------------------


def private_input():
    return {
        "INPUT_ID": "PRIVATE-SOURCE",
        "SENSITIVITY": "PRIVATE_EPHEMERAL",
        "SOURCE_KIND": "TEXT_FILE",
        "EXTRACTION_KIND": "WHOLE_FILE",
        "EXTRACTOR_VERSION": "WHOLE-FILE-1",
        "EXTRACTED_SHA256": sha(b"destroyed plaintext"),
        "REQUIRED_FOR_LIVE": True,
        "SOURCE_PATH": "private/input.txt",
    }


def test_private_input_may_not_carry_an_archival_fixture():
    record = private_input()
    record["ARCHIVED_FIXTURE"] = "archive/private.txt"
    with pytest.raises(SailangError, match="MANIFEST_PRIVATE_FIXTURE_FORBIDDEN"):
        em.manifest_identity(manifest([record]))


def test_missing_private_plaintext_reports_unavailable_by_design(tmp_path):
    document = manifest([private_input()])
    result = em.verify_historical(document, fixture_root=tmp_path)
    assert result["verdict"] == em.HISTORICAL_INPUT_UNAVAILABLE_BY_DESIGN
    assert result["inputs"][0]["status"] == em.HISTORICAL_INPUT_UNAVAILABLE_BY_DESIGN
    assert result["verdict"] not in ("VERIFIED", "PASS", "FAIL_AS_CORRUPT", "RECONSTRUCTED")
    assert not list(tmp_path.rglob("*")), "private history must not gain plaintext or files"


def test_no_reconstruction_path_exists(tmp_path):
    parameters = set(inspect.signature(em.verify_historical).parameters)
    assert parameters == {"manifest", "fixture_root"}, (
        "historical verification must not receive a current-source root to fall back to")
    result = em.verify_historical(manifest([private_input()]), fixture_root=tmp_path)
    assert result["current_source_read"] is False


# ---------------------------------------------------------------------------
# CURRENT CHECKOUT
# ---------------------------------------------------------------------------


def test_current_selected_input_match_reported(tmp_path):
    write(tmp_path / "source.txt", b"payload")
    document = manifest([whole_file_input("MAIN", "source.txt", b"payload")])
    current = em.verify_current(document, root=tmp_path)
    assert current["verdict"] == em.CURRENT_MATCH
    assert current["inputs"] == [{"INPUT_ID": "MAIN", "status": em.CURRENT_MATCH}]


def test_current_input_drift_reported(tmp_path):
    write(tmp_path / "source.txt", b"payload")
    document = manifest([whole_file_input("MAIN", "source.txt", b"payload")])
    write(tmp_path / "source.txt", b"payload!")
    current = em.verify_current(document, root=tmp_path)
    assert current["verdict"] == em.CURRENT_INPUT_DRIFT
    assert current["inputs"][0]["reason"] == "EXTRACTED_SHA256_DIFFERS"


def test_implementation_drift_reported_independently(tmp_path):
    write(tmp_path / "source.txt", b"payload")
    write(tmp_path / "runner.py", b"runner v1")
    component = {"PATH": "runner.py", "SHA256": sha(b"runner v1"), "ROLE": "RUNNER"}
    document = manifest([whole_file_input("MAIN", "source.txt", b"payload")],
                        implementation=[component])
    assert em.verify_current(document, root=tmp_path)["verdict"] == em.CURRENT_MATCH
    write(tmp_path / "runner.py", b"runner v2")
    current = em.verify_current(document, root=tmp_path)
    assert current["verdict"] == em.CURRENT_IMPLEMENTATION_DRIFT
    assert current["inputs"][0]["status"] == em.CURRENT_MATCH
    assert current["implementation"][0]["status"] == em.CURRENT_IMPLEMENTATION_DRIFT


# ---------------------------------------------------------------------------
# LIVE ADMISSION
# ---------------------------------------------------------------------------


def live_document(tmp_path, *, input_bytes=b"payload", runner_bytes=b"runner v1"):
    write(tmp_path / "source.txt", input_bytes)
    write(tmp_path / "runner.py", runner_bytes)
    component = {"PATH": "runner.py", "SHA256": sha(runner_bytes), "ROLE": "RUNNER"}
    return manifest([whole_file_input("MAIN", "source.txt", input_bytes)],
                    authority="LIVE_ELIGIBLE", implementation=[component])


def test_exact_new_live_manifest_passes_local_admission(tmp_path):
    network = Network()
    document = live_document(tmp_path)
    result = em.admit_live(document, root=tmp_path, network=network)
    assert result["admitted"] is True
    assert result["network_calls"] == 0
    assert network.calls == 0
    assert result["manifest_identity"] == em.manifest_identity(document)


def test_changed_registered_input_refuses_before_network(tmp_path):
    network = Network()
    document = live_document(tmp_path, input_bytes=b"payload")
    write(tmp_path / "source.txt", b"payload changed")
    with pytest.raises(SailangError, match="LIVE_INPUT_DRIFT"):
        em.admit_live(document, root=tmp_path, network=network)
    assert network.calls == 0


def test_unknown_manifest_refuses_live_admission(tmp_path):
    document = live_document(tmp_path)
    document["manifest_version"] = "EXPERIMENT-MANIFEST-2"
    with pytest.raises(SailangError, match="MANIFEST_UNKNOWN_VERSION"):
        em.admit_live(document, root=tmp_path, network=Network())


def test_historical_only_manifest_cannot_go_live(tmp_path):
    network = Network()
    document = t71_manifest()
    assert document["authority"] == "HISTORICAL_ONLY"
    with pytest.raises(SailangError, match="HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY"):
        em.admit_live(document, root=ROOT, network=network)
    assert network.calls == 0


def test_live_refusals_perform_zero_network_calls(tmp_path):
    network = Network()
    document = live_document(tmp_path)
    document["authority"] = "HISTORICAL_ONLY"
    for mutate in (lambda: None,
                   lambda: write(tmp_path / "source.txt", b"drift"),
                   lambda: document["inputs"].append(copy.deepcopy(private_input()))):
        mutate()
        with pytest.raises(SailangError):
            em.admit_live(document, root=tmp_path, network=network)
        assert network.calls == 0


# ---------------------------------------------------------------------------
# T-71 REAL CONTROL
# ---------------------------------------------------------------------------


def test_t71_quarantine_historical_fixture_verifies():
    assert sha(QUARANTINE_FIXTURE.read_bytes()) == QUARANTINE_FIXTURE_SHA
    result = em.verify_historical(t71_manifest(), fixture_root=ROOT)
    row = next(r for r in result["inputs"] if r["INPUT_ID"] == "T71-QUARANTINE-SOURCE")
    assert row["status"] == em.HISTORICAL_VERIFIED


def test_t71_legacy_historical_fixture_verifies():
    assert sha(LEGACY_FIXTURE.read_bytes()) == LEGACY_FIXTURE_SHA
    result = em.verify_historical(t71_manifest(), fixture_root=ROOT)
    row = next(r for r in result["inputs"] if r["INPUT_ID"] == "T71-LEGACY-SOURCE")
    assert row["status"] == em.HISTORICAL_VERIFIED


@pytest.mark.parametrize("rel,recorded", [
    ("saimail/quarantine.py", QUARANTINE_FIXTURE_SHA),
    ("saimail/legacy.py", LEGACY_FIXTURE_SHA),
])
def test_t71_current_production_files_may_legitimately_differ(rel, recorded):
    current = (ROOT / rel).read_bytes()
    assert sha(current) != recorded, (
        "this check documents the separation only; if the current file happens to "
        "equal the historical pin, the drift control has nothing to show")
    assert em.verify_historical(t71_manifest(), fixture_root=ROOT)["verdict"] == \
        em.HISTORICAL_VERIFIED


def test_t71_historical_manifest_cannot_authorize_live():
    network = Network()
    with pytest.raises(SailangError, match="HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY"):
        em.admit_live(t71_manifest(), root=ROOT, network=network)
    assert network.calls == 0


# ---------------------------------------------------------------------------
# SEPARATION
# ---------------------------------------------------------------------------


def test_historical_green_and_current_drift_coexist(tmp_path):
    root = tmp_path / "checkout"
    for rel in ("tests/fixtures/t71/quarantine.py.txt", "tests/fixtures/t71/legacy.py.txt",
                "lab/ally_generation_live.py"):
        write(root / rel, (ROOT / rel).read_bytes())
    write(root / "lab/project_corpus_reachability.py", b"current runner moved on")
    assert em.verify_historical(t71_manifest(), fixture_root=root)["verdict"] == \
        em.HISTORICAL_VERIFIED
    current = em.verify_current(t71_manifest(), root=root)
    assert current["verdict"] == em.CURRENT_IMPLEMENTATION_DRIFT
    assert all(row["status"] == em.CURRENT_MATCH for row in current["inputs"])


def test_current_green_does_not_imply_historical_verification(tmp_path):
    write(tmp_path / "source.txt", b"payload")
    write(tmp_path / "archive/source.txt", b"substituted history")
    record = whole_file_input("MAIN", "source.txt", b"payload",
                              fixture="archive/source.txt")
    document = manifest([record])
    assert em.verify_current(document, root=tmp_path)["verdict"] == em.CURRENT_MATCH
    assert em.verify_historical(document, fixture_root=tmp_path)["verdict"] == \
        em.HISTORICAL_MISMATCH


def test_historical_green_does_not_imply_live_permission():
    network = Network()
    document = t71_manifest()
    assert em.verify_historical(document, fixture_root=ROOT)["verdict"] == \
        em.HISTORICAL_VERIFIED
    with pytest.raises(SailangError, match="HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY"):
        em.admit_live(document, root=ROOT, network=network)
    assert network.calls == 0


# ---------------------------------------------------------------------------
# REGRESSION
# ---------------------------------------------------------------------------


def test_manifest_module_is_offline_and_touches_no_production_module():
    source = (ROOT / "lab" / "experiment_manifest.py").read_text(encoding="utf-8")
    for token in ("import socket", "import urllib", "import requests", "http.client",
                  "import saimail", "from saimail"):
        assert token not in source, token


def test_t71_registration_and_fixtures_stay_immutable():
    assert sha((ROOT / "lab" / "project_corpus_reachability_registration.json").read_bytes()) \
        == T71_REGISTRATION_SHA
    assert sha(QUARANTINE_FIXTURE.read_bytes()) == QUARANTINE_FIXTURE_SHA
    assert sha(LEGACY_FIXTURE.read_bytes()) == LEGACY_FIXTURE_SHA
