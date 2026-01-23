# DATA_MODEL_REFERENCE.md
# Полный справочник моделей данных системы 2.0
# PostgreSQL • Laravel Models • Python ORM • Связи • Ограничения
# **ОБНОВЛЕНО ПОСЛЕ МЕГА-РЕФАКТОРИНГА 2025-12-25**

Документ описывает всю структуру данных системы 2.0:
таблицы, связи, ключи, индексы, правила и использование.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

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
greenhouse_id BIGINT FK -> greenhouses
preset_id BIGINT FK -> presets
uid VARCHAR(64) UNIQUE
name VARCHAR
description TEXT
status VARCHAR (online/offline/warning/critical)
water_state VARCHAR (NORMAL_RECIRC/WATER_CHANGE_DRAIN/WATER_CHANGE_FILL/WATER_CHANGE_STABILIZE)
solution_started_at TIMESTAMP
health_score NUMERIC(5,2)
health_status VARCHAR(16)
hardware_profile JSONB
capabilities JSONB
settings JSONB
created_at
updated_at
```

Индексы:
```
zones_status_idx
zones_uid_unique
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
error_count INTEGER DEFAULT 0
warning_count INTEGER DEFAULT 0
critical_count INTEGER DEFAULT 0
created_at
updated_at
```

Индексы:
```
nodes_zone_id_idx (zone_id) WHERE zone_id IS NOT NULL
nodes_zone_type_idx (zone_id, type) WHERE zone_id IS NOT NULL AND type IS NOT NULL
nodes_zone_status_idx (zone_id, status) WHERE zone_id IS NOT NULL
nodes_last_seen_at_idx (last_seen_at) WHERE last_seen_at IS NOT NULL
nodes_type_idx (type) WHERE type IS NOT NULL
nodes_status_idx (status) -- уже существует
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
metric VARCHAR (PH, EC, TEMPERATURE…)
unit VARCHAR
config JSONB
created_at
updated_at
```

---

# 4. Таблицы телеметрии

## 4.1. sensors (идентичность сенсора)

```
id BIGSERIAL PK
greenhouse_id FK
zone_id FK NULL
node_id FK NULL
scope ENUM(inside|outside)
type ENUM(TEMPERATURE|HUMIDITY|CO2|PH|EC|WATER_LEVEL|...)
label VARCHAR
unit VARCHAR NULL
specs JSONB NULL
is_active BOOLEAN
last_read_at TIMESTAMP NULL
created_at
updated_at
```

Индексы:
```
sensors_zone_idx
sensors_greenhouse_scope_idx
sensors_greenhouse_type_idx
sensors_node_idx
sensors_active_idx
UNIQUE(zone_id, node_id, scope, type, label)
```

---

## 4.2. telemetry_samples (история)

```
id BIGSERIAL PK
sensor_id FK
ts TIMESTAMP
zone_id FK NULL
cycle_id FK NULL
value DECIMAL
quality ENUM(GOOD|BAD|UNCERTAIN)
metadata JSONB
created_at
```

Индексы:
```
telemetry_samples_sensor_ts_idx
telemetry_samples_zone_ts_idx
telemetry_samples_cycle_ts_idx
```

---

## 4.3. telemetry_last (последние значения)

```
sensor_id PK FK
last_value DECIMAL
last_ts TIMESTAMP
last_quality ENUM
updated_at
```

---

# 5. Таблицы рецептов (новая модель после рефакторинга)

## 5.1. recipes
```
id BIGSERIAL PK
name VARCHAR
description TEXT
plant_id BIGINT FK → plants (опционально)
metadata JSONB
created_by BIGINT FK → users
created_at TIMESTAMP
updated_at TIMESTAMP
```

## 5.2. recipe_revisions (версии рецептов)
```
id BIGSERIAL PK
recipe_id BIGINT FK → recipes CASCADE
revision_number INT DEFAULT 1
status ENUM('DRAFT', 'PUBLISHED', 'ARCHIVED') DEFAULT 'DRAFT'
description TEXT
created_by BIGINT FK → users NULL
published_at TIMESTAMP NULL
created_at TIMESTAMP
updated_at TIMESTAMP

UNIQUE: (recipe_id, revision_number)
INDEX: (recipe_id, status)
```

## 5.3. recipe_revision_phases (шаблоны фаз)
```
id BIGSERIAL PK
recipe_revision_id BIGINT FK → recipe_revisions CASCADE
phase_index INT DEFAULT 0
name VARCHAR
stage_template_id BIGINT FK → grow_stage_templates NULL

