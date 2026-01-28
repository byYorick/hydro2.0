# ZONE_LOGIC_FLOW.md
# Полная логика работы зоны в системе 2.0
# Полный жизненный цикл: данные → контроллеры → команды → события → UI
# ESP32 • MQTT • Python Scheduler • PostgreSQL • Laravel • Vue 3

Документ описывает, **как работает зона 2.0 как целостная система**:
от телеметрии до формирования решений и отображения на UI.

Это главный документ, который связывает:
- рецепты,
- фазы,
- контроллеры,
- узлы,
- команды,
- телеметрию,
- события,
- алерты.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

# 1. Главная концепция

Зона — это логическая единица, содержащая:

- набор узлов (ESP32)
- сенсоры (pH, EC, температура, влажность, уровень воды, свет)
- актуаторы (насосы, клапаны, вентиляторы, освещение)
- рецепт выращивания
- контроллеры (pH, EC, климат, свет, полив)
- события и тревоги

Зона работает по модели:

```
Telemetry → State → Controllers → Commands → Actions → New Telemetry
```

---

# 2. Полный цикл жизни зоны (Zone Loop)

## 2.1. Telemetry Flow

ESP32 узлы отправляют телеметрию в MQTT:

```
hydro/{gh}/{zone}/{node}/{channel}/telemetry
{
 "value": 23.4,
 "ts": 1737355123123
}
```

Python Router получает → валидирует → сохраняет:

1. `telemetry_samples` (история)
2. `telemetry_last` (актуальные данные)

---

## 2.2. Zone State Assembly

Scheduler собирает состояние зоны:

```
ph = telemetry_last["PH"]
ec = telemetry_last["EC"]
temp = telemetry_last["TEMPERATURE"]
humidity = telemetry_last["HUMIDITY"]
water_level = telemetry_last["WATER_LEVEL"]
light = telemetry_last["LIGHT"]
```

Также включает:

- текущая фаза рецепта
- цели фазы (targets)
- активные алерты
- ограничения безопасности (cooldown, max doses)

---

## 2.3. Controllers Loop (каждые 5–10 сек)

Порядок вызова:

1. **Lighting Controller**
2. **Climate Controller**
3. **Irrigation Controller**
4. **pH Controller**
5. **EC Controller**

Почему такой порядок?
- Свет влияет на климат
- Климат влияет на полив
- Полив влияет на pH и EC
- pH/EC корректируем последними

---

## 3. Lighting Controller

### Логика:

```
light_on_period = light_hours
if now in photoperiod → свет ON
else → OFF
```

Команда:
```json
{
  "cmd_id": "cmd-light-001",
  "cmd": "set_relay",
  "params": { "state": true },
  "ts": 1737355112,
  "sig": "a1b2c3d4e5f6..."
}
```

События:
- `LIGHT_ON`
- `LIGHT_OFF`

Алерты:
- `LIGHT_FAILURE`

---

# 4. Climate Controller

Обрабатывает:
- температуру воздуха
- влажность воздуха
- CO₂ (если есть)

### Температура:

```
if temp > target + hysteresis → включить охлаждение
if temp < target - hysteresis → включить нагрев
```

События:
- `CLIMATE_COOLING_ON`
- `CLIMATE_HEATING_ON`

Алерты:
- `TEMPERATURE_HIGH`
- `TEMPERATURE_LOW`

---

# 5. Irrigation Controller

Основан на:

- `irrigation_interval_sec`
- `irrigation_duration_sec`
- water_level
- phase progress

Логика:

```
if (now - last_irrigation > interval) AND water_level_ok:
 pump_irrigation.run(duration)
```

События:
- `IRRIGATION_STARTED`
- `IRRIGATION_FINISHED`

Алерты:
- `WATER_LEVEL_LOW`
- `NO_FLOW`

---

# 6. pH Controller

Формула:

```
if ph > target + 0.1 → acid pump
if ph < target - 0.1 → base pump
```

Дозирование:

```
dose_ml = (abs(ph - target)) * K
```

Событие:
- `PH_CORRECTED`

Алерты:
- `PH_HIGH`
- `PH_LOW`

---

# 7. EC Controller

Если EC < цель:

```
dose_ml = (target - ec) * nutrient_factor
```

События:
- `EC_DOSING`

Алерты:
- `EC_LOW`

---

# 8. Command Engine

Все контроллеры создают команды в таблицу `commands`.

Python Dispatcher каждые 500–2000 мс отправляет их узлам:

```
hydro/{gh}/{zone}/{node}/{channel}/command
{
 "cmd": "dose",
 "params": { "ml": 1.2 },
 "cmd_id": "cmd-abc123",
 "ts": 1737355112,
 "sig": "hmacsha256"
}
```

Ответ узла:
```
/command_response
```

Laravel UI показывает историю команд.

---

# 9. Alerts Engine (в зоне)

Каждый контроллер может вызвать:

- создание алерта,
- обновление алерта,
- автоматическое или ручное закрытие.

UI выводит:
- активные тревоги,
- цветовую индикацию,
- историю алертов.

---

# 10. Events Engine (в зоне)

Каждые действия создают событие.

События отображаются:

- на странице зоны,
- в журнале системы.

---

# 11. Zone Health

Здоровье зоны вычисляется по:

```
active_alerts_count
node_status (online/offline)
average_deviation_from_targets
last_update_time
```

Результат:

- Green = OK
- Yellow = Warning
- Red = Critical

---

# 12. Примеры полного потока работы зоны

---

## 12.1. Сценарий: высокая температура

1. TEMPERATURE = 29°C (target 24°C)
2. Climate Controller:
 - создаёт событие `CLIMATE_OVERHEAT`
 - включает вентилятор и охлаждение
 - создаёт команду включения реле
3. Устанавливается алерт `TEMPERATURE_HIGH`
4. Узел выполняет команду → отправляет командный ответ
5. Vue показывает предупреждение + изменение статуса

---

## 12.2. Сценарий: низкий EC

1. EC = 1.1 (цель 1.5)
2. EC Controller:
 - dose_ml = (1.5-1.1)*3 = 1.2 ml
 - создаёт команду дозирования
 - создаёт событие `EC_DOSING`
3. Узел дозирует → отправляет telemetry обновлённого EC
4. Система автоматически продолжает корректировку

---

## 12.3. Сценарий: полив по расписанию

1. last_irrigation = 20 минут назад
2. interval = 15 мин
3. Irrigation Controller:
 - запускает насос на 8 сек
 - создаёт события start/end
4. Узел работает → telemetry обновляется

---

# 13. Правила для ИИ

ИИ может:

- оптимизировать порядок контроллеров,
- добавлять новые контроллеры,
- вводить адаптивные модели,
- расширять события,
- улучшать реакцию на алерты.

ИИ НЕ может:

- менять формат команд,
- ломать MQTT топики,
- удалять существующие контроллеры,
- менять структуру pipeline.

---

# 14. Чек‑лист Zone Logic Flow

Перед изменением логики зоны нужно проверить:

1. pipeline сохранён? 
2. targets читаются корректно? 
3. контроллеры выполняются в нужном порядке? 
4. дозирование не слишком частое? 
5. команды подписаны? 
6. события создаются корректно? 
7. алерты корректно создаются/закрываются? 
8. UI получает правильные пропсы? 
9. нет перебоев в MQTT? 

---

# Конец файла ZONE_LOGIC_FLOW.md
