# AE2_STAGE_S12_TASK.md
# Stage S12: Load + Chaos + Acceptance

**Версия:** v0.1  
**Дата:** 2026-02-18  
**Статус:** IN_PROGRESS  
**Роль:** AI-QA  
**Режим:** implementation

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Входной контекст (что прочитать)
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_ENGINE_AE2_MASTER_PLAN_FOR_AI.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S11_FINAL_REPORT.md`
- `backend/services/automation-engine/test_api.py`
- `backend/services/automation-engine/test_scheduler_task_executor.py`
- `backend/services/automation-engine/test_zone_node_recovery.py`

## 2. Конкретные файлы для изменения
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S12_TASK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_ACCEPTANCE_VALIDATION_S12.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_RUNBOOK.md`
- `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md`
- `backend/services/automation-engine/test_api.py`
- профильные тесты `backend/services/automation-engine/test_*.py` (по необходимости)

## 3. Файлы, которые запрещено менять
- `backend/services/automation-engine/infrastructure/command_bus.py` (кроме явного bugfix по S12 acceptance blocker)
- `backend/services/automation-engine/main.py` (кроме явного bugfix по S12 acceptance blocker)
- `backend/services/history-logger/*`
- любые MQTT topic/spec контракты без отдельного stage-решения

## 4. Тесты для проверки
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest test_api.py`
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest test_scheduler_task_executor.py test_zone_node_recovery.py`
- `docker compose -f backend/docker-compose.dev.yml run --rm --no-deps -e AE2_SLO_PROBE_MODE=local automation-engine python tests/s12_cutover_slo_probe.py`
- `docker compose -f backend/docker-compose.dev.yml run --rm --no-deps -e AE2_SLO_PROBE_MODE=local -e AE2_SLO_PROBE_OUTPUT_MODE=csv automation-engine python tests/s12_cutover_slo_probe.py > doc_ai/10_AI_DEV_GUIDES/AE2_S12_LOCAL_SLO_BASELINE.csv`
- `docker compose -f backend/docker-compose.dev.yml run --rm --no-deps -e AE2_SLO_PROBE_MODE=remote -e AE2_SLO_PROBE_BASE_URL=http://<staging-ae-host>:<port> -e AE2_SLO_PROBE_AUTHORIZATION='Bearer <token>' -e AE2_SLO_PROBE_OUTPUT_MODE=csv automation-engine python tests/s12_cutover_slo_probe.py > doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv`
- `cat doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv | docker compose -f backend/docker-compose.dev.yml run --rm --no-deps -T automation-engine python tests/s12_slo_release_decision.py --stdin`
- `AE2_SLO_PROBE_BASE_URL=http://<staging-ae-host>:<port> AE2_SLO_PROBE_AUTHORIZATION='Bearer <token>' ./tools/testing/run_ae2_s12_staging_gate.sh`
- `AE2_SLO_PROBE_MODE=local AE2_S12_BASELINE_CSV=artifacts/ae2_s12_local_baseline.csv AE2_S12_DECISION_TXT=artifacts/ae2_s12_local_decision.txt ./tools/testing/run_ae2_s12_staging_gate.sh`
- `AE2_SLO_PROBE_MODE=local AE2_S12_RUN_BUNDLE_CHECK=false ./tools/testing/run_ae2_s12_staging_gate.sh` (отладочный режим wrapper без auto-check)
- `AE2_SLO_PROBE_MODE=local AE2_S12_WRITE_SUMMARY=false ./tools/testing/run_ae2_s12_staging_gate.sh` (отладочный режим wrapper без auto-summary)
- `AE2_SLO_PROBE_MODE=local AE2_S12_WRITE_METADATA=false ./tools/testing/run_ae2_s12_staging_gate.sh` (отладочный режим wrapper без auto-metadata)
- `./tools/testing/check_ae2_s12_release_bundle.sh`
- `AE2_S12_EXPECT_DECISION=allow_full_rollout ./tools/testing/check_ae2_s12_release_bundle.sh` (ожидаемый PASS: нормализация регистра expected decision)
- `AE2_S12_EXPECT_DECISION=decision=allow_full_rollout ./tools/testing/check_ae2_s12_release_bundle.sh` (ожидаемый PASS: поддержка опционального префикса `decision=`)
- `AE2_S12_EXPECT_DECISION=ANY ./tools/testing/check_ae2_s12_release_bundle.sh` (диагностический режим, без strict ALLOW gate)
- `AE2_S12_REQUIRE_REMOTE_METADATA=true ./tools/testing/check_ae2_s12_release_bundle.sh` (финальный strict gate для стенда)
- `AE2_S12_REQUIRE_REMOTE_METADATA=true AE2_S12_EXPECT_DECISION=ANY ./tools/testing/check_ae2_s12_release_bundle.sh` (ожидаемый FAIL: strict remote gate не допускает ANY)
- `AE2_SLO_PROBE_MODE=local AE2_S12_AUTO_FINALIZE_DOCS=true AE2_S12_EXPECT_DECISION=HOLD_AND_INVESTIGATE ./tools/testing/run_ae2_s12_staging_gate.sh` (ожидаемый FAIL на strict bundle-check для текущего ALLOW baseline; auto-finalize допустим только при `ALLOW_FULL_ROLLOUT`)
- `python3 tools/testing/build_ae2_s12_gate_summary.py --baseline-csv doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv --decision-txt doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_RELEASE_DECISION.txt --output-md doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_SUMMARY.md --mode remote`
- `python3 tools/testing/build_ae2_s12_gate_metadata.py --mode remote --baseline-csv doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv --decision-txt doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_RELEASE_DECISION.txt --summary-md doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_SUMMARY.md --output-json doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_METADATA.json --base-url http://<staging-ae-host>:<port> --requests 240 --concurrency 40 --bootstrap-wait-sec 60 --run-bundle-check true --expect-decision ALLOW_FULL_ROLLOUT`
- `python3 tools/testing/finalize_ae2_s12_docs.py` (dry-run финализации статусов)
- `python3 tools/testing/finalize_ae2_s12_docs.py --apply` (применять только после strict gate PASS)
- `python3 tools/testing/finalize_ae2_s12_docs.py --apply --skip-gate-check` (ожидаемый FAIL без `AE2_S12_ALLOW_UNSAFE_FINALIZE=true`)
- `AE2_SLO_PROBE_BASE_URL=http://<staging-ae-host>:<port> AE2_SLO_PROBE_AUTHORIZATION='Bearer <token>' AE2_S12_AUTO_FINALIZE_DOCS=true ./tools/testing/run_ae2_s12_staging_gate.sh` (полный one-command flow)
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_RUNBOOK.md` (стендовый SLO gate)

## 5. Критерий завершения
1. Есть acceptance-отчет `AE2_ACCEPTANCE_VALIDATION_S12.md` с load/chaos/parity/SLO gate-статусами.
2. Regression suite по затронутым тестам зеленый в Docker.
3. `AE2_CURRENT_STATE.md` обновлен до статуса `S12 COMPLETED` и содержит финальный gate-increment.