-- Целевые параметры по колонкам (не JSON!)
ph_target DECIMAL(4,2) NULL
ph_min DECIMAL(4,2) NULL
ph_max DECIMAL(4,2) NULL
ec_target DECIMAL(5,2) NULL
ec_min DECIMAL(5,2) NULL
ec_max DECIMAL(5,2) NULL
irrigation_mode ENUM('SUBSTRATE', 'RECIRC') NULL
irrigation_interval_sec INT NULL
irrigation_duration_sec INT NULL
lighting_photoperiod_hours INT NULL
lighting_start_time TIME NULL
mist_interval_sec INT NULL
mist_duration_sec INT NULL
mist_mode ENUM('NORMAL', 'SPRAY') NULL
temp_air_target DECIMAL(5,2) NULL
humidity_target DECIMAL(5,2) NULL
co2_target INT NULL

-- Прогресс
progress_model VARCHAR NULL -- TIME|TIME_WITH_TEMPERATURE_CORRECTION|GDD
duration_hours INT NULL
duration_days INT NULL
base_temp_c DECIMAL(4,2) NULL
target_gdd DECIMAL(8,2) NULL
dli_target DECIMAL(6,2) NULL

-- Расширения
extensions JSONB NULL

created_at TIMESTAMP
updated_at TIMESTAMP

UNIQUE: (recipe_revision_id, phase_index)
INDEX: recipe_revision_phase_idx (recipe_revision_id)
```

## 5.4. recipe_revision_phase_steps (шаги внутри фаз)
```
id BIGSERIAL PK
recipe_revision_phase_id BIGINT FK → recipe_revision_phases CASCADE
step_index INT DEFAULT 0
name VARCHAR
description TEXT
action_type VARCHAR -- IRRIGATION|LIGHTING|MIST|etc
action_params JSONB
offset_hours INT NULL
duration_sec INT NULL

created_at TIMESTAMP
updated_at TIMESTAMP

UNIQUE: (recipe_revision_phase_id, step_index)
INDEX: recipe_revision_phase_step_idx (recipe_revision_phase_id)
```

# 6. Таблицы циклов выращивания (новая модель — центр истины)

## 6.1. grow_cycles (ЦЕНТР ИСТИНЫ)
```
id BIGSERIAL PK
greenhouse_id BIGINT FK → greenhouses
zone_id BIGINT FK → zones
plant_id BIGINT FK → plants
recipe_id BIGINT FK → recipes (legacy, для совместимости)
recipe_revision_id BIGINT FK → recipe_revisions NOT NULL

-- Статус и временные метки
status ENUM('PLANNED', 'RUNNING', 'PAUSED', 'HARVESTED', 'ABORTED', 'COMPLETED')
started_at TIMESTAMP NULL
recipe_started_at TIMESTAMP NULL
expected_harvest_at TIMESTAMP NULL
actual_harvest_at TIMESTAMP NULL
planting_at TIMESTAMP NULL

-- Текущая фаза (ссылки на снапшоты)
current_phase_id BIGINT FK → grow_cycle_phases NULL
current_step_id BIGINT FK → grow_cycle_phase_steps NULL
phase_started_at TIMESTAMP NULL
step_started_at TIMESTAMP NULL

-- Метаданные
batch_label VARCHAR NULL
notes TEXT NULL
settings JSONB NULL
progress_meta JSONB NULL

created_at TIMESTAMP
updated_at TIMESTAMP

-- Критические ограничения
UNIQUE: (zone_id) WHERE status IN ('PLANNED', 'RUNNING', 'PAUSED')
INDEX: grow_cycle_zone_active_idx (zone_id, status)
INDEX: grow_cycle_status_idx (status)
INDEX: grow_cycle_recipe_revision_idx (recipe_revision_id)
```

## 6.2. grow_cycle_phases (снапшоты фаз для конкретного цикла)
```
id BIGSERIAL PK
grow_cycle_id BIGINT FK → grow_cycles CASCADE
recipe_revision_phase_id BIGINT FK → recipe_revision_phases NULL (трассировка)

phase_index INT DEFAULT 0
name VARCHAR

