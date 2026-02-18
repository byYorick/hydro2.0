# AE2_STAGE_S06_TASK.md
# Stage S6: State Serialization Audit

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED  
**Роль:** AI-ARCH  
**Режим:** read-only audit

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `backend/services/automation-engine/services/zone_automation_service.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/main.py`
- `backend/services/automation-engine/api.py`
- `backend/services/automation-engine/infrastructure/workflow_state_store.py`
- `backend/services/automation-engine/services/pid_state_manager.py`

## 2. Конкретные файлы для изменения
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S06_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STATE_SERIALIZATION_AUDIT_S6.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`

## 3. Файлы, которые запрещено менять
- Любой production-код `backend/services/*`
- БД schema/migrations
- MQTT/API контракты publish-pipeline

## 4. Тесты для проверки
- Для S6 read-only этапа: запуск production-тестов не обязателен.
- Проверка полноты аудита:
  1. Полный inventory runtime-state.
  2. Разделение durable vs in-memory state.
  3. Формальный gap-анализ по `serialize()/deserialize()`.

## 5. Критерий завершения
1. Зафиксирован state inventory для `ZoneAutomationService`, `CorrectionController`, `main.py`, `api.py`.
2. Зафиксировано, какие state уже имеют durable restore path.
3. Определены обязательные контракты сериализации и migration-гейты для следующих этапов.
4. `AE2_CURRENT_STATE.md` обновлен до `S6 COMPLETED`.

## 6. Роль и режим
- Stage `S6` выполняется в режиме `read-only audit`.
