"""P1 — bounded metadata-only inbox query (spec/22-LOCAL-INBOX-QUERY-v0.md).

A separate operation over the canonical Post Office index. It is deliberately
its own module rather than a method on `PostOffice`: the frozen V2-02 / FG-04B
experiment registrations hash-pin the exact bytes of `saimail/postoffice.py`,
so P1 must not rewrite that module. It reuses the proven bounded streaming
primitives (`_checked_cursor_offset`, `_stream_index_rows`) and the proven
fail-closed `PostOffice.bundle_state`; it duplicates no cursor implementation
and never reads `.senv` payload bytes, decrypts, opens, promotes or mutates any
lifecycle state.

Search is not open: finding a message is metadata work, and reading it stays the
explicit authenticated `open --envelope` action.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Optional, Tuple

from saimail import envelope
from saimail import postoffice as _po

#: The default is deliberately small; the hard maximum refuses an unbounded
#: scan instead of silently running one.
DEFAULT_SCAN_BUDGET = 100
MAX_SCAN_BUDGET = 10000
BAD_QUERY_FILTER = "BAD_QUERY_FILTER"

#: The closed durable-state set a query may filter on. `BOTH`, `NEITHER` and
#: `EXPIRY_RECONCILIATION_REQUIRED` are abnormal and fail closed instead of
#: becoming a filterable value.
QUERY_STATES = frozenset({_po.UNREAD, _po.READ_STATE, _po.EXPIRED_STATE})


@dataclass(frozen=True)
class MetadataQuery:
    """One exact, metadata-only inbox query. Every filter combines with AND.

    Filters are token equality (sender seat, topic token, closed SENV2 kind,
    durable state, canonical `ref`) and half-open receiver-receipt time
    (`since` inclusive, `before` exclusive) over `received_at`. `created` is
    sender time and is never conflated with receiver receipt time; it is
    returned as metadata but is not a filter here.
    """

    sender: Optional[str] = None
    topic: Optional[str] = None
    kind: Optional[str] = None
    state: Optional[str] = None
    ref: Optional[str] = None
    since: Optional[str] = None
    before: Optional[str] = None


@dataclass(frozen=True)
class MetadataItem:
    """One index row's canonical metadata plus its derived durable state.

    Deliberately the same bounded field set `inbox` already reports: no
    payload, no claim, no decrypted subject, no private identity material.
    """

    envelope_id: str
    sender: str
    recipient: str
    kind: str
    topic: str
    created: str
    received_at: str
    state: str
    ref: Optional[str]

    def as_dict(self) -> dict:
        return {
            "envelope_id": self.envelope_id, "from": self.sender,
            "to": self.recipient, "kind": self.kind, "topic": self.topic,
            "created": self.created, "received_at": self.received_at,
            "state": self.state, "ref": self.ref,
        }


@dataclass(frozen=True)
class MetadataQueryResult:
    """One bounded page of a metadata query.

    `rows_examined` is the exact number of index rows parsed by this call and
    bounds both matching work and output size. `exhausted` and `cursor` follow
    `postoffice.ScanResult`: `exhausted` is True when the window ended with
    index data still unread, and a continuation `cursor` is then present that
    resumes exactly after the last examined row without re-reading the prefix.
    """

    items: Tuple[MetadataItem, ...]
    rows_examined: int
    match_count: int
    exhausted: bool
    cursor: Optional[_po.ScanCursor]


def _validate_query(query: MetadataQuery) -> None:
    """Reject a filter value outside its closed, canonical domain."""
    if not isinstance(query, MetadataQuery):
        _po._reject(BAD_QUERY_FILTER, "a metadata query is a MetadataQuery")
    if query.sender is not None and (
            not isinstance(query.sender, str) or not _po._SEAT_RE.match(query.sender)):
        _po._reject(BAD_QUERY_FILTER, "sender filter is one seat token")
    if query.topic is not None and (
            not isinstance(query.topic, str) or not _po._TOPIC_RE.match(query.topic)):
        _po._reject(BAD_QUERY_FILTER, "topic filter is one topic token")
    if query.kind is not None and (
            not isinstance(query.kind, str) or query.kind not in envelope.KINDS):
        _po._reject(BAD_QUERY_FILTER,
                    f"kind filter {query.kind!r} is outside the closed SENV2 kind set")
    if query.state is not None and query.state not in QUERY_STATES:
        _po._reject(BAD_QUERY_FILTER,
                    f"state filter {query.state!r} is outside {sorted(QUERY_STATES)}")
    if query.ref is not None and (
            not isinstance(query.ref, str) or not _po._EID_RE.match(query.ref)):
        _po._reject(BAD_QUERY_FILTER, "ref filter is sha256:<64 lowercase hex>")
    for name in ("since", "before"):
        value = getattr(query, name)
        if value is not None:
            _po._parse_utc(value, code=BAD_QUERY_FILTER)


def _matches(query: MetadataQuery, row: Mapping, state: str) -> bool:
    """Exact AND semantics over canonical row metadata and derived state."""
    if query.sender is not None and row["from"] != query.sender:
        return False
    if query.topic is not None and row["topic"] != query.topic:
        return False
    if query.kind is not None and row["kind"] != query.kind:
        return False
    if query.state is not None and state != query.state:
        return False
    if query.ref is not None and row.get("ref") != query.ref:
        return False
    # Canonical UTC instants are fixed-width, so lexicographic comparison is
    # chronological; `since` is inclusive and `before` is exclusive.
    if query.since is not None and row["received_at"] < query.since:
        return False
    if query.before is not None and not row["received_at"] < query.before:
        return False
    return True


def query_metadata(office: _po.PostOffice, query: MetadataQuery, *,
                   cursor: Optional[_po.ScanCursor] = None,
                   scan_budget: Optional[int] = None) -> MetadataQueryResult:
    """Stream the canonical index under a declared budget; match metadata.

    A separate operation from `PostOfficeSession.scan`: it never uses scan's
    unread-only filter, `HeaderInterest`, attention merging or model
    recommendations. It reports every normal durable state and fails closed on
    the abnormal ones exactly as a header scan does. It reads no `.senv` bytes:
    state derives from directory existence plus a valid tombstone, and the work
    bound is the number of index rows parsed, never the mailbox size.
    """
    _validate_query(query)
    budget = DEFAULT_SCAN_BUDGET if scan_budget is None else scan_budget
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 0:
        _po._reject(_po.BAD_BUDGET, "scan_budget is a non-negative integer count")
    if budget > MAX_SCAN_BUDGET:
        _po._reject(_po.BAD_BUDGET,
                    f"scan_budget {budget} exceeds the hard maximum {MAX_SCAN_BUDGET}")
    if cursor is not None and not isinstance(cursor, _po.ScanCursor):
        _po._reject(_po.BAD_CURSOR, "a continuation is a ScanCursor from a previous query")
    index_path = office.mail_root / _po.INDEX_NAME
    start = _po._checked_cursor_offset(
        index_path, cursor.offset if cursor is not None else 0)
    rows, next_offset, exhausted = _po._stream_index_rows(
        index_path, start_offset=start, max_rows=budget)
    items = []
    for row in rows:
        state = office.bundle_state(row["envelope_id"], row=row)
        if state == _po.NEITHER:
            _po._reject(_po.INDEX_BODY_MISSING,
                        f"indexed envelope {row['envelope_id']} has neither an inbox nor "
                        "a read bundle; refusing to forget it silently")
        if state == _po.BOTH:
            _po._reject(_po.RECONCILIATION_REQUIRED,
                        f"envelope {row['envelope_id']} exists as both an inbox and a read "
                        "bundle; maintenance reconciliation must prove identity first")
        if state == _po.EXPIRY_RECONCILIATION_REQUIRED:
            _po._reject(_po.EXPIRY_RECONCILIATION_REQUIRED,
                        f"envelope {row['envelope_id']} has an expired tombstone and a live "
                        "bundle; maintenance reconciliation must prove identity first")
        if _matches(query, row, state):
            items.append(MetadataItem(
                envelope_id=row["envelope_id"], sender=row["from"],
                recipient=row["to"], kind=row["kind"], topic=row["topic"],
                created=row["created"], received_at=row["received_at"],
                state=state, ref=row.get("ref")))
    return MetadataQueryResult(
        items=tuple(items), rows_examined=len(rows), match_count=len(items),
        exhausted=exhausted,
        cursor=_po.ScanCursor(offset=next_offset) if exhausted else None)


__all__ = [
    "BAD_QUERY_FILTER",
    "DEFAULT_SCAN_BUDGET",
    "MAX_SCAN_BUDGET",
    "QUERY_STATES",
    "MetadataItem",
    "MetadataQuery",
    "MetadataQueryResult",
    "query_metadata",
]
