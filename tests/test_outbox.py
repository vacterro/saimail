"""V6-05 durable outbox (T-119): one logical message per idempotency key.

A seal is randomized and the receiver deduplicates by the ENVELOPE_ID of the
exact bytes, so a retried ``send_message`` used to become a second message. The
outbox records the intent first, seals once, persists the container before any
delivery and only ever replays those bytes. These controls kill real processes
at every durable transition, race concurrent writers, and check that nothing is
lost, nothing is delivered twice and no plaintext stays at rest after sealing.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

import saimail_local
from sailang import SailangError
from saimail import credentials, custody, outbox, postoffice, workspace

ROOT = Path(__file__).resolve().parent.parent
T0 = "2026-09-24T07:00:00Z"
TOPIC = "T-119"


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _pair(tmp_path, *, register_back=True, mode=custody.CUSTODY_RAW, store=None):
    workspace.init_workspace(tmp_path / "A", seat="alpha", custody=mode, store=store)
    workspace.init_workspace(tmp_path / "B", seat="beta", custody=mode, store=store)
    A = workspace.load_workspace(tmp_path / "A", store=store)
    B = workspace.load_workspace(tmp_path / "B", store=store)
    workspace.add_recipient(A, "beta", workspace.identity_card(B), B.root)
    if register_back:
        workspace.add_recipient(B, "alpha", workspace.identity_card(A), A.root)
    return A, B


def _received(B, topic=TOPIC) -> int:
    return workspace.query_inbox(workspace.load_workspace_headers(B.root),
                                 topic=topic)["match_count"]


def _intent_file(A, key) -> Path:
    return A.root / "outbox" / "intents" / (outbox.key_id(key).split(":", 1)[1] + ".json")


def _send(A, key="k:1", claim="the finding", clock=None, **kwargs):
    return outbox.submit_send(A, "beta", key=key, claim=claim, topic=TOPIC,
                              kind="DISCOVERY", clock=clock, **kwargs)


def test_one_key_is_one_message_and_no_plaintext_stays_at_rest(tmp_path):
    A, B = _pair(tmp_path)
    first = _send(A)
    assert first["status"] == outbox.DELIVERED and first["ok"] is True
    again = _send(A)
    assert again["intent"]["envelope_id"] == first["intent"]["envelope_id"]
    assert again["intent"]["attempts"] == 1, "a resubmission must not deliver again"
    assert _received(B) == 1
    stored = _intent_file(A, "k:1").read_text(encoding="utf-8")
    assert "the finding" not in stored and json.loads(stored)["record"] is None
    envelope_id = first["intent"]["envelope_id"]
    assert (A.root / "outbox" / (envelope_id.split(":")[1] + ".senv")).is_file()
    opened = workspace.open_message(B, envelope_id)
    assert opened["record"]["claim"] == "the finding"


def test_a_reused_key_with_another_request_changes_nothing(tmp_path):
    A, B = _pair(tmp_path)
    _send(A)
    before = _intent_file(A, "k:1").read_bytes()
    for change in ({"claim": "another finding"}, {"kind": "WARNING"}, {"topic": "T-7"}):
        kwargs = {"key": "k:1", "claim": "the finding", "topic": TOPIC, "kind": "DISCOVERY"}
        kwargs.update(change)
        assert _code(outbox.submit_send, A, "beta", **kwargs) == outbox.IDEMPOTENCY_KEY_CONFLICT
    assert _intent_file(A, "k:1").read_bytes() == before
    assert _received(B) == 1


@pytest.mark.parametrize("key", ["", "has space", "x" * 257, "tab\tkey", "ключ"])
def test_bad_idempotency_keys_are_refused_before_anything_is_written(tmp_path, key):
    A, B = _pair(tmp_path)
    assert _code(_send, A, key=key) == outbox.IDEMPOTENCY_KEY_INVALID
    assert not (A.root / "outbox" / "intents").exists()


def test_an_offline_recipient_is_retried_with_backoff_and_delivered_once(tmp_path):
    A, B = _pair(tmp_path)
    offline = tmp_path / "B-offline"
    B.root.rename(offline)
    pending = _send(A, clock=lambda: T0)
    assert pending["status"] == outbox.PENDING_RETRY and pending["ok"] is True
    intent = pending["intent"]
    assert intent["state"] == outbox.SEALED and intent["attempts"] == 1
    assert intent["last_error"] == workspace.DELIVERY_TARGET_UNAVAILABLE
    assert intent["next_attempt_at"] == "2026-09-24T07:00:30Z"

    early = outbox.resume_outbox(A, clock=lambda: "2026-09-24T07:00:10Z")
    assert early["counts"]["not_due"] == 1 and early["counts"]["examined"] == 0
    second = outbox.resume_outbox(A, clock=lambda: "2026-09-24T07:00:30Z")
    assert second["items"][0]["next_attempt_at"] == "2026-09-24T07:01:30Z", "backoff doubles"

    offline.rename(B.root)
    done = outbox.resume_outbox(A, clock=lambda: "2026-09-24T07:01:30Z")
    assert done["counts"][outbox.DELIVERED] == 1
    assert _received(B) == 1
    assert outbox.resume_outbox(A, clock=lambda: "2026-09-24T08:00:00Z")["counts"]["examined"] == 0


def test_a_quarantine_is_terminal_until_the_operator_re_arms_it(tmp_path):
    A, B = _pair(tmp_path, register_back=False)
    failed = _send(A)
    assert failed["status"] == outbox.FAILED and failed["ok"] is False
    assert failed["intent"]["failure"] == postoffice.QUARANTINED
    assert outbox.resume_outbox(A)["counts"]["examined"] == 0, "no automatic retry loop"
    assert json.loads(_intent_file(A, "k:1").read_text(encoding="utf-8"))["attempts"] == 1

    workspace.add_recipient(B, "alpha", workspace.identity_card(A), A.root)
    retried = outbox.retry_intent(A, "k:1")
    assert retried["status"] == outbox.DELIVERED
    assert retried["intent"]["envelope_id"] == failed["intent"]["envelope_id"]
    assert _received(B) == 1
    assert _code(outbox.retry_intent, A, "k:1") == outbox.INTENT_NOT_FAILED
    assert _code(outbox.retry_intent, A, "k:unknown") == outbox.INTENT_UNKNOWN


def test_an_alias_rebound_to_another_seat_never_receives_the_sealed_bytes(tmp_path):
    A, B = _pair(tmp_path)
    _send(A, deliver=False)
    workspace.init_workspace(tmp_path / "C", seat="gamma")
    C = workspace.load_workspace(tmp_path / "C")
    peers = json.loads((A.root / workspace.PEERS_NAME).read_text(encoding="utf-8"))
    card = workspace.identity_card(C)
    peers["recipients"]["beta"] = {**peers["recipients"]["beta"], "seat": "gamma",
                                   "sender_public_key": card["sender_public_key"],
                                   "recipient_public_key": card["recipient_public_key"],
                                   "sender_kid": card["sender_kid"],
                                   "recipient_kid": card["recipient_kid"],
                                   "workspace": str(C.root)}
    (A.root / workspace.PEERS_NAME).write_text(json.dumps(peers), encoding="utf-8")
    result = outbox.resume_outbox(A)
    assert result["counts"][outbox.FAILED] == 1
    assert result["items"][0]["failure"] == workspace.RECIPIENT_IDENTITY_MISMATCH
    assert workspace.list_inbox(workspace.load_workspace_headers(C.root))["items"] == []


CHILD = r"""
import os, sys
sys.path.insert(0, sys.argv[1])
from saimail import envelope, outbox, postoffice, workspace

