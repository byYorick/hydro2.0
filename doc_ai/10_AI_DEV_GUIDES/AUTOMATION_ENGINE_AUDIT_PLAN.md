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

### BUG-10: [P1/HIGH] Невозможен первый автополив без исторического события

**Код (`irrigation_controller.py`):**
- `get_last_irrigation_time()` ищет только `IRRIGATION_STARTED` в `zone_events`.
- `check_and_control_irrigation()` при `last_irrigation_time is None` сразу возвращает `None`.

**Проблема:**
- Для новой зоны или после очистки событий автополив не стартует **никогда**.
- Комментарий в коде противоречит реализации: написано «можно запустить сразу (или подождать половину интервала)», но фактически всегда `return None`.

**Риск:**
- silent failure в production: зона может остаться без первого автоматического полива до ручного вмешательства.

### BUG-11: [P1/HIGH] Оптимистичная запись событий до фактической отправки команды

**Код (`services/zone_automation_service.py`):**
- В `_process_irrigation_controller()`/`_process_recirculation_controller()`/`_process_climate_controller()` сначала вызывается `create_zone_event(...)`, затем `publish_controller_command(...)`.

**Проблема:**
- Если отправка в history-logger/API не подтверждена (CircuitBreaker/open, network errors, timeout), в БД остаётся событие как будто действие выполнено.
- Для полива это критично: интервал считается от `IRRIGATION_STARTED`, и «фантомный старт» блокирует следующий реальный запуск.

**Риск:**
- Искажение доменной истории, неверные интервалы, неверная диагностика и аудит.

### BUG-12: [P2/MEDIUM] Частичный EC batch без компенсации/rollback

**Код (`correction_controller.py`, `apply_correction`):**
- EC batch отправляется по компонентам последовательно (`npk → calcium → magnesium → micro`).
- При сбое на N-ом компоненте фиксируется `EC_COMPONENT_BATCH_ABORTED`, но уже отправленные дозы не компенсируются и не маркируются как degraded-result для внешнего workflow.

**Проблема:**
- Получается частично скорректированный раствор с «поломанной» стехиометрией.
- Текущий контроль не инициирует автоматический safety-переход (например, forced recirculation + повторная оценка targets).

**Риск:**
- drift по EC/ионному составу, трудно воспроизводимые регрессии качества раствора.

### BUG-13: [P2/MEDIUM] Шторм событий `CORRECTION_SKIPPED_MISSING_FLAGS` без троттлинга

**Код (`services/zone_automation_service.py`):**
- В `_process_correction_controllers()` при каждом цикле с `missing_flags` создаётся `create_zone_event("CORRECTION_SKIPPED_MISSING_FLAGS", ...)`.
- Троттлинг есть только для infra-alert (`_emit_correction_missing_flags_signal`, `CORRECTION_FLAGS_MISSING_ALERT_THROTTLE_SECONDS`), но не для zone-events.

**Проблема:**
- При длительном отсутствии флагов (`flow_active/stable/corrections_allowed`) БД получает постоянный поток одинаковых событий.
- На стандартном цикле обработки это приводит к лишней записи и шуму в аналитике/дашбордах.

**Риск:**
- Рост объёма `zone_events`, деградация signal-to-noise в операционном мониторинге, ухудшение расследований инцидентов.

### BUG-14: [P1/HIGH] Гейтинг коррекций не валидирует свежесть correction_flags

**Код (`services/zone_automation_service.py`):**
- `_build_correction_gating_state()` нормализует `flow_active/stable/corrections_allowed` и сохраняет `*_ts`, но не проверяет их возраст перед разрешением коррекций.

**Проблема:**
- При stale flags система может продолжать коррекции на устаревшем состоянии потока/стабильности.
- Это особенно опасно после разрывов связи/лагов ingest: флаг остаётся `True`, хотя реальный поток уже остановлен.

**Риск:**
- Ложноположительный `gating_passed`, нежелательное дозирование и дрейф параметров раствора.

### BUG-15: [P1/HIGH] Silent fallback workflow в three-tank маскирует ошибки scheduler payload

