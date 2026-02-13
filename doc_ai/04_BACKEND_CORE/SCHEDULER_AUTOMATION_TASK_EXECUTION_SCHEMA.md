# Схема Scheduler -> Automation-Engine: аудит, целевая модель и план внедрения (v3.2)

**Дата:** 2026-02-10  
**Статус:** Актуализировано после реализации cycle-start/refill workflow  
**Область:** `backend/services/scheduler`, `backend/services/automation-engine`, `backend/laravel`  

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость для старых scheduler/device-level контрактов не поддерживается.

---

## 1. Источники и границы аудита

Проверены фактические контракты и поведение по коду:

- `backend/services/scheduler/main.py`
- `backend/services/scheduler/test_main.py`
- `backend/services/automation-engine/api.py`
- `backend/services/automation-engine/scheduler_task_executor.py`
- `backend/services/automation-engine/infrastructure/command_bus.py`
- `backend/services/automation-engine/test_api.py`
- `backend/laravel/app/Http/Controllers/SchedulerTaskController.php`
- `backend/laravel/tests/Feature/SchedulerTaskControllerTest.php`
- `backend/laravel/routes/api.php`

Цель этого документа:
1. Зафиксировать `as-is` (что реально работает сейчас).
2. Зафиксировать `to-be` (какая модель нужна по целевой архитектуре).
3. Дать пошаговый план рефакторинга и тестирования.

---

## 2. As-Is (фактическая реализация)

## 2.1 Роли сервисов

- `scheduler`:
  - строит расписания из `effective-targets`;
  - отправляет абстрактную задачу в `automation-engine` через `POST /scheduler/task`;
  - хранит active task в памяти (`_ACTIVE_TASKS`), опрашивает статус задачи;
  - пишет `scheduler_logs` и `zone_events` о lifecycle.

- `automation-engine`:
  - принимает scheduler-task через `POST /scheduler/task`;
  - выполняет task через `SchedulerTaskExecutor`;
  - отправляет device-level команды через `CommandBus -> history-logger`;
  - отдает статус по `GET /scheduler/task/{task_id}`;
  - хранит snapshot задачи в `scheduler_logs`.

- `laravel`:
  - отдает UI API:
    - `GET /api/zones/{zone}/scheduler-tasks`
    - `GET /api/zones/{zone}/scheduler-tasks/{taskId}`
  - при `show` использует только upstream статус из `automation-engine` (legacy fallback удалён).

## 2.2 Реально существующие endpoint-ы

### automation-engine

- `POST /scheduler/task`
- `GET /scheduler/task/{task_id}`
- `POST /scheduler/bootstrap`
- `POST /scheduler/bootstrap/heartbeat`
- `POST /scheduler/internal/enqueue`
- `GET /health/live`
- `GET /health/ready`
- `POST /test/hook` (только test mode)

### laravel

- `GET /api/zones/{zone}/scheduler-tasks`
- `GET /api/zones/{zone}/scheduler-tasks/{taskId}`

## 2.3 Реальный контракт scheduler-task (as-is)

### `POST /scheduler/task` request (as-is)

```json
{
  "zone_id": 28,
  "task_type": "irrigation",
  "payload": {
    "targets": {},
    "config": {},
    "trigger_time": "2026-02-10T10:00:00"
  },
  "scheduled_for": "2026-02-10T10:00:00",
  "due_at": "2026-02-10T10:00:15",
  "expires_at": "2026-02-10T10:02:00",
  "correlation_id": "sch:z28:irrigation:abc123def456"
}
```

Текущее поведение:
- `correlation_id` обязателен.
- `due_at`, `expires_at` обязательны, используются для детерминированного fail-fast (`rejected/expired`).
- реализована идемпотентность по `correlation_id` с `idempotency_payload_mismatch=409`.

### `POST /scheduler/task` response (as-is)

```json
{
  "status": "ok",
  "data": {
    "task_id": "st-...",
    "zone_id": 28,
    "task_type": "irrigation",
    "status": "accepted"
  }
}
```

### `GET /scheduler/task/{task_id}` response (as-is)

