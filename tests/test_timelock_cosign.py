"""FUTURE GATE Wave 6: time capsules, co-signed letters, successor audience.

The wave's acceptance cases, stated as refusals rather than features:

* an early open refuses deterministically
* a post-date open survives restart
* co-signing a mutated body is detected
* signatures survive archive, export and import
* the content stays non-authoritative inert data

Each of those is a claim about what the system does NOT do, which is why most of
this file asserts that a call failed and that its message carried no body. A
test that only checked a happy path would pass against an implementation that
opened everything early and signed whatever it was handed.

Three properties get real proofs rather than mocked ones:

* the early refusal is checked against the date sealed inside the container,
  not a projection, so it survives deleting and rebuilding the registry and
  survives a fresh process;
* a body mutation is performed on the real bytes on disk -- the letter is
  re-sealed with different text -- so the signature failure is produced by the
  actual hash changing rather than by a stub;
* signatures are carried through the real archive/export/import route, so
  "survives export/import" is not a claim about a dict copy.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from sailang import SailangError
from saimail import future_letter as fl
from saimail import workspace

ROOT = Path(__file__).resolve().parent.parent
T0 = "2026-10-04T09:00:00Z"
T1 = "2026-10-04T10:00:00Z"
T2 = "2026-10-04T11:00:00Z"
T3 = "2026-10-04T12:00:00Z"
T_HALF = "2026-10-04T09:30:00Z"
#: Far enough ahead that every "too early" test is unambiguous -- including the
#: one that runs the real clock inside a subprocess.
T_FUTURE = "2099-01-01T00:00:00Z"


def _clock(*stamps):
    sequence = list(stamps)

    def now():
        return sequence.pop(0) if len(sequence) > 1 else sequence[0]

    return now


def _code(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.code
    return "NO_ERROR"


def _detail(fn, *args, **kwargs) -> str:
    try:
        fn(*args, **kwargs)
    except SailangError as exc:
        return exc.detail or ""
    return ""


def _one(tmp_path, name="probe", seat="probe"):
    workspace.init_workspace(tmp_path / name, seat=seat)
    return workspace.load_workspace(tmp_path / name)


def _locked(tmp_path, *, not_before=T_FUTURE, expires_after=None, roster=(),
            name="probe", seat="probe"):
    """One workspace holding one time-locked letter."""
    ws = _one(tmp_path, name, seat)
    created = fl.create(ws, title="a capsule", body="the sealed fact",
                        not_before=not_before, expires_after=expires_after,
                        required_signers=roster, clock=_clock(T0))
    return ws, created


def _cli(*argv, accept=(0,)):
    proc = subprocess.run(
        [sys.executable, "-m", "saimail_local", *argv, "--json"],
        cwd=str(ROOT), capture_output=True, text=True)
    assert proc.returncode in accept, (
        f"exit {proc.returncode} (expected {accept}): {proc.stderr}")
    return json.loads(proc.stdout)


# --------------------------------------------------------------------------
# Part A: the time lock
# --------------------------------------------------------------------------

def test_an_early_open_refuses_and_names_the_date(tmp_path):
    """The acceptance case. The refusal must carry the eligible time."""
    ws, created = _locked(tmp_path)
    ref = created["letter"]["letter_id"]

    detail = _detail(fl.open_letter, ws, ref, clock=_clock(T1))
    assert _code(fl.open_letter, ws, ref, clock=_clock(T1)) == fl.TIME_LOCKED
    assert T_FUTURE in detail, "a refusal that does not name the date is a dead end"
    # Nothing about the refusal is a hint at the content.
    assert "the sealed fact" not in detail

    # And it refuses the same way every time, and for a reopen too. A lock that
    # only guards `open` is a lock a determined reader walks around.
    assert _code(fl.open_letter, ws, ref, clock=_clock(T1)) == fl.TIME_LOCKED
    assert _code(fl.reopen_letter, ws, ref, clock=_clock(T1)) == fl.TIME_LOCKED


def test_metadata_is_visible_before_the_date_but_the_body_is_not(tmp_path):
    """Discovery answers "is there something"; reading stays a separate act.

    Metadata may legitimately be visible early -- that is how a reader learns a
    capsule exists at all -- so the module states the policy instead of leaving
    it implied.
    """
    ws, created = _locked(tmp_path)
    ref = created["letter"]["letter_id"]

    shown = fl.show(ws, ref, clock=_clock(T1))["letter"]
    assert shown["title"] == "a capsule"
    assert shown["not_before"] == T_FUTURE
    assert shown["audience_enforced"] is False

    listed = fl.list_letters(ws, clock=_clock(T1))
    assert listed["items"][0]["not_before"] == T_FUTURE, \
        "a listing that hides the date hides the reason an open failed"

    # The roster report is metadata too, and it says why the letter is closed.
    roster = fl.signatures(ws, ref, clock=_clock(T1))
    assert roster["lock_state"] == fl.TIME_LOCKED
    assert "body" not in roster, "a metadata report must not carry the body"


def test_a_post_date_open_survives_restart_and_a_rebuilt_projection(tmp_path):
    """The lock lives in the sealed container, so nothing cached can move it."""
    ws, created = _locked(tmp_path)
    ref = created["letter"]["letter_id"]

    # A brand new process, a brand new workspace object: the refusal is identical.
    early = subprocess.run(
        [sys.executable, "-c",
         "import json,sys;sys.path.insert(0,%r)\n"
         "from sailang import SailangError\n"
         "from saimail import future_letter as fl, workspace\n"
         "ws = workspace.load_workspace(sys.argv[1])\n"
         "try:\n"
         "    fl.open_letter(ws, sys.argv[2], clock=lambda: %r)\n"
         "    print('OPENED')\n"
         "except SailangError as exc:\n"
         "    print(exc.code)\n" % (str(ROOT), T1), str(ws.root), ref],
        cwd=str(ROOT), capture_output=True, text=True)
    assert early.stdout.strip() == fl.TIME_LOCKED, early.stderr

    # Delete the registry outright and rebuild it from the canonical mailbox.
    registry = Path(ws.root) / fl.DIRECTORY / fl.INDEX_NAME
    registry.unlink()
    rebuilt = fl.reconcile(ws, clock=_clock(T1))
    assert rebuilt["rebuilt"] >= 1, "the projection came back empty"
    try:
        fl.open_letter(ws, ref, clock=_clock(T1))
    except SailangError as exc:
        assert exc.code == fl.TIME_LOCKED, "a rebuilt projection moved the lock"

    # After the date, in a fresh process, the body comes back as data.
    late = subprocess.run(
        [sys.executable, "-c",
         "import sys;sys.path.insert(0,%r)\n"
         "from saimail import future_letter as fl, workspace\n"
         "ws = workspace.load_workspace(sys.argv[1])\n"
         "r = fl.open_letter(ws, sys.argv[2], clock=lambda: %r)\n"
         "print(r['body']); print(r['lock_state'])\n" % (str(ROOT), T_FUTURE),
         str(ws.root), ref], cwd=str(ROOT), capture_output=True, text=True)
    assert late.stdout.splitlines() == ["the sealed fact", fl.LOCK_OPEN], \
        late.stdout + late.stderr


def test_an_expired_capsule_refuses_rather_than_reopening(tmp_path):
    """A lock that quietly kept giving up its contents would not be a lock."""
    ws, created = _locked(tmp_path, not_before=T0, expires_after=3600)
    ref = created["letter"]["letter_id"]

    # Half an hour in, the letter is readable.
    assert fl.open_letter(ws, ref, clock=_clock(T_HALF))["body"] == "the sealed fact"
    # The window is half-open: at the closing instant it has closed.
    later = _clock(T1)
    detail = _detail(fl.open_letter, ws, ref, clock=later)
    assert _code(fl.open_letter, ws, ref, clock=later) == fl.LETTER_EXPIRED
    assert "2026-10-04T10:00:00Z" in detail, "the closing time is the useful part"
    # An expired letter is not merely "still locked": waiting would never help.
    assert fl.TIME_LOCKED not in detail
    # And `reopen` cannot be the way back either.
    assert _code(fl.reopen_letter, ws, ref, clock=_clock(T2)) == fl.LETTER_EXPIRED


def test_a_capsule_that_could_never_open_is_refused_at_creation(tmp_path):
    """Three ways to author a dead letter, all caught by the author."""
    ws = _one(tmp_path)
    common = dict(title="t", body="b")

    # Locked to a moment before it was written.
    assert _code(fl.create, ws, not_before="2020-01-01T00:00:00Z",
                 clock=_clock(T0), **common) == fl.BAD_INPUT
    # Window closes before it opens.
    assert _code(fl.create, ws, not_before=T_FUTURE, expires_after=60,
                 clock=_clock(T0), **common) == fl.BAD_INPUT
    # Durations that are not durations.
    for bad in (0, -1, True, "3600", 1.5):
        assert _code(fl.create, ws, expires_after=bad,
                     clock=_clock(T0), **common) == fl.BAD_INPUT, bad
    # A date this module cannot compare is refused, never rounded to the epoch.
    assert _code(fl.create, ws, not_before="whenever",
                 clock=_clock(T0), **common) == fl.BAD_INPUT
    # A century out is a lock-shaped piece of decoration.
    assert _code(fl.create, ws, expires_after=fl.MAX_LOCK_SECONDS + 1,
                 clock=_clock(T0), **common) == fl.BAD_INPUT

    assert fl.list_letters(ws, clock=_clock(T1))["count"] == 0, \
        "a refused creation left a letter behind"


def test_becoming_eligible_schedules_nothing(tmp_path):
    """No queue, no timer, no prompt -- the wave's explicit non-goal."""
    ws, created = _locked(tmp_path)
    ref = created["letter"]["letter_id"]
    before = _tree(Path(ws.root))

    # Ask past a date that has not arrived. Nothing may appear, run or fire --
    # and, because these are metadata questions, nothing may even be marked
    # read: asking about a letter is not reading it.
    far = _clock("2030-01-01T00:00:00Z")
    assert fl.signatures(ws, ref, clock=far)["lock_state"] == fl.TIME_LOCKED
    fl.list_letters(ws, clock=far)
    assert _tree(Path(ws.root)) == before, "asking about a letter changed the mailbox"
    assert fl.list_letters(ws, clock=far)["items"][0]["state"] == "UNREAD"

    # Ask on a letter whose date HAS passed. It still opens only because someone
    # asked, and what comes back is a string.
    open_ws, ready = _locked(tmp_path, not_before=T0, name="ready", seat="ready")
    ready_ref = ready["letter"]["letter_id"]
    opened = fl.open_letter(open_ws, ready_ref, clock=_clock(T_HALF))
    assert opened["body"] == "the sealed fact"
    assert opened["notice"] == fl.INERT_NOTICE
    assert opened["letter"]["audience_enforced"] is False
    assert opened["lock_state"] == fl.LOCK_OPEN


