# Laravel Scheduler + AE — Рефакторинг (as-built)

**Статус:** DONE (все 3 фазы)
**Дата завершения:** 2026-03-12
**Ветка:** ae3

---

## Что было сделано

Трёхфазный рефакторинг, закрывший три взаимосвязанные проблемы:

1. **Фаза 1 — Cleanup:** Удалены 3 deprecated трейта (~1300 строк); `SchedulerCycleService` (1421 строка) разбит на 4 специализированных класса + тонкая обёртка (backward compat).
2. **Фаза 2 — Boundary fix:** Статус AE3-задач читается напрямую из shared DB (`zone_automation_intents`) вместо HTTP-опроса AE API. HTTP остался как fallback для старых задач без `intent_id` в details.
3. **Фаза 3 — Event-driven:** Добавлен PostgreSQL NOTIFY-триггер на терминальные переходы `zone_automation_intents`; реализованы два слушателя — Python AE background task и Laravel artisan daemon. В AE callback теперь будит worker через `worker.kick()`, а tracked background tasks ведутся fail-closed.

---

## Текущая архитектура

### Участвующие компоненты

```
automation:dispatch-schedules (Artisan command)
    │
    └──► SchedulerCycleService  [thin wrapper, backward compat]
             │
             └──► SchedulerCycleOrchestrator  [владеет runCycle()]
                      ├──► ScheduleLoader       [загрузка зон, targets, cursors]
                      ├──► ScheduleDispatcher   [dispatch одного расписания]
                      └──► SchedulerCycleFinalizer  [time-crossings, cursor, cleanup]

automation:intent-listener (Artisan daemon, via supervisor)
    │
    └──► LISTEN scheduler_intent_terminal (PDO::pgsqlGetNotify)
             │
             └──► ActiveTaskStore::findByIntentId() → markTerminal()

AE3 Python (background task в lifespan)
    └──► IntentStatusListener (asyncpg dedicated connection)
             └──► LISTEN scheduler_intent_terminal
```

### Поток статусов задач (AE3-зоны)

```
zone_automation_intents (PostgreSQL)
    │
    ├── [UPDATE status → completed/failed/cancelled]
    │       │
    │       └──► TRIGGER trg_intent_terminal
    │               └──► pg_notify('scheduler_intent_terminal', {intent_id, zone_id, status, error_code})
    │
    ├──► automation:intent-listener (PHP daemon)  ← realtime
    │       └──► ActiveTaskStore::markTerminal()
    │               └──► laravel_scheduler_active_tasks.status = terminal
    │
    └──► IntentStatusListener (Python AE)  ← realtime fast-path wake-up
```

### Fallback polling

`ActiveTaskPoller::reconcilePendingActiveTasks()` продолжает работать как fallback (каждую минуту) для задач, которые не были покрыты NOTIFY (например: слушатель перезапускался, задача завершилась в оффлайн).

---

## Файловая структура

### Новые/изменённые PHP-файлы

| Файл | Статус | Ответственность |
|------|--------|-----------------|
| `Services/AutomationScheduler/SchedulerCycleService.php` | Переписан (thin wrapper) | Backward compat facade → `SchedulerCycleOrchestrator` |
| `Services/AutomationScheduler/SchedulerCycleOrchestrator.php` | Создан | `runCycle()`, построение расписаний, метрики, лог-буфер |
| `Services/AutomationScheduler/ScheduleLoader.php` | Создан | Загрузка зон, targets, lastRun, cursors |
| `Services/AutomationScheduler/ScheduleDispatcher.php` | Создан | HTTP dispatch в AE, intent upsert, active task snapshot |
| `Services/AutomationScheduler/SchedulerCycleFinalizer.php` | Создан | Crossings, catchup policy, cursor persist, cleanup |
| `Services/AutomationScheduler/ActiveTaskPoller.php` | Изменён | Добавлены DB-first статус + HTTP fallback |
| `Services/AutomationScheduler/ActiveTaskStore.php` | Изменён | Добавлен `findByIntentId()` |
| `Console/Commands/AutomationIntentListener.php` | Создан | Artisan daemon: LISTEN + markTerminal |
| `database/migrations/2026_03_12_120000_add_intent_terminal_notify_trigger.php` | Создан | PostgreSQL trigger |

### Удалённые PHP-файлы

| Файл | Причина |
|------|---------|
| `Console/Commands/Concerns/BuildsAutomationDispatchSchedules.php` | Deprecated trait, код перенесён в Orchestrator/Finalizer |
| `Console/Commands/Concerns/DispatchesAutomationSchedules.php` | Deprecated trait, код перенесён в Dispatcher/Poller |
| `Console/Commands/Concerns/ConfiguresAutomationDispatch.php` | Deprecated trait, код перенесён в Loader/Orchestrator |

