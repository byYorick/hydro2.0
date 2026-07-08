# WATER_FLOW_ENGINE.md
# Полная логика водного цикла и контроля потока в системе 2.0
# Насосы • Клапаны • Расход • Уровень воды • Подача • Рециркуляция • Защита

Этот документ описывает всю логику управления водой в системе 2.0:
от датчиков уровня и расхода до алгоритмов насосов, клапанов и защиты.

**Версия:** 1.1  
**Дата:** 2026-07-08  
**Статус:** добавлен контур `solution_topup` (этап B, AGRO_AUTONOMY_MASTER_PLAN)

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Общая архитектура водной системы

Вода в гидропонной системе включает:

1. **Основной резервуар (tank)** 
2. **Насосы полива (irrigation pumps)** 
3. **Дозирующие насосы (pH/EC)** 
4. **Клапаны направления** 
5. **Расходомеры (flow sensors)** 
6. **Датчики уровня воды** 
7. **Опционально: рециркуляция, дренаж, переливы** 

Pipeline:

```
Уровень → Поток → Контроллеры → Команды → Узлы ESP32 → Результат → Телеметрия
```

---

# 2. Сенсоры водной системы

## 2.1. WATER_LEVEL_SENSOR

Типы:
- поплавковый (0 или 1)
- аналоговый (0–1.0)
- ультразвуковой (cm → глубина)

MQTT telemetry:
```json
{
 "value": 0.64,
 "unit": "relative",
 "ts": 1737355110000
}
```

В БД хранится в `telemetry_last`.

---

## 2.2. FLOW_SENSOR (расходомер)

Пример:
```json
{
 "value": 1.3,
 "unit": "L/min",
 "ts": 1737355105000
}
```

Используется для:

- подтверждения работы насоса 
- детекции NO_FLOW аварий 
- вычисления объёма расхода 
- калибровки полива 

---

## 2.3. PRESSURE_SENSOR (опционально)

```json
{ "value": 1.2, "unit": "Bar" }
```

---

# 3. Актуаторы

## 3.1. IRRIGATION_PUMP

Команда:
```json
{
  "cmd_id": "cmd-irrig-001",
  "cmd": "run_pump",
  "params": { "duration_ms": 8000 },
  "ts": 1737355112,
  "sig": "a1b2c3d4e5f6..."
}
```

## 3.2. VALVE (распределитель потоков)

Команды (единый формат):
- `set_relay` с `params.state: true|false`
- при необходимости выбора линии: `params.select_line: X`

## 3.3. RECIRCULATION_PUMP (опционально)

## 3.4. DRAIN_PUMP (сливной насос)

---

# 4. Irrigation Cycle Logic (основной полив)

Полив — это периодическое включение насоса для подачи раствора.

### 4.1. Формула запуска

```
if now - last_irrigation >= irrigation_interval_sec:
 if water_level_ok:
 запуск насоса
```

### 4.2. Длительность полива

```
pump.run(irrigation_duration_sec)
```

### 4.3. Flow‑подтверждение

После команды Python ждёт telemetry:

```
flow > 0.1 L/min в течение первых 3 секунд
```

Если нет — алерт:

```
NO_FLOW
```

---

# 5. Расчёт объёма полива

Объём полива рассчитывается так:

```
volume_L = sum(flow * dt)
```

Хранится в событиях:

```
IRRIGATION_FINISHED:
{
 "duration_sec": 8,
 "avg_flow": 1.2,
 "volume": 0.16
}
```

---

# 6. Water Level Logic

### Уровень считается низким, если:

```
value < 0.2 (или 20%)
```

### Действия:

- блокировка полива 
- алерт `WATER_LEVEL_LOW` 
- блокировка дозирования EC/pH 

---

# 7. Защита от сухого хода

Алгоритм:

```
pump_run_time > 3 сек AND flow < threshold → NO_FLOW alert → stop pump
```

---

# 8. Режим калибровки расхода

UI кнопка:

```
Start Flow Calibration
```

Алгоритм:

1. запуск насоса на 10 сек 
2. измерение потока 
3. вычисление постоянной K (пульс → L/min) 
4. сохранение в node_channel.config 

---

# 9. Режим наполнения (Fill Mode)

Может быть вызван вручную (как высокоуровневая операция),
но на MQTT отправляются только стандартные команды:

```json
{
  "cmd_id": "cmd-fill-001",
  "cmd": "set_relay",
  "params": { "state": true },
  "ts": 1737355112,
  "sig": "a1b2c3d4e5f6..."
}
```

```json
{
  "cmd_id": "cmd-fill-002",
  "cmd": "run_pump",
  "params": { "duration_ms": 8000 },
  "ts": 1737355112,
  "sig": "a1b2c3d4e5f6..."
}
```

Узел:

- включает клапан подачи
- включает насос
- контролирует уровень
- останавливается при достижении уровня

---

# 10. Режим слива (Drain Mode)

```json
{
  "cmd_id": "cmd-drain-001",
  "cmd": "set_relay",
  "params": { "state": true },
  "ts": 1737355112,
  "sig": "a1b2c3d4e5f6..."
}
```

```json
{
  "cmd_id": "cmd-drain-002",
  "cmd": "run_pump",
  "params": { "duration_ms": 8000 },
  "ts": 1737355112,
  "sig": "a1b2c3d4e5f6..."
}
```

Аналогично, но наоборот.

---

# 11. Управление рециркуляцией

Если включена:

```
каждые N минут → run recirculation_pump for M sec
```

Событие:
```
RECIRCULATION_CYCLE
```

---

# 12. Интеграция контроллеров

pH и EC корректируются только если:

```
water_level_ok AND not in irrigation AND not in drain
```

Flow влияет на:

- подтверждение дозирования EC/pH
- предотвращение передозировок

---

# 13. Alerts Engine для воды

Типы тревог:

- `WATER_LEVEL_LOW`
- `WATER_LEVEL_HIGH` (редко)
- `NO_FLOW`
- `PUMP_FAILURE`
- `VALVE_STUCK`
- `DRAIN_TIMEOUT`
- `FILL_TIMEOUT`

---

# 14. Zone Events для воды

События:

- `IRRIGATION_STARTED`
- `IRRIGATION_FINISHED`
- `WATER_LEVEL_CHANGED`
- `RECIRCULATION_CYCLE`
- `DRAIN_STARTED`
- `DRAIN_FINISHED`
- `FILL_STARTED`
- `FILL_FINISHED`

---

# 15. PostgreSQL схемы

### telemetry_last
```
metric_type = FLOW, WATER_LEVEL
value
updated_at
```

### commands
```
cmd = run_pump, set_relay
params = {duration_ms, state, select_line}
```

### events
```
IRRIGATION_FINISHED: {volume, duration}
```

---

# 16. Laravel UI

UI должен показывать:

- текущий уровень воды (бар)
- расход (график)
- статус насосов
- история поливов
- кнопки:
 - ручной полив
 - fill
 - drain
 - calibrate flow
- тревоги
- события

---

# 17. Automation-engine и планировщик

Типовые задачи рантайма (см. `../04_BACKEND_CORE/ae3lite.md`, `SCHEDULER_ENGINE.md`):

- старт/оркестрация полива и связанных шагов;
- проверка расхода/объёма по телеметрии;
- генерация событий и алертов;
- блокировка небезопасных действий (fail-closed).

---

# 18. Правила для ИИ

ИИ может:

- улучшать алгоритмы flow detection,
- добавлять adaptive irrigation,
- вводить auto-fill по расписанию,
- предлагать ML‑предсказание полива.

ИИ НЕ может:

- отключать защиту dry-run,
- снижать важность WATER_LEVEL_LOW,
- менять формат telemetry.

---

# 19. Контур автодолива бака раствора (`solution_topup`)

> **Этап B** из `doc_ai/AGRO_AUTONOMY_MASTER_PLAN.md`.  
> Цель: в фазе роста (`workflow_phase='ready'`) автоматически восполнять бак раствора
> при падении уровня ниже `level_solution_max`, не дожидаясь критического `level_solution_min`.

