# T-121 SCOUT: V6-07 SAIMAIL half, capability and health surface (SRC-108 item 5)

Requirement: capability negotiation on entry (schema/API version, mailbox, seat,
workspace health, secret-free header capability); incompatibility gives DEGRADED
instead of breaking `saipen continue`; health shows configured seat, peer count,
pending outbox, unread header count, retry count, oldest pending age, last
delivery, last error class, API compatibility, degraded capabilities; no plaintext.

Facts: SAIPEN T-1497 today calls `saipen telegrams` (counts only, no seat check,
refusal code read from the wrong field). The header view (D-059), outbox status
(D-060) and participant registry (D-061) are all keyless, so one keyless call can
report everything. `_saipen_project` raises when no project is found; the new
command must degrade instead.

Design: `saimail/capabilities.py` + `saimail-local saipen capabilities`: never
exits non-zero for a state; SAIOPP capability states; closed reason codes; the
awareness counts only when the acting seat equals the workspace seat (the
SAIMAIL-side answer to SAIPEN finding 3); signing reported UNVERIFIED because no
key is touched. SAIPEN switches to it in its V6-07 half.
