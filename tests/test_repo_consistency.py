"""T-13 acceptance: source continuity, derived-doc consistency, reproducibility.

Derived documents are projections. A projection that contradicts the decision
log is drift, and drift is what this file is for.
"""

import pathlib
import re
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec"
INTAKE = ROOT / ".saipen" / "intake" / "active"

DOCS = sorted(SPEC.glob("*.md")) + [ROOT / "README.md", ROOT / "bench" / "ANALYSIS.md"]


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------
# source continuity
# --------------------------------------------------------------------


# SRC-002 recorded the path `idea_continue.md`; the operator renamed that working
# file to `idea_continue1.md` on 2026-09-17. The receipt is unchanged.
@pytest.mark.parametrize("receipt,origin", [("SRC-001", "idea.md"), ("SRC-002", "idea_continue1.md")])
def test_every_source_document_has_an_immutable_receipt(receipt, origin):
    body = INTAKE / f"{receipt}.md"
    meta = INTAKE / f"{receipt}.meta.json"
    assert body.is_file(), f"{receipt} body missing"
    assert meta.is_file(), f"{receipt} sidecar missing"
    assert (ROOT / origin).is_file(), f"{origin} missing"


def test_the_two_sources_are_separate_receipts_not_a_merge():
    import hashlib
    import json

    digests = {}
    for receipt in ("SRC-001", "SRC-002"):
        meta = json.loads(read(INTAKE / f"{receipt}.meta.json"))
        body = (INTAKE / f"{receipt}.md").read_bytes()
        digests[receipt] = meta["source_sha256"]
        assert hashlib.sha256(body).hexdigest() == meta["source_sha256"], (
            f"{receipt} body does not match its recorded digest"
        )
    assert digests["SRC-001"] != digests["SRC-002"]


def test_backlog_cites_the_receipt_it_came_from():
    backlog = read(SPEC / "BACKLOG.md")
    assert "SRC-002" in backlog
    for entry in ("B-001", "B-002", "B-004", "B-005"):
        assert entry in backlog, f"{entry} missing from the backlog"


# --------------------------------------------------------------------
# derived docs agree with the decision log
# --------------------------------------------------------------------


def decision_ids() -> set:
    return set(re.findall(r"^## (D-\d{3})", read(SPEC / "DECISIONS.md"), flags=re.MULTILINE))


def test_every_decision_referenced_anywhere_actually_exists():
    known = decision_ids()
    assert known, "the decision log has no decisions"
    for doc in DOCS + sorted(ROOT.glob("*.py")) + sorted((ROOT / "sailang").glob("*.py")):
        referenced = set(re.findall(r"\bD-\d{3}\b", read(doc)))
        unknown = referenced - known
        assert not unknown, f"{doc.name} cites decisions that do not exist: {sorted(unknown)}"


def test_removed_novelty_field_survives_nowhere_in_the_spec():
    # DECISIONS.md and BACKLOG.md are history: naming what was removed is their
    # job. Every other derived document is a projection of the current design.
    history = {"DECISIONS.md", "BACKLOG.md"}
    for doc in DOCS:
        if doc.name in history:
            continue
        assert "N:83" not in read(doc), f"{doc.name} still carries the removed novelty field"


def test_no_short_hash_notation_survives_as_identity():
    # `$a17f` style references were replaced by full sha256 identity in D-003.
    pattern = re.compile(r"\$[0-9a-fA-F]{4,8}\b")
    for doc in DOCS:
        hits = pattern.findall(read(doc))
        assert not hits, f"{doc.name} still uses short-hash identity: {hits}"


def test_promotion_is_described_as_kind_aware_everywhere_it_is_described():
    for name in ("03-POST-OFFICE.md", "04-SAIPEN-SEAM.md"):
        text = read(SPEC / name)
        if "promotion" in text.lower():
            assert "D-006" in text, f"{name} describes promotion without citing D-006"
    universal = "promotion without an evidence ref is refused, not warned"
    for doc in DOCS:
        assert universal not in read(doc), f"{doc.name} still states the pre-D-006 universal rule"


