"""Promotion gate: kind-aware, evidence-honest, never a writer (D-006, T-10).

Promotion is the single gate separating institutional memory from a shared
mood, and "evidence required" is right for factual knowledge and wrong as a
universal rule. Per ``spec/DECISIONS.md`` D-006:

* ``F`` and ``O`` require an evidence ref -- refused without one, not warned;
* ``H`` requires authenticated provenance plus a falsification condition, and
  supporting evidence does not silently convert it into an ``F``;
* ``G`` and ``V`` require authenticated provenance only -- a stated goal or
  value is worth preserving and needs no pretend factual evidence.

Authenticated provenance is mechanical, not asserted, and it has two steps
(D-035): the caller hands in the ``OpenedEnvelope`` the receiver's own
``open`` operation minted for the exact envelope -- a type-state that can only exist
after parse, verify, recipient acceptance and AEAD decryption of that one
container -- and the promoted record must BE that payload:
``record.canonical_bytes() == opened.plaintext``. An authenticated container
is not an authenticated record (the T-10 defect this closes); provenance never
transfers to a record the envelope never carried. The currently supported
payload shape is exactly one canonical record; anything else is a mismatch,
and a multi-record payload is a protocol decision nobody has made yet.

This module emits a KNOWLEDGE **card proposal** and never writes a card. The
proposal carries the envelope's transport identity (``ENVELOPE_ID``), so the
durable memory can always point back at the sealed evidence it came from; the
decision to turn a proposal into a card belongs to a caller with authority,
not to a gate.

A promoted record that is later contradicted is marked and kept by the ledger
(D-008); nothing here deletes or tidies forensic history.
"""

from __future__ import annotations

from typing import Optional

from sailang.errors import SailangError
from sailang.record import Record

from saimail import envelope


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def propose(record: Record, opened: "envelope.OpenedEnvelope", *, reason: str) -> dict:
    """Return one KNOWLEDGE card proposal for a promotable record.

    ``opened`` is the :class:`~saimail.envelope.OpenedEnvelope` minted by the
    receiver's ``open`` operation for the exact envelope the record arrived in, and the
    record must be the exact plaintext that envelope carried. The proposal is
    returned, never written: no file, no directory, no card.
    """
    if not isinstance(record, Record):
        _reject("NOT_A_RECORD",
                f"a promotion proposal takes a canonical Record, got {type(record).__name__}")
    if not isinstance(opened, envelope.OpenedEnvelope):
        _reject("NOT_OPENED",
                "authenticated provenance means the exact decrypted payload: pass the "
                "OpenedEnvelope minted by the open operation for this envelope. A container, a "
                "VerifiedEnvelope or loose bytes authenticate the envelope, never the "
                "record (D-035)")
    if record.canonical_bytes() != opened.plaintext:
        _reject("PROMOTION_PAYLOAD_MISMATCH",
                f"the record hashes to {record.content_id} but this envelope carried "
                "different plaintext; AUTHENTICATED CONTAINER != AUTHENTICATED RECORD "
                "and provenance does not transfer (D-035)")

    if not isinstance(reason, str) or not reason.strip():
        _reject("BAD_PROMOTION_REASON",
                "a promotion names why this item earned durable memory; an empty reason is a "
                "promotion nobody can audit later")

    kind = record.get("KIND")
    evidence_note = "NOT_REQUIRED"
    if kind in ("F", "O"):
        if not record.has_evidence:
            _reject("PROMOTION_EVIDENCE_REQUIRED",
                    f"KIND {kind} promotes only with an evidence ref; refusing, not warning "
                    "(D-006: this refusal is the gate between memory and a shared mood)")
        evidence_note = "EVIDENCE_REF_REQUIRED_AND_PRESENT"
    elif kind == "H":
        if not record.get("FALSIFY"):
            _reject("PROMOTION_FALSIFICATION_REQUIRED",
                    "KIND H promotes with a falsification condition; a hypothesis that cannot "
                    "fail cannot be promoted")
        # supporting evidence never converts an H into an F (D-006)
        evidence_note = ("EVIDENCE_SUPPORTS_WITHOUT_CONVERTING"
                         if record.has_evidence else "UNEVIDENCED_HYPOTHESIS")
    # G and V: authenticated provenance only, already proven above; their kind
    # rules forbid assessment fields, so no pretend factual evidence exists.

    return {
        "proposal": "KNOWLEDGE_CARD",
        "kind": kind,
        "subject": record.get("SUBJ"),
        "claim": record.get("CLAIM"),
        "rung": record.get("STATUS"),
        "evidence": evidence_note,
        "envelope": opened.envelope_id,
        "reason": reason,
        "written_by_this_call": False,
    }
