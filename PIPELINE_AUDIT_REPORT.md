# Отчет о проверке пайплайна от нод к backend сервисам

## Дата: 2025-01-XX

## Цель
Проверить полный пайплайн передачи данных от ESP32 нод через MQTT до backend сервисов (history-logger, Laravel).

## Архитектура пайплайна

```
ESP32 Node → MQTT Broker → Backend Services
    ↓              ↓              ↓
mqtt_manager  MQTT Topics   history-logger
              Laravel Services
```

## 1. Публикация данных от нод

### 1.1. Формат топиков (build_topic)

**Функция:** `mqtt_manager.c::build_topic()`

**Формат:**
- С каналом: `hydro/{gh}/{zone}/{node}/{channel}/{type}`
- Без канала: `hydro/{gh}/{zone}/{node}/{type}`

**Примеры:**
- Telemetry: `hydro/gh-1/zn-3/nd-ph-1/ph_sensor/telemetry`
- Heartbeat: `hydro/gh-1/zn-3/nd-ph-1/heartbeat`
- Status: `hydro/gh-1/zn-3/nd-ph-1/status`
- Command Response: `hydro/gh-1/zn-3/nd-ph-1/pump_acid/command_response`
- Config Response: `hydro/gh-1/zn-3/nd-ph-1/config_response`
- LWT: `hydro/gh-1/zn-3/nd-ph-1/lwt`

**Статус:** ✅ **КОРРЕКТНО**

### 1.2. Типы сообщений от нод

#### Telemetry
- **Функция:** `mqtt_manager_publish_telemetry(channel, data)`
- **Топик:** `hydro/{gh}/{zone}/{node}/{channel}/telemetry`
- **QoS:** 1
- **Retain:** false
- **Payload формат:**
```json
{
  "metric_type": "PH",
  "value": 6.5,
  "ts": 1737979.2,
  "channel": "ph_sensor",
  "node_id": "nd-ph-1",
  "raw": 1465,
  "stub": false,
  "stable": true
}
```

#### Heartbeat
- **Функция:** `mqtt_manager_publish_heartbeat(data)`
- **Топик:** `hydro/{gh}/{zone}/{node}/heartbeat`
- **QoS:** 0 (⚠️ **ПРОБЛЕМА:** должно быть 1 согласно спецификации)
- **Retain:** false
- **Payload формат:**
```json
{
  "uptime": 35555,
  "free_heap": 102000,
  "rssi": -62
}
```

#### Status
- **Функция:** `mqtt_manager_publish_status(data)`
- **Топик:** `hydro/{gh}/{zone}/{node}/status`
- **QoS:** 1
- **Retain:** true
- **Payload формат:**
```json
{
  "status": "ONLINE",
  "ts": 1710001555
}
```

#### Node Hello
- **Функция:** `mqtt_manager_publish_raw("hydro/node_hello", data, 1, 0)`
- **Топик:** `hydro/node_hello` (глобальный) или `hydro/{gh}/{zone}/{node}/node_hello`
- **QoS:** 1
- **Retain:** false
- **Payload формат:**
```json
{
  "message_type": "node_hello",
  "hardware_id": "esp32-aabbccddeeff",
  "node_type": "ph",
  "fw_version": "v5.1.0",
  "hardware_revision": "rev1",
  "capabilities": [...],
  "provisioning_meta": {...}
}
```

#### Command Response
- **Функция:** `mqtt_manager_publish_command_response(channel, data)`
- **Топик:** `hydro/{gh}/{zone}/{node}/{channel}/command_response`
- **QoS:** 1
- **Retain:** false

#### Config Response
- **Функция:** `mqtt_manager_publish_config_response(data)`
- **Топик:** `hydro/{gh}/{zone}/{node}/config_response`
- **QoS:** 1
- **Retain:** false

## 2. Подписки backend сервисов

### 2.1. history-logger (Python/FastAPI)

**Файл:** `backend/services/history-logger/main.py`

