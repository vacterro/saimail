"""FUTURE GATE Wave 5: a mailbox safe to break, and the proof that it was.

The wave exists because destructive tests aimed at whatever mailbox was closest
is a real failure mode, not a hypothetical one: the moment a crash-window proof
or a corrupt-container probe is run against a fixture that is actually somebody's
mail, a passing suite is a suite that demonstrated it can delete real mail.

So the synthetic identity is permanent and pre-committed, and these tests pin
the acceptance cases:

* the destructive suite touches no real mailbox
* canary classification survives export/import
* production list/search excludes test data by default
* reset refuses a non-canary target
* at least one real crash/recovery proof passes

plus the scenarios the wave lists -- corrupt SENV, wrong key, rotation,
revocation, duplicate delivery, a crash window, ledger/index loss, archive
restore, Future Letter export/import and recovery bundles -- and the invariants
under them: a stamp that does not verify never authorises a destroy, a canary
whose key survived a test is a canary the next test inherits, and a failure
report lives outside the mailbox it describes.

Two of these are real rather than simulated on purpose. The crash proof spawns
an actual process and kills it mid-transaction with ``os._exit``, so nothing is
unwound, flushed or closed by an interpreter on the way out; and the corruption
tests overwrite bytes on disk rather than patching a reader.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from pathlib import Path

from sailang import SailangError
from saimail import canary, catchup, cold_archive as cold, future_letter
from saimail import keyvault, ledger, outbox, postoffice, trust, workspace

ROOT = Path(__file__).resolve().parent.parent
T0 = "2026-10-04T09:00:00Z"
T1 = "2026-10-04T10:00:00Z"
T2 = "2026-10-04T11:00:00Z"
T3 = "2026-10-04T12:00:00Z"
SEAT = "canary-probe"
PEER_SEAT = "canary-mirror"

CRASH_CHILD = (
    "import os, sys\n"
    "sys.path.insert(0, %r)\n"
    "from saimail import ledger, outbox, workspace\n"
    "A = workspace.load_workspace(sys.argv[1])\n"
    "real = ledger.append\n"
    "def crashing(target, event, **kw):\n"
    "    result = real(target, event, **kw)\n"
    "    if event == ledger.SEALED:\n"
    "        os._exit(9)          # no unwinding, no flush, no close\n"
    "    return result\n"
    "ledger.append = crashing\n"
    "outbox.submit_send(A, %r, key='crashy', claim='a claim that must survive',\n"
    "                   clock=lambda: %r)\n"
    "sys.exit(0)\n"
)


def _clock(*stamps):
    sequence = list(stamps)

    def now():
        return sequence.pop(0) if len(sequence) > 1 else sequence[0]

    return now


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _canary(root, seat=SEAT, *, purpose="destructive proof lane"):
    canary.seed(root, seat=seat, purpose=purpose, clock=_clock(T0))
    return workspace.load_workspace(root)


def _pair(tmp_path):
    """Two canaries wired to each other. Nothing here is a real mailbox."""
    A = _canary(tmp_path / "probe", SEAT)
    B = _canary(tmp_path / "mirror", PEER_SEAT)
    workspace.add_recipient(A, PEER_SEAT, workspace.identity_card(B), B.root)
    workspace.add_recipient(B, SEAT, workspace.identity_card(A), A.root)
    trust.pin(A, PEER_SEAT, source="canary fixture", clock=_clock(T0))
    return A, B


def _send(A, key="k1", claim="one canary fact", *, clock=None, to=PEER_SEAT):
    return outbox.submit_send(A, to, key=key, claim=claim,
                              clock=clock or _clock(T1))


def _delivered(tmp_path, *, key="k1", claim="one canary fact"):
    A, B = _pair(tmp_path)
    result = _send(A, key=key, claim=claim)
    assert result["status"] == outbox.DELIVERED, result["detail"]
    return A, B, result["intent"]["envelope_id"]


def _tree(root: Path) -> dict:
    """Every file under `root` with its bytes. The 'nothing was touched' proof."""
    seen = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            seen[str(path.relative_to(root))] = path.read_bytes()
    return seen


def _container(recipient, envelope_id: str) -> Path:
    """Where a delivered body actually lands: the RECIPIENT's own seat.

    The inbox path is keyed by who is allowed to read it, not by who sent it,
    so a probe that looks under the sender's seat finds nothing and mistakes a
    delivered message for a missing one.
    """
    root = Path(recipient.root) if not isinstance(recipient, (str, Path)) else recipient
    seat = recipient.seat if hasattr(recipient, "seat") else SEAT
    return (root / postoffice.MAIL_DIR / postoffice.INBOX / seat
            / postoffice._bundle_name(envelope_id) / postoffice.CONTAINER_NAME)


def _cli(*argv, accept=(0,)):
    """Run the real entry point in a real process and parse what it printed.

    `accept` lets a caller say which exit codes are a correct ANSWER rather than a
    crash: a refusal is the module working, so it exits non-zero on purpose and
    still has to print a result an operator can read.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "saimail_local", *argv, "--json"],
        cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode in accept, (
        f"exit {proc.returncode} (expected one of {accept}): {proc.stderr}")
    return json.loads(proc.stdout)


