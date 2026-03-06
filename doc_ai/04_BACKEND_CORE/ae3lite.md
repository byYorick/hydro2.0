# AE3-Lite: Clean Reboot

**Версия:** 3.1-canonical  
**Дата:** 2026-03-06  
**Статус:** CANONICAL CLEAN-ROOM SPEC

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. Роль документа

`ae3lite.md` — канонический документ для новой реализации `automation-engine`, которую можно
писать с нуля ИИ-ассистентами маленькими, проверяемыми PR.

Этот документ намеренно заменяет перегруженный план. Цель AE3-Lite — не построить новую
платформу событий, а сделать простой, надёжный, понятный executor автоматических задач зоны.

Главная идея:
1. Сначала простой runtime-core.
2. Потом controlled migration с AE2.
3. Потом расширения.

---

## 1. Что Такое AE3-Lite

AE3-Lite v1:
1. DB-backed executor задач зоны.
2. Работает через текущий protected pipeline:
   `Scheduler -> Automation-Engine -> history-logger -> MQTT -> ESP32`.
3. Использует direct SQL read-model.
4. Исполняет задачи последовательно и только по closed-loop contract.
5. Сохраняет текущий внешний wake-up ingress: `POST /zones/{id}/start-cycle`.

AE3-Lite v1 не является:
1. Новым scheduler.
2. Event-platform/outbox-platform.
3. Generic workflow framework на все случаи.
4. Автоматическим rollout-controller.
5. Полной заменой всех runtime API AE2 в первом релизе.

---

## 2. Неподвижные Инварианты

1. Команды на узлы публикуются только через `history-logger` (`POST /commands`).
2. Прямой MQTT publish из AE и Laravel запрещён.
3. Внешний ingress до cutover: только `POST /zones/{id}/start-cycle`.
4. В production v1 допускается только одна активная реплика AE3-Lite.
5. Одновременно на одну зону допускается только одна активная задача исполнения.
6. Успешный terminal outcome mutating-команды только `DONE`.
7. `NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED` всегда означают fail.
8. Runtime path не зависит от runtime HTTP-вызовов в Laravel.
9. Изменения БД выполняются только через Laravel migrations.
10. Domain/Application код `ae3lite/*` не импортирует `ae2lite/*`.
11. Compatibility code живёт только в anti-corruption/adapters слое.
12. Сначала корректность и восстановление, потом масштабирование.

---

## 3. Архитектурный Стиль

### 3.1 Подход

AE3-Lite строится в стиле:
1. OOP
2. DDD
3. Clean Architecture
4. Fail-closed runtime

### 3.2 Bounded Contexts

В v1 допускаются только 3 bounded context:
1. `CompatibilityFacade`
   - принимает legacy ingress;
   - маппит legacy intent в canonical AE3 task.
2. `ExecutionCore`
   - создаёт, лочит, исполняет и завершает task;
   - публикует команды;
   - ждёт terminal status.
3. `ZoneReadModel`
   - читает SQL snapshot зоны;
   - не содержит бизнес-логики исполнения.

Никаких дополнительных platform-context в v1 не создаётся.

### 3.3 Dependency Rule

Разрешённая зависимость слоёв:

`api -> application -> domain <- infrastructure`

Правила:
1. `domain` не знает про SQL, HTTP, FastAPI, asyncpg, Prometheus.
2. `application` оркестрирует use case, но не содержит SQL.
3. `infrastructure` реализует repository/gateway interfaces.
4. `api` только валидирует контракт и вызывает use case.

---

## 4. Domain Model

### 4.1 Aggregate Roots

#### `AutomationTask`

Единственный корневой aggregate исполнения.

Отвечает за:
1. lifecycle task;
2. текущий step;
3. terminal policy;
4. result/error fields.

#### `ZoneLease`

Отвечает за:
1. single-writer на зону;
2. lease timeout;
3. безопасный claim/reclaim.

