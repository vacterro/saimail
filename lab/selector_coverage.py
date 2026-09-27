"""V2-02 paired experiment: one receiver-owned ignore-topic coverage change.

Truth stays outside the header policy. Information loss disqualifies a cost win.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bench.selector_corpus import CASES, INTEREST
from lab import experiment_manifest as em
from lab import local_scenario as ls
from lab import utility_friction as uf
from saimail import envelope, postoffice
from saimail.acceptance import ProfileRegistry
from saimail.selector import DEFER, IGNORE, OPEN_R2, OPEN_R3, depth, select
from sailang import Record, SailangError
from sailang.frame import Batch, Profile, decode, project_batch

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = "lab/selector_coverage_manifest.json"
REGISTRATION = "lab/selector_coverage_registration.json"
FIXTURES = "lab/selector_coverage_fixtures.json"
RESULT_SCHEMA = "SELECTOR_COVERAGE_RESULT_1"
OPEN = frozenset({OPEN_R2, OPEN_R3})


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def preflight(root: Path = ROOT) -> dict:
    manifest = em.load(root / MANIFEST)
    current = em.verify_current(manifest, root=root)
    history = em.verify_historical(manifest, fixture_root=root)
    if current["verdict"] != em.CURRENT_MATCH:
        raise SailangError("V202_INPUT_DRIFT", json.dumps(current))
    if history["verdict"] != em.HISTORICAL_VERIFIED:
        raise SailangError("V202_HISTORY_MISMATCH", json.dumps(history))
    return {"current": current, "historical": history}


def policy(treatment: bool) -> postoffice.HeaderInterest:
    return postoffice.HeaderInterest.of(
        open_r3_topics={"action"}, open_r3_kinds={"WARNING"},
        ignore_topics={"noise", "ci-ok"} if treatment else {"noise"})


def expand(workload: dict) -> list[dict]:
    messages = []
    for group in workload["messages"]:
        for _ in range(group["count"]):
            messages.append({**group, "id": f'{workload["id"]}-{len(messages):03d}'})
    return messages


def _participant(identity, root: Path, treatment: bool) -> ls.Participant:
    return ls.Participant(identity=identity, root=root, interest=policy(treatment),
                          default_ttl=postoffice.MIN_TTL_SECONDS,
                          clock=lambda: ls.SCENARIO_TIME)


def _arm(messages: list[dict], containers: list, sender, receiver, root: Path,
         treatment: bool) -> dict:
    participant = _participant(receiver, root, treatment)
    peer = _participant(sender, root / "unused-peer", treatment)
    participant.connect([peer])
    deliveries = [participant.office.deliver(container) for container in containers]
    if any(item.status != postoffice.ACCEPTED for item in deliveries):
        raise AssertionError("the paired arm did not receive every frozen message")
    session = postoffice.PostOfficeSession(
        participant.office, scan_budget=len(messages), open_budget=len(messages))
    scan = session.scan(now=ls.SCENARIO_TIME)
    by_id = {item.view.envelope_id: item for item in scan.items}
    if len(by_id) != len(messages):
        raise AssertionError("the paired arm did not scan every frozen message")
    rows = []
    for message, delivery in zip(messages, deliveries, strict=True):
        item = by_id[delivery.envelope_id]
        opened = item.final_verdict in OPEN or item.final_verdict == DEFER
        if opened:
            result = session.open_message(delivery.envelope_id,
                                          recipient_private_key=receiver.recipient_key)
            if sha256(result.plaintext) != message["payload_sha256"]:
                raise AssertionError("opened content differs from the paired input")
        rows.append({"message_id": message["id"], "relevant": message["relevant"],
                     "machine_verdict": item.machine_verdict,
                     "final_verdict": item.final_verdict, "rule": item.machine_rule,
                     "opened": opened, "payload_sha256": message["payload_sha256"]})
    relevant_open = sum(row["relevant"] and row["opened"] for row in rows)
    total_open = sum(row["opened"] for row in rows)
    components = {
        "header_scan": len(rows), "full_read": total_open, "durable_write": len(rows),
        "promotion_decision": relevant_open, "attention_reservation": relevant_open,
        "attention_acknowledgement": relevant_open, "recovery_action": 0,
        "duplicate_suppressed": 0,
        "token_kunit": round((len(rows) * uf.T9B_FRAME_PROSE_RATIO
                              + total_open * uf.T9B_RECORD_PROSE_RATIO) / 1000, 6),
    }
    return {
        "messages_delivered": len(rows), "messages_scanned": len(rows),
        "messages_opened": total_open,
        "fallback_opens": sum(row["opened"] and row["machine_verdict"] == DEFER for row in rows),
        "false_ignores": sum(row["relevant"] and row["final_verdict"] == IGNORE for row in rows),
        "missed_relevant": sum(row["relevant"] and not row["opened"] for row in rows),
        "unnecessary_opens": sum(not row["relevant"] and row["opened"] for row in rows),
        "friction_components": components, "modeled_total_friction": uf._friction(components),
        "modeled_attention_events_not_executed": True,
        "sender_seals": len(rows), "sender_extra_treatment_work": 0, "rows": rows,
    }


def grade_pair(baseline: dict, treatment: dict) -> dict:
    """Grade after the independent policy scans; never feed truth to a policy."""
    if len(baseline["rows"]) != len(treatment["rows"]):
        raise ValueError("paired arms differ in length")
    new_false_ignores, new_missed, floor_downgrades = [], [], []
    for left, right in zip(baseline["rows"], treatment["rows"], strict=True):
        if any(left[key] != right[key] for key in ("message_id", "payload_sha256", "relevant")):
            raise ValueError("paired arms do not identify the same message and truth")
        if right["relevant"] and right["final_verdict"] == IGNORE and left["final_verdict"] != IGNORE:
            new_false_ignores.append(right["message_id"])
        if right["relevant"] and left["opened"] and not right["opened"]:
            new_missed.append(right["message_id"])
        if left["machine_verdict"] in OPEN and depth(right["final_verdict"]) < depth(left["machine_verdict"]):
            floor_downgrades.append(right["message_id"])
    safe = not (new_false_ignores or new_missed or floor_downgrades)
    return {"new_false_ignores": new_false_ignores, "new_missed_relevant": new_missed,
            "baseline_required_open_downgrades": floor_downgrades,
            "fallback_opens_reduced_by": baseline["fallback_opens"] - treatment["fallback_opens"],
            "unnecessary_opens_reduced_by": baseline["unnecessary_opens"] - treatment["unnecessary_opens"],
            "safe_on_fixture": safe, "modeled_utility_comparison_admissible": safe,
            "friction_delta_treatment_minus_baseline": round(
                treatment["modeled_total_friction"] - baseline["modeled_total_friction"], 4)}


def r1_control() -> dict:
    profile = Profile.load("1")
    records = [Record.create(**case.fields) for case in CASES]
    container = project_batch(records, profile).render()
    frames = Batch.parse(container, ProfileRegistry.with_profiles(profile).resolve(profile.id)).frames
    views = [decode(frame) for frame in frames]
    decisions = [select(view, INTEREST) for view in views]
    return {"scope": "unchanged current R1 corpus; not the transport-header experiment",
            "cases": len(CASES),
            "unknown_atom_fallbacks": sum(d.rule == "R2-UNKNOWN" for d in decisions),
            "opaque_claim_fallbacks": sum(d.rule == "R3-OPEN-RECORD" for d in decisions),
            "false_ignores": sum(d.verdict == IGNORE and depth(c.truth) > 0
                                 for c, d in zip(CASES, decisions, strict=True)),
            "changed_by_treatment": False}


def run_experiment(base: Path, *, root: Path = ROOT, probe: dict | None = None) -> dict:
    admission = preflight(root)
    base = Path(base)
    if base.exists() and any(base.iterdir()):
        raise ValueError("V202_NONEMPTY_WORKSPACE")
    base.mkdir(parents=True, exist_ok=True)
    fixture = json.loads((root / FIXTURES).read_text(encoding="utf-8"))
    registration = json.loads((root / REGISTRATION).read_text(encoding="utf-8"))
    if registration["friction_weights"] != uf.FRICTION_WEIGHTS:
        raise ValueError("V202_FRICTION_DRIFT")
    pairs = []
    identities = {seat: ls.identity(f"v202-{seat}", seat) for seat in ("V202A", "V202B")}
    for workload in fixture["workloads"]:
        for direction in fixture["directions"]:
            sender_seat, receiver_seat = (("V202A", "V202B") if direction == "A_TO_B"
                                          else ("V202B", "V202A"))
            sender, receiver = identities[sender_seat], identities[receiver_seat]
            messages = expand(workload)
            containers = []
            for message in messages:
                record = Record.create(KIND="F", SRC=f"AGENT:{sender_seat}",
                                       SUBJ="queue", CLAIM=message["claim"] + " " + message["id"],
                                       TYPE="OBS", EV="sha256:" + "a1" * 32,
                                       STATUS="U2", CREATED=ls.SCENARIO_TIME)
                payload = record.canonical_bytes()
                message["payload_sha256"] = sha256(payload)
                containers.append(envelope.seal(
                    record.canonical_text(), sender_private_key=sender.sender_key,
                    sender_seat=sender_seat, recipient_seat=receiver_seat,
                    recipient_public_key=receiver.recipient_key.public_key(),
                    kind=message["kind"], topic=message["topic"], created=ls.SCENARIO_TIME))
            location = base / workload["id"] / direction
            baseline = _arm(messages, containers, sender, receiver, location / "baseline", False)
            treatment = _arm(messages, containers, sender, receiver, location / "treatment", True)
            pairs.append({"workload": workload["id"], "direction": direction,
                          "paired_transport_bytes_identical": True,
                          "baseline": baseline, "treatment": treatment,
                          "comparison": grade_pair(baseline, treatment)})
    safe = all(pair["comparison"]["safe_on_fixture"] for pair in pairs)
    reduction = sum(pair["comparison"]["fallback_opens_reduced_by"] for pair in pairs)
    outcome = ("CANDIDATE_REJECTED_SAFETY" if not safe else
               "CANDIDATE_SUPPORTED_ON_FIXTURES" if reduction > 0 else "NO_REDUCTION")
    return {
        "schema": RESULT_SCHEMA, "version": 1, "status": "PASS", "outcome": outcome,
        "admission": admission, "fixture_sha256": sha256((root / FIXTURES).read_bytes()),
        "registration_sha256": sha256((root / REGISTRATION).read_bytes()),
        "pairs": pairs, "r1_control": r1_control(),
        "friction_model": {"identity": uf.FRICTION_MODEL_ID, "weights": uf.FRICTION_WEIGHTS,
                           "token_ratios_source": "unchanged FG-06/T-9B; modeled, not remeasured"},
        "setup_and_maintenance": {"receiver_policy_edits_for_two_participants": 2,
                                  "new_topic_entries_per_receiver": 1,
                                  "sender_extra_treatment_work": 0,
                                  "future_topic_review_cost": "NOT_MEASURED",
                                  "setup_cost_not_in_frozen_friction_model": True},
        "runtime": {"network_attempts": (probe or {}).get("blocked", 0),
                    "model_calls": 0, "provider_calls": 0},
        "latency": "NOT_MEASURED", "subjective_pleasantness": "NOT_MEASURED",
        "production_promotion": "NONE", "publication": "NONE",
        "interpretation": "PASS means the registered experiment completed, not that the candidate is safe",
    }


def render_report(result: dict) -> str:
    lines = ["# V2-02 selector coverage experiment", "",
             f"Experiment: {result['status']}; candidate: {result['outcome']}.", "",
             "| Workload / direction | Opens before / after | Fallback before / after | New false ignores | Required-open downgrades |",
             "|---|---:|---:|---:|---:|"]
    for pair in result["pairs"]:
        before, after, comparison = pair["baseline"], pair["treatment"], pair["comparison"]
        lines.append(f"| {pair['workload']} / {pair['direction']} | "
                     f"{before['messages_opened']} / {after['messages_opened']} | "
                     f"{before['fallback_opens']} / {after['fallback_opens']} | "
                     f"{len(comparison['new_false_ignores'])} | "
                     f"{len(comparison['baseline_required_open_downgrades'])} |")
    lines += ["", "False ignores and unnecessary opens are separate harms. Cost savings on an unsafe arm are not a utility win.",
              "Both arms receive identical sealed bytes. Both directions are reported separately.",
              "R1 unknown-atom/opaque-claim fallbacks are unchanged; this is a transport-header experiment.",
              "Two receiver setup edits and ongoing topic maintenance are outside the frozen friction scalar; maintenance, latency and subjective pleasantness are NOT_MEASURED.",
              "No production promotion, model/provider/network call, frozen-candidate rebuild or publication.", ""]
    return "\n".join(lines)
