# Automation-Engine: полный план декомпозиции

**Версия:** v1.0  
**Дата:** 2026-02-16  
**Статус:** В работе (D0 завершён, D1 частично, D2 существенно завершён, D3 в прогрессе)

Связанные документы:
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AUDIT_PLAN.md`
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AGENT_B_EXECUTOR_DECOMPOSITION.md`
- `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`

## 1. Цель

Полностью завершить декомпозицию automation-engine так, чтобы:
- убрать god-object файлы;
- зафиксировать модульные границы `application/domain/infrastructure`;
- сохранить backward-compatible поведение существующих API/контрактов;
- обеспечить ограничение: **каждый ключевой production-файл <= 1000 строк**.

## 2. Область и ограничения

### 2.1. In scope

- `backend/services/automation-engine/application/scheduler_executor_impl.py`
- `backend/services/automation-engine/api.py`
- `backend/services/automation-engine/services/zone_automation_service.py`
- `backend/services/automation-engine/correction_controller.py`
- связанные unit/e2e тесты и документация `doc_ai/*`

### 2.2. Out of scope

- изменения MQTT namespace и transport контрактов;
- изменения БД вне миграций Laravel;
- изменения unrelated сервисов вне `automation-engine`.

### 2.3. Неприкосновенные контракты

- путь публикации команд: `Scheduler -> Automation-Engine -> History-Logger -> MQTT -> ESP32`;
- публичная сигнатура `SchedulerTaskExecutor.execute(...)`;
- fail-closed поведение по workflow/payload контрактам;
- существующие scheduler task статусы и idempotency semantics.

## 3. Текущий baseline (2026-02-16)

- `scheduler_task_executor.py`: 59 строк (тонкий coordinator, ок)
- `application/scheduler_executor_impl.py`: 4351 строка (критично)
- `api.py`: 2972 строки (критично)
- `services/zone_automation_service.py`: 2570 строк (критично)
- `correction_controller.py`: 1494 строки (критично)
- `irrigation_controller.py`: 341 строка (ок)

### 3.1. Актуальный прогресс (2026-02-16, после шагов D0/D3)

- `scheduler_task_executor.py`: 59 строк (без изменений, целевой coordinator)
- `application/scheduler_executor_impl.py`: **413** строк (было 4351)
- `application/task_events.py`: 36 строк
- `application/task_events_persistence.py`: 58 строк
- `application/cycle_alerts.py`: 32 строки
- `application/task_context.py`: 18 строк
- `application/execution_flow_policy.py`: 115 строк
- `application/execution_logging.py`: 71 строка
- `application/decision_alerts.py`: 49 строк
- `application/execution_branches.py`: 63 строки
- `application/no_action_branch.py`: 54 строки
- `application/execution_finalize.py`: 85 строк
- `application/execution_startup.py`: 51 строка
- `application/execution_decision.py`: 44 строки
- `application/execution_prepare.py`: 24 строки
- `application/decision_retry_enqueue.py`: 81 строка
- `application/workflow_phase_update.py`: 65 строк
- `application/two_tank_enqueue.py`: 45 строк
- `application/two_tank_compensation.py`: 54 строки
- `application/two_tank_logging.py`: 33 строки
- `application/command_publish_batch.py`: 183 строки
- `application/device_task_core.py`: 83 строки
- `application/two_tank_command_plan_core.py`: 105 строк
- `application/dispatch_merge.py`: 42 строки
- `application/ventilation_climate_guards.py`: 115 строк
- `application/two_tank_runtime_config.py`: 266 строк
- `application/workflow_phase_sync_core.py`: 174 строки
- `application/sensor_mode_dispatch.py`: 60 строк
- `application/two_tank_recovery_transition.py`: 66 строк
- `application/refill_command_resolver.py`: 58 строк
- `application/diagnostics_execution.py`: 135 строк
- `application/two_tank_phase_starters.py`: 549 строк
- `application/diagnostics_task_execution.py`: 72 строки
- `application/executor_run.py`: 213 строк
- `application/executor_init.py`: 62 строки
- `application/executor_constants.py`: 155 строк
- `application/executor_method_delegates.py`: 231 строка
- `application/executor_small_delegates.py`: 140 строк
- `application/executor_event_delegates.py`: 63 строки
- `application/executor_bound_core_methods.py`: 243 строки
- `application/executor_bound_workflow_methods.py`: 153 строки
- `application/executor_bound_refill_methods.py`: 164 строки
- `application/executor_bound_misc_methods.py`: 103 строки
- `application/executor_bound_policy_static_methods.py`: 244 строки
- `application/executor_bound_workflow_input_methods.py`: 119 строк
- `application/executor_bound_query_dispatch_methods.py`: 212 строк
- `application/executor_bound_runtime_methods.py`: 90 строк
- `application/executor_bound_phase_methods.py`: 122 строки
- `application/api_automation_state.py`: 234 строки
- `application/api_payload_parsing.py`: 70 строк
- `application/api_task_snapshot.py`: 77 строк
- `api.py`: 2859 строк
- `services/zone_automation_service.py`: 2570 строк
- `correction_controller.py`: 1494 строки
- `domain/workflows/two_tank_core.py`: **133** строки (было 1017)
- `domain/workflows/two_tank_startup_core.py`: 732 строки
- `domain/workflows/two_tank_recovery_core.py`: 243 строки
- `infrastructure/node_query_adapter.py`: 214 строк
- `infrastructure/telemetry_query_adapter.py`: 352 строки
- `domain/policies/target_evaluation_policy.py`: 71 строка
- `domain/policies/cycle_start_refill_policy.py`: 159 строк
- `domain/policies/two_tank_guard_policy.py`: 70 строк
- `domain/policies/normalization_policy.py`: 63 строки
- `domain/policies/diagnostics_policy.py`: 30 строк
- `domain/policies/workflow_input_policy.py`: 123 строки
- `domain/policies/decision_detail_policy.py`: 56 строк
- `domain/policies/command_mapping_policy.py`: 79 строк
- `domain/policies/outcome_policy.py`: 40 строк
- `domain/policies/outcome_enrichment_policy.py`: 101 строка