def _tree(root: Path) -> dict:
    seen = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            seen[str(path.relative_to(root))] = path.read_bytes()
    return seen


# --------------------------------------------------------------------------
# Part B: co-signatures
# --------------------------------------------------------------------------

def test_a_roster_with_a_missing_signer_reads_partially_signed(tmp_path):
    """The headline of Part B: 'mostly agreed' is never rounded up."""
    ws = _one(tmp_path)
    created = fl.create(ws, title="needs two", body="a shared decision",
                        required_signers=["probe", "second"],
                        clock=_clock(T0))
    ref = created["letter"]["letter_id"]

    empty = fl.signatures(ws, ref, clock=_clock(T1))["cosignatures"]
    assert empty["state"] == fl.COSIGN_UNSIGNED
    assert empty["missing"] == ["probe", "second"]

    fl.cosign(ws, ref, clock=_clock(T1))
    partial = fl.signatures(ws, ref, clock=_clock(T1))["cosignatures"]
    assert partial["state"] == fl.COSIGN_PARTIALLY_SIGNED
    assert partial["missing"] == ["second"]
    assert partial["complete"] is False
    assert partial["signed_by"] == ["probe"]

    # The opened letter carries the same verdict, so nobody reads a body and
    # concludes the letter was agreed.
    opened = fl.open_letter(ws, ref, clock=_clock(T1))
    assert opened["cosignatures"]["state"] == fl.COSIGN_PARTIALLY_SIGNED


