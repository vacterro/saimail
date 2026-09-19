"""T-10/T-42 acceptance: promotion is kind-aware, payload-bound, never a writer.

What is proven here, in the order the gate decides it:

* provenance is authenticated mechanically in two steps (D-035): the proposal
  consumes the ``OpenedEnvelope`` the receiver's own ``open()`` minted, and the
  promoted record must BE the exact plaintext that envelope carried -- an
  authenticated container never lends its provenance to a record it never
  held;
* opened state cannot be forged, constructed or transplanted;
* ``F``/``O`` refuse without an evidence ref -- refused, never warned;
* ``H`` requires a falsification condition, and supporting evidence does not
  silently convert it into an ``F``;
* ``G``/``V`` need authenticated provenance only -- no pretend evidence;
* the output is a KNOWLEDGE card PROPOSAL carrying the envelope's transport
  identity, and the module never writes a card, a file or a directory;
* the kind rules of the record layer already keep assessment fields out of
  goals and values, which is what makes "provenance only" honest.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from sailang import Record, SailangError
from saimail import envelope, promotion
from saimail.envelope import KeyRegistry, RecipientKeyRegistry

ROOT = pathlib.Path(__file__).resolve().parent.parent
T = "2026-09-18T12:00:00Z"

SENDER = Ed25519PrivateKey.generate()
RECIPIENT = X25519PrivateKey.generate()
SENDER_REGISTRY = KeyRegistry({"A17": [SENDER.public_key()]})
RECIPIENT_REGISTRY = RecipientKeyRegistry({"B03": [RECIPIENT.public_key()]})


def err(fn, *a, **k):
    with pytest.raises(SailangError) as e:
        fn(*a, **k)
    return e.value.code


def carried(record_or_text):
    """Seal a record (or raw text); return (container, the opened envelope)."""
    payload = (record_or_text.canonical_text() if isinstance(record_or_text, Record)
               else record_or_text)
    container = envelope.seal(payload, sender_private_key=SENDER, sender_seat="A17",
                              recipient_seat="B03", recipient_public_key=RECIPIENT.public_key(),
                              kind="DISCOVERY", topic="promotion", created=T)
    verified = envelope.verify(envelope.parse_header(container), SENDER_REGISTRY)
    opened = envelope.open(verified, RECIPIENT, RECIPIENT_REGISTRY)
    return container, opened


def fact(**over):
    fields = dict(KIND="F", SRC="AGENT:a17", SUBJ="queue", CLAIM="the retry ran twice",
                  TYPE="OBS", EV="sha256:" + "e" * 64, STATUS="U2", CREATED=T)
    fields.update(over)
    for key in [k for k, v in fields.items() if v is None]:
        del fields[key]
    return Record.create(**fields)


def hypothesis(**over):
    fields = dict(KIND="H", SRC="AGENT:a17", SUBJ="queue", CLAIM="retries double under load",
                  TYPE="INT", EV="sha256:" + "e" * 64, STATUS="U2", CREATED=T,
                  FALSIFY="sha256:" + "f" * 64)
    fields.update(over)
    for key in [k for k, v in fields.items() if v is None]:
        del fields[key]
    return Record.create(**fields)


def goal(**over):
    fields = dict(KIND="G", SRC="AGENT:a17", CLAIM="keep the queue drained",
                  CREATED=T)
    fields.update(over)
    for key in [k for k, v in fields.items() if v is None]:
        del fields[key]
    return Record.create(**fields)


# ------------------------------------------------ authenticated provenance


def test_the_exact_carried_record_promotes_under_its_own_envelope_id():
    record = fact()
    container, opened = carried(record)
    assert opened.plaintext == record.canonical_bytes()
    proposal = promotion.propose(record, opened, reason="reused in T-1342")
    assert proposal["envelope"] == envelope.envelope_id(container), \
        "the opened state derives the id of the exact canonical container bytes"
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", proposal["envelope"])


def test_an_unrelated_record_cannot_inherit_envelope_provenance():
    """The T-42 reproduction: benign G envelope, forged F record beside it."""
    container, opened = carried(goal())
    forged = fact(CLAIM="forged fact", EV="sha256:" + "e" * 64)
    assert err(promotion.propose, forged, opened, reason="forged") == \
        "PROMOTION_PAYLOAD_MISMATCH"
    unrelated_goal = goal(CLAIM="a different goal entirely")
    assert err(promotion.propose, unrelated_goal, opened, reason="borrowed") == \
        "PROMOTION_PAYLOAD_MISMATCH"


def test_the_same_claim_under_different_canonical_metadata_is_refused():
    exact = fact()
    container, opened = carried(exact)
    altered = fact(STATUS="U3", CREATED="2026-09-18T13:00:00Z")
    assert altered.get("CLAIM") == exact.get("CLAIM")
    assert err(promotion.propose, altered, opened, reason="lookalike") == \
        "PROMOTION_PAYLOAD_MISMATCH"


def test_a_non_record_payload_never_promotes_any_record():
    _, opened = carried("just text, not a canonical record\n")
    assert err(promotion.propose, fact(), opened, reason="text") == \
        "PROMOTION_PAYLOAD_MISMATCH"


def test_only_opened_state_is_promotion_grade_provenance():
    record = fact()
    container, opened = carried(record)
    assert err(promotion.propose, record, container, reason="bytes") == "NOT_OPENED"
    verified = envelope.verify(envelope.parse_header(container), SENDER_REGISTRY)
    assert err(promotion.propose, record, verified, reason="verified but sealed") == \
        "NOT_OPENED"
    assert err(promotion.propose, record, opened.plaintext, reason="loose bytes") == \
        "NOT_OPENED"


# ------------------------------------------------ opened state cannot be forged


def test_opened_envelope_state_cannot_be_constructed_or_transplanted():
    record = fact()
    _, opened = carried(record)
    assert err(envelope.OpenedEnvelope, opened.verified, b"other bytes",
               opened.envelope_id) == "UNOPENED_ENVELOPE"
    assert err(envelope.OpenedEnvelope, verified=opened.verified,
               plaintext=b"other bytes", envelope_id=opened.envelope_id) == \
        "UNOPENED_ENVELOPE"
    assert err(dataclasses.replace, opened, plaintext=fact(CLAIM="swapped").canonical_bytes()) \
        == "UNOPENED_ENVELOPE"
    assert "_OPENED" not in opened.__dict__, "the mint is not retained on the instance"


def test_opened_state_survives_a_round_trip_through_its_own_fields():
    record = fact()
    container, opened = carried(record)
    again = envelope.open(opened.verified, RECIPIENT, RECIPIENT_REGISTRY)
    assert again.plaintext == opened.plaintext
    assert again.envelope_id == envelope.envelope_id(container)


# ------------------------------------------------ kind-aware gates


def test_f_promotes_only_with_an_evidence_ref():
    with_evidence = fact()
    _, opened = carried(with_evidence)
    proposal = promotion.propose(with_evidence, opened, reason="reused")
    assert proposal["kind"] == "F"
    assert proposal["evidence"] == "EVIDENCE_REF_REQUIRED_AND_PRESENT"
    without = fact(EV="0", STATUS="U1")
    _, opened2 = carried(without)
    assert err(promotion.propose, without, opened2, reason="reused") == \
        "PROMOTION_EVIDENCE_REQUIRED"


def test_o_promotes_only_with_an_evidence_ref():
    observation = Record.create(
        KIND="O", SRC="LOG:run42", SUBJ="queue", CLAIM="latency doubled",
        TYPE="OBS", EV="sha256:" + "e" * 64, STATUS="U2", CREATED=T)
    _, opened = carried(observation)
    assert promotion.propose(observation, opened, reason="cited")["kind"] == "O"
    bare = Record.create(
        KIND="O", SRC="LOG:run43", SUBJ="queue", CLAIM="latency doubled",
        TYPE="OBS", EV="0", STATUS="U1", CREATED=T)
    _, opened2 = carried(bare)
    assert err(promotion.propose, bare, opened2, reason="cited") == \
        "PROMOTION_EVIDENCE_REQUIRED"


def test_h_requires_a_falsification_condition_and_stays_an_h():
    supported = hypothesis()
    _, opened = carried(supported)
    proposal = promotion.propose(supported, opened, reason="shaped a fix")
    assert proposal["kind"] == "H"
    assert proposal["evidence"] == "EVIDENCE_SUPPORTS_WITHOUT_CONVERTING", \
        "supporting evidence must not silently convert an H into an F (D-006)"
    unevidenced = hypothesis(EV="0", STATUS="U1")
    _, opened2 = carried(unevidenced)
    proposal2 = promotion.propose(unevidenced, opened2, reason="shaped a fix")
    assert proposal2["evidence"] == "UNEVIDENCED_HYPOTHESIS"
    # an H without a falsification condition is refused by the record layer
    # before this gate ever sees it; the gate keeps the same refusal for
    # anything that reaches it without one
    assert err(Record.create, KIND="H", SRC="AGENT:a17", SUBJ="queue",
               CLAIM="something is wrong", TYPE="INT", EV="sha256:" + "e" * 64,
               STATUS="U2", CREATED=T) == "MISSING_FIELD"


def test_g_and_v_promote_on_authenticated_provenance_only():
    stated_goal = goal()
    _, opened = carried(stated_goal)
    proposal = promotion.propose(stated_goal, opened, reason="steers work")
    assert proposal["kind"] == "G"
    assert proposal["evidence"] == "NOT_REQUIRED"
    value = Record.create(KIND="V", SRC="AGENT:a17", CLAIM="no silent truncation",
                          CREATED=T)
    _, opened2 = carried(value)
    assert promotion.propose(value, opened2, reason="norm")["evidence"] == "NOT_REQUIRED"
    # and the record layer keeps pretend factual evidence out of G/V already
    assert err(goal, EV="sha256:" + "e" * 64) == "FIELD_FORBIDDEN_FOR_KIND"


def test_the_reason_is_auditable_not_empty():
    record = fact()
    _, opened = carried(record)
    assert err(promotion.propose, record, opened, reason="  ") == \
        "BAD_PROMOTION_REASON"


# ------------------------------------------------ a proposal, never a card


def test_the_gate_emits_a_proposal_and_never_writes_a_card(tmp_path):
    record = fact()
    _, opened = carried(record)
    proposal = promotion.propose(record, opened, reason="reused twice")
    assert proposal["proposal"] == "KNOWLEDGE_CARD"
    assert proposal["claim"] == record.get("CLAIM") and proposal["rung"] == "U2"
    assert proposal["written_by_this_call"] is False
    assert not list(tmp_path.rglob("*")), "nothing was written anywhere"
    source = (ROOT / "saimail" / "promotion.py").read_text(encoding="utf-8")
    for forbidden in ("write_text", "write_bytes", "mkdir", "unlink", "rmtree",
                      "subprocess", "socket", "open("):
        assert forbidden not in source, f"the promotion gate must not carry {forbidden}"
