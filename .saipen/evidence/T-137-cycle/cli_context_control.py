"""A changing host state must not be hidden by two separate CLI admissions."""

import contextlib
import hashlib
import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import saimail_local
from saimail import saipen_bridge

spec = importlib.util.spec_from_file_location("cycle_fixture", ROOT / "tests/test_correspondence.py")
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
label = sys.argv[1]
with pytest.MonkeyPatch.context() as patch:
    pair = fixture.setup.__wrapped__(Path(tempfile.mkdtemp(prefix="saimail-cycle-context-")), patch)
    _, receiver, root, _ = pair
    original = saipen_bridge.enter
    calls = []

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        calls.append(result["saipen"]["last_event"])
        if len(calls) == 1:
            state = root / ".saipen/STATE.md"
            state.write_text(state.read_text(encoding="utf-8").replace("last_event: 40", "last_event: 41"), encoding="utf-8")
        return result

    patch.setattr(saipen_bridge, "enter", changed)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = saimail_local.main(["--json", "saipen", "letter", "cycle", "--work", "T-9",
                                  "--workspace", str(receiver.root), "--project-root", str(root),
                                  "--seat", "reviewer"])
    result = json.loads(output.getvalue())
    good = code == 1 and result["status"] == saipen_bridge.SAIPEN_CONTEXT_CHANGED
    evidence = {"schema": "SAIMAIL_T137_CONTEXT_CONTROL_1", "verdict": "PASS" if good else "FAIL",
                "cli_exit": code, "status": result["status"], "admission_events": calls,
                "verifier": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "subject": hashlib.sha256((ROOT / "saimail_local.py").read_bytes()).hexdigest()}
    Path(__file__).with_name(label + "-context.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence))
    raise SystemExit(0 if good else 1)
