/**
 * @file docs/FIRMWARE_NODE_ARCHITECTURE.md
 * @brief Архитектура прошивок нод под Hydro Automation (relay_node + ph_node как примеры).
 *
 * Руководство предназначено для ИИ-ассистентов/инженеров, которые пишут или поддерживают
 * прошивку. Спецификация описывает общие шаблоны работы node_framework, жёстко
 * конфигурируемые каналы и взаимодействие с MQTT/NodeConfig. Базируется на relay_node и ph_node.
 */

# Архитектура прошивок нод Hydro Automation

## Цель

- Обеспечить единую модель для всех узлов (relay/pH/pump/климат), где:
  1. Все конфигурации каналов хранятся в прошивке (firmware-defined).
  2. NodeConfig обрабатывается, но `channels` заменяется встроенным массивом.
  3. MQTT-команды/телеметрия обрабатываются через `node_framework` в согласованном формате.
  4. Документация понятна ИИ-ассистентам: они знают, куда вставлять новые каналы и обработчики.

## Основные компоненты

| Компонент | Описание | Пример |
|-----------|----------|--------|
| `node_framework` | Унифицированный запуск каналов/команд/телеметрии. | `firmware/nodes/*/main/*_framework_integration.c` содержит вызовы `node_framework_init`, `node_config_handler_set_channels_callback` и регистрацию команд. |
| `node_config_handler` | Парсит NodeConfig, пишет `config_storage`, публикует ответы и позволяет `config_apply_mqtt`. | `firmware/nodes/common/components/node_framework/node_config_handler.c`. |
| `config_storage` | Хранит JSON-конфиг. Любой модуль может получить текущий конфиг и перезаписать `channels`. | `firmware/nodes/common/components/config_storage`. |
| `mqtt_manager` | Обслуживает подписки/публикации и вызывает `node_config_handler_process`. | `firmware/nodes/common/components/mqtt_manager`. |
| `node_channel_map` | Массивы `sensor` + `actuator`, заданы в прошивке, используются для `node_config_handler` и `config_report`. | `ph_node_channel_map.c`, `relay_node_hw_map.c`. |

## Принципы обработки `channels`

1. Включить callback `node_config_handler_set_channels_callback`, возвращающий встроенный список каналов.
2. Обернуть вызов `node_config_handler_process` собственным `*_config_handler_wrapper`, который:
   - Парсит пришедший JSON через `cJSON_ParseWithLength`.
   - Удаляет ключ `channels`.
   - Добавляет массив, построенный на основе `relay_node_hw_map.h` или `ph_node_channel_map.c`.
   - Сериализует и передает обратно в `node_config_handler_process`.
3. `config_storage` всегда сохраняет именно встроенные каналы, поэтому сервер видит эталон.
4. `mqtt_manager_register_config_cb` и `node_config_handler_set_mqtt_callbacks` используют эту обёртку.

## Каналы в прошивке

### relay_node (пример реле)

- Описание канала: `relay_node_hw_channel_t` (`name`, `gpio`, `active_high`, `relay_type`).
- `relay_node_build_channels_from_hw_map` возвращает массив `ACTUATOR` c `actuator_type = RELAY`, `metric = RELAY`.
- `relay_driver_resolve_hw_gpio` использует этот массив, чтобы при инициализации драйвера искать GPIO.
- Конфиг от сервера игнорируется по полю `channels`; все ответы от ноды публикуются с этим же списком.

### ph_node (пример комбинированной системы)

- Две категории каналов:
  - Сенсоры `ph_sensor` (metric `PH`) и `solution_temp_c` (`TEMP_SOLUTION`).
  - Актуаторы `ph_doser_up`/`ph_doser_down` типа `PUMP`, включая `safe_limits` и `gpio`.
- Набор параметров (`poll_interval_ms`, `precision`, `GPIO`, `safe_limits`, `ml_per_second`) описан в `ph_node_channel_map.h`.
- Обработчик `ph_node_config_handler_wrapper` заменяет `channels` на `ph_node_build_config_channels` и вызывает оригинальный процессор.
- Команды (`run_pump`, `stop_pump`, `calibrate`) подключаются через `node_command_handler_register`.

### ec_node (текущее состояние)

- Использует встроенный `channel_map` и игнорирует входящие `channels` из MQTT.
- Каналы задаются в `ec_node_channel_map.{c,h}` и сохраняются в `config_storage`.
- `ec_node_config_handler_wrapper` подменяет `channels` и добавляет лимиты тока (`currentMin/currentMax`).
- Каналы по умолчанию:
  - `ec_sensor` (SENSOR, EC, unit mS/cm)
  - `pump_nutrient` (ACTUATOR/PUMP)
- Команды: `run_pump`, `stop_pump`, `calibrate`, `calibrate_ec`, `test_sensor`.
- Телеметрия:
  - `ec_sensor` (metric `EC`, unit `mS/cm`)
  - `TDS` публикуется как `METRIC_TYPE_CUSTOM` (unit `ppm`) при наличии данных.
- EC сенсор использует I2C_BUS_0 (SDA=21, SCL=22 по умолчанию).

### light_node (текущее состояние)

- Использует встроенный `channel_map` и игнорирует входящие `channels` из MQTT.
- Каналы задаются в `light_node_channel_map.{c,h}` и сохраняются в `config_storage`.
- Команда: `test_sensor` (быстрый опрос света).
- Телеметрия:
  - `light` (metric `LIGHT`, unit `lux`, публикация через `METRIC_TYPE_CUSTOM`).

## Команды и телеметрия

1. Все узлы регистрируют команды через `node_command_handler_register`.
2. Телеметрия публикуется с помощью `node_telemetry_engine`, которая сопоставляет имя канала и метрику.
3. `node_state_manager` отражает состояние и safe_mode, чтобы, например, при SAFE_MODE насосы отключались.

