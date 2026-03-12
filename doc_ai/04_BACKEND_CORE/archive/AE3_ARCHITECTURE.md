# AE3: Архитектура Automation Engine v3 (ARCHIVED)

> **Статус:** ARCHIVED (historical reference)
> **Ветка:** ae3
> **Дата:** 2026-03-05

Архивная копия. Нормативный документ AE3: `doc_ai/04_BACKEND_CORE/ae3lite.md`.

## 0. Нормативный compatibility-контракт (до code cutover)

Этот документ приведен к контрактам `AE3_C.md` и текущей реализации AE2-Lite.
При конфликте формулировок внутри документа приоритет у этого раздела.

1. Внешний wake-up: `POST /zones/{id}/start-cycle` (canonical до migration gate).
2. Внешний scheduler `task_type` до cutover: `irrigation`, `lighting`, `ventilation`, `solution_change`, `mist`, `diagnostics`.
3. `POST /internal/tasks/enqueue` — internal runtime endpoint; внешний scheduler использует его только после `AE3C_ENABLE_SCHEDULER_DIRECT_ENQUEUE=1` и canary gate.
4. Poller compatibility обязателен: `task_id=intent-<id>` + legacy statuses `accepted|completed|failed|cancelled|not_found`.
5. Dual-run `zone_automation_intents <-> ae_tasks` и interlock против split-brain writer обязательны в transition.
6. Для actuator-команд success = только terminal `DONE` (`NO_EFFECT` трактуется как fail).
7. PID state contract: `last_output_ms`, `last_dose_at`, `prev_derivative`, `current_zone` (без несовместимых rename).

## 1. Философия

**Главный принцип:** Automation Engine — это **реактивный исполнитель задач**, а не polling loop.

Текущая система (AE2) работает как непрерывный цикл с 15-секундным интервалом, который сам решает, что делать. AE3 переворачивает модель: **каждое действие запускается либо scheduler-ом, либо вручную через API**. AE3 не делает ничего, пока не получит задачу.

### Ключевые отличия от AE2

| Аспект | AE2 (текущая) | AE3 (новая) |
|--------|---------------|-------------|
| Модель выполнения | Polling loop 15 сек | Event-driven: задачи по запросу |
| Кто решает "что делать" | AE сам (внутренний цикл) | Scheduler (Laravel) + Manual API |
| Состояние зоны | Глобальные dict-ы в памяти | `ZoneContext` — изолированный объект на задачу |
| Workflow FSM | Мягкое (warning на невалидный переход) | Строгое (исключение на невалидный переход) |
| PID состояние | Глобальный `_pid_by_zone` dict | Персистентный в БД, загружается в `ZoneContext` |
| Контроллеры | 30+ callback-ов в функцию | Интерфейс `Controller` с методом `execute()` |
| Параллелизм | `asyncio.gather()` с Semaphore | Task queue с воркерами |

---

## 2. Обзор архитектуры

```
                    ┌──────────────────────┐
                    │   Laravel Scheduler   │
                    │  (cron / interval)    │
                    └─────────┬────────────┘
                              │ POST /zones/{id}/start-cycle
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    AE3 (Python, asyncio)                     │
│                                                             │
│  ┌─────────────┐    ┌──────────────┐    ┌───────────────┐  │
│  │  REST API    │───▶│  TaskRouter   │───▶│  TaskExecutor  │  │
│  │  (FastAPI)   │    │              │    │  (per zone)    │  │
│  └─────────────┘    └──────────────┘    └───────┬───────┘  │
│                                                  │          │
│       ┌──────────────────────────────────────────┤          │
│       │              │              │             │          │
│       ▼              ▼              ▼             ▼          │
│  ┌─────────┐   ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │Correction│   │Irrigation│  │ Climate  │  │ Lighting │   │
│  │Controller│   │Controller│  │Controller│  │Controller│   │
│  └────┬─────┘   └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │             │          │
│       └──────────────┴──────────────┴─────────────┘          │
│                          │                                   │
│                          ▼                                   │
│                 ┌────────────────┐                           │
│                 │   CommandBus    │                           │
│                 │ (history-logger)│                           │
│                 └────────────────┘                           │
└─────────────────────────────────────────────────────────────┘
```

### Потоки данных

```
1. Scheduler → POST /zones/{id}/start-cycle → Intent bridge → TaskRouter → TaskExecutor → Controllers → CommandBus → MQTT → ESP32
2. Manual   → POST /zones/{id}/manual-action → TaskRouter → ...то же самое
3. ESP32    → MQTT → history-logger → DB (telemetry) ← AE3 читает при выполнении задачи
```

---

## 3. Типы задач (Task Types)

До migration gate scheduler отправляет только legacy `task_type`, а AE3 planner маппит их во внутренние canonical задачи.

### 3.1 Полный список task types (internal canonical)

| task_type | Описание | Контроллер | Периодичность |
|-----------|----------|------------|---------------|
| `correction_ph` | Коррекция pH раствора | CorrectionController | 90-120 сек |
| `correction_ec` | Коррекция EC раствора | CorrectionController | 120-180 сек |
| `irrigation_start` | Запуск полива | IrrigationController | По расписанию |
| `irrigation_stop` | Остановка полива | IrrigationController | По таймеру |
| `recirculation_start` | Запуск рециркуляции | RecirculationController | После полива |
| `recirculation_stop` | Остановка рециркуляции | RecirculationController | По таймеру |
| `climate_check` | Проверка/коррекция климата | ClimateController | 60-300 сек |
| `lighting_check` | Проверка/управление светом | LightingController | 60 сек |
| `workflow_step` | Шаг two-tank workflow | WorkflowController | По событию |
| `health_check` | Проверка здоровья зоны | HealthController | 60 сек |
| `diagnostics` | Диагностика + запуск цикла | DiagnosticsController | По запросу |

Legacy -> canonical bridge (до direct enqueue):
- `irrigation` -> `irrigation_start/irrigation_stop/recirculation_*`
- `lighting` -> `lighting_check`
- `ventilation` -> `climate_check`
- `solution_change` -> `workflow_step/diagnostics`
- `mist` -> `climate_check`
- `diagnostics` -> `diagnostics + workflow_step`

### 3.2 Зависимости между задачами

```
diagnostics ──► workflow_step (startup)
                    │
                    ├──► workflow_step (clean_fill)
                    ├──► workflow_step (solution_fill)
                    ├──► workflow_step (prepare_recirc)
                    │
                    ▼
              [zone READY]
                    │
    ┌───────────────┼───────────────────┐
    ▼               ▼                   ▼
irrigation_start  climate_check    lighting_check
    │             (периодически)   (периодически)
    ▼
irrigation_stop
    │
    ▼
recirculation_start
    │               ┌───────────────┐
    ▼               ▼               │
recirculation_stop  correction_ph   │
                    correction_ec   │
                    (в разрешённых   │
                     фазах)         │
                         │          │
                         ▼          │
                    irrigation_start┘  (следующий цикл)
```

**Правило:** До scheduler direct-enqueue оркестрация цепочек выполняется planner-ом/runtime внутри AE (через intent bridge). После migration gate scheduler может планировать canonical задачи напрямую.

---

## 4. ZoneContext — единица состояния

Каждая задача получает изолированный `ZoneContext`. Нет глобальных dict-ов, нет shared mutable state.

### 4.1 Структура

```python
@dataclass
class ZoneContext:
    """Полный контекст зоны для выполнения одной задачи. Immutable после создания."""

    # Идентификация
    zone_id: int
    task_id: str
    task_type: str
    correlation_id: str
    task_payload: Dict[str, Any]  # payload из TaskRequest (workflow_step, duration_sec, ...)

    # Конфигурация (snapshot на момент задачи)
    zone_config: ZoneConfig           # из Laravel API / кэша
    targets: EffectiveTargets         # целевые значения из рецепта
    topology: str                     # "two_tank_drip_substrate_trays"
    grow_cycle_id: Optional[int]

    # Состояние workflow (из БД, загружается при создании контекста)
    workflow_phase: WorkflowPhase     # enum: idle, tank_filling, ...
    workflow_payload: Dict[str, Any]  # контекст текущей фазы

    # Телеметрия (snapshot, загружается при создании контекста)
    telemetry: ZoneTelemetry          # последние значения всех сенсоров
    telemetry_timestamps: Dict[str, datetime]  # время последнего значения

    # PID состояние (загружается из БД)
    pid_state: Optional[PidState]     # integral, prev_error, prev_derivative, last_output_ms

    # Correction gating (загружается из БД)
    correction_flags: CorrectionFlags  # flow_active, stable, corrections_allowed, updated_at

    # Узлы и привязки
    nodes: List[ZoneNode]             # узлы, привязанные к зоне
    bindings: Dict[str, NodeBinding]  # channel → node_uid mapping

    # Водоснабжение
    water_levels: WaterLevels         # level_clean_min/max, level_solution_min/max

    # Timestamps
    created_at: datetime              # когда контекст создан
    task_received_at: datetime        # когда задача получена API
```

### 4.2 Жизненный цикл ZoneContext

```
1. POST /internal/tasks/enqueue → API получает TaskRequest
2. TaskRouter создаёт ZoneContext:
   a. Загрузить zone_config из кэша (или Laravel API)
   b. Загрузить targets из кэша (или DB)
   c. Загрузить workflow_phase из DB
   d. Загрузить telemetry из DB (telemetry_last)
   e. Загрузить correction_flags из DB
   f. Загрузить pid_state из DB (если correction task)
   g. Загрузить nodes и bindings из DB
   h. Загрузить water_levels из telemetry
3. ZoneContext передаётся в Controller.execute(ctx)
4. Controller возвращает TaskResult
5. ZoneContext GC-ится (не хранится в памяти между задачами)
```