### Новые/изменённые Python-файлы

| Файл | Статус | Ответственность |
|------|--------|-----------------|
| `ae3lite/infrastructure/intent_status_listener.py` | Создан | `IntentStatusListener` — asyncpg LISTEN, auto-reconnect |
| `ae3lite/runtime/app.py` | Изменён | Запуск listener в lifespan, `worker.kick()` callback, hard-limit background tasks |

---

## Архитектура классов (PHP)

### SchedulerCycleService

Тонкая обёртка для backward compatibility. Все вызывающие стороны продолжают работать без изменений.

```php
class SchedulerCycleService {
    public function __construct(
        private readonly SchedulerCycleOrchestrator $orchestrator,
    ) {}

    public function runCycle(array $cfg, array $zoneFilter): array {
        return $this->orchestrator->runCycle($cfg, $zoneFilter);
    }
}
```

### SchedulerCycleOrchestrator

Главный оркестратор. Владеет `runCycle()`, строит `$schedules`, управляет циклом, пишет метрики и буферизует логи.

**Ключевые методы:**
- `runCycle(array $cfg, array $zoneFilter): array`
- `buildSchedulesForZone(int $zoneId, array $targets, ...): array`
- `buildGenericTaskSchedules(string $taskType, array $spec, ...): array`
- `isTaskScheduleEnabled(string $taskType, array $cfg): bool`
- `writeSchedulerLog(string $taskName, string $status, array $details): void` (буферизует)
- `writeSchedulerLogImmediate(string $taskName, string $status, array $details): void`
- `flushSchedulerLogsBuffer(): void`
- `writeCycleMetrics(array $stats): void`

**Зависимости:** `ScheduleLoader`, `ScheduleDispatcher`, `SchedulerCycleFinalizer`, `LightingScheduleParser`, `ActiveTaskPoller`

### ScheduleLoader

Загрузка данных, необходимых для построения расписаний цикла.

**Ключевые методы:**
- `loadActiveZoneIds(array $cfg): array<int>`
- `loadEffectiveTargetsByZone(array $zoneIds): array<int, mixed>`
- `loadLastRunBatch(array $taskNames): array<string, CarbonImmutable>` — батч-выборка для interval-задач
- `collectIntervalTaskNames(array $schedules): array<string>` — сбор имён для батч-запроса
- `resolveZoneLastCheck(int $zoneId, array $cfg): CarbonImmutable`

**Зависимости:** `EffectiveTargetsService`, `ZoneCursorStore`

### ScheduleDispatcher

Диспатч одного расписания в AE: HTTP POST + intent upsert + снапшот активной задачи.

**Ключевые методы:**
- `dispatch(array $schedule, array $cfg, string $traceId, callable $writeLog): array` — основной entry point
- `upsertSchedulerIntent(int $zoneId, string $intentType, array $payload, ...): array`
- `persistActiveTaskSnapshot(int $zoneId, string $taskId, array $intentSnapshot, ...): void`
- `buildSchedulerCorrelationId(int $zoneId, string $taskType, string $time): string`
- `resolveSubmittedTaskIdentity(array $response): array{task_id: ?string, intent_id: ?int}`
- `computeTaskDeadlines(array $cfg, CarbonImmutable $now): array{pending_deadline: ..., running_deadline: ...}`
- `mapTaskTypeToIntentType(string $taskType): string` — `irrigation` → `IRRIGATE_ONCE`, etc.
- `normalizeSubmittedTaskStatus(string $status): string`

**Зависимости:** `ActiveTaskStore`, `ActiveTaskPoller`, Http

### SchedulerCycleFinalizer

Временная логика, cursor, cleanup.

**Ключевые методы:**
- `cleanupTerminalActiveTasks(array $cfg): void`
- `scheduleCrossings(CarbonImmutable $last, CarbonImmutable $now, string $targetTime): array<CarbonImmutable>`
- `applyCatchupPolicy(array $crossings, CarbonImmutable $now, string $policy, int $maxWindows): array`
- `shouldRunIntervalTask(string $taskName, int $intervalSec, CarbonImmutable $now, array $lastRunByTaskName): bool`
- `isTimeInWindow(string $nowTime, string $startTime, string $endTime): bool`
- `persistZoneCursor(int $zoneId, CarbonImmutable $cursorAt, string $catchupPolicy, bool $enabled, callable $writeLog): void`