## 19.1. Контекст и границы

Two-tank контур уже использует дискретные датчики уровня в startup/поливе
(`clean_fill`, `solution_fill`, guards полива). В `ready` сегодня работает только
**stop-guard** по `level_solution_min` (сброс в startup через `GuardSolutionTankStartupResetUseCase`),
но нет **проактивного долива**.

`solution_topup` закрывает промежуточную зону между «бак полный» и «раствор критически
закончился»:

| Coarse level (`level_monitor.coarse_solution_tank_level_percent`) | `solution_min` | `solution_max` | Семантика | Действие `solution_topup` |
|------------------------------------------------------------------|----------------|----------------|-----------|---------------------------|
| 100% | triggered | triggered | Бак полный | **Не запускать** (hysteresis hold) |
| 50% | triggered | not triggered | Раствор есть, уровень ниже max | **Запускать** (целевое состояние долива) |
| 0% | not triggered | not triggered | Критическое истощение | **Не запускать** — срабатывает startup-reset guard, не topup |

Формулировка «уровень низкий, но не min» в мастер-плане означает: **`solution_min`
ещё подтверждён** (раствор в баке присутствует), но **`solution_max` уже не
подтверждён** (бак не полный). Это соответствует coarse **50%**, а не «отдельному
третьему датчику».

Вне scope v1:
- подмена/полная замена раствора (`solution_change`, этап D);
- дозирование NPK/pH/EC внутри topup (долив — только гидравлика; химия остаётся
  в штатных correction windows);
- прямой MQTT publish из Laravel/AE3 (только history-logger).

Согласованность с кодом:
- семантика датчиков: `level_switch_semantics.level_switch_is_triggered`, роли
  из `level_monitor.resolve_level_role`;
- coarse percent: `level_monitor.coarse_solution_tank_level_percent`;
- fail-safe паттерны: `handlers/solution_fill.py`, `handlers/clean_fill.py`;
- fast-path wake-up: `LEVEL_SWITCH_CHANGED` → `worker.kick()` (см.
  `AE3_IRR_LEVEL_SWITCH_EVENT_CONTRACT.md` §12).

## 19.2. Триггеры запуска

### 19.2.1. Реактивный (primary)

После ingest `level_switch_changed` в `zone_events` AE3 выполняет reconcile read-model
и **может** создать intent/task `solution_topup`, если одновременно:

1. `zone_workflow_state.workflow_phase = 'ready'` (или stage `complete_ready`);
2. `solution_topup_enabled = true` в runtime bundle;
3. read-model подтверждает **need topup**:
   - `level_solution_min` triggered (`solution_min=true`);
   - `level_solution_max` not triggered (`solution_max=false`);
4. нет активной conflicting task на зоне (partial unique index + lease);
5. не активен cooldown после предыдущего успешного/аварийного topup;
6. telemetry/freshness в пределах `telemetry_max_age_sec`.

Релевантные channel-level edges (fast-path hint, не единственное основание):

| Канал | Edge | Интерпретация |
|-------|------|---------------|
| `level_solution_max` | `1 → 0` | Уровень опустился ниже max — кандидат на topup |
| `level_solution_min` | `0 → 1` | Восстановление после долива/полива — **не** старт topup |
| `level_solution_min` | `1 → 0` | Критическое истощение — **не** topup, startup-reset guard |

`initial=true` после reconnect обрабатывается идемпотентно: reconcile-only, без
повторного terminal outcome.

### 19.2.2. Периодический (optional, backup)

Laravel scheduler может диспатчить **probe-tick** по расписанию (аналог `lighting_tick`):

- `intent_type = 'SOLUTION_TOPUP_TICK'`
- endpoint AE3: `POST /zones/{id}/start-solution-topup`
- tick **не открывает клапаны сам** — только claim intent → AE3 reconcile → create task
  если условия §19.2.1 выполнены.

Рекомендуемый интервал: **15–30 мин** в фазе роста (конфигурируемо per zone/recipe).
Периодический tick нужен как страховка при пропущенных MQTT events.

