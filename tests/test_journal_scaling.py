"""Count canonical parser work; keep corruption visible after warm reads."""

import copy
import os
import subprocess
import sys

import pytest

from sailang import SailangError
from saimail import ledger, postoffice, surface, workspace
from test_postoffice_delivery import T, office_at, sealed_bytes

NOW = "2026-10-29T01:00:00Z"


def append(root, index):
    return ledger.append(root, ledger.CREATED, message_id=f"message-{index}",
                         actor="sender", at=NOW)


@pytest.mark.parametrize("count", [100, 200])
def test_sequential_appends_do_not_reparse_all_history(tmp_path, monkeypatch, count):
    original = ledger._parse_line
    calls = []

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(ledger, "_parse_line", counted)
    for index in range(count):
        assert append(tmp_path, index) is not None
    assert len(calls) <= count, f"{count} appends parsed {len(calls)} old rows"
    events, state = ledger.read_events(tmp_path)
    assert state == ledger.STATE_OK
    assert [event["seq"] for event in events] == list(range(1, count + 1))


def test_warm_feed_parses_only_its_window_and_does_not_return_mutable_cache_rows(tmp_path, monkeypatch):
    workspace.init_workspace(tmp_path / "ws", seat="sender")
    ws = workspace.load_workspace_headers(tmp_path / "ws")
    for index in range(200):
        append(ws.root, index)
    ledger.read_events(ws)  # one permitted validation/rebuild
    original = ledger._parse_line
    calls = []

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(ledger, "_parse_line", counted)
    cursor = 0
    for expected in range(1, 11):
        page = ledger.feed(ws, cursor=cursor, limit=1)
        assert page["events"][0]["seq"] == expected
        cursor = page["cursor"]
        page["events"][0]["detail"] = {"caller": "mutation"}
    assert len(calls) <= 10, f"ten one-row pages parsed {len(calls)} rows"
    assert ledger.feed(ws, limit=1)["events"][0]["detail"] is None


@pytest.mark.parametrize("position", [0, 2, 4])
def test_warm_tail_never_allows_append_or_feed_over_a_tampered_prefix(tmp_path, position):
    workspace.init_workspace(tmp_path / "ws", seat="sender")
    ws = workspace.load_workspace_headers(tmp_path / "ws")
    for index in range(5):
        append(ws.root, index)
    ledger.read_events(ws)
    path = ledger.ledger_path(ws)
    stamp = path.stat()
    rows = path.read_bytes().splitlines(keepends=True)
    assert b'"actor":"sender"' in rows[position]
    rows[position] = rows[position].replace(b'"actor":"sender"', b'"actor":"forged"')
    path.write_bytes(b"".join(rows))
    # A restored mtime alone must not fool a validated tail.
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    before = path.read_bytes()
    assert append(ws.root, 6) is None
    assert path.read_bytes() == before
    assert ledger.feed(ws, limit=1)["status"] == ledger.UNKNOWN


@pytest.mark.parametrize("count", [100, 200])
def test_index_insert_and_point_lookup_use_a_validated_map(tmp_path, monkeypatch, count):
    office, _ = office_at(tmp_path)
    header = postoffice.envelope.parse_header(sealed_bytes())
    original = postoffice._parse_index_line
    calls = []

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(postoffice, "_parse_index_line", counted)
    identifiers = [f"sha256:{index:064x}" for index in range(count)]
    for identifier in identifiers:
        assert office.ensure_index_row(header, identifier, T)
    assert len(calls) <= count, f"{count} inserts parsed {len(calls)} historical rows"
    calls.clear()
    for identifier in identifiers:
        row = office.read_index_row(identifier)
        assert row["envelope_id"] == identifier
        row["topic"] = "caller mutation"
    assert len(calls) <= count
    assert office.read_index_row(identifiers[0])["topic"] != "caller mutation"


def test_warm_index_rejects_external_corruption_and_duplicate_rows(tmp_path):
    office, _ = office_at(tmp_path)
    raw = sealed_bytes()
    header = postoffice.envelope.parse_header(raw)
    identifier = postoffice.envelope.envelope_id(raw)
    office.ensure_index_row(header, identifier, T)
    path = office.mail_root / postoffice.INDEX_NAME
    original = path.read_bytes()
    assert office.has_index_row(identifier)
    path.write_bytes(original + original)
    with pytest.raises(SailangError) as exc:
        office.read_index_row(identifier)
    assert exc.value.code == postoffice.INDEX_DUPLICATE_ENVELOPE_ID
    path.write_bytes(original.replace(b'"topic":', b'"broken":'))
    with pytest.raises(SailangError) as exc:
        office.ensure_index_row(header, identifier, T)
    assert exc.value.code == postoffice.INDEX_CORRUPT


def test_health_folds_once_and_receipt_section_reads_once(tmp_path, monkeypatch):
    workspace.init_workspace(tmp_path / "ws", seat="sender")
    ws = workspace.load_workspace_headers(tmp_path / "ws")
    append(ws.root, 0)
    original_fold = ledger.fold
    original_read = ledger.read_events
    folds, reads = [], []

    def counted_fold(events):
        folds.append(1)
        return original_fold(events)

    def counted_read(target):
        reads.append(1)
        return original_read(target)

    monkeypatch.setattr(ledger, "fold", counted_fold)
    monkeypatch.setattr(ledger, "read_events", counted_read)
    assert ledger.health(ws)["ledger"]["messages"] == 1
    assert len(folds) == 1
    reads.clear()
    assert surface._receipts_section(ws)["counts"]["pending_receipts"] == 0
    assert len(reads) == 1


