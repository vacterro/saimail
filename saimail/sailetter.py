"""SAILETTER v0 — HUMAN_PRIVATE letters sealed in HENV1 (D-042).

The contract is `spec/05-SAILETTER-v0.md` and `spec/DECISIONS.md` D-042; this
module implements it and never invents a second one. Four properties are
load-bearing:

* **The plaintext is one canonical object.** `HLET1` has exactly one accepted
  byte representation; SUBJECT and BODY round-trip exactly, multiline prose
  included, with no trim and no normalization.
* **The container is recipient-bound.** One fresh CEK encrypts the letter once;
  each authorized slot (PRIMARY, or PRIMARY plus RECOVERY) wraps that CEK with
  a fresh ephemeral P-256 ECDH and a role-separated HKDF. The AEAD associated
  data binds the exact routing identity the ciphertext was created under, so a
  relabelled and freshly re-signed container still refuses to open.
* **Verification precedes every recipient private-key operation.** The sender
  Ed25519 signature is checked against the receiver-owned acceptance registry
  before any provider ECDH call, so a forged sender reaches zero private-key
  operations.
* **The store is ciphertext-only.** One immutable `.henv1` file per committed
  letter under `human-private/<human-id-digest>/`; delivery needs no recipient
  key and decrypts nothing; listing reveals only clear container metadata;
  opening is explicit, provider-driven and stateless.

`SoftwareP256Provider` is a reference software provider for tests: its key
lives in process memory and it is not hardware protection. Opened state is a
constructor-guarded type-state over the normal public interface (D-015): it
stops accidents, not adversaries.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import os
import re
from dataclasses import InitVar, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from sailang.errors import SailangError

from . import envelope, publish

try:  # cryptography stays a declared extra of the distribution
    from cryptography.exceptions import InvalidSignature, InvalidTag
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

    _CRYPTO_IMPORT_ERROR: Optional[BaseException] = None
except ImportError as _exc:  # pragma: no cover - exercised only without the extra
    _CRYPTO_IMPORT_ERROR = _exc

PLAINTEXT_FORMAT = "HLET1"
CONTAINER_FORMAT = "HENV1"
LETTER_CLASS = "HUMAN_PRIVATE"
MODE_STRICT = "STRICT"
MODE_RECOVERABLE = "RECOVERABLE"
SLOT_PRIMARY = "PRIMARY"
SLOT_RECOVERY = "RECOVERY"
SIGNATURE_ALGORITHM = "ed25519"
HUMAN_ID_PREFIX = "human-id:sha256:"
HASH_PREFIX = "sha256:"
NONE = "NONE"

#: The four immutable HENV1 domains (D-042). No SENV2 domain is reused.
PAYLOAD_DOMAIN = b"SAIMAIL-HENV1-PAYLOAD\x00"
CEK_PRIMARY_DOMAIN = b"SAIMAIL-HENV1-CEK-PRIMARY\x00"
CEK_RECOVERY_DOMAIN = b"SAIMAIL-HENV1-CEK-RECOVERY\x00"
SIGNATURE_DOMAIN = b"SAIMAIL-HENV1-SIGNATURE\x00"

MAX_SUBJECT_BYTES = 256
MAX_BODY_BYTES = 65_536
MAX_HLET_BYTES = 98_304
MAX_HENV1_BYTES = 262_144
MAX_VALUE_BYTES = 512
CEK_BYTES = 32
NONCE_BYTES = 12
WRAPPED_CEK_BYTES = 48
CURVE_NAME = "secp256r1"

DELIVERED = "DELIVERED"
DUPLICATE = "DUPLICATE"
HUMAN_DIR = "human-private"
HENV1_SUFFIX = ".henv1"

_HUMAN_ID_RE = re.compile(r"^human-id:sha256:[0-9a-f]{64}$")
_KID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_SEAT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HEX_RE = re.compile(r"^[0-9a-f]+$")

_HLET_FIELDS = ("CLASS", "TO_HUMAN", "CREATED", "SUBJECT_B64", "BODY_B64")
_HENV1_HEAD = ("FROM", "FROM_KID", "TO_HUMAN", "MODE", "PRIMARY_KID", "RECOVERY_KID",
               "PRIMARY_EPK", "PRIMARY_WRAP_NONCE", "PRIMARY_WRAPPED_CEK")
_HENV1_RECOVERY = ("RECOVERY_EPK", "RECOVERY_WRAP_NONCE", "RECOVERY_WRAPPED_CEK")
_HENV1_TAIL = ("PAYLOAD_NONCE", "PAYLOAD_B64")
_HENV1_FIELDS = frozenset(_HENV1_HEAD + _HENV1_RECOVERY + _HENV1_TAIL)


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _require_crypto() -> None:
    if _CRYPTO_IMPORT_ERROR is not None:
        _reject("CRYPTO_UNAVAILABLE",
                "the cryptography package is not installed; install with "
                "pip install -e .[crypto]")


def _p256_public_key(value, *, code: str = "NOT_P256_PUBLIC_KEY") -> None:
    if not isinstance(value, ec.EllipticCurvePublicKey) or value.curve.name != CURVE_NAME:
        _reject(code, "this protocol speaks P-256 (secp256r1) public keys only")


def _check_utc(value, *, code: str) -> None:
    if not isinstance(value, str) or not _UTC_RE.fullmatch(value):
        _reject(code, "timestamp must be exact UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        _reject(code, "timestamp is not a real UTC calendar instant")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _reject(code, "timestamp is not canonical UTC")


def _check_human_id(field: str, value) -> None:
    if not isinstance(value, str) or not _HUMAN_ID_RE.fullmatch(value):
        _reject("HLET1_BAD_TO_HUMAN" if field == "TO_HUMAN" else f"HENV1_BAD_{field}",
                f"{field} is human-id:sha256:<64 lowercase hex>")


def human_id(public_key) -> str:
    """The one human identity: ``sha256`` over canonical P-256 SPKI DER bytes."""
    _require_crypto()
    _p256_public_key(public_key)
    der = public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return HUMAN_ID_PREFIX + hashlib.sha256(der).hexdigest()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


# --------------------------------------------------------------------
# Target B: canonical HLET1 plaintext
# --------------------------------------------------------------------


@dataclass(frozen=True)
class HumanPrivateLetter:
    """One immutable HUMAN_PRIVATE letter; its prose is inert data."""

    to_human: str
    created: str
    subject: str
    body: str

    def __post_init__(self) -> None:
        _check_human_id("TO_HUMAN", self.to_human)
        _check_utc(self.created, code="HLET1_BAD_CREATED")
        if not isinstance(self.subject, str):
            _reject("HLET1_BAD_SUBJECT", "SUBJECT must be text")
        if not isinstance(self.body, str):
            _reject("HLET1_BAD_BODY", "BODY must be text")
        for name, value, limit, empty_code, size_code in (
            ("SUBJECT", self.subject, MAX_SUBJECT_BYTES, "HLET1_EMPTY_SUBJECT",
             "HLET1_SUBJECT_OVERSIZE"),
            ("BODY", self.body, MAX_BODY_BYTES, "HLET1_EMPTY_BODY",
             "HLET1_BODY_OVERSIZE"),
        ):
            if value == "":
                _reject(empty_code, f"{name} is required and cannot be empty")
            try:
                encoded = value.encode("utf-8")
            except UnicodeEncodeError:
                _reject("HLET1_BAD_UTF8", f"{name} must be well-formed UTF-8 text")
            if len(encoded) > limit:
                _reject(size_code, f"{name} exceeds {limit} UTF-8 bytes")
        if len(self.render()) > MAX_HLET_BYTES:
            _reject("HLET1_OVERSIZE", f"HLET1 exceeds {MAX_HLET_BYTES} bytes")

    @classmethod
    def parse(cls, data) -> "HumanPrivateLetter":
        """Parse one canonical HLET1; anything else refuses."""
        if isinstance(data, (bytes, bytearray)):
            raw = bytes(data)
            if raw[:3] == b"\xef\xbb\xbf":
                _reject("HLET1_NONCANONICAL", "a letter is UTF-8 without BOM")
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                _reject("HLET1_BAD_UTF8", "a letter body is strict UTF-8")
        elif isinstance(data, str):
            text = data
            if text.startswith("\ufeff"):
                _reject("HLET1_NONCANONICAL", "a letter is UTF-8 without BOM")
            raw = text.encode("utf-8")
        else:
            _reject("NON_TEXT_INPUT", "a letter is text or UTF-8 bytes")
        if "\r" in text or "\x00" in text:
            _reject("HLET1_NONCANONICAL", "line ends are LF and NUL is not part of HLET1")
        if not text.endswith("\n"):
            _reject("HLET1_NONCANONICAL", "HLET1 ends with exactly one final LF")
        lines = text[:-1].split("\n")
        if not lines or lines[0] != PLAINTEXT_FORMAT:
            _reject("HLET1_BAD_FORMAT", f"the first line must be exactly {PLAINTEXT_FORMAT!r}")
        pairs: list = []
        seen_names = set()
        for line in lines[1:]:
            if ":" not in line:
                _reject("HLET1_FIELD_SET", "every HLET1 field line is NAME:VALUE")
            name, value = line.split(":", 1)
            if name in seen_names:
                _reject("HLET1_DUPLICATE_FIELD", f"duplicate field {name}")
            seen_names.add(name)
            if name not in _HLET_FIELDS:
                _reject("HLET1_UNKNOWN_FIELD", f"{name!r} is not an HLET1 field")
            pairs.append((name, value))
        if len(pairs) != len(_HLET_FIELDS):
            _reject("HLET1_FIELD_SET", "HLET1 has a missing, duplicate, or unknown field")
        parsed: dict = {}
        for expected, (name, value) in zip(_HLET_FIELDS, pairs):
            if name != expected:
                _reject("HLET1_FIELD_ORDER", f"expected {expected}, found {name}")
            parsed[name] = value
        if parsed["CLASS"] != LETTER_CLASS:
            _reject("HLET1_BAD_CLASS", f"CLASS must be exactly {LETTER_CLASS!r}")
        values = {}
        for name in ("SUBJECT", "BODY"):
            try:
                decoded = base64.b64decode(parsed[f"{name}_B64"], validate=True)
            except (binascii.Error, ValueError):
                _reject("HLET1_BAD_BASE64", f"{name}_B64 is standard base64 with padding")
            try:
                values[name] = decoded.decode("utf-8")
            except UnicodeDecodeError:
                _reject("HLET1_BAD_UTF8", f"{name} is not valid UTF-8")
        letter = cls(
            to_human=parsed["TO_HUMAN"],
            created=parsed["CREATED"],
            subject=values["SUBJECT"],
            body=values["BODY"],
        )
        if letter.render() != raw:
            _reject("HLET1_NONCANONICAL",
                    "a letter has exactly one byte representation; this one is not the "
                    "canonical rendering of the text it carries")
        return letter

    def render(self) -> bytes:
        lines = [
            PLAINTEXT_FORMAT,
            f"CLASS:{LETTER_CLASS}",
            f"TO_HUMAN:{self.to_human}",
            f"CREATED:{self.created}",
            f"SUBJECT_B64:{_b64(self.subject.encode('utf-8'))}",
            f"BODY_B64:{_b64(self.body.encode('utf-8'))}",
        ]
        return ("\n".join(lines) + "\n").encode("utf-8")


@dataclass(frozen=True)
class HumanRecipient:
    """One human's authorized encryption identity; never trusted independently."""

    human_id: str
    primary_public_key: "ec.EllipticCurvePublicKey"
    recovery_public_key: Optional["ec.EllipticCurvePublicKey"] = None

    def __post_init__(self) -> None:
        _require_crypto()
        if not isinstance(self.human_id, str) or not _HUMAN_ID_RE.fullmatch(self.human_id):
            _reject("BAD_HUMAN_ID", "HUMAN_ID is human-id:sha256:<64 lowercase hex>")
        _p256_public_key(self.primary_public_key)
        if self.human_id != human_id(self.primary_public_key):
            _reject("HUMAN_ID_MISMATCH",
                    "the supplied HUMAN_ID is not the fingerprint of the supplied primary key")
        if self.recovery_public_key is not None:
            _p256_public_key(self.recovery_public_key)
            if human_id(self.recovery_public_key) == self.human_id:
                _reject("RECOVERY_KEY_NOT_DISTINCT",
                        "a recovery key must be cryptographically distinct from the primary key")


