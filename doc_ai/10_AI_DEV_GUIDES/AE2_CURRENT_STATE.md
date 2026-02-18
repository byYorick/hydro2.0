# AE2_CURRENT_STATE.md
# Текущее состояние AE2 stage-потока

**Дата обновления:** 2026-02-18  
**Статус:** ACTIVE

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Текущий Stage
- `S10` Resilience Consolidation: IN_PROGRESS.
- Previous: `S9` Correction/Policy Hardening: COMPLETED.

## 2. Завершенные Stage
- `S1` Baseline Audit: COMPLETED.
- Mini-`S2` Safety Research Gate: COMPLETED.
- `S3` Safety Bounds + Rate Limit + Fail-Closed Audit: COMPLETED.
- `S4` Contract + Security Baseline: COMPLETED.
- `S5` Baseline Metrics/Coverage: COMPLETED.
- `S6` State Serialization Audit: COMPLETED.
- `S7` DI/Wiring: COMPLETED.
- `S8` CommandGateway Migration: COMPLETED.
- `S9` Correction/Policy Hardening: COMPLETED.

## 3. Открытые решения/ADR
1. Scheduler monolith split ADR (S8/S9) — OPEN.
2. Single-writer arbitration hardening ADR (S10) — OPEN.
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
10. S8: введен `CommandGateway` как единая runtime publish-точка для scheduler/correction/controller action paths.
11. S8: correction, sensor-mode и scheduler batch dispatch переведены на `CommandGateway` без изменения внешних контрактов.
12. S8: deprecated `main.publish_correction_command()` использует gateway-path.
13. S9: proactive correction (EWMA/slope) включен для pH/EC внутри dead-zone с cooldown gate и structured events.
14. S9: anomaly guard `dose -> no_effect xN` добавлен с auto-block dosing (`status=degraded`) и kill-free rollback через env-flags.
15. S10 (increment 1): runtime-state crash snapshot (`AE_RUNTIME_STATE_*`) добавлен для `_zone_states` + correction runtime maps с restore на startup/shutdown.
16. S10 (increment 2): required-nodes offline recovery gate добавлен в zone-cycle (freeze + backoff + recovered reconcile signals).
17. S10 (increment 3): введен базовый `resilience_contract` для унификации infra/reason codes в runtime/backoff/recovery signals.
18. S10 (increment 4): `resilience_contract` расширен на controller guardrails и correction-gating alerts; offline-recovery acceptance coverage расширен.
19. S10 (increment 5): retry/unconfirmed correction-command paths переведены на `resilience_contract` infra-codes.
20. S10 (increment 6): housekeeping/irrigation/event-write infra-codes переведены на `resilience_contract`; добавлен restart-parity тест offline-recovery state.
21. S10 (increment 7): correction-gating reason-коды переведены на `resilience_contract`.
22. S10 (increment 8): correction anomaly infra-alert code переведен на `resilience_contract` + unit-assert.
23. S10 (increment 9): `application/*` infra-alert literal codes переведены на `resilience_contract` (api runtime/recovery, scheduler execution, workflow-state sync, device-task, diagnostics, task-event persistence).

## 5. Известные риски
1. Остаточный dual-writer риск до полного S10 arbitration hardening.
2. Crash-recovery runtime maps частично закрыт snapshot-механизмом; остается расширенный acceptance/chaos набор для offline recovery и dedupe/retry contract consolidation.

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
- `backend/services/automation-engine/infrastructure/command_gateway.py`
- `backend/services/automation-engine/infrastructure/__init__.py`
- `backend/services/automation-engine/application/command_publish_batch.py`
- `backend/services/automation-engine/application/executor_init.py`
- `backend/services/automation-engine/application/executor_small_delegates.py`
- `backend/services/automation-engine/correction_command_retry.py`
- `backend/services/automation-engine/main.py`
- `backend/services/automation-engine/services/zone_controller_execution.py`
- `backend/services/automation-engine/services/zone_sensor_mode_orchestrator.py`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S08_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_COMMAND_GATEWAY_MIGRATION_S8.md`
- `backend/services/automation-engine/correction_cooldown.py`
- `backend/services/automation-engine/test_correction_cooldown.py`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S09_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CORRECTION_POLICY_HARDENING_S9.md`
- `backend/services/automation-engine/infrastructure/runtime_state_store.py`
- `backend/services/automation-engine/test_runtime_state_store.py`
- `backend/services/automation-engine/services/zone_node_recovery.py`
- `backend/services/automation-engine/test_zone_node_recovery.py`
- `backend/services/automation-engine/services/resilience_contract.py`
- `backend/services/automation-engine/services/zone_controller_guardrails.py`
- `backend/services/automation-engine/services/zone_correction_signals.py`
- `backend/services/automation-engine/application/api_runtime.py`
- `backend/services/automation-engine/application/api_recovery.py`
- `backend/services/automation-engine/application/workflow_phase_sync_core.py`
- `backend/services/automation-engine/application/device_task_core.py`
- `backend/services/automation-engine/application/api_scheduler_execution.py`
- `backend/services/automation-engine/application/diagnostics_execution.py`
- `backend/services/automation-engine/application/task_events_persistence.py`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S10_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_RESILIENCE_CONSOLIDATION_S10.md`
