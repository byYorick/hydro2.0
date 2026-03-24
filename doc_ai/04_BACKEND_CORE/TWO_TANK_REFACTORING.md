# Two-Tank Automation: Plan Рефакторинга

**Версия:** 1.0
**Дата:** 2026-03-03
**Сервис:** `backend/services/automation-engine`
**Ветка:** создать `feature/two-tank-refactoring` от `main`

---

## Контекст и мотивация

Двухбаковая система автоматики реализована в `backend/services/automation-engine` и управляет физическим оборудованием: насосами, клапанами, датчиками уровня, pH/EC.

### Текущие проблемы (по приоритету)

| Приоритет | Проблема | Файл |
|-----------|----------|------|
| 🔴 Критично | `valve_irrigation` не восстанавливается после recovery | `executor/two_tank_runtime_config.py:48` |
| 🔴 Критично | `can_run_pump` обёрнут в feature flag — отключаемая защита насоса | `executor/two_tank_phase_starters_*.py` |
| 🔴 Критично | Нет concurrency guard — две задачи для одной зоны могут запуститься одновременно | отсутствует |
| 🟠 Высокий | `degraded_tolerance` — молчаливое продолжение с off-spec раствором | `domain/workflows/two_tank_recovery_core.py` |
| 🟠 Высокий | `manual_step` обходит irr_state guard | `domain/workflows/two_tank_core.py` |
| 🟠 Высокий | Нет min-level проверки для бака раствора | `domain/workflows/two_tank_startup_solution_branch.py` |
| 🟡 Средний | `_resolve_primary_pump_channel` copy-paste в 3 файлах | `executor/two_tank_phase_starters_*.py` |
| 🟡 Средний | IRR state busy-wait (до 20 SQL запросов на проверку) | `domain/workflows/two_tank_irr_state_helpers.py` |
| 🟡 Средний | Молчаливые дефолты pH/EC без warning | `executor/two_tank_runtime_config.py:209` |
| 🟡 Средний | Две архитектуры одновременно: `self` в workflow core vs explicit deps в starters | весь `domain/workflows/` |
| 🟢 Низкий | ~150 дублирующихся error-dict без базового конструктора | весь two-tank |
| 🟢 Низкий | Safety guards — зонтичный feature flag вместо явной конфигурации | `executor/two_tank_phase_starters_*.py` |

### Архитектура сейчас

```
SchedulerTaskExecutor (большой класс)
  └── executor_bound_two_tank_methods.py  (bridge: self → policy_delegate)
      └── executor_method_delegates.py    (bridge: executor= → start_fn(*_fn=...))
          └── executor/two_tank_phase_starters_*.py  (explicit deps) ✓

domain/workflows/two_tank_core.py         (self напрямую) ✗ несовместимо
domain/workflows/two_tank_startup_*.py    (self напрямую) ✗
domain/workflows/two_tank_recovery_core.py (self напрямую) ✗
```

### Целевая архитектура

```
SchedulerTaskExecutor
  └── _build_two_tank_deps(zone_id) → TwoTankDeps (dataclass)
      └── domain/workflows/two_tank_*.py  (deps: TwoTankDeps) ✓
          └── executor/two_tank_phase_starters_*.py (explicit deps) ✓
```

### FSM состояний

```
idle → tank_filling → tank_recirc → ready → irrigating → irrig_recirc → irrigating
                                                 ↑_________________________________|
```

Переходы определены в `executor/workflow_phase_policy.py`. В текущей реализации нет **enforcement** — порядок не гарантируется.

---

## Разделение работы между агентами

| Агент | Фокус | Фазы | Зависимости |
|-------|-------|-------|-------------|
| **Агент 1** | Критические баги + консолидация | Phase 0, Phase 1 | Нет (начинает первым) |
| **Агент 2** | Архитектурный рефакторинг | Phase 2, Phase 4, Phase 5 | Ждёт завершения Phase 0.2 от Агента 1 |
| **Агент 3** | Инфраструктура и долгосрочные изменения | Phase 3, Phase 6, Phase 7, Phase 8 | Phase 3 независим; остальные после Агента 2 |

**Порядок запуска:** Агент 1 → (Агент 2 и Агент 3 параллельно, но Агент 2 ждёт merge Phase 0)

---

---

# АГЕНТ 1: Критические баги и консолидация

## Прочитать сначала

1. `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`
2. `backend/services/automation-engine/executor/two_tank_runtime_config.py`
3. `backend/services/automation-engine/executor/two_tank_phase_starters_startup.py`
4. `backend/services/automation-engine/executor/two_tank_phase_starters_prepare.py`
5. `backend/services/automation-engine/executor/two_tank_phase_starters_recovery.py`
6. `backend/services/automation-engine/domain/workflows/two_tank_recovery_core.py`
7. `backend/services/automation-engine/domain/workflows/two_tank_startup_solution_branch.py`
8. `backend/services/automation-engine/domain/workflows/two_tank_core.py`
9. `backend/services/automation-engine/executor/executor_constants.py` — для констант ошибок

## Phase 0: Hotfixes (критические баги)

### 0.1 Восстановление `valve_irrigation` после recovery

**Файл:** `backend/services/automation-engine/executor/two_tank_runtime_config.py`

**Проблема:** `irrigation_recovery_start` закрывает `valve_irrigation` (`state: False`) для перенаправления потока на рециркуляцию. Но `irrigation_recovery_stop` его **не открывает**. После recovery система переходит в фазу `irrigating`, но клапан физически закрыт — полив не работает.

