"""Operator-side replay of real Work evidence through fresh CLI hosts.

This host integration tool owns process invocation and temporary project state;
it is outside the inert protocol and laboratory packages. No provider calls or
external recipients. Decisions are scripted controls, not
model judgments. Generated identities and mutable project state stay in a
temporary directory; the output contains only constructed experiment data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import saimail_host
from saimail import letters, participants, workspace

SCHEMA = "SAIMAIL_AGENT_CYCLE_EXPERIMENT_1"
PLAN = {
    "schema": SCHEMA, "version": 4, "repetitions": 3, "network_calls": 0,
    "work_basis": "Controlled replay of actual T-137 before/after CLI race evidence",
    "baseline": ["awareness", "metrics"], "candidate": ["cycle"],
    "focus_candidate": "Negotiated compact CLI focus with independent local metadata validation",
    "local_focus_baseline": "HostClient.focus with original cycle transport",
    "compact_focus_candidate": "HostClient.focus(prefer_cli=True), negotiated cli_focus with old-peer fallback",
    "wire_hypothesis": "Compact CLI preserves agent-visible metadata with less than 75% of full-cycle wire bytes and the same two invocations.",
    "hypothesis": "One cycle returns equivalent discovery and reason feedback with fewer CLI invocations.",
    "primary_measure": "Actual CLI invocations, including fresh contract negotiation",
    "secondary_measures": ["Normalized JSON payload bytes", "Agent-visible normalized JSON bytes", "Descriptive wall time only"],
    "focus_hypothesis": "Host-owned focus preserves reading references, context, coverage and receiver feedback with fewer agent-visible bytes.",
    "temporal_comparison": "Lifetime metrics match exactly; separately sampled seven-day windows must preserve active assessments and exclusion counts. Observation times may differ.",
    "controls": ["Lost correspondence state removes reserve", "Changed result bytes fail recheck",
                 "Changed host event refuses continuation", "STALE correction removes reserve"],
    "claim_boundary": "Scripted receiver decisions and fresh CLI processes; no model, field-use or comfort claim.",
}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def worker(args):
    calls = []
    invoke = saimail_host._invoke

    def measured(argv, timeout):
        start = time.perf_counter()
        answer = invoke(argv, timeout)
        payload = json.dumps(answer.get("data", answer), sort_keys=True, separators=(",", ":")).encode()
        calls.append({"operation": "contract" if "--contract" in argv else args.action,
                      "elapsed_seconds": time.perf_counter() - start,
                      "normalized_payload_bytes": len(payload)})
        return answer

    saimail_host._invoke = measured
    host = saimail_host.HostClient([sys.executable, "-m", "saimail_local"],
                                  workspace=args.box, project_root=args.project, seat=args.seat)
    operations = PLAN["baseline"] if args.action == "baseline" else [args.action]
    data = []
    for action in operations:
        if action in {"focus", "local-focus"}:
            projection = host.focus(args.arguments, prefer_cli=action == "focus")
            answer = ({"state": "OK", "data": projection, "authority": "INFORMATION_ONLY"}
                      if projection["state"] == "OK" else projection)
        else:
            answer = host.request(action, args.arguments if action != "metrics" else [])
        data.append(answer)
    visible = sum(len(json.dumps(answer.get("data", answer), sort_keys=True, separators=(",", ":")).encode()) for answer in data)
    print(json.dumps({"calls": calls, "answers": data, "agent_visible_payload_bytes": visible}))


def run(out):
    out.mkdir(parents=True, exist_ok=True)
    if (out / "plan.json").exists() or (out / "result.json").exists():
        raise ValueError("registration already exists; preserve that trial and choose a fresh --out")
    evidence_dir = ROOT / ".saipen/evidence/T-137-cycle"
    inputs = {name: (evidence_dir / f"{name}-context.json").read_bytes() for name in ("before", "after")}
    before, after = (json.loads(inputs[name]) for name in ("before", "after"))
    if (before["verdict"] != "FAIL" or after["verdict"] != "PASS"
            or before["verifier"] != after["verifier"] or after["status"] != "SAIPEN_CONTEXT_CHANGED"):
        raise ValueError("real Work controls do not establish the registered replay")
    registration = {**PLAN, "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    "inputs": {name: hashlib.sha256(raw).hexdigest() for name, raw in inputs.items()}}
    write(out / "plan.json", registration)  # before any trial invocation
    records, checks = [], {}
    env = dict(os.environ)
    env.pop("SAIPEN_AGENT", None)  # explicit experimental seats, independent of the invoking host
    with tempfile.TemporaryDirectory(prefix="saimail-cycle-replay-") as temporary:
        scratch = Path(temporary)
        project = scratch / "project"
        memory = project / ".saipen"
        memory.mkdir(parents=True)
        lineage = "lineage-" + "d8" * 16  # experiment namespace, never the real project's authority
        state = "---\nphase: BUILD\ntask: T-137\nagent: reviewer\nlast_event: 1\n---\n"
        (memory / "STATE.md").write_text(state, encoding="utf-8")
        (memory / "IDENTITY.md").write_text(f"---\nproject_lineage: {lineage}\n---\n", encoding="utf-8")
        (memory / "BOARD.md").write_text(
            "## DOING\n- [/] T-136 [P2] replay producer | owner: builder\n"
            "- [/] T-137 [P2] replay receiver | owner: reviewer\n"
            "- [/] T-138 [P2] replay successor | owner: reviewer\n", encoding="utf-8")
        (memory / "LOG.md").write_text("# Controlled replay; no production authority\n", encoding="utf-8")
        for name, raw in inputs.items():
            (project / f"{name}.json").write_bytes(raw)
        boxes = {}
        for seat in ("builder", "reviewer"):
            workspace.init_workspace(scratch / seat, seat=seat)
            boxes[seat] = workspace.load_workspace(scratch / seat)
        for seat, peer in (("builder", "reviewer"), ("reviewer", "builder")):
            workspace.add_recipient(boxes[seat], peer, workspace.identity_card(boxes[peer]), boxes[peer].root)
            participants.admit_participant(boxes[seat], lineage, peer)

        def observe(stage, action, arguments=(), *, seat="reviewer", expected="OK"):
            command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--action", action,
                       "--box", str(boxes[seat].root), "--project", str(project), "--seat", seat,
                       "--", *arguments]
            child = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=45, check=False,
                                   **({"creationflags": subprocess.CREATE_NO_WINDOW}
                                      if hasattr(subprocess, "CREATE_NO_WINDOW") else {}))
            if child.returncode != 0:
                raise ValueError(f"host worker failed in {stage}; exit {child.returncode}")
            result = json.loads(child.stdout)
            records.append({"stage": stage, "action": action, "seat": seat, **result})
            write(out / "observations.json", records)  # retain unsuccessful evidence too
            if any(answer["state"] != expected for answer in result["answers"]):
                raise ValueError(f"unexpected host result in {stage}")
            return result if action == "baseline" else result["answers"][0].get("data", result["answers"][0])

        def dispatch(issue, *, vague=False):
            letter = letters.template(lineage, "T-136", "T-137", issue=issue)
            letter.update(
                observation="A possible problem needs attention." if vague else
                "T-137's pre-fix CLI control hid event 40->41 behind a second admission and returned OK.",
                impact="The receiver could adopt a cycle bound to a different observed Work context.",
                request="Consider improving this." if vague else "Inspect the fixed one-admission control and recheck its named refusal.",
                done_when="Receiver determines completion." if vague else
                "The same control returns SAIPEN_CONTEXT_CHANGED, exit 1 and exactly one admission event.",
                uncertainty="Actual mechanical Work evidence; this replay has scripted decisions and no model judgment.",
                evidence=[letters.evidence_ref(project, "before.json")], scope=["saimail_local.py"])
            path = project / f"{issue}.json"
            write(path, letter)
            # Each simulated host owns its actual sender Work at dispatch.
            current_state = (memory / "STATE.md").read_bytes()
            (memory / "STATE.md").write_text(
                state.replace("task: T-137", "task: T-136").replace("agent: reviewer", "agent: builder"), encoding="utf-8")
            try:
                sent = observe(issue, "dispatch", ["--letter", str(path), "--to", "reviewer"], seat="builder")
            finally:
                (memory / "STATE.md").write_bytes(current_state)
            return sent["intent"]["envelope_id"]

        eid = dispatch("actual-context-race")
        query = ["--work", "T-137", "--scope", "saimail_local.py", "--budget", "20"]
        baseline, candidate, focused_rows, local_rows = [], [], [], []
        for n in range(PLAN["repetitions"]):
            # Alternate order to reduce a fixed startup/cache advantage.
            order = (("baseline", "cycle", "local-focus", "focus"),
                     ("focus", "local-focus", "cycle", "baseline"),
                     ("cycle", "focus", "baseline", "local-focus"))[n]
            paired = {action: observe(f"entry-{n}-{action}", action, query) for action in order}
            separate = paired["baseline"]["answers"]
            combined = paired["cycle"]
            focused = paired["focus"]
            local = paired["local-focus"]
            for key in ("reading", "host", "context", "coverage", "continuation", "decisions", "feedback", "next_action"):
                if focused[key] != local[key]:
                    raise ValueError(f"compact focus changed agent metadata: {key}")
            for key in ("items", "cases", "complete", "complete_from_start"):
                if separate[0]["data"][key] != combined["desk"][key]:
                    raise ValueError(f"discovery mismatch: {key}")
            separate_metrics = separate[1]["data"]["metrics"]
            if ({key: value for key, value in separate_metrics.items() if key != "feedback_signals"}
                    != {key: value for key, value in combined["metrics"].items() if key != "feedback_signals"}):
                raise ValueError("receiver metrics mismatch")
            separate_signals = separate_metrics["feedback_signals"]
            cycle_signals = combined["metrics"]["feedback_signals"]
            focus_signals = focused["feedback_signals"]
            if (focus_signals["state"] != "KNOWN" or any(
                    separate_signals[key] != cycle_signals[key] or cycle_signals[key] != focus_signals[key]
                    for key in ("active", "excluded", "basis", "window_days"))):
                raise ValueError("dated feedback mismatch")
            for signal in (separate_signals, cycle_signals, focus_signals):
                if (saimail_host._instant(signal["observed_at"]) - saimail_host._instant(signal["window_start"])
                        != timedelta(days=7)):
                    raise ValueError("feedback observation window mismatch")
            if (focused["reading"] != [{"envelope_id": row["envelope_id"], "reason": row["reason"]}
                                      for row in combined["cycle"]["actions"]]
                    or focused["context"] != combined["cycle"]["context"]
                    or focused["continuation"] != combined["cycle"]["continuation"]
                    or focused["coverage"]["complete"] != combined["cycle"]["complete"]
                    or focused["coverage"]["complete_from_start"] != combined["cycle"]["complete_from_start"]
                    or focused["decisions"] != combined["metrics"]["decisions"]):
                raise ValueError("focus lost discovery, coverage or receiver feedback")
            baseline.append(next(row for row in reversed(records) if row["stage"] == f"entry-{n}-baseline"))
            candidate.append(next(row for row in reversed(records) if row["stage"] == f"entry-{n}-cycle"))
            focused_rows.append(next(row for row in reversed(records) if row["stage"] == f"entry-{n}-focus"))
            local_rows.append(next(row for row in reversed(records) if row["stage"] == f"entry-{n}-local-focus"))
        checks["equivalent_keyless_observation"] = True
        checks["focused_discovery_preserved"] = True
        checks["dated_feedback_preserved_with_separate_observation_times"] = True
        checks["compact_metadata_matches_original_projection"] = True
        opened = observe("explicit-first-review", "review", ["--envelope", eid])
        checks["review_is_pending"] = opened["case"]["decision"] == "PENDING"
        observe("defer", "decision", ["--envelope", eid, "--decision", "DEFERRED", "--reason", "WAITING_DEPENDENCY"])
        deferred = observe("report-defer", "report", ["--envelope", eid])
        feedback = observe("fresh-sender-feedback", "review", ["--envelope", deferred["intent"]["envelope_id"]], seat="builder")
        checks["sealed_deferred_feedback"] = "DEFERRED/WAITING_DEPENDENCY" in feedback["letter"]["observation"]

        vague = dispatch("vague-request", vague=True)
        observe("decline-vague", "decision", ["--envelope", vague, "--decision", "DECLINED", "--reason", "NOT_ACTIONABLE"])
        negative = observe("report-decline", "report", ["--envelope", vague])
        received = observe("fresh-sender-negative", "review", ["--envelope", negative["intent"]["envelope_id"]], seat="builder")
        checks["sealed_negative_feedback"] = "DECLINED/NOT_ACTIONABLE" in received["letter"]["observation"]
        focused_feedback = observe("focused-receiver-feedback", "focus", query)
        checks["focused_negative_and_deferred_feedback"] = {
            row["reason"] for row in focused_feedback["feedback"]} == {"WAITING_DEPENDENCY", "NOT_ACTIONABLE"}
        adapted = dispatch("clarified-request")
        clarified = observe("review-clarified", "review", ["--envelope", adapted])
        observe("accept-clarified", "decision", ["--envelope", adapted, "--decision", "ACCEPTED", "--reason", "ACTION_PLANNED"])
        checks["scripted_sender_adaptation"] = clarified["letter"]["done_when"] != received["letter"]["done_when"]

        page = observe("partial-page", "cycle", ["--work", "T-137", "--budget", "1"])
        token = page["cycle"]["continuation"]
        if token is None:
            raise ValueError("context control requires a partial page")
        (memory / "STATE.md").write_text(state.replace("last_event: 1", "last_event: 2"), encoding="utf-8")
        refused = observe("changed-host-context", "cycle", ["--work", "T-137", "--budget", "1", "--continuation", token], expected="DEGRADED")
        checks["changed_context_refused"] = refused["code"] == "SAIPEN_CONTEXT_CHANGED"
        focused_refusal = observe("focused-changed-host-context", "focus", ["--work", "T-137", "--budget", "1", "--continuation", token], expected="DEGRADED")
        checks["focused_changed_context_refused"] = focused_refusal["code"] == "SAIPEN_CONTEXT_CHANGED"
        (memory / "STATE.md").write_text(state, encoding="utf-8")

        resolved = observe("resolve", "decision", ["--envelope", eid, "--decision", "RESOLVED", "--reason", "ACTION_TAKEN", "--result", "after.json"])
        observe("retain", "retain", ["--envelope", eid])
        report = observe("report-resolution", "report", ["--envelope", eid])
        retry = observe("retry-resolution", "report", ["--envelope", eid])
        checks["resolution_retry_idempotent"] = report["intent"]["envelope_id"] == retry["intent"]["envelope_id"]
        checks["resolution_history_preserved"] = [row["decision"] for row in resolved["history"]] == ["DEFERRED", "RESOLVED"]
        successor_query = ["--work", "T-138", "--scope", "saimail_local.py"]
        successor = observe("fresh-successor", "cycle", successor_query)
        checks["fresh_successor_discovers_reserve"] = any(
            row["envelope_id"] == eid and row["reason"] == "SUCCESSOR_RESERVE" for row in successor["cycle"]["actions"])
        successor_focus = observe("focused-fresh-successor", "focus", successor_query)
        checks["focused_successor_preserves_reserve"] = successor_focus["reading"] == [
            {"envelope_id": row["envelope_id"], "reason": row["reason"]} for row in successor["cycle"]["actions"]]
        rechecked = observe("successor-result-recheck", "review", ["--envelope", eid])
        checks["fresh_successor_rechecks_actual_result"] = rechecked["result_current"]
        db = boxes["reviewer"].root / "correspondence.sqlite3"
        held = db.with_suffix(".held")
        db.rename(held)
        try:
            lost = observe("lost-state-control", "cycle", successor_query)
            checks["lost_state_does_not_invent_reserve"] = not lost["cycle"]["actions"] and not db.exists()
            focused_lost = observe("focused-lost-state-control", "focus", successor_query)
            checks["focused_lost_state_preserved"] = not focused_lost["reading"] and not db.exists()
        finally:
            held.rename(db)
        (project / "after.json").write_bytes(inputs["after"] + b"\n")
        changed = observe("changed-result-control", "review", ["--envelope", eid])
        checks["changed_result_detected"] = not changed["result_current"] and changed["result_evidence"][0]["state"] == "CHANGED"
        observe("stale-correction", "decision", ["--envelope", eid, "--decision", "STALE", "--reason", "EVIDENCE_CHANGED", "--revise"])
        stale_report = observe("report-stale", "report", ["--envelope", eid])
        stale = observe("successor-after-stale", "cycle", successor_query)
        checks["stale_correction_removes_reserve"] = not stale["cycle"]["actions"]
        focused_stale = observe("focused-successor-after-stale", "focus", successor_query)
        checks["focused_stale_correction_preserved"] = not focused_stale["reading"] and any(
            row["reason"] == "EVIDENCE_CHANGED" for row in focused_stale["feedback"])
        checks["correction_has_distinct_reply"] = stale_report["intent"]["envelope_id"] != report["intent"]["envelope_id"]

        def summary(rows):
            return {"cli_invocations_per_entry": [len(row["calls"]) for row in rows],
                    "normalized_payload_bytes": [sum(call["normalized_payload_bytes"] for call in row["calls"]) for row in rows],
                    "agent_visible_payload_bytes": [row["agent_visible_payload_bytes"] for row in rows],
                    "median_cli_seconds": statistics.median(sum(call["elapsed_seconds"] for call in row["calls"]) for row in rows)}

        metrics = {"baseline": summary(baseline), "cycle": summary(candidate),
                   "local_focus": summary(local_rows), "focus": summary(focused_rows)}
        checks["fewer_cli_invocations"] = all(
            len(c["calls"]) < len(b["calls"]) for b, c in zip(baseline, candidate, strict=True))
        checks["focus_reduces_agent_context"] = all(
            f["agent_visible_payload_bytes"] < c["agent_visible_payload_bytes"]
            for f, c in zip(focused_rows, candidate, strict=True))
        checks["focus_keeps_cycle_invocation_count"] = all(
            len(f["calls"]) == len(c["calls"]) for f, c in zip(focused_rows, candidate, strict=True))
        checks["compact_focus_reduces_wire_bytes"] = all(
            sum(call["normalized_payload_bytes"] for call in f["calls"])
            < 0.75 * sum(call["normalized_payload_bytes"] for call in c["calls"])
            for f, c in zip(focused_rows, candidate, strict=True))
        checks["compact_focus_preserves_visible_bytes"] = all(
            f["agent_visible_payload_bytes"] == local["agent_visible_payload_bytes"]
            for f, local in zip(focused_rows, local_rows, strict=True))
        result = {"schema": SCHEMA, "status": "PASS" if all(checks.values()) else "FAIL",
                  "checks": checks, "measurements": metrics, "claim_boundary": PLAN["claim_boundary"],
                  "limitations": ["Three repetitions on one Windows checkout", "Payload bytes are normalized JSON, not model tokens",
                                  "Latency includes local startup/cache variation", "Receiver and sender choices are scripted",
                                  "Broader autonomous improvement and real-session usefulness remain unproven"]}
        write(out / "result.json", result)
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "PASS" else 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--action")
    parser.add_argument("--box")
    parser.add_argument("--project")
    parser.add_argument("--seat")
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.arguments[:1] == ["--"]:
        args.arguments = args.arguments[1:]
    if args.worker:
        worker(args)
        return 0
    if args.out is None:
        parser.error("--out is required")
    root = args.out.resolve()
    root.mkdir(parents=True, exist_ok=True)
    number = 1
    while (root / f"attempt-{number:03d}").exists():
        number += 1
    attempt = root / f"attempt-{number:03d}"
    try:
        code = run(attempt)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        write(attempt / "result.json", {"schema": SCHEMA, "status": "FAIL", "error_class": type(exc).__name__,
                                      "reason": "Trial interrupted; inspect preserved observations and registration."})
        write(root / "latest.json", {"attempt": attempt.name, "status": "FAIL"})
        raise
    write(root / "latest.json", {"attempt": attempt.name, "status": "PASS" if code == 0 else "FAIL"})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
