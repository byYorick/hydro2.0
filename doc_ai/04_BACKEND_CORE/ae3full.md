# AE3FULL: Канонический план реализации Automation Engine v3

**Версия:** 2.0-canonical
**Дата:** 2026-03-06
**Статус:** MASTER IMPLEMENTATION PLAN (ready for development)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

> **Это единственный нормативный документ AE3.** `AE3_B.md`, `AE3_C.md`, `AE3_ARCHITECTURE.md` — исторические черновики, при конфликте приоритет у этого файла.

---

## 0. Назначение

Единый план эволюции AE от AE2-Lite до AE3:
1. DDD/OOP/Clean Architecture без разрыва живых контрактов.
2. Durable task runtime с distributed single-writer.
3. Strict closed-loop command confirmation.
4. Phased cutover с rollback gates.

---

## 1. Неподвижные инварианты (нельзя нарушать ни в одной фазе)

1. Командный путь: `Scheduler → AE → history-logger → MQTT → ESP32`.
2. Прямой MQTT publish из Laravel/AE запрещён.
3. Внешний wake-up до cutover: только `POST /zones/{id}/start-cycle`.
4. Для зоны одновременно только один активный writer.
5. Для `(node_uid, channel)` одновременно только одна in-flight команда.
6. Workflow mutating переход — только после terminal command outcome.
7. Все изменения БД только через Laravel migrations.
8. В `prod` closed-loop disable запрещён — startup fail-fast.
9. Все SLA/deadline/lease вычисления используют DB time (`NOW()`), не process clock.

---

## 2. Source of Truth (нормативный код)

1. `backend/laravel/app/Services/AutomationScheduler/SchedulerConstants.php`
2. `backend/laravel/app/Services/AutomationScheduler/ActiveTaskPoller.php`
3. `backend/services/automation-engine/ae2lite/api_contracts.py`
4. `backend/services/automation-engine/ae2lite/api_intents.py`
5. `backend/services/automation-engine/ae2lite/api_runtime_concurrency.py`
6. `backend/services/automation-engine/config/scheduler_task_mapping.py`
7. `backend/services/automation-engine/infrastructure/command_tracker_runtime.py`
8. `backend/services/automation-engine/executor/executor_constants.py`
9. `backend/services/automation-engine/services/pid_state_manager.py`
10. `backend/services/automation-engine/domain/workflows/two_tank.py`
11. `backend/services/automation-engine/domain/workflows/three_tank.py` ← существует, учитывать при миграции
12. `doc_ai/03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`

---

## 3. Живой контракт, который нельзя ломать

### 3.1 Scheduler ingress

- `task_type` (legacy, до cutover): `irrigation|lighting|ventilation|solution_change|mist|diagnostics`.
- Wake-up endpoint: `POST /zones/{id}/start-cycle`.
- Poller использует `task_id=intent-<id>` и словарь: `accepted|completed|failed|cancelled|not_found`.
- Poller fallback: lookup в `scheduler_logs` для non-intent task_id.

### 3.2 Single-writer baseline

- Текущие флаги: `AE2_RUNTIME_SINGLE_WRITER_ENFORCE`, `AE2_FALLBACK_LOOP_WRITER_ENABLED`.
- AE3 interlock должен быть согласован с этими флагами.

### 3.3 Command baseline

- Публикация только через `history-logger /commands`.
- Node-level статусы: `ACK|DONE|ERROR|INVALID|BUSY|NO_EFFECT|TIMEOUT`.
- `SEND_FAILED` — backend/publish-layer, не MQTT node-level.
- Успех actuator-команды = только `DONE`. `NO_EFFECT` = fail.

### 3.4 PID baseline

- Рабочие поля: `last_output_ms`, `last_dose_at`, `prev_derivative`, `current_zone`.
- `pid_state` — persisted source of truth.
- Нельзя rename поля без отдельной migration фазы с dual-read.

### 3.5 Topology baseline

- Prod scope: `two_tank_drip_substrate_trays`.
- `three_tank` — существующий код (`domain/workflows/three_tank.py`), но не активен как runtime. При миграции не потерять.

---

## 4. DDD: стратегический дизайн

### 4.1 Bounded Contexts

1. **Ingress & Bridge Context** — start-cycle, legacy task_type mapping, `intent-<id>` alias.
2. **Task Orchestration Context** — queue, attempts, claim/lease/fence, retries, lifecycle.
3. **Workflow & Topology Context** — FSM фазы, topology-router, guards, transitions.
4. **Command Delivery Context** — command plan, outbox, publish, tracker, outcome gate.
5. **Operations & Control Context** — `auto|semi|manual`, degraded mode, SLO gates.

### 4.2 Context Map

1. Ingress → публикует `TaskRequested` в Orchestration.
2. Orchestration → запрашивает domain decision у Workflow.
3. Orchestration → делегирует command emission в Command Delivery.
4. Command Delivery → возвращает `TerminalOutcome` в Orchestration.
5. Operations читает domain events из всех контекстов.

---

## 5. Ubiquitous Language

| Термин | Определение |
|---|---|
| `Task` | Единица выполнения доменной операции. |
| `Attempt` | Конкретная попытка выполнения Task. |
| `Lease` | Право writer-а на зону с fence-version. |
| `CommandPlan` | Упорядоченный набор шагов `step_no=1..N`. |
| `CommandIntent` | Намерение опубликовать команду (до фактического publish). |
| `TerminalOutcome` | Финальный результат команды (`DONE|NO_EFFECT|...`). |
| `WorkflowTransition` | Переход фазы зоны по валидному событию FSM. |
| `BridgeAlias` | `intent-<id>` ссылка на native task. |
| `SagaCompensation` | Компенсирующая задача при частично успешной цепочке. |

---

## 6. DDD: тактический дизайн

### 6.1 Агрегаты

