# ZONE_CONTROLLERS_AI_GUIDE.md
# Полная спецификация контроллеров зон (pH, EC, климат, полив, свет)
# Инструкция для ИИ-агентов и Python-разработчиков

Этот документ описывает математику, алгоритмы, правила, ограничения 
и взаимодействие всех контроллеров зоны 2.0. 
Контроллеры работают в Python-сервисе (main_scheduler.py).

---

# 1. Общая логика работы контроллеров

Контроллеры:
- работают каждые N секунд (обычно 5–10 сек);
- используют данные **только** из `telemetry_last`;
- сравнивают фактические значения с целевыми из `zone_recipe_instances`;
- принимают решение о дозировании, включении или выключении устройств;
- создают команду через `create_command()`;
- **не** публикуют MQTT напрямую (это делает middleware).

Основные контроллеры:
1. pH Controller 
2. EC Controller 
3. Climate Controller 
4. Irrigation Controller 
5. Lighting Controller 

---

# 2. Общие функции для всех контроллеров

## 2.1. Фильтрация шумов

Любой контроллер должен использовать **скользящее усреднение**:

```
avg = SMA(last N values)
где N = 3…5
```

## 2.2. Гистерезис

Чтобы устройства не «щелкали»:

```
ON, если значение > target + hysteresis
OFF, если значение < target - hysteresis
```

Стандартный гистерезис:
- температура: 0.5–1°C 
- влажность: 3–5% 
- EC: 0.05–0.1 mS/cm 
- pH: 0.05–0.1

## 2.3. Минимальное время между действиями

Каждый контроллер должен проверять:

```
last_action_time + cooldown_sec < now
```

Значения:
- pH: 45–120 сек
- EC: 60–300 сек
- Climate: 5–10 сек
- Irrigation: 300–1800 сек
- Lighting: 60 сек

---

# 3. pH Controller

## 3.1. Цели из рецепта

```
target_ph = recipe.phase.targets["ph"]
```

## 3.2. Логика коррекции

Если `current_ph > target + 0.1` → дозируем кислоту 
Если `current_ph < target - 0.1` → дозируем щёлочь

### Команда:

```python
create_command(
 zone_id=zone.id,
 node_id=node_ph_doser,
 channel="pump_acid" or "pump_base",
 cmd="dose",
 params={"ml": dose_ml}
)
```

## 3.3. Дозирование

Формула дозирования:

```
dose_ml = (current_ph - target) * K
```

`K` — коэффициент (0.2–0.5)

ИИ-агент может предлагать умные PID‑расширения, 
но должен сохранять базовую совместимость.

---

# 4. EC Controller

## 4.1. Цели из рецепта

```
target_ec = recipe.phase.targets["ec"]
```

## 4.2. Алгоритм

Если EC < target - 0.05:

```
dose_ml = (target - current_ec) * nutrient_strength_ml_per_ms
```

Создаём команду:

```python
create_command(
 zone.id,
 node_nutrient,
 "pump_nutrient",
 "dose",
 {"ml": dose_ml}
)
```

### Ограничения:

- не дозировать чаще 1 раза в 5–10 минут;
- не превышать max ml за один цикл;
- выдавать предупреждение при EC > target + 0.2.

---

# 5. Climate Controller

Климат делится на 3 параметра:

1. Температура воздуха
2. Влажность воздуха
3. CO₂ (опционально)

---

## 5.1. Температура воздуха

```
if temp_air > target_temp + 0.5:
 включаем fan_air и cooler
elif temp_air < target_temp - 0.5:
 включаем heater_air
else:
 выключаем всё
```

Команды:

```
cmd="on" / "off"
```

---

## 5.2. Влажность воздуха

```
if humidity > target + 5:
 включаем fan_air
```

||

```
if humidity < target - 5:
 включаем увлажнитель (если есть)
```

---

## 5.3. CO₂ (опционально)

```
if co2 < target - 100:
 open co2_valve for 2–5 sec
```

---

# 6. Irrigation Controller (полив)

Полив — один из самых сложных контроллеров.

Основан на:

- фазе рецепта,
- интервале полива,
- объёме полива,
- данных о воде.

## 6.1. Логика интервалов

Задаётся в рецепте:

```
irrigation_interval_sec (например: 600)
irrigation_duration_sec (например: 10)
```

Условия полива:

1. Время → last_irrigation + interval 
2. Достаточный уровень воды 
3. Нет активных ошибок (ALERT water_level_low)

## 6.2. Команда полива

```python
create_command(
 zone.id,
 node_irrig,
 "pump_irrigation",
 "run",
 {"duration_ms": irrigation_duration_sec * 1000}
)
```

---

# 7. Lighting Controller

Основан на фазе и расписании:

```
photoperiod_hours = recipe.phase.targets["light_hours"]
```

## 7.1. Логика

```
time_now in [light_start, light_start + photoperiod]
 => включить свет
иначе
 => выключить
```

### Команда:

```
cmd="on" / "off"
```

---

# 8. Общий жизненный цикл контроллера

```python
for zone in zones:
 run_ph(zone)
 run_ec(zone)
 run_climate(zone)
 run_irrigation(zone)
 run_lighting(zone)
```

---

# 9. Система алармов (Alerts)

Контроллеры могут инициировать:

- PH_HIGH
- PH_LOW
- EC_LOW
- TEMP_HIGH
- TEMP_LOW
- HUMIDITY_HIGH/LOW
- WATER_LOW
- LIGHT_FAILURE
- FLOW_ERROR

ИИ-агент при добавлении новых алертов должен:

1. Добавить их в spec.
2. Добавить обработку в Python.
3. Добавить отображение в UI.
4. Добавить Eloquent-модель Alert.

---

# 10. Совместимость и ограничения ИИ

ИИ-агент **может**:

- улучшать контроллеры,
- добавлять PID,
- делать адаптивные алгоритмы,
- использовать машинное обучение в analyzer.py.

ИИ-агент **не может**:

- менять структуру команд (`cmd, params`),
- ломать существующие каналы,
- менять жизненный цикл scheduler.

---

# 11. Чек-лист перед изменениями

1. Все контроллеры должны основываться на `telemetry_last`.
2. Нельзя создавать команды слишком часто.
3. Все команды должны иметь cooldown.
4. Нельзя превышать max ml/сек и max дозы.
5. EC/pH корректируются мягко.
6. Свет — только через расписание.
7. Полив — только через интервал.
8. В климате — обязательный гистерезис.
9. Алгоритм не должен создавать бесконечных циклов.
10. Любые новые параметры должны быть добавлены в:
 - Python
 - БД
 - Laravel UI

---

# Конец файла ZONE_CONTROLLERS_AI_GUIDE.md
