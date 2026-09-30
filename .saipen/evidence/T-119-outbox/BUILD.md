# T-119 BUILD: V6-05 durable outbox (SRC-108 wave item 3)

Defect class eliminated: a send that cannot be retried safely (a retry re-seals a
second logical message because sealing is randomized and dedup is by exact bytes).

## Product change

- New `saimail/outbox.py`: intent files `outbox/intents/<sha256(key)>.json`
  (`SAIMAIL_OUTBOX_INTENT_1`), PENDING -> SEALED -> DELIVERED | FAILED, atomic
  writes; request digest binds key to (alias, kind, topic, content); seal once and
  persist the container (intent + `.senv`) before delivery; replay exact bytes;
  plaintext dropped at SEALED; `postoffice._OsFileLock` outbox lock (dies with its
  process); transient codes back off 30 s doubling to 1 h; terminal -> FAILED,
  re-armed only by `retry_intent`; keyless SEALED delivery and status.
- `saimail_local.py`: `outbox send|resume|retry|status` (status uses the D-059
  header view). Diff: `saimail_local.diff`.
- `saimail/workspace.py`: renderer lines for intent/outbox/resume blocks only.
  Diff: `workspace.diff`.
- `lab/stable_local_api.json`: 5 APIs + `local_outbox` failure-code group.

## Tests

- `tests/test_outbox.py` (24): one key one message, no plaintext at rest; key
  reuse with another request changes nothing; bad keys write nothing; offline
  recipient backoff 30 s -> 60 s then delivered once; quarantine terminal until
  retry; rebound alias never receives the bytes; real `os._exit` kill after
  intent / after SEALED record / before delivery / after delivery each resumes to
  exactly one message; lock exclusion across processes; 6-process same-key race ->
  1 message; 8-process distinct keys -> 8; keyless status + sealed delivery with a
  locked os-store store (0 secret reads); pending waits for signing key; tampered
  intents fail closed; CLI round trip.
- `tests/test_repo_consistency.py`: V6-05 oracle (additive).

## Red controls (`red-controls.txt`, `.saipen/kitchen/t119_red_control.py`)

- Pre-T-119 path: `send_message` retried -> receiver holds 2 messages.
- Unmutated isolated copy: 24 passed.
- Source mutants: no_lock -> 2 failed (lock exclusion, same-key race);
  reseal -> 6 failed (crash matrix, one-key, quarantine, tamper);
  keep_plaintext -> 5 failed; all_terminal -> 1 failed (offline backoff).
- Weak-control finding fixed during BUILD: the first race control passed the
  no_lock mutant (conftest mutation did not reach children; start jitter kept
  critical sections apart). Replaced by source mutants, a start barrier and a
  deterministic lock-exclusion control.

## Docs

`spec/28-DURABLE-OUTBOX-v0.md`, `spec/DECISIONS-D060.md`, Roadmap v6 §16 (wave
table V6-04..V6-08 + policy row + later items), CURRENT-STATE banner and wave
section, CHANGELOG (mixed line endings preserved after a normalization slip was
caught and reverted from the before copy).

## Checks

Lint E4/E7/E9/F PASS on touched Python; adjacent suites green; protected set
(T-117 list: release trees, audio, VERSION, pyproject, postoffice/envelope/GUI
code, frozen DECISIONS.md, earlier evidence) 222/0.
