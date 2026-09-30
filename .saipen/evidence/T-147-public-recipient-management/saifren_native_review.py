"""Bounded two-stage native SAIFREN product review; never study mail or enrollment.

Reasoning events, raw provider error text and credentials are never persisted.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
EXECUTABLE = Path("C:/nodejs/node_modules/opencode-ai/bin/opencode.exe")
MODEL = "sairoute/SAIFREN"


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(value, target, indent=2, ensure_ascii=True)
        target.write("\n")


def run(context, prompt, *, session=None):
    argv = [str(EXECUTABLE), "run", "--agent", "plan", "--model", MODEL,
            "--format", "json", "--dir", context["workspace"], "--title", "SAIMAIL T147 independent product review"]
    if session:
        argv += ["--session", session]
    argv.append(prompt)
    started = datetime.now(UTC).isoformat()
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               encoding="utf-8", errors="replace",
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                               **({"creationflags": subprocess.CREATE_NO_WINDOW}
                                  if hasattr(subprocess, "CREATE_NO_WINDOW") else {}))
    timed_out = False
    try:
        stdout, _stderr = process.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        timed_out = True
        process.kill()
        stdout, _stderr = process.communicate()
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except (ValueError, TypeError):
            continue
        part = event.get("part") or {}
        public = {"type": event.get("type"), "sessionID": event.get("sessionID")}
        if event.get("type") == "text":
            public["text"] = part.get("text", "")
        elif event.get("type") in ("step_start", "step_finish"):
            public.update({k: part.get(k) for k in ("reason", "tokens", "cost") if k in part})
        elif event.get("type") == "tool_use":
            public.update(tool=part.get("tool"), status=(part.get("state") or {}).get("status"))
        elif event.get("type") == "error":
            public["error_observed"] = True
        else:
            continue
        events.append(public)
    sessions = sorted({e["sessionID"] for e in events if isinstance(e.get("sessionID"), str)})
    return {"started": started, "ended": datetime.now(UTC).isoformat(),
            "pid": process.pid, "exit_code": process.returncode, "timed_out": timed_out,
            "model_route_requested": MODEL, "provider_context": "OPAQUE",
            "sessions": sessions, "events": events,
            "raw_reasoning_and_errors_retained": False,
            "transcript_available": bool(events)}


def main():
    if sys.argv[1] == "baseline":
        folder = Path(tempfile.mkdtemp(prefix="saimail-T147-SAIFREN-"))
        config = {"$schema": "https://opencode.ai/config.json",
                  "agent": {"plan": {"steps": 6, "permission": {
                      "*": "deny", "read": "allow", "glob": "allow", "grep": "allow",
                      "list": "allow", "edit": "deny", "bash": "deny", "task": "deny",
                      "external_directory": "deny"}}}}
        write_new(folder / "opencode.json", config)
        context = {"schema": "T147_NATIVE_REVIEW_CONTEXT_1", "created": datetime.now(UTC).isoformat(),
                   "workspace": str(folder), "work": "T-147", "authorization": ["SRC-112", "SRC-113"],
                   "purpose": "Independent product review; not an eligible-letter study observation",
                   "source_evidence_supplied": False, "prior_root_chat_supplied": False,
                   "native_session_required_before_source": True, "steps_per_invocation": 6,
                   "timeout_per_invocation_seconds": 180, "max_invocations": 2}
        write_new(OUT / "native-context.json", context)
        prompt = ("You are an independent reviewer of actual SAIMAIL product Work T-147. "
                  "No predecessor conversation or source evidence has been supplied. "
                  "Before any evidence exposure, declare your review scope, comparable effort boundary, "
                  "and criteria for acceptance, requesting changes, or unavailable evidence. "
                  "Do not use tools yet. Do not infer a verdict. Keep this baseline declaration concise.")
        answer = run(context, prompt)
        write_new(OUT / "native-baseline.json", answer)
    else:
        context = json.loads((OUT / "native-context.json").read_text(encoding="utf-8"))
        baseline = json.loads((OUT / "native-baseline.json").read_text(encoding="utf-8"))
        if baseline["exit_code"] or baseline["timed_out"] or len(baseline["sessions"]) != 1:
            raise ValueError("actual native baseline/session unavailable; no source exposure")
        if not any(e.get("text") for e in baseline["events"]):
            raise ValueError("no declared baseline before source")
        folder = Path(context["workspace"])
        files = ["saimail_local.py", "saimail/workspace.py", "tests/test_public_recipient_management.py",
                 "spec/17-LOCAL-WORKSPACE-v0.md"]
        manifest = {"created": datetime.now(UTC).isoformat(), "native_session": baseline["sessions"][0],
                    "source_hashes": {}, "prior_root_chat_supplied": False,
                    "prior_review_verdicts_or_test_results_supplied": False,
                    "role": "INDEPENDENT_PRODUCT_REVIEWER_NOT_STUDY_RECEIVER",
                    "study_enrolled": False, "study_observation_created": False}
        for name in files:
            data = (ROOT / name).read_bytes()
            path = folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as target:
                target.write(data)
            manifest["source_hashes"][name] = hashlib.sha256(data).hexdigest()
        write_new(OUT / "native-source-manifest.json", manifest)
        prompt = ("Apply your previously declared baseline independently to the real T-147 evidence now in "
                  "saimail_local.py, saimail/workspace.py, tests/test_public_recipient_management.py and "
                  "spec/17-LOCAL-WORKSPACE-v0.md. The change concerns only public recipient list/add: "
                  "public workspace loading and structured identity-card read errors. Read the actual files. "
                  "Decide for yourself whether behavior is correct, and report any concrete defect with "
                  "file/line, trigger and reason. No source writes, shell commands, delegation, provider calls "
                  "or enrolling peers. Do not assume any test outcome. Report unavailable evidence honestly. "
                  "Give your disposition and actual evidence inspected; findings are welcome, acceptance "
                  "is not required. This product review is not field-improvement evidence.")
        answer = run(context, prompt, session=baseline["sessions"][0])
        write_new(OUT / "native-review.json", answer)
    print(json.dumps({"exit_code": answer["exit_code"], "timed_out": answer["timed_out"],
                      "sessions": answer["sessions"], "transcript_available": answer["transcript_available"]}))
    for event in answer["events"]:
        if "text" in event:
            print(event["text"][:6000])


if __name__ == "__main__":
    main()
