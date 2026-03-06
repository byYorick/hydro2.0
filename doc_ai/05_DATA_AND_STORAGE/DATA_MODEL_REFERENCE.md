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
type VARCHAR (ph, ec, climate, irrig, light, relay, water_sensor, recirculation, unknown)
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

### 3.1.1. Каноническая схема `nodes.type` (strict)

Допустимые значения:
- `ph`
- `ec`
- `climate`
- `irrig`
- `light`
- `relay`
- `water_sensor`
- `recirculation`
- `unknown`

Ограничения:
- В БД действует `CHECK`-ограничение `nodes_type_canonical_check`.
- `nodes.type` не допускает `NULL` (используется default/fallback `unknown`).
- Legacy-алиасы (`pump_node`, `irrigation`, `lighting_node`, `climate_node`, и т.п.) не допускаются.
- Для нераспознанных значений используется `unknown`.

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

Практика для актуаторов-дозаторов:
- калибровка насоса хранится в `node_channels.config.pump_calibration`:
  `ml_per_sec`, `duration_sec`, `actual_ml`, `component`, `calibrated_at`,
  `k_ms_per_ml_l`, `test_volume_l`, `ec_before_ms`, `ec_after_ms`, `delta_ec_ms`, `temperature_c`.
- `component` для EC-питания поддерживает: `npk`, `calcium`, `magnesium`, `micro` (для pH — `acid`/`base`).
- Для новой логики питания не используется legacy 3-компонентная схема: актуальна только 4-компонентная модель.

---

# 4. Таблицы телеметрии

## 4.1. sensors (идентичность сенсора)

```
id BIGSERIAL PK
greenhouse_id FK
zone_id FK NULL
node_id FK NULL
scope ENUM(inside|outside)
type ENUM(TEMPERATURE|HUMIDITY|CO2|PH|EC|WATER_LEVEL|WATER_LEVEL_SWITCH|SOIL_MOISTURE|SOIL_TEMP|WIND_SPEED|OUTSIDE_TEMP|...)
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

Индексы:
```
telemetry_last_ts_idx (last_ts)
telemetry_last_sensor_updated_at_idx (sensor_id, updated_at) -- AE2-Lite freshness/polling
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

