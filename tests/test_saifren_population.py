"""Where a SAIFREN experiment's participants come from, and what that entitles
an artifact to claim (D-020).

Nothing here touches the network: discovery and every probe are injected.
"""

from __future__ import annotations

import json

import pytest

from lab import saifren_population as pop
from lab import saifren_run as lab

COMBO = "SAIFREN"


def catalog_payload(rows=None):
    rows = rows if rows is not None else [
        {"id": COMBO, "object": "model", "owned_by": "combo"},
        {"id": "SAIOPP", "object": "model", "owned_by": "combo"},
        {"id": "alpha/big", "owned_by": "alpha", "context_length": 1_000_000,
         "capabilities": {"tools": True}},
        {"id": "alpha/small", "owned_by": "alpha", "context_length": 8_000,
         "capabilities": {"tools": True}},
        {"id": "beta/big", "owned_by": "beta", "context_length": 500_000,
         "capabilities": {"tools": True}},
        {"id": "gamma/undescribed", "owned_by": "gamma"},
    ]
    return {"object": "list", "data": rows}


def answered(model, provider=None):
    record = {"output": "OK", "reported_model": model, "finish_reason": "stop"}
    if provider:
        record["provider"] = provider
    return record


def refused(error_class="HTTPError", error="HTTP 503 upstream overloaded"):
    return {"error_class": error_class, "error": error}


class Probes:
    """Answers per requested model id, recording the exact order of requests."""

    def __init__(self, answers, default=None):
        self.answers = dict(answers)
        self.default = default if default is not None else refused()
        self.requested = []

    def __call__(self, model):
        self.requested.append(model)
        answer = self.answers.get(model, self.default)
        return answer(model) if callable(answer) else answer


def resolved(answers, default=None, rows=None, **kwargs):
    probes = Probes(answers, default)
    population = pop.resolve_population(
        COMBO, lambda: catalog_payload(rows), probes, "2026-09-17T00:00:00Z", **kwargs)
    return population, probes


# ------------------------------------------------------------------ discovery


def test_the_catalog_snapshot_has_an_identity_and_no_capability_payload():
    catalog = pop.parse_catalog(catalog_payload(), "2026-09-17T00:00:00Z")
    assert catalog.digest.startswith("sha256:")
    assert catalog.combos == ("SAIFREN", "SAIOPP")
    assert len(catalog.entries) == 6
    assert len(catalog.models()) == 4
    entry = next(e for e in catalog.entries if e.id == "alpha/big")
    assert entry.capabilities_stated is True and entry.context_length == 1_000_000
    assert not hasattr(entry, "capabilities"), "capability detail is a flag, not stored payload"


def test_the_digest_changes_when_the_catalog_changes():
    first = pop.parse_catalog(catalog_payload(), "t")
    same = pop.parse_catalog(catalog_payload(), "later")
    extra = pop.parse_catalog(
        catalog_payload(catalog_payload()["data"] + [{"id": "delta/new", "owned_by": "delta"}]),
        "t")
    assert first.digest == same.digest, "the identity is the catalog, not the clock"
    assert first.digest != extra.digest


def test_a_discovery_body_without_a_model_list_is_refused():
    with pytest.raises(ValueError):
        pop.parse_catalog({"object": "list"}, "t")


# ----------------------------------------------------------------- membership


def test_the_roster_is_never_claimed_from_the_documented_surface():
    population, _ = resolved({COMBO: answered("vendor/one")})
    assert population.roster_status == pop.ROSTER_NOT_EXPOSED
    assert population.discovery["roster_field_present"] is False
    assert population.membership_source == pop.COMBO_ALIAS_SAMPLE
    assert any("ALIAS_SAMPLE_IS_NOT_A_ROSTER" in note for note in population.notes)


def test_an_alias_sample_records_every_distinct_member_it_saw():
    seen = iter(["vendor/one", "vendor/two"])
    population, probes = resolved({COMBO: lambda model: answered(next(seen))})
    assert population.observed_members == ("vendor/one", "vendor/two")
    assert population.membership_digest.startswith("sha256:")
    assert probes.requested[:2] == [COMBO, COMBO]


