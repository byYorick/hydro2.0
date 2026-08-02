# MQTT_SPEC_FULL.md
# Полная MQTT спецификация 2.0 (Топики, Payload, Протоколы, Правила)

Этот документ описывает полный протокол MQTT для системы 2.0 управления теплицами.
Здесь указаны форматы топиков, JSON‑payload, правила QoS, LWT, NodeConfig, Telemetry,
Command, Responses и системные события.

**Дата обновления:** 2026-08-02 (sensor-mode channel=`system`; HMAC→ERROR; storage_state channel-level; HL `+/event`).

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

---

# 1. Общая концепция MQTT 2.0

MQTT используется как **единая шина данных** между backend и ESP‑узлами (нодами).
Принципы:

- Backend — главный мозг. Узлы — исполнители.
- Модель: pub/sub, JSON‑payload.
- Все топики строго стандартизированы.
- Узлы используют:
 - Telemetry → НАВЕРХ
 - Status/LWT → НАВЕРХ
 - Config_report → НАВЕРХ
 - Command → ВНИЗ
 - Config (NodeConfig push) → ВНИЗ (bind/rebind/unbind через history-logger)
- Backend слушает точечными wildcard-подписками (не `hydro/#`).
- Узлы подписываются на свои `command` и на `.../config` (provisioning / bind / update NodeConfig).

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

Полный список типов сообщений (`{type}`), которые реально публикуются/обрабатываются runtime:

**Узел → backend (channel-level):**
- `telemetry` — измерения с канала
- `command_response` — ответ на команду
- `event` — channel-level node event (`level_switch_changed`, `storage_state/event`, …)
- `storage_state/event` — aggregate state event контура 2 бака (`channel=storage_state`, только `irrig`)

**Узел → backend (node-level, без `{channel}`):**
- `status` — online/offline status (retained)
- `lwt` — Last Will and Testament (retained, payload `"offline"`)
- `config_report` — текущий NodeConfig
- `heartbeat` — uptime/free_heap/rssi
- `node_hello` — первая регистрация (доп. также безсегментный `hydro/node_hello`)
- `diagnostics` — опциональный engineering snapshot
- `error` — узловые ошибки

**Backend → узел:**
- `command` — команда на канал (в т.ч. `channel=system` для `activate_sensor_mode` / `deactivate_sensor_mode`)
- `config` — push NodeConfig (Laravel → history-logger → MQTT; bind/rebind/unbind, обновление mirror)

**Системные / broadcast:**
- `hydro/time/request` (узел → backend)
- `hydro/time/response` (backend → узлы)

Status: **planned / not implemented** — `hydro/{node}/debug` (см. §9.4); обработчик в history-logger отсутствует, оставлен как опциональная диагностика.

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
- `stable` (boolean) — флаг стабильности значения (для активированных sensor-нод)
- `flow_active` (boolean) — индикатор активного потока через сенсор (pH/EC)
- `corrections_allowed` (boolean) — runtime-флаг доступности коррекции
- `tds` (number) — производное TDS-значение для EC-нод
- `health` (object) — sensor-side health context (`status`, `error_count`)

> **Важно:** Поля `node_id` и `channel` **не включаются** в JSON payload, так как они уже присутствуют в структуре MQTT топика (`hydro/{gh}/{zone}/{node}/{channel}/telemetry`). Формат соответствует эталону node-sim, который успешно проходит E2E тесты.

## 3.3. Requirements
- QoS = 1
- Retain = false
- Узел публикует telemetry только после time sync через `hydro/time/response`
- `history-logger` сохраняет запись в hypertable `telemetry_samples` (Timescale, chunk 1 day) и обновляет кэш последнего значения в PostgreSQL `telemetry_last` (PK по `sensor_id`).
- `history-logger` использует точечные подписки MQTT — `hydro/+/+/+/+/{telemetry|command_response|event}` и `hydro/+/+/+/{status|lwt|config_report|heartbeat|diagnostics|error|node_hello}`, без подписки на широкий wildcard `hydro/#`. Aggregate `storage_state/event` — **channel-level** (`channel=storage_state`) и попадает в подписку `hydro/+/+/+/+/event` (отдельная node-level подписка на `storage_state/event` не нужна и в коде HL отсутствует).
- `history-logger` также пишет business-trigger в `zone_events` и эмитит `AlertService` ingest при выходе за пороги/freshness.
- Last-value хранится в **PostgreSQL** (`telemetry_last`), Redis для последних значений **не используется** (исторический паттерн ранних версий, removed).

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

