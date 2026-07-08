# AUDIT_2026_07_07_RELIABILITY_PLAN.md
# Аудит пайплайна «ноды → автоматика» и план повышения надёжности, стабильности и наблюдаемости

**Дата:** 2026-07-07
**Версия:** 1.0
**Скоуп аудита:** весь пайплайн `ESP32 → MQTT → history-logger → PostgreSQL → Laravel scheduler → AE3 → history-logger → MQTT → ESP32` + инфраструктура (Docker/Mosquitto/Prometheus/Alertmanager/Grafana/backup).
**Объём находок:** ~120 (13 critical, ~35 high, ~45 medium, остальное low/informational).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

> Этот план — продолжение `AUDIT_2026_05_28_BUGFIX_PLAN.md` (security fast-track закрыт).
> Фокус текущего плана: **тихие падения, потеря данных, застревания задач, fail-safe и observability-пробелы**.

---

## Статус выполнения (2026-07-07)

| Этап | Статус | Примечание |
|------|--------|------------|
| **R1** | ✅ | Alertmanager bearer, prod healthchecks, exporters |
| **R2** | ✅ | 60 alert rules (dev+prod), метрики в коде |
| **R3** | ✅ | processing-list, PUBACK, shutdown drain; HL 527 passed |
| **R4** | ✅ | lease fail-closed, waiting_command janitor, HL retry=1; AE 1668+ passed |
| **R5** | ✅ | link-loss fail-safe, честная телеметрия; 6 нод собраны |
| **R6** | ✅ | window_interval, missed ticks, fail-closed token; Laravel 1126 passed |
| **R7** | ✅ | `/backups` volume, check-скрипты, backup onFailure |

**Отклонения / осознанные компромиссы:**
- R5 HMAC canonical `cJSON_Print` — heap на однопоточном mqtt path (приемлемо для v1)
- Replay пропущенных interval-окон — только метрика + лог, без автоматического replay (по дизайну)

**Закрыто в финальной итерации (2026-07-07):**
- Prometheus exporter: `laravel_scheduler_missed_windows_total`, `laravel_scheduler_lock_skipped_total`
- Workspace `missed_total` / `suppressed_total` из `scheduler_logs` + totals fallback
- HL chaos-сценарий PG down → requeue → recovery (`test_reliability_r3.py`)
- Vitest: мок `automationStateBootstrap` в AutomationProcessPanel / ZoneShow / ZoneAutomationTab

---

## Статус повторного аудита (2026-07-08)

Повторная проверка закрыла оставшиеся пробелы из §Definition of Done и R6.4/R7:

| Область | Закрыто |
|---------|---------|
| **R7.2 SPOF** | `08_SECURITY_AND_OPS/SINGLE_INSTANCE_SPOF_RUNBOOK.md` — SPOF-карта, recovery, retention/env |
| **R7.3 mqtt-bridge** | `POST /bridge/zones/{id}/commands` → HTTP 410 (только HL публикует команды) |
| **R6.4 / R7 retention** | `TELEMETRY_RETENTION_DAYS` и `RETENTION_SAMPLES_DAYS` синхронизированы на **30** в docker-compose |
| **AE3 recovery** | foreign lease skip; `waiting_command` poll-deadline reconcile (W5); legacy `ACCEPTED` → `command_protocol_violation` + unit-тест |
| **HL telemetry** | processing-list reclaim, `telemetry_dead_cli.py`, метрики phantom/drop |
| **Тесты** | дубликат `test_waiting_command_reconcile_poll_deadline_fails_stale_task` удалён |

**Остаётся осознанным компромиссом (без изменений):** interval replay только метрика+лог; R5 HMAC heap на mqtt path; HA вне скоупа v1.

---

## 1. Резюме аудита

### Что уже сделано хорошо (не трогаем)

