# MQTT_SPEC_FULL.md
# Полная MQTT спецификация 2.0 (Топики, Payload, Протоколы, Правила)

Этот документ описывает полный протокол MQTT для системы 2.0 управления теплицами.
Здесь указаны форматы топиков, JSON‑payload, правила QoS, LWT, NodeConfig, Telemetry,
Command, Responses и системные события.

---

# 1. Общая концепция MQTT 2.0

MQTT используется как **единая шина данных** между backend и ESP‑узлами (нодами).
Принципы:

- Backend — главный мозг. Узлы — исполнители.
- Модель: pub/sub, JSON‑payload.
- Все топики строго стандартизированы.
- Узлы используют только:
 - Telemetry → НАВЕРХ
 - Status/LWT → НАВЕРХ
 - Config/Command → ВНИЗ
- Backend слушает всё.
- Узлы подписываются только на свои config/command.

---

# 2. Структура MQTT-топиков 2.0

Формат топиков:

```
hydro/{gh}/{zone}/{node}/{channel}/{type}
```

Где:
- `gh` — UID теплицы (`greenhouses.uid`), например `gh-1`.
- `zone` — идентификатор зоны (обычно `zones.id` или `zones.uid`), например `zn-3`.
- `node` — строковый UID узла (`nodes.uid`), совпадает с `node_uid` из `NODE_CHANNELS_REFERENCE.md`.
- `channel` — имя канала (например `ph_sensor` или `pump_acid`).
- `type` — тип сообщения:

Типы:
- **telemetry**
- **command**
- **command_response**
- **config**
- **config_response**
- **status**
- **lwt**

Пример:
```
hydro/gh-1/zn-3/nd-ph-1/ph_sensor/telemetry
```
---

# 3. Telemetry (узлы → backend)

## 3.1. Топик
```
hydro/{gh}/{zone}/{node}/{channel}/telemetry
```

## 3.2. Пример JSON
```json
{
 "node_id": "nd-ph-1",
 "channel": "ph_sensor",
 "metric_type": "PH",
 "value": 5.86,
 "raw": 1465,
 "timestamp": 1710001234
}
```

> Примечание: в поле `node_id` передаётся строковый UID узла (`nodes.uid`), совпадающий с сегментом `{node}` в топике и `node_uid` из `NODE_CHANNELS_REFERENCE.md`.

## 3.3. Requirements
- QoS = 1
- Retain = false
- Backend сохраняет TelemetrySample
- Backend обновляет last_value в Redis
- Backend может триггерить Alerts

---

# 4. Status & LWT (жизненный цикл узла)

## 4.1. LWT

Устанавливается при connect:

```
hydro/{gh}/{zone}/{node}/lwt
payload: "offline"
```

## 4.2. Online status

**ОБЯЗАТЕЛЬНО:** При успешном подключении к MQTT брокеру (событие `MQTT_EVENT_CONNECTED`) узел **ОБЯЗАН** немедленно опубликовать status топик.

**Топик:**
```
hydro/{gh}/{zone}/{node}/status
```

**Payload:**
```json
{
 "status": "ONLINE",
 "ts": 1710001555
}
```

**Требования:**
- QoS = 1
- Retain = true
- Публикация выполняется **сразу после** успешного подключения, до подписки на config/command топики
- Поле `ts` содержит Unix timestamp в секундах (время публикации)
- Backend использует этот статус для обновления `nodes.status` и `nodes.last_seen_at`

**Последовательность действий при подключении:**
1. Установка LWT (Last Will and Testament) — выполняется при инициализации MQTT клиента
2. Подключение к брокеру
3. **Публикация status с "ONLINE"** ← ОБЯЗАТЕЛЬНО
4. Подписка на `hydro/{gh}/{zone}/{node}/config`
5. Подписка на `hydro/{gh}/{zone}/{node}/+/command` (wildcard для всех каналов)
6. Вызов connection callback (если зарегистрирован)

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (mqtt_manager.c, строки 370-374)

## 4.3. Offline
Отправляется брокером автоматически (LWT):

```
payload: "offline"
```

## 4.4. Backend действия:
- помечает ноду OFFLINE
- создаёт Alert
- Zone может перейти в ALARM

---

# 5. NodeConfig (backend → узлы)

## 5.1. Топик
```
hydro/{gh}/{zone}/{node}/config
```

