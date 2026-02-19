# AE2_STAGE_S03_TASK.md
# Stage S3: Safety Implementation

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED  
**Роль:** AI-CORE  
**Режим:** implementation

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_SAFETY_RESEARCH_S2.md`
- `backend/services/automation-engine/config/settings.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/services/zone_correction_orchestrator.py`

## 2. Конкретные файлы для изменения
- `backend/services/automation-engine/config/settings.py`
- `backend/services/automation-engine/services/correction_bounds_policy.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/services/zone_correction_orchestrator.py`
- `backend/services/automation-engine/test_correction_bounds_policy.py`
- `backend/services/automation-engine/test_correction_controller.py`
- `backend/services/automation-engine/test_zone_automation_service.py`
- `backend/services/automation-engine/test_config_settings.py`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S03_TASK.md`

## 3. Файлы, которые запрещено менять
- `backend/services/automation-engine/infrastructure/command_bus.py`
- `backend/services/automation-engine/main.py` (кроме согласованного crash-mitigation)
- MQTT/API/DB контракты и схемы

## 4. Тесты для проверки
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest -q test_correction_bounds_policy.py test_correction_controller.py test_zone_automation_service.py test_config_settings.py`

## 5. Критерий завершения
1. В correction-path внедрены safety bounds, hybrid source selection и fail-closed behavior.
2. Добавлен rate-limit изменения target (`max_delta_per_min`) с audit-сигналами.
3. Regression suite по safety-модулям зеленый.
4. `AE2_CURRENT_STATE.md` обновлен отметкой завершения `S3`.

## 6. Роль и режим
- Stage `S3` выполнен в режиме `implementation`.
