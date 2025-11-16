# Задача: драйвер INA209 и логика контроля насосов по суммарному току на ноде насосов

## Контекст

- Компонент: прошивка **ноды насосов** (ESP32, C, ESP-IDF).
- Архитектура узла и логика команд:
  - `02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md`
  - `02_HARDWARE_FIRMWARE/NODE_LOGIC_FULL.md`
  - `02_HARDWARE_FIRMWARE/DEVICE_NODE_PROTOCOL.md`
- Аппаратная спецификация насосов и схемы:
  - `02_HARDWARE_FIRMWARE/HARDWARE_ARCH_FULL.md` (раздел 8.2)
- Каналы и их типы:
  - `02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md` (актуаторы `pump_*` и сенсор `pump_bus_current`)
- MQTT и ответы на команды:
  - `03_TRANSPORT_MQTT/MQTT_SPEC_FULL.md` (особенно раздел 8. Command Response)

Аппаратная схема ноды:

- Все насосы имеют **общий плюс питания**.
- Минус каждого насоса коммутируется через **MOSFET (low-side)**.
- MOSFET управляется через **оптопару** от ESP32.
- В разрыв общего плюса насосов включён **один датчик тока INA209** (через шунт).
- INA209 подключён по **I²C** к ESP32.

Цель: реализовать драйвер INA209 и интегрировать его в логику обработки команд к насосам так,
чтобы узел мог по **суммарному току шины насосов** проверять, реально ли насосы включились,
и формировать корректные `command_response` (`ACK` / `ERROR`).

---

## Текущая ситуация

- Конфигурация ноды (NodeConfig) уже концептуально определена в архитектуре (есть пример JSON),
  включая:
  - секцию `ina209` (i2c_bus, addr, shunt_res_milliohm и т.п.);
  - секцию `pump_safety` (stabilization_delay_ms, min_bus_current_on_ma, max_bus_current_on_ma и т.д.);
  - список каналов `pump_*` и сенсорный канал `pump_bus_current`.
- В логике узла описан общий алгоритм обработки команд и `command_response`,
  а также high-level псевдокод для проверки тока насосов.
- Реальной C-имплементации:
  - драйвера INA209;
  - чтения суммарного тока;
  - интеграции в ActuatorEngine для pump-каналов —
  **ещё нет**.

---

## Цель

Сделать так, чтобы **нода насосов**:

1. Умела инициализировать INA209 по данным из NodeConfig.
2. Периодически публиковала телеметрию `pump_bus_current` (mA).
3. При получении команд к насосам (`pump_acid`, `pump_base`, `pump_nutrient`, `pump_in`):
   - включала соответствующий MOSFET;
   - ждала stabilization_delay_ms;
   - измеряла `bus_current_ma` через INA209;
   - сравнивала с `min_bus_current_on_ma` и `max_bus_current_on_ma`;
   - отсылала `command_response` c `ACK` или `ERROR` (`current_not_detected` / `overcurrent`);
   - при необходимости отключала насосы и переходила в SAFE_MODE при частых ошибках.

---

## Входные данные

1. **NodeConfig (пример JSON)** — на него нужно ориентироваться при дизайне структур:

   ```json
   {
     "node_id": "nd-pump-1",
     "version": 1,
     "ina209": {
       "i2c_bus": 0,
       "scl_gpio": 22,
       "sda_gpio": 21,
       "addr": "0x40",
       "shunt_res_milliohm": 10,
       "max_expected_ma": 1000
     },
     "pump_safety": {
       "stabilization_delay_ms": 200,
       "min_bus_current_on_ma": 80,
       "max_bus_current_on_ma": 800,
       "error_threshold_count": 3,
       "error_threshold_window_s": 300,
       "safe_mode_timeout_s": 600
     },
     "channels": [
       {
         "name": "pump_acid",
         "type": "ACTUATOR",
         "actuator_type": "PUMP",
         "gpio": 25,
         "safe_limits": {
           "max_duration_ms": 30000,
           "min_off_ms": 5000,
           "max_daily_ml": 300,
           "cooldown_after_error_ms": 60000
         }
       },
       {
         "name": "pump_base",
         "type": "ACTUATOR",
         "actuator_type": "PUMP",
         "gpio": 26,
         "safe_limits": {
           "max_duration_ms": 30000,
           "min_off_ms": 5000,
           "max_daily_ml": 300,
           "cooldown_after_error_ms": 60000
         }
       },
       {
         "name": "pump_nutrient",
         "type": "ACTUATOR",
         "actuator_type": "PUMP",
         "gpio": 27,
         "safe_limits": {
           "max_duration_ms": 60000,
           "min_off_ms": 5000,
           "max_daily_ml": 2000,
           "cooldown_after_error_ms": 60000
         }
       },
       {
         "name": "pump_in",
         "type": "ACTUATOR",
         "actuator_type": "PUMP",
         "gpio": 32,
         "safe_limits": {
           "max_duration_ms": 120000,
           "min_off_ms": 10000,
           "cooldown_after_error_ms": 60000
         }
       },
       {
         "name": "pump_bus_current",
         "type": "SENSOR",
         "metric": "CURRENT_MA",
         "poll_interval_ms": 5000
       }
     ]
   }
   ```