| Слой | Сильные стороны |
|------|----------------|
| **Firmware** | LWT retain, HMAC canonical JSON + idempotency LRU, time-sync gate на телеметрию, I2C mutex, NVS verify-after-write, TWDT, diagnostics/heartbeat |
| **history-logger** | Idempotency команд по `cmd_id`, HMAC + ts-skew валидация, retry+DLQ для command status → Laravel, drain stale QUEUED после рестарта, метрики drop reasons |
| **AE3-Lite** | Drain supervisor, command idempotency (`planner_step`, `published_unconfirmed` redrive), startup recovery с fail-closed на прерванной коррекции, flow-path guard с critical alerts, multi-check readiness |
| **Laravel scheduler** | Cache-lock + `withoutOverlapping` + `onOneServer`, intent retry chain (max 3), watchdog `ae3:reap-stale-tasks`, Prometheus exporter + 6 alert rules |
| **Инфраструктура** | 37 alert rules в dev, healthchecks python-сервисов, supervisord autorestart, TimescaleDB retention/compression, backup-скрипты |

### Топ-13 critical находок (сквозной список)

| # | Слой | Находка | Где |
|---|------|---------|-----|
| K1 | Firmware | При потере MQTT/WiFi актуаторы **не останавливаются**; latched pumps (`auto_stop_enabled=false`) работают бесконечно | `ph_node_init.c:102-115`, `pump_node_init.c:126-147`, `pump_driver.c:673-693` |
| K2 | Firmware | `allow_legacy_hmac` — команды без HMAC и timestamp check | `node_command_handler.c:1065-1071` |
| K3 | HL | Redis pop телеметрии **без ACK/transaction**: ошибка после LPOP или при десериализации = безвозвратная потеря батча | `common/redis_queue.py:257-275` |
| K4 | HL | Ошибка записи в PG (FK violation, insert fail) после pop — батч **не возвращается** в очередь | `telemetry_processing.py:1297,1583-1601` |
| K5 | HL | `delivery_result.dropped=True` — статус команды не доставлен в Laravel, нет paging | `handlers/command_response.py:296-308`, `command_status_queue.py:969-977` |
| K6 | AE3 | Ошибки heartbeat lease только логируются; задача продолжает работать **без валидного lease** (split-brain risk) | `runtime/worker.py:740-747` |
| K7 | AE3 | `waiting_command` не сканируется stale janitor — вечное зависание при мёртвом reconcile | `automation_task_repository.py:224-264`, `stale_task_reconcile.py:40-159` |
| K8 | Laravel | `window_interval`: план в UI показывает тики внутри окна, orchestrator диспатчит только на границах окна — **ложные ожидания полива** | `ScheduleWorkspaceService.php:307-338` vs `SchedulerCycleOrchestrator.php:506-528` |
| K9 | Infra | Prod compose: `depends_on` без `condition: service_healthy`; mqtt/db/redis без healthcheck | `docker-compose.prod.yml:2-70,201-235` |
| K10 | Infra | `backup:full` пишет в `/backups`, но volume **не смонтирован** ни в dev, ни в prod | `routes/console.php:39-45`, `docker-compose.prod.yml:445-455` |
| K11 | Infra | Alertmanager webhook → Laravel без bearer token; в prod middleware требует secret → алерты **не доставляются** (401/500); SMTP/Telegram — placeholders | `configs/prod/alertmanager/config.yml:4-48`, `VerifyAlertmanagerWebhook.php:38-64` |
| K12 | AE3/Laravel | HL retry policy: `AE_HL_MAX_RETRIES=2` (3 попытки) нарушает контракт «max 1 transient retry» из `ARCHITECTURE_FLOWS.md` §2 | `runtime/env.py:119` |
| K13 | HL | MQTT publish команд проверяет `rc==0`, но не ждёт PUBACK (`wait_for_publish`) — «SENT» без гарантии доставки на брокер | `command_service.py:247-257` |

### Карта «тихих падений» по пайплайну

