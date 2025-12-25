# Этап 1: Проверка всех колонок таблиц

**Дата:** 2025-12-25  
**Статус:** ✅ Проверка завершена

## Результаты проверки структуры таблиц

### 1. recipe_revisions ✅

**Колонки:**
- `id` (bigint, PK)
- `recipe_id` (bigint, FK → recipes, NOT NULL)
- `revision_number` (integer, NOT NULL, default: 1)
- `status` (varchar, NOT NULL, default: 'DRAFT')
- `description` (text, nullable)
- `created_by` (bigint, FK → users, nullable)
- `published_at` (timestamp, nullable)
- `created_at`, `updated_at` (timestamps)

**Индексы:**
- ✅ PRIMARY KEY (id)
- ✅ UNIQUE (recipe_id, revision_number)
- ✅ INDEX (recipe_id, status)

**Соответствие плану:** ✅ Полностью соответствует

---

### 2. recipe_revision_phases ✅

**Обязательные колонки (MVP):**
- ✅ `ph_target` (numeric(4,2), nullable)
- ✅ `ph_min` (numeric(4,2), nullable)
- ✅ `ph_max` (numeric(4,2), nullable)
- ✅ `ec_target` (numeric(5,2), nullable)
- ✅ `ec_min` (numeric(5,2), nullable)
- ✅ `ec_max` (numeric(5,2), nullable)
- ✅ `irrigation_mode` (ENUM: 'SUBSTRATE'|'RECIRC', nullable) - реализовано как CHECK constraint
- ✅ `irrigation_interval_sec` (integer, nullable)
- ✅ `irrigation_duration_sec` (integer, nullable)

**Опциональные колонки:**
- ✅ `lighting_photoperiod_hours` (integer, nullable)
- ✅ `lighting_start_time` (time, nullable)
- ✅ `mist_interval_sec` (integer, nullable)
- ✅ `mist_duration_sec` (integer, nullable)
- ✅ `mist_mode` (ENUM: 'NORMAL'|'SPRAY', nullable) - реализовано как CHECK constraint
- ✅ `temp_air_target` (numeric(5,2), nullable)
- ✅ `humidity_target` (numeric(5,2), nullable)
- ✅ `co2_target` (integer, nullable)
- ✅ `progress_model` (varchar, nullable)
- ✅ `duration_hours` (integer, nullable)
- ✅ `duration_days` (integer, nullable)
- ✅ `base_temp_c` (numeric(4,2), nullable)
- ✅ `target_gdd` (numeric(8,2), nullable)
- ✅ `dli_target` (numeric(6,2), nullable)

**Дополнительные колонки:**
- ✅ `id` (bigint, PK)
- ✅ `recipe_revision_id` (bigint, FK → recipe_revisions, NOT NULL)
- ✅ `stage_template_id` (bigint, FK → grow_stage_templates, nullable) - вариант Б из плана
- ✅ `phase_index` (integer, NOT NULL, default: 0)
- ✅ `name` (varchar, NOT NULL)
- ✅ `extensions` (jsonb, nullable) - для нестандартных параметров
- ✅ `created_at`, `updated_at` (timestamps)

**Индексы:**
- ✅ PRIMARY KEY (id)
- ✅ UNIQUE (recipe_revision_id, phase_index)
- ✅ INDEX (recipe_revision_id)
- ✅ INDEX (stage_template_id)

**CHECK constraints:**
- ✅ `irrigation_mode` IN ('SUBSTRATE', 'RECIRC')
- ✅ `mist_mode` IN ('NORMAL', 'SPRAY')

**Соответствие плану:** ✅ Полностью соответствует, все обязательные и опциональные поля присутствуют

---

### 3. recipe_revision_phase_steps ✅

**Колонки:**
- ✅ `id` (bigint, PK)
- ✅ `phase_id` (bigint, FK → recipe_revision_phases, NOT NULL)
- ✅ `step_index` (integer, NOT NULL, default: 0)
- ✅ `name` (varchar, NOT NULL)
- ✅ `offset_hours` (integer, NOT NULL, default: 0)
- ✅ `action` (varchar, nullable)
- ✅ `description` (text, nullable)
- ✅ `targets_override` (jsonb, nullable)
- ✅ `created_at`, `updated_at` (timestamps)

