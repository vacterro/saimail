# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-065 — a contended lock initialization is waited for, never an I/O failure (T-123)

The defect class is concurrency surfaced as a delivery error: two processes
initializing the same OS-backed lock file at once, where the loser's
initializing write into a byte another process already locked was refused by
Windows (`PermissionError`) and propagated as `DELIVERY_IO_ERROR`. The mesh
torture (SRC-108 item 8) found it: 2 of 5 series red on the pre-fix code
across 2/4/8/12-agent meshes with two racing processes per agent.

**Decision.** `_OsFileLock.__enter__` (`saimail/postoffice.py`) treats the
initializing write's `PermissionError` as the contended case: the waiter
waits for the OS lock (the existing `INDEX_LOCK_TIMEOUT` /
`LIFECYCLE_LOCK_TIMEOUT` deadline vocabulary, unchanged) instead of failing
the delivery. The OS lock stays the authority; the initializing byte 0 is
still written by whoever holds the lock first.

**Boundary.** Lock ordering, busy-code vocabulary, and the frozen `0.0.2a3`
candidate are unchanged. POSIX semantics were already correct (no refused
write); the fix is Windows-only in effect, guarded by nothing — the wait is
correct on every platform. Editing `saimail/postoffice.py` drifted its
current-implementation SHA in `lab/selector_coverage_manifest.json`
(EXPERIMENT-MANIFEST-1 pins the checkout, not just history); the pin is
re-frozen to the new bytes, exactly the `CURRENT_IMPLEMENTATION_DRIFT`
re-pinning the manifest was built for (T-65/T-78 precedent). The
`HISTORICAL_ONLY` fixtures and archived inputs are untouched.

**Evidence.** `tests/test_mailbox_lock_init.py` (red on pre-fix bytes, green
after) and `tests/test_mesh.py` (full meshes of 2/4/8/12 agents, two racing
processes per agent, every fact retried, all agents killed inside the outbox
lock after a delivery and restarted: exactly one message per fact per sender,
intact indexes, no FAILED, no `DELIVERY_IO_ERROR`;
`.saipen/evidence/T-123-mesh/`).
