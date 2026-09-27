"""EXPERIMENT-MANIFEST-1: separated historical, current and live authorities.

The defect class this module eliminates: **a shared verification gate read as
three interchangeable permissions.** Measured three times in this repository:
a new decision appended to the shared decision log invalidated B-018
source-file pins even though the registered section had not changed; the T-65
fix in ``saimail/quarantine.py`` invalidated the historical T-71 tests; the
T-78 change to ``saimail/legacy.py`` again required a frozen fixture. The
fixtures were right, and the remaining gap was always the same one: nothing in
the contract said that

    HISTORICAL_GREEN != CURRENT_CODE_GREEN != LIVE_RUN_AUTHORIZED.

Three operations, three result vocabularies, no shared short-circuit:

``verify_historical(manifest, fixture_root=...)``
    re-proves a recorded historical experiment from its registered immutable
    evidence. It reads nothing but archived fixtures: there is no current
    source parameter to fall back to, so "trust the checkout instead" is not a
    code path. A missing fixture is a mismatch, never a substitution.
``verify_current(manifest, root=...)``
    checks the current checkout against the manifest's selected-source
    extraction rules and frozen implementation bindings. It never claims the
    historical experiment was rerun and it never authorizes a live run.
``admit_live(manifest, root=..., network=...)``
    gates a future live experiment before network. A ``HISTORICAL_ONLY``
    manifest refuses here with ``HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY`` even
    when every hash matches. ``network`` is an optional caller-supplied object
    this gate never invokes; refusals happen before any caller-visible step.

Selected input identity is ``EXTRACTED_SHA256``.
``CONTAINER_SHA256_AT_REGISTRATION`` is evidence about the historical container,
never identity, so an unrelated append outside the registered selector cannot
invalidate a registered input.

Manifest identity is ``sha256(exact canonical JSON bytes)`` -- sorted keys,
compact separators, UTF-8, no trailing newline. The manifest never contains its
own digest and this module never writes one into it.

The schema is closed: unknown fields, unknown versions, unknown extraction
kinds, unknown extractor versions and unknown roles refuse. LAB only: nothing
here performs a model or network call, and nothing here imports a production
``saimail`` module.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from sailang.errors import SailangError

MANIFEST_VERSION = "EXPERIMENT-MANIFEST-1"

TOP_FIELDS = frozenset({"manifest_version", "experiment_id", "authority", "inputs",
                        "implementation"})
INPUT_REQUIRED = frozenset({"INPUT_ID", "SENSITIVITY", "SOURCE_KIND", "EXTRACTION_KIND",
                            "EXTRACTOR_VERSION", "EXTRACTED_SHA256", "REQUIRED_FOR_LIVE"})
INPUT_OPTIONAL = frozenset({"SOURCE_PATH", "SELECTOR", "ARCHIVED_FIXTURE",
                            "CONTAINER_SHA256_AT_REGISTRATION"})
IMPLEMENTATION_FIELDS = frozenset({"PATH", "SHA256", "ROLE"})

SENSITIVITIES = ("PUBLIC_ARCHIVABLE", "PRIVATE_EPHEMERAL")
AUTHORITIES = ("HISTORICAL_ONLY", "LIVE_ELIGIBLE")
SOURCE_KINDS = ("TEXT_FILE", "MARKDOWN_DOCUMENT", "LOG_FILE", "IMMUTABLE_FIXTURE")
EXTRACTION_KINDS = ("WHOLE_FILE", "MARKDOWN_SECTION", "LOG_RECORD", "IMMUTABLE_FIXTURE")
EXTRACTOR_VERSIONS = {
    "WHOLE_FILE": "WHOLE-FILE-1",
    "MARKDOWN_SECTION": "MARKDOWN-SECTION-1",
    "LOG_RECORD": "LOG-RECORD-1",
    "IMMUTABLE_FIXTURE": "IMMUTABLE-FIXTURE-1",
}
ROLES = ("PARSER", "EXTRACTOR", "RUNNER", "GRADER")

HISTORICAL_VERIFIED = "HISTORICAL_VERIFIED"
HISTORICAL_INPUT_UNAVAILABLE_BY_DESIGN = "HISTORICAL_INPUT_UNAVAILABLE_BY_DESIGN"
HISTORICAL_MISMATCH = "HISTORICAL_MISMATCH"
CURRENT_MATCH = "CURRENT_MATCH"
CURRENT_INPUT_DRIFT = "CURRENT_INPUT_DRIFT"
CURRENT_IMPLEMENTATION_DRIFT = "CURRENT_IMPLEMENTATION_DRIFT"

INPUT_ID_RE = re.compile(r"^[A-Z][A-Z0-9_-]{0,63}$")
EXPERIMENT_ID_RE = re.compile(r"^[A-Z][A-Z0-9._-]{0,63}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

_MD_HEADING = "md-heading:"
_LOG_LINE = "log-line:"


def _refuse(code: str, detail: str) -> None:
    raise SailangError(code, detail)


def canonical_bytes(manifest: object) -> bytes:
    """The exact bytes manifest identity is computed over. No trailing newline."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def manifest_identity(manifest: object) -> str:
    """sha256 over canonical JSON bytes; the manifest never contains it."""
    validate(manifest)
    return hashlib.sha256(canonical_bytes(manifest)).hexdigest()


