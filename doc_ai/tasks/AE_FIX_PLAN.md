# AE Fix Plan — Automation Engine: аудит и план фиксов

> Дата аудита: 2026-03-11
> Ветка: ae3
> Статус: ПЛАН (не реализован)

---

## Сводка найденных проблем

### Из анализа БД (подтверждено данными)

| ID | Проблема | Серьёзность | Подтверждение |
|----|----------|------------|---------------|
| BUG-DB-1 | **Все 19 задач упали** со статусом `failed`, стадия `startup`, причина: нет `zone_automation_logic_profile` | 🔴 КРИТИЧНО | `SELECT * FROM ae_tasks` → 19 rows, все `failed` |
| BUG-DB-2 | **Нулевых профилей автоматизации** — `zone_automation_logic_profiles` пустая для всех зон | 🔴 КРИТИЧНО | `SELECT * FROM zone_automation_logic_profiles` → 0 rows |
| BUG-DB-3 | **Race condition: дублирующиеся задачи** для зон 3 и 10 (по 2 задачи) | 🔴 КРИТИЧНО | `ae_tasks` zones 3 (id=3,4) и 10 (id=10,11) имеют по 2 задачи |
| BUG-DB-4 | **Нет `IRR_STATE_SNAPSHOT` событий** — `zone_events` не содержит ни одного события этого типа | 🔴 КРИТИЧНО | `SELECT * FROM zone_events WHERE type='IRR_STATE_SNAPSHOT'` → 0 rows |
| BUG-DB-5 | **`ae_zone_intents` таблица отсутствует** в схеме, хотя код ссылается на неё | 🟡 СРЕДН. | `\dt ae_*` → только 4 таблицы без `ae_zone_intents` |

### Из анализа кода Automation Engine

| ID | Проблема | Серьёзность | Файл |
|----|----------|------------|------|
| BUG-AE-1 | **Race condition в `create_task_from_intent`**: `get_active_for_zone()` → `get_zone_lease()` → `create_pending()` не атомарно, между ними может вклиниться другой worker | 🔴 КРИТИЧНО | `ae3lite/application/use_cases/create_task_from_intent.py` |
| BUG-AE-2 | **`startup` handler падает** если нет `IRR_STATE_SNAPSHOT` в `zone_events` — нет graceful handling, только `TaskExecutionError` | 🔴 КРИТИЧНО | `ae3lite/application/handlers/startup.py` |
| BUG-AE-3 | **`/zones/{id}/state` endpoint отсутствует** в ae3lite — существует только `/control-mode` и `/start-cycle` | 🔴 КРИТИЧНО | `ae3lite/runtime/app.py:305-309` |
| BUG-AE-4 | **`GetZoneControlStateUseCase` читает только активные задачи** — failed-задачи невидимы, зона показывается как IDLE | 🔴 КРИТИЧНО | `ae3lite/application/use_cases/get_zone_control_state.py:39-50` |
| BUG-AE-5 | **Нет валидации сенсоров до старта workflow** — snapshot валидирует actuators, но не sensors. Цикл стартует и падает на первом `_read_level()` | 🟡 СРЕДН. | `ae3lite/infrastructure/read_models/zone_snapshot_read_model.py:245` |
| BUG-AE-6 | **Zone lease может истечь** во время долгого execute — нет heartbeat механизма для продления lease | 🟡 СРЕДН. | `ae3lite/runtime/worker.py` |
| BUG-AE-7 | **`telemetry_max_age_sec` default = 300 сек** — решения по уровням резервуаров принимаются на данных до 5 минут давности | 🟡 СРЕДН. | `ae3lite/domain/services/two_tank_runtime_spec.py` |
| BUG-AE-8 | **Snapshot не кешируется** — загружается заново на каждый `execute_task`, 8 SQL-запросов при каждом тике | 🟢 MINOR | `ae3lite/infrastructure/read_models/zone_snapshot_read_model.py` |

### Из анализа Frontend

