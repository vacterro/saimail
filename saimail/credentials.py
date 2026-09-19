"""Persistent local credential resolver for SAIRoute / 9router.

The canonical path, and the only one an ordinary command takes:

    credential://9router/sairoute  ->  local credential resolver
                                   ->  Windows Credential Manager (WinVault)
                                   ->  transport

The defect class this module eliminates: **an inherited environment variable
silently standing in for a provisioned credential.** A secret that arrives from
the ambient environment is a secret nobody can point at, rotate or revoke, and
a resolver that quietly prefers it turns the credential store into decoration.

So there is no precedence rule here. A caller names exactly one source
(D-019):

* ``SOURCE_STORE`` (the default) reads the credential store and nothing else.
  A missing credential is ``SAIROUTE_CREDENTIAL_NOT_PROVISIONED``, never a
  quiet fall-through to the environment.
* ``SOURCE_ENV`` is the explicit legacy/debug mode, selected by the caller and
  recorded in whatever artifact the caller writes. It reads the environment
  variable and nothing else.

Nothing in this module prints, logs, returns in a ``repr`` or stores a secret
value. :class:`ResolvedCredential` carries the secret and hides it from
``repr``; the label beside it is what an artifact may keep.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional, Protocol

DEFAULT_HANDLE = "credential://9router/sairoute"
_HANDLE_RE = re.compile(r"^credential://([^/]+)/(.+)$")

#: The environment variable the legacy/debug source reads. It is never read by
#: the default source, and naming it here does not give it precedence.
LEGACY_ENV_VAR = "SAIROUTE_API_KEY"

#: The two declared sources. There is no third, and no order between them.
SOURCE_STORE = "store"
SOURCE_ENV = "env"
SOURCES = (SOURCE_STORE, SOURCE_ENV)

#: The backend this module claims when it says "Windows Credential Manager".
#: Nothing below claims it because ``keyring`` imported; it is checked.
WINDOWS_BACKEND = "keyring.backends.Windows.WinVaultKeyring"
#: Backends that cannot be the declared persistent local store, whatever the
#: platform: two that store nothing, and the alt file backend, which is a
#: plaintext file wearing a keyring costume.
UNSUITABLE_BACKENDS = frozenset({
    "keyring.backends.fail.Keyring",
    "keyring.backends.null.Keyring",
    "keyrings.alt.file.PlaintextKeyring",
})


class CredentialError(RuntimeError):
    """Base error for credential resolution."""


class CredentialNotProvisioned(CredentialError):
    """Named operational error when the required credential is missing."""


class BackendError(CredentialError):
    """Raised when the backing store fails."""


class UnsuitableBackend(BackendError):
    """The selected keyring backend is not the declared persistent local store."""


class CredentialStore(Protocol):
    def get(self, handle: str) -> Optional[str]: ...
    def set(self, handle: str, secret: str) -> None: ...
    def delete(self, handle: str) -> bool: ...


def parse_handle(handle: str) -> tuple[str, str]:
    m = _HANDLE_RE.match(handle)
    if not m:
        raise CredentialError(
            f"Invalid credential handle format: {handle!r}. "
            "Expected credential://<service>/<username>"
        )
    return m.group(1), m.group(2)


@dataclass(frozen=True)
class ResolvedCredential:
    """A secret plus the label of where it came from.

    ``secret`` never reaches ``repr``: a dataclass that prints its own fields is
    how a credential ends up in a traceback, a log line and then an artifact.
    """

    secret: str = field(repr=False)
    source: str
    handle: str
    backend: Optional[str] = None

    def __str__(self) -> str:  # pragma: no cover - defensive, same as repr
        return repr(self)


def _backend_name(backend: object) -> str:
    return f"{type(backend).__module__}.{type(backend).__name__}"


def _resolve_chain(backend: object) -> object:
    """The backend that actually answers, looking through keyring's chainer.

    ``ChainerBackend`` is a dispatcher, not a store; claiming it would say
    nothing about where a secret lands.
    """
    seen = set()
    while True:
        name = _backend_name(backend)
        members = getattr(backend, "backends", None)
        if name not in ("keyring.backends.chainer.ChainerBackend",) or not members:
            return backend
        if id(backend) in seen:  # pragma: no cover - a cyclic chain would hang
            return backend
        seen.add(id(backend))
        viable = [b for b in members if _backend_name(b) not in UNSUITABLE_BACKENDS]
        if not viable:
            return backend
        backend = viable[0]


class KeyringCredentialStore:
    """The persistent local store, with its backend checked rather than assumed.

    On Windows the declared store is Windows Credential Manager, so the only
    accepted backend is ``WinVaultKeyring``. Everywhere else any backend that
    is not in :data:`UNSUITABLE_BACKENDS` is accepted: this module makes no
    claim about what a non-Windows host persists into.
    """

    def __init__(self, require_backend: bool = True) -> None:
        self._require_backend = require_backend
        try:
            import keyring
            self._keyring = keyring
        except ImportError:
            self._keyring = None

    # ---------------------------------------------------------------- backend

    def backend_name(self) -> str:
        """The dotted name of the backend that would answer. Never a secret."""
        self._require_keyring()
        try:
            return _backend_name(_resolve_chain(self._keyring.get_keyring()))
        except Exception as exc:  # noqa: BLE001 - an unreadable backend is an error
            raise BackendError(
                f"SAIROUTE_CREDENTIAL_BACKEND_UNREADABLE: {type(exc).__name__}"
            ) from None

    def check_backend(self) -> str:
        """Return the backend name, or raise the named operational error."""
        name = self.backend_name()
        if name in UNSUITABLE_BACKENDS:
            raise UnsuitableBackend(
                f"SAIROUTE_CREDENTIAL_BACKEND_UNSUITABLE: keyring selected {name}, which is "
                "not a persistent local credential store"
            )
        if sys.platform == "win32" and name != WINDOWS_BACKEND:
            raise UnsuitableBackend(
                f"SAIROUTE_CREDENTIAL_BACKEND_UNSUITABLE: this host is Windows and the declared "
                f"store is Windows Credential Manager ({WINDOWS_BACKEND}), but keyring selected "
                f"{name}"
            )
        return name

    def _require_keyring(self) -> None:
        if self._keyring is None:
            raise BackendError(
                "keyring package is not installed; install with pip install -e .[credentials]"
            )

    def _ready(self) -> None:
        self._require_keyring()
        if self._require_backend:
            self.check_backend()

    # ------------------------------------------------------------------ store

    def get(self, handle: str) -> Optional[str]:
        self._ready()
        service, username = parse_handle(handle)
        try:
            return self._keyring.get_password(service, username)
        except Exception:
            raise BackendError("Failed to retrieve credential from backing store") from None

    def set(self, handle: str, secret: str) -> None:
        self._ready()
        if not secret:
            raise CredentialError("Secret must not be empty")
        service, username = parse_handle(handle)
        try:
            self._keyring.set_password(service, username, secret)
        except Exception:
            raise BackendError("Failed to store credential in backing store") from None

    def delete(self, handle: str) -> bool:
        """Delete a credential, distinguishing absence from backend failure (W2-006).

        ``False`` means absence was actually established through the backing
        store; a failure of the store while reading or deleting a known-present
        credential raises :class:`BackendError`. Swallowing that difference
        would make revocation indistinguishable from an empty shelf.
        """
        self._ready()
        service, username = parse_handle(handle)
        try:
            present = self._keyring.get_password(service, username)
        except Exception:
            raise BackendError("Failed to retrieve credential from backing store") from None
        if present is None:
            return False
        try:
            self._keyring.delete_password(service, username)
        except Exception:
            raise BackendError("Failed to delete credential from backing store") from None
        return True


class InMemoryCredentialStore:
    """Injectable in-memory store for isolated unit tests."""

    def __init__(self, initial: Optional[dict[str, str]] = None,
                 fail_on: Optional[set[str]] = None) -> None:
        self._data: dict[str, str] = dict(initial or {})
        self._fail_on: set[str] = set(fail_on or ())

    def backend_name(self) -> str:
        return "saimail.credentials.InMemoryCredentialStore"

    def check_backend(self) -> str:
        return self.backend_name()

    def get(self, handle: str) -> Optional[str]:
        parse_handle(handle)
        if "get" in self._fail_on:
            raise BackendError("Simulated backend failure on get")
        return self._data.get(handle)

    def set(self, handle: str, secret: str) -> None:
        parse_handle(handle)
        if "set" in self._fail_on:
            raise BackendError("Simulated backend failure on set")
        if not secret:
            raise CredentialError("Secret must not be empty")
        self._data[handle] = secret

    def delete(self, handle: str) -> bool:
        parse_handle(handle)
        if "delete" in self._fail_on:
            raise BackendError("Simulated backend failure on delete")
        if handle in self._data:
            del self._data[handle]
            return True
        return False


_ACTIVE_STORE: Optional[CredentialStore] = None


def set_credential_store(store: Optional[CredentialStore]) -> None:
    global _ACTIVE_STORE
    _ACTIVE_STORE = store


def get_credential_store() -> CredentialStore:
    global _ACTIVE_STORE
    if _ACTIVE_STORE is not None:
        return _ACTIVE_STORE
    return KeyringCredentialStore()


def backend_label(store: Optional[CredentialStore] = None) -> str:
    """A non-secret label for the backend in use, for an artifact or a report."""
    s = store or get_credential_store()
    name = getattr(s, "backend_name", None)
    if callable(name):
        try:
            return name()
        except BackendError as exc:
            return str(exc).split(":", 1)[0]
    return type(s).__module__ + "." + type(s).__name__


def resolve(handle: str = DEFAULT_HANDLE, source: str = SOURCE_STORE,
            store: Optional[CredentialStore] = None) -> ResolvedCredential:
    """Resolve the credential for ``handle`` from exactly the named source.

    ``SOURCE_STORE`` never reads the environment and ``SOURCE_ENV`` never reads
    the store. Neither falls through to the other: a source is an authority, and
    two authorities with an invisible order between them is the defect this
    replaces.
    """
    if source not in SOURCES:
        raise CredentialError(
            f"Unknown credential source {source!r}; expected one of {SOURCES}")

    if source == SOURCE_ENV:
        secret = os.environ.get(LEGACY_ENV_VAR) or ""
        if not secret:
            raise CredentialNotProvisioned(
                f"SAIROUTE_CREDENTIAL_NOT_PROVISIONED: legacy source {SOURCE_ENV!r} was selected "
                f"and {LEGACY_ENV_VAR} is unset or empty. The canonical path is the credential "
                f"store: python tools/provision_sairoute_credential.py"
            )
        return ResolvedCredential(secret=secret, source=SOURCE_ENV, handle=handle,
                                  backend=f"environment:{LEGACY_ENV_VAR}")

    s = store or get_credential_store()
    secret = s.get(handle)
    if not secret:
        raise CredentialNotProvisioned(
            f"SAIROUTE_CREDENTIAL_NOT_PROVISIONED: No credential found for {handle}. "
            "Please run: python tools/provision_sairoute_credential.py"
        )
    return ResolvedCredential(secret=secret, source=SOURCE_STORE, handle=handle,
                              backend=backend_label(s))


def resolve_credential(handle: str = DEFAULT_HANDLE,
                       store: Optional[CredentialStore] = None,
                       source: str = SOURCE_STORE) -> str:
    """The secret alone, for a caller that does not record where it came from.

    Defaults to the credential store. There is no environment fall-through;
    pass ``source=SOURCE_ENV`` to select the legacy variable explicitly.
    """
    return resolve(handle=handle, source=source, store=store).secret