def _production_with_canary_peer(tmp_path):
    """A production mailbox that has a canary registered as a real recipient."""
    A = _canary(tmp_path / "probe")
    workspace.init_workspace(tmp_path / "prod", seat="alpha")
    workspace.add_recipient(workspace.load_workspace(tmp_path / "prod"), SEAT,
                            workspace.identity_card(A), A.root)
    workspace.add_recipient(A, "alpha",
                            workspace.identity_card(
                                workspace.load_workspace(tmp_path / "prod")),
                            tmp_path / "prod")
    trust.pin(workspace.load_workspace(tmp_path / "prod"), SEAT,
              source="canary fixture", clock=_clock(T0))
    return A, workspace.load_workspace(tmp_path / "prod")


# --------------------------------------------------------------------------
# the mailbox itself: unmistakable, and hard to mistake for permission
# --------------------------------------------------------------------------

def test_a_canary_is_unmistakable_before_anything_parses_it(tmp_path):
    """The seat prefix and the stamp both say TEST DATA, in a directory listing."""
    A = _canary(tmp_path / "probe")
    names = sorted(p.name for p in (tmp_path / "probe").iterdir())
    assert canary.STAMP_NAME in names
    assert canary.classify_seat(A.seat) == canary.CLASSIFICATION_CANARY
    # The stamp names the identity it claims, so it cannot be copied onto another.
    stamp = canary.read_stamp(tmp_path / "probe")
    assert stamp["seat"] == A.seat
    assert stamp["sender_kid"] == A.sender_kid
    assert stamp["recipient_kid"] == A.recipient_kid
    assert stamp["classification"] == canary.CLASSIFICATION_CANARY
    # The SEAT is the classification, not the folder name: a canary parked in a
    # neutrally named directory is still a canary, and the stamp still proves it.
    assert A.seat.startswith(canary.SEAT_PREFIX)
    assert not A.root.name.startswith(canary.SEAT_PREFIX)


def test_a_production_mailbox_is_not_canary_and_says_why(tmp_path):
    """Unclassified is not a silent state: status names what is missing."""
    workspace.init_workspace(tmp_path / "prod", seat="alpha")
    P = workspace.load_workspace(tmp_path / "prod")
    status = canary.status(P)
    assert status["classification"] == canary.CLASSIFICATION_PRODUCTION
    assert status["destructive_allowed"] is False
    assert "no readable canary stamp" in status["stamp_problem"]


def test_seed_refuses_a_seat_outside_the_reserved_namespace(tmp_path):
    """A canary that can wear a production name will eventually be mistaken."""
    assert _code(canary.seed, tmp_path / "sneaky", seat="alpha") == (
        canary.CANARY_SEAT_REQUIRED)
    assert _code(canary.seed, tmp_path / "empty", seat=canary.SEAT_PREFIX) == (
        canary.CANARY_SEAT_REQUIRED)
    assert _code(canary.seed, tmp_path / "blank", seat="canary-probe",
                 purpose="   ") == canary.BAD_INPUT
    assert not (tmp_path / "sneaky").exists()


