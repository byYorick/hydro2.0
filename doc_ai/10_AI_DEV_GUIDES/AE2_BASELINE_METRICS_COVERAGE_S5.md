# AE2_BASELINE_METRICS_COVERAGE_S5.md
# AE2 S5: Baseline Metrics/Coverage

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Scope S5
Зафиксирован baseline для `automation-engine`/`scheduler` перед следующими release-gates.

Цели S5:
1. baseline `p50/p95/p99`;
2. baseline coverage по критическим путям;
3. фиксация reproducible команд.

## 2. Baseline metrics
Источник: `doc_ai/10_AI_DEV_GUIDES/AE2_BASELINE_METRICS_S5.csv`.

Ключевые значения:
1. `automation_engine_critical_suite`:
- samples: `263`
- `p50=0.003s`, `p95=0.192s`, `p99=0.507s`
- total test-case duration: `45.687s`.

2. `scheduler_submit_poll_profile`:
- samples: `9`
- `p50=0.006s`, `p95=0.237s`, `p99=0.237s`
- total test-case duration: `0.372s`.

## 3. Baseline coverage
Источник: `doc_ai/10_AI_DEV_GUIDES/AE2_BASELINE_COVERAGE_S5.csv`.

Критические модули automation-engine:
1. `application.scheduler_executor_impl`: `100%`
2. `infrastructure.command_bus`: `80%`
3. `correction_controller`: `90%`
4. `application.api_recovery`: `76%`
5. `infrastructure.workflow_state_store`: `67%`
6. `services.zone_runtime_backoff`: `97%`
7. Сводно по критическим модулям: `84%`.

Scheduler submit/poll focused profile:
1. `scheduler/main.py`: `21%` в рамках узкого profile-набора (не full-suite coverage).

## 4. Reproducible commands
1. Automation-engine timing baseline:
- `pytest -q test_api.py test_scheduler_task_executor.py test_command_bus.py test_correction_controller.py test_correction_bounds_policy.py test_zone_automation_service.py test_config_settings.py --junitxml=/tmp/ae_s5_junit.xml`

2. Automation-engine critical coverage baseline:
- `python -m pytest -q automation-engine/test_api.py automation-engine/test_scheduler_task_executor.py automation-engine/test_command_bus.py automation-engine/test_correction_controller.py automation-engine/test_zone_automation_service.py automation-engine/test_config_settings.py automation-engine/test_correction_bounds_policy.py --cov=application.scheduler_executor_impl --cov=infrastructure.command_bus --cov=correction_controller --cov=application.api_recovery --cov=infrastructure.workflow_state_store --cov=services.zone_runtime_backoff`

3. Scheduler submit/poll profile:
- `pytest -q test_main.py -k "submit_task_to_automation_engine_* or wait_task_completion_*" --junitxml=/tmp/scheduler_s5_junit.xml`
- `python -m pytest -q test_main.py -k "submit_task_to_automation_engine_* or wait_task_completion_*" --cov=main`

## 5. Ограничения baseline
1. `p50/p95/p99` зафиксированы как test-case timing baseline, не как production SLO.
2. Scheduler coverage `21%` отражает только submit/poll профиль; full coverage требует отдельного S5 расширения.
3. Для запуска coverage в `python-tests` контейнере требуется service-token env (после S4 security baseline).

## 6. Gate verdict
S5 verdict: `PASS`.

Готовность к переходу:
1. Baseline metrics/coverage зафиксированы;
2. Gate-метрики документированы;
3. Следующий stage: `S6` (State Serialization Audit).
