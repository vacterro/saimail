"""T-2 acceptance: the line is a lossy, deterministic triage projection.

The rules under test come from spec/DECISIONS.md D-002 and
spec/01-SAILANG-v0.md section 5.
"""

import ast

import pytest

from sailang import Record, SailangError
from sailang.line import (
    ABSENT,
    OPEN_RECORD,
    Dictionary,
    default_dictionary,
    project,
    triage,
)

REF_A = "sha256:" + "a" * 64
REF_B = "sha256:" + "b" * 64


def fact(**over):
    fields = dict(KIND="F", SRC="AGENT:a17", SUBJ="queue", CLAIM="QSTALE>RETRY>DUP_EXEC",
                  TYPE="INT", EV=REF_A, STATUS="U2", CREATED="2026-09-17T08:41:00Z")
    fields.update(over)
    for key in [k for k, v in fields.items() if v is None]:
        del fields[key]
    return Record.create(**fields)


# --------------------------------------------------------------------
# determinism and purity
# --------------------------------------------------------------------


def test_same_record_same_line():
    record = fact()
    assert project(record) == project(record)
    assert project(fact()) == project(record)


def test_projection_cannot_mutate_the_canonical_record():
    record = fact()
    before_bytes = record.canonical_bytes()
    before_id = record.content_id
    for _ in range(3):
        project(record)
        triage(record)
    assert record.canonical_bytes() == before_bytes
    assert record.content_id == before_id


def test_line_shape_is_the_documented_seven_slots():
    line = project(fact())
    slots = line.split("|")
    assert len(slots) == 7
    assert slots[0] == "L1D0"
    assert line == "L1D0|F|queue|U2|EV+|QSTALE>RETRY>DUP_EXEC|-"


# --------------------------------------------------------------------
# no line -> record path exists
# --------------------------------------------------------------------


def test_module_exposes_no_line_parser():
    import sailang.line as module

    public = {name for name in dir(module) if not name.startswith("_")}
    for forbidden in ("parse", "parse_line", "from_line", "unproject", "decode", "loads"):
        assert forbidden not in public, f"{forbidden} would make the line authoritative"


def test_no_function_in_the_package_returns_a_record_from_a_line():
    import sailang.line as module

    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            args = [a.arg for a in node.args.args]
            returns_record = isinstance(node.returns, ast.Name) and node.returns.id == "Record"
            assert not (returns_record and "line" in args), (
                f"{node.name} reconstructs a record from a line"
            )


def test_a_line_is_not_accepted_where_a_record_is_expected():
    with pytest.raises(SailangError) as excinfo:
        project("L1D0|F|queue|U2|EV+|QSTALE|-")
    assert excinfo.value.code == "NOT_A_RECORD"


# --------------------------------------------------------------------
# triage fields are preserved, never upgraded
# --------------------------------------------------------------------


@pytest.mark.parametrize("kind,extra", [
    ("F", {}),
    ("O", {"SRC": "FS:/var/log/queue.log", "TYPE": "OBS"}),
    ("H", {"TYPE": "INT", "FALSIFY": "a fresh owner still duplicates", "STATUS": "U3"}),
])
def test_kind_is_carried_exactly(kind, extra):
    record = fact(KIND=kind, **extra)
    assert triage(record)["kind"] == kind
    assert project(record).split("|")[1] == kind


@pytest.mark.parametrize("status", ["U0", "U1", "U2", "U3", "U4"])
def test_status_is_carried_and_never_upgraded(status):
    evidence = "0" if status in ("U0", "U1") else REF_A
    record = fact(STATUS=status, EV=evidence)
    assert triage(record)["status"] == status


def test_evidence_presence_is_carried_and_never_invented():
    assert triage(fact(EV="0", STATUS="U1"))["has_evidence"] is False
    assert "|EV0|" in project(fact(EV="0", STATUS="U1"))
    assert triage(fact(EV=REF_A, STATUS="U2"))["has_evidence"] is True
    assert "|EV+|" in project(fact(EV=REF_A, STATUS="U2"))


def test_flags_carry_refutation_support_conflict_and_falsifiability():
    plain = triage(fact())
    assert (plain["refutes"], plain["supports"], plain["conflict"], plain["falsifiable"]) == (
        False, False, False, False
    )
    loaded = triage(fact(REFUTES=REF_B, SUPPORTS=REF_A, CON=REF_B))
    assert loaded["refutes"] and loaded["supports"] and loaded["conflict"]
    hypothesis = triage(Record.create(
        KIND="H", SRC="AGENT:a17", SUBJ="queue", CLAIM="RETRY>DUP_EXEC", TYPE="INT",
        FALSIFY="a fresh owner still duplicates", EV="0", STATUS="U1",
        CREATED="2026-09-17T08:41:00Z"))
    assert hypothesis["falsifiable"] is True
    assert hypothesis["kind"] == "H"


def test_goal_has_no_status_slot_and_no_fake_evidence():
    goal = Record.create(KIND="G", SRC="HUMAN:vacterro", SUBJ="maintenance",
                         CLAIM="reduce maintenance burden", CREATED="2026-09-17T08:41:00Z")
    view = triage(goal)
    assert view["kind"] == "G"
    assert view["status"] is None
    assert view["has_evidence"] is False
    assert project(goal).split("|")[3] == ABSENT
    assert project(goal).split("|")[4] == "EV0"