1. **TaskAggregate**
   - root: `Task`
   - children: `Attempt`, `TaskCommand`
   - инварианты: валидный lifecycle, retry лимиты, atomic `complete + enqueue_next`, compensation tracking.

2. **ZoneExecutionAggregate**
   - root: `ZoneLease`
   - children: `WorkflowStateRef`, `ActuatorLocks`
   - инварианты: single writer (fence), fence-check перед каждым mutating шагом.

3. **CommandAggregate**
   - root: `TaskCommand`
   - children: `OutboxRecord`, `TerminalOutcome`
   - инварианты: intent persisted до publish; terminal outcome обязателен по policy.

4. **BridgeAggregate**
   - root: `IntentBridge`
   - children: `BridgeAlias`
   - инварианты: `intent-<id>` → native task id; poller vocabulary mapping корректен.

### 6.2 Entities

1. `Task(id, task_uid, zone_id, task_type, status, priority, saga_id, compensation_for_task_id, ...)`
2. `TaskAttempt(task_id, attempt_no, status, retryable, error_code, ...)`
3. `ZoneLease(zone_id, owner_id, lease_version, lease_until)`
4. `TaskCommand(task_id, step_no, node_uid, channel, publish_status, terminal_status)`
5. `OutboxRecord(task_command_id, available_at, attempts, published_at)`
6. `ActuatorLock(node_uid, channel, zone_id, task_id, lock_owner, lock_version, lock_until)`

### 6.3 Value Objects

1. `TaskId` — `ae3:<decimal_pk>`
2. `IntentAlias` — `intent-<intent_id>`
3. `IdempotencyKey`
4. `TaskType` (validation against canonical list)
5. `TaskStatus`
6. `CommandStatus`
7. `LeaseVersion`
8. `ControlMode` (`auto|semi|manual`)
9. `TaskSchemaVersion`

### 6.4 Domain Services

1. `LegacyTaskTypeMapper` — legacy → canonical mapping.
2. `TaskAdmissionPolicy` — проверка `ControlMode` + source.
3. `CommandOutcomePolicy` — `done_only`, `done_only_if_emitted`, `no_command_expected`.
4. `WorkflowTransitionPolicy` — valid FSM events per phase.
5. `LeaseConflictPolicy` — CAS conditions, backoff class.
6. `TaskSchemaVersionPolicy` — version N / N-1 support.
7. `SagaCompensationPolicy` — когда и какую compensating task ставить.

### 6.5 Domain Events

`TaskRequested`, `TaskLeased`, `TaskExecutionStarted`, `CommandIntentPersisted`,
`CommandPublished`, `CommandTerminalObserved`, `WorkflowTransitionApplied`,
`TaskCompleted`, `TaskFailed`, `TaskConflict`, `LeaseFenceLost`,
`ActuatorLockConflict`, `SagaCompensationRequired`.

---

## 7. OOP + Clean Code правила

1. SOLID обязательны для всех новых модулей.
2. Domain слой не импортирует infrastructure/transport.
3. Все зависимости domain/application — через ports (интерфейсы).
4. Метод > 30 строк → refactor/extract method.
5. Конструкторы без I/O и hidden side-effects.
6. Никаких static god helpers для доменной логики.
7. Исключения только typed: `DomainError`, `ConcurrencyError`, `ExternalDependencyError`.
8. Один класс — одна причина изменения.
9. Repositories возвращают domain objects, не сырые dict.
10. Non-trivial if-chain в policies → explicit Strategy/State.

---

## 8. Application Layer (Use Cases)

1. `StartCycleUseCase(zone_id, idempotency_key, source)` → `task_id=intent-<id>` до cutover.
2. `EnqueueTaskUseCase` — validate envelope, persist, emit `pg_notify`.
3. `ClaimTaskUseCase` — `FOR UPDATE SKIP LOCKED`, reserve attempt, set `leased_until`.
4. `ExecuteLeasedTaskUseCase` — acquire zone lease, load ZoneContext snapshot, build command plan, enforce workflow policy.
5. `RecoverStaleTaskUseCase` — reconcile in-progress steps перед resume (см. §10.4).
6. `AwaitCommandOutcomeUseCase` — ждёт terminal для всех steps, применяет policy.
7. `FinalizeTaskUseCase` — атомарная транзакция: result + workflow + next_tasks + notify.
8. `EnqueueSagaCompensationUseCase` — при partial success ставит compensating task P0_SAFETY.
9. `RetryTaskUseCase` — operator/manual only, audit mandatory.
10. `ResolveTaskStatusUseCase` — принимает `ae3:<id>` и `intent-<id>`.

---

## 9. Ports and Adapters

### 9.1 Primary Ports (inbound)

`StartCyclePort`, `TaskEnqueuePort`, `TaskRetryPort`, `TaskStatusQueryPort`, `ControlModePort`.

### 9.2 Secondary Ports (outbound)

`TaskRepositoryPort`, `LeaseRepositoryPort`, `WorkflowRepositoryPort`,
`CommandRepositoryPort`, `OutboxRepositoryPort`, `ActuatorLockRepositoryPort`,
`HistoryLoggerClientPort`, `TelemetryReadModelPort`, `EventBusPort` (LISTEN/NOTIFY), `ClockPort`.

### 9.3 Adapters

1. FastAPI controllers (inbound).
2. PostgreSQL repositories (outbound).
3. history-logger REST adapter.
4. PG LISTEN/NOTIFY adapter — **dedicated persistent connection**, отдельная от пула (см. §10.7).
5. Prometheus/structlog adapter.

---

## 10. Канонические runtime-алгоритмы

### 10.1 Worker wake-up

