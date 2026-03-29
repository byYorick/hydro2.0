# PYTHON_SERVICES_ARCH.md
# Архитектура Python-сервисов hydro2.0 (AE3)

**Версия:** 3.2  
**Дата обновления:** 2026-03-24  
**Статус:** Актуально (канонично для runtime)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy scheduler-task transport удален из runtime; обратная совместимость не поддерживается.

---

## 1. Цель

Зафиксировать текущую архитектуру Python-сервисов после перехода на AE3 authority runtime:
- единый поток команд через `history-logger`;
- единый запуск workflow зоны через `POST /zones/{id}/start-cycle`;
- direct SQL read-model в runtime path automation-engine;
- `LISTEN/NOTIFY + reconcile polling` для телеметрии и статусов команд.
- для AE3-совместимого runtime: fast-path wake-up по `scheduler_intent_terminal` без отказа от DB-first source of truth.

---

## 2. Состав сервисов

### 2.1 `history-logger`

Назначение:
- подписка на MQTT телеметрию и события;
- запись в PostgreSQL (`telemetry_samples`, `telemetry_last`, `commands`, `zone_events`);
- единственная точка публикации команд в MQTT через `POST /commands`.

Порты:
- `9300` REST API;
- `9301` metrics.

### 2.2 `automation-engine` (AE3)

Назначение:
- долгоживущие zone runners;
- two-tank workflow;
- коррекция pH/EC;
- rich zone state для UI;
- исполнение intents от Laravel scheduler.

Порты:
- `9405` REST API;
- `9401` metrics.

### 2.3 Прочие Python-сервисы

- `mqtt-bridge`, `digital-twin`, `health-monitor` и др. работают в своих доменах.
- Никакой сервис, кроме `history-logger`, не публикует device-команды напрямую в MQTT.

---

## 3. Канонические потоки

### 3.1 Командный поток (инвариант)

`Laravel scheduler -> automation-engine -> history-logger -> MQTT -> ESP32`

Правила:
- `automation-engine` отправляет команды только через `POST http://history-logger:9300/commands`.
- Командный await в AE3 завершается только по terminal statuses:
  `DONE|ERROR|INVALID|BUSY|NO_EFFECT|TIMEOUT|SEND_FAILED`.
- `QUEUED|SENT|ACK` считаются non-terminal.

### 3.1.1. Alert lifecycle flow

Канонический alert flow:

`Python/AE3 producer -> Laravel /api/python/alerts -> AlertService -> alerts + zone_events + realtime`

Инварианты:

- Python и AE3 не пишут lifecycle alert-а напрямую в `alerts` или `zone_events`;
- history-logger владеет transport retry/DLQ (`pending_alerts`, `pending_alerts_dlq`);
- scoped incident identity хранится в `details.dedupe_key`;
- `system.alert_policies` задаёт policy auto-resolve только для policy-managed AE3 business alert code.

### 3.2 Запуск цикла и intents

Единый внешний entrypoint:
- `POST /zones/{id}/start-cycle`

Scheduler модель:
1. Laravel scheduler пишет запись в `zone_automation_intents` со статусом `pending`.
2. Laravel вызывает `POST /zones/{id}/start-cycle`.
3. AE3 claim intent (`FOR UPDATE SKIP LOCKED`) и исполняет.
4. AE3 обновляет intent lifecycle (`claimed/running/completed/failed/cancelled`).

Контракт intent payload (wake-up only):
- разрешены только поля metadata: `source`, `task_type=diagnostics`, `workflow=cycle_start`, `topology`, `grow_cycle_id` (опционально);
- `task_payload` и `schedule_payload` не используются и считаются legacy;
- runtime path `start-cycle` не принимает и не исполняет device-level payload из intent.

Legacy endpoint-ы:
- `POST /scheduler/task` — удален.
- `GET /scheduler/task/{task_id}` — удален.

### 3.3 Телеметрия и фидбек команд

Основной transport:
- PostgreSQL `LISTEN/NOTIFY` каналы:
  - `ae_command_status`
  - `ae_signal_update`

Payload-contract:
- `ae_command_status`: `cmd_id`, `zone_id`, `status`, `updated_at`;
- `ae_signal_update`: `zone_id`, `kind`, `updated_at`.

Обязательный fallback:
- reconcile polling (`commands`, `telemetry_last`, `zone_events`).
- при burst/перегрузке listener runtime переключается на polling-first до стабилизации.

Источник истины:
- таблицы PostgreSQL; не runtime HTTP запросы в Laravel API.

### 3.3.1 Config-report observation

Канонический flow для `config_report`:

`ESP32 -> MQTT -> history-logger -> Laravel /api/python/nodes/config-report-observed -> NodeService/NodeLifecycleService`

Инварианты:
- `history-logger` только сохраняет `config_report`, синхронизирует channel snapshot и сообщает Laravel наблюдаемый факт;
- `history-logger` не выполняет `service-update` и не делает lifecycle transition ноды напрямую;
- решение о финализации `pending_zone_id -> zone_id` принимает только Laravel;
- финализация bind/rebind разрешена только после namespace validation на стороне Laravel.

### 3.4 Runtime hardening