```json
{
  "status": "ok",
  "data": {
    "task_id": "st-...",
    "zone_id": 28,
    "task_type": "irrigation",
    "status": "running",
    "created_at": "2026-02-10T10:00:00",
    "updated_at": "2026-02-10T10:00:01",
    "scheduled_for": "2026-02-10T10:00:00",
    "due_at": "2026-02-10T10:00:15",
    "expires_at": "2026-02-10T10:02:00",
    "correlation_id": "sch:z28:irrigation:abc123def456",
    "result": null,
    "error": null,
    "error_code": null
  }
}
```

### Статусы (as-is)

- В `automation-engine`:
  - при валидных дедлайнах: `accepted -> running -> completed|failed`;
  - при дедлайнах в прошлом: immediate terminal `rejected|expired` (без запуска executor).
- В `scheduler` дополнительно есть локальные транспортные/наблюдательные terminal-состояния:
  - `timeout`
  - `not_found`

## 2.3.1 Формальная owner-модель статусов (фиксировано, R0)

- Business-статусы (owner: `automation-engine`, источник истины: `/scheduler/task/{task_id}`):
  - `accepted`, `running`, `completed`, `failed`, `rejected`, `expired`.
- Transport/observability-статусы (owner: `scheduler`, источник истины: `scheduler_logs` reconcile):
  - `timeout`, `not_found`.

Инварианты owner-модели:
1. `automation-engine` не возвращает транспортные статусы `timeout|not_found` в `GET /scheduler/task/{task_id}`.
2. `scheduler` не интерпретирует transport-статусы как business outcome automation-layer.
3. UI/аналитика обязаны трактовать `timeout|not_found` как транспортную деградацию планировщика, а не как решение decision-layer.

## 2.4 События и наблюдаемость (as-is)

Что реально публикуется:

- `scheduler`:
  - `SCHEDULE_TASK_ACCEPTED`
  - `SCHEDULE_TASK_COMPLETED`
  - `SCHEDULE_TASK_FAILED`

- `automation-engine / scheduler_task_executor`:
  - `TASK_RECEIVED`
  - `TASK_STARTED`
  - `DECISION_MADE`
  - `COMMAND_DISPATCHED`
  - `COMMAND_FAILED`
  - `COMMAND_EFFECT_NOT_CONFIRMED`
  - `TASK_FINISHED`
  - `SCHEDULE_TASK_EXECUTION_STARTED`
  - `SCHEDULE_TASK_EXECUTION_FINISHED`
  - `DIAGNOSTICS_SERVICE_UNAVAILABLE`

Ограничения текущей реализации (после апдейта 2026-02-10):
- task-события `event_id/event_seq` публикуются из `automation-engine`, но не все legacy события нормализованы;
- Laravel API уже отдает `timeline[]` из `zone_events` для `GET /api/zones/{zone}/scheduler-tasks/{taskId}`
  (и опционально для списка через `include_timeline=1`), UI рендерит lifecycle/timeline/SLA в `ZoneAutomationTab`,
  browser e2e сценарий для SLA/timeline добавлен (`tests/e2e/browser/specs/03-zone-detail.spec.ts`);
- в `automation-engine` реализован startup recovery scanner:
  latest snapshot задач со статусами `accepted|running` после рестарта финализируется как `failed`
  (`error_code=task_recovered_after_restart`) для исключения “зависших” lifecycle;
- в `scheduler` реализован startup recovery scanner:
  latest snapshot задач со статусом `accepted` после рестарта поднимается в `_ACTIVE_TASKS`,
  после чего reconcile доводит задачу до terminal `completed|failed|timeout|not_found`;
- сценарий refill/tank-cycle реализован в `SchedulerTaskExecutor` (events: `CYCLE_START_*`, `TANK_*`, `SELF_TASK_ENQUEUED`);
  recovery/chaos сценарии lease-loss/restart покрыты docker-скриптами в `tests/e2e/scheduler/*`.

## 2.5 Что уже соответствует целевой идее

- scheduler больше не отправляет device-level команды напрямую.
- scheduler работает как планировщик и передает intent в `automation-engine`.
- laravel/UI уже умеют читать lifecycle задач по зоне.

---

## 3. Findings: ключевые проблемы и риски

## 3.1 Критические (P1)

1. Документ v2.1 смешивал `to-be` и `as-is` как «рабочий контракт».  
Результат: архитектурная неоднозначность для разработки и тестов.

