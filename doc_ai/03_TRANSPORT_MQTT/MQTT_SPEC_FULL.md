# MQTT_SPEC_FULL.md
# Полная MQTT спецификация 2.0 (Топики, Payload, Протоколы, Правила)

Этот документ описывает полный протокол MQTT для системы 2.0 управления теплицами.
Здесь указаны форматы топиков, JSON‑payload, правила QoS, LWT, NodeConfig, Telemetry,
Command, Responses и системные события.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

# 1. Общая концепция MQTT 2.0

MQTT используется как **единая шина данных** между backend и ESP‑узлами (нодами).
Принципы:

- Backend — главный мозг. Узлы — исполнители.
- Модель: pub/sub, JSON‑payload.
- Все топики строго стандартизированы.
- Узлы используют только:
 - Telemetry → НАВЕРХ
 - Status/LWT → НАВЕРХ
 - Config_report → НАВЕРХ
 - Command → ВНИЗ
- Backend слушает всё.
- Узлы подписываются только на свои command (config — опционально, legacy).

---

# 2. Структура MQTT-топиков 2.0

Формат топиков:

```
hydro/{gh}/{zone}/{node}/{channel}/{type}
```

Для системных сообщений без канала используется сокращённый формат:
```
hydro/{gh}/{zone}/{node}/{type}
```

Где:
- `gh` — UID теплицы (`greenhouses.uid`), например `gh-1`.
- `zone` — идентификатор зоны (обычно `zones.id` или `zones.uid`), например `zn-3`.
- `node` — строковый UID узла (`nodes.uid`), совпадает с `node_uid` из `../02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`.
- `channel` — имя канала (например `ph_sensor` или `pump_acid`).
- `type` — тип сообщения:

Типы:
- **telemetry**
- **command**
- **command_response**
- **config_report**
- **config** (legacy)
- **status**
- **lwt**

Пример:
```
hydro/gh-1/zn-3/nd-ph-1/ph_sensor/telemetry
```
---

# 3. Telemetry (узлы → backend)

## 3.1. Топик
```
hydro/{gh}/{zone}/{node}/{channel}/telemetry
```

## 3.2. Пример JSON
```json
{
 "metric_type": "PH",
 "value": 5.86,
 "ts": 1710001234
}
```

**Обязательные поля:**
- `metric_type` (string, UPPERCASE) — тип метрики: `PH`, `EC`, `TEMPERATURE`, `HUMIDITY`, `CO2`, `LIGHT_INTENSITY`, `WATER_LEVEL`, `WATER_LEVEL_SWITCH`, `SOIL_MOISTURE`, `SOIL_TEMP`, `WIND_SPEED`, `OUTSIDE_TEMP`, `FLOW_RATE`, `PUMP_CURRENT`
- `value` (number) — значение метрики
- `ts` (integer) — UTC timestamp в секундах (Unix timestamp)

**Опциональные поля:**
- `unit` (string) — единица измерения (например, "pH", "°C", "%")
- `raw` (integer) — сырое значение сенсора
- `stub` (boolean) — флаг, указывающий на симулированное значение
- `stable` (boolean) — флаг, указывающий на стабильность значения

> **Важно:** Поля `node_id` и `channel` **не включаются** в JSON payload, так как они уже присутствуют в структуре MQTT топика (`hydro/{gh}/{zone}/{node}/{channel}/telemetry`). Формат соответствует эталону node-sim, который успешно проходит E2E тесты.

## 3.3. Requirements
- QoS = 1
- Retain = false
- Backend сохраняет TelemetrySample
- Backend обновляет last_value в Redis
- Backend может триггерить Alerts

## 3.4. Telemetry для дискретных датчиков уровня (2-бака)

Для каналов:
- `level_clean_min`
- `level_clean_max`
- `level_solution_min`
- `level_solution_max`

узел публикует стандартную telemetry с `value` в формате `0|1`:

```json
{
  "metric_type": "WATER_LEVEL_SWITCH",
  "value": 1,
  "ts": 1710001234
}
```

Семантика:
- `1` — датчик сработал;
- `0` — датчик не сработал.

Решение по контракту:
- `WATER_LEVEL_SWITCH` является каноническим `metric_type` для дискретных датчиков уровня (`0|1`).

---

# 4. Status & LWT (жизненный цикл узла)

## 4.1. LWT

Устанавливается при connect:

```
hydro/{gh}/{zone}/{node}/lwt
payload: "offline"
```

Примечание для node-sim (preconfig):
- В режиме preconfig (до привязки к зоне) node-sim может выставлять LWT в temp-namespace:
  `hydro/gh-temp/zn-temp/{node_uid_or_hw}/lwt`

## 4.2. Online status

**ОБЯЗАТЕЛЬНО:** При успешном подключении к MQTT брокеру (событие `MQTT_EVENT_CONNECTED`) узел **ОБЯЗАН** немедленно опубликовать status топик.

**Топик:**
```
hydro/{gh}/{zone}/{node}/status
```

**Payload:**
```json
{
 "status": "ONLINE",
 "ts": 1710001555
}
```

