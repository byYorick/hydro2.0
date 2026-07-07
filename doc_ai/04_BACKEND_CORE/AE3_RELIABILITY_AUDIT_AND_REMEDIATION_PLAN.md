# AE3-Lite: аудит надёжности и план доработки

**Дата:** 2026-07-02
**Версия:** 1.0
**Статус:** План доработки (по результатам полного аудита кода)
**Область:** `backend/services/automation-engine/ae3lite/*`, supervisor/compose, метрики/алерты

---

## 1. Цель

Зафиксировать результаты глубокого аудита AE3-Lite (~33 000 строк, 123 модуля): места возможных
зависаний, отказов, fail-open рисков, race conditions, недочёты логирования и наблюдаемости —
и определить приоритезированный план доработки.

## 2. Сводка

| Severity | Кол-во | Ключевые темы |
|----------|--------|---------------|
| **Critical** | 8 | Мёртвый drain loop без respawn; нет periodic healing застрявших task; pool exhaustion → бесконечный `acquire()`; неатомарный publish pipeline; неаутентифицированный `/zones/{id}/state`; listeners не стартуют в dev (нет `AE_DB_DSN`); swallow stop-команд prepare_recirc; manual mode на активном flow-path |
| **High** | ~20 | Duplicate dose при retry (новый `cmd_id`); sanity bounds не применяются в correction decision window; clamp дозы без пересчёта ml; supervisor `stopwaitsecs` < shutdown grace; intent sync swallowed; NOTIFY gap без catch-up; утечка internal messages в 503; нет JSON-логов; trace_id не доходит до worker |
| **Medium** | ~40 | Phantom `last_dose_at`; retry без cap; TOCTOU claim/lease; hot-reload races; error catalog drift; пробелы access-логов |
| **Low** | ~17 | Мёртвый legacy-код; расхождения doc/code; мелкие валидации |

**Что уже сделано хорошо (не трогаем):** task FSM с CAS + `FOR UPDATE SKIP LOCKED`; lease heartbeat +
`AE_MAX_TASK_EXECUTION_SEC`; startup recovery с advisory lock и crash-window тестами; graceful shutdown
path; idempotency `cmd_id` на стороне history-logger; fail-closed config loader; ~50 Prometheus-метрик;
алерты на task failures/lease/SLO; `CorrectionEventLogger` с `correction_window_id`.

---

## 3. Находки: зависания и отказы

### 3.1 Runtime / worker loop

| # | Локация | Проблема | Sev |
|---|---------|----------|-----|
| R1 | `ae3lite/runtime/worker.py:295` + `runtime/app.py:125-150` | Необработанное исключение в `_drain_pending_tasks()` (например `TaskClaimRollbackError`, `TaskExecutionError` при CAS-miss `mark_running`) убивает drain loop навсегда. Callback только логирует crash, respawn происходит лишь при внешнем `kick()`. HTTP жив, `/health/live` = 200, supervisor не рестартует. Обработка всех зон останавливается. | **critical** |
| R2 | `worker.py:252-255`, `execute_task.py:103-105` | Исключение одной задачи роняет весь drain, а не одну задачу: задача остаётся в `claimed`, lease снимается → осиротевший `claimed`. | **critical** |
| R3 | `startup_recovery.py:78`, `waiting_command_reconcile.py` | `release_expired()` и scan `claimed/running` выполняются **только при старте процесса**. Фоновый reconcile покрывает только `waiting_command`. Задача, застрявшая в `claimed`/`running` при живом AE (drain умер, hard kill executора), блокирует зону часами — partial unique index не даст создать новую task. | **critical** |
| R4 | `supervisor.conf:18` vs `env.py:93` | `stopwaitsecs=10`, а `AE_SHUTDOWN_GRACE_SEC=30`: supervisor шлёт SIGKILL через 10 с — graceful shutdown (`requeue_unpublished_execution`, finalize inflight) не успевает. | **high** |
| R5 | `worker.py:554-591` | `_safe_mark_intent_running/terminal` глотают исключения → intent в Laravel остаётся `running` при terminal task; scheduler-dispatch рассинхронизирован. | **high** |
| R6 | `env.py:86` | `AE_WORKER_OWNER` default `ae3-runtime-worker` одинаков для всех реплик → при scale>1 неразличимые owner в lease/heartbeat/логах. | **high** |
| R7 | `advisory_locks.py:21-30` + `startup_recovery.py` | Второй экземпляр при недоступном advisory lock полностью пропускает recovery, включая `release_expired`. | **high** |
| R8 | `worker.py:167-177`, `493-552` | Reconcile loop и heartbeat при повторяющихся ошибках БД — warning + continue без backoff (tight loop 0.5 с) и без счётчика consecutive failures. | **medium** |
| R9 | `claim_next_task.py:52-83` | TOCTOU: task claim до zone lease; при провале rollback — `TaskClaimRollbackError` → см. R1. | **medium** |

