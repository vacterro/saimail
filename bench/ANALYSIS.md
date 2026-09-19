# Benchmark analysis — what the measurements actually mean

Current evidence: `bench/out/T9B_REPORT.md`, `t9b_results.csv`,
`t9b_results.json`. Reproduce with:

```
python bench/t9b.py --out bench/out
```

Corpus: 45 fixtures, 15 information classes. Tokenizers: `cl100k_base`,
`o200k_base`, `p50k_base`, `gpt2`.

**T-9B supersedes the headline ratios of T-9.** The earlier run compared a
triage frame against prose that carried the *whole record*, which is not the
same information. Those numbers are withdrawn; the superseded ones are named
below so nobody quotes them from an old chat log.

## Verdict: CONDITIONAL

Zero semantic inversions, zero decode mismatches, zero non-determinism, a large
and consistent workload win, and an alias break-even inside the bar — against a
frame that is **more expensive than equivalent prose per message**.

## Finding 1 — the compact frame is a net loss per message, and T-9 hid it

Q1, frame tokens ÷ equivalent triage-prose tokens (lower is better):

| tokenizer | v0 line | v0.1 frame | frame p90 |
|---|---|---|---|
| cl100k_base | 1.474 | **1.154** | 1.333 |
| o200k_base | 1.500 | **1.167** | 1.357 |
| p50k_base | 1.625 | **1.286** | 1.588 |
| gpt2 | 1.625 | **1.286** | 1.588 |

Every number is above 1.0. Prose that carries exactly the frame's semantics —
kind, subject, rung, evidence presence, relations, and the claim only when the
frame could carry it — is **cheaper than the frame on every tokenizer**.

T-9 reported 0.703–0.784 for the same artifact. That result is superseded: its
baseline prose also spelled out provenance and an evidence identity the frame
never carried, so the frame was winning a race against a heavier runner.

The design instinct that compact ASCII beats English is wrong here, twice
measured.

## Finding 2 — moving version metadata out of the frame worked, exactly as predicted

Dropping the per-frame `L1D<v>|` marker saved **225 tokens over 45 frames** on
every tokenizer. The batch header that replaced it costs **47–52 tokens once**,
for any batch size.

That is the whole v0 → v0.1 improvement: 1.474 → 1.154 on `cl100k_base`,
1.625 → 1.286 on `gpt2`. The prediction from the T-9 variant analysis held.

## Finding 3 — the dictionary now earns its place, which it did not before

| variant | cl100k | o200k | p50k | gpt2 |
|---|---|---|---|---|
| frame with dictionary | 1.154 | 1.167 | 1.286 | 1.286 |
| frame **without** dictionary | 1.214 | 1.263 | 1.438 | 1.438 |
| frame, claim slot lowercased | **1.091** | **1.125** | **1.250** | **1.250** |

Under T-9 the dictionary looked marginal because the per-frame marker that
announced it cost five times what it saved. With the marker gone, substitution
is a clear win. The version marker was not paying for the dictionary; it was
drowning it.

Lowercasing **only** the claim vocabulary is still the cheapest variant on every
tokenizer — `SHOUTING_SNAKE_CASE` continues to cost real money — but even that
does not get below 1.0.

## Finding 4 — the canonical record costs 1.7x equivalent prose, not 4.8x

Q2, record ÷ information-equivalent full prose:

| tokenizer | median | mean | p90 | worst | record cheaper in |
|---|---|---|---|---|---|
| cl100k_base | 1.667 | 1.840 | 2.529 | 2.742 | 0/45 |
| o200k_base | 1.689 | 1.868 | 2.636 | 2.867 | 0/45 |
| p50k_base | 1.708 | 1.903 | 2.788 | 3.097 | 0/45 |
| gpt2 | 1.708 | 1.903 | 2.788 | 3.097 | 0/45 |

T-9's 4.50–4.80 is superseded: it compared the record against prose that
abbreviated the evidence identity to `sha256:5f2b…`. Given prose that actually
carries the same 64 hex characters, the gap collapses to about 1.7x.

The conclusion from T-9 survives in a weaker form: the record is **never**
cheaper than prose, in 45 of 45 cases, so it remains a storage and audit format
rather than a context format. It is simply less catastrophic than first
measured.

## Finding 5 — the entire value is selective resolution, and it is large