### 19.2.3. Ручной (operator)

UI/API может инициировать тот же endpoint с `source='operator'` и явным
`idempotency_key` — для тестов и принудительного долива.

## 19.3. Гистерезис, таймауты, лимиты

### 19.3.1. Гистерезис low → max

- **Старт долива:** `solution_min=true` **AND** `solution_max=false`.
- **Стоп долива (success):** `solution_max=true` (подтверждено DB read-model).
- **Hold (не перезапускать):** пока `solution_max=true`, новые topup **запрещены**
  даже при periodic tick.
- **Re-arm:** только после edge `solution_max: true → false` **или** истечения
  `solution_topup_cooldown_sec` при сохранении `solution_max=false`.

Это предотвращает «дёргание» клапана на шуме около max.

### 19.3.2. Таймауты

Конфиг (zone `logic_profile` → runtime bundle, секция `startup` / `fail_safe_guards`):

| Поле | Default | Смысл |
|------|---------|-------|
| `solution_topup_timeout_sec` | `900` (15 мин) | Макс. длительность одного topup cycle |
| `solution_topup_cooldown_sec` | `300` (5 мин) | Min интервал между topup на зоне |
| `solution_topup_clean_min_check_delay_ms` | `5000` | Задержка leak/source guard по clean min (mirror `solution_fill`) |
| `solution_topup_solution_min_check_delay_ms` | `60000` | Задержка leak guard по solution min (mirror `solution_fill`) |
| `level_poll_interval_sec` | `2` | Poll interval на stage `solution_topup_check` |

Stage deadline = `now + solution_topup_timeout_sec` при входе в active fill.

### 19.3.3. Max volume per tick

v1 (без обязательного flow-meter на topup path):

- hard cap задаётся **`solution_topup_timeout_sec`** + command plan duration (как
  `solution_fill`);
- опционально `solution_topup_max_duration_ms` в command plan (≤ `solution_topup_timeout_sec`).

v1.1 (при наличии FLOW telemetry на fill path):

- `solution_topup_max_volume_ml` — discard/abort при превышении интеграла расхода за tick;
- при отсутствии flow sensor поле игнорируется (fail-open на volume, fail-closed на level/timeout).

## 19.4. Гидравлический path (command plan)

По умолчанию topup **переиспользует** тот же actuator path, что и `solution_fill_start`
(чистая вода из clean-бака в solution-бак):

```
pump_main ON
valve_clean_supply ON
valve_solution_fill ON
```

Stop plan (`solution_topup_stop`) — зеркало `solution_fill_stop`:

```
pump_main OFF
valve_solution_fill OFF
valve_clean_supply OFF
```

Команды публикуются **только** через history-logger (`POST /commands`).

Named plans в `two_tank_commands` (runtime bundle):

- `solution_topup_start` — alias/copy `solution_fill_start` unless overridden;
- `solution_topup_stop` — alias/copy `solution_fill_stop`.

## 19.5. Fail-safe (fail-closed)

AE3 **дублирует** firmware guards (см. `AE3_IRR_FAILSAFE_AND_ESTOP_CONTRACT.md`).
Node aggregate events — fast-path; terminal outcome только после DB confirmation.

| Условие | Detection | AE3 outcome | Actuator safe state | Alert |
|---------|-----------|-------------|---------------------|-------|
| **Leak** | после `solution_topup_solution_min_check_delay_ms` `level_solution_min` not triggered | `solution_topup_leak_stop` | stop plan | `biz_solution_topup_leak` + `solution_topup_leak_detected` |
| **Source empty** | после `solution_topup_clean_min_check_delay_ms` `level_clean_min` not triggered | `solution_topup_source_empty_stop` | stop plan | `biz_solution_topup_source_empty` + `solution_topup_source_empty` |
| **Timeout** | stage deadline без `solution_max` | `solution_topup_timeout_stop` | stop plan | `biz_solution_topup_timeout` + `solution_topup_timeout` |
| **Overflow / stuck max** | `solution_max` triggered, но flow/irr_state mismatch после stop | `solution_topup_overflow_stop` | stop plan + probe | `biz_solution_topup_overflow` |
| **E-STOP** | `EMERGENCY_STOP_ACTIVATED` | reconcile → stop или hold | OFF snapshot | existing E-STOP alerts |
| **Stale/unavailable level** | telemetry age / missing | poll hold или fail | no new commands | `two_tank_solution_*` codes |
| **Zone busy** | active `cycle_start` / `irrigation_start` / другой topup | reject intent `409` | no change | — |
| **Not ready** | `workflow_phase != 'ready'` | reject intent `409` | no change | — |
| **Depleted (min lost)** | `solution_min` not triggered | **no topup**; startup-reset guard | no topup start | existing guard path |