### 3.2 Инфраструктура (PG / HTTP / LISTEN-NOTIFY)

| # | Локация | Проблема | Sev |
|---|---------|----------|-----|
| I1 | `common/db.py:104-125` | Пул PG `max_size=5` (default), `pool.acquire()` **без timeout**. 4 parallel tasks + reconcile + API + advisory lock ≈ исчерпание → корутины ждут бесконечно, worker и API зависают. | **critical** |
| I2 | `docker-compose.dev.yml` (automation-engine) | **Не задан `AE_DB_DSN`** → `runtime_config.db_dsn` пуст → LISTEN/NOTIFY listeners (`ae_zone_event`, `scheduler_intent_terminal`) не запускаются в dev; работает только polling. `env.py:96-125` не валидирует `db_dsn` — сервис стартует «полуживым». | **critical** |
| I3 | `sequential_command_gateway.py:136-281` | Publish pipeline не атомарен: `ae_commands` INSERT → HL publish → `mark_publish_accepted` → `mark_waiting_command` — 4 отдельных TX. Crash между шагами = команда in flight при task в `running` или ложный `command_send_failed`. | **critical** |
| I4 | `sequential_command_gateway.py:162-170, 198-207` | При retry после `command_send_failed` генерируется **новый `cmd_id`** (`ae3-t{task}-z{zone}-s{step_no}`, монотонный step_no). Если первая публикация дошла до MQTT — повторная доза / повторное включение насоса. Idempotency HL по `cmd_id` не спасает. | **high** |
| I5 | `sequential_command_gateway.py:339-391` + HL `command_status_queue.py:1265` | Poll terminal status без deadline, если `stage_deadline_at is None`; HL не переводит stale `SENT/ACK` в `TIMEOUT`. Offline-узел → до 15 мин (900 с task cap) «замороженной» зоны. | **high** |
| I6 | `zone_event_listener.py:80-103`, `intent_status_listener.py:99-127` | При разрыве соединения пропущенные NOTIFY не перечитываются (нет catch-up query); reconnect есть, но kick теряется. Dispatch callbacks без backpressure. | **high** |
| I7 | infrastructure слой | Нет circuit breaker на history-logger; retry HL — 1 повтор, фиксированный backoff 1 с, не конфигурируется env. | **high** |
| I8 | `advisory_locks.py` | Session advisory lock держит соединение пула на весь startup recovery scan. | **medium** |
| I9 | `runtime/app.py:729-755` | `/health/ready` не проверяет доступность history-logger; docker healthcheck использует только `/health/live`. | **medium** |
| I10 | `bootstrap.py:76` | `httpx.AsyncClient(timeout=10.0)` — единый timeout без разделения connect/read/write/pool. | **medium** |

### 3.3 Доменная логика / handlers (fail-open риски)

