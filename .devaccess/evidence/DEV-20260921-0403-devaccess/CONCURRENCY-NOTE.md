# DEV ACCESS concurrency note — DEV-20260921-0403-devaccess

Filed 2026-09-21T02:20Z by the session that owns T-100's canonical seat.

## What happened

Two DEV ACCESS jobs overlapped on `tools/dev_access.py` and `.devaccess/**`:

| Job | Began | Owner evidence |
|---|---|---|
| DEV-20260921-0403-devaccess (this task) | 2026-09-21T01:13:32Z | work + baseline + result records |
| DEV-20260921-0423-devaccess-hardening | 2026-09-21T01:52:21Z | work record only, `status: active` |

The second job's `begin` should have been refused with
`DEV_ACCESS_WRITE_CONFLICT`, because this task already owned the same paths.
It was admitted by the pre-repair helper, whose conflict filter skipped records
with `status in ("active", "done")` instead of conflicting with active ones.
That defect is fixed in the current `tools/dev_access.py`; the second job
therefore stands as an illegally-admitted overlap.

## Authoritative timeline on current bytes

* 01:08:38Z — original `baseline.json` written by hand; it was **invalid JSON**
  (trailing comma) and `begin` had no baseline capture then.
* 01:13:32Z — this task began (work record).
* 01:52:21Z — the second job began; 01:52:48Z it rewrote `ACTIVE.json` to
  schema `SAIMAIL_DEV_ACCESS_2` (ttl, draining, protected product files).
* 02:10:38Z — this session rewrote `tools/dev_access.py` (contract repair:
  baseline capture, snapshot drift detection, self-expiry, delta tracking,
  `finish` canonical-drift refusal) and added `tests/test_dev_access.py`.
* 02:16:03Z — baseline re-captured with valid JSON and the fixed snapshot
  logic; original starting digests preserved.
* 02:16:31Z — this task finished `DEV_COMPLETE`.

## Attribution correction

`result.json` derives file deltas mechanically and therefore lists files the
second job authored:

* `.devaccess/ACTIVE.json` changed by the **second job** (v1 -> v2 schema
  upgrade), not by this one; base digest 133f78f1..., final b54b24c5....
* `.devaccess/work/DEV-20260921-0423-devaccess-hardening.json` was created by
  the **second job**.

The `tools/dev_access.py` change (44ff15c5... -> ce2ed15e...) and
`tests/test_dev_access.py` creation are this task's product delta.

## Action taken

`DEV_ACCESS_EXTERNAL_DRIFT`: this session stopped writing
`tools/dev_access.py` and `.devaccess/**` content other than evidence notes the
moment the overlap was detected. No further product edits were made.

## Required resolution

The second job must not silently merge its version over this revision. Its
session must either:

1. re-run `check` with the repaired helper (it will now report the conflict),
   reconcile deliberately on top of the current bytes, and record its own
   delta; or
2. retire its record if it never wrote product bytes.

Until then, `tools/dev_access.py` revision ce2ed15e is the delivered T-100
artifact, and any later bytes from the second job are drift to be diffed at
DEV ACCESS reconciliation.