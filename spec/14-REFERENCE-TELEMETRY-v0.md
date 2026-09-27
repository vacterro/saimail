# Reference telemetry v0: offline diagnosis without acceptance authority

T-74 ended with a strict-JSON CANDIDATE that the unchanged corpus-ref gate
rejected as `ALLY_GENERATED_REF_OUTSIDE_CORPUS`, and the durable metadata proves
only `outside_ref_count = 1`. The rejected raw ref was never persisted, so the
exact historical failure class is **UNKNOWN** and is not reconstructed here.
This contract defines one additive LAB diagnostic layer for FUTURE outputs and
synthetic controls: it classifies candidate evidence references mechanically,
retains no model prose, and holds no acceptance authority.

This is not a repair, not a second parser, and not a second evidence system.

## Foundational rules

```
REFERENCE_TELEMETRY != ACCEPTANCE
REFERENCE_TELEMETRY != EVIDENCE
REFERENCE_TELEMETRY != REPAIR
UNKNOWN_REF != MALFORMED_REF
EVENT_REF != EVIDENCE_REF
CANONICAL_SHA256_SHAPE != CORPUS_MEMBERSHIP
MODEL_TEXT_MUST_NOT_BE_PERSISTED_AS_A_REFERENCE
T74_EXACT_REFERENCE_FAILURE = UNKNOWN
```

The authoritative product gates remain exactly the existing ones:
`saimail.ally_advice` schema validation, `saimail.ally_generation` corpus-ref
gate, event-floor gate, evidence resolution and semantic review. Telemetry only
observes.

Implementation: `lab/reference_telemetry.py` (LAB only). Tests:
`tests/test_reference_telemetry.py` and
`tests/test_reference_telemetry_integration.py`. No production `saimail/*`
module changes, no filesystem or network access, no model invocation.

## Closed reference classification

Exactly one class is assigned per reference token, from this closed set:

```
KNOWN_EVIDENCE_REF         exact token is present in ReflectionCorpus.refs()
KNOWN_EVENT_REF_AS_EVIDENCE exact token is not a corpus EVIDENCE_REF but
                           exactly matches one declared ReflectionItem.event_ref
CORPUS_ID_AS_EVIDENCE      exact token equals ReflectionCorpus.corpus_id
                           and is not an EVIDENCE_REF
UNKNOWN_CANONICAL_REF      exact canonical shape sha256:<64 lowercase hex>
                           but matches no corpus evidence ref, event ref or
                           corpus id
MALFORMED_REF              text that does not satisfy canonical evidence-ref
                           syntax (wrong prefix, wrong hex length, uppercase
                           hex, non-hex characters, leading/trailing
                           whitespace, blank string)
NON_TEXT_REF               the raw reference value is not a string
```

Precedence is fixed and evaluated in this order: corpus evidence membership,
then declared event ref, then corpus id, then canonical-shape unknown, then
malformed, then non-text. The three known classes assert identity only:
`KNOWN_EVIDENCE_REF` does not prove the cited artifact supports the candidate
prose, and the two confusion classes carry no motive attribution. T-74 is never
assumed to have made any of these errors.

No other class exists. `LIKELY_TYPO`, `SEMANTICALLY_CLOSE`, `PROBABLY_MEANT`,
`MODEL_HALLUCINATION`, `NEAR_MATCH` and any nearest-ref vocabulary are
forbidden. No similarity, edit-distance or first/last-N-hex matching exists.

## Privacy-safe identity

For any text token that is NOT a known corpus EVIDENCE_REF, durable telemetry
may retain only the domain-separated fingerprint

```
sha256(b"SAIMAIL-REFERENCE-TELEMETRY1\x00" || exact UTF-8 token)
```

rendered as 64 lowercase hex characters. Known corpus evidence refs are not
duplicated into telemetry; counts are preferred. For `NON_TEXT_REF` no
`repr(value)` and no other serialization of the value is retained -- only the
class and its count. No malformed or unknown token plaintext is ever persisted.
A text value that is not encodable as strict UTF-8 classifies as
`MALFORMED_REF` and retains no fingerprint.

## Field distribution and aggregate counts

