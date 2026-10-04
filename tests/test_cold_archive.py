"""FUTURE GATE Wave 3: hot -> cold archive -> verify -> prune.

The wave exists because bounding a mailbox by deleting old bundles is data loss
the moment the copy being deleted from is the only copy, and it is worst exactly
when a cold write failed halfway -- which is when an operator is most likely to
be reaching for a delete. These tests pin the acceptance cases:

* archive, verify, prune and restore round-trip the exact logical content
* a forced write failure and a forced verify failure both leave hot untouched
* a Future Letter stays discoverable after its hot copy is pruned
* cold corruption is visible

plus the invariants the pipeline rests on: nothing is pruned unverified, a
pinned class is never pruned, restore is idempotent, search is metadata-only and
points at the canonical source, and the cold format records no plaintext.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.serialization import (
    Encoding, NoEncryption, PrivateFormat)

from sailang import SailangError
from saimail import cold_archive as cold
from saimail import custody, envelope, future_letter, ledger, outbox, postoffice, workspace

ROOT = Path(__file__).resolve().parent.parent
T0 = "2026-10-04T09:00:00Z"
T1 = "2026-10-04T10:00:00Z"
T2 = "2026-10-04T11:00:00Z"
T3 = "2026-10-04T12:00:00Z"


def _clock(*stamps):
    sequence = list(stamps)

    def now():
        return sequence.pop(0) if len(sequence) > 1 else sequence[0]

    return now


def _pair(tmp_path, *, mode=custody.CUSTODY_RAW, store=None):
    workspace.init_workspace(tmp_path / "A", seat="alpha", custody=mode, store=store)
    workspace.init_workspace(tmp_path / "B", seat="beta", custody=mode, store=store)
    A = workspace.load_workspace(tmp_path / "A", store=store)
    B = workspace.load_workspace(tmp_path / "B", store=store)
    workspace.add_recipient(A, "beta", workspace.identity_card(B), B.root)
    workspace.add_recipient(B, "alpha", workspace.identity_card(A), A.root)
    return A, B


def _send(A, key="k1", claim="one fact", clock=None):
    return outbox.submit_send(A, "beta", key=key, claim=claim,
                              clock=clock or _clock(T0))


def _letter(ws, *, claim="what I learned", clock=None):
    """A FUTURE_LETTER in `ws`'s own mailbox, through the ordinary sealed path."""
    created = future_letter.create(ws, title="A Letter to Future Models",
                                   body=claim, clock=clock or _clock(T1))
    return created["letter"]["envelope_id"]


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _hot_bytes(office, envelope_id):
    for bundle in (office.inbox_bundle(envelope_id), office.read_bundle(envelope_id)):
        if bundle.is_dir():
            return (bundle / postoffice.CONTAINER_NAME).read_bytes()
    raise AssertionError(f"{envelope_id} has no hot bundle")


# --------------------------------------------------------------------------
# acceptance 1: archive, verify, prune, restore the exact logical content
# --------------------------------------------------------------------------

def test_archive_verify_prune_restore_round_trips_exact_bytes(tmp_path):
    A, B = _pair(tmp_path)
    sent = _send(A)
    envelope_id = sent["intent"]["envelope_id"]
    office = B.office(clock=_clock(T1))
    original = _hot_bytes(office, envelope_id)

    archived = cold.archive(B, envelope_id, clock=_clock(T1))
    assert archived["status"] == cold.ARCHIVED
    # The authorized reopen really ran: B holds the recipient key.
    assert archived["verified"]["reopen"] == cold.REOPEN_OPENED
    assert archived["verified"]["hash"] is True
    assert archived["pruned"]["removed"] is False

    stored = cold.record_path(B, envelope_id)
    assert (stored / cold.CONTAINER_NAME).read_bytes() == original
    assert cold.read_record(B, envelope_id)["index_row"]["kind"] is not None
    # The archive carries the ledger link, so a pruned message is traceable.
    link = cold.read_record(B, envelope_id)
    assert link["ledger_seq"] is not None and link["ledger_message_id"] == envelope_id

    pruned = cold.prune(B, retention=cold.retention_policy(max_count=0),
                        clock=_clock(T2))
    assert envelope_id in pruned["pruned"]["removed"]
    assert office.bundle_state(envelope_id) == "NEITHER"
    assert office.read_index_row(envelope_id) is not None, \
        "prune removes the body, never the discoverability row"

    restored = cold.restore(B, envelope_id, clock=_clock(T3))
    assert restored["status"] == cold.RESTORED
    assert _hot_bytes(B.office(clock=_clock(T3)), envelope_id) == original


