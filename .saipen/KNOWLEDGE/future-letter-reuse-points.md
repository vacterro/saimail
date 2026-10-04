# Future letters: canonical reuse points (T-161)

Durable, promotion-qualified: reuse points a future feature needs and which no
other card records.

## Reuse, do not rebuild

- `saimail/workspace.py::_seal_deliver` is the ONE canonical seal+deliver path.
  It takes a `sailang.Record`, so a payload that is not a SAILANG record needs a
  sibling that accepts raw payload bytes. Do not hand-build SENV2 bytes.
- `saimail/workspace.py::Workspace` exposes `sender_private_key` and
  `recipient_private_key`; `identity` projects both public halves. Self-sealing
  (sender = recipient = the same seat) is legal without registering a peer.
- `saimail/postoffice.py::PostOfficeSession.open_message` / `reopen_message`
  are the existing explicit open gates; they need no change to open a non-SAILANG
  payload, only a different parse step by the caller.
- `saimail/envelope.py::KINDS` is the closed SENV2 kind set; adding a value is
  additive and does not change any existing header.

## Shape constraint that shaped the design

`sailang.Record` is one `KEY:VALUE` per line with a closed field set and a
one-line `CLAIM`, so a multi-line future-letter body cannot ride inside a
SAILANG record. The letter body therefore travels as its own canonical
container sealed by SENV2, not as record text.

## Canonical verification

`python -m pytest -q` from the project root. See VERIFICATION.md.