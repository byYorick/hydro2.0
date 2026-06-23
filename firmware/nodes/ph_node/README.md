# pH Node

pH-нода для измерения pH и управления насосами кислоты/щелочи (`node_type=ph`).

## Архитектура

- Тонкий слой: `ph_node_app` → `ph_node_init` (8 шагов) → `ph_node_start_tasks`
- Интеграция с `node_framework`: `ph_node_framework_init()`, `ph_node_framework_register_mqtt_handlers()`
- Каналы и GPIO задаются прошивкой (`ph_node_channel_map.c`); входящий NodeConfig патчится firmware map
- Общие лимиты correction-нод: `correction_node_contract.h` (queue=8, `max_duration_ms`=60000, STATUS interval=60 с)

## Используемый сенсор

Нода использует **Trema pH-сенсор (iarduino)** через I²C:

| Шина | GPIO (дефолт) | Устройства |
|------|----------------|------------|
| **I2C 0** | SDA **21**, SCL **22** | OLED (**0x3C**), INA209 (**0x40**) |
| **I2C 1** | SDA **18**, SCL **19** | Trema pH |

- Компонент: `trema_ph`
- I²C адрес: **0x09** (заводской iarduino; см. `ph_node_defaults.h`)
- Калибровка: 2 этапа, persist в NVS + `config_report`
- Опрос: `ph_node_ph_poll_sensor_once()` → MQTT/OLED только из `trema_ph_try_cached_measurement`

## Каналы

### Сенсоры
- `ph_sensor` — датчик pH (aliases: `ph`)

### Актуаторы
- `pump_acid` — насос кислоты (aliases: `ph_doser_down`)
- `pump_base` — насос щелочи (aliases: `ph_doser_up`)

### Система
- `system` — `activate_sensor_mode`, `deactivate_sensor_mode`, builtin `restart`/`reboot`/`report_config`

## Команды

### run_pump

Запуск насоса на указанное время:

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
- `duration_ms` (integer): 1–60000 мс (жёсткий лимит валидатора; `safe_limits.max_duration_ms` в channel map — тот же cap)
- `cmd_id` (string): обязателен, HMAC-подпись команды

**Ответ (двухфазный):**
1. `ACK` — команда принята в очередь (`details.queued=true`, опционально `cooldown_ms`)
2. `DONE` или `ERROR` — terminal-ответ по тому же `cmd_id` после завершения таймера

**Коды ERROR (terminal и синхронные):**
- `pump_busy` — насос занят или cooldown
- `pump_not_found` — канал не найден
- `pump_queue_full` — очередь насосов переполнена (лимит **8**)
- `invalid_params` — неверный `duration_ms`
- `pump_not_calibrated` — насос не откалиброван в NodeConfig
- `current_unavailable` — INA209 не подтвердил ток после старта (или fault от `pump_driver`)
- `node_not_activated` — для `dose`, если sensor mode выключен

### dose

Дозирование в миллилитрах (orchestration-контракт):

```json
{
  "cmd": "dose",
  "cmd_id": "cmd-123",
  "params": {
    "ml": 0.8
  }
}
```

Нода преобразует `ml` → `duration_ms` по `ml_per_second` канала. Доступна только при активном **sensor mode** (`activate_sensor_mode` на канале `system`). Ответ: `ACK` → `DONE`/`ERROR`.

### calibrate / calibrate_ph

Калибровка pH (только канал **`ph_sensor`**):

```json
{
  "cmd": "calibrate",
  "cmd_id": "cmd-124",
  "params": {
    "stage": 1,
    "known_ph": 7.0
  }
}
```

**Параметры:**
- `stage` (integer): 1 или 2
- `known_ph` (float) или alias `ph_value`: 0.0–14.0

**Этапы:**
- **1** — нейтральный буфер (типично pH 7.0)
- **2** — кислый/щелочной буфер (типично 4.0 или 10.0)

**Ответ (синхронный):**
- `DONE` — калибровка выполнена, точка записана в `calibration.ph.pointN` (NVS) и отправлен `config_report` (с retry)
- `ERROR`: `invalid_channel`, `calibration_failed`, `calibration_nvs_sync_failed`

### test_sensor / probe_sensor

Синхронный `DONE` с reading на SENSOR-канале. Для `ph_sensor` stub → `ERROR` `sensor_stub` (в отличие от телеметрии, где stub помечается `stub=true`).

### system / sensor mode

- `activate_sensor_mode` / `deactivate_sensor_mode` — идемпотентный `DONE`
- Builtin: `restart`, `reboot`, `report_config`, `set_time`

## STATUS и heartbeat

- Периодическая публикация **STATUS** каждые **60 с** (`status_task`)
- Payload (расширенный профиль `DEVICE_NODE_PROTOCOL.md` §4.2): `status`, `ts`, `online`, `ip`, `rssi`, `fw`
- Heartbeat — общий компонент `heartbeat_task`

## Идемпотентность cmd_id

`node_command_handler` кеширует terminal-статусы `DONE`/`ERROR` и in-flight `ACK` по `cmd_id` (TTL **5 мин**, LRU 128). Повтор с тем же `cmd_id` возвращает закешированный статус без повторного исполнения.

## Очередь насосов

- Лимит **8** команд (`CORRECTION_NODE_PUMP_QUEUE_MAX`)
- Последовательная обработка в `ph_pump_queue` task
- Перед стартом — проверка тока INA209; при fail — terminal `ERROR` `current_unavailable`

## Watchdog

Watchdog (~10 с): `sensor_task`, `pump_current_task`, `status_task` периодически сбрасывают WDT.

## Документация

- Архитектура нод: `../../../doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- MQTT: `../../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- NodeConfig: `../../NODE_CONFIG_SPEC.md`
- Device protocol (STATUS): `../../../doc_ai/02_HARDWARE_FIRMWARE/DEVICE_NODE_PROTOCOL.md`