```
ESP32 ──── telemetry ────► Mosquitto ────► HL ingress ────► Redis ────► PG
  │                                          │                │          │
  │ NaN дропается молча                      │ invalid JSON   │ pop без  │ FK/insert fail
  │ (climate temp/hum);                      │ без метрики    │ ACK      │ без requeue
  │ фиктивный pH 6.5 / EC 1.2 stub           │                │ drop 20-50% при >95%
  │ невалидная команда — нет response        │                │
  ▼                                          ▼                ▼
Laravel scheduler ──► intent pending ──► AE3 worker ──► HL /commands ──► MQTT
  │                     │                  │                 │
  │ нет токена = exit 0 │ orphan до 900s   │ lease heartbeat │ нет PUBACK-wait;
  │ interval без        │ без alert        │ fail игнорится; │ статус в Laravel
  │ catch-up;           │                  │ intent sync     │ может drop в DLQ
  │ lock-skip = SUCCESS │                  │ только warning  │ без paging
```

---

## 2. План доработки

### Принципы

1. **Поэтапная доставка**, каждый этап — независимый merge с зелёным suite (`make test`, `make test-ae`, HL/bridge pytest, protocol-check при затрагивании контрактов).
2. **Никаких breaking changes** в защищённом пайплайне; все правки аддитивны, поведенческие изменения fail-safe направления (fail-closed).
3. **Сначала наблюдаемость, потом поведение**: этапы R1–R2 дают видимость проблем, чтобы верифицировать эффекты R3–R6.
4. Formats: `fix(<scope>): ...` / `feat(<scope>): ...`; строка `Compatible-With` в PR при затрагивании контрактов.

### Карта этапов

| Этап | Тема | Слой | Срочность | Риск регрессии |
|------|------|------|-----------|----------------|
| **R1** | Доставка алертов + prod-инфраструктура | Infra | **CRITICAL** | низкий |
| **R2** | Observability-пробелы (метрики + alert rules) | все | **CRITICAL** | низкий |
| **R3** | Надёжная очередь телеметрии (no data loss) | HL | **HIGH** | средний |
| **R4** | AE3: leases, janitor, intent sync | AE3 | **HIGH** | средний |
| **R5** | Firmware fail-safe и честная телеметрия | Firmware | **HIGH** | средний |
| **R6** | Laravel scheduler: catch-up, window_interval, fail-closed | Laravel | **HIGH** | средний |
| **R7** | Backup, retention, гигиена | Infra | medium | низкий |

---

## Этап R1 — Доставка алертов и prod-инфраструктура (CRITICAL)

> Без этого этапа все остальные алерты бессмысленны: сейчас в prod Alertmanager
> не может доставить ничего ни в Laravel, ни наружу.

### R1.1 Alertmanager → Laravel auth (K11)

- `backend/configs/prod/alertmanager/config.yml`, `backend/configs/dev/alertmanager/config.yml`: добавить `http_config.authorization` (bearer) для webhook receiver; секрет через env-substitution.
- `backend/docker-compose.prod.yml` / `.dev.yml`: прокинуть `ALERTMANAGER_WEBHOOK_SECRET` в alertmanager и laravel.
- Заменить placeholder SMTP/Telegram receivers на рабочие или удалить с явным комментарием «доставка только через Laravel webhook».
- Тест: `check_monitoring.sh` дополнить проверкой POST на webhook (см. R7.3).

### R1.2 Prod healthchecks + health-aware старты (K9)

- `backend/docker-compose.prod.yml`:
  - mqtt: `nc -z localhost 1883`; db: `pg_isready -U hydro`; redis: `redis-cli ping`;
  - все `depends_on` перевести на `condition: service_healthy` (паритет с dev);
  - HL healthcheck: HTTP `/health` вместо TCP 9300 (паритет с dev).
- `backend/docker-compose.dev.yml`: `restart: unless-stopped` для mqtt/db/redis/laravel; healthchecks для prometheus (`/-/healthy`), grafana (`/api/health`), alertmanager (`/-/ready`).
- Grafana prod: pin версии `11.5.2` вместо `latest`; пароль PG datasource из env (`configs/prod/grafana/datasources.yml:19-20`).

### R1.3 Синхронизация prod alerts.yml с dev

