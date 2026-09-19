"""T-7 acceptance: receiver-owned TTL sweep, immutable tombstones, no resurrection.

What is proven here, in the order the contract decides it (D-038):

* retention is receiver-owned: the default sits inside the declared 7–30 day
  range and an out-of-range policy is refused, never clamped; the signed
  `TTL` header is a retention CEILING (`effective = min(sender, default)`), so a
  sender may request shorter retention and can never force longer; a `TTL:0H`
  body is eligible on the first explicit sweep and nothing is ever auto-deleted
  during delivery;
* the expiry clock is receiver-local (`RECEIVED_AT + effective_ttl`), so a
  future or ancient sender `CREATED` cannot move it;
* `sweep_expired` is the ONLY TTL entry point — explicit maintenance, never
  inside deliver/scan/open/recover, no daemon, timer, scheduler or worker;
* an eligible body is mechanically re-verified, then an immutable tombstone is
  published BEFORE the body is deleted; the tombstone carries no plaintext and
  no ciphertext, the index row survives, and a non-eligible body is retained;
* a corrupt bundle, a conflicting index row, a conflicting tombstone and a
  conflicting crash pair all fail closed with the body kept; an identical
  tombstone re-sweep is idempotent;
* scan treats an intentionally expired body as `EXPIRED` (skipped, not
  `INDEX_BODY_MISSING`), stays header-only, still charges the examined row, and
  reports `EXPIRY_RECONCILIATION_REQUIRED` for a tombstone beside a live body;
  a body with no tombstone stays `INDEX_BODY_MISSING`;
* open of an expired id is `ALREADY_EXPIRED` with no decrypt and no budget
  consumption; exact redelivery of an expired `ENVELOPE_ID` is `DUPLICATE` with
  the original `RECEIVED_AT` and resurrects nothing, while the same plaintext
  freshly resealed is a new object;
* the one normal destructive crash window (tombstone published, body not yet
  deleted) is finished by `recover()`, and a conflicting pair is
  `EXPIRY_STATE_CONFLICT`;
* the OS lifecycle lock is the authority, order is lifecycle-then-index, and
  T-7 never touches the promotion layer.

Keys are ephemeral and in memory, per D-028/B6.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import threading
from datetime import datetime, timedelta, timezone

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from sailang import SailangError
from saimail import envelope, postoffice
from saimail.envelope import KeyRegistry, RecipientKeyRegistry

SENDER = Ed25519PrivateKey.generate()
RECIPIENT = X25519PrivateKey.generate()
OTHER_RECIPIENT = X25519PrivateKey.generate()
SEAT = "B03"
SENDER_SEAT = "A17"
T = "2026-09-18T10:00:00Z"
DAY = 24 * 60 * 60
PLAINTEXT_MARKER = "unique-expiry-plaintext-marker"


def err(fn, *a, **k):
    with pytest.raises(SailangError) as e:
        fn(*a, **k)
    return e.value.code


def office_at(tmp_path, *, interest=None, clock=None, default_ttl=postoffice.DEFAULT_TTL_SECONDS,
              sender=SENDER, sender_seat=SENDER_SEAT):
    sender_registry = KeyRegistry({sender_seat: [sender.public_key()]})
    recipient_registry = RecipientKeyRegistry({SEAT: [RECIPIENT.public_key()]})
    office = postoffice.PostOffice(
        tmp_path, seat=SEAT, sender_registry=sender_registry,
        recipient_registry=recipient_registry, interest=interest,
        clock=clock if clock is not None else (lambda: T), default_ttl=default_ttl)
    return office, recipient_registry


def sealed_bytes(payload=PLAINTEXT_MARKER, *, sender=SENDER, sender_seat=SENDER_SEAT,
                 recipient=RECIPIENT, seat=SEAT, kind="DISCOVERY",
                 topic="queue-ownership", created=T, ttl=None, ref=None):
    return envelope.seal(payload, sender_private_key=sender, sender_seat=sender_seat,
                         recipient_seat=seat, recipient_public_key=recipient.public_key(),
                         kind=kind, topic=topic, created=created, ttl=ttl,
                         ref=ref).encode("utf-8")


def deliver(office, **kwargs):
    result = office.deliver(sealed_bytes(**kwargs))
    assert result.status == postoffice.ACCEPTED
    return result


def session_for(office, *, scan_budget=8, open_budget=8):
    return postoffice.PostOfficeSession(office, scan_budget=scan_budget,
                                        open_budget=open_budget)


def instant(text):
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def later(days=15, hours=0):
    return instant(T) + timedelta(days=days, hours=hours)


def tombstone_of(office, envelope_id):
    return json.loads(office.expired_tombstone(envelope_id).read_text(encoding="utf-8"))


# ================================================ CONTRACT (D-038 §1–2)


def test_absent_ttl_uses_the_receiver_default(tmp_path):
    office, _ = office_at(tmp_path)
    assert office.default_ttl == 14 * DAY
    assert postoffice.effective_ttl_seconds(envelope.parse_header(sealed_bytes()), office.default_ttl) \
        == 14 * DAY


@pytest.mark.parametrize("bad", [0, 6 * DAY, 31 * DAY, 7 * DAY - 1, 30 * DAY + 1])
def test_receiver_default_outside_the_range_is_refused(tmp_path, bad):
    assert err(office_at, tmp_path, default_ttl=bad) == postoffice.RECEIVER_TTL_OUT_OF_RANGE


@pytest.mark.parametrize("bad", [-1, 1.5, True, "14D", None])
def test_receiver_default_of_the_wrong_shape_is_refused(tmp_path, bad):
    assert err(office_at, tmp_path, default_ttl=bad) == postoffice.BAD_TTL_POLICY


@pytest.mark.parametrize("bound", [7 * DAY, 30 * DAY])
def test_receiver_default_range_bounds_are_accepted(tmp_path, bound):
    office, _ = office_at(tmp_path, default_ttl=bound)
    assert office.default_ttl == bound


def test_sender_ttl_shorter_than_default_wins(tmp_path):
    office, _ = office_at(tmp_path)
    header = envelope.parse_header(sealed_bytes(ttl="7D"))
    assert postoffice.effective_ttl_seconds(header, office.default_ttl) == 7 * DAY


def test_sender_ttl_longer_than_default_is_capped(tmp_path):
    office, _ = office_at(tmp_path)
    header = envelope.parse_header(sealed_bytes(ttl="30D"))
    assert postoffice.effective_ttl_seconds(header, office.default_ttl) == 14 * DAY


def test_zero_ttl_is_eligible_on_the_first_explicit_sweep(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office, ttl="0H")
    sweep = office.sweep_expired(now=T)
    assert (sweep.expired, sweep.retained) == (1, 0)
    assert office.bundle_state(result.envelope_id) == postoffice.EXPIRED_STATE


def test_zero_ttl_is_not_deleted_during_delivery(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office, ttl="0H")
    assert office.bundle_state(result.envelope_id) == postoffice.UNREAD
    assert office.inbox_bundle(result.envelope_id).is_dir()


def test_expiry_uses_received_at_not_created(tmp_path):
    office, _ = office_at(tmp_path)
    ancient = deliver(office, created="1999-01-01T00:00:00Z")
    future = deliver(office, created="2099-01-01T00:00:00Z")
    # A CREATED far outside the window changes nothing: both expire 14D after
    # the receiver-local RECEIVED_AT, never relative to CREATED.
    sweep = office.sweep_expired(now=later(days=13))
    assert sweep.retained == 2 and sweep.expired == 0
    sweep = office.sweep_expired(now=later(days=14, hours=1))
    assert sweep.expired == 2
    for result in (ancient, future):
        assert office.bundle_state(result.envelope_id) == postoffice.EXPIRED_STATE


# ================================================ SWEEP (D-038 §3–4)


def test_unread_eligible_body_becomes_tombstone_and_body_removed(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    index_before = (office.mail_root / "index.jsonl").read_bytes()
    sweep = office.sweep_expired(now=later(days=15))
    assert (sweep.examined, sweep.expired, sweep.retained) == (1, 1, 0)
    assert not office.inbox_bundle(result.envelope_id).exists()
    assert office.expired_tombstone(result.envelope_id).is_file()
    assert (office.mail_root / "index.jsonl").read_bytes() == index_before
    assert len(office.read_index()) == 1


def test_read_eligible_body_becomes_tombstone_and_body_removed(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    session_for(office, open_budget=1).open_message(result.envelope_id,
                                                    recipient_private_key=RECIPIENT)
    sweep = office.sweep_expired(now=later(days=15))
    assert sweep.expired == 1
    assert not office.read_bundle(result.envelope_id).exists()
    assert office.expired_tombstone(result.envelope_id).is_file()
    assert len(office.read_index()) == 1


def test_non_eligible_object_is_retained(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    sweep = office.sweep_expired(now=later(days=13))
    assert (sweep.retained, sweep.expired) == (1, 0)
    assert office.inbox_bundle(result.envelope_id).is_dir()
    assert not office.expired_tombstone(result.envelope_id).exists()


def test_tombstone_schema_and_no_ciphertext_or_plaintext(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    office.sweep_expired(now=later(days=15))
    raw = office.expired_tombstone(result.envelope_id).read_bytes()
    tombstone = json.loads(raw.decode("utf-8"))
    assert set(tombstone) == {
        "schema", "envelope_id", "sender", "recipient", "kind", "received_at",
        "expired_at", "effective_ttl_seconds", "reason"}
    assert tombstone["schema"] == 1
    assert tombstone["envelope_id"] == result.envelope_id
    assert tombstone["sender"] == SENDER_SEAT and tombstone["recipient"] == SEAT
    assert tombstone["kind"] == "DISCOVERY"
    assert tombstone["received_at"] == T
    assert tombstone["expired_at"] == "2026-10-03T10:00:00Z"
    assert tombstone["effective_ttl_seconds"] == 14 * DAY
    assert tombstone["reason"] == postoffice.TTL_EXPIRED
    text = raw.decode("utf-8")
    assert PLAINTEXT_MARKER not in text and "CIPHERTEXT" not in text


def test_identical_tombstone_resweep_is_idempotent(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    office.sweep_expired(now=later(days=15))
    committed = office.expired_tombstone(result.envelope_id).read_bytes()
    sweep = office.sweep_expired(now=later(days=16))
    assert (sweep.expired, sweep.already_expired) == (0, 1)
    assert office.expired_tombstone(result.envelope_id).read_bytes() == committed


def test_conflicting_tombstone_refuses_and_keeps_the_body(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    bundle = office.inbox_bundle(result.envelope_id)
    header, stored_at = office._verify_bundle(bundle, result.envelope_id)
    office.expired_tombstone(result.envelope_id).write_bytes(b'{"different":"tombstone"}\n')
    before = office.expired_tombstone(result.envelope_id).read_bytes()
    assert err(office._expire_bundle, bundle, header, result.envelope_id, stored_at,
               14 * DAY, instant(T)) == postoffice.EXPIRED_TOMBSTONE_CONFLICT
    assert bundle.is_dir()
    assert office.expired_tombstone(result.envelope_id).read_bytes() == before


def test_corrupted_bundle_refuses_without_deletion(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    bundle = office.inbox_bundle(result.envelope_id)
    tampered = bytearray((bundle / "envelope.senv").read_bytes())
    tampered[-2] ^= 0x01
    (bundle / "envelope.senv").write_bytes(bytes(tampered))
    assert err(office.sweep_expired, now=later(days=15)) == postoffice.BUNDLE_INVALID
    assert bundle.is_dir()
    assert not office.expired_tombstone(result.envelope_id).exists()


def test_conflicting_index_row_refuses_without_deletion(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    row = office.read_index()[0]
    row["received_at"] = "2026-09-18T11:00:00Z"
    (office.mail_root / "index.jsonl").write_bytes(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8"))
    assert err(office.sweep_expired, now=later(days=15)) == postoffice.INDEX_ROW_CONFLICT
    assert office.inbox_bundle(result.envelope_id).is_dir()
    assert not office.expired_tombstone(result.envelope_id).exists()


def test_sweep_ignores_quarantine_and_promoted(tmp_path):
    office, _ = office_at(tmp_path)
    deliver(office)
    (office.mail_root / "quarantine" / "some-dir").mkdir()
    (office.mail_root / "promoted" / "some-dir").mkdir()
    sweep = office.sweep_expired(now=later(days=15))
    assert sweep.expired == 1
    assert (office.mail_root / "quarantine" / "some-dir").is_dir()
    assert (office.mail_root / "promoted" / "some-dir").is_dir()


# ================================================ CRASH (D-038 §5, C4)


def crash_after_tombstone(monkeypatch, office, envelope_id):
    real = shutil.rmtree

    def boom(path, *a, **k):
        if pathlib.Path(path).name == envelope_id.split(":", 1)[1]:
            raise OSError("simulated crash before body deletion")
        return real(path, *a, **k)

    monkeypatch.setattr(postoffice.shutil, "rmtree", boom)
    with pytest.raises(OSError):
        office.sweep_expired(now=later(days=15))
    monkeypatch.setattr(postoffice.shutil, "rmtree", real)


def test_crash_after_tombstone_before_body_deletion_leaves_both(tmp_path, monkeypatch):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    crash_after_tombstone(monkeypatch, office, result.envelope_id)
    assert office.expired_tombstone(result.envelope_id).is_file()
    assert office.inbox_bundle(result.envelope_id).is_dir()
    assert office.bundle_state(result.envelope_id) == postoffice.EXPIRY_RECONCILIATION_REQUIRED


def test_scan_on_the_crash_pair_requires_reconciliation(tmp_path, monkeypatch):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    crash_after_tombstone(monkeypatch, office, result.envelope_id)
    assert err(session_for(office).scan, now=later(days=15)) == \
        postoffice.EXPIRY_RECONCILIATION_REQUIRED


def test_recover_finishes_the_crash_expiry(tmp_path, monkeypatch):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    crash_after_tombstone(monkeypatch, office, result.envelope_id)
    recovery = office.recover()
    assert recovery.rows_appended == 0
    assert not office.inbox_bundle(result.envelope_id).exists()
    assert office.expired_tombstone(result.envelope_id).is_file()
    assert office.bundle_state(result.envelope_id) == postoffice.EXPIRED_STATE
    # A second recovery is idempotent.
    assert office.recover().rows_appended == 0
    assert office.expired_tombstone(result.envelope_id).is_file()


def test_conflicting_crash_pair_is_expiry_state_conflict(tmp_path, monkeypatch):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    crash_after_tombstone(monkeypatch, office, result.envelope_id)
    path = office.expired_tombstone(result.envelope_id)
    tombstone = json.loads(path.read_text(encoding="utf-8"))
    tombstone["sender"] = "Z99"
    path.write_bytes((json.dumps(tombstone, sort_keys=True, separators=(",", ":")) + "\n")
                     .encode("utf-8"))
    committed = path.read_bytes()
    assert err(office.recover) == postoffice.EXPIRY_STATE_CONFLICT
    assert path.read_bytes() == committed
    assert office.inbox_bundle(result.envelope_id).is_dir()


# ================================================ SCAN (D-038 §7, C1)


def test_expired_indexed_envelope_is_skipped_not_body_missing(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    office.sweep_expired(now=later(days=15))
    scan = session_for(office).scan(now=later(days=15))
    assert scan.items == ()
    assert scan.rows_examined == 1  # the row was examined, so the unit is charged


def test_missing_body_without_tombstone_stays_body_missing(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    shutil.rmtree(office.inbox_bundle(result.envelope_id))
    assert err(session_for(office).scan, now=later(days=15)) == postoffice.INDEX_BODY_MISSING


def test_expired_scan_still_never_reads_senv(tmp_path, monkeypatch):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    office.sweep_expired(now=later(days=15))
    real = pathlib.Path.read_bytes

    def guarded(self):
        if self.suffix == ".senv":
            raise AssertionError(f"scan read payload bytes from {self.name}")
        return real(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", guarded)
    scan = session_for(office).scan(now=later(days=15))
    assert scan.items == ()
    assert scan.rows_examined == 1
    assert not office.inbox_bundle(result.envelope_id).exists()


# ================================================ OPEN (D-038 §8, C2)


def test_open_expired_is_already_expired(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    office.sweep_expired(now=later(days=15))
    session = session_for(office, open_budget=2)
    assert err(session.open_message, result.envelope_id,
               recipient_private_key=RECIPIENT) == postoffice.ALREADY_EXPIRED


def test_open_expired_performs_no_decrypt(tmp_path, monkeypatch):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    office.sweep_expired(now=later(days=15))

    def forbidden(*a, **k):
        raise AssertionError("an expired message must never be decrypted")

    monkeypatch.setattr(postoffice.envelope, "open", forbidden)
    session = session_for(office, open_budget=2)
    assert err(session.open_message, result.envelope_id,
               recipient_private_key=RECIPIENT) == postoffice.ALREADY_EXPIRED


def test_open_expired_does_not_consume_open_budget(tmp_path):
    office, _ = office_at(tmp_path)
    expired = deliver(office)
    office.sweep_expired(now=later(days=15))
    fresh = deliver(office, topic="fresh-topic")
    session = session_for(office, open_budget=1)
    assert err(session.open_message, expired.envelope_id,
               recipient_private_key=RECIPIENT) == postoffice.ALREADY_EXPIRED
    assert session.open_attempts_used == 0
    opened = session.open_message(fresh.envelope_id, recipient_private_key=RECIPIENT)
    assert opened.envelope_id == fresh.envelope_id


# ================================================ REDELIVERY (D-038 §8, C3)


def test_exact_redelivery_of_expired_id_is_duplicate(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    first = office.deliver(raw)
    office.sweep_expired(now=later(days=15))
    replay = office.deliver(raw)
    assert replay.status == postoffice.DUPLICATE
    assert replay.received_at == first.received_at == T


def test_expired_redelivery_resurrects_nothing(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    first = office.deliver(raw)
    office.sweep_expired(now=later(days=15))
    index_before = (office.mail_root / "index.jsonl").read_bytes()
    tombstone_before = office.expired_tombstone(first.envelope_id).read_bytes()
    office.deliver(raw)
    assert not office.inbox_bundle(first.envelope_id).exists()
    assert not office.read_bundle(first.envelope_id).exists()
    assert (office.mail_root / "index.jsonl").read_bytes() == index_before
    assert len(office.read_index()) == 1
    assert office.expired_tombstone(first.envelope_id).read_bytes() == tombstone_before


def test_same_plaintext_resealed_after_expiry_is_a_new_object(tmp_path):
    office, _ = office_at(tmp_path)
    first = office.deliver(sealed_bytes(payload="same"))
    office.sweep_expired(now=later(days=15))
    second = office.deliver(sealed_bytes(payload="same"))
    assert second.status == postoffice.ACCEPTED
    assert second.envelope_id != first.envelope_id
    assert len(office.read_index()) == 2
    assert office.inbox_bundle(second.envelope_id).is_dir()


def test_redelivery_against_a_corrupt_tombstone_fails_closed(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    first = office.deliver(raw)
    office.sweep_expired(now=later(days=15))
    path = office.expired_tombstone(first.envelope_id)
    path.write_bytes(b"not-a-tombstone\n")
    committed = path.read_bytes()
    assert err(office.deliver, raw) == postoffice.EXPIRED_TOMBSTONE_CORRUPT
    assert path.read_bytes() == committed


# ================================================ CONCURRENCY (D-038 §9, C5–C7)


def test_open_vs_sweep_converges_to_one_coherent_state(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    barrier = threading.Barrier(2)
    outcomes = []
    lock = threading.Lock()

    def do_open():
        barrier.wait()
        session = session_for(office, open_budget=1)
        try:
            session.open_message(result.envelope_id, recipient_private_key=RECIPIENT)
            outcome = "OPENED"
        except SailangError as exc:
            outcome = exc.code
        with lock:
            outcomes.append(outcome)

    def do_sweep():
        barrier.wait()
        office.sweep_expired(now=later(days=15))

    threads = [threading.Thread(target=do_open), threading.Thread(target=do_sweep)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    state = office.bundle_state(result.envelope_id)
    assert state == postoffice.EXPIRED_STATE
    # Never two conflicting bodies, never a body without a tombstone.
    assert not office.inbox_bundle(result.envelope_id).exists()
    assert not office.read_bundle(result.envelope_id).exists()
    assert office.expired_tombstone(result.envelope_id).is_file()
    assert outcomes in (["OPENED"], [postoffice.ALREADY_EXPIRED])
    # A later open never resurrects a payload.
    session = session_for(office, open_budget=1)
    assert err(session.open_message, result.envelope_id,
               recipient_private_key=RECIPIENT) == postoffice.ALREADY_EXPIRED


def test_replay_delivery_vs_sweep_cannot_resurrect_unread(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    first = office.deliver(raw)
    barrier = threading.Barrier(2)

    def do_replay():
        barrier.wait()
        office.deliver(raw)

    def do_sweep():
        barrier.wait()
        office.sweep_expired(now=later(days=15))

    threads = [threading.Thread(target=do_replay), threading.Thread(target=do_sweep)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not office.inbox_bundle(first.envelope_id).exists()
    assert not office.read_bundle(first.envelope_id).exists()
    assert office.expired_tombstone(first.envelope_id).is_file()
    rows = office.read_index()
    assert len(rows) == 1 and rows[0]["received_at"] == T
    replay = office.deliver(raw)
    assert replay.status == postoffice.DUPLICATE and replay.received_at == T


def test_two_sweepers_converge_idempotently(tmp_path):
    office, _ = office_at(tmp_path)
    result = deliver(office)
    barrier = threading.Barrier(2)
    outcomes = []
    lock = threading.Lock()

    def do_sweep():
        barrier.wait()
        outcome = office.sweep_expired(now=later(days=15))
        with lock:
            outcomes.append(outcome)

    threads = [threading.Thread(target=do_sweep) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert sum(o.expired for o in outcomes) == 1
    assert office.expired_tombstone(result.envelope_id).is_file()
    assert not office.inbox_bundle(result.envelope_id).exists()
    assert len(office.read_index()) == 1


def test_lifecycle_lock_is_released_on_operation_exit(tmp_path):
    office, _ = office_at(tmp_path)
    with office._lifecycle_lock():
        pass
    # Re-acquiring after release proves the OS lock was released, not merely
    # that the file exists.
    with office._lifecycle_lock():
        pass


def test_lock_ordering_is_lifecycle_then_index(tmp_path, monkeypatch):
    office, _ = office_at(tmp_path)
    order = []
    lifecycle = postoffice._LifecycleLock
    mailbox = postoffice._MailboxLock
    real_lifecycle_enter = lifecycle.__enter__
    real_lifecycle_exit = lifecycle.__exit__
    real_index_enter = mailbox.__enter__
    held = {"lifecycle": 0}

    def lifecycle_enter(self):
        held["lifecycle"] += 1
        order.append("lifecycle")
        return real_lifecycle_enter(self)

    def lifecycle_exit(self, *exc):
        held["lifecycle"] -= 1
        return real_lifecycle_exit(self, *exc)

    def index_enter(self):
        assert held["lifecycle"] > 0, "index lock must never be taken before lifecycle"
        order.append("index")
        return real_index_enter(self)

    monkeypatch.setattr(lifecycle, "__enter__", lifecycle_enter)
    monkeypatch.setattr(lifecycle, "__exit__", lifecycle_exit)
    monkeypatch.setattr(mailbox, "__enter__", index_enter)
    result = deliver(office)
    office.sweep_expired(now=later(days=15))
    assert order[0] == "lifecycle"


# ================================================ PROMOTION BOUNDARY (D-038 §8)


def test_sweep_never_calls_promotion(tmp_path, monkeypatch):
    from saimail import promotion

    def forbidden(*a, **k):
        raise AssertionError("TTL sweep must not promote; MESSAGE != MEMORY")

    monkeypatch.setattr(promotion, "propose", forbidden)
    office, _ = office_at(tmp_path)
    deliver(office)
    office.sweep_expired(now=later(days=15))


def test_postoffice_imports_no_promotion_or_network_layer():
    source = pathlib.Path(postoffice.__file__).read_text(encoding="utf-8")
    imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    assert not any("promotion" in line for line in imports)
    assert "SAIFREN" not in source and "9router" not in source
    assert "propose" not in source
