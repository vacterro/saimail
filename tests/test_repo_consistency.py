"""T-13 acceptance: source continuity, derived-doc consistency, reproducibility.

Derived documents are projections. A projection that contradicts the decision
log is drift, and drift is what this file is for.
"""

import pathlib
import hashlib
import json
import re
import tomllib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec"
INTAKE = ROOT / ".saipen" / "intake" / "active"
RETIRED = ROOT / ".saipen" / "archive" / "retired"
TOMBSTONES = ROOT / ".saipen" / "intake" / "tombstones"
MEDIA_POLICY = ROOT / "humbox" / "media-assets.json"
SAIGIMN_PATH = ROOT / "humbox" / "SAIGIMN.mp3"
SAIGIMN_SHA256 = "e9694312b0ebcb7a1a409cea1da0b2534d60ef348b440aded7bac25959a1a870"
SAIGIMN_SIZE = 6_851_614

DOCS = sorted(SPEC.glob("*.md")) + [ROOT / "README.md", ROOT / "bench" / "ANALYSIS.md"]


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# --------------------------------------------------------------------
# source continuity
# --------------------------------------------------------------------


# SRC-002 recorded the path `idea_continue.md`; the operator renamed that working
# file to `idea_continue1.md` on 2026-09-17. The receipt is unchanged.
#
# SRC-001 and SRC-002 were RETIRED on 2026-09-21 with reason SUPERSEDED_SOURCE
# and their documented successors (spec/DECISIONS.md: "The lineage is SRC-001 ->
# SRC-003 and SRC-002 -> SRC-004 (the originals captured a path instead of a
# body and were amended, never rewritten)"; retirement events E-1294/E-1295).
# Retirement RELOCATES a receipt, it never purges it, so this invariant is now
# asserted at the location the protocol's own verb wrote and is strictly
# STRONGER than the body it replaces: it pins the digest, the retirement
# reason, the named successor and the retirement event, none of which the
# active-location form could see.
@pytest.mark.parametrize("receipt,origin,successor,event",
                         [("SRC-001", "idea.md", "SRC-003", "E-1294"),
                          ("SRC-002", "idea_continue1.md", "SRC-004", "E-1295")])
def test_every_source_document_has_an_immutable_receipt(
        receipt, origin, successor, event):
    import hashlib
    import json

    body = RETIRED / f"{receipt}.md"
    meta = RETIRED / f"{receipt}.meta.json"
    assert body.is_file(), f"{receipt} retired body missing"
    assert meta.is_file(), f"{receipt} retired sidecar missing"
    assert (ROOT / origin).is_file(), f"{origin} missing"
    digest = hashlib.sha256(body.read_bytes()).hexdigest()
    assert digest == json.loads(read(meta))["source_sha256"], (
        f"{receipt} body does not match its recorded digest"
    )
    tomb = json.loads(read(TOMBSTONES / f"{receipt}.json"))
    assert tomb["source_sha256"] == digest
    assert tomb["archive_ref"] == f".saipen/archive/retired/{receipt}.md"
    assert tomb["retirement"]["reason"] == "SUPERSEDED_SOURCE"
    assert tomb["retirement"]["successor"] == successor
    assert tomb["retirement"]["retirement_event"] == event
    assert (INTAKE / f"{successor}.md").is_file(), (
        f"{successor} is the live carrier of the lineage"
    )


def test_the_two_sources_are_separate_receipts_not_a_merge():
    import hashlib
    import json

    digests = {}
    for receipt in ("SRC-001", "SRC-002"):
        meta = json.loads(read(RETIRED / f"{receipt}.meta.json"))
        body = (RETIRED / f"{receipt}.md").read_bytes()
        digests[receipt] = meta["source_sha256"]
        assert hashlib.sha256(body).hexdigest() == meta["source_sha256"], (
            f"{receipt} body does not match its recorded digest"
        )
    assert digests["SRC-001"] != digests["SRC-002"]
    # The amendment lineage is two SEPARATE receipts, never a merge: each
    # successor carries its own body, both live, neither rewritten.
    successor_bodies = {(INTAKE / f"SRC-00{n}.md").read_bytes()
                        for n in (3, 4)}
    assert len(successor_bodies) == 2


def test_backlog_cites_the_receipt_it_came_from():
    backlog = read(SPEC / "BACKLOG.md")
    assert "SRC-002" in backlog
    for entry in ("B-001", "B-002", "B-004", "B-005"):
        assert entry in backlog, f"{entry} missing from the backlog"


# --------------------------------------------------------------------
# derived docs agree with the decision log
# --------------------------------------------------------------------


def decision_ids() -> set:
    # Frozen experiment inputs cannot change; later decisions use addenda.
    logs = [SPEC / "DECISIONS.md", *sorted(SPEC.glob("DECISIONS-D*.md"))]
    return {decision for log in logs
            for decision in re.findall(r"^## (D-\d{3})", read(log), flags=re.MULTILINE)}


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
    declared_media = _validate_intentional_media_asset()
    for path in ROOT.rglob("*"):
        if not path.is_file() or ".saipen" in path.parts or ".git" in path.parts:
            continue
        assert path.suffix not in {".bin", ".safetensors", ".gguf", ".pt", ".onnx"}, (
            f"{path} looks like vendored model data"
        )
        if path.stat().st_size > 2_000_000 and path.resolve() != declared_media.resolve():
            raise AssertionError(f"{path} is unexpectedly large for this repository")


def _validate_intentional_media_asset():
    policy = json.loads(read(MEDIA_POLICY))
    expected = {
        "schema": "SAIMAIL_INTENTIONAL_MEDIA_ASSETS_1",
        "source_receipt": "SRC-102",
        "assets": [{
            "path": "humbox/SAIGIMN.mp3",
            "media_type": "audio/mpeg",
            "size_bytes": SAIGIMN_SIZE,
            "sha256": SAIGIMN_SHA256,
        }],
    }
    assert policy == expected, "intentional media policy must stay exact and source-bound"
    assert SAIGIMN_PATH.is_file()
    assert SAIGIMN_PATH.suffix.lower() == ".mp3"
    assert SAIGIMN_PATH.stat().st_size == SAIGIMN_SIZE
    digest = hashlib.sha256(SAIGIMN_PATH.read_bytes()).hexdigest()
    assert digest == SAIGIMN_SHA256, "the approved media bytes changed"
    return SAIGIMN_PATH


def test_intentional_media_asset_is_exact_and_source_bound():
    assert _validate_intentional_media_asset() == SAIGIMN_PATH


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


def test_review_invocation_boundary_is_recorded():
    # T-62 / SRC-044 corrects D-047 additively without rewriting it: the
    # report is data, the reviewed type-state needs an actual invocation, and
    # evidence-bearing PASS cites at least one corpus ref.
    decisions = read(SPEC / "DECISIONS.md")
    assert re.search(r"^## D-047\b", decisions, flags=re.MULTILINE), "D-047 history moved"
    entry = re.search(r"^## D-048 .*?(?=^## |\Z)", decisions,
                      flags=re.MULTILINE | re.DOTALL)
    assert entry, "D-048 (the invocation-bound review decision) is missing"
    for needle in (
        "SEMANTIC_REVIEW_REPORT = DATA_NOT_INVOCATION_PROOF",
        "REVIEWED_TYPE_MINT_REQUIRES = ACTUAL_REVIEWER_INVOCATION",
        "CALLER_CONSTRUCTED_REPORT_CAN_MINT_REVIEWED_STATE = false",
        "REVIEW_INVOCATIONS_PER_RUN <= 1",
        "OBSERVATION_SUPPORT_PASS_REQUIRES_REVIEW_EVIDENCE_REF = true",
        "COUNTEREVIDENCE_ADEQUACY_PASS_REQUIRES_REVIEW_EVIDENCE_REF = true",
        "REVIEW_EVIDENCE_REF_MEANS = REVIEWER_CITED_SOURCE_NOT_SEMANTIC_PROOF",
    ):
        assert needle in entry.group(0), f"D-048 must record {needle!r}"
    contract = read(SPEC / "09-ALLY-GENERATION-v0.md")
    for needle in (
        "SEMANTIC_REVIEW_REPORT = DATA_NOT_INVOCATION_PROOF",
        "ReviewInvocationResult", "ALLY_GEN_REVIEW_EVIDENCE_REQUIRED",
    ):
        assert needle in contract, f"09-ALLY-GENERATION-v0.md is missing {needle!r}"
    production = read(ROOT / "saimail" / "ally_generation.py")
    assert "_REVIEW_INVOCATION = object()" in production, (
        "the invocation mint sentinel is missing"
    )
    assert "def run_semantic_review(" in production, "the invocation path is missing"