**Требования:**
- QoS = 1
- Retain = true
- Публикация выполняется **сразу после** успешного подключения, до подписки на command топики
- Поле `ts` содержит Unix timestamp в секундах (время публикации)
- Backend использует этот статус для обновления `nodes.status` и `nodes.last_seen_at`

**Последовательность действий при подключении:**
1. Установка LWT (Last Will and Testament) — выполняется при инициализации MQTT клиента
2. Подключение к брокеру
3. **Публикация status с "ONLINE"** ← ОБЯЗАТЕЛЬНО
4. Подписка на `hydro/{gh}/{zone}/{node}/+/command` (wildcard для всех каналов)
5. (Опционально) Подписка на `hydro/{gh}/{zone}/{node}/config` для legacy/сервисного сценария
6. Вызов connection callback (если зарегистрирован)

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (mqtt_manager.c, строки 370-374)

## 4.3. Offline
Отправляется брокером автоматически (LWT):

```
payload: "offline"
```

## 4.4. Backend действия:
- помечает ноду OFFLINE
- создаёт Alert
- Zone может перейти в ALARM

---

# 5. NodeConfig (узлы → backend)

## 5.1. Топик
```
hydro/{gh}/{zone}/{node}/config_report
```

## 5.2. Пример полного NodeConfig:
```json
{
 "node_id": "nd-ph-1",
 "version": 3,
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
 "ssid": "HydroFarm",
 "pass": "12345678"
 },
 "mqtt": {
 "host": "192.168.1.10",
 "port": 1883,
 "keepalive": 30
 }
}
```

## 5.3. Requirements
- QoS = 1
- Retain = false
- Узел сохраняет конфиг в NVS
- Узел отправляет `config_report` при подключении

---

# 6. Обработка config_report на backend

Backend подписывается на `hydro/+/+/+/config_report` через сервис `history-logger`:

- сохраняет NodeConfig в `nodes.config`
- синхронизирует `node_channels`
- переводит ноду в `ASSIGNED_TO_ZONE`, если она в `REGISTERED_BACKEND` и имеет `zone_id`/`pending_zone_id`

---

# 7. Commands (backend → узлы)

## 7.1. Топик
```
hydro/{gh}/{zone}/{node}/{channel}/command
```

## 7.2. Пример команд

### 1) Пуск насоса
```json
{
 "cmd": "run_pump",
 "params": {
   "duration_ms": 2500
 },
 "cmd_id": "cmd-591",
 "ts": 1737355112,
 "sig": "a1b2c3d4e5f6..."
}
```

### 2) Дозирование (pH/EC)
```json
{
 "cmd": "dose",
 "params": {
   "ml": 0.5
 },
 "cmd_id": "cmd-592",
 "ts": 1737355113,
 "sig": "b2c3d4e5f6a1..."
}
```

### 3) Включение реле
```json
{
 "cmd": "set_relay",
 "params": {
   "state": true
 },
 "cmd_id": "cmd-593",
 "ts": 1737355114,
 "sig": "c3d4e5f6a1b2..."
}
```

### 4) PWM
```json
{
 "cmd": "set_pwm",
 "params": {
   "value": 128
 },
 "cmd_id": "cmd-594",
 "ts": 1737355115,
 "sig": "d4e5f6a1b2c3..."
}
```

### 5) Калибровка
```json
{
 "cmd": "calibrate",
 "params": {
   "type": "PH_7"
 },
 "cmd_id": "cmd-595",
 "ts": 1737355116,
 "sig": "e5f6a1b2c3d4..."
}
```

### 6) Тест сенсора канала
```json
{
 "cmd": "test_sensor",
 "params": {},
 "cmd_id": "cmd-596",
 "ts": 1737355117,
 "sig": "f6a1b2c3d4e5..."
}
```
**Правило (для всех нод):** команда `test_sensor` обязательна для любых узлов, у которых есть
каналы типа `SENSOR`. Узел выполняет разовое чтение датчика для канала из MQTT-топика
`.../{channel}/command` и отвечает `command_response`:
- при успехе: `status=DONE` и `details` как объект с измерением (например `value`, `unit`,
  `metric_type`, опционально `raw`, `stable`, `tvoc_ppb` и т.п.);
- при ошибке чтения/инициализации: `status=ERROR` или `INVALID` + `error_code`/`error_message`.

### 7) Перезапуск ноды
```json
{
 "cmd": "restart",
 "params": {},
 "cmd_id": "cmd-597",
 "ts": 1737355118,
 "sig": "a7b8c9d0e1f2..."
}
```
**Правило (для всех нод):** команда `restart` доступна для любых узлов. Узел обязан отправить
`command_response` со статусом `DONE`, а затем выполнить перезагрузку устройства.

## 7.3. Формат команды с HMAC подписью

Все команды должны содержать следующие обязательные поля:

| Поле | Тип | Описание |
|------|-----|----------|
| `cmd` | string | Имя команды |
| `cmd_id` | string | Уникальный ID команды |
| `params` | object | Параметры команды (обязательное поле, может быть пустым) |
| `ts` | number | Unix timestamp в секундах (обязательно для HMAC) |
| `sig` | string | HMAC-SHA256 подпись (обязательно для HMAC) |