| # | Локация | Проблема | Sev |
|---|---------|----------|-----|
| D1 | `handlers/clean_fill.py:84`, `solution_fill.py:119`, `prepare_recirc.py:119`, `irrigation_check.py:173`, `startup.py:80` | Переключение `control_mode=manual/semi` во время активного flow-path stage → бесконечный `poll`: AE перестаёт оркестрировать, **насос/клапаны остаются в состоянии предыдущего stage** до task timeout (900 с) и далее. Главный fail-open. | **critical** |
| D2 | `handlers/prepare_recirc_window.py:54-74` | При исчерпании retry stop-команды (`prepare_recirculation_stop`, `sensor_mode_deactivate`) `TaskExecutionError` **проглатывается**: task fail, hardware может остаться ON. Нет zone_event о риске. | **critical** |
| D3 | `application/services/decision_window_reader.py:79-129` | Correction decision window не применяет `_sensor_value_in_bounds` (pH∈[0,14], EC∈[0,20]) в отличие от `base._read_target_metric_window`. Error codes датчика (-1, 999) проходят фильтр стабильности → неверные решения/бесконечные retry. | **high** |
| D4 | `domain/services/correction_planner.py:1245-1268` | Clamp дозы до `max_dose_ms` режет duration, но **не пересчитывает `dose_ml`** в команде: систематический under-dose, PID считает иначе. | **high** |
| D5 | `handlers/correction.py:1218-1234` | `multi_parallel` batch dose по ml без синхронизации с duration planner; в связке с I4 — риск дубликатов. | **high** |
| D6 | `correction_planner.py:991`, `correction.py:931` | `last_dose_at=now` персистится **до** подтверждения команды: при fail — фантомный cooldown блокирует следующий цикл. | **medium** |
| D7 | `correction.py:487` | `CORRECTION_SKIPPED_BY_ALERT_BLOCK` → retry каждые 60 с без верхнего предела попыток. | **medium** |
| D8 | `correction_planner.py:223` | Fallback `solution_volume_l=100` при отсутствии в конфиге — нарушение fail-closed политики (неверные process gains). | **medium** |
| D9 | `greenhouse_climate/run_tick.py:881-926` | Vent-команды: `cmd_id=uuid4()` (не идемпотентен при retry); частичный успех пары (одна сторона DONE, другая fail) не откатывается. | **medium** |
| D10 | `use_cases/startup_recovery.py:271-281` | Recovery при прерванной коррекции — fail-closed по FSM, но нет probe состояния актуатора / алерта «проверьте оборудование» — доза могла уйти. | **medium** |
| D11 | `correction_planner.py:694` | `far_zone <= close_zone` не валидируется при построении плана. | **medium** |

### 3.4 API / конфигурация

| # | Локация | Проблема | Sev |
|---|---------|----------|-----|
| A1 | `runtime/app.py:670-681` | `GET /zones/{id}/state` и `GET /zones/{id}/control-mode` — **без** security baseline (Bearer/trace) и без rate limit. Порт 9405 проброшен наружу в dev. Полное operational state читается перебором zone_id. | **critical** |
| A2 | `api/validation.py:10-36`, `compat_endpoints.py` | Ingress не проверяет `automation_runtime='ae3'` — проверка происходит поздно в planner, после создания task/intent (мусорные tasks, отложенный fail). | **high** |
| A3 | `compat_endpoints.py:206-214, 439-447, 629-637` | В 503-ответы включается `str(exc)` — утечка internal путей/SQL деталей клиенту. | **high** |
| A4 | `runtime/app.py` | Нет глобального exception handler (не-HTTPException → default 500 без structured body) и нет handler `RequestValidationError` (422 не мапится на catalog codes). | **high** |
| A5 | `api/rate_limit.py`, `greenhouse_climate_compat.py:48` | Rate limit не покрывает climate tick, `/state`, control-mode/manual-step; общий bucket на cycle/irrigation/lighting per zone. In-memory limiter без cap ключей. | **high** |
| A6 | `env.py:96-125` | `validate()` не проверяет `db_dsn` (см. I2); `enforce=0` полностью отключает security без привязки к `APP_ENV`. | **high** |
| A7 | `error_codes.json` | Используемые коды отсутствуют в каталоге: `start_irrigation_intent_not_found`, `unauthorized`, `missing_trace_id`, `task_not_found` и др. → generic «Системная ошибка» в UI. | **medium** |
| A8 | `handlers/base.py:191-343`, `config/modes.py` | Hot-reload конфига в LIVE mode: TOCTOU между чтением `config_revision` и rebuild; смена targets mid-correction; silent fallback на старый план при ошибке rebuild. | **medium** |
| A9 | `api/security.py:29` | Сравнение токена не constant-time (`!=` вместо `secrets.compare_digest`). | **low** |

