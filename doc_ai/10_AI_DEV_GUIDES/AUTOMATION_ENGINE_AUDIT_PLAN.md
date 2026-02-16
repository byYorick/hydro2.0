# Automation-Engine: план рефакторинга

**Версия:** v3.0
**Дата:** 2026-02-15
**Статус:** Готов к исполнению

> **Для AI-ассистента:** Этот документ — единственный источник задач по рефакторингу automation-engine.
> Читай последовательно: сначала контекст (§1-2), потом задачи (§3), потом правила (§4).
> Каждая задача содержит всё необходимое: баг, файлы, действия, тесты, критерии готовности.

---

## 1. Архитектурный контекст

### 1.1. Codebase

Все файлы относительно `backend/services/automation-engine/`.

| Файл | Строк | Роль |
|------|-------|------|
| `scheduler_task_executor.py` | ~4400 | State machine two-tank/three-tank workflow |
| `services/zone_automation_service.py` | ~1637 | Периодический цикл обработки зон (~15 сек) |
| `correction_controller.py` | ~1213 | Коррекция pH/EC с PID |
| `irrigation_controller.py` | ~250 | Контроллер полива |
| `infrastructure/command_bus.py` | ~1047 | Публикация команд через REST → history-logger |
| `config/scheduler_task_mapping.py` | ~154 | Маппинг задач → команды |
| `services/pid_state_manager.py` | ~211 | Персистенция PID |
| `main.py` | ~1234 | Entry point |

### 1.2. Два параллельных пути автоматизации

В системе **два независимых процесса**, которые сейчас не координированы (это корень большинства багов):

**Путь A — ZoneAutomationService (ZAS)** — периодический цикл каждые ~15 сек:
```
process_zone() → light → climate → irrigation → recirculation → correction → health
```
- Проверяет gating-флаги: `flow_active + stable + corrections_allowed`
- Управляет sensor mode (activate/deactivate)
- Вызывает CorrectionController для pH/EC

**Путь B — SchedulerTaskExecutor** — по задачам от scheduler:
```
POST /scheduler/task → execute() → _decide_action() → two_tank/three_tank workflow
```
- Self-enqueue через `enqueue_internal_scheduler_task`
- Polling check-фаз по таймеру
- Оценивает `_evaluate_ph_ec_targets` на check-фазах

**Ключевая проблема:** ZAS не знает о текущей фазе workflow. Workflow не знает о действиях ZAS. Они работают параллельно и могут конфликтовать.

### 1.3. Документированная state machine (source of truth)

Из `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md`:

```
IDLE → TANK_FILLING → TANK_RECIRC → READY → IRRIGATING → IRRIG_RECIRC → IDLE
```

| Состояние | Поток | Сенсоры | NPK | Ca/Mg/Micro | pH |
|-----------|-------|---------|-----|-------------|-----|
| IDLE | нет | нет | - | - | - |
| TANK_FILLING | да | да | да | **нет** | да |
| TANK_RECIRC | да | да | да | **нет** | да |
| READY | нет | нет | - | - | - |
| IRRIGATING | да | да | **нет** | да | да |
| IRRIG_RECIRC | да | да | **нет** | да | да |

### 1.4. Реализованная state machine (scheduler_task_executor.py)

```
startup → clean_fill_check → solution_fill_check → prepare_recirculation_check → DONE
                                                                         ↕
                                        irrigation_recovery → irrigation_recovery_check → DONE
```

### 1.5. Что работает корректно (НЕ ЛОМАТЬ)

- **Зональная маршрутизация:** `_resolve_online_node_for_channel(zone_id)` ищет ноды строго в пределах zone_id
- **Correction gating (fail-closed):** 3 обязательных флага, `None` → skip, `flow_active=false` → deactivate
- **Safety guards two-tank:** stop не подтверждён → рестарт запрещён; enqueue failure → compensating stop
- **Default command plans:** корректно описывают valve/pump конфигурации
- **PID state persistence:** save при shutdown, restore при startup
- **Three-tank → cycle_start делегация:** работает корректно