**Формат подписи:**
```
sig = HMAC_SHA256(node_secret, canonical_json(command_without_sig))
```

Где:
- `node_secret` — секретный ключ узла (хранится в NodeConfig поле `node_secret`)
- `canonical_json` — каноническая JSON-строка команды без поля `sig`:
  - ключи объектов отсортированы лексикографически,
  - порядок массивов сохраняется,
  - сериализация без пробелов,
  - числа форматируются как в cJSON (int если целое, иначе 15/17 значащих),
  - строки JSON-экранируются, UTF-8, слэши не экранируются.
- Подпись возвращается в виде hex строки (64 символа, нижний регистр)

**Проверка на узле:**
1. Узел проверяет наличие полей `ts` и `sig` (обязательные поля).
2. Если любого поля нет, команда отклоняется с ошибкой `invalid_hmac_format`.
3. Если поля присутствуют, выполняется проверка:
   - Формат: `ts` должен быть числом, `sig` должен быть строкой длиной 64 символа (hex)
   - Timestamp: `abs(now - ts) < 10 секунд` (где `now` и `ts` в секундах Unix timestamp)
   - HMAC подпись: вычисляется ожидаемая подпись и сравнивается с полученной (регистронезависимое сравнение hex)
4. Если проверки не пройдены, команда отклоняется с ошибкой:
   - `invalid_hmac_format` — неверный формат полей или длина подписи
   - `timestamp_expired` — timestamp вне допустимого диапазона
   - `invalid_signature` — подпись не совпадает

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (node_command_handler.c)

## 7.4. Архитектура публикации команд через Scheduler-Task

**Важно:** Scheduler и Automation-Engine **НЕ публикуют команды напрямую в MQTT**. Вместо этого используется многоуровневая архитектура с централизованной публикацией через history-logger.

### 7.4.1. Поток команд

```
┌──────────┐      REST API (9405)      ┌────────────────┐      REST API (9300)      ┌───────────────┐
│ Scheduler│ ────────────────────────> │ Automation-    │ ────────────────────────> │ History-      │
│          │  POST /scheduler/task     │ Engine         │  POST /commands           │ Logger        │
└──────────┘                            └────────────────┘                            └───────────────┘
                                                                                              │
                                                                                              │ MQTT Publish
                                                                                              ▼
                                                                                      ┌──────────────┐
                                                                                      │ MQTT Broker  │
                                                                                      │ (Mosquitto)  │
                                                                                      └──────────────┘
                                                                                              │
                                                                                              │ Subscribe
                                                                                              ▼
                                                                                      ┌──────────────┐
                                                                                      │  ESP32 Nodes │
                                                                                      └──────────────┘
```

### 7.4.2. Scheduler → Automation-Engine

**Endpoint:** `POST http://automation-engine:9405/scheduler/task`

**Назначение:** Scheduler создает абстрактную задачу (scheduler-task) и отправляет её в automation-engine для выполнения.

**Формат scheduler-task:**
```json
{
  "task_id": "task-irrigation-123",
  "type": "IRRIGATION",
  "zone_id": 1,
  "params": {
    "duration_sec": 60,
    "volume_ml": 2000,
    "mode": "SCHEDULED"
  },
  "context": {
    "source": "scheduler",
    "cycle_id": 456,
    "phase": "VEG",
    "scheduled_at": "2026-02-14T10:00:00Z"
  }
}
```

**Типы scheduler-task:**
- `IRRIGATION` — задача полива
- `LIGHTING` — задача управления освещением
- `DOSING` — задача дозирования (pH/EC)
- `CLIMATE_CONTROL` — задача управления климатом

### 7.4.3. Automation-Engine → History-Logger

**Endpoint:** `POST http://history-logger:9300/commands`

**Назначение:** Automation-engine преобразует абстрактную scheduler-task в конкретные device-level команды и отправляет их в history-logger для публикации в MQTT.
Контракт history-logger strict: поле `cmd` обязательно, legacy `type` в `/commands` не допускается.

**Преобразование задачи в команду:**

Scheduler-task `IRRIGATION`:
```json
{
  "task_id": "task-irrigation-123",
  "type": "IRRIGATION",
  "zone_id": 1,
  "params": {
    "duration_sec": 60
  }
}
```

↓ **Преобразуется automation-engine в** ↓

MQTT команда `run_pump`:
```json
{
  "cmd": "run_pump",
  "params": {
    "duration_ms": 60000
  },
  "cmd_id": "cmd-12345",
  "ts": 1710001234,
  "sig": "a1b2c3d4e5f6..."
}
```

**Топик:** `hydro/gh-1/zn-1/nd-pump-1/pump_in/command`

### 7.4.4. History-Logger → MQTT

**Назначение:** History-logger — **единственная точка публикации команд в MQTT**. Это обеспечивает:
- Централизованное логирование всех команд
- Единая точка валидации
- Единая точка HMAC подписи
- Упрощенный мониторинг и отладка

