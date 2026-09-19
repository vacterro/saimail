"""T-49 acceptance: tombstone authority and one-pass expiry convergence.

What is proven here, in the order the contract decides it:

TARGET A — a tombstone must PROVE the exact transport object and index state
it represents (never file existence alone):

* a body-absent indexed envelope with a non-JSON / non-canonical / missing-key
  tombstone is `EXPIRED_TOMBSTONE_CORRUPT`, never `EXPIRED`; scan/open refuse it
  instead of silently masking `INDEX_BODY_MISSING`;
* a structurally valid tombstone whose JSON `envelope_id` disagrees with its own
  file-name digest is refused (path and object must agree);
* a tombstone whose `sender`/`recipient`/`kind`/`received_at` disagrees with the
  canonical index row is `EXPIRED_TOMBSTONE_CONFLICT`;
* an exact redelivery of X requires a tombstone that actually describes X: a
  tombstone under X's name claiming another sender/kind can never suppress the
  delivery as `DUPLICATE`;
* a valid, bound tombstone keeps the existing `EXPIRED` scan-skip / open
  `ALREADY_EXPIRED` / redelivery `DUPLICATE` behavior green.

TARGET B — every expiry crash/BOTH state converges to one coherent EXPIRED state
in ONE successful maintenance pass:

* `valid tombstone + inbox + read` -> a single `recover()` leaves only the
  tombstone (`EXPIRED`), never a leftover body or a second `EXPIRY_
  RECONCILIATION_REQUIRED`;
* a conflicting inbox/read pair refuses and destroys no last-good body;
* a BOTH pair (no tombstone) that is sweep-eligible converges to one coherent
  EXPIRED in one sweep, never a successful sweep that leaves a live body;
* a tombstone whose `effective_ttl_seconds` was altered, or whose `expired_at`
  is earlier than eligibility, is refused and the body retained (premature
  deletion is impossible);
* a crash that deletes only one of two exact copies converges on the next
  `recover()`;
* ordinary single-body expiry, open-vs-sweep / delivery-vs-sweep concurrency,
  and the header-only scan (never reading `.senv`) stay green.

Keys are ephemeral and in memory, per D-028/B6.
"""

from __future__ import annotations

import json
import shutil
import threading
from datetime import datetime, timezone

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from sailang import SailangError
from saimail import envelope, postoffice
from saimail.envelope import KeyRegistry, RecipientKeyRegistry

SENDER = Ed25519PrivateKey.generate()
RECIPIENT = X25519PrivateKey.generate()
SEAT = "B03"
SENDER_SEAT = "A17"
T = "2026-09-18T10:00:00Z"
DAY = 24 * 60 * 60
PLAINTEXT_MARKER = "unique-expiry-authority-marker"


def err(fn, *a, **k):
    with pytest.raises(SailangError) as e:
        fn(*a, **k)
    return e.value.code


def office_at(tmp_path, *, clock=None, default_ttl=postoffice.DEFAULT_TTL_SECONDS):
    office = postoffice.PostOffice(
        tmp_path, seat=SEAT,
        sender_registry=KeyRegistry({SENDER_SEAT: [SENDER.public_key()]}),
        recipient_registry=RecipientKeyRegistry({SEAT: [RECIPIENT.public_key()]}),
        clock=clock if clock is not None else (lambda: T), default_ttl=default_ttl)
    return office


def sealed_bytes(payload=PLAINTEXT_MARKER, *, kind="DISCOVERY", topic="queue-ownership",
                 ttl=None, sender=SENDER, sender_seat=SENDER_SEAT):
    return envelope.seal(payload, sender_private_key=sender, sender_seat=sender_seat,
                         recipient_seat=SEAT, recipient_public_key=RECIPIENT.public_key(),
                         kind=kind, topic=topic, created=T, ttl=ttl).encode("utf-8")


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
    import datetime as _dt
    return instant(T) + _dt.timedelta(days=days, hours=hours)


def expire(office, envelope_id, *, now=None):
    result = office.sweep_expired(now=now if now is not None else later(days=15))
    assert result.expired == 1
    return result


def tombstone_path(office, envelope_id):
    return office.expired_tombstone(envelope_id)


def retype_tombstone(office, eid, **changes):
    """Rewrite the tombstone JSON preserving canonical form (for corrupt fixtures)."""
    path = tombstone_path(office, eid)
    tombstone = json.loads(path.read_text(encoding="utf-8"))
    tombstone.update(changes)
    path.write_bytes((json.dumps(tombstone, sort_keys=True, separators=(",", ":")) + "\n")
                     .encode("utf-8"))


