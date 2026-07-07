# AE3-Lite: план рефакторинга для ИИ-агентов

**Дата:** 2026-07-02
**Версия:** 1.1
**Статус:** В работе — PR1–PR7 реализованы в ветке; PR8–PR9 частично; сквозной `make test-ae` и E2E smoke — в процессе стабилизации.

### Прогресс по PR (2026-07-06)

| PR | Статус | Примечание |
|----|--------|------------|
| PR1 | ✅ Готово | DSN, pool timeout, supervisor stopwaitsecs, `/health/ready` (dev; dev.win — в этой ветке) |
| PR2 | ✅ Готово | drain supervisor, per-task isolation, honest health |
| PR3 | ✅ Готово | stale task reconcile, janitor |
| PR4 | ✅ Готово | log context, observability |
| PR5 | ✅ Готово | command idempotency, publish pipeline |
| PR6 | ✅ Готово | startup recovery multi-instance |
| PR7 | ✅ Готово | FlowPathGuard, manual_hold, P0–P2 доработки |
| PR8 | 🟡 Частично | MetricWindowValidator и часть correction — в ветке; полный scope — проверить |
| PR9 | 🟡 Частично | auth на read-routes, rate limit, error path; `Path(gt=0)` на read-routes — в ветке |
**Основание:** `doc_ai/04_BACKEND_CORE/AE3_RELIABILITY_AUDIT_AND_REMEDIATION_PLAN.md` (полный аудит с находками и severity)

---

## 1. Назначение документа

Это пошаговый план рефакторинга AE3-Lite, оформленный как последовательность самостоятельных
задач (PR1–PR9) для ИИ-агента. Каждая задача содержит: контекст, цель, точный список файлов,
инструкции по реализации, ограничения и критерии приёмки. Задачи спроектированы так, чтобы
каждая была независимо тестируемой и мерджилась отдельным PR.

Ссылки на находки аудита даются в формате `R1`, `I3`, `D2`, `A5`, `O7` — расшифровка в
`AE3_RELIABILITY_AUDIT_AND_REMEDIATION_PLAN.md` §3–4.

## 2. Обязательный контекст перед любой задачей

Прочитать перед началом работы:

1. `backend/services/automation-engine/AGENT.md` — канонический контракт AE3-Lite (FSM, error codes, команды тестов).
2. `backend/services/AGENTS.md` — границы ответственности сервисов.
3. `doc_ai/04_BACKEND_CORE/ae3lite.md` — архитектура runtime.
4. `doc_ai/04_BACKEND_CORE/AE3_RELIABILITY_AUDIT_AND_REMEDIATION_PLAN.md` — находки аудита.
5. Для PR5: `doc_ai/04_BACKEND_CORE/HISTORY_LOGGER_API.md`, `doc_ai/05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`.
6. Для PR7: `doc_ai/04_BACKEND_CORE/AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`.
7. Для PR8: `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`.

### 2.1 Глобальные ограничения (действуют для всех задач)

- **Запрещено** публиковать команды в MQTT в обход history-logger.
- **Запрещено** менять форматы MQTT-топиков/payload и существующие статусы команд
  (`ACK/DONE/ERROR/INVALID/BUSY/NO_EFFECT/TIMEOUT`).
- Изменения схемы БД — **только** через Laravel-миграции (`backend/laravel/database/migrations/`),
  с предварительным описанием в `DATA_MODEL_REFERENCE.md`.
- Task FSM (`pending → claimed → running → waiting_command → completed/failed`, requeue через
  `requeue_pending`) не расширять новыми статусами без обновления `ae3lite.md`.
- `ae3lite/*` не импортирует legacy-модули корня `automation-engine/` (кроме `common/`).
- Успешный terminal outcome mutating-команды — только `DONE`.
- Новые error codes добавлять одновременно в `backend/error_codes.json` и
  `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md`.
- Существующие тесты не удалять и не ослаблять; при изменении поведения — обновлять тест
  вместе с контрактной документацией.
- Общение, комментарии коммитов — на русском; формат коммита `<тип>: <описание>`.

### 2.2 Команды тестирования

```bash
# Полный AE suite (пишет в hydro_test, безопасно)
make test-ae

# Один файл / фильтр
make test-ae PYTEST_ARGS="-q test_ae3lite_worker_shutdown.py"
make test-ae PYTEST_ARGS="-x -k test_name"

# Unit без БД (быстрый прогон)
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q <file>

# Сброс тестовой БД
make test-db-reset
```

Перед сдачей каждого PR: `make test-ae` полностью зелёный.

---

## PR1 — Hotfix конфигурации и пула БД

**Приоритет:** немедленно. **Риск:** низкий. **Зависимости:** нет.
**Закрывает:** I1, I2 (частично), R4, R6.

### Контекст

Четыре независимых дефекта конфигурации/инфраструктуры, воспроизводимо ломающих надёжность:
listeners не стартуют в dev, SIGKILL раньше graceful shutdown, неразличимые owner реплик,
бесконечное ожидание соединения из пула.

### Инструкции