def test_project_corpus_builder_policy_is_recorded():
    # T-67 / SRC-050: D-050 freezes the explicit-only real-project corpus
    # builder above D-049's EVENT_REF. The contract exists, the production
    # module mints its own identities, and completeness stays NOT_PROVEN.
    decisions = read(SPEC / "DECISIONS.md")
    assert re.search(r"^## D-049\b", decisions, flags=re.MULTILINE), "D-049 history moved"
    entry = re.search(r"^## D-050 .*?(?=^## |\Z)", decisions,
                      flags=re.MULTILINE | re.DOTALL)
    assert entry, "D-050 (the real-project corpus builder decision) is missing"
    for needle in (
        "REAL_PROJECT_CORPUS_BUILDER = EXPLICIT_ONLY",
        "IMPLICIT_DISCOVERY = false",
        "PROJECT_SCOPE = EXPLICIT_CALLER_SUPPLIED",
        "SOURCE_DOMAIN = PROJECT_OPERATIONAL",
        "SELECTION_BASIS = EXPLICIT_BOUNDED_SET",
        "GLOBAL_COMPLETENESS_PROVEN = false",
        "SOURCE_REF_IS_EVENT_IDENTITY = false",
        "FILE_PATH_IS_EVENT_IDENTITY = false",
        "TICKET_ID_IS_EVENT_IDENTITY = false",
        "TIMESTAMP_IS_EVENT_IDENTITY = false",
        "EVIDENCE_REF_MINTED_BY = PROJECT_CORPUS_BUILDER",
        "EVENT_REF_MINTED_BY = PROJECT_CORPUS_BUILDER",
        "EVENT_GROUPING_AUTHORITY = EXPLICIT_CALLER_DECLARATION",
        "EVENT_GROUPING_IS_TRUTH = false",
        "EVENT_DECLARATIONS_FORM_EXACT_SELECTED_SET_PARTITION = true",
        "ONE_ARTIFACT_ONE_EVENT_V0 = true",
        "BUILD_ID_BINDS = POLICY + SCOPE + WINDOW + ARTIFACTS + EVENT_GROUPING",
        "CORPUS_ID_REUSES = B016",
        "REAL_PROJECT_PILOT_REQUIRES_BUILDER_PROOF = future_gate",
        "AUTO_EVENT_INFERENCE = false",
        "AUTO_FILE_DISCOVERY = false",
    ):
        assert needle in entry.group(0), f"D-050 must record {needle!r}"
    contract = read(SPEC / "10-PROJECT-CORPUS-v0.md")
    for needle in (
        "NOT_PROVEN", "ProjectEventDeclaration", "ProjectCorpusRequest",
        "BuiltProjectCorpus", "require_built_project_corpus",
        "PROJECT_CORPUS_PROOF_FORGED", "ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS",
    ):
        assert needle in contract, f"10-PROJECT-CORPUS-v0.md is missing {needle!r}"
    production = read(ROOT / "saimail" / "project_corpus.py")
    assert "def build_project_corpus(" in production, "the builder entry point is missing"
    assert "_MINT_TOKEN = object()" in production, "the corpus mint sentinel is missing"
    assert "def require_built_project_corpus(" in production, "the pilot gate is missing"
    backlog = read(SPEC / "BACKLOG.md")
    assert "B-017" in backlog, "B-017 is missing from the backlog"
    readme = read(ROOT / "README.md")
    assert "10-PROJECT-CORPUS-v0.md" in readme, "README does not link the B-017 contract"


def test_fg02_current_state_and_t74_navigation_are_truthful():
    """Keep the compact restart map and immutable T-74 pointers from drifting."""
    import hashlib

    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    latest = read(ROOT / "lab" / "LATEST.md")
    assert (ROOT / "humbox" / "CURRENT-STATE.md").is_file()
    assert "humbox/FUTURE-GATES.md" in current
    assert "T-75" in current and "VERIFIED BUT NOT FORMALLY CLOSED" in current
    assert "T-75" not in re.search(r"## FORMALLY DONE.*?(?=^## )", current,
                                    flags=re.MULTILINE | re.DOTALL).group(0)
    assert "SAIPEN core validation is **NOT VALID**" in current
    assert "SRC-017 / T-41" in current and "SRC-036" in current
    assert "FG-00 DONE" in current
    assert "FG-01 diagnosed / externally blocked" in current
    assert "FG-02 DONE via T-79" in current
    assert "FG-03 DONE via T-78" in current
    assert "T-78/T-80/T-81/T-82/T-83 are DONE" in current
    assert "FG-04B DONE via T-81" in current
    assert "FG-05 DONE via T-82" in current
    assert "FG-06 DONE via T-83" in current
    assert "recorded terminal lifecycles" in current
    for rel in ("spec/13-EXPERIMENT-REPRODUCIBILITY-v0.md",
                "lab/experiment_manifest.py",
                "lab/history/t71_manifest.json",
                "tests/test_experiment_manifest.py"):
        assert (ROOT / rel).is_file(), f"FG-02 artifact missing: {rel}"
    for path in (
        "lab/out/project_corpus_budget4096_live_20260920T005752Z.json",
        "lab/out/PROJECT_CORPUS_BUDGET4096_REPORT_20260920T005752Z.md",
        "lab/analysis/project_corpus_budget4096_20260920T005752Z.md",
        "lab/analysis/project_corpus_budget4096_closure.md",
    ):
        assert path in latest
    pins = {
        "lab/out/project_corpus_budget4096_live_20260920T005752Z.json":
            "0af0735ade363c9e2fc96d84de1a5768263031053c52b15b805bbd4d2bd61474",
        "lab/out/PROJECT_CORPUS_BUDGET4096_REPORT_20260920T005752Z.md":
            "bdbb9158d3073ea7df809c755195d1cf467adeeee0fdaf86c33ddde92a290982",
        "lab/analysis/project_corpus_budget4096_20260920T005752Z.md":
            "bdbb9158d3073ea7df809c755195d1cf467adeeee0fdaf86c33ddde92a290982",
        "lab/analysis/project_corpus_budget4096_closure.md":
            "28c182a1698f1293cf5da72636176480766377f8232e2992a3dbcf1ed1af0ea4",
    }
    for path, expected in pins.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    assert "4096 -> finish_reason=stop" in latest
    assert "NO_ADVICE -> reviewer 0" in latest


def test_fg04a_reference_telemetry_is_recorded():
    """FG-04A closed offline: contract, LAB observer and T-74 limit stay true."""
    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    assert "FG-04A DONE via T-80" in current
    assert "FG-04B DONE via T-81" in current
    assert "T-74 exact bad-ref class remains" in current
    assert "UNKNOWN" in current
    assert "no model/network call occurred in FG-04A" in current
    for rel in ("spec/14-REFERENCE-TELEMETRY-v0.md",
                "lab/reference_telemetry.py",
                "tests/test_reference_telemetry.py",
                "tests/test_reference_telemetry_integration.py",
                "lab/analysis/reference_telemetry_fg04a.md"):
        assert (ROOT / rel).is_file(), f"FG-04A artifact missing: {rel}"
    spec = read(ROOT / "spec" / "14-REFERENCE-TELEMETRY-v0.md")
    assert "T74_EXACT_REF_CLASS = UNKNOWN_FROM_RETAINED_EVIDENCE" in spec
    assert "REFERENCE_TELEMETRY != ACCEPTANCE" in spec
    production = read(ROOT / "lab" / "reference_telemetry.py")
    assert "def observe_candidate_references(" in production
    assert "def observe_raw_references(" in production
    for module in ("saimail/ally_generation.py", "saimail/ally_advice.py",
                   "saimail/project_corpus.py"):
        text = read(ROOT / module)
        assert "reference_telemetry" not in text, (
            f"{module} must not depend on the LAB observer"
        )