Telemetry distinguishes where references appeared: `OBSERVED` and
`COUNTEREVIDENCE`. No statement text is stored. The closed aggregate fields
are:

```
version
observed_ref_occurrences
observed_unique_ref_tokens
counterevidence_ref_occurrences
counterevidence_unique_ref_tokens
known_evidence_ref_count
known_event_ref_as_evidence_count
corpus_id_as_evidence_count
unknown_canonical_ref_count
malformed_ref_count
non_text_ref_count
unknown_or_invalid_ref_count
observed_unknown_or_invalid_ref_count
counterevidence_unknown_or_invalid_ref_count
known_observed_evidence_ref_count
known_observed_distinct_event_count
event_floor_relation
corpus_ref_relation
unknown_or_invalid_unique_token_count
unknown_or_invalid_fingerprints
```

`*_unique_ref_tokens` counts distinct text tokens in that field.
`unknown_or_invalid_unique_token_count` and `unknown_or_invalid_fingerprints`
deduplicate across both fields: the same unknown token cited in both fields
stays one unique token behind one fingerprint while its occurrences are counted
in each field.

## Event coverage

Using only `KNOWN_EVIDENCE_REF` values from `OBSERVED`, telemetry derives
`known_observed_evidence_ref_count` (occurrence count) and
`known_observed_distinct_event_count` (distinct declared `EVENT_REF` values
resolved through the supplied corpus). The relation is:

```
MET           every OBSERVED ref is a known corpus evidence ref
              AND distinct declared events >= MIN_DISTINCT_OBSERVED_EVENTS
NOT_MET       every OBSERVED ref is a known corpus evidence ref
              AND distinct declared events < MIN_DISTINCT_OBSERVED_EVENTS
NOT_EVALUABLE any OBSERVED ref is malformed, non-text, or outside the
              evidence-ref set (event ref, corpus id, unknown canonical)
```

An unknown ref never counts as a new event, and known refs spanning two events
cannot mask an unknown observed ref. `MIN_DISTINCT_OBSERVED_EVENTS` is the
unchanged product constant. A counterevidence-only violation does not rewrite
the observed event count; it is visible in its own field counters.

## Corpus ref relation

One metadata-only diagnostic relation is derived over both fields:

```
CLEAN                       every ref is KNOWN_EVIDENCE_REF
HAS_OUTSIDE_CANONICAL       only unknown canonical refs present
HAS_IDENTIFIER_TYPE_CONFUSION
                            only event-ref-as-evidence and/or
                            corpus-id-as-evidence present
HAS_MALFORMED               only malformed refs present
HAS_NON_TEXT                only non-text refs present
MIXED_INVALID               more than one invalid category present
```

This is diagnostic vocabulary, not the product verdict. The product verdict
still comes from the existing product gate, which re-reads the actual candidate
and corpus and cannot be made to pass by any telemetry value.

## Two observation levels, no second parser

1. **Raw token observation** accepts already supplied reference values plus
   field identity (`OBSERVED` / `COUNTEREVIDENCE`) and classifies them. It
   performs no JSON parsing and no prose parsing, and it never traverses an
   arbitrary model-output document looking for anything that resembles a ref.
2. **Parsed candidate observation** accepts an already-constructed `AllyAdvice`
   candidate and a `ReflectionCorpus`, and collects references from exactly
   `candidate.observed[*].evidence_refs` and
   `candidate.counterevidence[*].evidence_refs`. It builds no second
   `AllyAdvice` parser.

Membership exists only against the explicitly supplied corpus. There is no
global, filesystem, repository-history, SAIPEN, network or model lookup.

## Bounds

For a parsed candidate the existing product object bounds are authoritative.
For raw synthetic observation the total token count is capped at the maximum
reference occurrences representable by one valid `AllyAdvice` candidate --
`MAX_OBSERVATIONS * MAX_EVIDENCE_REFS_PER_ITEM + MAX_COUNTEREVIDENCE *
MAX_EVIDENCE_REFS_PER_ITEM` -- and overflow refuses with a named code rather
than truncating. A bare string is not accepted as a collection.

## Closed telemetry schema

