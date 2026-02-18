# AE2_STAGE_S11_TASK.md
# Stage S11: Observability + Integration + Cutover

**Версия:** v0.1  
**Дата:** 2026-02-18  
**Статус:** IN_PROGRESS  
**Роль:** AI-INTEGRATION + AI-RELIABILITY + AI-QA  
**Режим:** implementation

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S10_FINAL_REPORT.md`
- `backend/services/automation-engine/api.py`
- `backend/services/automation-engine/application/api_scheduler_bootstrap.py`

## 2. Цель Stage
1. Подготовить наблюдаемое и управляемое cutover-поведение для scheduler ingress без нарушения protected pipeline.
2. Зафиксировать rollout-profile и integration capabilities в bootstrap-contract.
3. Расширить observability для bootstrap/dedupe/retry decision paths.

## 3. Текущий инкремент (выполнено)
1. Bootstrap API расширен additive-полями:
- `rollout_profile` (default `canary-first`);
- `tier2_capabilities` (`gdd_phase_transitions`, `mobile_approvals`, `daily_health_digest`).
2. Добавлена метрика bootstrap-статусов:
- `scheduler_bootstrap_status_total{status,rollout_profile}`.
3. Добавлены env-flags rollout/integration (read-only для scheduler bootstrap payload):
- `AE2_ROLLOUT_PROFILE`;
- `AE2_TIER2_GDD_ENABLED`;
- `AE2_TIER2_APPROVALS_ENABLED`;
- `AE2_TIER2_DAILY_DIGEST_ENABLED`.
4. Bootstrap status/reason literals переведены на contract constants в `resilience_contract`.
5. Добавлен endpoint `GET /scheduler/cutover/state` для rollout/cutover introspection.
6. Добавлен endpoint `GET /scheduler/integration/contracts` для явного Tier2 integration contract snapshot.

## 4. Остаток S11 (open)
1. Нормализовать cutover observability dashboard contract (required metrics/events list).
2. Подготовить integration contract для Tier2 signals (GDD transitions, approvals, digest) с feature-gated rollout.
3. Подготовить S11 final report и gate на переход к `S12`.

## 5. Тесты текущего инкремента
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest test_api.py test_scheduler_task_executor.py`
