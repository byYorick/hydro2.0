# Telemetry Aggregator

Сервис для агрегации телеметрии в таблицы `telemetry_agg_1m`, `telemetry_agg_1h`, `telemetry_daily`.

## Описание

Сервис периодически (по умолчанию каждые 5 минут) агрегирует данные из `telemetry_samples`:

1. **telemetry_agg_1m** - агрегация по 1 минуте (из `telemetry_samples`)
2. **telemetry_agg_1h** - агрегация по 1 часу (из `telemetry_agg_1m`)
3. **telemetry_daily** - агрегация по дням (из `telemetry_agg_1h`)

## Использование

Сервис запускается автоматически в Docker Compose и работает в фоне.

## Конфигурация

- `AGGREGATION_INTERVAL_SECONDS` - интервал запуска агрегации (по умолчанию 300 секунд = 5 минут)

## Метрики Prometheus

- `aggregation_runs_total` - количество запусков агрегации
- `aggregation_records_total` - количество созданных записей
- `aggregation_seconds` - длительность агрегации
- `aggregation_errors_total` - количество ошибок

Порт: `9404`

## Таблицы

### aggregator_state

Хранит состояние агрегации:
- `aggregation_type` - тип агрегации ('1m', '1h', 'daily')
- `last_ts` - последняя обработанная временная метка
- `updated_at` - время последнего обновления


