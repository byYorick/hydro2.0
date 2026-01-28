# DB_CANON_V2.md
# Каноническая структура БД для модели "Теплица → Зона → Цикл (центр истины) → Растение → Рецепты → Фазы"


Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.
Breaking-change: legacy форматы/алиасы удалены, обратная совместимость не поддерживается.

Дата: 2025-12-25
Ветка: `refactor/grow-cycle-centric`

## 1) Цели БД-рефакторинга (инварианты)

### Доменные инварианты

1. **Зона не делит контуры с другими зонами** (логика на уровне приложений, но БД должна исключать "двойную привязку" железа)
2. **1 зона = 1 нода** (и наоборот, для зонных нод)
3. **1 активный цикл на зону** (активные: PLANNED/RUNNING/PAUSED)
4. **Цикл жёстко связан с одним растением**
5. **Текущая фаза/шаг хранятся в цикле** (не вычисляются)
6. **Рецепты версионируются** (ревизии); агроном может редактировать, но в данных остаётся история
7. **Уставки по колонкам** (EC/pH/полив обязательно; климат/свет nullable)
8. **Команды допускаются вне цикла**; подтверждение команд двухфазное
9. **Архивных таблиц нет** → вместо этого партиционирование/retention

## 2) Целевая структура БД (модули)

### A) Топология и привязки

#### `greenhouses`
- `id` (PK)
- `name`, `location`, `settings` (jsonb)
- `created_at`, `updated_at`

#### `zones`
- `id` (PK)
- `greenhouse_id` (FK → greenhouses)
- `node_id` (FK UNIQUE → nodes.id) — **жёсткое правило 1:1 зона↔нода**
- `name`, `settings` (jsonb)
- `created_at`, `updated_at`

#### `nodes`
- `id` (PK)
- `zone_id` (FK nullable → zones.id) — альтернативный вариант (выбрать один канонический)
- `mac_address`, `ip_address`, `status`
- `created_at`, `updated_at`

#### `node_channels`
- `id` (PK)
- `node_id` (FK → nodes)
- `channel` (string, например "D1", "A0")
- `type` (enum: actuator/sensor)
- `capabilities` (jsonb)
- `created_at`, `updated_at`
- **UNIQUE(node_id, channel)**

### B) Растение / рецепты / ревизии

#### `plants`
- `id` (PK)
- `name`, `scientific_name`, `description`
- `created_at`, `updated_at`

#### `grow_recipes`
- `id` (PK)
- `name`, `description`
- `plant_id` (FK → plants)
- `created_at`, `updated_at`

#### `recipe_revisions`
- `id` (PK)
- `recipe_id` (FK → grow_recipes)
- `revision_number` (integer, default 1)
- `status` (enum: DRAFT|PUBLISHED)
- `description` (text nullable)
- `created_by` (FK nullable → users)
- `published_at` (timestamp nullable)
- `created_at`, `updated_at`
- **UNIQUE(recipe_id, revision_number)**

#### `recipe_revision_phases`
- `id` (PK)
- `recipe_revision_id` (FK → recipe_revisions)
- `stage_template_id` (FK nullable → grow_stage_templates)
- `phase_index` (integer, default 0)
- `name` (string)
- **Уставки по колонкам (обязательные):**
  - `ph_target`, `ph_min`, `ph_max` (decimal 4,2 nullable)
  - `ec_target`, `ec_min`, `ec_max` (decimal 5,2 nullable)
  - `irrigation_mode` (enum: SUBSTRATE|RECIRC nullable)
  - `irrigation_interval_sec`, `irrigation_duration_sec` (integer nullable)
- **Уставки по колонкам (nullable):**
  - `lighting_photoperiod_hours`, `lighting_start_time` (time nullable)
  - `mist_interval_sec`, `mist_duration_sec` (integer nullable)
  - `mist_mode` (enum: NORMAL|SPRAY nullable)
  - `temp_air_target`, `humidity_target` (decimal 5,2 nullable)
  - `co2_target` (integer nullable)
- **Прогресс:**
  - `progress_model` (string nullable: TIME|TIME_WITH_TEMP_CORRECTION|GDD)
  - `duration_hours`, `duration_days` (integer nullable)
  - `base_temp_c`, `target_gdd` (decimal nullable)
  - `dli_target` (decimal nullable)
