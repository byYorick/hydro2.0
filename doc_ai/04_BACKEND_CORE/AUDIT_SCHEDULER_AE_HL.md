# Аудит: Scheduler ↔ Automation Engine ↔ History Logger

**Дата:** 2026-03-12
**Ветка:** ae3
**Статус:** аудит синхронизирован с актуальным кодом на 2026-03-13; часть исторических пунктов закрыта, оставшиеся замечания относятся в основном к observability и hardening

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

**Статус:** закрыто 2026-03-12

**Файл:** `backend/services/automation-engine/ae3lite/infrastructure/gateways/sequential_command_gateway.py:133`

```python
reconcile_now = datetime.utcnow().replace(microsecond=0)
```

**Проблема:** `datetime.utcnow()` deprecated в Python 3.12. Весь остальной код использует `utcnow_naive` из `common.utils.time`. Это единственное место с прямым вызовом `utcnow()`.

**Фикс:** Прямой `utcnow()` убран; gateway использует общий UTC helper.

**Приоритет:** закрыто
**Оценка:** выполнено

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

### 1.5 [MEDIUM] `upsertSchedulerIntent` мутировал terminal intents

**Статус:** закрыто 2026-03-12

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

### 1.6 [LOW] IntentStatusListener в AE использует fire-and-forget fast-path

**Статус:** частично закрыто 2026-03-12

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

**Проблема:** Исходная формулировка устарела. Callback уже делает `worker.kick()` и используется как realtime fast-path. Актуальное замечание уже уже: dispatch остаётся fire-and-forget, а ошибка callback только логируется.

**Фикс:** Держать listener как fast-path wake-up. При дальнейшем усложнении callback потребуется retry/self-heal или явный fallback.

**Приоритет:** P4
**Оценка:** 15-30 минут при необходимости дополнительного hardening

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

### 2.2 [INFO] Двойной NOTIFY при scheduler + AE terminal update

**Статус:** исторический сценарий; критичный конфликт закрыт фиксами в `mark_intent_terminal`

**Сценарий:**
1. AE завершает task → `mark_intent_terminal(completed)` → trigger fires NOTIFY
2. Scheduler одновременно поллит → `syncIntentTerminalStatus(failed)` → guard `WHERE status IN ('pending','claimed','running')` → UPDATE пропускается (уже completed)

Этот сценарий безопасен благодаря guard в scheduler. Ранее обратный порядок был опасен (см. bug 1.1):
1. Scheduler поллит → `syncIntentTerminalStatus(failed)` → UPDATE (с guard) succeeds
2. AE завершает → `mark_intent_terminal(completed)` → UPDATE (без guard!) succeeds → перезаписывает failed → **рассинхрон**

После добавления WHERE guard в `mark_intent_terminal` этот сценарий больше не является открытым багом.

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

1. **`hard_stale_after_sec` по умолчанию всё ещё велик** — effective default сейчас `1200s` (20 минут), поэтому без fast-path notify/poll reconcile зона может оставаться busy дольше, чем хотелось бы для чувствительных расписаний.

2. **Разрыв частично закрыт:** scheduler defaults приведены к `expires_after_sec=600s` и effective `hard_stale_after_sec=max(900, expires_after_sec*2)`. При явном override `hard_stale_after_sec` пользовательское значение сохраняется.

3. **Retry budget жёстко ограничен архитектурой:** у `automation-engine -> history-logger` разрешён не более чем один transient retry с backoff. Это сознательный fail-closed инвариант, а не просто недоделка.

**Фикс / текущее состояние:**
- Выровнять `expires_after_sec` с реальной длительностью workflow (предложение: 600s)
- Уменьшить `hard_stale_after_sec` (предложение: `max(900, expires_after_sec * 2)`)
- Не увеличивать retries в `HistoryLoggerClient.publish()` без синхронного изменения архитектурной спецификации

**Приоритет:** P1
**Оценка:** 1 час

---

### 3.3 [MEDIUM] Command polling без backoff

**Статус:** закрыто 2026-03-12

**Файл:** `backend/services/automation-engine/ae3lite/infrastructure/gateways/sequential_command_gateway.py:131-141`

```python
while True:
    await asyncio.sleep(self._poll_interval_sec)  # 0.5s fixed
    ...
```

**Проблема:** Исторический пункт. На момент первичного аудита polling был с фиксированным интервалом; сейчас в runtime уже есть bounded backoff.

**Фикс:** Реализован bounded backoff: start от базового poll interval, рост до max interval с backoff factor.

**Приоритет:** закрыто
**Оценка:** выполнено

---

### 3.4 [LOW] `_BACKGROUND_TASKS_SIZE_LIMIT = 256` — мягкий лимит

**Статус:** закрыто 2026-03-12

**Файл:** `backend/services/automation-engine/ae3lite/runtime/app.py:49,62-69`

Исторический пункт. Сейчас при превышении лимита spawn отклоняется fail-closed с ошибкой, а coroutine закрывается.

**Фикс:** Hard limit с отклонением создания task реализован.

**Приоритет:** P3

---

## 4. Наблюдаемость

