# AE2_CURRENT_STATE.md
# Текущее состояние AE2 stage-потока

**Дата обновления:** 2026-02-18  
**Статус:** ACTIVE

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Текущий Stage
- `S4` Contract + Security Baseline: COMPLETED.
- Next: `S5` Baseline Metrics/Coverage.

## 2. Завершенные Stage
- `S1` Baseline Audit: COMPLETED.
- Mini-`S2` Safety Research Gate: COMPLETED.
- `S3` Safety Bounds + Rate Limit + Fail-Closed Audit: COMPLETED.
- `S4` Contract + Security Baseline: COMPLETED.

## 3. Открытые решения/ADR
1. `CommandGateway` migration ADR (S8) — OPEN.
2. Scheduler monolith split ADR (S7/S8) — OPEN.

## 4. Зафиксированные решения
1. `check_phase_transitions` owner: AE simulation-only path.
2. Safety bounds source: hybrid (override -> targets -> defaults).
3. Safety rollout mode: on by default + kill-switch.
4. Scheduler ingress baseline security (`/scheduler/task`): required `Authorization + X-Trace-Id`.
5. Hardened scheduler security (`X-Request-Nonce`, `X-Sent-At`) остается `DEFERRED`.

## 5. Известные риски
1. Dual-writer publish risk до полной миграции на `CommandGateway`.
2. Наличие legacy deprecated correction publish path в `main.py`.

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
