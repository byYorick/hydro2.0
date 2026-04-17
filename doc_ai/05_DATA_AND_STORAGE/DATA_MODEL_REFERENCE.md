# DATA_MODEL_REFERENCE.md
# Полный справочник моделей данных системы 2.0
# PostgreSQL • Laravel Models • Python ORM • Связи • Ограничения
# **ОБНОВЛЕНО ПОСЛЕ AUTHORITY CUTOVER 2026-03-24**

Документ описывает всю структуру данных системы 2.0:
таблицы, связи, ключи, индексы, правила и использование.


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: обратная совместимость со старыми форматами и алиасами не поддерживается.

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
automation_runtime VARCHAR(16) NOT NULL DEFAULT 'ae3' CHECK (automation_runtime IN ('ae3'))
control_mode VARCHAR(16) NOT NULL DEFAULT 'auto' CHECK (control_mode IN ('auto','semi','manual'))
-- Phase 5: config modes (locked/live)
config_mode VARCHAR(16) NOT NULL DEFAULT 'locked' CHECK (config_mode IN ('locked','live'))
config_mode_changed_at TIMESTAMP NULL
config_mode_changed_by BIGINT NULL FK -> users
live_until TIMESTAMP NULL          -- TTL для auto-revert
live_started_at TIMESTAMP NULL     -- первое включение live (7-day cap)
config_revision BIGINT NOT NULL DEFAULT 1
CHECK (config_mode = 'locked' OR live_until IS NOT NULL)
created_at
updated_at
```

Индексы:
```
zones_status_idx
zones_uid_unique
zones_automation_runtime_idx
```

## 2.3. zone_config_changes (Phase 5)

Audit trail всех правок конфигурации зоны.

```
id BIGSERIAL PK
zone_id BIGINT FK -> zones ON DELETE CASCADE
revision BIGINT          -- матчит `zones.config_revision` на момент записи
namespace VARCHAR(64)    -- 'zone.config_mode' | 'zone.correction' | 'recipe.phase'
diff_json JSONB          -- {from/to} для mode; {before/after} для setpoints
user_id BIGINT NULL FK -> users  -- NULL для system-originated (TTL auto-revert)
reason TEXT NULL
created_at TIMESTAMP DEFAULT NOW()
UNIQUE (zone_id, revision)  -- correctness net против race
```

Индексы:
```
zone_config_changes_zone_id_created_at_idx
zone_config_changes_zone_id_namespace_idx
```

Заполняется через:
- `ZoneConfigRevisionService::bumpAndAudit` (атомарный `UPDATE ... RETURNING` + INSERT внутри транзакции)
- `ZoneConfigModeController::update|extend` на switch режима
- `RevertExpiredLiveModesCommand` на TTL-expire (user_id=NULL, reason='auto-revert: live TTL expired')

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
- Алиасы вне канона (`pump_node`, `irrigation`, `lighting_node`, `climate_node`, и т.п.) не допускаются.
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
- оперативная калибровка канала насоса хранится в `node_channels.config.pump_calibration` как last-known mirror:
  `ml_per_sec`, `duration_sec`, `actual_ml`, `component`, `calibrated_at`,
  `k_ms_per_ml_l`, `test_volume_l`, `ec_before_ms`, `ec_after_ms`, `delta_ec_ms`, `temperature_c`.
- этот mirror обновляется Laravel calibration flow; Python/history-logger не является owner для
  pump calibration tracking или persistence.
- системные пороги и UI/runtime defaults для pump calibration хранятся в
  `automation_config_documents(namespace='system.pump_calibration_policy', scope_type='system', scope_id=0)`.
- zone-level correction runtime contract хранится в
  `automation_config_documents(namespace='zone.correction', scope_type='zone', scope_id={zone_id})`
  и materialized bundle `automation_effective_bundles(scope_type='zone', scope_id={zone_id})`.
- `component` для EC-питания поддерживает: `npk`, `calcium`, `magnesium`, `micro` (для pH — `acid`/`base`).
- Для новой логики питания не используется старая 3-компонентная схема: актуальна только 4-компонентная модель.

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
telemetry_last_sensor_updated_at_idx (sensor_id, updated_at) -- runtime freshness/polling
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

## 5.2.2. substrates (справочник субстратов)

Миграция: `backend/laravel/database/migrations/2026_04_13_120000_create_substrates_table.php`.

```
id BIGSERIAL PK
code VARCHAR(64) UNIQUE     -- короткий идентификатор (латиница, цифры, _)
name VARCHAR(255)
components JSONB DEFAULT '[]'         -- [{name, label, ratio_pct}, ...], сумма ratio_pct = 100
applicable_systems JSONB DEFAULT '[]' -- массив enum irrigation_system_type
notes TEXT NULL
created_at TIMESTAMP
updated_at TIMESTAMP
```

Связи (логические):
- `recipe_revision_phases.substrate_type` ссылается на `substrates.code` (FK-by-code, не enforce на уровне БД).
- `grow_cycle_phases.substrate_type` хранит ту же строку как snapshot — удаление записи в `substrates` не каскадирует на snapshot.

REST API: `/api/substrates` (CRUD, write требует роли agronomist).
Контроллер: `App\Http\Controllers\SubstrateController`.
Form Request: `App\Http\Requests\SubstrateRequest` (валидирует `components` и сумму `ratio_pct = 100%`).

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
nutrient_ec_dosing_mode VARCHAR(32) NULL  -- enum: sequential|parallel (миграция 2026_04_12_200000)
irrigation_mode ENUM('SUBSTRATE', 'RECIRC') NULL
irrigation_system_type VARCHAR(32) NULL   -- enum: drip_tape|drip_emitter|ebb_flow|nft|dwc|aeroponics (миграция 2026_04_13_150000)
substrate_type VARCHAR(64) NULL           -- FK-by-code → substrates.code (миграция 2026_04_13_150000)
day_night_enabled BOOLEAN NULL            -- активирует extensions.day_night override (миграция 2026_04_13_150000)
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

Семантика новых flat-полей (см. также `../06_DOMAIN_ZONES_RECIPES/RECIPE_ENGINE_FULL.md` §2.1.1):
- `nutrient_ec_dosing_mode` — `sequential` | `parallel`. Управляет порядком дозирования компонентов NPK/Ca/Mg/Micro при EC коррекции в irrigation-фазе.
- `irrigation_system_type` — тип ирригационной системы фазы; используется для согласованности с `applicable_systems` выбранного субстрата.
- `substrate_type` — короткий код субстрата из таблицы `substrates` (FK-by-code; см. §5.2.2).
- `day_night_enabled` — если `true`, AE3 применяет `extensions.day_night.{ph,ec,...}` overrides по локальному времени (см. `EFFECTIVE_TARGETS_SPEC.md` §10).

Правила валидации для топологии `2 бака`:
- область применения: только при активной runtime-топологии
  `zone.logic_profile.active_profile.subsystems.diagnostics.execution.topology = "two_tank_drip_substrate_trays"`.
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
recipe_id BIGINT FK → recipes (историческое поле для совместимости)
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
nutrient_ec_dosing_mode VARCHAR(32) NULL  -- enum: sequential|parallel (snapshot)
irrigation_mode ENUM('SUBSTRATE', 'RECIRC') NULL
irrigation_system_type VARCHAR(32) NULL   -- enum (snapshot)
substrate_type VARCHAR(64) NULL           -- FK-by-code (snapshot, не каскадирует на удаление subsрата)
day_night_enabled BOOLEAN NULL            -- snapshot активации day/night override
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

## 6.4. cycle.phase_overrides / cycle.manual_overrides

Таблица `grow_cycle_overrides` не входит в authority-path.
Cycle-level overrides теперь хранятся в `automation_config_documents`:

- `namespace='cycle.phase_overrides'`, `scope_type='grow_cycle'`
- `namespace='cycle.manual_overrides'`, `scope_type='grow_cycle'`

`cycle.phase_overrides`:
- объект с phase snapshot override-полями (`ph_target`, `ec_target`, `irrigation_interval_sec`, ...).
- Семантика — **sparse diff**, а не полный snapshot фазы: хранятся только override-поля,
  которые compiler накладывает поверх phase snapshot / zone authority.
- Для `zone.correction.payload.phase_overrides` используется тот же подход:
  outer document schema `schemas/zone_correction_document.v1.json` ссылается на
  `schemas/zone_correction.v1.json#/$defs/PhaseOverride`.