def test_an_unobservable_membership_says_so_instead_of_guessing():
    population, _ = resolved({}, default=refused())
    assert population.membership_source == pop.MEMBERSHIP_NOT_OBSERVABLE
    assert population.observed_members == ()
    assert population.membership_digest == ""
    assert any(pop.MEMBERSHIP_NOT_OBSERVABLE in note for note in population.notes)
    assert population.discovery["alias_transport_errors"], "the refusal is recorded, not hidden"


def test_a_combo_missing_from_the_catalog_is_recorded():
    rows = [r for r in catalog_payload()["data"] if r["id"] != COMBO]
    population, _ = resolved({COMBO: answered("vendor/one")}, rows=rows)
    assert any("COMBO_ABSENT_FROM_CATALOG" in note for note in population.notes)


def test_a_dry_run_population_makes_no_claim():
    population = pop.offline_population(COMBO, "t", "a dry run makes no call")
    assert population.membership_source == pop.MEMBERSHIP_NOT_OBSERVABLE
    assert population.participants == () and population.heterogeneous is False
    assert population.discovery["queried"] is False


# ------------------------------------------------------------------ selection


def test_role_a_is_the_alias_and_is_an_observed_member():
    population, _ = resolved({COMBO: answered("vendor/one"), "alpha/big": answered("alpha/one")})
    role_a = population.participants[0]
    assert role_a.role == "A" and role_a.requested == COMBO
    assert role_a.reported_model == "vendor/one"
    assert role_a.member_status == pop.OBSERVED_COMBO_MEMBER


def test_role_b_comes_from_the_catalog_and_is_not_claimed_as_a_member():
    population, _ = resolved({COMBO: answered("vendor/one"), "alpha/big": answered("alpha/one")})
    role_b = population.participants[1]
    assert role_b.role == "B" and role_b.requested == "alpha/big"
    assert role_b.reported_model == "alpha/one"
    assert role_b.member_status == pop.NOT_PROVEN_COMBO_MEMBER
    assert role_b.source == "CATALOG_ELIGIBLE"
    assert population.heterogeneous is True


def _code_strings(path):
    """Every string literal in a module except its docstrings.

    Prose may name the old pinned routes -- that is what the defect was. Code
    may not: a future change to SAIFREN must not need an edit here (B2).
    """
    import ast

    tree = ast.parse(open(path, encoding="utf-8").read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if not body or not isinstance(body[0], ast.Expr):
                continue
            first = body[0].value
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                docstrings.add(id(first))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]


def test_no_model_identifier_is_a_source_constant():
    for path in (pop.__file__, lab.__file__):
        joined = " ".join(_code_strings(path)).lower()
        for pinned in ("deepseek", "nemotron", "nvidia", "gemini", "minimax", "openrouter"):
            assert pinned not in joined, f"{path} pins the model family {pinned!r} in code"


def test_candidates_are_one_per_namespace_best_first():
    catalog = pop.parse_catalog(catalog_payload(), "t")
    ranked = [e.id for e in pop.rank_candidates(catalog)]
    assert ranked == ["alpha/big", "beta/big", "gamma/undescribed"]
    assert "alpha/small" not in ranked, "a refusing namespace refuses for all its models"


def test_an_operator_preference_reorders_without_a_source_edit():
    catalog = pop.parse_catalog(catalog_payload(), "t")
    ranked = [e.id for e in pop.rank_candidates(catalog, prefer=("beta",))]
    assert ranked[0] == "beta/big"


def test_the_preference_reaches_selection_and_not_only_the_ranker():
    """An option accepted and then dropped is worse than one that never existed."""
    population, probes = resolved({COMBO: answered("vendor/one"),
                                   "alpha/big": answered("alpha/one"),
                                   "beta/big": answered("beta/one")},
                                  prefer=("beta",))
    assert probes.requested[2] == "beta/big", "the preferred namespace is probed first"
    assert population.participants[1].requested == "beta/big"


def test_the_preference_is_read_from_the_environment(monkeypatch):
    monkeypatch.setenv(pop.PREFER_ENV, "gamma")
    catalog = pop.parse_catalog(catalog_payload(), "t")
    assert pop.rank_candidates(catalog)[0].id == "gamma/undescribed"