**Код (`scheduler_task_executor.py`):**
- В `_execute_three_tank_startup_workflow()` используется `fallback_workflow = "refill_check" if workflow == "refill_check" else "cycle_start"`.
- Для любого неизвестного `workflow` (опечатка/ошибка контракта) выполнение молча переводится в `cycle_start`.

**Проблема:**
- Ошибка входного payload не детектируется как контрактная, а превращается в запуск реального сценария.
- Для two-tank аналогичный случай обрабатывается fail-closed (`unsupported_workflow`), что создаёт непоследовательное поведение между топологиями.

**Риск:**
- Скрытые дефекты интеграции scheduler↔AE и нежелательные операции водного контура вместо явного отказа.

### BUG-16: [P2/MEDIUM] Sensor mode не деактивируется при части блокировок gating

**Код (`services/zone_automation_service.py`):**
- В `_process_correction_controllers()` deactivation sensor mode выполняется только для `reason_code == "flow_inactive"`.
- Для `sensor_unstable` и `corrections_not_allowed` деактивация не выполняется.

**Проблема:**
- После предыдущего успешного цикла sensor mode может оставаться активным, даже когда коррекции длительно заблокированы не из-за потока.
- Это создаёт лишнюю нагрузку на сенсорные узлы и «размывает» семантику sensor mode как признака активной коррекции.

**Риск:**
- Длительная работа сенсоров/канала в ненужном режиме, лишний telemetry noise и осложнение диагностики.

### BUG-17: [P1/HIGH] Неявный default workflow (`cycle_start`) при неполном payload

**Код (`scheduler_task_executor.py`):**
- `_extract_workflow()` возвращает `"cycle_start"`, если `workflow/diagnostics_workflow/execution.workflow` отсутствуют.

**Проблема:**
- При частично битом payload или ошибке сериализации workflow не валидируется как missing-required, а silently заменяется на активный сценарий.
- Сервис выполняет рабочий цикл вместо fail-closed ответа о некорректном контракте.

**Риск:**
- Непредсказуемые старты workflow на дефектных задачах scheduler и скрытые интеграционные ошибки.

---

## 3.1. Подтверждение аудита по текущему коду (2026-02-15)

Выполнена дополнительная верификация реализаций Automation-Engine:

1. Проверена реальная связка `SchedulerTaskExecutor -> ZoneAutomationService -> CommandBus` на предмет координации фаз, sensor mode и fail-closed поведения.
2. Сверены контроллеры полива/рециркуляции с источником времени и event-driven интервалами.
3. Проверен EC batch flow (формирование + применение + ранний stop + abort path).
4. Повторно оценены guard-флаги node-zone/channel compatibility и их дефолтные значения.

Итог: исходные BUG-01..BUG-09 подтверждаются; добавлены BUG-10..BUG-17 как новые high-value findings.

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

#### 1.4. Исправить bootstrap первого автополива
**Приоритет:** P1
**Файлы:** `irrigation_controller.py`, `test_irrigation_controller.py`
**Суть:**
- Изменить поведение `last_irrigation_time is None`:
  - либо разрешать немедленный первый запуск;
  - либо использовать `zone.created_at`/`automation_enabled_at` как точку отсчёта.
- Явно синхронизировать поведение с документацией и комментарием в коде.

#### 1.5. Перенести запись событий после подтверждения публикации
**Приоритет:** P1
**Файлы:** `services/zone_automation_service.py`, `correction_controller.py`
**Суть:**
- Для action-событий (`IRRIGATION_STARTED`, `RECIRCULATION_CYCLE`, климат/коррекции) писать факт выполнения только после успешного `publish_controller_command`.
- Для отказов/ошибок — отдельные event types (`*_COMMAND_REJECTED`, `*_COMMAND_UNCONFIRMED`) без симуляции «успешного старта».
- Дополнительно: ввести correlation_id в event_details для склейки с command_audit.