### 4.3 Загрузка контекста — batch оптимизация

```python
async def build_zone_context(zone_id: int, task: TaskRequest, deps: AppDeps) -> ZoneContext:
    """Загрузить всё состояние зоны одним batch-ом."""
    # Один round-trip к БД: все SELECT-ы в одном SQL блоке
    raw = await deps.db.fetch("""
        SELECT
            ws.workflow_phase, ws.payload AS ws_payload, ws.updated_at AS ws_updated_at,
            cf.flow_active, cf.stable, cf.corrections_allowed, cf.updated_at AS cf_updated_at,
            ps.integral, ps.prev_error, ps.prev_derivative, ps.last_output_ms,
            ps.current_zone, ps.pid_type
        FROM zones z
        LEFT JOIN zone_workflow_state ws ON ws.zone_id = z.id
        LEFT JOIN zone_correction_flags cf ON cf.zone_id = z.id
        LEFT JOIN pid_state ps ON ps.zone_id = z.id AND ps.pid_type = $2
        WHERE z.id = $1
    """, zone_id, task.correction_type_for_pid())

    telemetry = await deps.db.fetch("""
        SELECT sensor_type, last_value, last_ts
        FROM telemetry_last
        WHERE zone_id = $1
    """, zone_id)

    nodes = await deps.db.fetch("""
        SELECT zn.node_uid, zn.channel, n.type, n.status
        FROM zone_nodes zn
        JOIN nodes n ON n.uid = zn.node_uid
        WHERE zn.zone_id = $1
    """, zone_id)

    # Собрать ZoneContext из raw данных
    return ZoneContext(
        zone_id=zone_id,
        task_id=task.task_id,
        task_type=task.task_type,
        # ...
    )
```

**3 SQL запроса вместо 6+ в текущей системе.** Можно ещё оптимизировать до 1 запроса с CTE, но читаемость важнее.

---

## 5. Workflow FSM — строгая машина состояний

### 5.1 Фазы и переходы

```
                    ┌──────┐
          ┌────────▶│ idle │◄──────────────────────────┐
          │         └──┬───┘                           │
          │            │ event: start_filling             │
          │            ▼                               │
          │    ┌──────────────┐                        │
          │    │ tank_filling  │                        │
          │    └──────┬───────┘                        │
          │           │ event: filling_complete         │
          │           ▼                               │
          │    ┌──────────────┐                        │
          │    │  tank_recirc  │                        │
          │    └──────┬───────┘                        │
          │           │ event: recirc_complete          │
          │           ▼                               │
          │    ┌──────────────┐                        │
    abort  │    │    ready      │◄─────┐                │
    (any)  │    └──────┬───────┘      │                │
          │           │ event: irrigation_started      │
          │           ▼               │                │
          │    ┌──────────────┐       │                │
          │    │  irrigating   │       │ irrigation_started│
          │    └──────┬───────┘      │ (следующий цикл)│
          │           │ event: irrigation_stopped       │
          │           ▼               │                │
          │    ┌──────────────┐       │                │
          │    │ irrig_recirc  │───────┘                │
          │    └──────┬───────┘  event: recirc_complete │
          │           │                                │
          └───────────┘ (cycle_complete → idle)         │
                                                       │
          emergency_stop (из любой фазы) ──────────────┘
```

### 5.2 Реализация

```python
class WorkflowPhase(str, Enum):
    IDLE = "idle"
    TANK_FILLING = "tank_filling"
    TANK_RECIRC = "tank_recirc"
    READY = "ready"
    IRRIGATING = "irrigating"
    IRRIG_RECIRC = "irrig_recirc"


# Явная таблица переходов.
# Ключ = (текущая_фаза, transition_event), значение = новая_фаза.
# transition_event — это НЕ task_type. Контроллер возвращает event в TaskResult.state_updates.
TRANSITIONS: Dict[Tuple[WorkflowPhase, str], WorkflowPhase] = {
    # Startup (two-tank)
    (WorkflowPhase.IDLE, "start_filling"):              WorkflowPhase.TANK_FILLING,
    (WorkflowPhase.TANK_FILLING, "filling_complete"):   WorkflowPhase.TANK_RECIRC,
    (WorkflowPhase.TANK_RECIRC, "recirc_complete"):     WorkflowPhase.READY,

    # Irrigation cycle
    (WorkflowPhase.READY, "irrigation_started"):        WorkflowPhase.IRRIGATING,
    (WorkflowPhase.IRRIGATING, "irrigation_stopped"):   WorkflowPhase.IRRIG_RECIRC,
    (WorkflowPhase.IRRIG_RECIRC, "irrigation_started"): WorkflowPhase.IRRIGATING,
    (WorkflowPhase.IRRIG_RECIRC, "recirc_complete"):    WorkflowPhase.READY,
}

# Переход idle разрешён из любой фазы (emergency/abort/cycle_complete).
UNIVERSAL_TRANSITIONS: Dict[str, WorkflowPhase] = {
    "emergency_stop":  WorkflowPhase.IDLE,
    "abort":           WorkflowPhase.IDLE,
    "cycle_complete":  WorkflowPhase.IDLE,
}


def transition(current: WorkflowPhase, event: str) -> WorkflowPhase:
    """Строгий переход. Бросает InvalidTransition если переход невалиден.

    Args:
        current: текущая фаза workflow
        event: событие перехода (НЕ task_type, а семантическое событие)
    """
    if event in UNIVERSAL_TRANSITIONS:
        return UNIVERSAL_TRANSITIONS[event]

    key = (current, event)
    if key not in TRANSITIONS:
        allowed = [ev for (ph, ev) in TRANSITIONS if ph == current]
        raise InvalidTransitionError(
            f"Переход {current.value} + '{event}' не разрешён. "
            f"Допустимые события из {current.value}: {allowed}"
        )
    return TRANSITIONS[key]
```

### 5.3 Персистенция workflow state

```python
async def save_workflow_transition(
    zone_id: int,
    old_phase: WorkflowPhase,
    new_phase: WorkflowPhase,
    task_id: str,
    payload: Dict[str, Any],
    db: Database,
) -> None:
    """Атомарно обновить фазу с проверкой текущей."""
    result = await db.execute("""
        UPDATE zone_workflow_state
        SET workflow_phase = $2,
            started_at = NOW(),
            updated_at = NOW(),
            payload = $3::jsonb,
            scheduler_task_id = $4
        WHERE zone_id = $1
          AND workflow_phase = $5  -- optimistic lock: фаза не изменилась
        RETURNING zone_id
    """, zone_id, new_phase.value, json.dumps(payload), task_id, old_phase.value)

    if not result:
        raise ConcurrentModificationError(
            f"Zone {zone_id}: workflow_phase изменилась между загрузкой и сохранением. "
            f"Ожидалась {old_phase.value}, но в БД уже другая."
        )

    # Запись в журнал событий
    await db.execute("""
        INSERT INTO zone_events (zone_id, type, payload_json, created_at)
        VALUES ($1, 'WORKFLOW_PHASE_CHANGED', $2::jsonb, NOW())
    """, zone_id, json.dumps({
        "from": old_phase.value,
        "to": new_phase.value,
        "task_id": task_id,
        "trigger": "task_execution",
    }))
```

**Optimistic locking:** если два task-а одновременно пытаются сменить фазу одной зоны, второй получит `ConcurrentModificationError`. Это правильное поведение — scheduler не должен отправлять конфликтующие задачи для одной зоны.

---

## 6. Контроллеры

### 6.1 Интерфейс

```python
@dataclass
class TaskResult:
    """Результат выполнения задачи."""
    success: bool
    commands_sent: List[CommandRecord]  # отправленные команды
    next_tasks: List[NextTask]         # задачи, которые scheduler должен запланировать
    state_updates: StateUpdates        # изменения состояния для персистенции
    errors: List[TaskError]            # ошибки (не фатальные)
    metrics: Dict[str, float]          # метрики для Prometheus


@dataclass
class NextTask:
    """Запрос на создание следующей задачи."""
    task_type: str
    delay_seconds: int      # через сколько секунд запустить
    payload: Dict[str, Any] # дополнительные данные
    reason: str             # почему нужна эта задача


@dataclass
class StateUpdates:
    """Изменения состояния, которые нужно сохранить после задачи."""
    workflow_transition_event: Optional[str] = None  # событие FSM ("start_filling", "irrigation_started", ...)
    pid_state: Optional[PidState] = None
    correction_flags_reset: bool = False


class Controller(Protocol):
    """Интерфейс контроллера. Каждый контроллер — чистая функция от контекста к результату."""

    async def execute(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        """Выполнить задачу. Не мутирует ctx. Возвращает результат."""
        ...

    def can_execute(self, ctx: ZoneContext) -> Tuple[bool, Optional[str]]:
        """Проверить, можно ли выполнить задачу в текущем контексте.
        Возвращает (True, None) или (False, причина)."""
        ...
```

### 6.2 CorrectionController (pH / EC)