**Действия history-logger:**
1. Получает команду через REST API (9300)
2. Валидирует формат команды
3. Добавляет HMAC подпись (если требуется)
4. Публикует в MQTT топик
5. Логирует команду в БД (`commands` таблица)
6. Экспортирует метрики в Prometheus

### 7.4.5. Пример полного потока

**1. Scheduler отправляет задачу:**
```bash
POST http://automation-engine:9405/scheduler/task
{
  "task_id": "task-irr-001",
  "type": "IRRIGATION",
  "zone_id": 1,
  "params": {"duration_sec": 30}
}
```

**2. Automation-engine обрабатывает задачу:**
- Получает effective-targets для зоны 1
- Определяет, какую ноду и канал использовать (например, `nd-pump-1/pump_in`)
- Преобразует в device-level команду `run_pump`

**3. Automation-engine отправляет команду в history-logger:**
```bash
POST http://history-logger:9300/commands
{
  "greenhouse_uid": "gh-1",
  "zone_id": 1,
  "node_uid": "nd-pump-1",
  "channel": "pump_in",
  "cmd": "run_pump",
  "params": {"duration_ms": 30000},
  "context": {
    "task_id": "task-irr-001",
    "source": "scheduler"
  }
}
```

**4. History-logger публикует в MQTT:**
```
Topic: hydro/gh-1/zn-1/nd-pump-1/pump_in/command
Payload:
{
  "cmd": "run_pump",
  "params": {"duration_ms": 30000},
  "cmd_id": "cmd-abc123",
  "ts": 1710001234,
  "sig": "a1b2c3..."
}
```

**5. ESP32 нода получает команду:**
- Подписана на топик `hydro/gh-1/zn-1/nd-pump-1/pump_in/command`
- Проверяет HMAC подпись
- Выполняет команду
- Отправляет `command_response` (см. раздел 8)

### 7.4.6. Преимущества архитектуры

1. **Разделение ответственности:**
   - Scheduler — планирование и расписания
   - Automation-engine — бизнес-логика и преобразование задач
   - History-logger — транспортный уровень и логирование

2. **Централизованное логирование:**
   - Все команды проходят через history-logger
   - Единая точка для аудита и отладки
   - Упрощенный мониторинг через Prometheus

3. **Гибкость:**
   - Scheduler работает с абстрактными задачами
   - Automation-engine может менять логику преобразования без изменения scheduler
   - History-logger может менять MQTT брокер без изменения вышестоящих сервисов

4. **Безопасность:**
   - HMAC подпись добавляется в одном месте (history-logger)
   - Централизованная валидация команд
   - Единая точка для rate limiting

### 7.4.7. См. также