**ОБЯЗАТЕЛЬНО:** Узел публикует `status` только после успешной синхронизации времени через `hydro/time/response`.
Публикация `status` сразу после `MQTT_EVENT_CONNECTED` (до time sync) **запрещена**.

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
- Публикация не должна происходить до завершения time sync
- Поле `ts` содержит Unix timestamp в секундах (время публикации)
- Backend использует этот статус для обновления `nodes.status` и `nodes.last_seen_at`

**Каноническая последовательность при подключении:**
1. Установка LWT (Last Will and Testament) — при инициализации MQTT клиента
2. Подключение к брокеру (`MQTT_EVENT_CONNECTED`)
3. Подписка на `hydro/time/response`, `.../+/command` и `.../config`
4. Публикация `hydro/time/request`
5. Получение `hydro/time/response` (time sync)
6. Только после time sync: публикация `status` / `telemetry` / `event` (и прочих сообщений с полем `ts`)

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

# 5. NodeConfig (config_report вверх + config push вниз)

## 5.1. Топик
```
hydro/{gh}/{zone}/{node}/config_report
```

## 5.2. Пример полного NodeConfig (v3, обязательные поля):
```json
{
 "node_id": "nd-ph-1",
 "version": 3,
 "fw_version": "1.0.0",
 "type": "ph",
 "gh_uid": "gh-1",
 "zone_uid": "zn-3",
 "node_secret": "CHANGE_ME_32_PLUS_CHARS_XXXXXXXXX",
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

Обязательные поля верхнего уровня v3: `node_id`, `version`, `type`, `gh_uid`, `zone_uid`,
`channels`, `wifi`, `mqtt` (см. `../02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md`).
`node_secret` обязателен для HMAC команд (длина ≥ 32 символа/байта).

## 5.3. Requirements
- QoS = 1
- Retain = false
- Узел сохраняет конфиг в NVS
- Узел отправляет `config_report` при подключении и после успешного apply MQTT `.../config`
- `fw_version` — версия прикладной прошивки, сформированная самой нодой; это не версия ESP-IDF SDK. Backend сохраняет её в `nodes.fw_version`.

## 5.4. Config push (backend → node)

Канонический provisioning/bind flow публикует целевой NodeConfig **вниз** на топик:

```
hydro/{gh}/{zone}/{node}/config
```

(часто temp namespace `hydro/gh-temp/zn-temp/{node}/config` при bind, пока нода ещё не в целевой зоне).

Путь: Laravel (`PublishNodeConfigJob` / unbind services) → history-logger `POST /nodes/{uid}/config` → MQTT.
Нода применяет конфиг, сохраняет в NVS и подтверждает `config_report` из актуального namespace.
Подробности: `../01_SYSTEM/NODE_ASSIGNMENT_LOGIC.md`, `../01_SYSTEM/NODE_LIFECYCLE_AND_PROVISIONING.md`,
`../02_HARDWARE_FIRMWARE/NODE_CONFIG_SPEC.md`.

---

# 6. Обработка config_report на backend

Backend подписывается на `hydro/+/+/+/config_report` через сервис `history-logger`:

- сохраняет NodeConfig в `nodes.config`
- синхронизирует `node_channels`
- сообщает Laravel observed-факт `config_report`
- Laravel финализирует bind/rebind и переводит ноду в `ASSIGNED_TO_ZONE`

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

Правило для orchestration/runtime:
- `run_pump` остаётся time-based командой с `duration_ms`;
- `dose` является канонической командой для pH/EC dosing и использует только `params.ml` как source of truth для объёма на ноде;
- нода вычисляет `duration_ms = ceil(ml / ml_per_second * 1000)` по NodeConfig actuator channel и режет по `safe_limits.max_duration_ms`;
- AE3 планирует `ml` по DB `pump_calibrations.ml_per_sec` и обязан clamp'ить до согласованного `max_dose_ms` (default 60_000 ms = firmware ph/ec node);
- при clamp на ноде ACK содержит `details.duration_limited=true` и фактический `details.duration_ms`.

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

### 5) Позиция привода (roof vent, greenhouse climate)

Каналы `roof_vent_left` / `roof_vent_right` (см. `NODE_CHANNELS_REFERENCE.md`, `GREENHOUSE_CLIMATE_CONTROL_PLAN.md`).
Сегмент `{zone}` в топике — UID anchor-зоны при greenhouse-only приводе (см. `MQTT_NAMESPACE.md`).

```json
{
 "cmd": "set_position",
 "params": {
   "position_pct": 40,
   "max_step_pct": 25
 },
 "cmd_id": "cmd-594b",
 "ts": 1737355115,
 "sig": "..."
}
```

### 6) Калибровка
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

### 7) Тест сенсора канала
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

### 8) Перезапуск ноды
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

### 9) Снимок состояния IRR-ноды (`state`)
```json
{
 "cmd": "state",
 "params": {},
 "cmd_id": "cmd-598",
 "ts": 1737355119,
 "sig": "b7c8d9e0f1a2..."
}
```
**Правило (для нод типа `irrig`):** команда `state` возвращает `command_response` со статусом `DONE`
и `details.snapshot`, где все дискретные поля представлены как `bool`.

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

## 7.4. Архитектура публикации команд

**Важно:** Laravel scheduler и automation-engine **НЕ публикуют команды напрямую в MQTT**.  
Единственный publisher команд в MQTT: `history-logger`.

### 7.4.1. Поток команд

```
┌──────────────────────┐   DB write (intent)   ┌────────────────┐  REST API (9300)   ┌───────────────┐
│ Laravel scheduler    │ ─────────────────────> │ Automation-    │ ──────────────────> │ History-      │
│ (dispatch)           │   + POST /start-cycle  │ Engine         │  POST /commands     │ Logger        │
└──────────────────────┘                         └────────────────┘                     └───────────────┘
                                                                                                 │
                                                                                                 │ MQTT Publish
                                                                                                 ▼
                                                                                         ┌──────────────┐
                                                                                         │ MQTT Broker  │
                                                                                         └──────────────┘
                                                                                                 │
                                                                                                 ▼
                                                                                         ┌──────────────┐
                                                                                         │ ESP32 Nodes  │
                                                                                         └──────────────┘
