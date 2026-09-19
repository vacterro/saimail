"""One-time local provisioning for the SAIRoute credential.

The defect class this tool eliminates: **a secret arriving through a pipe.**

    echo $SECRET | python tools/provision_sairoute_credential.py

puts the credential in shell history, in the process table and in any transcript
of the session, which is the exact exposure the credential store exists to
remove. So there is no non-interactive ingestion path here, and no ``--key`` or
``--secret`` option to add one back: the secret is typed at a real terminal, not
echoed, and confirmed once. Without a TTY the tool refuses and explains itself.

    python tools/provision_sairoute_credential.py               # store or replace
    python tools/provision_sairoute_credential.py --check       # is one stored?
    python tools/provision_sairoute_credential.py --delete      # remove it

Rotation is the ordinary store command: storing again replaces the value under
the same handle, and the ordinary live command picks it up with no other change.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from saimail.credentials import (  # noqa: E402
    DEFAULT_HANDLE,
    BackendError,
    CredentialError,
    KeyringCredentialStore,
)

#: Exit code for "this is not an interactive terminal". Distinct from 1 so a
#: wrapper can tell a refused environment from a refused secret.
EXIT_NO_TTY = 2


def _prompt(handle: str, getpass_fn=None) -> str:
    """Read the secret twice from a non-echoing terminal prompt.

    ``getpass.getpass`` is looked up at call time, not bound as a default: a
    default argument is resolved at import and would quietly ignore a test that
    replaced the prompt, which is how a suite ends up reading a real terminal.
    """
    getpass_fn = getpass_fn or getpass.getpass
    first = getpass_fn(f"Enter secret for {handle}: ").strip()
    if not first:
        raise CredentialError("Empty secret provided. Nothing stored.")
    again = getpass_fn("Enter it again to confirm: ").strip()
    if first != again:
        raise CredentialError("The two entries differ. Nothing stored.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Provision the SAIRoute credential in the local credential store. "
                    "The secret is typed interactively; there is no option that accepts it "
                    "on the command line or on standard input.")
    parser.add_argument("--handle", default=DEFAULT_HANDLE, help="Logical credential handle")
    parser.add_argument("--delete", action="store_true", help="Delete the stored credential")
    parser.add_argument(
        "--check", action="store_true",
        help="Report whether a credential is provisioned, and which backend holds it, "
             "without displaying the value")
    args = parser.parse_args(argv)

    store = KeyringCredentialStore()
    handle = args.handle

    # The backend claim is checked before anything is read or written, so a host
    # whose keyring cannot be the declared persistent store fails here with a
    # named error instead of appearing to work.
    try:
        backend = store.check_backend()
    except BackendError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.delete:
        try:
            deleted = store.delete(handle)
        except BackendError as exc:
            print(f"Credential backend failure while deleting {handle}: {exc}", file=sys.stderr)
            return 1
        if deleted:
            print(f"Successfully deleted credential for {handle}")
            return 0
        print(f"No credential found for {handle}")
        return 1

    if args.check:
        try:
            present = bool(store.get(handle))
        except BackendError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if present:
            print(f"Credential is provisioned for {handle} (backend: {backend})")
            return 0
        print(f"No credential provisioned for {handle} (backend: {backend})")
        return 1

    if not sys.stdin.isatty():
        print("SAIROUTE_PROVISIONING_REQUIRES_TTY: this tool reads the secret from an "
              "interactive non-echoing prompt and has no pipe, file or command-line input "
              "path. Run it from a terminal.", file=sys.stderr)
        return EXIT_NO_TTY

    try:
        secret = _prompt(handle)
    except (KeyboardInterrupt, EOFError):
        print("\nProvisioning cancelled.", file=sys.stderr)
        return 1
    except CredentialError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    try:
        store.set(handle, secret)
    except Exception as exc:  # noqa: BLE001 - reported, never re-raised with the secret
        print(f"Failed to store credential: {exc}", file=sys.stderr)
        return 1
    print(f"Successfully stored credential for {handle} (backend: {backend})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