- `../04_BACKEND_CORE/HISTORY_LOGGER_API.md` — REST API спецификация history-logger
- `../04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура Python сервисов
- `BACKEND_NODE_CONTRACT_FULL.md` — контракт между backend и нодами

## 7.5. Системные команды активации/деактивации нод (Correction Cycle)

**ВАЖНО:** pH/EC измерения валидны только при потоке через сенсор. Automation-Engine управляет жизненным циклом сенсорных нод через системные команды активации/деактивации.

### 7.5.1. Топик системных команд

В отличие от канальных команд, системные команды публикуются в топик **без указания канала**:

```
hydro/{gh}/{zone}/{node}/system/command
```

**Примеры:**
```
hydro/gh-1/zn-1/nd-ph-1/system/command
hydro/gh-1/zn-1/nd-ec-1/system/command
```

### 7.5.2. Команда activate_sensor_mode

**Назначение:** Активация сенсорной ноды перед началом измерений (при старте потока через сенсор).

**Топик:** `hydro/{gh}/{zone}/{node}/system/command`

**Payload:**
```json
{
  "cmd": "activate_sensor_mode",
  "params": {
    "stabilization_time_sec": 60
  },
  "cmd_id": "cmd-activate-123",
  "ts": 1710001234,
  "sig": "a1b2c3d4e5f6..."
}
```

**Параметры:**
- `stabilization_time_sec` (integer, обязательно) — время стабилизации сенсора в секундах. После активации нода ждет это время перед разрешением коррекций.

**Поведение ноды при получении activate_sensor_mode:**
1. Переход из режима IDLE в режим ACTIVE
2. Запуск таймера стабилизации (`stabilization_time_sec`)
3. Начало измерений и публикации телеметрии
4. Установка флагов в телеметрии:
   - `flow_active: true` (есть поток)
   - `stable: false` (пока идет стабилизация)
   - `corrections_allowed: false` (коррекции запрещены до окончания стабилизации)
5. По истечении `stabilization_time_sec`:
   - `stable: true`
   - `corrections_allowed: true` (коррекции разрешены)

**Command Response:**
```json
{
  "cmd_id": "cmd-activate-123",
  "status": "DONE",
  "details": {
    "mode": "ACTIVE",
    "stabilization_time_sec": 60
  },
  "ts": 1710001235000
}
```

### 7.5.3. Команда deactivate_sensor_mode

**Назначение:** Деактивация сенсорной ноды после завершения цикла (при остановке потока).

**Топик:** `hydro/{gh}/{zone}/{node}/system/command`

**Payload:**
```json
{
  "cmd": "deactivate_sensor_mode",
  "params": {},
  "cmd_id": "cmd-deactivate-456",
  "ts": 1710002234,
  "sig": "b2c3d4e5f6a1..."
}
```

**Параметры:** Пустой объект (команда не требует параметров).

**Поведение ноды при получении deactivate_sensor_mode:**
1. Переход из режима ACTIVE в режим IDLE
2. Остановка измерений
3. Прекращение публикации телеметрии
4. Публикация только heartbeat и LWT (status)

**Command Response:**
```json
{
  "cmd_id": "cmd-deactivate-456",
  "status": "DONE",
  "details": {
    "mode": "IDLE"
  },
  "ts": 1710002235000
}
```

### 7.5.4. Расширенная телеметрия при активации

При активированном режиме ACTIVE, pH/EC ноды публикуют расширенную телеметрию с дополнительными флагами:

**Топик:** `hydro/{gh}/{zone}/{node}/{channel}/telemetry`

**Payload (во время стабилизации):**
```json
{
  "metric_type": "PH",
  "value": 5.86,
  "ts": 1710001250,
  "flow_active": true,
  "stable": false,
  "stabilization_progress_sec": 15,
  "corrections_allowed": false
}
```

**Payload (после стабилизации):**
```json
{
  "metric_type": "PH",
  "value": 5.86,
  "ts": 1710001300,
  "flow_active": true,
  "stable": true,
  "stabilization_progress_sec": 60,
  "corrections_allowed": true
}
```

**Новые поля телеметрии:**
- `flow_active` (boolean) — индикатор наличия потока через сенсор
- `stable` (boolean) — true после истечения `stabilization_time_sec`
- `stabilization_progress_sec` (integer) — прогресс стабилизации (секунды с момента активации)
- `corrections_allowed` (boolean) — разрешение на коррекции (true после стабилизации + min_interval_sec)

### 7.5.5. Применение в Correction Cycle State Machine

Системные команды активации/деактивации используются automation-engine для управления state machine коррекции:

| Переход состояний | Команда | Ноды |
|------------------|---------|------|
| IDLE → TANK_FILLING | `activate_sensor_mode` | pH, EC |
| READY → IDLE | `deactivate_sensor_mode` | pH, EC |
| READY → IRRIGATING | `activate_sensor_mode` | pH, EC (если требуется) |
| IRRIG_RECIRC → IDLE | `deactivate_sensor_mode` | pH, EC |

**Режимы активации:**

**TANK_FILLING / TANK_RECIRC:**
- Активируются pH + EC ноды
- Коррекции: NPK (через EC ноду) + pH
- Deactivation при переходе в READY

**IRRIGATING / IRRIG_RECIRC:**
- Активируются pH + EC ноды (если не были активны)
- Коррекции: Ca/Mg/micro (через EC ноду) + pH
- Deactivation при переходе в IDLE

### 7.5.6. Требования к реализации на прошивке

**pH/EC ноды должны:**
1. Подписаться на топик `hydro/{gh}/{zone}/{node}/system/command` при подключении
2. Поддерживать два режима работы:
   - **IDLE:** Нет измерений, только heartbeat и LWT
   - **ACTIVE:** Активные измерения и публикация телеметрии
3. Реализовать таймер стабилизации для постепенного перехода к разрешению коррекций
4. Публиковать расширенную телеметрию с флагами `flow_active`, `stable`, `corrections_allowed`
5. Обрабатывать команды `activate_sensor_mode` и `deactivate_sensor_mode` с отправкой `command_response`

**ВАЖНО про подписку на топики:**

Узлы должны подписаться на системный топик **отдельно** от канальных команд:

```c
// Подписка на канальные команды (wildcard для всех каналов)
mqtt_subscribe("hydro/gh-1/zn-1/nd-ph-1/+/command");

