# AE3-Lite: Полный переход + Полноценный ручной режим

**Версия:** 1.0
**Дата:** 2026-03-09
**Статус:** PLAN — не реализован
**Автор анализа:** на основе аудита кодовой базы

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 0. Состояние на старте

### Что уже сделано
- Python `automation-engine` — **100% AE3-Lite**. Кода AE2-Lite нет.
- Реализованы стадии: `startup → clean_fill → solution_fill → prepare_recirc → ready`
- 11-шаговая FSM коррекции pH/EC работает.
- `ae_tasks`, `ae_commands`, `ae_zone_leases`, `ae_stage_transitions` — в production.

### Что сломано / не реализовано
| Компонент | Проблема |
|-----------|---------|
| `zones.automation_runtime` | DEFAULT = `'ae2'`, новые зоны создаются на несуществующем runtime |
| `ResolvesAutomationRuntime.php` | fallback → `'ae2'` при DB ошибке |
| `ZoneController.php` | принимает `automation_runtime='ae2'` |
| `ZoneAutomationControlModeController.php` | прокси → AE; AE возвращает 404/501 |
| `ZoneAutomationManualStepController.php` | прокси → AE; AE возвращает 404/501 |
| Frontend (47 мест) | кнопки "Ручной режим" и "Ручной шаг" мёртвые |
| `AutomationStateType` в TS | `IRRIGATING`, `IRRIG_RECIRC` — AE2 фазы, не существуют в AE3 |
| `WorkflowStageCode` в TS | `irrigating`, `irrig_recirc` — то же |

---

## 1. Концепция ручного режима для AE3-Lite

### 1.1 Три режима управления

| Режим | Поведение |
|-------|-----------|
| `auto` | Полностью автоматический. Текущее поведение worker-а. |
| `semi` | Выполняет command-стадии автоматически, но перед каждой новой фазой наполнения ждёт подтверждения оператора. |
| `manual` | На check-стадиях не переходит автоматически — ждёт явного `pending_manual_step`. Команды старта/стопа выдаёт только по указанию оператора. |

### 1.2 Где хранится `control_mode`

**`zones.control_mode`** — постоянная колонка. Живёт вне задачи, применяется немедленно.

Рациональные: оператор может переключить режим прямо во время исполнения задачи.
`ZoneSnapshot` читает `zones.control_mode` при каждом тике — изменение применяется на следующем тике.

### 1.3 Механизм `pending_manual_step`

**`ae_tasks.pending_manual_step`** — nullable VARCHAR(64).

Алгоритм:
1. Оператор отправляет `POST /zones/{id}/manual-step` с `{ "manual_step": "clean_fill_stop" }`.
2. Laravel валидирует шаг, проверяет что шаг допустим для текущей стадии.
3. Laravel делает `POST http://automation-engine:9405/zones/{id}/manual-step`.
4. AE выполняет атомарный `UPDATE ae_tasks SET pending_manual_step = $1 WHERE zone_id = $2 AND status IN (...)`.
5. На следующем тике worker читает `pending_manual_step` из задачи.
6. Handler-чек видит `pending_manual_step` → выполняет соответствующий переход → сбрасывает `pending_manual_step = NULL`.

### 1.4 Маппинг manual_step → stage transition

| `manual_step` | Допустимые stage-контексты | Переход в `next_stage` |
|---|---|---|
| `clean_fill_start` | `startup` (если режим semi/manual) | `clean_fill_start` |
| `clean_fill_stop` | `clean_fill_check` | `clean_fill_stop_to_solution` |
| `solution_fill_start` | `startup` (clean tank полон) или после `clean_fill` в semi | `solution_fill_start` |
| `solution_fill_stop_to_ready` | `solution_fill_check` | `solution_fill_stop_to_ready` |
| `solution_fill_stop_to_prepare` | `solution_fill_check` | `solution_fill_stop_to_prepare` |
| `prepare_recirculation_start` | после `solution_fill_stop_to_prepare` в semi | `prepare_recirculation_start` |
| `prepare_recirculation_stop_to_ready` | `prepare_recirculation_check` | `prepare_recirculation_stop_to_ready` |

