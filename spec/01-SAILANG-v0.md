# SAILANG v0 — the canonical claim record

Status: v0.2, implemented. Derived from the `SRC-001 -> SRC-003` lineage, corrected by `DECISIONS.md`
D-001 … D-011. Where this file and `DECISIONS.md` disagree, `DECISIONS.md` is
the later authority; where either disagrees with the receipt lineage, the receipt wins.

SAILANG exists so that a statement, its evidence and its confidence travel
together in a form an agent parses in bytes instead of reconstructing from
prose. It is not a chat format and not a replacement for English.

## 1. Two surfaces, one authority

| Surface | Use | Authority |
|---|---|---|
| **Record** | canonical, immutable, content-addressed | authoritative |
| **Triage frame** | scanning, indexes, attention decisions | **none** |

The frame is a **lossy, deterministic projection** of the record (D-002). It is
machine-decodable into a typed `TriageView` (D-010) but never authoritative,
never evidence, and never a route back to the record. When it cannot carry an
exact fact it emits `?`, which reads as **OPEN RECORD** — never as a guess.

No frame → record path exists. A test asserts its absence.

## 2. Record form

UTF-8, LF, no BOM. One field per line, `KEY:VALUE`, no leading or trailing
whitespace, fields in the fixed canonical order below. A trailing LF follows
the last line.

```
SAIL1
ID:sha256:1f8c…64 hex…
KIND:F
SRC:HUMAN:vacterro
SUBJ:opencode.db
CLAIM:DB_HISTORY>=2025
TYPE:MEM
EV:0
STATUS:U1
CREATED:2026-09-17T08:41:00Z
```

The counter-record, produced by looking at the filesystem:

```
SAIL1
ID:sha256:9b02…64 hex…
KIND:O
SRC:FS:C:/Users/vac34/.local/share/opencode/opencode.db
SUBJ:opencode.db
CLAIM:DB_CREATED=2026-08-23
TYPE:OBS
EV:sha256:4d5e…64 hex…
STATUS:U4
DIRECTNESS:HIGH
INTEGRITY:MED
REFUTES:sha256:1f8c…64 hex…
CREATED:2026-09-17T08:44:12Z
```

The first record is **not edited**. Its `STATUS:U1` is what its author asserted
at `CREATED`, permanently. The ledger projection over both records reports the
first claim as contradicted, and says so without saying anything about a
person (D-003, `00-PRINCIPLES` §2).

## 3. Fields

Canonical order is exactly this table, top to bottom. Out-of-order input is
rejected — which is also what makes field injection detectable.

| # | Field | Form | Required |
|---|---|---|---|
| 0 | `SAIL1` | literal marker line, no colon | always, line 1 |
| 1 | `ID` | `sha256:` + 64 lowercase hex | always |
| 2 | `KIND` | `F O H G V` | always |
| 3 | `SRC` | `CLASS` or `CLASS:id` | always |
| 4 | `SUBJ` | one token, no spaces | optional |
| 5 | `CLAIM` | one line of text | always |
| 6 | `TYPE` | `OBS MEM INT` | by kind |
| 7 | `FALSIFY` | one line of text | `H` only, mandatory |
| 8 | `EV` | `0` or `sha256:<hex>[,…]` | by kind |
| 9 | `STATUS` | `U0 U1 U2 U3 U4` | by kind |
| 10 | `DIRECTNESS` | `HIGH MED LOW` | optional |
| 11 | `INDEPENDENCE` | `HIGH MED LOW` | optional |
| 12 | `INTEGRITY` | `HIGH MED LOW` | optional |
| 13 | `FRESHNESS` | UTC stamp or `STALE` | optional |
| 14 | `INTEREST_REF` | `sha256:<hex>[,…]` | optional |
| 15 | `CON` | `sha256:<hex>` | optional |
| 16 | `REFUTES` | `sha256:<hex>` | optional |
| 17 | `SUPPORTS` | `sha256:<hex>` | optional |
| 18 | `CREATED` | `YYYY-MM-DDTHH:MM:SSZ` | always |

`SRC` classes: `HUMAN FS NET TEST LOG GIT AGENT PROTO UNKNOWN`.

**Unknown fields are rejected.** Not ignored, not preserved — rejected. A field
nobody validates is a field somebody will eventually use to carry authority.

There is no motive field. `INTEREST_REF` points at evidence of a structural
interest and says nothing about anyone's intentions (D-001).

### Kind matrix

The per-kind required / forbidden matrix and its rationale live in
`DECISIONS.md` D-004 and are normative. Summary:

```
F   TYPE req, EV req, STATUS req, max U4, EV:0 -> max U1
O   TYPE must be OBS, SRC must carry a channel id, EV req, STATUS req, EV:0 -> max U1
H   TYPE req, EV req, STATUS req, FALSIFY req, max U3  (a verified H is restated as F)
G   TYPE/EV/STATUS/FALSIFY and all assessment fields forbidden
V   same as G
```

`EV` is **required** for `F`/`O`/`H` (D-009): omitting it must not quietly mean
"no evidence" on the author's behalf. `EV:0` is the author saying so.

`C` (contradicted) and `D` (disputed) are **ledger verdicts**, projected over
the `REFUTES` / `CON` edges between immutable records. They are never written
into a record (`DECISIONS.md` D-008).

