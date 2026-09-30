"""T-119 red controls: every outbox guarantee has a test that sees it break.

1. Defect demonstration on the pre-T-119 path: a caller that retries
   ``send_message`` after an unclear result sends a second message.
2. Source-level mutants of saimail/outbox.py in an isolated copy (so child
   processes of the crash and race controls run the mutant too):
   - no_lock:        the outbox lock is a no-op
   - reseal:         plaintext is kept and every delivery attempt re-seals it
   - keep_plaintext: the record is not dropped at SEALED
   - all_terminal:   transient failures are treated as terminal

Usage: python .saipen/kitchen/t119_red_control.py <scratch-dir>
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[2]
scratch = Path(sys.argv[1]).resolve()
TEST = "tests/test_outbox.py"

LOCK = ("    return postoffice._OsFileLock(_outbox_root(workspace) / LOCK_NAME,\n"
        "                                  busy_code=OUTBOX_LOCK_TIMEOUT)\n")
DROP = "    intent.update(state=SEALED, record=None, container=container,\n"
CHECK = ('    if intent["state"] in (SEALED, DELIVERED) and (not sealed or '
         'intent["record"] is not None):\n')
DELIVER = '        delivery = office.deliver(intent["container"])\n'
RESEAL = '''        if intent["record"] is not None and getattr(workspace, "sender_private_key", None):
            fresh = envelope.seal(
                parse_record(intent["record"].encode("utf-8")).canonical_bytes(),
                sender_private_key=workspace.sender_private_key, sender_seat=workspace.seat,
                recipient_seat=recipient["seat"],
                recipient_public_key=X25519PublicKey.from_public_bytes(
                    bytes.fromhex(recipient["recipient_public_key"])),
                kind=intent["kind"], topic=intent["topic"], created=intent["created"])
            intent.update(container=fresh, envelope_id=envelope.envelope_id(fresh))
        delivery = office.deliver(intent["container"])
'''
KEEP_CHECK = ('    if intent["state"] in (SEALED, DELIVERED) and not sealed:\n')
DROP_KEEP = "    intent.update(state=SEALED, container=container,\n"

MUTANTS = {
    "no_lock": [(LOCK, "    import contextlib\n    return contextlib.nullcontext()\n")],
    "reseal": [(DROP, DROP_KEEP), (CHECK, KEEP_CHECK), (DELIVER, RESEAL)],
    "keep_plaintext": [(DROP, DROP_KEEP), (CHECK, KEEP_CHECK)],
    "all_terminal": [("TRANSIENT_CODES = frozenset({",
                      "TRANSIENT_CODES = frozenset() and frozenset({")],
}


def run(where: Path):
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                           "-rA", TEST], cwd=where, capture_output=True, text=True)
    failed = [ln.split(" - ")[0] for ln in proc.stdout.splitlines() if ln.startswith("FAILED")]
    return proc.returncode, failed, proc.stdout.strip().splitlines()[-1]


def copy_tree(dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "tests").mkdir(parents=True)
    for name in ("sailang", "saimail", "lab"):
        shutil.copytree(root / name, dest / name,
                        ignore=shutil.ignore_patterns("__pycache__", "out", "history"))
    shutil.copy2(root / "conftest.py", dest / "conftest.py")
    shutil.copy2(root / "saimail_local.py", dest / "saimail_local.py")
    shutil.copy2(root / TEST, dest / TEST)


def defect_demonstration() -> str:
    sys.path.insert(0, str(root))
    from saimail import workspace
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        workspace.init_workspace(tmp / "A", seat="alpha")
        workspace.init_workspace(tmp / "B", seat="beta")
        A = workspace.load_workspace(tmp / "A")
        B = workspace.load_workspace(tmp / "B")
        workspace.add_recipient(A, "beta", workspace.identity_card(B), B.root)
        workspace.add_recipient(B, "alpha", workspace.identity_card(A), A.root)
        for _attempt in range(2):  # the second call is the caller's retry
            workspace.send_message(A, "beta", claim="same finding", topic="T-119",
                                   kind="DISCOVERY")
        count = workspace.query_inbox(workspace.load_workspace_headers(B.root),
                                      topic="T-119")["match_count"]
    return f"send_message retried after an unclear result: receiver holds {count} messages"


print("== defect demonstration (pre-T-119 send path)")
print(defect_demonstration())
where = scratch / "baseline"
copy_tree(where)
rc, failed, summary = run(where)
print(f"== unmutated copy: rc={rc} {summary}")
for name, edits in MUTANTS.items():
    where = scratch / name
    copy_tree(where)
    target = where / "saimail" / "outbox.py"
    text = target.read_text(encoding="utf-8")
    for old, new in edits:
        assert text.count(old) == 1, (name, old[:50])
        text = text.replace(old, new)
    target.write_text(text, encoding="utf-8")
    rc, failed, summary = run(where)
    print(f"== mutant {name}: rc={rc} {summary}")
    for line in failed:
        print("  " + line)
