# SCHEDULER_AUTOMATION_AI_AGENT_ROADMAP_PLAN.md

Дата: 2026-02-10
Статус: Done (R0-R9 закрыты для docker/dev контура)
Область: `backend/services/scheduler`, `backend/services/automation-engine`, `backend/laravel`, `doc_ai/04_BACKEND_CORE`, `doc_ai/05_DATA_AND_STORAGE`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость с legacy/deprecated контрактами не требуется; legacy endpoint-ы, alias-поля и fallback-ветки удаляются при переходе на целевой контракт.

---

## 1. Цель плана

Довести систему `scheduler + automation-engine` до эксплуатационного режима «посадил и забыл»:

1. Детерминированный lifecycle задач без потерь после рестартов.
2. Явные границы ответственности и единый контракт task-status/task-events.
3. Наблюдаемость и SLO для раннего обнаружения деградации.
4. Полное покрытие unit/integration/e2e/chaos сценариями.

## 1.1 Текущий прогресс (на 2026-02-10)

- Закрыт deadline-contract (`due_at/expires_at` mandatory) и fail-fast terminal статусы `rejected|expired`.
- Закрыта идемпотентность по `correlation_id` + `idempotency_payload_mismatch`.
- Закрыт structured outcome (`decision/reason_code/error_code/action_required`) для API-level failure веток.
- Закрыт backend/UI lifecycle+timeline+SLA рендер (`ZoneAutomationTab`) и browser e2e для SLA/timeline (`03-zone-detail.spec.ts`).
- Закрыт recovery-hardening:
  - `automation-engine` startup recovery scanner финализирует `accepted/running` в terminal `failed` (`task_recovered_after_restart`);
  - `scheduler` startup recovery поднимает `accepted` snapshot-ы и дофинализирует их через reconcile;
  - добавлены unit/integration/chaos проверки recovery в:
    - `backend/services/automation-engine/test_api.py`
    - `backend/services/scheduler/test_main.py`
    - `tests/e2e/scheduler/automation_engine_restart_recovery_chaos.sh`
    - `tests/e2e/scheduler/scheduler_restart_recovery_chaos.sh`
- R1 закрыт:
  - добавлены `automation-engine` endpoint-ы `/health/live` и `/health/ready` (legacy alias `/health` удален);
  - readiness учитывает `CommandBus`, DB probe и bootstrap lease-store;
  - bootstrap/heartbeat переведены на readiness-gate (при деградации возвращают `bootstrap_status=wait`);
  - healthcheck в `backend/docker-compose.dev.yml` переведен на API `9405` (`/health/live`).
- R3 закрыт:
  - добавлен startup recovery scanner в `automation-engine` для финализации `accepted/running` задач после рестарта;
  - добавлен startup recovery scanner в `scheduler` для восстановления `accepted` задач после рестарта и последующей reconcile-финализации;
  - recovery-policy: in-flight задачи переводятся в terminal `failed` с `error_code=task_recovered_after_restart` или `status=timeout|not_found` при reconcile;
  - добавлены unit/integration/chaos тесты recovery.
- R2 закрыт:
  - в `scheduler` добавлен single-leader режим через `pg advisory lock` (`SCHEDULER_LEADER_ELECTION=1`);
  - dispatch-gate: только лидер выполняет bootstrap/heartbeat + dispatch;
  - при потере DB-соединения лидер переводится в follower-mode с retry backoff;
  - добавлены anti-silent diagnostics/alerts для `leader backoff`, `bootstrap backoff`, `heartbeat http/not-ready`,
    `schedule busy skip`, `task status http/timeout/not_found`, `internal enqueue invalid/expired/dispatch_failed`,
    а также dispatch-cycle summary logs и метрика `scheduler_dispatch_skips_total`;
  - добавлены unit + service-level integration тесты lock acquire/busy/loss/reacquire
    (включая real PostgreSQL advisory lock session) в `backend/services/scheduler/test_main.py`;
  - добавлены process-level multi-instance integration тесты (2 независимых scheduler-процесса: single-leader + failover/reacquire);
  - добавлен container-level chaos сценарий failover:
    - `tests/e2e/scheduler/scheduler_leader_failover_chaos.sh`.
- R4 закрыт:
  - внедрён persistent cursor (`scheduler_logs`) + catch-up policy `skip|replay_limited|replay_all`;
  - добавлены replay rate-limit, jitter и diagnostics/alerts.