def test_an_external_process_append_invalidates_the_warm_tail(tmp_path):
    assert append(tmp_path, 0)["seq"] == 1
    script = ("import sys; from pathlib import Path; from saimail import ledger; "
              "r=ledger.append(Path(sys.argv[1]), ledger.CREATED, message_id='external', "
              "actor='other', at='2026-10-29T01:00:00Z'); assert r['seq']==2")
    child = subprocess.run([sys.executable, "-c", script, str(tmp_path)],
                           capture_output=True, text=True, timeout=20)
    assert child.returncode == 0, child.stderr
    assert append(tmp_path, 2)["seq"] == 3
    assert [row["message_id"] for row in ledger.read_events(tmp_path)[0]] == [
        "message-0", "external", "message-2"]


def test_an_external_index_writer_is_observed_before_the_next_append(tmp_path):
    office, _ = office_at(tmp_path)
    header = postoffice.envelope.parse_header(sealed_bytes())
    first = "sha256:" + "1" * 64
    second = "sha256:" + "2" * 64
    office.ensure_index_row(header, first, T)
    path = office.mail_root / postoffice.INDEX_NAME
    row = office.read_index_row(first)
    row["envelope_id"] = second
    with path.open("ab") as handle:
        handle.write(postoffice._canonical_json_line(row))
        handle.flush()
        os.fsync(handle.fileno())
    assert office.read_index_row(second) == row
    assert not office.ensure_index_row(header, second, T)
    assert len(office.read_index()) == 2


def test_failed_fsync_does_not_publish_a_fictitious_cached_tail(tmp_path, monkeypatch):
    assert append(tmp_path, 0)["seq"] == 1

    def unavailable(fd):
        raise OSError("fsync failed after writing")

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", unavailable)
        assert append(tmp_path, 1) is None
    # Bytes may have reached the file before fsync failed. Rebuild from those
    # bytes instead of trusting either the previous tail or an assumed append.
    actual = ledger.read_events(tmp_path)[0]
    following = append(tmp_path, 2)
    assert following["seq"] == actual[-1]["seq"] + 1
    assert following["prev"] == actual[-1]["hash"]


def test_missing_native_change_time_forces_canonical_revalidation(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("native Windows generation fallback")
    from saimail import _journal_cache

    monkeypatch.setattr(_journal_cache, "_change_time", lambda handle: None)
    append(tmp_path, 0)
    path = ledger.ledger_path(tmp_path)
    stamp = path.stat()
    path.write_bytes(path.read_bytes().replace(b'"actor":"sender"', b'"actor":"forged"'))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert append(tmp_path, 1) is None


@pytest.mark.parametrize("missing_api", [False, True])
def test_missing_or_failed_windows_metadata_api_never_hides_corruption(tmp_path, monkeypatch,
                                                                      missing_api):
    if os.name != "nt":
        pytest.skip("Windows metadata backend")
    from saimail import _journal_cache

    class UnavailableApi:
        class error(Exception):
            pass

        @staticmethod
        def CreateFile(*args):
            raise UnavailableApi.error("metadata access refused")

        @staticmethod
        def GetFileInformationByHandleEx(*args):
            raise UnavailableApi.error("metadata query refused")

        FileBasicInfo = 0

    monkeypatch.setattr(_journal_cache, "_windows_api",
                        lambda: None if missing_api else UnavailableApi)
    append(tmp_path, 0)
    path = ledger.ledger_path(tmp_path)
    stamp = path.stat()
    path.write_bytes(path.read_bytes().replace(b'"actor":"sender"', b'"actor":"forged"'))
    os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert append(tmp_path, 1) is None


def test_fold_does_not_mutate_the_callers_event_objects(tmp_path):
    for index in range(3):
        append(tmp_path, index)
    events = ledger.read_events(tmp_path)[0]
    before = copy.deepcopy(events)
    assert ledger.fold(events) == ledger.fold(events)
    assert events == before


@pytest.mark.parametrize("count", [10, 20])
def test_recovery_rebuilds_index_with_linear_validation_work(tmp_path, monkeypatch, count):
    office, _ = office_at(tmp_path)
    for index in range(count):
        assert office.deliver(sealed_bytes(payload=f"message {index}")).status == postoffice.ACCEPTED
    index_path = office.mail_root / postoffice.INDEX_NAME
    expected = index_path.read_bytes()
    index_path.unlink()
    original = postoffice._parse_index_line
    calls = []

    def counted(raw):
        calls.append(1)
        return original(raw)

    monkeypatch.setattr(postoffice, "_parse_index_line", counted)
    result = office.recover()
    assert result.bundles_scanned == count
    assert result.rows_appended == count
    # Bundle order is canonical, not necessarily delivery order.
    assert set(index_path.read_bytes().splitlines()) == set(expected.splitlines())
    assert len(calls) <= 2 * count
    calls.clear()
    assert office.recover().rows_appended == 0
    assert len(calls) <= count


def test_a_cold_batch_of_point_lookups_loads_the_index_once(tmp_path, monkeypatch):
    source, _ = office_at(tmp_path / "source")
    header = postoffice.envelope.parse_header(sealed_bytes())
    identifiers = [f"sha256:{index:064x}" for index in range(50)]
    for identifier in identifiers:
        source.ensure_index_row(header, identifier, T)
    target, _ = office_at(tmp_path / "target")
    (target.mail_root / postoffice.INDEX_NAME).write_bytes(
        (source.mail_root / postoffice.INDEX_NAME).read_bytes())
    original = postoffice._parse_index_line
    calls = []

    def counted(raw):
        calls.append(1)
        return original(raw)

    monkeypatch.setattr(postoffice, "_parse_index_line", counted)
    for identifier in identifiers:
        assert target.read_index_row(identifier)["envelope_id"] == identifier
    assert len(calls) == len(identifiers)
