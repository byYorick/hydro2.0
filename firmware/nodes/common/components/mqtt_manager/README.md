# MQTT Client Component

Компонент MQTT клиента для всех ESP32-нод системы Hydro 2.0.

## Описание

Компонент обеспечивает подключение к MQTT брокеру, подписки на топики конфигурации и команд, публикацию телеметрии, статусов и heartbeat согласно спецификации `MQTT_SPEC_FULL.md`.

## Возможности

- Подключение к MQTT брокеру с поддержкой TLS
- Автоматический реконнект при разрыве соединения
- LWT (Last Will and Testament) для уведомления об отключении
- Подписка на топики config и command
- Публикация всех типов сообщений с правильными QoS/Retain
- Callback'и для обработки входящих сообщений и событий подключения

## API

### Инициализация

```c
mqtt_client_config_t mqtt_config = {
    .host = "192.168.1.10",
    .port = 1883,
    .keepalive = 30,
    .client_id = NULL,  // Используется node_uid
    .username = NULL,
    .password = NULL,
    .use_tls = false
};

mqtt_node_info_t node_info = {
    .gh_uid = "gh-1",
    .zone_uid = "zn-3",
    .node_uid = "nd-ph-1"
};

mqtt_client_init(&mqtt_config, &node_info);
mqtt_client_start();
```

### Регистрация callbacks

```c
// Обработка config сообщений
mqtt_client_register_config_cb(on_config_received, NULL);

// Обработка command сообщений
mqtt_client_register_command_cb(on_command_received, NULL);

// События подключения/отключения
mqtt_client_register_connection_cb(on_connection_changed, NULL);
```

### Публикация сообщений

```c
// Телеметрия
mqtt_client_publish_telemetry("ph_sensor", json_data);

// Статус
mqtt_client_publish_status(json_data);

// Heartbeat
mqtt_client_publish_heartbeat(json_data);

// Ответ на команду
mqtt_client_publish_command_response("pump_acid", json_data);

// Ответ на конфигурацию
mqtt_client_publish_config_response(json_data);
```

## Формат топиков

Согласно `MQTT_SPEC_FULL.md` раздел 2:

- Config: `hydro/{gh}/{zone}/{node}/config`
- Command: `hydro/{gh}/{zone}/{node}/{channel}/command`
- Telemetry: `hydro/{gh}/{zone}/{node}/{channel}/telemetry`
- Status: `hydro/{gh}/{zone}/{node}/status`
- LWT: `hydro/{gh}/{zone}/{node}/lwt`
- Heartbeat: `hydro/{gh}/{zone}/{node}/heartbeat`
- Command Response: `hydro/{gh}/{zone}/{node}/{channel}/command_response`
- Config Response: `hydro/{gh}/{zone}/{node}/config_response`

Где:
- `{gh}` — UID теплицы (например `gh-1`)
- `{zone}` — UID зоны (например `zn-3`)
- `{node}` — UID узла (например `nd-ph-1`)
- `{channel}` — имя канала (например `ph_sensor`, `pump_acid`)

## Форматы JSON сообщений

### Telemetry (раздел 3.2 MQTT_SPEC_FULL.md)
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

### Status (раздел 4.2 MQTT_SPEC_FULL.md)
```json
{
  "status": "ONLINE",
  "ts": 1710001555
}
```

### Heartbeat (раздел 9.1 MQTT_SPEC_FULL.md)
```json
{
  "uptime": 35555,
  "free_heap": 102000,
  "rssi": -62
}
```

### Command Response (раздел 8.3 MQTT_SPEC_FULL.md)
Успех:
```json
{
  "cmd_id": "cmd-591",
  "status": "ACK",
  "ts": 1710003333
}
```

Ошибка:
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

### Config Response (раздел 6.2 MQTT_SPEC_FULL.md)
Успех:
```json
{
  "status": "OK",
  "node_id": "nd-ph-1",
  "applied": true,
  "timestamp": 1710002222
}
```

Ошибка:
```json
{
  "status": "ERROR",
  "error": "Invalid channel ph_sensor",
  "timestamp": 1710002223
}
```

## QoS и Retain

- Telemetry, Command, Command Response, Config, Config Response: QoS=1, Retain=false
- Status, LWT: QoS=1, Retain=true
- Heartbeat: QoS=0, Retain=false

## Зависимости

- ESP-IDF компонент `mqtt`
- ESP-IDF компонент `esp_netif`
- ESP-IDF компонент `esp_event`
- ESP-IDF компонент `esp_timer`

## Документация

- Спецификация MQTT: `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- Стандарты кодирования: `doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md`
- Спецификация NodeConfig: `firmware/NODE_CONFIG_SPEC.md`

