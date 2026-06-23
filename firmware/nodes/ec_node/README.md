# EC Node

EC-нода для измерения электропроводности и управления четырьмя насосами питания (`node_type=ec`).

## Архитектура

- Тонкий слой: `ec_node_app` → `ec_node_init` (8 шагов) → `ec_node_start_tasks`
- Интеграция с `node_framework`: `ec_node_framework_init()`, `ec_node_framework_register_mqtt_handlers()`
- Каналы и GPIO задаются прошивкой (`ec_node_channel_map.c`); входящий NodeConfig патчится firmware map
- Общие лимиты correction-нод: `correction_node_contract.h` (queue=8, `max_duration_ms`=60000, STATUS interval=60 с)

## Используемый сенсор

Нода использует **Trema EC-сенсор (iarduino)** через I²C.

**Разводка I²C как на ph_node:** две шины — **I2C 0** (21/22) для OLED и INA209, **I2C 1** (18/19) для Trema EC.

| Шина | GPIO (дефолт) | Устройства |
|------|----------------|------------|
| **I2C 0** | SDA **21**, SCL **22** | OLED (**0x3C**), INA209 (**0x40**) |
| **I2C 1** | SDA **18**, SCL **19** | Trema Flash TDS/EC (7-bit **0x09** завод / **0x08** и др.) |

Драйвер `trema_ec` по умолчанию на **`I2C_BUS_1`**; при недоступности — fallback на `I2C_BUS_0` (legacy). Пины — `ec_node_defaults.h`.

- Компонент: `trema_ec`
- Калибровка: 2 этапа по `tds_value` (ppm), persist в NVS + `config_report`
- Температурная компенсация (чтение temp из config_storage; отдельная temp-телеметрия не публикуется)
- Телеметрия: `ec_sensor` (mS/cm) + канал `ec_tds_ppm` (ppm, `METRIC_TYPE_CUSTOM`)
- Фильтр скачков EC: отклонение ΔEC > 2.5 mS/cm → hold last good + `stub=true`

## Опрос и телеметрия (sensor_task)

- За тик: **`ec_node_ec_poll_sensor_once()`** — probe, init, read, `trema_ec_push_telemetry_snapshot`
- MQTT/OLED: только **`trema_ec_try_cached_measurement`** (без повторного I²C read)
- Для OLED: **`ec_node_ec_last_poll_probe_present()`**

## Каналы

### Сенсоры
- `ec_sensor` — датчик EC (alias: `ec`)

### Актуаторы
- `pump_a` — компонент A (NPK)
- `pump_b` — компонент B (Ca)
- `pump_c` — компонент C (Mg)
- `pump_d` — компонент D (Micro)

### Система
- `system` — sensor mode + builtin команды

## Команды

### run_pump

```json
{
  "cmd": "run_pump",
  "cmd_id": "cmd-123",
  "params": {
    "duration_ms": 2000
  }
}
```

**Параметры:**
- `duration_ms` (integer): 1–60000 мс
- `cmd_id` (string): обязателен, HMAC-подпись

**Ответ (двухфазный):**
1. `ACK` — принято в очередь
2. `DONE` / `ERROR` — terminal по тому же `cmd_id`

**Коды ERROR:**
- `pump_busy`, `pump_not_found`, `pump_queue_full` (лимит **8**)
- `invalid_params`, `pump_not_calibrated`
- `current_unavailable` — нет подтверждения тока INA209
- `cooldown_active`
- `node_not_activated` — для `dose` без sensor mode

### dose

```json
{
  "cmd": "dose",
  "cmd_id": "cmd-123",
  "params": {
    "ml": 20.0
  }
}
```

`ml` → `duration_ms` по `ml_per_second`. Только при активном sensor mode. Ответ: `ACK` → `DONE`/`ERROR`.

### calibrate / calibrate_ec

Калибровка EC (только канал **`ec_sensor`**):

```json
{
  "cmd": "calibrate",
  "cmd_id": "cmd-124",
  "params": {
    "stage": 1,
    "tds_value": 1413
  }
}
```

**Параметры:**
- `stage` (integer): 1 или 2
- `tds_value` (integer): 0–10000 ppm

**Этапы:**
- **1** — стандартный раствор (например 1413 ppm)
- **2** — второй эталон (например 2764 ppm)

**Ответ (синхронный):**
- `DONE` — калибровка выполнена; `calibration.ec.pointN` записан в NVS; `config_report` с retry
- `ERROR`: `invalid_channel`, `invalid_format`, `invalid_stage`, `invalid_tds`, `calibration_failed`, `calibration_nvs_sync_failed`

### test_sensor / probe_sensor

Синхронный `DONE` с reading на `ec_sensor`. Stub → `ERROR` `sensor_stub`.

### system / sensor mode

- `activate_sensor_mode` / `deactivate_sensor_mode` — идемпотентный `DONE`
- Builtin: `restart`, `reboot`, `report_config`, `set_time`
- Alias: `probe_sensor` → `test_sensor`

## STATUS и heartbeat

- Периодическая **STATUS** каждые **60 с** (`status_task`)
- Payload: `status`, `ts`, `online`, `ip`, `rssi`, `fw` (`node_utils_publish_device_status_extended`)
- Heartbeat — `heartbeat_task_start_default()`

## Идемпотентность cmd_id

Кеш `node_command_handler`: `DONE`/`ERROR`/`ACK` (in-flight) по `cmd_id`, TTL **5 мин**. Повтор — без повторного исполнения.

## Очередь насосов

- Лимит **8** (`CORRECTION_NODE_PUMP_QUEUE_MAX`)
- Обработка в `ec_pump_queue` task; terminal publish + `cache_final_status`
- INA209 current gate при старте насоса

## Watchdog

`sensor_task` и `status_task` сбрасывают watchdog в цикле.

## Документация

- Архитектура нод: `../../../doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- MQTT: `../../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- NodeConfig: `../../NODE_CONFIG_SPEC.md`
- Device protocol (STATUS): `../../../doc_ai/02_HARDWARE_FIRMWARE/DEVICE_NODE_PROTOCOL.md`
