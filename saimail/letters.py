"""Evidence-bearing letters for work across sessions and agent generations.

This checks an explicit communication contract, not semantic truth or a
sender's self-reported novelty. Files are evidence pointers, never attachments
or executable instructions. No model, network, or host lifecycle writes.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from sailang import SailangError
from saimail import participants, postoffice

SCHEMA = "SAIMAIL_LETTER_1"
BAD_LETTER = "BAD_LETTER"
LETTER_EVIDENCE_INVALID = "LETTER_EVIDENCE_INVALID"
LETTER_EXPIRED = "LETTER_EXPIRED"
MAX_LETTER_BYTES = 16384
MAX_EVIDENCE = 8
MAX_EVIDENCE_BYTES = 8 * 1024 * 1024
MAX_TEXT_BYTES = 2048
_WORK = re.compile(r"T-[0-9]+\Z")
_ISSUE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset({"schema", "lineage", "issue", "trigger", "sender_work",
                     "recipient_work", "observation", "impact", "request",
                     "done_when", "uncertainty", "evidence", "scope", "expires_at", "in_reply_to"})


def _reject(code, detail):
    raise SailangError(code, detail)


def _text(value, name, *, required=True):
    if (not isinstance(value, str) or not _portable_text(value)
            or len(value.encode("utf-8")) > MAX_TEXT_BYTES):
        _reject(BAD_LETTER, f"{name} must be bounded single-line text")
    if required and not value.strip():
        _reject(BAD_LETTER, f"{name} is required: explain the useful work boundary")
    return value


def _portable_text(value):
    return not any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF
                   or c in "\x7f\u2028\u2029" for c in value)


def topic(lineage, work):
    """Public routing namespace for one project and Work in a shared mailbox."""
    participants._check_lineage(lineage)
    if not isinstance(work, str) or not _WORK.fullmatch(work):
        _reject(BAD_LETTER, "routing needs an exact Work id")
    value = "l." + lineage.removeprefix("lineage-") + "." + work
    if len(value) > 64:
        _reject(BAD_LETTER, "Work id exceeds the routing topic budget")
    return value


def check_path(value):
    """One portable project-relative file path; no glob, device, ADS or escape."""
    if (not isinstance(value, str) or not value or not _portable_text(value)
            or len(value.encode("utf-8")) > 512 or any(c in value for c in "\\:*?<>|\"")
            or value.startswith("/") or any(p in ("", ".", "..") for p in value.split("/"))
            or any(p.endswith((".", " ")) for p in value.split("/"))):
        _reject(BAD_LETTER, "evidence and scope use exact project-relative file paths")
    devices = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{n}" for prefix in ("COM", "LPT") for n in range(1, 10)}
    if any(p.split(".")[0].upper() in devices for p in value.split("/")):
        _reject(BAD_LETTER, "device paths are not evidence")
    return value


def check_evidence(value):
    if not isinstance(value, list) or len(value) > MAX_EVIDENCE:
        _reject(BAD_LETTER, f"evidence is a list of at most {MAX_EVIDENCE} file hashes")
    seen = set()
    for item in value:
        if (not isinstance(item, dict) or set(item) != {"path", "sha256"}
                or not isinstance(item["sha256"], str) or not _HASH.fullmatch(item["sha256"])):
            _reject(BAD_LETTER, "each evidence pointer has exactly path and sha256")
        check_path(item["path"])
        if item["path"] in seen:
            _reject(BAD_LETTER, "evidence paths must be distinct")
        seen.add(item["path"])
    return value


def encode(letter):
    return json.dumps(letter, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def validate(letter, *, lineage=None, sender_work=None, recipient_work=None):
    if not isinstance(letter, dict) or set(letter) != _FIELDS or letter.get("schema") != SCHEMA:
        _reject(BAD_LETTER, f"expected the exact {SCHEMA} fields; use letter template")
    participants._check_lineage(letter["lineage"])
    if not isinstance(letter["issue"], str) or not _ISSUE.fullmatch(letter["issue"]):
        _reject(BAD_LETTER, "issue is a stable token for one decision; retries keep it")
    if not isinstance(letter["trigger"], str) or letter["trigger"] not in participants.TRIGGERS:
        _reject(BAD_LETTER, "a letter uses a closed ownership-boundary trigger")
    for name in ("sender_work", "recipient_work"):
        if not isinstance(letter[name], str) or not _WORK.fullmatch(letter[name]):
            _reject(BAD_LETTER, f"{name} must be T-<number>")
        topic(letter["lineage"], letter[name])
    for name in ("observation", "impact", "request", "done_when"):
        _text(letter[name], name)
    _text(letter["uncertainty"], "uncertainty", required=False)
    check_evidence(letter["evidence"])
    if not letter["evidence"] and not letter["uncertainty"].strip():
        _reject(BAD_LETTER, "attach evidence or explicitly explain what is unverified")
    scope = letter["scope"]
    if not isinstance(scope, list) or not 1 <= len(scope) <= MAX_EVIDENCE:
        _reject(BAD_LETTER, "scope names 1 to 8 exact files where this letter is useful")
    for path in scope:
        check_path(path)
    if len(set(scope)) != len(scope):
        _reject(BAD_LETTER, "scope paths must be distinct")
    if not isinstance(letter["expires_at"], str):
        _reject(BAD_LETTER, "expires_at is a UTC timestamp")
    postoffice._parse_utc(letter["expires_at"], code=BAD_LETTER)
    if letter["in_reply_to"] is not None and (
            not isinstance(letter["in_reply_to"], str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", letter["in_reply_to"])):
        _reject(BAD_LETTER, "in_reply_to is null or one exact envelope identity")
    for name, expected in (("lineage", lineage), ("sender_work", sender_work),
                           ("recipient_work", recipient_work)):
        if expected is not None and letter[name] != expected:
            _reject(BAD_LETTER, f"letter {name} differs from the admitted work context")
    if len(encode(letter).encode("utf-8")) > MAX_LETTER_BYTES:
        _reject(BAD_LETTER, f"a letter must fit in {MAX_LETTER_BYTES} bytes")
    return letter


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _reject(BAD_LETTER, "duplicate JSON fields are ambiguous")
        result[key] = value
    return result


def parse(raw):
    if not isinstance(raw, (str, bytes)):
        _reject(BAD_LETTER, "letter input is JSON text")
    try:
        if len(raw.encode("utf-8") if isinstance(raw, str) else raw) > MAX_LETTER_BYTES:
            _reject(BAD_LETTER, "letter input exceeds its byte budget")
        value = json.loads(raw, object_pairs_hook=_unique_pairs)
    except (ValueError, UnicodeError, RecursionError) as exc:
        _reject(BAD_LETTER, f"letter is not valid bounded JSON: {type(exc).__name__}")
    return validate(value)


def load(path):
    try:
        with Path(path).open("rb") as stream:
            raw = stream.read(MAX_LETTER_BYTES + 1)
    except OSError:
        _reject(BAD_LETTER, "letter file is unreadable")
    return parse(raw)


def _file_hash(root, path):
    base = Path(root).resolve(strict=True)
    candidate = base.joinpath(*PurePosixPath(check_path(path)).parts)
    # Refuse symlink/junction escapes, including a link to a large/device file.
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(base) or not resolved.is_file():
        _reject(LETTER_EVIDENCE_INVALID, "evidence must resolve to a file inside the project")
    digest = hashlib.sha256()
    size = 0
    with resolved.open("rb") as stream:
        while True:
            chunk = stream.read(min(65536, MAX_EVIDENCE_BYTES + 1 - size))
            if not chunk:
                return digest.hexdigest()
            size += len(chunk)
            if size > MAX_EVIDENCE_BYTES:
                _reject(LETTER_EVIDENCE_INVALID, "evidence file exceeds its byte budget")
            digest.update(chunk)


def evidence_ref(project_root, path):
    try:
        return {"path": check_path(path), "sha256": _file_hash(project_root, path)}
    except OSError:
        _reject(LETTER_EVIDENCE_INVALID, "evidence file is missing or unreadable")


def verify_evidence(refs, project_root):
    """Recheck exact bytes locally. A matching hash proves bytes, not the claim."""
    check_evidence(refs)
    results = []
    for ref in refs:
        try:
            actual = _file_hash(project_root, ref["path"])
            state = "CURRENT" if actual == ref["sha256"] else "CHANGED"
        except FileNotFoundError:
            state = "MISSING"
        except (OSError, SailangError):
            state = "UNAVAILABLE"
        results.append({**ref, "state": state})
    return results


def require_current(refs, project_root):
    checked = verify_evidence(refs, project_root)
    if any(ref["state"] != "CURRENT" for ref in checked):
        _reject(LETTER_EVIDENCE_INVALID, "evidence changed, disappeared or cannot be checked")
    return checked


def is_expired(letter, now):
    return postoffice._parse_utc(letter["expires_at"], code=BAD_LETTER) <= \
        postoffice._parse_utc(now, code="BAD_CLOCK")


def template(lineage, sender_work, recipient_work, *, trigger="finding", issue="replace-me",
             clock=None):
    from datetime import timedelta

    now = (clock or postoffice.utc_now)()
    return {"schema": SCHEMA, "lineage": lineage, "issue": issue, "trigger": trigger,
            "sender_work": sender_work, "recipient_work": recipient_work,
            "observation": "", "impact": "", "request": "", "done_when": "",
            "uncertainty": "", "evidence": [], "scope": [], "in_reply_to": None,
            "expires_at": postoffice._format_utc(
                postoffice._parse_utc(now, code="BAD_CLOCK") + timedelta(days=30))}


__all__ = [
    "BAD_LETTER",
    "LETTER_EVIDENCE_INVALID",
    "LETTER_EXPIRED",
    "SCHEMA",
    "encode",
    "evidence_ref",
    "load",
    "parse",
    "template",
    "validate",
    "verify_evidence",
]