```python
class CorrectionController:
    """Контроллер коррекции pH или EC."""

    def __init__(self, correction_type: CorrectionType):
        self.correction_type = correction_type  # PH или EC

    # Фазы, в которых коррекции pH/EC разрешены
    CORRECTION_ALLOWED_PHASES = {
        WorkflowPhase.TANK_FILLING,
        WorkflowPhase.TANK_RECIRC,
        WorkflowPhase.IRRIGATING,
        WorkflowPhase.IRRIG_RECIRC,
    }

    def can_execute(self, ctx: ZoneContext) -> Tuple[bool, Optional[str]]:
        # 1. Workflow phase разрешает коррекции?
        if ctx.workflow_phase not in self.CORRECTION_ALLOWED_PHASES:
            return False, f"phase_{ctx.workflow_phase.value}_not_allowed"

        # 2. Correction flags свежие и разрешают?
        if not ctx.correction_flags.is_fresh(max_age_sec=300):
            return False, "correction_flags_stale"
        if not ctx.correction_flags.flow_active:
            return False, "flow_inactive"
        if not ctx.correction_flags.stable:
            return False, "sensor_unstable"
        if not ctx.correction_flags.corrections_allowed:
            return False, "corrections_not_allowed"

        # 3. Телеметрия свежая?
        sensor_key = "PH" if self.correction_type == CorrectionType.PH else "EC"
        ts = ctx.telemetry_timestamps.get(sensor_key)
        if ts is None or (ctx.created_at - ts).total_seconds() > 300:
            return False, "telemetry_stale"

        # 4. Water level OK?
        if not ctx.water_levels.is_ok():
            return False, "water_level_low"

        return True, None

    async def execute(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        can, reason = self.can_execute(ctx)
        if not can:
            return TaskResult(
                success=True,  # не ошибка, просто skip
                commands_sent=[],
                next_tasks=[],
                state_updates=StateUpdates(),
                errors=[],
                metrics={"correction_skipped": 1, "skip_reason": reason},
            )

        # Загрузить/создать PID
        pid = self._restore_pid(ctx)

        current_value = ctx.telemetry.get(self.correction_type.sensor_key)
        target_value = ctx.targets.get(self.correction_type.target_key)
        error = target_value - current_value

        # Safety bounds
        if not self._within_safety_bounds(current_value):
            return self._safety_bounds_result(current_value, ctx)

        # Anomaly check (без critical override — просто блокировка)
        if self._is_anomaly(current_value, ctx):
            return self._anomaly_result(current_value, ctx)

        # PID compute
        dt_seconds = self._compute_dt(ctx)
        dose_ml = pid.compute(current_value, dt_seconds)

        if dose_ml <= 0:
            return TaskResult(
                success=True,
                commands_sent=[],
                next_tasks=[],
                state_updates=StateUpdates(pid_state=self._snapshot_pid(pid)),
                errors=[],
                metrics={"correction_dose_ml": 0, "error": abs(error)},
            )

        # Построить команды дозирования
        # Для EC: компоненты зависят от фазы workflow
        # tank_filling, tank_recirc → ["npk"]
        # irrigating, irrig_recirc → ["calcium", "magnesium", "micro"]
        commands = self._build_dose_commands(ctx, dose_ml)

        return TaskResult(
            success=True,
            commands_sent=[],  # заполнится после отправки
            next_tasks=[],
            state_updates=StateUpdates(pid_state=self._snapshot_pid(pid)),
            errors=[],
            metrics={
                "correction_dose_ml": dose_ml,
                "error": abs(error),
                "pid_integral": pid.integral,
                "pid_zone": pid.current_zone.value,
            },
        )
```

### 6.3 IrrigationController

```python
class IrrigationController:
    """Управление поливом."""

    async def execute(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        if ctx.task_type == "irrigation_start":
            return await self._start_irrigation(ctx, deps)
        elif ctx.task_type == "irrigation_stop":
            return await self._stop_irrigation(ctx, deps)
        else:
            raise ValueError(f"Unknown task_type for IrrigationController: {ctx.task_type}")

    async def _start_irrigation(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        # Проверить water level
        if not ctx.water_levels.is_ok():
            return TaskResult(success=False, errors=[TaskError("water_level_low")])

        # Команда включения насоса
        pump_binding = ctx.bindings.get("pump_main")
        if not pump_binding:
            return TaskResult(success=False, errors=[TaskError("no_pump_binding")])

        duration_sec = ctx.targets.irrigation.duration_sec

        commands = [
            CommandRecord(
                node_uid=pump_binding.node_uid,
                channel=pump_binding.channel,
                cmd="set_relay",
                params={"state": True},
            )
        ]

        # Запланировать остановку полива через duration_sec
        next_tasks = [
            NextTask(
                task_type="irrigation_stop",
                delay_seconds=duration_sec,
                payload={"started_by_task": ctx.task_id},
                reason="irrigation_duration_elapsed",
            )
        ]

        return TaskResult(
            success=True,
            commands_sent=commands,
            next_tasks=next_tasks,
            state_updates=StateUpdates(workflow_transition_event="irrigation_started"),
            errors=[],
            metrics={"irrigation_duration_sec": duration_sec},
        )

    async def _stop_irrigation(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        pump_binding = ctx.bindings.get("pump_main")
        commands = [
            CommandRecord(
                node_uid=pump_binding.node_uid,
                channel=pump_binding.channel,
                cmd="set_relay",
                params={"state": False},
            )
        ]

        # После полива — рециркуляция
        next_tasks = [
            NextTask(
                task_type="recirculation_start",
                delay_seconds=5,
                payload={"after_irrigation_task": ctx.task_id},
                reason="post_irrigation_recirculation",
            )
        ]

        return TaskResult(
            success=True,
            commands_sent=commands,
            next_tasks=next_tasks,
            state_updates=StateUpdates(workflow_transition_event="irrigation_stopped"),
            errors=[],
            metrics={},
        )
```

### 6.4 ClimateController

```python
class ClimateController:
    """Управление климатом: температура, влажность, CO2."""

    async def execute(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        commands = []

        # Температура
        temp_cmds = self._evaluate_temperature(ctx)
        commands.extend(temp_cmds)

        # Влажность
        humidity_cmds = self._evaluate_humidity(ctx)
        commands.extend(humidity_cmds)

        # CO2 — только алерт, без актуаторов
        co2_alerts = self._evaluate_co2(ctx)

        return TaskResult(
            success=True,
            commands_sent=commands,
            next_tasks=[],
            state_updates=StateUpdates(),
            errors=co2_alerts,
            metrics={
                "temperature": ctx.telemetry.temperature,
                "humidity": ctx.telemetry.humidity,
                "co2": ctx.telemetry.co2,
            },
        )

    def _evaluate_temperature(self, ctx: ZoneContext) -> List[CommandRecord]:
        current = ctx.telemetry.temperature
        target = ctx.targets.climate.temp_target
        if current is None or target is None:
            return []

        diff = current - target
        fan_binding = ctx.bindings.get("fan")
        heater_binding = ctx.bindings.get("heater")
        commands = []

        # Гистерезис: включить вентилятор если temp > target + 1.0
        if diff > 1.0 and fan_binding:
            pwm = min(100, int(diff * 25))  # пропорциональное управление
            commands.append(CommandRecord(
                node_uid=fan_binding.node_uid,
                channel=fan_binding.channel,
                cmd="set_pwm",
                params={"value": pwm},
            ))
        elif diff < -1.0 and heater_binding:
            commands.append(CommandRecord(
                node_uid=heater_binding.node_uid,
                channel=heater_binding.channel,
                cmd="set_relay",
                params={"state": True},
            ))
        elif abs(diff) < 0.5:
            # В мёртвой зоне — выключить всё
            if fan_binding:
                commands.append(CommandRecord(
                    node_uid=fan_binding.node_uid,
                    channel=fan_binding.channel,
                    cmd="set_pwm",
                    params={"value": 0},
                ))
            if heater_binding:
                commands.append(CommandRecord(
                    node_uid=heater_binding.node_uid,
                    channel=heater_binding.channel,
                    cmd="set_relay",
                    params={"state": False},
                ))

        return commands
```

### 6.5 RecirculationController

```python
class RecirculationController:
    """Управление рециркуляцией раствора после полива."""

    async def execute(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        if ctx.task_type == "recirculation_start":
            return await self._start(ctx, deps)
        elif ctx.task_type == "recirculation_stop":
            return await self._stop(ctx, deps)
        else:
            raise ValueError(f"Unknown task_type: {ctx.task_type}")

    async def _start(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        pump_binding = ctx.bindings.get("pump_recirc")
        if not pump_binding:
            return TaskResult(success=False, errors=[TaskError("no_recirc_pump_binding")])

        recirc_duration = ctx.targets.irrigation.recirc_duration_sec or 300

        commands = [
            CommandRecord(
                node_uid=pump_binding.node_uid,
                channel=pump_binding.channel,
                cmd="set_relay",
                params={"state": True},
            )
        ]

        return TaskResult(
            success=True,
            commands_sent=commands,
            next_tasks=[
                NextTask(
                    task_type="recirculation_stop",
                    delay_seconds=recirc_duration,
                    payload={"started_by_task": ctx.task_id},
                    reason="recirculation_duration_elapsed",
                )
            ],
            state_updates=StateUpdates(),  # фаза уже IRRIG_RECIRC (установлена irrigation_stop)
            errors=[],
            metrics={"recirc_duration_sec": recirc_duration},
        )

    async def _stop(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        pump_binding = ctx.bindings.get("pump_recirc")
        commands = []
        if pump_binding:
            commands.append(CommandRecord(
                node_uid=pump_binding.node_uid,
                channel=pump_binding.channel,
                cmd="set_relay",
                params={"state": False},
            ))

        return TaskResult(
            success=True,
            commands_sent=commands,
            next_tasks=[],
            state_updates=StateUpdates(workflow_transition_event="recirc_complete"),
            errors=[],
            metrics={},
        )
```

### 6.6. LightingController