#### `ZoneWorkflow`

Отвечает за:
1. текущую фазу workflow зоны;
2. CAS version;
3. разрешённые phase transitions.

### 4.2 Внутренние Entity

#### `PlannedCommand`

Child-entity внутри `AutomationTask`.

Хранит:
1. `step_no`
2. `node_uid`
3. `channel`
4. `payload`
5. `external_command_id`
6. `terminal_status`

### 4.3 Value Objects

Минимум:
1. `TaskId`
2. `ZoneId`
3. `TaskType`
4. `TaskStatus`
5. `WorkflowPhase`
6. `CommandTerminalStatus`
7. `LeaseOwner`

### 4.4 Canonical Task Types

В очередь `ae_tasks` помещаются только business-level tasks:
1. `cycle_start`
2. `lighting_tick`
3. `ventilation_tick`
4. `solution_change`
5. `mist`
6. `diagnostics`
7. `recovery`

Запрещено помещать в очередь как top-level task:
1. `irrigation_start`
2. `irrigation_stop`
3. `recirculation_start`
4. `recirculation_stop`
5. `correction_ph`
6. `correction_ec`
7. `compensation`

Эти действия являются внутренними workflow-шагами `cycle_start`, а не отдельными root-task.

### 4.5 Task Statuses

Main path:
`pending -> claimed -> running -> waiting_command -> completed`

Terminal:
`failed | cancelled`

В v1 статусы `skipped|expired|conflict` не вводятся. Они усложняют модель без критической пользы.

### 4.6 Workflow Phases

Допустимые фазы:
1. `idle`
2. `tank_filling`
3. `tank_recirc`
4. `irrigating`
5. `irrig_recirc`
6. `ready`

Только `cycle_start` имеет право мутировать `ZoneWorkflow`.

---

## 5. Compatibility Facade

### 5.1 Внешний Контракт

До полного cutover сохраняется:
1. `POST /zones/{id}/start-cycle`
2. `zone_automation_intents`
3. `idempotency_key`

### 5.2 Legacy -> AE3 Mapping

Mapping выполняется в одном адаптере:
`application/adapters/legacy_intent_mapper.py`

Правила:
1. `payload.workflow=cycle_start` -> `cycle_start`
2. `intent_type=irrigate_once` -> `cycle_start`
3. `intent_type=irrigation_tick` -> `cycle_start`
4. `intent_type=lighting_tick` -> `lighting_tick`
5. `intent_type=ventilation_tick` -> `ventilation_tick`
6. `intent_type=solution_change_tick` -> `solution_change`
7. `intent_type=mist_tick` -> `mist`
8. `intent_type=diagnostics_tick` -> `diagnostics`

Если mapping не определён:
1. фасад возвращает controlled error;
2. новая AE3 task не создаётся;
3. событие пишется в `zone_events`.

### 5.3 Что Не Делаем В v1

В v1 не поддерживаем:
1. `scheduler_logs` compatibility projection;
2. dual status mirrors;
3. bridge audit journal;
4. alias table `intent-* <-> ae3:*`.

Вместо этого:
1. внешний `start-cycle` остаётся прежним;
2. новый Laravel poller переводится на canonical `GET /internal/tasks/{task_id}`;
3. только после этого AE2 удаляется.

---

## 6. Runtime Flow

### 6.1 High-Level Sequence

1. `CompatibilityFacade` валидирует ingress.
2. Создаётся `AutomationTask(status=pending)`.
3. Worker выбирает следующую задачу.
4. Worker получает `ZoneLease`.
5. Загружается `ZoneSnapshot` через SQL read-model.
6. Planner строит `CommandPlan`.
7. Команды сохраняются в `ae_commands`.
8. Команды отправляются через `history-logger`.
9. Runtime ждёт terminal status в таблице `commands`.
10. `DONE` переводит к следующему step.
11. Любой другой terminal завершает task как `failed`.
12. `ZoneLease` освобождается.