- Перенести отсутствующие в prod правила (HL command status repair ×2) из `configs/dev/prometheus/alerts.yml:92-110`.
- Дальше поддерживать паритет: одна группа правил, отличаются только пороги (комментарий в обоих файлах).

### Критерии приёмки R1

- В prod-конфигурации тестовый алерт из Prometheus доходит до таблицы `alerts` Laravel (интеграционный прогон в dev с включённым secret).
- `docker compose -f backend/docker-compose.prod.yml config` валиден; порядок старта: db/redis/mqtt → laravel → python-сервисы.

---

## Этап R2 — Observability-пробелы (CRITICAL)

> Цель: каждое «тихое падение» из карты выше получает метрику и alert rule.
> Только метрики/правила — поведение сервисов не меняется.

### R2.1 history-logger

| Метрика/правило | Где добавить |
|-----------------|--------------|
| `telemetry_deserialize_failed_total` (pop из Redis вернул мусор) | `common/redis_queue.py:267-269` |
| `telemetry_pg_write_failed_total{stage=last\|samples}` | `telemetry_processing.py:1441-1601` |
| `telemetry_dropped{reason="invalid_json"}` на MQTT ingress | `telemetry/ingress.py:92-93` |
| Redis ping + queue depth/utilization в `/health` | `system_routes.py` |
| Prometheus gauge `command_status_dlq_size`, `alert_dlq_size` (сейчас только `/health`) | `metrics.py` |
| Alert: `rate(mqtt_publish_errors_total[5m]) > 0` for 5m (H2) | `configs/*/prometheus/alerts.yml` |
| Alert: DLQ size > 0 for 10m; `delivery_dropped_total > 0` → critical | там же |
| `config_report_buffer_expired_total` / overflow counter | `handlers/_shared.py:169-189` |

### R2.2 AE3-Lite

| Метрика/правило | Где |
|-----------------|-----|
| Gauge `ae3_oldest_active_task_age_seconds{status}` (running/waiting_command/claimed) + alert > 15 мин (H3) | `infrastructure/metrics.py` + exporter query |
| Counter `ae3_intent_sync_failed_total` (mark_running/terminal errors) + alert | `runtime/worker.py:749-786` |
| Gauge `ae3_reconcile_consecutive_errors` + alert `AE3ReconcileLoopDegraded` | `runtime/worker.py:201-233` |
| Fix `COMMAND_DISPATCH_DURATION` (сейчас observe сразу после publish, всегда ≈0) | `command_publish_pipeline.py:193-195` |
| Alert rule на `OBSERVABILITY_WRITE_FAILED{kind="biz_alert"}` (тихий провал task_failed_alert) | alerts.yml |
| Counter `listener_invalid_payload_total`, gauge dispatch queue depth listeners | `intent_status_listener.py`, `zone_event_listener.py` |

### R2.3 Laravel scheduler

| Метрика/правило | Где |
|-----------------|-----|
| `laravel_scheduler_lock_skipped_total` | `AutomationDispatchSchedules.php:37-41` |
| `laravel_scheduler_missed_windows_total{zone_id,task_type}` + catchup debt gauge | `SchedulerCycleOrchestrator.php` / `SchedulerCycleFinalizer.php` |
| `hang_hints` → Prometheus gauge per code + периодический bridge critical hints → `AlertService` | `ZoneAutomationObservabilityService.php:386-426` |
| Missing scheduler API token: `Log::error` + `Command::FAILURE` вместо silent SUCCESS | `SchedulerCycleOrchestrator.php:55-71` |
| Auth (bearer или internal-network-only) на `GET /api/system/scheduler/metrics` | `routes/api.php:86-87` |

### R2.4 Инфраструктурные exporters

