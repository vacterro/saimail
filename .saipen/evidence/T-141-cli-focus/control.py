"""Apply one wire-cost criterion to retained before and current replay data."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def evaluate(value):
    measurements = value["measurements"]
    cycle, focus = measurements["cycle"], measurements["focus"]
    local = measurements.get("local_focus", focus)
    checks = {
        "three_registered_repetitions": len(focus["normalized_payload_bytes"]) == 3,
        "same_two_invocations": focus["cli_invocations_per_entry"] == cycle["cli_invocations_per_entry"] == [2, 2, 2],
        "visible_context_preserved": focus["agent_visible_payload_bytes"] == local["agent_visible_payload_bytes"],
        "discovery_and_temporal_controls": all(value["checks"][key] for key in
            ("focused_discovery_preserved", "dated_feedback_preserved_with_separate_observation_times")),
        "wire_below_75_percent_of_cycle": all(f < 0.75 * c for f, c in
            zip(focus["normalized_payload_bytes"], cycle["normalized_payload_bytes"], strict=True)),
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "cycle_wire": cycle["normalized_payload_bytes"], "focus_wire": focus["normalized_payload_bytes"],
            "agent_visible": focus["agent_visible_payload_bytes"]}


before_raw = (HERE / "before-result.json").read_bytes()
output = ROOT / "lab/out/CLI_FOCUS_T141"
latest = json.loads((output / "latest.json").read_text())
after_path = output / latest["attempt"] / "result.json"
after_raw = after_path.read_bytes()
before, after = json.loads(before_raw), json.loads(after_raw)
result = {"schema": "SAIMAIL_CLI_FOCUS_COST_CONTROL_1",
          "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "before_sha256": hashlib.sha256(before_raw).hexdigest(),
          "after_path": str(after_path.relative_to(ROOT)), "after_sha256": hashlib.sha256(after_raw).hexdigest(),
          "before_subject_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in
                                    (HERE / "before-subject").glob("*.py")},
          "subject_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                             ("saimail_local.py", "saimail_host.py", "saimail/host_contract.py")},
          "before": evaluate(before), "after": evaluate(after),
          "claim_boundary": "Same fixed cost criterion over retained actual T-140 and current registered measurements; no receiver-utility or model improvement claim."}
result["status"] = "PASS" if result["before"]["status"] == "FAIL" and result["after"]["status"] == "PASS" else "FAIL"
(HERE / "control.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
raise SystemExit(0 if result["status"] == "PASS" else 1)
