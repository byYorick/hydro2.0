Общие компоненты для всех нод.

## Статус

Компоненты реализуются по мере необходимости. Некоторые компоненты уже реализованы и используются в нодах.

## Реализованные компоненты

### Аппаратные компоненты
- `i2c_bus/` — общий драйвер I²C с mutex'ом ✅
- `sensors/` — драйверы сенсоров:
  - `trema_ph/` — pH-сенсор Trema ✅
  - `trema_ec/` — EC-сенсор Trema ✅
  - `sht3x/` — SHT3x (температура/влажность) ✅
  - `ina209/` — драйвер датчика тока INA209 ✅
- `oled_ui/` — драйвер OLED дисплея для локального UI ✅

### Сетевые компоненты
- `mqtt_manager/` — MQTT менеджер и топик-роутер ✅
- `wifi_manager/` — Wi-Fi менеджер ✅

### Системные компоненты
- `config_storage/` — загрузка NodeConfig из NVS ✅
- `logging/` — система логирования ✅
- `setup_portal/` — портал настройки Wi-Fi ✅
- `heartbeat_task/` — задача публикации heartbeat ✅
- `connection_status/` — получение статуса соединений (WiFi/MQTT/RSSI) ✅

## Планируемые компоненты

### Аппаратные компоненты
- `sensors/` — дополнительные драйверы:
  - CCS811 (CO₂)
  - Датчики освещённости

### Сетевые компоненты
- `mesh_comm/` — ESP-MESH коммуникация (если используется)

### Системные компоненты
- `diagnostics/` — диагностика, метрики, watchdog
- `safe_mode/` — безопасный режим при ошибках

## Документация

- Структура прошивки: `doc_ai/02_HARDWARE_FIRMWARE/FIRMWARE_STRUCTURE.md`
- Стандарты кодирования: `doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md`
- Структура проекта: `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md`
- Архитектура нод: `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`

## Примечание

Компоненты будут созданы по мере реализации нод. Каждый компонент должен иметь:
- `include/<component_name>.h` — публичный API
- `<component_name>.c` — реализацию
- `CMakeLists.txt` — для сборки в ESP-IDF