## 5.2. Пример полного NodeConfig:
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
 "ssid": "HydroFarm",
 "pass": "12345678"
 },
 "mqtt": {
 "host": "192.168.1.10",
 "port": 1883,
 "keepalive": 30
 }
}
```

## 5.3. Requirements
- QoS = 1
- Retain = false
- Узел сохраняет конфиг в NVS
- Узел отправляет config_response

---

# 6. Config Response (узлы → backend)

## 6.1. Топик
```
hydro/{gh}/{zone}/{node}/config_response
```

## 6.2. Пример JSON
```json
{
 "status": "OK",
 "node_id": "nd-ph-1",
 "applied": true,
 "timestamp": 1710002222
}
```

Если ошибка:
```json
{
 "status": "ERROR",
 "error": "Invalid channel ph_sensor",
 "timestamp": 1710002223
}
```

---

# 7. Commands (backend → узлы)

## 7.1. Топик
```
hydro/{gh}/{zone}/{node}/{channel}/command
```

## 7.2. Пример команд

### 1) Пуск насоса
```json
{
 "cmd": "run_pump",
 "duration_ms": 2500,
 "cmd_id": "cmd-591"
}
```

### 2) Включение реле
```json
{
 "cmd": "set_relay",
 "state": true,
 "cmd_id": "cmd-592"
}
```

### 3) PWM
```json
{
 "cmd": "set_pwm",
 "value": 128,
 "cmd_id": "cmd-593"
}
```

### 4) Калибровка
```json
{
 "cmd": "calibrate",
 "type": "PH_7",
 "cmd_id": "cmd-594"
}
```

---

# 8. Command Response (узлы → backend)

## 8.1. Топик
```
hydro/{gh}/{zone}/{node}/{channel}/command_response
```

## 8.2. Общие требования

Каждая команда, отправленная в `.../{channel}/command`, **обязана** породить хотя бы один
ответ `command_response` от узла:

- даже если команда была отвергнута по валидации;
- даже если действие выполнить не удалось по железу (ошибка насоса, проблема с питанием);
- даже если узел находился в SAFE_MODE.

Backend никогда не остаётся “в неизвестности”: по `cmd_id` он либо получает `ACK`,
либо `ERROR`/`TIMEOUT` и может принять управленческое решение.

## 8.3. Базовый payload

```json
{
  "cmd_id": "cmd-591",
  "status": "ACK",
  "ts": 1710003333
}
```

Статусы:
- `ACK` — команда принята и выполнена без критичных ошибок;
- `ERROR` — команда не выполнена или выполнена с ошибкой;
- `TIMEOUT` — узел сам зафиксировал превышение внутренних таймаутов.

## 8.4. Расширенный payload для ошибок

Для ошибок допускается расширенный формат:

```json
{
  "cmd_id": "cmd-591",
  "status": "ERROR",
  "ts": 1710003399,
  "error_code": "current_not_detected",
  "error_message": "No current on pump_in channel after switching on",
  "details": {
    "channel": "pump_in",
    "requested_state": 1,
    "measured_current_ma": 5,
    "expected_min_current_ma": 80
  }
}
```

`error_code` — машинночитаемый код для backend-логики,  
`error_message` — человекочитаемое пояснение,  
`details` — любые доп. поля (например, измеренный ток, номер повторной попытки и т.п.).

## 8.5. Особые правила для насосов (pump\_*)

Для всех команд, связанных с насосами (`pump_acid`, `pump_base`, `pump_nutrient`,
`pump_in` и другие актуаторные каналы насосов):

1. Узел **обязан** после включения насоса:
   - подождать минимальное время стабилизации (настраиваемое, например 100–300 ms),
   - считать ток через соответствующий датчик INA209 по I²C,
   - сравнить его с порогами в NodeConfig.

2. Если ток ниже минимального порога или выходит за допустимый диапазон:
   - узел отправляет `command_response` со статусом `ERROR` и `error_code="current_not_detected"` или другим подходящим кодом;
   - дополнительно может отправить диагностическую telemetry по каналу тока.

3. Если ток в норме:
   - узел отправляет `command_response` со статусом `ACK`,
   - при необходимости публикует telemetry с измеренным током (см. раздел Telemetry для каналов тока).

Таким образом, backend всегда знает не только то, что команда на включение насоса была отправлена,
но и то, что **реле реально замкнулось и насос потребляет ток** в ожидаемых пределах.

---
# 9. Дополнительные системные топики

## 9.1. Node Hello (регистрация узла)
```
hydro/node_hello
hydro/{gh}/{zone}/{node}/node_hello
```

**Топик:** 
- `hydro/node_hello` — для начальной регистрации, когда узел не знает gh/zone/node
- `hydro/{gh}/{zone}/{node}/node_hello` — если узел уже знает свои параметры из provisioning

**Payload:**
```json
{
  "message_type": "node_hello",
  "hardware_id": "esp32-ABCD1234",
  "node_type": "ph",
  "fw_version": "2.0.1",
  "hardware_revision": "v1.0",
  "capabilities": ["ph", "temperature"],
  "provisioning_meta": {
    "greenhouse_token": "gh-123",
    "zone_id": null,
    "node_name": null
  }
}
```

**Requirements:**
- QoS = 1
- Retain = false
- Backend обрабатывает и создаёт/обновляет `DeviceNode` с `logical_node_id` (uid)

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (обработчик `handle_node_hello` в history-logger, интеграция с Laravel API)

---

## 9.2. Heartbeat узла
```
hydro/{gh}/{zone}/{node}/heartbeat
```

**Payload:**
```json
{
  "uptime": 35555,
  "free_heap": 102000,
  "rssi": -62
}
```

**Альтернативные имена полей:**
- `free_heap` или `free_heap_bytes` — свободная память в байтах
- `uptime` — время работы узла в секундах
- `rssi` — сила сигнала Wi-Fi в dBm

**Requirements:**
- QoS = 1 (обновлено: было 0, теперь 1 для надёжности)
- Retain = false
- Backend обновляет поля `last_heartbeat_at`, `uptime_seconds`, `free_heap_bytes`, `rssi` в таблице `nodes`
- Обновляет также `last_seen_at` при получении heartbeat

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (обработчик `handle_heartbeat` в history-logger, поля в БД добавлены)

---

## 9.3. Debug (опционально)
```
hydro/{node}/debug
```

---

# 10. Правила QoS и Retain

| Тип | QoS | Retain |
|-----|-----|---------|
| telemetry | 1 | false |
| command | 1 | false |
| command_response | 1 | false |
| config | 1 | false |
| config_response | 1 | false |
| status | 1 | true |
| lwt | 1 | true |
| node_hello | 1 | false |
| heartbeat | 1 | false |

---

# 11. Правила именования

### Node ID
```
nd-{type}-{nn}
```
Примеры:
- `nd-ph-1`
- `nd-ec-2`

### Channel ID
```
ph_sensor
ec_sensor
pump_acid
pump_base
fan_A
heater_1
```

---

# 12. Потоки данных (Data Flows)

## Telemetry → Backend
```
node → mqtt → listener → router → handler → TelemetryService
```

## Command → Node
```
controller → CommandService → NodeCoordinator → mqtt → node
```

## Config → Node
```
backend → NodeConfigService → mqtt-bridge → mqtt → node → config_response
```

**Автоматическая синхронизация:**
- При изменении узла или каналов автоматически генерируется и публикуется новый NodeConfig через Event/Listener систему
- Публикация выполняется через `mqtt-bridge` сервис

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (NodeConfigService, автоматическая синхронизация через Events)

## Status → Backend
```
node → status/lwt → history-logger → AlertService
```

## Node Hello → Backend
```
node → node_hello → history-logger → Laravel API → NodeRegistryService
```

## Heartbeat → Backend
```
node → heartbeat → history-logger → nodes table (uptime, free_heap, rssi)
```

---

# 13. Требования к узлам (Node Firmware)

## 13.1. Подписки (обязательные)

Узел **ОБЯЗАН** подписаться на:
- `hydro/{gh}/{zone}/{node}/config` — для получения конфигурации
- `hydro/{gh}/{zone}/{node}/+/command` — для получения команд по всем каналам (wildcard)

## 13.2. Публикации (обязательные)

Узел **ОБЯЗАН** публиковать:

### При подключении к MQTT брокеру:
- **status** (`hydro/{gh}/{zone}/{node}/status`) — **ОБЯЗАТЕЛЬНО** сразу после `MQTT_EVENT_CONNECTED` (см. раздел 4.2)

### Регулярно:
- **telemetry** (`hydro/{gh}/{zone}/{node}/{channel}/telemetry`) — по расписанию из NodeConfig
- **heartbeat** (`hydro/{gh}/{zone}/{node}/heartbeat`) — периодически (например, каждые 30 секунд)

### По запросу:
- **command_response** (`hydro/{gh}/{zone}/{node}/{channel}/command_response`) — на каждую команду
- **config_response** (`hydro/{gh}/{zone}/{node}/config_response`) — при получении config

### При регистрации:
- **node_hello** (`hydro/node_hello` или `hydro/{gh}/{zone}/{node}/node_hello`) — при первой регистрации

### При инициализации:
- **lwt** (`hydro/{gh}/{zone}/{node}/lwt`) — настраивается при инициализации MQTT клиента

## 13.3. Общие требования

- JSON строго формализован согласно спецификации
- Ошибки всегда возвращаются через command_response или config_response
- Все публикации должны соответствовать форматам из разделов 3-9
- QoS и Retain должны соответствовать таблице из раздела 10

---

# 14. Требования к backend

- полный MQTT router
- QoS = 1
- хранение команд
- таймаут команд (если нет ACK)
- NodeConfig пересылать при изменениях (✅ реализовано через автоматическую синхронизацию)
- обработка node_hello для регистрации узлов (✅ реализовано в history-logger)
- обработка heartbeat для мониторинга узлов (✅ реализовано в history-logger)
- алерты при offline / telemetry out of range

---

# 15. Будущее расширение (2.0)

- групповые команды
- топики для AI-моделей
- нормализация telemetry через schema registry
- агрономические триггеры MQTT→backend
- автоматические профили нод

---

# Конец файла
