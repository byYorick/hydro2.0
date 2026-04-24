# Pump Node

Нода насосов для управления насосами и мониторинга тока через INA209.

## Используемое оборудование

Нода использует **INA209** для мониторинга тока насосов через I²C:
- Компонент: `ina209`
- I²C адрес: 0x40 (по умолчанию)
- Измерение суммарного тока всех насосов на шине
- Автоматическая проверка тока при запуске насосов

## Описание

Нода управляет насосами через реле/драйверы и контролирует их работу через измерение тока. Каждый насос включается через MOSFET, управляемый через оптопару. INA209 измеряет суммарный ток всех насосов на общей шине питания.

## Каналы

### Сенсоры
- `pump_bus_current` - датчик тока насосов (INA209)

### Актуаторы
- `pump_*` - насосы (настраиваются через NodeConfig)
  - Примеры: `pump_acid`, `pump_base`, `pump_nutrient`, `pump_in` и др.

## Команды

### run_pump
Запуск насоса на указанное время:
```json
{
  "cmd": "run_pump",
  "cmd_id": "cmd-123",
  "duration_ms": 2000
}
```

**Параметры:**
- `duration_ms` (integer): длительность работы в миллисекундах (1-60000)
- `cmd_id` (string): уникальный идентификатор команды

**Ответ:**
- `ACK` - насос успешно запущен (включает health информацию)
- `ERROR` с кодами:
  - `pump_busy` - насос уже работает или в режиме охлаждения
  - `pump_not_found` - канал насоса не найден
  - `current_not_detected` - ток не обнаружен после запуска
  - `overcurrent` - превышен максимальный ток
  - `invalid_parameter` - неверный параметр
  - `missing_duration` - отсутствует параметр duration_ms

**Health информация в ответе:**
При успешном запуске в ответе включается объект `health` с метриками:
- `channel` - имя канала
- `running` - текущее состояние (работает/остановлен)
- `last_run_success` - успешность последнего запуска
- `last_run_ms` - длительность последнего запуска
- `run_count` - общее количество запусков
- `failure_count` - количество ошибок
- `overcurrent_events` - количество событий перегрузки
- `no_current_events` - количество событий отсутствия тока
- `last_start_ts` - timestamp последнего запуска
- `last_stop_ts` - timestamp последней остановки

## Телеметрия

### pump_bus_current
Публикуется периодически (интервал настраивается через NodeConfig):
```json
{
  "value": 1250.5,
  "unit": "mA",
  "ts": 1234567890.123,
  "raw": 1250,
  "stub": false,
  "stable": true
}
```

### pump_health
Публикуется каждые 10 секунд с информацией о состоянии всех насосов и INA209:
```json
{
  "ts": 1234567890.123,
  "channels": [
    {
      "channel": "pump_acid",
      "running": false,
      "last_run_success": true,
      "last_run_ms": 2000,
      "total_run_ms": 50000,
      "run_count": 25,
      "failure_count": 0,
      "overcurrent_events": 0,
      "no_current_events": 0,
      "last_start_ts": 1234567890.0,
      "last_stop_ts": 1234567892.0
    }
  ],
  "ina209": {
    "enabled": true,
    "reading_valid": true,
    "overcurrent": false,
    "undercurrent": false,
    "last_current_ma": 1250.5
  }
}
```

### STATUS
Публикуется каждые 60 секунд согласно DEVICE_NODE_PROTOCOL.md:
```json
{
  "online": true,
  "ip": "192.168.1.100",
  "rssi": -65,
  "fw": "v5.1.2"
}
```

## Структура проекта

- `main/` — основной код:
  - `main.c` — точка входа
  - `pump_node_app.c` — логика приложения (тонкий слой координации)
  - `pump_node_app.h` — заголовочный файл приложения
  - `pump_node_init.c` — координация инициализации, setup mode и callbacks
  - `pump_node_init.h` — заголовочный файл инициализации
  - `pump_node_init_steps.c` — модульные шаги инициализации
  - `pump_node_init_steps.h` — заголовочный файл шагов инициализации
  - `pump_node_defaults.h` — централизованные значения по умолчанию
  - `pump_node_tasks.c` — FreeRTOS задачи (heartbeat, current poll, health, status)
  - `pump_node_framework_integration.c` — интеграция с node_framework
  - `pump_node_framework_integration.h` — заголовочный файл интеграции

## Инициализация

Нода использует модульную систему инициализации с 6 шагами:

1. **Config Storage** - загрузка конфигурации из NVS
2. **Wi-Fi Manager** - инициализация Wi-Fi (setup mode при отсутствии конфига)
3. **I2C Bus** - инициализация I2C шины для INA209
4. **Pump Driver** - инициализация насосов из NodeConfig
5. **MQTT Manager** - инициализация MQTT клиента
6. **Finalization** - запуск MQTT и завершение инициализации

## Защита от дублирующих команд

Нода автоматически игнорирует повторные команды с тем же `cmd_id` в течение 60 секунд. При получении дубликата отправляется ответ со статусом `NO_EFFECT`.

## Очередь команд

Нода поддерживает очередь команд с лимитом 5. Если очередь заполнена, новые команды отклоняются с ошибкой `queue_full`. Команды обрабатываются последовательно в отдельной задаче.

## Watchdog таймер

Нода использует watchdog таймер (10 секунд) для защиты от зависаний. Все критические задачи автоматически сбрасывают watchdog в цикле.

## Safe Mode

При критических ошибках (перегрузка, отсутствие тока) нода может перейти в SAFE_MODE, отключая все насосы для предотвращения повреждений.

## Документация

- Архитектура нод: `doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- Логика нод: `doc_ai/02_HARDWARE_FIRMWARE/NODE_LOGIC_FULL.md`
- INA209 задача: `doc_ai/02_HARDWARE_FIRMWARE/TASK_INA209_PUMP_NODE.md`
- MQTT протокол: `doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- NodeConfig: `firmware/NODE_CONFIG_SPEC.md`
- Device Node Protocol: `doc_ai/02_HARDWARE_FIRMWARE/DEVICE_NODE_PROTOCOL.md`
