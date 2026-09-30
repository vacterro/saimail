"""Workspace identity key custody at rest (V3-01).

The defect class this module eliminates: a persistent workspace whose identity
private keys live in the workspace directory itself, so copying the directory
copies the identity. V2-01 stored raw hex Ed25519/X25519 software keys in
``identity/identity.json`` and stated that limitation honestly (spec/17 section
10); this module is the bounded custody boundary that removes the raw bytes
from the workspace for operators who select it.

This is STORAGE POLICY ONLY. It adds no protocol rule, no new cryptography, no
wire-format change and no network path. It reuses the already-tested credential
store abstraction (:mod:`saimail.credentials`) under a SEPARATE namespace --
never the SAIRoute ``credential://9router/sairoute`` handle and never its
authority domain.

What the selected protection claims, and no more: a copied workspace directory
does not contain the private key bytes; the keys require an OS credential-store
access in the authorized user context; a missing or wrong store fails closed
instead of regenerating or falling back to raw material. It does NOT claim
protection from malware running as the same user, administrator or kernel
compromise, human identity proof, hardware isolation, physical-presence
enforcement, forward secrecy or automatic recovery. Those claims are recorded
in spec/20-LOCAL-KEY-CUSTODY-v0.md, not here.

Failure semantics are named, never collapsed (see spec/20 section 6):
``CUSTODY_BACKEND_UNAVAILABLE``, ``CUSTODY_BACKEND_UNSUITABLE``,
``CUSTODY_KEY_MISSING``, ``CUSTODY_KEY_MISMATCH``, ``CUSTODY_ACCESS_FAILED``
and ``CUSTODY_MIGRATION_CONFLICT``. No error carries a private key value; a
handle is a location label, not a secret.
"""

from __future__ import annotations

import re

from sailang import SailangError
from saimail.credentials import (
    BackendError,
    CredentialStore,
    UnsuitableBackend,
    get_credential_store,
)

#: Three custody modes. ``raw`` is the V2-01 legacy layout; ``os-store``
#: keeps the private bytes in the OS credential store and only handles plus
#: public material in the workspace. ``master-key`` stores password-wrapped keys.
CUSTODY_RAW = "raw"
CUSTODY_OS_STORE = "os-store"
CUSTODY_MASTER_KEY = "master-key"
CUSTODY_MODES = (CUSTODY_RAW, CUSTODY_OS_STORE, CUSTODY_MASTER_KEY)

#: The service segment of a workspace custody handle. Deliberately not
#: ``9router``: SAIRoute transport credentials and workspace identity custody
#: are separate authority domains (V3-01 handoff) and must never share an entry.
HANDLE_SERVICE = "saimail-workspace"
HANDLE_PREFIX = f"credential://{HANDLE_SERVICE}/"

ROLE_SENDER = "sender"
ROLE_RECIPIENT = "recipient"
ROLES = (ROLE_SENDER, ROLE_RECIPIENT)

#: Named failure codes (spec/20 section 6). Missing credential, backend
#: failure and identity mismatch stay mechanically distinct so operator
#: recovery information survives.
CUSTODY_BACKEND_UNAVAILABLE = "CUSTODY_BACKEND_UNAVAILABLE"
CUSTODY_BACKEND_UNSUITABLE = "CUSTODY_BACKEND_UNSUITABLE"
CUSTODY_KEY_MISSING = "CUSTODY_KEY_MISSING"
CUSTODY_KEY_MISMATCH = "CUSTODY_KEY_MISMATCH"
CUSTODY_ACCESS_FAILED = "CUSTODY_ACCESS_FAILED"
CUSTODY_MIGRATION_CONFLICT = "CUSTODY_MIGRATION_CONFLICT"

#: Idempotent repeat of a completed migration; not an error.
CUSTODY_ALREADY_PROTECTED = "CUSTODY_ALREADY_PROTECTED"