point = sys.argv[3]
original = postoffice.PostOffice.deliver
if point == "after_intent":
    envelope.seal = lambda *a, **k: os._exit(77)
elif point == "after_sealed_record":
    workspace._store_outbox = lambda *a, **k: os._exit(77)
elif point == "before_delivery":
    postoffice.PostOffice.deliver = lambda self, data: os._exit(77)
elif point == "after_delivery":
    def deliver_then_die(self, data):
        original(self, data)
        os._exit(77)
    postoffice.PostOffice.deliver = deliver_then_die
A = workspace.load_workspace(sys.argv[2])
outbox.submit_send(A, "beta", key="k:crash", claim="survives a crash", topic="T-119",
                   kind="DISCOVERY")
os._exit(0)
"""

CRASH_POINTS = {
    # point: (intent state left on disk, messages the receiver already holds)
    "after_intent": (outbox.PENDING, 0),
    "after_sealed_record": (outbox.SEALED, 0),
    "before_delivery": (outbox.SEALED, 0),
    "after_delivery": (outbox.SEALED, 1),
}


@pytest.mark.parametrize("point", sorted(CRASH_POINTS))
def test_a_process_killed_at_any_transition_resumes_to_exactly_one_message(tmp_path, point):
    A, B = _pair(tmp_path)
    killed = subprocess.run([sys.executable, "-c", CHILD, str(ROOT), str(A.root), point],
                            capture_output=True, text=True, timeout=120)
    assert killed.returncode == 77, killed.stderr
    on_disk = json.loads(_intent_file(A, "k:crash").read_text(encoding="utf-8"))
    state, delivered = CRASH_POINTS[point]
    assert on_disk["state"] == state
    assert _received(B) == delivered
    if state == outbox.SEALED:
        assert on_disk["record"] is None, "plaintext must leave the intent at SEALED"

    restarted = workspace.load_workspace(A.root)
    resumed = outbox.resume_outbox(restarted)
    assert resumed["counts"][outbox.DELIVERED] == 1
    final = resumed["items"][0]
    assert final["delivery_status"] == (postoffice.DUPLICATE if delivered else postoffice.ACCEPTED)
    assert _received(B) == 1
    again = _send(restarted, key="k:crash", claim="survives a crash")
    assert again["intent"]["envelope_id"] == final["envelope_id"] and _received(B) == 1
    opened = workspace.open_message(B, final["envelope_id"])
    assert opened["record"]["claim"] == "survives a crash"


RACER = r"""
import json, os, sys, time
sys.path.insert(0, sys.argv[1])
from saimail import outbox, workspace
A = workspace.load_workspace(sys.argv[2])
go = sys.argv[4]
deadline = time.monotonic() + 120
while not os.path.exists(go) and time.monotonic() < deadline:
    time.sleep(0.001)