1. Enqueue commit → `pg_notify('ae_task_enqueued', '{"zone_id": N, "task_uid": "ae3:..."}')`.
2. Worker: `LISTEN ae_task_enqueued`.
3. Fallback polling при деградации notify:
   - `TASK_POLL_INTERVAL_SEC=2` (idle default)
   - `TASK_POLL_MAX_INTERVAL_SEC=15` (adaptive backoff max)
   - jitter 10%

### 10.2 Lease timing

| Параметр | Значение | Правило |
|---|---|---|
| `ZONE_LEASE_TTL_SEC` | 180 | — |
| `ZONE_LEASE_HEARTBEAT_SEC` | 15 | обязательно `< TTL/3` |
| `COMMAND_TERMINAL_TIMEOUT_SEC` | 60 | обязательно `< LEASE_TTL - 2*HEARTBEAT` |
| `ACTUATOR_LOCK_TTL_SEC` | 90 | обязательно `>= COMMAND_TERMINAL_TIMEOUT_SEC + 20` |

**Zone lease CAS:**
```sql
UPDATE ae_zone_leases
SET owner_id = :new_owner, lease_version = lease_version + 1,
    lease_until = NOW() + :ttl_interval, updated_at = NOW()
WHERE zone_id = :zone_id
  AND (lease_until < NOW() OR owner_id = :new_owner);
```
Если `rows_affected = 0` → `zone_lease_conflict`.

**Heartbeat:**
```sql
UPDATE ae_zone_leases
SET lease_until = NOW() + :ttl_interval, updated_at = NOW()
WHERE zone_id = :zone_id AND lease_version = :expected_version;
```
Если `rows_affected = 0` → `LeaseFenceLost`.

### 10.3 Multi-command FSM (`waiting_command`)

Переходы для `step_no = 1..N`:

```
running → waiting_command(step 1)
waiting_command(step i) + DONE → running(step i+1)
waiting_command(step N) + DONE → completed
waiting_command(step i) + terminal != DONE → failed
```

Прогресс хранится в `ae_task_commands(task_id, step_no, terminal_status)`. In-memory счётчик — не source of truth.

### 10.4 Recovery из stale `waiting_command` (обязательный алгоритм)

При claim задачи в статусе `leased` (stale после `lease_until < NOW()`):

1. Найти текущий attempt в `ae_task_attempts`.
2. Найти шаг с `terminal_status IS NULL` в `ae_task_commands`.
3. **Reconcile перед republish:**
   - Если `command_id IS NOT NULL` → запросить статус у history-logger: `GET /commands/{command_id}/status`.
   - Если terminal получен → записать в `ae_task_commands.terminal_status`, продолжить FSM.
   - Если ещё non-terminal → resume `AwaitCommandOutcomeUseCase`.
4. Если `command_id IS NULL` (`publish_requested`, не принят) → republish через outbox (безопасно: `task_command_id UNIQUE` защищает от дублей в outbox).
5. Если history-logger недоступен → задача получает `transient_io` retry, `retryable=true`.

**Инвариант:** никогда не повторно publish без предварительного reconcile при наличии `command_id`.

### 10.5 Actuator lock CAS

**Захват:**
```sql
INSERT INTO ae_actuator_locks
  (node_uid, channel, zone_id, task_id, lock_owner, lock_version, lock_until, updated_at)
VALUES (...)
ON CONFLICT (node_uid, channel) DO UPDATE
SET zone_id = EXCLUDED.zone_id,
    task_id = EXCLUDED.task_id,
    lock_owner = EXCLUDED.lock_owner,
    lock_version = ae_actuator_locks.lock_version + 1,
    lock_until = NOW() + :actuator_lock_ttl_interval,
    updated_at = NOW()
WHERE ae_actuator_locks.lock_until < NOW();
```
Если `rows_affected = 0` → `actuator_busy`, retry по contention policy.

**Освобождение:**
```sql
DELETE FROM ae_actuator_locks
WHERE node_uid = :node_uid AND channel = :channel AND task_id = :task_id;
```

**Watchdog cleanup** (`ACTUATOR_LOCK_TTL_SEC`): при запуске и периодически `DELETE FROM ae_actuator_locks WHERE lock_until < NOW()`.

### 10.6 Idempotency key format

| Источник | Формат |
|---|---|
| Scheduler wake-up | `sch:{zone_id}:{task_type}:{iso_minute}` |
| Planner next_task | `ae3:{parent_task_uid}:next:{task_type}:{step_index}` |
| Manual API | `manual:{zone_id}:{task_type}:{actor}:{iso_second}` |
| Saga compensation | `ae3:{parent_task_uid}:comp:{task_type}` |
| Safety tick | `safety:{zone_id}:{task_type}:{iso_minute}` |

Все ключи детерминированы — безопасны при crash-recovery replay.

### 10.7 LISTEN/NOTIFY connection

1. **Dedicated persistent connection** — отдельная asyncpg connection, не из пула.
2. Reconnect при потере: exponential backoff `1s → 2s → 4s → max 30s`.
3. После reconnect: немедленно полный scan `pending|leased` задач перед возвратом в `LISTEN` — компенсация missed notifications за время disconnect.
4. Метрика: `ae_notify_reconnect_total`, `ae_notify_lag_seconds`.
5. Если notify lag > `NOTIFY_LAG_ALERT_SEC=10` → alert + переключение в polling-first.

### 10.8 Clock policy

| Поле | Источник времени |
|---|---|
| `scheduled_for` (из scheduler) | Process clock Laravel; принимается as-is |
| `due_at`, `expires_at` (вычисляются AE) | `DB NOW()` |
| `created_at`, `updated_at` | `DB NOW()` |
| Lease/deadline comparisons | `DB NOW()` только |
| `CLOCK_SKEW_MAX_SEC=5` | Максимально допустимый drift `scheduled_for` vs `DB NOW()` при enqueue |

Если `|scheduled_for - DB NOW()| > CLOCK_SKEW_MAX_SEC` при enqueue → логировать `clock_skew_detected`, продолжать (не reject).

