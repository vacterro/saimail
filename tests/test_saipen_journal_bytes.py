"""The SAIPEN journal is a byte-pinned corpus input, so its bytes are a test.

`lab/project_corpus_pilot_registration.json` registers `.saipen/LOG.md` by
`LOG_RECORD` markers and `lab/project_corpus_pilot.py::_prove_append_only_recovery`
re-extracts those records on every corpus run, refusing with
`PROJECT_PILOT_SOURCE_CHANGED` when a digest no longer matches. Growth is legal;
drift is not. Two ordinary-looking mistakes break it silently, and both happened
in T-161:

- appending the journal through a text-mode write rewrites every line ending to
  CRLF, which changes every registered record's bytes;
- quoting a bracketed pinned marker inside a new entry makes that marker appear
  twice, and `extract_log_record` refuses with
  `PROJECT_PILOT_SELECTOR_DUPLICATE` instead of picking one.

Both fail the historical corpus suite (124 tests in T-161's case) with no hint
that the journal was the cause. These two assertions turn each mistake into one
failing test at the moment it is committed.
"""

import json
from pathlib import Path

import pytest

from lab import project_corpus_pilot as pcp

ROOT = Path(__file__).resolve().parents[1]
JOURNAL = ROOT / ".saipen" / "LOG.md"
REGISTRATION = ROOT / "lab" / "project_corpus_pilot_registration.json"


@pytest.fixture(scope="module")
def journal_bytes() -> bytes:
    assert JOURNAL.is_file(), f"missing {JOURNAL}"
    return JOURNAL.read_bytes()


def _log_selectors() -> list[dict]:
    registration = json.loads(REGISTRATION.read_bytes())
    return [entry for entry in registration["artifacts"]
            if entry["source"] == ".saipen/LOG.md"]


def test_the_journal_keeps_the_line_endings_its_registered_records_were_frozen_with(journal_bytes):
    """CRLF rewrites every historical record's bytes, so the journal stays LF.

    `.gitattributes` declares `*.md text eol=lf`, which is what the frozen
    content pins were computed from; a CRLF journal still passes git's own
    normalization and only breaks the registration at run time.
    """
    assert b"\r\n" not in journal_bytes, (
        f"{JOURNAL.name} contains CRLF line endings; the registered LOG records "
        "were frozen as LF, so every one of them now hashes differently and the "
        "historical corpus suite refuses with PROJECT_PILOT_SOURCE_CHANGED. Write "
        "the journal in binary mode with LF: append with open('ab') and write "
        "bytes, never read_text/write_text over the whole file."
    )


@pytest.mark.parametrize("entry", _log_selectors(),
                         ids=[entry["label"] for entry in _log_selectors()])
def test_a_pinned_record_marker_is_quoted_exactly_once(journal_bytes, entry):
    """A new entry that quotes the marker verbatim would make the selector ambiguous.

    `extract_log_record` rejects a duplicate marker rather than guessing which
    record was meant, so this is a hard refusal, not a warning.
    """
    marker = entry["selector"]["marker"]
    occurrences = journal_bytes.decode("utf-8").count(marker)
    assert occurrences == 1, (
        f"{marker} appears {occurrences} times in {JOURNAL.name}; the registered "
        f"record {entry['label']} is selected by that marker, so the corpus "
        "extractor refuses with PROJECT_PILOT_SELECTOR_DUPLICATE. Write the "
        "marker without its brackets when you need to mention it in prose."
    )


def test_every_registered_journal_record_still_extracts_to_its_pinned_digest(journal_bytes):
    """The end-to-end form: what the corpus actually runs, on the real journal."""
    registration = json.loads(REGISTRATION.read_bytes())
    text = pcp._decode_source(journal_bytes, ".saipen/LOG.md")
    for entry in _log_selectors():
        content = pcp.extract_selected_content(text, entry["selector"])
        assert pcp._sha256_text(content) == entry["extracted_content_sha256"], (
            f"registered record {entry['label']} no longer matches its frozen "
            "content pin"
        )
