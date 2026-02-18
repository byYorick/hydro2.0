# AE2_RESILIENCE_CONSOLIDATION_S10.md
# AE2 S10: Resilience Consolidation (Increment 1)

**Версия:** v0.1  
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

## 3. Что не менялось
1. Pipeline `Scheduler -> AE -> History-Logger -> MQTT -> ESP32` не изменялся.
2. Внешние REST/MQTT/DB контракты не менялись.
3. `CommandBus`/publish-path не модифицировались.

## 4. Тесты
1. `pytest -q test_runtime_state_store.py test_main.py test_zone_automation_service.py test_correction_controller.py test_config_settings.py` -> `116 passed`.

## 5. Следующие шаги S10
1. Consolidate dedupe/retry/backoff/circuit-breaker policy и событийные коды в единый resilience contract.
2. Расширить auto-recovery loop offline нод до явного acceptance набора (retry/backoff/freeze/reconcile).
