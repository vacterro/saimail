"""D1 focused acceptance: release decision inputs, packet and publication gate.

Focused areas: version-surface agreement, frozen-wheel immutability and exact
identity, mechanical frozen-vs-checkout delta, claim-boundary honesty, external
proof binding, bounded packet schema, publication defaulting to forbidden, and
no secret leakage. Contract: spec/21-RELEASE-DECISION-v0.md, D-054.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
EVIDENCE = ROOT / "release" / "evidence"
FROZEN_SHA256 = "ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a"
FROZEN_WHEEL = ROOT / "release" / "local-alpha" / "saimail-0.0.2a1-py3-none-any.whl"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rd = _load("release_decision", TOOLS / "release_decision.py")
privacy = _load("scan_local_alpha_privacy", TOOLS / "scan_local_alpha_privacy.py")


@pytest.fixture(scope="module")
def packet() -> dict:
    return json.loads((EVIDENCE / "release_decision.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def inputs() -> dict:
    return rd.build_decision_inputs(ROOT)


def test_version_surfaces_agree_with_the_canonical_authority(inputs):
    # The D1 packet records the checkout as of D1; D2 owns the version bump, so
    # this asserts agreement with the canonical VERSION authority, not a frozen
    # D1-era literal.
    canonical = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    version = inputs["version_identity"]
    assert version["canonical_authority"] == "VERSION"
    assert version["agreement"] is True, version["surfaces"]
    assert version["surfaces"]["VERSION"] == canonical
    assert version["surfaces"]["pyproject.toml"] == version["canonical"]
    assert version["surfaces"]["saimail_local.py._VERSION_FALLBACK"] == version["canonical"]
    assert version["surfaces"]["lab/stable_local_api.json.release"] == version["canonical"]
    for name in ("README.md", "README.ee.md", "README.ded.md", "README.ja.md"):
        assert version["surfaces"][name] == version["canonical"], name


def test_frozen_candidate_remains_immutable_and_hash_exact():
    manifest = json.loads(
        (ROOT / "release" / "local-alpha" / "local_alpha_candidate.json").read_text(
            encoding="utf-8"))
    actual = hashlib.sha256(FROZEN_WHEEL.read_bytes()).hexdigest()
    assert actual == FROZEN_SHA256
    assert manifest["wheel"]["sha256"] == FROZEN_SHA256
    assert manifest["publication_status"] == "NOT_PUBLISHED"
    sums = (ROOT / "release" / "local-alpha" / "SHA256SUMS.txt").read_text(encoding="utf-8")
    assert f"{FROZEN_SHA256}  {FROZEN_WHEEL.name}" in sums
    acceptance = json.loads(
        (EVIDENCE / "external_proof_acceptance.json").read_text(encoding="utf-8"))
    assert acceptance["candidate_sha256"] == FROZEN_SHA256
    names = zipfile.ZipFile(FROZEN_WHEEL).namelist()
    assert len(names) == manifest["wheel"]["member_count"] == 57


def test_checkout_frozen_delta_is_detected_mechanically(inputs):
    frozen = inputs["frozen_capability"]
    checkout = inputs["checkout_capability"]
    assert frozen["has_custody_module"] is False
    assert frozen["identity_schemas"] == ["SAIMAIL_LOCAL_IDENTITY_1"]
    assert frozen["cli_custody_commands"] is False
    assert frozen["cli_os_store"] is False
    assert checkout["has_custody_module"] is True
    assert "SAIMAIL_LOCAL_IDENTITY_2" in checkout["identity_schemas"]
    assert checkout["cli_custody_commands"] is True
    assert inputs["source_lineage"]["post_candidate_source_delta"] == ["V3-01"]
    assert inputs["source_lineage"]["external_evidence_scope"] == "FROZEN_WHEEL_ONLY"
    with zipfile.ZipFile(FROZEN_WHEEL) as archive:
        cli = archive.read("saimail_local.py").decode("utf-8")
    assert "custody" not in cli and "os-store" not in cli


def test_packet_is_bounded_and_schema_valid(packet):
    report = rd.validate_decision(ROOT, packet)
    assert report["status"] == "PASS", report["problems"]
    assert packet["schema"] == rd.DECISION_SCHEMA
    assert packet["version"] == 1
    assert packet["outcome"] in rd.ALLOWED_OUTCOMES
    assert packet["outcome"] == "NEW_CANDIDATE_REQUIRED"
    assert [gate["id"] for gate in packet["gates"]] == list(rd.GATE_IDS)
    claims = {row["claim"] for row in packet["claims"]}
    for required in rd.REQUIRED_CLAIMS:
        assert required in claims, required
    stages = [stage["stage"] for stage in packet["publication_mechanics"]["stages"]]
    assert stages == list(rd.PUBLICATION_STAGES)


def test_historical_proof_cannot_apply_to_a_different_wheel():
    acceptance = json.loads(
        (EVIDENCE / "external_proof_acceptance.json").read_text(encoding="utf-8"))
    assert rd.external_proof_applies(acceptance, FROZEN_SHA256) is True
    assert rd.external_proof_applies(acceptance, "0" * 64) is False
    assert rd.external_proof_applies(acceptance, "") is False


def test_post_v301_source_cannot_be_called_externally_verified(packet):
    claims = {row["claim"]: row for row in packet["claims"]}
    assert claims["external_install"]["frozen_0_0_2a1"] == "PROVEN"
    assert claims["external_install"]["current_checkout"] == "NOT_PROVEN"
    assert claims["os_store_custody"]["frozen_0_0_2a1"] == "ABSENT"
    assert claims["os_store_custody"]["current_checkout"] == "PROVEN"
    assert claims["os_store_custody"]["next_distributable_candidate"] == "NOT_PROVEN"
    assert packet["support_scope"]["external_evidence_scope"] == "FROZEN_WHEEL_ONLY"

    tampered = copy.deepcopy(packet)
    for row in tampered["claims"]:
        if row["claim"] == "os_store_custody":
            row["frozen_0_0_2a1"] = "PROVEN"
    assert rd.validate_decision(ROOT, tampered)["status"] == "FAIL"

    dishonest = copy.deepcopy(packet)
    dishonest["outcome"] = "READY_TO_PUBLISH_EXISTING_CANDIDATE"
    report = rd.validate_decision(ROOT, dishonest)
    assert report["status"] == "FAIL"
    assert any("READY" in problem for problem in report["problems"])


def test_publication_defaults_to_forbidden_without_operator_authorization(packet):
    assert rd.publication_allowed(packet) is False
    assert rd.publication_allowed(packet, operator_authorization="operator said yes") is False
    ready = copy.deepcopy(packet)
    ready["outcome"] = "READY_TO_PUBLISH_EXISTING_CANDIDATE"
    ready["publication_authorization"] = "PRESENT"
    assert rd.publication_allowed(ready, operator_authorization="approved by operator") is True
    assert rd.publication_allowed(ready) is False
    assert packet["publication"] == "NONE"
    assert packet["publication_authorization"] == "ABSENT"


def test_next_candidate_identity_cannot_equal_the_frozen_candidate(packet):
    version = packet["version_decision"]
    assert version["next_candidate_version"] == "0.0.2a2"
    assert version["next_candidate_version"] != version["current_frozen_artifact_version"]
    assert version["current_frozen_artifact_version"] == "0.0.2a1"
    collided = copy.deepcopy(packet)
    collided["version_decision"]["next_candidate_version"] = "0.0.2a1"
    report = rd.validate_decision(ROOT, collided)
    assert report["status"] == "FAIL"
    assert any("next_candidate_version" in problem for problem in report["problems"])


def test_decision_artifacts_contain_no_secrets():
    for name in ("release_decision.json", "release_decision_inputs.json",
                 "RELEASE-DECISION.md"):
        findings = privacy.scan_path(EVIDENCE / name)
        assert findings == [], (name, findings)
    packet_text = (EVIDENCE / "release_decision.json").read_text(encoding="utf-8")
    assert "PRIVATE KEY-----" not in packet_text
    assert '"secrets"' not in packet_text or "NONE" in packet_text
