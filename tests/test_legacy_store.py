"""B-013 Target B: OpenedEnvelope-bound explicit immutable adoption."""

import dataclasses
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from sailang import SailangError
from saimail import envelope, postoffice, promotion
from saimail.legacy import (
    ADOPTED,
    ALREADY_ADOPTED,
    AuthenticatedLegacy,
    LegacyEntry,
    LegacyPacket,
    LegacyStore,
    authenticate_legacy,
)

SENDER = Ed25519PrivateKey.generate()
RECIPIENT = X25519PrivateKey.generate()
SEAT = "B03"
SENDER_SEAT = "A17"
T = "2026-09-19T10:00:00Z"
R1 = "sha256:" + "1" * 64
R2 = "sha256:" + "2" * 64
R3 = "sha256:" + "3" * 64


def packet(**changes):
    values = dict(
        subject="queue-lease-recovery",
        observed_scope="notifications queue only",
        what_worked="heartbeat extension prevented duplicate delivery",
        what_worked_evidence=(R1,),
        what_failed="raising timeout did not stop notification retries",
        what_failed_evidence=(R2,),
        what_looked_right_but_was_wrong="empty depth hid an in-flight lease",
        what_wrong_evidence=(R3,),
        watch_next="possible worker crash race",
        watch_next_evidence=(),
        watch_next_status="UNVERIFIED",
        created=T,
    )
    values.update(changes)
    return LegacyPacket(**values)


