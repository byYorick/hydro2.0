# PYTHON_SERVICES_ARCH.md
# Архитектура Python-сервисов hydro2.0 (AE 1.0.0)

**Версия:** 3.8
**Дата обновления:** 2026-09-25
**Статус:** Актуально (канон поведения автоматики — `ae4.md`; sync 2026-09-25: без ae3lite и без Laravel dispatcher)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: диспетчер Laravel и зональные `start-*` ingress удалены; wake-up — тик воркера 1.0.0.

---

## 1. Цель

Зафиксировать текущую архитектуру Python-сервисов после AE 1.0.0:
- единый поток команд через `history-logger`;
- пробуждение зон — тик воркера `ae4/` (без `ScheduleDispatcher`);
- **тик климата теплицы (крыша)** — один `POST /greenhouses/{id}/start-climate-tick` на теплицу из того же тика;
- direct SQL read-model в runtime path automation-engine;
- terminal статусы команд — **poll** (не LISTEN для telemetry/command status).

---

## 2. Состав сервисов

### 2.1 `history-logger`

Назначение:
- подписка на MQTT телеметрию и события;
- запись в PostgreSQL (`telemetry_samples`, `telemetry_last`, `commands`, `zone_events`);
- единственная точка публикации команд в MQTT через `POST /commands`.

Порты:
- `9300` REST API;
- `9300/metrics` Prometheus metrics.

### 2.2 `automation-engine` (AE 1.0.0)

Назначение:
- воркер `ae4/` + HTTP (`/health`, `/metrics`, состояние зоны, `POST /greenhouses/{id}/start-climate-tick`);
- тик сам назначает полив/химию/свет и один climate-tick на теплицу;
- коррекция pH/EC (импульс);
- rich zone state для UI (`unattended_ready`, blockers);
- device-команды только через history-logger.
- исполнение intents от Laravel scheduler.

Порты:
- `9405` REST API;
- `9405/metrics/` Prometheus metrics.

### 2.3 Прочие Python-сервисы

- `digital-twin`, `telemetry-aggregator` (и прочие вспомогательные сервисы из `docker-compose`) работают в своих доменах.
- Никакой сервис, кроме `history-logger`, не публикует device-команды напрямую в MQTT.

### 2.4 `mqtt-bridge` (ops leftover / probe)

Роль: **ops leftover / probe + metrics**, **не** command path и **не** канон NodeConfig.
Порт: `9000` (REST + `/metrics`). Входит в default `make up` как leftover; боевой путь команд и конфигов — только `history-logger`.

Канон:
- команды к узлам — `history-logger` `POST /commands` (порт `9300`);
- NodeConfig — `history-logger` `POST /nodes/{uid}/config` из Laravel `PublishNodeConfigJob`.

`POST /bridge/{zones|nodes}/commands` отвечают **410** (`endpoint_deprecated_use_history_logger`) и **пока живы до P1** (удаление роутов — отдельная фаза). Не использовать как мост команд.

| Метод | Путь | Статус |
|-------|------|--------|
| GET | `/metrics` | active — ops probe |
| GET | `/bridge/nodes/{node_uid}/live-status` | active — MQTT live probe |
| POST | `/bridge/nodes/{node_uid}/config` | **legacy**; канон уже HL `POST /nodes/{uid}/config` (`PublishNodeConfigJob`) |
| POST | `/bridge/zones/{zone_id}/commands` | **410** (жив до P1) → history-logger |
| POST | `/bridge/nodes/{node_uid}/commands` | **410** (жив до P1) → history-logger |

README: `backend/services/mqtt-bridge/README.md`.

### 2.5 `digital-twin`

Назначение: solvers pH/EC/climate, калибровка → `zone_dt_params`, offline/live sim, replay.

Порты (dev): REST `8003`, metrics `9403`.

