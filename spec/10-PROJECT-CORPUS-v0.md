# PROJECT CORPUS v0

Normative decision: [D-050](DECISIONS.md). This specification defines the
bounded real-project corpus builder above the completed B-016 generation layer
([ALLY_ADVICE GENERATION v0](09-ALLY-GENERATION-v0.md)). It adds no SAILANG
kind, no encryption format, no model adapter and no store. Nothing here starts
a real-project pilot, and nothing here ingests this repository's own history.

## Purpose and authority

B-016 froze the generation gate but deliberately left one authority boundary
open: `EVENT_REF` arrived already declared on `ReflectionItem`, and nothing
defined what a real project artifact is, who selects the bounded source set,
how several artifacts are declared to belong to one event, or how corpus
selection honesty is represented. B-017 answers exactly those questions with a
pure bounded builder that converts explicitly supplied project captures plus
explicit event declarations into the existing `ReflectionCorpus` and mints a
non-transferable `BuiltProjectCorpus` proof.

The builder creates a deterministic representation of one explicit bounded
selection. It never proves that the selection is complete, unbiased or
correct; it never decides whether the resulting events form a meaningful human
pattern. It does not know what was omitted upstream.

```
SOURCE_REF != EVIDENCE_REF
EVIDENCE_REF != EVENT_REF
EVENT_REF != TRUTH
TICKET_ID != EVENT_IDENTITY
COMMIT_ID != EVENT_IDENTITY
FILE_PATH != EVENT_IDENTITY
FILENAME != EVENT_IDENTITY
TIMESTAMP_PROXIMITY != EVENT_IDENTITY
SAME_SOURCE_KIND != SAME_EVENT
DISTINCT_SOURCE_REF != DISTINCT_EVENT
DISTINCT_EVENT_REF != SEMANTIC_PATTERN_PROOF
CORPUS_BUILDER_DECLARATION != GLOBAL_COMPLETENESS
SELECTED_CORPUS != ALL_RELEVANT_EVIDENCE
```

## No discovery

The builder performs zero source discovery. It does not walk directories,
inspect repository metadata, read SAIPEN BOARD/LOG, read LEGACY or
`HumanPrivateStore`, query a network, a model, a connected application or any
host memory. `build_project_corpus(request)` takes one data object and nothing
else: there is no path parameter, no "auto" flag and no location to crawl. The
caller supplies every candidate project artifact explicitly; a supplied value
is data, not a place to look.

Selection basis is frozen to `EXPLICIT_BOUNDED_SET` and completeness is frozen
to `NOT_PROVEN`. A caller may not set `COMPLETE`, `ALL_RELEVANT`, `EXHAUSTIVE`
or `UNBIASED` as a machine-trusted v0 value; the request refuses such a claim
mechanically (`PROJECT_CORPUS_SELECTION_BASIS_REFUSED`). No confidence
percentage exists anywhere in this layer.

## Project scope

Every build is bound to exactly one canonical `PROJECT_SCOPE` token supplied
by the caller (`project:saimail` form). Scope is never inferred from a working
directory, repository name, remote, folder name or any host state. Request
scope, artifact scope and declaration scope must match exactly: prefix
matching is forbidden (`project:saimail` never matches `project:saimail-test`),
and a mixed-project build refuses (`PROJECT_CORPUS_SCOPE_MISMATCH`).

## ProjectArtifact

One immutable pre-corpus object captures one explicitly supplied project
artifact:

- `PROJECT_SCOPE` — the exact canonical scope above;
- `SOURCE_KIND` — a member of the frozen v0 `PROJECT_OPERATIONAL` vocabulary
  (`OPERATOR_DECISION`, `SPEC_DECISION`, `IMPLEMENTATION_CHANGE`,
  `TEST_RESULT`, `REVIEW_FINDING`, `INCIDENT`, `RUNTIME_OBSERVATION`);
  unknown kinds refuse and free-form kinds do not exist. Source kind is
  provenance metadata and never a truth rank: `TEST_RESULT` does not mean
  `TRUE`, `REVIEW_FINDING` does not mean `VALID_FINDING`, and
  `OPERATOR_DECISION` does not mean `FACT`;
- `SOURCE_REF` — the bounded explicit upstream locator/identity the caller
  says this capture represents (`saipen-event:E-123`, `ticket:T-66`,
  `commit:<hash>`, `test-run:<id>`, `decision:D-049`, `file-digest:<hash>`,
  `review:<id>` are examples, not trusted automatic identities). No form is
  automatically treated as event identity or as truth;
