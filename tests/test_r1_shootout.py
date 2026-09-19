"""T-15 acceptance: the three codecs are actually comparable, and the gate can drop the custom wire."""

import ast
import json
import pathlib

import pytest

from bench import r1_codecs
from bench.r1_shootout import CRITERIA, classify, run
from bench.corpus import CASES
from sailang import Record, SailangError
from sailang.frame import Profile


@pytest.fixture(scope="module")
def profile():
    return Profile.load("1")


@pytest.fixture(scope="module")
def records():
    return [Record.create(**case.fields) for case in CASES[:12]]


CODECS = list(r1_codecs.CODECS.items())


# --------------------------------------------------------------------
# identical semantics, no codec privileged
# --------------------------------------------------------------------


@pytest.mark.parametrize("name,codec", CODECS)
def test_every_codec_round_trips_to_the_identical_typed_view(name, codec, records, profile):
    reference = r1_codecs.sailang_decode_all(
        r1_codecs.sailang_encode(records, profile), profile)
    assert codec["decode"](codec["encode"](records, profile), profile) == reference


@pytest.mark.parametrize("name,codec", CODECS)
def test_encoding_is_deterministic(name, codec, records, profile):
    first = codec["encode"](records, profile)
    assert first == codec["encode"](records, profile)


@pytest.mark.parametrize("name,codec", CODECS)
def test_every_codec_carries_the_same_six_slots(name, codec, records, profile):
    text = codec["encode"](records, profile)
    body = text.rstrip("\n").split("\n")[1:]
    assert len(body) == len(records)
    views = codec["decode"](text, profile)
    for view in views:
        assert view.kind and view.profile_id == profile.id


# --------------------------------------------------------------------
# correctness gates each codec must pass on its own
# --------------------------------------------------------------------


@pytest.mark.parametrize("name,codec", CODECS)
def test_wrong_profile_is_refused_by_every_codec(name, codec, records, profile):
    other = Profile.inline("other", {"RETRY": {"wire": "RTY", "render": "a retry"}})
    text = codec["encode"](records, profile)
    with pytest.raises(SailangError) as excinfo:
        codec["decode"](text, other)
    assert excinfo.value.code == "PROFILE_MISMATCH"


@pytest.mark.parametrize("name,codec", CODECS)
def test_unknown_field_is_refused_by_every_codec(name, codec, records, profile):
    from bench.r1_shootout import _with_unknown_field

    text = _with_unknown_field(codec["encode"](records, profile), name)
    with pytest.raises((SailangError, ValueError, KeyError)):
        codec["decode"](text, profile)


@pytest.mark.parametrize("name,codec", CODECS)
@pytest.mark.parametrize("mutate", ["truncate", "count", "garbage", "empty"])
def test_malformed_input_is_refused_by_every_codec(name, codec, records, profile, mutate):
    text = codec["encode"](records, profile)
    broken = {
        "truncate": text.split("\n")[0] + "\n",
        "count": text.replace(f"N:{len(records)}", "N:99").replace(
            f'"n":{len(records)}', '"n":99').replace(f"n={len(records)}", "n=99"),
        "garbage": text.rstrip("\n") + "\nnot a frame at all\n",
        "empty": "",
    }[mutate]
    with pytest.raises((SailangError, ValueError, IndexError, KeyError, TypeError)):
        codec["decode"](broken, profile)


# --------------------------------------------------------------------
# the gate can drop the custom wire
# --------------------------------------------------------------------


def _row(ok=True, body=100, decode_ns=100.0, surface=10):
    return {"correctness_ok": ok, "bytes_body": body,
            "decode_ns_per_batch": decode_ns, "code_surface_statements": surface}


@pytest.mark.parametrize("custom,json_row,kv_row,expected", [
    (_row(), _row(body=200), _row(body=300), "KEEP_CUSTOM_WIRE"),
    (_row(body=190), _row(body=200), _row(body=300), "DROP_CUSTOM_WIRE"),      # no byte edge
    (_row(decode_ns=1000.0), _row(), _row(), "DROP_CUSTOM_WIRE"),              # too slow
    (_row(surface=100), _row(), _row(), "DROP_CUSTOM_WIRE"),                   # too much code
    (_row(ok=False), _row(), _row(), "DROP_CUSTOM_WIRE"),                      # failed a gate
    (_row(ok=False), _row(ok=False), _row(ok=False), "REDESIGN_R1"),           # nothing survived
])
def test_classification_reaches_every_verdict(custom, json_row, kv_row, expected):
    verdict, _ = classify({"A_sailang_wire": custom, "B_compact_json": json_row,
                           "C_typed_kv": kv_row})
    assert verdict == expected


def test_criteria_are_declared_above_the_measurement():
    source = pathlib.Path("bench/r1_shootout.py").read_text(encoding="utf-8")
    assert source.index("CRITERIA = {") < source.index("def run(")
    assert 0 < CRITERIA["bytes_advantage_required"] < 1
    assert CRITERIA["decode_latency_ceiling"] >= 1
    assert CRITERIA["code_surface_ceiling"] >= 1


def test_no_third_party_serialization_dependency():
    tree = ast.parse(pathlib.Path("bench/r1_codecs.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    for forbidden in ("msgpack", "cbor2", "google", "protobuf", "ujson", "orjson"):
        assert forbidden not in imported
    assert imported <= {"__future__", "json", "re", "typing", "sailang"}


def test_shootout_produces_complete_output(tmp_path):
    out = run(tmp_path)
    assert out["verdict"] in {"KEEP_CUSTOM_WIRE", "DROP_CUSTOM_WIRE", "REDESIGN_R1"}
    for name in r1_codecs.CODECS:
        row = out["codecs"][name]
        for key in ("bytes_body", "encode_ns_per_batch", "decode_ns_per_batch",
                    "encode_peak_bytes", "decode_peak_bytes",
                    "code_surface_statements", "round_trip_identical_view",
                    "malformed_all_refused", "unknown_field_behaviour",
                    "wrong_profile_behaviour", "correctness_ok"):
            assert key in row, f"{name} is missing {key}"
    for artifact in ("r1_shootout.json", "R1_SHOOTOUT.md"):
        assert (tmp_path / artifact).is_file()
    payload = json.loads((tmp_path / "r1_shootout.json").read_text(encoding="utf-8"))
    assert payload["verdict"] == out["verdict"]
    report = (tmp_path / "R1_SHOOTOUT.md").read_text(encoding="utf-8")
    assert "MEASUREMENT BOUNDARY" in report, "the code-surface boundary must be disclosed"
