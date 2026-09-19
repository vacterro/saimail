"""The canonical credential path: one named source, an interactive-only prompt,
a checked backend, and no secret anywhere it can be read back (D-019)."""

from __future__ import annotations

import io
import os
import sys

import pytest

from saimail.credentials import (
    DEFAULT_HANDLE,
    LEGACY_ENV_VAR,
    SOURCE_ENV,
    SOURCE_STORE,
    UNSUITABLE_BACKENDS,
    WINDOWS_BACKEND,
    BackendError,
    CredentialError,
    CredentialNotProvisioned,
    InMemoryCredentialStore,
    KeyringCredentialStore,
    ResolvedCredential,
    UnsuitableBackend,
    backend_label,
    parse_handle,
    resolve,
    resolve_credential,
    set_credential_store,
)
from tools import provision_sairoute_credential as provision

FAKE_SECRET = "sk-test-secret-value-abc-123"
OTHER_SECRET = "sk-test-secret-value-xyz-789"
ENV_SECRET = "sk-test-environment-value-999"


@pytest.fixture(autouse=True)
def clean_store():
    store = InMemoryCredentialStore()
    set_credential_store(store)
    old_env = os.environ.get(LEGACY_ENV_VAR)
    os.environ.pop(LEGACY_ENV_VAR, None)
    yield store
    set_credential_store(None)
    if old_env is not None:
        os.environ[LEGACY_ENV_VAR] = old_env
    else:
        os.environ.pop(LEGACY_ENV_VAR, None)


class FakeKeyring:
    """A keyring module stand-in: one backend object and a dict of secrets."""

    def __init__(self, backend, data=None, raises=None):
        self._backend = backend
        self._data = dict(data or {})
        self._raises = raises

    def get_keyring(self):
        if self._raises:
            raise self._raises
        return self._backend

    def get_password(self, service, username):
        return self._data.get((service, username))

    def set_password(self, service, username, secret):
        self._data[(service, username)] = secret

    def delete_password(self, service, username):
        del self._data[(service, username)]


def _named_backend(module, name):
    return type(name, (), {"__module__": module})()


def _store_with(backend, data=None, raises=None):
    store = KeyringCredentialStore()
    store._keyring = FakeKeyring(backend, data, raises)
    return store


# ------------------------------------------------------------------ handles


def test_parse_handle_valid():
    service, username = parse_handle("credential://9router/sairoute")
    assert service == "9router"
    assert username == "sairoute"


def test_parse_handle_invalid():
    with pytest.raises(CredentialError) as exc_info:
        parse_handle("invalid://handle")
    assert "Invalid credential handle format" in str(exc_info.value)


# ------------------------------------------------------- one source, no order


def test_the_store_is_the_default_source(clean_store):
    clean_store.set(DEFAULT_HANDLE, FAKE_SECRET)
    assert resolve_credential(DEFAULT_HANDLE, store=clean_store) == FAKE_SECRET
    resolved = resolve(DEFAULT_HANDLE, store=clean_store)
    assert resolved.source == SOURCE_STORE
    assert resolved.handle == DEFAULT_HANDLE


def test_the_environment_can_never_stand_in_for_the_store(clean_store, monkeypatch):
    """The defect D-019 removes: an inherited variable resolving silently."""
    monkeypatch.setenv(LEGACY_ENV_VAR, ENV_SECRET)
    with pytest.raises(CredentialNotProvisioned) as exc_info:
        resolve_credential(DEFAULT_HANDLE, store=clean_store)
    assert "SAIROUTE_CREDENTIAL_NOT_PROVISIONED" in str(exc_info.value)
    assert ENV_SECRET not in str(exc_info.value)


def test_the_store_wins_because_it_is_the_only_source_asked(clean_store, monkeypatch):
    monkeypatch.setenv(LEGACY_ENV_VAR, ENV_SECRET)
    clean_store.set(DEFAULT_HANDLE, FAKE_SECRET)
    assert resolve_credential(DEFAULT_HANDLE, store=clean_store) == FAKE_SECRET


def test_the_legacy_source_is_explicit_and_reads_only_the_variable(clean_store, monkeypatch):
    monkeypatch.setenv(LEGACY_ENV_VAR, ENV_SECRET)
    clean_store.set(DEFAULT_HANDLE, FAKE_SECRET)
    resolved = resolve(DEFAULT_HANDLE, source=SOURCE_ENV, store=clean_store)
    assert resolved.secret == ENV_SECRET
    assert resolved.source == SOURCE_ENV
    assert resolved.backend == f"environment:{LEGACY_ENV_VAR}"