- Добавить в compose + prometheus.yml: `postgres_exporter`, `redis_exporter`, mosquitto probe (blackbox tcp или mosquitto-exporter) — закрывает H1/H4.
- Переименовать/починить `MQTTBrokerDown` (сейчас проверяет `up{job="mqtt-bridge"}`, а не брокер).
- Self-monitoring: `up{job="prometheus"}`, alertmanager, grafana.
- Alert «нода offline» и «зона без свежей телеметрии X мин» на Prometheus-уровне: экспортировать из HL gauge `node_last_seen_age_seconds{node_uid}` / `telemetry_last_age_seconds{zone_id}` (или SQL-exporter) — сейчас есть только app-level `biz_node_offline`.

### Критерии приёмки R2

- Каждый пункт таблиц — метрика видна в Prometheus, правило в `alerts.yml` (dev+prod), панель в Grafana (минимум: расширить `system-overview.json`).
- Негативные тесты: unit-тест на инкремент каждого нового счётчика.

---

## Этап R3 — Надёжная очередь телеметрии в history-logger (HIGH)

> Устраняем безвозвратную потерю телеметрии (K3, K4).

### R3.1 Reliable pop (K3)

- `common/redis_queue.py`: заменить LPOP-pipeline на паттерн processing-list (`LMOVE` queue → processing) либо Lua-скрипт с атомарным батчем.
- ACK после успешной записи в PG: удалить из processing; при рестарте — reclaim processing-list (startup drain).
- Элементы, не прошедшие десериализацию, — в side-list `hydro:telemetry:dead` + метрика (из R2.1).

### R3.2 Requeue при ошибке PG (K4)

- `telemetry_processing.py`: при ошибке батчевой записи (`telemetry_samples` insert, FK violation) возвращать необработанные элементы в processing/queue с retry-счётчиком; после N попыток — dead-list.
- Разделить обработку: per-item FK violation (нерегистрированный сенсор) → dead-list сразу, транспортные ошибки PG → requeue целиком.

### R3.3 DLQ для телеметрии + replay CLI

- По образцу `dlq_cli.py` (command status): просмотр/replay/purge `hydro:telemetry:dead`.
- Retention dead-list: TTL 7 дней, метрика размера.

### R3.4 PUBACK для команд (K13)

- `command_service.py:247-257`: `result.wait_for_publish(timeout=...)` перед `mark_command_sent`; timeout → `SEND_FAILED` (существующий drain подберёт).
- Метрика `commands_published_unconfirmed_total`.

### R3.5 Shutdown drain

- `telemetry_processing.py:1703-1725`: drain-loop до пустой очереди (с общим timeout), вместо лимита `batch_size × 10`; метрика `shutdown_queue_remaining`.
- Realtime broadcast: requeue при неуспешном force-flush (`telemetry_processing.py:390-411`).

### Критерии приёмки R3

- Интеграционный тест: kill PG посреди батча → рестарт → все сэмплы в `telemetry_samples`, без дублей (idempotent upsert / `ON CONFLICT`).
- Тест: мусорный элемент в очереди попадает в dead-list, остальной батч записывается.
- HL pytest suite зелёный; нагрузочный smoke: 10k сообщений без потерь при рестарте consumer.

---

## Этап R4 — AE3: leases, janitor, intent sync (HIGH)

### R4.1 Lease heartbeat fail-closed (K6)

- `runtime/worker.py:740-747`: transient DB error при heartbeat → ограниченный retry; после N подряд неудач — `lease_lost_event.set()` + infra alert (как в ветке `extend=False`).
- Тест: mock repository с 3 последовательными ошибками → задача отменяется через lease-lost path.

### R4.2 `waiting_command` в stale janitor (K7)

- `automation_task_repository.py`: `list_stale_waiting_command(updated_at + poll_deadline + margin)`.
- `stale_task_reconcile.py`: обработка — если команда terminal в `commands` → доиграть transition; если нет terminal и дедлайн истёк → `fail_for_recovery` (fail-closed, существующий путь).
- `stale_task_reconcile_result.py:17-18`: `kick_needed = requeued > 0 or failed > 0`.

### R4.3 Intent↔task sync (drift)

- `runtime/worker.py:749-786`: retry на `_safe_mark_intent_*`; счётчик из R2.2; периодический reconcile job «terminal task + non-terminal intent» → доводит intent до terminal (расширение существующего reap в Laravel или в AE3-reconcile).