#### 1.6. Троттлинг повторяющихся correction-skip событий
**Приоритет:** P2
**Файлы:** `services/zone_automation_service.py`
**Суть:**
- Добавить per-zone троттлинг для `CORRECTION_SKIPPED_MISSING_FLAGS` (например, не чаще 1 события в N секунд).
- Для повторов в окне троттлинга инкрементировать счётчик/метрику вместо записи дубликатного события.
- Сохранить первый event при смене reason/missing_flags (чтобы не терять важные переходы состояния).

#### 1.7. Freshness-валидация correction_flags в gating
**Приоритет:** P1
**Файлы:** `services/zone_automation_service.py`, `config/settings.py`
**Суть:**
- Ввести максимальный возраст флагов (`AE_CORRECTION_FLAGS_MAX_AGE_SEC`).
- При устаревших `flow_active_ts/stable_ts/corrections_allowed_ts` переводить gating в `can_run=False` с reason `stale_flags` и обязательной деактивацией sensor mode при необходимости.
- Добавить observability: отдельный zone_event и infra-alert по stale flags с троттлингом.

#### 1.8. Fail-closed обработка unsupported workflow для three-tank
**Приоритет:** P1
**Файлы:** `scheduler_task_executor.py`, `test_scheduler_task_executor.py`
**Суть:**
- Убрать silent fallback к `cycle_start` для неизвестных `workflow`.
- Возвращать явную ошибку `unsupported_workflow` (аналогично two-tank) и фиксировать событие с исходным payload.
- Для допустимых workflow сохранить текущее поведение без регрессии happy-path.

#### 1.9. Полный lifecycle sensor mode при gating-блокировках
**Приоритет:** P2
**Файлы:** `services/zone_automation_service.py`
**Суть:**
- Для блокировок `sensor_unstable` и `corrections_not_allowed` определить явную политику deactivation sensor mode.
- Добавить защиту от лишних повторных команд (stateful debounce уже есть) и события переходов состояния mode.
- Согласовать policy с `CORRECTION_CYCLE_SPEC.md` (когда sensor mode обязан быть активен/неактивен).

#### 1.10. Явная валидация mandatory workflow в scheduler payload
**Приоритет:** P1
**Файлы:** `scheduler_task_executor.py`, `scheduler_internal_enqueue.py`, `test_scheduler_task_executor.py`
**Суть:**
- Для diagnostic/startup задач требовать явно переданный workflow (без implicit `cycle_start` по умолчанию).
- При отсутствии workflow возвращать `invalid_payload_missing_workflow` и писать контрактный event.
- Сохранить backward-compatible режим через feature-flag на период миграции producer-ов.

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

### 6.4. Тесты целостности истории и первого запуска

| ID | Тест | Покрытие | Файл |
|----|------|----------|------|
| E2E-20 | **First irrigation bootstrap:** нет IRRIGATION_STARTED в history → первый автополив запускается корректно | BUG-10 | `test_irrigation_bootstrap.py` |
| E2E-21 | **No phantom success events:** publish fail/open circuit → событие успешного действия не создаётся | BUG-11 | `test_event_integrity.py` |
| E2E-22 | **EC batch partial failure policy:** сбой на 2/4 компоненте → фиксируется degraded-path и запускается компенсационный сценарий | BUG-12 | `test_ec_batch_failure_policy.py` |
| E2E-23 | **Correction skip throttle:** длительный missing_flags не создаёт event-storm | BUG-13 | `test_event_throttle.py` |
| E2E-24 | **Stale correction flags:** устаревшие timestamps блокируют коррекции (fail-closed) | BUG-14 | `test_correction_flags_freshness.py` |
| E2E-25 | **Three-tank unsupported workflow:** неизвестный workflow → явный reject, без silent fallback в cycle_start | BUG-15 | `test_three_tank_workflow_contract.py` |
| E2E-26 | **Sensor mode lifecycle:** при `sensor_unstable/corrections_not_allowed` mode деактивируется по policy | BUG-16 | `test_sensor_mode_lifecycle.py` |
| E2E-27 | **Missing workflow in payload:** отсутствует workflow → fail-closed с контрактной ошибкой | BUG-17 | `test_scheduler_payload_contract.py` |

### 6.5. Тесты зональной изоляции

