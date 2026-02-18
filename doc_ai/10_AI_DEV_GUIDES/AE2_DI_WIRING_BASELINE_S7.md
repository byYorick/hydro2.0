# AE2_DI_WIRING_BASELINE_S7.md
# AE2 S7: DI/Wiring Baseline

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Scope S7
Stage S7 закрывает минимальный DI/Wiring baseline для `SchedulerTaskExecutor`:
1. Явный runtime wiring зависимостей.
2. Удаление скрытого monkey-patch пути в public wrapper.
3. Сохранение обратной совместимости для существующих тестов и API.

## 2. Реализовано
1. Добавлен wiring-модуль:
- `backend/services/automation-engine/application/scheduler_executor_wiring.py`
- `SchedulerExecutorRuntimeBindings`
- `build_scheduler_executor_runtime_bindings(...)`
- `apply_scheduler_executor_runtime_bindings(...)`

2. Обновлён публичный executor API:
- `backend/services/automation-engine/scheduler_task_executor.py`
- удалены `_impl.fetch/_impl.create_zone_event/_impl.send_infra_alert/_impl.enqueue_internal_scheduler_task = proxy`.
- `SchedulerTaskExecutor` стал явным wrapper-классом с `runtime_bindings`.
- добавлен composition helper `create_scheduler_task_executor(...)`.

3. В execution-path убран обход DI:
- `backend/services/automation-engine/domain/workflows/cycle_start_core.py`
- self-task enqueue переведён на `self.enqueue_internal_scheduler_task_fn`.

4. API wiring baseline:
- `backend/services/automation-engine/application/api_scheduler_execution.py`
  - `scheduler_task_executor_cls` -> `scheduler_task_executor_factory`.
- `backend/services/automation-engine/api.py`
  - добавлен `_build_scheduler_task_executor(...)` как composition root для scheduler execution path.

5. Тесты:
- `backend/services/automation-engine/test_scheduler_task_executor.py`
  - добавлены проверки wiring-поведения.

## 3. Что важно по совместимости
1. Внешний REST/MQTT контракт не менялся.
2. Публикационный pipeline команд не менялся.
3. Точки monkeypatch в `scheduler_task_executor` (`fetch/create_zone_event/send_infra_alert/enqueue_internal_scheduler_task`) сохранены для тестовой совместимости.

## 4. Прогон тестов
1. `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q test_scheduler_task_executor.py` -> `67 passed`.
2. `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q test_api.py -k "scheduler_task or execute_scheduler_task or scheduler_internal_enqueue"` -> `38 passed, 32 deselected`.

## 5. Остаточные вопросы к S8
1. Полная доменная декомпозиция на интерфейсы (`IWorkflowExecutor`, `ICommandGateway`, `ITaskOutcomeAssembler` и др.) остаётся открытым блоком для `S8`.
2. Миграция обязательных publish-path на `CommandGateway` остаётся отдельным stage-gate (`S8`).
