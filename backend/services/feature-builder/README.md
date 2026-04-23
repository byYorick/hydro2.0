# feature-builder

ML Phase 2 skeleton — единственный writer в ML-витрины `zone_features_5m`,
`ml_labels`, `dose_response_events`, а также автор записей в
`ml_data_quality_windows`.

## Текущий статус

**Phase 2A (этот коммит):** скелет. `/healthz`, `/readyz`, `/metrics`, poll-loop
с заглушкой (`_poll_once` — no-op).

**Phase 3 (следующий):** реальная сборка витрин из `telemetry_agg_1m` +
`commands` + `grow_cycles`, правила качества, ground-truth backfill для
`ml_predictions` (когда тот появится).

## Конфигурация (env)

| Переменная | По умолчанию | Смысл |
|---|---|---|
| `FEATURE_BUILDER_POLL_INTERVAL_SEC` | `60` | Частота poll-loop |
| `FEATURE_BUILDER_LOOKBACK_HOURS` | `24` | Окно инкрементального догона |
| `FEATURE_BUILDER_HORIZONS` | `5,15,60` | Горизонты `ml_labels` в минутах |
| `FEATURE_BUILDER_MIN_VALID_RATIO` | `0.7` | Порог для пометки окна `low_quality` |
| `FEATURE_BUILDER_SCHEMA_VERSION` | `1` | Текущая версия фичей |
| `FEATURE_BUILDER_PORT` | `9410` | HTTP-порт |
| `PG_*` | db/5432/hydro | Как у всех Python-сервисов |

## Эндпоинты

- `GET /healthz` — структурная проверка (ML-витрины существуют + БД доступна)
- `GET /readyz` — то же, для K8s readiness probe
- `GET /metrics` — Prometheus

## Метрики

```
feature_builder_rows_written_total{table=...}
feature_builder_errors_total{stage=...}
feature_builder_lag_seconds{pipeline=...}
feature_builder_poll_runs_total
```

## Ссылки

- Спецификация: `doc_ai/09_AI_AND_DIGITAL_TWIN/ML_FEATURE_PIPELINE.md` §6
- Приложение C (решения и корректировки): тот же файл