**Зависимости:** `ZoneCursorStore`, `ActiveTaskStore`

---

## Фаза 2: DB-first статус AE3-задач

### Проблема

Для AE3-зон `fetchAe3CanonicalTaskStatus()` делала HTTP GET `/internal/tasks/{taskId}` к AE API. Так как Laravel и AE используют одну БД PostgreSQL, `intent_id` уже доступен через `laravel_scheduler_active_tasks.details['intent_id']`.

### Новый путь

1. **Основной (DB-first):** `intent_id` из `details` → `SELECT status FROM zone_automation_intents WHERE id = :intent_id AND zone_id = :zone_id`
2. **Fallback (HTTP):** только если `intent_id` отсутствует в details (старые задачи или задачи без intent)

```php
// ActiveTaskPoller
private function fetchAe3CanonicalTaskStatus(
    LaravelSchedulerActiveTask $task,
    string $taskId,
    array $cfg,
): ?string {
    $intentId = $this->resolveIntentIdForTask($task);
    if ($intentId > 0) {
        return $this->fetchIntentStatusFromDb($intentId, (int) $task->zone_id);
    }
    Log::debug('AE3 status poll via HTTP fallback (no intent_id in details)', [
        'task_id' => $taskId,
        'zone_id' => $task->zone_id,
    ]);
    return $this->fetchAe3StatusViaHttp($task, $taskId, $cfg);
}

private function fetchIntentStatusFromDb(int $intentId, int $zoneId): ?string
{
    $row = DB::table('zone_automation_intents')
        ->where('id', $intentId)
        ->where('zone_id', $zoneId)
        ->first(['status']);

    if ($row === null) {
        return 'not_found';
    }

    return match (strtolower(trim((string) ($row->status ?? '')))) {
        'pending', 'claimed', 'running', 'waiting_command' => 'accepted',
        'completed'  => 'completed',
        'failed'     => 'failed',
        'cancelled'  => 'cancelled',
        default      => null,
    };
}
```

### `ActiveTaskStore::findByIntentId()`

Новый метод для поиска активной задачи по `intent_id` из JSONB поля `details`:

```php
public function findByIntentId(int $intentId, int $zoneId): ?LaravelSchedulerActiveTask
{
    return LaravelSchedulerActiveTask::query()
        ->where('zone_id', $zoneId)
        ->whereRaw("(details->>'intent_id')::int = ?", [$intentId])
        ->whereNotIn('status', SchedulerConstants::TERMINAL_STATUSES)
        ->orderByDesc('id')
        ->first();
}
```

---

## Фаза 3: PostgreSQL NOTIFY

### Trigger

Миграция: `2026_03_12_120000_add_intent_terminal_notify_trigger.php`

```sql
CREATE OR REPLACE FUNCTION notify_intent_terminal()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IN ('completed', 'failed', 'cancelled')
     AND (OLD.status IS DISTINCT FROM NEW.status) THEN
    PERFORM pg_notify(
      'scheduler_intent_terminal',
      json_build_object(
        'intent_id',  NEW.id,
        'zone_id',    NEW.zone_id,
        'status',     NEW.status,
        'error_code', NEW.error_code
      )::text
    );
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_intent_terminal
  AFTER UPDATE ON zone_automation_intents
  FOR EACH ROW EXECUTE FUNCTION notify_intent_terminal();
```

**Канал:** `scheduler_intent_terminal`

**Payload (JSON):**
```json
{
  "intent_id": 123,
  "zone_id": 42,
  "status": "completed",
  "error_code": null
}
```

### Python: IntentStatusListener

Файл: `ae3lite/infrastructure/intent_status_listener.py`

Класс с выделенным asyncpg-коннектом (вне общего пула), keepalive SELECT 1 каждые 30 сек, exponential backoff при reconnect (1s → 60s).

```python
class IntentStatusListener:
    def __init__(
        self,
        dsn: str,
        on_terminal_intent: Callable[[dict], Coroutine],
    ) -> None: ...

    def stop(self) -> None: ...         # кооперативная остановка через asyncio.Event
    async def run(self) -> None: ...    # внешняя точка входа с auto-reconnect
```

Запускается в `app.py` lifespan как background task (только если `runtime_config.db_dsn` задан):

```python
if runtime_config.db_dsn:
    async def _on_terminal_intent(data: dict[str, Any]) -> None:
        bundle.worker.kick()

    intent_listener = IntentStatusListener(
        dsn=runtime_config.db_dsn,
        on_terminal_intent=_on_terminal_intent,
    )
    intent_listener_task = _spawn_background_task(
        intent_listener.run(),
        background_tasks=background_tasks,
        task_name="ae3-intent-status-listener",
    )
```