---

## 4. Находки: логирование и наблюдаемость

| # | Локация | Проблема | Sev |
|---|---------|----------|-----|
| O1 | `main.py` / bootstrap | `common.logging_setup` (JsonFormatter) **не подключён** в AE — единственный из core-сервисов с plain-text логами; `LOG_FORMAT=json` в compose не действует. | **high** |
| O2 | метрики | Нет: `ae3_pending_tasks` (глубина очереди), `ae3_oldest_pending_task_age_seconds`, `ae3_task_duration_seconds` (wall-clock до terminal), метрик listeners (connected/reconnects), метрик HL HTTP (latency/errors), метрик PG pool (acquire wait/exhaustion). | **high** |
| O3 | алерты (`prometheus/alerts.yml`) | Нет: «pending task без claim > N мин», «worker не тикает при наличии работы», «listener disconnected», «fail_safe_transition», алертов на `waiting_command` stuck по возрасту. `AE3StuckTask` (active>0 15m) даёт false positives на длинных recirc. | **critical** (первые два) |
| O4 | `worker.py`, `automation_task_repository.py` | Claim/terminal/CAS-miss переходы FSM — только DEBUG или без логов вовсе; в prod невозможно проследить жизнь task по логам. | **medium** |
| O5 | worker/handlers | `trace_id` из HTTP kick не пробрасывается в background worker (contextvars теряются) — нет сквозной трассировки ingress → execution → command. | **high** |
| O6 | `correction.py:739, 817`, `correction_planner.py:1226-1258` | Warning'и «telemetry stale», «dose discarded/clamped» — без `task_id`/`correction_window_id`/zone context. | **medium** |
| O7 | `workflow_router.py:760-776` | Stage transitions two-tank пишутся только в `ae_stage_transitions`, не в `zone_events` — оператор не видит AE-переходы в timeline; при offline-узле UI «молчит» (нет синтетических событий при stage deadline). | **high** |
| O8 | `decision_gate.py:153`, `correction_event_logger.py:70`, `sequential_command_gateway.py:310, 455` | Ошибки записи zone_events/biz-alerts проглатываются без метрики — «дырявый» timeline незаметен. | **medium** |
| O9 | `runtime/app.py:497-507, 777` | `access_log=False`; 4xx (409 busy, 404, 422) не логируются системно; успешный dispatch — только DEBUG. | **medium** |
| O10 | `worker.py:823-838` | `drain_health()` возвращает ok по последнему exit reason; после crash без respawn при pending tasks в БД readiness может остаться зелёным. | **high** |
| O11 | legacy | `alerts_manager.py`, `health_monitor.py`, `error_handler.py`, `config/settings.py:PROMETHEUS_PORT=9401` — мёртвый код для ae3lite, путает операторов. | **low** |

---

## 5. План доработки

### Фаза 0 — Hotfix конфигурации (день)

Без изменений кода, только конфиги:

1. **`AE_DB_DSN` для automation-engine** в `backend/docker-compose.dev.yml` (I2) — включить listeners в dev; проверить prod/ci compose.
2. **`supervisor.conf`: `stopwaitsecs=45`** (≥ grace 30 + 10) (R4).
3. **`AE_WORKER_OWNER=${HOSTNAME}`** в compose/K8s (R6).
4. Поднять `PG_POOL_MAX_SIZE` для AE до `max_parallel_tasks + 4` (I1, частично).

Приёмка: listeners поднимаются (лог + `/health/ready`), graceful shutdown успевает при `docker stop`.

### Фаза 1 — Живучесть worker (неделя) — критично

1. **Auto-respawn drain loop** (R1): в done-callback `ae3lite_runtime_worker` при exception — respawn с exponential backoff + метрика `ae3_drain_crashes_total`.
2. **Изоляция ошибок per-task** (R2): обернуть `_execute_claimed_task` — fail_closed конкретной задачи, drain продолжает; CAS-miss `mark_running` = terminal fail задачи, не raise.
3. **Periodic stale-task reconcile** (R3): фоновый use case — `release_expired()` + перевод stale `claimed`/`running` (age > TTL) в `fail_for_recovery`/`requeue_unpublished_execution`; вынести `release_expired` из-под advisory lock (R7).
4. **`pool.acquire(timeout=5)`** + метрика exhaustion (I1).
5. **`db_dsn` в `Ae3RuntimeConfig.validate()`** — fail-fast (A6).
6. **`drain_health()` честный** (O10): при pending tasks в БД и мёртвом drain — ready=false; docker healthcheck → `/health/ready`.
7. Retry с backoff для `_safe_mark_intent_*` + метрика `ae3_intent_sync_failed_total` (R5).

Тесты: `make test-ae` — новые unit на respawn/isolation/stale-reconcile; существующие crash-window тесты не ломать.

### Фаза 2 — Безопасность дозирования и hardware fail-open (1-2 недели) — критично

1. **Manual/semi на активном flow-path** (D1): при переключении — немедленный stop-stage (подтверждённое OFF) либо запрет переключения при активном flow; событие `CONTROL_MODE_CHANGED_FLOW_STOPPED`.
2. **Stop-команды prepare_recirc не глотать** (D2): при провале stop — zone_event `PREPARE_RECIRC_STOP_FAILED_HARDWARE_MAY_BE_ACTIVE` + biz-alert + повторный stop через recovery.
3. **Идемпотентность команд** (I4, D9): стабильный `cmd_id` per (task, stage, corr_step, seq_index) при retry; deterministic cmd_id для climate vents.
4. **Sanity bounds в `DecisionWindowReader`** (D3): общий валидатор с `base._read_target_metric_window`.
5. **Clamp дозы: пересчёт ml ↔ ms** (D4) + логирование `effective_ml`; согласовать `multi_parallel` (D5).
6. **`last_dose_at` только после DONE** (D6).
7. Fail-closed для `solution_volume_l` (D8); валидация `far_zone > close_zone` (D11); cap на retry alert-block (D7).
8. Probe актуатора + алерт при recovery прерванной коррекции (D10).

Обновить: `CORRECTION_CYCLE_SPEC.md`, `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md` (семантика stop при manual, идемпотентность cmd_id).

### Фаза 3 — Инфраструктура команд (1-2 недели)

1. **Outbox/saga для publish pipeline** (I3): минимум — идемпотентный recovery всех промежуточных состояний `ae_commands` (частично есть в startup recovery → распространить на periodic reconcile).
2. **Deadline на command poll** (I5): default poll-timeout из типа команды/duration_ms даже без stage deadline; согласовать с HL — sweeper stale `SENT → TIMEOUT` (отдельная задача в HL).
3. **Circuit breaker + конфигурируемый retry HL** (I7): env `AE_HL_MAX_RETRIES`, `AE_HL_RETRY_BACKOFF_SEC`; open → fast-fail `command_send_failed`.
4. **NOTIFY catch-up** (I6): после reconnect — запрос пропущенных terminal intents/zone events по `created_at`; backpressure (semaphore + coalesce per zone).
5. Granular httpx timeouts (I10); HL health в `/health/ready` (I9).

