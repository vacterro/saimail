"""B-018 real-project corpus pilot (Target A/B/C): frozen registration, one real
BuiltProjectCorpus, reproduction, mutation controls, B-016 compatibility.

The pilot freezes one immutable registration before capture, reads exactly the
registered sources, builds through the unchanged B-017 builder, and publishes
one explicit lab snapshot plus report.  These tests prove the frozen shape, the
registration identity, deterministic reproduction in fresh processes, every
mutation control, the absence of live model/network/mail side effects and the
future-pilot proof gate.
"""

import dataclasses
import hashlib
import inspect
import json
import re
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

from lab import project_corpus_pilot as pcp
from sailang.errors import SailangError
from saimail import ally_advice as aa
from saimail import ally_generation as ag
from saimail import project_corpus as pc

ROOT = Path(__file__).resolve().parent.parent
REAL_REGISTRATION = ROOT / "lab" / pcp.REGISTRATION_FILE
CREATED = "2026-09-19T21:00:00Z"
STAMP = "20260919T230000Z"
DECISIONS_PATH = "spec/DECISIONS.md"
LOG_PATH = ".saipen/LOG.md"
REPORT_PATH = "lab/out/ALLY_GENERATION_REPORT_20260919T201826Z_2a73d98de110453a.md"


def error(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value


def sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def copy_registered_sources(target: Path) -> Path:
    for spec in pcp.selection_artifacts():
        destination = target / spec["source"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / spec["source"]).read_bytes())
    return target


@pytest.fixture
def frozen(tmp_path):
    root = copy_registered_sources(tmp_path / "project")
    registration = pcp.freeze_registration(tmp_path / pcp.REGISTRATION_FILE, root)
    return root, tmp_path / pcp.REGISTRATION_FILE, registration


@pytest.fixture(scope="module")
def real_result():
    registration = pcp.load_registration(REAL_REGISTRATION)
    return pcp.build_pilot_corpus(registration, ROOT)


def rewrite_registration(path: Path, mutate):
    document = json.loads(Path(path).read_bytes().decode("utf-8"))
    mutate(document)
    Path(path).write_bytes(pcp.canonical_registration_bytes(document))


# ------------------------------------------------------ registration (1..7)


def test_real_registration_frozen_shape():
    registration = pcp.load_registration(REAL_REGISTRATION)
    assert registration.registration_version == pcp.PILOT_VERSION
    assert registration.project_scope == "project:saimail"
    assert registration.window_start == "2026-09-19T19:30:00Z"
    assert registration.window_end == "2026-09-19T21:20:00Z"
    assert registration.selection_basis == pc.SELECTION_BASIS
    assert registration.completeness == pc.COMPLETENESS
    assert registration.expected_artifact_count == 8
    assert registration.expected_event_count == 5
    assert tuple(entry.label for entry in registration.artifacts) == tuple(
        f"A{index}" for index in range(1, 9))
    assert tuple(entry.source_kind for entry in registration.artifacts) == (
        pc.SPEC_DECISION, pc.TEST_RESULT, pc.SPEC_DECISION, pc.TEST_RESULT,
        pc.REVIEW_FINDING, pc.SPEC_DECISION, pc.SPEC_DECISION, pc.TEST_RESULT)
    assert tuple(entry.source_ref for entry in registration.artifacts) == (
        "decision:D-047", "saipen-log:E-715", "decision:D-048", "saipen-log:E-726",
        "lab-report:ALLY_GENERATION_REPORT_20260919T201826Z_2a73d98de110453a",
        "decision:D-049", "decision:D-050", "saipen-log:E-779")
    assert tuple(entry.observed_at for entry in registration.artifacts) == (
        "2026-09-19T19:32:00Z", "2026-09-19T19:32:00Z", "2026-09-19T19:48:00Z",
        "2026-09-19T19:49:00Z", "2026-09-19T20:18:26Z", "2026-09-19T20:46:00Z",
        "2026-09-19T21:16:00Z", "2026-09-19T21:17:00Z")
    assert set(registration.source_file_sha256) == {
        DECISIONS_PATH, LOG_PATH, REPORT_PATH}
    assert tuple(entry.label for entry in registration.events) == (
        "P1", "P2", "P3", "P4", "P5")
    assert tuple(entry.members for entry in registration.events) == (
        ("A1", "A2"), ("A3", "A4"), ("A5",), ("A6",), ("A7", "A8"))


