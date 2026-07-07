# AGENT.md (automation-engine / AE3-Lite v1)

Краткие инструкции для ИИ-ассистента при работе в `backend/services/automation-engine`.
Обновлено: 2026-05-28 (sync с runtime кодом: `update_stage`, error codes, file tree)
Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Главная цель

Поддерживать и развивать **AE3-Lite v1** — DB-backed executor для `cycle_start`, `irrigation_start`, `lighting_tick` и `greenhouse_climate_tick`.
Canonical spec: `doc_ai/04_BACKEND_CORE/ae3lite.md`.

Прежний monolithic automation runtime удалён. Рабочий пакет автоматики — `ae3lite/`.

## 2. Жёсткие ограничения (инварианты из spec §2)

1. Никакого прямого MQTT из AE или Laravel.
2. Все команды к узлам идут только через `history-logger` (`POST /commands`).
3. Одна активная execution task на зону — гарантируется partial unique index и `ae_zone_leases`; отдельно single-writer lease на теплицу для `greenhouse_climate_tick` — `greenhouse_automation_leases`.
4. Успешный terminal outcome mutating-команды только `DONE`; все остальные — fail.
5. Изменения схемы БД только через Laravel миграции (не ручной DDL).
6. `ae3lite/*` не импортирует legacy runtime пакеты.
7. Переключение `zones.automation_runtime` на `ae3` запрещено при активной task или lease.
8. Runtime читает zone state напрямую из PostgreSQL read-model, без HTTP к Laravel.
9. Единственный internal status endpoint: `GET /internal/tasks/{task_id}`.
10. Внешние ingress AE3-Lite: `POST /zones/{id}/start-cycle`, `POST /zones/{id}/start-irrigation`, `POST /zones/{id}/start-lighting-tick`, `POST /greenhouses/{id}/start-climate-tick` (плюс internal `GET /internal/tasks/{task_id}`).
11. Hardcoded default targets запрещены (spec §5.3.4); отсутствие target → `PlannerConfigurationError`.
12. CAS-промах в `zone_workflow_state.upsert_phase` → `Ae3LiteError` (не silent None).

## 3. Структура кода

```
ae3lite/
  api/                # HTTP endpoints (compat + internal), security, rate_limit
  greenhouse_climate/ # rule-based roof vent tick (POST /greenhouses/{id}/start-climate-tick)
  domain/
    entities/         # AutomationTask, ZoneWorkflow, ZoneLease, PlannedCommand
    errors.py         # ErrorCodes + domain exceptions
    services/         # CycleStartPlanner, CorrectionPlanner, irrigation_decision_controller
    value_objects.py
  application/
    use_cases/        # create_task_from_intent, claim_next_task, execute_task,
                      # finalize_task, startup_recovery
    handlers/         # stage handlers: startup, clean_fill_*, solution_fill_*,
                      # prepare_recirc_*, await_ready, decision_gate,
                      # irrigation_*, correction, base (с _checkpoint hot-reload)
    services/         # workflow_topology (TWO_TANK graph), workflow_router,
                      # topology_registry, correction_transition_policy
    adapters/         # intent mapping
  config/             # Pydantic schemas, runtime_plan_builder, loader
  infrastructure/
    repositories/     # PgAutomationTaskRepository (claim/update_stage/mark_*),
                      # PgZoneWorkflowRepository, PgZoneLeaseRepository,
                      # PgAeCommandRepository, PgPidStateRepository
    gateways/         # SequentialCommandGateway (publish + recover_waiting_command polling)
    clients/          # HistoryLoggerClient
    read_models/      # PgZoneSnapshotReadModel, TaskStatusReadModel,
                      # ZoneRuntimeMonitor, laravel_schema_contract
    intent_status_listener.py   # LISTEN scheduler_intent_terminal → worker.kick()
    zone_event_listener.py      # LISTEN ae_zone_event → worker.kick()
  runtime/
    worker.py         # Ae3RuntimeWorker (drain loop, lease heartbeat)
    bootstrap.py      # build_ae3_runtime_bundle()
    env.py            # Ae3RuntimeConfig.from_env()
    app.py            # create_app() / serve()
main.py               # точка входа → ae3lite.main
```

Все `common/` и `utils/` — только вспомогательные; основная логика в `ae3lite/`.

## 4. Task FSM

```
pending → claimed → running → waiting_command → completed
                                               → failed
                  → failed (любой exception)
                  → cancelled (control_mode_switched_to_manual)
```

