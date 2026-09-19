"""Selection corpus: messages built to stress an R1 filter, with declared truth.

``truth`` is what a reader who already knew everything would have done. It is
written from the reader's point of view and deliberately NOT derived from the
selector's rules — otherwise the experiment would be the filter grading its own
homework. Where the two disagree, that disagreement is the measurement.

The declared interest below is fixed before the run: an agent working on the
queue / retry / duplicate-execution area.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List

from saimail.selector import DEFER, IGNORE, OPEN_R2, OPEN_R3, Interest

WATCHED = "sha256:" + __import__("hashlib").sha256(b"watched-record").hexdigest()

INTEREST = Interest.of(
    atoms={"QUEUE_OWNERSHIP_STALE", "RETRY", "DUPLICATE_EXECUTION",
           "DEADLOCK", "CONCURRENCY", "RECOVERY"},
    subjects={"queue", "recovery"},
    #: one canonical record this reader is watching
    watched={WATCHED},
    #: declared by the reader, never scored by a sender
    noise={"CHECKPOINT", "TIMESTAMP", "METADATA"},
)

T = "2026-09-17T08:41:00Z"


def ev(tag: str) -> str:
    return "sha256:" + hashlib.sha256(tag.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Pick:
    name: str
    klass: str
    fields: dict
    truth: str
    why: str


CASES: List[Pick] = []


def add(name, klass, truth, why, **fields):
    CASES.append(Pick(name=name, klass=klass, fields=fields, truth=truth, why=why))


def F(claim, subj="queue", ev_ref=None, status="U2", **extra):
    base = dict(KIND="F", SRC="AGENT:a17", SUBJ=subj, CLAIM=claim, TYPE="INT",
                EV=ev_ref or "0", STATUS=status, CREATED=T)
    base.update(extra)
    return base


# ------------------------------------------------ relevant known atoms

add("rel-1", "relevant_known", OPEN_R3, "a supported duplicate-execution finding is the reader's core topic",
    **F("QUEUE_OWNERSHIP_STALE>RETRY>DUPLICATE_EXECUTION", ev_ref=ev("r1")))
add("rel-2", "relevant_known", OPEN_R3, "deadlock under concurrency on the queue, with evidence",
    **F("CONCURRENCY>QUEUE_OWNERSHIP_STALE>DEADLOCK", ev_ref=ev("r2"), status="U3"))
add("rel-3", "relevant_known", OPEN_R2, "relevant but unverified: worth a summary, not the record yet",
    **F("RECOVERY>QUEUE_OWNERSHIP_STALE", status="U1"))
add("rel-4", "relevant_known", OPEN_R3, "retry causing duplicates, verified",
    **F("RETRY>DUPLICATE_EXECUTION", subj="recovery", ev_ref=ev("r4"), status="U4"))
add("rel-5", "relevant_known", OPEN_R2, "relevant topic, no evidence attached",
    **F("QUEUE_OWNERSHIP_STALE>RECOVERY", status="U0"))

# ------------------------------------------------ irrelevant known atoms

add("irr-1", "irrelevant_known", DEFER, "signature ordering is another team's problem",
    **F("SIGNATURE>ENVELOPE", subj="envelope", ev_ref=ev("i1")))
add("irr-2", "irrelevant_known", DEFER, "configuration regression, unrelated subsystem",
    **F("CONFIGURATION>REGRESSION", subj="loader", ev_ref=ev("i2")))
add("irr-3", "irrelevant_known", DEFER, "promotion gate semantics, not this reader",
    **F("PROMOTION>EVIDENCE", subj="promotion", ev_ref=ev("i3")))
add("irr-4", "operational_noise", IGNORE, "checkpoint performance elsewhere",
    **F("CHECKPOINT>PERFORMANCE", subj="session", ev_ref=ev("i4")))
add("irr-5", "operational_noise", IGNORE, "database metadata, different area",
    **F("DATABASE>METADATA>TIMESTAMP", subj="db", ev_ref=ev("i5")))

# ------------------------------------------------ unknown atoms

add("unk-1", "unknown_atom", OPEN_R2, "an unreadable token could be anything; looking is mandatory",
    **F("WOMBAT_SUBSYSTEM>RETRY", ev_ref=ev("u1")))
add("unk-2", "unknown_atom", OPEN_R2, "entirely unknown vocabulary on an unknown subject",
    **F("ZEPHYR_LAYER>QUUX_STATE", subj="zephyr", ev_ref=ev("u2")))
add("unk-3", "unknown_atom", OPEN_R2, "unknown token on the reader's own subject",
    **F("CACHE_SHARD_SPLIT", ev_ref=ev("u3")))
add("unk-4", "unknown_atom", OPEN_R2, "half known, half unknown: the unknown half decides",
    **F("RETRY>GRIFFIN_MODE", ev_ref=ev("u4")))

# ------------------------------------------------ prose claims the frame cannot carry

add("prose-rel-1", "ambiguous_prose", OPEN_R2, "genuinely about the queue; the frame cannot say so",
    **F("stale queue ownership survives a retry and duplicates work", ev_ref=ev("p1")))
add("prose-rel-2", "ambiguous_prose", OPEN_R2, "a real recovery finding written as prose",
    **F("recovery leaves the ownership record behind", subj="recovery", ev_ref=ev("p2")))
add("prose-irr-1", "ambiguous_prose", DEFER, "prose about an unrelated area: the ideal reader skips it",
    **F("the release notes template needs rewording", subj="docs", ev_ref=ev("p3")))
add("prose-irr-2", "ambiguous_prose", DEFER, "unrelated prose, no way for R1 to know",
    **F("the icon set looks inconsistent at small sizes", subj="ui", ev_ref=ev("p4")))

# ------------------------------------------------ contradictions

add("con-1", "contradiction", OPEN_R3, "a refutation of a relevant claim must reach the record",
    **F("RETRY>DUPLICATE_EXECUTION", ev_ref=ev("c1"), status="U4", REFUTES=ev("r1")))
add("con-2", "contradiction", OPEN_R3, "a conflict on the reader's own subject",
    **F("QUEUE_OWNERSHIP_STALE>RECOVERY", ev_ref=ev("c2"), CON=ev("r3")))
add("con-3", "contradiction", DEFER, "a contradiction in someone else's area stays there",
    **F("SIGNATURE>VALIDATION", subj="envelope", ev_ref=ev("c3"), REFUTES=ev("i1")))

# ------------------------------------------------ hypotheses

add("hyp-1", "hypothesis", OPEN_R2, "a relevant hypothesis is worth a summary, never treated as fact",
    KIND="H", SRC="AGENT:b03", SUBJ="queue", CLAIM="RETRY>DUPLICATE_EXECUTION", TYPE="INT",
    FALSIFY="a retry with a fresh owner still duplicates", EV="0", STATUS="U1", CREATED=T)
add("hyp-2", "hypothesis", OPEN_R3, "a relevant hypothesis with evidence at the supported rung",
    KIND="H", SRC="AGENT:b03", SUBJ="recovery", CLAIM="RECOVERY>DEADLOCK", TYPE="INT",
    FALSIFY="a recovery with no concurrent writer still deadlocks", EV=ev("h2"), STATUS="U3",
    CREATED=T)
add("hyp-3", "hypothesis", DEFER, "someone else's hypothesis about someone else's subsystem",
    KIND="H", SRC="AGENT:c11", SUBJ="loader", CLAIM="CONFIGURATION>PERFORMANCE", TYPE="INT",
    FALSIFY="reverting the loader leaves the regression", EV="0", STATUS="U1", CREATED=T)

# ------------------------------------------------ goals and values

add("goal-rel", "goal_value", OPEN_R2, "a goal aimed at the reader's own area changes what they work on",
    KIND="G", SRC="HUMAN:vacterro", SUBJ="queue", CLAIM="make duplicate execution impossible",
    CREATED=T)
add("goal-irr", "goal_value", DEFER, "a goal about maintenance burden is not this reader's work",
    KIND="G", SRC="HUMAN:vacterro", SUBJ="maintenance", CLAIM="reduce maintenance burden",
    CREATED=T)
add("value-irr", "goal_value", DEFER, "a stated preference with no bearing on the queue",
    KIND="V", SRC="HUMAN:vacterro", SUBJ="style", CLAIM="prefer simple over clever", CREATED=T)
add("value-rel", "goal_value", OPEN_R2, "a preference that ranks reliability above throughput on this queue",
    KIND="V", SRC="HUMAN:vacterro", SUBJ="queue", CLAIM="reliability outranks throughput",
    CREATED=T)

# ------------------------------------------------ warnings

add("warn-1", "warning", OPEN_R3, "a verified warning about the reader's own failure mode",
    **F("RETRY>DUPLICATE_EXECUTION", ev_ref=ev("w1"), status="U4"))
add("warn-2", "warning", OPEN_R2, "a relevant warning with nothing behind it yet",
    **F("CONCURRENCY>RETRY", status="U1"))
add("warn-3", "warning", DEFER, "a warning about the envelope layer",
    **F("SIGNATURE>ENVELOPE", subj="envelope", ev_ref=ev("w3"), status="U3"))

# ------------------------------------------------ repeated topics

add("rep-1", "repeated_topic", OPEN_R3, "the same finding reproduced independently still matters",
    **F("QUEUE_OWNERSHIP_STALE>RETRY>DUPLICATE_EXECUTION", ev_ref=ev("rp1"), SUPPORTS=ev("r1")))
add("rep-2", "repeated_topic", OPEN_R2, "a third report of the same thing, unverified",
    **F("QUEUE_OWNERSHIP_STALE>RETRY>DUPLICATE_EXECUTION", status="U1"))
add("rep-3", "repeated_topic", DEFER, "a repeated report from an unrelated area",
    **F("CONFIGURATION>REGRESSION", subj="loader", ev_ref=ev("rp3")))

# ------------------------------------------------ novel discoveries

add("nov-1", "novel_discovery", OPEN_R2, "a new mechanism nobody has vocabulary for yet",
    **F("SHARD_REBALANCE>RETRY", ev_ref=ev("n1")))
add("nov-2", "novel_discovery", OPEN_R2, "novel and unreadable: the expensive one to get wrong",
    **F("PHANTOM_LEASE>DUPLICATE_EXECUTION", ev_ref=ev("n2")))
add("nov-3", "novel_discovery", OPEN_R2, "novel vocabulary on an unrelated subject, still unreadable",
    **F("GLACIER_TIER>METADATA", subj="storage", ev_ref=ev("n3")))

# ------------------------------------------------ same topic, different relation

add("rel-sup", "same_topic_relation", OPEN_R3, "support for a relevant claim, with evidence",
    **F("RETRY>DUPLICATE_EXECUTION", ev_ref=ev("s1"), SUPPORTS=ev("r1")))
add("rel-ref", "same_topic_relation", OPEN_R3, "refutation of the same relevant claim",
    **F("RETRY>DUPLICATE_EXECUTION", ev_ref=ev("s2"), REFUTES=ev("r1")))
add("rel-plain", "same_topic_relation", OPEN_R2, "the same topic with no relation and no evidence",
    **F("RETRY>DUPLICATE_EXECUTION", status="U1"))

# ------------------------------------------------ BLOCKED versus BLOCKER

add("blk-state", "blocked_vs_blocker", DEFER, "release work is blocked by a dependency: not this reader",
    **F("BLOCKED>DEPENDENCY", subj="release", ev_ref=ev("b1")))
add("blk-cause", "blocked_vs_blocker", OPEN_R3, "the retry path is what is blocking others: the reader owns it",
    **F("BLOCKER>RETRY", subj="queue", ev_ref=ev("b2"), status="U3"))


# ------------------------------------------------ relation to a watched record

add("watch-refute", "relation_to_watched", OPEN_R3,
    "the vocabulary is another domain entirely, and it refutes a record this reader watches",
    **F("SIGNATURE>ENVELOPE", subj="envelope", ev_ref=ev("wr1"), REFUTES=WATCHED))
add("watch-conflict", "relation_to_watched", OPEN_R3,
    "an unrelated-looking configuration note that conflicts with the watched record",
    **F("CONFIGURATION>REGRESSION", subj="loader", ev_ref=ev("wr2"), CON=WATCHED))
add("watch-support", "relation_to_watched", OPEN_R3,
    "support for the watched record, from a subsystem the reader never looks at",
    **F("DATABASE>METADATA", subj="db", ev_ref=ev("wr3"), SUPPORTS=WATCHED))
add("watch-other", "relation_to_watched", DEFER,
    "relevant-looking vocabulary whose relation points at a record nobody watches",
    **F("SIGNATURE>VALIDATION", subj="envelope", ev_ref=ev("wr4"), REFUTES=ev("some-other")))

# ------------------------------------------------ defer / serendipity

add("cross-1", "cross_domain_discovery", DEFER,
    "a real discovery in a neighbouring subsystem: not now, not never",
    **F("PERFORMANCE>REGRESSION", subj="loader", ev_ref=ev("cd1")))
add("cross-2", "cross_domain_discovery", DEFER,
    "someone else found something about sessions that may matter later",
    **F("SESSION>PERFORMANCE", subj="session", ev_ref=ev("cd2")))
add("later-1", "later_relevant", DEFER,
    "an observation about validation that becomes relevant once the queue work lands",
    **F("VALIDATION>REGRESSION", subj="validate", ev_ref=ev("lr1")))
add("noise-1", "operational_noise", IGNORE,
    "a checkpoint timestamp: the reader declared this class to be noise",
    **F("CHECKPOINT>TIMESTAMP", subj="session", ev_ref=ev("nz1")))
add("noise-2", "operational_noise", IGNORE,
    "routine metadata churn, declared noise by this reader",
    **F("METADATA>TIMESTAMP", subj="db", ev_ref=ev("nz2")))


CLASSES = sorted({case.klass for case in CASES})
TRUTH_COUNTS = {verdict: sum(1 for c in CASES if c.truth == verdict)
                for verdict in (IGNORE, DEFER, OPEN_R2, OPEN_R3)}
