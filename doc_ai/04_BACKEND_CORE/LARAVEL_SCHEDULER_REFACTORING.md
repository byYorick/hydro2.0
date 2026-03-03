# Laravel Scheduler — Plan рефакторинга

**Статус:** PLANNED
**Дата:** 2026-03-03
**Ветка:** feature/laravel-scheduler-refactor

---

## Контекст

`automation:dispatch-schedules` — Laravel Artisan команда, которая каждую минуту:
1. Загружает активные зоны и их effective targets
2. Строит расписания из targets (время, интервалы, окна)
3. Отправляет HTTP POST `/zones/{id}/start-cycle` → automation-engine
4. Отслеживает статусы активных задач (polling)
5. Сохраняет zone cursors для catch-up

Код реализован в 3 трейтах + основной команде (~1500 строк суммарно):
- `BuildsAutomationDispatchSchedules` — парсинг расписаний
- `DispatchesAutomationSchedules` — dispatch + polling
- `ConfiguresAutomationDispatch` — конфигурация, загрузка зон

---

## Выявленные проблемы

### Критические (баги / мёртвый код)

**P0-1. Поле `task_type` в `upsertSchedulerIntent` — мёртвый код**
Файл: `DispatchesAutomationSchedules.php:626`

```php
$intentPayload = [
    'task_type' => 'diagnostics',  // ← всегда, для любого task type
    'topology' => 'two_tank_drip_substrate_trays',  // ← хардкод
    ...
];
```

Реальность: `api_intents.py:68` на стороне automation-engine всегда ставит
`task_type = "diagnostics"` и `topology = default_topology` из конфига АЕ —
значения из intent payload просто игнорируются.
Итог: оба поля в payload — мёртвый код, вводящий в заблуждение.

**P0-2. `intent_type` (IRRIGATE_ONCE / LIGHTING_TICK) никогда не доходит до executor**
`build_scheduler_task_request_from_intent` в AE создаёт `SchedulerTaskRequest`
с `task_type="diagnostics"` всегда. `intent_type` хранится в БД только для аудита.
Это архитектурный факт, но он нигде не задокументирован — разработчики ожидают,
что scheduling по типу работает, а он не работает.

**P0-3. `toIso` не включает timezone-суффикс**
Файл: `DispatchesAutomationSchedules.php:706`

```php
return $value->format('Y-m-d\TH:i:s');  // "2026-03-03T10:00:00" — без Z
```

ISO 8601 без суффикса амбивалентен. Automation-engine (Python) парсит через
`datetime.fromisoformat()` — в Python <3.11 строка без суффикса трактуется как
local time, не UTC.

**P0-4. `ACTIVE_ZONE_STATUSES` смешивает регистры**
`['online', 'warning', 'RUNNING', 'PAUSED']` — симптом несогласованности в
`zones.status`. Запрос использует `whereIn` без LOWER() → хрупко.

---

### Производительность (N+1 и отсутствие индексов)

**P1-1. `shouldRunIntervalTask` — одна SQL-выборка на каждый interval-тип задачи**
Файл: `BuildsAutomationDispatchSchedules.php:309`

```php
// Вызывается ВНУТРИ foreach ($schedules as $schedule)
$lastTerminalLog = SchedulerLog::query()
    ->where('task_name', $taskName)
    ->whereIn('status', ['completed', 'failed'])
    ->orderByDesc('created_at')->orderByDesc('id')
    ->first(['created_at']);
```

При 10 зонах × 3 interval-расписания = 30 DB-запросов в минуту.
Фиксируется батч-выборкой всех нужных task_name за один запрос в начале цикла.

**P1-2. `fetchTaskStatus` — JSONB-scan без индекса**
Файл: `DispatchesAutomationSchedules.php:527`

```php
SchedulerLog::query()
    ->whereRaw("details->>'task_id' = ?", [$taskId])
    ...
```