### 1.5 `allowed_manual_steps` — что разрешено в текущей стадии

Вычисляется runtime-ом на `GET /zones/{id}/control-mode`:

| Стадия (`current_stage`) | `allowed_manual_steps` |
|---|---|
| `startup` | `['clean_fill_start', 'solution_fill_start']` (semi/manual) |
| `clean_fill_check` | `['clean_fill_stop']` |
| `solution_fill_check` | `['solution_fill_stop_to_ready', 'solution_fill_stop_to_prepare']` |
| `prepare_recirculation_check` | `['prepare_recirculation_stop_to_ready']` |
| Все command-стадии (`*_start`, `*_stop_*`) | `[]` — нельзя прерывать |
| `complete_ready` | `[]` |

### 1.6 Поведение в `semi` режиме

В `semi` режиме worker автоматически:
- Выполняет все command-стадии
- Выполняет `startup`

Но **паузит** перед:
- `clean_fill_start` (ждёт `pending_manual_step='clean_fill_start'`)
- `solution_fill_start` (ждёт `pending_manual_step='solution_fill_start'`)
- `prepare_recirculation_start` (ждёт `pending_manual_step='prepare_recirculation_start'`)

То есть в `semi` — check-стадии по-прежнему автоматические, но переход к каждой новой фазе — ручной.

---

## 2. Архитектурные решения

### 2.1 Изменения схемы данных

**Таблица `zones`** — добавить:
```sql
control_mode VARCHAR(16) NOT NULL DEFAULT 'auto'
  CHECK (control_mode IN ('auto', 'semi', 'manual'))
```

**Таблица `ae_tasks`** — добавить:
```sql
pending_manual_step VARCHAR(64) NULL  -- шаг, ожидающий выполнения
control_mode_snapshot VARCHAR(16) NULL  -- снимок режима на момент создания задачи
```

> `control_mode_snapshot` нужен для `GET /zones/{id}/control-mode` — чтобы показать режим активной задачи.

### 2.2 `ZoneSnapshot` — новое поле

```python
@dataclass(frozen=True)
class ZoneSnapshot:
    ...
    control_mode: str  # 'auto' | 'semi' | 'manual', читается из zones.control_mode
```

### 2.3 `WorkflowState` — расширение

```python
@dataclass(frozen=True)
class WorkflowState:
    current_stage: str
    workflow_phase: str
    stage_deadline_at: Optional[datetime]
    stage_retry_count: int
    stage_entered_at: Optional[datetime]
    clean_fill_cycle: int
    control_mode: str = "auto"       # из zones.control_mode (snapshotted per tick)
    pending_manual_step: Optional[str] = None  # из ae_tasks.pending_manual_step
```

### 2.4 Логика в check-handler-ах

Каждый check-handler получает `task.workflow.control_mode` и `task.workflow.pending_manual_step`.

```python
# Пример: SolutionFillCheckHandler.run()

if control_mode in ('semi', 'manual'):
    if pending_manual_step is None:
        # Нет команды — ждём оператора
        return StageOutcome(kind="poll", due_delay_sec=5)

    if pending_manual_step == 'solution_fill_stop_to_ready':
        return StageOutcome(kind="transition", next_stage="solution_fill_stop_to_ready")

    if pending_manual_step == 'solution_fill_stop_to_prepare':
        return StageOutcome(kind="transition", next_stage="solution_fill_stop_to_prepare")

    # Неизвестный шаг — игнорируем (безопасно)
    return StageOutcome(kind="poll", due_delay_sec=5)

# auto режим — обычная логика проверки уровня
...
```

### 2.5 `StageDef` — новое поле `semi_pause`

```python
@dataclass(frozen=True)
class StageDef:
    ...
    semi_pause: bool = False  # В semi-режиме: ждать pending_manual_step перед входом
```

`StartupHandler` проверяет: если `control_mode='semi'` и `semi_pause=True` у следующей стадии — возвращает `poll` вместо `transition`.

