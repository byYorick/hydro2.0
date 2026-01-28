# Relay Node

Релейная нода для управления системой накопления и обновления воды в баках через реле.

## Описание

Нода управляет системой накопления и обновления воды в баках через реле:
- 2 насоса: перекачивающий и дренажный
- 2 емкости воды (расширяемо)
- Клапана для переключения магистралей воды
- Все устройства 220В, управляются через реле

Нода использует модульную архитектуру инициализации и интегрирована с `node_framework` для обработки конфигурации, команд и телеметрии.

## Архитектура

### Компоненты

- **relay_driver** - драйвер управления реле (GPIO)
- **node_framework** - унифицированный фреймворк для обработки конфигурации и команд
- **mqtt_manager** - управление MQTT подключением
- **wifi_manager** - управление Wi-Fi подключением
- **config_storage** - хранение конфигурации в NVS
- **oled_ui** - OLED дисплей для отображения статуса (опционально)
- **node_watchdog** - watchdog таймер для защиты от зависаний

### Модульная инициализация

Инициализация разбита на отдельные шаги:

1. **Config Storage** - загрузка конфигурации из NVS
2. **Wi-Fi Manager** - инициализация Wi-Fi
3. **I2C Buses** - инициализация I²C для OLED (если используется)
4. **OLED UI** - инициализация OLED дисплея (опционально)
5. **Relay Driver** - инициализация драйвера реле по встроенной карте каналов (см. `relay_node_hw_map.h`)
6. **MQTT Manager** - инициализация MQTT клиента
7. **Finalization** - запуск MQTT и установка OLED в нормальный режим

## Каналы

### Актуаторы (реле)

Состав каналов фиксирован в прошивке (карта `relay_node_hw_map.h`) и не редактируется через сервер. Примеры каналов:

- `pump_transfer` - перекачивающий насос
- `pump_drain` - дренажный насос
- `valve_tank1_in` - клапан подачи в бак 1
- `valve_tank1_out` - клапан выхода из бака 1
- `valve_tank2_in` - клапан подачи в бак 2
- `valve_tank2_out` - клапан выхода из бака 2
- `valve_main` - главный клапан магистрали (опционально)

## Команды

Все команды обрабатываются через `node_framework` и отправляются на топик:
```
hydro/{gh_uid}/{zone_uid}/{node_id}/{channel}/command
```

### set_relay

Установка состояния реле (OPEN/CLOSED):

```json
{
  "cmd": "set_relay",
  "cmd_id": "cmd-123",
  "params": {
    "state": 1
  }
}
```

**Параметры:**
- `state` (integer): 0 = OPEN (разомкнуто), 1 = CLOSED (замкнуто)
- `cmd_id` (string): уникальный идентификатор команды

**Ответ:**
```json
{
  "status": "ACK",
  "cmd_id": "cmd-123",
  "state": 1
}
```

**Ошибки:**
- `relay_not_found` - канал реле не найден
- `relay_not_initialized` - драйвер реле не инициализирован
- `relay_error` - ошибка установки состояния
- `invalid_parameter` - неверный параметр

### toggle

Переключение состояния реле:

```json
{
  "cmd": "toggle",
  "cmd_id": "cmd-124",
  "params": {}
}
```

**Параметры:**
- `cmd_id` (string): уникальный идентификатор команды

**Ответ:**
```json
{
  "status": "ACK",
  "cmd_id": "cmd-124",
  "state": 1
}
```

**Ошибки:**
- `relay_not_found` - канал реле не найден
- `relay_error` - ошибка переключения

### timed_on

Включение реле на указанное время:

```json
{
  "cmd": "timed_on",
  "cmd_id": "cmd-125",
  "duration_ms": 5000
}
```

**Параметры:**
- `duration_ms` (integer): длительность работы в миллисекундах (1-300000)
- `cmd_id` (string): уникальный идентификатор команды

**Ответ:**
```json
{
  "status": "ACK",
  "cmd_id": "cmd-125"
}
```

**Ошибки:**
- `relay_not_found` - канал реле не найден
- `relay_error` - ошибка включения
- `invalid_parameter` - неверный параметр

**Примечание:** В текущей реализации реле остается включенным до следующей команды. Для полной реализации автоматического выключения требуется система таймеров.

## Обработка дубликатов

`node_framework` (модуль `node_command_handler`) автоматически игнорирует повторные команды с тем же `cmd_id` в течение 60 секунд. При получении дубликата отправляется ответ со статусом `NO_EFFECT`:

```json
{
  "status": "NO_EFFECT",
  "cmd_id": "cmd-123",
  "reason": "duplicate_command"
}
```

## Телеметрия

Нода публикует телеметрию через `node_framework`:

- **STATUS** - статус ноды (публикуется каждые 60 секунд)
- **Heartbeat** - heartbeat сообщения (публикуются через `heartbeat_task` компонент)

### STATUS сообщение

