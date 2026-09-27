"""U1 — drift-safe watched coverage without new ignore authority.

One receiver-owned variable, ``Interest.watched``, is compared against itself:
baseline watches nothing, treatment watches exactly one canonical target. Every
record and every frame is byte-identical between the two arms; the only changed
receiver input is the watched set. The selector (``saimail/selector.py``) is
used unchanged, including the pre-existing ``R0-WATCHED`` rule that raises a
message to ``OPEN_R3`` when a relation points at a watched canonical target.

The mechanism is raise-only by construction: ``R0-WATCHED`` is the first rule,
so treatment attention depth can never fall below baseline attention depth. The
experiment measures the coverage that receiver-owned watching buys under
vocabulary/topic drift, and the attention inflation a sender can force by
asserting relations to a watched target.

Truth is the fixture row's declared receiver need, independent of the selector
verdict. Offline only: no network, no model, no provider.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bench.selector_corpus import CASES, INTEREST as STRESS_INTEREST
from lab import experiment_manifest as em
from saimail.acceptance import ProfileRegistry
from saimail.selector import IGNORE, OPEN_R2, OPEN_R3, Interest, depth, select
from sailang import Record
from sailang.errors import SailangError
from sailang.frame import Batch, Profile, decode, project_batch

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "lab/watched_coverage_manifest.json"
REGISTRATION = "lab/watched_coverage_registration.json"
FIXTURES = "lab/watched_coverage_fixtures.json"
RESULT_SCHEMA = "WATCHED_COVERAGE_RESULT_1"
OPEN = frozenset({OPEN_R2, OPEN_R3})
WATCHED_RULE = "R0-WATCHED"
CREATED = "2026-09-20T21:20:00Z"
SEATS = {"A_TO_B": ("U1A", "U1B"), "B_TO_A": ("U1B", "U1A")}

_TERMINAL = ("COVERAGE_GAIN_NO_EXTRA_OPENS", "COVERAGE_GAIN_WITH_EXTRA_OPENS",
             "NO_COVERAGE_GAIN", "SAFETY_INVARIANT_VIOLATION")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ev(tag: str) -> str:
    return "sha256:" + sha256(tag.encode("utf-8"))


def preflight(root: Path = ROOT) -> dict:
    manifest = em.load(root / MANIFEST)
    current = em.verify_current(manifest, root=root)
    history = em.verify_historical(manifest, fixture_root=root)
    if current["verdict"] != em.CURRENT_MATCH:
        raise SailangError("U1_INPUT_DRIFT", json.dumps(current))
    if history["verdict"] != em.HISTORICAL_VERIFIED:
        raise SailangError("U1_HISTORY_MISMATCH", json.dumps(history))
    return {"current": current, "historical": history}


def load_fixture(root: Path = ROOT) -> dict:
    return json.loads((root / FIXTURES).read_text(encoding="utf-8"))


def load_registration(root: Path = ROOT) -> dict:
    return json.loads((root / REGISTRATION).read_text(encoding="utf-8"))


def _interest(spec: dict, watched) -> Interest:
    return Interest.of(atoms=spec["atoms"], subjects=spec["subjects"],
                       watched=watched, noise=spec["noise"])


def baseline_interest(registration: dict) -> Interest:
    return _interest(registration["baseline_interest"], registration["baseline_watched"])


def treatment_interest(registration: dict) -> Interest:
    return _interest(registration["treatment_interest"], registration["treatment_watched"])


def _targets(registration: dict) -> dict:
    return {"WATCHED": registration["watched_target"],
            "OTHER": registration["other_target"]}


def _record(message_id: str, index: int, group: dict, seat: str, targets: dict) -> Record:
    fields = dict(KIND="F", SRC=f"AGENT:{seat}", SUBJ=group["subject"],
                  CLAIM=group["claim"], TYPE="OBS", CREATED=CREATED,
                  STATUS=group["status"])
    fields["EV"] = ev(message_id) if group["evidence"] else "0"
    flag = group.get("flag")
    target = group.get("target")
    if flag and target:
        fields[flag] = targets[target]
    return Record.create(**fields)


def _entries(workload: dict, direction: str, registration: dict, profile: Profile):
    sender, _ = SEATS[direction]
    targets = _targets(registration)
    planned = []
    index = 0
    for group in workload["messages"]:
        for _ in range(group["count"]):
            message_id = f'{workload["id"]}-{index:03d}'
            planned.append((message_id, group, _record(message_id, index, group,
                                                       sender, targets)))
            index += 1
    batch = project_batch([record for _, _, record in planned], profile)
    frames = Batch.parse(batch.render(),
                         ProfileRegistry.with_profiles(profile).resolve(profile.id)).frames
    if len(frames) != len(planned):
        raise AssertionError("the frozen workload did not project every record")
    return tuple((message_id, group, frame)
                 for (message_id, group, _), frame in zip(planned, frames, strict=True))


def _arm(entries, interest: Interest) -> dict:
    rows = []
    for message_id, group, frame in entries:
        view = decode(frame)
        decision = select(view, interest)
        rows.append({
            "message_id": message_id,
            "workload": message_id.rsplit("-", 1)[0],
            "relevant": group["relevant"],
            "verdict": decision.verdict,
            "rule": decision.rule,
            "depth": depth(decision.verdict),
            "frame_sha256": sha256(frame.wire.encode("utf-8")),
        })
    return {
        "messages": len(rows),
        "total_open": sum(row["verdict"] in OPEN for row in rows),
        "rows": rows,
    }


def grade_pair(baseline: dict, treatment: dict) -> dict:
    """Grade after the independent arm decisions; truth never reaches a selector."""
    if len(baseline["rows"]) != len(treatment["rows"]):
        raise ValueError("paired arms differ in length")
    upgrades, rescued, not_rescued = [], [], []
    relevant_upgrades, irrelevant_upgrades = [], []
    spam_opens, noise_opens, extra_opens = [], [], []
    new_false_ignores, new_missed, downgrades, downward = [], [], [], []
    for left, right in zip(baseline["rows"], treatment["rows"], strict=True):
        if any(left[key] != right[key]
               for key in ("message_id", "workload", "relevant", "frame_sha256")):
            raise ValueError("paired arms do not identify the same message, truth and frame")
        base_depth, treat_depth = left["depth"], right["depth"]
        if treat_depth < base_depth:
            downward.append(right["message_id"])
            if left["verdict"] in OPEN:
                downgrades.append(right["message_id"])
        if treat_depth > base_depth:
            upgrades.append(right["message_id"])
            (relevant_upgrades if right["relevant"] else irrelevant_upgrades).append(
                right["message_id"])
            if not right["relevant"]:
                extra_opens.append(right["message_id"])
                if right["workload"] == "RELATION_SPAM":
                    spam_opens.append(right["message_id"])
                if right["workload"] == "NOISE_OVERLAP":
                    noise_opens.append(right["message_id"])
        if right["relevant"] and right["verdict"] == IGNORE and left["verdict"] != IGNORE:
            new_false_ignores.append(right["message_id"])
        if right["relevant"] and left["verdict"] in OPEN and right["verdict"] not in OPEN:
            new_missed.append(right["message_id"])
        if (right["relevant"] and left["verdict"] not in OPEN and right["verdict"] in OPEN
                and right["rule"] == WATCHED_RULE):
            rescued.append(right["message_id"])
        if (right["workload"] == "NO_RELATION_RELEVANT" and right["relevant"]
                and left["verdict"] not in OPEN and right["verdict"] not in OPEN):
            not_rescued.append(right["message_id"])
    extra_opens_other = sorted(set(extra_opens) - set(spam_opens) - set(noise_opens))
    violation = bool(downward or new_false_ignores or new_missed or downgrades)
    return {
        "relevant_attention_upgrades": len(relevant_upgrades),
        "irrelevant_attention_upgrades": len(irrelevant_upgrades),
        "total_attention_upgrades": len(upgrades),
        "relevant_drift_rescued": len(rescued),
        "relevant_drift_not_rescued": len(not_rescued),
        "unnecessary_extra_opens": len(extra_opens_other),
        "relation_spam_extra_opens": len(spam_opens),
        "noise_overlap_extra_opens": len(noise_opens),
        "downward_attention_changes": len(downward),
        "new_false_ignores": len(new_false_ignores),
        "new_missed_relevant": len(new_missed),
        "baseline_required_open_downgrades": len(downgrades),
        "safety_invariant_violation": violation,
        "upgraded_message_ids": upgrades,
        "rescued_message_ids": rescued,
        "relevant_not_rescued_message_ids": not_rescued,
        "extra_open_message_ids": sorted(extra_opens),
        "baseline_total_open": baseline["total_open"],
        "treatment_total_open": treatment["total_open"],
    }


def _outcome(aggregate: dict) -> str:
    if aggregate["safety_invariant_violation"]:
        return "SAFETY_INVARIANT_VIOLATION"
    if aggregate["relevant_attention_upgrades"] > 0:
        if aggregate["irrelevant_attention_upgrades"] == 0:
            return "COVERAGE_GAIN_NO_EXTRA_OPENS"
        return "COVERAGE_GAIN_WITH_EXTRA_OPENS"
    return "NO_COVERAGE_GAIN"


_METRIC_KEYS = (
    "relevant_attention_upgrades", "irrelevant_attention_upgrades",
    "total_attention_upgrades", "relevant_drift_rescued", "relevant_drift_not_rescued",
    "unnecessary_extra_opens", "relation_spam_extra_opens", "noise_overlap_extra_opens",
    "downward_attention_changes", "new_false_ignores", "new_missed_relevant",
    "baseline_required_open_downgrades", "baseline_total_open", "treatment_total_open",
)


def _aggregate(pairs: list) -> dict:
    totals = {key: sum(pair["comparison"][key] for pair in pairs) for key in _METRIC_KEYS}
    totals["safety_invariant_violation"] = any(
        pair["comparison"]["safety_invariant_violation"] for pair in pairs)
    totals["outcome"] = _outcome(totals)
    return totals


def r1_control() -> dict:
    """The unchanged R1 stress corpus, measured separately by the existing selector."""
    profile = Profile.load("1")
    records = [Record.create(**case.fields) for case in CASES]
    frames = Batch.parse(
        project_batch(records, profile).render(),
        ProfileRegistry.with_profiles(profile).resolve(profile.id)).frames
    decisions = [select(decode(frame), STRESS_INTEREST) for frame in frames]
    fingerprint = sha256(json.dumps(
        [f"{case.name}:{decision.verdict}" for case, decision in
         zip(CASES, decisions, strict=True)]).encode("utf-8"))
    return {
        "scope": "unchanged current R1 stress corpus; not the U1 transport/header experiment",
        "cases": len(CASES),
        "watched_relation_cases": sum(case.klass == "relation_to_watched" for case in CASES),
        "unknown_atom_fallbacks": sum(d.rule == "R2-UNKNOWN" for d in decisions),
        "opaque_claim_fallbacks": sum(d.rule == "R3-OPEN-RECORD" for d in decisions),
        "false_ignores": sum(d.verdict == IGNORE and depth(c.truth) > 0
                             for c, d in zip(CASES, decisions, strict=True)),
        "verdict_fingerprint": fingerprint,
        "changed_by_treatment": False,
    }


def run_experiment(base, *, root: Path = ROOT, probe: dict | None = None) -> dict:
    admission = preflight(root)
    base = Path(base)
    if base.exists() and any(base.iterdir()):
        raise ValueError("U1_NONEMPTY_WORKSPACE")
    base.mkdir(parents=True, exist_ok=True)
    fixture = load_fixture(root)
    registration = load_registration(root)
    profile = Profile.load("1")
    baseline_rule = baseline_interest(registration)
    treatment_rule = treatment_interest(registration)
    pairs = []
    for workload in fixture["workloads"]:
        for direction in fixture["directions"]:
            entries = _entries(workload, direction, registration, profile)
            baseline = _arm(entries, baseline_rule)
            treatment = _arm(entries, treatment_rule)
            identical = all(
                left["frame_sha256"] == right["frame_sha256"]
                for left, right in zip(baseline["rows"], treatment["rows"], strict=True))
            if not identical:
                raise AssertionError("paired arms did not receive identical frames")
            pairs.append({
                "workload": workload["id"], "direction": direction,
                "paired_frames_identical": identical,
                "baseline": baseline, "treatment": treatment,
                "comparison": grade_pair(baseline, treatment),
            })
    aggregate = _aggregate(pairs)
    return {
        "schema": RESULT_SCHEMA, "version": 1, "status": "PASS",
        "outcome": aggregate["outcome"],
        "admission": admission,
        "watched_target": registration["watched_target"],
        "other_target": registration["other_target"],
        "treatment_variable": registration["treatment_variable"],
        "directions": fixture["directions"],
        "workload_ids": [workload["id"] for workload in fixture["workloads"]],
        "fixture_sha256": sha256((root / FIXTURES).read_bytes()),
        "registration_sha256": sha256((root / REGISTRATION).read_bytes()),
        "pairs": pairs,
        "aggregate": aggregate,
        "r1_control": r1_control(),
        "setup_and_maintenance": {
            "receiver_watched_target_entries_for_two_participants": 2,
            "sender_extra_treatment_work": 0,
            "future_watched_target_review_cost": "NOT_MEASURED",
            "setup_cost_not_in_any_friction_model": True,
        },
        "runtime": {"network_attempts": (probe or {}).get("blocked", 0),
                    "model_calls": 0, "provider_calls": 0},
        "latency": "NOT_MEASURED", "subjective_pleasantness": "NOT_MEASURED",
        "production_promotion": "NONE", "publication": "NONE",
        "no_production_default_change": True,
        "interpretation": "PASS means the registered experiment completed, not that watching proves relevance",
    }


def render_report(result: dict) -> str:
    aggregate = result["aggregate"]
    lines = [
        "# U1 watched-coverage experiment", "",
        f"Experiment: {result['status']}; outcome: **{result['outcome']}**.", "",
        f"Treatment variable: `{result['treatment_variable']}` (raise-only). "
        "The sender-asserted relation is an attention hint, never relevance truth.", "",
        "| Workload / direction | Relevant upgrades | Irrelevant upgrades | Rescued | Not rescued | Spam opens | Noise opens | Downgrades |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for pair in result["pairs"]:
        comparison = pair["comparison"]
        lines.append(
            f"| {pair['workload']} / {pair['direction']} | "
            f"{comparison['relevant_attention_upgrades']} | "
            f"{comparison['irrelevant_attention_upgrades']} | "
            f"{comparison['relevant_drift_rescued']} | "
            f"{comparison['relevant_drift_not_rescued']} | "
            f"{comparison['relation_spam_extra_opens']} | "
            f"{comparison['noise_overlap_extra_opens']} | "
            f"{comparison['baseline_required_open_downgrades']} |")
    lines += [
        "",
        "## Aggregate (both directions)", "",
        f"- relevant_attention_upgrades: {aggregate['relevant_attention_upgrades']}",
        f"- irrelevant_attention_upgrades: {aggregate['irrelevant_attention_upgrades']}",
        f"- total_attention_upgrades: {aggregate['total_attention_upgrades']}",
        f"- relevant_drift_rescued: {aggregate['relevant_drift_rescued']}",
        f"- relevant_drift_not_rescued: {aggregate['relevant_drift_not_rescued']}",
        f"- unnecessary_extra_opens: {aggregate['unnecessary_extra_opens']}",
        f"- relation_spam_extra_opens: {aggregate['relation_spam_extra_opens']}",
        f"- noise_overlap_extra_opens: {aggregate['noise_overlap_extra_opens']}",
        f"- downward_attention_changes: {aggregate['downward_attention_changes']}",
        f"- new_false_ignores: {aggregate['new_false_ignores']}",
        f"- new_missed_relevant: {aggregate['new_missed_relevant']}",
        f"- baseline_required_open_downgrades: {aggregate['baseline_required_open_downgrades']}",
        "",
        "False opens are measurable cost; false ignores are information loss. "
        "They are reported separately and never exchanged for each other.",
        "R0-WATCHED is the pre-existing production rule; U1 did not modify the selector, "
        "and no ignore authority was created by this experiment.",
        "This is an R1 attention-coverage measurement after a TriageView exists. "
        "It must not be compared to the V2-02 transport/header fallback-open savings.",
        "No production default change, no model/provider/network call, no frozen-candidate "
        "rebuild and no publication.", "",
    ]
    return "\n".join(lines)
