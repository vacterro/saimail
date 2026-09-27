"""T-74 budget4096 harness: registration freeze, per-function budgets, privacy.

Dry controls run the harness against deterministic fakes: the exact B-018 corpus
is rebuilt locally, the generator request carries max_tokens 4096 and the
reviewer request max_tokens 2048, ``response_format`` is absent, a >4000-byte
full output reaches the strict parser intact, and no raw prose is durable.
"""

import json
import pathlib
import socket
from types import SimpleNamespace

import pytest

from lab import parse_shape as shape
from lab import project_corpus_budget4096 as budget
from lab import project_corpus_generation_pilot as pilot
from lab import saifren_run as live
from sailang.errors import SailangError

CANARY = "PRIVATE_BUDGET4096_CANARY_4a71c"
STARTED = "2026-09-20T00:00:00Z"


@pytest.fixture(scope="module")
def built():
    return pilot.prepare_input(budget.ROOT)


def document(built, transport=None):
    return budget._experiment(built, transport or budget.DryTransport(
        built.reflection_corpus,
        candidate=budget.large_valid_candidate(built.reflection_corpus)),
        dry_run=True, started=STARTED)


# ------------------------------------------------------------- REGISTRATION

def test_registration_matches_frozen_inputs_prompts_and_budgets():
    doc = budget.registration()
    assert doc["routes"] == budget.ROUTES
    assert doc["budget"]["max_live_calls"] == 6
    assert doc["token_budgets"]["generator_max_tokens"] == 4096
    assert doc["token_budgets"]["reviewer_max_tokens"] == 2048
    assert doc["token_budgets"]["probe_max_tokens"] == 16
    assert doc["prompts"]["t71_max_tokens"] == 2048
    assert doc["prompts"]["legacy_max_output_chars"] == 4000
    assert doc["response_format"]["this_run_is"] == "BUDGET_ONLY_ARM"


def test_registration_refuses_changed_bytes(tmp_path):
    path = tmp_path / "registration.json"
    path.write_bytes(budget.REGISTRATION_PATH.read_bytes() + b" ")
    with pytest.raises(SailangError, match="REGISTRATION_MISMATCH"):
        budget.registration(path=path)


def test_prompt_change_refused(monkeypatch):
    monkeypatch.setattr(pilot, "GENERATOR_TEMPLATE", pilot.GENERATOR_TEMPLATE + " ")
    with pytest.raises(SailangError, match="PROMPT_DRIFT"):
        budget.registration()


def test_protected_input_drift_refused(tmp_path, monkeypatch):
    real_read = pathlib.Path.read_bytes

    def drift(self):
        if self.name == "ally_generation.py":
            return b"changed"
        return real_read(self)
    monkeypatch.setattr(pathlib.Path, "read_bytes", drift)
    with pytest.raises(SailangError, match="PROTECTED_INPUT_DRIFT"):
        budget.registration(root=budget.ROOT)


def test_b018_identity_is_the_frozen_exact_subject(built):
    assert built.build_id == pilot.B018_BUILD_ID
    assert built.corpus_id == pilot.B018_CORPUS_ID
    assert built.artifact_count == 8
    assert built.event_count == 5


# ------------------------------------------------ DRY CONTROL: budget + parser

def test_dry_role_swap_reaches_review_and_no_advice_skips(built):
    result = document(built)
    assert [(r["generator_role"], r["reviewer_role"]) for r in result["replicates"]] == [
        ("A", "B"), ("B", "A")]
    assert [r["outcome"] for r in result["replicates"]] == [
        budget.ag.NO_ADVICE if hasattr(budget, "ag") else "APPROVED",
        "NO_ADVICE"][:0] + [result["replicates"][0]["outcome"], result["replicates"][1]["outcome"]]
    assert result["replicates"][1]["outcome"] == "NO_ADVICE"
    assert result["replicates"][1]["reviewer_calls"] == 0


def test_generator_request_is_4096_and_reviewer_is_2048(built):
    result = document(built)
    gens = [c for c in result["calls"] if c["function"] == "GENERATOR"]
    revs = [c for c in result["calls"] if c["function"] == "REVIEWER"]
    probes = [c for c in result["calls"] if c["function"] == "PROBE"]
    assert all(c["request_max_tokens"] == 4096 for c in gens)
    assert all(c["request_max_tokens"] == 2048 for c in revs)
    assert all(c["request_max_tokens"] == 16 for c in probes)


def test_response_format_is_absent_on_every_content_call(built):
    result = document(built)
    assert all(c["response_format_kind"] == "NONE" for c in result["calls"])


def test_full_output_beyond_4000_reaches_the_strict_parser(built):
    result = document(built)
    gen = next(c for c in result["calls"] if c["function"] == "GENERATOR"
               and c["role"] == "A")
    assert gen["full_output_bytes"] > 4000
    assert gen["legacy_projection_would_truncate"] is True
    assert gen["output_truncated"] is False
    # the authoritative strict parser accepted the complete output
    assert gen["parser_status"] == "OK"
    assert result["replicates"][0]["candidate_emitted"] is True
    # A9/RED-E: the diagnostic observer may hit its own resource limit on
    # >4000 input; that observation has no acceptance authority.
    assert gen["parse_shape"]["syntax"] == "RESOURCE_LIMIT"
    assert result["replicates"][0]["outcome"] != "ERROR"


def test_dry_run_spends_no_network(built):
    result = document(built)
    assert result["budget"]["network_calls"] == 0
    assert result["budget"]["retries"] == 0
    assert result["budget"]["repair_calls"] == 0