- `OBSERVED_AT` — canonical UTC informational source time. It never determines
  `EVIDENCE_REF`, `EVENT_REF`, pattern eligibility, attention priority or
  semantic truth, and the builder never invents it from a filesystem mtime, a
  checkout time or its own clock; the caller supplies it explicitly or does not
  build;
- `CONTENT` — bounded exact UTF-8 project-operational evidence text,
  preserved byte-for-byte. The builder never strips, summarises, rewrites,
  model-normalises, spell-corrects or translates it. Trailing-newline
  differences remain real content differences, and two byte-different captures
  are never pretended identical.

There is no caller-writable `EVIDENCE_REF` field: the builder mints it.

## Artifact identity

`EVIDENCE_REF` is minted mechanically from a domain-separated construction
over `PROJECT_SCOPE`, `SOURCE_KIND`, `SOURCE_REF` and the exact content digest
of the UTF-8 `CONTENT`:

```
sha256(
    b"SAIMAIL-PROJECT-ARTIFACT1\x00"
    || canonical(PROJECT_SCOPE)
    || canonical(SOURCE_KIND)
    || canonical(SOURCE_REF)
    || sha256(exact UTF-8 CONTENT)
)
```

`EVENT_REF` is not an input, no arbitrary caller evidence ref is accepted and
identity is never derived from a filename or from content alone: two identical
texts from distinct upstream artifacts stay distinct evidence artifacts
because `SOURCE_REF` participates in identity. Changing only `OBSERVED_AT`
leaves the `EVIDENCE_REF` stable while the resulting corpus representation
changes, so the `BUILD_ID` and B-016 `CORPUS_ID` change with it.

Within one build request one upstream source appears exactly once. An exact
duplicate capture refuses with `PROJECT_SOURCE_REF_DUPLICATE`, and the same
`SOURCE_REF` with different content refuses with `PROJECT_SOURCE_REF_CONFLICT`:
two versions of one upstream source identity are never silently accepted and
never silently deduplicated.

## Selection window

Every build declares `WINDOW_START` and `WINDOW_END`, both canonical UTC with
`WINDOW_START < WINDOW_END` (`PROJECT_CORPUS_BAD_WINDOW` otherwise), and every
`OBSERVED_AT` must satisfy the exact half-open rule
`WINDOW_START <= OBSERVED_AT < WINDOW_END`. There is no clamping and no
automatic exclusion: an out-of-window artifact refuses the build
(`PROJECT_CORPUS_WINDOW_EXCLUDED`), because silently dropping it would change
the selected source set without explicit caller knowledge. The window bounds
the supplied sample; it never proves that every relevant artifact in that
period was included.

## Event declaration

Event grouping is explicit and caller-authored. A `ProjectEventDeclaration`
carries the project scope and `MEMBER_EVIDENCE_REFS`, a bounded canonical set
of minted `EVIDENCE_REF` values; membership references evidence identities
only, never `SOURCE_REF`, because grouping happens after artifact identity is
mechanically fixed. Duplicate members (`PROJECT_CORPUS_DUPLICATE_MEMBER`),
empty declarations (`PROJECT_CORPUS_EMPTY_EVENT`) and malformed member refs
(`PROJECT_CORPUS_BAD_DECLARATION`) refuse. A caller cannot supply an
`event_ref` argument at all: the builder computes it.

```
EVENT_GROUPING_AUTHORITY = EXPLICIT_CALLER_DECLARATION
EVENT_GROUPING_IS_TRUTH = false
AUTO_EVENT_INFERENCE = false
```

The declaration says only: "for this corpus build, the caller declares these
evidence artifacts to represent one underlying operational occurrence/group".
It does not prove the declaration true.

## Event identity

`EVENT_REF` is minted mechanically from the exact canonical group:

```
sha256(
    b"SAIMAIL-PROJECT-EVENT1\x00"
    || canonical(PROJECT_SCOPE)
    || canonical_sorted(MEMBER_EVIDENCE_REFS)
)
```

Properties: the same exact grouping mints the same `EVENT_REF`; any membership
change or artifact regrouping mints a different one; no event label, filename,
ticket id, timestamp bucket or model judgement participates beyond what the
evidence artifacts themselves already carry indirectly. An event may contain a
single evidence artifact — some real occurrences genuinely have one usable
capture — and the existing B-016 repeated-pattern floor (`>= 2` distinct
declared events, `ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS` otherwise) still
decides recurrence eligibility, not this layer.