### 6.2 Execution Policy

1. Все шаги исполняются строго последовательно.
2. Параллельные command-steps в v1 запрещены.
3. Следующий step разрешён только после terminal предыдущего.
4. `cycle_start` — единственный сложный multi-step workflow в v1.
5. `lighting_tick`, `ventilation_tick`, `mist`, `solution_change`, `diagnostics` — single-plan tasks.

### 6.3 DONE-Only Contract

Для всех mutating-команд:
1. success = только `DONE`;
2. `NO_EFFECT` не считается успехом;
3. dedupe не может подменять реальный terminal;
4. publish failure не может трактоваться как implicit ACK.

### 6.4 Failure Handling

В v1 нет отдельного `compensation task`.

Вместо этого:
1. fail-finalize выполняется в том же use case;
2. если нужен safety-stop, он выполняется как inline fail-safe action;
3. fail-safe action запускается только после того, как предыдущий command-step уже имеет terminal status;
4. fail-safe action не создаёт новую business-task в очереди.

Это принципиально упрощает safety model.

---

## 7. Planning В Стиле DDD

### 7.1 Domain Services

Допускаются только такие planners:
1. `CycleStartPlanner`
2. `LightingTickPlanner`
3. `VentilationTickPlanner`
4. `SolutionChangePlanner`
5. `MistPlanner`
6. `DiagnosticsPlanner`
7. `RecoveryPlanner`

Каждый planner:
1. принимает `AutomationTask` и `ZoneSnapshot`;
2. возвращает `CommandPlan`;
3. не содержит SQL и HTTP.

### 7.2 CommandPlan

`CommandPlan` содержит:
1. `steps: list[PlannedCommandDraft]`
2. `requires_terminal: bool`
3. `timeout_sec: int`
4. `workflow_transition_on_success: WorkflowTransition | None`

### 7.3 Zone Snapshot

`ZoneSnapshot` загружается отдельным reader-service из БД.

Обязательные источники:
1. `zones`
2. `grow_cycles`
3. `grow_cycle_phases`
4. `grow_cycle_overrides`
5. `zone_workflow_state`
6. `telemetry_last`
7. `nodes`
8. `node_channels`
9. `channel_bindings`
10. `pump_calibrations`
11. `pid_state`
12. `zone_pid_configs`

`ZoneSnapshot` — immutable DTO application layer.

---

## 8. Минимальная Схема Данных

### 8.1 `ae_tasks`

Минимальные поля:
1. `id`
2. `zone_id`
3. `task_type`
4. `status`
5. `payload`
6. `idempotency_key`
7. `scheduled_for`
8. `due_at`
9. `claimed_by`
10. `claimed_at`
11. `error_code`
12. `error_message`
13. `created_at`
14. `updated_at`
15. `completed_at`

### 8.2 `ae_commands`

Минимальные поля:
1. `id`
2. `task_id`
3. `step_no`
4. `node_uid`
5. `channel`
6. `payload`
7. `external_id`
8. `publish_status`
9. `terminal_status`
10. `ack_received_at`
11. `terminal_at`
12. `last_error`
13. `created_at`
14. `updated_at`

### 8.3 `ae_zone_leases`

Минимальные поля:
1. `zone_id`
2. `owner`
3. `leased_until`
4. `updated_at`

### 8.4 `zone_workflow_state`

Обязательное расширение:
1. `version BIGINT NOT NULL DEFAULT 0`

В `zone_workflow_state` храним только:
1. `workflow_phase`
2. `version`
3. `scheduler_task_id`
4. `started_at`
5. `updated_at`

Запрещено хранить там:
1. `control_mode`
2. `sensor_mode`
3. случайные recovery blobs
4. cross-context flags

### 8.5 `zones`

Для controlled rollout достаточно одного поля:
1. `automation_runtime TEXT NOT NULL DEFAULT 'ae2' CHECK (automation_runtime IN ('ae2','ae3'))`

