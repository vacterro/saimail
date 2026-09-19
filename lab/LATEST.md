# SAIFREN live runs — index

**Latest: [run 5 — 2026-09-17T15:20:12Z](analysis/20260917T152012Z.md).** Latest stability run: [S1 — 2026-09-17T16:16:36Z](analysis/stability_20260917T161636Z.md).

This file is the index. It points at the newest interpretation and lists every
run that came before it. It does not summarise them: a summary of an experiment
is a place for a number to lose its denominator.

Three rules hold for everything below (D-022):

- **A run's artifact is immutable.** `lab/out/saifren_live_<stamp>.json` and its
  report `lab/out/SAIFREN_REPORT_<stamp>.md` are written once and never edited.
  `lab/out/SAIFREN_REPORT.md` is a copy of the newest one, kept for convenience.
- **A run's interpretation is immutable.** `lab/analysis/<stamp>.md` is the
  reading of that run. A later run may contradict it; it does not rewrite it.
- **A negative finding stays visible.** Nothing here is tidied because a later
  run looked better.

| # | started | artifact | protocol | live calls | routes observed | experiment class (derived, D-024) | verdicts | reading |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-09-17T10:51:04Z | `saifren_live_20260917T105104Z.json` | v3 / SAIB3 | 22 | 1 | `SAIFREN_SINGLE_ROUTE` | PASS 9, FAIL 2, MEASURED 3 | [analysis](analysis/20260917T105104Z.md) |
| 2 | 2026-09-17T11:46:16Z | `saifren_live_20260917T114616Z.json` | v3 / SAIB3 | 22 | 2 | `SAIFREN_NOT_OBSERVED` | PASS 8, FAIL 2, MEASURED 3, ERROR 1 | [analysis](analysis/20260917T114616Z.md) |
| 3 | 2026-09-17T12:23:46Z | `saifren_live_20260917T122346Z.json` | v4 / SAIB4 | 22 | 2 | `SAIFREN_NOT_OBSERVED` | PASS 8, FAIL 1, MEASURED 3, ERROR 2 | [analysis](analysis/20260917T122346Z.md) |
| 4 | 2026-09-17T15:16:23Z | `saifren_live_20260917T151623Z.json` | v4 / SAIB4 | 12 (6 discovery, 6 experiment) | 2 | `SAIFREN_EXTERNAL_COMPARATOR` | PASS 1, FAIL 1, MEASURED 1 | [analysis](analysis/20260917T151623Z.md) |
| 5 | 2026-09-17T15:20:12Z | `saifren_live_20260917T152012Z.json` | v4 / SAIB4 | 12 (6 discovery, 6 experiment) | 2 | `SAIFREN_EXTERNAL_COMPARATOR` | PASS 1, FAIL 1, MEASURED 1 | [analysis](analysis/20260917T152012Z.md) |

Runs 4 and 5 are a **narrow validation sample**, not a replacement for runs 1–3:
three units declared in source before they ran. Their numbers are not comparable
with a 22-unit plan and are not meant to be. Run 5 repeats run 4 against the
shipped code after review fixed three defects in the harness; run 4 measures the
revision before those fixes and stays on the record as such. The harness cap
moved from 24 to 30 between them, so a discovering run reserves its 8 probes
inside its own declared bound.

## Stability runs (D-025)

A registered repeat sample, not a replacement for any run above: four cases,
three identical calls per participant per case, analysis rules fixed in
`lab/stability_registration.json` before the first call. Its artifact and report
follow the same immutability rules as the runs above.

| # | started | artifact | registration | live calls | experiment class (derived, D-024) | findings | reading |
|---|---|---|---|---|---|---|---|
| S1 | 2026-09-17T16:16:36Z | `stability_live_20260917T161636Z.json` | `sha256:c60bc6ac…` | 30 (6 discovery, 24 experiment) | `SAIFREN_EXTERNAL_COMPARATOR` | MODEL_VARIANCE 4, CROSS_MODEL_DISAGREEMENT 0, PROTOCOL_HOTSPOT 0 | [analysis](analysis/stability_20260917T161636Z.md) |

What it changed about the findings below: the three typed-semantics cases were
stable across every repeat of both models; all four variance findings are in
`S3.mailbox`; and `MiniMax-M3` answered M3 `IGNORE` three times out of three —
one participant failing one item every time, which is neither a hotspot nor a
cross-model disagreement under the registered rules.

## What each run is entitled to call itself

The class column is derived from each stored artifact by
`lab/experiment_class.py` and checked against this table by
`tests/test_experiment_class.py`. The artifacts and their readings are not
edited (D-022); the class is added beside them, not written into them.

- **Run 1 is `SAIFREN_SINGLE_ROUTE`.** Every call went through the alias and all
  22 resolved to one model. One observed member, no cross-member claim.
- **Runs 2 and 3 are `SAIFREN_NOT_OBSERVED`.** Both participants were pinned
  catalog ids; no call went through the alias, so neither answering model has
  SAIFREN membership evidence *from that run*. They measured two models, not
  SAIFREN.
- **Runs 4 and 5 are `SAIFREN_EXTERNAL_COMPARATOR`.** Role A reached
  `deepseek/deepseek-v4-flash` through the alias: an observed member. Role B,
  `MiniMaxAI/MiniMax-M3`, was selected from the live catalog and is an
  **external comparator**. It is not a SAIFREN member, and nothing in either run
  shows it is. Where their readings say "two distinct observed participants",
  read: two distinct reported models, exactly one of them an observed SAIFREN
  member.

No run so far is `SAIFREN_INTERNAL`: the roster is not observable, and no alias
sample has resolved to more than one member.

Runs 2 and 3 shipped without an analysis file; theirs were written on
2026-09-17 from the stored artifacts, after the fact, and say so at the top.

## Findings that no later run has overturned

- **Hidden context.** Reported `prompt_tokens` exceed what the harness sent by
  roughly 2.8k tokens on every measured call, on every route. Every answer in
  every run was produced under instructions nobody here can read. This is a
  standing limit on every semantic conclusion drawn from this lab.
- **Hidden reasoning.** `completion_tokens` run far above the visible answers.
  None of it is stored, by design — and none of it is available to explain a
  result either.
- **Small samples, and unstable answers.** Most units are n=1. Runs 4 and 5 ran
  the identical `S3.mailbox` prompt on the identical model four minutes apart
  and got different answers on two of four items. A single run of this unit
  supports no conclusion about any model, including the runs here that report
  one. Stability run S1 repeated it three times per model: the
  instability is real on M1, M2 and M4, while the failing item M3 did not vary.
- **Routes were pinned, not discovered, in runs 2 and 3.** Those runs sent two
  model identifiers typed into the harness. They measured cross-model behaviour
  and claimed nothing about SAIFREN membership, because they could not. Run 4
  resolves participants from the discovery surface instead (D-020).
- **The roster is still not observable.** `GET /v1/models` lists the combo but
  carries no member list, and the administrative surface refuses the SAIRoute
  credential. Membership is *sampled* through the alias, and a sample is not a
  roster. Run 4 observed exactly one member and says so.
- **Most of this catalog does not answer.** Three of four ranked candidates in
  run 4 refused at the transport (upstream 429, 403 and 500). A declared
  replacement policy is load-bearing, not ceremony.