| ID | Тест | Покрытие | Файл |
|----|------|----------|------|
| E2E-14 | **Zone isolation:** 2 зоны с workflow → команды не пересекаются | Zone routing | `test_zone_isolation.py` |
| E2E-15 | **Node-zone mismatch:** команда к ноде чужой зоны → rejection + alert | BUG-08 | `test_zone_isolation.py` |
| E2E-16 | **Channel-cmd compatibility:** actuator cmd на sensor channel → rejection | Guard validation | `test_zone_isolation.py` |

### 6.6. Тесты safety и compensation

| ID | Тест | Покрытие | Файл |
|----|------|----------|------|
| E2E-17 | **Enqueue failure → compensating stop:** enqueue fails → stop commands sent | Compensation | `test_safety_compensation.py` |
| E2E-18 | **Stop not confirmed → no restart:** stop fails → safety guard blocks restart | Safety guards | `test_safety_compensation.py` |
| E2E-19 | **Workflow recovery after restart:** workflow in DB → AE restart → resume | BUG-05 | `test_workflow_persistence.py` |

### 6.7. Рекомендуемая структура тестов

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
4. **1.4** Bootstrap первого автополива
5. **1.5** Event integrity (без фантомных success)
6. **1.6** Троттлинг correction-skip event storm
7. **1.7** Freshness-валидация correction_flags
8. **1.8** Fail-closed для unsupported workflow (three-tank)
9. **1.9** Lifecycle-policy для sensor mode
10. **1.10** Mandatory workflow validation в payload
11. **E2E-09, E2E-10, E2E-11, E2E-20, E2E-21, E2E-23, E2E-24, E2E-25, E2E-26, E2E-27** — тесты координации и целостности/контракта

### Sprint 2 (неделя 3-4): Sensor mode и inline-коррекция
5. **2.1** Sensor mode activation из workflow
6. **2.2** Inline-коррекция при solution fill
7. **2.3** PID reset при смене фазы
8. **E2E-01, E2E-06, E2E-13** — тесты workflow и sensor mode

### Sprint 3 (неделя 5-6): Персистенция и safety
9. **3.1** Workflow state в БД
10. **3.2** Startup recovery
11. Политика компенсации для частичного EC batch (BUG-12)
12. **E2E-17, E2E-18, E2E-19, E2E-22** — тесты safety/persistence/batch-failure

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
| Риск «фантомных» action events при недоставке команды | Средняя | Высокое | Запись success-события только после publish confirm, E2E-21 |
| Частичное EC дозирование без компенсации | Средняя | Высокое | Деградационный сценарий + компенсационный workflow, E2E-22 |
| Event-storm при missing correction flags | Средняя | Среднее | Троттлинг duplicate events + метрика счётчика, E2E-23 |
| stale correction_flags пропускают лишние дозирования | Средняя | Высокое | Max-age в gating + fail-closed reason `stale_flags`, E2E-24 |
| Silent fallback unknown workflow в three-tank | Низкая | Высокое | Явный reject `unsupported_workflow`, E2E-25 |
| Sensor mode остаётся активным при части gating-блокировок | Средняя | Среднее | Lifecycle-policy + тест переходов, E2E-26 |
| missing mandatory workflow silently defaults в cycle_start | Низкая | Высокое | Контрактная валидация payload + feature-flag миграции, E2E-27 |


---

## 10. Master Plan: рефакторинг всей системы Automation-Engine (SOLID + модульность + наблюдаемость)

> Цель этого раздела: зафиксировать **единый, исполнимый план полного рефакторинга** Automation-Engine,
> где архитектура, бизнес-логика, контракты, тестирование и observability развиваются синхронно.

### 10.1. Принципы и архитектурные требования