### R4.4 HL retry контракт (K12)

- `runtime/env.py:119`: default `AE_HL_MAX_RETRIES=1`; обновить `AGENT.md` и тест на число HTTP-попыток.

### R4.5 Прочее high

- `execute_task.py:1452-1466`: non-success fail-safe shutdown batch → `send_biz_alert` (код `FLOW_STOP_FAILED` уже есть в каталоге).
- `sequential_command_gateway.py:35-36`: `ACCEPTED` убрать из `_NON_TERMINAL` (запрещённый статус по MQTT-контракту) → терминальный fail с кодом `command_protocol_violation`.
- Zone event listener whitelist (`runtime/app.py:282-337`): явный список critical event codes (E-STOP, emergency) которые обязаны будить worker; сейчас фильтр пропускает только `LEVEL_SWITCH_CHANGED`/`storage_state`.
- Listener reconnect: снизить max backoff (60s → 15s) + replay пропущенных terminal intents из таблицы на reconnect.
- `runtime/app.py:204-205`: crash-alert фоновой задачи планировать через tracked `_spawn_background_task`.

### Критерии приёмки R4

- `make test-ae` зелёный; новые тесты: janitor для `waiting_command`, lease heartbeat fail-closed, retry count к HL, ACCEPTED-статус.
- Chaos-сценарий (docker-стенд): kill AE3 в `waiting_command` → рестарт → задача доигрывается или фейлится за ≤ janitor-интервал, intent terminal, alert поднят.

---

## Этап R5 — Firmware: fail-safe и честная телеметрия (HIGH)

> Требует OTA-выкатки; правки менять поведение только в сторону безопасности.

### R5.1 Link-loss fail-safe для актуаторов (K1)

- Единая policy в `node_framework`: конфигурируемый `link_loss_timeout_sec` (NodeConfig, зеркалит `fail_safe_guards`); по истечении при MQTT DISCONNECTED:
  - pump_node / ph_node / ec_node: `pump_driver_emergency_stop_all()` **включая latched runs** (`pump_driver.c:673-693` — расширить на `auto_stop_enabled=false`);
  - relay_node / storage_irrigation_node: перевод реле в safe state (использовать NC/NO-корректную логику, см. `relay_driver.c:264-268`).
- Публиковать `event_code="link_loss_failsafe"` после reconnect.
- Документация: `NODE_CONFIG_SPEC.md` (+ формат поля), `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`.

### R5.2 Запрет legacy HMAC в production (K2)

- `node_command_handler.c:1065-1071`: `allow_legacy_hmac` только при dev-флаге сборки (`CONFIG_HYDRO_DEV_ALLOW_LEGACY_HMAC`); в release-сборке — жёсткий reject + error response `hmac_required`.

### R5.3 Честные stub/stale значения

- Убрать фиктивные дефолты: pH 6.5 (`ph_node_tasks.c:407-411`), EC 1.2 (`ec_node_framework_integration.c:942-944`) — вместо публикации placeholder: skip publish + `node_state_manager` error → topic `error`.
- Last-good republish EC: `stable:false` + возраст значения (`ec_node_framework_integration.c:929-958`).
- Climate NaN: не публиковать NaN (движок его молча дропает — `node_telemetry_engine.c:353-355`); публиковать error event.
- Бэкенд-контракт: HL/AE3 уже используют `stub`/`stable` — проверить, что correction planner отбрасывает `stub=true` (есть `test_sensor` reject stub, распространить на телеметрию pH — см. `_sensor_value_in_bounds`).

### R5.4 Ответы на невалидные команды

- `node_command_handler.c:822-836`: при невалидном JSON/не-object — если извлекается `cmd_id`, отправлять `command_response` со статусом `INVALID` (`invalid_json`); иначе — инкремент diagnostics counter. Устраняет вечное ожидание в AE3-poll (сейчас спасает только timeout).

### R5.5 Прочее high

