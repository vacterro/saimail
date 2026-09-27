# FG-06 — UTILITY, TOTAL_FRICTION AND LOCAL ENTRYPOINT v0

Status: working. Contract for `lab/utility_friction.py`,
`saimail_local.py`, `tools/fg05_local_scenario.py` and
`tests/test_utility_friction.py` / `tests/test_local_entrypoint.py` /
`tests/test_clean_install.py`.

## 1. What this gate is

An evidence and usability gate, not a redesign. It asks where the working local
protocol path saves work, where it adds work, which benefit comes from
selective resolution rather than compact syntax, what another user must do to
reproduce it, and what the protocol explicitly does not promise. It preserves
every prior negative measurement (T-9B, R1) and does not overwrite FG-05
evidence.

## 2. Comparison baseline and information equivalence

One deliberately simple baseline represents a receiver with **no
selective-resolution machinery**: it reads every discovered message fully. The
protocol side scans cheap clear headers and opens only the selected subset
(D-037). Both sides must surface the receiver-relevant payloads; the baseline
additionally reads the irrelevant ones, and that extra reading is the measured
cost of lacking a selector — not extra semantics attributed to SAIMAIL.

* `baseline_identity`: `EAGER_CANONICAL_READ_ALL_v1`
* `protocol_identity`: `SAIMAIL_PROGRESSIVE_RESOLUTION_v1`

Equivalence boundary, stated explicitly:

* both sides receive the identical transport objects, so the durable-write term
  is identical and cancels in the ratio;
* both sides carry the same claim/evidence/uncertainty semantics; the baseline
  does not carry provenance fields the compared stage omits;
* only the message-reading terms differ, and they differ because the baseline
  cannot filter;
* no model-driven baseline is used; the model-based prose ambiguity branch is
  reported `NOT_MEASURED`.

## 3. Workloads

Five deterministic, frozen fixtures (built from exact plan strings, identified
by a SHA-256 over their content):

| id | shape |
|---|---|
| `A_LOW_OPEN_RATE` | 5% receiver-relevant |
| `B_MODERATE_OPEN_RATE` | 20% receiver-relevant |
| `C_HIGH_OPEN_RATE` | 65% receiver-relevant |
| `D_FALLBACK_HEAVY` | unknown topics force DEFER opens; 0% safely ignorable at R1 |
| `E_ERROR_RECOVERY` | reuses the FG-05 injected-failure scenario unchanged |

Fixtures are frozen before measurement and cannot be tuned after a result is
seen. Token cost is integrated from T-9B, never re-measured.

## 4. TOTAL_FRICTION model

Raw components are always reported. A normalized scalar is produced only under
the code-frozen `TOTAL_FRICTION_FRICTION_UNITS_v1` model, with every weight
declared before measurement: one friction unit per header scan; eight per full
read; four per durable write; one hundred per promotion/attention decision; and
one unit per 1000 modeled triage-prose tokens. The token normalization uses the
T-9B ratios (`frame/prose 1.16`, `record/prose 1.67`, `cl100k_base`) as prior
evidence. The scalar is a model, labelled as such, and never replaces the raw
vector.

Measured or explicitly classified components: `discovery_cost`,
`schema_overhead` (T-9B token overhead plus per-message parse counts),
`generation_cost`/`review_cost` (N/A — no model on the base path),
`open_cost` (counts and latency), `error_handling_cost`/`recovery_cost` (FG-05),
`human_attention_cost`, plus `token_cost`, `transport_bits`, `ambiguity_cost`,
`decode_latency`, `error_probability`.

## 5. Honest outcome categories

`UTILITY_POSITIVE`, `UTILITY_CONDITIONAL`, `UTILITY_NEUTRAL`,
`UTILITY_NEGATIVE`, `INSUFFICIENT_EVIDENCE`. The category is workload-specific;
a missed mandatory open or false ignore dominates and yields `NEGATIVE`. False
ignore and false open are reported separately and never summed — no exchange
rate is invented. The measured result is `UTILITY_CONDITIONAL`: a real cost win
at low open rate, neutral at moderate/high and fallback-heavy, with the source
identified as selective resolution plus the zero-inference header scan.

## 6. Local entrypoint

One installable command, no framework/GUI/daemon/web service/plugin
system/model/hardware dependency:

```
saimail-local --help
saimail-local --version
saimail-local                 # FG-05 end-to-end demo
saimail-local --utility       # FG-06 TOTAL_FRICTION benchmark
saimail-local --api-map       # path to the machine-readable stable API map
```

`--out DIR` writes the bounded machine-readable result and a summary; `--keep`
retains the temporary workspace; `--json` prints the result. The repository
shim `python tools/fg05_local_scenario.py` delegates to the same
`saimail_local.main` — one runner, not two. `LOCAL_SCENARIO_RESULT_1` and its
FG-05 semantics are unchanged; FG-06 adds a separate `FG06_UTILITY_RESULT_1`.

## 7. Clean install and package content

The wheel ships `sailang`, `saimail`, the bounded `lab` engine
(`local_scenario`, `utility_friction`, `stable_local_api.json`) and the
`saimail_local` entrypoint. Lab out/analysis/history artifacts and registration
JSON are not package data and do not ship. Install:

```
pip install "saimail[crypto]"          # runtime crypto extra for the demo
saimail-local --version
```

`tests/test_clean_install.py` builds the wheel, installs it `--no-deps` into a
fresh `--system-site-packages` venv, runs the entrypoint from a directory that
is not the checkout, and proves the modules resolve inside the venv.

## 8. Stable API, type and failure maps

`lab/stable_local_api.json` (`SAIMAIL_STABLE_LOCAL_API_1`) is the
machine-readable map: module, symbol, kind, purpose, inputs, outputs, related
codes and stability. It covers record creation/parsing, envelope
seal/verify/open, Post Office delivery/scan/open/recovery/expiry, promotion
proposal, LEGACY adoption/recovery/successor context, HUMAN_PRIVATE
seal/store/list/open and attention admission/reserve/ack/budget. The principal
crossing types are `Record`, `Header`, `VerifiedEnvelope`, `OpenedEnvelope`,
`DeliveryResult`, `ScanResult`/`ScanCursor`, `SweepResult`, `LegacyPacket`/
`AuthenticatedLegacy`/`LegacyEntry`, `HumanPrivateLetter`/`HumanPrivateListing`/
`OpenedHumanPrivateLetter`, `AttentionCandidate`/`Reservation`/`AckResult` and
`BudgetState`. The failure map groups externally meaningful codes by category
with `retry_safe`, `operator_action` and `authority_intact` flags. LAB-only
symbols are marked `lab-only` and carry no long-term compatibility promise.

## 9. Limitations and what SAIMAIL does not promise

Limitations: token cost is integrated from T-9B, not re-measured; the
model-based prose ambiguity branch is `NOT_MEASURED`; generation/review cost is
N/A on the base path; microbenchmark latency is machine-local and not portable;
false ignore and false open are never summed; the friction scalar is a declared
model, not physical truth.

SAIMAIL does **not** promise automatic truth detection, semantic reviewer
reliability, guaranteed provider JSON Schema enforcement, automatic personal
correspondence, automatic memory promotion, production Gmail/Slack/Outlook
integration, hardware-key provisioning, zero-cost protocol overhead, global
utility independent of workload, or live multi-user service readiness.