- **S (Single Responsibility):** каждый модуль решает одну задачу (валидация payload, orchestration workflow, publish команд, gating policy, sensor-mode lifecycle).
- **O (Open/Closed):** новые topologies/workflows добавляются через расширение стратегий, а не правкой централизованного god-object.
- **L (Liskov):** единые интерфейсы для workflow-обработчиков и policy-классов без скрытых side-effect.
- **I (Interface Segregation):** узкие протоколы для `WorkflowStateStore`, `WorkflowValidator`, `GatingPolicy`, `CommandPublisher`.
- **D (Dependency Inversion):** доменная логика зависит от абстракций, а не от `fetch/create_zone_event/httpx` напрямую.
- **PEP8 + typing-first:** типизированные dataclass/TypedDict протоколы, ограничение длины функций, единый стиль логирования.

### 10.2. Целевое разбиение модулей (target structure)

```text
backend/services/automation-engine/
  domain/
    workflows/
      two_tank.py
      three_tank.py
      cycle_start.py
    policies/
      correction_gating_policy.py
      sensor_mode_policy.py
      event_integrity_policy.py
    models/
      workflow_models.py
      gating_models.py
      command_models.py
  application/
    scheduler_executor.py            # тонкий coordinator
    workflow_router.py
    workflow_validator.py
  infrastructure/
    command_publisher.py             # adapter around CommandBus/history-logger
    workflow_state_store.py          # in-memory + DB/event persistence
    observability.py                 # structured logging/metrics helpers
```

### 10.3. Пошаговый roadmap (release train)

#### Release R1 — Contract Hardening (2 недели)

- Fail-closed валидация workflow payload (mandatory `workflow`, explicit topology gates).
- Удаление silent-fallback для unknown workflow во всех топологиях.
- Единый error taxonomy:
  - `invalid_payload_*`
  - `unsupported_workflow`
  - `contract_violation_*`
- Тесты: contract/unit для scheduler payload validator.

**Закрывает:** BUG-15, BUG-17.

#### Release R2 — Gating/Sensor Lifecycle (2 недели)

- Выделение `CorrectionGatingPolicy`.
- Freshness max-age для `flow_active/stable/corrections_allowed`.
- Явная state table для sensor-mode transitions.
- Троттлинг duplicate correction-skip событий + счётчики вместо event-storm.

**Закрывает:** BUG-13, BUG-14, BUG-16.

#### Release R3 — Workflow/ZAS Coordination (2-3 недели)

- Единый `workflow_phase` как часть состояния зоны.
- Блокировка irrigation/correction по фазе.
- Фазовое EC-дозирование (NPK для prepare; Ca/Mg/Micro для irrigation).
- Inline-correction на этапе `solution_fill` + explicit sensor activation from workflow.

**Закрывает:** BUG-01, BUG-02, BUG-03, BUG-04, BUG-06, BUG-07.

#### Release R4 — Event Integrity + Safety (2 недели)

- Запись action-событий только после подтверждения publish.
- Введение rejected/unconfirmed event types.
- Политика деградации и компенсации для partial EC-batch.
- Guard-флаги zone/channel включены по дефолту (с migration feature flag периодом).

**Закрывает:** BUG-08, BUG-11, BUG-12.

#### Release R5 — Persistence + Recovery + Decomposition Completion (2-3 недели)

- Персистентный `zone_workflow_state` + startup recovery.
- Финальная декомпозиция `scheduler_task_executor.py` (тонкий coordinator).
- Полный e2e регресс по матрице E2E-01..E2E-27.

**Закрывает:** BUG-05, BUG-09 и технический долг архитектуры.

### 10.4. Engineering DoD (Definition of Done) для каждого release

- Код проходит `ruff/flake8` + `mypy` (или эквивалентный typing gate).
- Unit + contract tests green.
- Минимум 1 e2e-сценарий на каждый новый reason_code/policy transition.
- Логи структурированы: `zone_id`, `workflow`, `reason_code`, `correlation_id`, `task_id`.
- Обновлены `doc_ai/*` спецификации, если изменены контракты/состояния.
- Для потенциально breaking изменений — feature flag + migration note.

### 10.5. Observability и эксплуатационные SLO

- Метрики:
  - `ae_workflow_transition_total{from,to}`
  - `ae_gating_block_total{reason_code}`
  - `ae_sensor_mode_transition_total{state}`
  - `ae_command_publish_total{status}`
  - `ae_event_integrity_violation_total`
