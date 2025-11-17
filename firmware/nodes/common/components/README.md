Общие компоненты для всех нод (PLANNED).

## Статус

Все компоненты находятся в стадии планирования. Реализация будет выполнена согласно документации.

## Планируемые компоненты

Согласно `doc_ai/01_SYSTEM/01_PROJECT_STRUCTURE_PROD.md` и `doc_ai/02_HARDWARE_FIRMWARE/`:

### Аппаратные компоненты
- `i2c_bus/` — общий драйвер I²C с mutex'ом
- `ina209/` — драйвер датчика тока INA209 (для pump_node)
- `oled_display/` — драйвер OLED дисплея для локального UI
- `sensors/` — драйверы сенсоров:
  - pH-сенсор
  - EC-сенсор
  - SHT3x (температура/влажность)
  - CCS811 (CO₂)
  - Датчики освещённости

### Сетевые компоненты
- `mesh_comm/` — ESP-MESH коммуникация (если используется)
- `mqtt_client/` — MQTT клиент и топик-роутер

### Системные компоненты
- `config_loader/` — загрузка NodeConfig из NVS/JSON
- `logging/` — система логирования
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