Это заменяет:
1. canary-router;
2. `ae3l_canary_state`;
3. `ae2_writer_heartbeat`;
4. автоматический gate orchestration.

---

## 9. API Контракты

### 9.1 v1 Обязательные Endpoints

1. `POST /zones/{id}/start-cycle`
2. `GET /internal/tasks/{task_id}`

### 9.2 `POST /zones/{id}/start-cycle`

Сохраняет текущий внешний контракт:
1. принимает `source`, `idempotency_key`;
2. валидирует security baseline;
3. через compatibility facade создаёт canonical AE3 task.

До cutover допустим внешний `task_id="intent-<id>"`, но внутренним source of truth считается `ae_tasks.id`.

### 9.3 `GET /internal/tasks/{task_id}`

Минимальный ответ:
1. `task_id`
2. `zone_id`
3. `task_type`
4. `status`
5. `error_code`
6. `error_message`
7. `created_at`
8. `updated_at`
9. `completed_at`

В v1 этот endpoint — canonical source для poller/status UI migration.

### 9.4 Что Не Входит В v1

Эндпоинты:
1. `/zones/{id}/state`
2. `/zones/{id}/control-mode`
3. `/zones/{id}/manual-step`
4. `/zones/{id}/start-relay-autotune`
5. `/zones/{id}/relay-autotune/status`

остаются в AE2 до стабилизации AE3 execution core.

---

## 10. Recovery И Safety

### 10.1 Deployment Invariant

Production v1:
1. одна реплика;
2. один worker loop;
3. recovery выполняется тем же процессом.

Это сознательное ограничение для уменьшения сложности.

### 10.2 Startup Recovery

При старте:
1. `waiting_command` задачи проверяются по `commands`;
2. если terminal уже есть — задача финализируется;
3. `running` без активной команды переводятся в `failed` с `error_code=recovery_required`;
4. `ZoneLease` с истёкшим `leased_until` освобождаются;
5. recovery не создаёт cascade retry storm.

### 10.3 Telemetry Freshness

1. Для critical checks используется freshness guard.
2. Stale critical telemetry -> fail-closed.
3. Hardcoded default targets запрещены.

### 10.4 Degraded Mode

В v1 degraded-mode отдельной подсистемой не вводится.

Если scheduler/source недоступен:
1. новые задачи не принимаются;
2. уже активные задачи завершаются корректно;
3. система не создаёт специальные background tasks сама.

---

## 11. Кодовая Структура

```text
backend/services/automation-engine/ae3lite/
├── api/
│   ├── compat_endpoints.py
│   └── internal_endpoints.py
├── application/
│   ├── adapters/
│   │   └── legacy_intent_mapper.py
│   └── use_cases/
│       ├── create_task_from_intent.py
│       ├── claim_next_task.py
│       ├── execute_task.py
│       ├── reconcile_command.py
│       └── finalize_task.py
├── domain/
│   ├── entities/
│   │   ├── automation_task.py
│   │   ├── planned_command.py
│   │   ├── zone_lease.py
│   │   └── zone_workflow.py
│   ├── services/
│   │   ├── cycle_start_planner.py
│   │   ├── lighting_tick_planner.py
│   │   ├── ventilation_tick_planner.py
│   │   ├── diagnostics_planner.py
│   │   └── recovery_planner.py
│   ├── value_objects.py
│   └── errors.py
├── infrastructure/
│   ├── repositories/
│   ├── gateways/
│   └── read_models/
├── runtime/
│   ├── worker.py
│   └── recovery.py
└── main.py
```

Правила clean code:
1. один публичный класс или один use case на файл;
2. без god-module;
3. без module-level mutable state;
4. без неявной магии через dict-ключи между слоями;
5. DTO и domain objects не смешиваются.

---

## 12. План Реализации

### Phase 0: Foundations