### 1.6. Связанная документация

- `doc_ai/06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` — 6-state machine (source of truth)
- `doc_ai/ARCHITECTURE_FLOWS.md` — пайплайн коррекции, таблица режимов
- `doc_ai/04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура сервисов
- `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md` — контракт scheduler↔AE
- `doc_ai/10_AI_DEV_GUIDES/AUTOMATION_LOGIC_AI_AGENT_PLAN.md` — 10-step plan

---

## 2. Реестр багов

Каждый баг привязан к конкретной задаче в §3. Здесь — краткий справочник.

| ID | Приоритет | Суть | Файл | Задача |
|----|-----------|------|------|--------|
| BUG-01 | P0 | Нет inline-коррекции при solution fill — бак заполняется без дозирования | `scheduler_task_executor.py:2994` | P2.4 |
| BUG-02 | P0 | ZAS не знает о фазе workflow → может запустить полив незрелым раствором | `irrigation_controller.py:66-171` | P2.1 |
| BUG-03 | P0 | EC-компоненты не разделены по фазам — всегда дозируются все 4 | `correction_controller.py:803-906` | P2.3 |
| BUG-04 | P1 | Нет перехода STARTUP_COMPLETED → IRRIGATION_ALLOWED для ZAS | `scheduler_task_executor.py:3736` | P2.1 |
| BUG-05 | P1 | Workflow state только в payload enqueue — теряется при рестарте | `scheduler_task_executor.py:2796` | P4.1 |
| BUG-06 | P1 | Sensor mode не активируется из workflow (circular dependency) | `scheduler_task_executor.py:2994,3097` | P2.4 |
| BUG-07 | P2 | PID integral не сбрасывается при смене фазы → overshoot | `pid_state_manager.py` | P2.5 |
| BUG-08 | P2 | Zone guards отключены по дефолту (`"0"`) | `command_bus.py:79-88` | P3.3 |
| BUG-09 | P3 | God Object — 4400+ строк в одном файле | `scheduler_task_executor.py` | P5.1 |
| BUG-10 | P1 | Первый автополив невозможен без исторического IRRIGATION_STARTED | `irrigation_controller.py` | P3.1 |
| BUG-11 | P1 | Событие записывается ДО подтверждения отправки команды | `zone_automation_service.py` | P3.2 |
| BUG-12 | P2 | Частичный EC batch без компенсации — сломанная стехиометрия | `correction_controller.py` | P3.4 |
| BUG-13 | P2 | Event-storm `CORRECTION_SKIPPED_MISSING_FLAGS` без троттлинга | `zone_automation_service.py` | P1.3 |
| BUG-14 | P1 | Gating не проверяет свежесть correction_flags → stale flags | `zone_automation_service.py` | P1.1 |
| BUG-15 | P1 | Silent fallback unknown workflow в three-tank → cycle_start | `scheduler_task_executor.py` | P0.1 |
| BUG-16 | P2 | Sensor mode не деактивируется при `sensor_unstable`/`corrections_not_allowed` | `zone_automation_service.py` | P1.2 |
| BUG-17 | P1 | Missing workflow в payload → silent default `cycle_start` | `scheduler_task_executor.py` | P0.2 |

**Архитектурное решение для BUG-06 (ownership sensor mode):**
Sensor mode activation — ответственность **только workflow** (SchedulerTaskExecutor).
ZAS **не активирует** sensor mode, только проверяет состояние и деактивирует при необходимости.
Цепочка: workflow запускает насос + активирует сенсоры → ноды отдают флаги → ZAS читает флаги для gating.

---

## 3. Задачи по этапам

Этапы выполняются **строго последовательно**: P0 → P1 → P2 → P3 → P4 → P5.
Каждый следующий этап зависит от предыдущих.

```
P0 (7д) → P1 (10д) → P2 (12д) → P3 (10д) → P4 (10д) → P5 (12д)
```

### Этап P0 — Contract Gates (7 дней)

**Цель:** fail-closed на уровне входного контракта scheduler→AE.
**Зависимости:** нет.
**Закрывает:** BUG-15, BUG-17.

---

#### P0.1. Fail-closed для unsupported workflow в three-tank

**Закрывает:** BUG-15

**Проблема в коде:** `scheduler_task_executor.py` — `_execute_three_tank_startup_workflow()` использует
`fallback_workflow = "refill_check" if workflow == "refill_check" else "cycle_start"`.
Любой неизвестный `workflow` молча становится `cycle_start`. Для two-tank аналогичный случай уже fail-closed.

**Что сделать:**
1. В `_execute_three_tank_startup_workflow()` — для неизвестного workflow возвращать `{"success": False, "error": "unsupported_workflow", "workflow": workflow}` (по аналогии с two-tank)
2. Фиксировать zone_event с исходным payload при ошибке
3. Для допустимых workflow (`cycle_start`, `refill_check`) — без изменений

**Тесты:**
- E2E-25: неизвестный workflow → явный reject, без silent fallback в `cycle_start`

**Exit criteria:** 0 silent fallback для unknown workflow в тестах.

---

#### P0.2. Mandatory workflow в scheduler payload

**Закрывает:** BUG-17

**Проблема в коде:** `scheduler_task_executor.py` — `_extract_workflow()` возвращает `"cycle_start"` если `workflow/diagnostics_workflow/execution.workflow` отсутствуют.

**Что сделать:**
1. Для diagnostic/startup задач c tank topologies — требовать явный `workflow`
2. При отсутствии → возвращать `{"success": False, "error": "invalid_payload_missing_workflow"}`
3. Добавить feature-flag `AE_LEGACY_WORKFLOW_DEFAULT_ENABLED` (default=`0`) для обратной совместимости на период миграции

**Тесты:**
- E2E-27: отсутствует workflow → fail-closed с контрактной ошибкой

**Exit criteria:** при пустом payload workflow — всегда явная ошибка (при выключенном legacy flag).

---

### Этап P1 — Gating + Sensor Lifecycle (10 дней)

**Цель:** deterministic policy для correction gating и sensor mode.
**Зависимости:** P0 завершён.
**Закрывает:** BUG-13, BUG-14, BUG-16.

---

#### P1.1. Freshness-валидация correction_flags

**Закрывает:** BUG-14

**Проблема в коде:** `zone_automation_service.py` — `_build_correction_gating_state()` нормализует `flow_active/stable/corrections_allowed` и сохраняет `*_ts`, но не проверяет их возраст. При stale flags (связь потеряна, ingest лагает) коррекции продолжаются на устаревших данных.

**Что сделать:**
1. Добавить настройку `AE_CORRECTION_FLAGS_MAX_AGE_SEC` в `config/settings.py`
2. В `_build_correction_gating_state()` — если `now - *_ts > max_age` → `can_run=False`, reason=`stale_flags`
3. При `stale_flags` — деактивировать sensor mode
4. Добавить zone_event `CORRECTION_SKIPPED_STALE_FLAGS` + infra-alert с троттлингом

**Тесты:**
- E2E-24: устаревшие timestamps → коррекции блокируются (fail-closed)

---

#### P1.2. Sensor mode lifecycle при gating-блокировках

**Закрывает:** BUG-16

**Проблема в коде:** `zone_automation_service.py` — `_process_correction_controllers()` деактивирует sensor mode только при `reason_code == "flow_inactive"`. Для `sensor_unstable` и `corrections_not_allowed` деактивация не выполняется.

**Что сделать:**
1. Создать `SensorModePolicy` — таблица переходов (`activate/deactivate/noop`) для всех reason_code
2. Для `sensor_unstable` и `corrections_not_allowed` — определить явную политику deactivation
3. Использовать существующий stateful debounce для защиты от лишних повторных команд
4. Согласовать policy с `CORRECTION_CYCLE_SPEC.md`

**Тесты:**
- E2E-26: при `sensor_unstable/corrections_not_allowed` mode деактивируется по policy

---

#### P1.3. Троттлинг correction-skip событий

**Закрывает:** BUG-13

**Проблема в коде:** `zone_automation_service.py` — `_process_correction_controllers()` при каждом цикле (~15 сек) с `missing_flags` создаёт `create_zone_event("CORRECTION_SKIPPED_MISSING_FLAGS", ...)`. Троттлинг есть только для infra-alert, но не для zone-events.

**Что сделать:**
1. Добавить per-zone троттлинг для `CORRECTION_SKIPPED_MISSING_FLAGS` (не чаще 1 события в N секунд)
2. Для повторов в окне троттлинга — инкрементировать счётчик/метрику вместо записи события
3. Сохранить первый event при смене reason/missing_flags (не терять переходы состояния)

**Тесты:**
- E2E-23: длительный missing_flags не создаёт event-storm

**Exit criteria для P1:** нет event-storm при `missing_flags`; для `stale_flags` всегда fail-closed.

---

### Этап P2 — Workflow Coordination (10-15 дней)

**Цель:** синхронизация Scheduler workflow и ZAS контроллеров.
**Зависимости:** P0 и P1 завершены.
**Закрывает:** BUG-01, BUG-02, BUG-03, BUG-04, BUG-06, BUG-07.

---

#### P2.1. Zone Workflow State — координация ZAS ↔ Workflow

**Закрывает:** BUG-02, BUG-04

**Проблема в коде:**
- `irrigation_controller.py:66-171` — `check_and_control_irrigation()` проверяет только `irrigation_interval_sec` и `water_level_ok`, но **не текущую фазу workflow**
- `scheduler_task_executor.py:3736` — при завершении startup возвращает `decision: "skip"` в scheduler, но ZAS не узнаёт

**Что сделать:**
1. Добавить per-zone `workflow_phase` в `_zone_states` (или отдельную структуру) в `zone_automation_service.py`
2. SchedulerTaskExecutor обновляет `workflow_phase` при каждом переходе: `idle`, `clean_fill`, `solution_fill`, `prepare_recirc`, `ready`, `irrigating`, `recovery`
3. ZAS проверяет `workflow_phase` перед irrigation: если не `ready`/`irrigating` → skip
4. ZAS проверяет `workflow_phase` перед correction: передаёт текущую фазу в `correction_controller`

**Реализация:** гибрид — in-memory cache + persist в zone_events при переходах, restore при старте.

**Тесты:**
- E2E-09: startup in progress → ZAS skip irrigation

---

#### P2.2. Блокировка irrigation по workflow phase

**Часть BUG-02**

**Что сделать:**
1. В `irrigation_controller.py` — `check_and_control_irrigation()` принимает `workflow_phase`
2. Если `workflow_phase` не в `[None, "idle", "ready", "irrigating"]` → return None (skip)
3. ZAS передаёт `workflow_phase` при вызове

---

#### P2.3. EC-компоненты по фазам

**Закрывает:** BUG-03

**Проблема в коде:** `correction_controller.py:803-906` — `required_components = ["npk", "calcium", "magnesium", "micro"]` всегда все 4.

**Что сделать:**
1. Добавить параметр `allowed_ec_components: Optional[List[str]]` в `check_and_correct()` и `_build_ec_component_batch()`
2. ZAS передаёт компоненты по `workflow_phase`:
   - `tank_filling` / `tank_recirc` → `["npk"]`
   - `irrigating` / `irrig_recirc` → `["calcium", "magnesium", "micro"]`
   - `ready` / `idle` / `None` → все (обратная совместимость)
3. Фильтрация: `required_components = [c for c in required if c in allowed]`

**Тесты:**
- E2E-10: workflow=tank_filling → correction uses only NPK
- E2E-11: workflow=irrigating → correction uses Ca/Mg/Micro

---

#### P2.4. Sensor mode activation из workflow + inline-коррекция при solution fill

**Закрывает:** BUG-01, BUG-06

**Проблема в коде:**
- `_start_two_tank_solution_fill()` (строка 2994) отправляет только valve/pump команды, НЕ активирует sensor mode
- `_start_two_tank_prepare_recirculation()` (строка 3097) — аналогично

**Что сделать:**
1. В `_start_two_tank_solution_fill()` после valve/pump commands → отправить `activate_sensor_mode` для pH/EC нод через `_resolve_online_node_for_channel(zone_id, channel="system", node_types=["ph","ec"])`
2. В каждом stop command plan → отправить `deactivate_sensor_mode`
3. При переходе в `solution_fill` → установить `workflow_phase = "tank_filling"`
4. ZAS в correction gating: если `workflow_phase == "tank_filling"` → разрешить коррекцию (workflow уже запустил насос)
5. Убрать из ZAS логику `activate_sensor_mode` при `missing_flags` (ownership только у workflow)

**Тесты:**
- E2E-01: Full startup cycle: startup → clean_fill → solution_fill → prepare_recirc → targets_reached
- E2E-13: solution_fill_start → activate_sensor_mode sent

---

#### P2.5. PID reset при смене фазы

**Закрывает:** BUG-07

**Проблема в коде:** `pid_state_manager.py` — PID state сохраняется по `(zone_id, pid_type)`, нет понятия «фаза». При смене prepare → irrigation EC target меняется, но integral заряжен от предыдущей фазы.

**Что сделать:**
1. При переходе `workflow_phase` (prepare → irrigation) → `del ph_controller._pid_by_zone[zone_id]`
2. Аналогично для ec_controller
3. PID пересоздаётся с новым target при следующей коррекции

**Тесты:**
- E2E-12: prepare → irrigation → PID integral reset

**Exit criteria для P2:** E2E координации фаз зелёные; нет команд полива в фазах startup/prepare.

---

### Этап P3 — Event Integrity + Safety (10 дней)

**Цель:** событие = подтверждённое действие, не намерение.
**Зависимости:** P1 и P2 завершены.
**Закрывает:** BUG-08, BUG-10, BUG-11, BUG-12.

---

#### P3.1. Bootstrap первого автополива

**Закрывает:** BUG-10

**Проблема в коде:** `irrigation_controller.py` — `get_last_irrigation_time()` ищет `IRRIGATION_STARTED` в `zone_events`. При `None` — `return None` (полив не запускается никогда). Комментарий в коде противоречит реализации.

**Что сделать:**
1. При `last_irrigation_time is None` — разрешать немедленный первый запуск (или использовать `zone.created_at` как точку отсчёта)
2. Синхронизировать поведение с комментарием в коде

**Тесты:**
- E2E-20: нет IRRIGATION_STARTED в history → первый автополив запускается

---

#### P3.2. Запись событий после подтверждения publish

**Закрывает:** BUG-11

**Проблема в коде:** `zone_automation_service.py` — в `_process_irrigation_controller()` и др. сначала `create_zone_event(...)`, затем `publish_controller_command(...)`. При failure publish — «фантомное» событие остаётся в БД.

**Что сделать:**
1. Для action-событий (`IRRIGATION_STARTED`, `RECIRCULATION_CYCLE`, коррекции) — писать **только после** успешного `publish_controller_command`
2. Для отказов — отдельные event types: `*_COMMAND_REJECTED`, `*_COMMAND_UNCONFIRMED`
3. Ввести `correlation_id` в `event_details` для склейки с `command_audit`

**Тесты:**
- E2E-21: publish fail/open circuit → событие успешного действия не создаётся

---

#### P3.3. Zone guards по дефолту

**Закрывает:** BUG-08

**Проблема в коде:** `command_bus.py:79-88` — `AE_ENFORCE_NODE_ZONE_ASSIGNMENT` и `AE_ENFORCE_COMMAND_CHANNEL_COMPATIBILITY` default=`"0"`.

**Что сделать:**
1. Изменить default с `"0"` на `"1"` в `command_bus.py`
2. Обновить `docker-compose.dev.yml` и `.env.example`

**Тесты:**
- E2E-15: команда к ноде чужой зоны → rejection + alert
- E2E-16: actuator cmd на sensor channel → rejection

---

#### P3.4. Политика компенсации partial EC batch

**Закрывает:** BUG-12

**Проблема в коде:** `correction_controller.py` (`apply_correction`) — EC batch `npk → calcium → magnesium → micro`. При сбое на N-ом компоненте → `EC_COMPONENT_BATCH_ABORTED`, но отправленные дозы не компенсируются.

**Что сделать:**
1. При partial failure — маркировать результат как `degraded` для внешнего workflow
2. Инициировать safety-path: forced recirculation + повторная оценка targets
3. Фиксировать `EC_BATCH_PARTIAL_FAILURE` с деталями (какие компоненты успешны, какие нет)

**Тесты:**
- E2E-22: сбой на 2/4 компоненте → degraded-path и компенсационный сценарий

**Exit criteria для P3:** нет фантомных `IRRIGATION_STARTED`/`EC_CORRECTED`; компенсационный path покрыт e2e.

---

### Этап P4 — Persistence + Recovery (10 дней)

**Цель:** восстановление workflow после рестарта без unsafe-эффектов.
**Зависимости:** P2 и P3 завершены.
**Закрывает:** BUG-05.

---

#### P4.1. Workflow state в БД

**Закрывает:** BUG-05

**Проблема в коде:** `scheduler_task_executor.py:2796` — всё состояние workflow в `payload` enqueue. Рестарт AE → потеря in-flight workflows, нет журнала активных workflows.

**Что сделать:**
1. Миграция БД — новая таблица:
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
2. При каждом переходе в two_tank workflow → UPDATE
3. Связать с in-memory `workflow_phase` из P2.1

---

#### P4.2. Startup recovery

**Что сделать:**
1. При запуске AE: `SELECT * FROM zone_workflow_state WHERE workflow_phase != 'idle'`
2. Для каждой активной зоны: проверить актуальность (не expired ли), при необходимости → enqueue continuation или → safety stop
3. Timeout policy для stale in-flight state

**Тесты:**
- E2E-19: workflow in DB → AE restart → resume

**Exit criteria для P4:** restart recovery e2e зелёный; нет «вечных» зависших фаз.

---

### Этап P5 — Decomposition (10-15 дней)

**Цель:** устранение god-object, модульная архитектура.
**Зависимости:** P0..P4 завершены.
**Закрывает:** BUG-09.

---

#### P5.1. Декомпозиция scheduler_task_executor.py

**Закрывает:** BUG-09

**Целевая структура:**
```
backend/services/automation-engine/
  domain/
    workflows/
      two_tank.py           # вся логика two-tank
      three_tank.py          # three-tank + cycle_start
      cycle_start.py
    policies/
      correction_gating_policy.py
      sensor_mode_policy.py
      event_integrity_policy.py
    models/
      workflow_models.py     # dataclass вместо Dict[str, Any]
      gating_models.py
      command_models.py
  application/
    scheduler_executor.py    # тонкий coordinator (<800 строк)
    workflow_router.py
    workflow_validator.py
  infrastructure/
    command_publisher.py     # adapter around CommandBus
    workflow_state_store.py  # in-memory + DB persistence
    observability.py         # structured logging/metrics