| ID | Проблема | Серьёзность | Файл |
|----|----------|------------|------|
| BUG-FE-1 | **`AutomationState` тип не содержит `error_code` и `error_message`** — frontend не может показать причину ошибки | 🔴 КРИТИЧНО | `resources/js/types/Automation.ts:42-83` |
| BUG-FE-2 | **`failed` и `error_code` не передаются из AE** — `buildCompatibilityStateFromControlMode()` всегда возвращает `failed: false` | 🔴 КРИТИЧНО | `app/Http/Controllers/ZoneAutomationStateController.php:206` |
| BUG-FE-3 | **`workflow_phase` и `current_stage` приходят с backend но игнорируются фронтом** — поля не отображаются в UI | 🟡 СРЕДН. | `resources/js/types/Automation.ts` (поля отсутствуют в типе) |
| BUG-FE-4 | **Нет индикатора времени последнего обновления** для live-данных (только для stale/cache) | 🟡 СРЕДН. | `resources/js/Components/AutomationWorkflowCard.vue` |
| BUG-FE-5 | **Fallback state (`buildCompatibilityStateFromControlMode`) не читает последнюю failed задачу** из БД — зоны с ошибкой показываются как IDLE | 🔴 КРИТИЧНО | `app/Http/Controllers/ZoneAutomationStateController.php:133-238` |

---

## Детальный план фиксов

### БЛОК 1: Критические баги данных и инфраструктуры

---

#### FIX-1: Добавить `zone_automation_logic_profiles` в seeder

**Проблема:** BUG-DB-2 + BUG-DB-1
**Причина:** Ни один seeder не создаёт записи в `zone_automation_logic_profiles`. Все попытки запустить цикл немедленно падают с `ae3_task_execution_failed: Zone X has no active zone_automation_logic_profile`.

**Что нужно сделать:**

1. Найти основной seeder для dev-данных (предположительно `DatabaseSeeder.php` или `FullServiceTestSeeder.php`)
2. Для каждой зоны создать запись в `zone_automation_logic_profiles` с:
   - `is_active = true`
   - `mode = 'auto'`
   - `command_plans` — валидный JSON со схемой `{"schema_version": 1, "plans": {...}}`
   - `automation_runtime = 'ae3'` (если поле присутствует в схеме)
3. Проверить, что `command_plans` содержит минимально необходимые планы: `clean_fill_start`, `clean_fill_stop`, `solution_fill_start`, `solution_fill_stop`, `prepare_recirculation_start`, `prepare_recirculation_stop`

**Файлы:**
- `backend/laravel/database/seeders/DatabaseSeeder.php` (или главный seeder)
- `backend/laravel/database/seeders/LiteAutomationSeeder.php` — проверить и дополнить
- `backend/laravel/database/migrations/2026_02_12_230100_create_zone_automation_logic_profiles_table.php` — проверить структуру

**Проверка:** После `make seed` → `SELECT count(*) FROM zone_automation_logic_profiles WHERE is_active = true;` → должно быть > 0

---

#### FIX-2: Добавить endpoint `/zones/{id}/state` в ae3lite

**Проблема:** BUG-AE-3 + BUG-FE-2
**Причина:** Laravel-контроллер запрашивает `/zones/{id}/state`, получает 404 и всегда падает в fallback, который показывает пустое IDLE-состояние независимо от реального статуса.

**Что нужно сделать:**

Добавить в `ae3lite/runtime/app.py`:
```python
@app.get("/zones/{zone_id}/state")
async def get_zone_state(zone_id: int) -> dict[str, Any]:
    """Full automation state for a zone — задачи, фазы, ошибки."""
    result = await bundle.get_zone_automation_state_use_case.run(zone_id=zone_id)
    return result
```

Создать `ae3lite/application/use_cases/get_zone_automation_state.py`:
- Читает последнюю задачу для зоны (включая `failed` и `completed`)
- Если задача `failed` — возвращает состояние с `state_details.failed=true`, `error_code`, `error_message`
- Если задача `running`/`waiting_command` — маппит `workflow_phase` → `AutomationStateType`
- Если задач нет или последняя `completed` — возвращает `state=IDLE`
- Структура ответа должна соответствовать `AutomationState` типу (включая новые поля из FIX-4)

**Файлы:**
- `backend/services/automation-engine/ae3lite/runtime/app.py` — регистрация маршрута
- `backend/services/automation-engine/ae3lite/application/use_cases/get_zone_automation_state.py` — новый файл
- `backend/services/automation-engine/ae3lite/runtime/bootstrap.py` — wire up нового use case

