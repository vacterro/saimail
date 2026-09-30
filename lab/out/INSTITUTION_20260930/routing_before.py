def desk(workspace, *, lineage, work, scope=None, budget=20, cursor=0, inbox_cursor=None,
         clock=None):
    """Keyless bounded discovery of unread mail, unfinished decisions and reserve.

    Two independent cursors cover the index and receiver database. No body is
    opened, no evidence file is read, no database is created by this query.
    """
    participants._check_lineage(lineage)
    if not isinstance(work, str) or not letters._WORK.fullmatch(work):
        _reject(letters.BAD_LETTER, "desk needs an exact Work id")
    if (isinstance(budget, bool) or not isinstance(budget, int) or not 1 <= budget <= MAX_PAGE
            or isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0):
        _reject(letters.BAD_LETTER, "desk page budget is 1..100 and cursor is a nonnegative integer")
    watched = [] if scope is None else scope
    if not isinstance(watched, list) or len(watched) > letters.MAX_EVIDENCE:
        _reject(letters.BAD_LETTER, "desk scope is a bounded list of exact files")
    for path in watched:
        letters.check_path(path)
    now = _now(clock)
    page = ws.query_inbox(workspace, topic=work, state=postoffice.UNREAD,
                          scan_budget=budget, cursor=inbox_cursor, clock=clock)
    cases = []
    examined = 0
    continuation = None
    with _db(workspace) as db:
        if db is not None:
            # Fetch one sentinel to distinguish completion from a full page.
            rows = db.execute("SELECT * FROM cases WHERE lineage=? AND id>? ORDER BY id LIMIT ?",
                              (lineage, cursor, budget + 1)).fetchall()
            examined = min(len(rows), budget)
            for row in rows[:budget]:
                view = _case_view(row, now)
                in_work = view["recipient_work"] == work
                in_reserve = view["retained"] and bool(set(watched) & set(view["scope"]))
                if not view["expired"] and ((in_work and view["actionable"]) or in_reserve):
                    view["match"] = "SUCCESSOR_RESERVE" if in_reserve else "CURRENT_WORK"
                    cases.append(view)
            if len(rows) > budget:
                continuation = rows[budget - 1]["id"]
    return ws.command_result("letter-desk", "OK", workspace=workspace, items=page["items"],
                             cases=cases, rows_examined=page["rows_examined"],
                             cases_examined=examined, cursor=continuation,
                             inbox_cursor=page["cursor"],
                             complete=continuation is None and page["cursor"] is None,
                             detail="metadata only; reserve evidence must be rechecked by explicit review")

def notify(workspace, *, lineage: str, work: str, trigger: str, to_seat: str, claim=None,
           citation=None, event=None, letter=None, clock=None) -> dict:
    """Send one automatic notification exactly once, or suppress it by budget.

    Exactly one body: ``claim`` (one line) or ``citation`` (the S2 record of
    ``event``). The recipient, kind and alias come from the participant registry;
    the key makes every repeat of the same fact the same message.
    """
    if sum(body is not None for body in (claim, citation, letter)) != 1:
        _reject(_workspace.BAD_INPUT, "a notification carries exactly one body")
    resolved = participants.resolve_participant(workspace, lineage, to_seat,
                                                trigger=trigger)["participant"]
    if letter is not None:
        from sailang import Record
        from saimail import letters

        letters.validate(letter, lineage=lineage, recipient_work=work)
        if letter["trigger"] != trigger:
            _reject(letters.BAD_LETTER, "letter trigger differs from its routing trigger")
        # Stable issue identity prevents a reworded decision from becoming a
        # second letter. A changed request must be an explicit new decision.
        basis = "l" + hashlib.sha256(
            (letter["sender_work"] + ":" + letter["issue"]).encode("utf-8")).hexdigest()[:24]
        identity = {"form": "letter", "letter": letter}
        citation = Record.create(
            KIND="O", SRC="AGENT:" + workspace.seat, SUBJ=work,
            CLAIM=letters.encode(letter), TYPE="OBS", STATUS="U1",
            EV=("sha256:" + letter["evidence"][0]["sha256"] if letter["evidence"] else "0"),
            CREATED=(clock or postoffice.utc_now)())
    elif citation is not None:
        if not isinstance(event, str) or not _EVENT_RE.match(event):
            _reject(_workspace.BAD_INPUT, "a citation names its event id E-<number>")
        basis = event
        identity = {"form": "citation", "event": event, "ev": citation.get("EV")}
    else:
        if not isinstance(claim, str) or not claim.strip() or "\n" in claim or "\r" in claim:
            _reject(_workspace.BAD_INPUT, "a notification claim is one non-empty line")
        basis = "c" + hashlib.sha256(claim.strip().encode("utf-8")).hexdigest()[:24]
        identity = None
    key = notify_key(lineage, work, trigger, to_seat, basis)
    now = (clock or postoffice.utc_now)()
    kwargs = {"key": key, "subject": work, "topic": work, "kind": resolved["kind"],
              "content_identity": identity, "gate": _budget_gate(to_seat, work, now),
              "clock": clock}
    try:
        if citation is not None:
            with tempfile.TemporaryDirectory(prefix="saimail-notify-") as scratch:
                path = Path(scratch) / "citation.sail"
                path.write_bytes(citation.canonical_bytes())
                sent = outbox.submit_send(workspace, resolved["alias"], record_path=path,
                                          **kwargs)
        else:
            sent = outbox.submit_send(workspace, resolved["alias"], claim=claim.strip(),
                                      **kwargs)
    except SailangError as exc:
        if exc.code != NOTIFY_BUDGET_EXCEEDED:
            raise
        return _workspace.command_result(
            "saipen-notify", NOTIFY_SUPPRESSED, workspace=workspace,
            notify=_view(trigger, to_seat, resolved, work, key),
            detail=f"suppressed by the receiver attention budget: {exc.detail}; nothing written")
    resumed = outbox.resume_outbox(workspace, budget=RESUME_BUDGET, clock=clock)["counts"]
    result = dict(sent)
    result.update(command="saipen-notify", notify=_view(trigger, to_seat, resolved, work, key),
                  resumed=resumed)
    result["notify"]["content_contract"] = "SAIMAIL_LETTER_1" if letter is not None else "UNASSESSED"
    return result
