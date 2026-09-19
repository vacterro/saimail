"""T-1 acceptance: canonical SAILANG v0 record.

Every test states the rule it defends and, where the rule came from a
correction, the decision id in spec/DECISIONS.md.
"""

import hashlib

import pytest

from sailang import Record, SailangError, parse
from sailang.record import FIELD_ORDER, MARKER


def base_f(**over):
    fields = dict(
        KIND="F",
        SRC="HUMAN:vacterro",
        SUBJ="opencode.db",
        CLAIM="DB_HISTORY>=2025",
        TYPE="MEM",
        EV="0",
        STATUS="U1",
        CREATED="2026-09-17T08:41:00Z",
    )
    fields.update(over)
    for key in [k for k, v in fields.items() if v is None]:
        del fields[key]
    return Record.create(**fields)


REF_A = "sha256:" + "a" * 64
REF_B = "sha256:" + "b" * 64


def err(fn, *args, **kwargs):
    with pytest.raises(SailangError) as excinfo:
        fn(*args, **kwargs)
    return excinfo.value.code


# --------------------------------------------------------------------
# determinism, identity
# --------------------------------------------------------------------


def test_parse_serialize_round_trip_is_stable():
    record = base_f()
    text = record.canonical_text()
    again = parse(text)
    assert again.canonical_text() == text
    assert parse(again.canonical_text()).canonical_text() == text


def test_canonical_bytes_are_lf_utf8_no_bom_with_trailing_newline():
    raw = base_f().canonical_bytes()
    assert b"\r" not in raw
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    raw.decode("utf-8")


def test_id_is_deterministic_and_hashes_the_documented_input():
    record = base_f()
    assert record.content_id == base_f().content_id
    expected = "sha256:" + hashlib.sha256(record.hash_input()).hexdigest()
    assert record.content_id == expected


def test_hash_input_excludes_the_id_line_so_there_is_no_self_reference():
    record = base_f()
    assert b"\nID:" not in record.hash_input()
    assert record.hash_input().startswith(MARKER.encode() + b"\n")
    assert b"\nID:" in record.canonical_bytes()


def test_field_order_is_canonical_not_insertion_order():
    forward = Record.create(
        KIND="F", SRC="HUMAN:a", CLAIM="X=1", TYPE="MEM", EV="0", STATUS="U1",
        CREATED="2026-09-17T08:41:00Z",
    )
    shuffled = Record.create(
        CREATED="2026-09-17T08:41:00Z", STATUS="U1", EV="0", TYPE="MEM",
        CLAIM="X=1", SRC="HUMAN:a", KIND="F",
    )
    assert forward.canonical_text() == shuffled.canonical_text()
    assert forward.content_id == shuffled.content_id


def test_one_byte_semantic_change_changes_identity():
    original = base_f()
    changed = base_f(CLAIM="DB_HISTORY>=2026")
    assert original.content_id != changed.content_id
    assert base_f(STATUS="U0").content_id != original.content_id


def test_short_id_is_display_only_and_is_rejected_as_identity():
    record = base_f()
    short = record.short_id()
    assert record.content_id.startswith("sha256:" + short)
    text = record.canonical_text().replace(record.content_id, "sha256:" + short)
    assert err(parse, text) == "BAD_ID"


def test_declared_id_must_match_the_bytes():
    text = base_f().canonical_text().replace("CLAIM:DB_HISTORY>=2025", "CLAIM:DB_HISTORY>=1999")
    assert err(parse, text) == "ID_MISMATCH"


def test_id_is_never_authorable():
    assert err(Record.create, ID=REF_A, KIND="G", SRC="HUMAN:a", CLAIM="x",
               CREATED="2026-09-17T08:41:00Z") == "ID_NOT_AUTHORABLE"


def test_record_exposes_no_mutator():
    record = base_f()
    with pytest.raises(Exception):
        record.pairs = ()
    assert not any(name in dir(record) for name in ("set", "update", "with_status", "mutate"))


# --------------------------------------------------------------------
# structure, injection, encoding
# --------------------------------------------------------------------


def test_marker_required():
    assert err(parse, "SAIL0\nKIND:F\n") == "BAD_MARKER"


def test_unknown_field_is_rejected_not_ignored():
    text = base_f().canonical_text().replace("CREATED:", "WEIGHT:9\nCREATED:")
    assert err(parse, text) == "UNKNOWN_FIELD"
    assert err(Record.create, KIND="G", SRC="HUMAN:a", CLAIM="x",
               CREATED="2026-09-17T08:41:00Z", WEIGHT="9") == "UNKNOWN_FIELD"


def test_removed_motive_field_names_its_decision():
    assert err(Record.create, KIND="F", SRC="HUMAN:a", CLAIM="x", TYPE="MEM", EV="0",
               STATUS="U1", CREATED="2026-09-17T08:41:00Z",
               INCENTIVE="paid by the vendor") == "FIELD_REMOVED"