- `extensions` (jsonb nullable) — только для расширений
- `created_at`, `updated_at`
- **UNIQUE(recipe_revision_id, phase_index)**

#### `recipe_revision_phase_steps`
- `id` (PK)
- `phase_id` (FK → recipe_revision_phases)
- `step_index` (integer, default 0)
- `name` (string)
- `offset_hours` (integer, default 0)
- `action` (string nullable)
- `description` (text nullable)
- **Уставки по колонкам (nullable, те же что у фаз):**
  - `ph_target`, `ph_min`, `ph_max`, `ec_target`, `ec_min`, `ec_max`
  - `irrigation_mode`, `irrigation_interval_sec`, `irrigation_duration_sec`
  - `lighting_photoperiod_hours`, `lighting_start_time`
  - `mist_interval_sec`, `mist_duration_sec`, `mist_mode`
  - `temp_air_target`, `humidity_target`, `co2_target`
- `extensions` (jsonb nullable) — только для расширений
- `created_at`, `updated_at`
- **UNIQUE(phase_id, step_index)**

### C) Цикл как центр истины

#### `grow_cycles`
- `id` (PK)
- `zone_id` (FK → zones)
- `plant_id` (FK → plants)
- `recipe_id` (FK → grow_recipes)
- `recipe_revision_id` (FK NOT NULL → recipe_revisions) — **обязательно**
- `status` (enum: PLANNED|RUNNING|PAUSED|HARVESTED|ABORTED|AWAITING_CONFIRM)
- `current_phase_id` (FK nullable → recipe_revision_phases) — текущая фаза
- `current_step_id` (FK nullable → recipe_revision_phase_steps) — текущий шаг
- `started_at`, `ended_at` (timestamp nullable)
- `planting_at` (timestamp nullable)
- `phase_started_at` (timestamp nullable)
- `step_started_at` (timestamp nullable)
- `progress_meta` (jsonb nullable) — для temp/light коррекций
- `settings` (jsonb nullable)
- `created_at`, `updated_at`
- **Partial unique index:** `(zone_id) WHERE status IN ('PLANNED','RUNNING','PAUSED')`

#### `grow_cycle_phases` (снапшоты)
- `id` (PK)
- `grow_cycle_id` (FK → grow_cycles)
- `recipe_revision_phase_id` (FK nullable → recipe_revision_phases) — для трассировки
- `phase_index` (integer)
- `name` (string)
- **Все поля уставок как в recipe_revision_phases (колонками)**
- `started_at`, `ended_at` (timestamp nullable)
- `created_at`, `updated_at`
- **UNIQUE(grow_cycle_id, phase_index)**

#### `grow_cycle_phase_steps` (снапшоты)
- `id` (PK)
- `grow_cycle_phase_id` (FK → grow_cycle_phases)
- `recipe_revision_phase_step_id` (FK nullable → recipe_revision_phase_steps) — для трассировки
- `step_index` (integer)
- `name` (string)
- **Все поля уставок как в recipe_revision_phase_steps (колонками)**
- `started_at`, `ended_at` (timestamp nullable)
- `created_at`, `updated_at`
- **UNIQUE(grow_cycle_phase_id, step_index)**

#### `grow_cycle_overrides`
- `id` (PK)
- `grow_cycle_id` (FK → grow_cycles)
- `parameter_name` (string) — например "ph_target", "ec_target"
- `value` (jsonb) — новое значение
- `reason` (text nullable)
- `created_by` (FK → users)
- `valid_from` (timestamp)
- `valid_until` (timestamp nullable)
- `created_at`, `updated_at`
- **Index:** `(grow_cycle_id, valid_from, valid_until)` для активных override'ов

