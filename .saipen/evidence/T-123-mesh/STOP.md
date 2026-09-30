# T-123 STOP checkpoint (operator `saipen stop`), phase BUILD

Source SRC-109 ("давай до конца ... реальным хранилищем-посредником для SAIPEN и
всего живого"). T-123 = mesh torture (SRC-108 item 8).

Done in BUILD:
- `tests/test_mesh.py` (5): full meshes of 2/4/8/12 agents, two racing processes
  per agent, every fact retried; all 4 agents killed inside the outbox lock after
  a delivery, then restarted; asserts exactly one message per fact per sender,
  intact indexes, no FAILED, no DELIVERY_IO_ERROR.
- Defect found by the mesh: concurrent first deliveries into a fresh mailbox hit
  `PermissionError` in `postoffice._OsFileLock.__enter__` (the initializing
  `os.write` into byte 0 that another process already locked; Windows refuses it),
  surfacing as DELIVERY_IO_ERROR. Deterministic repro in-process.
- Fix: `saimail/postoffice.py` `_OsFileLock.__enter__` tolerates that
  PermissionError and waits for the lock (before copy: `postoffice.before.py`,
  LF endings preserved).
- `tests/test_mailbox_lock_init.py`: red on pre-fix bytes (1 failed), green after.
- Mesh on pre-fix bytes: 2 of 5 series red; after fix: 8 of 8 series green.

Not yet done (resume here):
1. spec/03 lifecycle-lock paragraph: one sentence on the contended-init wait;
   decision D-065; Roadmap v6 §16 row for T-123; CURRENT-STATE; CHANGELOG;
   oracle line.
2. Checkpoint build -> transition VERIFY; quiescent full suite (clean env and
   with SAIPEN_AGENT); REGRESSION-EVIDENCE pair for the lock fix; REVIEW; SHIP
   skip-publish; finish.

Also written this session outside this repo (SAIPEN-owned, for its protocolist):
`_SAIPEN/future_gate/FUTURE GATE — SAITELEMES RELIABLE DELIVERY SAIPEN HALF_20260924.md`
(the SAIPEN halves V6-04/V6-07/V6-08 with the operator's SRC-108 authorization).
SAIPEN project was held by seat astra throughout; no SAIPEN Work was created.