def test_deferred_decision_kind_is_not_advertised_as_a_v0_kind():
    for name in ("00-PRINCIPLES.md", "01-SAILANG-v0.md", "04-SAIPEN-SEAM.md"):
        text = read(SPEC / name)
        assert "F / O / H / G / V / D" not in text, f"{name} still lists D as a v0 kind"


def test_readme_does_not_claim_the_code_does_not_exist():
    readme = read(ROOT / "README.md")
    assert "No implementation yet" not in readme
    assert "sailang" in readme


def test_every_document_readme_links_to_exists():
    readme = read(ROOT / "README.md")
    for target in re.findall(r"\]\(([^)]+)\)", readme):
        if target.startswith("http"):
            continue
        assert (ROOT / target).exists(), f"README links to a missing file: {target}"


# --------------------------------------------------------------------
# reproducibility
# --------------------------------------------------------------------


def test_dependency_surface_is_declared():
    config = tomllib.loads(read(ROOT / "pyproject.toml"))
    project = config["project"]
    assert project["requires-python"]
    assert project["dependencies"] == [], "the library itself must stay dependency free"
    extras = project["optional-dependencies"]
    assert any(dep.startswith("pytest") for dep in extras["test"])
    # D-014: the extra behind the advertised command installs everything the
    # full suite imports, tokenizer included.
    assert any(dep.startswith("tiktoken") for dep in extras["test"]), (
        "`python -m pytest -q` is advertised with the test extra, and four tests "
        "import tiktoken; the extra must cover them"
    )
    bench = extras["bench"]
    tokenizer = [dep for dep in bench if dep.startswith("tiktoken")]
    assert tokenizer, "the benchmark tokenizer must be declared"
    assert re.search(r"[<>=]", tokenizer[0]), (
        "the tokenizer must be constrained: an unpinned BPE table silently changes "
        "every published ratio"
    )


def test_no_tokenizer_data_or_model_weights_are_vendored():
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".saipen" in path.parts:
            continue
        assert path.suffix not in {".bin", ".safetensors", ".gguf", ".pt", ".onnx"}, (
            f"{path} looks like vendored model data"
        )
        if path.stat().st_size > 2_000_000:
            raise AssertionError(f"{path} is unexpectedly large for this repository")


def test_declared_shipped_modules_actually_import():
    import sailang
    import sailang.line

    assert sailang.Record and sailang.parse
    assert sailang.line.project


def test_post_office_semantics_are_recorded_before_the_store():
    # T-36/T-43 recorded the T-5 preconditions in D-031/D-036 and spec/03
    # section 8; T-45 (SRC-022) then built the store those semantics describe.
    # The tripwire therefore flips at the phase transition: the module must now
    # exist, while the mailbox root stays caller-supplied — the repository
    # itself still carries no store.
    decisions = read(SPEC / "DECISIONS.md")
    assert re.search(r"^## D-031\b", decisions, flags=re.MULTILINE), "D-031 is missing"
    for marker in ("ENVELOPE_ID", "RECEIVED_AT", "FIRST_RECEIVED_AT", "B-014"):
        assert marker in decisions, f"{marker} is not recorded in DECISIONS.md"
    post_office = read(SPEC / "03-POST-OFFICE.md")
    for marker in ("D-031", "ENVELOPE_ID", "RECEIVED_AT", "FIRST_RECEIVED_AT", "B-014"):
        assert marker in post_office, f"03-POST-OFFICE.md does not record {marker}"
    assert (ROOT / "saimail" / "postoffice.py").is_file(), (
        "T-45 built the Post Office under the recorded semantics; the module is missing"
    )
    assert not (ROOT / "mail").exists(), (
        "the Post Office root is caller-supplied; no mailbox lives in the repository"
    )