#### `grow_cycle_transitions`
- `id` (PK)
- `grow_cycle_id` (FK → grow_cycles)
- `from_phase_id` (FK nullable → recipe_revision_phases, restrictOnDelete)
- `to_phase_id` (FK nullable → recipe_revision_phases, restrictOnDelete) — **nullable для завершения цикла**
- `from_step_id` (FK nullable → recipe_revision_phase_steps, restrictOnDelete)
- `to_step_id` (FK nullable → recipe_revision_phase_steps, restrictOnDelete)
- `trigger_type` (enum: AUTO|MANUAL|RECIPE_CHANGE|SYSTEM)
- `comment` (text nullable)
- `triggered_by` (FK nullable → users)
- `metadata` (jsonb nullable)
- `created_at`, `updated_at`
- **Index:** `(grow_cycle_id, created_at)`

### D) Инфраструктура

#### `infrastructure_instances`
- `id` (PK)
- `owner_type` (enum: zone|greenhouse)
- `owner_id` (integer)
- `asset_type` (enum: PUMP|MISTER|TANK_CLEAN|TANK_WORKING|LIGHT|VENT|HEATER|...)
- `label` (string)
- `specs` (jsonb nullable)
- `required` (boolean, default true)
- `created_at`, `updated_at`
- **Polymorphic index:** `(owner_type, owner_id)`

#### `channel_bindings`
- `id` (PK)
- `infrastructure_instance_id` (FK → infrastructure_instances)
- `node_channel_id` (FK → node_channels) — **нормализовано через node_channels**
- `direction` (enum: actuator|sensor)
- `role` (string) — main_pump|drain_pump|mister|fan|heater|ph_sensor|ec_sensor|...
- `created_at`, `updated_at`
- **UNIQUE(infrastructure_instance_id, node_channel_id)**
- **UNIQUE(node_channel_id)** — один канал не может принадлежать двум инстансам

### E) Сенсоры и телеметрия

#### `sensors`
- `id` (PK)
- `greenhouse_id` (FK NOT NULL → greenhouses)
- `zone_id` (FK nullable → zones) — NULL для тепличных/наружных
- `node_id` (FK nullable → nodes)
- `scope` (enum: inside|outside)
- `type` (enum: TEMPERATURE|HUMIDITY|CO2|PH|EC|...)
- `label` (string)
- `unit` (string nullable)
- `specs` (jsonb nullable)
- `is_active` (boolean, default true)
- `last_read_at` (timestamp nullable)
- `created_at`, `updated_at`
- **Index:** `(zone_id)`, `(greenhouse_id, scope)`, `(greenhouse_id, type)`, `(node_id)`, `(is_active)`
- **UNIQUE:** `(zone_id, node_id, scope, type, label)`

#### `telemetry_samples` (партиционирование)
- `id` (PK)
- `sensor_id` (FK → sensors)
- `ts` (timestamp)
- `zone_id` (FK nullable → zones) — проставляет сервер
- `cycle_id` (FK nullable → grow_cycles) — проставляет сервер
- `value` (decimal)
- `quality` (enum: GOOD|BAD|UNCERTAIN)
- `metadata` (jsonb nullable)
- `created_at`
- **Partitioned by:** `ts` (range, по месяцам)
- **Index:** `(sensor_id, ts)`, `(zone_id, ts)`, `(cycle_id, ts)`

#### `telemetry_last` (кэш)
- `sensor_id` (PK, FK → sensors)
- `last_value` (decimal)
- `last_ts` (timestamp)
- `last_quality` (enum)
- `updated_at`

### F) Команды и подтверждения

#### `commands`
- `id` (PK)
- `cycle_id` (FK nullable → grow_cycles) — **nullable для внецикловых команд**
- `context_type` (enum: cycle|manual|maintenance|calibration)
- `node_id` (FK → nodes)
- `channel` (string)
- `command_type` (enum: SET|GET|CALIBRATE|...)
- `payload` (jsonb)
- `status` (enum: queued|sent|accepted|executing|done|failed|timeout)
- `request_id` (string, unique) — для двухфазного подтверждения
- `created_at`, `updated_at`
- **Index:** `(cycle_id)`, `(node_id, status)`, `(request_id)`

#### `command_acks`
- `id` (PK)
- `command_id` (FK → commands)
- `ack_type` (enum: accepted|executed|verified|error)
- `measured_current` (decimal nullable)
- `measured_flow` (decimal nullable)
- `error_message` (text nullable)
- `metadata` (jsonb nullable)
- `created_at`
- **Index:** `(command_id, ack_type)`