## 5.2.1. nutrient_products (справочник продуктов питания)
```
id BIGSERIAL PK
manufacturer VARCHAR(128)
name VARCHAR(191)
component VARCHAR(16) -- npk|calcium|magnesium|micro
composition VARCHAR(128) NULL
recommended_stage VARCHAR(64) NULL
notes TEXT NULL
metadata JSONB NULL
created_at TIMESTAMP
updated_at TIMESTAMP

UNIQUE: (manufacturer, name, component)
INDEX: nutrient_products_component_idx (component)
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
nutrient_program_code VARCHAR(64) NULL
nutrient_npk_ratio_pct DECIMAL(5,2) NULL
nutrient_calcium_ratio_pct DECIMAL(5,2) NULL
nutrient_magnesium_ratio_pct DECIMAL(5,2) NULL
nutrient_micro_ratio_pct DECIMAL(5,2) NULL
nutrient_npk_dose_ml_l DECIMAL(8,3) NULL
nutrient_calcium_dose_ml_l DECIMAL(8,3) NULL
nutrient_magnesium_dose_ml_l DECIMAL(8,3) NULL
nutrient_micro_dose_ml_l DECIMAL(8,3) NULL
nutrient_npk_product_id BIGINT FK → nutrient_products NULL
nutrient_calcium_product_id BIGINT FK → nutrient_products NULL
nutrient_magnesium_product_id BIGINT FK → nutrient_products NULL
nutrient_micro_product_id BIGINT FK → nutrient_products NULL
nutrient_mode VARCHAR(32) NULL -- ratio_ec_pid|delta_ec_by_k|dose_ml_l_only
nutrient_solution_volume_l DECIMAL(8,2) NULL
nutrient_dose_delay_sec INT NULL
nutrient_ec_stop_tolerance DECIMAL(5,3) NULL
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

Правила валидации для топологии `2 бака`:
- область применения: только при активной runtime-топологии
  `zone_automation_logic_profiles.subsystems.diagnostics.execution.topology = "two_tank_drip_substrate_trays"`.
- для фаз со статусом ревизии `PUBLISHED` обязательны поля:
  - `nutrient_npk_ratio_pct`
  - `nutrient_calcium_ratio_pct`
  - `nutrient_magnesium_ratio_pct`
  - `nutrient_micro_ratio_pct`
- сумма долей компонентов должна быть `100%` (допуск только на округление).
- отсутствие любой доли или некорректная сумма блокируют запуск startup/prepare workflow.

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
nutrient_program_code VARCHAR(64) NULL
nutrient_npk_ratio_pct DECIMAL(5,2) NULL
nutrient_calcium_ratio_pct DECIMAL(5,2) NULL
nutrient_magnesium_ratio_pct DECIMAL(5,2) NULL
nutrient_micro_ratio_pct DECIMAL(5,2) NULL
nutrient_npk_dose_ml_l DECIMAL(8,3) NULL
nutrient_calcium_dose_ml_l DECIMAL(8,3) NULL
nutrient_magnesium_dose_ml_l DECIMAL(8,3) NULL
nutrient_micro_dose_ml_l DECIMAL(8,3) NULL
nutrient_npk_product_id BIGINT FK → nutrient_products NULL
nutrient_calcium_product_id BIGINT FK → nutrient_products NULL
nutrient_magnesium_product_id BIGINT FK → nutrient_products NULL
nutrient_micro_product_id BIGINT FK → nutrient_products NULL
nutrient_mode VARCHAR(32) NULL -- ratio_ec_pid|delta_ec_by_k|dose_ml_l_only
nutrient_solution_volume_l DECIMAL(8,2) NULL
nutrient_dose_delay_sec INT NULL
nutrient_ec_stop_tolerance DECIMAL(5,3) NULL
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
status VARCHAR (QUEUED/SENT/ACK/DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT/SEND_FAILED)
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
commands_status_updated_at_idx (status, updated_at DESC) -- AE2-Lite reconcile polling
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
prev_derivative FLOAT DEFAULT 0
last_output_ms BIGINT DEFAULT 0
last_dose_at TIMESTAMPTZ NULL
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

## 6.6. zone_workflow_state

```
zone_id FK → zones
workflow_phase VARCHAR(50) NOT NULL DEFAULT 'idle'
scheduler_task_id VARCHAR(100) NULL
started_at TIMESTAMPTZ NULL
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
payload JSONB NOT NULL DEFAULT '{}'::jsonb
PK (zone_id)
```

Индексы:
```
zone_workflow_state_workflow_phase_idx (workflow_phase)
zone_workflow_state_updated_at_idx (updated_at)
zone_workflow_state_scheduler_task_id_idx (scheduler_task_id)
```

Назначение:
- персистентное хранение доменной `workflow_phase` для зоны;
- восстановление in-flight workflow после рестарта `automation-engine`;
- связь continuation payload с текущим intent (`payload.intent_id`).

Допустимые значения `workflow_phase`:
- `idle`
- `tank_filling`
- `tank_recirc`
- `ready`
- `irrigating`
- `irrig_recirc`

## 6.7. zone_automation_logic_profiles

```
id PK
zone_id FK → zones
mode VARCHAR(16) -- setup|working
subsystems JSONB -- runtime-конфиг подсистем
command_plans JSONB NOT NULL DEFAULT '{}'::jsonb -- планы команд two-tank
is_active BOOLEAN DEFAULT false
created_by FK → users NULL
updated_by FK → users NULL
created_at TIMESTAMP
updated_at TIMESTAMP
UNIQUE (zone_id, mode)
```

Индексы:
```
zone_automation_logic_profiles_zone_id_is_active_index
```

Требования к `command_plans`:
- содержит `schema_version` и `plan_version`;
- каждый plan содержит `steps[]` с `channel`, `cmd`, `params`;
- приоритет runtime-резолва: `command_plans` (колонка) -> legacy fallback только на период миграции.

Минимальная JSON-схема `command_plans` (AE2-Lite):

```json
{
  "schema_version": 1,
  "plan_version": 1,
  "source": "subsystems_backfill|manual",
  "plans": {
    "diagnostics": {
      "execution": {
        "topology": "two_tank_drip_substrate_trays",
        "workflow": "cycle_start"
      },
      "steps": [
        {
          "name": "clean_fill_start",
          "channel": "irrigation",
          "cmd": "set_valve",
          "params": {
            "valve": "valve_clean_fill",
            "state": true
          },
          "timeout_sec": 30
        }
      ]
    }
  }
}
```

Правила валидации:
- `schema_version` и `plan_version` обязательны;
- `plans.<plan>.steps[]` обязательный массив;
- каждый шаг обязан иметь `channel`, `cmd`, `params` (JSON object);
- неподдерживаемый `schema_version` блокирует runtime-выполнение (fail-closed).

## 6.8. zone_automation_intents

```
id BIGSERIAL PK
zone_id BIGINT NOT NULL FK -> zones
intent_type VARCHAR(64) NOT NULL
payload JSONB NULL
idempotency_key VARCHAR(191) NOT NULL
status VARCHAR(32) NOT NULL -- pending|claimed|running|completed|failed|cancelled
not_before TIMESTAMPTZ NULL
claimed_at TIMESTAMPTZ NULL
completed_at TIMESTAMPTZ NULL
error_code VARCHAR(128) NULL
error_message TEXT NULL
retry_count INT NOT NULL DEFAULT 0
max_retries INT NOT NULL DEFAULT 3
created_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL
```

Индексы:
```
zone_automation_intents_idempotency_key_unique (idempotency_key) UNIQUE
zone_automation_intents_zone_status_idx (zone_id, status)
zone_automation_intents_status_not_before_idx (status, not_before)
```

Constraints:
```
zone_automation_intents_status_check:
status IN ('pending','claimed','running','completed','failed','cancelled')
```

Назначение:
- durable contract между Laravel scheduler-dispatch и AE2-Lite;
- идемпотентный запуск циклов через `POST /zones/{id}/start-cycle`;
- арбитраж конкурентных запусков через claim (`FOR UPDATE SKIP LOCKED`).

Payload-contract (`payload` JSONB, wake-up only):
```json
{
  "source": "laravel_scheduler",
  "task_type": "diagnostics",
  "workflow": "cycle_start",
  "topology": "two_tank_drip_substrate_trays",
  "grow_cycle_id": 123
}
```

Ограничения:
- `task_payload` запрещен;
- `schedule_payload` запрещен;
- любые device-level команды/steps в payload запрещены.

Lifecycle:
- `pending` -> `claimed` -> `running` -> `completed|failed|cancelled`
- повторный `idempotency_key` возвращает deduplicated wake-up без повторного исполнения;
- `failed` intent может быть re-claimed только при `retry_count < max_retries`;
- stale `claimed` intent может быть re-claimed при
  `claimed_at <= now - AE_START_CYCLE_CLAIM_STALE_SEC` (default: 180 sec),
  при re-claim увеличивается `retry_count`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

## 6.9. PostgreSQL NOTIFY triggers (AE2-Lite)

Источник событий для fast-path listener в `automation-engine`:

1) `ae_command_status`:
- trigger: `trg_ae_command_status_notify` на `commands` (`AFTER INSERT OR UPDATE OF status, updated_at`);
- payload:
```json
{"cmd_id":"...", "zone_id":12, "status":"DONE", "updated_at":"..."}
```

2) `ae_signal_update`:
- trigger: `trg_ae_signal_update_zone_events` на `zone_events` (`AFTER INSERT OR UPDATE`);
- trigger: `trg_ae_signal_update_telemetry_last` на `telemetry_last`
  (`AFTER INSERT OR UPDATE OF last_value, last_ts, updated_at`);
- payload:
```json
{"zone_id":12, "kind":"zone_event|telemetry_last", "updated_at":"..."}
```

Правило runtime:
- `NOTIFY` используется как fast-path;
- reconcile polling обязателен как fallback на случай пропуска notify-событий.
- изменение runtime profile (`zone_automation_logic_profiles`) должно порождать `zone_events`
  типа `AUTOMATION_LOGIC_PROFILE_UPDATED`, чтобы инициировать `ae_signal_update` по `kind=zone_event`.

Рекомендуемая структура `subsystems` для startup/recovery в `2 бака`:

```json
{
  "solution_prepare": {
    "enabled": true,
    "topology": "two_tank_drip_substrate_trays",
    "startup": {
      "clean_fill_timeout_sec": 1200,
      "solution_fill_timeout_sec": 1800,
      "level_poll_interval_sec": 60,
      "clean_fill_retry_cycles": 1,
      "prepare_recirculation_timeout_sec": 1200
    },
    "dosing_rules": {
      "prepare_allowed_components": ["npk"],
      "prepare_ph_correction": true
    }
  },
  "irrigation": {
    "enabled": true,
    "recovery": {
      "max_continue_attempts": 5,
      "degraded_tolerance": {
        "ec_pct": 20,
        "ph_pct": 10
      }
    },
    "dosing_rules": {
      "irrigation_allowed_components": ["calcium", "magnesium", "micro"],
      "irrigation_forbid_components": ["npk"],
      "irrigation_ph_correction": true
    }
  }
}
```

## 6.10. AE3-Lite runtime tables (staged rollout)

Ниже таблицы вводятся migration-пакетом AE3-Lite и используются runtime-слоем
`backend/services/automation-engine/ae3lite/` (см. `04_BACKEND_CORE/ae3lite.md`).

### 6.10.1. ae_task_types

```
code VARCHAR(64) PK
description TEXT NULL
is_active BOOLEAN NOT NULL DEFAULT TRUE
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### 6.10.2. ae_tasks