### 3.2. Оперативный статус валидации (2026-02-16)

- Основной decomposition regression-пакет зелёный:
  - `31 passed, 1 warning`
  - запуск: `test_executor_run.py`, `test_diagnostics_task_execution.py`,
    `test_two_tank_phase_starters.py`, `test_diagnostics_execution.py`,
    `test_refill_command_resolver.py`, `test_two_tank_recovery_transition.py`,
    `test_sensor_mode_dispatch.py`, `test_workflow_phase_sync_core.py`,
    `test_ventilation_climate_guards.py`, `test_two_tank_runtime_config.py`,
    `test_line_budget.py`.
- Текущий warning:
  - `PytestConfigWarning: Unknown config option: asyncio_mode`.
- Ограничение окружения:
  - `test_api.py` не выполняется локально в текущем окружении из-за отсутствующей зависимости `httpx`
    (`ModuleNotFoundError: No module named 'httpx'`), поэтому API-декомпозиция валидируется
    через regression-пакет + pyflakes до установки `httpx`.

Сделано:
1. D0: добавлен non-regression line-budget gate `backend/services/automation-engine/test_line_budget.py`.
2. D1 (частично): вынесены decision model/policy:
 - `backend/services/automation-engine/domain/models/decision_models.py`
 - `backend/services/automation-engine/domain/policies/decision_policy.py`
3. D1 (частично): вынесена workflow phase/stage policy:
 - `backend/services/automation-engine/application/workflow_phase_policy.py`
 - `SchedulerTaskExecutor` переключен на thin wrappers к policy.
4. D1 (частично): разделён two-tank workflow core:
 - `backend/services/automation-engine/domain/workflows/two_tank_core.py` (координатор)
 - `backend/services/automation-engine/domain/workflows/two_tank_startup_core.py`
 - `backend/services/automation-engine/domain/workflows/two_tank_recovery_core.py`
5. D2 (частично): вынесены node/telemetry query adapters из scheduler coordinator:
 - `backend/services/automation-engine/infrastructure/node_query_adapter.py`
 - `backend/services/automation-engine/infrastructure/telemetry_query_adapter.py`
 - `SchedulerTaskExecutor` переведён на thin wrappers для `_get_zone_nodes`, `_resolve_online_node_for_channel`,
   `_check_required_nodes_online`, `_read_level_switch`, `_read_latest_metric`,
   `_read_clean_tank_level`, `_find_zone_event_since`, `_resolve_refill_command`.
6. D2 (частично): вынесен target evaluation policy:
 - `backend/services/automation-engine/domain/policies/target_evaluation_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers `_is_value_within_pct`, `_evaluate_ph_ec_targets`.
7. Добавлены unit-тесты вынесенных policy/adapters:
 - `backend/services/automation-engine/test_decision_policy.py`
 - `backend/services/automation-engine/test_workflow_phase_policy.py`
 - `backend/services/automation-engine/test_query_adapters.py`
 - `backend/services/automation-engine/test_target_evaluation_policy.py`
8. D2 (частично): вынесен cycle-start refill helper-блок:
 - `backend/services/automation-engine/domain/policies/cycle_start_refill_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers `_resolve_required_node_types`,
   `_resolve_clean_tank_threshold`, `_resolve_refill_duration_ms`, `_resolve_refill_attempt`,
   `_resolve_refill_started_at`, `_resolve_refill_timeout_at`, `_build_refill_check_payload`.
 - добавлен unit-тест `backend/services/automation-engine/test_cycle_start_refill_policy.py`.
9. D2 (частично): вынесены two-tank payload/result helpers:
 - `backend/services/automation-engine/domain/policies/two_tank_guard_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers `_build_two_tank_check_payload`,
   `_build_two_tank_stop_not_confirmed_result`.
 - добавлен unit-тест `backend/services/automation-engine/test_two_tank_guard_policy.py`.
10. D2 (частично): вынесены shared normalization/coercion helpers:
 - `backend/services/automation-engine/domain/policies/normalization_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers `_resolve_int`, `_resolve_float`,
   `_normalize_labels`, `_canonical_sensor_label`, `_merge_dict_recursive`.
 - добавлен unit-тест `backend/services/automation-engine/test_normalization_policy.py`.
