"""SAINOTE — the human twin of a sealed envelope (spec/02 §6, T-8).

SAINOTE is not a downgraded envelope. It is the explainability surface:
human-readable prose over the *same clear header*, with no sealed payload and
no TTL by default. Where a sealed discovery later changes a shared decision,
the decision's rationale must be expressible as a SAINOTE — a conclusion whose
reasoning cannot be stated to a human does not get to steer shared work.

Two rules shape this module:

* **I2 — observable but private.** Every sealed envelope has a fully clear
  header: existence, addressing, kind, topic and time are always readable.
  :func:`clear_header` is that check, and it refuses anything it cannot read.
* **Provenance before narration.** The renderer takes a ``VerifiedEnvelope``,
  never raw bytes: a note narrating an unauthenticated header would lend
  narrative authority to bytes nobody verified.

The module renders; it never writes, never parses payloads and never decrypts
anything.
"""

from __future__ import annotations

from typing import Optional

from sailang.errors import SailangError

from saimail import envelope

MARKER = "SAINOTE"

#: The clear, human-relevant header fields, in the canonical envelope order.
CLEAR_FIELDS = ("FROM", "FROM_KID", "TO", "TO_KID", "K", "TOPIC", "CREATED", "REF")
#: Sealing artifacts: real on the envelope, absent from the human twin.
CRYPTO_FIELDS = ("CIPHER_HASH", "EPK", "NONCE")
#: Lifetime metadata: shown only when the caller asks (spec/02 §6).
CONDITIONAL_FIELDS = ("TTL",)

#: Kind names in words, so a human reads meaning, not a code (spec/02 §3).
KIND_WORDS = {
    "DISCOVERY": "something found",
    "EXPERIENCE": "something lived through",
    "WARNING": "something that will bite the reader",
    "QUESTION": "an open problem handed to someone else",
    "HYPOTHESIS": "a guess with a falsification condition",
    "MEMORY_FRAGMENT": "a fact worth carrying, not yet worth promoting",
    "PERSONAL_MESSAGE": "agent to agent, about the recipient's own behaviour",
    "PROTOCOL_PROPOSAL": "a suggested rule change",
}


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def clear_header(container) -> dict:
    """The I2 check: every sealed envelope has a fully clear header.

    Parses the container with the bounded, crypto-free parser and returns the
    clear addressing fields. Anything unreadable, incomplete or not a container
    refuses by name — privacy of content never becomes invisibility of traffic.
    """
    header = envelope.parse_header(container)
    missing = [field for field in ("FROM", "FROM_KID", "TO", "TO_KID", "K",
                                   "TOPIC", "CREATED")
               if header.get(field) is None]
    if missing:
        _reject("HEADER_NOT_CLEAR",
                f"an envelope header is always clear; {', '.join(missing)} unreadable")
    return {field: header.get(field) for field in CLEAR_FIELDS if header.get(field)}


def render(verified: "envelope.VerifiedEnvelope", *, with_ttl: bool = False) -> str:
    """Render the human-readable twin of one verified envelope.

    Same clear header, prose the reader can act on, no sealed payload, and no
    TTL unless the caller explicitly asks for it. The sender's key fingerprint
    travels too: for a human note, verifiability beats brevity.
    """
    if not isinstance(verified, envelope.VerifiedEnvelope):
        _reject("NOT_VERIFIED",
                "a SAINOTE narrates a header the receiver verified; raw bytes would lend "
                "narrative authority to something unauthenticated")
    header = verified.header
    get = header.get
    lines = [MARKER]
    lines.extend(f"{field}:{get(field)}" for field in CLEAR_FIELDS if get(field))
    if with_ttl and get("TTL"):
        lines.append(f"TTL:{get('TTL')}")
    kind = get("K")
    body = (f"{get('FROM')} sent {get('TO')} {KIND_WORDS.get(kind, 'a message')} "
            f"about {get('TOPIC')} on {get('CREATED')}.")
    if get("REF"):
        body += f" It refers to {get('REF')}."
    body += " The payload is sealed; this note is the clear twin of its header."
    return "\n".join(lines) + "\n\n" + body + "\n"
