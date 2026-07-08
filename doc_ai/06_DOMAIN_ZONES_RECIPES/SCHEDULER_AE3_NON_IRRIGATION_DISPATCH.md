# SCHEDULER_AE3_NON_IRRIGATION_DISPATCH
# Dispatch света/климата/пр. для AE3 (C1)

**Статус:** реализовано для **lighting** (C1) и для **greenhouse climate** (крышные форточки): Laravel scheduler → соответствующий `POST ...` в AE3 → history-logger → MQTT. Для **diagnostics** включён compat-path через `POST .../start-cycle` → AE3 `cycle_start`. Расширение **lighting day/night ON/OFF** (этап A, `AGRO_AUTONOMY_MASTER_PLAN.md` §A) — **задокументировано**, реализация payload `desired_state` / `brightness_pct` — в коде по §A.2–A.3 того же плана. Зональные типы `climate`/`mist`/`ventilation` в рецепте без отдельного AE-endpoint по-прежнему **не** автодиспатчатся на AE3 (см. `SCHEDULER_ENGINE.md`); климат **теплицы** идёт отдельным контуром `greenhouse_automation_*`, а не через `zone_automation_intents` с `task_type=climate`.
**Связано с:** `SCHEDULER_ENGINE.md`, `ScheduleDispatcher.php`, `ae3lite.md`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Проблема (историческая / остаточная)

Ранее при `zones.automation_runtime = 'ae3'` планировщик диспатчил только **полив** (`start-irrigation`); свет из расписания не запускался автоматически; климат теплицы (общие форточки) не имел отдельного контура.

**Текущее состояние:** для **lighting** добавлен канонический путь `POST .../start-lighting-tick` → задача `lighting_tick` (C1). Для **`diagnostics`** включён scheduler-dispatch через существующий `POST .../start-cycle` с intent `DIAGNOSTICS_TICK` и исполнением через compat-path `cycle_start`. Для **greenhouse climate (крыша)** — `greenhouse_automation_intents` + `POST /greenhouses/{id}/start-climate-tick` (см. `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`). Расписания **`climate`**, **`mist`**, **`ventilation`** на уровне **зоны** на AE3 по-прежнему **не диспатчатся** до появления отдельных compat-endpoint-ов и task type в AE3.

План в `schedule-workspace` показывает окна из effective targets; типы без автодиспатча перечисляются в `capabilities.non_executable_planned_task_types`.

---

## 2. Цель C1

Обеспечить **определённый** способ автоматического запуска (хотя бы для **lighting**) из того же Laravel scheduler без нарушения инварианта «команды к узлам только через history-logger».

---

## 3. Варианты архитектуры (на выбор перед кодом)

### 3.1. Расширить AE3: отдельные compat-endpoints

- `POST /zones/{id}/start-lighting-tick` (и аналоги) с intent в БД, идемпотентностью и rate-limit как у `start-irrigation`.
- Плюсы: явные контракты, не смешивать с two-tank cycle.
- Минусы: больше surface area в AE, дублирование claim/marker логики.

### 3.2. Единый `start-cycle` с типом задачи в теле

- Расширить payload `start-cycle`, чтобы для scheduler создавалась **узкая** задача (не полный two-tank cycle), если `task_type` из intent = `lighting_tick`.
- Минусы: риск смешения с diagnostics/cycle_start; нужна жёсткая валидация в `CreateTaskFromIntentUseCase`.

### 3.3. Фоновый тик в AE без Laravel HTTP

- AE периодически читает effective targets и сам публикует команды света по расписанию.
- Минусы: дублирование источника истины с Laravel scheduler; сложнее аудит intentов.

**Рекомендация черновика:** начать с **3.1** для одного типа (`lighting`), повторить паттерн `start-irrigation` (intent → task → HL).

---

## 4. Изменения по слоям (чек-лист)

| Слой | Действия |
|------|----------|
| `doc_ai` | Обновить `MQTT_SPEC` / `HISTORY_LOGGER_API` только если появятся новые команды или форматы |
| Laravel | `ScheduleDispatcher`: для AE3 разрешить `lighting` → новый endpoint; `ZoneScheduleItemBuilder` без изменений или payload для длительности |
| PostgreSQL | При новых `intent_type` — миграция + `DATA_MODEL_REFERENCE.md` |
| AE3 | Маршрут, claim intent, task type, workflow стадий (минимальный граф для «тика света») |
| Frontend | Убрать/сузить предупреждение, когда `non_executable_planned_task_types` пуст |

---

## 5. Критерии приёмки C1

1. При включённом флаге/конфиге зона с AE3 получает **реальный** dispatch lighting по расписанию (e2e: scheduler → AE → HL → MQTT mock).
2. Нет прямой публикации команд из Laravel в MQTT.
3. Intent lifecycle согласован с `zone_automation_intents` и не ломает существующий полив.

---

## 6. Ограничения

