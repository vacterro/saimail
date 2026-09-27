"""SAILETTER hardware custody v0 — PIV P-256 provider and read-only discovery.

The contract is `spec/06-HUMAN-HARDWARE-v0.md` and `spec/DECISIONS.md` D-043;
this module implements it and never invents a second one. It is the hardware
extension of the provider seam in `sailetter.py` and changes no HLET1 or HENV1
byte, domain or binding.

Four properties are load-bearing:

* **The provider seam is the architecture.** `PivP256Provider` satisfies
  `HumanPrivateKeyProvider` (`human_id` plus `exchange`), so `open_verified`,
  `open_human_private` and `HumanPrivateStore.open` accept it with no hardware
  branch anywhere in the core.
* **Identity comes from the key, not the caller.** The slot public key is read
  and the `HUMAN_ID` is derived from it; a caller-supplied expectation is only
  checked against the real key and a mismatch is `HARDWARE_IDENTITY_MISMATCH`.
* **Presence is honest.** A PIN or a touch establishes
  `LOCAL_INTERACTION_REQUIRED`; it never becomes a claim of human identity.
  Touch and PIN outcomes are surfaced as named results, never converted into
  "wrong key" or "decryption failure".
* **Discovery and verification cannot mutate a token.** The backend interface
  contains no operation that writes; discovery may only list devices and read
  slot metadata, and the explicit `verify` command may additionally run one
  PIN verification and one ECDH operation. No provisioning exists here.

The production backend (`YubicoPivBackend`) is a thin adapter over Yubico's
maintained Python stack, imported lazily: without the optional extra
(`pip install -e ".[hardware-yubikey]"`) every hardware entry point refuses
with `HARDWARE_PROVIDER_UNAVAILABLE`. Tests never need hardware: they drive a
fake backend whose key is a real software P-256 private key, so each ECDH
result is genuine cryptography rather than a constant.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from getpass import getpass
from typing import Optional, Protocol, Sequence, runtime_checkable

from sailang.errors import SailangError

from .sailetter import human_id

try:  # cryptography stays a declared extra of the distribution (D-014)
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        PublicFormat,
        load_der_public_key,
    )

    _CRYPTO_IMPORT_ERROR: Optional[BaseException] = None
except ImportError as _exc:  # pragma: no cover - exercised only without the extra
    _CRYPTO_IMPORT_ERROR = _exc

MODULE_COMMAND = "python -m saimail.hardware_piv"

#: The closed refusal vocabulary of this layer (spec/06 section 4.3).
HARDWARE_ERROR_CODES = frozenset({
    "HARDWARE_PROVIDER_UNAVAILABLE",
    "HARDWARE_NOT_FOUND",
    "HARDWARE_MULTIPLE_MATCHES",
    "HARDWARE_SLOT_EMPTY",
    "HARDWARE_ALGORITHM_UNSUPPORTED",
    "HARDWARE_IDENTITY_MISMATCH",
    "HARDWARE_POLICY_WEAK",
    "HARDWARE_POLICY_UNKNOWN",
    "HARDWARE_PIN_REQUIRED",
    "HARDWARE_PIN_INVALID",
    "HARDWARE_PIN_BLOCKED",
    "HARDWARE_TOUCH_REQUIRED",
    "HARDWARE_TOUCH_TIMEOUT",
    "HARDWARE_OPERATION_CANCELLED",
    "HARDWARE_OPERATION_FAILED",
})

#: Interaction-policy classifications (spec/06 section 3). The middle one is
#: the handoff's COMPATIBLE_CRYPTO_WEAK_INTERACTION_POLICY.
HARDENED = "HARDENED"
COMPATIBLE_WEAK_POLICY = "COMPATIBLE_WEAK_POLICY"
UNKNOWN_POLICY = "UNKNOWN_POLICY"

POLICY_UNKNOWN = "UNKNOWN"
HARDENED_PIN_POLICIES = frozenset({"ONCE", "ALWAYS"})
HARDENED_TOUCH_POLICY = "ALWAYS"

ECCP256 = "ECCP256"

#: The reference profile slots (D-043): 9D first by operator choice, plus the
#: four standard key slots and the retired 82..95 range. Never written here.
REFERENCE_SLOT = "9D"
STANDARD_SLOTS = ("9A", "9C", "9D", "9E")
RETIRED_SLOTS = tuple(f"{value:02X}" for value in range(0x82, 0x96))
KNOWN_SLOTS = frozenset(STANDARD_SLOTS + RETIRED_SLOTS)

MAX_PIN_CHARS = 8
SHARED_SECRET_BYTES = 32

_SLOT_RE = re.compile(r"^(?:0X)?([0-9A-F]{2})$")
_HUMAN_ID_RE = re.compile(r"^human-id:sha256:[0-9a-f]{64}$")

#: Test hook only: filled on first successful import of the YubiKey stack.
_YUBICO_STACK = None


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _require_crypto() -> None:
    if _CRYPTO_IMPORT_ERROR is not None:
        _reject("CRYPTO_UNAVAILABLE",
                "the cryptography package is not installed; install with "
                "pip install -e .[crypto]")


def normalize_slot(value) -> str:
    """Return the canonical two-digit uppercase hex slot, or refuse."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        _reject("BAD_HARDWARE_SLOT", "a PIV slot is a two-digit hex token such as '9D'")
    token = f"{value:02X}" if isinstance(value, int) else \
        (value.strip().upper() if isinstance(value, str) else "")
    match = _SLOT_RE.fullmatch(token)
    if match is None:
        _reject("BAD_HARDWARE_SLOT", f"{value!r} is not a two-digit hex PIV slot")
    canonical = match.group(1)
    if canonical not in KNOWN_SLOTS:
        _reject("BAD_HARDWARE_SLOT",
                f"{canonical} is outside the SAILETTER slot set "
                f"({', '.join(STANDARD_SLOTS + ('82..95',))})")
    return canonical