def test_registration_identity_is_canonical_bytes_digest():
    raw = REAL_REGISTRATION.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    assert pcp.canonical_registration_bytes(document) == raw
    registration = pcp.load_registration(REAL_REGISTRATION)
    assert registration.registration_id == pcp.registration_id_for(raw)
    assert registration.registration_id.startswith("sha256:")
    assert len(registration.registration_id) == len("sha256:") + 64


def test_registration_identity_is_stable_across_loads():
    first = pcp.load_registration(REAL_REGISTRATION)
    second = pcp.load_registration(REAL_REGISTRATION)
    assert first.registration_id == second.registration_id
    assert first.canonical_bytes == second.canonical_bytes


def test_registration_mutation_changes_identity(tmp_path):
    raw = REAL_REGISTRATION.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    document["window_start"] = "2026-09-19T19:30:01Z"
    mutated = tmp_path / pcp.REGISTRATION_FILE
    mutated.write_bytes(pcp.canonical_registration_bytes(document))
    changed = pcp.load_registration(mutated)
    original = pcp.load_registration(REAL_REGISTRATION)
    assert changed.registration_id != original.registration_id
    noncanonical = tmp_path / "noncanonical.json"
    noncanonical.write_bytes(raw + b" ")
    assert error(pcp.load_registration, noncanonical).code == (
        pcp.PROJECT_PILOT_REGISTRATION_INVALID)


def test_registration_requires_source_pins(tmp_path):
    raw = REAL_REGISTRATION.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    del document["source_file_sha256"][LOG_PATH]
    mutated = tmp_path / pcp.REGISTRATION_FILE
    mutated.write_bytes(pcp.canonical_registration_bytes(document))
    assert error(pcp.load_registration, mutated).code == (
        pcp.PROJECT_PILOT_REGISTRATION_INVALID)


def test_dropped_artifact_refused(tmp_path):
    # C5: the registered count is a frozen exact shape; a seven-item request
    # never silently builds a seven-item corpus.
    raw = REAL_REGISTRATION.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    document["artifacts"] = [entry for entry in document["artifacts"]
                             if entry["label"] != "A4"]
    mutated = tmp_path / pcp.REGISTRATION_FILE
    mutated.write_bytes(pcp.canonical_registration_bytes(document))
    assert error(pcp.load_registration, mutated).code == (
        pcp.PROJECT_PILOT_ARTIFACT_COUNT_MISMATCH)


def test_unknown_source_kind_refused(tmp_path):
    # C7: an unknown source kind refuses; the unknown string is never preserved.
    raw = REAL_REGISTRATION.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    document["artifacts"][4]["source_kind"] = "SOCIAL_POST"
    mutated = tmp_path / pcp.REGISTRATION_FILE
    mutated.write_bytes(pcp.canonical_registration_bytes(document))
    assert error(pcp.load_registration, mutated).code == (
        pc.PROJECT_CORPUS_SOURCE_KIND_UNKNOWN)


def test_out_of_window_artifact_refused(frozen):
    # C6: OBSERVED_AT = WINDOW_END is outside the half-open window; never clamped.
    root, registration_path, _ = frozen
    rewrite_registration(
        registration_path,
        lambda document: document["artifacts"][4].__setitem__(
            "observed_at", "2026-09-19T21:20:00Z"))
    registration = pcp.load_registration(registration_path)
    assert error(pcp.build_pilot_corpus, registration, root).code == (
        pc.PROJECT_CORPUS_WINDOW_EXCLUDED)


# ------------------------------------------------------------- build (18..26)


