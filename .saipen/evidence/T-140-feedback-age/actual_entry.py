"""Read the active agent's own local Work; empty mail is not utility evidence."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from saimail_host import HostClient

mailbox = Path("C:/Users/vac34/AppData/Local/saipen/saimail")
assert mailbox.is_dir(), "the configured acting mailbox must already exist"
memory = ROOT / ".saipen"
before = {name: (memory / name).read_bytes() for name in ("STATE.md", "IDENTITY.md", "BOARD.md", "LOG.md")}
client = HostClient([sys.executable, "-m", "saimail_local"], workspace=mailbox,
                    project_root=ROOT, seat="saipen-cli")
focus = client.focus(["--work", "T-140", "--scope", "saimail/correspondence.py", "--budget", "20"])
assert focus["state"] == "OK" and focus["host"]["task"] == "T-140"
assert focus["feedback_signals"]["state"] == "KNOWN"
assert {name: (memory / name).read_bytes() for name in before} == before
result = {"schema": "SAIMAIL_ACTUAL_WORK_ENTRY_1", "work": "T-140", "observation": focus,
          "claim_boundary": "One actual keyless Work entry, with no send/open/decision/lifecycle action. Empty observations do not prove receiver usefulness."}
Path(__file__).with_suffix(".json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"state": focus["state"], "work": focus["work"], "reading_count": len(focus["reading"]),
                  "reviewed": focus["reviewed"], "temporal_state": focus["feedback_signals"]["state"],
                  "memory_unchanged": True}))