После любого fail-closed outcome:
1. выполнить stop command plan через HL;
2. probe `irr_state` (expected OFF snapshot);
3. записать `zone_event` + biz alert;
4. task → `failed` с каноническим `error_code`;
5. **`solution_topup_cooldown_sec`** блокирует немедленный retry (кроме operator `force` mode).

## 19.6. Task type и AE3 workflow

| Поле | Значение |
|------|----------|
| `ae_tasks.task_type` | `solution_topup` |
| `workflow` | `solution_topup` |
| `topology` | `two_tank` (только) |
| Guard phase | `workflow_phase='ready'` |

Минимальный stage graph (outline — см. §19.8):

```
solution_topup_guard → solution_topup_start → solution_topup_check
  → solution_topup_stop → completed
```

Terminal fail stages: `solution_topup_timeout_stop`, `solution_topup_leak_stop`,
`solution_topup_source_empty_stop`, `solution_topup_overflow_stop`.

Domain events (`zone_events.type`):

- `SOLUTION_TOPUP_STARTED`
- `SOLUTION_TOPUP_DONE`
- `SOLUTION_TOPUP_TIMEOUT`
- `SOLUTION_TOPUP_SOURCE_EMPTY`
- `SOLUTION_TOPUP_LEAK_DETECTED`

Aggregate node events (firmware, **planned** mirror `solution_fill_*`):

- `solution_topup_completed`
- `solution_topup_timeout`
- `solution_topup_source_empty`
- `solution_topup_leak_detected`

До реализации firmware aggregate AE3 обязан достигать тех же outcomes через
DB-first reconcile (как `clean_fill_check` timeout path).

## 19.7. API contract (draft): `POST /zones/{id}/start-solution-topup`

Симметричен `POST /zones/{id}/start-lighting-tick` (intent claim → task create → worker kick).

**Request body:**

```json
{
  "source": "laravel_scheduler",
  "idempotency_key": "sched:zone:42:solution_topup:2026-07-08T10:00:00Z",
  "mode": "normal",
  "trigger": "periodic_tick"
}
```

| Поле | Тип | Обяз. | Описание |
|------|-----|-------|----------|
| `source` | string | да | `laravel_scheduler` \| `level_event` \| `operator` |
| `idempotency_key` | string | да | 8–160 chars; unique per `(zone_id, key)` |
| `mode` | string | нет | `normal` (default) \| `force` — `force` bypass cooldown, не bypass fail-safe |
| `trigger` | string | нет | `periodic_tick` \| `level_switch` \| `manual` — observability only |

**Success (202/200):**

```json
{
  "status": "accepted",
  "zone_id": 42,
  "intent_id": 1001,
  "task_id": 501,
  "decision": "claimed",
  "task_type": "solution_topup"
}
```

**Errors (draft):**

| HTTP | code | Условие |
|------|------|---------|
| 409 | `start_solution_topup_zone_busy` | active task/intent на зоне |
| 409 | `start_solution_topup_not_ready` | `workflow_phase != 'ready'` |
| 409 | `start_solution_topup_level_not_low` | нет need-topup (max triggered или min lost) |
| 409 | `start_solution_topup_cooldown_active` | cooldown не истёк |
| 409 | `start_solution_topup_intent_not_found` | intent не найден по key |
| 429 | `start_solution_topup_rate_limited` | rate limit endpoint |
| 503 | `start_solution_topup_intent_claim_unavailable` | DB claim failed |