def test_the_attention_floor_is_decided_before_a_post_office_exists():
    # T-37: B-014 is the one question T-5 must answer first, so it is greppable
    # from all three surfaces and this tripwire turns "we forgot" into a red
    # test the moment the store appears.
    post_office = read(SPEC / "03-POST-OFFICE.md")
    decisions = read(SPEC / "DECISIONS.md")
    backlog = read(SPEC / "BACKLOG.md")
    for name, text in (("03-POST-OFFICE.md", post_office), ("DECISIONS.md", decisions),
                       ("BACKLOG.md", backlog)):
        assert "MACHINE_REQUIRED_OPEN" in text, f"{name} does not name the pending decision"
    state = re.search(r"ATTENTION_FLOOR: (PENDING|DECIDED)", post_office)
    assert state, "03-POST-OFFICE.md section 8 carries no attention-floor state marker"
    started = ((ROOT / "mail").exists()
               or list((ROOT / "saimail").glob("*postoffice*"))
               or list((ROOT / "saimail").glob("*post_office*")))
    if state.group(1) == "PENDING":
        assert not started, (
            "a Post Office may not be implemented while the attention floor is PENDING: "
            "decide B-014 on the recorded evidence first"
        )


def test_the_attention_floor_decision_is_recorded_and_non_downgradable():
    # T-43 / SRC-020 Target B1: B-014 is DECIDED, by a numbered decision entry
    # that states the floor in full: machine-required opens may rise in
    # resolution, never fall to DEFER/IGNORE.
    post_office = read(SPEC / "03-POST-OFFICE.md")
    state = re.search(r"ATTENTION_FLOOR: (PENDING|DECIDED)", post_office)
    assert state and state.group(1) == "DECIDED", (
        "B-014 was decided under SRC-020; the marker must say so"
    )
    decisions = read(SPEC / "DECISIONS.md")
    entry = re.search(r"^## D-036 .*?(?=^## )", decisions,
                      flags=re.MULTILINE | re.DOTALL)
    assert entry, "D-036 (the B-014 decision entry) is missing from DECISIONS.md"
    body = entry.group(0)
    for needle in ("MACHINE_REQUIRED_OPEN", "never `DEFER`", "remains `OPEN_R3`"):
        assert needle in body, f"D-036 must state the floor: missing {needle!r}"
    assert "non-downgradable" in body.lower()


def test_header_scan_cannot_promote():
    # T-43 / SRC-020 Target B2: header attention is not memory promotion. The
    # interest-filter table may not carry a PROMOTE verdict, and the promotion
    # boundary (opened payload + D-035 gate) must stay stated in the spec.
    post_office = read(SPEC / "03-POST-OFFICE.md")
    verdict_table = post_office[post_office.index("## 3. The interest filter"):
                                post_office.index("## 4. Three memory tiers")]
    verdict_rows = [line for line in verdict_table.splitlines()
                    if line.startswith("| `")]
    verdicts = {row.split("|")[1].strip() for row in verdict_rows}
    assert verdicts == {"`OPEN`", "`DEFER`", "`IGNORE`"}, (
        f"header-only scan verdicts are OPEN/DEFER/IGNORE, got {sorted(verdicts)}"
    )
    assert "HEADER ATTENTION != MEMORY PROMOTION" in post_office, (
        "the promotion boundary principle is not stated"
    )
    assert "D-035" in post_office, "promotion must cite the payload-bound gate"


def test_header_scan_age_is_receiver_local():
    # T-44 / SRC-021 Target B2: the interest-filter age the reader sees is a
    # receiver-local observation, never the sender-authored CREATED clock.
    post_office = read(SPEC / "03-POST-OFFICE.md")
    assert "HEADER_SCAN AGE" in post_office, "the header-scan age is not defined"
    assert "now - RECEIVED_AT" in post_office, (
        "header-scan age must be derived from RECEIVED_AT"
    )
    assert "never `current_time - CREATED`" in post_office, (
        "the spec must name the rejected sender-clock reading"
    )


