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
 - Config_report → НАВЕРХ
 - Command → ВНИЗ
- Backend слушает всё.
- Узлы подписываются только на свои command (config — опционально, legacy).

---

# 2. Структура MQTT-топиков 2.0

Формат топиков:

```
hydro/{gh}/{zone}/{node}/{channel}/{type}
```

Для системных сообщений без канала используется сокращённый формат:
```
hydro/{gh}/{zone}/{node}/{type}
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
- **config_report**
- **config** (legacy)
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
 "metric_type": "PH",
 "value": 5.86,
 "ts": 1710001234
}
```

**Обязательные поля:**
- `metric_type` (string, UPPERCASE) — тип метрики: `PH`, `EC`, `TEMPERATURE`, `HUMIDITY`, `CO2`, `LIGHT_INTENSITY`, `WATER_LEVEL`, `FLOW_RATE`, `PUMP_CURRENT`
- `value` (number) — значение метрики
- `ts` (integer) — UTC timestamp в секундах (Unix timestamp)

**Опциональные поля:**
- `unit` (string) — единица измерения (например, "pH", "°C", "%")
- `raw` (integer) — сырое значение сенсора
- `stub` (boolean) — флаг, указывающий на симулированное значение
- `stable` (boolean) — флаг, указывающий на стабильность значения

> **Важно:** Поля `node_id` и `channel` **не включаются** в JSON payload, так как они уже присутствуют в структуре MQTT топика (`hydro/{gh}/{zone}/{node}/{channel}/telemetry`). Формат соответствует эталону node-sim, который успешно проходит E2E тесты.

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
- Публикация выполняется **сразу после** успешного подключения, до подписки на command топики
- Поле `ts` содержит Unix timestamp в секундах (время публикации)
- Backend использует этот статус для обновления `nodes.status` и `nodes.last_seen_at`

**Последовательность действий при подключении:**
1. Установка LWT (Last Will and Testament) — выполняется при инициализации MQTT клиента
2. Подключение к брокеру
3. **Публикация status с "ONLINE"** ← ОБЯЗАТЕЛЬНО
4. Подписка на `hydro/{gh}/{zone}/{node}/+/command` (wildcard для всех каналов)
5. (Опционально) Подписка на `hydro/{gh}/{zone}/{node}/config` для legacy/сервисного сценария
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

# 5. NodeConfig (узлы → backend)

## 5.1. Топик
```
hydro/{gh}/{zone}/{node}/config_report
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
- Узел отправляет `config_report` при подключении

---

# 6. Обработка config_report на backend

Backend подписывается на `hydro/+/+/+/config_report` через сервис `history-logger`:

- сохраняет NodeConfig в `nodes.config`
- синхронизирует `node_channels`
- переводит ноду в `ASSIGNED_TO_ZONE`, если она в `REGISTERED_BACKEND` и имеет `zone_id`/`pending_zone_id`

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
 "params": {
   "duration_ms": 2500
 },
 "cmd_id": "cmd-591",
 "ts": 1737355112,
 "sig": "a1b2c3d4e5f6..."
}
```

### 2) Включение реле
```json
{
 "cmd": "set_relay",
 "params": {
   "state": true
 },
 "cmd_id": "cmd-592",
 "ts": 1737355113,
 "sig": "b2c3d4e5f6a1..."
}
```

### 3) PWM
```json
{
 "cmd": "set_pwm",
 "params": {
   "value": 128
 },
 "cmd_id": "cmd-593",
 "ts": 1737355114,
 "sig": "c3d4e5f6a1b2..."
}
```

### 4) Калибровка
```json
{
 "cmd": "calibrate",
 "params": {
   "type": "PH_7"
 },
 "cmd_id": "cmd-594",
 "ts": 1737355115,
 "sig": "d4e5f6a1b2c3..."
}
```

## 7.3. Формат команды с HMAC подписью

Все команды должны содержать следующие обязательные поля:

| Поле | Тип | Описание |
|------|-----|----------|
| `cmd` | string | Имя команды |
| `cmd_id` | string | Уникальный ID команды |
| `params` | object | Параметры команды (опционально) |
| `ts` | number | Unix timestamp в секундах (обязательно для HMAC) |
| `sig` | string | HMAC-SHA256 подпись (обязательно для HMAC) |

**Формат подписи:**
```
sig = HMAC_SHA256(node_secret, canonical_json(command_without_sig))
```