**Подписки:**
```python
await mqtt.subscribe("hydro/+/+/+/+/telemetry", handle_telemetry)
await mqtt.subscribe("hydro/+/+/+/heartbeat", handle_heartbeat)
await mqtt.subscribe("hydro/node_hello", handle_node_hello)
await mqtt.subscribe("hydro/+/+/+/node_hello", handle_node_hello)
await mqtt.subscribe("hydro/+/+/+/config_response", handle_config_response)
await mqtt.subscribe("hydro/+/+/+/+/command_response", handle_command_response)
```

**Статус:** ✅ **КОРРЕКТНО**

**Проблема:** ❌ **НЕТ подписки на status топик!**

### 2.2. Laravel Services

**Сервисы:**
- `NodeRegistryService` - регистрация узлов через API (вызывается из history-logger)
- `NodeLifecycleService` - управление жизненным циклом узлов
- `NodeConfigService` - управление конфигурацией узлов

**Статус:** ✅ **КОРРЕКТНО** (работают через API, не напрямую через MQTT)

## 3. Обработчики backend

### 3.1. handle_telemetry

**Функция:** `backend/services/history-logger/main.py::handle_telemetry()`

**Процесс:**
1. Парсинг JSON payload
2. Валидация через Pydantic (`TelemetryPayloadModel`)
3. Извлечение данных из топика: `gh_uid`, `zone_uid`, `node_uid`, `channel`
4. Создание `TelemetryQueueItem`
5. Добавление в Redis queue
6. Асинхронная обработка через `process_telemetry_queue()`
7. Сохранение в PostgreSQL/TimescaleDB

**Статус:** ✅ **КОРРЕКТНО**

### 3.2. handle_heartbeat

**Функция:** `backend/services/history-logger/main.py::handle_heartbeat()`

**Процесс:**
1. Парсинг JSON payload
2. Извлечение `node_uid` из топика
3. Whitelist полей для безопасности (uptime, free_heap, rssi)
4. Обновление таблицы `nodes`:
   - `uptime_seconds` (конвертация из миллисекунд)
   - `free_heap_bytes`
   - `rssi`
   - `last_heartbeat_at = NOW()`
   - `last_seen_at = NOW()`
   - `status = 'online'`

**Статус:** ✅ **КОРРЕКТНО**

**Проблема:** ⚠️ **QoS heartbeat в firmware = 0, но должно быть 1**

### 3.3. handle_node_hello

**Функция:** `backend/services/history-logger/main.py::handle_node_hello()`

**Процесс:**
1. Парсинг JSON payload
2. Проверка `message_type == "node_hello"`
3. Извлечение `hardware_id`
4. Вызов Laravel API: `POST /api/nodes/register`
5. Retry логика с exponential backoff
6. Обновление метрик Prometheus

**Статус:** ✅ **КОРРЕКТНО**

### 3.4. handle_config_response

**Функция:** `backend/services/history-logger/main.py::handle_config_response()`

**Процесс:**
1. Парсинг JSON payload
2. Извлечение `node_uid` из топика
3. Проверка статуса `ACK`
4. Валидация `cmd_id` и `config_version`
5. Переход узла в `ASSIGNED_TO_ZONE` через Laravel API

**Статус:** ✅ **КОРРЕКТНО**

### 3.5. handle_command_response

**Функция:** `backend/services/history-logger/main.py::handle_command_response()`

**Процесс:**
1. Парсинг JSON payload
2. Извлечение данных из топика
3. Обновление статуса команды (для уведомлений на фронт)

**Статус:** ✅ **КОРРЕКТНО**

## 4. Извлечение данных из топиков

### 4.1. Функции извлечения

**Файл:** `backend/services/history-logger/main.py`

**Функции:**
- `_extract_gh_uid(topic)` - извлекает `gh_uid` (2-й элемент)
- `_extract_zone_uid(topic)` - извлекает `zone_uid` (3-й элемент)
- `_extract_node_uid(topic)` - извлекает `node_uid` (4-й элемент)
- `_extract_channel_from_topic(topic)` - извлекает `channel` (5-й элемент для telemetry)

**Формат топика:** `hydro/{gh}/{zone}/{node}/{channel}/{type}`

**Пример:**
- Топик: `hydro/gh-1/zn-3/nd-ph-1/ph_sensor/telemetry`
- `gh_uid` = `gh-1`
- `zone_uid` = `zn-3`
- `node_uid` = `nd-ph-1`
- `channel` = `ph_sensor`
- `type` = `telemetry`