```

**Что вынести из `scheduler_task_executor.py`:**
- `two_tank_workflow.py` — startup, check-phases, helpers
- `three_tank_workflow.py` — three-tank + cycle_start
- `decision_engine.py` — `_decide_action`, reason codes, feature flags
- `workflow_helpers.py` — level reading, target evaluation, node resolution
- `scheduler_task_executor.py` → тонкий диспетчер

**Exit criteria для P5:** coordinator < 800 строк; все E2E-01..E2E-27 зелёные.

---

## 4. Тесты

### 4.1. Матрица E2E тестов

| ID | Тест | Покрывает | Файл | Этап |
|----|------|-----------|------|------|
| E2E-01 | Full startup cycle: startup → targets_reached | BUG-01, BUG-06 | `test_two_tank_workflow.py` | P2 |
| E2E-02 | Skip clean fill: tank already full | Happy path | `test_two_tank_workflow.py` | P5 |
| E2E-03 | Clean fill retry: timeout → retry → success | Retry logic | `test_two_tank_workflow.py` | P5 |
| E2E-04 | Solution fill timeout → fail | Timeout | `test_two_tank_workflow.py` | P5 |
| E2E-05 | Prepare recirc timeout → degraded | Degraded mode | `test_two_tank_workflow.py` | P5 |
| E2E-06 | Recovery success: drift → recovery → targets reached | Recovery | `test_two_tank_recovery.py` | P2 |
| E2E-07 | Recovery degraded: timeout → degraded ok | Degraded | `test_two_tank_recovery.py` | P5 |
| E2E-08 | Recovery max attempts → fail | Attempt limit | `test_two_tank_recovery.py` | P5 |
| E2E-09 | No irrigation during startup | BUG-02 | `test_workflow_coordination.py` | P2 |
| E2E-10 | NPK-only during prepare | BUG-03 | `test_workflow_coordination.py` | P2 |
| E2E-11 | CaMgMicro during irrigation | BUG-03 | `test_workflow_coordination.py` | P2 |
| E2E-12 | PID reset on phase change | BUG-07 | `test_workflow_coordination.py` | P2 |
| E2E-13 | Sensor mode from workflow | BUG-06 | `test_workflow_coordination.py` | P2 |
| E2E-14 | Zone isolation: 2 зоны, команды не пересекаются | Zone routing | `test_zone_isolation.py` | P5 |
| E2E-15 | Node-zone mismatch → rejection | BUG-08 | `test_zone_isolation.py` | P3 |
| E2E-16 | Channel-cmd compatibility → rejection | Guards | `test_zone_isolation.py` | P3 |
| E2E-17 | Enqueue failure → compensating stop | Compensation | `test_safety_compensation.py` | P5 |
| E2E-18 | Stop not confirmed → no restart | Safety guards | `test_safety_compensation.py` | P5 |
| E2E-19 | Workflow recovery after restart | BUG-05 | `test_workflow_persistence.py` | P4 |
| E2E-20 | First irrigation bootstrap | BUG-10 | `test_irrigation_bootstrap.py` | P3 |
| E2E-21 | No phantom success events | BUG-11 | `test_event_integrity.py` | P3 |
| E2E-22 | EC batch partial failure | BUG-12 | `test_ec_batch_failure_policy.py` | P3 |
| E2E-23 | Correction skip throttle | BUG-13 | `test_event_throttle.py` | P1 |
| E2E-24 | Stale correction flags → fail-closed | BUG-14 | `test_correction_flags_freshness.py` | P1 |
| E2E-25 | Three-tank unsupported workflow → reject | BUG-15 | `test_three_tank_workflow_contract.py` | P0 |
| E2E-26 | Sensor mode lifecycle | BUG-16 | `test_sensor_mode_lifecycle.py` | P1 |
| E2E-27 | Missing workflow in payload → fail-closed | BUG-17 | `test_scheduler_payload_contract.py` | P0 |

### 4.2. Структура тестов

```
backend/services/automation-engine/tests/e2e/
├── conftest.py                        # Fixtures: mock CommandBus, DB, enqueue
├── test_two_tank_workflow.py          # E2E-01..E2E-05
├── test_two_tank_recovery.py          # E2E-06..E2E-08
├── test_workflow_coordination.py      # E2E-09..E2E-13
├── test_irrigation_bootstrap.py       # E2E-20
├── test_event_integrity.py            # E2E-21
├── test_ec_batch_failure_policy.py    # E2E-22
├── test_event_throttle.py             # E2E-23
├── test_correction_flags_freshness.py # E2E-24
├── test_three_tank_workflow_contract.py # E2E-25
├── test_sensor_mode_lifecycle.py      # E2E-26
├── test_scheduler_payload_contract.py # E2E-27
├── test_zone_isolation.py             # E2E-14..E2E-16
├── test_safety_compensation.py        # E2E-17..E2E-18
└── test_workflow_persistence.py       # E2E-19
```

### 4.3. Стратегия моков

- `enqueue_internal_scheduler_task` → mock (записать payload, вернуть success)
- `CommandBus.publish_command` → mock (записать команду, вернуть True)
- `CommandBus.publish_controller_command_closed_loop` → mock (записать, вернуть DONE)
- `fetch()` (DB) → реальные PostgreSQL fixtures для zones/nodes/sensors
- `_read_level_switch` → parametrize (full/empty/stale/unavailable)
- `_evaluate_ph_ec_targets` → parametrize (reached/not_reached/stale)

---

## 5. Правила и ограничения

### 5.1. Что НЕЛЬЗЯ делать

1. **В одном PR** нельзя одновременно менять: payload-контракт, доменную логику дозирования, persistence recovery
2. Нельзя возвращать прямую публикацию команд вне `history-logger/CommandBus`
3. Нельзя добавлять silent fallback как постоянное поведение
4. Нельзя ломать §1.5 (что работает корректно)

### 5.2. Quality gates для каждого PR

- `ruff`/`flake8` — без ошибок
- `mypy` (или эквивалент) — без ошибок
- unit + contract tests по изменённому модулю — зелёные
- Минимум 1 e2e-сценарий на каждый новый reason_code/policy transition

### 5.3. Формат PR

```
## Scope
Закрывает P*.* (название задачи)