def test_build_shape_and_identity_minted_by_b017(frozen):
    root, _, registration = frozen
    result = pcp.build_pilot_corpus(registration, root)
    built = result.built
    assert isinstance(built, pc.BuiltProjectCorpus)
    assert pc.is_built_project_corpus(built) is True
    assert built.project_scope == "project:saimail"
    assert built.window_start == "2026-09-19T19:30:00Z"
    assert built.window_end == "2026-09-19T21:20:00Z"
    assert built.selection_basis == pc.SELECTION_BASIS
    assert built.artifact_count == 8
    assert built.event_count == 5
    assert result.registration.completeness == "NOT_PROVEN"
    assert built.build_id.startswith("sha256:")
    assert built.corpus_id.startswith("sha256:")
    assert built.build_id != built.corpus_id
    assert len(built.receipts()) == 8
    assert len(built.evidence_refs()) == 8
    assert len(built.event_refs()) == 5


def test_evidence_refs_are_builder_minted_not_ad_hoc(frozen):
    root, _, registration = frozen
    result = pcp.build_pilot_corpus(registration, root)
    for entry, artifact in zip(result.registration.artifacts,
                               result.capture.artifacts, strict=True):
        assert result.evidence_ref_for(entry.label) == pc.project_evidence_ref(artifact)
        assert sha256_text(artifact.content) == entry.extracted_content_sha256
    assert not hasattr(pc.ProjectArtifact, "evidence_ref")


def test_event_refs_are_builder_minted_from_exact_membership(frozen):
    root, _, registration = frozen
    result = pcp.build_pilot_corpus(registration, root)
    declarations = result.built.request.event_declarations
    assert len(declarations) == 5
    for event, declaration in zip(registration.events, declarations, strict=True):
        assert result.event_ref_for_event(event.label) == (
            pc.project_event_ref(declaration))
        assert declaration.member_evidence_refs == tuple(sorted(
            result.evidence_ref_for(label) for label in event.members))
    assert all(entry.computed_event_ref for entry in declarations)


def test_exact_event_partition_of_real_artifacts(frozen):
    root, _, registration = frozen
    result = pcp.build_pilot_corpus(registration, root)
    membership = {}
    for event in registration.events:
        for label in event.members:
            assert label not in membership, "one artifact belongs to one event"
            membership[label] = event.label
    assert set(membership) == {entry.label for entry in registration.artifacts}
    mapping = dict(result.built.evidence_ref_to_event_ref())
    for label, evidence_ref in result.evidence_labels:
        assert mapping[evidence_ref] == result.event_ref_for_artifact(label)


# --------------------------------------------------------- reproduction (27..31)


def test_rebuild_same_process_is_identity_identical():
    registration = pcp.load_registration(REAL_REGISTRATION)
    first = pcp.build_pilot_corpus(registration, ROOT)
    second = pcp.build_pilot_corpus(registration, ROOT)
    assert first.evidence_labels == second.evidence_labels
    assert first.event_refs_by_label == second.event_refs_by_label
    assert first.built.build_id == second.built.build_id
    assert first.built.corpus_id == second.built.corpus_id


FRESH_PROCESS_SCRIPT = """
import json, pathlib, sys
sys.path.insert(0, {root!r})
from lab import project_corpus_pilot as pcp
registration = pcp.load_registration(pathlib.Path({registration!r}))
result = pcp.build_pilot_corpus(registration, pathlib.Path({sources!r}))
print(json.dumps({{
    "registration_id": registration.registration_id,
    "build_id": result.built.build_id,
    "corpus_id": result.built.corpus_id,
    "evidence": [list(row) for row in result.evidence_labels],
    "events": [list(row) for row in result.event_refs_by_label],
}}, sort_keys=True))
"""


def test_rebuild_in_two_fresh_processes_is_identity_identical(frozen):
    root, registration_path, registration = frozen
    script = FRESH_PROCESS_SCRIPT.format(
        root=str(ROOT), registration=str(registration_path), sources=str(root))
    outputs = []
    for _ in range(2):
        completed = subprocess.run(
            [sys.executable, "-c", script], cwd=str(ROOT), check=True,
            capture_output=True, text=True, timeout=120)
        outputs.append(json.loads(completed.stdout))
    local = pcp.build_pilot_corpus(registration, root)
    assert outputs[0] == outputs[1]
    assert outputs[0]["registration_id"] == registration.registration_id
    assert outputs[0]["build_id"] == local.built.build_id
    assert outputs[0]["corpus_id"] == local.built.corpus_id
    assert outputs[0]["evidence"] == [list(row) for row in local.evidence_labels]
    assert outputs[0]["events"] == [list(row) for row in local.event_refs_by_label]