1. Создать `ae3lite/` skeleton.
2. Добавить `zones.automation_runtime`.
3. Создать `ae_tasks`, `ae_commands`, `ae_zone_leases`.
4. Добавить `zone_workflow_state.version`.
5. Реализовать `GET /internal/tasks/{task_id}`.

### Phase 1: ExecutionCore v1

1. Реализовать `AutomationTask`, `ZoneLease`, `ZoneWorkflow`.
2. Реализовать `CycleStartPlanner`.
3. Реализовать sequential worker.
4. Реализовать history-logger gateway.
5. Реализовать recovery для `waiting_command`.

### Phase 2: CompatibilityFacade

1. Реализовать `legacy_intent_mapper`.
2. Подключить `POST /zones/{id}/start-cycle` к AE3 path.
3. Сохранить текущий ingress contract.
4. Laravel poller перевести на `GET /internal/tasks/{task_id}`.

### Phase 3: Controlled Rollout

1. Переключение только вручную через `zones.automation_runtime='ae3'`.
2. Сначала 1 тестовая зона.
3. Потом несколько production зон с низким риском.
4. Потом все `cycle_start` зоны.

### Phase 4: Additional Tasks

После стабилизации core:
1. `lighting_tick`
2. `ventilation_tick`
3. `solution_change`
4. `mist`

### Phase 5: Post-Core Extensions

Только после cutover core:
1. новый `/zones/{id}/state`
2. `control-mode`
3. `manual-step`
4. `relay-autotune`
5. multi-replica deployment
6. advanced recovery

---

## 13. Тестовая Стратегия

### 13.1 Unit

1. aggregate transitions
2. planner decisions
3. legacy mapping
4. DONE-only policy

### 13.2 Integration

1. task claim
2. zone lease
3. command publish
4. command terminal reconcile
5. startup recovery
6. workflow CAS update

### 13.3 E2E

Минимум:
1. `scheduler -> start-cycle -> task created`
2. `task -> command -> DONE -> completed`
3. `task -> TIMEOUT -> failed`
4. `restart during waiting_command -> recover and finalize`

### 13.4 Что Не Считается Доказательством Корректности

В v1 не используем как главный proof:
1. shadow-run без publish;
2. parity-only comparison без node terminal;
3. сложные synthetic canary metrics вместо реальных integration tests.

---

## 14. Правила Для ИИ-Ассистентов

AE3-Lite должен быть пригоден для безопасной реализации ИИ-ассистентами.

Обязательные правила:
1. один PR — один use case или один schema package;
2. сначала domain contract, потом repository, потом runtime wiring;
3. перед merge обязателен тест затронутого use case;
4. запрещено смешивать migration, planner logic и API refactor в одном PR;
5. запрещено тянуть legacy runtime код в новый domain;
6. если нужен compatibility code, он пишется только в adapter/facade слое;
7. сложность режется удалением scope, а не добавлением новых abstraction layers.

---

## 15. Что Отложено Осознанно

Не входит в canonical AE3-Lite v1:
1. `scheduler_logs` projection
2. outbox/domain-events subsystem
3. auto-canary router
4. auto-rollback controller
5. anti-starvation subsystem
6. reference-table `ae_task_types`
7. manual-step runtime
8. relay-autotune runtime
9. multi-replica active-active
10. generic compensation task queue

Каждый пункт может быть добавлен только отдельным RFC после успешного cutover core runtime.

---

## 16. Definition of Done

AE3-Lite v1 считается готовым, когда:
1. `cycle_start` работает через новый `ExecutionCore`;
2. успешная mutating-команда подтверждается только `DONE`;
3. `ZoneLease` исключает двойное исполнение зоны;
4. `waiting_command` корректно восстанавливается после restart;
5. Laravel poller умеет читать canonical `GET /internal/tasks/{task_id}`;
6. минимум одна production зона стабильно работает на `automation_runtime='ae3'`;
7. в `ae3lite/*` нет импортов из `ae2lite/*`;
8. интеграционные и e2e тесты зелёные;
9. документация остаётся компактной и однозначной.

