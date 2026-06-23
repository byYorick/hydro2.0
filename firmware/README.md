Прошивки ESP32 (ESP-IDF). Содержит общие компоненты и проекты нод.

## Структура

```
firmware/
├── nodes/
│   ├── common/components/   # Общие ESP-IDF-компоненты (~25 модулей)
│   ├── ph_node/
│   ├── ec_node/
│   ├── climate_node/
│   ├── storage_irrigation_node/
│   ├── relay_node/
│   ├── pump_node/
│   └── light_node/          # ESP32-C3, сенсор освещённости (trema_light)
├── test_node/               # HIL: виртуальные ноды на одном ESP32
├── schemas/
├── build_all_nodes.sh
└── check_compilation.sh
```

### Общие компоненты (`nodes/common/components/`)

- `mqtt_manager/` — MQTT клиент и топик-роутер (MVP_DONE)
- `mqtt_client/` — compatibility shim к `mqtt_manager`
- `wifi_manager/`, `config_storage/`, `config_apply/`, `node_framework/`
- `i2c_bus/`, `i2c_cache/`, `memory_pool/`, `oled_ui/`, `logging/`
- `heartbeat_task/`, `connection_status/`, `setup_portal/`, `diagnostics/`
- `factory_reset_button/`, `node_utils/`, `node_watchdog/` (внутри `node_framework/`)
- `sensors/` — trema_ph, trema_ec, trema_light, sht3x, ina209, ccs811, ph_sensor, ec_sensor
- `pump_driver/`, `relay_driver/` — драйверы актуаторов (MVP_DONE)
- `ws2811_driver/` — **planned** (только `WS2811_GUIDE.md`, без `.c`)

**Примечание:** PWM для `climate_node` реализован локально в `climate_node/main/pwm_driver.c`, не в `common/components/`.

## Документация

- Спецификация NodeConfig: `NODE_CONFIG_SPEC.md` → `doc_ai/02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md`
- Архитектура нод: `../doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- Структура прошивки: `../doc_ai/02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md`
- MQTT протокол: `../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`

### Тестирование

- Тесты совместимости: `tests/README.md`
- Симулятор ноды: `../tests/node_sim/README.md`
- Тестовая прошивка: `test_node/README.md`

## Сборка

```bash
# Все production-ноды (требуется ESP-IDF)
./firmware/build_all_nodes.sh

# Подмножество (CI / быстрая проверка)
./firmware/check_compilation.sh

# Одна нода
source ~/esp/esp-idf/export.sh
cd firmware/nodes/ph_node && idf.py build
```

## Статус реализации

| Нода | Статус | Примечание |
|------|--------|------------|
| `ph_node` | ✅ production | trema_ph, pump_driver, node_framework |
| `ec_node` | ✅ production | trema_ec, pump_driver |
| `storage_irrigation_node` | ✅ production | two-tank, level_switch events, fail-safe |
| `climate_node` | ✅ production | sht3x, ccs811, relay + local PWM |
| `relay_node` | ⚠️ средняя | GPIO map — проверить под плату |
| `pump_node` | ⚠️ средняя | иной bootstrap в `main.c` |
| `light_node` | ⚠️ сенсорная | trema_light, без актуаторов света |
| `test_node` | ✅ HIL | эталон контрактов, не production |