def test_caller_ordering_does_not_change_identity(frozen):
    root, _, registration = frozen
    result = pcp.build_pilot_corpus(registration, root)
    reversed_request = pc.ProjectCorpusRequest(
        project_scope=registration.project_scope,
        window_start=registration.window_start,
        window_end=registration.window_end,
        selection_basis=registration.selection_basis,
        artifacts=tuple(reversed(result.capture.artifacts)),
        event_declarations=tuple(reversed(result.built.request.event_declarations)),
    )
    reversed_built = pc.build_project_corpus(reversed_request)
    assert reversed_built.build_id == result.built.build_id
    assert reversed_built.corpus_id == result.built.corpus_id


# ------------------------------------------------------------- mutation (32..39)


def test_source_content_mutation_refuses_old_registration(frozen):
    # C2: one byte changed in the registered D-047 section refuses the old
    # registration; the real source is untouched (fixture copy only).
    root, _, registration = frozen
    decisions = root / DECISIONS_PATH
    text = decisions.read_bytes().decode("utf-8")
    assert "single-attempt" in text
    decisions.write_bytes(text.replace("single-attempt", "single-attempt!", 1).encode("utf-8"))
    assert error(pcp.build_pilot_corpus, registration, root).code == (
        pcp.PROJECT_PILOT_SOURCE_CHANGED)


def test_log_record_mutation_refuses_old_registration(frozen):
    # C3: modifying the E-726 record refuses; no substitution with E-725/E-727.
    root, _, registration = frozen
    log = root / LOG_PATH
    text = log.read_bytes().decode("utf-8")
    target = "[E-726]"
    index = text.index(target)
    end = text.index("\n", index)
    log.write_bytes((text[:end] + " MUTATED" + text[end:]).encode("utf-8"))
    assert error(pcp.build_pilot_corpus, registration, root).code == (
        pcp.PROJECT_PILOT_SOURCE_CHANGED)


def test_append_only_journal_growth_is_recovered_by_content_pin(frozen):
    # The registered journal is SAIPEN's append-only LOG: growth after the
    # freeze may be recovered only by proving every registered record still
    # matches its content pin; identity is unchanged and recovery is recorded.
    root, _, registration = frozen
    baseline = pcp.build_pilot_corpus(registration, root)
    log = root / LOG_PATH
    log.write_bytes(log.read_bytes() + (
        b"- 19.09.26 22:00 [E-900] [parent: E-899] [T-none] [agent: lab] "
        b"RUN: appended after the pilot freeze\n"))
    result = pcp.build_pilot_corpus(registration, root)
    assert dict(result.capture.source_recovery) == {
        LOG_PATH: pcp.APPEND_ONLY_CONTENT_PIN_MATCH}
    assert result.evidence_labels == baseline.evidence_labels
    assert result.event_refs_by_label == baseline.event_refs_by_label
    assert result.built.build_id == baseline.built.build_id
    assert result.built.corpus_id == baseline.built.corpus_id
    for label in ("A2", "A4", "A8"):
        content = result.built.reflection_corpus.item_for(
            result.evidence_ref_for(label)).content
        assert content == baseline.built.reflection_corpus.item_for(
            baseline.evidence_ref_for(label)).content


def test_append_only_recovery_still_refuses_a_modified_record(frozen):
    # Growth is recoverable; a changed registered record is not.
    root, _, registration = frozen
    log = root / LOG_PATH
    text = log.read_bytes().decode("utf-8")
    index = text.index("[E-779]")
    end = text.index("\n", index)
    log.write_bytes((text[:end] + " MUTATED" + text[end:]).encode("utf-8"))
    assert error(pcp.build_pilot_corpus, registration, root).code == (
        pcp.PROJECT_PILOT_SOURCE_CHANGED)