@runtime_checkable
class HumanPrivateKeyProvider(Protocol):
    """The narrow seam: a recipient identity and one P-256 ECDH operation."""

    @property
    def human_id(self) -> str:
        ...

    def exchange(self, ephemeral_public_key: bytes) -> bytes:
        ...


class SoftwareP256Provider:
    """Reference software provider for tests.

    The private key lives in process memory; this class is not hardware
    protection and no hardware-backed property is claimed for it.
    """

    def __init__(self, private_key: "ec.EllipticCurvePrivateKey"):
        _require_crypto()
        if not isinstance(private_key, ec.EllipticCurvePrivateKey) \
                or private_key.curve.name != CURVE_NAME:
            _reject("NOT_P256_PRIVATE_KEY", "this provider holds P-256 private keys only")
        self._private_key = private_key

    @property
    def human_id(self) -> str:
        return human_id(self._private_key.public_key())

    def exchange(self, ephemeral_public_key: bytes) -> bytes:
        if not isinstance(ephemeral_public_key, (bytes, bytearray)):
            _reject("BAD_EPHEMERAL_KEY", "the ephemeral public key is exact bytes")
        try:
            peer = load_der_public_key(bytes(ephemeral_public_key))
        except ValueError:
            _reject("BAD_EPHEMERAL_KEY", "the ephemeral public key is not DER SubjectPublicKeyInfo")
        _p256_public_key(peer, code="BAD_EPHEMERAL_KEY")
        return self._private_key.exchange(ec.ECDH(), peer)


