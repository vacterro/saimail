# T-113 continuation after D3 closure

SRC-102 contains two outcomes. The user-confirmed `humbox/SAIGIMN.mp3` asset
stays in SAIMAIL; a verified stream-copy preserved the decoded PCM SHA256 but
made the MP3 4 bytes larger, so there is no useful lossless compression and
the original bytes remain authoritative. T-107 may now use a narrow manifest
bound to SRC-102 and the exact asset hash.

The requested follow-on product improvement is receiver re-read continuity.
The relevant code path was SCOUTed: durable `read/<seat>/<digest>/` bundles
retain the sealed container and receipt; `PostOfficeSession.open_message`
only accepts UNREAD and moves the bundle once; GUI selection is metadata-only;
TTL sweep also expires READ bundles. A safe implementation needs a distinct
explicit `reopen_message` path, never reuse first-open semantics, require READ,
hold the lifecycle lock, re-verify bundle/receipt/index/sender/recipient,
honor expiry and crash-refusal behavior, spend the open budget, leave READ
state and bytes unchanged, and persist no plaintext. Add separate local CLI
`reopen` and GUI `Reopen` controls. Keep `Open`, selection, refresh and
double-click behavior unchanged.

T-107's active acceptance requires V6-02 to remain NOT STARTED. Therefore do
not implement the reread path until T-107 is DONE. Exact discovery targets:
`saimail/postoffice.py`, `saimail/workspace.py`, `saimail/gui_adapter.py`,
`saimail/gui_app.py`, `saimail_local.py`, `lab/stable_local_api.json`,
`tests/test_postoffice_scan.py`, `tests/test_local_workspace.py`,
`tests/test_gui_surface.py`, `tests/test_local_entrypoint.py`,
`spec/03-POST-OFFICE.md`, `spec/25-DESKTOP-LOCAL-MESSENGER-v0.md`, and README.
Canonical test command: `python -m pytest -q`.
