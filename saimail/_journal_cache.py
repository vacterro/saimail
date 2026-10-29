"""Process-local validated file snapshots; canonical journals stay on disk.

Only the process that validated a generation may reuse it. A new process, an
external append/rewrite/replacement, truncation, or a failed write rebuilds
from canonical bytes. No persisted cache can assert that a journal is valid.
"""

import os
import threading
from functools import lru_cache
from pathlib import Path


def _signature(info, change=None):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, change)


@lru_cache(maxsize=1)
def _windows_api():
    # A fixed file-metadata API, never a general native-code loader. Windows
    # runtime/test extras declare this dependency. Without it, canonical reads
    # remain correct but cannot reuse a generation whose ChangeTime is unknown.
    try:
        import win32file
    except ImportError:
        return None
    return win32file


def _change_time(handle):
    api = _windows_api()
    if api is None:
        return None
    try:
        return api.GetFileInformationByHandleEx(handle, api.FileBasicInfo)["ChangeTime"]
    except (OSError, api.error):
        return None


def _descriptor_stamp(fd):
    if os.name != "nt":
        return _signature(os.fstat(fd))
    import msvcrt

    return _signature(os.fstat(fd), _change_time(msvcrt.get_osfhandle(fd)))


def stamp(path):
    try:
        info = path.stat()
        if os.name != "nt":
            return _signature(info)
        # st_ctime is creation time on Windows. Native ChangeTime also detects
        # same-size edits whose LastWriteTime the editor restores afterwards.
        api = _windows_api()
        if api is None:
            return _signature(info)  # no reliable generation: rebuild, never reuse
        try:
            handle = api.CreateFile(str(path.resolve()), 0x80, 7, None, 3, 0, None)
        except (OSError, api.error):
            return _signature(info)
        try:
            change = _change_time(handle)
        finally:
            handle.Close()
        if _signature(path.stat()) != _signature(info):
            raise OSError("canonical journal replaced during metadata read")
        return _signature(info, change)
    except FileNotFoundError:
        return None


class ValidatedFile:
    def __init__(self):
        self.lock = threading.RLock()
        self.signature = None
        self.value = None

    def invalidate(self):
        self.signature = self.value = None

    def load(self, path, loader):
        """Caller holds lock for the entire use of the returned private value."""
        before = stamp(path)
        reliable = os.name != "nt" or before is None or before[-1] is not None
        if self.value is None or before != self.signature or not reliable:
            self.invalidate()
            value = loader(path)
            if stamp(path) != before:
                raise OSError("canonical journal changed during validation")
            self.signature, self.value = before, value
        return self.value

    def check(self, path):
        if stamp(path) != self.signature:
            self.invalidate()
            raise OSError("canonical journal changed during reading")

    def append(self, path, line, advance):
        """Advance a validated snapshot only after this append is durable.

        The caller also holds the journal's established OS writer lock. Opening
        and closing a descriptor pins the file identity across the append;
        failed or externally displaced writes never update the snapshot.
        """
        try:
            with path.open("ab") as handle:
                opened = _descriptor_stamp(handle.fileno())
                if ((self.signature is None and opened[2] != 0)
                        or (self.signature is not None and opened != self.signature)):
                    raise OSError("canonical journal changed before append")
                handle.write(line)
                handle.flush()
                os.fsync(handle.fileno())
                after = _descriptor_stamp(handle.fileno())
                if after[:2] != opened[:2] or after[2] != opened[2] + len(line):
                    raise OSError("canonical journal changed during append")
            if stamp(path) != after:
                raise OSError("canonical journal replaced during append")
            advance(self.value, opened[2])
            self.signature = after
        except BaseException:
            self.invalidate()
            raise


@lru_cache(maxsize=64)
def _cache(path):
    return ValidatedFile()


def for_path(path):
    return _cache(os.path.normcase(str(Path(path).resolve())))