def _relative(rel: object, field: str) -> str:
    if (not isinstance(rel, str) or not rel or rel.startswith(("/", "\\"))
            or ":" in rel or "\\" in rel):
        _refuse("MANIFEST_INVALID_PATH", f"{field}={rel!r} is not a relative POSIX path")
    parts = rel.split("/")
    if any(part in ("", ".", "..") for part in parts):
        _refuse("MANIFEST_INVALID_PATH", f"{field}={rel!r} has an unsafe component")
    return rel


def _owned(root: Path | str, rel: object, field: str) -> Path:
    path = (Path(root) / _relative(rel, field)).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        _refuse("MANIFEST_INVALID_PATH", f"{field}={rel!r} escapes {root}")
    return path


def _validate_input(record: object, seen: set) -> None:
    if type(record) is not dict:
        _refuse("MANIFEST_INVALID", "each input record must be an object")
    fields = set(record)
    unknown = fields - (INPUT_REQUIRED | INPUT_OPTIONAL)
    if unknown:
        _refuse("MANIFEST_UNKNOWN_FIELD", f"input has unknown fields {sorted(unknown)}")
    missing = INPUT_REQUIRED - fields
    if missing:
        _refuse("MANIFEST_MISSING_FIELD", f"input is missing {sorted(missing)}")
    input_id = record["INPUT_ID"]
    if not isinstance(input_id, str) or not INPUT_ID_RE.match(input_id):
        _refuse("MANIFEST_INVALID_INPUT_ID", f"INPUT_ID={input_id!r}")
    if input_id in seen:
        _refuse("MANIFEST_DUPLICATE_INPUT", f"INPUT_ID={input_id!r} appears twice")
    seen.add(input_id)
    if record["SENSITIVITY"] not in SENSITIVITIES:
        _refuse("MANIFEST_UNKNOWN_SENSITIVITY", f"SENSITIVITY={record['SENSITIVITY']!r}")
    if record["SOURCE_KIND"] not in SOURCE_KINDS:
        _refuse("MANIFEST_UNKNOWN_SOURCE_KIND", f"SOURCE_KIND={record['SOURCE_KIND']!r}")
    kind = record["EXTRACTION_KIND"]
    if kind not in EXTRACTOR_VERSIONS:
        _refuse("MANIFEST_UNKNOWN_EXTRACTION_KIND", f"EXTRACTION_KIND={kind!r}")
    expected = EXTRACTOR_VERSIONS[kind]
    if record["EXTRACTOR_VERSION"] != expected:
        _refuse("MANIFEST_UNKNOWN_EXTRACTOR_VERSION",
                f"{kind} requires extractor {expected!r}, got {record['EXTRACTOR_VERSION']!r}")
    digest = record["EXTRACTED_SHA256"]
    if not isinstance(digest, str) or not HEX64_RE.match(digest):
        _refuse("MANIFEST_INVALID_DIGEST", f"EXTRACTED_SHA256={digest!r}")
    if type(record["REQUIRED_FOR_LIVE"]) is not bool:
        _refuse("MANIFEST_INVALID", "REQUIRED_FOR_LIVE must be a boolean")
    fixture = record.get("ARCHIVED_FIXTURE")
    if fixture is not None:
        _relative(fixture, "ARCHIVED_FIXTURE")
        if record["SENSITIVITY"] == "PRIVATE_EPHEMERAL":
            _refuse("MANIFEST_PRIVATE_FIXTURE_FORBIDDEN",
                    f"{input_id} is private and may not carry an archival fixture")
    if kind == "IMMUTABLE_FIXTURE" and fixture is None:
        _refuse("MANIFEST_FIXTURE_REQUIRED",
                f"{input_id} declares IMMUTABLE_FIXTURE without ARCHIVED_FIXTURE")
    if kind != "IMMUTABLE_FIXTURE":
        if "SOURCE_PATH" not in record:
            _refuse("MANIFEST_MISSING_FIELD", f"{input_id} needs SOURCE_PATH for {kind}")
        _relative(record["SOURCE_PATH"], "SOURCE_PATH")
    if kind in ("WHOLE_FILE", "IMMUTABLE_FIXTURE") and "SELECTOR" in record:
        _refuse("MANIFEST_FIELD_NOT_APPLICABLE", f"{kind} does not take SELECTOR")
    if kind in ("MARKDOWN_SECTION", "LOG_RECORD"):
        selector = record.get("SELECTOR")
        if not isinstance(selector, str) or not selector:
            _refuse("MANIFEST_MISSING_FIELD", f"{input_id} needs SELECTOR for {kind}")
        if kind == "MARKDOWN_SECTION" and not selector.startswith(_MD_HEADING):
            _refuse("MANIFEST_UNKNOWN_SELECTOR", f"SELECTOR={selector!r}")
        if kind == "LOG_RECORD" and not selector.startswith(_LOG_LINE):
            _refuse("MANIFEST_UNKNOWN_SELECTOR", f"SELECTOR={selector!r}")
    container = record.get("CONTAINER_SHA256_AT_REGISTRATION")
    if container is not None and (not isinstance(container, str) or not HEX64_RE.match(container)):
        _refuse("MANIFEST_INVALID_DIGEST", f"CONTAINER_SHA256_AT_REGISTRATION={container!r}")


