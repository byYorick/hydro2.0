# Аудит Automation-Engine: Результаты и план доработки

**Дата:** 2026-02-15
**Статус:** Утвержден аудитором, требует ревью владельцем

---

## 1. Контекст аудита

### 1.1. Что проверялось

Глубокий аудит automation-engine как архитектор: state machine, последовательность команд водного контура, зональная маршрутизация, персистенция состояния, синхронность кода с документацией.

### 1.2. Проверенные файлы

| Файл | Строк | Роль |
|------|-------|------|
| `scheduler_task_executor.py` | ~4400 | State machine two-tank/three-tank workflow |
| `services/zone_automation_service.py` | ~1637 | Периодический цикл обработки зон |
| `correction_controller.py` | ~1213 | Универсальная коррекция pH/EC с PID |
| `irrigation_controller.py` | ~250 | Контроллер полива |
| `infrastructure/command_bus.py` | ~1047 | Публикация команд через REST |
| `config/scheduler_task_mapping.py` | ~154 | Маппинг задач → команды |
| `services/pid_state_manager.py` | ~211 | Персистенция PID |
| `main.py` | ~1234 | Entry point |

### 1.3. Проверенная документация

- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` — 6-state machine (source of truth)
- `doc_ai/ARCHITECTURE_FLOWS.md` — пайплайн коррекции, таблица режимов
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_LOGIC_AI_AGENT_PLAN.md` — 10-step plan
- `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура сервисов
- `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md` — контракт scheduler↔AE

---

## 2. Архитектурный обзор

### 2.1. Два параллельных пути автоматизации

**Путь A — `ZoneAutomationService` (каждые ~15 сек):**
```
process_zone() → light → climate → irrigation → recirculation → correction → health
```
- Проверяет gating: `flow_active + stable + corrections_allowed`
- Управляет sensor mode (activate/deactivate)
- Вызывает CorrectionController для pH/EC

**Путь B — `SchedulerTaskExecutor` (по задачам scheduler):**
```
POST /scheduler/task → execute() → _decide_action() → two_tank/three_tank workflow
```
- Self-enqueue через `enqueue_internal_scheduler_task`
- Polling по таймеру для check-фаз
- Оценивает `_evaluate_ph_ec_targets` на check-фазах

### 2.2. Документированная state machine (CORRECTION_CYCLE_SPEC.md)

```
IDLE → TANK_FILLING → TANK_RECIRC → READY → IRRIGATING → IRRIG_RECIRC → IDLE
```

| Состояние | Поток | Сенсоры | NPK | Ca/Mg/Micro | pH |
|-----------|-------|---------|-----|-------------|-----|
| IDLE | нет | нет | - | - | - |
| TANK_FILLING | да | да | ✅ | ❌ | ✅ |
| TANK_RECIRC | да | да | ✅ | ❌ | ✅ |
| READY | нет | нет | - | - | - |
| IRRIGATING | да | да | ❌ | ✅ | ✅ |
| IRRIG_RECIRC | да | да | ❌ | ✅ | ✅ |

### 2.3. Реализованная state machine (scheduler_task_executor.py)

```
startup → clean_fill_check → solution_fill_check → prepare_recirculation_check → DONE
                                                                         ↕
                                        irrigation_recovery → irrigation_recovery_check → DONE