Существующие индексы (миграция `2026_02_10`) покрывают `details->>'zone_id'`,
но НЕ `details->>'task_id'`. При 500 pending-задачах = 500 seq-scan'ов в минуту.
Фиксируется: либо добавлением expression index, либо заменой источника истины
(использовать `laravel_scheduler_active_tasks.status` напрямую).

**P1-3. Двойной polling одной задачи за цикл**
`reconcilePendingActiveTasks` в начале цикла полит все pending-задачи.
Затем `isScheduleBusy` для каждого занятого расписания вызывает
`reconcilePersistedActiveTask` снова — для тех же задач.
Одна задача полится дважды.

**P1-4. `markTerminal` = SELECT + UPDATE вместо одного UPDATE**
Файл: `ActiveTaskStore.php:161-184`

```php
$task = $this->findByTaskId($taskId);  // SELECT
if (! $task) { return; }
$task->fill([...])->save();            // UPDATE
```

Должно быть: `UPDATE WHERE task_id = ? AND status NOT IN (terminal_statuses)`.

---

### Дизайн и сопровождаемость

**P2-1. 3 трейта = разрезанный класс со скрытым shared state**
Трейты обращаются к `$this->activeTaskStore`, `$this->zoneCursorStore`,
`$this->zoneCursorCache` — это не независимые компоненты, а искусственно
разрезанный монолит. Добавление метода в любой трейт без понимания двух
других ломает инварианты.

**P2-2. `$zoneCursorCache` — instance property вместо локальной переменной**
`private array $zoneCursorCache = []` объявлен на уровне класса, но нужен
только внутри одного вызова `dispatchCycle`. Создаёт ощущение, что кеш
живёт дольше одного цикла.

**P2-3. `$targets` в каждом schedule-массиве — бесполезный оверхед**
Каждый schedule item хранит `'targets' => $targets` (весь объект effective
targets). `dispatchSchedule` берёт из schedule только `type` и `payload` —
`targets` никуда не уходит. При 10 зонах × 5 расписаний = 50 копий targets
в памяти за цикл.

**P2-4. Дублирование `TERMINAL_STATUSES`**
Константа объявлена в `AutomationDispatchSchedules` (Command) и независимо
воспроизведена в `ActiveTaskStore`. При добавлении нового статуса надо
обновлять оба места вручную.

**P2-5. Три несовместимых пути разбора расписания освещения**
`buildSchedulesForZone` обрабатывает lighting тремя ветками:
- `photoperiod_hours + start_time` → window (start/end)
- `lighting_schedule` как `"HH:MM-HH:MM"` строка → window
- fallback → `buildGenericTaskSchedules` (time-points или interval)

Ни одна ветка не задокументирована. При добавлении четвёртого формата
логика становится нечитаемой.

**P2-6. Нормализация статусов дублируется в двух местах**
`normalizeTerminalStatus` в трейте и `normalizeStatus` в `ActiveTaskStore`
делают одно и то же: `done→completed`, `error→failed`. Расхождение гарантировано
при следующем изменении.

---

### Надёжность

**P3-1. Redis-сбой → молчаливый skip всего цикла**
```php
} catch (\Throwable $e) {
    Log::warning('...');
    return null;  // lock = null
}
// handle(): if (!$lock) return SUCCESS  ← никакого алерта
```
При деградации Redis все расписания молча не срабатывают. Операторы видят
только `Log::warning` в общем потоке логов.

**P3-2. `scheduler_logs` растёт без ограничений**
`writeSchedulerLog` пишет строку на каждое событие (accepted, cursor, failed...) —
минимум 10–20 строк в минуту. `logs:cleanup` — раз в неделю. При 50 зонах
таблица растёт ~72 000 строк/сутки.

---

## Архитектурный факт, требующий документирования

**Все типы задач всегда выполняются как `diagnostics/cycle_start`.**

`mapTaskTypeToIntentType('irrigation') → 'IRRIGATE_ONCE'` — это значение сохраняется
в `zone_automation_intents.intent_type` для аудита. Но `api_intents.py` при
обработке intent всегда создаёт `SchedulerTaskRequest(task_type="diagnostics")`.
Automation-engine сам определяет, что делать, исходя из фазы зоны (FSM).