# --------------------------------------------------------------------
# Target B: bindings and HENV1 container
# --------------------------------------------------------------------


def _canonical_binding(domain: bytes, lines) -> bytes:
    return domain + ("\n".join(lines) + "\n").encode("utf-8")


def _payload_binding(from_seat: str, from_kid: str, to_human: str, mode: str,
                     primary_kid: str, recovery_kid: str) -> bytes:
    return _canonical_binding(PAYLOAD_DOMAIN, (
        CONTAINER_FORMAT,
        f"FROM:{from_seat}",
        f"FROM_KID:{from_kid}",
        f"TO_HUMAN:{to_human}",
        f"MODE:{mode}",
        f"PRIMARY_KID:{primary_kid}",
        f"RECOVERY_KID:{recovery_kid}",
    ))


def _wrap_binding(from_seat: str, from_kid: str, to_human: str, mode: str,
                  slot: str, recipient_kid: str) -> bytes:
    domain = CEK_PRIMARY_DOMAIN if slot == SLOT_PRIMARY else CEK_RECOVERY_DOMAIN
    return _canonical_binding(domain, (
        CONTAINER_FORMAT,
        f"FROM:{from_seat}",
        f"FROM_KID:{from_kid}",
        f"TO_HUMAN:{to_human}",
        f"MODE:{mode}",
        f"SLOT:{slot}",
        f"RECIPIENT_KID:{recipient_kid}",
    ))


def _require_parsed(parsed) -> "HENV1":
    if not isinstance(parsed, HENV1):
        _reject("NOT_A_HENV1", "this operation takes a parsed HENV1")
    return parsed


@dataclass(frozen=True)
class HENV1:
    """One parsed HENV1 container with decoded cryptographic material."""

    from_seat: str
    from_kid: str
    to_human: str
    mode: str
    primary_kid: str
    recovery_kid: str
    primary_epk: bytes
    primary_wrap_nonce: bytes
    primary_wrapped_cek: bytes
    payload_nonce: bytes
    payload_ciphertext: bytes
    signature: bytes
    recovery_epk: Optional[bytes] = None
    recovery_wrap_nonce: Optional[bytes] = None
    recovery_wrapped_cek: Optional[bytes] = None

    @property
    def payload_b64_text(self) -> str:
        return _b64(self.payload_ciphertext)

    def _lines(self, *, include_signature: bool = True) -> list:
        lines = [
            CONTAINER_FORMAT,
            f"FROM:{self.from_seat}",
            f"FROM_KID:{self.from_kid}",
            f"TO_HUMAN:{self.to_human}",
            f"MODE:{self.mode}",
            f"PRIMARY_KID:{self.primary_kid}",
            f"RECOVERY_KID:{self.recovery_kid}",
            f"PRIMARY_EPK:{_b64(self.primary_epk)}",
            f"PRIMARY_WRAP_NONCE:{self.primary_wrap_nonce.hex()}",
            f"PRIMARY_WRAPPED_CEK:{_b64(self.primary_wrapped_cek)}",
        ]
        if self.mode == MODE_RECOVERABLE:
            lines.extend((
                f"RECOVERY_EPK:{_b64(self.recovery_epk)}",
                f"RECOVERY_WRAP_NONCE:{self.recovery_wrap_nonce.hex()}",
                f"RECOVERY_WRAPPED_CEK:{_b64(self.recovery_wrapped_cek)}",
            ))
        lines.extend((
            f"PAYLOAD_NONCE:{self.payload_nonce.hex()}",
            f"PAYLOAD_B64:{_b64(self.payload_ciphertext)}",
        ))
        if include_signature:
            lines.append(f"SIG:{SIGNATURE_ALGORITHM}:{self.signature.hex()}")
        return lines

    def render(self) -> str:
        return "\n".join(self._lines()) + "\n"


