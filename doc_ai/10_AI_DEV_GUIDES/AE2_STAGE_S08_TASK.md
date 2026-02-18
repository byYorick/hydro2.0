# AE2_STAGE_S08_TASK.md
# Stage S8: CommandGateway Migration

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED  
**Роль:** AI-CORE + AI-RELIABILITY  
**Режим:** implementation

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `backend/services/automation-engine/application/command_publish_batch.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/correction_command_retry.py`
- `backend/services/automation-engine/services/zone_controller_execution.py`
- `backend/services/automation-engine/main.py`

## 2. Конкретные файлы для изменения
- `backend/services/automation-engine/infrastructure/command_gateway.py`
- `backend/services/automation-engine/infrastructure/__init__.py`
- `backend/services/automation-engine/application/executor_init.py`
- `backend/services/automation-engine/application/executor_small_delegates.py`
- `backend/services/automation-engine/application/command_publish_batch.py`
- `backend/services/automation-engine/correction_command_retry.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/services/zone_controller_execution.py`
- `backend/services/automation-engine/services/zone_sensor_mode_orchestrator.py`
- `backend/services/automation-engine/services/zone_correction_orchestrator.py`
- `backend/services/automation-engine/services/zone_automation_service.py`
- `backend/services/automation-engine/main.py`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S08_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_COMMAND_GATEWAY_MIGRATION_S8.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`

## 3. Файлы, которые запрещено менять
- `backend/services/automation-engine/infrastructure/command_bus.py` (без функциональной перестройки transport слоя)
- Публикационный pipeline `Scheduler -> AE -> History-Logger -> MQTT -> ESP32`
- MQTT/API/DB контракты и схемы

## 4. Тесты для проверки
- `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q test_command_publish_batch.py test_scheduler_task_executor.py test_zone_automation_service.py`
- `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q test_correction_controller.py -k "publish_controller_command_with_retry or command_unconfirmed"`
- `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q test_api.py -k "scheduler_task or execute_scheduler_task or scheduler_internal_enqueue"`

## 5. Критерий завершения
1. Введен `CommandGateway` как единая publish-точка в runtime-path.
2. Scheduler execution batch path использует gateway.
3. Correction publish/retry path использует gateway.
4. Zone controller publish path (`controller actions`, `sensor mode`) использует gateway.
5. Deprecated `main.publish_correction_command()` использует gateway.
6. Профильные тесты без регрессий.

## 6. Роль и режим
- Stage `S8` выполняется в режиме `implementation`.