```python
class LightingController:
    """Управление освещением по фотопериоду."""

    async def execute(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        lighting = ctx.targets.lighting
        if not lighting or not lighting.enabled:
            return TaskResult(success=True, commands_sent=[], next_tasks=[],
                            state_updates=StateUpdates(), errors=[], metrics={})

        now = ctx.created_at
        should_be_on = lighting.is_within_photoperiod(now)
        light_binding = ctx.bindings.get("light")
        if not light_binding:
            return TaskResult(success=True, commands_sent=[], next_tasks=[],
                            state_updates=StateUpdates(),
                            errors=[TaskError("no_light_binding")], metrics={})

        if should_be_on:
            cmd = CommandRecord(
                node_uid=light_binding.node_uid,
                channel=light_binding.channel,
                cmd="set_pwm",
                params={"value": lighting.intensity},
            )
        else:
            cmd = CommandRecord(
                node_uid=light_binding.node_uid,
                channel=light_binding.channel,
                cmd="set_relay",
                params={"state": False},
            )

        return TaskResult(
            success=True,
            commands_sent=[cmd],
            next_tasks=[],
            state_updates=StateUpdates(),
            errors=[],
            metrics={"light_on": 1 if should_be_on else 0, "intensity": lighting.intensity if should_be_on else 0},
        )
```

### 6.7 WorkflowController (two-tank)

```python
class WorkflowController:
    """Управление two-tank workflow: startup → fill → recirc → ready."""

    async def execute(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        step = ctx.task_payload.get("workflow_step")

        handler = {
            "startup":           self._handle_startup,
            "clean_fill_start":  self._handle_clean_fill_start,
            "clean_fill_check":  self._handle_clean_fill_check,
            "solution_fill":     self._handle_solution_fill,
            "solution_fill_check": self._handle_solution_fill_check,
            "prepare_recirc":    self._handle_prepare_recirc,
            "prepare_recirc_check": self._handle_prepare_recirc_check,
        }.get(step)

        if not handler:
            return TaskResult(success=False, errors=[TaskError(f"unknown_workflow_step: {step}")])

        return await handler(ctx, deps)

    async def _handle_startup(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        """Начало цикла: проверить ресурсы и запустить заполнение."""
        # Проверить, что все критические узлы онлайн
        offline_nodes = [n for n in ctx.nodes if n.is_critical and n.status != "online"]
        if offline_nodes:
            return TaskResult(
                success=False,
                errors=[TaskError(f"critical_nodes_offline: {[n.node_uid for n in offline_nodes]}")],
            )

        # Запуск заполнения чистой воды
        commands = self._build_clean_fill_commands(ctx)

        return TaskResult(
            success=True,
            commands_sent=commands,
            next_tasks=[
                NextTask(
                    task_type="workflow_step",
                    delay_seconds=30,  # проверить через 30 сек
                    payload={"workflow_step": "clean_fill_check"},
                    reason="check_clean_fill_progress",
                )
            ],
            state_updates=StateUpdates(workflow_transition_event="start_filling"),
            errors=[],
            metrics={},
        )

    async def _handle_clean_fill_check(self, ctx: ZoneContext, deps: ControllerDeps) -> TaskResult:
        """Проверить, заполнен ли чистый танк."""
        if ctx.water_levels.clean_max:
            # Танк полный, переходим к заполнению раствора
            commands = self._build_stop_clean_fill_commands(ctx)
            return TaskResult(
                success=True,
                commands_sent=commands,
                next_tasks=[
                    NextTask(
                        task_type="workflow_step",
                        delay_seconds=5,
                        payload={"workflow_step": "solution_fill"},
                        reason="clean_fill_complete",
                    )
                ],
                state_updates=StateUpdates(),
                errors=[],
                metrics={},
            )
        else:
            # Ещё не заполнен — перепроверить
            return TaskResult(
                success=True,
                commands_sent=[],
                next_tasks=[
                    NextTask(
                        task_type="workflow_step",
                        delay_seconds=30,
                        payload={"workflow_step": "clean_fill_check"},
                        reason="clean_fill_in_progress",
                    )
                ],
                state_updates=StateUpdates(),
                errors=[],
                metrics={"clean_level": ctx.water_levels.clean_level_pct},
            )
```

---

## 7. TaskRouter — маршрутизация задач

```python
class TaskRouter:
    """Маршрутизирует входящие задачи к контроллерам."""

    def __init__(self):
        self._controllers: Dict[str, Controller] = {
            "correction_ph":       CorrectionController(CorrectionType.PH),
            "correction_ec":       CorrectionController(CorrectionType.EC),
            "irrigation_start":    IrrigationController(),
            "irrigation_stop":     IrrigationController(),
            "recirculation_start": RecirculationController(),
            "recirculation_stop":  RecirculationController(),
            "climate_check":       ClimateController(),
            "lighting_check":      LightingController(),
            "workflow_step":       WorkflowController(),
            "health_check":        HealthController(),
            "diagnostics":         DiagnosticsController(),
        }

    def get_controller(self, task_type: str) -> Controller:
        controller = self._controllers.get(task_type)
        if not controller:
            raise UnknownTaskTypeError(f"Неизвестный task_type: {task_type}")
        return controller
```

---

## 8. TaskExecutor — выполнение задач

```python
class TaskExecutor:
    """Выполняет задачу: загружает контекст, запускает контроллер, сохраняет результат."""

    def __init__(self, router: TaskRouter, deps: AppDeps):
        self.router = router
        self.deps = deps
        self._zone_locks: Dict[int, asyncio.Lock] = {}  # per-zone lock

    async def execute(self, task: TaskRequest) -> TaskResponse:
        """Главный метод. Гарантирует: одна задача на зону в момент времени."""

        # Per-zone lock: предотвращает параллельное выполнение задач для одной зоны
        lock = self._zone_locks.setdefault(task.zone_id, asyncio.Lock())
        async with lock:
            return await self._execute_locked(task)

    async def _execute_locked(self, task: TaskRequest) -> TaskResponse:
        start_time = time.monotonic()

        # 1. Загрузить контекст
        try:
            ctx = await build_zone_context(task.zone_id, task, self.deps)
        except ZoneNotFoundError:
            return TaskResponse(status="rejected", error="zone_not_found")
        except Exception as exc:
            logger.error("Failed to build ZoneContext for zone %s: %s", task.zone_id, exc)
            return TaskResponse(status="error", error="context_build_failed")

        # 2. Найти контроллер
        try:
            controller = self.router.get_controller(task.task_type)
        except UnknownTaskTypeError:
            return TaskResponse(status="rejected", error="unknown_task_type")

        # 3. Проверить предусловия
        can, reason = controller.can_execute(ctx)
        if not can:
            TASK_SKIPPED.labels(task_type=task.task_type, reason=reason).inc()
            return TaskResponse(status="skipped", skip_reason=reason)

        # 4. Выполнить
        try:
            result = await controller.execute(ctx, self.deps.controller_deps)
        except InvalidTransitionError as exc:
            logger.error("Zone %s: invalid workflow transition: %s", task.zone_id, exc)
            return TaskResponse(status="error", error="invalid_workflow_transition")
        except ConcurrentModificationError as exc:
            logger.warning("Zone %s: concurrent modification: %s", task.zone_id, exc)
            return TaskResponse(status="conflict", error="concurrent_modification")
        except Exception as exc:
            logger.error("Zone %s: task execution failed: %s", task.zone_id, exc, exc_info=True)
            return TaskResponse(status="error", error=str(exc))

        # 5. Отправить команды через CommandBus
        sent_commands = []
        for cmd in result.commands_sent:
            success = await self.deps.command_bus.publish_command(
                zone_id=task.zone_id,
                node_uid=cmd.node_uid,
                channel=cmd.channel,
                cmd=cmd.cmd,
                params=cmd.params,
            )
            sent_commands.append(SentCommand(cmd=cmd, success=success))

        # 6. Сохранить state updates
        if result.state_updates.workflow_transition_event:
            new_phase = transition(ctx.workflow_phase, result.state_updates.workflow_transition_event)
            await save_workflow_transition(
                zone_id=task.zone_id,
                old_phase=ctx.workflow_phase,
                new_phase=new_phase,
                task_id=task.task_id,
                payload={"task_type": task.task_type, "event": result.state_updates.workflow_transition_event},
                db=self.deps.db,
            )

        if result.state_updates.pid_state:
            await save_pid_state(task.zone_id, result.state_updates.pid_state, self.deps.db)

        # 7. Записать метрики
        elapsed = time.monotonic() - start_time
        TASK_DURATION.labels(task_type=task.task_type).observe(elapsed)
        for key, value in result.metrics.items():
            TASK_METRICS.labels(task_type=task.task_type, metric=key).set(value)

        # 8. Вернуть ответ (включая next_tasks для scheduler)
        return TaskResponse(
            status="completed" if result.success else "failed",
            commands_sent=len(sent_commands),
            commands_failed=len([c for c in sent_commands if not c.success]),
            next_tasks=[
                NextTaskResponse(
                    task_type=nt.task_type,
                    delay_seconds=nt.delay_seconds,
                    payload=nt.payload,
                    reason=nt.reason,
                )
                for nt in result.next_tasks
            ],
            errors=[e.code for e in result.errors],
            duration_ms=int(elapsed * 1000),
        )
```

---

## 9. REST API

### 9.1 Endpoints

```
POST /internal/tasks/enqueue          — internal enqueue (асинхронно, 202)
GET  /internal/tasks/{task_id}        — статус/итог задачи (poll endpoint)
POST /zones/{id}/manual-action       — ручное действие (UI / оператор)
GET  /zones/{id}/state               — текущее состояние зоны
GET  /zones/{id}/workflow             — текущая фаза workflow
GET  /health                          — healthcheck
GET  /metrics                         — Prometheus метрики
```

### 9.2 POST /internal/tasks/enqueue — контракт

**Request:**
```json
{
  "task_id": "sch:z447:correction_ph:abc123",
  "zone_id": 447,
  "task_type": "correction_ph",
  "source": "laravel_scheduler",
  "idempotency_key": "sch:z447:correction_ph:abc123",
  "payload": {},
  "scheduled_for": "2026-03-05T10:30:00Z",
  "due_at": "2026-03-05T10:30:15Z",
  "expires_at": "2026-03-05T10:32:00Z"
}
```

