"""Receiver-owned operator-interruption admission for agent-originated mail (spec/35).

    MESSAGE_DURABLY_EXISTS            != OPERATOR_INTERRUPTION_PRESENTED
    CANDIDATE_EXISTS                  != OPERATOR_INTERRUPTION_PRESENTED
    SENDER_REQUESTS_AN_INTERRUPTION   != RECEIVER_ADMITS_ONE
    ZERO_PRESENTED_INTERRUPTIONS      IS A SUCCESSFUL_OUTCOME

The defect class this module eliminates: an agent that cannot finish a Work
turning its own running commentary into operator mail. A live session produced
five letters from one Work in 41 minutes -- a tentative repair, a correction, a
correction of the correction, a retraction and a final hard stop. The etiquette
that forbids this already existed in prose in ``README.md`` and ``send --help``
and was still bypassed, because prose is not a product boundary.

What changed here is where the decision lives. Everything below is settled by
the RECEIVER, in the receiver's own workspace:

* **Eligibility is a closed set.** Only ``OPERATOR_ACTION_REQUIRED``,
  ``DATA_OR_MONEY_RISK`` and ``CROSS_PROJECT_CRITICAL_DISCOVERY`` may reach the
  operator. Everything else -- progress, a finished ticket, test results, an
  audit summary, an intermediate finding, a correction, a retraction, an FYI --
  is ineligible by construction, not by tone. The class is a validated field,
  never a keyword match against prose.
* **Stability is declared, not read.** A candidate must be marked settled. An
  unsettled diagnosis is durable transport and nothing else. The sender settles
  the diagnosis first; this layer never guesses that it has.
* **Identity binds the decision, not the spelling.** ``DECISION`` is a
  domain-separated digest over receiver, Work and the sender's stable
  ``decision_id``. A reworded letter for the same decision is the same
  candidate, so it is idempotent, never a second unread interruption.
* **Corrections supersede, they do not add.** A newer letter for a decision that
  has not been presented replaces the pending pointer. The operator sees the
  latest stable state, not the debugging timeline.
* **Attention is scarce and receiver-owned.** Presentation is scheduled by the
  existing :class:`saimail.human_attention.AttentionQueue` -- one presentation
  per 24 hours by default -- through its own two-phase reserve/ack protocol.
  This module adds no second scheduler, no reminder and no requeue. A sender
  cannot spend a slot by rewording, re-subjecting, re-triggering, splitting one
  decision into several issues, or by declaring a louder class.
* **The visible body is a contract.** At most 600 UTF-8 bytes and 4 logical
  lines. An oversized request is refused before presentation and must be
  rewritten; prose is never truncated into a lie.
* **Presence is receiver context.** When the host knows the operator is in the
  chat, an ordinary action request stays in the chat. When presence is unknown
  the attention queue decides. Absent a trustworthy signal, presence is
  ``UNKNOWN``, never ``ABSENT``; sender prose never claims presence either way.

Transport is untouched. An agent letter still exists durably, is still readable
in the ordinary mailbox, and still costs the operator nothing. Only *presentation*
is scarce. ``NOT_AN_INTERRUPT`` is the ordinary path for a human writing
ordinary correspondence, and it is the default for every message that carries no
declaration: the strict gate is specifically for automated senders, and a human
using ``saimail-local send`` by hand keeps full ordinary mail.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from sailang import Record, SailangError
from saimail import human_attention as _attention
from saimail import postoffice
from saimail.postoffice import _OsFileLock

FORMAT = "SAIMAIL-OPERATOR-INTERRUPT1"
SCHEMA = "SAIMAIL_OPERATOR_INTERRUPT_1"
LEDGER_SCHEMA = "SAIMAIL_OPERATOR_INTERRUPT_LEDGER_1"
INTERRUPT_DIR = "operator-interrupt"

#: The closed eligibility set. A class outside it is ineligible, so a sender
#: cannot invent a louder one; "no class" is ineligible too.
OPERATOR_ACTION_REQUIRED = "OPERATOR_ACTION_REQUIRED"
DATA_OR_MONEY_RISK = "DATA_OR_MONEY_RISK"
CROSS_PROJECT_CRITICAL_DISCOVERY = "CROSS_PROJECT_CRITICAL_DISCOVERY"
ELIGIBLE_CLASSES = frozenset({
    OPERATOR_ACTION_REQUIRED, DATA_OR_MONEY_RISK, CROSS_PROJECT_CRITICAL_DISCOVERY})

#: Receiver-side origin context. The receiver states whether automation produced
#: the message; a sender may not declare its own importance, including by
#: declaring that it is a person. ``HUMAN`` skips the gate: ordinary hand-written
#: correspondence is not an automated interruption.
ORIGIN_HUMAN = "HUMAN"
ORIGIN_AGENT = "AGENT"
ORIGINS = frozenset({ORIGIN_HUMAN, ORIGIN_AGENT})

#: Receiver-owned operator presence. ``ABSENT`` is deliberately not a value:
#: absence of a trustworthy signal is ``UNKNOWN``, never proof of absence.
PRESENCE_ACTIVE_CHAT = "ACTIVE_CHAT"
PRESENCE_UNKNOWN = "UNKNOWN"
PRESENCE_STATES = frozenset({PRESENCE_ACTIVE_CHAT, PRESENCE_UNKNOWN})

#: The compact operator presentation contract. Refused, never truncated.
MAX_OPERATOR_BODY_BYTES = 600
MAX_OPERATOR_BODY_LINES = 4

#: Deferral is inert data handed back to the caller. A risk class may therefore
#: stay pending when the budget is spent; it never spends a slot by itself.
DEFERRAL_BY_CLASS = {
    DATA_OR_MONEY_RISK: "ESCALATE_AND_HALT",
    OPERATOR_ACTION_REQUIRED: "BLOCK_UNTIL_HUMAN",
    CROSS_PROJECT_CRITICAL_DISCOVERY: "QUEUE_AND_CONTINUE",
}

#: Receiver-side queue class. It orders candidates; it never buys a slot, and
#: ``CRITICAL_RECOVERY`` has no budget bypass here either.
ALLOCATION_BY_CLASS = {
    DATA_OR_MONEY_RISK: "CRITICAL_RECOVERY",
    OPERATOR_ACTION_REQUIRED: "DECISION_REQUEST",
    CROSS_PROJECT_CRITICAL_DISCOVERY: "AMBIGUITY_RESOLUTION",
}

# Result vocabulary. Every one of these is a successful, non-error outcome.
NOT_AN_INTERRUPT = "NOT_AN_INTERRUPT"
UNSETTLED = "UNSETTLED"
INELIGIBLE_CLASS = "INELIGIBLE_CLASS"
ORIGIN_NOT_AUTOMATION = "ORIGIN_NOT_AUTOMATION"
PRESENCE_CHAT_SUFFICIENT = "PRESENCE_CHAT_SUFFICIENT"
ADMITTED = "ADMITTED"
DUPLICATE_DECISION = "DUPLICATE_DECISION"
SUPERSEDED = "SUPERSEDED"
ALREADY_PRESENTED = "ALREADY_PRESENTED"
PRESENTED = "PRESENTED"
NOTHING_PENDING = "NOTHING_PENDING"
PENDING_FULL = "PENDING_FULL"

# Refusal codes. These are the cases a caller must fix before anything is tried.
INTERRUPT_MALFORMED = "INTERRUPT_MALFORMED"
INTERRUPT_BAD_CLASS = "INTERRUPT_BAD_CLASS"
INTERRUPT_BAD_DECISION_ID = "INTERRUPT_BAD_DECISION_ID"
INTERRUPT_BAD_WORK = "INTERRUPT_BAD_WORK"
INTERRUPT_BAD_ORIGIN = "INTERRUPT_BAD_ORIGIN"
INTERRUPT_BAD_PRESENCE = "INTERRUPT_BAD_PRESENCE"
OPERATOR_BODY_TOO_LARGE = "OPERATOR_BODY_TOO_LARGE"
INTERRUPT_LEDGER_CORRUPT = "INTERRUPT_LEDGER_CORRUPT"
INTERRUPT_BAD_ENVELOPE = "INTERRUPT_BAD_ENVELOPE"

#: The pending set is bounded. Every admitted decision writes a durable queue
#: candidate the queue can never retire, so an unbounded pile would both flood
#: the operator's queue and let cheap low-allocation letters sit in front of a
#: real stop. A full set refuses the next arrival of any class; the letter stays
#: durable mail and the operator sees the bound in ``status``.
MAX_PENDING_DECISIONS = 8

OPERATOR_ACTION_CODES = frozenset({OPERATOR_BODY_TOO_LARGE})

DECISION_DOMAIN = b"SAIMAIL-OPERATOR-INTERRUPT-DECISION1\x00"

_FIELDS = frozenset({"schema", "class", "decision_id", "work", "settled", "body"})
_LEDGER_FIELDS = frozenset({
    "SCHEMA", "DECISION", "TO_HUMAN", "WORK", "CLASS", "ENVELOPE", "STATE",
    "BODY", "RESERVATION", "ENQUEUED_AT", "UPDATED_AT"})

_WORK_RE = re.compile(r"T-[0-9]+")
_DECISION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_HUMAN_ID_RE = re.compile(r"^human-id:sha256:[0-9a-f]{64}$")
_REF_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

PENDING = "PENDING"
SHOWN = "PRESENTED"


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False) + "\n").encode("utf-8")


def _reject_free_text(value, name: str, *, multiline: bool = False) -> None:
    """Printable text only. A line break is part of the compact body contract."""
    if not isinstance(value, str) or not value:
        _reject(INTERRUPT_MALFORMED, f"{name} is bounded printable text")
    allowed = set("\n\t") if multiline else set()
    for char in value:
        if char in allowed:
            continue
        if ord(char) < 32 or 0xD800 <= ord(char) <= 0xDFFF or char in "\x7f\u2028\u2029":
            _reject(INTERRUPT_MALFORMED, f"{name} is bounded printable text")


def _check_body(body: str) -> str:
    """Refuse an oversized operator request; never shorten the sender's words."""
    _reject_free_text(body.strip(), "body", multiline=True)
    lines = body.count("\n") + 1
    if len(body.encode("utf-8")) > MAX_OPERATOR_BODY_BYTES or lines > MAX_OPERATOR_BODY_LINES:
        _reject(OPERATOR_BODY_TOO_LARGE,
                f"an operator interruption is at most {MAX_OPERATOR_BODY_BYTES} UTF-8 bytes and "
                f"{MAX_OPERATOR_BODY_LINES} lines; this request is {len(body.encode('utf-8'))} "
                f"bytes in {lines} lines. Put the investigation in the chat and the Work "
                "evidence, and send only: what stopped, why you must act, one exact action.")
    return body.strip()


