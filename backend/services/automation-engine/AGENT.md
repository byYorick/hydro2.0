# AGENT.md (automation-engine / AE3-Lite v1)

Краткие инструкции для ИИ-ассистента при работе в `backend/services/automation-engine`.
Обновлено: 2026-03-07
Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Главная цель

Поддерживать и развивать **AE3-Lite v1** — DB-backed executor для `cycle_start`.
Canonical spec: `doc_ai/04_BACKEND_CORE/ae3lite.md`.

Прежний monolithic automation runtime удалён. Рабочий пакет автоматики — `ae3lite/`.

## 2. Жёсткие ограничения (инварианты из spec §2)

1. Никакого прямого MQTT из AE или Laravel.
2. Все команды к узлам идут только через `history-logger` (`POST /commands`).
3. Одна активная execution task на зону — гарантируется partial unique index и ZoneLease.
4. Успешный terminal outcome mutating-команды только `DONE`; все остальные — fail.
5. Изменения схемы БД только через Laravel миграции (не ручной DDL).
6. `ae3lite/*` не импортирует legacy runtime пакеты.
7. Переключение `zones.automation_runtime` на `ae3` запрещено при активной task или lease.
8. Runtime читает zone state напрямую из PostgreSQL read-model, без HTTP к Laravel.
9. Единственный internal status endpoint: `GET /internal/tasks/{task_id}`.
10. Единственный внешний ingress: `POST /zones/{id}/start-cycle`.
11. Hardcoded default targets запрещены (spec §5.3.4); отсутствие target → `PlannerConfigurationError`.
12. CAS-промах в `zone_workflow_state.upsert_phase` → `Ae3LiteError` (не silent None).

## 3. Структура кода

```
ae3lite/
  api/              # HTTP endpoints (compat + internal), security, rate_limit
  domain/
    entities/       # AutomationTask, ZoneWorkflow, ZoneLease, PlannedCommand
    errors.py       # Все domain-ошибки
    services/       # CycleStartPlanner, two_tank_runtime_spec
  application/
    use_cases/      # create_task, claim_next, execute_task, finalize_task,
                    # reconcile_command, startup_recovery, two_tank_executor
    adapters/       # intent mapping adapter (фактическое имя модуля см. в каталоге)
  infrastructure/
    repositories/   # PgAutomationTaskRepository, PgZoneWorkflowRepository,
                    # PgZoneLease, PgAeCommandRepository
    gateways/       # SequentialCommandGateway
    clients/        # HistoryLoggerClient
    read_models/    # ZoneSnapshotReadModel, TaskStatusReadModel, ZoneRuntimeMonitor
  runtime/
    worker.py       # Ae3RuntimeWorker (drain loop)
    bootstrap.py    # build_ae3_runtime_bundle()
    config.py       # Ae3RuntimeConfig.from_env()
    app.py          # create_app() / serve()
main.py             # точка входа → ae3lite.main
```

Все `common/` и `utils/` — только вспомогательные; основная логика в `ae3lite/`.

## 4. Task FSM

```
pending → claimed → running → waiting_command → completed
                                               → failed
                  → failed (любой exception)
```

Реквью (two-tank): `running → pending` через `requeue_pending`.
`mark_running`: WHERE `status IN ('claimed', 'running')` (не `waiting_command`).
`resume_after_waiting_command`: отдельный метод для `waiting_command → running`.

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

- `ae3_task_create_conflict` — idempotency race (другой worker создал task)
- `ae3_lease_claim_failed` — ZoneLease занята другим owner
- `ae3_complete_transition_failed` — task не смог перейти в completed
- `ae3_requeue_failed` — two-tank stage не смог создать следующий pending
- `cycle_start_blocked_nodes_unavailable` — нет online-узлов обязательных типов
- `irr_state_unavailable` — снимок IRR state недоступен
- `two_tank_prepare_targets_unavailable` — нет PH/EC телеметрии для prepare check

## 8. Обязательные проверки перед merge

1. Запускать тесты только в Docker:
   `docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q`
2. Laravel AE3 тесты:
   `docker compose exec -e APP_ENV=testing -e DB_DATABASE=hydro_test laravel php artisan test --filter="Ae3Lite"`
3. При изменении миграций: `php artisan migrate` + rollback.
4. При изменении API/контрактов: обновить `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`.

## 9. Обновление документации при изменениях

1. DB schema → `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`
2. API/контракты → `doc_ai/04_BACKEND_CORE/REST_API_REFERENCE.md`
3. Runtime flows → `doc_ai/ARCHITECTURE_FLOWS.md`
4. Canonical spec → `doc_ai/04_BACKEND_CORE/ae3lite.md`
