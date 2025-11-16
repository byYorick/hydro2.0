# NODE_ARCH_FULL.md
# Полная архитектура узлов ESP32 2.0 (Детальный документ)

Этот документ описывает полноценную архитектуру **узлов ESP32 (Device Nodes)** в системе 2.0:
структура прошивки, модули, каналы, протоколы, безопасность, обновление, обработка команд,
генерация телеметрии, хранение конфигурации, подключение по Wi‑Fi и MQTT.

---

# 1. Цели и принципы архитектуры узлов

Узел ESP32 — это **минималистичное, предсказуемое, детерминированное устройство**, которое:

- не принимает агрономических решений,
- не содержит бизнес-логики,
- не рассчитывает pH/EC/климат,
- является только **источником телеметрии** и **исполнителем команд**.

Backend принимает решения → узлы исполняют.

Принципы:
1. Узел никогда не работает автономно (кроме safety-таймеров).
2. Логика: минимальная, чёткая, несложная.
3. Узел полностью конфигурируется через NodeConfig.
4. Всё общение через MQTT.
5. Узел сам по себе — модуль каналов:
 - SensorChannel
 - ActuatorChannel

---

# 2. Архитектура прошивки узла (Firmware Structure)

Структура модулей:

```
src/
 ├─ main.cpp
 ├─ wifi/
 │ ├─ wifi_manager.cpp
 │ └─ wifi_manager.h
 ├─ mqtt/
 │ ├─ mqtt_client.cpp
 │ ├─ mqtt_client.h
 │ ├─ mqtt_topics.cpp
 │ └─ mqtt_topics.h
 ├─ config/
 │ ├─ node_config.cpp
 │ ├─ node_config.h
 │ ├─ nvs_storage.cpp
 │ └─ nvs_storage.h
 ├─ channels/
 │ ├─ sensor_channel.cpp
 │ ├─ sensor_channel.h
 │ ├─ actuator_channel.cpp
 │ ├─ actuator_channel.h
 │ ├─ ph_sensor.cpp
 │ ├─ ec_sensor.cpp
 │ ├─ sht31.cpp
 │ ├─ ccs811.cpp
 │ ├─ pump.cpp
 │ ├─ fan.cpp
 │ ├─ heater.cpp
 │ └─ relay.cpp
 ├─ telemetry/
 │ ├─ telemetry_manager.cpp
 │ └─ telemetry_manager.h
 ├─ commands/
 │ ├─ command_parser.cpp
 │ └─ command_parser.h
 ├─ utils/
 │ ├─ json.cpp
 │ ├─ json.h
 │ ├─ timers.cpp
 │ ├─ timers.h
 │ └─ safe_mode.cpp
 └─ main_loop.cpp
```

---

# 3. Жизненный цикл узла

1. **Boot**
2. Загрузка NodeConfig из NVS
3. Подключение к Wi-Fi
4. Подключение к MQTT
5. Публикация STATUS ONLINE
6. Подписка на:
 - `config`
 - `command`
7. Запуск циклов:
 - Sensor Polling
 - Telemetry Push
 - Heartbeat
8. Ожидание команд

---

# 4. NodeConfig

NodeConfig полностью формируется на backend.

## 4.1. Формат
```json
{
 "node_id": "nd-ph-1",
 "version": 3,
 "channels": [
 {
 "name": "ph_sensor",
 "type": "SENSOR",
 "metric": "PH",
 "poll_interval_ms": 3000
 },
 {
 "name": "pump_acid",
 "type": "ACTUATOR",
 "actuator_type": "PUMP",
 "safe_limits": {
 "max_duration_ms": 5000,
 "min_off_ms": 3000
 }
 }
 ],
 "wifi": {
 "ssid": "FarmWiFi",
 "pass": "12345678"
 },
 "mqtt": {
 "host": "192.168.1.50",
 "port": 1883,
 "keepalive": 30
 }
}
```

## 4.2. Применение
- сохраняется в NVS,
- подтверждается через `config_response`,
- вызывает перезапуск сенсорных циклов.

---

# 5. Каналы узла (Node Channels)

## 5.1. SensorChannel
Содержит:
- имя
- тип метрики (PH, EC, TEMP_AIR, HUMIDITY…)
- период измерения
- драйвер сенсора
- фильтрацию (усреднение)

### Алгоритм:
```
каждые poll_interval:
 read sensor
 apply smoothing
 post telemetry
```

---

## 5.2. ActuatorChannel
Типы:
- PUMP
- VALVE
- FAN
- LIGHT
- PWM
- HEATER
- RELAY

Поддерживает:
- безопасные лимиты
- сквозной контроль состояния
- command → выполнение → command_response

---

# 6. Telemetry

## 6.1. Формат
```json
{
 "node_id": "nd-ph-1",
 "channel": "ph_sensor",
 "metric_type": "PH",
 "value": 5.82,
 "raw": 1460,
 "ts": 1710001234
}
```

## 6.2. Отправка
Топик:
```
hydro/{gh}/{zone}/{node}/{channel}/telemetry
```

Частота отправки:
- зависит от сенсора,
- регулируется backend,
- всегда QoS=1.

---

# 7. Команды (Command Execution)

## 7.1. Формат
```json
{
 "cmd_id": "cmd-39494",
 "cmd": "run_pump",
 "duration_ms": 2000
}
```

## 7.2. Поддерживаемые команды
- run_pump 
- set_pwm 
- set_relay 
- calibrate 
- reboot 
- measure_now 

## 7.3. Ответ узла
```json
{
 "cmd_id": "cmd-39494",
 "status": "ACK",
 "ts": 1710001234
}
```

---

# 8. Status и LWT

## 8.1. При подключении
```json
{
 "status": "ONLINE",
 "ts": 1710001555
}
```

## 8.2. LWT (offline)
```
payload: "offline"
```

---

# 9. Heartbeat

Период: раз в 15 секунд.

```json
{
 "uptime": 55199,
 "free_heap": 102320,
 "rssi": -55
}
```

---

# 10. Безопасность ноды

Узел должен иметь защиту:

- max duration для насосов
- min off time
- предотвращение двойного запуска
- защита от зависания команд
- защита от дублирующих MQTT сообщений
- watchdog таймер

---

# 11. Обновление прошивки (OTA)

Поддержка OTA (опционально):

- HTTP server (backend)
- Подпись прошивки
- Minimum rollback protection

---

# 12. Wi-Fi архитектура

## Режимы:
- STA (обычный режим)
- Wi‑Fi Reconnect Loop
- Ping watchdog

---

# 13. Внутренние таймеры узла

Таймеры:
- sensor polling timers
- actuator safety timers
- heartbeat timer
- command timeout timer

---

# 14. Потоки узла (очень важно)

```
[MQTT RX] → parse command → execute → publish response
[SENSOR] → measure → push telemetry
[WIFI] → monitor connection
[CONFIG] → receive config → NVS → restart loops
[SAFE] → enforce safe timers
```

---

# 15. Будущие расширения

- Каналы для CO₂
- PWM-регулирование света
- Поддержка RS485 модулей
- Zero‑conf добавление нод
- Поддержка ESP‑Now fallback

---

# Конец файла NODE_ARCH_FULL.md