## Exact partition

For v0, event declarations must form an exact partition of the selected
artifact set: every `EVIDENCE_REF` belongs to exactly one declaration. An
unassigned artifact (`PROJECT_CORPUS_UNASSIGNED_ARTIFACT`), an artifact in two
events (`PROJECT_CORPUS_ARTIFACT_MULTI_EVENT`), a declaration referencing an
unknown artifact (`PROJECT_CORPUS_UNKNOWN_EVENT_MEMBER`) and an empty event
`PROJECT_CORPUS_EMPTY_EVENT` all refuse; the grouping is never repaired
automatically. This gives a mechanically complete grouping of the bounded
selected set and nothing beyond it: it does not prove global event
completeness.

## No automatic grouping

The builder never groups artifacts by ticket id, commit id, filename,
directory, path, timestamp, timestamp distance, exception string, source kind,
text resemblance, embeddings, regex or a model. Those may someday suggest
candidates to an operator under another policy; in B-017 they are not event
identity authority. No helper accepting such inputs exists.

## Request, BUILD_ID and result

`ProjectCorpusRequest` binds one scope, one window, the fixed selection basis,
the artifacts and the declarations; it carries no model, no path to crawl, no
network endpoint and no "auto" flag. Validating order is fixed: shapes and
scope, window rule, source-ref uniqueness, then the exact partition.

`BUILD_ID` is a domain-separated identity bound to the builder policy version,
scope, window, selection basis, canonical artifact descriptors (minted
`EVIDENCE_REF`, source kind, source ref, observation time) and canonical event
declarations, all in a deterministic order; caller list order is never
semantic. `BUILD_ID` answers "what exact builder input and policy produced
this corpus?"; the `CORPUS_ID` remains the existing B-016 identity of the
resulting `ReflectionCorpus`, reused unchanged.

`BuiltProjectCorpus` is minted only by `build_project_corpus`, after artifact
validation, window validation, source-ref uniqueness, event partition
validation, event-ref computation, `ReflectionCorpus` construction and
`BUILD_ID` construction. It binds the exact request, the exact corpus and the
exact policy through a constructor-only mint token that is not retained:
direct construction and `dataclasses.replace` refuse
(`PROJECT_CORPUS_PROOF_FORGED`), and the bound identity and corpus are
recomputed from the bound request, so an old proof cannot transfer across a
different corpus, grouping, window or artifact set. The proof exposes bounded
audit metadata only: `BUILD_ID`, `CORPUS_ID`, scope, window, artifact and
event counts, capture-to-evidence-ref and evidence-ref-to-event-ref mappings
and source kind per evidence ref. It is called `BuiltProjectCorpus`, not
`TRUE_CORPUS`, `COMPLETE_CORPUS`, `VALID_PATTERN_CORPUS` or
`UNBIASED_CORPUS`.

`SOURCE_DOMAIN` is exactly `PROJECT_OPERATIONAL`; `OBSERVED_SCOPE` is the
project scope; `CONTENT` is the exact capture; `EVIDENCE_REF` and `EVENT_REF`
are builder-minted. No new `ReflectionItem` schema exists, `SOURCE_KIND` is not
smuggled into content or into the item schema, and no corpus or plaintext is
persisted automatically: the builder writes nothing, calls nothing and returns
objects.

## B-016 stays generic

The generic B-016 path is unchanged: any caller may still construct a
`ReflectionCorpus` for synthetic experiments, and the manual B-012 path is
untouched. B-017 adds a stricter provenance corridor for future real-project
pilots. A future real-project pilot must require `BuiltProjectCorpus` rather
than an arbitrary `ReflectionCorpus`; the narrow helper
`require_built_project_corpus` exists for that gate
(`PROJECT_CORPUS_BUILDER_PROOF_REQUIRED`) and no pilot runner is built here.

## Honest limit

The builder does not prove that the selection is complete, unbiased or
globally correct, that the declared grouping is true, that two declared events
are genuinely independent, that any capture is truthful, or that a distinct
declared event set is a semantic pattern. It provides explicit source bounds,
explicit caller-authored grouping, mechanically minted identities, exact
partition proof, deterministic rebuildability, regrouping invalidation and a
non-transferable provenance proof. That is the actual guarantee.