Стадии с `semi_pause=True`: `clean_fill_start`, `solution_fill_start`, `prepare_recirculation_start`.

### 2.6 Новые Python use cases

```
ae3lite/application/use_cases/
  set_control_mode.py        # SetControlModeUseCase
  request_manual_step.py     # RequestManualStepUseCase
  get_zone_control_state.py  # GetZoneControlStateUseCase
```

### 2.7 Новые API endpoints в AE3-Lite

```
GET  /zones/{id}/control-mode
     → {control_mode, allowed_manual_steps, current_stage, workflow_phase}

POST /zones/{id}/control-mode
     → body: {control_mode: 'auto'|'semi'|'manual'}
     → 200: {control_mode, allowed_manual_steps}

POST /zones/{id}/manual-step
     → body: {manual_step: str}
     → валидация: шаг допустим для текущей стадии
     → атомарный UPDATE ae_tasks SET pending_manual_step = $1
     → 200: {task_id, pending_manual_step}
     → 409: если нет активной задачи
     → 422: если шаг недопустим для текущей стадии
```

---

## 3. Этапы реализации

### Этап 0 — Подготовка (P0, без кода AE)

**Цель:** очистить легаси-слой, переключить все зоны на AE3.

#### 0.1 DB migration: migrate zones to ae3 + control_mode
```php
// 2026_XX_XX_000000_full_ae3_cutover.php

// 1. Добавить control_mode в zones
$table->string('control_mode', 16)->default('auto')
      ->after('automation_runtime');
DB::statement("ALTER TABLE zones ADD CONSTRAINT zones_control_mode_check
               CHECK (control_mode IN ('auto', 'semi', 'manual'))");

// 2. Мигрировать все зоны на ae3
DB::statement("UPDATE zones SET automation_runtime = 'ae3'
               WHERE automation_runtime = 'ae2'");
DB::statement("ALTER TABLE zones ALTER COLUMN automation_runtime SET DEFAULT 'ae3'");
DB::statement("ALTER TABLE zones DROP CONSTRAINT IF EXISTS zones_automation_runtime_check");
DB::statement("ALTER TABLE zones ADD CONSTRAINT zones_automation_runtime_check
               CHECK (automation_runtime IN ('ae3'))");
```

#### 0.2 DB migration: добавить поля в ae_tasks
```php
// 2026_XX_XX_000001_ae3_manual_mode_task_fields.php

$table->string('pending_manual_step', 64)->nullable()->after('corr_wait_until');
$table->string('control_mode_snapshot', 16)->nullable()->after('pending_manual_step');
```

#### 0.3 Laravel PHP cleanup
- `ResolvesAutomationRuntime.php`: fallback `'ae2'` → `'ae3'`
- `ZoneController.php`: `in:ae2,ae3` → `in:ae3`
- Удалить `ZoneAutomationControlModeController.php` (будет заменён в Этапе 1)
- Удалить `ZoneAutomationManualStepController.php` (будет заменён в Этапе 1)
- Routes временно удалить (вернутся в Этапе 1)

#### 0.4 Тесты
- `AutomationDispatchSchedulesCommandTest.php` — `'ae2'` → `'ae3'`
- `SchedulerCycleServiceTest.php` — `'ae2'` → `'ae3'`
- `Ae3LiteSchemaTest.php` — обновить проверку DEFAULT
- `Ae3LiteRuntimeSwitchGuardTest.php` — обновить `'ae2'` → `'ae3'`

**Критерий приёмки этапа 0:**
- `SELECT COUNT(*) FROM zones WHERE automation_runtime != 'ae3'` = 0
- Все Laravel тесты зелёные

---

### Этап 1 — Python: ZoneSnapshot + control_mode read (P0)

**Цель:** AE3-Lite читает `control_mode` из `zones` и отдаёт через `GET /zones/{id}/control-mode`.

#### 1.1 `zone_snapshot_read_model.py`
Добавить в SQL-запрос:
```sql
z.control_mode
```
Добавить поле в `ZoneSnapshot`:
```python
control_mode: str  # 'auto' | 'semi' | 'manual'
```

