# T-14 — real interest filter over R1

Corpus: 51 messages across 16 selection-stress classes. Declared interest: atoms ['CONCURRENCY', 'DEADLOCK', 'DUPLICATE_EXECUTION', 'QUEUE_OWNERSHIP_STALE', 'RECOVERY', 'RETRY'], subjects ['queue', 'recovery'].

Ground truth is what a reader who already knew everything would have done,
declared per fixture and not derived from the rules.

## Rules, declared before the run

- `R0-WATCHED` — a relation points at a record this reader watches, whatever the vocabulary
- `R1-UNRESOLVED-RELATION` — a relation names a target the container never declared
- `R2-UNKNOWN` — a wire token this profile has no atom for: unreadable, so never dropped
- `R3-OPEN-RECORD` — the frame could not carry the claim at all
- `R4-NOISE` — every atom is on the declared noise list for this reader
- `R5-NOT-NOW` — known, readable, not relevant right now: kept rather than discarded
- `R6-CONTRADICTION` — relevant, and it refutes or conflicts with something
- `R7-ACTIONABLE` — relevant, evidence attached, and at or above the supported rung
- `R8-RELEVANT` — relevant but not yet actionable

## What the filter actually did

| measure | value |
|---|---|
| R1 scanned | 51 |
| opened to R2 | 21 |
| opened to R3 | 14 |
| ignored | 2 |
| **actual open rate** | **0.686** |
| agreement with declared truth | 0.882 |
| unknown-atom fallbacks | 7 |
| open-record fallbacks | 8 |
| selector latency | 1244 ns per message |
| R1 bytes per message | 39.0 |

Truth distribution for reference: IGNORE 4, DEFER 16, OPEN_R2 17, OPEN_R3 14.

## Errors, kept apart on purpose

> FALSE_IGNORE >> FALSE_OPEN >> EXTRA_BYTES
>
> Reported separately and never summed. A single score would need a calibrated exchange rate between a missed discovery and a wasted summary, and no such calibration exists.

- **false ignore: 0** — the expensive failure
- false open: 2
  - `irr-4` (operational_noise): rule R5-NOT-NOW — atoms ['CHECKPOINT', 'PERFORMANCE'] are readable and not relevant now
  - `irr-5` (operational_noise): rule R5-NOT-NOW — atoms ['DATABASE', 'METADATA', 'TIMESTAMP'] are readable and not relevant now
- under-open (opened, but not deep enough): 0

## Context actually emitted

| tokenizer | emitted at R2/R3 | eager full prose | ratio |
|---|---|---|---|
| cl100k_base | 1911 | 4246 | **0.450** |
| o200k_base | 1940 | 4267 | **0.455** |
| p50k_base | 2135 | 4552 | **0.469** |
| gpt2 | 2135 | 4552 | **0.469** |

## Rule usage

- `R0-WATCHED`: 3
- `R2-UNKNOWN`: 7
- `R3-OPEN-RECORD`: 8
- `R4-NOISE`: 2
- `R5-NOT-NOW`: 14
- `R6-CONTRADICTION`: 3
- `R7-ACTIONABLE`: 8
- `R8-RELEVANT`: 6

## Boundary refusals

These never reach the selector at all.

- stale_profile: `PROFILE_MISMATCH`
- malformed_frame_container: `BAD_BATCH`
- malformed_frame_decode: `BAD_FRAME`
- forged_frame_binding: `UNVERIFIED_BINDING`
- explicitly_bound_frame: `F`