## Behavior Change
Что изменилось для runtime

## Risk + Rollback
Как откатить, что может пойти не так

## Tests
Какие тесты добавлены/изменены

## Compatible-With (при изменении контрактов)
Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0
```

### 5.4. Обновление документации (при реализации)

| Когда | Что обновить |
|-------|-------------|
| При изменении workflow states | `CORRECTION_CYCLE_SPEC.md` — интеграция state machine с SchedulerTaskExecutor |
| При изменении контракта scheduler↔AE | `SCHEDULER_AUTOMATION_TASK_EXECUTION_SCHEMA.md` — workflow_phase в response |
| При добавлении zone_workflow_state | `PYTHON_SERVICES_ARCH.md` — описание таблицы |
| При любых изменениях | `backend/services/automation-engine/README.md` — актуализировать |

### 5.5. Observability

**Метрики (добавлять по мере реализации):**
- `ae_workflow_transition_total{from,to}`
- `ae_gating_block_total{reason_code}`
- `ae_sensor_mode_transition_total{state}`
- `ae_command_publish_total{status}`
- `ae_event_integrity_violation_total`

**SLI-формулы:**

| SLI | Формула | Окно | Порог |
|-----|---------|------|-------|
| unsupported_workflow_rate | `unsupported_workflow / diagnostics_tasks_total` | rolling 15m | ≤ 1% |
| command_unconfirmed_rate | `command_unconfirmed / publish_attempt_total` | rolling 15m | ≤ 0.5% |
| correction_skip_burst | `correction_skipped_events / zone / hour` | 1h per zone | ≤ N (конфигурируемо) |

### 5.6. Rollout-политика

1. Новые проверки — под feature flags
2. Shadow-mode метрики (наблюдение, без blocking)
3. Canary 10% зон перед каждым расширением
4. Max +20% зон за итерацию
5. Расширение **только после 24h** без trigger-нарушений
6. При превышении SLO — **автостоп** и откат
7. Freeze-window: запрет параллельных релизов в `scheduler` и `history-logger` с P2/P3/P4

---

## 6. Оценка ресурсов

| Этап | Дни | Зависимости |
|------|-----|-------------|
| P0 — Contract Gates | 7 | — |
| P1 — Gating/Sensor Lifecycle | 10 | P0 |
| P2 — Workflow Coordination | 12 | P0, P1 |
| P3 — Event Integrity + Safety | 10 | P1, P2 |
| P4 — Persistence + Recovery | 10 | P2, P3 |
| P5 — Decomposition | 12 | P0..P4 |
| **Итого** | **~61** | |

**1 разработчик:** ~3 месяца (последовательно).
**2 разработчика:** ~2 месяца (Dev A: P0→P2→P4, Dev B: P1→P3→P5, B начинает после P0).
