# Scheduler Service

Планировщик поливов и освещения с интеграцией через automation-engine REST API.

## Описание

Scheduler читает расписания из Laravel API `effective-targets` (GrowCycle) и публикует команды через automation-engine REST API.

## Функционал

- Чтение расписаний из `effective-targets.targets`:
  - `irrigation_schedule` / `irrigation`: расписание и параметры поливов
  - `lighting` (`photoperiod_hours`, `start_time`) и `lighting_schedule`: окно освещения (например, `"06:00-22:00"`)
- Публикация команд через automation-engine REST API
- Мониторинг безопасности насосов (защита от сухого хода)
- Проверка уровня воды перед поливом
- Расчет объема полива

## Архитектура команд

```
Scheduler → REST API (automation-engine:9405) → automation-engine → REST API (history-logger:9300) → history-logger → MQTT → Ноды
```

**Важно:** Scheduler **не публикует команды напрямую в MQTT**. Все команды проходят через automation-engine и history-logger.

## Метрики Prometheus

Метрики доступны на порту 9402 (`/metrics`):

- `schedule_executions_total{zone_id, task_type}` - выполненные расписания
- `active_schedules` - количество активных расписаний
- `scheduler_command_rest_errors_total{error_type}` - ошибки REST запросов к automation-engine

## Конфигурация

### Переменные окружения

- `AUTOMATION_ENGINE_URL` - URL automation-engine (по умолчанию: `http://automation-engine:9405`)
- `PG_HOST`, `PG_PORT`, `PG_DB`, `PG_USER`, `PG_PASS` - настройки PostgreSQL
- `MQTT_HOST`, `MQTT_PORT` - настройки MQTT (только для чтения статуса, опционально)

## Тестирование

```bash
pytest scheduler/test_main.py -v
```

**Покрытие:** 9 тестов, включая тесты REST интеграции.