def test_the_attention_floor_merge_rule_is_recorded():
    # T-45 / SRC-022: D-037 completes the merge D-036 left open for the
    # DEFER/IGNORE interactions, now that the reader that enforces it exists.
    # The exact rule is on record for every case, and no model-vs-machine case
    # stays undecided.
    post_office = read(SPEC / "03-POST-OFFICE.md")
    for needle in (
        "machine `OPEN_R2` + model `IGNORE` -> `OPEN_R2`",
        "machine `OPEN_R2` + model `DEFER` -> `OPEN_R2`",
        "machine `OPEN_R2` + model `OPEN_R3` -> `OPEN_R3`",
        "machine `OPEN_R3` + any lower verdict -> `OPEN_R3`",
        "machine `IGNORE` + model `DEFER` -> `DEFER`",
        "machine `IGNORE` + model `OPEN_R2` -> `OPEN_R2`",
        "machine `DEFER` + model `OPEN_R3` -> `OPEN_R3`",
        "no model recommendation -> the machine verdict unchanged",
    ):
        assert needle in post_office, f"merge rule missing: {needle!r}"
    assert "D-037" in post_office, (
        "the completed merge must cite the decision that records it"
    )
    assert "stay undecided here" not in post_office, (
        "the DEFER/IGNORE merge is decided now that the Post Office reader exists"
    )
    decisions = read(SPEC / "DECISIONS.md")
    assert re.search(r"^## D-037\b", decisions, flags=re.MULTILINE), (
        "D-037 (the completed merge decision) is missing from DECISIONS.md"
    )


def test_ttl_sweep_contract_is_recorded_before_the_sweep_exists():
    # T-7 / SRC-026: the T-7 execution contract was captured before any TTL
    # code, exactly as T-5's preconditions were. The tripwire turns "we forgot
    # the decision" into a red test the moment the sweep appears.
    decisions = read(SPEC / "DECISIONS.md")
    entry = re.search(r"^## D-038 .*?(?=^## )", decisions,
                      flags=re.MULTILINE | re.DOTALL)
    assert entry, "D-038 (the T-7 TTL contract) is missing from DECISIONS.md"
    body = entry.group(0)
    for needle in ("14", "RETENTION_CEILING", "RECEIVED_AT",
                   "EXPLICIT_MAINTENANCE", "TTL_EXPIRED", "ALREADY_EXPIRED",
                   "DUPLICATE_NO_RESURRECTION", "OUT_OF_SCOPE"):
        assert needle in body, f"D-038 must record {needle!r}"
    post_office = read(SPEC / "03-POST-OFFICE.md")
    for needle in ("D-038", "effective_ttl", "RECEIVED_AT", "sweep_expired",
                   "mail/expired/<seat>", "ALREADY_EXPIRED"):
        assert needle in post_office, f"03-POST-OFFICE.md does not record {needle!r}"
    readme = read(ROOT / "README.md")
    row = readme.split("TTL sweep to tombstone (T-7", 1)[1].split("\n")[0]
    assert "not built" not in row, (
        "the README still advertises the T-7 sweep as not built after it shipped"
    )


def test_tombstone_authority_repair_is_recorded():
    # T-49 / SRC-028: the tombstone-authority and one-pass-convergence repair is
    # recorded additively; D-038 itself stays untouched history.
    decisions = read(SPEC / "DECISIONS.md")
    assert re.search(r"^## D-038\b", decisions, flags=re.MULTILINE), "D-038 is missing"
    entry = re.search(r"^## D-039 .*?(?=^## )", decisions,
                      flags=re.MULTILINE | re.DOTALL)
    assert entry, "D-039 (the T-49 repair decision) is missing from DECISIONS.md"
    body = entry.group(0)
    for needle in ("REFERENCE_EXISTS", "INDEX_BODY_MISSING",
                   "EXPIRED_TOMBSTONE_CORRUPT", "EXPIRED_TOMBSTONE_CONFLICT",
                   "one maintenance pass", "premature"):
        assert needle.lower() in body.lower(), f"D-039 must record {needle!r}"
    post_office = read(SPEC / "03-POST-OFFICE.md")
    assert "D-039" in post_office, "03-POST-OFFICE.md does not cite D-039"