**Статус:** ✅ **КОРРЕКТНО**

## 5. Проблемы и рекомендации

### ❌ Критические проблемы

1. **Нет подписки на status топик в history-logger**
   - **Проблема:** Backend не обрабатывает статус "ONLINE" при подключении узла
   - **Решение:** Добавить подписку `hydro/+/+/+/status` и обработчик `handle_status()`
   - **Приоритет:** Высокий

2. **QoS heartbeat = 0 вместо 1**
   - **Проблема:** В `mqtt_manager.c::mqtt_manager_publish_heartbeat()` используется QoS 0
   - **Спецификация:** QoS должен быть 1
   - **Решение:** Изменить QoS на 1 в firmware
   - **Приоритет:** Средний

### ⚠️ Предупреждения

1. **Публикация status при подключении**
   - **Статус:** Нужно проверить, что ноды публикуют status при `MQTT_EVENT_CONNECTED`
   - **Рекомендация:** Проверить реализацию в `mqtt_manager.c::mqtt_event_handler()`

2. **Формат uptime в heartbeat**
   - **Проблема:** Прошивки отправляют uptime в миллисекундах, backend конвертирует в секунды
   - **Статус:** ✅ Обработано корректно в `handle_heartbeat()`

## 6. Проверка соответствия форматов

### 6.1. Telemetry

| Поле | Firmware | Backend | Статус |
|------|----------|---------|--------|
| metric_type | ✅ | ✅ | ✅ |
| value | ✅ | ✅ | ✅ |
| ts | ✅ | ✅ | ✅ |
| channel | ✅ | ✅ | ✅ |
| node_id | ✅ | ✅ | ✅ |
| raw | ✅ | ✅ | ✅ |
| stub | ✅ | ✅ | ✅ |
| stable | ✅ | ✅ | ✅ |

### 6.2. Heartbeat

| Поле | Firmware | Backend | Статус |
|------|----------|---------|--------|
| uptime | ✅ (ms) | ✅ (конверт в сек) | ✅ |
| free_heap | ✅ | ✅ | ✅ |
| rssi | ✅ | ✅ | ✅ |

### 6.3. Node Hello

| Поле | Firmware | Backend | Статус |
|------|----------|---------|--------|
| message_type | ✅ | ✅ | ✅ |
| hardware_id | ✅ | ✅ | ✅ |
| node_type | ✅ | ✅ | ✅ |
| fw_version | ✅ | ✅ | ✅ |
| hardware_revision | ✅ | ✅ | ✅ |
| capabilities | ✅ | ✅ | ✅ |
| provisioning_meta | ✅ | ✅ | ✅ |

## 7. Резюме

### ✅ Работает корректно:
- Формат топиков (build_topic)
- Подписки на telemetry, heartbeat, node_hello, config_response, command_response
- Обработка telemetry (валидация, очередь, сохранение)
- Обработка heartbeat (обновление статуса узла)
- Обработка node_hello (регистрация через Laravel API)
- Обработка config_response (переход в ASSIGNED_TO_ZONE)
- Извлечение данных из топиков
- Публикация status при MQTT_EVENT_CONNECTED в firmware ✅

### ✅ Исправлено:
1. ✅ Добавлена подписка на status топик в history-logger
2. ✅ Добавлен обработчик handle_status() для обновления статуса узлов
3. ✅ Изменен QoS heartbeat с 0 на 1 в firmware
4. ✅ Добавлена метрика STATUS_RECEIVED для мониторинга

## 8. Рекомендации

1. **Добавить обработчик status в history-logger:**
   ```python
   await mqtt.subscribe("hydro/+/+/+/status", handle_status)
   ```

2. **Исправить QoS heartbeat в firmware:**
   ```c
   return mqtt_manager_publish_internal(topic, data, 1, 0);  // QoS = 1
   ```

3. **Проверить публикацию status при подключении:**
   - Убедиться, что в `mqtt_event_handler()` при `MQTT_EVENT_CONNECTED` публикуется status

4. **Добавить мониторинг:**
   - Метрики для обработки status сообщений
   - Алерты на отсутствие status при подключении

