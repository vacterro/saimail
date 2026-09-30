"""Evaluate retained pre-change data and a new fixed-clock view identically."""

import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from saimail import agent_cycle, workspace
from saimail_host import _focus

HERE = Path(__file__).resolve().parent
FUTURE = "2026-12-31T10:00:00Z"


def evaluate(value):
    signal = value.get("feedback_signals", {})
    checks = {
        "history_retained": value["feedback"] == [{"decision": "DEFERRED", "reason": "WAITING_DEPENDENCY",
            "count": 1, "suggestion": "WAIT_FOR_DEPENDENCY_EVIDENCE"}],
        "expired_letter_not_recruited": value["source_expired"] and value["reading"] == [],
        "temporal_basis_known": signal.get("state") == "KNOWN",
        "same_observation_time": signal.get("observed_at") == FUTURE,
        "explicit_seven_day_window": signal.get("window_start") == "2026-12-24T10:00:00Z"
            and signal.get("window_days") == 7,
        "historical_assessment_excluded": signal.get("active") == []
            and signal.get("excluded", {}).get("OUTSIDE_WINDOW") == 1,
    }
    return {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}


spec = importlib.util.spec_from_file_location("age_fixture", ROOT / "tests/test_correspondence.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
before_raw = (HERE / "baseline.json").read_bytes()
before = json.loads(before_raw)
with tempfile.TemporaryDirectory(prefix="saimail-feedback-age-control-") as temporary, pytest.MonkeyPatch.context() as patch:
    pair = fixture.setup.__wrapped__(Path(temporary), patch)
    eid = fixture.send(pair)["intent"]["envelope_id"]
    fixture.decide(pair, eid, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    _, receiver, root, letter = pair
    observed = agent_cycle.entry(workspace.load_workspace_headers(receiver.root), root / ".saipen/STATE.md",
                                 root / ".saipen/IDENTITY.md", seat="reviewer", work="T-9", clock=lambda: FUTURE)
    focused = _focus(observed, "reviewer", [])
    after = {"observed_at": FUTURE, "source_expires_at": letter["expires_at"],
             "source_expired": letter["expires_at"] <= FUTURE,
             "reading": focused["reading"], "feedback": focused["feedback"],
             "feedback_basis": focused["feedback_basis"], "feedback_signals": focused["feedback_signals"]}
    (HERE / "after.json").write_text(json.dumps(after, indent=2) + "\n", encoding="utf-8")
result = {"schema": "SAIMAIL_FEEDBACK_AGE_CONTROL_1",
          "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "after_sha256": hashlib.sha256((HERE / "after.json").read_bytes()).hexdigest(),
          "subject_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
                             ("saimail/correspondence.py", "saimail/agent_cycle.py", "saimail_host.py")},
          "before_sha256": hashlib.sha256(before_raw).hexdigest(), "before": evaluate(before), "after": evaluate(after),
          "claim_boundary": "Same fixed-clock temporal criterion over retained pre-change and current data; no field utility claim."}
result["status"] = "PASS" if result["before"]["status"] == "FAIL" and result["after"]["status"] == "PASS" else "FAIL"
(HERE / "control.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
raise SystemExit(0 if result["status"] == "PASS" else 1)
