# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-054 — the next distributed candidate keeps raw custody as default, and its identity is 0.0.2a2 (T-90 / D1)

The defect class is release folklore: an old wheel's proof silently becoming the
proof of different code, a version string standing in for artifact bytes, and a
publication step happening without an explicit decision. D1 compiles the
decision from evidence and gates publication on operator authorization.

**Frozen artifact.** The frozen `0.0.2a1` wheel
(`ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a`)
predates V3-01. Mechanical inspection of the wheel: 57 members, no
`saimail/custody.py`, identity schema `SAIMAIL_LOCAL_IDENTITY_1` only, and no
`--custody` / `os-store` surface in the bundled CLI. The external Linux /
Python 3.13.5 proof remains fully valid for exactly those bytes and is not
transferable to the current checkout. The frozen candidate is classified
`HISTORICAL_VERIFIED_ALPHA`; the current source is `CURRENT_SOURCE_CAPABILITY`.
Outcome: `NEW_CANDIDATE_REQUIRED`.

**Custody default.** `KEEP_RAW_DEFAULT` for new workspaces in the next
distributable candidate. Rationale, from evidence rather than preference:

* the core package's zero-required-dependency install contract is documented in
  `pyproject.toml`, the README, D-052 and D-053; an `os-store` default would
  put `keyring` on the ordinary install path or force a silent degradation,
  and silent degradation is already excluded by spec/20;
* the OS-store backend is proven on the Windows host only (WinVaultKeyring
  classification plus one disposable real-vault smoke); the external proof
  environment is Linux, where no backend for this namespace has been verified —
  shipping it as the default would make an unproven platform path primary;
* requiring an explicit choice (option C) would break the documented
  `init --workspace` compatibility and scripting surface without an observed
  need.

The residual risk (a copied default workspace is a copied identity; threat
cases A/B in spec/20) stays explicit. D2 must carry the custody warning on the
first-run surface without changing the default, and the default is re-evaluated
only when a second supported platform has verified OS-store backend evidence.

**Version.** The frozen artifact stays `0.0.2a1`. The next candidate is a new
prerelease identity, `0.0.2a2` — the smallest PEP 440 progression within the
same alpha line (`V3-01` is additive). The source checkout keeps declaring
`0.0.2a1` until D2 owns the version bump, as D1 is not the rebuild gate; the
intentional temporary difference is recorded because artifact identity is the
exact wheel SHA-256, never the version string (D-052).

**Publication.** G17 (explicit operator publication authorization) is required
and currently `ABSENT`; `publication = NONE`, `publication_status =
NOT_PUBLISHED`. Publication mechanics are documented as five separated stages
(local candidate build, Git commit, Git tag, GitHub release, package-index
upload) in `release/evidence/release_decision.json`; a package-index upload
convention is `NOT_ESTABLISHED` in this repository. D1 executes no stage.

**Evidence.** `tools/release_decision.py` (inputs collection and packet
validation with mechanical refusals), `release/evidence/release_decision.json`
(`SAIMAIL_RELEASE_DECISION_1` v1), `release/evidence/release_decision_inputs.json`
(`SAIMAIL_RELEASE_DECISION_INPUTS_1` v1), `release/evidence/RELEASE-DECISION.md`
(human report), `tests/test_release_decision.py` (focused proofs: hash
immutability, delta detection, proof-binding refusal, publication default,
claim-boundary honesty, no secrets) and the locale-mirror consistency test in
`tests/test_repo_consistency.py`.

Regression evidence: `spec/21-RELEASE-DECISION-v0.md`,
`release/evidence/external_proof_acceptance.json`.

---
