# P1 — LOCAL INBOX QUERY v0 (metadata-only triage)

Status: working. Contract for `saimail.inbox_query.query_metadata`,
`saimail.workspace.query_inbox` and the filtered `saimail-local inbox`
subcommand; focused tests in `tests/test_local_inbox_query.py` and
`tests/test_local_inbox_query_acceptance.py`.

## 1. Why this document exists

V2-01 lists messages and opens them, but an operator had no bounded way to find
a prior message without reading the whole listing. P1 adds the smallest useful
step: a deterministic, bounded, **metadata-only** query over the index the Post
Office already keeps. It adds no protocol rule, no second index, no database
engine, no model, no network path and no new cryptography.

## 2. Search is not open

Querying an index row never:

* reads `.senv` payload bytes;
* parses or decrypts an encrypted payload;
* calls `envelope.parse_header`, `envelope.verify` or `envelope.open`;
* calls `PostOfficeSession.open_message` or `workspace.open_message`;
* moves inbox/read bundles, acknowledges attention or promotes memory;
* mutates any lifecycle state.

Finding a message is metadata work. Reading a message remains the explicit,
authenticated `open --envelope ENVELOPE_ID` action. A query result carries only
the metadata already allowed by `inbox` listing, so it is sufficient to choose
the next explicit `open`.

## 3. Operations

* `saimail.inbox_query.query_metadata(office, query, *, cursor=None,
  scan_budget=None)` — one bounded page of the canonical index. It is its own
  module rather than a method on `PostOffice` because the frozen V2-02 / FG-04B
  experiment registrations hash-pin the exact bytes of `saimail/postoffice.py`;
  P1 must not rewrite that module. It reuses the bounded streaming primitives
  of `PostOfficeSession.scan` (`_checked_cursor_offset`, `_stream_index_rows`)
  and `PostOffice.bundle_state`, but **not** scan's unread-only behaviour, its
  `HeaderInterest` decision, attention merging or model recommendations. It is
  a separate operation with separate semantics and duplicates no cursor
  implementation.
* `saimail.workspace.query_inbox(workspace, *, sender, topic, kind, state, ref,
  since, before, scan_budget, cursor, clock)` — the `LOCAL_WORKSPACE_COMMAND_1`
  projection with `command = "inbox-query"`.
* `saimail-local inbox --workspace DIR [filters]` — the CLI surface. With **no**
  filter/budget/cursor argument it keeps the exact legacy unbounded listing
  (`command = "inbox"`); any query argument switches to the bounded query. This
  is deliberate backward compatibility (section 8).

## 4. Filters

All filters are exact and combine with **AND only**; there is no implicit OR and
no query language.

| Filter | Field | Semantics |
|--------|-------|-----------|
| `sender` / `--from-seat` | `from` | exact seat equality |
| `topic` / `--topic` | `topic` | exact topic-token equality |
| `kind` / `--kind` | `kind` | exact closed SENV2 kind equality |
| `state` / `--state` | derived durable state | closed set `UNREAD` / `READ` / `EXPIRED` |
| `ref` / `--ref` | `ref` | exact canonical `sha256:<64 hex>` equality |
| `since` / `--since` | `received_at` | inclusive lower bound (`received_at >= since`) |
| `before` / `--before` | `received_at` | exclusive upper bound (`received_at < before`) |

The triage clock is the receiver-local `received_at`; sender `created` time is
returned as metadata but is never used as a filter and is never conflated with
receipt time. Bounds are canonical UTC instants (`YYYY-MM-DDTHH:MM:SSZ`), so
lexicographic comparison is chronological.

Deliberately **not** supported, now or in this version: payload/substring
search, claim or subject search, regex, fuzzy matching, stemming, ranking,
embeddings, semantic similarity and model-assisted triage. Those belong to a
future evidence-backed gate, if one is ever justified.

## 5. Result contract

`LOCAL_WORKSPACE_COMMAND_1` (unchanged schema, `version = 1`) with
`command = "inbox-query"` and the following fields:

| Field | Meaning |
|-------|---------|
| `command` | `"inbox-query"` |
| `status` | `"OK"`, or a named refusal code |
| `query` | the exact filters applied plus the effective `scan_budget` |
| `items` | matched metadata items (bounded by `rows_examined`) |
| `rows_examined` | exact number of index rows parsed by this call |
| `match_count` | number of items on this page (`== len(items)`) |
| `exhausted` | `true` when more index data remains after this page |
| `cursor` | continuation byte offset when `exhausted`, else `null` |

Each item carries exactly the fields `inbox` already lists: `envelope_id`,
`from`, `to`, `kind`, `topic`, `created`, `received_at`, `state`, `ref`. No
payload, no claim, no decrypted subject and no private identity material is ever
included.

## 6. State semantics

Normal durable states are returned as metadata: `UNREAD`, `READ`, `EXPIRED`.
Abnormal lifecycle states preserve the existing fail-closed behaviour instead of
being silently omitted to make results look cleaner:

* `NEITHER` for an indexed row → `INDEX_BODY_MISSING`;
* `BOTH` (crash copy in both `inbox/` and `read/`) → `RECONCILIATION_REQUIRED`;
* a valid tombstone beside a live body → `EXPIRY_RECONCILIATION_REQUIRED`;
* a structurally invalid tombstone → `EXPIRED_TOMBSTONE_CONFLICT`.

P1 is triage, not recovery: it never resolves these states.

## 7. Bounds and cursor

* `scan_budget` defaults to `saimail.inbox_query.DEFAULT_SCAN_BUDGET = 100` and
  is refused above the hard maximum `MAX_SCAN_BUDGET = 10000` with `BAD_BUDGET`; a
  negative or non-integer budget is `BAD_BUDGET`. A zero budget is valid and
  examines no row (a continuation cursor at offset `0` is returned when the
  index is non-empty).
* The cost of one call is bounded by rows parsed, never by total mailbox size.
  Rows beyond the budget are never parsed and cannot fail that call.
* A continuation `cursor` is the byte offset of the next row; it is mechanically
  validated (`_checked_cursor_offset`): negative, non-boundary (inside a row),
  past-EOF, and nonzero-on-missing-index cursors are all refused with the
  existing `BAD_CURSOR` contract. Continuation resumes exactly after the last
  examined row and never re-reads the prefix.
* A malformed row actually reached fails closed with `INDEX_CORRUPT`; a
  malformed row beyond the current budget is not parsed by that call and fails
  when a later continuation reaches it. This preserves the D-037 bounded-work
  philosophy.

## 8. Ordering and backward compatibility

Results preserve canonical index order (append order); no reordering, sorting or
random filesystem order is introduced. The legacy unfiltered `saimail-local
inbox` command keeps its existing behaviour exactly — it is a full, fail-open
listing sorted by `(received_at, envelope_id)`. A no-filter query is equivalent
to that listing in metadata content (same items, same fields); only the query
ordering and the `query`-aware summary differ. The equivalence is proven by test.

## 9. Attention and selector isolation

`HeaderInterest`, `merge_attention`, model recommendations and selector ignore
rules are never consulted. A message that a previous selector experiment would
have ignored is still findable through metadata if its canonical index row
matches the explicit query. P1 is operator-directed retrieval, not the V2-02
selector, and it reintroduces no static topic-ignore authority.

## 10. Privacy and evidence

* No payload bytes, decrypted claim, subject or private key material appear in
  any query result or CLI stdout; tests assert their absence.
* Red-control tests poison `PostOffice._read_bundle_container`,
  `PostOffice._verify_bundle`, `envelope.parse_header`, `envelope.verify`,
  `envelope.open`, `PostOfficeSession.open_message` and `workspace.open_message`
  and prove matching and non-matching metadata queries still succeed while those
  paths are unavailable.
* A query leaves the `mail/` tree byte-identical: READ/UNREAD filesystem state
  is snapshotted before and after and compared.
* Fully offline: zero network, model, provider or hardware calls.

## 11. What this does NOT claim

P1 is deterministic local metadata triage, not email-client search. It does not
promise a search index, a database, full-text or semantic search, relevance
ranking, inbox rules, automatic opening or promotion, or any change to SENV2,
custody, delivery, read/open or attention semantics. It exposes only the
authority the canonical index already carries.