1. **`backend/docker-compose.dev.yml`**, сервис `automation-engine` (блок ~строки 310–362):
   добавить в `environment`:
   ```yaml
   - AE_DB_DSN=postgresql://hydro:hydro@db:5432/hydro_dev
   - AE_WORKER_OWNER=ae3-${HOSTNAME:-dev}
   - PG_POOL_MAX_SIZE=10
   ```
   Проверить аналогичные блоки в `docker-compose.dev.win.yml`, `docker-compose.ci.yml`,
   `docker-compose.prod.yml` — добавить туда же (для prod — через `${...}` без хардкода пароля).
2. **`backend/services/automation-engine/supervisor.conf`**: `stopwaitsecs=10` → `stopwaitsecs=45`
   (правило: `stopwaitsecs >= AE_SHUTDOWN_GRACE_SEC + 10`, grace default 30 в
   `ae3lite/runtime/env.py:93`).
3. **`backend/services/common/db.py`**: в местах `pool.acquire()` (строки ~164, ~191) добавить
   `timeout` из настройки `pg_pool_acquire_timeout_sec` (default 5.0, env `PG_POOL_ACQUIRE_TIMEOUT_SEC`
   в `common/env.py`). При `TimeoutError` — логировать ERROR с именем операции и пробрасывать
   исключение (fail-closed). Не менять поведение для `PYTEST_CURRENT_TEST`.
4. **`ae3lite/runtime/env.py`**, метод `Ae3RuntimeConfig.validate()` (строки 96–125): добавить
   fail-fast проверку `if not self.db_dsn: raise ValueError("AE_DB_DSN / DATABASE_URL не задан ...")`.
   Обновить `test_ae3lite_config_validate.py` (позитивный/негативный кейс).

### Критерии приёмки

- `make up` → в логах automation-engine видны строки старта `IntentStatusListener` и
  `ZoneEventListener`; `GET localhost:9405/health/ready` = 200.
- `docker compose ... stop automation-engine` завершается без SIGKILL (в логах есть shutdown-путь
  `requeue_unpublished_execution` / нет `exit code 137`... допускается проверка по времени остановки < 45 с).
- `make test-ae` зелёный; новые тесты на `validate()` проходят.

---

## PR2 — WorkerSupervisor: живучесть drain loop

**Приоритет:** critical. **Риск:** средний. **Зависимости:** PR1.
**Закрывает:** R1, R2, R8 (частично), R9, O10.

### Контекст

`ae3lite/runtime/worker.py:_drain_pending_tasks()` (строки 221–302) — одноразовая корутина.
Два дефекта: (а) необработанное исключение убивает её навсегда, respawn только по внешнему
`kick()`; (б) `await done_task` на строке 255 пробрасывает исключение из
`_execute_claimed_task`, т.е. падение одной задачи роняет обработку всех зон. `drain_health()`
(строки 823–838) после crash может возвращать ok.

### Инструкции

1. **Супервизор.** В `Ae3RuntimeWorker` добавить `_drain_supervisor()`:
   бесконечный цикл (пока не `_shutting_down`): `await self._drain_pending_tasks()`;
   штатный return → выход из супервизора; `Exception` → инкремент новой метрики
   `ae3_drain_crashes_total`, `logger.exception`, sleep с экспоненциальным backoff
   (1с → ×2 → cap 60с, сброс backoff после успешной итерации), повтор.
   `CancelledError` пробрасывать. Все места, которые сейчас спавнят
   `_drain_pending_tasks` (метод `_spawn_drain_task`, строки 608–619), переводить на спавн
   супервизора. Имя фоновой задачи оставить `ae3lite_runtime_worker` (на него завязан health).
2. **Изоляция per-task.** Ввести `_execute_claimed_task_safe(task)`: try/except вокруг
   `_execute_claimed_task`; при `Exception`: метрика `ae3_task_execution_crashed_total{error}`,
   ERROR-лог с `task_id`, `zone_id`, попытка перевести задачу в terminal fail
   (использовать существующий fail-closed путь `execute_task` / `fail_for_recovery` из
   репозитория с error code `ae3_task_execution_crashed` — добавить код в каталог),
   release lease. Исключение НЕ пробрасывать. В drain (строки 236, 279) спавнить `_safe`-вариант;
   `await done_task` больше не может raise (кроме CancelledError — обработать).
3. **`TaskClaimRollbackError`** (`application/use_cases/claim_next_task.py:66-76`): в drain
   перехватывать отдельно — WARNING-лог + метрика `ae3_claim_rollback_failed_total`, `continue`
   (осиротевший `claimed` подберёт PR3-janitor; до PR3 — startup recovery).
4. **CAS-miss `mark_running`** (`application/use_cases/execute_task.py:103-105`): вместо raise
   `TaskExecutionError` — терминальный fail только этой задачи (лог WARNING + метрика), задача
   не должна ронять loop.
5. **Честный health.** `drain_health()`: если drain-задача мертва И в БД есть pending задачи
   (быстрый `SELECT count(*) ... WHERE status='pending' AND scheduled_at <= now()` через
   существующий репозиторий, кэш 5 с) → `(False, "drain_dead_with_pending")`. В
   `docker-compose.dev.yml` healthcheck перевести с `/health/live` на `/health/ready`
   (start_period оставить 60s).
