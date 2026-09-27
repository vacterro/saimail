# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-058 — SAITELEMES v0 is an ordinary sealed message on existing kinds, sent only by the acting seat, read header-only at turn entry (T-109)

The defect class is a finding that stalls in the wrong place. When one running
agent learns something that belongs to another running agent, the fact waited for
a human relay or sat in a cold inbox. T-108 measured it: the SAIPEN protocolist
heard about three defects only after the operator asked, and the host's
cross-session message expired unapproved in the recipient session.

**Decision.** A telegram (SAITELEME) is one ordinary sealed SAIMAIL message sent in
one call (`saimail-local saipen telegram`) and found in one call
(`saimail-local saipen telegrams`). Contract: `spec/26-SAITELEMES-v0.md`.

- **No new wire.** The kind comes from the closed SENV2 set (default `DISCOVERY`).
  `TELEGRAM` is refused as `BAD_INPUT`. The TOPIC carries the SAIPEN Work id, which
  lets a receiver filter one audit exactly, with the existing P1 `topic` filter.
- **No sender urgency.** Nothing in a telegram asks for attention. The receiver's
  scan budget and explicit `open` decide, as spec/07 already requires.
- **Only the acting seat sends.** A workspace whose seat differs from the acting
  SAIPEN seat (`--seat` > `SAIPEN_AGENT` > `STATE.agent`) refuses with
  `SAIPEN_SEAT_MISMATCH` and delivers nothing. This closes, on the SAIMAIL side,
  the misattribution T-108 found in SAIPEN's own actor inheritance.
- **Body.** Exactly one of the ordinary claim wrapper (`EV:0`, `U1`) or the D-057 S2
  citation of one LOG event, which the receiver re-derives with `saipen verify`.
- **Turn-entry read.** `telegrams` is the P1 metadata query at `state=UNREAD`,
  bounded, header-only. It opens nothing and needs no SAIPEN project.

**Boundary.** SAIMAIL does not make SAIPEN send or read telegrams by itself. That
trigger and turn-entry hook are SAIPEN protocol changes. They are filed as a future
gate with the protocolist (`_SAIPEN/future_gate/FUTURE GATE — SAITELEMES AUTOMATIC
AGENT TELEGRAMS_20260922.md`). The protocolist acknowledged receipt and triages
after its current Work. The first draft of that note named a `TELEGRAM` kind; it
was corrected before triage to match this decision.

**Evidence.** `tests/test_saitelemes.py`: claim and citation telegrams delivered
under the Work topic; the turn-entry read finds them without opening; a
seat-mismatched send is refused and delivers nothing; no-body, two-body and
out-of-set kinds (including `TELEGRAM`) are refused; the topic falls back and
filters; command-looking claim text stays data; nothing under SAIPEN memory is
written; CLI send and a project-free turn-entry read work.
