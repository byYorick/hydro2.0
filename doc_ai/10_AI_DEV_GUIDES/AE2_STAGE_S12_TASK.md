# AE2_STAGE_S12_TASK.md
# Stage S12: Load + Chaos + Acceptance

**Версия:** v0.1  
**Дата:** 2026-02-18  
**Статус:** IN_PROGRESS  
**Роль:** AI-QA  
**Режим:** implementation

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S11_FINAL_REPORT.md`
- `backend/services/automation-engine/test_api.py`
- `backend/services/automation-engine/test_scheduler_task_executor.py`
- `backend/services/automation-engine/test_zone_node_recovery.py`

## 2. Конкретные файлы для изменения
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S12_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_ACCEPTANCE_VALIDATION_S12.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `backend/services/automation-engine/test_api.py`
- профильные тесты `backend/services/automation-engine/test_*.py` (по необходимости)

## 3. Файлы, которые запрещено менять
- `backend/services/automation-engine/infrastructure/command_bus.py` (кроме явного bugfix по S12 acceptance blocker)
- `backend/services/automation-engine/main.py` (кроме явного bugfix по S12 acceptance blocker)
- `backend/services/history-logger/*`
- любые MQTT topic/spec контракты без отдельного stage-решения

## 4. Тесты для проверки
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest test_api.py`
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest test_scheduler_task_executor.py test_zone_node_recovery.py`
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine python tests/s12_cutover_slo_probe.py`
- `docker compose -f backend/docker-compose.dev.yml run --rm -e AE2_SLO_PROBE_OUTPUT_MODE=csv automation-engine python tests/s12_cutover_slo_probe.py > doc_ai/10_AI_DEV_GUIDES/AE2_S12_LOCAL_SLO_BASELINE.csv`

## 5. Критерий завершения
1. Есть acceptance-отчет `AE2_ACCEPTANCE_VALIDATION_S12.md` с load/chaos/parity/SLO gate-статусами.
2. Regression suite по затронутым тестам зеленый в Docker.
3. `AE2_CURRENT_STATE.md` обновлен до статуса `S12 COMPLETED` и содержит финальный gate-increment.
