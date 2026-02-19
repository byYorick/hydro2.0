# AE2 S12 Gate Summary

- Generated-At: 2026-02-19T05:46:42.464973+00:00
- Mode: remote
- Baseline: `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv`
- Decision: `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_RELEASE_DECISION.txt`
- Result: `decision=ALLOW_FULL_ROLLOUT`

| endpoint | count | p50_ms | p95_ms | p99_ms | max_ms |
|---|---:|---:|---:|---:|---:|
| cutover_state | 240 | 11.74 | 13.97 | 14.99 | 15.26 |
| integration_contracts | 240 | 12.18 | 33.54 | 34.19 | 34.40 |
| observability_contracts | 240 | 12.77 | 15.19 | 15.59 | 15.77 |
| bootstrap_heartbeat | 240 | 49.10 | 186.83 | 196.83 | 198.56 |

