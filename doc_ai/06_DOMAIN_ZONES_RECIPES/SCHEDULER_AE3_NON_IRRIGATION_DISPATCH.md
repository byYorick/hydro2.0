# SCHEDULER_AE3_NON_IRRIGATION_DISPATCH
# Dispatch света/климата/пр. для AE3 (C1)

**Статус:** реализовано для **lighting** (C1): Laravel scheduler → `POST .../start-lighting-tick` → AE3 task `lighting_tick` → history-logger → MQTT. Для **diagnostics** включён compat-path через `POST .../start-cycle` → AE3 `cycle_start`. Климат/прочие типы по-прежнему вне dispatch.  
**Связано с:** `SCHEDULER_ENGINE.md`, `ScheduleDispatcher.php`, `ae3lite.md`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

---

## 1. Проблема (историческая / остаточная)

Ранее при `zones.automation_runtime = 'ae3'` планировщик диспатчил только **полив** (`start-irrigation`); свет/климат из расписания не запускались автоматически.

**Текущее состояние:** для **lighting** добавлен канонический путь `POST .../start-lighting-tick` → задача `lighting_tick` (C1). Для **`diagnostics`** включён scheduler-dispatch через существующий `POST .../start-cycle` с intent `DIAGNOSTICS_TICK` и исполнением через compat-path `cycle_start`. Расписания **`climate`**, **`mist`**, **`ventilation`** и т.п. на AE3 по-прежнему **не диспатчатся** до появления отдельных compat-endpoint-ов и task type в AE3.

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

**См. также:** `doc_ai/06_DOMAIN_ZONES_RECIPES/SCHEDULER_ENGINE.md`, `doc_ai/04_BACKEND_CORE/ae3lite.md`.
