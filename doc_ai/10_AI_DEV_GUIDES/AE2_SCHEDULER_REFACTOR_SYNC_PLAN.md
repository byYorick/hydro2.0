# [HISTORICAL] AE2 Scheduler: план рефакторинга и синхронизации

**Дата:** 2026-02-19  
**Статус:** HISTORICAL_ARCHIVE  
**Область:** `backend/services/scheduler/main.py`, `backend/services/scheduler/test_main.py`, контракт `scheduler <-> automation-engine`

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

> Важно (2026-02-20): документ исторический.  
> Runtime owner planning/dispatch в текущей модели: Laravel scheduler-dispatch.  
> Источник истины: `doc_ai/10_AI_DEV_GUIDES/LARAVEL_SCHEDULER_MIGRATION_PLAN_FOR_AI.md`.

## 1. Цель

Снизить архитектурный риск монолита `backend/services/scheduler/main.py` и закрепить строгую синхронизацию со слоем `automation-engine` без нарушения защищенного пайплайна:

`Scheduler -> Automation-Engine -> History-Logger -> MQTT -> ESP32`.

Ключевой результат:
1. `scheduler` становится composable-модулем (ingress/planning/dispatch/reconciliation), без роста монолита.
2. Синхронизация `scheduler <-> AE` становится deterministic: lease-aware dispatch, idempotent submit, стабильный reconcile.
3. Поведение при рестартах/частичных сбоях воспроизводимо и покрыто тестами.

---

## 2. Ограничения (не нарушать)

1. `scheduler` не отправляет device-level команды и не обходит `history-logger`.
2. MQTT публикация остается только через AE/CommandBus/history-logger.
3. Не ломать контрактные статусы задач (`accepted/running/completed/failed/rejected/expired`).
4. Все изменения обратимо выкатываются через feature-flag cutover.
5. Разработка и прогоны выполнять в Docker-контуре проекта.

---

## 3. As-Is карта монолита (baseline)

Текущее смешение bounded-context в `backend/services/scheduler/main.py`:
1. Planning/cursors/catchup:
`_resolve_zone_last_check`, `_persist_zone_cursor`, `_apply_catchup_policy`, `_schedule_crossings`, `get_active_schedules`, `check_and_execute_schedules`.
2. Ingress/bootstrap/heartbeat:
`ensure_scheduler_bootstrap_ready`, `send_scheduler_bootstrap_heartbeat`, `_scheduler_headers`.
3. Leader election:
`ensure_scheduler_leader`, `_transition_to_follower`, `release_scheduler_leader`.
4. Dispatch:
`submit_task_to_automation_engine`, `execute_scheduled_task`, correlation/deadline helpers.
5. Polling/reconciliation/restart recovery:
`wait_task_completion`, `_fetch_task_status_once`, `recover_active_tasks_after_restart`, `reconcile_active_tasks`.
6. Internal enqueue recovery:
`_load_pending_internal_enqueues`, `process_internal_enqueued_tasks`.
7. Main loop/orchestration:
`main`.

Проблема: жизненные циклы lease/dispatch/reconcile завязаны на глобальные in-memory state-map, что усложняет эволюцию и локализацию отказов.

---

## 4. Target-архитектура scheduler (to-be)

Целевая структура (фазовый split, без Big Bang):

```text
backend/services/scheduler/
  main.py                        # thin composition root
  app/
    runtime_loop.py              # tick orchestration
    bootstrap_sync.py            # bootstrap + heartbeat state machine
    leader_election.py           # advisory lock lifecycle
    dispatch_service.py          # submit + preflight + active-task register
    reconcile_service.py         # polling + terminal persistence
    internal_enqueue_service.py  # self-enqueue recovery
  domain/
    planning_engine.py           # crossings/catchup/window logic
    schedule_model.py            # normalized schedule/task structures
  infrastructure/
    scheduler_logs_repo.py       # create_scheduler_log wrappers
    zone_events_repo.py          # create_zone_event wrappers
    ae_client.py                 # HTTP client to AE with strict headers
    cursor_store.py              # zone cursor persistence
    metrics.py                   # Prometheus registration/update API
```

Принципы split:
1. `main.py` содержит только wiring + lifecycle.
2. Глобальные map/state заменяются на явный `SchedulerRuntimeState` dataclass.
3. Логика принятия решений отделяется от I/O (fetch/http/logs/events).
4. Все cross-module контракты typed и покрыты unit-тестами.

---

## 5. Модель синхронизации scheduler <-> AE

## 5.1. Ownership
1. `scheduler` владеет только планированием/dispatch abstract-task.
2. `automation-engine` владеет оркестрацией и side-effect командами к устройствам.
3. `history-logger` остается единой точкой MQTT publish.

## 5.2. Ingress contract (strict)
1. Для `POST /scheduler/task` обязательны:
`Authorization`, `X-Trace-Id`, `X-Scheduler-Id`, `X-Scheduler-Lease-Id`.
2. Обязательные поля payload:
`zone_id`, `task_type`, `payload`, `correlation_id`, `scheduled_for`.
3. При временных окнах дополнительно:
`due_at`, `expires_at`.
4. Legacy fallback-пути для missing topology/workflow не расширять; fail-closed только.

