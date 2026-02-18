# AE2_RESILIENCE_CONSOLIDATION_S10.md
# AE2 S10: Resilience Consolidation (Increment 1)

**Версия:** v0.2  
**Дата:** 2026-02-18  
**Статус:** IN_PROGRESS

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Scope инкремента
Закрыть практическую часть crash-recovery runtime-state без изменения внешних контрактов и publish pipeline.

## 2. Реализовано
1. Новый runtime snapshot store:
- `backend/services/automation-engine/infrastructure/runtime_state_store.py`.
- атомарная запись JSON (`*.tmp -> replace`) и безопасная загрузка.

2. Runtime-state export/restore для correction policy:
- `backend/services/automation-engine/correction_controller.py`
  - `export_runtime_state()`;
  - `restore_runtime_state(...)`.
- В snapshot входят:
  - `last_target_by_zone`,
  - freshness failure counters,
  - no-effect streaks,
  - pending effect windows,
  - anomaly block windows.

3. Runtime-state export/restore для zone orchestrator:
- `backend/services/automation-engine/services/zone_automation_service.py`
  - `export_runtime_state()`;
  - `restore_runtime_state(...)`.
- В snapshot входят:
  - `_zone_states`,
  - `_controller_failures`,
  - `_controller_cooldown_reported_at`,
  - `_controller_circuit_open_reported_at`,
  - `_correction_sensor_mode_state`,
  - вложенные snapshot pH/EC correction controllers.

4. Lifecycle integration:
- `backend/services/automation-engine/main.py`
  - restore snapshot при первом создании `_zone_service`;
  - save snapshot в graceful shutdown.
- Новые настройки:
  - `AE_RUNTIME_STATE_PERSIST_ENABLED` (default `true`),
  - `AE_RUNTIME_STATE_SNAPSHOT_PATH` (default `/tmp/ae_runtime_state_snapshot.json`).

5. Auto-recovery loop (offline required nodes):
- `backend/services/automation-engine/services/zone_node_recovery.py`
  - `derive_required_node_types(capabilities)`;
  - `evaluate_required_nodes_recovery_gate(...)`.
- Интеграция:
  - `backend/services/automation-engine/services/zone_process_cycle.py`
    - gate перед controller execution;
    - при offline required nodes -> freeze/skip текущего цикла + backoff/error streak.
  - `backend/services/automation-engine/services/zone_automation_service.py`
    - `_check_required_nodes_online(...)`;
    - `_emit_required_nodes_offline_signal(...)`;
    - `_emit_required_nodes_recovered_signal(...)`;
    - `_evaluate_required_nodes_recovery_gate(...)`.
- Runtime-state:
  - новые поля в `zone_state_runtime.get_zone_state(...)`:
    `required_nodes_offline_*`, `last_required_nodes_offline_report_at`.

6. Resilience contract consolidation (incremental):
- `backend/services/automation-engine/services/resilience_contract.py`
  - унифицированы базовые resilience infra-codes/reason-codes;
  - применено в:
    - `zone_runtime_signals.py`,
    - `zone_skip_signals.py`,
    - `zone_automation_service.py` (required nodes offline/recovered).

## 3. Что не менялось
1. Pipeline `Scheduler -> AE -> History-Logger -> MQTT -> ESP32` не изменялся.
2. Внешние REST/MQTT/DB контракты не менялись.
3. `CommandBus`/publish-path не модифицировались.

## 4. Тесты
1. `pytest -q test_runtime_state_store.py test_zone_node_recovery.py test_main.py test_zone_automation_service.py test_correction_controller.py test_config_settings.py` -> `121 passed`.

## 5. Следующие шаги S10
1. Consolidate dedupe/retry/backoff/circuit-breaker policy и событийные коды в единый resilience contract.
2. Расширить acceptance coverage offline recovery (chaos/restart parity и длительные offline окна).
