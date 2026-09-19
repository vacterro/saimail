# T-15 — R1 representation shootout

**Verdict: KEEP_CUSTOM_WIRE**

Pre-registered criteria, declared in `bench/r1_shootout.py` before measurement:

> Correctness gates first, and they disqualify: a codec must round-trip every fixture to an identical TriageView, refuse every malformed input, refuse an unknown field, and refuse a container whose profile differs. A codec that fails any of those is out regardless of its numbers. Among the survivors: KEEP_CUSTOM_WIRE only if the SAILANG wire is at most 0.85x the bytes of the best standard codec AND at most 1.25x its decode latency AND at most 1.50x its code surface. Otherwise DROP_CUSTOM_WIRE while keeping the semantic schema. REDESIGN_R1 if no codec passes the correctness gates.

Corpus: 45 records, identical R1 semantics in every codec.

## Correctness gates

| codec | round-trip view | malformed refused | unknown field | wrong profile | passes |
|---|---|---|---|---|---|
| A_sailang_wire | True | True | `BAD_FRAME` | `PROFILE_MISMATCH` | **True** |
| B_compact_json | True | True | `UNKNOWN_FIELD` | `PROFILE_MISMATCH` | **True** |
| C_typed_kv | True | True | `UNKNOWN_FIELD` | `PROFILE_MISMATCH` | **True** |

## Cost

| codec | body bytes | bytes/frame | header | encode ns | decode ns | encode peak B | decode peak B | statements |
|---|---|---|---|---|---|---|---|---|
| A_sailang_wire | 1538 | 34.2 | 84 | 236800 | 217885 | 11017 | 32896 | 29 |
| B_compact_json | 3303 | 73.4 | 86 | 404630 | 391290 | 13830 | 33178 | 39 |
| C_typed_kv | 2123 | 47.2 | 78 | 308765 | 368455 | 13941 | 32697 | 41 |

## Secondary diagnostic — tokens

R1 is not meant to enter model context during ordinary scanning, so this
ranks below every column above.

| codec | cl100k_base | o200k_base | p50k_base | gpt2 |
|---|---|---|---|---|
| A_sailang_wire | 911 | 893 | 1037 | 1037 |
| B_compact_json | 1545 | 1536 | 1678 | 1678 |
| C_typed_kv | 1327 | 1304 | 1538 | 1538 |

## Reasoning

- custom/best-standard bytes 0.724 (needs <= 0.85)
- custom/best-standard decode latency 0.591 (needs <= 1.25)
- custom/best-standard code surface 0.744 (needs <= 1.5)

## Caveat

Latency is wall-clock on one machine and one interpreter; it ranks codecs against each other on the same run, and is not an absolute figure. Token counts are a secondary diagnostic: R1 is not meant to enter model context during ordinary scanning.

