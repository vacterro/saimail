"""The unchanged isolation oracle rejects host effects owned by the lab."""

import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
source = ROOT / "tests/test_lab_contract.py"
spec = importlib.util.spec_from_file_location("original_lab_guard", source)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
guard = module.test_the_lab_is_isolated_from_the_protocol_code
result = {"schema": "SAIMAIL_T139_ISOLATION_CONTROL_1",
          "verifier_sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
with tempfile.TemporaryDirectory(prefix="saimail-isolation-control-") as temporary:
    trial = Path(temporary)
    (trial / "lab").mkdir()
    # The identical protocol source is present in both controls.
    for package in ("sailang", "saimail"):
        (trial / package).mkdir()
        for path in (ROOT / package).glob("*.py"):
            (trial / package / path.name).write_bytes(path.read_bytes())
    sample = trial / "lab/agent_cycle_run.py"
    host_source = (ROOT / "tools/agent_cycle_replay.py").read_bytes()
    sample.write_bytes(host_source)
    module.ROOT = trial
    try:
        guard()
        result["host_effects_in_lab"] = "PASS"
    except AssertionError:
        result["host_effects_in_lab"] = "FAIL"
    (trial / "tools").mkdir()
    (trial / "tools/agent_cycle_replay.py").write_bytes(host_source)
    sample.write_bytes((ROOT / "lab/agent_cycle_run.py").read_bytes())
    guard()
    result["host_effects_in_operator_tool"] = "PASS"
    result["verifier_unchanged"] = hashlib.sha256(source.read_bytes()).hexdigest() == result["verifier_sha256"]
result["status"] = ("PASS" if result["host_effects_in_lab"] == "FAIL" and result["verifier_unchanged"] else "FAIL")
Path(__file__).with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result))
raise SystemExit(0 if result["status"] == "PASS" else 1)