Последствие: scheduling типов `lighting`, `ventilation`, `mist` через `/start-cycle`
сегодня не приводит к запуску специфичного workflow — запускается тот же
`cycle_start`. Это осознанное архитектурное решение или незавершённый функционал —
нужно зафиксировать явно.

---

## Plan рефакторинга

### Phase 0 — Correctness (без рефакторинга, просто фиксы)

**Файлы:** `DispatchesAutomationSchedules.php`, `ConfiguresAutomationDispatch.php`

#### 0.1. Убрать мёртвые поля из `upsertSchedulerIntent`
Удалить из `$intentPayload`:
- `'task_type' => 'diagnostics'` — automation-engine игнорирует, вводит в заблуждение
- `'topology' => 'two_tank_drip_substrate_trays'` — automation-engine использует
  свой `default_topology` из конфига, не это поле

Оставить только: `source`, `intent_type` (уже есть как отдельная колонка в схеме).

#### 0.2. Исправить `toIso` — добавить `Z`
```php
// Было:
return $value->format('Y-m-d\TH:i:s');
// Стало:
return $value->format('Y-m-d\TH:i:s\Z');
```
Проверить все вызовы `toIso` в тестах и данных.

#### 0.3. Нормализовать `ACTIVE_ZONE_STATUSES`
Заменить `whereIn('status', self::ACTIVE_ZONE_STATUSES)` на
`whereIn(DB::raw('lower(status)'), ['online', 'warning', 'running', 'paused'])`.
Либо добавить миграцию, приводящую колонку к единому регистру.

#### 0.4. Задокументировать архитектурный факт о `intent_type` vs `task_type`
В `DispatchesAutomationSchedules.php` над `mapTaskTypeToIntentType` и в
`api_intents.py` добавить комментарии, объясняющие что `intent_type` = auditing
only, `task_type` при выполнении всегда `"diagnostics"`.

---

### Phase 1 — Performance (N+1 elimination)

**Файлы:** `BuildsAutomationDispatchSchedules.php`, `DispatchesAutomationSchedules.php`,
`ActiveTaskStore.php`, новая миграция

#### 1.1. Батч-выборка для `shouldRunIntervalTask`

Вместо SQL-запроса на каждый interval-тип задачи — одна выборка в начале цикла:

```php
// До dispatchCycle loop: загрузить все last_run для нужных task_name
$intervalTaskNames = $this->collectIntervalTaskNames($schedules);
$lastRunByTaskName = $this->loadLastRunBatch($intervalTaskNames);

// shouldRunIntervalTask теперь принимает $lastRunByTaskName вместо DB-запроса
private function shouldRunIntervalTask(
    string $taskName,
    int $intervalSec,
    CarbonImmutable $now,
    array $lastRunByTaskName,  // ← новый параметр
): bool
```

`loadLastRunBatch` — один запрос:
```sql
SELECT task_name, MAX(created_at) as last_at
FROM scheduler_logs
WHERE task_name = ANY(?) AND status IN ('completed', 'failed')
GROUP BY task_name
```

#### 1.2. Добавить expression index на `details->>'task_id'`

Новая миграция `2026_03_XX_add_scheduler_logs_task_id_index.php`:
```sql
CREATE INDEX scheduler_logs_details_task_id_idx
ON scheduler_logs ((details->>'task_id'))
WHERE details->>'task_id' IS NOT NULL;
```

Либо (радикальнее): добавить колонку `task_id VARCHAR(128)` в `scheduler_logs`,
выставляемую при записи, с обычным B-tree индексом. Убирает JSONB-scan полностью.

#### 1.3. Устранить двойной polling

`reconcilePendingActiveTasks` строит map `scheduleKey → isBusy` и возвращает его
наружу. `isScheduleBusy` сначала смотрит в этот map — если результат уже есть,
не делает повторный `reconcilePersistedActiveTask`:

```php
// Возвращаемый результат из reconcilePendingActiveTasks
/** @var array<string, bool> $reconciledBusyness */
$reconciledBusyness = $this->reconcilePendingActiveTasks($cfg, $headers);

// isScheduleBusy проверяет map первым делом
private function isScheduleBusy(
    string $scheduleKey,
    array $cfg,
    array $headers,
    array $reconciledBusyness,  // ← добавить
): bool {
    if (array_key_exists($scheduleKey, $reconciledBusyness)) {
        return $reconciledBusyness[$scheduleKey];
    }
    // ... остальная логика
}
```

#### 1.4. `markTerminal` — один UPDATE вместо SELECT + UPDATE

```php
public function markTerminal(
    string $taskId,
    string $status,
    CarbonImmutable $terminalAt,
    array $detailsPatch = [],
    ?CarbonImmutable $lastPolledAt = null,
): void {
    LaravelSchedulerActiveTask::query()
        ->where('task_id', $taskId)
        ->whereNotIn('status', self::TERMINAL_STATUSES)
        ->update([
            'status' => $this->normalizeStatus($status),
            'terminal_at' => $terminalAt,
            'last_polled_at' => $lastPolledAt,
            // details merge через raw jsonb concatenation
            'details' => DB::raw("details || ?::jsonb"),
        ]);
}
```

Примечание: jsonb merge в Laravel требует raw expression с binding.
Альтернатива проще — SELECT + conditional UPDATE остаётся, но переносится
в `ActiveTaskStore::markTerminalIfNotAlready` с явным именем.

---

### Phase 2 — Architecture (extract service, remove traits)

**Новые файлы:**
- `app/Services/AutomationScheduler/SchedulerCycleService.php`
- `app/Services/AutomationScheduler/ScheduleItem.php` (DTO)
- `app/Services/AutomationScheduler/ScheduleCycleContext.php` (value object)
- `app/Services/AutomationScheduler/LightingScheduleParser.php`
- `app/Services/AutomationScheduler/ActiveTaskPoller.php`

**Изменяемые файлы:**
- `AutomationDispatchSchedules.php` → становится тонкой обёрткой
- Трейты → удаляются (или помечаются deprecated до удаления)

#### 2.1. `ScheduleItem` DTO

```php
final class ScheduleItem
{
    public function __construct(
        public readonly int $zoneId,
        public readonly string $taskType,
        public readonly ?string $time,           // "HH:mm:ss" | null
        public readonly ?string $startTime,      // "HH:mm:ss" | null
        public readonly ?string $endTime,        // "HH:mm:ss" | null
        public readonly int $intervalSec,        // 0 = не интервальный
        public readonly string $scheduleKey,
        public readonly array $payload,          // только то, что нужно для dispatch
    ) {}
}
```

Убирает `'targets' => $targets` из schedule-массивов (P2-3).

#### 2.2. `ScheduleCycleContext` — один объект вместо россыпи переменных

```php
final class ScheduleCycleContext
{
    public function __construct(
        public readonly array $cfg,
        public readonly array $headers,
        public readonly string $traceId,
        public readonly CarbonImmutable $cycleNow,
        public readonly array $lastRunByTaskName,  // для interval check (1.1)
        public readonly array $reconciledBusyness, // для isScheduleBusy (1.3)
    ) {}
}
```

#### 2.3. `LightingScheduleParser` — единая точка разбора освещения

```php
final class LightingScheduleParser
{
    /**
     * Принимает lighting config и возвращает ScheduleItem или null.
     * Единственное место, где знает про photoperiod_hours, lighting_schedule, time-points.
     */
    public function parse(int $zoneId, array $lightingConfig, array $targets): ?ScheduleItem;
}
```

Три ветки `buildSchedulesForZone` для lighting → один вызов `LightingScheduleParser::parse`.

#### 2.4. `SchedulerCycleService` — основная логика цикла