def _validate_implementation(record: object, seen: set) -> None:
    if type(record) is not dict:
        _refuse("MANIFEST_INVALID", "each implementation component must be an object")
    if set(record) != IMPLEMENTATION_FIELDS:
        _refuse("MANIFEST_UNKNOWN_FIELD",
                f"implementation component fields must be exactly {sorted(IMPLEMENTATION_FIELDS)}")
    path = _relative(record["PATH"], "PATH")
    if path in seen:
        _refuse("MANIFEST_DUPLICATE_IMPLEMENTATION", f"PATH={path!r} appears twice")
    seen.add(path)
    digest = record["SHA256"]
    if not isinstance(digest, str) or not HEX64_RE.match(digest):
        _refuse("MANIFEST_INVALID_DIGEST", f"SHA256={digest!r}")
    if record["ROLE"] not in ROLES:
        _refuse("MANIFEST_UNKNOWN_ROLE", f"ROLE={record['ROLE']!r}")


def validate(manifest: object) -> None:
    """Closed-schema validation. Unknown anything refuses; no best effort."""
    if type(manifest) is not dict:
        _refuse("MANIFEST_INVALID", "a manifest is a JSON object")
    fields = set(manifest)
    unknown = fields - TOP_FIELDS
    if unknown:
        _refuse("MANIFEST_UNKNOWN_FIELD", f"manifest has unknown fields {sorted(unknown)}")
    missing = TOP_FIELDS - fields
    if missing:
        _refuse("MANIFEST_MISSING_FIELD", f"manifest is missing {sorted(missing)}")
    if manifest["manifest_version"] != MANIFEST_VERSION:
        _refuse("MANIFEST_UNKNOWN_VERSION", f"manifest_version={manifest['manifest_version']!r}")
    if (not isinstance(manifest["experiment_id"], str)
            or not EXPERIMENT_ID_RE.match(manifest["experiment_id"])):
        _refuse("MANIFEST_INVALID", f"experiment_id={manifest['experiment_id']!r}")
    if manifest["authority"] not in AUTHORITIES:
        _refuse("MANIFEST_UNKNOWN_AUTHORITY", f"authority={manifest['authority']!r}")
    inputs = manifest["inputs"]
    if type(inputs) is not list or not inputs:
        _refuse("MANIFEST_INVALID", "inputs must be a non-empty list")
    seen: set = set()
    for record in inputs:
        _validate_input(record, seen)
    implementation = manifest["implementation"]
    if type(implementation) is not list:
        _refuse("MANIFEST_INVALID", "implementation must be a list")
    comp_seen: set = set()
    for component in implementation:
        _validate_implementation(component, comp_seen)


