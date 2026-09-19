"""T-9 benchmark corpus: realistic SAIPEN/SAIMAIL-like information.

Each case carries three things that must stay independent of each other:

* ``prose``   — a concise natural-language baseline carrying the SAME
  information as the record, including provenance, confidence and the evidence
  pointer. Padding the prose would rig the benchmark; so would stripping its
  provenance, which is the part SAILANG charges bytes for.
* ``fields``  — the canonical SAILANG record.
* ``expect``  — triage-relevant ground truth, declared BY HAND. It is never
  derived from the implementation, or the semantic check would be comparing
  the projector against itself.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional


def ev(tag: str) -> str:
    """A deterministic stand-in for a real evidence content address."""
    return "sha256:" + hashlib.sha256(tag.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Case:
    case: str
    klass: str
    prose: str
    fields: dict
    expect: dict = field(default_factory=dict)


CASES: list[Case] = []


def add(case: str, klass: str, prose: str, fields: dict, expect: dict) -> None:
    CASES.append(Case(case=case, klass=klass, prose=prose, fields=fields, expect=expect))


T = "2026-09-17T08:41:00Z"

# ---------------------------------------------------------------- 1. verified test result

add(
    "verified-test-1", "verified_test_result",
    "The suite passed: pytest reported 574 of 574 tests green on the queue module, "
    "run by agent a17 on 2026-09-17, evidence sha256:5f2b… — verified.",
    dict(KIND="O", SRC="TEST:pytest/queue", SUBJ="queue", CLAIM="TEST_SUITE=574_574_PASS",
         TYPE="OBS", EV=ev("pytest-queue"), STATUS="U4", DIRECTNESS="HIGH", CREATED=T),
    dict(kind="O", subject="queue", status="U4", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "verified-test-2", "verified_test_result",
    "Verified by agent b03: the recovery regression suite ran clean, 88 of 88 green, "
    "evidence sha256:1c9a… attached.",
    dict(KIND="O", SRC="TEST:pytest/recovery", SUBJ="recovery", CLAIM="TEST_SUITE=88_88_PASS",
         TYPE="OBS", EV=ev("pytest-recovery"), STATUS="U4", DIRECTNESS="HIGH", CREATED=T),
    dict(kind="O", subject="recovery", status="U4", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "verified-test-3", "verified_test_result",
    "Direct observation from the CI log: the validation gate went green on commit "
    "10a2989, evidence sha256:7d41… — verified, high directness.",
    dict(KIND="O", SRC="LOG:ci/validate", SUBJ="validate", CLAIM="VALIDATION=PASS",
         TYPE="OBS", EV=ev("ci-validate"), STATUS="U4", DIRECTNESS="HIGH",
         INTEGRITY="MED", CREATED=T),
    dict(kind="O", subject="validate", status="U4", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)

# ------------------------------------------------- 2. contradicted human memory claim

add(
    "human-memory-1", "contradicted_human_memory",
    "vacterro remembers the OpenCode database holding data from 2025. This is memory, "
    "not observation: no evidence attached, so it stays unverified.",
    dict(KIND="F", SRC="HUMAN:vacterro", SUBJ="opencode.db", CLAIM="DB_HISTORY>=2025",
         TYPE="MEM", EV="0", STATUS="U1", DIRECTNESS="LOW", CREATED=T),
    dict(kind="F", subject="opencode.db", status="U1", has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "human-memory-2", "contradicted_human_memory",
    "Filesystem metadata contradicts that: the database was created 2026-08-23, "
    "observed directly at the path, evidence sha256:a3f0…, and it refutes the "
    "earlier recollection.",
    dict(KIND="O", SRC="FS:C:/Users/vac34/.local/share/opencode/opencode.db",
         SUBJ="opencode.db", CLAIM="DB_CREATED=2026-08-23", TYPE="OBS",
         EV=ev("fs-opencode-db"), STATUS="U4", DIRECTNESS="HIGH", INTEGRITY="MED",
         REFUTES=ev("claim-db-2025"), CREATED=T),
    dict(kind="O", subject="opencode.db", status="U4", has_evidence=True, refutes=True,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "human-memory-3", "contradicted_human_memory",
    "vacterro recalls never touching the retry configuration. Memory only, "
    "no evidence, unverified — and the git log disagrees.",
    dict(KIND="F", SRC="HUMAN:vacterro", SUBJ="retry.cfg", CLAIM="CONFIGURATION=UNCHANGED",
         TYPE="MEM", EV="0", STATUS="U1", DIRECTNESS="LOW",
         CON=ev("git-retry-cfg"), CREATED=T),
    dict(kind="F", subject="retry.cfg", status="U1", has_evidence=False, refutes=False,
         supports=False, conflict=True, falsifiable=False, claim_open_record=False),
)

# ------------------------------------------------- 3. agent overclaim after partial tests

add(
    "overclaim-1", "agent_overclaim",
    "Agent a17 reported the root cause as found and the defect fully fixed, but only "
    "2 of 40 tests were run. Interpretation, not observation; no evidence attached, "
    "so it stays unverified.",
    dict(KIND="F", SRC="AGENT:a17", SUBJ="retry", CLAIM="ROOT_CAUSE=CLAIMED_ON_PARTIAL_TEST",
         TYPE="INT", EV="0", STATUS="U1", DIRECTNESS="LOW", CREATED=T),
    dict(kind="F", subject="retry", status="U1", has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "overclaim-2", "agent_overclaim",
    "Observed pattern from the run log: agent b03 raises its stated confidence after "
    "partial test runs, evidence sha256:6b22… — supported.",
    dict(KIND="O", SRC="LOG:seat/b03", SUBJ="b03", CLAIM="CONFIDENCE>PARTIAL_TEST",
         TYPE="OBS", EV=ev("seat-b03-conf"), STATUS="U2", DIRECTNESS="MED", CREATED=T),
    dict(kind="O", subject="b03", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "overclaim-3", "agent_overclaim",
    "Agent c11 said tests confirm the fix. The suite it cites never ran; no evidence, "
    "unverified, and it conflicts with the CI record.",
    dict(KIND="F", SRC="AGENT:c11", SUBJ="fix", CLAIM="TEST_SUITE=CLAIMED_NOT_RUN",
         TYPE="INT", EV="0", STATUS="U0", CON=ev("ci-no-run"), CREATED=T),
    dict(kind="F", subject="fix", status="U0", has_evidence=False, refutes=False,
         supports=False, conflict=True, falsifiable=False, claim_open_record=False),
)

# ------------------------------------- 4. queue / retry / duplicate-execution discovery

add(
    "queue-discovery-1", "queue_retry_duplicate_discovery",
    "Discovery: after recovery, stale queue ownership survives a retry and causes "
    "duplicate execution. Interpretation over the run log, evidence sha256:91a7…, "
    "supported.",
    dict(KIND="F", SRC="AGENT:a17", SUBJ="queue",
         CLAIM="QUEUE_OWNERSHIP_STALE>RETRY>DUPLICATE_EXECUTION", TYPE="INT",
         EV=ev("queue-dup-exec"), STATUS="U2", DIRECTNESS="MED", CREATED=T),
    dict(kind="F", subject="queue", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "queue-discovery-2", "queue_retry_duplicate_discovery",
    "Second path to the same failure: recovery leaves the ownership record stale and "
    "the retry then duplicates work. Evidence sha256:bb31…, supports the earlier "
    "discovery.",
    dict(KIND="F", SRC="AGENT:b03", SUBJ="queue",
         CLAIM="RECOVERY>QUEUE_OWNERSHIP_STALE>DUPLICATE_EXECUTION", TYPE="INT",
         EV=ev("queue-dup-exec-2"), STATUS="U2",
         SUPPORTS=ev("queue-dup-exec"), CREATED=T),
    dict(kind="F", subject="queue", status="U2", has_evidence=True, refutes=False,
         supports=True, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "queue-discovery-3", "queue_retry_duplicate_discovery",
    "Observed in the deadlock trace: concurrency plus a stale queue owner produces a "
    "deadlock, evidence sha256:04dd…, strongly supported.",
    dict(KIND="O", SRC="LOG:trace/deadlock", SUBJ="queue",
         CLAIM="CONCURRENCY>QUEUE_OWNERSHIP_STALE>DEADLOCK", TYPE="OBS",
         EV=ev("deadlock-trace"), STATUS="U3", DIRECTNESS="HIGH", CREATED=T),
    dict(kind="O", subject="queue", status="U3", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)

# ---------------------------------------------------------------- 5. blocker

add(
    "blocker-1", "blocker",
    "Blocked: the ship path waits on active source coverage that nothing can close "
    "from here. Agent a17, no evidence attached, unverified.",
    dict(KIND="F", SRC="AGENT:a17", SUBJ="ship", CLAIM="BLOCKER=SOURCE_COVERAGE_OPEN",
         TYPE="INT", EV="0", STATUS="U1", CREATED=T),
    dict(kind="F", subject="ship", status="U1", has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "blocker-2", "blocker",
    "Blocked by a missing dependency: the release job cannot start until the upstream "
    "package publishes. Observed on the CI queue, evidence sha256:2e18…, supported.",
    dict(KIND="O", SRC="LOG:ci/release", SUBJ="release", CLAIM="BLOCKED>DEPENDENCY",
         TYPE="OBS", EV=ev("ci-release-block"), STATUS="U2", CREATED=T),
    dict(kind="O", subject="release", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "blocker-3", "blocker",
    "The board row is blocked on a validation gate that refuses without a receipt. "
    "Agent b03, evidence sha256:9ac4…, supported.",
    dict(KIND="F", SRC="AGENT:b03", SUBJ="T-1367", CLAIM="BLOCKER>VALIDATION",
         TYPE="INT", EV=ev("board-block"), STATUS="U2", CREATED=T),
    dict(kind="F", subject="T-1367", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)

# ------------------------------------------- 6. hypothesis + falsification condition

add(
    "hypothesis-1", "hypothesis",
    "Hypothesis from agent a17: the retry path itself causes the duplicate execution. "
    "It is falsified if a retry with a fresh owner still duplicates. Evidence "
    "sha256:91a7… supports it; still a hypothesis, not a fact.",
    dict(KIND="H", SRC="AGENT:a17", SUBJ="queue", CLAIM="RETRY>DUPLICATE_EXECUTION",
         TYPE="INT", FALSIFY="a retry with a fresh owner still duplicates",
         EV=ev("queue-dup-exec"), STATUS="U3", CREATED=T),
    dict(kind="H", subject="queue", status="U3", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=True, claim_open_record=False),
)
add(
    "hypothesis-2", "hypothesis",
    "Hypothesis: the performance regression comes from the new configuration loader. "
    "Falsified if reverting the loader leaves the regression in place. No evidence "
    "yet, so unverified.",
    dict(KIND="H", SRC="AGENT:b03", SUBJ="loader", CLAIM="CONFIGURATION>REGRESSION",
         TYPE="INT", FALSIFY="reverting the loader leaves the regression in place",
         EV="0", STATUS="U1", CREATED=T),
    dict(kind="H", subject="loader", status="U1", has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=True, claim_open_record=False),
)
add(
    "hypothesis-3", "hypothesis",
    "Hypothesis: checkpoint write amplification explains the slow session start. "
    "Falsified if a session with checkpointing disabled starts equally slowly. "
    "Evidence sha256:cc70… supports it.",
    dict(KIND="H", SRC="AGENT:c11", SUBJ="session", CLAIM="CHECKPOINT>PERFORMANCE",
         TYPE="INT", FALSIFY="a session with checkpointing disabled starts equally slowly",
         EV=ev("ckpt-perf"), STATUS="U2", CREATED=T),
    dict(kind="H", subject="session", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=True, claim_open_record=False),
)

# ---------------------------------------------------------------- 7. human goal

add(
    "goal-1", "human_goal",
    "vacterro wants the maintenance burden reduced. A goal, stated 2026-09-17; "
    "no evidence applies to it.",
    dict(KIND="G", SRC="HUMAN:vacterro", SUBJ="maintenance",
         CLAIM="reduce maintenance burden", CREATED=T),
    dict(kind="G", subject="maintenance", status=None, has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=True),
)
add(
    "goal-2", "human_goal",
    "vacterro wants stale OpenCode sessions deleted. A goal, not a claim about the world.",
    dict(KIND="G", SRC="HUMAN:vacterro", SUBJ="opencode",
         CLAIM="delete stale OpenCode sessions", CREATED=T),
    dict(kind="G", subject="opencode", status=None, has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=True),
)
add(
    "goal-3", "human_goal",
    "Goal from the steward: SAIMAIL must stay deletable without SAIPEN noticing.",
    dict(KIND="G", SRC="HUMAN:vacterro", SUBJ="saimail",
         CLAIM="SAIMAIL remains removable with no effect on SAIPEN", CREATED=T),
    dict(kind="G", subject="saimail", status=None, has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=True),
)

# ------------------------------------------------------- 8. human value / preference

add(
    "value-1", "human_value",
    "vacterro holds that quality outranks speed. A preference, stated 2026-09-17; "
    "evidence does not apply.",
    dict(KIND="V", SRC="HUMAN:vacterro", SUBJ="priority",
         CLAIM="quality outranks speed", CREATED=T),
    dict(kind="V", subject="priority", status=None, has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=True),
)
add(
    "value-2", "human_value",
    "Preference: reliability matters more than raw throughput.",
    dict(KIND="V", SRC="HUMAN:vacterro", SUBJ="tradeoff",
         CLAIM="reliability matters more than throughput", CREATED=T),
    dict(kind="V", subject="tradeoff", status=None, has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=True),
)
add(
    "value-3", "human_value",
    "Preference, compactly stated: prefer simple over clever.",
    dict(KIND="V", SRC="HUMAN:vacterro", SUBJ="style", CLAIM="SIMPLE>CLEVER", CREATED=T),
    dict(kind="V", subject="style", status=None, has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)

# ------------------------------------------------- 9. evidence-backed observation

add(
    "observation-1", "evidence_backed_observation",
    "Observed on disk: the state file was last written 2026-09-17T08:50:40Z, read "
    "directly from filesystem metadata, evidence sha256:3311…, verified.",
    dict(KIND="O", SRC="FS:V:/_SAIPEN/.saipen/STATE.md", SUBJ="STATE.md",
         CLAIM="TIMESTAMP=2026-09-17T08:50:40Z", TYPE="OBS", EV=ev("state-mtime"),
         STATUS="U4", DIRECTNESS="HIGH", INTEGRITY="MED", CREATED=T),
    dict(kind="O", subject="STATE.md", status="U4", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "observation-2", "evidence_backed_observation",
    "Observed in the git record: commit 10a2989 is the current head, evidence "
    "sha256:5e77…, verified with high integrity.",
    dict(KIND="O", SRC="GIT:_SAIPEN", SUBJ="HEAD", CLAIM="HEAD=10a2989", TYPE="OBS",
         EV=ev("git-head"), STATUS="U4", DIRECTNESS="HIGH", INTEGRITY="HIGH", CREATED=T),
    dict(kind="O", subject="HEAD", status="U4", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "observation-3", "evidence_backed_observation",
    "Observed: the intake directory holds 51 active receipts, counted directly, "
    "evidence sha256:8c2f…, verified, data as of 2026-09-17.",
    dict(KIND="O", SRC="FS:V:/_SAIPEN/.saipen/intake/active", SUBJ="intake",
         CLAIM="RECEIPTS=51", TYPE="OBS", EV=ev("intake-count"), STATUS="U4",
         DIRECTNESS="HIGH", FRESHNESS="2026-09-17T08:00:00Z", CREATED=T),
    dict(kind="O", subject="intake", status="U4", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)

# ------------------------------------------------- 10. unknown / uncertain claim

add(
    "unknown-1", "unknown_uncertain",
    "Someone reported intermittent duplicate deliveries. Source unknown, no evidence, "
    "nothing established.",
    dict(KIND="F", SRC="UNKNOWN", SUBJ="delivery", CLAIM="DUPLICATE_EXECUTION=INTERMITTENT",
         TYPE="INT", EV="0", STATUS="U0", DIRECTNESS="LOW", CREATED=T),
    dict(kind="F", subject="delivery", status="U0", has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "unknown-2", "unknown_uncertain",
    "Unverified network report that the mirror is stale. No provenance worth the name, "
    "nothing established.",
    dict(KIND="F", SRC="NET:mirror-report", SUBJ="mirror", CLAIM="METADATA=STALE",
         TYPE="INT", EV="0", STATUS="U0", DIRECTNESS="LOW", CREATED=T),
    dict(kind="F", subject="mirror", status="U0", has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "unknown-3", "unknown_uncertain",
    "An agent thinks the session store may be growing without bound, but has not "
    "looked. Unverified.",
    dict(KIND="F", SRC="AGENT:c11", SUBJ="session", CLAIM="SESSION=UNBOUNDED_GROWTH",
         TYPE="INT", EV="0", STATUS="U1", CREATED=T),
    dict(kind="F", subject="session", status="U1", has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)

# ---------------------------------------------------------------- 11. warning

add(
    "warning-1", "warning",
    "Warning for the next seat: promoting a record without an evidence reference "
    "corrupts the memory gate. Observed once already, evidence sha256:ad90…, supported.",
    dict(KIND="F", SRC="AGENT:a17", SUBJ="promotion", CLAIM="PROMOTION>EVIDENCE=REQUIRED",
         TYPE="INT", EV=ev("promo-gate"), STATUS="U2", CREATED=T),
    # claim_open_record=True, corrected after the first benchmark run: this claim
    # is a chain that ENDS in a comparison ("A>B=C"), which SAILANG v0 grammar does
    # not cover. The projector is right to fall back; the original expectation
    # asserted a capability v0 never promised. Reported as finding N-1, and the
    # grammar was deliberately NOT widened mid-benchmark.
    dict(kind="F", subject="promotion", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=True),
)
add(
    "warning-2", "warning",
    "Warning: the signature must be verified before the payload is decrypted, or a "
    "forged envelope gets parsed first. Evidence sha256:71be…, strongly supported.",
    dict(KIND="F", SRC="AGENT:b03", SUBJ="envelope", CLAIM="SIGNATURE>ENVELOPE=BEFORE_DECRYPT",
         TYPE="INT", EV=ev("sig-order"), STATUS="U3", CREATED=T),
    # claim_open_record=True for the same reason as warning-1 (finding N-1).
    dict(kind="F", subject="envelope", status="U3", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=True),
)
add(
    "warning-3", "warning",
    "Warning from the maintenance seat: a checkpoint written during recovery can "
    "outrank the recovery itself. No evidence attached yet.",
    dict(KIND="F", SRC="AGENT:c11", SUBJ="recovery", CLAIM="CHECKPOINT>RECOVERY",
         TYPE="INT", EV="0", STATUS="U1", CREATED=T),
    dict(kind="F", subject="recovery", status="U1", has_evidence=False, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)

# ------------------------------------------------- 12. cross-reference to evidence

add(
    "crossref-1", "cross_reference",
    "This supports the earlier queue discovery: a second independent run reproduced "
    "it, evidence sha256:bb31…, and it corroborates record sha256:91a7…, supported.",
    dict(KIND="F", SRC="AGENT:b03", SUBJ="queue", CLAIM="DUPLICATE_EXECUTION=REPRODUCED",
         TYPE="INT", EV=ev("queue-dup-exec-2"), STATUS="U2",
         SUPPORTS=ev("queue-dup-exec"), CREATED=T),
    dict(kind="F", subject="queue", status="U2", has_evidence=True, refutes=False,
         supports=True, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "crossref-2", "cross_reference",
    "This refutes the earlier timestamp claim: the file metadata says otherwise, "
    "evidence sha256:a3f0…, refuting record sha256:1f8c…, verified.",
    dict(KIND="O", SRC="FS:V:/_SAIPEN/.saipen/LOG.md", SUBJ="LOG.md",
         CLAIM="TIMESTAMP=2026-09-17T08:55:00Z", TYPE="OBS", EV=ev("log-mtime"),
         STATUS="U4", REFUTES=ev("claim-log-time"), CREATED=T),
    dict(kind="O", subject="LOG.md", status="U4", has_evidence=True, refutes=True,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "crossref-3", "cross_reference",
    "Two records disagree about the same subject and both are retained: this one "
    "conflicts with sha256:6b22…, evidence sha256:e4a1…, supported.",
    dict(KIND="F", SRC="AGENT:a17", SUBJ="b03", CLAIM="CONFIDENCE=CALIBRATED",
         TYPE="INT", EV=ev("conf-calib"), STATUS="U2", CON=ev("seat-b03-conf"), CREATED=T),
    dict(kind="F", subject="b03", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=True, falsifiable=False, claim_open_record=False),
)

# ---------------------------------------------------------------- 13. Unicode content

add(
    "unicode-1", "unicode_content",
    "Наблюдение: база данных создана 2026-08-23, прочитано напрямую из метаданных "
    "файловой системы, доказательство sha256:a3f0…, проверено.",
    dict(KIND="O", SRC="FS:C:/Users/vac34/opencode.db", SUBJ="opencode.db",
         CLAIM="база создана 2026-08-23", TYPE="OBS", EV=ev("fs-opencode-db"),
         STATUS="U4", CREATED=T),
    dict(kind="O", subject="opencode.db", status="U4", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=True),
)
add(
    "unicode-2", "unicode_content",
    "検証可能性: the verification gate is the point, not the verdict. Agent note, "
    "evidence sha256:4f80…, supported.",
    dict(KIND="F", SRC="AGENT:a17", SUBJ="検証", CLAIM="検証可能性が判定より重要",
         TYPE="INT", EV=ev("kensho"), STATUS="U2", CREATED=T),
    dict(kind="F", subject="検証", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=True),
)
add(
    "unicode-3", "unicode_content",
    "Märkus eesti keeles: tõenduspõhisus on ainus tee, tõend sha256:9b7c…, toetatud.",
    dict(KIND="F", SRC="HUMAN:vacterro", SUBJ="tõendus",
         CLAIM="tõenduspõhisus on ainus tee", TYPE="INT", EV=ev("toendus"),
         STATUS="U2", CREATED=T),
    dict(kind="F", subject="tõendus", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=True),
)

# --------------------------------------------------- 14. long file / path reference

add(
    "longpath-1", "long_path_reference",
    "Observed in V:/___VAC/__K/__CODE/_AI_STUFF_AGENTIC/_SAIPEN/tools/saipen_engine/"
    "operations.py at line 1860: the VERIFY to REVIEW gate refuses without evidence. "
    "Evidence sha256:0f3d…, verified.",
    dict(KIND="O",
         SRC="FS:V:/___VAC/__K/__CODE/_AI_STUFF_AGENTIC/_SAIPEN/tools/saipen_engine/operations.py",
         SUBJ="operations.py:1860", CLAIM="VALIDATION=REFUSES_WITHOUT_EVIDENCE",
         TYPE="OBS", EV=ev("ops-1860"), STATUS="U4", DIRECTNESS="HIGH", CREATED=T),
    dict(kind="O", subject="operations.py:1860", status="U4", has_evidence=True,
         refutes=False, supports=False, conflict=False, falsifiable=False,
         claim_open_record=False),
)
add(
    "longpath-2", "long_path_reference",
    "Observed in V:/___VAC/__K/__CODE/_AI_STUFF_AGENTIC/_SAIPEN/.saipen/extensions/subs/"
    "PROTOCOL.md: a subSaipen is never a second write path. Evidence sha256:2b6e…, verified.",
    dict(KIND="O",
         SRC="FS:V:/___VAC/__K/__CODE/_AI_STUFF_AGENTIC/_SAIPEN/.saipen/extensions/subs/PROTOCOL.md",
         SUBJ="subs/PROTOCOL.md", CLAIM="SUBSAIPEN=NO_SECOND_WRITE_PATH", TYPE="OBS",
         EV=ev("subs-protocol"), STATUS="U4", CREATED=T),
    dict(kind="O", subject="subs/PROTOCOL.md", status="U4", has_evidence=True,
         refutes=False, supports=False, conflict=False, falsifiable=False,
         claim_open_record=False),
)
add(
    "longpath-3", "long_path_reference",
    "Observed in C:/Users/vac34/AppData/Local/saipen/scheduled-source/saipen/phases/"
    "verify.md: a gate that cannot fail is not a gate. Evidence sha256:7a15…, verified.",
    dict(KIND="O",
         SRC="FS:C:/Users/vac34/AppData/Local/saipen/scheduled-source/saipen/phases/verify.md",
         SUBJ="phases/verify.md", CLAIM="VALIDATION=RED_CONTROL_REQUIRED", TYPE="OBS",
         EV=ev("verify-md"), STATUS="U4", CREATED=T),
    dict(kind="O", subject="phases/verify.md", status="U4", has_evidence=True,
         refutes=False, supports=False, conflict=False, falsifiable=False,
         claim_open_record=False),
)

# ------------------------------------------------- 15. repeated dictionary terms

add(
    "dictterms-1", "repeated_dictionary_terms",
    "Discovery: recovery leaves queue ownership stale, the retry then causes duplicate "
    "execution, and the regression suite reproduces it. Evidence sha256:d0c1…, supported.",
    dict(KIND="F", SRC="AGENT:a17", SUBJ="queue",
         CLAIM="RECOVERY>QUEUE_OWNERSHIP_STALE>RETRY>DUPLICATE_EXECUTION>REGRESSION",
         TYPE="INT", EV=ev("dict-heavy-1"), STATUS="U2", CREATED=T),
    dict(kind="F", subject="queue", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "dictterms-2", "repeated_dictionary_terms",
    "Discovery: a checkpoint during validation writes a signature the envelope layer "
    "later rejects, which shows up as a regression. Evidence sha256:f2aa…, supported.",
    dict(KIND="F", SRC="AGENT:b03", SUBJ="envelope",
         CLAIM="CHECKPOINT>VALIDATION>SIGNATURE>ENVELOPE>REGRESSION", TYPE="INT",
         EV=ev("dict-heavy-2"), STATUS="U2", CREATED=T),
    dict(kind="F", subject="envelope", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)
add(
    "dictterms-3", "repeated_dictionary_terms",
    "Discovery: database metadata plus a stale timestamp plus a configuration reload "
    "produce a performance regression under concurrency. Evidence sha256:63bd…, supported.",
    dict(KIND="F", SRC="AGENT:c11", SUBJ="db",
         CLAIM="DATABASE>METADATA>TIMESTAMP>CONFIGURATION>PERFORMANCE>CONCURRENCY",
         TYPE="INT", EV=ev("dict-heavy-3"), STATUS="U2", CREATED=T),
    dict(kind="F", subject="db", status="U2", has_evidence=True, refutes=False,
         supports=False, conflict=False, falsifiable=False, claim_open_record=False),
)

#: The information classes this corpus is required to cover.
REQUIRED_CLASSES = (
    "verified_test_result",
    "contradicted_human_memory",
    "agent_overclaim",
    "queue_retry_duplicate_discovery",
    "blocker",
    "hypothesis",
    "human_goal",
    "human_value",
    "evidence_backed_observation",
    "unknown_uncertain",
    "warning",
    "cross_reference",
    "unicode_content",
    "long_path_reference",
    "repeated_dictionary_terms",
)


def classes() -> dict:
    out: dict = {}
    for case in CASES:
        out.setdefault(case.klass, []).append(case.case)
    return out