6. **Backoff reconcile loop** (`worker.py:167-177`): счётчик consecutive errors; после 3 подряд —
   sleep `min(2^n, 30)` вместо фиксированного интервала; сброс при успехе.
7. Все новые ERROR/WARNING-логи — с `task_id`, `zone_id`, `owner`.

### Новые тесты (`test_ae3lite_drain_supervisor.py`)

- Drain бросает исключение → супервизор перезапускает, backoff растёт, метрика инкрементится.
- Одна задача бросает исключение в execution → задача terminal fail, drain продолжает
  обрабатывать следующую задачу.
- `TaskClaimRollbackError` → drain жив, метрика.
- Drain мёртв + pending в БД → `drain_health()` = False; drain idle без pending → True.
- Существующие `test_ae3lite_worker_shutdown.py`, `test_ae3lite_claim_next_task*.py` — зелёные без правок семантики.

### Ограничения

- Не менять сигнатуры `kick()` / `shutdown()` — на них завязаны app.py и тесты.
- Не менять FSM-статусы.
- Graceful shutdown (`_finalize_inflight_on_shutdown`) должен работать и при активном супервизоре:
  shutdown отменяет супервизор ПОСЛЕ штатного завершения drain.

---

## PR3 — TaskJanitor: периодический healing застрявших задач

**Приоритет:** critical. **Риск:** средний. **Зависимости:** PR2.
**Закрывает:** R3, R7, I8 (частично).

### Контекст

`release_expired()` (lease) и восстановление `claimed`/`running` выполняются только в
`StartupRecoveryUseCase` (при старте процесса, под advisory lock `ae3_startup_recovery`).
Фоновый `WaitingCommandReconcileUseCase` покрывает только `waiting_command`. Задача,
осиротевшая в `claimed`/`running` при живом процессе, блокирует зону неограниченно
(partial unique index `ae_tasks_active_zone_unique`).

### Инструкции

1. Создать `ae3lite/application/use_cases/stale_task_reconcile.py` —
   `StaleTaskReconcileUseCase.run(now)`:
   - Шаг 1: `zone_lease_repository.release_expired(now)` — всегда, без advisory lock.
   - Шаг 2: выборка stale задач: `claimed` c `claimed_at < now - AE_STALE_CLAIMED_TTL_SEC`
     (default 120) и `running` с `updated_at < now - AE_STALE_RUNNING_TTL_SEC` (default
     `AE_MAX_TASK_EXECUTION_SEC + 60`). Выборка `FOR UPDATE SKIP LOCKED`, батч ≤ 16.
   - Шаг 3: для каждой: если lease зоны активен у ДРУГОГО живого owner — пропустить;
     если нет `ae_commands` в непубликованном состоянии — `requeue_pending`
     (переиспользовать `requeue_unpublished_execution`); иначе — terminal fail через
     `fail_for_recovery` с новым error code `ae3_stale_task_reclaimed`.
   - Каждое действие: zone_event `AE_TASK_RECLAIMED` (payload: `task_id`, `from_status`,
     `action`, `age_sec`) + метрика `ae3_stale_tasks_reclaimed_total{from_status,action}` +
     INFO-лог.
   - После requeue — `worker.kick()`.
2. Встроить вызов в существующий reconcile loop worker'а (там, где крутится
   `WaitingCommandReconcileUseCase`), с собственным интервалом `AE_STALE_TASK_RECONCILE_SEC`
   (default 60; выполнять не каждый тик 0.5 с, а по таймеру).
3. **Сузить advisory lock** в `StartupRecoveryUseCase` (`startup_recovery.py:61-76`):
   `release_expired()` вынести ДО захвата lock (выполняется каждой репликой); под lock оставить
   только scan/heal активных задач. Обновить комментарий о причинах.
4. Новые env-переменные задокументировать в `ae3lite/runtime/env.py` и `AGENT.md` (раздел env).
5. Error code `ae3_stale_task_reclaimed` → `error_codes.json` + `ERROR_CODE_CATALOG.md`.
   Event type `AE_TASK_RECLAIMED` → `AE3_RUNTIME_EVENT_CONTRACT.md`.

### Новые тесты (`test_ae3lite_stale_task_reconcile.py`, интеграционные — через `make test-ae`)

- `claimed` старше TTL без команд → requeue_pending, зона разблокирована, event/метрика есть.
- `running` старше TTL → fail_for_recovery с `ae3_stale_task_reclaimed`.
- Задача с активным чужим lease — не тронута.
- Свежая `claimed` (моложе TTL) — не тронута.
- Две конкурентные итерации janitor (эмуляция реплик) — нет double-requeue (SKIP LOCKED).

### Ограничения

- Не трогать семантику `WaitingCommandReconcileUseCase` (republish запрещён — сохранить).
- TTL выбирать консервативно: false-positive requeue живой задачи недопустим — поэтому
  для `running` TTL строго больше `AE_MAX_TASK_EXECUTION_SEC`.