CUSTODY_CODES = frozenset({
    CUSTODY_BACKEND_UNAVAILABLE,
    CUSTODY_BACKEND_UNSUITABLE,
    CUSTODY_KEY_MISSING,
    CUSTODY_KEY_MISMATCH,
    CUSTODY_ACCESS_FAILED,
    CUSTODY_MIGRATION_CONFLICT,
})

_SEAT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_HEX32_RE = re.compile(r"^[0-9a-f]{64}$")
_KID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _kid_digest(kid: str) -> str:
    if not isinstance(kid, str) or not _KID_RE.match(kid):
        _reject(CUSTODY_KEY_MISMATCH, "a key fingerprint is sha256:<64 lowercase hex>")
    return kid.split(":", 1)[1]


def handle_for(seat: str, role: str, kid: str) -> str:
    """The one handle format for one workspace key, derived from public data.

    ``credential://saimail-workspace/<seat>/<role>/<fingerprint-digest>``. The
    digest binds the handle to the exact identity, so two workspaces that reuse
    a seat name but hold different keys cannot collide in the store.
    """
    if not isinstance(seat, str) or not _SEAT_RE.match(seat):
        _reject(CUSTODY_MIGRATION_CONFLICT, "a workspace seat is one address token")
    if role not in ROLES:
        _reject(CUSTODY_MIGRATION_CONFLICT, f"unknown custody role {role!r}")
    return f"{HANDLE_PREFIX}{seat}/{role}/{_kid_digest(kid)}"


def handle_matches(handle, *, seat: str, role: str, kid: str) -> bool:
    """Structural check: does this handle claim exactly this workspace key?"""
    if not isinstance(handle, str) or not handle.startswith(HANDLE_PREFIX):
        return False
    try:
        expected = handle_for(seat, role, kid)
    except SailangError:
        return False
    return handle == expected


def validate_hex_key(value, *, what: str) -> str:
    """One private key value as stored: exactly 32 raw bytes of lowercase hex."""
    if not isinstance(value, str) or not _HEX32_RE.match(value):
        _reject(CUSTODY_KEY_MISMATCH,
                f"{what} is not 32 raw bytes of lowercase hex; refusing to serve it")
    return value


def _map_backend_error(exc: BaseException, *, doing: str, handle: str) -> None:
    if isinstance(exc, UnsuitableBackend):
        _reject(CUSTODY_BACKEND_UNSUITABLE,
                f"the credential-store backend is unsuitable for workspace custody "
                f"while {doing} {handle}: {exc}")
    if isinstance(exc, BackendError):
        _reject(CUSTODY_ACCESS_FAILED,
                f"the credential store failed while {doing} {handle}: {exc}")


def resolve_store(store: CredentialStore | None = None) -> CredentialStore:
    return store if store is not None else get_credential_store()


def _require_available(store: CredentialStore) -> None:
    """A store object can only answer if its backing module exists here.

    ``KeyringCredentialStore`` records an absent keyring package as
    ``_keyring = None``. That is "no store on this host", which must be named
    apart from a failing store; for any other store object this check is inert.
    """
    if getattr(store, "_keyring", "present") is None:
        _reject(CUSTODY_BACKEND_UNAVAILABLE,
                "the keyring package is not installed; protected custody requires it "
                "(install with pip install -e .[credentials])")


def classify_backend(store: CredentialStore | None = None) -> str:
    """The dotted backend name that would answer, or a named refusal.

    Checked rather than assumed, exactly as in the SAIRoute resolver: keyring
    importing is not evidence that a persistent local store answered.
    """
    s = resolve_store(store)
    _require_available(s)
    check = getattr(s, "check_backend", None)
    try:
        if callable(check):
            return str(check())
        return str(s.backend_name())  # type: ignore[attr-defined]
    except SailangError:
        raise
    except (UnsuitableBackend, BackendError) as exc:
        _map_backend_error(exc, doing="classify the store for", handle="workspace custody")
    except Exception as exc:  # noqa: BLE001 - an unreadable store is an error, never assumed
        _reject(CUSTODY_BACKEND_UNAVAILABLE,
                f"the credential-store backend is unreadable: {type(exc).__name__}")
    raise AssertionError("unreachable")