def payload_aad(parsed: "HENV1") -> bytes:
    """The payload AEAD associated data of this container (section 6)."""
    parsed = _require_parsed(parsed)
    return _payload_binding(parsed.from_seat, parsed.from_kid, parsed.to_human,
                            parsed.mode, parsed.primary_kid, parsed.recovery_kid)


def wrap_aad(parsed: "HENV1", slot: str) -> bytes:
    """The CEK-wrap AEAD associated data of one slot (section 6)."""
    parsed = _require_parsed(parsed)
    if slot == SLOT_PRIMARY:
        recipient_kid = parsed.primary_kid
    elif slot == SLOT_RECOVERY:
        recipient_kid = parsed.recovery_kid
    else:
        _reject("BAD_SLOT", "a slot is PRIMARY or RECOVERY")
    return _wrap_binding(parsed.from_seat, parsed.from_kid, parsed.to_human,
                         parsed.mode, slot, recipient_kid)


def signature_input(parsed: "HENV1") -> bytes:
    """The exact bytes the Ed25519 signature covers: every line except SIG."""
    parsed = _require_parsed(parsed)
    unsigned = parsed._lines(include_signature=False)
    return _canonical_binding(SIGNATURE_DOMAIN, unsigned)


def letter_id(parsed: "HENV1") -> str:
    """sha256 over the exact canonical complete HENV1 bytes (D-042, A9)."""
    parsed = _require_parsed(parsed)
    return HASH_PREFIX + hashlib.sha256(parsed.render().encode("utf-8")).hexdigest()


def _expected_keys(mode: str) -> tuple:
    if mode == MODE_RECOVERABLE:
        return _HENV1_HEAD + _HENV1_RECOVERY + _HENV1_TAIL
    return _HENV1_HEAD + _HENV1_TAIL


