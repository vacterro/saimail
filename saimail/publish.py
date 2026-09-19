"""Immutable evidence publication: complete staging, atomic no-overwrite commit.

    COMPLETE STAGING FIRST.
    THE NAME APPEARS ONLY WITH COMPLETE BYTES BEHIND IT.
    A COMMITTED EVIDENCE OBJECT IS NEVER REPLACED.

The defect class this module eliminates: an "immutable" evidence writer whose
final step is ``os.replace(staged, path)``. Replacement is atomic, but it is
not publication -- two concurrent writers both succeed and the second one's
bytes silently win, which is exactly the overwrite write-once semantics
forbid (T-42/C2).

The publish operation here is a hard link from a same-directory staged file:

1. the complete bytes are written to ``.<name>.<random>.tmp`` beside the
   target, flushed and fsynced -- a crash here leaves no target and the
   staged temporary is removed;
2. ``os.link(staged, target)`` names the object in one atomic step. The link
   fails with ``FileExistsError`` when any writer already published, so the
   target only ever appears holding complete bytes, exactly once;
3. a losing writer compares its staged bytes against the winner's: identical
   bytes converge idempotently (``IDEMPOTENT``, the winner untouched), any
   other difference refuses with the caller's named conflict code.

On a filesystem without hard-link support the link step degrades to an
exclusive ``O_CREAT | O_EXCL`` create followed by copying the staged bytes
into place: still strictly no-overwrite, but bytes stream into the visible
name during the copy rather than appearing complete -- the one guarantee this
fallback genuinely provides, stated here so no caller overclaims it.

This is crash-atomicity between writers on one machine, not protection
against a hostile process with write access to the directory.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from sailang.errors import SailangError

PUBLISHED = "PUBLISHED"
IDEMPOTENT = "IDEMPOTENT"


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _fsync_directory(directory: Path) -> None:
    """Persist the directory entry where the platform allows it."""
    if os.name == "nt":  # Windows cannot open a directory for fsync
        return
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _compare_existing(path: Path, data: bytes, conflict_code: str) -> str:
    """Another writer won the name: identical bytes converge, else named conflict."""
    try:
        winner = path.read_bytes()
    except OSError as exc:
        _reject(conflict_code,
                f"{path} was published by another writer and cannot be read back "
                f"({type(exc).__name__}); a committed evidence object is not replaced")
    if winner == data:
        return IDEMPOTENT
    _reject(conflict_code,
            f"{path} already holds different bytes; evidence is published once and a "
            "committed object is never overwritten by a concurrent writer")


def _exclusive_fallback(path: Path, data: bytes, conflict_code: str) -> str:
    """No-hardlink filesystems: exclusive create, then copy the staged bytes in.

    Weaker than the link path and documented as such: the target can never be
    overwritten (``O_EXCL``), but its bytes stream in after the name appears.
    """
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        return _compare_existing(path, data, conflict_code)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return PUBLISHED
    except OSError:
        path.unlink(missing_ok=True)  # never leave a partial evidence object
        raise


def publish_immutable(path: Path, data: bytes, *, conflict_code: str) -> str:
    """Publish one immutable evidence object. Returns ``PUBLISHED`` or ``IDEMPOTENT``.

    ``conflict_code`` names the refusal a losing writer with different bytes
    receives, so each caller's evidence vocabulary stays its own. A failure
    before the publish step leaves no target and no staged temporary; a losing
    race never touches the winner's bytes.
    """
    staged = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with staged.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(staged, path)
        except FileExistsError:
            return _compare_existing(path, data, conflict_code)
        except (NotImplementedError, OSError):
            # some filesystems refuse hard links outright; the fallback keeps
            # the no-overwrite contract and honestly loses complete-at-appear
            return _exclusive_fallback(path, data, conflict_code)
        _fsync_directory(path.parent)
        return PUBLISHED
    finally:
        staged.unlink(missing_ok=True)