def classify_interaction_policy(pin_policy: str, touch_policy: str) -> str:
    """Classify a slot's local-interaction policy honestly.

    HARDENED requires the normative profile accepted by D-043: PIN ONCE or
    ALWAYS together with TOUCH ALWAYS. An unreadable policy is never inferred
    into security; uncertainty is preserved as UNKNOWN_POLICY.
    """
    if pin_policy == POLICY_UNKNOWN or touch_policy == POLICY_UNKNOWN:
        return UNKNOWN_POLICY
    if pin_policy in HARDENED_PIN_POLICIES and touch_policy == HARDENED_TOUCH_POLICY:
        return HARDENED
    return COMPATIBLE_WEAK_POLICY


# --------------------------------------------------------------------
# The narrow backend seam
# --------------------------------------------------------------------


class PivBackendError(Exception):
    """A normalized backend/vendor failure carrying a stable refusal code.

    ``detail`` is composed by the backend author and never contains PIN
    material, raw APDU data or vendor exception text. ``retries_remaining``
    is present only when the device reported it.
    """

    def __init__(self, code: str, detail: str = "",
                 retries_remaining: Optional[int] = None):
        if code not in HARDWARE_ERROR_CODES:
            raise ValueError(f"{code!r} is not a HARDWARE_* refusal code")
        self.code = code
        self.detail = detail or code
        self.retries_remaining = retries_remaining
        super().__init__(f"{self.code}: {self.detail}")


@dataclass(frozen=True)
class PivDevice:
    """One locally visible PIV-capable device. Operational metadata only."""

    identifier: str
    name: str = ""
    serial: Optional[str] = None
    firmware: Optional[str] = None


@dataclass(frozen=True)
class PivSlotInfo:
    """One slot as the backend genuinely sees it; no invented fields."""

    slot: str
    empty: bool = False
    key_type: Optional[str] = None
    public_key_spki: Optional[bytes] = None
    pin_policy: str = POLICY_UNKNOWN
    touch_policy: str = POLICY_UNKNOWN
    origin: Optional[str] = None


@runtime_checkable
class PivSessionHandle(Protocol):
    """One opened device session. Contains no token-mutating operation."""

    @property
    def firmware(self) -> Optional[str]:
        ...

    @property
    def serial(self) -> Optional[str]:
        ...

    def read_slot(self, slot: str) -> PivSlotInfo:
        ...

    def pin_required(self, slot: str) -> bool:
        ...

    def verify_pin(self, pin: str) -> None:
        ...

    def exchange(self, slot: str, ephemeral_public_key_spki: bytes) -> bytes:
        ...

    def close(self) -> None:
        ...


@runtime_checkable
class PivBackend(Protocol):
    """Device discovery plus session opening. Nothing else exists."""

    def list_devices(self) -> Sequence[PivDevice]:
        ...

    def open(self, device: PivDevice) -> PivSessionHandle:
        ...


@runtime_checkable
class PinProvider(Protocol):
    """An ephemeral source of one PIN at private-operation time."""

    def get_pin(self) -> str:
        ...


