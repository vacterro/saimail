"""Check the retained laboratory run's accounting and claim boundaries."""

import copy
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ARTIFACT = ROOT / "lab/out/SAIFREN_T145/saifren_live_20260930T125211Z_b9d3f9d3fd22479c.json"


def check(run):
    failures = []
    if run["authority"] != "EXPERIMENT_DATA" or run["dry_run"] is not False:
        failures.append("live experiment authority missing")
    if not (run["max_runs"] == 14 and run["live_calls"] <= run["max_runs"]
            and run["live_calls"] == run["discovery_calls"] + run["experiment_calls"]):
        failures.append("bounded call accounting differs")
    if (run["planned_calls"] != 6 or run["experiment_calls"] != 6
            or len(run["calls"]) != 6 or any(c["status"] != "OK" for c in run["calls"])):
        failures.append("sample did not complete its six calls")
    if [u["unit_id"] for u in run["units"]] != ["S2.chain1", "S3.mailbox", "S5.trial1"]:
        failures.append("preregistered sample changed")
    counted = Counter(u["verdict"] for u in run["units"])
    if any(run["summary"]["verdicts"][k] != counted[k] for k in run["summary"]["verdicts"]):
        failures.append("summary verdicts differ from unit evidence")
    classification = run["experiment_class"]
    if (classification["experiment_class"] != "SAIFREN_EXTERNAL_COMPARATOR"
            or classification["cross_member_claim"] is not False
            or classification["observed_combo_members"] != ["stealth/space-bunny-alpha"]
            or classification["external_comparators"] != ["gemini-3-flash"]):
        failures.append("comparator incorrectly counted as combo member")
    if run["context_visibility"] != "OPAQUE" or run.get("field_improvement", "UNPROVEN") != "UNPROVEN":
        failures.append("unknown context or unsupported field claim hidden")
    return failures


def main():
    run = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    failures = check(run)
    controls = []
    for name in ("budget", "summary", "membership", "field_claim"):
        bad = copy.deepcopy(run)
        if name == "budget":
            bad["max_runs"] = run["live_calls"] - 1
        elif name == "summary":
            bad["summary"]["verdicts"]["PASS"] += 1
        elif name == "membership":
            bad["experiment_class"]["cross_member_claim"] = True
        else:
            bad["field_improvement"] = "PROVEN"
        refused = check(bad)
        controls.append({"name": name, "rejected": bool(refused), "failures": refused})
        if not refused:
            failures.append("negative control accepted: " + name)
    result = {"state": "FAIL" if failures else "PASS", "failures": failures,
              "known_bad_controls": controls, "live_calls": run["live_calls"],
              "verdicts": run["summary"]["verdicts"], "field_improvement": "UNPROVEN"}
    print(json.dumps(result))
    return int(bool(failures))


if __name__ == "__main__":
    raise SystemExit(main())