```
id BIGSERIAL PK
task_uid TEXT UNIQUE NOT NULL          -- ae3:<id>
zone_id BIGINT NOT NULL FK -> zones
task_type VARCHAR(64) NOT NULL FK -> ae_task_types(code)
source VARCHAR(32) NOT NULL
status VARCHAR(32) NOT NULL            -- pending|leased|running|waiting_command|completed|skipped|failed|conflict|expired|cancelled
priority SMALLINT NOT NULL DEFAULT 1
payload JSONB NOT NULL DEFAULT '{}'
idempotency_key TEXT UNIQUE NOT NULL
scheduled_for TIMESTAMPTZ NOT NULL
due_at TIMESTAMPTZ NOT NULL
expires_at TIMESTAMPTZ NOT NULL
max_attempts INT NOT NULL DEFAULT 3
attempt_no INT NOT NULL DEFAULT 0
leased_until TIMESTAMPTZ NULL
claimed_by TEXT NULL
root_intent_id BIGINT NULL FK -> zone_automation_intents
task_schema_version SMALLINT NOT NULL DEFAULT 1
last_error_class VARCHAR(64) NULL
error_code VARCHAR(128) NULL
error_message TEXT NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
completed_at TIMESTAMPTZ NULL
```

Ключевые индексы:
```
ae_tasks_pending_idx (status, priority, due_at, created_at) WHERE status='pending'
ae_tasks_zone_status_idx (zone_id, status)
ae_tasks_leaseable_idx (status, leased_until) WHERE status IN ('leased','running','waiting_command')
```