**Индексы:**
- ✅ PRIMARY KEY (id)
- ✅ UNIQUE (phase_id, step_index)
- ✅ INDEX (phase_id)

**Соответствие плану:** ✅ Полностью соответствует

---

### 4. grow_cycle_overrides ✅

**Колонки:**
- ✅ `id` (bigint, PK)
- ✅ `grow_cycle_id` (bigint, FK → grow_cycles, NOT NULL)
- ✅ `parameter` (varchar, NOT NULL)
- ✅ `value_type` (varchar, NOT NULL, default: 'decimal')
- ✅ `value` (text, NOT NULL)
- ✅ `reason` (text, nullable)
- ✅ `created_by` (bigint, FK → users, nullable)
- ✅ `applies_from` (timestamp, nullable)
- ✅ `applies_until` (timestamp, nullable)
- ✅ `is_active` (boolean, NOT NULL, default: true)
- ✅ `created_at`, `updated_at` (timestamps)

**Индексы:**
- ✅ PRIMARY KEY (id)
- ✅ INDEX (grow_cycle_id, is_active)
- ✅ INDEX (grow_cycle_id, parameter)

**Соответствие плану:** ✅ Полностью соответствует (таблица для аудита вместо JSONB)

---

### 5. grow_cycle_transitions ✅

**Колонки:**
- ✅ `id` (bigint, PK)
- ✅ `grow_cycle_id` (bigint, FK → grow_cycles, NOT NULL)
- ✅ `from_phase_id` (bigint, FK → recipe_revision_phases, nullable)
- ✅ `to_phase_id` (bigint, FK → recipe_revision_phases, NOT NULL)
- ✅ `from_step_id` (bigint, FK → recipe_revision_phase_steps, nullable)
- ✅ `to_step_id` (bigint, FK → recipe_revision_phase_steps, nullable)
- ✅ `trigger_type` (varchar, NOT NULL) - AUTO|MANUAL|RECIPE_CHANGE|SYSTEM
- ✅ `comment` (text, nullable)
- ✅ `triggered_by` (bigint, FK → users, nullable)
- ✅ `metadata` (jsonb, nullable)
- ✅ `created_at`, `updated_at` (timestamps)

**Индексы:**
- ✅ PRIMARY KEY (id)
- ✅ INDEX (grow_cycle_id)
- ✅ INDEX (grow_cycle_id, created_at)
- ✅ INDEX (trigger_type)

**Соответствие плану:** ✅ Полностью соответствует

---

### 6. infrastructure_instances ✅

**Колонки:**
- ✅ `id` (bigint, PK)
- ✅ `owner_type` (varchar, NOT NULL) - 'zone'|'greenhouse'
- ✅ `owner_id` (bigint, NOT NULL)
- ✅ `asset_type` (ENUM, NOT NULL) - реализовано как CHECK constraint
- ✅ `label` (varchar, NOT NULL)
- ✅ `required` (boolean, NOT NULL, default: false)
- ✅ `capacity_liters` (numeric(10,2), nullable)
- ✅ `flow_rate` (numeric(10,2), nullable)
- ✅ `specs` (jsonb, nullable)
- ✅ `created_at`, `updated_at` (timestamps)

**CHECK constraints:**
- ✅ `asset_type` IN ('PUMP', 'MISTER', 'TANK_CLEAN', 'TANK_WORKING', 'TANK_NUTRIENT', 'DRAIN', 'LIGHT', 'VENT', 'HEATER', 'FAN', 'CO2_INJECTOR', 'OTHER')

**Индексы:**
- ✅ PRIMARY KEY (id)
- ✅ INDEX (owner_type, owner_id)
- ✅ INDEX (owner_type, owner_id, asset_type)
- ✅ INDEX (owner_type, owner_id, required)

**Соответствие плану:** ✅ Полностью соответствует (полиморфная инфраструктура)

---

### 7. channel_bindings ✅