Every telemetry object is immutable, bounded metadata. Serialization validates
the exact closed schema recursively; an unknown key or a wrong type refuses
before any artifact is written. Fields such as `preview`, `raw_ref`,
`raw_value`, `statement`, `model_text`, `prefix`, `suffix`, `nearest_ref`,
`edit_distance` and `similarity` are outside the schema by construction and
cannot be added.

## No repair

Forbidden everywhere in this layer: lowercasing uppercase hex, adding a missing
`sha256:` prefix, trimming whitespace, nearest-neighbor matching, matching
first/last N hex digits, mapping an event ref to an evidence ref, and replacing
an unknown ref with a known one. The observer reports; it never repairs.

## Product parity

For a fully valid parsed candidate, `CORPUS_REF_RELATION = CLEAN` implies the
existing generation corpus-ref membership logic finds zero outside refs on the
same candidate and corpus. When telemetry reports an outside canonical or
identifier-type-confusion ref, the existing product orchestration still rejects
independently. Telemetry cannot make any candidate pass, and a forged or
monkeypatched telemetry result cannot change the product outcome; the product
path does not consult this module.

## Synthetic controls (normative)

```
C1  clean two-event candidate        CLEAN + MET, zero unknown counts;
                                     product gate may proceed to review
C2  unknown canonical OBSERVED ref   UNKNOWN_CANONICAL_REF, OBSERVED field,
                                     HAS_OUTSIDE_CANONICAL, NOT_EVALUABLE;
                                     product ALLY_GENERATED_REF_OUTSIDE_CORPUS,
                                     reviewer calls 0
C3  unknown counterevidence-only     COUNTEREVIDENCE field identified; product
                                     rejects at the corpus-ref gate, never as an
                                     observed event-floor failure
C4  exact real EVENT_REF as evidence KNOWN_EVENT_REF_AS_EVIDENCE, not
                                     UNKNOWN_CANONICAL_REF; no mapping to member
                                     evidence refs; product still rejects
C5  corpus.corpus_id as evidence     CORPUS_ID_AS_EVIDENCE; product rejects
C6  one-event clean candidate        CLEAN + NOT_MET; product
                                     ALLY_GEN_INSUFFICIENT_DISTINCT_EVENTS,
                                     reviewer calls 0; outside-ref failure is
                                     not an event-floor failure
C7  unknown ref plus two known events NOT_EVALUABLE, never MET
C8  same unknown token in both fields  both occurrence counts, one unique token,
                                     one fingerprint, no duplicated plaintext
C9  malformed matrix                 MALFORMED_REF, no token plaintext
C10 non-text values                  NON_TEXT_REF, no repr persisted
C11 privacy canary                   canary absent from serialized telemetry,
                                     stdout and stderr; fingerprint may remain
C12 near match                       UNKNOWN_CANONICAL_REF only; no typo or
                                     nearest-ref label, no edit-distance code
C13 T-74 historical control          durable outside_ref_count = 1,
                                     outcome_code = ALLY_GENERATED_REF_OUTSIDE_CORPUS,
                                     reviewer_calls = 0; then
                                     T74_EXACT_REF_CLASS = UNKNOWN_FROM_RETAINED_EVIDENCE;
                                     T-74 artifact/report/analysis unchanged
```

## T-74 historical control

The only durable truth about the T-74 bad ref is the bounded metadata above.
The exact class stays `UNKNOWN_FROM_RETAINED_EVIDENCE`; no telemetry class is
manufactured for it, and the historical artifact, report and analysis remain
immutable and hash-pinned by `tests/test_repo_consistency.py`.

## FG-04B handoff surface

FG-04A leaves exactly one small callable surface for a future parsed generator
response:

```
observe_candidate_references(candidate, corpus)
```

FG-04B may persist the returned bounded metadata after a live response is
parsed, and is not required to persist raw refs or prose merely to diagnose a
failure. FG-04A does not register FG-04B, does not enable `JSON_SCHEMA`, and
does not decide whether a future schema constrains `EVIDENCE_REF` values to the
allowed corpus refs or only to sha256 syntax.

## Boundaries

This contract is additive and LAB-only. No earlier spec is rewritten, no
production semantic decision changes, no historical registration or artifact is
touched, and no model or network call is made under it. Network/model calls: 0.
