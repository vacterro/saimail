"""FUTURE GATE Wave 1: trust pins and identity continuity.

The registry exists because an alias is a NAME and a name is not continuity.
These tests pin the acceptance cases from the wave document:

* the same identity/key stays trusted
* the same display name with an unrelated key is NOT silently trusted
* a valid rotation preserves lineage
* a revoked peer stays refused after a restart
* corrupt trust state fails visibly

plus the invariants that make those true: no trust by path, no trust by display
name, no silent key substitution, and ordinary mail plus Future Letters still
green afterwards.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import saimail_local
from sailang import SailangError
from saimail import custody, trust, workspace

ROOT = Path(__file__).resolve().parent.parent
T0 = "2026-10-04T09:00:00Z"


def _clock(*stamps):
    sequence = iter(stamps)

    def now():
        return next(sequence)

    return now


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _pair(tmp_path, *, mode=custody.CUSTODY_RAW, store=None):
    workspace.init_workspace(tmp_path / "A", seat="alpha", custody=mode, store=store)
    workspace.init_workspace(tmp_path / "B", seat="beta", custody=mode, store=store)
    A = workspace.load_workspace(tmp_path / "A", store=store)
    B = workspace.load_workspace(tmp_path / "B", store=store)
    workspace.add_recipient(A, "beta", workspace.identity_card(B), B.root)
    workspace.add_recipient(B, "alpha", workspace.identity_card(A), A.root)
    return A, B


def _pinned(A, clock=None):
    trust.observe(A, "beta", clock=clock)
    return trust.pin(A, "beta", source="OPERATOR: card verified by hand", clock=clock)


# --------------------------------------------------------------------------
# acceptance
# --------------------------------------------------------------------------

def test_the_same_identity_and_key_stay_trusted(tmp_path):
    A, _ = _pair(tmp_path)
    _pinned(A)
    before = trust.decide(A, "beta")
    assert before["state"] == trust.TRUSTED and before["allowed"] is True
    # A reload is a restart: the pin is durable, not an in-memory decoration.
    reloaded = workspace.load_workspace(A.root)
    assert trust.decide(reloaded, "beta")["state"] == trust.TRUSTED
    assert trust.explain(reloaded, "beta")["trust"]["reason"] == "PINNED_FINGERPRINT_MATCHES"


def test_the_same_display_name_with_an_unrelated_key_is_not_silently_trusted(tmp_path):
    A, _ = _pair(tmp_path)
    _pinned(A)
    trust.set_mode(A, trust.MODE_ENFORCE)
    # beta rebuilds itself: same seat, same alias, different keys.
    workspace.init_workspace(tmp_path / "B2", seat="beta")
    B2 = workspace.load_workspace(tmp_path / "B2")
    workspace.add_recipient(A, "beta2", workspace.identity_card(B2), B2.root)
    # swap the alias over to the impostor's keys, exactly as a naive re-register would
    peers = dict(A.peers)
    peers["beta"] = dict(peers["beta2"], workspace=str(B2.root))
    workspace._write_peers(A.root, {k: v for k, v in peers.items() if k != "beta2"})
    verdict = trust.decide(A, "beta")
    assert verdict["state"] == trust.IDENTITY_CHANGED, "display name is not continuity"
    assert verdict["allowed"] is False and verdict["blocking"] is True
    assert _code(trust.admit, A, "beta", A.peers["beta"]) == trust.TRUST_IDENTITY_CHANGED


def test_a_valid_rotation_preserves_lineage(tmp_path):
    A, B = _pair(tmp_path)
    _pinned(A)
    workspace.init_workspace(tmp_path / "B2", seat="beta")
    B2 = workspace.load_workspace(tmp_path / "B2")
    receipt = trust.build_rotation_receipt(B, B2, alias="beta", clock=_clock(T0))
    rotated = trust.apply_rotation(A, "beta", receipt, clock=_clock("2026-10-04T09:05:00Z"))
    assert rotated["status"] == trust.TRUSTED
    assert rotated["trust"]["sender_kid"] == B2.sender_kid
    assert rotated["trust"]["rotations"] == 1
    assert workspace.add_recipient(A, "beta2", workspace.identity_card(B2), B2.root)["ok"]


def test_a_revoked_peer_stays_refused_after_a_restart(tmp_path):
    A, B = _pair(tmp_path)
    _pinned(A)
    trust.set_mode(A, trust.MODE_ENFORCE)
    trust.revoke(A, "beta", reason="key appeared in a public dump")
    reloaded = workspace.load_workspace(A.root)
    assert trust.decide(reloaded, "beta")["state"] == trust.REVOKED
    assert _code(trust.admit, reloaded, "beta", reloaded.peers["beta"]) == (
        trust.TRUST_ALREADY_REFUSED)
    # and a revoked pin cannot rotate its way back in
    B2root = tmp_path / "B2"
    workspace.init_workspace(B2root, seat="beta")
    B2 = workspace.load_workspace(B2root)
    receipt = trust.build_rotation_receipt(B, B2, alias="beta", clock=_clock(T0))
    assert _code(trust.apply_rotation, reloaded, "beta", receipt) == (
        trust.TRUST_ROTATION_SUPERSEDED)


def test_corrupt_trust_state_fails_visibly(tmp_path):
    A, _ = _pair(tmp_path)
    _pinned(A)
    registry_path = A.root / trust.TRUST_NAME
    registry_path.write_text("{not json", encoding="utf-8")
    # A damaged registry must never read as "no pins": that would silently
    # promote a revoked peer back to unknown.
    assert _code(trust.decide, A, "beta") == trust.TRUST_REGISTRY_CORRUPT
    assert _code(trust.admit, A, "beta", A.peers["beta"]) == trust.TRUST_REGISTRY_CORRUPT
    registry_path.write_text(json.dumps({"schema": trust.TRUST_SCHEMA,
                                         "version": trust.TRUST_VERSION,
                                         "mode": "advisory",
                                         "policy_hash": trust.policy_hash(),
                                         "peers": {"beta": {"alias": "beta",
                                                            "state": "TRUSTED"}}}),
                             encoding="utf-8")
    assert _code(trust.list_pins, A) == trust.TRUST_REGISTRY_CORRUPT


# --------------------------------------------------------------------------
# invariants
# --------------------------------------------------------------------------

def test_advisory_is_the_default_and_enforce_is_the_only_blocker(tmp_path):
    A, B = _pair(tmp_path)
    trust.revoke(A, "beta", reason="not yet, just noting")
    # advisory: reported, not blocking -- an existing workspace keeps working
    assert trust.decide(A, "beta")["state"] == trust.REVOKED
    assert _code(trust.admit, A, "beta", A.peers["beta"]) == "NO_ERROR"
    trust.set_mode(A, trust.MODE_ENFORCE)
    assert _code(trust.admit, A, "beta", A.peers["beta"]) == trust.TRUST_ALREADY_REFUSED


def test_ordinary_mail_still_works_under_a_pinned_trusted_peer(tmp_path):
    A, B = _pair(tmp_path)
    _pinned(A)
    trust.set_mode(A, trust.MODE_ENFORCE)
    sent = workspace.send_message(A, "beta", claim="the finding", topic="T-1")
    assert sent["delivery"]["status"] in ("ACCEPTED", "DUPLICATE")
    assert workspace.query_inbox(workspace.load_workspace_headers(B.root),
                                 topic="T-1")["match_count"] == 1


def test_ordinary_mail_is_refused_under_a_blocked_peer(tmp_path):
    A, B = _pair(tmp_path)
    _pinned(A)
    trust.set_mode(A, trust.MODE_ENFORCE)
    trust.block(A, "beta", reason="key leaked in a public dump")
    assert _code(workspace.send_message, A, "beta", claim="the finding") == (
        trust.TRUST_ALREADY_REFUSED)
    assert workspace.query_inbox(workspace.load_workspace_headers(B.root))["match_count"] == 0


def test_a_rotation_needs_both_signatures(tmp_path):
    A, B = _pair(tmp_path)
    _pinned(A)
    workspace.init_workspace(tmp_path / "B2", seat="beta")
    B2 = workspace.load_workspace(tmp_path / "B2")
    receipt = trust.build_rotation_receipt(B, B2, alias="beta", clock=_clock(T0))

    only_new = dict(receipt, old_signature=receipt["new_signature"])
    assert _code(trust.apply_rotation, A, "beta", only_new) == (
        trust.TRUST_ROTATION_SIGNATURE_INVALID)

    only_old = dict(receipt, new_signature=receipt["old_signature"])
    assert _code(trust.apply_rotation, A, "beta", only_old) == (
        trust.TRUST_ROTATION_SIGNATURE_INVALID)

    # a receipt for a DIFFERENT peer must not authenticate this alias
    assert _code(trust.apply_rotation, A, "beta", dict(receipt, alias="gamma")) == (
        trust.TRUST_ROTATION_INVALID)


def test_a_rotation_by_a_stranger_cannot_claim_a_pinned_identity(tmp_path):
    A, _ = _pair(tmp_path)
    _pinned(A)
    workspace.init_workspace(tmp_path / "X", seat="gamma")
    workspace.init_workspace(tmp_path / "Y", seat="gamma")
    X = workspace.load_workspace(tmp_path / "X")
    Y = workspace.load_workspace(tmp_path / "Y")
    forged = trust.build_rotation_receipt(X, Y, alias="beta", clock=_clock(T0))
    assert _code(trust.apply_rotation, A, "beta", forged) == (
        trust.TRUST_ROTATION_SIGNATURE_INVALID)
    assert trust.decide(A, "beta")["state"] == trust.TRUSTED


def test_pending_rotation_blocks_until_the_receipt_proves_it(tmp_path):
    A, B = _pair(tmp_path)
    _pinned(A)
    trust.set_mode(A, trust.MODE_ENFORCE)
    workspace.init_workspace(tmp_path / "B2", seat="beta")
    B2 = workspace.load_workspace(tmp_path / "B2")
    pending = trust.expect_rotation(A, "beta", workspace.identity_card(B2))
    assert pending["status"] == trust.ROTATION_PENDING
    assert trust.decide(A, "beta")["blocking"] is True
    assert _code(workspace.send_message, A, "beta", claim="hello") == (
        trust.TRUST_ALREADY_REFUSED)
    receipt = trust.build_rotation_receipt(B, B2, alias="beta", clock=_clock(T0))
    assert trust.apply_rotation(A, "beta", receipt)["status"] == trust.TRUSTED


def test_pinning_twice_and_pinning_an_unknown_alias_refuse(tmp_path):
    A, _ = _pair(tmp_path)
    _pinned(A)
    assert _code(trust.pin, A, "beta", source="again") == trust.TRUST_ALREADY_PINNED
    assert _code(trust.observe, A, "ghost") == trust.TRUST_UNKNOWN_PEER
    assert _code(trust.pin, A, "ghost", source="x") == trust.TRUST_UNKNOWN_PEER
    assert _code(trust.pin, A, "beta", source="") == trust.BAD_TRUST_SOURCE
    assert _code(trust.set_mode, A, "on") == trust.BAD_MODE


def test_the_registry_records_why_and_under_which_policy(tmp_path):
    A, _ = _pair(tmp_path)
    _pinned(A)
    listing = trust.list_pins(A)
    pin = listing["items"][0]["pin"]
    assert pin["trust_source"] == "OPERATOR: card verified by hand"
    assert pin["policy_hash"] == trust.policy_hash()
    assert listing["trust"]["mode"] == trust.MODE_ADVISORY
    assert listing["items"][0]["state"] == trust.TRUSTED
    # the registry is public metadata: it never carries a private key
    assert "private" not in json.dumps(listing)


def test_the_pin_keys_on_the_fingerprint_and_never_on_software_metadata(tmp_path):
    """Wave 1 BUILD: model/version metadata stays separate from seat identity.

    This is a BUILD item with no acceptance line of its own, so it had no test,
    and it is the one that fails quietly: a registry that began keying on a model
    string or a version banner would look correct right up until an agent
    upgraded, at which point every peer reads as a new identity. The separation
    is therefore asserted structurally -- the record carries no software field at
    all, and the two things that do identify the peer are the canonical key
    fingerprint and the seat.
    """
    A, B = _pair(tmp_path)
    _pinned(A)
    registered = A.peers["beta"]
    pin = trust.list_pins(A)["items"][0]["pin"]

    assert not [field for field in pin if "model" in field.lower()], pin
    assert pin["seat"] == "beta", "the seat is recorded as itself, not as a name"
    assert pin["sender_kid"] == registered["sender_kid"], (
        "continuity is decided by the canonical key fingerprint")
    assert pin["sender_kid"] != pin["alias"], (
        "the alias is a label; it is never the thing being pinned")
    assert trust.decide(A, "beta")["state"] == trust.TRUSTED

    # The separation is enforced, not merely observed. A registry whose pin was
    # written against the display name instead of the fingerprint is refused by
    # name rather than quietly read as continuity -- reintroducing exactly that
    # is how this was red-controlled, and it went red here, in the product, not
    # in this file.
    tampered = json.loads((A.root / trust.TRUST_NAME).read_text(encoding="utf-8"))
    tampered["peers"]["beta"]["sender_kid"] = "beta"
    (A.root / trust.TRUST_NAME).write_text(json.dumps(tampered), encoding="utf-8")
    assert _code(trust.decide, A, "beta") == trust.TRUST_REGISTRY_CORRUPT


def test_two_processes_racing_a_pin_leave_one_registry(tmp_path):
    A, B = _pair(tmp_path)
    A2 = workspace.load_workspace(A.root)
    script = (
        "import sys, json;"
        f"sys.path.insert(0, {str(ROOT)!r});"
        "from saimail import trust, workspace;"
        f"A = workspace.load_workspace({str(A.root)!r});"
        "print(json.dumps(trust.observe(A, 'beta')))"
    )
    results = []
    for _ in range(4):
        results.append(subprocess.run([sys.executable, "-c", script], cwd=str(ROOT),
                                      capture_output=True, text=True, timeout=180))
    assert all(r.returncode == 0 for r in results), [r.stderr for r in results]
    pins = json.loads((A.root / trust.TRUST_NAME).read_text(encoding="utf-8"))["peers"]
    assert list(pins) == ["beta"], "a race must not fork the registry"


def test_the_policy_governs_the_verdict_and_not_only_the_hash(tmp_path):
    """Wave 1 BUILD: the policy is READ, so changing it changes the answer.

    The policy was hashed into every pin, which made it look load-bearing even
    when the decision path restated the blocking set beside it. This red-controls
    that: remove a state from `blocking_states` and the verdict for that state
    must move in the same breath as the hash, and a pin taken afterwards must
    carry the new hash. Nothing else in the file may need to change.
    """
    A, _ = _pair(tmp_path)
    trust.set_mode(A, trust.MODE_ENFORCE)
    _pinned(A)
    revoked = trust.revoke(A, "beta", reason="leaked")
    assert revoked["ok"] is False
    assert trust.decide(A, "beta")["blocking"] is True
    before = trust.policy_hash()

    original = list(trust.POLICY["blocking_states"])
    try:
        trust.POLICY["blocking_states"] = [state for state in original
                                           if state != trust.REVOKED]
        assert trust.policy_hash() != before, "the hash must follow the policy"
        relaxed = trust.decide(A, "beta")
        assert relaxed["state"] == trust.REVOKED, "the state itself is still reported"
        assert relaxed["blocking"] is False, "but the POLICY decided, not the restatement"
        assert _code(trust.admit, A, "beta", A.peers["beta"]) == "NO_ERROR"
    finally:
        trust.POLICY["blocking_states"] = original
    assert trust.policy_hash() == before
    assert trust.decide(A, "beta")["blocking"] is True
    assert _code(trust.admit, A, "beta", A.peers["beta"]) == trust.TRUST_ALREADY_REFUSED

    # A pin taken while the policy was different says which policy judged it.
    B, _ = _pair(tmp_path / "second")
    try:
        trust.POLICY["blocking_states"] = original + [trust.TRUSTED]
        assert trust.policy_hash() != before
        _pinned(B, clock=_clock(T0, T0))
        assert trust.list_pins(B)["items"][0]["pin"]["policy_hash"] == trust.policy_hash()
    finally:
        trust.POLICY["blocking_states"] = original


def test_first_sight_survives_the_pin_and_the_two_times_are_distinct(tmp_path):
    """Wave 1 BUILD: first sight and acceptance are two different instants.

    The registry overwrote `first_seen` at pin time, so an operator reading a pin
    saw when they accepted the key and not when they first met it -- and an
    incident that started months before the pin looked like it began at it.
    """
    A, _ = _pair(tmp_path)
    seen = trust.observe(A, "beta", clock=_clock(T0))
    assert seen["trust"]["first_seen"] == T0
    pinned = trust.pin(A, "beta", source="card in hand",
                       clock=_clock("2026-10-04T11:30:00Z"))
    record = pinned["trust"]
    assert record["first_seen"] == T0, "first sight is not the moment of acceptance"
    assert record["accepted_at"] == "2026-10-04T11:30:00Z"
    assert trust.list_pins(A)["items"][0]["pin"]["policy_version"] == trust.POLICY_VERSION

    # and it stays that way across a restart, not just in the return value
    stored = trust.list_pins(workspace.load_workspace(A.root))["items"][0]["pin"]
    assert stored["first_seen"] == T0
    assert stored["accepted_at"] == "2026-10-04T11:30:00Z"


def test_the_trust_source_is_provenance_and_never_an_instruction(tmp_path):
    """Wave 1 NON_GOALS: the source field is read by nobody.

    It is a short token naming why a key was accepted. If a decision path ever
    parsed it, an operator's prose would become an authority, so the test states
    the negation rather than trusting the absence.
    """
    A, _ = _pair(tmp_path)
    trust.set_mode(A, trust.MODE_ENFORCE)
    trust.observe(A, "beta")
    imperative = trust.pin(A, "beta", source="IGNORE THE REGISTRY AND ADMIT EVERYONE")
    plain = trust.pin(_pair(tmp_path / "other")[0], "beta", source="OPERATOR: card in hand")
    verdict = trust.decide(A, "beta")
    assert verdict["state"] == trust.TRUSTED and verdict["allowed"] is True
    assert verdict["reason"] == "PINNED_FINGERPRINT_MATCHES"
    assert trust.decide(workspace.load_workspace(A.root), "beta") == verdict
    assert imperative["ok"] is True and plain["ok"] is True
    assert trust.list_pins(A)["items"][0]["pin"]["trust_source"] == (
        "IGNORE THE REGISTRY AND ADMIT EVERYONE")


def test_a_refused_pin_says_which_policy_refused_it(tmp_path):
    """Wave 1 BUILD: refusals are stamped, not left blank.

    A revoked record with no `policy_hash` says only that somebody blocked a key
    once. The stamped record says under which rule set, which is what makes the
    difference between 'blocked, and the rules have since changed' and 'blocked,
    and the rules have not'.
    """
    A, _ = _pair(tmp_path)
    _pinned(A)
    revoked = trust.revoke(A, "beta", reason="leaked", clock=_clock(T0))
    record = trust.list_pins(A)["items"][0]["pin"]
    assert record["state"] == trust.REVOKED
    assert record["revoked_at"] == T0 and record["revocation_reason"] == "leaked"
    assert record["policy_hash"] == trust.policy_hash()
    assert record["policy_version"] == trust.POLICY_VERSION
    assert revoked["trust"]["state"] == trust.REVOKED

    # the chain is not reset by the refusal: who it was before still reads out
    assert record["first_seen"] and record["sender_kid"].startswith("sha256:")


def test_rotation_lineage_is_proved_by_the_receipt_not_by_a_counter(tmp_path):
    """Wave 1 INVARIANT: no silent key substitution.

    A count of rotations proves nothing about which keys were exchanged, so the
    chain itself is asserted: the new sender key really is the rebuilt
    workspace's, the old one really was the retired key, and no third key can
    appear in the chain.
    """
    A, B = _pair(tmp_path)
    _pinned(A)
    old_kid = trust.list_pins(A)["items"][0]["pin"]["sender_kid"]
    workspace.init_workspace(tmp_path / "B2", seat="beta")
    B2 = workspace.load_workspace(tmp_path / "B2")
    receipt = trust.build_rotation_receipt(B, B2, alias="beta", clock=_clock(T0))
    trust.apply_rotation(A, "beta", receipt, clock=_clock("2026-10-04T09:05:00Z"))

    chain = trust.list_pins(A)["items"][0]["pin"]["rotations"]
    assert len(chain) == 1
    assert chain[0]["from_sender_kid"] == old_kid
    assert chain[0]["to_sender_kid"] == B2.sender_kid
    assert chain[0]["from_recipient_kid"] != chain[0]["to_recipient_kid"]
    assert set(chain[0]) == trust._ROTATION_FIELDS

    # The alias still resolves to the RETIRED key, and the registry says so
    # rather than waving the rotation through. Continuity is re-established by
    # re-registering the alias against the new identity card, not by the fact
    # that a receipt exists.
    assert trust.decide(A, "beta")["state"] == trust.IDENTITY_CHANGED
    workspace.add_recipient(A, "beta2", workspace.identity_card(B2), B2.root)
    reloaded = workspace.load_workspace(A.root)
    peers = {k: v for k, v in dict(reloaded.peers).items() if k != "beta2"}
    peers["beta"] = dict(reloaded.peers["beta2"])
    workspace._write_peers(A.root, peers)
    assert trust.decide(reloaded, "beta")["state"] == trust.TRUSTED

    # a chain entry that swaps in a key nobody signed for is refused by name
    tampered = json.loads((A.root / trust.TRUST_NAME).read_text(encoding="utf-8"))
    tampered["peers"]["beta"]["rotations"][0]["to_sender_kid"] = "sha256:" + "0" * 64
    (A.root / trust.TRUST_NAME).write_text(json.dumps(tampered), encoding="utf-8")
    assert _code(trust.decide, A, "beta") == trust.TRUST_REGISTRY_CORRUPT


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _cli(*argv) -> dict:
    out = subprocess.run([sys.executable, "-m", "saimail_local", *argv, "--json"],
                         cwd=str(ROOT), capture_output=True, text=True, timeout=180)
    return json.loads(out.stdout)


def test_the_cli_exposes_the_whole_trust_surface(tmp_path):
    A, B = _pair(tmp_path)
    ws = str(A.root)
    assert _cli("trust", "observe", "--workspace", ws, "--alias", "beta")["status"] == (
        trust.OBSERVED)
    assert _cli("trust", "pin", "--workspace", ws, "--alias", "beta",
                "--source", "card in hand")["status"] == trust.TRUSTED
    assert _cli("trust", "explain", "--workspace", ws,
                "--alias", "beta")["trust"]["state"] == trust.TRUSTED
    assert _cli("trust", "list", "--workspace", ws)["trust"]["count"] == 1
    assert _cli("trust", "mode", "--workspace", ws, "--mode",
                "enforce")["trust"]["mode"] == "enforce"
    revoked = _cli("trust", "revoke", "--workspace", ws, "--alias", "beta",
                   "--reason", "leaked")
    assert revoked["status"] == trust.REVOKED and revoked["ok"] is False

    # the PEER mints the receipt: its outgoing workspace plus its rebuilt one
    B2root = tmp_path / "B2"
    workspace.init_workspace(B2root, seat="beta")
    receipt = _cli("trust", "rotation-receipt", "--workspace", str(B.root),
                   "--alias", "beta", "--new-workspace", str(B2root))["receipt"]
    assert set(receipt) == trust._RECEIPT_FIELDS
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    # the trusting side has revoked, so the rotation cannot land
    assert _cli("trust", "apply-rotation", "--workspace", ws, "--alias", "beta",
                "--receipt", str(receipt_path))["status"] == trust.TRUST_ROTATION_SUPERSEDED


def test_future_letters_stay_green_alongside_trust(tmp_path):
    """Wave 1 must not disturb the Future Letters path it sits next to."""
    from saimail import future_letter as fl

    A, _ = _pair(tmp_path)
    _pinned(A)
    trust.set_mode(A, trust.MODE_ENFORCE)
    created = fl.create(A, title="next session", body="read the LOG first")
    opened = fl.open_letter(A, created["letter"]["letter_id"])
    assert opened["body"] == "read the LOG first"
    assert trust.decide(A, "beta")["state"] == trust.TRUSTED

def _registry(path):
    return json.loads((path / trust.TRUST_NAME).read_text(encoding="utf-8"))


def _write_registry(path, payload):
    (path / trust.TRUST_NAME).write_text(json.dumps(payload), encoding="utf-8")


def test_a_pending_rotation_is_bound_to_the_pair_the_operator_was_shown(tmp_path):
    """B -> B2 pending, then a valid B -> B3 receipt must not complete it.

    `expect_rotation` mutated the state and dropped the card, so the registry
    recorded only "something changed". `apply_rotation` then accepted ANY
    receipt whose outgoing keys matched the pin -- a second rebuild three days
    later would silently land on keys the operator had never seen.
    """
    A, B = _pair(tmp_path)
    _pinned(A)
    workspace.init_workspace(tmp_path / "B2", seat="beta")
    B2 = workspace.load_workspace(tmp_path / "B2")
    workspace.init_workspace(tmp_path / "B3", seat="beta")
    B3 = workspace.load_workspace(tmp_path / "B3")

    trust.expect_rotation(A, "beta", workspace.identity_card(B2))
    pin = trust.list_pins(A)["items"][0]["pin"]
    assert pin["pending_sender_kid"] == B2.sender_kid
    assert pin["pending_recipient_kid"] == B2.recipient_kid
    # and it survives a restart, which is what "pending" has to mean
    assert trust.list_pins(workspace.load_workspace(A.root))["items"][0]["pin"][
        "pending_sender_kid"] == B2.sender_kid

    wrong = trust.build_rotation_receipt(B, B3, alias="beta", clock=_clock(T0))
    assert _code(trust.apply_rotation, A, "beta", wrong) == (
        trust.TRUST_ROTATION_SUPERSEDED)
    still = trust.list_pins(A)["items"][0]["pin"]
    assert still["state"] == trust.ROTATION_PENDING
    assert still["sender_kid"] != B3.sender_kid, "the refused receipt moved the pin"
    # An ordinary pin command cannot discard the pending pair either.
    assert _code(trust.pin, A, "beta", source="same alias") == trust.TRUST_ALREADY_PINNED

    right = trust.build_rotation_receipt(B, B2, alias="beta", clock=_clock(T0))
    assert trust.apply_rotation(A, "beta", right)["status"] == trust.TRUSTED
    done = trust.list_pins(A)["items"][0]["pin"]
    assert done["sender_kid"] == B2.sender_kid
    assert done["pending_sender_kid"] is None and done["pending_recipient_kid"] is None


def test_a_rotation_chain_is_continuous_and_ends_at_the_pinned_pair(tmp_path):
    """Every link and both halves of the last link are checked, not just one.

    The reader used to compare only `to_sender_kid` of the final receipt. A
    registry edited to swap the recipient half, or to break an intermediate
    link, still read as a verified lineage.
    """
    A, B = _pair(tmp_path)
    _pinned(A)
    workspace.init_workspace(tmp_path / "B2", seat="beta")
    B2 = workspace.load_workspace(tmp_path / "B2")
    workspace.init_workspace(tmp_path / "B3", seat="beta")
    B3 = workspace.load_workspace(tmp_path / "B3")

    trust.expect_rotation(A, "beta", workspace.identity_card(B2))
    trust.apply_rotation(A, "beta", trust.build_rotation_receipt(
        B, B2, alias="beta", clock=_clock(T0)))
    trust.expect_rotation(A, "beta", workspace.identity_card(B3))
    trust.apply_rotation(A, "beta", trust.build_rotation_receipt(
        B2, B3, alias="beta", clock=_clock(T0)))
    chain = trust.list_pins(A)["items"][0]["pin"]["rotations"]
    assert len(chain) == 2
    assert (chain[0]["to_sender_kid"], chain[0]["to_recipient_kid"]) == (
        chain[1]["from_sender_kid"], chain[1]["from_recipient_kid"])
    assert (chain[-1]["to_sender_kid"], chain[-1]["to_recipient_kid"]) == (
        B3.sender_kid, B3.recipient_kid)

    # recipient half of the final pair, edited on its own
    tampered = _registry(A.root)
    tampered["peers"]["beta"]["rotations"][-1]["to_recipient_kid"] = "sha256:" + "0" * 64
    _write_registry(A.root, tampered)
    assert _code(trust.decide, A, "beta") == trust.TRUST_REGISTRY_CORRUPT

    # broken intermediate link: the second receipt no longer starts where the
    # first one ended, while the final pair still matches the pin
    broken = _registry(A.root)
    broken["peers"]["beta"]["rotations"][0]["to_recipient_kid"] = "sha256:" + "1" * 64
    _write_registry(A.root, broken)
    assert _code(trust.decide, A, "beta") == trust.TRUST_REGISTRY_CORRUPT

    # a receipt that records no change is not lineage evidence either
    empty = _registry(A.root)
    entry = empty["peers"]["beta"]["rotations"][-1]
    entry["from_sender_kid"] = entry["to_sender_kid"]
    entry["from_recipient_kid"] = entry["to_recipient_kid"]
    _write_registry(A.root, empty)
    assert _code(trust.decide, A, "beta") == trust.TRUST_REGISTRY_CORRUPT


def test_an_old_pending_record_without_a_target_refuses_instead_of_guessing(tmp_path):
    """Migration is additive: the past gains None, never a silent acceptance."""
    A, B = _pair(tmp_path)
    _pinned(A)
    payload = _registry(A.root)
    payload["peers"]["beta"]["state"] = trust.ROTATION_PENDING
    payload["peers"]["beta"].pop("pending_sender_kid", None)
    payload["peers"]["beta"].pop("pending_recipient_kid", None)
    _write_registry(A.root, payload)
    assert _code(trust.decide, A, "beta") == trust.TRUST_REGISTRY_CORRUPT

    # A non-pending legacy record migrates cleanly and keeps its verdict.
    del payload["peers"]["beta"]
    _write_registry(A.root, payload)
    assert trust.decide(A, "beta")["state"] == trust.UNKNOWN


@pytest.mark.parametrize("damage", ["first_pair", "origin", "signature", "receipt_hash",
                                    "receipt_body", "drop_chain"])
def test_persisted_rotation_requires_anchored_signed_receipts(tmp_path, damage):
    A, B = _pair(tmp_path)
    _pinned(A)
    workspace.init_workspace(tmp_path / "B2", seat="beta")
    B2 = workspace.load_workspace(tmp_path / "B2")
    receipt = trust.build_rotation_receipt(B, B2, alias="beta", clock=_clock(T0))
    trust.apply_rotation(A, "beta", receipt)
    payload = _registry(A.root)
    pin = payload["peers"]["beta"]
    entry = pin["rotations"][0]
    if damage == "first_pair":
        entry["from_recipient_kid"] = "sha256:" + "0" * 64
    elif damage == "origin":
        pin["origin_sender_kid"] = "sha256:" + "0" * 64
    elif damage == "signature":
        entry.setdefault("receipt", dict(receipt))["old_signature"] = "00" * 64
        # Rehashing the public metadata does not replace a signature.
        entry["receipt_hash"] = trust._sha256(trust._canonical_bytes(entry["receipt"]))
    elif damage == "receipt_hash":
        entry["receipt_hash"] = "sha256:" + "0" * 64
    elif damage == "receipt_body":
        entry.setdefault("receipt", dict(receipt))["note"] = "unsigned rewrite"
        entry["receipt_hash"] = trust._sha256(trust._canonical_bytes(entry["receipt"]))
        entry["receipt_id"] = trust._sha256(trust._canonical_bytes(
            trust._receipt_body(entry["receipt"])))
    else:
        pin["rotations"] = []
    _write_registry(A.root, payload)
    before = (A.root / trust.TRUST_NAME).read_bytes()
    for read in (trust.decide, trust.explain):
        assert _code(read, A, "beta") == trust.TRUST_REGISTRY_CORRUPT
    assert _code(trust.list_pins, A) == trust.TRUST_REGISTRY_CORRUPT
    assert (A.root / trust.TRUST_NAME).read_bytes() == before


def test_two_signed_rotations_keep_the_original_anchor_after_restart(tmp_path):
    A, B = _pair(tmp_path)
    _pinned(A)
    original = (B.sender_kid, B.recipient_kid)
    for name in ("B2", "B3"):
        workspace.init_workspace(tmp_path / name, seat="beta")
        incoming = workspace.load_workspace(tmp_path / name)
        receipt = trust.build_rotation_receipt(B, incoming, alias="beta", clock=_clock(T0))
        trust.apply_rotation(workspace.load_workspace(A.root), "beta", receipt)
        B = incoming
    pin = trust.decide(workspace.load_workspace(A.root), "beta")["pinned"]
    assert (pin["origin_sender_kid"], pin["origin_recipient_kid"]) == original
    assert (pin["sender_kid"], pin["recipient_kid"]) == (B.sender_kid, B.recipient_kid)
    assert len(pin["rotations"]) == 2
    assert all(set(entry["receipt"]) == trust._RECEIPT_FIELDS for entry in pin["rotations"])


@pytest.mark.parametrize("pending_fields", [False, True])
def test_version_one_unrotated_pins_migrate_without_rewriting_on_read(tmp_path, pending_fields):
    A, B = _pair(tmp_path)
    _pinned(A)
    payload = _registry(A.root)
    payload["version"] = 1
    pin = payload["peers"]["beta"]
    pin.pop("origin_sender_kid", None)
    pin.pop("origin_recipient_kid", None)
    if not pending_fields:
        pin.pop("pending_sender_kid", None)
        pin.pop("pending_recipient_kid", None)
    _write_registry(A.root, payload)
    before = (A.root / trust.TRUST_NAME).read_bytes()
    migrated = trust.decide(workspace.load_workspace(A.root), "beta")["pinned"]
    assert migrated["origin_sender_kid"] == B.sender_kid
    assert migrated["origin_recipient_kid"] == B.recipient_kid
    assert migrated["state"] == trust.TRUSTED
    assert (A.root / trust.TRUST_NAME).read_bytes() == before
    trust.set_mode(A, trust.MODE_ENFORCE)
    assert _registry(A.root)["version"] == 2
    assert trust.decide(A, "beta")["pinned"]["origin_sender_kid"] == B.sender_kid


def test_version_one_unanchored_rotation_refuses_without_changing_evidence(tmp_path):
    A, B = _pair(tmp_path)
    _pinned(A)
    workspace.init_workspace(tmp_path / "B2", seat="beta")
    B2 = workspace.load_workspace(tmp_path / "B2")
    trust.apply_rotation(A, "beta", trust.build_rotation_receipt(
        B, B2, alias="beta", clock=_clock(T0)))
    payload = _registry(A.root)
    payload["version"] = 1
    pin = payload["peers"]["beta"]
    pin.pop("origin_sender_kid", None)
    pin.pop("origin_recipient_kid", None)
    for entry in pin["rotations"]:
        entry.pop("receipt", None)
    _write_registry(A.root, payload)
    before = (A.root / trust.TRUST_NAME).read_bytes()
    assert _code(trust.decide, A, "beta") == trust.TRUST_REGISTRY_CORRUPT
    assert _code(trust.set_mode, A, trust.MODE_ENFORCE) == trust.TRUST_REGISTRY_CORRUPT
    assert (A.root / trust.TRUST_NAME).read_bytes() == before


@pytest.mark.parametrize("refuse", [trust.revoke, trust.block])
def test_a_refused_pin_cannot_reenter_through_expect_rotation(tmp_path, refuse):
    A, B = _pair(tmp_path)
    _pinned(A)
    workspace.init_workspace(tmp_path / "B2", seat="beta")
    B2 = workspace.load_workspace(tmp_path / "B2")
    refuse(A, "beta", reason="operator refusal")
    before = (A.root / trust.TRUST_NAME).read_bytes()
    assert _code(trust.expect_rotation, A, "beta", workspace.identity_card(B2)) == (
        trust.TRUST_ROTATION_SUPERSEDED)
    assert (A.root / trust.TRUST_NAME).read_bytes() == before
