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
1. Load gate: `PASS (local burst baseline)`:
- `pytest test_api.py` включает burst/churn/high-volume acceptance checks для scheduler cutover/bootstrap/task-ingress paths.
2. Chaos gate: `PASS (local baseline)`:
- `pytest test_scheduler_task_executor.py test_zone_node_recovery.py` -> `72 passed`.
3. Parity gate: `PASS (local baseline)`:
- `pytest test_api.py` -> `79 passed`, включая новые S12 acceptance checks.
4. SLO gate: `PASS (local probe baseline)`:
- подтвержден `s12_cutover_slo_probe.py`, стендовый SLO gate остается обязательным перед full rollout.

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

## 5. Increment 3 (2026-02-18)
1. Добавлены burst/churn acceptance тесты в `test_api.py`:
- `test_scheduler_cutover_contract_endpoints_burst_no_errors` (180 concurrent GET calls);
- `test_scheduler_bootstrap_heartbeat_churn_stays_ready` (30 concurrent bootstrap+heartbeat циклов).
2. Повторный Docker-прогон:
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest test_api.py` -> `79 passed`.
3. Локальный load gate переведен в `PASS (local burst baseline)` без изменения runtime логики.

## 6. Increment 4 (2026-02-18)
1. Добавлен high-volume ingress acceptance тест в `test_api.py`:
- `test_scheduler_task_high_volume_concurrent_submit_stable` (120 concurrent `/scheduler/task` submit с уникальными correlation id).
2. Повторный Docker-прогон:
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest test_api.py` -> `80 passed`.
3. Локальный load gate подтвержден для burst/churn/high-volume сценариев scheduler ingress.

## 7. Increment 5 (2026-02-18)
1. Выполнен consolidated Docker acceptance прогон:
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest test_api.py test_scheduler_task_executor.py test_zone_node_recovery.py` -> `152 passed`.
2. Подтвержден локальный baseline стабильности для cutover parity + chaos recovery + scheduler ingress.

## 8. Increment 6 (2026-02-18)
1. Добавлен reproducible локальный SLO probe:
- `backend/services/automation-engine/tests/s12_cutover_slo_probe.py`.
2. Прогон в Docker:
- `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine python tests/s12_cutover_slo_probe.py`.
3. Результаты локального probe (ms):
- `GET /scheduler/cutover/state`: p50=5.92, p95=6.75, p99=7.11;
- `GET /scheduler/integration/contracts`: p50=6.12, p95=7.18, p99=7.66;
- `GET /scheduler/observability/contracts`: p50=5.86, p95=28.12, p99=28.37;
- `POST /scheduler/bootstrap/heartbeat`: p50=23.21, p95=132.33, p99=138.29.
4. SLO gate переведен в `PASS (local probe baseline)`, стендовый gate остается обязательным перед full rollout.

## 9. Increment 7 (2026-02-18)
1. Добавлен machine-readable SLO baseline artifact:
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_LOCAL_SLO_BASELINE.csv`.
2. Зафиксирован reproducible экспорт:
- `docker compose -f backend/docker-compose.dev.yml run --rm -e AE2_SLO_PROBE_OUTPUT_MODE=csv automation-engine python tests/s12_cutover_slo_probe.py > doc_ai/10_AI_DEV_GUIDES/AE2_S12_LOCAL_SLO_BASELINE.csv`.
3. Последний локальный baseline (ms):
- `cutover_state`: p50=6.42, p95=8.43, p99=8.76;
- `integration_contracts`: p50=6.79, p95=8.95, p99=9.49;
- `observability_contracts`: p50=6.18, p95=26.27, p99=26.42;
- `bootstrap_heartbeat`: p50=25.67, p95=140.67, p99=146.87.

## 10. Следующий инкремент S12
1. Провести стендовый SLO-прогон cutover ingress и зафиксировать p50/p95/p99.
2. Подтвердить/скорректировать SLO gate по стендовым метрикам и оформить release decision.
3. Подготовить `AE2_STAGE_S12_FINAL_REPORT.md` после закрытия обязательных gates.