- R5 закрыт:
  - closed-loop success только при terminal `DONE`;
  - `NO_EFFECT/BUSY/INVALID/ERROR/TIMEOUT/SEND_FAILED` трактуются как failure;
  - добавлены поля `command_submitted` vs `command_effect_confirmed` и события `COMMAND_EFFECT_NOT_CONFIRMED`.
- R6 закрыт:
  - добавлен freshness fail-safe (`AE_TELEMETRY_FRESHNESS_*`) для критичной телеметрии бака;
  - добавлены `TANK_LEVEL_STALE` event и `cycle_start_tank_level_stale` reason/error code.
- R7 закрыт:
  - UI показывает DONE-confirm badge, command confirmation counters, SLA, фильтры и пресеты;
  - удалены legacy fallback события/лейблы в scheduler-task timeline.
- R8 закрыт:
  - добавлены SLI/SLO метрики `task_accept_to_terminal_latency`, `task_deadline_violation_rate`,
    `task_recovery_success_rate`, `command_effect_confirm_rate`;
  - добавлены alert rules и валидация `promtool check rules`.
- R0 закрыт:
  - зафиксирована owner-модель статусов (business vs transport);
  - зафиксированы инварианты `due_at/expires_at/correlation_id` и порядок timeline сортировки;
  - синхронизированы `REST_API_REFERENCE.md`, `API_SPEC_FRONTEND_BACKEND_FULL.md`,
    `SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md`, `DATA_MODEL_REFERENCE.md`.
- R9/CI закрыт:
  - chaos сценарии scheduler добавлены в отдельный CI stage `scheduler-chaos`;
  - stage выполняет все скрипты без ранней остановки и публикует docker-логи как artifacts.
  - стабильность подтверждена локально: 5 последовательных прогонов полного chaos-suite (3 скрипта) без падений (2026-02-10).

---

## 2. Формат исполнения этапа (обязательный для ИИ-агента)

Для каждого этапа агент обязан фиксировать:

1. `Scope` — какие файлы/подсистемы затронуты.
2. `Changes` — список изменений по файлам.
3. `Checks` — какие проверки выполнены (lint/tests/smoke/e2e).
4. `Docs` — какие документы обновлены.
5. `Gate` — критерий завершения этапа (pass/fail).
6. `Rollback` — как откатить изменения этапа.

Формат синхронизирован с `doc_ai/10_AI_DEV_GUIDES/AI_AGENT_EXECUTION_PLAN_V2.md`.

## 2.1 Правила реализации (обязательные)

1. Обратная совместимость с legacy/deprecated контрактами не требуется.
2. При переходе на новый контракт legacy endpoint-ы, alias-поля, fallback-ветки и deprecated код удаляются в том же этапе.
3. Новое поведение фиксируется только через целевой контракт Protocol 2.0.
4. Любое удаление legacy сопровождается тестами на новый контракт и обновлением документации.

---

## 3. Дорожная карта по этапам

## R0. Базовая фиксация контракта и инвариантов

Статус: Done.

- Scope:
  - `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md`
  - `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
  - `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
- Changes:
  - зафиксировать owner-модель статусов: business vs transport;
  - зафиксировать инварианты `due_at/expires_at/correlation_id`;
  - зафиксировать event-contract timeline (обязательные поля + порядок сортировки).
- Checks:
  - manual contract review по чек-листу;
  - verify, что Laravel/UI используют тот же словарь статусов/кодов.
- Docs:
  - обновить документы API/контрактов.
- Gate:
  - нет неоднозначности в as-is/to-be разделе;
  - согласован словарь статусов и reason/error кодов.
- Rollback:
  - revert doc-only commit.

## R1. Health/Startup hardening

Статус: Done.

- Scope:
  - `backend/services/automation-engine/main.py`
  - `backend/services/automation-engine/api.py`
  - `backend/docker-compose.dev.yml`
  - `backend/services/automation-engine/test_api.py`
- Changes:
  - отделить health readiness API (`/health/live`, `/health/ready`);
  - сделать readiness зависимым от готовности `CommandBus`, DB и bootstrap lease-store;
  - обновить docker healthcheck: проверять API-порт `9405`, а не только metrics `9401`.
- Checks:
  - `pytest -q backend/services/automation-engine/test_api.py`
  - smoke: контейнер unhealthy при недоступном API.
- Docs:
  - `REST_API_REFERENCE.md` (новые health endpoint-ы и semantics).
