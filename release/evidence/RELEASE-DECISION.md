# SAIMAIL — D1 release decision packet (human report)

Machine-readable packet: `release/evidence/release_decision.json`
(`SAIMAIL_RELEASE_DECISION_1` v1). Inputs:
`release/evidence/release_decision_inputs.json`
(`SAIMAIL_RELEASE_DECISION_INPUTS_1` v1). Contract:
`spec/21-RELEASE-DECISION-v0.md`. Decision: `spec/DECISIONS-D054.md`.

## Outcome

**`NEW_CANDIDATE_REQUIRED`.** This is a successful D1 closure, not a blocker.

The frozen `0.0.2a1` wheel is a real, externally verified artifact — of the
code that existed before V3-01. The current checkout is not that code, and no
distributable artifact of the current checkout exists.

## Frozen artifact

| | |
|---|---|
| Wheel | `saimail-0.0.2a1-py3-none-any.whl` |
| SHA-256 | `ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a` |
| Size / members | 370,976 bytes / 57 |
| Content digest | `d060491b6fe865e6844f353aaa691d97eaa92db7e1a75c13617e658993bdab8f` |
| Classification | `HISTORICAL_VERIFIED_ALPHA` |
| Publication | `NOT_PUBLISHED` |

Mechanical inspection of the wheel: **no `saimail/custody.py`**, identity schema
`SAIMAIL_LOCAL_IDENTITY_1` only, no `--custody` or `os-store` surface in the
bundled CLI. The external Linux / Python 3.13.5 proof binds exactly these bytes
and is not transferable to any other wheel.

## Current source delta

`POST_CANDIDATE_SOURCE_DELTA = V3-01`. The checkout adds:
`saimail/custody.py`, identity schema `SAIMAIL_LOCAL_IDENTITY_2`,
`init --custody os-store`, `custody status`, `custody migrate`, named
`CUSTODY_*` failure semantics and copied-workspace protection in protected mode.
Proven locally (focused tests with injected stores plus one disposable real-vault
smoke); **not externally proven as an artifact**.

## Version decision

* `CURRENT_FROZEN_ARTIFACT_VERSION` = `0.0.2a1`
* `CURRENT_CHECKOUT_DECLARED_VERSION` = `0.0.2a1`
* `NEXT_CANDIDATE_VERSION` = `0.0.2a2`

The intentional temporary difference: the checkout still declares `0.0.2a1`
while containing post-freeze code. Artifact identity is the exact wheel SHA-256,
never a version string (D-052); D2 owns the version-surface bump when it builds
and freezes the new wheel.

## Custody default decision

**`KEEP_RAW_DEFAULT`** for new workspaces in the next distributable candidate
(D-054). Rationale from evidence: the zero-required-dependency core install
contract is documented; OS-store backend evidence exists on Windows only, while
the external proof environment is Linux — a protected default would make an
unproven platform path primary; an explicit-choice requirement would break the
documented `init` compatibility without an observed need. D2 must carry the
custody warning on the first-run surface without changing behavior, and the
default is re-evaluated only with verified backend evidence on a second
supported platform.

## Support scope

Local filesystem messaging only; CPython `>=3.11`. Demonstrated for the frozen
candidate: win32 / Python 3.11 locally and Linux / Python 3.13.5 externally.
The next candidate's scope is `UNCHANGED_UNTIL_PROVEN` and must earn its own
external evidence (G13).

## Claims boundary (summary)

* **Proven for the frozen `0.0.2a1`:** installability, stable local CLI,
  persistent workspace, send/list/open/restart/dedup, FG-05, FG-06
  (`UTILITY_CONDITIONAL`), external install, Windows and Linux evidence, raw
  custody, zero runtime network/model calls, privacy and integrity checks.
* **Proven for the current checkout (locally):** all of the above plus
  os-store custody, custody migration and copied-workspace protection — local
  evidence only, no external proof.
* **Not yet proven for a distributable post-V3-01 artifact:** the new wheel's
  identity/hash, its clean install, its external install proof, its privacy and
  integrity red controls, the shipped custody default, `0.0.2a2` version
  surfaces and publication authorization.

The full matrix with evidence references is in the JSON packet.

## Residual risks

Raw default copied-identity risk; same-user malware and admin/kernel compromise
not protected; os-store loss/migration availability; the credential store as an
operational dependency; `UTILITY_CONDITIONAL`; semantic reviewer reliability
not demonstrated; inherited SAIPEN debt (3 FAIL / 21 WARN) plus
`SAIPEN_DIGEST_DRIFT`; T-75 blocked on historical accounting; dirty worktree
(SHA-256 is the only candidate identity); no package-index convention.

## Metadata status

Locale README mirrors corrected (`v0.0.1` → `v0.0.2a1`) with a
repo-consistency test deriving the expected value from `VERSION`; version
surfaces agree; the frozen bundle is untouched; the `0.0.2a2` CHANGELOG section
belongs to the next candidate gate.

## GO / NO-GO gates

G1 version consistency, G2 package content, G3 custody default, G4 custody
security, G5 clean install, G6 local workflow, G7 FG-05, G8 FG-06, G9 custody
acceptance, G10 integrity, G11 privacy, G12 zero runtime network/model, G13
external install, G14 documentation, G15 full suite, G16 SAIPEN, G17 explicit
operator publication authorization. All 17 apply to the next candidate; G17 is
`ABSENT` today, so publication is forbidden regardless of engineering status.

## Publication mechanics (documented, not executed)

1. local candidate build (`tools/local_alpha_release.py build`);
2. Git commit;
3. Git tag (`v0.0.2a2` template; latest existing tag is `v0.0.1`);
4. GitHub release (a `v0.0.1` release surface exists from T-54);
5. package-index upload — `NOT_ESTABLISHED` in this repository, not required
   unless the operator establishes a convention.

No stage was executed; no push, tag, release or upload; no service was
authenticated to.

## Publication authorization and status

`publication_authorization = ABSENT`; `publication = NONE`;
`publication_status = NOT_PUBLISHED`.

## Next target

**D2 — Post-V3-01 release candidate refresh**, `NOT_STARTED` (not started inside
D1).
