"""A mailbox safe to break, and the lane where breaking it is proven (FUTURE GATE Wave 5).

Defect class this module eliminates: destructive tests aimed at whatever mailbox
was closest. Every crash-window proof, corrupt-container probe and rotation
rejection in a mail system eventually gets aimed at a working agent's real mail,
because the alternative -- a dedicated synthetic identity nobody trusts to be
synthetic -- takes more setup than running the test against a fixture that
happens to be lying around. Then a passing suite is a suite that proved it can
delete real mail.

So the synthetic identity is permanent and pre-committed, not built per test:

* a **reserved seat namespace** (``canary-``) makes the identity unmistakable in
  a log line, a lock file and a directory listing before anything parses it;
* a **durable stamp** beside the workspace marker names the seat and both key
  fingerprints, so the classification travels with the identity instead of with
  a test that happens to still be running;
* **destructive operations refuse anything that is not canary**, checking the
  stamp against the loaded identity before touching a single byte.

Two checks, because they fail closed in opposite directions and one rule cannot
do both jobs. The seat prefix decides what production *sees* -- a canary message
is excluded from an inbox or a metrics view, and a prefix is visible without any
I/O. The stamp decides what may be *destroyed* -- a stamp that does not match the
loaded seat and both fingerprints is not proof of anything, so the reset refuses.

The classification travels: a Future Letter created from a canary workspace
carries ``CANARY`` in its tags, which are part of the sealed container, so it
survives ``export_bundle`` -> ``import_bundle`` into a workspace that has never
seen the canary module. A classification that lives in a sidecar file next to
the mailbox says nothing about a bundle that has travelled somewhere else.

ponytail: the seat prefix is a naming convention, not a capability. Anyone who
deliberately renames a production workspace to ``canary-*`` *and* writes a
matching stamp has declared it test data, and the module will believe them. That
is the intended ceiling -- what this buys is that no *accident* is ever mistaken
for permission. A capability-backed identity would mean a key the production
runtime cannot present, which is a different trust model than this codebase
uses anywhere else.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from sailang import SailangError
from saimail import postoffice
from saimail import workspace as _workspace

CANARY_SCHEMA = "SAIMAIL_CANARY_1"
CANARY_VERSION = 1

#: The file beside the workspace marker. Deliberately NOT inside the marker:
#: `_validate_marker` accepts an exact field set, and a test classification is
#: not part of an identity's public projection.
STAMP_NAME = "canary.json"

#: Failure reports live here, inside the canary but outside the mailbox, so a
#: scenario's evidence can never be mistaken for a message, an index row or a
#: pending delivery -- and so a mailbox listing stays a listing of mail.
REPORT_DIR = "chaos"

#: Where `reset` moves reports before it wipes. A sibling, not a child: the
#: reset deletes the workspace tree, and reports that survive it have to live
#: somewhere the wipe does not reach.
HISTORY_SUFFIX = ".chaos-history"

#: The reserved namespace. Chosen to be loud in a log line rather than short.
SEAT_PREFIX = "canary-"

#: The container tag that carries classification through export/import.
TAG = "CANARY"

CLASSIFICATION_CANARY = "CANARY"
CLASSIFICATION_PRODUCTION = "PRODUCTION"

SEEDED = "SEEDED"
RESET = "RESET"
RECORDED = "RECORDED"
CLASSIFIED = "CLASSIFIED"

CANARY_TARGET_REFUSED = "CANARY_TARGET_REFUSED"
CANARY_STAMP_INVALID = "CANARY_STAMP_INVALID"
CANARY_SEAT_REQUIRED = "CANARY_SEAT_REQUIRED"
CANARY_REPORT_INVALID = "CANARY_REPORT_INVALID"
BAD_INPUT = _workspace.BAD_INPUT

REFUSED = postoffice.REFUSED

_STAMP_FIELDS = frozenset({"schema", "version", "classification", "seat", "purpose",
                           "created", "sender_kid", "recipient_kid"})

_UTC_LEN = len("0000-00-00T00:00:00Z")


def _reject(code: str, detail: str) -> None:
    raise SailangError(code, detail)


# --------------------------------------------------------------------------
# classification
# --------------------------------------------------------------------------

def classify_seat(seat) -> str:
    """The one rule, with no I/O: the reserved seat prefix.

    Exposed separately from the stamp because an inbox filter must classify
    thousands of senders per scan, and because the two checks fail closed in
    opposite directions -- see the module docstring.
    """
    if (isinstance(seat, str) and seat.startswith(SEAT_PREFIX)
            and len(seat) > len(SEAT_PREFIX)):
        return CLASSIFICATION_CANARY
    return CLASSIFICATION_PRODUCTION


def is_test_data(name) -> bool:
    """True when a sender alias, seat or label is canary traffic."""
    return classify_seat(name) == CLASSIFICATION_CANARY


def visible_to(workspace, include_test_data=None) -> bool:
    """Whether THIS mailbox should show test data. ``None`` means "ask it".

    A production operator must not have canary traffic in their inbox or their
    metrics, so production hides it. A canary's own mailbox is the destructive
    lane's entire output -- hiding its own mail there would blind the very thing
    the lane exists to exercise -- so a canary always sees everything. An
    explicit True/False from a caller always wins over both.

    Getting this backwards is not a cosmetic bug: a filter applied blindly makes
    a canary mailbox report an empty inbox for a delivery that landed, which is
    the exact false negative the whole lane is built to avoid.
    """
    if include_test_data is not None:
        return bool(include_test_data)
    return is_canary(workspace)


def filter_items(items, *, include_test_data: bool = False, key: str = "from"):
    """``(kept, excluded_count)`` -- the production default hides test data."""
    if include_test_data:
        return list(items), 0
    kept, dropped = [], 0
    for item in items:
        if is_test_data(item.get(key)):
            dropped += 1
        else:
            kept.append(item)
    return kept, dropped


def stamp_tags(tags):
    """``tags`` with the canary tag on it, exactly once."""
    values = tuple(tags or ())
    return values if TAG in values else values + (TAG,)


def container_is_canary(container) -> bool:
    """Read the classification back out of a Future Letter container."""
    if not isinstance(container, dict):
        return False
    return TAG in (container.get("tags") or ())


def _root_of(workspace_or_root) -> Path:
    """The workspace root, given either a loaded workspace or a plain path.

    `PurePath.root` exists and means the DRIVE ANCHOR, so reading `.root` off a
    Path silently answers `V:\` -- the whole drive. Every helper here accepts
    both shapes, so the Path case has to be checked first or a stamp gets
    written to the filesystem root instead of the mailbox.
    """
    if isinstance(workspace_or_root, (str, Path)):
        return Path(workspace_or_root)
    return Path(workspace_or_root.root)


def stamp_path(workspace_or_root) -> Path:
    return _root_of(workspace_or_root) / STAMP_NAME


def read_stamp(workspace_or_root):
    """The raw stamp, or ``None``. Never raises for a missing or broken file.

    A stamp this function cannot read is *not* canary. Raising here would make
    an unreadable file look like a decision.
    """
    payload = _read_json_or_none(stamp_path(workspace_or_root))
    return payload


def _read_json_or_none(path: Path):
    """JSON object at `path`, or None. Never raises: an unreadable stamp is
    not a decision, and `classify` is about to say so either way."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _stamp_problem(workspace, payload) -> str | None:
    """Why this stamp does not prove the loaded workspace is a canary.

    Returns ``None`` when it does prove it. Every check is a way the stamp and
    the identity can disagree, and each disagreement means the file was written
    for a different identity than the one standing here.
    """
    if set(payload) != _STAMP_FIELDS:
        return "stamp has an unexpected field set"
    if (payload.get("schema") != CANARY_SCHEMA
            or payload.get("version") != CANARY_VERSION):
        return (f"stamp declares {payload.get('schema')!r} "
                f"v{payload.get('version')!r}; this build reads {CANARY_SCHEMA} "
                f"v{CANARY_VERSION}")
    if payload.get("classification") != CLASSIFICATION_CANARY:
        return "stamp does not declare itself canary"
    seat = payload.get("seat")
    if not isinstance(seat, str) or classify_seat(seat) != CLASSIFICATION_CANARY:
        return "stamp names a seat outside the reserved canary namespace"
    if seat != workspace.seat:
        return (f"stamp names seat {seat!r} but the workspace here is "
                f"{workspace.seat!r}")
    for field, actual in (("sender_kid", workspace.sender_kid),
                          ("recipient_kid", workspace.recipient_kid)):
        if payload.get(field) != actual:
            return f"stamp {field} does not match this identity"
    created = payload.get("created")
    if not isinstance(created, str) or len(created) != _UTC_LEN:
        return "stamp created is not a UTC timestamp"
    if not isinstance(payload.get("purpose"), str):
        return "stamp purpose is not text"
    return None


def classify(workspace) -> str:
    """``CANARY`` or ``PRODUCTION``, for a loaded workspace or headers.

    A stamp that does not verify leaves the classification at ``PRODUCTION``:
    the stamp is evidence, and unverified evidence is not permission to destroy.
    """
    payload = read_stamp(workspace)
    if payload is None:
        return CLASSIFICATION_PRODUCTION
    if _stamp_problem(workspace, payload) is not None:
        return CLASSIFICATION_PRODUCTION
    return CLASSIFICATION_CANARY


def is_canary(workspace) -> bool:
    return classify(workspace) == CLASSIFICATION_CANARY


def require_canary(workspace) -> dict:
    """The guard every destructive operation opens with. Refuses loudly."""
    payload = read_stamp(workspace)
    if payload is None:
        _reject(CANARY_TARGET_REFUSED,
                f"no canary stamp at {stamp_path(workspace)}; this target is not "
                "declared test data and nothing will be destroyed")
    problem = _stamp_problem(workspace, payload)
    if problem is not None:
        _reject(CANARY_TARGET_REFUSED,
                f"the canary stamp does not prove this identity is test data "
                f"({problem}); nothing will be destroyed")
    return payload


# --------------------------------------------------------------------------
# seed / reset
# --------------------------------------------------------------------------

def _write_stamp(root: Path, workspace, purpose: str, created: str) -> dict:
    payload = {
        "schema": CANARY_SCHEMA,
        "version": CANARY_VERSION,
        "classification": CLASSIFICATION_CANARY,
        "seat": workspace.seat,
        "purpose": purpose,
        "created": created,
        "sender_kid": workspace.sender_kid,
        "recipient_kid": workspace.recipient_kid,
    }
    _atomic_write(stamp_path(root),
                  _workspace._canonical_json_bytes(payload))
    return payload


def _atomic_write(path: Path, data: bytes) -> None:
    """The same temp+fsync+replace the workspace module uses. Never partial."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def seed(root, *, seat: str, purpose: str = "destructive proof lane",
         custody: str = "raw", clock=None) -> dict:
    """Create the permanent canary mailbox and stamp it as test data.

    The seat must already be in the reserved namespace: a canary that can be
    created under a production-looking name is a canary that will eventually be
    mistaken for one.
    """
    clock = clock or postoffice.utc_now
    if classify_seat(seat) != CLASSIFICATION_CANARY:
        _reject(CANARY_SEAT_REQUIRED,
                f"a canary seat must start with {SEAT_PREFIX!r} and name something "
                f"after it; {seat!r} does not")
    if not isinstance(purpose, str) or not purpose.strip():
        _reject(BAD_INPUT, "purpose must be non-empty text: it is what a reader "
                           "of the stamp is told this mailbox is for")
    root = Path(root)
    _workspace.init_workspace(root, seat=seat, custody=custody, clock=clock)
    workspace = _workspace.load_workspace(root)
    stamp = _write_stamp(root, workspace, purpose, clock())
    return _workspace.command_result(
        "canary-seed", SEEDED, workspace=workspace,
        classification=CLASSIFICATION_CANARY, stamp=stamp,
        reports=str(reports_dir(root)),
        detail=(f"canary mailbox seeded for seat {seat}; every row below is TEST "
                "DATA and is excluded from production listings by default"))


def reports_dir(workspace_or_root) -> Path:
    return _root_of(workspace_or_root) / REPORT_DIR


def history_dir(workspace_or_root) -> Path:
    root = _root_of(workspace_or_root)
    return root.parent / (root.name + HISTORY_SUFFIX)


def archive_reports(workspace_or_root) -> Path | None:
    """Move the failure reports out to a sibling before a wipe.

    Returns where they went, or ``None`` when there was nothing to preserve.
    Moving rather than copying is deliberate: a report left inside the target
    would be deleted by the very reset it documents.
    """
    source = reports_dir(workspace_or_root)
    if not source.is_dir():
        return None
    if not any(source.iterdir()):
        return None
    destination = history_dir(workspace_or_root)
    destination.mkdir(parents=True, exist_ok=True)
    for entry in sorted(source.iterdir()):
        shutil.move(str(entry), str(destination / entry.name))
    shutil.rmtree(source, ignore_errors=True)
    return destination


def reset(root, *, purpose: str = "destructive proof lane", custody: str = "raw",
          clock=None) -> dict:
    """Deterministic reset of a canary mailbox. Refuses anything else.

    Deterministic means the *procedure*: the same target always produces the
    same shape of outcome, and a target that is not canary always produces a
    refusal with nothing touched. It does not mean reproducible keys -- reseeding
    mints a fresh identity on purpose, because a canary whose key survived the
    test is a canary that the next test inherits.
    """
    clock = clock or postoffice.utc_now
    root = Path(root)
    if not (root / _workspace.MARKER_NAME).is_file():
        _reject(CANARY_TARGET_REFUSED,
                f"{root} carries no workspace marker; this target is not a "
                "canary mailbox and nothing will be destroyed")
    current = _workspace.load_workspace_headers(root)
    require_canary(current)
    seat = current.seat
    preserved = archive_reports(root)
    shutil.rmtree(root)
    seeded = seed(root, seat=seat, purpose=purpose, custody=custody, clock=clock)
    return _workspace.command_result(
        "canary-reset", RESET, workspace=_workspace.load_workspace(root),
        reseeded=seeded["stamp"],
        classification=CLASSIFICATION_CANARY,
        previous_identity={"sender_kid": current.sender_kid,
                           "recipient_kid": current.recipient_kid},
        reports_preserved_to=str(preserved) if preserved else None,
        detail=(f"canary mailbox for seat {seat} wiped and reseeded; a previous "
                "failure report was preserved outside the target"
                if preserved else
                f"canary mailbox for seat {seat} wiped and reseeded"))


# --------------------------------------------------------------------------
# failure reports
# --------------------------------------------------------------------------

def record_failure(workspace, *, scenario: str, outcome: str, detail: str = "",
                   evidence=None) -> dict:
    """Preserve one scenario's outcome in the canary, outside the mailbox.

    `evidence` must be JSON-serialisable and is stored verbatim. Nothing here
    reads a private key, and nothing here writes into ``mail/`` -- a report that
    appeared in an inbox would be the module defeating its own point.
    """
    if not isinstance(scenario, str) or not _workspace.SEAT_RE.match(scenario):
        _reject(BAD_INPUT,
                "scenario is one token of letters, digits, dot, dash or underscore")
    if not isinstance(outcome, str) or not outcome:
        _reject(CANARY_REPORT_INVALID, "outcome is required: a report that cannot "
                                       "say what happened is not evidence")
    if evidence is not None and not _is_json(evidence):
        _reject(CANARY_REPORT_INVALID, "evidence must be JSON-serialisable")
    root = _root_of(workspace)
    report = {
        "schema": CANARY_SCHEMA,
        "version": CANARY_VERSION,
        "classification": CLASSIFICATION_CANARY,
        "seat": getattr(workspace, "seat", None),
        "scenario": scenario,
        "outcome": outcome,
        "detail": detail,
        "evidence": evidence if evidence is not None else {},
    }
    target = reports_dir(root) / f"{scenario}.json"
    _atomic_write(target, _workspace._canonical_json_bytes(report))
    return _workspace.command_result(
        "canary-record", RECORDED, workspace=workspace,
        report=report, report_path=str(target),
        detail=(f"TEST DATA: scenario {scenario!r} preserved at {target}, outside "
                "the mailbox so it can never be mistaken for a message"))


def _is_json(value) -> bool:
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


def read_reports(workspace_or_root) -> list:
    """Every preserved report, ordered by scenario. Never decrypts anything."""
    directory = reports_dir(workspace_or_root)
    if not directory.is_dir():
        return []
    return [payload for payload in
            (_read_json_or_none(path) for path in sorted(directory.glob("*.json")))
            if payload is not None]


def reports(workspace) -> dict:
    """Every preserved report for one mailbox, ordered by scenario."""
    found = read_reports(workspace)
    return _workspace.command_result(
        "canary-reports", CLASSIFIED, workspace=workspace,
        reports=found, count=len(found),
        detail=(f"{len(found)} preserved TEST DATA failure report(s); they live "
                f"in {reports_dir(workspace)} and in no index row"))


def status(workspace) -> dict:
    """What this mailbox is, and whether it may be destroyed."""
    payload = read_stamp(workspace)
    # "no stamp" and "a stamp that does not verify" are both PRODUCTION, but an
    # operator reading this needs to know which one they are looking at.
    problem = (f"no readable canary stamp at {stamp_path(workspace)}"
               if payload is None else _stamp_problem(workspace, payload))
    classification = classify(workspace)
    return _workspace.command_result(
        "canary-status", CLASSIFIED, workspace=workspace,
        classification=classification,
        destructive_allowed=(classification == CLASSIFICATION_CANARY),
        stamp=payload,
        stamp_problem=problem,
        reports=len(read_reports(workspace)),
        detail=("test data: destructive operations are permitted"
                if classification == CLASSIFICATION_CANARY else
                "production identity: destructive operations are refused"))