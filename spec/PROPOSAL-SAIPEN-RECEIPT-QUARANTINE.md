# Proposal — receipt quarantine on SAIPEN's export path

**Status: PROPOSED to SAIPEN Core. Not implemented there, and not implemented
around it from here.** Origin: `SRC-009` Target A5, ticket T-32, decision D-023.

SAIMAIL built everything it owns: a structural detector, a quarantine record, a
sanitized derivative, an authority path that survives without the original, and
a tested distribution policy (`saimail/quarantine.py`,
`provenance/quarantine/`, `tests/test_quarantine.py`). What it cannot do from
this repository is stop SAIPEN's own exporters from shipping the original
receipt body. Doing that by hand — moving the body, editing intake metadata,
teaching an exporter a private exclusion — would be improvising around the
protocol, so this subtarget stops here and states the requirement.

## PROTOCOL_CHANGE_PROPOSAL

Give a SAIPEN source receipt a **distribution state**, orthogonal to its
lifecycle status:

```
ACTIVE_NORMAL          the receipt body travels with every export, as today
SENSITIVE_QUARANTINED  id, digest, length, reason, derivative identity and
                       provenance travel; the body lives only in a protected,
                       non-exportable local location
```

The defect class this eliminates: **an immutable receipt whose body carries a
credential can only be exported by exporting the credential** — and SAIPEN's
credential detection does not see a credential that sits inside a file name, so
today it cannot even tell that it is doing so.

Immutability is kept exactly: the body is never rewritten, its digest never
changes, Work and Contract links stay valid. Only where the bytes may travel
changes.

## EVIDENCE

Reproduced on 2026-09-17 against protocol 8.0.1 and this project's own
`.saipen/`. Every command below prints booleans, codes or counts; none prints
receipt content.

1. **SAIPEN's detector passes the receipt.** Through `saipen_engine`:
   `intake._looks_sensitive(SRC-007) -> False`,
   `intake._redact_text(SRC-007) != SRC-007 -> False`,
   `codec.redact_credentials(SRC-007) != SRC-007 -> False` (its five patterns
   cover `ghp_`, `AKIA`, `sk-`, a postgres URI password and a bearer token), and
   `intake._legacy_sensitive_source_gate(project) -> SOURCE_CREDENTIALS_SAFE`.
2. **The metadata agrees with the detector, not with the bytes.**
   `SRC-007.meta.json`: `status ACTIVE`, `sensitive false`,
   `redaction.applied false`, `source_authority.mode exact`.
3. **The bytes do carry credential-bearing material.** SAIMAIL's structural scan
   (`saimail-credential-scan/1`) reports exactly one finding:
   `CREDENTIAL_LABELLED_FILENAME`, line 3, bytes 60..93 — a file name whose stem
   pairs a secret label with other runs. The operator states in `SRC-009` that
   this file name embeds a credential value. No other receipt (`SRC-001` to
   `SRC-009`) has a finding, and no other file in the project holds any
   searchable fragment of the component (`withheld_fragments`, in memory).
4. **SAIPEN's export contract ships the body.**
   `tools/saipen_engine/audit_manifest.py` declares `("intake", True, 8000)` and
   `("archive/source", True, 8000)` as conditional evidence and
   `NON_EXPORTABLE = ("locks/", "recovery/", "LOCAL_STATE.json")` — nothing
   else. This project's generated `.saipen/MANIFEST.json` says the same.
   `bootstrap/export.ps1` archives the whole memory root
   (`Compress-Archive -Path $saipenDir`). `SOURCES.md` states it outright:
   state-only exports include `.saipen/`, "therefore every active receipt ...
   remains in the bundle".
5. **Measured, not assumed.** `saipen_export_status(manifest, records)` returns
   `NOT_HONOURED` for this project; the quarantine record carries that value and
   `tests/test_quarantine.py` fails the day the record and the manifest disagree.
6. **No existing route is a quarantine.** Closure moves the body to
   `archive/source/`, which is exported too. `purge --confirm` requires closure
   and destroys the forensic bytes outright. Moving the body by hand turns the
   reread and release gates, which read `intake/active/SRC-NNN.md`, into
   `ORPHAN_RECEIPT` / `SOURCE_CORRUPTION` findings about a receipt that is
   intact.
