# Этап 1: Пересборка схемы БД под новую доменную модель

**Ветка:** `refactor/grow-cycle-centric`  
**Дата:** 2025-12-25  
**Статус:** ✅ Завершено

## Цель этапа

Пересобрать схему БД под новую доменную модель с центром истины в `grow_cycles` и ревизиями рецептов, удалив legacy таблицы и колонки.

## Выполненные работы

### 1.1. Новые таблицы (миграции созданы)

#### ✅ `recipe_revisions`
- Версионирование рецептов (DRAFT|PUBLISHED|ARCHIVED)
- Связь с `recipes` (1—N)
- Поля: `revision_number`, `status`, `description`, `created_by`, `published_at`
- Уникальность: `(recipe_id, revision_number)`

**Миграция:** `2025_12_25_151705_create_recipe_revisions_table.php`

#### ✅ `recipe_revision_phases`
- Фазы ревизии рецепта с целевыми параметрами по колонкам (не JSONB)
- Связь с `recipe_revisions` (1—N) и `grow_stage_templates` (N—1)
- Обязательные параметры (MVP):
  - `ph_target`, `ph_min`, `ph_max`
  - `ec_target`, `ec_min`, `ec_max`
  - `irrigation_mode` ENUM('SUBSTRATE','RECIRC')
  - `irrigation_interval_sec`, `irrigation_duration_sec`
- Опциональные параметры:
  - `lighting_photoperiod_hours`, `lighting_start_time`
  - `mist_interval_sec`, `mist_duration_sec`, `mist_mode`
  - `temp_air_target`, `humidity_target`, `co2_target`
  - `progress_model`, `duration_hours|days`, `base_temp_c`, `target_gdd`, `dli_target`
- Уникальность: `(recipe_revision_id, phase_index)`

**Миграция:** `2025_12_25_151706_create_recipe_revision_phases_table.php`

#### ✅ `recipe_revision_phase_steps`
- Подшаги внутри фазы (опционально)
- Связь с `recipe_revision_phases` (1—N)
- Поля: `step_index`, `name`, `offset_hours`, `action`, `description`, `targets_override`
- Уникальность: `(phase_id, step_index)`

**Миграция:** `2025_12_25_151707_create_recipe_revision_phase_steps_table.php`

#### ✅ `grow_cycle_overrides`
- Перекрытия целевых параметров для активного цикла
- Таблица для аудита (лучше чем JSONB)
- Поля: `parameter`, `value_type`, `value`, `reason`, `created_by`, `applies_from`, `applies_until`, `is_active`
- Индексы для быстрого поиска активных перекрытий

**Миграция:** `2025_12_25_151708_create_grow_cycle_overrides_table.php`

#### ✅ `grow_cycle_transitions`
- История переходов фаз в цикле выращивания
- Логирует все переходы: AUTO|MANUAL|RECIPE_CHANGE|SYSTEM
- Поля: `from_phase_id`, `to_phase_id`, `from_step_id`, `to_step_id`, `trigger_type`, `comment`, `triggered_by`, `metadata`
- Индексы для истории переходов

**Миграция:** `2025_12_25_151709_create_grow_cycle_transitions_table.php`

### 1.2. Модификация `grow_cycles`

#### ✅ Удалено:
- `zone_recipe_instance_id` (legacy связь)

#### ✅ Добавлено:
- `recipe_revision_id` (FK → `recipe_revisions`, nullable пока, потом NOT NULL)
- `current_phase_id` (FK → `recipe_revision_phases`, nullable)
- `current_step_id` (FK → `recipe_revision_phase_steps`, nullable)
- `planting_at` (timestamp, nullable) - дата посадки
- `phase_started_at` (timestamp, nullable) - когда началась текущая фаза
- `step_started_at` (timestamp, nullable) - когда начался текущий шаг
- `progress_meta` (jsonb, nullable) - метаданные прогресса (temp/light коррекции, computed_due_at)

**Миграция:** `2025_12_25_151710_modify_grow_cycles_table.php`

**Примечание:** Добавлены проверки на существование колонок перед их добавлением для идемпотентности миграции.

### 1.3. Полиморфная инфраструктура

