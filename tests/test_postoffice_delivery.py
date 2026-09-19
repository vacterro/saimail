"""T-45 / T-5 acceptance: durable delivery, canonical index, dedup, recovery.

What is proven here, in the order the contract decides it (spec/03 D-031/D-037):

* the caller supplies the Post Office root, and the v0 layout appears under it
  (`mail/inbox/<seat>`, `mail/read/<seat>`, `mail/quarantine`, `expired`,
  `promoted`, `index.jsonl`) with no hardcoded user path;
* a valid SENV2 object is accepted only after parse, sender verification,
  recipient-seat and recipient-key acceptance — and without any private key or
  any payload decryption — then becomes one immutable bundle
  (`envelope.senv` + receiver-owned `receipt.json`) plus exactly one canonical
  index row that carries no plaintext and no ciphertext;
* invalid signature, unknown/unaccepted sender, wrong seat, unaccepted `TO_KID`
  and legacy SENV1 are quarantined under a domain-separated raw-bytes identity
  with a reason code and no active index row; an object over the container's
  hard bound is refused without persisting the hostile body;
* the same exact `ENVELOPE_ID` delivered again is a `DUPLICATE`: no second
  bundle, no second row, the original `RECEIVED_AT` unchanged — including after
  the object moved to `read/`, where a replay resurrects no unread state, while
  a stored read object that does not mechanically match fails closed; the same
  plaintext resealed is a distinct transport object;
* `index.jsonl` enforces exactly one row per `ENVELOPE_ID`, a repeat being
  `INDEX_DUPLICATE_ENVELOPE_ID` rather than silently deduplicated evidence, and
  `ensure_index_row` compares an existing row against the verified header plus
  the original `RECEIVED_AT` instead of merely noticing it, refusing a
  conflicting row as `INDEX_ROW_CONFLICT`;
* the commit order leaves exactly one crash window (bundle present, row
  absent), and `recover()` closes it exactly once with the bundle's own
  original `RECEIVED_AT`;
* concurrent identical delivery cannot corrupt the index or double-commit, and
  a committed bundle is never overwritten — different bytes under the same
  identity fail closed.

Keys are ephemeral and in memory, per D-028/B6.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import threading

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from sailang import SailangError
from saimail import envelope, postoffice
from saimail.envelope import KeyRegistry, RecipientKeyRegistry

SENDER = Ed25519PrivateKey.generate()
OTHER_SENDER = Ed25519PrivateKey.generate()
RECIPIENT = X25519PrivateKey.generate()
OTHER_RECIPIENT = X25519PrivateKey.generate()
SEAT = "B03"
SENDER_SEAT = "A17"
T = "2026-09-18T10:00:00Z"
PLAINTEXT_MARKER = "unique-plaintext-marker"


def err(fn, *a, **k):
    with pytest.raises(SailangError) as e:
        fn(*a, **k)
    return e.value.code


def office_at(tmp_path, *, interest=None, clock=None, sender=SENDER, sender_seat=SENDER_SEAT):
    sender_registry = KeyRegistry({sender_seat: [sender.public_key()]})
    recipient_registry = RecipientKeyRegistry({SEAT: [RECIPIENT.public_key()]})
    office = postoffice.PostOffice(
        tmp_path, seat=SEAT, sender_registry=sender_registry,
        recipient_registry=recipient_registry, interest=interest,
        clock=clock if clock is not None else (lambda: T))
    return office, recipient_registry


def sealed_bytes(payload="payload", *, sender=SENDER, sender_seat=SENDER_SEAT,
                 recipient=RECIPIENT, seat=SEAT, kind="DISCOVERY",
                 topic="queue-ownership", created=T, ref=None):
    return envelope.seal(payload, sender_private_key=sender, sender_seat=sender_seat,
                         recipient_seat=seat, recipient_public_key=recipient.public_key(),
                         kind=kind, topic=topic, created=created, ref=ref).encode("utf-8")


# ------------------------------------------------ layout and acceptance


def test_layout_lives_under_the_caller_supplied_root(tmp_path):
    office, _ = office_at(tmp_path)
    assert office.mail_root == pathlib.Path(tmp_path) / "mail"
    for state in ("inbox", "read"):
        assert (office.mail_root / state / SEAT).is_dir()
    for state in ("quarantine", "expired", "promoted"):
        assert (office.mail_root / state).is_dir()


def test_valid_envelope_becomes_one_bundle_and_one_clean_index_row(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes(payload=PLAINTEXT_MARKER)
    result = office.deliver(raw)
    assert result.status == postoffice.ACCEPTED
    assert result.envelope_id == envelope.envelope_id(raw)
    assert result.received_at == T

    bundle = office.inbox_bundle(result.envelope_id)
    assert (bundle / "envelope.senv").read_bytes() == raw
    receipt = json.loads((bundle / "receipt.json").read_text(encoding="utf-8"))
    assert receipt == {"schema": 1, "envelope_id": result.envelope_id, "received_at": T}

    rows = office.read_index()
    assert len(rows) == 1
    row = rows[0]
    assert row["schema"] == 1
    assert row["envelope_id"] == result.envelope_id
    assert row["received_at"] == T
    assert row["from"] == SENDER_SEAT and row["to"] == SEAT
    assert row["kind"] == "DISCOVERY" and row["topic"] == "queue-ownership"
    assert row["created"] == T
    assert "ref" not in row

    index_text = (office.mail_root / "index.jsonl").read_text(encoding="utf-8")
    assert PLAINTEXT_MARKER not in index_text
    assert "CIPHERTEXT" not in index_text
    assert PLAINTEXT_MARKER not in (bundle / "receipt.json").read_text(encoding="utf-8")


def test_index_row_carries_the_optional_ref_when_present(tmp_path):
    office, _ = office_at(tmp_path)
    referenced = "sha256:" + "a" * 64
    result = office.deliver(sealed_bytes(ref=referenced))
    assert office.read_index()[0]["ref"] == referenced
    assert result.status == postoffice.ACCEPTED


# ------------------------------------------------ authentication / addressing


def _with_flipped_signature(raw: bytes) -> bytes:
    lines = raw.decode("utf-8").split("\n")
    position = next(i for i, line in enumerate(lines) if line.startswith("SIG:"))
    body = lines[position][len("SIG:ed25519:"):]
    flipped = body[:-1] + ("0" if body[-1] != "0" else "1")
    lines[position] = "SIG:ed25519:" + flipped
    return "\n".join(lines).encode("utf-8")


def test_invalid_signature_is_quarantined_without_an_index_row(tmp_path):
    office, _ = office_at(tmp_path)
    raw = _with_flipped_signature(sealed_bytes())
    result = office.deliver(raw)
    assert result.status == postoffice.QUARANTINED
    assert result.reason == "SIGNATURE_INVALID"
    assert office.read_index() == ()
    assert list((office.mail_root / "inbox" / SEAT).iterdir()) == []
    quarantine = office.mail_root / "quarantine" / result.quarantine_id.split(":")[1]
    assert (quarantine / "object.bin").read_bytes() == raw
    assert json.loads((quarantine / "reason.json").read_text(encoding="utf-8"))["reason"] == \
        "SIGNATURE_INVALID"
    # quarantine identity is domain-separated and never an ENVELOPE_ID
    assert result.quarantine_id != envelope.envelope_id(raw)


def test_unaccepted_sender_fingerprint_is_quarantined(tmp_path):
    office, _ = office_at(tmp_path)
    result = office.deliver(sealed_bytes(sender=OTHER_SENDER))
    assert (result.status, result.reason) == (postoffice.QUARANTINED,
                                              "SENDER_KEY_NOT_ACCEPTED")
    assert office.read_index() == ()


def test_unknown_sender_seat_is_quarantined(tmp_path):
    office, _ = office_at(tmp_path)
    result = office.deliver(sealed_bytes(sender=OTHER_SENDER, sender_seat="Z99"))
    assert (result.status, result.reason) == (postoffice.QUARANTINED,
                                              "UNKNOWN_SENDER_KEY")
    assert office.read_index() == ()


def test_wrong_recipient_seat_is_quarantined(tmp_path):
    office, _ = office_at(tmp_path)
    result = office.deliver(sealed_bytes(seat="C99"))
    assert (result.status, result.reason) == (postoffice.QUARANTINED,
                                              postoffice.WRONG_RECIPIENT_SEAT)
    assert office.read_index() == ()


def test_unaccepted_to_kid_is_quarantined(tmp_path):
    office, _ = office_at(tmp_path)
    result = office.deliver(sealed_bytes(recipient=OTHER_RECIPIENT))
    assert (result.status, result.reason) == (postoffice.QUARANTINED,
                                              postoffice.RECIPIENT_KEY_NOT_ACCEPTED)
    assert office.read_index() == ()


def test_legacy_senv1_is_quarantined(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes().replace(b"SENV2\n", b"SENV1\n", 1)
    result = office.deliver(raw)
    assert (result.status, result.reason) == (postoffice.QUARANTINED, "LEGACY_VERSION")
    assert office.read_index() == ()


def test_oversized_input_is_refused_without_persisting_the_body(tmp_path):
    office, _ = office_at(tmp_path)
    raw = b"SENV2\n" + b"x" * (envelope.MAX_CONTAINER_BYTES + 1)
    result = office.deliver(raw)
    assert (result.status, result.reason) == (postoffice.REFUSED,
                                              postoffice.CONTAINER_OVERSIZE)
    assert office.read_index() == ()
    assert list((office.mail_root / "quarantine").iterdir()) == []


# ------------------------------------------------ duplicate semantics


def test_duplicate_delivery_keeps_one_object_one_row_and_original_received_at(tmp_path):
    times = iter(["2026-09-18T10:00:00Z", "2026-09-18T11:00:00Z"])
    office, _ = office_at(tmp_path, clock=lambda: next(times))
    raw = sealed_bytes()
    first = office.deliver(raw)
    second = office.deliver(raw)
    assert first.status == postoffice.ACCEPTED
    assert second.status == postoffice.DUPLICATE
    assert second.envelope_id == first.envelope_id
    assert second.received_at == first.received_at == "2026-09-18T10:00:00Z"
    assert len(office.read_index()) == 1
    assert len(list((office.mail_root / "inbox" / SEAT).iterdir())) == 1


def test_same_plaintext_resealed_is_a_distinct_transport_object(tmp_path):
    office, _ = office_at(tmp_path)
    first = office.deliver(sealed_bytes(payload="same"))
    second = office.deliver(sealed_bytes(payload="same"))
    assert first.envelope_id != second.envelope_id
    assert len(office.read_index()) == 2
    assert office.inbox_bundle(first.envelope_id).is_dir()
    assert office.inbox_bundle(second.envelope_id).is_dir()


# ------------------------------------------------ crash window and concurrency


def test_crash_between_bundle_and_index_recovers_exactly_one_row(tmp_path, monkeypatch):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    original = office.ensure_index_row
    monkeypatch.setattr(office, "ensure_index_row", lambda *a, **k: False)
    crashed = office.deliver(raw)
    assert crashed.status == postoffice.ACCEPTED
    assert office.read_index() == ()
    assert office.inbox_bundle(crashed.envelope_id).is_dir()

    monkeypatch.setattr(office, "ensure_index_row", original)
    recovery = office.recover()
    assert recovery.bundles_scanned == 1 and recovery.rows_appended == 1
    rows = office.read_index()
    assert len(rows) == 1 and rows[0]["received_at"] == crashed.received_at

    replay = office.deliver(raw)
    assert replay.status == postoffice.DUPLICATE
    assert replay.received_at == crashed.received_at
    assert len(office.read_index()) == 1
    assert office.recover().rows_appended == 0


def test_concurrent_identical_delivery_commits_one_row(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    barrier = threading.Barrier(2)
    results = []
    lock = threading.Lock()

    def run():
        barrier.wait()
        outcome = office.deliver(raw)
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert sorted(result.status for result in results) == [postoffice.ACCEPTED,
                                                           postoffice.DUPLICATE]
    assert len({result.received_at for result in results}) == 1
    assert len(office.read_index()) == 1


def test_a_committed_bundle_is_never_overwritten(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    first = office.deliver(raw)
    bundle = office.inbox_bundle(first.envelope_id)
    (bundle / "envelope.senv").write_bytes(b"tampered-bytes")
    assert err(office.deliver, raw) == postoffice.ENVELOPE_ID_CONFLICT
    assert (bundle / "envelope.senv").read_bytes() == b"tampered-bytes"
    assert len(office.read_index()) == 1


# ------------------------------------------------ read-lifecycle dedup (T-46)


def open_first(office, envelope_id):
    session = postoffice.PostOfficeSession(office, scan_budget=8, open_budget=1)
    return session.open_message(envelope_id, recipient_private_key=RECIPIENT)


def test_replay_after_read_is_duplicate_and_never_recreates_unread_state(tmp_path):
    calls = []

    def clock():
        calls.append(1)
        if len(calls) > 1:
            raise AssertionError("a replay must not mint a new RECEIVED_AT")
        return T

    office, _ = office_at(tmp_path, clock=clock)
    raw = sealed_bytes()
    first = office.deliver(raw)
    assert first.status == postoffice.ACCEPTED
    open_first(office, first.envelope_id)
    assert not office.inbox_bundle(first.envelope_id).exists()
    index_before = (office.mail_root / "index.jsonl").read_bytes()

    replay = office.deliver(raw)
    assert replay.status == postoffice.DUPLICATE
    assert replay.envelope_id == first.envelope_id
    assert replay.received_at == first.received_at == T
    assert not office.inbox_bundle(first.envelope_id).exists()
    assert office.bundle_state(first.envelope_id) == postoffice.READ_STATE
    assert (office.read_bundle(first.envelope_id) / "envelope.senv").read_bytes() == raw
    assert (office.mail_root / "index.jsonl").read_bytes() == index_before
    assert len(office.read_index()) == 1


def test_replay_against_a_tampered_read_bundle_fails_closed(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    first = office.deliver(raw)
    open_first(office, first.envelope_id)
    read = office.read_bundle(first.envelope_id)
    tampered = bytearray(raw)
    tampered[-2] ^= 0x01
    assert len(tampered) == len(raw)
    (read / "envelope.senv").write_bytes(bytes(tampered))
    committed = (read / "envelope.senv").read_bytes()

    assert err(office.deliver, raw) == postoffice.READ_BUNDLE_CONFLICT
    assert (read / "envelope.senv").read_bytes() == committed
    assert office.bundle_state(first.envelope_id) == postoffice.READ_STATE
    assert len(office.read_index()) == 1


def test_inbox_read_pairs_are_not_reconciled_by_receipt_and_size_alone(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    first = office.deliver(raw)
    read = office.read_bundle(first.envelope_id)
    shutil.copytree(office.inbox_bundle(first.envelope_id), read)
    tampered = bytearray(raw)
    tampered[-2] ^= 0x01
    (read / "envelope.senv").write_bytes(bytes(tampered))
    session = postoffice.PostOfficeSession(office, scan_budget=8, open_budget=1)
    assert err(session.scan, now=T) == postoffice.RECONCILIATION_REQUIRED
    assert err(session.open_message, first.envelope_id,
               recipient_private_key=RECIPIENT) == postoffice.RECONCILIATION_REQUIRED
    assert err(office.recover) == postoffice.READ_BUNDLE_CONFLICT
    assert office.inbox_bundle(first.envelope_id).is_dir()
    assert read.is_dir()


# ------------------------------------------------ index uniqueness (T-46)


def canonical_line(row):
    return (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def index_rows(office):
    path = office.mail_root / "index.jsonl"
    return [json.loads(line) for line in path.read_bytes().decode("utf-8").splitlines()]


def rewrite_index(office, rows):
    (office.mail_root / "index.jsonl").write_bytes(
        b"".join(canonical_line(row) for row in rows))


def test_index_refuses_a_second_row_for_the_same_envelope_id(tmp_path):
    office, _ = office_at(tmp_path)
    office.deliver(sealed_bytes())
    index = office.mail_root / "index.jsonl"
    line = index.read_bytes()
    index.write_bytes(line + line)
    assert err(office.read_index) == postoffice.INDEX_DUPLICATE_ENVELOPE_ID
    session = postoffice.PostOfficeSession(office, scan_budget=8, open_budget=8)
    assert err(session.scan, now=T) == postoffice.INDEX_DUPLICATE_ENVELOPE_ID


def test_index_refuses_a_changed_row_for_the_same_envelope_id(tmp_path):
    office, _ = office_at(tmp_path)
    office.deliver(sealed_bytes())
    row = index_rows(office)[0]
    original = (office.mail_root / "index.jsonl").read_bytes()
    for field, value in (("topic", "some-other-topic"),
                         ("kind", "WARNING"),
                         ("received_at", "2026-09-18T11:00:00Z")):
        altered = dict(row)
        altered[field] = value
        (office.mail_root / "index.jsonl").write_bytes(original + canonical_line(altered))
        assert err(office.read_index) == postoffice.INDEX_DUPLICATE_ENVELOPE_ID


def test_ensure_index_row_is_idempotent_against_a_matching_row(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    result = office.deliver(raw)
    header = envelope.parse_header(raw)
    assert office.ensure_index_row(header, result.envelope_id,
                                   result.received_at) is False
    assert len(office.read_index()) == 1


def test_ensure_index_row_refuses_a_conflicting_row(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    result = office.deliver(raw)
    header = envelope.parse_header(raw)
    row = index_rows(office)[0]
    row["topic"] = "rewritten-topic"
    rewrite_index(office, [row])
    before = (office.mail_root / "index.jsonl").read_bytes()
    assert err(office.ensure_index_row, header, result.envelope_id,
               result.received_at) == postoffice.INDEX_ROW_CONFLICT
    assert (office.mail_root / "index.jsonl").read_bytes() == before


def test_recovery_refuses_a_conflicting_index_row(tmp_path):
    office, _ = office_at(tmp_path)
    office.deliver(sealed_bytes())
    row = index_rows(office)[0]
    row["received_at"] = "2026-09-18T11:00:00Z"
    rewrite_index(office, [row])
    before = (office.mail_root / "index.jsonl").read_bytes()
    assert err(office.recover) == postoffice.INDEX_ROW_CONFLICT
    assert (office.mail_root / "index.jsonl").read_bytes() == before
