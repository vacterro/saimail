SAIMAIL

SAIHANDOFF — FUTURE GATE WAVE 1
TRUST PINS + IDENTITY CONTINUITY

STATUS
FUTURE GATE. Start only after current Future Letters/recovery work is accepted and baseline is green.

INSPIRATION
AIPass trusts a specific enrolled config hash rather than a directory name, and treats persistent identity as separate from transient sessions.

GOAL
Make SAIMAIL answer without guessing:
- Is this the same peer I trusted?
- Did its key rotate legitimately?
- Is this a new identity reusing an old display name?
- Why is it trusted/refused right now?

BUILD
- Versioned trust-pin registry.
- States: UNKNOWN, OBSERVED, TRUSTED, ROTATION_PENDING, REVOKED, BLOCKED/COMPROMISED if useful.
- Pin canonical key fingerprint, first_seen, accepted_at, trust_source, policy/schema version.
- Key-rotation receipt: old identity authenticates transition where possible; new key proves possession.
- Display-name equality never proves continuity.
- Model/version metadata stays separate from stable agent/seat identity.
- Policy/config affecting trust should itself be versioned/hashed so material policy changes are visible.
- CLI/API equivalents: show peer, trust, revoke, inspect rotation chain, explain decision.

INVARIANTS
- No trust by path alone.
- No trust by display name alone.
- No silent key substitution.
- Revocation survives restart.
- Trust records are evidence, never instructions.

ACCEPTANCE
- same identity/key remains trusted
- same display name + unrelated key is not silently trusted
- valid rotation preserves lineage
- revoked peer stays refused after restart
- corrupt trust state fails visibly
- ordinary mail + Future Letters remain green

NON_GOALS
Global PKI, blockchain, automatic transitive web-of-trust.
