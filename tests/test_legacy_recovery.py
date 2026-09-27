"""B-015: receiver-owned adoption intent and explicit recovery."""

import json
import threading

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from sailang import SailangError
from saimail import envelope, postoffice
from saimail.legacy import (
    ADOPTION_INTENT_NAME,
    LEGACY_PARTIAL_ADOPTION_REQUIRES_AUTHENTICATED_RETRY,
    RECOVERY_REPAIRED,
    RECOVERY_REQUIRES_AUTHENTICATED_RETRY,
    LegacyPacket,
    LegacyStore,
    authenticate_legacy,
)

SENDER = Ed25519PrivateKey.generate()
RECIPIENT = X25519PrivateKey.generate()
SENDER_SEAT = "A17"
SEAT = "B03"
T = "2026-09-19T10:00:00Z"
REF = lambda n: "sha256:" + str(n) * 64


def packet():
    return LegacyPacket(
        subject="queue-lease-recovery", observed_scope="queue only",
        what_worked="worked", what_worked_evidence=(REF(1),),
        what_failed="failed", what_failed_evidence=(REF(2),),
        what_looked_right_but_was_wrong="wrong", what_wrong_evidence=(REF(3),),
        watch_next="inspect", watch_next_evidence=(),
        watch_next_status="UNVERIFIED", created=T,
    )


def setup(tmp_path):
    office = postoffice.PostOffice(
        tmp_path, seat=SEAT,
        sender_registry=envelope.KeyRegistry({SENDER_SEAT: [SENDER.public_key()]}),
        recipient_registry=envelope.RecipientKeyRegistry({SEAT: [RECIPIENT.public_key()]}),
        clock=lambda: T,
    )
    item = packet()
    raw = envelope.seal(item.render(), sender_private_key=SENDER,
                        sender_seat=SENDER_SEAT, recipient_seat=SEAT,
                        recipient_public_key=RECIPIENT.public_key(),
                        kind="EXPERIENCE", topic="legacy", created=T).encode()
    delivered = office.deliver(raw)
    opened = postoffice.PostOfficeSession(office, scan_budget=8, open_budget=8).open_message(
        delivered.envelope_id, recipient_private_key=RECIPIENT)
    return office, item, authenticate_legacy(opened, item)


def test_intent_is_published_before_recovery_pair_and_recovery_is_idempotent(tmp_path):
    office, item, proof = setup(tmp_path)
    store = LegacyStore(office)
    first = store.adopt(proof)
    (first.path / "packet.leg1").unlink()
    (first.path / "provenance.json").unlink()

    intent = first.path / ADOPTION_INTENT_NAME
    assert intent.is_file()
    assert json.loads(intent.read_text())["legacy_entry_id"] == proof.entry_id

    pending = store.recover()
    assert pending[0].status == RECOVERY_REQUIRES_AUTHENTICATED_RETRY
    repaired = store.recover(proof)
    assert repaired[0].status == RECOVERY_REPAIRED
    assert (first.path / "packet.leg1").read_bytes() == item.render()
    assert store.recover(proof)[0].entry.entry_id == proof.entry_id


def test_old_partial_directory_without_intent_requires_authenticated_retry(tmp_path):
    office, _, proof = setup(tmp_path)
    store = LegacyStore(office)
    directory = store.entry_path(proof.entry_id)
    directory.mkdir(parents=True)
    with pytest.raises(SailangError) as caught:
        store.adopt(proof)
    assert caught.value.code == LEGACY_PARTIAL_ADOPTION_REQUIRES_AUTHENTICATED_RETRY


def test_concurrent_identical_adoption_converges_to_one_pair(tmp_path):
    office, _, proof = setup(tmp_path)
    stores = [LegacyStore(office), LegacyStore(office)]
    barrier = threading.Barrier(2)
    results = []

    def adopt(store):
        barrier.wait()
        results.append(store.adopt(proof).status)

    threads = [threading.Thread(target=adopt, args=(store,)) for store in stores]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["ADOPTED", "ALREADY_ADOPTED"]
    assert len(stores[0].all()) == 1


def test_recovery_refuses_a_different_authenticated_entry(tmp_path):
    office, item, proof = setup(tmp_path)
    store = LegacyStore(office)
    result = store.adopt(proof)
    (result.path / "packet.leg1").unlink()
    other = LegacyPacket(
        subject=item.subject, observed_scope=item.observed_scope,
        what_worked="different", what_worked_evidence=item.what_worked_evidence,
        what_failed=item.what_failed, what_failed_evidence=item.what_failed_evidence,
        what_looked_right_but_was_wrong=item.what_looked_right_but_was_wrong,
        what_wrong_evidence=item.what_wrong_evidence, watch_next=item.watch_next,
        watch_next_evidence=item.watch_next_evidence,
        watch_next_status=item.watch_next_status, created=item.created,
    )
    # The source envelope is bound to the original packet, so this proof cannot
    # be forged by merely changing packet data.
    with pytest.raises(SailangError):
        authenticate_legacy(None, other)
    assert store.recover(proof)[0].status == RECOVERY_REPAIRED