# --------------------------------------------------------------------
# the declared side: what an automated sender may state
# --------------------------------------------------------------------

def declaration(*, class_name: str, decision_id: str, work: str, body: str,
                settled: bool = True) -> dict:
    """Validate one interruption declaration before it is ever sealed.

    The result is the exact field set carried inside the message. It states a
    class, a stable decision identity and a compact operator body; it cannot
    state urgency, priority, presence or receiver policy, because no such field
    exists here to fill.
    """
    if class_name not in ELIGIBLE_CLASSES:
        _reject(INTERRUPT_BAD_CLASS,
                f"an operator interruption class is one of {sorted(ELIGIBLE_CLASSES)}; "
                "everything else is ordinary correspondence")
    if not isinstance(decision_id, str) or not _DECISION_ID_RE.fullmatch(decision_id):
        _reject(INTERRUPT_BAD_DECISION_ID,
                "decision_id is a stable token for ONE operator decision; a correction or a "
                "retraction reuses it, because the decision did not change")
    if not isinstance(work, str) or not _WORK_RE.fullmatch(work):
        _reject(INTERRUPT_BAD_WORK, "an operator interruption names the Work it stops")
    if not isinstance(settled, bool):
        _reject(INTERRUPT_MALFORMED, "settled is true or false")
    return {"schema": SCHEMA, "class": class_name, "decision_id": decision_id,
            "work": work, "settled": settled, "body": _check_body(body)}