- Gate:
  - scheduler не dispatch-ит задачи при degraded readiness automation-engine.
- Rollback:
  - вернуть старые health endpoint-ы и docker healthcheck.

## R2. Single-leader scheduler и failover

Статус: Done.

- Scope:
  - `backend/services/scheduler/main.py`
  - `backend/services/scheduler/test_main.py`
  - (при необходимости) миграция для lease-lock таблицы через Laravel.
- Changes:
  - внедрить лидер-элекцию (`pg advisory lock` или lease-table);
  - гарантировать ровно один dispatcher на greenhouse/cluster;
  - добавить безопасный failover при потере лидера.
- Checks:
  - unit: lock acquire/release/retry (сделано);
  - integration (service-level): advisory lock busy/release/reacquire на реальной PostgreSQL сессии (сделано);
  - integration (process-level multi-instance): второй scheduler-процесс не становится лидером при активном lock + takeover после release (сделано);
  - e2e/chaos (container-level multi-instance): второй scheduler не dispatch-ит при активном лидере + takeover после остановки лидера (`tests/e2e/scheduler/scheduler_leader_failover_chaos.sh`, сделано).
- Docs:
  - `SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md` (раздел failover semantics);
  - `DATA_MODEL_REFERENCE.md` (если добавляется lease table).
- Gate:
  - исключен двойной dispatch в multi-instance сценарии.
- Rollback:
  - feature-flag `SCHEDULER_LEADER_ELECTION=0`.

## R3. Durable recovery scheduler-task после рестарта

Статус: Done.

- Scope:
  - `backend/services/automation-engine/api.py`
  - `backend/services/automation-engine/main.py`
  - `backend/services/automation-engine/test_api.py`
  - `backend/services/scheduler/main.py`
  - `backend/services/scheduler/test_main.py`
- Changes:
  - реализовать startup recovery scanner:
    - поднимать `accepted/running` задачи из `scheduler_logs`;
    - переисполнять/финализировать по policy;
  - добавить guard от двойного исполнения recovery-задач.
- Checks:
  - unit/integration: restart во время `running`;
  - verify: задача доходит до terminal статуса после перезапуска.
- Docs:
  - `SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md` (lifecycle guarantees).
- Gate:
  - нет “зависших” задач после рестарта сервиса.
- Rollback:
  - `AE_TASK_RECOVERY_ENABLED=0`.

## R4. Deterministic scheduling и catch-up policy

Статус: Done.

- Scope:
  - `backend/services/scheduler/main.py`
  - `backend/services/scheduler/test_main.py`
  - (опционально) новая таблица cursor/checkpoints.
- Changes:
  - перейти от in-memory `last_check` к persistent cursor;
  - добавить policy пропущенных окон: `skip`, `replay_limited`, `replay_all` (через конфиг);
  - ограничить burst replay (rate-limit + jitter).
- Checks:
  - unit: вычисление crossings при downtime N минут/часов;
  - integration: восстановление после долгого простоя.
- Docs:
  - `SCHEDULER_AUTOMATION_REFACTOR_PLAN.md` (policy);
  - `DATA_MODEL_REFERENCE.md` (новые сущности при необходимости).
- Gate:
  - предсказуемое поведение после downtime подтверждено тестами.
- Rollback:
  - fallback на старый режим через feature-flag.

## R5. Closed-loop outcome для команд

Статус: Done.

- Scope:
  - `backend/services/automation-engine/scheduler_task_executor.py`
  - `backend/services/automation-engine/infrastructure/command_bus.py`
  - `backend/services/automation-engine/infrastructure/command_tracker.py`
  - `backend/services/automation-engine/test_scheduler_task_executor.py`
- Changes:
  - для критичных task-type включить режим, где успех команды фиксируется только по ответу ноды со статусом `DONE` (через history-logger/CommandTracker);
  - статусы `NO_EFFECT`, `BUSY`, `INVALID`, `ERROR`, `TIMEOUT`, `SEND_FAILED` трактуются как неуспех команды;
  - разделить outcome: `command_submitted` vs `command_effect_confirmed`.
- Checks:
  - unit: переходы статусов команд, включая негативные ветки `NO_EFFECT/BUSY/INVALID/ERROR/TIMEOUT/SEND_FAILED`;
  - integration: failed publish, missing ack, delayed `DONE`, отсутствие `DONE`.
- Docs:
  - `SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md` (новые result поля);
  - `REST_API_REFERENCE.md` (обновлённый контракт `result`).
