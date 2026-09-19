# T-9B — total-friction benchmark (v0.1 transport surface)

**Verdict: CONDITIONAL**

Pre-registered rule, declared in `bench/t9b.py` before measurement:

> GO requires ALL of: zero semantic inversions; decode of every frame reproduces the declared triage ground truth; zero non-deterministic cases; at a 20% open rate the progressive workload costs below 0.70 of the eager full-prose baseline on every tokenizer; the local-alias break-even is at most 4 repeats on every tokenizer; and the v0.1 frame shows no p90 regression above 1.10x against triage prose. CONDITIONAL: semantics are clean and deterministic but at least one quantitative bar is missed. NO_GO: any semantic inversion, any decode mismatch, any non-determinism, or the progressive workload failing to beat eager loading at a 20% open rate.

Corpus: 45 fixtures, 15 classes. Profile `sha256:35b279aaba8c…`, dictionary v1, 30 atoms.

## Baselines, and why there are two of them

| Baseline | Carries | Used for |
|---|---|---|
| `A1_triage_prose` | exactly the frame's triage semantics | Q1 |
| `A2_full_prose` | everything the record carries, full 64-hex ids included | Q2, workload |
| `A3_human_prose` | informal hand-written text, **not** equivalent | reference only, excluded from every verdict |

Triage template: `[rung] [kind] on [subject], [evidence][, relations]: [claim | open the record]`

Full template: `On [created], [source] recorded a [rung] [kind] about [subject]: [claim]. [Type]. Evidence: [full 64-hex ids | none]. [Grades]. [Relations with full ids]. [Falsification condition].`

## Q1 — triage: frame versus triage prose

| tokenizer | v0 line | v0.1 frame | frame p90 | lowercase claim | no dictionary |
|---|---|---|---|---|---|
| cl100k_base | 1.462 | **1.160** | 1.333 | 1.091 | 1.200 |
| o200k_base | 1.471 | **1.160** | 1.286 | 1.136 | 1.263 |
| p50k_base | 1.615 | **1.273** | 1.545 | 1.222 | 1.438 |
| gpt2 | 1.615 | **1.273** | 1.545 | 1.222 | 1.438 |

- `cl100k_base`: dropping the per-frame marker saved 218 tokens over 45 frames; the batch header costs 49 tokens once.
- `o200k_base`: dropping the per-frame marker saved 223 tokens over 45 frames; the batch header costs 49 tokens once.
- `p50k_base`: dropping the per-frame marker saved 230 tokens over 45 frames; the batch header costs 50 tokens once.
- `gpt2`: dropping the per-frame marker saved 230 tokens over 45 frames; the batch header costs 50 tokens once.

## Q2 — full transfer: record versus complete prose

| tokenizer | record/full-prose median | mean | p90 | best | worst | record cheaper in |
|---|---|---|---|---|---|---|
| cl100k_base | 1.667 | 1.840 | 2.529 | 1.406 | 2.742 | 0/45 |
| o200k_base | 1.689 | 1.868 | 2.636 | 1.425 | 2.867 | 0/45 |
| p50k_base | 1.708 | 1.903 | 2.788 | 1.420 | 3.097 | 0/45 |
| gpt2 | 1.708 | 1.903 | 2.788 | 1.420 | 3.097 | 0/45 |

## Q3 — progressive decoding workload

100 messages; of those opened to a summary, a declared 40% escalate to the canonical record. Declared before the run and not tuned.

> Of the messages opened to a summary, a declared 40% escalate to the canonical record. R4 (attached evidence) is excluded: no real evidence artifacts exist yet, and inventing a size would be fabricated evidence. Including it would only widen the gap, since fewer than half the opened messages ever reach it.

| tokenizer | open rate | progressive | eager full prose | ratio | vs eager records |
|---|---|---|---|---|---|
| cl100k_base | 5pct | 2212 | 8387 | **0.264** | 0.155 |
| cl100k_base | 20pct | 3243 | 8387 | **0.387** | 0.227 |
| cl100k_base | 50pct | 5225 | 8387 | **0.623** | 0.366 |
| o200k_base | 5pct | 2204 | 8360 | **0.264** | 0.153 |
| o200k_base | 20pct | 3251 | 8360 | **0.389** | 0.226 |
| o200k_base | 50pct | 5252 | 8360 | **0.628** | 0.366 |
| p50k_base | 5pct | 2545 | 9119 | **0.279** | 0.161 |
| p50k_base | 20pct | 3740 | 9119 | **0.410** | 0.236 |
| p50k_base | 50pct | 6031 | 9119 | **0.661** | 0.381 |
| gpt2 | 5pct | 2545 | 9119 | **0.279** | 0.161 |
| gpt2 | 20pct | 3740 | 9119 | **0.410** | 0.236 |
| gpt2 | 50pct | 6031 | 9119 | **0.661** | 0.381 |

## Q4 — local alias break-even

| tokenizer | CID | alias | declaration | break-even repeats | corpus saving |
|---|---|---|---|---|---|
| cl100k_base | 39 | 2 | 43 | 1.16 | 42 |
| o200k_base | 39 | 2 | 43 | 1.16 | 42 |
| p50k_base | 38 | 2 | 42 | 1.17 | 36 |
| gpt2 | 38 | 2 | 42 | 1.17 | 36 |

Corpus reference distribution: 36 references over 30 distinct identities, of which 10 appear more than once.

## Semantics

- Semantic inversions: 0.
- Batch/standalone decode mismatches: 0.
- Non-deterministic cases: none.
- Frames that carry no claim (OPEN RECORD): 10 of 45.

## Tokenizer caveat

Every count is evidence for the tokenizer that produced it. None of these are
Claude, Sol, GLM, Qwen or DeepSeek tokenizers. A vocabulary tuned to one family
and called universal is exactly the error this section exists to prevent.