# ================================================ TARGET A — tombstone authority


def test_body_absent_with_non_json_tombstone_is_corrupt_not_expired(tmp_path):
    office = office_at(tmp_path)
    result = deliver(office)
    shutil.rmtree(office.inbox_bundle(result.envelope_id))
    tombstone_path(office, result.envelope_id).write_bytes(b"not-json\n")
    assert err(office.bundle_state, result.envelope_id) == postoffice.EXPIRED_TOMBSTONE_CORRUPT
    assert err(session_for(office).scan, now=later(days=15)) == \
        postoffice.EXPIRED_TOMBSTONE_CORRUPT
    assert err(session_for(office).open_message, result.envelope_id,
               recipient_private_key=RECIPIENT) == postoffice.EXPIRED_TOMBSTONE_CORRUPT


def test_missing_tombstone_still_body_missing_not_corrupt(tmp_path):
    office = office_at(tmp_path)
    result = deliver(office)
    shutil.rmtree(office.inbox_bundle(result.envelope_id))
    assert err(session_for(office).scan, now=later(days=15)) == postoffice.INDEX_BODY_MISSING


def test_tombstone_with_wrong_keys_is_corrupt(tmp_path):
    office = office_at(tmp_path)
    result = deliver(office)
    expire(office, result.envelope_id)
    path = tombstone_path(office, result.envelope_id)
    tombstone = json.loads(path.read_text(encoding="utf-8"))
    del tombstone["kind"]
    path.write_bytes((json.dumps(tombstone, sort_keys=True, separators=(",", ":")) + "\n")
                     .encode("utf-8"))
    assert err(office.bundle_state, result.envelope_id) == postoffice.EXPIRED_TOMBSTONE_CORRUPT


def test_non_canonical_tombstone_is_corrupt(tmp_path):
    office = office_at(tmp_path)
    result = deliver(office)
    expire(office, result.envelope_id)
    path = tombstone_path(office, result.envelope_id)
    tombstone = json.loads(path.read_text(encoding="utf-8"))
    path.write_bytes(json.dumps(tombstone, indent=2).encode("utf-8") + b"\n")
    assert err(office.bundle_state, result.envelope_id) == postoffice.EXPIRED_TOMBSTONE_CORRUPT


def test_tombstone_filename_and_envelope_id_must_agree(tmp_path):
    office = office_at(tmp_path)
    raw = sealed_bytes()
    result = office.deliver(raw)
    expire(office, result.envelope_id)
    retype_tombstone(office, result.envelope_id, envelope_id="sha256:" + "b" * 64)
    assert err(session_for(office).scan, now=later(days=15)) == \
        postoffice.EXPIRED_TOMBSTONE_CORRUPT
    assert err(office.deliver, raw) == postoffice.EXPIRED_TOMBSTONE_CORRUPT


def test_tombstone_sender_disagreement_with_index_is_conflict(tmp_path):
    office = office_at(tmp_path)
    raw = sealed_bytes()
    result = office.deliver(raw)
    expire(office, result.envelope_id)
    retype_tombstone(office, result.envelope_id, sender="Z99")
    assert err(session_for(office).scan, now=later(days=15)) == \
        postoffice.EXPIRED_TOMBSTONE_CONFLICT
    assert err(office.deliver, raw) == postoffice.EXPIRED_TOMBSTONE_CONFLICT


def test_tombstone_kind_disagreement_with_index_is_conflict(tmp_path):
    office = office_at(tmp_path)
    raw = sealed_bytes()
    result = office.deliver(raw)
    expire(office, result.envelope_id)
    retype_tombstone(office, result.envelope_id, kind="WARNING")
    assert err(session_for(office).scan, now=later(days=15)) == \
        postoffice.EXPIRED_TOMBSTONE_CONFLICT
    assert err(office.deliver, raw) == postoffice.EXPIRED_TOMBSTONE_CONFLICT


def test_tombstone_received_at_disagreement_with_index_is_conflict(tmp_path):
    office = office_at(tmp_path)
    result = deliver(office)
    expire(office, result.envelope_id)
    retype_tombstone(office, result.envelope_id, received_at="2026-09-18T11:00:00Z")
    assert err(office.bundle_state, result.envelope_id) == \
        postoffice.EXPIRED_TOMBSTONE_CONFLICT


