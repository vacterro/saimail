"""Retain one read-only blocker recheck; never append a study observation."""

import hashlib
import importlib.util
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from saimail import participants, workspace


def main():
    root = Path(__file__).resolve().parents[3]
    audit = root / ".saipen/evidence/T-142-evolution-audit"
    spec = importlib.util.spec_from_file_location("t142_recheck_verifier", audit / "verify.py")
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    box = Path(os.environ.get("SAIMAIL_WORKSPACE") or
               Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "saipen" / "saimail")
    paths = [root / ".saipen" / name for name in
             ("STATE.md", "IDENTITY.md", "BOARD.md", "LOG.md")]
    paths += [root.parent / "_SAIPEN/.saipen/STATE.md", audit / "registration.json"]
    paths += sorted(audit.glob("runtime*.json"))

    def hashes():
        return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}

    before = hashes()
    summary = checker.sequence(audit)
    headers = workspace.load_workspace_headers(box)
    peers = [{"alias": alias, "seat": peer.get("seat")}
             for alias, peer in headers.peers.items()]
    enrolled = participants.list_participants(headers, summary["project_lineage"])
    inbox = workspace.query_inbox(headers, scan_budget=20)
    after = hashes()
    if before != after:
        raise ValueError("canonical memory, historical evidence or foreign STATE changed")
    record = {
        "schema": "T146_READ_ONLY_BLOCKER_RECHECK_1",
        "timestamp": datetime.now(UTC).isoformat(),
        "user_continuation": "Хорошо, продолжи дальше в таком случае до конца. Используй всё, что для этого требуетсяю.",
        "study_entry_created": False,
        "claim_boundary": "Current public peer/participant metadata and one bounded inbox page; no independent actor or baseline inferred",
        "workspace": str(box.resolve()), "seat": headers.seat,
        "peers": peers, "participants": enrolled, "inbox": inbox,
        "sequence": summary, "before": before, "after": after,
        "canonical_memory_history_and_foreign_state_unchanged": True,
    }
    destination = Path(__file__).with_name(
        "recheck-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with destination.open("x", encoding="utf-8", newline="\n") as target:
        json.dump(record, target, indent=2, ensure_ascii=True)
        target.write("\n")
    print(json.dumps({"evidence": str(destination), "peer_count": len(peers),
                      "participant_count": sum(len(seats) for seats in enrolled["participants"].values()),
                      "inbox_matches": inbox["match_count"],
                      "study_entry_created": False, "field_improvement": summary["field_improvement"]}))


if __name__ == "__main__":
    main()