def load(path: Path | str) -> dict:
    """Read and validate one manifest file. Parse failure refuses, never guesses."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        _refuse("MANIFEST_UNREADABLE", f"{path}: {exc}")
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        _refuse("MANIFEST_UNPARSEABLE", f"{path}: {exc}")
    validate(document)
    return document


def _decode(data: bytes, rel: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        _refuse("MANIFEST_SOURCE_NOT_UTF8", f"{rel} is not UTF-8")


def _markdown_section(data: bytes, selector: str, rel: str) -> bytes:
    heading = selector[len(_MD_HEADING):]
    level = len(heading) - len(heading.lstrip("#"))
    if level < 1 or not heading[level:].startswith(" "):
        _refuse("MANIFEST_UNKNOWN_SELECTOR", f"SELECTOR={selector!r}")
    lines = _decode(data, rel).splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines)
                  if line.rstrip("\r\n") == heading), None)
    if start is None:
        _refuse("MANIFEST_SELECTOR_NOT_FOUND", f"{rel} has no {heading!r}")
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        opened = len(line) - len(line.lstrip("#"))
        if 0 < opened <= level:
            end = index
            break
    return "".join(lines[start:end]).encode("utf-8")


def _log_line(data: bytes, selector: str, rel: str) -> bytes:
    target = selector[len(_LOG_LINE):]
    for line in _decode(data, rel).splitlines():
        if line == target:
            return line.encode("utf-8")
    _refuse("MANIFEST_SELECTOR_NOT_FOUND", f"{rel} has no log line {target!r}")


def _current_bytes(record: dict, root: Path | str, fixture_root: Path | str) -> bytes:
    """The selected bytes as the CURRENT checkout presents them."""
    kind = record["EXTRACTION_KIND"]
    if kind == "IMMUTABLE_FIXTURE":
        path = _owned(fixture_root, record["ARCHIVED_FIXTURE"], "ARCHIVED_FIXTURE")
        return path.read_bytes()
    source = _owned(root, record["SOURCE_PATH"], "SOURCE_PATH")
    data = source.read_bytes()
    if kind == "WHOLE_FILE":
        return data
    if kind == "MARKDOWN_SECTION":
        return _markdown_section(data, record["SELECTOR"], record["SOURCE_PATH"])
    return _log_line(data, record["SELECTOR"], record["SOURCE_PATH"])


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_historical(manifest: dict, *, fixture_root: Path | str) -> dict:
    """Re-prove a recorded experiment from immutable evidence only.

    There is no current-source argument on purpose: this operation cannot read
    the checkout, so a fixture gap can never be silently filled by it. A missing
    or substituted fixture is ``HISTORICAL_MISMATCH``.
    """
    validate(manifest)
    rows = []
    any_mismatch = False
    any_unavailable = False
    for record in manifest["inputs"]:
        input_id = record["INPUT_ID"]
        if record["SENSITIVITY"] == "PRIVATE_EPHEMERAL":
            rows.append({"INPUT_ID": input_id,
                         "status": HISTORICAL_INPUT_UNAVAILABLE_BY_DESIGN,
                         "reason": "PRIVATE_PLAINTEXT_NOT_RETAINED"})
            any_unavailable = True
            continue
        fixture = record.get("ARCHIVED_FIXTURE")
        if fixture is None:
            rows.append({"INPUT_ID": input_id, "status": HISTORICAL_MISMATCH,
                         "reason": "FIXTURE_MISSING"})
            any_mismatch = True
            continue
        try:
            data = _owned(fixture_root, fixture, "ARCHIVED_FIXTURE").read_bytes()
        except (OSError, SailangError):
            rows.append({"INPUT_ID": input_id, "status": HISTORICAL_MISMATCH,
                         "reason": "FIXTURE_MISSING"})
            any_mismatch = True
            continue
        if _digest(data) != record["EXTRACTED_SHA256"]:
            rows.append({"INPUT_ID": input_id, "status": HISTORICAL_MISMATCH,
                         "reason": "FIXTURE_SUBSTITUTION"})
            any_mismatch = True
        else:
            rows.append({"INPUT_ID": input_id, "status": HISTORICAL_VERIFIED})
    if any_mismatch:
        verdict = HISTORICAL_MISMATCH
    elif any_unavailable:
        verdict = HISTORICAL_INPUT_UNAVAILABLE_BY_DESIGN
    else:
        verdict = HISTORICAL_VERIFIED
    return {"verdict": verdict, "manifest_identity": manifest_identity(manifest),
            "current_source_read": False, "inputs": rows}


def verify_current(manifest: dict, *, root: Path | str) -> dict:
    """Check the current checkout against the manifest's registered rules.

    Reports input drift and implementation drift independently. Neither result
    claims the historical experiment was rerun and neither authorizes a live
    run.
    """
    validate(manifest)
    rows = []
    input_drift = False
    for record in manifest["inputs"]:
        input_id = record["INPUT_ID"]
        if record["SENSITIVITY"] == "PRIVATE_EPHEMERAL":
            rows.append({"INPUT_ID": input_id,
                         "status": "CURRENT_INPUT_NOT_CHECKABLE_PRIVATE",
                         "reason": "PRIVATE_EPHEMERAL"})
            continue
        try:
            data = _current_bytes(record, root, root)
        except (OSError, SailangError) as exc:
            rows.append({"INPUT_ID": input_id, "status": CURRENT_INPUT_DRIFT,
                         "reason": getattr(exc, "code", "SOURCE_UNAVAILABLE")})
            input_drift = True
            continue
        if _digest(data) != record["EXTRACTED_SHA256"]:
            rows.append({"INPUT_ID": input_id, "status": CURRENT_INPUT_DRIFT,
                         "reason": "EXTRACTED_SHA256_DIFFERS"})
            input_drift = True
        else:
            rows.append({"INPUT_ID": input_id, "status": CURRENT_MATCH})
    components = []
    implementation_drift = False
    for component in manifest["implementation"]:
        try:
            data = _owned(root, component["PATH"], "PATH").read_bytes()
        except (OSError, SailangError):
            components.append({"PATH": component["PATH"], "ROLE": component["ROLE"],
                               "status": CURRENT_IMPLEMENTATION_DRIFT,
                               "reason": "IMPLEMENTATION_MISSING"})
            implementation_drift = True
            continue
        if _digest(data) != component["SHA256"]:
            components.append({"PATH": component["PATH"], "ROLE": component["ROLE"],
                               "status": CURRENT_IMPLEMENTATION_DRIFT,
                               "reason": "IMPLEMENTATION_HASH_DRIFT"})
            implementation_drift = True
        else:
            components.append({"PATH": component["PATH"], "ROLE": component["ROLE"],
                               "status": CURRENT_MATCH})
    if input_drift:
        verdict = CURRENT_INPUT_DRIFT
    elif implementation_drift:
        verdict = CURRENT_IMPLEMENTATION_DRIFT
    else:
        verdict = CURRENT_MATCH
    return {"verdict": verdict, "manifest_identity": manifest_identity(manifest),
            "inputs": rows, "implementation": components}


def admit_live(manifest: dict, *, root: Path | str, fixture_root: Path | str | None = None,
               network: object | None = None) -> dict:
    """Gate a future live experiment before network.

    Refuses with ``HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY`` for a
    ``HISTORICAL_ONLY`` manifest even when every hash matches,
    ``LIVE_PRIVATE_INPUT_UNVERIFIABLE`` when a required input is private,
    ``LIVE_INPUT_DRIFT`` when required current selected bytes do not match the
    registered ``EXTRACTED_SHA256``, and ``LIVE_IMPLEMENTATION_DRIFT`` when a
    required current implementation binding does not match its frozen hash.
    ``network`` is never invoked, on admission or on refusal.
    """
    validate(manifest)
    if manifest["authority"] != "LIVE_ELIGIBLE":
        _refuse("HISTORICAL_MANIFEST_NOT_LIVE_AUTHORITY",
                f"manifest authority is {manifest['authority']!r}")
    fixtures = Path(fixture_root) if fixture_root is not None else Path(root)
    for record in manifest["inputs"]:
        if not record["REQUIRED_FOR_LIVE"]:
            continue
        if record["SENSITIVITY"] == "PRIVATE_EPHEMERAL":
            _refuse("LIVE_PRIVATE_INPUT_UNVERIFIABLE",
                    f"{record['INPUT_ID']} is PRIVATE_EPHEMERAL and required for live")
        try:
            data = _current_bytes(record, root, fixtures)
        except (OSError, SailangError) as exc:
            _refuse("LIVE_INPUT_DRIFT",
                    f"{record['INPUT_ID']}: {getattr(exc, 'code', 'SOURCE_UNAVAILABLE')}")
        if _digest(data) != record["EXTRACTED_SHA256"]:
            _refuse("LIVE_INPUT_DRIFT", f"{record['INPUT_ID']} selected bytes changed")
    for component in manifest["implementation"]:
        try:
            data = _owned(root, component["PATH"], "PATH").read_bytes()
        except (OSError, SailangError) as exc:
            _refuse("LIVE_IMPLEMENTATION_DRIFT",
                    f"{component['PATH']}: {getattr(exc, 'code', 'IMPLEMENTATION_MISSING')}")
        if _digest(data) != component["SHA256"]:
            _refuse("LIVE_IMPLEMENTATION_DRIFT", f"{component['PATH']} changed")
    return {"admitted": True, "manifest_identity": manifest_identity(manifest),
            "network_calls": 0, "network_used": False}