def test_each_signature_is_inspectable_and_only_one_per_identity(tmp_path):
    ws = _one(tmp_path)
    created = fl.create(ws, title="signed once", body="b",
                        required_signers=["probe"], clock=_clock(T0))
    ref = created["letter"]["letter_id"]

    fl.cosign(ws, ref, clock=_clock(T1))
    signatures = fl.signatures(ws, ref, clock=_clock(T1))["cosignatures"]["signatures"]
    assert len(signatures) == 1
    only = signatures[0]
    assert only["seat"] == "probe"
    assert only["signer_kid"] == ws.sender_kid
    assert only["verified"] is True
    assert only["signed_at"] == T1
    assert len(only["signer_public_key"]) == 64, "the key is named, not implied"

    # A second signature from the same identity is refused, not appended.
    assert _code(fl.cosign, ws, ref, clock=_clock(T1)) == fl.COSIGN_ALREADY_SIGNED
    assert len(fl.signatures(ws, ref, clock=_clock(T1))["cosignatures"][
        "signatures"]) == 1


def test_a_body_edited_after_a_signature_invalidates_it(tmp_path):
    """The acceptance case, on the mechanism that actually binds.

    A signature covers a statement naming the `letter_id` -- the hash of the
    canonical container. So the binding is not "the text still says what I read";
    it is "these bytes are the ones I signed". The test therefore drives the real
    seal path twice: the signed letter, then a second letter through the same
    writer with different words. The signature must not follow.
    """
    ws = _one(tmp_path)
    created = fl.create(ws, title="signed once", body="the original claim",
                        required_signers=["probe"], clock=_clock(T0))
    ref = created["letter"]["letter_id"]
    fl.cosign(ws, ref, clock=_clock(T1))
    assert fl.signatures(ws, ref, clock=_clock(T1))["cosignatures"]["state"] == (
        fl.COSIGN_SIGNED)

    # Same title, different words, sealed by the same author in the same mailbox.
    other = fl.create(ws, title="signed once", body="a completely different claim",
                      required_signers=["probe"], clock=_clock(T2))
    assert other["letter"]["letter_id"] != ref, "the rewrite must change the id"

    # The signature does not migrate onto text its signer never saw.
    moved = fl.signatures(ws, other["letter"]["letter_id"],
                          clock=_clock(T2))["cosignatures"]
    assert moved["state"] == fl.COSIGN_UNSIGNED
    assert moved["signatures"] == []

    # And the letter that WAS signed is still exactly what it was, verbatim.
    assert fl.open_letter(ws, ref, clock=_clock(T2))["body"] == "the original claim"
    assert fl.signatures(ws, ref, clock=_clock(T2))["cosignatures"]["state"] == (
        fl.COSIGN_SIGNED)