**Что сделать:** В функции `default_two_tank_command_plan`, в плане `irrigation_recovery_stop`, добавить команду восстановления `valve_irrigation` в конец:

```python
"irrigation_recovery_stop": [
    {"channel": "pump_main",             "cmd": "set_relay", "params": {"state": False}},
    {"channel": "valve_solution_fill",   "cmd": "set_relay", "params": {"state": False}},
    {"channel": "valve_solution_supply", "cmd": "set_relay", "params": {"state": False}},
    # ДОБАВИТЬ:
    {"channel": "valve_irrigation",      "cmd": "set_relay", "params": {"state": True}},
],
```

**Важно:** `valve_irrigation` должен быть последним в списке (после остановки насоса и закрытия supply-клапанов).

**Тест:** Добавить тест-кейс в `test_two_tank_runtime_config.py` проверяющий, что `default_two_tank_command_plan("irrigation_recovery_stop")` содержит `{"channel": "valve_irrigation", "params": {"state": True}}`.

---

### 0.2 Вынести `can_run_pump` из-под feature flag

**Файлы:**
- `backend/services/automation-engine/executor/two_tank_phase_starters_startup.py` — функция `start_two_tank_solution_fill`
- `backend/services/automation-engine/executor/two_tank_phase_starters_prepare.py` — функция `start_two_tank_prepare_recirculation`
- `backend/services/automation-engine/executor/two_tank_phase_starters_recovery.py` — функция `start_two_tank_irrigation_recovery`

**Проблема:** `can_run_pump` сейчас обёрнут в `if safety_guards_enabled`. Это сделало физическую защиту насоса отключаемой feature flag-ом. `safety_guards_enabled` был предназначен только для одного: "блокировать retry если stop не подтверждён".

**Что сделать** во всех трёх функциях:

```python
# БЫЛО (неверно):
safety_guards_enabled = bool(two_tank_safety_guards_enabled_fn())
if safety_guards_enabled:
    pump_channel = _resolve_primary_pump_channel(...)
    can_run, safety_error = await can_run_pump(...)
    if not can_run:
        return {..., "feature_flag_state": safety_guards_enabled}

plan_result = await dispatch_two_tank_command_plan_fn(...)
...
if self._two_tank_safety_guards_enabled() and not stop_result.get("success"):
    ...

# ДОЛЖНО БЫТЬ:
# 1. can_run_pump — ВСЕГДА, без условия
pump_channel = _resolve_primary_pump_channel(...)
can_run, safety_error = await can_run_pump(...)
if not can_run:
    return {...}  # убрать "feature_flag_state" из этого return

plan_result = await dispatch_two_tank_command_plan_fn(...)
...
# 2. safety_guards_enabled — ТОЛЬКО для retry guard
safety_guards_enabled = bool(two_tank_safety_guards_enabled_fn())
if safety_guards_enabled and not stop_result.get("success"):
    ...
```

**Примечание:** В `start_two_tank_clean_fill` нет `can_run_pump` — это правильно, `clean_fill` не использует насос (только `valve_clean_fill`).

**Тест:** Добавить в `test_two_tank_phase_starters_safety.py` тесты, подтверждающие, что `can_run_pump` вызывается при `safety_guards_enabled=False`.

---

### 0.3 Warning при использовании дефолтных pH/EC таргетов

**Файл:** `backend/services/automation-engine/executor/two_tank_runtime_config.py`

**Проблема:** Если `target_ph` и `target_ec` не сконфигурированы ни в одном из источников, система молча использует `ph=5.8, ec=1.6`.

**Что сделать:** После блока резолюции в `resolve_two_tank_runtime_config`, добавить warning если оба значения пришли из дефолта:

```python
import logging
_logger = logging.getLogger(__name__)

# После вычисления target_ph и target_ec:
if target_ph_raw is None and target_ec_raw is None:
    _logger.warning(
        "Zone two_tank: both target_ph and target_ec resolved to defaults "
        "(ph=%.2f ec=%.3f) — targets not configured in payload or execution config",
        target_ph, target_ec,
    )
```

---

## Phase 1: Консолидация

### 1.1 Устранить copy-paste `_resolve_primary_pump_channel`

**Создать файл:** `backend/services/automation-engine/executor/two_tank_common.py`

```python
"""Shared utilities for two-tank phase starters."""
from __future__ import annotations
from typing import Any


def resolve_primary_pump_channel(command_plan: Any) -> str:
    """Extract the first pump channel from a command plan list.

    Returns 'pump_main' as fallback if no pump channel found.
    """
    if isinstance(command_plan, list):
        for item in command_plan:
            if not isinstance(item, dict):
                continue
            channel = str(item.get("channel") or "").strip().lower()
            if channel.startswith("pump"):
                return channel
    return "pump_main"


__all__ = ["resolve_primary_pump_channel"]
```

**Изменить** в трёх файлах:
- `two_tank_phase_starters_startup.py` — удалить `_resolve_primary_pump_channel`, добавить `from executor.two_tank_common import resolve_primary_pump_channel`
- `two_tank_phase_starters_prepare.py` — то же
- `two_tank_phase_starters_recovery.py` — то же

**Тест:** Unit-тест для `resolve_primary_pump_channel` в `test_two_tank_command_plan_core.py`.

---

### 1.2 Min-level проверка для бака раствора

**Файл:** `backend/services/automation-engine/domain/workflows/two_tank_startup_solution_branch.py`

**Проблема:** При `solution_triggered` (уровень раствора достиг max) отсутствует проверка `solution_min` на несогласованность (аналог проверки для чистого бака). `solution_min_labels` есть в `runtime_cfg` но не используется.