7. **What SAIMAIL proved without SAIPEN.** A normal distribution built under the
   SAIMAIL policy (in memory, in the test) carries the quarantine record, the
   derivative and the intake metadata, carries zero withheld fragments, and
   still resolves `SRC-007` and its three backlog attributions to
   `USER_ACCEPTANCE` with the original absent.

## REQUIRED_CORE_CHANGE

1. **Distribution state on receipt metadata, additive.** A `distribution`
   object beside `status`: `state`, `reason` (category code), `detector`,
   `derivative` (`id`, `path`, `sha256`, `redaction_version`) and the authority
   receipt that ordered it. `status` keeps its meaning; a consumer that ignores
   `distribution` loses nothing it has today.
2. **A protected local location.** For example
   `.saipen/quarantine/source/SRC-NNN.md`, listed in the audit manifest's
   `non_exportable`, with a `quarantine.excluded_bodies` list naming every
   quarantined body. Because this changes what a consumer must leave out, the
   manifest `contract_version` goes to 2; a v1 consumer already refuses an
   unknown version, which is the correct failure.
3. **Gates that know the state.** Reread, closure, release and recovery accept a
   `SENSITIVE_QUARANTINED` receipt whose body is at the protected location
   (digest verified there), and, in a distributed copy where it is absent,
   verify identity from the metadata digest and the derivative digest instead of
   reporting an orphan. Closure never moves a quarantined body into
   `archive/source/`.
4. **Detection that sees file names.** `_looks_sensitive` and the release
   credential gate gain path-component classes — a credential-labelled file
   name and a high-entropy path component — so a receipt like `SRC-007` stops
   reading as `SOURCE_CREDENTIALS_SAFE`.
5. **One writer.** `saipen source quarantine SRC-N --reason CODE --derivative PATH
   --authority SRC-M`: idempotent, LOG event, protected-path aware. `source show`
   of a quarantined receipt returns the derivative; the original only under an
   explicit forensic flag, never by default.
6. **Exporters that obey the manifest.** `bootstrap/export.ps1`,
   `bootstrap/export.sh` and `build_handoff_archive.py` exclude
   `non_exportable` entries. (They currently compress the whole directory, which
   also ships `locks/` and `recovery/` — a separate defect with the same fix.)

## SAFE_MIGRATION_PLAN

0. **Rotate the credential.** The only remedy for an exposed secret. Nothing
   below substitutes for it, and archives already distributed cannot be
   recalled.
1. **Detector first, report-only.** Ship the path-component classes as findings
   that name affected receipts without moving anything. Projects learn what
   they hold before any byte moves.
2. **Manifest contract v2.** Add `quarantine.excluded_bodies` and the protected
   location to `non_exportable`; bump `contract_version`; v1 consumers refuse.
3. **The quarantine operation, crash-safe.** Write the body to the protected
   location and verify its digest; write the `distribution` metadata; remove the
   hot copy. Recovery reconciles each crash point: body in both places resumes,
   body only in the protected location is done, a digest mismatch is
   `SOURCE_CORRUPTION`. Receipt id and digest never change, so every Work and
   Contract link stays valid.
4. **Exporters honour v2**, with hostile controls:
   - an export of a project holding a quarantined receipt contains its metadata
     and derivative and zero fragments of the withheld component;
   - closing or archiving a quarantined receipt leaves its body in the protected
     location;
   - `source show` without the forensic flag never returns the original;
   - an exact recapture of the same bytes deduplicates to the quarantined
     receipt and creates no new hot copy;
   - a derivative that claims authority of its own is refused.
5. **SAIMAIL adopts the core state.** `provenance/quarantine/SRC-007.json`
   becomes a consumer of SAIPEN's `distribution` record, its
   `saipen_export.status` moves to `HONOURED` under a new decision entry, and
   the note in `original.protected_location_blocker` is retired — recorded, not
   silently edited.
6. **Rollback.** Move the body back to the hot intake (digest verified) and drop
   the `distribution` object. Nothing about the receipt's identity changed, so
   nothing downstream needs repair.

## Non-goals

Encryption at rest, crypto of any kind, secret scanning of ordinary source
files, recalling archives that already left the machine, and any change to how
a receipt body is hashed.
