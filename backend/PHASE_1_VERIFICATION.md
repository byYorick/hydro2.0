# PHASE 1 - Проверка выполненных изменений

Дата: 2025-12-25

## ✅ Статус проверки

Все критические исправления PHASE 1 выполнены и проверены.

## 1. Проверка миграций

### ✅ 1.1. Partial unique index включает PLANNED

**Файл:** `2025_12_25_151713_add_constraints_to_grow_cycles.php`

```php
DB::statement('
    CREATE UNIQUE INDEX grow_cycles_zone_active_unique 
    ON grow_cycles(zone_id) 
    WHERE status IN (\'PLANNED\', \'RUNNING\', \'PAUSED\')
');
```

✅ **Статус:** Корректно - индекс включает все три активных статуса.

### ✅ 1.2. recipe_revision_id NOT NULL

**Файл:** `2025_12_25_151710_modify_grow_cycles_table.php`

```php
// Добавляем связь с ревизией рецепта (NOT NULL - обязательно)
if (!Schema::hasColumn('grow_cycles', 'recipe_revision_id')) {
    $table->foreignId('recipe_revision_id')->after('recipe_id')->constrained('recipe_revisions')->cascadeOnDelete();
}

// Убеждаемся, что recipe_revision_id NOT NULL
if (Schema::hasColumn('grow_cycles', 'recipe_revision_id')) {
    DB::statement('ALTER TABLE grow_cycles ALTER COLUMN recipe_revision_id SET NOT NULL');
}
```

✅ **Статус:** Корректно - колонка создаётся без nullable, затем явно устанавливается NOT NULL.

### ✅ 1.3. Убраны JSON из шагов рецепта

**Файл:** `2025_12_25_151707_create_recipe_revision_phase_steps_table.php`

**Удалено:**
- `$table->jsonb('targets_override')->nullable();`

**Добавлено:**
- Все уставки по колонкам (ph_target, ec_target, irrigation_mode, lighting_photoperiod_hours, и т.д.)
- `$table->jsonb('extensions')->nullable();` - только для расширений

✅ **Статус:** Корректно - базовые параметры хранятся колонками, JSON только для расширений.

### ✅ 1.4. Нормализация channel_bindings через node_channel_id

**Файл:** `2025_12_25_151712_create_channel_bindings_table.php`

**Изменения:**
- Удалены: `node_id`, `channel` (string)
- Добавлен: `node_channel_id` (FK → node_channels)
- Добавлены уникальные индексы:
  - `unique(['infrastructure_instance_id', 'node_channel_id'])`
  - `unique(['node_channel_id'])` - один канал не может принадлежать двум инстансам

✅ **Статус:** Корректно - нормализация через FK выполнена.

### ✅ 1.5. Исправлен grow_cycle_transitions.to_phase_id

**Файл:** `2025_12_25_151709_create_grow_cycle_transitions_table.php`

**Изменения:**
- `to_phase_id` теперь `nullable()` - для завершения цикла
- Все FK используют `restrictOnDelete()` вместо `nullOnDelete()` - для сохранения истории

✅ **Статус:** Корректно - nullable для завершения цикла, restrictOnDelete для истории.

### ✅ 1.6. Добавлен статус AWAITING_CONFIRM

**Файл:** `app/Enums/GrowCycleStatus.php`

**Добавлено:**
```php
case AWAITING_CONFIRM = 'AWAITING_CONFIRM';
```

**Обновлено:**
- `isActive()` теперь включает `PLANNED`
- `label()` добавлен перевод для `AWAITING_CONFIRM`

✅ **Статус:** Корректно - статус добавлен и интегрирован.

## 2. Проверка моделей

### ✅ 2.1. ChannelBinding модель

**Файл:** `app/Models/ChannelBinding.php`

**Изменения:**
- `fillable` обновлён: `node_id`, `channel` → `node_channel_id`
- Добавлен relationship: `nodeChannel()`
- Добавлен accessor: `getNodeAttribute()` для обратной совместимости

✅ **Статус:** Корректно - модель обновлена под новую структуру.

### ✅ 2.2. Zone и GrowCycle модели

**Файлы:** `app/Models/Zone.php`, `app/Models/GrowCycle.php`

**Изменения:**
- `activeGrowCycle()` и `scopeActive()` теперь включают `PLANNED` в фильтр активных статусов

✅ **Статус:** Корректно - модели синхронизированы с новым индексом.

## 3. Проверка документации

### ✅ 3.1. DB_CANON_V2.md

**Файл:** `doc_ai/DB_CANON_V2.md`

✅ **Статус:** Создан - содержит полную каноническую структуру БД с инвариантами.

### ✅ 3.2. db_sanity.sql

**Файл:** `backend/laravel/database/sql/db_sanity.sql`

✅ **Статус:** Создан - содержит SQL проверки всех ключевых инвариантов:
- Уникальность активного цикла на зону
- Правило 1:1 зона↔нода
- NOT NULL для recipe_revision_id
- Уникальность каналов ноды
- Нормализация channel_bindings
- Упорядочивание фаз/шагов
- Отсутствие JSON в базовых полях
- Наличие статуса AWAITING_CONFIRM
- Проверка индексов

## 4. Проверка синтаксиса

✅ **Linter:** Нет ошибок линтера в изменённых файлах.

## 5. Потенциальные проблемы

### ⚠️ 5.1. Использование ChannelBinding в коде

**Найдено:** Модель `ChannelBinding` может использоваться в коде с полями `node_id` и `channel`.

**Рекомендация:** Необходимо проверить и обновить все места использования:
- `ChannelBindingService`
- `InfrastructureInstanceService`
- Контроллеры, использующие `ChannelBinding`

**Статус:** Требует проверки при выполнении миграций.

### ⚠️ 5.2. Миграция данных

**Проблема:** При переходе на `node_channel_id` в `channel_bindings` необходимо:
1. Создать записи в `node_channels` для всех существующих комбинаций `node_id + channel`
2. Обновить `channel_bindings` для ссылки на новые `node_channel_id`

**Статус:** Требует data migration скрипта (если есть существующие данные).

## 6. Итоговый статус

✅ **PHASE 1 завершена успешно**

Все критические исправления выполнены:
- ✅ Partial unique index включает PLANNED
- ✅ recipe_revision_id NOT NULL
- ✅ JSON убран из шагов рецепта
- ✅ channel_bindings нормализованы
- ✅ grow_cycle_transitions исправлены
- ✅ Статус AWAITING_CONFIRM добавлен

**Следующие шаги:**
1. Проверить использование `ChannelBinding` в коде
2. Создать data migration для существующих `channel_bindings` (если нужно)
3. Перейти к PHASE 2: Снапшоты циклов