**Response (accepted):**
```json
{
  "status": "accepted",
  "task_id": "sch:z447:correction_ph:abc123",
  "zone_id": 447,
  "idempotency_key": "sch:z447:correction_ph:abc123",
  "poll_url": "/internal/tasks/sch:z447:correction_ph:abc123",
  "error_code": null
}
```

**Response (deduplicated):**
```json
{
  "status": "deduplicated",
  "task_id": "sch:z447:correction_ph:abc123",
  "zone_id": 447,
  "idempotency_key": "sch:z447:correction_ph:abc123",
  "poll_url": "/internal/tasks/sch:z447:correction_ph:abc123",
  "error_code": null
}
```

Terminal result читается через `GET /internal/tasks/{task_id}`:
```json
{
  "status": "completed",
  "task_id": "sch:z447:irrigation_start:def456",
  "zone_id": 447,
  "commands_sent": 1,
  "commands_failed": 0,
  "next_tasks": [
    {
      "task_type": "irrigation_stop",
      "delay_seconds": 120,
      "payload": {"started_by_task": "sch:z447:irrigation_start:def456"},
      "reason": "irrigation_duration_elapsed"
    }
  ],
  "errors": [],
  "duration_ms": 38
}
```

### 9.3 POST /zones/{id}/manual-action

Для ручного управления из UI. Минимальные отличия от `/internal/tasks/enqueue`:
- Не требует `idempotency_key` (генерируется автоматически)
- `source` = "manual"
- Логируется отдельно для audit trail

**Request:**
```json
{
  "action": "irrigation_start",
  "payload": {
    "duration_sec": 60,
    "reason": "operator_manual_override"
  }
}
```

---

## 10. PID State — персистенция

### 10.1 Почему персистенция нужна

В AE2 PID state живёт только в памяти. При рестарте:
- `integral` = 0 → первые несколько коррекций будут неоптимальны
- `last_output_ms` = 0 → первая коррекция пройдёт без min_interval guard
- `prev_error` = None → derivative term = 0 на первом шаге

### 10.2 Структура

```python
@dataclass
class PidState:
    """Персистентное состояние PID контроллера."""
    zone_id: int
    pid_type: str               # "ph" или "ec"
    integral: float             # накопленный integral term
    prev_error: Optional[float] # предыдущая ошибка
    prev_derivative: float      # отфильтрованная производная
    last_output_ms: int         # monotonic ms последнего выхода (для min_interval)
    last_dose_at: datetime      # wall clock последнего выхода (для персистенции)
    emergency: bool             # emergency stop активен?
    current_zone: str           # "dead", "close", "far"
    compute_count: int          # статистика
    corrections_count: int
    saturation_count: int
    total_output: float
    max_error: float
    avg_error: float
    updated_at: datetime
```

### 10.3 Таблица

```sql
CREATE TABLE pid_state (
    zone_id INT NOT NULL,
    pid_type VARCHAR(10) NOT NULL,  -- 'ph' или 'ec'
    integral DOUBLE PRECISION NOT NULL DEFAULT 0,
    prev_error DOUBLE PRECISION,
    last_output_ms BIGINT NOT NULL DEFAULT 0,
    prev_derivative DOUBLE PRECISION NOT NULL DEFAULT 0,
    last_dose_at TIMESTAMP,
    emergency BOOLEAN NOT NULL DEFAULT FALSE,
    current_zone VARCHAR(10) NOT NULL DEFAULT 'dead',
    compute_count INT NOT NULL DEFAULT 0,
    corrections_count INT NOT NULL DEFAULT 0,
    saturation_count INT NOT NULL DEFAULT 0,
    total_output DOUBLE PRECISION NOT NULL DEFAULT 0,
    max_error DOUBLE PRECISION NOT NULL DEFAULT 0,
    avg_error DOUBLE PRECISION NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (zone_id, pid_type)
);
```

### 10.4 Восстановление min_interval при рестарте

```python
def restore_pid_from_db(state: PidState) -> AdaptivePid:
    pid = AdaptivePid(config=get_pid_config(state.pid_type))
    pid.integral = state.integral
    pid.prev_error = state.prev_error
    pid.prev_derivative = state.prev_derivative
    pid.emergency = state.emergency
    pid.stats.compute_count = state.compute_count
    pid.stats.corrections_count = state.corrections_count

    # Восстановить last_output_ms из wall clock
    if state.last_dose_at:
        elapsed_since_last = (datetime.utcnow() - state.last_dose_at).total_seconds()
        if elapsed_since_last < pid.config.min_interval_ms / 1000:
            # Ещё не прошло min_interval — установить last_output_ms так,
            # чтобы guard сработал правильно
            pid.last_output_ms = int(time.monotonic() * 1000) - int(elapsed_since_last * 1000)
        # Если прошло больше min_interval — оставляем 0, коррекция разрешена

    return pid
```

---

## 11. Scheduler Integration — новый контракт

### 11.1 Текущий контракт (AE2)

```
Scheduler → POST /zones/{id}/start-cycle → AE claims intent → AE executes workflow → AE marks terminal
```

Проблема: scheduler отправляет одну задачу (`start-cycle`), а AE сам решает, что делать. Scheduler не знает, какие конкретные действия AE выполнит.

### 11.2 Новый контракт (AE3, phased)

```
Фаза A-B (до direct-enqueue):
Scheduler → POST /zones/{id}/start-cycle → intent bridge → AE planner/executor

Фаза C+ (после migration gate):
Scheduler → POST /internal/tasks/enqueue {task_type: "..."} → AE executes → scheduler poll status
```

До direct-enqueue scheduler отвечает за:
- wake-up и idempotency через `start-cycle`;
- tracking статуса через `intent-<id>`/poller bridge;
- retry на уровне scheduler intent-policy.

После direct-enqueue scheduler отвечает за:
- Определение КОГДА запускать задачу (cron, interval, event-driven)
- Отслеживание статуса задачи
- Retry при failure

**AE отвечает за:**
- Определение КАК выполнить задачу (команды, PID, gating)
- Планирование/enqueue `next_tasks` через internal planner policy
- Персистенция состояния

### 11.3 Пример: полный irrigation цикл (после direct-enqueue gate)

```
1. Scheduler: POST /internal/tasks/enqueue {task_type: "irrigation_start", zone_id: 447}
   AE response: {
     status: "completed",
     next_tasks: [{task_type: "irrigation_stop", delay_seconds: 120}]
   }

2. Scheduler ждёт 120 сек, затем:
   POST /internal/tasks/enqueue {task_type: "irrigation_stop", zone_id: 447}
   AE response: {
     status: "completed",
     next_tasks: [{task_type: "recirculation_start", delay_seconds: 5}]
   }

3. Scheduler ждёт 5 сек:
   POST /internal/tasks/enqueue {task_type: "recirculation_start", zone_id: 447}
   AE response: {
     status: "completed",
     next_tasks: [{task_type: "recirculation_stop", delay_seconds: 300}]
   }

4. Scheduler ждёт 300 сек:
   POST /internal/tasks/enqueue {task_type: "recirculation_stop", zone_id: 447}
   AE response: {
     status: "completed",
     next_tasks: []
   }
```

### 11.4 Пример: two-tank startup (после direct-enqueue gate)

```
1. Scheduler (или manual): POST /internal/tasks/enqueue {task_type: "workflow_step", zone_id: 447, payload: {workflow_step: "startup"}}
   AE: открывает клапаны, возвращает:
   {next_tasks: [{task_type: "workflow_step", delay_seconds: 30, payload: {workflow_step: "clean_fill_check"}}]}

2. Scheduler через 30 сек: POST /internal/tasks/enqueue {task_type: "workflow_step", payload: {workflow_step: "clean_fill_check"}}
   AE: проверяет уровень воды. Ещё не заполнен:
   {next_tasks: [{task_type: "workflow_step", delay_seconds: 30, payload: {workflow_step: "clean_fill_check"}}]}

3. Scheduler через 30 сек: тот же запрос
   AE: танк заполнен!
   {next_tasks: [{task_type: "workflow_step", delay_seconds: 5, payload: {workflow_step: "solution_fill"}}]}

...и так далее до READY.
```

### 11.5 Периодические задачи

Для `correction_*`, `climate_check`, `lighting_check` direct enqueue scheduler-ом допустим только после migration gate.
До gate эти задачи формируются internal planner-ом из legacy scheduler task types.

```
correction_ph:  каждые 90 секунд
correction_ec:  каждые 120 секунд
climate_check:  каждые 60 секунд
lighting_check: каждые 60 секунд
health_check:   каждые 60 секунд
```

AE **не планирует** эти задачи сам. Если correction_ph вернёт `skipped` (flow_inactive), scheduler просто отправит следующую через 90 секунд. Scheduler не прекращает отправлять периодические задачи — AE сам решает, выполнять или пропустить.

---

## 12. Concurrency и Safety

### 12.1 Per-zone Lock

```python
# В TaskExecutor
_zone_locks: Dict[int, asyncio.Lock]

# Гарантия: только одна задача выполняется для зоны в момент времени.
# Если scheduler отправит две задачи для zone 447 одновременно,
# вторая подождёт завершения первой.
```

### 12.2 Optimistic Locking для workflow state

```sql
UPDATE zone_workflow_state
SET workflow_phase = $2
WHERE zone_id = $1
  AND workflow_phase = $5  -- optimistic lock
```

Если кто-то другой уже изменил фазу → `ConcurrentModificationError` → scheduler получит `conflict` и может retry.

### 12.3 Idempotency