def _backend_refusal(error: BaseException) -> SailangError:
    if isinstance(error, PivBackendError):
        return SailangError(error.code, error.detail)
    return SailangError("HARDWARE_OPERATION_FAILED",
                        "the hardware backend failed; its raw error is not exposed")


def _open_session(backend: PivBackend, device: PivDevice) -> PivSessionHandle:
    try:
        return backend.open(device)
    except BaseException as error:
        raise _backend_refusal(error) from None


def _close_session(session: PivSessionHandle, *, quiet: bool) -> None:
    try:
        session.close()
    except BaseException as error:
        if not quiet:
            raise _backend_refusal(error) from None


def _read_slot(session: PivSessionHandle, slot: str) -> PivSlotInfo:
    try:
        return session.read_slot(slot)
    except BaseException as error:
        raise _backend_refusal(error) from None


def _select_device(devices: Sequence[PivDevice], selector) -> PivDevice:
    """Resolve one device, never silently when the choice is ambiguous."""
    if selector is None:
        if not devices:
            _reject("HARDWARE_NOT_FOUND", "no PIV-capable device is attached")
        if len(devices) > 1:
            _reject("HARDWARE_MULTIPLE_MATCHES",
                    f"{len(devices)} PIV-capable devices are attached; "
                    "select one explicitly")
        return devices[0]
    if not isinstance(selector, str) or selector == "":
        _reject("HARDWARE_NOT_FOUND", "a device selector is a non-empty string")
    matches = [device for device in devices
               if selector in (device.identifier, device.name, device.serial)]
    if not matches:
        _reject("HARDWARE_NOT_FOUND", f"no attached PIV device matches {selector!r}")
    if len(matches) > 1:
        _reject("HARDWARE_MULTIPLE_MATCHES",
                f"{len(matches)} attached PIV devices match {selector!r}")
    return matches[0]


def _list_devices(backend: PivBackend) -> tuple:
    try:
        return tuple(backend.list_devices())
    except BaseException as error:
        raise _backend_refusal(error) from None


# --------------------------------------------------------------------
# The provider
# --------------------------------------------------------------------