def test_event_regrouping_changes_identities_and_proof(frozen):
    # C4: moving A8 from P5 into P4 changes the event mapping, BUILD_ID and
    # CORPUS_ID; the old BuiltProjectCorpus proof cannot transfer.
    root, registration_path, registration = frozen
    original = pcp.build_pilot_corpus(registration, root)
    rewrite_registration(
        registration_path,
        lambda document: (
            document["events"][3].__setitem__("members", ["A6", "A8"]),
            document["events"][4].__setitem__("members", ["A7"]),
        ))
    regrouped_registration = pcp.load_registration(registration_path)
    assert regrouped_registration.registration_id != registration.registration_id
    regrouped = pcp.build_pilot_corpus(regrouped_registration, root)
    assert regrouped.event_ref_for_event("P4") != original.event_ref_for_event("P4")
    assert regrouped.event_ref_for_event("P5") != original.event_ref_for_event("P5")
    assert regrouped.built.build_id != original.built.build_id
    assert regrouped.built.corpus_id != original.built.corpus_id
    assert error(dataclasses.replace, original.built,
                 request=regrouped.built.request).code == (
        pc.PROJECT_CORPUS_PROOF_FORGED)


# ------------------------------------------- projection, report, claims (B9..B12)


def test_pilot_run_publishes_immutable_snapshot_and_report(frozen, tmp_path, monkeypatch):
    root, _, registration = frozen
    monkeypatch.setattr(pcp, "utc_stamp", lambda now=None: STAMP)
    out = tmp_path / "out"
    result, artifact_path, report_path = pcp.run_pilot(registration, root, out)
    assert artifact_path.name == f"project_corpus_pilot_{STAMP}.json"
    assert report_path.name == f"PROJECT_CORPUS_PILOT_REPORT_{STAMP}.md"
    assert sorted(entry.name for entry in out.iterdir()) == [
        f"PROJECT_CORPUS_PILOT_REPORT_{STAMP}.md",
        f"project_corpus_pilot_{STAMP}.json",
    ]
    # B9: the in-process proof is the type-state, never a deserialized report.
    assert isinstance(result.built, pc.BuiltProjectCorpus)
    document = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert document["registration_id"] == registration.registration_id
    assert document["build_id"] == result.built.build_id
    assert document["corpus_id"] == result.built.corpus_id
    assert document["artifact_count"] == 8
    assert document["event_count"] == 5
    assert document["completeness"] == "NOT_PROVEN"
    for entry in document["artifacts"]:
        assert entry["evidence_ref"] == result.evidence_ref_for(entry["label"])
        assert entry["event_ref"] == result.event_ref_for_artifact(entry["label"])
        assert entry["content_sha256"] == sha256_text(entry["content"])
    assert document["source_immutability"]["unchanged_during_capture"] is True
    # an identical second publication is idempotent, never a rewrite
    _, same_artifact, _ = pcp.run_pilot(registration, root, out)
    assert same_artifact.read_bytes() == artifact_path.read_bytes()


def test_conflicting_artifact_bytes_refuse(frozen, tmp_path):
    root, _, registration = frozen
    out = tmp_path / "clash"
    out.mkdir()
    (out / pcp.ARTIFACT_TEMPLATE.format(stamp=STAMP)).write_bytes(b"not the pilot")
    assert error(pcp.run_pilot, registration, root, out, stamp=STAMP).code == (
        pcp.PROJECT_PILOT_ARTIFACT_CHANGED)


