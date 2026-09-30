# T-120 REVIEW
- Independent `python -m pytest -q` (clean env): see review-full.xml; STATE/BOARD/LOG
  hash unchanged around the run.
- Verifier changes: new `tests/test_participants.py`; oracle additive (0 removed
  lines); `tests/test_turn_entry_headers.py` gained only an autouse env fixture
  (no assertion changed) to remove a carrier dependency found in VERIFY.
- Final bytes of `saimail/participants.py`: resolution checks project, seat,
  trigger, self and pinned identity before returning an alias; admission pins the
  current identity and refuses silent change; the file is read strictly; writes
  are atomic under an OS lock; no `.saipen` name; keyless.
- No P0/P1. Memory promotion: YES as a Claude memory note only (carrier leak in
  test runs), no project KNOWLEDGE card.
- Verdict: DEC: SHIP.
