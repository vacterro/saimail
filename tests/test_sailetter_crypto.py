"""B-001 Target B: HENV1 container crypto, bindings and open order (D-042).

The adversarial controls here mutate one field, re-sign the container with an
accepted sender key, and require the sealed layer to refuse anyway: the AEAD
associated data authenticates the binding the container was created under, so a
relabel is not repaired by a fresh valid signature. Signature verification
always runs before any recipient private-key provider operation.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_public_key,
)

from sailang import SailangError
from saimail import envelope
from saimail.sailetter import (
    CEK_PRIMARY_DOMAIN,
    MODE_RECOVERABLE,
    MODE_STRICT,
    SLOT_PRIMARY,
    SLOT_RECOVERY,
    SIGNATURE_DOMAIN,
    HumanPrivateLetter,
    HumanRecipient,
    OpenedHumanPrivateLetter,
    SoftwareP256Provider,
    VerifiedHENV1,
    human_id,
    letter_id,
    open_human_private,
    parse_henv1,
    payload_aad,
    seal_human_private,
    signature_input,
    verify_sender,
    wrap_aad,
)

T = "2026-09-19T10:00:00Z"
SENDER = Ed25519PrivateKey.generate()
OTHER_SENDER = Ed25519PrivateKey.generate()
SENDER_SEAT = "A17"
OTHER_SEAT = "B03"
PRIMARY = ec.generate_private_key(ec.SECP256R1())
RECOVERY = ec.generate_private_key(ec.SECP256R1())
OTHER_RECIPIENT = ec.generate_private_key(ec.SECP256R1())
ID_PRIMARY = human_id(PRIMARY.public_key())
ID_RECOVERY = human_id(RECOVERY.public_key())
ID_OTHER = human_id(OTHER_RECIPIENT.public_key())


def err(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value.code


def spki_b64(private_key) -> str:
    der = private_key.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(der).decode("ascii")


def letter(**changes) -> HumanPrivateLetter:
    values = dict(to_human=ID_PRIMARY, created=T, subject="queue note", body="one line")
    values.update(changes)
    return HumanPrivateLetter(**values)


def recipient(with_recovery: bool = False, key=PRIMARY, recovery=RECOVERY) -> HumanRecipient:
    kwargs = dict(human_id=human_id(key.public_key()), primary_public_key=key.public_key())
    if with_recovery:
        kwargs["recovery_public_key"] = recovery.public_key()
    return HumanRecipient(**kwargs)


def sealed(*, mode=MODE_STRICT, item=None, recipient_obj=None, sender=SENDER,
           sender_seat=SENDER_SEAT, to=None) -> str:
    item = item or letter(to_human=to or (recipient_obj.human_id if recipient_obj else ID_PRIMARY))
    return seal_human_private(
        item, sender_private_key=sender, sender_seat=sender_seat,
        recipient=recipient_obj or recipient(with_recovery=mode == MODE_RECOVERABLE),
        mode=mode,
    )


def registry(*keys: Ed25519PrivateKey) -> envelope.KeyRegistry:
    table = {}
    for seat, key in ((SENDER_SEAT, SENDER), (OTHER_SEAT, OTHER_SENDER)):
        table.setdefault(seat, [])
        if key in keys:
            table[seat].append(key.public_key())
    return envelope.KeyRegistry(table)


def registry_any() -> envelope.KeyRegistry:
    keys = [SENDER.public_key(), OTHER_SENDER.public_key()]
    return envelope.KeyRegistry({SENDER_SEAT: keys, OTHER_SEAT: keys})


def provider(private_key) -> SoftwareP256Provider:
    return SoftwareP256Provider(private_key)


class CountingProvider:
    def __init__(self, private_key):
        self._inner = SoftwareP256Provider(private_key)
        self.calls = 0

    @property
    def human_id(self) -> str:
        return self._inner.human_id

    def exchange(self, ephemeral_public_key: bytes) -> bytes:
        self.calls += 1
        return self._inner.exchange(ephemeral_public_key)


def with_line(text: str, name: str, value: str) -> str:
    out = []
    for line in text.rstrip("\n").split("\n"):
        out.append(f"{name}:{value}" if line.startswith(name + ":") else line)
    return "\n".join(out) + "\n"


def resign(text: str, key: Ed25519PrivateKey = SENDER) -> str:
    lines = [line for line in text.rstrip("\n").split("\n") if not line.startswith("SIG:")]
    signature = key.sign(SIGNATURE_DOMAIN + ("\n".join(lines) + "\n").encode("utf-8"))
    return "\n".join(lines + [f"SIG:ed25519:{signature.hex()}"]) + "\n"


def flipped_b64(value: str) -> str:
    raw = bytearray(base64.b64decode(value))
    raw[0] ^= 0x01
    return base64.b64encode(bytes(raw)).decode("ascii")


# --------------------------------------------------------------------
# seal / open round trips
# --------------------------------------------------------------------


def test_strict_primary_decrypt_and_letter_identity():
    text = sealed()
    opened = open_human_private(text, provider=provider(PRIMARY), sender_registry=registry(SENDER))
    assert isinstance(opened, OpenedHumanPrivateLetter)
    assert opened.letter == letter()
    assert opened.letter.render() == letter().render()
    assert opened.slot == SLOT_PRIMARY
    parsed = parse_henv1(text)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    assert opened.letter_id == letter_id(parsed) == "sha256:" + digest
    assert parsed.recovery_kid == "NONE"


def test_recoverable_primary_and_recovery_yield_identical_hlet1():
    text = sealed(mode=MODE_RECOVERABLE)
    parsed = parse_henv1(text)
    assert parsed.recovery_kid == ID_RECOVERY
    primary_open = open_human_private(text, provider=provider(PRIMARY),
                                      sender_registry=registry(SENDER))
    recovery_open = open_human_private(text, provider=provider(RECOVERY),
                                       sender_registry=registry(SENDER))
    assert primary_open.slot == SLOT_PRIMARY
    assert recovery_open.slot == SLOT_RECOVERY
    assert primary_open.letter.render() == recovery_open.letter.render() == letter().render()
    assert primary_open.letter_id == recovery_open.letter_id


def test_recovery_mode_requires_a_distinct_supplied_recovery_key():
    assert err(seal_human_private, letter(), sender_private_key=SENDER, sender_seat=SENDER_SEAT,
               recipient=recipient(with_recovery=False), mode=MODE_RECOVERABLE) \
        == "RECOVERY_KEY_REQUIRED"
    assert err(seal_human_private, letter(), sender_private_key=SENDER, sender_seat=SENDER_SEAT,
               recipient=recipient(with_recovery=True), mode=MODE_STRICT) \
        == "RECOVERY_KEY_NOT_ALLOWED"
    assert err(seal_human_private, letter(), sender_private_key=SENDER, sender_seat=SENDER_SEAT,
               recipient=recipient(), mode="IMPLICIT") == "BAD_MODE"
    assert err(seal_human_private, letter(), sender_private_key=SENDER, sender_seat=SENDER_SEAT,
               recipient=recipient(), mode="") == "BAD_MODE"


def test_seal_refuses_letter_recipient_mismatch():
    assert err(seal_human_private, letter(to_human=ID_OTHER), sender_private_key=SENDER,
               sender_seat=SENDER_SEAT, recipient=recipient(), mode=MODE_STRICT) \
        == "LETTER_RECIPIENT_MISMATCH"


def test_strict_refuses_the_recovery_provider():
    text = sealed()
    counting = CountingProvider(RECOVERY)
    assert err(open_human_private, text, provider=counting,
               sender_registry=registry(SENDER)) == "RECIPIENT_KEY_UNRELATED"
    assert counting.calls == 0


# --------------------------------------------------------------------
# parser: structure, cardinality, canonical bytes
# --------------------------------------------------------------------


def test_parser_rejects_noncanonical_and_wrong_version():
    text = sealed()
    assert err(parse_henv1, b"\xef\xbb\xbf" + text.encode("utf-8")) == "HENV1_NONCANONICAL"
    assert err(parse_henv1, text.replace("\n", "\r\n")) == "HENV1_NONCANONICAL"
    assert err(parse_henv1, text[:-1]) == "HENV1_NONCANONICAL"
    assert err(parse_henv1, "HENV2" + text[len("HENV1"):]) == "HENV1_BAD_VERSION"


def test_parser_rejects_duplicate_unknown_and_reordered_fields():
    text = sealed()
    lines = text.rstrip("\n").split("\n")
    duplicate = "\n".join(lines[:3] + [lines[2]] + lines[3:]) + "\n"
    assert err(parse_henv1, duplicate) == "HENV1_DUPLICATE_FIELD"
    unknown = text.replace("PAYLOAD_NONCE:",
                           f"RECOVERY2_EPK:{spki_b64(RECOVERY)}\nPAYLOAD_NONCE:", 1)
    assert err(parse_henv1, unknown) == "HENV1_UNKNOWN_FIELD"
    reordered = "\n".join([lines[0], lines[2], lines[1]] + lines[3:]) + "\n"
    assert err(parse_henv1, reordered) == "HENV1_FIELD_ORDER"


def test_parser_enforces_mode_slot_cardinality():
    strict = sealed()
    recoverable = sealed(mode=MODE_RECOVERABLE)
    assert err(parse_henv1, with_line(strict, "MODE", MODE_RECOVERABLE)) \
        == "HENV1_SLOT_CARDINALITY"
    assert err(parse_henv1, with_line(recoverable, "MODE", MODE_STRICT)) \
        == "HENV1_SLOT_CARDINALITY"
    assert err(parse_henv1, with_line(recoverable, "MODE", "OPPORTUNISTIC")) == "HENV1_BAD_MODE"
    with_third = recoverable.replace(
        "PAYLOAD_NONCE:", f"EXTRA_EPK:{spki_b64(OTHER_RECIPIENT)}\nPAYLOAD_NONCE:", 1)
    assert err(parse_henv1, with_third) == "HENV1_UNKNOWN_FIELD"


def test_parser_rejects_bad_shapes():
    text = sealed()
    assert err(parse_henv1, with_line(text, "FROM", "bad seat!")) == "HENV1_BAD_SEAT"
    assert err(parse_henv1, with_line(text, "FROM_KID", "sha256:" + "A" * 64)) == "HENV1_BAD_KID"
    assert err(parse_henv1, with_line(text, "PRIMARY_EPK", "!!!")) == "HENV1_BAD_BASE64"
    assert err(parse_henv1, with_line(text, "PRIMARY_EPK", base64.b64encode(b"junk").decode())) \
        == "HENV1_BAD_EPK"
    assert err(parse_henv1, with_line(text, "PRIMARY_WRAP_NONCE", "00")) == "HENV1_BAD_NONCE"
    assert err(parse_henv1, with_line(text, "PRIMARY_WRAPPED_CEK",
                                      base64.b64encode(b"short").decode())) \
        == "HENV1_BAD_WRAPPED_CEK"
    assert err(parse_henv1, with_line(text, "SIG", "ed25519:" + "g" * 128)) == "HENV1_BAD_SIGNATURE"
    assert err(parse_henv1, with_line(text, "TO_HUMAN", ID_OTHER)) == "HENV1_IDENTITY_MISMATCH"
    assert err(parse_henv1, 17) == "NON_TEXT_INPUT"


# --------------------------------------------------------------------
# cryptographic binding: mutate one field, re-sign, still refuse
# --------------------------------------------------------------------


def mutated(name: str, value: str, *, mode=MODE_STRICT, signer=SENDER, **kwargs):
    text = sealed(mode=mode, **kwargs)
    return resign(with_line(text, name, value), signer)


def test_changed_from_refused_even_re_signed():
    assert err(open_human_private, mutated("FROM", OTHER_SEAT),
               provider=provider(PRIMARY), sender_registry=registry_any()) == "CEK_UNWRAP_FAILED"


def test_changed_from_kid_refused_even_re_signed():
    other_kid = envelope.fingerprint(OTHER_SENDER.public_key())
    assert err(open_human_private, mutated("FROM_KID", other_kid, signer=OTHER_SENDER),
               provider=provider(PRIMARY), sender_registry=registry_any()) == "CEK_UNWRAP_FAILED"


def test_sender_relabel_and_resign_refused():
    text = sealed()
    text = with_line(text, "FROM", OTHER_SEAT)
    text = with_line(text, "FROM_KID", envelope.fingerprint(OTHER_SENDER.public_key()))
    text = resign(text, OTHER_SENDER)
    assert err(open_human_private, text, provider=provider(PRIMARY),
               sender_registry=registry_any()) == "CEK_UNWRAP_FAILED"


def test_recipient_relabel_to_another_human_refused():
    text = sealed()
    text = with_line(text, "TO_HUMAN", ID_OTHER)
    text = with_line(text, "PRIMARY_KID", ID_OTHER)
    text = resign(text)
    counting = CountingProvider(OTHER_RECIPIENT)
    assert err(open_human_private, text, provider=counting,
               sender_registry=registry(SENDER)) == "CEK_UNWRAP_FAILED"
    assert counting.calls == 1, "the provider ran only after a valid signature"


def test_changed_to_human_or_primary_kid_refused():
    assert err(parse_henv1, with_line(sealed(), "TO_HUMAN", ID_OTHER)) == "HENV1_IDENTITY_MISMATCH"
    assert err(parse_henv1, with_line(sealed(), "PRIMARY_KID", ID_OTHER)) == "HENV1_IDENTITY_MISMATCH"


def test_changed_mode_refused():
    assert err(parse_henv1, with_line(sealed(mode=MODE_RECOVERABLE), "MODE", MODE_STRICT)) \
        == "HENV1_SLOT_CARDINALITY"


def test_changed_recovery_kid_refused():
    # The primary path refuses through the payload binding; a provider that
    # matches the relabelled slot still refuses through the recovery wrap AAD.
    assert err(open_human_private, mutated("RECOVERY_KID", ID_OTHER, mode=MODE_RECOVERABLE),
               provider=provider(PRIMARY), sender_registry=registry(SENDER)) == "PAYLOAD_DECRYPT_FAILED"
    assert err(open_human_private, mutated("RECOVERY_KID", ID_OTHER, mode=MODE_RECOVERABLE),
               provider=provider(OTHER_RECIPIENT), sender_registry=registry(SENDER)) \
        == "CEK_UNWRAP_FAILED"


def test_changed_ephemeral_key_refused():
    assert err(open_human_private, mutated("PRIMARY_EPK", spki_b64(OTHER_RECIPIENT)),
               provider=provider(PRIMARY), sender_registry=registry(SENDER)) == "CEK_UNWRAP_FAILED"


def test_changed_cek_wrap_and_wrap_nonce_refused():
    parsed = parse_henv1(sealed())
    wrapped = base64.b64encode(parsed.primary_wrapped_cek).decode("ascii")
    assert err(open_human_private, mutated("PRIMARY_WRAPPED_CEK", flipped_b64(wrapped)),
               provider=provider(PRIMARY), sender_registry=registry(SENDER)) == "CEK_UNWRAP_FAILED"
    other_nonce = ("00" * 12)
    assert err(open_human_private, mutated("PRIMARY_WRAP_NONCE", other_nonce),
               provider=provider(PRIMARY), sender_registry=registry(SENDER)) == "CEK_UNWRAP_FAILED"


def test_changed_payload_nonce_and_ciphertext_refused():
    parsed = parse_henv1(sealed())
    other_nonce = ("11" * 12)
    assert err(open_human_private, mutated("PAYLOAD_NONCE", other_nonce),
               provider=provider(PRIMARY), sender_registry=registry(SENDER)) == "PAYLOAD_DECRYPT_FAILED"
    assert err(open_human_private, mutated("PAYLOAD_B64", flipped_b64(parsed.payload_b64_text)),
               provider=provider(PRIMARY), sender_registry=registry(SENDER)) == "PAYLOAD_DECRYPT_FAILED"


# --------------------------------------------------------------------
# verify-before-private-operation invariant
# --------------------------------------------------------------------


def test_invalid_signature_performs_zero_provider_operations():
    text = sealed()
    signature = parse_henv1(text).signature
    broken = (int.from_bytes(signature, "big") ^ 1).to_bytes(len(signature), "big").hex()
    counting = CountingProvider(PRIMARY)
    assert err(open_human_private, with_line(text, "SIG", "ed25519:" + broken),
               provider=counting, sender_registry=registry(SENDER)) == "SIGNATURE_INVALID"
    assert counting.calls == 0


def test_unaccepted_sender_performs_zero_provider_operations():
    counting = CountingProvider(PRIMARY)
    assert err(open_human_private, sealed(), provider=counting,
               sender_registry=registry(OTHER_SENDER)) == "UNKNOWN_SENDER_KEY"
    assert counting.calls == 0
    wrong_seat_registry = envelope.KeyRegistry({SENDER_SEAT: [OTHER_SENDER.public_key()]})
    assert err(open_human_private, sealed(), provider=counting,
               sender_registry=wrong_seat_registry) == "SENDER_KEY_NOT_ACCEPTED"
    assert counting.calls == 0


def test_verified_state_is_minted_only_by_verification():
    parsed = parse_henv1(sealed())
    assert err(VerifiedHENV1, parsed=parsed, sender_key=SENDER.public_key()) == "UNVERIFIED_HENV1"
    verified = verify_sender(parsed, registry(SENDER))
    assert verified.parsed is parsed


def test_signature_input_covers_every_line_except_sig():
    parsed = parse_henv1(sealed())
    signed = signature_input(parsed)
    assert signed.startswith(SIGNATURE_DOMAIN)
    SENDER.public_key().verify(parsed.signature, signed)
    tampered = parse_henv1(with_line(sealed(), "PAYLOAD_NONCE", "00" * 12))
    assert err(verify_sender, tampered, registry(SENDER)) == "SIGNATURE_INVALID"


# --------------------------------------------------------------------
# payload binding: inner/outer agreement, opened type-state
# --------------------------------------------------------------------


def rewrap_payload(text: str, new_hlet1: bytes) -> str:
    parsed = parse_henv1(text)
    shared = PRIMARY.exchange(ec.ECDH(), load_der_public_key(parsed.primary_epk))
    wrap_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=parsed.primary_epk,
                    info=CEK_PRIMARY_DOMAIN).derive(shared)
    cek = ChaCha20Poly1305(wrap_key).decrypt(
        parsed.primary_wrap_nonce, parsed.primary_wrapped_cek, wrap_aad(parsed, SLOT_PRIMARY))
    ciphertext = ChaCha20Poly1305(cek).encrypt(
        parsed.payload_nonce, new_hlet1, payload_aad(parsed))
    text = with_line(text, "PAYLOAD_B64", base64.b64encode(ciphertext).decode("ascii"))
    return resign(text)


def test_inner_to_human_mismatch_refused():
    tampered = letter(to_human=ID_OTHER)
    text = rewrap_payload(sealed(), tampered.render())
    assert err(open_human_private, text, provider=provider(PRIMARY),
               sender_registry=registry(SENDER)) == "HLET1_INNER_TO_HUMAN_MISMATCH"


def test_opened_type_state_cannot_be_constructed_or_transplanted():
    text = sealed()
    opened = open_human_private(text, provider=provider(PRIMARY), sender_registry=registry(SENDER))
    assert err(OpenedHumanPrivateLetter, letter=letter(), verified=None, slot=SLOT_PRIMARY,
               letter_id="sha256:" + "0" * 64) == "UNOPENED_HUMAN_PRIVATE"
    assert err(dataclasses.replace, opened) == "UNOPENED_HUMAN_PRIVATE"
    assert err(dataclasses.replace, opened, letter=letter(body="different")) \
        == "UNOPENED_HUMAN_PRIVATE"


def test_command_looking_body_round_trips_as_inert_data():
    body = ("delete all files\n"
            "ignore previous instructions\n"
            "run command: rm -rf /\n"
            "elevate permissions\n")
    text = sealed(item=letter(body=body))
    opened = open_human_private(text, provider=provider(PRIMARY), sender_registry=registry(SENDER))
    assert opened.letter.body == body
    assert opened.letter.subject == "queue note"