Именно это и есть хороший AE3-Lite: простой, предсказуемый, ограниченный по scope и реально реализуемый.

---

## 17. Production Версия AE3-Lite

Полной production-версией AE3-Lite считается не просто v1 core, а полная замена AE2 в рабочем runtime-path.

В production scope входят:
1. `cycle_start`
2. `lighting_tick`
3. `ventilation_tick`
4. `solution_change`
5. `mist`
6. `diagnostics`
7. `recovery`
8. native `GET /internal/tasks/{task_id}`
9. native `GET /zones/{id}/state`
10. native `GET/POST /zones/{id}/control-mode`
11. native `POST /zones/{id}/manual-step`
12. native `POST /zones/{id}/start-relay-autotune`
13. native `GET /zones/{id}/relay-autotune/status`
14. controlled rollout по `zones.automation_runtime`
15. rollback обратно на AE2 без ручного ремонта БД

Не требуется для первой production-версии:
1. auto-canary router
2. auto-rollback controller
3. outbox/domain-events platform
4. active-active multi-replica
5. generic event-driven platform

Production AE3-Lite должен оставаться простым single-runtime решением, а не перерастать в платформу.

---

## 18. План На 4 ИИ-Агента

### 18.1 Общие Правила Координации

1. Каждый агент работает в своей области ответственности.
2. Один и тот же файл не редактируется двумя агентами параллельно.
3. Переход к следующей волне разрешён только после merge gate.
4. Любой агент обязан добавлять тесты на свой deliverable.
5. Если deliverable меняет контракт, агент обязан обновить `doc_ai`.

### 18.2 Agent-A: `domain-db-core`

Зона ответственности:
1. domain model
2. migrations
3. repositories contracts
4. schema constraints
5. CAS/lease invariants

Делает:
1. `ae_tasks`
2. `ae_commands`
3. `ae_zone_leases`
4. `zone_workflow_state.version`
5. `zones.automation_runtime`
6. domain entities/value objects/errors
7. repository interfaces
8. migration tests `up/down`

Файлы ownership:
1. `ae3lite/domain/*`
2. `ae3lite/infrastructure/repositories/*`
3. Laravel migrations для AE3-Lite

Definition of Done агента:
1. схема поднимается в Docker
2. schema rollback работает
3. domain aggregate tests зелёные
4. DB constraints реально защищают инварианты

### 18.3 Agent-B: `runtime-commands`

Зона ответственности:
1. worker loop
2. command execution
3. reconcile
4. startup recovery
5. history-logger integration

Делает:
1. `claim_next_task`
2. `execute_task`
3. `reconcile_command`
4. `finalize_task`
5. `runtime/worker.py`
6. `runtime/recovery.py`
7. history-logger gateway
8. `CycleStartPlanner`
9. additional planners для `lighting_tick`, `ventilation_tick`, `solution_change`, `mist`, `diagnostics`, `recovery`

Файлы ownership:
1. `ae3lite/application/use_cases/*`
2. `ae3lite/runtime/*`
3. `ae3lite/infrastructure/gateways/*`
4. `ae3lite/domain/services/*`

Definition of Done агента:
1. все mutating paths obey `DONE-only`
2. worker корректно доходит до `completed|failed`
3. restart в `waiting_command` восстанавливается
4. integration tests для publish/reconcile зелёные

### 18.4 Agent-C: `compat-api-rollout`

Зона ответственности:
1. compatibility facade
2. ingress contracts
3. internal/public API
4. Laravel poller migration
5. runtime API replacement AE2