## 11. Increment 8 (2026-02-19)
1. Подготовлен staging runbook:
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_RUNBOOK.md`.
2. Зафиксирован единый шаблон стендового прогона и артефактов для финального S12 gate.

## 12. Increment 9 (2026-02-19)
1. Подготовлен драфт финального отчета:
- `doc_ai/10_AI_DEV_GUIDES/AE2_STAGE_S12_FINAL_REPORT.md`.
2. В отчете отделены локально закрытые gates и обязательные staging-blockers перед `S12 COMPLETED`.

## 13. Increment 10 (2026-02-19)
1. Выполнен dry-run команды staging runbook в повышенном профиле нагрузки:
- `AE2_SLO_PROBE_REQUESTS=240`, `AE2_SLO_PROBE_CONCURRENCY=40`.
2. Добавлен артефакт формата стендового отчета:
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_SLO_BASELINE.csv`.
3. Результаты dry-run (ms):
- `cutover_state`: p50=11.74, p95=13.97, p99=14.99;
- `integration_contracts`: p50=12.18, p95=33.54, p99=34.19;
- `observability_contracts`: p50=12.77, p95=15.19, p99=15.59;
- `bootstrap_heartbeat`: p50=49.10, p95=186.83, p99=196.83.
4. Статус блокера не меняется: нужен реальный стендовый прогон.

## 14. Increment 11 (2026-02-19)
1. Добавлен автоматический decision-helper:
- `backend/services/automation-engine/tests/s12_slo_release_decision.py`.
2. Прогон decision-helper на `AE2_S12_STAGING_SLO_BASELINE.csv`:
- `decision=ALLOW_FULL_ROLLOUT` (для текущего dry-run baseline).
3. `AE2_S12_STAGING_SLO_RUNBOOK.md` обновлен командой формализации release decision.
4. Статус блокера сохраняется: требуется прогон на реальном стенде.

## 15. Increment 12 (2026-02-19)
1. Сформирован отдельный decision artifact:
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_RELEASE_DECISION.txt`.
2. Для текущего dry-run baseline зафиксирован результат:
- `decision=ALLOW_FULL_ROLLOUT`.
3. Runbook и final report обновлены: decision artifact включен в обязательный пакет для финального S12 gate.

## 16. Increment 13 (2026-02-19)
1. `tests/s12_cutover_slo_probe.py` расширен двумя режимами:
- `AE2_SLO_PROBE_MODE=local` (in-process baseline, как раньше);
- `AE2_SLO_PROBE_MODE=remote` (реальный HTTP probe стенда).
2. Для staging-режима добавлены:
- polling bootstrap (`wait -> ready`) с таймаутом `AE2_SLO_PROBE_BOOTSTRAP_WAIT_SEC`;
- optional `Authorization` header (`AE2_SLO_PROBE_AUTHORIZATION`);
- optional `X-Trace-Id` per-request (`AE2_SLO_PROBE_TRACE_ID_PREFIX`).
3. `AE2_S12_STAGING_SLO_RUNBOOK.md` обновлен: локальный и стендовый прогоны разведены отдельными командами, staging baseline теперь формируется только через `remote` режим.

## 17. Increment 14 (2026-02-19)
1. `tests/s12_cutover_slo_probe.py` hardened для изолированного local-run:
- в `AE2_SLO_PROBE_MODE=local` подменяются DB/infra side-effects (`fetch`, `create_scheduler_log`, `send_infra_alert`) на local no-op stubs;
- снята обязательная зависимость local probe от живых `db/laravel` сервисов.
2. Локальный probe подтвержден в Docker с `--no-deps`:
- human output: `S12 Local SLO Probe Results (in-process ASGI)` с валидными p50/p95/p99 по 4 endpoint-ам;
- csv output: сформирован корректный CSV payload (`endpoint,count,p50_ms,p95_ms,p99_ms,max_ms`).
3. `AE2_S12_STAGING_SLO_RUNBOOK.md` и `AE2_STAGE_S12_TASK.md` обновлены:
- для local/remote probe и decision-helper команд закреплен `docker compose ... run --rm --no-deps ...`;
- снижен риск конфликтов с уже поднятыми `backend-db-1/backend-redis-1` контейнерами при S12 verification.

## 18. Increment 15 (2026-02-19)
1. Обновлен локальный machine-readable baseline:
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_LOCAL_SLO_BASELINE.csv` перегенерирован через `AE2_SLO_PROBE_MODE=local` + `--no-deps`.
2. Последний локальный baseline (ms):
- `cutover_state`: p50=6.81, p95=8.17, p99=8.79;
- `integration_contracts`: p50=7.04, p95=8.37, p99=8.63;
- `observability_contracts`: p50=7.48, p95=26.88, p99=27.19;
- `bootstrap_heartbeat`: p50=12.23, p95=14.86, p99=15.52.
3. Decision-helper по локальному baseline:
- `python tests/s12_slo_release_decision.py --csv-path doc_ai/10_AI_DEV_GUIDES/AE2_S12_LOCAL_SLO_BASELINE.csv`
- результат: `decision=ALLOW_FULL_ROLLOUT`.