Stage re-enqueue (two-tank workflow): атомарный `update_stage` из `PgAutomationTaskRepository`. Он одной транзакцией переводит `(claimed|running|waiting_command) → pending`, сбрасывает `claimed_by/claimed_at` и обновляет `current_stage` + correction-поля (`corr_*`). Прежний `requeue_pending` снят, любой stage handler возвращает `StageOutcome.transition/poll/enter_correction`, который `WorkflowRouter` транслирует в `update_stage`.

Ключевые методы:
- `claim_next_pending`: `pending → claimed` с `FOR UPDATE SKIP LOCKED`.
- `mark_running`: WHERE `status IN ('claimed','running')` (не `waiting_command`).
- `mark_waiting_command` / `resume_after_waiting_command`: ожидание terminal в `commands` и возврат в `running`.
- `mark_completed` / `mark_failed`: terminal.
- `release_claim`: rollback `claimed → pending` (при провале `ZoneLease.claim`).
- `update_stage`: атомарный stage advance с requeue (см. выше).

## 5. Политика cleanup

1. Если новая функция готова — соответствующий устаревший код удаляется в той же итерации.
2. Нельзя оставлять "временно отключенный" код.
3. Любой неиспользуемый код, endpoint, флаг, тест — удалить.
4. После крупного этапа обязателен cleanup-аудит.

## 6. Definition of Done (Summary)

Полный список — spec §13. Критичные критерии:
- Все 320 Python тестов зелёные (`pytest -x -q` в контейнере).
- Laravel AE3 тесты зелёные (`php artisan test --filter="Ae3Lite"`).
- E2E сценарии пройдены: `start-cycle→DONE→completed`, `TIMEOUT→failed`,
  `restart during waiting_command → recovered`, `runtime switch denied while busy`.
- На staging: минимум один rollout и один rollback.
- Хотя бы одна production зона отработала на `automation_runtime='ae3'`.

## 7. Типовые error codes

Полный канонический реестр — `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md`. Здесь — только наиболее частые в AE3 runtime.

Ingress / task creation:
- `start_cycle_zone_busy` — у зоны уже есть active task или active lease.
- `start_cycle_idempotency_key_conflict` — другой intent уже занял тот же `(zone_id, idempotency_key)`.
- `start_irrigation_setup_pending` — `POST /zones/{id}/start-irrigation` вызван до перехода зоны в `workflow_phase='ready'`.
- `ae3_task_create_failed` — не удалось вставить task (DB-сбой, нарушение constraints).

Snapshot / topology:
- `ae3_snapshot_no_active_grow_cycle`, `ae3_snapshot_bundle_invalid` — типичные snapshot-ошибки.
- `ae3_snapshot_required_node_type_missing` — для топологии two_tank/`two_tank_drip_substrate_trays` отсутствует узел обязательного типа (`irrig|ph|ec`).
- `ae3_snapshot_required_node_persistently_offline` — обязательный узел не отвечает дольше `AE3_NODE_PERSISTENT_DEAD_SEC` (fail-closed без retry).
- `ae3_snapshot_no_online_actuator_channels` — нет ни одного online actuator/service канала.

Execution / FSM:
- `ae3_complete_transition_failed` — не удалось перевести task в `completed` (CAS-промах).
- `ae3_transition_apply_failed`, `ae3_poll_apply_failed`, `ae3_correction_apply_failed` — `WorkflowRouter` не смог применить `StageOutcome` через `update_stage`.
- `ae3_zone_lease_lost`, `ae3_zone_lease_release_failed` — runtime потерял или не смог отдать lease.
- `ae3_task_execution_timeout` — превышен `AE_MAX_TASK_EXECUTION_SEC`.
- `runtime_plan_missing` — у task в `running/waiting_command` нет RuntimePlan (битый снимок).
- `control_mode_switched_to_manual` — task отменена переключением `control_mode='manual'`.

Commands:
- `command_send_failed`, `command_timeout`, `ae3_command_poll_deadline_exceeded`.
- `ae3_missing_ae_command`, `ae3_legacy_command_not_found` — рассинхрон `ae_commands`/`commands`.
- Command idempotency (PR5): `ae_commands.planner_step` стабилизирует `cmd_id` при retry;
  `publish_status=published_unconfirmed` — re-drive после crash между HL publish и `external_id` link;
  env: `AE_COMMAND_POLL_DEFAULT_SEC` (default 120), `AE_COMMAND_POLL_MARGIN_SEC` (default 30, добавляется к `duration_ms/1000`).

IRR probe:
- `irr_state_unavailable`, `irr_state_stale`, `irr_state_mismatch`.
- `irrigation_recovery_probe_exhausted`, `irrigation_wait_ready_timeout`.