class PivP256Provider:
    """HumanPrivateKeyProvider over one existing P-256 key in a PIV slot.

    Construction reads the slot public key once (read-only), requires a
    P-256 EC key, derives the HUMAN_ID from that key and closes the session
    again. Each ``exchange`` call is one explicit session: open, re-verify the
    slot identity, verify the PIN once if the slot demands it, one ECDH
    operation, close — including on error. No private-key accessor exists and
    no PIN is ever held in constructor state.
    """

    def __init__(self, backend: PivBackend, *, slot, device=None,
                 expected_human_id: Optional[str] = None, pin_provider=None,
                 require_hardened: bool = False):
        _require_crypto()
        if not isinstance(backend, PivBackend):
            _reject("NOT_A_PIV_BACKEND",
                    "a PIV backend lists devices and opens one session at a time")
        if pin_provider is not None and not isinstance(pin_provider, PinProvider):
            _reject("HARDWARE_PIN_REQUIRED",
                    "the PIN source must expose get_pin() and nothing is guessed")
        self._backend = backend
        self.slot = normalize_slot(slot)
        self._device = _select_device(_list_devices(backend), device)
        self._pin_provider = pin_provider
        if expected_human_id is not None:
            if not isinstance(expected_human_id, str) \
                    or not _HUMAN_ID_RE.fullmatch(expected_human_id):
                _reject("BAD_HUMAN_ID", "HUMAN_ID is human-id:sha256:<64 lowercase hex>")
        session = _open_session(backend, self._device)
        try:
            info = _read_slot(session, self.slot)
        finally:
            _close_session(session, quiet=True)
        self._human_id, self._public_key_spki = self._identity(info)
        if expected_human_id is not None and expected_human_id != self._human_id:
            _reject("HARDWARE_IDENTITY_MISMATCH",
                    "the slot public key is not the expected HUMAN_ID")
        self._interaction_policy = classify_interaction_policy(
            info.pin_policy, info.touch_policy)
        if require_hardened:
            if self._interaction_policy == UNKNOWN_POLICY:
                _reject("HARDWARE_POLICY_UNKNOWN",
                        "the slot interaction policy is not readable")
            if self._interaction_policy != HARDENED:
                _reject("HARDWARE_POLICY_WEAK",
                        "the slot interaction policy is below the reference profile")

    # -- read-only facade ------------------------------------------------

    @property
    def human_id(self) -> str:
        return self._human_id

    @property
    def public_key_spki(self) -> bytes:
        """The slot public key as canonical DER SubjectPublicKeyInfo."""
        return self._public_key_spki

    @property
    def interaction_policy(self) -> str:
        return self._interaction_policy

    @property
    def device(self) -> PivDevice:
        return self._device

    # -- the one private operation ---------------------------------------

    def exchange(self, ephemeral_public_key: bytes) -> bytes:
        if not isinstance(ephemeral_public_key, (bytes, bytearray)):
            _reject("BAD_EPHEMERAL_KEY",
                    "the ephemeral public key is exact DER SubjectPublicKeyInfo bytes")
        ephemeral_public_key = bytes(ephemeral_public_key)
        self._load_p256(ephemeral_public_key)

        session = _open_session(self._backend, self._device)
        try:
            info = _read_slot(session, self.slot)
            current_human_id, _ = self._identity(info)
            if current_human_id != self._human_id:
                _reject("HARDWARE_IDENTITY_MISMATCH",
                        "the slot key changed since this provider was constructed")
            if self._pin_needed(session):
                self._verify_pin(session)
            secret = self._exchange(session, ephemeral_public_key)
        except BaseException:
            _close_session(session, quiet=True)
            raise
        _close_session(session, quiet=False)
        if not isinstance(secret, (bytes, bytearray)) or len(secret) != SHARED_SECRET_BYTES:
            _reject("HARDWARE_OPERATION_FAILED",
                    "the token did not return a 32-byte P-256 shared secret")
        return bytes(secret)

    # -- internals -------------------------------------------------------

    def _identity(self, info: PivSlotInfo) -> tuple:
        if info.empty:
            _reject("HARDWARE_SLOT_EMPTY", f"PIV slot {self.slot} holds no key")
        if info.key_type != ECCP256 or info.public_key_spki is None:
            _reject("HARDWARE_ALGORITHM_UNSUPPORTED",
                    f"PIV slot {self.slot} does not hold a readable P-256 EC key")
        try:
            key = load_der_public_key(info.public_key_spki)
        except ValueError:
            _reject("HARDWARE_ALGORITHM_UNSUPPORTED",
                    f"PIV slot {self.slot} public key is not a DER SubjectPublicKeyInfo")
        self._load_p256_object(key)
        return human_id(key), info.public_key_spki

    def _load_p256(self, spki: bytes) -> None:
        try:
            key = load_der_public_key(spki)
        except ValueError:
            _reject("BAD_EPHEMERAL_KEY",
                    "the ephemeral public key is not DER SubjectPublicKeyInfo")
        self._load_p256_object(key, code="BAD_EPHEMERAL_KEY")

    def _load_p256_object(self, key, *, code: str = "HARDWARE_ALGORITHM_UNSUPPORTED") -> None:
        if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
            _reject(code, "this provider works with P-256 ECDH keys only")

    def _pin_needed(self, session: PivSessionHandle) -> bool:
        try:
            return bool(session.pin_required(self.slot))
        except BaseException as error:
            raise _backend_refusal(error) from None

    def _verify_pin(self, session: PivSessionHandle) -> None:
        if self._pin_provider is None:
            _reject("HARDWARE_PIN_REQUIRED",
                    f"PIV slot {self.slot} requires PIN verification; "
                    "no interactive PIN source was supplied")
        pin = self._pin_provider.get_pin()
        if not isinstance(pin, str) or pin == "":
            _reject("HARDWARE_PIN_REQUIRED", "the PIN source did not supply a PIN")
        try:
            session.verify_pin(pin)
        except BaseException as error:
            if isinstance(error, PivBackendError) \
                    and error.code == "HARDWARE_PIN_INVALID" \
                    and error.retries_remaining is not None:
                raise SailangError(
                    "HARDWARE_PIN_INVALID",
                    f"PIN verification failed; {error.retries_remaining} "
                    "attempt(s) remaining on the token") from None
            raise _backend_refusal(error) from None
        finally:
            # One attempt per explicit request, and no speculative retry. Python
            # strings are immutable, so this only drops the local reference; no
            # secure memory erasure is claimed.
            del pin

    def _exchange(self, session: PivSessionHandle, ephemeral_public_key: bytes) -> bytes:
        try:
            return session.exchange(self.slot, ephemeral_public_key)
        except BaseException as error:
            raise _backend_refusal(error) from None


# --------------------------------------------------------------------
# Read-only discovery
# --------------------------------------------------------------------


@dataclass(frozen=True)
class SlotInspection:
    """One slot as reported by read-only discovery."""

    slot: str
    empty: bool
    key_type: Optional[str]
    human_id: Optional[str]
    pin_policy: str
    touch_policy: str
    origin: Optional[str]
    interaction_policy: str