### G) Алерты / события

#### `alerts`
- `id` (PK)
- `zone_id` (FK nullable → zones)
- `cycle_id` (FK nullable → grow_cycles)
- `severity` (enum: INFO|WARNING|ERROR|CRITICAL)
- `type` (string)
- `message` (text)
- `resolved_at` (timestamp nullable)
- `created_at`, `updated_at`
- **Index:** `(zone_id, resolved_at)`, `(cycle_id, resolved_at)`

#### `zone_events` / `cycle_events` (партиционирование)
- `id` (PK)
- `zone_id` (FK → zones)
- `cycle_id` (FK nullable → grow_cycles)
- `entity_type` (enum: grow_cycle|infrastructure|sensor|...)
- `entity_id` (integer)
- `type` (string) — CYCLE_STARTED|CYCLE_PAUSED|PHASE_CHANGED|...
- `data` (jsonb nullable)
- `created_at`
- **Partitioned by:** `created_at` (range, по месяцам)
- **Index:** `(zone_id, created_at)`, `(cycle_id, created_at)`

## 3) Ключевые constraints и индексы

### Обязательные constraints

1. **Уникальность активного цикла:**
   ```sql
   CREATE UNIQUE INDEX grow_cycles_zone_active_unique 
   ON grow_cycles(zone_id) 
   WHERE status IN ('PLANNED', 'RUNNING', 'PAUSED');
   ```

2. **1 зона = 1 нода:**
   ```sql
   CREATE UNIQUE INDEX nodes_zone_unique 
   ON nodes(zone_id) 
   WHERE zone_id IS NOT NULL;
   ```
   Или альтернативно:
   ```sql
   CREATE UNIQUE INDEX zones_node_unique 
   ON zones(node_id) 
   WHERE node_id IS NOT NULL;
   ```

3. **Уникальность каналов ноды:**
   ```sql
   UNIQUE(node_id, channel) в node_channels
   ```

4. **Уникальность привязки канала:**
   ```sql
   UNIQUE(infrastructure_instance_id, node_channel_id) в channel_bindings
   UNIQUE(node_channel_id) в channel_bindings
   ```

5. **Упорядочивание фаз/шагов:**
   ```sql
   UNIQUE(recipe_revision_id, phase_index) в recipe_revision_phases
   UNIQUE(phase_id, step_index) в recipe_revision_phase_steps
   UNIQUE(grow_cycle_id, phase_index) в grow_cycle_phases
   UNIQUE(grow_cycle_phase_id, step_index) в grow_cycle_phase_steps
   ```

6. **NOT NULL constraints:**
   - `grow_cycles.recipe_revision_id` — обязательно
   - `commands.request_id` — обязательно для двухфазного подтверждения

## 4) Статусы и enum'ы

### GrowCycleStatus
- `PLANNED` — запланирован
- `RUNNING` — выполняется
- `PAUSED` — приостановлен
- `HARVESTED` — завершён (урожай собран)
- `ABORTED` — прерван
- `AWAITING_CONFIRM` — ожидает подтверждения команды

### RecipeRevisionStatus
- `DRAFT` — черновик (можно редактировать)
- `PUBLISHED` — опубликован (заблокирован для редактирования)

### CommandStatus
- `queued` — в очереди
- `sent` — отправлена
- `accepted` — принята (ACK получен)
- `executing` — выполняется
- `done` — выполнена успешно
- `failed` — ошибка выполнения
- `timeout` — таймаут

### CommandAckType
- `accepted` — команда принята к выполнению
- `executed` — команда выполнена
- `verified` — результат проверен
- `error` — ошибка выполнения

## 5) Партиционирование и retention

### telemetry_samples
- **Partitioning:** Range по `ts` (по месяцам)
- **Retention:** Raw данные — 90 дней, агрегаты — 1 год

### zone_events / cycle_events
- **Partitioning:** Range по `created_at` (по месяцам)
- **Retention:** 1 год

## 6) Миграционная стратегия

- **Режим:** `migrate:fresh --seed` (без обратной совместимости)
- **Legacy таблицы:** удаляются жёстко
- **Data migration:** только если критично сохранить данные (на этом этапе проще не сохранять)
