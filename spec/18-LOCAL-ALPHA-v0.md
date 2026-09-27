# V2-04 — SCOPED LOCAL ALPHA RELEASE READINESS v0

Status: working. Contract for `tools/local_alpha_release.py`,
`tools/verify_local_alpha.py`, `tools/scan_local_alpha_privacy.py`,
`tests/test_local_alpha_release.py` and the release bundle under
`release/local-alpha/`. Decision: [D-052](DECISIONS-D052.md).

## 1. What this gate is

V2-04 converts the proven V2-01 local workflow into one exact, inspectable,
hashed local-alpha candidate that another environment can install and verify.
It is release readiness, not publication. It adds no protocol rule, no network
path, no model call and no change to any earlier result contract.

## 2. Alpha scope

The candidate claims:

* local filesystem messaging only — a shared local path, never a network
  service;
* persistent V2-01 workspaces (init, identity, recipient add/list, send,
  inbox, open, acceptance);
* explicit public identity-card exchange and deterministic recipient
  registration;
* the current SENV2 envelope and Post Office semantics, including canonical
  duplicate suppression and explicit open;
* the documented `saimail-local` command workflow.

The demonstrated platform is CPython 3.11 on win32 (the host that produced the
clean-install and verification evidence). No broader portability is claimed.

The candidate does not claim: a hosted service; LAN or internet transport;
Gmail/Slack/Outlook or any adapter; a daemon or background synchronization;
production service readiness; a protected *default* (raw stays the default); a
protected mode that covers same-user malware, admin/kernel compromise,
hardware attack, physical presence or human-identity proof; hardware-key
custody; key rotation; automatic recovery; automatic correspondence; semantic
reviewer reliability; universal utility; zero protocol overhead; or
production-grade remote identity discovery. `os-store` custody is a bounded
explicit opt-in with its own claim boundary (section 2.1 of spec/20).

Carried with mode separation: in the default `raw` mode identity private keys
are raw software key files protected only by their file location; the explicit
`os-store` mode keeps only handles plus public material in the workspace and
the private keys in the checked OS credential store. The measured verdict
`UTILITY_CONDITIONAL` is unchanged: SAIMAIL does not universally save tokens or
cost.

## 3. Version identity

The current candidate version is `0.0.2a2` (PEP 440 prerelease; no fake final
version). Authoritative surfaces: `pyproject.toml`, `VERSION`,
`saimail_local._VERSION_FALLBACK`, `lab/stable_local_api.json.release`, the
candidate manifest and the built wheel metadata. One consistency test enforces
agreement; no second version authority exists. The earlier `0.0.2a1` candidate
is a separate frozen historical artifact (`release/local-alpha/`) with its own
SHA-256 and its own external proof; a version string is never artifact
identity, which is always the wheel SHA-256 (D-052).

## 4. Bundle layout

`tools/local_alpha_release.py build --out DIR` produces one candidate bundle:

```
saimail-0.0.2a2-py3-none-any.whl   the frozen candidate wheel
local_alpha_candidate.json         LOCAL_ALPHA_CANDIDATE_1 v1 manifest
SHA256SUMS.txt                     hashes of every shipped file except itself
README-LOCAL-ALPHA.md              install and verify instructions, scope,
                                   limitations, security and publication status
verify_local_alpha.py              the bounded verifier (standalone, stdlib)
```

Candidates live in identity-bearing directories; the current one is
`release/candidates/0.0.2a2/`. `release/local-alpha/` holds the historical
`0.0.2a1` bundle and is closed to new builds (the tooling refuses), and a
directory that already holds a candidate manifest is never overwritten.
saimail-0.0.2a1-py3-none-any.whl   the frozen candidate wheel
local_alpha_candidate.json         LOCAL_ALPHA_CANDIDATE_1 v1 manifest
SHA256SUMS.txt                     hashes of every shipped file except itself
README-LOCAL-ALPHA.md              install and verify instructions, scope,
                                   limitations, security and publication status