2. **Целевой стек:**
   - ESP32 (допустить ESP32-S3 / ESP32-S2);
   - ESP-IDF 5.x;
   - FreeRTOS.

3. **Структуры и конвенции** — соблюдать стиль и подход из:
   - `02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md`
   - `DEV_CONVENTIONS.md`

---

## Ожидаемый результат

Нужно выдать **полный C-код** для следующих модулей (пути примерные, но логичные):

1. `node_pump/drivers/ina209_driver.h`
2. `node_pump/drivers/ina209_driver.c`
3. `node_pump/logic/pump_safety.h`
4. `node_pump/logic/pump_safety.c`
5. При необходимости — правки в:
   - `node_pump/logic/command_handler.c` (или аналогичный файл обработчика команд),
   - `node_pump/logic/telemetry_publisher.c` (для отправки `pump_bus_current`).

### 1) `ina209_driver.[ch]`

Функциональность:

- Инициализация:

  ```c
  esp_err_t ina209_init(const ina209_config_t *cfg);
  ```

- Чтение тока (mA) по шине насосов:

  ```c
  esp_err_t ina209_read_bus_current(float *current_ma);
  ```

Требования:

- Использовать стандартный I2C-драйвер ESP-IDF (`i2c_driver_install`, `i2c_cmd_link_create` и т.п.).
- Учесть параметры шунта (`shunt_res_milliohm`) и масштабирование тока.
- Обрабатывать ошибки I2C и возвращать `esp_err_t`.

### 2) `pump_safety.[ch]`

Функциональность:

- Инициализация конфигурации безопасности:

  ```c
  void pump_safety_init(const pump_safety_config_t *cfg);
  ```

- Проверка тока при включении насоса:

  ```c
  typedef enum {
      PUMP_SAFETY_OK = 0,
      PUMP_SAFETY_ERR_NO_CURRENT,
      PUMP_SAFETY_ERR_OVERCURRENT
  } pump_safety_result_t;

  pump_safety_result_t pump_safety_check_after_on(
      const char *channel_name,
      const pump_safety_config_t *cfg,
      float bus_current_ma
  );
  ```

- Учёт ошибок и переход в SAFE_MODE:

  ```c
  bool pump_safety_register_error_and_check_safe_mode(
      const char *channel_name,
      pump_safety_result_t last_result,
      uint32_t now_ts_s
  );
  ```

Где:

- `true` означает, что ноду/насосы нужно перевести в SAFE_MODE
  (выключить все насосы и блокировать новые команды до тайм-аута).

### 3) Интеграция в обработчик команд и телеметрию

- В обработчике команд для каналов `pump_*` нужно:

  - включать MOSFET;
  - ждать `stabilization_delay_ms` (с учётом FreeRTOS `vTaskDelay`);
  - вызывать `ina209_read_bus_current`;
  - кормить результат в `pump_safety_check_after_on`;
  - в зависимости от результата:
    - отправлять `command_response` (`ACK` / `ERROR` + `error_code`);
    - при серии ошибок — вызывать `pump_safety_register_error_and_check_safe_mode`
      и при необходимости отключать все насосы и выставлять SAFE_MODE.

- Для канала `pump_bus_current`:

  - реализовать периодический опрос INA209 по `poll_interval_ms`;
  - публиковать MQTT-telemetry в формате:

    ```json
    {
      "node_id": "nd-pump-1",
      "channel": "pump_bus_current",
      "metric_type": "CURRENT_MA",
      "value": 220.5,
      "timestamp": 1710005555
    }
    ```

---

## Ограничения и требования

1. **Соблюдать `DEV_CONVENTIONS.md` и `ESP32_C_CODING_STANDARDS.md`.**
2. Не использовать динамическое выделение памяти (`malloc`) в “горячем” пути исполнения команд к насосам.
3. Ошибки I2C и INA209 должны логироваться через `ESP_LOGE` с понятными тегами (`"INA209"`, `"PUMP_SAFETY"`).
4. Не менять публичные интерфейсы вне указанных файлов без явной необходимости
   (если нужно — описать изменения в резюме).
5. Код должен быть самодостаточен: можно компилировать для отдельной прошивки ноды насосов
   без обращения к внешним неописанным функциям (кроме базовых ESP-IDF).

---

## Формат ответа

1. **Краткое резюме** (пару пунктов: что сделано, какие файлы добавлены/изменены).
2. **Полный код файлов** в отдельных блоках с указанием пути, например:

   ```c
   // path: node_pump/drivers/ina209_driver.h
   ...полный код...
   ```

   ```c
   // path: node_pump/drivers/ina209_driver.c
   ...полный код...
   ```

   и т.д. для всех затронутых файлов.

3. При необходимости — **список TODO**/идей для дальнейшего улучшения
   (например, калибровка INA209, более сложные профили тока для разных насосов),
   но основной код должен быть полностью рабочим без заглушек.