### 10.9 Atomic finalize

В одной DB транзакции:
```
1. UPDATE ae_tasks SET status='completed', completed_at=NOW() WHERE id=:id AND attempt_no=:attempt
2. UPDATE zone_workflow_state SET workflow_phase=:new_phase, version=version+1, ... WHERE zone_id=:id AND version=:expected
3. INSERT INTO ae_tasks (...) VALUES (next_task_1), (next_task_2), ...
4. SELECT pg_notify('ae_task_enqueued', ...)
```
Если строка 2 затрагивает 0 строк → `workflow_version_conflict`, rollback всей транзакции.

### 10.10 Contention policy

| Класс | Причина | Backoff | Max retries |
|---|---|---|---|
| `transient_io` | `db_timeout`, `history_logger_unavailable` | exp: `base=2s, factor=2, max=60s` | `TASK_MAX_ATTEMPTS=3` |
| `contention` | `zone_lease_conflict`, `actuator_busy`, `workflow_version_conflict` | jitter: `base=1s, factor=2, max=30s, jitter=20%` | 8 |
| `command_timeout` | terminal timeout | reconcile + retry | `TASK_MAX_ATTEMPTS` |
| `business_skip` | stale telemetry, flow_inactive | no retry | 0 |
| `fatal` | unknown_task_type, invalid_payload | no retry | 0 |

После исчерпания → `is_dead_letter=true` в `ae_task_attempts`, operator intervention required.

### 10.11 Saga compensation policy

При partial success многошаговых цепочек (`irrigation_start → irrigation_stop → recirculation_*`):

1. Если `irrigation_start` = DONE, но следующий critical step = failed → `SagaCompensationPolicy` принимает решение.
2. `EnqueueSagaCompensationUseCase` создаёт compensating task в `ae_tasks`:
   - `priority = P0_SAFETY (0)`
   - `idempotency_key = ae3:{parent_task_uid}:comp:{task_type}`
   - `compensation_for_task_id = :failed_task_id`
   - `saga_id = :parent_saga_id`
3. Compensation task выполняется по обычному worker-loop, но не может быть отменена оператором.
4. Если compensation сама failed → `SAFETY_VIOLATION` event + alert, operator escalation.
5. Не требует отдельной таблицы — `ae_tasks.saga_id` + `ae_tasks.compensation_for_task_id` достаточно для tracking.

### 10.12 Priority + anti-starvation

Очередь сортируется: `(priority ASC, due_at ASC, created_at ASC)`.

Приоритеты:
- `P0_SAFETY = 0` — compensation, emergency recovery.
- `P1_CONTROL = 1` — correction_*, irrigation_*, workflow_step.
- `P2_MAINTENANCE = 2` — health_check, climate_check, lighting_check.

Anti-starvation: после `ANTISTARVATION_MAX_CONSECUTIVE=10` подряд P1_CONTROL задач — принудительно взять overdue P2_MAINTENANCE задачу, если есть.

### 10.13 `available_at` семантика

`ae_command_outbox.available_at`:
- При первоначальной записи: `available_at = NOW()` (немедленная публикация).
- При retry после publish failure: `available_at = NOW() + backoff_duration`.
- Publisher query: `WHERE published_at IS NULL AND available_at <= NOW() ORDER BY available_at ASC LIMIT :batch`.

---

## 11. Схема данных

### 11.1 Новые таблицы (все через Laravel migrations)

**`ae_tasks`**
```sql
id BIGSERIAL PK
task_uid TEXT UNIQUE NOT NULL          -- 'ae3:<id>'
zone_id BIGINT NOT NULL
task_type TEXT NOT NULL
source TEXT NOT NULL                   -- 'scheduler|planner|manual|safety|compensation'
status TEXT NOT NULL                   -- pending|leased|running|waiting_command|completed|skipped|failed|conflict|expired|cancelled
priority SMALLINT NOT NULL             -- 0=P0_SAFETY, 1=P1_CONTROL, 2=P2_MAINTENANCE
payload JSONB NOT NULL
task_schema_version INT NOT NULL
idempotency_key TEXT UNIQUE NOT NULL
scheduled_for TIMESTAMPTZ NOT NULL
due_at TIMESTAMPTZ NOT NULL
expires_at TIMESTAMPTZ NOT NULL        -- expires_at > due_at >= scheduled_for
max_attempts INT NOT NULL
attempt_no INT NOT NULL DEFAULT 0
leased_until TIMESTAMPTZ NULL          -- set on claim, cleared on finalize/fail
root_intent_id BIGINT NULL REFERENCES zone_automation_intents(id)
saga_id TEXT NULL                      -- groups saga chain tasks
compensation_for_task_id BIGINT NULL REFERENCES ae_tasks(id)
error_code TEXT NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
completed_at TIMESTAMPTZ NULL
```

**`ae_task_attempts`**
```sql
id BIGSERIAL PK
task_id BIGINT NOT NULL REFERENCES ae_tasks(id)
attempt_no INT NOT NULL
status TEXT NOT NULL
retryable BOOLEAN NOT NULL
error_code TEXT NULL
error_message TEXT NULL
is_dead_letter BOOLEAN NOT NULL DEFAULT false
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
finished_at TIMESTAMPTZ NULL
UNIQUE(task_id, attempt_no)
```

**`ae_zone_leases`**
```sql
zone_id BIGINT PK
owner_id TEXT NOT NULL
lease_version BIGINT NOT NULL
lease_until TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
```

