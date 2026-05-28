# LOGGING_AND_MONITORING.md
# Система логирования и мониторинга 2.0

Документ описывает, как система 2.0 должна собирать логи, метрики и алерты.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 1. Цели

- видеть текущее состояние сервисов и узлов;
- быстро находить причины ошибок;
- получать уведомления о критических событиях;
- иметь историю для анализа и улучшений.

---

## 2. Компоненты Observability

1. **Логи приложений** (Python-сервис, Laravel).
2. **Метрики сервисов** (CPU, RAM, количество сообщений MQTT и т.п.).
3. **Метрики домена** (количество алертов, успешных команд и т.п.).
4. **Алертинг** (e-mail, Telegram).

---

## 3. Логи

Каждый сервис пишет структурированные логи (JSON):

```json
{
 "ts": "2025-11-15T10:00:00Z",
 "service": "automation-engine",
 "level": "INFO",
 "zone_id": 2,
 "node_id": 11,
 "event": "COMMAND_SENT",
 "details": {
 "command_type": "dose",
 "channel": "pump_acid",
 "ml": 1.0
 }
}
```

Требования:

- уровни: DEBUG, INFO, WARNING, ERROR, CRITICAL;
- наличие минимальных полей: `ts`, `service`, `level`, `event`;
- отсутствие чувствительных данных в логах (пароли, токены).

---

## 4. Метрики

Сервисы публикуют метрики в систему мониторинга (Prometheus/иное):

- системные:
 - загрузка CPU;
 - использование памяти;
 - количество активных подключений к БД;
- доменные:
 - количество алертов по зонам;
 - количество команд в минуту;
 - количество сообщений MQTT в минуту.

Графики строятся в Grafana.

---

## 4.1. Мониторинг history-logger

### Статус сервиса

**Видимость статуса:**
- **Health endpoint**: `GET /health` — проверка доступности сервиса
- **Метрика**: `telemetry_queue_size` (Gauge) — текущий размер очереди Redis
- **Метрика**: `telemetry_queue_age_seconds` (Gauge) — возраст самого старого элемента в очереди

**Критические индикаторы:**
- Если `telemetry_queue_size > 10000` — очередь переполняется, требуется вмешательство
- Если `telemetry_queue_age_seconds > 300` — элементы задерживаются в очереди более 5 минут
- Если `telemetry_dropped_total > 0` — сообщения теряются

### Прогресс на уровне этапов

**Этапы обработки телеметрии:**
1. **Прием из MQTT** → `telemetry_received_total` (Counter)
2. **Добавление в очередь Redis** → `redis_operation_duration_seconds` (Histogram)
3. **Обработка батча** → `telemetry_processed_total` (Counter), `telemetry_batch_size` (Histogram)
4. **Запись в БД** → `telemetry_processing_duration_seconds` (Histogram), `database_errors_total` (Counter)

**Метрики прогресса:**
- `telemetry_received_total` — общее количество полученных сообщений
- `telemetry_processed_total` — общее количество обработанных сообщений
- Соотношение `telemetry_processed_total / telemetry_received_total` должно быть близко к 1.0
- `telemetry_batch_size` — размер батчей (целевое значение: 50-200 элементов)
- `node_event_unknown_total` — количество node event, которые не попали в whitelist и агрегированы как `OTHER`

### Выделенные представления мониторинга

**Grafana Dashboard: "History Logger Service"**

1. **Обзор сервиса:**
   - Статус сервиса (health check)
   - Размер очереди Redis (`telemetry_queue_size`)
   - Возраст элементов в очереди (`telemetry_queue_age_seconds`)
   - Скорость обработки (сообщений/сек)

2. **Поток телеметрии:**
   - График `telemetry_received_total` (rate)
   - График `telemetry_processed_total` (rate)
   - Разница между полученными и обработанными (показывает потери)
   - Размер батчей (`telemetry_batch_size`)

3. **Производительность:**
   - Время обработки батча (`telemetry_processing_duration_seconds`)
   - Время операций Redis (`redis_operation_duration_seconds`)
   - Время запросов к Laravel API (`laravel_api_request_duration_seconds`)

4. **Ошибки и потери:**
   - `telemetry_dropped_total` по причинам (validation_failed, queue_push_failed, missing_metric_type)
   - `database_errors_total` по типам ошибок
   - `node_hello_errors_total` по типам ошибок
   - `rate(node_event_unknown_total[5m])` — тренд unknown node events (контроль деградации `event_code` контракта)