`cycle.manual_overrides`:
- массив объектов:
  - `parameter`
  - `value_type`
  - `value`
  - `is_active`
  - `applies_from`
  - `applies_until`
  - `reason`
  - `created_by`

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
commands_status_updated_at_idx (status, updated_at DESC) -- runtime reconcile polling
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

Runtime-семантика AE3-Lite:
- `last_measured_value` хранит baseline/последнее подтверждённое измерение controller-а;
- `hold_until` блокирует раннее повторное решение до окончания process observation window;
- `feedforward_bias` используется для cross-coupled correction после `EC`-дозы;
- `no_effect_count` хранит consecutive no-effect attempts по конкретному `pid_type`;
- `current_zone` хранит выбранную planner-ом PID-зону (`dead`, `close`, `far`);
- `stats.adaptive` хранит persisted runtime-learning:
  learned process gain EMA, retention/wave EMA и learned timing window (`transport_delay_sec_ema`, `settle_sec_ema`);
- ordinary attempt limits и `no_effect_count` — разные safety-механизмы.

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
version BIGINT NOT NULL DEFAULT 0
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
- `AE3-Lite v1` использует `version` для последующего CAS-update workflow state.

Допустимые значения `workflow_phase`:
- `idle`
- `tank_filling`
- `tank_recirc`
- `ready`
- `irrigating`
- `irrig_recirc`

## 6.7. zone.logic_profile

Таблица `zone_automation_logic_profiles` не входит в authority-path.
Runtime profile зоны хранится в:

`automation_config_documents(namespace='zone.logic_profile', scope_type='zone', scope_id={zone_id})`

Payload:
- `active_mode`
- `profiles.setup|profiles.working`
  - `mode`
  - `is_active`
  - `subsystems`
  - `command_plans`
  - `created_by`
  - `updated_by`
  - `created_at`
  - `updated_at`

Требования к `command_plans`:
- содержит `schema_version` и `plan_version`;
- каждый plan содержит `steps[]` с `channel`, `cmd`, `params`;
- runtime использует `active_profile.command_plans` из compiled bundle, без запасного чтения из устаревших таблиц.