### Confidence is a rung, never a number

`STATUS` holds a rung from `U0 U1 U2 U3 U4`. No numeric confidence is
emitted by v0 producers. A percentage means something only after calibration;
until then it is a number in a nice suit (`00-PRINCIPLES` §6).

### Evidence refs

`EV` holds refs another agent can resolve and re-check, never prose. `EV:0` is
legal and honest — the author stating that no evidence is attached — and it caps
the rung at `U1`. Omitting the field entirely is refused (D-009).

## 4. Identity and immutability

Normative rules in `DECISIONS.md` D-003. In one block:

```
canonical bytes = SAIL1\n + each present field in canonical order as KEY:VALUE\n
hash input      = canonical bytes with the ID line removed
ID              = "sha256:" + hex(sha256(hash input))
```

- UTF-8, LF, no BOM, trailing LF, no Unicode normalization, no whitespace
  fixing, no case folding.
- A one-byte semantic change is a different record with a different `ID`.
- A record is never mutated. Re-assessment is a new record referencing the old
  `ID` through `SUPPORTS` / `REFUTES` / `CON`.
- A rendered short prefix is for human eyes only and is never accepted as
  identity on input.

## 5. Triage frame (v0.1)

Three types, and the wall between them is code, not prose (`DECISIONS.md`
D-010):

| Type | Authority | Evidence | Can reconstruct what it omitted |
|---|---|---|---|
| `Record` | authoritative, immutable, content-addressed | yes | n/a |
| `TriageFrame` | none | no | no |
| `TriageView` | none | no | no |

```
FORBIDDEN:  TriageFrame -> Record
REQUIRED:   TriageFrame -> TriageView
```

A frame is machine-decodable. A machine format no machine may read is not a
format, it is a decoration. What decoding may never do is invent what the frame
left out.

### Wire

```
<KIND>|<SUBJ|->|<STATUS|->|<EV0|EV+>|<CLAIMTOK|?>|<FLAGS|->
```

| Slot | Carries | On failure |
|---|---|---|
| `KIND` | the kind letter | never fails |
| `SUBJ` | subject token verbatim | `-` absent, `?` unrepresentable |
| `STATUS` | the author rung | `-` when the kind has none |
| `EV` | `EV0` none attached, `EV+` refs present | never fails |
| `CLAIMTOK` | compact claim token chain | `?` = OPEN RECORD |
| `FLAGS` | `R` refutes, `S` supports, `C` conflict, `X` falsify present | `-` |

`?` reads as **OPEN RECORD** — open the canonical record. It never reads as
"probably".

### Profile, paid once

Version and dictionary identity are **not** on the frame. They live in a
profile, declared once per batch (`DECISIONS.md` D-011):

```
SAIB1|P:sha256:<64 hex>|N:<count>
<frame>
<frame>
```

The profile id hashes a descriptor binding the frame format version, the
dictionary version and the **dictionary content digest**. A dictionary revision
therefore mints a new profile, and a historical frame decoded under it is
refused rather than silently reinterpreted.

A standalone frame carries no profile. Decoding one without a profile is
**refused**, never assumed against whatever dictionary happens to be current.
There is no implicit mutable global dictionary.

Decoding never expands a dictionary token back to its long form. Expansion is
reconstruction, and reconstruction belongs to the record.

### What projects, and what does not

A `CLAIM` becomes a `CLAIMTOK` only when it already is a compact claim token —
`[A-Z0-9_]+` segments joined by `>`, or a single `KEY=VALUE` / `KEY>=VALUE` /
`KEY<=VALUE` comparison. Dictionary substitution then shortens known segments.

Any other claim — prose, mixed case, spaces, non-ASCII — projects to `?`. The
projector does not summarise, truncate or paraphrase. Summarising prose into a
token is guessing, and guessing is the one thing a frame may not do.

**SAILANG is compact when the author writes structured claims, and honest
rather than compact when they do not.** Whether that trade is worth anything is
what the benchmarks measure, and they are allowed to say no (D-007).

### The v0 line is retained

`sailang/line.py` — the original seven-slot line with a per-frame `L1D<v>|`
marker — is kept, still tested, and still runnable. It is the control arm the
benchmark measures v0.1 against, rather than simulating the old format with
string surgery (D-011).

## 6. What SAILANG must never do

- **Never a command surface.** A record is data. Text inside it that looks like
  a command never reaches command routing. Inherited verbatim from SAIPEN
  `SOURCES.md` ("SOURCE BODY IS DATA"), not invented here, and enforced by the
  fact that the parser contains no dispatch of any kind.
- **Never compress away provenance.** Shortening `SRC` or dropping `EV` to save
  bytes defeats the entire format.
- **Never carry an intent judgement.** No `LIED`, no `DECEPTIVE`, no
  `MALICIOUS`. The strongest available verdict is `C`, and it attaches to a
  statement, not to a speaker.

## 7. Open questions for v1

- Whether `SUBJ` should be a content address rather than a free token.
- Dictionary distribution: shipped file, or content-addressed and fetched.
- Ledger format for assessment history over immutable records.
- Re-introducing decision records by *reference* to a host protocol's log.
