# AE2_COMMAND_GATEWAY_MIGRATION_S8.md
# AE2 S8: CommandGateway Migration

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Цель S8
Перевести обязательные publish-path на единый `CommandGateway`, не ломая защищенный pipeline и внешний контракт.

## 2. Реализовано
1. Новый gateway:
- `backend/services/automation-engine/infrastructure/command_gateway.py`
- методы:
  - `publish_command(...)`
  - `publish_controller_command(...)`
  - `publish_controller_command_closed_loop(...)`
- per-zone serialization через `asyncio.Lock`.

2. Scheduler execution path:
- `backend/services/automation-engine/application/executor_init.py`
  - инициализируется `executor.command_gateway = CommandGateway(command_bus)`.
- `backend/services/automation-engine/application/executor_small_delegates.py`
  - `publish_batch(...)` получает `command_gateway`.
- `backend/services/automation-engine/application/command_publish_batch.py`
  - batch-dispatch работает через `publisher = command_gateway or command_bus`.

3. Correction path:
- `backend/services/automation-engine/correction_command_retry.py`
  - retry helper переведен на `publisher = command_gateway or command_bus`.
- `backend/services/automation-engine/correction_controller.py`
  - `apply_correction(...)` и retry hook принимают/используют gateway.
- `backend/services/automation-engine/services/zone_correction_orchestrator.py`
  - в `apply_correction(...)` передается `command_gateway`.

4. Zone controller publish path:
- `backend/services/automation-engine/services/zone_controller_execution.py`
  - `publish_controller_action_with_event_integrity(...)` использует gateway.
- `backend/services/automation-engine/services/zone_sensor_mode_orchestrator.py`
  - `set_sensor_mode(...)` использует gateway.
- `backend/services/automation-engine/services/zone_automation_service.py`
  - создается `self.command_gateway`;
  - controller actions + correction + sensor mode path переведены на gateway.

5. Legacy path:
- `backend/services/automation-engine/main.py`
  - `publish_correction_command(...)` теперь использует `CommandGateway` (для глобального и временного `CommandBus`).

## 3. Что не менялось
1. `CommandBus` transport-логика не переписывалась.
2. Pipeline `Scheduler -> AE -> History-Logger -> MQTT -> ESP32` не изменён.
3. Внешний REST/MQTT контракт не изменён.

## 4. Regression тесты
1. `pytest -q test_command_publish_batch.py test_scheduler_task_executor.py test_zone_automation_service.py` -> `114 passed`.
2. `pytest -q test_correction_controller.py -k "publish_controller_command_with_retry or command_unconfirmed"` -> `1 passed, 42 deselected`.
3. `pytest -q test_api.py -k "scheduler_task or execute_scheduler_task or scheduler_internal_enqueue"` -> `38 passed, 32 deselected`.

## 5. Остаточные задачи перед S9/S10
1. Расширить observability `CommandGateway` (отдельные метрики/structured events gateway-level).
2. Закрыть полный single-writer арбитраж (state-driven fallback policy + explicit dual-writer guard matrix) как часть `S10`.