---

## PR4 — Наблюдаемость: JSON-логи, log-context, метрики очереди, алерты

**Приоритет:** high. **Риск:** низкий. **Зависимости:** PR1 (желательно после PR2/PR3, чтобы включить их метрики).
**Закрывает:** O1–O6, O8, O9, O11, часть O2/O3.

### Инструкции

1. **JSON-логи** (`main.py` automation-engine): вызвать `common.logging_setup.setup_standard_logging()`
   по образцу history-logger (`backend/services/history-logger/main.py`). Убедиться, что
   `LOG_FORMAT=json` из compose работает.
2. **Log-context**: создать `ae3lite/infrastructure/log_context.py` — contextvars-хелпер
   `bind_log_context(task_id=None, zone_id=None, stage=None, correction_window_id=None, cmd_id=None, trace_id=None)`
   + logging.Filter, добавляющий поля в record (подключить в setup). Установка контекста:
   - HTTP middleware (`runtime/app.py:454-495`) — `trace_id`;
   - `_execute_claimed_task_safe` (PR2) — `task_id`, `zone_id`;
   - workflow router при входе в stage — `stage`;
   - correction handler — `correction_window_id`;
   - command gateway — `cmd_id`.
3. **Trace propagation**: при создании task из intent сохранять `trace_id` ingress-запроса в
   metadata intent/task (столбец/поле metadata уже есть — использовать его, БЕЗ миграции);
   в worker при claim восстанавливать в log-context.
4. **INFO-логи FSM**: в `automation_task_repository.py` (или в use cases) — structured INFO при
   `claim`, `mark_running`, `mark_waiting_command`, terminal, `requeue`, и WARNING при CAS-miss
   (поля: `task_id`, `zone_id`, `from_status`, `to_status`, `owner`).
5. **Access-лог 4xx**: в HTTP middleware (`app.py:497-507`) логировать WARNING все ответы
   400–499 с `path`, `status`, `error` code из detail, `trace_id`, `zone_id` (если есть).
   Успешный dispatch ingress (`compat_endpoints.py`) — INFO с `zone_id`, `task_id`, `idempotency_key`.
6. **Метрики** (`ae3lite/infrastructure/metrics.py`):
   - `ae3_pending_tasks` (Gauge), `ae3_oldest_pending_task_age_seconds` (Gauge) — обновлять в
     janitor-тике (PR3) одним SQL;
   - `ae3_task_duration_seconds` (Histogram, labels `topology`, `outcome`) — observe при terminal;
   - `ae3_listener_connected{listener}` (Gauge 0/1), `ae3_listener_reconnect_total{listener}` —
     в `zone_event_listener.py`, `intent_status_listener.py`;
   - `ae3_observability_write_failed_total{kind}` — инкремент во всех местах, где ошибки записи
     zone_events/alerts проглатываются (`decision_gate.py:153`, `correction_event_logger.py:70`,
     `sequential_command_gateway.py:310,455` и аналогичных).
7. **Алерты** (`backend/configs/dev/prometheus/alerts.yml`, зеркально prod-конфиг если есть):
   - `AE3PendingTaskStuck`: `ae3_oldest_pending_task_age_seconds > 600` for 5m, severity critical;
   - `AE3WorkerSilent`: `ae3_pending_tasks > 0 and rate(ae3_tick_duration_seconds_count[5m]) == 0` for 5m, critical;
   - `AE3ListenerDown`: `ae3_listener_connected == 0` for 5m, warning;
   - `AE3DrainCrashLoop`: `increase(ae3_drain_crashes_total[15m]) > 3`, critical;
   - заменить `AE3StuckTask` (active>0 15m) на age-based вариант.
   Панели в `backend/configs/dev/grafana/dashboards/automation-engine.json` для новых метрик.
8. **Удаление legacy**: удалить `alerts_manager.py`, `health_monitor.py`, `error_handler.py` из
   корня automation-engine вместе с их тестами (предварительно `rg`-проверка, что не импортируются
   нигде кроме своих тестов); удалить `PROMETHEUS_PORT` из `config/settings.py`.

### Критерии приёмки

- Логи AE в dev — JSON, содержат `task_id`/`zone_id`/`trace_id` в записях из worker/handlers.
- Один цикл коррекции трассируется по `correction_window_id` в логах end-to-end.
- `promtool check rules` на изменённый alerts.yml проходит (или docker-прогон prometheus без ошибок конфига).
- `make test-ae` зелёный; `rg "alerts_manager|health_monitor|error_handler" backend/services/automation-engine --glob '!*test*'` пусто.

---

## PR5 — Идемпотентность команд и re-drive publish pipeline

**Приоритет:** critical (безопасность дозирования). **Риск:** высокий. **Зависимости:** PR3, PR4.
**Закрывает:** I3, I4, I5, D9, T6.

### Контекст

