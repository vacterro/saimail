"""Use the compact command on the active agent's existing Work and mailbox."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
memory = ROOT / ".saipen"
before = {name: (memory / name).read_bytes() for name in ("STATE.md", "IDENTITY.md", "BOARD.md", "LOG.md")}
argv = [sys.executable, "-m", "saimail_local", "--json", "saipen", "letter", "focus",
        "--workspace", "C:/Users/vac34/AppData/Local/saipen/saimail", "--project-root", str(ROOT),
        "--seat", "saipen-cli", "--work", "T-141", "--scope", "saimail_local.py", "--budget", "20"]
run = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=10, check=False,
                     **({"creationflags": subprocess.CREATE_NO_WINDOW}
                        if hasattr(subprocess, "CREATE_NO_WINDOW") else {}))
assert run.returncode == 0, "compact local observation must succeed; do not forward stderr"
data = json.loads(run.stdout)
focus = data["focus"]
assert focus["state"] == "OK" and focus["host"]["task"] == "T-141" and focus["work"] == "T-141"
assert {name: (memory / name).read_bytes() for name in before} == before
record = {"schema": "SAIMAIL_ACTUAL_COMPACT_CLI_ENTRY_1", "work": "T-141", "command_result": data,
          "normalized_command_bytes": len(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()),
          "memory_unchanged": True,
          "claim_boundary": "One actual configured read-only CLI entry; empty observations do not establish receiver benefit."}
Path(__file__).with_suffix(".json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"state": focus["state"], "work": focus["work"], "reading_count": len(focus["reading"]),
                  "reviewed": focus["reviewed"], "memory_unchanged": True,
                  "normalized_command_bytes": record["normalized_command_bytes"]}))