def err(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value.code


def office_at(tmp_path, clock=lambda: T, default_ttl=postoffice.DEFAULT_TTL_SECONDS):
    senders = envelope.KeyRegistry({SENDER_SEAT: [SENDER.public_key()]})
    recipients = envelope.RecipientKeyRegistry({SEAT: [RECIPIENT.public_key()]})
    return postoffice.PostOffice(
        tmp_path, seat=SEAT, sender_registry=senders, recipient_registry=recipients,
        clock=clock, default_ttl=default_ttl,
    )


def sealed(item, *, kind="EXPERIENCE", topic="legacy", ttl=None):
    return envelope.seal(
        item.render(), sender_private_key=SENDER, sender_seat=SENDER_SEAT,
        recipient_seat=SEAT, recipient_public_key=RECIPIENT.public_key(),
        kind=kind, topic=topic, created=T, ttl=ttl,
    ).encode("utf-8")


def deliver_open(office, item=None, **wire):
    item = item or packet()
    raw = sealed(item, **wire)
    delivered = office.deliver(raw)
    assert delivered.status == postoffice.ACCEPTED
    session = postoffice.PostOfficeSession(office, scan_budget=8, open_budget=8)
    opened = session.open_message(delivered.envelope_id, recipient_private_key=RECIPIENT)
    return item, raw, opened


def authenticated_at(tmp_path, **wire):
    office = office_at(tmp_path)
    item, raw, opened = deliver_open(office, **wire)
    return office, item, raw, opened, authenticate_legacy(opened, item)


def test_raw_packet_cannot_mint_authenticated_legacy():
    item = packet()
    code = err(AuthenticatedLegacy, item, "sha256:" + "a" * 64, SENDER_SEAT,
               "sha256:" + "b" * 64, SEAT)
    assert code == "UNAUTHENTICATED_LEGACY"


def test_verified_envelope_is_insufficient(tmp_path):
    raw = sealed(packet())
    verified = envelope.verify(envelope.parse_header(raw),
                               envelope.KeyRegistry({SENDER_SEAT: [SENDER.public_key()]}))
    assert err(authenticate_legacy, verified, packet()) == "LEGACY_REQUIRES_OPENED_ENVELOPE"


def test_unrelated_packet_cannot_inherit_opened_provenance(tmp_path):
    office = office_at(tmp_path)
    item, _, opened = deliver_open(office)
    other = dataclasses.replace(item, watch_next="different bytes")
    assert err(authenticate_legacy, opened, other) == "LEGACY_PAYLOAD_MISMATCH"


def test_exact_leg1_payload_from_opened_envelope_is_accepted(tmp_path):
    office = office_at(tmp_path)
    item, _, opened = deliver_open(office)
    proof = authenticate_legacy(opened, item)
    assert proof.packet.render() == opened.plaintext
    assert proof.source_envelope_id == opened.envelope_id
    assert proof.source_from == SENDER_SEAT and proof.recipient == SEAT


@pytest.mark.parametrize("wire,code", [
    ({"kind": "DISCOVERY"}, "LEGACY_WRONG_KIND"),
    ({"topic": "other"}, "LEGACY_WRONG_TOPIC"),
])
def test_transport_kind_and_topic_gate(tmp_path, wire, code):
    office = office_at(tmp_path)
    item, _, opened = deliver_open(office, **wire)
    assert err(authenticate_legacy, opened, item) == code


def test_dataclasses_replace_cannot_transplant_authenticated_state(tmp_path):
    _, item, _, _, proof = authenticated_at(tmp_path)
    other = dataclasses.replace(item, watch_next="transplanted")
    assert err(dataclasses.replace, proof, packet=other) == "UNAUTHENTICATED_LEGACY"


def test_direct_legacy_entry_construction_cannot_claim_store_validation(tmp_path):
    office, _, _, _, proof = authenticated_at(tmp_path)
    real = LegacyStore(office).adopt(proof).entry
    assert err(LegacyEntry, real.packet, real.provenance) == "UNVERIFIED_LEGACY_ENTRY"


def test_dataclasses_replace_cannot_transplant_validated_entry_packet(tmp_path):
    office, item, _, _, proof = authenticated_at(tmp_path)
    real = LegacyStore(office).adopt(proof).entry
    forged = dataclasses.replace(item, what_worked="forged predecessor account")
    assert err(dataclasses.replace, real, packet=forged) == "UNVERIFIED_LEGACY_ENTRY"


def test_dataclasses_replace_cannot_transplant_validated_entry_provenance(tmp_path):
    office, _, _, _, proof = authenticated_at(tmp_path)
    real = LegacyStore(office).adopt(proof).entry
    forged = dataclasses.replace(real.provenance, source_from="TRUSTED")
    assert err(dataclasses.replace, real, provenance=forged) == "UNVERIFIED_LEGACY_ENTRY"


def test_store_read_is_the_entry_proof_point_and_remains_renderable(tmp_path):
    office, _, _, _, proof = authenticated_at(tmp_path)
    store = LegacyStore(office)
    store.adopt(proof)
    validated = store.for_subject("queue-lease-recovery")
    assert len(validated) == 1
    context = store.build_successor_context("queue-lease-recovery", "billing queue")
    assert validated[0].entry_id.encode() in context.data


def test_opening_does_not_automatically_create_legacy_state(tmp_path):
    office = office_at(tmp_path)
    deliver_open(office)
    assert not (office.mail_root / "legacy").exists()
    assert not (office.mail_root / "promoted").joinpath(SEAT).exists()


def test_explicit_adoption_creates_one_immutable_entry_and_repeat_is_idempotent(tmp_path):
    office, item, _, _, proof = authenticated_at(tmp_path)
    store = LegacyStore(office)
    first = store.adopt(proof)
    second = store.adopt(proof)
    assert first.status == ADOPTED and second.status == ALREADY_ADOPTED
    assert first.path == second.path
    assert (first.path / "packet.leg1").read_bytes() == item.render()
    assert len(store.all()) == 1


def test_same_content_from_two_envelopes_keeps_two_provenance_events(tmp_path):
    office = office_at(tmp_path)
    item, _, opened_a = deliver_open(office)
    _, _, opened_b = deliver_open(office, item)
    proof_a = authenticate_legacy(opened_a, item)
    proof_b = authenticate_legacy(opened_b, item)
    store = LegacyStore(office)
    first, second = store.adopt(proof_a), store.adopt(proof_b)
    assert first.entry.packet.id == second.entry.packet.id
    assert first.entry.entry_id != second.entry.entry_id
    assert len(store.all()) == 2


def test_conflicting_existing_entry_refuses_without_overwrite(tmp_path):
    office, item, _, _, proof = authenticated_at(tmp_path)
    store = LegacyStore(office)
    result = store.adopt(proof)
    hostile = dataclasses.replace(item, watch_next="changed committed bytes").render()
    (result.path / "packet.leg1").write_bytes(hostile)
    before = (result.path / "packet.leg1").read_bytes()
    assert err(store.adopt, proof) in {"LEGACY_ENTRY_CONFLICT", "LEGACY_ENTRY_CORRUPT"}
    assert (result.path / "packet.leg1").read_bytes() == before


def test_provenance_sidecar_is_receiver_owned_and_contains_no_secret(tmp_path):
    office, item, _, opened, proof = authenticated_at(tmp_path)
    result = LegacyStore(office).adopt(proof)
    sidecar_bytes = (result.path / "provenance.json").read_bytes()
    sidecar = json.loads(sidecar_bytes)
    assert sidecar_bytes.endswith(b"\n")
    assert sidecar["legacy_entry_id"] == proof.entry_id
    assert sidecar["legacy_content_id"] == item.id
    assert sidecar["source_envelope_id"] == opened.envelope_id
    assert sidecar["source_from"] == SENDER_SEAT
    assert sidecar["source_from_kid"] == envelope.fingerprint(SENDER.public_key())
    assert sidecar["recipient"] == SEAT
    assert sidecar["received_at"] == T and sidecar["adopted_at"] == T
    text = sidecar_bytes.decode("utf-8").lower()
    assert "private" not in text and "confidence" not in text and "trust" not in text


def test_adoption_never_calls_promotion_or_creates_knowledge(tmp_path, monkeypatch):
    office, _, _, _, proof = authenticated_at(tmp_path)
    calls = []
    monkeypatch.setattr(promotion, "propose", lambda *a, **k: calls.append((a, k)))
    LegacyStore(office).adopt(proof)
    assert calls == []
    assert not (tmp_path / "KNOWLEDGE").exists()


def test_source_transport_expiry_does_not_remove_adopted_legacy(tmp_path):
    now = [T]
    office = office_at(tmp_path, clock=lambda: now[0],
                       default_ttl=postoffice.MIN_TTL_SECONDS)
    item, _, opened = deliver_open(office, ttl="7D")
    store = LegacyStore(office)
    adopted = store.adopt(authenticate_legacy(opened, item))
    instant = datetime.strptime(T, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    now[0] = (instant + timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sweep = office.sweep_expired()
    assert sweep.expired == 1
    assert not office.read_bundle(opened.envelope_id).exists()
    assert office.expired_tombstone(opened.envelope_id).is_file()
    assert (adopted.path / "packet.leg1").read_bytes() == item.render()
    assert store.for_subject(item.subject)[0].provenance.source_envelope_id == opened.envelope_id