**`ae_task_commands`**
```sql
id BIGSERIAL PK
task_id BIGINT NOT NULL REFERENCES ae_tasks(id)
step_no INT NOT NULL
node_uid TEXT NOT NULL
channel TEXT NOT NULL
command_payload JSONB NOT NULL
command_id TEXT NULL                   -- получен от history-logger
publish_status TEXT NOT NULL           -- publish_requested|publish_accepted|publish_failed
terminal_status TEXT NULL              -- DONE|NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED
published_at TIMESTAMPTZ NULL
terminal_at TIMESTAMPTZ NULL
error_code TEXT NULL
UNIQUE(task_id, step_no)
```

**`ae_command_outbox`**
```sql
id BIGSERIAL PK
task_command_id BIGINT UNIQUE NOT NULL REFERENCES ae_task_commands(id)
task_id BIGINT NOT NULL REFERENCES ae_tasks(id)
zone_id BIGINT NOT NULL
payload JSONB NOT NULL
available_at TIMESTAMPTZ NOT NULL      -- NOW() при создании, NOW()+backoff при retry
attempts INT NOT NULL DEFAULT 0
published_at TIMESTAMPTZ NULL
last_error TEXT NULL
```

**`ae_actuator_locks`**
```sql
PRIMARY KEY(node_uid, channel)
node_uid TEXT NOT NULL
channel TEXT NOT NULL
zone_id BIGINT NOT NULL
task_id BIGINT NOT NULL REFERENCES ae_tasks(id)
lock_owner TEXT NOT NULL
lock_version BIGINT NOT NULL
lock_until TIMESTAMPTZ NOT NULL        -- NOW() + ACTUATOR_LOCK_TTL_SEC
updated_at TIMESTAMPTZ NOT NULL
```

### 11.2 Индексы (обязательный минимум)

```sql
-- ae_tasks: hot path
CREATE INDEX ON ae_tasks(status, priority, due_at) WHERE status IN ('pending','leased');
CREATE INDEX ON ae_tasks(zone_id, status);
CREATE INDEX ON ae_tasks(leased_until) WHERE status = 'leased';
CREATE INDEX ON ae_tasks(idempotency_key);  -- UNIQUE уже создаёт

-- ae_task_attempts
CREATE INDEX ON ae_task_attempts(task_id, attempt_no DESC);
CREATE INDEX ON ae_task_attempts(is_dead_letter, created_at) WHERE is_dead_letter = true;

-- ae_task_commands
CREATE INDEX ON ae_task_commands(task_id, step_no);
CREATE INDEX ON ae_task_commands(command_id) WHERE command_id IS NOT NULL;

-- ae_command_outbox: publisher hot path
CREATE INDEX ON ae_command_outbox(available_at, published_at) WHERE published_at IS NULL;

-- ae_actuator_locks: cleanup
CREATE INDEX ON ae_actuator_locks(lock_until);
```

### 11.3 Изменения существующих таблиц

```sql
-- zone_workflow_state: CAS на переходы
ALTER TABLE zone_workflow_state ADD COLUMN version BIGINT NOT NULL DEFAULT 0;

-- zone_automation_intents: bridge link
ALTER TABLE zone_automation_intents ADD COLUMN root_task_id BIGINT NULL REFERENCES ae_tasks(id);

-- pid_state: нормализация (только если поля не существуют)
-- Обязательные поля: last_output_ms, last_dose_at, prev_derivative, current_zone
-- Нельзя rename без отдельной dual-read migration фазы
```

---

## 12. Контракты статусов и ID

### 12.1 Task statuses (lowercase)

`pending → leased → running → waiting_command → completed`

Terminal branches: `skipped | failed | conflict | expired | cancelled`

- `skipped` = бизнес-пропуск по guardrail (stale telemetry, flow_inactive).
- `cancelled` = явная отмена оператором.
- `conflict` = исчерпан лимит contention retries.
- `expired` = `now > expires_at` при попытке lease.

### 12.2 Command statuses (uppercase)

Non-terminal: `QUEUED | SENT | ACK`

Terminal: `DONE | NO_EFFECT | ERROR | INVALID | BUSY | TIMEOUT | SEND_FAILED`

- `SEND_FAILED` — только backend/publish layer (не MQTT node).
- Actuator успех = только `DONE`.

### 12.3 Poller vocabulary (lowercase)

`accepted | completed | failed | cancelled | not_found`

Mapping:
- `pending|leased|running|waiting_command` → `accepted`
- `completed|skipped` → `completed`
- `failed|conflict|expired` → `failed`
- `cancelled` → `cancelled`
- отсутствует → `not_found`

### 12.4 Task ID format

- Native: `ae3:<decimal_task_pk>`
- Bridge alias: `intent-<intent_id>`

---

## 13. Command success policy

| task_type | policy | success | fail |
|---|---|---|---|
| `correction_ph`, `correction_ec` | `done_only` | `DONE` | остальные terminal |
| `irrigation_*`, `recirculation_*` | `done_only` | `DONE` | остальные terminal |
| `workflow_step` | `done_only` | `DONE` | остальные terminal |
| `climate_check`, `lighting_check` | `done_only_if_emitted` | `DONE` или `no_command_needed` | остальные terminal |
| `health_check`, `recovery_reconcile` | `no_command_expected` | `no_command_needed` | `ERROR`, `TIMEOUT` |

`done_only_if_emitted`: если контроллер не эмитировал команду (условие не выполнено) → task `completed` со статусом `no_command_needed` без ожидания terminal.

---

## 14. Legacy bridge

### 14.1 task_type mapping

До `ENABLE_SCHEDULER_DIRECT_ENQUEUE=1` scheduler использует только legacy types.
`LegacyTaskTypeMapper` внутри AE конвертирует:

```
irrigation       → irrigation_start / irrigation_stop / recirculation_*
lighting         → lighting_check
ventilation      → climate_check
solution_change  → workflow_step / diagnostics (по phase/router policy)
mist             → climate_check
diagnostics      → diagnostics + workflow_step
```

### 14.2 Poller bridge