def test_reset_refuses_a_production_target_and_touches_nothing(tmp_path):
    """The headline acceptance case, proved on real bytes rather than a mock."""
    workspace.init_workspace(tmp_path / "prod", seat="alpha")
    before = _tree(tmp_path / "prod")
    assert before, "the target must have something to lose"

    assert _code(canary.reset, tmp_path / "prod") == canary.CANARY_TARGET_REFUSED
    assert _tree(tmp_path / "prod") == before, "a refused reset changed bytes"
    assert workspace.load_workspace(tmp_path / "prod").seat == "alpha"

    # A directory that is not a workspace at all is refused the same way.
    empty = tmp_path / "not-a-mailbox"
    empty.mkdir()
    (empty / "notes.txt").write_text("operator notes", encoding="utf-8")
    assert _code(canary.reset, empty) == canary.CANARY_TARGET_REFUSED
    assert (empty / "notes.txt").is_file()


def test_reset_refuses_a_stamp_that_does_not_describe_this_identity(tmp_path):
    """A stamp is evidence. Unverified evidence is not permission to destroy."""
    root = tmp_path / "probe"
    _canary(root)
    stamp_file = root / canary.STAMP_NAME

    def rest():
        return {name: blob for name, blob in _tree(root).items()
                if name != canary.STAMP_NAME}

    def rewrite(**changes):
        payload = canary.read_stamp(root)
        payload.update(changes)
        stamp_file.write_text(json.dumps(payload), encoding="utf-8")

    original = rest()
    cases = {
        "another seat's name": {"seat": "canary-somebody-else"},
        "another identity's key": {"sender_kid": "sha256:" + "0" * 64},
        "a field it should not have": {"note": "trust me"},
        "a version it cannot read": {"version": 99},
        "not a canary after all": {"classification": "PRODUCTION"},
        "a seat outside the namespace": {"seat": "alpha"},
    }
    for label, changes in cases.items():
        rewrite(**changes)
        A = workspace.load_workspace(root)
        assert canary.classify(A) == canary.CLASSIFICATION_PRODUCTION, label
        assert _code(canary.reset, root) == canary.CANARY_TARGET_REFUSED, label
        assert rest() == original, label

    stamp_file.write_bytes(b"not json at all")
    assert canary.is_canary(workspace.load_workspace(root)) is False
    assert _code(canary.reset, root) == canary.CANARY_TARGET_REFUSED

    stamp_file.unlink()
    assert canary.is_canary(workspace.load_workspace(root)) is False
    assert _code(canary.reset, root) == canary.CANARY_TARGET_REFUSED
    assert rest() == original, "a refused reset changed anything but the stamp"


def test_reset_preserves_failure_reports_outside_the_wipe(tmp_path):
    """A report that lives inside the target is deleted by the reset it documents."""
    root = tmp_path / "probe"
    A = _canary(root)
    canary.record_failure(A, scenario="corrupt-senv", outcome="PASS",
                          detail="the container refused to parse",
                          evidence={"bytes_flipped": 1})
    assert len(canary.read_reports(A)) == 1

    result = canary.reset(root, clock=_clock(T3))
    history = Path(result["reports_preserved_to"])
    assert history == canary.history_dir(root)
    assert history.parent == root.parent, "history must sit outside the wipe"
    assert sorted(p.name for p in history.iterdir()) == ["corrupt-senv.json"]

    reseeded = workspace.load_workspace(root)
    assert canary.read_reports(reseeded) == [], "the fresh mailbox starts clean"
    preserved = json.loads((history / "corrupt-senv.json").read_text(encoding="utf-8"))
    assert preserved["classification"] == canary.CLASSIFICATION_CANARY
    assert preserved["evidence"] == {"bytes_flipped": 1}


def test_reset_rotates_the_identity_so_the_next_test_cannot_inherit_it(tmp_path):
    """Deterministic means the procedure is repeatable, not that keys survive."""
    root = tmp_path / "probe"
    A = _canary(root)
    assert _code(canary.reset, root, clock=_clock(T3)) == "NO_ERROR"
    B = workspace.load_workspace(root)
    assert B.seat == A.seat, "the seat is stable so the address is stable"
    assert B.sender_kid != A.sender_kid, "but the identity is not"
    assert B.recipient_kid != A.recipient_kid
    assert canary.is_canary(B), "and the fresh one is canary all the same"
    assert canary.status(B)["destructive_allowed"] is True


