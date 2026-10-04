"""SAIENVELOPE v0 (SENV2) — the sealed message container.

One recipient, one clear header, one sealed payload. The contract is
`spec/02-SAIENVELOPE-v0.md` and `spec/DECISIONS.md` D-028/D-034; this module
implements it and never invents a second one.

The API makes the unsafe order difficult to reach:

    parse_header(text) -> Header                bounded, cheap, no crypto
    verify(header, registry) -> VerifiedEnvelope   hash, acceptance, signature
    open(verified, recipient_private_key, recipient_registry) -> bytes
                                                recipient binding, then decrypt

Plaintext exists only after signature verification succeeded. Nothing here
parses the payload: opened bytes are data, and the caller decides what, if
anything, they mean (I1).

SENV2 binds the sender identity into the sealed layer (D-034): the AEAD
associated data is the sender-binding domain marker plus the exact
`FROM`/`FROM_KID` pair, so a relabelled and re-signed copy of an existing
ciphertext fails decryption instead of opening under a new sender. SENV1 is
retired; a `SENV1` first line refuses `LEGACY_VERSION`, and no legacy decode
path exists (D-033 records why SENV1 was insufficient).

Every key and every payload is used, never stored. Error messages carry a code
and a bounded detail; they never quote the payload and never quote key bytes.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from dataclasses import InitVar, dataclass
from datetime import datetime
from typing import Iterable, Mapping, Optional, Tuple

from sailang.errors import SailangError

try:  # cryptography is a declared extra; the library keeps no runtime dependency
    from cryptography.exceptions import InvalidSignature, InvalidTag
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
        X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    _CRYPTO_IMPORT_ERROR: Optional[BaseException] = None
except ImportError as _exc:  # pragma: no cover - exercised only without the extra
    _CRYPTO_IMPORT_ERROR = _exc

FORMAT_VERSION = "SENV2"
SIGNATURE_ALGORITHM = "ed25519"
HASH_PREFIX = "sha256:"

#: The one signature domain marker (D-029, renamed for the SENV2 wire in
#: D-034). Ed25519 signs this exact prefix followed by the canonical unsigned
#: header bytes -- never the field block alone, so a signature can never be
#: replayed into another protocol context.
SIGNATURE_DOMAIN = b"SAIMAIL-SENV2-SIGNATURE\x00"

#: The sender-binding domain marker (D-034). The AEAD associated data is this
#: prefix followed by the exact canonical sender identity bytes, so the sealed
#: layer authenticates the `FROM`/`FROM_KID` pair the ciphertext was sealed
#: under. CIPHER_HASH and SIG are never part of the AEAD associated data.
SENDER_BINDING_DOMAIN = b"SAIMAIL-SENV2-SENDER-BINDING\x00"

#: The closed kind set of spec/02 section 3.
KINDS = frozenset({
    "DISCOVERY", "EXPERIENCE", "WARNING", "QUESTION", "HYPOTHESIS",
    "MEMORY_FRAGMENT", "PERSONAL_MESSAGE", "PROTOCOL_PROPOSAL",
})

#: The one canonical header order (D-028). SIG is not here: it is excluded
#: from its own signature and always rendered last.
HEADER_ORDER = ("FROM", "FROM_KID", "TO", "TO_KID", "K", "TOPIC", "CREATED",
                "TTL", "REF", "CIPHER_HASH", "EPK", "NONCE")
MANDATORY_FIELDS = ("FROM", "FROM_KID", "TO", "TO_KID", "K", "TOPIC", "CREATED",
                    "CIPHER_HASH", "EPK", "NONCE")
OPTIONAL_FIELDS = ("TTL", "REF")

#: Declared bounds (D-028, B8). Enforced before any crypto call.
MAX_HEADER_BYTES = 4096
MAX_FIELDS = 24
MAX_VALUE_BYTES = 1024
MAX_CONTAINER_BYTES = 384 * 1024
MAX_PLAINTEXT_BYTES = 256 * 1024
MAX_CIPHERTEXT_BYTES = 256 * 1024 + 16
NONCE_BYTES = 12

#: The HKDF context string that domain-separates payload keys (D-034). The
#: SENV1 info string is deliberately not reused across the wire transition, so
#: no SENV1 and SENV2 payload key can coincide for the same shared secret.
HKDF_INFO = b"SAIMAIL-SENV2-PAYLOAD-KEY\x00"

_SEAT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TOPIC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_KID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_TTL_RE = re.compile(r"^[0-9]{1,5}[DH]$")
_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_HEX_RE = re.compile(r"^[0-9a-f]+$")
_BOM = "\ufeff"


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _require_crypto() -> None:
    if _CRYPTO_IMPORT_ERROR is not None:
        _reject("CRYPTO_UNAVAILABLE",
                "the cryptography package is not installed; install with "
                "pip install -e .[crypto]")


@dataclass(frozen=True)
class Header:
    """One parsed clear header plus the decoded ciphertext.

    ``pairs`` is in canonical order and never contains SIG; ``signature`` holds
    the decoded signature bytes.
    """

    pairs: Tuple[Tuple[str, str], ...]
    signature: bytes
    ciphertext: bytes

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        for name, value in self.pairs:
            if name == key:
                return value
        return default


#: Only successful verification may mint this. A VerifiedEnvelope is the
#: type-state proof that the signature gate ran; an ordinary constructor call
#: must never manufacture it (T-39/CORE-002).
_VERIFIED = object()


@dataclass(frozen=True)
class VerifiedEnvelope:
    """A header whose signature has been verified against an accepted key.

    Constructed only by :func:`verify`; the constructor refuses anything that
    does not carry the module-private mint, so an unauthenticated header cannot
    be relabelled as verified state and passed to :func:`open` (T-39/CORE-002).
    The mint is a constructor-only ``InitVar`` (T-40) and is not retained, so
    one verified envelope cannot be copied, replaced or transplanted onto
    another header. Python privacy stops accidents, not adversaries (D-015):
    the type exists so no ordinary caller can reach :func:`open` with
    unverified bytes.
    """

    header: Header
    sender_key: "Ed25519PublicKey"
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _VERIFIED:
            _reject(
                "UNVERIFIED_ENVELOPE",
                "a VerifiedEnvelope is minted by verify() alone; constructing one directly "
                "would assert a signature check that never ran",
            )


#: Only a successful AEAD open may mint this. An OpenedEnvelope is the
#: type-state proof that its plaintext bytes were obtained from the exact
#: envelope its VerifiedEnvelope describes (T-42/Target B).
_OPENED = object()


@dataclass(frozen=True)
class OpenedEnvelope:
    """The authenticated payload of one verified envelope: the exact plaintext.

    Constructed only by :func:`open`, after parse, signature verification,
    recipient acceptance and a successful AEAD decryption have all run for one
    envelope; an ordinary constructor call must never manufacture it. The mint
    is a constructor-only ``InitVar`` (the T-40 pattern) and is not retained,
    so opened state cannot be copied, replaced or transplanted onto other
    plaintext or another envelope.

    The payload is the only promotion-grade provenance there is (D-035): a
    ``VerifiedEnvelope`` authenticates the container, not any record, so a
    caller handing a record and a container to a gate proves nothing about the
    record. Here the plaintext is bound to its envelope mechanically, and
    ``envelope_id`` names the canonical container bytes it came out of (the
    parser accepts exactly one byte representation, D-032, so re-rendering the
    verified header reproduces them).

    This is a correctness / type-state boundary over the normal public API,
    not hostile-process security: Python privacy stops accidents, not
    adversaries (D-015).
    """

    verified: VerifiedEnvelope
    plaintext: bytes
    envelope_id: str
    binding: InitVar[object] = None

    def __post_init__(self, binding: object) -> None:
        if binding is not _OPENED:
            _reject(
                "UNOPENED_ENVELOPE",
                "an OpenedEnvelope is minted by open() alone; constructing one directly "
                "would assert plaintext nobody decrypted out of any envelope",
            )


class KeyRegistry:
    """Receiver-owned acceptance: which exact sender keys belong to a seat.

    Identity and acceptance are separate things (D-028, B4). The envelope
    states which key claims the message; this registry states which key the
    receiver accepts for that seat. An unknown seat or an unaccepted
    fingerprint refuses; there is no silent first-contact trust.
    """

    def __init__(self, entries: Optional[Mapping[str, Iterable["Ed25519PublicKey"]]] = None):
        self._keys: dict = {}
        for seat, keys in (entries or {}).items():
            for key in keys:
                self.accept(seat, key)

    def accept(self, seat: str, public_key: "Ed25519PublicKey") -> str:
        _require_crypto()
        if not isinstance(seat, str) or not _SEAT_RE.match(seat):
            _reject("BAD_SEAT", "a seat is one token of letters, digits, dot, dash or underscore")
        if not isinstance(public_key, Ed25519PublicKey):
            _reject("NOT_ED25519_KEY", "sender acceptance takes Ed25519 public keys only")
        accepted = self._keys.get(seat, ())
        if public_key not in accepted:
            self._keys[seat] = accepted + (public_key,)
        return fingerprint(public_key)

    def accepted(self, seat: str) -> Tuple["Ed25519PublicKey", ...]:
        return self._keys.get(seat, ())

    def resolves(self, seat: str, kid: str) -> Optional["Ed25519PublicKey"]:
        for key in self._keys.get(seat, ()):
            if fingerprint(key) == kid:
                return key
        return None


class RecipientKeyRegistry:
    """Receiver-owned acceptance: which exact recipient keys belong to a seat.

    The mirror of :class:`KeyRegistry` on the recipient side (D-030). The
    envelope states which key it was sealed to; this registry states which key
    the receiver accepts for that seat. The normal open path binds all three:
    the header's ``TO`` seat, its ``TO_KID`` fingerprint, and the presented
    private key. A sender can neither enroll nor redefine a recipient
    identity: the registry is held by the receiver and is never built from
    envelope bytes. There is no silent first-contact trust.
    """

    def __init__(self, entries: Optional[Mapping[str, Iterable["X25519PublicKey"]]] = None):
        self._keys: dict = {}
        for seat, keys in (entries or {}).items():
            for key in keys:
                self.accept(seat, key)

    def accept(self, seat: str, public_key: "X25519PublicKey") -> str:
        _require_crypto()
        if not isinstance(seat, str) or not _SEAT_RE.match(seat):
            _reject("BAD_SEAT", "a seat is one token of letters, digits, dot, dash or underscore")
        if not isinstance(public_key, X25519PublicKey):
            _reject("NOT_X25519_KEY", "recipient acceptance takes X25519 public keys only")
        accepted = self._keys.get(seat, ())
        if public_key not in accepted:
            self._keys[seat] = accepted + (public_key,)
        return fingerprint(public_key)

    def accepted(self, seat: str) -> Tuple["X25519PublicKey", ...]:
        return self._keys.get(seat, ())

    def resolves(self, seat: str, kid: str) -> Optional["X25519PublicKey"]:
        for key in self._keys.get(seat, ()):
            if fingerprint(key) == kid:
                return key
        return None


def fingerprint(public_key) -> str:
    """Full key identity: ``sha256:<hex>`` over the raw 32-byte public key.

    Never a shortened display prefix (D-028, B3).
    """
    _require_crypto()
    if not isinstance(public_key, (Ed25519PublicKey, X25519PublicKey)):
        _reject("NOT_A_PUBLIC_KEY", "a fingerprint needs an Ed25519 or X25519 public key")
    raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return HASH_PREFIX + hashlib.sha256(raw).hexdigest()


def canonical_header_bytes(header: Header) -> bytes:
    """The canonical unsigned header bytes (D-028, B2).

    Every header line except SIG, in the canonical order, LF, UTF-8, no BOM,
    final LF. Nothing depends on dict iteration or parser normalization.
    These bytes are the header half of :func:`signature_input`; they are never
    signed on their own.
    """
    lines = [f"{key}:{value}" for key, value in header.pairs]
    return ("\n".join(lines) + "\n").encode("utf-8")


def signature_input(header: Header) -> bytes:
    """The one exact byte sequence a signature covers (D-029, D-034).

    The SENV2 protocol domain marker followed by the canonical unsigned header
    bytes. SIG is excluded from its own input; CIPHER_HASH, EPK, NONCE and
    every other header field are inside it. One sequence, one meaning.
    """
    return SIGNATURE_DOMAIN + canonical_header_bytes(header)


def sender_binding_bytes(from_seat: str, from_kid: str) -> bytes:
    """The one exact byte sequence bound into the AEAD (D-034).

    The sender-binding domain marker followed by the canonical sender
    identity: ``FROM:<seat>\\nFROM_KID:<full fingerprint>\\n``, UTF-8, LF,
    final LF, fixed field order. Both values are parser-constrained (a seat
    token cannot contain a newline or an ambiguous colon; the fingerprint is a
    fixed ``sha256:<64 hex>`` shape), so the serialization is one-to-one. It is
    constructed only from these two fields in this order -- never from dict
    iteration -- and it is the associated data of every SENV2 encryption and
    decryption, which is what makes a relabelled ciphertext refuse to open.
    """
    identity = f"FROM:{from_seat}\nFROM_KID:{from_kid}\n"
    return SENDER_BINDING_DOMAIN + identity.encode("utf-8")


def envelope_id(container) -> str:
    """Deterministic transport-object identity (D-031).

    ``sha256`` over the exact container bytes: same bytes, same id; the same
    plaintext sealed again is normally a different transport object with a
    different id. No key, no parsing and no decryption are required -- which is
    why it takes raw bytes and hashes whatever it is given. It is the identity
    of a *transport object* only where those bytes are a container
    :func:`parse_header` accepts, and there exactly one byte representation per
    logical envelope is accepted (D-028, D-032), so one envelope has one id.
    Never plaintext, semantic-message, knowledge, evidence, sender or trust
    identity.
    """
    if isinstance(container, str):
        data = container.encode("utf-8")
    elif isinstance(container, (bytes, bytearray)):
        data = bytes(container)
    else:
        _reject("NON_TEXT_INPUT", "a container is text or UTF-8 bytes")
    return HASH_PREFIX + hashlib.sha256(data).hexdigest()


def seal(payload, *, sender_private_key: "Ed25519PrivateKey", sender_seat: str,
         recipient_seat: str, recipient_public_key: "X25519PublicKey",
         kind: str, topic: str, created: str, ttl: Optional[str] = None,
         ref: Optional[str] = None) -> str:
    """Seal one payload for one recipient and return the canonical container.

    ``payload`` is bytes, or text that is encoded as UTF-8. The payload is not
    parsed: sealing a command-shaped string is sealing data.
    """
    _require_crypto()
    if not isinstance(sender_private_key, Ed25519PrivateKey):
        _reject("NOT_ED25519_PRIVATE_KEY", "the sender key must be an Ed25519 private key")
    if not isinstance(recipient_public_key, X25519PublicKey):
        _reject("NOT_X25519_PUBLIC_KEY", "the recipient key must be an X25519 public key")
    _check_seat("FROM", sender_seat)
    _check_seat("TO", recipient_seat)
    if kind not in KINDS:
        _reject("BAD_KIND", f"K must be one of the closed kind set, got {kind!r}")
    if not isinstance(topic, str) or not _TOPIC_RE.match(topic):
        _reject("BAD_TOPIC", "TOPIC is one token of letters, digits, dot, dash or underscore")
    _check_utc(created)
    if ttl is not None and (not isinstance(ttl, str) or not _TTL_RE.match(ttl)):
        _reject("BAD_TTL", "TTL is a count followed by D or H")
    if ref is not None and (not isinstance(ref, str) or not _KID_RE.match(ref)):
        _reject("BAD_REF", "REF is sha256:<64 lowercase hex>")

    if isinstance(payload, str):
        payload_bytes = payload.encode("utf-8")
    elif isinstance(payload, (bytes, bytearray)):
        payload_bytes = bytes(payload)
    else:
        _reject("NON_BYTES_PAYLOAD", "a payload is bytes or text")
    if len(payload_bytes) > MAX_PLAINTEXT_BYTES:
        _reject("PAYLOAD_OVERSIZE",
                f"payload exceeds {MAX_PLAINTEXT_BYTES} bytes; the container refuses before encrypting")

    ephemeral = X25519PrivateKey.generate()
    ephemeral_raw = ephemeral.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    shared = ephemeral.exchange(recipient_public_key)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=ephemeral_raw,
               info=HKDF_INFO).derive(shared)
    nonce = os.urandom(NONCE_BYTES)
    # The sender identity is fixed before encryption and becomes the AEAD
    # associated data (D-034): the pair is bound into the sealed layer, so no
    # later field rewrite can reopen these ciphertext bytes under another FROM.
    sender_kid = fingerprint(sender_private_key.public_key())
    aad = sender_binding_bytes(sender_seat, sender_kid)
    ciphertext = ChaCha20Poly1305(key).encrypt(nonce, payload_bytes, aad)

    fields = [("FROM", sender_seat), ("FROM_KID", sender_kid),
              ("TO", recipient_seat), ("TO_KID", fingerprint(recipient_public_key)),
              ("K", kind), ("TOPIC", topic), ("CREATED", created)]
    if ttl is not None:
        fields.append(("TTL", ttl))
    if ref is not None:
        fields.append(("REF", ref))
    fields.extend([("CIPHER_HASH", HASH_PREFIX + hashlib.sha256(ciphertext).hexdigest()),
                   ("EPK", ephemeral_raw.hex()), ("NONCE", nonce.hex())])

    header = Header(pairs=tuple(fields), signature=b"", ciphertext=ciphertext)
    signature = sender_private_key.sign(signature_input(header))
    return _render(header, signature)


def _render(header: Header, signature: bytes) -> str:
    lines = [FORMAT_VERSION]
    lines.extend(f"{key}:{value}" for key, value in header.pairs)
    lines.append(f"SIG:{SIGNATURE_ALGORITHM}:{signature.hex()}")
    lines.append("")
    lines.append("CIPHERTEXT:" + base64.b64encode(header.ciphertext).decode("ascii"))
    return "\n".join(lines) + "\n"


def parse_header(data) -> Header:
    """Parse one container into a bounded :class:`Header`. No crypto happens here.

    Cheap validation first: representation, size, field count, canonical order,
    field shapes, base64. A malformed input never reaches a crypto operation.
    """
    if isinstance(data, (bytes, bytearray)):
        raw = bytes(data)
        if raw[:3] == b"\xef\xbb\xbf":
            _reject("BOM_PRESENT", "a container is UTF-8 without BOM")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            _reject("NOT_UTF8", "a container body is UTF-8 or it is not a container body")
    elif isinstance(data, str):
        text = data
        if text.startswith(_BOM):
            _reject("BOM_PRESENT", "a container is UTF-8 without BOM")
    else:
        _reject("NON_TEXT_INPUT", "a container is text or UTF-8 bytes")
    if "\r" in text:
        _reject("CANONICAL_LF_REQUIRED", "line ends are LF; a CR would be a second representation")
    if len(text.encode("utf-8")) > MAX_CONTAINER_BYTES:
        _reject("CONTAINER_OVERSIZE", f"container exceeds {MAX_CONTAINER_BYTES} bytes")

    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        _reject("EMPTY_INPUT", "no content")
    if lines[0] == "SENV1":
        _reject("LEGACY_VERSION",
                "SENV1 is retired (D-034): its accepted-peer relabel limitation (D-033) has no "
                "downgrade path, and no legacy decode exists in the ordinary receive path")
    if lines[0] != FORMAT_VERSION:
        _reject("BAD_VERSION", f"line 1 must be exactly {FORMAT_VERSION!r}")
    if "" not in lines:
        _reject("MISSING_SEPARATOR", "a blank line separates the clear header from the ciphertext")
    separator = lines.index("")
    header_lines = lines[1:separator]
    tail = lines[separator + 1:]
    if len(tail) != 1 or not tail[0].startswith("CIPHERTEXT:"):
        _reject("TRAILING_CONTENT",
                "exactly one CIPHERTEXT line follows the separator; nothing else is a container")

    header_bytes = len("\n".join(header_lines).encode("utf-8"))
    if header_bytes > MAX_HEADER_BYTES:
        _reject("HEADER_OVERSIZE", f"clear header exceeds {MAX_HEADER_BYTES} bytes")
    if len(header_lines) > MAX_FIELDS + 1:
        _reject("TOO_MANY_FIELDS", f"clear header carries more than {MAX_FIELDS} fields")

    pairs: list = []
    signature: Optional[bytes] = None
    expected_position = {key: number for number, key in enumerate(HEADER_ORDER)}
    last_position = -1
    for lineno, raw_line in enumerate(header_lines, start=2):
        if ":" not in raw_line:
            _reject("MALFORMED_FIELD", f"header line {lineno} is not KEY:VALUE")
        key, value = raw_line.split(":", 1)
        if len(value.encode("utf-8")) > MAX_VALUE_BYTES:
            _reject("VALUE_OVERSIZE", f"header line {lineno} exceeds {MAX_VALUE_BYTES} bytes")
        if key == "SIG":
            if signature is not None:
                _reject("DUPLICATE_FIELD", "SIG appears twice")
            if lineno != len(header_lines) + 1:
                _reject("FIELD_ORDER", "SIG is the last header line, over everything before it")
            prefix = SIGNATURE_ALGORITHM + ":"
            if not value.startswith(prefix):
                _reject("BAD_SIGNATURE", f"SIG must be {prefix}<128 lowercase hex>")
            body = value[len(prefix):]
            if len(body) != 128 or not _HEX_RE.match(body):
                _reject("BAD_SIGNATURE", "SIG must be ed25519:<128 lowercase hex>")
            signature = bytes.fromhex(body)
            continue
        if key not in expected_position:
            _reject("UNKNOWN_FIELD", f"header line {lineno}: {key!r} is not a SENV2 field")
        if any(name == key for name, _ in pairs):
            _reject("DUPLICATE_FIELD", f"header line {lineno}: {key} appears twice")
        position = expected_position[key]
        if position <= last_position:
            _reject("FIELD_ORDER", f"header line {lineno}: {key} is out of canonical order")
        last_position = position
        pairs.append((key, value))
    if signature is None:
        _reject("MISSING_FIELD", "the header carries no SIG")

    names = {name for name, _ in pairs}
    missing = [key for key in MANDATORY_FIELDS if key not in names]
    if missing:
        _reject("MISSING_FIELD", f"the header is missing {', '.join(missing)}")
    present = dict(pairs)

    _check_seat("FROM", present["FROM"])
    _check_seat("TO", present["TO"])
    if not _KID_RE.match(present["FROM_KID"]):
        _reject("BAD_KID", "FROM_KID is sha256:<64 lowercase hex>")
    if not _KID_RE.match(present["TO_KID"]):
        _reject("BAD_KID", "TO_KID is sha256:<64 lowercase hex>")
    if present["K"] not in KINDS:
        _reject("BAD_KIND", f"K must be one of the closed kind set, got {present['K']!r}")
    if not _TOPIC_RE.match(present["TOPIC"]):
        _reject("BAD_TOPIC", "TOPIC is one token of letters, digits, dot, dash or underscore")
    _check_utc(present["CREATED"])
    if "TTL" in present and not _TTL_RE.match(present["TTL"]):
        _reject("BAD_TTL", "TTL is a count followed by D or H")
    if "REF" in present and not _KID_RE.match(present["REF"]):
        _reject("BAD_REF", "REF is sha256:<64 lowercase hex>")
    if not _KID_RE.match(present["CIPHER_HASH"]):
        _reject("BAD_CIPHER_HASH", "CIPHER_HASH is sha256:<64 lowercase hex>")

    epk = present["EPK"]
    if len(epk) != 64 or not _HEX_RE.match(epk):
        _reject("BAD_EPK", "EPK is 64 lowercase hex characters")
    nonce = present["NONCE"]
    if len(nonce) != 2 * NONCE_BYTES or not _HEX_RE.match(nonce):
        _reject("BAD_NONCE", f"NONCE is {2 * NONCE_BYTES} lowercase hex characters")

    encoded = tail[0][len("CIPHERTEXT:"):]
    if len(encoded) > 4 * (MAX_CIPHERTEXT_BYTES // 3 + 2):
        _reject("CIPHERTEXT_OVERSIZE", f"ciphertext exceeds {MAX_CIPHERTEXT_BYTES} bytes")
    try:
        ciphertext = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        _reject("BAD_CIPHERTEXT", "CIPHERTEXT is standard base64 with padding")
    if len(ciphertext) > MAX_CIPHERTEXT_BYTES:
        _reject("CIPHERTEXT_OVERSIZE", f"ciphertext exceeds {MAX_CIPHERTEXT_BYTES} bytes")

    header = Header(pairs=tuple(pairs), signature=signature, ciphertext=ciphertext)
    # One logical envelope, one byte representation (D-028, D-032). Comparing
    # the input against its own canonical rendering closes every second
    # representation at once -- a missing final LF, a non-canonical base64 last
    # quantum, or any later serializer slack -- so a transport object cannot be
    # minted twice under two ENVELOPE_IDs (D-031).
    if text != _render(header, signature):
        _reject("NON_CANONICAL_CONTAINER",
                "a container has exactly one byte representation; this one is not the "
                "canonical serialization of the header and ciphertext it carries")
    return header


def verify(header: Header, registry: KeyRegistry) -> VerifiedEnvelope:
    """Authenticate the encrypted body, then its sender. Refusal or nothing.

    Order follows D-028: ciphertext hash, accepted sender key, signature. A
    failure raises; there is no warn-and-continue path.
    """
    _require_crypto()
    if not isinstance(header, Header):
        _reject("NOT_A_HEADER", "verify takes a parsed Header")
    if not isinstance(registry, KeyRegistry):
        _reject("NOT_A_REGISTRY", "verify takes a receiver-owned KeyRegistry")

    recorded = header.get("CIPHER_HASH")
    actual = HASH_PREFIX + hashlib.sha256(header.ciphertext).hexdigest()
    if recorded != actual:
        _reject("CIPHER_HASH_MISMATCH",
                "the ciphertext does not hash to CIPHER_HASH; the body was changed or corrupted")

    seat = header.get("FROM")
    kid = header.get("FROM_KID")
    sender_key = registry.resolves(seat, kid)
    if sender_key is None:
        if not registry.accepted(seat):
            _reject("UNKNOWN_SENDER_KEY",
                    f"no accepted key for seat {seat!r}; this receiver never granted it one")
        _reject("SENDER_KEY_NOT_ACCEPTED",
                f"seat {seat!r} does not accept this key fingerprint")
    try:
        sender_key.verify(header.signature, signature_input(header))
    except InvalidSignature:
        _reject("SIGNATURE_INVALID", "the Ed25519 signature does not cover this header")
    return VerifiedEnvelope(header=header, sender_key=sender_key, binding=_VERIFIED)


def open(verified: VerifiedEnvelope, recipient_private_key: "X25519PrivateKey",
         recipient_registry: RecipientKeyRegistry) -> OpenedEnvelope:
    """Decrypt a verified envelope for a recipient the receiver accepts.

    Three things must agree before any decryption (D-030): the header's ``TO``
    seat is known to the receiver-owned registry, its ``TO_KID`` fingerprint is
    accepted for that seat, and the presented private key matches that
    fingerprint. The return value is the :class:`OpenedEnvelope` carrying the
    exact decrypted bytes; nothing here parses them.
    """
    _require_crypto()
    if not isinstance(verified, VerifiedEnvelope):
        _reject("NOT_VERIFIED", "open takes a VerifiedEnvelope; parse and verify first")
    if not isinstance(recipient_private_key, X25519PrivateKey):
        _reject("NOT_X25519_PRIVATE_KEY", "the recipient key must be an X25519 private key")
    if not isinstance(recipient_registry, RecipientKeyRegistry):
        _reject("NOT_A_RECIPIENT_REGISTRY", "open takes a receiver-owned RecipientKeyRegistry")

    seat = verified.header.get("TO")
    kid = verified.header.get("TO_KID")
    if not recipient_registry.accepted(seat):
        _reject("UNKNOWN_RECIPIENT_SEAT",
                f"no accepted key for seat {seat!r}; this receiver never granted it one")
    if recipient_registry.resolves(seat, kid) is None:
        _reject("RECIPIENT_KEY_NOT_ACCEPTED",
                f"seat {seat!r} does not accept this recipient key fingerprint")
    if kid != fingerprint(recipient_private_key.public_key()):
        _reject("RECIPIENT_KEY_MISMATCH",
                "this envelope is sealed to a different recipient key")

    header = verified.header
    try:
        epk_bytes = bytes.fromhex(header.get("EPK"))
        nonce = bytes.fromhex(header.get("NONCE"))
        ephemeral_public = X25519PublicKey.from_public_bytes(epk_bytes)
        shared = recipient_private_key.exchange(ephemeral_public)
        key = HKDF(algorithm=hashes.SHA256(), length=32, salt=epk_bytes,
                   info=HKDF_INFO).derive(shared)
        # The sealed layer rebinds the same sender identity the header states
        # (D-034). A relabelled header re-signs cleanly but reconstructs a
        # different authentication context here, and the AEAD refuses it as
        # DECRYPTION_FAILED -- not as a signature failure.
        aad = sender_binding_bytes(header.get("FROM"), header.get("FROM_KID"))
        plaintext = ChaCha20Poly1305(key).decrypt(nonce, header.ciphertext, aad)
    except (ValueError, InvalidTag):
        _reject("DECRYPTION_FAILED",
                "the ciphertext does not authenticate under this recipient key")
    # ENVELOPE_ID over the exact canonical container bytes (D-031, D-032):
    # parse_header refuses any second byte representation, so re-rendering the
    # verified header reproduces the bytes this plaintext was sealed in
    canonical = _render(header, header.signature)
    return OpenedEnvelope(
        verified=verified,
        plaintext=plaintext,
        envelope_id=HASH_PREFIX + hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        binding=_OPENED,
    )


def _check_seat(field: str, value) -> None:
    if not isinstance(value, str) or not _SEAT_RE.match(value):
        _reject("BAD_SEAT",
                f"{field} is one token of letters, digits, dot, dash or underscore")


def _check_utc(value) -> None:
    if not isinstance(value, str) or not _UTC_RE.match(value):
        _reject("BAD_CREATED", "CREATED must be YYYY-MM-DDTHH:MM:SSZ")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        _reject("BAD_CREATED", "CREATED is not a real UTC instant")
