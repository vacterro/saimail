# D3 / a3 external verification request (bounded, one action)

D3 local repair work T-107 DONE at E-1502 after T-108, T-109 and T-110. SRC-102 confirms
`humbox/SAIGIMN.mp3` is user-owned and must remain; the repository consistency
rule recognizes only this exact asset through `humbox/media-assets.json`.
Local verification passed 2514 tests plus a 111-test independent review;
candidate-bound local evidence is in this directory. Candidate `0.0.2a3` remains frozen at the identity below and
is `NOT_PUBLISHED`. G13 is `PENDING_EXTERNAL`, G17 is `ABSENT`, and publication
is `NONE`.

Local closure is recorded. The roadmap-required proof may now be collected
from a genuinely separate environment
(another machine or isolated VM/host that is NOT the current checkout
environment).

## Exact candidate to verify

- **candidate:** `0.0.2a3`
- **bundle:** `release/candidates/0.0.2a3/`
- **wheel:** `saimail-0.0.2a3-py3-none-any.whl`
- **wheel SHA256:**
  `6427feab24c310184e7fd3ec4bb33dc3f5b1581b00128e2ec08d456fa5aa10cc`

Copy the **entire** `release/candidates/0.0.2a3/` bundle — not
`release/local-alpha/` (that is the historical a1 wheel) and not
`release/candidates/0.0.2a2/` (that is the a2 wheel).

## Exact steps on the second machine

1. Copy the whole candidate directory to a genuinely separate machine / VM /
   host that is not the current checkout environment.
   A second virtualenv on the same host is NOT genuine G13 external evidence.
2. Ensure a Python 3.11+ interpreter exists there. The wheel is `py3-none-any`;
   the one runtime extra is `cryptography` (the verifier tries a clean venv
   with the host interpreter's packages, then a package index, then `--offline`).
3. Run, from inside the copied bundle directory:

   ```
   python verify_local_alpha.py --bundle . --out verification
   ```

   (add `--offline` on a machine with no package index; the host interpreter
   must then already provide `cryptography`.)

4. Return `verification/local_alpha_verification.json` byte-identical, without
   editing it.

## Expected proof

The expected proof must identify the exact a3 candidate and exact wheel SHA256:

```
"schema": "LOCAL_ALPHA_VERIFICATION_1",
"status": "PASS",
"candidate": {
  "version": "0.0.2a3",
  "wheel_filename": "saimail-0.0.2a3-py3-none-any.whl",
  "wheel_sha256": "6427feab24c310184e7fd3ec4bb33dc3f5b1581b00128e2ec08d456fa5aa10cc",
  ...
}
```

## Not valid

- A second virtualenv on the same host is not genuine G13 external evidence.
- The a1 proof (wheel `ed930e38a238c4533ddbb406e0f777e7c86ebc2068657bd8c761d337d880a40a`)
  is not valid for a3.
- The a2 proof (wheel `d1f975375dd27aa26fc2b0639987a64ea53c39aa297c628abfddb712ab64e31d`)
  is not valid for a3.

## Publication

This request is not publication. The candidate is
`publication_status = NOT_PUBLISHED`; publication authorization (G17) is ABSENT.
No publish action is authorized by completing this verification.

If the run fails, return the exact `failures` list and the environment block; a
SAIMAIL defect means a new candidate (rebuilt, re-hashed, re-verified) would be
required before this gate can close.