### 6.10.3. ae_zone_locks

```
zone_id BIGINT PK FK -> zones ON DELETE CASCADE
lock_owner TEXT NOT NULL
lock_version BIGINT NOT NULL
lock_until TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### 6.10.4. ae_commands

```
id BIGSERIAL PK
task_id BIGINT NOT NULL FK -> ae_tasks
step_no INT NOT NULL
node_uid VARCHAR(128) NOT NULL
channel VARCHAR(64) NOT NULL
payload JSONB NOT NULL
publish_status VARCHAR(16) NOT NULL    -- pending|accepted|failed
retry_count INT NOT NULL DEFAULT 0
next_attempt_at TIMESTAMPTZ NULL
published_at TIMESTAMPTZ NULL
external_id VARCHAR(128) NULL          -- == commands.cmd_id
correlation_id VARCHAR(255) NULL
command_status VARCHAR(16) NOT NULL DEFAULT 'queued'   -- queued|sent|ack
ack_received_at TIMESTAMPTZ NULL
terminal_status VARCHAR(32) NULL       -- done|no_effect|error|invalid|busy|timeout|send_failed
terminal_at TIMESTAMPTZ NULL
node_response JSONB NULL
history_logger_response JSONB NULL
last_error TEXT NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
UNIQUE (task_id, step_no)
```

Ключевые индексы/ограничения:
```
ae_commands_publish_idx (publish_status, next_attempt_at) WHERE terminal_status IS NULL
ae_commands_external_id_idx (external_id) WHERE external_id IS NOT NULL
ae_commands_correlation_id_idx (correlation_id) WHERE correlation_id IS NOT NULL
ae_commands_inflight_node_channel_uq (node_uid, channel) WHERE terminal_status IS NULL
```

Примечание по статусам:
- `ae_commands.*status` хранится в lowercase;
- `commands.status` (Laravel/history-logger) хранится в uppercase;
- трекинг делается через mapping `external_id -> commands.cmd_id`.

### 6.10.5. ae_task_attempts

```
id BIGSERIAL PK
task_id BIGINT NOT NULL FK -> ae_tasks
attempt_no INT NOT NULL
error_class VARCHAR(64) NOT NULL
error_code VARCHAR(128) NULL
retryable BOOLEAN NOT NULL
is_dead_letter BOOLEAN NOT NULL DEFAULT FALSE
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
finished_at TIMESTAMPTZ NULL
UNIQUE (task_id, attempt_no)
```

### 6.10.6. ae_domain_events

```
id BIGSERIAL PK
aggregate_type VARCHAR(64) NOT NULL
aggregate_id VARCHAR(128) NOT NULL
event_type VARCHAR(128) NOT NULL
event_version INT NOT NULL DEFAULT 1
payload JSONB NOT NULL
occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
publish_attempts INT NOT NULL DEFAULT 0
next_attempt_at TIMESTAMPTZ NULL
published_at TIMESTAMPTZ NULL
dead_letter_at TIMESTAMPTZ NULL
last_error TEXT NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Ключевой runtime-контракт:
- publisher читает только `published_at IS NULL AND dead_letter_at IS NULL`
  в детерминированном порядке `ORDER BY id ASC`.

