"""B-001 Target B: canonical HLET1 plaintext and HUMAN_ID identity (D-042).

Proven here: one letter has exactly one accepted byte representation; SUBJECT
and BODY round-trip exactly, multiline prose included, with no trim and no
normalization; bounds and field-set violations refuse before any crypto; the
human identity is the sha256 of the canonical P-256 SPKI DER and a recovery key
must be cryptographically distinct from the primary one.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric import ec, x25519
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from sailang import SailangError
from saimail.sailetter import (
    HUMAN_ID_PREFIX,
    HumanPrivateLetter,
    HumanRecipient,
    human_id,
)

T = "2026-09-19T10:00:00Z"
OTHER = "human-id:sha256:" + "b" * 64

PRIMARY = ec.generate_private_key(ec.SECP256R1())
RECOVERY = ec.generate_private_key(ec.SECP256R1())


def err(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value.code


def spki(public_key) -> bytes:
    return public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)


def b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def letter_text(**changes) -> str:
    values = dict(
        to_human=human_id(PRIMARY.public_key()),
        created=T,
        subject="queue note",
        body="one line",
    )
    values.update(changes)
    return (
        "HLET1\n"
        "CLASS:HUMAN_PRIVATE\n"
        f"TO_HUMAN:{values['to_human']}\n"
        f"CREATED:{values['created']}\n"
        f"SUBJECT_B64:{b64(values['subject'])}\n"
        f"BODY_B64:{b64(values['body'])}\n"
    )


def letter(**changes) -> HumanPrivateLetter:
    return HumanPrivateLetter(
        to_human=changes.get("to_human", human_id(PRIMARY.public_key())),
        created=changes.get("created", T),
        subject=changes.get("subject", "queue note"),
        body=changes.get("body", "one line"),
    )


# --------------------------------------------------------------------
# canonical round-trip
# --------------------------------------------------------------------


def test_hlet1_canonical_round_trip():
    original = letter(subject="subject", body="single line body")
    parsed = HumanPrivateLetter.parse(original.render())
    assert parsed == original
    assert parsed.render() == original.render()


def test_multiline_body_exact_round_trip():
    body = "line one\n\nline three\r\nline four with trailing spaces   \n\u00e4\u00f5\u00fc \U0001f600\n"
    original = letter(subject="multi\nline subject", body=body)
    parsed = HumanPrivateLetter.parse(original.render())
    assert parsed.body == body
    assert "\r" in parsed.body, "CR is data inside the base64 body and is preserved"
    assert parsed.subject == "multi\nline subject"


def test_no_hidden_normalization():
    original = letter(subject="  padded  ", body="\ttabbed\ntrail  \n")
    parsed = HumanPrivateLetter.parse(original.render())
    assert parsed.subject == "  padded  "
    assert parsed.body == "\ttabbed\ntrail  \n"


def test_letter_is_immutable():
    item = letter()
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.subject = "other"


# --------------------------------------------------------------------
# bounded canonical parsing
# --------------------------------------------------------------------


def test_hlet1_rejects_wrong_format_and_class():
    assert err(HumanPrivateLetter.parse,
               letter_text().replace("HLET1", "HLET2", 1)) == "HLET1_BAD_FORMAT"
    assert err(HumanPrivateLetter.parse,
               letter_text().replace("CLASS:HUMAN_PRIVATE", "CLASS:HUMAN_PUBLIC")) == "HLET1_BAD_CLASS"


def test_hlet1_rejects_duplicate_unknown_and_reordered_fields():
    text = letter_text()
    lines = text.rstrip("\n").split("\n")
    assert err(HumanPrivateLetter.parse,
               text.replace("CREATED:", "CREATED2:", 1)) == "HLET1_UNKNOWN_FIELD"
    duplicate = "\n".join(lines[:2] + [lines[2], lines[2]] + lines[3:]) + "\n"
    assert err(HumanPrivateLetter.parse, duplicate) == "HLET1_DUPLICATE_FIELD"
    reordered = "\n".join([lines[0], lines[1], lines[3], lines[2], lines[4], lines[5]]) + "\n"
    assert err(HumanPrivateLetter.parse, reordered) == "HLET1_FIELD_ORDER"


def test_hlet1_rejects_noncanonical_bytes():
    text = letter_text()
    assert err(HumanPrivateLetter.parse, b"\xef\xbb\xbf" + text.encode("utf-8")) \
        == "HLET1_NONCANONICAL"
    assert err(HumanPrivateLetter.parse, text.replace("\n", "\r\n")) == "HLET1_NONCANONICAL"
    assert err(HumanPrivateLetter.parse, text[:-1]) == "HLET1_NONCANONICAL"
    # `YR==` and `YQ==` decode to the same byte; only the canonical spelling parses.
    subject_a = letter_text(subject="a")
    assert "SUBJECT_B64:YQ==" in subject_a
    assert err(HumanPrivateLetter.parse,
               subject_a.replace("SUBJECT_B64:YQ==", "SUBJECT_B64:YR==", 1)) == "HLET1_NONCANONICAL"


def test_hlet1_rejects_bad_base64_and_bad_utf8():
    text = letter_text()
    assert err(HumanPrivateLetter.parse,
               text.replace("SUBJECT_B64:", "SUBJECT_B64:!", 1)) == "HLET1_BAD_BASE64"
    not_utf8 = base64.b64encode(b"\xff\xfe").decode("ascii")
    assert err(HumanPrivateLetter.parse,
               text.replace(f"SUBJECT_B64:{b64('queue note')}",
                            f"SUBJECT_B64:{not_utf8}", 1)) == "HLET1_BAD_UTF8"


def test_hlet1_rejects_bounds_and_empty_text():
    assert err(HumanPrivateLetter, to_human=human_id(PRIMARY.public_key()), created=T,
               subject="", body="x") == "HLET1_EMPTY_SUBJECT"
    assert err(HumanPrivateLetter, to_human=human_id(PRIMARY.public_key()), created=T,
               subject="x", body="") == "HLET1_EMPTY_BODY"
    assert err(HumanPrivateLetter, to_human=human_id(PRIMARY.public_key()), created=T,
               subject="s" * 257, body="x") == "HLET1_SUBJECT_OVERSIZE"
    assert err(HumanPrivateLetter, to_human=human_id(PRIMARY.public_key()), created=T,
               subject="s", body="b" * 65537) == "HLET1_BODY_OVERSIZE"


def test_hlet1_parse_refuses_oversized_body_before_building():
    oversized = letter_text(body="b" * 70000)
    assert err(HumanPrivateLetter.parse, oversized.encode("utf-8")) == "HLET1_BODY_OVERSIZE"


def test_hlet1_rejects_bad_identity_and_timestamp():
    assert err(HumanPrivateLetter, to_human="human-id:sha256:" + "A" * 64, created=T,
               subject="s", body="b") == "HLET1_BAD_TO_HUMAN"
    assert err(HumanPrivateLetter, to_human="name:alice", created=T,
               subject="s", body="b") == "HLET1_BAD_TO_HUMAN"
    assert err(HumanPrivateLetter, to_human=human_id(PRIMARY.public_key()),
               created="2026-13-40T99:00:00Z", subject="s", body="b") == "HLET1_BAD_CREATED"


# --------------------------------------------------------------------
# human identity and recipient
# --------------------------------------------------------------------


def test_human_id_is_spki_sha256():
    expected = HUMAN_ID_PREFIX + hashlib.sha256(spki(PRIMARY.public_key())).hexdigest()
    assert human_id(PRIMARY.public_key()) == expected
    assert human_id(RECOVERY.public_key()) != human_id(PRIMARY.public_key())


def test_human_id_requires_p256():
    assert err(human_id, x25519.X25519PrivateKey.generate().public_key()) == "NOT_P256_PUBLIC_KEY"


def test_human_recipient_verifies_identity_against_key():
    ident = human_id(PRIMARY.public_key())
    recipient = HumanRecipient(human_id=ident, primary_public_key=PRIMARY.public_key())
    assert recipient.human_id == ident
    assert recipient.recovery_public_key is None
    assert err(HumanRecipient, human_id=OTHER, primary_public_key=PRIMARY.public_key()) \
        == "HUMAN_ID_MISMATCH"


def test_human_recipient_recovery_must_be_distinct_p256():
    ident = human_id(PRIMARY.public_key())
    with_recovery = HumanRecipient(
        human_id=ident, primary_public_key=PRIMARY.public_key(),
        recovery_public_key=RECOVERY.public_key())
    assert with_recovery.recovery_public_key is not None
    assert err(HumanRecipient, human_id=ident, primary_public_key=PRIMARY.public_key(),
               recovery_public_key=PRIMARY.public_key()) == "RECOVERY_KEY_NOT_DISTINCT"
    assert err(HumanRecipient, human_id=ident, primary_public_key=PRIMARY.public_key(),
               recovery_public_key=x25519.X25519PrivateKey.generate().public_key()) \
        == "NOT_P256_PUBLIC_KEY"
