"""A torn-tail repair keeps its evidence even if recovery or the process stops."""
import hashlib
import json

import pytest

from saimail import postoffice
from sailang import SailangError
from test_postoffice_delivery import office_at, sealed_bytes


def torn_index(tmp_path):
    office, _ = office_at(tmp_path)
    office.deliver(sealed_bytes())
    path = office.mail_root / postoffice.INDEX_NAME
    prefix = path.read_bytes()
    tail = b'{"schema":1,"interrupted":'
    path.write_bytes(prefix + tail)
    return office, path, prefix, tail


def test_recovery_publishes_exact_tail_evidence_before_truncating(tmp_path):
    office, path, prefix, tail = torn_index(tmp_path)
    repair = office.recover().torn_index_tail
    evidence_path = office.mail_root / repair["evidence_ref"]
    record = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert record["offset"] == len(prefix)
    assert record["prefix_sha256"] == "sha256:" + hashlib.sha256(prefix).hexdigest()
    assert record["tail_sha256"] == "sha256:" + hashlib.sha256(tail).hexdigest()
    assert (evidence_path.parent / "tail.bin").read_bytes() == tail
    assert path.read_bytes() == prefix
    before = evidence_path.read_bytes()
    path.write_bytes(prefix + tail)
    assert office.recover().torn_index_tail["evidence_ref"] == repair["evidence_ref"]
    assert evidence_path.read_bytes() == before


@pytest.mark.parametrize("after_publish", [False, True])
def test_failed_evidence_publication_never_discards_the_tail(tmp_path, monkeypatch, after_publish):
    office, path, prefix, tail = torn_index(tmp_path)
    original = postoffice._publish_dir

    def fail(parent, *args, **kwargs):
        if parent.name == "index-tails":
            if after_publish:
                original(parent, *args, **kwargs)
            raise OSError("evidence publication interrupted")
        return original(parent, *args, **kwargs)

    monkeypatch.setattr(postoffice, "_publish_dir", fail)
    with pytest.raises(OSError, match="publication interrupted"):
        office.recover()
    assert path.read_bytes() == prefix + tail
    monkeypatch.setattr(postoffice, "_publish_dir", original)
    assert office.recover().torn_index_tail["truncated_bytes"] == len(tail)
    assert path.read_bytes() == prefix


@pytest.mark.parametrize("member", ["evidence.json", "tail.bin"])
def test_existing_conflicting_repair_evidence_is_never_overwritten(tmp_path, member):
    office, path, prefix, tail = torn_index(tmp_path)
    repair = office.recover().torn_index_tail
    evidence_path = office.mail_root / repair["evidence_ref"]
    damaged_path = evidence_path.with_name(member)
    damaged_path.write_bytes(b"damaged prior evidence")
    path.write_bytes(prefix + tail)
    with pytest.raises(SailangError) as error:
        office.recover()
    assert error.value.code == postoffice.INDEX_CORRUPT
    assert damaged_path.read_bytes() == b"damaged prior evidence"
    assert path.read_bytes() == prefix + tail
