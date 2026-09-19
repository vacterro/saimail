"""R1 interest filter: decide what to open, from typed R1 information only.

The selector sees a ``TriageView`` and a declared ``Interest``. It does not see
the canonical record, the claim prose, the evidence body, or any hidden ground
truth, and it never calls a model. It is a deterministic function over the R1
slots, which is the whole point: scanning a mailbox must cost no inference.

Four outcomes:

``IGNORE``    declared noise for this reader policy
``DEFER``     not worth context now, kept as potentially interesting later
``OPEN_R2``   fetch the semantic summary
``OPEN_R3``   fetch the canonical record

``DEFER`` exists because the founding idea includes useful communication with no
immediate task attached. "Known and not relevant right now" must not collapse
into "discarded forever", or a mailbox can only ever carry what somebody
already asked for. No persistence and no TTL here: this defines classification
and nothing else.

``PROMOTE`` is deliberately absent.

The rule order below is declared before any measurement and is not tuned to a
corpus. The asymmetry that shapes it: **a false ignore is far more expensive
than a false open.** A filter that saves context by silently dropping relevant
discoveries has not saved anything, it has lost them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Tuple

from sailang.frame import TriageView

IGNORE = "IGNORE"
DEFER = "DEFER"
OPEN_R2 = "OPEN_R2"
OPEN_R3 = "OPEN_R3"
VERDICTS = (IGNORE, DEFER, OPEN_R2, OPEN_R3)

#: Resolution ordering: how much of the message a verdict pulls into context.
_DEPTH = {IGNORE: 0, DEFER: 1, OPEN_R2: 2, OPEN_R3: 3}


def depth(verdict: str) -> int:
    return _DEPTH[verdict]


@dataclass(frozen=True)
class Interest:
    """What this reader cares about. Declared, never inferred from traffic."""

    atoms: FrozenSet[str]
    subjects: FrozenSet[str] = field(default_factory=frozenset)
    #: canonical identities this reader is watching. A relation pointing at one
    #: matters even when the message vocabulary looks unrelated.
    watched: FrozenSet[str] = field(default_factory=frozenset)
    #: atoms this reader has DECLARED to be operational noise. Receiver-owned,
    #: because a sender scoring its own message is an authority channel with no
    #: evidence under it.
    noise: FrozenSet[str] = field(default_factory=frozenset)

    @classmethod
    def of(cls, atoms, subjects=(), watched=(), noise=()) -> "Interest":
        return cls(atoms=frozenset(atoms), subjects=frozenset(subjects),
                   watched=frozenset(watched), noise=frozenset(noise))


@dataclass(frozen=True)
class Decision:
    verdict: str
    rule: str
    reason: str


#: The rules, in order. First match wins. Declared here, in the source, above
#: every measurement that uses them.
RULES = (
    ("R0-WATCHED", "a relation points at a record this reader watches, whatever the vocabulary"),
    ("R1-UNRESOLVED-RELATION", "a relation names a target the container never declared"),
    ("R2-UNKNOWN", "a wire token this profile has no atom for: unreadable, so never dropped"),
    ("R3-OPEN-RECORD", "the frame could not carry the claim at all"),
    ("R4-NOISE", "every atom is on the declared noise list for this reader"),
    ("R5-NOT-NOW", "known, readable, not relevant right now: kept rather than discarded"),
    ("R6-CONTRADICTION", "relevant, and it refutes or conflicts with something"),
    ("R7-ACTIONABLE", "relevant, evidence attached, and at or above the supported rung"),
    ("R8-RELEVANT", "relevant but not yet actionable"),
)

_ACTIONABLE_RUNGS = frozenset({"U2", "U3", "U4"})


def select(view: TriageView, interest: Interest) -> Decision:
    """Decide from R1 alone. Deterministic, total, and model-free."""
    if not isinstance(view, TriageView):
        raise TypeError("the selector reads a TriageView and nothing else")

    hits = [cid for _, cid in view.relation_targets if cid in interest.watched]
    if hits:
        return Decision(OPEN_R3, "R0-WATCHED",
                        f"a relation points at watched record {hits[0][:19]}")
    if view.unresolved_aliases:
        return Decision(OPEN_R2, "R1-UNRESOLVED-RELATION",
                        f"relation target {list(view.unresolved_aliases)} was never declared")
    if view.has_unknown_atoms:
        return Decision(OPEN_R2, "R2-UNKNOWN",
                        f"unknown wire tokens {list(view.claim_unknown_wires)}")
    if view.claim_open_record:
        return Decision(OPEN_R2, "R3-OPEN-RECORD", "claim not representable at R1")

    relevant_atoms = tuple(a for a in view.claim_atoms if a in interest.atoms)
    subject_relevant = view.subject is not None and view.subject in interest.subjects
    if not relevant_atoms and not subject_relevant:
        if view.claim_atoms and all(a in interest.noise for a in view.claim_atoms):
            return Decision(IGNORE, "R4-NOISE",
                            f"atoms {list(view.claim_atoms)} are on the declared noise list")
        return Decision(DEFER, "R5-NOT-NOW",
                        f"atoms {list(view.claim_atoms)} are readable and not relevant now")

    if view.refutes or view.conflict:
        return Decision(OPEN_R3, "R6-CONTRADICTION",
                        "relevant and carries a refutation or a conflict")
    if view.has_evidence and view.status in _ACTIONABLE_RUNGS:
        return Decision(OPEN_R3, "R7-ACTIONABLE",
                        f"relevant, evidence attached, rung {view.status}")
    return Decision(OPEN_R2, "R8-RELEVANT",
                    f"relevant via {list(relevant_atoms) or 'subject'}, not yet actionable")


def select_all(views, interest: Interest) -> Tuple[Decision, ...]:
    return tuple(select(view, interest) for view in views)