**Что сделать:** В функции `handle_two_tank_solution_fill_check`, в ветке `if solution_triggered:`, перед `stop_result = await self._dispatch_two_tank_command_plan(...)` добавить:

```python
if solution_triggered:
    solution_min_level = await self._read_level_switch(
        zone_id=zone_id,
        sensor_labels=runtime_cfg["solution_min_labels"],
        threshold=runtime_cfg["level_switch_on_threshold"],
    )
    if solution_min_level["has_level"]:
        if self._telemetry_freshness_enforce() and solution_min_level["is_stale"]:
            return {
                "success": False,
                "task_type": "diagnostics",
                "mode": "two_tank_solution_min_level_stale",
                "workflow": workflow,
                "commands_total": 0, "commands_failed": 0,
                "action_required": True, "decision": "run",
                "reason_code": REASON_SENSOR_STALE_DETECTED,
                "reason": "Телеметрия датчика нижнего уровня бака раствора устарела",
                "error": ERR_TWO_TANK_LEVEL_STALE,
                "error_code": ERR_TWO_TANK_LEVEL_STALE,
            }
        if not solution_min_level["is_triggered"]:
            return build_sensor_state_inconsistent_result(
                workflow=workflow,
                reason="Несогласованность датчиков бака раствора: max=1 и min=0",
                clean_level_max=True,  # переиспользуем структуру
                clean_level_min=False,
            )
    # Если solution_min_level не has_level — только warning, не блокируем
    # (sensor_min может отсутствовать в конфигурации зоны)
    elif solution_min_level.get("expected_labels"):
        logger.warning(
            "Zone %s: solution min level sensor unavailable (non-blocking), "
            "expected=%s",
            zone_id,
            solution_min_level.get("expected_labels", runtime_cfg["solution_min_labels"]),
        )

    stop_result = await self._dispatch_two_tank_command_plan(...)  # существующий код
```

**Важно:** Для `solution_min` отсутствие данных — **предупреждение, не ошибка** (датчик может быть не установлен). Для чистого бака отсутствие данных — ошибка (датчик обязателен). Это отражает разницу в обязательности оборудования.

**Константы:** Добавить в `executor/executor_constants.py` если не существует:
```python
ERR_TWO_TANK_SOLUTION_MIN_LEVEL_STALE = "two_tank_solution_min_level_stale"
```

---

### 1.3 Явный алерт при degraded tolerance

**Файл:** `backend/services/automation-engine/domain/workflows/two_tank_recovery_core.py`

**Проблема:** Когда irrigation recovery завершается с `degraded_tolerance` (мягкие допуски), `action_required=False` и `success=True`. Полив возобновляется с off-spec раствором без каких-либо алертов.

**Что сделать:** В ветке `degraded_state["targets_reached"]` изменить:

```python
# Добавить эмит события до обновления фазы
await self._emit_task_event(
    zone_id=zone_id,
    task_type="diagnostics",
    context=context,
    event_type="IRRIGATION_RECOVERY_DEGRADED",  # отдельный тип события
    payload={
        "irrigation_recovery_attempt": attempt,
        "targets_state": degraded_state,
        "reason_code": REASON_IRRIGATION_RECOVERY_DEGRADED,
        "reason": "Полив возобновлён в degraded tolerance — pH/EC вне нормальных допусков",
        "action_required_human": True,  # сигнал для алерт-менеджера
    },
)

# Изменить в возвращаемом результате:
return {
    ...
    "action_required": True,   # БЫЛО False — изменить
    "decision": "skip",
    "degraded": True,           # новое поле для явной идентификации
    "reason_code": REASON_IRRIGATION_RECOVERY_DEGRADED,
    ...
}
```

**Добавить константу** в `executor/executor_constants.py`:
```python
REASON_IRRIGATION_RECOVERY_DEGRADED = "irrigation_recovery_degraded"
```

**Тест:** В `test_zone_sensor_mode_orchestrator.py` или новом файле проверить, что `action_required=True` и `degraded=True` при degraded success.

---

### 1.4 IRR state expectations для `clean_fill_check`

**Файл:** `backend/services/automation-engine/domain/workflows/two_tank_core.py`

**Проблема:** `_CRITICAL_IRR_STATE_EXPECTATIONS` не содержит `clean_fill_check`. Во время наполнения чистого бака ожидаемое состояние: `pump_main=False` (насос не должен работать при наполнении через гравитацию/водопровод).

**Что сделать:** Добавить в `_CRITICAL_IRR_STATE_EXPECTATIONS`:

```python
_CRITICAL_IRR_STATE_EXPECTATIONS: Dict[str, Dict[str, bool]] = {
    "startup": {
        "pump_main": False,
    },
    "clean_fill_check": {          # ДОБАВИТЬ
        "pump_main": False,
    },
    "solution_fill_check": {
        "valve_clean_supply": True,
        "valve_solution_fill": True,
        "pump_main": True,
    },
    ...
}
```

**Тест:** Добавить тест-кейс в `test_two_tank_irr_state_helpers.py`.

---

## Что НЕ трогать (Агент 1)

- Архитектуру delegation chain (executor_bound_*, executor_method_delegates.py)
- `WorkflowExecutorProtocol` и `TwoTankWorkflow`
- Тесты за пределами two-tank
- `workflow_phase_policy.py`
- `two_tank_irr_state_helpers.py` (только read для понимания)

## Критерии приёмки (Агент 1)

