"""What a live SAIFREN artifact is entitled to call itself (D-024).

The defect class this module eliminates: **a heterogeneous run read as a run
inside SAIFREN.** Runs 4 and 5 sent one participant through the SAIFREN alias
and put an independently selected catalog model beside it, labelled
``NOT_PROVEN_COMBO_MEMBER``. The label was right and easy to read past: "two
distinct observed participants" is true, and it is not "two SAIFREN members".
The distinction lived in one field of one participant record. Here it is the
first thing an artifact says about itself.

    9router -> SAIRoute -> SAIFREN     the canonical live SAIMAIL lab (D-020)

Classes, derived from membership evidence inside the run and never from
catalog eligibility, a participant label, or an earlier run:

``SAIFREN_INTERNAL``
    Every answering participant is an observed SAIFREN member, and at least two
    distinct members answered.
``SAIFREN_EXTERNAL_COMPARATOR``
    At least one observed member answered, and at least one external live
    participant whose model is not an observed member answered beside it. The
    external participants are comparators, not members.
``SAIFREN_SINGLE_ROUTE``
    Exactly one observed member answered and nothing external did. No
    cross-member claim is available.
``SAIFREN_NOT_OBSERVED``
    Something answered, but no answering participant is an observed member: the
    run pinned catalog models, or the alias answered without reporting which
    model it resolved to.
``NOT_MEASURED``
    Nothing answered.

**Membership evidence** is one thing only: a call in this run that requested
the combo alias and was answered with a reported model other than the alias
itself. The gateway chose that model, so it is a member. A probe that did the
same during discovery counts too. A catalog listing does not, a
``member_status`` field does not, and neither does a model's appearance in an
earlier run.

A sample remains a sample: ``OBSERVED_COMBO_MEMBERS`` is what this run saw, not
what SAIFREN contains, and ``ROSTER_STATUS`` stays ``NOT_OBSERVABLE`` until a
roster is actually read.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Set

RULE = "saifren-experiment-class/1"

SAIFREN_INTERNAL = "SAIFREN_INTERNAL"
SAIFREN_EXTERNAL_COMPARATOR = "SAIFREN_EXTERNAL_COMPARATOR"
SAIFREN_SINGLE_ROUTE = "SAIFREN_SINGLE_ROUTE"
SAIFREN_NOT_OBSERVED = "SAIFREN_NOT_OBSERVED"
NOT_MEASURED = "NOT_MEASURED"
EXPERIMENT_CLASSES = (SAIFREN_INTERNAL, SAIFREN_EXTERNAL_COMPARATOR, SAIFREN_SINGLE_ROUTE,
                      SAIFREN_NOT_OBSERVED, NOT_MEASURED)

ROSTER_OBSERVED = "OBSERVED"
ROSTER_NOT_OBSERVABLE = "NOT_OBSERVABLE"
#: The only population value that means a member list was actually read. No
#: surface in use today produces it.
_ROSTER_READ = "ROSTER_OBSERVED"

#: Each call names the id it requested (every artifact written after D-024).
BASIS_CALL_RECORDS = "CALL_RECORDS"
#: Calls carry no requested id; the run's population record maps each reported
#: model to the participant that was requested for it (runs 4 and 5).
BASIS_POPULATION_RECORD = "POPULATION_RECORD"
#: No population record; the harness block says whether routes were pinned or
#: the alias was sent (runs 1 to 3).
BASIS_HARNESS_ROUTES = "HARNESS_ROUTES"

MEMBER = "OBSERVED_SAIFREN_MEMBER"
EXTERNAL = "EXTERNAL_COMPARATOR"
ALIAS_ONLY = "ALIAS_ONLY_NO_MODEL_REPORTED"

NOTE = ("Membership is sampled through the combo alias, never read from a roster and never "
        "inferred from catalog eligibility. OBSERVED_COMBO_MEMBERS is what this run saw, not "
        "what SAIFREN contains. EXTERNAL_COMPARATORS are live catalog models answering beside "
        "SAIFREN for contrast; nothing in the run shows they are SAIFREN members.")


class UnattributableRun(ValueError):
    """A historical artifact that cannot say which call went through the alias."""


def roster_status(population: Optional[Mapping]) -> Dict[str, str]:
    basis = (population or {}).get("roster_status") or "NO_POPULATION_RECORD"
    return {"roster_status": ROSTER_OBSERVED if basis == _ROSTER_READ else ROSTER_NOT_OBSERVABLE,
            "roster_status_basis": basis}


def classify_calls(combo: str, calls: Iterable[Mapping], population: Optional[Mapping] = None,
                   basis: str = BASIS_CALL_RECORDS) -> dict:
    """The class of one run from its own calls. ``requested_model`` must be set on each call."""
    answered = [c for c in calls
                if c.get("status") == "OK" and isinstance(c.get("reported_model"), str)
                and c.get("reported_model")]
    probe_members: Set[str] = set((population or {}).get("observed_members") or ())
    member_evidence: Dict[str, List[str]] = {}
    alias_only: List[str] = []
    for call in answered:
        if call.get("requested_model") != combo:
            continue
        if call["reported_model"] == combo:
            alias_only.append(call.get("call_id"))
        else:
            member_evidence.setdefault(call["reported_model"], []).append(call.get("call_id"))
    members = set(member_evidence) | probe_members
    participating: Set[str] = set()
    external: Dict[str, List[str]] = {}
    unattributed: Set[str] = set()
    for call in answered:
        model, requested = call["reported_model"], call.get("requested_model")
        if model == combo:
            continue  # the alias echoed back is not a model
        if model in members:
            participating.add(model)
        elif requested is None:
            unattributed.add(model)
        elif requested != combo:
            external.setdefault(model, []).append(call.get("call_id"))
    if not answered:
        experiment_class = NOT_MEASURED
    elif not participating:
        experiment_class = SAIFREN_NOT_OBSERVED
    elif external:
        experiment_class = SAIFREN_EXTERNAL_COMPARATOR
    elif len(participating) >= 2:
        experiment_class = SAIFREN_INTERNAL
    else:
        experiment_class = SAIFREN_SINGLE_ROUTE
    distinct = sorted(participating | set(external) | unattributed)
    return {
        "rule": RULE,
        "experiment_class": experiment_class,
        "combo": combo,
        "observed_combo_members": sorted(members),
        "participating_combo_members": sorted(participating),
        "external_comparators": sorted(external),
        "distinct_reported_models": distinct,
        **roster_status(population),
        "membership_evidence_basis": basis,
        "membership_evidence": {
            "alias_calls": {m: [i for i in ids if i] for m, ids in sorted(member_evidence.items())},
            "membership_probes": sorted(probe_members),
            "alias_only_answers": len(alias_only),
        },
        "unattributed_models": sorted(unattributed),
        "cross_member_claim": experiment_class == SAIFREN_INTERNAL,
        "note": NOTE,
    }


def label(model: Optional[str], klass: Mapping) -> str:
    """How a report names one reported model under this run's class."""
    if not model or model == klass.get("combo"):
        return ALIAS_ONLY
    if model in klass.get("observed_combo_members", ()):
        return MEMBER
    if model in klass.get("external_comparators", ()):
        return EXTERNAL
    return "UNATTRIBUTED"


