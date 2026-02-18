# AE2_STAGE_S09_TASK.md
# Stage S9: Correction/Policy Hardening

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED  
**Роль:** AI-CORE + AI-RELIABILITY  
**Режим:** implementation

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `backend/services/automation-engine/correction_cooldown.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/config/settings.py`

## 2. Конкретные файлы для изменения
- `backend/services/automation-engine/config/settings.py`
- `backend/services/automation-engine/correction_cooldown.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/test_correction_cooldown.py`
- `backend/services/automation-engine/test_correction_controller.py`
- `backend/services/automation-engine/test_config_settings.py`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S09_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CORRECTION_POLICY_HARDENING_S9.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`

## 3. Файлы, которые запрещено менять
- `backend/services/automation-engine/infrastructure/command_bus.py`
- Публикационный pipeline `Scheduler -> AE -> History-Logger -> MQTT -> ESP32`
- MQTT/API/DB контракты и схемы

## 4. Тесты для проверки
- `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q test_correction_cooldown.py test_correction_controller.py test_config_settings.py`
- `docker compose -f backend/docker-compose.dev.yml exec -T automation-engine pytest -q test_zone_automation_service.py`

## 5. Критерий завершения
1. Реализован `proactive correction` на базе EWMA/slope для pH/EC внутри dead-zone.
2. Реализован anomaly guard `dose -> no_effect xN` с авто-блокировкой дозирования.
3. Добавлены structured events/reason-code для audit/degraded-path.
4. Контракты публикации команд и transport-path не изменены.
5. Профильные unit/integration тесты зеленые.

## 6. Роль и режим
- Stage `S9` выполнен в режиме `implementation`.