- [ ] `pytest backend/services/automation-engine/ -x -k "two_tank"` проходит без ошибок
- [ ] `irrigation_recovery_stop` plan содержит `valve_irrigation: True`
- [ ] `can_run_pump` вызывается независимо от `safety_guards_enabled`
- [ ] Warning в логах при pH/EC defaults
- [ ] `solution_fill_check` проверяет min-level (non-blocking при отсутствии датчика)
- [ ] `degraded` recovery возвращает `action_required=True`
- [ ] `clean_fill_check` добавлен в `_CRITICAL_IRR_STATE_EXPECTATIONS`
- [ ] `_resolve_primary_pump_channel` существует только в `two_tank_common.py`

---

---

# АГЕНТ 2: Архитектурный рефакторинг

## Предусловие

Агент 2 начинает только после того, как **Phase 0 от Агента 1 смержен** в ветку. Это необходимо, чтобы не создавать конфликты в `two_tank_phase_starters_*.py`.

## Прочитать сначала

1. `backend/services/automation-engine/domain/workflows/executor_protocol.py` — существующий Protocol
2. `backend/services/automation-engine/executor/executor_bound_two_tank_methods.py` — delegation chain
3. `backend/services/automation-engine/executor/executor_method_delegates.py`
4. `backend/services/automation-engine/executor/executor_init.py`
5. `backend/services/automation-engine/domain/workflows/two_tank_core.py` — главный объект рефакторинга
6. Все `domain/workflows/two_tank_*.py`

## Phase 2: `TwoTankDeps` dataclass

### Мотивация

Сейчас `domain/workflows/two_tank_*.py` функции принимают `self` — псевдо-методы класса `SchedulerTaskExecutor`. Это делает их нетестируемыми без полного инстанса executor-а. Phase starters уже используют правильный паттерн (explicit deps через `*_fn` параметры). Цель — привести workflow core к тому же паттерну через единый dataclass.

### 2.1 Создать `TwoTankDeps`

**Создать файл:** `backend/services/automation-engine/domain/workflows/two_tank_deps.py`

```python
"""Dependency container for two-tank workflow functions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class TwoTankDeps:
    """All dependencies needed by two-tank workflow functions.

    Replaces 'self' (SchedulerTaskExecutor) as first argument in workflow
    functions, enabling unit testing without a full executor instance.
    """
    zone_id: int

    # Infrastructure
    fetch_fn: Any                         # async (sql, *args) -> List[Row]
    command_gateway: Any                  # has publish_controller_command(...)

    # Command dispatch
    dispatch_two_tank_command_plan: Callable   # async (**kwargs) -> Dict

    # Events / state
    emit_task_event: Callable            # async (*, zone_id, task_type, context, event_type, payload)
    update_zone_workflow_phase: Callable # async (*, zone_id, workflow_phase, **kwargs)
    find_zone_event_since: Callable      # async (**kwargs) -> Optional[Dict]

    # Node queries
    check_required_nodes_online: Callable # async (zone_id, required_types) -> Dict
    get_zone_nodes: Callable              # async (zone_id, node_types) -> List[Dict]

    # Telemetry
    read_level_switch: Callable           # async (**kwargs) -> Dict
    evaluate_ph_ec_targets: Callable      # async (**kwargs) -> Dict

    # Phase starters (already refactored)
    start_two_tank_clean_fill: Callable
    start_two_tank_solution_fill: Callable
    start_two_tank_prepare_recirculation: Callable
    start_two_tank_irrigation_recovery: Callable
    merge_with_sensor_mode_deactivate: Callable
    enqueue_two_tank_check: Callable

    # Utilities
    resolve_int: Callable                 # (value, default, minimum) -> int
    normalize_two_tank_workflow: Callable # (payload) -> str
    resolve_two_tank_runtime_config: Callable  # (payload) -> Dict
    extract_topology: Callable            # (payload) -> str
    telemetry_freshness_enforce: Callable  # () -> bool
    two_tank_safety_guards_enabled: Callable   # () -> bool
    log_two_tank_safety_guard: Callable
    build_two_tank_stop_not_confirmed_result: Callable


__all__ = ["TwoTankDeps"]
```

### 2.2 Factory метод в executor

**Файл:** `backend/services/automation-engine/executor/executor_bound_two_tank_methods.py`

Добавить factory метод в конец файла:

```python
def bound_build_two_tank_deps(self, zone_id: int) -> "TwoTankDeps":
    from domain.workflows.two_tank_deps import TwoTankDeps
    return TwoTankDeps(
        zone_id=zone_id,
        fetch_fn=self.fetch_fn,
        command_gateway=self.command_gateway,
        dispatch_two_tank_command_plan=self._dispatch_two_tank_command_plan,
        emit_task_event=self._emit_task_event,
        update_zone_workflow_phase=self._update_zone_workflow_phase,
        find_zone_event_since=self._find_zone_event_since,
        check_required_nodes_online=self._check_required_nodes_online,
        get_zone_nodes=self._get_zone_nodes,
        read_level_switch=self._read_level_switch,
        evaluate_ph_ec_targets=self._evaluate_ph_ec_targets,
        start_two_tank_clean_fill=self._start_two_tank_clean_fill,
        start_two_tank_solution_fill=self._start_two_tank_solution_fill,
        start_two_tank_prepare_recirculation=self._start_two_tank_prepare_recirculation,
        start_two_tank_irrigation_recovery=self._start_two_tank_irrigation_recovery,
        merge_with_sensor_mode_deactivate=self._merge_with_sensor_mode_deactivate,
        enqueue_two_tank_check=self._enqueue_two_tank_check,
        resolve_int=self._resolve_int,
        normalize_two_tank_workflow=self._normalize_two_tank_workflow,
        resolve_two_tank_runtime_config=self._resolve_two_tank_runtime_config,
        extract_topology=self._extract_topology,
        telemetry_freshness_enforce=self._telemetry_freshness_enforce,
        two_tank_safety_guards_enabled=self._two_tank_safety_guards_enabled,
        log_two_tank_safety_guard=self._log_two_tank_safety_guard,
        build_two_tank_stop_not_confirmed_result=self._build_two_tank_stop_not_confirmed_result,
    )
```