- Gate:
  - terminal `completed` для execute-сценария допускается только после получения `DONE` от ноды по всем обязательным командам.
- Rollback:
  - feature-flag per task-type (`*_CLOSED_LOOP=0`).

## R6. Safety decision-layer (freshness + confidence)

Статус: Done.

- Scope:
  - `backend/services/automation-engine/scheduler_task_executor.py`
  - `backend/services/automation-engine/test_scheduler_task_executor.py`
- Changes:
  - добавить freshness-порог для критичной телеметрии (tank level и др.);
  - добавить reason/error коды для stale telemetry;
  - fail-safe policy: не исполнять рискованные действия на stale данных.
- Checks:
  - unit: stale/valid telemetry branches;
  - integration: деградация телеметрии в cycle_start/refill workflow.
- Docs:
  - `SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md` (коды и правила decision).
- Gate:
  - ни одна критичная команда не стартует на устаревших данных.
- Rollback:
  - `AE_TELEMETRY_FRESHNESS_ENFORCE=0`.

## R7. UI hardening и операторский UX

Статус: Done.

- Scope:
  - `backend/laravel/resources/js/Pages/Zones/Tabs/ZoneAutomationTab.vue`
  - `backend/laravel/resources/js/composables/useZoneAutomationTab.ts`
  - `backend/laravel/resources/js/Pages/Zones/Tabs/__tests__/ZoneAutomationTab.spec.ts`
  - `backend/laravel/tests/Feature/SchedulerTaskControllerTest.php`
  - `tests/e2e/browser/specs/03-zone-detail.spec.ts`
- Changes:
  - доработать task lifecycle panel: явные состояния `accepted/running/completed/failed/rejected/expired`, SLA и decision outcome;
  - добавить отдельную UI-индикацию подтверждённого исполнения команды по статусу ноды `DONE`;
  - добавить фильтры/поиск и быстрые пресеты по ошибкам (`error_code/reason_code`) для операторского разбора инцидентов;
  - удалить legacy отображения, legacy label mappings и fallback-ветки, не соответствующие целевому контракту.
- Checks:
  - unit (vitest): маппинг статусов/decision/reason/error и SLA мета;
  - feature (Laravel): `timeline[]` и `result` fallback без legacy-полей;
  - browser e2e: сценарии `completed(DONE)/failed/rejected/expired` и отображение причин.
- Docs:
  - `doc_ai/07_FRONTEND/FRONTEND_UI_UX_SPEC.md`
  - `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md`
- Gate:
  - оператор в UI видит подтверждение `DONE` для execute-команд и полный timeline без legacy-статусов.
- Rollback:
  - пофайловый revert UI-изменений этапа.

## R8. Наблюдаемость и SLO

Статус: Done.

- Scope:
  - `backend/services/scheduler/main.py`
  - `backend/services/automation-engine/main.py`
  - `configs/dev/prometheus.yml`
  - `configs/dev/prometheus/alerts.yml`
  - `backend/laravel/resources/js/composables/useZoneAutomationTab.ts` (при необходимости SLO badges)
- Changes:
  - добавить SLI-метрики:
    - `task_accept_to_terminal_latency`
    - `task_deadline_violation_rate`
    - `task_recovery_success_rate`
    - `command_effect_confirm_rate` (для closed-loop задач);
  - добавить alert rules по SLO/error budget.
- Checks:
  - unit smoke метрик;
  - promtool check rules;
  - local alert dry-run.
- Docs:
  - `doc_ai/04_BACKEND_CORE/REALTIME_UPDATES_ARCH.md` (если меняется поток realtime);
  - раздел SLO в `SCHEDULER_AUTOMATION_REFACTOR_PLAN.md`.
- Gate:
  - SLO дашборд показывает SLA и recovery в разрезе зоны/task-type.
- Rollback:
  - отключение новых alert groups и графиков.

## R9. E2E/Chaos/HIL верификация и релиз

Статус: Done (для docker/dev контура).

- Scope:
  - `tests/e2e/*`
  - `infra/hil/*` (если используете HIL контур)
  - `backend/laravel/tests/Feature/SchedulerTaskControllerTest.php`
  - `backend/services/scheduler/test_main.py`
  - `backend/services/automation-engine/test_api.py`