1. `POST /zones/{id}/start-cycle` → возвращает `{"task_id": "intent-<id>", ...}`.
2. `GET /internal/tasks/{task_id}` → резолвит native `ae3:*` и alias `intent-*`.
3. Fallback lookup в `scheduler_logs` для non-intent task_id (текущий поллер path).

### 14.3 Dual-run фазы

| Фаза | Source of truth | Действие |
|---|---|---|
| A | `zone_automation_intents` | AE3 пишет `root_task_id` в intents при wake-up |
| B | dual-write | Статусы зеркалируются в обе стороны |
| C | `ae_tasks` | Scheduler poller читает tasks, fallback → intents/logs |
| D | `ae_tasks` | Cutover, alias `intent-*` сохраняется |
| E | — | Deprecate bridge после SLO-stable окна |

Инвариант dual-run: при ошибке mirror-sync → fail-closed **для текущей зоны** (не глобально), retry с backoff `5s/10s/30s`, после исчерпания → `zone_event: BRIDGE_SYNC_FAILED`.

---

## 15. Control Mode (admission matrix)

| task_type class | `auto` | `semi` | `manual` |
|---|---|---|---|
| `diagnostics`, `workflow_step` (FSM transition) | scheduler/planner | **требует operator approve** | manual |
| `irrigation_*`, `recirculation_*` | scheduler/planner | **требует operator approve** | manual |
| `correction_ph`, `correction_ec` | scheduler | scheduler (автоматически) | manual |
| `climate_check`, `lighting_check` | scheduler | scheduler (автоматически) | disabled |
| `health_check` | scheduler | scheduler | scheduler |
| `recovery_reconcile` | safety tick | safety tick | safety tick |
| `compensation` | system (P0) | system (P0) | system (P0) |

**Ключевое уточнение `semi`:** `correction_*` и periodic checks — разрешены без approve (safety-critical, нельзя останавливать). Approve требуется только для workflow FSM transitions и actuator-тяжёлых операций (irrigation, recirculation).

Переключение режима: только `POST /zones/{id}/control-mode` с `{actor, reason, ts}`. После смены — revalidation всех `pending` задач.

---

## 16. Degraded Mode

### 16.1 Компонент

`ae3/degraded_ticker` — отдельный компонент, не основной worker loop.

### 16.2 Механизм активации

AE отслеживает время последнего `POST /zones/*/start-cycle` запроса от scheduler.

```
last_scheduler_call_at → хранится in-memory + persisted в ae_degraded_state (простая KV таблица)
```

Если `NOW() - last_scheduler_call_at > SCHEDULER_STALE_SEC=300` → degraded mode активирован.

| Параметр | Значение |
|---|---|
| `SCHEDULER_STALE_SEC` | 300 |
| `DEGRADED_TICK_SEC` | 60 |

### 16.3 В degraded разрешены только:

- `health_check` (по всем активным зонам)
- `climate_check` (только critical/alert policy)
- `recovery_reconcile` (только при stale running tasks)

Не выполняется: irrigation, corrections, workflow steps.

---

## 17. PID lifecycle в task-модели

1. Каждый `correction_ph/ec` task загружает `pid_state` из БД.
2. `AdaptivePid.compute()`.
3. Сохраняет обновлённое состояние в рамках того же attempt.
4. `AdaptivePid` не живёт между tasks в памяти как source of truth.
5. `min_interval` проверяется по `last_dose_at` + `DB NOW()`.
6. Stale telemetry > `TELEMETRY_MAX_AGE_SEC=300` → task `skipped`, fail-closed.
7. При stale `last_dose_at` (нет в БД) → `last_output_ms=0` + audit log (legacy row).

---

## 18. Topology scope

1. MVP (фазы 0-5): только `two_tank_drip_substrate_trays`.
2. `three_tank` — extension-point:
   - Код существует в `domain/workflows/three_tank.py` → перенести в `ae3/domain/workflow/topologies/three_tank.py` как feature-gated (off по умолчанию).
   - До prod обязательны: shadow execution без side-effects, отдельный rollout RFC, canary gates.
3. Topology-router обязателен: роутинг по `(topology, workflow)`, не `if/elif` цепочка.

---

## 19. Task schema versioning

1. Workers поддерживают version N и N-1.
2. Version > N → `rejected/task_schema_unsupported`.
3. Version < N-1 → `rejected/task_schema_too_old`.
4. При deploy rollback (N → N-1): **pre-drain** — дождаться опустошения очереди задач с version N перед переключением. Порядок:
   - Остановить enqueue новых version=N задач (feature-flag).
   - Дождаться `ae_tasks WHERE task_schema_version=N AND status NOT IN terminal = 0`.
   - Deploy N-1.
5. Version adapters: `ae3/domain/task/version_adapters/v{X}_to_v{Y}.py`, никакого inline.
6. `task_schema_version=1` — текущий canonical payload format (задаётся в фазе 0 Freeze).

---

## 20. Feature Flags

Единый канонический префикс: **``**.

