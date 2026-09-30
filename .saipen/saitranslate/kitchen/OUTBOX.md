# OUTBOX

## SAIT-001: superseded initial Japanese and Ukrainian README translations
- **status:** stale
- **summary:** superseded by SAIT-003; retained as history only
- **main_project_refs:** [README.md, README.ja.md, README.uk.md]
- **critical:** false
- **producer:** saitranslate
- **source_head:** 3fa8f2295f564a6a75733905388ddee55b2f73b8
- **source_tree_fingerprint:** git-delta-v1:724edbad100d2a9034bc55b0d61fa4e1711ab83167e9d240e88cd65690e5183d
- **role_revision:** sha256:7d18729f8d94eb58471ae3bb5fad9151e8499fea291e574b26439c5c89012e41
- **coverage:** historical v0.0.1 package
- **payload:** historical
- **verified:** FAIL -- source drift superseded this package
- **instructions:** none -- superseded history, never integrate
- **details:** Kept for forensic history. Never collectable.

## SAIT-002: superseded v0.0.2a2 Japanese and Ukrainian README translations
- **status:** stale
- **summary:** complete Japanese and Ukrainian README translations from the v0.0.2a2 tree; superseded by the current v0.0.2a3 payload in SAIT-003
- **main_project_refs:** [README.md, VERSION, README.ja.md, README.uk.md]
- **critical:** false
- **producer:** saitranslate
- **source_head:** 3fa8f2295f564a6a75733905388ddee55b2f73b8
- **source_tree_fingerprint:** git-delta-v1:19a295b7c542a2828d9f724b3fc86ac1ec3a8697c0f20728b516d0c4a6603aa2
- **role_revision:** sha256:7d18729f8d94eb58471ae3bb5fad9151e8499fea291e574b26439c5c89012e41
- **coverage:** historical v0.0.2a2 README translations
- **payload:** historical
- **verified:** FAIL -- current source fingerprint differs
- **instructions:** none -- superseded by SAIT-003, never integrate
- **details:** The immutable READY artifacts remain forensic evidence. Their source identity is stale and must not be collected.