-- Целевые параметры (копия из шаблона)
ph_target DECIMAL(4,2) NULL
ph_min DECIMAL(4,2) NULL
ph_max DECIMAL(4,2) NULL
ec_target DECIMAL(5,2) NULL
ec_min DECIMAL(5,2) NULL
ec_max DECIMAL(5,2) NULL
irrigation_mode ENUM('SUBSTRATE', 'RECIRC') NULL
irrigation_interval_sec INT NULL
irrigation_duration_sec INT NULL
lighting_photoperiod_hours INT NULL
lighting_start_time TIME NULL
mist_interval_sec INT NULL
mist_duration_sec INT NULL
mist_mode ENUM('NORMAL', 'SPRAY') NULL
temp_air_target DECIMAL(5,2) NULL
humidity_target DECIMAL(5,2) NULL
co2_target INT NULL

-- Прогресс
progress_model VARCHAR NULL
duration_hours INT NULL
duration_days INT NULL
base_temp_c DECIMAL(4,2) NULL
target_gdd DECIMAL(8,2) NULL
dli_target DECIMAL(6,2) NULL

extensions JSONB NULL

-- Выполнение в цикле
started_at TIMESTAMP NULL
ended_at TIMESTAMP NULL

created_at TIMESTAMP
updated_at TIMESTAMP

UNIQUE: (grow_cycle_id, phase_index)
INDEX: grow_cycle_phase_cycle_idx (grow_cycle_id)
INDEX: grow_cycle_phase_revision_phase_idx (recipe_revision_phase_id)
```

## 6.3. grow_cycle_phase_steps (снапшоты шагов)
```
id BIGSERIAL PK
grow_cycle_phase_id BIGINT FK → grow_cycle_phases CASCADE
recipe_revision_phase_step_id BIGINT FK → recipe_revision_phase_steps NULL

step_index INT DEFAULT 0
name VARCHAR
description TEXT
action_type VARCHAR
action_params JSONB
offset_hours INT NULL
duration_sec INT NULL

started_at TIMESTAMP NULL
ended_at TIMESTAMP NULL

created_at TIMESTAMP
updated_at TIMESTAMP

UNIQUE: (grow_cycle_phase_id, step_index)
INDEX: grow_cycle_phase_step_phase_idx (grow_cycle_phase_id)
```

## 6.4. grow_cycle_overrides (перекрытия параметров)
```
id BIGSERIAL PK
grow_cycle_id BIGINT FK → grow_cycles CASCADE
parameter VARCHAR -- 'ph.target', 'irrigation.interval_sec', etc
value_type ENUM('numeric', 'string', 'boolean', 'json')
numeric_value DECIMAL(10,4) NULL
string_value VARCHAR NULL
boolean_value BOOLEAN NULL
json_value JSONB NULL

is_active BOOLEAN DEFAULT TRUE
reason TEXT NULL
created_by BIGINT FK → users NULL

created_at TIMESTAMP
updated_at TIMESTAMP

INDEX: grow_cycle_override_cycle_active_idx (grow_cycle_id, is_active)
INDEX: grow_cycle_override_parameter_idx (parameter)
```

## 6.5. grow_cycle_transitions (история переходов фаз)
```
id BIGSERIAL PK
grow_cycle_id BIGINT FK → grow_cycles CASCADE

from_phase_id BIGINT FK → grow_cycle_phases NULL
to_phase_id BIGINT FK → grow_cycle_phases NULL

trigger_type ENUM('CYCLE_CREATED', 'AUTO_ADVANCE', 'MANUAL_SWITCH', 'HARVEST', 'ABORT')
triggered_by BIGINT FK → users NULL
comment TEXT NULL

created_at TIMESTAMP

