# AE2_STAGE_S05_TASK.md
# Stage S5: Baseline Metrics/Coverage

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED  
**Роль:** AI-QA + AI-ARCH  
**Режим:** metrics/coverage baseline

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CONTRACT_SECURITY_BASELINE_S4.md`
- `backend/services/automation-engine/test_*.py` (профильные наборы)
- `backend/services/scheduler/test_main.py` (submit/poll профиль)

## 2. Конкретные файлы для изменения
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S05_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_BASELINE_METRICS_COVERAGE_S5.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_BASELINE_METRICS_S5.csv`
- `doc_ai/10_AI_DEV_GUIDES/AE2_BASELINE_COVERAGE_S5.csv`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`

## 3. Файлы, которые запрещено менять
- runtime publish-path (`command_bus.py`, `history-logger` contract)
- MQTT namespace/spec
- DB schema/migrations

## 4. Тесты для проверки
- Automation-engine профильный пакет:
  - `test_api.py`
  - `test_scheduler_task_executor.py`
  - `test_command_bus.py`
  - `test_correction_controller.py`
  - `test_correction_bounds_policy.py`
  - `test_zone_automation_service.py`
  - `test_config_settings.py`
- Scheduler профиль submit/poll:
  - `test_main.py -k submit_task_to_automation_engine_* or wait_task_completion_*`

## 5. Критерий завершения
1. Зафиксирован baseline metrics CSV (`p50/p95/p99`) для профильных наборов.
2. Зафиксирован baseline coverage report по критическим модулям:
   - scheduler task execution;
   - command publish/dedupe;
   - correction dosing;
   - recovery/state.
3. Обновлён `AE2_CURRENT_STATE.md` с отметкой завершения `S5`.

## 6. Роль и режим
- Stage `S5` выполняется в режиме `metrics/coverage baseline`.