def _decode_b64(value: str, code: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        _reject(code, "the field is standard base64 with padding")


def _decode_epk(value: str) -> bytes:
    der = _decode_b64(value, "HENV1_BAD_BASE64")
    try:
        key = load_der_public_key(der)
    except ValueError:
        _reject("HENV1_BAD_EPK", "EPK is not a DER SubjectPublicKeyInfo public key")
    _p256_public_key(key, code="HENV1_BAD_EPK")
    return der


def _decode_nonce(value: str) -> bytes:
    if len(value) != 2 * NONCE_BYTES or not _HEX_RE.fullmatch(value):
        _reject("HENV1_BAD_NONCE", f"a nonce is exactly {2 * NONCE_BYTES} lowercase hex characters")
    return bytes.fromhex(value)


def parse_henv1(data) -> "HENV1":
    """Parse one bounded, canonical HENV1. No key agreement and no decryption."""
    _require_crypto()
    if isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
        if raw[:3] == b"\xef\xbb\xbf":
            _reject("HENV1_NONCANONICAL", "a container is UTF-8 without BOM")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            _reject("HENV1_NOT_UTF8", "a container body is strict UTF-8")
    elif isinstance(data, str):
        text = data
        if text.startswith("\ufeff"):
            _reject("HENV1_NONCANONICAL", "a container is UTF-8 without BOM")
    else:
        _reject("NON_TEXT_INPUT", "a container is text or UTF-8 bytes")
    if "\r" in text or "\x00" in text:
        _reject("HENV1_NONCANONICAL", "line ends are LF and NUL is not part of HENV1")
    if len(text.encode("utf-8")) > MAX_HENV1_BYTES:
        _reject("HENV1_OVERSIZE", f"container exceeds {MAX_HENV1_BYTES} bytes")
    if not text.endswith("\n"):
        _reject("HENV1_NONCANONICAL", "HENV1 ends with exactly one final LF")
    lines = text[:-1].split("\n")
    if not lines or lines[0] != CONTAINER_FORMAT:
        _reject("HENV1_BAD_VERSION", f"line 1 must be exactly {CONTAINER_FORMAT!r}")
    body = lines[1:]
    if not body:
        _reject("HENV1_MISSING_FIELD", "the container carries no fields")

    pairs: list = []
    signature: Optional[bytes] = None
    seen = set()
    for lineno, line in enumerate(body, start=2):
        if ":" not in line:
            _reject("HENV1_MALFORMED_FIELD", f"line {lineno} is not KEY:VALUE")
        name, value = line.split(":", 1)
        if len(value.encode("utf-8")) > MAX_VALUE_BYTES and name != "PAYLOAD_B64":
            _reject("HENV1_VALUE_OVERSIZE", f"line {lineno} exceeds {MAX_VALUE_BYTES} bytes")
        if name == "SIG":
            if signature is not None:
                _reject("HENV1_DUPLICATE_FIELD", "SIG appears twice")
            if lineno != len(body) + 1:
                _reject("HENV1_FIELD_ORDER", "SIG is the last line, over everything before it")
            prefix = SIGNATURE_ALGORITHM + ":"
            if not value.startswith(prefix):
                _reject("HENV1_BAD_SIGNATURE", f"SIG must be {prefix}<128 lowercase hex>")
            hex_body = value[len(prefix):]
            if len(hex_body) != 128 or not _HEX_RE.fullmatch(hex_body):
                _reject("HENV1_BAD_SIGNATURE", "SIG must be ed25519:<128 lowercase hex>")
            signature = bytes.fromhex(hex_body)
            continue
        if name not in _HENV1_FIELDS:
            _reject("HENV1_UNKNOWN_FIELD", f"line {lineno}: {name!r} is not a HENV1 field")
        if name in seen:
            _reject("HENV1_DUPLICATE_FIELD", f"line {lineno}: {name} appears twice")
        seen.add(name)
        pairs.append((name, value))
    if signature is None:
        _reject("HENV1_MISSING_FIELD", "the container carries no SIG")

    names = [name for name, _ in pairs]
    if "MODE" not in names:
        _reject("HENV1_MISSING_FIELD", "the container carries no MODE")
    mode = dict(pairs)["MODE"]
    if mode not in (MODE_STRICT, MODE_RECOVERABLE):
        _reject("HENV1_BAD_MODE", f"MODE must be {MODE_STRICT} or {MODE_RECOVERABLE}")
    expected = list(_expected_keys(mode))
    if names != expected:
        extra = set(names) - set(expected)
        missing = set(expected) - set(names)
        if extra & set(_HENV1_RECOVERY) or missing & set(_HENV1_RECOVERY):
            _reject("HENV1_SLOT_CARDINALITY",
                    "STRICT carries exactly PRIMARY and RECOVERABLE exactly PRIMARY plus RECOVERY")
        if missing:
            _reject("HENV1_MISSING_FIELD", f"the container is missing {', '.join(sorted(missing))}")
        _reject("HENV1_FIELD_ORDER", "HENV1 fields appear in one fixed canonical order")
    present = dict(pairs)

    if not _SEAT_RE.fullmatch(present["FROM"]):
        _reject("HENV1_BAD_SEAT", "FROM is one token of letters, digits, dot, dash or underscore")
    if not _KID_RE.fullmatch(present["FROM_KID"]):
        _reject("HENV1_BAD_KID", "FROM_KID is sha256:<64 lowercase hex>")
    for field in ("TO_HUMAN", "PRIMARY_KID"):
        if not _HUMAN_ID_RE.fullmatch(present[field]):
            _reject("HENV1_BAD_KID", f"{field} is human-id:sha256:<64 lowercase hex>")
    if present["TO_HUMAN"] != present["PRIMARY_KID"]:
        _reject("HENV1_IDENTITY_MISMATCH",
                "TO_HUMAN is the primary key identity; they cannot disagree")
    recovery_kid = present["RECOVERY_KID"]
    if mode == MODE_STRICT:
        if recovery_kid != NONE:
            _reject("HENV1_SLOT_CARDINALITY", "STRICT carries RECOVERY_KID:NONE and no recovery slot")
    else:
        if not _HUMAN_ID_RE.fullmatch(recovery_kid):
            _reject("HENV1_BAD_KID", "RECOVERY_KID is a full human-id or NONE")
        if recovery_kid == present["PRIMARY_KID"]:
            _reject("RECOVERY_KEY_NOT_DISTINCT",
                    "a recovery key must be cryptographically distinct from the primary key")

    primary_epk = _decode_epk(present["PRIMARY_EPK"])
    primary_wrap_nonce = _decode_nonce(present["PRIMARY_WRAP_NONCE"])
    primary_wrapped_cek = _decode_b64(present["PRIMARY_WRAPPED_CEK"], "HENV1_BAD_BASE64")
    if len(primary_wrapped_cek) != WRAPPED_CEK_BYTES:
        _reject("HENV1_BAD_WRAPPED_CEK",
                f"a wrapped CEK is exactly {WRAPPED_CEK_BYTES} bytes")
    payload_nonce = _decode_nonce(present["PAYLOAD_NONCE"])
    payload_ciphertext = _decode_b64(present["PAYLOAD_B64"], "HENV1_BAD_BASE64")
    if len(payload_ciphertext) < 16 or len(payload_ciphertext) > MAX_HLET_BYTES + 16:
        _reject("HENV1_BAD_PAYLOAD", "PAYLOAD_B64 is not one bounded AEAD ciphertext")

    recovery_epk = recovery_wrap_nonce = recovery_wrapped_cek = None
    if mode == MODE_RECOVERABLE:
        recovery_epk = _decode_epk(present["RECOVERY_EPK"])
        recovery_wrap_nonce = _decode_nonce(present["RECOVERY_WRAP_NONCE"])
        recovery_wrapped_cek = _decode_b64(present["RECOVERY_WRAPPED_CEK"],
                                           "HENV1_BAD_BASE64")
        if len(recovery_wrapped_cek) != WRAPPED_CEK_BYTES:
            _reject("HENV1_BAD_WRAPPED_CEK",
                    f"a wrapped CEK is exactly {WRAPPED_CEK_BYTES} bytes")

    parsed = HENV1(
        from_seat=present["FROM"],
        from_kid=present["FROM_KID"],
        to_human=present["TO_HUMAN"],
        mode=mode,
        primary_kid=present["PRIMARY_KID"],
        recovery_kid=recovery_kid,
        primary_epk=primary_epk,
        primary_wrap_nonce=primary_wrap_nonce,
        primary_wrapped_cek=primary_wrapped_cek,
        payload_nonce=payload_nonce,
        payload_ciphertext=payload_ciphertext,
        signature=signature,
        recovery_epk=recovery_epk,
        recovery_wrap_nonce=recovery_wrap_nonce,
        recovery_wrapped_cek=recovery_wrapped_cek,
    )
    if parsed.render() != text:
        _reject("HENV1_NONCANONICAL",
                "a container has exactly one byte representation; this one is not the "
                "canonical rendering of the fields it carries")
    return parsed


_VERIFIED = object()
_OPENED = object()


@dataclass(frozen=True)
class VerifiedHENV1:
    """A container whose sender signature has been verified. Minted by verify only."""

    parsed: HENV1
    sender_key: object
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _VERIFIED:
            _reject("UNVERIFIED_HENV1",
                    "a VerifiedHENV1 is minted by verify_sender() alone; constructing one "
                    "directly would assert a signature check that never ran")


@dataclass(frozen=True)
class OpenedHumanPrivateLetter:
    """Authenticated plaintext of one HENV1; minted only by a successful decrypt."""

    letter: HumanPrivateLetter
    verified: VerifiedHENV1
    slot: str
    letter_id: str
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _OPENED:
            _reject("UNOPENED_HUMAN_PRIVATE",
                    "an OpenedHumanPrivateLetter is minted by a successful authenticated "
                    "decrypt alone; the mint is not retained, so opened state cannot be "
                    "copied, replaced or transplanted")


def seal_human_private(letter: HumanPrivateLetter, *, sender_private_key, sender_seat: str,
                       recipient: HumanRecipient, mode: str) -> str:
    """Seal one letter for one human recipient and return canonical HENV1 text."""
    _require_crypto()
    if not isinstance(letter, HumanPrivateLetter):
        _reject("NOT_A_HUMAN_PRIVATE_LETTER", "sealing takes a HumanPrivateLetter")
    if not isinstance(sender_private_key, Ed25519PrivateKey):
        _reject("NOT_ED25519_PRIVATE_KEY", "the sender key must be an Ed25519 private key")
    if not isinstance(sender_seat, str) or not _SEAT_RE.fullmatch(sender_seat):
        _reject("BAD_SEAT", "FROM is one token of letters, digits, dot, dash or underscore")
    if not isinstance(recipient, HumanRecipient):
        _reject("NOT_A_HUMAN_RECIPIENT", "sealing takes a HumanRecipient")
    if mode not in (MODE_STRICT, MODE_RECOVERABLE):
        _reject("BAD_MODE", f"MODE must be {MODE_STRICT} or {MODE_RECOVERABLE}")
    if mode == MODE_RECOVERABLE:
        if recipient.recovery_public_key is None:
            _reject("RECOVERY_KEY_REQUIRED",
                    "RECOVERABLE requires an explicitly supplied, cryptographically "
                    "distinct recovery public key; recovery is never inferred")
    elif recipient.recovery_public_key is not None:
        _reject("RECOVERY_KEY_NOT_ALLOWED",
                "STRICT carries exactly one authorized key; choose RECOVERABLE explicitly")
    if letter.to_human != recipient.human_id:
        _reject("LETTER_RECIPIENT_MISMATCH",
                "the letter names a TO_HUMAN that is not this recipient identity")

    sender_kid = envelope.fingerprint(sender_private_key.public_key())
    recovery_kid = NONE
    if mode == MODE_RECOVERABLE:
        recovery_kid = human_id(recipient.recovery_public_key)

    cek = os.urandom(CEK_BYTES)
    payload_nonce = os.urandom(NONCE_BYTES)
    payload_bind = _payload_binding(sender_seat, sender_kid, recipient.human_id, mode,
                                    recipient.human_id, recovery_kid)
    payload_ciphertext = ChaCha20Poly1305(cek).encrypt(
        payload_nonce, letter.render(), payload_bind)

    def wrap(slot: str, recipient_kid: str, recipient_public_key) -> tuple:
        ephemeral = ec.generate_private_key(ec.SECP256R1())
        epk = ephemeral.public_key().public_bytes(
            Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        shared = ephemeral.exchange(ec.ECDH(), recipient_public_key)
        domain = CEK_PRIMARY_DOMAIN if slot == SLOT_PRIMARY else CEK_RECOVERY_DOMAIN
        wrap_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=epk,
                        info=domain).derive(shared)
        nonce = os.urandom(NONCE_BYTES)
        aad = _wrap_binding(sender_seat, sender_kid, recipient.human_id, mode,
                            slot, recipient_kid)
        return epk, nonce, ChaCha20Poly1305(wrap_key).encrypt(nonce, cek, aad)

    primary_epk, primary_nonce, primary_wrapped = wrap(
        SLOT_PRIMARY, recipient.human_id, recipient.primary_public_key)
    recovery_epk = recovery_nonce = recovery_wrapped = None
    if mode == MODE_RECOVERABLE:
        recovery_epk, recovery_nonce, recovery_wrapped = wrap(
            SLOT_RECOVERY, recovery_kid, recipient.recovery_public_key)

    unsigned = HENV1(
        from_seat=sender_seat,
        from_kid=sender_kid,
        to_human=recipient.human_id,
        mode=mode,
        primary_kid=recipient.human_id,
        recovery_kid=recovery_kid,
        primary_epk=primary_epk,
        primary_wrap_nonce=primary_nonce,
        primary_wrapped_cek=primary_wrapped,
        payload_nonce=payload_nonce,
        payload_ciphertext=payload_ciphertext,
        signature=b"",
        recovery_epk=recovery_epk,
        recovery_wrap_nonce=recovery_nonce,
        recovery_wrapped_cek=recovery_wrapped,
    )
    signature = sender_private_key.sign(signature_input(unsigned))
    return dataclasses.replace(unsigned, signature=signature).render()


def verify_sender(parsed: HENV1, registry: envelope.KeyRegistry) -> VerifiedHENV1:
    """Resolve the accepted sender key and verify the signature. Refusal or nothing."""
    _require_crypto()
    parsed = _require_parsed(parsed)
    if not isinstance(registry, envelope.KeyRegistry):
        _reject("NOT_A_REGISTRY", "verification takes a receiver-owned KeyRegistry")
    sender_key = registry.resolves(parsed.from_seat, parsed.from_kid)
    if sender_key is None:
        if not registry.accepted(parsed.from_seat):
            _reject("UNKNOWN_SENDER_KEY",
                    f"no accepted key for seat {parsed.from_seat!r}; this receiver never "
                    "granted it one")
        _reject("SENDER_KEY_NOT_ACCEPTED",
                f"seat {parsed.from_seat!r} does not accept this key fingerprint")
    try:
        sender_key.verify(parsed.signature, signature_input(parsed))
    except InvalidSignature:
        _reject("SIGNATURE_INVALID", "the Ed25519 signature does not cover this container")
    return VerifiedHENV1(parsed=parsed, sender_key=sender_key, binding=_VERIFIED)


def open_verified(verified: VerifiedHENV1, provider: HumanPrivateKeyProvider
                  ) -> OpenedHumanPrivateLetter:
    """Decrypt one verified container through an authorized provider.

    The provider identity is matched against the container's slot identities
    before any private-key operation; the CEK unwrap and payload decrypt then
    authenticate the exact binding the container was created under.
    """
    _require_crypto()
    if not isinstance(verified, VerifiedHENV1):
        _reject("NOT_VERIFIED_HENV1", "open takes a VerifiedHENV1; parse and verify first")
    if not isinstance(provider, HumanPrivateKeyProvider):
        _reject("NOT_A_PROVIDER",
                "a provider exposes a human identity and one P-256 ECDH operation")
    parsed = verified.parsed
    if provider.human_id == parsed.primary_kid:
        slot = SLOT_PRIMARY
    elif parsed.mode == MODE_RECOVERABLE and provider.human_id == parsed.recovery_kid:
        slot = SLOT_RECOVERY
    else:
        _reject("RECIPIENT_KEY_UNRELATED",
                "this provider is not an authorized decryptor of this container")

    if slot == SLOT_PRIMARY:
        epk, wrap_nonce, wrapped_cek = (parsed.primary_epk, parsed.primary_wrap_nonce,
                                        parsed.primary_wrapped_cek)
    else:
        epk, wrap_nonce, wrapped_cek = (parsed.recovery_epk, parsed.recovery_wrap_nonce,
                                        parsed.recovery_wrapped_cek)
    domain = CEK_PRIMARY_DOMAIN if slot == SLOT_PRIMARY else CEK_RECOVERY_DOMAIN
    try:
        shared = provider.exchange(epk)
        if not isinstance(shared, (bytes, bytearray)) or len(shared) != 32:
            _reject("BAD_PROVIDER_SHARED",
                    "the provider must return the 32-byte P-256 shared secret")
        wrap_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=epk,
                        info=domain).derive(bytes(shared))
        cek = ChaCha20Poly1305(wrap_key).decrypt(wrap_nonce, wrapped_cek,
                                                 wrap_aad(parsed, slot))
    except InvalidTag:
        _reject("CEK_UNWRAP_FAILED",
                "the wrapped CEK does not authenticate under this recipient key")
    try:
        plaintext = ChaCha20Poly1305(cek).decrypt(
            parsed.payload_nonce, parsed.payload_ciphertext, payload_aad(parsed))
    except InvalidTag:
        _reject("PAYLOAD_DECRYPT_FAILED",
                "the payload does not authenticate under the container binding")
    letter = HumanPrivateLetter.parse(plaintext)
    if letter.to_human != parsed.to_human:
        _reject("HLET1_INNER_TO_HUMAN_MISMATCH",
                "the decrypted letter names a different TO_HUMAN than its container")
    return OpenedHumanPrivateLetter(letter=letter, verified=verified, slot=slot,
                                    letter_id=letter_id(parsed), binding=_OPENED)