Минимальная JSON-схема `command_plans` (runtime):

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
zone_automation_intents_zone_idempotency_unique (zone_id, idempotency_key) UNIQUE
zone_automation_intents_zone_status_idx (zone_id, status)
zone_automation_intents_status_not_before_idx (status, not_before)
```

Constraints:
```
zone_automation_intents_status_check:
status IN ('pending','claimed','running','completed','failed','cancelled')
```

Назначение:
- durable contract между Laravel scheduler-dispatch и automation-engine;
- идемпотентный запуск workflow через `POST /zones/{id}/start-cycle`
  и `POST /zones/{id}/start-irrigation`;
- арбитраж конкурентных запусков через claim (`FOR UPDATE SKIP LOCKED`).

Payload-contract (`payload` JSONB, wake-up only):
```json
{
  "source": "laravel_scheduler",
  "task_type": "irrigation_start",
  "workflow": "irrigation_start",
  "topology": "two_tank_drip_substrate_trays",
  "grow_cycle_id": 123,
  "mode": "normal",
  "requested_duration_sec": 120
}
```

Ограничения:
- `task_payload` запрещен;
- `schedule_payload` запрещен;
- любые device-level команды/steps в payload запрещены.

Lifecycle:
- `pending` -> `claimed` -> `running` -> `completed|failed|cancelled`
- повторный `idempotency_key` в рамках той же `zone_id` возвращает deduplicated wake-up без повторного исполнения;
- одинаковый `idempotency_key` допускается в разных зонах;
- `failed` intent может быть re-claimed только при `retry_count < max_retries`;
- stale `claimed` intent может быть re-claimed при
  `claimed_at <= now - AE_START_CYCLE_CLAIM_STALE_SEC` (default: 180 sec),
  при re-claim увеличивается `retry_count`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0

## 6.9. PostgreSQL NOTIFY triggers (runtime)

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
- изменение runtime profile (`zone.logic_profile`) должно порождать `zone_events`
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
    "decision": {
      "strategy": "smart_soil_v1",
      "config": {
        "lookback_sec": 1800,
        "min_samples": 3,
        "stale_after_sec": 600,
        "hysteresis_pct": 2,
        "spread_alert_threshold_pct": 12
      }
    },
    "recovery": {
      "max_continue_attempts": 5,
      "auto_replay_after_setup": true,
      "max_setup_replays": 1,
      "degraded_tolerance": {
        "ec_pct": 20,
        "ph_pct": 10
      }
    },
    "safety": {
      "stop_on_solution_min": true
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

### 6.10.1. ae_tasks

```
id BIGSERIAL PK
zone_id BIGINT NOT NULL FK -> zones ON DELETE CASCADE
task_type VARCHAR(64) NOT NULL         -- в v1 допустимо cycle_start|irrigation_start
status VARCHAR(32) NOT NULL            -- pending|claimed|running|waiting_command|completed|failed|cancelled
idempotency_key VARCHAR(191) NOT NULL
intent_source VARCHAR(64) NULL
intent_trigger VARCHAR(64) NULL
intent_id BIGINT NULL
intent_meta JSONB NOT NULL DEFAULT '{}'
topology VARCHAR(64) NOT NULL DEFAULT 'two_tank'
current_stage VARCHAR(64) NOT NULL DEFAULT 'startup'
workflow_phase VARCHAR(32) NOT NULL DEFAULT 'idle'
scheduled_for TIMESTAMPTZ NOT NULL
due_at TIMESTAMPTZ NOT NULL
claimed_by VARCHAR(191) NULL
claimed_at TIMESTAMPTZ NULL
error_code VARCHAR(128) NULL
error_message TEXT NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
completed_at TIMESTAMPTZ NULL
stage_deadline_at TIMESTAMPTZ NULL
stage_retry_count SMALLINT NOT NULL DEFAULT 0
stage_entered_at TIMESTAMPTZ NULL
clean_fill_cycle SMALLINT NOT NULL DEFAULT 0
corr_step VARCHAR(32) NULL
corr_attempt SMALLINT NULL
corr_max_attempts SMALLINT NULL
corr_activated_here BOOLEAN NULL
corr_stabilization_sec SMALLINT NULL
corr_return_stage_success VARCHAR(64) NULL
corr_return_stage_fail VARCHAR(64) NULL
corr_outcome_success BOOLEAN NULL
corr_needs_ec BOOLEAN NULL
corr_ec_node_uid VARCHAR(128) NULL
corr_ec_channel VARCHAR(64) NULL
corr_ec_duration_ms INTEGER NULL
corr_needs_ph_up BOOLEAN NULL
corr_needs_ph_down BOOLEAN NULL
corr_ph_node_uid VARCHAR(128) NULL
corr_ph_channel VARCHAR(64) NULL
corr_ph_duration_ms INTEGER NULL
corr_wait_until TIMESTAMPTZ NULL
corr_ec_component VARCHAR(100) NULL
corr_ec_amount_ml NUMERIC(12,3) NULL
corr_ec_dose_sequence_json JSONB NULL
corr_ec_current_seq_index INT NOT NULL DEFAULT 0
corr_ph_amount_ml NUMERIC(12,3) NULL
corr_snapshot_event_id BIGINT NULL
corr_snapshot_created_at TIMESTAMPTZ NULL
corr_snapshot_cmd_id VARCHAR(191) NULL
corr_snapshot_source_event_type VARCHAR(64) NULL
corr_limit_policy_logged BOOLEAN NOT NULL DEFAULT FALSE
corr_ec_attempt SMALLINT NULL
corr_ec_max_attempts SMALLINT NULL
corr_ph_attempt SMALLINT NULL
corr_ph_max_attempts SMALLINT NULL
pending_manual_step VARCHAR(64) NULL
control_mode_snapshot VARCHAR(16) NULL
irrigation_mode VARCHAR(16) NULL
irrigation_requested_duration_sec INTEGER NULL
irrigation_decision_strategy VARCHAR(64) NULL
irrigation_decision_outcome VARCHAR(32) NULL
irrigation_decision_reason_code VARCHAR(128) NULL
irrigation_decision_degraded BOOLEAN NOT NULL DEFAULT FALSE
irrigation_replay_count SMALLINT NOT NULL DEFAULT 0
irrigation_wait_ready_deadline_at TIMESTAMPTZ NULL
irrigation_setup_deadline_at TIMESTAMPTZ NULL
```

Ключевые индексы:
```
ae_tasks_zone_status_idx (zone_id, status)
ae_tasks_zone_idempotency_unique (zone_id, idempotency_key) UNIQUE
ae_tasks_pending_idx (due_at, created_at) WHERE status='pending'
ae_tasks_active_zone_unique (zone_id) UNIQUE WHERE status IN ('pending','claimed','running','waiting_command')
ae_tasks_deadline_idx (stage_deadline_at) WHERE stage_deadline_at IS NOT NULL AND status IN ('running','waiting_command')
ae_tasks_topology_stage_idx (topology, current_stage) WHERE status IN ('running','waiting_command')
```

Инварианты v1:
- не более одной active task на зону;
- `idempotency_key` уникален только в рамках `zone_id`;
- correction amount-поля (`corr_ec_amount_ml`, `corr_ph_amount_ml`) хранятся с точностью `NUMERIC(12,3)`;
- `corr_snapshot_*` хранит causal link на последний подтверждённый `IRR_STATE_SNAPSHOT`, который должен переживать `enter_correction`, requeue и process restart;
- `corr_limit_policy_logged=true` означает, что `CORRECTION_LIMIT_POLICY_APPLIED` уже был записан для текущего correction-window и повторно эмитироваться не должен;
- `task_type IN ('cycle_start', 'irrigation_start')` фиксируется DB check constraint.
- `workflow_phase` допускает `idle|tank_filling|tank_recirc|irrigating|irrig_recirc|ready`.

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0
- irrigation decision/replay/runtime state хранится в explicit columns, а не в свободном JSON.
- canonical stage progress читается из `topology/current_stage/workflow_phase`, а не из произвольного JSON в `payload`.

### 6.10.2. ae_commands

```
id BIGSERIAL PK
task_id BIGINT NOT NULL FK -> ae_tasks ON DELETE CASCADE
step_no INT NOT NULL
node_uid VARCHAR(128) NOT NULL
channel VARCHAR(64) NOT NULL
payload JSONB NOT NULL DEFAULT '{}'
external_id VARCHAR(191) NULL          -- связь с commands.cmd_id
publish_status VARCHAR(16) NOT NULL    -- pending|accepted|failed
ack_received_at TIMESTAMPTZ NULL
terminal_status VARCHAR(32) NULL       -- DONE|NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED
terminal_at TIMESTAMPTZ NULL
last_error TEXT NULL
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
UNIQUE (task_id, step_no)
```

Ключевые индексы/ограничения:
```
ae_commands_external_id_idx (external_id) WHERE external_id IS NOT NULL
```

Примечание по статусам:
- `publish_status` хранится в lowercase;
- `terminal_status` синхронизирован по значениям с `commands.status`;
- трекинг делается через mapping `external_id -> commands.cmd_id`.

### 6.10.3. ae_zone_leases

```
zone_id BIGINT PK FK -> zones ON DELETE CASCADE
owner VARCHAR(191) NOT NULL
leased_until TIMESTAMPTZ NOT NULL
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Retention (операционный минимум для AE3-Lite):
- `ae_tasks`, `ae_commands`: hot retention 30 дней для terminal-данных;
- `ae_zone_leases`: только operational текущего runtime состояния;
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