При shutdown: `intent_listener.stop()` → `_drain_background_tasks()`.

Дополнительные runtime-инварианты:
- Python listener не ведёт отдельный status store и не меняет DB state напрямую; его роль — ускорить повторный drain через `worker.kick()`.
- `background_tasks` registry в AE имеет hard limit и при переполнении отклоняет spawn fail-closed, вместо best-effort продолжения.

### PHP: automation:intent-listener

Файл: `Console/Commands/AutomationIntentListener.php`

Долгоживущий artisan daemon. Запускается через supervisor (не через `schedule()`).

```bash
php artisan automation:intent-listener
php artisan automation:intent-listener --timeout=3600
php artisan automation:intent-listener --poll-interval=5000
```

**Опции:**
- `--timeout=0` — максимальное время работы в секундах (0 = бесконечно)
- `--poll-interval=5000` — таймаут `pgsqlGetNotify` в мс (минимум 100)

**Логика обработки уведомления:**
1. Парсить JSON payload
2. Проверить `intentId`, `zoneId`, `intentStatus` (должны быть валидными и терминальными)
3. `ActiveTaskStore::findByIntentId($intentId, $zoneId)` — найти активную задачу
4. Если задача уже в терминальном статусе — пропустить
5. `ActiveTaskStore::markTerminal(taskId, status, now, detailsPatch, lastPolledAt)` — пометить как завершённую

**`detailsPatch` при обработке NOTIFY:**
```php
[
    'terminal_source' => 'intent_notify_listener',
    'intent_id'       => $intentId,
    'error_code'      => $errorCode,
]
```

---

## Архитектурный факт: intent_type vs task_type

**Для AE3 v1 через `POST /zones/{id}/start-cycle` будится только `irrigation`.**

`mapTaskTypeToIntentType('irrigation')` → `'IRRIGATE_ONCE'` — это значение сохраняется в `zone_automation_intents.intent_type` для аудита, а runtime-path AE3 исполняет только `cycle_start`. Scheduler-maintenance task types (`lighting`, `ventilation`, `solution_change`, `mist`, `diagnostics`) не должны будить `cycle_start` в AE3 v1 и пропускаются на стороне Laravel dispatcher до появления выделенных executor-ов.

Это осознанное ограничение текущего scope: AE3 v1 владеет только cycle-start workflow, а scheduler не должен расширять этот scope косвенно через legacy task_type.

---

## Запуск и проверка

### PHP тесты (scheduler)

```bash
docker compose -f backend/docker-compose.dev.yml exec laravel \
  php artisan test --filter=AutomationScheduler

docker compose -f backend/docker-compose.dev.yml exec laravel \
  php artisan test --filter=AutomationDispatchSchedules
```

### Ручной dispatch

```bash
docker compose -f backend/docker-compose.dev.yml exec laravel \
  php artisan automation:dispatch-schedules --zone-id=447
```

### Запуск intent listener (вручную)

```bash
docker compose -f backend/docker-compose.dev.yml exec laravel \
  php artisan automation:intent-listener --poll-interval=2000
```

### Проверка NOTIFY trigger

```bash
# Терминал 1 — подписаться
docker compose -f backend/docker-compose.dev.yml exec db \
  psql -U hydro hydro_dev -c "LISTEN scheduler_intent_terminal; SELECT pg_sleep(60);"

# Терминал 2 — перевести intent в terminal
docker compose -f backend/docker-compose.dev.yml exec db \
  psql -U hydro hydro_dev -c \
  "UPDATE zone_automation_intents SET status='completed' WHERE id=<id>;"
```

### Python тесты (AE)

```bash
docker compose -f backend/docker-compose.dev.yml exec automation-engine \
  pytest -x -q -k "intent_status_listener or startup_recovery or worker"
```

---

## Зависимости в DI (AppServiceProvider)

Новые классы регистрируются через Laravel DI. Тонкая обёртка `SchedulerCycleService` разрешается автоматически, если `SchedulerCycleOrchestrator` зарегистрирован:

```php
// app/Providers/AppServiceProvider.php
$this->app->singleton(SchedulerCycleOrchestrator::class);
$this->app->singleton(ScheduleLoader::class);
$this->app->singleton(ScheduleDispatcher::class);
$this->app->singleton(SchedulerCycleFinalizer::class);
```

`AutomationIntentListener` разрешается через constructor injection (Laravel автоматически инжектирует `ActiveTaskStore`).