def test_role_as_model_is_never_offered_back_as_a_candidate():
    catalog = pop.parse_catalog(catalog_payload(), "t")
    ranked = [e.id for e in pop.rank_candidates(catalog, exclude_ids=("alpha/big",))]
    assert "alpha/big" not in ranked
    assert "alpha/small" in ranked, "the namespace keeps its next-best entry"
    assert ranked[0] == "beta/big", "ranking is by the declared key, not by namespace order"


# -------------------------------------------------------- replacement policy


def test_a_refusing_candidate_is_replaced_by_the_next_one():
    population, probes = resolved({COMBO: answered("vendor/one"),
                                   "alpha/big": refused("HTTPError", "HTTP 429 quota"),
                                   "beta/big": answered("beta/one")})
    assert [p.requested for p in population.participants] == [COMBO, "beta/big"]
    rejected = population.rejected_candidates
    assert rejected[0]["requested"] == "alpha/big" and rejected[0]["reason"] == "TRANSPORT"
    assert "429" in rejected[0]["error"]
    assert probes.requested == [COMBO, COMBO, "alpha/big", "beta/big"]


def test_a_candidate_that_answers_as_role_a_is_not_a_second_participant():
    population, _ = resolved({COMBO: answered("vendor/one"),
                              "alpha/big": answered("vendor/one"),
                              "beta/big": answered("beta/one")})
    assert [p.reported_model for p in population.participants] == ["vendor/one", "beta/one"]
    assert population.rejected_candidates[0]["reason"] == "SAME_REPORTED_MODEL_AS_ROLE_A"


def test_the_probe_budget_is_declared_and_bounded():
    population, probes = resolved({COMBO: answered("vendor/one")}, default=refused(),
                                  max_selection_probes=2)
    assert population.selection_probes_used == 2
    assert probes.requested.count(COMBO) == pop.MEMBERSHIP_PROBES
    assert len(population.participants) == 1
    assert any("HETEROGENEOUS_NOT_ACHIEVED" in note for note in population.notes)
    assert population.heterogeneous is False


def test_a_content_answer_never_triggers_a_retry():
    """Replacement is a transport rule. It may not shop for a preferred answer."""
    population, probes = resolved({COMBO: answered("vendor/one"),
                                   "alpha/big": answered("alpha/one")})
    assert probes.requested.count("alpha/big") == 1
    assert len(population.participants) == 2


# ------------------------------------------------------------- provenance


def test_the_record_carries_everything_needed_to_reproduce_the_population():
    population, _ = resolved({COMBO: answered("vendor/one"),
                              "alpha/big": answered("alpha/one", provider="Alpha Inc")})
    record = population.as_record()
    for key in ("combo", "membership_observed_at", "membership_source", "roster_status",
                "observed_members", "membership_digest", "catalog_size", "catalog_digest",
                "selection_rule", "replacement_policy", "participants",
                "heterogeneous_participants", "notes"):
        assert key in record, key
    assert record["combo"] == COMBO
    assert record["selection_rule"] == pop.SELECTION_RULE
    assert record["replacement_policy"] == pop.REPLACEMENT_POLICY
    assert record["catalog_size"] == 6
    assert json.dumps(record), "the record is serializable as it stands"


def test_provider_is_kept_only_when_the_gateway_states_it():
    population, _ = resolved({COMBO: answered("vendor/one"),
                              "alpha/big": answered("alpha/one", provider="Alpha Inc")})
    role_a, role_b = population.participants
    assert role_a.provider is None, "an alias answer that states nothing claims nothing"
    assert role_b.provider == "Alpha Inc"
    assert role_b.catalog_namespace == "alpha"


# --------------------------------------------------------- inside the harness


def test_the_harness_sends_the_resolved_participants_not_a_constant():
    population, _ = resolved({COMBO: answered("vendor/one"), "alpha/big": answered("alpha/one")})
    assert lab.routes_of(population) == (COMBO, "alpha/big")


def test_a_run_without_participants_sends_the_alias_and_claims_nothing():
    population = pop.offline_population(COMBO, "t", "discovery was not requested")
    assert lab.routes_of(population) == (None, None)
    assert population.as_record()["heterogeneous_participants"] is False


def test_one_resolved_participant_is_used_for_both_roles():
    population, _ = resolved({COMBO: answered("vendor/one")}, default=refused(),
                             max_selection_probes=1)
    assert lab.routes_of(population) == (COMBO, COMBO)