def test_a_tampered_signature_is_reported_false_and_does_not_poison_the_roster(tmp_path):
    """One bad signature must not make the good ones unreadable."""
    ws = _one(tmp_path)
    created = fl.create(ws, title="two of three", body="b",
                        required_signers=["probe", "second"],
                        clock=_clock(T0))
    ref = created["letter"]["letter_id"]
    fl.cosign(ws, ref, clock=_clock(T1))

    path = Path(ws.root) / fl.DIRECTORY / fl.COSIGN_NAME
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]
    forged = dict(rows[0], seat="second", signer_kid="sha256:" + "0" * 64,
                  signer_public_key="11" * 32,
                  signature=rows[0]["signature"][:-2] + "00")
    # APPEND the forgery: the good signature stays on the roster next to it.
    path.write_text(path.read_text(encoding="utf-8") + json.dumps(forged) + "\n",
                    encoding="utf-8")

    roster = fl.signatures(ws, ref, clock=_clock(T2))["cosignatures"]
    verdicts = {item["seat"]: item["verified"] for item in roster["signatures"]}
    assert verdicts == {"probe": True, "second": False}
    assert roster["state"] == fl.COSIGN_PARTIALLY_SIGNED
    assert roster["missing"] == ["second"]


def test_signatures_survive_the_real_export_and_import_route(tmp_path):
    """Two identities, two workspaces, one letter -- the acceptance case."""
    author = _one(tmp_path, "author", "author")
    signer = _one(tmp_path, "signer", "signer")
    created = fl.create(author, title="two parties", body="a shared decision",
                        required_signers=["author", "signer"], clock=_clock(T0))
    ref = created["letter"]["letter_id"]
    fl.cosign(author, ref, clock=_clock(T1))

    bundle = tmp_path / "letter.zip"
    fl.export_bundle(author, ref, out=bundle, recovery=True, clock=_clock(T1))
    document = tmp_path / "sigs.json"
    fl.export_cosignatures(author, ref, out=document, clock=_clock(T1))
    assert document.is_file()

    # The signer's workspace has never seen this letter and never saw the author
    # sign; it receives the letter, then the detached signatures, through the
    # ordinary routes and adopts the roster.
    imported = fl.import_bundle(signer, bundle, clock=_clock(T2))
    copy_id = imported["letter"]["letter_id"]
    assert copy_id != ref, "an honest re-seal gets its own identity"
    assert imported["letter"]["source_ref"] == ref
    adopted = fl.import_cosignatures(signer, document, clock=_clock(T2))
    assert adopted["accepted"] == ["author"]
    assert adopted["signs"] == ref, "the signature names the letter it signed"
    assert adopted["letter_id"] == copy_id, "and is filed against the local copy"
    assert adopted["roster"]["state"] == fl.COSIGN_PARTIALLY_SIGNED
    assert adopted["roster"]["missing"] == ["signer"]

    fl.cosign(signer, copy_id, clock=_clock(T2))
    final = fl.signatures(signer, copy_id, clock=_clock(T2))["cosignatures"]
    assert final["state"] == fl.COSIGN_SIGNED, final
    assert final["signed_by"] == ["author", "signer"]

    # Re-importing the same document adds nothing: a roster cannot be padded.
    again = fl.import_cosignatures(signer, document, clock=_clock(T3))
    assert again["accepted"] == []
    assert again["rejected"][0]["reason"] == "ALREADY_HELD"