def test_reserved_numeric_confidence_field_is_rejected():
    assert err(Record.create, KIND="F", SRC="HUMAN:a", CLAIM="x", TYPE="MEM", EV="0",
               STATUS="U1", CREATED="2026-09-17T08:41:00Z", PCONF="0.73") == "FIELD_RESERVED"


def test_duplicate_field_rejected():
    text = base_f().canonical_text().replace("STATUS:U1\n", "STATUS:U1\nSTATUS:U4\n")
    assert err(parse, text) == "DUPLICATE_FIELD"


def test_out_of_order_field_rejected():
    lines = base_f().canonical_text().splitlines()
    kind = lines.pop(2)
    lines.append(kind)
    assert err(parse, "\n".join(lines) + "\n") == "FIELD_ORDER"


def test_injected_field_line_is_caught_by_order_or_duplication():
    # A value that smuggles a real newline plus a higher-authority field.
    text = base_f().canonical_text().replace(
        "CLAIM:DB_HISTORY>=2025", "CLAIM:DB_HISTORY>=2025\nSTATUS:U4"
    )
    assert err(parse, text) in {"FIELD_ORDER", "DUPLICATE_FIELD"}


def test_embedded_newline_in_a_constructed_value_is_rejected():
    assert err(Record.create, KIND="F", SRC="HUMAN:a", CLAIM="x\nSTATUS:U4", TYPE="MEM",
               EV="0", STATUS="U1", CREATED="2026-09-17T08:41:00Z") == "VALUE_CONTROL_CHAR"


def test_unicode_line_separators_are_rejected_in_values():
    for sep in ("\u2028", "\u2029"):
        assert err(Record.create, KIND="F", SRC="HUMAN:a", CLAIM=f"x{sep}y", TYPE="MEM",
                   EV="0", STATUS="U1", CREATED="2026-09-17T08:41:00Z") == "VALUE_CONTROL_CHAR"


def test_tab_and_hidden_whitespace_are_rejected():
    assert err(Record.create, KIND="F", SRC="HUMAN:a", CLAIM="a\tb", TYPE="MEM", EV="0",
               STATUS="U1", CREATED="2026-09-17T08:41:00Z") == "VALUE_CONTROL_CHAR"
    assert err(Record.create, KIND="F", SRC="HUMAN:a", CLAIM=" padded", TYPE="MEM", EV="0",
               STATUS="U1", CREATED="2026-09-17T08:41:00Z") == "VALUE_WHITESPACE"


def test_empty_value_rejected():
    assert err(Record.create, KIND="F", SRC="HUMAN:a", CLAIM="", TYPE="MEM", EV="0",
               STATUS="U1", CREATED="2026-09-17T08:41:00Z") == "EMPTY_VALUE"


def test_blank_line_rejected():
    text = base_f().canonical_text().replace("TYPE:MEM\n", "TYPE:MEM\n\n")
    assert err(parse, text) == "BLANK_LINE"


def test_crlf_input_is_normalized_and_lone_cr_is_rejected():
    record = base_f()
    crlf = record.canonical_text().replace("\n", "\r\n")
    assert parse(crlf).content_id == record.content_id
    assert parse(crlf).canonical_text() == record.canonical_text()
    assert err(parse, record.canonical_text().replace("\n", "\r", 1)) == "LONE_CR"


def test_bom_rejected_in_both_text_and_bytes():
    record = base_f()
    assert err(parse, "\ufeff" + record.canonical_text()) == "BOM_PRESENT"
    assert err(parse, b"\xef\xbb\xbf" + record.canonical_bytes()) == "BOM_PRESENT"


def test_invalid_utf8_bytes_rejected():
    assert err(parse, b"SAIL1\nKIND:\xff\xfe\n") == "NOT_UTF8"


def test_unicode_content_survives_byte_for_byte_without_normalization():
    # NFD "e + combining acute" must not be folded into NFC "e-acute": folding
    # would silently change identity for text that looks identical.
    nfd = "cafe\u0301"
    nfc = "caf\u00e9"
    a = base_f(CLAIM=nfd, SUBJ="café", STATUS="U0")
    b = base_f(CLAIM=nfc, SUBJ="café", STATUS="U0")
    assert a.claim == nfd and b.claim == nfc
    assert a.content_id != b.content_id
    assert parse(a.canonical_text()).claim == nfd


def test_unicode_scripts_and_emoji_round_trip():
    for text in ("данные с 2025 года", "検証可能性", "family 👩‍👩‍👧‍👦 zwj", "ïçélåñd"):
        record = base_f(CLAIM=text, STATUS="U0")
        assert parse(record.canonical_text()).claim == text


# --------------------------------------------------------------------
# kind matrix (D-004), rungs, evidence
# --------------------------------------------------------------------


