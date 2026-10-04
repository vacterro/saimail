# Benchmarks

`TOTAL_FRICTION` is the objective (B-004), not `strlen()`:

```
TOTAL_FRICTION =
    transport_bits
  + token_cost
  + decode_latency
  + ambiguity_cost
  + recovery_cost
  + error_probability
```

The receipt is explicit that the real latency lives in serialization →
routing → context insertion → tokenizer → inference → tool execution →
verification, and that inference dominates. A format must minimise cognitive
decode cost, not characters.

## What is measured

| Harness | Question |
|---|---|
| `bench/t9b.py` | total-friction measurement over the benchmark corpus |
| `bench/r1_shootout.py` | R1 representation shootout: SAILANG frame vs compact deterministic JSON vs minimal stdlib key-value — identical R1 semantics, measured on bytes, encode/decode latency, malformed refusal, unknown-field and profile behaviour, and code surface |
| `bench/selector_run.py` | deterministic selector over typed views: selection ground truth declared per fixture, measured open rate with asymmetric false-ignore cost |
| `bench/coverage_curve.py` | semantic coverage curve: relation targets resolved to canonical identities, coverage vs fallback-open |
| `lab/` | bounded live experiments (own page: [Lab](Lab.md)) |

## The negative findings

The last benchmark verdict, the negative findings, and the recommended next
simplification live in
[bench/ANALYSIS.md](https://github.com/vacterro/saimail/blob/main/bench/ANALYSIS.md).
Read it before building anything downstream. The recorded ones:

- **B-008** — claim grammar gap: chains ending in a comparison (`A>B=C`) are
  idiomatic and unsupported by v0 grammar; the projector falls back to
  `OPEN RECORD`. A candidate v1 extension, deliberately not applied inside
  the run that measured it.
- **B-009** — non-ASCII claim vocabulary: the compact claim grammar is
  ASCII-only, so every non-English claim degrades to `OPEN RECORD`.
- **B-010** — vocabulary chosen for tokenizers, not for looks:
  `SHOUTING_SNAKE_CASE` measurably costs tokens against ordinary words.

Measurement supports a claim and never asks for work. Nothing here is an
instruction to build.
