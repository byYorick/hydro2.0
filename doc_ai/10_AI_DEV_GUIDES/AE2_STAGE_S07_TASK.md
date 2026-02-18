# AE2_STAGE_S07_TASK.md
# Stage S7: DI/Wiring Baseline

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED  
**Роль:** AI-CORE  
**Режим:** implementation

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `backend/services/automation-engine/scheduler_task_executor.py`
- `backend/services/automation-engine/application/scheduler_executor_impl.py`
- `backend/services/automation-engine/application/api_scheduler_execution.py`
- `backend/services/automation-engine/api.py`

## 2. Конкретные файлы для изменения
- `backend/services/automation-engine/scheduler_task_executor.py`
- `backend/services/automation-engine/application/scheduler_executor_wiring.py`
- `backend/services/automation-engine/domain/workflows/cycle_start_core.py`
- `backend/services/automation-engine/application/api_scheduler_execution.py`
- `backend/services/automation-engine/api.py`
- `backend/services/automation-engine/test_scheduler_task_executor.py`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S07_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_DI_WIRING_BASELINE_S7.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`

## 3. Файлы, которые запрещено менять
- `backend/services/automation-engine/infrastructure/command_bus.py`
- Путь публикации команд `Scheduler -> AE -> History-Logger -> MQTT -> ESP32`
- MQTT/API/DB контракты и схемы

## 4. Тесты для проверки
- `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q test_scheduler_task_executor.py`
- `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q test_api.py -k "scheduler_task or execute_scheduler_task or scheduler_internal_enqueue"`

## 5. Критерий завершения
1. Удалён monkey-patch path в `scheduler_task_executor.py` (`_impl.* = proxy`).
2. Добавлен явный DI/wiring baseline для runtime-dependencies executor-а.
3. `cycle_start` self-enqueue использует DI-bound function, а не прямой глобальный вызов.
4. Профильные тесты scheduler executor/API проходят.

## 6. Роль и режим
- Stage `S7` выполняется в режиме `implementation`.