- `trema_ph.c:103-108`: провал создания mutex → fail init + safe_mode (не продолжать без mutex).
- HMAC hot-path без heap: static buffer для canonical JSON (`node_command_handler.c:515-604`).
- WiFi reconnect backoff (`wifi_manager.c:84-99`): экспоненциальный с jitter, cap 60s.
- Time-sync re-request: периодический повтор `hydro/time/request` до получения ответа (`mqtt_manager.c:1017-1027`).
- `storage_irrigation_fw_pump_cmd.c:182-183`: done-queue full → retry с timeout вместо drop DONE.

### Критерии приёмки R5

- Сборка всех нод (`idf.py build`) без warnings в затронутых компонентах.
- HIL/node_sim сценарий: обрыв MQTT при запущенном насосе → останов в пределах `link_loss_timeout_sec`; `protocol-check` зелёный (contract не менялся — только новый event_code, обновить `NODE_CHANNELS_REFERENCE.md`).
- Обновлены `MQTT_SPEC_FULL.md`/`BACKEND_NODE_CONTRACT_FULL.md` (новый event_code, поведение INVALID response), `DATA_MODEL_REFERENCE.md` при необходимости.

---

## Этап R6 — Laravel scheduler: catch-up, window_interval, fail-closed (HIGH)

### R6.1 window_interval: план vs dispatch (K8)

- Зафиксировать доменную семантику в `doc_ai/06_DOMAIN_ZONES_RECIPES/` (что означает interval внутри window).
- Вариант A (вероятный): orchestrator диспатчит interval-тики внутри окна → доработать `SchedulerCycleOrchestrator.php:506-528`.
- Вариант B: окно = только границы → починить план UI (`ScheduleWorkspaceService.php:307-338`), чтобы не показывать несуществующие тики.
- Решение согласовать с владельцем продукта до реализации; текущее рассогласование — источник «тихо не полилось».

### R6.2 Interval catch-up / alert на пропуски

- `SchedulerCycleOrchestrator.php:309-327` + `SchedulerCycleFinalizer.php:87-102`: после простоя scheduler interval-расписания не догоняют пропуски. Минимум: метрика + алерт «пропущено N interval-тиков» (R2.3); опционально ограниченный replay как у time-based (`replay_limited`).
- `ScheduleWorkspaceService.php:59-63`: вычислять `missed_total`/`suppressed_total` вместо хардкода 0.

### R6.3 Fail-closed и логирование

- Missing API token → `FAILURE` (перенесено в R2.3, поведенческая часть здесь).
- `ScheduleLoader.php:71-76`: зоны, исключённые из-за ошибки effective targets → `Log::warning` + hang_hint.
- `SchedulerCycleOrchestrator.php:689-707`: retry flush буфера `scheduler_logs`; critical statuses — немедленная запись.
- HTTP → AE3: 1 retry на `ConnectionException` в `ScheduleDispatcher.php:103-139` (паритет с `ZoneAutomationStateService`).
- Per-window alert: при terminal-неуспехе irrigation-окна — `AlertService::createOrUpdateActive` (`infra_scheduler_command_failed` / новый `biz_irrigation_window_missed` в `error_codes.json`).

### R6.4 Гигиена

- `queue-supervisor.conf`: `--tries=3` для критичных jobs, рассмотреть 2 воркера.
- Retention: синхронизировать Laravel 30d vs Python 90d (`routes/console.php:12-19`) — единый источник в env.

### Критерии приёмки R6

- PHPUnit: новые тесты на catch-up метрику, fail-closed token, per-window alert; `php artisan test` зелёный; Pint clean.
- Ручной сценарий в dev: остановить laravel на 2 interval-тика → после старта виден alert/метрика пропуска.

---

## Этап R7 — Backup, retention, гигиена (MEDIUM)

### R7.1 Backup работоспособен (K10)