#### ✅ `infrastructure_instances`
- Заменяет `zone_infrastructure` + `infrastructure_assets`
- Полиморфная связь: `owner_type` ('zone'|'greenhouse'), `owner_id`
- Поля: `asset_type` ENUM, `label`, `required`, `capacity_liters`, `flow_rate`, `specs`
- Индексы для поиска по owner и типу

**Миграция:** `2025_12_25_151711_create_infrastructure_instances_table.php`

#### ✅ `channel_bindings`
- Заменяет `zone_channel_bindings`
- Owner-agnostic привязка каналов к инфраструктуре
- Поля: `infrastructure_instance_id`, `node_id`, `channel`, `direction`, `role`
- Уникальность: `(infrastructure_instance_id, node_id, channel)`

**Миграция:** `2025_12_25_151712_create_channel_bindings_table.php`

### 1.4. Ограничения целостности

#### ✅ Уникальность активного цикла на зону
- Частичный уникальный индекс: `grow_cycles(zone_id) WHERE status IN ('RUNNING','PAUSED')`
- Гарантирует: только один RUNNING или PAUSED цикл в зоне одновременно

#### ✅ Enforce "1 node = 1 zone"
- Частичный уникальный индекс: `nodes(zone_id) WHERE zone_id IS NOT NULL`
- Гарантирует: только один нода может быть привязан к одной зоне

**Миграция:** `2025_12_25_151713_add_constraints_to_grow_cycles.php`

### 1.5. Удаление legacy таблиц

#### ✅ Удалены таблицы:
- `zone_recipe_instances` (заменено на `grow_cycles` + `recipe_revisions`)
- `recipe_phases` (legacy JSON targets, заменено на `recipe_revision_phases`)
- `zone_cycles` (дублирование, заменено на `grow_cycles`)
- `plant_cycles` (если существовала, дублирование)
- `commands_archive` (дубли, retention через политики)
- `zone_events_archive` (дубли, retention через политики)
- `recipe_stage_maps` (заменено на `stage_template_id` в `recipe_revision_phases`)
- `zone_infrastructure` (заменено на `infrastructure_instances`)
- `infrastructure_assets` (заменено на `infrastructure_instances`)
- `zone_channel_bindings` (заменено на `channel_bindings`)

**Миграция:** `2025_12_25_151714_drop_legacy_tables.php`

**Примечание:** В `down()` методе восстановлена структура таблиц для возможности rollback (без данных).

## Результаты

### ✅ Миграции выполнены успешно
```
2025_12_25_151705_create_recipe_revisions_table ............... DONE
2025_12_25_151706_create_recipe_revision_phases_table ........... DONE
2025_12_25_151707_create_recipe_revision_phase_steps_table ...... DONE
2025_12_25_151708_create_grow_cycle_overrides_table ............ DONE
2025_12_25_151709_create_grow_cycle_transitions_table .......... DONE
2025_12_25_151710_modify_grow_cycles_table ..................... DONE
2025_12_25_151711_create_infrastructure_instances_table ........ DONE
2025_12_25_151712_create_channel_bindings_table ................ DONE
2025_12_25_151713_add_constraints_to_grow_cycles ............... DONE
2025_12_25_151714_drop_legacy_tables .......................... DONE
```

### ⚠️ Известные проблемы

1. **Сидеры используют старые таблицы**
   - Сидеры пытаются использовать `infrastructure_assets` и другие удаленные таблицы
   - Требуется обновление сидеров на Этапе 2 (модели и сервисы)

2. **`recipe_revision_id` пока nullable**
   - После заполнения данных можно сделать NOT NULL
   - Требуется миграция данных из legacy таблиц (если есть)

## Следующие шаги

1. ✅ Этап 1 завершен
2. ⏭️ **Этап 2:** Laravel Backend - модели, сервисы, API, события
   - Создать Eloquent модели для новых таблиц
   - Обновить существующие модели
   - Удалить модели legacy таблиц
   - Обновить сидеры

## Acceptance Criteria

- ✅ `php artisan migrate:fresh` проходит без ошибок
- ✅ Схема соответствует новой модели
- ✅ Legacy таблицы удалены
- ✅ Ограничения целостности добавлены
- ⚠️ Сидеры требуют обновления (будет выполнено на Этапе 2)

---

**Примечание:** Все миграции работают с `migrate:fresh` (backward compatibility не требуется по плану рефакторинга).