Two-tank stages:
- `prepare_recirculation_attempt_limit_reached`, `clean_fill_source_empty_stop`, `solution_fill_leak_detected`, `solution_fill_timeout_stop` и др. stage-terminal коды (см. каталог).

Startup recovery: `startup_recovery_unconfirmed_command`, `startup_recovery_pending_resume_failed`, …

Stale task janitor (PR3):
- `ae3_stale_task_reclaimed` — task в `claimed`/`running` старше TTL с `ae_commands` → terminal fail.
- Env: `AE_STALE_CLAIMED_TTL_SEC` (default 120), `AE_STALE_RUNNING_TTL_SEC` (default `AE_MAX_TASK_EXECUTION_SEC + 60`),
  `AE_STALE_TASK_RECONCILE_SEC` (default 60, интервал janitor-тика в worker reconcile loop).

Flow-path guard (PR7):
- `ae3_flow_stop_unconfirmed` — stop/probe flow-path не подтвердил OFF.
- `ae3_manual_hold_deadline_exceeded`, `ae3_manual_hold_return_stage_missing` — stage `manual_hold`.
- Runtime flag `semi_allows_active_flow` (default false): при `semi` не останавливать активный fill без явного включения.
- `pending_manual_step` в `manual_hold`: `__mh_return:{stage}` или `__mh_step:{stage}:{operator_step}`; API возвращает plain step оператору.

Deprecated (не используются в runtime, оставлены только в backlog/catalog для compat):
- `ae3_task_create_conflict` → заменён на `start_cycle_zone_busy` / `start_cycle_idempotency_key_conflict`.
- `ae3_lease_claim_failed` → провал lease не raise'ит code, делает silent rollback claim (`release_claim`); при потере уже захваченной lease — `ae3_zone_lease_lost`.
- `ae3_requeue_failed` → заменён на `ae3_transition_apply_failed` / `ae3_poll_apply_failed` / `ae3_correction_apply_failed`.
- `cycle_start_blocked_nodes_unavailable` → заменён на `ae3_snapshot_required_node_type_missing` / `ae3_snapshot_no_online_actuator_channels` / `ae3_snapshot_required_node_persistently_offline`.

## 9. Reliability / observability (R4)

- **Lease heartbeat fail-closed:** `Ae3RuntimeWorker._lease_heartbeat` продлевает lease с transient DB retry (`AE_LEASE_HEARTBEAT_TRANSIENT_RETRIES`); после `AE_LEASE_HEARTBEAT_MAX_FAILURES` подряд неудач — `lease_lost_event` + infra alert `ae3_zone_lease_lost`, метрики `ae3_lease_heartbeat_failed_total`, `ae3_zone_lease_lost_total`.
- **Intent sync retry:** `_safe_mark_intent_running` / `_safe_mark_intent_terminal*` retry до `AE_INTENT_SYNC_MAX_RETRIES`; при исчерпании — `ae3_intent_sync_failed_total{operation=...}`.
- **HL publish:** default `AE_HL_MAX_RETRIES=1` (один retry на 503/transport).
- **Command protocol:** legacy status `ACCEPTED` — fail-closed `command_protocol_violation` (не non-terminal poll).
- **Fail-safe shutdown:** non-success batch → biz alert `biz_flow_stop_failed_hardware_may_be_active`.
- **Метрики:** `ae3_oldest_active_task_age_seconds{status}`, `ae3_command_dispatch_duration_seconds` (HL publish wall time), `ae3_reconcile_consecutive_errors`.
- **Stale janitor:** `StaleTaskReconcileResult.kick_needed` при `requeued > 0`.

## 8. Обязательные проверки перед merge

1. Запускать тесты только в Docker:
   `docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q`
2. Laravel AE3 тесты:
   `docker compose exec -e APP_ENV=testing -e DB_DATABASE=hydro_test laravel php artisan test --filter="Ae3Lite"`
3. При изменении миграций: `php artisan migrate` + rollback.
4. При изменении API/контрактов: обновить `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`.
5. `make test-ae PYTEST_ARGS="..."` из корня репозитория: пути задаются **относительно WORKDIR контейнера** (`/app` = `backend/services/automation-engine`). Пример: `test_greenhouse_climate_tick_integration.py`. Путь вида `backend/services/automation-engine/...` в контейнере **не существует** — pytest завершится с «file or directory not found».

## 10. Обновление документации при изменениях

1. DB schema → `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
2. API/контракты → `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
3. Runtime flows → `doc_ai/ARCHITECTURE_FLOWS.md`
4. Canonical spec → `doc_ai/04_BACKEND_CORE/ae3lite.md`
