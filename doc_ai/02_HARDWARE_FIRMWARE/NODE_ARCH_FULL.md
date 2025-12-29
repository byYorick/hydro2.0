# NODE_ARCH_FULL.md
# Полная архитектура узлов ESP32 2.0 (Детальный документ)

Этот документ описывает полноценную архитектуру **узлов ESP32 (Device Nodes)** в системе 2.0:
структура прошивки, модули, каналы, протоколы, безопасность, обновление, обработка команд,
генерация телеметрии, хранение конфигурации, подключение по Wi‑Fi и MQTT.

---

# 1. Цели и принципы архитектуры узлов

Узел ESP32 — это **минималистичное, предсказуемое, детерминированное устройство**, которое:

- не принимает агрономических решений,
- не содержит бизнес-логики,
- не рассчитывает pH/EC/климат,
- является только **источником телеметрии** и **исполнителем команд**.

Backend принимает решения → узлы исполняют.

Принципы:
1. Узел никогда не работает автономно (кроме safety-таймеров).
2. Логика: минимальная, чёткая, несложная.
3. Узел полностью конфигурируется через NodeConfig.
4. Всё общение через MQTT.
5. Узел сам по себе — модуль каналов:
 - SensorChannel
 - ActuatorChannel

---

# 2. Архитектура прошивки узла (Firmware Structure)

Прошивка построена на ESP-IDF framework и использует структуру компонентов.

## 2.1. Структура проекта ESP-IDF

Каждая нода — отдельный ESP-IDF проект:

```
firmware/nodes/{node_type}/
├─ main/
│  ├─ main.c                    # Точка входа приложения
│  ├─ {node_type}_app.c         # Основная логика ноды
│  ├─ {node_type}_app.h
│  └─ CMakeLists.txt            # Конфигурация компонента main
├─ components/                  # Специфические компоненты ноды (опционально)
├─ CMakeLists.txt               # Корневой CMakeLists проекта
├─ sdkconfig.defaults           # Конфигурация ESP-IDF по умолчанию
├─ partitions.csv               # Таблица разделов флеш-памяти
└─ README.md
```

## 2.2. Общие компоненты

Все общие компоненты находятся в `firmware/nodes/common/components/`:

```
firmware/nodes/common/components/
├─ mqtt_manager/                # MQTT менеджер и топик-роутер
├─ wifi_manager/                # Wi-Fi менеджер
├─ config_storage/              # Хранение NodeConfig в NVS
├─ node_framework/              # Унифицированный фреймворк для всех нод
│  ├─ node_telemetry_engine.c   # Движок публикации телеметрии
│  ├─ node_command_handler.c    # Обработчик команд
│  └─ node_state_manager.c      # Управление состоянием (Safe Mode)
├─ heartbeat_task/              # Задача публикации heartbeat
├─ sensors/                     # Драйверы сенсоров
│  ├─ ph_sensor/                # Универсальный драйвер pH
│  ├─ trema_ph/                 # Trema pH-сенсор (iarduino)
│  ├─ ec_sensor/                # Универсальный драйвер EC
│  ├─ trema_ec/                 # Trema EC-сенсор (iarduino)
│  ├─ sht3x/                    # Температура/влажность
│  └─ ina209/                   # Датчик тока
├─ i2c_bus/                     # I²C шина
├─ oled_ui/                     # OLED дисплей UI
├─ logging/                     # Система логирования
└─ ...
```

## 2.3. Архитектура компонентов

Каждый компонент — это ESP-IDF компонент со структурой:

```
component_name/
├─ include/
│  └─ component_name.h          # Публичный API компонента
├─ component_name.c             # Реализация компонента
├─ CMakeLists.txt               # Конфигурация компонента
└─ README.md                    # Документация компонента
```

## 2.4. Основные модули

- **node_framework** — унифицированный фреймворк:
  - Обработка NodeConfig
  - Обработка команд MQTT
  - Публикация телеметрии
  - Управление состоянием (Safe Mode)
  - Watchdog

- **mqtt_manager** — MQTT клиент и менеджер:
  - Подключение к брокеру
  - Публикация сообщений
  - Подписка на топики
  - Обработка LWT

- **config_storage** — хранение конфигурации:
  - Сохранение NodeConfig в NVS
  - Загрузка при старте
  - Валидация конфигурации

- **telemetry_engine** — движок телеметрии:
  - Батчинг сообщений
  - Форматирование JSON
  - Публикация в MQTT

---

# 3. Жизненный цикл узла

1. **Boot**
2. Загрузка NodeConfig из NVS
3. Подключение к Wi-Fi
4. Подключение к MQTT
5. Публикация STATUS ONLINE
6. Подписка на:
 - `config`
 - `command`