**Колонки:**
- ✅ `id` (bigint, PK)
- ✅ `infrastructure_instance_id` (bigint, FK → infrastructure_instances, NOT NULL)
- ✅ `node_id` (bigint, FK → nodes, NOT NULL)
- ✅ `channel` (varchar, NOT NULL)
- ✅ `direction` (ENUM, NOT NULL) - реализовано как CHECK constraint
- ✅ `role` (varchar, NOT NULL)
- ✅ `created_at`, `updated_at` (timestamps)

**CHECK constraints:**
- ✅ `direction` IN ('actuator', 'sensor')

**Индексы:**
- ✅ PRIMARY KEY (id)
- ✅ UNIQUE (infrastructure_instance_id, node_id, channel)
- ✅ INDEX (infrastructure_instance_id)
- ✅ INDEX (node_id, channel)

**Соответствие плану:** ✅ Полностью соответствует (owner-agnostic)

---

### 8. grow_cycles ✅

**Удаленные legacy колонки (проверено):**
- ✅ `zone_recipe_instance_id` - УДАЛЕНО
- ✅ `current_stage_code` - УДАЛЕНО
- ✅ `current_stage_started_at` - УДАЛЕНО

**Существующие колонки:**
- ✅ `id` (bigint, PK)
- ✅ `greenhouse_id` (bigint, FK → greenhouses, NOT NULL)
- ✅ `zone_id` (bigint, FK → zones, NOT NULL)
- ✅ `plant_id` (bigint, FK → plants, nullable)
- ✅ `recipe_id` (bigint, FK → recipes, nullable) - оставлено для совместимости
- ✅ `status` (varchar, NOT NULL, default: 'PLANNED')
- ✅ `started_at` (timestamp, nullable)
- ✅ `recipe_started_at` (timestamp, nullable)
- ✅ `expected_harvest_at` (timestamp, nullable)
- ✅ `actual_harvest_at` (timestamp, nullable)
- ✅ `batch_label` (varchar, nullable)
- ✅ `notes` (text, nullable)
- ✅ `settings` (jsonb, nullable)

**Новые колонки (добавлены):**
- ✅ `recipe_revision_id` (bigint, FK → recipe_revisions, nullable) - будет NOT NULL после миграции данных
- ✅ `current_phase_id` (bigint, FK → recipe_revision_phases, nullable)
- ✅ `current_step_id` (bigint, FK → recipe_revision_phase_steps, nullable)
- ✅ `planting_at` (timestamp, nullable)
- ✅ `phase_started_at` (timestamp, nullable)
- ✅ `step_started_at` (timestamp, nullable)
- ✅ `progress_meta` (jsonb, nullable)

**Индексы:**
- ✅ PRIMARY KEY (id)
- ✅ INDEX (greenhouse_id)
- ✅ INDEX (zone_id)
- ✅ INDEX (status)
- ✅ INDEX (zone_id, status)
- ✅ **UNIQUE PARTIAL INDEX** (zone_id) WHERE status IN ('RUNNING', 'PAUSED') - ограничение целостности

**Соответствие плану:** ✅ Полностью соответствует, все legacy поля удалены, новые добавлены

---

## Итоговая проверка

### ✅ Все таблицы соответствуют плану рефакторинга

1. **Новые таблицы созданы корректно** - все колонки присутствуют
2. **Legacy колонки удалены** - проверено отсутствие в grow_cycles
3. **Типы данных корректны** - соответствуют плану
4. **Ограничения целостности** - уникальность активного цикла, упорядочивание фаз
5. **Foreign keys** - все связи настроены правильно
6. **Индексы** - оптимизированы для запросов

### ⚠️ Замечания

1. **recipe_revision_id в grow_cycles пока nullable**
   - По плану должно быть NOT NULL после заполнения данных
   - Требуется миграция данных из legacy таблиц (если есть)

2. **recipe_id в grow_cycles оставлено**
   - Можно удалить после полного перехода на recipe_revisions
   - Или оставить для обратной совместимости (но по плану backward compat не требуется)

### ✅ Готово к Этапу 2

Все колонки проверены и соответствуют плану рефакторинга. Можно переходить к созданию Eloquent моделей.