- Смонтировать persistent volume `/backups` в laravel-контейнер (dev+prod); проверить наличие `pg_dump` в образе (или вынести backup в sidecar).
- Alert на провал `backup:full` (schedule → `onFailure` → AlertService + Prometheus push).
- WAL archive rotation: подключить `scripts/backup/wal_archive.sh` cron + disk-usage alert (после postgres_exporter из R2.4).
- Прогнать restore-тест: `scripts/restore/*` на dev-стенде, задокументировать RTO/RPO в `08_SECURITY_AND_OPS/`.

### R7.2 SPOF-документация

- Задокументировать single-instance ограничения (mosquitto, HL как единственный publisher, AE3 single-writer) и recovery-процедуры в `08_SECURITY_AND_OPS/` (runbook). HA — вне скоупа плана.

### R7.3 Скрипты проверки

- `check_monitoring.sh`: + HL `/health` и `:9301/metrics`, firing alerts (`/api/v1/alerts`), тестовый webhook Alertmanager → Laravel.
- `check-prod-ready.sh`: + проверка `/backups` mount, `ALERTMANAGER_WEBHOOK_SECRET`, non-placeholder receivers.
- mqtt-bridge: формально deprecated `/bridge/.../commands` (нет idempotency/QUEUED lifecycle — `mqtt-bridge/main.py:256-315`) — вернуть 410 или proxy на HL; оставить live-status/config.

### Критерии приёмки R7

- `backup:full` в dev создаёт артефакты в persistent volume; restore-тест проходит.
- `check-prod-ready.sh` падает на непроставленном secret/receivers.

---

## 3. Порядок выполнения и зависимости

```
R1 (доставка алертов) ──► R2 (метрики+правила) ──► R3 (HL очередь)
                                   │                    │
                                   ├──► R4 (AE3)  ──────┤
                                   ├──► R6 (Laravel) ───┤ независимы между собой
                                   └──► R5 (Firmware) ──┘ (требует OTA-окна)
R7 — параллельно после R1.
```

- R1+R2 — первая неделя работ, без них нельзя верифицировать остальное.
- R3, R4, R6 — независимые треки, можно параллелить.
- R5 — требует окна для OTA-выкатки и HIL-проверки; спецификации (`NODE_CONFIG_SPEC.md`, MQTT-доки) обновляются **до** кода (doc-first).

## 4. Definition of Done по всему плану

1. Все critical K1–K13 закрыты или явно downgrade'ированы с обоснованием в этом документе.
2. Каждая категория «тихого падения» из карты §1 имеет: метрику → alert rule (dev+prod) → панель Grafana → runbook-строку.
3. Полные suites зелёные: Laravel, `make test-ae`, HL, mqtt-bridge, Vitest, protocol-check.
4. Документация синхронизирована: `MQTT_SPEC_FULL.md`, `BACKEND_NODE_CONTRACT_FULL.md`, `NODE_CONFIG_SPEC.md`, `HISTORY_LOGGER_API.md`, `ae3lite.md`, `ERROR_CODE_CATALOG.md` (новые коды), `DATA_RETENTION_POLICY.md`.
5. Chaos-минимум пройден: kill PG во время ingest, kill AE3 в `waiting_command`, обрыв MQTT при работающем насосе (sim/HIL), останов scheduler на 2 тика — во всех случаях: нет потери данных или есть alert, нет застрявших задач/интентов, актуаторы в safe state.

---

## 5. Приложение: полные отчёты по слоям

Детальные таблицы находок (файл:строка, severity, рекомендация) — в отчётах субагентов аудита от 2026-07-07:

- Firmware ESP32 — ~30 находок (fail-safe, stub-телеметрия, HMAC hot path, reconnect).
- history-logger + mqtt-bridge — ~40 находок (Redis queue, DLQ, PUBACK, shutdown drain).
- AE3-Lite — ~35 находок (lease, janitor, intent sync, listeners, метрики).
- Laravel scheduler/ingest/alerts — ~45 находок (catch-up, window_interval, hang_hints, метрики).
- Инфраструктура — C1–C6 + H1–H4 (compose, Mosquitto, Prometheus, Alertmanager, backup).

При взятии этапа в работу — сверяться с actual-кодом: номера строк могли сместиться.
