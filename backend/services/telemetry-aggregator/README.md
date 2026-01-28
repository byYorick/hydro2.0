# Telemetry Aggregator

Сервис для агрегации телеметрии в таблицы `telemetry_agg_1m`, `telemetry_agg_1h`, `telemetry_daily`.

## Описание

Сервис периодически (по умолчанию каждые 5 минут) агрегирует данные из `telemetry_samples`
с джоином на `sensors` для получения `node_id` и `metric_type` (`sensors.type`).
Канал берется из `telemetry_samples.metadata->>'channel'` (при наличии).

1. **telemetry_agg_1m** - агрегация по 1 минуте (из `telemetry_samples`)
2. **telemetry_agg_1h** - агрегация по 1 часу (из `telemetry_agg_1m`)
3. **telemetry_daily** - агрегация по дням (из `telemetry_agg_1h`)

## Использование

Сервис запускается автоматически в Docker Compose и работает в фоне.

## Конфигурация

- `AGGREGATION_INTERVAL_SECONDS` - интервал запуска агрегации (по умолчанию 300 секунд = 5 минут)
- `CLEANUP_INTERVAL_SECONDS` - интервал запуска очистки старых данных (по умолчанию 86400 секунд = 24 часа)
- `RETENTION_SAMPLES_DAYS` - retention для telemetry_samples (по умолчанию 90 дней)
- `RETENTION_1M_DAYS` - retention для telemetry_agg_1m (по умолчанию 30 дней)
- `RETENTION_1H_DAYS` - retention для telemetry_agg_1h (по умолчанию 365 дней)

## Retention Policy

Сервис автоматически удаляет старые данные согласно retention policy:

- **telemetry_samples**: 90 дней (raw данные хранятся 3 месяца)
- **telemetry_agg_1m**: 30 дней (минутные агрегаты хранятся 1 месяц)
- **telemetry_agg_1h**: 365 дней (часовые агрегаты хранятся 1 год)
- **telemetry_daily**: бессрочно (дневные агрегаты хранятся всегда)

Очистка запускается автоматически раз в день (настраивается через `CLEANUP_INTERVAL_SECONDS`).

## Метрики Prometheus

- `aggregation_runs_total` - количество запусков агрегации (по типам: 1m, 1h, daily)
- `aggregation_records_total` - количество созданных записей (по типам)
- `aggregation_seconds` - длительность агрегации (по типам)
- `aggregation_errors_total` - количество ошибок (по типам)
- `cleanup_runs_total` - количество запусков очистки
- `cleanup_deleted_total` - количество удаленных записей (по таблицам)
- `cleanup_seconds` - длительность очистки

Порт: `9404`

## Таблицы

### aggregator_state

Хранит состояние агрегации:
- `aggregation_type` - тип агрегации ('1m', '1h', 'daily')
- `last_ts` - последняя обработанная временная метка
- `updated_at` - время последнего обновления