#### 1.2 `GetZoneControlStateUseCase`
```python
class GetZoneControlStateUseCase:
    async def run(self, *, zone_id: int) -> dict:
        # Читает zones.control_mode + ae_tasks.current_stage + pending_manual_step
        # Возвращает allowed_manual_steps на основе текущей стадии
```

#### 1.3 API endpoint `GET /zones/{id}/control-mode`
```python
@router.get("/zones/{zone_id}/control-mode")
async def get_control_mode(zone_id: int):
    result = await get_zone_control_state_use_case.run(zone_id=zone_id)
    return {
        "data": {
            "zone_id": zone_id,
            "control_mode": result.control_mode,
            "current_stage": result.current_stage,
            "workflow_phase": result.workflow_phase,
            "allowed_manual_steps": result.allowed_manual_steps,
        }
    }
```

#### 1.4 Laravel: восстановить `ZoneAutomationControlModeController.php` (GET only)
- Только `show()` → прокси → AE `GET /zones/{id}/control-mode`
- `update()` вернётся в Этапе 3

**Критерий приёмки этапа 1:**
- `GET /api/zones/{id}/control-mode` → 200 с полем `control_mode`
- Frontend перестаёт показывать 501

---

### Этап 2 — Python: WorkflowState + ручной режим в handler-ах (P1)

**Цель:** `auto`-режим не меняется. `manual` и `semi` корректно паузят worker.

#### 2.1 `WorkflowState` — добавить поля
```python
@dataclass(frozen=True)
class WorkflowState:
    current_stage: str
    workflow_phase: str
    stage_deadline_at: Optional[datetime]
    stage_retry_count: int
    stage_entered_at: Optional[datetime]
    clean_fill_cycle: int
    control_mode: str = "auto"
    pending_manual_step: Optional[str] = None
```

#### 2.2 `AutomationTask.from_row()` — читать новые колонки
```python
WorkflowState(
    ...
    control_mode=str(row.get("control_mode_snapshot") or row.get("control_mode") or "auto"),
    pending_manual_step=row.get("pending_manual_step"),
)
```

#### 2.3 `StageDef` — добавить `semi_pause: bool = False`
Стадии с `semi_pause=True`:
- `clean_fill_start`
- `solution_fill_start`
- `prepare_recirculation_start`

#### 2.4 `StartupHandler` — учёт `semi_pause`
```python
async def run(self, *, task, plan, stage_def, now):
    ...
    next_stage = "clean_fill_start" if not clean_max else "solution_fill_start"
    next_def = registry.get(topology, next_stage)

    control_mode = task.workflow.control_mode
    pending = task.workflow.pending_manual_step

    if next_def.semi_pause and control_mode in ('semi', 'manual'):
        if pending != next_stage_step_name:
            return StageOutcome(kind="poll", due_delay_sec=5)

    return StageOutcome(kind="transition", next_stage=next_stage)
```

#### 2.5 Check-handler-ы: `CleanFillCheckHandler`, `SolutionFillCheckHandler`, `PrepareRecircCheckHandler`
Добавить в начало `run()`:

```python
control_mode = task.workflow.control_mode
pending = task.workflow.pending_manual_step

if control_mode == 'manual':
    if pending is None:
        return StageOutcome(kind="poll", due_delay_sec=5)
    # Обработка конкретного шага ниже в теле handler-а
```

Каждый handler знает свои допустимые `pending_manual_step` значения (из `ALLOWED_STEPS` константы).

#### 2.6 `PgAutomationTaskRepository` — метод `set_pending_manual_step()`
```python
async def set_pending_manual_step(
    self, *, zone_id: int, step: str
) -> Optional[AutomationTask]:
    """Атомарно устанавливает pending_manual_step для активной задачи зоны."""
    # UPDATE ae_tasks SET pending_manual_step = $1, updated_at = NOW()
    # WHERE zone_id = $2
    #   AND status IN ('pending', 'claimed', 'running', 'waiting_command')
    # RETURNING *
```