verify_local_alpha.py              the bounded verifier (standalone, stdlib)
```

The bundle contains no private keys, plaintext messages, credentials, tokens,
local secret paths, environment dumps, test logs, `.saipen` state, lab history,
temporary workspaces or caches. The frozen candidate is exactly the wheel
identified by the recorded SHA-256; a modified wheel is a new candidate with a
new manifest and hash. Verification evidence produced by this repository is
kept outside the bundle, under `release/evidence/`, so the bundle's checksum
surface stays exactly the shipped files.

## 5. Manifest — `LOCAL_ALPHA_CANDIDATE_1` v1

Bounded, non-secret fields: schema and version; package name and version;
alpha scope; Python compatibility scope; platform proof scope; creation
timestamp (UTC); wheel filename, size, SHA-256 and a per-member content digest;
source identity (Git HEAD, dirty flag, note that no commit uniquely identifies
the candidate); expected result schemas (`LOCAL_SCENARIO_RESULT_1` v1,
`FG06_UTILITY_RESULT_1` v1, `LOCAL_WORKSPACE_COMMAND_1` v1,
`LOCAL_WORKSPACE_RESULT_1` v1); verification procedure identity; limitations
reference; security limitations; zero-runtime-network and zero-model-call
expectations; `publication_status = NOT_PUBLISHED`.

Post-V3-01 (D2) additions, all additive to v1:

* `custody` — the mode-separated truth: `default = raw`, the optional
  `os-store` opt-in and its requirement (the credentials extra plus a checked
  backend), what protected mode stores where, what it protects against
  (workspace-directory-copy exposure) and the explicit not-protected list
  (same-user malware, admin/kernel compromise, hardware attack, physical
  presence, human-identity proof), the not-provided list (hardware custody,
  rotation, automatic recovery), the Windows-specific backend evidence
  boundary and the no-silent-fallback rule;
* `content_proof` — the mechanical wheel inspection (identity
  `LOCAL_ALPHA_WHEEL_CONTENT_PROOF_1`): the wheel must contain
  `saimail/custody.py`, the identity
  schema v2 marker, the `--custody` / `custody status` / `custody migrate` CLI
  surface and the first-run notice marker, all read from the wheel's own
  members; a failing proof refuses the build;
* `historical_candidate_a1` — the frozen pre-V3-01 candidate identity (wheel
  SHA-256) with the explicit note that its external proof is never inherited.

## 6. Reproducibility and integrity

Two clean builds from the same frozen source state are compared on package
metadata, file list, member content hashes, installed behavior, result-schema
identities and version identity. Byte-identical wheels are attempted; when the
packaging tool embeds nondeterministic metadata, the cause is identified, the
selected wheel is frozen by SHA-256, and the remaining binary nondeterminism is
documented — never faked as equality.

Integrity gate: `verify_bundle_integrity` recomputes SHA-256 of the actual
wheel and every `SHA256SUMS.txt` entry. Red control required: a corrupted
wheel and a corrupted recorded hash are both rejected.

## 7. External verifier — `LOCAL_ALPHA_VERIFICATION_1` v1

`verify_local_alpha.py` runs on a machine that does not have the checkout. It
operates on the bundle only and produces one bounded machine-readable result:

* status `PASS` / `FAIL` / `BLOCKED`;
* candidate version and wheel hash;
* Python version and platform;
* install result and module-resolution proof (installed environment, not a
  checkout);
* `saimail-local --version` result;
* stable API map identity and release marker;
* FG-05, FG-06 and V2-01 acceptance results (schema and status);
* runtime network-attempt counter and model/provider call counter (0 on the
  base path);
* privacy checks;
* limitation acknowledgement/version;
* verification timestamp and verifier version;
* D2 additions: the candidate wheel content proof status; the base custody
  block (`default = raw`, the `os-store` selection/requirement and the
  platform-evidence boundary); the direct-init custody mode and first-run
  notice presence; the FG-06 verdict comparison against the declared
  candidate verdict; and an explicit `scope` block that separates
  `base_candidate_verification` (tested here) from
  `os_store_platform_verification` (platform-specific, not tested by this
  verifier and never implied by a PASS).

Dependency installation (for example `cryptography`) is reported separately as
installation activity, never as SAIMAIL runtime network activity. With
`--offline` the verifier never contacts a package index and requires the host
interpreter to provide the declared crypto dependency. The verifier stores no
private key material and no opened plaintext, and uses temporary workspaces
unless evidence retention is requested.

## 8. Current-host clean-install proof

Before any external attempt, the frozen candidate is installed into a fresh
virtual environment created by the verifier itself, from a working directory
outside the checkout. Module resolution is proven inside that environment. The
bounded verifier result is stored as evidence under `release/evidence/` and
never rewrites the frozen wheel, manifest or checksums.

## 9. Privacy gate

`scan_local_alpha_privacy.py` scans the candidate bundle and its reports for
bounded known material: Ed25519/X25519 private key fields, PEM private key
headers, API-token shapes, assigned credential values (a documented handle
name alone is not a secret), planted privacy markers and unintended absolute
user secret paths. Red control required: a planted marker in a disposable copy
must fail the scan; the real candidate must pass. The scanner is a bounded
structural check, not a proof that no secret exists.

## 10. Publication status

`publication_status = NOT_PUBLISHED`. Building, hashing, packing and locally
verifying the candidate does not publish anything. No push, tag, PyPI upload,
GitHub release or announcement is part of this gate; publication remains a
separate explicit operator action. The current `0.0.2a2` candidate is
`NOT_PUBLISHED` and its external (separate-environment) proof is the one
outstanding engineering gate; the historical `0.0.2a1` candidate stays
`NOT_PUBLISHED` as well.

## 11. What this does not claim

The candidate is a scoped local alpha, not a production communication service.
It does not promise remote delivery, a server, a daemon, account
synchronization, automatic recipient discovery, hardened key storage,
automatic correspondence or a general-purpose secure-messenger claim. It does
not turn a shared filesystem path into network messaging, and it does not
claim utility beyond the measured `UTILITY_CONDITIONAL` result.