7. Запуск циклов:
 - Sensor Polling
 - Telemetry Push
 - Heartbeat
8. Ожидание команд

---

# 4. NodeConfig

NodeConfig полностью формируется на backend.

## 4.1. Формат
```json
{
 "node_id": "nd-ph-1",
 "version": 3,
 "type": "ph_node",
 "gh_uid": "gh-1",
 "zone_uid": "zn-3",
 "channels": [
 {
 "name": "ph_sensor",
 "type": "SENSOR",
 "metric": "PH",
 "poll_interval_ms": 3000
 },
 {
 "name": "pump_acid",
 "type": "ACTUATOR",
 "actuator_type": "PUMP",
 "safe_limits": {
 "max_duration_ms": 5000,
 "min_off_ms": 3000
 }
 }
 ],
 "wifi": {
 "ssid": "FarmWiFi",
 "pass": "12345678"
 },
 "mqtt": {
 "host": "192.168.1.50",
 "port": 1883,
 "keepalive": 30
 }
}
```

**Важные поля:**
- `gh_uid` — уникальный идентификатор теплицы (обязательное поле с версии 3)
- `zone_uid` — уникальный идентификатор зоны (обязательное поле с версии 3)
- Используются в MQTT топиках для маршрутизации сообщений

## 4.2. Применение
- сохраняется в NVS,
- подтверждается публикацией `config_report`,
- вызывает перезапуск сенсорных циклов.

---

# 5. Каналы узла (Node Channels)

## 5.1. SensorChannel
Содержит:
- имя
- тип метрики (PH, EC, TEMP_AIR, HUMIDITY…)
- период измерения
- драйвер сенсора
- фильтрацию (усреднение)

### Алгоритм:
```
каждые poll_interval:
 read sensor
 apply smoothing
 post telemetry
```

---

## 5.2. ActuatorChannel
Типы:
- PUMP
- VALVE
- FAN
- LIGHT
- PWM
- HEATER
- RELAY

Поддерживает:
- безопасные лимиты
- сквозной контроль состояния
- command → выполнение → command_response

---

# 6. Telemetry

## 6.1. Формат
```json
{
 "metric_type": "ph",
 "value": 5.82,
 "ts": 1710001234
}
```

**Обязательные поля:**
- `metric_type` (string, lowercase) — тип метрики: `ph`, `ec`, `air_temp_c`, `air_rh` и т.д.
- `value` (number) — значение метрики
- `ts` (integer) — UTC timestamp в секундах (Unix timestamp)

**Опциональные поля:**
- `unit` (string) — единица измерения
- `raw` (integer) — сырое значение сенсора
- `stub` (boolean) — флаг симулированного значения
- `stable` (boolean) — флаг стабильности значения

> **Важно:** Поля `node_id` и `channel` **не включаются** в JSON payload, так как они уже присутствуют в структуре MQTT топика (`hydro/{gh}/{zone}/{node}/{channel}/telemetry`). Формат соответствует эталону node-sim.

## 6.2. Отправка
Топик:
```
hydro/{gh}/{zone}/{node}/{channel}/telemetry
```

Частота отправки:
- зависит от сенсора,
- регулируется backend,
- всегда QoS=1.

---

# 7. Команды (Command Execution)

## 7.1. Формат
```json
{
 "cmd_id": "cmd-39494",
 "cmd": "run_pump",
 "duration_ms": 2000
}
```

## 7.2. Поддерживаемые команды
- run_pump 
- set_pwm 
- set_relay 
- calibrate 
- reboot 
- measure_now 

## 7.3. Ответ узла
```json
{
 "cmd_id": "cmd-39494",
 "status": "ACK",
 "ts": 1710001234
}
```

---

# 8. Status и LWT

## 8.1. При подключении
```json
{
 "status": "ONLINE",
 "ts": 1710001555
}
```

## 8.2. LWT (offline)
```
payload: "offline"
```

---

# 9. Heartbeat

Период: раз в 15 секунд.

```json
{
 "uptime": 55199,
 "free_heap": 102320,
 "rssi": -55
}
```

---

# 10. Безопасность ноды и драйверы актуаторов

## 10.1. Защита узла

Узел должен иметь защиту:

- max duration для насосов
- min off time
- предотвращение двойного запуска
- защита от зависания команд
- защита от дублирующих MQTT сообщений
- watchdog таймер

## 10.2. Relay Driver

**Компонент:** `firmware/nodes/common/components/relay_driver/`

Абстракция для управления реле:

- Поддержка нормально-замкнутых (NC) и нормально-разомкнутых (NO) реле
- Управление через GPIO с учётом `active_low`
- Fail-safe режим для NC-реле (при потере питания реле замкнуто)
- Инициализация из NodeConfig
- Используется в `climate_node` для управления реле