#### 2.7 `WorkflowRouter` — сброс `pending_manual_step` после перехода
При применении outcome типа `transition` или `exit_correction`:
```python
# В _apply_transition():
# Если был pending_manual_step — он "использован", сбросить в NULL
await self._task_repo.clear_pending_manual_step(task_id=task.id)
```

#### 2.8 Тесты Python (новые)
```
test_ae3lite_manual_mode_clean_fill.py
test_ae3lite_manual_mode_solution_fill.py
test_ae3lite_manual_mode_prepare_recirc.py
test_ae3lite_semi_mode_pause_at_start.py
test_ae3lite_set_pending_manual_step.py
```

**Критерий приёмки этапа 2:**
- В `manual` режиме worker не переходит автоматически на check-стадиях
- В `semi` режиме worker паузит перед `clean_fill_start`, `solution_fill_start`, `prepare_recirculation_start`
- В `auto` режиме поведение не изменилось (регрессионные тесты зелёные)

---

### Этап 3 — Python: SetControlMode + RequestManualStep API (P1)

#### 3.1 `SetControlModeUseCase`
```python
class SetControlModeUseCase:
    """Обновляет zones.control_mode + snapshot в активной задаче."""

    async def run(self, *, zone_id: int, control_mode: str) -> dict:
        # UPDATE zones SET control_mode = $1 WHERE id = $2
        # Если есть активная ae_task — обновить control_mode_snapshot тоже
        # Записать zone_event AUTOMATION_CONTROL_MODE_UPDATED
        # Вернуть {control_mode, current_stage, allowed_manual_steps}
```

#### 3.2 `RequestManualStepUseCase`
```python
class RequestManualStepUseCase:
    """Устанавливает pending_manual_step для активной задачи зоны."""

    ALLOWED_STEPS_BY_STAGE: dict[str, list[str]] = {
        "startup":                        ["clean_fill_start", "solution_fill_start"],
        "clean_fill_check":               ["clean_fill_stop"],
        "solution_fill_check":            ["solution_fill_stop_to_ready",
                                           "solution_fill_stop_to_prepare"],
        "prepare_recirculation_check":    ["prepare_recirculation_stop_to_ready"],
        "clean_fill_start":               [],  # command-стадии нельзя прерывать
        "solution_fill_start":            [],
        "prepare_recirculation_start":    [],
        # ... остальные command-стадии = []
    }

    async def run(self, *, zone_id: int, manual_step: str) -> dict:
        task = await self._task_repo.get_active_for_zone(zone_id=zone_id)
        if task is None:
            raise ManualStepError("no_active_task", "Нет активной задачи")

        allowed = self.ALLOWED_STEPS_BY_STAGE.get(task.current_stage, [])
        if manual_step not in allowed:
            raise ManualStepError(
                "step_not_allowed",
                f"Шаг '{manual_step}' недопустим в стадии '{task.current_stage}'"
            )

        updated = await self._task_repo.set_pending_manual_step(
            zone_id=zone_id, step=manual_step
        )
        # Kick worker
        self._worker.kick()
        return {"task_id": task.id, "pending_manual_step": manual_step}
```

#### 3.3 API endpoints в AE3-Lite

```python
@router.post("/zones/{zone_id}/control-mode")
async def set_control_mode(zone_id: int, body: SetControlModeRequest):
    # body: {control_mode: 'auto'|'semi'|'manual'}
    result = await set_control_mode_use_case.run(
        zone_id=zone_id, control_mode=body.control_mode
    )
    # Записать zone_event AUTOMATION_CONTROL_MODE_UPDATED → WebSocket push
    return {"data": result}

@router.post("/zones/{zone_id}/manual-step")
async def request_manual_step(zone_id: int, body: ManualStepRequest):
    # body: {manual_step: str, source?: str}
    result = await request_manual_step_use_case.run(
        zone_id=zone_id, manual_step=body.manual_step
    )
    return {"data": result}
```

#### 3.4 Laravel: восстановить контроллеры