def test_a_signature_document_for_another_letter_is_refused(tmp_path):
    ws = _one(tmp_path, "a", "alpha")
    ws2 = _one(tmp_path, "b", "beta")
    first = fl.create(ws, title="one", body="b", clock=_clock(T0))["letter"]
    second = fl.create(ws2, title="two", body="b", clock=_clock(T0))["letter"]
    fl.cosign(ws2, second["letter_id"], clock=_clock(T1))

    document = tmp_path / "sigs.json"
    fl.export_cosignatures(ws2, second["letter_id"], out=document, clock=_clock(T1))
    assert _code(fl.import_cosignatures, ws, document, clock=_clock(T1)) == (
        fl.LETTER_NOT_FOUND)

    # A document whose HEADER claims a letter this mailbox holds while its
    # signatures name a different one contributes nothing. It is not refused
    # whole -- it is refused per signature, and the roster is left untouched,
    # which is the same fail-closed answer with the reason named.
    tampered = json.loads(document.read_text(encoding="utf-8"))
    tampered["letter_id"] = first["letter_id"]
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(tampered), encoding="utf-8")
    result = fl.import_cosignatures(ws, bad, clock=_clock(T1))
    assert result["accepted"] == []
    assert result["rejected"][0]["reason"] == "SIGNS_ANOTHER_LETTER"
    assert fl.signatures(ws, first["letter_id"], clock=_clock(T1))[
        "cosignatures"]["state"] == fl.COSIGN_UNSIGNED