### Фаза 4 — API и безопасность (неделя)

1. **Auth + rate limit на `/state`, `/control-mode`, climate tick** (A1, A5).
2. **Guard `automation_runtime='ae3'` на ingress** (A2) с каноническим 409-кодом.
3. **Не утекать `str(exc)`** в HTTP (A3); глобальный exception handler + `RequestValidationError` handler (A4).
4. Синхронизировать `error_codes.json` с фактически используемыми кодами (A7).
5. `secrets.compare_digest` для токена (A9); fail-fast `enforce=0` при `APP_ENV != local` (A6).
6. Hot-reload: применять только между stages, event `CONFIG_HOT_RELOAD_SKIPPED` при конфликте (A8).

### Фаза 5 — Наблюдаемость (1-2 недели, параллельно с 2-4)

1. **JSON-логи**: подключить `common.logging_setup` (O1); единый log-context `{task_id, zone_id, stage, correction_window_id, cmd_id, trace_id}` в worker/handlers (O5, O6); INFO-логи FSM-переходов claim/terminal/CAS-miss (O4); access-log 4xx/успешного dispatch (O9).
2. **Метрики** (O2): `ae3_pending_tasks`, `ae3_oldest_pending_task_age_seconds`, `ae3_task_duration_seconds{outcome}`, `ae3_listener_connected`/`_reconnect_total`, `ae3_hl_request_duration_seconds`/`_errors_total{status}`, `ae3_pg_pool_acquire_wait_seconds`, `ae3_drain_crashes_total`, `ae3_stale_tasks_reclaimed_total`.
3. **Алерты** (O3): pending age > 10 мин; «есть работа, но нет тиков»; listener down; fail_safe_transition; waiting_command stuck по возрасту; заменить `AE3StuckTask` на age-based. Панели Grafana для новых метрик.
4. **Zone events для UI** (O7): `AE_STAGE_TRANSITION`/`AE_STAGE_FAILED` для two-tank переходов и stage deadline; `AE_TASK_CANCELLED` с reason; `AE_FAIL_SAFE_TRANSITION`.
5. Метрика `ae3_observability_write_failed_total` на проглоченные ошибки записи событий (O8).
6. Удалить/пометить deprecated legacy `alerts_manager.py`, `health_monitor.py`, `error_handler.py`, `PROMETHEUS_PORT=9401` (O11).

### Фаза 6 — Отложенное (backlog)

- Leader election / полноценный multi-replica режим (R7 полный).
- Redis-based rate limiter с cap ключей (A5).
- Унификация timeout-политики greenhouse climate ↔ zone gateway.
- Расхождения doc/code по probe policy (`AE3_IRR_FAILSAFE…` §349) — синхронизировать.

---

## 6. Критерии приёмки (сквозные)

1. **Chaos-тест**: kill -9 AE в каждом окне FSM (`claimed`, `running`, `waiting_command`, mid-publish) → после рестарта или без него (periodic reconcile) зона разблокируется ≤ TTL, ни одна команда не задублирована.
2. **Оффлайн-узел**: команда к offline-узлу завершается fail-closed за bounded time (poll deadline), с zone_event и алертом; насос не остаётся ON.
3. **Деградация HL/PG**: при 5xx HL — circuit breaker, fast-fail, метрики; при исчерпании пула — acquire timeout + метрика, без вечных зависаний.
4. **Наблюдаемость**: один цикл коррекции трассируется end-to-end по JSON-логам по `correction_window_id`; застрявшая pending task поднимает алерт ≤ 10 мин.
5. Все существующие тесты (`make test-ae`) зелёные; новые unit/integration на каждый фикс critical/high.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