Канон калибровки: `POST /v1/calibrate/zone/{zone_id}?persist=true` (не legacy `/calibrate/zone/...`).  
Live: `/simulations/live/start|stop` (связь с `node-sim-manager` `:9100`).  
Доки: `doc_ai/09_AI_AND_DIGITAL_TWIN/DIGITAL_TWIN_ENGINE.md`, `backend/services/digital-twin/README.md`.

### 2.6 `feature-builder` / `node-sim-manager`

- `feature-builder` — **skeleton**, не writer витрин в runtime. Не часть default `make up` (compose profile `ml`, `make up-ml`). Порт **9410** health/metrics; фазы — `ML_FEATURE_PIPELINE.md`. Не расширять без явного запроса.
- `node-sim-manager` — управление node_sim для live-sim / HIL (порт **9100`); не часть default `make up` (profile `sim`).

---

## 3. Канонические потоки

### 3.1 Командный поток (инвариант)

`Laravel scheduler -> automation-engine -> history-logger -> MQTT -> ESP32`

Правила:
- `automation-engine` отправляет команды только через `POST http://history-logger:9300/commands`.
- Командный await в AE3 завершается только по terminal statuses:
  `DONE|ERROR|INVALID|BUSY|NO_EFFECT|TIMEOUT|SEND_FAILED`.
- `PENDING|QUEUED|SENT|ACK|RUNNING` считаются non-terminal.

### 3.1.1. Alert lifecycle flow

Канонический alert flow:

`Python/AE3 producer -> Laravel /api/python/alerts -> AlertService -> alerts + zone_events + realtime`

Инварианты:

- Python и AE3 не пишут lifecycle alert-а напрямую в `alerts` или `zone_events`;
- history-logger владеет transport retry/DLQ (`pending_alerts`, `pending_alerts_dlq`);
- scoped incident identity хранится в `details.dedupe_key`;
- `system.alert_policies` задаёт policy auto-resolve только для policy-managed AE3 business alert code.

### 3.2 Пробуждение зон (AE 1.0.0)

Диспетчера Laravel (`ScheduleDispatcher`, `automation:dispatch-schedules`) нет. Маршрутов `start-cycle` / `start-irrigation` / `start-lighting-tick` / `start-solution-topup` / `start-solution-change` нет.

Живой путь:
1. Тик воркера `ae4/` обходит зоны без явного `ae3`, при необходимости пишет задачу мутации с `due_at=now`.
2. Тот же тик будит форточки одним `POST /greenhouses/{id}/start-climate-tick` на теплицу.
3. Device-команды — только через history-logger `POST /commands`.

Канон: `doc_ai/04_BACKEND_CORE/ae4.md`. Удалённые endpoint'ы (в прошлом):
- `POST /scheduler/task`, `GET /scheduler/task/{task_id}`;
- зональные `start-*` ingress волны AE3.

### 3.3 Телеметрия и фидбек команд

Канонические `LISTEN/NOTIFY` каналы, на которые AE3 действительно подписывается (см. `ae3lite/infrastructure/read_models/laravel_schema_contract.py::NOTIFY_CHANNELS`):
- `scheduler_intent_terminal` — terminal lifecycle intent от Laravel scheduler (`IntentStatusListener` → `worker.kick()`).
- `ae_zone_event` — node runtime event (`level_switch_changed`, `storage_state/event`, e-stop), записанный history-logger'ом (`ZoneEventListener` → `worker.kick()`).

Канал `ae_command_status` (триггер `trg_ae_command_status_notify` на `commands`) **не подписывается** AE3 — он остаётся как fast-path notification для других потребителей (Laravel scheduler cockpit, future консьюмеры). Reconcile terminal статусов команд для AE3 идёт исключительно через **polling**:
- `SequentialCommandGateway.recover_waiting_command(...)` периодически читает `ae_commands` + `commands` с интервалом `AE_RECONCILE_POLL_INTERVAL_SEC` (default `0.5s`), bounded backoff x1.5, upper bound `5s`.
- В `waiting_command` цикл polling крутится до terminal статуса либо до истечения stage deadline (`AE_MAX_TASK_EXECUTION_SEC`, default `900s`).

Payload-contract:
- `scheduler_intent_terminal`: `intent_id`, `zone_id`, `status` (terminal), `updated_at`.
- `ae_zone_event`: `zone_id`, `event_type`, `event_id`, `created_at`.

Status: AE3 listens — `scheduler_intent_terminal`, `ae_zone_event`. Status: NOT subscribed by AE3 — `ae_command_status`, `ae_signal_update` (зарезервированы за scheduler cockpit / Laravel; AE3 для команд использует polling).

Обязательные правила:
- reconcile polling (`commands`, `telemetry_last`, `zone_events`) обязателен независимо от NOTIFY — DB остаётся source of truth.
- при burst/перегрузке runtime переключается на polling-first до стабилизации listener'а.
- любой fast-path NOTIFY никогда не заменяет canonical DB read.

Для production IRR two-tank runtime:
- `storage_irrigation_node` публикует channel-level `level_* /event` с `event_code=level_switch_changed`;
- `history-logger` сохраняет их в `zone_events`;
- `history-logger` после успешной записи node runtime event публикует PostgreSQL `NOTIFY ae_zone_event`;
- AE3 может использовать их только как fast-path wake-up/reconcile signal;
- canonical stage decision остаётся DB-first.

Детальный контракт см. `AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md`.
Контракт дублирования fail-safe/e-stop логики см. `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`.

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
- `ae_zone_event` используется только как fast-path invalidation/wake-up для node runtime events; решение принимается только после повторного чтения `zone_events` / `telemetry_last`.
- `initial=true` из `LEVEL_SWITCH_CHANGED` будит reconcile и может использоваться для `ready/startup guard`, но не должен сам по себе завершать active stage без повторного DB confirmation.
- reconcile polling при ожидании terminal статуса в `commands` использует bounded exponential backoff: старт от `reconcile_poll_interval_sec`, множитель `1.5`, верхняя граница `5s`.
- публикация команды в `history-logger` допускает не более одного transient retry с backoff `1s` для transport error или `HTTP 5xx`; далее runtime fail-closed.
- registry background tasks должен быть hard-limited; overflow не может продолжаться в режиме best-effort.
- whole-task execution ограничен `AE_MAX_TASK_EXECUTION_SEC` (default `900s`); timeout обязан переводить runtime в fail-closed path с fail-safe shutdown и terminal `failed`.
- runtime различает timeout cancel и обычный service shutdown cancel: только timeout-path завершается как `ae3_task_execution_timeout`, штатная остановка оставляет recovery после restart.
- минимальные Prometheus-метрики intent lifecycle: `ae3_intent_claimed_total`, `ae3_intent_terminal_total`, `ae3_intent_stale_reclaimed_total`.

---

## 4. Runtime-модель AE3

Архитектура runtime — DB-backed drain loop, не per-zone runner:
- один event loop на процесс;
- один `Ae3RuntimeWorker` (`ae3lite/runtime/worker.py`) на процесс выполняет drain loop по `ae_tasks`: `claim_next_pending` (FOR UPDATE SKIP LOCKED) → `ZoneLease.claim` → `ExecuteTaskUseCase.run()` → terminal или requeue через `update_stage`;
- per-zone изоляция обеспечивается **только** комбинацией partial unique index `ae_tasks_active_zone_unique` и `ae_zone_leases` (а не отдельным процессом/таском на зону);
- последовательное исполнение шагов: `send -> await terminal -> next`;
- переход на следующий шаг только при `DONE`;
- worker продлевает lease heartbeat и при потере lease отменяет run с `ae3_zone_lease_lost`.

### 4.1 Режимы управления

Поддерживаются только:
- `auto`
- `semi`
- `manual`

### 4.2 Topology registry (zone workflows)

Реальный registry задан в `ae3lite/application/services/workflow_topology.py` и `topology_registry.py`. Поддерживаемые topology для `ae_tasks`:
- `two_tank_drip_substrate_trays` — production two-tank workflow (`TWO_TANK` graph);
- `two_tank` — алиас к `two_tank_drip_substrate_trays` (compat);
- `generic_cycle_start` — облегчённый cycle_start для зон без two-tank (`single_tank`/`single_tank_drip`);
- `lighting_tick` — workflow для `task_type='lighting_tick'`.

Greenhouse climate (`task_type='greenhouse_climate_tick'`) исполняется отдельным runtime path (`ae3lite/greenhouse_climate/`) и не использует topology registry зоны.

Фазы two-tank (стадии графа агрегируются в `workflow_phase`):
- `idle -> tank_filling -> tank_recirc -> ready -> irrigating <-> irrig_recirc`.

---

## 5. Источник runtime-данных (direct SQL read-model)

AE runtime читает данные напрямую из PostgreSQL:
- `zones`, `nodes`, `node_channels`, `infrastructure_instances`, `channel_bindings`;
- `grow_cycles`, `grow_cycle_phases`;
- `automation_effective_bundles`;
- `telemetry_last`, `telemetry_samples`;
- `commands`, `zone_events`, `zone_workflow_state`, `pid_state`;
- `ae_tasks`, `ae_commands`, `ae_zone_leases`, `ae_stage_transitions`;
- `zone_automation_intents` (для claim из Laravel scheduler).

Канонический runtime-конфиг:
- authority state живёт в `automation_config_documents`;
- runtime не читает raw documents на hot path;
- runtime использует compiled bundle по `grow_cycles.settings.bundle_revision`;
- `automation_config_violations` поддерживается на стороне Laravel compiler, но AE3 runtime его на hot path не читает: фактический mismatch bundle ловится через `ZoneSnapshotReadModel` (raise `ae3_snapshot_bundle_invalid`/`ae3_snapshot_bundle_missing`).

Compile precedence (для Laravel compiler):
`system.* -> zone.* -> cycle.*`

Требования:
- runtime path не зависит от `/api/internal/effective-targets/*`;
- runtime path не читает устаревшие automation config tables как source of truth;
- missing bundle / revision mismatch обрабатываются fail-closed.

---

## 6. API automation-engine (runtime)

### 6.1 Канонические endpoint-ы

Wake-up / ingress:
- `POST /zones/{id}/start-cycle`
- `POST /zones/{id}/start-irrigation`
- `POST /zones/{id}/start-lighting-tick`
- `POST /zones/{id}/start-solution-topup`
- `POST /zones/{id}/start-solution-change`
- `POST /greenhouses/{id}/start-climate-tick`

Internal / status:
- `GET /internal/tasks/{task_id}` — canonical task status

Operator-уровень (см. `runtime/app.py`):
- `GET /zones/{id}/state`
- `GET /zones/{id}/control-mode`
- `POST /zones/{id}/control-mode`
- `POST /zones/{id}/manual-step`

Ops:
- `GET /health/live`
- `GET /health/ready`
- `/metrics/` — Prometheus ASGI mount

Status: **planned / not implemented** — `POST /zones/{id}/start-relay-autotune` (relay-autotune остаётся out of scope для v1, см. `ae3lite.md` §1).

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

## 10. Политика по устаревшему коду

- заменённый устаревший код удаляется в той же итерации;
- отключенные «временно» устаревшие route/флаги не допускаются;
- после этапов обязателен cleanup-аудит.

---

## 11. Связанные документы

- `HISTORY_LOGGER_API.md`
- `REST_API_REFERENCE.md`
- `API_SPEC_FRONTEND_BACKEND_FULL.md`
- `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- `ae4.md`
