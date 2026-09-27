# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-055 — D2 freezes 0.0.2a2 as the post-V3-01 candidate, with the first-run custody notice and a separate evidence identity (T-91 / D2)

The defect class is release folklore at the next increment: the V3-01 custody
implementation exists in the checkout but no artifact carries it, a new wheel
would silently inherit the old wheel's proof, and an operator creating a
default workspace could still believe raw file custody is protection. D2
freezes a new candidate, makes the default mode honest at first contact, and
re-earns every artifact-specific claim.

**Version and identity.** The current source and candidate version is
`0.0.2a2` (PEP 440 prerelease). The frozen `0.0.2a1` bundle at
`release/local-alpha/` stays byte-identical and `NOT_PUBLISHED`; the new
candidate lives at `release/candidates/0.0.2a2/`. Artifact identity remains the
exact wheel SHA-256 (D-052), never the version string.

**Custody default.** `KEEP_RAW_DEFAULT` from D-054 is implemented unchanged:
`init --workspace DIR --seat SEAT` stays raw, no new mandatory option exists,
and `--custody os-store` remains the explicit opt-in requiring the
`credentials` extra and a checked backend. A requested protected custody never
silently falls back.

**First-run notice (D-054 requirement).** Creating a new workspace returns one
bounded machine-readable notice plus a human `NOTICE:` rendering:
`RAW_CUSTODY_DEFAULT` for a raw workspace (implicit default and explicit
`--custody raw` alike) and `OS_STORE_CUSTODY` for a protected one. The raw
text states: raw is the default; private Ed25519/X25519 keys are stored in the
workspace; copying the workspace copies the identity; `--custody os-store` is
available where a checked backend exists; os-store protects against
workspace-directory-copy exposure, not same-user malware or admin/kernel
compromise. `ALREADY_EXISTS` is not a first run and carries no notice; later
commands never repeat it. The surface is additive:
`SAIMAIL_CUSTODY_NOTICE_1` v1 in the `notices` field of the creating
`LOCAL_WORKSPACE_COMMAND_1` result (spec/17 section 8 addendum, spec/20
section 7).

**Release tooling truth.** `tools/local_alpha_release.py` no longer carries
pre-V3-01 blanket wording: the candidate manifest separates the raw default
from the optional protected mode (`custody` block), records the
mode-accurate security limitations, mechanically proves the V3-01 custody
surface inside the built wheel (`content_proof`,
`LOCAL_ALPHA_WHEEL_CONTENT_PROOF_1`) and refuses to build into the historical
a1 bundle or to overwrite any frozen candidate.

**Evidence.** A new wheel means new evidence; nothing artifact-specific is
inherited from a1. Evidence set: `release/evidence/a2/`
(`local_alpha_verification.json` installed-wheel base verification,
`windows_os_store_proof.json` installed-wheel WinVault acceptance plus the
injected-store migration proof, `reproducibility.json` two-build content and
behavior comparison, `privacy_controls.json` and `integrity_controls.json`
with red controls, `claim_matrix.json`, `gate_evaluation.json`). The verifier
result separates base candidate verification from platform-specific os-store
verification explicitly.

**Publication.** `publication = NONE` and `publication_authorization = ABSENT`
(D1/G17). D2 stops before publication. At first freeze the one open engineering
gate was G13: the exact `0.0.2a2` wheel had no external separate-environment
proof yet, so D2's truthful terminal state was
`READY_FOR_EXTERNAL_INSTALL_PROOF`. The closure addendum below records the
supplied external proof that closes G13 without touching publication.

**Regression evidence.** `tests/test_release_decision.py` (D1 history
unchanged, surfaces agree with the canonical VERSION),
`tests/test_local_alpha_release.py` (candidate manifest, content proof,
custody truth, verifier), `tests/test_first_run_custody_notice.py` (notice
semantics), `tests/test_a2_release_candidate.py` (a1 immutability pins, build
guards, evidence binding, gate matrix), `tests/test_clean_install.py`,
`tests/test_workspace_custody.py`.

## Closure addendum — G13 satisfied by the supplied external proof (T-92)

The operator supplied the separate-environment proof of the exact frozen
`0.0.2a2` wheel: `LOCAL_ALPHA_VERIFICATION_1` v1, `PASS`, generated on Linux /
Python 3.13.5 with the bundle's own bundled verifier
(`python verify_local_alpha.py --bundle . --out verification --offline`). The
proof bytes are stored byte-identically at
`release/evidence/a2/external_linux_verification.json` (SHA-256
`2d77e13dd1e414e8642fb5a1b60e216e2136bb267bf1789c7e1169adfaa1d5c2`), the
acceptance record is
`release/evidence/a2/external_verification_record.json`, and G13 is `PASS`, so
D2's terminal state is `DONE` (`release/evidence/a2/gate_evaluation.json`).

**Claim boundary preserved.** The external proof validates the base candidate
path only: exact wheel identity, clean install, package/version identity,
shipped custody code/content, raw-default workflow, first-run custody notice,
FG-05, FG-06 `UTILITY_CONDITIONAL`, V2-01, privacy and zero runtime
network/model/provider calls. It reports `os_store_platform_verification:
NOT_TESTED_HERE`; Linux os-store support is **not** claimed and the independent
Windows installed-wheel `WinVaultKeyring` evidence stays the os-store platform
authority. Publication remains `NONE` with authorization `ABSENT` (G17).

---
