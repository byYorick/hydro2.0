# Схема Scheduler -> Automation-Engine: аудит, целевая модель и план внедрения (v3.1)

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
  - при `show` сначала пробует статус из `automation-engine`, затем fallback из `scheduler_logs`.

## 2.2 Реально существующие endpoint-ы

### automation-engine

- `POST /scheduler/task`
- `GET /scheduler/task/{task_id}`
- `POST /scheduler/bootstrap`
- `POST /scheduler/bootstrap/heartbeat`
- `POST /scheduler/internal/enqueue`
- `GET /health`
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
- `due_at`, `expires_at` поддерживаются (опционально), используются scheduler для дедлайнов.
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
    "correlation_id": "sch:z28:irrigation:abc123def456",
    "result": null,
    "error": null
  }
}
```

### Статусы (as-is)

- В `automation-engine` задача проходит: `accepted -> running -> completed|failed`.
- В `scheduler` дополнительно есть локальные транспортные/наблюдательные terminal-состояния:
  - `timeout`
  - `not_found`

Важно: сейчас нет строгого формального разделения бизнес-статусов и транспортных статусов на уровне контракта.

## 2.4 События и наблюдаемость (as-is)

Что реально публикуется:

- `scheduler`:
  - `SCHEDULE_TASK_ACCEPTED`
  - `SCHEDULE_TASK_COMPLETED`
  - `SCHEDULE_TASK_FAILED`

- `automation-engine / scheduler_task_executor`:
  - `SCHEDULE_TASK_EXECUTION_STARTED`
  - `SCHEDULE_TASK_EXECUTION_FINISHED`
  - иногда `SCHEDULE_TASK_FALLBACK_EVENT_ONLY`, `SCHEDULE_DIAGNOSTICS_REQUESTED`

Ограничения текущей реализации (после апдейта 2026-02-10):
- task-события `event_id/event_seq` публикуются из `automation-engine`, но не все legacy события нормализованы;
- Laravel API уже отдает `timeline[]` из `zone_events` для `GET /api/zones/{zone}/scheduler-tasks/{taskId}`
  (и опционально для списка через `include_timeline=1`), но UI покрывает только базовый рендер;
- сценарий refill/tank-cycle реализован в `SchedulerTaskExecutor` (events: `CYCLE_START_*`, `TANK_*`, `SELF_TASK_ENQUEUED`),
  но e2e-покрытие фронта еще не завершено.

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

1. Нет формального owner-моделя для статусов (business vs transport).  
Риск: UI/аналитика трактует транспортные ошибки как бизнес-ошибки автоматики.

2. Нет обязательного decision outcome при `completed` (почему выполнено/почему скип).

3. Нет формального task-event контракта для фронта (таймлайн действий automation-engine).

## 3.3 Средние (P3)

1. `error_code` добавлен в snapshot/API; требуется выравнивание кодов по всем failure-веткам.
2. Нет lifecycle-гарантий на случай restart и сетевых сбоев (as-is описано частично, но не формализовано).

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
  - отображение причины skip/execute.

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

---

## 7. Логика исполнения (to-be)

## 7.1 Базовый pipeline любой scheduler-задачи

1. `scheduler` отправляет intent.
2. `automation-engine` принимает задачу (`accepted`).
3. `automation-engine` переводит в `running`.
4. Decision layer:
   - `execute` если действие действительно нужно;
   - `skip` если действие не требуется.
5. При `execute` отправляются device-level команды через `CommandBus`.
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

Нормализованные коды outcome (актуально):
- reason:
  - `required_nodes_checked`
  - `tank_level_checked`
  - `tank_refill_required`
  - `tank_refill_started`
  - `tank_refill_in_progress`
  - `tank_refill_completed`
  - `tank_refill_not_required`
  - `cycle_start_blocked_nodes_unavailable`
  - `cycle_start_tank_level_unavailable`
  - `cycle_start_refill_timeout`
  - `cycle_start_refill_command_failed`
  - `cycle_start_self_task_enqueue_failed`
- error:
  - `command_publish_failed`
  - `mapping_not_found`
  - `no_online_nodes`
  - `cycle_start_required_nodes_unavailable`
  - `cycle_start_tank_level_unavailable`
  - `cycle_start_refill_timeout`
  - `cycle_start_refill_node_not_found`
  - `cycle_start_refill_command_failed`
  - `cycle_start_self_task_enqueue_failed`

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

---

## 9. Матрица разрывов (as-is -> to-be)

| Область | As-Is | To-Be | Приоритет |
|---|---|---|---|
| Startup handshake | реализован (`/scheduler/bootstrap`, `/scheduler/bootstrap/heartbeat`) | hardening: lease-loss recovery e2e | P1 |
| Idempotency | реализован (`correlation_id` required + payload mismatch) | расширить observability dedupe hit-rate | P1 |
| Decision layer | реализован (structured result + skip/execute) | унифицировать reason_code taxonomy | P1 |
| error_code | реализован в snapshot/API | доравнять коды во всех failure-ветках | P2 |
| Event timeline | реализован базовый timeline + tank/refill events | финальная нормализация frontend render + SLA | P2 |
| Self-task enqueue | реализован (`/scheduler/internal/enqueue` + scheduler scan/dispatched) | e2e сценарии восстановления после рестарта | P2 |
| Tank refill workflow | реализован в diagnostics workflow (`cycle_start/refill_check`) | расширить policy (retries/backoff/limits) | P2 |

---

## 10. План внедрения (порядок реализации)

1. **Документировать и зафиксировать as-is** (сделано).  
2. **Startup-handshake** (`/scheduler/bootstrap`, `/scheduler/bootstrap/heartbeat`) — реализовано.  
3. **Mandatory `correlation_id` + persistent dedupe** — реализовано.  
4. **Decision layer + structured result** — реализовано.  
5. **`error_code` в snapshot/API** — реализовано, требуется унификация словаря кодов.  
6. **AE -> scheduler internal enqueue** — реализовано.  
7. **Task timeline contract + детальные события** — реализовано в backend, требуется финальный UI polishing/e2e.  
8. **Доработать laravel/UI** для отображения timeline + reason_code/decision.  
9. **Обновить API и data model документацию** по факту внедрения.  

---

## 11. Стратегия тестирования

## 11.1 Unit

Покрыть:
- decision layer (`execute/skip`);
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
- laravel proxy/fallback контракт;
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