def test_reports_are_never_written_into_the_mailbox(tmp_path):
    """The failure lane must not be able to fake a message."""
    A, B, _ = _delivered(tmp_path, key="reported")
    canary.record_failure(B, scenario="duplicate-delivery", outcome="PASS")
    mail = B.root / postoffice.MAIL_DIR
    assert canary.reports_dir(B).is_dir()
    assert canary.reports_dir(B).name not in {p.name for p in mail.iterdir()}
    index = mail / postoffice.INDEX_NAME
    assert canary.TAG not in index.read_text(encoding="utf-8"), \
        "a report must not appear in the index as if it were mail"
    # And a report is never counted as a message.
    assert len(workspace.list_inbox(B)["items"]) == 1


def test_a_report_that_cannot_say_what_happened_is_refused(tmp_path):
    """Evidence with no outcome is indistinguishable from noise."""
    A = _canary(tmp_path / "probe")
    assert _code(canary.record_failure, A, scenario="s", outcome="") == (
        canary.CANARY_REPORT_INVALID)
    assert _code(canary.record_failure, A, scenario="bad name", outcome="PASS") == (
        canary.BAD_INPUT)
    assert _code(canary.record_failure, A, scenario="s", outcome="PASS",
                 evidence={"bad": object()}) == canary.CANARY_REPORT_INVALID
    assert canary.read_reports(A) == []
    assert canary.reports(A)["count"] == 0


# --------------------------------------------------------------------------
# the destructive proof lane -- the scenarios the wave lists
# --------------------------------------------------------------------------

def test_a_corrupt_senv_is_refused_rather_than_silently_read(tmp_path):
    """Real bytes are flipped on disk; the mailbox must not serve them."""
    A, B, envelope_id = _delivered(tmp_path, key="corruptible")
    container = _container(B, envelope_id)
    assert container.is_file()
    container.write_bytes(b"\x00" * 4096)

    # The row survives: a corrupt body must not delete the envelope.
    assert B.office().read_index_row(envelope_id) is not None
    # Opening refuses -- damaged bytes are never served as a claim.
    assert _code(workspace.open_message, B, envelope_id) != "NO_ERROR"
    # And the message is still LISTED, so a broken message reads as broken rather
    # than silently vanishing, which is the failure this whole lane prevents.
    listed = workspace.list_inbox(B, include_test_data=True)
    assert [item["envelope_id"] for item in listed["items"]] == [envelope_id]


def test_a_message_sealed_to_another_key_cannot_be_opened(tmp_path):
    """Wrong key, real decryption, real refusal."""
    A, B, envelope_id = _delivered(tmp_path, key="wrong-key")
    _canary(tmp_path / "impostor", "canary-impostor")
    impostor = workspace.load_workspace(tmp_path / "impostor")
    assert _code(workspace.open_message, impostor, envelope_id) != "NO_ERROR"

    # The genuine holder still reads it: the refusal was about identity, not bytes.
    opened = workspace.open_message(B, envelope_id)
    assert opened["record"]["claim"] == "one canary fact"