def declaration_record(*, seat: str, class_name: str, decision_id: str, work: str,
                       body: str, settled: bool = True, created: str | None = None,
                       evidence: str = "0") -> Record:
    """Seal one declaration as an ordinary observation record.

    This is transport reuse, not a new wire field: the same ``KIND:O`` shape
    ``notify`` already uses for a letter carries the declaration as its claim.
    The receiver finds it by parsing that claim, never by reading prose.
    """
    stated = declaration(class_name=class_name, decision_id=decision_id,
                         work=work, body=body, settled=settled)
    return Record.create(
        KIND="O", SRC="AGENT:" + seat, SUBJ=work, CLAIM=json.dumps(
            stated, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        TYPE="OBS", STATUS="U1", EV=evidence,
        CREATED=created or postoffice.utc_now())


def _no_repeated_keys(pairs):
    """Refuse a repeated JSON key instead of silently keeping the last one."""
    value = {}
    for key, item in pairs:
        if key in value:
            _reject(INTERRUPT_MALFORMED,
                    f"the declaration repeats the key {key!r}; a reader that resolved it "
                    f"the other way would see a different interruption")
        value[key] = item
    return value


def parse_declaration(record) -> dict | None:
    """The declared metadata of one record, or ``None`` when it declares none.

    Accepts a canonical ``Record`` or the public ``open``/``reopen`` command
    result, so a receiver reading what the CLI actually gives it needs no
    private accessor. A record that claims this schema and carries anything
    else refuses: a malformed declaration is a broken promise, not ordinary mail.
    """
    if isinstance(record, dict) and "claim" in record:
        # The CLI's secret-free command result spells the fields lowercase.
        if record.get("kind") not in (None, "O"):
            return None
        claim = record["claim"]
    else:
        claim = record.get("CLAIM") if hasattr(record, "get") else None
    if not isinstance(claim, str) or not claim.strip().startswith("{"):
        return None
    try:
        # Repeated keys are refused, never last-one-wins: another reader could
        # legitimately resolve the duplicate the other way.
        value = json.loads(claim, object_pairs_hook=_no_repeated_keys)
    except (ValueError, RecursionError):
        return None
    if not isinstance(value, dict):
        return None
    if value.get("schema") != SCHEMA:
        return None
    if set(value) != _FIELDS:
        _reject(INTERRUPT_MALFORMED,
                f"a declaration carries exactly {sorted(_FIELDS)}")
    if value["class"] not in ELIGIBLE_CLASSES:
        _reject(INTERRUPT_BAD_CLASS,
                f"an operator interruption class is one of {sorted(ELIGIBLE_CLASSES)}")
    if not isinstance(value["decision_id"], str) \
            or not _DECISION_ID_RE.fullmatch(value["decision_id"]):
        _reject(INTERRUPT_BAD_DECISION_ID, "decision_id is a bounded stable decision token")
    if not isinstance(value["work"], str) or not _WORK_RE.fullmatch(value["work"]):
        _reject(INTERRUPT_BAD_WORK, "work is T-<number>")
    if not isinstance(value["settled"], bool):
        _reject(INTERRUPT_MALFORMED, "settled is true or false")
    _check_body(value["body"])
    return dict(value)


# --------------------------------------------------------------------
# the receiver side
# --------------------------------------------------------------------

def human_id(workspace) -> str:
    """The receiver's own human identity, derived from its durable mailbox key.

    Receiver-owned by construction: it is a function of the receiver's identity,
    so no sender and no other process can name a different person.
    """
    return "human-id:sha256:" + hashlib.sha256(
        str(workspace.recipient_kid).encode("utf-8")).hexdigest()


def decision_identity(to_human: str, work: str, decision_id: str) -> str:
    """The stable operator decision, bound and nothing else.

    Two letters that differ only in wording, subject, trigger or envelope share
    this value, so the second is idempotent rather than a second interruption.
    """
    material = (DECISION_DOMAIN + to_human.encode("utf-8") + b"\x00"
                + work.encode("ascii") + b"\x00" + decision_id.encode("utf-8"))
    return "decision:" + hashlib.sha256(material).hexdigest()


def decision_key(to_human: str, work: str, decision_id: str) -> str:
    """The attention candidate one decision occupies, in this receiver's queue.

    It is the receiver's own candidate identity over the stable decision, so the
    queue's dedup and this module's dedup are the same dedup -- there is no
    second place for a sender to spend a slot.
    """
    return _attention.attention_candidate_id(
        to_human, _attention.EXTERNAL_REFERENCE, decision_identity(to_human, work, decision_id))


def _check_human(to_human: str) -> str:
    if not isinstance(to_human, str) or not _HUMAN_ID_RE.fullmatch(to_human):
        _reject(INTERRUPT_MALFORMED, "TO_HUMAN is human-id:sha256:<64 lowercase hex>")
    return to_human


def _check_now(value: str) -> str:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        _reject(INTERRUPT_MALFORMED, "receiver time is exact UTC YYYY-MM-DDTHH:MM:SSZ")
    return value


def _replace_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staged = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with staged.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(staged, path)
    finally:
        staged.unlink(missing_ok=True)


class _InterruptLock(_OsFileLock):
    def __init__(self, path: Path):
        super().__init__(path, busy_code="INTERRUPT_LOCK_TIMEOUT")


class Receiver:
    """One receiver's interruption ledger and attention queue, under one root."""

    def __init__(self, root, *, to_human: str, budget=None, clock=None):
        self.to_human = _check_human(to_human)
        self.root = Path(root) / INTERRUPT_DIR
        if budget is None:
            budget = _attention.AttentionBudget(
                max_presentations=_attention.DEFAULT_MAX_PRESENTATIONS,
                period_seconds=_attention.DEFAULT_PERIOD_SECONDS)
        if not isinstance(budget, _attention.AttentionBudget):
            _reject(INTERRUPT_MALFORMED, "budget is an AttentionBudget")
        self.budget = budget
        self.clock = clock or postoffice.utc_now

    def queue(self) -> _attention.AttentionQueue:
        """The one scheduler. Presentation capacity is its budget, never a flag."""
        return _attention.AttentionQueue(self.root.parent, human_id=self.to_human,
                                         budget=self.budget, clock=self.clock)

    # -- ledger ---------------------------------------------------------

    def _lock(self) -> _InterruptLock:
        return _InterruptLock(self.root / "interrupt.lock")

    def _entry_path(self, decision: str) -> Path:
        return self.root / "decisions" / (decision.rsplit(":", 1)[1] + ".json")

    def _read_entry(self, decision: str) -> dict | None:
        path = self._entry_path(decision)
        if not path.is_file():
            return None
        try:
            raw = path.read_bytes()
        except OSError as exc:
            _reject(INTERRUPT_LEDGER_CORRUPT, f"interruption ledger entry unreadable: {exc}")
        try:
            value = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError, RecursionError):
            _reject(INTERRUPT_LEDGER_CORRUPT, "an interruption ledger entry is not JSON")
        if not isinstance(value, dict) or set(value) != _LEDGER_FIELDS \
                or value.get("SCHEMA") != 1 or _canonical(value) != raw:
            _reject(INTERRUPT_LEDGER_CORRUPT, "an interruption ledger entry is not canonical")
        if value["DECISION"] != decision or value["TO_HUMAN"] != self.to_human \
                or not isinstance(value["STATE"], str) or value["STATE"] not in (PENDING, SHOWN):
            _reject(INTERRUPT_LEDGER_CORRUPT, "an interruption ledger entry disagrees with itself")
        return value

    def _write_entry(self, value: dict) -> None:
        _replace_atomic(self._entry_path(value["DECISION"]), _canonical(value))

    def entries(self) -> list:
        directory = self.root / "decisions"
        if not directory.is_dir():
            return []
        found = []
        for path in sorted(directory.iterdir()):
            if path.name.startswith("."):
                continue
            if not _HEX64_RE.fullmatch(path.name[:-len(".json")] if path.name.endswith(".json")
                                        else ""):
                _reject(INTERRUPT_LEDGER_CORRUPT, f"{path.name!r} is not a ledger entry name")
            found.append(self._read_entry("sha256:" + path.name[:-len(".json")]))
        return [entry for entry in found if entry is not None]

    # -- admission ------------------------------------------------------

    def admit(self, envelope_id: str, declared: dict, *, origin: str = ORIGIN_AGENT,
              presence: str = PRESENCE_UNKNOWN) -> dict:
        """One receiver decision about one message. Transport is never blocked.

        Admission means "this is a real candidate for the operator's attention",
        not "the operator has been interrupted". Presentation is a separate,
        budgeted step (:meth:`reserve` then :meth:`acknowledge`).
        """
        if not isinstance(envelope_id, str) or not _REF_RE.fullmatch(envelope_id):
            _reject(INTERRUPT_BAD_ENVELOPE, "an interruption is admitted by exact ENVELOPE_ID")
        if origin not in ORIGINS:
            _reject(INTERRUPT_BAD_ORIGIN, f"origin is one of {sorted(ORIGINS)}")
        if presence not in PRESENCE_STATES:
            _reject(INTERRUPT_BAD_PRESENCE,
                    f"presence is receiver-owned context, one of {sorted(PRESENCE_STATES)}")
        if not isinstance(declared, dict) or set(declared) != _FIELDS \
                or declared.get("schema") != SCHEMA:
            _reject(INTERRUPT_MALFORMED, "admission needs a validated declaration")
        # Re-check the visible body here: the sender helper validating it is a
        # convenience, and the receiver cannot be talked out of its own contract.
        _check_body(declared["body"])
        if origin == ORIGIN_HUMAN:
            return self._view(NOT_AN_INTERRUPT, envelope_id, declared,
                              detail="a hand-written letter is ordinary correspondence, "
                                     "not an automated operator interruption")
        if not declared["settled"]:
            return self._view(UNSETTLED, envelope_id, declared,
                              detail="the diagnosis is not settled; it stays durable mail and "
                                     "presents nothing. Settle the diagnosis, then send one "
                                     "letter for the decision")
        if declared["class"] not in ELIGIBLE_CLASSES:
            return self._view(INELIGIBLE_CLASS, envelope_id, declared,
                              detail="this class is not an operator interruption; the message "
                                     "is ordinary durable correspondence")
        if presence == PRESENCE_ACTIVE_CHAT and declared["class"] == OPERATOR_ACTION_REQUIRED:
            return self._view(PRESENCE_CHAT_SUFFICIENT, envelope_id, declared,
                              detail="the operator is in the chat, so an ordinary action "
                                     "request stays in the chat and presents nothing")
        now = _check_now(self.clock())
        decision = decision_key(self.to_human, declared["work"], declared["decision_id"])
        with self._lock():
            existing = self._read_entry(decision)
            if existing is not None and existing["STATE"] == SHOWN:
                return self._view(ALREADY_PRESENTED, envelope_id, declared,
                                  decision=decision, entry=existing,
                                  detail="this decision was already interrupted once; one "
                                         "decision gets one interruption, and the rest stays "
                                         "readable in the mailbox")
            if existing is not None and existing["CLASS"] != declared["class"]:
                # Reclassifying one decision must not buy a second slot, and the
                # queue refuses a policy change anyway. Refuse here, before any
                # write, so the ledger and the scheduler can never disagree.
                _reject(INTERRUPT_BAD_CLASS,
                        f"decision {declared['decision_id']} of {declared['work']} is "
                        f"already admitted as {existing['CLASS']}; a different class is a "
                        f"different decision_id")
            if existing is not None and existing["ENVELOPE"] == envelope_id \
                    and existing["BODY"] == declared["body"]:
                return self._view(DUPLICATE_DECISION, envelope_id, declared,
                                  decision=decision, entry=existing,
                                  detail="exact retry of one decision: idempotent, no second "
                                         "unread letter")
        # Enqueue BEFORE the ledger write. A crash in between leaves a candidate
        # the receiver can recognise and self-heal (reserve() releases a candidate
        # that names no admitted decision, and the retry re-enqueues), whereas a
        # ledger entry without a candidate would sit pending and never clear.
        # The bound is checked first: a refusal must leave no candidate behind,
        # because the queue has no way to retire one later.
        self._require_pending_room(decision)
        self.queue().admit_receiver_candidate(
            source_kind=_attention.EXTERNAL_REFERENCE,
            source_ref=decision_identity(self.to_human, declared["work"],
                                         declared["decision_id"]),
            allocation=ALLOCATION_BY_CLASS[declared["class"]],
            deferral_policy=DEFERRAL_BY_CLASS[declared["class"]])
        with self._lock():
            existing = self._read_entry(decision)
            self._write_entry({
                "SCHEMA": 1, "DECISION": decision, "TO_HUMAN": self.to_human,
                "WORK": declared["work"], "CLASS": declared["class"],
                "ENVELOPE": envelope_id, "STATE": PENDING, "BODY": declared["body"],
                "RESERVATION": existing["RESERVATION"] if existing else "",
                "ENQUEUED_AT": existing["ENQUEUED_AT"] if existing else now,
                "UPDATED_AT": now,
            })
            view = self._view(SUPERSEDED if existing is not None else ADMITTED,
                              envelope_id, declared, decision=decision,
                              entry=self._read_entry(decision),
                              detail=("a newer letter for the same decision replaced the "
                                      "pending one; the operator sees the latest stable "
                                      "state, never the debugging timeline"
                                      if existing is not None else
                                      "admitted as a candidate; presenting it still costs "
                                      "the receiver's one attention slot"))
        return view

    def _require_pending_room(self, decision: str) -> None:
        """Bound the pending set without ever evicting an admitted decision.

        An admitted decision owns a durable queue candidate, and the queue has no
        retirement path, so dropping one here would leave the queue serving a
        candidate whose decision the receiver no longer holds -- the queue would
        then answer every presentation with nothing to show. The bound is
        therefore a door, not a ranking: at the cap the next arrival is refused
        of any class, stays ordinary durable mail, and the operator still sees it
        in the mailbox and in ``status``.
        """
        with self._lock():
            pending = [entry for entry in self.entries() if entry["STATE"] == PENDING]
            if len(pending) < MAX_PENDING_DECISIONS or decision in {
                    entry["DECISION"] for entry in pending}:
                return
            _reject(PENDING_FULL,
                    f"{len(pending)} decisions are already waiting for the operator "
                    f"(the cap is {MAX_PENDING_DECISIONS}); this one stays durable mail "
                    f"and is read from the mailbox until one of them is presented")

    def _view(self, status: str, envelope_id: str, declared: dict, *, detail: str,
              decision: str | None = None, entry: dict | None = None) -> dict:
        return {"schema": FORMAT, "status": status, "envelope_id": envelope_id,
                "work": declared["work"], "class": declared["class"],
                "decision_id": declared["decision_id"], "settled": declared["settled"],
                "decision": decision, "presented": bool(entry and entry["STATE"] == SHOWN),
                "body_bytes": len(declared["body"].encode("utf-8")),
                "budget": self.budget.max_presentations,
                "period_seconds": self.budget.period_seconds,
                "detail": detail}

    # -- presentation ---------------------------------------------------

    def reserve(self) -> dict:
        """Propose one operator interruption. Consumes nothing until ``acknowledge``.

        The queue's lease is what stops two concurrent presenters from both
        taking the single default slot.
        """
        selection = self.queue().reserve_next()
        if selection.status != _attention.RESERVED:
            return {"schema": FORMAT, "status": selection.status,
                    "candidate": None if selection.candidate is None else
                    selection.candidate.candidate_id,
                    "presented": False, "detail": _deferral_detail(selection.status)}
        decision = selection.candidate.candidate_id
        with self._lock():
            entry = self._read_entry(decision)
            if entry is None or entry["STATE"] != PENDING:
                # Durable attention state outlived a dropped decision pointer;
                # hand the slot straight back rather than inventing a message.
                self.queue().release(selection.reservation.reservation_id)
                return {"schema": FORMAT, "status": NOTHING_PENDING, "candidate": decision,
                        "presented": False,
                        "detail": "an attention candidate names no admitted decision; "
                                  "nothing is presented"}
            self._write_entry({**entry, "UPDATED_AT": _check_now(self.clock()),
                               "RESERVATION": selection.reservation.reservation_id})
            return {"schema": FORMAT, "status": _attention.RESERVED, "candidate": decision,
                    "reservation_id": selection.reservation.reservation_id,
                    "work": entry["WORK"], "class": entry["CLASS"],
                    "envelope_id": entry["ENVELOPE"], "body": entry["BODY"],
                    "body_bytes": len(entry["BODY"].encode("utf-8")),
                    "presented": False,
                    "detail": "reserved one presentation slot; acknowledge after the operator "
                              "surface actually shows it"}

    def acknowledge(self, reservation_id: str) -> dict:
        """Record the presentation. The only step that spends the slot."""
        receipt = self.queue().ack_presented(reservation_id)
        with self._lock():
            entry = self._read_entry(receipt.receipt.candidate_id)
            if entry is None:
                _reject(INTERRUPT_LEDGER_CORRUPT, "a presented candidate names no admitted decision")
            self._write_entry({**entry, "STATE": SHOWN, "RESERVATION": "",
                               "UPDATED_AT": receipt.receipt.presented_at})
        return {"schema": FORMAT, "status": PRESENTED,
                "decision": receipt.receipt.candidate_id,
                "envelope_id": entry["ENVELOPE"], "work": entry["WORK"],
                "class": entry["CLASS"], "body": entry["BODY"],
                "body_bytes": len(entry["BODY"].encode("utf-8")),
                "presented_at": receipt.receipt.presented_at, "presented": True,
                "detail": "one operator interruption presented; it records a surfacing, "
                          "never that the operator read or acted on it"}

    def release(self, reservation_id: str) -> dict:
        """Drop one reservation; the decision stays pending and nothing is spent."""
        released = self.queue().release(reservation_id)
        with self._lock():
            for entry in self.entries():
                if entry["RESERVATION"] == reservation_id:
                    self._write_entry({**entry, "RESERVATION": "",
                                       "UPDATED_AT": _check_now(self.clock())})
        return released

    def outstanding(self) -> list:
        """Reservations this receiver holds and has not acknowledged.

        A presentation crosses process boundaries: the slot is reserved before
        the operator surface shows anything and acknowledged afterwards, so the
        acknowledging call is usually not the reserving one. The pointer lives in
        this receiver's own ledger, because it is the receiver's own outstanding
        debt and no shared scheduler needs to know about it. Asking spends
        nothing; a presented decision has already cleared its pointer.
        """
        return [entry["RESERVATION"] for entry in self.entries()
                if entry["STATE"] == PENDING and entry["RESERVATION"]]

    # -- inspection -----------------------------------------------------

    def status(self) -> dict:
        """Pending and presented interruptions, plus the rolling budget state."""
        budget = self.queue().budget_state()
        entries = self.entries()
        return {
            "schema": FORMAT, "to_human": self.to_human,
            "pending": [{"decision": entry["DECISION"], "work": entry["WORK"],
                         "class": entry["CLASS"], "envelope_id": entry["ENVELOPE"],
                         "body": entry["BODY"], "updated_at": entry["UPDATED_AT"]}
                        for entry in entries if entry["STATE"] == PENDING],
            "presented": [{"decision": entry["DECISION"], "work": entry["WORK"],
                           "class": entry["CLASS"], "envelope_id": entry["ENVELOPE"],
                           "updated_at": entry["UPDATED_AT"]}
                          for entry in entries if entry["STATE"] == SHOWN],
            "budget": {"max_presentations": budget.max_presentations,
                       "period_seconds": budget.period_seconds,
                       "consumed": budget.consumed, "available": budget.available,
                       "presented_in_window": budget.presented_in_window,
                       "active_reservations": budget.active_reservations,
                       "pending_candidates": budget.pending_candidates},
            "operator_unread": len([e for e in entries if e["STATE"] == SHOWN]),
            "detail": "unread counts admitted interruptions only; ordinary agent and work "
                      "correspondence is durable mail and never enters this count",
        }