```

### 7.4.2. Laravel scheduler → Automation-Engine

Laravel scheduler передает intent двумя шагами:
1. пишет `pending` в `zone_automation_intents`;
2. вызывает `POST http://automation-engine:9405/zones/{id}/start-cycle`.

`POST /zones/{id}/start-cycle` является wake-up endpoint и не несет device-level команд.

### 7.4.3. Automation-Engine → History-Logger

**Endpoint:** `POST http://history-logger:9300/commands`

Automation-engine:
- claim-ит pending intent;
- строит шаги workflow зоны;
- отправляет device-level команды в history-logger;
- ждет terminal status (`DONE|ERROR|INVALID|BUSY|NO_EFFECT|TIMEOUT|SEND_FAILED`).

Контракт history-logger strict:
- поле `cmd` обязательно;
- поле `type` в `/commands` не допускается (только `cmd`).

### 7.4.4. History-Logger → MQTT

History-logger:
1. принимает команду через REST;
2. валидирует payload;
3. подписывает (если включен HMAC policy);
4. публикует в MQTT топик `hydro/{gh}/{zone}/{node}/{channel}/command`;
5. фиксирует lifecycle команды в БД.

### 7.4.5. Пример полного потока

**1. Laravel scheduler-dispatch создаёт intent и будит зону**
```bash
POST http://automation-engine:9405/zones/1/start-cycle
{
  "source": "laravel_scheduler",
  "idempotency_key": "sch:z1:irrigation:2026-02-21T10:00:00Z"
}
```

