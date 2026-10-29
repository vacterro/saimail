"""Read-only checks of private operator sources, requiring an explicit root.

Public test fixtures exercise these same assertions; no private intake records,
conversations, or runtime mailboxes are distribution inputs.
"""
import argparse
import hashlib
import json
import pathlib
import re


def read(path):
    return path.read_text(encoding="utf-8")

LEGACY_UNREGISTERED_BEACON = frozenset({
    "CURRENT-STATE.md",
    "EVOLUTION-AUDIT.md",
    "EVOLUTION.md",
    "FUTURE-GATES-V2.md",
    "FUTURE-GATES-V3.md",
    "FUTURE-GATES-V4.md",
    "FUTURE-GATES-V5.md",
    "FUTURE-GATES-V6.md",
    "FUTURE-GATES.md",
    "GITHUB-SETTINGS-V6.md",
    "INSTITUTION.md",
    "SAIOPP_instructions.md",
    "SAIOPP_prose.md",
    "SAI_AGENT_REACTIONS.md",
    "SAIPEN-WORK-DESK.md",
    "bee_like_idea1.md",
    "bee_like_idea1_future_Gate.md",
    "computer1.md",
    "future1.md",
    "iniciative.md",
    "talking.md",
    "talking1.md",
    "tv.md",
    "what_means_SAI.md",
})

BEACON_BINDINGS = {
    "milestoned1.md": "SRC-117",  # T-151
    "YAZADAYU_born1.md": "SRC-119",  # T-157
    "autonomy.md": "SRC-125",  # Context-only imported conversation, night-shift triage
    "brain.md": "SRC-126",  # Context-only; captured body quarantined from distribution
    "images_prompts.md": "SRC-127",  # Context-only creative reference
}

STALE_OWNERSHIP = re.compile(
    r"\bT-\d+ (?:still )?owns\b|"
    r"\bowns? (?:the )?(?:subsequent|that|next) continuation|"
    r"\bT-\d+ (?:is|remains) (?:still )?(?:the )?(?:active|current)\b|"
    r"\b(?:the )?current (?:capability[- ]truth |capability/recovery truth |truth )?repair\b|"
    r"\b(?:inside|in|outside|part of) this repair\b|"
    r"\bafter\b[^.;]{0,80}?\bis accepted\b",
    re.IGNORECASE)

def stale_ownership_claims(text: str) -> list:
    """Unqualified ticket-bound ownership claims; blocks marked historical are evidence."""
    claims = []
    for paragraph in text.split("\n\n"):
        for block in re.split(r"\n(?=\s*[-*] |\s*\d+\. )", paragraph):
            flat = " ".join(block.replace("*", "").replace("`", "").split())
            if "(historical)" in flat or flat.startswith(("Historical", "> Historical")):
                continue
            claims += [flat[max(0, m.start() - 40):m.end() + 40]
                       for m in STALE_OWNERSHIP.finditer(flat)]
    return claims


def check_retired_receipt(root, receipt, origin, successor, event):
    ROOT = pathlib.Path(root)
    INTAKE = ROOT / ".saipen/intake/active"
    RETIRED = ROOT / ".saipen/archive/retired"
    TOMBSTONES = ROOT / ".saipen/intake/tombstones"
    import hashlib
    import json

    body = RETIRED / f"{receipt}.md"
    meta = RETIRED / f"{receipt}.meta.json"
    assert body.is_file(), f"{receipt} retired body missing"
    assert meta.is_file(), f"{receipt} retired sidecar missing"
    assert (ROOT / origin).is_file(), f"{origin} missing"
    digest = hashlib.sha256(body.read_bytes()).hexdigest()
    assert digest == json.loads(read(meta))["source_sha256"], (
        f"{receipt} body does not match its recorded digest"
    )
    tomb = json.loads(read(TOMBSTONES / f"{receipt}.json"))
    assert tomb["source_sha256"] == digest
    assert tomb["archive_ref"] == f".saipen/archive/retired/{receipt}.md"
    assert tomb["retirement"]["reason"] == "SUPERSEDED_SOURCE"
    assert tomb["retirement"]["successor"] == successor
    assert tomb["retirement"]["retirement_event"] == event
    assert (INTAKE / f"{successor}.md").is_file(), (
        f"{successor} is the live carrier of the lineage"
    )

def check_separate_receipts(root):
    ROOT = pathlib.Path(root)
    INTAKE = ROOT / ".saipen/intake/active"
    RETIRED = ROOT / ".saipen/archive/retired"
    TOMBSTONES = ROOT / ".saipen/intake/tombstones"
    import hashlib
    import json

    digests = {}
    for receipt in ("SRC-001", "SRC-002"):
        meta = json.loads(read(RETIRED / f"{receipt}.meta.json"))
        body = (RETIRED / f"{receipt}.md").read_bytes()
        digests[receipt] = meta["source_sha256"]
        assert hashlib.sha256(body).hexdigest() == meta["source_sha256"], (
            f"{receipt} body does not match its recorded digest"
        )
    assert digests["SRC-001"] != digests["SRC-002"]
    # The amendment lineage is two SEPARATE receipts, never a merge: each
    # successor carries its own body, both live, neither rewritten.
    successor_bodies = {(INTAKE / f"SRC-00{n}.md").read_bytes()
                        for n in (3, 4)}
    assert len(successor_bodies) == 2

