Прошивки ESP32 (ESP-IDF). Содержит общие компоненты и проекты нод.

## Структура

- `common/components/` — общие компоненты
  - `mqtt_client/` — MQTT клиент (MVP_DONE)
  - `mqtt_manager/` — MQTT менеджер и топик-роутер (MVP_DONE)
  - `wifi_manager/` — Wi-Fi менеджер (MVP_DONE)
  - `config_storage/` — Хранение NodeConfig (MVP_DONE)
  - `config_apply/` — Применение конфигурации (MVP_DONE)
  - `i2c_bus/` — I²C шина (MVP_DONE)
  - `oled_ui/` — OLED дисплей UI (MVP_DONE)
  - `logging/` — Система логирования (MVP_DONE)
  - `factory_reset_button/` — Аппаратный сброс NVS по длинному нажатию кнопки (NEW)
  - `heartbeat_task/` — Задача публикации heartbeat (MVP_DONE)
  - `node_framework/` — Унифицированный фреймворк для всех нод (MVP_DONE)
    - Обработка NodeConfig, команд, телеметрии
    - Управление состоянием (Safe Mode)
    - Унифицированный watchdog
  - `memory_pool/` — Оптимизация использования памяти (MVP_DONE)
  - `sensors/` — Драйверы сенсоров
    - `ph_sensor/` — pH-сенсор (универсальный драйвер, MVP_DONE)
    - `trema_ph/` — Trema pH-сенсор (iarduino, I²C, MVP_DONE) - используется в ph_node
    - `ec_sensor/` — EC-сенсор (универсальный драйвер, MVP_DONE)
    - `trema_ec/` — Trema EC-сенсор (iarduino, I²C, MVP_DONE) - используется в ec_node
    - `sht3x/` — Температура/влажность (MVP_DONE)
    - `ina209/` — Датчик тока (MVP_DONE)
  - `pump_driver/` — Драйвер насосов с мониторингом тока (MVP_DONE)
  - `relay_driver/` — Драйвер реле (MVP_DONE)
  - `pwm_driver/` — Драйвер PWM (MVP_DONE)
- `nodes/` — проекты нод:
  - `pump_node/` — насосная нода (частичная реализация)
  - `ph_node/` — pH нода (частичная реализация)
  - `ec_node/` — EC нода (частичная реализация)
  - `climate_node/` — климатическая нода (частичная реализация)

## Документация

- Спецификация NodeConfig: `NODE_CONFIG_SPEC.md`
- Архитектура нод: `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- Структура прошивки: `doc_ai/02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md`
- MQTT протокол: `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`

## Статус реализации

### Общие компоненты
- ✅ `mqtt_client` — MVP_DONE
- ✅ `mqtt_manager` — MVP_DONE
- ✅ `wifi_manager` — MVP_DONE
- ✅ `config_storage` — MVP_DONE
- ✅ `config_apply` — MVP_DONE
- ✅ `i2c_bus` — MVP_DONE
- ✅ `node_framework` — MVP_DONE (интегрирован во все ноды)
- ✅ `memory_pool` — MVP_DONE (интегрирован в node_framework)
- ✅ `oled_ui` — MVP_DONE
- ✅ `logging` — MVP_DONE
- ✅ `factory_reset_button` — MVP_DONE

### Драйверы сенсоров
- ✅ `ph_sensor` — MVP_DONE (универсальный драйвер)
- ✅ `trema_ph` — MVP_DONE (Trema pH-сенсор, интегрирован в ph_node)
- ✅ `ec_sensor` — MVP_DONE (универсальный драйвер)
- ✅ `trema_ec` — MVP_DONE (Trema EC-сенсор, интегрирован в ec_node)
- ✅ `sht3x` — MVP_DONE
- ✅ `ina209` — MVP_DONE

### Ноды
- ⚠️ `pump_node` — скелет создан, частичная реализация
- ⚠️ `ph_node` — скелет создан, частичная реализация
- ⚠️ `ec_node` — скелет создан, частичная реализация
- ⚠️ `climate_node` — скелет создан, частичная реализация