// Подписка на системные команды (отдельная подписка!)
mqtt_subscribe("hydro/gh-1/zn-1/nd-ph-1/system/command");
```

**Почему нужна отдельная подписка:**

Wildcard `+/command` **НЕ захватывает** топик без канала между `{node}` и `command`.

- `hydro/.../nd-ph-1/+/command` — подписывается на `ph_main/command`, `pump_ph_up/command` и т.д.
- `hydro/.../nd-ph-1/system/command` — **НЕ** соответствует wildcard `+/command`, так как `system` находится на месте канала, но топик заканчивается на `system/command` без дополнительного уровня

**Правильная инициализация подписок при подключении:**

```c
void mqtt_on_connected(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    // 1. Подписка на канальные команды
    char topic_channels[128];
    snprintf(topic_channels, sizeof(topic_channels),
             "hydro/%s/%s/%s/+/command",
             config->greenhouse_uid, config->zone_uid, config->node_uid);
    esp_mqtt_client_subscribe(mqtt_client, topic_channels, 1);

    // 2. Подписка на системные команды (отдельно!)
    char topic_system[128];
    snprintf(topic_system, sizeof(topic_system),
             "hydro/%s/%s/%s/system/command",
             config->greenhouse_uid, config->zone_uid, config->node_uid);
    esp_mqtt_client_subscribe(mqtt_client, topic_system, 1);

    ESP_LOGI(TAG, "Subscribed to channel commands: %s", topic_channels);
    ESP_LOGI(TAG, "Subscribed to system commands: %s", topic_system);
}
```

### 7.5.7. См. также

- `../06_DOMAIN_ZONES_RECIPES/CORRECTION_CYCLE_SPEC.md` — спецификация correction cycle state machine
- `../06_DOMAIN_ZONES_RECIPES/EFFECTIVE_TARGETS_SPEC.md` — конфигурация параметров стабилизации
- `ARCHITECTURE_FLOWS.md` — диаграммы потоков с state machine

---

# 8. Command Response (узлы → backend)

## 8.1. Топик
```
hydro/{gh}/{zone}/{node}/{channel}/command_response
```

## 8.2. Общие требования

Каждая команда, отправленная в `.../{channel}/command`, **обязана** породить хотя бы один
ответ `command_response` от узла:

- даже если команда была отвергнута по валидации (HMAC, timestamp, параметры);
- даже если действие выполнить не удалось по железу (ошибка насоса, проблема с питанием);
- даже если узел находился в SAFE_MODE.

Backend никогда не остаётся "в неизвестности": по `cmd_id` он либо получает `ACK`,
либо `ERROR`/`TIMEOUT` и может принять управленческое решение.

## 8.2.1. Формат command_response

**Обязательные поля:**
- `cmd_id` (string) — идентификатор команды, точно соответствующий `cmd_id` из команды
- `status` (string) — статус выполнения: `ACK`, `DONE`, `ERROR`, `INVALID`, `BUSY`, `NO_EFFECT`
  (допустим также `TIMEOUT` для device-level timeout сценариев)
- `ts` (integer) — UTC timestamp в миллисекундах

**Опциональные поля:**
- `details` (object) — детали выполнения команды
- `error_code` (string) — машинночитаемый код ошибки для `status=ERROR`
- `error_message` (string) — человекочитаемое пояснение для `status=ERROR`

**Пример успешного ответа:**
```json
{
  "cmd_id": "cmd-591",
  "status": "DONE",
  "details": {
    "result": "ok"
  },
  "ts": 1710003399123
}
```

**Пример ошибки валидации HMAC:**

Если команда отклонена из-за невалидной HMAC подписи или истекшего timestamp, узел отправляет:

```json
{
  "cmd_id": "cmd-591",
  "status": "ERROR",
  "ts": 1710003399123,
  "error_code": "invalid_signature",
  "error_message": "Command HMAC signature verification failed"
}
```

или

```json
{
  "cmd_id": "cmd-591",
  "status": "ERROR",
  "ts": 1710003399,
  "error_code": "timestamp_expired",
  "error_message": "Command timestamp is outside acceptable range"
}
```

## 8.3. Базовый payload

```json
{
  "cmd_id": "cmd-591",
  "status": "ACK",
  "ts": 1710003333123
}
```

**Важно:** Поле `ts` содержит UTC timestamp в **миллисекундах** (не секундах).

Статусы:
- `ACK` — команда принята и будет выполнена;
- `DONE` — команда выполнена успешно;
- `ERROR` — команда не выполнена или выполнена с ошибкой;
- `INVALID` — команда невалидна (неверные параметры);
- `BUSY` — узел занят, команда не может быть выполнена сейчас;
- `NO_EFFECT` — команда не оказала эффекта (например, реле уже в нужном состоянии).
- `TIMEOUT` — команда/операция прервана по таймауту на стороне ноды.

Legacy-статусы `ACCEPTED` и `FAILED` запрещены.
`SEND_FAILED` — backend-layer статус (ошибка публикации), в `command_response` от ноды не используется.

## 8.4. Расширенный payload для ошибок

Для ошибок допускается расширенный формат:

```json
{
  "cmd_id": "cmd-591",
  "status": "ERROR",
  "ts": 1710003399,
  "error_code": "current_not_detected",
  "error_message": "No current on pump_in channel after switching on",
  "details": {
    "channel": "pump_in",
    "requested_state": 1,
    "measured_current_ma": 5,
    "expected_min_current_ma": 80
  }
}
```

`error_code` — машинночитаемый код для backend-логики,  
`error_message` — человекочитаемое пояснение,  
`details` — любые доп. поля (например, измеренный ток, номер повторной попытки и т.п.).

## 8.5. Особые правила для насосов (pump\_*)

Для всех команд, связанных с насосами (`pump_acid`, `pump_base`, `pump_a`, `pump_b`,
`pump_c`, `pump_d`, `pump_in` и другие актуаторные каналы насосов):

1. Узел **обязан** после включения насоса:
   - подождать минимальное время стабилизации (настраиваемое, например 100–300 ms),
   - считать ток через соответствующий датчик INA209 по I²C,
   - сравнить его с порогами в NodeConfig.

2. Если ток ниже минимального порога или выходит за допустимый диапазон:
   - узел отправляет `command_response` со статусом `ERROR` и `error_code="current_not_detected"` или другим подходящим кодом;
   - дополнительно может отправить диагностическую telemetry по каналу тока.

3. Если ток в норме:
   - узел отправляет `command_response` со статусом `ACK`,
   - при необходимости публикует telemetry с измеренным током (см. раздел Telemetry для каналов тока).

Таким образом, backend всегда знает не только то, что команда на включение насоса была отправлена,
но и то, что **реле реально замкнулось и насос потребляет ток** в ожидаемых пределах.

## 8.6. Особые правила для авто-наполнения баков (2-бака)

Для каналов `valve_clean_fill` и `valve_solution_fill`:

1. Нода обязана локально остановить наполнение по датчику `*_max`:
   - `level_clean_max` для чистого бака;
   - `level_solution_max` для бака раствора.
2. При авто-остановке нода обязана отправить `command_response`:

```json
{
  "cmd_id": "cmd-701",
  "status": "DONE",
  "ts": 1710003399123,
  "details": {
    "result": "auto_stopped",
    "reason_code": "level_max_reached",
    "tank": "clean"
  }
}
```

3. Дополнительно нода публикует событие (канал `storage_state`):

Топик:
```text
hydro/{gh}/{zone}/{node}/storage_state/event
```

Payload:
```json
{
  "event_code": "clean_fill_completed",
  "ts": 1710003399,
  "state": {
    "level_clean_min": 1,
    "level_clean_max": 1,
    "level_solution_min": 0,
    "level_solution_max": 0
  }
}
```

Нормализация в backend (`history-logger`):
- `event_code` (или fallback-поля `event`/`type`) преобразуется в `zone_events.type`;
- преобразование: `UPPERCASE` + все не `[A-Z0-9]` символы заменяются на `_` + схлопывание повторов `_`;
- пример: `clean fill-completed/v2` -> `CLEAN_FILL_COMPLETED_V2`;
- если код пустой, используется `NODE_EVENT`.
- для `zone_events.type` действует лимит 255 символов: если нормализованный код длиннее, он усечётся
  детерминированно и получит suffix `_{SHA1_10}` (первые 10 hex-символов SHA1).

Метрика приёма событий (`node_event_received_total{event_code=...}`):
- в label попадают только whitelisted коды событий двухбакового контура;
- все остальные коды агрегируются в `event_code="OTHER"` для контроля кардинальности Prometheus.

Назначение:
- automation-engine использует это событие как fast-path подтверждение;
- scheduler/automation сохраняют периодический poll как резервный канал контроля.

---
# 9. Дополнительные системные топики

## 9.1. Node Hello (регистрация узла)
```
hydro/node_hello
hydro/{gh}/{zone}/{node}/node_hello
```

**Топик:** 
- `hydro/node_hello` — для начальной регистрации, когда узел не знает gh/zone/node
- `hydro/{gh}/{zone}/{node}/node_hello` — если узел уже знает свои параметры из provisioning

**Payload:**
```json
{
  "message_type": "node_hello",
  "hardware_id": "esp32-ABCD1234",
  "node_type": "ph",
  "fw_version": "2.0.1",
  "hardware_revision": "v1.0",
  "capabilities": ["ph", "temperature"],
  "provisioning_meta": {
    "node_name": null,
    "greenhouse_token": null,
    "zone_id": null
  }
}
```

**Requirements:**
- QoS = 1
- Retain = false
- Backend обрабатывает и создаёт/обновляет `DeviceNode` с `logical_node_id` (uid). Поля `greenhouse_token` и `zone_id` из `provisioning_meta` игнорируются; привязка теплицы/зоны выполняется только вручную через UI/Android, после чего нода отправляет `config_report`.
- `node_type` передаётся только в канонической схеме: `ph|ec|climate|irrig|light|relay|water_sensor|recirculation|unknown`.
- Legacy-алиасы `node_type` не поддерживаются.

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (обработчик `handle_node_hello` в history-logger, интеграция с Laravel API; автопривязка по token отключена)

---

## 9.2. Heartbeat узла
```
hydro/{gh}/{zone}/{node}/heartbeat
```

**Payload:**
```json
{
  "uptime": 3600,
  "free_heap": 102000,
  "rssi": -62
}
```

**Обязательные поля:**
- `uptime` (integer) — время работы узла в секундах (не миллисекунды)
- `free_heap` (integer) — свободная память в байтах

**Опциональные поля:**
- `rssi` (integer) — сила сигнала Wi-Fi в dBm (от -100 до 0)

> **Важно:** Поле `ts` **не включается** в heartbeat согласно эталону node-sim. Формат соответствует эталону, который успешно проходит E2E тесты.

**Requirements:**
- QoS = 1 (обновлено: было 0, теперь 1 для надёжности)
- Retain = false
- Backend обновляет поля `last_heartbeat_at`, `uptime_seconds`, `free_heap_bytes`, `rssi` в таблице `nodes`
- Обновляет также `last_seen_at` при получении heartbeat

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (обработчик `handle_heartbeat` в history-logger, поля в БД добавлены)

---

## 9.3. Error (публикация ошибок узлом)

**Топик:**
```
hydro/{gh}/{zone}/{node}/error
```

**Payload:**
```json
{
  "level": "ERROR",
  "component": "ph_sensor",
  "error_code": "esp_ESP_ERR_INVALID_STATE",
  "message": "Sensor not initialized",
  "ts": 1710003399123,
  "details": {
    "error_code_num": 9,
    "original_level": "CRITICAL"
  }
}
```

**Обязательные поля:**
- `level` (string) — уровень ошибки: `ERROR`, `WARNING`, `INFO` (CRITICAL маппится в ERROR)
- `component` (string) — компонент, сгенерировавший ошибку
- `error_code` (string) — код ошибки (например, `esp_ESP_ERR_INVALID_STATE`)
- `message` (string) — человекочитаемое сообщение об ошибке

**Опциональные поля:**
- `ts` (integer) — UTC timestamp в миллисекундах
- `details` (object) — дополнительные детали ошибки

**Requirements:**
- QoS = 1
- Retain = false
- Backend обрабатывает ошибки и может создавать алерты

---

## 9.4. Debug (опционально)
```
hydro/{node}/debug
```

---

# 10. Правила QoS и Retain

| Тип | QoS | Retain |
|-----|-----|---------|
| telemetry | 1 | false |
| command | 1 | false |
| command_response | 1 | false |
| config_report | 1 | false |
| status | 1 | true |
| lwt | 1 | true |
| node_hello | 1 | false |
| heartbeat | 1 | false |

---

# 11. Правила именования

### Node ID
```
nd-{type}-{nn}
```
Примеры:
- `nd-ph-1`
- `nd-ec-2`

### Channel ID
```
ph_sensor
ec_sensor
pump_acid
pump_base
pump_a
pump_b
pump_c
pump_d
fan_A
heater_1
```

---

# 12. Потоки данных (Data Flows)

## Telemetry → Backend
```
node → mqtt → listener → router → handler → TelemetryService
```

## Command → Node
```
controller → CommandService → NodeCoordinator → mqtt → node
```

## Config → Backend
```
node → mqtt → history-logger → Laravel API → nodes.config + node_channels
```

**Автоматическая синхронизация:**
- Нода отправляет `config_report` при подключении (или после обновления прошивки)
- Сервер сохраняет конфиг и синхронизирует каналы

**Статус реализации:** ✅ **РЕАЛИЗОВАНО** (history-logger config_report handler)

## Status → Backend
```
node → status/lwt → history-logger → AlertService
```

## Node Hello → Backend
```
node → node_hello → history-logger → Laravel API → NodeRegistryService
```

## Heartbeat → Backend
```
node → heartbeat → history-logger → nodes table (uptime, free_heap, rssi)
```

---

# 13. Требования к узлам (Node Firmware)

## 13.1. Подписки (обязательные)

Узел **ОБЯЗАН** подписаться на:
- `hydro/{gh}/{zone}/{node}/+/command` — для получения команд по всем каналам (wildcard)

Опционально (legacy/сервисный сценарий):
- `hydro/{gh}/{zone}/{node}/config` — получение конфигурации с сервера, если она публикуется вручную

## 13.2. Публикации (обязательные)

Узел **ОБЯЗАН** публиковать:

### При подключении к MQTT брокеру:
- **status** (`hydro/{gh}/{zone}/{node}/status`) — **ОБЯЗАТЕЛЬНО** сразу после `MQTT_EVENT_CONNECTED` (см. раздел 4.2)

### Регулярно:
- **telemetry** (`hydro/{gh}/{zone}/{node}/{channel}/telemetry`) — по расписанию из NodeConfig
- **heartbeat** (`hydro/{gh}/{zone}/{node}/heartbeat`) — периодически (например, каждые 30 секунд)

### По запросу:
- **command_response** (`hydro/{gh}/{zone}/{node}/{channel}/command_response`) — на каждую команду
- **config_report** (`hydro/{gh}/{zone}/{node}/config_report`) — при подключении/инициализации (отправка текущего NodeConfig)

### При регистрации:
- **node_hello** (`hydro/node_hello` или `hydro/{gh}/{zone}/{node}/node_hello`) — при первой регистрации

### При инициализации:
- **lwt** (`hydro/{gh}/{zone}/{node}/lwt`) — настраивается при инициализации MQTT клиента

## 13.3. Общие требования

- JSON строго формализован согласно спецификации
- Ошибки команд возвращаются через command_response
- Все публикации должны соответствовать форматам из разделов 3-9
- QoS и Retain должны соответствовать таблице из раздела 10

---

# 14. Требования к backend

- полный MQTT router
- QoS = 1
- хранение команд
- таймаут команд (если нет ACK)
- хранить NodeConfig из `config_report` и использовать его для команд/телеметрии
- обработка node_hello для регистрации узлов (✅ реализовано в history-logger)
- обработка heartbeat для мониторинга узлов (✅ реализовано в history-logger)
- алерты при offline / telemetry out of range

---

# 15. Будущее расширение (2.0)

- групповые команды
- топики для AI-моделей
- нормализация telemetry через schema registry
- агрономические триггеры MQTT→backend
- автоматические профили нод

---

# Конец файла
