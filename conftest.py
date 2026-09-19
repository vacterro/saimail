"""Make the project root importable regardless of how pytest was invoked."""

import pathlib
import sys

ROOT = str(pathlib.Path(__file__).resolve().parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from saimail.credentials import InMemoryCredentialStore, set_credential_store


@pytest.fixture(autouse=True)
def _isolate_credential_store():
    """Ensure unit tests never access the real Windows credential store."""
    store = InMemoryCredentialStore()
    set_credential_store(store)
    yield store
    set_credential_store(None)