**Маппинг `workflow_phase` → `AutomationStateType`:**
```
idle          → IDLE
tank_filling  → TANK_FILLING
tank_recirc   → TANK_RECIRC
ready         → READY
error         → IDLE (с failed=true)
```

---

#### FIX-3: Исправить race condition в `create_task_from_intent`

**Проблема:** BUG-AE-1 + BUG-DB-3
**Причина:** Многошаговая проверка `get_active_for_zone()` → `get_zone_lease()` → `create_pending()` не атомарна. Подтверждено: зоны 3 и 10 имеют по 2 failed-задачи.

**Что нужно сделать:**

Вариант A (рекомендуется): использовать **PostgreSQL advisory lock** на уровне `zone_id` при создании задачи:
```sql
SELECT pg_try_advisory_xact_lock($1)  -- zone_id как ключ
```

Вариант B: объединить проверку active task + create в одну атомарную операцию через CTE:
```sql
WITH guard AS (
    SELECT id FROM ae_tasks
    WHERE zone_id = $zone_id
      AND status IN ('pending','claimed','running','waiting_command')
    FOR UPDATE
    LIMIT 1
)
INSERT INTO ae_tasks (...)
SELECT ...
WHERE NOT EXISTS (SELECT 1 FROM guard)
RETURNING *
```

**Файлы:**
- `backend/services/automation-engine/ae3lite/application/use_cases/create_task_from_intent.py`
- `backend/services/automation-engine/ae3lite/infrastructure/repositories/automation_task_repository.py`

**Проверка:** После фикса повторный вызов `start-cycle` для одной зоны должен возвращать `deduplicated`, не создавать вторую задачу.

---

#### FIX-4: Добавить `IRR_STATE_SNAPSHOT` в seeder или сделать startup handler более resilient

**Проблема:** BUG-DB-4 + BUG-AE-2
**Причина:** `startup` handler требует хотя бы одно `IRR_STATE_SNAPSHOT` событие в `zone_events`. В dev-окружении таких событий нет вообще.

**Два варианта (выбрать один или оба):**

**Вариант A: Graceful fallback в startup handler**
Если нет `IRR_STATE_SNAPSHOT` за последние N секунд — не падать с `TaskExecutionError`, а:
- Логировать предупреждение
- Считать, что `pump_main = False` (безопасное состояние по умолчанию)
- Продолжить startup workflow

**Файл:** `ae3lite/application/handlers/startup.py` — метод `_probe_irr_state()`

**Вариант B: Добавить начальные IRR_STATE события в seeder**
В `AutomationEngineE2ESeeder.php` или новом seeder добавить insert в `zone_events`:
```php
DB::table('zone_events')->insert([
    'zone_id' => $zoneId,
    'type' => 'IRR_STATE_SNAPSHOT',
    'payload_json' => json_encode([
        'pump_main' => false,
        'valve_clean_fill' => false,
        // ... все остальные поля false
    ]),
    'created_at' => now(),
    'updated_at' => now(),
]);
```

**Рекомендация:** Реализовать оба варианта — A как safeguard, B для dev-окружения.

---

### БЛОК 2: Frontend — отображение состояния автоматики

---

#### FIX-5: Добавить `error_code`, `error_message`, `workflow_phase`, `current_stage` в тип `AutomationState`

**Проблема:** BUG-FE-1 + BUG-FE-3
**Причина:** TypeScript тип не содержит полей для ошибки и текущей стадии.

**Что нужно сделать:**

В `resources/js/types/Automation.ts` расширить интерфейс `AutomationState`:

```typescript
export interface AutomationState {
  // ... существующие поля ...
  state_details: {
    started_at: string | null
    elapsed_sec: number
    progress_percent: number
    failed?: boolean
    error_code?: string | null      // ← NEW: код ошибки (ae3_task_execution_failed и т.д.)
    error_message?: string | null   // ← NEW: человекочитаемое сообщение
  }
  workflow_phase?: string | null    // ← NEW: idle/tank_filling/tank_recirc/ready/error
  current_stage?: string | null     // ← NEW: startup/clean_fill_check/solution_fill_check/...
  // ... остальные поля ...
}
```