## Архитектура тестов (актуатор vs сенсор)

### Общие правила

- Тест запускается с фронта через команду в MQTT (через `/commands` API).
- Нода всегда отвечает в `command_response` и публикует `status` в формате `ACCEPTED/DONE/FAILED`.
- В `FAILED` обязательно заполнить `error_code` и `error_message`.

### Тест актуатора

- Команда зависит от типа актуатора:
  - Насос: `run_pump` с `duration_ms`.
  - Реле: `set_state` с `state` и `duration_ms`.
  - Клапан: `set_relay` с `state` и `duration_ms`.
- Ответы:
  - Сразу `ACCEPTED` (если команда валидна и запуск успешен).
  - После завершения — `DONE` или `FAILED` (по факту исполнения).
- Для насосов pH/EC обязательный параметр: `current_ma` в ответе (если недоступен — `FAILED`).
- DONE/FAILED публикуется из отложенного события (таймер/очередь), чтобы фронт видел этапы “Выполнение → Выполнено”.

### Тест сенсора

- Единая команда: `test_sensor` без `duration_ms`.
- Нода делает единичный опрос и сразу возвращает `DONE` с измерением:
  - `data.value`, `data.unit`, `data.metric_type`, `data.raw_value`, `data.stable`.
- Ошибка чтения/инициализации — `FAILED` с детальным `error_code`/`error_message`.
- Если сенсор не реализован в прошивке, ответ: `FAILED` с `sensor_unavailable`.

## Что уже реализовано (актуальный статус)

### Жёсткие каналы в прошивке

- `relay_node` и `ph_node` всегда возвращают встроенный массив каналов.
- MQTT `channels` игнорируются: прошивка удаляет `channels` из входящего конфига и подставляет встроенные.
- Каналы определяются в:
  - `relay_node_hw_map.{c,h}`
  - `ph_node_channel_map.{c,h}`
- `config_storage` сохраняет именно этот массив, поэтому сервер видит только эталонные каналы из прошивки.
- Аналогично `ec_node` и `light_node` используют:
  - `ec_node_channel_map.{c,h}`
  - `light_node_channel_map.{c,h}`

### pH‑нода: каналы и GPIO

- Каналы pH‑ноды сведены к минимальному составу:
  - `ph_sensor` (SENSOR, PH, unit pH)
  - `solution_temp_c` (SENSOR, TEMP_SOLUTION, unit C)
  - `ph_doser_up` (ACTUATOR/PUMP)
  - `ph_doser_down` (ACTUATOR/PUMP)
- GPIO дозаторов:
  - `ph_doser_up` = GPIO 12
  - `ph_doser_down` = GPIO 13

### Тесты: командный протокол

- Для актуаторов реализован двухэтапный ответ: `ACCEPTED` → `DONE/FAILED`.
- Для сенсоров реализована команда `test_sensor` (быстрый опрос и ответ `DONE` с измерением).
- Для насосов обязателен параметр `current_ma` в ответе; если ток недоступен — `FAILED`.

### Очередь насосов (без параллельного запуска)

- Если один насос активен, следующий `run_pump` ставится в очередь (FIFO).
- Команда в очереди получает `ACCEPTED` с `data.queued=true`.
- При cooldown канала добавляется `data.cooldown_ms`.
- Следующий насос запускается только после `DONE`/`stop_pump`.
- Одновременно два насоса не включаются.
- Ошибки очереди:
  - `pump_queue_full` — очередь переполнена.
  - `pump_busy` — насос уже запущен (блокировка).
  - `cooldown_active` — канал в cooldown.

### Ошибки и алерты

- Ошибки ноды публикуются в MQTT `/error` и попадают в фронтовые алерты.
- I2C‑спам подавлен на уровне драйвера: остаётся одно сообщение верхнего уровня о проблеме датчика pH.

### Контракт HMAC

- Команды с `sig` без `ts` считаются ошибкой.
- Если `ts` достраивается — подпись пересчитывается.

## Настройка новых нод

1. Для новой ноды создать `*_channel_map.c/.h` (или аналог) с описанием каналов.
2. В `*_framework_integration.c`:
   - Добавить helper-обёртку, копирующую и заменяющую `channels`.
   - Зарегистрировать `node_config_handler_set_channels_callback`.
   - Подключить обработчики команд и telemetries.
3. Убедиться, что `config_storage` сохраняет JSON с прошивочными каналами (протестировать через `config_storage_get_json`).

## Указания ИИ-ассистентам

1. При внесении изменений каналы меняются в `*_channel_map.c`/`relay_node_hw_map.c`, не в Laravel.
2. NodeConfig всегда поступает, но прошивка игнорирует секцию `channels`; нужно опираться на встроенный массив.
3. Используйте существующие helper-обёртки (`ph_node_config_handler_wrapper`/`relay_node_config_handler_wrapper`) как шаблон.
4. Если добавляете новый тип узла, копируйте структуру:
   - `node_framework_init` с `node_config_handler_set_channels_callback`.
   - Сериализация/десериализация `cJSON` перед `node_config_handler_process`.
   - Массив `channels` жестко задаётся в прошивке и публикуется обратно на MQTT.

## Ссылки

- Пример конфигурации серверной стороны: `backend/laravel/app/Services/NodeConfigService.php`.
- Управление MQTT: `firmware/nodes/common/components/mqtt_manager/mqtt_manager.c`.
- Сборка каналов:
  - `firmware/nodes/ph_node/main/ph_node_channel_map.c`
  - `firmware/nodes/relay_node/main/relay_node_hw_map.c`