Каждая задача имеет `idempotency_key`. AE отслеживает:

```sql
CREATE TABLE ae_tasks (
    idempotency_key VARCHAR(255) PRIMARY KEY,
    zone_id INT NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL,  -- pending, leased, running, waiting_command, completed, skipped, failed, conflict, expired, cancelled
    result JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Очистка выполняется scheduled cleanup job / partition policy
CREATE INDEX idx_ae_tasks_created_at ON ae_tasks (created_at);
```

При повторном запросе с тем же `idempotency_key`:
- Если задача уже completed → вернуть cached result
- Если задача in-progress → вернуть `status: "in_progress"`
- Если задача failed → можно retry (сброс записи)

### 12.4 Safety: нет глобального мутабельного состояния

**AE2 (проблема):**
```python
# Глобальные переменные в main_runtime_shared.py:
_scheduler_writer_active_since: Dict[int, float] = {}  # без lock!
_last_db_circuit_open_alert_at: float = 0.0             # без lock!
```

**AE3 (решение):**
```python
# Всё состояние в ZoneContext (immutable на время задачи)
# Всё между задачами — в БД
# Единственный mutable state — _zone_locks (asyncio.Lock, thread-safe в asyncio)
```

---

## 13. Обработка ошибок

### 13.1 Уровни ошибок

| Уровень | Пример | Обработка |
|---------|--------|-----------|
| **Transient** | DB timeout, network error | Retry через scheduler |
| **Business** | flow_inactive, water_level_low | Skip, вернуть reason |
| **Fatal** | zone_not_found, unknown_task_type | Reject, не retry |
| **Safety** | safety_bounds_violated | Block + alert |

### 13.2 Retry policy

AE3 **не делает retry сам**. Он возвращает статус scheduler-у, и scheduler решает:

```python
# В ответе AE3:
{
  "status": "error",
  "error": "db_timeout",
  "retryable": True,       # scheduler может retry
  "retry_after_sec": 10    # рекомендуемая задержка
}
```

### 13.3 Circuit Breakers

```python
@dataclass
class AppDeps:
    """Зависимости приложения. Создаются один раз при старте."""
    db: Database
    command_bus: CommandBus
    config_cache: ConfigCache

    # Circuit breakers (stateful, но thread-safe)
    db_circuit_breaker: CircuitBreaker
    api_circuit_breaker: CircuitBreaker   # history-logger
    laravel_circuit_breaker: CircuitBreaker
```

Circuit breaker-ы — единственный stateful компонент кроме `_zone_locks`. Они thread-safe по дизайну.

---

## 14. Observability

### 14.1 Prometheus метрики

```python
# Задачи
TASK_RECEIVED    = Counter("ae3_task_received_total", "Tasks received", ["task_type"])
TASK_COMPLETED   = Counter("ae3_task_completed_total", "Tasks completed", ["task_type", "status"])
TASK_SKIPPED     = Counter("ae3_task_skipped_total", "Tasks skipped", ["task_type", "reason"])
TASK_DURATION    = Histogram("ae3_task_duration_seconds", "Task execution time", ["task_type"])
TASK_QUEUE_SIZE  = Gauge("ae3_task_queue_size", "Pending tasks in queue")

# Команды
COMMANDS_SENT    = Counter("ae3_commands_sent_total", "Commands sent", ["zone_id", "cmd"])
COMMANDS_FAILED  = Counter("ae3_commands_failed_total", "Commands failed", ["zone_id", "cmd"])

# PID
PID_OUTPUT       = Histogram("ae3_pid_output_ml", "PID output dose", ["zone_id", "type"])
PID_ERROR        = Gauge("ae3_pid_error", "Current PID error", ["zone_id", "type"])

# Workflow
WORKFLOW_PHASE   = Gauge("ae3_workflow_phase", "Current phase (encoded)", ["zone_id"])
WORKFLOW_TRANSITIONS = Counter("ae3_workflow_transitions_total", "Phase transitions", ["from", "to"])
```

### 14.2 Structured logging

```python
# Каждый лог содержит task context
logger.info(
    "Task executed",
    extra={
        "task_id": ctx.task_id,
        "zone_id": ctx.zone_id,
        "task_type": ctx.task_type,
        "correlation_id": ctx.correlation_id,
        "workflow_phase": ctx.workflow_phase.value,
        "duration_ms": elapsed_ms,
        "commands_sent": len(result.commands_sent),
    }
)
```

### 14.3 Zone Events (audit log)

Каждое действие записывается в `zone_events`:

```
TASK_RECEIVED        — задача получена
TASK_SKIPPED         — задача пропущена (с причиной)
TASK_COMPLETED       — задача выполнена
TASK_FAILED          — задача завершилась ошибкой
COMMAND_DISPATCHED   — команда отправлена
WORKFLOW_PHASE_CHANGED — фаза workflow изменилась
CORRECTION_APPLIED   — коррекция pH/EC применена
SAFETY_VIOLATION     — нарушение safety bounds
```

---

## 15. Миграция AE2 → AE3

### 15.1 Этапы

1. **Фаза 0 (compat bootstrap)** — добавить `ae_tasks/*`, bridge-контракты и interlock (`AE3C_INTERLOCK_ENFORCE=1`) без смены внешнего API.
2. **Фаза 1 (dual-write)** — при `start-cycle` accepted intent создавать root task в `ae_tasks` и фиксировать links `intent <-> task`.
3. **Фаза 2 (executor rollout)** — включать AE3 executor по canary зонам, сохраняя `start-cycle` внешний вход.
4. **Фаза 3 (strict FSM + command gate)** — enforce strict transitions и `DONE-only` для actuator-команд.
5. **Фаза 4 (poller bridge)** — `GET /internal/tasks/{task_id}` с поддержкой `intent-<id>` alias + status mapping.
6. **Фаза 5 (optional direct enqueue)** — включать `AE3C_ENABLE_SCHEDULER_DIRECT_ENQUEUE=1` только после SLO-stable и shadow parity.
7. **Фаза 6 (deprecation)** — удалять legacy intent/fallback path только после подтвержденной стабильности.

### 15.2 Обратная совместимость

На время миграции:
- `POST /zones/{id}/start-cycle` остается canonical wake-up endpoint.
- Poller сохраняет compatibility формат `task_id=intent-<id>` до полного cutover.
- `ae_tasks.status` маппится в poller vocabulary `accepted|completed|failed|cancelled|not_found`.
- scheduler legacy `task_type` contract сохраняется до direct-enqueue migration gate.

---

## 16. Структура файлов AE3

```
backend/services/automation-engine/
├── ae3/
│   ├── __init__.py
│   ├── app.py                    # FastAPI app, инициализация AppDeps
│   ├── api/
│   │   ├── tasks.py              # POST /internal/tasks/enqueue
│   │   ├── manual.py             # POST /zones/{id}/manual-action
│   │   ├── state.py              # GET /zones/{id}/state, /workflow
│   │   └── contracts.py          # Pydantic модели request/response
│   ├── core/
│   │   ├── task_router.py        # TaskRouter
│   │   ├── task_executor.py      # TaskExecutor
│   │   ├── zone_context.py       # ZoneContext + build_zone_context()
│   │   └── errors.py             # InvalidTransitionError, ConcurrentModificationError, ...
│   ├── controllers/
│   │   ├── base.py               # Controller protocol, TaskResult, NextTask
│   │   ├── correction.py         # CorrectionController (pH/EC)
│   │   ├── irrigation.py         # IrrigationController
│   │   ├── recirculation.py      # RecirculationController
│   │   ├── climate.py            # ClimateController
│   │   ├── lighting.py           # LightingController
│   │   ├── workflow.py           # WorkflowController (two-tank)
│   │   ├── health.py             # HealthController
│   │   └── diagnostics.py        # DiagnosticsController
│   ├── workflow/
│   │   ├── fsm.py                # WorkflowPhase enum, TRANSITIONS, transition()
│   │   ├── persistence.py        # save_workflow_transition()
│   │   └── two_tank.py           # команды для two-tank шагов
│   ├── pid/
│   │   ├── adaptive_pid.py       # AdaptivePid (из utils/, без изменений)
│   │   ├── state.py              # PidState dataclass
│   │   ├── persistence.py        # save/load pid_state из БД
│   │   └── autotune.py           # RelayAutotuner (из utils/, без изменений)
│   ├── infrastructure/
│   │   ├── command_bus.py        # CommandBus (упрощённый)
│   │   ├── database.py           # Database connection pool
│   │   ├── config_cache.py       # ConfigCache (TTL-based)
│   │   └── circuit_breaker.py    # CircuitBreaker
│   └── config/
│       └── settings.py           # AutomationSettings
├── tests/
│   ├── test_controllers/
│   │   ├── test_correction.py
│   │   ├── test_irrigation.py
│   │   ├── test_climate.py
│   │   ├── test_lighting.py
│   │   └── test_workflow.py
│   ├── test_core/
│   │   ├── test_task_executor.py
│   │   ├── test_zone_context.py
│   │   └── test_fsm.py
│   └── test_pid/
│       ├── test_adaptive_pid.py
│       └── test_persistence.py
```

---

## 17. Сценарий: наполнение баков (пошагово)

Ниже — полный пошаговый сценарий startup two-tank системы. Каждый шаг — отдельная задача от scheduler-а (или next_task от предыдущей).

### Физическая схема