`ZoneAutomationControlModeController.php`:
- `show()` → прокси `GET /zones/{id}/control-mode` (уже из Этапа 1)
- `update()` → прокси `POST /zones/{id}/control-mode`

`ZoneAutomationManualStepController.php`:
- `store()` → прокси `POST /zones/{id}/manual-step`

Routes в `api.php`:
```php
Route::get('zones/{zone}/control-mode', [ZoneAutomationControlModeController::class, 'show']);
Route::post('zones/{zone}/control-mode', [ZoneAutomationControlModeController::class, 'update'])
    ->middleware('role:operator,admin,agronomist,engineer');
Route::post('zones/{zone}/manual-step', [ZoneAutomationManualStepController::class, 'store'])
    ->middleware('role:operator,admin,agronomist,engineer');
```

**Критерий приёмки этапа 3:**
- `POST /api/zones/{id}/control-mode` обновляет режим в БД
- `POST /api/zones/{id}/manual-step` устанавливает pending шаг
- В manual-режиме worker ждёт → оператор отправляет шаг → worker выполняет

---

### Этап 4 — Frontend: обновление типов и UI (P1)

#### 4.1 `Automation.ts` — исправить типы

```typescript
// Удалить AE2-фазы:
// export type AutomationStateType = 'IDLE' | 'TANK_FILLING' | 'TANK_RECIRC' | 'READY'
//   | 'IRRIGATING' | 'IRRIG_RECIRC'  ← УДАЛИТЬ

// Актуальные AE3-фазы:
export type AutomationStateType =
  | 'IDLE'
  | 'TANK_FILLING'
  | 'TANK_RECIRC'
  | 'READY'
  | 'ERROR'

// Актуальные manual steps (добавить новые из RequestManualStepUseCase):
export type AutomationManualStep =
  | 'clean_fill_start'
  | 'clean_fill_stop'
  | 'solution_fill_start'
  | 'solution_fill_stop_to_ready'
  | 'solution_fill_stop_to_prepare'
  | 'prepare_recirculation_start'
  | 'prepare_recirculation_stop_to_ready'

// WorkflowStageCode — удалить IRRIGATING, IRRIG_RECIRC:
export type WorkflowStageCode = 'tank_filling' | 'tank_recirc' | 'ready' | 'error'
```

#### 4.2 `useZoneAutomationScheduler.ts` — исправить manual step loading map

```typescript
const manualStepLoading = ref<Record<AutomationManualStep, boolean>>({
  clean_fill_start: false,
  clean_fill_stop: false,
  solution_fill_start: false,
  solution_fill_stop_to_ready: false,
  solution_fill_stop_to_prepare: false,
  prepare_recirculation_start: false,
  prepare_recirculation_stop_to_ready: false,
})
```

#### 4.3 Компоненты UI

Если существует компонент с кнопками ручного шага — обновить список шагов под новые типы.
Добавить label-ы для новых шагов в i18n/форматтерах:
```
solution_fill_stop_to_ready → 'Завершить наполнение (переход в READY)'
solution_fill_stop_to_prepare → 'Завершить наполнение (→ рециркуляция)'
prepare_recirculation_stop_to_ready → 'Завершить рециркуляцию (→ READY)'
```

#### 4.4 WebSocket: новый event kind

`AUTOMATION_CONTROL_MODE_UPDATED` уже обрабатывается в `shouldRefreshByGlobalKind()` — ничего добавлять не нужно.

Убедиться что `MANUAL_STEP_*` события корректно обрабатываются (код уже есть).

---

### Этап 5 — Итоговый cleanup (P2)

После стабилизации всех этапов:

1. Удалить `IRRIGATING`, `IRRIG_RECIRC` из любых оставшихся мест в коде/тестах.
2. Убедиться что DB CHECK constraint содержит только `('ae3')`.
3. Удалить `ae2` из любых enum-ов, валидаций, документации.
4. Провести cleanup-аудит: `grep -rn "ae2" backend/ --include="*.php" --include="*.ts" --include="*.vue"`.
5. Обновить `doc_ai/04_BACKEND_CORE/ae3lite.md` — добавить секцию про manual mode.
6. Обновить `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — новые endpoints.

---

## 4. Новые файлы (Python)

```
ae3lite/application/use_cases/
  set_control_mode.py
  request_manual_step.py
  get_zone_control_state.py