def _receipt_capture_digest(root, receipt_id: str) -> str:
    """The digest a receipt recorded of the bytes it was minted from.

    ``compared_digest`` is that record; ``source_sha256`` is the digest of the
    receipt file itself and says nothing about humbox/. Returns "" when the
    receipt is missing or unreadable so the caller fails the binding rather than
    the suite -- an absent receipt is the finding, not a crash.
    """
    meta = pathlib.Path(root) / ".saipen" / "intake" / "active" / f"{receipt_id}.meta.json"
    if not meta.is_file():
        return ""
    try:
        return json.loads(read(meta))["request_provenance"]["compared_digest"]
    except (ValueError, KeyError, TypeError):
        return ""

def _beacon_key(path: pathlib.Path, humbox) -> str:
    """A beacon file's identity: its path relative to humbox/.

    The basename is not an identity. A file in a subdirectory that happens to
    share a word with a captured file is a different file, and reading it as
    the same one is the mistake this check exists to catch -- so a top-level
    file is identified by its bare name and a nested one by its relative path.
    """
    return path.relative_to(humbox).as_posix()

def check_beacon_registration(root):
    HUMBOX = pathlib.Path(root) / "humbox"
    """An operator file that lands in humbox/ is traceable, or it is named.

    The beacon is fed by a human, so it changes whenever the human has
    something to say and nothing in the product notices. That is the whole
    reason the intake path exists: the bytes get hashed into a receipt and
    projected into Work, so the material is attributable instead of just
    being present. Checking the folder as a whole -- rather than one named
    file per ticket -- is the only form of that check that survives the next
    arrival.

    Registered means one of exactly two things: a BEACON_BINDINGS row whose
    receipt still hashes to the file's bytes, or an explicit exemption in
    LEGACY_UNREGISTERED_BEACON. It does not mean "mentioned somewhere" -- the
    BOARD and the journal are free text that the protocol is actively pruning,
    and T-160 was written because a sentence about a probe was passing as a
    capture.
    """
    drifted = []
    for key, receipt in sorted(BEACON_BINDINGS.items()):
        path = HUMBOX / key
        if not path.is_file():
            drifted.append(f"{key} is bound to {receipt} but the file is gone")
            continue
        raw = path.read_bytes()
        live = {
            hashlib.sha256(raw).hexdigest(),
            hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest(),
            # Canonical ingress strips outer whitespace and normalizes CRLF.
            # The raw source identity remains in source_sha256 separately.
            hashlib.sha256(raw.replace(b"\r\n", b"\n").strip()).hexdigest(),
        }
        if _receipt_capture_digest(root, receipt) not in live:
            drifted.append(f"{key} no longer hashes to what {receipt} captured")
    assert not drifted, (
        "a beacon binding the receipt cannot vouch for: "
        f"{drifted} -- the binding claims these bytes were captured; re-capture "
        "the file or drop the row"
    )

    registered = set(BEACON_BINDINGS)
    unregistered = sorted(
        key
        for path in HUMBOX.rglob("*.md")
        for key in (_beacon_key(path, HUMBOX),)
        if key not in registered
        and key not in LEGACY_UNREGISTERED_BEACON
    )
    assert not unregistered, (
        "operator material in humbox/ that no receipt accounts for: "
        f"{unregistered} -- capture it with `saipen start --file humbox/<path>`, "
        'then add "<key>": "<SRC-id>" to BEACON_BINDINGS (the row is checked '
        "against that receipt's digest), or add it to "
        "LEGACY_UNREGISTERED_BEACON if it genuinely needs no Work"
    )

def check_private_recovery(root):
    path = pathlib.Path(root) / ".saipen/kitchen/T-113-reread-continuation.md"
    assert stale_ownership_claims(read(path)) == [], str(path)


def verify(root):
    root = pathlib.Path(root)
    for receipt, origin, successor, event in (
        ("SRC-001", "idea.md", "SRC-003", "E-1294"),
        ("SRC-002", "idea_continue1.md", "SRC-004", "E-1295"),
    ):
        check_retired_receipt(root, receipt, origin, successor, event)
    check_separate_receipts(root)
    check_beacon_registration(root)
    check_private_recovery(root)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=pathlib.Path, required=True,
                        help="operator checkout containing its own private intake corpus")
    args = parser.parse_args(argv)
    try:
        verify(args.root)
    except (OSError, ValueError, KeyError, TypeError, AssertionError) as exc:
        print(f"FAIL: {exc}")
        return 1
    print("PASS: explicit private operator-source corpus; no files changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