## 19. Increment 16 (2026-02-19)
1. Добавлен one-command wrapper для staging gate:
- `tools/testing/run_ae2_s12_staging_gate.sh` (probe + decision, оба артефакта в `doc_ai/10_AI_DEV_GUIDES`).
2. Fail-fast валидация wrapper:
- без `AE2_SLO_PROBE_BASE_URL` скрипт завершает выполнение с `exit 2` и явным сообщением об обязательной переменной.
3. `AE2_S12_STAGING_SLO_RUNBOOK.md` и `AE2_STAGE_S12_TASK.md` обновлены:
- добавлена команда запуска wrapper как эквивалент ручных шагов staging probe + decision.

## 20. Increment 17 (2026-02-19)
1. Wrapper расширен режимами запуска:
- `AE2_SLO_PROBE_MODE=remote` (default, staging gate);
- `AE2_SLO_PROBE_MODE=local` (dry-run полного wrapper pipeline без стенда).
2. Добавлена нормализация output путей:
- `AE2_S12_BASELINE_CSV` и `AE2_S12_DECISION_TXT` автоматически резолвятся относительно корня репозитория, если переданы как relative paths.
3. Подтвержден local wrapper dry-run из подпапки (`tools/testing`):
- baseline/decision артефакты успешно записаны в `artifacts/ae2_s12_local_*_from_tools.*`;
- decision: `ALLOW_FULL_ROLLOUT`.

## 21. Increment 18 (2026-02-19)
1. Добавлен bundle consistency checker:
- `tools/testing/check_ae2_s12_release_bundle.sh`.
2. Checker верифицирует:
- наличие и непустоту `baseline.csv` + `decision.txt`;
- корректный формат первой строки `decision=...` в decision artifact;
- совпадение recorded decision с пересчитанным decision из baseline CSV через `tests/s12_slo_release_decision.py`.
3. На текущем dry-run staging bundle checker возвращает:
- `PASS` (`Recorded decision == Computed decision == ALLOW_FULL_ROLLOUT`).

## 22. Increment 19 (2026-02-19)
1. `tools/testing/check_ae2_s12_release_bundle.sh` усилен до strict gate:
- добавлен `AE2_S12_EXPECT_DECISION` (default: `ALLOW_FULL_ROLLOUT`);
- при несовпадении decision с ожидаемым checker завершает выполнение с ошибкой.
2. Добавлен диагностический override:
- `AE2_S12_EXPECT_DECISION=ANY` отключает проверку expected-decision, оставляя только консистентность bundle.
3. Runbook/task обновлены с двумя режимами (`strict` и `diagnostic`).

## 23. Increment 20 (2026-02-19)
1. `tools/testing/run_ae2_s12_staging_gate.sh` обновлен:
- wrapper теперь автоматически выполняет `check_ae2_s12_release_bundle.sh` после генерации baseline+decision;
- добавлен флаг `AE2_S12_RUN_BUNDLE_CHECK` (`true` по умолчанию, `false` для debug-only режима).
2. Локальная валидация wrapper:
- auto-check mode: `PASS` (bundle consistency + expected decision check);
- debug skip mode (`AE2_S12_RUN_BUNDLE_CHECK=false`): `PASS`, checker корректно пропускается.
3. Runbook/task/README обновлены под новое поведение wrapper (auto-check by default + explicit skip mode).