Канонический lifecycle:

- единственный writer: Laravel `AlertService`;
- Python/AE3 публикуют только ingest intent;
- scoped lookup использует `details.dedupe_key`;
- `error_count`, `first_seen_at`, `last_seen_at` обновляются только в canonical dedup path.

Практика:

- `details.dedupe_key` обязателен для scoped infra/node alert-ов и для scoped business alert-ов;
- `details.alert_policy_mode`, `details.auto_resolve_policy_managed`, `details.auto_resolve_eligible`
  используются для policy-aware AE3 alert lifecycle;
- `zone_id = NULL` допустим для global/unassigned incidents.

## 7.1.1. pending_alerts и pending_alerts_dlq

Transport queue для alert ingest:

- `pending_alerts` — retry queue;
- `pending_alerts_dlq` — dead-letter queue.

Канон:

- replay path не использует `pending_alerts.status='dlq'`;
- replay переносит запись из `pending_alerts_dlq` обратно в `pending_alerts`;
- retry/replay не меняют `code`, `source`, `zone_id` и `details.dedupe_key`.

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
- Для событий от MQTT (`hydro/{gh}/{zone}/{node}/storage_state/event` и `hydro/{gh}/{zone}/{node}/{channel}/event`)
  поле `type` получает нормализованный `event_code`;
  при длине >255 значение детерминированно усекается до 255 символов.