_DESCRIPTION = {
    MEMBER: "observed SAIFREN member, reached through the alias",
    EXTERNAL: "external comparator, not a SAIFREN member",
    ALIAS_ONLY: "alias only, no model reported",
    "UNATTRIBUTED": "unattributed: not shown to be a member or an external route",
}


def describe(model: Optional[str], klass: Mapping) -> str:
    """The words a report prints beside one reported model. One wording, every report."""
    return _DESCRIPTION[label(model, klass)]


def classify_artifact(artifact: Mapping) -> dict:
    """The class of a stored artifact, on the strongest basis it carries.

    Stored artifacts are never edited (D-022). This reads them as they are and
    says which basis it used, so a historical classification is visibly weaker
    than one computed from per-call request ids.
    """
    harness = artifact.get("harness") or {}
    population = artifact.get("population")
    combo = (population or {}).get("combo") or harness.get("model_alias") or "SAIFREN"
    calls = [c for c in artifact.get("calls") or () if c.get("status") != "NOT_RUN"]
    if calls and all("requested_model" in c for c in calls):
        return classify_calls(combo, calls, population, BASIS_CALL_RECORDS)
    if population is not None:
        by_model = {p.get("reported_model"): p.get("requested")
                    for p in population.get("participants") or () if p.get("reported_model")}
        mapped = [{**c, "requested_model": by_model.get(c.get("reported_model"))} for c in calls]
        return classify_calls(combo, mapped, population, BASIS_POPULATION_RECORD)
    routes = [harness.get("route_a"), harness.get("route_b")]
    if all(r is None for r in routes):
        requested = combo
    elif all(r is not None and r != combo for r in routes):
        requested = "PINNED_CATALOG_ROUTE"
    else:
        raise UnattributableRun(
            "the harness mixed the alias with a pinned route and the calls do not say which "
            "one each call requested; no class can be derived without guessing")
    return classify_calls(combo, [{**c, "requested_model": requested} for c in calls], None,
                          BASIS_HARNESS_ROUTES)
