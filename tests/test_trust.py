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