- SLO (первичный baseline):
  - не более 1% `unsupported_workflow` на 10k задач
  - не более 0.5% `command_unconfirmed` на критических workflow командах
  - отсутствие event-storm: не более N correction-skip событий/зона/час (конфигурируемо)

### 10.6. Governance: управление рисками изменений

- Любая правка orchestration проходит через ADR-lite запись (краткая decision note).
- PR размером >800 строк логики делить минимум на 2-3 функциональных PR.
- Запрещено смешивать в одном PR:
  1) изменение контрактов payload,
  2) изменение доменной логики дозирования,
  3) изменение persistence recovery.

### 10.7. Карта трассировки BUG -> release -> тесты

| BUG | Release | Ключевой тест-кластер |
|-----|---------|------------------------|
| 15, 17 | R1 | contract payload / three-tank workflow |
| 13, 14, 16 | R2 | gating + sensor mode lifecycle |
| 01, 02, 03, 04, 06, 07 | R3 | workflow coordination + inline correction |
| 08, 11, 12 | R4 | guards + event integrity + compensation |
| 05, 09 | R5 | persistence recovery + architectural decomposition |

### 10.8. Порядок внедрения без остановки production

1. Включить новые проверки под feature flags.
2. Запустить shadow-mode метрики (только наблюдение, без blocking).
3. На 10-20% зон включить enforcement режим.
4. Расширить до 100% после стабильного окна (48-72 часа).
5. Удалить legacy fallback ветки после 2 релизов стабильной работы.


---

## 11. Жёсткий план рефакторинга (Execution Plan v2 — единственный источник исполнения)

> Этот раздел вводится как **обязательный operational-план**.
> Для реализации использовать именно его; разделы 7 и 10 считать контекстом и обоснованием.

### 11.1. Governance правило №1 (Single Source of Execution Truth)

- Источник исполнения: **раздел 11**.
- Любая задача в спринте должна иметь ссылку на пункт `11.x`.
- Если `11.x` и разделы 7/10 расходятся — приоритет у `11.x`.

### 11.2. Dependency Matrix (что блокирует что)

| Этап | Зависит от | Разблокирует | Блокирующие риски |
|------|------------|--------------|-------------------|
| P0 Contract Gates | - | P1, P2 | Несовместимость producer payload |
| P1 Gating/Sensor Lifecycle | P0 | P2, P3 | Ложные blocking/overblocking коррекций |
| P2 Workflow Coordination | P0, P1 | P3 | Регресс в коррекциях и поливе |
| P3 Event Integrity + Safety | P1, P2 | P4 | Расхождение event history и command audit |
| P4 Persistence + Recovery | P2, P3 | P5 | Неверный resume после рестарта |
| P5 Decomposition Final | P0..P4 | Release hardening | Скрытые side-effect при распиле модулей |

### 11.3. Этапы исполнения (обязательные deliverables)

#### P0 — Contract Gates (7 дней)

**Цель:** полный fail-closed на уровне входного контракта scheduler→AE.

**Deliverables:**
1. Явная схема payload для diagnostics/startup задач (`workflow` обязателен для tank topologies).
2. Единый коды ошибок контракта: `invalid_payload_*`, `unsupported_workflow`.
3. Feature-flag совместимости legacy payload (`AE_LEGACY_WORKFLOW_DEFAULT_ENABLED`, default=`0`).

**Exit criteria:**
- 0 silent fallback сценариев в тестах.
- 100% новых contract тестов зелёные.

#### P1 — Gating + Sensor Lifecycle (10 дней)

**Цель:** deterministic policy для correction gating и sensor mode.

**Deliverables:**
1. `CorrectionGatingPolicy` с max-age проверкой `flow_active/stable/corrections_allowed`.
2. `SensorModePolicy` с таблицей переходов (`activate/deactivate/noop`) для всех reason_code.
3. Троттлинг повторяющихся `CORRECTION_SKIPPED_*` событий + счётчик suppressed-events.

**Exit criteria:**
- Нет event-storm при `missing_flags`.
- Для `stale_flags` всегда fail-closed (документированный reason).