@dataclass(frozen=True)
class DeviceInspection:
    """One device as reported by read-only discovery."""

    device: PivDevice
    firmware: Optional[str]
    serial: Optional[str]
    slots: tuple


def inspect_devices(backend: PivBackend, *, device=None,
                    slots: Optional[Sequence[str]] = None) -> tuple:
    """Read-only capability discovery. Never asks for a PIN, never does ECDH.

    A slot that cannot be read is reported honestly: an empty slot stays empty,
    an unreadable policy stays UNKNOWN_POLICY, and nothing is inferred into
    security. The caller still owns device and slot selection.
    """
    wanted = tuple(normalize_slot(value) for value in (slots or STANDARD_SLOTS + RETIRED_SLOTS))
    devices = _list_devices(backend)
    if device is not None:
        devices = (_select_device(devices, device),)
    reports = []
    for item in devices:
        session = _open_session(backend, item)
        try:
            firmware = session.firmware
            serial = session.serial
            inspections = []
            for slot in wanted:
                info = _read_slot(session, slot)
                derived_human_id = None
                if not info.empty and info.key_type == ECCP256 \
                        and info.public_key_spki is not None:
                    try:
                        derived_human_id = human_id(load_der_public_key(info.public_key_spki))
                    except (ValueError, SailangError):
                        derived_human_id = None
                inspections.append(SlotInspection(
                    slot=slot,
                    empty=info.empty,
                    key_type=info.key_type,
                    human_id=derived_human_id,
                    pin_policy=info.pin_policy,
                    touch_policy=info.touch_policy,
                    origin=info.origin,
                    interaction_policy=classify_interaction_policy(
                        info.pin_policy, info.touch_policy),
                ))
        finally:
            _close_session(session, quiet=True)
        reports.append(DeviceInspection(
            device=item,
            firmware=firmware,
            serial=serial,
            slots=tuple(inspections),
        ))
    return tuple(reports)


# --------------------------------------------------------------------
# Production backend: the optional Yubico stack, imported lazily
# --------------------------------------------------------------------

_YK_READER_HINT = "yubikey"


def _require_yubico_stack():
    """Import the optional vendor stack on first use; refuse by name if absent."""
    global _YUBICO_STACK
    if _YUBICO_STACK is not None:
        return _YUBICO_STACK
    try:
        from smartcard import System
        from smartcard.Exceptions import CardConnectionException, NoCardException
        from yubikit.core import (
            ApplicationNotAvailableError,
            BadResponseError,
            CommandError,
            InvalidPinError,
            NotSupportedError,
            TRANSPORT,
            TimeoutError as YubicoTimeoutError,
        )
        from yubikit.core.smartcard import ApduError, SW
        from yubikit.piv import KEY_TYPE, PIN_POLICY, TOUCH_POLICY, PivSession, SLOT
    except ImportError as exc:
        raise PivBackendError(
            "HARDWARE_PROVIDER_UNAVAILABLE",
            "the optional YubiKey stack is not installed; install with "
            'pip install -e ".[hardware-yubikey]"') from None
    _YUBICO_STACK = {
        "System": System,
        "CardConnectionException": CardConnectionException,
        "NoCardException": NoCardException,
        "ApplicationNotAvailableError": ApplicationNotAvailableError,
        "BadResponseError": BadResponseError,
        "CommandError": CommandError,
        "InvalidPinError": InvalidPinError,
        "NotSupportedError": NotSupportedError,
        "YubicoTimeoutError": YubicoTimeoutError,
        "ApduError": ApduError,
        "SW": SW,
        "KEY_TYPE": KEY_TYPE,
        "PIN_POLICY": PIN_POLICY,
        "TOUCH_POLICY": TOUCH_POLICY,
        "PivSession": PivSession,
        "SLOT": SLOT,
        "TRANSPORT": TRANSPORT,
    }
    return _YUBICO_STACK


