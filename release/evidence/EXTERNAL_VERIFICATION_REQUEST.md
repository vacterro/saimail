# V2-04 external verification request (bounded, one action)

The V2-04 local work is complete: the candidate is frozen, hashed, privacy
scanned with red controls, integrity red controls pass, a clean install outside
the checkout passes on this host, and the same verifier is bundled. What is
still missing is the roadmap-required proof from a genuinely separate
environment (another machine or an isolated VM/host without this checkout).

## Exact steps on the second machine

1. Copy the whole `release/local-alpha/` directory to the second machine
   (USB drive, network share, `scp`; the bundle is self-contained and the
   verifier is stdlib-only).
2. Ensure a Python 3.11+ interpreter exists there. The wheel is
   `py3-none-any`; the one runtime extra is `cryptography` (the verifier tries
   a clean venv with the host interpreter's packages, then a package index,
   then `--offline`).
3. Run, from inside the copied bundle directory:

   ```
   python verify_local_alpha.py --bundle . --out verification
   ```

   (add `--offline` on a machine with no package index; the host interpreter
   must then already provide `cryptography`.)

4. Return `verification/local_alpha_verification.json`.

Expected: `"schema": "LOCAL_ALPHA_VERIFICATION_1"`, `"status": "PASS"`, and
`"candidate": {"wheel_sha256":
"ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a", ...}`.

If the run fails, return the exact `failures` list and the environment block;
a SAIMAIL defect means a new candidate (rebuilt, re-hashed, re-verified) is
required before this gate can close.

This request itself is not publication: the candidate is
`publication_status = NOT_PUBLISHED`.