## SAIT-003: current Japanese and Ukrainian README payloads; incomplete translation surface
- **status:** draft
- **summary:** rebuilt Japanese and Ukrainian README translations against current v0.0.2a3 source; package is intentionally not collectable because 27 optional locales and the real GUI-string surface remain uncovered
- **main_project_refs:** [README.md, VERSION, saimail/gui_app.py, saimail/gui_adapter.py, README.ja.md, README.uk.md]
- **critical:** false
- **producer:** saitranslate
- **source_head:** 3fa8f2295f564a6a75733905388ddee55b2f73b8
- **source_tree_fingerprint:** git-delta-v1:8b5376574aa5f803b4d48b6863a90b58aa658d9684c6b42332a8762015a5763f
- **role_revision:** sha256:7d18729f8d94eb58471ae3bb5fad9151e8499fea291e574b26439c5c89012e41
- **coverage:** partial. README.md is fully translated into Japanese and Ukrainian, including current v0.0.2a3 material, SAIPEN work desk, P1/V4-01/V5-01 status, local alpha candidate, SAIRoute, documents, rules, authority chain, exact command/identifier/link/table structure, and required source-digest marker. English is the canonical source. Russian, Estonian, and Дед mirrors remain Core-owned. Missing producer-owned README locales: German, French, Spanish, Italian, Portuguese, Dutch, Polish, Swedish, Danish, Finnish, Norwegian, Chinese, Korean, Thai, Vietnamese, Arabic, Hebrew, Turkish, Hindi, Indonesian, Greek, Czech, Romanian, Hungarian, Bulgarian, Slovak, Croatian. A real second surface exists in `saimail/gui_app.py` and `saimail/gui_adapter.py`: concrete operator-visible labels, reasons, prompts, and status text are hard-coded. The repository has no shipped locale format, translator abstraction, or translation bundle for that surface, so TRANSLATE cannot invent or integrate one from this producer namespace.
- **payload:** .saipen/saitranslate/kitchen/README.ja.md, .saipen/saitranslate/kitchen/README.uk.md
- **verified:** PASS -- both README payloads rechecked by an independent producer run on 2026-09-25 with NO rebuild: the current source identity recomputed from the tree is byte-identical to the triple this package is bound to (source_head 3fa8f2295f564a6a75733905388ddee55b2f73b8, source_tree_fingerprint git-delta-v1:8b5376574aa5f803b4d48b6863a90b58aa658d9684c6b42332a8762015a5763f, role_revision sha256:7d18729f8d94eb58471ae3bb5fad9151e8499fea291e574b26439c5c89012e41), and both payloads carry the current canonical marker 4d4136e1e20cebce, re-derived with the recipe pinned in kitchen/_source_digest.py. Prior structural recheck stands: LF-only; 24 fence markers; 73 source links with identical ordered destinations and anchors plus the language-switcher link; 1 image; 53 table rows; 12 headings; executable command portions preserved; v0.0.2a3 and P1/V4-01/V5-01 material present. FAIL -- complete producer coverage is absent, so no READY machine package was published and this draft is not collectable.
- **instructions:** (1) keep this OUTBOX in `draft`; (2) decide and establish the GUI locale format outside the producer namespace before translating UI strings; (3) translate the 27 named README locales from current source; (4) return to a forced-fresh PREPARE run; (5) publish READY only after every real surface and every required locale are current.
- **details:** The previous producer claim that this project had no UI-string surface is false for the current tree. `gui_app.py` and `gui_adapter.py` prove a real user-facing GUI. The charter forbids inventing a locale format, and no current project-owned format exists. The two verified README translations remain useful producer work, but calling the package ready would violate the complete-surface rule.
  Payload correction, 2026-09-25: both payloads opened with the 4-line root release-mirror stub that current `README.md` does not contain, so each carried a second version badge the source never had. The stub is removed from both; the opening now matches the source exactly, badge count is 1 per payload, and both markers re-verify current.
  Marker restamp, 2026-09-25 (T-127): the canonical recipe stopped normalising only three numeric components, so a pre-release suffix bump moves the digest. Both markers were recomputed from current `README.md` under the corrected recipe, `4d4136e1e20cebce` to `feaa43e9b8d0f7bb`, one marker per file and no other byte touched. This is a restamp caused by a change in the digest DEFINITION, not by prose drift, and it is declared as such rather than presented as a fresh translation. `kitchen/_source_digest.py` now imports the recipe from `<saipen_home>/tools/freshness.py` instead of restating it, because two consecutive producer runs failed to reproduce their own marker by guessing it locally.
  Digest provenance, added 2026-09-25: `phases/translate.md` states the marker rule in prose ("normalizing every version string to literal VERSION"), and that prose admits several readings -- fifteen prose-literal readings were tried against the current README.md and none reproduced the marker, the same failure class this file's predecessor logged for its own marker. The executable form of the rule is `tools/validate.py` section 1b11: `sha256(re.sub(r"\d+\.\d+\.\d+", "VERSION", README.md.read_text(encoding="utf-8-sig")))`, written as the first 16 hex chars. That recipe is now pinned in `kitchen/_source_digest.py`, reproduces `4d4136e1e20cebce` exactly, and self-checks that the numeric components never move the digest.
  Two defects in that recipe are reported to Core because they live in the protocol home, outside this producer's write scope. First, the validator compares the marker's captured hex against the FULL 64-hex digest while `translate.md` mandates `<16 hex>`, so a conformant marker can never compare equal and the `translation-stale` warning can never be cleared. Second, the regex normalises three numeric components only, so a pre-release suffix bump (`0.0.2a3` to `0.0.2b1`) moves the digest -- precisely the badge-bump case the validator's own comment claims can never cause it.