## 5.3. Idempotency и dedupe
1. `correlation_id` детерминированный:
`zone_id + task_type + schedule_key + logical_trigger_time`.
2. Повторный submit той же logical-задачи должен возвращать согласованный dedupe-result, без создания нового side-effect execution.
3. `scheduler` хранит в `scheduler_logs` correlation + schedule_key + accepted_at для recovery/reconcile.

## 5.4. Reconciliation contract
1. `accepted/running` задачи живут в explicit active-task registry.
2. Terminal статусы (`completed/failed/rejected/expired/timeout`) фиксируются единожды.
3. При рестарте scheduler восстанавливает active set из latest logs snapshot и дофинализирует через poll.

## 5.5. Bootstrap/lease safety
1. Dispatch разрешен только при `bootstrap_status=ready`.
2. Потеря heartbeat/lease переводит scheduler в safe-mode (dispatch pause + diagnostics).
3. Возврат в ready должен быть явным и подтвержден heartbeat.

---

## 6. Поэтапный roadmap

## Phase 0: ADR + контракты (1 итерация)
1. Зафиксировать ADR split-плана для `scheduler/main.py` (границы модулей и ownership).
2. Зафиксировать scheduler sync contract v1 (headers, required fields, idempotency semantics, terminal mapping).
3. Подготовить migration checklist call-sites и feature flags.

Deliverables:
1. ADR документ в `doc_ai/10_AI_DEV_GUIDES/`.
2. Контрактный markdown для scheduler sync.
3. Список invariants для CI.

## Phase 1: Mechanical split без изменения поведения (1-2 итерации)
1. Вынести из `main.py` в `app/*`:
leader/bootstrap/dispatch/reconcile/internal-enqueue.
2. Вынести planning/catchup/window в `domain/planning_engine.py`.
3. Вынести HTTP/DB adapters в `infrastructure/*`.
4. Оставить `main.py` как composition root.

Acceptance:
1. Поведенческий parity с текущими тестами.
2. `pytest -q backend/services/scheduler/test_main.py` green.

## Phase 2: Синхронизация и state hardening (1-2 итерации)
1. Ввести `SchedulerRuntimeState` и убрать неявные глобальные mutable map.
2. Ужесточить lifecycle lease/heartbeat (единый state machine + reason codes).
3. Унифицировать terminal persistence path (single terminal writer).
4. Добавить защиту от race в active-task registry (atomic operations per task_id/schedule_key).

Acceptance:
1. Нет duplicate terminal writes на task_id.
2. Restart-recovery deterministic в chaos сценариях.

## Phase 3: Idempotency/reconcile hardening (1 итерация)
1. Закрепить stable correlation policy для replay/catchup задач.
2. Добавить explicit dedupe diagnostics в scheduler logs (reused vs new submit).
3. Для poll/reconcile добавить bounded retry/backoff policy и alert codes.

Acceptance:
1. Повторный dispatch того же logical trigger не создает новый side-effect execution.
2. Reconcile завершает зависшие active-task записи в рамках SLA.

## Phase 4: Интеграция и e2e cutover (1 итерация)
1. Прогнать e2e набор automation-engine + scheduler (включая restart, leader churn, bootstrap churn).
2. Canary rollout флагом на staging.
3. После PASS перевести default mode на split-архитектуру.

Acceptance:
1. No-regression по protected pipeline.
2. Ошибки синхронизации не превышают baseline SLO.

---

## 7. Тестовая стратегия

1. Unit:
planning/catchup/window, correlation builder, deadline math, lease state machine.
2. Integration:
submit + poll + terminal persist, internal enqueue recovery, restart recovery.
3. E2E/chaos:
leader switch, bootstrap deny/not-ready, delayed terminal status, AE temporary unavailability.
4. Regression gates:
`pytest -q backend/services/scheduler/test_main.py`
и профильные тесты AE scheduler API.

---

## 8. Риски и rollback

Риски:
1. Непреднамеренное изменение dedupe/dispatch семантики.
2. Drift между bootstrap state и реальным lease состоянием.
3. Потеря active-task snapshot на рестарте при race в terminal persist.

Rollback:
1. Фича-флаг на запуск old-loop path.
2. Reverse switch только после фиксации reason-кодов в diagnostics.
3. При rollback сохранить новый telemetry/diagnostics формат, не откатывая контрактные логи.

---

## 9. Артефакты выполнения

Минимальный пакет завершения плана:
1. ADR split + sync contract.
2. PR с модульным split (`main.py` thin root).
3. Обновленные тесты и отчет parity/e2e.
4. Обновленный `doc_ai/10_AI_DEV_GUIDES/AE2_CURRENT_STATE.md` с закрытием пункта:
`Scheduler monolith split ADR`.