def test_fg04b_jsonschema_experiment_is_recorded():
    """FG-04B closed live: one registered experiment, measured outcome, no rollout."""
    import hashlib

    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    latest = read(ROOT / "lab" / "LATEST.md")
    assert "FG-04B DONE via T-81" in current
    assert "CORPUS_ENUM" in current
    assert "REVIEWER_ERROR" in current
    assert "NO_ADVICE" in current
    assert "reviewer's own reply shape" in current
    assert "FG-05 DONE via T-82" in current
    assert "FG-06 DONE via T-83" in current
    for rel in ("lab/project_corpus_jsonschema_registration.json",
                "lab/project_corpus_jsonschema_schema.json",
                "lab/project_corpus_jsonschema_manifest.json",
                "lab/project_corpus_jsonschema.py",
                "tests/test_project_corpus_jsonschema.py",
                "lab/analysis/project_corpus_jsonschema_closure.md"):
        assert (ROOT / rel).is_file(), f"FG-04B artifact missing: {rel}"
    pins = {
        "lab/out/project_corpus_jsonschema_live_20260920T155227Z.json":
            "8ee8d5f77bff8b784304a704d7377e9ac13cb3fe98fac9b31d0d85506cd11334",
        "lab/out/PROJECT_CORPUS_JSONSCHEMA_REPORT_20260920T155227Z.md":
            "785e4fe46b96577567ce3a2319cb1891fc9275963243628576c04ccef830ddc6",
        "lab/analysis/project_corpus_jsonschema_20260920T155227Z.md":
            "785e4fe46b96577567ce3a2319cb1891fc9275963243628576c04ccef830ddc6",
        "lab/project_corpus_jsonschema_registration.json":
            "1e7784bb5efc91531ad23fa91ecafd87dc899a26198b8e5e443590a31fb3f978",
        "lab/project_corpus_jsonschema_schema.json":
            "84304f73399c35f3dc755a1cf19780e4b66ba1a93308c8a81e04d95f8ca285ef",
        "lab/project_corpus_jsonschema_manifest.json":
            "121979de099e09633e5336d30dbde3237afbad62bd1e830b5c953500da5b08fe",
    }
    for path, expected in pins.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected
    for path in ("lab/out/project_corpus_jsonschema_live_20260920T155227Z.json",
                 "lab/out/PROJECT_CORPUS_JSONSCHEMA_REPORT_20260920T155227Z.md",
                 "lab/analysis/project_corpus_jsonschema_20260920T155227Z.md",
                 "lab/analysis/project_corpus_jsonschema_closure.md"):
        assert path in latest
    production = read(ROOT / "lab" / "project_corpus_jsonschema_registration.json")
    assert "CORPUS_ENUM" in production
    assert "SYNTAX_ONLY" in production
    for module in ("saimail/ally_generation.py", "saimail/ally_advice.py"):
        text = read(ROOT / module)
        assert "project_corpus_jsonschema" not in text, (
            f"{module} must not depend on the LAB JSON_SCHEMA harness"
        )


def test_fg05_local_scenario_is_recorded():
    """FG-05 closed offline: contract, LAB scenario and production isolation."""
    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    assert "FG-05 DONE via T-82" in current
    assert "FG-06 DONE via T-83" in current
    for rel in ("spec/15-LOCAL-SCENARIO-v0.md",
                "lab/local_scenario.py",
                "tools/fg05_local_scenario.py",
                "tests/test_local_scenario.py"):
        assert (ROOT / rel).is_file(), f"FG-05 artifact missing: {rel}"
    spec = read(ROOT / "spec" / "15-LOCAL-SCENARIO-v0.md")
    assert "LOCAL_SCENARIO_RESULT_1" in spec
    assert "socket tripwire" in spec
    scenario = read(ROOT / "lab" / "local_scenario.py")
    assert "def run_scenario(" in scenario
    assert "RESULT_SCHEMA = \"LOCAL_SCENARIO_RESULT_1\"" in scenario
    for module in ("saimail/envelope.py", "saimail/postoffice.py",
                   "saimail/legacy.py", "saimail/sailetter.py",
                   "saimail/human_attention.py", "saimail/promotion.py"):
        text = read(ROOT / module)
        assert "local_scenario" not in text, (
            f"{module} must not depend on the FG-05 LAB scenario"
        )


def test_fg06_utility_and_entrypoint_is_recorded():
    """FG-06 closed offline: benchmark, entrypoint, API map and preserved T-9B."""
    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    assert "FG-06 DONE via T-83" in current
    assert "roadmap is complete" in current
    for rel in ("spec/16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md",
                "lab/utility_friction.py",
                "lab/stable_local_api.json",
                "saimail_local.py",
                "tools/fg05_local_scenario.py",
                "tests/test_utility_friction.py",
                "tests/test_local_entrypoint.py",
                "tests/test_clean_install.py"):
        assert (ROOT / rel).is_file(), f"FG-06 artifact missing: {rel}"
    spec = read(ROOT / "spec" / "16-UTILITY-AND-LOCAL-ENTRYPOINT-v0.md")
    assert "FG06_UTILITY_RESULT_1" in spec
    assert "NOT_MEASURED" in spec
    assert "does **not** promise" in spec
    # T-9B's negative finding must survive; FG-06 may not overwrite it.
    analysis = read(ROOT / "bench" / "ANALYSIS.md")
    assert "Every number is above 1.0" in analysis
    assert "cheaper than the frame on every tokenizer" in analysis
    # FG-05 historical result contract is unchanged.
    scenario = read(ROOT / "lab" / "local_scenario.py")
    assert 'RESULT_SCHEMA = "LOCAL_SCENARIO_RESULT_1"' in scenario
    utility = read(ROOT / "lab" / "utility_friction.py")
    assert 'UTILITY_SCHEMA = "FG06_UTILITY_RESULT_1"' in utility
    api_map = read(ROOT / "lab" / "stable_local_api.json")
    assert "SAIMAIL_STABLE_LOCAL_API_1" in api_map
    for package in ("sailang", "saimail"):
        for path in (ROOT / package).glob("*.py"):
            text = read(path)
            assert "import lab" not in text and "from lab" not in text, path
            assert "saimail_local" not in text, path


def test_post_fg06_roadmap_v2_is_recorded_and_v1_stays_intact():
    """T-84/T-88: completed v1 and v2 roadmaps are frozen history, v3 is the
    current authority, CURRENT-STATE points at v3, and one next brick is NOT
    started."""
    import hashlib

    v1 = ROOT / "humbox" / "FUTURE-GATES.md"
    v2 = ROOT / "humbox" / "FUTURE-GATES-V2.md"
    v3 = ROOT / "humbox" / "FUTURE-GATES-V3.md"
    current = read(ROOT / "humbox" / "CURRENT-STATE.md")

    # Completed roadmap v1 stays byte-identifiable as historical evidence.
    assert v1.is_file(), "completed Roadmap v1 is missing"
    assert hashlib.sha256(v1.read_bytes()).hexdigest() == (
        "569bcbd2846b4bc9a34950beaca213207e1821b3cf9543596f6a90691e90e660"
    ), "Roadmap v1 bytes changed; it must stay intact as completed history"
    v1_text = read(v1)
    for gate in ("FG-00", "FG-01", "FG-02", "FG-03", "FG-04", "FG-05", "FG-06"):
        assert gate in v1_text, f"Roadmap v1 no longer carries gate {gate}"

    # A distinct current roadmap v2 exists.
    assert v2.is_file(), "current Roadmap v2 artifact is missing"
    text = read(v2)
    for gate in ("V2-01", "V2-02", "V2-03", "V2-04"):
        assert gate in text, f"Roadmap v2 does not define {gate}"
    for section in (
        "## 1. Current proven baseline",
        "## 2. Current limitations",
        "## 3. Priority principles",
        "## 4. Roadmap table",
        "## 6. Dependencies",
        "## 7. Deferred work",
        "## 8. Next executable brick",
        "## 9. Restart / context-loss entry",
        "## 10. What not to claim",
    ):
        assert section in text, f"Roadmap v2 is missing section {section!r}"
    # Preserved conditional-utility and syntax-cost negatives.
    assert "UTILITY_CONDITIONAL" in text
    assert "more expensive than information-equivalent triage prose" in text

    # The current roadmap is v3; v1 and v2 are completed historical evidence.
    assert v3.is_file(), "current Roadmap v3 artifact is missing"
    v3_text = read(v3)
    for marker in ("V3-01", "SECURITY / CUSTODY LANE", "PRACTICAL PRODUCT LANE",
                   "UTILITY / SELECTOR LANE", "DISTRIBUTION LANE",
                   "OPTIONAL RESEARCH LANE", "Restart / context-loss entry"):
        assert marker in v3_text, f"Roadmap v3 is missing {marker!r}"
    assert "CANDIDATE_REJECTED_SAFETY" in v3_text

    # CURRENT-STATE names the completed authorities and the new current one.
    assert "humbox/FUTURE-GATES-V3.md" in current
    assert "humbox/FUTURE-GATES-V2.md" in current
    assert "humbox/FUTURE-GATES.md" in current
    assert "completed Roadmap v1" in current
    assert "current Roadmap v3" in current
    assert "V3-01" in current

    # Exactly one next brick, consistently named, and explicitly not started.
    assert "V3-01" in v3_text and "V3-01" in current
    assert "not started" in v3_text.lower() or "not started" in current.lower()

    # No completed FG state was reverted.
    for marker in (
        "FG-00 DONE",
        "FG-01 diagnosed / externally blocked",
        "FG-02 DONE via T-79",
        "FG-03 DONE via T-78",
        "FG-04B DONE via T-81",
        "FG-05 DONE via T-82",
        "FG-06 DONE via T-83",
    ):
        assert marker in current, f"CURRENT-STATE reverted a completed FG state: {marker}"


