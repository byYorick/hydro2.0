# ZONE_CONTROLLER_FULL.md
# Полный детальный документ Zone Controllers 2.0
# (Nutrient/pH, EC, Climate, Irrigation, Light)

Этот документ описывает полный набор контроллеров,
которые управляют зоной теплицы в архитектуре 2.0.

Backend является «мозгом» всех контроллеров.
Узлы ESP32 — исполнители, работающие через MQTT.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

# 1. Общая концепция контроллеров зоны

Каждая зона имеет свои цели (targets), определяемые рецептом.

Контроллеры:
1. **ZoneNutrientController** — pH и EC.
2. **ZoneClimateController** — температура и влажность.
3. **ZoneIrrigationController** — расход, рециркуляция, уровень.
4. **ZoneLightController** — свет, интесивность, длительность.
5. **ZoneHealthMonitor** — состояние зоны, алерты, деградации.

Все контроллеры работают через единый Scheduler.

---

# 2. Архитектура Zone Controller Engine

```
 ┌────────────────────────┐
 │ ZoneControllerEngine │
 └───────────┬────────────┘
 │
 ┌───────────────┼────────────────┬───────────────────┬──────────────┐
 ▼ ▼ ▼ ▼ ▼
NutrientCtrl ClimateCtrl IrrigationCtrl LightCtrl ZoneHealthMonitor
```

---

# 3. Общий pipeline работы контроллера

Scheduler каждые 1–5 секунд выполняет:

```
read telemetry
compare with targets
compute deviation
decide correction
publish commands
log events
update zone state
```

---

# 4. ZoneNutrientController (pH + EC)

Контролирует:

- pH коррекцию (acid/base)
- EC коррекцию (nutrients)
- стабилизацию раствора

## 4.1. Алгоритм pH

```
target = zone.targets.ph
current = telemetry.ph

delta = current - target

if |delta| < tolerance:
 do nothing

if delta > 0:
 send command to pump_acid
else:
 send command to pump_base
```

### 4.2. Условия:

- корректировать не чаще чем 1 раз/5 минут
- ограничение дозировки (мг/ч)
- проверка уровня воды
- защита от «колебаний»

## 4.3. Алгоритм EC

```
target = zone.targets.ec
current = telemetry.ec

if current < target - tolerance:
 dose nutrients
```

Условия:

- проверка расхода
- проверка уровня
- не превышать max step

---

# 5. ZoneClimateController (t°, RH, CO₂)

Контролирует:

- температуру воздуха
- влажность
- вентиляцию
- нагрев

## 5.1. Алгоритм температуры

```
if temp_air < target.min:
 turn_on heater
elif temp_air > target.max:
 turn_on fans
```

## 5.2. Алгоритм влажности

```
if humidity > target.max:
 increase ventilation
```

## 5.3. CO₂ (опционально)

Если CO₂ ниже порога → событие.

---

# 6. ZoneIrrigationController (полив и рециркуляция)

Контролирует:

- циклы полива (irrigation cycles)
- рециркуляцию
- расходомер
- уровень бака

## 6.1. Таймовые циклы

```
if now >= next_irrigation_time:
 send irrigation command
 schedule next cycle
```

## 6.2. Контроль по расходу

```
flow = telemetry.flow

if flow < min_flow:
 raise alert "NO_FLOW"
```

## 6.3. Контроль уровня

```
if level < MIN_LEVEL:
 disable all pumps
 raise alert
```

---

# 7. ZoneLightController

Контролирует:

- интенсивность
- длительность
- расписание утро/вечер
- PWM управление

## 7.1. Алгоритм

```
if hour in active_hours:
 turn_on_light(intensity)
else:
 turn_off_light()
```

---

# 8. ZoneHealthMonitor

Анализирует:

- стабильность pH за последние 2 часа
- стабильность EC
- качество климата
- частоту алертов
- состояние узлов
- уровень воды
- расход воды
- Wi‑Fi качество узлов

Выдаёт агрегированный статус:

- OK
- WARNING
- ALARM

---

# 9. События контроллеров (ZoneEvents)

Каждый контроллер создаёт события:

```
PH_CORRECTED
EC_CORRECTED
TEMP_HIGH
TEMP_LOW
HUMIDITY_HIGH
IRRIGATION_STARTED
IRRIGATION_FINISHED
LIGHT_ON
LIGHT_OFF
NO_FLOW
LOW_LEVEL
NODE_OFFLINE
ALARM_ENTER
ALARM_EXIT
```

---

# 10. Интеграция с NodeConfig и MQTT

Контроллеры:

- читают telemetry
- создают команды
- Scheduler → отправляет MQTT команду
- Node → выполняет → даёт command_response
- контроллер → обновляет zone state

---

# 11. API для контроллеров

## 11.1. POST /api/grow-cycles/{growCycle}/pause 
Приостанавливает активный grow-cycle зоны.

## 11.2. POST /api/grow-cycles/{growCycle}/resume 
Возобновляет активный grow-cycle.

## 11.3. POST /api/grow-cycles/{growCycle}/advance-phase 
Сигнал для перехода на следующую фазу рецепта.

---

# 12. Будущее развитие

- ML‑контроллер полива (adaptive irrigation)
- прогнозирование pH/EC
- паттерны климата
- контроллер CO₂ enrichment

---

# Конец файла ZONE_CONTROLLER_FULL.md