def test_serialized_artifact_and_report_carry_limits(frozen, tmp_path):
    root, _, registration = frozen
    result, artifact_path, report_path = pcp.run_pilot(
        registration, root, tmp_path / "out", stamp=STAMP)
    artifact_text = artifact_path.read_text(encoding="utf-8")
    report_text = report_path.read_text(encoding="utf-8")
    document = json.loads(artifact_text)
    metadata = dict(document)
    metadata["artifacts"] = [
        {key: value for key, value in entry.items() if key != "content"}
        for entry in document["artifacts"]]
    metadata_text = json.dumps(metadata, ensure_ascii=False)
    # C8: COMPLETENESS = NOT_PROVEN and no positive completeness assertion in
    # the pilot's own metadata or report (captured source content may quote the
    # forbidden terms as explicitly forbidden terms).
    for text in (metadata_text, report_text):
        assert "NOT_PROVEN" in text
        assert re.search(r"\b(COMPLETE|EXHAUSTIVE|ALL_RELEVANT|UNBIASED)\b", text) is None
        assert "EVENT_REF_IS_TRUTH = false" in text
    # B12: report carries the exact identities and mappings.
    assert registration.registration_id in report_text
    assert result.built.build_id in report_text
    assert result.built.corpus_id in report_text
    for label in ("A1", "A8"):
        assert result.evidence_ref_for(label) in report_text
        assert result.event_ref_for_artifact(label) in report_text
    for label in ("P1", "P5"):
        assert result.event_ref_for_event(label) in report_text
    assert "What this run does not show" in report_text
    assert "grouping" in report_text


def test_artifact_and_report_have_no_forbidden_content_literals(frozen, tmp_path):
    # B11: no ALLY1/HENV1/HLET1 objects, no credentials, no model output in the
    # pilot's own metadata; the captured project-operational content is the
    # explicitly registered selection and is checked for object/canonical markers.
    root, _, registration = frozen
    _, artifact_path, report_path = pcp.run_pilot(
        registration, root, tmp_path / "out", stamp=STAMP)
    document = json.loads(artifact_path.read_text(encoding="utf-8"))
    metadata = dict(document)
    metadata["artifacts"] = [
        {key: value for key, value in entry.items() if key != "content"}
        for entry in document["artifacts"]]
    metadata_text = json.dumps(metadata, ensure_ascii=False)
    for forbidden in ("ALLY1", "HLET1", "HENV1", "BEGIN PRIVATE KEY",
                      "Authorization:", "Bearer ", "api_key"):
        assert forbidden not in metadata_text
    report_text = report_path.read_text(encoding="utf-8")
    for forbidden in ("BEGIN PRIVATE KEY", "Authorization:", "Bearer ",
                      "api_key", '"FORMAT":"ALLY1"'):
        assert forbidden not in report_text


# ------------------------------------------------------- B-016 compatibility (40..44)


class FixedGenerator:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def generate(self, corpus):
        self.calls += 1
        return self.result


class ReportReviewer:
    def __init__(self, evidence_refs):
        self.evidence_refs = tuple(sorted(evidence_refs))
        self.calls = 0

    def review(self, resolved, corpus):
        self.calls += 1
        verdicts = tuple(
            ag.ReviewVerdict(
                dimension,
                ag.PASS,
                f"{dimension} rationale.",
                self.evidence_refs
                if dimension in ag.EVIDENCE_REQUIRED_DIMENSIONS else ())
            for dimension in ag.DIMENSIONS
        )
        return ag.SemanticReviewReport(
            ag.ally_candidate_id(resolved.advice), corpus.corpus_id,
            ag.RUBRIC_VERSION, verdicts)


def two_event_candidate(result):
    refs = [result.evidence_ref_for(label)
            for label in ("A1", "A2", "A3", "A4", "A5")]
    return aa.AllyAdvice(
        created=CREATED,
        work_context="Real pilot corpus structural compatibility check.",
        observed_scope="One bounded project window.",
        observed=(
            aa.AdviceObservation("First observation across two captures.",
                                 tuple(sorted(refs[:2]))),
            aa.AdviceObservation("Second observation from another declared event.",
                                 tuple(sorted(refs[2:4]))),
        ),
        inferred="The captures may describe a recurring operational shape.",
        guidance_mode=aa.CONSIDER_CHANGE,
        suggested="Consider one reversible review pass before the next release.",
        counterevidence=(
            aa.AdviceCounterevidence("Counterevidence capture limits the inference.",
                                     (refs[4],)),
        ),
        uncertainty="This bounded sample may be specific to one window.",
    )


