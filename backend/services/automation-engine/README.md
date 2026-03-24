# Automation Engine

Система автоматизации управления параметрами теплиц с поддержкой параллельной обработки зон, централизованной обработкой ошибок и модульной архитектурой.

## Актуальный AE3 runtime (2026-03-24)

- Canonical runtime API:
  - `ae3lite/runtime/app.py` (entrypoint FastAPI)
  - `ae3lite/api/compat_endpoints.py` (bind `POST /zones/{id}/start-cycle`)
  - `ae3lite/api/internal_endpoints.py` (canonical internal task/status API)
  - `ae3lite/application/use_cases/get_zone_automation_state.py` (zone state read-path)
- Legacy runtime package удалён из рабочего кода; canonical implementation живёт только в `ae3lite/*`.
- Single-writer policy:
  - lease уникален на зону (`start_cycle:{zone_id}`);
  - при активной lease повторный запуск зоны блокируется;
  - runtime работает fail-closed без fallback writer-режима.

## Актуализация 2026-02-16 (P3/P4/P5)

- Оперативный статус декомпозиции:
  - `application/scheduler_executor_impl.py`: 413 строк (decomposition target выполнен: <=1000);
  - `api.py`: 2859 строк (в работе, этап D3);
  - добавлены API helper-модули:
    - `application/api_automation_state.py`
    - `application/api_payload_parsing.py`
    - `application/api_task_snapshot.py`;
  - decomposition regression-пакет: `31 passed, 1 warning`;
  - `test_api.py` в текущем окружении требует `httpx` (без зависимости не стартует).

- Event integrity:
  - action-события контроллеров (`IRRIGATION_STARTED`, `RECIRCULATION_CYCLE`, ...) пишутся только после подтверждённого publish;
  - при отказе publish фиксируются `*_COMMAND_REJECTED` / `*_COMMAND_UNCONFIRMED`;
  - в `event_details` добавляется `correlation_id` (`cmd_id`) для связи с command audit.
- Workflow coordination/persistence:
  - `IrrigationController` учитывает `workflow_phase`; разрешён bootstrap первого автополива при отсутствии истории `IRRIGATION_STARTED`;
  - `SchedulerTaskExecutor` синхронизирует фазу и сохраняет её в `zone_workflow_state` через `WorkflowStateStore`;
  - startup recovery продолжает in-flight workflow или делает stale safety-stop.
- Safety defaults:
  - `AE_ENFORCE_NODE_ZONE_ASSIGNMENT=1`
  - `AE_ENFORCE_COMMAND_CHANNEL_COMPATIBILITY=1`
- EC partial batch policy:
  - при частичном сбое дозирования пишется `EC_BATCH_PARTIAL_FAILURE`;
  - запускается компенсационный degraded-path через enqueue diagnostics workflow.