def test_legacy_contract_precedes_and_bounds_the_production_surface():
    # B-013 / T-50: D-040 froze the host-protocol object before legacy.py was
    # written. This catches the dangerous drift classes, not just file presence.
    decisions = read(SPEC / "DECISIONS.md")
    entry = re.search(r"^## D-040 .*?(?=^## |\Z)", decisions,
                      flags=re.MULTILINE | re.DOTALL)
    assert entry, "D-040 (the LEG1 production decision) is missing"
    for needle in (
        "FORMAT = LEG1", "HOST_PROTOCOL_OBJECT = true", "SAILANG_KIND_ADDED = false",
        "SENV_K = EXPERIENCE", "SENV_TOPIC = legacy", "WATCH_NEXT_STATUS = UNVERIFIED",
        "ADOPTION_REQUIRES = OpenedEnvelope", "AUTO_ADOPTION = false",
        "AUTHORITY_GAIN = none", "KNOWLEDGE_PROMOTION = none",
        "COMMAND_SEMANTICS = inert",
    ):
        assert needle in entry.group(0), f"D-040 must record {needle!r}"
    contract = read(SPEC / "04-LEGACY-v0.md")
    for needle in (
        "OBSERVED_SCOPE != NEW_TASK_SCOPE", "REFERENCE_EXISTS != REFERENCE_SUPPORTS_CLAIM",
        "mail/legacy/<recipient-seat>", "FAILED_IN_OBSERVED_SCOPE",
        "WATCH_NEXT_STATUS:UNVERIFIED",
    ):
        assert needle in contract, f"LEGACY v0 contract is missing {needle!r}"
    production = read(ROOT / "saimail" / "legacy.py")
    assert "from lab" not in production and "import lab" not in production
    assert "promotion" not in production


def test_legacy_successor_hardening_is_additive_and_receiver_owned():
    # T-51 corrects the successor surface without rewriting D-040 or LEG1.
    decisions = read(SPEC / "DECISIONS.md")
    assert re.search(r"^## D-040\b", decisions, flags=re.MULTILINE), "D-040 history moved"
    entry = re.search(r"^## D-041 .*?(?=^## |\Z)", decisions,
                      flags=re.MULTILINE | re.DOTALL)
    assert entry, "D-041 (successor provenance/order/pagination) is missing"
    for needle in (
        "LegacyStore-validated type-state", "received_at DESC",
        "PREDECESSOR_CREATED != RETRIEVAL_RECENCY",
        "CURSOR = legacy_entry_id", "LEGACY_BAD_CONTINUATION",
        "LEGACY_CONTEXT_ENTRY_TOO_LARGE", "TOTAL_MATCHES",
    ):
        assert needle in entry.group(0), f"D-041 must record {needle!r}"
    contract = read(SPEC / "04-LEGACY-v0.md")
    for needle in (
        "receiver-owned", "legacy_entry_id", "LEGACY_BAD_CONTINUATION",
        "LEGACY_CONTEXT_ENTRY_TOO_LARGE", "zero-progress",
    ):
        assert needle in contract, f"LEGACY successor contract is missing {needle!r}"
    backlog = read(SPEC / "BACKLOG.md")
    assert "P2 LEGACY_PARTIAL_ADOPTION_RECOVERY" in backlog
    assert re.search(r"no\s+recovery mechanism is implemented", backlog)