```

---

## 3. Рассинхрон кода с документацией

### BUG-01: [P0/CRITICAL] Нет inline-коррекции при solution fill

**Документация (CORRECTION_CYCLE_SPEC §3.1):**
> TANK_FILLING: Поток активен, NPK + pH коррекция. Automation-engine → MQTT: activate ph_node, ec_node → start pump_in → ожидание стабилизации → дозирование NPK → дозирование pH

**Код (`_start_two_tank_solution_fill`, строка 2994):**
- Отправляет только `solution_fill_start` command plan (открытие клапанов + насос)
- **НЕ** активирует sensor mode
- **НЕ** запускает коррекцию во время наполнения
- Только polling `solution_max` level sensor

**Последствие:** Бак заполняется чистой водой без коррекции. Коррекция начинается только после заполнения (prepare_recirculation), что значительно дольше и менее эффективно.

### BUG-02: [P0/CRITICAL] Нет координации ZAS ↔ workflow

**Проблема:** `ZoneAutomationService.process_zone()` не знает о текущей фазе two-tank workflow.

**Конкретный сценарий:**
1. Two-tank workflow в фазе `solution_fill` (бак заполняется)
2. ZAS видит `irrigation_interval_sec` достигнут → формирует команду `run_pump`
3. Полив запускается незрелым раствором

**Где в коде:** `irrigation_controller.py:66-171` — `check_and_control_irrigation()` проверяет только:
- `irrigation_interval_sec` (прошел ли интервал)
- `water_level_ok` (достаточно ли воды)
- **Нет проверки** текущего workflow state / irrigation_allowed флага

**Зеркальная проблема:** ZAS запускает `correction_controller` параллельно с workflow, но не знает какие EC-компоненты дозировать (NPK vs Ca/Mg/Micro).

### BUG-03: [P0/CRITICAL] Нет разделения EC-компонентов по фазам

**Документация (ARCHITECTURE_FLOWS §3.3.5, CORRECTION_CYCLE_SPEC §2.2):**
- TANK_FILLING/TANK_RECIRC: только NPK + pH
- IRRIGATING/IRRIG_RECIRC: только Ca/Mg/Micro + pH

**Код (`correction_controller.py`, строки 803-906):**
```python
required_components = ["npk", "calcium", "magnesium", "micro"]  # ВСЕГДА все 4
```
`_build_ec_component_batch()` дозирует **все 4 компонента** при каждой EC-коррекции. Нет входного параметра для фильтрации по фазе.

**Последствие:** При подготовке бака дозируются Ca/Mg/Micro (не нужны), при поливе дозируется NPK (перерасход, может быть вредно для растений).

### BUG-04: [P1/HIGH] Нет перехода STARTUP_COMPLETED → IRRIGATION_ALLOWED

**Проблема:** Когда `solution_fill_check` или `prepare_recirculation_check` завершается с success, результат возвращается в scheduler, но **никакого флага или события** не устанавливается для ZAS.

**Код (строка 3736):**
```python
return {
    "success": True,
    "mode": "two_tank_startup_completed",
    "decision": "skip",  # ← возврат в scheduler, ZAS не узнаёт
}
```

ZAS не имеет механизма узнать, что startup завершен и irrigation разрешен.

### BUG-05: [P1/HIGH] Персистенция workflow state только через payload

**Код (строка 2796):**
```python
return await enqueue_internal_scheduler_task(
    zone_id=zone_id,
    task_type="diagnostics",
    payload=next_payload,  # ← всё состояние тут
)
```

**Проблемы:**
- Рестарт AE → потеря всех in-flight workflows
- Enqueue failure → компенсация best-effort, но workflow state потерян
- Нет журнала активных workflows → нельзя определить что workflow уже идёт
- Невозможно показать в UI текущую фазу workflow

### BUG-06: [P1/HIGH] Sensor mode не активируется из workflow

**Код:** `_start_two_tank_solution_fill` (строка 2994) и `_start_two_tank_prepare_recirculation` (строка 3097) отправляют только valve/pump команды.

**Ожидание (CORRECTION_CYCLE_SPEC §3.1):** При переходе в TANK_FILLING:
1. activate ph_node, ec_node
2. start pump_in
3. ожидание стабилизации

Активация sensor mode происходит **только** через ZAS `_process_correction_controllers()` → `_set_sensor_mode()`, но ZAS не знает что пора активировать (нет flow_active от workflow).

**Зависимость:** Sensor mode активируется только если `correction_flags.flow_active == True`, что приходит **от самих pH/EC нод** после активации. Получается circular dependency: нужно активировать, чтобы получить флаг, нужен флаг чтобы активировать.

**Текущее спасение (строка 1349):** При `missing_flags` ZAS отправляет `activate_sensor_mode`. Это работает, но:
- Вносит задержку (каждый цикл ~15 сек пока флаги появятся)
- Семантически неверно (активация из-за "missing" а не из-за "flow started")

### BUG-07: [P2/MEDIUM] PID integral не сбрасывается при смене фазы

**Код (`pid_state_manager.py`):** PID state (integral, prev_error) сохраняется/восстанавливается глобально по `(zone_id, pid_type)`. Нет понятия "фаза".

**Проблема:** При переходе prepare → irrigation:
- EC target меняется (с `target_ec_prepare` на `target_ec`)
- PID integral "заряжен" от предыдущей фазы
- Возможен overshoot при первых коррекциях в новой фазе

**В `_check_pid_config_updates` (строка 1567):** PID удаляется из `_pid_by_zone` при изменении конфига зоны, но **не при смене workflow фазы**.

### BUG-08: [P2/MEDIUM] Zone guards отключены по дефолту

**Код (`command_bus.py`, строки 79-88):**
```python
raw_guard = str(os.getenv("AE_ENFORCE_NODE_ZONE_ASSIGNMENT", "0"))
self.enforce_node_zone_assignment = raw_guard in _TRUE_VALUES  # default: False