Для AE3-совместимого runtime path действуют дополнительные правила:
- `scheduler_intent_terminal` используется только как fast-path для `worker.kick()`; source of truth остаётся в PostgreSQL.
- reconcile polling для legacy command wait использует bounded exponential backoff: старт от `reconcile_poll_interval_sec`, множитель `1.5`, верхняя граница `5s`.
- публикация команды в `history-logger` допускает не более одного transient retry с backoff `1s` для transport error или `HTTP 5xx`; далее runtime fail-closed.
- registry background tasks должен быть hard-limited; overflow не может продолжаться в режиме best-effort.
- whole-task execution ограничен `AE_MAX_TASK_EXECUTION_SEC` (default `900s`); timeout обязан переводить runtime в fail-closed path с fail-safe shutdown и terminal `failed`.
- runtime различает timeout cancel и обычный service shutdown cancel: только timeout-path завершается как `ae3_task_execution_timeout`, штатная остановка оставляет recovery после restart.
- минимальные Prometheus-метрики intent lifecycle: `ae3_intent_claimed_total`, `ae3_intent_terminal_total`, `ae3_intent_stale_reclaimed_total`.

---

## 4. Runtime-модель AE3

- один event loop на процесс;
- один долгоживущий `ZoneRunner` на зону;
- последовательное исполнение шагов: `send -> await terminal -> next`;
- переход на следующий шаг только при `DONE`.

### 4.1 Режимы управления

Поддерживаются только:
- `auto`
- `semi`
- `manual`

### 4.2 Two-tank scope

Поддерживаемая топология runtime v1:
- только `two_tank`.

Фазы:
- `idle -> tank_filling -> tank_recirc -> ready -> irrigating <-> irrig_recirc`.

---

## 5. Источник runtime-данных (direct SQL read-model)

AE runtime читает данные напрямую из PostgreSQL:
- `zones`, `nodes`, `node_channels`, `infrastructure_instances`, `channel_bindings`;
- `grow_cycles`, `grow_cycle_phases`;
- `automation_effective_bundles`;
- `automation_config_violations`;
- `telemetry_last`, `telemetry_samples`;
- `commands`, `zone_events`, `zone_workflow_state`, `pid_state`.

Канонический runtime-конфиг:
- authority state живёт в `automation_config_documents`;
- runtime не читает raw documents на hot path;
- runtime использует compiled bundle по `grow_cycles.settings.bundle_revision`.

Compile precedence:
`system.* -> zone.* -> cycle.*`

Требования:
- runtime path не зависит от `/api/internal/effective-targets/*`;
- runtime path не читает legacy automation config tables как source of truth;
- missing bundle / revision mismatch обрабатываются fail-closed.

---

## 6. API automation-engine (runtime)

### 6.1 Канонические endpoint-ы

- `POST /zones/{id}/start-cycle`
- `GET /zones/{id}/state`
- `POST /zones/{id}/control-mode`
- `POST /zones/{id}/manual-step`
- `POST /zones/{id}/start-relay-autotune`
- `GET /health/live`
- `GET /health/ready`

### 6.2 Удаленные endpoint-ы

- `POST /scheduler/task`
- `GET /scheduler/task/{task_id}`
- `POST /scheduler/bootstrap`
- `POST /scheduler/bootstrap/heartbeat`
- `POST /scheduler/internal/enqueue`
- `POST /zones/{id}/automation/manual-resume`
- `GET /zones/{id}/automation-state`
- `GET /zones/{id}/automation/control-mode`
- `POST /zones/{id}/automation/control-mode`
- `POST /zones/{id}/automation/manual-step`
- `/test/hook*`

---

## 7. База данных и миграции

Изменения схемы только через Laravel migrations.

Ключевые сущности runtime:
- `automation_effective_bundles` (compiled runtime config);
- `automation_config_violations` (machine-readable config errors);
- `zone_automation_intents` (scheduler -> automation контракт);
- `zone_workflow_state` (workflow snapshot);
- `zone_automation_state` (rich UI state snapshot);
- `command_audit`.

---

## 8. Freshness и fail-closed

`effective_ts = COALESCE(sample_ts, updated_at)`

Пороги (дефолты):
- pH/EC: `<= 300s`
- gating flags (`flow_active/stable/corrections_allowed`): `<= 60s`
- irr state: `<= 30s`
- level switches: `<= 120s`

Fail-closed:
- stale critical сигнал -> коррекция/шаг блокируется;
- причина фиксируется в `zone_events`.

---

## 9. Тестирование

Обязательные уровни:
- unit: workflow, plan executor, PID/gating/freshness;
- integration: command wait, notify/polling, intent claim/idempotency;
- e2e smoke в Docker: `start-cycle -> two-tank progression -> state API`.

---

## 10. Legacy policy

- замененный legacy-код удаляется в той же итерации;
- отключенные “временно” legacy route/флаги не допускаются;
- после этапов обязателен cleanup-аудит.

---

## 11. Связанные документы

- `HISTORY_LOGGER_API.md`
- `REST_API_REFERENCE.md`
- `API_SPEC_FRONTEND_BACKEND_FULL.md`
- `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- `ae3lite.md`