```
                     ┌─────────────────┐
                     │  ВОДОПРОВОД      │
                     └────────┬────────┘
                              │
                     [valve_clean_fill]
                              │
                     ┌────────▼────────┐
                     │  ЧИСТЫЙ БАК      │
                     │                  │
                     │  level_clean_max │ ← binary (0/1)
                     │  level_clean_min │ ← binary (0/1)
                     └────────┬────────┘
                              │
                     [valve_clean_supply]
                              │
              ┌───────────────▼───────────────┐
              │         БАК РАСТВОРА           │
              │                                │
              │   level_solution_max           │ ← binary (0/1)
              │   level_solution_min           │ ← binary (0/1)
              │                                │
              │   ← pH сенсор                  │
              │   ← EC сенсор                  │
              │                                │
              └───────┬───────────────┬────────┘
                      │               │
             [valve_solution_fill]  [valve_solution_supply]
                      │               │
                      │          ┌────▼─────┐
                      │          │ РАСТЕНИЯ  │
                      │          │(капельницы)│
                      │          └────┬─────┘
                      │               │
                      └──[pump_main]──┘
                     (рециркуляция)
```

### Шаг 0: Запуск цикла

```
Scheduler (или оператор):
  POST /internal/tasks/enqueue {
    task_type: "workflow_step",
    zone_id: 447,
    payload: { workflow_step: "startup" }
  }
```

**AE3 проверяет:**
- Все критические узлы онлайн?
- Зона в фазе `idle`?
- irr_state (состояние клапанов): pump_main=OFF?

**AE3 отправляет команду:**
```
valve_clean_fill → set_relay { state: true }   # открыть подачу воды
```

**AE3 возвращает:**
```json
{
  "status": "completed",
  "state_updates": { "workflow_transition_event": "start_filling" },
  "next_tasks": [{
    "task_type": "workflow_step",
    "delay_seconds": 30,
    "payload": { "workflow_step": "clean_fill_check" }
  }]
}
```

**FSM:** `idle` → `tank_filling`

### Шаг 1: Проверка заполнения чистого бака (polling)

```
Scheduler (через 30 сек):
  POST /internal/tasks/enqueue {
    task_type: "workflow_step",
    zone_id: 447,
    payload: { workflow_step: "clean_fill_check" }
  }
```

**AE3 читает телеметрию:**
```sql
SELECT sensor_type, last_value FROM telemetry_last
WHERE zone_id = 447 AND sensor_type IN ('level_clean_max', 'level_clean_min')
```

**Вариант A: бак ещё не полный** (`level_clean_max = 0`)
```json
{
  "status": "completed",
  "next_tasks": [{
    "task_type": "workflow_step",
    "delay_seconds": 30,
    "payload": { "workflow_step": "clean_fill_check" }
  }]
}
```
Scheduler перешлёт ту же задачу через 30 сек. Цикл повторяется до заполнения или таймаута.

**Вариант B: бак полный** (`level_clean_max = 1, level_clean_min = 1`)

AE3 отправляет:
```
valve_clean_fill → set_relay { state: false }   # закрыть подачу воды
```

AE3 возвращает:
```json
{
  "status": "completed",
  "next_tasks": [{
    "task_type": "workflow_step",
    "delay_seconds": 5,
    "payload": { "workflow_step": "solution_fill_start" }
  }]
}
```

**Вариант C: таймаут** (прошло > 1200 сек с начала)
```json
{
  "status": "failed",
  "errors": ["clean_fill_timeout"],
  "next_tasks": []
}
```
Scheduler решает: retry или alert оператору.

### Шаг 2: Запуск заполнения бака раствора

```
Scheduler (через 5 сек):
  POST /internal/tasks/enqueue {
    task_type: "workflow_step",
    zone_id: 447,
    payload: { workflow_step: "solution_fill_start" }
  }
```

**AE3 выполняет:**

1. Активирует sensor mode для pH/EC узлов (чтобы начали отправлять телеметрию)
2. Ждёт стабилизации сенсоров (60 сек — закладывается в delay_seconds)

**Команды:**
```
valve_clean_supply  → set_relay { state: true }   # чистая вода → бак раствора
valve_solution_fill → set_relay { state: true }   # рециркуляция раствора
pump_main           → set_relay { state: true }   # включить насос
```

**AE3 возвращает:**
```json
{
  "status": "completed",
  "next_tasks": [{
    "task_type": "workflow_step",
    "delay_seconds": 90,
    "payload": { "workflow_step": "solution_fill_check" }
  }]
}
```

Delay 90 сек = 60 сек стабилизация сенсоров + 30 сек первый poll.

### Шаг 3: Проверка заполнения бака раствора (polling)

```
Scheduler (через 90 сек):
  POST /internal/tasks/enqueue {
    task_type: "workflow_step",
    zone_id: 447,
    payload: { "workflow_step": "solution_fill_check" }
  }
```

**AE3 читает:**
```sql
-- Уровень воды
SELECT sensor_type, last_value FROM telemetry_last
WHERE zone_id = 447 AND sensor_type IN ('level_solution_max', 'level_solution_min')

-- Качество раствора
SELECT sensor_type, last_value FROM telemetry_last
WHERE zone_id = 447 AND sensor_type IN ('PH', 'EC')
```

**Вариант A: бак не полный** — перезапуск poll через 30 сек.

**Вариант B: бак полный** (`level_solution_max = 1`)

AE3 останавливает заполнение:
```
pump_main           → set_relay { state: false }
valve_solution_fill → set_relay { state: false }
valve_clean_supply  → set_relay { state: false }
```

Проверяет целевые значения pH/EC:
- `target_ph = 6.0` (из рецепта)
- `target_ec_prepare = 0.8` (EC для подготовки, обычно NPK only)
- `prepare_tolerance = { ph_pct: 5%, ec_pct: 25% }`

Если pH в пределах 5.7-6.3 и EC в пределах 0.6-1.0 → **READY!**

```json
{
  "status": "completed",
  "state_updates": { "workflow_transition_event": "filling_complete" },
  "next_tasks": []
}
```

**FSM:** `tank_filling` → `tank_recirc` (промежуточно) → `ready`

Если pH/EC не в целевых пределах → **рециркуляция:**

```json
{
  "status": "completed",
  "state_updates": { "workflow_transition_event": "filling_complete" },
  "next_tasks": [{
    "task_type": "workflow_step",
    "delay_seconds": 5,
    "payload": { "workflow_step": "prepare_recirc_start" }
  }]
}
```

**FSM:** `tank_filling` → `tank_recirc`

### Шаг 4: Подготовка рециркуляцией (если нужна)

```
Scheduler:
  POST /internal/tasks/enqueue {
    task_type: "workflow_step",
    zone_id: 447,
    payload: { "workflow_step": "prepare_recirc_start" }
  }
```

**Команды:**
```
valve_solution_supply → set_relay { state: true }
valve_solution_fill   → set_relay { state: true }
pump_main             → set_relay { state: true }
```

Раствор циркулирует по контуру: бак → насос → бак. Сенсоры pH/EC измеряют в реальном времени.

**AE3 возвращает:**
```json
{
  "next_tasks": [{
    "task_type": "workflow_step",
    "delay_seconds": 60,
    "payload": { "workflow_step": "prepare_recirc_check" }
  }]
}
```

### Шаг 5: Проверка готовности раствора (polling)

```
Scheduler (через 60 сек):
  POST /internal/tasks/enqueue {
    task_type: "workflow_step",
    zone_id: 447,
    payload: { "workflow_step": "prepare_recirc_check" }
  }
```

**AE3 читает pH/EC и сравнивает с целевыми:**

| Параметр | Текущий | Цель | Tolerance | В норме? |
|----------|---------|------|-----------|----------|
| pH | 5.85 | 6.0 | ±5% (5.7-6.3) | Да |
| EC | 0.72 | 0.8 | ±25% (0.6-1.0) | Да |

**Вариант A: в норме**

Останавливаем рециркуляцию:
```
pump_main             → set_relay { state: false }
valve_solution_fill   → set_relay { state: false }
valve_solution_supply → set_relay { state: false }
```

```json
{
  "status": "completed",
  "state_updates": { "workflow_transition_event": "recirc_complete" },
  "next_tasks": []
}
```

**FSM:** `tank_recirc` → `ready`

**Зона готова к поливу!** Scheduler может начать отправлять `irrigation_start`, `correction_ph`, `correction_ec`, `climate_check`, `lighting_check`.

**Вариант B: не в норме** — перезапуск poll через 60 сек.

**Вариант C: таймаут** (1200 сек) — останавливаем насос, ошибка.

---

## 18. Сценарий: коррекция pH (пошагово)

Коррекция pH запускается scheduler-ом каждые 90 секунд, пока зона в одной из фаз: `tank_filling`, `tank_recirc`, `irrigating`, `irrig_recirc`.

### Шаг 0: Scheduler отправляет задачу

```
POST /internal/tasks/enqueue {
  task_type: "correction_ph",
  zone_id: 447,
  idempotency_key: "sch:z447:correction_ph:2026-03-05T10:30:00Z"
}
```

### Шаг 1: Построение ZoneContext

AE3 загружает всё состояние 3 SQL запросами:

```sql
-- Запрос 1: workflow + flags + PID state
SELECT
    ws.workflow_phase,                      -- 'irrigating'
    cf.flow_active, cf.stable,              -- true, true
    cf.corrections_allowed, cf.updated_at,  -- true, '2026-03-05T10:29:45Z'
    ps.integral, ps.prev_error,             -- 2.34, -0.12
    ps.prev_derivative, ps.last_dose_at   -- 0.01, '2026-03-05T10:28:30Z'
FROM zones z
LEFT JOIN zone_workflow_state ws ON ws.zone_id = z.id
LEFT JOIN zone_correction_flags cf ON cf.zone_id = z.id
LEFT JOIN pid_state ps ON ps.zone_id = z.id AND ps.pid_type = 'ph'
WHERE z.id = 447;

-- Запрос 2: телеметрия
SELECT sensor_type, last_value, last_ts FROM telemetry_last WHERE zone_id = 447;
-- Результат: PH=6.35, EC=1.21, TEMPERATURE=24.5, ...

-- Запрос 3: узлы
SELECT zn.node_uid, zn.channel, n.type, n.status
FROM zone_nodes zn JOIN nodes n ON n.uid = zn.node_uid
WHERE zn.zone_id = 447;
-- Результат: ph_node/pump_acid, ph_node/pump_base, ...
```