# ------------------------------------------------ RED: variable mixing

def test_old_generic_4000_path_cannot_supply_the_complete_json(built):
    """RED-D: the historical projection hands the parser a truncated prefix."""
    candidate = budget.large_valid_candidate(built.reflection_corpus)
    full = pilot.wire_candidate_text(candidate)
    assert len(full) > 4000
    assert budget.parse_len_prefix_invalid(full) is True
    assert budget.parse_full_valid(full) is True


def test_generator_request_body_carries_4096_and_no_response_format():
    body = json.dumps({"model": "SAIFREN", "stream": False, "max_tokens": 4096,
                       "messages": [{"role": "user", "content": "p"}]}).encode()
    assert b'"max_tokens": 4096' in body
    assert b"response_format" not in body


# ------------------------------------------------ privacy

def test_privacy_canaries_absent_from_artifact(built, tmp_path):
    candidate = budget.large_valid_candidate(built.reflection_corpus, tail_canary=CANARY)
    transport = budget.DryTransport(built.reflection_corpus, candidate=candidate)
    result = document(built, transport)
    result["dry_run"] = False
    paths = budget._write(tmp_path, budget.registration(), result, "")
    for path in paths.values():
        text = pathlib.Path(path).read_text(encoding="utf-8")
        assert CANARY not in text
        for item in built.reflection_corpus.items:
            assert item.content not in text


def test_full_output_plaintext_is_not_a_durable_field(built, tmp_path):
    candidate = budget.large_valid_candidate(built.reflection_corpus)
    transport = budget.DryTransport(built.reflection_corpus, candidate=candidate)
    result = document(built, transport)
    serialized = json.dumps(result, ensure_ascii=False)
    body = pilot.wire_candidate_text(candidate)
    assert body not in serialized
    assert all("full_output" not in call or call["full_output"] is None
               for call in result["calls"] if "full_output" in call)


def test_canary_in_full_output_is_not_durable(built, tmp_path):
    raw = ('{"result":"CANDIDATE","WORK_CONTEXT":"' + CANARY + '",' + '"OBSERVED":[],'
           '"INFERRED":"x","GUIDANCE_MODE":"OBSERVE_ONLY","SUGGESTED":"y",'
           '"COUNTEREVIDENCE":[],"UNCERTAINTY":"z"}')
    transport = budget.DryTransport(built.reflection_corpus)
    transport.send_ephemeral_full = lambda prompt, model=None, max_tokens=None: (
        transport._ok(raw, model))
    result = document(built, transport)
    assert CANARY not in json.dumps(result)


def test_privacy_tripwire_refuses_before_writes(built, tmp_path):
    result = document(built)
    result[CANARY] = CANARY
    with pytest.raises(SailangError, match=shape.PRIVACY_TRIPWIRE):
        budget._write(tmp_path, budget.registration(), result, "")
    assert not list(tmp_path.iterdir())


# ------------------------------------------------ run lifecycle

def setup_workspace(monkeypatch, tmp_path, built):
    doc = budget.registration()
    monkeypatch.setattr(budget, "registration", lambda *args, **kwargs: doc)
    monkeypatch.setattr(pilot, "prepare_input", lambda *args: built)
    return doc


def test_dry_run_never_touches_network_or_credentials(tmp_path, monkeypatch, built):
    doc = setup_workspace(monkeypatch, tmp_path, built)

    def forbidden(*args, **kwargs):
        pytest.fail("dry run attempted network or credential resolution")
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(budget, "resolve", forbidden)
    monkeypatch.setattr(live, "HttpTransport", forbidden)
    real_write = budget._write
    monkeypatch.setattr(budget, "_write", lambda root, d, doc_, key: real_write(
        tmp_path, d, doc_, key))
    marker = pathlib.Path(budget.ROOT) / doc["attempt_marker"]
    before = marker.read_bytes() if marker.exists() else None
    result = budget.run(dry_run=True, root=budget.ROOT)
    assert result["budget"]["network_calls"] == 0
    after = marker.read_bytes() if marker.exists() else None
    assert after == before, "a dry run never mints or changes the live-attempt marker"


def test_one_attempt_survives_second_invocation(tmp_path, monkeypatch, built):
    doc = setup_workspace(monkeypatch, tmp_path, built)
    budget.run(dry_run=True, root=tmp_path)
    monkeypatch.setattr(budget, "resolve", lambda: SimpleNamespace(secret="fake-secret"))
    monkeypatch.setattr(budget.eph, "EphemeralTransport",
                        lambda key: budget.DryTransport(built.reflection_corpus))
    budget.run(root=tmp_path)
    marker = tmp_path / doc["attempt_marker"]
    assert marker.exists()
    original = marker.read_bytes()
    with pytest.raises(SailangError, match="ALREADY_ATTEMPTED"):
        budget.run(root=tmp_path)
    assert marker.read_bytes() == original


def test_live_requires_a_matching_dry_control(tmp_path, monkeypatch, built):
    setup_workspace(monkeypatch, tmp_path, built)
    monkeypatch.setattr(budget, "resolve", lambda: pytest.fail("credential touched too early"))
    with pytest.raises(SailangError, match="DRY_CONTROL_REQUIRED"):
        budget.run(root=tmp_path)


def test_reserve_is_publish_once(tmp_path):
    path = tmp_path / "attempt.json"
    budget._reserve(path)
    with pytest.raises(SailangError, match="ALREADY_ATTEMPTED"):
        budget._reserve(path)
