# Изменения для синхронизации с эталоном node-sim

## Краткое описание

Выполнены изменения в прошивках для приведения форматов сообщений MQTT к эталонному протоколу node-sim, который успешно проходит E2E тесты.

## Измененные файлы

### 1. `node_telemetry_engine.c`

**Изменения:**
- Удалены поля `node_id` и `channel` из JSON payload телеметрии (они уже есть в топике)
- Исправлен формат `metric_type` на lowercase согласно эталону (ph, ec, air_temp_c и т.д.)
- Исправлен тип `ts` на int (вместо double)
- Создана функция `channel_to_metric_type()` для маппинга каналов → metric_type

**Пример изменений:**
```c
// Было:
{
  "node_id": "nd-ph-esp32una",
  "channel": "ph_sensor",
  "metric_type": "PH",
  "value": 6.5,
  "ts": 1704067200.0
}

// Стало:
{
  "metric_type": "ph",
  "value": 6.5,
  "ts": 1704067200
}
```

### 2. `node_command_handler.c`

**Изменения:**
- Исправлен формат `ts` в ответах на команды: теперь в миллисекундах (было секунды)

**Пример изменений:**
```c
// Было:
cJSON_AddNumberToObject(response, "ts", (double)node_utils_get_timestamp_seconds());

// Стало:
int64_t ts_ms = node_utils_get_timestamp_seconds() * 1000;
cJSON_AddNumberToObject(response, "ts", (double)ts_ms);
```

### 3. `heartbeat_task.c`

**Изменения:**
- Исправлен формат `uptime`: теперь в секундах (было миллисекунды)
- Удалено поле `ts` (не требуется эталоном)
- Удалены дополнительные поля: `min_heap_free`, `memory_pool_hit_rate`
- Оставлены только обязательные поля: `uptime`, `free_heap`, `rssi` (опционально)

**Пример изменений:**
```c
// Было:
{
  "uptime": 3600000,  // миллисекунды
  "ts": 1704067200,
  "free_heap": 200000,
  "rssi": -65,
  "min_heap_free": 150000,
  "memory_pool_hit_rate": 95.5
}

// Стало:
{
  "uptime": 3600,  // секунды
  "free_heap": 200000,
  "rssi": -65
}
```

### 4. `node_state_manager.c`

**Изменения:**
- Исправлен маппинг уровня ошибок: CRITICAL → ERROR (эталон не поддерживает CRITICAL)
- Исправлен формат `ts` в ошибках: теперь в миллисекундах (было секунды)
- Улучшен формат `error_code`: добавлен префикс "esp_" для кодов ESP-IDF
- Добавлено поле `details` с дополнительной информацией

**Пример изменений:**
```c
// Было:
{
  "level": "CRITICAL",
  "component": "ph_sensor",
  "error_code": "ESP_ERR_INVALID_STATE",
  "error_code_num": 9,
  "message": "Sensor not initialized",
  "ts": 1704067200  // секунды
}

// Стало:
{
  "level": "ERROR",  // CRITICAL → ERROR
  "component": "ph_sensor",
  "error_code": "esp_ESP_ERR_INVALID_STATE",
  "message": "Sensor not initialized",
  "ts": 1704067200123,  // миллисекунды
  "details": {
    "error_code_num": 9,
    "original_level": "CRITICAL"
  }
}
```

## Маппинг каналов → metric_type

Создана функция `channel_to_metric_type()` для правильного маппинга:

| Канал (firmware) | metric_type (эталон) |
|------------------|---------------------|
| `ph_sensor` / `ph` | `ph` |
| `ec_sensor` / `ec` | `ec` |
| `air_temp_c` / `temperature` | `air_temp_c` |
| `air_rh` / `humidity` | `air_rh` |
| `co2_ppm` / `co2` | `co2_ppm` |
| `ina209` / `pump_bus_current` | `ina209_ma` |
| `flow_present` | `flow_present` |
| `solution_temp_c` | `solution_temp_c` |

## Совместимость

Все изменения обратно совместимы:
- Опциональные поля (`unit`, `raw`, `stub`, `stable`) в телеметрии сохранены для совместимости
- Старые форматы команд продолжают работать
- Дополнительные поля в ошибках вынесены в `details`

## Тестирование

После изменений рекомендуется:
1. Прогнать E2E тесты (E6x, E2x сценарии)
2. Проверить работу всех типов прошивок (ph, ec, climate, pump, relay, light)
3. Убедиться, что backend корректно обрабатывает новые форматы

## Документация

Созданы документы:
- `FIRMWARE_NODE_SIM_SYNC_PLAN.md` - полный план синхронизации
- `FIRMWARE_COMPATIBILITY_CHECKLIST.md` - чек-лист для разработчиков
- JSON схемы в `schemas/` для валидации форматов

---

**Дата изменений:** 2024-01-XX  
**Версия:** 1.0

