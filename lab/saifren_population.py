"""Who actually answers a SAIFREN experiment, discovered rather than declared.

The defect class this module eliminates: **two model identifiers pinned in
source code, presented as a combo.** A harness that sends
``goat/deepseek/deepseek-v4-flash`` and ``openrouter/nvidia/...`` proves that
two models behave differently. It proves nothing about SAIFREN, and it goes
stale the moment somebody edits the combo — silently, because nothing in the
artifact says which population was tested.

So participants are resolved at run time from what the gateway will actually
show, and every artifact records how they were found (D-020):

    9router  ->  SAIRoute  ->  SAIFREN  ->  role A: the member the alias resolves to
                                        ->  role B: an external catalog comparator

Only role A is a SAIFREN participant. Role B is chosen from the eligible catalog
for contrast and is never described as a member; a run with this shape is
``SAIFREN_EXTERNAL_COMPARATOR``, not an experiment inside SAIFREN (D-024).

What the authorized read-only surface does and does not give
-----------------------------------------------------------

``GET /v1/models`` is the documented OpenAI-compatible discovery surface. It
lists the combo (``owned_by: "combo"``) and the full eligible catalog. It does
**not** carry a member list, and the administrative surface that might is not
reachable with the SAIRoute credential. So the roster is recorded as
``ROSTER_NOT_EXPOSED`` and membership is *sampled* instead: a bounded number of
calls to the combo alias, each of which the gateway resolves to a concrete
model and reports back. Every distinct model reported that way is an observed
member, because the gateway itself chose it.

A sample is not a roster, and this module never pretends otherwise. A sample of
``n`` cannot distinguish a one-member combo from a combo with a deterministic
primary, and :data:`MEMBERSHIP_NOT_OBSERVABLE` / ``roster_status`` say which
claim the artifact is entitled to.

Selection rule ``saifren-selection/1``, declared here and before any run:

1. Role A is the combo alias itself. Whatever the gateway resolves it to is an
   observed SAIFREN member, recorded as reported.
2. Role B is drawn from the observed catalog, never from a constant: the
   highest-ranked entry of each catalog namespace, ranked by *capabilities
   stated first*, then larger stated context length, then model id ascending,
   with an optional operator preference from ``SAIFREN_CANDIDATE_PREFER``.
3. A candidate becomes a participant only after one small live probe answers
   **and** reports a model different from role A's. It is labelled
   ``NOT_PROVEN_COMBO_MEMBER``, because an unobservable roster cannot be
   claimed, and the run it joins is an external comparator run.

Replacement policy ``saifren-replacement/1``, declared here and before any run:
a candidate that fails at the transport (HTTP error, timeout, empty output) is
replaced by the next ranked candidate, at most
:data:`MAX_SELECTION_PROBES` probes in total, all spent from the same call
budget. It fires only while resolving participants. It never fires during the
experiment, and no answer's *content* ever triggers a retry.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

#: The documented read-only discovery surface.
DISCOVERY_PATH = "/v1/models"
#: ``owned_by`` value that marks a catalog entry as a combo rather than a model.
COMBO_OWNER = "combo"

SELECTION_RULE = "saifren-selection/1"
REPLACEMENT_POLICY = "saifren-replacement/1"

#: Calls spent sampling the combo alias. Small on purpose: this measures whether
#: repeated resolution is stable, it does not enumerate a roster.
MEMBERSHIP_PROBES = 2
#: Hard cap on candidate probes while resolving role B.
MAX_SELECTION_PROBES = 6
#: Calls a discovering run may spend before the experiment starts. Declared so
#: a plan can be refused *before* the first call rather than running into a
#: spent budget half way through and calling the remainder an error.
DISCOVERY_RESERVE = MEMBERSHIP_PROBES + MAX_SELECTION_PROBES
#: Operator steering, so a change to the population never needs a source edit.
PREFER_ENV = "SAIFREN_CANDIDATE_PREFER"

ROSTER_NOT_EXPOSED = "ROSTER_NOT_EXPOSED"
MEMBERSHIP_NOT_OBSERVABLE = "SAIFREN_MEMBERSHIP_NOT_OBSERVABLE"
COMBO_ALIAS_SAMPLE = "COMBO_ALIAS_SAMPLE"

OBSERVED_COMBO_MEMBER = "OBSERVED_COMBO_MEMBER"
NOT_PROVEN_COMBO_MEMBER = "NOT_PROVEN_COMBO_MEMBER"

#: The shortest prompt that still forces a completion, used for every probe.
PROBE_PROMPT = "Reply with the single word OK."


def _digest(parts: Sequence[str]) -> str:
    joined = "\n".join(parts).encode("utf-8")
    return "sha256:" + hashlib.sha256(joined).hexdigest()


@dataclass(frozen=True)
class CatalogEntry:
    """One non-secret catalog row. Capability detail is kept only as a flag."""

    id: str
    owned_by: Optional[str]
    context_length: Optional[int]
    capabilities_stated: bool

    @property
    def namespace(self) -> Optional[str]:
        return self.owned_by


@dataclass(frozen=True)
class Catalog:
    entries: Tuple[CatalogEntry, ...]
    digest: str
    observed_at: str
    combos: Tuple[str, ...]

    def has_combo(self, name: str) -> bool:
        return name in self.combos

    def models(self) -> Tuple[CatalogEntry, ...]:
        return tuple(e for e in self.entries if e.owned_by != COMBO_OWNER)


@dataclass(frozen=True)
class Participant:
    """One resolved experiment participant, with how it was found."""

    role: str
    #: the model identifier the harness sends
    requested: str
    #: the model identifier the gateway reported for it
    reported_model: Optional[str]
    #: OBSERVED_COMBO_MEMBER or NOT_PROVEN_COMBO_MEMBER -- never a guess
    member_status: str
    #: COMBO_ALIAS or CATALOG_ELIGIBLE
    source: str
    #: stated by the gateway only; a model id prefix is a namespace, not a provider
    provider: Optional[str] = None
    catalog_namespace: Optional[str] = None

    def as_record(self) -> dict:
        return {"role": self.role, "requested": self.requested,
                "reported_model": self.reported_model, "member_status": self.member_status,
                "source": self.source, "provider": self.provider,
                "catalog_namespace": self.catalog_namespace}


@dataclass
class Population:
    """Everything an artifact needs to say which population was tested."""

    combo: str
    observed_at: str
    membership_source: str
    roster_status: str
    observed_members: Tuple[str, ...] = ()
    catalog_size: int = 0
    catalog_digest: str = ""
    membership_digest: str = ""
    participants: Tuple[Participant, ...] = ()
    probes_used: int = 0
    selection_probes_used: int = 0
    rejected_candidates: Tuple[dict, ...] = ()
    notes: Tuple[str, ...] = ()
    discovery: dict = field(default_factory=dict)

    @property
    def heterogeneous(self) -> bool:
        seen = [p.reported_model for p in self.participants if p.reported_model]
        return len(set(seen)) >= 2

    def as_record(self) -> dict:
        return {
            "combo": self.combo,
            "membership_observed_at": self.observed_at,
            "membership_source": self.membership_source,
            "roster_status": self.roster_status,
            "observed_members": list(self.observed_members),
            "membership_digest": self.membership_digest,
            "catalog_size": self.catalog_size,
            "catalog_digest": self.catalog_digest,
            "discovery": dict(self.discovery),
            "selection_rule": SELECTION_RULE,
            "replacement_policy": REPLACEMENT_POLICY,
            "membership_probes_used": self.probes_used,
            "selection_probes_used": self.selection_probes_used,
            "participants": [p.as_record() for p in self.participants],
            "rejected_candidates": [dict(r) for r in self.rejected_candidates],
            "heterogeneous_participants": self.heterogeneous,
            "notes": list(self.notes),
        }


# ------------------------------------------------------------------ discovery


def parse_catalog(payload: Mapping, observed_at: str) -> Catalog:
    """Reduce a ``/v1/models`` body to non-secret rows plus a snapshot identity.

    The digest covers ``id|owned_by`` for every row, sorted, so two runs against
    the same catalog carry the same identity and a changed catalog is visible
    without storing the catalog itself.
    """
    rows = payload.get("data") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("the discovery surface returned no model list")
    entries: List[CatalogEntry] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str):
            continue
        owned_by = row.get("owned_by") if isinstance(row.get("owned_by"), str) else None
        context = row.get("context_length")
        entries.append(CatalogEntry(
            id=row["id"], owned_by=owned_by,
            context_length=context if isinstance(context, int) else None,
            capabilities_stated=isinstance(row.get("capabilities"), dict)))
    combos = tuple(sorted(e.id for e in entries if e.owned_by == COMBO_OWNER))
    digest = _digest(sorted(f"{e.id}|{e.owned_by}" for e in entries))
    return Catalog(entries=tuple(entries), digest=digest, observed_at=observed_at,
                   combos=combos)


def _prefer_terms(prefer: Optional[Sequence[str]] = None) -> Tuple[str, ...]:
    if prefer is None:
        raw = os.environ.get(PREFER_ENV, "")
        prefer = [p.strip() for p in raw.split(",")]
    return tuple(p.lower() for p in prefer if p and p.strip())


def rank_candidates(catalog: Catalog, exclude_ids: Sequence[str] = (),
                    prefer: Optional[Sequence[str]] = None) -> Tuple[CatalogEntry, ...]:
    """The declared candidate order: one entry per namespace, best first.

    One per namespace on purpose. A namespace that refuses (quota, auth, a dead
    upstream) refuses for all of its models, so walking twenty siblings spends
    the whole probe budget learning one fact.
    """
    terms = _prefer_terms(prefer)
    excluded = {e for e in exclude_ids if e}

    def sort_key(entry: CatalogEntry):
        preferred = not any(t in entry.id.lower() or t == (entry.owned_by or "").lower()
                            for t in terms) if terms else True
        return (preferred, not entry.capabilities_stated,
                -(entry.context_length or 0), entry.id)

    best: Dict[Optional[str], CatalogEntry] = {}
    for entry in sorted(catalog.models(), key=sort_key):
        if entry.id in excluded:
            continue
        best.setdefault(entry.owned_by, entry)
    return tuple(sorted(best.values(), key=sort_key))


# ----------------------------------------------------------------- membership


def _reported(result: Optional[Mapping]) -> Optional[str]:
    if not isinstance(result, Mapping) or result.get("error_class"):
        return None
    model = result.get("reported_model")
    return model if isinstance(model, str) and model else None


def observe_membership(combo: str, catalog: Catalog,
                       probe: Callable[[str], dict],
                       probes: int = MEMBERSHIP_PROBES) -> Population:
    """Sample the combo alias and record exactly what that entitles us to say."""
    notes: List[str] = []
    if not catalog.has_combo(combo):
        notes.append(f"COMBO_ABSENT_FROM_CATALOG: {combo} is not listed by {DISCOVERY_PATH}")

    members: List[str] = []
    transport_errors: List[dict] = []
    used = 0
    for _ in range(max(0, probes)):
        result = probe(combo)
        used += 1
        reported = _reported(result)
        if reported is None:
            transport_errors.append({
                "requested": combo,
                "error_class": (result or {}).get("error_class") or "NoReportedModel",
                "error": str((result or {}).get("error") or "")[:240]})
            continue
        if reported not in members:
            members.append(reported)

    if members:
        source = COMBO_ALIAS_SAMPLE
        notes.append(
            f"ALIAS_SAMPLE_IS_NOT_A_ROSTER: {used} call(s) to the alias observed "
            f"{len(members)} distinct member(s); a sample of this size cannot tell a "
            "one-member combo from a combo with a deterministic primary")
    else:
        source = MEMBERSHIP_NOT_OBSERVABLE
        notes.append(f"{MEMBERSHIP_NOT_OBSERVABLE}: neither a roster surface nor an alias "
                     "sample produced a member; no claim is made about current membership")

    return Population(
        combo=combo,
        observed_at=catalog.observed_at,
        membership_source=source,
        roster_status=ROSTER_NOT_EXPOSED,
        observed_members=tuple(members),
        catalog_size=len(catalog.entries),
        catalog_digest=catalog.digest,
        membership_digest=_digest(sorted(members)) if members else "",
        probes_used=used,
        notes=tuple(notes),
        discovery={"surface": DISCOVERY_PATH, "combos_listed": list(catalog.combos),
                   "roster_field_present": False,
                   "alias_transport_errors": transport_errors},
    )


def select_participants(population: Population, catalog: Catalog,
                        probe: Callable[[str], dict],
                        max_probes: int = MAX_SELECTION_PROBES,
                        prefer: Optional[Sequence[str]] = None) -> Population:
    """Resolve roles A and B under ``saifren-selection/1``.

    Role A is the alias and needs no probe: the membership sample already
    observed it. Role B costs one probe per candidate, bounded by
    ``max_probes``, and is accepted only when it answers with a model different
    from role A's.
    """
    notes = list(population.notes)
    participants: List[Participant] = []
    rejected: List[dict] = []
    spent = 0

    member_a = population.observed_members[0] if population.observed_members else None
    if member_a is not None:
        participants.append(Participant(
            role="A", requested=population.combo, reported_model=member_a,
            member_status=OBSERVED_COMBO_MEMBER, source="COMBO_ALIAS"))
    else:
        notes.append("ROLE_A_UNRESOLVED: the combo alias reported no model, so no participant "
                     "can be described as an observed member")

    candidates = rank_candidates(catalog, exclude_ids=(member_a,) if member_a else (),
                                 prefer=prefer)
    for entry in candidates:
        if len(participants) >= 2 or spent >= max_probes:
            break
        result = probe(entry.id)
        spent += 1
        reported = _reported(result)
        if reported is None:
            rejected.append({"requested": entry.id, "namespace": entry.owned_by,
                             "reason": "TRANSPORT",
                             "error_class": (result or {}).get("error_class") or "Unknown",
                             "error": str((result or {}).get("error") or "")[:240]})
            continue
        if member_a is not None and reported == member_a:
            rejected.append({"requested": entry.id, "namespace": entry.owned_by,
                             "reason": "SAME_REPORTED_MODEL_AS_ROLE_A",
                             "reported_model": reported})
            continue
        provider = result.get("provider") if isinstance(result, Mapping) else None
        participants.append(Participant(
            role="B" if participants else "A", requested=entry.id, reported_model=reported,
            member_status=NOT_PROVEN_COMBO_MEMBER, source="CATALOG_ELIGIBLE",
            provider=provider if isinstance(provider, str) and provider else None,
            catalog_namespace=entry.owned_by))

    if len(participants) < 2:
        notes.append(
            f"HETEROGENEOUS_NOT_ACHIEVED: {len(participants)} participant(s) resolved within "
            f"{spent} selection probe(s) of {max_probes}; a two-participant unit cannot claim "
            "distinct observed participants in this run")

    population.participants = tuple(participants)
    population.selection_probes_used = spent
    population.rejected_candidates = tuple(rejected)
    population.notes = tuple(notes)
    return population


def resolve_population(combo: str, fetch_catalog: Callable[[], Mapping],
                       probe: Callable[[str], dict], observed_at: str,
                       membership_probes: int = MEMBERSHIP_PROBES,
                       max_selection_probes: int = MAX_SELECTION_PROBES,
                       prefer: Optional[Sequence[str]] = None) -> Population:
    """Discovery, membership sampling and selection, in the declared order."""
    catalog = parse_catalog(fetch_catalog(), observed_at)
    population = observe_membership(combo, catalog, probe, probes=membership_probes)
    return select_participants(population, catalog, probe,
                               max_probes=max_selection_probes, prefer=prefer)


def offline_population(combo: str, observed_at: str, reason: str) -> Population:
    """The population record a dry run is entitled to: no calls, no claims."""
    return Population(
        combo=combo, observed_at=observed_at,
        membership_source=MEMBERSHIP_NOT_OBSERVABLE,
        roster_status=ROSTER_NOT_EXPOSED,
        notes=(f"{MEMBERSHIP_NOT_OBSERVABLE}: {reason}",),
        discovery={"surface": DISCOVERY_PATH, "queried": False},
    )