**Файл:** `backend/laravel/resources/js/types/Automation.ts:42-83`

---

#### FIX-6: Отображать `error_code`/`error_message` в UI при ошибке

**Проблема:** BUG-FE-1 + BUG-FE-2
**Причина:** Когда задача failed, пользователь видит `IDLE` ("Ожидание") без какой-либо информации об ошибке.

**Что нужно сделать:**

1. **В `Ae3WorkflowStatusCard.vue`** или **`AutomationWorkflowCard.vue`** — добавить блок отображения ошибки:
   - Если `state_details.failed === true` — показывать красный banner с `error_message`
   - Если `error_code` содержит `no_active_zone_automation_logic_profile` — показывать специфичную подсказку: "Зона не настроена. Добавьте профиль автоматизации."

2. **В `AutomationStatusHeader.vue`** (строки 23-34) — убедиться, что блок ошибок показывает текст из `error_message`, а не только generic "Ошибка выполнения".

3. **В `useAutomationPanel.ts`** — в методе обнаружения failed-состояния (строки 637-647) — читать `error_code` и `error_message` из состояния.

**Файлы:**
- `resources/js/Components/Ae3WorkflowStatusCard.vue`
- `resources/js/Components/AutomationWorkflowCard.vue`
- `resources/js/Components/AutomationStatusHeader.vue`
- `resources/js/composables/useAutomationPanel.ts`

---

#### FIX-7: Отображать `current_stage` и `workflow_phase` в UI

**Проблема:** BUG-FE-3
**Причина:** Поля приходят с backend, но нигде не отображаются — пользователь не видит на каком шаге находится цикл.

**Что нужно сделать:**

В `Ae3WorkflowStatusCard.vue` добавить отображение текущей стадии:
- Маппинг `current_stage` → человекочитаемое название (startup → "Инициализация", clean_fill_check → "Наполнение чистой водой", solution_fill_check → "Наполнение раствором", prepare_recirculation_check → "Подготовка рециркуляции")
- Маппинг `workflow_phase` → Badge/пиктограмма (цвет по фазе)

**Файлы:**
- `resources/js/Components/Ae3WorkflowStatusCard.vue`
- `resources/js/types/Automation.ts` — добавить type `AutomationCurrentStage`

---

#### FIX-8: Исправить `buildCompatibilityStateFromControlMode` — читать последнюю задачу из БД

**Проблема:** BUG-FE-5
**Причина:** Fallback-метод в Laravel-контроллере всегда возвращает `failed: false`. Когда `/state` не существует (сейчас всегда), frontend не знает о реальных ошибках.

**Временное решение** (до реализации FIX-2):
Добавить в `ZoneAutomationStateController` метод `fetchLastTaskStateFromDatabase()`:
```php
private function fetchLastTaskStateFromDatabase(int $zoneId): ?array
{
    $task = DB::table('ae_tasks')
        ->where('zone_id', $zoneId)
        ->whereIn('status', ['running', 'waiting_command', 'failed', 'pending'])
        ->orderByDesc('created_at')
        ->first(['status', 'current_stage', 'workflow_phase', 'error_code', 'error_message']);

    if (!$task) return null;

    return [
        'task_status' => $task->status,
        'current_stage' => $task->current_stage,
        'workflow_phase' => $task->workflow_phase,
        'failed' => $task->status === 'failed',
        'error_code' => $task->error_code,
        'error_message' => $task->error_message,
    ];
}
```

Использовать результат в `buildCompatibilityStateFromControlMode()` для заполнения `state_details` и `state`.

**Файл:** `backend/laravel/app/Http/Controllers/ZoneAutomationStateController.php`

---

#### FIX-9: Показывать timestamp последнего обновления для всех данных (не только stale)

**Проблема:** BUG-FE-4
**Причина:** `served_at` уже есть в `state_meta`, но отображается в UI только для stale/cache. Live-данные не имеют timestamp'а, и пользователь не знает, насколько актуальна информация.

**Что нужно сделать:**