- Decomposition step:
  - `scheduler_task_executor.py` оставлен тонким coordinator-модулем без `exec(...)` (явные импорты + совместимость patch points);
  - основная реализация — `application/scheduler_executor_impl.py`;
  - добавлены `application/workflow_router.py`, `application/workflow_validator.py`,
    `application/command_dispatch.py`, `application/workflow_state_sync.py`;
  - вынесена decision-модель и policy:
    - `domain/models/decision_models.py`
    - `domain/policies/decision_policy.py`;
  - вынесена policy маппинга workflow phase/stage:
    - `application/workflow_phase_policy.py`;
  - добавлены domain-entrypoint модули `domain/workflows/{two_tank,three_tank,cycle_start}.py`;
  - разделён monolith `domain/workflows/two_tank_core.py`:
    - coordinator: `domain/workflows/two_tank_core.py`
    - startup branch: `domain/workflows/two_tank_startup_core.py`
    - recovery branch: `domain/workflows/two_tank_recovery_core.py`
  - вынесены DB/query adapters для scheduler executor:
    - `infrastructure/node_query_adapter.py`
    - `infrastructure/telemetry_query_adapter.py`
    - выбор refill-ноды (`_resolve_refill_command`) переведён на thin adapter-вызов без SQL в coordinator;
  - вынесена policy проверки целевых pH/EC:
    - `domain/policies/target_evaluation_policy.py`
    - `SchedulerTaskExecutor` использует thin wrappers `_is_value_within_pct` / `_evaluate_ph_ec_targets`;
  - вынесены policy helper-правила cycle-start refill:
    - `domain/policies/cycle_start_refill_policy.py`
    - `SchedulerTaskExecutor` использует thin wrappers `_resolve_required_node_types`,
      `_resolve_clean_tank_threshold`, `_resolve_refill_duration_ms`, `_resolve_refill_attempt`,
      `_resolve_refill_started_at`, `_resolve_refill_timeout_at`, `_build_refill_check_payload`;
  - вынесены two-tank helper-правила формирования payload/result:
    - `domain/policies/two_tank_guard_policy.py`
    - `SchedulerTaskExecutor` использует thin wrappers `_build_two_tank_check_payload`,
      `_build_two_tank_stop_not_confirmed_result`;
  - вынесены shared normalization/coercion helpers:
    - `domain/policies/normalization_policy.py`
    - `SchedulerTaskExecutor` использует thin wrappers `_resolve_int`, `_resolve_float`,
      `_normalize_labels`, `_canonical_sensor_label`, `_merge_dict_recursive`;
  - вынесен diagnostics helper для fail-closed invalid payload response:
    - `domain/policies/diagnostics_policy.py`
    - `SchedulerTaskExecutor` использует thin wrapper `_build_diagnostics_invalid_payload_result`;
  - вынесены workflow input extract/normalize helpers:
    - `domain/policies/workflow_input_policy.py`
    - `SchedulerTaskExecutor` использует thin wrappers `_extract_execution_config`, `_extract_refill_config`,
      `_extract_payload_contract_version`, `_is_supported_payload_contract_version`, `_extract_workflow`,
      `_extract_topology`, `_normalize_two_tank_workflow`, `_is_two_tank_startup_workflow`,
      `_is_three_tank_startup_workflow`;
  - вынесены decision detail helpers:
    - `domain/policies/decision_detail_policy.py`
    - `SchedulerTaskExecutor` использует thin wrappers `_to_optional_float`, `_with_decision_details`;
  - вынесены command mapping helpers:
    - `domain/policies/command_mapping_policy.py`
    - `SchedulerTaskExecutor` использует thin wrappers `_terminal_status_to_error_code`,
      `_extract_duration_sec`, `_resolve_command_name`, `_resolve_command_params`;
  - вынесены outcome helpers:
    - `domain/policies/outcome_policy.py`
    - `SchedulerTaskExecutor` использует thin wrappers `_build_decision_retry_correlation_id`,
      `_extract_two_tank_chemistry_orchestration`;
  - вынесен outcome enrichment helper-блок:
    - `domain/policies/outcome_enrichment_policy.py`
    - `SchedulerTaskExecutor` использует thin wrapper `_ensure_extended_outcome`;
  - вынесен helper формирования payload task events:
    - `application/task_events.py`
    - `SchedulerTaskExecutor` использует helper `build_task_event_payload(...)` в `_emit_task_event`;
  - вынесен helper безопасного persist task events:
    - `application/task_events_persistence.py`
    - `SchedulerTaskExecutor` использует helper `persist_zone_event_safe(...)` в `_create_zone_event_safe`;
  - вынесен helper отправки cycle infra-alert:
    - `application/cycle_alerts.py`
    - `SchedulerTaskExecutor` использует helper `emit_cycle_alert(...)` в `_emit_cycle_alert`;
  - вынесен helper построения execution context:
    - `application/task_context.py`
    - `SchedulerTaskExecutor` использует helper `build_task_context(...)` в `execute(...)`;
  - вынесены execution flow payload/result helpers:
    - `application/execution_flow_policy.py`
    - `SchedulerTaskExecutor` использует helper-функции в `execute(...)` для
      `TASK_RECEIVED`/`DECISION_MADE`/`TASK_FINISHED` payload и no-action результата;
  - вынесены execution lifecycle structured logging helpers:
    - `application/execution_logging.py`
    - `SchedulerTaskExecutor` использует `log_execution_started(...)` / `log_execution_finished(...)`;
  - вынесен helper отправки decision infra-alert для no-action ветки:
    - `application/decision_alerts.py`
    - `SchedulerTaskExecutor` использует `should_emit_decision_alert(...)` /
      `emit_decision_alert(...)` в `execute(...)`;
  - вынесен helper action-required dispatch ветки:
    - `application/execution_branches.py`
    - `SchedulerTaskExecutor` использует `execute_action_required_branch(...)` в `execute(...)`;
  - вынесен helper no-action dispatch ветки:
    - `application/no_action_branch.py`
    - `SchedulerTaskExecutor` использует `execute_no_action_branch(...)` в `execute(...)`;
  - вынесен helper финализации выполнения задачи:
    - `application/execution_finalize.py`
    - `SchedulerTaskExecutor` использует `finalize_execution(...)` в `execute(...)`;
  - вынесен helper стартовых execution events:
    - `application/execution_startup.py`
    - `SchedulerTaskExecutor` использует `emit_execution_started_events(...)` в `execute(...)`;
  - вынесен helper decision-фазы выполнения:
    - `application/execution_decision.py`
    - `SchedulerTaskExecutor` использует `run_decision_phase(...)` в `execute(...)`;
  - вынесен helper подготовки входов выполнения:
    - `application/execution_prepare.py`
    - `SchedulerTaskExecutor` использует `prepare_execution_inputs(...)` в `execute(...)`;
  - вынесен helper постановки decision retry в scheduler:
    - `application/decision_retry_enqueue.py`
    - `SchedulerTaskExecutor` использует `enqueue_decision_retry(...)` в `_enqueue_decision_retry`;
  - вынесен helper обновления workflow phase:
    - `application/workflow_phase_update.py`
    - `SchedulerTaskExecutor` использует `update_zone_workflow_phase(...)` в `_update_zone_workflow_phase`;
  - вынесен helper постановки two-tank check в scheduler:
    - `application/two_tank_enqueue.py`
    - `SchedulerTaskExecutor` использует `enqueue_two_tank_check(...)` в `_enqueue_two_tank_check`;
  - вынесен helper two-tank enqueue-failure compensation:
    - `application/two_tank_compensation.py`
    - `SchedulerTaskExecutor` использует `compensate_two_tank_start_enqueue_failure(...)`
      в `_compensate_two_tank_start_enqueue_failure`;
  - вынесен helper two-tank safety guard logging:
    - `application/two_tank_logging.py`
    - `SchedulerTaskExecutor` использует `log_two_tank_safety_guard(...)`
      в `_log_two_tank_safety_guard`;
  - вынесен helper batch-публикации команд:
    - `application/command_publish_batch.py`
    - `SchedulerTaskExecutor` использует `publish_batch(...)` в `_publish_batch`;
  - вынесен helper core-ветки выполнения device task:
    - `application/device_task_core.py`
    - `SchedulerTaskExecutor` использует `execute_device_task_core(...)` в `_execute_device_task_core`;
  - вынесен helper core-ветки выполнения two-tank command plan:
    - `application/two_tank_command_plan_core.py`
    - `SchedulerTaskExecutor` использует `dispatch_two_tank_command_plan_core(...)`
      в `_dispatch_two_tank_command_plan_core`;
  - вынесен helper merge-агрегации command dispatch результатов:
    - `application/dispatch_merge.py`
    - `SchedulerTaskExecutor` использует `merge_command_dispatch_results(...)`
      в `_merge_command_dispatch_results`;
  - вынесен helper ventilation climate guards:
    - `application/ventilation_climate_guards.py`
    - `SchedulerTaskExecutor` использует `apply_ventilation_climate_guards(...)`
      в `_apply_ventilation_climate_guards`;
  - вынесен helper two-tank runtime config:
    - `application/two_tank_runtime_config.py`
    - `SchedulerTaskExecutor` использует
      `default_two_tank_command_plan(...)`, `normalize_command_plan(...)`,
      `resolve_two_tank_runtime_config(...)` в соответствующих thin wrappers;
  - вынесен helper workflow phase sync core:
    - `application/workflow_phase_sync_core.py`
    - `SchedulerTaskExecutor` использует `sync_zone_workflow_phase_core(...)`
      в `_sync_zone_workflow_phase_core` c сохранением fail-closed флага
      `_workflow_state_persist_failed`;
  - вынесен helper sensor mode dispatch:
    - `application/sensor_mode_dispatch.py`
    - `SchedulerTaskExecutor` использует
      `dispatch_sensor_mode_command_for_nodes(...)`
      в `_dispatch_sensor_mode_command_for_nodes`;
  - вынесен helper two-tank recovery transition:
    - `application/two_tank_recovery_transition.py`
    - `SchedulerTaskExecutor` использует
      `try_start_two_tank_irrigation_recovery_from_irrigation_failure(...)`
      в `_try_start_two_tank_irrigation_recovery_from_irrigation_failure`;
  - вынесен helper refill command resolver:
    - `application/refill_command_resolver.py`
    - `SchedulerTaskExecutor` использует `resolve_refill_command(...)`
      в `_resolve_refill_command`;
  - вынесен helper diagnostics execution:
    - `application/diagnostics_execution.py`
    - `SchedulerTaskExecutor` использует `execute_diagnostics(...)`
      в `_execute_diagnostics`;
  - вынесен helper стартовых фаз two-tank:
    - `application/two_tank_phase_starters.py`
    - `SchedulerTaskExecutor` использует:
      `start_two_tank_clean_fill(...)`, `start_two_tank_solution_fill(...)`,
      `start_two_tank_prepare_recirculation(...)`,
      `start_two_tank_irrigation_recovery(...)`;
  - вынесен helper роутинга diagnostics task:
    - `application/diagnostics_task_execution.py`
    - `SchedulerTaskExecutor` использует `execute_diagnostics_task(...)`
      в `_execute_diagnostics_task`;
  - вынесен helper orchestration-потока execute:
    - `application/executor_run.py`
    - `SchedulerTaskExecutor.execute(...)` использует
      `run_scheduler_executor_execute(...)`;
  - вынесен helper инициализации runtime-компонентов executor:
    - `application/executor_init.py`
    - `SchedulerTaskExecutor.__init__(...)` использует
      `initialize_executor_components(...)`;
  - вынесены runtime-константы/feature-flags/reason-codes executor:
    - `application/executor_constants.py`
    - `SchedulerTaskExecutor` импортирует значения из единого модуля
      constants вместо локальных больших блоков в `scheduler_executor_impl.py`;
  - вынесены delegate-вызовы verbose policy wiring:
    - `application/executor_method_delegates.py`
    - `SchedulerTaskExecutor` использует delegates для
      workflow-phase sync и two-tank start/recovery методов;
  - вынесены medium-size delegates executor:
    - `application/executor_small_delegates.py`
    - `SchedulerTaskExecutor` использует delegates для
      `_update_zone_workflow_phase`, `_publish_batch`,
      `_execute_device_task_core`, `_build_two_tank_runtime_payload`;
  - вынесены event delegates executor:
    - `application/executor_event_delegates.py`
    - `SchedulerTaskExecutor` использует delegates для
      `_emit_task_event` и `_merge_with_sensor_mode_deactivate`;
  - вынесены bound core-методы executor:
    - `application/executor_bound_core_methods.py`
    - `SchedulerTaskExecutor` использует class-bound методы для
      `_create_zone_event_safe`, `_sync_zone_workflow_phase_core`,
      `_emit_task_event`, `_update_zone_workflow_phase`, `_publish_batch`,
      `_enqueue_decision_retry`, `_ensure_extended_outcome`,
      `_execute_diagnostics_task`, `_dispatch_diagnostics_workflow`;
  - вынесены bound workflow-методы executor:
    - `application/executor_bound_workflow_methods.py`
    - `SchedulerTaskExecutor` использует class-bound методы для
      `_execute_two_tank_startup_workflow`, `_execute_two_tank_startup_workflow_core`,
      `_execute_three_tank_startup_workflow`, `_execute_three_tank_startup_workflow_core`,
      `_execute_cycle_start_workflow`, `_execute_cycle_start_workflow_core`,
      `_execute_diagnostics`;
  - вынесены bound refill/cycle-start helper-методы executor:
    - `application/executor_bound_refill_methods.py`
    - `SchedulerTaskExecutor` использует class-bound методы для
      `_resolve_required_node_types`, `_resolve_clean_tank_threshold`,
      `_resolve_refill_duration_ms`, `_resolve_refill_attempt`,
      `_resolve_refill_started_at`, `_resolve_refill_timeout_at`,
      `_build_refill_check_payload`, `_check_required_nodes_online`,
      `_read_clean_tank_level`, `_resolve_refill_command`;
  - вынесены bound misc helper-методы executor:
    - `application/executor_bound_misc_methods.py`
    - `SchedulerTaskExecutor` использует class-bound методы для
      `_emit_cycle_alert`, `_build_two_tank_check_payload`,
      `_log_two_tank_safety_guard`, `_build_two_tank_stop_not_confirmed_result`;
  - вынесены static policy-wrapper методы executor:
    - `application/executor_bound_policy_static_methods.py`
    - `SchedulerTaskExecutor` использует `staticmethod(...)` aliases для
      decision/input/normalization wrappers
      (`_decide_action`, `_safe_*`, `_extract_*`, `_resolve_*` и др.);
  - вынесены bound workflow-input/runtime методы executor:
    - `application/executor_bound_workflow_input_methods.py`
    - `SchedulerTaskExecutor` использует class-bound методы для
      `_extract_workflow`, `_is_cycle_start_workflow`,
      `_normalize_two_tank_workflow`, `_is_two_tank_startup_workflow`,
      `_is_three_tank_startup_workflow`, `_default_two_tank_command_plan`,
      `_normalize_command_plan`, `_resolve_two_tank_runtime_config`,
      `_build_diagnostics_invalid_payload_result`;
  - вынесены bound query/dispatch методы executor:
    - `application/executor_bound_query_dispatch_methods.py`
    - `SchedulerTaskExecutor` использует class-bound/static-bound методы для
      `_get_zone_nodes`, `_read_level_switch`, `_read_latest_metric`,
      `_is_value_within_pct`, `_evaluate_ph_ec_targets`,
      `_find_zone_event_since`, `_resolve_online_node_for_channel`,
      `_dispatch_sensor_mode_command_for_nodes`,
      `_merge_command_dispatch_results`, `_dispatch_two_tank_command_plan`,
      `_dispatch_two_tank_command_plan_core`,
      `_two_tank_safety_guards_enabled`;
  - вынесены bound runtime helper-методы executor:
    - `application/executor_bound_runtime_methods.py`
    - `SchedulerTaskExecutor` использует class-bound методы для
      `_execute_device_task`, `_execute_device_task_core`,
      `_apply_ventilation_climate_guards`, `_build_two_tank_runtime_payload`;
  - вынесены bound workflow-phase/runtime helper-методы executor:
    - `application/executor_bound_phase_methods.py`
    - `SchedulerTaskExecutor` использует class-bound/static-bound методы для
      `_requires_explicit_workflow`, `_tank_state_machine_enabled`,
      `_telemetry_freshness_enforce`, `_telemetry_freshness_max_age_sec`,
      `_extract_workflow_hint`, `_derive_workflow_phase`,
      `_build_workflow_state_payload`, `_resolve_workflow_stage_for_state_sync`,
      `_sync_zone_workflow_phase`;
  - вынесен automation-state/timeline helper-блок API:
    - `application/api_automation_state.py`
    - `api.py` использует thin wrappers для
      `_derive_automation_state`, `_resolve_state_started_at`,
      `_estimate_progress_percent`, `_estimate_completion_seconds`,
      `_derive_active_processes`, `_extract_timeline_reason`,
      `_build_timeline_label`;
  - вынесен payload parsing/coercion helper-блок API:
    - `application/api_payload_parsing.py`
    - `api.py` использует thin wrappers для
      `_to_optional_int`, `_to_optional_float`, `_coerce_datetime`,
      `_extract_workflow`, `_extract_topology`;
  - вынесен task snapshot helper-блок API:
    - `application/api_task_snapshot.py`
    - `api.py` использует thin wrappers для
      `_is_task_active`, `_task_sort_key`,
      `_pick_preferred_zone_task`, `_sanitize_scheduler_task_snapshot`;
  - добавлен `infrastructure/observability.py` для стандартного structured logging.
  - добавлен guard rail по размеру файлов: `test_line_budget.py` (non-regression budget).
  - добавлены unit-тесты policy:
    - `test_decision_policy.py`
    - `test_workflow_phase_policy.py`
    - `test_cycle_start_refill_policy.py`
    - `test_two_tank_guard_policy.py`
    - `test_normalization_policy.py`
    - `test_diagnostics_policy.py`
    - `test_workflow_input_policy.py`
    - `test_decision_detail_policy.py`
    - `test_command_mapping_policy.py`
    - `test_outcome_policy.py`
    - `test_outcome_enrichment_policy.py`
    - `test_task_events.py`
    - `test_task_events_persistence.py`
    - `test_cycle_alerts.py`
    - `test_task_context.py`
    - `test_execution_flow_policy.py`
    - `test_execution_logging.py`
    - `test_decision_alerts.py`
    - `test_execution_branches.py`
    - `test_no_action_branch.py`
    - `test_execution_finalize.py`
    - `test_execution_startup.py`
    - `test_execution_decision.py`
    - `test_execution_prepare.py`
    - `test_decision_retry_enqueue.py`
    - `test_workflow_phase_update.py`
    - `test_two_tank_enqueue.py`
    - `test_two_tank_compensation.py`
    - `test_two_tank_logging.py`
    - `test_command_publish_batch.py`
    - `test_device_task_core.py`
    - `test_two_tank_command_plan_core.py`
    - `test_dispatch_merge.py`
    - `test_ventilation_climate_guards.py`
    - `test_two_tank_runtime_config.py`
    - `test_workflow_phase_sync_core.py`
    - `test_sensor_mode_dispatch.py`
    - `test_two_tank_recovery_transition.py`
    - `test_refill_command_resolver.py`
    - `test_diagnostics_execution.py`
    - `test_two_tank_phase_starters.py`
    - `test_diagnostics_task_execution.py`
    - `test_executor_run.py`
    - `test_target_evaluation_policy.py`.
  - добавлены unit-тесты query adapters:
    - `test_query_adapters.py`.

