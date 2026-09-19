"""Prose baselines for T-9B, rendered deterministically from the same ground truth.

Two questions need two different baselines, and mixing them is the mistake the
first benchmark made:

* ``triage_prose`` carries **exactly** the triage semantics a frame carries —
  kind, subject, rung, evidence presence, relation flags, and the claim only
  when the frame could carry it. Comparing a frame against prose that also
  spells out a 64-hex evidence id would be comparing different information.
* ``full_prose`` carries **everything the canonical record carries**, including
  the complete evidence identity, the source channel and the timestamp. That is
  the only fair opponent for the record.

Both are rendered by template rather than hand-written, on purpose: a template
cannot be quietly tuned per case after seeing a result, and the template itself
is printed in the report so a reader can attack it. The hand-written
``case.prose`` is kept as an informal third baseline and is **excluded from
every verdict**, because it is not information-equivalent to anything.
"""

from __future__ import annotations

from sailang import Record
from sailang.frame import OPEN_RECORD, Profile, decode, project

KIND_WORD = {"F": "claim", "O": "observation", "H": "hypothesis",
             "G": "goal", "V": "preference"}
RUNG_WORD = {"U0": "unknown", "U1": "unverified", "U2": "supported",
             "U3": "strongly supported", "U4": "verified"}
TYPE_WORD = {"OBS": "observed directly", "MEM": "from memory", "INT": "by interpretation"}
GRADE_WORD = {"HIGH": "high", "MED": "medium", "LOW": "low"}

#: Printed in the report. Changing it changes every baseline, which is the point.
TRIAGE_TEMPLATE = (
    "[rung] [kind] on [subject], [evidence][, relations]: [claim | open the record]"
)
FULL_TEMPLATE = (
    "On [created], [source] recorded a [rung] [kind] about [subject]: [claim]. "
    "[Type]. Evidence: [full 64-hex ids | none]. [Grades]. [Relations with full ids]. "
    "[Falsification condition]."
)


def _claim_words(token: str) -> str:
    return token.replace(">", " -> ").replace("_", " ").lower()


def triage_prose(record: Record, profile: Profile) -> str:
    """Prose carrying the frame's semantics and nothing more."""
    view = decode(project(record, profile))
    parts = []
    if view.status:
        parts.append(RUNG_WORD[view.status])
    parts.append(KIND_WORD[view.kind])
    head = " ".join(parts)
    subject = view.subject or "an unnamed subject"
    if view.evidence_state == "EVIDENCE_NOT_APPLICABLE":
        evidence = "no evidence applies"
    elif view.has_evidence:
        evidence = "evidence attached"
    else:
        evidence = "no evidence"
    relations = []
    if view.refutes:
        relations.append("refutes another record")
    if view.supports:
        relations.append("supports another record")
    if view.conflict:
        relations.append("conflicts with another record")
    if view.falsifiable:
        relations.append("falsifiable")
    relation_clause = ", " + ", ".join(relations) if relations else ""
    body = _claim_words(view.claim_token) if view.claim_token else "open the record"
    return f"{head} on {subject}, {evidence}{relation_clause}: {body}"


def full_prose(record: Record) -> str:
    """Prose carrying everything the canonical record carries."""
    kind = KIND_WORD[record.kind]
    rung = RUNG_WORD[record.get("STATUS")] + " " if record.get("STATUS") else ""
    subject = record.get("SUBJ") or "an unnamed subject"
    sentences = [
        f"On {record.get('CREATED')}, {record.get('SRC')} recorded a {rung}{kind} "
        f"about {subject}: {record.claim}."
    ]
    if record.get("TYPE"):
        sentences.append(f"It is {TYPE_WORD[record.get('TYPE')]}.")
    evidence = record.get("EV")
    if evidence is None:
        pass
    elif evidence == "0":
        sentences.append("No evidence is attached.")
    else:
        sentences.append("Evidence: " + ", ".join(evidence.split(",")) + ".")
    grades = [
        f"{name.lower()} is {GRADE_WORD[record.get(name)]}"
        for name in ("DIRECTNESS", "INDEPENDENCE", "INTEGRITY")
        if record.get(name)
    ]
    if grades:
        sentences.append(("; ".join(grades)).capitalize() + ".")
    if record.get("FRESHNESS"):
        sentences.append(f"Data as of {record.get('FRESHNESS')}.")
    for field, verb in (("REFUTES", "refutes"), ("SUPPORTS", "supports"),
                        ("CON", "conflicts with"), ("INTEREST_REF", "has a structural interest recorded in")):
        if record.get(field):
            sentences.append(f"It {verb} {record.get(field)}.")
    if record.get("FALSIFY"):
        sentences.append(f"It is falsified if {record.get('FALSIFY')}.")
    return " ".join(sentences)


def summary_prose(record: Record) -> str:
    """R2: a one-line semantic summary, derived from the record, no provenance."""
    subject = record.get("SUBJ") or "an unnamed subject"
    return f"{subject}: {record.claim}"


def open_record_marker() -> str:
    return OPEN_RECORD
