"""Compare the final oracle with restored pre-T-136 behavior in an isolated copy."""

import ast
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
COMMAND = [sys.executable, "-m", "pytest", "-q", "tests/test_correspondence.py",
           "tests/test_saipen_work_desk.py", "tests/test_host_client.py", "--tb=short"]
TESTS = COMMAND[4:7]
SUBJECTS = ["saimail/correspondence.py", "saimail/saipen_bridge.py"]

# These function sources were read before T-136 via graph snippets and direct
# source fallback. Restore the implementation, not a changed expectation/mock.
OLD_REPORT = '''def report(workspace, envelope_id, *, lineage, project_root, clock=None):
    """Send a resolved result back to its authenticated sender, once per letter.

    Receiver result evidence, not delivery/open status, closes the information
    loop. The receiving host still decides what to do with that evidence.
    """
    reviewed = review(workspace, envelope_id, lineage=lineage, project_root=project_root, clock=clock)
    with _db(workspace) as db:
        case = db.execute("SELECT * FROM cases WHERE envelope_id=?", (envelope_id,)).fetchone()
        if case["decision"] != "RESOLVED":
            _reject(LETTER_DECISION_INVALID, "report requires an evidence-backed receiver resolution")
        event = db.execute("SELECT evidence FROM events WHERE envelope_id=? AND decision='RESOLVED' "
                           "ORDER BY id DESC LIMIT 1", (envelope_id,)).fetchone()
    original = reviewed["letter"]
    response = letters.template(lineage, original["recipient_work"], original["sender_work"],
                                trigger="reply", issue="result-" + envelope_id.split(":")[1][:32],
                                clock=clock)
    response.update(
        observation="The receiver recorded ACTION_TAKEN for " + envelope_id,
        impact="The original sender can inspect the resulting artifact before repeating or depending on this work.",
        request="Check the result evidence against the original completion criterion carried in this result letter.",
        done_when=original["done_when"],
        uncertainty="A receiver-reported outcome and matching artifact bytes do not prove the claim is true.",
        evidence=json.loads(event["evidence"]), scope=original["scope"], in_reply_to=envelope_id)
    with _db(workspace) as db:
        at = db.execute("SELECT at FROM events WHERE envelope_id=? AND decision='RESOLVED' "
                        "ORDER BY id DESC LIMIT 1", (envelope_id,)).fetchone()[0]
    response["expires_at"] = letters.template(
        lineage, response["sender_work"], response["recipient_work"], clock=lambda: at)["expires_at"]
    result = dispatch(workspace, response, lineage=lineage, sender_work=response["sender_work"],
                      to_seat=case["sender"], project_root=project_root, clock=clock)
    result["command"] = "letter-report"
    return result
'''
OLD_METRICS = '''def metrics(workspace, *, lineage):
    """Actual receiver dispositions, never delivery counts called improvement."""
    participants._check_lineage(lineage)
    counts = {state: 0 for state in sorted(DECISIONS | {"PENDING"})}
    retained = 0
    with _db(workspace) as db:
        if db is not None:
            for row in db.execute("SELECT decision, COUNT(*) AS n FROM cases WHERE lineage=? GROUP BY decision",
                                  (lineage,)):
                if row["decision"] not in counts:
                    _reject(CORRESPONDENCE_CORRUPT, "invalid receiver disposition")
                counts[row["decision"]] = row["n"]
            retained = db.execute("SELECT COUNT(*) FROM cases WHERE lineage=? AND retained=1",
                                  (lineage,)).fetchone()[0]
    total = sum(counts.values())
    return ws.command_result("letter-metrics", "OK", workspace=workspace,
                             metrics={"reviewed": total, "decisions": counts, "retained": retained,
                                      "resolved_fraction": counts["RESOLVED"] / total if total else None,
                                      "basis": "EXPLICIT_RECEIVER_DECISIONS", "model_improvement_proven": False},
                             detail="receiver-recorded outcomes; no claim about model intelligence or universal utility")
'''


def replace_function(source, name, restored):
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
    lines = source.splitlines(keepends=True)
    return "".join(lines[:node.lineno - 1]) + restored + "".join(lines[node.end_lineno:])


def hashes(base, paths):
    return {p: hashlib.sha256((base / p).read_bytes()).hexdigest() for p in paths}


def run(base, label):
    result = subprocess.run(COMMAND, cwd=base, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=120,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    (OUT / (label + "-output.txt")).write_text(result.stdout + result.stderr, encoding="utf-8")
    return {"exit_code": result.returncode, "subject_files": hashes(base, SUBJECTS),
            "verifier_files": hashes(base, TESTS)}


def main():
    sandbox = Path(tempfile.mkdtemp(prefix="saimail-t136-regression-"))
    for package in ("saimail", "sailang", "lab"):
        shutil.copytree(ROOT / package, sandbox / package,
                        ignore=shutil.ignore_patterns("__pycache__", "out", "analysis"))
    for module in ("saimail_local.py", "saimail_host.py", "saimail_project.py"):
        shutil.copyfile(ROOT / module, sandbox / module)
    (sandbox / "tests").mkdir()
    for path in TESTS:
        shutil.copyfile(ROOT / path, sandbox / path)
    good = run(sandbox, "after")
    if good["exit_code"] != 0:
        raise SystemExit("isolated current implementation failed; no baseline classification")
    source = (sandbox / SUBJECTS[0]).read_text(encoding="utf-8")
    source = replace_function(source, "report", OLD_REPORT)
    source = replace_function(source, "metrics", OLD_METRICS)
    (sandbox / SUBJECTS[0]).write_text(source, encoding="utf-8")
    source = (sandbox / SUBJECTS[1]).read_text(encoding="utf-8")
    old_relation = 'relation = "current_topic" if current_topic and item["topic"] == current_topic else "other_topics"'
    new_relation = 'relation = "current_topic" if item["topic"] in work_topics else "other_topics"'
    assert source.count(new_relation) == 1
    (sandbox / SUBJECTS[1]).write_text(source.replace(new_relation, old_relation), encoding="utf-8")
    bad = run(sandbox, "before")
    same_oracle = bad["verifier_files"] == good["verifier_files"]
    result = {"schema": "SAIMAIL_T136_REGRESSION_1", "python": sys.version.split()[0],
              "pytest": pytest.__version__, "command": COMMAND[1:], "before": bad, "after": good,
              "same_oracle": same_oracle, "baseline": "restored pre-T136 report, metrics and brief association",
              "scope": "behavior restoration in isolated copy; unused additive metadata is preserved"}
    (OUT / "regression.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"before_exit": bad["exit_code"], "after_exit": good["exit_code"],
                      "same_oracle": same_oracle}))
    if not same_oracle or bad["exit_code"] == 0:
        raise SystemExit("restored implementation did not fail the unchanged oracle")


if __name__ == "__main__":
    main()