### 6.10.7. ae_task_id_aliases

```
alias_id VARCHAR(128) PK
task_id BIGINT NOT NULL FK -> ae_tasks ON DELETE CASCADE
alias_type VARCHAR(32) NOT NULL         -- native|bridge_intent
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
UNIQUE (task_id, alias_type)
```

### 6.10.8. ae_bridge_sync_journal

```
id BIGSERIAL PK
task_id BIGINT NOT NULL FK -> ae_tasks
zone_id BIGINT NOT NULL FK -> zones
root_intent_id BIGINT NULL
attempt_no INT NOT NULL
result VARCHAR(16) NOT NULL             -- ok|conflict|failed
error_code VARCHAR(128) NULL
details JSONB NOT NULL DEFAULT '{}'
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Индексы:
```
ae_bridge_sync_journal_zone_created_idx (zone_id, created_at DESC)
ae_bridge_sync_journal_task_attempt_idx (task_id, attempt_no)
```

### 6.10.9. ae_worker_runtime_state

```
worker_id VARCHAR(128) PK
consecutive_high_prio INT NOT NULL DEFAULT 0
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### 6.10.10. ae_scheduler_heartbeat

```
greenhouse_id BIGINT PK FK -> greenhouses ON DELETE CASCADE
last_scheduler_call_at TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### 6.10.11. ae2_writer_heartbeat

```
greenhouse_id BIGINT PK FK -> greenhouses ON DELETE CASCADE
last_seen_at TIMESTAMPTZ NOT NULL
writer_mode VARCHAR(16) NOT NULL        -- active|readonly
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

### 6.10.12. ae3l_canary_state

```
greenhouse_id BIGINT PK FK -> greenhouses ON DELETE CASCADE
gate SMALLINT NOT NULL DEFAULT 0 CHECK (gate BETWEEN 0 AND 3)
last_advance_at TIMESTAMPTZ NULL
rollback_count INT NOT NULL DEFAULT 0 CHECK (rollback_count >= 0)
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Retention (операционный минимум для AE3-Lite):
- `ae_tasks`, `ae_commands`, `ae_task_attempts`: hot retention 30 дней для terminal-данных;
- `ae_domain_events`: hot retention 90 дней + архив;
- purge выполняется batched job в off-peak окнах.

---

# 7. Таблицы тревог (Alerts)

## 7.1. alerts

```
id PK
zone_id FK → zones NULL
source VARCHAR (biz/infra/node)
code VARCHAR
type VARCHAR
details JSONB
status VARCHAR (ACTIVE/RESOLVED)
category VARCHAR (agronomy/infrastructure/operations/node/config/safety/other)
severity VARCHAR (info/warning/error/critical)
node_uid VARCHAR NULL
hardware_id VARCHAR NULL
error_count INTEGER DEFAULT 1
first_seen_at TIMESTAMP NULL
last_seen_at TIMESTAMP NULL
created_at
resolved_at
```

Индексы:
```
alerts_zone_status_idx
alerts_source_code_status_idx
alerts_zone_status_severity_idx
alerts_zone_status_category_idx
alerts_node_uid_idx
alerts_hardware_id_idx
```

---

# 8. Таблицы событий (Events)

## 8.1. zone_events

```
id PK
zone_id FK
type VARCHAR(255)
entity_type VARCHAR NULL
entity_id TEXT NULL
server_ts BIGINT NULL
payload_json JSONB NULL
details JSONB -- generated column над payload_json (для обратной читаемости запросов)
created_at
```

Индексы:
```
zone_events_zone_id_created_at_idx
zone_events_type_idx
zone_events_zone_entity_idx
zone_events_zone_id_id_idx
```

Примечание:
- Основной payload хранится в `payload_json`.
- `details` используется как совместимый read-layer и в актуальной схеме генерируется из `payload_json`.
- Для событий от MQTT (`hydro/{gh}/{zone}/{node}/storage_state/event`) поле `type` получает нормализованный `event_code`;
  при длине >255 значение детерминированно усекается до 255 символов.
- Для runtime invalidation effective targets используется событие
  `AUTOMATION_LOGIC_PROFILE_UPDATED` (source: upsert active automation profile).

---

## 8.2. simulation_events

```
id PK
simulation_id FK → zone_simulations
zone_id FK → zones
service VARCHAR
stage VARCHAR
status VARCHAR
level VARCHAR (info/warning/error)
message TEXT NULL
payload JSONB NULL
occurred_at TIMESTAMP
created_at TIMESTAMP
```

Индексы:
```
simulation_events_sim_id_occurred_idx (simulation_id, occurred_at)
simulation_events_zone_id_occurred_idx (zone_id, occurred_at)
simulation_events_service_stage_idx (service, stage)
simulation_events_status_idx (status)
```

---

## 8.3. simulation_reports

```
id PK
simulation_id FK → zone_simulations (UNIQUE)
zone_id FK → zones
status VARCHAR
started_at TIMESTAMP NULL
finished_at TIMESTAMP NULL
summary_json JSONB NULL
phases_json JSONB NULL
metrics_json JSONB NULL
errors_json JSONB NULL
created_at
updated_at
```

Индексы:
```
simulation_reports_simulation_id_unique (simulation_id)
simulation_reports_zone_id_index (zone_id)
simulation_reports_status_index (status)
```

---

## 8.4. scheduler_logs (LEGACY / DIAGNOSTICS)

```
id PK
task_name VARCHAR
status VARCHAR
details JSONB NULL
created_at TIMESTAMP
```

Назначение:
- исторический журнал старого scheduler-task транспорта;
- может использоваться как diagnostics source до полного cleanup.

Индексы:
```
scheduler_logs_task_created_idx
scheduler_logs_status_idx
scheduler_logs_created_at_idx
scheduler_logs_task_zone_created_idx -- expression index по details->>'zone_id'
scheduler_logs_zone_created_idx -- expression partial index по details->>'zone_id'
```

### 8.4.1. Контракт `scheduler_logs.details` (LEGACY)

Обязательные ключи task snapshot:
- `task_id: string`
- `zone_id: int`
- `task_type: string`
- `status: string`
- `correlation_id: string`
- `scheduled_for: ISO8601|null`
- `due_at: ISO8601`
- `expires_at: ISO8601`

Обязательные ключи terminal outcome (`completed|failed|rejected|expired`):
- `result.action_required: bool`
- `result.decision: \"run\"|\"skip\"|\"retry\"|\"fail\"`
- `result.reason_code: string`
- `result.error_code: string|null`
- `result.command_submitted: bool|null`
- `result.command_effect_confirmed: bool|null`
- `result.commands_total: int|null`
- `result.commands_effect_confirmed: int|null`
- `result.commands_failed: int|null`

