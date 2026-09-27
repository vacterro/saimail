# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-056 — D3 freezes 0.0.2a3 as the post-GUI candidate, with an additive a3 evidence identity and no inherited a2 proof (T-106 / D3)

The defect class is release folklore at the third increment: the checkout is
materially ahead of the frozen `0.0.2a2` candidate (P1 inbox query, V4-01
correspondence continuation, V5-01 desktop GUI), yet the tree still declares
`0.0.2a2`; an old wheel's proof could silently become the proof of different
code. D3 derives the decision from exact source/artifact comparison and re-earns
every artifact-specific claim for a new candidate.

**Decision.** `NEW_CANDIDATE_REQUIRED`. The frozen `0.0.2a2` wheel
(`d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d`, 59 members)
mechanically lacks `saimail/inbox_query.py`, `saimail/workspace.py.reply_message`,
the `saimail/gui_*` modules, the `saimail-gui` console entrypoint and the `gui`
optional extra. The frozen wheel is classified `HISTORICAL_VERIFIED_ALPHA` and
its local, custody, reproducibility and external proofs bind exactly its own
wheel bytes; none is inherited by the new candidate. Evidence:
`release/evidence/d3/release_decision.json` (`SAIMAIL_D3_RELEASE_DECISION_1` v1),
`tools/d3_release_evidence.py decide`.

**Version and identity.** The current source and candidate version is
`0.0.2a3` (PEP 440 prerelease). The frozen `0.0.2a1`
(`ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a`) and
`0.0.2a2` bundles stay byte-identical and `NOT_PUBLISHED`; the new candidate
lives at `release/candidates/0.0.2a3/`. Artifact identity remains the exact wheel
SHA-256 (D-052), never the version string.

**Scope.** The candidate carries the accepted post-a2 product delta unchanged:
P1 (bounded metadata-only inbox query/triage), V4-01 (explicit one-hop local
correspondence continuation) and V5-01 (the optional desktop local messenger
GUI). It preserves all a2 functionality and security boundaries. The `gui` extra
belongs to candidate verification: PySide6 stays an optional extra, the base
install never requires Qt, and `saimail-local` keeps working without Qt.

**Custody default.** `KEEP_RAW_DEFAULT` from D-054/D-055 is unchanged: `raw` is
the documented default, `--custody os-store` remains the explicit opt-in
requiring the `credentials` extra and a checked backend, and a requested
protected custody never silently falls back.

**Release tooling truth.** `tools/local_alpha_release.py` gains an additive
`--require-product-delta` content proof
(`LOCAL_ALPHA_WHEEL_PRODUCT_DELTA_PROOF_1`) that mechanically proves the
P1/V4-01/V5-01 surface inside the built wheel; the default build keeps the exact
a2 custody-only proof. A new additive driver `tools/d3_release_evidence.py`
provides the D3 decision packet, the frozen a1/a2 immutability proof, the a3
claim matrix and the a3 gate evaluation, delegating the generic
integrity/privacy/reproducibility red controls to the a2 driver with D3 schema
identities. `tools/local_alpha_release.py` still refuses to touch the historical
a1 bundle or to overwrite any frozen candidate.

**Evidence.** A new wheel means new evidence; nothing artifact-specific is
inherited from a2 or a1. Evidence set under `release/evidence/a3/`:
`local_alpha_verification.json` (installed-wheel base verification, now also
exercising P1 and V4-01 from the installed public API),
`windows_os_store_proof.json` (fresh installed-wheel WinVault acceptance plus the
injected-store migration proof, schema `SAIMAIL_D3_WINDOWS_OS_STORE_PROOF_1`),
`gui_install_matrix.json` (the `gui` extra installs PySide6, `saimail-gui`
exists, the GUI modules resolve from the environment and the repository's own
offscreen GUI acceptance passes against the wheel),
`reproducibility.json`, `privacy_controls.json` and `integrity_controls.json`
with red controls, `claim_matrix.json`, `gate_evaluation.json` (G1–G20; G13
`PENDING_EXTERNAL` until a genuine separate environment proves the exact a3
wheel; G17 `ABSENT`). The a1/a2 immutability proof lives in
`release/evidence/d3/immutability.json`.

**Publication.** `publication = NONE` and `publication_authorization = ABSENT`
(D1/G17). D3 stops before publication. The truthful terminal state is
`READY_FOR_EXTERNAL_INSTALL_PROOF` until a genuine separate-environment proof of
the exact `0.0.2a3` wheel is supplied and admitted through the canonical
continuation path.

**Regression evidence.** `tests/test_d3_release_candidate.py` (a3 version
surfaces, new-candidate path, extended content proof, a1+a2 immutability pins,
build guards, a3 evidence binding, gate matrix), `tests/test_a2_release_candidate.py`
(a2 history preserved; the stale "current surfaces are a2" assertion moved to
the a2-history/compatibility form), `tests/test_a2_external_proof.py`,
`tests/test_local_alpha_release.py`, `tests/test_clean_install.py`,
`tests/test_repo_consistency.py`.

---
