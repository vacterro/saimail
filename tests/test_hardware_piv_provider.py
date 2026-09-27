"""T-56 Target B — PivP256Provider: identity binding, one explicit ECDH
session, honest PIN/touch handling, and zero private-key exposure (D-043).

Every ECDH result in these tests is real P-256 cryptography: the fake backend
holds a software private key and performs the operation itself, so no test can
pass because a constant was returned. The hardware path stays optional; this
file never imports a vendor library.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_public_key,
)

from sailang import SailangError
from saimail import envelope
from saimail.hardware_piv import (
    COMPATIBLE_WEAK_POLICY,
    HARDENED,
    HARDWARE_ERROR_CODES,
    UNKNOWN_POLICY,
    PivBackendError,
    PivDevice,
    PivP256Provider,
    PivSlotInfo,
)
from saimail.sailetter import (
    MODE_RECOVERABLE,
    MODE_STRICT,
    SLOT_RECOVERY,
    HumanPrivateLetter,
    HumanPrivateStore,
    HumanRecipient,
    SoftwareP256Provider,
    human_id,
    open_human_private,
    seal_human_private,
)

T = "2026-09-19T10:00:00Z"
SEAT = "A17"
SENDER = Ed25519PrivateKey.generate()

TOKEN_KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())
RECOVERY_KEY = ec.generate_private_key(ec.SECP256R1())
P384_KEY = ec.generate_private_key(ec.SECP384R1())
RSA_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

PRIMARY_SLOT = "9D"
RECOVERY_SLOT = "82"


def err(fn, *args, **kwargs):
    with pytest.raises(SailangError) as caught:
        fn(*args, **kwargs)
    return caught.value.code


def spki(private_key) -> bytes:
    return private_key.public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo)


@dataclass
class SlotSpec:
    key: object = None
    key_type: str = "ECCP256"
    pin_policy: str = "ONCE"
    touch_policy: str = "ALWAYS"
    origin: str = "GENERATED"


def slot(private_key, *, key_type: str = "ECCP256", pin_policy: str = "ONCE",
         touch_policy: str = "ALWAYS") -> SlotSpec:
    return SlotSpec(key=private_key, key_type=key_type,
                    pin_policy=pin_policy, touch_policy=touch_policy)


class FakeSession:
    def __init__(self, backend, device):
        self.backend = backend
        self.device = device
        self.calls = backend.calls
        self.pin_ok = False
        self.closed = False

    @property
    def firmware(self):
        return self.device.firmware

    @property
    def serial(self):
        return self.device.serial

    def _spec(self, slot_name):
        return self.backend.slots[self.device.identifier].get(slot_name)

    def read_slot(self, slot_name) -> PivSlotInfo:
        self.calls["read_slot"] += 1
        spec = self._spec(slot_name)
        if spec is None or spec.key is None:
            return PivSlotInfo(slot=slot_name, empty=True)
        return PivSlotInfo(
            slot=slot_name,
            empty=False,
            key_type=spec.key_type,
            public_key_spki=spki(spec.key),
            pin_policy=spec.pin_policy,
            touch_policy=spec.touch_policy,
            origin=spec.origin,
        )

    def pin_required(self, slot_name) -> bool:
        self.calls["pin_required"] += 1
        spec = self._spec(slot_name)
        if spec is None or spec.key is None:
            return False
        return spec.pin_policy != "NEVER"

    def verify_pin(self, pin: str) -> None:
        self.calls["verify_pin"] += 1
        if pin != self.backend.pin:
            raise PivBackendError("HARDWARE_PIN_INVALID",
                                  "PIN verification failed", retries_remaining=2)
        self.pin_ok = True

    def exchange(self, slot_name, ephemeral_public_key_spki: bytes) -> bytes:
        self.calls["exchange"] += 1
        spec = self._spec(slot_name)
        if spec is None or spec.key is None:
            raise PivBackendError("HARDWARE_SLOT_EMPTY",
                                  "the selected slot holds no key")
        if self.backend.fail_exchange is not None:
            raise PivBackendError(self.backend.fail_exchange,
                                  "the device reported this outcome")
        if spec.pin_policy != "NEVER" and not self.pin_ok:
            raise PivBackendError("HARDWARE_PIN_REQUIRED",
                                  "the device requires PIN verification")
        peer = load_der_public_key(ephemeral_public_key_spki)
        return spec.key.exchange(ec.ECDH(), peer)

    def close(self) -> None:
        self.calls["close"] += 1
        self.closed = True


class FakeBackend:
    def __init__(self, *, pin: str = "123456"):
        self.pin = pin
        self.fail_exchange = None
        self.devices = {}
        self.slots = {}
        self.calls = Counter()
        self.sessions = []

    def add_device(self, identifier: str, slots: dict, *, serial: str = "SN-0001",
                   firmware: str = "5.4.3", name: str = "") -> None:
        self.devices[identifier] = PivDevice(
            identifier=identifier, name=name or identifier,
            serial=serial, firmware=firmware)
        self.slots[identifier] = dict(slots)

    def list_devices(self):
        self.calls["list_devices"] += 1
        return tuple(self.devices.values())

    def open(self, device):
        self.calls["open"] += 1
        session = FakeSession(self, device)
        self.sessions.append(session)
        return session


class StaticPin:
    def __init__(self, pin: str, *, require_bytes: bool = False):
        self.pin = pin
        self.require_bytes = require_bytes
        self.calls = 0

    def get_pin(self) -> str:
        self.calls += 1
        return b"not-a-str" if self.require_bytes else self.pin


def backend(*, pin="123456", fail_exchange=None, slot_name=PRIMARY_SLOT,
            key=TOKEN_KEY, pin_policy="ONCE", touch_policy="ALWAYS",
            key_type="ECCP256") -> FakeBackend:
    result = FakeBackend(pin=pin)
    result.fail_exchange = fail_exchange
    result.add_device("fake-1", {
        slot_name: slot(key, key_type=key_type, pin_policy=pin_policy,
                        touch_policy=touch_policy),
    })
    return result


def provider(fake: FakeBackend, *, pin=None, slot_name=PRIMARY_SLOT, **changes):
    pin_source = None if pin is None else StaticPin(pin)
    return PivP256Provider(fake, slot=slot_name, device="fake-1",
                           pin_provider=pin_source, **changes)


def registry(*keys) -> envelope.KeyRegistry:
    return envelope.KeyRegistry({SEAT: [key.public_key() for key in keys]})


def recipient(key, recovery_key=None) -> HumanRecipient:
    kwargs = dict(human_id=human_id(key.public_key()),
                  primary_public_key=key.public_key())
    if recovery_key is not None:
        kwargs["recovery_public_key"] = recovery_key.public_key()
    return HumanRecipient(**kwargs)


def sealed(key, *, mode=MODE_STRICT, recovery_key=None) -> str:
    item = HumanPrivateLetter(to_human=human_id(key.public_key()), created=T,
                              subject="hardware note", body="one line")
    return seal_human_private(
        item, sender_private_key=SENDER, sender_seat=SEAT,
        recipient=recipient(key, recovery_key), mode=mode)


def tamper_signature(text: str) -> str:
    out = []
    for line in text.rstrip("\n").split("\n"):
        if line.startswith("SIG:ed25519:"):
            hexpart = line[len("SIG:ed25519:"):]
            flipped = ("0" if hexpart[0] != "0" else "1") + hexpart[1:]
            line = "SIG:ed25519:" + flipped
        out.append(line)
    return "\n".join(out) + "\n"


def ephemeral_spki() -> bytes:
    return spki(ec.generate_private_key(ec.SECP256R1()))


# --------------------------------------------------------------------
# identity binding (B12 controls 1-5, 19)
# --------------------------------------------------------------------


def test_p256_slot_yields_the_key_fingerprint():
    fake = backend()
    piv = provider(fake)
    assert piv.human_id == human_id(TOKEN_KEY.public_key())
    assert piv.public_key_spki == spki(TOKEN_KEY)


def test_rsa_slot_is_refused_before_any_private_operation():
    fake = backend(slot_name="9A", key=RSA_KEY, key_type="RSA2048")
    assert err(provider, fake, slot_name="9A") == "HARDWARE_ALGORITHM_UNSUPPORTED"
    assert fake.calls["exchange"] == 0
    assert fake.calls["verify_pin"] == 0


def test_p384_slot_is_refused():
    fake = backend(slot_name="9C", key=P384_KEY, key_type="ECCP384")
    assert err(provider, fake, slot_name="9C") == "HARDWARE_ALGORITHM_UNSUPPORTED"
    assert fake.calls["exchange"] == 0


def test_empty_slot_is_refused():
    fake = FakeBackend()
    fake.add_device("fake-1", {})
    assert err(provider, fake, slot_name="9D") == "HARDWARE_SLOT_EMPTY"
    assert fake.calls["exchange"] == 0


def test_expected_human_id_mismatch_is_refused():
    fake = backend()
    assert err(provider, fake, expected_human_id=human_id(OTHER_KEY.public_key())) \
        == "HARDWARE_IDENTITY_MISMATCH"
    assert fake.calls["exchange"] == 0


def test_hardware_metadata_never_enters_henv1():
    container = sealed(TOKEN_KEY).encode("utf-8")
    assert b"SN-0001" not in container
    assert b"fake-1" not in container
    assert b"5.4.3" not in container
    assert human_id(TOKEN_KEY.public_key()).encode("ascii") in container


# --------------------------------------------------------------------
# provider surface and ECDH equivalence (controls 6, 7)
# --------------------------------------------------------------------


def test_provider_exposes_no_raw_private_key_api():
    piv = provider(backend())
    for forbidden in ("private_key", "private_numbers", "private_bytes",
                      "key_material", "_private_key"):
        assert not hasattr(piv, forbidden)


def test_exchange_matches_the_software_reference_provider():
    fake = backend()
    piv = provider(fake, pin="123456")
    peer = ephemeral_spki()
    reference = software_shared_secret(TOKEN_KEY, peer)
    assert piv.exchange(peer) == reference
    assert len(reference) == 32


def software_shared_secret(private_key, peer_spki: bytes) -> bytes:
    return private_key.exchange(ec.ECDH(), load_der_public_key(peer_spki))


# --------------------------------------------------------------------
# HENV1 integration through the existing seam (controls 8-10)
# --------------------------------------------------------------------


def test_strict_henv1_opens_through_the_hardware_provider():
    piv = provider(backend(), pin="123456")
    opened = open_human_private(sealed(TOKEN_KEY), provider=piv,
                                sender_registry=registry(SENDER))
    assert opened.letter.body == "one line"


def test_recoverable_henv1_opens_through_a_recovery_slot_provider():
    fake = FakeBackend()
    fake.add_device("fake-1", {
        PRIMARY_SLOT: slot(TOKEN_KEY),
        RECOVERY_SLOT: slot(RECOVERY_KEY, pin_policy="NEVER"),
    })
    container = sealed(TOKEN_KEY, mode=MODE_RECOVERABLE, recovery_key=RECOVERY_KEY)
    piv = provider(fake, slot_name=RECOVERY_SLOT)
    opened = open_human_private(container, provider=piv,
                                sender_registry=registry(SENDER))
    assert opened.slot == SLOT_RECOVERY


def test_store_open_accepts_the_hardware_provider(tmp_path):
    piv = provider(backend(), pin="123456")
    store = HumanPrivateStore(tmp_path, human_id=human_id(TOKEN_KEY.public_key()),
                              sender_registry=registry(SENDER))
    delivered = store.deliver(sealed(TOKEN_KEY))
    opened = store.open(delivered.letter_id, provider=piv)
    assert opened.letter.body == "one line"


def test_unrelated_provider_never_reaches_the_hardware():
    fake = backend(key=OTHER_KEY)
    piv = provider(fake, pin="123456")
    assert err(open_human_private, sealed(TOKEN_KEY), provider=piv,
               sender_registry=registry(SENDER)) == "RECIPIENT_KEY_UNRELATED"
    assert fake.calls["exchange"] == 0
    assert fake.calls["verify_pin"] == 0


def test_software_provider_still_opens_the_same_container():
    container = sealed(TOKEN_KEY)
    opened = open_human_private(container, provider=SoftwareP256Provider(TOKEN_KEY),
                                sender_registry=registry(SENDER))
    assert opened.letter.body == "one line"


# --------------------------------------------------------------------
# PIN discipline (controls 11-14, 16, 17)
# --------------------------------------------------------------------


def test_pin_is_requested_only_when_the_private_operation_begins():
    fake = backend()
    pin = StaticPin("123456")
    piv = PivP256Provider(fake, slot=PRIMARY_SLOT, device="fake-1", pin_provider=pin)
    assert fake.calls["verify_pin"] == 0
    assert pin.calls == 0
    piv.exchange(ephemeral_spki())
    assert fake.calls["verify_pin"] == 1
    assert pin.calls == 1


def test_never_policy_slot_needs_no_pin_source():
    fake = backend(pin_policy="NEVER")
    piv = provider(fake)
    assert piv.interaction_policy == COMPATIBLE_WEAK_POLICY
    piv.exchange(ephemeral_spki())
    assert fake.calls["verify_pin"] == 0


def test_missing_pin_source_is_a_named_refusal():
    fake = backend()
    piv = provider(fake)
    assert err(piv.exchange, ephemeral_spki()) == "HARDWARE_PIN_REQUIRED"
    assert fake.calls["exchange"] == 0


def test_invalid_sender_signature_reaches_zero_hardware_operations():
    fake = backend()
    piv = provider(fake, pin="123456")
    tampered = tamper_signature(sealed(TOKEN_KEY))
    assert err(open_human_private, tampered, provider=piv,
               sender_registry=registry(SENDER)) == "SIGNATURE_INVALID"
    assert fake.calls["exchange"] == 0
    assert fake.calls["verify_pin"] == 0
    assert fake.calls["pin_required"] == 0


def test_pin_invalid_is_preserved_with_retries_and_a_single_attempt():
    fake = backend()
    pin = StaticPin("999999")
    piv = PivP256Provider(fake, slot=PRIMARY_SLOT, device="fake-1", pin_provider=pin)
    with pytest.raises(SailangError) as caught:
        piv.exchange(ephemeral_spki())
    assert caught.value.code == "HARDWARE_PIN_INVALID"
    assert "2 attempt(s) remaining" in caught.value.detail
    assert pin.calls == 1
    assert fake.calls["verify_pin"] == 1
    assert fake.calls["exchange"] == 0


def test_foreign_pin_source_result_is_refused_without_guessing():
    fake = backend()
    piv = provider(fake, pin="123456")
    piv._pin_provider = StaticPin("123456", require_bytes=True)
    assert err(piv.exchange, ephemeral_spki()) == "HARDWARE_PIN_REQUIRED"
    assert fake.calls["verify_pin"] == 0


def test_touch_required_and_timeout_results_are_preserved():
    for code in ("HARDWARE_TOUCH_REQUIRED", "HARDWARE_TOUCH_TIMEOUT"):
        fake = backend(fail_exchange=code, pin_policy="NEVER")
        piv = provider(fake)
        assert err(piv.exchange, ephemeral_spki()) == code


def test_session_closes_after_success_and_after_failure():
    fake = backend(pin="123456")
    piv = provider(fake, pin="123456")
    piv.exchange(ephemeral_spki())
    assert fake.calls["open"] == fake.calls["close"]
    assert all(session.closed for session in fake.sessions)

    bad = backend(fail_exchange="HARDWARE_TOUCH_TIMEOUT", pin_policy="NEVER")
    piv_bad = provider(bad)
    assert err(piv_bad.exchange, ephemeral_spki()) == "HARDWARE_TOUCH_TIMEOUT"
    assert bad.calls["open"] == bad.calls["close"]
    assert all(session.closed for session in bad.sessions)


def test_bad_ephemeral_key_refuses_before_any_session():
    fake = backend(pin_policy="NEVER")
    piv = provider(fake)
    assert err(piv.exchange, b"not-der") == "BAD_EPHEMERAL_KEY"
    assert fake.calls["open"] == 1  # construction only


# --------------------------------------------------------------------
# selection and policy honesty (C3/C5, B5)
# --------------------------------------------------------------------


def test_two_devices_are_never_selected_silently():
    fake = FakeBackend()
    fake.add_device("fake-1", {PRIMARY_SLOT: slot(TOKEN_KEY)})
    fake.add_device("fake-2", {PRIMARY_SLOT: slot(OTHER_KEY)})
    assert err(PivP256Provider, fake, slot=PRIMARY_SLOT) == "HARDWARE_MULTIPLE_MATCHES"
    piv = PivP256Provider(fake, slot=PRIMARY_SLOT, device="fake-2")
    assert piv.human_id == human_id(OTHER_KEY.public_key())


def test_slot_is_an_explicit_required_choice():
    fake = backend()
    with pytest.raises(TypeError):
        PivP256Provider(fake, device="fake-1")


def test_require_hardened_refuses_weak_and_unknown_policies():
    weak = backend(pin_policy="NEVER")
    assert err(provider, weak, require_hardened=True) == "HARDWARE_POLICY_WEAK"

    unknown = FakeBackend()
    unknown.add_device("fake-1", {
        PRIMARY_SLOT: SlotSpec(key=TOKEN_KEY, pin_policy="UNKNOWN",
                               touch_policy="UNKNOWN"),
    })
    assert err(provider, unknown, require_hardened=True) == "HARDWARE_POLICY_UNKNOWN"

    hardened = backend()
    piv = provider(hardened, require_hardened=True)
    assert piv.interaction_policy == HARDENED


def test_refusal_codes_are_a_closed_vocabulary():
    for code in ("HARDWARE_TOUCH_REQUIRED", "HARDWARE_PIN_INVALID",
                 "HARDWARE_IDENTITY_MISMATCH", "HARDWARE_POLICY_WEAK",
                 "HARDWARE_POLICY_UNKNOWN"):
        assert code in HARDWARE_ERROR_CODES
    with pytest.raises(ValueError):
        PivBackendError("NOT_A_HARDWARE_CODE")