Где:
- `node_secret` — секретный ключ узла (хранится в NodeConfig поле `node_secret` или используется дефолтный)
- `canonical_json` — каноническая JSON-строка команды без поля `sig`:
  - ключи объектов отсортированы лексикографически,
  - порядок массивов сохраняется,
  - сериализация без пробелов,
  - числа форматируются как в cJSON (int если целое, иначе 15/17 значащих),
  - строки JSON-экранируются, UTF-8, слэши не экранируются.
- Подпись возвращается в виде hex строки (64 символа, нижний регистр)

**Проверка на узле:**
1. Узел проверяет наличие полей `ts` и `sig`
2. Если поля присутствуют, выполняется проверка:
   - Формат: `ts` должен быть числом, `sig` должен быть строкой длиной 64 символа (hex)
   - Timestamp: `abs(now - ts) < 10 секунд` (где `now` и `ts` в секундах Unix timestamp)
   - HMAC подпись: вычисляется ожидаемая подпись и сравнивается с полученной (регистронезависимое сравнение hex)
3. Если проверки не пройдены, команда отклоняется с ошибкой:
   - `invalid_hmac_format` — неверный формат полей или длина подписи
   - `timestamp_expired` — timestamp вне допустимого диапазона
   - `invalid_signature` — подпись не совпадает
4. Если поля `ts` и `sig` отсутствуют, команда обрабатывается в режиме обратной совместимости (с предупреждением в логах)

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (node_command_handler.c)

---

# 8. Command Response (узлы → backend)

## 8.1. Топик
```
hydro/{gh}/{zone}/{node}/{channel}/command_response
```

## 8.2. Общие требования

Каждая команда, отправленная в `.../{channel}/command`, **обязана** породить хотя бы один
ответ `command_response` от узла:

- даже если команда была отвергнута по валидации (HMAC, timestamp, параметры);
- даже если действие выполнить не удалось по железу (ошибка насоса, проблема с питанием);
- даже если узел находился в SAFE_MODE.

Backend никогда не остаётся "в неизвестности": по `cmd_id` он либо получает `ACK`,
либо `ERROR`/`TIMEOUT` и может принять управленческое решение.

## 8.2.1. Формат command_response

**Обязательные поля:**
- `cmd_id` (string) — идентификатор команды, точно соответствующий `cmd_id` из команды
- `status` (string) — статус выполнения: `ACK`, `DONE`, `ERROR`, `INVALID`, `BUSY`, `NO_EFFECT`
- `ts` (integer) — UTC timestamp в миллисекундах

**Опциональные поля:**
- `details` (string) — детали выполнения команды

**Пример успешного ответа:**
```json
{
  "cmd_id": "cmd-591",
  "status": "DONE",
  "details": "OK",
  "ts": 1710003399123
}
```

**Пример ошибки валидации HMAC:**

Если команда отклонена из-за невалидной HMAC подписи или истекшего timestamp, узел отправляет:

```json
{
  "cmd_id": "cmd-591",
  "status": "ERROR",
  "details": "Command HMAC signature verification failed",
  "ts": 1710003399123
}
```

или

```json
{
  "cmd_id": "cmd-591",
  "status": "ERROR",
  "ts": 1710003399,
  "error_code": "timestamp_expired",
  "error_message": "Command timestamp is outside acceptable range"
}
```

## 8.3. Базовый payload

```json
{
  "cmd_id": "cmd-591",
  "status": "ACK",
  "ts": 1710003333123
}
```

**Важно:** Поле `ts` содержит UTC timestamp в **миллисекундах** (не секундах).