- Changes:
  - добавить e2e сценарии:
    - lease loss + re-bootstrap;
    - restart automation-engine во время running task;
    - restart scheduler во время pending/reconcile;
    - refill success / refill timeout / stale telemetry;
  - добавить chaos runbook (какие сервисы/в каком порядке перезапускать).
  - статус на 2026-02-10:
    - lease-loss/re-bootstrap покрыт service-level тестами (`automation-engine/test_api.py`, `scheduler/test_main.py`);
    - restart automation-engine recovery покрыт chaos скриптом `tests/e2e/scheduler/automation_engine_restart_recovery_chaos.sh`;
    - restart scheduler pending/reconcile покрыт chaos скриптом `tests/e2e/scheduler/scheduler_restart_recovery_chaos.sh`;
    - multi-instance failover покрыт chaos скриптом `tests/e2e/scheduler/scheduler_leader_failover_chaos.sh`;
    - chaos-suite (`leader_failover + scheduler_restart_recovery + automation_engine_restart_recovery`) пройден 5 раз подряд в docker/dev контуре;
    - refill success / timeout / stale telemetry покрыты unit/integration тестами `backend/services/automation-engine/test_scheduler_task_executor.py`;
    - browser e2e lifecycle/SLA/DONE покрыт `tests/e2e/browser/specs/03-zone-detail.spec.ts`.
- Checks:
  - e2e pass в docker;
  - chaos suite pass;
  - smoke в staging.
- Docs:
  - обновить `SCHEDULER_AUTOMATION_REFACTOR_PLAN.md` статусами “сделано”;
  - финальный changelog в backend docs.
- Gate:
  - релизный checklist закрыт, критических дефектов нет.
- Rollback:
  - откат поэтапно feature-flag-ами + rollback миграций по инструкции.

---

## 4. Матрица тестов (минимум)

1. Unit:
   - deadline/idempotency/lease проверки API;
   - decision-layer ветки (`run/skip/retry/fail` + transport `timeout/not_found`).
2. Integration:
   - scheduler <-> automation-engine lifecycle;
   - internal enqueue + recovery после рестарта.
3. Feature (Laravel):
   - `GET /api/zones/{zone}/scheduler-tasks` и `.../{taskId}`;
   - timeline parsing из `result` fallback.
4. E2E:
   - сценарии R9 (lease/restart/refill/stale telemetry + UI lifecycle flows).
5. Chaos:
   - controlled restarts + network degradation.

---

## 5. Команды проверки (Docker, ориентир)

1. `docker compose -f backend/docker-compose.dev.yml run --rm scheduler pytest -q test_main.py`
2. `docker compose -f backend/docker-compose.dev.yml run --rm automation-engine pytest -q test_api.py test_scheduler_task_executor.py`
3. `docker compose -f backend/docker-compose.dev.yml run --rm laravel php artisan test --filter=SchedulerTaskControllerTest`
4. `docker compose -f backend/docker-compose.dev.yml run --rm laravel npm run test -- resources/js/Pages/Zones/Tabs/__tests__/ZoneAutomationTab.spec.ts`
5. `docker compose -f tests/e2e/docker-compose.e2e.yml up --abort-on-container-exit --exit-code-from e2e-runner`
6. `bash tests/e2e/scheduler/scheduler_leader_failover_chaos.sh`
7. `bash tests/e2e/scheduler/scheduler_restart_recovery_chaos.sh`
8. `bash tests/e2e/scheduler/automation_engine_restart_recovery_chaos.sh`

Если добавлены новые тест-модули, они должны быть включены в CI до закрытия этапа.

---

## 6. Матрица документации (обязательное обновление)

1. Контракты API:
   - `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
   - `doc_ai/04_BACKEND_CORE/API_SPEC_FRONTEND_BACKEND_FULL.md`
2. Архитектурные документы:
   - `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_REFACTOR_PLAN.md`
   - `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md`
3. Модель данных:
   - `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` (если есть новые таблицы/поля).
4. Совместимость:
   - фиксировать `Compatible-With` в PR/commit при изменении контрактов.

---

## 7. Критерии готовности “посадил и забыл”

1. Нет потери task lifecycle при рестартах сервисов.
2. Нет двойного dispatch в multi-instance scheduler.
3. Критичные решения не принимаются на stale телеметрии.
4. SLA дедлайны контролируются автоматически, нарушения видны в SLO дашборде.
5. Успех execute-команд подтверждается только ответом ноды `DONE`.
6. UI отображает lifecycle/timeline и `DONE`-подтверждение без legacy fallback поведения.
7. E2E/chaos сценарии проходят стабильно не менее 5 прогонов подряд.