Зарегистрировать как метод в классе (аналогично другим bound_ методам в проекте).

### 2.3 Мигрировать workflow core-функции

**Стратегия миграции:** поэтапная, один файл за раз. Сигнатура меняется:

```python
# Было:
async def execute_two_tank_startup_workflow_core(
    self,  # ← SchedulerTaskExecutor instance
    *,
    zone_id: int,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
) -> Dict[str, Any]:
    runtime_cfg = self._resolve_two_tank_runtime_config(payload)
    nodes_state = await self._check_required_nodes_online(zone_id, ...)

# Станет:
async def execute_two_tank_startup_workflow_core(
    deps: TwoTankDeps,  # ← dataclass
    *,
    payload: Dict[str, Any],
    context: Dict[str, Any],
    decision: DecisionOutcome,
) -> Dict[str, Any]:
    runtime_cfg = deps.resolve_two_tank_runtime_config(payload)
    nodes_state = await deps.check_required_nodes_online(deps.zone_id, ...)
```

**Файлы для миграции (в порядке):**

1. `domain/workflows/two_tank_core.py` — `execute_two_tank_startup_workflow_core`
2. `domain/workflows/two_tank_startup_core.py` — `execute_two_tank_startup_branch`
3. `domain/workflows/two_tank_startup_start_branch.py` — `handle_two_tank_startup_initial`
4. `domain/workflows/two_tank_startup_solution_branch.py` — `handle_two_tank_solution_fill_check`
5. `domain/workflows/two_tank_startup_prepare_branch.py` — `handle_two_tank_prepare_branches`
6. `domain/workflows/two_tank_recovery_core.py` — `execute_two_tank_recovery_branch`

**Также обновить** вызывающий код в `executor/executor_bound_workflow_methods.py` — заменить `self` на `deps = self._build_two_tank_deps(zone_id)`.

### 2.4 Упростить delegation chain

После миграции два уровня delegation становятся лишними.

**Файл:** `executor/executor_method_delegates.py` — удалить `start_two_tank_*` делегаты для two-tank (они теперь вызываются напрямую через `TwoTankDeps`).

**Файл:** `executor/executor_bound_two_tank_methods.py` — удалить `bound_start_two_tank_*` методы, оставить только `bound_build_two_tank_deps`.

**Осторожно:** проверить, что `bound_enqueue_two_tank_check` и `bound_compensate_two_tank_start_enqueue_failure` не используются за пределами two-tank.

---

## Phase 4: `TwoTankResult` builder

### Мотивация

~150 return-dict конструкций с повторяющимися полями. Легко забыть `command_statuses` или `task_type`.

### 4.1 Создать builder

**Создать файл:** `backend/services/automation-engine/domain/workflows/two_tank_result.py`

```python
"""Result builder for two-tank workflow responses."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def two_tank_error(
    *,
    mode: str,
    workflow: str,
    reason_code: str,
    reason: str,
    error_code: str,
    error: Optional[str] = None,
    commands_total: int = 0,
    commands_failed: int = 0,
    command_statuses: Optional[List[Any]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a failed two-tank result dict."""
    result: Dict[str, Any] = {
        "success": False,
        "task_type": "diagnostics",
        "mode": mode,
        "workflow": workflow,
        "commands_total": commands_total,
        "commands_failed": commands_failed,
        "command_statuses": command_statuses or [],
        "action_required": True,
        "decision": "run",
        "reason_code": reason_code,
        "reason": reason,
        "error": error or error_code,
        "error_code": error_code,
    }
    result.update(extra)
    return result


def two_tank_success(
    *,
    mode: str,
    workflow: str,
    reason_code: str,
    reason: str,
    action_required: bool,
    decision: str,
    commands_total: int = 0,
    commands_failed: int = 0,
    command_statuses: Optional[List[Any]] = None,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a successful two-tank result dict."""
    result: Dict[str, Any] = {
        "success": True,
        "task_type": "diagnostics",
        "mode": mode,
        "workflow": workflow,
        "commands_total": commands_total,
        "commands_failed": commands_failed,
        "command_statuses": command_statuses or [],
        "action_required": action_required,
        "decision": decision,
        "reason_code": reason_code,
        "reason": reason,
    }
    result.update(extra)
    return result


__all__ = ["two_tank_error", "two_tank_success"]
```

### 4.2 Постепенная замена

**Стратегия:** не заменять всё сразу. Начать с наиболее повторяющихся паттернов:
- Все `"mode": "two_tank_*_timeout"` блоки
- Все `"mode": "two_tank_*_command_failed"` блоки
- Все `"mode": "two_tank_*_enqueue_failed"` блоки

**Порядок файлов:**
1. `two_tank_recovery_core.py` (проще, меньше файл)
2. `two_tank_startup_solution_branch.py`
3. `two_tank_startup_prepare_branch.py`
4. `two_tank_startup_core.py`
5. `two_tank_core.py`

