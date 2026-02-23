# PYTHON_SERVICES_ARCH.md
# Архитектура Python-сервисов hydro2.0 (AE2-Lite)

**Версия:** 3.0  
**Дата обновления:** 2026-02-21  
**Статус:** Актуально (канонично для runtime)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy scheduler-task transport удален из runtime; обратная совместимость не поддерживается.

---

## 1. Цель

Зафиксировать текущую архитектуру Python-сервисов после перехода на AE2-Lite:
- единый поток команд через `history-logger`;
- единый запуск workflow зоны через `POST /zones/{id}/start-cycle`;
- direct SQL read-model в runtime path automation-engine;
- `LISTEN/NOTIFY + reconcile polling` для телеметрии и статусов команд.

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

### 2.2 `automation-engine` (AE2-Lite)

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
- Командный await в AE2-Lite завершается только по terminal statuses:
  `DONE|ERROR|INVALID|BUSY|NO_EFFECT|TIMEOUT|SEND_FAILED`.
- `QUEUED|SENT|ACK` считаются non-terminal.

### 3.2 Запуск цикла и intents

Единый внешний entrypoint:
- `POST /zones/{id}/start-cycle`

Scheduler модель:
1. Laravel scheduler пишет запись в `zone_automation_intents` со статусом `pending`.
2. Laravel вызывает `POST /zones/{id}/start-cycle`.
3. AE2-Lite claim intent (`FOR UPDATE SKIP LOCKED`) и исполняет.
4. AE2-Lite обновляет intent lifecycle (`claimed/running/completed/failed/cancelled`).

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

---

## 4. Runtime-модель AE2-Lite

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

AE2-Lite в runtime читает данные напрямую из PostgreSQL:
- `zones`, `nodes`, `node_channels`, `infrastructure_instances`, `channel_bindings`;
- `grow_cycles`, `grow_cycle_phases`;
- `zone_automation_logic_profiles`;
- `telemetry_last`, `telemetry_samples`;
- `commands`, `zone_events`, `zone_workflow_state`, `pid_state`.

Приоритет резолва runtime-настроек:
`phase snapshot -> grow_cycle_overrides -> zone_automation_logic_profiles (active mode)`.

Требование:
- runtime path не зависит от `/api/internal/effective-targets/*`.

---

## 6. API automation-engine (runtime)

### 6.1 Канонические endpoint-ы

- `POST /zones/{id}/start-cycle`
- `GET /zones/{id}/state`
- `POST /zones/{id}/control-mode`
- `POST /zones/{id}/manual-step`
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

Ключевые сущности AE2-Lite:
- `zone_automation_logic_profiles.command_plans` (JSONB, явный приоритет);
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
- `../10_AI_DEV_GUIDES/AE2_LITE_IMPLEMENTATION_PLAN.md`