raw_guard = str(os.getenv("AE_ENFORCE_COMMAND_CHANNEL_COMPATIBILITY", "0"))
self.enforce_command_channel_compatibility = raw_guard in _TRUE_VALUES  # default: False
```

**Последствие:** В production команда может быть отправлена ноде из другой зоны без предупреждения.

### BUG-09: [P3/LOW] God Object — scheduler_task_executor.py

4400+ строк в одном файле. Содержит: decision logic, workflow orchestration, node resolution, sensor reading, command dispatching, enqueue logic, runtime config parsing, compensation logic, utility helpers.

---

## 4. Что работает корректно

### 4.1. Зональная маршрутизация (при включенных guards)

- `_dispatch_two_tank_command_plan` → `_resolve_online_node_for_channel(zone_id=zone_id)` — ноды ищутся строго в пределах zone_id
- `CommandBus._verify_node_zone_assignment()` — проверяет принадлежность ноды к зоне (если включен)
- `_resolve_greenhouse_uid_for_zone(zone_id)` — greenhouse_uid из БД по zone_id

### 4.2. Correction gating (fail-closed)

- 3 обязательных флага: `flow_active`, `stable`, `corrections_allowed`
- Все `None` → skip (missing_flags) + activate sensor mode
- `flow_active=false` → skip + deactivate sensor mode
- Freshness check в CorrectionController: stale data → skip

### 4.3. Safety guards two-tank

- `AE_TWOTANK_SAFETY_GUARDS_ENABLED` — если stop не подтверждён, повторный запуск запрещён
- `_compensate_two_tank_start_enqueue_failure` — при ошибке enqueue отправляется stop
- Каждая check-фаза имеет timeout с cleanup

### 4.4. Default command plans

Корректно описывают аппаратную конфигурацию:
- `solution_fill_start`: valve_clean_supply(ON) + valve_solution_fill(ON) + pump_main(ON)
- `prepare_recirculation_start`: valve_solution_supply(ON) + valve_solution_fill(ON) + pump_main(ON)
- `irrigation_recovery_start`: valve_irrigation(OFF) + valve_solution_supply(ON) + valve_solution_fill(ON) + pump_main(ON)

### 4.5. PID state persistence

- `PidStateManager.save_pid_state()` — integral, prev_error, stats → PostgreSQL
- `save_all_pid_states()` вызывается при graceful shutdown
- `restore_pid_state()` вызывается при startup

### 4.6. Three-tank → cycle_start делегация

`_execute_three_tank_startup_workflow` корректно делегирует в `_execute_cycle_start_workflow` с mode mapping.

---

## 5. План доработки

### Фаза 1: Критические фиксы (блокеры production)

#### 1.1. Zone Workflow State — координация ZAS ↔ Workflow
**Приоритет:** P0
**Файлы:** `zone_automation_service.py`, `scheduler_task_executor.py`, `api.py`
**Суть:**
- Добавить per-zone `workflow_phase` в `_zone_states` (или отдельную структуру)
- SchedulerTaskExecutor обновляет `workflow_phase` при каждом переходе (startup, clean_fill, solution_fill, prepare_recirc, ready, irrigating, recovery)
- ZAS проверяет `workflow_phase` перед irrigation: если не `ready`/`irrigating` → skip irrigation
- ZAS проверяет `workflow_phase` перед correction: передаёт текущую фазу в correction_controller

**Варианты реализации:**
- **A.** In-memory dict в shared service (singleton ZoneAutomationService) — быстро, но теряется при рестарте
- **B.** zone_events + query при каждом цикле — надёжно, но нагрузка на БД
- **C.** Гибрид: in-memory cache + persist в zone_events при переходах, restore при старте

**Рекомендация:** Вариант C.

#### 1.2. EC-компоненты по фазам
**Приоритет:** P0
**Файлы:** `correction_controller.py`, `zone_automation_service.py`
**Суть:**
- Добавить параметр `allowed_ec_components: Optional[List[str]]` в `check_and_correct()` и `_build_ec_component_batch()`
- ZAS передаёт компоненты в зависимости от `workflow_phase`:
  - `tank_filling` / `tank_recirc` → `["npk"]`
  - `irrigating` / `irrig_recirc` → `["calcium", "magnesium", "micro"]`
  - `ready` / `idle` / None → все (для обратной совместимости)
- Фильтрация в `_build_ec_component_batch()`: `required_components = [c for c in required if c in allowed]`

#### 1.3. Включить zone guards по дефолту
**Приоритет:** P0
**Файлы:** `command_bus.py`, `docker-compose.dev.yml`, `.env.example`
**Суть:** Изменить default с `"0"` на `"1"` для:
- `AE_ENFORCE_NODE_ZONE_ASSIGNMENT`
- `AE_ENFORCE_COMMAND_CHANNEL_COMPATIBILITY`

### Фаза 2: Inline-коррекция и sensor mode

#### 2.1. Sensor mode activation из workflow
**Приоритет:** P1
**Файлы:** `scheduler_task_executor.py`
**Суть:**
- В `_start_two_tank_solution_fill()` после отправки valve/pump commands → отправить `activate_sensor_mode` для pH/EC нод в зоне
- В каждом stop command plan → отправить `deactivate_sensor_mode`
- Использовать `_resolve_online_node_for_channel(zone_id, channel="system", node_types=["ph","ec"])` для поиска сенсорных нод

#### 2.2. Inline-коррекция при solution fill (PREPARE_CORRECTION_ONLINE)
**Приоритет:** P1
**Файлы:** `scheduler_task_executor.py`, `zone_automation_service.py`
**Суть:**
- При переходе в `solution_fill` → установить `workflow_phase = "tank_filling"`
- ZAS в correction gating: если `workflow_phase == "tank_filling"` → разрешить коррекцию даже без explicit flow_active (потому что мы сами запустили насос)
- Альтернатива: подождать пока flow_active=true появится от ноды (текущее поведение, но с задержкой)

#### 2.3. PID reset при смене фазы
**Приоритет:** P2
**Файлы:** `zone_automation_service.py`, `correction_controller.py`
**Суть:**
- При переходе workflow_phase (prepare → irrigation) → `del ph_controller._pid_by_zone[zone_id]`
- При переходе workflow_phase (prepare → irrigation) → `del ec_controller._pid_by_zone[zone_id]`
- PID пересоздаётся с новым target при следующей коррекции

### Фаза 3: Персистенция workflow state

#### 3.1. Workflow state в БД
**Приоритет:** P1
**Файлы:** миграция БД, `scheduler_task_executor.py`, `main.py`
**Суть:**
- Новая таблица `zone_workflow_state`:
  ```sql
  CREATE TABLE zone_workflow_state (
      zone_id INTEGER PRIMARY KEY REFERENCES zones(id),
      workflow_phase VARCHAR(50) NOT NULL DEFAULT 'idle',
      started_at TIMESTAMPTZ,
      updated_at TIMESTAMPTZ DEFAULT NOW(),
      payload JSONB DEFAULT '{}'::jsonb,
      scheduler_task_id VARCHAR(100)
  );
  ```
- При каждом переходе в two_tank workflow → UPDATE
- При startup AE → SELECT и восстановление in-flight workflows

#### 3.2. Startup recovery
**Приоритет:** P1
**Файлы:** `main.py`, `scheduler_task_executor.py`
**Суть:**
- При запуске: `SELECT * FROM zone_workflow_state WHERE workflow_phase != 'idle'`
- Для каждой активной зоны: проверить актуальность (не expired ли task), при необходимости → enqueue continuation task или → safety stop

### Фаза 4: Рефакторинг

#### 4.1. Декомпозиция scheduler_task_executor.py
**Приоритет:** P2
**Суть:**
- `two_tank_workflow.py` — вся логика two-tank (startup, check-phases, helpers)
- `three_tank_workflow.py` — three-tank + cycle_start
- `decision_engine.py` — `_decide_action`, reason codes, feature flags
- `workflow_helpers.py` — общие методы (level reading, target evaluation, node resolution)
- `scheduler_task_executor.py` — тонкий диспетчер

#### 4.2. Типизированный WorkflowState
**Приоритет:** P3
**Суть:** Dataclass вместо `Dict[str, Any]` для payload workflow. Типы, валидация, автодополнение.

---

## 6. Сквозные тесты

### 6.1. Тесты водного контура (two-tank)

| ID | Тест | Покрытие | Файл |
|----|------|----------|------|
| E2E-01 | **Full startup cycle:** startup → clean_fill → solution_fill → prepare_recirc → targets_reached | BUG-01, BUG-06 | `test_two_tank_workflow.py` |
| E2E-02 | **Skip clean fill:** clean tank already full → solution_fill directly | Happy path optimization | `test_two_tank_workflow.py` |
| E2E-03 | **Clean fill retry:** clean_fill timeout → retry → success on 2nd attempt | Retry logic | `test_two_tank_workflow.py` |
| E2E-04 | **Solution fill timeout:** solution_fill timeout → fail | Timeout handling | `test_two_tank_workflow.py` |
| E2E-05 | **Prepare recirc timeout → degraded:** recirc timeout → degraded tolerance check | Degraded mode | `test_two_tank_workflow.py` |

### 6.2. Тесты irrigation recovery

| ID | Тест | Покрытие | Файл |
|----|------|----------|------|
| E2E-06 | **Recovery success:** targets drift → recovery → targets reached → continue | Recovery logic | `test_two_tank_recovery.py` |
| E2E-07 | **Recovery degraded:** recovery timeout → degraded ok → finish | Degraded tolerance | `test_two_tank_recovery.py` |
| E2E-08 | **Recovery max attempts:** recovery timeout × max_attempts → fail | Attempt limit | `test_two_tank_recovery.py` |

### 6.3. Тесты координации ZAS ↔ workflow

| ID | Тест | Покрытие | Файл |
|----|------|----------|------|
| E2E-09 | **No irrigation during startup:** startup in progress → ZAS skip irrigation | BUG-02 | `test_workflow_coordination.py` |
| E2E-10 | **NPK-only during prepare:** workflow=tank_filling → correction uses only NPK | BUG-03 | `test_workflow_coordination.py` |
| E2E-11 | **CaMgMicro during irrigation:** workflow=irrigating → correction uses Ca/Mg/Micro | BUG-03 | `test_workflow_coordination.py` |
| E2E-12 | **PID reset on phase change:** prepare → irrigation → PID integral reset | BUG-07 | `test_workflow_coordination.py` |
| E2E-13 | **Sensor mode from workflow:** solution_fill_start → activate_sensor_mode sent | BUG-06 | `test_workflow_coordination.py` |

### 6.4. Тесты зональной изоляции

| ID | Тест | Покрытие | Файл |
|----|------|----------|------|
| E2E-14 | **Zone isolation:** 2 зоны с workflow → команды не пересекаются | Zone routing | `test_zone_isolation.py` |
| E2E-15 | **Node-zone mismatch:** команда к ноде чужой зоны → rejection + alert | BUG-08 | `test_zone_isolation.py` |
| E2E-16 | **Channel-cmd compatibility:** actuator cmd на sensor channel → rejection | Guard validation | `test_zone_isolation.py` |

### 6.5. Тесты safety и compensation

| ID | Тест | Покрытие | Файл |
|----|------|----------|------|
| E2E-17 | **Enqueue failure → compensating stop:** enqueue fails → stop commands sent | Compensation | `test_safety_compensation.py` |
| E2E-18 | **Stop not confirmed → no restart:** stop fails → safety guard blocks restart | Safety guards | `test_safety_compensation.py` |
| E2E-19 | **Workflow recovery after restart:** workflow in DB → AE restart → resume | BUG-05 | `test_workflow_persistence.py` |

### 6.6. Рекомендуемая структура тестов

```
backend/services/automation-engine/tests/e2e/
├── conftest.py                     # Fixtures: mock CommandBus, DB, enqueue
├── test_two_tank_workflow.py       # E2E-01..E2E-05
├── test_two_tank_recovery.py       # E2E-06..E2E-08
├── test_workflow_coordination.py   # E2E-09..E2E-13
├── test_zone_isolation.py          # E2E-14..E2E-16
├── test_safety_compensation.py     # E2E-17..E2E-18
└── test_workflow_persistence.py    # E2E-19
```

**Стратегия моков:**
- `enqueue_internal_scheduler_task` → mock (записать payload, вернуть success)
- `CommandBus.publish_command` → mock (записать команду, вернуть True)
- `CommandBus.publish_controller_command_closed_loop` → mock (записать, вернуть DONE)
- `fetch()` (DB) → реальные PostgreSQL fixtures для zones/nodes/sensors
- `_read_level_switch` → parametrize (full/empty/stale/unavailable)
- `_evaluate_ph_ec_targets` → parametrize (reached/not_reached/stale)

---

## 7. Приоритеты реализации

### Sprint 1 (неделя 1-2): Критические фиксы
1. **1.1** Zone Workflow State — координация
2. **1.2** EC-компоненты по фазам
3. **1.3** Включить zone guards
4. **E2E-09, E2E-10, E2E-11** — тесты координации

### Sprint 2 (неделя 3-4): Sensor mode и inline-коррекция
5. **2.1** Sensor mode activation из workflow
6. **2.2** Inline-коррекция при solution fill
7. **2.3** PID reset при смене фазы
8. **E2E-01, E2E-06, E2E-13** — тесты workflow и sensor mode

### Sprint 3 (неделя 5-6): Персистенция и safety
9. **3.1** Workflow state в БД
10. **3.2** Startup recovery
11. **E2E-17, E2E-18, E2E-19** — тесты safety и persistence

### Sprint 4 (неделя 7-8): Рефакторинг и полное покрытие
12. **4.1** Декомпозиция scheduler_task_executor.py
13. Остальные E2E тесты (E2E-02..E2E-08, E2E-14..E2E-16)

---

## 8. Обновление документации (при реализации)

| Документ | Что обновить |
|----------|-------------|
| `CORRECTION_CYCLE_SPEC.md` | Добавить описание интеграции state machine с SchedulerTaskExecutor |
| `AUTOMATION_LOGIC_AI_AGENT_PLAN.md` | Обновить статус реализованных состояний |
| `PYTHON_SERVICES_ARCH.md` | Добавить описание zone_workflow_state таблицы |
| `SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md` | Добавить workflow_phase в response контракт |
| `backend/services/automation-engine/README.md` | Обновить описание архитектуры с workflow state |

---

## 9. Риски

| Риск | Вероятность | Влияние | Митигация |
|------|------------|---------|-----------|
| Обратная совместимость при включении guards | Средняя | Высокое | Feature flag период, постепенное включение |
| Overhead от workflow state persist | Низкая | Низкое | Одна запись на зону, UPDATE only |
| Регрессия при разделении EC-компонентов | Средняя | Высокое | E2E-10, E2E-11 тесты |
| Circular dependency sensor mode ↔ flow_active | Низкая | Среднее | Explicit activation из workflow (2.1) |