def test_v201_persistent_local_workspace_is_recorded():
    """T-85 / V2-01: the persistent workspace workflow is recorded, its
    contract is versioned, and the FG-05/FG-06 result contracts stay intact."""
    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    assert "V2-01 DONE via T-85" in current
    assert "V2-02" in current and "V2-03" in current and "V2-04" in current
    for rel in ("spec/17-LOCAL-WORKSPACE-v0.md",
                "saimail/workspace.py",
                "tests/test_local_workspace.py",
                "tests/test_local_workspace_acceptance.py"):
        assert (ROOT / rel).is_file(), f"V2-01 artifact missing: {rel}"
    spec = read(ROOT / "spec" / "17-LOCAL-WORKSPACE-v0.md")
    for marker in ("SAIMAIL_LOCAL_WORKSPACE_1", "LOCAL_WORKSPACE_COMMAND_1",
                   "LOCAL_WORKSPACE_RESULT_1", "SAIMAIL_IDENTITY_CARD_1",
                   "no encryption at rest"):
        assert marker in spec, f"V2-01 contract does not state {marker!r}"
    engine = read(ROOT / "saimail" / "workspace.py")
    assert 'WORKSPACE_SCHEMA = "SAIMAIL_LOCAL_WORKSPACE_1"' in engine
    entrypoint = read(ROOT / "saimail_local.py")
    for subcommand in ("init", "identity", "recipient", "send", "inbox", "open",
                       "acceptance"):
        assert subcommand in entrypoint, f"entrypoint lost subcommand {subcommand}"
    # FG-05 / FG-06 result contracts are not rewritten by V2-01.
    scenario = read(ROOT / "lab" / "local_scenario.py")
    assert 'RESULT_SCHEMA = "LOCAL_SCENARIO_RESULT_1"' in scenario
    utility = read(ROOT / "lab" / "utility_friction.py")
    assert 'UTILITY_SCHEMA = "FG06_UTILITY_RESULT_1"' in utility
    # The README carries one practical local workflow and links its contract.
    readme = read(ROOT / "README.md")
    assert "spec/17-LOCAL-WORKSPACE-v0.md" in readme
    assert "saimail-local acceptance" in readme


def test_v202_selector_coverage_experiment_is_recorded():
    """T-88 / V2-02: the selector-coverage experiment closed as a measured
    negative, its preregistration and manifest are frozen, and no production
    module depends on the LAB harness."""
    import hashlib

    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    latest = read(ROOT / "lab" / "LATEST.md")
    assert "V2-02 DONE via T-88" in current
    assert "CANDIDATE_REJECTED_SAFETY" in current
    assert "TOPIC_DRIFT" in current
    assert "246 -> 68" in current
    assert "V3-01" in current

    for rel in ("spec/19-SELECTOR-COVERAGE-EXPERIMENT-v0.md",
                "lab/selector_coverage.py",
                "lab/selector_coverage_fixtures.json",
                "lab/selector_coverage_registration.json",
                "lab/selector_coverage_manifest.json",
                "lab/history/v202-selector-coverage/selector_coverage_fixtures.json",
                "lab/history/v202-selector-coverage/selector_coverage_registration.json",
                "tests/test_selector_coverage.py",
                "lab/analysis/v202_selector_coverage_20260920T184536Z.md",
                "lab/analysis/v202_selector_coverage_closure.md"):
        assert (ROOT / rel).is_file(), f"V2-02 artifact missing: {rel}"

    pins = {
        "lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/result.json":
            "65e71e259f06160065af4ad801f9f1476d6e7fe2c42293be9564b08c875afdf1",
        "lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/report.md":
            "d5d2e23dbca6e758c2df3ee16f47b1bc145201005976aadf8337f41c390b2fd1",
        "lab/selector_coverage_fixtures.json":
            "a8fa4095ea4bbd1361a40c4c0d6be8968584e562a3cde3f47183a3cfccf9631e",
        "lab/selector_coverage_registration.json":
            "9be09310122a3638155745b3955f769a8aad20a618a8c795a37eb78b1f6324fa",
    }
    for path, expected in pins.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    for path in ("lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/result.json",
                 "lab/out/V202_SELECTOR_COVERAGE_20260920T184536Z/report.md",
                 "lab/analysis/v202_selector_coverage_20260920T184536Z.md",
                 "lab/analysis/v202_selector_coverage_closure.md"):
        assert path in latest, f"{path} is not indexed in lab/LATEST.md"

    manifest = read(ROOT / "lab" / "selector_coverage_manifest.json")
    assert '"authority": "HISTORICAL_ONLY"' in manifest
    registration = read(ROOT / "lab" / "selector_coverage_registration.json")
    assert '"treatment_variable": "ignore_topics"' in registration
    assert '"changed_value_added": "ci-ok"' in registration
    assert '"production_promotion": "NONE"' in registration

    for module in (ROOT / "saimail").glob("*.py"):
        assert "selector_coverage" not in read(module), (
            f"{module.name} must not depend on the V2-02 LAB harness")


def test_v203_reviewer_structured_output_experiment_is_recorded():
    """T-96 / V2-03: the reviewer structured-output experiment is recorded with
    its single variable, terminal outcome and frozen artifacts, and no production
    module depends on the LAB harness."""
    import hashlib

    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    latest = read(ROOT / "lab" / "LATEST.md")
    assert "V2-03" in current
    assert "REVIEWER_BAD_JSON" in current
    assert "response_format" in current and "reviewer" in current

    for rel in ("lab/reviewer_structured_output_registration.json",
                "lab/reviewer_structured_output_schema.json",
                "lab/reviewer_structured_output_manifest.json",
                "lab/reviewer_structured_output.py",
                "tests/test_reviewer_structured_output.py",
                "lab/analysis/reviewer_structured_output_closure.md"):
        assert (ROOT / rel).is_file(), f"V2-03 artifact missing: {rel}"

    pins = {
        "lab/out/reviewer_structured_output_live_20260920T221857Z.json":
            "9997a9a23e59de250e81aee37d66924d9a1a8b42af3b6f6b3f449d091e268633",
        "lab/out/REVIEWER_STRUCTURED_OUTPUT_REPORT_20260920T221857Z.md":
            "3f47e24d4a56ea3490121af2c5c815e32e9a13e882e086850f47f18b7b8fafda",
        "lab/reviewer_structured_output_schema.json":
            "8db0e5b00c8d817ce9130814ee5a952c6d1ead344539e7ce6aa4acdba6396bb9",
    }
    registration = read(ROOT / "lab" / "reviewer_structured_output_registration.json")
    assert '"reviewer response_format ABSENT -> JSON_SCHEMA"' in registration
    assert '"REVIEWER_VERDICT_PARSED"' in registration
    assert '"RESPONSE_FORMAT_REJECTED"' in registration
    assert '"no_response_format_fallback":true' in registration

    manifest = read(ROOT / "lab" / "reviewer_structured_output_manifest.json")
    assert '"authority": "LIVE_ELIGIBLE"' in manifest
    assert '"experiment_id": "V2-03-REVIEWER-STRUCTURED-OUTPUT-1"' in manifest

    for path in ("lab/out/reviewer_structured_output_live_20260920T221857Z.json",
                 "lab/out/REVIEWER_STRUCTURED_OUTPUT_REPORT_20260920T221857Z.md",
                 "lab/analysis/reviewer_structured_output_20260920T221857Z.md",
                 "lab/analysis/reviewer_structured_output_closure.md"):
        assert path in latest, f"{path} is not indexed in lab/LATEST.md"
    for path, expected in pins.items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path

    # The FG-04B comparator stays byte-identical: the treatment is one variable.
    assert hashlib.sha256(
        (ROOT / "lab/project_corpus_jsonschema_schema.json").read_bytes()
    ).hexdigest() == "84304f73399c35f3dc755a1cf19780e4b66ba1a93308c8a81e04d95f8ca285ef"

    for module in (ROOT / "saimail").glob("*.py"):
        assert "reviewer_structured_output" not in read(module), (
            f"{module.name} must not depend on the V2-03 LAB harness")


def test_readme_mirrors_match_the_canonical_version_authority():
    """D1 / T-90: the locale README mirrors are release metadata, not a second
    version authority. Expected version is derived from VERSION so this cannot
    silently drift again."""
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    canonical = read(ROOT / "README.md")
    assert f"**v{version}" in canonical, (
        f"README.md does not carry the canonical version {version!r}")
    for name in ("README.ee.md", "README.ded.md", "README.ja.md"):
        text = read(ROOT / name)
        match = re.search(r"^\*\*v([^*]+)\*\*$", text, flags=re.MULTILINE)
        assert match, f"{name} carries no version mirror line"
        assert match.group(1) == version, (
            f"{name} version {match.group(1)!r} != canonical VERSION {version!r}")
        assert "README.md" in text, f"{name} no longer points at the canonical README"


