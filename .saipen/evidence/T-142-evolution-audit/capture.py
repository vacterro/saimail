"""Append one actual current-Work metadata observation to the registered study.

No numbering/Work override, provisioning, body open, receiver decision, provider
call or canonical lifecycle command is accepted. Entry 1 and registration remain
byte-identical. Repeated Work is refused before any command executes.
"""

import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
HOST = ROOT.parent / "_SAIPEN"
BOX = Path(os.environ.get("SAIMAIL_WORKSPACE") or
           Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "saipen" / "saimail")
MEMORY = ("STATE.md", "IDENTITY.md", "BOARD.md", "LOG.md")


def verifier():
    spec = importlib.util.spec_from_file_location("t142_sequence_verifier", Path(__file__).with_name("verify.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(argv):
    started = datetime.now(UTC).isoformat()
    run = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False,
                         **({"creationflags": subprocess.CREATE_NO_WINDOW}
                            if hasattr(subprocess, "CREATE_NO_WINDOW") else {}))
    return {"argv": argv, "started": started, "exit_code": run.returncode,
            "answer": json.loads(run.stdout), "ended": datetime.now(UTC).isoformat()}


def append(path, record):
    # O_EXCL ('xb') arbitrates simultaneous writers. A partial file survives a
    # crash and makes the next validation refuse; it is never silently repaired.
    with path.open("xb") as target:
        target.write((json.dumps(record, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
        target.flush()
        os.fsync(target.fileno())


def observe():
    check = verifier()
    summary = check.sequence(OUT)
    check.require(summary["next_entry"] is not None, "registration entry_limit reached")
    registered = check.registration(OUT)
    seat = registered["observer"]["seat"]
    check.require(os.environ.get("SAIPEN_AGENT", seat) == seat, "no current authorized observer seat")
    memory = {name: (ROOT / ".saipen" / name).read_bytes() for name in MEMORY}
    snapshot = {name: memory[name].decode("utf-8") for name in ("STATE.md", "IDENTITY.md", "BOARD.md")}
    identity = check.canonical_identity(snapshot, seat)
    check.require(identity["lineage"] == summary["project_lineage"], "foreign project lineage in study")
    key = check.boundary_key(identity)
    check.require(key not in summary["boundary_keys"], "current Work/context already observed")
    log_tail = [line for line in memory["LOG.md"].decode("utf-8").splitlines() if line.startswith("- ")][-1]
    check.require(re.match(r"^- \d{2}\.\d{2}\.\d{2} \d{2}:\d{2} \[E-" + identity["last_event"] + r"\]", log_tail),
                  "canonical context last_event differs from LOG tail")
    before = {name: hashlib.sha256(value).hexdigest() for name, value in memory.items()}
    foreign_before = digest(HOST / ".saipen/STATE.md")
    retained_before = {p.name: digest(p) for p in OUT.glob("runtime*.json")}
    executable = shutil.which("saimail-local")
    check.require(executable is not None, "existing configured executable required; no provisioning")

    # Reuse the product's keyless binding and witness; no canonical continue
    # command is invoked, since routing/reconciliation can mutate memory.
    from saimail import saipen_bridge, workspace

    state_path = ROOT / ".saipen/STATE.md"
    identity_path = ROOT / ".saipen/IDENTITY.md"
    binding = saipen_bridge._admission_binding(state_path, identity_path, seat)
    headers = workspace.load_workspace_headers(BOX)
    witness = {"schema": "SAIMAIL_AGENT_CYCLE_1", "saipen": binding,
               "work": identity["work"], "scope": [], "workspace": str(BOX.resolve()),
               "recipient_kid": headers.recipient_kid, "state_path": str(state_path.resolve()),
               "identity_path": str(identity_path.resolve())}
    contract = command([executable, "--contract"])
    focus = command([executable, "--json", "saipen", "letter", "focus",
                     "--workspace", str(BOX), "--project-root", str(ROOT),
                     "--seat", seat, "--work", identity["work"], "--budget", "20"])
    after = {name: digest(ROOT / ".saipen" / name) for name in MEMORY}
    check.require(before == after, "project memory changed during observation")
    foreign_after = digest(HOST / ".saipen/STATE.md")
    check.require(foreign_before == foreign_after, "foreign SAIPEN state changed during observation")
    check.require(check.sequence(OUT) == summary and retained_before ==
                  {p.name: digest(p) for p in OUT.glob("runtime*.json")}, "retained evidence changed during observation")
    observed = focus["answer"].get("focus")
    check.require(isinstance(observed, dict) and observed.get("state") == "OK", "focus observation unavailable")
    kind = check.observation_kind(observed)
    record = {"schema": "SAIMAIL_REAL_USE_OBSERVATION_2", "study": registered["study"],
              "entry": summary["next_entry"], "actor": seat, "role": registered["observer"]["role"],
              "registration_sha256": summary["registration_sha256"], "work": identity["work"],
              "previous_observation_sha256": summary["last_observation_sha256"],
              "workspace": str(BOX.resolve()), "timestamp": datetime.now(UTC).isoformat(),
              "canonical_context": {**identity, "project_root": str(ROOT.resolve()), "log_tail": log_tail,
                                    "focus_context": observed["context"], "continuation": observed["continuation"],
                                    "focus_witness": witness}, "canonical_memory": snapshot,
              "boundary_key": key, "qualifies_context_boundary": True,
              "contract": contract, "explicit_focus": focus, "memory_before": before, "memory_after": after,
              "foreign_state_sha256": foreign_before, "foreign_state_after_sha256": foreign_after,
              "observation": kind, "eligible_receiver_opportunities": len(check.opportunities(observed)),
              "receiver_effort": "UNKNOWN_NO_RECEIVER_OPPORTUNITY" if kind == "EMPTY" else "UNKNOWN_NOT_MEASURED",
              "independent_receiver": False, "independent_successor": False,
              "independent_revision": "NOT_RUN", "successor_execution": "NOT_RUN", "field_improvement": "UNPROVEN"}
    check.validate_record(record, registered, record["entry"])
    check.require(check.timestamp(record["timestamp"]) >= check.timestamp(summary["last_observed_at"]),
                  "observation timestamp chronology precedes retained evidence")
    destination = OUT / f"runtime-{record['entry']:03d}.json"
    append(destination, record)
    check.sequence(OUT)
    return record


def main():
    result = observe()
    print(json.dumps({"entry": result["entry"], "work": result["work"], "observation": result["observation"],
                      "memory_unchanged": result["memory_before"] == result["memory_after"],
                      "field_improvement": result["field_improvement"]}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, OSError, IndexError) as exc:
        print(json.dumps({"state": "REFUSED", "reason": str(exc), "field_improvement": "UNPROVEN"}))
        raise SystemExit(1) from exc