11. D2 (частично): вынесен diagnostics invalid-payload result helper:
 - `backend/services/automation-engine/domain/policies/diagnostics_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper `_build_diagnostics_invalid_payload_result`.
 - добавлен unit-тест `backend/services/automation-engine/test_diagnostics_policy.py`.
12. D2 (частично): вынесены workflow input extract/normalize helpers:
 - `backend/services/automation-engine/domain/policies/workflow_input_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers `_extract_execution_config`, `_extract_refill_config`,
   `_extract_payload_contract_version`, `_is_supported_payload_contract_version`, `_extract_workflow`,
   `_extract_topology`, `_normalize_two_tank_workflow`, `_is_two_tank_startup_workflow`,
   `_is_three_tank_startup_workflow`.
 - добавлен unit-тест `backend/services/automation-engine/test_workflow_input_policy.py`.
13. D2 (частично): вынесены decision detail helpers:
 - `backend/services/automation-engine/domain/policies/decision_detail_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers `_to_optional_float`, `_with_decision_details`.
 - удалён неиспользуемый импорт `math` из `scheduler_executor_impl.py`.
 - добавлен unit-тест `backend/services/automation-engine/test_decision_detail_policy.py`.
14. D2 (частично): вынесены command mapping helpers:
 - `backend/services/automation-engine/domain/policies/command_mapping_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers `_terminal_status_to_error_code`,
   `_extract_duration_sec`, `_resolve_command_name`, `_resolve_command_params`.
 - добавлен unit-тест `backend/services/automation-engine/test_command_mapping_policy.py`.
15. D2 (частично): вынесены outcome helpers:
 - `backend/services/automation-engine/domain/policies/outcome_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers `_build_decision_retry_correlation_id`,
   `_extract_two_tank_chemistry_orchestration`.
 - добавлен unit-тест `backend/services/automation-engine/test_outcome_policy.py`.
16. D2 (частично): вынесен outcome enrichment helper-блок:
 - `backend/services/automation-engine/domain/policies/outcome_enrichment_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper `_ensure_extended_outcome`.
 - добавлен unit-тест `backend/services/automation-engine/test_outcome_enrichment_policy.py`.
17. D2 (частично): вынесен task event payload helper-блок:
 - `backend/services/automation-engine/application/task_events.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_emit_task_event` через
   `build_task_event_payload(...)`.
 - добавлен unit-тест `backend/services/automation-engine/test_task_events.py`.
18. D2 (частично): вынесен task event persistence helper-блок:
 - `backend/services/automation-engine/application/task_events_persistence.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_create_zone_event_safe` через
   `persist_zone_event_safe(...)`.
 - добавлен unit-тест `backend/services/automation-engine/test_task_events_persistence.py`.
19. D2 (частично): вынесен cycle alert helper-блок:
 - `backend/services/automation-engine/application/cycle_alerts.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_emit_cycle_alert` через
   `emit_cycle_alert(...)`.
 - добавлен unit-тест `backend/services/automation-engine/test_cycle_alerts.py`.
20. D2 (частично): вынесен helper построения execution context:
 - `backend/services/automation-engine/application/task_context.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `execute(...)` через
   `build_task_context(...)`.
 - добавлен unit-тест `backend/services/automation-engine/test_task_context.py`.
21. D2 (частично): вынесены execution flow payload/result helpers:
 - `backend/services/automation-engine/application/execution_flow_policy.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers в `execute(...)` для:
   `build_task_received_payload`, `build_execution_started_zone_event_payload`,
   `build_decision_payload`, `build_no_action_result`, `apply_decision_defaults`,
   `build_task_finished_payload`, `build_execution_finished_zone_event_payload`.
 - добавлен unit-тест `backend/services/automation-engine/test_execution_flow_policy.py`.
22. D2 (частично): вынесены execution lifecycle logging helpers:
 - `backend/services/automation-engine/application/execution_logging.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers в `execute(...)` для:
   `log_execution_started`, `log_execution_finished`.
 - добавлен unit-тест `backend/services/automation-engine/test_execution_logging.py`.
23. D2 (частично): вынесен decision infra-alert helper-блок:
 - `backend/services/automation-engine/application/decision_alerts.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `execute(...)` для no-action ветки:
   `should_emit_decision_alert(...)` + `emit_decision_alert(...)`.
 - добавлен unit-тест `backend/services/automation-engine/test_decision_alerts.py`.
24. D2 (частично): вынесен action-required dispatch helper-блок:
 - `backend/services/automation-engine/application/execution_branches.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `execute(...)` для ветки
   `action_required=True` (`diagnostics`/`device_task`/`irrigation_recovery`).
 - добавлен unit-тест `backend/services/automation-engine/test_execution_branches.py`.
25. D2 (частично): вынесен no-action dispatch helper-блок:
 - `backend/services/automation-engine/application/no_action_branch.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `execute(...)` для ветки
   `action_required=False` (`retry enqueue`/`next_due_at`/decision alert).
 - добавлен unit-тест `backend/services/automation-engine/test_no_action_branch.py`.
