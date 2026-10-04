SAIMAIL

SAIHANDOFF — FUTURE GATE WAVE 6
TIME CAPSULES + CO-SIGNED FUTURE LETTERS

STATUS
FUTURE GATE. Build only after Future Letters and recovery semantics are solid.

INSPIRATION
AIPass Commons has provenance artifacts, co-signing and time capsules that refuse to open before their date.

PART A — TIME-LOCKED FUTURE LETTERS
Fields: created_at, not_before, optional expires_after, author identity, custody mode, title/audience/tags, canonical body hash.

Before not_before:
- metadata may be visible according to policy
- plaintext open refuses and names eligible time
- no automatic prompt injection or execution

After not_before:
- explicit open works
- content remains inert historical data

PART B — CO-SIGNED LETTERS
- canonical object/body hash fixed before signing
- multiple identities sign the same object
- each signature inspectable
- missing signer => PARTIALLY_SIGNED, never fake-complete
- body mutation after one signature invalidates verification

PART C — SUCCESSOR AUDIENCE
Optional audience metadata: specific seat, successor-of-seat, project maintainers, operator.
Audience is metadata, not access control unless custody binds it.

ACCEPTANCE
- early open refuses deterministically
- post-date open survives restart
- co-sign mutation detected
- signatures survive archive/export/import
- content remains non-authoritative inert data

NON_GOALS
DRM, automatic execution at date, automatic model-context injection.
