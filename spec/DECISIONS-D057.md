# Decisions log addendum

Parent: [spec/DECISIONS.md](DECISIONS.md). The parent file is an exact-hash
frozen source of the B-018 experiment. This additive entry lives separately
to preserve that registered source without weakening its drift gate.

## D-057 — The SAIPEN seam S2 bridge reads caller-named evidence, binds the acting seat, and cites a LOG line by hash only (T-108 / S2)

The defect class is testimony without a checkable witness at the one seam the
project was designed around (`spec/04-SAIPEN-SEAM.md`). An agent working under
SAIPEN had to copy its seat by hand into `saimail-local init --seat`, and could
refer to project work only in free prose, so a message about a SAIPEN event
carried nothing a reader could re-check (`C != F`). T-108 measured three further
ways a naive bridge fails, and this decision closes each one:

1. **A library that reaches into SAIPEN memory.** The first build placed the
   SAIPEN layout inside `saimail/`; the I1 structural test
   (`tests/test_i1_inert_payload.py`) refused it because the library must never
   name SAIPEN's memory root. **Decision:** `saimail.saipen_bridge` takes the
   exact STATE, IDENTITY and LOG files from its caller and writes to none of
   them. The SAIPEN directory layout and project-root discovery live in the
   operator entrypoint (`saimail-local saipen ...`), the pattern
   `tools/dev_access.py` already uses.
2. **A mailbox inside the project tree.** The first build defaulted the
   workspace to `<project>/mail/<seat>`; `tests/test_repo_consistency.py`
   refused it because the Post Office root is caller-supplied (D-031). A
   gitignore would only have hidden raw-custody private keys in the tree.
   **Decision:** `saipen init` requires `--workspace`; the bridge supplies the
   seat only.
3. **The last owner mislabelled as the actor.** `STATE.agent` records who last
   owned the project, not who is acting. Binding it silently put seat `astra` on
   work astra never did (operator report, T-108). **Decision:** the seat is
   `--seat`, else `SAIPEN_AGENT` (SAIPEN's explicit actor carrier), else
   `STATE.agent`. The binding reports `seat_source` and `state_agent` so an
   inherited seat is visible, never implied.

**Citation shape.** `cite --event E-###` locates exactly one LOG line whose
fixed skeleton id is that event (active `LOG.md` and sealed `logs/LOG-*.md`),
and emits one `KIND:O` record: `SRC:LOG:saipen/<lineage>/E-###`,
`EV:sha256:<exact line bytes, terminator excluded>`, `STATUS:U4`,
`DIRECTNESS:HIGH`, `INTEGRITY:MED`, `SUBJ` the ticket (else the event),
`CLAIM:SAIPEN LOG carries E-### <TAXONOMY>`. The claim is only that the LOG
carries that line. What the line says is not asserted, and the line's text never
travels inside the record: the line is evidence by hash, not payload, so I1
holds for command-looking LOG text. A `[parent: E-###]` mention or commentary
never counts as the event; two lines headed by one id refuse
(`SAIPEN_EVENT_AMBIGUOUS`).

**Re-check is re-derivation, not a hash compare.** `verify --record` rebuilds
the citation the line yields at the record's own `CREATED` and requires the
identical record. REVIEW pass 1 measured the weaker verifier: with only `EV`
compared, a record that kept the right hash but lied in `SUBJ`, `CLAIM`,
`STATUS` or `INTEGRITY` returned `CITATION_VERIFIED`. The regression tests were
red against that verifier and are green against this one. Outcomes:
`CITATION_VERIFIED`, `SAIPEN_CITATION_MISMATCH` (the line changed),
`SAIPEN_CITATION_INVALID` (not a citation, malformed `SRC`, or any field that
differs), `SAIPEN_CITATION_FOREIGN` (another project's lineage).

**Transport and scope.** A cited record is sent with the unchanged
`saimail-local send --record`; no wire field, no state field and no write path
into SAIPEN are added. This is spec/04 stage S2 only; S4 (a registered SAIPEN
extension) stays unstarted. Limits: `INTEGRITY:MED` because a LOG file is plain
writable text, so the hash proves the line is unchanged since citation, not that
it was ever true; a reader without the same project tree cannot re-check; LOG
times are UTC without a zone marker and are hashed as written.

**Release truth.** The bridge is checkout-only. The frozen `0.0.2a3` wheel
(D-056) does not contain it, and no a3 evidence is claimed for it. The checkout
is ahead of frozen `0.0.2a3` by S2 alone; no version bump, rebuild, tag, push or
publication is part of T-108.

**Evidence.** `tests/test_saipen_bridge.py` (binding, seat precedence,
caller-supplied workspace, no write to what it reads, citation shape, CRLF,
sealed segments, skeleton-only ids, ambiguity, forged-field and malformed-SRC
refusals, a sealed end-to-end send that the receiver opens with the cited content
identity, CLI surface); `tests/test_i1_inert_payload.py` unchanged and green for
the new module; live run on this project: E-1362 cited, sealed `opus -> reviewer`,
`READ`, `CITATION_VERIFIED`.