## 🏗️ Архитектура

### Слоистая архитектура

```
┌─────────────────────────────────────┐
│         main.py (Entry Point)        │
│  - Конфигурация из Laravel API      │
│  - Параллельная обработка зон       │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│   ZoneAutomationService (Service)    │
│  - Оркестрация обработки зоны        │
│  - Координация контроллеров          │
└──────────────┬──────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
┌───▼────────┐    ┌───────▼──────────┐
│ Controllers│    │  Repositories    │
│ - pH/EC    │    │  - Zone          │
│ - Climate  │    │  - Telemetry     │
│ - Light    │    │  - Node          │
│ - Irrigation│   │  - Recipe        │
└───┬────────┘    └───────┬──────────┘
    │                     │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │   Infrastructure    │
    │  - CommandBus (REST)│
    │  - Error Handler    │
    │  - Retry Mechanism  │
    └─────────────────────┘
```

### Основные компоненты

#### 1. **Services** (`services/`)
- `ZoneAutomationService` - оркестрация обработки зоны, координация всех контроллеров

#### 2. **Repositories** (`repositories/`)
- `ZoneRepository` - доступ к данным зон и capabilities
- `TelemetryRepository` - доступ к телеметрии
- `NodeRepository` - доступ к узлам
- `RecipeRepository` - доступ к рецептам и фазам