`sequential_command_gateway.py`: (а) `cmd_id = ae3-t{task}-z{zone}-s{step_no}` с монотонным
`step_no` — retry после `command_send_failed` создаёт НОВЫЙ cmd_id, идемпотентность HL по cmd_id
не защищает от повторной дозы (строки 136–207); (б) pipeline
`INSERT ae_commands → HL publish → resolve_legacy → mark_publish_accepted → mark_waiting_command`
не атомарен — crash между шагами даёт команду in flight при task в `running` или ложный fail;
(в) poll terminal status (строки 339–391) не имеет deadline при `stage_deadline_at is None`.

**ВАЖНО:** это изменение затрагивает защищённый пайплайн команд. Сначала обновить спецификации,
затем код. В PR обязательна строка:
`Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0`.

### Инструкции

1. **Документация первой**: в `DATA_MODEL_REFERENCE.md` описать новые поля `ae_commands`;
   в `HISTORY_LOGGER_API.md` — семантику повторной публикации с тем же `cmd_id`
   (HL уже идемпотентен по cmd_id — `history-logger/commands/lifecycle.py:90-138`, зафиксировать
   это как контракт).
2. **Laravel-миграция**: добавить в `ae_commands` колонки
   `planner_step VARCHAR(160) NULL` (детерминированный ключ шага планировщика:
   `{stage}:{seq_index}` или `{stage}:{corr_step}:{component}`) и
   `publish_state VARCHAR(32) NOT NULL DEFAULT 'pending'`
   (`pending|published_unconfirmed|accepted|failed`). Частичный индекс
   `(task_id, planner_step) WHERE publish_state IN ('pending','published_unconfirmed')`.
3. **Стабильный `cmd_id`**: в `ae_command_repository.allocate_and_create_pending` — сначала
   `SELECT ... FOR UPDATE` существующей строки по `(task_id, planner_step)` в непубликованном
   состоянии; если есть — вернуть её `(id, step_no)` (cmd_id восстанавливается тем же шаблоном);
   иначе — текущая аллокация нового step_no. Gateway передаёт `planner_step`, собранный из
   контекста `PlannedCommand` (stage + индекс команды в плане; для correction — corr_step).
4. **Re-drive вместо ложного fail**: в gateway после успешного `publish` (строка 199) немедленно
   ставить `publish_state='published_unconfirmed'`; при ошибке на `resolve_legacy_command_id` /
   `mark_publish_accepted` — НЕ бросать `CommandPublishError`, а оставить
   `published_unconfirmed` и вернуть управление в poll-ветку: reconcile/janitor довязывает
   `external_id` по `cmd_id` (retry `resolve_legacy_command_id` 3×50мс уже в первом проходе).
   `fail` команды — только если HL вернул ошибку публикации ИЛИ по deadline.
5. **Deadline poll всегда**: в `_await_terminal_status` — `effective_deadline = min(
   stage_deadline_at or +inf, now + poll_timeout)`, где `poll_timeout =
   (params.duration_ms/1000 + AE_COMMAND_POLL_MARGIN_SEC)` для команд с длительностью, иначе
   `AE_COMMAND_POLL_DEFAULT_SEC` (env, default 120). По deadline — существующий путь
   `ae3_command_poll_deadline_exceeded`.
6. **Устранить дублирование**: `use_cases/publish_planned_command.py` перевести на общий helper
   с gateway (одна реализация publish-пайплайна).
7. **Climate vents** (`greenhouse_climate/run_tick.py:881`): `cmd_id = f"ghc-{greenhouse_id}-{idempotency_key}-{side}-{target}"`
   вместо `uuid4()`.
8. Метрики: `ae3_command_publish_redriven_total`, `ae3_command_cmd_id_reused_total`.

### Новые тесты

- Retry после `command_send_failed` → тот же `cmd_id`, в `commands` HL нет второй записи
  (интеграционный, `make test-ae`).
- Эмуляция crash между publish и accept (мок падает на `mark_publish_accepted`) → задача не
  fail, reconcile довязывает external_id, команда доходит до terminal.
- Poll без stage_deadline → завершение fail-closed за `AE_COMMAND_POLL_DEFAULT_SEC`.
- Существующие `test_ae3lite_ae_command_step_allocation.py` и command-тесты — зелёные
  (при изменении семантики — обновить вместе с AGENT.md).

### Ограничения

- Двухфазная совместимость: код обязан работать и со строками `ae_commands` без `planner_step`
  (NULL → старое поведение аллокации), чтобы не ломать задачи, находящиеся in flight при деплое.
- Не менять форматы payload команд к узлам.

---

## PR6 — HL-клиент: retry-конфиг, circuit breaker, таймауты

**Приоритет:** high. **Риск:** низкий. **Зависимости:** нет (можно параллельно с PR2–PR5).
**Закрывает:** I7, I9, I10, F2, M2.

### Инструкции