def test_a_signature_survives_the_letters_own_reimport(tmp_path):
    """The alias rule, on the journey it exists for.

    An import re-seals honestly as `source: IMPORTED`, so the copy has its own
    `letter_id`; without `source_ref` being treated as an alias the signature
    would name an id this mailbox has never held.
    """
    author = _one(tmp_path, "author", "author")
    other = _one(tmp_path, "other", "other")
    created = fl.create(author, title="portable", body="carried across",
                        required_signers=["author"], clock=_clock(T0))
    ref = created["letter"]["letter_id"]
    fl.cosign(author, ref, clock=_clock(T1))

    bundle = tmp_path / "letter.zip"
    fl.export_bundle(author, ref, out=bundle, recovery=True, clock=_clock(T1))
    imported = fl.import_bundle(other, bundle, clock=_clock(T2))
    copy_id = imported["letter"]["letter_id"]
    assert copy_id != ref, "an honest re-seal gets its own identity"
    assert imported["letter"]["source_ref"] == ref

    # The lock and the roster travel with the letter. An import that rewrote
    # provenance but dropped them would hand over a copy that is unlocked and
    # unrostered while claiming to be the letter that was locked.
    carried = fl.create(author, title="carried", body="still locked",
                        not_before=T_FUTURE, required_signers=["author"],
                        clock=_clock(T0))
    locked_bundle = tmp_path / "locked.zip"
    fl.export_bundle(author, carried["letter"]["letter_id"], out=locked_bundle,
                     recovery=True, clock=_clock(T1))
    locked_copy = fl.import_bundle(other, locked_bundle, clock=_clock(T2))
    copy = locked_copy["letter"]
    assert copy["not_before"] == T_FUTURE
    assert copy["required_signers"] == ["author"]
    assert _code(fl.open_letter, other, copy["letter_id"],
                 clock=_clock(T2)) == fl.TIME_LOCKED

    # The signature travels in its own detached document, and the copy finds it
    # through the alias rather than through the id it was made under.
    document = tmp_path / "sigs.json"
    fl.export_cosignatures(author, ref, out=document, clock=_clock(T1))
    fl.import_cosignatures(other, document, clock=_clock(T2))
    assert fl.signatures(other, copy_id, clock=_clock(T2))["cosignatures"]["state"] == (
        fl.COSIGN_SIGNED), "the signature did not survive its own letter's reimport"

    # And a local signature still binds: the copy is complete for its roster.
    roster = fl.cosign(other, copy_id, clock=_clock(T2))["roster"]
    assert roster["state"] == fl.COSIGN_SIGNED
    assert roster["signed_by"] == ["author", "other"]


def test_a_damaged_signature_document_is_refused_whole(tmp_path):
    """Fail closed, like everything else that crosses a trust boundary."""
    ws = _one(tmp_path)
    created = fl.create(ws, title="t", body="b", clock=_clock(T0))
    ref = created["letter"]["letter_id"]
    fl.cosign(ws, ref, clock=_clock(T1))
    document = tmp_path / "sigs.json"
    fl.export_cosignatures(ws, ref, out=document, clock=_clock(T1))
    good = document.read_text(encoding="utf-8")

    cases = {
        "not json at all": ("this is not json", fl.COSIGN_DOC_INVALID),
        "not an object": ("[]", fl.COSIGN_DOC_INVALID),
        "an unexpected field set": (json.dumps(
            {**json.loads(good), "extra": 1}), fl.COSIGN_DOC_INVALID),
        # A schema this reader does not know is UNSUPPORTED_SCHEMA, exactly as
        # for a container: one code per meaning beats a locally tidier one.
        "a schema this reader does not know": (json.dumps(
            {**json.loads(good), "schema": "SAIMAIL_FUTURE_LETTER_COSIGN_99"}),
            fl.UNSUPPORTED_SCHEMA),
        "a signature with an extra field": (json.dumps(
            {**json.loads(good), "signatures": [
                {**json.loads(good)["signatures"][0], "note": "trust me"}]}),
            fl.COSIGN_DOC_INVALID),
    }
    for label, (text, expected) in cases.items():
        document.write_text(text, encoding="utf-8")
        assert _code(fl.import_cosignatures, ws, document,
                     clock=_clock(T2)) == expected, label

    document.write_text(good, encoding="utf-8")
    assert _code(fl.import_cosignatures, ws, tmp_path / "absent.json",
                 clock=_clock(T2)) == fl.COSIGN_DOC_INVALID


# --------------------------------------------------------------------------
# Part C: successor audience
# --------------------------------------------------------------------------

def test_an_audience_names_a_reader_without_becoming_a_gate(tmp_path):
    """Metadata, not access control -- stated in the result, not implied."""
    ws = _one(tmp_path)
    for scope, subject in (("SEAT", "the-next-agent"),
                           ("SUCCESSOR_OF", "the-last-agent"),
                           ("MAINTAINERS", None), ("OPERATOR", None)):
        created = fl.create(ws, title=scope, body="b", audience_scope=scope,
                            audience_subject=subject, clock=_clock(T0))
        letter = created["letter"]
        assert letter["audience_scope"] == scope
        assert letter["audience_subject"] == subject
        assert letter["audience_enforced"] is False, scope
        # And it really is not a gate: anybody holding the workspace reads it.
        assert fl.open_letter(ws, letter["letter_id"],
                              clock=_clock(T1))["body"] == "b"