| Флаг | Default | Назначение |
|---|---|---|
| `ENABLE_RUNTIME` | 0 | Включить AE3 runtime (canary zones) |
| `ENABLE_OUTBOX` | 0 | Включить outbox publisher |
| `ENABLE_SCHEDULER_DIRECT_ENQUEUE` | 0 | Разрешить canonical task types от scheduler |
| `ENABLE_CANARY` | 0 | Route-by-zone canary |
| `CLOSED_LOOP_REQUIRED` | 1 | В prod — startup fail-fast если closed-loop off |
| `INTERLOCK_ENFORCE` | 1 | Split-brain защита AE2/AE3 |
| `ZONE_LEASE_TTL_SEC` | 180 | — |
| `ZONE_LEASE_HEARTBEAT_SEC` | 15 | — |
| `COMMAND_TERMINAL_TIMEOUT_SEC` | 60 | — |
| `ACTUATOR_LOCK_TTL_SEC` | 90 | — |
| `TASK_POLL_INTERVAL_SEC` | 2 | Fallback polling idle |
| `TASK_POLL_MAX_INTERVAL_SEC` | 15 | Fallback polling max |
| `TASK_MAX_ATTEMPTS` | 3 | Transient retry limit |
| `SCHEDULER_STALE_SEC` | 300 | Порог активации degraded mode |
| `TELEMETRY_MAX_AGE_SEC` | 300 | Freshness для correction |
| `CLOCK_SKEW_MAX_SEC` | 5 | Допустимый drift scheduled_for vs DB NOW() |
| `ANTISTARVATION_MAX_CONSECUTIVE` | 10 | P1 задач перед anti-starvation P2 |
| `NOTIFY_LAG_ALERT_SEC` | 10 | Порог алерта на notify lag |
| `OUTBOX_PUBLISH_BATCH` | 100 | Batch size outbox publisher |

**Совместимость с AE2:**
- `CLOSED_LOOP_REQUIRED=1` требует `AE_TASK_EXECUTE_CLOSED_LOOP=1`.
- `INTERLOCK_ENFORCE=1` координируется с `AE2_RUNTIME_SINGLE_WRITER_ENFORCE=1`.
- `AE2_FALLBACK_LOOP_WRITER_ENABLED=0` обязателен при активном AE3 runtime.

---

## 21. Фазовый план реализации

### Фаза 0: Contract Freeze (2-3 дня) — Лид: Agent-1

1. Freeze ubiquitous language, enums, task/command status contracts.
2. Freeze DDL draft.
3. Freeze bridge mappings, idempotency key formats.
4. Freeze `task_schema_version=1` payload schemas по каждому task_type.
5. Подписать ownership matrix агентов.

Выход: CI проходит на пустом каркасе пакета `ae3/`.

### Фаза 1: Domain Core (4-6 дней) — Лид: Agent-1

1. Entities, value objects, policies, events.
2. Aggregate invariants.
3. Unit tests domain-first (без I/O).

Выход: 100% unit coverage domain слоя.

### Фаза 2: Application Layer (4-6 дней) — Лид: Agent-2

1. Use cases 1-10 (§8).
2. Unit of Work + transaction boundaries.
3. Contract tests.

Выход: все use-case контракты покрыты тестами с mock ports.

### Фаза 3: Infrastructure Adapters (5-7 дней) — Лид: Agent-3

1. PostgreSQL repositories (migrations в фазе 1).
2. LISTEN/NOTIFY adapter (dedicated connection, reconnect protocol).
3. history-logger REST adapter.
4. Outbox publisher + tracker.
5. Actuator lock manager.
6. Concurrency correctness tests.

Выход: integration tests enqueue/claim/lease/outbox зелёные; fault injection crash-точек пройден.

### Фаза 4: Legacy Bridge + Laravel Integration (4-6 дней) — Лид: Agent-4

1. `start-cycle` + `intent-<id>` compatibility.
2. `LegacyTaskTypeMapper`.
3. Poller bridge + fallback paths.
4. E2E тест: scheduler → start-cycle → task → command → terminal → poller sees `completed`.

Выход: полная backward compatibility для текущего scheduler flow.

### Фаза 5: Canary + Hardening (5-8 дней) — Лид: Agent-4

1. Fault injection: lost notify, DB deadlock, history-logger timeout, worker crash.
2. Load tests: 50 / 100 / 200 зон одновременно.
3. Canary: `5% → 25% → 100%` зон.
4. Rollback automation по burn-rate thresholds.

Выход: SLO соблюдены на 100% зон; rollback отрабатывает автоматически.

---

## 22. Plan для 4 AI-агентов (DDD ownership)

| Агент | Слой | Зона ответственности |
|---|---|---|
| **Agent-1** | Domain + Contracts | entities, value objects, policies, events, enums, DDL migrations, schema version adapters |
| **Agent-2** | Application Orchestration | use cases, lease/fence flow, workflow FSM execution, planner, saga compensation |
| **Agent-3** | Infrastructure Reliability | outbox publisher, tracker, LISTEN/NOTIFY adapter, repositories, actuator lock manager, circuit breaker |
| **Agent-4** | Bridge + Ops + Tests | Laravel integration, poller bridge, e2e/fault/load/canary, runbook, dashboards |

**Правило:** изменение freeze-артефакта только через RFC-коммит. Агент не меняет слой другого агента без RFC.

---

## 23. Структура каталогов

```text
backend/services/automation-engine/ae3/
├── domain/
│   ├── task/
│   │   ├── entities/          # Task, TaskAttempt, TaskCommand
│   │   ├── value_objects/     # TaskId, TaskType, TaskStatus, ...
│   │   ├── policies/          # AdmissionPolicy, OutcomePolicy, SagaPolicy
│   │   ├── events/            # TaskRequested, TaskCompleted, ...
│   │   └── version_adapters/  # v1_to_v2.py
│   ├── workflow/
│   │   ├── fsm.py
│   │   ├── transition_policy.py
│   │   └── topologies/
│   │       ├── two_tank.py    # production
│   │       └── three_tank.py  # feature-gated, migrated from domain/workflows/three_tank.py
│   ├── command/
│   │   ├── command_plan.py
│   │   └── outcome_policy.py
│   └── shared/
│       └── errors.py          # DomainError, ConcurrencyError, ExternalDependencyError
├── application/
│   ├── use_cases/             # StartCycle, Enqueue, Claim, Execute, Finalize, ...
│   ├── ports/                 # TaskRepositoryPort, LeaseRepositoryPort, ...
│   └── dto/
├── infrastructure/
│   ├── persistence/postgres/  # repositories, migrations helper
│   ├── messaging/pg_notify/   # dedicated connection, reconnect, listener
│   ├── history_logger/        # REST adapter
│   ├── reliability/           # circuit_breaker, outbox_publisher, tracker
│   └── observability/         # metrics, structured logging
├── interfaces/
│   ├── api/                   # FastAPI routes
│   └── cli/
├── bootstrap/
│   ├── di_container.py
│   └── app.py
└── tests/
    ├── unit/                  # domain + use-case tests (no I/O)
    ├── integration/           # DB + notify + outbox + history-logger
    ├── contract/              # API/status/schema contracts
    ├── fault_injection/       # crash points, lost notify, deadlock
    └── load/                  # 50/100/200 зон
```