## 24. Increment 21 (2026-02-19)
1. Добавлена автоматическая генерация gate summary:
- `tools/testing/build_ae2_s12_gate_summary.py` (baseline.csv + decision.txt -> markdown summary).
2. Wrapper `run_ae2_s12_staging_gate.sh` расширен:
- auto-summary включен по умолчанию (`AE2_S12_WRITE_SUMMARY=true`);
- path summary настраивается через `AE2_S12_SUMMARY_MD`.
3. На текущем dry-run staging пакете сформирован:
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_SUMMARY.md`.
4. Runbook/task/README обновлены:
- добавлены команды `AE2_S12_WRITE_SUMMARY=false` и ручной rebuild summary.

## 25. Increment 22 (2026-02-19)
1. Добавлен metadata artifact для staging gate:
- `doc_ai/10_AI_DEV_GUIDES/AE2_S12_STAGING_GATE_METADATA.json`
- (генерация через `tools/testing/build_ae2_s12_gate_metadata.py` и/или wrapper auto-metadata).
2. Bundle checker расширен metadata-валидацией:
- сверка decision в metadata против decision artifact;
- сверка путей baseline/decision из metadata против входных артефактов checker.
3. Добавлен строгий стендовый режим checker:
- `AE2_S12_REQUIRE_REMOTE_METADATA=true` требует `mode=remote` и непустой `base_url` в metadata.
4. Текущее состояние dry-run пакета:
- `./tools/testing/check_ae2_s12_release_bundle.sh` -> `PASS`;
- `AE2_S12_REQUIRE_REMOTE_METADATA=true ./tools/testing/check_ae2_s12_release_bundle.sh` -> `FAIL` (ожидаемо: `metadata base_url is empty`).

## 26. Increment 23 (2026-02-19)
1. Добавлен post-gate финализатор статусов:
- `tools/testing/finalize_ae2_s12_docs.py`.
2. Поведение финализатора:
- `dry-run` показывает целевые изменения без правок;
- `--apply` требует strict gate PASS (внутренний вызов checker с `AE2_S12_REQUIRE_REMOTE_METADATA=true`), иначе завершает выполнение с ошибкой.
3. На текущем dry-run пакете:
- `python3 tools/testing/finalize_ae2_s12_docs.py` -> показывает ожидаемые файлы для смены статуса;
- `python3 tools/testing/finalize_ae2_s12_docs.py --apply` -> корректно блокируется strict gate (ожидаемо до реального стенда).

## 27. Increment 24 (2026-02-19)
1. Wrapper `tools/testing/run_ae2_s12_staging_gate.sh` расширен full-flow режимом:
- `AE2_S12_AUTO_FINALIZE_DOCS=true` для one-command сценария `staging gate + docs finalize`.
2. Защитные условия auto-finalize в wrapper:
- финализация выполняется только при `AE2_SLO_PROBE_MODE=remote`;
- финализация требует включенного bundle-check (`AE2_S12_RUN_BUNDLE_CHECK=true`).
3. Локальная валидация skip-path:
- `AE2_SLO_PROBE_MODE=local ... AE2_S12_AUTO_FINALIZE_DOCS=true ./tools/testing/run_ae2_s12_staging_gate.sh` завершает gate успешно и корректно пропускает finalization вне `remote` режима.

## 28. Increment 25 (2026-02-19)
1. Hardened `tools/testing/finalize_ae2_s12_docs.py`:
- проверка уже добавленной финальной строки в `AE2_CURRENT_STATE.md` переведена на regex (`S12 (increment N): финальный стендовый gate закрыт`) вместо жёсткой привязки к `increment 23`.
2. Добавлена tolerant-логика статус-замен:
- `IN_PROGRESS -> COMPLETED` (и `DRAFT -> COMPLETED`) теперь обрабатывается безопасно, даже если статус уже переведен вручную.
3. Локальная валидация:
- `python3 tools/testing/finalize_ae2_s12_docs.py` продолжает работать в dry-run режиме и корректно показывает список файлов для финализации.

## 29. Increment 26 (2026-02-19)
1. Wrapper `tools/testing/run_ae2_s12_staging_gate.sh` дополнительно защищен для full-flow:
- при `AE2_S12_AUTO_FINALIZE_DOCS=true` auto-finalize теперь явно пропускается, если `AE2_S12_WRITE_METADATA=false`.
2. Причина hardening:
- strict gate финализатора требует metadata (`AE2_S12_REQUIRE_REMOTE_METADATA=true`), поэтому запуск финализации без metadata не имеет смысла и должен отсеиваться заранее.
3. Runbook/README синхронизированы:
- условия full-flow включают три обязательных флага: `remote` mode, `RUN_BUNDLE_CHECK=true`, `WRITE_METADATA=true`.

## 30. Increment 27 (2026-02-19)
1. Strict remote gate усилен в `tools/testing/check_ae2_s12_release_bundle.sh`:
- при `AE2_S12_REQUIRE_REMOTE_METADATA=true` значение `AE2_S12_EXPECT_DECISION=ANY` теперь запрещено (early fail).
2. Финализатор закреплен в strict ALLOW режиме:
- `tools/testing/finalize_ae2_s12_docs.py` принудительно запускает gate-check с `AE2_S12_EXPECT_DECISION=ALLOW_FULL_ROLLOUT`.
3. Wrapper full-flow синхронизирован:
- при `AE2_S12_AUTO_FINALIZE_DOCS=true` финализация пропускается, если установлен `AE2_S12_EXPECT_DECISION=ANY`.

## 31. Increment 28 (2026-02-19)
1. Нормализован `AE2_S12_EXPECT_DECISION` в wrapper/checker:
- `tools/testing/run_ae2_s12_staging_gate.sh` и `tools/testing/check_ae2_s12_release_bundle.sh` приводят значение к uppercase + trim.
2. Эффект hardening:
- исключены ложные FAIL из-за регистра (`allow_full_rollout` == `ALLOW_FULL_ROLLOUT`).
3. Совместимость strict gate сохранена:
- `ANY` продолжает работать только как диагностический режим вне strict remote metadata gate.

## 32. Increment 29 (2026-02-19)
1. Wrapper full-flow дополнительно ограничен по expected decision:
- при `AE2_S12_AUTO_FINALIZE_DOCS=true` auto-finalize выполняется только если `AE2_S12_EXPECT_DECISION=ALLOW_FULL_ROLLOUT`.
2. Причина hardening:
- финализатор переводит `S12` в `COMPLETED`, что допустимо только для позитивного release decision (`ALLOW_FULL_ROLLOUT`), а не для `HOLD_AND_INVESTIGATE`.
3. Runbook/README/task синхронизированы:
- условие `ALLOW_FULL_ROLLOUT` добавлено в preconditions full-flow и в проверочный чек-лист.

## 33. Increment 30 (2026-02-19)
1. Wrapper full-flow ранний strict-check:
- при `AE2_S12_AUTO_FINALIZE_DOCS=true` и `remote` режиме bundle-check запускается с `AE2_S12_REQUIRE_REMOTE_METADATA=true`.
2. Эффект hardening:
- несоответствие strict remote metadata условий выявляется до шага `finalize_ae2_s12_docs.py`, без позднего повторного провала.
3. Runbook/README синхронизированы:
- явно зафиксировано auto-включение strict remote metadata проверки в one-command full flow.

## 34. Increment 31 (2026-02-19)
1. Нормализация `AE2_S12_EXPECT_DECISION` расширена:
- `tools/testing/check_ae2_s12_release_bundle.sh` и `tools/testing/run_ae2_s12_staging_gate.sh` теперь поддерживают опциональный префикс `decision=`.
2. Эффект hardening:
- значения `ALLOW_FULL_ROLLOUT`, `allow_full_rollout` и `decision=allow_full_rollout` эквивалентны;
- снижен риск ложных FAIL из-за ручного копирования первой строки decision artifact в env-переменную.
3. Runbook/README/task синхронизированы:
- добавлены примеры с форматом `AE2_S12_EXPECT_DECISION=decision=...`.

## 35. Increment 32 (2026-02-19)
1. Hardened unsafe override в `tools/testing/finalize_ae2_s12_docs.py`:
- `--skip-gate-check` при `--apply` теперь требует явного подтверждения `AE2_S12_ALLOW_UNSAFE_FINALIZE=true`.
2. Защитный эффект:
- исключен случайный bypass strict gate из-за ошибочного добавления `--skip-gate-check` в операторской команде.
3. Runbook/README/task синхронизированы:
- добавлен аварийный пример запуска с `AE2_S12_ALLOW_UNSAFE_FINALIZE=true` и явной пометкой unsafe режима.