#### P2 — Workflow Coordination (10-15 дней)

**Цель:** синхронизация Scheduler workflow и ZAS контроллеров.

**Deliverables:**
1. `workflow_phase` как обязательное поле runtime-state зоны.
2. Блокировки irrigation/correction по фазе.
3. Разделение EC-компонентов по фазам (NPK vs Ca/Mg/Micro).
4. Inline-correction на `solution_fill` с корректным sensor activation.

**Exit criteria:**
- E2E сценарии координации фаз зелёные.
- Нет команд полива в фазах startup/prepare без `irrigation_allowed`.

#### P3 — Event Integrity + Safety (10 дней)

**Цель:** событие = подтверждённое действие, не намерение.

**Deliverables:**
1. Перенос action-events после подтверждения publish.
2. Отдельные event types для reject/unconfirmed.
3. Политика компенсации partial EC batch + safety-path.

**Exit criteria:**
- Нет фантомных `IRRIGATION_STARTED`/`EC_CORRECTED` без подтверждённой команды.
- Компенсационный path покрыт e2e.

#### P4 — Persistence + Recovery (10 дней)

**Цель:** восстановление workflow после рестарта без unsafe-эффектов.

**Deliverables:**
1. `zone_workflow_state` + миграция.
2. Startup recovery policy: resume vs safety-stop.
3. Timeout policy для stale in-flight state.

**Exit criteria:**
- Restart recovery e2e зелёный.
- Нет «вечных» зависших фаз.

#### P5 — Decomposition Final (10-15 дней)

**Цель:** устранение god-object и переход к модульной архитектуре.

**Deliverables:**
1. Разделение `scheduler_task_executor.py` на application/domain/infrastructure модули.
2. Тонкий coordinator + изолированные workflow handlers.
3. Удаление legacy fallback веток после migration window.

**Exit criteria:**
- Размер coordinator файла < 800 строк.
- Cyclomatic complexity ключевых функций в пределах agreed threshold.

### 11.4. CI/CD Quality Gates (обязательные)

**PR Gate (blocking):**
- `ruff`/`flake8`
- `mypy` (или эквивалент)
- unit + contract tests по изменённому модулю
- `git diff --check`

**Nightly Gate (blocking next-day deploy):**
- e2e матрица E2E-01..E2E-27
- chaos/restart recovery сценарии
- regression по event volume

### 11.5. Contract Versioning + Migration Calendar

- Ввести поле `payload_contract_version` для scheduler diagnostics/startup задач.
- Поддержка:
  - `v1` (legacy, через flag)
  - `v2` (mandatory workflow, fail-closed)
- Календарь:
  1. Неделя 1: dual-read + предупреждения
  2. Неделя 2: блокировка новых legacy задач
  3. Неделя 3: отключение `v1` в production

### 11.6. Anti-goals (что запрещено в этом рефакторинге)

1. Нельзя в одном PR одновременно менять:
   - payload-контракт,
   - доменную логику дозирования,
   - persistence recovery.
2. Нельзя возвращать прямую публикацию команд вне `history-logger/CommandBus`.
3. Нельзя добавлять «временные» silent fallback как постоянное поведение.

### 11.7. Incident Runbook (операционный минимум)

**Trigger A:** рост `unsupported_workflow` > 1% за 15 минут.
- Действия: rollback enforcement flag `AE_LEGACY_WORKFLOW_DEFAULT_ENABLED=1`, включить расширенный audit-log payload.

**Trigger B:** рост `command_unconfirmed` > 0.5%.
- Действия: ограничить rollout на 20%, включить degraded-safety mode, провести сверку command audit.

**Trigger C:** event-storm correction skips.
- Действия: увеличить throttle, включить suppressed-counter dashboard, проверить freshness источники flags.

### 11.8. Формат PR для этапов P0..P5

Каждый PR обязан содержать:
1. `Scope` (какой `P*` пункт закрывается)
2. `Behavior Change` (что изменилось для runtime)
3. `Risk` + `Rollback`
4. `Tests` (unit/contract/e2e)
5. `Compatible-With` строку при изменении контрактов/данных