def test_the_legacy_source_refuses_when_the_variable_is_unset(clean_store):
    with pytest.raises(CredentialNotProvisioned) as exc_info:
        resolve(DEFAULT_HANDLE, source=SOURCE_ENV, store=clean_store)
    assert LEGACY_ENV_VAR in str(exc_info.value)


def test_an_unknown_source_is_refused_not_guessed(clean_store):
    with pytest.raises(CredentialError) as exc_info:
        resolve(DEFAULT_HANDLE, source="somewhere", store=clean_store)
    assert "Unknown credential source" in str(exc_info.value)


def test_a_resolved_credential_never_prints_its_secret():
    resolved = ResolvedCredential(secret=FAKE_SECRET, source=SOURCE_STORE, handle=DEFAULT_HANDLE)
    assert FAKE_SECRET not in repr(resolved)
    assert FAKE_SECRET not in str(resolved)
    assert FAKE_SECRET not in f"{resolved}"
    assert resolved.secret == FAKE_SECRET


# ------------------------------------------------------------------- errors


def test_credential_absent(clean_store):
    with pytest.raises(CredentialNotProvisioned) as exc_info:
        resolve_credential(DEFAULT_HANDLE, store=clean_store)
    msg = str(exc_info.value)
    assert "SAIROUTE_CREDENTIAL_NOT_PROVISIONED" in msg
    assert "python tools/provision_sairoute_credential.py" in msg
    assert FAKE_SECRET not in msg


def test_backend_failure_on_get(clean_store):
    failing_store = InMemoryCredentialStore(fail_on={"get"})
    with pytest.raises(BackendError) as exc_info:
        resolve_credential(DEFAULT_HANDLE, store=failing_store)
    assert "Simulated backend failure on get" in str(exc_info.value)


def test_backend_failure_on_set():
    failing_store = InMemoryCredentialStore(fail_on={"set"})
    with pytest.raises(BackendError):
        failing_store.set(DEFAULT_HANDLE, FAKE_SECRET)


def test_credential_replacement_is_rotation(clean_store):
    clean_store.set(DEFAULT_HANDLE, FAKE_SECRET)
    assert resolve_credential(DEFAULT_HANDLE, store=clean_store) == FAKE_SECRET
    clean_store.set(DEFAULT_HANDLE, OTHER_SECRET)
    assert resolve_credential(DEFAULT_HANDLE, store=clean_store) == OTHER_SECRET


def test_credential_delete(clean_store):
    clean_store.set(DEFAULT_HANDLE, FAKE_SECRET)
    assert clean_store.delete(DEFAULT_HANDLE) is True
    assert clean_store.get(DEFAULT_HANDLE) is None
    assert clean_store.delete(DEFAULT_HANDLE) is False


def test_secret_never_appears_in_exception_text(clean_store):
    with pytest.raises(Exception) as exc_info:
        clean_store.set("invalid-handle", FAKE_SECRET)
    assert FAKE_SECRET not in str(exc_info.value)

    failing_store = InMemoryCredentialStore(fail_on={"set"})
    with pytest.raises(Exception) as exc_info:
        failing_store.set(DEFAULT_HANDLE, FAKE_SECRET)
    assert FAKE_SECRET not in str(exc_info.value)


# ------------------------------------------------- the backend claim is checked


def test_the_windows_backend_claim_is_checked_not_assumed(monkeypatch):
    """Importing keyring is not evidence that WinVault answered."""
    monkeypatch.setattr(sys, "platform", "win32")
    module, name = WINDOWS_BACKEND.rsplit(".", 1)
    good = _store_with(_named_backend(module, name))
    assert good.check_backend() == WINDOWS_BACKEND

    bad = _store_with(_named_backend("keyrings.alt.file", "PlaintextKeyring"))
    with pytest.raises(UnsuitableBackend) as exc_info:
        bad.check_backend()
    assert "SAIROUTE_CREDENTIAL_BACKEND_UNSUITABLE" in str(exc_info.value)
    assert "PlaintextKeyring" in str(exc_info.value)


