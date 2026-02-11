# MQTT_NAMESPACE.md
# Полный справочник MQTT-топиков для системы 2.0

Документ описывает **единый MQTT-namespace**, используемый всеми компонентами:

- узлами ESP32,
- Python-сервисом,
- backend-сервисами.

Frontend и Android **не** обращаются к MQTT напрямую.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

---

## 1. Базовый формат топиков

Общий паттерн для сообщений уровня канала (channel-level):

```text
hydro/{gh}/{zone}/{node}/{channel}/{message_type}
```

Для сообщений уровня узла (node-level, без канала) используется паттерн:

```text
hydro/{gh}/{zone}/{node}/{message_type}
```

Где:

- `{gh}` — UID теплицы (`greenhouses.uid`),
- `{zone}` — UID зоны (`zones.uid`),
- `{node}` — UID узла (`nodes.uid`),
- `{channel}` — ключ канала (`channels.key`), используется только для channel-level сообщений,
- `{message_type}` — тип сообщения: 
 `telemetry`, `command`, `status`, `event`, `config` и т.п.

**Все сегменты строчные, без пробелов, с `-` или `_` по необходимости.**

---

## 2. Типы сообщений

### 2.1. telemetry

Отправитель: **узел ESP32** 
Получатель: **Python-сервис**

Топик:

```text
hydro/{gh}/{zone}/{node}/{channel}/telemetry
```

Payload (пример):

```json
{
 "metric_type": "TEMPERATURE",
 "value": 23.4,
 "ts": 1737355600
}
```

> **Важно:** Формат соответствует эталону node-sim. Поля `node_id` и `channel` не включаются в JSON, так как они уже есть в топике. `metric_type` передается в UPPERCASE.

### 2.2. command

Отправитель: **Python-сервис / Backend** 
Получатель: **узел ESP32**

```text
hydro/{gh}/{zone}/{node}/{channel}/command
```

Payload (пример):

```json
{
 "cmd_id": "cmd-2025-01-01-12-00-00-001",
 "cmd": "set_pwm",
 "params": {
   "value": 128
 },
 "ts": 1737355112,
 "sig": "a1b2c3d4e5f6..."
}
```

### 2.3. status

Отправитель: **узел ESP32** 
Получатель: **Python-сервис**

```text
hydro/{gh}/{zone}/{node}/status
```

Payload (пример):

```json
{
 "status": "ONLINE",
 "ts": 1710001555
}
```

> `status` является node-level сообщением и публикуется без сегмента `{channel}`.

### 2.4. event

Отправитель: **узел ESP32 / Python-сервис** 
Получатель: **Python-сервис / Backend**

```text
hydro/{gh}/{zone}/{node}/{channel}/event
```

Примеры событий:

- `SENSOR_ERROR`, `SENSOR_CALIBRATION_REQUIRED`;
- `ACTUATOR_FAULT`, `PUMP_OVERCURRENT`;
- `PH_DRIFT_TOO_HIGH`, `EC_OUT_OF_RANGE`.

---

## 3. Системный namespace

Для служебных задач вводится отдельная ветка:

```text
hydro/system/{subtopic}
```

Примеры:

- `hydro/system/ota/{node_uid}` — управление OTA;
- `hydro/system/announce/{node_uid}` — объявление новых узлов;
- `hydro/system/health/{node_uid}` — отчёт о состоянии узла;
- `hydro/system/metrics/{service}` — метрики Python-сервиса и backend.

---

## 4. Правила именования каналов

Ключи каналов (`{channel}`) соответствуют полю `channels.key` и описаны в
`../02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`.

Примеры:

- `ph_main`;
- `ec_main`;
- `temp_air`, `temp_water`;
- `pump_acid`, `pump_base`, `pump_a`, `pump_b`, `pump_c`, `pump_d`;
- `fan_in`, `fan_out`;
- `light_main`.

**Запрещается**:

- использовать случайные ключи без отражения в БД;
- вводить новые каналы без правки справочника каналов и миграций.

---

## 5. Версионирование протокола

Для будущих изменений возможен формат:

```text
hydro/v2/{gh}/{zone}/{node}/{channel}/{message_type}
```

Но по умолчанию используется **v1 без явного сегмента**.

Конкретные изменения протокола должны быть задокументированы и отражены в:

- `../05_DATA_AND_STORAGE/TELEMETRY_PIPELINE.md`,
- `../02_HARDWARE_FIRMWARE/NODE_CHANNELS_REFERENCE.md`,
- `../10_AI_DEV_GUIDES/MQTT_TOPICS_SPEC_AI_GUIDE.md`.

---

## 6. Правила для ИИ-агентов

1. Не менять базовые паттерны:
 - channel-level: `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`;
 - node-level: `hydro/{gh}/{zone}/{node}/{message_type}`.
2. Любые новые темы должны быть расширением, а не заменой.
3. Все изменения должны быть:

 - согласованы с `../05_DATA_AND_STORAGE/DATA_MODEL_REFERENCE.md`;
 - отражены в `../10_AI_DEV_GUIDES/PYTHON_MQTT_SERVICE_AI_GUIDE.md` и `../10_AI_DEV_GUIDES/MQTT_TOPICS_SPEC_AI_GUIDE.md`.

MQTT-namespace — это **хребет системы 2.0**, поэтому изменения здесь должны происходить крайне аккуратно.