Статус:
- в AE2-Lite canonical runtime вместо scheduler-task используется `zone_automation_intents`.

---

## 8.5. laravel_scheduler_active_tasks (ACTIVE: Laravel scheduler owner)

Durable state Laravel dispatcher для reconcile/anti-overlap в цепочке
`Scheduler -> /start-cycle -> intent -> executor`.

Примечание:
- `zone_automation_intents` — canonical lifecycle намерений;
- `laravel_scheduler_active_tasks` — operational state external dispatcher-а
  (busy arbitration, polling, recovery после рестартов Laravel).

```
id BIGSERIAL PK
task_id VARCHAR(128) UNIQUE NOT NULL
zone_id BIGINT FK -> zones
task_type VARCHAR(64) NOT NULL
schedule_key VARCHAR(255) NOT NULL
correlation_id VARCHAR(255) NOT NULL
status VARCHAR(32) NOT NULL
accepted_at TIMESTAMPTZ NOT NULL
due_at TIMESTAMPTZ NULL
expires_at TIMESTAMPTZ NULL
last_polled_at TIMESTAMPTZ NULL
terminal_at TIMESTAMPTZ NULL
details JSONB NOT NULL DEFAULT '{}'
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Индексы:
```
lsat_zone_status_updated_idx (zone_id, status, updated_at)
lsat_sched_key_updated_idx (schedule_key, updated_at)
lsat_expires_at_idx (expires_at)
lsat_terminal_at_idx (terminal_at)
lsat_corr_idx (correlation_id)
```

Назначение:
- восстановление reconcile после рестарта Laravel/worker;
- арбитраж `isScheduleBusy` через БД;
- cleanup terminal записей по retention policy.

---

## 8.6. laravel_scheduler_zone_cursors (LEGACY / OPTIONAL)

Исторический курсор legacy scheduler-reconcile.

```
zone_id BIGINT PK FK -> zones
cursor_at TIMESTAMPTZ NOT NULL
catchup_policy VARCHAR(32) NOT NULL
metadata JSONB NOT NULL DEFAULT '{}'
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Индексы:
```
lszc_cursor_at_idx (cursor_at)
```