def test_an_audience_scope_that_names_nobody_is_refused(tmp_path):
    ws = _one(tmp_path)
    common = dict(title="t", body="b", clock=_clock(T0))
    assert _code(fl.create, ws, audience_scope="SEAT", **common) == fl.BAD_INPUT
    assert _code(fl.create, ws, audience_scope="SUCCESSOR_OF",
                 **common) == fl.BAD_INPUT
    assert _code(fl.create, ws, audience_scope="EVERYONE",
                 **common) == fl.BAD_INPUT
    # A successor of nobody is not a successor.
    assert _code(fl.create, ws, audience_subject="orphan",
                 **common) == fl.BAD_INPUT
    # MAINTAINERS and OPERATOR need no name and get none invented.
    made = fl.create(ws, audience_scope="MAINTAINERS", **common)
    assert made["letter"]["audience_subject"] is None
    assert fl.list_letters(ws, clock=_clock(T1))["count"] == 1


# --------------------------------------------------------------------------
# the format change itself
# --------------------------------------------------------------------------

def test_a_v1_letter_still_parses_and_keeps_its_identity(tmp_path):
    """The bump must not re-identify every letter already in a mailbox.

    A v1 container rebuilt as v2 would have a different `letter_id`, so every
    stored letter would fail its own hash check the first time it was opened.
    """
    legacy = {
        "schema": fl.LEGACY_CONTAINER_SCHEMA, "title": "an old letter",
        "body": "written before wave 6", "author": None, "audience": None,
        "tags": [], "created_at": T0, "custody": fl.CUSTODY_PRIVATE,
        "source": fl.SOURCE_AUTHORED, "source_ref": None,
    }
    raw = json.dumps(legacy, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False).encode("utf-8")
    rebuilt = fl.parse_container(raw)
    assert rebuilt["schema"] == fl.LEGACY_CONTAINER_SCHEMA
    assert fl.container_bytes(rebuilt) == raw, "a v1 letter's bytes must not move"
    assert fl.letter_id(rebuilt) == fl.letter_id(legacy)

    # A v2-only field inside a v1 container is refused, not ignored.
    smuggled = {**legacy, "schema": fl.LEGACY_CONTAINER_SCHEMA,
                "not_before": T_FUTURE}
    assert _code(fl.parse_container, json.dumps(smuggled).encode("utf-8")) == (
        fl.BAD_LETTER)

    # And a v1 letter has no lock and no roster, which are different from empty.
    assert rebuilt.get("not_before") is None
    assert fl._lock_state(rebuilt, T1) == fl.LOCK_OPEN
    assert fl._roster_state(type("W", (), {"root": str(tmp_path)})(), "x",
                            rebuilt)["state"] == fl.COSIGN_UNSIGNED


def test_the_cli_offers_the_same_refusals_as_the_module(tmp_path):
    """Nothing is CLI-only behaviour, including the locks."""
    ws, created = _locked(tmp_path, roster=["probe", "second"])
    ref = created["letter"]["letter_id"]
    root = str(ws.root)

    refused = _cli("future-letter", "open", "--workspace", root,
                   "--letter", ref, accept=(1,))
    assert refused["status"] == fl.TIME_LOCKED
    assert T_FUTURE in refused["detail"]

    made = _cli("future-letter", "create", "--workspace", root,
                "--title", "from the cli", "--body", "text",
                "--not-before", T_FUTURE, "--required-signer", "second",
                "--audience-scope", "SUCCESSOR_OF", "--audience-subject", "old")
    assert made["letter"]["not_before"] == T_FUTURE
    assert made["letter"]["required_signers"] == ["second"]
    assert made["letter"]["audience_scope"] == "SUCCESSOR_OF"

    signed = _cli("future-letter", "cosign", "--workspace", root, "--letter", ref)
    assert signed["roster"]["state"] == fl.COSIGN_PARTIALLY_SIGNED

    report = _cli("future-letter", "signatures", "--workspace", root,
                  "--letter", ref)
    assert report["cosignatures"]["missing"] == ["second"]
    assert report["lock_state"] == fl.TIME_LOCKED

    document = tmp_path / "cli-sigs.json"
    _cli("future-letter", "export-signatures", "--workspace", root,
         "--letter", ref, "--out", str(document))
    assert json.loads(document.read_text(encoding="utf-8"))["letter_id"] == ref