"""Check the audit's recorded boundaries; this does not grade field utility."""

import argparse
import copy
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
HOST = ROOT.parent / "_SAIPEN"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def boundaries(record, registration):
    failures = []
    if record["registration_sha256"] != sha(OUT / "registration.json"):
        failures.append("registration changed after observation")
    if record["memory_before"] != record["memory_after"]:
        failures.append("project memory changed during observation")
    if any(record[name]["exit_code"] != 0
           for name in ("contract", "canonical_entry", "explicit_focus")):
        failures.append("recorded configured command did not succeed")
    focus = record["explicit_focus"]["answer"]["focus"]
    if focus["state"] != "OK" or focus["work"] != "T-142" or focus["host"]["task"] != "T-142":
        failures.append("observation is not current recorded Work")
    if record["observation"] == "EMPTY" and (
            focus["reading"] or focus["reviewed"]
            or focus["coverage"]["complete_from_start"] is not True):
        failures.append("incomplete or nonempty observation claimed empty")
    if (record["field_improvement"] != "UNPROVEN"
            or record["independent_receiver"] or record["independent_successor"]
            or any(value != "NOT_ENROLLED" for value in registration["roles"].values())):
        failures.append("unavailable independent behavior claimed as established")
    return failures


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, choices=("verify.json", "review.json"))
    args = parser.parse_args()
    target = OUT / args.out
    if target.exists():
        raise SystemExit("Existing verification retained; do not overwrite it.")
    record = json.loads((OUT / "runtime.json").read_text(encoding="utf-8"))
    registration = json.loads((OUT / "registration.json").read_text(encoding="utf-8"))
    failures = boundaries(record, registration)
    sources = json.loads((OUT / "sources.json").read_text(encoding="utf-8"))
    for group, root in (("local", ROOT), ("foreign", HOST)):
        for name, expected in sources[group].items():
            if sha(root / name) != expected:
                failures.append("current source changed; re-inspect " + group + ":" + name)
    audit = (ROOT / "humbox/EVOLUTION-AUDIT.md").read_text(encoding="utf-8")
    ids = re.findall(r"^\| (R\d+) \|", audit, flags=re.MULTILINE)
    if ids != ["R" + str(i) for i in range(1, 13)]:
        failures.append("audit matrix rows missing or duplicated")
    suites = ET.parse(ROOT / ".saipen/evidence/T-141-cli-focus/full.xml").getroot()
    inherited = [dict(suite.attrib) for suite in suites.iter("testsuite")]
    if sum(int(s["tests"]) for s in inherited) != 2824 or any(
            int(s[k]) for s in inherited for k in ("failures", "errors", "skipped")):
        failures.append("inherited T-141 suite evidence differs from documentation")
    controls = {}
    for name in ("unsupported_field_claim", "invented_independent_actor", "false_empty_coverage"):
        bad = copy.deepcopy(record)
        if name == "unsupported_field_claim":
            bad["field_improvement"] = "PROVEN"
        elif name == "invented_independent_actor":
            bad["independent_successor"] = True
        else:
            bad["explicit_focus"]["answer"]["focus"]["coverage"]["complete_from_start"] = False
        refused = boundaries(bad, registration)
        controls[name] = {"rejected": bool(refused), "failures": refused}
        if not refused:
            failures.append("known-bad control not detected: " + name)
    result = {"schema": "SAIMAIL_EVOLUTION_AUDIT_CHECK_1", "state": "FAIL" if failures else "PASS",
              "failures": failures, "matrix_rows": ids, "inherited_suite": inherited,
              "known_bad_controls": controls, "verifier_sha256": sha(Path(__file__)),
              "runtime_sha256": sha(OUT / "runtime.json"), "audit_sha256": sha(ROOT / "humbox/EVOLUTION-AUDIT.md"),
              "claim_boundary": "Record consistency and source freshness; matrix semantics require source review; no field utility verdict"}
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"state": result["state"], "failures": failures,
                      "matrix_rows": len(ids), "rejected_controls": len(controls),
                      "inherited_tests": sum(int(s["tests"]) for s in inherited)}))
    raise SystemExit(bool(failures))


if __name__ == "__main__":
    main()
