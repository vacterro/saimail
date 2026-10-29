"""Failed OS lock entry releases its descriptor before propagating refusal."""

import os

import pytest

from sailang import SailangError
from saimail import postoffice


@pytest.mark.parametrize("stage", ["stat", "seek", "acquire"])
def test_failed_lock_entry_closes_its_descriptor_and_can_retry(tmp_path, monkeypatch, stage):
    lock = postoffice._OsFileLock(tmp_path / "operation.lock")
    original_open = os.open
    descriptors = []

    def record_open(*args, **kwargs):
        fd = original_open(*args, **kwargs)
        descriptors.append(fd)
        return fd

    def fail(*args, **kwargs):
        raise SailangError("TEST_LOCK_FAILURE", stage)

    with monkeypatch.context() as patch:
        patch.setattr(os, "open", record_open)
        if stage == "acquire":
            patch.setattr(lock, "_acquire", fail)
        else:
            patch.setattr(os, "fstat" if stage == "stat" else "lseek", fail)
        with pytest.raises(SailangError, match="TEST_LOCK_FAILURE"):
            with lock:
                pytest.fail("failed acquisition entered the body")
    assert lock._fd is None
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        os.fstat(descriptors[0])
    with lock:
        assert lock._fd is not None
    assert lock._fd is None
