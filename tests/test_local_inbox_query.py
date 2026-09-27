"""P1 focused tests: bounded, metadata-only inbox triage query (spec/22).

Covers the query contract end to end: exact filters combined with AND, the
derived durable-state set, half-open receiver-receipt time bounds, the declared
scan budget and byte-offset continuation, fail-closed abnormal lifecycle states,
the proof that no payload path is ever reached, and the equivalence between the
legacy unbounded listing and a no-filter query.

No network, no model, no provider and no payload access anywhere here.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from sailang import Record, SailangError
from saimail import envelope, inbox_query, postoffice, workspace

REF1 = "sha256:" + "1" * 64
REF2 = "sha256:" + "2" * 64
PAYLOAD_MARKER = "p1 synthetic payload never read by a metadata query b4d1"
PAYLOAD = Record.create(
    KIND="F", SRC="HUMAN:fixture", SUBJ="p1-fixture", CLAIM=PAYLOAD_MARKER,
    TYPE="OBS", EV="0", STATUS="U1", CREATED="2026-09-01T09:00:00Z").canonical_bytes()


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _t(minutes: int) -> str:
    total = 10 * 60 + minutes
    return f"2026-09-01T{total // 60:02d}:{total % 60:02d}:00Z"


def _init(root: Path, seat: str) -> workspace.Workspace:
    workspace.init_workspace(root, seat=seat)
    return workspace.load_workspace(root)


def _link(sender: workspace.Workspace, receiver: workspace.Workspace, alias: str) -> None:
    workspace.add_recipient(receiver, alias, workspace.identity_card(sender), sender.root)


def _send(office: postoffice.PostOffice, sender: workspace.Workspace,
          recipient: workspace.Workspace, *, kind: str, topic: str, created: str,
          received_at: str, ref: str | None = None) -> str:
    """Deliver one message with exact metadata; returns its ENVELOPE_ID."""
    container = envelope.seal(
        PAYLOAD, sender_private_key=sender.sender_private_key, sender_seat=sender.seat,
        recipient_seat=recipient.seat,
        recipient_public_key=recipient.recipient_private_key.public_key(),
        kind=kind, topic=topic, created=created, ref=ref)
    result = office.deliver(container)
    assert result.status == postoffice.ACCEPTED, result
    return envelope.envelope_id(container)


def _fixture(tmp_path) -> dict:
    """A deterministic mailbox covering senders, kinds, topics, refs and times."""
    a = _init(tmp_path / "ws-a", "SAIMAIL-A")
    c = _init(tmp_path / "ws-c", "SAIMAIL-C")
    b = _init(tmp_path / "ws-b", "SAIMAIL-B")
    _link(a, b, "alice")
    _link(c, b, "carol")

    rows = [
        ("A", "alpha", "PERSONAL_MESSAGE", 0, REF1, "2026-09-01T10:00:00Z"),
        ("C", "beta", "WARNING", 1, None, None),
        ("A", "alpha", "QUESTION", 2, None, None),
        ("C", "gamma", "PERSONAL_MESSAGE", 3, REF2, "2020-01-01T00:00:00Z"),
        ("A", "beta", "WARNING", 4, None, None),
        ("C", "alpha", "PERSONAL_MESSAGE", 4, None, None),
        ("A", "gamma", "QUESTION", 5, None, None),
        ("C", "beta", "WARNING", 6, None, None),
        ("A", "alpha", "PERSONAL_MESSAGE", 7, None, None),
        ("C", "gamma", "DISCOVERY", 8, None, None),
    ]
    senders = {"A": a, "C": c}
    records = []
    for who, topic, kind, minute, ref, created in rows:
        # records[6] (the expiry candidate) is deliberately much older, so a
        # single sweep expires exactly it and leaves the other rows live.
        received_at = ("2026-08-01T10:05:00Z"
                       if (who, topic, kind, minute) == ("A", "gamma", "QUESTION", 5)
                       else _t(minute))
        office = b.office(clock=lambda stamp=received_at: stamp)
        eid = _send(office, senders[who], b, kind=kind, topic=topic,
                    created=created or received_at, received_at=received_at, ref=ref)
        records.append({"envelope_id": eid, "sender": senders[who].seat, "topic": topic,
                        "kind": kind, "received_at": received_at, "ref": ref,
                        "state": postoffice.UNREAD, "minute": minute})
    # m8 -> READ, m7 -> EXPIRED; the rest stay UNREAD.
    read_eid = records[7]["envelope_id"]
    session = postoffice.PostOfficeSession(b.office(), scan_budget=0, open_budget=1)
    session.open_message(read_eid, recipient_private_key=b.recipient_private_key)
    records[7]["state"] = postoffice.READ_STATE
    sweep = b.office().sweep_expired(now="2026-09-10T00:00:00Z")
    assert sweep.expired == 1, sweep
    records[6]["state"] = postoffice.EXPIRED_STATE
    return {"A": a, "B": b, "C": c, "records": records}


def _expected(records, *, sender=None, topic=None, kind=None, state=None, ref=None,
              since=None, before=None) -> set:
    out = set()
    for record in records:
        if sender is not None and record["sender"] != sender:
            continue
        if topic is not None and record["topic"] != topic:
            continue
        if kind is not None and record["kind"] != kind:
            continue
        if state is not None and record["state"] != state:
            continue
        if ref is not None and record["ref"] != ref:
            continue
        if since is not None and record["received_at"] < since:
            continue
        if before is not None and not record["received_at"] < before:
            continue
        out.add(record["envelope_id"])
    return out


def _results(result: dict) -> set:
    return {item["envelope_id"] for item in result["items"]}


def _query(b: workspace.Workspace, **kwargs) -> dict:
    return workspace.query_inbox(b, **kwargs)


# --------------------------------------------------------------- A. filters


def test_no_filter_query_reports_every_normal_state(tmp_path):
    fx = _fixture(tmp_path)
    result = _query(fx["B"])
    assert result["schema"] == workspace.COMMAND_SCHEMA
    assert result["command"] == "inbox-query"
    assert result["status"] == "OK"
    assert _results(result) == {r["envelope_id"] for r in fx["records"]}
    states = {item["envelope_id"]: item["state"] for item in result["items"]}
    assert states[fx["records"][6]["envelope_id"]] == postoffice.EXPIRED_STATE
    assert states[fx["records"][7]["envelope_id"]] == postoffice.READ_STATE
    assert result["match_count"] == len(fx["records"])
    assert result["rows_examined"] == len(fx["records"])


def test_each_filter_independently(tmp_path):
    fx = _fixture(tmp_path)
    records = fx["records"]
    cases = [
        {"sender": "SAIMAIL-A"},
        {"topic": "alpha"},
        {"kind": "WARNING"},
        {"state": postoffice.UNREAD},
        {"state": postoffice.READ_STATE},
        {"state": postoffice.EXPIRED_STATE},
        {"ref": REF1},
        {"ref": REF2},
        {"since": _t(3)},
        {"before": _t(4)},
    ]
    for kwargs in cases:
        result = _query(fx["B"], **kwargs)
        assert _results(result) == _expected(records, **kwargs), kwargs


def test_filter_combinations_are_and_not_or(tmp_path):
    fx = _fixture(tmp_path)
    records = fx["records"]
    cases = [
        {"sender": "SAIMAIL-A", "topic": "alpha"},
        {"topic": "beta", "state": postoffice.READ_STATE},
        {"sender": "SAIMAIL-A", "since": _t(2), "before": _t(6)},
        {"kind": "PERSONAL_MESSAGE", "state": postoffice.UNREAD,
         "since": _t(0), "before": _t(5)},
        {"topic": "alpha", "kind": "QUESTION", "state": postoffice.UNREAD},
    ]
    for kwargs in cases:
        result = _query(fx["B"], **kwargs)
        assert _results(result) == _expected(records, **kwargs), kwargs


def test_since_is_inclusive_and_before_is_exclusive(tmp_path):
    fx = _fixture(tmp_path)
    records = fx["records"]
    since = _t(2)
    before = _t(4)
    result = _query(fx["B"], since=since, before=before)
    expected = {r["envelope_id"] for r in records
                if since <= r["received_at"] < before}
    assert _results(result) == expected
    assert all(since <= r["received_at"] < before
               for r in records if r["envelope_id"] in _results(result))


def test_received_at_is_the_triage_clock_not_created(tmp_path):
    fx = _fixture(tmp_path)
    # records[3] has a 2020 CREATED time but a 2026 RECEIVED_AT; receipt time
    # must decide, never sender time.
    result = _query(fx["B"], since=_t(3), before=_t(4))
    assert _results(result) == {fx["records"][3]["envelope_id"]}


def test_same_timestamp_rows_are_both_returned(tmp_path):
    fx = _fixture(tmp_path)
    result = _query(fx["B"], since=_t(4), before=_t(5))
    assert _results(result) == {fx["records"][4]["envelope_id"],
                               fx["records"][5]["envelope_id"]}


def test_bad_filter_values_are_refused(tmp_path):
    fx = _fixture(tmp_path)
    assert _code(_query, fx["B"], sender="bad seat") == inbox_query.BAD_QUERY_FILTER
    assert _code(_query, fx["B"], topic="bad topic") == inbox_query.BAD_QUERY_FILTER
    assert _code(_query, fx["B"], kind="NOT_A_KIND") == inbox_query.BAD_QUERY_FILTER
    assert _code(_query, fx["B"], state="BOTH") == inbox_query.BAD_QUERY_FILTER
    assert _code(_query, fx["B"], state="NEITHER") == inbox_query.BAD_QUERY_FILTER
    assert _code(_query, fx["B"], ref="nope") == inbox_query.BAD_QUERY_FILTER
    assert _code(_query, fx["B"], since="not-a-time") == inbox_query.BAD_QUERY_FILTER


# ------------------------------------------------------- B. metadata shape


def test_items_are_canonical_metadata_only(tmp_path):
    fx = _fixture(tmp_path)
    result = _query(fx["B"])
    allowed = {"envelope_id", "from", "to", "kind", "topic", "created",
               "received_at", "state", "ref"}
    for item in result["items"]:
        assert set(item) == allowed
    assert PAYLOAD_MARKER not in json.dumps(result)


def test_query_result_is_bounded_and_usable_for_explicit_open(tmp_path):
    fx = _fixture(tmp_path)
    result = _query(fx["B"], state=postoffice.UNREAD)
    assert len(result["items"]) <= result["rows_examined"]
    selected = result["items"][0]["envelope_id"]
    opened = workspace.open_message(fx["B"], selected)
    assert opened["status"] == postoffice.READ_STATE


# ---------------------------------------------------- C. cursor / boundary


def test_first_page_and_continuation_resume_without_prefix_reread(tmp_path):
    fx = _fixture(tmp_path)
    records = fx["records"]
    first = _query(fx["B"], scan_budget=3)
    assert first["rows_examined"] == 3
    assert first["exhausted"] is True and first["cursor"] is not None
    first_ids = [item["envelope_id"] for item in first["items"]]
    assert first_ids == [r["envelope_id"] for r in records[:3]]
    second = _query(fx["B"], scan_budget=3, cursor=first["cursor"])
    second_ids = [item["envelope_id"] for item in second["items"]]
    assert second_ids == [r["envelope_id"] for r in records[3:6]]
    assert set(first_ids).isdisjoint(second_ids)
    third = _query(fx["B"], scan_budget=10, cursor=second["cursor"])
    assert [item["envelope_id"] for item in third["items"]] == [
        r["envelope_id"] for r in records[6:]]
    assert third["exhausted"] is False and third["cursor"] is None


def test_matches_spanning_pages_equal_one_unbounded_query(tmp_path):
    fx = _fixture(tmp_path)
    whole = _query(fx["B"], topic="alpha")
    paged: set = set()
    cursor = None
    while True:
        page = _query(fx["B"], topic="alpha", scan_budget=2,
                      **({"cursor": cursor} if cursor is not None else {}))
        paged.update(item["envelope_id"] for item in page["items"])
        cursor = page["cursor"]
        if cursor is None:
            break
    assert paged == _results(whole)


def test_cursor_nonsense_is_refused(tmp_path):
    fx = _fixture(tmp_path)
    index = fx["B"].root / "mail" / postoffice.INDEX_NAME
    size = index.stat().st_size
    for bad in (-1, 1, size + 1):
        assert _code(_query, fx["B"], cursor=bad) == postoffice.BAD_CURSOR
    missing = _init(tmp_path / "ws-empty", "SAIMAIL-E")
    assert _code(_query, missing, cursor=5) == postoffice.BAD_CURSOR


def test_zero_budget_and_empty_inbox_are_deterministic(tmp_path):
    fx = _fixture(tmp_path)
    zero = _query(fx["B"], scan_budget=0)
    assert zero["rows_examined"] == 0 and zero["items"] == []
    assert zero["exhausted"] is True and zero["cursor"] == 0
    empty_root = tmp_path / "ws-fresh"
    fresh = _init(empty_root, "SAIMAIL-F")
    empty = _query(fresh)
    assert empty["rows_examined"] == 0 and empty["items"] == []
    assert empty["exhausted"] is False and empty["cursor"] is None


def test_scan_budget_hard_maximum_is_enforced(tmp_path):
    fx = _fixture(tmp_path)
    assert _code(_query, fx["B"],
                 scan_budget=inbox_query.MAX_SCAN_BUDGET + 1) == postoffice.BAD_BUDGET
    assert _code(_query, fx["B"], scan_budget=-1) == postoffice.BAD_BUDGET
    assert _code(_query, fx["B"], scan_budget=True) == postoffice.BAD_BUDGET


def _append_raw(index: Path, line: bytes) -> None:
    with index.open("ab") as handle:
        handle.write(line)


def test_malformed_row_inside_budget_fails_closed(tmp_path):
    fx = _fixture(tmp_path)
    index = fx["B"].root / "mail" / postoffice.INDEX_NAME
    _append_raw(index, b"{not json\n")
    assert _code(_query, fx["B"]) == postoffice.INDEX_CORRUPT


def test_malformed_row_beyond_budget_is_not_parsed_then_fails_on_continuation(tmp_path):
    fx = _fixture(tmp_path)
    index = fx["B"].root / "mail" / postoffice.INDEX_NAME
    _append_raw(index, b"{not json\n")
    total = len(fx["records"])
    page = _query(fx["B"], scan_budget=total)
    assert page["rows_examined"] == total
    assert page["exhausted"] is True and page["cursor"] is not None
    assert _code(_query, fx["B"], cursor=page["cursor"]) == postoffice.INDEX_CORRUPT


# ------------------------------------------------ D. abnormal states fail


def test_abnormal_lifecycle_states_fail_closed(tmp_path):
    fx = _fixture(tmp_path)
    b = fx["B"]
    eid = fx["records"][0]["envelope_id"]
    digest = eid.split(":", 1)[1]
    read_parent = b.root / "mail" / postoffice.READ / b.seat
    read_parent.mkdir(parents=True, exist_ok=True)
    # BOTH: the same object in inbox/ and read/ is a crash window, never a hit.
    (read_parent / digest).mkdir()
    assert _code(_query, b) == postoffice.RECONCILIATION_REQUIRED


def test_index_row_without_body_fails_closed(tmp_path):
    fx = _fixture(tmp_path)
    b = fx["B"]
    eid = fx["records"][0]["envelope_id"]
    digest = eid.split(":", 1)[1]
    for state in (postoffice.INBOX, postoffice.READ):
        target = b.root / "mail" / state / b.seat / digest
        if target.is_dir():
            import shutil

            shutil.rmtree(target)
    assert _code(_query, b) == postoffice.INDEX_BODY_MISSING


# ------------------------------------------------- E. no payload access


def _filesystem_snapshot(root: Path) -> dict:
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            snapshot[str(path.relative_to(root))] = hashlib.sha256(
                path.read_bytes()).hexdigest()
    return snapshot


def _poison_payload_paths(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("a metadata query reached a payload/open path")

    monkeypatch.setattr(postoffice.PostOffice, "_read_bundle_container", boom)
    monkeypatch.setattr(postoffice.PostOffice, "_verify_bundle", boom)
    monkeypatch.setattr(envelope, "parse_header", boom)
    monkeypatch.setattr(envelope, "verify", boom)
    monkeypatch.setattr(envelope, "open", boom)
    monkeypatch.setattr(postoffice.PostOfficeSession, "open_message", boom)
    monkeypatch.setattr(workspace, "open_message", boom)


def test_query_never_reads_payload_and_never_mutates_state(tmp_path, monkeypatch):
    fx = _fixture(tmp_path)
    b = fx["B"]
    before = _filesystem_snapshot(b.root)
    _poison_payload_paths(monkeypatch)
    matching = _query(b, topic="alpha")
    non_matching = _query(b, sender="SAIMAIL-Z")
    assert _results(matching) == _expected(fx["records"], topic="alpha")
    assert _results(non_matching) == set()
    after = _filesystem_snapshot(b.root)
    assert before == after


# ---------------------------------------- F. attention policy untouched


def test_query_does_not_consult_attention_machinery(tmp_path, monkeypatch):
    fx = _fixture(tmp_path)
    b = fx["B"]

    def boom(*_args, **_kwargs):
        raise AssertionError("a metadata query consulted attention policy")

    monkeypatch.setattr(postoffice.HeaderInterest, "decide", boom)
    monkeypatch.setattr(postoffice, "merge_attention", boom)
    result = _query(b, topic="alpha")
    assert _results(result) == _expected(fx["records"], topic="alpha")


def test_a_selector_ignored_topic_is_still_findable(tmp_path):
    fx = _fixture(tmp_path)
    b = fx["B"]
    office = b.office()
    office.interest = postoffice.HeaderInterest(ignore_topics={"alpha"})
    indexed = {r["envelope_id"] for r in fx["records"] if r["topic"] == "alpha"}
    result = inbox_query.query_metadata(office, inbox_query.MetadataQuery(topic="alpha"))
    assert {item.envelope_id for item in result.items} == indexed


# ------------------------------------------------- G. equivalence


def test_no_filter_query_equals_legacy_inbox_listing(tmp_path):
    fx = _fixture(tmp_path)
    b = fx["B"]
    legacy = workspace.list_inbox(b)
    modern = workspace.query_inbox(b)
    legacy_items = {item["envelope_id"]: item for item in legacy["items"]}
    modern_items = {item["envelope_id"]: item for item in modern["items"]}
    assert legacy_items == modern_items
    assert legacy["detail"] != modern["detail"]  # legacy keeps its own summary


# ------------------------------------------------- H. boundedness


def _fabricate_index(office: postoffice.PostOffice, count: int, topic: str = "bulk") -> None:
    """Rows plus directory state only: enough for a metadata query, no payload."""
    index = office.mail_root / postoffice.INDEX_NAME
    with index.open("ab") as handle:
        for i in range(count):
            eid = f"sha256:{i:064x}"
            (office.mail_root / postoffice.INBOX / office.seat / f"{i:064x}").mkdir(
                parents=True, exist_ok=True)
            row = {
                "schema": 1, "envelope_id": eid, "received_at": _t(0),
                "from": "SAIMAIL-A", "from_kid": "sha256:" + "a" * 64,
                "to": office.seat, "to_kid": "sha256:" + "b" * 64,
                "kind": "PERSONAL_MESSAGE", "topic": topic, "created": _t(0),
            }
            handle.write(postoffice._canonical_json_line(row))


def test_large_index_work_is_bounded_by_the_declared_budget(tmp_path, monkeypatch):
    b = _init(tmp_path / "ws-big", "SAIMAIL-B")
    office = b.office()
    _fabricate_index(office, 250)
    parses = {"n": 0}
    original = postoffice._parse_index_line

    def counting(raw):
        parses["n"] += 1
        return original(raw)

    monkeypatch.setattr(postoffice, "_parse_index_line", counting)

    def boom(*_args, **_kwargs):
        raise AssertionError("a metadata query reached a payload path")

    monkeypatch.setattr(postoffice.PostOffice, "_read_bundle_container", boom)
    page = inbox_query.query_metadata(office, inbox_query.MetadataQuery(), scan_budget=40)
    assert page.rows_examined == 40
    assert page.match_count == 40
    assert parses["n"] == 40
    assert page.exhausted is True and page.cursor is not None
    rest = inbox_query.query_metadata(office, inbox_query.MetadataQuery(),
                                      cursor=page.cursor, scan_budget=250)
    assert rest.rows_examined == 210
    assert parses["n"] == 250
    assert rest.match_count <= rest.rows_examined
    assert rest.exhausted is False and rest.cursor is None