---

## 12. Критика Execution Plan v2 и обязательные усиления (v2.1)

Ниже зафиксированы оставшиеся слабые места раздела 11, которые нужно устранить
до старта масштабного рефакторинга в production-контурах.

### 12.1. Слабое место: нет WBS-гранулярности внутри этапов P0..P5

**Проблема:** этапы крупные, но не декомпозированы до подзадач с однозначным owner/result.

**Риск:** этап формально «в процессе», но фактически блокирован на скрытом dependency.

**Усиление (обязательно):** для каждого `P*` ввести WBS-уровень `P*.1..P*.N` с полями:
- `owner_role`
- `input_artifacts`
- `output_artifacts`
- `blocking_dependencies`
- `acceptance_test_ids`

### 12.2. Слабое место: не зафиксирован RACI для критичных решений

**Проблема:** раздел 11 задаёт что делать, но не фиксирует, кто утверждает
breaking-решения по контрактам/feature-flags.

**Риск:** «архитектурный пинг-понг» между backend/python/qa при rollout.

**Усиление (обязательно):** добавить мини-RACI:
- `A` (Accountable): Tech Lead Automation
- `R` (Responsible): владелец этапа `P*`
- `C` (Consulted): Backend Lead, Python Services Lead, QA Lead
- `I` (Informed): DevOps on-call

### 12.3. Слабое место: метрики есть, но нет SLI-формул

**Проблема:** SLO заданы порогами, но нет единой формулы вычисления (числитель/знаменатель/окно).

**Риск:** разные дашборды показывают разные значения, решения о rollback субъективны.

**Усиление (обязательно):** добавить в observability-спеку:
- `unsupported_workflow_rate = unsupported_workflow / diagnostics_tasks_total` (rolling 15m)
- `command_unconfirmed_rate = command_unconfirmed / publish_attempt_total` (rolling 15m)
- `correction_skip_burst = correction_skipped_events / zone / hour`

### 12.4. Слабое место: не зафиксирован freeze-window для risky этапов

**Проблема:** P2/P3/P4 могут попасть в период высокой операционной нагрузки.

**Риск:** накладка с релизами других подсистем и усложнённый triage инцидентов.

**Усиление (обязательно):**
- ввод change-freeze окна для P2/P3/P4;
- запрет параллельных релизов в `scheduler` и `history-logger` в тот же день;
- обязательный canary 10% зон перед каждым расширением.

### 12.5. Слабое место: не описана стратегия данных для replay/backfill

**Проблема:** при переходе к новой event-integrity логике не зафиксирована политика
обработки исторических «фантомных» событий.

**Риск:** аналитика и аудит могут сравнивать несовместимые эпохи данных.

**Усиление (обязательно):**
- добавить флаг эпохи данных (`event_integrity_epoch`);
- описать backfill/reconciliation процедуру для `zone_events` ↔ `command_audit`;
- явно задокументировать «границу доверия» метрик до/после epoch-switch.

### 12.6. Слабое место: нет жёсткого лимита blast radius на этапе rollout

**Проблема:** раздел 11 описывает 10-20%-rollout как guideline, но без auto-stop критериев.

**Риск:** дефект может распространиться до ручной остановки.

**Усиление (обязательно):**
- автостоп расширения rollout при превышении любого trigger из 11.7;
- расширение только после 24h стабильного окна;
- max +20% зон за одну итерацию rollout.

### 12.7. Слабое место: не формализована обратная связь из эксплуатации

**Проблема:** после incident response нет обязательного postmortem-цикла.

**Риск:** одни и те же классы ошибок повторяются в следующих этапах.

**Усиление (обязательно):**
- postmortem в течение 48h;
- action-items маппить на `P*.x` WBS;
- без закрытия action-items — запрет перехода к следующему этапу.

### 12.8. Итог критики v2

Execution Plan v2 годен как operational skeleton, но до старта больших
изменений должен быть усилен пунктами 12.1-12.7.
До фиксации этих пунктов план считать **условно готовым**.
