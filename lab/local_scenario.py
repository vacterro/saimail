"""FG-05 — one deterministic two-participant end-to-end local scenario.

This is integration evidence, not a new framework and not a live experiment.
It composes already-shipped public/stable APIs in the order the product expects
them and records one finite machine-readable result
(``LOCAL_SCENARIO_RESULT_1``). Nothing here reaches the network or a model, and
no hardware key is provisioned: participant keys are software keys derived
deterministically from scenario labels, so a fresh run is reproducible in
identity even though SENV2 minting is (correctly) randomised per transport
object.

This module is the pure offline engine: it has no CLI, no network and no
filesystem teardown of its own (the LAB isolation contract forbids ``socket``
and ``shutil`` here). The documented one-command operator entrypoint that adds
the socket tripwire and the temp-root lifecycle is
``python tools/fg05_local_scenario.py``.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from sailang import Record, SailangError
from sailang import parse as parse_record
from saimail import (
    ally_advice as aa,
)
from saimail import (
    ally_generation as ag,
)
from saimail import (
    envelope,
    legacy,
    postoffice,
    promotion,
    sailetter,
)
from saimail import (
    human_attention as ha,
)

SCENARIO = "FG05-LOCAL-SCENARIO"
SCENARIO_VERSION = 1
RESULT_SCHEMA = "LOCAL_SCENARIO_RESULT_1"

INJECTED_FAILURE = "FG05_INJECTED_WRITE_FAILURE"
SCENARIO_TIME = "2026-09-20T12:00:00Z"
SWEEP_TIME = "2026-09-20T14:00:00Z"

SEAT_A = "FG05A"
SEAT_B = "FG05B"

#: A synthetic private-payload marker that must never be persisted or printed.
PRIVATE_MARKER = "fg05-private-marker-6f2a1c-not-persisted"

#: SECP256R1 group order, used only to derive a valid deterministic scalar.
_P256_ORDER = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551

_EVIDENCE = "sha256:" + "a1" * 32
_EVENT = "sha256:" + "b2" * 32
_REF_WORKED = "sha256:" + "c3" * 32
_REF_FAILED = "sha256:" + "d4" * 32
_REF_WRONG = "sha256:" + "e5" * 32


def _seed(label: str, index: int) -> bytes:
    return hashlib.sha256(
        b"SAIMAIL-FG05-LOCAL-SCENARIO-KEY\x00" + label.encode("ascii")
        + b"\x00" + str(index).encode("ascii")
    ).digest()


def _ed25519(label: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_seed(label, 0))


def _x25519(label: str) -> X25519PrivateKey:
    return X25519PrivateKey.from_private_bytes(_seed(label, 1))


def _p256(label: str) -> ec.EllipticCurvePrivateKey:
    scalar = int.from_bytes(_seed(label, 2), "big") % (_P256_ORDER - 1) + 1
    return ec.derive_private_key(scalar, ec.SECP256R1())


def _ref(tag: str) -> str:
    return "sha256:" + hashlib.sha256(tag.encode("utf-8")).hexdigest()


def _refs(*tags: str) -> tuple:
    return tuple(sorted(_ref(tag) for tag in tags))


# --------------------------------------------------------------------------
# participants
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Identity:
    """One deterministic software participant identity (no hardware, no secrets)."""

    seat: str
    sender_key: Ed25519PrivateKey
    recipient_key: X25519PrivateKey
    human_key: ec.EllipticCurvePrivateKey

    @property
    def sender_kid(self) -> str:
        return envelope.fingerprint(self.sender_key.public_key())

    @property
    def recipient_kid(self) -> str:
        return envelope.fingerprint(self.recipient_key.public_key())

    @property
    def human_id(self) -> str:
        return sailetter.human_id(self.human_key.public_key())

    @property
    def provider(self) -> sailetter.SoftwareP256Provider:
        return sailetter.SoftwareP256Provider(self.human_key)


def identity(label: str, seat: str) -> Identity:
    return Identity(seat=seat, sender_key=_ed25519(label),
                    recipient_key=_x25519(label), human_key=_p256(label))


@dataclass
class Participant:
    """A rooted participant whose durable objects are rebuilt only from its root.

    ``connect`` constructs the receiver-owned registries, the Post Office, the
    ciphertext-only letter store and the attention queue from the same durable
    root and identity every time; ``disconnect`` drops the live objects. No
    durable state is cached on the instance, so a restart is a real
    reconstruction rather than a witness of Python object identity.
    """

    identity: Identity
    root: Path
    interest: postoffice.HeaderInterest
    default_ttl: int
    clock: Callable[[], str]
    office: postoffice.PostOffice | None = None
    letters: sailetter.HumanPrivateStore | None = None
    attention: ha.AttentionQueue | None = None
    peers: tuple = field(default=())

    def connect(self, peers) -> None:
        self.peers = tuple(peers)
        sender_registry = envelope.KeyRegistry(
            {p.identity.seat: [p.identity.sender_key.public_key()] for p in self.peers})
        recipient_registry = envelope.RecipientKeyRegistry(
            {self.identity.seat: [self.identity.recipient_key.public_key()]})
        self.office = postoffice.PostOffice(
            self.root, seat=self.identity.seat, sender_registry=sender_registry,
            recipient_registry=recipient_registry, interest=self.interest,
            clock=self.clock, default_ttl=self.default_ttl)
        self.letters = sailetter.HumanPrivateStore(
            self.root, human_id=self.identity.human_id, sender_registry=sender_registry)
        self.attention = ha.AttentionQueue(
            self.root, human_id=self.identity.human_id, clock=self.clock,
            budget=ha.AttentionBudget(2, 86_400))

    def disconnect(self) -> None:
        self.office = None
        self.letters = None
        self.attention = None


def _participant(label: str, seat: str, root: Path) -> Participant:
    return Participant(
        identity=identity(label, seat), root=root,
        interest=postoffice.HeaderInterest.of(open_r3_kinds=frozenset({"DISCOVERY"})),
        default_ttl=postoffice.MIN_TTL_SECONDS,
        clock=lambda: SCENARIO_TIME,
    )


# --------------------------------------------------------------------------
# evidence accumulator
# --------------------------------------------------------------------------


@dataclass
class Evidence:
    checks: list = field(default_factory=list)

    def check(self, check_id: str, condition: object, detail: str = "") -> bool:
        ok = bool(condition)
        self.checks.append({
            "id": check_id, "ok": ok, "detail": "" if ok else (detail or "check failed"),
        })
        return ok

    @property
    def ok(self) -> bool:
        return all(entry["ok"] for entry in self.checks)


# --------------------------------------------------------------------------
# fault injection at durable-write boundaries
# --------------------------------------------------------------------------


@contextlib.contextmanager
def fail_once(target: object, name: str):
    """Make exactly the next call of ``target.name`` fail at the write boundary.

    The original attribute is restored in ``finally`` even on exception, and the
    failure is a named ``SailangError`` so no caller can mistake the injected
    boundary for a protocol verdict.
    """
    original = getattr(target, name)

    def wrapper(*args, **kwargs):
        def _raise():
            raise SailangError(INJECTED_FAILURE,
                               f"injected durable-write failure at {name}")
        setattr(target, name, original)
        _raise()

    setattr(target, name, wrapper)
    try:
        yield
    finally:
        setattr(target, name, original)


def contains_marker(root: Path, marker: str) -> bool:
    needle = marker.encode("utf-8")
    for path in Path(root).rglob("*"):
        if not path.is_file():
            continue
        try:
            if needle in path.read_bytes():
                return True
        except OSError:
            continue
    return False


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


# --------------------------------------------------------------------------
# scenario
# --------------------------------------------------------------------------


def _record(claim: str, *, subject: str = "queue-lease") -> Record:
    return Record.create(KIND="F", SRC="AGENT:fg05a", SUBJ=subject, CLAIM=claim,
                         TYPE="OBS", EV=_EVIDENCE, STATUS="U2", CREATED=SCENARIO_TIME)


def _seal_record(record: Record, sender: Identity, recipient: Identity, *,
                 ttl: str | None = None) -> str:
    return envelope.seal(
        record.canonical_text(), sender_private_key=sender.sender_key,
        sender_seat=sender.seat, recipient_seat=recipient.seat,
        recipient_public_key=recipient.recipient_key.public_key(),
        kind="DISCOVERY", topic="queue-ownership", created=SCENARIO_TIME, ttl=ttl)


class _NoAdviceGenerator:
    calls = 0

    def generate(self, source):
        self.calls += 1
        return ag.GeneratorResult.no_advice()


class _NeverCalledReviewer:
    calls = 0

    def review(self, resolved, corpus):
        self.calls += 1
        raise AssertionError("a NO_ADVICE run must not invoke the reviewer")


class _MissingResolver:
    def resolve(self, evidence_ref: str) -> str:
        return aa.MISSING


def _advice() -> aa.AllyAdvice:
    return aa.AllyAdvice(
        created=SCENARIO_TIME,
        work_context="fg05 local scenario work context",
        observed_scope="one local queue only",
        observed=(
            aa.AdviceObservation("recovery paths were added", _refs("o1", "o2")),
            aa.AdviceObservation("scope notes were added", _refs("o3")),
        ),
        inferred="this may describe premature convergence",
        guidance_mode=aa.CONSIDER_CHANGE,
        suggested="consider one reversible review pass",
        counterevidence=(aa.AdviceCounterevidence("later work self-corrected",
                                                  _refs("c1")),),
        uncertainty="this small sample may be specific to one window",
    )


def _corpus() -> ag.ReflectionCorpus:
    return ag.ReflectionCorpus(items=(
        ag.ReflectionItem(
            evidence_ref=_ref("o1"), source_domain=ag.PROJECT_OPERATIONAL,
            observed_at=SCENARIO_TIME, observed_scope="one local queue",
            content="corpus item one", event_ref=_ref("event-1")),
        ag.ReflectionItem(
            evidence_ref=_ref("o2"), source_domain=ag.PROJECT_OPERATIONAL,
            observed_at=SCENARIO_TIME, observed_scope="one local queue",
            content="corpus item two", event_ref=_ref("event-2")),
    ))


def run_scenario(base_dir, *, probe=None) -> dict:
    """Execute the whole scenario against ``base_dir`` and return the result.

    ``probe`` is an optional caller-owned dict used by the runner's network
    tripwire; the engine only reports the count it observes. The engine itself
    never imports ``socket`` (LAB isolation), so the sentinel lives in the
    operator runner and the test.
    """
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    ev = Evidence()
    probe = probe if probe is not None else {}
    effects = {
        "mail_accepts": 0, "mail_duplicates": 0, "durable_message_creations": 0,
        "explicit_opens": 0, "promotions": 0, "attention_reservations": 0,
        "attention_acknowledgements": 0, "tombstones": 0, "legacy_adoptions": 0,
        "legacy_recoveries": 0, "private_accepts": 0, "private_duplicates": 0,
        "injected_failures": 0,
    }
    result: dict = {
        "schema": RESULT_SCHEMA, "scenario": SCENARIO, "version": SCENARIO_VERSION,
        "time": SCENARIO_TIME,
    }

    # The network tripwire is installed by the caller (tools runner / test);
    # this engine never imports socket, so it only reports what the caller saw.
    with contextlib.nullcontext():
        A = _participant("alice", SEAT_A, base / "participant-a")
        B = _participant("bob", SEAT_B, base / "participant-b")
        A.connect([B])
        B.connect([A])

        ev.check("participants_isolated_roots", A.root != B.root and A.root.is_dir()
                 and B.root.is_dir())
        ev.check("participants_distinct_identities",
                 A.identity.sender_kid != B.identity.sender_kid
                 and A.identity.human_id != B.identity.human_id)

        # -- 1. SOURCE -> 2. PACKAGING ----------------------------------
        main_record = _record("queue lease expiry was observed twice")
        main_container = _seal_record(main_record, A.identity, B.identity)
        env_main = envelope.envelope_id(main_container)
        parsed_main = envelope.parse_header(main_container)
        ev.check("packaging_identity", env_main.startswith("sha256:") and len(env_main) == 71)
        ev.check("packaging_addressing",
                 parsed_main.get("FROM") == SEAT_A and parsed_main.get("TO") == SEAT_B)

        # -- 3. DELIVERY -------------------------------------------------
        r_main = B.office.deliver(main_container)
        if r_main.status == postoffice.ACCEPTED:
            effects["mail_accepts"] += 1
        ev.check("delivery_accepted", r_main.status == postoffice.ACCEPTED,
                 f"status={r_main.status}")
        ev.check("delivery_index_row", B.office.has_index_row(env_main))
        ev.check("delivery_no_plaintext_on_disk",
                 not contains_marker(B.root, main_record.claim))

        # -- 5. HEADER / DISCOVERY SCAN (budget + continuation) ---------
        scan_record = _record("second unread discovery for scan budget")
        scan_container = _seal_record(scan_record, A.identity, B.identity)
        env_scan = envelope.envelope_id(scan_container)
        r_scan = B.office.deliver(scan_container)
        if r_scan.status == postoffice.ACCEPTED:
            effects["mail_accepts"] += 1
        ev.check("scan_second_delivered", r_scan.status == postoffice.ACCEPTED)

        session = postoffice.PostOfficeSession(B.office, scan_budget=1, open_budget=10)
        first = session.scan(now=SCENARIO_TIME)
        ev.check("scan_budget_exact", first.rows_examined == 1 and first.exhausted
                 and first.cursor is not None)
        ev.check("scan_machine_verdict",
                 first.items and first.items[0].machine_verdict == "OPEN_R3")
        second = session.scan(cursor=first.cursor, now=SCENARIO_TIME)
        ev.check("scan_continuation", second.rows_examined == 1 and not second.exhausted)

        # -- 6. EXPLICIT OPEN -------------------------------------------
        opened_main = session.open_message(env_main,
                                           recipient_private_key=B.identity.recipient_key)
        effects["explicit_opens"] += 1
        ev.check("open_explicit_plaintext", opened_main.plaintext == main_record.canonical_bytes())
        receiver_view = parse_record(opened_main.plaintext)
        ev.check("open_claim_preserved", receiver_view.claim == main_record.claim)
        ev.check("open_evidence_preserved", receiver_view.is_evidence_attached
                 and receiver_view.get("EV") == _EVIDENCE)
        ev.check("open_uncertainty_preserved", receiver_view.status == "U2")
        ev.check("open_moves_to_read", B.office.bundle_state(env_main) == postoffice.READ_STATE)

        # -- 8. PROMOTION (separate action over the exact opened payload) -
        promoted_dir = B.office.mail_root / postoffice.PROMOTED
        before_promotion = sorted(p.name for p in promoted_dir.iterdir())
        proposal = promotion.propose(receiver_view, opened_main,
                                     reason="FG-05 local scenario promotion")
        effects["promotions"] += 1
        ev.check("promotion_binds_envelope", proposal["envelope"] == env_main)
        ev.check("promotion_claim_separated", proposal["claim"] == main_record.claim)
        ev.check("promotion_evidence_separated",
                 proposal["evidence"] == "EVIDENCE_REF_REQUIRED_AND_PRESENT")
        ev.check("promotion_is_not_a_writer",
                 proposal["written_by_this_call"] is False
                 and sorted(p.name for p in promoted_dir.iterdir()) == before_promotion)

        # -- 4. DEDUPLICATION (before and after read) -------------------
        dup_main = B.office.deliver(main_container)
        effects["mail_duplicates"] += 1
        ev.check("dedup_status_duplicate", dup_main.status == postoffice.DUPLICATE)
        ev.check("dedup_original_received_at", dup_main.received_at == r_main.received_at)
        ev.check("dedup_no_second_row", len(B.office.read_index()) == 2)

        # -- LEGACY succession ------------------------------------------
        packet = legacy.LegacyPacket(
            subject="queue-lease-recovery", observed_scope="notifications queue only",
            what_worked="heartbeat worked", what_worked_evidence=(_REF_WORKED,),
            what_failed="raising timeout failed", what_failed_evidence=(_REF_FAILED,),
            what_looked_right_but_was_wrong="clean depth looked conclusive",
            what_wrong_evidence=(_REF_WRONG,),
            watch_next="possible worker crash race", watch_next_evidence=(),
            watch_next_status="UNVERIFIED", created=SCENARIO_TIME)
        legacy_container = envelope.seal(
            packet.render(), sender_private_key=A.identity.sender_key, sender_seat=SEAT_A,
            recipient_seat=SEAT_B, recipient_public_key=B.identity.recipient_key.public_key(),
            kind=legacy.LEGACY_KIND, topic=legacy.LEGACY_TOPIC, created=SCENARIO_TIME)
        r_legacy = B.office.deliver(legacy_container)
        if r_legacy.status == postoffice.ACCEPTED:
            effects["mail_accepts"] += 1
        opened_legacy = session.open_message(r_legacy.envelope_id,
                                             recipient_private_key=B.identity.recipient_key)
        legacy_proof = legacy.authenticate_legacy(opened_legacy, packet)
        adoption = legacy.LegacyStore(B.office).adopt(legacy_proof)
        effects["legacy_adoptions"] += 1
        ev.check("legacy_adopted", adoption.status == legacy.ADOPTED
                 and adoption.entry.entry_id == legacy_proof.entry_id)
        ev.check("legacy_provenance_preserved",
                 adoption.entry.provenance.source_envelope_id == r_legacy.envelope_id
                 and adoption.entry.provenance.source_from == SEAT_A)
        successor = legacy.LegacyStore(B.office).build_successor_context(
            "queue-lease-recovery", "fg05 successor scope")
        ev.check("legacy_successor_uncertainty",
                 successor.included_entries == 1
                 and "WATCH_NEXT_STATUS:UNVERIFIED" in successor.text())
        ev.check("legacy_no_authority_gain", "AUTHORITY_GAIN:NONE" in successor.text())

        # -- HUMAN_PRIVATE branch ---------------------------------------
        letter = sailetter.HumanPrivateLetter(
            to_human=B.identity.human_id, created=SCENARIO_TIME,
            subject="fg05 private note", body=PRIVATE_MARKER)
        human_recipient = sailetter.HumanRecipient(
            human_id=B.identity.human_id,
            primary_public_key=B.identity.human_key.public_key())
        letter_container = sailetter.seal_human_private(
            letter, sender_private_key=A.identity.sender_key, sender_seat=SEAT_A,
            recipient=human_recipient, mode=sailetter.MODE_STRICT)
        private_delivery = B.letters.deliver(letter_container)
        if private_delivery.status == sailetter.DELIVERED:
            effects["private_accepts"] += 1
        ev.check("private_delivered", private_delivery.status == sailetter.DELIVERED)
        listing = B.letters.listing()
        ev.check("private_listing_metadata_only",
                 len(listing) == 1 and listing[0].letter_id == private_delivery.letter_id)
        ev.check("private_marker_absent_before_open",
                 not contains_marker(B.root, PRIVATE_MARKER))
        opened_letter = B.letters.open(private_delivery.letter_id,
                                       provider=B.identity.provider)
        ev.check("private_open_explicit", opened_letter.letter == letter)
        ev.check("private_marker_absent_after_open",
                 not contains_marker(B.root, PRIVATE_MARKER))

        admission = B.attention.admit_receiver_candidate(
            source_kind=ha.HUMAN_PRIVATE, source_ref=private_delivery.letter_id,
            allocation="DECISION_REQUEST", deferral_policy="QUEUE_AND_CONTINUE")
        re_admission = B.attention.admit_receiver_candidate(
            source_kind=ha.HUMAN_PRIVATE, source_ref=private_delivery.letter_id,
            allocation="DECISION_REQUEST", deferral_policy="QUEUE_AND_CONTINUE")
        ev.check("attention_admitted", admission.status == ha.ADMITTED
                 and re_admission.status == ha.IDEMPOTENT)
        selection = B.attention.reserve_next()
        effects["attention_reservations"] += 1
        ev.check("attention_reserved", selection.status == ha.RESERVED)
        acknowledgement = B.attention.ack_presented(selection.reservation.reservation_id)
        effects["attention_acknowledgements"] += 1
        ev.check("attention_acked", acknowledgement.status == ha.ACKED)
        ev.check("attention_ack_idempotent",
                 B.attention.ack_presented(
                     selection.reservation.reservation_id).status == ha.ALREADY_ACKED)
        ev.check("attention_consumed_once", B.attention.budget_state().consumed == 1)

        # -- NO_ADVICE / UNVERIFIED ADVICE (no delivery, no attention) --
        attention_before = B.attention.budget_state()
        letters_before = len(B.letters.listing())
        generator = _NoAdviceGenerator()
        reviewer = _NeverCalledReviewer()
        outcome = ag.generate_reviewed_ally_advice(_corpus(), generator, reviewer)
        ev.check("no_advice_outcome", outcome.status == ag.NO_ADVICE
                 and generator.calls == 1 and reviewer.calls == 0)
        missing_code = _code(aa.resolve_ally_evidence, _advice(), _MissingResolver())
        ev.check("unverified_resolution_refused", missing_code == aa.ALLY_EVIDENCE_MISSING)
        conversion_code = _code(aa.ally_to_human_private, _advice(),
                                recipient_human_id=B.identity.human_id)
        ev.check("unverified_conversion_refused",
                 conversion_code == aa.ALLY_EVIDENCE_RESOLUTION_REQUIRED)
        attention_after = B.attention.budget_state()
        ev.check("advice_paths_no_delivery", len(B.letters.listing()) == letters_before)
        ev.check("advice_paths_no_attention",
                 (attention_before.consumed, attention_before.pending_candidates,
                  attention_before.active_reservations)
                 == (attention_after.consumed, attention_after.pending_candidates,
                     attention_after.active_reservations))

        # -- TTL + TOMBSTONE --------------------------------------------
        ttl_record = _record("ttl candidate observation", subject="ttl-candidate")
        ttl_container = _seal_record(ttl_record, A.identity, B.identity, ttl="1H")
        env_ttl = envelope.envelope_id(ttl_container)
        r_ttl = B.office.deliver(ttl_container)
        if r_ttl.status == postoffice.ACCEPTED:
            effects["mail_accepts"] += 1
        sweep = B.office.sweep_expired(now=SWEEP_TIME)
        effects["tombstones"] += sweep.expired
        ev.check("ttl_sweep_expire_exactly_one", sweep.expired == 1 and sweep.retained >= 1)
        ev.check("ttl_tombstone_published",
                 B.office.expired_tombstone(env_ttl).is_file())
        ev.check("ttl_state_expired", B.office.bundle_state(env_ttl) == postoffice.EXPIRED_STATE)
        dup_ttl = B.office.deliver(ttl_container)
        effects["mail_duplicates"] += 1
        ev.check("ttl_redelivery_duplicate",
                 dup_ttl.status == postoffice.DUPLICATE
                 and dup_ttl.received_at == r_ttl.received_at)
        ev.check("ttl_no_resurrection",
                 B.office.bundle_state(env_ttl) == postoffice.EXPIRED_STATE)

        # -- DURABLE FAULT INJECTION ------------------------------------
        fault_write_record = _record("fault write boundary", subject="fault-write")
        fault_write_container = _seal_record(fault_write_record, A.identity, B.identity)
        env_fault_write = envelope.envelope_id(fault_write_container)
        with fail_once(postoffice, "_publish_dir"):
            write_code = _code(B.office.deliver, fault_write_container)
        effects["injected_failures"] += 1
        ev.check("fault_bundle_write_named", write_code == INJECTED_FAILURE)
        ev.check("fault_bundle_write_incomplete",
                 not B.office.has_index_row(env_fault_write)
                 and not B.office.inbox_bundle(env_fault_write).is_dir())
        retried = B.office.deliver(fault_write_container)
        if retried.status == postoffice.ACCEPTED:
            effects["mail_accepts"] += 1
        ev.check("fault_bundle_write_retry_safe", retried.status == postoffice.ACCEPTED)

        fault_commit_record = _record("fault commit boundary", subject="fault-commit")
        fault_commit_container = _seal_record(fault_commit_record, A.identity, B.identity)
        env_fault_commit = envelope.envelope_id(fault_commit_container)
        with fail_once(postoffice.PostOffice, "ensure_index_row"):
            commit_code = _code(B.office.deliver, fault_commit_container)
        effects["injected_failures"] += 1
        ev.check("fault_commit_named", commit_code == INJECTED_FAILURE)
        ev.check("fault_commit_incomplete_detectable",
                 B.office.inbox_bundle(env_fault_commit).is_dir()
                 and not B.office.has_index_row(env_fault_commit))
        recovery_commit = B.office.recover()
        ev.check("fault_commit_recovered",
                 B.office.has_index_row(env_fault_commit)
                 and recovery_commit.rows_appended >= 1)

        # Simulate the read-transition crash window by duplicating the read
        # bundle into inbox/ (the inbox removal never persisted). No shutil: the
        # LAB isolation contract forbids it.
        read_bundle = B.office.read_bundle(env_main)
        inbox_copy = B.office.inbox_bundle(env_main)
        inbox_copy.mkdir(parents=True)
        for name in (postoffice.CONTAINER_NAME, postoffice.RECEIPT_NAME):
            (inbox_copy / name).write_bytes((read_bundle / name).read_bytes())
        effects["injected_failures"] += 1
        ev.check("fault_read_transition_both",
                 B.office.bundle_state(env_main) == postoffice.BOTH)
        B.office.recover()
        ev.check("fault_read_transition_reconciled",
                 B.office.bundle_state(env_main) == postoffice.READ_STATE
                 and not inbox_copy.is_dir())

        injection_candidate = B.attention.admit_receiver_candidate(
            source_kind=ha.EXTERNAL_REFERENCE, source_ref="fg05-injection-1",
            allocation="ROUTINE_AUDIT", deferral_policy="QUEUE_AND_CONTINUE")
        injection_selection = B.attention.reserve_next()
        effects["attention_reservations"] += 1
        ev.check("fault_attention_reserved",
                 injection_candidate.status == ha.ADMITTED
                 and injection_selection.status == ha.RESERVED)
        with fail_once(ha, "publish_immutable"):
            ack_code = _code(B.attention.ack_presented,
                             injection_selection.reservation.reservation_id)
        effects["injected_failures"] += 1
        ev.check("fault_ack_named", ack_code == INJECTED_FAILURE)
        ev.check("fault_ack_lease_retained",
                 B.attention.budget_state().active_reservations == 1)
        injection_ack = B.attention.ack_presented(injection_selection.reservation.reservation_id)
        effects["attention_acknowledgements"] += 1
        ev.check("fault_ack_retry_acks", injection_ack.status == ha.ACKED)

        entry_dir = adoption.path
        (entry_dir / "packet.leg1").unlink()
        (entry_dir / "provenance.json").unlink()
        effects["injected_failures"] += 1
        pending_recovery = legacy.LegacyStore(B.office).recover()
        ev.check("fault_legacy_incomplete_detectable",
                 bool(pending_recovery)
                 and pending_recovery[0].status
                 == legacy.RECOVERY_REQUIRES_AUTHENTICATED_RETRY)
        repaired = legacy.LegacyStore(B.office).recover(legacy_proof)
        effects["legacy_recoveries"] += 1
        ev.check("fault_legacy_repaired",
                 bool(repaired) and repaired[0].status == legacy.RECOVERY_REPAIRED
                 and legacy.LegacyStore(B.office).all()[0].entry_id
                 == legacy_proof.entry_id)

        digest_ttl = env_ttl.split(":", 1)[1]
        restored_inbox = B.office.mail_root / postoffice.INBOX / SEAT_B / digest_ttl
        restored_inbox.mkdir(parents=True)
        (restored_inbox / postoffice.CONTAINER_NAME).write_bytes(ttl_container.encode("utf-8"))
        receipt = json.dumps(
            {"schema": 1, "envelope_id": env_ttl, "received_at": r_ttl.received_at},
            sort_keys=True, separators=(",", ":")) + "\n"
        (restored_inbox / postoffice.RECEIPT_NAME).write_bytes(receipt.encode("utf-8"))
        effects["injected_failures"] += 1
        ev.check("fault_tombstone_crash_window",
                 B.office.bundle_state(env_ttl)
                 == postoffice.EXPIRY_RECONCILIATION_REQUIRED)
        B.office.recover()
        ev.check("fault_tombstone_finished",
                 B.office.bundle_state(env_ttl) == postoffice.EXPIRED_STATE
                 and not restored_inbox.is_dir())

        # -- durable snapshot before restart ----------------------------
        pre_index = B.office.read_index()
        pre_index_ids = [row["envelope_id"] for row in pre_index]
        pre_budget = B.attention.budget_state()
        pre_letters = len(B.letters.listing())
        pre_received = {
            "main": r_main.received_at, "ttl": r_ttl.received_at,
        }
        pre_identity = (A.identity.sender_kid, B.identity.sender_kid,
                        B.identity.human_id, legacy_proof.entry_id)
        expected_states = {
            "main": postoffice.READ_STATE, "scan": postoffice.UNREAD,
            "ttl": postoffice.EXPIRED_STATE, "fault_write": postoffice.UNREAD,
            "fault_commit": postoffice.UNREAD,
        }
        envelope_by_name = {"main": env_main, "scan": env_scan, "ttl": env_ttl,
                            "fault_write": env_fault_write, "fault_commit": env_fault_commit}

        # -- RESTART: release objects and reconstruct from durable roots -
        A.disconnect()
        B.disconnect()
        ev.check("restart_objects_released", A.office is None and B.office is None
                 and A.letters is None and B.letters is None
                 and A.attention is None and B.attention is None)
        A = _participant("alice", SEAT_A, base / "participant-a")
        B = _participant("bob", SEAT_B, base / "participant-b")
        A.connect([B])
        B.connect([A])
        ev.check("restart_identity_deterministic",
                 (A.identity.sender_kid, B.identity.sender_kid,
                  B.identity.human_id, legacy_proof.entry_id) == pre_identity)

        post_index = B.office.read_index()
        ev.check("restart_index_survives", [row["envelope_id"] for row in post_index]
                 == pre_index_ids)
        ev.check("restart_states_survive",
                 all(B.office.bundle_state(envelope_by_name[name]) == state
                     for name, state in expected_states.items()))
        ev.check("restart_tombstone_survives", B.office.expired_tombstone(env_ttl).is_file())
        ev.check("restart_legacy_survives",
                 legacy.LegacyStore(B.office).all()[0].entry_id == legacy_proof.entry_id)
        ev.check("restart_attention_survives",
                 B.attention.budget_state().consumed == pre_budget.consumed)
        ev.check("restart_letters_survive", len(B.letters.listing()) == pre_letters)

        # -- continue through public APIs after restart -----------------
        post_session = postoffice.PostOfficeSession(B.office, scan_budget=50, open_budget=5)
        opened_scan = post_session.open_message(env_scan,
                                                recipient_private_key=B.identity.recipient_key)
        effects["explicit_opens"] += 1
        ev.check("restart_open_continues",
                 opened_scan.plaintext == scan_record.canonical_bytes())
        dup_main_after = B.office.deliver(main_container)
        effects["mail_duplicates"] += 1
        ev.check("restart_dedup_main", dup_main_after.status == postoffice.DUPLICATE
                 and dup_main_after.received_at == pre_received["main"])
        dup_ttl_after = B.office.deliver(ttl_container)
        effects["mail_duplicates"] += 1
        ev.check("restart_dedup_ttl", dup_ttl_after.status == postoffice.DUPLICATE
                 and dup_ttl_after.received_at == pre_received["ttl"])
        dup_letter_after = B.letters.deliver(letter_container)
        effects["private_duplicates"] += 1
        ev.check("restart_dedup_private", dup_letter_after.status == sailetter.DUPLICATE)
        post_scan = post_session.scan(now=SCENARIO_TIME)
        unread_ids = {item.view.envelope_id for item in post_scan.items}
        ev.check("restart_scan_skips_read_and_expired",
                 env_main not in unread_ids and env_ttl not in unread_ids
                 and env_fault_write in unread_ids and env_fault_commit in unread_ids)

        effects["durable_message_creations"] = len(B.office.read_index())
        ev.check("zero_network_model_calls", probe.get("blocked", 0) == 0
                 and generator.calls == 1 and reviewer.calls == 0)
        ev.check("privacy_marker_never_persisted",
                 not contains_marker(A.root, PRIVATE_MARKER)
                 and not contains_marker(B.root, PRIVATE_MARKER))
        ev.check("privacy_marker_absent_reported",
                 not contains_marker(base, PRIVATE_MARKER))

    expected_effects = {
        "mail_accepts": 5, "mail_duplicates": 4, "durable_message_creations": 6,
        "explicit_opens": 2, "promotions": 1, "attention_reservations": 2,
        "attention_acknowledgements": 2, "tombstones": 1, "legacy_adoptions": 1,
        "legacy_recoveries": 1, "private_accepts": 1, "private_duplicates": 1,
        "injected_failures": 6,
    }
    for name, expected in expected_effects.items():
        ev.check(f"side_effect_{name}", effects[name] == expected,
                 f"{name}={effects[name]} expected={expected}")

    result.update({
        "participants": {
            "A": {"seat": SEAT_A, "sender_kid": A.identity.sender_kid,
                  "recipient_kid": A.identity.recipient_kid,
                  "human_id": A.identity.human_id},
            "B": {"seat": SEAT_B, "sender_kid": B.identity.sender_kid,
                  "recipient_kid": B.identity.recipient_kid,
                  "human_id": B.identity.human_id},
        },
        "envelopes": {
            "main": env_main, "scan": env_scan, "ttl": env_ttl,
            "fault_write": env_fault_write, "fault_commit": env_fault_commit,
            "legacy": r_legacy.envelope_id, "private_letter": private_delivery.letter_id,
        },
        "happy_path": {
            "index_rows": len(pre_index), "open": "EXPLICIT",
            "claim_preserved": True, "evidence_preserved": True,
            "uncertainty_preserved": True, "promotion": "SEPARATE_ACTION",
        },
        "restart_proof": {
            "object_identity_released": True, "index_rows": len(post_index),
            "states": expected_states, "continued_open": "PASS",
        },
        "dedup_proof": {"mail_duplicates": effects["mail_duplicates"],
                        "private_duplicates": effects["private_duplicates"]},
        "ttl_tombstone_proof": {
            "expired": True, "tombstone": True, "redelivery": "DUPLICATE",
            "resurrection": False,
        },
        "legacy_proof": {
            "adopted": True, "entry_id": legacy_proof.entry_id,
            "provenance_source_envelope": r_legacy.envelope_id,
            "recovery_repaired": True,
        },
        "human_private_proof": {
            "letter_id": private_delivery.letter_id,
            "mode": opened_letter.verified.parsed.mode,
            "opened": True, "plaintext_persisted": False,
        },
        "attention_accounting": {
            "reservations": effects["attention_reservations"],
            "acknowledgements": effects["attention_acknowledgements"],
            "consumed": B.attention.budget_state().consumed,
        },
        "no_advice_proof": {"status": outcome.status,
                            "generator_calls": generator.calls,
                            "reviewer_calls": reviewer.calls,
                            "delivery": False, "attention_consumed": False,
                            "unverified_conversion": conversion_code},
        "failure_injection": {
            "count": effects["injected_failures"],
            "boundaries": ["bundle_write", "index_commit", "read_transition",
                           "attention_ack", "legacy_write", "tombstone_expiry"],
        },
        "side_effects": effects,
        "zero_network_model": {"network_attempts": probe.get("blocked", 0),
                               "provider_calls": 0},
        "artifacts": {"root": str(base), "retained": True},
    })
    result["checks"] = ev.checks
    result["status"] = "PASS" if ev.ok else "FAIL"
    if PRIVATE_MARKER in json.dumps(result):
        result["status"] = "FAIL"
        result["checks"].append({"id": "result_privacy", "ok": False,
                                 "detail": "private marker appeared in the result"})
    return result


# --------------------------------------------------------------------------
# summary
# --------------------------------------------------------------------------


def render_summary(result: dict) -> str:
    """Bounded state summary; never private payloads."""
    participants = (f"{result['participants']['A']['seat']}, "
                    f"{result['participants']['B']['seat']}")
    network = (f"{result['zero_network_model']['network_attempts']} attempts, "
               f"{result['zero_network_model']['provider_calls']} provider calls")
    checks = (f"{sum(1 for c in result['checks'] if c['ok'])}/"
              f"{len(result['checks'])} passed")
    lines = [
        "FG-05 LOCAL SCENARIO",
        f"STATUS:            {result['status']}",
        f"SCHEMA:            {result['schema']} v{result['version']}",
        f"PARTICIPANTS:      {participants}",
        "SIDE EFFECTS:      " + ", ".join(
            f"{name}={value}" for name, value in sorted(result["side_effects"].items())),
        f"FAILURE INJECTION: {result['failure_injection']['count']} boundaries",
        f"NETWORK/MODEL:     {network}",
        f"CHECKS:            {checks}",
    ]
    failures = [c for c in result["checks"] if not c["ok"]]
    for entry in failures:
        lines.append(f"  FAILED {entry['id']}: {entry['detail']}")
    return "\n".join(lines)