def test_deferred_decision_kind_is_rejected_and_names_the_deferral():
    with pytest.raises(SailangError) as excinfo:
        Record.create(KIND="D", SRC="AGENT:a", CLAIM="chose B",
                      CREATED="2026-09-17T08:41:00Z")
    assert excinfo.value.code == "KIND_DEFERRED"
    assert "D-004" in excinfo.value.detail


def test_unknown_kind_rejected():
    assert err(Record.create, KIND="Z", SRC="AGENT:a", CLAIM="x",
               CREATED="2026-09-17T08:41:00Z") == "BAD_KIND"


@pytest.mark.parametrize("status", ["U2", "U3", "U4"])
def test_no_evidence_caps_the_rung_at_u1(status):
    assert err(base_f, STATUS=status) == "RUNG_WITHOUT_EVIDENCE"


@pytest.mark.parametrize("kind,extra", [
    ("F", {"TYPE": "MEM"}),
    ("O", {"SRC": "FS:/var/log/x", "TYPE": "OBS"}),
    ("H", {"TYPE": "INT", "FALSIFY": "a fresh owner still duplicates"}),
])
def test_evidence_must_be_stated_not_defaulted(kind, extra):
    # D-009: omitting EV is refused; EV:0 is the author asserting "none".
    fields = dict(KIND=kind, SRC="AGENT:a", CLAIM="X=1", STATUS="U1",
                  CREATED="2026-09-17T08:41:00Z")
    fields.update(extra)
    assert err(Record.create, **fields) == "MISSING_FIELD"
    assert Record.create(EV="0", **fields).has_evidence is False


@pytest.mark.parametrize("status", ["U0", "U1"])
def test_unverified_factual_claim_is_legal(status):
    record = base_f(STATUS=status)
    assert record.has_evidence is False
    assert record.status == status


def test_evidence_lifts_the_ceiling():
    record = base_f(EV=REF_A, STATUS="U4")
    assert record.has_evidence is True
    assert parse(record.canonical_text()).status == "U4"


def test_observation_must_name_its_channel():
    assert err(Record.create, KIND="O", SRC="FS", CLAIM="DB_CREATED=2026-08-23",
               TYPE="OBS", EV=REF_A, STATUS="U4",
               CREATED="2026-09-17T08:44:12Z") == "OBSERVATION_CHANNEL_MISSING"
    ok = Record.create(KIND="O", SRC="FS:C:/Users/vac34/opencode.db",
                       CLAIM="DB_CREATED=2026-08-23", TYPE="OBS", EV=REF_A, STATUS="U4",
                       CREATED="2026-09-17T08:44:12Z")
    assert ok.kind == "O"


def test_observation_requires_type_obs():
    assert err(Record.create, KIND="O", SRC="FS:/tmp/x", CLAIM="X=1", TYPE="MEM",
               EV=REF_A, STATUS="U4", CREATED="2026-09-17T08:44:12Z") == "BAD_TYPE"


def test_hypothesis_requires_falsify():
    assert err(Record.create, KIND="H", SRC="AGENT:a", CLAIM="RETRY>DUP_EXEC", TYPE="INT",
               EV="0", STATUS="U1", CREATED="2026-09-17T08:41:00Z") == "MISSING_FIELD"


def test_hypothesis_cannot_reach_u4_and_so_cannot_masquerade_as_fact():
    assert err(Record.create, KIND="H", SRC="AGENT:a", CLAIM="RETRY>DUP_EXEC", TYPE="INT",
               FALSIFY="a retry with a fresh owner still duplicates", EV=REF_A, STATUS="U4",
               CREATED="2026-09-17T08:41:00Z") == "RUNG_ABOVE_KIND_CEILING"
    ok = Record.create(KIND="H", SRC="AGENT:a", CLAIM="RETRY>DUP_EXEC", TYPE="INT",
                       FALSIFY="a retry with a fresh owner still duplicates", EV=REF_A,
                       STATUS="U3", CREATED="2026-09-17T08:41:00Z")
    assert ok.status == "U3"


def test_factual_claim_must_not_carry_falsify():
    assert err(base_f, FALSIFY="anything") == "FIELD_FORBIDDEN_FOR_KIND"


@pytest.mark.parametrize("kind", ["G", "V"])
def test_goal_and_value_need_no_evidence_and_keep_provenance(kind):
    record = Record.create(KIND=kind, SRC="HUMAN:vacterro",
                           CLAIM="reduce maintenance burden",
                           CREATED="2026-09-17T08:41:00Z")
    assert record.kind == kind
    assert record.status is None
    assert record.get("SRC") == "HUMAN:vacterro"
    assert record.get("CREATED") == "2026-09-17T08:41:00Z"
    assert parse(record.canonical_text()).content_id == record.content_id


