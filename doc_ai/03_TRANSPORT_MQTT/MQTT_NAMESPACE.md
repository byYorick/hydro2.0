# MQTT_NAMESPACE.md
# Полный справочник MQTT-топиков для системы 2.0

Документ описывает **единый MQTT-namespace**, используемый всеми компонентами:

- узлами ESP32,
- Python-сервисом,
- backend-сервисами.

Frontend и Android **не** обращаются к MQTT напрямую.

---

## 1. Базовый формат топиков

Общий паттерн:

```text
hydro/{gh}/{zone}/{node}/{channel}/{message_type}
```

Где:

- `{gh}` — UID теплицы (`greenhouses.uid`),
- `{zone}` — UID зоны (`zones.uid`),
- `{node}` — UID узла (`nodes.uid`),
- `{channel}` — ключ канала (`channels.key`),
- `{message_type}` — тип сообщения: 
 `telemetry`, `command`, `status`, `event`, `config` и т.п.

**Все сегменты строчные, без пробелов, с `-` или `_` по необходимости.**

---

## 2. Типы сообщений по каналам

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
 "value": 23.4,
 "metric": "TEMP_AIR",
 "ts": 1737355600456
}
```

### 2.2. command

Отправитель: **Python-сервис / Backend** 
Получатель: **узел ESP32**

```text
hydro/{gh}/{zone}/{node}/{channel}/command
```

Payload (пример):

```json
{
 "cmd": "SET_PWM",
 "value": 128,
 "ttl_ms": 5000,
 "reason": "ZONE_PH_CORRECTION",
 "request_id": "cmd-2025-01-01-12-00-00-001"
}
```

### 2.3. status

Отправитель: **узел ESP32** 
Получатель: **Python-сервис**

```text
hydro/{gh}/{zone}/{node}/{channel}/status
```

Payload (пример):

```json
{
 "request_id": "cmd-2025-01-01-12-00-00-001",
 "status": "OK",
 "ts": 1737355601123
}
```

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
`NODE_CHANNELS_REFERENCE.md`.

Примеры:

- `ph_main`;
- `ec_main`;
- `temp_air`, `temp_water`;
- `pump_acid`, `pump_base`, `pump_nutrient`;
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

- `TELEMETRY_PIPELINE.md`,
- `NODE_CHANNELS_REFERENCE.md`,
- `MQTT_TOPICS_SPEC_AI_GUIDE.md`.

---

## 6. Правила для ИИ-агентов

1. Не менять базовый паттерн `hydro/{gh}/{zone}/{node}/{channel}/{message_type}`.
2. Любые новые темы должны быть расширением, а не заменой.
3. Все изменения должны быть:

 - согласованы с `DATA_MODEL_REFERENCE.md`;
 - отражены в `PYTHON_MQTT_SERVICE_AI_GUIDE.md` и `MQTT_TOPICS_SPEC_AI_GUIDE.md`.

MQTT-namespace — это **хребет системы 2.0**, поэтому изменения здесь должны происходить крайне аккуратно.
