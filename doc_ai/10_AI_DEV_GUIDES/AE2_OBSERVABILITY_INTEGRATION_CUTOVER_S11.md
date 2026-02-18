# AE2_OBSERVABILITY_INTEGRATION_CUTOVER_S11.md
# AE2 S11: Observability + Integration + Cutover

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Scope инкремента
1. Зафиксировать bootstrap cutover-contract для scheduler.
2. Добавить минимально необходимую observability для bootstrap rollout-контуров.
3. Не менять publish pipeline и не вводить breaking changes.

## 2. Реализовано
1. Bootstrap contract (additive):
- `rollout_profile`;
- `tier2_capabilities`.
2. Bootstrap observability metric:
- `scheduler_bootstrap_status_total{status,rollout_profile}`.
3. Runtime rollout flags:
- `AE2_ROLLOUT_PROFILE` (default `canary-first`);
- `AE2_TIER2_GDD_ENABLED`;
- `AE2_TIER2_APPROVALS_ENABLED`;
- `AE2_TIER2_DAILY_DIGEST_ENABLED`.
4. Bootstrap contract literals (`status/reason`) нормализованы через `resilience_contract` constants.
5. Добавлен `GET /scheduler/cutover/state`:
- возвращает rollout profile, Tier2 capability flags и ingress cutover параметры;
- используется как read-only observability/control-plane snapshot для canary/cutover.
6. Добавлен `GET /scheduler/integration/contracts`:
- возвращает versioned integration contract (`s11-v1`) и сигналы Tier2 интеграций;
- используется как machine-checkable snapshot для integration/cutover QA.
7. Добавлен bootstrap deny-alert path:
- при `bootstrap_status=deny` (например, `protocol_not_supported`) отправляется
  `infra_scheduler_bootstrap_denied`.
8. Добавлен `GET /scheduler/observability/contracts`:
- возвращает versioned required list для cutover observability
  (метрики, alert codes, ключевые scheduler/workflow events).

## 3. Что не менялось
1. `Scheduler -> AE -> History-Logger -> MQTT -> ESP32` path не менялся.
2. Existing auth/lease semantics scheduler ingress не менялись.
3. Existing task execution semantics не менялись.

## 4. Верификация
1. `pytest test_api.py test_scheduler_task_executor.py` -> green.
2. Проверено, что bootstrap/heartbeat возвращают rollout-capabilities без изменения статусов `ready/wait/deny`.
3. Проверено, что `GET /scheduler/cutover/state` возвращает согласованное состояние rollout/cutover флагов.
4. Проверено, что `GET /scheduler/integration/contracts` возвращает ожидаемый versioned contract payload.
5. Проверено, что protocol mismatch вызывает `bootstrap_status=deny` и infra-alert emit.
6. Проверено, что `GET /scheduler/observability/contracts` возвращает expected required observability contract.

## 5. Следующие шаги
1. Перенос в `S12`: load/chaos/parity acceptance для full cutover decision.
