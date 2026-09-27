"""T-56 Target C — read-only discovery, policy honesty, native error mapping,
and the operator CLI (D-043 / spec/06-HUMAN-HARDWARE-v0.md).

The mutation guard is structural: the backend and session interfaces expose no
operation that writes, and discovery is proven to call only reads, never a PIN
verification and never ECDH.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_der_public_key,
)

from sailang import SailangError
from saimail.hardware_piv import (
    COMPATIBLE_WEAK_POLICY,
    HARDENED,
    HARDWARE_ERROR_CODES,
    UNKNOWN_POLICY,
    PivBackend,
    PivBackendError,
    PivDevice,
    PivP256Provider,
    PivSessionHandle,
    PivSlotInfo,
    YubicoPivBackend,
    _native_failure,
    classify_interaction_policy,
    inspect_devices,
    main,
    normalize_slot,
)
from saimail.sailetter import human_id

KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())


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


class FakeSession:
    def __init__(self, backend, device):
        self.backend = backend
        self.device = device
        self.calls = backend.calls
        self.method_calls = []
        self.closed = False
        self.pin_ok = False

    @property
    def firmware(self):
        return self.device.firmware

    @property
    def serial(self):
        return self.device.serial

    def read_slot(self, slot_name) -> PivSlotInfo:
        self.method_calls.append("read_slot")
        self.calls["read_slot"] += 1
        spec = self.backend.slots[self.device.identifier].get(slot_name)
        if spec is None or spec.key is None:
            return PivSlotInfo(slot=slot_name, empty=True)
        return PivSlotInfo(slot=slot_name, empty=False, key_type=spec.key_type,
                           public_key_spki=spki(spec.key), pin_policy=spec.pin_policy,
                           touch_policy=spec.touch_policy, origin=spec.origin)

    def pin_required(self, slot_name) -> bool:
        self.method_calls.append("pin_required")
        self.calls["pin_required"] += 1
        spec = self.backend.slots[self.device.identifier].get(slot_name)
        return bool(spec and spec.key is not None and spec.pin_policy != "NEVER")

    def verify_pin(self, pin: str) -> None:
        self.method_calls.append("verify_pin")
        self.calls["verify_pin"] += 1
        if pin != self.backend.pin:
            raise PivBackendError("HARDWARE_PIN_INVALID",
                                  "PIN verification failed", retries_remaining=2)
        self.pin_ok = True

    def exchange(self, slot_name, ephemeral_public_key_spki: bytes) -> bytes:
        self.method_calls.append("exchange")
        self.calls["exchange"] += 1
        peer = load_der_public_key(ephemeral_public_key_spki)
        return self.backend.slots[self.device.identifier][slot_name].key.exchange(
            ec.ECDH(), peer)

    def close(self) -> None:
        self.method_calls.append("close")
        self.calls["close"] += 1
        self.closed = True


class FakeBackend:
    def __init__(self):
        self.devices = {}
        self.slots = {}
        self.calls = Counter()
        self.sessions = []
        self.pin = "123456"

    def add_device(self, identifier: str, slots: dict, *, serial: str = "SN-0001",
                   firmware: str = "5.4.3") -> None:
        self.devices[identifier] = PivDevice(identifier=identifier, name=identifier,
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


def fake_one() -> FakeBackend:
    backend = FakeBackend()
    backend.add_device("fake-1", {
        "9D": SlotSpec(key=KEY, pin_policy="ONCE", touch_policy="ALWAYS"),
        "82": SlotSpec(),
    })
    return backend


# --------------------------------------------------------------------
# policy classification (B5 / A5)
# --------------------------------------------------------------------


@pytest.mark.parametrize("pin,touch,expected", [
    ("ONCE", "ALWAYS", HARDENED),
    ("ALWAYS", "ALWAYS", HARDENED),
    ("NEVER", "ALWAYS", COMPATIBLE_WEAK_POLICY),
    ("ONCE", "NEVER", COMPATIBLE_WEAK_POLICY),
    ("DEFAULT", "DEFAULT", COMPATIBLE_WEAK_POLICY),
    ("MATCH_ONCE", "CACHED", COMPATIBLE_WEAK_POLICY),
    ("UNKNOWN", "ALWAYS", UNKNOWN_POLICY),
    ("ONCE", "UNKNOWN", UNKNOWN_POLICY),
])
def test_policy_classification_is_honest(pin, touch, expected):
    assert classify_interaction_policy(pin, touch) == expected


def test_weak_and_unknown_are_never_hardened():
    for pin, touch in (("NEVER", "NEVER"), ("DEFAULT", "DEFAULT"),
                       ("UNKNOWN", "UNKNOWN")):
        assert classify_interaction_policy(pin, touch) != HARDENED


# --------------------------------------------------------------------
# discovery is strictly read-only (B12 controls 12, C1)
# --------------------------------------------------------------------


def test_discovery_reads_only_and_never_pins_or_does_ecdh():
    backend = fake_one()
    reports = inspect_devices(backend, slots=("9D", "82"))
    assert len(reports) == 1
    assert backend.calls["pin_required"] == 0
    assert backend.calls["verify_pin"] == 0
    assert backend.calls["exchange"] == 0
    for session in backend.sessions:
        assert set(session.method_calls) <= {"read_slot", "close"}
        assert session.closed


def test_discovery_reports_device_and_slot_metadata():
    backend = fake_one()
    (report,) = inspect_devices(backend, slots=("9D", "82"))
    assert report.device.identifier == "fake-1"
    assert report.serial == "SN-0001"
    assert report.firmware == "5.4.3"
    keyed, empty = report.slots
    assert keyed.slot == "9D"
    assert keyed.human_id == human_id(KEY.public_key())
    assert keyed.interaction_policy == HARDENED
    assert keyed.origin == "GENERATED"
    assert empty.slot == "82"
    assert empty.empty is True
    assert empty.human_id is None


def test_discovery_preserves_uncertainty():
    backend = FakeBackend()
    backend.add_device("fake-1", {
        "9D": SlotSpec(key=KEY, pin_policy="UNKNOWN", touch_policy="UNKNOWN"),
    })
    (report,) = inspect_devices(backend, slots=("9D",))
    assert report.slots[0].interaction_policy == UNKNOWN_POLICY


def test_multiple_devices_are_all_reported_never_silently_picked():
    backend = FakeBackend()
    backend.add_device("fake-1", {"9D": SlotSpec(key=KEY)})
    backend.add_device("fake-2", {"9D": SlotSpec(key=OTHER_KEY)}, serial="SN-0001")
    assert len(inspect_devices(backend, slots=("9D",))) == 2
    selected = inspect_devices(backend, slots=("9D",), device="fake-2")
    assert len(selected) == 1
    with pytest.raises(SailangError) as caught:
        inspect_devices(backend, slots=("9D",), device="SN-0001")
    assert caught.value.code == "HARDWARE_MULTIPLE_MATCHES"
    with pytest.raises(SailangError) as caught:
        inspect_devices(backend, slots=("9D",), device="fake")
    assert caught.value.code == "HARDWARE_NOT_FOUND"


def test_slot_names_must_be_in_the_known_set():
    assert normalize_slot("9d") == "9D"
    assert normalize_slot(0x82) == "82"
    assert normalize_slot("0x9C") == "9C"
    with pytest.raises(SailangError) as caught:
        normalize_slot("F9")
    assert caught.value.code == "BAD_HARDWARE_SLOT"


# --------------------------------------------------------------------
# structural mutation guard (red controls 5, 8, 9)
# --------------------------------------------------------------------


def test_no_mutating_operation_exists_on_the_public_surface():
    import saimail.hardware_piv as module

    verbs = ("generate", "import", "delete", "reset", "write", "set_", "put_",
             "change_", "provision", "register", "overwrite", "erase",
             "unblock", "swap", "restore", "initialize", "create", "move")
    for surface in (PivBackend, PivSessionHandle, PivP256Provider, YubicoPivBackend):
        for name in dir(surface):
            if name.startswith("_"):
                continue
            assert not any(verb in name.lower() for verb in verbs), \
                f"{surface.__name__}.{name} looks like a token mutation"
    for name in dir(module):
        if name.startswith("_"):
            continue
        assert not any(verb in name.lower() for verb in verbs), \
            f"saimail.hardware_piv.{name} looks like a token mutation"


def test_backend_interface_is_exactly_read_operations():
    backend_api = {name for name in dir(PivBackend) if not name.startswith("_")}
    session_api = {name for name in dir(PivSessionHandle) if not name.startswith("_")}
    assert backend_api == {"list_devices", "open"}
    assert session_api == {"firmware", "serial", "read_slot", "pin_required",
                           "verify_pin", "exchange", "close"}


# --------------------------------------------------------------------
# native failure normalization
# --------------------------------------------------------------------


def native_instance(name: str, message: str = "raw SECRET-APDU 123456", **attrs):
    cls = type(name, (Exception,), {})
    instance = cls(message)
    for key, value in attrs.items():
        setattr(instance, key, value)
    return instance


@pytest.mark.parametrize("error,touch,code", [
    (native_instance("InvalidPinError", attempts_remaining=2), False, "HARDWARE_PIN_INVALID"),
    (native_instance("NoCardException"), False, "HARDWARE_NOT_FOUND"),
    (native_instance("CardConnectionException"), False, "HARDWARE_OPERATION_FAILED"),
    (native_instance("TimeoutError"), True, "HARDWARE_TOUCH_TIMEOUT"),
    (native_instance("TimeoutError"), False, "HARDWARE_OPERATION_FAILED"),
    (native_instance("ApplicationNotAvailableError"), False, "HARDWARE_ALGORITHM_UNSUPPORTED"),
    (native_instance("NotSupportedError"), False, "HARDWARE_ALGORITHM_UNSUPPORTED"),
    (native_instance("ApduError", sw=0x6A82), False, "HARDWARE_SLOT_EMPTY"),
    (native_instance("ApduError", sw=0x6982), False, "HARDWARE_PIN_REQUIRED"),
    (native_instance("ApduError", sw=0x6983), False, "HARDWARE_PIN_BLOCKED"),
    (native_instance("ApduError", sw=0x6A80), False, "HARDWARE_ALGORITHM_UNSUPPORTED"),
    (native_instance("ApduError", sw=0x6985), True, "HARDWARE_TOUCH_TIMEOUT"),
    (native_instance("ApduError", sw=0x6F00), False, "HARDWARE_OPERATION_FAILED"),
    (native_instance("SomethingUnknown"), False, "HARDWARE_OPERATION_FAILED"),
])
def test_native_failures_map_into_the_closed_vocabulary(error, touch, code):
    mapped_code, detail, _ = _native_failure(error, touch_expected=touch)
    assert mapped_code == code
    assert mapped_code in HARDWARE_ERROR_CODES
    assert "SECRET-APDU" not in detail
    assert "123456" not in detail


def test_apdu_retry_counters_become_pin_invalid_with_remaining_attempts():
    code, _detail, retries = _native_failure(
        native_instance("ApduError", sw=0x63C3), touch_expected=False)
    assert code == "HARDWARE_PIN_INVALID"
    assert retries == 3
    code, _detail, retries = _native_failure(
        native_instance("InvalidPinError", attempts_remaining=4), touch_expected=False)
    assert (code, retries) == ("HARDWARE_PIN_INVALID", 4)


def test_cancelled_connection_is_named_as_cancelled():
    cancelled = native_instance("CardConnectionException",
                                "The operation was cancelled by the user")
    assert _native_failure(cancelled, touch_expected=True)[0] \
        == "HARDWARE_OPERATION_CANCELLED"


def test_production_backend_degrades_by_name_without_the_extra():
    backend = YubicoPivBackend()
    try:
        devices = backend.list_devices()
    except PivBackendError as error:
        assert error.code == "HARDWARE_PROVIDER_UNAVAILABLE"
        return
    assert all(isinstance(device, PivDevice) for device in devices)


# --------------------------------------------------------------------
# operator CLI
# --------------------------------------------------------------------


class StaticPin:
    def __init__(self, pin: str):
        self.pin = pin
        self.calls = 0

    def get_pin(self) -> str:
        self.calls += 1
        return self.pin


def test_cli_inspect_reports_read_only(capsys):
    backend = fake_one()
    assert main(["inspect", "--slot", "9D"], backend=backend) == 0
    out = capsys.readouterr().out
    assert "REAL_HARDWARE_INSPECTION: RAN" in out
    assert "HARDENED" in out
    assert human_id(KEY.public_key()) in out
    assert backend.calls["verify_pin"] == 0
    assert backend.calls["exchange"] == 0
    assert "123456" not in out


def test_cli_inspect_without_devices_is_not_run(capsys):
    assert main(["inspect"], backend=FakeBackend()) == 2
    assert "NOT_RUN" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["verify"], ["verify", "--device", "fake-1"],
                                  ["verify", "--slot", "9D"]])
def test_cli_verify_requires_explicit_device_and_slot(argv):
    with pytest.raises(SystemExit) as caught:
        main(argv, backend=fake_one())
    assert caught.value.code == 2


def test_cli_never_accepts_a_pin_option():
    with pytest.raises(SystemExit) as caught:
        main(["verify", "--device", "fake-1", "--slot", "9D", "--pin", "123456"],
             backend=fake_one())
    assert caught.value.code == 2


def test_cli_verify_passes_against_a_weak_policy_without_calling_it_hardened(capsys):
    backend = FakeBackend()
    backend.add_device("fake-1", {
        "82": SlotSpec(key=KEY, pin_policy="NEVER", touch_policy="NEVER"),
    })
    assert main(["verify", "--device", "fake-1", "--slot", "82"], backend=backend) == 0
    out = capsys.readouterr().out
    assert "ECDH: PASS" in out
    assert COMPATIBLE_WEAK_POLICY in out
    assert "POLICY: HARDENED" not in out
    assert backend.calls["verify_pin"] == 0


def test_cli_verify_uses_the_pin_source_and_reports_pin_failure(capsys):
    backend = fake_one()
    assert main(["verify", "--device", "fake-1", "--slot", "9D"],
                backend=backend, pin_provider=StaticPin("123456")) == 0
    assert "ECDH: PASS" in capsys.readouterr().out
    assert backend.calls["verify_pin"] == 1

    failing = fake_one()
    assert main(["verify", "--device", "fake-1", "--slot", "9D"],
                backend=failing, pin_provider=StaticPin("000000")) == 1
    assert "HARDWARE_PIN_INVALID" in capsys.readouterr().out


def test_cli_verify_output_is_exactly_the_safe_projection(capsys):
    backend = fake_one()
    assert main(["verify", "--device", "fake-1", "--slot", "9D"],
                backend=backend, pin_provider=StaticPin("123456")) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "REAL_HARDWARE_ECDH_VERIFY: RAN (non-destructive; one ECDH operation)"
    assert lines[1] == "DEVICE: fake-1"
    assert lines[2] == "SLOT: 9D"
    assert lines[3] == f"HUMAN_ID: {human_id(KEY.public_key())}"
    assert lines[4] == "POLICY: HARDENED"
    assert lines[5] == "ECDH: PASS"