```php
final class SchedulerCycleService
{
    public function __construct(
        private readonly ActiveTaskStore $activeTaskStore,
        private readonly ActiveTaskPoller $poller,
        private readonly ZoneCursorStore $zoneCursorStore,
        private readonly EffectiveTargetsService $effectiveTargetsService,
        private readonly LightingScheduleParser $lightingParser,
        private readonly ScheduleBuilder $scheduleBuilder,
    ) {}

    public function runCycle(array $cfg, array $zoneFilter): CycleStats;
}
```

`AutomationDispatchSchedules::handle()` становится:
```php
public function handle(): int
{
    // проверка enabled, acquire lock, вызов service->runCycle(), release lock
    // ~40 строк вместо 350
}
```

#### 2.5. `ActiveTaskPoller` — отдельный сервис polling

Инкапсулирует:
- `reconcilePendingActiveTasks`
- `isScheduleBusy`
- `fetchTaskStatus`

Принимает batch task_ids, возвращает `array<string, bool>` (scheduleKey → isBusy).

---

### Phase 3 — `TERMINAL_STATUSES` единая константа

**Файл:** новый `app/Services/AutomationScheduler/SchedulerConstants.php`

```php
final class SchedulerConstants
{
    public const TERMINAL_STATUSES = [
        'completed', 'done', 'failed', 'rejected',
        'expired', 'timeout', 'error', 'cancelled', 'not_found',
    ];

    public const ACTIVE_ZONE_STATUSES_LOWER = ['online', 'warning', 'running', 'paused'];
}
```

`AutomationDispatchSchedules`, `ActiveTaskStore`, `DispatchesAutomationSchedules` —
все используют `SchedulerConstants::TERMINAL_STATUSES`.

---

### Phase 4 — Observability

#### 4.1. Redis-сбой → исключение или алерт (не `Log::warning`)

```php
if (! $lock) {
    // Если исключение от Redis — это критичная ошибка, не просто "занят"
    Log::error('Laravel scheduler: lock acquisition failed — Redis unavailable');
    // Вызвать alert-hook или бросить исключение чтобы cron записал non-zero exit
    return self::FAILURE;
}
```

Или отличать "lock занят другим процессом" от "Redis недоступен" по типу исключения.

#### 4.2. Батч-запись в `scheduler_logs` (или async)

Вместо N вызовов `SchedulerLog::query()->create(...)` в цикле — накапливать
в буфере и делать `SchedulerLog::insert($buffer)` в конце цикла.
Исключение — критичные события (error/failed), которые пишем сразу.

#### 4.3. Prometheus-метрики для цикла

Добавить к `/metrics` эндпоинту Laravel (если есть) или записывать в `scheduler_logs`
в структурированном виде:
- `laravel_scheduler_dispatches_total{zone_id, task_type, result}`
- `laravel_scheduler_cycle_duration_seconds`
- `laravel_scheduler_active_tasks_count`

---

## Приоритизация для 3 AI-агентов

### Агент 1 — Correctness + Performance DB (Phase 0 + Phase 1)

**Входные файлы:**
- `DispatchesAutomationSchedules.php`
- `BuildsAutomationDispatchSchedules.php`
- `ConfiguresAutomationDispatch.php`
- `ActiveTaskStore.php`
- Миграции `2026_02_20_180000_*`, `2026_02_20_180100_*`

**Задачи:**
1. Phase 0.1 — убрать `task_type`/`topology` из `upsertSchedulerIntent` payload
2. Phase 0.2 — `toIso` добавить `\Z`
3. Phase 0.3 — нормализовать `ACTIVE_ZONE_STATUSES` (case-insensitive)
4. Phase 0.4 — добавить комментарий об `intent_type` vs `task_type` в обоих файлах
5. Phase 1.1 — батч-выборка для `shouldRunIntervalTask`
6. Phase 1.2 — новая миграция с expression index `details->>'task_id'`
7. Phase 1.4 — `markTerminal` → один UPDATE