Q3, 100 messages, declared before the run: everything is scanned as a frame, a
declared fraction is opened to a summary, and a declared 40% of those escalate
to the canonical record.

| open rate | vs eager full prose | vs eager records |
|---|---|---|
| 5% | 0.262 – 0.281 | 0.153 – 0.162 |
| 20% | **0.385 – 0.412** | 0.226 – 0.237 |
| 50% | 0.621 – 0.663 | 0.365 – 0.382 |

Progressive resolution costs roughly **a third** of loading equivalent prose
eagerly at a realistic open rate, and still wins at a 50% open rate.

So the frame's justification is not its size. A frame costs about 15–29% more
than the prose that says the same thing — and saves 60–75% of the mailbox,
because most messages are never opened at all. The win comes from the `R0…R4`
resolution ladder in `SRC-002`, not from the syntax.

`R4` (attached evidence) is excluded from the model: no real evidence artifacts
exist yet, and inventing a size would be fabricating evidence. Including it
widens the gap, since fewer than half of the opened messages ever reach it.

## Finding 6 — local aliases pay off after two repeats, and the corpus barely repeats

| tokenizer | CID tokens | alias tokens | declaration | break-even repeats |
|---|---|---|---|---|
| cl100k_base | 39 | 2 | 43 | 1.16 |
| o200k_base | 39 | 2 | 43 | 1.16 |
| p50k_base | 38 | 2 | 42 | 1.17 |
| gpt2 | 38 | 2 | 42 | 1.17 |

A full `sha256:` identity costs 38–39 tokens; a `@7` alias costs 2. The
declaration pays for itself on the **second** reference.

But the honest corpus number is small: total saving across all 45 fixtures is
only **36–42 tokens**, because almost every evidence identity in this corpus is
referenced exactly once. Aliases are worth real money in a conversation that
keeps citing the same artifacts, and worth nothing in a mailbox of unrelated
messages. The break-even is proven; the workload that benefits is not this one.

The canonical identity is untouched. An alias is a batch-local reference that
expands through an explicit declaration, never a replacement identity.

## Finding 7 — a withdrawn measurement

T-9's `lowercase_claim` variant lowercased the **entire** markerless line: the
kind letter, the rung, the evidence marker and the flags along with the claim.
It measured a format nobody proposed. The number is withdrawn, the variant is
fixed to mutate only the claim slot, and a test now asserts that the other five
slots survive unchanged.

## Methodology, and where to attack it

Both prose baselines are **rendered from templates**, printed in the report, so
they cannot be quietly tuned per case after seeing a result:

```
triage: [rung] [kind] on [subject], [evidence][, relations]: [claim | open the record]
full:   On [created], [source] recorded a [rung] [kind] about [subject]: [claim].
        [Type]. Evidence: [full ids | none]. [Grades]. [Relations]. [Falsification].
```

The obvious attack: a template is more uniform than a human, and uniform text
compresses predictably. A third baseline, the hand-written `A3_human_prose`, is
measured and reported but **excluded from every verdict**, because it is not
information-equivalent to anything.

A second attack worth taking seriously: `TOTAL_FRICTION` from `SRC-002` has six
terms and this benchmark measures two of them — `token_cost` and
`transport_bits`. `ambiguity_cost`, `decode_latency`, `recovery_cost` and
`error_probability` are unmeasured. That matters here, because after Finding 1
the frame's remaining justification rests entirely on one of the unmeasured
terms: a frame is decodable by a deterministic parser with closed sets, and
prose is not. A mailbox scan over frames needs no model at all; a mailbox scan
over prose needs one. That is a real argument and it is currently an unmeasured
one.

## Tokenizer caveat

Every count is evidence for the tokenizer that produced it. None of these are
Claude, Sol, GLM, Qwen or DeepSeek tokenizers. The *direction* of Finding 1 —
abbreviations tokenize worse than words — is a general property of sub-word BPE
and is likely to hold; the exact ratios are not transferable. Adding a family
means adding an adapter in `bench/tokenizer_adapters.py` and nothing else.

## What this says about the next step

Stop optimising the wire vocabulary. Two runs have now shown that route gives
back single-digit percentages while the resolution ladder gives back 60–75%.