5. **Регистрация узлов:**
   - `node_hello_received_total` — получено сообщений node_hello
   - `node_hello_registered_total` — успешно зарегистрировано узлов
   - `node_hello_errors_total` — ошибки регистрации

6. **Heartbeat:**
   - `heartbeat_received_total` по узлам — активность узлов

**Алерты:**
- `telemetry_queue_size > 10000` — очередь переполняется
- `telemetry_dropped_total{reason="queue_push_failed"} > 10` — критические потери данных
- `database_errors_total > 5` за 5 минут — проблемы с БД
- `telemetry_processing_duration_seconds > 5` — медленная обработка
- `rate(node_event_unknown_total[5m]) > 0.05` в течение 10 минут — деградация контракта `event_code` между нодой и backend

---

## 4.2. Мониторинг automation-engine (AE3)

### Статус сервиса

**Видимость статуса:**
- **Prometheus endpoint:** `http://automation-engine:9405/metrics/` (mount на ту же FastAPI app, не отдельный порт; путь с trailing slash);
- **Health:** `GET http://automation-engine:9405/health/live` и `/health/ready`.

> **Note:** Историческое именование метрик AE2 (`zone_checks_total`, `automation_commands_sent_total`, `config_fetch_*`, `automation_loop_errors_total`, `mqtt_publish_errors_total`) **deprecated и не существует** в AE3 runtime. Реальные канонические метрики AE3 — ниже.

### Канонические метрики AE3 (`backend/services/automation-engine/ae3lite/infrastructure/metrics.py`)

**Intent lifecycle:**
- `ae3_intent_claimed_total{source_status}` — claim intent из `zone_automation_intents`
- `ae3_intent_terminal_total{status}` — terminal lifecycle intent (completed/failed/cancelled)
- `ae3_intent_stale_reclaimed_total` — re-claim просроченного `claimed` intent

**Команды:**
- `ae3_command_dispatched_total` — публикация команды через history-logger
- `ae3_command_dispatch_duration_seconds` — длительность publish call
- `ae3_command_terminal_total{status}` — terminal статус для AE3-команды
- `ae3_command_send_retry_total{reason}` — transient retry HL publish

**Task / workflow:**
- `ae3_tick_duration_seconds` — длительность `Ae3RuntimeWorker` drain tick
- `ae3_fail_safe_transition_total{topology, stage, reason, source}` — fail-closed terminal в two-tank workflow
- `ae3_emergency_stop_reconcile_total{topology, stage, outcome}` — E-stop reconcile
- `ae3_node_runtime_event_kick_total{event_type, channel}` — wake-up по `ae_zone_event` NOTIFY
- `ae3_config_hot_reload_total{result}` — hot-reload runtime config (`config_mode=live`)
- `ae3_irrigation_wait_ready_*` — `await_ready` stage metrics
- `ae3_start_irrigation_blocked_total{reason}` — ingress guard `start-irrigation` (например, `setup_pending`)

**Snapshot / retry:**
- `infra_ae3_snapshot_retry_scheduled_total` — запланированный retry при transient snapshot gap
- `ae3_snapshot_retry_exhausted_total` — исчерпание retry budget

**Greenhouse climate (отдельный runtime):**
- `greenhouse_climate_*` метрики (см. `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`)

**Health:** `ae3_health_live`, `ae3_health_ready` (gauge 0/1).

### Прогресс на уровне этапов (AE3 task lifecycle)

1. **Claim intent** → `ae3_intent_claimed_total`
2. **Snapshot load** → `infra_ae3_snapshot_retry_scheduled_total` при transient gap, иначе success
3. **Task creation** → `ae_tasks` insert + partial unique index `ae_tasks_active_zone_unique`
4. **Stage execution** → `ae3_tick_duration_seconds`; per-stage transitions в `ae_stage_transitions`
5. **Command publish** → `ae3_command_dispatched_total` + duration histogram
6. **Wait terminal** → polling `recover_waiting_command`; на terminal — `ae3_command_terminal_total`
7. **Stage advance / requeue** → `update_stage` (атомарно `claimed/running/waiting_command → pending`)
8. **Terminal task** → `ae3_intent_terminal_total{status}`

### Метрики Laravel scheduler-dispatch

Параллельный набор от Laravel-stack (см. `backend/laravel/app/Services/AutomationScheduler/`):

- `laravel_scheduler_dispatches_total{zone_id, task_type, result}` — Counter dispatch результатов
- `laravel_scheduler_cycle_duration_seconds{dispatch_mode}` — Histogram длительности cycle
- `laravel_scheduler_active_tasks{status}` — Gauge активных tasks (cursor + active_tasks таблицы)