- Не восстанавливать удалённые `POST /scheduler/task` в Python.
- Любой новый HTTP endpoint в AE — с тестами и описанием в `ae3lite.md`.

---

## 7. Освещение: day/night ON/OFF (`lighting_tick`, этап A)

**Связано с:** `EFFECTIVE_TARGETS_SPEC.md` §4.4, `AGRO_AUTONOMY_MASTER_PLAN.md` §A, `SchedulerCycleOrchestrator.php`, `ScheduleDispatcher.php`, `cycle_start_planner.py`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

### 7.1. Проблема (baseline до этапа A)

Базовый C1-path (`POST /zones/{id}/start-lighting-tick` → `lighting_tick`) dispatch'ит tick только на **границе** окна фотопериода, но AE3 planner (`cycle_start_planner._build_lighting_tick_plan`) всегда строит план **включения** с фиксированным duty (fallback `100%`). На переходе `on → off` свет не гасится — нарушение фотопериода для плодовых культур.

### 7.2. Триггер dispatch (Laravel)

`SchedulerCycleOrchestrator` для schedule item с `startTime`/`endTime` (окно из `LightingScheduleParser` / effective targets):

1. На каждом scheduler tick сравнивает «желаемое состояние» освещения: `desiredNow = isTimeInWindow(now, startTime, endTime)` vs `desiredLast` для предыдущего cursor.
2. Dispatch выполняется **только при смене** `desiredNow !== desiredLast` (вход в окно или выход из него).
3. В job payload добавляется:
   - `desired_state`: `"on"` если `desiredNow === true`, иначе `"off"`;
   - `brightness`: значение `targets.lighting.brightness` (для ON-tick; см. §7.4).

Для lighting **без** окна (interval / point time-spec) — поведение C1: каждый триггер считается ON-tick, `desired_state` default `"on"`.

### 7.3. HTTP-контракт `POST /zones/{id}/start-lighting-tick`

Канонический ingress AE3 (не меняется URL). Тело запроса (`StartLightingTickRequest`):

| Поле | Тип | Обязательность | Описание |
|------|-----|----------------|----------|
| `source` | string | да (default `laravel_scheduler`) | Источник intent |
| `idempotency_key` | string | да | Ключ идемпотентности (correlation scheduler) |
| `desired_state` | `"on"` \| `"off"` | нет (default `"on"`) | Целевое состояние освещения для данного tick |
| `brightness_pct` | int `0..100` | нет | Явная яркость для ON-tick; для OFF-tick игнорируется |

**Примеры payload:**

Включение в `on_time` (яркость 80% из effective targets):

```json
{
  "source": "laravel_scheduler",
  "idempotency_key": "sch:z7:lighting:2026-07-08T06:00:00+03:00",
  "desired_state": "on",
  "brightness_pct": 80
}
```

Выключение в `off_time`:

```json
{
  "source": "laravel_scheduler",
  "idempotency_key": "sch:z7:lighting:2026-07-08T22:00:00+03:00",
  "desired_state": "off"
}
```

`ScheduleDispatcher.php` формирует `request_payload` для endpoint `/start-lighting-tick`, пробрасывая `desired_state` и `brightness_pct` из scheduler job payload (см. §A.2 мастер-плана).

### 7.4. Разрешение яркости ON-tick

Приоритет для `desired_state="on"`:

1. Явный `brightness_pct` в HTTP-запросе (из Laravel dispatch).
2. `targets.lighting.brightness` из effective targets / zone snapshot.
3. Day/night config (`extensions.day_night.lighting` + `day_night_enabled`) — если tick попадает в дневное окно.
4. Fallback `100` (только если targets не заданы; для production рецептов яркость должна быть явной).

При `desired_state="off"` AE3 **не** использует `brightness_pct`; целевой duty = `0` (PWM) или `state=false` (relay).

### 7.5. Исполнение в AE3 (`lighting_tick`)

`CycleStartPlanner._build_lighting_tick_plan`:

| `desired_state` | Канал actuator | Команда MQTT |
|-----------------|----------------|--------------|
| `"on"` | PWM (`light_main`, `*pwm*`) | `set_pwm` `{duty: brightness_pct}` |
| `"on"` | relay | `set_relay` `{state: true}` |
| `"off"` | PWM | `set_pwm` `{duty: 0}` |
| `"off"` | relay | `set_relay` `{state: false}` |

Workflow: одношаговый `lighting_tick`, `complete_on_ack=true`. Команды — только через history-logger.

### 7.6. Критерии приёмки (этап A, dispatch-слой)

1. На границе `off_time` scheduler создаёт intent с `desired_state=off` и AE3 публикует команду выключения.
2. На границе `on_time` — intent с `desired_state=on` и duty из `brightness` / `brightness_pct`.
3. Повторный tick без смены состояния окна **не** dispatch'ится orchestrator'ом (инвариант C1 сохранён).
4. Нет прямой MQTT-публикации из Laravel.

---

**См. также:** `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`, `doc_ai/04_BACKEND_CORE/ae3lite.md`.
