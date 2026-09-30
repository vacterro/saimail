# T-121 BUILD: V6-07 SAIMAIL half, capability document (SRC-108 item 5)

Defect class eliminated: an orchestrator that learns whether the mail channel
works only by calling it and parsing a failure.

- New `saimail/capabilities.py`: `SAIMAIL_CAPABILITIES_1` document; never raises
  for a state; SAIOPP states; closed reasons; seat mismatch -> UNAVAILABLE with no
  counts; signing UNVERIFIED (keys untouched); header view only.
- `saimail_local.py`: `saipen capabilities` (project optional; binding failures
  degrade to PROJECT_NOT_BOUND). `saimail/workspace.py`: renderer lines only.
- API map entry; `tests/test_capabilities.py` (10); V6-07 oracle (additive).
- Red controls: six source mutants caught (`red-controls.txt`).
- Docs: spec/30, D-062, roadmap row + subsection, CURRENT-STATE, Work Desk guide
  (capabilities, participant admission, outbox), CHANGELOG.
- Line-ending slip caught and fixed during BUILD: the snippet helper inserted LF
  lines into CRLF `saimail_local.py` and `saimail/workspace.py`; both restored to
  pure CRLF (their before copies were pure CRLF) and the helper now renders the
  replacement with the line break found at the match.
