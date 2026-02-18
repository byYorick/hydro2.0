# AE2_CONTRACT_SECURITY_BASELINE_S4.md
# AE2 S4: Contract + Security Baseline

**Версия:** v1.0  
**Дата:** 2026-02-18  
**Статус:** COMPLETED

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Scope S4
S4 фиксирует baseline security для scheduler ingress в automation-engine без hardened replay-защиты.

В текущем цикле применено к:
- `POST /scheduler/task`

## 2. Baseline requirements (implemented)
1. `Authorization: Bearer <service-token>` обязателен.
2. `X-Trace-Id` обязателен.
3. Проверка lease (`X-Scheduler-Id`, `X-Scheduler-Lease-Id`) сохраняется и выполняется отдельно.

## 3. Token source policy
### AE (ingress validation)
`SCHEDULER_API_TOKEN` -> `PY_INGEST_TOKEN` -> `PY_API_TOKEN`.

### Scheduler (egress headers)
`SCHEDULER_API_TOKEN` -> `PY_INGEST_TOKEN` -> `PY_API_TOKEN`.

## 4. Error contract
Для `POST /scheduler/task`:
1. `401 unauthorized` — отсутствует/невалиден `Authorization`.
2. `422 missing_trace_id` — отсутствует trace header.
3. `500 scheduler_security_token_not_configured` — baseline enforcement включен, но token не настроен.

## 5. Hardened profile
`DEFERRED` (не реализуется в S4 без отдельного запроса/threat-model):
- `X-Request-Nonce`
- `X-Sent-At`
- replay-window и persistent nonce-store.

## 6. Regression checks
Пройдено:
- `backend/services/automation-engine/test_api.py`

Добавленные кейсы:
1. missing Authorization -> `401`
2. invalid Authorization -> `401`
3. missing X-Trace-Id -> `422`

## 7. Ограничения S4
1. Публикационный pipeline команд не изменён.
2. MQTT/DB/API внешние контракты не ломаются.
3. Реализация ограничена ingress guard и egress headers.