1. `ae3lite/infrastructure/clients/history_logger_client.py`:
   - параметры `max_retries` / `retry_backoff_sec` из env `AE_HL_MAX_RETRIES` (default 2),
     `AE_HL_RETRY_BACKOFF_SEC` (default 0.5); backoff экспоненциальный с jitter ±25%;
   - retry по-прежнему только на 5xx/transport (4xx — fail сразу);
   - встроенный circuit breaker без внешних зависимостей: после
     `AE_HL_BREAKER_FAIL_THRESHOLD` (default 5) подряд ошибок — open на
     `AE_HL_BREAKER_OPEN_SEC` (default 15); в open — немедленный
     `CommandPublishError("hl_circuit_open")`; half-open — одна пробная попытка;
   - метрики: `ae3_hl_request_duration_seconds` (Histogram, label `path`),
     `ae3_hl_request_errors_total{kind=timeout|5xx|4xx|transport}`,
     `ae3_hl_breaker_state` (Gauge 0=closed/1=open/2=half-open).
2. `ae3lite/runtime/bootstrap.py:76`: `httpx.AsyncClient(timeout=httpx.Timeout(connect=2.0,
   read=8.0, write=5.0, pool=2.0))`; значения через env `AE_HTTP_CLIENT_*_TIMEOUT_SEC`
   (сохранить обратную совместимость с `AE_HTTP_CLIENT_TIMEOUT_SEC` как общим дефолтом).
3. `runtime/app.py` `/health/ready`: добавить проверку HL — `GET {history_logger_url}/health`
   с таймаутом 2 с и кэшем результата 10 с; при недоступности HL → `503 degraded`
   с reason `history_logger_unreachable` (listeners/DB-проверки не менять).
4. Env-переменные задокументировать в `env.py` и `AGENT.md`.

### Тесты

- Юнит на breaker: threshold → open → fast-fail → half-open → закрытие.
- Ретраи с jitter (мок transport error).
- ready=503 при недоступном HL (мок).

---

## PR7 — FlowPathGuard: fail-safe при manual mode и провале stop

**Приоритет:** critical (fail-open железа). **Риск:** высокий. **Зависимости:** PR2, PR5 (желательно).
**Закрывает:** D1, D2, D10, часть O7.

### Контекст

(а) Переключение `control_mode=manual/semi` во время активного flow-path stage
(`clean_fill.py:84`, `solution_fill.py:119`, `prepare_recirc.py:119`, `irrigation_check.py:173`,
`irrigation_recovery.py:50`, `startup.py:80`) возвращает бесконечный `poll` — AE перестаёт
оркестрировать, насос/клапаны остаются в состоянии прошлого stage.
(б) `prepare_recirc_window.py:54-74` глотает `TaskExecutionError` от stop-команд при исчерпании
retry — task fail, железо может остаться ON, ни события, ни алерта.

**ВАЖНО:** сначала обновить `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md` — добавить раздел
«Manual mode на активном flow-path» и «Гарантии stop-команд», затем код.

### Инструкции

1. Создать `ae3lite/application/handlers/flow_path_guard.py` — функция/класс
   `ensure_flow_stopped(ctx, reason) -> FlowStopOutcome`:
   - формирует stop-команды текущего stage (переиспользовать существующие stop-планы
     handlers: `prepare_recirculation_stop`, `sensor_mode_deactivate`, irrigation stop и т.д.);
   - отправляет через штатный command gateway (никакого прямого MQTT);
   - после terminal DONE — probe (`irr_state` snapshot / `_assert_flow_path_active` инверсия)
     для подтверждения OFF;
   - при провале (fail-статус команды, deadline, probe mismatch): zone_event
     `FLOW_STOP_FAILED_HARDWARE_MAY_BE_ACTIVE` (payload: `stage`, `commands`, `reason`,
     `task_id`) + biz-alert severity critical + метрика
     `ae3_flow_stop_failed_total{stage}` + возврат `FlowStopOutcome(confirmed=False)`.
     Исключение НЕ глотать молча — но и не терять контекст: терминальный fail задачи происходит
     ПОСЛЕ фиксации события/алерта.
2. **Manual/semi на flow-path**: в перечисленных handlers ветку
   `control_mode in (manual, semi)` на активном flow-стадии заменить с бесконечного `poll` на:
   `ensure_flow_stopped(reason="control_mode_manual")` → transition в stage `manual_hold`
   (poll с deadline = stage deadline; выход — возврат `control_mode=auto` или manual step).
   Zone_event `CONTROL_MODE_FLOW_STOPPED`. Если политика зоны допускает продолжение в semi —
   вынести решение в `correction_transition_policy` / RuntimePlan-флаг
   `semi_allows_active_flow` (default false, fail-closed).
3. **`prepare_recirc_window.py:54-74`**: заменить swallow на `ensure_flow_stopped`; при
   `confirmed=False` — terminal fail с error code `ae3_flow_stop_unconfirmed` (новый код).
4. **Recovery прерванной коррекции** (`startup_recovery.py:271-281`): после fail
   `startup_recovery_correction_interrupted` — probe состояния дозирующего актуатора; при
   активном состоянии — тот же `FLOW_STOP_FAILED...`-путь c алертом «проверьте оборудование».
5. Новые event types (`FLOW_STOP_FAILED_HARDWARE_MAY_BE_ACTIVE`, `CONTROL_MODE_FLOW_STOPPED`)
   → `AE3_RUNTIME_EVENT_CONTRACT.md`; error code `ae3_flow_stop_unconfirmed` → каталог.