Назначение:
- источник истины для `resolveZoneLastCheck`;
- сохранение catchup-контекста между циклами и рестартами.

---

# 9. Пользователи и роли

## 9.1. users

```
id PK
name
email UNIQUE
password
role VARCHAR (admin/operator/viewer/agronomist/engineer)
preferences JSONB NULL -- пользовательские UI-настройки
created_at
updated_at
```

## 9.2. user_greenhouses

```
id PK
user_id BIGINT FK → users CASCADE
greenhouse_id BIGINT FK → greenhouses CASCADE
created_at
updated_at

UNIQUE(user_id, greenhouse_id)
INDEX(greenhouse_id, user_id)
```

Назначение:

- Явная привязка пользователя к теплицам.
- Используется в `ACCESS_CONTROL_MODE=enforce` и `shadow`.

## 9.3. user_zones

```
id PK
user_id BIGINT FK → users CASCADE
zone_id BIGINT FK → zones CASCADE
created_at
updated_at

UNIQUE(user_id, zone_id)
INDEX(zone_id, user_id)
```

Назначение:

- Точечная привязка пользователя к зонам.
- В strict-доступе объединяется с `user_greenhouses` (доступ через зону или через ее теплицу).

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
users N—N greenhouses (user_greenhouses)
users N—N zones (user_zones)
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
zone 1—N scheduler_logs (логическая связь через `scheduler_logs.details.zone_id`, без FK)
zone 1—N laravel_scheduler_active_tasks
zone 1—1 laravel_scheduler_zone_cursors
zone 1—N commands
zone 1—1 zone_workflow_state
zone 1—N zone_simulations
zone_simulation 1—N simulation_events
zone_simulation 1—1 simulation_reports
```

**Инфраструктура (новая модель):**
```
infrastructure_instance (polymorphic: owner_type='zone'|'greenhouse')
infrastructure_instance 1—N channel_bindings
channel_binding 1—1 node_channel
```

**AE3-Lite runtime (staged):**
```
zone 1—N ae_tasks
ae_task_types 1—N ae_tasks
ae_tasks 1—N ae_commands
ae_tasks 1—N ae_task_attempts
ae_tasks 1—N ae_task_id_aliases
ae_tasks 1—N ae_bridge_sync_journal
zone 1—N ae_bridge_sync_journal
zone 1—1 ae_zone_locks
greenhouse 1—1 ae_scheduler_heartbeat
greenhouse 1—1 ae2_writer_heartbeat
greenhouse 1—1 ae3l_canary_state
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

# 13. Использование данных в Python сервисах (AE2-Lite)

**Automation-engine (AE2-Lite) использует direct SQL read-model в runtime path.**

**Основной контракт runtime:**
- чтение таблиц `grow_cycles`, `grow_cycle_phases`, `zone_automation_logic_profiles`,
  `telemetry_last`, `zone_workflow_state`, `zone_events`, `commands`;
- приоритет резолва: `phase snapshot -> grow_cycle_overrides -> active logic profile`;
- отсутствие runtime-зависимости от `/api/internal/effective-targets/*`.

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
    "irrigation": {
      "mode": "SUBSTRATE",
      "interval_sec": 3600,
      "duration_sec": 300,
      "execution": {
        "node_types": ["irrig"],
        "cmd": "run_pump",
        "params": {"duration_sec": 300},
        "fallback_mode": "none"
      }
    }
    // ... остальные цели
  }
}
```

### 13.1. Контракт `targets.*.execution` для AE2-Lite workflow

Для workflow-исполнения поддерживаются execution-конфиги
в секциях `targets.irrigation|lighting|ventilation|solution_change|mist|diagnostics`.

Поля:
- `node_types: string[]` (только канонические типы `nodes.type`)
- `cmd: string`
- `cmd_true: string`
- `cmd_false: string`
- `state_key: string`
- `default_state: bool`
- `params: object`
- `duration_sec: number`
- `fallback_mode: \"none\"|\"zone_service\"|\"event_only\"` (optional)

### 13.2. Runtime-конфиг автоматики (`zone_automation_logic_profiles` -> runtime DTO)

Источник runtime-настроек фронтового конфигуратора: `zone_automation_logic_profiles.subsystems`.

При формировании runtime DTO применяется приоритет:

`phase snapshot -> grow_cycle_overrides -> zone_automation_logic_profiles (active mode runtime)`.

Применение runtime-профиля:
- фронтенд сохраняет профиль через `POST /api/zones/{zone}/automation-logic-profile`
- scheduler/оператор формирует intent;
- AE2-Lite читает профиль напрямую из БД и применяет в зоне.