**API:**
- `relay_driver_init_from_config()` — инициализация из NodeConfig
- `relay_driver_set_state(channel, state)` — установка состояния (OPEN/CLOSED)
- `relay_driver_get_state(channel)` — получение текущего состояния

## 10.3. Pump Driver

**Компонент:** `firmware/nodes/common/components/pump_driver/`

Абстракция для управления насосами:

- Интеграция с INA209 для мониторинга тока
- Проверка overcurrent и no-flow при запуске насоса
- Поддержка управления через relay_driver (для NC-реле)
- Безопасные лимиты (max_duration_ms, min_off_time_ms)
- Дозирование по объёму (ml_per_second)
- Используется в `ec_node` и `pump_node`

**API:**
- `pump_driver_init_from_config()` — инициализация из NodeConfig
- `pump_driver_run(channel, duration_ms)` — запуск насоса на заданное время
- `pump_driver_dose(channel, dose_ml)` — дозирование по объёму
- `pump_driver_set_ina209_config(config)` — настройка INA209 для проверки тока

**Интеграция INA209:**
- Проверка тока после запуска насоса (стабилизация 200ms)
- Пороги из NodeConfig (`limits.currentMin`, `limits.currentMax`)
- Ошибки: `current_not_detected` (ESP_ERR_INVALID_RESPONSE), `overcurrent` (ESP_ERR_INVALID_SIZE)

---

# 11. Обновление прошивки (OTA)

Поддержка OTA (опционально):

- HTTP server (backend)
- Подпись прошивки
- Minimum rollback protection

---

# 12. Wi-Fi архитектура и Setup Mode

## 12.1. Режимы:
- STA (обычный режим)
- Wi‑Fi Reconnect Loop
- Ping watchdog
- **Setup Mode (AP режим)** — для первичной настройки

## 12.2. Setup Portal (Provisioning)

При первом запуске или отсутствии Wi-Fi конфигурации:

- Узел переходит в режим Access Point (AP)
- SSID: `{NODE_TYPE}_SETUP_{PIN}`, где PIN генерируется из MAC-адреса
- Пароль: `hydro2025` (настраивается)
- HTTP-сервер для ввода Wi-Fi credentials
- После получения credentials:
  - Сохранение в NVS через `config_storage`
  - Перезагрузка устройства
  - Подключение к указанной Wi-Fi сети

**Реализовано для всех типов нод:**
- `ph_node`
- `ec_node`
- `climate_node`
- `pump_node`

**Компонент:** `firmware/nodes/common/components/setup_portal/`

---

# 13. Внутренние таймеры узла

Таймеры:
- sensor polling timers
- actuator safety timers
- heartbeat timer
- command timeout timer

---

# 14. Потоки узла (очень важно)

```
[MQTT RX] → parse command → execute → publish response
[SENSOR] → measure → push telemetry
[WIFI] → monitor connection
[CONFIG] → receive config → NVS → restart loops
[SAFE] → enforce safe timers
```

---

# 15. Реализованные компоненты (статус: 2025-01-27)

## 15.1. Компоненты прошивки

✅ **config_storage** — хранение NodeConfig в NVS
- Поддержка версии 3 с `gh_uid` и `zone_uid`
- Функции: `config_storage_get_gh_uid()`, `config_storage_get_zone_uid()`

✅ **setup_portal** — первичная настройка Wi-Fi
- AP режим с веб-интерфейсом
- Генерация PIN из MAC-адреса
- Интеграция с config_storage

✅ **relay_driver** — управление реле
- Поддержка NC/NO реле
- Интеграция в `climate_node`

✅ **pump_driver** — управление насосами
- Интеграция INA209 для проверки тока
- Периодический опрос тока в `pump_node`
- Интеграция в `ec_node` и `pump_node`

✅ **Graceful переподключение Wi-Fi/MQTT**
- Автоматическое переподключение при изменении NodeConfig
- Реализовано в `pump_node`

## 15.2. Backend компоненты

✅ **Water Cycle Engine** (`backend/services/common/water_cycle.py`)
- Логика циркуляции с учётом NC-реле
- Проверка EC drift для смены воды
- Точная логика duty_cycle (циклы по 10 минут)
- Фиксация параметров после стабилизации

✅ **Pump Safety Engine** (`backend/services/common/pump_safety.py`)
- Проверка MCU offline
- Получение порогов из конфигурации узла
- Улучшенная проверка pump_stuck_on с учётом типов насосов

# 16. Будущие расширения

- Каналы для CO₂
- PWM-регулирование света
- Поддержка RS485 модулей
- Zero‑conf добавление нод
- Поддержка ESP‑Now fallback
- ML калибровка Digital Twin

---

# Конец файла NODE_ARCH_FULL.md
