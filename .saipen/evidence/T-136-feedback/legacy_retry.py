"""Prove an already submitted v1 result report survives a checkout update."""

import importlib.util
import json
import runpy
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from saimail import correspondence as co, letters

spec = importlib.util.spec_from_file_location("t136_fixture", ROOT / "tests/test_correspondence.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
old = runpy.run_path(str(Path(__file__).with_name("regression.py")))["OLD_REPORT"]
namespace = dict(co.__dict__)
exec(compile(old, "pre-T136-report", "exec"), namespace)

with pytest.MonkeyPatch.context() as patch:
    pair = fixture.setup.__wrapped__(Path(tempfile.mkdtemp(prefix="saimail-t136-legacy-")), patch)
    _, receiver, project, _ = pair
    envelope = fixture.send(pair)["intent"]["envelope_id"]
    fixture.decide(pair, envelope, evidence=[letters.evidence_ref(project, "result.txt")])
    first = namespace["report"](receiver, envelope, lineage=fixture.LINEAGE,
                                project_root=project, clock=fixture.CLOCK)
    again = co.report(receiver, envelope, lineage=fixture.LINEAGE,
                      project_root=project, clock=lambda: "2026-09-30T11:00:00Z")
    assert first["intent"]["envelope_id"] == again["intent"]["envelope_id"]
    result = {"schema": "SAIMAIL_T136_LEGACY_RETRY_1", "verdict": "PASS",
              "original_envelope": envelope, "report_envelope": first["intent"]["envelope_id"],
              "same_report_after_update": True, "scope": "first v1 resolution report at a later retry time"}
    Path(__file__).with_name("legacy-retry.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"same_report_after_update": True}))