Нормализация runtime-полей в automation контракт:

- `subsystems.irrigation.execution.interval_minutes` -> `targets.irrigation.interval_sec`
- `subsystems.irrigation.execution.duration_seconds` -> `targets.irrigation.duration_sec`
- `subsystems.irrigation.execution.system_type` -> `targets.irrigation.system_type`
- `subsystems.irrigation.execution.*` -> `targets.irrigation.execution.*`
- `subsystems.climate.execution.interval_sec` -> `targets.ventilation.interval_sec`
- `subsystems.climate.execution.*` -> `targets.ventilation.execution.*`
- `subsystems.lighting.execution.interval_sec` -> `targets.lighting.interval_sec`
- `subsystems.lighting.execution.*` -> `targets.lighting.execution.*`
- `subsystems.solution_change.execution.interval_sec` -> `targets.solution_change.interval_sec`
- `subsystems.solution_change.execution.duration_sec` -> `targets.solution_change.duration_sec`
- `subsystems.solution_change.execution.*` -> `targets.solution_change.execution.*`
- `subsystems.diagnostics.execution.*` -> `targets.diagnostics.*` и `targets.diagnostics.execution.*`
- `subsystems.diagnostics.execution.startup.clean_fill_timeout_sec` -> `targets.diagnostics.execution.clean_fill_timeout_sec`
- `subsystems.diagnostics.execution.startup.solution_fill_timeout_sec` -> `targets.diagnostics.execution.solution_fill_timeout_sec`
- `subsystems.diagnostics.execution.startup.level_poll_interval_sec` -> `targets.diagnostics.execution.level_poll_interval_sec`
- `subsystems.diagnostics.execution.startup.prepare_recirculation_timeout_sec` -> `targets.diagnostics.execution.prepare_recirculation_timeout_sec`
- `subsystems.diagnostics.execution.topology` -> `targets.diagnostics.execution.topology`
- `subsystems.irrigation.recovery.max_continue_attempts` -> `targets.irrigation.execution.max_continue_attempts`
- `subsystems.irrigation.recovery.degraded_tolerance.ec_pct` -> `targets.irrigation.execution.degraded_tolerance.ec_pct`
- `subsystems.irrigation.recovery.degraded_tolerance.ph_pct` -> `targets.irrigation.execution.degraded_tolerance.ph_pct`

Совместимость rollout:
- legacy `subsystems.*.targets` отклоняется backend-слоем (`422`);
- канонический формат для новых payload/документации: `subsystems.*.execution`.

Политика enable/disable подсистем:

- при `enabled=false` выставляется `targets.<task>.execution.force_skip=true`
- при `enabled=true` выставляется `targets.<task>.execution.force_skip=false`

Runtime-снимок подсистем отражается в `zone_automation_state` для UI/диагностики.

Ручные override-действия (`fill_clean_tank`, `prepare_solution`, `recirculate_solution`, `resume_irrigation`)
обязаны фиксироваться в `zone_events` и lifecycle `zone_automation_intents`.

Legacy примечание:
- старый scheduler-task транспорт и его таблицы считаются историческими.

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

# 16. Pump Calibration Domain Model (2026-02-25)

Добавлена выделенная доменная сущность калибровки насосов.  
`node_channels.config.pump_calibration` сохранён как **legacy read-through fallback** на переходный период.

### 16.1. Таблица `pump_calibrations`

- Назначение: версионируемое хранение калибровок дозирующих каналов.
- Ключевые поля:
  - `node_channel_id` (FK -> `node_channels.id`)
  - `ml_per_sec` (обязательный)
  - `k_ms_per_ml_l` (опциональный)
  - `valid_from`, `valid_to`, `is_active`
  - `source`, `quality_score`, `sample_count`
  - `component`, `meta`
- Политика версии:
  - новая калибровка деактивирует предыдущую (`is_active=false`, `valid_to=NOW()`),
  - актуальная калибровка выбирается по `is_active=true` и `valid_from DESC`.

### 16.2. Таблица `node_channels` (activity sync)

Добавлены поля:
- `last_seen_at` — последнее подтверждённое присутствие канала в `config_report`.
- `is_active` — soft-state активности канала.

Политика sync `config_report`:
- destructive-delete заменён на soft-deactivate (`is_active=false`) при explicit full-snapshot prune;
- по умолчанию prune отключён для transport-safe поведения.

### 16.3. Совместимость чтения

- Automation-Engine сначала читает активную запись из `pump_calibrations`.
- При отсутствии записи используется fallback из `node_channels.config.pump_calibration`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

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