def one_event_candidate(result):
    refs = [result.evidence_ref_for(label) for label in ("A1", "A2", "A3")]
    return aa.AllyAdvice(
        created=CREATED,
        work_context="Temporary one-declared-event candidate.",
        observed_scope="One bounded project window.",
        observed=(
            aa.AdviceObservation("First observation from one declared event.",
                                 tuple(sorted(refs[:2]))),
            aa.AdviceObservation("Second observation from the same declared event.",
                                 (refs[2],)),
        ),
        inferred="The captures may describe one occurrence.",
        guidance_mode=aa.CONSIDER_CHANGE,
        suggested="Consider one reversible review pass before the next release.",
        counterevidence=(
            aa.AdviceCounterevidence("Counterevidence capture limits the inference.",
                                     (refs[0],)),
        ),
        uncertainty="This bounded sample may be specific to one window.",
    )


def test_real_built_corpus_reaches_semantic_reviewer(real_result):
    # C9: real BuiltProjectCorpus.reflection_corpus + deterministic fakes only.
    candidate = two_event_candidate(real_result)
    generator = FixedGenerator(ag.GeneratorResult.of(candidate))
    reviewer = ReportReviewer((real_result.evidence_ref_for("A1"),
                               real_result.evidence_ref_for("A5")))
    outcome = ag.generate_reviewed_ally_advice(
        real_result.built.reflection_corpus, generator, reviewer)
    assert outcome.status == ag.APPROVED
    assert generator.calls == 1
    assert reviewer.calls == 1
    assert isinstance(outcome.reviewed, ag.SemanticallyReviewedAllyAdvice)


def test_one_event_fake_candidate_has_zero_reviewer_calls(frozen):
    # C9 second half: the frozen partition's largest declared event holds two
    # artifacts while B-012 needs three distinct observed refs, so the control
    # runs against a temporary explicitly regrouped registration over the same
    # real source bytes; the declared-event gate itself is corpus-independent.
    root, registration_path, _ = frozen
    rewrite_registration(
        registration_path,
        lambda document: (
            document["events"][0].__setitem__("members", ["A1", "A2", "A3"]),
            document["events"][1].__setitem__("members", ["A4"]),
        ))
    regrouped = pcp.load_registration(registration_path)
    result = pcp.build_pilot_corpus(regrouped, root)
    candidate = one_event_candidate(result)
    generator = FixedGenerator(ag.GeneratorResult.of(candidate))
    reviewer = ReportReviewer((result.evidence_ref_for("A1"),))
    outcome = ag.generate_reviewed_ally_advice(
        result.built.reflection_corpus, generator, reviewer)
    assert outcome.status == ag.REJECTED
    assert outcome.code == ag.ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS
    assert generator.calls == 1
    assert reviewer.calls == 0
    assert outcome.reviewed is None


def test_future_pilot_gate_requires_the_built_proof(real_result):
    # C10: the future live-pilot entrance boundary.
    assert pc.require_built_project_corpus(real_result.built) is real_result.built
    assert error(pc.require_built_project_corpus,
                 real_result.built.reflection_corpus).code == (
        pc.PROJECT_CORPUS_BUILDER_PROOF_REQUIRED)
    assert pc.is_built_project_corpus(real_result.built.reflection_corpus) is False


def test_generic_synthetic_b016_path_is_unchanged():
    # 44: an arbitrary ReflectionCorpus stays valid for synthetic experiments.
    refs = [sha256_text(f"synthetic-{index}") for index in range(4)]
    raw = ag.ReflectionCorpus(items=tuple(
        ag.ReflectionItem(
            evidence_ref=ref,
            source_domain=ag.PROJECT_OPERATIONAL,
            observed_at=CREATED,
            observed_scope="synthetic:test",
            content=f"Synthetic item {index}.",
            event_ref=sha256_text(f"synthetic-event-{index % 2}"),
        )
        for index, ref in enumerate(refs)
    ))
    candidate = aa.AllyAdvice(
        created=CREATED,
        work_context="Generic synthetic corpus check.",
        observed_scope="synthetic:test",
        observed=(
            aa.AdviceObservation("First synthetic observation.",
                                 tuple(sorted((refs[0], refs[1])))),
            aa.AdviceObservation("Second synthetic observation.", (refs[2],)),
        ),
        inferred="The synthetic items may be unrelated.",
        guidance_mode=aa.CONSIDER_CHANGE,
        suggested="Consider one reversible review pass before the next release.",
        counterevidence=(aa.AdviceCounterevidence("One synthetic item limits this.",
                                                  (refs[3],)),),
        uncertainty="Synthetic items prove interface compatibility only.",
    )
    reviewer = ReportReviewer((refs[0], refs[3]))
    outcome = ag.generate_reviewed_ally_advice(
        raw, FixedGenerator(ag.GeneratorResult.of(candidate)), reviewer)
    assert outcome.status == ag.APPROVED
    assert reviewer.calls == 1