def _deferral_detail(status: str) -> str:
    return {
        _attention.NO_MESSAGE: "nothing is waiting for the operator; zero interruptions is a "
                                "successful outcome",
        _attention.DEFERRED: "queued: this decision waits for the next available slot",
        _attention.ATTENTION_BLOCKED: "pending: an ordinary action request cannot proceed "
                                      "until the operator acts, and its slot is spent",
        _attention.ATTENTION_HALT_REQUIRED: "pending risk: it stays queued, still unpresented, "
                                            "because the receiver's slot is spent",
    }.get(status, "the receiver attention queue returned no presentation opportunity")


__all__ = [
    "ADMITTED",
    "ALREADY_PRESENTED",
    "CROSS_PROJECT_CRITICAL_DISCOVERY",
    "DATA_OR_MONEY_RISK",
    "DECISION_DOMAIN",
    "DUPLICATE_DECISION",
    "ELIGIBLE_CLASSES",
    "FORMAT",
    "INELIGIBLE_CLASS",
    "INTERRUPT_BAD_CLASS",
    "INTERRUPT_BAD_DECISION_ID",
    "INTERRUPT_BAD_ENVELOPE",
    "INTERRUPT_BAD_ORIGIN",
    "INTERRUPT_BAD_PRESENCE",
    "INTERRUPT_BAD_WORK",
    "INTERRUPT_LEDGER_CORRUPT",
    "INTERRUPT_MALFORMED",
    "LEDGER_SCHEMA",
    "MAX_OPERATOR_BODY_BYTES",
    "MAX_OPERATOR_BODY_LINES",
    "NOTHING_PENDING",
    "NOT_AN_INTERRUPT",
    "OPERATOR_ACTION_CODES",
    "OPERATOR_ACTION_REQUIRED",
    "OPERATOR_BODY_TOO_LARGE",
    "ORIGINS",
    "ORIGIN_AGENT",
    "ORIGIN_HUMAN",
    "PENDING",
    "PRESENCE_ACTIVE_CHAT",
    "PRESENCE_CHAT_SUFFICIENT",
    "PRESENCE_STATES",
    "PRESENCE_UNKNOWN",
    "PRESENTED",
    "SCHEMA",
    "SHOWN",
    "SUPERSEDED",
    "UNSETTLED",
    "Receiver",
    "decision_identity",
    "decision_key",
    "declaration",
    "declaration_record",
    "human_id",
    "parse_declaration",
]