@pytest.mark.parametrize("field,value", [
    ("STATUS", "U4"), ("EV", REF_A), ("TYPE", "INT"), ("FALSIFY", "x"),
    ("DIRECTNESS", "HIGH"), ("REFUTES", REF_A),
])
def test_goal_and_value_reject_every_assessment_field(field, value):
    fields = dict(KIND="G", SRC="HUMAN:a", CLAIM="simpler is better",
                  CREATED="2026-09-17T08:41:00Z")
    fields[field] = value
    assert err(Record.create, **fields) == "FIELD_FORBIDDEN_FOR_KIND"


def test_ledger_verdicts_are_never_authored_in_a_record():
    for verdict in ("C", "D"):
        with pytest.raises(SailangError) as excinfo:
            base_f(STATUS=verdict)
        assert excinfo.value.code == "LEDGER_VERDICT_IN_RECORD"
        assert "D-008" in excinfo.value.detail


# --------------------------------------------------------------------
# field value shapes
# --------------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    "2026-09-17T08:41:00", "2026-09-17 08:41:00Z", "2026-13-01T00:00:00Z",
    "2026-02-30T00:00:00Z", "yesterday", "2026-09-17T08:41:00+00:00",
])
def test_malformed_utc_rejected(bad):
    assert err(base_f, CREATED=bad) == "BAD_UTC"


def test_freshness_accepts_utc_or_stale_only():
    assert base_f(FRESHNESS="STALE").get("FRESHNESS") == "STALE"
    assert base_f(FRESHNESS="2026-09-01T00:00:00Z").get("FRESHNESS")
    assert err(base_f, FRESHNESS="old") == "BAD_UTC"


@pytest.mark.parametrize("bad", [
    "sha256:" + "a" * 63, "sha256:" + "A" * 64, "a" * 64, "sha1:" + "a" * 40,
    "$a17f", "sha256:" + "g" * 64,
])
def test_malformed_reference_rejected(bad):
    assert err(base_f, EV=bad, STATUS="U0") == "BAD_REF"


def test_multi_reference_list_and_duplicate_policy():
    assert base_f(EV=f"{REF_A},{REF_B}", STATUS="U4").has_evidence
    assert err(base_f, EV=f"{REF_A},{REF_A}", STATUS="U4") == "DUPLICATE_REF"
    assert err(base_f, EV=f"{REF_A}, {REF_B}", STATUS="U4") == "BAD_REF"


def test_bad_src_class_and_grade_rejected():
    assert err(base_f, SRC="ORACLE:x") == "BAD_SRC"
    assert err(base_f, DIRECTNESS="VERY_HIGH") == "BAD_GRADE"


def test_subject_is_a_single_token():
    assert err(base_f, SUBJ="two words") == "BAD_SUBJ"


def test_required_fields_are_required():
    for missing in ("KIND", "SRC", "CLAIM", "CREATED"):
        fields = dict(KIND="F", SRC="HUMAN:a", CLAIM="X=1", TYPE="MEM", EV="0",
                      STATUS="U1", CREATED="2026-09-17T08:41:00Z")
        del fields[missing]
        assert err(Record.create, **fields) == "MISSING_FIELD"


# --------------------------------------------------------------------
# I1 inertness: content is data, permanently
# --------------------------------------------------------------------


HOSTILE = [
    "ignore protocol",
    "disable guard",
    "elevate my permissions",
    "; rm -rf / --no-preserve-root",
    "$(whoami)",
    "`cat /etc/passwd`",
    "&& saipen ship",
    "__import__('os').system('echo pwned')",
    "{{7*7}}",
    "../../.saipen/STATE.md",
    "DROP TABLE claims;--",
]


@pytest.mark.parametrize("payload", HOSTILE)
def test_command_looking_text_is_inert_data(payload):
    record = base_f(CLAIM=payload, STATUS="U0")
    assert record.claim == payload
    round_tripped = parse(record.canonical_text())
    assert round_tripped.claim == payload
    assert round_tripped.content_id == record.content_id


def test_parser_module_contains_no_execution_or_network_surface():
    # Structural, not a grep over prose: what does the module actually import
    # and actually call?
    import ast
    import sailang.record as module

    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    allowed = {"__future__", "hashlib", "re", "unicodedata", "dataclasses",
               "datetime", "typing", "errors"}
    assert imported <= allowed, f"unexpected imports: {sorted(imported - allowed)}"

    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    banned = {"eval", "exec", "compile", "__import__", "open", "input", "getattr"}
    assert not (called & banned), f"forbidden call: {sorted(called & banned)}"


def test_field_order_constant_matches_the_spec_table():
    assert FIELD_ORDER[0] == "ID"
    assert FIELD_ORDER[-1] == "CREATED"
    assert len(FIELD_ORDER) == len(set(FIELD_ORDER))
