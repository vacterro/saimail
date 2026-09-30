"""Canonical README source-digest for the saitranslate producer.

`phases/translate.md` states the marker rule in prose -- a locale README ends
with `<!-- source-digest: README.md sha256:<16 hex> -->` computed from the
current `README.md` -- and that prose admits several readings. Two producer
runs proved the cost: the first stamped a marker the next run could not
reproduce, and the second tried fifteen prose-literal readings before finding
the executable one. There is exactly one definition, and it is not here:

    <saipen_home>/tools/freshness.py
        VERSION_TOKEN_RE, normalize_version_strings, source_content_digest,
        digest_marker_matches

This module imports those three names rather than restating them, so a
producer marker and the gate that reads it can never disagree about the
recipe. The validator's own branch (`tools/validate.py`, the translation
digest check) calls the same functions.

Touches only .saipen/saitranslate/kitchen/. Reads the main tree, writes
nothing. Self-checks when run directly: a version bump must not move the
digest, prose drift must, and a wrong marker must still read stale.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MARKER_RE = re.compile(r"<!-- source-digest: README\.md sha256:([0-9a-f]+) -->")
SAIPEN_HOME = Path(r"V:\___VAC\__K\__CODE\_AI_STUFF_AGENTIC\_SAIPEN")
sys.path.insert(0, str(SAIPEN_HOME / "tools"))

try:
    from freshness import (  # noqa: E402
        digest_marker_matches,
        normalize_version_strings,
        source_content_digest,
    )
except ImportError as exc:  # pragma: no cover - a missing home is an operator fact
    raise SystemExit(
        f"canonical source-digest recipe unavailable at {SAIPEN_HOME / 'tools'}: {exc}"
    ) from exc


def source_digest(readme: Path) -> str:
    """Full 64-hex digest of README.md with version tokens normalised out."""
    return source_content_digest(readme.read_text(encoding="utf-8-sig"))


def marker_prefix(readme: Path, length: int = 16) -> str:
    return source_digest(readme)[:length]


def check(locale_readme: Path, canonical_readme: Path | None = None) -> bool:
    """True when the locale payload carries the current canonical marker."""
    canonical_readme = canonical_readme or (ROOT / "README.md")
    match = MARKER_RE.search(locale_readme.read_text(encoding="utf-8-sig"))
    return match is not None and digest_marker_matches(
        match.group(1), source_digest(canonical_readme)
    )


def _self_check() -> None:
    # A numeric bump must not move the digest.
    assert normalize_version_strings("v1.2.3") == normalize_version_strings("v4.5.6")
    # Neither must a pre-release suffix bump: the defect T-127 fixed.
    assert normalize_version_strings("v0.0.2a3") == normalize_version_strings("v0.0.2b1")
    # Prose drift must.
    assert source_content_digest("v1.2.3 alpha") != source_content_digest("v1.2.3 beta")
    # A wrong digest must still read stale, at either documented width.
    assert digest_marker_matches("deadbeef12345678", "f" * 64) is False
    assert digest_marker_matches("f" * 64, "f" * 64) is True

    kitchen = ROOT / ".saipen" / "saitranslate" / "kitchen"
    for name in ("README.ja.md", "README.uk.md"):
        payload = kitchen / name
        if payload.is_file():
            print(f"{name}: {'current' if check(payload) else 'STALE'}")


if __name__ == "__main__":
    _self_check()
    sys.exit(0)