2. Закрыто в v3.1: endpoint-ы bootstrap/internal enqueue реализованы и отражены в as-is контракте.

3. Закрыто в v3.1: `correlation_id` обязателен, работает dedupe и `payload_mismatch` контроль.

## 3.2 Высокие (P2)

1. Закрыто в v3.2: owner-модель статусов зафиксирована
   (`accepted|running|completed|failed|rejected|expired` vs `timeout|not_found`).

2. Закрыто в v3.2: decision outcome для terminal `completed` формализован
   (`action_required/decision/reason_code`).

3. Закрыто в v3.2: task-event контракт для фронта формализован (обязательные поля timeline).

## 3.3 Средние (P3)

1. Закрыто в v3.2: `error_code/reason_code` унифицированы в task-result для API-level failure веток
   (`command_bus_unavailable`, `execution_exception`, fallback `task_execution_failed`).
2. Закрыто в v3.4: recovery-гарантии покрыты для обоих сервисов:
   `automation-engine` (`accepted|running` -> terminal `failed`) и `scheduler` (`accepted` -> reconcile terminal),
   добавлены docker chaos проверки restart/failover (`tests/e2e/scheduler/*`).

---

## 4. Target (to-be): целевая архитектура

## 4.1 Главный принцип

`automation-engine` — главный оркестратор автоматизации.

Это означает:
1. `automation-engine` инициализирует запуск `scheduler`.
2. `scheduler` только планирует и отправляет intent-задачи.
3. `automation-engine` принимает решение «исполнять/не исполнять» на основе телеметрии и состояния системы.
4. `automation-engine` всегда возвращает явный outcome задачи.

## 4.2 Границы ответственности

- `scheduler`:
  - формирование расписаний;
  - dispatch абстрактных task intent;
  - контроль lifecycle задач на уровне планировщика.

- `automation-engine`:
  - прием task intent;
  - decision layer;
  - исполнение команд через `CommandBus`;
  - safety/аварийная логика;
  - коррекции и контроль параметров;
  - возврат финального outcome.

- `laravel + ui`:
  - отображение lifecycle и timeline событий задачи;
  - отображение причины skip/run/retry/fail.

---

## 5. Target task contract (to-be)

## 5.1 POST /scheduler/task request (to-be)

```json
{
  "protocol_version": "2.0",
  "correlation_id": "sch:zone-28:irrigation:2026-02-10T10:00:00Z",
  "zone_id": 28,
  "task_type": "irrigation",
  "scheduled_for": "2026-02-10T10:00:00Z",
  "due_at": "2026-02-10T10:00:15Z",
  "expires_at": "2026-02-10T10:02:00Z",
  "payload": {
    "trigger_time": "2026-02-10T10:00:00Z",
    "schedule_key": "zone:28|type:irrigation|interval=1200",
    "targets": {},
    "config": {}
  }
}
```

Требования:
- `correlation_id` обязателен.
- идемпотентность по `correlation_id` + контролю payload mismatch.
- `due_at/expires_at` обязательны для детерминированного timeout/fail-fast.

## 5.2 GET /scheduler/task/{task_id} response (to-be)

```json
{
  "status": "ok",
  "data": {
    "task_id": "st-...",
    "zone_id": 28,
    "task_type": "irrigation",
    "status": "completed",
    "scheduled_for": "2026-02-10T10:00:00Z",
    "correlation_id": "sch:zone-28:irrigation:2026-02-10T10:00:00Z",
    "result": {
      "action_required": false,
      "decision": "skip",
      "reason_code": "irrigation_not_required",
      "reason": "Влажность субстрата в целевом диапазоне",
      "commands_total": 0,
      "commands_failed": 0
    },
    "error": null,
    "error_code": null
  }
}
```

Инвариант:
- если действие не нужно, задача все равно terminal как `completed`, но с `action_required=false`.

---

## 6. Startup-handshake (to-be)

## 6.1 Endpoint-ы

- `POST /scheduler/bootstrap` (scheduler -> automation-engine)
- `POST /scheduler/bootstrap/heartbeat`

Назначение:
- scheduler начинает dispatch только после `bootstrap_status=ready`.
- `automation-engine` управляет readiness и lease.

## 6.2 Инварианты handshake