### Шаг 2: can_execute() — проверка предусловий

```
✓ workflow_phase = 'irrigating' → в CORRECTION_ALLOWED_PHASES
✓ correction_flags.is_fresh(300) → updated 15 сек назад → свежие
✓ flow_active = true → поток есть
✓ stable = true → сенсор стабилен
✓ corrections_allowed = true → коррекции разрешены
✓ telemetry.PH.last_ts = 10 сек назад → свежая
✓ water_levels.is_ok() → датчики уровня OK
→ can_execute = True
```

### Шаг 3: PID вычисление

```
Входные данные:
  current_ph = 6.35
  target_ph  = 6.00
  error      = 6.00 - 6.35 = -0.35  (нужно подкислить)

Выбор зоны PID:
  |error| = 0.35
  dead_zone  = 0.05 → 0.35 > 0.05 → не dead
  close_zone = 0.30 → 0.35 > 0.30 → не close
  → зона FAR

Коэффициенты FAR зоны:
  Kp = 8.0, Ki = 0.02, Kd = 0.0

Восстановление PID из БД:
  integral = 2.34 (из pid_state)
  prev_error = -0.12
  last_dose_at = 10:28:30 (90 сек назад → min_interval 90с пройден)

PID compute:
  dt = 90 сек
  proportional = Kp * error = 8.0 * (-0.35) = -2.80
  integral_new = 2.34 + ((-0.35) * 90) = 2.34 + (-31.5) = -29.16
  integral_clamped = max(-100, min(-29.16, 100)) = -29.16
  integral_term = Ki * integral = 0.02 * (-29.16) = -0.58
  derivative_raw = ((-0.35) - (-0.12)) / 90 = -0.0026
  derivative_term = Kd * derivative = 0
  raw_output = -2.80 + (-0.58) + 0 = -3.38

  output = abs(raw_output) = 3.38 мл
  output_clamped = min(3.38, max_output=20) = 3.38 мл
```

### Шаг 4: Определение направления коррекции

```
error = -0.35 (pH выше цели)
→ correction_type = "add_acid" (нужно понизить pH)
→ actuator = { node_uid: "ph_node", channel: "pump_acid" }
```

### Шаг 5: Построение команды

```python
CommandRecord(
    node_uid="ph_node",
    channel="pump_acid",
    cmd="pump_dose",
    params={
        "ml": 3.38,
        "mode": "continuous"
    }
)
```

### Шаг 6: TaskResult

```json
{
  "success": true,
  "commands_sent": [{
    "node_uid": "ph_node",
    "channel": "pump_acid",
    "cmd": "pump_dose",
    "params": { "ml": 3.38 }
  }],
  "next_tasks": [],
  "state_updates": {
    "pid_state": {
      "integral": -29.16,
      "prev_error": -0.35,
      "prev_derivative": -0.0026,
      "last_dose_at": "2026-03-05T10:30:00Z",
      "current_zone": "far",
      "corrections_count": 15
    }
  },
  "metrics": {
    "correction_dose_ml": 3.38,
    "error": 0.35,
    "pid_integral": -29.16,
    "pid_zone": "far"
  }
}
```

### Шаг 7: TaskExecutor сохраняет

1. Команда отправлена через CommandBus → `POST history-logger:9300/commands`
2. PID state сохранён в `pid_state`
3. Zone event записан: `PH_CORRECTION { ml: 3.38, direction: add_acid }`

### Шаг 8: Через 90 сек — следующая коррекция

Scheduler отправляет `correction_ph` снова. AE3 повторяет процесс.

Если pH сместился к 6.12:
```
error = 6.00 - 6.12 = -0.12
|error| = 0.12 → зона CLOSE (Kp=5.0, Ki=0.05)
→ меньшая доза (≈0.6 мл)
```

Если pH в dead zone (5.95-6.05):
```
|error| = 0.03 → зона DEAD
→ output = 0 (skip, PID не дозирует)
```

---

## 19. Сценарий: коррекция EC (пошагово, с компонентами)

EC коррекция сложнее pH, потому что EC состоит из нескольких питательных компонентов.

### Фаза-зависимые компоненты

```
tank_filling, tank_recirc  → добавляем только ["npk"]
irrigating, irrig_recirc   → добавляем ["calcium", "magnesium", "micro"]
```

Логика: NPK добавляется при подготовке раствора, остальные компоненты — во время полива (чтобы избежать осаждения кальция с фосфатами NPK).

### Пример: коррекция EC во время полива

```
Scheduler:
  POST /internal/tasks/enqueue { task_type: "correction_ec", zone_id: 447 }

Контекст:
  current_ec = 1.05
  target_ec  = 1.20
  error      = 1.20 - 1.05 = +0.15 (нужно добавить питание)
  workflow_phase = "irrigating"
  → компоненты: ["calcium", "magnesium", "micro"]
```

**PID вычисляет суммарную дозу:**
```
Зона CLOSE (|0.15| < 0.30):
  Kp = 30.0, Ki = 0.30
  proportional = 30.0 * 0.15 = 4.5
  integral_term = 0.30 * integral = ...
  output = 12.5 мл (суммарно на все компоненты)
```

**Разбивка по компонентам (из рецепта):**
```
calcium:   40% × 12.5 = 5.0 мл
magnesium: 35% × 12.5 = 4.375 мл
micro:     25% × 12.5 = 3.125 мл
```

**Последовательная отправка:**
```
Шаг 1: pump_calcium  → pump_dose { ml: 5.0 }
        ↓ (пауза 8 сек — dose_delay_sec)
Шаг 2: Проверка EC: current_ec = 1.12 (< target 1.20) → продолжаем
        pump_magnesium → pump_dose { ml: 4.375 }
        ↓ (пауза 8 сек)
Шаг 3: Проверка EC: current_ec = 1.18 (< target 1.20 - 0.05) → продолжаем
        pump_micro → pump_dose { ml: 3.125 }

Итого: 3 команды, 16 сек между компонентами
```

**Если EC достигнут раньше:**
```
Шаг 1: pump_calcium → pump_dose { ml: 5.0 }
        ↓ (пауза 8 сек)
Шаг 2: Проверка EC: current_ec = 1.19 (>= target 1.20 - tolerance 0.05)
        → СТОП. Не дозируем magnesium и micro.
```

**Если команда не прошла (например, node offline):**
```
Шаг 1: pump_calcium → pump_dose { ml: 5.0 } → SUCCESS
Шаг 2: pump_magnesium → pump_dose { ml: 4.375 } → FAILED!
        → Компенсация: НЕ отменяем calcium (уже влит)
        → Ошибка в TaskResult, scheduler retry через 120 сек
```

---

## 20. Таймлайн: полный день работы зоны

```
06:00  lighting_check    → свет ВКЛ (фотопериод 06:00-22:00, PWM=75%)
06:01  climate_check     → температура 22°C, вентилятор OFF
06:02  health_check      → все узлы online, телеметрия свежая

06:30  correction_ph     → pH=6.02, dead zone → skip
06:32  correction_ec     → EC=1.18, close zone → dose 2.1 мл NPK

07:00  irrigation_start  → pump_main ON, valve_irrigation ON
07:02  correction_ph     → pH=5.92, dead zone → skip
07:04  correction_ec     → EC=1.15, close zone → dose calcium 3.2 мл

07:05  irrigation_stop   → pump_main OFF (после 5 мин полива)
       → next_task: recirculation_start через 5 сек

07:05  recirculation_start → valve_solution_supply ON, pump_main ON
       → next_task: recirculation_stop через 300 сек

07:10  recirculation_stop  → pump_main OFF, все valve OFF
       → FSM: irrig_recirc → ready

07:12  correction_ph     → pH=6.15, close zone → dose acid 1.8 мл
07:14  correction_ec     → EC=1.08, close zone → dose calcium 5.0 мл + magnesium 3.5 мл

08:00  irrigation_start  → следующий цикл полива
...

22:00  lighting_check    → свет ВЫКЛ (конец фотопериода)
22:01  climate_check     → температура 20°C, в норме
```

---

## 21. Итого: что решает AE3

| Проблема AE2 | Решение AE3 |
|---------------|-------------|
| Polling loop 15 сек (wasted work) | Event-driven: задачи по запросу |
| God object ZoneAutomationService (55 methods) | Отдельные Controller классы |
| 30+ callback в process_zone_cycle | Controller.execute(ctx, deps) |
| Глобальные dict-ы без lock | ZoneContext (immutable) + per-zone asyncio.Lock |
| Soft workflow FSM (warning, не block) | Strict FSM (exception на невалидный переход) |
| PID state в памяти (теряется при рестарте) | Персистенция в БД (pid_state) |
| N+1 SQL запросы (6+ на зону) | Batch загрузка (3 запроса на ZoneContext) |
| Repos создаются каждый тик | AppDeps — singleton на lifetime процесса |
| AE сам решает "что делать" | Scheduler решает "что и когда", AE — "как" |
| min_interval теряется при рестарте | last_dose_at в БД → восстановление guard |
| Anomaly critical override (опасно) | Строгая блокировка + алерт оператору |
| Потеря pending состояния команд при рестарте | Durable tracking: `ae_task_commands` + `ae_command_outbox` + reconcile |
| Отсутствие idempotency | `ae_tasks(idempotency_key)` + poller bridge |
