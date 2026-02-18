# AE2_CURRENT_STATE.md
# Текущее состояние AE2 stage-потока

**Дата обновления:** 2026-02-18  
**Статус:** ACTIVE

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Текущий Stage
- `S7` DI/Wiring: COMPLETED.
- Next: `S8` CommandGateway Migration.

## 2. Завершенные Stage
- `S1` Baseline Audit: COMPLETED.
- Mini-`S2` Safety Research Gate: COMPLETED.
- `S3` Safety Bounds + Rate Limit + Fail-Closed Audit: COMPLETED.
- `S4` Contract + Security Baseline: COMPLETED.
- `S5` Baseline Metrics/Coverage: COMPLETED.
- `S6` State Serialization Audit: COMPLETED.
- `S7` DI/Wiring: COMPLETED.

## 3. Открытые решения/ADR
1. `CommandGateway` migration ADR (S8) — OPEN.
2. Scheduler monolith split ADR (S7/S8) — OPEN.
3. Runtime-state schema versioning + unified serialization contract ADR — OPEN.

## 4. Зафиксированные решения
1. `check_phase_transitions` owner: AE simulation-only path.
2. Safety bounds source: hybrid (override -> targets -> defaults).
3. Safety rollout mode: on by default + kill-switch.
4. Scheduler ingress baseline security (`/scheduler/task`): required `Authorization + X-Trace-Id`.
5. Hardened scheduler security (`X-Request-Nonce`, `X-Sent-At`) остается `DEFERRED`.
6. S5 baseline metrics/coverage зафиксирован как pre-release gate baseline.
7. S6 audit: явные `serialize()/deserialize()` contracts отсутствуют; частично закрыто через `WorkflowStateStore` и `PidStateManager`.
8. S7: monkey-patch path в `scheduler_task_executor.py` удален; runtime wiring переведен на явный composition/wiring.
9. S7: `cycle_start` self-enqueue использует DI-bound `self.enqueue_internal_scheduler_task_fn`.

## 5. Известные риски
1. Dual-writer publish risk до полной миграции на `CommandGateway`.
2. Наличие legacy deprecated correction publish path в `main.py`.
3. Неполный crash-recovery runtime maps (`_zone_states`, cooldown/alert-throttle caches, target-history maps) до внедрения unified serialization contracts.

## 6. Flaky tests / проблемы
- На момент обновления: не зафиксировано.

## 7. Кумулятивный список измененных файлов (этой сессии)
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S01_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_P0A_MIN_BLOCKING_AUDIT.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_SAFETY_HOTFIX_BACKLOG.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_SAFETY_RESEARCH_S2.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `backend/services/automation-engine/config/settings.py`
- `backend/services/automation-engine/services/correction_bounds_policy.py`
- `backend/services/automation-engine/correction_controller.py`
- `backend/services/automation-engine/services/zone_correction_orchestrator.py`
- `backend/services/automation-engine/test_correction_bounds_policy.py`
- `backend/services/automation-engine/test_correction_controller.py`
- `backend/services/automation-engine/test_zone_automation_service.py`
- `backend/services/automation-engine/test_config_settings.py`
- `backend/docker-compose.dev.yml`
- `backend/services/automation-engine/application/api_scheduler_security.py`
- `backend/services/automation-engine/application/api_scheduler_routes.py`
- `backend/services/automation-engine/api.py`
- `backend/services/automation-engine/test_api.py`
- `backend/services/scheduler/main.py`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S04_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CONTRACT_SECURITY_BASELINE_S4.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S05_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_BASELINE_METRICS_COVERAGE_S5.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_BASELINE_METRICS_S5.csv`
- `doc_ai/10_AI_DEV_GUIDES/AE2_BASELINE_COVERAGE_S5.csv`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S06_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STATE_SERIALIZATION_AUDIT_S6.md`
- `backend/services/automation-engine/scheduler_task_executor.py`
- `backend/services/automation-engine/application/scheduler_executor_wiring.py`
- `backend/services/automation-engine/domain/workflows/cycle_start_core.py`
- `backend/services/automation-engine/application/api_scheduler_execution.py`
- `backend/services/automation-engine/test_scheduler_task_executor.py`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S07_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_DI_WIRING_BASELINE_S7.md`