26. D2 (частично): вынесен execution finalization helper-блок:
 - `backend/services/automation-engine/application/execution_finalize.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `execute(...)` для блока
   `extended_outcome + workflow_state_sync + finish events + finish log`.
 - добавлен unit-тест `backend/services/automation-engine/test_execution_finalize.py`.
27. D2 (частично): вынесен execution startup helper-блок:
 - `backend/services/automation-engine/application/execution_startup.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `execute(...)` для блока
   `TASK_RECEIVED + TASK_STARTED + SCHEDULE_TASK_EXECUTION_STARTED`.
 - добавлен unit-тест `backend/services/automation-engine/test_execution_startup.py`.
28. D2 (частично): вынесен execution decision helper-блок:
 - `backend/services/automation-engine/application/execution_decision.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `execute(...)` для блока
   `_decide_action + climate_guards + DECISION_MADE`.
 - добавлен unit-тест `backend/services/automation-engine/test_execution_decision.py`.
29. D2 (частично): вынесен execution prepare helper-блок:
 - `backend/services/automation-engine/application/execution_prepare.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `execute(...)` для блока
   `task_type/payload/config/mapping normalization`.
 - добавлен unit-тест `backend/services/automation-engine/test_execution_prepare.py`.
30. D2 (частично): вынесен decision retry enqueue helper-блок:
 - `backend/services/automation-engine/application/decision_retry_enqueue.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_enqueue_decision_retry`.
 - добавлен unit-тест `backend/services/automation-engine/test_decision_retry_enqueue.py`.
31. D2 (частично): вынесен workflow phase update helper-блок:
 - `backend/services/automation-engine/application/workflow_phase_update.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_update_zone_workflow_phase`.
 - добавлен unit-тест `backend/services/automation-engine/test_workflow_phase_update.py`.
32. D2 (частично): вынесен two-tank enqueue helper-блок:
 - `backend/services/automation-engine/application/two_tank_enqueue.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_enqueue_two_tank_check`.
 - добавлен unit-тест `backend/services/automation-engine/test_two_tank_enqueue.py`.
33. D2 (частично): вынесен two-tank compensation helper-блок:
 - `backend/services/automation-engine/application/two_tank_compensation.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в
   `_compensate_two_tank_start_enqueue_failure`.
 - добавлен unit-тест `backend/services/automation-engine/test_two_tank_compensation.py`.
34. D2 (частично): вынесен two-tank safety logging helper-блок:
 - `backend/services/automation-engine/application/two_tank_logging.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_log_two_tank_safety_guard`.
 - добавлен unit-тест `backend/services/automation-engine/test_two_tank_logging.py`.
35. D2 (частично): вынесен command publish-batch helper-блок:
 - `backend/services/automation-engine/application/command_publish_batch.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_publish_batch`.
 - добавлен unit-тест `backend/services/automation-engine/test_command_publish_batch.py`.
36. D2 (частично): вынесен device-task core helper-блок:
 - `backend/services/automation-engine/application/device_task_core.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_execute_device_task_core`.
 - добавлен unit-тест `backend/services/automation-engine/test_device_task_core.py`.
37. D2 (частично): вынесен two-tank command-plan core helper-блок:
 - `backend/services/automation-engine/application/two_tank_command_plan_core.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_dispatch_two_tank_command_plan_core`.
 - добавлен unit-тест `backend/services/automation-engine/test_two_tank_command_plan_core.py`.
38. D2 (частично): вынесен dispatch merge helper-блок:
 - `backend/services/automation-engine/application/dispatch_merge.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_merge_command_dispatch_results`.
 - добавлен unit-тест `backend/services/automation-engine/test_dispatch_merge.py`.
39. D2 (частично): вынесен ventilation climate guards helper-блок:
 - `backend/services/automation-engine/application/ventilation_climate_guards.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_apply_ventilation_climate_guards`.
 - добавлен unit-тест `backend/services/automation-engine/test_ventilation_climate_guards.py`.
40. D2 (частично): вынесен two-tank runtime config helper-блок:
 - `backend/services/automation-engine/application/two_tank_runtime_config.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers:
   `_default_two_tank_command_plan`, `_normalize_command_plan`, `_resolve_two_tank_runtime_config`.
 - добавлен unit-тест `backend/services/automation-engine/test_two_tank_runtime_config.py`.
41. D2 (частично): вынесен workflow phase sync core helper-блок:
 - `backend/services/automation-engine/application/workflow_phase_sync_core.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_sync_zone_workflow_phase_core`
   с сохранением семантики `_workflow_state_persist_failed`.
 - добавлен unit-тест `backend/services/automation-engine/test_workflow_phase_sync_core.py`.
42. D2 (частично): вынесен sensor mode dispatch helper-блок:
 - `backend/services/automation-engine/application/sensor_mode_dispatch.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_dispatch_sensor_mode_command_for_nodes`.
 - добавлен unit-тест `backend/services/automation-engine/test_sensor_mode_dispatch.py`.
