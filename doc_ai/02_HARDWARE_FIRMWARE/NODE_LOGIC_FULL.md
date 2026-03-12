# NODE_LOGIC_FULL.md
# Полная логика работы узлов ESP32 2.0 (детальный документ)

Этот документ описывает детальную **операционную логику узлов ESP32** в архитектуре 2.0.
Он фиксирует правила поведения, внутренние процессы, машинные состояния, обработку команд,
алгоритмы сенсоров, диагностику, fail‑safe и протоколы взаимодействия.

---

# 1. Главная концепция логики узла

Узел — это **детерминированная машина каналов**, которая состоит из:

- SensorChannels (производят данные)
- ActuatorChannels (выполняют действия)
- MQTT-клиента
- Wi‑Fi менеджера
- Конфигуратора (NodeConfig)
- NVS-хранилища
- Главного цикла (main loop)
- Системы безопасности (SafeMode)

Узел **не принимает решений**:
- не рассчитывает pH/EC дозировки,
- не оценивает климат,
- не управляет рецептами.

Вся логика → только на backend.

---

# 2. Машина состояний ноды

```
BOOT
 ↓
LOAD_CONFIG
 ↓
WIFI_CONNECTING → WIFI_CONNECTED
 ↓
MQTT_CONNECTING → MQTT_CONNECTED
 ↓
RUNNING
 ├─ SENSOR_LOOP
 ├─ ACTUATOR_EXECUTION
 ├─ MQTT_RX_LOOP
 ├─ HEARTBEAT
 ├─ SAFE_MODE
 └─ CONFIG_APPLY
```

Если Wi‑Fi потерян:
```
WIFI_RECONNECT_LOOP
```

Если MQTT потерян:
```
MQTT_RECONNECT_LOOP
```

Если критическая ошибка:
```
SAFE_MODE → ограниченный режим
```

---

# 3. Логические модули

## 3.1. Wi-Fi Manager
Функции:

- загрузка SSID/PASS из NodeConfig
- попытка подключения с экспоненциальной задержкой
- автоматический reconnect
- мониторинг RSSI
- публикация heartbeat с RSSI

События:

- on_wifi_connected
- on_wifi_disconnected
- on_wifi_timeout

---

## 3.2. MQTT Manager

Обязанности:

- инициализация MQTT клиента
- подписка на:
 - config
 - command
- публикация:
 - telemetry
 - status
 - command_response
 - config_response
 - heartbeat
- авто‑reconnect

Триггеры:

- on_mqtt_connected → publish ONLINE
- broker publishes LWT → backend фиксирует offline

---

## 3.3. Config Manager (NodeConfig)

Логика:

1. Получить config JSON.
2. Проверить версию.
3. Проверить валидность каналов.
4. Сохранить в NVS.
5. Перезапустить sensor loops.
6. Ответить config_response.

В случае ошибки:
```json
{
 "status": "ERROR",
 "error": "Invalid channel name"
}
```

---

## 3.4. Sensor Engine

Данные хранятся в структуре:

```
SensorChannel {
 name,
 metric,
 poll_interval_ms,
 last_value,
 driver,
 filter_state
}
```

Алгоритм:
```
каждый poll_interval:
 raw = driver.read_raw()
 val = filter(raw)
 last_value = val
 publish telemetry
```

Поддерживаются:

- PH
- EC
- TEMP_AIR
- TEMP_WATER
- HUMIDITY
- LUX
- CO2 (опционально)
- WATER_LEVEL
- FLOW_RATE

---

## 3.5. Actuator Engine

Для каждого канала:

```
ActuatorChannel {
 name,
 type,
 safe_limits,
 state,
 cooldown_timer,
 active_timer
}
```

При получении команды:

1. Проверить safe_limits:
 - max_duration
 - min_off
 - duty restrictions

2. Выполнить действие:
 - включить реле
 - запустить насос
 - установить PWM
 - выполнить калибровку

3. Запустить active_timer.

4. Отправить command_response.

---

# 4. Логика обработки команд

## 4.1. Формат
```json
{
 "cmd_id": "cmd-19292",
 "cmd": "run_pump",
 "duration_ms": 2000
}
```

## 4.2. Алгоритм выполнения
```
on_command_received:
 parse JSON
 validate channel
 validate safe_limits
 execute
 publish command_response
```

## 4.2.1. Специальный случай: команды к насосам с проверкой суммарного тока (INA209)

Для всех команд, затрагивающих насосы (`pump_acid`, `pump_base`, `pump_nutrient`, `pump_in` и др.),
алгоритм `on_command_received` расширяется проверкой по **суммарному току** через INA209,
включённому в разрыв общего плюса питания насосов.

Рекомендуется по возможности управлять насосами так, чтобы одновременно был активен
только один насос на ноде — это упрощает диагностику и настройку порогов.

Пример алгоритма:

```
on_command_received for pump_channel:
  parse JSON
  validate channel (must be pump_*)
  validate safe_limits (duration, cooldown, max_duty)

  // включаем нужный насос
  switch MOSFET (через оптопару) для данного pump_channel

  wait stabilization_delay_ms (из NodeConfig, например 100–300 ms)

  // измеряем суммарный ток по шине насосов
  bus_current_ma = ina209_read_bus_current()

  if bus_current_ma < min_bus_current_on:
      publish command_response {
        cmd_id,
        status = "ERROR",
        error_code = "current_not_detected",
        details = { channel, bus_current_ma, min_bus_current_on }
      }
      optionally: publish telemetry on channel "pump_bus_current"
      register error counter for this node/pump_group
      if repeated errors exceed threshold:
          enter local SAFE_MODE for pump node (disable all pumps)
  else if bus_current_ma > max_bus_current_on:
      publish command_response {
        cmd_id,
        status = "ERROR",
        error_code = "overcurrent",
        details = { channel, bus_current_ma, max_bus_current_on }
      }
      switch_off_all_pumps()
      optionally: publish telemetry on "pump_bus_current"
      enter local SAFE_MODE for pump node
  else:
      publish command_response {
        cmd_id,
        status = "ACK",
        details = { channel, bus_current_ma }
      }
      optionally: publish telemetry on "pump_bus_current"
```

Значения `min_bus_current_on` и `max_bus_current_on` хранятся в NodeConfig.  
При необходимости могут настраиваться разные профили порогов для разных режимов,
но базовый сценарий — “включён ровно один насос, суммарный ток в ожидаемом окне”.

Таким образом, узел подтверждает не только факт приёма команды,
но и реальное включение насосов по показаниям суммарного тока.
## 4.3. Ответы
### Успех
```json
{
 "cmd_id": "cmd-19292",
 "status": "ACK",
 "ts": 1710012345
}
```

### Ошибка
```json
{
 "cmd_id": "cmd-19292",
 "status": "ERROR",
 "error": "cooldown_active"
}
```

---

# 5. Telemetry Logic

## 5.1. Стандартный JSON
```json
{
 "node_id": "nd-ph-1",
 "channel": "ph_sensor",
 "metric_type": "PH",
 "value": 5.82,
 "raw": 1463,
 "ts": 1710012567
}
```

## 5.2. Правила:
- отправка с QoS=1
- interval определяет backend
- raw значение сохраняется для диагностики
- timestamp обязан быть UNIX time или millis()

---

# 6. Heartbeat Logic

Каждые 15 секунд:

```json
{
 "uptime": 58222,
 "heap": 102300,
 "rssi": -59,
 "ts": 1710012711
}
```

Используется backend для:

- диагностики
- оценки качества Wi‑Fi
- обнаружения зависаний
- анализа потребления памяти

---

# 7. NVS Storage Logic

В NVS хранятся:

- NodeConfig
- Wi-Fi параметры
- MQTT параметры
- Calibration data
- Device metadata (node_type, hw_version)

При повреждении конфигурации:
- fallback в SAFE MODE
- запросить config с backend
- отправить config_response(ERROR)

---

# 8. Safety Logic (SafeMode)

Узел переходит в SAFE_MODE если:

- pump работает дольше max_duration_ms
- превышен duty cycle
- повреждён NodeConfig
- сенсор возвращает абсурдные значения
- завис MQTT
- перезагрузки чаще X раз

В SAFE_MODE:

- актуаторы отключены
- telemetry работает
- heartbeat работает
- узел просит новый config

---

# 9. OTA Logic (опционально)

Алгоритм:

1. Узел получает URL прошивки от backend.
2. Скачивает блоками.
3. Проверяет подпись.
4. Прошивает второй раздел.
5. Перезагружается.
6. Шлёт "OTA_OK".

При ошибке:
- откатывается
- шлёт "OTA_FAIL".

---

# 10. Full Node Data Flow

```
[Sensor Channels]
 ↓ telemetry
[MQTT Publish] → backend

[MQTT Subscribe] ← config / command
 ↓
Command Parser → Actuator Channel → command_response

[WiFi Manager] → RSSI → heartbeat

[SafeMode] protects all
```

---

# 11. Debug режим (опционально)

Топик:
```
hydro/{node}/debug
```

Публикует:
- stack trace
- free heap spikes
- reboot causes
- driver errors

---

# 12. Жизненный цикл обновлений NodeConfig

Цепочка:

```
backend → build NodeConfig
backend → publish config
node → validate config
node → save in NVS
node → restart sensor loops
node → config_response(OK)
```

Если ошибка:
```
node → config_response(ERROR)
```

---

# 13. Мини‑алгоритмы для сенсоров

## PH Sensor
- стабилизация 500–1000 мс
- медианный фильтр (3 значения)
- температурная компенсация (если t° есть)
- raw + calibrated

## EC Sensor
- компенсация температуры
- проверка диапазона 0.1–5.0 mS/cm
- защита от шумов (low-pass)

## SHT3x
- t°/RH в паре
- I2C recovery при ошибках

## CCS811
- warm-up режим
- baseline calibration

---

# 14. Мини‑алгоритмы для исполнительных устройств

## Pumps
- ограничение по max_duration
- минимальная пауза между запусками
- защита от дребезга команд
- auto-off таймер

## Fans
- управление PWM
- пределы 0–255

## Heater
- ручной контроль с backend
- защита по duty 40–60%

---

# 15. Расширения будущих версий

- RS485 модули
- CAN bus
- ESP‑Now backup link
- Multi-channel ADC board
- Smart power modules
- Self-test mode

---

# Конец файла NODE_LOGIC_FULL.md