INDEX: grow_cycle_transition_cycle_idx (grow_cycle_id)
INDEX: grow_cycle_transition_trigger_idx (trigger_type)
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
commands_status_idx (status)
commands_cmd_id_idx (cmd_id) -- UNIQUE
commands_status_created_idx (status, created_at) -- уже существует
commands_zone_status_idx (zone_id, status) -- уже существует
commands_node_status_idx (node_id, status) -- уже существует
commands_created_at_idx (created_at) -- уже существует
commands_sent_at_idx (sent_at) -- уже существует
commands_zone_node_status_idx (zone_id, node_id, status) WHERE zone_id IS NOT NULL AND node_id IS NOT NULL
commands_ack_at_idx (ack_at) WHERE ack_at IS NOT NULL
commands_node_channel_idx (node_id, channel) WHERE node_id IS NOT NULL AND channel IS NOT NULL
```

## 6.2. command_tracking

```
id PK
cmd_id VARCHAR UNIQUE
zone_id FK → zones
command JSONB
status VARCHAR (pending/completed/failed)
sent_at TIMESTAMP
completed_at TIMESTAMP NULL
response JSONB NULL
error TEXT NULL
latency_seconds FLOAT NULL
context JSONB NULL
```

Индексы:
```
idx_command_tracking_zone_id (zone_id)
idx_command_tracking_status (status)
idx_command_tracking_sent_at (sent_at)
idx_command_tracking_cmd_id (cmd_id)
```

## 6.3. command_audit

```
id PK
zone_id FK → zones
command_type VARCHAR
command_data JSONB
telemetry_snapshot JSONB NULL
decision_context JSONB NULL
pid_state JSONB NULL
created_at TIMESTAMP
```

Индексы:
```
idx_command_audit_zone_id (zone_id)
idx_command_audit_created_at (created_at)
idx_command_audit_command_type (command_type)
```

## 6.4. pid_state

```
zone_id FK → zones
pid_type VARCHAR (ph/ec)
integral FLOAT DEFAULT 0
prev_error FLOAT NULL
last_output_ms BIGINT DEFAULT 0
stats JSONB NULL
current_zone VARCHAR NULL
created_at TIMESTAMP
updated_at TIMESTAMP
PK (zone_id, pid_type)
```

Индексы:
```
idx_pid_state_zone_id (zone_id)
idx_pid_state_updated_at (updated_at)
```

## 6.5. zone_automation_state

```
zone_id FK → zones
state JSONB NULL
created_at TIMESTAMP
updated_at TIMESTAMP
PK (zone_id)
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

# 11. Ключевые связи (обновлено после рефакторинга)

**Основная доменная модель:**
```
greenhouse 1—N zones
zone 1—1 grow_cycle (активный: PLANNED/RUNNING/PAUSED)
grow_cycle 1—1 recipe_revision (зафиксированная версия)
recipe 1—N recipe_revisions
recipe_revision 1—N recipe_revision_phases
recipe_revision_phase 1—N recipe_revision_phase_steps

grow_cycle 1—N grow_cycle_phases (снапшоты)
grow_cycle_phase 1—N grow_cycle_phase_steps (снапшоты)
grow_cycle 1—N grow_cycle_overrides
grow_cycle 1—N grow_cycle_transitions
```

**Оборудование и телеметрия:**
```
zone 1—N nodes (1 node = 1 zone enforced)
node 1—N node_channels
greenhouse 1—N sensors
zone 1—N sensors
node 1—N sensors
sensor 1—N telemetry_samples
sensor 1—1 telemetry_last
zone 1—N alerts
zone 1—N zone_events
zone 1—N commands
```

**Инфраструктура (новая модель):**
```
infrastructure_instance (polymorphic: owner_type='zone'|'greenhouse')
infrastructure_instance 1—N channel_bindings
channel_binding 1—1 node_channel
```

---

# 12. Использование данных в Laravel (обновлено)

**Laravel модели (новая модель):**

- **GrowCycle** — центр истины, содержит всю логику цикла
- **GrowCyclePhase** — снапшоты фаз для цикла
- **GrowCyclePhaseStep** — снапшоты шагов
- **GrowCycleOverride** — перекрытия параметров
- **GrowCycleTransition** — история переходов

- **RecipeRevision** — версии рецептов (DRAFT/PUBLISHED/ARCHIVED)
- **RecipeRevisionPhase** — шаблоны фаз с целями по колонкам
- **RecipeRevisionPhaseStep** — шаблоны шагов

- **InfrastructureInstance** — полиморфная инфраструктура (zone/greenhouse)
- **ChannelBinding** — привязки каналов к инфраструктуре

**Устаревшие модели (удалены после рефакторинга):**
- ❌ ZoneRecipeInstance
- ❌ RecipePhase (legacy JSON targets)
- ❌ ZoneCycle
- ❌ PlantCycle

**Сервисы:**
- **EffectiveTargetsService** — единый контракт для Python сервисов
- **GrowCycleService** — управление циклами и создание снапшотов

Все используют Eloquent ORM с proper type casting.

---

# 13. Использование данных в Python сервисах (обновлено)

**Python сервисы теперь используют Laravel API вместо прямых SQL запросов:**

