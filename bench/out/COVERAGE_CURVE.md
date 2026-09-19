# C2 — semantic coverage curve

Corpus: 51 messages. Token column: `cl100k_base`.

> Stop adding atoms when the marginal atom saves fewer emitted R2 tokens than it costs to define and carry. Reported as marginal tokens saved per atom added; a negative or near-zero tail is the signal to stop.

| atoms | wire bytes | dict bytes | fallback opens | opened | open rate | emitted tokens |
|---|---|---|---|---|---|---|
| 0 | 2509 | 2 | 48 | 51 | 1.000 | 1021 |
| 2 | 2355 | 124 | 41 | 51 | 1.000 | 1846 |
| 4 | 2220 | 267 | 38 | 51 | 1.000 | 2197 |
| 6 | 2150 | 383 | 36 | 49 | 0.961 | 2183 |
| 8 | 2106 | 493 | 34 | 47 | 0.922 | 2170 |
| 10 | 2082 | 608 | 29 | 45 | 0.882 | 2347 |
| 13 | 2043 | 780 | 23 | 39 | 0.765 | 2303 |
| 16 | 2011 | 954 | 19 | 38 | 0.745 | 2588 |
| 20 | 1994 | 1192 | 17 | 37 | 0.725 | 2719 |
| 25 | 1987 | 1508 | 15 | 35 | 0.686 | 2706 |
| 30 | 1987 | 1828 | 15 | 35 | 0.686 | 2706 |

## Marginal return per atom added

| atoms | added | tokens saved | per atom | fallback delta |
|---|---|---|---|---|
| 0→2 | 2 | -825 | -412.5 | -7 |
| 2→4 | 2 | -351 | -175.5 | -3 |
| 4→6 | 2 | 14 | 7.0 | -2 |
| 6→8 | 2 | 13 | 6.5 | -2 |
| 8→10 | 2 | -177 | -88.5 | -5 |
| 10→13 | 3 | 44 | 14.7 | -6 |
| 13→16 | 3 | -285 | -95.0 | -4 |
| 16→20 | 4 | -131 | -32.8 | -2 |
| 20→25 | 5 | 13 | 2.6 | -2 |
| 25→30 | 5 | 0 | 0.0 | 0 |

## Caveat

Coverage is measured against the atoms this corpus actually uses. A dictionary can always be made to look better by adding atoms nobody writes; that is why the curve is plotted against observed usage and why arbitrary English vocabulary is not added.