### Тесты

- Manual во время solution_fill → отправлен stop, подтверждён OFF, stage=manual_hold, event есть.
- Stop-команда возвращает TIMEOUT → task fail, event `FLOW_STOP_FAILED...`, biz-alert создан.
- Возврат в auto из manual_hold → workflow продолжается со следующего stage.
- Существующие E2E-сценарии two-tank (`tests/e2e/scenarios/ae3lite/E102*, E103*`) — без регрессий
  (прогнать соответствующий e2e smoke).

### Ограничения

- Никаких прямых MQTT-публикаций — только через command gateway → history-logger.
- Семантика E-STOP (`correction.py:434`) не меняется в этом PR.
- `allowed_manual_steps` для UI должны отражать `manual_hold` (проверить
  `get_zone_control_state_use_case` и фронтенд-контракт; если меняется Inertia props —
  обновить фронтенд или явно зафиксировать отсутствие изменений).

---

## PR8 — Correction: единый валидатор окна и честная семантика дозы

**Приоритет:** high. **Риск:** средний. **Зависимости:** нет (лучше после PR4 для логов).
**Закрывает:** D3, D4, D5, D6, D7, D8, D11, часть O6.

### Инструкции

1. **`MetricWindowValidator`** — новый модуль `ae3lite/domain/services/metric_window_validator.py`:
   перенести логику sanity bounds (`base.py:1595-1600`: pH∈[0,14], EC∈[0,20]), staleness и
   стабильности в один переиспользуемый валидатор. Подключить в
   `application/services/decision_window_reader.py:79-129` (сейчас bounds там НЕТ — это баг D3)
   и в `base._read_target_metric_window` (заменить локальную реализацию). Выход за bounds →
   существующий reason `sensor_out_of_bounds` (не новый retry).
2. **Clamp дозы** (`correction_planner.py:1245-1268`): при срезании duration до `max_dose_ms`
   пересчитывать объём: `effective_ml = ml_per_sec * clamped_ms / 1000`; в команду и в
   `EC_DOSING`/`PH_CORRECTED` события класть `effective_ml` (+ сохранить `requested_ml` в
   payload события). PID/attempt-логика должна оперировать `effective_ml`.
3. **`last_dose_at` после DONE** (`correction_planner.py:991`, `correction.py:931`): убрать
   персист `last_dose_at=now` на этапе планирования; переместить в обработку terminal-статуса
   дозирующей команды в correction handler — писать только при `DONE`. Проверить взаимодействие
   с существующим guard `_strip_last_dose_at`.
4. **Fail-closed конфиг**: `correction_planner.py:223` — убрать fallback
   `_DEFAULT_SOLUTION_VOLUME_L=100`; отсутствие `solution_volume_l` → `PlannerConfigurationError`
   (по аналогии с pump_calibration). `correction_planner.py:694` — при `far_zone <= close_zone`
   → `PlannerConfigurationError` на этапе build плана.
5. **Cap на retry alert-block** (`correction.py:487`): добавить лимит
   `AE_CORRECTION_ALERT_BLOCK_MAX_RETRIES` (default 10); по исчерпании — terminal fail с
   существующим кодом `correction_blocked_by_no_effect_alert`.
6. **`multi_parallel`** (`correction.py:1218-1234`): в командах каждого компонента передавать и
   `ml`, и `duration_ms` из плана (согласованная пара после п.2).
7. **Логи** (`correction.py:739,817`, `correction_planner.py:1226-1258`): warning'и
   «telemetry stale/invalid», «dose discarded/clamped» — дополнить `task_id`,
   `correction_window_id`, `zone_id` (через log-context PR4 или параметрами).
8. Обновить `CORRECTION_CYCLE_SPEC.md` (семантика effective_ml, last_dose_at, fail-closed volume)
   и `EFFECTIVE_TARGETS_SPEC.md` при затрагивании targets.

### Тесты

- DecisionWindowReader: значение pH=-1/EC=999 → `sensor_out_of_bounds`, не retry
  (расширить `test_ae3lite_correction_planner.py` / handler-тесты).
- Clamp: dose 500мл при cap 300000мс → команда с effective_ml, событие содержит оба значения.
- Fail дозы → `last_dose_at` не записан, следующий цикл не блокируется фантомным cooldown.
- Отсутствие `solution_volume_l` → `PlannerConfigurationError`.
- `far_zone <= close_zone` → ошибка конфигурации.
- Alert-block: после N retry → terminal fail.

---

## PR9 — API: единый error-путь, auth на read-endpoints, guard runtime

**Приоритет:** high. **Риск:** средний. **Зависимости:** согласование с Laravel (единственный клиент).
**Закрывает:** A1–A7, A9.

### Инструкции

1. **Auth на read-endpoints** (`runtime/app.py:670-681`): `GET /zones/{id}/state` и
   `GET /zones/{id}/control-mode` — добавить `_validate_scheduler_security_baseline(request)`.
   **Одновременно** в Laravel: найти вызовы этих endpoint'ов
   (`rg "zones/.+/state|control-mode" backend/laravel/app`) и добавить Bearer-заголовок
   (токен уже используется для start-cycle — переиспользовать HTTP-клиент/конфиг).
   Прогнать Laravel feature-тесты затронутых экшенов.