---

## 24. Test Strategy

1. **Domain tests** — aggregate invariants, policy decisions, FSM transitions.
2. **Use-case tests** — transaction boundaries, saga compensation, admission rules.
3. **Contract tests** — API/status/schema/version contracts frozen.
4. **Integration tests** — DB + notify + outbox + history-logger adapter.
5. **Concurrency tests** — zone lease, fence loss, actuator contention, 100-zone burst.
6. **Fault tests** — crash after outbox insert, crash during waiting_command, lost notify recovery, DB deadlock, history-logger timeout.
7. **Load tests** — 50/100/200 зон; queue backlog, p95 latency, lease conflict rate.

Обязательные concurrency-сценарии:
- 100 зон burst enqueue → нет двух `running` на одну зону.
- Same-zone duplicate enqueue → dedupe через idempotency_key.
- Lease fence loss → старый worker не может завершить finalize.
- Actuator contention → вторая команда получает `actuator_busy|conflict`.
- Workflow CAS conflict → корректный retry без повреждения state.

---

## 25. Observability и SLO

### 25.1 Метрики (prefix `ae_`, запрещён `zone_id` как label)

```
ae_task_received_total{task_type}
ae_task_finished_total{task_type, status}
ae_task_latency_seconds{task_type}         -- histogram
ae_zone_lease_conflict_total
ae_fence_lost_total
ae_actuator_lock_conflict_total
ae_command_terminal_timeout_total
ae_outbox_backlog                          -- gauge: unpublished outbox entries
ae_notify_lag_seconds                      -- gauge: time since last notify
ae_notify_reconnect_total
ae_dead_letter_total
ae_saga_compensation_required_total
```

### 25.2 SLO

1. `task_completion_ratio >= 99.0%` (rolling 30d)
2. `command_terminal_success_ratio >= 99.5%` (rolling 30d)
3. `workflow_transition_success_ratio >= 99.9%` (rolling 30d)
4. p95 latency: `correction_* ≤ 5s`, `irrigation_* ≤ 10s`, `health_check ≤ 3s`

### 25.3 Burn-rate alerts

- Fast burn: window 5m, threshold `≥ 14x` error budget → freeze rollout.
- Slow burn: window 1h, threshold `≥ 3x` error budget → warning.
- Fast + Slow одновременно → автоматический rollback на предыдущий canary stage + incident + RCA до следующего rollout.

### 25.4 Rollback thresholds (автоматический rollback)

| Метрика | Порог | Окно |
|---|---|---|
| `task_failed_rate` | > 2% | 15 мин |
| `command_terminal_timeout_rate` | > 1% | 15 мин |
| p95 `task_latency_seconds` | +50% vs AE2 baseline | 15 мин |
| `workflow_version_conflict` | > 0.5% от total | 15 мин |

---

## 26. Runbook-сценарии (обязательны до cutover)

1. `scheduler_down` — деградация в safety tick mode.
2. `history_logger_down` — circuit breaker, task retryable.
3. `lease_fence_loss_storm` — признаки, диагностика, fix.
4. `notify_lag_spike` — переключение в polling-first.
5. `outbox_backlog_growth` — диагностика publisher, manual drain.
6. `command_terminal_timeout_spike` — reconcile, dead_letter review.
7. `saga_compensation_failed` — operator escalation, pump emergency stop.

---

## 27. Definition of Ready / Done

### Ready (кодинг стартует только если):

1. Freeze contracts подписан (task/command/status/id/version/payload).
2. DDL freeze подписан.
3. Use-case contracts подписаны.
4. Legacy bridge matrix подписана.
5. Agent ownership matrix подписана.
6. Canary routing policy по зонам зафиксирована.

### Done (cutover только если):

1. Все инварианты §1 соблюдены.
2. `start-cycle` + poller compatibility подтверждены E2E.
3. No-overlap доказан concurrency + load тестами.
4. Rollback automation проверена на canary.
5. Все runbook-сценарии §26 подготовлены и проверены tabletop.
6. SLO соблюдены на 100% зон в canary.

---

## 28. Freeze Checklist

1. `TaskStatus` enum frozen.
2. `CommandStatus` enum frozen.
3. Poller status mapping frozen.
4. `TaskId` / `IntentAlias` format frozen.
5. `IdempotencyKey` format по source frozen.
6. DDL по 6 таблицам frozen.
7. Lease timing params frozen (TTL=180, HB=15, CMD_TIMEOUT=60, ACTUATOR_TTL=90).
8. Actuator lock CAS algorithm frozen.
9. Multi-command FSM + recovery algorithm frozen.
10. Atomic finalize rule frozen.
11. Saga compensation policy frozen.
12. Legacy task_type mapping frozen.
13. Poller bridge mapping frozen.
14. Control mode admission matrix frozen (особенно `semi` semantics).
15. Degraded ticker mechanism frozen (`SCHEDULER_STALE_SEC`).
16. `task_schema_version=1` payload per task_type frozen.
17. Anti-starvation quota `ANTISTARVATION_MAX_CONSECUTIVE` frozen.
18. SLO + burn-rate gates frozen.
19. Agent layer ownership frozen.
20. RFC process frozen.
