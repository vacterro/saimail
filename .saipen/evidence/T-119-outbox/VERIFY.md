# T-119 VERIFY

- Canonical `python -m pytest -q` (quiescent): 2593 passed / 0 failed / 0 errors /
  0 skipped (`full-canonical.xml`, 130 s). Previous baseline 2567 + 24 outbox
  controls + 1 V6-05 oracle + 1 oracle-file delta accounted.
- Instrument controls: unmutated isolated copy 24 passed; four source mutants each
  turn their controls red; pre-T-119 retry path demonstrably duplicates
  (`red-controls.txt`). The race control was strengthened after it initially
  passed a no-lock mutant.
- Demonstrated against the operator's description (SRC-108 item 3): "durable
  intent first, then seal/delivery, then receipt; deterministic idempotency key;
  after crash the system repeats delivery but receiver dedup makes the repeat a
  no-op; at-least-once transport + exactly-once observable effect": the four
  process-kill controls end with exactly one message and `DUPLICATE` after a
  post-delivery crash.
- Protected set 222/0. conf: high