```json
{
  "message_type": "status",
  "node_id": "nd-relay-1",
  "timestamp": 1234567890,
  "wifi_connected": true,
  "mqtt_connected": true,
  "wifi_rssi": -65,
  "relay_channels": [
    {
      "name": "pump_transfer",
      "state": 1
    },
    {
      "name": "pump_drain",
      "state": 0
    }
  ]
}
```

## Конфигурация

Каналы реле полностью зашиты в прошивке (см. `relay_node_hw_map.h`) и не передаются сервером. NodeConfig от сервера содержит только идентификаторы теплицы/зоны, Wi‑Fi/MQTT параметры и прочие общие настройки, без описания каналов.

## Watchdog таймер

Нода использует watchdog таймер (10 секунд) для защиты от зависаний. Все критические задачи автоматически сбрасывают watchdog в цикле:

- `task_status` - сбрасывает watchdog каждую секунду
- `command_processor_task` - сбрасывает watchdog при обработке команд
- `heartbeat_task` - сбрасывает watchdog при публикации heartbeat

## Safe Mode

При переходе в Safe Mode (критическая ошибка) все актуаторы автоматически отключаются через callback `relay_node_disable_actuators_in_safe_mode`.

## FreeRTOS задачи

### task_status

Публикует STATUS сообщения каждые 60 секунд:
- Интервал: 60 секунд
- Stack size: 3072 байт
- Priority: 3

### command_processor_task

Обрабатывает команды из очереди:
- Stack size: 4096 байт
- Priority: 5
- Очередь: до 5 команд

### heartbeat_task

Публикует heartbeat сообщения (через компонент `heartbeat_task`):
- Интервал: 15 секунд
- Stack size: 3072 байт
- Priority: 3

## Значения по умолчанию

Определены в `relay_node_defaults.h`:

- **Node ID**: `nd-relay-1`
- **GH UID**: `gh-1`
- **Zone UID**: `zn-4`
- **MQTT Host**: `192.168.1.10`
- **MQTT Port**: `1883`
- **MQTT Keepalive**: `30` секунд
- **I2C SDA**: `21` (ESP32), `4` (ESP32C3)
- **I2C SCL**: `22` (ESP32), `5` (ESP32C3)
- **OLED Address**: `0x3C`
- **OLED Update Interval**: `1500` мс
- **Setup AP Password**: `hydro2025`

## Требования

- ESP-IDF 5.x
- ESP32 или ESP32C3
- Компоненты:
  - `relay_driver`
  - `node_framework`
  - `mqtt_manager`
  - `wifi_manager`
  - `config_storage`
  - `node_watchdog`
  - `oled_ui` (опционально)

## Сборка

```bash
cd firmware/nodes/relay_node
idf.py build
idf.py flash
idf.py monitor
```

## Разделы памяти

Размер разделов определен в `partitions.csv`:
- `factory`: 1792K (приложение)
- `nvs`: 16K (NVS хранилище)
- `otadata`: 4K (OTA данные)

## Документация

- **Архитектура нод**: `../../../doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
- **MQTT спецификация**: `../../../doc_ai/03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md`
- **Relay Driver**: `firmware/nodes/common/components/relay_driver/include/relay_driver.h`

## Известные ограничения

1. **timed_on команда**: В текущей реализации реле остается включенным до следующей команды. Для полной реализации автоматического выключения требуется система таймеров.

2. **Очередь команд**: Лимит очереди - 5 команд. При переполнении новые команды отклоняются.

3. **Защита от дубликатов**: TTL для cmd_id кэша - 60 секунд. Команды с одинаковым cmd_id игнорируются в течение этого времени.

## Примеры использования

### Управление реле через команды

```bash
# Включить реле
mosquitto_pub -h 192.168.1.10 -t "hydro/gh-1/zn-4/nd-relay-1/pump_transfer/command" \
  -m '{"cmd":"set_relay","cmd_id":"cmd-001","params":{"state":1}}'

# Выключить реле
mosquitto_pub -h 192.168.1.10 -t "hydro/gh-1/zn-4/nd-relay-1/pump_transfer/command" \
  -m '{"cmd":"set_relay","cmd_id":"cmd-002","params":{"state":0}}'

# Переключить реле
mosquitto_pub -h 192.168.1.10 -t "hydro/gh-1/zn-4/nd-relay-1/pump_transfer/command" \
  -m '{"cmd":"toggle","cmd_id":"cmd-003","params":{}}'
```

## Отладка

### Логирование

Нода использует следующие теги для логирования:
- `relay_node` - основной тег приложения
- `relay_node_tasks` - задачи FreeRTOS
- `relay_node_fw` - интеграция с node_framework
- `relay_driver` - драйвер реле

### Проверка статуса

```bash
# Подписка на STATUS сообщения
mosquitto_sub -h 192.168.1.10 -t "hydro/gh-1/zn-4/nd-relay-1/status"
```

### Проверка команд

```bash
# Подписка на ответы команд
mosquitto_sub -h 192.168.1.10 -t "hydro/gh-1/zn-4/nd-relay-1/+/command_response"
```