#### 3. **Controllers** (корневая директория)
- `CorrectionController` - универсальный контроллер для pH/EC корректировки
- `ClimateController` - управление климатом (температура, влажность, CO₂)
- `LightController` - управление освещением и фотопериодом
- `IrrigationController` - управление поливом и рециркуляцией

#### 4. **Infrastructure** (`infrastructure/`)
- `CommandBus` - централизованная публикация команд через history-logger REST API
- `WorkflowStateStore` - DB-backed persistence для `zone_workflow_state` (workflow recovery)
- `error_handler.py` - централизованная обработка ошибок
- `exceptions.py` - кастомные исключения
- `utils/retry.py` - retry механизм для критических операций

#### 5. **Configuration** (`config/`)
- `settings.py` - централизованные настройки (пороги, интервалы, множители)

### Scheduler Task API (planner contract)

`automation-engine` принимает от `scheduler` абстрактные задачи расписания:

- `POST /zones/{zone_id}/start-cycle` -> каноничный wake-up для запуска цикла
- `GET /zones/{zone_id}/state` -> текущий state workflow автоматики зоны для UI-панели
- `GET /zones/{zone_id}/control-mode` -> активный режим (`auto|semi|manual`) и разрешенные manual-step
- `POST /zones/{zone_id}/control-mode` -> переключение режима
- `POST /zones/{zone_id}/manual-step` -> запуск ручного шага (только в `semi|manual`)
- `GET /health/live` -> liveness probe
- `GET /health/ready` -> readiness probe (`CommandBus + DB`)

