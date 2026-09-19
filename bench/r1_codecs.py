"""Three R1 codecs carrying IDENTICAL semantics, stdlib only.

The point of the shootout is that the custom wire must justify its own syntax.
So every codec here encodes exactly the same six logical slots, verifies the
same container-level profile identity, and decodes to the SAME
``sailang.frame.TriageView`` object. No codec gets an extra field, an extra
guarantee, or a friendlier error.

No third-party serialization dependency, by instruction: this first comparison
is against what the standard library already offers.
"""

from __future__ import annotations

import json
import re
from typing import Sequence, Tuple

from sailang.errors import SailangError
from sailang.frame import (
    ABSENT,
    OPEN_RECORD,
    Profile,
    _bind_verified,
    TriageView,
    decode as sailang_decode,
    project as sailang_project,
)
from sailang.record import KINDS, RUNGS, Record

_HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_FLAG_CHARS = frozenset("RSCX")
_SLOTS = ("k", "s", "st", "e", "c", "f")


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def _slots_from_record(record: Record, profile: Profile) -> dict:
    """The one place the six logical slots are derived. Shared by all codecs."""
    wire = sailang_project(record, profile).wire.split("|")
    return dict(zip(_SLOTS, wire))


def _view_from_slots(slots: dict, profile: Profile) -> TriageView:
    """Every codec lands on the same typed view, produced by the same decoder."""
    missing = [name for name in _SLOTS if name not in slots]
    if missing:
        _reject("BAD_FRAME", f"missing slots: {missing}")
    extra = [name for name in slots if name not in _SLOTS]
    if extra:
        _reject("UNKNOWN_FIELD", f"unknown slots: {extra}")
    for name in _SLOTS:
        if not isinstance(slots[name], str) or not slots[name]:
            _reject("BAD_FRAME", f"slot {name} must be a non-empty string")
    wire = "|".join(slots[name] for name in _SLOTS)
    if wire.count("|") != len(_SLOTS) - 1:
        _reject("BAD_FRAME", "a slot value carried the separator")
    return sailang_decode(_bind_verified(wire, profile))


# --------------------------------------------------------------------
# A — SAILANG custom wire
# --------------------------------------------------------------------


def sailang_encode(records: Sequence[Record], profile: Profile) -> str:
    header = f"{profile.batch_marker}|P:{profile.id}|N:{len(records)}|D:0"
    body = [sailang_project(record, profile).wire for record in records]
    return "\n".join([header] + body) + "\n"


def sailang_decode_all(text: str, profile: Profile) -> Tuple[TriageView, ...]:
    lines = text.rstrip("\n").split("\n")
    header = lines[0].split("|")
    if len(header) != 4 or header[0] != profile.batch_marker:
        _reject("BAD_BATCH", "bad container header")
    if not header[1].startswith("P:") or not _HASH_RE.match(header[1][2:]):
        _reject("BAD_PROFILE_ID", "bad profile id")
    if header[1][2:] != profile.id:
        _reject("PROFILE_MISMATCH", "container profile differs from the supplied profile")
    if not header[2].startswith("N:") or int(header[2][2:]) != len(lines) - 1:
        _reject("BAD_BATCH", "declared count differs from the body")
    return tuple(
        sailang_decode(_bind_verified(line, profile)) for line in lines[1:]
    )


# --------------------------------------------------------------------
# B — compact deterministic JSON
# --------------------------------------------------------------------


def json_encode(records: Sequence[Record], profile: Profile) -> str:
    header = json.dumps({"n": len(records), "p": profile.id},
                        sort_keys=True, separators=(",", ":"))
    body = [
        json.dumps(_slots_from_record(record, profile), sort_keys=True, separators=(",", ":"))
        for record in records
    ]
    return "\n".join([header] + body) + "\n"


def json_decode_all(text: str, profile: Profile) -> Tuple[TriageView, ...]:
    lines = text.rstrip("\n").split("\n")
    try:
        header = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        _reject("BAD_BATCH", f"bad container header: {exc}")
    if not isinstance(header, dict) or set(header) != {"n", "p"}:
        _reject("BAD_BATCH", "container header must carry exactly n and p")
    if not isinstance(header["p"], str) or not _HASH_RE.match(header["p"]):
        _reject("BAD_PROFILE_ID", "bad profile id")
    if header["p"] != profile.id:
        _reject("PROFILE_MISMATCH", "container profile differs from the supplied profile")
    if header["n"] != len(lines) - 1:
        _reject("BAD_BATCH", "declared count differs from the body")
    views = []
    for line in lines[1:]:
        try:
            slots = json.loads(line)
        except json.JSONDecodeError as exc:
            _reject("BAD_FRAME", f"bad frame: {exc}")
        if not isinstance(slots, dict):
            _reject("BAD_FRAME", "a frame must be an object")
        views.append(_view_from_slots(slots, profile))
    return tuple(views)


# --------------------------------------------------------------------
# C — minimal typed key/value, stdlib only
# --------------------------------------------------------------------


def kv_encode(records: Sequence[Record], profile: Profile) -> str:
    header = f"p={profile.id};n={len(records)}"
    body = [
        ";".join(f"{name}={value}" for name, value in _slots_from_record(record, profile).items())
        for record in records
    ]
    return "\n".join([header] + body) + "\n"


def _kv_pairs(line: str) -> dict:
    out: dict = {}
    for chunk in line.split(";"):
        if "=" not in chunk:
            _reject("BAD_FRAME", f"{chunk!r} is not key=value")
        key, value = chunk.split("=", 1)
        if key in out:
            _reject("BAD_FRAME", f"duplicate key {key!r}")
        out[key] = value
    return out


def kv_decode_all(text: str, profile: Profile) -> Tuple[TriageView, ...]:
    lines = text.rstrip("\n").split("\n")
    header = _kv_pairs(lines[0])
    if set(header) != {"p", "n"}:
        _reject("BAD_BATCH", "container header must carry exactly p and n")
    if not _HASH_RE.match(header["p"]):
        _reject("BAD_PROFILE_ID", "bad profile id")
    if header["p"] != profile.id:
        _reject("PROFILE_MISMATCH", "container profile differs from the supplied profile")
    try:
        declared = int(header["n"])
    except ValueError:
        _reject("BAD_BATCH", "n must be an integer")
    if declared != len(lines) - 1:
        _reject("BAD_BATCH", "declared count differs from the body")
    return tuple(_view_from_slots(_kv_pairs(line), profile) for line in lines[1:])


CODECS = {
    "A_sailang_wire": {"encode": sailang_encode, "decode": sailang_decode_all,
                       "functions": ("sailang_encode", "sailang_decode_all")},
    "B_compact_json": {"encode": json_encode, "decode": json_decode_all,
                       "functions": ("json_encode", "json_decode_all")},
    "C_typed_kv": {"encode": kv_encode, "decode": kv_decode_all,
                   "functions": ("kv_encode", "_kv_pairs", "kv_decode_all")},
}

#: Shared machinery every codec uses, counted once against each of them.
SHARED_FUNCTIONS = ("_slots_from_record", "_view_from_slots")
