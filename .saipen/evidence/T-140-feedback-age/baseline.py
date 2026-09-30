"""Record undated historical feedback after its source letter has expired."""

import hashlib
import importlib.util
import inspect
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from saimail import agent_cycle, correspondence, letters, workspace
from saimail_host import _focus

spec = importlib.util.spec_from_file_location("age_fixture", ROOT / "tests/test_correspondence.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
future = "2026-12-31T10:00:00Z"
with tempfile.TemporaryDirectory(prefix="saimail-feedback-age-") as temporary, pytest.MonkeyPatch.context() as patch:
    pair = fixture.setup.__wrapped__(Path(temporary), patch)
    eid = fixture.send(pair)["intent"]["envelope_id"]
    fixture.decide(pair, eid, decision="DEFERRED", reason="WAITING_DEPENDENCY")
    _, receiver, root, letter = pair
    observed = agent_cycle.entry(workspace.load_workspace_headers(receiver.root), root / ".saipen/STATE.md",
                                 root / ".saipen/IDENTITY.md", seat="reviewer", work="T-9", clock=lambda: future)
    focused = _focus(observed, "reviewer", ["--work", "T-9"])
    result = {"schema": "SAIMAIL_FEEDBACK_AGE_BASELINE_1", "experiment": "CONTROLLED_FUTURE_CLOCK",
              "observed_at": future, "source_expires_at": letter["expires_at"],
              "source_expired": letters.is_expired(letter, future), "reading": focused["reading"],
              "feedback": focused["feedback"], "feedback_basis": focused["feedback_basis"],
              "metrics_source_sha256": hashlib.sha256(inspect.getsource(correspondence.metrics).encode()).hexdigest(),
              "claim_boundary": "Historical assessment is retained correctly, but this view cannot distinguish its age or current eligibility."}
Path(__file__).with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
