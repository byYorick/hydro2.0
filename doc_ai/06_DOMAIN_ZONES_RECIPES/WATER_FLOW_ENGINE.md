# WATER_FLOW_ENGINE.md
# Полная логика водного цикла и контроля потока в системе 2.0
# Насосы • Клапаны • Расход • Уровень воды • Подача • Рециркуляция • Защита

Этот документ описывает всю логику управления водой в системе 2.0:
от датчиков уровня и расхода до алгоритмов насосов, клапанов и защиты.

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
{"cmd": "run", "params": {"sec": 8}}
```

## 3.2. VALVE (распределитель потоков)

Команды:
- `open`
- `close`
- `select_line: X`

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

Может быть вызван вручную:

```
{"cmd": "fill", "params": {"target_level": 0.9}}
```

Узел:

- включает клапан подачи 
- включает насос 
- контролирует уровень 
- останавливается при достижении уровня 

---

# 10. Режим слива (Drain Mode)

```
{"cmd": "drain", "params": {"target_level": 0.1}}
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
cmd = run, stop, fill, drain
params = {sec, target_level}
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

# 17. Python Scheduler

Use cases:

- start irrigation
- validate flow
- compute volume
- generate events
- create alerts
- block unsafe actions

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

# Конец файла WATER_FLOW_ENGINE.md