def test_rotation_and_revocation_both_stop_delivery_to_the_old_identity(tmp_path):
    """The trust lane, exercised destructively rather than mocked."""
    A, B = _pair(tmp_path)
    # The rotated mailbox keeps the SAME seat: a rotation replaces the keys under
    # an address, it does not move the identity to a new one. Getting this wrong
    # is refused by the module, which is the correct refusal -- an alias is the
    # only thing a rotation is allowed to keep.
    B2 = _canary(tmp_path / "mirror-rotated", PEER_SEAT)
    assert B2.sender_kid != B.sender_kid

    receipt = trust.build_rotation_receipt(B, B2, alias=PEER_SEAT, clock=_clock(T0))
    rotated = trust.apply_rotation(A, PEER_SEAT, receipt, clock=_clock(T1))
    assert rotated["trust"]["state"] == trust.TRUSTED
    assert rotated["trust"]["rotations"] == 1, "the lineage is kept, not reset"
    # The pin moved, but A still holds the OLD recipient card, so the derived
    # verdict is IDENTITY_CHANGED: a rotation is not a free pass back into trust,
    # it is a claim that has not been met yet. The state is derived, never stored.
    assert trust.decide(A, PEER_SEAT)["state"] == trust.IDENTITY_CHANGED

    trust.revoke(A, PEER_SEAT, reason="canary: key hit the public dump",
                 clock=_clock(T2))
    assert trust.decide(A, PEER_SEAT)["state"] == trust.REVOKED
    # Revocation survives a restart: it is durable, not an in-memory verdict.
    assert trust.decide(workspace.load_workspace(tmp_path / "probe"),
                        PEER_SEAT)["state"] == trust.REVOKED

    # A forged receipt cannot walk any of this back.
    forged = trust.build_rotation_receipt(B2, B, alias=PEER_SEAT, clock=_clock(T3))
    assert _code(trust.apply_rotation, workspace.load_workspace(tmp_path / "probe"),
                 PEER_SEAT, forged) != "NO_ERROR"
    assert trust.decide(workspace.load_workspace(tmp_path / "probe"),
                        PEER_SEAT)["state"] == trust.REVOKED


def test_a_duplicate_delivery_is_idempotent_not_a_second_message(tmp_path):
    """Replaying the same request must not double the recipient's mail."""
    A, B, envelope_id = _delivered(tmp_path, key="dupe", claim="one canary fact")
    before = len(workspace.list_inbox(B)["items"])

    again = _send(A, key="dupe", claim="one canary fact")
    assert again["intent"]["envelope_id"] == envelope_id, "a replay re-sealed the body"
    assert len(workspace.list_inbox(B)["items"]) == before, "the recipient gained a copy"
    assert workspace.list_inbox(B)["items"][0]["envelope_id"] == envelope_id

    # The same key naming a DIFFERENT request is a conflict, not a silent
    # overwrite -- otherwise a retry could quietly change what was sent.
    assert _code(_send, A, key="dupe", claim="a different claim") == (
        outbox.IDEMPOTENCY_KEY_CONFLICT)