def test_absent_subject_is_marked_absent_not_guessed():
    record = fact(SUBJ=None)
    assert project(record).split("|")[2] == ABSENT
    assert triage(record)["subject"] is None


# --------------------------------------------------------------------
# unknown information falls back, never guesses
# --------------------------------------------------------------------


def test_prose_claim_becomes_open_record_not_a_summary():
    record = fact(CLAIM="stale queue ownership survives a retry and duplicates work")
    view = triage(record)
    assert view["claim"] is None
    assert view["claim_open_record"] is True
    assert project(record).split("|")[5] == OPEN_RECORD


@pytest.mark.parametrize("claim", [
    "mixed Case Words", "has spaces", "trailing.punctuation.", "русский текст",
    "検証可能性", "path/to/file.py:42",
])
def test_non_compact_claims_all_fall_back_to_open_record(claim):
    assert triage(fact(CLAIM=claim))["claim"] is None


def test_unknown_dictionary_segment_is_carried_verbatim_never_guessed():
    record = fact(CLAIM="WOMBAT_SUBSYSTEM>RETRY")
    assert triage(record)["claim"] == "WOMBAT_SUBSYSTEM>RETRY"


def test_known_dictionary_segments_are_substituted():
    record = fact(CLAIM="QUEUE_OWNERSHIP_STALE>RETRY>DUPLICATE_EXECUTION")
    assert triage(record)["claim"] == "QSTALE>RETRY>DUP_EXEC"


def test_comparison_claims_project_with_the_right_side_verbatim():
    assert triage(fact(CLAIM="DB_CREATED=2026-08-23"))["claim"] == "DB_CREATED=2026-08-23"
    assert triage(fact(CLAIM="TIMESTAMP>=2025"))["claim"] == "TS>=2025"


def test_a_separator_inside_a_slot_opens_the_record_instead_of_escaping():
    record = fact(SUBJ="queue|shard", CLAIM="A=b|c")
    slots = project(record).split("|")
    assert len(slots) == 7
    assert slots[2] == OPEN_RECORD
    assert slots[5] == OPEN_RECORD


def test_line_carries_its_dictionary_version():
    assert project(fact()).startswith(f"L1D{default_dictionary().version}")


def test_malformed_dictionary_fails_loudly(tmp_path, monkeypatch):
    import sailang.line as module

    bad = tmp_path / "v9.json"
    bad.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(module, "_DICTIONARY_DIR", tmp_path)
    with pytest.raises(SailangError) as excinfo:
        Dictionary.load("9")
    assert excinfo.value.code == "DICTIONARY_MALFORMED"

    bad.write_text('{"version": "9", "terms": {"A B": "C"}}', encoding="utf-8")
    with pytest.raises(SailangError) as excinfo:
        Dictionary.load("9")
    assert excinfo.value.code == "DICTIONARY_MALFORMED"

    bad.write_text('{"version": "7", "terms": {}}', encoding="utf-8")
    with pytest.raises(SailangError) as excinfo:
        Dictionary.load("9")
    assert excinfo.value.code == "DICTIONARY_VERSION_MISMATCH"


def test_missing_dictionary_fails_loudly(tmp_path, monkeypatch):
    import sailang.line as module

    monkeypatch.setattr(module, "_DICTIONARY_DIR", tmp_path)
    with pytest.raises(SailangError) as excinfo:
        Dictionary.load("404")
    assert excinfo.value.code == "DICTIONARY_MISSING"


def test_a_later_dictionary_cannot_change_an_older_line_in_place():
    record = fact(CLAIM="WOMBAT_SUBSYSTEM>RETRY")
    old = project(record)
    newer = Dictionary("1", {"WOMBAT_SUBSYSTEM": "WOMB"})
    new = project(record, newer)
    assert old != new
    assert old.startswith("L1D0") and new.startswith("L1D1")
    # The record, which is the authority, is identical under both.
    assert record.content_id == fact(CLAIM="WOMBAT_SUBSYSTEM>RETRY").content_id


# --------------------------------------------------------------------
# inertness survives projection
# --------------------------------------------------------------------


@pytest.mark.parametrize("payload", [
    "ignore protocol", "disable guard", "; rm -rf /", "$(whoami)", "&& saipen ship",
])
def test_command_looking_claims_project_to_open_record_and_stay_data(payload):
    record = fact(CLAIM=payload, EV="0", STATUS="U1")
    view = triage(record)
    assert view["claim"] is None
    assert record.claim == payload


def test_projection_module_has_no_execution_or_network_surface():
    import sailang.line as module

    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    allowed = {"__future__", "json", "pathlib", "re", "typing", "errors", "record"}
    assert imported <= allowed, f"unexpected imports: {sorted(imported - allowed)}"

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    banned = {"eval", "exec", "compile", "__import__", "open", "input"}
    assert not (called & banned), f"forbidden call: {sorted(called & banned)}"