def _native_failure(error: BaseException, *, touch_expected: bool) -> tuple:
    """Map a vendor exception to (code, fixed detail, retries). No raw data.

    The mapping keys on the vendor exception class names so it can be proven
    deterministically without importing the vendor stack; detail strings are
    fixed here and never interpolate the exception's own text.
    """
    name = type(error).__name__
    if name == "InvalidPinError":
        retries = getattr(error, "attempts_remaining", None)
        return "HARDWARE_PIN_INVALID", "PIN verification failed", retries
    if name == "NoCardException":
        return "HARDWARE_NOT_FOUND", "the selected token is no longer present", None
    if name == "CardConnectionException":
        if "cancel" in str(error).lower():
            return ("HARDWARE_OPERATION_CANCELLED",
                    "the operation was cancelled at the device", None)
        return "HARDWARE_OPERATION_FAILED", "the device connection failed", None
    if name == "ApplicationNotAvailableError":
        return ("HARDWARE_ALGORITHM_UNSUPPORTED",
                "the device does not expose the PIV application", None)
    if name == "NotSupportedError":
        return ("HARDWARE_ALGORITHM_UNSUPPORTED",
                "the device or firmware does not support this operation", None)
    if name in ("TimeoutError", "YubicoTimeoutError"):
        if touch_expected:
            return ("HARDWARE_TOUCH_TIMEOUT",
                    "the token did not register the required touch in time", None)
        return "HARDWARE_OPERATION_FAILED", "the device operation timed out", None
    if name == "ApduError":
        sw = getattr(error, "sw", None)
        if sw in (0x6A82, 0x6A83, 0x6A88):
            return "HARDWARE_SLOT_EMPTY", "the selected slot holds no key", None
        if sw == 0x6982:
            return ("HARDWARE_PIN_REQUIRED",
                    "the device requires PIN verification for this operation", None)
        if sw == 0x6983:
            return "HARDWARE_PIN_BLOCKED", "PIN verification is blocked on the token", 0
        if isinstance(sw, int) and sw & 0xFFF0 == 0x63C0:
            return ("HARDWARE_PIN_INVALID", "PIN verification failed", sw & 0x0F)
        if isinstance(sw, int) and sw & 0xFF00 == 0x6300:
            return ("HARDWARE_PIN_INVALID", "PIN verification failed", sw & 0xFF)
        if sw == 0x6985:
            if touch_expected:
                return ("HARDWARE_TOUCH_TIMEOUT",
                        "the token did not register the required touch in time", None)
            return ("HARDWARE_OPERATION_FAILED",
                    "the device refused the operation in its current state", None)
        if sw in (0x6A80, 0x6A81, 0x6D00, 0x6E00, 0x6B00):
            return ("HARDWARE_ALGORITHM_UNSUPPORTED",
                    "the selected slot key is not usable for P-256 ECDH", None)
        return "HARDWARE_OPERATION_FAILED", "the device refused the operation", None
    if name == "BadResponseError":
        return "HARDWARE_OPERATION_FAILED", "the device returned an invalid response", None
    if name == "CommandError":
        return "HARDWARE_OPERATION_FAILED", "the device reported a command failure", None
    return "HARDWARE_OPERATION_FAILED", "the hardware backend failed", None


class _ScardConnection:
    """Minimal PC/SC transport adapter for yubikit's SmartCardConnection seam.

    Mimics only what ``SmartCardProtocol`` uses: ``send_and_receive``,
    ``close`` and ``transport``. It is not a copy of vendor code.
    """

    def __init__(self, connection, transport):
        self._connection = connection
        self.transport = transport

    def send_and_receive(self, apdu: bytes) -> tuple:
        data, sw1, sw2 = self._connection.transmit(list(apdu))
        return bytes(data), (sw1 << 8) | sw2

    def close(self) -> None:
        try:
            self._connection.disconnect()
        except Exception:  # a disconnect fault is not an operation failure here
            pass


