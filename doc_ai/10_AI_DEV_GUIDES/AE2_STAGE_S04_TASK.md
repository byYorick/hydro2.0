# AE2_STAGE_S04_TASK.md
# Stage S4: Contract + Security Baseline

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED  
**Роль:** AI-ARCH + AI-SEC  
**Режим:** contract/spec + limited code

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `AGENTS.md` (корень)
- `backend/services/AGENTS.md`
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `backend/services/automation-engine/api.py`
- `backend/services/automation-engine/application/api_scheduler_routes.py`
- `backend/services/scheduler/main.py`

## 2. Конкретные файлы для изменения
- `backend/services/automation-engine/application/api_scheduler_security.py`
- `backend/services/automation-engine/application/api_scheduler_routes.py`
- `backend/services/automation-engine/api.py`
- `backend/services/automation-engine/test_api.py`
- `backend/services/scheduler/main.py`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CONTRACT_SECURITY_BASELINE_S4.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S04_TASK.md`

## 3. Файлы, которые запрещено менять
- `backend/services/automation-engine/infrastructure/command_bus.py`
- MQTT contracts/specs и DB schema/migrations
- hardened security реализацию (`X-Request-Nonce`, `X-Sent-At`) без отдельного запроса/ADR

## 4. Тесты для проверки
- `pytest -q backend/services/automation-engine/test_api.py`
- Профильные проверки scheduler submit/poll headers для `Authorization` и `X-Trace-Id`

## 5. Критерий завершения
1. Для `POST /scheduler/task` включен baseline security gate:
   - валидный `Authorization` (service token)
   - обязательный `X-Trace-Id`.
2. Scheduler отправляет baseline headers в task/status path.
3. Hardened profile явно зафиксирован как `DEFERRED`.
4. Контрактные тесты API зелёные.

## 6. Роль и режим
- Stage `S4` выполняется в режиме `contract/spec + limited code`.