def test_tombstone_without_index_row_is_refused(tmp_path):
    office = office_at(tmp_path)
    result = deliver(office)
    expire(office, result.envelope_id)
    (office.mail_root / "index.jsonl").write_bytes(b"")
    assert err(office.bundle_state, result.envelope_id) == \
        postoffice.EXPIRED_TOMBSTONE_CONFLICT


def test_exact_redelivery_requires_a_tombstone_that_describes_that_envelope(tmp_path):
    office = office_at(tmp_path)
    raw = sealed_bytes()
    first = office.deliver(raw)
    expire(office, first.envelope_id)
    # A tombstone validity failure must refuse, never suppress delivery as DUPLICATE.
    retype_tombstone(office, first.envelope_id, sender="Z99")
    assert err(office.deliver, raw) == postoffice.EXPIRED_TOMBSTONE_CONFLICT


def test_valid_bound_tombstone_keeps_expired_behavior_green(tmp_path):
    office = office_at(tmp_path)
    raw = sealed_bytes()
    first = office.deliver(raw)
    expire(office, first.envelope_id)
    assert office.bundle_state(first.envelope_id) == postoffice.EXPIRED_STATE
    assert session_for(office).scan(now=later(days=15)).items == ()
    assert err(session_for(office, open_budget=2).open_message, first.envelope_id,
               recipient_private_key=RECIPIENT) == postoffice.ALREADY_EXPIRED
    replay = office.deliver(raw)
    assert replay.status == postoffice.DUPLICATE and replay.received_at == T


# ================================================ TARGET B — one-pass convergence


def plant_crash_pair(monkeypatch, office, envelope_id):
    """Publish the tombstone then crash before any body deletion (inbox+read)."""
    result = deliver(office)
    shutil.copytree(office.inbox_bundle(result.envelope_id),
                    office.read_bundle(result.envelope_id))
    real = shutil.rmtree

    def boom(path, *a, **k):
        if getattr(path, "name", "") == envelope_id.split(":", 1)[1]:
            raise OSError("simulated crash before body deletion")
        return real(path, *a, **k)

    monkeypatch.setattr(postoffice.shutil, "rmtree", boom)
    with pytest.raises(OSError):
        office.sweep_expired(now=later(days=15))
    monkeypatch.setattr(postoffice.shutil, "rmtree", real)
    return result


def test_one_recover_finishes_tombstone_plus_both(tmp_path, monkeypatch):
    office = office_at(tmp_path)
    result = deliver(office)
    shutil.copytree(office.inbox_bundle(result.envelope_id),
                    office.read_bundle(result.envelope_id))
    crash_after_tombstone(monkeypatch, office, result.envelope_id)
    assert office.expired_tombstone(result.envelope_id).is_file()
    assert office.inbox_bundle(result.envelope_id).is_dir()
    assert office.read_bundle(result.envelope_id).is_dir()

    office.recover()
    assert office.bundle_state(result.envelope_id) == postoffice.EXPIRED_STATE
    assert not office.inbox_bundle(result.envelope_id).exists()
    assert not office.read_bundle(result.envelope_id).exists()
    assert office.expired_tombstone(result.envelope_id).is_file()


def crash_after_tombstone(monkeypatch, office, envelope_id):
    """Publish the tombstone then crash before deleting the body.

    Drives `_expire_bundle` directly so the fixture models exactly the permitted
    crash window (tombstone committed, any live body left) without the sweep's
    own reconciliation step deciding the outcome first.
    """
    bundle = office.inbox_bundle(envelope_id)
    header, stored_at = office._verify_bundle(bundle, envelope_id)
    ttl = postoffice.effective_ttl_seconds(header, office.default_ttl)
    real = shutil.rmtree

    def boom(path, *a, **k):
        if getattr(path, "name", "") == envelope_id.split(":", 1)[1]:
            raise OSError("simulated crash before body deletion")
        return real(path, *a, **k)

    monkeypatch.setattr(postoffice.shutil, "rmtree", boom)
    with pytest.raises(OSError):
        office._expire_bundle(bundle, header, envelope_id, stored_at, ttl, later(days=15))
    monkeypatch.setattr(postoffice.shutil, "rmtree", real)


def test_conflicting_pair_destroys_no_last_good_body(tmp_path, monkeypatch):
    office = office_at(tmp_path)
    result = deliver(office)
    read = office.read_bundle(result.envelope_id)
    shutil.copytree(office.inbox_bundle(result.envelope_id), read)
    (read / "envelope.senv").write_bytes(
        (read / "envelope.senv").read_bytes()[:-2] + b"XY")
    crash_after_tombstone(monkeypatch, office, result.envelope_id)
    assert err(office.recover) == postoffice.READ_BUNDLE_CONFLICT
    assert office.inbox_bundle(result.envelope_id).is_dir()
    assert read.is_dir()