43. D2 (частично): вынесен two-tank recovery transition helper-блок:
 - `backend/services/automation-engine/application/two_tank_recovery_transition.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в
   `_try_start_two_tank_irrigation_recovery_from_irrigation_failure`.
 - добавлен unit-тест `backend/services/automation-engine/test_two_tank_recovery_transition.py`.
44. D2 (частично): вынесен refill command resolver helper-блок:
 - `backend/services/automation-engine/application/refill_command_resolver.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_resolve_refill_command`.
 - добавлен unit-тест `backend/services/automation-engine/test_refill_command_resolver.py`.
45. D2 (частично): вынесен diagnostics execution helper-блок:
 - `backend/services/automation-engine/application/diagnostics_execution.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_execute_diagnostics`.
 - добавлен unit-тест `backend/services/automation-engine/test_diagnostics_execution.py`.
46. D2 (частично): вынесен helper стартовых фаз two-tank:
 - `backend/services/automation-engine/application/two_tank_phase_starters.py`
 - `SchedulerTaskExecutor` переключён на thin wrappers:
   `_start_two_tank_clean_fill`, `_start_two_tank_solution_fill`,
   `_start_two_tank_prepare_recirculation`, `_start_two_tank_irrigation_recovery`.
 - добавлен unit-тест `backend/services/automation-engine/test_two_tank_phase_starters.py`.
47. D2 (частично): вынесен diagnostics task routing helper-блок:
 - `backend/services/automation-engine/application/diagnostics_task_execution.py`
 - `SchedulerTaskExecutor` переключён на thin wrapper в `_execute_diagnostics_task`.
 - добавлен unit-тест `backend/services/automation-engine/test_diagnostics_task_execution.py`.
48. D2 (частично): вынесен high-level execute orchestration helper-блок:
 - `backend/services/automation-engine/application/executor_run.py`
 - `SchedulerTaskExecutor.execute(...)` переключён на helper `run_scheduler_executor_execute(...)`.
 - добавлен unit-тест `backend/services/automation-engine/test_executor_run.py`.
49. D2 (частично): перенесён execute-wiring из scheduler coordinator в helper-модуль:
 - `backend/services/automation-engine/application/executor_run.py`
 - из `scheduler_executor_impl.py` удалены policy-wiring лямбды для `execute(...)`;
 - coordinator оставлен в виде thin wrapper + runtime dependencies.
50. D2 (частично): вынесена инициализация runtime-компонентов executor:
 - `backend/services/automation-engine/application/executor_init.py`
 - `SchedulerTaskExecutor.__init__(...)` переключён на helper
   `initialize_executor_components(...)`.
51. D2 (частично): вынесены runtime-константы и reason/error-коды executor:
 - `backend/services/automation-engine/application/executor_constants.py`
 - из `scheduler_executor_impl.py` удалены env/helper функции и большие
   блоки constants/reason/error definitions.
52. D2 (частично): вынесены verbose policy delegates методов executor:
 - `backend/services/automation-engine/application/executor_method_delegates.py`
 - `SchedulerTaskExecutor` переключён на delegate-вызовы в:
   `_sync_zone_workflow_phase_core`,
   `_try_start_two_tank_irrigation_recovery_from_irrigation_failure`,
   `_start_two_tank_clean_fill`,
   `_start_two_tank_solution_fill`,
   `_start_two_tank_prepare_recirculation`,
   `_start_two_tank_irrigation_recovery`.
53. D2 (частично): вынесены medium-size wrappers executor в отдельные delegates:
 - `backend/services/automation-engine/application/executor_small_delegates.py`
 - `SchedulerTaskExecutor` переключён на delegate-вызовы в:
   `_update_zone_workflow_phase`,
   `_publish_batch`,
   `_execute_device_task_core`,
   `_build_two_tank_runtime_payload`.
54. D2 (частично): вынесены event delegates executor:
 - `backend/services/automation-engine/application/executor_event_delegates.py`
 - `SchedulerTaskExecutor` переключён на delegate-вызовы в:
   `_emit_task_event`,
   `_merge_with_sensor_mode_deactivate`.
55. D2 (частично): вынесены bound core-методы executor:
 - `backend/services/automation-engine/application/executor_bound_core_methods.py`
 - `SchedulerTaskExecutor` переключён на class-bound методы в:
   `_create_zone_event_safe`,
   `_sync_zone_workflow_phase_core`,
   `_emit_task_event`,
   `_update_zone_workflow_phase`,
   `_publish_batch`,
   `_enqueue_decision_retry`,
   `_ensure_extended_outcome`,
   `_execute_diagnostics_task`,
   `_dispatch_diagnostics_workflow`.
56. D2 (частично): вынесены bound workflow-методы executor:
 - `backend/services/automation-engine/application/executor_bound_workflow_methods.py`
 - `SchedulerTaskExecutor` переключён на class-bound методы в:
   `_execute_two_tank_startup_workflow`,
   `_execute_two_tank_startup_workflow_core`,
   `_execute_three_tank_startup_workflow`,
   `_execute_three_tank_startup_workflow_core`,
   `_execute_cycle_start_workflow`,
   `_execute_cycle_start_workflow_core`,
   `_execute_diagnostics`.
57. D2 (частично): вынесены bound refill/cycle-start helper-методы executor:
 - `backend/services/automation-engine/application/executor_bound_refill_methods.py`
 - `SchedulerTaskExecutor` переключён на class-bound методы в:
   `_resolve_required_node_types`,
   `_resolve_clean_tank_threshold`,
   `_resolve_refill_duration_ms`,
   `_resolve_refill_attempt`,
   `_resolve_refill_started_at`,
   `_resolve_refill_timeout_at`,
   `_build_refill_check_payload`,
   `_check_required_nodes_online`,
   `_read_clean_tank_level`,
   `_resolve_refill_command`.
58. D2 (частично): вынесены bound misc helper-методы executor:
 - `backend/services/automation-engine/application/executor_bound_misc_methods.py`
 - `SchedulerTaskExecutor` переключён на class-bound методы в:
   `_emit_cycle_alert`,
   `_build_two_tank_check_payload`,
   `_log_two_tank_safety_guard`,
   `_build_two_tank_stop_not_confirmed_result`.
59. D2 (частично): вынесены static policy-wrapper методы executor:
 - `backend/services/automation-engine/application/executor_bound_policy_static_methods.py`
 - `SchedulerTaskExecutor` переключён на `staticmethod(...)` aliases для
   decision/input/normalization wrappers:
   `_decide_action`, `_safe_float`, `_safe_int`, `_safe_bool`,
   `_extract_nested_metric`, `_extract_nested_bool`, `_extract_retry_attempt`,
   `_decide_irrigation_action`, `_extract_next_due_at`,
   `_build_decision_retry_correlation_id`,
   `_extract_two_tank_chemistry_orchestration`,
   `_normalize_workflow_stage`, `_normalize_workflow_phase`,
   `_terminal_status_to_error_code`,
   `_extract_duration_sec`, `_resolve_command_name`, `_resolve_command_params`,
   `_extract_execution_config`, `_extract_refill_config`,
   `_extract_payload_contract_version`,
   `_is_supported_payload_contract_version`,
   `_extract_topology`,
   `_to_optional_float`, `_with_decision_details`,
   `_resolve_int`, `_resolve_float`, `_normalize_labels`,
   `_canonical_sensor_label`, `_merge_dict_recursive`,
   `_normalize_text_list`, `_normalize_node_type_list`.
60. D2 (частично): вынесены bound workflow-input/runtime методы executor:
 - `backend/services/automation-engine/application/executor_bound_workflow_input_methods.py`
 - `SchedulerTaskExecutor` переключён на class-bound методы в:
   `_extract_workflow`,
   `_is_cycle_start_workflow`,
   `_normalize_two_tank_workflow`,
   `_is_two_tank_startup_workflow`,
   `_is_three_tank_startup_workflow`,
   `_default_two_tank_command_plan`,
   `_normalize_command_plan`,
   `_resolve_two_tank_runtime_config`,
   `_build_diagnostics_invalid_payload_result`.
61. D2 (частично): вынесены bound query/dispatch методы executor:
 - `backend/services/automation-engine/application/executor_bound_query_dispatch_methods.py`
 - `SchedulerTaskExecutor` переключён на class-bound/static-bound методы в:
   `_get_zone_nodes`,
   `_read_level_switch`,
   `_read_latest_metric`,
   `_is_value_within_pct`,
   `_evaluate_ph_ec_targets`,
   `_find_zone_event_since`,
   `_resolve_online_node_for_channel`,
   `_dispatch_sensor_mode_command_for_nodes`,
   `_merge_command_dispatch_results`,
   `_dispatch_two_tank_command_plan`,
   `_dispatch_two_tank_command_plan_core`,
   `_two_tank_safety_guards_enabled`.
62. D2 (частично): вынесены bound runtime helper-методы executor:
 - `backend/services/automation-engine/application/executor_bound_runtime_methods.py`
 - `SchedulerTaskExecutor` переключён на class-bound методы в:
   `_execute_device_task`,
   `_execute_device_task_core`,
   `_apply_ventilation_climate_guards`,
   `_build_two_tank_runtime_payload`.
63. D2 (частично): вынесены bound workflow-phase/runtime helper-методы executor:
 - `backend/services/automation-engine/application/executor_bound_phase_methods.py`
 - `SchedulerTaskExecutor` переключён на class-bound/static-bound методы в:
   `_requires_explicit_workflow`,
   `_tank_state_machine_enabled`,
   `_telemetry_freshness_enforce`,
   `_telemetry_freshness_max_age_sec`,
   `_extract_workflow_hint`,
   `_derive_workflow_phase`,
   `_build_workflow_state_payload`,
   `_resolve_workflow_stage_for_state_sync`,
   `_sync_zone_workflow_phase`.
64. D3 (частично): вынесен automation-state/timeline helper-блок API:
 - `backend/services/automation-engine/application/api_automation_state.py`
 - `api.py` переключён на thin wrappers в:
   `_derive_automation_state`,
   `_resolve_state_started_at`,
   `_estimate_progress_percent`,
   `_estimate_completion_seconds`,
   `_derive_active_processes`,
   `_extract_timeline_reason`,
   `_build_timeline_label`.
65. D3 (частично): вынесен payload parsing/coercion helper-блок API:
 - `backend/services/automation-engine/application/api_payload_parsing.py`
 - `api.py` переключён на thin wrappers в:
   `_to_optional_int`,
   `_to_optional_float`,
   `_coerce_datetime`,
   `_extract_workflow`,
   `_extract_topology`.
66. D3 (частично): вынесен task snapshot helper-блок API:
 - `backend/services/automation-engine/application/api_task_snapshot.py`
 - `api.py` переключён на thin wrappers в:
   `_is_task_active`,
   `_task_sort_key`,
   `_pick_preferred_zone_task`,
   `_sanitize_scheduler_task_snapshot`.

## 4. Целевая структура (после полной декомпозиции)

```text
backend/services/automation-engine/
  scheduler_task_executor.py                # <= 200
  api.py                                    # <= 900
  application/
    scheduler_executor.py                   # <= 700
    workflow_router.py                      # <= 400
    workflow_validator.py                   # <= 400
    command_dispatch.py                     # <= 500
    workflow_state_sync.py                  # <= 500
    task_context.py                         # <= 300
    task_events.py                          # <= 400
  domain/
    models/
      workflow_models.py                    # <= 400
      command_models.py                     # <= 400
      decision_models.py                    # <= 400
    workflows/
      two_tank_startup.py                   # <= 900
      two_tank_recovery.py                  # <= 800
      three_tank_startup.py                 # <= 700
      cycle_start.py                        # <= 700
    policies/
      decision_policy.py                    # <= 700
      safety_policy.py                      # <= 700
      telemetry_freshness_policy.py         # <= 500
  services/
    zone_automation_service.py              # <= 900
    zone_runtime_coordinator.py             # <= 700
    correction_orchestrator.py              # <= 700
    sensor_mode_orchestrator.py             # <= 500
  controllers/
    correction_controller.py                # <= 900
    correction_ec_batch.py                  # <= 700
    correction_ph_logic.py                  # <= 600
  infrastructure/
    command_bus.py                          # <= 1000
    command_publisher.py                    # <= 400
    workflow_state_store.py                 # <= 600
    observability.py                        # <= 500
    scheduler_task_store.py                 # <= 700
