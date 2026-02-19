# AE2_S12_STAGING_SLO_RUNBOOK.md
# AE2 S12 Staging SLO Runbook

**Версия:** v0.1  
**Дата:** 2026-02-19  
**Статус:** READY

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Цель
1. Провести стендовую SLO-проверку scheduler cutover ingress перед закрытием `S12`.
2. Зафиксировать p50/p95/p99 для ключевых endpoint-ов и release decision.

## 2. Обязательные endpoint-ы
1. `GET /scheduler/cutover/state`
2. `GET /scheduler/integration/contracts`
3. `GET /scheduler/observability/contracts`
4. `POST /scheduler/bootstrap/heartbeat`

## 3. Подготовка стенда
1. Поднять актуальный docker-профиль backend + services.
2. Проверить readiness:
- `GET /health/live` -> `200`
- `GET /health/ready` -> `200`
3. Убедиться, что bootstrap-contract возвращает `bootstrap_status=ready`.

## 4. Прогон
1. Базовый probe (CSV артефакт):
```bash
docker compose -f backend/docker-compose.dev.yml run --rm \
  -e AE2_SLO_PROBE_OUTPUT_MODE=csv \
  -e AE2_SLO_PROBE_REQUESTS=240 \
  -e AE2_SLO_PROBE_CONCURRENCY=40 \
  automation-engine python tests/s12_cutover_slo_probe.py \
  > doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv
```
2. Параллельно сохранить сервисные логи `automation-engine` и `scheduler`.

## 5. Gate-таблица (заполнить по факту)
1. `load gate`: `PASS/FAIL`
2. `chaos gate`: `PASS/FAIL`
3. `parity gate`: `PASS/FAIL`
4. `slo gate`: `PASS/FAIL`

## 6. Что приложить к S12 final report
1. `AE2_S12_STAGING_SLO_BASELINE.csv`
2. Краткий summary p50/p95/p99 по каждому endpoint.
3. Release decision:
- `ALLOW_FULL_ROLLOUT` или `HOLD_AND_INVESTIGATE`.
4. Список отклонений (если есть) и mitigation-план.