Поддерживаемые `task_type`:
- `irrigation`
- `lighting`
- `ventilation`
- `solution_change`
- `mist`
- `diagnostics`

Важно: scheduler не должен отправлять device-level команды напрямую.  
Детализация и исполнение задач выполняются внутри `automation-engine` через `CommandBus`.

Дополнительно:
- `idempotency_key` в `POST /zones/{zone_id}/start-cycle` обязателен;
- повторный вызов с тем же `idempotency_key` возвращает deduplicated `accepted` без двойного исполнения.

Маппинг `task_type -> node_types/cmd/params` вынесен в `config/scheduler_task_mapping.py` и поддерживает override из `payload.config.execution`.
Снимки статусов scheduler-task (`accepted/running/completed/failed`) сохраняются в `scheduler_logs` для восстановления после рестарта.

## 🚀 Возможности

### Основной функционал
- ✅ Параллельная обработка зон (до 5 одновременно)
- ✅ Batch запросы к БД (оптимизация производительности)
- ✅ Автоматическая корректировка pH/EC
- ✅ Управление климатом (температура, влажность, вентиляция)
- ✅ Управление освещением (фотопериод, интенсивность)
- ✅ Управление поливом и рециркуляцией
- ✅ Мониторинг здоровья зон (health score)
- ✅ Автоматические переходы между фазами рецепта