Делает:
1. `legacy_intent_mapper`
2. `POST /zones/{id}/start-cycle`
3. `GET /internal/tasks/{task_id}`
4. native `GET /zones/{id}/state`
5. native `GET/POST /zones/{id}/control-mode`
6. native `POST /zones/{id}/manual-step`
7. native relay-autotune endpoints
8. migration Laravel poller на canonical task API
9. rollback-safe switch по `zones.automation_runtime`

Файлы ownership:
1. `ae3lite/api/*`
2. `ae3lite/application/adapters/*`
3. Laravel integration points, которые читают task/status API

Definition of Done агента:
1. старый ingress не сломан
2. новый internal task API стабилен
3. AE2-only API зависимости удалены с новых путей
4. API contract tests зелёные

### 18.5 Agent-D: `qa-e2e-prod`

Зона ответственности:
1. test harness
2. docker/integration/e2e
3. staging/prod rollout
4. observability minimum
5. docs sync

Делает:
1. unit/integration/e2e orchestration
2. Docker test profiles
3. staging smoke scripts
4. production rollout checklist
5. rollback checklist
6. docs sync в `INDEX.md`, `ARCHITECTURE_FLOWS.md`, `04_BACKEND_CORE/README.md`, `REST_API_REFERENCE.md`, `API_SPEC_FRONTEND_BACKEND_FULL.md`, `DATA_MODEL_REFERENCE.md`
7. minimum monitoring:
   - structured logs
   - task status counters
   - command failure counters
   - worker recovery counters

Файлы ownership:
1. `tests/*`
2. CI/test scripts
3. rollout docs/runbooks
4. cross-doc sync

Definition of Done агента:
1. весь test matrix автоматизирован
2. staging rollout воспроизводим
3. rollback воспроизводим
4. документы синхронизированы с кодом

### 18.6 Волны Реализации

#### Wave 1: Foundation

Owner:
1. Agent-A primary
2. Agent-D support

Deliverables:
1. skeleton `ae3lite/`
2. migrations
3. domain contracts
4. repository interfaces
5. migration tests

Gate G1:
1. migrations `up/down` зелёные
2. aggregate unit tests зелёные
3. ни одного импорта `ae2lite/*` в `ae3lite/*`

#### Wave 2: Core Runtime

Owner:
1. Agent-B primary
2. Agent-A support

Deliverables:
1. worker
2. `CycleStartPlanner`
3. history-logger gateway
4. reconcile/recovery
5. `cycle_start` end-to-end path

Gate G2:
1. `start-cycle -> DONE -> completed` зелёный в Docker
2. `start-cycle -> TIMEOUT -> failed` зелёный
3. restart during `waiting_command` восстанавливается

#### Wave 3: Compatibility And Status API

Owner:
1. Agent-C primary
2. Agent-B support
3. Agent-D tests

Deliverables:
1. `legacy_intent_mapper`
2. compatibility `POST /zones/{id}/start-cycle`
3. canonical `GET /internal/tasks/{task_id}`
4. Laravel poller migration

Gate G3:
1. старый scheduler ingress работает
2. poller читает canonical task API
3. одна staging зона проходит полный `cycle_start`

#### Wave 4: Full Production Feature Set

Owner:
1. Agent-B primary на execution tasks
2. Agent-C primary на API
3. Agent-D tests

Deliverables:
1. `lighting_tick`
2. `ventilation_tick`
3. `solution_change`
4. `mist`
5. native `/zones/{id}/state`
6. native `control-mode`
7. native `manual-step`
8. native relay-autotune endpoints

Gate G4:
1. все task types проходят integration tests
2. все runtime API проходят contract tests
3. AE2 больше не нужен для активных production сценариев

#### Wave 5: Production Cutover

Owner:
1. Agent-D primary
2. Agent-C rollout support
3. Agent-B hotfix support

Deliverables:
1. manual rollout runbook
2. manual rollback runbook
3. staging soak
4. production soak
5. AE2 deactivation plan

Gate G5:
1. staging soak без инцидентов
2. pilot production zones стабильны
3. rollback проверен
4. docs sync complete