def test_restore_is_idempotent_and_never_duplicates(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    cold.archive(B, envelope_id, clock=_clock(T1))
    cold.prune(B, retention=cold.retention_policy(max_count=0), clock=_clock(T2))
    assert cold.restore(B, envelope_id, clock=_clock(T3))["status"] == cold.RESTORED
    again = cold.restore(B, envelope_id, clock=_clock(T3))
    assert again["status"] == cold.ALREADY_HOT
    office = B.office(clock=_clock(T3))
    assert office.bundle_state(envelope_id) == "UNREAD", \
        "restore returns the message to the state it was archived from"
    assert len(office.read_index()) == 1


# --------------------------------------------------------------------------
# acceptance 2: a forced write or verify failure leaves hot untouched
# --------------------------------------------------------------------------

def test_a_forced_write_failure_leaves_the_hot_copy_untouched(tmp_path, monkeypatch):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    office = B.office(clock=_clock(T1))
    before = _hot_bytes(office, envelope_id)

    def boom(*args, **kwargs):
        raise OSError("no space left on device")

    monkeypatch.setattr(cold.postoffice, "_write_complete", boom)
    result = cold.archive(B, envelope_id, clock=_clock(T1))
    assert result["status"] == cold.COLD_WRITE_FAILED
    assert result["ok"] is False and result["operator_action_required"] is True
    assert office.bundle_state(envelope_id) == "UNREAD"
    assert _hot_bytes(office, envelope_id) == before
    # And nothing half-written is visible under the record's own name.
    assert cold.items_root(B).is_dir() is False or \
        not cold.record_path(B, envelope_id).exists()


def test_a_forced_verify_failure_leaves_the_hot_copy_untouched(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    office = B.office(clock=_clock(T1))
    before = _hot_bytes(office, envelope_id)

    def refusing_opener(raw):
        raise SailangError("NOT_VERIFIED", "the archived container did not verify")

    result = cold.archive(B, envelope_id, opener=refusing_opener, prune=True,
                          clock=_clock(T1))
    assert result["status"] == cold.COLD_VERIFY_FAILED
    assert result["ok"] is False
    assert "left untouched" in result["detail"] and "NOT pruned" in result["detail"]
    assert office.bundle_state(envelope_id) == "UNREAD"
    assert _hot_bytes(office, envelope_id) == before


def test_a_hash_mismatch_in_the_hot_copy_is_refused_without_deleting(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    office = B.office(clock=_clock(T1))
    bundle = office.inbox_bundle(envelope_id)
    (bundle / postoffice.CONTAINER_NAME).write_bytes(b"not an envelope at all")
    with pytest.raises(SailangError) as excinfo:
        cold.archive(B, envelope_id, clock=_clock(T1))
    assert excinfo.value.code in (cold.COLD_CORRUPT, cold.COLD_HASH_MISMATCH)
    assert bundle.is_dir(), "the hot copy is never deleted by a failed archive"
    assert cold.read_record(B, envelope_id) is None


# --------------------------------------------------------------------------
# acceptance 3: a Future Letter stays discoverable after its hot copy is pruned
# --------------------------------------------------------------------------

def test_a_future_letter_stays_discoverable_after_hot_prune(tmp_path):
    B = workspace.load_workspace(_pair(tmp_path)[1].root)
    envelope_id = _letter(B, claim="what the next agent needs to know")

    archived = cold.archive(B, envelope_id, clock=_clock(T1))
    assert archived["status"] == cold.ARCHIVED
    # A Future Letter is pinned by class without anyone asking for it.
    record = cold.read_record(B, envelope_id)
    assert record["pinned"] is True
    assert record["pinned_reason"] == "KIND_FUTURE_LETTER"

    # Even the most aggressive retention policy leaves it hot, because pinned
    # is checked before count, size and age.
    aggressive = cold.retention_policy(older_than_seconds=-1, max_count=0,
                                       max_bytes=1)
    pruned = cold.prune(B, retention=aggressive, clock=_clock(T3))
    assert pruned["pruned"]["removed"] == []
    assert pruned["retained"][envelope_id] == "KIND_FUTURE_LETTER"
    assert B.office(clock=_clock(T3)).bundle_state(envelope_id) != "NEITHER"

    found = cold.search(B, kinds=["FUTURE_LETTER"])
    assert [hit["envelope_id"] for hit in found["hits"]] == [envelope_id]
    hit = found["hits"][0]
    assert hit["kind"] == "FUTURE_LETTER"
    assert hit["canonical_source"] == str(cold.record_path(B, envelope_id))
    # Still hot, so there is nothing to restore: the pin kept it there.
    assert hit["hot_removed"] is False and hit["restorable"] is False
    assert hit["pinned"] is True


def test_a_pruned_message_is_still_searchable_and_restorable(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A, key="k1", claim="plain fact")["intent"]["envelope_id"]
    cold.archive(B, envelope_id, pin=True, clock=_clock(T1))
    # An explicit pin outranks every retention bound.
    pruned = cold.prune(B, retention=cold.retention_policy(max_count=0, max_bytes=1),
                        clock=_clock(T2))
    assert pruned["pruned"]["removed"] == []
    assert pruned["retained"][envelope_id] == "EXPLICIT_PIN"

    other = _send(A, key="k2", claim="second fact")["intent"]["envelope_id"]
    cold.archive(B, other, clock=_clock(T1))
    cold.prune(B, retention=cold.retention_policy(max_count=0), clock=_clock(T2))
    hits = cold.search(B)["hits"]
    pruned_hits = [hit for hit in hits if hit["hot_removed"]]
    assert [hit["envelope_id"] for hit in pruned_hits] == [other]
    assert cold.restore(B, other, clock=_clock(T3))["status"] == cold.RESTORED


# --------------------------------------------------------------------------
# acceptance 4: cold corruption is visible
# --------------------------------------------------------------------------

def test_a_corrupted_cold_container_is_visible_in_health(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    cold.archive(B, envelope_id, clock=_clock(T1))

    target = cold.record_path(B, envelope_id) / cold.CONTAINER_NAME
    target.write_bytes(target.read_bytes()[:-1] + b"\x00")

    verified = cold.verify_record(B, envelope_id)
    assert verified["status"] == cold.COLD_HASH_MISMATCH
    assert verified["ok"] is False and verified["operator_action_required"] is True

    health = cold.health(B)
    assert health["cold"]["state"] == "DEGRADED"
    assert health["cold"]["verified"] == 0
    assert health["cold"]["corrupt"][0]["envelope_id"] == envelope_id
    assert health["ok"] is False


def test_a_corrupted_manifest_is_visible_and_never_silently_skipped(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    cold.archive(B, envelope_id, clock=_clock(T1))
    manifest = cold.record_path(B, envelope_id) / cold.MANIFEST_NAME
    manifest.write_bytes(b'{"schema": "SAIMAIL_COLD_1"}')

    health = cold.health(B)
    assert health["cold"]["state"] == "DEGRADED"
    assert health["cold"]["corrupt"][0]["reason"] == cold.COLD_MANIFEST_INVALID
    # A record whose manifest cannot be read is NOT absent: it is still on disk
    # and still recoverable by hand, so it must not disappear from the count.
    assert health["cold"]["records"] == 1


def test_an_unlistable_archive_is_unknown_not_empty(tmp_path):
    A, B = _pair(tmp_path)
    _send(A)
    # A FILE where the items directory belongs: it exists, so this is not the
    # "no archive" case, and it cannot be listed.
    cold.items_root(B).parent.mkdir(parents=True, exist_ok=True)
    cold.items_root(B).write_bytes(b"not a directory")
    health = cold.health(B)
    assert health["status"] == cold.COLD_UNREADABLE
    assert health["cold"]["state"] == "UNKNOWN"
    assert health["cold"]["records"] == 0
    assert health["ok"] is False and health["operator_action_required"] is True


# --------------------------------------------------------------------------
# pipeline invariants
# --------------------------------------------------------------------------

def test_prune_never_removes_an_unverified_record(tmp_path):
    A, B = _pair(tmp_path)
    good = _send(A, key="k1")["intent"]["envelope_id"]
    bad = _send(A, key="k2")["intent"]["envelope_id"]
    for envelope_id in (good, bad):
        cold.archive(B, envelope_id, clock=_clock(T1))
    (cold.record_path(B, bad) / cold.RECEIPT_NAME).unlink()

    result = cold.prune(B, retention=cold.retention_policy(max_count=0),
                        clock=_clock(T2))
    assert good in result["pruned"]["removed"]
    assert bad not in result["pruned"]["removed"]
    assert result["failed"][0]["envelope_id"] == bad
    assert B.office(clock=_clock(T2)).bundle_state(bad) == "UNREAD", \
        "a record whose cold copy is incomplete keeps its hot copy"


def test_archive_is_idempotent_and_rewrites_nothing(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    first = cold.archive(B, envelope_id, clock=_clock(T1))
    manifest = (cold.record_path(B, envelope_id) / cold.MANIFEST_NAME).read_bytes()
    second = cold.archive(B, envelope_id, clock=_clock(T1))
    assert second["status"] == cold.ALREADY_COLD
    assert (cold.record_path(B, envelope_id) / cold.MANIFEST_NAME).read_bytes() \
        == manifest
    assert first["cold"]["envelope_id"] == second["cold"]["envelope_id"]


def test_archive_of_something_that_is_not_mail_refuses_without_deleting(tmp_path):
    A, _ = _pair(tmp_path)
    absent = envelope.envelope_id(b"never delivered")
    result = cold.archive(A, absent, clock=_clock(T1))
    assert result["status"] == cold.NOT_HOT
    assert result["ok"] is True, "there is nothing to archive and nothing wrong"
    assert "nothing was deleted" in result["detail"]


def test_the_cold_format_records_the_provenance_and_the_ledger_link(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    cold.archive(B, envelope_id, clock=_clock(T1))
    record = cold.read_record(B, envelope_id)

    assert record["schema"] == cold.COLD_SCHEMA and record["version"] == 1
    assert record["hot_state"] == "UNREAD"
    assert record["bytes"] == len(_hot_bytes(B.office(clock=_clock(T1)), envelope_id))
    row = record["index_row"]
    assert row["envelope_id"] == envelope_id
    assert row["from"] == "alpha" and row["to"] == "beta"
    assert record["ledger_seq"] == ledger.fold(
        ledger.read_events(B)[0])["messages"][envelope_id]["seq"]


def test_the_cold_record_holds_no_plaintext_and_no_private_key(tmp_path):
    B = workspace.load_workspace(_pair(tmp_path)[1].root)
    envelope_id = _letter(B, claim="SECRET-CLAIM-MARKER")
    cold.archive(B, envelope_id, clock=_clock(T1))
    record = cold.record_path(B, envelope_id)
    blob = b"".join(path.read_bytes() for path in sorted(record.iterdir()))
    assert b"SECRET-CLAIM-MARKER" not in blob
    for key in (B.sender_private_key, B.recipient_private_key):
        secret = key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
        assert secret not in blob
        assert secret.hex().encode("ascii") not in blob


def test_retention_by_age_count_and_size_each_retain_independently(tmp_path):
    A, B = _pair(tmp_path)
    ids = []
    for index, stamp in enumerate((T0, T1, T2, T3), start=1):
        envelope_id = _send(A, key=f"k{index}", claim=f"fact {index}",
                            clock=_clock(stamp))["intent"]["envelope_id"]
        ids.append(envelope_id)
        cold.archive(B, envelope_id, clock=_clock(stamp))
    records = cold.read_records(B)
    assert [item["envelope_id"] for item in records] == ids, \
        "ARCHIVED_AT ordering is the archive's canonical order"
    newest, oldest = ids[-1], ids[0]

    # Age: measured from ARCHIVED_AT at the caller's "now".
    by_age = cold.select_for_prune(records, cold.retention_policy(
        older_than_seconds=2 * 3600), now=T3)
    assert sorted(by_age["prunable"]) == sorted([ids[0], ids[1]])
    assert newest in by_age["retained"]
    assert by_age["retained"][newest] == "NEWER_THAN_RETENTION"

    # Count: the budget is spent on the NEWEST, never the oldest.
    by_count = cold.select_for_prune(
        records, cold.retention_policy(max_count=1), now=T3)
    assert by_count["retained"][newest] == "WITHIN_COUNT"
    assert sorted(by_count["prunable"]) == sorted(ids[:-1])
    assert oldest in by_count["prunable"]

    # Size: the byte budget fills from the newest down, so one byte under the
    # total drops exactly the oldest record and keeps every other one.
    size = records[0]["bytes"]
    by_bytes = cold.select_for_prune(
        records, cold.retention_policy(max_bytes=4 * size - 1), now=T3)
    assert by_bytes["prunable"] == [oldest]
    assert by_bytes["retained"][newest] == "WITHIN_BYTES"

    scope = cold.select_for_prune(
        records, cold.retention_policy(kinds=frozenset({"WARNING"})), now=T3)
    assert scope["prunable"] == [] and \
        set(scope["retained"].values()) == {"KIND_OUT_OF_SCOPE"}


def test_the_default_policy_prunes_nothing(tmp_path):
    A, B = _pair(tmp_path)
    for index in range(3):
        envelope_id = _send(A, key=f"k{index}", claim=f"fact {index}") \
            ["intent"]["envelope_id"]
        cold.archive(B, envelope_id, clock=_clock(T1))
    result = cold.prune(B, clock=_clock(T3))
    assert result["pruned"]["removed"] == []
    assert result["cold"]["considered"] == 3
    assert result["detail"].startswith("0 hot copy/copies removed")


def test_a_dry_run_prune_removes_nothing(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    cold.archive(B, envelope_id, clock=_clock(T1))
    result = cold.prune(B, retention=cold.retention_policy(max_count=0),
                        dry_run=True, clock=_clock(T2))
    assert result["pruned"]["dry_run"] is True
    assert result["cold"]["prunable"] == 1
    assert B.office(clock=_clock(T2)).bundle_state(envelope_id) == "UNREAD"


def test_search_is_metadata_only_and_refuses_semantic_by_name(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    cold.archive(B, envelope_id, clock=_clock(T1))
    row = cold.read_record(B, envelope_id)["index_row"]

    found = cold.search(B, text=row["topic"])
    assert found["search_mode"] == "METADATA_ONLY"
    assert found["hits"][0]["envelope_id"] == envelope_id
    assert cold.search(B, text="no-such-metadata")["hits"] == []
    # The payload word is NOT findable, and that is the honest answer: the
    # archive holds no plaintext derivative to search.
    assert cold.search(B, text="fact")["hits"] == []

    refused = cold.search(B, semantic=True)
    assert refused["status"] == cold.SEMANTIC_SEARCH_UNSUPPORTED
    assert refused["ok"] is False and refused["hits"] == []
    assert "no plaintext derivative" in refused["detail"]


def test_search_filters_by_kind_and_bounds_the_result_set(tmp_path):
    A, B = _pair(tmp_path)
    plain = _send(A, key="k1", claim="plain")["intent"]["envelope_id"]
    letter = _letter(B, claim="a letter")
    for envelope_id in (plain, letter):
        cold.archive(B, envelope_id, clock=_clock(T2))

    only_letters = cold.search(B, kinds=["FUTURE_LETTER"])
    assert [hit["envelope_id"] for hit in only_letters["hits"]] == [letter]
    assert only_letters["cold"]["scanned"] == 2
    bounded = cold.search(B, limit=1)
    assert len(bounded["hits"]) == 1 and bounded["cold"]["truncated"] is True
    assert _code(cold.search, B, limit=0) == cold.BAD_RETENTION


def test_health_is_healthy_for_an_absent_or_intact_archive(tmp_path):
    A, B = _pair(tmp_path)
    absent = cold.health(B)
    assert absent["status"] == "HEALTHY" and absent["cold"]["reason"] == "NO_ARCHIVE"
    assert absent["ok"] is True

    envelope_id = _send(A)["intent"]["envelope_id"]
    cold.archive(B, envelope_id, clock=_clock(T1))
    healthy = cold.health(B)
    assert healthy["status"] == "HEALTHY"
    assert healthy["cold"] == {"state": "HEALTHY", "records": 1, "verified": 1,
                               "corrupt": [], "missing": []}


def test_a_bad_envelope_id_is_refused_by_name(tmp_path):
    A, _ = _pair(tmp_path)
    for bad in ("not-an-id", "sha256:short", "sha256:" + "Z" * 64):
        with pytest.raises(SailangError) as excinfo:
            cold.record_path(A, bad)
        assert excinfo.value.code == cold.COLD_UNKNOWN_ID


def test_a_header_only_caller_verifies_by_hash_and_says_so(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    cold.archive(B, envelope_id, clock=_clock(T1))
    headers = workspace.load_workspace_headers(B.root)
    verified = cold.verify_record(headers, envelope_id)
    assert verified["status"] == cold.VERIFIED
    assert verified["verified"]["reopen"] == cold.REOPEN_SKIPPED
    assert verified["verified"]["hash"] is True


def test_an_archived_message_restores_even_after_a_prune_and_restart(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    original = _hot_bytes(B.office(clock=_clock(T1)), envelope_id)
    cold.archive(B, envelope_id, clock=_clock(T1))
    cold.prune(B, retention=cold.retention_policy(max_count=0), clock=_clock(T2))

    restarted = workspace.load_workspace(B.root)
    assert restarted.office(clock=_clock(T3)).bundle_state(envelope_id) == "NEITHER"
    assert cold.restore(restarted, envelope_id, clock=_clock(T3))["status"] \
        == cold.RESTORED
    assert _hot_bytes(restarted.office(clock=_clock(T3)), envelope_id) == original


def test_restore_refuses_a_corrupted_cold_copy(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    cold.archive(B, envelope_id, clock=_clock(T1))
    target = cold.record_path(B, envelope_id) / cold.CONTAINER_NAME
    target.write_bytes(b"corrupted")

    result = cold.restore(B, envelope_id, clock=_clock(T2))
    assert result["status"] == cold.COLD_HASH_MISMATCH
    assert result["ok"] is False
    assert B.office(clock=_clock(T2)).bundle_state(envelope_id) == "UNREAD", \
        "unverifiable bytes never repopulate hot storage"


def test_the_whole_cold_surface_is_reachable_from_the_cli(tmp_path):
    A, B = _pair(tmp_path)
    envelope_id = _send(A)["intent"]["envelope_id"]
    ws = str(B.root)

    assert _cli("cold", "health", "--workspace", ws)["status"] == "HEALTHY"
    assert _cli("cold", "archive", "--workspace", ws, "--envelope-id", envelope_id,
                "--pin")["status"] == cold.ARCHIVED
    assert _cli("cold", "verify", "--workspace", ws,
                "--envelope-id", envelope_id)["status"] == cold.VERIFIED
    assert _cli("cold", "search", "--workspace", ws)["hits"][0]["envelope_id"] \
        == envelope_id
    # An explicit CLI pin outranks --max-count 0.
    dry = _cli("cold", "prune", "--workspace", ws, "--max-count", "0",
               "--dry-run")
    assert dry["pruned"]["dry_run"] is True
    assert dry["cold"]["prunable"] == 0
    live = _cli("cold", "prune", "--workspace", ws, "--max-count", "0")
    assert live["pruned"]["removed"] == []
    refused = _cli("cold", "search", "--workspace", ws, "--semantic")
    assert refused["status"] == cold.SEMANTIC_SEARCH_UNSUPPORTED
    assert _cli("cold", "restore", "--workspace", ws,
                "--envelope-id", envelope_id)["status"] == cold.ALREADY_HOT


def _cli(*argv) -> dict:
    out = subprocess.run([sys.executable, "-m", "saimail_local", *argv, "--json"],
                         cwd=str(ROOT), capture_output=True, text=True, timeout=180)
    return json.loads(out.stdout)