Статусы:
- `ACK` — команда принята и будет выполнена;
- `DONE` — команда выполнена успешно;
- `ERROR` — команда не выполнена или выполнена с ошибкой;
- `INVALID` — команда невалидна (неверные параметры);
- `BUSY` — узел занят, команда не может быть выполнена сейчас;
- `NO_EFFECT` — команда не оказала эффекта (например, реле уже в нужном состоянии).

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
    "node_name": null,
    "greenhouse_token": null,
    "zone_id": null
  }
}
```

**Requirements:**
- QoS = 1
- Retain = false
- Backend обрабатывает и создаёт/обновляет `DeviceNode` с `logical_node_id` (uid). Поля `greenhouse_token` и `zone_id` из `provisioning_meta` игнорируются; привязка теплицы/зоны выполняется только вручную через UI/Android, после чего нода отправляет `config_report`.

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (обработчик `handle_node_hello` в history-logger, интеграция с Laravel API; автопривязка по token отключена)

---

## 9.2. Heartbeat узла
```
hydro/{gh}/{zone}/{node}/heartbeat
```

**Payload:**
```json
{
  "uptime": 3600,
  "free_heap": 102000,
  "rssi": -62
}
```

**Обязательные поля:**
- `uptime` (integer) — время работы узла в секундах (не миллисекунды)
- `free_heap` (integer) — свободная память в байтах

**Опциональные поля:**
- `rssi` (integer) — сила сигнала Wi-Fi в dBm (от -100 до 0)

> **Важно:** Поле `ts` **не включается** в heartbeat согласно эталону node-sim. Формат соответствует эталону, который успешно проходит E2E тесты.

**Requirements:**
- QoS = 1 (обновлено: было 0, теперь 1 для надёжности)
- Retain = false
- Backend обновляет поля `last_heartbeat_at`, `uptime_seconds`, `free_heap_bytes`, `rssi` в таблице `nodes`
- Обновляет также `last_seen_at` при получении heartbeat

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (обработчик `handle_heartbeat` в history-logger, поля в БД добавлены)

---

## 9.3. Error (публикация ошибок узлом)

**Топик:**
```
hydro/{gh}/{zone}/{node}/error
```

**Payload:**
```json
{
  "level": "ERROR",
  "component": "ph_sensor",
  "error_code": "esp_ESP_ERR_INVALID_STATE",
  "message": "Sensor not initialized",
  "ts": 1710003399123,
  "details": {
    "error_code_num": 9,
    "original_level": "CRITICAL"
  }
}
```

**Обязательные поля:**
- `level` (string) — уровень ошибки: `ERROR`, `WARNING`, `INFO` (CRITICAL маппится в ERROR)
- `component` (string) — компонент, сгенерировавший ошибку
- `error_code` (string) — код ошибки (например, `esp_ESP_ERR_INVALID_STATE`)
- `message` (string) — человекочитаемое сообщение об ошибке

**Опциональные поля:**
- `ts` (integer) — UTC timestamp в миллисекундах
- `details` (object) — дополнительные детали ошибки

**Requirements:**
- QoS = 1
- Retain = false
- Backend обрабатывает ошибки и может создавать алерты

---

## 9.4. Debug (опционально)
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
| config_report | 1 | false |
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

## Config → Backend
```
node → mqtt → history-logger → Laravel API → nodes.config + node_channels
```

**Автоматическая синхронизация:**
- Нода отправляет `config_report` при подключении (или после обновления прошивки)
- Сервер сохраняет конфиг и синхронизирует каналы

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (history-logger config_report handler)

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
- `hydro/{gh}/{zone}/{node}/+/command` — для получения команд по всем каналам (wildcard)

Опционально (legacy/сервисный сценарий):
- `hydro/{gh}/{zone}/{node}/config` — получение конфигурации с сервера, если она публикуется вручную

## 13.2. Публикации (обязательные)

Узел **ОБЯЗАН** публиковать:

### При подключении к MQTT брокеру:
- **status** (`hydro/{gh}/{zone}/{node}/status`) — **ОБЯЗАТЕЛЬНО** сразу после `MQTT_EVENT_CONNECTED` (см. раздел 4.2)

### Регулярно:
- **telemetry** (`hydro/{gh}/{zone}/{node}/{channel}/telemetry`) — по расписанию из NodeConfig
- **heartbeat** (`hydro/{gh}/{zone}/{node}/heartbeat`) — периодически (например, каждые 30 секунд)

### По запросу:
- **command_response** (`hydro/{gh}/{zone}/{node}/{channel}/command_response`) — на каждую команду
- **config_report** (`hydro/{gh}/{zone}/{node}/config_report`) — при подключении/инициализации (отправка текущего NodeConfig)

### При регистрации:
- **node_hello** (`hydro/node_hello` или `hydro/{gh}/{zone}/{node}/node_hello`) — при первой регистрации

### При инициализации:
- **lwt** (`hydro/{gh}/{zone}/{node}/lwt`) — настраивается при инициализации MQTT клиента

## 13.3. Общие требования

- JSON строго формализован согласно спецификации
- Ошибки команд возвращаются через command_response
- Все публикации должны соответствовать форматам из разделов 3-9
- QoS и Retain должны соответствовать таблице из раздела 10

---

# 14. Требования к backend

- полный MQTT router
- QoS = 1
- хранение команд
- таймаут команд (если нет ACK)
- хранить NodeConfig из `config_report` и использовать его для команд/телеметрии
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