2. **Rate limit**: отдельные limiter'ы для `/state` (например 60/10с per zone) и climate tick
   (per greenhouse_id); в `SlidingWindowRateLimiter` добавить cap количества ключей
   (LRU, например 10 000). Раздельные buckets для cycle/irrigation/lighting (взвешивание
   не требуется — просто три экземпляра limiter).
3. **Guard `automation_runtime='ae3'`**: в `api/validation.py:validate_scheduler_zone` заменить
   `SELECT id` на `SELECT id, automation_runtime`; при runtime != 'ae3' → 409 с кодом
   `start_cycle_unsupported_runtime` (согласовать имя с `ERROR_CODE_CATALOG.md`; для
   lighting уже есть `start_lighting_tick_unsupported_runtime` — переиспользовать паттерн).
4. **Единый error-путь**:
   - все `HTTPException(detail={...})` в `compat_endpoints.py` перевести на
     `api_error_detail()` из `http_errors.py`;
   - убрать `"message": str(exc)` из 503-ответов (строки 206–214, 439–447, 629–637) — в HTTP
     только code + safe-поля, полный текст — в лог с `trace_id`;
   - добавить `@app.exception_handler(Exception)` → 500
     `{status:"error", code:"ae3_internal_error", trace_id}` (лог + infra alert сохраняются);
   - добавить `@app.exception_handler(RequestValidationError)` → 422 с маппингом
     недостающих полей на catalog codes (минимум `start_cycle_missing_idempotency_key`);
   - `validation.py:35-36` — 404 через `api_error_detail("zone_not_found", ...)`.
5. **Каталог**: добавить в `error_codes.json` + `ERROR_CODE_CATALOG.md` используемые, но
   отсутствующие коды: `start_irrigation_intent_not_found`, `start_lighting_tick_intent_not_found`,
   `start_lighting_tick_zone_busy`, `unauthorized`, `missing_trace_id`,
   `scheduler_security_token_not_configured`, `task_not_found`,
   `start_cycle_solution_tank_guard_failed`, `ae3_internal_error`, `zone_not_found`.
6. **Мелочи**: `secrets.compare_digest` в `security.py:29`; `enforce=0` допустим только при
   `APP_ENV=local` (иначе `ValueError` в `validate()`); `Path(..., gt=0)` для `zone_id`;
   унифицировать `idempotency_key` max_length (160) в `greenhouse_climate_compat.py`.
7. Laravel-side: проверить `PresentsLocalizedApiErrors` на совместимость с новым форматом
   (формат `api_error_detail` уже используется internal endpoint'ом — регресс не ожидается,
   но прогнать соответствующие feature-тесты).

### Тесты

- `/state` без Bearer → 401 с кодом `unauthorized`; с Bearer → 200.
- Зона с `automation_runtime='legacy'` → 409 на start-cycle/irrigation, task НЕ создан.
- Необработанное исключение в route (мок) → 500 без internal текста, с trace_id.
- 422 без idempotency_key → catalog code.
- Rate limit `/state`: превышение → 429.
- Laravel feature-тесты затронутых экшенов зелёные
  (`docker compose ... exec laravel php artisan test --filter=...`).

### Ограничения

- Не менять `auth/roles` Laravel.
- Изменение ответов API → строка `Compatible-With` в PR.

---

## 3. Матрица покрытия находок аудита

| PR | Закрываемые находки |
|----|---------------------|
| PR1 | I1, I2, R4, R6, A6 (db_dsn) |
| PR2 | R1, R2, R8, R9, O10 |
| PR3 | R3, R7, I8 |
| PR4 | O1–O6, O8, O9, O11 |
| PR5 | I3, I4, I5, D9, T6 |
| PR6 | I7, I9, I10, F2 |
| PR7 | D1, D2, D10, O7 (часть) |
| PR8 | D3, D4, D5, D6, D7, D8, D11 |
| PR9 | A1–A5, A7, A9 |
| Backlog (вне плана) | R7-полный (leader election), Redis rate limiter, HL sweeper SENT→TIMEOUT (задача в history-logger), унификация climate timeout |

## 4. Сквозные критерии готовности всего рефакторинга

1. Chaos: kill -9 AE в каждом окне FSM → зона разблокируется ≤ `AE_STALE_*_TTL` без рестарта,
   ни одна команда не задублирована (проверка по `commands` HL: один ряд на cmd_id).
2. Offline-узел: команда завершается fail-closed за bounded time, насос не остаётся ON,
   есть zone_event и алерт.
3. Manual mode во время fill → железо остановлено и подтверждено, событие в timeline.
4. Метрики/алерты: застрявшая pending задача поднимает алерт ≤ 10 минут; смерть drain — ≤ 15 минут.
5. Полный `make test-ae` + e2e smoke `start-cycle → workflow` + Laravel feature-тесты — зелёные.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
