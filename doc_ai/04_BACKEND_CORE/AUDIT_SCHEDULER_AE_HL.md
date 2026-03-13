# Аудит: Scheduler ↔ Automation Engine ↔ History Logger

**Дата:** 2026-03-12
**Ветка:** ae3
**Статус:** Phase 1 выполнена; observability остаётся открытой, hardening частично закрыт

---

## Содержание

1. [Баги (критические и средние)](#1-баги)
2. [Race conditions и проблемы синхронизации](#2-race-conditions)
3. [Таймауты и узкие места](#3-таймауты)
4. [Наблюдаемость](#4-наблюдаемость)
5. [Архитектурные проблемы](#5-архитектура)
6. [План исправлений по фазам](#6-план-исправлений)

---

## 1. Баги

### 1.1 [CRITICAL] `mark_intent_terminal` не защищён WHERE status guard

**Статус:** закрыто 2026-03-12

**Файл:** `backend/services/automation-engine/ae3lite/api/intents.py:179-194`

```python
UPDATE zone_automation_intents
SET status = $2, completed_at = $3, ...
WHERE id = $1
```

**Проблема:** UPDATE без `WHERE status IN ('claimed', 'running')`. Два сценария гонки:

1. **AE перезаписывает scheduler timeout:**
   - Scheduler помечает intent `failed` (c guard `WHERE status IN ('pending','claimed','running')`) из-за hard_stale_after_sec
   - AE чуть позже завершает task → вызывает `mark_intent_terminal(success=True)` → безусловный UPDATE → intent становится `completed`
   - Результат: scheduler думает что задача провалена, intent говорит что успех — рассинхрон

2. **Двойной terminal UPDATE:** Если оба (AE и scheduler) пытаются пометить intent terminal одновременно, последний writer побеждает без детекции конфликта.

**Фикс:**
```python
UPDATE zone_automation_intents
SET status = $2, completed_at = $3, ...
WHERE id = $1
  AND status IN ('pending', 'claimed', 'running')
```

**Приоритет:** P0
**Оценка:** 15 минут

---

### 1.2 [CRITICAL] `asyncio.get_event_loop()` в IntentStatusListener

**Статус:** закрыто 2026-03-12

**Файл:** `backend/services/automation-engine/ae3lite/infrastructure/intent_status_listener.py:123`

```python
asyncio.get_event_loop().create_task(self._dispatch(data))
```

**Проблема:** `get_event_loop()` deprecated в Python 3.10+, выбрасывает `DeprecationWarning`. В Python 3.12+ вызывает `RuntimeError` если нет running loop. Callback `_notify_handler` вызывается asyncpg sync — running loop **есть** (asyncpg гарантирует), но использование deprecated API — бомба замедленного действия.

**Фикс:** Заменить на `asyncio.get_running_loop().create_task(...)`.

**Приоритет:** P1
**Оценка:** 5 минут

---

### 1.3 [MEDIUM] `datetime.utcnow()` в SequentialCommandGateway

**Файл:** `backend/services/automation-engine/ae3lite/infrastructure/gateways/sequential_command_gateway.py:133`

```python
reconcile_now = datetime.utcnow().replace(microsecond=0)
```

**Проблема:** `datetime.utcnow()` deprecated в Python 3.12. Весь остальной код использует `utcnow_naive` из `common.utils.time`. Это единственное место с прямым вызовом `utcnow()`.

**Фикс:** Заменить на `datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)` или пробросить `now_fn` в gateway.

**Приоритет:** P2
**Оценка:** 10 минут

---

### 1.4 [MEDIUM] HistoryLoggerClient создаёт новый httpx.AsyncClient на каждый запрос

**Статус:** закрыто 2026-03-12

**Файл:** `backend/services/automation-engine/ae3lite/infrastructure/clients/history_logger_client.py:71-75`

```python
async def _post(self, path, payload, headers):
    if self._client is not None:
        return await self._client.post(...)
    async with httpx.AsyncClient(timeout=self._timeout_sec) as client:
        return await client.post(...)  # новое TCP соединение каждый раз
```

**Проблема:** По умолчанию `self._client = None`, поэтому каждый `publish()` создаёт новый `httpx.AsyncClient` → новый TCP connection → TLS handshake (если HTTPS). В two_tank workflow одна задача может отправить 5-15 команд последовательно — это 5-15 новых соединений.

**Фикс:** Создавать и переиспользовать `httpx.AsyncClient` на уровне `create_app()` / bootstrap, передавать в конструктор.

**Приоритет:** P1
**Оценка:** 30 минут

---

### 1.5 [MEDIUM] `upsertSchedulerIntent` мутирует terminal intents

**Файл:** `backend/laravel/app/Services/AutomationScheduler/ScheduleDispatcher.php:298-328`

```sql
ON CONFLICT (idempotency_key)
DO UPDATE SET
    payload = EXCLUDED.payload,
    not_before = EXCLUDED.not_before,
    updated_at = EXCLUDED.updated_at
RETURNING id
```

**Проблема:** Если intent с данным `idempotency_key` уже `completed/failed/cancelled`, UPDATE всё равно меняет `payload`, `not_before`, `updated_at`. Это:
- Загрязняет audit trail (updated_at меняется после завершения)
- Может сбить stale-detection, который опирается на `updated_at`

**Фикс:** Добавить `WHERE` в `DO UPDATE`:
```sql
ON CONFLICT (idempotency_key)
DO UPDATE SET ...
WHERE zone_automation_intents.status NOT IN ('completed', 'failed', 'cancelled')
```

**Приоритет:** P2
**Оценка:** 10 минут

---

### 1.6 [LOW] IntentStatusListener в AE — бесполезный callback

**Файл:** `backend/services/automation-engine/ae3lite/runtime/app.py:187-196`

```python
async def _on_terminal_intent(data: dict) -> None:
    intent_id = data.get("intent_id")
    zone_id = data.get("zone_id")
    status = data.get("status")
    logger.info(
        "IntentStatusListener: terminal intent received ...",
        intent_id, zone_id, status,
    )
```

**Проблема:** Callback только логирует. Не триггерит worker kick, не обновляет кэш, не очищает lease. Listener потребляет отдельное DB-соединение (вне пула) и CPU ради одного `logger.info`.

**Фикс:** Либо удалить listener из AE (NOTIFY полезен только для Laravel-стороны), либо добавить полезное действие — например, `bundle.worker.kick()` для быстрого подхвата следующей задачи.

**Приоритет:** P3
**Оценка:** 15 минут (удаление) или 30 минут (полезный callback)

---

## 2. Race Conditions и синхронизация

### 2.1 [MEDIUM] Task claim + zone lease — не атомарная операция

**Файл:** `backend/services/automation-engine/ae3lite/application/use_cases/claim_next_task.py:52-83`

**Поток:**
1. `claim_next_pending()` — атомарный `UPDATE ... FOR UPDATE SKIP LOCKED`
2. `zone_lease_repository.claim()` — отдельный `INSERT ON CONFLICT`
3. Если lease не получен → `release_claim()` откатывает task

**Проблема:** Между шагами 1 и 2 task в статусе `claimed`, но lease не получен. Если AE падает между 1 и 2:
- Task остаётся `claimed` навсегда (пока startup recovery не найдёт его)
- Zone lease может быть у другого owner

**Текущая защита:** single-worker дизайн, startup_recovery. При одном AE instance — проблема теоретическая.

**Риск:** При горизонтальном масштабировании (2+ AE instances) — deadlock/starvation.

**Фикс (будущий):** Advisory lock на zone_id перед claim_next_pending, или CTE-объединение claim + lease в одну транзакцию.

**Приоритет:** P3 (не блокер при single-worker)

---

### 2.2 [MEDIUM] Двойной NOTIFY при scheduler + AE terminal update

**Сценарий:**
1. AE завершает task → `mark_intent_terminal(completed)` → trigger fires NOTIFY
2. Scheduler одновременно поллит → `syncIntentTerminalStatus(failed)` → guard `WHERE status IN ('pending','claimed','running')` → UPDATE пропускается (уже completed)

Этот сценарий безопасен благодаря guard в scheduler. **НО** обратный порядок опасен (см. bug 1.1):
1. Scheduler поллит → `syncIntentTerminalStatus(failed)` → UPDATE (с guard) succeeds
2. AE завершает → `mark_intent_terminal(completed)` → UPDATE (без guard!) succeeds → перезаписывает failed → **рассинхрон**

**Фикс:** Bug 1.1 (добавить WHERE guard в `mark_intent_terminal`).

---

### 2.3 [LOW] Scheduler cycle не атомарен между reconcile и dispatch

**Файл:** `backend/laravel/app/Services/AutomationScheduler/SchedulerCycleOrchestrator.php:63-68`

```php
$reconciledBusyness = $this->activeTaskPoller->reconcilePendingActiveTasks(...);
// ... далее dispatch цикл ...
```

**Проблема:** `reconciledBusyness` — snapshot на момент вызова. К моменту dispatch (через 10-50ms) status может измениться. Это не критично, т.к.:
- `isScheduleBusy()` делает fresh check если key не в reconciled map
- Idempotency key предотвращает дубли

**Оценка:** приемлемый trade-off.

---

## 3. Таймауты и узкие места

### 3.1 [CRITICAL] Нет общего таймаута выполнения task в worker

**Статус:** закрыто 2026-03-12

**Файл:** `backend/services/automation-engine/ae3lite/runtime/worker.py:86-164`

```python
async def _drain_pending_tasks(self) -> None:
    while True:
        claimed = await self._claim_next_task_use_case.run(...)
        ...
        final_task = await self._execute_task_use_case.run(task=task, now=...)
        # ← Нет asyncio.wait_for / timeout_after
```

**Проблема:** Если `execute_task_use_case.run()` зависает (DB connection pool exhausted, HL не отвечает, handler infinite loop) — worker заблокирован навсегда. Lease heartbeat продлевает lease, не давая другим workers забрать zone.

**Текущие защиты:**
- `stage_deadline_at` в command gateway (проверяется в poll loop) — но только для command polling, не для handler execution
- Lease TTL (300s, heartbeat каждые 100s) — если heartbeat тоже заблокирован, lease истечёт через 5 минут

**Фикс:** `worker` использует bounded whole-task timeout (`AE_MAX_TASK_EXECUTION_SEC`, default `900s`). Timeout-path отменяет execution с причиной `ae3_task_execution_timeout`, `ExecuteTaskUseCase` выполняет fail-safe shutdown и fail-closed terminal transition task; затем worker доводит intent до terminal статуса.

**Приоритет:** P0
**Оценка:** 45 минут

---

### 3.2 [MEDIUM] Цепочка таймаутов не согласована

**Статус:** Phase 1 закрыла базовое согласование defaults 2026-03-12

**Полная цепочка:**

```
Laravel Scheduler (dispatch)
  ├─ HTTP timeout к AE: timeout_sec (cfg, обычно 5-10s)
  ├─ expires_after_sec: 600s (intent expiry from scheduler)
  └─ hard_stale_after_sec: effective default `max(900, expires_after_sec*2)` = 1200s (20 min)

AE (execution)
  ├─ start_cycle_claim_stale_sec: 180s (3 min)
  ├─ start_cycle_running_stale_sec: 1800s (30 min)
  ├─ lease_ttl_sec: 300s (5 min)
  ├─ stage_deadline_at: varies by stage (runtime config)
  └─ command gateway poll: 0.5s interval, deadline = stage_deadline_at

HL (command publish)
  └─ HL timeout to MQTT: implicit (paho default)
```

**Проблемы:**

1. **hard_stale_after_sec = 30 минут** — scheduler считает задачу "потенциально живой" 30 минут даже если AE уже пометил intent terminal. Это значит что `isScheduleBusy()` возвращает `true` до 30 минут если intent_notify_listener не сработал.

2. **Разрыв частично закрыт:** scheduler defaults приведены к `expires_after_sec=600s` и effective `hard_stale_after_sec=max(900, expires_after_sec*2)`. При явном override `hard_stale_after_sec` пользовательское значение сохраняется.

3. **Нет retry budget для failed commands:** Если HL вернул ошибку, command gateway сразу fail-ит task. Нет retry с backoff на transient HL errors.

**Фикс:**
- Выровнять `expires_after_sec` с реальной длительностью workflow (предложение: 600s)
- Уменьшить `hard_stale_after_sec` (предложение: `max(900, expires_after_sec * 2)`)
- Добавить 1-retry с 1s backoff в `HistoryLoggerClient.publish()`

**Приоритет:** P1
**Оценка:** 1 час

---

### 3.3 [MEDIUM] Command polling без backoff

**Файл:** `backend/services/automation-engine/ae3lite/infrastructure/gateways/sequential_command_gateway.py:131-141`

```python
while True:
    await asyncio.sleep(self._poll_interval_sec)  # 0.5s fixed
    ...
```

**Проблема:** Фиксированный интервал 0.5s. Для relay_node (ответ за 50-100ms) — избыточная задержка. Для climate_node (ответ за 5-30s) — слишком частый polling.

**Фикс:** Экспоненциальный backoff: start=0.2s, max=5s, factor=1.5.

**Приоритет:** P3
**Оценка:** 20 минут

---

### 3.4 [LOW] `_BACKGROUND_TASKS_SIZE_LIMIT = 256` — мягкий лимит

**Файл:** `backend/services/automation-engine/ae3lite/runtime/app.py:49,62-69`

При достижении 256 background tasks — лишь `logger.error`, но task всё равно создаётся. В теории бесконечный рост.

**Фикс:** Hard limit с отклонением создания task (return None или raise).

**Приоритет:** P3

---

## 4. Наблюдаемость

### 4.1 [HIGH] Laravel Scheduler не экспортирует Prometheus метрики

**Проблема:** Все метрики scheduler идут в таблицу `scheduler_logs` (DB). Нет Prometheus endpoint → невозможно:
- Построить dashboard в Grafana для cycle duration, dispatch rate, active tasks
- Настроить алерты на Prometheus (увеличение failed dispatches, cycle duration spike)
- Корреляция между scheduler и AE метриками в одном стеке

**Python сервисы:** AE (`:9401/metrics`), HL (`:9301/metrics`), Scheduler (`:9402/metrics`) — все имеют Prometheus.

**Фикс:** Добавить Prometheus PHP exporter или реализовать `/metrics` endpoint в Laravel, экспортирующий:
- `laravel_scheduler_cycle_duration_seconds` (histogram)
- `laravel_scheduler_dispatches_total` (counter by zone_id, task_type, result)
- `laravel_scheduler_active_tasks_count` (gauge)

**Приоритет:** P2
**Оценка:** 2-3 часа (новый endpoint + метрики)

---

### 4.2 [MEDIUM] Нет метрики для полного RTT команды

**Файл:** `backend/services/automation-engine/ae3lite/infrastructure/metrics.py`

**Есть:**
- `ae3_command_dispatch_duration_seconds` — время отправки в HL
- `ae3_command_terminal_total` — счётчик terminal статусов

**Нет:**
- **`ae3_command_roundtrip_duration_seconds`** — от publish до terminal status (включая время на node ответ)
- **`ae3_command_poll_iterations_total`** — сколько poll циклов до terminal (для определения оптимального poll interval)

**Фикс:** Добавить histogram RTT и counter poll iterations в `SequentialCommandGateway`.

**Приоритет:** P2
**Оценка:** 30 минут

---

### 4.3 [MEDIUM] health_ready всегда рапортует worker=ok

**Файл:** `backend/services/automation-engine/ae3lite/runtime/app.py:378-380`

```python
"worker": {"ok": True, "reason": runtime_config.worker_owner},
```

**Проблема:** Если drain task упал и не был respawned — readiness probe врёт. Kubernetes/Docker не узнает что AE не обрабатывает задачи.

**Фикс:** Проверять `bundle.worker._drain_task` is not None and not done, и проверять время последнего claim (если > 5 * idle_poll_interval — suspicious).

**Приоритет:** P1
**Оценка:** 30 минут

---

### 4.4 [LOW] Нет tracing span для inter-service HTTP calls

**AE → HL:** Trace-ID пробрасывается (middleware), но нет OpenTelemetry spans.
**Scheduler → AE:** X-Trace-Id header есть.

**Проблема:** Нельзя построить distributed trace Scheduler → AE → HL → MQTT → Node.

**Приоритет:** P4 (будущее)

---

### 4.5 [LOW] Отсутствуют метрики для intent lifecycle

Нет Prometheus метрик для:
- `intent_created_total`
- `intent_claimed_total`
- `intent_terminal_total{status}`
- `intent_stale_reclaimed_total`

Это ключевой coordination primitive, но он невидим в мониторинге.

**Приоритет:** P3
**Оценка:** 30 минут

---

## 5. Архитектурные проблемы

### 5.1 [INFO] Дублирование MQTT publish logic в HL

**Файлы:**
- `command_service.py:106-162` — `publish_command_mqtt()` использует `base_client._client.publish()` (прямой paho)
- `command_service.py:49-57` — `_mqtt_client_context()` создаёт новый MqttClient каждый раз
- `command_routes.py` — использует `get_mqtt_client()` singleton

Три разных паттерна доступа к MQTT в одном сервисе.

### 5.2 [INFO] Two-tank exclusive дизайн

Вся AE3 архитектура (topology registry, workflow router, stage handlers) заточена под `two_tank`/`two_tank_drip_substrate_trays`. Другие topologies (single_tank, drip_to_waste) не имеют stage definitions → fallback на generic `run_batch` без workflow FSM.

### 5.3 [INFO] LaravelSchedulerActiveTask vs zone_automation_intents — параллельные truth stores

Два источника правды о статусе задачи:
- `laravel_scheduler_active_tasks` (Laravel) — кэш для fast busy check
- `zone_automation_intents` (shared DB) — canonical status

`syncIntentTerminalStatus` и `intent_notify_listener` пытаются синхронизировать их, но при сбое любого listener-а — diverge.

---

## 6. План исправлений по фазам

### Фаза 1: Critical bugs (P0-P1)

**Статус:** выполнена 2026-03-12
**Примечание:** worker timeout-path доведён до fail-closed semantics; scheduler timeout defaults и legacy default derivation синхронизированы. Таргетные `automation-engine` и `laravel` тесты пройдены в Docker.

| # | Задача | Файл(ы) | Оценка |
|---|--------|---------|--------|
| 1 | WHERE guard в `mark_intent_terminal` | `ae3lite/api/intents.py` | 15 мин |
| 2 | `asyncio.wait_for` для task execution в worker | `ae3lite/runtime/worker.py` | 45 мин |
| 3 | `asyncio.get_running_loop()` в IntentStatusListener | `ae3lite/infrastructure/intent_status_listener.py` | 5 мин |
| 4 | Reusable `httpx.AsyncClient` в HistoryLoggerClient | `ae3lite/infrastructure/clients/history_logger_client.py`, `ae3lite/runtime/bootstrap.py` | 30 мин |
| 5 | Worker health в readiness probe | `ae3lite/runtime/app.py` | 30 мин |
| 6 | Согласование таймаутов (expires_after_sec, hard_stale) | `ScheduleDispatcher.php`, `ActiveTaskPoller.php`, `SchedulerConstants.php` | 45 мин |

**Итого фаза 1:** ~3 часа

### Фаза 2: Observability (P2)

| # | Задача | Файл(ы) | Оценка |
|---|--------|---------|--------|
| 7 | Prometheus метрики в Laravel scheduler | Laravel, новый endpoint | 2-3 часа |
| 8 | Command RTT histogram + poll iteration counter | `sequential_command_gateway.py`, `metrics.py` | 30 мин |
| 9 | `datetime.utcnow()` → `utcnow_naive` | `sequential_command_gateway.py` | 10 мин |
| 10 | WHERE guard в `upsertSchedulerIntent` | `ScheduleDispatcher.php` | 10 мин |

**Итого фаза 2:** ~3.5 часа

### Фаза 3: Hardening (P3)

**Статус:** выполнено для `automation-engine` 2026-03-12
**Примечание:** закрыты задачи 11-15 в AE3-Lite (`intent` метрики, polling backoff, activation `IntentStatusListener`, hard limit background tasks, retry в `HistoryLoggerClient`).

| # | Задача | Файл(ы) | Оценка |
|---|--------|---------|--------|
| 11 | Intent lifecycle Prometheus метрики | `ae3lite/api/intents.py`, `metrics.py` | 30 мин |
| 12 | Exponential backoff в command polling | `sequential_command_gateway.py` | 20 мин |
| 13 | Удалить или активировать AE IntentStatusListener | `ae3lite/runtime/app.py` | 15 мин |
| 14 | Hard limit на background tasks | `ae3lite/runtime/app.py` | 15 мин |
| 15 | 1-retry с backoff в HistoryLoggerClient | `history_logger_client.py` | 30 мин |

**Итого фаза 3:** ~2 часа

### Тестирование

После каждой фазы:
```bash
# AE тесты
docker compose -f backend/docker-compose.dev.yml exec automation-engine pytest -x -q

# HL тесты
docker compose -f backend/docker-compose.dev.yml exec history-logger pytest -x -q

# Laravel тесты
docker compose -f backend/docker-compose.dev.yml exec laravel php artisan test

# Протокольные контракты
make protocol-check
```

---

## Приложение: Диаграмма таймаутов (после исправлений фазы 1)

```
Scheduler dispatch cycle (every ~60s)
│
├─ HTTP POST to AE ──── timeout_sec (5-10s) ────→ AE /start-cycle
│
├─ intent expires_after_sec ─── 600s ──────────→ default для scheduler
│
├─ hard_stale_after_sec ──── 1200s (20 min) ──→ effective default `max(900, expires*2)`
│
│                             AE Task Execution
│                             ├─ claim_stale_sec: 180s
│                             ├─ running_stale_sec: 1800s
│                             ├─ lease_ttl_sec: 300s
│                             │   └─ heartbeat: 100s
│                             ├─ whole-task timeout: 900s
│                             └─ stage_deadline_at: varies
│                                 └─ command poll: 0.5s fixed
│
│                                              HL Command
│                                              └─ httpx timeout: 5s
│                                                  └─ MQTT QoS 1
```

**Зафиксированные значения / инварианты:**
- `expires_after_sec`: default **600s**
- `hard_stale_after_sec`: effective default **max(900, expires*2)**
- `AE_MAX_TASK_EXECUTION_SEC`: default **900s** (15 min)
- Command poll: 0.5s fixed → **0.2s start, 5s max, 1.5x backoff**