def open_human_private(container, *, provider: HumanPrivateKeyProvider,
                       sender_registry: envelope.KeyRegistry) -> OpenedHumanPrivateLetter:
    """The full receive path: bounded parse, signature verify, then provider work."""
    parsed = parse_henv1(container)
    verified = verify_sender(parsed, sender_registry)
    return open_verified(verified, provider)


# --------------------------------------------------------------------
# Target C: ciphertext-only store
# --------------------------------------------------------------------


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    letter_id: str
    path: Path


@dataclass(frozen=True)
class HumanPrivateListing:
    """Clear routing metadata genuinely present in one stored container."""

    letter_id: str
    from_seat: str
    from_kid: str
    mode: str
    primary_kid: str
    recovery_kid: str
    size_bytes: int


class HumanPrivateStore:
    """One receiver human's immutable ciphertext-only letter store.

    Delivery verifies and publishes without decryption. Listing reads clear
    container metadata only. Opening is explicit, provider-driven and writes
    nothing: no plaintext sidecar, subject index, body cache or read state.
    """

    def __init__(self, root, *, human_id: str, sender_registry: envelope.KeyRegistry):
        _require_crypto()
        if not isinstance(human_id, str) or not _HUMAN_ID_RE.fullmatch(human_id):
            _reject("BAD_HUMAN_ID", "HUMAN_ID is human-id:sha256:<64 lowercase hex>")
        if not isinstance(sender_registry, envelope.KeyRegistry):
            _reject("NOT_A_REGISTRY", "the store takes the receiver-owned KeyRegistry")
        self.human_id = human_id
        self.sender_registry = sender_registry
        self.root = Path(root) / HUMAN_DIR / human_id.rsplit(":", 1)[1]

    def letter_path(self, letter_id: str) -> Path:
        token = letter_id[len(HASH_PREFIX):] if isinstance(letter_id, str) \
            and letter_id.startswith(HASH_PREFIX) else ""
        if len(token) != 64 or not _HEX_RE.fullmatch(token):
            _reject("HUMAN_PRIVATE_BAD_LETTER_ID", "LETTER_ID is sha256:<64 lowercase hex>")
        return self.root / token / (token + HENV1_SUFFIX)

    def deliver(self, data) -> DeliveryResult:
        """Verify sender and recipient, then publish one immutable container."""
        parsed = parse_henv1(data)
        verify_sender(parsed, self.sender_registry)
        if parsed.to_human != self.human_id:
            _reject("HUMAN_PRIVATE_WRONG_RECIPIENT",
                    "this container is sealed to a different human identity")
        identity = letter_id(parsed)
        path = self.letter_path(identity)
        outcome = publish.publish_immutable(
            path, parsed.render().encode("utf-8"),
            conflict_code="HUMAN_PRIVATE_STORE_CONFLICT")
        status = DELIVERED if outcome == publish.PUBLISHED else DUPLICATE
        return DeliveryResult(status=status, letter_id=identity, path=path)

    def listing(self) -> tuple:
        entries = []
        if not self.root.exists():
            return ()
        for path in sorted(self.root.rglob("*" + HENV1_SUFFIX)):
            try:
                data = path.read_bytes()
            except OSError:
                _reject("HUMAN_PRIVATE_STORE_CORRUPT",
                        f"{path.name} cannot be read back from the store")
            try:
                parsed = parse_henv1(data)
            except SailangError:
                _reject("HUMAN_PRIVATE_STORE_CORRUPT",
                        f"{path.name} is not a canonical HENV1 container")
            identity = letter_id(parsed)
            if path.name != identity[len(HASH_PREFIX):] + HENV1_SUFFIX:
                _reject("HUMAN_PRIVATE_STORE_CORRUPT",
                        f"{path.name} does not agree with its own container identity")
            entries.append(HumanPrivateListing(
                letter_id=identity,
                from_seat=parsed.from_seat,
                from_kid=parsed.from_kid,
                mode=parsed.mode,
                primary_kid=parsed.primary_kid,
                recovery_kid=parsed.recovery_kid,
                size_bytes=len(data),
            ))
        return tuple(entries)

    def open(self, letter_id_value: str, *, provider: HumanPrivateKeyProvider
             ) -> OpenedHumanPrivateLetter:
        """Explicitly open one stored letter; nothing is written anywhere."""
        path = self.letter_path(letter_id_value)
        if not path.is_file():
            _reject("HUMAN_PRIVATE_LETTER_NOT_FOUND",
                    "no committed container with this LETTER_ID in this store")
        try:
            data = path.read_bytes()
        except OSError:
            _reject("HUMAN_PRIVATE_STORE_CORRUPT",
                    "the committed container cannot be read back from the store")
        parsed = parse_henv1(data)
        if letter_id(parsed) != letter_id_value:
            _reject("HUMAN_PRIVATE_STORE_CORRUPT",
                    "the stored bytes do not hash to the requested LETTER_ID")
        verified = verify_sender(parsed, self.sender_registry)
        if parsed.to_human != self.human_id:
            _reject("HUMAN_PRIVATE_WRONG_RECIPIENT",
                    "this container is sealed to a different human identity")
        if not isinstance(provider, HumanPrivateKeyProvider):
            _reject("NOT_A_PROVIDER",
                    "a provider exposes a human identity and one P-256 ECDH operation")
        if provider.human_id not in (self.human_id, parsed.recovery_kid):
            _reject("RECIPIENT_KEY_UNRELATED",
                    "this provider is not an authorized decryptor of this store's letters")
        return open_verified(verified, provider)


__all__ = [
    "CEK_PRIMARY_DOMAIN", "CEK_RECOVERY_DOMAIN", "CONTAINER_FORMAT", "DELIVERED",
    "DUPLICATE", "DeliveryResult", "HENV1", "HUMAN_ID_PREFIX", "HUMAN_DIR",
    "HumanPrivateKeyProvider", "HumanPrivateLetter", "HumanPrivateListing",
    "HumanPrivateStore", "HumanRecipient", "LETTER_CLASS", "MAX_BODY_BYTES",
    "MAX_HLET_BYTES", "MAX_SUBJECT_BYTES", "MODE_RECOVERABLE", "MODE_STRICT",
    "OpenedHumanPrivateLetter", "PAYLOAD_DOMAIN", "PLAINTEXT_FORMAT",
    "SIGNATURE_DOMAIN", "SLOT_PRIMARY", "SLOT_RECOVERY", "SoftwareP256Provider",
    "VerifiedHENV1", "human_id", "letter_id", "open_human_private", "open_verified",
    "parse_henv1", "payload_aad", "seal_human_private", "signature_input",
    "verify_sender", "wrap_aad",
]