result = outbox.submit_send(A, "beta", key=sys.argv[3], claim="raced " + sys.argv[3],
                            topic="T-119", kind="DISCOVERY")
print(json.dumps({"state": result["intent"]["state"],
                  "envelope_id": result["intent"]["envelope_id"]}))
"""


def _start_racers(A, keys, go: Path):
    return [subprocess.Popen([sys.executable, "-c", RACER, str(ROOT), str(A.root), key,
                              str(go)],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            for key in keys]


def _collect(racers):
    answers = []
    for racer in racers:
        out, err = racer.communicate(timeout=180)
        assert racer.returncode == 0, err
        answers.append(json.loads(out))
    return answers


def _race(A, keys):
    go = A.root.parent / "go"
    racers = _start_racers(A, keys, go)
    time.sleep(1.5)  # every racer is loaded and polling the start line
    go.write_text("go", encoding="utf-8")
    return _collect(racers)


def test_the_outbox_lock_excludes_a_second_process(tmp_path):
    A, B = _pair(tmp_path)
    go = tmp_path / "go"
    go.write_text("go", encoding="utf-8")
    with outbox._lock(A):
        racers = _start_racers(A, ["k:locked"], go)
        time.sleep(2.0)
        assert racers[0].poll() is None, "the second writer must wait for the lock"
        assert not _intent_file(A, "k:locked").exists()
    answers = _collect(racers)
    assert answers[0]["state"] == outbox.DELIVERED and _received(B) == 1


def test_concurrent_writers_with_one_key_produce_one_message(tmp_path):
    A, B = _pair(tmp_path)
    answers = _race(A, ["k:same"] * 6)
    assert {answer["state"] for answer in answers} == {outbox.DELIVERED}
    assert len({answer["envelope_id"] for answer in answers}) == 1
    assert _received(B) == 1


def test_concurrent_writers_with_distinct_keys_each_deliver_exactly_once(tmp_path):
    A, B = _pair(tmp_path)
    keys = [f"k:{number}" for number in range(8)]
    answers = _race(A, keys)
    assert len({answer["envelope_id"] for answer in answers}) == 8
    listing = workspace.list_inbox(workspace.load_workspace_headers(B.root))
    assert len(listing["items"]) == 8
    status = outbox.outbox_status(workspace.load_workspace_headers(A.root))["outbox"]
    assert status["counts"][outbox.DELIVERED] == 8 and status["pending"] == 0


class _Store(credentials.InMemoryCredentialStore):
    def __init__(self):
        super().__init__()
        self.reads = 0
        self.locked = False

    def get(self, handle):
        self.reads += 1
        if self.locked:
            raise credentials.BackendError("the credential store is locked")
        return super().get(handle)


def test_status_and_sealed_delivery_need_no_private_key(tmp_path):
    store = _Store()
    credentials.set_credential_store(store)
    try:
        A, B = _pair(tmp_path, mode=custody.CUSTODY_OS_STORE, store=store)
        _send(A, key="k:sealed", deliver=False)
        store.locked = True
        store.reads = 0
        view = workspace.load_workspace_headers(A.root)
        status = outbox.outbox_status(view)
        assert status["outbox"]["counts"][outbox.SEALED] == 1
        text = json.dumps(status)
        assert "the finding" not in text and "container" not in text
        resumed = outbox.resume_outbox(view)
        assert resumed["counts"][outbox.DELIVERED] == 1
        assert store.reads == 0, "status and sealed delivery must not touch custody"
        assert _received(B) == 1
    finally:
        credentials.set_credential_store(None)


def test_a_pending_intent_waits_for_the_signing_key_instead_of_failing(tmp_path):
    A, B = _pair(tmp_path)
    intent_key_id = outbox.key_id("k:pending")
    path = _intent_file(A, "k:pending")
    _send(A, key="k:pending", deliver=False)
    sealed = json.loads(path.read_text(encoding="utf-8"))
    # Rebuild the PENDING shape a crash before sealing leaves behind.
    record = workspace._build_content_record(A, claim="the finding", record_path=None,
                                             subject=workspace.DEFAULT_SUBJECT,
                                             created=sealed["created"])
    sealed.update(state=outbox.PENDING, container=None, envelope_id=None, sealed_at=None,
                  record=record.canonical_bytes().decode("utf-8"))
    path.write_text(json.dumps(sealed), encoding="utf-8")
    keyless = outbox.resume_outbox(workspace.load_workspace_headers(A.root))
    assert keyless["counts"]["needs_signing_key"] == 1 and _received(B) == 0
    assert outbox.resume_outbox(A)["counts"][outbox.DELIVERED] == 1
    assert _received(B) == 1 and intent_key_id.startswith("sha256:")


@pytest.mark.parametrize("damage", [
    lambda intent: intent.update(state="SENT"),
    lambda intent: intent.update(record="plaintext", state=outbox.DELIVERED),
    lambda intent: intent.update(envelope_id="sha256:" + "0" * 64),
    lambda intent: intent.update(stray=True),
])
def test_a_tampered_intent_fails_closed(tmp_path, damage):
    A, B = _pair(tmp_path)
    _send(A)
    path = _intent_file(A, "k:1")
    intent = json.loads(path.read_text(encoding="utf-8"))
    damage(intent)
    path.write_text(json.dumps(intent), encoding="utf-8")
    view = workspace.load_workspace_headers(A.root)
    assert _code(outbox.outbox_status, view) == outbox.OUTBOX_INTENT_CORRUPT
    assert _code(outbox.resume_outbox, A) == outbox.OUTBOX_INTENT_CORRUPT
    assert _code(_send, A) == outbox.OUTBOX_INTENT_CORRUPT
    assert _received(B) == 1


def test_cli_send_status_resume_and_retry(tmp_path, capsys):
    A, B = _pair(tmp_path)

    def cli(*argv):
        code = saimail_local.main(["outbox", *argv, "--workspace", str(A.root), "--json"])
        return code, json.loads(capsys.readouterr().out)

    code, sent = cli("send", "--to", "beta", "--key", "cli:1", "--claim", "via cli",
                     "--topic", TOPIC, "--kind", "WARNING")
    assert code == 0 and sent["status"] == outbox.DELIVERED
    assert sent["network_attempts"] == 0
    code, again = cli("send", "--to", "beta", "--key", "cli:1", "--claim", "via cli",
                      "--topic", TOPIC, "--kind", "WARNING")
    assert code == 0 and again["intent"]["attempts"] == 1
    code, conflict = cli("send", "--to", "beta", "--key", "cli:1", "--claim", "changed",
                         "--topic", TOPIC, "--kind", "WARNING")
    assert code == 1 and conflict["status"] == outbox.IDEMPOTENCY_KEY_CONFLICT
    assert conflict["operator_action_required"] is True
    code, status = cli("status")
    assert code == 0 and status["outbox"]["counts"][outbox.DELIVERED] == 1
    code, resumed = cli("resume")
    assert code == 0 and resumed["counts"]["examined"] == 0
    code, refused = cli("retry", "--key", "cli:1")
    assert code == 1 and refused["status"] == outbox.INTENT_NOT_FAILED
    assert _received(B) == 1
