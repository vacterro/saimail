"""SAILANG — canonical claim records and non-authoritative triage frames.

Data only: this package parses, validates, projects and decodes text. It never
executes, routes, fetches or mutates anything.

Authority runs one way and only one way:

    Record  ->  TriageFrame  ->  TriageView

and never back. A view is never promoted into a record (spec/DECISIONS.md
D-010).
"""

from .errors import SailangError
from .frame import (Batch, Profile, TriageFrame, TriageView, decode, project,
                    project_batch)
from .record import (EVIDENCE_ATTACHED, EVIDENCE_EXPLICITLY_ABSENT,
                    EVIDENCE_NOT_APPLICABLE, EVIDENCE_STATES, FORMAT_VERSION,
                    Record, parse)

__all__ = [
    "Record",
    "parse",
    "SailangError",
    "FORMAT_VERSION",
    "EVIDENCE_ATTACHED",
    "EVIDENCE_EXPLICITLY_ABSENT",
    "EVIDENCE_NOT_APPLICABLE",
    "EVIDENCE_STATES",
    "Profile",
    "TriageFrame",
    "TriageView",
    "Batch",
    "project",
    "project_batch",
    "decode",
]
