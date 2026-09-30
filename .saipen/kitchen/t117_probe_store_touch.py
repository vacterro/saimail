"""Probe: how many custody-store secret reads does one turn-entry read cost?

Runs the real CLI entry in-process against an os-store workspace whose store is
an in-memory counting double, then against a store that refuses every read.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, r"V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\__SAIMAIL__")

import saimail_local  # noqa: E402
from saimail import credentials, workspace  # noqa: E402


class CountingStore(credentials.InMemoryCredentialStore):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.reads = 0
        self.refuse = False

    def get(self, handle):
        self.reads += 1
        if self.refuse:
            raise credentials.BackendError("store locked (probe)")
        return super().get(handle)


def cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = saimail_local.main(list(argv))
    return rc, json.loads(out.getvalue())


def main() -> None:
    store = CountingStore()
    credentials.set_credential_store(store)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "A", Path(tmp) / "B"
            workspace.init_workspace(a, seat="alpha", custody="os-store", store=store)
            workspace.init_workspace(b, seat="beta", custody="os-store", store=store)
            A = workspace.load_workspace(a, store=store)
            B = workspace.load_workspace(b, store=store)
            workspace.add_recipient(A, "beta", workspace.identity_card(B), B.root)
            workspace.add_recipient(B, "alpha", workspace.identity_card(A), A.root)
            sent = workspace.send_message(A, "beta", claim="probe", topic="T-117",
                                          kind="DISCOVERY")
            print(f"send: {sent['status']}")
            store.reads = 0
            rc, res = cli("--json", "saipen", "telegrams", "--workspace", str(b),
                          "--scan-budget", "200")
            print(f"unlocked store: rc={rc} status={res.get('status')} "
                  f"match_count={res.get('match_count')} secret_reads={store.reads}")
            store.reads = 0
            store.refuse = True
            rc, res = cli("--json", "saipen", "telegrams", "--workspace", str(b),
                          "--scan-budget", "200")
            print(f"locked store:   rc={rc} status={res.get('status')} "
                  f"code={res.get('code')} match_count={res.get('match_count')} "
                  f"secret_reads={store.reads}")
    finally:
        credentials.set_credential_store(None)


if __name__ == "__main__":
    main()