**2. Automation-engine отправляет команду в history-logger**
```bash
POST http://history-logger:9300/commands
{
  "greenhouse_uid": "gh-1",
  "zone_id": 1,
  "node_uid": "nd-pump-1",
  "channel": "pump_in",
  "cmd": "run_pump",
  "params": {"duration_ms": 30000},
  "source": "automation-engine"
}
```

**3. Нода возвращает `command_response`**
- `history-logger` сохраняет статус команды;
- Automation-engine получает обновление через `LISTEN/NOTIFY` и reconcile polling.

### 7.4.6. Преимущества архитектуры

1. Единый командный publisher (`history-logger`) и единый audit trail.
2. Детерминированный wake-up контракт (`POST /zones/{id}/start-cycle`).
3. Отделение scheduling (Laravel) от device execution (automation-engine).
4. Устойчивость через `NOTIFY + polling` для feedback-команд.

2. **Централизованное логирование:**
   - Все команды проходят через history-logger
   - Единая точка для аудита и отладки
   - Упрощенный мониторинг через Prometheus

3. **Гибкость:**
   - Laravel планирует абстрактные задачи расписания
   - Automation-engine может менять логику преобразования без изменения контракта Laravel → AE
   - History-logger может менять MQTT брокер без изменения вышестоящих сервисов

4. **Безопасность:**
   - HMAC подпись добавляется в одном месте (history-logger)
   - Централизованная валидация команд
   - Единая точка для rate limiting

### 7.4.7. См. также

- `../04_BACKEND_CORE/HISTORY_LOGGER_API.md` — REST API спецификация history-logger
- `../04_BACKEND_CORE/PYTHON_SERVICES_ARCH.md` — архитектура Python сервисов
- `BACKEND_NODE_CONTRACT_FULL.md` — контракт между backend и нодами

## 7.5. Команды sensor mode на канале `system` (Correction Cycle)

**ВАЖНО:** Automation-Engine управляет флагом sensor mode pH/EC нод через команды `activate_sensor_mode` / `deactivate_sensor_mode`. Эти команды — обычные channel-level команды с `channel=system` (service channel в NodeConfig), а не отдельный node-level формат «без канала».

### 7.5.1. Топик команд sensor mode

Топик совпадает с канальным паттерном `hydro/{gh}/{zone}/{node}/{channel}/command`, где `{channel}=system`:

```
hydro/{gh}/{zone}/{node}/system/command
```

**Примеры:**
```
hydro/gh-1/zn-1/nd-ph-1/system/command
hydro/gh-1/zn-1/nd-ec-1/system/command
```

`system` — это **channel-level** сегмент (как `ph_sensor` или `pump_acid`), а не «системный топик без канала». Firmware принимает эти команды только при `channel == "system"` (`ph_node_is_system_channel` / аналог на EC).

### 7.5.2. Команда activate_sensor_mode

**Назначение:** Включить sensor mode (разрешить коррекции / выставить flow-флаги) перед циклом коррекции.

**Топик:** `hydro/{gh}/{zone}/{node}/system/command`

**Payload (фактический контракт firmware):**
```json
{
  "cmd": "activate_sensor_mode",
  "params": {},
  "cmd_id": "cmd-activate-123",
  "ts": 1710001234,
  "sig": "a1b2c3d4e5f6..."
}
```

**Параметры:** пустой объект. Поле `stabilization_time_sec` в firmware **не реализовано / planned** — handler его не читает и таймер стабилизации не запускает.

**Фактическое поведение ноды при `activate_sensor_mode`:**
1. Устанавливает внутренний bool `sensor_mode_active = true` (идемпотентно: повторный activate → `DONE` + `note=sensor_mode_already_active_treated_as_done`).
2. Измерения и публикация telemetry **уже идут** независимо от sensor mode; activate их не «стартует».
3. В telemetry выставляются флаги:
   - `flow_active` = `sensor_mode_active` (true)
   - `corrections_allowed` = `sensor_mode_active` (true)
   - `stable` — значение стабильности **с датчика** (driver/cache), при `sensor_mode_active=false` публикуется `stable=false`