**Invariants:**
- Laravel **не** публикует MQTT;
- один active execution task per zone;
- topup не стартует при active `irrigation_start` / `cycle_start`.

## 19.8. Outline handler FSM (`solution_topup.py`)

1. **`solution_topup_guard`** — проверить `workflow_phase=ready`, `solution_topup_enabled`,
   need-topup (`min=true`, `max=false`), cooldown, zone not busy; иначе terminal skip/fail.
2. **`solution_topup_start`** — dispatch `solution_topup_start` command plan через HL;
   set `stage_deadline_at = now + solution_topup_timeout_sec`; event `SOLUTION_TOPUP_STARTED`.
3. **`solution_topup_check`** (poll loop) — read levels + recent storage events:
   - success path: `solution_max triggered` → transition stop;
   - leak/source/estop paths → mirror `solution_fill_check` delays;
   - deadline → timeout stop + alert.
4. **`solution_topup_stop`** — dispatch stop plan; wait terminal `DONE`; probe irr_state OFF.
5. **`solution_topup_complete`** — event `SOLUTION_TOPUP_DONE`; task `completed`; set cooldown marker.
6. **Fail terminals** — `*_leak_stop`, `*_source_empty_stop`, `*_timeout_stop`, `*_overflow_stop`:
   stop plan → probe → biz alert → task `failed`.
7. **Idempotency** — повторный tick при `solution_max=true` → no-op completed intent;
   duplicate `level_solution_max` edge during active topup → continue check stage only.

## 19.9. Конфликты с другими контурами

| Active process | `solution_topup` behavior |
|----------------|-------------------------|
| `irrigation_start` running | reject / defer (zone busy) |
| `cycle_start` running | reject (zone busy) |
| `correction` window | topup independent, но single-task rule: correction waits |
| `lighting_tick` | independent; different task type, same busy arbitration |
| Startup-reset (`solution_min` lost) | topup suppressed; guard resets workflow to startup |

## 19.10. Intent / DATA_MODEL (draft)

Черновик для `zone_automation_intents` (полная фиксация — в `DATA_MODEL_REFERENCE.md`
при миграции):

```
intent_type: SOLUTION_TOPUP_TICK | SOLUTION_TOPUP (manual)
task_type:   solution_topup
```

**Payload (`zone_automation_intents.payload`):**

```json
{
  "source": "laravel_scheduler",
  "task_type": "solution_topup",
  "workflow": "solution_topup",
  "topology": "two_tank",
  "grow_cycle_id": 123,
  "mode": "normal",
  "trigger": "periodic_tick"
}
```

Ограничения (как §6.8 `DATA_MODEL_REFERENCE.md`):
- `task_payload` / `schedule_payload` / device steps **запрещены** в intent;
- wake-up only; command plans резолвятся AE3 из runtime bundle.

**Idempotency key (scheduler):**

```text
sched:zone:{zone_id}:solution_topup:{slot_iso8601}
```

**Laravel dispatch (draft):**
- `ScheduleDispatcher`: mapping `solution_topup` schedule kind → endpoint `/start-solution-topup`;
- `isAeDispatchableTaskType`: добавить `solution_topup` для AE3 runtime zones.

## 19.11. Error codes (draft для `error_codes.json`)

См. consolidated list в ответе агента / `ERROR_CODE_CATALOG.md` при реализации.

## 19.12. Критерии приёмки (этап B)

1. В `ready` при `solution_min=true`, `solution_max=false` автоматически выполняется
   долив до `solution_max=true`.
2. Fail-safe leak/source/timeout/overflow → stop + alert + safe actuators.
3. Single active task per zone сохранён; нет конфликта с поливом/startup.
4. `LEVEL_SWITCH_CHANGED` будит reconcile, но terminal outcome только по DB read-model.
5. E2E node_sim two-tank: падение уровня в ready → topup → восстановление до max.

---

# Конец файла WATER_FLOW_ENGINE.md