### 18.7 Запрещённые Пересечения

1. Agent-A не пишет runtime API.
2. Agent-B не меняет Laravel poller и фронтовые контракты.
3. Agent-C не меняет domain invariants без ревью Agent-A.
4. Agent-D не меняет core domain behavior без явного handoff.

---

## 19. Обязательный Test Matrix Для 4 Агентов

### 19.1 Unit

Owner:
1. Agent-A
2. Agent-B

Покрытие:
1. aggregate transitions
2. workflow CAS
3. lease rules
4. planner decisions
5. legacy mapping

### 19.2 Integration

Owner:
1. Agent-B
2. Agent-C

Покрытие:
1. DB repositories
2. `history-logger` publish contract
3. `commands` reconcile
4. startup recovery
5. API + DB path
6. `zones.automation_runtime` switch

### 19.3 API Contract

Owner:
1. Agent-C
2. Agent-D

Покрытие:
1. `POST /zones/{id}/start-cycle`
2. `GET /internal/tasks/{task_id}`
3. `GET /zones/{id}/state`
4. `GET/POST /zones/{id}/control-mode`
5. `POST /zones/{id}/manual-step`
6. `POST /zones/{id}/start-relay-autotune`
7. `GET /zones/{id}/relay-autotune/status`

### 19.4 E2E

Owner:
1. Agent-D

Минимальные сценарии:
1. `start-cycle -> completed`
2. `start-cycle -> command TIMEOUT -> failed`
3. `start-cycle -> restart during waiting_command -> recovered`
4. `lighting_tick -> DONE -> completed`
5. `ventilation_tick -> DONE -> completed`
6. `solution_change -> terminal path`
7. `mist -> terminal path`
8. `manual-step` в допустимой фазе
9. `manual-step` в недопустимой фазе
10. `control-mode` switch
11. relay-autotune `start -> running -> complete|timeout`

### 19.5 Staging Soak

Owner:
1. Agent-D

Обязательно:
1. минимум 24 часа на staging
2. минимум одна restart-проверка сервиса
3. минимум одна rollback-проверка на staging

### 19.6 Production Pilot

Owner:
1. Agent-D
2. Agent-C

Обязательно:
1. сначала 1 production зона
2. затем 3-5 зон
3. затем все зоны
4. переход между стадиями только вручную

---

## 20. Production Rollout И Rollback

### 20.1 Rollout Preconditions

Перед production rollout должны быть выполнены все условия:
1. G1-G5 закрыты
2. test matrix зелёный
3. документация синхронизирована
4. Laravel poller не зависит от AE2-only status path
5. AE3 runtime запускается стабильно в Docker/staging

### 20.2 Rollout Procedure

1. Выбрать pilot zone.
2. Установить `zones.automation_runtime='ae3'`.
3. Перезапустить `automation-engine`.
4. Выполнить smoke:
   - `start-cycle`
   - task status poll
   - command publish
   - terminal reconcile
5. Наблюдать пилотную зону.
6. Повторить для группы зон.
7. После стабильной группы переключить остальные зоны.

### 20.3 Rollback Procedure

Rollback должен быть максимально тупым и обратимым:
1. установить `zones.automation_runtime='ae2'` для проблемных зон;
2. перезапустить `automation-engine`;
3. новые задачи снова уйдут через AE2 path;
4. незавершённые AE3 tasks остаются в БД для расследования;
5. ручной destructive cleanup запрещён.

### 20.4 Production Definition of Done

AE3-Lite считается доведённым до production-version, когда:
1. все runtime paths из раздела 17 реализованы;
2. 4 агента закрыли свои deliverables и gate-ы;
3. pilot и grouped rollout прошли без rollback;
4. AE2 исключён из active runtime path;
5. rollback назад на AE2 остаётся доступным до финального freeze-window;
6. документация и тесты отражают фактический production state.
