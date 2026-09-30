# Lab

The bounded SAIFREN laboratory. Role A is reached through the SAIFREN alias;
role B is an external catalog comparator; every artifact is classed by its
own membership evidence, never by catalog eligibility.

```
9router -> SAIRoute -> SAIFREN -> selected current member(s)
```

## Truth classes

| Class | Meaning |
|---|---|
| `SAIFREN_INTERNAL` | every participant observed in the SAIFREN population |
| `SAIFREN_EXTERNAL_COMPARATOR` | one observed member beside one model that is not |
| `SAIFREN_SINGLE_ROUTE` | one participant only |

Every live artifact and report states `EXPERIMENT_CLASS`,
`OBSERVED_COMBO_MEMBERS`, `EXTERNAL_COMPARATORS`, `DISTINCT_REPORTED_MODELS`
and `ROSTER_STATUS`. Membership is discovered read-only through the
documented `/v1/models` surface; when it cannot be observed, the artifact
says `SAIFREN_MEMBERSHIP_NOT_OBSERVABLE` instead of pretending hardcoded
models prove combo membership.

## What runs

| Harness | What it does |
|---|---|
| `lab/saifren_run.py` | one answer schema per call, a real A-to-B handoff, legacy versus control; `--dry-run` proves the harness without touching the network |
| `lab/stability_run.py` | four registered semantic cases, three identical repeats per participant, at a fixed N under a declared call budget |
| `lab/project_corpus_pilot.py` | B-018 real-project corpus pilot: registered selectors, read-only capture, corpus built through the unchanged B-017 builder |
| `lab/project_corpus_generation_pilot.py` | B-019 bounded generation pilot: live registration frozen before discovery, two role-swapped replicates, metadata-only call records |

## The rules the lab runs under

- Transport failure is never a semantic verdict: a missing output is not
  graded as disagreement.
- `LIVE_OUTPUT = EXPERIMENT_DATA`. It is not consensus, truth, a protocol
  change or user intent; agreement between two models promotes nothing.
- Attention outcomes are graded exactly: `EXACT`, `FALSE_IGNORE`,
  `UNDER_OPEN`, `OVER_OPEN` — observations, not a single score.
- Historical live artifacts are immutable experiment evidence; a current
  index keeps the latest report obvious and every earlier reading accessible
  ([lab/LATEST.md](https://github.com/vacterro/saimail/blob/main/lab/LATEST.md)).
- A live run is named by its membership evidence, never by its participants'
  eligibility (D-024), and one response is not a model property (D-025).

The stability registration is committed before the first live run
([lab/stability_registration.json](https://github.com/vacterro/saimail/blob/main/lab/stability_registration.json)).
Five bounded live runs and the later bounded experiments are indexed in
[lab/LATEST.md](https://github.com/vacterro/saimail/blob/main/lab/LATEST.md).
The most recent negative results: **V2-02** (`CANDIDATE_REJECTED_SAFETY` — a
static topic ignore loses relevant messages under semantic topic drift, so
negative evidence closes the gate) and **V2-03** (`REVIEWER_BAD_JSON` — a
request carrying a JSON Schema is not provider enforcement; reachability was
proven, reliability was not).