def read_key(store: CredentialStore | None, handle: str) -> str:
    """Retrieve one private key value; absence and backend failure stay distinct."""
    classify_backend(store)
    s = resolve_store(store)
    try:
        value = s.get(handle)
    except SailangError:
        raise
    except (UnsuitableBackend, BackendError) as exc:
        _map_backend_error(exc, doing="read", handle=handle)
    except Exception as exc:  # noqa: BLE001
        _reject(CUSTODY_ACCESS_FAILED,
                f"the credential store failed while reading {handle}: {type(exc).__name__}")
    if value is None:
        _reject(CUSTODY_KEY_MISSING,
                f"no private key material is stored for {handle}; the workspace fails "
                f"closed and nothing is regenerated")
    return value


def write_key(store: CredentialStore | None, handle: str, value: str) -> bool:
    """Store one private key value without overwriting a different identity.

    Returns ``True`` when the entry was created by this call, ``False`` when an
    identical value was already present (an interrupted earlier attempt that
    reached the same identity). A different value under the same handle is
    ``CUSTODY_MIGRATION_CONFLICT``: no silent substitution, ever.
    """
    validate_hex_key(value, what="the private key to store")
    classify_backend(store)
    s = resolve_store(store)
    try:
        existing = s.get(handle)
    except SailangError:
        raise
    except (UnsuitableBackend, BackendError) as exc:
        _map_backend_error(exc, doing="inspect", handle=handle)
    except Exception as exc:  # noqa: BLE001
        _reject(CUSTODY_ACCESS_FAILED,
                f"the credential store failed while inspecting {handle}: {type(exc).__name__}")
    if existing is not None:
        if existing == value:
            return False
        _reject(CUSTODY_MIGRATION_CONFLICT,
                f"{handle} already holds a different key; refusing to overwrite it")
    try:
        s.set(handle, value)
    except SailangError:
        raise
    except (UnsuitableBackend, BackendError) as exc:
        _map_backend_error(exc, doing="write", handle=handle)
    except Exception as exc:  # noqa: BLE001
        _reject(CUSTODY_ACCESS_FAILED,
                f"the credential store failed while writing {handle}: {type(exc).__name__}")
    return True


def release_keys(store: CredentialStore | None, handles) -> list[str]:
    """Best-effort removal of entries this run created, for failed attempts.

    Returns the handles that could not be removed. Never raises: the caller is
    already handling a failure, and a cleanup problem must be reported beside
    that failure, not replace it with a different one.
    """
    s = resolve_store(store)
    remaining: list[str] = []
    for handle in handles:
        try:
            s.delete(handle)
        except Exception:  # noqa: BLE001 - cleanup is reported, never raised
            remaining.append(handle)
    return remaining


def key_present(store: CredentialStore | None, handle: str) -> bool | None:
    """Presence only, for a diagnostic; ``None`` when the store cannot answer."""
    s = resolve_store(store)
    try:
        return s.get(handle) is not None
    except Exception:  # noqa: BLE001 - status is a report, not an operation
        return None


__all__ = [
    "CUSTODY_ACCESS_FAILED",
    "CUSTODY_ALREADY_PROTECTED",
    "CUSTODY_BACKEND_UNAVAILABLE",
    "CUSTODY_BACKEND_UNSUITABLE",
    "CUSTODY_CODES",
    "CUSTODY_KEY_MISMATCH",
    "CUSTODY_KEY_MISSING",
    "CUSTODY_MASTER_KEY",
    "CUSTODY_MIGRATION_CONFLICT",
    "CUSTODY_MODES",
    "CUSTODY_OS_STORE",
    "CUSTODY_RAW",
    "HANDLE_PREFIX",
    "HANDLE_SERVICE",
    "ROLES",
    "ROLE_RECIPIENT",
    "ROLE_SENDER",
    "classify_backend",
    "handle_for",
    "handle_matches",
    "key_present",
    "read_key",
    "release_keys",
    "resolve_store",
    "validate_hex_key",
    "write_key",
]