1. Без `ready` dispatch запрещен.
2. Потеря lease переводит scheduler в safe mode.
3. После рестарта любого из сервисов bootstrap обязателен заново.

## 6.3 Single-leader failover semantics (R2)

Статус: реализовано (unit + service-level + process-level + container-level chaos, `backend/services/scheduler/main.py`).

Инварианты:
1. При `SCHEDULER_LEADER_ELECTION=1` dispatch выполняет только лидер-инстанс scheduler.
2. Лидер определяется через PostgreSQL advisory lock (`pg_try_advisory_lock`) с scope `SCHEDULER_LEADER_LOCK_SCOPE`.
3. Потеря лидерского DB-соединения переводит инстанс в follower-mode и немедленно останавливает dispatch.
4. Повторный захват лидера выполняется с backoff (`SCHEDULER_LEADER_RETRY_BACKOFF_SEC`).

Container-level chaos:
- `tests/e2e/scheduler/scheduler_leader_failover_chaos.sh` проверяет single-leader и takeover после остановки лидера.

Наблюдаемость (anti-silent):
- scheduler публикует diagnostics/alerts при `leader retry backoff`, `bootstrap retry backoff`,
  `bootstrap heartbeat http error`, `bootstrap heartbeat not-ready`, `schedule busy skip`,
  `task status timeout/http/not_found`, `internal enqueue invalid/expired/dispatch_failed`;
- добавлена метрика `scheduler_dispatch_skips_total{reason}` и dispatch-cycle summary service logs.

---

## 7. Логика исполнения (to-be)

## 7.1 Базовый pipeline любой scheduler-задачи

1. `scheduler` отправляет intent.
2. `automation-engine` принимает задачу (`accepted`).
3. `automation-engine` переводит в `running`.
4. Decision layer:
   - `run` если действие действительно нужно;
   - `skip` если действие не требуется;
   - `retry` если требуются повторные попытки;
   - `fail` если выполнение завершено ошибкой.
5. При `run` отправляются device-level команды через `CommandBus`.
6. Возврат terminal-результата в `completed|failed|rejected|expired`.

## 7.2 Обязательный сценарий старта цикла (automation-engine)

`automation-engine` инициирует цикл:

1. Проверка доступности обязательных нод.
2. Проверка баков по датчикам уровня.
3. Если бак чистой воды неполный:
   - команда refill;
   - ожидание подтверждения наполнения;
   - при успехе: завершение шага;
   - при таймауте: alert + service log + task outcome с причиной.

Без долгих блокирующих ожиданий:
- для длительных ожиданий `automation-engine` создает self-task через `scheduler`
  (отложенная проверка через N времени).

## 7.3 Реализованный payload-contract для cycle-start/refill

`task_type=diagnostics`:

- старт цикла:
  - `payload.workflow = "cycle_start"`
- отложенная проверка refill:
  - `payload.workflow = "refill_check"`
  - `payload.refill_started_at` (ISO)
  - `payload.refill_timeout_at` (ISO)
  - `payload.refill_attempt` (int)

Поддерживаемые execution override:
- `payload.config.execution.required_node_types`
- `payload.config.execution.clean_tank_full_threshold`
- `payload.config.execution.refill`:
  - `node_types`
  - `preferred_channels`
  - `channel`
  - `cmd`
  - `duration_sec`
  - `params`
  - `timeout_sec`

Итоги исполнения:
- если бак полный: `completed + decision=skip + reason_code=tank_refill_not_required`
- если бак неполный и timeout не истек: отправка refill-команды + `SELF_TASK_ENQUEUED`
- если timeout истек: `failed + error_code=cycle_start_refill_timeout` + infra alert `infra_tank_refill_timeout`

Для топологии `two_tank_drip_substrate_trays` (актуальный runtime):
- `payload.targets.diagnostics.execution.workflow` поддерживает:
  - `startup`
  - `clean_fill_check`
  - `solution_fill_check`
  - `prepare_recirculation`
  - `prepare_recirculation_check`
  - `irrigation_recovery`
  - `irrigation_recovery_check`
- при `task_type=irrigation` и неуспешной online-коррекции выполняется автоматический переход:
  - `reason_code=online_correction_failed`
  - запуск `irrigation_recovery` с `reason_code=tank_to_tank_correction_started`
  - публикация события `IRRIGATION_ONLINE_CORRECTION_FAILED`.