---

## Phase 5: Разделение `TwoTankSafetyConfig`

### Мотивация

Текущий `_two_tank_safety_guards_enabled()` — зонтичный флаг. После Phase 0.2 `can_run_pump` уже выведен из-под него, но архитектурно проблема остаётся: один флаг для разнородных concerns.

### 5.1 Создать конфиг

**Создать файл:** `backend/services/automation-engine/domain/policies/two_tank_safety_config.py`

```python
"""Explicit safety configuration for two-tank workflow."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TwoTankSafetyConfig:
    """Explicit per-concern safety switches.

    pump_interlock: физический interlock насоса.
        Должен быть True в production ВСЕГДА.
        False — только в unit-тестах.

    stop_confirmation_required: блокировать retry если stop-команда
        не подтверждена нодой.
        Может быть False в degraded/debug режиме с явным логом.

    irr_state_validation: валидировать expected vs actual состояние
        irr-ноды перед каждым workflow.
        Может быть False при отладке без физической ноды.
    """
    pump_interlock: bool = True
    stop_confirmation_required: bool = True
    irr_state_validation: bool = True

    @classmethod
    def production(cls) -> "TwoTankSafetyConfig":
        """Default production config — all guards enabled."""
        return cls()

    @classmethod
    def testing(cls) -> "TwoTankSafetyConfig":
        """Config for unit tests — pump interlock disabled."""
        return cls(pump_interlock=False)


__all__ = ["TwoTankSafetyConfig"]
```

### 5.2 Интеграция

В `TwoTankDeps` заменить `two_tank_safety_guards_enabled: Callable` на `safety_config: TwoTankSafetyConfig`.

В workflow-функциях заменить `self._two_tank_safety_guards_enabled()` на явные проверки:
```python
# Было:
if self._two_tank_safety_guards_enabled() and not stop_result.get("success"):
    ...

# Станет:
if deps.safety_config.stop_confirmation_required and not stop_result.get("success"):
    ...
```

---

## Что НЕ трогать (Агент 2)

- `executor/two_tank_phase_starters_*.py` — они уже в правильном стиле
- `executor/two_tank_runtime_config.py` — изменён Агентом 1
- `executor/workflow_phase_policy.py` — изменяет Агент 3
- Любые three_tank или cycle_start файлы

## Критерии приёмки (Агент 2)

- [ ] `TwoTankDeps` dataclass создан и используется во всех `domain/workflows/two_tank_*.py`
- [ ] Ни один workflow core-файл не принимает `self` первым аргументом
- [ ] `WorkflowExecutorProtocol` в `executor_protocol.py` можно удалить или оставить как deprecated
- [ ] Уровни делегирования сокращены: `executor._execute_two_tank_startup_workflow_core` → `execute_two_tank_startup_workflow_core(deps, ...)`
- [ ] `two_tank_error()` и `two_tank_success()` используются минимум в 50% return-points
- [ ] `TwoTankSafetyConfig` используется вместо callable флага
- [ ] `pytest backend/services/automation-engine/ -x -k "two_tank"` проходит

---

---

# АГЕНТ 3: Инфраструктура и долгосрочные изменения

## Прочитать сначала

1. существующий runtime pg_notify listener в `automation-engine` — текущая точка интеграции NOTIFY
2. `backend/services/automation-engine/executor/workflow_phase_policy.py` — FSM состояния
3. `backend/services/automation-engine/infrastructure/runtime_state_store.py`
4. `backend/services/automation-engine/main.py` — точка входа сервиса
5. `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md`

## Phase 3: Zone Concurrency Guard

### Мотивация

Нет защиты от одновременного выполнения двух задач для одной зоны. Если scheduler поставит в очередь два task для zone_id=5 одновременно, оба начнут отправлять команды клапанам и насосу.

### 3.1 In-process asyncio Lock

**Создать файл:** `backend/services/automation-engine/infrastructure/zone_execution_lock.py`

```python
"""Per-zone asyncio execution lock for two-tank workflow serialization."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict

_logger = logging.getLogger(__name__)
_zone_locks: Dict[int, asyncio.Lock] = {}
_registry_lock = asyncio.Lock()


async def _get_zone_lock(zone_id: int) -> asyncio.Lock:
    async with _registry_lock:
        if zone_id not in _zone_locks:
            _zone_locks[zone_id] = asyncio.Lock()
        return _zone_locks[zone_id]


@asynccontextmanager
async def zone_execution_context(
    zone_id: int,
    *,
    task_type: str = "unknown",
    workflow: str = "",
) -> AsyncIterator[None]:
    """Async context manager that serializes execution per zone_id.

    NOTE: In-process only. For multi-instance deployments, replace with
    PostgreSQL advisory lock (pg_try_advisory_xact_lock) via fetch_fn.
    """
    lock = await _get_zone_lock(zone_id)
    if lock.locked():
        _logger.warning(
            "Zone %s: execution lock contention detected (task_type=%s workflow=%s) — waiting",
            zone_id, task_type, workflow or "<none>",
        )
    async with lock:
        yield


__all__ = ["zone_execution_context"]
```

### 3.2 Применить в точке входа workflow

**Файл:** `backend/services/automation-engine/executor/executor_bound_workflow_methods.py` или где вызывается `_execute_two_tank_startup_workflow_core`.

Найти точку входа (метод executor который вызывает `two_tank_workflow.execute`) и обернуть:

```python
from infrastructure.zone_execution_lock import zone_execution_context

async with zone_execution_context(
    zone_id=zone_id,
    task_type=context.get("task_type", "diagnostics"),
    workflow=payload.get("workflow", ""),
):
    result = await self.two_tank_workflow.execute(
        zone_id=zone_id, payload=payload, context=context, decision=decision
    )
```

### 3.3 Тест

Добавить тест в `test_zone_sensor_mode_orchestrator.py` или создать `test_zone_execution_lock.py`:
- Два concurrent вызова для одного zone_id выполняются последовательно
- Два concurrent вызова для **разных** zone_id выполняются параллельно

---

## Phase 6: Event-Driven переход (подготовительный этап)

### Мотивация

Сейчас `clean_fill_check` и `solution_fill_check` опрашивают базу данных с интервалом `poll_interval_sec` (дефолт: из конфига, обычно 30-60 сек). Это создаёт задержку реакции на заполнение бака. Оборудование срабатывает мгновенно, а система узнаёт об этом через минуту.

### Подход

Вместо полного event-driven (требует изменения MQTT и firmware), использовать **PostgreSQL NOTIFY** уже существующий в runtime automation-engine.

Когда `history-logger` записывает событие `CLEAN_FILL_COMPLETED` или `SOLUTION_FILL_COMPLETED` в `zone_events` — он может эмитировать `NOTIFY two_tank_zone_{zone_id}`. `automation-engine` слушает этот канал и немедленно ставит `clean_fill_check` задачу, не ожидая `poll_interval_sec`.

### 6.1 Определить интерфейс (только дизайн, без реализации)

**Создать файл:** `backend/services/automation-engine/infrastructure/zone_event_trigger.py`

```python
"""Interface for event-driven zone task triggering.

This module defines the contract for triggering workflow check tasks
immediately upon receiving zone events (via pg_notify or other mechanisms),
without waiting for the next poll_interval_sec cycle.

Current implementation: stub (polling only).
Future implementation: pg_notify listener that calls _enqueue_two_tank_check
immediately when CLEAN_FILL_COMPLETED or SOLUTION_FILL_COMPLETED events arrive.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class ZoneEventTrigger:
    """Stub implementation — falls back to polling."""

    async def on_zone_event(
        self,
        *,
        zone_id: int,
        event_type: str,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Called when a zone event arrives via push mechanism.

        Returns enqueue result if task was triggered, None otherwise.
        """
        return None


__all__ = ["ZoneEventTrigger"]
```

### 6.2 Подключить к существующему pg_notify listener

**Файл:** текущий runtime pg_notify listener в `backend/services/automation-engine`

Изучить существующий listener. Добавить handling для событий типа `CLEAN_FILL_COMPLETED` и `SOLUTION_FILL_COMPLETED`:

```python
# В обработчике pg_notify событий добавить:
TWO_TANK_TRIGGER_EVENTS = {
    "CLEAN_FILL_COMPLETED",
    "SOLUTION_FILL_COMPLETED",
    "PREPARE_TARGETS_REACHED",
}

if event_type in TWO_TANK_TRIGGER_EVENTS:
    await zone_event_trigger.on_zone_event(
        zone_id=zone_id,
        event_type=event_type,
        payload=event_payload,
    )
```

**Примечание:** Не меняет контракт MQTT и firmware. Использует уже существующий механизм `zone_events` таблицы.

---

## Phase 7: FSM Formalization

### Мотивация

Состояния `workflow_phase` и переходы между ними определены в `workflow_phase_policy.py`, но не **enforceable**. Система может сделать переход `ready → tank_filling` повторно если scheduler создаст дублирующую задачу.

### Допустимые переходы

```
idle            → tank_filling   (startup, clean_fill_check, cycle_start)
tank_filling    → tank_recirc    (prepare_recirculation)
tank_filling    → ready          (solution_fill_check если targets уже достигнуты)
tank_recirc     → ready          (prepare_recirculation_check targets reached)
ready           → irrigating     (irrigation task run)
irrigating      → irrig_recirc   (irrigation_recovery start)
irrig_recirc    → irrigating     (irrigation_recovery_check completed/degraded)
* → idle                         (любой terminal failure)
```

### 7.1 Добавить таблицу допустимых переходов

**Файл:** `backend/services/automation-engine/executor/workflow_phase_policy.py`

```python
# Добавить в конец файла:

WORKFLOW_PHASE_VALID_TRANSITIONS: Dict[str, frozenset] = {
    WORKFLOW_PHASE_IDLE: frozenset({
        WORKFLOW_PHASE_TANK_FILLING,
    }),
    WORKFLOW_PHASE_TANK_FILLING: frozenset({
        WORKFLOW_PHASE_TANK_RECIRC,
        WORKFLOW_PHASE_READY,
        WORKFLOW_PHASE_IDLE,
    }),
    WORKFLOW_PHASE_TANK_RECIRC: frozenset({
        WORKFLOW_PHASE_READY,
        WORKFLOW_PHASE_IDLE,
    }),
    WORKFLOW_PHASE_READY: frozenset({
        WORKFLOW_PHASE_IRRIGATING,
        WORKFLOW_PHASE_IDLE,
    }),
    WORKFLOW_PHASE_IRRIGATING: frozenset({
        WORKFLOW_PHASE_IRRIG_RECIRC,
        WORKFLOW_PHASE_IDLE,
    }),
    WORKFLOW_PHASE_IRRIG_RECIRC: frozenset({
        WORKFLOW_PHASE_IRRIGATING,
        WORKFLOW_PHASE_IDLE,
    }),
}


def is_valid_phase_transition(
    from_phase: str,
    to_phase: str,
) -> bool:
    """Check if a phase transition is allowed."""
    allowed = WORKFLOW_PHASE_VALID_TRANSITIONS.get(from_phase, frozenset())
    return to_phase in allowed


def validate_phase_transition(
    from_phase: str,
    to_phase: str,
    *,
    zone_id: int,
    logger: Optional[logging.Logger] = None,
) -> bool:
    """Validate transition and log warning if invalid. Returns True if valid."""
    if is_valid_phase_transition(from_phase, to_phase):
        return True
    if logger is not None:
        logger.warning(
            "Zone %s: invalid workflow phase transition %s → %s (ignored)",
            zone_id, from_phase, to_phase,
        )
    return False
```

