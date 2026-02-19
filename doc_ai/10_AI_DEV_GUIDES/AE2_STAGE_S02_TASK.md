# AE2_STAGE_S02_TASK.md
# Stage S2: Safety Research (mini-gate, без production-кода)

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED  
**Роль:** AI-ARCH  
**Режим:** read-only research

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `AGENTS.md` (корень)
- `backend/services/AGENTS.md`
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S01_TASK.md`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/services/zone_correction_orchestrator.py`
- `backend/services/automation-engine/config/settings.py`

## 2. Конкретные файлы для изменения
- `doc_ai/10_AI_DEV_GUIDES/AE2_SAFETY_RESEARCH_S2.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S02_TASK.md`

## 3. Файлы, которые запрещено менять
- Любой production-код в `backend/services/*`
- MQTT/API/DB контракты
- Миграции/DDL

## 4. Тесты для проверки
- Проверка полноты research-артефакта `AE2_SAFETY_RESEARCH_S2.md`:
  - точки внедрения;
  - порядок источников safety bounds;
  - fail-closed правила;
  - обязательные тест-сценарии.
- Проверка gate `S1 -> S2` в `AE2_CURRENT_STATE.md`.

## 5. Критерий завершения
1. Подготовлен `decision-complete` исследовательский план внедрения safety bounds.
2. Подтверждено, что `S2` не содержит production-код изменений.
3. `AE2_CURRENT_STATE.md` обновлен отметкой завершения mini-`S2`.

## 6. Роль и режим
- Stage `S2` выполняется в режиме `read-only research`.