Нормализованные коды outcome (актуально):
- reason:
  - `task_due_deadline_exceeded`
  - `task_expired`
  - `command_bus_unavailable`
  - `execution_exception`
  - `task_execution_failed`
  - `required_nodes_checked`
  - `tank_level_checked`
  - `tank_refill_required`
  - `tank_refill_started`
  - `tank_refill_in_progress`
  - `tank_refill_completed`
  - `tank_refill_not_required`
  - `cycle_start_blocked_nodes_unavailable`
  - `cycle_start_tank_level_unavailable`
  - `cycle_start_tank_level_stale`
  - `cycle_start_refill_timeout`
  - `cycle_start_refill_command_failed`
  - `cycle_start_self_task_enqueue_failed`
  - `online_correction_failed`
  - `tank_to_tank_correction_started`
  - `clean_fill_started`
  - `clean_fill_in_progress`
  - `clean_fill_completed`
  - `clean_fill_timeout`
  - `clean_fill_retry_started`
  - `solution_fill_started`
  - `solution_fill_in_progress`
  - `solution_fill_completed`
  - `solution_fill_timeout`
  - `prepare_recirculation_started`
  - `prepare_targets_reached`
  - `prepare_targets_not_reached`
  - `irrigation_recovery_started`
  - `irrigation_recovery_recovered`
  - `irrigation_recovery_failed`
  - `irrigation_recovery_degraded`
  - `diagnostics_service_unavailable`
- error:
  - `task_due_deadline_exceeded`
  - `task_expired`
  - `command_bus_unavailable`
  - `execution_exception`
  - `task_execution_failed`
  - `command_publish_failed`
  - `command_send_failed`
  - `command_timeout`
  - `command_error`
  - `command_invalid`
  - `command_busy`
  - `command_no_effect`
  - `command_tracker_unavailable`
  - `command_effect_not_confirmed`
  - `mapping_not_found`
  - `no_online_nodes`
  - `cycle_start_required_nodes_unavailable`
  - `cycle_start_tank_level_unavailable`
  - `cycle_start_tank_level_stale`
  - `cycle_start_refill_timeout`
  - `cycle_start_refill_node_not_found`
  - `cycle_start_refill_command_failed`
  - `cycle_start_self_task_enqueue_failed`
  - `clean_tank_not_filled_timeout`
  - `solution_tank_not_filled_timeout`
  - `two_tank_level_unavailable`
  - `two_tank_level_stale`
  - `two_tank_command_failed`
  - `two_tank_enqueue_failed`
  - `two_tank_channel_not_found`
  - `prepare_npk_ph_target_not_reached`
  - `irrigation_recovery_attempts_exceeded`
  - `diagnostics_service_unavailable`

---

## 8. События для фронтенда (to-be)

## 8.1 Требование

Все значимые действия `automation-engine` при обработке scheduler-task должны быть видны во фронте через события зоны.

## 8.2 Минимальный event contract

Обязательные поля:
- `event_id`
- `event_seq`
- `event_type`
- `occurred_at`
- `zone_id`
- `task_id`
- `correlation_id`
- `task_type`
- `action_required`
- `decision`
- `reason_code`
- `node_uid`/`channel`/`cmd` (если применимо)
- `command_submitted`/`command_effect_confirmed` (если применимо)

## 8.3 Минимальный список событий

- `TASK_RECEIVED`
- `TASK_STARTED`
- `DECISION_MADE`
- `COMMAND_DISPATCHED`
- `COMMAND_FAILED`
- `TASK_FINISHED`
- для сценария баков:
  - `CYCLE_START_INITIATED`
  - `NODES_AVAILABILITY_CHECKED`
  - `TANK_LEVEL_CHECKED`
  - `TANK_REFILL_STARTED`
  - `TANK_REFILL_COMPLETED`
  - `TANK_REFILL_TIMEOUT`
  - `SELF_TASK_ENQUEUED`
  - `IRRIGATION_ONLINE_CORRECTION_FAILED`

## 8.4 Порядок сортировки timeline (фиксировано, R0)