```

Примечание: допускается иная детализация файлов, если сохраняются те же границы ответственности и лимит строк.

## 5. План выполнения по фазам

## Фаза D0: Stabilization & Guard Rails

Цель:
- зафиксировать не меняемые контракты до глубокой декомпозиции.

Действия:
1. Добавить ADR/док секцию с инвариантами контракта scheduler->AE.
2. Ввести check в CI: warning/fail при превышении лимита строк для целевых файлов.
3. Зафиксировать список regression-сценариев как release gate.

Артефакты:
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_FULL_DECOMPOSITION_PLAN.md`
- `.github/workflows/*` или `tests/*` (line-budget check)

Критерий выхода:
- есть автоматический line-budget gate;
- список критичных e2e закреплён в CI job.

## Фаза D1: Scheduler Executor Core Split

Цель:
- разрезать `application/scheduler_executor_impl.py` на независимые модули, оставить coordinator.

Действия:
1. Вынести dataclass/DTO модели в `domain/models/*`.
2. Вынести decision engine в `domain/policies/decision_policy.py`.
3. Разделить two-tank на два файла:
   - `domain/workflows/two_tank_startup.py`
   - `domain/workflows/two_tank_recovery.py`
4. Перенести cycle_start/three_tank в отдельные workflow-файлы.
5. В `application/scheduler_executor.py` оставить orchestration + DI.