В `AutomationWorkflowCard.vue` — показывать "Обновлено: NN сек назад" для всех состояний, не только для кеша. Threshold:
- < 30 сек → зелёный, не акцентировать
- 30–60 сек → жёлтый, лёгкий предупреждающий вид
- > 60 сек → оранжевый, явный badge "данные устарели"

**Файл:** `resources/js/Components/AutomationWorkflowCard.vue`

---

### БЛОК 3: Производительность и надёжность AE

---

#### FIX-10: Уменьшить `telemetry_max_age_sec` default до разумного значения

**Проблема:** BUG-AE-7
**Причина:** Default 300 секунд (5 минут). Решения по уровням резервуаров принимаются на основе данных 5-минутной давности — это опасно.

**Что нужно сделать:**

В `ae3lite/domain/services/two_tank_runtime_spec.py` изменить default:
```python
telemetry_max_age_sec = int(cfg.get("telemetry_max_age_sec", 60))  # было 300
```

Или параметризовать через env-переменную `AE_TELEMETRY_MAX_AGE_SEC`.

**Файл:** `backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py`

---

#### FIX-11: Добавить lease heartbeat

**Проблема:** BUG-AE-6
**Причина:** Zone lease имеет фиксированный TTL. Долгие workflow-шаги (например, clean_fill с timeout 1200 сек) могут превысить TTL, и другой worker теоретически захватит зону.

**Что нужно сделать:**

В `ae3lite/runtime/worker.py` добавить фоновый coroutine для продления lease во время execute:
```python
async def _lease_heartbeat(zone_id, owner, interval_sec=30):
    while True:
        await asyncio.sleep(interval_sec)
        await zone_lease_repository.extend(zone_id=zone_id, owner=owner, extend_by_sec=60)
```

**Файл:** `backend/services/automation-engine/ae3lite/runtime/worker.py`

---

## Приоритизация

| Приоритет | Фиксы | Результат |
|-----------|-------|---------|
| **P0 — Сейчас** | FIX-1, FIX-4 (Вариант B) | Задачи перестают падать сразу при запуске |
| **P1 — Краткосрочно** | FIX-2, FIX-3, FIX-8 | AE отдаёт реальное состояние; нет race conditions |
| **P2 — UI** | FIX-5, FIX-6, FIX-7, FIX-9 | Пользователь видит ошибки и текущую стадию |
| **P3 — Надёжность** | FIX-10, FIX-11, FIX-4 Вариант A | Устойчивость к сбоям сенсоров и долгим операциям |

---

## Критерии приёмки

1. **После FIX-1 + FIX-4B:** `make seed && make test` — все задачи должны проходить стадию `startup` без ошибки профиля
2. **После FIX-2 + FIX-3:** Повторный `POST /zones/1/start-cycle` возвращает `deduplicated`; в `ae_tasks` одна задача на зону
3. **После FIX-5 + FIX-6:** Открыть зону в UI при наличии failed-задачи — должен отображаться красный banner с текстом ошибки
4. **После всех P0+P1 фиксов:** E2E тест two_tank (E83/E84/E85) должен проходить
5. **Нет регрессий:** `make test` — все PHP и Python тесты green

---

## Связанные файлы (ключевые пути)

```
# AE Python
backend/services/automation-engine/ae3lite/runtime/app.py:305
backend/services/automation-engine/ae3lite/application/use_cases/create_task_from_intent.py
backend/services/automation-engine/ae3lite/application/use_cases/get_zone_control_state.py
backend/services/automation-engine/ae3lite/application/handlers/startup.py
backend/services/automation-engine/ae3lite/domain/services/two_tank_runtime_spec.py

# Laravel Backend
backend/laravel/app/Http/Controllers/ZoneAutomationStateController.php:133-238
backend/laravel/database/seeders/LiteAutomationSeeder.php
backend/laravel/database/seeders/AutomationEngineE2ESeeder.php

# Frontend
backend/laravel/resources/js/types/Automation.ts:42-83
backend/laravel/resources/js/Components/Ae3WorkflowStatusCard.vue
backend/laravel/resources/js/Components/AutomationWorkflowCard.vue
backend/laravel/resources/js/Components/AutomationStatusHeader.vue
backend/laravel/resources/js/composables/useAutomationPanel.ts:637-647
```