Status: **не реализовано / planned** — таймер стабилизации по `stabilization_time_sec`, поля `stabilization_progress_sec`, поэтапный переход `stable`/`corrections_allowed` по истечении таймера.

**Command Response:**
```json
{
  "cmd_id": "cmd-activate-123",
  "status": "DONE",
  "details": {
    "sensor_mode_active": true
  },
  "ts": 1710001235000
}
```

(Не `mode: ACTIVE|IDLE` и не `stabilization_time_sec` — firmware отдаёт bool `sensor_mode_active`.)

### 7.5.3. Команда deactivate_sensor_mode

**Назначение:** Сбросить sensor mode после завершения цикла (запретить коррекции через flow-флаги).

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

**Параметры:** пустой объект.

**Фактическое поведение ноды при `deactivate_sensor_mode`:**
1. Устанавливает `sensor_mode_active = false` (идемпотентно: повторный deactivate → `DONE` + `note=sensor_mode_already_inactive_treated_as_done`).
2. **Не** останавливает измерения и **не** прекращает публикацию telemetry — сбрасываются только sensor-mode флаги (`flow_active`/`corrections_allowed` → false, `stable` → false в publish path).
3. Heartbeat / LWT / status продолжают публиковаться как обычно.

**Command Response:**
```json
{
  "cmd_id": "cmd-deactivate-456",
  "status": "DONE",
  "details": {
    "sensor_mode_active": false
  },
  "ts": 1710002235000
}
```

### 7.5.4. Расширенная телеметрия при sensor mode

pH/EC ноды публикуют telemetry с flow-флагами постоянно (и при active, и при inactive sensor mode):

**Топик:** `hydro/{gh}/{zone}/{node}/{channel}/telemetry`

**Payload (`sensor_mode_active=true`, датчик считает значение стабильным):**
```json
{
  "metric_type": "PH",
  "value": 5.86,
  "ts": 1710001300,
  "flow_active": true,
  "stable": true,
  "corrections_allowed": true
}
```

**Payload (`sensor_mode_active=false`):**
```json
{
  "metric_type": "PH",
  "value": 5.86,
  "ts": 1710001300,
  "flow_active": false,
  "stable": false,
  "corrections_allowed": false
}
```

**Поля телеметрии (фактический контракт):**
- `flow_active` (boolean) — зеркало `sensor_mode_active`
- `corrections_allowed` (boolean) — зеркало `sensor_mode_active`
- `stable` (boolean) — стабильность с датчика при `sensor_mode_active=true`, иначе `false`

Status: **не реализовано / planned** — `stabilization_time_sec`, `stabilization_progress_sec`, таймер стабилизации на ноде.

### 7.5.5. Применение в Correction Cycle State Machine

Команды sensor mode используются automation-engine для управления state machine коррекции:

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

**pH/EC ноды (фактическое поведение `mqtt_manager` + node handlers):**
1. Подписаться на `hydro/{gh}/{zone}/{node}/+/command` при подключении — этого **достаточно**: MQTT single-level `+` матчит любой один сегмент канала, **включая** `system`.
2. Хранить bool `sensor_mode_active`; команды `activate_sensor_mode` / `deactivate_sensor_mode` принимаются **только** на `channel=system`.
3. Публиковать telemetry с флагами `flow_active`, `stable`, `corrections_allowed` (см. §7.5.4); измерения **не** останавливаются на deactivate.
4. В `command_response.details` отдавать `sensor_mode_active: bool` (опционально `note` при идемпотентном повторном вызове).

**Подписка (как в firmware `mqtt_manager.c`):**

```c
// Одна подписка покрывает и ph_sensor/command, и system/command
mqtt_subscribe("hydro/gh-1/zn-1/nd-ph-1/+/command");
```

Wildcard `+/command` **захватывает** `system/command`: сегмент `system` — обычный `{channel}` одного уровня.