### 4.1 [HIGH] Laravel Scheduler не экспортирует Prometheus метрики

**Статус:** закрыто 2026-03-12

**Проблема:** Исторический пункт. Сейчас у Laravel scheduler есть metrics endpoint и exporter.

Раньше все метрики scheduler шли только в БД, из-за чего было невозможно:
- Построить dashboard в Grafana для cycle duration, dispatch rate, active tasks
- Настроить алерты на Prometheus (увеличение failed dispatches, cycle duration spike)
- Корреляция между scheduler и AE метриками в одном стеке

**Текущее состояние:** есть `/api/system/scheduler/metrics`, exporter и feature-тесты на Prometheus output.

**Фикс:** реализован.

**Приоритет:** закрыто
**Оценка:** выполнено

---

### 4.2 [MEDIUM] Нет метрики для полного RTT команды

**Статус:** закрыто 2026-03-12

**Файл:** `backend/services/automation-engine/ae3lite/infrastructure/metrics.py`

Исторический пункт. Эти метрики уже есть:
- `ae3_command_roundtrip_duration_seconds`
- `ae3_command_poll_iterations_total`

**Фикс:** реализован в `SequentialCommandGateway` и `metrics.py`.

**Приоритет:** закрыто
**Оценка:** выполнено

---

### 4.3 [MEDIUM] health_ready всегда рапортует worker=ok

**Статус:** закрыто 2026-03-12

**Файл:** `backend/services/automation-engine/ae3lite/runtime/app.py:378-380`

```python
"worker": {"ok": True, "reason": runtime_config.worker_owner},
```

**Проблема:** Исторический пункт. Сейчас readiness probe использует `bundle.worker.drain_health()` и уже не рапортует worker как безусловно healthy.

**Фикс:** Проверка health drain worker реализована.

**Приоритет:** закрыто
**Оценка:** выполнено

---

### 4.4 [LOW] Нет tracing span для inter-service HTTP calls

**AE → HL:** Trace-ID пробрасывается (middleware), но нет OpenTelemetry spans.
**Scheduler → AE:** X-Trace-Id header есть.

**Проблема:** Нельзя построить distributed trace Scheduler → AE → HL → MQTT → Node.

**Приоритет:** P4 (будущее)

---

### 4.5 [LOW] Отсутствуют метрики для intent lifecycle

**Статус:** частично закрыто 2026-03-12

Сейчас уже есть:
- `ae3_intent_claimed_total`
- `ae3_intent_terminal_total{status}`
- `ae3_intent_stale_reclaimed_total`

Остаётся возможное улучшение: добавить отдельную creation-метрику, если она действительно нужна для операционной картины.

**Приоритет:** P4
**Оценка:** 15-30 минут при подтверждённой ценности

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

**Статус:** частично выполнена 2026-03-12

| # | Задача | Файл(ы) | Оценка |
|---|--------|---------|--------|
| 7 | Prometheus метрики в Laravel scheduler | Laravel, новый endpoint | выполнено |
| 8 | Command RTT histogram + poll iteration counter | `sequential_command_gateway.py`, `metrics.py` | выполнено |
| 9 | `datetime.utcnow()` → `utcnow_naive` | `sequential_command_gateway.py` | выполнено |
| 10 | WHERE guard в `upsertSchedulerIntent` | `ScheduleDispatcher.php` | выполнено |

**Итого фаза 2:** базовые задачи выполнены; открыты только дополнительные observability-улучшения

### Фаза 3: Hardening (P3)

**Статус:** выполнено для `automation-engine` 2026-03-12
**Примечание:** закрыты задачи 11-15 в AE3-Lite (`intent` метрики, polling backoff, activation `IntentStatusListener`, hard limit background tasks, retry в `HistoryLoggerClient`).

| # | Задача | Файл(ы) | Оценка |
|---|--------|---------|--------|
| 11 | Intent lifecycle Prometheus метрики | `ae3lite/api/intents.py`, `metrics.py` | выполнено частично |
| 12 | Exponential backoff в command polling | `sequential_command_gateway.py` | выполнено |
| 13 | Удалить или активировать AE IntentStatusListener | `ae3lite/runtime/app.py` | выполнено (активирован fast-path kick) |
| 14 | Hard limit на background tasks | `ae3lite/runtime/app.py` | выполнено |
| 15 | 1-retry с backoff в HistoryLoggerClient | `history_logger_client.py` | выполнено |

**Итого фаза 3:** основные hardening-задачи для AE закрыты

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

## Приложение: Диаграмма таймаутов (актуализировано после синхронизации аудита)

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
│                                 └─ command poll: bounded backoff
│
│                                              HL Command
│                                              └─ httpx timeout: 5s
│                                                  └─ MQTT QoS 1
```

**Зафиксированные значения / инварианты:**
- `expires_after_sec`: default **600s**
- `hard_stale_after_sec`: effective default **max(900, expires*2)**
- `AE_MAX_TASK_EXECUTION_SEC`: default **900s** (15 min)
- Command poll: bounded backoff с ростом до max interval
- `automation-engine -> history-logger`: не более **1 transient retry** с backoff `1s`, далее fail-closed