def test_both_without_tombstone_sweep_converges_not_partial(tmp_path):
    office = office_at(tmp_path)
    result = deliver(office)
    shutil.copytree(office.inbox_bundle(result.envelope_id),
                    office.read_bundle(result.envelope_id))
    sweep = office.sweep_expired(now=later(days=15))
    assert sweep.expired == 1
    # Never a successful sweep that leaves a live body behind.
    assert not office.inbox_bundle(result.envelope_id).exists()
    assert not office.read_bundle(result.envelope_id).exists()
    assert office.bundle_state(result.envelope_id) == postoffice.EXPIRED_STATE


def test_altered_effective_ttl_refuses_and_keeps_body(tmp_path, monkeypatch):
    office = office_at(tmp_path)
    result = deliver(office)
    crash_after_tombstone(monkeypatch, office, result.envelope_id)
    retype_tombstone(office, result.envelope_id, effective_ttl_seconds=1)
    assert err(office.recover) == postoffice.EXPIRY_STATE_CONFLICT
    assert office.inbox_bundle(result.envelope_id).is_dir()


def test_premature_expired_at_refuses_and_keeps_body(tmp_path, monkeypatch):
    office = office_at(tmp_path)
    result = deliver(office)
    crash_after_tombstone(monkeypatch, office, result.envelope_id)
    retype_tombstone(office, result.envelope_id, expired_at=T)
    assert err(office.recover) == postoffice.EXPIRY_STATE_CONFLICT
    assert office.inbox_bundle(result.envelope_id).is_dir()


def test_crash_after_one_of_two_copies_converges_on_next_recover(tmp_path, monkeypatch):
    office = office_at(tmp_path)
    result = deliver(office)
    shutil.copytree(office.inbox_bundle(result.envelope_id),
                    office.read_bundle(result.envelope_id))
    crash_after_tombstone(monkeypatch, office, result.envelope_id)
    # One copy was removed by the failed pass so far; the next recover finishes.
    if office.read_bundle(result.envelope_id).is_dir():
        shutil.rmtree(office.read_bundle(result.envelope_id))
    office.recover()
    assert office.bundle_state(result.envelope_id) == postoffice.EXPIRED_STATE
    assert not office.inbox_bundle(result.envelope_id).exists()


def test_ordinary_single_body_expiry_unchanged(tmp_path):
    office = office_at(tmp_path)
    result = deliver(office)
    sweep = office.sweep_expired(now=later(days=15))
    assert (sweep.expired, sweep.retained) == (1, 0)
    assert office.bundle_state(result.envelope_id) == postoffice.EXPIRED_STATE


# ================================================ regressions kept green


def test_header_only_scan_still_never_reads_senv(tmp_path, monkeypatch):
    import pathlib
    office = office_at(tmp_path)
    result = deliver(office)
    real = pathlib.Path.read_bytes

    def guarded(self):
        if self.suffix == ".senv":
            raise AssertionError(f"scan read payload bytes from {self.name}")
        return real(self)

    monkeypatch.setattr(pathlib.Path, "read_bytes", guarded)
    scan = session_for(office).scan(now=T)
    assert {item.view.envelope_id for item in scan.items} == {result.envelope_id}


def test_open_vs_sweep_still_converges(tmp_path):
    office = office_at(tmp_path)
    result = deliver(office)
    barrier = threading.Barrier(2)

    def do_open():
        barrier.wait()
        try:
            session_for(office, open_budget=1).open_message(
                result.envelope_id, recipient_private_key=RECIPIENT)
        except SailangError:
            pass

    def do_sweep():
        barrier.wait()
        office.sweep_expired(now=later(days=15))

    threads = [threading.Thread(target=do_open), threading.Thread(target=do_sweep)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert office.bundle_state(result.envelope_id) == postoffice.EXPIRED_STATE
    assert not office.inbox_bundle(result.envelope_id).exists()
    assert not office.read_bundle(result.envelope_id).exists()


def test_delivery_vs_sweep_still_cannot_resurrect(tmp_path):
    office = office_at(tmp_path)
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
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not office.inbox_bundle(first.envelope_id).exists()
    assert office.expired_tombstone(first.envelope_id).is_file()
    assert office.deliver(raw).status == postoffice.DUPLICATE