- Для two-tank IRR-контракта в `zone_events.type` допустимы, в том числе:
  `LEVEL_SWITCH_CHANGED`, `CLEAN_FILL_SOURCE_EMPTY`, `CLEAN_FILL_COMPLETED`,
  `SOLUTION_FILL_SOURCE_EMPTY`, `SOLUTION_FILL_LEAK_DETECTED`, `SOLUTION_FILL_COMPLETED`,
  `RECIRCULATION_SOLUTION_LOW`, `IRRIGATION_SOLUTION_LOW`, `SOLUTION_FILL_TIMEOUT`,
  `PREPARE_RECIRCULATION_TIMEOUT`, `EMERGENCY_STOP_ACTIVATED`.
- Для `LEVEL_SWITCH_CHANGED` в `payload_json` должны сохраняться как минимум
  `channel`, `state`, `initial`, `snapshot`, `ts`.
- Для runtime invalidation effective targets используется событие
  `AUTOMATION_LOGIC_PROFILE_UPDATED` (source: upsert active automation profile).
- Correction-runtime события (`CORRECTION_COMPLETE`, `CORRECTION_SKIPPED_COOLDOWN`,
  `CORRECTION_SKIPPED_DEAD_ZONE`, `CORRECTION_SKIPPED_WATER_LEVEL`,
  `CORRECTION_SKIPPED_FRESHNESS`, `CORRECTION_SKIPPED_WINDOW_NOT_READY`,
  `CORRECTION_NO_EFFECT`, `CORRECTION_EXHAUSTED`)
  обязаны использовать `payload_json` как canonical source и по возможности включать
  `stage`, `workflow_phase`, `corr_step`, `attempt`, `ec_attempt`, `ph_attempt`.

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

## 8.4. scheduler_logs (диагностика / опционально)

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

### 8.4.1. Контракт `scheduler_logs.details` (вне основного authority-path)

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
- в canonical runtime вместо scheduler-task используется `zone_automation_intents`.

---

## 8.5. laravel_scheduler_active_tasks (ACTIVE: Laravel scheduler owner)

Durable state Laravel dispatcher для reconcile/anti-overlap в цепочке
`Laravel scheduler-dispatch -> /start-cycle -> intent -> executor`.

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

## 8.5.1. laravel_scheduler_dispatch_metric_totals (ACTIVE)

Персистентные Prometheus-compatible counters для Laravel scheduler. Таблица не
подпадает под `logs:cleanup` и используется exporter-ом вместо реконструкции из
`scheduler_logs`.

```
id BIGSERIAL PK
zone_id BIGINT FK -> zones
task_type VARCHAR(64) NOT NULL
result VARCHAR(64) NOT NULL
total BIGINT NOT NULL DEFAULT 0
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Индексы:
```
ls_dispatch_metric_unique (zone_id, task_type, result) UNIQUE
ls_dispatch_metric_task_result_idx (task_type, result)
```

Назначение:
- источник для `laravel_scheduler_dispatches_total{zone_id,task_type,result}`;
- монотонные счётчики, устойчивые к retention cleanup логов.

---

## 8.5.2. laravel_scheduler_cycle_duration_aggregates (ACTIVE)

Агрегированное состояние histogram метрики длительности scheduler cycle.

```
id BIGSERIAL PK
dispatch_mode VARCHAR(64) UNIQUE NOT NULL
sample_count BIGINT NOT NULL DEFAULT 0
sample_sum DOUBLE PRECISION NOT NULL DEFAULT 0
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Назначение:
- хранение `_count` и `_sum` для `laravel_scheduler_cycle_duration_seconds`;
- независимость histogram от TTL в `scheduler_logs`.

---

## 8.5.3. laravel_scheduler_cycle_duration_bucket_counts (ACTIVE)

Персистентные bucket counts для histogram `laravel_scheduler_cycle_duration_seconds`.

```
id BIGSERIAL PK
dispatch_mode VARCHAR(64) NOT NULL
bucket_le VARCHAR(32) NOT NULL
sample_count BIGINT NOT NULL DEFAULT 0
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

Индексы:
```
ls_cycle_duration_bucket_unique (dispatch_mode, bucket_le) UNIQUE
ls_cycle_duration_bucket_mode_idx (dispatch_mode)
```

Назначение:
- хранение cumulative bucket counts для фиксированного набора `le` bucket-ов;
- exporter строит `_bucket{le="+Inf"}` из `sample_count` таблицы
  `laravel_scheduler_cycle_duration_aggregates`.

---

## 8.6. laravel_scheduler_zone_cursors (опционально, вне основного authority-path)

Исторический курсор reconcile (до единого Laravel ownership dispatch).

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

## 8.7. automation_config_documents

Каноническое authority-хранилище automation/runtime-конфигов.

```
id BIGSERIAL PK
namespace VARCHAR(128) NOT NULL
scope_type VARCHAR(32) NOT NULL
scope_id BIGINT NOT NULL
schema_version INT NOT NULL DEFAULT 1
payload JSONB NOT NULL DEFAULT '{}'::jsonb
status VARCHAR(32) NOT NULL DEFAULT 'valid'
source VARCHAR(32) NOT NULL DEFAULT 'migration'
checksum VARCHAR(64) NOT NULL
updated_by BIGINT FK -> users NULL ON DELETE SET NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ

UNIQUE(namespace, scope_type, scope_id)
INDEX(scope_type, scope_id)
```

Ключевые namespace:

- `system.runtime`
- `system.automation_defaults`
- `system.command_templates`
- `system.process_calibration_defaults`
- `system.pump_calibration_policy`
- `system.sensor_calibration_policy`
- `greenhouse.logic_profile`
- `zone.logic_profile`
- `zone.correction`
- `zone.pid.ph`
- `zone.pid.ec`
- `zone.process_calibration.generic`
- `zone.process_calibration.solution_fill`
- `zone.process_calibration.tank_recirc`
- `zone.process_calibration.irrigation`
- `cycle.start_snapshot`
- `cycle.phase_overrides`
- `cycle.manual_overrides`

Примечание по PID authority:
- `zone.pid.ph|ec` содержат только zoned PID tuning
  (`dead_zone`, `close_zone`, `far_zone`, `zone_coeffs`, `max_integral`);
- `system.pid_defaults.*` удалены из canonical authority model и не поддерживаются;
- target хранится только в актуальной recipe phase;
- дозовые лимиты и интервалы хранятся только в `zone.correction.resolved_config.controllers.*`.

## 8.8. automation_config_versions

История всех изменений authority documents.

```
id BIGSERIAL PK
document_id BIGINT FK -> automation_config_documents CASCADE
namespace VARCHAR(128) NOT NULL
scope_type VARCHAR(32) NOT NULL
scope_id BIGINT NOT NULL
schema_version INT NOT NULL DEFAULT 1
payload JSONB NOT NULL DEFAULT '{}'::jsonb
status VARCHAR(32) NOT NULL DEFAULT 'valid'
source VARCHAR(32) NOT NULL DEFAULT 'migration'
checksum VARCHAR(64) NOT NULL
changed_by BIGINT FK -> users NULL ON DELETE SET NULL
changed_at TIMESTAMPTZ NOT NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

## 8.9. automation_effective_bundles

Materialized runtime bundles. Это единственный runtime read-path для automation config.

```
id BIGSERIAL PK
scope_type VARCHAR(32) NOT NULL
scope_id BIGINT NOT NULL
bundle_revision VARCHAR(64) NOT NULL
schema_revision VARCHAR(64) NOT NULL
config JSONB NOT NULL DEFAULT '{}'::jsonb
violations JSONB NOT NULL DEFAULT '[]'::jsonb
status VARCHAR(32) NOT NULL DEFAULT 'valid'
compiled_at TIMESTAMPTZ NOT NULL
inputs_checksum VARCHAR(64) NOT NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ

UNIQUE(scope_type, scope_id)
INDEX(bundle_revision)
```

Compile precedence:
`system.* -> zone.* -> cycle.*`

## 8.10. automation_config_violations

Machine-readable ошибки и предупреждения compiler/validator pipeline.

```
id BIGSERIAL PK
scope_type VARCHAR(32) NOT NULL
scope_id BIGINT NOT NULL
namespace VARCHAR(128) NOT NULL
path VARCHAR(255) NOT NULL DEFAULT ''
code VARCHAR(128) NOT NULL
severity VARCHAR(32) NOT NULL
blocking BOOLEAN NOT NULL DEFAULT FALSE
message TEXT NOT NULL
detected_at TIMESTAMPTZ NOT NULL

INDEX(scope_type, scope_id)
```

## 8.11. automation_config_presets

Preset storage для correction family. Preset не является runtime authority.

```
id BIGSERIAL PK
namespace VARCHAR(128) NOT NULL
scope VARCHAR(32) NOT NULL DEFAULT 'custom'
is_locked BOOLEAN NOT NULL DEFAULT FALSE
name VARCHAR NOT NULL
slug VARCHAR UNIQUE NOT NULL
description TEXT NULL
schema_version INT NOT NULL DEFAULT 1
payload JSONB NOT NULL DEFAULT '{}'::jsonb
updated_by BIGINT FK -> users NULL ON DELETE SET NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ

INDEX(namespace, scope)
```

## 8.12. automation_config_preset_versions

История изменений preset-ов.

```
id BIGSERIAL PK
preset_id BIGINT FK -> automation_config_presets CASCADE
namespace VARCHAR(128) NOT NULL
scope VARCHAR(32) NOT NULL
schema_version INT NOT NULL DEFAULT 1
payload JSONB NOT NULL DEFAULT '{}'::jsonb
checksum VARCHAR(64) NOT NULL
changed_by BIGINT FK -> users NULL ON DELETE SET NULL
changed_at TIMESTAMPTZ NOT NULL
created_at TIMESTAMPTZ
updated_at TIMESTAMPTZ
```

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
- Используется в strict ACL как канонический источник доступа к теплицам.

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
users 1—N automation_config_documents (updated_by)
users 1—N automation_config_versions (changed_by)
users 1—N automation_config_presets (updated_by)
users 1—N automation_config_preset_versions (changed_by)
zone 1—1 grow_cycle (активный: PLANNED/RUNNING/PAUSED)
grow_cycle 1—1 recipe_revision (зафиксированная версия)
recipe 1—N recipe_revisions
recipe_revision 1—N recipe_revision_phases
recipe_revision_phase 1—N recipe_revision_phase_steps