### Надежность
- ✅ Централизованная обработка ошибок
- ✅ Retry механизм для критических операций
- ✅ Валидация входных данных
- ✅ Кастомные исключения с контекстом
- ✅ Структурированное логирование

### Производительность
- ✅ Параллельная обработка зон (ускорение в 3-5 раз)
- ✅ Batch запросы к БД (снижение нагрузки на 40-50%)
- ✅ Оптимизированные SQL запросы с CTE

## 📦 Установка

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск
python main.py
```

## ⚙️ Конфигурация

Настройки находятся в `config/settings.py`:

```python
from config.settings import get_settings

settings = get_settings()
print(settings.MAIN_LOOP_SLEEP_SECONDS)  # 15
print(settings.MAX_CONCURRENT_ZONES)     # 5
print(settings.PH_CORRECTION_THRESHOLD)  # 0.2
```

### Основные настройки

- `MAIN_LOOP_SLEEP_SECONDS` - интервал между циклами обработки (по умолчанию: 15)
- `MAX_CONCURRENT_ZONES` - максимальное количество параллельно обрабатываемых зон (по умолчанию: 5)
- `PH_CORRECTION_THRESHOLD` - минимальная разница для корректировки pH (по умолчанию: 0.2)
- `EC_CORRECTION_THRESHOLD` - минимальная разница для корректировки EC (по умолчанию: 0.2)
- `PH_DOSING_MULTIPLIER` - множитель для расчета дозировки pH (по умолчанию: 10.0)
- `EC_DOSING_MULTIPLIER` - множитель для расчета дозировки EC (по умолчанию: 100.0)

## 🧪 Тестирование

```bash
# Запуск всех тестов
pytest automation-engine/ -v