**Основной контракт:**
- `GET /api/internal/effective-targets/batch` — batch получение effective targets для зон
- Возвращает цели из активного цикла с учётом overrides

**Структура ответа:**
```json
{
  "zone_id": 123,
  "cycle_id": 456,
  "phase": {
    "id": 789,
    "code": "VEG",
    "name": "Вегетация",
    "started_at": "2025-01-01T10:00:00Z",
    "due_at": "2025-01-15T10:00:00Z"
  },
  "targets": {
    "ph": {"target": 6.0, "min": 5.8, "max": 6.2},
    "ec": {"target": 1.5, "min": 1.3, "max": 1.7},
    "irrigation": {"mode": "SUBSTRATE", "interval_sec": 3600, "duration_sec": 300}
    // ... остальные цели
  }
}
```

**Устаревший подход (до рефакторинга):**
- ❌ Прямые SQL запросы к `zone_recipe_instances` + `recipe_phases.targets`
- ✅ Заменён на Laravel API для consistency и версионирования

---

# 14. Transaction Isolation и Concurrency Control

## 14.1. SERIALIZABLE Isolation Level

Для критичных операций используется **SERIALIZABLE** isolation level с автоматическим retry на serialization failures.

### Критичные операции:

1. **PublishNodeConfigJob** - публикация конфигурации узла
   - Использует `TransactionHelper::withSerializableRetry()` с advisory lock
   - Advisory lock: `pg_try_advisory_xact_lock(crc32("publish_config:{node_id}"))`
   - Retry: до 5 попыток с exponential backoff

2. **NodeService::update()** - обновление узла
   - Использует `TransactionHelper::withSerializableRetry()`
   - Блокировка строки: `SELECT ... FOR UPDATE`
   - Retry: до 5 попыток с exponential backoff

3. **NodeLifecycleService::transition()** - переход состояния узла
   - Использует `TransactionHelper::withSerializableRetry()`
   - Retry: до 5 попыток с exponential backoff

### Advisory Locks

PostgreSQL advisory locks используются для предотвращения конкурентного выполнения критичных операций:

- **Publish Config**: `pg_try_advisory_xact_lock(crc32("publish_config:{node_id}"))`
  - Гарантирует, что конфиг публикуется только один раз
  - Автоматически освобождается при завершении транзакции

### Retry Logic

`TransactionHelper::withSerializableRetry()` автоматически обрабатывает serialization failures:

- **PostgreSQL Error Codes**: `40001` (serialization failure), `40P01` (deadlock detected)
- **Retry Strategy**: Exponential backoff (50ms, 100ms, 200ms, 400ms, 800ms)
- **Max Retries**: 5 попыток по умолчанию
- **Logging**: Все retry попытки логируются с предупреждением

### Пример использования:

```php
use App\Helpers\TransactionHelper;

// С SERIALIZABLE isolation и retry
$result = TransactionHelper::withSerializableRetry(function () {
    // Критичная операция
    return DB::transaction(function () {
        // ...
    });
});

// С advisory lock
$result = TransactionHelper::withAdvisoryLock("operation:{$id}", function () {
    // Операция под блокировкой
});
```

---

# 15. Правила для ИИ (после рефакторинга)

**ИИ может:**
- Добавлять новые модели в доменную модель GrowCycle
- Создавать новые версии рецептов через RecipeRevision
- Добавлять поля в effective targets контракт
- Расширять JSONB поля (extensions, progress_meta)
- Добавлять индексы для performance
- Вводить новые связи между сущностями
- Использовать `TransactionHelper` для критичных операций
- Обновлять Laravel API endpoints с сохранением контракта

**ИИ не может:**
- Менять существующие поля без обновления всех зависимостей
- Удалять таблицы или поля из активной модели
- Переименовывать критические поля (recipe_revision_id, current_phase_id, etc.)
- Нарушать effective targets контракт
- Использовать транзакции без SERIALIZABLE для критичных операций
- Добавлять прямые SQL запросы в Python сервисы (только Laravel API)
- Менять логику создания снапшотов в GrowCycleService

**Критически важно:**
- Все изменения в доменной модели должны отражаться в тестах EffectiveTargetsServiceTest
- Новые API endpoints должны иметь Feature тесты
- Любые изменения контракта effective targets требуют обновления Python клиентов

---

# Конец файла DATA_MODEL_REFERENCE.md
