# EC Node

EC-нода для измерения электропроводности и управления четырьмя насосами питания.

## Используемый сенсор

Нода использует **Trema EC-сенсор (iarduino)** через I²C.

**Разводка I²C как на ph_node:** две шины — **I2C 0** (21/22) для OLED и INA209, **I2C 1** (18/19) **только для Trema EC** (отдельная линия, `pullup_enable=false` на мастере — подтяжки на модуле/внешние).

| Шина | GPIO (дефолт) | Устройства |
|------|----------------|-------------|
| **I2C 0** | SDA **21**, SCL **22** | OLED (**0x3C**), INA209 (**0x40**) |
| **I2C 1** | SDA **18**, SCL **19** | **Только Trema Flash TDS/EC** (7-bit **0x09** завод / **0x08** и др. — см. `trema_ec_get_i2c_address()`, `NODE_CHANNELS_REFERENCE` раздел 2.2) |

Драйвер `trema_ec` по умолчанию использует **`I2C_BUS_1`**; при недоступности шины 1 или отсутствии датчика на ней — **fallback на `I2C_BUS_0`** (legacy wiring, как до разводки ph_node). Шина задаётся через `trema_ec_set_i2c_bus()` в `ec_node_init_step_i2c`. Пины — `ec_node_defaults.h` (`EC_NODE_I2C_BUS_*`).

- Компонент: `trema_ec`
- I²C адрес: **0x09** (заводской iarduino); также **0x08** / **0x0A** при discovery; рабочий адрес на стенде часто **0x08** (см. `NODE_CHANNELS_REFERENCE`, раздел 2.2)
- Поддержка калибровки (2 этапа)
- Температурная компенсация
- Измерение EC (mS/cm) и TDS (ppm)

## Опрос и телеметрия (sensor_task)

- За тик вызывается **`ec_node_ec_poll_sensor_once()`**: `trema_ec_probe_present`, при необходимости `trema_ec_init`,
  температура, **`trema_ec_read`**, **`trema_ec_get_tds`**, затем **`trema_ec_push_telemetry_snapshot`** (в очередь
  попадают EC, raw, **tds_ppm**).
- **`ec_node_publish_telemetry_callback`** и OLED используют только **`trema_ec_try_cached_measurement`** — без
  повторного read/get_tds на MQTT.
- Для OLED без второго probe на шине: **`ec_node_ec_last_poll_probe_present()`** (результат probe в последнем poll).

## Описание

Нода измеряет EC (электропроводность) раствора и управляет 4 насосами для внесения компонентов питания.

## Каналы

### Сенсоры
- `ec_sensor` - датчик EC

### Актуаторы
- `pump_a` - насос компонента A (NPK)
- `pump_b` - насос компонента B (Ca)
- `pump_c` - насос компонента C (Mg)
- `pump_d` - насос компонента D (Micro)

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

### dose
Дозирование в миллилитрах через orchestration-совместимый контракт:
```json
{
  "cmd": "dose",
  "cmd_id": "cmd-123",
  "params": {
    "ml": 20.0
  }
}
```

Нода преобразует `ml` в `duration_ms` по `ml_per_second` канала насоса. Команда доступна только при активном `sensor_mode`.

### calibrate
Калибровка EC датчика (2 этапа):
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

Этапы калибровки:
- **Этап 1**: калибровка на известное TDS значение (например, 1413 ppm - стандартный раствор)
- **Этап 2**: калибровка на другое TDS значение (например, 2764 ppm)

После отправки команды калибровки нода отвечает статусом ACK или ERROR.

### system / sensor mode
Сервисный канал `system` поддерживает:
- `activate_sensor_mode`
- `deactivate_sensor_mode`
- `report_config`
- `reboot`

Также поддерживается alias `probe_sensor` -> `test_sensor`.

## Документация

- Архитектура нод: `../../../doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- MQTT спецификация: `../../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- NodeConfig: `../../NODE_CONFIG_SPEC.md`