Текущий статус:
- [x] Вынесены dataclass/DTO для decision (`DecisionOutcome`).
- [x] Вынесен decision engine (`decision_policy.py`).
- [x] Вынесен workflow phase/stage mapping (`application/workflow_phase_policy.py`).
- [x] Выполнен split two-tank workflow core на `startup/recovery` (+ coordinator).
- [ ] Финальная сборка `application/scheduler_executor.py <= 700`.

Критерий выхода:
- `application/scheduler_executor.py <= 700`;
- ни один workflow-файл не > 1000;
- `test_scheduler_task_executor.py` полностью зелёный.

## Фаза D2: Command/Telemetry Helpers Split

Цель:
- убрать из scheduler-координатора низкоуровневые query/helper блоки.

Действия:
1. Вынести node resolution и telemetry reads в `infrastructure/*` adapters.
2. Вынести evaluation helpers (pH/EC target checks, stale telemetry) в `domain/policies/*`.
3. Оставить в coordinator только вызовы интерфейсов.

Текущий статус:
- [x] Вынесены node resolution и telemetry reads в `infrastructure/*` adapters.
- [x] Evaluation helpers (pH/EC target checks, stale telemetry) вынесены в policy/adapter-модули.
- [x] SQL/query по выбору refill-ноды вынесен в `infrastructure/node_query_adapter.py`.
- [x] Refill helper-политики (threshold/attempt/timeout/payload) вынесены в `domain/policies`.
- [x] Two-tank payload/result helper-политики вынесены в `domain/policies`.
- [x] Shared normalization/coercion helpers вынесены в `domain/policies`.
- [x] Diagnostics invalid-payload helper вынесен в `domain/policies`.
- [x] Workflow input extract/normalize helpers вынесены в `domain/policies`.
- [x] Decision detail helpers вынесены в `domain/policies`.
- [x] Command mapping helpers вынесены в `domain/policies`.
- [x] Outcome helpers вынесены в `domain/policies`.
- [ ] Полный thin-coordinator для helper-блока не завершён.

