"""Quarantine one credential-bearing receipt, or check every existing quarantine.

The defect class this tool eliminates: **a secret that can only be withheld by
deleting the evidence around it.** A receipt is immutable, so the tool never
touches it. It writes two files beside the receipt's segment map instead:

    provenance/quarantine/<SRC>.json          identity, reason, derivative record
    provenance/quarantine/<SRC>.sanitized.md  the receipt with markers in place of
                                              every credential-bearing component

    python tools/quarantine_receipt.py SRC-007 --source-receipt SRC-009 \\
        --ticket T-32 --decision D-023 --statement "<what the operator said>"
    python tools/quarantine_receipt.py --check

Nothing it prints or writes contains the withheld material: findings are
categories, lines and byte offsets (D-023). Writing is refused when the
detector finds nothing, when the receipt no longer matches its recorded digest,
and when a record already exists with different content -- a record is
evidence, and evidence is not silently regenerated.

Publication is immutable (T-42/C2): the complete bytes are staged beside the
target and the name appears through a no-overwrite link, so a concurrent
writer with different bytes loses with a named conflict and can never replace
a committed evidence object.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sailang.errors import SailangError  # noqa: E402
from saimail import quarantine as q  # noqa: E402
from saimail.publish import publish_immutable  # noqa: E402

MEMORY_ROOT = ".saipen"
INTAKE = f"{MEMORY_ROOT}/intake/active"
MANIFEST = f"{MEMORY_ROOT}/MANIFEST.json"
RECORDS = Path("provenance") / q.QUARANTINE_DIR
PROPOSAL = "spec/PROPOSAL-SAIPEN-RECEIPT-QUARANTINE.md"
BLOCKER = ("the original remains in the SAIPEN hot intake, which SAIPEN's own export contract "
           f"ships; a protected local location needs the SAIPEN core change in {PROPOSAL}")


def _manifest(root: Path) -> dict:
    path = root / MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def build(root: Path, receipt: str, source_receipt: str, ticket: str, decision: str,
          statement: str) -> tuple[dict, bytes]:
    """One receipt analysis per build (PERF-006).

    The receipt digest, credential scan, redaction plan, sanitization and
    derivative hash are invariant in the export status that the record's
    evidence carries, so the dominant body analysis runs once: the status is
    derived from the provisional record and the evidence field is assembled
    onto it, which is byte-identical to what a second full build produced.
    """
    body = (root / INTAKE / f"{receipt}.md").read_bytes()
    meta = json.loads((root / INTAKE / f"{receipt}.meta.json").read_text(encoding="utf-8"))
    evidence = {
        "original": {"protected_location": "NOT_AVAILABLE",
                     "protected_location_blocker": BLOCKER},
        "reason": {"operator_statement": {"receipt": source_receipt, "says": statement}},
        "quarantined_under": {"source_receipt": source_receipt, "ticket": ticket,
                              "decision": decision},
    }
    paths = dict(original_path=f"{INTAKE}/{receipt}.md",
                 derivative_path=(RECORDS / f"{receipt}.sanitized.md").as_posix())
    record, sanitized = q.build_record(receipt, body, meta, evidence=evidence, **paths)
    status = q.saipen_export_status(_manifest(root), {receipt: q.record_from_dict(record)},
                                    MEMORY_ROOT)
    record["saipen_export"] = {"status": status, "manifest": MANIFEST, "proposal": PROPOSAL}
    # the writer still produces nothing the reader would refuse, now with the
    # assembled evidence in place (the same check the second full build ran)
    q.record_from_dict(record)
    return record, sanitized


def check(root: Path) -> list[dict]:
    rows = []
    for receipt, record in q.load_records(root / RECORDS).items():
        derivative = (root / record.derivative.path).read_bytes()
        original = q.find_original(root, record)
        fidelity = q.verify_derivative(record, derivative, original)
        rescan = None
        if original is not None:
            rescan = [f.as_record() for f in q.scan(original)] == \
                [f.as_record() for f in record.findings]
        rows.append({"receipt": receipt, "distribution_state": q.SENSITIVE_QUARANTINED,
                     "derivative": record.derivative.id, "fidelity": fidelity,
                     "original_present": original is not None,
                     "findings_reproduced": rescan,
                     "saipen_export": q.saipen_export_status(_manifest(root), {receipt: record},
                                                             MEMORY_ROOT)})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Quarantine a credential-bearing receipt "
                                                 "without touching it.")
    parser.add_argument("receipt", nargs="?")
    parser.add_argument("--source-receipt")
    parser.add_argument("--ticket")
    parser.add_argument("--decision")
    parser.add_argument("--statement")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        if args.check:
            print(json.dumps(check(root), indent=2))
            return 0
        if not (args.receipt and args.source_receipt and args.ticket and args.decision
                and args.statement):
            parser.error("a quarantine names the receipt, the source receipt that asked for it, "
                         "the ticket, the decision and the operator statement")
        record, sanitized = build(root, args.receipt, args.source_receipt, args.ticket,
                                  args.decision, args.statement)
        rendered = q.render_record(record).encode("utf-8")
        target = root / RECORDS / f"{args.receipt}.json"
        derivative = root / record["derivative"]["path"]
        # conflicts are settled before any mutation: evidence is not regenerated
        if target.is_file() and target.read_bytes() != rendered:
            raise SailangError("RECORD_EXISTS_DIFFERENT",
                               f"{target.relative_to(root).as_posix()} exists with other "
                               "content; a quarantine record is evidence and is not "
                               "silently regenerated")
        if derivative.is_file() and derivative.read_bytes() != sanitized:
            raise SailangError("DERIVATIVE_EXISTS_DIFFERENT",
                               f"{derivative.relative_to(root).as_posix()} exists with other "
                               "content; the sanitized derivative is evidence and is not "
                               "silently regenerated")
        target.parent.mkdir(parents=True, exist_ok=True)
        # The JSON record is the commit marker (W2-004): the derivative is
        # committed first, so a failure before the record write leaves either
        # nothing visible or an unreferenced identical derivative that this
        # same command adopts on retry. Both publications are no-overwrite
        # (T-42/C2): a race with different bytes loses with the named conflict
        # above, and identical bytes converge without rewriting the winner.
        publish_immutable(derivative, sanitized,
                          conflict_code="DERIVATIVE_EXISTS_DIFFERENT")
        publish_immutable(target, rendered, conflict_code="RECORD_EXISTS_DIFFERENT")
    except SailangError as exc:
        print(json.dumps({"ok": False, "code": exc.code, "detail": exc.detail}, indent=2))
        return 1
    except OSError as exc:
        print(json.dumps({"ok": False, "code": "QUARANTINE_WRITE_FAILED",
                          "detail": f"{type(exc).__name__}: {exc}; nothing was committed and "
                                    "the receipt was not touched"}, indent=2))
        return 1
    print(json.dumps({
        "ok": True, "receipt": args.receipt, "distribution_state": q.SENSITIVE_QUARANTINED,
        "findings": [{"category": f["category"], "line": f["line"]}
                     for f in record["reason"]["findings"]],
        "derivative": record["derivative"]["id"],
        "derivative_sha256": record["derivative"]["sha256"],
        "saipen_export": record["saipen_export"]["status"],
        "written": [target.relative_to(root).as_posix(), derivative.relative_to(root).as_posix()],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