ae3lite/domain/errors.py
  + ManualStepError (новый класс ошибки)

ae3lite/infrastructure/repositories/
  automation_task_repository.py
  + set_pending_manual_step()
  + clear_pending_manual_step()
  + update_control_mode_snapshot()

ae3lite/runtime/
  serve.py (или app.py)
  + POST /zones/{id}/control-mode
  + POST /zones/{id}/manual-step
  (GET /zones/{id}/control-mode уже или добавляется здесь)
```

---

## 5. Новые файлы (Laravel)

```
app/Http/Controllers/
  ZoneAutomationControlModeController.php  ← обновить (уже есть)
  ZoneAutomationManualStepController.php   ← обновить (уже есть)

database/migrations/
  2026_XX_XX_000000_full_ae3_cutover.php
  2026_XX_XX_000001_ae3_manual_mode_task_fields.php
```

---

## 6. Новые тесты

```
# Python
test_ae3lite_manual_mode_clean_fill.py
test_ae3lite_manual_mode_solution_fill.py
test_ae3lite_manual_mode_prepare_recirc.py
test_ae3lite_semi_mode_startup_pause.py
test_ae3lite_set_control_mode_use_case.py
test_ae3lite_request_manual_step_use_case.py
test_ae3lite_control_mode_api.py
test_ae3lite_manual_step_api.py

# Laravel
tests/Feature/ZoneAutomationControlModeControllerTest.php  ← обновить
tests/Feature/ZoneAutomationManualStepControllerTest.php   ← обновить
```

---

## 7. Полный порядок выполнения

```
Этап 0: DB migration + Laravel PHP cleanup + тесты
    ↓
Этап 1: Python GET /control-mode (read-only) + Laravel GET прокси
    ↓
Этап 2: Python manual/semi логика в handler-ах
    ↓
Этап 3: Python SET + STEP API + Laravel POST прокси
    ↓
Этап 4: Frontend типы + UI
    ↓
Этап 5: Финальный cleanup + документация
```

---

## 8. Критерии приёмки всего плана

- [ ] `SELECT COUNT(*) FROM zones WHERE automation_runtime != 'ae3'` = 0
- [ ] `SELECT COUNT(*) FROM zones WHERE control_mode NOT IN ('auto','semi','manual')` = 0
- [ ] В `auto` режиме: workflow работает идентично текущему (регрессия)
- [ ] В `manual` режиме: worker паузит на check-стадиях без `pending_manual_step`
- [ ] В `manual` режиме: после `POST /manual-step` worker продолжает и очищает `pending_manual_step`
- [ ] В `semi` режиме: worker паузит перед `clean_fill_start`, `solution_fill_start`, `prepare_recirculation_start`
- [ ] `GET /api/zones/{id}/control-mode` возвращает `allowed_manual_steps` для текущей стадии
- [ ] `POST /api/zones/{id}/control-mode` обновляет режим в БД + WebSocket push
- [ ] `POST /api/zones/{id}/manual-step` → 422 для недопустимого шага
- [ ] `POST /api/zones/{id}/manual-step` → 409 при отсутствии активной задачи
- [ ] Frontend: кнопки ручного шага активны только когда режим = manual и шаг допустим
- [ ] Frontend: нет TS ошибок по типам Automation
- [ ] Все Laravel тесты зелёные
- [ ] Все Python тесты зелёные (~460+ тестов)

---

## 9. Связанные документы

- `ae3lite.md` — канонический spec AE3-Lite
- `AE3_FULL_MIGRATION_PLAN.md` — предыдущий план (DB/Laravel cleanup)
- `CORRECTION_CYCLE_SPEC.md` — FSM коррекции pH/EC
- `PYTHON_SERVICES_ARCH.md` — архитектура сервисов
