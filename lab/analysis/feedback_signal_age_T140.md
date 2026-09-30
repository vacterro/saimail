# Dated guidance with preserved history

T-139's compact view retained a correct historical assessment after the source
letter expired, but offered no date or eligibility basis. T-140 records that
pre-change view in `.saipen/evidence/T-140-feedback-age/baseline.json`: a
2026-09-30 DEFERRED/WAITING_DEPENDENCY assessment still appears on 2026-12-31.
No reading reference appears. The defect is missing temporal context, not loss
of history or a wrong lifetime count.

The new additive `SAIMAIL_FEEDBACK_SIGNALS_1` metadata states an observation
time and seven-day window over latest distinct receiver assessments. Old,
future-dated and pending assessments remain explicitly counted. Recent live
decisions require unexpired recorded relevance. Recent terminal assessments
can explain expired letters as ASSESSMENT_ONLY, without reviving their content.
The fixed seven-day horizon is a local design choice, not a scientifically
established optimum. Reading, reporting, retaining and identical retries do not
refresh it. Lifetime counts, history and compatibility fields are preserved.

`control.py` applies the same six checks to the retained before data and the
current fixed-clock projection. The old view fails the four temporal checks;
the new view passes all six. Both retain the historical assessment and omit
expired reading references. `control.json` binds the verifier and before bytes
by SHA-256. This is a missing-feature control over observation data, not an
independent model verdict.

`tests/test_feedback_signal_age.py` exercises inclusive age boundaries, future
timestamps, exact relevance expiry, date ranges/counts, pending exclusion,
dated late correction, immutable decision history, unchanged read/report/
retain/retry timestamps, one sampled cycle clock, metadata-only observations,
corrupt dates, older peers and malformed consumer claims. Its first late-correction
fixture exceeded the sealed-envelope TTL and correctly received ALREADY_EXPIRED.
The corrected fixture separates expired letter relevance from an available
sealed envelope. A separate control preserves the TTL refusal; no decrypt or
lifecycle guard was weakened.

Replay version 3 keeps the previous discovery, continuity and feedback controls,
and checks temporal eligibility independently of separately sampled observation
times. Lifetime metrics still compare exactly. Attempts 001 and 002 under
`lab/out/FEEDBACK_SIGNAL_AGE_T140/` retain three rotating-order repetitions per
mode. Attempt 002, with the final history labels, passes 24 controls:

| Observation | CLI calls including negotiation | Agent-visible normalized bytes |
| --- | ---: | ---: |
| Separate awareness + metrics | 3 | 3077 |
| Full cycle | 2 | 3707 |
| Host focus | 2 | 1279 |

Focus is 65.5% smaller than full cycle in this trial. It grows from the earlier
T-139 result of 978 bytes to 1279 (+30.8%) because the temporal basis and lifetime
label are now explicit. Wire bytes remain the same between cycle and focus
(4791 here). The historical T-139 measurements remain unchanged. This cost is
visible rather than presented as a free improvement. Timing is descriptive.

The trials use constructed temporary mailboxes, actual T-137 regression artifacts
and scripted receiver choices. They make no network/provider calls and do not
demonstrate recurring field usefulness, lower receiver effort, independent
successor judgment or improved model weights. Those remain part of the active
evolution objective in `humbox/EVOLUTION.md` and roadmap v6 section 17.

The active agent also read its configured local mailbox during the actual T-140
VERIFY phase. `actual_entry.json` records KNOWN temporal basis, zero reviewed
cases and zero reading references, with STATE/IDENTITY/BOARD/LOG byte-identical
before and after. This second real entry, following T-139, demonstrates a
working metadata seam; two empty observations establish no receiver benefit.

Canonical full suite: 2800 passed, zero failures/errors/skips (140.840 seconds;
`full.xml`). Focus/cycle/correspondence/temporal checks: 127 passed. Ruff and
owned-file whitespace checks passed. No installed/frozen release was changed.

REVIEW independently reran the ticket's verifier: 127 tests and a fresh replay
attempt 003 passed all 24 controls with the same 3707/1279 visible-byte results.
The data control binds current producer/consumer source and after-data hashes;
its same verifier evaluates both retained before and current observations.
No original lifetime, retry, envelope-TTL or isolation oracle was weakened.

T-141 follows the observed remaining cost: offer compact focus through negotiated
CLI so agents can reuse command setup and reduce wire bytes, retaining older
host fallback. This remains a measured integration improvement; recurring useful
receiver decisions and independently selected successor use still require
actual Work evidence.
