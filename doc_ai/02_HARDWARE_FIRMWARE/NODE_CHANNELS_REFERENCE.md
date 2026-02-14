# NODE_CHANNELS_REFERENCE.md
# Полный справочник каналов узлов 2.0 (ESP32)

Документ описывает типы каналов, ключи, единицы измерения и типичные payload-ы.
Он дополняет `../03_TRANSPORT_MQTT/MQTT_NAMESPACE.md` и `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Общие принципы

Каждый канал описывается:

- полем `channels.key` в БД;
- типом (`SENSOR`, `ACTUATOR`, `VIRTUAL`);
- типом данных (`float`, `int`, `bool`);
- единицами измерения (для сенсоров);
- допустимым диапазоном значений.

Все каналы используют MQTT-паттерн:

```text
hydro/{gh}/{zone}/{node}/{channel}/{message_type}
```

---

## 2. Сенсорные каналы (SENSOR)

### 2.1. pH

- Ключ: `ph_main`
- Тип: `SENSOR`
- Единицы: pH
- Диапазон: 3.0–9.0
- Telemetry payload:

```json
{
 "value": 5.78,
 "metric_type": "PH",
 "ts": 1737355600456
}
```

### 2.2. EC (электропроводность)

- Ключ: `ec_main`
- Тип: `SENSOR`
- Единицы: mS/cm или µS/cm (фиксируется в конфиге зоны)
- Telemetry payload:

```json
{
 "value": 1.6,
 "metric_type": "EC",
 "ts": 1737355600456
}
```

### 2.3. Температура воздуха

- Ключ: `temp_air`
- Тип: `SENSOR`
- Единицы: °C

### 2.4. Температура раствора

- Ключ: `temp_water`
- Тип: `SENSOR`
- Единицы: °C

### 2.5. Влажность воздуха

- Ключ: `humidity_air`
- Тип: `SENSOR`
- Единицы: %

### 2.6. Освещённость

- Ключ: `lux_main`
- Тип: `SENSOR`
- Единицы: lux или PPFD (фиксируется в конфиге).

### 2.7. Уровень воды

- Ключ: `water_level`
- Тип: `SENSOR`
- Единицы: relative (0.0–1.0) или cm (фиксируется в конфиге).

### 2.8. Расход (поток)

- Ключ: `flow_present`
- Тип: `SENSOR`
- Единицы: L/min

### 2.9. Дискретные датчики уровня для 2-баковой системы

Канонические ключи:

- `level_clean_min` — нижний уровень бака чистой воды;
- `level_clean_max` — верхний уровень бака чистой воды;
- `level_solution_min` — нижний уровень бака рабочего раствора;
- `level_solution_max` — верхний уровень бака рабочего раствора.

Тип:
- `SENSOR` (`bool` / `0|1`).

Семантика:
- `1` — датчик сработал;
- `0` — датчик не сработал.

Рекомендуемый telemetry payload:

```json
{
  "metric_type": "WATER_LEVEL_SWITCH",
  "value": 1,
  "ts": 1737355600456
}
```

### 2.10. Датчики субстрата (soil)

Канонические ключи:

- `soil_moisture` — влажность субстрата;
- `soil_temp` — температура субстрата.

Тип:
- `SENSOR` (`float`).

Канонические `metric_type`:
- `SOIL_MOISTURE`;
- `SOIL_TEMP`.

Рекомендуемый telemetry payload:

```json
{
  "metric_type": "SOIL_MOISTURE",
  "value": 41.2,
  "ts": 1737355600456
}
```

### 2.11. Внешние погодные датчики (weather)

Канонические ключи:

- `wind_speed` — скорость ветра;
- `outside_temp` — наружная температура.

Тип:
- `SENSOR` (`float`).

Канонические `metric_type`:
- `WIND_SPEED`;
- `OUTSIDE_TEMP`.

Рекомендуемый telemetry payload:

```json
{
  "metric_type": "OUTSIDE_TEMP",
  "value": 7.8,
  "ts": 1737355600456
}
```

---

## 3. Актуаторные каналы (ACTUATOR)

Актуаторы управляют физическими исполнительными устройствами (насосы, клапаны,
вентиляторы, освещение и т.п.). Все команды к ним приходят через MQTT-топики `.../{channel}/command`,
а факт исполнения подтверждается через `command_response` (см. `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` и
`DEVICE_NODE_PROTOCOL.md`).

### 3.1. Насосы pH

- `pump_acid` — насос дозирования кислоты;
- `pump_base` — насос дозирования щёлочи.

Тип: `ACTUATOR`.

Базовые команды (JSON-payload):

1. Дозирование по объёму:

```json
{
  "cmd_id": "cmd-19292",
  "cmd": "dose",
  "params": {
    "ml": 1.0,
    "ttl_ms": 5000
  }
}
```

2. Прямое управление состоянием (например, сервисные режимы):

```json
{
  "cmd_id": "cmd-19293",
  "cmd": "set_relay",
  "params": {
    "state": true
  }
}
```

### 3.2. Насосы питательного раствора / подачи

- `pump_a` — EC насос NPK;
- `pump_b` — EC насос Calcium;
- `pump_c` — EC насос Magnesium;
- `pump_d` — EC насос Micro;
- `pump_in` — насос/клапан подачи/наполнения;
- при необходимости могут добавляться другие насосы, все они описываются аналогично.

Тип: `ACTUATOR`.

Команды аналогичны:

```json
{
  "cmd_id": "cmd-20101",
  "cmd": "dose",
  "params": {
    "ml": 5.0,
    "ttl_ms": 10000
  }
}
```

или

```json
{
  "cmd_id": "cmd-20102",
  "cmd": "set_relay",
  "params": {
    "state": true
  }
}
```

### 3.3. Другие актуаторы

- `valve_irrigation` — клапан полива;
- `valve_clean_fill` — клапан набора чистой воды;
- `valve_clean_supply` — клапан забора чистой воды из бака;
- `valve_solution_fill` — клапан набора в бак раствора;
- `valve_solution_supply` — клапан забора из бака раствора;
- `pump_main` — главный насос контура подготовки/полива;
- `fan_air` — вентилятор;
- `heater_air` — нагреватель воздуха;
- `white_light` — основное освещение;
- `uv_light` — УФ-лампы.

Тип: `ACTUATOR`.

Пример команды включения/выключения:

```json
{
  "cmd_id": "cmd-30001",
  "cmd": "set_relay",
  "params": {
    "state": true
  }
}
```

Для ШИМ-управления (если канал поддерживает PWM):

```json
{
  "cmd_id": "cmd-30002",
  "cmd": "set_pwm",
  "params": {
    "value": 255
  }
}
```

### 3.4. Правило локального авто-стопа наполнения бака

Для каналов `valve_clean_fill` и `valve_solution_fill` нода обязана:

1. При активном наполнении контролировать датчики `level_clean_max` / `level_solution_max`.
2. При срабатывании соответствующего `*_max` локально закрыть клапан (без ожидания команды backend).
3. Отправить подтверждение в backend:
   - через `command_response` для активной команды;
   - через `event` (канал состояния ноды), если завершение произошло асинхронно.

Это обязательное поведение для безопасного startup workflow в automation-engine.

### 3.5. Канал суммарного тока насосов (SENSOR + связь с актуаторами)

Так как на ноде используется **один датчик тока INA209**, включённый в цепь общего питания насосов,
вводится один сенсорный канал, отражающий суммарный ток по “шине насосов”.

Рекомендуемый ключ канала:

- `pump_bus_current` — суммарный ток по линии питания насосов данной ноды.

Характеристики:

- Тип: `SENSOR`
- Тип данных: `float`
- Единицы: mA
- Источник данных: INA209 по I²C (адрес и параметры шунта задаются в NodeConfig).
- Канал логически привязан ко всей ноде насосов, а не к отдельному насосу.

Типичный payload telemetry для `pump_bus_current`:

```json
{
  "metric_type": "PUMP_CURRENT",
  "value": 220.5,
  "timestamp": 1710005555
}
```

Логика использования:

- при включении любого насосного канала (`pump_acid`, `pump_base`, `pump_a`, `pump_b`, `pump_c`, `pump_d`, `pump_in`)
  ожидается рост тока по `pump_bus_current` выше заданного порога `min_bus_current_on`;
- в NodeConfig могут быть заданы разные ожидаемые окна тока для разных режимов (например,
  “работает только один насос”);
- при отсутствии тока при активной команде насосам, либо при аномально большом токе,
  узел формирует `command_response` со статусом `ERROR` и соответствующим `error_code`,
  а также может публиковать дополнительную диагностическую telemetry.

## 4. Системные каналы и команды (SYSTEM)

### 4.1. Системный канал

Системный канал используется для управления жизненным циклом ноды и не привязан к конкретному физическому каналу.

**Ключ канала:** `system`

**Тип:** SYSTEM (специальный тип для управляющих команд)

**MQTT топик:**
```
hydro/{gh}/{zone}/{node}/system/command
```

**Отличия от канальных команд:**
- Топик не содержит имя канала между `{node}` и `command`
- Команды влияют на поведение всей ноды, а не отдельного канала
- Используется для управления режимами работы сенсорных нод

### 4.2. Команда activate_sensor_mode

**Назначение:** Активация сенсорной ноды перед началом измерений (при старте потока через сенсор).

**Применимость:** pH ноды, EC ноды (узлы с сенсорами, зависящими от потока раствора).

**Payload:**
```json
{
  "cmd": "activate_sensor_mode",
  "params": {
    "stabilization_time_sec": 60
  },
  "cmd_id": "cmd-activate-123",
  "ts": 1710001234,
  "sig": "a1b2c3d4e5f6..."
}
```

**Параметры:**
- `stabilization_time_sec` (integer, обязательно) — время стабилизации сенсора в секундах

**Поведение ноды:**
1. Переход из режима IDLE в режим ACTIVE
2. Запуск таймера стабилизации
3. Начало измерений и публикации телеметрии с расширенными флагами:
   - `flow_active: true`
   - `stable: false` (до истечения stabilization_time_sec)
   - `stabilization_progress_sec` — прогресс стабилизации
   - `corrections_allowed: false` (до истечения stabilization_time_sec)
4. После стабилизации: `stable: true`, `corrections_allowed: true`

**Command Response:**
```json
{
  "cmd_id": "cmd-activate-123",
  "status": "DONE",
  "details": {
    "mode": "ACTIVE",
    "stabilization_time_sec": 60
  },
  "ts": 1710001235000
}
```

### 4.3. Команда deactivate_sensor_mode

**Назначение:** Деактивация сенсорной ноды после завершения цикла (при остановке потока).

**Применимость:** pH ноды, EC ноды.

**Payload:**
```json
{
  "cmd": "deactivate_sensor_mode",
  "params": {},
  "cmd_id": "cmd-deactivate-456",
  "ts": 1710002234,
  "sig": "b2c3d4e5f6a1..."
}
```

**Параметры:** Пустой объект (команда не требует параметров).

**Поведение ноды:**
1. Переход из режима ACTIVE в режим IDLE
2. Остановка измерений
3. Прекращение публикации телеметрии
4. Публикация только heartbeat и LWT (status)

**Command Response:**
```json
{
  "cmd_id": "cmd-deactivate-456",
  "status": "DONE",
  "details": {
    "mode": "IDLE"
  },
  "ts": 1710002235000
}
```

### 4.4. Расширенная телеметрия в ACTIVE режиме

В режиме ACTIVE pH/EC ноды публикуют стандартную телеметрию с дополнительными полями:

**Во время стабилизации:**
```json
{
  "metric_type": "PH",
  "value": 5.86,
  "ts": 1710001250,
  "flow_active": true,
  "stable": false,
  "stabilization_progress_sec": 15,
  "corrections_allowed": false
}
```

**После стабилизации:**
```json
{
  "metric_type": "PH",
  "value": 5.86,
  "ts": 1710001300,
  "flow_active": true,
  "stable": true,
  "stabilization_progress_sec": 60,
  "corrections_allowed": true
}
```

**Новые поля:**
- `flow_active` (boolean) — индикатор наличия потока через сенсор
- `stable` (boolean) — true после истечения stabilization_time_sec
- `stabilization_progress_sec` (integer) — прогресс стабилизации (секунды с момента активации)
- `corrections_allowed` (boolean) — разрешение на коррекции

### 4.5. Применение в Correction Cycle

Системные команды используются automation-engine для управления state machine коррекции:

| Переход состояний | Команда | Применимость |
|------------------|---------|-------------|
| IDLE → TANK_FILLING | `activate_sensor_mode` | pH, EC ноды |
| READY → IDLE | `deactivate_sensor_mode` | pH, EC ноды |
| READY → IRRIGATING | `activate_sensor_mode` | pH, EC ноды (если не активны) |
| IRRIG_RECIRC → IDLE | `deactivate_sensor_mode` | pH, EC ноды |

**См. также:**
- `../06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` — спецификация correction cycle
- `../03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` (секция 7.5) — полная спецификация системных команд

---

## 5. Виртуальные каналы (VIRTUAL)

Примеры:

- `zone_ph_avg` — средний pH по зоне;
- `zone_ec_avg` — средний EC;
- `zone_irrigation_state` — состояние полива зоны.
- `storage_state` — служебный канал событий/состояния 2-бакового контура ноды
  (наполнение, авто-стоп, ошибки датчиков).

Они **не соответствуют физическим пинам**.
Источник виртуального канала зависит от типа:
- агрегированные значения зоны (`zone_*`) формируются Python-сервисом;
- `storage_state` публикуется нодой как event-канал состояния контура.

---

## 6. Правила расширения справочника

1. Любой новый канал должен быть добавлен:
 - сюда;
 - в `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md` (таблица `channels`);
 - при необходимости — в NodeConfig прошивки.
2. Нельзя использовать один и тот же ключ для разных физических значений.
3. Для ИИ-агентов:
 - не придумывать произвольные ключи;
 - согласовывать новые каналы через доменную модель.

Этот справочник должен использоваться **как источник правды**
при разработке прошивки, Python-контроллеров и backend-логики.
