"""A mailbox lock that is being created by another process is waited for (T-123).

The mesh torture found concurrent first deliveries into a fresh mailbox failing
with DELIVERY_IO_ERROR: two processes saw the empty lock file, the first wrote
and locked byte 0, and the second's initializing write into that locked byte was
refused by Windows (PermissionError). A contended lock must be waited for, not
reported as an I/O failure.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

from saimail import postoffice

pytestmark = pytest.mark.skipif(os.name != "nt", reason="the refused write is Windows semantics")


def test_entering_a_lock_whose_byte_another_process_holds_waits_instead_of_failing(tmp_path):
    import msvcrt

    path = tmp_path / "lifecycle.lock"
    holder = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    msvcrt.locking(holder, msvcrt.LK_NBLCK, 1)  # byte 0 of a still empty file
    outcome = {}

    def enter():
        try:
            with postoffice._OsFileLock(path, busy_code="LIFECYCLE_LOCK_TIMEOUT"):
                outcome["acquired_at"] = time.monotonic()
        except BaseException as exc:  # noqa: BLE001 - the control reports what happened
            outcome["error"] = exc

    waiter = threading.Thread(target=enter)
    waiter.start()
    time.sleep(0.5)
    assert "error" not in outcome, f"a contended lock failed: {outcome.get('error')!r}"
    assert "acquired_at" not in outcome, "the lock was taken while another holder had it"
    released_at = time.monotonic()
    os.lseek(holder, 0, os.SEEK_SET)
    msvcrt.locking(holder, msvcrt.LK_UNLCK, 1)
    os.close(holder)
    waiter.join(timeout=10)
    assert outcome.get("acquired_at", 0) >= released_at