class _YubicoSession:
    """One narrow PIV session over the optional Yubico stack."""

    def __init__(self, mods, piv_session, connection, firmware, serial):
        self._mods = mods
        self._piv = piv_session
        self._connection = connection
        self._firmware = firmware
        self._serial = serial

    @property
    def firmware(self) -> Optional[str]:
        return self._firmware

    @property
    def serial(self) -> Optional[str]:
        return self._serial

    def _slot_enum(self, slot: str):
        return self._mods["SLOT"](int(slot, 16))

    def _touch_expected(self, slot: str) -> bool:
        try:
            meta = self._piv.get_slot_metadata(self._slot_enum(slot))
        except Exception:
            return False
        return meta.touch_policy != self._mods["TOUCH_POLICY"].NEVER

    def _call(self, func, *, touch_expected: bool = False):
        try:
            return func()
        except PivBackendError:
            raise
        except Exception as error:
            code, detail, retries = _native_failure(error, touch_expected=touch_expected)
            raise PivBackendError(code, detail, retries) from None

    def read_slot(self, slot: str) -> PivSlotInfo:
        def read():
            try:
                meta = self._piv.get_slot_metadata(self._slot_enum(slot))
            except self._mods["NotSupportedError"]:
                return PivSlotInfo(slot=slot)
            except self._mods["ApduError"] as error:
                if error.sw in (0x6A82, 0x6A83, 0x6A88):
                    return PivSlotInfo(slot=slot, empty=True)
                raise
            key = None
            spki = None
            try:
                key = meta.public_key()
                spki = key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
            except (ValueError, AttributeError):
                spki = None
            return PivSlotInfo(
                slot=slot,
                empty=spki is None,
                key_type=str(meta.key_type.name),
                public_key_spki=spki,
                pin_policy=str(meta.pin_policy.name),
                touch_policy=str(meta.touch_policy.name),
                origin="GENERATED" if meta.generated else "IMPORTED",
            )
        return self._call(read)

    def pin_required(self, slot: str) -> bool:
        def read():
            try:
                meta = self._piv.get_slot_metadata(self._slot_enum(slot))
            except self._mods["NotSupportedError"]:
                return True  # unknown policy: fail closed, ask once
            except self._mods["ApduError"] as error:
                if error.sw in (0x6A82, 0x6A83, 0x6A88):
                    return False
                raise
            return meta.pin_policy != self._mods["PIN_POLICY"].NEVER
        return self._call(read)

    def verify_pin(self, pin: str) -> None:
        self._call(lambda: self._piv.verify_pin(pin))

    def exchange(self, slot: str, ephemeral_public_key_spki: bytes) -> bytes:
        touch_expected = self._touch_expected(slot)
        peer = load_der_public_key(ephemeral_public_key_spki)

        def calculate():
            return self._piv.calculate_secret(self._slot_enum(slot), peer)
        return self._call(calculate, touch_expected=touch_expected)

    def close(self) -> None:
        self._connection.close()


class YubicoPivBackend:
    """Production backend over the optional Yubico Python stack.

    Every entry point imports the vendor stack lazily; without the declared
    extra the backend refuses with HARDWARE_PROVIDER_UNAVAILABLE and nothing
    is installed at runtime.
    """

    def list_devices(self) -> tuple:
        mods = _require_yubico_stack()
        try:
            readers = mods["System"].readers()
        except Exception:
            raise PivBackendError(
                "HARDWARE_PROVIDER_UNAVAILABLE",
                "PC/SC is not available on this host") from None
        devices = []
        for reader in readers:
            name = reader.name
            if _YK_READER_HINT in name.lower():
                devices.append(PivDevice(identifier=name, name=name))
        return tuple(devices)

    def open(self, device: PivDevice) -> _YubicoSession:
        mods = _require_yubico_stack()
        try:
            readers = mods["System"].readers()
        except Exception:
            raise PivBackendError(
                "HARDWARE_PROVIDER_UNAVAILABLE",
                "PC/SC is not available on this host") from None
        reader = next((item for item in readers if item.name == device.identifier), None)
        if reader is None:
            raise PivBackendError("HARDWARE_NOT_FOUND",
                                  "the selected reader is no longer attached")
        try:
            connection = reader.createConnection()
            connection.connect()
        except Exception as error:
            code, detail, retries = _native_failure(error, touch_expected=False)
            raise PivBackendError(code, detail, retries) from None
        try:
            transport = mods["TRANSPORT"].USB if connection.getATR() \
                else mods["TRANSPORT"].NFC
        except Exception:
            transport = mods["TRANSPORT"].USB
        wrapped = _ScardConnection(connection, transport)
        try:
            session = mods["PivSession"](wrapped)
        except Exception as error:
            wrapped.close()
            code, detail, retries = _native_failure(error, touch_expected=False)
            raise PivBackendError(code, detail, retries) from None
        firmware = None
        version = getattr(session, "version", None)
        if version is not None:
            firmware = str(version)
        serial = None
        try:
            serial = str(session.get_serial())
        except Exception:
            serial = None
        return _YubicoSession(mods, session, wrapped, firmware, serial)


# --------------------------------------------------------------------
# Operator tool: inspect (read-only) and verify (one explicit operation)
# --------------------------------------------------------------------


def _inspection_report(report: DeviceInspection) -> dict:
    return {
        "device": report.device.identifier,
        "serial": report.serial,
        "firmware": report.firmware,
        "slots": [
            {
                "slot": slot.slot,
                "state": "EMPTY" if slot.empty else "KEY",
                "key_type": slot.key_type,
                "human_id": slot.human_id,
                "pin_policy": slot.pin_policy,
                "touch_policy": slot.touch_policy,
                "origin": slot.origin,
                "interaction_policy": slot.interaction_policy,
            }
            for slot in report.slots
        ],
    }