- `hydro/.../nd-ph-1/+/command` → матчит `ph_sensor/command`, `pump_ph_up/command`, **`system/command`** и т.д.
- Отдельная подписка на `.../system/command` **не требуется** (в production firmware её нет).

**Инициализация подписки при подключении:**

```c
void mqtt_on_connected(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    char topic_channels[128];
    snprintf(topic_channels, sizeof(topic_channels),
             "hydro/%s/%s/%s/+/command",
             config->greenhouse_uid, config->zone_uid, config->node_uid);
    esp_mqtt_client_subscribe(mqtt_client, topic_channels, 1);

    ESP_LOGI(TAG, "Subscribed to channel commands (incl. system): %s", topic_channels);
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
- `error_code` (string) — машинночитаемый код ошибки для `status=ERROR` (полный каталог русских текстов: `backend/node_error_codes.json`, слияние в `backend/error_codes.json`; см. `doc_ai/04_BACKEND_CORE/ERROR_CODE_CATALOG.md` § Фаза 5)
- `error_message` (string) — человекочитаемое пояснение для `status=ERROR`
- `message` (string) — краткое top-level сообщение; допустимо как runtime fallback для `error_message`

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
  "ts": 1710003399123,
  "error_code": "timestamp_expired",
  "error_message": "Command timestamp is outside acceptable range"
}
```

## 8.2.2. Формат `command_response` для `cmd=state` (IRR)

Для `cmd=state` узел типа `irrig` возвращает snapshot:

```json
{
  "cmd_id": "cmd-598",
  "status": "DONE",
  "details": {
    "snapshot": {
      "clean_level_max": true,
      "clean_level_min": true,
      "solution_level_max": false,
      "solution_level_min": true,
      "valve_clean_fill": false,
      "valve_clean_supply": true,
      "valve_solution_fill": true,
      "valve_solution_supply": false,
      "valve_irrigation": false,
      "pump_main": true
    },
    "sample_ts": 1710003399
  },
  "ts": 1710003399123
}
```

Требования:
- поля `snapshot.*` — `bool`;
- отсутствие поля в snapshot трактуется как `unknown` на стороне backend;
- `sample_ts` используется для freshness-check в automation-engine.

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

Статусы `ACCEPTED` и `FAILED` (вне канона) запрещены.
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

Для production `storage_irrigation_node` правила такие:

1. `set_relay {state:true}` на actuator-каналах IRR-профиля работает как latched `ON/OFF` semantics и не должен
   локально auto-stop'иться по `max_duration_ms`.
1.1. Явный diagnostic/test path `set_relay {state:true, duration_ms}` допустим для actuator-каналов IRR-профиля:
   - immediate ответ: `ACK`;
   - нода держит канал включённым `duration_ms`;
   - затем нода сама возвращает канал в `OFF` и публикует terminal `DONE` по тому же `cmd_id`;
   - если вернуть канал в `OFF` не удалось, нода публикует terminal `ERROR`.
   - для `pump_main` bypass interlock разрешён только при `duration_ms<=3000` и только для manual dry-run smoke path;
     обычный `pump_main ON` без открытого flow path остаётся `ERROR/pump_interlock_blocked`.
2. `pump_main/set_relay {state:true, timeout_ms, stage}` используется для stage-level guard (stage-arm):
   - поддерживаются только `stage="solution_fill"` и `stage="prepare_recirculation"`;
   - immediate terminal ответ: `DONE` (AE3 ждёт `DONE`; `complete_on_ack` deprecated);
   - guard остаётся armed: нода держит flow-path до явного `pump_main OFF`, fail-safe stop или истечения `timeout_ms`;
   - при timeout / fail-safe stop нода останавливает stage-path, снимает guard и публикует
     `storage_state/event` (`solution_fill_timeout` / `prepare_recirculation_timeout` или fail-safe code)
     **без** второго terminal по arm-`cmd_id`;
   - явный `pump_main OFF` (другой `cmd_id`) снимает guard и может дополнительно опубликовать
     `DONE` для arm-`cmd_id` с `details.reason_code=stage_stopped_by_command`.