### 7.2 Применить в `_update_zone_workflow_phase`

Найти метод `_update_zone_workflow_phase` в executor и добавить вызов `validate_phase_transition` перед сохранением.

**Важно:** при невалидном переходе — **только warning, не exception**. Система должна продолжить работу даже с нарушением FSM, но зафиксировать нарушение в логах для расследования.

### 7.3 Тест

Добавить тесты в `test_workflow_phase_policy.py`:
- Все допустимые переходы возвращают True
- `idle → irrigating` возвращает False + warning в логе

---

## Phase 8: Distributed Lock Design (документация, не реализация)

### Мотивация

Phase 3 добавляет in-process asyncio Lock. Если сервис будет масштабироваться горизонтально, нужен distributed lock.

**Создать файл:** `backend/services/automation-engine/infrastructure/zone_execution_lock_pg.py`

```python
"""PostgreSQL advisory lock implementation for zone execution serialization.

Use this instead of zone_execution_lock.py when running multiple instances
of automation-engine simultaneously.

PostgreSQL advisory locks are session-scoped and automatically released
on connection close, making them safe for use in async contexts.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

_logger = logging.getLogger(__name__)

# Zone ID offset to avoid collisions with other advisory locks in the system
_LOCK_NAMESPACE = 0x54_57_4F_00  # "TWO\x00" in ASCII hex


@asynccontextmanager
async def zone_execution_context_pg(
    zone_id: int,
    *,
    fetch_fn: Any,
    task_type: str = "unknown",
    workflow: str = "",
) -> AsyncIterator[None]:
    """Distributed zone lock via PostgreSQL advisory lock.

    Uses pg_try_advisory_xact_lock for non-blocking attempt with fallback
    to pg_advisory_xact_lock for blocking acquisition.

    Requires: fetch_fn must use a dedicated connection (not pool) per task
    to ensure lock is held for the full duration of the workflow.

    TODO: Integrate with connection management in executor_init.py
    when horizontal scaling is required.
    """
    lock_key = _LOCK_NAMESPACE + zone_id

    # Try non-blocking first, log contention
    rows = await fetch_fn(
        "SELECT pg_try_advisory_xact_lock($1) AS acquired",
        lock_key,
    )
    acquired = rows[0]["acquired"] if rows else False

    if not acquired:
        _logger.warning(
            "Zone %s: distributed lock contention (task_type=%s workflow=%s) — waiting",
            zone_id, task_type, workflow or "<none>",
        )
        await fetch_fn("SELECT pg_advisory_xact_lock($1)", lock_key)

    try:
        yield
    finally:
        pass  # xact lock auto-released on transaction end


__all__ = ["zone_execution_context_pg"]
```

---

## Что НЕ трогать (Агент 3)

- Весь `domain/workflows/` (изменяет Агент 2)
- `executor/two_tank_phase_starters_*.py` (изменяет Агент 1)
- MQTT контракты и firmware — event-driven это pg_notify, не MQTT
- `history-logger` сервис

## Критерии приёмки (Агент 3)

- [ ] `zone_execution_context` применён к two-tank workflow точке входа
- [ ] Тест подтверждает сериализацию по zone_id и параллелизм между разными zone_id
- [ ] `WORKFLOW_PHASE_VALID_TRANSITIONS` добавлен в `workflow_phase_policy.py`
- [ ] `validate_phase_transition` вызывается в `_update_zone_workflow_phase`
- [ ] Тест невалидного перехода: только warning, не exception
- [ ] `ZoneEventTrigger` stub создан с документацией
- [ ] `zone_execution_lock_pg.py` создан с TODO на интеграцию
- [ ] `pytest backend/services/automation-engine/ -x` проходит

---

---

## Общие ограничения для всех агентов

1. **Не менять MQTT контракты** — `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`
2. **Не менять форматы команд** — `{"channel": ..., "cmd": "set_relay", "params": {"state": ...}}`
3. **Не трогать three_tank и cycle_start** — только two_tank
4. **Не рефакторить history-logger, scheduler, mqtt-bridge** — отдельные сервисы
5. **Каждое изменение — отдельный коммит** с форматом `fix: ...` или `refactor: ...`
6. **Запускать тесты после каждого файла** — `pytest -x -k "two_tank"`
7. **Не использовать `--no-verify`** при коммитах

## Порядок merge

```
Phase 0 (Агент 1) → merge в ветку
    ↓
Phase 1 (Агент 1) → merge
Phase 3 (Агент 3) → merge (параллельно с Агентом 1, нет конфликтов)
    ↓
Phase 2 (Агент 2) → merge (требует Phase 0 уже смержен)
Phase 6+7+8 (Агент 3) → merge (требует Phase 2 для интеграции с TwoTankDeps)
    ↓
Phase 4+5 (Агент 2) → merge
```
