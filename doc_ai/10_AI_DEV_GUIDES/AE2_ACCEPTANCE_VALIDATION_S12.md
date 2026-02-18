# AE2_ACCEPTANCE_VALIDATION_S12.md
# AE2 S12 Acceptance Validation

**Версия:** v0.1  
**Дата:** 2026-02-18  
**Статус:** IN_PROGRESS

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Scope
1. Подтвердить pre-release acceptance gate для AE2 после S11 cutover/observability.
2. Проверить parity bootstrap/cutover contracts и отсутствие регрессий scheduler ingress.
3. Зафиксировать минимальный chaos/regression baseline для recovery/dedupe paths.

## 2. Gates
1. Load gate: `PENDING` (вынесен в отдельный прогон на стенде S12).
2. Chaos gate: `PASS (local baseline)`:
- `pytest test_scheduler_task_executor.py test_zone_node_recovery.py` -> `72 passed`.
3. Parity gate: `PASS (local baseline)`:
- `pytest test_api.py` -> `77 passed`, включая новые S12 acceptance checks.
4. SLO gate: `PENDING` (требует стендовых метрик cutover потока).

## 3. Increment 1 (2026-02-18)
1. Добавлены acceptance-тесты в `test_api.py`:
- консистентность `rollout_profile` и `tier2_capabilities` между bootstrap/heartbeat/cutover/integration endpoint-ами;
- сценарий перехода bootstrap `wait -> ready` после восстановления readiness;
- проверка уникальности required observability contract lists.
2. Подготовлен stage-task `AE2_STAGE_S12_TASK.md`.

## 4. Increment 2 (2026-02-18)
1. Выполнены Docker-прогоны:
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest test_api.py` -> `77 passed`;
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest test_scheduler_task_executor.py test_zone_node_recovery.py` -> `72 passed`.
2. Зафиксирован локальный PASS по parity/chaos baseline для S12.

## 5. Следующий инкремент S12
1. Провести стендовый load-прогон cutover ingress и зафиксировать p50/p95/p99.
2. Зафиксировать SLO gate (`PASS/FAIL/DEFERRED`) на основании стендовых метрик.
3. Подготовить `AE2_STAGE_S12_FINAL_REPORT.md` после закрытия обязательных gates.
