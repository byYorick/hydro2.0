# AE2_STATE_SERIALIZATION_AUDIT_S6.md
# AE2 S6: State Serialization Audit

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Цель S6
Проверить полноту crash-recovery через явные serialization contracts для runtime-state и зафиксировать gaps до `S7/S8/S10`.

## 2. Инвентарь runtime-state (фактический)

### 2.1 `ZoneAutomationService` in-memory state
Файл: `backend/services/automation-engine/services/zone_automation_service.py`
1. `self._controller_failures` (`Dict[(zone_id, controller), datetime]`) — строка 189.
2. `self._zone_states` (`Dict[zone_id, Dict[str, Any]]`) — строка 190.
3. `self._controller_cooldown_reported_at` — строка 191.
4. `self._controller_circuit_open_reported_at` — строка 192.
5. `self._correction_sensor_mode_state` — строка 193.

Структура `self._zone_states` инициализируется в `services/zone_state_runtime.py`:
- `error_streak`, `next_allowed_run_at`, `last_backoff_reported_until`, `degraded_alert_active`,
- skip-throttle fields,
- `workflow_phase`, `workflow_phase_updated_at`, `workflow_phase_source`, `workflow_phase_loaded`.

### 2.2 `CorrectionController` in-memory state
Файл: `backend/services/automation-engine/correction_controller.py`
1. `self._pid_by_zone` — строка 65.
2. `self._last_pid_tick` — строка 66.
3. `self._last_target_by_zone` — строка 67.
4. `self._last_target_ts_by_zone` — строка 68.
5. `self._freshness_check_failure_count` — строка 71.

### 2.3 `main.py` process-level runtime state
Файл: `backend/services/automation-engine/main.py`
1. processing-time rolling window: `_avg_processing_time`, `_processing_times` — строки 98-99.
2. lifecycle pointers: `_shutdown_event`, `_zone_service`, `_command_tracker`, `_command_bus` — строки 104-107.
3. alert-throttle state:
- `_last_db_circuit_open_alert_at`,
- `_last_health_unhealthy_alert_at`,
- `_last_health_check_failed_alert_at`,
- `_last_config_unavailable_alert_at`,
- `_last_missing_gh_uid_alert_at`,
- `_last_config_fetch_error_alert_at` — строки 108-118.

### 2.4 `api.py` in-memory runtime state
Файл: `backend/services/automation-engine/api.py`
1. scheduler task cache: `_scheduler_tasks` — строка 175.
2. bootstrap lease cache: `_scheduler_bootstrap_leases` — строка 193.
3. command-effect counters cache: `_command_effect_totals`, `_command_effect_confirmed_totals` — строки 211-212.
4. test/runtime hooks cache: `_test_hooks`, `_zone_states_override` — строки 225-226.
5. background task registry: `_background_tasks` — строка 227.

## 3. Что уже durable (частично закрыто)
1. Workflow phase/state:
- `WorkflowStateStore.get/list_active/set()`
- `backend/services/automation-engine/infrastructure/workflow_state_store.py` (строки 23, 26, 53, 89).

2. PID state:
- `PidStateManager.save_pid_state/load_pid_state/restore_pid_state/save_all_pid_states`
- `backend/services/automation-engine/services/pid_state_manager.py` (строки 15, 18, 78, 125, 185).

3. Scheduler in-flight task recovery:
- `recover_inflight_scheduler_tasks()` в `application/api_recovery.py`.

## 4. Gap-анализ по требованиям S6

### 4.1 Формальный gap
Требование master-plan: все runtime-state структуры должны иметь явные `serialize()/deserialize()`.

Факт:
1. В `automation-engine` нет ни одного явного метода `serialize()/deserialize()` (поиск по коду пустой).
2. Часть state сохраняется через специализированные DB adapters (`WorkflowStateStore`, `PidStateManager`), но без единого versioned serialization contract.
3. Критичные in-memory maps (`_zone_states`, cooldown/alert-throttle caches, target-history maps) при crash теряются.

### 4.2 Риск
1. Неполный crash-recovery для backoff/degraded/safety-throttle поведения.
2. Возможны повторные alert spikes после рестарта.
3. Для single-writer миграции (`S8`) отсутствует формальный snapshot/restore boundary для runtime-state.

## 5. Обязательные действия на следующих этапах
1. `S7`: утвердить unified runtime-state contract:
- `serialize_state() -> dict`
- `deserialize_state(payload) -> None`
- `state_schema_version`.

2. `S8/S10`: внедрить durable checkpointing для:
- `ZoneAutomationService._zone_states` и связанных throttle/cooldown maps,
- `CorrectionController` target-history/freshness counters,
- `main.py` alert-throttle state (минимум в process-safe cache + periodic snapshot).

3. Добавить recovery-тесты:
- crash в середине correction loop,
- crash во время workflow phase transition,
- restart с восстановлением backoff/degraded flags.

## 6. Stage verdict
S6 verdict: `PASS_WITH_CRITICAL_GAPS`.

Итог:
1. Инвентарь и ownership runtime-state зафиксированы.
2. Частичные durable механизмы уже есть.
3. Единый serialization contract и schema-versioning остаются обязательным блоком до `S10` resilience acceptance.