# Запуск конкретного теста
pytest automation-engine/test_correction_controller.py -v

# С покрытием кода
pytest automation-engine/ --cov=automation-engine --cov-report=html
```

### Покрытие тестами

- **72+ тестов** покрывают основные компоненты
- **100% покрытие** для новых компонентов (exceptions, error_handler, config, retry)
- **Основные контроллеры** покрыты тестами
- **Репозитории** покрыты тестами с моками БД

## 📊 Метрики Prometheus

Метрики доступны на порту 9401 (настраивается в `config/settings.py`):

- `automation_loop_errors_total` - ошибки в главном цикле
- `config_fetch_errors_total` - ошибки получения конфигурации
- `config_fetch_success_total` - успешные получения конфигурации
- `zone_checks_total` - количество проверок зон
- `zone_check_seconds` - длительность проверки зоны
- `automation_commands_sent_total{zone_id, metric}` - отправленные команды
- `rest_command_errors_total{error_type}` - ошибки REST запросов к history-logger
- `command_rest_latency_seconds` - задержка REST запросов
- `automation_errors_total` - общие ошибки автоматизации

## 🔧 Использование

### Базовое использование

```python
from services import ZoneAutomationService
from repositories import ZoneRepository, TelemetryRepository, NodeRepository, RecipeRepository
from infrastructure import CommandBus

