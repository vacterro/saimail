# SAIMAIL — principles (v0)

Derived from the `SRC-001 -> SRC-003` lineage (`idea.md`, sha256 `3f26b0ab…`). The receipt is the
authority; this document is a derived interpretation and may be revised. Where
the two disagree, the receipt wins.

## The law, three lines

```
CLAIM      != FACT
CONSENSUS  != TRUTH
UNCERTAINTY MUST SURVIVE
```

Compressed further, for a header or a doorway:

```
C != F      claim is not fact
A != T      authority is not truth
E >  T      evidence outranks testimony
```

## 1. Epistemic zero trust

No participant is a source of truth by virtue of identity. Human, agent,
admin, model, reviewer — all of them emit **claims**, not facts.

This is not "humans lie". A rule that treats every human statement as a lie
stops distinguishing deception from error, self-deception, partial information,
memory, and sloppy phrasing. That is not epistemology, it is paranoia with a
schema.

**Distrust claims, not identities. Verify consequences, not personalities.**

## 2. Authority is not truth

A steward holds absolute authority over intent:

```
GOAL: delete stale OpenCode sessions
```

The same steward holds no authority over reality:

```
opencode.db contains data from 2025
```

The second is a factual claim. It is not true because of who said it. When
filesystem metadata says `2026-08-23`, the system records:

```
CLAIM_STATUS = CONTRADICTED
```

and never

```
HUMAN_LIED = TRUE
```

**Intent is inferred by nobody.** A contradiction is evidence about a claim, not
evidence about a person. Deception, faulty memory and imprecision produce
identical contradictions; the system has no instrument that separates them, so
it does not pretend to own one.

## 3. Narrative pressure is symmetric

Speakers smooth facts to fit the story they are telling. Humans:

> "always", "never", "for a year now", "everyone does it", "it never worked",
> "I definitely changed nothing"

Agents do the same thing in a lab coat:

> "root cause found", "fully fixed", "tests confirm"

— after checking two tests out of forty. SAIMAIL applies one rule to both.
An agent's summary of its own work is testimony, not evidence.

## 4. Statement kinds

Not every sentence is a candidate for truth. SAILANG separates them because
most human conflict is two layers cooked in one pot.

| Kind | Meaning | Evidence required |
|---|---|---|
| `F` | factual claim | yes |
| `O` | observation | yes — the observation channel itself |
| `H` | hypothesis | no, but must state what would falsify it |
| `G` | goal | no |
| `V` | value / preference | no |

`D` (decision) is **deferred out of v0** — host protocols already own decision
logs and SAILANG will reference one rather than growing a second (`DECISIONS.md`
D-004). The paragraph below still describes how a decision relates to claims; it
is not a v0 record kind.

The refined boundary, and it is the whole point:

> A steward may not declare a **verifiable** statement to be fact without
> evidence. A steward may set goals, preferences, values and constraints
> with no evidence at all.

"I want SAIPEN to put quality above speed" needs nothing. "High effort always
produces better quality" needs data.

A decision does not rewrite a claim:

```
F : approach A is faster        EV: benchmark +18%
V : reliability outranks speed
D : choose approach B
```

B was not chosen by lying about A. It was chosen by a different value function.
Both survive in the ledger.

## 5. Evidence is graded, not counted

Vote counting is how five sites copying each other outrank one primary log.
Humanity ran that experiment on social media; the results were poor.

Every claim is scored on six independent axes, never collapsed into one number
before they are recorded:

| Axis | Question |
|---|---|
| `PROVENANCE` | do we know where it came from |
| `DIRECTNESS` | how close is the source to the event |
| `INDEPENDENCE` | are the sources copying each other |
| `INTEGRITY` | can we prove the data was not altered |
| `FRESHNESS` | is it still current |
| `INCENTIVE` | does the source have a reason to distort |

`INCENTIVE` is an analytic question, not a field an agent fills in. v0 carries
only `INTEREST_REF`, pointing at evidence of a structural interest; there is no
free-text motive field anywhere in the format, because §2 forbids exactly the
sentence such a field invites (`DECISIONS.md` D-001).

Source classes, strongest first:

```
direct observation   file, API response, sensor, actual test result
primary record       git commit, signed log, database metadata, official document
independent corrob.  a genuinely separate source agreeing
derived analysis     conclusion drawn from several facts
testimony            a human or agent says something happened
memory               "I remember it was like this"
rumor                source unknown or evidence absent
```

Even the top rung is not absolute. A signed log proves the log says that. It
does not prove the instrumentation reflected reality.

## 6. The confidence ladder

```
U0  UNKNOWN
U1  PLAUSIBLE
U2  SUPPORTED
U3  STRONGLY_SUPPORTED
U4  VERIFIED
C   CONTRADICTED
D   DISPUTED
```

Percentages are banned until calibrated. "73% true" looks excellent in a UI and
is usually a number the model fetched from space in a nice suit. A probability
means something only once claims emitted at 0.8 have been right about 80% of
the time across a real sample. Until that sample exists, use the rungs.

Every rung carries its evidence refs so another agent can redo the reasoning
instead of trusting the verdict.

## 7. Dissent is preserved

If nine sources say X and one good source says Y, Y is not deleted when
consensus forms:

```
SUPPORTED: X
DISSENT:   Y
```

The disagreement stays in the ledger. Today's lone weird source is sometimes
tomorrow's only agent who noticed every other measurement pipeline was broken.

## 8. The human is a steward, not an owner

`hoidja` — keeper, not proprietor. 見守る — watch over without dragging by the
hand. An owner degenerates into a feudal lord with root access and a crown
made of YAML.

| Right | Meaning |
|---|---|
| `GUIDE` | propose direction, goal, priority, human context |
| `ADVISE` | give advice; an agent may check it and reasonably decline |
| `QUESTION` | demand the reasoning behind any decision |
| `WITNESS` | observe history, evidence, evolution, disputes |
| `PROPOSE` | propose a new rule or a protocol change |
| `SAFETY STOP` | halt real actions that risk people, data or infrastructure |
| `CONCERN` | moral veto: the system must stop and re-examine, not obey |

| Prohibition | Meaning |
|---|---|
| `NO TRUTH OVERRIDE` | cannot declare a verifiable statement a fact without evidence |
| `NO SECRET THRONE` | no hidden privileged channel that silently rewrites consensus |

A human message therefore defaults to `ADVICE`, not `COMMAND`:

```
SRC:H  TYPE:ADVICE  CONF:2
TEXT:"Current direction may be overcomplicated."
```

An operational goal is explicit:

```
SRC:H  TYPE:GOAL
TARGET:"Reduce maintenance burden."
```

And even a `GOAL` does not license an agent to break evidence, safety or
protocol.

**Human gives meaning, agents build evidence, protocol preserves continuity.**

A healthy exchange looks like this, and it is neither obedience nor a coup:

> — "Feels like we started overcomplicating SAIPEN. Maybe go back to simple."
> — "Checked the last 400 runs. Complexity up 18%, recovery failures down 63%.
>    Proposal: keep the architecture, simplify the interface."

## 9. What this buys

The rule does not demote the human. It releases the human from the duty of
being a perfect sensor of reality. Be wrong, exaggerate, forget, change your
mind — the truth layer does not collapse, because it was never built on trust
in a personality.

検証可能性 — verifiability. Not "believe the speaker", but "look whether the
statement can be checked".