Источник: персистентные таблицы `laravel_scheduler_dispatch_metric_totals`, `laravel_scheduler_cycle_duration_aggregates`, `laravel_scheduler_cycle_duration_bucket_counts`. Exporter: `App\Services\AutomationScheduler\SchedulerPrometheusMetricsExporter` → `GET /api/system/scheduler/metrics` (Prometheus text format).

### Выделенные представления мониторинга

**Grafana Dashboard: "Automation Engine Service"**

1. **Обзор сервиса:**
   - Статус сервиса (доступность метрик)
   - Количество активных зон
   - Скорость обработки зон (зон/минуту)
   - Время последней успешной проверки

2. **Обработка зон:**
   - График `zone_checks_total` (rate) — частота проверок
   - График `zone_check_seconds` (p50, p95, p99) — время обработки
   - График `automation_commands_sent_total` по зонам — активность по зонам
   - График `automation_commands_sent_total` по метрикам — типы команд

3. **Конфигурация:**
   - `config_fetch_success_total` — успешные загрузки конфигурации
   - `config_fetch_errors_total` по типам ошибок — проблемы с конфигурацией
   - Время между загрузками конфигурации

4. **Команды и публикация:**
   - `automation_commands_sent_total` по зонам — распределение команд
   - `automation_commands_sent_total` по метрикам (pH, EC, irrigation, climate, light)
   - `mqtt_publish_errors_total` по типам ошибок — проблемы с MQTT

5. **Ошибки:**
   - `automation_loop_errors_total` по типам ошибок — ошибки в цикле
   - `error_handler_errors_total` по зонам (из error_handler.py) — общие ошибки обработки
   - График ошибок во времени

6. **Производительность:**
   - Время обработки зон (`zone_check_seconds`)
   - Параллелизм обработки (количество зон, обрабатываемых одновременно)
   - Задержка между циклами обработки

**Алерты (AE3-каноничные):**
- `rate(ae3_intent_terminal_total{status="failed"}[5m]) > 0.1` — рост частоты failed intents
- `histogram_quantile(0.99, rate(ae3_tick_duration_seconds_bucket[5m])) > 30` — медленная обработка drain loop
- `rate(ae3_command_send_retry_total[10m]) > 0` — transient retries publish команд
- `rate(ae3_fail_safe_transition_total[15m]) > 0` — fail-closed переходы в workflow
- Отсутствие `ae3_intent_claimed_total` или `ae3_tick_duration_seconds_count` в течение 5 минут — AE3 worker не работает
- `ae3_health_live == 0` или `ae3_health_ready == 0` — degraded health

**Дополнительные метрики для мониторинга:**
- Количество зон в статусе "требует корректировки"
- Количество зон с активными алертами
- Health score зон (если используется health_monitor.py)
- Стабильность pH/EC по зонам

---

## 5. Алертинг

Примеры алертов:

- недоступен брокер MQTT;
- Python-сервис не пишет телеметрию > N минут;
- количество ошибок команды OTA выше порога;
- слишком много алертов по одной зоне.

Алерты могут отправляться в:

- e-mail;
- Telegram-чат;
- панель UI.

---

## 6. Доступ к мониторингу для пользователей

### Быстрый доступ

**Grafana Dashboard:**
- **URL:** `http://localhost:3000` (или IP вашего сервера)
- **Логин (dev):** `admin` / **Пароль:** `admin`
- **Логин (prod):** `admin` / **Пароль:** из переменной `GRAFANA_ADMIN_PASSWORD`

**Prometheus UI:**
- **URL:** `http://localhost:9090`
- Прямой доступ к метрикам и алертам

**Доступные Dashboards:**
1. **History Logger Service** - мониторинг сервиса записи телеметрии
2. **Automation Engine Service** - мониторинг системы автоматизации зон
3. **System Overview** - общий обзор системы
4. **Alerts Dashboard** - активные алерты

### Подробное руководство

Полное руководство пользователя доступно в: `../08_SECURITY_AND_OPS/MONITORING_USER_GUIDE.md`

---

## 7. Правила для ИИ-агентов

1. Не удалять существующие логи и метрики без замены.
2. При добавлении новой важной логики — добавить логирование ключевых событий.
3. Не логировать секретные данные.

Наблюдаемость — это «глаза и уши» системы. Без неё любое сложное поведение превращается в «чёрный ящик».
