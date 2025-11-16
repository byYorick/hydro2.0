# DATA_MODEL_REFERENCE.md
# Полный справочник моделей данных системы 2.0
# PostgreSQL • Laravel Models • Python ORM • Связи • Ограничения

Документ описывает всю структуру данных системы 2.0:
таблицы, связи, ключи, индексы, правила и использование.

---

# 1. Общая архитектура данных

Основные домены:

1. **Zones** — тепличные зоны
2. **Nodes** — узлы ESP32
3. **Channels** — сенсоры и актуаторы
4. **Telemetry** — данные сенсоров
5. **Recipes** — программы роста
6. **Alerts & Events** — тревоги и события
7. **Commands** — команды к узлам
8. **Users & Roles** — учетные записи
9. **OTA Firmware** — прошивки узлов

---

# 2. Таблицы теплиц и зон

## 2.1. greenhouses

```
id BIGSERIAL PK
uid VARCHAR(64) UNIQUE
name VARCHAR
timezone VARCHAR
type VARCHAR (GREENHOUSE, ROOM, FARM)
coordinates JSONB
description TEXT
created_at
updated_at
```

Связи:

- hasMany zones
- hasMany nodes (через zones или напрямую в будущем, если потребуется)

Практика:

- `uid` используется в MQTT как сегмент `{gh}`.
- В Backend/AI `greenhouse.uid` — основной внешний идентификатор теплицы.

---

## 2.2. zones

```
id BIGSERIAL PK
name VARCHAR
description TEXT
status VARCHAR (online/offline/warning/critical)
created_at
updated_at
```

Индексы:
```
zones_status_idx
```

---

# 3. Таблицы узлов

## 3.1. nodes

```
id BIGSERIAL PK
zone_id BIGINT FK → zones
uid VARCHAR(64) UNIQUE -- внешний строковый ID узла, совпадает с сегментом {node} в MQTT
name VARCHAR
type VARCHAR (ph, ec, climate, irrig, light)
fw_version VARCHAR
last_seen_at TIMESTAMP
status VARCHAR (online/offline)
config JSONB
created_at
updated_at
```

Семантика идентификаторов:

- `id` — внутренний числовой PK, не используется во внешних API.
- `uid` — стабильный внешний идентификатор узла:
 - используется в MQTT как сегмент `{node}`;
 - передаётся в конфигурации узла (NodeConfig) и команды;
 - применяется Backend/AI как основной внешний ключ при адресации узла.

## 3.2. node_channels

```
id BIGSERIAL PK
node_id FK → nodes
channel VARCHAR
type VARCHAR (sensor/actuator)
metric VARCHAR (PH, EC, TEMP_AIR…)
unit VARCHAR
config JSONB
created_at
updated_at
```

---

# 4. Таблицы телеметрии

## 4.1. telemetry_samples (история)

```
id BIGSERIAL PK
zone_id FK
node_id FK
channel VARCHAR
metric_type VARCHAR
value FLOAT
raw JSONB
ts TIMESTAMP
created_at
```

Индексы:
```
telemetry_samples_zone_metric_ts_idx
```

---

## 4.2. telemetry_last (последние значения)

```
zone_id PK
metric_type PK
node_id
channel
value FLOAT
updated_at
```

---

# 5. Таблицы рецептов

## 5.1. recipes
```
id PK
name
description
created_at
```

## 5.2. recipe_phases
```
id PK
recipe_id FK
phase_index INT
name
duration_hours INT
targets JSONB
created_at
```

## 5.3. zone_recipe_instances
```
id PK
zone_id FK
recipe_id FK
current_phase_index INT
started_at
updated_at
```

---

# 6. Таблицы команд (Commands)

## 6.1. commands

```
id PK
zone_id FK
node_id FK
channel VARCHAR
cmd VARCHAR
params JSONB
status VARCHAR (pending/sent/ack/failed)
cmd_id VARCHAR UNIQUE
created_at
sent_at
ack_at
failed_at
```

Индексы:
```
commands_status_idx
commands_cmd_id_idx
```

---

# 7. Таблицы тревог (Alerts)

## 7.1. alerts

```
id PK
zone_id FK
type VARCHAR
details JSONB
status VARCHAR (ACTIVE/RESOLVED)
created_at
resolved_at
```

Индексы:
```
alerts_zone_status_idx
```

---

# 8. Таблицы событий (Events)

## 8.1. zone_events

```
id PK
zone_id FK
type VARCHAR
details JSONB
created_at
```

---

# 9. Пользователи и роли

## 9.1. users

```
id PK
name
email UNIQUE
password
role VARCHAR (admin/operator/viewer/automation_bot)
created_at
updated_at
```

---

# 10. OTA прошивки

## 10.1. firmware_files
```
id PK
node_type VARCHAR
version VARCHAR
file_path VARCHAR
checksum_sha256 VARCHAR
release_notes TEXT
created_at
```

---

# 11. Ключевые связи

```
zone 1—N nodes
node 1—N channels
zone 1—N telemetry
zone 1—N alerts
zone 1—N events
recipe 1—N phases
zone 1—1 recipe_instance
zone 1—N commands
```

---

# 12. Использование данных в Laravel

Laravel модели:

- Zone
- Node
- NodeChannel
- TelemetrySample
- TelemetryLast
- Recipe
- RecipePhase
- ZoneRecipeInstance
- Alert
- ZoneEvent
- Command
- FirmwareFile

Все используют Eloquent ORM.

---

# 13. Использование данных в Python Scheduler

Python читает:

- zones
- nodes + node_channels
- telemetry_last
- recipe instances
- alerts
- commands

И пишет:

- telemetry_samples
- telemetry_last
- alerts
- events
- commands (через API или прямую запись)

---

# 14. Правила для ИИ

ИИ может:

- добавлять новые модели,
- расширять JSONB поля,
- добавлять индексы,
- вводить новые связи,

ИИ не может:

- менять существующие поля без backward-compatibility,
- удалять таблицы,
- переименовывать критические поля.

---

# Конец файла DATA_MODEL_REFERENCE.md