**Тесты:**
- `tests/Feature/AutomationScheduler/ShouldRunIntervalTaskTest.php` — батч vs individual
- `tests/Unit/AutomationScheduler/ActiveTaskStoreTest.php` — markTerminal
- `tests/Unit/AutomationScheduler/DispatchesAutomationSchedulesTest.php` — toIso имеет Z

**Критерий приёмки:** старые тесты не ломаются, N+1 устранён (проверить через `DB::enableQueryLog`).

---

### Агент 2 — ScheduleItem DTO + LightingScheduleParser + SchedulerConstants (Phase 2 + 3)

**Входные файлы:**
- `BuildsAutomationDispatchSchedules.php`
- `AutomationDispatchSchedules.php`
- `ActiveTaskStore.php`

**Задачи:**
1. Phase 2.1 — создать `ScheduleItem` DTO, заменить raw array везде
2. Phase 2.3 — создать `LightingScheduleParser`, удалить 3-ветковый if
3. Phase 2.2 — убрать `'targets'` из schedule items
4. Phase 3 — создать `SchedulerConstants`, переиспользовать в 3 местах
5. Phase 2.5 — убрать `$zoneCursorCache` из instance property, сделать локальной переменной цикла

**Тесты:**
- `tests/Unit/AutomationScheduler/LightingScheduleParserTest.php` — все 3 сценария + midnight crossing
- `tests/Unit/AutomationScheduler/ScheduleItemTest.php` — basic DTO validation

**Критерий приёмки:** `buildSchedulesForZone` для lighting — один путь; все 3 прежних варианта покрыты тестами.

---

### Агент 3 — SchedulerCycleService extract + double-polling fix + observability (Phase 2.4 + 1.3 + 4)

**Входные файлы:**
- `AutomationDispatchSchedules.php`
- `DispatchesAutomationSchedules.php`
- `ConfiguresAutomationDispatch.php`
- `ActiveTaskStore.php`

**Задачи:**
1. Phase 2.4 — создать `SchedulerCycleService`, перенести логику из трейтов
2. Phase 2.5 — создать `ActiveTaskPoller` как отдельный сервис
3. Phase 1.3 — устранить двойной polling через `reconciledBusyness` map
4. Phase 4.1 — Redis-fail = `FAILURE` (не `SUCCESS`)
5. Phase 4.2 — батч-запись `scheduler_logs` в конце цикла
6. Трейты → помечаются как deprecated или удаляются (если агент 1/2 уже перенесли всё)

**Тесты:**
- `tests/Feature/AutomationScheduler/SchedulerCycleServiceTest.php` — полный dispatch cycle mock
- `tests/Unit/AutomationScheduler/ActiveTaskPollerTest.php` — двойной polling устранён

**Критерий приёмки:** `AutomationDispatchSchedules::handle()` ≤ 50 строк; трейты не используются кодом.

---

## DB-изменения (миграции)

| Миграция | Тип | Содержимое |
|---|---|---|
| `2026_03_XX_add_scheduler_logs_task_id_index` | index | `(details->>'task_id')` expression index |
| `2026_03_XX_normalize_zone_status_case` (опционально) | data | `UPDATE zones SET status = LOWER(status)` |

---

## Не включено в план (out of scope)

- Переход с polling-модели на event-driven (WebSocket/pg_notify) — отдельный эпик
- Поддержка реального multi-topology диспатча (lighting/ventilation как отдельные workflows)
- Горизонтальное масштабирование (PostgreSQL advisory lock вместо Redis)
- Переход `scheduler_logs` на отдельный сервис логирования

---

## Проверка выполнения

```bash
# PHP тесты
docker compose -f backend/docker-compose.dev.yml exec laravel \
  php artisan test --filter=AutomationScheduler

# Query log проверка (N+1)
# В тестах: DB::enableQueryLog(), прогнать цикл, DB::getQueryLog() → assert count < N

# Запуск команды вручную с zone-filter
docker compose -f backend/docker-compose.dev.yml exec laravel \
  php artisan automation:dispatch-schedules --zone-id=1
```