def test_a_backend_that_stores_nothing_is_refused_on_every_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    for dotted in sorted(UNSUITABLE_BACKENDS):
        module, name = dotted.rsplit(".", 1)
        store = _store_with(_named_backend(module, name))
        with pytest.raises(UnsuitableBackend):
            store.check_backend()


def test_a_non_windows_host_accepts_any_persistent_backend(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    store = _store_with(_named_backend("keyring.backends.SecretService", "Keyring"))
    assert store.check_backend() == "keyring.backends.SecretService.Keyring"


def test_the_chainer_is_looked_through_rather_than_claimed(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    module, name = WINDOWS_BACKEND.rsplit(".", 1)
    winvault = _named_backend(module, name)
    fail = _named_backend("keyring.backends.fail", "Keyring")
    chainer = _named_backend("keyring.backends.chainer", "ChainerBackend")
    chainer.backends = [fail, winvault]
    store = _store_with(chainer)
    assert store.check_backend() == WINDOWS_BACKEND


def test_an_unsuitable_backend_blocks_reads_and_writes(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    store = _store_with(_named_backend("keyring.backends.fail", "Keyring"))
    with pytest.raises(UnsuitableBackend):
        store.get(DEFAULT_HANDLE)
    with pytest.raises(UnsuitableBackend):
        store.set(DEFAULT_HANDLE, FAKE_SECRET)
    with pytest.raises(UnsuitableBackend):
        store.delete(DEFAULT_HANDLE)


def test_an_unreadable_backend_is_a_named_error(monkeypatch):
    store = _store_with(None, raises=RuntimeError("no keyring here"))
    with pytest.raises(BackendError) as exc_info:
        store.backend_name()
    assert "SAIROUTE_CREDENTIAL_BACKEND_UNREADABLE" in str(exc_info.value)


def test_backend_label_is_never_a_secret(clean_store):
    clean_store.set(DEFAULT_HANDLE, FAKE_SECRET)
    label = backend_label(clean_store)
    assert label == "saimail.credentials.InMemoryCredentialStore"
    assert FAKE_SECRET not in label


# -------------------------------------------------- interactive provisioning


def _provision_store(monkeypatch, store=None):
    store = store or InMemoryCredentialStore()
    monkeypatch.setattr(provision, "KeyringCredentialStore", lambda: store)
    return store


def test_provisioning_reads_a_non_echoing_prompt_and_confirms_it(capsys, monkeypatch):
    store = _provision_store(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    typed = []

    def fake_getpass(prompt=""):
        typed.append(prompt)
        return FAKE_SECRET

    monkeypatch.setattr(provision.getpass, "getpass", fake_getpass)
    assert provision.main([]) == 0
    assert len(typed) == 2, "the secret is typed twice and compared"
    captured = capsys.readouterr()
    assert "Successfully stored credential for credential://9router/sairoute" in captured.out
    assert FAKE_SECRET not in captured.out and FAKE_SECRET not in captured.err
    assert store.get(DEFAULT_HANDLE) == FAKE_SECRET


def test_provisioning_refuses_two_different_entries(capsys, monkeypatch):
    store = _provision_store(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    answers = iter([FAKE_SECRET, OTHER_SECRET])
    monkeypatch.setattr(provision.getpass, "getpass", lambda prompt="": next(answers))
    assert provision.main([]) == 1
    captured = capsys.readouterr()
    assert "The two entries differ" in captured.err
    assert FAKE_SECRET not in captured.err and OTHER_SECRET not in captured.err
    assert store.get(DEFAULT_HANDLE) is None


def test_provisioning_refuses_a_pipe(capsys, monkeypatch):
    """``echo SECRET | provision.py`` is the exposure the store exists to remove."""
    store = _provision_store(monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{FAKE_SECRET}\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)

    def explode(prompt=""):  # pragma: no cover - reached only on a regression
        raise AssertionError("a non-interactive run must never reach the prompt")

    monkeypatch.setattr(provision.getpass, "getpass", explode)
    assert provision.main([]) == provision.EXIT_NO_TTY
    captured = capsys.readouterr()
    assert "SAIROUTE_PROVISIONING_REQUIRES_TTY" in captured.err
    assert FAKE_SECRET not in captured.err and FAKE_SECRET not in captured.out
    assert store.get(DEFAULT_HANDLE) is None


def test_provisioning_has_no_command_line_secret_surface(monkeypatch):
    _provision_store(monkeypatch)
    for option in ("--key", "--secret", "--password", "--value"):
        with pytest.raises(SystemExit):
            provision.main([option, FAKE_SECRET])


def test_provisioning_refuses_an_empty_secret(capsys, monkeypatch):
    store = _provision_store(monkeypatch)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    monkeypatch.setattr(provision.getpass, "getpass", lambda prompt="": "   ")
    assert provision.main([]) == 1
    assert "Empty secret provided" in capsys.readouterr().err
    assert store.get(DEFAULT_HANDLE) is None


def test_check_and_delete_report_the_backend_and_never_the_value(capsys, monkeypatch):
    store = _provision_store(monkeypatch, InMemoryCredentialStore({DEFAULT_HANDLE: FAKE_SECRET}))
    assert provision.main(["--check"]) == 0
    captured = capsys.readouterr()
    assert "Credential is provisioned" in captured.out
    assert "backend: saimail.credentials.InMemoryCredentialStore" in captured.out
    assert FAKE_SECRET not in captured.out

    assert provision.main(["--delete"]) == 0
    assert "Successfully deleted credential" in capsys.readouterr().out
    assert provision.main(["--check"]) == 1
    assert "No credential provisioned" in capsys.readouterr().out
    assert store.get(DEFAULT_HANDLE) is None


def test_provisioning_stops_on_an_unsuitable_backend(capsys, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    store = _store_with(_named_backend("keyring.backends.fail", "Keyring"))
    monkeypatch.setattr(provision, "KeyringCredentialStore", lambda: store)
    assert provision.main(["--check"]) == 1
    assert "SAIROUTE_CREDENTIAL_BACKEND_UNSUITABLE" in capsys.readouterr().err


def test_the_real_store_is_never_touched_by_the_suite(clean_store):
    """conftest injects an in-memory store; a unit test that reaches the OS is a bug."""
    from saimail.credentials import get_credential_store

    assert isinstance(get_credential_store(), InMemoryCredentialStore)


# ------------------------------------------------ W2-006: delete distinguishes absence from failure


class FakeDeletionKeyring:
    def __init__(self, present=True, fail_read=False, fail_delete=False):
        self.present = present
        self.fail_read = fail_read
        self.fail_delete = fail_delete
        self.deleted = []

    def get_password(self, service, username):
        if self.fail_read:
            raise RuntimeError("backend offline")
        return "stored-secret" if self.present else None

    def delete_password(self, service, username):
        if self.fail_delete:
            raise RuntimeError("backend offline")
        self.deleted.append((service, username))


def _keyring_store(fake):
    from saimail.credentials import KeyringCredentialStore
    store = KeyringCredentialStore(require_backend=False)
    store._keyring = fake
    return store


def test_delete_returns_false_only_when_absence_is_established():
    fake = FakeDeletionKeyring(present=False)
    assert _keyring_store(fake).delete(DEFAULT_HANDLE) is False
    assert fake.deleted == [], "nothing to delete: delete_password is not even called"


def test_delete_of_a_present_credential_succeeds_and_deletes():
    fake = FakeDeletionKeyring(present=True)
    assert _keyring_store(fake).delete(DEFAULT_HANDLE) is True
    assert len(fake.deleted) == 1


def test_a_backend_failure_during_the_absence_check_is_backend_error():
    with pytest.raises(BackendError):
        _keyring_store(FakeDeletionKeyring(fail_read=True)).delete(DEFAULT_HANDLE)


def test_a_backend_failure_during_deletion_of_a_known_credential_is_backend_error():
    with pytest.raises(BackendError):
        _keyring_store(FakeDeletionKeyring(present=True, fail_delete=True)).delete(DEFAULT_HANDLE)


def test_the_cli_names_a_backend_failure_apart_from_absence(capsys, monkeypatch):
    store = _provision_store(monkeypatch, InMemoryCredentialStore({DEFAULT_HANDLE: FAKE_SECRET},
                                                                  fail_on={"delete"}))
    assert provision.main(["--delete"]) == 1
    captured = capsys.readouterr()
    assert "backend" in (captured.err + captured.out).lower()
    assert FAKE_SECRET not in captured.out + captured.err
    monkeypatch.setattr(store, "_fail_on", set())
    assert provision.main(["--delete"]) == 0
    assert "Successfully deleted credential" in capsys.readouterr().out
    monkeypatch.setattr(store, "_data", {})
    assert provision.main(["--delete"]) == 1
    assert "No credential found" in capsys.readouterr().out