class _InteractivePinProvider:
    """The reference PIN source: interactive, never command line or environment."""

    def get_pin(self) -> str:
        return getpass("PIV PIN (not echoed, not stored): ")


def _run_inspect(backend, args) -> int:
    try:
        reports = inspect_devices(backend, device=args.device, slots=args.slot)
    except SailangError as error:
        print(f"REAL_HARDWARE_INSPECTION: NOT_RUN ({error.code})")
        return 2
    if not reports:
        print("REAL_HARDWARE_INSPECTION: NOT_RUN (NO_HARDWARE)")
        return 2
    print("REAL_HARDWARE_INSPECTION: RAN (read-only; no PIN, no ECDH, no writes)")
    print(json.dumps([_inspection_report(report) for report in reports],
                     indent=2, sort_keys=True))
    return 0


def _run_verify(backend, args, pin_provider) -> int:
    _require_crypto()
    source = pin_provider if pin_provider is not None else _InteractivePinProvider()
    try:
        provider = PivP256Provider(
            backend, slot=args.slot, device=args.device,
            expected_human_id=args.expected_human_id, pin_provider=source)
        ephemeral = ec.generate_private_key(ec.SECP256R1())
        ephemeral_spki = ephemeral.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        hardware_secret = provider.exchange(ephemeral_spki)
        token_key = load_der_public_key(provider.public_key_spki)
        software_secret = ephemeral.exchange(ec.ECDH(), token_key)
    except SailangError as error:
        if error.code in ("HARDWARE_NOT_FOUND", "HARDWARE_PROVIDER_UNAVAILABLE"):
            print(f"REAL_HARDWARE_ECDH_VERIFY: NOT_RUN ({error.code})")
            return 2
        print(f"REAL_HARDWARE_ECDH_VERIFY: FAIL ({error.code})")
        return 1
    print("REAL_HARDWARE_ECDH_VERIFY: RAN (non-destructive; one ECDH operation)")
    print(f"DEVICE: {provider.device.identifier}")
    print(f"SLOT: {provider.slot}")
    print(f"HUMAN_ID: {provider.human_id}")
    print(f"POLICY: {provider.interaction_policy}")
    print(f"ECDH: {'PASS' if hardware_secret == software_secret else 'FAIL'}")
    return 0 if hardware_secret == software_secret else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=MODULE_COMMAND,
        description="SAILETTER hardware custody: read-only PIV discovery and "
                    "explicit non-destructive hardware verification. No option "
                    "provisions, imports, deletes or resets anything, and there "
                    "is no PIN option: the PIN is only ever typed interactively.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser(
        "inspect", help="strictly read-only device and slot discovery")
    inspect_parser.add_argument("--device", default=None,
                                help="explicit device selector when more than one is attached")
    inspect_parser.add_argument("--slot", action="append", default=None,
                                help="slot to inspect (repeatable; default: standard + retired)")
    verify_parser = subparsers.add_parser(
        "verify", help="one explicit non-destructive P-256 ECDH verification")
    verify_parser.add_argument("--device", required=True,
                               help="explicit device selector (never chosen silently)")
    verify_parser.add_argument("--slot", required=True,
                               help="explicit existing slot with the P-256 key")
    verify_parser.add_argument("--expected-human-id", default=None,
                               help="optional expected human-id:sha256:<64 hex>")
    return parser


def main(argv: Optional[Sequence[str]] = None, *, backend=None, pin_provider=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inspect":
        return _run_inspect(backend if backend is not None else YubicoPivBackend(), args)
    return _run_verify(backend if backend is not None else YubicoPivBackend(),
                       args, pin_provider)


if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess by hand
    sys.exit(main())


__all__ = [
    "COMPATIBLE_WEAK_POLICY", "DeviceInspection", "ECCP256", "HARDENED",
    "HARDWARE_ERROR_CODES", "KNOWN_SLOTS", "MODULE_COMMAND", "PivBackend",
    "PivBackendError", "PivDevice", "PivP256Provider", "PivSessionHandle",
    "PivSlotInfo", "PinProvider", "REFERENCE_SLOT", "RETIRED_SLOTS",
    "STANDARD_SLOTS", "SlotInspection", "UNKNOWN_POLICY", "YubicoPivBackend",
    "build_parser", "classify_interaction_policy", "inspect_devices", "main",
    "normalize_slot",
]
