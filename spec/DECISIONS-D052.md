# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-052 — the local alpha candidate is an exact hashed artifact, not a version number (T-86 / V2-04)

The defect class is a release claim that cannot be checked: a version string,
a rebuilt wheel, and "the same" package drifting apart silently while every
document still reads as if one exact candidate had been verified. V2-04 turns
the proven V2-01 local workflow into a deliberately scoped local alpha
candidate without publishing it.

**Identity.** The candidate identity is `0.0.2a1`, a PEP 440 prerelease of the
0.0.1 baseline. No fake final release version is minted: the alpha is an alpha.
The authoritative version surfaces are `pyproject.toml`, `VERSION`,
`saimail_local._VERSION_FALLBACK`, `lab/stable_local_api.json.release`, the
candidate manifest and the built wheel metadata. No new version-management
subsystem is introduced; one consistency test enforces agreement, which is the
narrowest reliable source of truth boundary.

**Candidate = artifact.** The frozen candidate is exactly one wheel file
identified by SHA-256, recorded in `LOCAL_ALPHA_CANDIDATE_1` v1. A wheel whose
bytes differ is a new candidate with a new manifest and a new hash; the old
hash is never reused. Rebuild byte differences caused by packaging-tool
nondeterminism are documented, and content equality is proven per member file
instead of faking byte equality.

**Scope.** The alpha claims local filesystem messaging only: persistent V2-01
workspaces, explicit public-card exchange, deterministic recipient
registration, the current SENV2/Post Office semantics, and the documented
`saimail-local` command workflow. The demonstrated platform is CPython 3.11 on
win32; no broader portability is claimed. The alpha does not claim a hosted
service, LAN/internet transport, Gmail/Slack/Outlook or any adapter, a daemon,
hardened key custody or encryption at rest, key rotation, automatic
correspondence, semantic reviewer reliability, universal utility, or
production service readiness. Measured verdict `UTILITY_CONDITIONAL` is carried
unchanged. The V2-01 limitation carries forward: private keys are raw software
files protected only by filesystem permissions where supported.

**Publication.** Building, hashing and locally verifying the candidate is
release readiness, not publication. `publication_status = NOT_PUBLISHED` is a
manifest field. No push, tag, PyPI upload or GitHub release occurs in V2-04;
publication remains a separate explicit operator action.

**Verification.** One bounded procedure (`verify_local_alpha.py`, result schema
`LOCAL_ALPHA_VERIFICATION_1` v1) verifies the installed candidate from outside
the checkout: it hashes the actual wheel, installs it into a fresh environment,
runs `saimail-local --version`, the stable API map check, FG-05, FG-06 and the
V2-01 acceptance workflow, and reports runtime network and model counters
separately from dependency installation. Integrity and privacy gates carry
red controls: a corrupted wheel or recorded hash must be rejected, and a
planted privacy marker must be detected. A candidate that fails verification
is repaired, rebuilt and re-hashed; the old manifest is never silently reused.

**Not publication, not another gate.** V2-04 introduces no new protocol
semantics, no network path, no model call and no change to
`LOCAL_SCENARIO_RESULT_1`, `FG06_UTILITY_RESULT_1`,
`LOCAL_WORKSPACE_COMMAND_1` or `LOCAL_WORKSPACE_RESULT_1`.

Regression evidence: `spec/18-LOCAL-ALPHA-v0.md`,
`tools/local_alpha_release.py`, `tools/verify_local_alpha.py`,
`tools/scan_local_alpha_privacy.py`, `tests/test_local_alpha_release.py` and
the extended `tests/test_clean_install.py`.

---