def test_v501_desktop_local_messenger_is_recorded():
    """T-97 / V5-01: the GUI product gate is recorded, its artifacts exist, the
    roadmap authority is v5, and the Qt dependency stays optional."""
    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V5.md")
    assert "V5-01 DONE via T-97" in current
    assert "humbox/FUTURE-GATES-V5.md" in current
    assert "V5-01" in roadmap
    for marker in ("LOCAL ONLY", "explicit Open", "no background mutation"):
        assert marker in roadmap or marker in current, f"V5-01 lost {marker!r}"
    for rel in ("saimail/gui_adapter.py", "saimail/gui_app.py",
                "saimail/gui_theme.py", "tests/test_gui_surface.py",
                "tests/test_gui_acceptance.py",
                "spec/25-DESKTOP-LOCAL-MESSENGER-v0.md"):
        assert (ROOT / rel).is_file(), f"V5-01 artifact missing: {rel}"
    # The canonical UI.md fingerprint is recorded in the theme module so a
    # compliance drift check exists without packaging the spec.
    engine = read(ROOT / "saimail" / "gui_theme.py")
    assert "162fa0574533456541b65fb79f1893fef863e9143aaab94ba99e0ea938ea5dd0" in engine
    assert "TOKENS" in engine and '"surfaceAlt": "#453D30"' in engine
    # Qt is optional-only: never in base dependencies, never in another extra.
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["dependencies"] == [], "base must stay dependency-free"
    assert data["project"]["scripts"]["saimail-gui"] == "saimail.gui_app:main"
    gui = data["project"]["optional-dependencies"]["gui"]
    assert any(dep.startswith("PySide6") for dep in gui)
    for name, deps in data["project"]["optional-dependencies"].items():
        if name == "gui":
            continue
        assert not any("PySide6" in dep for dep in deps), (
            f"extra {name!r} must not pull Qt")
    # Every non-GUI saimail module stays Qt-free.
    import ast as _ast

    for path in (ROOT / "saimail").glob("*.py"):
        if path.name == "gui_app.py":
            continue
        tree = _ast.parse(path.read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("PySide6"), path
            elif isinstance(node, _ast.ImportFrom):
                assert not (node.module or "").startswith("PySide6"), path
    # The GUI module itself carries no network or background machinery.
    gui_source = read(ROOT / "saimail" / "gui_app.py")
    for banned in ("QNetwork", "socket", "threading", "QTimer",
                   "requests", "urllib"):
        assert banned not in gui_source, f"gui_app must not carry {banned!r}"
    # D-066 permits only user-requested KDF workers. The Qt surface test
    # exercises their explicit launch, competing-action guard and shutdown.
    assert "def _run_key_job" in gui_source and "self._key_job = None" in gui_source


def test_v601_github_identity_and_presentation_sync_is_recorded():
    """T-104 / V6-01: canonical logo, social preview, SECURITY.md, v6 roadmap
    authority, prepared GitHub metadata, and an honest frozen-vs-checkout
    README first screen."""
    import hashlib

    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V6.md")
    settings = read(ROOT / "humbox" / "GITHUB-SETTINGS-V6.md")
    security = " ".join(read(ROOT / "SECURITY.md").split())
    readme = read(ROOT / "README.md")

    for rel in ("pics/SAIMAIL_LOGO.png", "pics/SAIMAIL2.png",
                "pics/SAIMAIL_SOCIAL_PREVIEW.png", "SECURITY.md",
                "humbox/FUTURE-GATES-V6.md", "humbox/GITHUB-SETTINGS-V6.md",
                "tools/build_social_preview.py"):
        assert (ROOT / rel).is_file(), f"V6-01 artifact missing: {rel}"

    logo = hashlib.sha256((ROOT / "pics" / "SAIMAIL_LOGO.png").read_bytes()).hexdigest()
    source = hashlib.sha256((ROOT / "pics" / "SAIMAIL2.png").read_bytes()).hexdigest()
    assert logo == source, "canonical logo must be byte-identical to SAIMAIL2"

    from PIL import Image

    with Image.open(ROOT / "pics" / "SAIMAIL_SOCIAL_PREVIEW.png") as im:
        assert im.format == "PNG"
        assert im.size == (1280, 640), im.size
    assert (ROOT / "pics" / "SAIMAIL_SOCIAL_PREVIEW.png").stat().st_size < 1_000_000

    assert "V6-01" in roadmap
    assert "humbox/FUTURE-GATES-V6.md" in current
    assert "MANUAL_GITHUB_SETTINGS_REQUIRED" in settings
    assert "CURRENT SOURCE IS MATERIALLY AHEAD OF FROZEN 0.0.2a2." in settings
    assert "Local-first agent post office and desktop messenger" in settings
    for topic in ("python", "local-first", "messaging", "agents",
                  "cryptography", "provenance", "pyside6", "offline-first"):
        assert topic in settings, f"prepared topics lost {topic!r}"

    # README first screen: practical entry before deep status, honest split.
    head = " ".join(readme.split("## Status", 1)[0].split())
    assert "LOCAL ONLY" in head
    assert 'pip install "saimail[gui,crypto]"' in head
    assert "saimail-gui" in head
    assert "saimail-local" in head
    assert "FROZEN VERIFIED ARTIFACT" in head
    assert "0.0.2a2" in head
    assert "CURRENT CHECKOUT" in head
    assert "P1 + V4-01 + V5-01" in head
    assert "not** inside that frozen wheel" in head
    assert "pics/SAIMAIL_LOGO.png" in head
    assert "SECURITY.md" in head

    # SECURITY.md is concrete, not corporate boilerplate.
    for needle in ("GitHub Security Advisories", "Never publish",
                   "local-only", "may differ", "Private keys"):
        assert needle in security, f"SECURITY.md lost {needle!r}"


def test_s2_saipen_seam_bridge_is_recorded():
    """T-108 / S2: the SAIPEN seam bridge exists as code, and humbox, spec/04,
    D-057 and the README first screen tell the same checkout-only truth."""
    current = read(ROOT / "humbox" / "CURRENT-STATE.md")
    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V6.md")
    seam = read(ROOT / "spec" / "04-SAIPEN-SEAM.md")
    decision = read(ROOT / "spec" / "DECISIONS-D057.md")
    readme = read(ROOT / "README.md")

    for rel in ("saimail/saipen_bridge.py", "tests/test_saipen_bridge.py",
                "spec/DECISIONS-D057.md"):
        assert (ROOT / rel).is_file(), f"S2 artifact missing: {rel}"
    assert "D-057" in decision_ids()

    assert "S2 DONE via T-108" in current
    assert "S2 DONE via T-108" in roadmap
    assert "## 11. S2 — SAIPEN seam bridge (T-108)" in roadmap
    assert "### S2 as built" in seam
    # The beacon must not claim a3 alignment the bridge broke.
    flat = " ".join(current.split())
    assert "the checkout is aligned with the exact a3 candidate by D3" not in flat
    assert "S2 (T-108) has since moved the checkout ahead of frozen a3" in flat
    head = " ".join(readme.split("## Status", 1)[0].split())
    assert "SAIPEN seam bridge" in head and "not** inside the frozen `0.0.2a3` wheel" in head

    # The boundary the decision records is the boundary the code keeps.
    bridge = read(ROOT / "saimail" / "saipen_bridge.py")
    assert ".saipen" not in bridge, "the library must never name SAIPEN memory"
    entrypoint = read(ROOT / "saimail_local.py")
    assert '_SAIPEN_MEMORY = ".saipen"' in entrypoint
    for needle in ("SAIPEN_AGENT", "caller-supplied", "re-derivation", "0.0.2a3"):
        assert needle in decision, f"D-057 lost {needle!r}"


def test_saitelemes_v0_is_recorded():
    """T-109 / SAITELEMES v0: humbox, spec/26, D-058 and the README agree, and
    the wire stays closed (no TELEGRAM kind)."""
    from saimail import envelope

    current = " ".join(read(ROOT / "humbox" / "CURRENT-STATE.md").split())
    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V6.md")
    spec = " ".join(read(ROOT / "spec" / "26-SAITELEMES-v0.md").split())
    decision = " ".join(read(ROOT / "spec" / "DECISIONS-D058.md").split())
    readme = read(ROOT / "README.md")

    for rel in ("tests/test_saitelemes.py", "spec/26-SAITELEMES-v0.md",
                "spec/DECISIONS-D058.md"):
        assert (ROOT / rel).is_file(), f"SAITELEMES artifact missing: {rel}"
    assert "D-058" in decision_ids()
    assert "SAITELEMES v0 DONE via T-109" in current
    assert "## 12. SAITELEMES v0" in roadmap and "DONE via T-109" in roadmap
    assert "There is **no `TELEGRAM` kind**" in spec
    assert "SAIPEN_SEAT_MISMATCH" in spec and "SAIPEN_SEAT_MISMATCH" in decision
    assert "FUTURE GATE — SAITELEMES AUTOMATIC AGENT TELEGRAMS_20260922.md" in decision
    assert "spec/26-SAITELEMES-v0.md" in readme
    head = " ".join(readme.split("## Status", 1)[0].split())
    assert "SAITELEMES" in head and "not** inside the frozen `0.0.2a3` wheel" in head
    assert "TELEGRAM" not in envelope.KINDS, "SAITELEMES must not grow the closed wire set"


def test_v603_turn_entry_evaluation_is_recorded_and_header_reads_hold_no_secret():
    """T-117 / V6-03: humbox, spec/26 section 7, D-059 and the CLI agree that the
    SAIPEN turn-entry read and every header-only command load the secret-free view."""
    current = " ".join(read(ROOT / "humbox" / "CURRENT-STATE.md").split())
    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V6.md")
    spec = " ".join(read(ROOT / "spec" / "26-SAITELEMES-v0.md").split())
    decision = " ".join(read(ROOT / "spec" / "DECISIONS-D059.md").split())
    desk = " ".join(read(ROOT / "humbox" / "SAIPEN-WORK-DESK.md").split())

    assert "D-059" in decision_ids()
    assert "V6-03" in current and "T-1497" in current and "SAIMAIL_WORKSPACE" in desk
    rows = [[cell.strip() for cell in line.strip("|").split("|")]
            for line in roadmap.splitlines() if line.startswith("| V6-03 |")]
    assert len(rows) == 1 and rows[0][2] == "T-117" and "IMPLEMENTED" in rows[0][1]
    assert "## 15. V6-03" in roadmap
    assert "## 7. The SAIPEN turn-entry consumer" in spec
    for text in (spec, decision):
        assert "load_workspace_headers" in text and "status" in text
        assert "credential store" in text

    # The header-only commands load the view; the key-using ones keep the full load.
    entry = read(ROOT / "saimail_local.py")
    saipen = entry.split("def _cmd_saipen", 1)[1].split("\ndef ", 1)[0]
    for action in ("telegrams", "enter", "brief"):
        branch = saipen.split(f'args.saipen_action == "{action}"', 1)[1].split("return", 1)[0]
        assert "load_workspace_headers(" in branch, action
    telegram = saipen.split('args.saipen_action == "telegram"', 1)[1].split("return", 1)[0]
    assert "load_workspace(" in telegram and "load_workspace_headers(" not in telegram
    inbox = entry.split("def _cmd_inbox", 1)[1].split("\ndef ", 1)[0]
    assert "load_workspace_headers(" in inbox
    for command in ("_cmd_open", "_cmd_reopen", "_cmd_reply"):
        body = entry.split(f"def {command}", 1)[1].split("\ndef ", 1)[0]
        assert "load_workspace(" in body and "load_workspace_headers(" not in body, command

    api = json.loads(read(ROOT / "lab/stable_local_api.json"))
    exported = {(item["module"], item["symbol"]) for item in api["apis"]}
    assert ("saimail.workspace", "load_workspace_headers") in exported
    assert ("saimail.workspace", "WorkspaceHeaders") in exported


def test_v605_durable_outbox_is_recorded():
    """T-119 / V6-05: the wave table, spec/28, D-060, the API map and the module
    agree; the outbox never names SAIPEN memory and adds no wire field."""
    from saimail import envelope, outbox

    current = " ".join(read(ROOT / "humbox" / "CURRENT-STATE.md").split())
    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V6.md")
    spec = " ".join(read(ROOT / "spec" / "28-DURABLE-OUTBOX-v0.md").split())
    decision = " ".join(read(ROOT / "spec" / "DECISIONS-D060.md").split())

    assert "D-060" in decision_ids()
    assert "## 16. SAITELEMES reliable autonomous delivery v1" in roadmap
    rows = [[cell.strip() for cell in line.strip("|").split("|")]
            for line in roadmap.splitlines() if line.startswith("| V6-05 |")]
    assert len(rows) == 1 and rows[0][3] == "T-119" and "IMPLEMENTED" in rows[0][2]
    assert "V6-05" in current and "spec/28-DURABLE-OUTBOX-v0.md" in current
    for text in (spec, decision):
        assert "idempotency key" in text and "seal" in text.lower()
        assert "wire" in text, "the idempotency key must stay off the wire"
    source = read(ROOT / "saimail" / "outbox.py")
    assert ".saipen" not in source, "the library must never name SAIPEN memory"
    assert "IDEMPOTENCY" not in " ".join(envelope.KINDS)
    api = json.loads(read(ROOT / "lab/stable_local_api.json"))
    exported = {(item["module"], item["symbol"]) for item in api["apis"]}
    for symbol in ("submit_send", "resume_outbox", "retry_intent", "outbox_status"):
        assert ("saimail.outbox", symbol) in exported
        assert callable(getattr(outbox, symbol))


def test_v606_participant_registry_is_recorded():
    """T-120 / V6-06: roadmap row, spec/29, D-061, API map and module agree; the
    registry never names SAIPEN memory and its triggers use existing kinds."""
    from saimail import envelope, participants

    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V6.md")
    current = " ".join(read(ROOT / "humbox" / "CURRENT-STATE.md").split())
    assert "D-061" in decision_ids()
    rows = [[cell.strip() for cell in line.strip("|").split("|")]
            for line in roadmap.splitlines() if line.startswith("| V6-06 |")]
    assert len(rows) == 1 and rows[0][3] == "T-120" and "IMPLEMENTED" in rows[0][2]
    assert "spec/29-PARTICIPANT-REGISTRY-v0.md" in current
    assert ".saipen" not in read(ROOT / "saimail" / "participants.py")
    assert set(participants.TRIGGERS.values()) <= envelope.KINDS
    api = json.loads(read(ROOT / "lab/stable_local_api.json"))
    exported = {(item["module"], item["symbol"]) for item in api["apis"]}
    for symbol in ("admit_participant", "resolve_participant", "list_participants",
                   "revoke_participant"):
        assert ("saimail.participants", symbol) in exported


def test_v607_capability_document_is_recorded():
    """T-121 / V6-07 SAIMAIL half: roadmap row, spec/30, D-062, API map and module agree."""
    from saimail import capabilities

    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V6.md")
    assert "D-062" in decision_ids()
    rows = [[cell.strip() for cell in line.strip("|").split("|")]
            for line in roadmap.splitlines() if line.startswith("| V6-07 |")]
    assert len(rows) == 1 and "T-121" in rows[0][3] and "SAIMAIL half IMPLEMENTED" in rows[0][2]
    spec = " ".join(read(ROOT / "spec" / "30-SAIPEN-CAPABILITIES-v0.md").split())
    for reason in sorted(capabilities.REASONS):
        assert reason in spec, f"spec/30 lost reason {reason}"
    assert ".saipen" not in read(ROOT / "saimail" / "capabilities.py")
    api = json.loads(read(ROOT / "lab/stable_local_api.json"))
    assert ("saimail.capabilities", "capabilities") in {
        (item["module"], item["symbol"]) for item in api["apis"]}


def test_v608_notify_is_recorded_and_carries_no_sender_priority():
    """T-122 / V6-08 SAIMAIL half: roadmap row, spec/31, D-063 and module agree."""
    import inspect

    from saimail import notify, participants

    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V6.md")
    assert "D-063" in decision_ids()
    rows = [[cell.strip() for cell in line.strip("|").split("|")]
            for line in roadmap.splitlines() if line.startswith("| V6-08 |")]
    assert len(rows) == 1 and "T-122" in rows[0][3] and "SAIMAIL half IMPLEMENTED" in rows[0][2]
    spec = " ".join(read(ROOT / "spec" / "31-SAITELEMES-NOTIFY-v0.md").split())
    for trigger in participants.TRIGGERS:
        assert f"`{trigger}`" in spec
    assert not set(inspect.signature(notify.notify).parameters) & {
        "kind", "priority", "urgency", "importance"}
    assert ".saipen" not in read(ROOT / "saimail" / "notify.py")


def test_t123_mesh_torture_is_recorded_and_the_lock_waits():
    """T-123 / D-065: the torture matrix is on the roadmap, the decision exists,
    spec/03 records the contended-init wait, and the fix is in the source."""
    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V6.md")
    assert "D-065" in decision_ids()
    rows = [[cell.strip() for cell in line.strip("|").split("|")]
            for line in roadmap.splitlines() if line.startswith("| torture |")]
    assert len(rows) == 1 and "T-123" in rows[0][3], "the §16 torture row is missing"
    post_office = read(SPEC / "03-POST-OFFICE.md")
    assert "D-065" in post_office, "spec/03 lost the contended-init wait"
    source = read(ROOT / "saimail" / "postoffice.py")
    enter = re.search(r"def __enter__.*?(?=\n    def __exit__)", source, re.DOTALL)
    assert enter and "PermissionError" in enter.group(0), (
        "_OsFileLock.__enter__ no longer tolerates the contended initializing write")


def workshop_policy_rows() -> list:
    """The enforcement map of spec/32: (id, control, status) per rule row."""
    rows = []
    for line in read(ROOT / "spec" / "32-INTER-AGENT-WORKSHOP-POLICY-v0.md").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and re.fullmatch(r"[A-Z][0-9]", cells[0]):
            rows.append((cells[0], cells[3], cells[4]))
    return rows


def test_workshop_policy_is_mapped_to_live_controls():
    """T-118 / D-064: every operator workshop rule names a control that exists, or
    a SAIPEN-side wave gate on the roadmap; no state set can say ACTED."""
    from saimail import capabilities, outbox, postoffice

    rows = workshop_policy_rows()
    assert len(rows) == 25 and len({row[0] for row in rows}) == 25
    roadmap = read(ROOT / "humbox" / "FUTURE-GATES-V6.md")
    for rule, control, status in rows:
        if status == "ENFORCED":
            path, _, name = control.partition("::")
            source = read(ROOT / path)
            assert re.search(rf"^def {re.escape(name)}\(", source, re.MULTILINE), (
                f"{rule}: control {control} no longer exists")
        else:
            assert status == "SAIPEN-SIDE", rule
            gate = control.split()[0]
            assert any(line.startswith(f"| {gate} |") and "WAITING" in line
                       for line in roadmap.splitlines()), f"{rule}: {gate} is not a waiting gate"
    states = set(outbox.STATES) | {
        postoffice.UNREAD, postoffice.READ_STATE, postoffice.EXPIRED_STATE, postoffice.BOTH,
        postoffice.NEITHER, postoffice.ACCEPTED, postoffice.DUPLICATE, postoffice.QUARANTINED,
        postoffice.REFUSED} | {
        capabilities.AVAILABLE, capabilities.DEGRADED, capabilities.REQUIRES_HUMAN,
        capabilities.UNAVAILABLE, capabilities.UNVERIFIED}
    assert not any("ACTED" in state for state in states)


def test_gui_read_capability_language_matches_explicit_reopen():
    """Qt-independent oracle: first-Open refusal must point to real Reopen."""
    from saimail import gui_adapter, workspace

    assert callable(workspace.reopen_message)
    assert callable(gui_adapter.GuiAdapter.reopen_selected)
    assert not hasattr(gui_adapter, "READ_REREAD_GAP"), "T-113 resolved this gap"
    for reason in (gui_adapter.REASON_OPEN_ALREADY_READ,
                   gui_adapter.REASON_READ_NOT_THIS_SESSION):
        assert "READ" in reason and "Reopen" in reason, (
            "READ guidance must point to the explicit Reopen action")
    # Check only READ capability prose; non-READ refusal text remains valid.
    capability = " ".join((gui_adapter.__doc__,
                           gui_adapter.REASON_OPEN_ALREADY_READ,
                           gui_adapter.REASON_READ_NOT_THIS_SESSION))
    capability = " ".join(capability.split()).lower()
    assert not re.search(
        r"not re-readable|cannot be (?:re-?opened|shown again)|"
        r"(?:only|one|sole) decryption path|backend.capability gap", capability)


RECOVERY_DOCS = ("humbox/CURRENT-STATE.md", "humbox/FUTURE-GATES-V6.md",
                 "humbox/SAIPEN-WORK-DESK.md",
                 ".saipen/kitchen/T-113-reread-continuation.md")

# Ephemeral lifecycle ownership (active Work, its phase, pending acceptance)
# belongs to .saipen/STATE.md, BOARD and LOG. Durable recovery prose that pins
# it to a concrete ticket turns false the moment that ticket closes (T-116).
STALE_OWNERSHIP = re.compile(
    r"\bT-\d+ (?:still )?owns\b|"
    r"\bowns? (?:the )?(?:subsequent|that|next) continuation|"
    r"\bT-\d+ (?:is|remains) (?:still )?(?:the )?(?:active|current)\b|"
    r"\b(?:the )?current (?:capability[- ]truth |capability/recovery truth |truth )?repair\b|"
    r"\b(?:inside|in|outside|part of) this repair\b|"
    r"\bafter\b[^.;]{0,80}?\bis accepted\b",
    re.IGNORECASE)


def stale_ownership_claims(text: str) -> list:
    """Unqualified ticket-bound ownership claims; blocks marked historical are evidence."""
    claims = []
    for paragraph in text.split("\n\n"):
        for block in re.split(r"\n(?=\s*[-*] |\s*\d+\. )", paragraph):
            flat = " ".join(block.replace("*", "").replace("`", "").split())
            if "(historical)" in flat or flat.startswith(("Historical", "> Historical")):
                continue
            claims += [flat[max(0, m.start() - 40):m.end() + 40]
                       for m in STALE_OWNERSHIP.finditer(flat)]
    return claims


def test_recovery_docs_bind_no_ticket_as_active_owner():
    """T-116: completed Work is recorded, never used as a pointer to who owns next."""
    for rel in RECOVERY_DOCS:
        assert stale_ownership_claims(read(ROOT / rel)) == [], rel
    for rel in RECOVERY_DOCS[:3]:
        flat = " ".join(read(ROOT / rel).replace("*", "").replace("`", "").split())
        assert re.search(r"STATE(?:\.md)?,? BOARD and LOG|STATE/BOARD/LOG", flat), (
            f"{rel} must defer active Work to machine lifecycle state")
        assert "T-114 DONE (E-1541)" in flat
        assert re.search(r"T-114 did not implement (?:it|that hook)|"
                         r"not implemented by T-114", flat), rel


@pytest.mark.parametrize("injected", [
    "T-114 owns subsequent continuation.",
    "T-114 is still the current repair owner after E-1541.",
    "After this capability/recovery truth repair is accepted, evaluate the hook.",
    "After truth reconciliation is accepted, evaluate the separate turn-entry hook.",
    "T-117 owns that continuation; STATE owns its current phase.",
])
def test_stale_ownership_guard_detects_the_defect_class(injected):
    """Red controls in memory: the guard catches the class, not one ticket number."""
    current = read(ROOT / "humbox/CURRENT-STATE.md")
    marker = "## NEXT EXECUTABLE STEP\n"
    assert marker in current.replace("\r\n", "\n")
    tampered = current.replace("\r\n", "\n").replace(
        marker, marker + "\n" + injected + "\n", 1)
    assert stale_ownership_claims(tampered)
    # The same sentence explicitly scoped as history is allowed evidence.
    assert not stale_ownership_claims("Historical T-114 checkpoint: " + injected)


def test_current_recovery_recognizes_t113_closure_and_frozen_boundary():
    """T-114: current capability truth must not send cold recovery back to T-113."""
    current = read(ROOT / "humbox/CURRENT-STATE.md")
    roadmap = read(ROOT / "humbox/FUTURE-GATES-V6.md")
    desk = read(ROOT / "humbox/SAIPEN-WORK-DESK.md")

    # Parse the lane's status fields, not an exact prose paragraph snapshot.
    rows = [[cell.strip() for cell in line.strip("|").split("|")]
            for line in roadmap.splitlines() if line.startswith("| V6-02 |")]
    assert len(rows) == 1 and rows[0][:3] == ["V6-02", "DONE", "T-113"]
    assert "E-1527" in rows[0][3]
    for text in (current, roadmap, desk):
        flat = " ".join(text.replace("*", "").replace("`", "").split())
        assert re.search(r"T-113 DONE|DONE via T-113", flat)
        assert "Reopen" in flat
        assert "metadata-only" in flat or "metadata only" in flat
    for text in (current, roadmap):
        flat = " ".join(text.replace("*", "").replace("`", "").split())
        assert "Frozen 0.0.2a3 does not contain T-113" in flat
        assert "checkout-only" in flat
        for unchanged in (r"G13 (?:is )?PENDING_EXTERNAL", r"G17 (?:is )?ABSENT",
                          r"publication (?:is )?NONE"):
            assert re.search(unchanged, flat), unchanged

    # Explicit historical sections/paragraphs remain valid evidence. Check the
    # rest, including current position and restart, for the original drift.
    current_now = re.sub(r"## V5-01 DESKTOP.*?(?=\n## S2 )", "", current,
                         flags=re.DOTALL)
    for text in (current_now, roadmap, desk):
        for paragraph in text.split("\n\n"):
            if any(scope in paragraph for scope in (
                    "Historical T-107 boundary:", "NOT STARTED at T-107 closure",
                    "Next evaluation at T-110 closure (historical)")):
                continue
            flat = " ".join(paragraph.replace("*", "").replace("`", "").split())
            assert not re.search(
                r"READ_REREAD_GAP.{0,40}(?:remains|is) (?:open|real)|"
                r"V6-02.{0,25}NOT STARTED|"
                r"saved T-113.{0,50}(?:next|first)|Receiver continuity comes next",
                flat), flat

    api = json.loads(read(ROOT / "lab/stable_local_api.json"))
    exported = {(item["module"], item["symbol"]) for item in api["apis"]}
    assert ("saimail.workspace", "open_message") in exported
    assert ("saimail.workspace", "reopen_message") in exported


# --------------------------------------------------------------------
# beacon registration (T-155)
# --------------------------------------------------------------------

HUMBOX = ROOT / "humbox"

#: humbox/ predates the intake machinery and these twenty-four files were never
#: captured -- no receipt carries their text. They are NAMED here rather than
#: skipped: a silent skip lets the next arrival hide behind the old ones, which
#: is how both humbox/milestoned1.md (closed in T-151) and
#: humbox/YAZADAYU_born1.md (T-155) went unnoticed. EVOLUTION.md,
#: EVOLUTION-AUDIT.md and FUTURE-GATES-V5.md joined this set in T-158: they were
#: registered only by incidental BOARD and LOG mentions, which the hygiene
#: passes below remove. The remaining ten joined it in T-160, which deleted the
#: prose corpus as a source of registration altogether -- a mention is not a
#: capture, and ten of them were passing on nothing but the fact that some
#: unrelated journal line happened to spell their names. A file that leaves this
#: set must earn a receipt whose digest matches its bytes.
LEGACY_UNREGISTERED_BEACON = frozenset({
    "CURRENT-STATE.md",
    "EVOLUTION-AUDIT.md",
    "EVOLUTION.md",
    "FUTURE-GATES-V2.md",
    "FUTURE-GATES-V3.md",
    "FUTURE-GATES-V4.md",
    "FUTURE-GATES-V5.md",
    "FUTURE-GATES-V6.md",
    "FUTURE-GATES.md",
    "GITHUB-SETTINGS-V6.md",
    "INSTITUTION.md",
    "SAIOPP_instructions.md",
    "SAIOPP_prose.md",
    "SAI_AGENT_REACTIONS.md",
    "SAIPEN-WORK-DESK.md",
    "bee_like_idea1.md",
    "bee_like_idea1_future_Gate.md",
    "computer1.md",
    "future1.md",
    "iniciative.md",
    "talking.md",
    "talking1.md",
    "tv.md",
    "what_means_SAI.md",
})

#: Beacon file -> the receipt that captured it. The Work that closed is noted
#: beside its row.
#:
#: This table exists because no receipt can hold the binding itself: the intake
#: grammar has no source-path field, so a captured file's basename never reaches
#: its receipt. It exists -- rather than the journal -- because the journal is
#: free text: an agent writing a file's name while investigating it used to be
#: enough to pass the sweep, and in T-160 that is exactly what happened. A
#: binding here is a claim that the named receipt captured these bytes, and the
#: check verifies it against the receipt's own digest instead of taking the
#: word of a sentence. (T-158, hardened T-160)
BEACON_BINDINGS = {
    "milestoned1.md": "SRC-117",  # T-151
    "YAZADAYU_born1.md": "SRC-119",  # T-157
}


def _receipt_capture_digest(receipt_id: str) -> str:
    """The digest a receipt recorded of the bytes it was minted from.

    ``compared_digest`` is that record; ``source_sha256`` is the digest of the
    receipt file itself and says nothing about humbox/. Returns "" when the
    receipt is missing or unreadable so the caller fails the binding rather than
    the suite -- an absent receipt is the finding, not a crash.
    """
    meta = ROOT / ".saipen" / "intake" / "active" / f"{receipt_id}.meta.json"
    if not meta.is_file():
        return ""
    try:
        return json.loads(read(meta))["request_provenance"]["compared_digest"]
    except (ValueError, KeyError, TypeError):
        return ""


def _beacon_key(path: pathlib.Path) -> str:
    """A beacon file's identity: its path relative to humbox/.

    The basename is not an identity. A file in a subdirectory that happens to
    share a word with a captured file is a different file, and reading it as
    the same one is the mistake this check exists to catch -- so a top-level
    file is identified by its bare name and a nested one by its relative path.
    """
    return path.relative_to(HUMBOX).as_posix()


def test_every_new_operator_beacon_is_registered_before_it_sits_in_the_folder():
    """An operator file that lands in humbox/ is traceable, or it is named.

    The beacon is fed by a human, so it changes whenever the human has
    something to say and nothing in the product notices. That is the whole
    reason the intake path exists: the bytes get hashed into a receipt and
    projected into Work, so the material is attributable instead of just
    being present. Checking the folder as a whole -- rather than one named
    file per ticket -- is the only form of that check that survives the next
    arrival.

    Registered means one of exactly two things: a BEACON_BINDINGS row whose
    receipt still hashes to the file's bytes, or an explicit exemption in
    LEGACY_UNREGISTERED_BEACON. It does not mean "mentioned somewhere" -- the
    BOARD and the journal are free text that the protocol is actively pruning,
    and T-160 was written because a sentence about a probe was passing as a
    capture.
    """
    drifted = []
    for key, receipt in sorted(BEACON_BINDINGS.items()):
        path = HUMBOX / key
        if not path.is_file():
            drifted.append(f"{key} is bound to {receipt} but the file is gone")
            continue
        raw = path.read_bytes()
        live = {
            hashlib.sha256(raw).hexdigest(),
            hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
        }
        if _receipt_capture_digest(receipt) not in live:
            drifted.append(f"{key} no longer hashes to what {receipt} captured")
    assert not drifted, (
        "a beacon binding the receipt cannot vouch for: "
        f"{drifted} -- the binding claims these bytes were captured; re-capture "
        "the file or drop the row"
    )

    registered = set(BEACON_BINDINGS)
    unregistered = sorted(
        key
        for path in HUMBOX.rglob("*.md")
        for key in (_beacon_key(path),)
        if key not in registered
        and key not in LEGACY_UNREGISTERED_BEACON
    )
    assert not unregistered, (
        "operator material in humbox/ that no receipt accounts for: "
        f"{unregistered} -- capture it with `saipen start --file humbox/<path>`, "
        'then add "<key>": "<SRC-id>" to BEACON_BINDINGS (the row is checked '
        "against that receipt's digest), or add it to "
        "LEGACY_UNREGISTERED_BEACON if it genuinely needs no Work"
    )


# --------------------------------------------------------------------
# future letters (T-161)
# --------------------------------------------------------------------

def test_t161_future_letters_are_recorded_as_a_stable_non_authoritative_surface():
    """The API map, the module, the docs and the wire kind agree, and nothing
    here quietly became an instruction surface."""
    from saimail import envelope, future_letter

    api = json.loads(read(ROOT / "lab/stable_local_api.json"))
    exported = {(item["module"], item["symbol"]) for item in api["apis"]}
    for symbol in ("create", "list_letters", "show", "open_letter", "reopen_letter",
                   "export_bundle", "import_bundle", "read_bundle"):
        assert ("saimail.future_letter", symbol) in exported, symbol
        assert callable(getattr(future_letter, symbol))

    documented = {entry["code"] for entry in api["failure_codes"]
                  if entry["where"] == "saimail/future_letter.py"}
    for code in ("BUNDLE_CORRUPT", "BUNDLE_HASH_MISMATCH", "BUNDLE_DECRYPT_FAILED",
                 "UNSUPPORTED_SCHEMA", "RECOVERY_KEY_REQUIRED", "LETTER_NOT_FOUND",
                 "LETTER_ALREADY_IMPORTED"):
        assert code in documented, code

    # The kind rides the existing closed set rather than a parallel mailbox.
    assert future_letter.KIND in envelope.KINDS
    assert future_letter.KIND == "FUTURE_LETTER"

    # Nothing in the library names an instruction surface.
    source = read(ROOT / "saimail/future_letter.py")
    assert "saimail_local" not in source and "import lab" not in source
    assert ".saipen" not in source
    for forbidden in ("system_prompt", "append_to_prompt", "auto_open",
                      "startup_context"):
        assert forbidden not in source, forbidden

    # The two custody modes are named, not implied.
    assert future_letter.classification(future_letter.CUSTODY_PRIVATE) == "PRIVATE"
    assert (future_letter.classification(future_letter.CUSTODY_RECOVERY_ENABLED)
            == "NOT_PRIVATE_RECOVERY_ENABLED")

    # An agent entering the repo can learn the feature without tribal knowledge.
    readme = read(ROOT / "README.md")
    for phrase in ("Future letters", "future-letter list", "future-letter open",
                   "NOT_PRIVATE_RECOVERY_ENABLED"):
        assert phrase in readme, phrase
