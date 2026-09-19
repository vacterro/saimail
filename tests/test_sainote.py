"""T-8 acceptance: the SAINOTE renderer and the clear-header check (spec/02 §6).

What is proven here:

* every sealed envelope has a fully clear header (I2), and the check refuses
  anything unreadable by name;
* the note is the human twin of one *verified* envelope: same clear header,
  kind in words, no sealed payload, no TTL by default;
* narration requires provenance: raw bytes and unverified headers refuse;
* the note is deterministic and never contains sealing artifacts or plaintext;
* the module writes nothing, parses no payload and decrypts nothing.
"""

from __future__ import annotations

import base64
import pathlib

import pytest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

from sailang import SailangError
from saimail import envelope, sainote
from saimail.envelope import KeyRegistry, RecipientKeyRegistry

ROOT = pathlib.Path(__file__).resolve().parent.parent
T = "2026-09-18T12:34:56Z"

SENDER = Ed25519PrivateKey.generate()
OTHER_SENDER = Ed25519PrivateKey.generate()
RECIPIENT = X25519PrivateKey.generate()
REGISTRY = KeyRegistry({"A17": [SENDER.public_key(), OTHER_SENDER.public_key()]})
RECIPIENT_REGISTRY = RecipientKeyRegistry({"B03": [RECIPIENT.public_key()]})


def err(fn, *a, **k):
    with pytest.raises(SailangError) as e:
        fn(*a, **k)
    return e.value.code


def sealed(**over):
    fields = dict(sender=SENDER, sender_seat="A17", recipient_seat="B03",
                  kind="DISCOVERY", topic="queue-ownership", created=T, ttl=None,
                  ref=None, payload="sealed words")
    fields.update(over)
    return envelope.seal(fields.pop("payload"),
                         sender_private_key=fields.pop("sender"),
                         sender_seat=fields.pop("sender_seat"),
                         recipient_seat=fields.pop("recipient_seat"),
                         recipient_public_key=RECIPIENT.public_key(),
                         kind=fields.pop("kind"), topic=fields.pop("topic"),
                         created=fields.pop("created"), ttl=fields.pop("ttl"),
                         ref=fields.pop("ref"))


def verified_of(container):
    return envelope.verify(envelope.parse_header(container), REGISTRY)


def lines_of(text):
    return text[:-1].split("\n") if text.endswith("\n") else text.split("\n")


# ------------------------------------------------ I2: the clear-header check


def test_every_sealed_envelope_has_a_fully_clear_header():
    container = sealed(ttl="14D", ref="sha256:" + "e" * 64)
    clear = sainote.clear_header(container)
    assert clear["FROM"] == "A17" and clear["TO"] == "B03"
    assert clear["K"] == "DISCOVERY" and clear["TOPIC"] == "queue-ownership"
    assert clear["CREATED"] == T
    assert "TTL" not in clear and "REF" in clear, "TTL is conditional, REF is clear"
    for field in ("CIPHER_HASH", "EPK", "NONCE"):
        assert field not in clear, "sealing artifacts are not human metadata"


def test_the_clear_header_check_refuses_the_unclear():
    assert err(sainote.clear_header, "not a container at all") != None
    container = sealed()
    broken = container.replace("TOPIC:queue-ownership\n", "")
    assert err(sainote.clear_header, broken) in ("SIGNATURE_INVALID", "MISSING_FIELD",
                                                 "NON_CANONICAL_CONTAINER")


# ------------------------------------------------ the human twin


def test_the_note_is_the_twin_of_the_verified_header():
    container = sealed()
    note = sainote.render(verified_of(container))
    lines = lines_of(note)
    assert lines[0] == "SAINOTE"
    keys = [line.split(":", 1)[0] for line in lines[1:lines.index("")]]
    assert keys == ["FROM", "FROM_KID", "TO", "TO_KID", "K", "TOPIC", "CREATED"]
    assert "something found" in note, "the kind is rendered in words"
    assert "A17 sent B03" in note and T in note
    for artifact in ("CIPHERTEXT", "SIG:", "EPK:", "NONCE:", "CIPHER_HASH:"):
        assert artifact not in note, artifact
    assert "sealed words" not in note, "the payload never reaches the twin"


def test_ttl_is_absent_by_default_and_present_on_request():
    container = sealed(ttl="14D")
    assert "TTL:" not in sainote.render(verified_of(container))
    assert "TTL:14D" in sainote.render(verified_of(container), with_ttl=True)


def test_narration_requires_verified_provenance():
    container = sealed()
    parsed = envelope.parse_header(container)
    assert err(sainote.render, parsed) == "NOT_VERIFIED"
    assert err(sainote.render, container) == "NOT_VERIFIED"


def test_the_note_is_deterministic_and_sender_bound():
    first = sainote.render(verified_of(sealed()))
    second = sainote.render(verified_of(sealed()))
    assert first == second
    other = sainote.render(verified_of(sealed(sender=OTHER_SENDER,
                                              payload="other words")))
    assert other != first
    assert "FROM:A17" in first and "FROM:A17" in other


def test_the_renderer_writes_nothing_and_reads_no_payload():
    source = (ROOT / "saimail" / "sainote.py").read_text(encoding="utf-8")
    for forbidden in ("write_text", "write_bytes", "mkdir", "unlink", "rmtree",
                      "subprocess", "socket", "importlib"):
        assert forbidden not in source, f"the SAINOTE renderer must not carry {forbidden}"
    assert "open(" not in source
    note = sainote.render(verified_of(sealed(ref="sha256:" + "e" * 64)))
    assert "sha256:" + "e" * 64 in note, "a clear REF travels to the twin"