Критерий выхода:
- coordinator не содержит SQL-строк и сложных вычислений;
- логика stale checks и target evaluation покрыта отдельными unit-тестами.

## Фаза D3: API Layer Decomposition

Цель:
- разрезать `api.py` на модульные entrypoints без изменения внешних endpoint контрактов.

Действия:
1. Вынести scheduler endpoints в `api/scheduler_routes.py`.
2. Вынести health/readiness в `api/health_routes.py`.
3. Вынести recovery/bootstrap logic в `api/recovery_service.py`.
4. Оставить в `api.py` только app bootstrap + router wiring.

Критерий выхода:
- `api.py <= 900`;
- все существующие `test_api.py` проходят без изменения API контрактов.

## Фаза D4: ZoneAutomationService Decomposition

Цель:
- убрать оркестрационный монолит из `zone_automation_service.py`.

Действия:
1. Выделить `zone_runtime_coordinator.py` (state transitions / workflow_phase gates).
2. Выделить `correction_orchestrator.py` (gating + correction flow).
3. Выделить `sensor_mode_orchestrator.py` (activation/deactivation policy).
4. `zone_automation_service.py` оставить thin façade.

Критерий выхода:
- `zone_automation_service.py <= 900`;
- сценарии stale_flags, sensor_unstable, corrections_not_allowed покрыты.

## Фаза D5: Correction Controller Decomposition

Цель:
- разделить EC/pH batch-логику и compensation policy.

Действия:
1. Вынести EC batch planning/partial failure policy в `controllers/correction_ec_batch.py`.
2. Вынести pH branch logic в `controllers/correction_ph_logic.py`.
3. Оставить `correction_controller.py` как coordinator.

Критерий выхода:
- `correction_controller.py <= 900`;
- тесты partial batch + compensation + degraded path зелёные.

## Фаза D6: Observability & Consistency Finalization

Цель:
- унифицировать structured logging и correlation propagation.

Действия:
1. Проверить обязательные поля в логе на всех модульных границах:
   - `component`, `zone_id`, `task_id`, `task_type`, `workflow`, `workflow_phase`,
     `decision`, `reason_code`, `command_count`, `result_status`, `correlation_id`, `duration_ms`.
2. Устранить немые fallback-ветки (только WARNING/ERROR с reason_code).
3. Добавить smoke-тесты на наличие `correlation_id` в критических цепочках.

Критерий выхода:
- нет silent fallback;
- лог-поля консистентны по всем boundary-модулям.

## Фаза D7: Final Hardening & Handover

Цель:
- закрыть технический долг и выдать итоговый handover.

Действия:
1. Полный прогон regression/e2e матрицы (E2E-01..E2E-27).
2. Обновление документации:
   - `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
   - `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md`
   - `backend/services/automation-engine/README.md`
3. Подготовка mapping `old location -> new location` по всем перенесённым функциям.

Критерий выхода:
- все целевые файлы <= 1000 строк;
- тесты и docs синхронизированы;
- handover содержит остаточный tech debt и следующий roadmap.

## 6. Матрица тестов (минимум по фазам)

- D1:
  - `test_scheduler_task_executor.py`
  - `test_workflow_components.py`
- D2:
  - unit на telemetry/node adapters + policies
- D3:
  - `test_api.py` (scheduler tasks, idempotency, recovery)
- D4:
  - `test_zone_automation_service.py`
  - `tests/e2e/test_workflow_coordination.py`
- D5:
  - `test_correction_controller.py`
  - `tests/e2e/test_ec_batch_failure_policy.py`
- D6-D7:
  - полный regression + e2e (E2E-01..E2E-27)

## 7. Quality gates

1. Line budget gate:
   - fail CI, если любой целевой production файл > 1000 строк.
2. Contract gate:
   - fail CI при изменении публичных API без doc update.
3. Observability gate:
   - fail CI при отсутствии обязательных structured полей на boundary-логах.
4. Recovery gate:
   - fail CI, если сценарии restart recovery/phase persistence не проходят.

## 8. Риски и mitigation

Риск: скрытая поведенческая регрессия при переносе больших функций.  
Mitigation: перенос малыми PR-срезами + golden tests до/после.

Риск: деградация производительности из-за лишних абстракций.  
Mitigation: профилирование горячих путей (`dispatch`, `zone loop`) после каждой фазы.

Риск: рассинхрон docs и кода.  
Mitigation: doc update mandatory в каждом PR + checklist в шаблоне PR.

## 9. Формат PR-срезов

Для каждой фазы:
1. Scope только одной подфазы.
2. Изменения кода + тесты + docs в одном PR.
3. Обязательный блок в описании:
   - что вынесено;
   - mapping `old -> new`;
   - доказательство отсутствия breaking changes;
   - результаты тестов.

## 10. Финальный Definition of Done

План считается завершённым, когда одновременно выполнено:
1. `scheduler_executor_impl.py` разделён и заменён на coordinator + domain/application модули.
2. `api.py`, `zone_automation_service.py`, `correction_controller.py` декомпозированы и укладываются в line budget.
3. Публичные контракты scheduler/automation/history-logger не сломаны.
4. Все целевые production-файлы <= 1000 строк.
5. Regression + e2e тесты зелёные.
6. Документация обновлена и содержит актуальное mapping функций.