# Инициализация
zone_repo = ZoneRepository()
telemetry_repo = TelemetryRepository()
node_repo = NodeRepository()
recipe_repo = RecipeRepository()

# CommandBus использует REST API для публикации команд
history_logger_url = "http://history-logger:9300"
history_logger_token = os.getenv("HISTORY_LOGGER_API_TOKEN") or os.getenv("PY_INGEST_TOKEN")
command_bus = CommandBus(
    mqtt=None,  # Deprecated, не используется
    gh_uid="gh-1",
    history_logger_url=history_logger_url,
    history_logger_token=history_logger_token
)

# Создание сервиса
zone_service = ZoneAutomationService(
    zone_repo, telemetry_repo, node_repo, recipe_repo, command_bus
)

# Обработка зоны
await zone_service.process_zone(zone_id=1)
```

### Использование CorrectionController

```python
from correction_controller import CorrectionController, CorrectionType

# Создание контроллера для pH
ph_controller = CorrectionController(CorrectionType.PH)

# Проверка и корректировка
command = await ph_controller.check_and_correct(
    zone_id=1,
    targets={"ph": {"target": 6.5}},
    telemetry={"PH": 6.2},
    nodes={"irrig:default": {"node_uid": "nd-1", "channel": "default", "type": "irrig"}},
    water_level_ok=True
)

# Применение корректировки
if command:
    await ph_controller.apply_correction(command, command_bus)
```

### Обработка ошибок

```python
from error_handler import handle_zone_error, error_handler
from exceptions import ZoneNotFoundError

# Ручная обработка
try:
    await zone_service.process_zone(1)
except Exception as e:
    handle_zone_error(1, e, {"action": "process_zone"})

# Автоматическая обработка через декоратор
@error_handler(zone_id=1, default_return=None)
async def process_zone_safe(zone_id: int):
    await zone_service.process_zone(zone_id)
```

## 📁 Структура проекта

```
automation-engine/
├── main.py                      # Точка входа
├── config/                      # Конфигурация
│   ├── __init__.py
│   └── settings.py              # Настройки
├── repositories/                # Слой доступа к данным
│   ├── __init__.py
│   ├── zone_repository.py
│   ├── telemetry_repository.py
│   ├── node_repository.py
│   └── recipe_repository.py
├── services/                    # Сервисный слой
│   ├── __init__.py
│   └── zone_automation_service.py
├── infrastructure/              # Инфраструктура
│   ├── __init__.py
│   ├── command_bus.py          # REST API для команд
│   ├── command_validator.py    # Валидация команд
│   ├── command_tracker.py      # Отслеживание команд
│   └── command_audit.py        # Аудит команд
├── api.py                       # REST API для scheduler
├── utils/                       # Утилиты
│   ├── __init__.py
│   └── retry.py
├── exceptions.py                # Кастомные исключения
├── error_handler.py             # Обработка ошибок
├── correction_controller.py     # Контроллер pH/EC
├── climate_controller.py       # Контроллер климата
├── light_controller.py          # Контроллер освещения
├── irrigation_controller.py    # Контроллер полива
├── health_monitor.py            # Мониторинг здоровья
├── alerts_manager.py            # Управление алертами
├── correction_cooldown.py      # Cooldown для корректировок
└── test_*.py                    # Тесты
```

## 🔄 История рефакторинга

Проект прошел полный рефакторинг с улучшением архитектуры, производительности и надежности:

- ✅ **Этап A**: Исправление критических багов
- ✅ **Этап B**: Выделение Correction Controller (убрано 200+ строк дублирования)
- ✅ **Этап C**: Создание слоя репозиториев
- ✅ **Этап D**: Создание сервисного слоя
- ✅ **Этап E**: Оптимизация производительности (параллелизм, batch запросы)
- ✅ **Этап F**: Улучшение качества кода (конфигурация, обработка ошибок)
- ✅ **Этап G**: Тестирование (72+ тестов)

## 📈 Улучшения производительности

| Метрика | До | После | Улучшение |
|---------|-----|-------|-----------|
| Время обработки 10 зон | ~2.5 мин | ~30 сек | **5x** |
| Запросов к БД на зону | 4+ | 1-2 | **50-75%** |
| Нагрузка на БД | Высокая | Средняя | **40-50%** |

## 📝 Лицензия

Внутренний проект компании.