def test_a_real_process_death_mid_transaction_leaves_work_that_can_be_finished(tmp_path):
    """A genuine crash: a real child process, killed with os._exit mid-send.

    Nothing unwinds, nothing is flushed on the way out and no interpreter
    shutdown hook runs -- which is the point. The parent then has to prove the
    crash left *repairable* state rather than a lost message.
    """
    A, B = _pair(tmp_path)
    child = CRASH_CHILD % (str(ROOT), PEER_SEAT, T1)
    proc = subprocess.run([sys.executable, "-c", child, str(A.root)],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode == 9, f"the child did not die mid-transaction: {proc.stderr}"

    # The recipient never saw it: the crash window is real.
    assert workspace.list_inbox(B)["items"] == []

    # The sender's record survived the death and is still readable.
    events, state = ledger.read_events(A)
    assert state == ledger.STATE_OK, f"the record is {state}, not readable"
    assert events, "a readable ledger that returned nothing was not read at all"
    replayed = ledger.reconstruct(A, clock=_clock(T2))
    assert any(m.get("state") in (ledger.SEALED, ledger.OUTBOX_COMMITTED)
               for m in replayed["messages"]), replayed["messages"]

    # And the crash left owed work, which the catch-up lane owns rather than loses.
    catchup.plan(A, clock=_clock(T3))
    entries = catchup.queue(A, clock=_clock(T3))["queue"]["entries"]
    assert entries, "a crash that leaves no owed work is a message that was lost"
    canary.record_failure(A, scenario="crash-window", outcome="REPAIRABLE",
                          detail="child killed after SEALED with os._exit(9)",
                          evidence={"exit_code": proc.returncode,
                                    "owed_kinds": [e["kind"] for e in entries]})


def test_a_lost_index_is_rebuilt_from_canonical_state(tmp_path):
    """Delete the projection; the mailbox must come back from what is on disk."""
    A, B, envelope_id = _delivered(tmp_path, key="indexed")
    index = B.root / postoffice.MAIL_DIR / postoffice.INDEX_NAME
    assert index.is_file()
    index.unlink()

    assert workspace.list_inbox(B)["items"] == [], "the projection really is gone"

    B.office().recover()
    after = workspace.list_inbox(B)
    assert [item["envelope_id"] for item in after["items"]] == [envelope_id]


def test_an_archive_prune_and_restore_returns_the_exact_message(tmp_path):
    """The cold lane under a destructive flag, not a mock opener."""
    A, B, envelope_id = _delivered(tmp_path, key="archivable")
    # Archived from the mailbox that HOLDS the body. The sender kept no hot copy
    # of a message it handed over, so archiving from there archives nothing --
    # which the module says out loud rather than reporting a success.
    # The default retention prunes nothing, so the prune step is asked for under a
    # stated policy rather than assumed: an unbounded mailbox is a smaller problem
    # than a deleted letter, and that default is not overridden here by accident.
    done = cold.archive(B, envelope_id, clock=_clock(T2),
                        retention=cold.retention_policy(max_count=0), prune=True)
    assert done["status"] == cold.PRUNED, "prune ran and reported its own outcome"
    assert done["pruned"]["removed"] is True
    assert done["verified"]["hash"] is True, "the cold copy was read back, not assumed"
    assert cold.verify_record(B, envelope_id, clock=_clock(T3))["status"] == (
        cold.VERIFIED)

    restored = cold.restore(B, envelope_id, clock=_clock(T3))
    assert restored["status"] == cold.RESTORED
    assert workspace.open_message(B, envelope_id)["record"]["claim"] == (
        "one canary fact")

    # Restore is convergent, not additive.
    cold.restore(A, envelope_id, clock=_clock(T3))
    assert len(workspace.list_inbox(B)["items"]) == 1


def test_a_recovery_bundle_rebuilds_a_workspace_whose_identity_was_lost(tmp_path):
    """Offline recovery, driven entirely inside the canary."""
    root = tmp_path / "probe"
    A = _canary(root)
    password = "canary-master-key-1"
    keyvault.protect(workspace.load_workspace(root), password)
    locked = workspace.load_workspace(root, password=password)

    backup = keyvault.recovery_backup(locked, tmp_path / "canary-backup.json")
    raw = (tmp_path / "canary-backup.json").read_bytes()
    assert password.encode() not in raw, "the backup must not carry the password"
    assert backup["recovery_key"].encode() not in raw

    restored_root = tmp_path / "restored"
    keyvault.restore(backup["path"], restored_root, backup["recovery_key"],
                     "a-new-password-2")
    restored = workspace.load_workspace(restored_root, password="a-new-password-2")
    assert restored.sender_kid == A.sender_kid
    assert restored.recipient_kid == A.recipient_kid
    assert _code(keyvault.restore, backup["path"], tmp_path / "other",
                 "wrong recovery key", "a-new-password-2") != "NO_ERROR"


def test_canary_classification_survives_export_and_import(tmp_path):
    """The stamp has to travel, or a bundle arrives unlabelled somewhere else."""
    root = tmp_path / "probe"
    A = _canary(root)
    workspace.init_workspace(tmp_path / "stranger", seat="stranger")
    stranger = workspace.load_workspace(tmp_path / "stranger")
    assert canary.is_canary(stranger) is False

    created = future_letter.create(A, title="canary note", body="test data only",
                                   clock=_clock(T0))
    assert canary.TAG in created["letter"]["tags"], "authoring in a canary stamps it"

    bundle = tmp_path / "capsule.zip"
    future_letter.export_bundle(A, created["letter"]["letter_id"], out=bundle,
                                recovery=True, clock=_clock(T1))
    recovered = future_letter.read_bundle(bundle)
    assert canary.container_is_canary(recovered["container"]), \
        "the sealed container must carry the classification, not a sidecar file"

    imported = future_letter.import_bundle(stranger, bundle, clock=_clock(T2))
    assert imported["status"] == postoffice.ACCEPTED
    assert canary.TAG in imported["letter"]["tags"]
    listed = future_letter.list_letters(
        workspace.load_workspace(tmp_path / "stranger"), clock=_clock(T3))
    assert [canary.TAG in item["tags"] for item in listed["items"]] == [True]


def test_a_production_letter_is_not_labelled_by_proximity(tmp_path):
    """Standing next to a canary does not make everything test data."""
    root = tmp_path / "probe"
    _canary(root)
    workspace.init_workspace(tmp_path / "prod", seat="alpha")
    prod = workspace.load_workspace(tmp_path / "prod")
    letter = future_letter.create(prod, title="a real finding", body="not test data",
                                  clock=_clock(T0))
    assert canary.TAG not in letter["letter"]["tags"]


# --------------------------------------------------------------------------
# exclusion: production views must not mix test data in
# --------------------------------------------------------------------------

def test_a_production_inbox_hides_canary_traffic_and_reports_the_count(tmp_path):
    """The count of what was hidden is reported -- silence would be a lie."""
    A, P = _production_with_canary_peer(tmp_path)
    assert _send(A, key="probe-traffic", to="alpha")["status"] == outbox.DELIVERED

    hidden = workspace.list_inbox(P)
    assert hidden["items"] == []
    assert hidden["excluded_test_data"] == 1
    assert "1 test-data message(s) hidden" in hidden["detail"]

    shown = workspace.list_inbox(P, include_test_data=True)
    assert [item["from"] for item in shown["items"]] == [SEAT]
    assert shown["excluded_test_data"] == 0


def test_the_bounded_query_hides_canary_traffic_too(tmp_path):
    """Both listing surfaces, because an operator has two ways to look."""
    A, P = _production_with_canary_peer(tmp_path)
    _send(A, key="probe-traffic", to="alpha")

    hidden = workspace.query_inbox(P)
    assert hidden["items"] == []
    assert hidden["excluded_test_data"] == 1
    assert "1 test-data match(es) hidden" in hidden["detail"]
    assert len(workspace.query_inbox(P, include_test_data=True)["items"]) == 1


def test_a_canary_mailbox_still_sees_its_own_traffic(tmp_path):
    """The test lane's whole output is its inbox; hiding it would blind it."""
    A, B = _pair(tmp_path)
    assert _send(A, key="canary-mail", to=PEER_SEAT)["status"] == outbox.DELIVERED
    box = workspace.list_inbox(B)
    assert [item["from"] for item in box["items"]] == [SEAT], \
        "the canary's own mailbox must not hide its own mail"


def test_a_production_catchup_queue_hides_canary_debt(tmp_path):
    """Metrics carry the same rule as the inbox: test debt is not real debt.

    The debt here is an unsettled trust verdict for a canary alias, which is
    stable, needs no crash to create, and is exactly the shape of work an
    operator does not want counted against their own queue.
    """
    A = _canary(tmp_path / "probe")
    workspace.init_workspace(tmp_path / "prod", seat="alpha")
    P = workspace.load_workspace(tmp_path / "prod")
    workspace.add_recipient(P, SEAT, workspace.identity_card(A), A.root)
    # Registered but deliberately NOT pinned: the verdict is unsettled, so the
    # queue owes a TRUST decision about this alias.
    assert trust.decide(P, SEAT)["state"] != trust.TRUSTED
    catchup.plan(P, clock=_clock(T2))

    hidden = catchup.queue(P, clock=_clock(T3))
    assert hidden["queue"]["entries"] == [], "production owed something about a canary"
    assert hidden["excluded_test_data"] >= 1
    assert "test-data entry" in hidden["detail"]
    assert catchup.notice(P, clock=_clock(T3))["owed"] == 0, \
        "a production-shaped notice must not count test debt"

    shown = catchup.queue(P, clock=_clock(T3), include_test_data=True)
    assert [entry["peer"] for entry in shown["queue"]["entries"]] == [SEAT], \
        "the entry is real; it is only hidden by default"

    # And the canary's own mailbox shows its own queue unprompted, because the
    # lane's whole output IS its queue.
    canary_side = catchup.queue(A, clock=_clock(T3))
    assert canary_side["excluded_test_data"] == 0


def test_the_cli_speaks_the_same_language(tmp_path):
    """`canary status` and the module agree; nothing is CLI-only behaviour."""
    A = _canary(tmp_path / "probe")
    workspace.init_workspace(tmp_path / "prod", seat="alpha")
    assert _cli("canary", "status", "--workspace", str(A.root))["classification"] == (
        canary.CLASSIFICATION_CANARY)
    assert _cli("canary", "status", "--workspace",
                str(tmp_path / "prod"))["classification"] == (
        canary.CLASSIFICATION_PRODUCTION)
    refused = _cli("canary", "reset", "--workspace", str(tmp_path / "prod"),
                   accept=(0, 1))
    # The point of the test: the CLI reports the SAME code the module raises,
    # rather than a CLI-only phrasing an operator would have to look up.
    assert refused["status"] == _code(canary.reset, tmp_path / "prod") == (
        canary.CANARY_TARGET_REFUSED)
    assert refused["ok"] is False
    assert workspace.load_workspace(tmp_path / "prod").seat == "alpha", \
        "the refused CLI call changed nothing either"


# --------------------------------------------------------------------------
# the lane never points at anything real
# --------------------------------------------------------------------------

def test_the_destructive_suite_touches_no_real_mailbox(tmp_path):
    """Every mailbox the lane creates is a canary, or is created to be spared.

    The acceptance case stated as an invariant rather than a promise: the
    destructive step is allowed to break its OWN canary, while a production
    mailbox sits right next to it and is still byte-identical afterwards.
    """
    workspace.init_workspace(tmp_path / "prod", seat="alpha")
    A, B, envelope_id = _delivered(tmp_path, key="guarded")
    production_before = _tree(tmp_path / "prod")
    canary_before = _tree(B.root)

    container = _container(B, envelope_id)
    container.write_bytes(b"\x00" * 4096)
    cold.prune(A, limit=1)
    assert canary.reset(tmp_path / "probe")

    assert _tree(B.root) != canary_before, "the canary really was broken"
    assert _tree(tmp_path / "prod") == production_before, \
        "and the production mailbox next to it was not"
    # A reloaded mailbox, not the object held across the reset: the reset rotated
    # the keys, so the pre-reset identity no longer matches the stamp on disk.
    # That is the module refusing to honour a stale handle, not a lost canary.
    reseeded = workspace.load_workspace(tmp_path / "probe")
    assert canary.is_canary(reseeded)
    assert reseeded.sender_kid != A.sender_kid
    assert not canary.is_canary(A), "a pre-reset handle must not keep its grant"
    assert not canary.is_canary(workspace.load_workspace(tmp_path / "prod"))


def test_the_destructive_lane_runs_on_this_platform(tmp_path):
    """Windows-first, but it has to actually run wherever the suite runs."""
    record = canary.record_failure(
        _canary(tmp_path / "probe"),
        scenario="platform-proof", outcome="PASS",
        detail="real filesystem corruption and a real spawned process were exercised",
        evidence={"platform": platform.system(), "release": platform.release(),
                  "python": sys.version.split()[0], "pid_self": os.getpid()})
    assert record["report"]["evidence"]["platform"] == platform.system()
    assert platform.system() in ("Windows", "Linux", "Darwin"), \
        f"unproven platform: {platform.system()}"


def test_nothing_on_this_machine_is_mistaken_for_a_canary(tmp_path):
    """The guard reads the stamp, not the path: a canary-named dir is not enough."""
    decoy = tmp_path / "canary-decoy"
    workspace.init_workspace(decoy, seat="canary-decoy")
    D = workspace.load_workspace(decoy)
    assert canary.classify_seat(D.seat) == canary.CLASSIFICATION_CANARY, \
        "the prefix alone reads as canary in a listing"
    assert canary.is_canary(D) is False, \
        "but it must not GRANT permission without a verified stamp"
    assert _code(canary.reset, decoy) == canary.CANARY_TARGET_REFUSED
    assert (decoy / workspace.MARKER_NAME).is_file()