# --------------------------------------------------------- side effects (45..51)


def test_pilot_module_has_no_live_transport_surface():
    source = inspect.getsource(pcp)
    imports = re.findall(r"^\s*(?:import|from)\s+([A-Za-z0-9_.]+)", source,
                         flags=re.MULTILINE)
    for module in imports:
        assert module.split(".")[0] not in (
            "socket", "requests", "urllib", "http", "subprocess", "aiohttp",
            "httpx"), module
    for forbidden in ("os.walk", "rglob(", "iterdir(", "glob(", "model_name",
                      "temperature", "embedding", "api_key", "9router.",
                      "saifren_run", "urlopen("):
        assert forbidden not in source, forbidden


def test_pilot_run_makes_zero_network_calls(frozen, tmp_path, monkeypatch):
    root, _, registration = frozen

    def boom(*args, **kwargs):
        raise AssertionError("the pilot must make no network call")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    result, _, _ = pcp.run_pilot(registration, root, tmp_path / "out", stamp=STAMP)
    assert result.built.artifact_count == 8


def test_pilot_run_makes_zero_mail_or_attention_calls(frozen, tmp_path, monkeypatch):
    from saimail.human_attention import AttentionQueue
    from saimail.sailetter import HumanPrivateStore

    root, _, registration = frozen

    def boom(*args, **kwargs):
        raise AssertionError("the pilot must not touch the human-private corridor")

    monkeypatch.setattr(aa, "ally_to_human_private", boom)
    monkeypatch.setattr(ag, "reviewed_ally_to_human_private", boom)
    monkeypatch.setattr("saimail.sailetter.seal_human_private", boom)
    monkeypatch.setattr(HumanPrivateStore, "deliver", boom)
    monkeypatch.setattr(AttentionQueue, "admit_receiver_candidate", boom)
    result, _, _ = pcp.run_pilot(registration, root, tmp_path / "out", stamp=STAMP)
    assert result.built.event_count == 5


def test_pilot_run_creates_no_human_private_artifact(frozen, tmp_path):
    root, _, registration = frozen
    _, _, _ = pcp.run_pilot(registration, root, tmp_path / "out", stamp=STAMP)
    names = sorted(entry.name for entry in (tmp_path / "out").iterdir())
    assert names == [f"PROJECT_CORPUS_PILOT_REPORT_{STAMP}.md",
                     f"project_corpus_pilot_{STAMP}.json"]


def test_registered_real_selection_content_is_never_rewritten(real_result):
    # C13: the pilot observes history. The strict pins still hold for every
    # non-journal source; the append-only journal grew because SAIPEN itself
    # keeps checkpointing, and that growth is recovered only by proving every
    # registered record byte-identical (recorded, never silent).
    registration = pcp.load_registration(REAL_REGISTRATION)
    hashes = pcp.source_hashes(registration, ROOT)
    assert hashes[DECISIONS_PATH] == registration.source_file_sha256[DECISIONS_PATH]
    assert hashes[REPORT_PATH] == registration.source_file_sha256[REPORT_PATH]
    capture = real_result.capture
    assert capture.source_hashes_before == capture.source_hashes_after
    for source, reason in capture.source_recovery:
        assert source == LOG_PATH
        assert reason == pcp.APPEND_ONLY_CONTENT_PIN_MATCH
    for entry in registration.artifacts:
        content = real_result.built.reflection_corpus.item_for(
            real_result.evidence_ref_for(entry.label)).content
        assert sha256_text(content) == entry.extracted_content_sha256
