# SAIMAIL local alpha candidate 0.0.2a2

Scoped **local** alpha candidate with the V3-01 identity custody modes. Built
and hashed, **NOT PUBLISHED**.

## Install

```
python -m venv venv
venv\Scripts\activate            (POSIX: source venv/bin/activate)
pip install "saimail-0.0.2a2-py3-none-any.whl[crypto]"
saimail-local --version           # must print saimail 0.0.2a2
```

`cryptography` is the one runtime extra the local workflow needs. Protected
`os-store` custody additionally needs the `credentials` extra
(`pip install "saimail-0.0.2a2-py3-none-any.whl[crypto,credentials]"`). If the machine has no
package index access, either install the extras first from local wheels or a
`--system-site-packages` environment, or run the verifier with `--offline`
when the host interpreter already provides them; dependency installation is
separate from SAIMAIL runtime network activity, which is zero.

## Verify

```
python verify_local_alpha.py --bundle . --out verification [--offline]
```

Writes `verification/local_alpha_verification.json` with schema
`LOCAL_ALPHA_VERIFICATION_1` v1 and status `PASS` / `FAIL` / `BLOCKED`.
Integrity is checked against this bundle's `SHA256SUMS.txt` and the manifest's
wheel SHA-256 before anything is installed:

```
sha256 wheel: d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d
```

The bundled verifier proves the **base** candidate on any supported host. It
does not test `os-store` custody: that backend is platform-specific and its
evidence is Windows-only in this candidate (see the limitations below).

## What works

* install the package and run `saimail-local --version`, `--api-map`,
  `--demo`, `--utility`;
* initialize persistent workspaces and exchange public identity cards;
* register a known local peer explicitly;
* local send -> inbox list (metadata only) -> explicit open;
* duplicate suppression of an exact replay, restart persistence;
* raw (default) identity custody and the explicit `init --custody os-store`
  protected mode where a checked OS credential backend exists
  (`custody status`, `custody migrate`); the first-run result of a new
  workspace carries the bounded custody notice;
* FG-05 demo (`LOCAL_SCENARIO_RESULT_1`) and FG-06 benchmark
  (`FG06_UTILITY_RESULT_1`) with machine-readable results;
* V2-01 acceptance harness (`LOCAL_WORKSPACE_RESULT_1`).

## What does not exist

Remote delivery, email-provider integration, a server or daemon, account
synchronization, automatic recipient discovery, a protected default, hardware
custody, key rotation, automatic recovery, automatic correspondence, and any
general-purpose secure-messenger claim.

## Limitations and security

**Raw custody (default).** New workspaces store their private Ed25519/X25519
identity keys as raw software key files in `identity/identity.json`, protected
only by their file location (owner-only mode requested where the OS honours
it). A copied workspace directory copies the identity. No encryption at rest,
no rotation.

**os-store custody (explicit opt-in).** `init --custody os-store` (or
`custody migrate`) keeps only handles and public material in the workspace and
stores the private keys in the OS credential store under
`credential://saimail-workspace/...`, where a checked persistent backend
exists. It protects against workspace-directory-copy exposure **only**. It
does not protect against malware running as the same OS user, admin/kernel
compromise, hardware attack, physical presence or human-identity proof, and
it provides no hardware custody, key rotation or automatic recovery. A
requested protected custody never silently falls back to raw; a missing or
unsuitable store fails closed with a named `CUSTODY_*` code. Backend evidence
for this candidate is Windows-specific (`WinVaultKeyring`).

**Other limits.** Delivery is an explicit path to the recipient workspace; the
sender needs write access to it, and a shared local path is not network
messaging. Both sides must exchange public identity cards and register each
other; there is no automatic discovery. Utility is `UTILITY_CONDITIONAL`: a
measured cost win at low open rate, neutral at moderate/high and
fallback-heavy workloads. The demonstrated platform is CPython 3.11 on win32;
broader portability is not claimed.

## Publication status

`publication_status = NOT_PUBLISHED`. This bundle was built, hashed and
locally verified. Nothing here has been pushed, tagged, uploaded or announced;
publication is a separate explicit operator action. See
`spec/18-LOCAL-ALPHA-v0.md`, `spec/20-LOCAL-KEY-CUSTODY-v0.md` and
D-052 / D-053 / D-054 in the source repository for the full contract. The
pre-V3-01 `0.0.2a1` candidate remains a separate historical artifact
(`release/local-alpha/`) and its external proof is never inherited here.
