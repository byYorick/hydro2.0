# FIRMWARE_STRUCTURE.md
# Полная структура прошивки 2.0 для ESP32

Документ описывает архитектуру прошивки на C (ESP-IDF, C99) для ESP32/ESP32-S3,
используемую в узлах системы 2.0.

Цели:

- разделить код на понятные модули;
- обеспечить предсказуемую работу FreeRTOS-задач;
- упростить работу ИИ-агентов с кодом.

**Дата обновления:** 2026-05-28 (расширен фактический список common-компонентов и runtime tasks).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

## 1. Общая архитектура

Основные подсистемы прошивки:

1. **Core / RTOS** — инициализация, задачи, очереди, таймеры.
2. **Wi-Fi & MQTT** — подключение к сети и брокеру.
3. **Config (NVS)** — хранение конфигурации узла.
4. **Sensors** — драйверы датчиков (pH, EC, SHT, освещённость и т.п.).
5. **Actuators** — управление насосами, реле, вентиляторами, светом.
6. **Telemetry Engine** — формирование и отправка телеметрии.
7. **Command Engine** — обработка команд из MQTT.
8. **OTA (target)** — подсистема обновления прошивки (внедряется поэтапно).
9. **Diagnostics / Logging** — диагностика и статусы.
10. **OLED UI** — локальный интерфейс (см. `NODE_OLED_UI_SPEC.md`).

Пример структуры каталога для ноды:

```text
firmware/nodes/ph_node/
├─ main/
│  ├─ main.c
│  ├─ ph_node_app.c
│  └─ ph_node_tasks.c
├─ CMakeLists.txt
├─ sdkconfig.defaults
└─ Kconfig

firmware/nodes/common/components/  # Общие компоненты для всех нод
├─ node_framework/   # Унифицированный каркас ноды (FSM, state, telemetry/command engine,
│                    # config_handler, safe-mode, watchdog integration)
├─ node_utils/       # Утилиты: bootstrap network stack, time sync, ts helpers, log helpers
├─ node_watchdog/    # Task watchdog wrapper
├─ config_storage/   # NVS persistence NodeConfig (load/save/validate)
├─ config_apply/     # Применение конфига к runtime (channels, wifi, mqtt apply hooks)
├─ mqtt_manager/     # MQTT клиент + topic router (canonical runtime path)
├─ mqtt_client/      # Низкоуровневая обёртка над esp-mqtt (legacy/internal)
├─ wifi_manager/     # Wi-Fi подключение и переподключение
├─ setup_portal/     # Setup portal для provisioning (captive portal)
├─ heartbeat_task/   # Периодическая публикация heartbeat
├─ connection_status/# Агрегатор состояния (wifi/mqtt/time_sync)
├─ diagnostics/      # Engineering diagnostics publish
├─ factory_reset_button/  # Hardware factory reset (long-press)
├─ i2c_bus/          # I²C шина (mutex, recover, кэш handles)
├─ i2c_cache/        # Device handle cache
├─ memory_pool/      # Memory pool для горячих путей (no malloc)
├─ logging/          # Система логирования (ESP_LOG обёртка с TAG conventions)
├─ oled_ui/          # OLED UI
├─ sensors/          # Драйверы сенсоров
│  ├─ ph_sensor/
│  ├─ trema_ph/
│  ├─ ec_sensor/
│  ├─ trema_ec/
│  ├─ sht3x/
│  ├─ ccs811/        # CO2 sensor
│  └─ ina209/        # Pump current sensor
├─ pump_driver/      # Driver: pump on/off + current monitoring
├─ relay_driver/     # Driver: relay control с interlock
├─ pwm_driver/       # Driver: PWM channel (light/heater dim)
└─ ws2811_driver/    # Driver: addressable LED strip
```

Документация конкретного компонента — в его `README.md` (например, `firmware/nodes/common/components/i2c_bus/README.md`).

---

## 2. FreeRTOS-задачи

В актуальной реализации задачи запускаются `node_framework` через bootstrap-pipeline (`node_framework_start_*`). Каждая нода вызывает общий `node_utils_bootstrap_network_stack()` из `app_main()` и затем `node_framework_*` для подъёма доменных задач.

Канонический набор задач:

- **`task_main`** / `node_framework_main` — координация, FSM узла.
- **`task_wifi`** / `wifi_manager_task` — управление подключением Wi-Fi.
- **`task_mqtt`** / `mqtt_manager_task` — обработка входящих и исходящих MQTT-сообщений.
- **`task_sensors`** — опрос датчиков (per-channel polling).
- **`task_actuators`** — управление актуаторами по событиям.
- **`heartbeat_task`** — периодическая публикация heartbeat (`uptime`, `free_heap`, `rssi`).
- **`node_watchdog`** task — глобальный watchdog wrapper, регистрирует все долгоживущие задачи.
- **`task_ui`** / `oled_ui_task` — обновление OLED и обработка factory reset кнопки.
- **`task_ota`** — OTA-обновления (status: planned, реализация per-node).

Между задачами используются очереди/event groups:

- `queue_commands` — команды от MQTT → actuators (через `node_command_handler`);
- `queue_telemetry` — данные от sensors → mqtt (через `telemetry_engine`);
- `queue_ui_events` — события UI.
- `event_group_connection` — wifi/mqtt/time_sync bits для синхронизации старта публикаций.

---

## 3. Конфигурация узла (NodeConfig)

NodeConfig хранится в NVS и включает:

- `node_id` — UID узла;
- `zone_uid` — привязка к зоне;
- `gh_uid` — теплица;
- список каналов и их типы;
- параметры Wi-Fi (SSID, пароль или SmartConfig);
- параметры MQTT (host, порт, client_id);
- флаги калибровки (pH, EC).

Компоненты `config_storage` + `node_config_handler`:

- читает конфиг при старте;
- предоставляет API для применения/обновления конфигурации по MQTT `.../config`.

---

## 4. Telemetry Engine

Задачи:

- по расписанию опрашивать датчики;
- формировать сообщения телеметрии;
- отправлять их через MQTT.

Период опроса зависит от типа узла и задаётся конфигом.

---

## 5. Command Engine

Реализация: `firmware/nodes/common/components/node_framework/node_command_handler.c`.

Задачи:

- подписка на `hydro/{gh}/{zone}/{node}/+/command` (wildcard) и `hydro/{gh}/{zone}/{node}/system/command` (отдельная подписка, см. `MQTT_SPEC_FULL.md` §7.5.6);
- парсинг JSON-payload;
- проверка timestamp (`HMAC_TIMESTAMP_TOLERANCE_SEC=10`) и HMAC-подписи (через `node_secret`);
- дедуп по `cmd_id` (кэш final status);
- маршрутизация к зарегистрированным channel handlers;
- публикация `command_response` (с `ts` в **миллисекундах**).

Команды не должны содержать тяжёлой логики — только простые действия. Набор конкретных команд зависит от типа ноды и зарегистрированных handler'ов. Канонические команды (см. `NODE_CHANNELS_REFERENCE.md` и `MQTT_SPEC_FULL.md` §7):

- `run_pump` (timed pump on);
- `dose` (peristaltic pump, `params.ml`);
- `set_relay` (вкл/выкл; для IRR — также timed-start с `timeout_ms+stage`);
- `set_pwm` (climate/light dimming);
- `set_position` (drive/roof vent, `params.position_pct`);
- `calibrate` (sensor calibration, stage-based);
- `test_sensor` (разовое чтение);
- `restart` / `reboot` (требуется для всех нод);
- `state` (требуется для всех нод; для `irrig` возвращает `details.snapshot` с дискретными состояниями);
- `activate_sensor_mode` / `deactivate_sensor_mode` (system-level, для pH/EC нод).

Дополнительно firmware принимает: `report_config`, `calibrate_ph` / `calibrate_ec` aliases, `exit_safe_mode`, `get_diagnostics`, `toggle` (relay) — это node-specific extensions, не являются universal contract.

---

## 6. OTA Engine

- `OTA_UPDATE_PROTOCOL.md` задаёт целевой контракт.
- В текущем production baseline OTA-пайплайн не включён как активный runtime-функционал для всех нод.
- Перед боевым включением OTA требуется отдельная реализация, HIL/e2e-валидация и release-checklist.

---

## 7. OLED UI

- Работает как отдельная задача (`task_ui`).
- Не блокирует работу сети.
- Все данные берёт из общей модели состояния, а не напрямую из сенсоров.

---

## 8. Правила для ИИ-агентов

1. Не выносить бизнес-логику (рецепты, агрономические решения) в прошивку.
2. Соблюдать модульность и не смешивать слои (сетевой код не должен лазить в датчики напрямую).
3. Любые изменения в протоколах/форматах MQTT должны быть согласованы с `../03_TRANSPORT_MQTT/MQTT_NAMESPACE.md`.

Этот документ — основной ориентир при развитии прошивки узлов ESP32 в рамках версии 2.0.
