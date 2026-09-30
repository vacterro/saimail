# SAIMAIL local alpha candidate 0.0.2a1

Scoped **local** alpha candidate. Built and hashed, **NOT PUBLISHED**.

## Install

```
python -m venv venv
venv\Scripts\activate            (POSIX: source venv/bin/activate)
pip install "saimail-0.0.2a1-py3-none-any.whl[crypto]"
saimail-local --version           # must print saimail 0.0.2a1
```

`cryptography` is the one runtime extra the local workflow needs. If the
machine has no package index access, either install it first from a local wheel
or a `--system-site-packages` environment, or run the verifier with `--offline`
when the host interpreter already provides it; dependency installation is
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
sha256 wheel: ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a
```

## What works

* install the package and run `saimail-local --version`, `--api-map`,
  `--demo`, `--utility`;
* initialize persistent workspaces and exchange public identity cards;
* register a known local peer explicitly;
* local send -> inbox list (metadata only) -> explicit open;
* duplicate suppression of an exact replay, restart persistence;
* FG-05 demo (`LOCAL_SCENARIO_RESULT_1`) and FG-06 benchmark
  (`FG06_UTILITY_RESULT_1`) with machine-readable results;
* V2-01 acceptance harness (`LOCAL_WORKSPACE_RESULT_1`).

## What does not exist

Remote delivery, email-provider integration, a server or daemon, account
synchronization, automatic recipient discovery, hardened key storage,
automatic correspondence, and any general-purpose secure-messenger claim.

## Limitations and security

* Identity private keys are **not encrypted at rest**: they are raw software
  key files protected only by their file location (owner-only mode requested
  where the OS honours it). No hardware custody, no OS vault, no rotation.
* Delivery is an explicit path to the recipient workspace; the sender needs
  write access to it. A shared local path is not network messaging.
* Both sides must exchange public identity cards and register each other;
  there is no automatic discovery.
* Utility is `UTILITY_CONDITIONAL`: a measured cost win at low open rate,
  neutral at moderate/high and fallback-heavy workloads. SAIMAIL does not
  universally save tokens or cost.
* The demonstrated platform is CPython 3.11 on win32. Broader portability is
  not claimed.

## Publication status

`publication_status = NOT_PUBLISHED`. This bundle was built, hashed and
locally verified. Nothing here has been pushed, tagged, uploaded or announced;
publication is a separate explicit operator action. See
`spec/18-LOCAL-ALPHA-v0.md` and D-052 in the source repository for the full
contract.