The open question is no longer "is the frame shorter". It is: **is a
deterministically decodable frame worth 15–29% more tokens than prose, given
that scanning it costs no inference at all?** That is an `ambiguity_cost` and
`decode_latency` experiment, and it is the one worth running next.

---

# R1 data-plane results (T-14, T-15, T-16)

Evidence: `bench/out/R1_SHOOTOUT.md`, `bench/out/SELECTOR_REPORT.md`,
`r1_shootout.json`, `selector_results.json`. Reproduce with:

```
python bench/r1_shootout.py --out bench/out
python bench/selector_run.py --out bench/out
```

## Finding 8 — the assumed open rate was optimistic by a factor of four

T-9B declared open rates of 5%, 20% and 50% and proved the *arithmetic* of
selective opening. A real filter on a corpus built to stress selection opens
**76.2%** of the mailbox:

| | |
|---|---|
| scanned at R1 | 42 |
| opened to R2 | 21 |
| opened to R3 | 11 |
| ignored | 10 |
| **actual open rate** | **0.762** |
| agreement with declared truth | 0.905 |

The context saving survives — **0.451–0.474** of loading equivalent prose
eagerly — but it is roughly half of what the 20% assumption predicted (0.385).
Anyone quoting the T-9B workload number should quote this one instead.

## Finding 9 — the fallbacks, not the irrelevance, drive the open rate

Of 42 messages, **15 are opened purely because R1 could not read them**: 7 carry
a wire token this profile has no atom for, 8 carry a claim the frame could not
represent at all. That is 36% of the corpus opened without any evidence of
relevance.

This is correct behaviour and expensive behaviour at the same time. Unknown
must never become ignore — but every unknown atom is an open, so **the
vocabulary's coverage is the selector's efficiency**. The way to lower the open
rate is not a smarter filter; it is more atoms and more claims written in a
shape R1 can carry.

## Finding 10 — zero false ignores, four false opens

```
false ignore: 0     the expensive failure, avoided
false open:   4     all four are prose claims R1 cannot read
under-open:   0
```

The four false opens are exactly the `ambiguous_prose` fixtures whose content
turned out to be irrelevant. R1 had no way to know, and guessing would have
been the forbidden move. Reported separately from false ignores and never
summed: collapsing them into one score needs an exchange rate between a missed
discovery and a wasted summary, and no calibration exists.

Selector cost: **~1.5 µs per message**, no model, no inference. That is the
argument the frame has been leaning on since Finding 1, now measured.

## Finding 11 — the custom wire survives its own shootout

Three codecs carrying identical R1 semantics, all stdlib, all passing every
correctness gate (round-trip to an identical typed view, malformed refused,
unknown field refused, wrong profile refused):

| codec | body bytes | decode ns/batch | extra statements |
|---|---|---|---|
| SAILANG wire | **1538** | **217885** | **29** |
| compact JSON | 3303 | 391290 | 39 |
| typed key/value | 2123 | 368455 | 41 |

Against the best standard codec: bytes 0.724, decode latency 0.591, code
surface 0.744 — all three inside the pre-registered bars, so the verdict is
`KEEP_CUSTOM_WIRE`.

**Measurement boundary, stated because it matters:** every codec ends at the
same typed view produced by `sailang.frame.decode`, and that shared layer is
charged to none of them. "Code surface" is therefore the *extra* code each wire
needs on top of a typed-view layer they all depend on, not the total cost of
owning a format. Under a different boundary — counting the wire parser itself —
the custom wire would look worse. The numbers are not wrong; they answer a
narrower question than "is a custom format cheaper to own".

## Finding 12 — a hole found by a boundary probe, in code written the same day

The T-14 probe tried decoding a frame bound to a stale profile and got
`DECODED_UNDER_STALE_PROFILE`. `TriageFrame(wire=..., profile=...)` was a plain
dataclass constructor, so any caller could mint a frame asserting a profile
nobody had verified — the exact escape hatch D-013 was written to close,
reopened one layer down.

Fixed in-run: construction is guarded, and provenance can only be asserted
through `bind_verified(wire, profile)`, a named function that makes the claim
visible in a diff instead of looking like ordinary object construction. The
probe now reports `UNVERIFIED_BINDING`.

Worth recording as a pattern rather than a bug: closing an escape hatch at the
API level does nothing if the type underneath it is freely constructible.