Норматив для API/UI:
1. Backend возвращает `timeline[]` в стабильном порядке `created_at ASC`, затем `id ASC`
   (эквивалент: `occurred_at ASC`, при равенстве — по внутреннему идентификатору события).
2. `event_seq` используется как семантический sequence-id события и не должен ломать стабильность выдачи.
3. UI не должен переупорядочивать timeline; допускается только отображение в порядке, полученном от API.

---

## 9. Матрица разрывов (as-is -> to-be)

| Область | As-Is | To-Be | Приоритет |
|---|---|---|---|
| Startup handshake | реализован (`/scheduler/bootstrap`, `/scheduler/bootstrap/heartbeat`) + readiness-gate (`CommandBus+DB+lease-store`) + chaos-проверки lease/restart recovery | chaos suite подключен в отдельный CI stage `scheduler-chaos` | P1 |
| Single-leader scheduler | реализован feature-flag путь (`pg advisory lock`, follower safe-mode, reconnect backoff) + unit/service-level/process-level/container-level chaos failover | выполнять regression прогоны chaos-suite в CI | P1 |
| Idempotency | реализован (`correlation_id` required + payload mismatch) | расширить observability dedupe hit-rate | P1 |
| Decision layer | реализован (structured result + run/skip/retry/fail + normalized failure fallback) | UI labels/локализация reason_code | P2 |
| error_code | реализован в snapshot/API + унифицирован для API-level failure веток | поддерживать словарь при новых workflow | P3 |
| Event timeline | реализован базовый timeline + tank/refill events + SLA-render в ZoneAutomationTab + browser e2e UI-сценарий | расширить операторские пресеты при добавлении новых workflow | P2 |
| Self-task enqueue | реализован (`/scheduler/internal/enqueue` + scheduler scan/dispatched) + anti-silent diagnostics | расширить сценарии ретраев/backoff | P2 |
| Tank refill workflow | реализован в diagnostics workflow (`cycle_start/refill_check`) | расширить policy (retries/backoff/limits) | P2 |

---

## 10. План внедрения (порядок реализации)

1. **Документировать и зафиксировать as-is** (сделано).  
2. **Startup-handshake** (`/scheduler/bootstrap`, `/scheduler/bootstrap/heartbeat`) — реализовано.  
3. **Mandatory `correlation_id` + persistent dedupe** — реализовано.  
4. **Decision layer + structured result** — реализовано.  
5. **`error_code` в snapshot/API** — реализовано, унификация словаря кодов закрыта для текущих веток.  
6. **AE -> scheduler internal enqueue** — реализовано.  
7. **Task timeline contract + детальные события** — реализовано в backend, базовый UI polishing выполнен (ZoneAutomationTab).  
8. **Доработать laravel/UI** для отображения timeline + reason_code/decision + SLA — реализовано в ZoneAutomationTab и подтверждено browser e2e (`03-zone-detail.spec.ts`).  
9. **Обновить API и data model документацию** по факту внедрения — выполнено в v3.2.  

---

## 11. Стратегия тестирования

## 11.1 Unit

Покрыть:
- decision layer (`run/skip/retry/fail`);
- idempotency (`duplicate` / `payload_mismatch`);
- генерацию structured result;
- event builder (`event_seq`, обязательные поля);
- tank refill decision/timeout logic.

Файлы:
- `backend/services/automation-engine/test_scheduler_task_executor.py`
- `backend/services/automation-engine/test_api.py`
- новые unit для decision/self-task.

## 11.2 Feature/Integration

Покрыть:
- bootstrap handshake и safe mode scheduler;
- task lifecycle end-to-end между scheduler и automation-engine;
- laravel proxy контракт;
- internal enqueue сценарий self-task.

Файлы:
- `backend/services/scheduler/test_main.py`
- `backend/services/automation-engine/test_api.py`
- `backend/laravel/tests/Feature/SchedulerTaskControllerTest.php`

## 11.3 E2E

Обязательные сценарии:
1. `completed + action_required=false` (например, полив не требуется).
2. refill success.
3. refill timeout + alert + self-task enqueue.
4. lease lost/re-bootstrap/recovery.

Файлы:
- `backend/laravel/tests/e2e/*`

---

## 12. Синхронизация документации

После каждого шага рефакторинга синхронизировать:

- `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
- `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
- при изменении событий/потоков — разделы по frontend realtime.