grow_cycle 1—N grow_cycle_phases (снапшоты)
grow_cycle_phase 1—N grow_cycle_phase_steps (снапшоты)
grow_cycle 1—N grow_cycle_transitions
scope(system|greenhouse|zone|grow_cycle) 1—1 automation_effective_bundle
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
zone 1—N laravel_scheduler_dispatch_metric_totals
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
ae_tasks 1—N ae_commands
zone 1—1 ae_zone_leases
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
- ❌ RecipePhase (устаревшие JSON targets)
- ❌ ZoneCycle
- ❌ PlantCycle

**Сервисы:**
- **EffectiveTargetsService** — единый контракт для Python сервисов
- **GrowCycleService** — управление циклами и создание снапшотов

Все используют Eloquent ORM с proper type casting.

---

# 13. Использование данных в Python сервисах

**Automation-engine использует direct SQL read-model в runtime path.**

**Основной контракт runtime:**
- чтение таблиц `grow_cycles`, `grow_cycle_phases`, `automation_effective_bundles`,
  `automation_config_violations`, `telemetry_last`, `zone_workflow_state`, `zone_events`, `commands`;
- приоритет compile: `system.* -> zone.* -> cycle.*`;
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

### 13.1. Контракт `targets.*.execution` для runtime workflow

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

### 13.2. Runtime-конфиг автоматики (authority documents -> bundle DTO)

Источник runtime-настроек фронтового конфигуратора:

- `automation_config_documents(namespace='zone.logic_profile', scope_type='zone', scope_id={zone_id})`
- `automation_config_documents(namespace='greenhouse.logic_profile', scope_type='greenhouse', scope_id={greenhouse_id})`

Каноническая ownership-модель:

- zonal automation profile живёт в `zone.logic_profile`;
- greenhouse climate profile живёт в `greenhouse.logic_profile`;
- runtime path читает не raw profile document, а compiled bundle.

При формировании runtime DTO применяется precedence:

`system.* -> zone.* -> cycle.*`

Применение runtime-профиля:
- фронтенд сохраняет профиль через unified `/api/automation-configs/*`;
- scheduler/оператор формирует intent;
- AE runtime читает compiled bundle напрямую из БД и применяет его в зоне.

Нормализация runtime-полей в automation контракт:

- `subsystems.irrigation.execution.interval_minutes` -> `targets.irrigation.interval_sec`
- `subsystems.irrigation.execution.duration_seconds` -> `targets.irrigation.duration_sec`
- `subsystems.irrigation.execution.system_type` -> `targets.irrigation.system_type`
- `subsystems.irrigation.execution.*` -> `targets.irrigation.execution.*`
- `subsystems.lighting.execution.interval_sec` -> `targets.lighting.interval_sec`
- `subsystems.lighting.execution.*` -> `targets.lighting.execution.*`
- `subsystems.zone_climate.execution.*` -> zonal climate extensions для CO2/root-vent runtime
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
- поле `subsystems.*.targets` отклоняется backend-слоем (`422`);
- канонический формат для новых payload/документации: `subsystems.*.execution`.

Политика enable/disable подсистем:

- при `enabled=false` выставляется `targets.<task>.execution.force_skip=true`
- при `enabled=true` выставляется `targets.<task>.execution.force_skip=false`

Runtime-снимок подсистем отражается в `zone_automation_state` для UI/диагностики.

### 13.3. Runtime-конфиг greenhouse climate (`greenhouse.logic_profile`)

Назначение authority-документа: хранить greenhouse-owned profile общего климата теплицы.

Ключевые поля payload:

- `active_mode`
- `profiles`

Ограничение v1:

- поддерживается только subsystem `climate`;
- runtime-dispatch ещё не активирован, но authority document уже является source of truth для UI и дальнейшего rollout.

Связанные bindings не хранятся в самой таблице. Они описываются через:

- `infrastructure_instances.owner_type = 'greenhouse'`
- `channel_bindings.role in ('climate_sensor', 'weather_station_sensor', 'vent_actuator', 'fan_actuator')`

Zonal climate bindings аналогично остаются zone-owned:

- `channel_bindings.role in ('co2_sensor', 'co2_actuator', 'root_vent_actuator')`

Ручные override-действия (`fill_clean_tank`, `prepare_solution`, `recirculate_solution`, `resume_irrigation`)
обязаны фиксироваться в `zone_events` и lifecycle `zone_automation_intents`.

Примечание:
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

# 16. Calibration Settings And Automation Authority (2026-03-24)

Automation settings, PID defaults, correction runtime config и process calibration
переведены в единый authority layer. `node_channels.config.pump_calibration` сохранён
как operational mirror/manual payload, но не является source of truth для system policy.

### 16.1. System authority namespaces

Системные defaults и policy хранятся в `automation_config_documents` со scope:

- `scope_type='system'`
- `scope_id=0`

Поддерживаемые system namespace:

- `system.runtime`
- `system.automation_defaults`
- `system.command_templates`
- `system.process_calibration_defaults`
- `system.pump_calibration_policy`
- `system.sensor_calibration_policy`

Frontend не должен получать эти данные через Inertia props; authority-read идёт через unified API.

### 16.2. Таблица `sensor_calibrations`

- Назначение: backend-managed async tracking двухточечной калибровки pH/EC сенсоров.
- Ключевые поля:
  - `zone_id` (FK -> `zones.id`)
  - `node_channel_id` (FK -> `node_channels.id`)
  - `sensor_type` (`ph|ec`)
  - `status`
  - `point_1_reference`, `point_1_command_id`, `point_1_sent_at`, `point_1_result`, `point_1_error`
  - `point_2_reference`, `point_2_command_id`, `point_2_sent_at`, `point_2_result`, `point_2_error`
  - `completed_at`
  - `calibrated_by` (nullable FK -> `users.id`)
  - `notes`, `meta`