3. Для `clean_fill` проверка `level_clean_min` / публикация `clean_fill_source_empty` **не применяется**
   (поле `clean_fill_min_check_delay_ms` deprecated, mirror-only). Пустой источник определяется AE3
   через `clean_fill_timeout_sec` + `clean_fill_retry_cycles`.
4. `level_clean_max` локально завершает `clean_fill` (`valve_clean_fill -> OFF`), снимает stage-guard
   и публикует `clean_fill_completed` один раз на эпизод `clean_fill`.
5. Для `solution_fill` после `solution_fill_clean_min_check_delay_ms` нода обязана **непрерывно**
   проверять `level_clean_min` на каждом fail-safe scan до terminal event;
   если датчик `0`, нода локально выключает `pump_main/valve_solution_fill/valve_clean_supply`,
   снимает stage-guard и публикует `solution_fill_source_empty`.
6. Для `solution_fill` после `solution_fill_solution_min_check_delay_ms` нода обязана **непрерывно**
   проверять `level_solution_min` на каждом fail-safe scan до terminal event;
   если датчик `0`, нода локально выключает `pump_main/valve_solution_fill/valve_clean_supply`,
   снимает stage-guard и публикует `solution_fill_leak_detected`.
7. `level_solution_max` локально завершает `solution_fill`
   (`pump_main/valve_solution_fill/valve_clean_supply -> OFF`), снимает stage-guard и публикует
   `solution_fill_completed` один раз на эпизод `solution_fill`.
8. Для `prepare_recirculation` при включённом `recirculation_solution_min_guard_enabled`
   нода обязана остановить stage по `level_solution_min=0`, снять stage-guard и опубликовать
   `recirculation_solution_low`.
9. Для `irrigation` при включённом `irrigation_solution_min_guard_enabled`
   нода обязана остановить stage по `level_solution_min=0`, снять stage-guard и опубликовать
   `irrigation_solution_low`.
10. Пока физическая кнопка `E-Stop` удерживается нажатой, нода обязана держать все актуаторы в `OFF`;
    на момент нажатия публикуется `emergency_stop_activated`. Новые `set_relay {state:true}`
    отклоняются с `ERROR` / `error_code=estop_active`; OFF-команды разрешены.
11. Для каждого подтверждённого изменения любого `level_*` датчика нода публикует отдельное channel-level событие:

Топик:
```text
hydro/{gh}/{zone}/{node}/{level_channel}/event
```

Payload:
```json
{
  "event_code": "level_switch_changed",
  "channel": "level_clean_min",
  "state": true,
  "initial": false,
  "ts": 1710003398,
  "snapshot": {
    "clean_level_min": true,
    "clean_level_max": false,
    "solution_level_min": false,
    "solution_level_max": false,
    "pump_main": false
  }
}
```

Правила:
- событие публикуется на оба фронта: `0 -> 1` и `1 -> 0`;
- `state` содержит уже подтверждённое debounce-состояние;
- после boot/reconnect нода обязана один раз опубликовать initial-state событие для каждого
  из четырёх `level_*` каналов после завершения time sync;
- `snapshot` использует тот же `IRR_STATE_SNAPSHOT`, что и `storage_state/event`.

12. Дополнительно нода публикует aggregate событие (канал `storage_state`):

Топик:
```text
hydro/{gh}/{zone}/{node}/storage_state/event
```

Payload:
```json
{
  "event_code": "clean_fill_completed",
  "ts": 1710003399,
  "snapshot": {
    "clean_level_min": true,
    "clean_level_max": true,
    "solution_level_min": false,
    "solution_level_max": false,
    "pump_main": false
  },
  "state": {
    "level_clean_min": 1,
    "level_clean_max": 1,
    "level_solution_min": 0,
    "level_solution_max": 0
  }
}
```

Для `storage_state/event` `event_code` принимает, в том числе, одно из значений:

- `clean_fill_completed` (production `storage_irrigation_node`)
- `clean_fill_source_empty` (**legacy/compat**; production-нода не публикует — AE3 timeout/retry)
- `solution_fill_source_empty`
- `solution_fill_leak_detected`
- `solution_fill_completed`
- `recirculation_solution_low`
- `irrigation_solution_low`
- `solution_fill_timeout`
- `prepare_recirculation_timeout`
- `emergency_stop_activated`

Нормализация в backend (`history-logger`):
- `event_code` (или fallback-поля `event`/`type`) преобразуется в `zone_events.type`;
- преобразование: `UPPERCASE` + все не `[A-Z0-9]` символы заменяются на `_` + схлопывание повторов `_`;
- пример: `clean fill-completed/v2` -> `CLEAN_FILL_COMPLETED_V2`;
- если код пустой, используется `NODE_EVENT`.
- для `zone_events.type` действует лимит 255 символов: если нормализованный код длиннее, он усечётся
  детерминированно и получит suffix `_{SHA1_10}` (первые 10 hex-символов SHA1).

Метрика приёма событий (`node_event_received_total{event_code=...}`):
- в label попадают только whitelisted коды событий двухбакового контура, включая `level_switch_changed`;
- все остальные коды агрегируются в `event_code="OTHER"` для контроля кардинальности Prometheus.

Назначение:
- automation-engine использует это событие как fast-path подтверждение;
- scheduler/automation сохраняют периодический poll как резервный канал контроля.
- history-logger извлекает snapshot состояния из `snapshot` (предпочтительно) или `state` (запасной ключ).

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
- Алиасы `node_type` вне канона не поддерживаются.

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
  "rssi": -62,
  "fw_version": "1.0.0"
}
```

**Обязательные поля:**
- `uptime` (integer) — время работы узла в секундах (не миллисекунды)
- `free_heap` (integer) — свободная память в байтах

**Опциональные поля:**
- `rssi` (integer) — сила сигнала Wi-Fi в dBm (от -100 до 0)
- `fw_version` (string) — версия прикладной прошивки, которую сообщает сама нода; backend не задаёт её вручную и только сохраняет последнее полученное значение.

> **Важно:** Поле `ts` **не включается** в heartbeat согласно эталону node-sim. Формат соответствует эталону, который успешно проходит E2E тесты.

**Requirements:**
- QoS = 1 (обновлено: было 0, теперь 1 для надёжности)
- Retain = false
- Backend обновляет поля `last_heartbeat_at`, `uptime_seconds`, `free_heap_bytes`, `rssi`, `fw_version` в таблице `nodes`
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
| config (backend → node) | 1 | false |
| status | 1 | true |
| lwt | 1 | true |
| node_hello | 1 | false |
| heartbeat | 1 | false |
| event (channel-level) | 1 | false |
| storage_state/event (`channel=storage_state`) | 1 | false |
| diagnostics | 1 | false |
| error | 1 | false |
| system/command (`channel=system`) | 1 | false |
| hydro/time/request | 1 | false |
| hydro/time/response | 1 | false |

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
- `hydro/{gh}/{zone}/{node}/config` — получение NodeConfig push (bind/rebind/unbind, обновление mirror)
- `hydro/time/response` — синхронизация времени перед публикацией `status`/`telemetry`/`event` с `ts`

## 13.2. Публикации (обязательные)

Узел **ОБЯЗАН** публиковать:

### После time sync (канон §4.2: connect → time request/response → status):
- **status** (`hydro/{gh}/{zone}/{node}/status`) — **ОБЯЗАТЕЛЬНО** после `hydro/time/response`, не сразу после `MQTT_EVENT_CONNECTED`

### Регулярно:
- **telemetry** (`hydro/{gh}/{zone}/{node}/{channel}/telemetry`) — по расписанию из NodeConfig
- **heartbeat** (`hydro/{gh}/{zone}/{node}/heartbeat`) — периодически (например, каждые 30 секунд)
- **diagnostics** (`hydro/{gh}/{zone}/{node}/diagnostics`) — опционально, для structured engineering snapshots, не совместимых с scalar telemetry contract

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
- публиковать целевой NodeConfig на `.../config` через history-logger (`PublishNodeConfigJob` и related)
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
