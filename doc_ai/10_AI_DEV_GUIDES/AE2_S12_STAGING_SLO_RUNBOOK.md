# AE2_S12_STAGING_SLO_RUNBOOK.md
# AE2 S12 Staging SLO Runbook

**Версия:** v0.9  
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
1. Локальный baseline probe (контроль воспроизводимости, не заменяет staging):
```bash
docker compose -f backend/docker-compose.dev.yml run --rm \
  --no-deps \
  -e AE2_SLO_PROBE_MODE=local \
  -e AE2_SLO_PROBE_OUTPUT_MODE=csv \
  -e AE2_SLO_PROBE_REQUESTS=240 \
  -e AE2_SLO_PROBE_CONCURRENCY=40 \
  automation-engine python tests/s12_cutover_slo_probe.py \
  > doc_ai/10_AI_DEV_GUIDES/AE2_S12_LOCAL_SLO_BASELINE.csv
```
2. Staging probe (обязательный gate, реальный стенд):
```bash
docker compose -f backend/docker-compose.dev.yml run --rm \
  --no-deps \
  -e AE2_SLO_PROBE_MODE=remote \
  -e AE2_SLO_PROBE_BASE_URL=http://<staging-ae-host>:<port> \
  -e AE2_SLO_PROBE_AUTHORIZATION='Bearer <token>' \
  -e AE2_SLO_PROBE_OUTPUT_MODE=csv \
  -e AE2_SLO_PROBE_REQUESTS=240 \
  -e AE2_SLO_PROBE_CONCURRENCY=40 \
  -e AE2_SLO_PROBE_BOOTSTRAP_WAIT_SEC=60 \
  automation-engine python tests/s12_cutover_slo_probe.py \
  > doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv
```
3. Параллельно сохранить сервисные логи `automation-engine` и `scheduler`.
4. Рассчитать release decision по staging CSV артефакту:
```bash
cat doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv | \
  docker compose -f backend/docker-compose.dev.yml run --rm --no-deps -T \
  automation-engine python tests/s12_slo_release_decision.py --stdin \
  > doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_RELEASE_DECISION.txt
```
5. One-command wrapper (опционально, эквивалент шагам 2+4):
```bash
AE2_SLO_PROBE_BASE_URL=http://<staging-ae-host>:<port> \
AE2_SLO_PROBE_AUTHORIZATION='Bearer <token>' \
./tools/testing/run_ae2_s12_staging_gate.sh
```
Примечание: wrapper автоматически вызывает `check_ae2_s12_release_bundle.sh` после генерации артефактов.
Дополнительно wrapper автоматически формирует summary:
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_SUMMARY.md` (или `AE2_S12_SUMMARY_MD`).
И автоматически формирует metadata:
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_METADATA.json` (или `AE2_S12_METADATA_JSON`).
6. Wrapper local dry-run (опционально, без стенда):
```bash
AE2_SLO_PROBE_MODE=local \
AE2_S12_BASELINE_CSV=artifacts/ae2_s12_local_baseline.csv \
AE2_S12_DECISION_TXT=artifacts/ae2_s12_local_decision.txt \
./tools/testing/run_ae2_s12_staging_gate.sh
```
7. Примечание по путям артефактов wrapper:
- если `AE2_S12_BASELINE_CSV`/`AE2_S12_DECISION_TXT` заданы relative path, они автоматически резолвятся от корня репозитория.
8. Bundle consistency check (рекомендуется перед переводом `S12` в `COMPLETED`):
```bash
./tools/testing/check_ae2_s12_release_bundle.sh
```
9. Режимы проверки решения:
- по умолчанию checker требует `decision=ALLOW_FULL_ROLLOUT` (strict gate);
- для диагностического прогона без блокировки по `HOLD`:
```bash
AE2_S12_EXPECT_DECISION=ANY ./tools/testing/check_ae2_s12_release_bundle.sh
```
- `AE2_S12_EXPECT_DECISION` case-insensitive (`allow_full_rollout` и `ALLOW_FULL_ROLLOUT` эквивалентны);
- также поддерживается формат `AE2_S12_EXPECT_DECISION=decision=allow_full_rollout` (префикс `decision=` опционален);
- для wrapper можно временно отключить auto-check:
```bash
AE2_S12_RUN_BUNDLE_CHECK=false ./tools/testing/run_ae2_s12_staging_gate.sh
```
10. Управление summary-артефактом wrapper:
- отключить auto-summary:
```bash
AE2_S12_WRITE_SUMMARY=false ./tools/testing/run_ae2_s12_staging_gate.sh
```
- вручную пересобрать summary из текущего baseline+decision:
```bash
python3 tools/testing/build_ae2_s12_gate_summary.py \
  --baseline-csv doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv \
  --decision-txt doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_RELEASE_DECISION.txt \
  --output-md doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_SUMMARY.md \
  --mode remote
```
11. Ручная пересборка metadata (если нужен явный override):
```bash
python3 tools/testing/build_ae2_s12_gate_metadata.py \
  --mode remote \
  --baseline-csv doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv \
  --decision-txt doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_RELEASE_DECISION.txt \
  --summary-md doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_SUMMARY.md \
  --output-json doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_METADATA.json \
  --base-url http://<staging-ae-host>:<port> \
  --requests 240 \
  --concurrency 40 \
  --bootstrap-wait-sec 60 \
  --run-bundle-check true \
  --expect-decision ALLOW_FULL_ROLLOUT
```
12. Финальная строгая проверка перед `S12 COMPLETED` (обязательна для стенда):
```bash
AE2_S12_REQUIRE_REMOTE_METADATA=true ./tools/testing/check_ae2_s12_release_bundle.sh
```
13. Опциональная автоматизация финализации документов (только после шага 12 PASS):
```bash
python3 tools/testing/finalize_ae2_s12_docs.py --apply
```
Проверка без изменений (dry-run):
```bash
python3 tools/testing/finalize_ae2_s12_docs.py
```
Небезопасный override (только аварийный случай; bypass strict gate требует явного подтверждения):
```bash
AE2_S12_ALLOW_UNSAFE_FINALIZE=true \
python3 tools/testing/finalize_ae2_s12_docs.py --apply --skip-gate-check
```
14. One-command full flow (staging gate + auto finalize):
```bash
AE2_SLO_PROBE_BASE_URL=http://<staging-ae-host>:<port> \
AE2_SLO_PROBE_AUTHORIZATION='Bearer <token>' \
AE2_S12_AUTO_FINALIZE_DOCS=true \
./tools/testing/run_ae2_s12_staging_gate.sh
```
Условия auto-finalize:
- только `AE2_SLO_PROBE_MODE=remote`;
- только при включенном bundle-check (`AE2_S12_RUN_BUNDLE_CHECK=true`, default).
- только при включенном metadata artifact (`AE2_S12_WRITE_METADATA=true`, default).
- только при strict expected decision (`AE2_S12_EXPECT_DECISION` не `ANY`, default: `ALLOW_FULL_ROLLOUT`).
- только при `AE2_S12_EXPECT_DECISION=ALLOW_FULL_ROLLOUT`.
Примечание: при `AE2_S12_AUTO_FINALIZE_DOCS=true` wrapper запускает bundle-check в strict remote metadata режиме (`AE2_S12_REQUIRE_REMOTE_METADATA=true`) до шага финализации.

## 5. Gate-таблица (заполнить по факту)
1. `load gate`: `PASS/FAIL`
2. `chaos gate`: `PASS/FAIL`
3. `parity gate`: `PASS/FAIL`
4. `slo gate`: `PASS/FAIL`

## 6. Что приложить к S12 final report
1. `AE2_S12_STAGING_SLO_BASELINE.csv`
2. `AE2_S12_STAGING_RELEASE_DECISION.txt` (decision + violations, если есть).
3. Краткий summary p50/p95/p99 по каждому endpoint.
4. Release decision:
- `ALLOW_FULL_ROLLOUT` или `HOLD_AND_INVESTIGATE`.
5. Список отклонений (если есть) и mitigation-план.