- State machine:
  - `started`
  - `point_1_pending`
  - `point_1_done`
  - `point_2_pending`
  - `completed`
  - `failed`
  - `cancelled`
- Командная связка:
  - stage 1 и stage 2 публикуются через `history-logger POST /commands`
  - `point_1_command_id` и `point_2_command_id` совпадают с `commands.cmd_id`
  - terminal status `DONE` завершает stage 1 сразу, а для stage 2 сначала ставит `meta.awaiting_config_report=true`
  - финальный переход `point_2_pending -> completed` выполняется только после `config_report`, в котором нода прислала persisted `NodeConfig.calibration` для соответствующего `sensor_type`
  - terminal status `NO_EFFECT|ERROR|INVALID|BUSY|TIMEOUT|SEND_FAILED` маппится в `failed`
- `meta` используется для transport/runtime confirmation:
  - `awaiting_config_report` — stage 2 acknowledged, но backend ещё ждёт persisted config от ноды;
  - `persisted_via_config_report` / `persisted_at` — server-side подтверждение, что calibration пережила round-trip через node config.

### 16.3. Таблица `pump_calibrations`

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
- Two-step UX `run -> save` коррелируется через `zone_events.payload_json.run_token`:
  - Laravel/backend automation flow пишет `PUMP_CALIBRATION_STARTED` с `run_token`, `node_channel_id`, `duration_sec`, `component`, `command_id`;
  - Laravel/backend automation flow пишет `PUMP_CALIBRATION_FINISHED` и тем самым помечает `run_token` consumed;
  - сохранение canonical calibration допускается только после terminal `commands.status='DONE'` для связанного `command_id`;
  - прямой manual persist без correlated physical run допускается только с `manual_override=true`.
- Runtime constraint:
  - `ml_per_sec` обязан попадать в диапазон `0.01 .. 100.0`;
  - значение вне диапазона считается невалидной runtime-calibration и блокируется DB CHECK constraint.

### 16.3.1. Zone process calibration authority

Process-gain и observe-window contract хранятся в zone-scoped authority documents:

- `zone.process_calibration.generic`
- `zone.process_calibration.solution_fill`
- `zone.process_calibration.tank_recirc`
- `zone.process_calibration.irrigation`

Инварианты:
- runtime aliases нормализуются до canonical keys:
  `tank_filling -> solution_fill`,
  `prepare_recirculation -> tank_recirc`,
  `irrigating|irrig_recirc -> irrigation`;
- `transport_delay_sec` и `settle_sec` являются обязательной частью observe-window contract;
- readiness и start path проверяют эти payload semantically через compiled bundle.

### 16.4. Zone correction authority

- `zone.correction` хранит zonal correction payload:
  `preset_id`, `base_config`, `phase_overrides`, `resolved_config`;
- `resolved_config` materialized compiler/service layer и входит в zone/grow-cycle bundle;
- zone correction history хранится в `automation_config_versions`;
- AE runtime использует correction payload из compiled bundle, а не напрямую из отдельной correction-таблицы.

### 16.5. Zone correction config: timing contract

- `zone.correction.base_config.timing` и `zone.correction.resolved_config.timing`
  больше не содержат устаревшие wait-поля correction timing.
- `zone.correction.base_config` больше не содержит секцию adaptive timing.
- `zone.correction.*.retry.prepare_recirculation_max_correction_attempts`
  хранит только явный конечный лимит correction-loop внутри recirculation window;
  если field не задан, runtime использует `max(max_ec_correction_attempts, max_ph_correction_attempts)`.
- `zone.correction.*.retry.max_ec_correction_attempts` и
  `zone.correction.*.retry.max_ph_correction_attempts`
  тоже хранят только конечные значения внутри контрактной верхней границы.
- `zone.correction.*.retry.telemetry_stale_retry_sec`,
  `zone.correction.*.retry.decision_window_retry_sec` и
  `zone.correction.*.retry.low_water_retry_sec`
  задают delay для временных retry-path в `corr_check`/`corr_wait_{ec|ph}`.
- stage-level wait в correction path задаётся только через `timing.stabilization_sec`.
- observation hold-window для `EC`/`pH` задаётся только через
  `zone.process_calibration.*.transport_delay_sec` + `zone.process_calibration.*.settle_sec`
  и observe-параметры контроллеров.

### 16.6. Таблица `node_channels` (activity sync)

Добавлены поля:
- `last_seen_at` — последнее подтверждённое присутствие канала в `config_report`.
- `is_active` — soft-state активности канала.

Политика sync `config_report`:
- destructive-delete заменён на soft-deactivate (`is_active=false`) при explicit full-snapshot prune;
- по умолчанию prune отключён для transport-safe поведения.

### 16.7. Совместимость чтения

- Automation runtime читает system/zone/cycle config только из `automation_effective_bundles`.
- Laravel editors читают raw authority documents через `/api/automation-configs/*`.
- Ручная pump calibration панель Laravel читает активную запись из `pump_calibrations`.
- `node_channels.config.pump_calibration` допустим как read-through mirror/manual payload, но не как source of truth
  для системных default/min/max порогов.

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
